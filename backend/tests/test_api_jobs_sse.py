from __future__ import annotations

import asyncio
import contextlib
import json
import time

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
from starlette.requests import Request
from starlette.routing import Match

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


def test_cancel_a_missing_job_is_404_like_its_siblings(env):
    """Job không tồn tại là lỗi CLIENT (404), không phải 500.

    `request_cancel` là một UPDATE mù: 0 hàng, không ném. Nên nếu lần đọc lại
    `get_job` nằm NGOÀI khối `try`, `NotFound` nổi lên thành 500 — trong khi
    `GET /{job_id}` và `POST /{job_id}/retry` trả 404 cho đúng tình huống đó.
    """
    assert env.get("/api/jobs/9999").status_code == 404
    assert env.post("/api/jobs/9999/retry").status_code == 404
    assert env.post("/api/jobs/9999/cancel").status_code == 404


def test_sse_stream_emits_published_events(env):
    """Kiểm generator TRỰC TIẾP — KHÔNG qua `TestClient.stream()`.

    `TestClient` chạy app trong một portal rồi CHỜ app kết thúc, nên một
    `StreamingResponse` bọc generator vô hạn (`while True` + heartbeat 15s) làm
    `with env.stream(...)` **không bao giờ trả về**: test TREO chứ không đỏ.
    Gọi thẳng generator vẫn kiểm đúng tính chất cần kiểm — sự kiện publish ra
    thì có mặt trên luồng, đúng định dạng SSE — mà không cần app kết thúc.
    """
    async def drive():
        gen = stream_events(env.broker, heartbeat=0.05)
        try:
            assert await anext(gen) == ": connected\n\n"
            env.broker.publish({"id": 7, "state": "done", "progress": 1.0})
            return await asyncio.wait_for(anext(gen), 5)
        finally:
            await gen.aclose()

    line = asyncio.run(drive())
    assert line.startswith("data: ")
    assert json.loads(line[len("data: "):])["id"] == 7
    assert any(getattr(r, "path", None) == "/api/jobs/stream" for r in env.app.routes), (
        "route SSE phải được đăng ký trên app"
    )


def test_a_transition_during_the_snapshot_is_delivered_not_lost():
    """Cửa sổ giữa "chụp ảnh" và "nghe" không được nuốt mất một chuyển trạng thái.

    Đây là probe G của review: client chụp `GET /api/jobs` (thấy `running`) rồi
    mới mở stream; `done` rơi vào giữa hai bước thì client đứng ở `running` mãi,
    vì không có sự kiện nào tới và cũng không có gì chụp lại. Cách sửa là NGHE
    TRƯỚC rồi mới chụp, và chính stream gửi ảnh chụp đó. Ở đây ảnh chụp cố tình
    publish một sự kiện ngay trong lúc chụp — đúng cái cửa sổ đó.
    """
    broker = JobEventBroker()

    def snapshot():
        broker.publish({"id": 1, "state": js.DONE, "progress": 1.0, "phase": None,
                        "error": None, "log_tail": "xong"})
        return [{"id": 1, "state": js.RUNNING, "progress": 0.5, "phase": None,
                 "error": None, "log_tail": ""}]

    gen = stream_events(broker, heartbeat=0.05, snapshot=snapshot)
    async def drive():
        try:
            assert await anext(gen) == ": connected\n\n"
            return [await asyncio.wait_for(anext(gen), 5) for _ in range(2)]
        finally:
            await gen.aclose()

    lines = asyncio.run(drive())
    bodies = [json.loads(line[len("data: "):]) for line in lines
              if line.startswith("data: ")]
    assert [b["state"] for b in bodies] == [js.RUNNING, js.DONE], lines


def test_a_transition_is_not_both_snapshotted_and_resent():
    """Khử trùng: chuyển trạng thái đã nằm trong ảnh chụp không được gửi lại.

    Sự kiện publish SAU khi subscribe nhưng TRƯỚC khi ảnh chụp đọc xong sẽ vừa
    nằm trong ảnh chụp vừa nằm trong hàng đợi. Gửi cả hai là gửi trùng một
    chuyển; bỏ cả hai là mất một chuyển.
    """
    broker = JobEventBroker()
    running = {"id": 1, "state": js.RUNNING, "progress": 0.5, "phase": None,
               "error": None, "log_tail": ""}

    def snapshot():
        broker.publish(dict(running))
        broker.publish({"id": 2, "state": js.DONE, "progress": 1.0, "phase": None,
                        "error": None, "log_tail": ""})
        return [dict(running)]

    gen = stream_events(broker, heartbeat=0.05, snapshot=snapshot)

    async def drive():
        try:
            assert await anext(gen) == ": connected\n\n"
            return [await asyncio.wait_for(anext(gen), 5) for _ in range(2)]
        finally:
            await gen.aclose()

    lines = asyncio.run(drive())
    bodies = [json.loads(line[len("data: "):]) for line in lines
              if line.startswith("data: ")]
    assert [(b["id"], b["state"]) for b in bodies] == [(1, js.RUNNING), (2, js.DONE)], lines


