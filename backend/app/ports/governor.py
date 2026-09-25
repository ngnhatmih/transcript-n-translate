from __future__ import annotations

from typing import Protocol


class ResourceGovernor(Protocol):
    def before_phase(self, phase: str) -> None:
        """Giải phóng VRAM mà giai đoạn mới cần, trước khi nạp model của nó."""
        ...

    def after_phase(self, phase: str) -> None:
        """Gọi khi rời một giai đoạn (hàng đợi hết việc của giai đoạn đó)."""
        ...

    def can_run_parallel(self, a_vram_mb: int, b_vram_mb: int) -> bool:
        """Chỉ dùng ở GĐ3. GĐ1a luôn trả False."""
        ...
