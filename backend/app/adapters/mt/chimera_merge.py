"""Lượt PHA của Chimera: CÙNG một model, KHÁC hình dạng prompt.

Vì sao là một adapter riêng thay vì một cờ trong `OllamaMtEngine`: lượt pha KHÔNG
dịch `batch` — nó đọc `opts.merge_candidates` và gộp chúng lại. Nhét hai việc khác
nhau vào một `translate()` là biến một hàm có một hợp đồng rõ thành một hàm có hai
hợp đồng, và mọi người gọi nó sau này phải nhớ mình đang ở nhánh nào.

Vì sao vẫn ĐI QUA `OllamaMtEngine.chat`: lượt pha là một lần CHẠM ENGINE có tiêu
token và tiêu thời gian. Nó phải được đo và phải được đếm như mọi lượt khác
(spec §4.2), và `TranslateHandler._translate_batch` chỉ đếm được những lời gọi đi
qua `MtEngine.translate` của nó. Lớp này cài ĐÚNG hợp đồng đó, nên lượt pha thừa
hưởng nguyên chính sách alignment + retry + ghi `llm_calls` mà không cần một dòng
mới nào ở handler.

`release()` uỷ quyền cho engine gốc: model nằm trong VRAM của Ollama, không phải
của lớp này, và hai lệnh đổ cho cùng một model là một lệnh thừa.
"""
from __future__ import annotations

from app.adapters.mt.ollama_mt import OllamaMtEngine
from app.adapters.mt.prompts import (MERGE_PROMPT_VERSION, merge_system_prompt,
                                     merge_user_prompt, parse_batch_response)
from app.domain.models import Segment, Term
from app.domain.mt import MtOpts

#: Thấp, cùng lý do với lượt dịch: đây là GỘP bản đã có, không phải sáng tác.
#: Nhiệt độ của lượt pha KHÔNG lấy từ ứng viên mỏ neo — mỏ neo là dữ liệu ĐẦU VÀO
#: của lượt pha, không phải cấu hình của nó.
MERGE_TEMPERATURE = 0.1


class OllamaMergeEngine:
    """Hiện thực `MtEngine` cho lượt pha, trên một `OllamaMtEngine` đã dựng."""

    def __init__(self, base: OllamaMtEngine, *, engine_id: str) -> None:
        self._base = base
        self._engine_id = engine_id

    @property
    def engine_id(self) -> str:
        return self._engine_id

    @property
    def model_ref(self) -> str:
        """Tag model THẬT gửi cho Ollama — giá trị ghi vào `llm_calls.model_ref`."""
        return self._base.model_ref

    @property
    def prompt_version(self) -> str:
        return MERGE_PROMPT_VERSION

    @property
    def last_stats(self):
        return self._base.last_stats

    def supports_glossary(self) -> bool:
        return self._base.supports_glossary()

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        """Gộp N ứng viên trong `opts.merge_candidates` thành MỘT bản cho `batch`.

        Thiếu `merge_candidates` là LỖI LẬP TRÌNH, không phải dữ liệu xấu: không
        có ứng viên nào thì không có gì để pha, và im lặng trả về `batch` (bản
        NGUỒN) sẽ biến lượt pha hỏng thành một bản dịch là chữ Hán.
        """
        if not batch:
            return []
        candidates = opts.merge_candidates
        if not candidates:
            raise ValueError(
                "lượt pha Chimera cần `opts.merge_candidates`, nhận rỗng")
        content = self._base.chat(
            merge_system_prompt(glossary if self.supports_glossary() else [],
                                target_lang=opts.target_lang,
                                run_count=len(candidates)),
            merge_user_prompt(batch, candidates, anchor=opts.merge_anchor,
                              source_lang=opts.source_lang,
                              target_lang=opts.target_lang),
            temperature=MERGE_TEMPERATURE)
        return parse_batch_response(content, batch)

    def release(self) -> None:
        self._base.release()
