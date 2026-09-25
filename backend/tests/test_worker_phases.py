"""Test hàng đợi gom lô theo GIAI ĐOẠN = (loại job, engine)."""
from __future__ import annotations

import datetime as _dt

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.governor.single_gpu import SingleGpuGovernor
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.adapters.registry_file import load_registry
from app.domain import job_state as js
from app.domain.models import Job
from app.worker import PhaseQueueWorker
from tests.fakes import FakeClock, FakeGovernor, RecordingHandler, a_job


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def _worker(repos, governor, *handlers):
    return PhaseQueueWorker(repos, governor, {h.handles(): h for h in handlers})


def test_two_files_two_engines_cause_exactly_two_phase_switches(repos):
    """Đây là toàn bộ lý do tồn tại của hàng đợi theo giai đoạn.

    Thứ tự thêm: asr:fw ... , asr:fw ... , asr:sv ... , asr:sv ...
    Nếu chạy FIFO thuần thì mỗi job là một lần nạp/đổ model (4 lần).
    Gom theo giai đoạn thì chỉ 2 lần.
    """
    gov = FakeGovernor()
    fw = RecordingHandler(job_type="asr")
    worker = _worker(repos, gov, fw)

    for engine in ("fw-large-v3-turbo", "fw-large-v3-turbo",
                   "sensevoice-small", "sensevoice-small"):
        repos.add_job(a_job(None, job_type="asr", engine=engine))

    while worker.tick():
        pass

    assert len(fw.ran) == 4
    assert worker.phase_switches == 2, (
        f"phải là 2 lần đổi giai đoạn, thực tế {worker.phase_switches}"
    )
    assert gov.before == ["asr:fw-large-v3-turbo", "asr:sensevoice-small"]
    assert gov.after == ["asr:fw-large-v3-turbo", "asr:sensevoice-small"]


def test_interleaved_engines_still_group(repos):
    """Job xen kẽ engine vẫn gom lô: 2 lần đổi giai đoạn, thứ tự chạy [1, 3, 2].

    Job 1 (fw) mở giai đoạn `asr:fw-large-v3-turbo`; job 3 thêm sau nhưng CÙNG
    giai đoạn đang nạp nên được bốc ngay; job 2 (sensevoice) chỉ chạy khi giai
    đoạn fw cạn và worker buộc phải đổi giai đoạn. Tổng cộng đúng 2 lần đổi, và
    thứ tự chạy KHÔNG phải thứ tự id — đó chính là hành vi gom lô.
    """
    gov = FakeGovernor()
    fw = RecordingHandler(job_type="asr")
    worker = _worker(repos, gov, fw)
    for engine in ("fw-large-v3-turbo", "sensevoice-small", "fw-large-v3-turbo"):
        repos.add_job(a_job(None, job_type="asr", engine=engine))

    while worker.tick():
        pass

    assert worker.phase_switches == 2
    assert fw.ran == [1, 3, 2]
    assert gov.before == ["asr:fw-large-v3-turbo", "asr:sensevoice-small"]
    assert gov.after == ["asr:fw-large-v3-turbo", "asr:sensevoice-small"]


def test_current_phase_is_none_when_queue_drains(repos):
    gov = FakeGovernor()
    worker = _worker(repos, gov, RecordingHandler(job_type="asr"))
    repos.add_job(a_job(None, job_type="asr", engine="e"))
    assert worker.tick() is True
    assert worker.current_phase == "asr:e"
    assert worker.tick() is False
    assert worker.current_phase is None, "hết việc thì phải nhả giai đoạn để lần sau chọn lại"


class _RaisingAfterPhaseGovernor(FakeGovernor):
    """Governor đối kháng: `after_phase` ghi lại rồi NÉM RA (kịch bản R56)."""

    def after_phase(self, phase: str) -> None:
        super().after_phase(phase)      # ghi vào `self.after` trước khi nổ
        raise RuntimeError("after_phase hỏng theo kịch bản test")