class _EventJob:
    """Job giả cho ảnh chụp: chỉ cần `to_event()` trả về sự kiện đã định."""

    def __init__(self, event: dict):
        self._event = event

    def to_event(self) -> dict:
        return dict(self._event)


def test_two_events_for_one_job_in_the_snapshot_window_never_strand_the_client(env):
    """R1 của review: hàng đợi phải thu về sự kiện MỚI NHẤT mỗi job, không phát lại cái cũ.

    Cửa sổ "subscribe -> chụp ảnh" có thể chứa HAI chuyển trạng thái của cùng
    một job: `running` rồi `done`. Ảnh chụp đọc sau nên thấy `done`; hàng đợi
    giữ `[running, done]`. Khử trùng theo nội dung một-một sẽ bỏ `done` (trùng
    ảnh chụp) rồi gửi `running` NGAY SAU ảnh chụp — client đứng ở `running` mãi
    dù sự thật là `done`, và không còn sự kiện nào sửa lại.

    Đường THẬT: broker + repos của app đã lắp, và đúng biểu thức ảnh chụp của
    route (`[j.to_event() for j in repos.list_jobs()]`) — chỉ `heartbeat` ngắn
    hơn để biết lúc hàng đợi đã cạn. Ảnh chụp chạy trong executor nên callback
    của `publish` chỉ chạy sau đó, đúng thứ tự trên một event loop thật.
    """
    jid = env.repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))
    env.repos.set_job_state(jid, js.RUNNING)
    env.repos.set_job_state(jid, js.DONE)

    older = {"id": jid, "state": js.RUNNING, "progress": 0.5, "phase": None,
             "error": None, "log_tail": ""}
    real_list_jobs = env.repos.list_jobs
    started: list[int] = []

    class SnapshotInTheWindow:
        """`repos` như route thấy, nhưng ảnh chụp rơi đúng vào cửa sổ.

        Ảnh chụp chạy trong executor nên `asyncio.get_running_loop()` không có ở
        đây: publish qua loop bắt từ trước, đúng đường `call_soon_threadsafe` mà
        `JobEventBroker` dùng cho luồng worker. `list_jobs()` thật vẫn là nguồn
        của ảnh chụp; chỉ `to_event()` của job được thay để ảnh chụp mang đúng
        trạng thái mới nhất khi hàng đợi còn giữ bản cũ.
        """

        def __init__(self, repos, loop):
            self._repos = repos
            self._loop = loop

        def __getattr__(self, name):
            return getattr(self._repos, name)

        def list_jobs(self, **kwargs):
            started.append(1)
            self._loop.call_soon_threadsafe(env.broker.publish, dict(older))
            rows = real_list_jobs(**kwargs)
            newest = rows[0].to_event()
            assert newest["id"] == jid and newest["state"] == js.DONE, newest
            self._loop.call_soon_threadsafe(env.broker.publish, dict(newest))
            return [_EventJob(newest)]

    async def drive():
        loop = asyncio.get_running_loop()

        env.app.state.repos = SnapshotInTheWindow(env.repos, loop)
        try:
            response = _stream_response(env.app, heartbeat=0.05)
        finally:
            env.app.state.repos = env.repos

        it = response.body_iterator
        seen: list[str] = []
        try:
            assert await asyncio.wait_for(anext(it), 5) == ": connected\n\n"
            for _ in range(8):
                chunk = await asyncio.wait_for(anext(it), 5)
                if chunk.startswith(":"):
                    break                                     # nhịp tim: hết sự kiện
                body = json.loads(chunk[len("data: "):])
                if body["id"] == jid:
                    seen.append(body["state"])
        finally:
            await it.aclose()
        return seen

    seen = asyncio.run(drive())
    assert started == [1], "ảnh chụp của route phải chạy đúng một lần trong cửa sổ"
    assert js.DONE in seen, f"ảnh chụp mang trạng thái thật phải tới client: {seen}"
    assert seen[-1] == js.DONE, (
        f"trạng thái cuối client thấy phải là sự thật ({js.DONE}), không phải bản cũ: {seen}"
    )


def test_broker_drops_oldest_when_subscriber_is_slow():
    """Một subscriber chậm không được làm phình bộ nhớ server."""
    async def drive():
        broker = JobEventBroker(max_queue=3)
        sub = broker.subscribe()
        for n in range(10):
            broker.publish({"id": n})
        await asyncio.sleep(0.01)            # cho các callback trên loop chạy
        assert sub.queue.qsize() == 3
        return [sub.queue.get_nowait()["id"] for _ in range(3)]

    assert asyncio.run(drive()) == [7, 8, 9], "phải giữ sự kiện MỚI NHẤT, bỏ cái cũ"


