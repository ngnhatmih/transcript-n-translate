from experiments.accuracy_pipelines.ocr_scoring import (best_substring,
                                                per_caption_rows,
                                                score_caption_observations)


def test_best_substring_returns_character_error_breakdown():
    result = best_substring("今天", "你今天好")

    assert result["del"] == 0
    assert result["sub"] == 0
    assert result["ins"] == 0
    assert result["cer"] == 0


def test_caption_score_aggregates_deletion_substitution_and_insertion():
    observations = [
        {"start": 0, "end": 1, "ocr": "你好朋友"},
        {"start": 10, "end": 11, "ocr": "世界人民"},
        {"start": 20, "end": 21, "ocr": "再见朋友"},
    ]
    segments = [
        {"start": 0, "end": 1, "text": "你好"},
        {"start": 10, "end": 11, "text": "世界坏民"},
        {"start": 20, "end": 21, "text": "再见多朋友"},
    ]

    result = score_caption_observations(observations, segments, opencc=None)

    assert result["timed"]["n"] == 3
    assert result["timed"]["del"] == 2
    assert result["timed"]["sub"] == 1
    assert result["timed"]["ins"] == 1


def test_per_caption_rows_match_the_aggregate_score():
    """Bảng theo CẶP và bảng điểm phải là cùng một phép đo.

    Nếu `per_caption_rows` tự dựng lại cửa sổ ±2 s thì CI có thể nói về một tập
    caption khác với bảng điểm — đúng loại lệch không ai phát hiện được.
    """
    observations = [
        {"start": 0, "end": 1, "ocr": "你好朋友"},
        {"start": 10, "end": 11, "ocr": "世界人民"},
        {"start": 20, "end": 21, "ocr": "再见朋友"},
        {"start": 30, "end": 31, "ocr": "短"},  # dưới 4 ký tự: bị loại
    ]
    segments = [
        {"start": 0, "end": 1, "text": "你好"},
        {"start": 10, "end": 11, "text": "世界坏民"},
        {"start": 20, "end": 21, "text": "再见多朋友"},
    ]
    rows = per_caption_rows(observations, segments, opencc=None)
    result = score_caption_observations(observations, segments, opencc=None)

    assert len(rows) == result["timed"]["n"] == 3
    assert (sum(row["timed"]["errors"] for row in rows)
            == result["timed"]["errors"])