def test_leave_phase_clears_state_before_notifying_a_raising_governor(repos):
    """R56: `after_phase` ném ra thì `current_phase` VẪN phải đã được xoá.

    Bản cũ gọi governor TRƯỚC rồi mới gán `None`, nên khi governor nổ thì
    `current_phase` còn nguyên. Nhịp sau thấy phase còn, `next_queued_for_phase`
    trả None, rồi rời giai đoạn lần nữa -> `after_phase` bắn lại ở MỌI nhịp,
    vô hạn. Vì vậy bài này đếm số lần gọi chứ không chỉ khẳng định "có ném".
    """
    gov = _RaisingAfterPhaseGovernor()
    worker = _worker(repos, gov, RecordingHandler(job_type="asr"))
    repos.add_job(a_job(None, job_type="asr", engine="e"))

    assert worker.tick() is True                 # chạy hết job -> giai đoạn cạn việc
    assert worker.current_phase == "asr:e"

    with pytest.raises(RuntimeError, match="after_phase hỏng"):
        worker.tick()                            # rời giai đoạn -> governor nổ

    assert worker.current_phase is None, (
        "phải xoá current_phase TRƯỚC khi báo governor, nếu không lỗi lặp vô hạn"
    )
    assert gov.after == ["asr:e"], "after_phase phải được gọi đúng MỘT lần"

    # Hàng đợi đã rỗng: hai nhịp nữa không được rời lại giai đoạn cũ.
    assert worker.tick() is False
    assert worker.tick() is False
    assert gov.after == ["asr:e"], (
        f"after_phase chỉ được gọi một lần, thực tế {len(gov.after)} lần "
        "— bản cũ bắn lại mỗi nhịp vì current_phase không bao giờ được xoá"
    )


def test_failing_job_does_not_stop_the_queue(repos):
    gov = FakeGovernor()
    handler = RecordingHandler(job_type="asr", fail_on={2})
    worker = _worker(repos, gov, handler)
    for _ in range(3):
        repos.add_job(a_job(None, job_type="asr", engine="e"))

    while worker.tick():
        pass

    assert handler.ran == [1, 2, 3]
    assert repos.get_job(2).state == js.FAILED
    assert "hỏng theo kịch bản test" in (repos.get_job(2).error or "")
    assert repos.get_job(1).state == js.DONE
    assert repos.get_job(3).state == js.DONE


def test_job_of_another_type_is_deferred_not_starved(repos):
    """Job loại khác phải được chạy sau khi giai đoạn hiện tại hết việc,
    không được bỏ quên.

    Đây là test khoá RULING R2: nếu `tick()` trả False ngay khi giai đoạn hiện
    tại cạn việc thì vòng `while worker.tick()` dừng sớm và job 2 không bao giờ
    chạy — test này đỏ ở `asr.ran == [2]`.
    """
    gov = FakeGovernor()
    asr = RecordingHandler(job_type="asr")
    mt = RecordingHandler(job_type="translate")
    worker = _worker(repos, gov, asr, mt)
    repos.add_job(a_job(None, job_type="translate", engine="qwen2.5-7b", workspace=2))
    repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))

    while worker.tick():
        pass

    assert mt.ran == [1]
    assert asr.ran == [2]


def test_worker_drains_every_phase_in_one_call_loop(repos):
    """RULING R2: `tick()` chỉ được trả False khi KHÔNG còn job chờ nào.

    Bốn giai đoạn khác nhau, mỗi giai đoạn một job. Nếu `tick()` trả False lúc
    giai đoạn đầu cạn việc thì chỉ 1 job chạy; đúng ra phải là 4 và mỗi lần
    `tick()` đều trả True cho tới khi hàng đợi thật sự rỗng.
    """
    gov = FakeGovernor()
    handlers = [RecordingHandler(job_type=t) for t in ("asr", "translate")]
    worker = _worker(repos, gov, *handlers)
    repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))
    repos.add_job(a_job(None, job_type="translate", engine="qwen2.5-7b", workspace=2))
    repos.add_job(a_job(None, job_type="asr", engine="sensevoice-small"))
    repos.add_job(a_job(None, job_type="translate", engine="qwen2.5-3b", workspace=2))

    ticks = 0
    while worker.tick():
        ticks += 1

    assert ticks == 4, "mỗi nhịp chạy đúng một job, và không nhịp nào được dừng sớm"
    assert sum(len(h.ran) for h in handlers) == 4
    assert worker.phase_switches == 4
    assert worker.current_phase is None


def test_progress_and_log_are_written(repos):
    gov = FakeGovernor()
    worker = _worker(repos, gov, RecordingHandler(job_type="asr"))
    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    worker.tick()
    job = repos.get_job(jid)
    assert job.progress == 1.0
    assert "chạy job" in job.log_tail and "xong" in job.log_tail


