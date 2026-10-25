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


# --------------------------------------------------------------------------
# Sửa lỗi DỊCH IM LẶNG (echo): câu CẤM chép nguyên văn phải có mặt, và phải
# theo `target_lang`.
#
# Số đo ở `_realpipe2/echo_matrix.json` + `prompt_candidates.json`:
# prompt cũ (`p1`), cùng batch 8 câu, cùng `temperature=0.1`, model ấm:
#   * lặp 6 lần           -> ECHO 6/6
#   * seed=7 cố định      -> ECHO 3/3
#   * model vừa nạp lại   -> ECHO 3/3  (nên "vừa nạp lại" KHÔNG phải nguyên nhân)
#   * prompt cache HIT    -> ECHO (cache cũng KHÔNG phải nguyên nhân)
#   * bỏ `format:json`    -> ECHO 2/2
# Thêm ĐÚNG một câu vào cuối `system_prompt` -> tiếng Việt 5/5, 0 echo.
# Không có bài ghim này thì lần sau ai đó gỡ câu đó ra và lỗi quay lại trong im
# lặng — đúng kiểu hỏng mà nó tồn tại để chặn.
# --------------------------------------------------------------------------

def test_system_prompt_forbids_copying_the_source_verbatim():
    p = system_prompt([], target_lang="vi")
    assert "không sao chép" in p.lower(), (
        f"thiếu câu cấm chép nguyên văn (lỗi echo quay lại): {p!r}"
    )
    assert "không được để lại chữ của bản gốc" in p.lower(), p


def test_the_no_copy_rule_carries_the_target_language_it_was_given():
    """Câu mới cũng phải nhận `target_lang`, không được ghim cứng "vi"."""
    p = system_prompt([], target_lang="ja")
    assert "ja" in p and "vi" not in p, p


def test_the_prompt_change_bumped_the_prompt_version():
    """Luật của chính tệp này: đổi prompt PHẢI đổi `PROMPT_VERSION`.

    Không bump thì bản dịch echo cũ (`p1`) và bản dịch mới (`p2`) mang cùng một
    nhãn, và `translations.prompt_version` — dấu vết DUY NHẤT để phân biệt hai
    loại — trở thành vô nghĩa.
    """
    assert PROMPT_VERSION["qwen2.5-3b"] == "qwen-json-p2"
    assert PROMPT_VERSION["qwen2.5-7b"] == "qwen-json-p2"
    assert PROMPT_VERSION["opus-mt"] == "raw-p1", (
        "opus-mt không đổi prompt thì không được đổi nhãn"
    )



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


def test_parse_raises_alignment_when_the_reply_has_more_items_than_the_batch():
    """Phải ĐẾM số mục, không chỉ so tập id (review Task 8, I-1).

    `got` là dict nên id trùng bị nuốt TRƯỚC khi so sánh: 3 mục cho 2 segment,
    id `[1, 1, 2]`, vẫn qua được `sorted(got) != sorted(expected_ids)` và trả về
    `['B', 'C']` — không lỗi, không log, Task 11 không có cớ thử lại. Mutant thêm
    đúng dòng đếm này từng sống sót với 13 passed, nên bài này ghim nó.
    """
    batch = [seg(1, "a"), seg(2, "b")]
    raw = '{"translations": [{"i": 1, "text": "A"}, {"i": 1, "text": "B"}, {"i": 2, "text": "C"}]}'
    with pytest.raises(AlignmentProblem):
        parse_batch_response(raw, batch)


def test_parse_raises_valueerror_when_text_is_not_a_string():
    """`str()` hoá `None` thành phụ đề `"None"` (review Task 8, I-2).

    Chỉ kiểm tra khoá `text` CÓ mặt là không đủ: `null` thành chuỗi `"None"`,
    dict thành `repr` `"{'vi': 'A'}"` — cả hai đều là nội dung phụ đề trông hợp
    lệ, id vẫn khớp nên không tầng nào phía sau phát hiện được.
    """
    for bad in ('{"translations": [{"i": 1, "text": null}]}',
                '{"translations": [{"i": 1, "text": {"vi": "A"}}]}',
                '{"translations": [{"i": 1, "text": 123}]}'):
        with pytest.raises(ValueError):
            parse_batch_response(bad, [seg(1, "a")])


