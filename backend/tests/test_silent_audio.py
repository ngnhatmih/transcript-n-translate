"""R68 — quyết định cho audio IM LẶNG: job `FAILED`, KHÔNG phải transcript rỗng.

Bất biến này phải đúng cho **MỌI engine**, không riêng engine nào. Guard riêng
của `SenseVoiceEngine` (`app/adapters/asr/sensevoice.py:82-83`) được **GIỮ
NGUYÊN**, nhưng nó không phủ được engine mặc định của GĐ1a
(`fw-large-v3-turbo`, mục ASR đầu tiên trong `registry.json`) — và
`FasterWhisperEngine` KHÔNG có guard nào. Vì vậy `TranscribeHandler.run` giữ
guard thứ hai, độc lập engine, ngay sau `engine.transcribe(...)`: đó mới là chỗ
bảo đảm quyết định R68 trên đường chạy thật.

Bài ở đây ghim HỆ QUẢ ở tầng JOB — đúng chỗ trước đây không bài nào canh: một
tệp chỉ có im lặng đi hết đường ống thì job `asr` phải thành `FAILED` kèm lý do
đọc được, và **KHÔNG** được sinh ra một transcript rỗng rồi báo xanh.

Hai họ engine được lái qua **cùng** `TranscribeHandler` + `PhaseQueueWorker`
thật:

* `SenseVoiceEngine` — model FunASR giả trả `generate()` rỗng.
* `FasterWhisperEngine` — model giả **đúng hình dạng faster-whisper**
  (`transcribe()` trả `(iterator, info)`); `iterator` rỗng ⇒ 0 đoạn. Đây là
  engine mặc định, và là ca đã lọt lưới ở vòng trước: 0 đoạn, không exception,
  job `done`, và một hàng transcript `(1, 0)` trong DB.

Vì sao chọn FAILED (chứ không phải transcript rỗng): một transcript rỗng trông
y hệt một lần bóc băng thành công mà không có tiếng nói, nên nó giấu mất lỗi
giải mã/thiếu model. Cùng triết lý với R62 — "đầu ra rác mà báo xanh tệ hơn hẳn
một lỗi ồn ào". Đây là quyết định **có thể đảo ngược**, và điều kiện để đảo là
DỮ LIỆU: lần chạy SenseVoice thật đầu tiên trên một tệp im lặng xem upstream
trả gì (xem `task-20-report.md`, mục R68).
"""
from __future__ import annotations

import pathlib

import pytest

from app.adapters.asr.faster_whisper import FasterWhisperEngine
from app.adapters.asr.sensevoice import SenseVoiceEngine
from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.domain.models import Job
from app.pipeline.transcribe import TranscribeHandler
from app.registry import EngineSpec
from app.worker import PhaseQueueWorker
from tests.fakes import FakeGovernor

SENSEVOICE = EngineSpec(
    id="sensevoice-small", label="SenseVoice", kind="asr", runtime="inprocess",
    model_ref="iic/SenseVoiceSmall", vram_mb=1000, langs=("zh",),
    capabilities={}, opts={},
)

FASTER_WHISPER = EngineSpec(
    id="fw-large-v3-turbo", label="Faster Whisper", kind="asr", runtime="inprocess",
    model_ref="large-v3-turbo", vram_mb=1600, langs=("zh", "en"),
    capabilities={}, opts={},
)

# Engine không có trong registry và không có adapter nào ở đây: chỉ để chứng minh
# guard nằm ở HANDLER, không nằm ở một adapter cụ thể.
UNKNOWN_ENGINE = EngineSpec(
    id="some-future-engine", label="Engine tương lai", kind="asr",
    runtime="inprocess", model_ref="whatever", vram_mb=500, langs=("zh",),
    capabilities={}, opts={},
)


class _SilentModel:
    """FunASR trên audio im lặng: `generate()` không trả về đoạn nào có tiếng."""

    def __init__(self, raw):
        self.raw = raw

    def generate(self, **kwargs):
        return self.raw


