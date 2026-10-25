"""Đào bảng thuật ngữ nguồn-tới-nguồn từ reference OCR đóng băng (`v4`).

Mỗi cặp in ra là một bản vá **NGUỒN**: `wrong` (ASR nghe sai) -> `correct` (OCR
ghi đúng), áp lên transcript trước khi dịch. Đây KHÔNG phải bảng `Term` của app:
`Term` dịch thuật ngữ sang tiếng Việt trong lúc dịch, còn cặp ở đây sửa chính
chữ nguồn — nếu để lẫn hai thứ vào nhau thì một tên riêng bị nghe sai sẽ được
"dịch" thành âm Hán-Việt của chữ SAI, và lỗi đi thẳng vào bản dịch.

Vì sao lấy `ocr` chứ KHÔNG lấy `source_ocr`
    `ocr` là bản tham chiếu có hiệu lực đã chốt; nó khác `source_ocr` đúng bốn
    dòng (`i` = 26, 57, 64, 82) vì bốn dòng đó được sửa từ frame video. Lấy
    `source_ocr` là lấy lại đúng chữ mà reference đã cố ý bỏ, và bản vá sinh ra
    sẽ dạy translator đọc âm Hán-Việt của chữ sai.

Vì sao key theo `i` chứ KHÔNG theo vị trí mảng
    Hai mảng trong tệp không cùng độ dài khái niệm: vị trí 26 của
    `caption_observations` chứa `i` = 29, vị trí 57 chứa `i` = 62 (ba dòng
    `i` = 1, 2, 7 bị loại nên lệch từ đầu). Vị trí chỉ là thứ tự lưu; `i` mới là
    danh tính của dòng, và mọi vết (`rows[].i`, `evaluation_split`) phải bám
    theo `i` để người đọc đối chiếu được với reference.

Vì sao phải lọc watermark trước khi canh
    21 dòng `excluded_observations` vẫn mang cặp `(asr, ocr)` dùng được, nhưng
    9 trong số đó có `ocr` là watermark kênh (`想想工作室`, `想法工作室`,
    `bilibili`) — chữ TRÊN MÀN HÌNH, không phải lời nói. Ghép chúng với ASR sẽ
    sinh ra cặp rác dạng `Chance-Elysée -> 想想工作室`.

Vì sao phải t2s (OpenCC) TRƯỚC khi canh
    Dòng `i` = 87 của reference là chữ PHỒN THỂ (`在整個街區藏了很多個‘福’`)
    trong khi ASR là giản thể. Không t2s thì bộ canh thấy `个`/`個` và `区`/`區`
    là hai chữ khác nhau, rồi bảng dạy translator "sửa" `个` thành `個` — một bản
    vá đổi hệ chữ nhân danh "nghe nhầm". t2s là đúng `scoring_normalization` mà
    reference đã dùng để chấm; đây là cùng một phép biến đổi, áp ở đúng chỗ.

Vì sao cần cửa sổ neo (anchor)
    So đồng âm trên cửa sổ MỘT âm tiết là quá ít thông tin: `阴` (yīn) và `烟`
    (yān) khác nguyên âm nên bị loại, trong khi cả cụm `阴台山`/`烟台山` chỉ lệch
    một âm tiết trên ba (tỉ lệ khớp 0,67) và `烟台山` còn xuất hiện ở dòng thứ hai
    (i=53) — tức đây đúng là loại cặp đáng vá nhất, lại là cặp dễ mất nhất. Vì
    vậy mỗi `replace` được mở rộng thành một cửa sổ ngữ cảnh để so ở mức cụm; cửa
    sổ thay thế cặp hẹp trong danh sách (cặp hẹp vẫn được ghi lại trong
    `narrow_core`), chứ không phát thêm một dòng thứ hai cho cùng một lỗi.

Vì sao còn phải gate CORE (và đây là thứ chặn phần lớn rác)
    Cửa sổ neo tự nó quá dễ: một khác biệt MỘT chữ trong cửa sổ ba âm tiết luôn
    cho tỉ lệ 2/3 = 0,67 > 0,5, nên nó "cứu" mọi khác biệt một chữ — kể cả
    `是`/`就` (`shi`/`jiu`, không liên quan gì tới nghe nhầm). Đo trên reference:
    không gate core thì 16 cặp, gate core còn 11. Vì vậy mỗi candidate còn phải
    qua hai điều kiện trên CHÍNH cặp hẹp bên trong:

    * `multiple_cores`: cửa sổ gộp >= 2 opcode `replace` (`了→人` và `垫→钿` nằm
      chung một cửa sổ nghĩa là hai chỗ lệch; chỉ một chỗ có thể là nghe nhầm,
      nên cửa sổ đó không còn là một bản vá).
    * `core_not_homophone`: pinyin không dấu của core (NỐI thành chuỗi rồi mới
      so) phải khớp > 0,5. `阴`/`烟` (`yin`/`yan`) khớp 0,67 nên qua;
      `诶`/`哎` (`ei`/`ai`) khớp ĐÚNG 0,5 nên trượt — cùng lý do ngưỡng là `>`
      chứ không `>=` như ở quy tắc cửa sổ.

    Cặp bị loại KHÔNG biến mất khỏi tệp: nó nằm trong danh sách `dropped` kèm
    lý do và tỉ lệ, vì "vì sao cặp này không có trong bảng" là câu hỏi có thật,
    và một bộ lọc im lặng không trả lời được nó.

Vì sao chỉ cặp >= 2 ký tự mới được duyệt (patchable)
    Đầu ra của tệp này dùng để THAY CHUỖI trong transcript. Thay một chữ phổ
    thông (`业 <- 夜`) sẽ thay đúng chữ đó ở MỌI chỗ nó xuất hiện trong cả
    transcript, không chỉ chỗ bị nghe nhầm — đó là phá dữ liệu, không phải sửa
    lỗi. Cặp một chữ vẫn được in ra để người đọc thấy bằng chứng, nhưng không bao
    giờ `approved`.

Vì sao `pypinyin` / `opencc` chỉ nằm ở CLI
    Cả hai đều là phụ thuộc ĐÁNH GIÁ, không thuộc app (`requirements.txt` không
    có dòng nào cho chúng, giống `opencc-python-reimplemented` trước đây). Hàm
    đào nhận `pinyin_fn` và `t2s_fn` như tham số để test bơm bản giả (không cần
    cài gì, không chạm mạng, không GPU), còn CLI mới là chỗ nối bản thật và báo
    lỗi cài đặt rõ ràng nếu thiếu gói.

Vì sao "high" mới được duyệt
    OCR cũng sai được (chính bốn dòng 26/57/64/82 là bằng chứng: OCR gốc sai,
    phải sửa từ frame). Một cặp chỉ có MỘT dòng chưa kiểm chứng là một giả thuyết,
    không phải một bản vá — nên `confidence` chỉ lên `high` khi có ít nhất một
    trong ba nguồn tin cậy: dòng đã `frame_checked_*`, dạng đúng xuất hiện ở >= 2
    dòng, hoặc chính cặp đó do >= 2 dòng sinh ra. `approved` = `high` VÀ vá được.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import pathlib
import re
import sys
import unicodedata

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_REFERENCE = (
    BACKEND_DIR
    / "experiments"
    / "accuracy_pipelines"
    / "references"
    / "ocr-caption-reference-v4.json"
)
DEFAULT_OUTPUT = (
    ROOT_DIR
    / "data"
    / "experiments"
    / "accuracy-pipelines"
    / "20261019-ocr-glossary"
    / "ocr-glossary-candidates.json"
)

#: Watermark kênh bị đốt thẳng vào hình. So trên chuỗi đã chuẩn hoá và đã hạ chữ
#: thường: OCR có thể trả `Bilibili`/`BILIBILI`, so nguyên văn sẽ hụt đúng những
#: dòng đó rồi lọt vào bảng thuật ngữ.
WATERMARK_TERMS = ("想想工作室", "想法工作室", "bilibili")

#: NFKC biến `…` (U+2026) thành `...`, nên chỉ cần một tập ký tự là đủ che cả
#: `...`, `.` và `…`.
PLACEHOLDER_CHARS = frozenset(".")

#: Trần độ dài mỗi vế. Tên riêng nghe nhầm trong dữ liệu này dài 1-3 chữ; cặp dài
#: hơn 6 chữ gần như luôn là ranh giới cắt câu của `SequenceMatcher`, không phải
#: một lần nghe nhầm.
MAX_SIDE_CHARS = 6

#: Mỗi bên được mở thêm tối đa 2 ký tự khi dựng cửa sổ neo.
ANCHOR_MAX_EXTENSION = 2

#: Ngưỡng tỉ lệ khớp âm tiết, dùng cho CẢ HAI phép so: cửa sổ neo và core.
#: ĐO ĐƯỢC vì sao phải là `>` chứ không phải `>=`: `瓶值`/`平尺` có pinyin
#: `ping zhi`/`ping chi`, khớp ĐÚNG 0,5 — `>= 0,5` cho đúng cặp số-liệu-bị-chuẩn-
#: hoá-lại (dòng `i` = 13) lọt vào bảng. Cùng lý do đó loại `诶`/`哎` (`ei`/`ai`,
#: khớp đúng 0,5) khỏi bảng core. `阴台山`/`烟台山` khớp 0,67 và `长`/`展` khớp
#: 0,89 nên vẫn qua. Ngưỡng chặt hơn đúng một chút, và nó có lý do đo.
RATIO_THRESHOLD = 0.5

#: Hư từ / từ chức năng không thể là chữ MỞ ĐẦU của một từ ghép bị nghe nhầm, nên
#: khi ký tự bên trái là một trong số này thì cửa sổ neo phải mở sang PHẢI. Danh
#: sách nhỏ, cố ý đóng và đọc được từ dữ liệu: `来/去/有/找` đứng ngay trước cụm
#: danh từ (`来阴台山`, `去扇头`, `有夜内`, `找螺钿`), còn `拉/螺/榕/线/合` là hình
#: vị NỘI DUNG nên phải mở sang trái (`拉彩`, `螺垫`, `榕成`, `线钩`).
STOP_CHARS = frozenset(
    "的了着过地得是也都在就还和跟把被我你他她它这那些个来去有找说要给让做看想到吗呢吧啊嘛呀没"
)

#: Ngưỡng BÁO ĐỘNG, không phải ngưỡng lọc: 105 dòng mà nhả ra hơn chừng này cặp
#: thì bước lọc/neo lỏng hơn thiết kế, và người chạy phải thấy điều đó ngay trên
#: stderr thay vì tin vào một bảng trông có vẻ hợp lý.
#:
#: 🔴 Ngưỡng này TỪNG là `10`, và nó kêu oan: trên reference v4, bộ lọc ĐÃ SIẾT
#: (t2s + neo + cổng core) nhả ra đúng **11** cặp — mọi cặp đều là thay thế đồng
#: âm thật, 3 cặp approved, 8 cặp low. Một cái chuông reo ngay trên giá trị ĐÚNG
#: là một cái chuông hỏng: lần sau không ai còn đọc nó nữa. Nâng lên `15` để
#: chuông còn răng: trạng thái neo/lọc LỎNG của vòng trước nhả ra **16** cặp và
#: vẫn kêu, còn 11 (đã kiểm) im.
PAIR_COUNT_ALARM = 15

TRANSLATION_POLICY = (
    "proper nouns -> Sino-Vietnamese reading; artwork titles -> Vietnamese meaning "
    "followed by the Sino-Vietnamese reading (string check matches the parenthetical); "
    "common terms and slang -> meaning; every Term.translation stays "
    '"<VI: dien sau>" until a human fills it'
)

#: Regex thay cho phép thử "có chữ số ASCII": lớp `N` của `unicodedata` đã bao trùm
#: nó, nhưng để nguyên đây làm bằng chứng cho quy tắc đã chốt (spec nêu đúng
#: `[0-9０-９]`), và để lần đọc sau không ai "dọn" mất lớp bảo vệ thật.
_FORBIDDEN_CHAR_RE = re.compile(r"[0-9０-９]")


class PinyinUnavailable(RuntimeError):
    """`pypinyin` chưa có trong venv. Lỗi riêng để CLI in chỉ dẫn thay vì traceback."""


class T2sUnavailable(RuntimeError):
    """`opencc` chưa có trong venv. Lỗi riêng để CLI in chỉ dẫn thay vì traceback."""


def normalize(text: str) -> str:
    """NFKC rồi bỏ TOÀN BỘ khoảng trắng.

    Khoảng trắng không mang thông tin âm ở đây nhưng lại xuất hiện thật trong
    reference (`你 也 画 的 鱼 啊` là cách OCR chèn khoảng trắng giữa các chữ), nên
    giữ nó lại sẽ làm `SequenceMatcher` sinh ra một loạt `replace`/`insert` rỗng
    nghĩa và phá luôn phép so pinyin theo âm tiết.
    """
    return "".join(ch for ch in unicodedata.normalize("NFKC", text) if not ch.isspace())


def is_watermark(normalized: str) -> bool:
    lowered = normalized.casefold()
    return any(term in lowered for term in WATERMARK_TERMS)


def is_placeholder(normalized: str) -> bool:
    """Chuỗi rỗng hoặc chỉ gồm dấu chấm: `...`, `.`, `…` (đã thành `...` qua NFKC)."""
    return all(ch in PLACEHOLDER_CHARS for ch in normalized)


def has_forbidden_char(text: str) -> bool:
    """Có chữ số / ký hiệu / dấu câu không?

    Đây là quy tắc giữ số liệu bị định dạng lại (`一平尺2,000`) và dấu ngoặc của
    reference (`（+宽）x系数`) ra ngoài bảng: chúng là `replace` hợp lệ của
    `SequenceMatcher` nhưng không phải nghe nhầm tên riêng. Đo trên reference
    hiện tại: hai chuỗi ĐẦY ĐỦ đó bị quy tắc ĐỘ DÀI chặn trước (6 vs 9 và 5 vs 7
    ký tự); quy tắc này chặn đúng những mảnh `replace` mà bộ canh thật sự dựng
    lên — `成细 -> (+宽)x系` (dòng 6), hay `2000 -> 2,000` (4 vs 5 ký tự, lọt qua
    độ dài). Lọc theo LỚP Unicode chứ không theo danh sách ký tự, vì dữ liệu còn
    dấu câu toàn khổ (`，`, `、`) và ký hiệu toán học khác chưa gặp.
    """
    if _FORBIDDEN_CHAR_RE.search(text):
        return True
    for ch in text:
        if unicodedata.category(ch)[0] in ("N", "S", "P"):
            return True
    return False


def pypinyin_syllables(text: str) -> list[str]:
    """Âm tiết không dấu của `text` bằng `pypinyin` thật (dùng ở CLI).

    Bản thật duy nhất; nó nạp `pypinyin` BÊN TRONG hàm để `import` module này
    không kéo theo một phụ thuộc đánh giá.
    """
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError as exc:  # pragma: no cover - nhánh này do CLI kiểm
        raise PinyinUnavailable(
            "thiếu gói `pypinyin` (chỉ dùng cho bước ĐÁNH GIÁ, không thuộc app)"
        ) from exc
    # `errors` mặc định giữ nguyên ký tự không phải chữ Hán (chữ Latinh, chữ số),
    # đúng thứ ta cần: hai vế được so bằng cùng một phép biến đổi.
    return [syllable for syllable in lazy_pinyin(text, style=Style.NORMAL) if syllable.strip()]


_OPENCC = None


def opencc_t2s(text: str) -> str:
    """Phồn -> giản bằng OpenCC thật (dùng ở CLI).

    Converter được giữ lại giữa các lần gọi: `OpenCC("t2s")` nạp từ điển, tạo mới
    cho từng dòng là trả giá đó 105 lần cho một phép biến đổi thuần tuý.
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


