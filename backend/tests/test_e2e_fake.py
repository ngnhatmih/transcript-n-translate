"""Task 19: chạy CẢ đường ống với engine giả — không tốn một MB VRAM.

Đây là lợi ích cụ thể của việc phân tầng: `domain` thuần nên thay engine thật
bằng engine giả là chuyện bình thường, không phải hack. Không có test này thì
mỗi tầng đều xanh riêng lẻ mà không chỗ nào chứng minh chúng nối được với nhau:
upload -> ingest -> asr -> export -> tải về.

## Fixture đi qua ĐÚNG bộ ráp của production

`wired` gọi `main.build_components()` + `main.build_app()` chứ KHÔNG tự ráp lại
`PhaseQueueWorker`/`create_app`. Nhờ vậy mọi dây của production đều được chạy
thật và test không thể trôi khỏi nó: vòng `governor.register()` cho từng spec ASR
và từng engine dịch (main.py), `auto_forward="1"` mặc định, `publish=broker.publish`
ở worker, và `broker=` ở app. Chỉ DUY NHẤT hai adapter model bị thay
(`StubIngest` cho khúc ffmpeg của `IngestHandler`, `FakeMtEngine` cho khúc HTTP
tới Ollama).

`ensure_dirs()` (config.py:38-40) đọc biến toàn cục của CHÍNH `app.config`, nên
fixture phải vá CẢ `app.config` lẫn `main`: vá mỗi `main` thì
`main.build_components()` vẫn tạo `data/` THẬT của repo.

## Vì sao nay có BA lần đổi giai đoạn

Task 12 nối handler `translate` vào composition root và đổi `auto_forward` mặc
định sang `"1"`, nên bóc băng xong THẬT SỰ đẻ ra job dịch và worker chạy nó:

    ingest:-                     x3  -> vào giai đoạn lần 1
    asr:fw-large-v3-turbo        x3  -> vào giai đoạn lần 2
    translate:qwen2.5-7b         x3  -> vào giai đoạn lần 3
    hàng đợi cạn                 -> tick() trả False

`phase_switches` KHÔNG phải một quan sát độc lập với `governor.entered`: cả hai
đều được đặt trong `worker._enter_phase` (worker.py:117-120) với cùng một tham
số `phase`, nên về cấu trúc `phase_switches == len(entered)`. Test khẳng định
đúng đẳng thức đó, không trình bày chúng như hai nhân chứng.

Engine dịch thật (`OllamaMtEngine`) bị thay bằng `FakeMtEngine` đúng như engine
ASR bị thay: khúc HTTP tới Ollama là thứ duy nhất còn là hàng giả, còn VIỆC RÁP
DÂY (`mt_engines`, `governor.register`, `TranslateHandler`) là của `main.py`.
"""
from __future__ import annotations

import asyncio
import dataclasses
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.adapters.governor.single_gpu import SingleGpuGovernor
from app.adapters.mt.prompts import PROMPT_VERSION
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
        #
        # 🔴 WAV PHAI HOP LE, khong phai vai byte rac (do duoc). Ban dau o day ghi
        # `b"stub-wav"` — 9 byte, khong phai tep WAV. Duong ASR cu chi MO tep nen no
        # khong bao gio lo ra; nhung khi `run` di qua OCR, adapter goi `ffprobe` de
        # biet kich thuoc khung va no chet:
        #   CalledProcessError: ffprobe ... returned non-zero exit status 1
        # => job asr failed, 0 transcript, va test do vi mot ly do KHONG LIEN QUAN
        # toi thu no dinh kiem. Ghi WAV that bang `soundfile` (da co san trong venv,
        # va khong can ffmpeg): 1 giay im lang, 16 kHz, mono.
        audio = pathlib.Path(source.media_path).with_suffix(".wav")
        import numpy as np
        import soundfile as sf
        sf.write(str(audio), np.zeros(16_000, dtype=np.float32), 16_000)
        self._repos.set_source_audio(sid, str(audio), 8.0)
        # R7: và phải TẠO JOB ASR — không có nó thì không có gì chạy bóc băng.
        self._repos.add_job(Job(id=None, workspace=1, type="asr",
                                engine=self._asr.id, phase=self._asr.phase_key,
                                payload={"source_id": sid}))
        report(1.0, "ingest giả")