def test_stream_removes_its_subscriber_when_the_client_disconnects():
    """I3 của review: ngắt kết nối phải rút hàng đợi khỏi broker.

    Bỏ sót thì hàng đợi rò rỉ, và tệ hơn: mỗi lần publish sau đó lại serialize
    rồi nhét vào một subscriber không còn ai đọc — mãi mãi.
    """
    async def drive():
        broker = JobEventBroker()
        gen = stream_events(broker, heartbeat=0.05)
        try:
            assert await anext(gen) == ": connected\n\n"
            during = len(broker._subscribers)
        finally:
            await gen.aclose()
        return during, list(broker._subscribers)

    during, after = asyncio.run(drive())
    assert during == 1, "stream phải đăng ký đúng một subscriber"
    assert after == [], "ngắt kết nối phải rút hàng đợi khỏi broker"


def test_the_stream_route_is_declared_before_the_job_id_route(env):
    """I4 của review: `/api/jobs/stream` phải đứng TRƯỚC `/api/jobs/{job_id}`.

    Không phải chuyện thẩm mỹ: FastAPI khớp theo thứ tự khai báo, nên đảo lại
    thì "stream" khớp vào `{job_id}` và bị parse thành int -> 422 (đúng lỗi mà
    brief:370 cảnh báo). Test cũ chỉ khẳng định route TỒN TẠI nên không thấy
    được thứ tự; ở đây kiểm cả thứ tự LẪN route nào thực sự khớp được đường dẫn.
    """
    paths = [r.path for r in env.app.routes]
    assert paths.index("/api/jobs/stream") < paths.index("/api/jobs/{job_id}")

    scope = {"type": "http", "method": "GET", "path": "/api/jobs/stream", "headers": []}
    handler = next(r.endpoint for r in env.app.routes
                   if getattr(r, "matches", None) and r.matches(scope)[0] is Match.FULL)
    assert handler.__name__ == "stream", f"route khớp /api/jobs/stream là {handler.__name__}"


def _stream_response(app, **kwargs):
    """`StreamingResponse` y như route `/api/jobs/stream` dựng, nhưng chỉnh được `heartbeat`.

    Không dùng `TestClient.stream()`: nó chờ app kết thúc, mà generator SSE thì
    không bao giờ kết thúc -> test TREO. Ở đây vẫn là route THẬT (`request.app`
    -> broker + repos của app, `repos.list_jobs()` làm ảnh chụp), chỉ khác đối
    số `stream_events` mà route không thể nhận qua `Request`.
    """
    request = Request({"type": "http", "app": app, "method": "GET",
                       "path": "/api/jobs/stream", "headers": []})
    broker = request.app.state.broker
    repos = request.app.state.repos
    options = {"heartbeat": 15.0, **kwargs}
    return StreamingResponse(
        stream_events(broker, snapshot=lambda: [j.to_event() for j in repos.list_jobs()],
                      **options),
        media_type="text/event-stream",
    )


def test_the_stream_route_reads_the_broker_injected_into_the_app(env):
    """I5 của review: route phải đọc broker CỦA APP, không dựng broker mới.

    Hai test cũ gọi thẳng `stream_events(env.broker, ...)` nên không chạm vào
    dây route↔broker — đúng chỗ hổng đã để C1 lọt qua. Ở đây sự kiện publish
    trên `env.broker` phải đi ra tới body của response thật.
    """
    assert env.app.state.broker is env.broker, (
        "create_app() phải dùng broker được truyền vào, không dựng cái mới"
    )
    response = _stream_response(env.app)
    published = {"id": 42, "state": js.DONE, "progress": 1.0, "phase": None,
                 "error": None, "log_tail": ""}

    async def drive():
        it = response.body_iterator
        try:
            assert await asyncio.wait_for(anext(it), 5) == ": connected\n\n"
            env.broker.publish(published)
            return await asyncio.wait_for(anext(it), 5)
        finally:
            await it.aclose()

    line = asyncio.run(drive())
    assert json.loads(line[len("data: "):]) == published