def is_near_homophone(wrong: str, correct: str, pinyin_fn) -> bool:
    """Hai vế của CỬA SỔ có gần đồng âm không (so pinyin KHÔNG dấu)?

    Cặp 1:1 âm tiết phải BẰNG NHAU tuyệt đối: một âm tiết là quá ít thông tin để
    nới, và nới ở đó là mời `阴`(yīn) đứng ngang `烟`(yān) — chính cặp phải đi qua
    đường cửa sổ neo chứ không phải đường cặp hẹp. Cửa sổ >= 2 âm tiết thì hạ
    xuống tỉ lệ khớp > 0,5.
    """
    syllables_wrong = pinyin_fn(wrong)
    syllables_correct = pinyin_fn(correct)
    if len(syllables_wrong) == 1 and len(syllables_correct) == 1:
        return syllables_wrong == syllables_correct
    return (
        difflib.SequenceMatcher(None, syllables_wrong, syllables_correct).ratio()
        > RATIO_THRESHOLD
    )


def core_pinyin_ratio(narrow_wrong: str, narrow_correct: str, pinyin_fn) -> float:
    """Tỉ lệ khớp pinyin của CHÍNH cặp hẹp (NỐI âm tiết thành chuỗi rồi mới so).

    Nối thành chuỗi rồi mới so là để `阴`(yin) vs `烟`(yan) ra 0,67 — so theo phần
    tử rời thì chỉ còn 0 hoặc 1 và mất hết thông tin "gần âm". Đo trên reference:
    `夜`/`业` 1,0 · `长`/`展` 0,889 · `阴`/`烟` 0,667 · `诶`/`哎` 0,5 ·
    `喂`/`哎` 0,4 · `那`/`弄` và `是`/`就` 0,333.
    """
    joined_wrong = "".join(pinyin_fn(narrow_wrong))
    joined_correct = "".join(pinyin_fn(narrow_correct))
    return difflib.SequenceMatcher(None, joined_wrong, joined_correct).ratio()