class FakeMtEngine:
    """Engine dịch giả: chỉ thay đúng khúc HTTP tới Ollama.

    `translate` dùng `dataclasses.replace` chứ KHÔNG dựng `Segment(...)` bằng tay
    (hai task trong phase này đã nuốt 7/13 trường theo cách đó).
    """

    def __init__(self, model_ref: str, *, supports_glossary: bool = False,
                 engine_id: str | None = None,
                 base_url: str | None = None) -> None:
        self.model_ref = model_ref
        self._supports_glossary = supports_glossary
        #: M-10: `OllamaMtEngine` THẬT nhận `base_url` (địa chỉ do composition
        #: root phân giải từ `OLLAMA_HOST`); bản giả phải nuốt được đúng cách gọi
        #: đó, nếu không `_build_mt_engines` nổ `TypeError` ngay ở fixture.
        self.base_url = base_url
        #: Fix round 1 (I-2): `_build_mt_engines` truyền `spec.id` TƯỜNG MINH vào
        #: adapter Ollama, nên engine giả phải nhận tham số đó (giống chữ ký của
        #: `OllamaMtEngine`) — và ghi lại để bài ghim dây nối đọc được.
        self.received_engine_id = engine_id
        self.release_count = 0
        self.batches: list[list[int]] = []
        self.last_stats = None

    @property
    def engine_id(self) -> str:
        return "fake-mt"

    def supports_glossary(self) -> bool:
        return self._supports_glossary

    def translate(self, batch, glossary, opts):
        self.batches.append([s.i for s in batch])
        return [dataclasses.replace(s, text=f"[{opts.target_lang}] {s.text}")
                for s in batch]

    def release(self) -> None:
        self.release_count += 1


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """Ráp app bằng ĐÚNG `main.build_components()` + `main.build_app()`.

    Chỉ bốn thứ được thay: registry (spec nhỏ, không nạp model), engine thật
    (bằng `FakeASREngine`/`FakeMtEngine`), governor (bằng `TracingGovernor`, vẫn
    là `SingleGpuGovernor` thật) và phép dò Ollama (ghim `True` để suite không
    phụ thuộc việc Ollama có đang chạy trên máy hay không). Mọi đường dẫn bị
    chuyển vào `tmp_path` — cả `app.config` lẫn `main`, vì `ensure_dirs()` đọc
    biến toàn cục của `app.config` chứ không đọc tên đã import vào `main`.
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
    mt_created: list[FakeMtEngine] = []

    def factory(spec):
        engine = FakeASREngine(spec)
        created.append(engine)
        return engine

    def mt_factory(*args, **kwargs):
        engine = FakeMtEngine(*args, **kwargs)
        mt_created.append(engine)
        return engine

    monkeypatch.setattr(main, "load_registry", lambda: [ASR_SPEC, MT_SPEC])
    # WQ-02/F3: composition root nay đối chiếu `default_mt` với chính `specs` và
    # hỏng NGAY lúc dựng khi không khớp, nên registry GIẢ ở trên phải đi kèm một
    # mặc định GIẢ trỏ vào id CÓ THẬT trong đó — `registry.json` thật khai báo
    # `opus-mt`, id không có trong danh sách rút gọn này.
    monkeypatch.setattr(main, "load_default_mt", lambda: MT_SPEC.id)
    monkeypatch.setattr(main, "_engine_factory", factory)
    monkeypatch.setattr(main, "SingleGpuGovernor", TracingGovernor)
    # Task 12: `MT_SPEC` là runtime `ollama`, nên `available` của nó do phép dò
    # quyết định. Ghim để suite tất định, và thay adapter HTTP bằng engine giả.
    # Fix round 1 (I-1): phép dò trả về TÊN model đã pull, nên ở đây trả đúng
    # `MT_SPEC.model_ref` — "Ollama sống" không còn đủ để engine sẵn sàng.
    monkeypatch.setattr(main, "ollama_available",
                        lambda *a, **k: {MT_SPEC.model_ref})
    monkeypatch.setattr(main, "OllamaMtEngine", mt_factory)

    repos, specs, worker, broker, mt_engines = main.build_components()
    # ingest thật cần ffmpeg; đó là khúc duy nhất còn giả.
    worker.handlers["ingest"] = StubIngest(repos, specs)
    app = main.build_app(repos, specs, worker, broker)

    with TestClient(app) as c:
        c.repos = repos
        c.worker = worker
        c.created = created
        c.mt_created = mt_created
        c.mt_engines = mt_engines
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

    # Task 12: cấu hình production nay là `auto_forward="1"` (đã có handler
    # `translate`), nên chính đường bóc băng THẬT SỰ đẻ ra job dịch — không còn
    # phải xếp tay một job để canh nhánh "không có handler".
    assert wired.repos.get_setting(AUTO_FORWARD_SETTING) == "1", (
        "production đặt auto_forward='1' kể từ khi có handler translate"
    )
    translate_jobs = [j for j in wired.get("/api/jobs").json() if j["type"] == "translate"]
    assert len(translate_jobs) == 1, (
        f"bóc băng xong phải tự đẻ ĐÚNG một job dịch: {translate_jobs}"
    )
    assert translate_jobs[0]["state"] == "done", translate_jobs[0]
    assert translate_jobs[0]["engine"] == MT_SPEC.id
    assert wired.governor.entered[-1] == js.phase_of("translate", MT_SPEC.id), (
        f"job dịch tự sinh phải mở giai đoạn dịch: {wired.governor.entered}"
    )
    translations = wired.get(f"/api/transcripts/{tid}").json()["translations"]
    assert len(translations) == 1, translations
    summary = translations[0]
    assert summary["engine"] == MT_SPEC.id
    # I-4: cùng builder với `/api/translations` ⇒ `transcript_version` + `status`
    # (trước bản vá chỗ này phát `translated_from_version` và thiếu `status`, nên
    # một bản dịch vừa xếp và một bản dịch đã xong trông y hệt nhau ở đây).
    assert summary["transcript_version"] == 1
    assert summary["status"] == "done", (
        "endpoint này phải phân biệt được `queued` với `done`: đây là thứ giao "
        "diện Workspace 2 dùng để biết bản dịch đã sẵn sàng chưa"
    )
    assert summary["stale"] is False, "vừa dịch xong từ version 1 thì không được coi là cũ"
    assert summary["prompt_version"] == PROMPT_VERSION[MT_SPEC.id], (
        "prompt_version là DỮ LIỆU của `adapters/mt/prompts.py` do `main.py` bơm "
        f"vào; nhận được {summary['prompt_version']!r}"
    )
    assert wired.repos.get_translation(summary["id"]).status == "done"
    assert wired.mt_engines[MT_SPEC.id].batches == [[0, 1, 2]], (
        "engine dịch của CHÍNH composition root phải là cái đã được gọi"
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
    # Đây là cấu hình PRODUCTION: `main.build_components()` đặt `auto_forward="1"`
    # kể từ Task 12 (đã có handler `translate` thật). Fixture tự ráp dây thì biến
    # đó vắng mặt và `TranscribeHandler` hiểu là BẬT — nay hai đường giống nhau.
    assert wired.repos.get_setting(AUTO_FORWARD_SETTING) == "1", (
        "fixture phải chạy đúng cấu hình production (auto_forward='1')"
    )
    assert wired.governor.entered == [
        "ingest:-", "asr:fw-large-v3-turbo", f"translate:{MT_SPEC.id}",
    ], f"truy vết giai đoạn sai: {wired.governor.entered}"
    # `phase_switches` KHÔNG phải một quan sát độc lập với `entered`: cả hai đều
    # được đặt trong `worker._enter_phase` (worker.py:117-120) với cùng một tham
    # số `phase`. Đây là MỘT đẳng thức, không phải hai nhân chứng.
    assert wired.worker.phase_switches == len(wired.governor.entered) == 3, (
        "auto_forward='1' vào ingest:- rồi asr:fw-large-v3-turbo rồi giai đoạn dịch, "
        f"thực tế {wired.worker.phase_switches} lần đổi giai đoạn: "
        f"{wired.governor.entered}"
    )
    # Rời giai đoạn ASR là model phải được ĐỔ, qua đúng vòng
    # `governor.register()` của `main.py`. `release()` của handler idempotent nên
    # gọi lặp không tính thêm lần nào.
    assert wired.created[0].release_count == 1, (
        "đổi giai đoạn mà không đổ model thì VRAM rò rỉ: "
        f"{wired.created[0].release_count} lần đổ"
    )
    # Và engine DỊCH cũng phải được đăng ký với governor: ba job dịch chạy trong
    # đúng một giai đoạn, nên `release()` của nó được gọi ở cả `before_phase` của
    # giai đoạn khác lẫn `after_phase` của chính nó.
    engine = wired.mt_engines[MT_SPEC.id]
    assert engine.release_count >= 1, (
        "engine dịch không được đăng ký releaser: model Ollama nằm mãi trong VRAM"
    )


def test_layer_boundary_still_holds_after_everything(wired):
    """Nhắc lại: nếu test này đỏ thì ai đó đã import hạ tầng vào domain."""
    from tests.test_layer_boundary import test_domain_has_no_forbidden_absolute_imports
    test_domain_has_no_forbidden_absolute_imports()
