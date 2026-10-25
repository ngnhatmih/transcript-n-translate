from __future__ import annotations

import datetime as _dt


class SystemClock:
    def now_iso(self) -> str:
        return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FrozenClock:
    """Cho test: thời gian đứng yên, có thể đẩy tay."""

    def __init__(self, start: str = "2026-09-25T00:00:00Z") -> None:
        self._now = start
        self._tick = 0

    def now_iso(self) -> str:
        return self._now

    def advance(self, seconds: int) -> None:
        self._tick += seconds
        base = _dt.datetime.strptime(self._now, "%Y-%m-%dT%H:%M:%SZ")
        self._now = (base + _dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