def core_rejection(core_count: int, ratio: float) -> str | None:
    """Tên quy tắc gate-core đã loại cặp, hoặc `None` nếu core hợp lệ.

    Kiểm `multiple_cores` trước: một cửa sổ gộp hai chỗ lệch thì tỉ lệ pinyin của
    nó không còn nghĩa gì để bàn, và lý do "nhiều core" mới là lý do thật.
    """
    if core_count >= 2:
        return "multiple_cores"
    if not ratio > RATIO_THRESHOLD:
        return "core_not_homophone"
    return None


def pair_rejection(wrong: str, correct: str, pinyin_fn, t2s_fn=None) -> str | None:
    """Tên QUY TẮC đã loại cặp này, hoặc `None` nếu nó là một lần nghe nhầm.

    Trả về TÊN quy tắc chứ không trả `bool` vì câu hỏi thật của người đọc bảng là
    "vì sao cặp tôi biết là sai lại không có trong đây" — một `False` không trả lời
    được, còn `"not_homophone"` thì trả lời được ngay.

    `script_variant` là luật t2s viết thành một chỗ kiểm được: cặp mà hai vế chỉ
    khác nhau ở HỆ CHỮ (`个`/`個`, `区`/`區`) không phải nghe nhầm. Khi
    `collect_rows` đã t2s cả hai vế thì nhánh này không bao giờ bắn — nó tồn tại
    để bất biến "t2s(wrong) == t2s(correct) thì bỏ" có đúng MỘT chỗ cài đặt, và
    để nó vẫn đúng nếu ai đó đổi thứ tự chuẩn hoá về sau.
    """
    if wrong == correct:
        return "identical"
    if not (1 <= len(wrong) <= MAX_SIDE_CHARS and 1 <= len(correct) <= MAX_SIDE_CHARS):
        return "length"
    if has_forbidden_char(wrong) or has_forbidden_char(correct):
        return "digits_or_symbols"
    if t2s_fn is not None and t2s_fn(wrong) == t2s_fn(correct):
        return "script_variant"
    if not is_near_homophone(wrong, correct, pinyin_fn):
        return "not_homophone"
    return None


