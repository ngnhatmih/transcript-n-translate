"""Đường dẫn do BÊN NGOÀI gửi vào: cắt về tên trần, hoặc chứng minh nằm trong gốc.

Hai chiều của cùng một mối lo:

* `safe_basename` dùng khi ta GHI: ghép thẳng một chuỗi bên ngoài vào `Path` của
  máy chủ thì `../` ghi được ra ngoài thư mục dự định (R76). Dùng ở route upload
  (`filename` của client) và handler export (`stem` trong payload job). Cắt
  đường dẫn là chưa đủ: tên trần vẫn có thể không mở được thành tệp (`CON` là
  thiết bị console và chặn vô hạn, `a*b.mp4` làm `open()` ném `OSError`), nên
  hàm này còn TỪ CHỐI những tên như vậy — xem `_SAFE_CHARS`,
  `_RESERVED_DEVICE_NAMES`.
* `resolve_within` dùng khi ta ĐỌC: `media_path` lấy từ DB vẫn là dữ liệu, nên
  trước khi mở tệp phải phân giải đường dẫn rồi chứng minh nó vẫn nằm trong
  thư mục gốc. So chuỗi tiền tố là không đủ: `..` và symlink/junction đều đi
  vòng qua phép so đó, chỉ `Path.resolve()` mới lộ ra đích thật.
"""
from __future__ import annotations

import pathlib
import re

#: `.name` không bao giờ trả về `"."`, nhưng nó trả `""` cho `"."` và `".."` cho
#: `"x/.."`; cả ba đều KHÔNG phải tên tệp dùng được mà lại trỏ vào thư mục.
_INVALID = frozenset({"", ".", ".."})

#: Ký tự được phép trong tên tệp do BÊN NGOÀI gửi vào.
#:
#: Chọn bộ HẸP (chữ, số, `.`, `-`, `_`) thay vì liệt kê cái xấu: danh sách đen
#: luôn thiếu một ký tự — đúng thứ đã xảy ra (`* ? | < > : "` lọt qua phép cắt
#: đường dẫn rồi làm `open()` nổ 500). Tên tệp trên Windows còn có luật riêng
#: (thiết bị, dấu chấm cuối) mà một danh sách đen không kể hết. Bộ hẹp này đủ
#: cho tên tệp thật và từ chối mọi thứ còn lại, kể cả khoảng trắng và chữ có
#: dấu — người dùng đổi tên là xong, còn máy chủ thì không đoán.
_SAFE_CHARS = re.compile(r"\A[A-Za-z0-9._-]+\Z")

#: Thiết bị của Windows: `open()` trên tên này KHÔNG mở tệp mà mở thiết bị
#: (console, cổng nối tiếp). `open("CON", "rb")` chặn VÔ HẠN, nên chỉ một
#: request cũng đủ giữ event loop của server. Windows so khớp KHÔNG phân biệt
#: hoa/thường và bỏ qua phần mở rộng (`CON.mp4` vẫn là thiết bị), nên phải cắt
#: tại dấu chấm ĐẦU TIÊN rồi mới so.
_RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class InvalidBasename(ValueError):
    """Tên tệp do bên ngoài gửi vào không dùng được trên hệ tệp này.

    Gồm: rỗng/`.`/`..`, ký tự ngoài bộ an toàn, tên thiết bị dành riêng của
    Windows, và tên kết thúc bằng dấu chấm hoặc khoảng trắng.
    """


def _reject_unsafe_name(plain: str, original: str) -> None:
    """Ném `InvalidBasename` nếu `plain` không mở được thành tệp trên Windows."""
    if plain[-1] in " .":
        # Windows cắt khoảng trắng/dấu chấm cuối tên: `x.mp4.` mở ra `x.mp4`,
        # tức tên client gửi lên và tên trên đĩa không còn là một.
        raise InvalidBasename(
            f"tên tệp kết thúc bằng dấu chấm hoặc khoảng trắng: {original!r}")
    if plain.split(".", 1)[0].upper() in _RESERVED_DEVICE_NAMES:
        raise InvalidBasename(
            f"tên tệp là thiết bị dành riêng của Windows: {original!r}")
    if not _SAFE_CHARS.match(plain):
        raise InvalidBasename(f"tên tệp chứa ký tự không an toàn: {original!r}")


def safe_basename(name: str | None, fallback: str = "upload.bin") -> str:
    """Cắt mọi thành phần đường dẫn và TỪ CHỐI tên không dùng được trên đĩa.

    Đổi cả `\\` thành `/` TRƯỚC khi cắt: tên client gửi lên có thể mang dấu phân
    cách Windows, mà trên POSIX `pathlib.Path` coi `\\` là ký tự thường nên
    `"..\\..\\x.mp4"` sẽ lọt nguyên xi qua `.name`.

    Cắt đường dẫn là CHƯA ĐỦ: `CON` là tên trần hợp lệ với `pathlib` nhưng mở ra
    thiết bị console, còn `a*b.mp4` làm `open()` ném `OSError`. Tên như vậy là
    lỗi ĐẦU VÀO của client, nên bị từ chối ngay ở đây — trước khi bất kỳ ai
    chạm vào đĩa. Bộ ký tự cho phép và các tên bị cấm: xem `_SAFE_CHARS` và
    `_RESERVED_DEVICE_NAMES`.

    `name is None` (không có tên) dùng `fallback`. Mọi tên KHÔNG hợp lệ đều ném
    `InvalidBasename`, không âm thầm đổi thành `fallback`: nuốt lỗi ở đây thì
    tên rác của client biến thành một tệp trông hợp lệ mà không ai biết.
    """
    if name is None:
        return fallback
    plain = pathlib.PurePath(name.replace("\\", "/")).name
    if plain in _INVALID:
        raise InvalidBasename(f"tên tệp không hợp lệ: {name!r}")
    _reject_unsafe_name(plain, name)
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
