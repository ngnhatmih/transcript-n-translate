"""Vá tên riêng nghe nhầm trong transcript NGUỒN bằng caption OCR cùng cửa sổ thời gian.

Đây là bản **CHẠY THẬT** của ý tưởng mà `scripts/mine_ocr_glossary.py` đã chứng
minh trên một clip đóng băng: ở pipeline time, với một video MỚI, so caption OCR
đốt trong hình với transcript ASR **trong cùng một cửa sổ thời gian** rồi sửa chỗ
nghe gần đồng âm của tên riêng/thuật ngữ trong chữ NGUỒN, TRƯỚC khi dịch. Sửa
nguồn chứ không sửa bản dịch: để translator dịch âm Hán-Việt của chữ ĐÚNG.

Module này KHÔNG đọc bất kỳ artefact nào của miner
    `ocr-glossary-candidates.json` và `ocr-glossary-manual-approvals.json` là đầu
    ra của một lần đào trên MỘT clip; chúng là *test harness* để chứng minh bộ canh
    tổng quát hoá, không phải dữ liệu của đường chạy thật. Đầu vào duy nhất ở đây
    là `(segments, ocr_rows)` của chính video đang xử lý — nên video mới, cặp mới
    chưa ai đào, vẫn vá được. (Bài `test_a_pair_that_no_miner_ever_saw_is_patched`
    khoá bất biến này, kể cả ở mức mã nguồn.)

Vì sao key theo `i` của DÒNG OCR, không theo vị trí mảng
    Đo trên reference v4: vị trí 26 của `caption_observations` mang `i` = 29, vị trí
    57 mang `i` = 62 (ba dòng `i` = 1, 2, 7 bị loại nên lệch từ đầu). Vị trí chỉ là
    thứ tự lưu; `i` mới là danh tính của dòng. Bản vá ghi lại `ocr_row_i` để người
    đọc đối chiếu được về đúng dòng OCR đã sinh ra nó.

Vì sao chỉ đọc `ocr`, không `asr`/`source_ocr`
    Ở runtime, `asr` của một dòng OCR là bản decode của clip THAM CHIẾU, không phải
    transcript đang xử lý; `source_ocr` lại khác `ocr` đúng bốn dòng (`i` = 26, 57,
    64, 82) vì bốn dòng đó được sửa từ frame. Dùng chúng là trộn dữ liệu đào vào
    đường chạy thật. Thứ đốt trên màn hình của video này là `ocr`.

Vì sao phải lọc watermark trước khi canh
    9 trong 21 dòng `excluded_observations` của reference có `ocr` là watermark
    kênh (`想想工作室`, `想法工作室`, `bilibili`). Ở runtime watermark nằm trong
    CÙNG cửa sổ thời gian với lời nói gần như suốt clip, nên ghép nó với ASR sẽ sinh
    ra bản vá dạng `Chance-Elysée -> 想想工作室`: đổi lời nói thành chữ trên màn
    hình. Cùng lý do với dòng rỗng và dòng chỉ có dấu chấm (`...`, `…`).

Vì sao phải t2s (OpenCC) TRƯỚC khi canh
    Dòng `i` = 87 của reference là chữ PHỒN THỂ (`在整個街區藏了很多個‘福’`) trong
    khi ASR là giản thể. Không t2s thì `个`/`個`, `区`/`區` là hai chữ khác nhau và
    bản vá "sửa" hệ chữ nhân danh nghe nhầm. t2s cũng là phép đổi để chuỗi được
    vá nằm đúng hệ chữ mà transcript dùng.

Vì sao cần cửa sổ neo (anchor)
    Một `replace` của `SequenceMatcher` thường chỉ là một chữ (`燕`/`烟`,
    `阴`/`烟`): quá ít ngữ cảnh để biết đó là tên bị nghe nhầm hay chỉ là khác
    biệt từ vựng. Cửa sổ neo mở mỗi bên tối đa 2 ký tự cho tới khi mỗi bên đủ 2 âm
    tiết, nên cặp `来阴台山`/`来烟台山` được so ở mức CỤM (`阴台山`/`烟台山`) —
    đúng cặp đáng vá nhất và cũng là cặp dễ mất nhất nếu so một âm tiết.

Vì sao có HAI phép so pinyin, cố ý khác độ đo
    * `core_not_homophone`: pinyin của CHÍNH cặp hẹp, NỐI thành một chuỗi rồi mới
      so bằng `SequenceMatcher.ratio()`. Nối chuỗi cho `阴`(yin)/`烟`(yan) = 0,667
      và `瓶值`/`平尺` = 0,5; so theo phần tử rời thì chỉ còn 0 hoặc 1, mất hết
      thông tin "gần âm".
    * `window_not_homophone`: pinyin của cửa sổ neo, so như **danh sách âm tiết**.
      Đây là phép so khắt khe hơn ở mức âm tiết trọn vẹn, và nó bắt đúng loại mà
      core bỏ lọt: đo trên bản chạy thật, `教过`/`交给` có core = 0,714 (qua) nhưng
      cửa sổ = 0,5 (trượt) — một cặp động từ thay nhau, không phải tên nghe nhầm.
      Hai phép đo cố ý khác nhau; gộp chúng làm một là mất một trong hai cái bắt.

Vì sao ngưỡng là `>` chứ không `>=` (cùng lý do đã đo ở miner)
    `瓶值`/`平尺` (`ping zhi`/`ping chi`) khớp ĐÚNG 0,5. `>=` cho cặp số-liệu-bị-
    chuẩn-hoá-lại lọt qua. Đo trên bản chạy thật: `教过`/`交给` (cửa sổ 0,5),
    `经`/`金` (cửa sổ 0,5), `可以啊`/`可以吗` (cửa sổ 0,5) đều bị `>` loại; đó là
    các cặp khác nghĩa, không phải nghe nhầm.

Vì sao guard số/ký hiệu có HAI phạm vi, không phải một
    Đo trên đúng dòng `i` = 13 của reference: `一瓶值2000` vs `一平尺2,000`.
    `SequenceMatcher` cắt thành `replace` `瓶值 -> 平尺` **cộng một `insert` dấu
    phẩy** — chữ số không hề nằm trong opcode `replace`. Nếu chỉ soi cặp hẹp thì
    cặp trông sạch (`ping zhi`/`ping chi`) và bản vá "sửa" một con số thành chữ.
    Vì vậy CHỮ SỐ được soi trên vùng ±2 ký tự quanh cặp hẹp (đúng vùng cửa sổ neo
    được phép nhìn tới): chạm vào vùng số liệu là không vá.

    KÝ HIỆU/DẤU CÂU thì ngược lại, chỉ soi TRONG cặp hẹp: dấu câu trong core là
    bằng chứng cặp này không phải nghe nhầm tên (`成细 -> (+宽)x系`, `荣 -> “榕`
    vẫn bị chặn), còn dấu câu NGOÀI core chỉ là ngữ cảnh của câu. Tiêu đề Hán luôn
    có `《》`, nên soi dấu câu ngữ cảnh là false negative HỆ THỐNG: đo trên smoke,
    `指缘 -> 纸鸢` (dòng `i` = 12 của reference, core = 1,0, cửa sổ = 1,0) từng bị
    chặn chỉ vì `《` nằm trong ±2 — đúng loại tiêu đề tác phẩm mà bộ vá sinh ra để
    sửa. Sau khi tách hai phạm vi, dòng 14 của decode smoke vá được cả `二 -> 儿`
    và `指缘 -> 纸鸢` (`这是小二放指缘图` -> `这是小儿放纸鸢图`), còn `瓶是 -> 平尺`
    vẫn nằm trong `rejected` với `digits_or_symbols` (core = 0,857, cửa sổ = 0,5);
    số dòng `digits_or_symbols` trên smoke giảm 15 -> 11 và smoke có thêm đúng một
    câu vá (6 -> 7 câu, 8 bản vá).

Vì sao cặp 1 ký tự bị ghi `single_character_not_patchable` chứ không áp
    Luật này chép TÊN từ miner, nhưng lý do ở đây khác: bản vá áp theo OFFSET nên
    không đổi mọi chỗ của chữ đó trong transcript như miner lo. Cái còn lại là ngữ
    cảnh: nếu cửa sổ neo vẫn chỉ có 1 ký tự mỗi bên (câu quá ngắn, `燕`/`烟`) thì
    không có bằng chứng nào cho thấy đây là tên bị nghe nhầm, và hai công cụ phải
    cùng tên luật để so được với nhau.

Vì sao chống nhập nhằng thay vì chọn heuristic
    Hai dòng OCR chồng nhau (caption hai dòng, hai trạng thái caption liền nhau)
    có thể cùng đề xuất hai chữ khác nhau cho CÙNG một khoảng. Chọn một theo
    heuristic là đặt cược 50/50 rồi ghi vào transcript như thể chắc chắn. Ở đây
    KHÔNG áp gì cả và ghi lại `ambiguous` kèm mọi đề xuất để người đọc quyết định.

Vì sao `pypinyin` / `opencc` chỉ nằm ở biên CLI
    Cả hai là phụ thuộc ĐÁNH GIÁ, không thuộc app (`requirements.txt` không có dòng
    nào cho chúng). Hàm chính nhận `pinyin_fn` và `t2s_fn` như tham số để test bơm
    bản giả (không bài nào gọi `pypinyin`), còn CLI mới là chỗ nạp bản thật. Hai
    hàm thật dưới đây cố ý CHÉP lại từ miner thay vì import: module này là đường
    chạy thật, không được phụ thuộc một script đào một-lần.
"""
from __future__ import annotations

