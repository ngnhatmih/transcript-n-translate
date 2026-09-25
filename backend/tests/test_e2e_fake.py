"""Task 19: chạy CẢ đường ống với engine giả — không tốn một MB VRAM.

Đây là lợi ích cụ thể của việc phân tầng: `domain` thuần nên thay engine thật
bằng engine giả là chuyện bình thường, không phải hack. Không có test này thì
mỗi tầng đều xanh riêng lẻ mà không chỗ nào chứng minh chúng nối được với nhau:
upload -> ingest -> asr -> export -> tải về.

## Fixture đi qua ĐÚNG bộ ráp của production

`wired` gọi `main.build_components()` + `main.build_app()` (main.py:32-84) chứ
KHÔNG tự ráp lại `PhaseQueueWorker`/`create_app`. Nhờ vậy mọi dây của production
đều được chạy thật và test không thể trôi khỏi nó: vòng `governor.register()`
cho từng spec ASR (main.py:61-65), `auto_forward="0"` mặc định (main.py:71-72),
`publish=broker.publish` ở worker (main.py:55), và `broker=` ở app
(main.py:83-84). Chỉ DUY NHẤT khúc ffmpeg bị thay (`StubIngest`), vì
`IngestHandler` thật cần ffmpeg.

`ensure_dirs()` (config.py:38-40) đọc biến toàn cục của CHÍNH `app.config`, nên
fixture phải vá CẢ `app.config` lẫn `main`: vá mỗi `main` thì
`main.build_components()` vẫn tạo `data/` THẬT của repo.

## Vì sao có ĐÚNG hai lần đổi giai đoạn

Production đặt `auto_forward="0"` (main.py:71-72), nên job ASR KHÔNG đẻ job
`translate`, và nhịp chạy chỉ vào hai giai đoạn:

    ingest:-               x3  -> vào giai đoạn lần 1
    asr:fw-large-v3-turbo  x3  -> vào giai đoạn lần 2
    hàng đợi cạn           -> tick() trả False

`phase_switches` KHÔNG phải một quan sát độc lập với `governor.entered`: cả hai
đều được đặt trong `worker._enter_phase` (worker.py:117-120) với cùng một tham
số `phase`, nên về cấu trúc `phase_switches == len(entered)`. Test khẳng định
đúng đẳng thức đó, không trình bày chúng như hai nhân chứng.

Đường `translate` của GĐ1a (job không có handler -> FAILED ồn ào) vẫn được canh,
nhưng bằng một job XẾP TAY trong `test_full_pipeline_from_upload_to_srt`, không
mượn `auto_forward` bật — đó là cấu hình production không chạy.
"""
from __future__ import annotations

import asyncio
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.adapters.governor.single_gpu import SingleGpuGovernor
from app.domain import job_state as js
from app.domain.models import Job, Segment
from app.pipeline.transcribe import AUTO_FORWARD_SETTING
from app.registry import EngineSpec

ASR_SPEC = EngineSpec(id="fw-large-v3-turbo", label="FW", kind="asr", runtime="inprocess",
                      model_ref="large-v3-turbo", vram_mb=1600, langs=("zh", "en"),
                      capabilities={}, opts={})
MT_SPEC = EngineSpec(id="qwen2.5-7b", label="Qwen", kind="mt", runtime="ollama",
                     model_ref="qwen2.5:7b", vram_mb=5200, langs=("zh",),
                     capabilities={}, opts={})


class FakeASREngine:
    """Trả về transcript cố định, gồm cả một đoạn nghi ngờ."""

    def __init__(self, spec: EngineSpec) -> None:
        self.engine_id = spec.id
        self.release_count = 0

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        return [
            Segment(i=0, start=0.0, end=3.0, text="大家好"),
            Segment(i=1, start=3.0, end=5.0, text="今天我们要聊的是人工智能"),
            Segment(i=2, start=5.0, end=8.0, text="这个模型它其实……",
                    no_speech_prob=0.85, avg_logprob=-1.9, suspect=True),
        ]

    def release(self) -> None:
        self.release_count += 1


class TracingGovernor(SingleGpuGovernor):
    """`SingleGpuGovernor` THẬT + ghi lại giai đoạn nào đã được vào, theo thứ tự.

    Không đổi hành vi: mọi lệnh đều gọi `super()`. `worker._enter_phase` gọi
    `governor.before_phase(phase)` đúng MỘT lần cho mỗi giai đoạn, và
    `worker.phase_switches` được tăng ngay cạnh đó, nên `entered` là truy vết còn
    con số kia chỉ là `len(entered)` — không phải hai phép đo độc lập.
    """

    def __init__(self, repos) -> None:
        super().__init__(repos)
        self.entered: list[str] = []

    def before_phase(self, phase: str) -> None:
        self.entered.append(phase)
        super().before_phase(phase)


