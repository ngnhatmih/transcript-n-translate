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
        """Đăng ký releaser cho một giai đoạn, và giữ nó VĨNH VIỄN.

        `before_phase`/`after_phase` KHÔNG được pop đăng ký. Worker gọi
        `after_phase` ở MỖI lần cạn giai đoạn, nên bản pop-sau-lần-đầu chỉ đổ
        model đúng MỘT lần trong cả vòng đời tiến trình: từ lần thoát giai đoạn
        thứ hai trở đi không còn releaser nào để gọi và model nằm lại trong
        VRAM (`releases` đứng ở 1 dù engine vẫn nạp).

        Gọi lặp lại là an toàn vì releaser BẮT BUỘC idempotent — `release()` là
        no-op khi không có model nào đang nạp — nên không thể double-free. Yêu
        cầu đó là HỢP ĐỒNG của port (`ports/governor.ResourceGovernor`), không
        phải chi tiết của riêng adapter này: đổi một releaser thành không
        idempotent thì nó sẽ bị double-fire ở đây chứ không bị từ chối lúc
        đăng ký.
        """
        self._loaded[phase] = releaser

    def before_phase(self, phase: str) -> None:
        for other, releaser in list(self._loaded.items()):
            if other != phase:
                releaser()

    def after_phase(self, phase: str) -> None:
        releaser = self._loaded.get(phase)
        if releaser is not None:
            releaser()

    def can_run_parallel(self, a_vram_mb: int, b_vram_mb: int) -> bool:
        # Chế độ song song là GĐ3 và mặc định tắt. Trả False là hành vi thật,
        # không phải chỗ trống chờ điền.
        return False
