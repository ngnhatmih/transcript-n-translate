"""Test cho adapter faster-whisper và handler bóc băng.

KHÔNG bài nào nạp model thật. Mọi đường đi qua model đều dùng `model_factory`
được bơm vào (một seam của chính adapter), nên ở đây không có lượt tải mạng
nào. Model thật (~1.6 GB) là việc của smoke test Task 20.
"""
from __future__ import annotations

import builtins
import dataclasses
import sys
import types

import pytest

import app.adapters.asr.faster_whisper as fw_module
from app.adapters.asr.faster_whisper import FasterWhisperEngine, to_segments
from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.domain.models import Job, Segment, Source, Word
from app.pipeline.transcribe import TranscribeHandler


def test_to_segments_maps_confidence_and_marks_suspect():
    raw = [
        {"start": 0.0, "end": 2.0, "text": " 你好 ", "avg_logprob": -0.3,
         "no_speech_prob": 0.02, "words": [{"word": "你好", "start": 0.0, "end": 2.0}]},
        {"start": 2.0, "end": 4.0, "text": "感谢观看", "avg_logprob": -2.5,
         "no_speech_prob": 0.8, "words": []},
    ]
    segs = to_segments(raw)
    assert segs[0].text == "你好"
    assert segs[0].avg_logprob == -0.3
    assert segs[0].no_speech_prob == 0.02
    assert segs[0].suspect is False
    assert segs[0].words[0].w == "你好"
    assert segs[1].suspect is True, "no_speech_prob 0.8 phải bị đánh dấu nghi ngờ"
    assert segs[1].words is None, "không có word timestamp thì phải là None, không phải []"


def test_to_segments_marks_suspect_on_low_logprob():
    segs = to_segments([{"start": 0.0, "end": 1.0, "text": "x",
                         "avg_logprob": -1.5, "no_speech_prob": 0.01}])
    assert segs[0].suspect is True


class FakeEngine:
    def __init__(self, spec) -> None:
        self.engine_id = spec.id
        self.calls: list[tuple[str, str]] = []
        self.released = 0

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        self.calls.append((audio_path, lang))
        return [Segment(i=0, start=0.0, end=2.0, text="你好"),
                Segment(i=1, start=2.0, end=4.0, text="世界")]

    def release(self) -> None:
        self.released += 1


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


@pytest.fixture()
def specs():
    from app.registry import EngineSpec
    return [
        EngineSpec(id="fw-large-v3-turbo", label="FW", kind="asr",
                   runtime="inprocess", model_ref="large-v3-turbo", vram_mb=1600,
                   langs=("zh", "en"), capabilities={}, opts={}),
        EngineSpec(id="nllb-200-600m", label="NLLB", kind="mt",
                   runtime="ollama", model_ref="nllb-200-distilled-600M", vram_mb=0,
                   langs=("zh", "vi"), capabilities={}, opts={}),
    ]


