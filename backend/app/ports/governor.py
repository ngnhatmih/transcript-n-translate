from __future__ import annotations

from typing import Protocol


class ResourceGovernor(Protocol):
    """Hợp đồng điều phối VRAM giữa các giai đoạn.

    DOC-08 (N4): releaser đăng ký với governor **PHẢI idempotent**. `after_phase`
    được worker gọi ở MỖI lần cạn việc của một giai đoạn, và `before_phase` gọi
    releaser của MỌI giai đoạn KHÁC ở mỗi lần vào giai đoạn (đo được: 16 lần gọi
    / 4 lô, engine đổ đúng 4 lần) — nghĩa là cùng một releaser được gọi nhiều
    lần cho một lần nạp model. Gọi lúc không có model nào đang nạp phải là
    no-op; nếu không thì lần gọi thứ hai là double-fire. Hợp đồng này được ghim
    ở `test_registered_releaser_actually_unloads_the_loaded_model` (gọi releaser
    hai lần, `releases` vẫn là 1) và ở test rò VRAM bốn lô của
    `test_worker_phases.py`. Hiện thực: `SingleGpuGovernor.register()`
    (app/adapters/governor/single_gpu.py).
    """

    def before_phase(self, phase: str) -> None:
        """Giải phóng VRAM mà giai đoạn mới cần, trước khi nạp model của nó."""
        ...

    def after_phase(self, phase: str) -> None:
        """Gọi khi rời một giai đoạn (hàng đợi hết việc của giai đoạn đó)."""
        ...

    def can_run_parallel(self, a_vram_mb: int, b_vram_mb: int) -> bool:
        """Chỉ dùng ở GĐ3. GĐ1a luôn trả False."""
        ...