import copy
import difflib
import re
import unicodedata
from dataclasses import dataclass, field

#: Watermark kênh bị đốt thẳng vào hình. So trên chuỗi đã chuẩn hoá và đã casefold:
#: OCR có thể trả `Bilibili`/`BILIBILI`, so nguyên văn sẽ hụt đúng những dòng đó.
WATERMARK_TERMS = ("想想工作室", "想法工作室", "bilibili")

#: NFKC biến `…` (U+2026) thành `...`, nên một tập ký tự là đủ che `...`, `.`, `…`.
PLACEHOLDER_CHARS = frozenset(".")

#: Trần độ dài mỗi vế của cửa sổ neo. Tên riêng nghe nhầm trong dữ liệu này dài
#: 1-3 chữ; vế dài hơn 6 chữ gần như luôn là ranh giới cắt câu của
#: `SequenceMatcher`, không phải một lần nghe nhầm.
MAX_SIDE_CHARS = 6

#: Mỗi bên được mở thêm tối đa 2 ký tự khi dựng cửa sổ neo.
ANCHOR_MAX_EXTENSION = 2

#: Ngưỡng tỉ lệ khớp âm tiết, dùng cho CẢ HAI phép so (core và cửa sổ neo). Phải
#: là `>` chứ không `>=`: đo được các cặp khác nghĩa khớp ĐÚNG 0,5 (`教过`/`交给`,
#: `经`/`金`, `可以啊`/`可以吗`, `瓶值`/`平尺`) — xem docstring đầu tệp.
RATIO_THRESHOLD = 0.5