def test_handler_produces_transcript_and_forwards_to_workspace_2(repos, specs, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    sid = repos.add_source(kind="file", origin="a.mp4", media_path=str(tmp_path / "a.mp4"),
                           lang="zh", audio_path=str(wav), duration=4.0)
    created: list[FakeEngine] = []

    def factory(spec):
        engine = FakeEngine(spec)
        created.append(engine)
        return engine

    handler = TranscribeHandler(repos, specs, factory, workdir=tmp_path)
    job = Job(id=1, workspace=1, type="asr", engine="fw-large-v3-turbo",
              phase=js.phase_of("asr", "fw-large-v3-turbo"),
              payload={"source_id": sid}, created_at="2026-09-25T00:00:00Z")
    logs: list[tuple[float, str]] = []
    handler.run(job, lambda p, line: logs.append((p, line)))

    transcripts = repos.list_transcripts()
    assert len(transcripts) == 1
    t = transcripts[0]
    assert [s.text for s in t.segments] == ["你好", "世界"]
    assert t.engine == "fw-large-v3-turbo" and t.lang == "zh" and t.version == 1

    queue = repos.list_jobs()
    forwarded = [j for j in queue if j.type == "translate"]
    assert len(forwarded) == 1, "auto_forward mặc định BẬT nên phải có job dịch ở WS2"
    assert forwarded[0].workspace == 2
    assert forwarded[0].payload["transcript_id"] == t.id
    assert forwarded[0].engine == "nllb-200-600m", (
        "job dịch phải trỏ tới spec kind='mt' trong registry, không được để None"
    )
    assert forwarded[0].phase == "translate:nllb-200-600m"
    assert logs and logs[-1][0] == 1.0


def test_auto_forward_can_be_turned_off(repos, specs, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    repos.set_setting("auto_forward", "0")
    sid = repos.add_source(kind="file", origin="a", media_path="m", lang="zh",
                           audio_path=str(wav), duration=4.0)
    handler = TranscribeHandler(repos, specs, lambda spec: FakeEngine(spec), workdir=tmp_path)
    job = Job(id=1, workspace=1, type="asr", engine="fw-large-v3-turbo",
              phase="asr:fw-large-v3-turbo", payload={"source_id": sid},
              created_at="2026-09-25T00:00:00Z")
    handler.run(job, lambda p, line: None)
    assert [j for j in repos.list_jobs() if j.type == "translate"] == []
    assert repos.list_transcripts()[0].status == "draft"


def test_missing_audio_raises_actionable_error(repos, specs, tmp_path):
    sid = repos.add_source(kind="file", origin="a", media_path="m", lang="zh")
    handler = TranscribeHandler(repos, specs, lambda spec: FakeEngine(spec), workdir=tmp_path)
    job = Job(id=1, workspace=1, type="asr", engine="fw-large-v3-turbo",
              phase="asr:fw-large-v3-turbo", payload={"source_id": sid},
              created_at="2026-09-25T00:00:00Z")
    with pytest.raises(Exception) as exc:
        handler.run(job, lambda p, line: None)
    assert "audio" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# M-12: `audio_path` đến TỪ DB, nên trước khi mở nó phải CHỨNG MINH containment
# ---------------------------------------------------------------------------

def _an_asr_job(source_id: int, *, n: int = 1) -> Job:
    return Job(id=n, workspace=1, type="asr", engine="fw-large-v3-turbo",
               phase=js.phase_of("asr", "fw-large-v3-turbo"),
               payload={"source_id": source_id}, created_at="2026-09-25T00:00:00Z")


def test_audio_path_outside_the_media_root_is_refused(repos, specs, tmp_path):
    """M-12(a) · `audio_path` ngoài gốc media ⇒ `FileNotFoundError` NÓI VỀ gốc media.

    Cột `audio_path` đến từ DB, và đây là chỗ DUY NHẤT trong họ cột `*_path`
    không chứng minh containment — `routes_media.py:125` và
    `pipeline/ingest.py:199` đã đi qua `resolve_within` từ trước.

    Tệp ngoài gốc được TẠO THẬT: nếu nó không tồn tại thì một bản vá bỏ hẳn
    `resolve_within` vẫn đỏ vì "tệp audio không tồn tại", tức bài này xanh mà
    không chứng minh được phép containment nào. Cùng lý do, khẳng định bám vào
    chữ "gốc media" chứ không chỉ vào lớp ngoại lệ.
    """
    media = tmp_path / "media"
    media.mkdir()
    ngoai = tmp_path / "ngoai-goc-media"
    ngoai.mkdir()
    outside = ngoai / "a.wav"
    outside.write_bytes(b"RIFF")
    sid = repos.add_source(kind="file", origin="a.mp4", media_path="m", lang="zh",
                           audio_path=str(outside), duration=4.0)
    created: list[FakeEngine] = []

    def factory(spec):
        engine = FakeEngine(spec)
        created.append(engine)
        return engine

    handler = TranscribeHandler(repos, specs, factory, workdir=media)
    with pytest.raises(FileNotFoundError) as exc:
        handler.run(_an_asr_job(sid), lambda p, line: None)

    assert "gốc media" in str(exc.value), str(exc.value)
    assert str(media) in str(exc.value), (
        f"thông báo phải nêu gốc media ({media}): {exc.value}"
    )
    assert created == [], "engine không được nạp cho một tệp ngoài gốc media"
    assert repos.list_transcripts() == [], "không được ghi transcript nào"


def test_a_directory_as_audio_path_is_refused_before_the_engine(repos, specs, tmp_path):
    """M-12(b) · một THƯ MỤC có thật lọt qua `exists()` rồi nổ ở tận trong engine.

    `exists()` đúng cho cả thư mục, nên phép kiểm cũ cho nó đi qua và lỗi thật
    hiện ra ở trong engine với thông báo mơ hồ (hoặc một transcript rỗng).
    `is_file()` chặn ở ĐÚNG chỗ, trước khi `_engine_for` được gọi — nên khẳng
    định `created == []` mới là vế phân biệt "lỗi sạch" với "lỗi từ engine".
    """
    media = tmp_path / "media"
    media.mkdir()
    a_dir = media / "khong-phai-tap-tin.wav"
    a_dir.mkdir()                      # có THẬT trên đĩa, nhưng là THƯ MỤC
    sid = repos.add_source(kind="file", origin="a.mp4", media_path="m", lang="zh",
                           audio_path=str(a_dir), duration=4.0)
    created: list[FakeEngine] = []

    def factory(spec):
        engine = FakeEngine(spec)
        created.append(engine)
        return engine

    handler = TranscribeHandler(repos, specs, factory, workdir=media)
    with pytest.raises(FileNotFoundError) as exc:
        handler.run(_an_asr_job(sid), lambda p, line: None)

    assert "audio" in str(exc.value).lower(), str(exc.value)
    assert created == [], "lỗi phải xảy ra TRƯỚC khi engine được nạp"
    assert repos.list_transcripts() == []


def test_a_valid_audio_path_inside_the_media_root_is_unchanged(repos, specs, tmp_path):
    """M-12(c) · vế đối chứng: đường dẫn HỢP LỆ không đổi hành vi.

    Và đường dẫn giao cho engine vẫn là chính tệp đó SAU khi phân giải — một
    phép containment trả về `None`/chuỗi rỗng/rơi mất đường dẫn sẽ làm engine mở
    sai tệp, mà lỗi đó chỉ hiện ra ở tận adapter.
    """
    media = tmp_path / "media"
    media.mkdir()
    wav = media / "a.wav"
    wav.write_bytes(b"RIFF")
    sid = repos.add_source(kind="file", origin="a.mp4", media_path="m", lang="zh",
                           audio_path=str(wav), duration=4.0)
    created: list[FakeEngine] = []

    def factory(spec):
        engine = FakeEngine(spec)
        created.append(engine)
        return engine

    handler = TranscribeHandler(repos, specs, factory, workdir=media)
    handler.run(_an_asr_job(sid), lambda p, line: None)

    assert len(repos.list_transcripts()) == 1
    assert len(created) == 1
    assert created[0].calls == [(str(wav.resolve()), "zh")], (
        "engine phải nhận đường dẫn ĐÃ PHÂN GIẢI của chính tệp đó: "
        f"{created[0].calls}"
    )


def test_engine_is_reused_across_jobs_of_the_same_phase(repos, specs, tmp_path):
    """Nạp model 4 lần cho 4 job là lãng phí 4-8 giây mỗi lần. Handler phải
    giữ engine theo id và chỉ tạo mới khi đổi engine."""
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    created: list[FakeEngine] = []

    def factory(spec):
        engine = FakeEngine(spec)
        created.append(engine)
        return engine

    handler = TranscribeHandler(repos, specs, factory, workdir=tmp_path)
    for n in range(3):
        sid = repos.add_source(kind="file", origin=f"a{n}", media_path="m", lang="zh",
                               audio_path=str(wav), duration=4.0)
        job = Job(id=n + 1, workspace=1, type="asr", engine="fw-large-v3-turbo",
                  phase="asr:fw-large-v3-turbo", payload={"source_id": sid},
                  created_at="2026-09-25T00:00:00Z")
        handler.run(job, lambda p, line: None)

    assert len(created) == 1, f"chỉ được nạp model 1 lần, thực tế {len(created)}"


def test_handler_releases_engine_when_switching_engine(repos, specs, tmp_path):
    from app.registry import EngineSpec
    both = specs + [EngineSpec(id="sensevoice-small", label="SV", kind="asr",
                               runtime="inprocess", model_ref="iic/SenseVoiceSmall",
                               vram_mb=1000, langs=("zh",), capabilities={}, opts={})]
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    created: list[FakeEngine] = []

    def factory(spec):
        engine = FakeEngine(spec)
        created.append(engine)
        return engine

    handler = TranscribeHandler(repos, both, factory, workdir=tmp_path)
    for n, engine_id in enumerate(["fw-large-v3-turbo", "fw-large-v3-turbo", "sensevoice-small"]):
        sid = repos.add_source(kind="file", origin=f"a{n}", media_path="m", lang="zh",
                               audio_path=str(wav), duration=4.0)
        job = Job(id=n + 1, workspace=1, type="asr", engine=engine_id,
                  phase=js.phase_of("asr", engine_id), payload={"source_id": sid},
                  created_at="2026-09-25T00:00:00Z")
        handler.run(job, lambda p, line: None)

    assert len(created) == 2
    assert created[0].released == 1, "đổi engine phải giải phóng engine cũ"


# --------------------------------------------------------------------------
# R54(b): `_default_mt_engine` quyết định engine dịch của CẢ pipeline.
# Fixture `specs` ở trên có một spec kind="mt" nên nhánh dò registry chạy thật;
# bài dưới đây khoá thêm nhánh setting ghi đè.
# --------------------------------------------------------------------------

def _run_one_asr(repos, specs, tmp_path):
    """Chạy đúng một job asr rồi trả về các job `translate` đã được forward."""
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    sid = repos.add_source(kind="file", origin="a", media_path="m", lang="zh",
                           audio_path=str(wav), duration=4.0)
    handler = TranscribeHandler(repos, specs, lambda spec: FakeEngine(spec), workdir=tmp_path)
    job = Job(id=1, workspace=1, type="asr", engine="fw-large-v3-turbo",
              phase=js.phase_of("asr", "fw-large-v3-turbo"), payload={"source_id": sid},
              created_at="2026-09-25T00:00:00Z")
    handler.run(job, lambda p, line: None)
    return [j for j in repos.list_jobs() if j.type == "translate"]


def test_default_mt_engine_falls_back_to_the_mt_spec_in_the_registry(repos, specs, tmp_path):
    forwarded = _run_one_asr(repos, specs, tmp_path)
    assert len(forwarded) == 1
    assert forwarded[0].engine == "nllb-200-600m", (
        "không có setting thì phải lấy spec kind='mt' đầu tiên, không phải None"
    )
    assert forwarded[0].phase == "translate:nllb-200-600m"


def test_default_mt_engine_setting_overrides_the_registry(repos, specs, tmp_path):
    """Setting `default_mt_engine` thắng cả danh sách spec."""
    from app.registry import EngineSpec
    both = specs + [EngineSpec(id="gemma3-4b", label="G", kind="mt",
                               runtime="ollama", model_ref="gemma3:4b", vram_mb=3000,
                               langs=("zh", "vi"), capabilities={}, opts={})]
    repos.set_setting("default_mt_engine", "gemma3-4b")
    forwarded = _run_one_asr(repos, both, tmp_path)
    assert len(forwarded) == 1
    assert forwarded[0].engine == "gemma3-4b", (
        "nếu nhánh setting bị xoá, hàm sẽ rơi về spec mt đầu tiên là nllb-200-600m"
    )
    assert forwarded[0].phase == "translate:gemma3-4b"


# --------------------------------------------------------------------------
# R54(a): hợp đồng của FasterWhisperEngine qua `model_factory`.
# `model_factory` là seam của chính adapter ("bơm vào để test kiểm tra hợp đồng
# mà không nạp model"); các bài dưới đây là chỗ duy nhất dùng nó.
# --------------------------------------------------------------------------

class _Info:
    """Giá trị thứ hai mà faster-whisper trả về. Adapter cố tình bỏ qua nó."""

    language = "zh"
    duration = 8.0


class _Word:
    def __init__(self, word, start, end) -> None:
        self.word, self.start, self.end = word, start, end


class _Seg:
    """Segment GIẢ của faster-whisper.

    Thuộc tính phụ chỉ được gắn khi có trong `attrs`, nên dựng được cả segment
    THIẾU HẲN `words`/`avg_logprob`/`no_speech_prob` để ép đúng nhánh
    `getattr(..., None)` của adapter.
    """

    def __init__(self, start, end, text, **attrs) -> None:
        self.start, self.end, self.text = start, end, text
        for name, value in attrs.items():
            setattr(self, name, value)


class _FakeWhisperModel:
    def __init__(self, model_ref, *, device, compute_type, download_root) -> None:
        self.model_ref = model_ref
        self.load_kwargs = {"device": device, "compute_type": compute_type,
                            "download_root": download_root}
        self.segments: list = []
        self.info = _Info()
        self.transcribe_calls: list = []

    def transcribe(self, audio_path, **kwargs):
        self.transcribe_calls.append((audio_path, kwargs))
        return iter(self.segments), self.info


class _RecordingModelFactory:
    """`model_factory` giả: ghi lại đối số nạp và trả model giả."""

    def __init__(self, segments=()) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.models: list[_FakeWhisperModel] = []
        self.segments = list(segments)

    def __call__(self, model_ref, **kwargs):
        model = _FakeWhisperModel(model_ref, **kwargs)
        model.segments = list(self.segments)
        self.calls.append((model_ref, kwargs))
        self.models.append(model)
        return model


@pytest.fixture()
def asr_spec(specs):
    return specs[0]


def _with_opts(spec, **opts):
    return dataclasses.replace(spec, opts=dict(opts))


def test_engine_factory_gets_model_ref_device_compute_type_and_download_root(
        asr_spec, tmp_path):
    factory = _RecordingModelFactory()
    engine = FasterWhisperEngine(asr_spec, download_root=str(tmp_path / "models"),
                                 model_factory=factory)
    assert factory.calls == [], "chưa transcribe thì chưa được nạp model"

    engine.transcribe("a.wav", "zh")
    engine.transcribe("a.wav", "zh")
    assert factory.calls == [(
        "large-v3-turbo",
        {"device": "cuda", "compute_type": "int8_float16",
         "download_root": str(tmp_path / "models")},
    )], "nạp đúng một lần, đúng model_ref/device/compute_type/download_root"

    other = _RecordingModelFactory()
    FasterWhisperEngine(asr_spec, device="cpu", model_factory=other).transcribe("a.wav", "zh")
    assert other.calls[0][1]["device"] == "cpu"
    assert other.calls[0][1]["download_root"] is None


def test_engine_takes_compute_type_from_spec_opts(asr_spec):
    factory = _RecordingModelFactory()
    engine = FasterWhisperEngine(_with_opts(asr_spec, compute_type="float16"),
                                 model_factory=factory)
    engine.transcribe("a.wav", "zh")
    assert factory.calls[0][1]["compute_type"] == "float16", (
        "spec.opts phải thắng giá trị mặc định int8_float16"
    )


def test_engine_maps_fake_segments_through_to_segments_and_normalize(asr_spec):
    """Dựng lại dict thô từ segment của faster-whisper rồi đi hết `normalize`.

    Dữ liệu được chọn sao cho đầu ra KHÁC hẳn đầu vào: đoạn chỉ gồm nhãn ảo
    giác ('感谢观看') bị `normalize` bỏ. Nếu `normalize` không chạy, danh sách
    trả về có 4 phần tử thay vì 3 — nên assertion về số phần tử là thật.
    """
    factory = _RecordingModelFactory([
        _Seg(0.0, 2.0, " 你好 ", avg_logprob=-0.3, no_speech_prob=0.02,
             words=[_Word("你好", 0.0, 2.0), _Word("rác", None, None)]),
        _Seg(2.0, 4.0, " 感谢观看 ", avg_logprob=-0.2, no_speech_prob=0.01),
        _Seg(4.0, 6.0, "世界"),                       # thiếu hẳn mọi thuộc tính phụ
        _Seg(6.0, 8.0, "噪声", avg_logprob=-1.5, no_speech_prob=0.8),
    ])
    engine = FasterWhisperEngine(asr_spec, model_factory=factory)

    out = engine.transcribe("a.wav", "zh")

    assert [s.i for s in out] == [0, 1, 2]
    assert [s.text for s in out] == ["你好", "世界", "噪声"], (
        "nhãn ảo giác phải bị normalize bỏ; chỉ có to_segments thì '感谢观看' vẫn còn"
    )
    assert out[0].words == [Word(w="你好", s=0.0, e=2.0)], (
        "word timestamp phải được ánh xạ; từ thiếu start/end phải bị loại"
    )
    assert out[0].avg_logprob == -0.3 and out[0].no_speech_prob == 0.02
    assert out[0].suspect is False
    assert out[1].words is None, "segment không có words phải là None, không phải []"
    assert out[1].avg_logprob is None and out[1].no_speech_prob is None, (
        "getattr fallback: segment thiếu thuộc tính không được làm nổ adapter"
    )
    assert out[2].suspect is True


def test_engine_returns_exactly_what_normalize_returns(asr_spec, monkeypatch):
    """Không được trả thẳng `to_segments`: giá trị trả về phải là của `normalize`.

    Cố tình để khoảng trắng thừa quanh văn bản và một nhãn ảo giác, rồi soi
    ĐẦU VÀO của `normalize`: nó phải là `to_segments(raw)` — chữ đã được
    `.strip()` nhưng nhãn ảo giác VẪN CÒN (việc lọc là của normalize). Chuỗi
    cuối cùng một mình không khoá được `.strip()` vì `normalize` cũng gộp
    khoảng trắng.
    """
    factory = _RecordingModelFactory([
        _Seg(0.0, 2.0, " 你好 ", avg_logprob=-0.3, no_speech_prob=0.02),
        _Seg(2.0, 4.0, " 感谢观看 ", avg_logprob=-0.2, no_speech_prob=0.01),
    ])
    sentinel = [Segment(i=99, start=0.0, end=1.0, text="SENTINEL")]
    seen: list[list[Segment]] = []

    def spy(segments, **kwargs):
        seen.append(list(segments))
        return sentinel

    monkeypatch.setattr(fw_module, "normalize", spy)
    engine = FasterWhisperEngine(asr_spec, model_factory=factory)

    assert engine.transcribe("a.wav", "zh") is sentinel
    assert len(seen) == 1, "normalize phải được gọi đúng một lần"
    assert [s.text for s in seen[0]] == ["你好", "感谢观看"], (
        "đầu vào của normalize phải là to_segments(raw): chữ đã strip, nhãn ảo giác còn nguyên"
    )


class _FakeBatchedPipeline:
    instances: list["_FakeBatchedPipeline"] = []

    def __init__(self, *, model) -> None:
        self.model = model
        self.segments = [_Seg(0.0, 2.0, "你好", avg_logprob=-0.3, no_speech_prob=0.02)]
        self.calls: list[tuple[str, dict]] = []
        _FakeBatchedPipeline.instances.append(self)

    def transcribe(self, audio_path, **kwargs):
        self.calls.append((audio_path, kwargs))
        return iter(self.segments), _Info()


def test_engine_batched_branch_uses_batched_pipeline(asr_spec, monkeypatch):
    """`batch_size > 1` phải đi qua BatchedInferencePipeline, không qua model.

    `faster_whisper` được thay bằng module giả trong `sys.modules`, nên bài test
    không nạp thư viện thật và chắc chắn không tải model nào.
    """
    _FakeBatchedPipeline.instances = []
    fake_module = types.ModuleType("faster_whisper")
    fake_module.BatchedInferencePipeline = _FakeBatchedPipeline
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)

    factory = _RecordingModelFactory()
    engine = FasterWhisperEngine(
        _with_opts(asr_spec, batch_size=4, initial_prompt="xin chào"),
        model_factory=factory,
    )
    first = engine.transcribe("a.wav", "zh")
    engine.transcribe("b.wav", "zh")

    assert factory.models[0].transcribe_calls == [], (
        "nhánh batch không được gọi thẳng model.transcribe"
    )
    assert len(_FakeBatchedPipeline.instances) == 1, (
        "pipeline batch phải được giữ lại giữa hai lần transcribe"
    )
    batched = _FakeBatchedPipeline.instances[0]
    assert batched.model is factory.models[0]
    assert [c[0] for c in batched.calls] == ["a.wav", "b.wav"]
    assert batched.calls[0][1] == {
        "language": "zh", "batch_size": 4, "vad_filter": True,
        "word_timestamps": True, "condition_on_previous_text": False,
        "initial_prompt": "xin chào",
    }
    assert [s.text for s in first] == ["你好"]


def _block_torch_import(monkeypatch) -> None:
    """Làm `import torch` nổ ImportError một cách TẤT ĐỊNH, không phụ thuộc máy."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("torch bị chặn trong test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_release_is_no_arg_idempotent_and_survives_missing_torch(asr_spec, monkeypatch):
    """R42: release() sẽ được đăng ký làm callback đổ model của governor."""
    _block_torch_import(monkeypatch)
    factory = _RecordingModelFactory()
    engine = FasterWhisperEngine(asr_spec, model_factory=factory)

    engine.release()          # chưa nạp gì
    engine.release()          # gọi lại: phải idempotent
    assert factory.calls == [], "release() không được nạp model"

    engine.transcribe("a.wav", "zh")
    engine.release()
    assert engine._model is None and engine._batched is None

    engine.transcribe("a.wav", "zh")
    assert len(factory.calls) == 2, "release() phải thật sự nhả để lần sau nạp lại"


def test_release_empties_cuda_cache_only_when_torch_reports_a_gpu(asr_spec, monkeypatch):
    calls: list[str] = []
    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(
        is_available=lambda: True, empty_cache=lambda: calls.append("empty"))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    FasterWhisperEngine(asr_spec, model_factory=_RecordingModelFactory()).release()
    assert calls == ["empty"]

    fake_torch.cuda = types.SimpleNamespace(
        is_available=lambda: False, empty_cache=lambda: calls.append("empty"))
    FasterWhisperEngine(asr_spec, model_factory=_RecordingModelFactory()).release()
    assert calls == ["empty"], "không có GPU thì không được gọi empty_cache"


# --------------------------------------------------------------------------
# R55: `release()` là unload callback của governor (Task 15) và governor gọi
# `releaser()` KHÔNG có try/except ở cả `before_phase` lẫn `after_phase`. Một
# exception lọt ra khỏi đây sẽ bỏ dở cả vòng đổ model -> các model khác vẫn nằm
# trong VRAM và chuyển giai đoạn hỏng. Bản cũ chỉ bắt `ImportError`, nên hai
# đường đi THẬT dưới đây đều lọt ra ngoài.
# --------------------------------------------------------------------------

def _load_engine_with_model_and_batched(asr_spec, monkeypatch):
    """Trả về engine đang giữ CẢ `_model` lẫn `_batched` (đều khác None).

    Phải nạp qua nhánh `batch_size > 1` thì `_batched` mới được set; nếu chỉ
    nạp `_model` thì `_batched` vốn đã None từ đầu và khẳng định "đã xoá
    `_batched`" là vô nghĩa.
    """
    fake_module = types.ModuleType("faster_whisper")
    fake_module.BatchedInferencePipeline = _FakeBatchedPipeline
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)

    engine = FasterWhisperEngine(_with_opts(asr_spec, batch_size=4),
                                 model_factory=_RecordingModelFactory())
    engine.transcribe("a.wav", "zh")
    assert engine._model is not None and engine._batched is not None, (
        "test chỉ có nghĩa khi cả hai thuộc tính ĐANG được set trước release()"
    )
    return engine


def test_release_survives_oserror_from_a_broken_torch_install(asr_spec, monkeypatch):
    """R55: torch cài hỏng ném `OSError [WinError 126]` ngay lúc `import torch`.

    `OSError` KHÔNG phải lớp con của `ImportError`, nên `except ImportError` cũ
    để nguyên exception bay ra ngoài `release()`.
    """
    assert not issubclass(OSError, ImportError), (
        "đây là toàn bộ lý do phải bắt rộng: nếu OSError là ImportError thì bản cũ đã đủ"
    )
    engine = _load_engine_with_model_and_batched(asr_spec, monkeypatch)
    real_import = builtins.__import__

    def broken_import(name, *args, **kwargs):
        if name == "torch":
            raise OSError("[WinError 126] Không tìm thấy module được chỉ định")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_import)

    engine.release()          # không được ném

    assert engine._model is None and engine._batched is None, (
        "hai tham chiếu model phải được xoá TRƯỚC khối try, kể cả khi dọn torch nổ"
    )


def test_release_survives_runtimeerror_from_cuda_is_available(asr_spec, monkeypatch):
    """R55: `torch.cuda.is_available()` ném `RuntimeError` khi driver/CUDA hỏng."""
    engine = _load_engine_with_model_and_batched(asr_spec, monkeypatch)

    def boom():
        raise RuntimeError("CUDA driver không khả dụng")

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(is_available=boom, empty_cache=lambda: None)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    engine.release()          # không được ném

    assert engine._model is None and engine._batched is None, (
        "hai tham chiếu model phải được xoá TRƯỚC khối try, kể cả khi is_available nổ"
    )
