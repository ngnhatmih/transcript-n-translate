"""SỰ CỐ THẬT: một lỗi ở đường GHI SỔ làm CHẾT luôn vòng worker, và hàng đợi đứng im.

Bối cảnh đo được (stack Docker, lượt dùng của người dùng): một lượt dọn DB tay xoá các hàng
`jobs` đúng lúc worker đang chạy job trong số đó. Handler hỏng vì hàng của nó đã biến mất, rồi
đường **báo lỗi** của `_run_one` gọi `append_job_log` và nhận `NotFound`:

    File "/app/app/worker.py", line 203, in _run_one
        self.repos.append_job_log(job.id, f"LỖI: {exc}")
    app.adapters.persist.sqlite_repos.NotFound: job 27 không tồn tại

Exception đó thoát khỏi `tick()` và thoát khỏi `run_forever`, tức **luồng worker chết**. Từ
đó `/api/status` vẫn trả `queue_depth: 1`, giao diện vẫn hiện `chờ gom lô · 0%`, và KHÔNG có
lỗi nào hiện ra cho người dùng: job nằm chờ một worker không còn tồn tại.

⚠️ Đây KHÔNG phải đường của `DELETE /api/sources/{id}`: route đó 409 khi có job đang chạy, và
`delete_source` **cố ý không chạm bảng `jobs`** (job là lịch sử, không phải con của nguồn). Lớp
lỗi là rộng hơn: **bất kỳ** lỗi nào ở đường ghi sổ (`append_job_log`, `set_job_state`,
`get_job` — DB bị khoá, đĩa đầy, hàng đã mất) đều giết vòng lặp vĩnh viễn.
"""
from __future__ import annotations

import threading

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import NotFound, SqliteRepos
from app.domain import job_state as js
from app.worker import PhaseQueueWorker
from tests.fakes import FakeGovernor, RecordingHandler, a_job


class _ReposHongGhiSo:
    """Bọc `SqliteRepos` và làm ĐÚNG một việc: `append_job_log` của job `hong` ném `NotFound`.

    Bọc thay vì sửa repo: repo NÉM là đúng hợp đồng của nó (job không tồn tại thì không có gì
    để ghi), thứ sai là **người gọi** — đường báo lỗi không được phép tự chết.
    """

    def __init__(self, that: SqliteRepos, hong: int) -> None:
        self._that = that
        self._hong = hong

    def __getattr__(self, ten):
        return getattr(self._that, ten)

    def append_job_log(self, job_id: int, line: str) -> None:
        if job_id == self._hong:
            raise NotFound(f"job {job_id} không tồn tại")
        return self._that.append_job_log(job_id, line)


def _repos(tmp_path) -> SqliteRepos:
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def test_run_forever_song_khi_duong_ghi_so_nem_loi(tmp_path, capsys):
    """`run_forever` phải SỐNG: lỗi ghi sổ ở job một không được chặn job hai."""
    that = _repos(tmp_path)
    that.add_job(a_job(None, job_type="asr", engine="e"))
    that.add_job(a_job(None, job_type="asr", engine="e"))
    hong = _ReposHongGhiSo(that, hong=1)

    handler = RecordingHandler(job_type="asr", fail_on={1})
    worker = PhaseQueueWorker(hong, FakeGovernor(), {"asr": handler})

    # Vòng lặp THƯỜNG TRÚ: dừng bằng `stop_event` sau khi hàng đợi đã cạn, và đếm số lần
    # `tick()` trả False để chứng minh vòng lặp THẬT SỰ quay lại sau khi gặp lỗi.
    dung = threading.Event()
    so_lan_ngu = {"n": 0}

    def ngu(_giay: float) -> None:
        so_lan_ngu["n"] += 1
        if so_lan_ngu["n"] >= 2:
            dung.set()

    worker._sleep = ngu  # noqa: SLF001 - cùng khuôn `sleeper=` của `tests/fakes.py`
    worker.run_forever(dung)  # KHÔNG được ném

    assert handler.ran == [1, 2], (
        "job hai phải được chạy sau khi job một làm hỏng đường ghi sổ; "
        f"handler chạy được {handler.ran}"
    )
    assert that.get_job(2).state == js.DONE

    # Chẩn đoán phải NỔI LÊN: im lặng là đúng thứ đã làm sự cố vô hình suốt lượt dùng thật.
    err = capsys.readouterr().err
    assert "Traceback" in err, f"phải in vết lỗi ra stderr, đo được {err!r}"
    assert "job 1 không tồn tại" in err, (
        f"vết lỗi phải nêu ĐÚNG nguyên nhân (hàng jobs đã mất), đo được {err!r}"
    )

    # Vòng lặp còn sống sau đó: cạn việc thì `tick()` trả False thay vì ném.
    assert worker.tick() is False


def test_run_forever_van_dung_khi_duoc_yeu_cau(tmp_path):
    """Đối chứng: nhánh lỗi không được biến vòng lặp thành vòng vô hạn không dừng được."""
    that = _repos(tmp_path)
    handler = RecordingHandler(job_type="asr")
    worker = PhaseQueueWorker(that, FakeGovernor(), {"asr": handler})

    dung = threading.Event()
    dung.set()
    worker.run_forever(dung)
    assert handler.ran == []