def is_stop_char(char: str) -> bool:
    return char in STOP_CHARS


def syllable_count(text: str, pinyin_fn) -> int:
    return len(pinyin_fn(text))


def build_anchor_window(
    asr_norm: str, ocr_norm: str, i1: int, i2: int, j1: int, j2: int, pinyin_fn
) -> dict | None:
    """Cửa sổ neo quanh một `replace`, hoặc `None` nếu không cần/không mở được.

    Trả kèm `left`/`right` — số ký tự đã mở mỗi bên — vì gate core cần BIẾT cửa sổ
    phủ những opcode nào: một cửa sổ gộp hai `replace` là hai chỗ lệch, không phải
    một lần nghe nhầm.

    Hai bước, thứ tự có nghĩa:

    1. Mở sang TRÁI từng ký tự (tối đa 2), dừng ngay khi mỗi vế đã >= 2 âm tiết,
       và dừng hẳn nếu ký tự bên trái là hư từ — hư từ không thể là phần đầu của
       từ bị nghe nhầm, nên mở qua nó chỉ tạo cửa sổ rác (`来阴` thay vì
       `阴台山`).
    2. Không mở được sang trái thì mở sang PHẢI, lấy TỐI ĐA 2 ký tự (không dừng ở
       mốc 2 âm tiết): địa danh ba chữ như `烟台山` chỉ lộ ra khi lấy đủ hai ký tự
       bên phải; dừng sớm sẽ ra `阴台` — đúng chỗ tỉ lệ khớp tụt còn 0,5 và cặp
       tốt nhất của cả reference bị mất.
    """
    narrow_wrong = asr_norm[i1:i2]
    narrow_correct = ocr_norm[j1:j2]
    if syllable_count(narrow_wrong, pinyin_fn) >= 2 and syllable_count(
        narrow_correct, pinyin_fn
    ) >= 2:
        return None

    left = 0
    while left < ANCHOR_MAX_EXTENSION and i1 - left > 0 and j1 - left > 0:
        if is_stop_char(asr_norm[i1 - left - 1]) or is_stop_char(ocr_norm[j1 - left - 1]):
            break
        left += 1
        window_wrong = asr_norm[i1 - left:i2]
        window_correct = ocr_norm[j1 - left:j2]
        if syllable_count(window_wrong, pinyin_fn) >= 2 and syllable_count(
            window_correct, pinyin_fn
        ) >= 2:
            return {
                "wrong": window_wrong,
                "correct": window_correct,
                "left": left,
                "right": 0,
            }

    right = min(ANCHOR_MAX_EXTENSION, len(asr_norm) - i2, len(ocr_norm) - j2)
    while right > 0:
        window_wrong = asr_norm[i1 - left:i2 + right]
        window_correct = ocr_norm[j1 - left:j2 + right]
        if syllable_count(window_wrong, pinyin_fn) >= 2 and syllable_count(
            window_correct, pinyin_fn
        ) >= 2:
            return {
                "wrong": window_wrong,
                "correct": window_correct,
                "left": left,
                "right": right,
            }
        right -= 1
    return None