#: Vùng ±2 ký tự quanh cặp hẹp mà luật CHỮ SỐ soi tới. Chỉ chữ số dùng vùng này
#: (ký hiệu/dấu câu chỉ soi trong cặp hẹp — dấu câu ngoài core là ngữ cảnh, xem
#: `has_forbidden_symbol`): dòng `i` = 13 của reference (`一瓶值2000` /
#: `一平尺2,000`) sinh ra `replace` `瓶值 -> 平尺` cộng một `insert` dấu phẩy, nên
#: chữ số nằm NGOÀI opcode `replace`.
GUARD_CHARS = 2

#: Hư từ không thể là chữ MỞ ĐẦU của một từ ghép bị nghe nhầm, nên khi ký tự bên
#: trái là một trong số này thì cửa sổ neo phải mở sang PHẢI. Danh sách chép từ
#: miner, nơi nó được đọc từ dữ liệu: `来/去/有/找` đứng ngay trước cụm danh từ
#: (`来阴台山`), còn `拉/螺/榕/线/合` là hình vị NỘI DUNG nên mở sang trái
#: (`拉彩`, `螺垫`). Đo trên bản chạy thật: `来阴台山` nhờ luật này mở được sang
#: phải thành `阴台山`/`烟台山` (3 âm tiết) thay vì `来阴`/`来烟` — đúng cặp
#: `i` = 90 và là một trong tám bản vá (bảy câu) của lần smoke.
STOP_CHARS = frozenset(
    "的了着过地得是也都在就还和跟把被我你他她它这那些个来去有找说要给让做看想到吗呢吧啊嘛呀没"
)

#: Regex cho lớp số ASCII và toàn khổ. Lớp `N` của `unicodedata` đã bao trùm nó,
#: nhưng giữ riêng đây làm bằng chứng cho quy tắc đã chốt (`[0-9０-９]`) và để lần
#: đọc sau không ai "dọn" mất lớp bảo vệ thật.
_FORBIDDEN_CHAR_RE = re.compile(r"[0-9０-９]")

#: Khoá capability trong `registry.json` quyết định engine nào được phép vá tên.
#: Xem `name_patch_allowed` cho số đo và lý do.
NAME_PATCH_CAPABILITY = "name_patch"


class PinyinUnavailable(RuntimeError):
    """`pypinyin` chưa có trong venv. Lỗi riêng để CLI in chỉ dẫn thay vì traceback."""


class T2sUnavailable(RuntimeError):
    """`opencc` chưa có trong venv. Lỗi riêng để CLI in chỉ dẫn thay vì traceback."""


@dataclass
class PatchResult:
    """Kết quả một lượt vá. `segments` là bản SAO đã vá, không sửa đầu vào."""

    segments: list[dict]
    changes: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "segments": self.segments,
            "changes": self.changes,
            "rejected": self.rejected,
            "stats": self.stats,
        }


def is_watermark(normalized: str) -> bool:
    lowered = normalized.casefold()
    return any(term in lowered for term in WATERMARK_TERMS)


def is_placeholder(normalized: str) -> bool:
    """Chuỗi rỗng hoặc chỉ gồm dấu chấm: `...`, `.`, `…` (đã thành `...` qua NFKC)."""
    return all(ch in PLACEHOLDER_CHARS for ch in normalized)


def has_forbidden_digit(text: str) -> bool:
    """Có CHỮ SỐ không (ASCII `[0-9]`, toàn khổ, hoặc lớp Unicode `N`)?

    Nửa "số liệu" của quy tắc, và nó phải chạy trên vùng ±2 ký tự quanh cặp hẹp:
    dòng `i` = 13 của reference (`一瓶值2000` / `一平尺2,000`) sinh ra `replace`
    `瓶值 -> 平尺` **cộng một `insert` dấu phẩy**, nên chữ số nằm NGOÀI opcode
    `replace`. Chỉ soi cặp hẹp thì không có gì nói "đây là số liệu bị định dạng
    lại", và bản vá "sửa" một con số thành chữ. Lọc theo LỚP Unicode chứ không
    theo danh sách ký tự, vì dữ liệu còn chữ số toàn khổ chưa gặp.
    """
    if _FORBIDDEN_CHAR_RE.search(text):
        return True
    return any(unicodedata.category(ch)[0] == "N" for ch in text)


def has_forbidden_symbol(text: str) -> bool:
    """Có KÝ HIỆU / DẤU CÂU không (lớp Unicode `S` và `P`)?

    Nửa "ký hiệu" cố ý chỉ chạy trên **CHÍNH cặp hẹp**, không chạy trên vùng ±2:
    dấu câu nằm TRONG core là bằng chứng cặp này không phải nghe nhầm tên
    (`成细 -> (+宽)x系` có `+`/ngoặc trong core; `荣 -> “榕` có dấu nháy trong
    core — cả hai vẫn bị chặn), còn dấu câu NGOÀI core chỉ là ngữ cảnh của câu.
    Tiêu đề Hán luôn có `《》`, nên soi dấu câu ngữ cảnh là false negative hệ
    thống: đo trên smoke, `指缘 -> 纸鸢` (core = 1,0, cửa sổ = 1,0, dòng `i` = 12
    của reference) từng bị chặn chỉ vì `《` nằm trong ±2 — đúng loại tiêu đề tác
    phẩm mà bộ vá sinh ra để sửa.
    """
    return any(unicodedata.category(ch)[0] in ("S", "P") for ch in text)


