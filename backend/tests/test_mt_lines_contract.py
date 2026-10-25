"""Hợp đồng đầu ra `lines`: prompt và parser.

Vì sao có hợp đồng thứ hai (số đo, không phải sở thích): hợp đồng JSON của
`parse_batch_response` được **Ollama** bảo đảm bằng grammar-constrained decoding
(`format: "json"`), không phải model 7B tự làm được. Cùng `hy-mt`, cùng clip, cùng
lô 30, qua một endpoint OpenAI-compatible (Ollama `/v1`, tức KHÔNG có `format:
"json"`) thì model trả JSON hỏng cú pháp ở 5/33 lời gọi, và hỏng cả ở lô 1.
Artifact: `data/experiments/accuracy-pipelines/20261025-spike-openai-mt/`.

Ba bất biến được ghim ở đây, vì mỗi cái là một cách làm hỏng phụ đề trong im lặng:
thiếu dòng (trả list ngắn hơn), id lạ, và dòng không mang id nằm GIỮA khối bản
dịch (model xuống dòng giữa câu → bỏ dòng sau là mất nửa câu mà số dòng vẫn đủ).
"""
import pytest

from app.adapters.mt.prompts import (parse_lines_response, system_prompt,
                                     system_prompt_lines, user_prompt_lines)
from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term


def make(i: int, text: str = "nguồn") -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text, speaker="S1")


def batch(*ids: int) -> list[Segment]:
    return [make(i) for i in ids]


# -- đường hạnh phúc ---------------------------------------------------------
def test_tab_separated_lines_parse_in_order():
    out = parse_lines_response("7\tdịch bảy\n8\tdịch tám\n", batch(7, 8))
    assert [s.text for s in out] == ["dịch bảy", "dịch tám"]


def test_output_follows_input_order_even_when_model_reverses():
    out = parse_lines_response("8\ttám\n7\tbảy", batch(7, 8))
    assert [s.i for s in out] == [7, 8]
    assert [s.text for s in out] == ["bảy", "tám"]


@pytest.mark.parametrize("raw", [
    "7\tdịch bảy",
    "7|dịch bảy",
    "7: dịch bảy",
    "7. dịch bảy",
    "[7] dịch bảy",
    "  [7]  - dịch bảy  ",
    "7\t\tdịch bảy",
])
def test_separator_and_bracket_forms_are_tolerated(raw: str):
    """Những dạng dưới đây là thứ model THẬT trả thay cho TAB, không phải đầu vào
    bất thường: nới ở đây không làm yếu alignment, vì số dòng và tập id vẫn bị đòi
    đúng tuyệt đối."""
    assert parse_lines_response(raw, batch(7))[0].text == "dịch bảy"


def test_leading_prose_before_the_block_is_ignored():
    raw = "Dưới đây là bản dịch:\n7\tdịch bảy\n"
    assert parse_lines_response(raw, batch(7))[0].text == "dịch bảy"


def test_code_fence_is_stripped():
    raw = "```\n7\tdịch bảy\n```"
    assert parse_lines_response(raw, batch(7))[0].text == "dịch bảy"


def test_every_field_that_translation_does_not_own_is_preserved():
    """Dịch chỉ đổi `text`. Dựng `Segment(...)` bằng tay làm rơi 7/13 trường — lỗi
    đã xảy ra hai lần trong dự án — nên parser phải `replace` trên đầu vào."""
    src = Segment(i=3, start=3.0, end=4.0, text="nguồn", speaker="S2",
                  emotion="angry", events=["music"], avg_logprob=-0.5,
                  no_speech_prob=0.1, suspect=True, t="orig", qa=["check"])
    out = parse_lines_response("3\tvi", [src])[0]
    assert out.text == "vi"
    assert (out.i, out.start, out.end, out.speaker, out.emotion, out.events,
            out.avg_logprob, out.no_speech_prob, out.suspect, out.t,
            out.qa) == (3, 3.0, 4.0, "S2", "angry", ["music"], -0.5, 0.1,
                        True, "orig", ["check"])


# -- lệch alignment: phải ồn ------------------------------------------------
def test_missing_line_is_an_alignment_problem_not_a_short_list():
    with pytest.raises(AlignmentProblem):
        parse_lines_response("7\tbảy\n", batch(7, 8))


def test_extra_line_is_an_alignment_problem():
    with pytest.raises(AlignmentProblem):
        parse_lines_response("7\tbảy\n8\ttám\n9\tchín\n", batch(7, 8))


def test_unknown_id_is_an_alignment_problem():
    with pytest.raises(AlignmentProblem):
        parse_lines_response("7\tbảy\n99\tlạ\n", batch(7, 8))


def test_duplicate_id_is_an_error():
    """Hai bản dịch cho cùng một mục: nhận cái sau là chọn theo thứ tự model sinh
    ra, tức không tất định giữa hai lần chạy cùng prompt."""
    with pytest.raises(ValueError):
        parse_lines_response("7\tmột\n7\thai\n", batch(7))


def test_id_without_text_is_an_error():
    with pytest.raises(ValueError):
        parse_lines_response("7\tdịch bảy\n8\t\n", batch(7, 8))


def test_a_prose_line_AFTER_the_block_is_an_error_not_a_silent_drop():
    """Model xuống dòng giữa câu rồi viết tiếp dòng sau. Nếu ta bỏ dòng đó thì bản
    dịch mất nửa câu mà số dòng vẫn 'đủ' — đúng kiểu thất bại không triệu chứng."""
    with pytest.raises(ValueError):
        parse_lines_response("7\tdòng một\nphần còn lại của câu\n", batch(7))


def test_empty_response_is_an_alignment_problem():
    with pytest.raises(AlignmentProblem):
        parse_lines_response("", batch(7))


# -- prompt của hợp đồng `lines` -------------------------------------------
def test_lines_system_prompt_asks_for_lines_and_never_mentions_json():
    text = system_prompt_lines([], target_lang="vi")
    assert "dòng" in text
    assert "JSON" not in text
    assert "sao chép nguyên văn" in text      # câu cấm chép vẫn phải có


def test_lines_and_json_system_prompts_differ_in_exactly_one_line():
    """Hai hợp đồng là hai biến số, không phải hai prompt tự do: phần vai và câu
    cấm chép phải giống nhau từng dòng, chỉ dòng định dạng khác."""
    json_lines = system_prompt([], target_lang="vi").splitlines()
    line_lines = system_prompt_lines([], target_lang="vi").splitlines()
    assert len(json_lines) == len(line_lines)
    diff = [(a, b) for a, b in zip(json_lines, line_lines) if a != b]
    assert len(diff) == 1
    assert "JSON" in diff[0][0] and "dòng" in diff[0][1]


def test_lines_user_prompt_carries_id_and_source_on_one_line():
    text = user_prompt_lines(batch(7, 8), source_lang="zh", target_lang="vi")
    assert "7\tnguồn" in text
    assert "8\tnguồn" in text
    assert "TAB" in text
    assert "JSON" not in text


def test_glossary_reaches_the_lines_system_prompt():
    term = Term(id="t1", lang="zh", term="烟台山",
                translation="Yên Đài Sơn")
    text = system_prompt_lines([term], target_lang="vi")
    assert "烟台山 => Yên Đài Sơn" in text


def test_unknown_contract_is_loud():
    """Một hợp đồng không tồn tại mà vẫn chạy sẽ sinh artifact mang nhãn sai."""
    from app.adapters.mt.prompts import _role_lines
    with pytest.raises(ValueError):
        _role_lines("vi", contract="yaml")