def collect_rows(document: dict, t2s_fn=None) -> list[dict]:
    """Các dòng dùng được, đã chuẩn hoá, kèm nhãn `split` của chính dòng đó.

    Chuỗi được chuẩn hoá NFKC -> bỏ khoảng trắng -> t2s (nếu bật) TRƯỚC khi canh.
    t2s phải đứng trước `SequenceMatcher`, không phải sau: canh trên chữ phồn thì
    mọi `replace` của dòng 87 đều là "nghe nhầm" giả.

    Gộp cả `excluded_observations`: 21 dòng bị loại không phải rác đồng nhất —
    9 dòng là watermark (bỏ hẳn), 12 dòng bị loại vì "quá ngắn để chấm điểm", và
    2 trong 12 dòng đó (`i` = 2, `i` = 31) vẫn có chữ OCR thật (10 dòng còn lại
    `ocr` rỗng). Bỏ cả nhóm khỏi đầu vào nghĩa là câu ngắn — đúng chỗ ASR hay
    nghe nhầm nhất — sẽ không bao giờ được xét tới. Nhãn `split` của dòng bị loại
    là `None`: chúng không nằm trong nửa dev/test nào, nên không được phép trả lời
    câu "cặp này có được đào từ nửa test không".
    """
    metadata = document.get("metadata") or {}
    included = metadata.get("caption_observations") or []
    excluded = document.get("excluded_observations") or []

    def prepare(text: str) -> str:
        normalized = normalize(text)
        return t2s_fn(normalized) if t2s_fn is not None else normalized

    rows: list[dict] = []
    for raw, split in [(row, (row or {}).get("evaluation_split")) for row in included] + [
        (row, None) for row in excluded
    ]:
        if not isinstance(raw, dict):
            raise ValueError("mỗi observation phải là một object")
        if "i" not in raw:
            raise ValueError(f"observation thiếu khoá `i`: {sorted(raw)}")
        ocr_normalized = prepare(raw.get("ocr") or "")
        if not ocr_normalized or is_placeholder(ocr_normalized) or is_watermark(ocr_normalized):
            continue
        rows.append(
            {
                "i": int(raw["i"]),
                "split": split,
                "verification_status": raw.get("verification_status"),
                "asr_norm": prepare(raw.get("asr") or ""),
                "ocr_norm": ocr_normalized,
            }
        )
    return rows


def _count_form(form: str, corpus: list[str]) -> int:
    return sum(text.count(form) for text in corpus)


def count_replace_opcodes(rows: list[dict]) -> int:
    """Số opcode `replace` trên mọi dòng dùng được — MẪU SỐ của sổ ghi vết.

    Đếm ĐỘC LẬP bằng cách canh lại từ đầu, không dùng chung vòng lặp với
    `mine_candidates`: nếu dùng chung thì phép so `tổng ba danh sách == số opcode`
    sẽ luôn khớp kể cả khi chính vòng lặp đó bỏ sót opcode — một phép kiểm tự xác
    nhận chính nó.
    """
    total = 0
    for row in rows:
        matcher = difflib.SequenceMatcher(
            None, row["asr_norm"], row["ocr_norm"], autojunk=False
        )
        total += sum(1 for opcode in matcher.get_opcodes() if opcode[0] == "replace")
    return total


def _replace_count_inside(replace_opcodes, start: int, end: int) -> int:
    """Số opcode `replace` nằm TRỌN trong đoạn `[start, end)` của vế ASR."""
    return sum(1 for _, k1, k2, _, _ in replace_opcodes if k1 >= start and k2 <= end)


def _rows_payload(pair_rows: list[dict]) -> list[dict]:
    return [
        {
            "i": row["i"],
            "split": row["split"],
            "verification_status": row["verification_status"],
        }
        for row in pair_rows
    ]


