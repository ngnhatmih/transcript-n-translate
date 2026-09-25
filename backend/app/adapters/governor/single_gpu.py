from __future__ import annotations

from typing import Callable

from app.ports.repos import Repos


class SingleGpuGovernor:
    """Điều phối VRAM cho một GPU.

    GĐ1a chỉ có ASR chạy in-process và hàng đợi vốn đã tuần tự, nên việc thật
    sự cần làm là: khi rời một giai đoạn thì đảm bảo model của giai đoạn đó
    được giải phóng. Việc đổ model Ollama (keep_alive: 0) là của GĐ2.
    """

    def __init__(self, repos: Repos) -> None:
        self._repos = repos
        self._loaded: dict[str, Callable[[], None]] = {}

    def register(self, phase: str, releaser: Callable[[], None]) -> None:
        self._loaded[phase] = releaser

    def before_phase(self, phase: str) -> None:
        for other, releaser in list(self._loaded.items()):
            if other != phase:
                releaser()
                self._loaded.pop(other, None)

    def after_phase(self, phase: str) -> None:
        releaser = self._loaded.pop(phase, None)
        if releaser is not None:
            releaser()

    def can_run_parallel(self, a_vram_mb: int, b_vram_mb: int) -> bool:
        # Chế độ song song là GĐ3 và mặc định tắt. Trả False là hành vi thật,
        # không phải chỗ trống chờ điền.
        return False
