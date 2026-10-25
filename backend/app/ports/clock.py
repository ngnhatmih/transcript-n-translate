from __future__ import annotations

from typing import Protocol


class Clock(Protocol):
    def now_iso(self) -> str:
        """ISO-8601 UTC, ví dụ '2026-09-25T14:02:11Z'."""
        ...
