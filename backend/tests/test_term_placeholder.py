"""Hợp đồng của `app/domain/term_placeholder.py` — hàm THUẦN, không model.

Vì sao bộ test này tồn tại: policy tên riêng của sản phẩm là Hán-Việt
(`曹磊 -> Tào Lôi`, `烟台山 -> Yên Đài Sơn`), còn model đã ship trả pinyin
(`Cao Lei`, `núi Yantai`). Cơ chế bù là che chỗ thuật ngữ bằng token rồi thay
token bằng đúng chuỗi của hàng glossary — nên chỗ này phải ĐỎ khi:

* thứ tự "thuật ngữ dài trước" bị đảo (`纸鸢` ăn mất đuôi `小儿放纸鸢图`);
* mã token ngắn ăn mất mã token dài (`ZXQ1` ăn `ZXQ10`) — phụ đề sẽ ra
  "bản dịch của token 1" + "0";
* một token bị model bỏ/lặp/đổi số mà không ai nói ra;
* đánh số theo LẦN XUẤT HIỆN thay vì theo THUẬT NGỮ (cùng một cái tên trong một
  câu bị đếm hai lần).

Không bài nào cần GPU, mạng, hay model: mọi hàm ở đây là hàm thuần.
"""
from __future__ import annotations

import pytest

from app.domain.models import Term
from app.domain.term_placeholder import (TOKEN_DUPLICATED, TOKEN_LOST,
                                         TOKEN_UNKNOWN, count_tokens,
                                         has_token_like, plan_terms, protect,
                                         restore)


def term(value: str, rendering: str, *, lang: str = "zh",
         approved: bool = True) -> Term:
    return Term(id=None, lang=lang, term=value, translation=rendering,
                approved=approved)


TITLE = term("小儿放纸鸢图", "Tranh thả diều của trẻ nhỏ (Tiểu Nhi Phóng Chỉ Diên Đồ)")
KITE = term("纸鸢", "con diều")
NAME = term("曹磊", "Tào Lôi")
MOUNTAIN = term("烟台山", "Yên Đài Sơn")


def test_the_longest_term_wins():
    """`纸鸢` nằm TRONG `小儿放纸鸢图`: tên dài phải được xử lý trước.

    Đảo thứ tự thì `这是小儿放纸鸢图` ra hai token (`这是小儿放` + `ZXQ1`) và tiêu
    đề tác phẩm bị cắt làm hai mảnh — đúng thứ tự DÀI trước là chỗ duy nhất chặn
    điều đó, nên test này là chốt của cả cơ chế.
    """
    text = "这是小儿放纸鸢图"
    protected, mapping = protect(text, [KITE, TITLE])
    assert protected == "这是ZXQ1"
    assert len(mapping) == 1
    assert mapping == {"ZXQ1": TITLE.translation}


def test_an_echoing_engine_round_trips_the_text():
    """Protect + (engine chép nguyên văn) + restore ⇒ đúng chuỗi đầu vào.

    Bản dịch được đặt BẰNG chính chữ nguồn để phép thử đo CƠ CHẾ (không mất chữ,
    không lệch khoảng trắng), không đo policy Hán-Việt. Ca có bản dịch thật nằm ở
    bài dưới.
    """
    echo = term("曹磊", "曹磊")
    text = "这是曹磊的鱼灯"
    protected, mapping = protect(text, [echo])
    restored, issues = restore(protected, mapping)
    assert restored == text
    assert issues == []


def test_only_the_term_span_changes_in_a_round_trip():
    text = "这是小儿放纸鸢图"
    protected, mapping = protect(text, [KITE, TITLE])
    restored, issues = restore(protected, mapping)
    assert issues == []
    assert restored == text.replace("小儿放纸鸢图", TITLE.translation)
    assert restored != text, "bản dịch của glossary phải THAY chỗ thuật ngữ"


def test_a_term_used_twice_gets_one_token():
    """Đánh số theo THUẬT NGỮ, không theo lần xuất hiện.

    Cùng một cái tên hai lần trong một câu là hai chỗ của CÙNG một thuật ngữ. Đánh
    số theo lần xuất hiện (`ZXQ1`, `ZXQ2`) thì thống kê "token nào bị mất" đếm một
    cái tên thành hai, và `restore` tưởng model lặp token ở mọi câu lặp tên.
    """
    protected, mapping = protect("曹磊 và 曹磊", [NAME])
    assert protected == "ZXQ1 và ZXQ1"
    assert mapping == {"ZXQ1": "Tào Lôi"}