# --------------------------------------------------------------------------
# A3: đọc khoá KHÔNG phân biệt hoa/thường (và vài khoá tương đương), nhưng
# KHÔNG nới tới mức nhận rác.
#
# ĐO ĐƯỢC: `qwen2.5-3b` trả `{"i": 2, "Text": "..."}` — chữ T hoa — cho MỘT
# trong 8 mục, trong khi 7 mục kia là tiếng Việt tốt. Bản cũ ném
# `ValueError: mục thiếu 'i' hoặc 'text' không phải chuỗi` và **vứt cả 8 câu**.
# Ở lượt này đo lại được điều đắt hơn: lượt gọi ĐẦU TIÊN sau khi sửa prompt
# (xem `system_prompt`) cũng trả về  8/8 tiếng Việt kèm MỘT khoá `"Text"` — tức
# A3 chính là thứ quyết định lô đó được giữ hay bị vứt.
# --------------------------------------------------------------------------

def test_parse_accepts_a_capitalised_text_key_on_one_item():
    """A3 RED TRƯỚC: 7 câu tiếng Việt tốt + 1 khoá `"Text"` -> mất CẢ lô."""
    batch = [seg(1, "一"), seg(2, "二")]
    raw = '{"translations": [{"i": 1, "text": "một"}, {"i": 2, "Text": "hai"}]}'
    out = parse_batch_response(raw, batch)
    assert [s.text for s in out] == ["một", "hai"]


def test_parse_accepts_a_fully_upper_case_key():
    batch = [seg(1, "一")]
    raw = '{"translations": [{"I": 1, "TEXT": "một"}]}'
    assert parse_batch_response(raw, batch)[0].text == "một"


def test_parse_accepts_a_capitalised_translations_key():
    raw = '{"Translations": [{"i": 1, "text": "một"}]}'
    assert parse_batch_response(raw, [seg(1, "一")])[0].text == "một"


@pytest.mark.parametrize("raw", [
    '{"translations": [{"index": 1, "translation": "một"}]}',
    '{"translations": [{"id": 1, "translation": "một"}]}',
])
def test_parse_accepts_equivalent_key_names(raw):
    """`index`/`id` cho vị trí và `translation` cho nội dung là những tên khoá
    model thật hay dùng; chúng TƯƠNG ĐƯƠNG, không phải rác."""
    assert parse_batch_response(raw, [seg(1, "一")])[0].text == "một"


@pytest.mark.parametrize("raw", [
    '{"translations": [{"i": 1, "txt": "một"}]}',
    '{"translations": [{"i": 1}]}',
    '{"translations": [{"text": "một"}]}',
    '{"translations": [{"i": 1, "text": null}]}',
    '{"translations": [{"i": 1, "Translation": 123}]}',
    '{"translations": [{"i": 1, "Text": {"vi": "một"}}]}',
])
def test_parse_still_rejects_a_garbage_item(raw):
    """Nới khoá KHÔNG được thành nới kiểu: khoá lạ, thiếu khoá, và giá trị
    không phải chuỗi vẫn phải ném — nếu không thì một `null` thành phụ đề."""
    with pytest.raises(ValueError):
        parse_batch_response(raw, [seg(1, "一")])


def test_parse_prefers_the_exact_key_when_both_spellings_are_present():
    """Hai khoá tương đương cùng có mặt: chọn theo thứ tự TẤT ĐỊNH (khoá viết
    đúng chữ thường trước), không phụ thuộc thứ tự ngẫu nhiên của dict."""
    raw = '{"translations": [{"i": 1, "Text": "SAI", "text": "đúng"}]}'
    assert parse_batch_response(raw, [seg(1, "一")])[0].text == "đúng"



def test_parse_raises_valueerror_when_i_is_not_an_integer():
    """`int(null)` ném `TypeError` — ngoài cả `AlignmentProblem` lẫn `ValueError` (review I-3).

    `TypeError` không thuộc taxonomy của `app/domain/alignment.py:8-12`, nên bên
    gọi mất luôn quyết định thử lại cả lô hay lùi về từng segment.
    """
    with pytest.raises(ValueError):
        parse_batch_response('{"translations": [{"i": null, "text": "A"}]}', [seg(1, "a")])


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
