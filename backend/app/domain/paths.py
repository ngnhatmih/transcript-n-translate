"""Tên tệp do BÊN NGOÀI gửi vào -> tên TRẦN, luôn nằm trong thư mục đích.

Dùng chung cho hai chỗ ghép thẳng một chuỗi bên ngoài vào `Path` của máy chủ:
route upload (`filename` của client) và handler export (`stem` trong payload
job). Thiếu bước cắt này thì `../` ở cả hai chỗ ghi được ra ngoài thư mục dự
định (R76).
"""
from __future__ import annotations

import pathlib

#: `.name` không bao giờ trả về `"."`, nhưng nó trả `""` cho `"."` và `".."` cho
#: `"x/.."`; cả ba đều KHÔNG phải tên tệp dùng được mà lại trỏ vào thư mục.
_INVALID = frozenset({"", ".", ".."})


class InvalidBasename(ValueError):
    """Không phải tên tệp: rỗng, `.` hay `..` (trỏ vào một thư mục)."""


def safe_basename(name: str | None, fallback: str = "upload.bin") -> str:
    """Cắt mọi thành phần đường dẫn, chỉ giữ tên tệp cuối cùng.

    Đổi cả `\\` thành `/` TRƯỚC khi cắt: tên client gửi lên có thể mang dấu phân
    cách Windows, mà trên POSIX `pathlib.Path` coi `\\` là ký tự thường nên
    `"..\\..\\x.mp4"` sẽ lọt nguyên xi qua `.name`.

    `name is None` (không có tên) dùng `fallback`. Mọi tên KHÔNG hợp lệ đều ném
    `InvalidBasename`, không âm thầm đổi thành `fallback`: nuốt lỗi ở đây thì
    tên rác của client biến thành một tệp trông hợp lệ mà không ai biết.
    """
    if name is None:
        return fallback
    plain = pathlib.PurePath(name.replace("\\", "/")).name
    if plain in _INVALID:
        raise InvalidBasename(f"tên tệp không hợp lệ: {name!r}")
    return plain