def mine_candidates(
    rows: list[dict], pinyin_fn, t2s_fn=None
) -> tuple[list[dict], list[dict], list[dict]]:
    """Sinh `(candidates, dropped, rejected)` từ những dòng đã chuẩn hoá.

    Mỗi `replace` sinh ĐÚNG MỘT candidate: cửa sổ neo nếu mở được và qua bộ lọc,
    ngược lại là cặp hẹp. Phát cả hai là nhân đôi danh sách cho một lỗi, mà thông
    tin của cặp hẹp vẫn còn nguyên trong `narrow_core` của candidate neo — cặp bị
    cắt vụn TRỞ THÀNH cụm có nghĩa, không phải thành hai dòng. Nếu cửa sổ neo bị
    gate core loại thì KHÔNG rơi về cặp hẹp: cặp hẹp đó chính là core vừa trượt
    gate, phát nó ra chỉ để nói lại điều vừa bị loại.

    BẤT BIẾN: mỗi opcode `replace` của mọi dòng dùng được xuất hiện ĐÚNG MỘT LẦN
    trong hợp ba danh sách; opcode nào không thành candidate thì phải có mặt trong
    `rejected` kèm lý do. Trước vòng 4, 17 trên 32 opcode của reference biến mất
    không dấu vết, và người đọc không phân biệt được "bị loại vì lý do X" với
    "chưa bao giờ được xét" — hai chuyện rất khác nhau khi đi tìm lỗi.

    Chỉ xét opcode `replace`. `insert`/`delete` là ASR nói thêm hoặc bỏ chữ — cần
    một bản vá khác (cắt/ghép), không phải một mục thuật ngữ; trộn chúng vào đây
    sẽ biến bảng thành nơi chứa mọi khác biệt giữa hai bản, tức là vô dụng.
    """
    corpus = [row["asr_norm"] for row in rows] + [row["ocr_norm"] for row in rows]
    grouped: dict[tuple, dict] = {}
    merged: list[dict] = []
    rejected: list[dict] = []
    for row in rows:
        matcher = difflib.SequenceMatcher(
            None, row["asr_norm"], row["ocr_norm"], autojunk=False
        )
        replace_opcodes = [
            opcode for opcode in matcher.get_opcodes() if opcode[0] == "replace"
        ]
        for _, i1, i2, j1, j2 in replace_opcodes:
            narrow_wrong = row["asr_norm"][i1:i2]
            narrow_correct = row["ocr_norm"][j1:j2]
            narrowed = {"wrong": narrow_wrong, "correct": narrow_correct}
            anchor = build_anchor_window(
                row["asr_norm"], row["ocr_norm"], i1, i2, j1, j2, pinyin_fn
            )
            if anchor is not None and pair_rejection(
                anchor["wrong"], anchor["correct"], pinyin_fn, t2s_fn
            ) is None:
                wrong, correct, is_anchor = anchor["wrong"], anchor["correct"], True
                core_count = _replace_count_inside(
                    replace_opcodes, i1 - anchor["left"], i2 + anchor["right"]
                )
            else:
                narrow_rejection = pair_rejection(
                    narrow_wrong, narrow_correct, pinyin_fn, t2s_fn
                )
                if narrow_rejection is not None:
                    # Không thành candidate: phải ghi lại lý do, nếu không opcode
                    # này biến mất khỏi mọi danh sách và không ai truy được.
                    rejected.append(
                        {
                            "i": row["i"],
                            "split": row["split"],
                            "wrong": narrow_wrong,
                            "correct": narrow_correct,
                            "narrow_core": narrowed,
                            "reason": narrow_rejection,
                            "ratio": round(
                                core_pinyin_ratio(narrow_wrong, narrow_correct, pinyin_fn), 3
                            ),
                            "merged_into": None,
                        }
                    )
                    continue
                wrong, correct, is_anchor = narrow_wrong, narrow_correct, False
                core_count = 1
            ratio = core_pinyin_ratio(narrow_wrong, narrow_correct, pinyin_fn)
            key = (wrong, correct, is_anchor, narrow_wrong, narrow_correct)
            bucket = grouped.setdefault(
                key,
                {
                    "rows": {},
                    "reason": core_rejection(core_count, ratio),
                    "ratio": ratio,
                    "core_count": core_count,
                },
            )
            if bucket["rows"]:
                # Cùng một cặp ở dòng THỨ HAI: entry đã phát rồi, nên opcode này
                # chỉ ghi vết "đã gộp vào đâu" (không đẻ candidate thứ hai cho
                # cùng một cặp); `occurrences` của entry kia vẫn đếm đủ vì đó là
                # bằng chứng tin cậy của nó.
                merged.append(
                    {
                        "i": row["i"],
                        "split": row["split"],
                        "wrong": wrong,
                        "correct": correct,
                        "narrow_core": narrowed,
                        "reason": "merged_duplicate",
                        "ratio": round(ratio, 3),
                        "merged_into": None,
                        "_key": key,
                    }
                )
            bucket["rows"][row["i"]] = row

    candidates: list[dict] = []
    dropped: list[dict] = []
    emitted: dict[tuple, tuple[int, str]] = {}
    for (wrong, correct, is_anchor, narrow_wrong, narrow_correct), bucket in grouped.items():
        pair_rows = [bucket["rows"][index] for index in sorted(bucket["rows"])]
        narrowed = {"wrong": narrow_wrong, "correct": narrow_correct}
        key = (wrong, correct, is_anchor, narrow_wrong, narrow_correct)
        emitted[key] = (pair_rows[0]["i"], "dropped" if bucket["reason"] else "candidates")
        if bucket["reason"] is not None:
            # Bị loại vẫn phải ĐỌC ĐƯỢC: "vì sao cặp này không có trong bảng" là
            # câu hỏi có thật, và một bộ lọc im lặng không trả lời được nó.
            dropped.append(
                {
                    "wrong": wrong,
                    "correct": correct,
                    "anchor": is_anchor,
                    "narrow_core": narrowed,
                    "core_count": bucket["core_count"],
                    "core_pinyin_ratio": round(bucket["ratio"], 3),
                    "occurrences": len(pair_rows),
                    "rows": _rows_payload(pair_rows),
                    "reason": bucket["reason"],
                }
            )
            continue
        # `correct_form_rows` đếm trên TOÀN bộ dòng dùng được, không chỉ trên dòng
        # sinh ra cặp: đó là bằng chứng ngoại lai duy nhất ta có, và nó phải độc
        # lập với dòng đang xét thì mới đáng tin.
        correct_form_rows = len({row["i"] for row in rows if correct in row["ocr_norm"]})
        frame_checked = any(
            (row["verification_status"] or "").startswith("frame_checked_")
            for row in pair_rows
        )
        reasons: list[str] = []
        if frame_checked:
            reasons.append("frame-checked row in reference")
        if correct_form_rows >= 2:
            reasons.append(f"correct form corroborated by {correct_form_rows} rows")
        if len(pair_rows) >= 2:
            reasons.append(f"pair produced by {len(pair_rows)} rows")
        high = bool(reasons)
        if not reasons:
            reasons.append("single unverified row; not corroborated")
        # Patchability: thay một chữ phổ thông là thay nó ở MỌI chỗ trong
        # transcript, nên cặp một chữ không bao giờ được duyệt dù bằng chứng mạnh.
        patchable = len(wrong) >= 2 and len(correct) >= 2
        if not patchable:
            reasons.append("single_character_not_patchable")
        if is_anchor:
            reasons.append(f"context window around {narrow_wrong} -> {narrow_correct}")
        candidates.append(
            {
                "wrong": wrong,
                "correct": correct,
                "confidence": "high" if high else "low",
                # OCR cũng sai được, nên chỉ cặp "high" VÀ vá được mới được duyệt.
                "approved": high and patchable,
                "patchable": patchable,
                "occurrences": len(pair_rows),
                "correct_form_rows": correct_form_rows,
                "corpus_frequency": {
                    "correct": _count_form(correct, corpus),
                    "wrong": _count_form(wrong, corpus),
                },
                # Chỉ để ĐỌC, không dùng để duyệt: nó cho thấy `个`/`城` là chữ phổ
                # thông còn `烟台山`/`曹磊` là tên hiếm, mà không đổi quyết định nào.
                "rare_form": _count_form(correct, corpus) <= 3,
                "anchor": is_anchor,
                "narrow_core": narrowed,
                # Dạng PHẲNG của cùng cặp core, chỉ điền khi candidate là cửa sổ
                # neo (vòng 2 đã chốt nghĩa này: `narrow_*` = "cặp hẹp đã bị cửa
                # sổ thay thế"); với cặp hẹp thì `narrow_core` đã chính là cặp đó.
                "narrow_wrong": narrow_wrong if is_anchor else None,
                "narrow_correct": narrow_correct if is_anchor else None,
                "core_pinyin_ratio": round(bucket["ratio"], 3),
                "rows": _rows_payload(pair_rows),
                "reason": "; ".join(reasons),
            }
        )
    # `high` trước, trong mỗi mức thì nhiều bằng chứng trước. Khoá phụ `correct`
    # rồi `wrong` chỉ để hai lần chạy trên cùng tệp ra cùng thứ tự byte.
    candidates.sort(
        key=lambda entry: (
            0 if entry["confidence"] == "high" else 1,
            -entry["occurrences"],
            entry["correct"],
            entry["wrong"],
        )
    )
    dropped.sort(key=lambda entry: (entry["reason"], entry["correct"], entry["wrong"]))
    # Giờ mới biết mỗi cặp đã phát rơi vào `candidates` hay `dropped`, nên
    # `merged_into` được điền ở đây chứ không phải lúc gặp bản trùng.
    for entry in merged:
        first_i, where = emitted[entry.pop("_key")]
        entry["merged_into"] = {"i": first_i, "where": where}
        rejected.append(entry)
    rejected.sort(key=lambda entry: (entry["i"], entry["reason"]))
    return candidates, dropped, rejected


