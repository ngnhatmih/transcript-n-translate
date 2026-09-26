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
PROMPT_VERSION: dict[str, str] = {
    "qwen2.5-3b": "qwen-json-p1",
    "qwen2.5-7b": "qwen-json-p1",
    "opus-mt": "raw-p1",
}

#: Model thật hay bọc JSON trong ```json ... ``` — đây là failure mode phổ biến
#: chứ không phải đầu vào bất thường, nên nó phải parse được.
_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")


def system_prompt(glossary: list[Term], *, target_lang: str) -> str:
    """Vai trò + quy tắc + glossary. Rỗng glossary thì KHÔNG nhắc tới thuật ngữ.

    Nhắc tới glossary khi không có thuật ngữ nào là mời model bịa ra ràng buộc.
    """
    lines = [
        f"Bạn là dịch giả chuyên nghiệp sang {target_lang}.",
        "Dịch sát nghĩa, giữ nguyên văn phong và mức trang trọng của bản gốc.",
        "Trả về DUY NHẤT một đối tượng JSON, không thêm chữ nào khác.",
    ]
    if glossary:
        lines.append("Bắt buộc dùng đúng các thuật ngữ sau:")
        lines.extend(f"- {t.term} => {t.translation}" for t in glossary)
    return "\n".join(lines)


def user_prompt(batch: list[Segment], *, source_lang: str, target_lang: str) -> str:
    items = [{"i": s.i, "text": s.text} for s in batch]
    return (
        f"Dịch từng mục từ {source_lang} sang {target_lang}.\n"
        "Giữ nguyên `i` của từng mục và trả đúng bấy nhiêu mục.\n"
        'Định dạng: {"translations": [{"i": <số>, "text": "<bản dịch>"}]}\n'
        f"Dữ liệu: {json.dumps(items, ensure_ascii=False)}"
    )


def parse_batch_response(raw: str, batch: list[Segment]) -> list[Segment]:
    """Ghép bản dịch vào ĐÚNG segment đầu vào, giữ nguyên timestamp/người nói.

    Đây là chỗ DUY NHẤT biến phản hồi engine thành `Segment`, nên mọi lệch
    alignment phải ném ở đây: trả về một list ngắn hơn là đúng kiểu thất bại âm
    thầm làm phụ đề lệch chỗ mà không có triệu chứng nào.
    """
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"engine không trả JSON hợp lệ: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("translations"), list):
        raise ValueError("JSON thiếu khoá 'translations' hoặc sai kiểu")

    got: dict[int, str] = {}
    for item in data["translations"]:
        if not isinstance(item, dict) or "i" not in item or not isinstance(item.get("text"), str):
            raise ValueError(f"mục thiếu 'i' hoặc 'text' không phải chuỗi: {item!r}")
        try:
            key = int(item["i"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'i' không phải số nguyên: {item['i']!r}") from exc
        got[key] = item["text"]

    expected_ids = [s.i for s in batch]
    # ĐẾM số mục, không chỉ so TẬP id: `got` là dict nên id trùng bị nuốt trước khi
    # so sánh, và một mục thừa là dấu hiệu engine lẫn lộn — Task 11 phải thử lại cả
    # lô thay vì âm thầm nhận bản dịch thứ hai của cùng một id.
    if len(data["translations"]) != len(batch):
        raise AlignmentProblem(expected_ids, sorted(got),
                               f"engine trả {len(data['translations'])} mục, cần {len(batch)}")
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
