from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.api.sse import JobEventBroker, stream_events
from app.domain import job_state as js
from app.registry import EngineSpec

_ASR_SPEC = EngineSpec(id="fw-large-v3-turbo", label="FW", kind="asr",
                       runtime="inprocess", model_ref="large-v3-turbo",
                       vram_mb=1600, langs=("zh", "en"), capabilities={}, opts={})


@pytest.fixture()
def env(tmp_path):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    broker = JobEventBroker()
    app = create_app(repos=repos, specs=[_ASR_SPEC], media_dir=tmp_path / "m",
                     out_dir=tmp_path / "o", broker=broker)
    with TestClient(app) as c:
        c.repos = repos
        c.broker = broker
        yield c


def test_create_job_validates_type(env):
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "khong-co", "engine": None})
    assert resp.status_code == 422
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                      "engine": "fw-large-v3-turbo",
                                      "payload": {"source_id": 1}})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["phase"] == "asr:fw-large-v3-turbo"
    assert body["state"] == js.QUEUED


def test_create_job_rejects_unknown_engine(env):
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                      "engine": "khong-co", "payload": {}})
    assert resp.status_code == 422


def test_list_and_get_job(env):
    env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                "engine": "fw-large-v3-turbo", "payload": {}})
    listed = env.get("/api/jobs").json()
    assert len(listed) == 1
    jid = listed[0]["id"]
    assert env.get(f"/api/jobs/{jid}").json()["id"] == jid
    assert env.get("/api/jobs/9999").status_code == 404


def test_cancel_sets_flag_not_kill(env):
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                       "engine": "fw-large-v3-turbo", "payload": {}})
    jid = resp.json()["id"]
    assert env.post(f"/api/jobs/{jid}/cancel").json()["cancel_requested"] is True
    assert env.repos.get_job(jid).state == js.CANCELLED, (
        "huỷ job đang queued là xong ngay (spec §5.4: 'job chưa chạy, huỷ là xong')"
    )


def test_retry_only_from_retryable_states(env):
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                       "engine": "fw-large-v3-turbo", "payload": {}})
    jid = resp.json()["id"]
    assert env.post(f"/api/jobs/{jid}/retry").status_code == 409
    env.repos.set_job_state(jid, js.RUNNING)
    env.repos.set_job_state(jid, js.FAILED, error="x")
    assert env.post(f"/api/jobs/{jid}/retry").status_code == 200
    assert env.repos.get_job(jid).state == js.QUEUED


def test_sse_stream_emits_published_events(env):
    """Kiểm generator TRỰC TIẾP — KHÔNG qua `TestClient.stream()`.

    `TestClient` chạy app trong một portal rồi CHỜ app kết thúc, nên một
    `StreamingResponse` bọc generator vô hạn (`while True` + heartbeat 15s) làm
    `with env.stream(...)` **không bao giờ trả về**: test TREO chứ không đỏ.
    Gọi thẳng generator vẫn kiểm đúng tính chất cần kiểm — sự kiện publish ra
    thì có mặt trên luồng, đúng định dạng SSE — mà không cần app kết thúc.
    """
    gen = stream_events(env.broker, heartbeat=0.05)
    try:
        assert next(gen) == ": connected\n\n"
        env.broker.publish({"id": 7, "state": "done", "progress": 1.0})
        line = next(gen)
        assert line.startswith("data: ")
        assert json.loads(line[len("data: "):])["id"] == 7
    finally:
        gen.close()
    assert any(getattr(r, "path", None) == "/api/jobs/stream" for r in env.app.routes), (
        "route SSE phải được đăng ký trên app"
    )


def test_broker_drops_oldest_when_subscriber_is_slow():
    """Một subscriber chậm không được làm phình bộ nhớ server."""
    broker = JobEventBroker(max_queue=3)
    q = broker.subscribe()
    for n in range(10):
        broker.publish({"id": n})
    assert q.qsize() == 3
    got = [q.get_nowait()["id"] for _ in range(3)]
    assert got == [7, 8, 9], "phải giữ sự kiện MỚI NHẤT, bỏ cái cũ"


# ---------------------------------------------------------------------------
# Đường THẬT từ worker tới luồng SSE.
#
# Khối test của brief khoá hình dạng broker + route, nhưng không có gì nối
# `PhaseQueueWorker` vào broker: thêm tham số `publish` mà quên gọi nó ở một
# nhánh `set_job_state` thì cả 7 test trên vẫn xanh trong khi giao diện đứng im
# ở trạng thái cũ. Hai test dưới đây khoá đúng đường đó.
# ---------------------------------------------------------------------------

