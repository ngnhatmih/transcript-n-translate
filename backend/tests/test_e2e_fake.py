"""Task 19: chạy CẢ đường ống với engine giả — không tốn một MB VRAM.

Đây là lợi ích cụ thể của việc phân tầng: `domain` thuần nên thay engine thật
bằng engine giả là chuyện bình thường, không phải hack. Không có test này thì
mỗi tầng đều xanh riêng lẻ mà không chỗ nào chứng minh chúng nối được với nhau:
upload -> ingest -> asr -> (auto_forward đẻ job dịch) -> export -> tải về.

## Vì sao `phase_switches == 3` (ledger R8)

Fixture TỰ dựng `PhaseQueueWorker` chứ KHÔNG gọi `build_components()`, nên không
ai đặt `auto_forward="0"` (R59: `main.py` đặt biến đó cho tiến trình thật).
`TranscribeHandler` coi `auto_forward` VẮNG MẶT là BẬT, nên mỗi job ASR đẻ thêm
một job `translate`. Truy vết quan sát được — khẳng định NGUYÊN VĂN ở
`test_fake_asr_model_loaded_exactly_once_for_the_phase`:

    ingest:-               x3  -> vào giai đoạn lần 1
    asr:fw-large-v3-turbo  x3  -> vào giai đoạn lần 2
    translate:-            x3  -> vào giai đoạn lần 3
                                  (không handler -> FAILED, nhưng ĐÃ vào giai
                                  đoạn nên VẪN tính là một lần switch)

Con số **3 gắn với CHÍNH fixture này**. Nếu ai đó "dọn dẹp" cho nó dùng
`build_components()` (auto_forward="0", không job dịch) thì đúng phải là **2** —
test sẽ đỏ vì một lý do KHÔNG phải lỗi của nó. Muốn đổi số thì ĐO LẠI bằng truy
vết, đừng sửa mù.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.governor.single_gpu import SingleGpuGovernor
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.domain.models import Job, Segment
from app.pipeline.export import ExportHandler
from app.pipeline.transcribe import TranscribeHandler
from app.registry import EngineSpec
from app.worker import PhaseQueueWorker


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
    `governor.before_phase(phase)` đúng MỘT lần cho mỗi giai đoạn, nên `entered`
    chính là truy vết mà `worker.phase_switches` chỉ đếm được con số tổng.
    """

    def __init__(self, repos) -> None:
        super().__init__(repos)
        self.entered: list[str] = []

    def before_phase(self, phase: str) -> None:
        self.entered.append(phase)
        super().before_phase(phase)


@pytest.fixture()
def wired(tmp_path):
    # Chỉ cần thư mục media: route upload đặt tên tệp theo NỘI DUNG
    # (`<sha256[:16]>.mp4`), còn `StubIngest` tự tạo tệp `.wav` mà nó trỏ tới.
    # Hai tệp giả `clip.mp4`/`clip.wav` của bản plan cũ không ai đọc.
    media = tmp_path / "media"
    media.mkdir()

    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()

    specs = [
        EngineSpec(id="fw-large-v3-turbo", label="FW", kind="asr", runtime="inprocess",
                   model_ref="large-v3-turbo", vram_mb=1600, langs=("zh", "en"),
                   capabilities={}, opts={}),
    ]
    governor = TracingGovernor(repos)

    created: list[FakeASREngine] = []

    def factory(spec):
        engine = FakeASREngine(spec)
        created.append(engine)
        return engine

    handlers = {
        "asr": TranscribeHandler(repos, specs, factory, workdir=media),
        "export": ExportHandler(repos, out_dir=tmp_path / "out"),
    }
    # Gương của `main.py:61-65`: KHÔNG đăng ký releaser thì `before_phase`/
    # `after_phase` là hàm rỗng và model ASR nằm mãi trong VRAM (R39/R42). Không
    # có vòng lặp này thì `FakeASREngine.release_count` không bao giờ tăng và
    # khẳng định "đổ model khi đổi giai đoạn" ở dưới là vô nghĩa.
    governor.register(specs[0].phase_key, handlers["asr"].release)

    # ingest thật cần ffmpeg; ở test này ta đã có wav nên dùng handler giả tối thiểu
    class StubIngest:
        def handles(self) -> str:
            return "ingest"

        def run(self, job, report) -> None:
            sid = job.payload["source_id"]
            source = repos.get_source(sid)
            # R37: tệp wav phải TỒN TẠI. Bản trước suy tên qua `.replace(".mp4", ".wav")`
            # nhưng KHÔNG ai tạo tệp đó, nên `TranscribeHandler` ném FileNotFoundError
            # và job ASR thành FAILED. Dùng `open` (builtin) để khỏi thêm import.
            audio = source.media_path.replace(".mp4", ".wav")
            with open(audio, "wb") as fh:
                fh.write(b"stub-wav")
            repos.set_source_audio(sid, audio, 8.0)
            # R7: và phải TẠO JOB ASR — không có nó thì không có gì chạy bóc băng.
            repos.add_job(Job(id=None, workspace=1, type="asr",
                              engine="fw-large-v3-turbo",
                              phase="asr:fw-large-v3-turbo",
                              payload={"source_id": sid}))
            report(1.0, "ingest giả")

    handlers["ingest"] = StubIngest()

    worker = PhaseQueueWorker(repos, governor, handlers)
    app = create_app(repos=repos, specs=specs, media_dir=media,
                     out_dir=tmp_path / "out", worker=worker)
    with TestClient(app) as c:
        c.repos = repos
        c.worker = worker
        c.created = created
        c.governor = governor
        c.tmp = tmp_path
        yield c