def test_an_idle_stream_does_not_hold_a_threadpool_token(env):
    """I7 của review: stream đang CHỜ sự kiện không được giữ token threadpool.

    Generator đồng bộ bị Starlette bọc trong `iterate_in_threadpool`, nên mỗi
    `next()` đang chờ sự kiện chiếm một trong 40 token mặc định của anyio; với
    heartbeat 15s thì token bị giữ gần như suốt vòng đời kết nối. Review đo
    được 0.41s xếp hàng khi 40 stream mở. Ở đây hạ limiter xuống ĐÚNG một token
    rồi bắt một route sync phải chạy được ngay trong lúc stream đang chờ.
    """
    async def drive():
        limiter = anyio.to_thread.current_default_thread_limiter()
        previous = limiter.total_tokens
        limiter.total_tokens = 1
        it = _stream_response(env.app).body_iterator
        parked = None
        try:
            assert await asyncio.wait_for(anext(it), 5) == ": connected\n\n"
            parked = asyncio.ensure_future(anext(it))        # stream chờ sự kiện
            await asyncio.sleep(0.05)                         # để nó kịp park
            borrowed = limiter.borrowed_tokens
            transport = httpx.ASGITransport(app=env.app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://test") as client:
                started = time.monotonic()
                try:
                    resp = await asyncio.wait_for(client.get("/api/jobs"), timeout=5)
                except asyncio.TimeoutError:
                    raise AssertionError(
                        "route sync bị chặn quá 5s sau khi một stream im lặng đang chờ: "
                        "stream đang giữ token threadpool"
                    ) from None
                elapsed = time.monotonic() - started
            return borrowed, elapsed, resp.status_code
        finally:
            if parked is not None:
                parked.cancel()
                with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                    await parked
            await it.aclose()
            limiter.total_tokens = previous

    borrowed, elapsed, status = asyncio.run(drive())
    assert status == 200
    assert borrowed == 0, "stream đang giữ token threadpool khi chỉ ngồi chờ"
    assert elapsed < 1.0, (
        f"route sync phải chờ {elapsed:.3f}s sau một stream im lặng: "
        "stream đang giữ token threadpool"
    )


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
    """Nhánh `except` cũng phải publish — nếu không, job hỏng là job im lặng.

    Hình dạng sự kiện được khoá ĐÚNG khoá ở đây, kể cả `log_tail`: design §9.2
    yêu cầu log đi kèm stream, và một client chỉ nghe SSE phải đọc được dòng
    log cuối cùng mà không cần gọi thêm `GET /api/jobs/{id}`.
    """
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
                    "error": "RuntimeError: job 1 hỏng theo kịch bản test",
                    # ĐÚNG chuỗi trong `jobs.log_tail`: `append_job_log` nối
                    # bằng "\n" vào log_tail rỗng nên dòng đầu có tiền tố xuống
                    # dòng, còn `str(exc)` không kèm tên lớp (tên lớp chỉ nằm
                    # trong `error`).
                    "log_tail": "\nchạy job 1\n"
                                "LỖI: job 1 hỏng theo kịch bản test"}, last


def test_worker_events_carry_the_log_text(env):
    """I6 của review — design §9.2 "log streaming via SSE" phải được giao.

    Sự kiện mang theo `log_tail` đã bị chặn ở `LOG_TAIL_LINES`, nên client đang
    xem tiến độ đọc được dòng log vừa sinh ngay trên stream, không phải gọi
    thêm `GET /api/jobs/{id}` sau mỗi sự kiện.
    """
    events: list[dict] = []
    worker = _worker_publishing(env.repos, events.append)
    env.repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))
    while worker.tick():
        pass

    assert set(events[-1]) == {"id", "state", "progress", "phase", "error",
                              "log_tail"}, events[-1]
    assert [e["log_tail"].splitlines()[-1] if e["log_tail"] else "" for e in events] == [
        "", "chạy job 1", "xong", "xong",
    ], events


def test_published_events_reach_the_sse_stream(env):
    """Worker publish -> broker -> generator SSE, không cần app kết thúc.

    Worker đẩy thẳng vào `env.broker` (đúng broker mà route đọc), nên đây là
    đường THẬT. Generator được mở TRƯỚC khi worker chạy, y như một client đang
    nghe; worker chạy xong thì sự kiện đã nằm sẵn trong hàng đợi nên mỗi
    `anext(gen)` trả về ngay. Chạy xen kẽ từng nhịp thì heartbeat có thể lọt vào
    giữa và test đỏ vì lý do không liên quan.
    """
    recorded: list[dict] = []
    worker = _worker_publishing(env.repos, _tee(recorded, env.broker.publish))
    jid = env.repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))

    async def drive():
        gen = stream_events(env.broker, heartbeat=5.0)
        try:
            assert await anext(gen) == ": connected\n\n"
            while worker.tick():
                pass
            return [await asyncio.wait_for(anext(gen), 5) for _ in recorded]
        finally:
            await gen.aclose()

    lines = asyncio.run(drive())
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
    async def drive():
        sub = env.broker.subscribe()
        env.broker.publish({"id": 1, "state": "done"})
        try:
            return await asyncio.wait_for(sub.wait(5), 5)
        finally:
            env.broker.unsubscribe(sub)

    assert asyncio.run(drive()) == {"id": 1, "state": "done"}
