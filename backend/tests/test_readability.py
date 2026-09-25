from __future__ import annotations

from app.domain.readability import CPS_WARN, is_too_fast, reading_cps


def test_cps_counts_chars_without_spaces():
    # 20 ký tự không tính khoảng trắng, trong 2 giây -> 10 CPS
    assert reading_cps("a b c d e f g h i j k l m n o p q r s t", 0.0, 2.0) == 10.0


def test_zero_or_negative_duration_is_infinite_not_a_crash():
    assert reading_cps("abc", 5.0, 5.0) == float("inf")
    assert is_too_fast("abc", 5.0, 5.0) is True


def test_vietnamese_line_over_threshold_is_flagged():
    text = "Hôm nay chúng ta sẽ cùng bàn về trí tuệ nhân tạo"
    # 37 ký tự không tính khoảng trắng: 37 / 1.5 = 24.67 CPS (> 20) — còn
    # 37 / 2.0 = 18.50 CPS thì KHÔNG vượt ngưỡng, nên mốc 2.0 là sai.
    assert reading_cps(text, 0.0, 1.5) > CPS_WARN
    assert is_too_fast(text, 0.0, 1.5) is True
    assert is_too_fast(text, 0.0, 6.0) is False
