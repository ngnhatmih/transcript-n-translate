"""R68 — quyết định cho audio IM LẶNG: job `FAILED`, KHÔNG phải transcript rỗng.

Guard `if not segments: raise RuntimeError("SenseVoice không trả về đoạn nào")`
trong `app/adapters/asr/sensevoice.py` được **GIỮ NGUYÊN**. Bài ở đây ghim HỆ
QUẢ ở tầng JOB — đúng chỗ trước đây không bài nào canh: một tệp chỉ có im lặng
đi hết đường ống thì job `asr` phải thành `FAILED` kèm lý do đọc được, và
**KHÔNG** được sinh ra một transcript rỗng rồi báo xanh.

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


class _SilentModel:
    """FunASR trên audio im lặng: `generate()` không trả về đoạn nào có tiếng."""

    def __init__(self, raw):
        self.raw = raw

    def generate(self, **kwargs):
        return self.raw


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


@pytest.mark.parametrize("raw", [
    [],                                   # hoàn toàn không có item
    [{"text": "", "start": 0, "end": 0}],  # có item nhưng rỗng sau khi bóc tag
])
def test_silent_audio_fails_the_job_and_writes_no_transcript(repos, tmp_path, raw):
    wav = tmp_path / "silence.wav"
    wav.write_bytes(b"RIFF")
    source_id = repos.add_source(kind="file", origin="silence.wav",
                                 media_path=str(wav), lang="zh",
                                 audio_path=str(wav), duration=1.0)

    handler = TranscribeHandler(
        repos, [SENSEVOICE],
        lambda spec: SenseVoiceEngine(
            spec, model_factory=lambda **kwargs: _SilentModel(raw)),
        workdir=tmp_path,
    )
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": handler})
    repos.add_job(Job(id=None, workspace=1, type="asr", engine="sensevoice-small",
                      phase=js.phase_of("asr", "sensevoice-small"),
                      payload={"source_id": source_id}))

    while worker.tick():
        pass

    jobs = repos.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].state == js.FAILED, (
        "im lặng phải thành job FAILED — guard không được xoá và không được "
        "biến thành thành công giả"
    )
    assert "không trả về đoạn nào" in (jobs[0].error or ""), (
        f"lý do phải đọc được, thực tế: {jobs[0].error!r}"
    )
    assert repos.list_transcripts() == [], (
        "KHÔNG được lưu transcript rỗng: nó giấu mất lỗi và báo xanh cho một "
        "job không có nội dung"
    )
    assert [j for j in jobs if j.type == "translate"] == [], (
        "job hỏng thì không được auto_forward sang workspace 2"
    )