def pypinyin_syllables(text: str) -> list[str]:
    """Âm tiết không dấu của `text` bằng `pypinyin` thật (dùng ở CLI).

    `pypinyin` được nạp BÊN TRONG hàm để `import` module này không kéo theo một
    phụ thuộc đánh giá; test bơm bản giả nên không bài nào chạm tới đây.
    """
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError as exc:  # pragma: no cover - nhánh này do CLI kiểm
        raise PinyinUnavailable(
            "thiếu gói `pypinyin` (chỉ dùng cho bước ĐÁNH GIÁ, không thuộc app)"
        ) from exc
    # `errors` mặc định giữ nguyên ký tự không phải chữ Hán (Latinh, chữ số),
    # đúng thứ ta cần: hai vế được so bằng cùng một phép biến đổi.
    return [syllable for syllable in lazy_pinyin(text, style=Style.NORMAL) if syllable.strip()]


_OPENCC = None


def opencc_t2s(text: str) -> str:
    """Phồn -> giản bằng OpenCC thật (dùng ở CLI).

    Converter được giữ lại giữa các lần gọi: `OpenCC("t2s")` nạp từ điển, tạo mới
    cho từng dòng là trả giá đó cho một phép biến đổi thuần tuý.
    """
    global _OPENCC
    try:
        from opencc import OpenCC
    except ImportError as exc:  # pragma: no cover - nhánh này do CLI kiểm
        raise T2sUnavailable(
            "thiếu gói `opencc` (chỉ dùng cho bước ĐÁNH GIÁ, không thuộc app)"
        ) from exc
    if _OPENCC is None:
        _OPENCC = OpenCC("t2s")
    return _OPENCC.convert(text)


_AUTO = object()


def _normalize_with_map(text: str, t2s_fn) -> tuple[str, list[int]]:
    """NFKC, bỏ TOÀN BỘ khoảng trắng, rồi t2s — giữ ÁNH XẠ chỉ số về chuỗi GỐC.

    Khoảng trắng không mang thông tin âm ở đây nhưng lại xuất hiện thật trong
    caption OCR (`你 也 画 的 鱼 啊`), nên giữ nó sẽ làm `SequenceMatcher` sinh ra
    một loạt `replace`/`insert` rỗng nghĩa và phá luôn phép so pinyin theo âm tiết.

    Chuỗi chuẩn hoá cũng có thể bị t2s đổi chữ, nên chỉ số trong nó không còn trỏ
    đúng vào `text`. Bản vá phải cắt trên chuỗi GỐC để những ký tự không liên quan
    (và mọi khoá khác của segment) không bị đụng tới; vì vậy mỗi ký tự chuẩn hoá
    mang theo chỉ số gốc của nó.

    Hai nhánh dự phòng cho trường hợp NFKC/t2s ĐỔI ĐỘ DÀI (một ký tự thành nhiều
    ký tự): khi đó chuẩn hoá từng ký tự để ánh xạ vẫn đúng. Từ điển t2s chủ yếu
    là 1:1 nên nhánh này gần như không chạy trên dữ liệu thật; nó tồn tại để phép
    cắt không bao giờ lệch chỉ số một cách im lặng.
    """
    nfkc = unicodedata.normalize("NFKC", text)
    if len(nfkc) == len(text):
        base, base_map = nfkc, list(range(len(text)))
    else:  # pragma: no cover - NFKC đổi độ dài là ca hiếm
        base_chars, base_map = [], []
        for position, char in enumerate(text):
            for piece in unicodedata.normalize("NFKC", char):
                base_chars.append(piece)
                base_map.append(position)
        base = "".join(base_chars)

    stripped_chars, stripped_map = [], []
    for char, position in zip(base, base_map):
        if char.isspace():
            continue
        stripped_chars.append(char)
        stripped_map.append(position)
    stripped = "".join(stripped_chars)

    if t2s_fn is None:
        return stripped, stripped_map

    converted = t2s_fn(stripped)
    if len(converted) == len(stripped):
        return converted, stripped_map

    # pragma: no cover - ca hiếm: t2s đổi độ dài (luật theo cụm từ)
    out_chars, out_map = [], []
    for char, position in zip(stripped, stripped_map):
        for piece in t2s_fn(char):
            out_chars.append(piece)
            out_map.append(position)
    return "".join(out_chars), out_map


def _joined_pinyin_ratio(wrong: str, correct: str, pinyin_fn) -> float:
    """Tỉ lệ khớp pinyin của CẶP HẸP, NỐI âm tiết thành chuỗi rồi mới so.

    Nối chuỗi rồi mới so là để `阴`(yin)/`烟`(yan) ra 0,667 — so theo phần tử rời
    thì chỉ còn 0 hoặc 1 và mất hết thông tin "gần âm". Đo trên dữ liệu thật:
    `夜`/`业` 1,0 · `长`/`展` 0,889 · `阴`/`烟` 0,667 · `瓶值`/`平尺` 0,5 ·
    `教过`/`交给` 0,714 (qua core) nhưng 0,5 khi so theo danh sách âm tiết.
    """
    joined_wrong = "".join(pinyin_fn(wrong))
    joined_correct = "".join(pinyin_fn(correct))
    return difflib.SequenceMatcher(None, joined_wrong, joined_correct, autojunk=False).ratio()