def filter_by_confidence(entries: list[dict], minimum: str) -> list[dict]:
    if minimum == "low":
        return list(entries)
    return [entry for entry in entries if entry["confidence"] == "high"]


def build_output(
    document: dict,
    reference_bytes: bytes,
    entries: list[dict],
    dropped: list[dict],
    rejected: list[dict],
    t2s_enabled: bool,
) -> dict:
    """Document đầu ra, kèm phần gốc để đọc lại được là cặp nào sinh từ tệp nào.

    `normalization` ghi cả t2s: cùng một reference, `--no-t2s` cho ra danh sách
    khác (có `个 -> 個`, `区 -> 區`), nên một tệp đầu ra không nói rõ nó t2s hay
    không là một tệp không tái lập được. `dropped`/`rejected` nằm NGOÀI
    `candidates`: "bị gate core loại" và "bị quy tắc lọc loại" là hai chuyện khác
    với "đã thành bảng vá", và trộn ba thứ vào một danh sách là mời người sau vá
    nhầm. Ba danh sách cộng lại phải bằng đúng số opcode `replace` của reference.
    """
    return {
        "reference": {
            "dataset_id": document.get("dataset_id"),
            "version": document.get("version"),
            "sha256": hashlib.sha256(reference_bytes).hexdigest(),
        },
        "generated_by": "scripts/mine_ocr_glossary.py",
        "normalization": (
            "NFKC; strip all whitespace; OpenCC t2s"
            if t2s_enabled
            else "NFKC; strip all whitespace"
        ),
        "translation_policy": TRANSLATION_POLICY,
        "candidates": entries,
        "dropped": dropped,
        "rejected": rejected,
    }


def _rows_label(entry: dict) -> str:
    return ",".join(f"{row['i']}({row['split'] or '-'})" for row in entry["rows"])


def format_table(entries: list[dict]) -> str:
    lines = [
        "correct <- wrong | conf | approved | patchable | rare | freq c/w | core | anchor | rows"
    ]
    for entry in entries:
        frequency = (
            f"{entry['corpus_frequency']['correct']}/{entry['corpus_frequency']['wrong']}"
        )
        lines.append(
            f"{entry['correct']} <- {entry['wrong']} | {entry['confidence']} | "
            f"{'yes' if entry['approved'] else 'no'} | "
            f"{'yes' if entry['patchable'] else 'no'} | "
            f"{'yes' if entry['rare_form'] else 'no'} | {frequency} | "
            f"{entry['core_pinyin_ratio']:.3f} | "
            f"{'yes' if entry['anchor'] else 'no'} | {_rows_label(entry)}"
        )
    return "\n".join(lines)


def format_dropped_table(dropped: list[dict]) -> str:
    lines = ["correct <- wrong | reason | core ratio | cores | rows"]
    for entry in dropped:
        lines.append(
            f"{entry['correct']} <- {entry['wrong']} | {entry['reason']} | "
            f"{entry['core_pinyin_ratio']:.3f} | {entry['core_count']} | "
            f"{_rows_label(entry)}"
        )
    return "\n".join(lines)


def format_rejected_table(rejected: list[dict]) -> str:
    lines = ["i | wrong -> correct | reason | core ratio | merged_into"]
    for entry in rejected:
        merged_into = (
            f"{entry['merged_into']['i']}({entry['merged_into']['where']})"
            if entry["merged_into"]
            else "-"
        )
        lines.append(
            f"{entry['i']} | {entry['wrong']} -> {entry['correct']} | "
            f"{entry['reason']} | {entry['ratio']:.3f} | {merged_into}"
        )
    return "\n".join(lines)


def _resolve(path: pathlib.Path) -> pathlib.Path:
    return path if path.is_absolute() else ROOT_DIR / path


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mine_ocr_glossary.py",
        description=(
            "Đào cặp (ASR nghe sai, OCR đúng) từ reference OCR v4 "
            "thành bảng vá nguồn trước khi dịch."
        ),
    )
    parser.add_argument("--reference", type=pathlib.Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--min-confidence",
        choices=("high", "low"),
        default="low",
        help="mức thấp nhất được in/ghi; `high` chỉ giữ cặp đã được duyệt",
    )
    parser.add_argument(
        "--no-t2s",
        action="store_true",
        help="tắt OpenCC t2s (để thấy dòng phồn thể sinh ra cặp biến thể hệ chữ)",
    )
    return parser.parse_args(argv)


