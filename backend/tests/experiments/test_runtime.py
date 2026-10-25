from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.models import Segment
from app.domain.alignment import AlignmentProblem
from experiments.accuracy_pipelines.runtime import (
    ModelUnavailableError,
    extract_context_frames,
    extract_frame_at,
    load_runtime_context,
    ollama_json,
    require_ollama_models,
    transcribe,
    translate,
)


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        return self.payload


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)


def test_transcribe_releases_engine_if_inference_raises():
    class Engine:
        released = False

        def transcribe(self, *_):
            raise RuntimeError("decode failed")

        def release(self):
            self.released = True

    engine = Engine()

    with pytest.raises(RuntimeError, match="decode failed"):
        transcribe("fw-small", "audio.wav", "zh", engine_factory=lambda *_: engine)

    assert engine.released is True


def test_transcribe_passes_initial_prompt_through_engine_spec():
    seen = []

    class Engine:
        def transcribe(self, *_):
            return [Segment(i=0, start=0, end=1, text="汕头")]

        def release(self):
            pass

    def factory(spec):
        seen.append(spec.opts.get("initial_prompt"))
        return Engine()

    transcribe("fw-small", "audio.wav", "zh", engine_factory=factory,
               initial_prompt="汕头; 烟台山")

    assert seen == ["汕头; 烟台山"]


def test_translate_retries_malformed_large_batch_as_single_segments():
    class Engine:
        released = False
        calls = []

        def translate(self, batch, _glossary, _opts):
            self.calls.append([segment.i for segment in batch])
            if len(batch) > 1:
                raise ValueError("malformed batch JSON")
            return [Segment(i=s.i, start=s.start, end=s.end, text=f"T{s.i}") for s in batch]

        def release(self):
            self.released = True

    engine = Engine()
    source = [Segment(i=i, start=float(i), end=float(i + 1), text="你好") for i in range(2)]

    translated = translate("fake", source, [], "zh", "vi", engine_factory=lambda _id: engine)

    assert [segment.text for segment in translated] == ["T0", "T1"]
    assert engine.calls == [[0, 1], [0], [1]]
    assert engine.released is True


def test_translate_retries_alignment_failure_as_single_segments():
    class Engine:
        def translate(self, batch, _glossary, _opts):
            if len(batch) > 1:
                raise AlignmentProblem([0, 1], [0], "missing segment")
            return [Segment(i=s.i, start=s.start, end=s.end, text=f"T{s.i}") for s in batch]

        def release(self):
            pass

    source = [Segment(i=i, start=float(i), end=float(i + 1), text="你好") for i in range(2)]

    translated = translate("fake", source, [], "zh", "vi", engine_factory=lambda _id: Engine())

    assert [segment.text for segment in translated] == ["T0", "T1"]


def test_required_ollama_tag_reports_exact_pull_command():
    client = Client([Response({"models": [{"name": "qwen2.5:3b-instruct-q4_K_M"}]})])

    with pytest.raises(ModelUnavailableError, match="ollama pull qwen3-vl:2b"):
        require_ollama_models(["qwen3-vl:2b"], client=client)


def test_context_preparation_extracts_audio_once(tmp_path):
    media = tmp_path / "input.mp4"
    media.touch()
    calls = []

    def fake_extract(path, directory, *, stem):
        calls.append((path, directory, stem))
        audio = Path(directory) / "audio.wav"
        audio.touch()
        return audio, 42.0

    args = SimpleNamespace(media=str(media), source="zh", target="vi",
                           output_dir=str(tmp_path / "out"), frame_interval=15,
                           ollama_url="http://127.0.0.1:11434")
    context = load_runtime_context(args, audio_extractor=fake_extract)

    assert len(calls) == 1
    assert context.audio_path.name == "audio.wav"
    assert context.audio_duration_seconds == 42.0
    context.cleanup()


def test_ollama_json_always_requests_unload_after_success():
    client = Client([
        Response({"message": {"content": '{"context": "court"}'},
                  "prompt_eval_count": 12, "eval_count": 4, "total_duration": 9_000_000}),
        Response({"done_reason": "unload"}),
    ])

    payload, stats = ollama_json("qwen2.5:3b", "system", "user", client=client)

    assert payload == {"context": "court"}
    assert stats == {"tokens_in": 12, "tokens_out": 4, "duration_ms": 9}
    assert client.calls[-1][2]["json"]["keep_alive"] == 0


def test_ollama_json_can_disable_reasoning_for_vision_models():
    client = Client([
        Response({"message": {"content": '{"text":"字幕"}'}}),
        Response({"done_reason": "unload"}),
    ])

    ollama_json("qwen3-vl:2b", "system", "user", client=client, think=False)

    assert client.calls[0][2]["json"]["think"] is False


def test_ollama_json_can_keep_model_loaded_across_frame_requests():
    client = Client([Response({"message": {"content": '{"text":"字幕"}'}})])

    ollama_json("qwen3-vl:2b", "system", "user", client=client,
                think=False, unload_after=False)

    assert len(client.calls) == 1


def test_ollama_json_can_bound_generated_tokens_for_visual_ocr():
    client = Client([
        Response({"message": {"content": '{"text":"字幕"}'}}),
        Response({"done_reason": "unload"}),
    ])

    ollama_json("qwen3-vl:2b", "system", "user", client=client,
                think=False, num_predict=256)

    assert client.calls[0][2]["json"]["options"]["num_predict"] == 256


def test_ollama_json_omits_empty_system_message_for_vision_models():
    client = Client([
        Response({"message": {"content": '{"text":"字幕"}'}}),
        Response({"done_reason": "unload"}),
    ])

    ollama_json("qwen3-vl:2b", "", "Read subtitle", client=client)

    messages = client.calls[0][2]["json"]["messages"]
    assert messages == [{"role": "user", "content": "Read subtitle"}]


def test_ollama_json_unloads_even_when_content_is_invalid():
    client = Client([
        Response({"message": {"content": "not json"}}),
        Response({"done_reason": "unload"}),
    ])

    with pytest.raises(ValueError, match="JSON"):
        ollama_json("qwen2.5:3b", "system", "user", client=client)

    assert client.calls[-1][2]["json"]["keep_alive"] == 0


def test_visual_frame_sampling_rejects_audio_only_input(tmp_path):
    def fake_run(command, **kwargs):
        return SimpleNamespace(stdout='{"streams": []}', stderr="")

    with pytest.raises(ValueError, match="audio-only"):
        extract_context_frames(tmp_path / "audio.wav", tmp_path / "frames", 15,
                              runner=fake_run)


def test_context_frames_can_exclude_burned_in_subtitle_band(tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == "ffprobe":
            return SimpleNamespace(stdout='{"streams": [{"codec_type": "video"}]}', stderr="")
        (tmp_path / "frames" / "frame_0001.jpg").touch()
        return SimpleNamespace(stdout="", stderr="")

    extract_context_frames(tmp_path / "clip.mp4", tmp_path / "frames", 15,
                           runner=fake_run, crop_subtitles=True)

    video_filter = calls[1][calls[1].index("-vf") + 1]
    assert "crop=iw:ih*3/4:0:0" in video_filter


def test_extract_frame_at_requests_nearest_midpoint(tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return None

    output = tmp_path / "frame.jpg"
    extract_frame_at(tmp_path / "clip.mp4", 35.67, output, runner=fake_run)

    assert calls[0][calls[0].index("-ss") + 1] == "35.670"
    assert calls[0][-1] == str(output)