def _syllable_list_ratio(wrong: str, correct: str, pinyin_fn) -> float:
    """Tỉ lệ khớp theo DANH SÁCH âm tiết của CỬA SỔ NEO.

    Cố ý khác `_joined_pinyin_ratio` ở độ đo, không phải bản sao của nó: nối chuỗi
    thưởng cho các chữ cái trùng NHAU GIỮA hai âm tiết, còn so danh sách chỉ tính
    âm tiết khớp TRỌN VẸN. Vì vậy `阴`/`烟` qua core nhưng một cửa sổ chỉ có đúng
    cặp đó sẽ trượt cửa sổ — đúng ý: một âm tiết lệch nguyên âm chưa đủ bằng chứng,
    vài âm tiết cùng khớp thì đủ.
    """
    return difflib.SequenceMatcher(
        None, pinyin_fn(wrong), pinyin_fn(correct), autojunk=False
    ).ratio()


def _anchor_window(
    seg_norm: str,
    row_norm: str,
    i1: int,
    i2: int,
    j1: int,
    j2: int,
    pinyin_fn,
) -> dict:
    """Cửa sổ neo quanh một `replace`; cặp hẹp nếu không mở thêm được gì.

    Hai bước, thứ tự có nghĩa (chép từ miner vì đã đo ở đó):

    1. Mở sang TRÁI từng ký tự (tối đa 2), dừng ngay khi mỗi vế đã >= 2 âm tiết,
       và dừng hẳn nếu ký tự bên trái là hư từ — hư từ không thể là phần đầu của
       từ bị nghe nhầm, nên mở qua nó chỉ tạo cửa sổ rác (`来阴` thay vì
       `阴台山`).
    2. Không xong thì mở sang PHẢI, lấy TỐI ĐA 2 ký tự (không dừng sớm ở mốc 2 âm
       tiết): địa danh ba chữ như `烟台山` chỉ lộ ra khi lấy đủ hai ký tự bên phải.
    """
    if len(pinyin_fn(seg_norm[i1:i2])) >= 2 and len(pinyin_fn(row_norm[j1:j2])) >= 2:
        return {"wrong": seg_norm[i1:i2], "correct": row_norm[j1:j2], "left": 0, "right": 0}

    left = 0
    while left < ANCHOR_MAX_EXTENSION and i1 - left > 0 and j1 - left > 0:
        if (
            seg_norm[i1 - left - 1] in STOP_CHARS
            or row_norm[j1 - left - 1] in STOP_CHARS
        ):
            break
        left += 1
        if len(pinyin_fn(seg_norm[i1 - left : i2])) >= 2 and len(
            pinyin_fn(row_norm[j1 - left : j2])
        ) >= 2:
            return {
                "wrong": seg_norm[i1 - left : i2],
                "correct": row_norm[j1 - left : j2],
                "left": left,
                "right": 0,
            }

    right = min(ANCHOR_MAX_EXTENSION, len(seg_norm) - i2, len(row_norm) - j2)
    while right > 0:
        if len(pinyin_fn(seg_norm[i1 - left : i2 + right])) >= 2 and len(
            pinyin_fn(row_norm[j1 - left : j2 + right])
        ) >= 2:
            return {
                "wrong": seg_norm[i1 - left : i2 + right],
                "correct": row_norm[j1 - left : j2 + right],
                "left": left,
                "right": right,
            }
        right -= 1
    return {"wrong": seg_norm[i1:i2], "correct": row_norm[j1:j2], "left": 0, "right": 0}


def ocr_rows_from_document(document) -> list[dict]:
    """Lấy danh sách dòng OCR từ tệp: reference (`metadata.caption_observations`)
    hoặc một tệp observations thô đặt thẳng danh sách ở top level.
    """
    if isinstance(document, list):
        return list(document)
    if not isinstance(document, dict):
        raise ValueError("tệp OCR phải là một object hoặc một danh sách dòng")
    metadata = document.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("caption_observations") is not None:
        return list(metadata["caption_observations"])
    for key in ("caption_observations", "observations"):
        if document.get(key) is not None:
            return list(document[key])
    raise ValueError(
        "không thấy dòng OCR: cần `metadata.caption_observations` hoặc danh sách ở top level"
    )


def asr_segments_from_document(document: dict) -> tuple[str, list[dict]]:
    """`(khoá, danh sách segment)` của transcript — giữ đúng khoá để ghi lại.

    Pipeline JSON dùng `segments`, kết quả pipeline dùng `source_segments`. Ghi ra
    phải giữ đúng khoá của đầu vào, nếu không bước sau đọc sai trường.
    """
    if not isinstance(document, dict):
        raise ValueError("tệp transcript phải là một object JSON")
    for key in ("segments", "source_segments"):
        value = document.get(key)
        if isinstance(value, list):
            return key, value
    raise ValueError("transcript không có `segments` hay `source_segments`")