def test_unknown_job_type_does_not_crash_the_worker(repos):
    gov = FakeGovernor()
    worker = _worker(repos, gov, RecordingHandler(job_type="asr"))
    jid = repos.add_job(a_job(None, job_type="export", engine=None))
    while worker.tick():
        pass
    job = repos.get_job(jid)
    assert job.state == js.FAILED
    assert "không có handler" in (job.error or "")


def test_single_gpu_governor_never_allows_parallel_in_phase_1a(tmp_path):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    gov = SingleGpuGovernor(repos)
    assert gov.can_run_parallel(1600, 5200) is False
    assert gov.can_run_parallel(100, 100) is False


def test_single_gpu_governor_releases_registered_phase(tmp_path):
    """`after_phase` gọi releaser của giai đoạn đã đăng ký, và KHÔNG rút đăng ký.

    Gọi hai lần thì releaser được gọi hai lần; an toàn vì releaser BẮT BUỘC
    idempotent (`release()` là no-op khi không có model nào đang nạp) — chính
    tính idempotent đó là thứ khiến gọi lặp không thể double-free. Vì vậy ĐỪNG
    khôi phục kiểu "pop sau lần gọi đầu": worker gọi `after_phase` ở MỖI lần
    cạn giai đoạn, pop đi thì từ lần thoát thứ hai model không bao giờ được đổ
    nữa và VRAM rò rỉ (xem test hai lô liên tiếp bên dưới).
    """
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    gov = SingleGpuGovernor(repos)
    released: list[str] = []
    gov.register("asr:fw-large-v3-turbo", lambda: released.append("fw"))
    gov.after_phase("asr:fw-large-v3-turbo")
    gov.after_phase("asr:fw-large-v3-turbo")
    assert released == ["fw", "fw"], (
        "releaser phải được gọi ở MỖI lần after_phase; an toàn nhờ idempotent"
    )


def test_single_gpu_governor_releases_other_phases_before_entering(tmp_path):
    """Vào giai đoạn mới phải đổ model của giai đoạn KHÁC, giữ model trùng khoá.

    Registry là VĨNH VIỄN (không pop), nên lần vào thứ hai vẫn gọi releaser của
    giai đoạn khác. An toàn vì releaser bắt buộc idempotent — xem test trên;
    đừng khôi phục consume-once.
    """
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    gov = SingleGpuGovernor(repos)
    released: list[str] = []
    gov.register("asr:fw-large-v3-turbo", lambda: released.append("fw"))
    gov.register("translate:qwen2.5-7b", lambda: released.append("qwen"))
    gov.before_phase("translate:qwen2.5-7b")
    assert released == ["fw"], "chỉ model của giai đoạn khác bị đổ"
    gov.before_phase("translate:qwen2.5-7b")
    assert released == ["fw", "fw"], (
        "registry vĩnh viễn: mỗi lần vào giai đoạn đều đổ lại model giai đoạn khác"
    )


class _ModelHandler:
    """Handler ASR giả có 'model' đúng nghĩa đang nạp hay không.

    `release()` idempotent y như hợp đồng của releaser thật: gọi khi không có gì
    nạp là no-op, nên `releases` đếm đúng số lần model THẬT SỰ bị đổ.
    """

    def __init__(self) -> None:
        self.loaded = False
        self.releases = 0

    def handles(self) -> str:
        return "asr"

    def run(self, job, report) -> None:
        self.loaded = True          # chạy job = model được nạp

    def release(self) -> None:
        if not self.loaded:
            return
        self.loaded = False
        self.releases += 1


def test_two_consecutive_batches_release_the_model_once_each(repos):
    """HAI lô liên tiếp -> model phải được đổ HAI lần, không phải một.

    Đây là kịch bản rò rỉ VRAM: worker gọi `after_phase` ở mỗi lần cạn giai
    đoạn, nên bản governor pop-sau-lần-đầu chỉ đổ model ở lô ĐẦU; lô thứ hai
    thoát giai đoạn trong khi `_loaded` đã rỗng, releaser không bao giờ được
    gọi nữa và engine vẫn nằm trong VRAM (`releases == 1` cả hai lô).
    """
    gov = SingleGpuGovernor(repos)
    handler = _ModelHandler()
    gov.register("asr:fw-large-v3-turbo", handler.release)
    worker = _worker(repos, gov, handler)

    for batch in (1, 2):
        repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))
        while worker.tick():
            pass
        assert handler.releases == batch, (
            f"lô {batch}: model phải được đổ {batch} lần, thấy {handler.releases}"
        )
        assert handler.loaded is False, f"lô {batch}: model còn nằm trong VRAM"


