"""Hàng đợi một luồng, gom lô theo GIAI ĐOẠN.

Giai đoạn = cặp (loại job, engine). Chạy hết job của giai đoạn hiện tại rồi mới
đổi giai đoạn, nên số lần nạp/đổ model là O(số giai đoạn) thay vì O(số job).
Nạp qwen2.5-7B Q4 mất 5-15s, nên với video ngắn đây là 20-40% tổng thời gian.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Protocol

from app.domain import job_state as js
from app.domain.models import Job
from app.ports.governor import ResourceGovernor
from app.ports.repos import Repos


class JobHandler(Protocol):
    def handles(self) -> str:
        """Loại job mà handler này nhận: 'ingest' | 'asr' | 'translate' | 'export'."""
        ...

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        ...


class JobCancelled(Exception):
    """Handler ném ra từ checkpoint() khi có yêu cầu huỷ."""


class PhaseQueueWorker:
    def __init__(
        self,
        repos: Repos,
        governor: ResourceGovernor,
        handlers: dict[str, JobHandler],
        *,
        poll_interval: float = 0.05,
        sleeper: Callable[[float], None] = time.sleep,
        publish: Callable[[dict], None] | None = None,
    ) -> None:
        self.repos = repos
        self.governor = governor
        self.handlers = handlers
        self.poll_interval = poll_interval
        self._sleep = sleeper
        self._publish = publish or (lambda event: None)
        self.current_phase: str | None = None
        self.phase_switches = 0
        self._stop = threading.Event()

    def _emit(self, job_id: int) -> None:
        """Đẩy một sự kiện cho job vừa đổi trạng thái.

        Đọc lại hàng thay vì nhận tham số: `set_job_state` không trả về trạng
        thái, mà sự kiện phải khớp ĐÚNG thứ đã ghi (kể cả `error` do nhánh
        `except` đặt). Gọi sau MỖI lần ghi, nếu không giao diện đứng im ở trạng
        thái cũ cho tới khi client tự tải lại.

        Publish KHÔNG được làm chết worker: một subscriber hỏng là lỗi của tầng
        stream, không phải lý do để hàng đợi dừng giữa job.
        """
        try:
            job = self.repos.get_job(job_id)
            self._publish(job.to_event())
        except Exception:  # noqa: BLE001 - xem docstring
            pass

    # ---------- vòng đời ----------
    def recover(self) -> int:
        """Gọi MỘT LẦN lúc khởi động, trước run_forever."""
        return self.repos.mark_running_as_interrupted()

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        """Lặp `tick()`. `stop_event` tuỳ chọn để người gọi ngoài cầm cờ dừng.

        Truyền `stop_event` thì dùng nó; bỏ trống thì dùng cờ nội bộ mà `stop()`
        bật. Nhận cả hai dạng để không khoá cứng người gọi.
        """
        stop = stop_event if stop_event is not None else self._stop
        while not stop.is_set():
            if not self.tick():
                self._sleep(self.poll_interval)

    # ---------- một nhịp ----------
    def tick(self) -> bool:
        """Chạy đúng một job. Trả về True nếu có job được chạy.

        TRẢ VỀ FALSE **CHỈ** KHI KHÔNG CÒN JOB CHỜ NÀO, ở bất kỳ giai đoạn nào.
        `tick()` là tín hiệu kết thúc của vòng `while worker.tick(): pass`, nên
        khi giai đoạn hiện tại cạn việc mà vẫn còn giai đoạn khác chờ thì phải
        nhả giai đoạn (để governor đổ model) rồi bốc NGAY job của giai đoạn kế
        tiếp trong CÙNG nhịp này. Trả False sớm sẽ khiến người gọi dừng vòng lặp
        và bỏ quên toàn bộ job còn lại — im lặng, không exception.
        """
        if self.current_phase is not None:
            job = self.repos.next_queued_for_phase(self.current_phase)
            if job is not None:
                self._run_one(job)
                return True
            # Giai đoạn cạn việc: đổ model trước khi chọn giai đoạn mới.
            self._leave_phase()

        nxt = self.repos.oldest_queued()
        if nxt is None:
            # Hàng đợi rỗng thật sự: đây mới là lúc kết thúc vòng lặp.
            return False

        # R43/WQ-01: `oldest_queued()` và `next_queued_for_phase()` phải giữ
        # CÙNG một vị từ (`state = queued`) và cùng `ORDER BY id`; ở đây bốc
        # thẳng job của `oldest_queued()` mà không hỏi lại truy vấn kia, nên
        # thêm một bộ lọc (ví dụ theo `workspace`) vào MỘT trong hai sẽ khiến
        # `tick()` chạy SAI job mà không có test nào đỏ — bất biến đó được ghim
        # bởi `test_worker_phases.
        # test_oldest_queued_and_next_queued_for_phase_agree_on_the_same_job`.
        #
        # Quyết định GĐ1a (đừng "sửa" nhầm): hàng đợi là FIFO TOÀN CỤC, KHÔNG
        # lọc theo `workspace` — hai workspace dùng chung một worker và một GPU.
        # Nếu sau này cần hàng đợi theo workspace thì phải lọc ở CẢ HAI truy vấn.
        self._enter_phase(nxt.phase)
        self._run_one(nxt)
        return True

    def _enter_phase(self, phase: str) -> None:
        self.current_phase = phase
        self.phase_switches += 1
        self.governor.before_phase(phase)

    def _leave_phase(self) -> None:
        # Đọc ra biến cục bộ và XOÁ trạng thái TRƯỚC khi báo governor là chủ ý:
        # `after_phase` ném ra thì `current_phase` vẫn đã được nhả. Nếu để
        # `after_phase` chạy trước, một governor ném lỗi sẽ khiến `tick()` kế
        # tiếp thấy phase còn nguyên, tra không ra job, rồi rời giai đoạn lần
        # nữa — `after_phase` bắn lại VÔ HẠN ở mọi nhịp. Không bắt exception ở
        # đây: lỗi vẫn phải nổi lên cho người gọi thấy, chỉ là có biên.
        phase = self.current_phase
        if phase is None:
            return
        self.current_phase = None
        self.governor.after_phase(phase)

    # ---------- chạy job ----------
    def checkpoint(self, job_id: int) -> None:
        """Handler gọi giữa các bước. Đây là cách duy nhất để huỷ một job dài.

        Không kill tiến trình: nếu kill, DB có thể nằm ở trạng thái nửa vời và
        model đang nạp dở sẽ không được giải phóng.
        """
        if self.repos.get_job(job_id).cancel_requested:
            raise JobCancelled(f"job {job_id} đã được yêu cầu huỷ")

    def _run_one(self, job: Job) -> None:
        assert job.id is not None
        handler = self.handlers.get(job.type)

        self.repos.set_job_state(job.id, js.RUNNING)
        self._emit(job.id)

        if handler is None:
            self.repos.append_job_log(job.id, f"không có handler cho loại {job.type!r}")
            self.repos.set_job_state(
                job.id, js.FAILED, error=f"không có handler cho loại job {job.type!r}"
            )
            self._emit(job.id)
            return

        def report(progress: float, line: str) -> None:
            self.repos.set_job_progress(job.id, progress)
            self.repos.append_job_log(job.id, line)
            self._emit(job.id)

        try:
            handler.run(job, report)
        except JobCancelled:
            self.repos.append_job_log(job.id, "đã huỷ theo yêu cầu ở checkpoint")
            self.repos.set_job_state(job.id, js.CANCELLED)
            self._emit(job.id)
            return
        except Exception as exc:  # noqa: BLE001 - phải bắt hết để hàng đợi sống
            self.repos.append_job_log(job.id, f"LỖI: {exc}")
            self.repos.set_job_state(job.id, js.FAILED, error=f"{type(exc).__name__}: {exc}")
            self._emit(job.id)
            return

        # Kiểm tra yêu cầu huỷ ở RANH GIỚI job. Không có đường nào kill tiến trình.
        fresh = self.repos.get_job(job.id)
        if fresh.cancel_requested:
            self.repos.append_job_log(job.id, "đã huỷ theo yêu cầu")
            self.repos.set_job_state(job.id, js.CANCELLED)
            self._emit(job.id)
            return

        self.repos.set_job_progress(job.id, 1.0)
        self.repos.set_job_state(job.id, js.DONE)
        self._emit(job.id)