def _prepare_rows(rows: list[dict], t2s_fn) -> list[dict]:
    """Các dòng OCR dùng được, đã chuẩn hoá, giữ nguyên `i` của chính dòng đó."""
    prepared: list[dict] = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("mỗi dòng OCR phải là một object")
        if "i" not in raw:
            raise ValueError(f"dòng OCR thiếu khoá `i`: {sorted(raw)}")
        ocr_raw = raw.get("ocr") or ""
        ocr_norm, _ = _normalize_with_map(str(ocr_raw), t2s_fn)
        if not ocr_norm or is_placeholder(ocr_norm) or is_watermark(ocr_norm):
            continue
        prepared.append(
            {
                "i": int(raw["i"]),
                "start": float(raw["start"]),
                "end": float(raw["end"]),
                "raw": str(ocr_raw),
                "norm": ocr_norm,
            }
        )
    return prepared


def _overlap_seconds(start: float, end: float, row: dict) -> float:
    """Giao của dòng OCR với CHÍNH ĐOẠN ASR (không phải với cửa sổ đã nới).

    Cửa sổ chỉ dùng để CHỌN ứng viên; con số ghi lại (`overlap_s`) phải nói mức
    trùng thật, nếu không một dòng chỉ chạm mép cửa sổ sẽ trông như đang nói cùng
    lúc. Kẹp về 0 vì dòng đó vẫn là ứng viên hợp lệ.
    """
    return round(max(0.0, min(end, row["end"]) - max(start, row["start"])), 3)


def _evaluate(
    seg_norm: str,
    row_norm: str,
    i1: int,
    i2: int,
    j1: int,
    j2: int,
    pinyin_fn,
    threshold: float,
) -> dict:
    """Một opcode `replace` -> đề xuất kèm lý do (hoặc `reason = None`).

    Trả về TÊN quy tắc chứ không trả `bool`: câu hỏi thật của người đọc log là
    "vì sao chỗ tôi biết là sai lại không được vá", và một `False` không trả lời
    được. Tên quy tắc giữ đúng như miner để hai công cụ so được với nhau.
    """
    narrow_wrong = seg_norm[i1:i2]
    narrow_correct = row_norm[j1:j2]
    window = _anchor_window(seg_norm, row_norm, i1, i2, j1, j2, pinyin_fn)
    window_wrong, window_correct = window["wrong"], window["correct"]
    guard_wrong = seg_norm[max(0, i1 - GUARD_CHARS) : i2 + GUARD_CHARS]
    guard_correct = row_norm[max(0, j1 - GUARD_CHARS) : j2 + GUARD_CHARS]

    core_ratio = _joined_pinyin_ratio(narrow_wrong, narrow_correct, pinyin_fn)
    window_ratio = _syllable_list_ratio(window_wrong, window_correct, pinyin_fn)

    if not (1 <= len(window_wrong) <= MAX_SIDE_CHARS and 1 <= len(window_correct) <= MAX_SIDE_CHARS):
        reason = "length"
    elif len(window_wrong) < 2 or len(window_correct) < 2:
        # Không có ngữ cảnh để chứng minh đây là tên bị nghe nhầm (xem docstring).
        reason = "single_character_not_patchable"
    elif (
        has_forbidden_digit(guard_wrong)
        or has_forbidden_digit(guard_correct)
        or has_forbidden_symbol(narrow_wrong)
        or has_forbidden_symbol(narrow_correct)
    ):
        # HAI PHẠM VI KHÁC NHAU, cố ý: chữ số soi tới ±2 (vì nó nằm ngoài opcode
        # `replace`), còn ký hiệu/dấu câu chỉ soi TRONG cặp hẹp — `《》` của tiêu
        # đề sách nằm ngoài core là ngữ cảnh, không phải bằng chứng.
        reason = "digits_or_symbols"
    elif not core_ratio > threshold:
        reason = "core_not_homophone"
    elif not window_ratio > threshold:
        reason = "window_not_homophone"
    else:
        reason = None

    return {
        "narrow_wrong": narrow_wrong,
        "narrow_correct": narrow_correct,
        "window_wrong": window_wrong,
        "window_correct": window_correct,
        "core_pinyin_ratio": round(core_ratio, 3),
        "window_pinyin_ratio": round(window_ratio, 3),
        "reason": reason,
    }


def _rejected_entry(i, ocr_row_i: int, evaluation: dict, span: tuple[int, int]) -> dict:
    return {
        "i": i,
        "ocr_row_i": ocr_row_i,
        "narrow_wrong": evaluation["narrow_wrong"],
        "narrow_correct": evaluation["narrow_correct"],
        "window_wrong": evaluation["window_wrong"],
        "window_correct": evaluation["window_correct"],
        "span": [span[0], span[1]],
        "reason": evaluation["reason"],
        "core_pinyin_ratio": evaluation["core_pinyin_ratio"],
        "window_pinyin_ratio": evaluation["window_pinyin_ratio"],
    }