def test_the_tenth_token_is_not_eaten_by_the_first_one():
    """`ZXQ1` là TIỀN TỐ của `ZXQ10`: thay chuỗi con thô sẽ ăn mất số 0.

    Đây là lý do `restore` khớp theo RANH GIỚI token (`(?![0-9])`) chứ không
    `str.replace`: một lô 10 thuật ngữ là đủ chạm ca này, và hậu quả là phụ đề ra
    "Tào Lôi0" — một cái tên cộng một chữ số vô nghĩa.
    """
    mapping = {"ZXQ1": "một", "ZXQ10": "mười"}
    restored, issues = restore("ZXQ10 rồi ZXQ1", mapping)
    assert restored == "mười rồi một"
    assert issues == []


def test_the_model_may_case_and_split_the_token():
    """Model không chép token y nguyên: `ZXQ 3`, `Zxq3`, `ZXQ3,` đều phải khôi phục.

    Đo trên adapter thật thì `ZXQ{n}` sống 6/6 nguyên vẹn, nhưng đó là lô 7 câu —
    một model khác hoặc một câu dài hơn có thể tách số hoặc hoa chữ. Bỏ qua ba
    biến dạng này là để một `ZXQ3` thô nằm trong phụ đề.
    """
    mapping = {"ZXQ3": "Tào Lôi"}
    restored, issues = restore("a ZXQ 3, b Zxq3, c ZXQ3.", mapping,
                               expected={"ZXQ3": 3})
    assert restored == "a Tào Lôi, b Tào Lôi, c Tào Lôi."
    assert issues == []


def test_a_token_at_the_start_of_a_sentence_is_restored():
    """Token đứng ĐẦU câu là ca dễ bị model hoa hoá hoặc dán vào chữ sau."""
    mapping = {"ZXQ1": "Yên Đài Sơn"}
    restored, issues = restore("ZXQ1的鱼灯", mapping)
    assert restored == "Yên Đài Sơn的鱼灯"
    assert issues == []


def test_a_rendering_that_looks_like_a_token_is_not_replaced_twice():
    """Khôi phục là MỘT lượt `re.sub`, nên nó không đọc lại chữ do mình sinh ra.

    Một `Term.translation` có thể tình cờ chứa chuỗi giống token (đo trên dữ liệu
    thật: bản dịch có số và tên viết tắt). Nếu khôi phục chạy nhiều lượt — hoặc
    duyệt số LỚN -> NHỎ rồi thay bằng `str.replace` — thì chính bản dịch vừa chèn
    lại bị thay lần nữa, và cái tên biến thành một chuỗi khác.
    """
    mapping = {"ZXQ1": "Tào Lôi 2 ZXQ1"}
    restored, issues = restore("ZXQ1", mapping, expected={"ZXQ1": 1})
    assert restored == "Tào Lôi 2 ZXQ1"
    assert issues == []


def test_several_tokens_in_one_sentence_are_all_restored():
    mapping = {"ZXQ1": "Tào Lôi", "ZXQ2": "Yên Đài Sơn"}
    restored, issues = restore("ZXQ1 đi ZXQ2", mapping)
    assert restored == "Tào Lôi đi Yên Đài Sơn"
    assert issues == []


def test_a_dropped_token_is_reported_lost():
    mapping = {"ZXQ2": "Tào Lôi"}
    restored, issues = restore("Đó chính là thứ các bạn muốn mà", mapping)
    assert restored == "Đó chính là thứ các bạn muốn mà", (
        "model bỏ token thì GIỮ chữ của model, không bịa lại tên"
    )
    assert issues == [f"{TOKEN_LOST}:ZXQ2"]


def test_a_token_the_model_repeats_is_reported_duplicated():
    mapping = {"ZXQ1": "Tào Lôi"}
    restored, issues = restore("ZXQ1 và ZXQ1", mapping, expected=count_tokens("ZXQ1", mapping))
    assert restored == "Tào Lôi và Tào Lôi"
    assert issues == [f"{TOKEN_DUPLICATED}:ZXQ1"]