class _WhisperShapedModel:
    """Model giả ĐÚNG hình dạng `faster_whisper.WhisperModel`.

    `FasterWhisperEngine.transcribe()` gọi `model.transcribe(...)` rồi mở gói
    `(iterator, info)`. Trả về một iterator RỖNG là cách trung thực nhất để mô
    phỏng "VAD đã bỏ hết, không còn đoạn nào" mà không cần tải weight nào.
    """

    def __init__(self, segments=()):
        self.segments = list(segments)
        self.calls: list[dict] = []

    def transcribe(self, audio_path, **kwargs):
        self.calls.append({"audio_path": audio_path, **kwargs})
        return iter(self.segments), {"language": kwargs.get("language")}


class _ZeroSegmentEngine:
    """Engine thứ BA, KHÔNG dính dáng gì tới hai adapter trên.

    Nó trả `[]` trần trụi và KHÔNG BAO GIỜ ném — đúng ca đã lọt lưới. Bài dùng
    nó để phép kiểm không còn phụ thuộc vào việc adapter nào có guard riêng:
    nếu guard nằm ở `TranscribeHandler.run` thì engine nào cũng bị chặn.
    """

    def __init__(self, spec):
        self.engine_id = spec.id
        self.spec = spec

    def transcribe(self, audio_path, lang):
        return []

    def release(self):
        pass


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def _build(engine_key: str, raw):
    """Trả (spec, factory) cho một họ engine — cả ba đi qua handler THẬT."""

    def sensevoice_model(**kwargs):
        return _SilentModel(raw)

    def faster_whisper_model(*args, **kwargs):
        return _WhisperShapedModel()

    if engine_key == "sensevoice":
        return SENSEVOICE, lambda spec: SenseVoiceEngine(
            spec, model_factory=sensevoice_model)
    if engine_key == "faster_whisper":
        return FASTER_WHISPER, lambda spec: FasterWhisperEngine(
            spec, model_factory=faster_whisper_model)
    return UNKNOWN_ENGINE, _ZeroSegmentEngine


@pytest.mark.parametrize("engine_key",
                         ["sensevoice", "faster_whisper", "unknown_engine"])
@pytest.mark.parametrize("raw", [
    [],                                   # hoàn toàn không có item
    [{"text": "", "start": 0, "end": 0}],  # có item nhưng rỗng sau khi bóc tag
])
def test_silent_audio_fails_the_job_and_writes_no_transcript(
        repos, tmp_path, engine_key, raw):
    wav = tmp_path / "silence.wav"
    wav.write_bytes(b"RIFF")
    source_id = repos.add_source(kind="file", origin="silence.wav",
                                 media_path=str(wav), lang="zh",
                                 audio_path=str(wav), duration=1.0)

    spec, factory = _build(engine_key, raw)
    handler = TranscribeHandler(repos, [spec], factory, workdir=tmp_path)
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": handler})
    repos.add_job(Job(id=None, workspace=1, type="asr", engine=spec.id,
                      phase=js.phase_of("asr", spec.id),
                      payload={"source_id": source_id}))

    while worker.tick():
        pass

    jobs = repos.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].state == js.FAILED, (
        f"[{engine_key}] im lặng phải thành job FAILED — guard ở tầng handler "
        f"không được xoá và không được biến thành thành công giả"
    )
    # `SenseVoiceEngine` có guard riêng; hai engine còn lại dựa vào guard của
    # handler. Tất cả đều phải nói ĐÚNG chuyện "không có đoạn nào", không được
    # là một thông báo chung chung.
    error = jobs[0].error or ""
    assert "trả về đoạn nào" in error or "có đoạn nào" in error, (
        f"[{engine_key}] lý do phải đọc được, thực tế: {jobs[0].error!r}"
    )
    assert repos.list_transcripts() == [], (
        f"[{engine_key}] KHÔNG được lưu transcript rỗng: nó giấu mất lỗi và báo "
        f"xanh cho một job không có nội dung"
    )
    assert [j for j in jobs if j.type == "translate"] == [], (
        f"[{engine_key}] job hỏng thì không được auto_forward sang workspace 2"
    )