def name_patch_allowed(engine_id: str | None, specs=None) -> bool:
    """Engine này có được phép vá tên riêng không — capability `name_patch`.

    Vì sao phải có cổng này: bản vá sửa chữ NGUỒN, nên nó chỉ có lợi nếu engine
    dịch đọc đúng chữ đã sửa. ĐO ĐƯỢC: áp bản vá rồi dịch bằng `opus-mt` thì **3
    trong 7 câu TỆ ĐI** (bản vá làm mất một chỗ đúng hoặc đổi nghĩa), trong khi
    `hy-mt-1.5-7b` được lợi. Vì vậy đây là DỮ LIỆU của `registry.json`, không phải
    một bước luôn chạy: registry khai cho engine nào thì engine đó mới vá.

    Mặc định là **KHÔNG** vá: id lạ (không có trong danh sách `mt`) và engine thiếu
    khoá (hoặc khai `false`) đều trả `False`. Không đọc được registry cũng `False`
    — thà giữ nguyên chữ nguồn còn hơn vá rồi dịch bằng một engine chưa ai đo.

    `engine_id=None` là người gọi KHÔNG nêu engine (thư viện thuần, ví dụ một
    notebook chỉ muốn xem bản vá sinh ra gì) ⇒ không có ngữ cảnh registry để so,
    nên cổng không chặn. Đường CHẠY THẬT thì luôn nêu engine: CLI có `--engine`,
    và bước pipeline truyền đúng engine nó sắp dùng.
    """
    if engine_id is None:
        return True
    if specs is None:
        # Import BÊN TRONG hàm: module này là hàm thuần, và `app.adapters` kéo theo
        # `app.config` (đọc biến môi trường, tạo thư mục). Test bơm `specs` giả nên
        # không bài nào chạm đĩa.
        from app.adapters.registry_file import load_registry
        try:
            specs = load_registry()
        except (OSError, ValueError, KeyError):
            return False
    for spec in specs:
        if getattr(spec, "kind", None) == "mt" and spec.id == engine_id:
            return bool(spec.capabilities.get(NAME_PATCH_CAPABILITY, False))
    return False