def test_a_repeated_term_in_the_source_is_not_a_duplicate():
    """Nguồn có hai lần thì model viết hai lần là ĐÚNG — không được gắn cờ.

    Đây là lý do `restore` nhận `expected` (`count_tokens` trên bản đã che): không
    có con số đó thì mọi câu lặp tên đều bị `token_duplicated` oan.
    """
    protected, mapping = protect("曹磊 và 曹磊", [NAME])
    expected = count_tokens(protected, mapping)
    assert expected == {"ZXQ1": 2}
    restored, issues = restore(protected, mapping, expected=expected)
    assert restored == "Tào Lôi và Tào Lôi"
    assert issues == []


def test_an_unknown_token_is_left_verbatim():
    """Số không có trong map (model bịa/đổi số) ⇒ để NGUYÊN VĂN, không đoán tên."""
    mapping = {"ZXQ1": "Tào Lôi"}
    restored, issues = restore("ZXQ1 và ZXQ7", mapping)
    assert restored == "Tào Lôi và ZXQ7"
    assert issues == [f"{TOKEN_UNKNOWN}:ZXQ7"]


def test_a_prefix_already_in_the_text_raises():
    with pytest.raises(ValueError, match="ZXQ"):
        protect("nguồn đã có ZXQ1 rồi", [NAME])


def test_has_token_like_finds_the_collision_the_pipeline_must_skip():
    """Tầng gọi phải hỏi TRƯỚC khi `protect`: che lên chữ có sẵn là thay cả hai."""
    assert has_token_like("nguồn đã có ZXQ1 rồi")
    assert has_token_like("viết thường zxq 12")
    assert not has_token_like("không có gì đặc biệt")
    assert not has_token_like("曹磊")


def test_a_prefix_inside_a_term_raises():
    with pytest.raises(ValueError, match="ZXQ"):
        protect("曹磊", [term("曹ZXQ磊", "Tào Lôi")])


def test_an_empty_term_or_rendering_is_skipped():
    """Chuỗi rỗng là chuỗi con của MỌI văn bản — nhận nó là token hoá mọi segment."""
    text = "曹磊"
    protected, mapping = protect(text, [term("", "rỗng"), term("曹磊", "")])
    assert (protected, mapping) == (text, {})


def test_a_term_that_does_not_occur_is_skipped():
    protected, mapping = protect("曹磊", [NAME, MOUNTAIN])
    assert protected == "ZXQ1"
    assert mapping == {"ZXQ1": "Tào Lôi"}


def test_a_term_touching_a_digit_is_not_tokenised():
    """Token dính số là token KHÔNG khôi phục được ⇒ `protect` từ chối câu đó.

    `一平尺2000` là đúng cặp số liệu mà `name_patch` đã ghi: term đứng ngay trước
    chữ số. Che nó thành `一ZXQ12,000` thì `restore` đọc ra token số 12 (không có
    trong map) và để nguyên một `ZXQ12` thô trong phụ đề. Thà câu đó đi đường dịch
    thường (tầng gọi gắn `token_collision_in_source`) còn hơn.
    """
    with pytest.raises(ValueError, match="chữ số"):
        protect("一平尺2000", [term("平尺", "bình xích")])


def test_two_terms_touching_each_other_are_not_tokenised():
    """`纸鸢曹磊` ⇒ `ZXQ1ZXQ2`; token thứ hai bị chính chữ số của token đầu chặn."""
    with pytest.raises(ValueError, match="dính nhau"):
        protect("纸鸢曹磊", [KITE, NAME])


def test_plan_terms_keeps_only_approved_terms_of_the_source_language():
    terms = [NAME, term("dragon", "rồng", lang="en"),
             term("拉踩", "dìm hàng", approved=False)]
    assert plan_terms(terms, source_lang="zh") == [NAME]


def test_restore_is_idempotent():
    """Gọi hai lần không nhân đôi bản dịch và không báo token đã khôi phục là mất."""
    mapping = {"ZXQ1": "Tào Lôi"}
    once, _ = restore("ZXQ1", mapping)
    twice, issues = restore(once, mapping)
    assert (twice, issues) == ("Tào Lôi", [])
