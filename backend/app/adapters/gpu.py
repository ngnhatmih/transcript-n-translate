"""Đọc VRAM ĐANG DÙNG của card — dữ liệu cho `GET /api/status`.

Vì sao cần đường riêng: `registry.json` khai `vram_mb` cho từng engine, nhưng đó
là **số KHAI BÁO** dùng cho bộ điều phối (`registry.estimate_vram_mb`), không phải
VRAM đang bị chiếm. GĐ1a trả `vram: null` **TƯỜNG MINH** vì chưa có đường đọc
(`backend/app/api/routes_registry.py`), nên giao diện luôn in "VRAM: chưa đo
được" — đúng, nhưng vô dụng.

Số đo trên máy này (RTX 3070 8 GB, 2026-10-25): 20 lần gọi liên tiếp hết
**811,3 ms** ⇒ **~40,6 ms/lần**, giá trị **1467–1468 MiB** khi không model nào
nằm trong VRAM. Route `/api/status` đã probe Ollama MỖI request (trần
`_OLLAMA_PROBE_SECONDS` = 0,3 s), và frontend KHÔNG poll route này, nên 40 ms là
cùng bậc và **không cần cache** — cache là thêm trạng thái để test và để lệch.

Trả `None` khi không đọc được (không có `nvidia-smi`, không có GPU, timeout,
phản hồi lạ) — cùng khuôn với `ollama: "unknown"`: "chưa biết" phải là một giá
trị NÓI THẬT. Trả `0` cho ca đó là bịa một con số.
"""
from __future__ import annotations

import subprocess

from app.domain.vram import VRAM_UNIT  # noqa: F401 - đơn vị đi kèm số, xem `VramReader`

#: Lệnh đọc số. `nounits` để lấy số nguyên; đơn vị do miền khai
#: (`app/domain/vram.py::VRAM_UNIT`) chứ không đi kèm từng dòng.
NVIDIA_SMI = "nvidia-smi"
_QUERY = ("--query-gpu=memory.used", "--format=csv,noheader,nounits")

#: Trần thời gian MỘT lần gọi. Rộng hơn ~10 lần số đo trung bình (40,6 ms) để
#: một máy đang bận không biến route trạng thái thành route chậm, nhưng vẫn
#: chặn được `nvidia-smi` treo (driver lỗi) làm treo cả request.
DEFAULT_TIMEOUT_S = 0.5


def parse_mib(stdout: str) -> int | None:
    """Số MiB từ dòng ĐẦU TIÊN của `nvidia-smi --query-gpu=memory.used`.

    Nhiều GPU ⇒ dòng đầu là **GPU 0**, đúng card mà governor xếp job lên (ứng
    dụng này chạy một GPU). Dòng rỗng bị bỏ qua; dòng đầu không phải số nguyên
    không âm ⇒ `None` (không đoán, không `float()` hoá một chuỗi lạ).
    """
    for line in stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            value = int(text)
        except ValueError:
            return None
        return value if value >= 0 else None
    return None


def vram_used_mib(timeout_s: float = DEFAULT_TIMEOUT_S) -> int | None:
    """VRAM đang dùng (MiB), hoặc `None` khi không đọc được."""
    try:
        done = subprocess.run(
            [NVIDIA_SMI, *_QUERY],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        # Không có binary (FileNotFoundError), không chạy được, hoặc timeout —
        # tất cả đều là "chưa đọc được", không phải lỗi của route trạng thái.
        return None
    if done.returncode != 0:
        return None
    return parse_mib(done.stdout)


class VramReader:
    """Callable mà composition root đặt vào `app.state` (route không đọc adapter).

    `unit` đi cùng callable để tầng HTTP không phải biết đơn vị của một adapter —
    nó chỉ cần nói ra đơn vị của CON SỐ nó trả. Đây cũng là lý do lớp này tồn tại
    thay vì đưa `vram_used_mib` thẳng vào route: `app/api` bị cấm import
    `app.adapters` (`tests/test_api_sources.py`).
    """

    unit = VRAM_UNIT

    def __call__(self) -> int | None:
        return vram_used_mib()