# Bảng ánh xạ kind -> loại JOB, cố ý viết lại TẠI ĐÂY thay vì import từ
# app.registry: import thì test chạy cùng nhịp với chính code under test và
# không bao giờ bắt được một ánh xạ sai. test_registry.py đã lập tiền lệ này.
_JOB_TYPE_OF_KIND = {"asr": "asr", "mt": "translate"}


def test_every_shipped_engine_phase_key_finds_the_stored_job_phase(repos):
    """Khoá giai đoạn của CẢ 8 engine phải tra ra job đã lưu `Job.phase`.

    Đây là mắt còn thiếu của Task 8: `test_registry.py` chỉ so `phase_key` với
    `phase_of`, tức so công thức với công thức. Test này đi hết đường: ghi job
    xuống SQLite với `phase = phase_of(job_type, spec.id)` rồi tra lại bằng
    `next_queued_for_phase(spec.phase_key)` — đúng câu truy vấn mà worker dùng.
    Lệch một chữ cái ở `phase_key` thì `next_queued_for_phase` trả None và hàng
    đợi đứng im mà không ném exception, nên phải khoá lại bằng 8/8.
    """
    specs = load_registry()
    assert len(specs) == 8, f"registry phải có 8 engine, thấy {len(specs)}"

    not_found: list[str] = []
    for spec in specs:
        job_type = _JOB_TYPE_OF_KIND[spec.kind]
        jid = repos.add_job(Job(
            id=None, workspace=1, type=job_type, engine=spec.id,
            phase=js.phase_of(job_type, spec.id), payload={},
        ))
        got = repos.next_queued_for_phase(spec.phase_key)
        if got is None or got.id != jid:
            not_found.append(f"{spec.id} (phase_key={spec.phase_key!r})")

    assert not not_found, (
        "phase_key không khớp phase đã lưu nên hàng đợi sẽ đứng im cho: "
        + ", ".join(not_found)
    )
    assert len(specs) - len(not_found) == 8, "phải là 8/8, không được sót engine nào"


# ---------------------------------------------------------------------------
# RULING R30: FakeClock phải tôn trọng `start` và không sinh mốc thời gian sai.
# Hai test dưới đây không liên quan tới hàng đợi, nhưng tests/fakes.py là thứ
# các task sau dùng chung nên khiếm khuyết ở đó phải bị khoá ngay tại đây.
# ---------------------------------------------------------------------------

def test_fake_clock_honours_its_start_argument():
    """Hai FakeClock khác `start` phải cho ra mốc KHÁC nhau và đúng thứ tự.

    Bản cũ bỏ qua `start` và luôn in từ `2026-09-25T00:00:nnZ`, nên test này
    đỏ ở cả ba assert: hai đồng hồ ra y hệt nhau.
    """
    a = FakeClock(start="2026-09-25T00:00:00Z")
    b = FakeClock(start="2027-01-01T12:00:00Z")
    a_first, b_first = a.now_iso(), b.now_iso()
    assert a_first != b_first, "hai FakeClock khác `start` không được ra cùng mốc"
    assert b_first > a_first, "mốc của `start` muộn hơn phải lớn hơn khi so chuỗi"
    a_second, b_second = a.now_iso(), b.now_iso()
    assert a_second != b_second
    assert a_second > a_first and b_second > b_first, "mỗi lần gọi phải tiến lên"


def test_fake_clock_stays_valid_and_ordered_past_sixty_seconds():
    """Qua giây thứ 60 phải cuộn phút, không sinh `...:00:60Z` rồi `...:100Z`.

    Bản cũ đỏ ngay ở `fromisoformat` của mốc thứ 60 và ở phép so thứ tự từ mốc
    thứ 100 (`:100` đứng trước `:99` khi so chuỗi).
    """
    clock = FakeClock(start="2026-09-25T00:00:00Z")
    stamps = [clock.now_iso() for _ in range(121)]

    assert len(set(stamps)) == len(stamps), "mỗi lần gọi phải là một mốc mới"
    assert stamps == sorted(stamps), "mốc phải tăng đơn điệu theo thứ tự gọi"
    for s in stamps:
        # Giây 60 không tồn tại -> mốc hỏng sẽ ném ValueError tại đây.
        _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    assert stamps[59].endswith(":00:59Z")
    assert stamps[60].endswith(":01:00Z"), f"qua phút phải cuộn, thấy {stamps[60]!r}"
    assert stamps[100].endswith(":01:40Z"), f"mốc thứ 100 sai, thấy {stamps[100]!r}"
