"""Đường dẫn do BÊN NGOÀI gửi vào: cắt về tên trần, hoặc chứng minh nằm trong gốc.

Hai chiều của cùng một mối lo:

* `safe_basename` dùng khi ta GHI: ghép thẳng một chuỗi bên ngoài vào `Path` của
  máy chủ thì `../` ghi được ra ngoài thư mục dự định (R76). Dùng ở route upload
  (`filename` của client) và handler export (`stem` trong payload job).
* `resolve_within` dùng khi ta ĐỌC: `media_path` lấy từ DB vẫn là dữ liệu, nên
  trước khi mở tệp phải phân giải đường dẫn rồi chứng minh nó vẫn nằm trong
  thư mục gốc. So chuỗi tiền tố là không đủ: `..` và symlink/junction đều đi
  vòng qua phép so đó, chỉ `Path.resolve()` mới lộ ra đích thật.
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


class PathOutsideRoot(ValueError):
    """Đường dẫn sau khi phân giải không nằm trong thư mục gốc cho phép."""


def resolve_within(root: str | pathlib.Path,
                   candidate: str | pathlib.Path) -> pathlib.Path:
    """Phân giải `candidate` rồi trả về nó, CHỈ khi nó nằm trong `root`.

    `resolve()` chạy TRƯỚC phép so, nên mọi thứ mà đích thật đi vòng qua chuỗi
    ký tự đều bị bắt: `media/../../etc/passwd`, một đường dẫn tuyệt đối ở nơi
    khác, và một symlink/junction nằm trong `root` trỏ ra ngoài. Đường dẫn ở ổ
    đĩa khác (Windows) cũng là "ngoài" chứ không phải lỗi.

    Phân giải hỏng (ký tự không hợp lệ cho hệ tệp, tên quá dài) cũng là
    `PathOutsideRoot`: không chứng minh được thì TỪ CHỐI, không đoán.

    `root` cũng được phân giải, để hai bên so với nhau trên cùng một dạng.
    """
    resolved_root = pathlib.Path(root).resolve()
    try:
        resolved = pathlib.Path(candidate).resolve()
    except (OSError, ValueError) as exc:
        raise PathOutsideRoot(
            f"không phân giải được đường dẫn {candidate!r}: {exc}") from exc
    if not resolved.is_relative_to(resolved_root):
        raise PathOutsideRoot(f"đường dẫn nằm ngoài {resolved_root}: {resolved}")
    return resolved
