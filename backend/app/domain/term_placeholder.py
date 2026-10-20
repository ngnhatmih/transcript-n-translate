"""Token GIỮ CHỖ cho thuật ngữ, để bản dịch của thuật ngữ đến từ glossary.

Vì sao module này tồn tại
    Policy của sản phẩm cho chữ Hán trong phụ đề Việt là **Hán-Việt**
    (`曹磊` -> `Tào Lôi`, `烟台山` -> `Yên Đài Sơn`); tiêu đề tác phẩm là nghĩa
    tiếng Việt kèm Hán-Việt trong ngoặc; thuật ngữ/slang phổ thông thì lấy nghĩa
    (`螺钿` -> `khảm xà cừ`, `拉踩` -> `dìm hàng`). Model đã ship
    (`hy-mt1.5-7b:q4_K_M` qua Ollama) **KHÔNG** tự theo policy đó: đo trên 7 câu
    thật của smoke name-patch, nó trả `Cao Lei`, `núi Yantai`, `Yintai` — tức
    pinyin, không phải Hán-Việt. Sửa HẬU KỲ pinyin -> Hán-Việt bị loại: phải đoán
    một bảng âm, và mọi tên không có trong bảng sẽ bị "sửa" thành chữ khác.

Vì sao prompt glossary một mình không đủ, và vì sao vẫn phải giữ nó
    `prompts.system_prompt` đã liệt kê thuật ngữ, nhưng đó là một LỜI KHUYÊN:
    model vẫn chọn âm nó thích. Che chỗ thuật ngữ bằng một token rồi thay token
    bằng đúng chuỗi Việt của hàng glossary thì bản dịch của thuật ngữ KHÔNG còn do
    model chọn. Prompt vẫn phải giữ glossary — đó chính là thứ khiến model đặt
    token vào đúng chỗ ngữ pháp thay vì bỏ đi.

Vì sao token dạng `ZXQ{n}`
    Đã đo qua adapter THẬT, 7 câu trong một lô: cả ba kiểu token sống sót nguyên
    vẹn **6/6** lần. `ZXQ{n}` được chọn vì model giữ khoảng trắng tự nhiên quanh
    nó ("đèn cá của ZXQ1"), còn kiểu ngoặc (`[[T1]]`, `⟦T1⟧`) dính sát chữ xung
    quanh ("Đây là[[T1]]") — dính chữ thì việc thay token làm hỏng cả khoảng trắng
    của câu.

Vì sao ĐÁNH SỐ THEO THUẬT NGỮ, không theo lần xuất hiện
    Cùng một `Term` xuất hiện hai lần trong một câu phải ra **cùng một token**:
    token là đại diện cho thuật ngữ, không phải cho vị trí. Đánh số theo lần xuất
    hiện thì `曹磊 … 曹磊` thành `ZXQ1 … ZXQ2`, và mọi thống kê "token nào bị mất"
    đếm một cái tên hai lần.

Vì sao KHÔNG khôi phục bằng `str.replace` trần
    `ZXQ1` là tiền tố của `ZXQ10`/`ZXQ11`: thay từng chuỗi con thô thì token thứ
    10 biến thành "bản dịch của token 1" + "0". Vì vậy khôi phục khớp **theo ranh
    giới token** (`(?<![0-9A-Za-z]) … (?![0-9])`) và làm trong **MỘT** lượt
    `re.sub` có callback — một lượt thì không bao giờ đọc lại văn bản do chính nó
    sinh ra, nên một bản dịch tình cờ chứa chuỗi giống token không bị thay lần hai.

Vì sao cờ chỉ là CẢNH BÁO
    `token_lost` / `token_duplicated` / `token_unknown` / `token_collision_in_source`
    đều chỉ gắn vào QA: không chặn xuất bản, không thử lại bằng kiểu token khác.
    Hôm nay model vốn tự do ra pinyin, nên giữ nguyên văn của model không tệ hơn
    trạng thái trước khi có tính năng; biến nó thành cổng chặn là biến một tính
    năng cải thiện thành một chỗ tắc. Tần suất thật chưa biết, nên retry là phức
    tạp hoá trước khi có số — khi nào đo được tần suất cao thì mới thêm.

Vì sao chấp nhận classifier tiếng Việt trước token
    Model có thể tự thêm loại từ: `烟台山` -> "núi Yên Đài Sơn". Đọc được và không
    sai nghĩa, nên CHÍNH SÁCH LÀ CHẤP NHẬN — không cắt "núi" đi, và `Term` vẫn
    giữ nguyên dạng hiển thị đầy đủ (`Yên Đài Sơn`). Cắt nó là sửa lời của model
    dựa trên một phỏng đoán, đúng loại "sửa" mà pinyin hậu kỳ đã bị loại vì thế.

Hàm thuần: không I/O, không adapter, không phụ thuộc model. Toàn bộ quyết định
"thuật ngữ nào được bảo vệ" nằm ở `plan_terms`, để tầng gọi không phải tự lọc.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from app.domain.glossary_match import approved
from app.domain.models import Term

#: Tiền tố mặc định của token. Xem docstring đầu tệp: kiểu này giữ được khoảng
#: trắng tự nhiên quanh token (đo 6/6 trên 7 câu), khác hai kiểu ngoặc.
DEFAULT_PREFIX = "ZXQ"

#: Cờ do `restore` sinh ra, ghép với token thành chuỗi `"<cờ>:<token>"`. Tầng gọi
#: đọc phần TRƯỚC dấu `:` để gắn cờ QA lên segment; tên cờ ở đây là hợp đồng.
#:
#: CẢ BỐN cờ là CẢNH BÁO, KHÔNG chặn xuất bản và KHÔNG kích hoạt thử lại bằng
#: kiểu token khác. Lý do: (a) hôm nay model vốn ra pinyin, nên giữ nguyên văn của
#: model không tệ hơn trạng thái TRƯỚC khi có tính năng — chặn xuất bản sẽ biến
#: một tính năng cải thiện thành một cổng chặn; (b) tần suất thật chưa biết, nên
#: cơ chế thử lại là phức tạp hoá trước khi có số đo; (c) cờ đã hiện trong QA nên
#: người dùng vẫn thấy chỗ cần đọc lại. Khi nào đo được tần suất cao thì mới thêm
#: retry — và lúc đó con số này là chỗ bắt đầu.
TOKEN_LOST = "token_lost"
TOKEN_DUPLICATED = "token_duplicated"
TOKEN_UNKNOWN = "token_unknown"
#: Câu NGUỒN đã có sẵn chuỗi giống token: bảo vệ bị BỎ cho riêng câu đó (không
#: thể phân biệt token của ta với chữ có sẵn), câu vẫn được dịch bình thường.
TOKEN_COLLISION = "token_collision_in_source"

#: Một token là `tiền tố + số`, và số nằm ở CUỐI. Tách ngược từ khoá của mapping
#: nên module không cần biết tiền tố đã dùng (`protect` cho phép tham số).
_TOKEN_TAIL = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")

#: Ký tự Latin/số. Một token dán NGAY SAU chúng không phải ranh giới token: đó là
#: đuôi của một chuỗi dài hơn (`AZXQ1`), nên khôi phục không được đoán đó là token.
_LATIN = "0-9A-Za-z"


def plan_terms(terms: Sequence[Term], *, source_lang: str) -> list[Term]:
    """Thuật ngữ ĐƯỢC PHÉP đi vào đường bảo vệ: đã duyệt VÀ đúng ngôn ngữ nguồn.

    Hai phép lọc, không phải một:

    * `approved` — mục chưa duyệt là bản nháp của người dùng, không phải ràng
      buộc (spec §8.1). Bảo vệ bằng một bản nháp nghĩa là bản dịch bị ghim vào
      một chuỗi chưa ai xác nhận.
    * `lang` — cùng một chữ ở hai ngôn ngữ là hai danh tính. Port `list_terms`
      mặc định trả MỌI ngôn ngữ, nên lọc ở đây là chốt chặn thứ hai cho trường
      hợp bên gọi quên truyền `lang=`.
    """
    return [t for t in approved(list(terms)) if t.lang == source_lang]


def protect(text: str, terms: Sequence[Term], *,
            prefix: str = DEFAULT_PREFIX) -> tuple[str, dict[str, str]]:
    """Thay mọi lần xuất hiện của thuật ngữ trong `text` bằng token giữ chỗ.

    Trả `(văn bản đã token hoá, {token: bản dịch})`. Bản dịch lấy **nguyên văn**
    từ `Term.translation` — đây là cả điểm của module: chuỗi đó không do model
    sinh ra.

    Thứ tự xử lý là **thuật ngữ DÀI trước**: `小儿放纸鸢图` phải thắng `纸鸢`,
    nếu không thì vế ngắn chiếm mất phần đuôi của tên dài và tiêu đề tác phẩm bị
    cắt thành hai mảnh. Vùng đã bị một token chiếm thì không bao giờ bị token hoá
    lần nữa (mask theo từng ký tự), nên hai thuật ngữ lồng nhau không sinh ra hai
    token chồng lên nhau.

    Số hiệu là DUY NHẤT theo THUẬT NGỮ, không theo lần xuất hiện: cùng một cặp
    `(term, translation)` xuất hiện hai lần thì cả hai chỗ dùng CHUNG một token
    (xem "Vì sao ĐÁNH SỐ THEO THUẬT NGỮ" ở docstring đầu tệp).

    Bỏ qua (không ném): thuật ngữ rỗng, bản dịch rỗng, và thuật ngữ không xuất
    hiện. Chuỗi rỗng là chuỗi con của MỌI văn bản, nên nhận nó là nói mọi segment
    đều bị token hoá — cùng lý do `glossary_match.terms_in` bỏ qua nó.

    Ném `ValueError` khi `prefix` đã có trong `text` hoặc trong một `term`: token
    sinh ra sẽ trùng với chữ có sẵn, và `restore` không phân biệt được "token của
    ta" với "chữ của bản gốc" nên nó sẽ thay cả hai. Đó là lỗi của BÊN GỌI, nên nó
    ném ngay tại đây thay vì để `restore` đoán.
    """
    at = text.find(prefix)
    if at >= 0:
        raise ValueError(
            f"tiền tố {prefix!r} đã có sẵn trong văn bản nguồn (vị trí {at}): "
            f"token sinh ra sẽ trùng với chữ có sẵn và không khôi phục được"
        )
    for term in terms:
        if prefix in term.term:
            raise ValueError(
                f"tiền tố {prefix!r} đã có trong thuật ngữ {term.term!r}: "
                f"token sinh ra sẽ trùng với chữ có sẵn và không khôi phục được"
            )

    # Sắp xếp ỔN ĐỊNH (sorted của Python) nên hai thuật ngữ cùng độ dài giữ nguyên
    # thứ tự glossary — đầu ra phải TẤT ĐỊNH, cùng đầu vào cho cùng token.
    ordered = sorted(terms, key=lambda t: len(t.term), reverse=True)
    masked = [False] * len(text)
    spans: list[tuple[int, int, str]] = []
    token_of: dict[tuple[str, str], str] = {}
    mapping: dict[str, str] = {}
    for term in ordered:
        needle = term.term
        if not needle or not term.translation:
            continue
        start = 0
        while True:
            found = text.find(needle, start)
            if found < 0:
                break
            end = found + len(needle)
            # `any(masked[...])` chứ không `masked[found]`: một lần xuất hiện có
            # thể bắt đầu NGOÀI vùng đã chiếm nhưng chạm vào nó, và token hoá nửa
            # vùng đó là cắt đôi một token đang có.
            if not any(masked[found:end]):
                identity = (needle, term.translation)
                token = token_of.get(identity)
                if token is None:
                    token = f"{prefix}{len(token_of) + 1}"
                    token_of[identity] = token
                    mapping[token] = term.translation
                spans.append((found, end, token))
                for position in range(found, end):
                    masked[position] = True
            # `found + 1` chứ không `end`: lần xuất hiện TIẾP THEO có thể bắt đầu
            # ngay bên trong lần vừa rồi (thuật ngữ tự chồng), và nó vẫn phải được
            # xét — chỉ những vùng đã bị token chiếm mới bị bỏ.
            start = found + 1

    if not spans:
        return text, {}

    spans.sort()
    _guard_restorable(text, spans)
    parts: list[str] = []
    cursor = 0
    for found, end, token in spans:
        parts.append(text[cursor:found])
        parts.append(token)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), mapping


#: Ký tự ASCII là chữ hoặc số — đúng bộ mà ranh giới trái của `restore` chặn.
_ASCII_ALNUM = frozenset(
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")

#: Chữ số ASCII — đúng bộ mà ranh giới phải của `restore` chặn (`(?![0-9])`).
_ASCII_DIGITS = frozenset("0123456789")


def _guard_restorable(text: str, spans: Sequence[tuple[int, int, str]]) -> None:
    """Ném nếu một token sắp chèn sẽ KHÔNG khôi phục được vì hàng xóm của nó.

    Guard "tiền tố có sẵn" chỉ chặn trùng với chữ của bản gốc. Còn một lớp nữa:
    token sinh ra phải khớp được ĐÚNG ranh giới mà `restore` dùng, nếu không thì
    một `ZXQ1` thô nằm lại trong phụ đề. Ba hình dạng, cả ba đều đo được trên dữ
    liệu thật của repo này:

    * số dính NGAY SAU: `一平尺2000` (đúng cặp số liệu mà `name_patch` đã ghi
      trong docstring) ⇒ token `ZXQ1` + `2000` đọc thành token số 1 rồi "2000",
      hoặc tệ hơn là token số 12 nếu term đứng trước `2`;
    * chữ Latin/số dính NGAY TRƯỚC: `abc平尺` ⇒ `abcZXQ1` không khớp ranh giới
      trái, token thô còn nguyên;
    * hai thuật ngữ DÍNH nhau (`纸鸢曹磊`) ⇒ `ZXQ1ZXQ2`, token thứ hai bị chặn bởi
      chính chữ số của token thứ nhất.

    Cả ba đều là "câu này không che được", nên tầng gọi xử lý như va chạm: bỏ bảo
    vệ cho riêng câu đó và gắn cờ. Thà một câu phải dịch tay còn hơn một token thô
    trong phụ đề.
    """
    for index, (found, end, token) in enumerate(spans):
        if found > 0 and text[found - 1] in _ASCII_ALNUM:
            raise ValueError(
                f"token {token!r} sẽ dính vào chữ Latin/số đứng trước "
                f"({text[found - 1]!r}) nên không khôi phục được")
        if end < len(text) and text[end] in _ASCII_DIGITS:
            raise ValueError(
                f"token {token!r} sẽ dính vào chữ số đứng sau ({text[end]!r}) "
                f"nên không khôi phục được")
        if index and spans[index - 1][1] == found:
            raise ValueError(
                f"hai token {spans[index - 1][2]!r} và {token!r} dính nhau nên "
                f"token thứ hai không khôi phục được")


def _groups(mapping: Mapping[str, str]) -> dict[str, dict[int, str]]:
    """`{tiền tố: {số: token}}` tách ngược từ khoá của mapping.

    Nhóm theo tiền tố (không phải một tiền tố duy nhất) vì hai lần `protect` với
    hai tiền tố khác nhau có thể được gộp vào một mapping; xử lý theo nhóm thì
    chuyện đó không cần một nhánh riêng.
    """
    groups: dict[str, dict[int, str]] = {}
    for token in mapping:
        match = _TOKEN_TAIL.match(token)
        if match is None:
            continue
        groups.setdefault(match.group("prefix"), {})[int(match.group("number"))] = token
    return groups


def _token_like_pattern(prefix: str = DEFAULT_PREFIX) -> re.Pattern:
    """Chuỗi GIỐNG token ở bất kỳ đâu: dùng để phát hiện va chạm ở chữ NGUỒN.

    Không đòi ranh giới phải: đây là phép DÒ, và dò rộng tay chỉ làm ta bỏ bảo vệ
    ở một câu (an toàn), trong khi dò hẹp làm ta che lên chữ có sẵn (nguy hiểm).
    """
    return re.compile(rf"(?<![0-9A-Za-z]){re.escape(prefix)}\s*\d+", re.IGNORECASE)


def has_token_like(text: str, *, prefix: str = DEFAULT_PREFIX) -> bool:
    """`text` đã chứa sẵn chuỗi giống token chưa (`ZXQ1`, `zxq 12`)?

    Tầng gọi phải hỏi TRƯỚC khi `protect`: che một câu đã có `ZXQ1` thì `restore`
    không phân biệt được token của ta với chữ của bản gốc và sẽ thay cả hai.
    """
    return _token_like_pattern(prefix).search(text) is not None


def _strict_pattern(prefixes: Sequence[str]) -> re.Pattern:
    """MỘT pattern cho MỌI tiền tố: `ZXQ 3`, `zxq3`, `《ZXQ3》` đều khớp.

    Khoảng trắng tuỳ chọn giữa tiền tố và số là để chịu được việc model tách số
    (`ZXQ 1` — đã thấy kiểu này ở các model nhỏ). `re.IGNORECASE` để chịu được
    việc model hoa/thường hoá (`Zxq1`).

    Ranh giới PHẢI là `(?![0-9])` chứ không `\\b`: `ZXQ1` là tiền tố của `ZXQ10`,
    và `\\b` không phân biệt được `ZXQ1` với `ZXQ10` khi có chữ số theo sau. Chữ
    Việt (`của`) và chữ Hán (`的`) đều là ký tự WORD với `\\b`, nên `\\b` còn làm
    `ZXQ1của`/`ZXQ1的` KHÔNG khớp — một token thô nằm lại trong phụ đề, đúng thứ
    tính năng này sinh ra để tránh. `(?![0-9])` giữ nguyên bảo đảm của `\\b` về
    phía chữ số mà không có lỗ đó.
    """
    alternation = "|".join(re.escape(prefix) for prefix in prefixes)
    return re.compile(
        rf"(?<![{_LATIN}])({alternation})\s*(\d+)(?![0-9])", re.IGNORECASE)


def count_tokens(text: str, tokens: Mapping[str, str]) -> dict[str, int]:
    """Số lần mỗi token có mặt trong `text` — dùng trên bản ĐÃ CHE, trước khi dịch.

    Vì sao phải đếm trước: một thuật ngữ xuất hiện hai lần thì token của nó cũng
    có mặt hai lần trong câu NGUỒN, nên nếu `restore` coi "gặp hai lần" là model
    lặp token thì mọi câu lặp tên sẽ bị gắn cờ sai. Đếm ở đầu vào cho `restore` một
    con số để so, và cờ `token_duplicated` chỉ bật khi model viết NHIỀU HƠN nguồn.

    Đếm bằng ĐÚNG pattern của `restore`, nên con số này là "số lần `restore` sẽ
    thay" — hai bên không thể lệch nhau.
    """
    groups = _groups(tokens)
    if not groups:
        return {}
    pattern = _strict_pattern(sorted(groups))
    by_folded = {prefix.casefold(): numbers
                 for prefix, numbers in groups.items()}
    counts: dict[str, int] = {}
    for match in pattern.finditer(text):
        numbers = by_folded.get(match.group(1).casefold())
        token = numbers.get(int(match.group(2))) if numbers else None
        if token is not None:
            counts[token] = counts.get(token, 0) + 1
    return counts


def restore(text: str, mapping: Mapping[str, str], *,
            expected: Mapping[str, int] | None = None) -> tuple[str, list[str]]:
    """Thay token bằng bản dịch của nó; trả `(chữ đã khôi phục, vấn đề)`.

    Mỗi phần tử của danh sách vấn đề là `"<cờ>:<token>"`, với cờ là một trong
    `TOKEN_LOST` / `TOKEN_DUPLICATED` / `TOKEN_UNKNOWN`. Tầng gọi đọc phần trước
    dấu `:` để gắn đúng cờ QA lên segment — nó phải phân biệt được "model bỏ mất
    tên" với "model lặp tên", vì hai lỗi này cần hai cách sửa khác nhau.

    `expected` là số lần mỗi token CÓ trong bản đã che (`count_tokens` trước khi
    gọi engine). Có nó thì `token_duplicated` chỉ bật khi model viết nhiều hơn
    nguồn, và `token_lost` khi ít hơn. `None` (không biết nguồn) thì dùng luật thô:
    quá một lần là lặp, không lần nào là mất.

    Token LẠ (số không có trong map — model bịa số hoặc đổi số) được ĐỂ NGUYÊN VĂN
    và gắn `token_unknown`: bịa lại tên từ một con số không ánh xạ được là đúng
    kiểu đoán mà cả module này tránh.

    IDEMPOTENT cho token đã khôi phục: gọi lần hai trên chữ đã khôi phục trả lại
    đúng chữ đó và không báo token đó là mất (bản dịch của nó đang có mặt).

    MỘT LƯỢT `re.sub` DUY NHẤT, và đây là điều kiện đúng đắn chứ không phải chi
    tiết cài đặt: `re.sub` không bao giờ đọc lại văn bản do chính nó sinh ra, nên
    một `Term.translation` tình cờ chứa chuỗi GIỐNG token (ví dụ bản dịch
    "Tào Lôi 2 ZXQ1") không thể bị thay lần thứ hai. Một vòng lặp "thay từng
    token, số LỚN -> NHỎ" cũng qua được ca `ZXQ1`/`ZXQ10`, nhưng nó ĐỌC LẠI văn
    bản của chính mình ở mỗi vòng — đúng lớp rủi ro vừa nêu, nên nó đã bị bỏ.
    """
    if not mapping:
        return text, []

    issues: list[str] = []
    groups = _groups(mapping)
    if not groups:
        return text, [f"{TOKEN_LOST}:{token}" for token in sorted(mapping)]
    by_folded = {prefix.casefold(): numbers for prefix, numbers in groups.items()}
    counts: dict[str, int] = {}

    def _replace(match: re.Match) -> str:
        numbers = by_folded.get(match.group(1).casefold()) or {}
        token = numbers.get(int(match.group(2)))
        if token is None:
            issue = f"{TOKEN_UNKNOWN}:{match.group(0)}"
            if issue not in issues:
                issues.append(issue)
            return match.group(0)          # để NGUYÊN VĂN, không bịa tên
        counts[token] = counts.get(token, 0) + 1
        return mapping[token]

    out = _strict_pattern(sorted(groups)).sub(_replace, text)

    for token in sorted(mapping):
        rendering = mapping[token]
        found = counts.get(token, 0)
        if expected is None:
            if found > 1:
                issues.append(f"{TOKEN_DUPLICATED}:{token}")
            if found == 0 and (not rendering or rendering not in out):
                issues.append(f"{TOKEN_LOST}:{token}")
            continue
        want = expected.get(token, 0)
        if found > want:
            issues.append(f"{TOKEN_DUPLICATED}:{token}")
        elif found < want:
            issues.append(f"{TOKEN_LOST}:{token}")
    return out, issues


__all__ = [
    "DEFAULT_PREFIX",
    "TOKEN_COLLISION",
    "TOKEN_DUPLICATED",
    "TOKEN_LOST",
    "TOKEN_UNKNOWN",
    "count_tokens",
    "has_token_like",
    "plan_terms",
    "protect",
    "restore",
]