def patch_transcript(
    segments: list[dict],
    ocr_rows: list[dict],
    *,
    pinyin_fn,
    t2s_fn=_AUTO,
    window_s: float = 0.5,
    threshold: float = 0.5,
    engine_id: str | None = None,
    specs=None,
) -> PatchResult:
    """Vá `segments` bằng các dòng OCR chồng thời gian. Trả `PatchResult`.

    `engine_id` là engine DỊCH sẽ dùng chữ nguồn này; cổng `name_patch_allowed`
    trả `False` thì hàm trả bản SAO y nguyên đầu vào (`stats["name_patch"]` là
    `False` kèm lý do) thay vì vá. Cổng nằm ở đây chứ chỉ ở CLI vì hàm này cũng
    là đường vào của các pipeline thử nghiệm: một lời gọi bỏ qua CLI mà vá bằng
    engine chưa đo là đúng thứ cổng sinh ra để chặn. `engine_id=None` giữ nguyên
    hành vi cũ (không có ngữ cảnh engine).

    BẤT BIẾN:
    * chỉ `text` đổi. `start`/`end`/`i` (và mọi khoá khác) đi ra y nguyên từng
      byte — bản vá không được phép làm lệch một mốc thời gian nào, vì mọi bước
      sau (cắt phụ đề, ghép bản dịch) bám theo chúng.
    * danh sách ra cùng thứ tự, cùng độ dài, cùng id với danh sách vào.
    * mỗi opcode `replace` của mỗi cặp (đoạn, dòng OCR) xuất hiện ĐÚNG MỘT LẦN
      trong `changes ∪ rejected`: opcode nào không thành bản vá phải có mặt kèm
      lý do, nếu không người đọc không phân biệt được "bị loại vì luật X" với
      "chưa bao giờ được xét".
    * kết quả TẤT ĐỊNH: cùng đầu vào cho cùng JSON (không dùng set/dict không sắp
      thứ tự trong đầu ra; mọi danh sách được sắp bằng khoá tường minh).
    """
    if t2s_fn is _AUTO:
        t2s_fn = opencc_t2s
    raw_rows = list(ocr_rows)
    # Cổng capability TRƯỚC mọi phép chuẩn hoá: engine không được phép vá thì
    # không có lý do gì đọc/normalize OCR cả, và `segments` ra phải là bản SAO y
    # nguyên đầu vào (không sửa tại chỗ — bất biến "không đụng dữ liệu gọi vào").
    if not name_patch_allowed(engine_id, specs):
        return PatchResult(
            segments=copy.deepcopy(segments),
            changes=[],
            rejected=[],
            stats={
                "segments": len(segments),
                "ocr_rows": len(raw_rows),
                "overlaps": 0,
                "applied": 0,
                "rejected": 0,
                "engine_id": engine_id,
                "name_patch": False,
                "skipped_reason": (
                    f"engine {engine_id!r} không khai `capabilities."
                    f"{NAME_PATCH_CAPABILITY}` trong registry.json — đo trên "
                    f"`opus-mt`, bản vá làm 3/7 câu tệ đi"),
            },
        )
    rows = _prepare_rows(raw_rows, t2s_fn)
    patched = copy.deepcopy(segments)
    changes: list[dict] = []
    rejected: list[tuple[tuple, dict]] = []
    overlaps = 0

    for position, segment in enumerate(segments):
        start, end = float(segment["start"]), float(segment["end"])
        segment_i = segment.get("i", position)
        seg_norm, index_map = _normalize_with_map(str(segment.get("text") or ""), t2s_fn)

        candidates = []
        for row in rows:
            if row["end"] < start - window_s or row["start"] > end + window_s:
                continue
            overlaps += 1
            candidates.append(row)

        if not candidates or not seg_norm:
            continue

        evaluations: list[dict] = []
        for row in candidates:
            row_norm = row["norm"]
            matcher = difflib.SequenceMatcher(None, seg_norm, row_norm, autojunk=False)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag != "replace":
                    # `insert`/`delete` là ASR nói thêm hoặc bỏ chữ — cần một bản vá
                    # khác (cắt/ghép), không phải một tên bị nghe nhầm. Trộn chúng
                    # vào đây biến bộ vá thành nơi chứa mọi khác biệt giữa hai bản.
                    continue
                evaluation = _evaluate(seg_norm, row_norm, i1, i2, j1, j2, pinyin_fn, threshold)
                # Ánh xạ khoảng của chuỗi CHUẨN HOÁ về khoảng của chuỗi GỐC: bản vá
                # cắt trên `text` gốc nên mọi ký tự không liên quan còn nguyên.
                span = (index_map[i1], index_map[i2 - 1] + 1)
                entry = {
                    "position": position,
                    "i": segment_i,
                    "ocr_row_i": row["i"],
                    "ocr_text": row["raw"],
                    "overlap_s": _overlap_seconds(start, end, row),
                    "span": span,
                    "evaluation": evaluation,
                }
                if evaluation["reason"] is None:
                    evaluations.append(entry)
                else:
                    rejected.append(
                        (
                            (position, span[0], span[1], row["i"]),
                            _rejected_entry(segment_i, row["i"], evaluation, span),
                        )
                    )

        # --- chống nhập nhằng -------------------------------------------------
        # Hai dòng OCR chồng nhau có thể cùng đề xuất cho CÙNG một khoảng. Gom các
        # đề xuất có khoảng GIAO nhau thành cụm; cụm có >= 2 cách sửa khác nhau
        # thì KHÔNG áp gì cả. Không chọn theo heuristic: một lựa chọn 50/50 được
        # ghi vào transcript như thể chắc chắn là kiểu hỏng không ai truy được.
        evaluations.sort(key=lambda item: (item["span"][0], item["span"][1], item["ocr_row_i"]))
        clusters: list[dict] = []
        for item in evaluations:
            span_start, span_end = item["span"]
            if clusters and span_start < clusters[-1]["end"]:
                clusters[-1]["items"].append(item)
                clusters[-1]["end"] = max(clusters[-1]["end"], span_end)
            else:
                clusters.append({"end": span_end, "items": [item]})

        applied: list[dict] = []
        for cluster in clusters:
            items = cluster["items"]
            signatures = {(item["span"], item["evaluation"]["narrow_correct"]) for item in items}
            if len(signatures) > 1:
                proposals = [
                    {
                        "ocr_row_i": item["ocr_row_i"],
                        "ocr_text": item["ocr_text"],
                        "narrow_wrong": item["evaluation"]["narrow_wrong"],
                        "narrow_correct": item["evaluation"]["narrow_correct"],
                        "span": [item["span"][0], item["span"][1]],
                        "core_pinyin_ratio": item["evaluation"]["core_pinyin_ratio"],
                        "window_pinyin_ratio": item["evaluation"]["window_pinyin_ratio"],
                    }
                    for item in items
                ]
                for item in items:
                    evaluation = dict(item["evaluation"], reason="ambiguous")
                    entry = _rejected_entry(segment_i, item["ocr_row_i"], evaluation, item["span"])
                    entry["proposals"] = proposals
                    rejected.append(
                        (
                            (position, item["span"][0], item["span"][1], item["ocr_row_i"]),
                            entry,
                        )
                    )
                continue
            applied.append(items[0])
            for duplicate in items[1:]:
                evaluation = dict(duplicate["evaluation"], reason="duplicate_correction")
                entry = _rejected_entry(
                    segment_i, duplicate["ocr_row_i"], evaluation, duplicate["span"]
                )
                entry["same_as_ocr_row_i"] = items[0]["ocr_row_i"]
                rejected.append(
                    (
                        (position, duplicate["span"][0], duplicate["span"][1], duplicate["ocr_row_i"]),
                        entry,
                    )
                )

        if not applied:
            continue
        # --- áp bản vá: PHẢI sang phải -> trái để offset còn đúng -----------------
        text = str(segment.get("text") or "")
        applied.sort(key=lambda item: item["span"][0], reverse=True)
        for item in applied:
            span_start, span_end = item["span"]
            text = text[:span_start] + item["evaluation"]["narrow_correct"] + text[span_end:]
        patched[position]["text"] = text

        before = str(segment.get("text") or "")
        for item in reversed(applied):  # trả lại thứ tự trái -> phải cho dễ đọc
            evaluation = item["evaluation"]
            changes.append(
                {
                    "i": segment_i,
                    "before": before,
                    "after": text,
                    "narrow_wrong": evaluation["narrow_wrong"],
                    "narrow_correct": evaluation["narrow_correct"],
                    "window_wrong": evaluation["window_wrong"],
                    "window_correct": evaluation["window_correct"],
                    "core_pinyin_ratio": evaluation["core_pinyin_ratio"],
                    "window_pinyin_ratio": evaluation["window_pinyin_ratio"],
                    "ocr_row_i": item["ocr_row_i"],
                    "ocr_text": item["ocr_text"],
                    "overlap_s": item["overlap_s"],
                }
            )

    rejected.sort(key=lambda pair: pair[0])
    return PatchResult(
        segments=patched,
        changes=changes,
        rejected=[entry for _, entry in rejected],
        stats={
            "segments": len(segments),
            "ocr_rows": len(raw_rows),
            "overlaps": overlaps,
            "applied": len(changes),
            "rejected": len(rejected),
        },
    )


__all__ = [
    "NAME_PATCH_CAPABILITY",
    "PatchResult",
    "PinyinUnavailable",
    "T2sUnavailable",
    "asr_segments_from_document",
    "name_patch_allowed",
    "ocr_rows_from_document",
    "opencc_t2s",
    "patch_transcript",
    "pypinyin_syllables",
]
