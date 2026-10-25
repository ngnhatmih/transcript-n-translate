from __future__ import annotations

import pytest

from experiments.accuracy_pipelines.metrics import (char_error_rate, chrf, err_breakdown,
                                                paired_bootstrap_ci)


def test_identical_chinese_text_has_zero_cer_and_perfect_chrf():
    text = "你好，世界！"

    assert char_error_rate(text, text) == 0.0
    assert chrf(text, text) == 100.0


def test_cer_counts_one_vietnamese_character_substitution():
    assert char_error_rate("Xin chào", "Xin cháo") == pytest.approx(1 / 7)


def test_chrf_scores_character_overlap_when_one_character_differs():
    assert chrf("你好", "你坏", max_order=1) == pytest.approx(50.0)


def test_metrics_ignore_equivalent_punctuation_and_spacing():
    assert char_error_rate("你好，世界！", "你好, 世界!") == 0.0
    assert chrf("你好，世界！", "你好, 世界!") == 100.0


def test_empty_reference_is_scored_without_division_by_zero():
    assert char_error_rate("", "") == 0.0
    assert char_error_rate("", "abc") == 1.0
    assert chrf("", "abc") == 0.0


def test_err_breakdown_separates_deletions_substitutions_and_insertions():
    assert err_breakdown("abc", "ac") == {
        "del": 1, "sub": 0, "ins": 0, "errors": 1, "reference_chars": 3,
        "cer": pytest.approx(1 / 3),
    }
    assert err_breakdown("abc", "axc")["sub"] == 1
    assert err_breakdown("", "abc")["ins"] == 3


def test_paired_bootstrap_ci_is_zero_when_the_two_configs_are_identical():
    """Hai cấu hình cho CÙNG kết quả thì CI phải rỗng nghĩa, không phải "gần 0"."""
    mean, ci = paired_bootstrap_ci([0.0] * 10, resamples=500)
    assert (mean, ci) == (0.0, (0.0, 0.0))


def test_paired_bootstrap_ci_is_reproducible_for_a_seed():
    """Cùng seed cho đúng cùng CI — nếu không, một con số trong báo cáo không
    tái tạo được và không ai kiểm lại được kết luận."""
    deltas = [0.01, -0.02, 0.0, 0.03, -0.01]
    assert (paired_bootstrap_ci(deltas, resamples=500, seed=7)
            == paired_bootstrap_ci(deltas, resamples=500, seed=7))


def test_paired_bootstrap_ci_needs_at_least_one_pair():
    with pytest.raises(ValueError):
        paired_bootstrap_ci([])
