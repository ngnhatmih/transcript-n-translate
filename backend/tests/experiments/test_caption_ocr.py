from experiments.accuracy_pipelines.caption_ocr import choose_caption_text
from app.domain.models import Segment
from experiments.accuracy_pipelines.contracts import PipelineContext


def test_caption_ocr_corrects_close_homophone_but_keeps_asr_for_unrelated_text():
    assert choose_caption_text("但我直接去扇头", "但我直接去汕头") == "但我直接去汕头"
    assert choose_caption_text("但我直接去扇头", "想想工作室") == "但我直接去扇头"


def test_caption_ocr_keeps_asr_when_ocr_is_empty_or_not_similar_enough():
    assert choose_caption_text("那赶紧赔我了", "") == "那赶紧赔我了"
    assert choose_caption_text("那赶紧赔我了", "那该你赔我了") == "那该你赔我了"


def test_caption_ocr_rejects_partial_line_that_would_delete_asr_words():
    assert choose_caption_text("我反正要来一场大的", "我反正要来一串") == "我反正要来一场大的"


def test_caption_ocr_does_not_change_numbers_or_negation():
    assert choose_caption_text("你还欠我18万7712", "你还欠我187,712") == "你还欠我18万7712"
    assert choose_caption_text("这个不值钱", "这个值钱") == "这个不值钱"


def test_pipeline_ocr_corrects_source_before_translation_and_unloads_vlm(monkeypatch, tmp_path):
    from experiments.accuracy_pipelines import caption_ocr

    source = [Segment(i=0, start=10, end=12, text="但我直接去扇头")]
    calls = []
    monkeypatch.setattr(caption_ocr, "transcribe", lambda *_a, **_k: source)
    monkeypatch.setattr(caption_ocr, "extract_frame_at", lambda _media, at, out: (
        calls.append(("frame", at)) or out
    ))

    def fake_chat(_ctx, _model, _system, _prompt, **kwargs):
        calls.append(("vlm", kwargs.get("unload_after")))
        return {"text": "但我直接去汕头"}, {}

    monkeypatch.setattr(caption_ocr, "chat", fake_chat)
    monkeypatch.setattr(caption_ocr, "unload_ollama_model",
                        lambda *_a, **_k: calls.append(("unload",)))
    monkeypatch.setattr(caption_ocr, "translate", lambda _engine, segments, *_a, **_k: [
        Segment(i=s.i, start=s.start, end=s.end, text="Nhưng tôi đi Sán Đầu")
        for s in segments
    ])
    context = PipelineContext(
        media_path=tmp_path / "video.mp4", audio_path=tmp_path / "audio.wav",
        source_lang="zh", target_lang="vi", workdir=tmp_path,
        output_dir=tmp_path, models={"baseline_mt": "opus-mt"},
    )

    result = caption_ocr.run(context)

    assert result.corrected_segments[0].text == "但我直接去汕头"
    assert result.source_segments[0].text == "但我直接去扇头"
    assert result.final_translation[0].text == "Nhưng tôi đi Sán Đầu"
    assert calls == [("frame", 11.0), ("vlm", False), ("unload",)]
    assert result.metadata["caption_observations"] == [{
        "i": 0, "start": 10, "end": 12,
        "asr": "但我直接去扇头", "ocr": "但我直接去汕头",
        "selected": "但我直接去汕头",
    }]

