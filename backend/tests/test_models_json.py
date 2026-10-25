from __future__ import annotations

import json

from app.domain.models import Segment, Word, segments_from_json, segments_to_json


def test_segment_roundtrip_keeps_optional_fields_absent():
    seg = Segment(i=0, start=1.02, end=4.38, text="大家好")
    d = seg.to_json()
    assert d["i"] == 0 and d["start"] == 1.02 and d["end"] == 4.38
    assert d["text"] == "大家好"
    assert d["suspect"] is False
    assert "words" not in d, "engine không sinh words thì không được bịa khoá ra"
    assert "t" not in d, "chưa dịch thì không có khoá t"
    assert Segment.from_json(d) == seg


def test_segment_roundtrip_full():
    seg = Segment(
        i=3, start=12.85, end=15.6, text="这个模型它其实……",
        words=[Word(w="这个", s=12.85, e=13.4), Word(w="模型", s=13.4, e=14.1)],
        emotion="happy", events=["bgm"], speaker=None,
        avg_logprob=-1.42, no_speech_prob=0.71, suspect=True,
        t="Mô hình này thực ra thì……", qa=["too_long"],
    )
    d = seg.to_json()
    assert d["suspect"] is True
    assert d["events"] == ["bgm"]
    assert d["words"][0] == {"w": "这个", "s": 12.85, "e": 13.4}
    assert d["t"] == "Mô hình này thực ra thì……"
    assert Segment.from_json(d) == seg


def test_segments_json_is_valid_utf8_and_stable():
    segs = [Segment(i=0, start=0.0, end=1.0, text="你好")]
    raw = segments_to_json(segs)
    assert "你好" in raw, "ensure_ascii=False — đừng escape tiếng Trung"
    assert json.loads(raw)[0]["text"] == "你好"
    assert segments_from_json(raw) == segs


def test_from_json_tolerates_unknown_keys():
    d = {"i": 0, "start": 0.0, "end": 1.0, "text": "x", "la_ky_la": 1}
    assert Segment.from_json(d).text == "x"
