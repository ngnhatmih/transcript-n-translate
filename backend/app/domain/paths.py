"""Đường dẫn do BÊN NGOÀI gửi vào: cắt về tên trần, hoặc chứng minh nằm trong gốc.

Hai chiều của cùng một mối lo:

* `safe_basename` dùng khi ta GHI: ghép thẳng một chuỗi bên ngoài vào `Path` của
  máy chủ thì `../` ghi được ra ngoài thư mục dự định (R76). Dùng ở route upload
  (`filename` của client) và handler export (`stem` trong payload job). Cắt
  đường dẫn là chưa đủ: tên trần vẫn có thể không mở được thành tệp (`CON` là
  thiết bị console và chặn vô hạn, `a*b.mp4` làm `open()` ném `OSError`), nên
  hàm này còn TỪ CHỐI những tên như vậy — xem `_SAFE_CATEGORIES`,
  `_ALLOWED_PUNCT`, `_RESERVED_DEVICE_NAMES`.
* `resolve_within` dùng khi ta ĐỌC: `media_path` lấy từ DB vẫn là dữ liệu, nên
  trước khi mở tệp phải phân giải đường dẫn rồi chứng minh nó vẫn nằm trong
  thư mục gốc. So chuỗi tiền tố là không đủ: `..` và symlink/junction đều đi
  vòng qua phép so đó, chỉ `Path.resolve()` mới lộ ra đích thật.
"""
from __future__ import annotations

import pathlib
import unicodedata

#: `.name` không bao giờ trả về `"."`, nhưng nó trả `""` cho `"."` và `".."` cho
#: `"x/.."`; cả ba đều KHÔNG phải tên tệp dùng được mà lại trỏ vào thư mục.
_INVALID = frozenset({"", ".", ".."})

#: Ký tự được phép trong tên tệp do BÊN NGOÀI gửi vào.
#:
#: Chọn bộ HẸP theo LOẠI Unicode thay vì liệt kê cái xấu: danh sách đen luôn thiếu
#: một ký tự — đúng thứ đã xảy ra (`* ? | < > : "` lọt qua phép cắt đường dẫn rồi
#: làm `open()` nổ 500). Tên tệp trên Windows còn có luật riêng (thiết bị, dấu
#: chấm cuối) mà một danh sách đen không kể hết.
#:
#: A1 (đo được): bộ cũ là `\A[A-Za-z0-9._-]+\Z`, tức CHỈ ASCII — nên
#: `POST /api/sources/upload` trả **422** cho `Zh-请您欣赏.ogg` và `ảnh.mp4`, chặn
#: đúng người dùng tiếng Trung/tiếng Việt ngay ở cửa vào. Bộ mới cho phép mọi
#: LOẠI chữ/số (kể cả chữ Hán và chữ có dấu) và dấu tổ hợp, mà vẫn từ chối đúng
#: những thứ không mở được thành tệp: ký tự điều khiển, `< > : " | ? * / \`,
#: khoảng trắng, ngoặc, và mọi dấu câu khác.
#:
#: Vì sao an toàn hơn cả bộ ASCII cũ: những ký tự đi vòng qua `pathlib` trên hệ
#: tệp này (`/`, `\`) và những ký tự Windows cấm đều thuộc nhóm dấu câu, nên bị
#: từ chối; các bản "trông giống dấu phân cách" của Unicode (`／` U+FF0F, `：`
#: U+FF1A) cũng là dấu câu nên cũng bị từ chối.
_SAFE_CATEGORIES = frozenset({
    "Lu", "Ll", "Lt", "Lm", "Lo",     # chữ (gồm chữ Hán, chữ có dấu)
    "Nd", "Nl", "No",                 # số
    "Mn", "Mc",                       # dấu tổ hợp: dạng NFD của tiếng Việt
})

#: Dấu câu được phép: đúng bộ `._-` mà tên tệp thật cần, không thêm gì.
_ALLOWED_PUNCT = frozenset("._-")


