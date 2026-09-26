"""Dựng prompt và parse phản hồi. Không cần model — nên đây là chỗ bắt lỗi rẻ nhất.

Ba failure mode thật của LLM: bọc JSON trong ```, thiếu id, JSON hỏng.
"""
import pytest

from app.adapters.mt.prompts import (PROMPT_VERSION, parse_batch_response,
                                     system_prompt, user_prompt)
from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term, Word


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text, speaker="S1")


def term(t: str, tr: str) -> Term:
    return Term(id=None, lang="zh", term=t, translation=tr, approved=True)


def test_prompt_version_exists_for_both_shipped_engines():
    assert PROMPT_VERSION["qwen2.5-3b"] and PROMPT_VERSION["opus-mt"]


def test_system_prompt_carries_glossary_pairs():
    p = system_prompt([term("rồng", "dragon")], target_lang="vi")
    assert "rồng" in p and "dragon" in p


def test_system_prompt_carries_the_target_language_it_was_given():
    """`target_lang` phải tới được system prompt, không chỉ user prompt.

    Bài trên luôn gọi `target_lang="vi"` — trùng giá trị mặc định của cả tầng
    gọi — nên một hiện thực ghim cứng "vi" vẫn xanh (đã đo: mutant thay
    `{target_lang}` bằng `vi` sống sót, 12 passed) trong khi mọi bản dịch sang
    ngôn ngữ khác bị chỉ dẫn sai một cách âm thầm. Đây là cái giá của việc chỉ
    có MỘT giá trị được kiểm: dùng giá trị không trùng mặc định.
    """
    p = system_prompt([], target_lang="ja")
    assert "ja" in p and "vi" not in p


def test_system_prompt_without_glossary_says_nothing_about_terms():
    p = system_prompt([], target_lang="vi")
    assert "rồng" not in p and "glossary" not in p.lower()


def test_user_prompt_contains_every_id_and_text():
    p = user_prompt([seg(1, "a"), seg(2, "b")], source_lang="zh", target_lang="vi")
    assert '"i": 1' in p and '"i": 2' in p and "a" in p and "b" in p


def test_parse_maps_text_onto_input_timings():
    batch = [seg(1, "a"), seg(2, "b")]
    raw = '{"translations": [{"i": 1, "text": "A"}, {"i": 2, "text": "B"}]}'
    out = parse_batch_response(raw, batch)
    assert [s.text for s in out] == ["A", "B"]
    assert [s.i for s in out] == [1, 2]
    assert out[0].start == 1.0 and out[0].speaker == "S1", "timestamp/người nói phải lấy từ đầu vào"


def test_parse_strips_markdown_code_fences():
    batch = [seg(1, "a")]
    raw = '```json\n{"translations": [{"i": 1, "text": "A"}]}\n```'
    assert parse_batch_response(raw, batch)[0].text == "A"


def test_parse_raises_alignment_when_an_id_is_missing():
    batch = [seg(1, "a"), seg(2, "b")]
    raw = '{"translations": [{"i": 1, "text": "A"}]}'
    with pytest.raises(AlignmentProblem):
        parse_batch_response(raw, batch)


def test_parse_raises_alignment_when_an_id_is_alien():
    with pytest.raises(AlignmentProblem):
        parse_batch_response('{"translations": [{"i": 9, "text": "A"}]}', [seg(1, "a")])


def test_parse_raises_valueerror_on_broken_json():
    with pytest.raises(ValueError):
        parse_batch_response("không phải json", [seg(1, "a")])


def test_parse_raises_valueerror_when_translations_key_missing():
    with pytest.raises(ValueError):
        parse_batch_response('{"ket_qua": []}', [seg(1, "a")])


def test_parse_accepts_reordered_items_and_restores_input_order():
    batch = [seg(1, "a"), seg(2, "b")]
    raw = '{"translations": [{"i": 2, "text": "B"}, {"i": 1, "text": "A"}]}'
    out = parse_batch_response(raw, batch)
    assert [s.i for s in out] == [1, 2] and [s.text for s in out] == ["A", "B"]


def test_parse_changes_only_text_across_all_thirteen_segment_fields():
    """Parse chỉ được đổi `text`, không được dựng lại `Segment` bằng tay.

    `seg()` ở trên chỉ dựng 4/13 field, nên một hiện thực chép tay
    `Segment(i=..., start=..., end=..., text=..., words=..., speaker=...)` vẫn
    xanh hết các bài kia (đã đo: mutant đó chỉ chết ở CHÍNH bài này, 1 failed /
    11 passed) trong khi nuốt `emotion`,
    `events`, `avg_logprob`, `no_speech_prob`, `suspect`, `t`, `qa` — đúng lỗi đã
    bị bắt ở review Task 7. Dựng ĐỦ 13 field rồi so `to_json()` đầy đủ: một bản
    *bịa* thêm field cũng chết ở đây, không chỉ bản làm mất.
    """
    words = [Word(w="a", s=3.0, e=3.4)]
    src = Segment(i=7, start=3.0, end=4.0, text="a", words=words, emotion="neutral",
                  events=["music"], speaker="S1", avg_logprob=-0.31,
                  no_speech_prob=0.02, suspect=True, t="2026-09-26T00:00:00",
                  qa=["length:1=4.25"])
    out = parse_batch_response('{"translations": [{"i": 7, "text": "A"}]}', [src])
    assert out[0].to_json() == {**src.to_json(), "text": "A"}
    assert out[0].words is words, "word timestamp phải giữ nguyên tham chiếu"
