"""Đối tượng giả cho test. KHÔNG nạp model nào, KHÔNG chạm GPU."""
from __future__ import annotations

import datetime as _dt
import itertools
from dataclasses import dataclass, field
from typing import Callable

from app.domain.models import Job, Segment


class FakeClock:
    """Đồng hồ giả: mỗi lần gọi nhảy đúng MỘT giây, bắt đầu từ `start`.

    Không được nội suy mốc từ bộ đếm bằng f-string. Cách đó sinh ra
    `...T00:00:60Z` từ lần gọi thứ 60 (giây 60 không tồn tại) và `...T00:00:100Z`
    từ lần thứ 100 (`:100` đứng TRƯỚC `:99` khi so chuỗi), nên mọi test dựa vào
    thứ tự hay tính duy nhất của mốc thời gian sẽ nhiễm độc âm thầm. Ở đây mốc
    được cộng bằng `timedelta` thật rồi định dạng lại theo đúng khuôn
    `%Y-%m-%dT%H:%M:%SZ` của `SystemClock` — khuôn độ rộng cố định nên thứ tự
    chuỗi trùng với thứ tự thời gian.
    """

    def __init__(self, start: str = "2026-09-25T00:00:00Z") -> None:
        # `datetime.fromisoformat` chỉ hiểu "Z" từ Python 3.11, còn venv này là
        # 3.10 -> phải đổi "Z" thành "+00:00" trước khi parse.
        moment = _dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=_dt.timezone.utc)
        self._start = moment.astimezone(_dt.timezone.utc)
        self._counter = itertools.count()

    def now_iso(self) -> str:
        n = next(self._counter)
        moment = self._start + _dt.timedelta(seconds=n)
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeGovernor:
    """Ghi lại mọi lần nạp/đổ model để test đếm được số lần swap."""

    def __init__(self) -> None:
        self.before: list[str] = []
        self.after: list[str] = []

    def before_phase(self, phase: str) -> None:
        self.before.append(phase)

    def after_phase(self, phase: str) -> None:
        self.after.append(phase)

    def can_run_parallel(self, a_vram_mb: int, b_vram_mb: int) -> bool:
        return False


@dataclass
class RecordingHandler:
    """Handler giả: ghi lại thứ tự job đã chạy, có thể cấu hình để hỏng."""

    job_type: str
    fail_on: set[int] = field(default_factory=set)
    ran: list[int] = field(default_factory=list)
    cancel_after: int | None = None
    _repos: object | None = None
    _job_id_to_cancel: int | None = None

    def handles(self) -> str:
        return self.job_type

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        assert job.id is not None
        self.ran.append(job.id)
        report(0.5, f"chạy job {job.id}")
        if job.id in self.fail_on:
            raise RuntimeError(f"job {job.id} hỏng theo kịch bản test")
        if self.cancel_after is not None and len(self.ran) >= self.cancel_after:
            if self._repos is not None and self._job_id_to_cancel is not None:
                self._repos.request_cancel(self._job_id_to_cancel)
        report(1.0, "xong")


def a_job(job_id_ignored: int | None, *, job_type: str, engine: str,
          workspace: int = 1) -> Job:
    from app.domain.job_state import phase_of
    return Job(id=None, workspace=workspace, type=job_type, engine=engine,
               phase=phase_of(job_type, engine), payload={})
