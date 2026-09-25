from __future__ import annotations

from app.domain.qa_rules import check


def test_clean_translation_has_no_issues():
    assert check("人工智能很有趣", "Trí tuệ nhân tạo rất thú vị") == []


def test_empty_translation_is_flagged():
    assert "empty" in check("人工智能", "   ")


def test_missing_number_is_flagged_with_the_number():
    issues = check("增长到 2025 年", "Tăng trưởng trong năm nay")
    assert any(i.startswith("missing_number:2025") for i in issues), issues


def test_present_number_is_not_flagged():
    assert not [i for i in check("增长到 2025 年", "Tăng đến năm 2025") if i.startswith("missing_number")]


def test_missing_glossary_term_is_flagged():
    issues = check("大模型很重要", "Mô hình rất quan trọng", glossary_terms=["大模型"])
    assert "missing_term:大模型" in issues


def test_glossary_term_present_is_clean():
    # glossary giữ BẢN DỊCH của thuật ngữ — đó mới là thứ `check` đối chiếu với
    # translated_text. "大模型" là chữ Hán nên không bao giờ nằm trong một bản
    # dịch tiếng Việt: dùng nó ở đây thì test này đỏ với MỌI implementation,
    # kể cả implementation đúng. Cặp fixture gốc chỉ khác nhau ở chữ "lớn", nên
    # thuật ngữ phải là "Mô hình lớn".
    assert check("大模型很重要", "Mô hình lớn rất quan trọng", glossary_terms=["Mô hình lớn"]) == []


def test_overlong_translation_is_flagged():
    issues = check("好", "tốt " * 40)
    assert "too_long" in issues


def test_short_translation_is_not_flagged_for_length():
    assert "too_long" not in check("这是一个很长的句子用来测试", "Ngắn")