#: Trần độ dài của MỘT thành phần đường dẫn trên hệ tệp phổ biến (NTFS: 255 ký
#: tự). Không phải chuyện thẩm mỹ: một tên 302 ký tự toàn ký tự an toàn đi lọt
#: qua cả ba phép kiểm kia rồi làm `open()` ném `OSError`, tức route upload trả
#: **500** cho một lỗi ĐẦU VÀO — đúng lớp lỗi mà `a*b.mp4` và `CON` đã trả giá
#: (C-1/API-01). `len()` là phép kiểm thứ tư, cùng lớp `InvalidBasename` để route
#: map thành 422 như ba phép kia.
#:
#: Đây là trần của MỘT THÀNH PHẦN, không phải của cả đường dẫn: độ dài toàn
#: đường dẫn còn phụ thuộc `LongPathsEnabled` của máy đích (máy này BẬT, nên
#: `MAX_PATH` 260 không phải thứ chặn tên 302 ký tự ở đây), mà `LongPathsEnabled`
#: KHÔNG bypass được giới hạn 255 của một thành phần. Vì vậy độ dài toàn đường
#: dẫn CỐ Ý không được kiểm ở đây — đoán nó là đoán cấu hình của máy khác.
_MAX_NAME_LENGTH = 255

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
    Windows, tên kết thúc bằng dấu chấm hoặc khoảng trắng, và tên dài quá trần
    của một thành phần đường dẫn (`_MAX_NAME_LENGTH`).
    """


def _is_safe_name_char(ch: str) -> bool:
    """`True` nếu `ch` mở được thành tên tệp trên hệ tệp này."""
    return ch in _ALLOWED_PUNCT or unicodedata.category(ch) in _SAFE_CATEGORIES


def _reject_unsafe_name(plain: str, original: str) -> None:
    """Ném `InvalidBasename` nếu `plain` không mở được thành tệp trên Windows."""
    if len(plain) > _MAX_NAME_LENGTH:
        # Dài quá trần thì `open()` ném `OSError` — một lỗi ĐẦU VÀO của client
        # đội lốt lỗi máy chủ (500). `_SAFE_CHARS` không bắt được ca này: 302
        # chữ `a` khớp bộ ký tự an toàn hoàn hảo.
        raise InvalidBasename(
            f"tên tệp dài quá {_MAX_NAME_LENGTH} ký tự "
            f"({len(plain)} ký tự): {original!r}")
    if plain[-1] in " .":
        # Windows cắt khoảng trắng/dấu chấm cuối tên: `x.mp4.` mở ra `x.mp4`,
        # tức tên client gửi lên và tên trên đĩa không còn là một.
        raise InvalidBasename(
            f"tên tệp kết thúc bằng dấu chấm hoặc khoảng trắng: {original!r}")
    if plain.split(".", 1)[0].upper() in _RESERVED_DEVICE_NAMES:
        raise InvalidBasename(
            f"tên tệp là thiết bị dành riêng của Windows: {original!r}")
    bad = sorted({ch for ch in plain if not _is_safe_name_char(ch)})
    if bad:
        # Nêu ĐÍCH DANH ký tự bị từ chối: `'a*b.mp4'` và `'中文 音频.wav'` hỏng
        # vì hai lý do khác hẳn nhau, và người dùng sửa được cả hai chỉ khi biết
        # ký tự nào là thứ bị chặn.
        raise InvalidBasename(
            f"tên tệp chứa ký tự không an toàn: {original!r} "
            f"(bị từ chối: {' '.join(repr(c) for c in bad)})")



def safe_basename(name: str | None, fallback: str = "upload.bin") -> str:
    """Cắt mọi thành phần đường dẫn và TỪ CHỐI tên không dùng được trên đĩa.

    Đổi cả `\\` thành `/` TRƯỚC khi cắt: tên client gửi lên có thể mang dấu phân
    cách Windows, mà trên POSIX `pathlib.Path` coi `\\` là ký tự thường nên
    `"..\\..\\x.mp4"` sẽ lọt nguyên xi qua `.name`.

    Cắt đường dẫn là CHƯA ĐỦ: `CON` là tên trần hợp lệ với `pathlib` nhưng mở ra
    thiết bị console, còn `a*b.mp4` làm `open()` ném `OSError`. Tên như vậy là
    lỗi ĐẦU VÀO của client, nên bị từ chối ngay ở đây — trước khi bất kỳ ai
    chạm vào đĩa. Cùng lý do với tên DÀI quá `_MAX_NAME_LENGTH`: nó cũng
    chỉ nổ ở `open()`, tức 500 thay vì 422. Bộ ký tự cho phép, các tên bị
    cấm và trần độ dài: xem `_SAFE_CATEGORIES`, `_ALLOWED_PUNCT`,
    `_RESERVED_DEVICE_NAMES`, `_MAX_NAME_LENGTH`.

    `name is None` (không có tên) dùng `fallback`. Mọi tên KHÔNG hợp lệ đều ném
    `InvalidBasename`, không âm thầm đổi thành `fallback`: nuốt lỗi ở đây thì
    tên rác của client biến thành một tệp trông hợp lệ mà không ai biết.

    DOC-09 (N6): `None` và falsy KHÁC nhau, và đó là CỐ Ý — chỉ `None` mới dùng
    `fallback`, còn `""`, `"."`, `".."` đều ném. Vì vậy người gọi nào nhận giá
    trị tuỳ chọn từ BÊN NGOÀI phải tự quyết trước khi gọi:
    `ExportHandler` (`app/pipeline/export.py`) đổi `stem` falsy thành `None` để
    giữ đúng ngữ nghĩa `payload.get("stem") or f"transcript-{id}"` cũ, nên
    `stem=""` lùi về tên mặc định; route upload (`app/api/routes_sources.py`)
    đưa thẳng `filename` vào, nên `""` của client là **422**. Làm hai đường
    giống nhau là ĐỔI HỢP ĐỒNG, không phải sửa lỗi — đọc docstring này trước.
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