from app.worker import PhaseQueueWorker  # noqa: E402
from tests.fakes import FakeGovernor, RecordingHandler, a_job  # noqa: E402


def _worker_publishing(repos, publish) -> PhaseQueueWorker:
    return PhaseQueueWorker(
        repos, FakeGovernor(), {"asr": RecordingHandler(job_type="asr")},
        publish=publish,
    )


def test_worker_publishes_every_state_it_writes(env):
    """Mỗi lần worker ghi trạng thái/tiến độ phải có ĐÚNG một sự kiện ra broker.

    Thiếu `_emit` sau một nhánh `set_job_state` là lỗi im lặng: job đã `failed`
    trong DB mà giao diện vẫn hiện `running` cho tới khi client tự tải lại.

    Bốn sự kiện, không phải ba: `RecordingHandler` gọi `report()` HAI lần, nên
    có hai lần ghi tiến độ (0.5 rồi 1.0) trước khi worker chốt `done`.
    """
    events: list[dict] = []
    worker = _worker_publishing(env.repos, events.append)
    jid = env.repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))

    while worker.tick():
        pass

    assert [(e["id"], e["state"]) for e in events] == [
        (jid, js.RUNNING), (jid, js.RUNNING), (jid, js.RUNNING), (jid, js.DONE),
    ], events
    assert [e["progress"] for e in events] == [0.0, 0.5, 1.0, 1.0], events
    assert events[-1]["phase"] == js.phase_of("asr", "fw-large-v3-turbo")
    assert events[-1]["error"] is None


def test_worker_publishes_the_failed_state_and_reason(env):
    """Nhánh `except` cũng phải publish — nếu không, job hỏng là job im lặng."""
    events: list[dict] = []
    worker = PhaseQueueWorker(
        env.repos, FakeGovernor(),
        {"asr": RecordingHandler(job_type="asr", fail_on={1})},
        publish=events.append,
    )
    jid = env.repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))
    while worker.tick():
        pass

    last = events[-1]
    assert last == {"id": jid, "state": js.FAILED, "progress": 0.5,
                    "phase": "asr:fw-large-v3-turbo",
                    "error": "RuntimeError: job 1 hỏng theo kịch bản test"}, last


def test_published_events_reach_the_sse_stream(env):
    """Worker publish -> broker -> generator SSE, không cần app kết thúc.

    Worker đẩy thẳng vào `env.broker` (đúng broker mà route đọc), nên đây là
    đường THẬT. Generator được mở TRƯỚC khi worker chạy, y như một client đang
    nghe; worker chạy xong thì sự kiện đã nằm sẵn trong hàng đợi nên mỗi
    `next(gen)` trả về ngay. Chạy xen kẽ từng nhịp thì heartbeat 0.05s có thể
    lọt vào giữa và test đỏ vì lý do không liên quan.
    """
    recorded: list[dict] = []
    worker = _worker_publishing(env.repos, _tee(recorded, env.broker.publish))
    jid = env.repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))

    gen = stream_events(env.broker, heartbeat=0.05)
    try:
        assert next(gen) == ": connected\n\n"
        while worker.tick():
            pass
        lines = [next(gen) for _ in recorded]
    finally:
        gen.close()

    bodies = [json.loads(line[len("data: "):]) for line in lines]
    assert len(recorded) == 4, recorded
    assert [b["id"] for b in bodies] == [jid] * len(recorded), lines
    assert [b["state"] for b in bodies] == [js.RUNNING, js.RUNNING, js.RUNNING, js.DONE]


def _tee(recorded: list[dict], sink):
    """Vừa ghi lại sự kiện, vừa đẩy tiếp vào `sink` (broker thật)."""
    def publish(event: dict) -> None:
        recorded.append(event)
        sink(event)
    return publish


def test_broker_forwards_a_dict_without_handing_out_live_objects(env):
    """Sự kiện qua stream phải là JSON thuần, không kèm đối tượng sống."""
    q = env.broker.subscribe()
    env.broker.publish({"id": 1, "state": "done"})
    assert q.get_nowait() == {"id": 1, "state": "done"}