class StubIngest:
    """`IngestHandler` thật cần ffmpeg; đây là chỗ DUY NHẤT còn là hàng giả.

    Nó tái hiện đúng hai tác động của `IngestHandler.run` (ingest.py:196-215):
    ghi tệp audio + `set_source_audio`, rồi xếp job ASR — engine và phase lấy từ
    chính spec trong registry, không hard-code.
    """

    def __init__(self, repos, specs) -> None:
        self._repos = repos
        self._asr = next(s for s in specs if s.kind == "asr")

    def handles(self) -> str:
        return "ingest"

    def run(self, job, report) -> None:
        sid = job.payload["source_id"]
        source = self._repos.get_source(sid)
        # R37: tệp wav phải TỒN TẠI, nếu không `TranscribeHandler` ném
        # FileNotFoundError và job ASR thành FAILED.
        audio = pathlib.Path(source.media_path).with_suffix(".wav")
        audio.write_bytes(b"stub-wav")
        self._repos.set_source_audio(sid, str(audio), 8.0)
        # R7: và phải TẠO JOB ASR — không có nó thì không có gì chạy bóc băng.
        self._repos.add_job(Job(id=None, workspace=1, type="asr",
                                engine=self._asr.id, phase=self._asr.phase_key,
                                payload={"source_id": sid}))
        report(1.0, "ingest giả")


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """Ráp app bằng ĐÚNG `main.build_components()` + `main.build_app()`.

    Chỉ ba thứ được thay: registry (spec nhỏ, không nạp model), engine thật
    (bằng `FakeASREngine`) và governor (bằng `TracingGovernor`, vẫn là
    `SingleGpuGovernor` thật). Mọi đường dẫn bị chuyển vào `tmp_path` — cả
    `app.config` lẫn `main`, vì `ensure_dirs()` đọc biến toàn cục của
    `app.config` chứ không đọc tên đã import vào `main`.
    """
    from app import config, main

    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(config, "LOG_DIR", data / "logs")
    monkeypatch.setattr(config, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "DB_PATH", data / "app.db")
    monkeypatch.setattr(main, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(main, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "LOG_DIR", data / "logs")

    created: list[FakeASREngine] = []

    def factory(spec):
        engine = FakeASREngine(spec)
        created.append(engine)
        return engine

    monkeypatch.setattr(main, "load_registry", lambda: [ASR_SPEC, MT_SPEC])
    monkeypatch.setattr(main, "_engine_factory", factory)
    monkeypatch.setattr(main, "SingleGpuGovernor", TracingGovernor)

    repos, specs, worker, broker = main.build_components()
    # ingest thật cần ffmpeg; đó là khúc duy nhất còn giả.
    worker.handlers["ingest"] = StubIngest(repos, specs)
    app = main.build_app(repos, specs, worker, broker)

    with TestClient(app) as c:
        c.repos = repos
        c.worker = worker
        c.created = created
        c.governor = worker.governor
        c.broker = broker
        yield c


def _drain_with_stream(wired) -> list[dict]:
    """Đổ hàng đợi trong lúc NGHE broker của app.

    `main.build_components()` trao CHÍNH broker đó cho worker (`publish=`), và
    `main.build_app()` trao nó cho app; bỏ một trong hai dây là
    `/api/jobs/stream` câm vĩnh viễn dù job chạy xong.
    """
    async def run() -> list[dict]:
        sub = wired.app.state.broker.subscribe()
        try:
            wired.worker.recover()
            while wired.worker.tick():
                pass
            collected: list[dict] = []
            for _ in range(200):
                event = await sub.wait(2.0)
                assert event is not None, (
                    "worker không publish vào broker của app "
                    f"(mới nhận {len(collected)} sự kiện)"
                )
                collected.append(event)
                if event["state"] == "done":
                    break
            return collected
        finally:
            wired.app.state.broker.unsubscribe(sub)

    return asyncio.run(run())


def test_full_pipeline_from_upload_to_srt(wired):
    """upload -> ingest -> asr -> export -> tải về (đường dịch xếp tay ở dưới)."""
    resp = wired.post("/api/sources/upload",
                      files={"file": ("clip.mp4", b"x" * 64, "video/mp4")},
                      data={"lang": "zh"})
    assert resp.status_code == 201

    events = _drain_with_stream(wired)
    assert events[0]["state"] == "running" and events[-1]["state"] == "done", events

    transcripts = wired.get("/api/transcripts").json()
    assert len(transcripts) == 1
    tid = transcripts[0]["id"]

    detail = wired.get(f"/api/transcripts/{tid}").json()
    assert detail["version"] == 1
    assert [s["text"] for s in detail["segments"]][0] == "大家好"
    assert detail["segments"][2]["suspect"] is True

    running = wired.get("/api/status").json()
    assert running["queue_depth"] == 0, "hàng đợi phải cạn"

    # GĐ1a chưa có handler dịch: job phải FAILED RÕ RÀNG chứ không treo ở `queued`.
    # Không thêm handler giả cho `translate` — làm vậy là che mất đúng cái lỗ hổng
    # mà khẳng định này canh. Nhưng cấu hình production có `auto_forward="0"`, nên
    # đường bóc băng KHÔNG đẻ job dịch: muốn canh nhánh này thì phải TỰ xếp job,
    # đừng mượn `auto_forward` bật (đó là cấu hình production không chạy).
    assert wired.repos.get_setting(AUTO_FORWARD_SETTING) == "0", (
        "production đặt auto_forward='0' (main.py:71-72); fixture phải giống"
    )
    jobs = wired.get("/api/jobs").json()
    assert [j for j in jobs if j["type"] == "translate"] == [], (
        "auto_forward='0' không được đẻ job dịch"
    )

    source_id = wired.repos.list_sources()[0].id
    wired.repos.add_job(Job(
        id=None, workspace=2, type="translate", engine=MT_SPEC.id,
        phase=js.phase_of("translate", MT_SPEC.id),
        payload={"transcript_id": tid, "source_id": source_id, "lang": "zh"},
    ))
    while wired.worker.tick():
        pass

    translate_jobs = [j for j in wired.get("/api/jobs").json() if j["type"] == "translate"]
    assert len(translate_jobs) == 1
    assert translate_jobs[0]["state"] == "failed", (
        "GĐ1a chưa có handler dịch; job phải failed rõ ràng chứ không treo"
    )
    assert "không có handler" in (translate_jobs[0]["error"] or "")
    assert wired.governor.entered[-1] == js.phase_of("translate", MT_SPEC.id), (
        f"job dịch xếp tay phải mở giai đoạn dịch: {wired.governor.entered}"
    )

    read = wired.get(f"/api/transcripts/{tid}/readability",
                     params={"threshold": 5.0}).json()
    assert 1 in [item["i"] for item in read["too_fast"]], (
        "đoạn 1 = 6,00 CPS > ngưỡng 5,0 (CPS_WARN 20,0 sẽ không gắn cờ đoạn nào)"
    )

    exp = wired.post("/api/export", json={"transcript_id": tid, "format": "srt"})
    assert exp.status_code == 201
    job_id = exp.json()["id"]
    while wired.worker.tick():
        pass

    dl = wired.get(f"/api/export/{job_id}/download")
    assert dl.status_code == 200
    text = dl.text
    assert "1\n00:00:00,000 --> 00:00:03,000\n大家好" in text
    assert text.count("-->") == 3


def test_fake_asr_model_loaded_exactly_once_for_the_phase(wired):
    for n in range(3):
        wired.post("/api/sources/upload",
                   files={"file": (f"c{n}.mp4", b"x" * 64, "video/mp4")},
                   data={"lang": "zh"})
    wired.worker.recover()
    while wired.worker.tick():
        pass

    assert len(wired.created) == 1, (
        f"3 job cùng engine phải nạp model 1 lần, thực tế {len(wired.created)}"
    )
    # Đây là cấu hình PRODUCTION: `main.build_components()` đặt `auto_forward="0"`
    # (main.py:71-72). Fixture tự ráp dây thì biến đó vắng mặt, `TranscribeHandler`
    # hiểu là BẬT, và test sẽ khẳng định một cấu hình production không chạy.
    assert wired.repos.get_setting(AUTO_FORWARD_SETTING) == "0", (
        "fixture phải chạy đúng cấu hình production (auto_forward='0')"
    )
    assert wired.governor.entered == ["ingest:-", "asr:fw-large-v3-turbo"], (
        f"truy vết giai đoạn sai: {wired.governor.entered}"
    )
    # `phase_switches` KHÔNG phải một quan sát độc lập với `entered`: cả hai đều
    # được đặt trong `worker._enter_phase` (worker.py:117-120) với cùng một tham
    # số `phase`. Đây là MỘT đẳng thức, không phải hai nhân chứng.
    assert wired.worker.phase_switches == len(wired.governor.entered) == 2, (
        "auto_forward='0' chỉ vào ingest:- rồi asr:fw-large-v3-turbo, "
        f"thực tế {wired.worker.phase_switches} lần đổi giai đoạn: "
        f"{wired.governor.entered}"
    )
    # Rời giai đoạn ASR là model phải được ĐỔ, qua đúng vòng
    # `governor.register()` mà `main.py:61-65` chạy. `release()` của handler
    # idempotent nên gọi lặp không tính thêm lần nào.
    assert wired.created[0].release_count == 1, (
        "đổi giai đoạn mà không đổ model thì VRAM rò rỉ: "
        f"{wired.created[0].release_count} lần đổ"
    )


def test_layer_boundary_still_holds_after_everything(wired):
    """Nhắc lại: nếu test này đỏ thì ai đó đã import hạ tầng vào domain."""
    from tests.test_layer_boundary import test_domain_has_no_forbidden_absolute_imports
    test_domain_has_no_forbidden_absolute_imports()