def test_full_pipeline_from_upload_to_srt(wired):
    """upload -> ingest -> asr -> (auto_forward tạo job dịch) -> export -> tải về."""
    resp = wired.post("/api/sources/upload",
                      files={"file": ("clip.mp4", b"x" * 64, "video/mp4")},
                      data={"lang": "zh"})
    assert resp.status_code == 201

    wired.worker.recover()
    while wired.worker.tick():
        pass

    transcripts = wired.get("/api/transcripts").json()
    assert len(transcripts) == 1
    tid = transcripts[0]["id"]

    detail = wired.get(f"/api/transcripts/{tid}").json()
    assert detail["version"] == 1
    assert [s["text"] for s in detail["segments"]][0] == "大家好"
    assert detail["segments"][2]["suspect"] is True

    running = wired.get("/api/status").json()
    assert running["queue_depth"] == 0, "hàng đợi phải cạn; job dịch không có handler nên sẽ failed"

    # GĐ1a chưa có handler dịch: job phải FAILED RÕ RÀNG chứ không treo ở `queued`.
    # Không thêm handler giả cho `translate` — làm vậy là che mất đúng cái lỗ hổng
    # mà khẳng định này canh.
    jobs = wired.get("/api/jobs").json()
    translate_jobs = [j for j in jobs if j["type"] == "translate"]
    assert len(translate_jobs) == 1
    assert translate_jobs[0]["state"] == "failed", (
        "GĐ1a chưa có handler dịch; job phải failed rõ ràng chứ không treo"
    )
    assert "không có handler" in (translate_jobs[0]["error"] or "")

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
    # Truy vết THẬT của nhịp chạy này (xem docstring đầu tệp): giai đoạn thứ ba
    # `translate:-` có vào, dù mọi job của nó FAILED vì chưa có handler.
    assert wired.governor.entered == ["ingest:-", "asr:fw-large-v3-turbo", "translate:-"], (
        f"truy vết giai đoạn sai: {wired.governor.entered}"
    )
    assert wired.worker.phase_switches == 3, (
        "ingest:- -> asr:fw-large-v3-turbo -> translate:- (auto_forward đẻ job dịch; "
        f"thực tế {wired.worker.phase_switches})"
    )
    # Rời giai đoạn ASR là model phải được ĐỔ, qua đúng `governor.after_phase` mà
    # `main.py` nối dây. `release()` của handler idempotent nên gọi lặp (lúc vào
    # `translate:-`) không tính thêm lần nào.
    assert wired.created[0].release_count == 1, (
        "đổi giai đoạn mà không đổ model thì VRAM rò rỉ: "
        f"{wired.created[0].release_count} lần đổ"
    )


def test_layer_boundary_still_holds_after_everything(wired):
    """Nhắc lại: nếu test này đỏ thì ai đó đã import hạ tầng vào domain."""
    from tests.test_layer_boundary import test_domain_has_no_forbidden_absolute_imports
    test_domain_has_no_forbidden_absolute_imports()
