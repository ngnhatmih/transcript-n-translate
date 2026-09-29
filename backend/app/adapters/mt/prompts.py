"""Dựng prompt cho engine LLM và parse phản hồi về `Segment`.

Dữ liệu thuần: không import model, không gọi mạng ⇒ test được ở mọi máy. Mọi thứ
có thể sai mà không cần model đều phải bị bắt ở đây, vì đây là chỗ RẺ NHẤT trong
cả giai đoạn để bắt lỗi mà engine thật sinh ra.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace

from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term

#: Phiên bản prompt theo engine. Ghi vào `translations.prompt_version` và
#: `llm_calls.prompt_version`, nên đổi prompt PHẢI đổi chuỗi này — nếu không thì
#: không phân biệt được bản dịch cũ và mới khi prompt thay đổi.
#:
#: `p2` (lượt này): thêm câu CẤM chép nguyên văn vào `system_prompt`. Lý do đo
#: được ở `_report_/real-pipeline-fix-report.md` §B: với `p1`, `qwen2.5-3b` chép
#: nguyên chữ Trung cho ĐÚNG chuỗi prompt đó (A: 6/6, seed cố định 3/3, model
#: vừa nạp lại 3/3, bỏ `format:json` 2/2) và chỉ dịch khi prompt đổi; thêm MỘT
#: câu là 5/5 ra tiếng Việt. Không đổi chuỗi này thì các bản dịch echo cũ (`p1`)
#: nằm cùng nhãn với bản dịch mới — đúng thứ dòng này tồn tại để chặn.
PROMPT_VERSION: dict[str, str] = {
    "qwen2.5-3b": "qwen-json-p2",
    "qwen2.5-7b": "qwen-json-p2",
    "opus-mt": "raw-p1",
}

#: Model thật hay bọc JSON trong ```json ... ``` — đây là failure mode phổ biến
#: chứ không phải đầu vào bất thường, nên nó phải parse được.
_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")

#: Tên khoá TƯƠNG ĐƯƠNG cho hai trường của một mục. Đọc theo thứ tự này, nên tên
#: đầu tiên thắng khi model trả nhiều tên cùng lúc.
#:
#: Vì sao cần (A3, đo được): model trả `{"i": 2, "Text": "..."}` — chữ T hoa —
#: cho MỘT trong 8 mục, 7 mục kia là tiếng Việt tốt, và bản cũ ném
#: `ValueError: mục thiếu 'i' hoặc 'text' không phải chuỗi` rồi **vứt cả 8 câu**.
#: Nặng hơn: lượt gọi ĐẦU TIÊN sau khi sửa prompt (xem `system_prompt`) cũng trả
#: 8/8 tiếng Việt kèm MỘT khoá `"Text"` — tức phép nới này là thứ quyết định cả
#: lô được GIỮ hay bị vứt, không phải một chi tiết cú pháp.
#:
#: Nới tới đâu là cố ý: chỉ những tên THẬT SỰ TƯƠNG ĐƯƠNG. `txt`, `nội dung`,
#: hay một khoá bất kỳ KHÔNG được nhận — nhận chúng là biến "engine trả sai hợp
#: đồng" thành "ta đoán ý engine", và một `null` sẽ thành phụ đề.
_I_KEYS = ("i", "index", "id")
_TEXT_KEYS = ("text", "translation")



def system_prompt(glossary: list[Term], *, target_lang: str) -> str:
    """Vai trò + quy tắc + glossary. Rỗng glossary thì KHÔNG nhắc tới thuật ngữ.

    Nhắc tới glossary khi không có thuật ngữ nào là mời model bịa ra ràng buộc.

    Câu CUỐI là bản vá lỗi DỊCH IM LẶNG (xem `PROMPT_VERSION`: `p1` -> `p2`). Ba
    dòng đầu chỉ nói VAI và ĐỊNH DẠNG; không dòng nào nói "đầu ra phải ở ngôn ngữ
    đích", mà `user_prompt` thì kết thúc bằng một mảng JSON toàn chữ Trung — với
    `qwen2.5:3b` (Q4), continuation rẻ nhất là chép lại chính mảng đó. Đo được:
    `p1` echo 6/6, `p2` ra tiếng Việt 5/5, cùng batch, cùng `temperature=0.1`.

    Câu này để CUỐI (không phải ngay sau dòng đầu) vì đó ĐÚNG là vị trí đã đo:
    đặt giữa prompt là một biến thể CHƯA đo, và một phép sửa prompt không có số
    đo thì không được phép tự nhận là đã sửa.
    """
    lines = [
        f"Bạn là dịch giả chuyên nghiệp sang {target_lang}.",
        "Dịch sát nghĩa, giữ nguyên văn phong và mức trang trọng của bản gốc.",
        "Trả về DUY NHẤT một đối tượng JSON, không thêm chữ nào khác.",
    ]
    if glossary:
        lines.append("Bắt buộc dùng đúng các thuật ngữ sau:")
        lines.extend(f"- {t.term} => {t.translation}" for t in glossary)
    lines.append(
        f"TUYỆT ĐỐI không sao chép nguyên văn bản gốc: mỗi 'text' phải là câu "
        f"{target_lang}, không được để lại chữ của bản gốc.")
    return "\n".join(lines)



def user_prompt(batch: list[Segment], *, source_lang: str, target_lang: str) -> str:
    items = [{"i": s.i, "text": s.text} for s in batch]
    return (
        f"Dịch từng mục từ {source_lang} sang {target_lang}.\n"
        "Giữ nguyên `i` của từng mục và trả đúng bấy nhiêu mục.\n"
        'Định dạng: {"translations": [{"i": <số>, "text": "<bản dịch>"}]}\n'
        f"Dữ liệu: {json.dumps(items, ensure_ascii=False)}"
    )


def _normalised_keys(item: dict) -> dict:
    """Khoá của một đối tượng JSON, đã hạ chữ thường và cắt khoảng trắng.

    Hai LƯỢT, và thứ tự lượt là hợp đồng: lượt 1 chỉ nhận khoá viết ĐÚNG chữ
    thường (chuẩn), lượt 2 `setdefault` cho các cách viết khác. Nhờ vậy
    `{"Text": "SAI", "text": "đúng"}` luôn cho `"đúng"` bất kể model đặt khoá nào
    trước — chọn theo thứ tự dict là chọn theo thứ tự model sinh ra, tức không
    tất định giữa hai lần chạy cùng prompt.
    """
    out: dict = {}
    for key, value in item.items():
        if key == key.strip().lower():
            out[key] = value
    for key, value in item.items():
        out.setdefault(key.strip().lower(), value)
    return out


def _pick(item: dict, names: tuple[str, ...]) -> tuple[bool, object]:
    """`(có mặt, giá trị)` của tên khoá ĐẦU TIÊN trong `names` xuất hiện.

    `item` phải đã qua `_normalised_keys`; `names` là các tên đã hạ chữ thường.
    """
    for name in names:
        if name in item:
            return True, item[name]
    return False, None


def parse_batch_response(raw: str, batch: list[Segment]) -> list[Segment]:
    """Ghép bản dịch vào ĐÚNG segment đầu vào, giữ nguyên timestamp/người nói.

    Đây là chỗ DUY NHẤT biến phản hồi engine thành `Segment`, nên mọi lệch
    alignment phải ném ở đây: trả về một list ngắn hơn là đúng kiểu thất bại âm
    thầm làm phụ đề lệch chỗ mà không có triệu chứng nào.

    Khoá được đọc KHÔNG phân biệt hoa/thường và chấp nhận tên tương đương
    (`_I_KEYS`, `_TEXT_KEYS`) — lý do đo được ở docstring của hai hằng đó. Kiểu
    của GIÁ TRỊ thì vẫn nghiêm: `text` không phải chuỗi là `ValueError`, không
    bao giờ được `str()` hoá thành phụ đề.
    """
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"engine không trả JSON hợp lệ: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON thiếu khoá 'translations' hoặc sai kiểu")
    top = _normalised_keys(data)
    if not isinstance(top.get("translations"), list):
        raise ValueError("JSON thiếu khoá 'translations' hoặc sai kiểu")

    got: dict[int, str] = {}
    for item in top["translations"]:
        if not isinstance(item, dict):
            raise ValueError(f"mục không phải đối tượng JSON: {item!r}")
        fields = _normalised_keys(item)
        has_i, raw_i = _pick(fields, _I_KEYS)
        _has_text, raw_text = _pick(fields, _TEXT_KEYS)
        if not has_i or not isinstance(raw_text, str):
            # Vẫn giữ ĐÚNG câu chữ cũ: nó là hợp đồng grep được của tầng gọi.
            raise ValueError(f"mục thiếu 'i' hoặc 'text' không phải chuỗi: {item!r}")
        try:
            key = int(raw_i)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'i' không phải số nguyên: {raw_i!r}") from exc
        got[key] = raw_text

    expected_ids = [s.i for s in batch]
    # ĐẾM số mục, không chỉ so TẬP id: `got` là dict nên id trùng bị nuốt trước khi
    # so sánh, và một mục thừa là dấu hiệu engine lẫn lộn — Task 11 phải thử lại cả
    # lô thay vì âm thầm nhận bản dịch thứ hai của cùng một id.
    if len(top["translations"]) != len(batch):
        raise AlignmentProblem(expected_ids, sorted(got),
                               f"engine trả {len(top['translations'])} mục, cần {len(batch)}")

    if sorted(got) != sorted(expected_ids):
        raise AlignmentProblem(expected_ids, sorted(got),
                               f"engine trả id {sorted(got)}, cần {sorted(expected_ids)}")

    # Duyệt theo batch để thứ tự đầu ra LUÔN bằng thứ tự đầu vào, kể cả khi model
    # trả mục xáo trộn.
    #
    # `replace` chứ KHÔNG dựng `Segment(...)` bằng tay: dựng tay chỉ chép 6/13
    # field và nuốt `emotion`, `events`, `avg_logprob`, `no_speech_prob`,
    # `suspect`, `t`, `qa` (đúng lỗi đã bị bắt ở review Task 7). Dịch chỉ được
    # đổi `text`; mọi thứ khác — kể cả `words` — là dữ liệu của bản gốc.
    return [replace(s, text=got[s.i]) for s in batch]