def _force_utf8_streams() -> None:
    """Ép UTF-8 cho stdout/stderr trước khi in bất cứ thứ gì.

    Console Windows mặc định cp1252 còn bảng in ra toàn chữ Hán: lần chạy thật
    đầu tiên sẽ `UnicodeEncodeError` ngay giữa bảng, sau khi đã ghi xong tệp —
    đúng kiểu hỏng im lặng khó lần. (Cùng lý do với `scripts/smoke_asr.py`.)
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


_AUTO = object()


def _missing_package_message(package: str, install: str, hint: str = "") -> int:
    print(
        f"KHÔNG chạy được: thiếu gói `{package}` (chỉ dùng cho bước ĐÁNH GIÁ, "
        "không thuộc app).\n"
        f"Cài bằng: backend\\.venv\\Scripts\\python.exe -m pip install {install}\n"
        f"{hint}"
        "Gói này KHÔNG được thêm vào requirements của app.",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None, pinyin_fn=None, t2s_fn=_AUTO) -> int:
    _force_utf8_streams()
    args = parse_args(argv)
    reference_path = _resolve(args.reference)
    output_path = _resolve(args.output)
    if not reference_path.exists():
        print(f"KHÔNG thấy reference: {reference_path}", file=sys.stderr)
        return 2

    if pinyin_fn is None:
        try:
            pypinyin_syllables("燕")
            pinyin_fn = pypinyin_syllables
        except PinyinUnavailable:
            # Kiểm gói TRƯỚC khi đọc reference: thiếu gói là lỗi cài đặt, phải báo
            # ngay chứ không để nó nổ giữa lúc đào.
            return _missing_package_message("pypinyin", "pypinyin")

    if t2s_fn is _AUTO:
        if args.no_t2s:
            t2s_fn = None
        else:
            try:
                opencc_t2s("國")
                t2s_fn = opencc_t2s
            except T2sUnavailable:
                return _missing_package_message(
                    "opencc",
                    "opencc-python-reimplemented",
                    "Hoặc chạy lại với --no-t2s nếu chấp nhận cặp biến thể phồn/thống.\n",
                )

    reference_bytes = reference_path.read_bytes()
    document = json.loads(reference_bytes)
    if not isinstance(document, dict):
        print("reference phải là một object JSON", file=sys.stderr)
        return 2

    rows = collect_rows(document, t2s_fn)
    candidates, dropped, rejected = mine_candidates(rows, pinyin_fn, t2s_fn)
    opcodes = count_replace_opcodes(rows)
    accounted = len(candidates) + len(dropped) + len(rejected)

    filtered = filter_by_confidence(candidates, args.min_confidence)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # `dropped`/`rejected` KHÔNG bị `--min-confidence` lọc: chúng là sổ ghi vết của
    # bộ lọc, không phải một mức tin cậy, và cắt chúng đi là mở lại đúng lỗ hổng
    # mà vòng 4 tồn tại để vá.
    output = build_output(
        document, reference_bytes, filtered, dropped, rejected, t2s_fn is not None
    )
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    raw_included = len((document.get("metadata") or {}).get("caption_observations") or [])
    raw_excluded = len(document.get("excluded_observations") or [])
    print(
        f"reference {reference_path} (v{document.get('version')}, "
        f"sha256 {output['reference']['sha256'][:12]}…)"
    )
    print(
        f"dòng: {raw_included} included + {raw_excluded} excluded = "
        f"{raw_included + raw_excluded}; dùng được {len(rows)}; "
        f"t2s {'BẬT' if t2s_fn is not None else 'TẮT'}"
    )
    print(
        f"cặp: {len(candidates)} đào được, {len(filtered)} còn lại sau "
        f"--min-confidence {args.min_confidence}; "
        f"{sum(1 for entry in filtered if entry['approved'])} approved"
    )
    print(
        f"opcode: {opcodes} | candidate core: {len(candidates)} | "
        f"core-gate: {len(dropped)} | rejected: {len(rejected)} | "
        f"tổng giải trình: {accounted}"
    )
    print("")
    print(format_table(filtered))
    if dropped:
        print("")
        print(f"bị gate core loại ({len(dropped)}):")
        print(format_dropped_table(dropped))
    if rejected:
        print("")
        print(f"bị quy tắc lọc loại ({len(rejected)}):")
        print(format_rejected_table(rejected))
    print("")
    print(f"đã ghi {output_path}")

    if accounted != opcodes:
        # Sổ ghi vết tự nó phải đóng: thiếu một opcode nghĩa là có chỗ bị loại mà
        # không ai truy được, đúng lỗi mà vòng 4 sửa. In to, nhưng KHÔNG chặn tệp
        # — tệp còn đó mới là thứ dùng để tìm ra chỗ hở.
        print(
            "\n" + "!" * 78 + "\n"
            f"!!! BÁO ĐỘNG: {opcodes} opcode `replace` nhưng chỉ giải trình được "
            f"{accounted}.\n"
            "!!! Có opcode bị loại mà KHÔNG được ghi vào candidates/dropped/rejected "
            "— sổ ghi vết đang hở.\n"
            + "!" * 78,
            file=sys.stderr,
        )

    if len(filtered) > PAIR_COUNT_ALARM:
        # KHÔNG tự siết bộ lọc: nếu siết im lặng thì con số trên bảng trông đẹp mà
        # người chạy không biết mình vừa đổi định nghĩa "nghe nhầm" cho vừa mắt.
        # In MỘT lần ra stderr: in cả ra stdout nữa thì ai chạy trong terminal thấy
        # hai bản giống hệt nhau và tưởng script in lặp.
        print(
            "\n" + "!" * 78 + "\n"
            f"!!! BÁO ĐỘNG: {len(filtered)} cặp > ngưỡng {PAIR_COUNT_ALARM}. Danh sách "
            "DÀI HƠN thiết kế\n"
            "!!! (kỳ vọng 4-10 cặp tên/thuật ngữ). Bộ lọc KHÔNG được tự siết — bảng "
            "trên là nguyên\n"
            "!!! trạng để người đọc quyết định.\n"
            + "!" * 78,
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
