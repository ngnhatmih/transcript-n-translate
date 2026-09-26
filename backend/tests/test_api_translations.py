"""API bản dịch: tạo (sinh job), liệt kê kèm cờ `stale`, sửa tay.

Ba quyết định của tệp này, cả ba đều là hệ quả của những lỗi đã trả giá trong
chính giai đoạn này:

* **Mọi hành vi đi qua ĐƯỜNG THẬT** — `main.build_components()` +
  `main.build_app()` + `TestClient` — chứ không tự ráp lại assembly. Fixture tự
  dựng lại `PhaseQueueWorker`/`TranslateHandler` thì nó TRÔI khỏi `main.py` mà
  không test nào bắt (đúng lớp lỗi GĐ1a: `publish=` bị bỏ quên, SSE câm suốt).
  Vì cùng lý do, `wired` là TUPLE 5 phần tử của `build_components()` nguyên bản:
  không bọc lại thành một đối tượng có `.repos`/`.registry` — hai thuộc tính đó
  KHÔNG tồn tại trong sản phẩm, và một bản bọc như vậy là một assembly thứ hai
  nữa để trôi.
* **Không gán thẳng trường của đối tượng giả.** Task 11 từng có một test huỷ tự
  thoả mãn vì nó gán thẳng `job.cancel_requested`; ở đây `stale` được kiểm bằng
  cách SỬA TRANSCRIPT qua cổng thật (`increase_transcript_version`), để server
  tự tính lại từ dữ liệu.
* **`ensure_dirs()` đọc biến toàn cục của `app.config`**, không đọc tên đã
  import vào `main` — nên fixture vá CẢ `config` lẫn `main`, y như
  `tests/test_api_sources.py` và `tests/test_mt_wiring.py`. Vá mỗi `main` thì
  `build_components()` vẫn tạo `data/` THẬT của repo; `_assert_repo_data_untouched`
  dưới đây biến lời hứa đó thành thứ chạy được.
* **Phép dò Ollama bị ghim `set()`** trong fixture, nên `available` của engine
  `ollama` là `False` một cách TẤT ĐỊNH. Máy này đang chạy Ollama và chỉ pull
  `qwen2.5:3b-instruct-q4_K_M`, nên một bài hardcode "3b sẵn sàng" hay "3b không
  sẵn sàng" sẽ đỏ ở máy khác. Bài nào cần engine THẬT của registry thì nêu rõ
  engine nào, và `test_availability_of_a_real_registry_engine_holds_either_way`
  là bài đối chứng chạy với phép dò THẬT (không vá).
"""
from __future__ import annotations

import dataclasses
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.job_state import phase_of
from app.domain.models import Segment, Word
from app.registry import by_id, of_kind

#: Model KHÔNG có trong `/api/tags` của bất kỳ máy nào — tên này chỉ tồn tại ở
#: đây. Dùng nó để dựng nhánh "engine không sẵn sàng" một cách TẤT ĐỊNH thay vì
#: cá cược vào việc máy đang chạy có pull model nào.
NEVER_PULLED_MODEL_REF = "khong-bao-gio-duoc-pull:q0"

#: Engine `inprocess`, luôn sẵn sàng (`_mark_availability` trả `True` cho mọi
#: engine không phải `runtime == "ollama"`). Đây là engine mặc định đã ship.
INPROCESS_ENGINE_ID = "opus-mt"


def _seed(repos) -> tuple[int, int]:
    """Một source + transcript + một bản dịch tay, trả `(transcript_id, tr_id)`."""
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh",
                               segments=[Segment(i=1, start=0.0, end=1.0, text="你好")])
    tr_id = repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=INPROCESS_ENGINE_ID,
        target_lang="vi", segments=[Segment(i=1, start=0.0, end=1.0, text="Xin chào")],
        prompt_version="raw-p1")
    return tid, tr_id


def _repo_data_dirs() -> list[pathlib.Path]:
    """Bốn thư mục mà `ensure_dirs()` tạo cho cấu hình THẬT của repo.

    Đường dẫn suy từ `config.__file__`, KHÔNG từ `config.DATA_DIR`: chính
    `DATA_DIR` là thứ fixture vá, nên hỏi nó là hỏi kẻ vừa bị đổi.
    """
    from app import config

    root = pathlib.Path(config.__file__).resolve().parents[2] / "data"
    return [root, root / "media", root / "logs", root / "output"]


def _snapshot_repo_data_dirs() -> dict[pathlib.Path, bool]:
    return {d: d.exists() for d in _repo_data_dirs()}


def _assert_repo_data_dirs_untouched(before: dict[pathlib.Path, bool]) -> None:
    created = [str(d) for d, existed in before.items() if not existed and d.exists()]
    assert not created, (
        "build_components() đã tạo thư mục THẬT trong repo: " + ", ".join(created)
        + ". Phải vá `app.config` (nơi `ensure_dirs()` đọc biến), không chỉ vá "
          "tên đã import vào `main`."
    )


def _point_everything_at_tmp(tmp_path, monkeypatch, *, ollama_pulled: set[str]):
    """Chuyển mọi đường dẫn vào `tmp_path` và ghim phép dò Ollama.

    Trả `(main, config, data)`. Registry VẪN là `registry.json` THẬT và adapter
    engine vẫn là những adapter thật của `_build_mt_engines`: thứ duy nhất bị
    thay ở đây là đường dẫn đĩa và câu trả lời của phép dò mạng.
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
    # Một nút điều khiển DUY NHẤT cho cả hai nửa của `available`: phép dò trả về
    # TÊN model đã pull, nên `set()` là "Ollama không phục vụ được engine nào".
    monkeypatch.setattr(main, "ollama_available", lambda *a, **k: set(ollama_pulled))
    return main, config, data


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """`build_components()` + `build_app()` THẬT, chỉ đường dẫn bị chuyển đi.

    Trả `(client, repos, specs, worker, broker, mt_engines)` — nguyên tuple của
    `build_components()`, không bọc lại.
    """
    before = _snapshot_repo_data_dirs()
    main, _config, _data = _point_everything_at_tmp(
        tmp_path, monkeypatch, ollama_pulled=set())

    built = main.build_components()
    _assert_repo_data_dirs_untouched(before)
    repos, specs, worker, broker, mt_engines = built
    app = main.build_app(repos, specs, worker, broker, mt_engines)

    with TestClient(app) as client:
        client.repos = repos            # type: ignore[attr-defined]
        yield client, repos, specs, worker, broker, mt_engines


class _FakeMtEngine:
    """Engine dịch GIẢ cắm vào ĐÚNG dict `mt_engines` của composition root.

    Nó chỉ đổi `text` qua `dataclasses.replace` — KHÔNG dựng `Segment(...)` bằng
    tay (13 trường; dựng tay là cách hai task trong giai đoạn này nuốt 7 trường).
    """

    def __init__(self, model_ref: str, *, supports_glossary: bool = False,
                 engine_id: str | None = None) -> None:
        self.model_ref = model_ref
        self._supports_glossary = supports_glossary
        self.received_engine_id = engine_id
        self.batches: list[list[int]] = []
        self.last_stats = None

    @property
    def engine_id(self) -> str:
        return f"engine-id-cua-{self.model_ref}"

    def supports_glossary(self) -> bool:
        return self._supports_glossary

    def translate(self, batch, glossary, opts):
        self.batches.append([s.i for s in batch])
        return [dataclasses.replace(s, text=f"[{opts.target_lang}] {s.text}")
                for s in batch]

    def release(self) -> None:
        return None


# ---------------------------------------------------------------------------
# POST /api/translations — tạo bản dịch, xếp MỘT job `translate`
# ---------------------------------------------------------------------------

def test_create_translation_enqueues_a_translate_job(wired):
    """Job phải mang ĐÚNG khoá payload `TranslateHandler.run` đọc.

    Thừa/thiếu một khoá thì job chết bằng `KeyError` ở TẬN worker, sau khi hàng
    `translations` đã được ghi — một bản dịch `queued` không bao giờ chạy.
    """
    c, repos, _specs, _worker, _broker, _mt = wired
    tid, _ = _seed(repos)

    r = c.post("/api/translations", json={"transcript_id": tid,
                                          "engine": INPROCESS_ENGINE_ID})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["translation"]["engine"] == INPROCESS_ENGINE_ID
    assert body["translation"]["transcript_id"] == tid
    assert body["translation"]["transcript_version"] == 1
    assert body["translation"]["stale"] is False

    job = repos.get_job(body["job"]["id"])
    assert job.type == "translate"
    assert job.workspace == 2
    assert job.phase == phase_of("translate", INPROCESS_ENGINE_ID)
    assert job.engine == INPROCESS_ENGINE_ID
    assert set(job.payload) == {"translation_id", "transcript_id", "engine_id",
                                "source_lang", "target_lang"}, job.payload
    assert job.payload["translation_id"] == body["translation"]["id"]
    assert job.payload["transcript_id"] == tid
    assert job.payload["engine_id"] == INPROCESS_ENGINE_ID
    assert job.payload["source_lang"] == "zh"
    assert job.payload["target_lang"] == "vi"
    # Hàng phải CÓ THẬT trước khi job chạy: handler tra nó bằng
    # `translation_id` và `NotFound` ở tận worker là mất cả job.
    stored = repos.get_translation(body["translation"]["id"])
    assert stored.status == "queued"
    assert stored.segments == []


def test_create_translation_uses_the_spec_prompt_version_not_an_adapter_import(wired):
    """Correction B · `prompt_version` là dữ liệu của `spec.capabilities`.

    Route `from app.adapters.mt.prompts import PROMPT_VERSION` là đỏ ngay
    (`test_api_layer_does_not_import_adapters`), nên giá trị phải được tính ở
    composition root — CÙNG khuôn với `available` — và tầng API chỉ tiêu thụ.
    """
    c, repos, specs, _worker, _broker, _mt = wired
    tid, _ = _seed(repos)
    expected = by_id(specs, INPROCESS_ENGINE_ID).capabilities["prompt_version"]
    assert expected == "raw-p1", (
        "registry.json khai opus-mt; PROMPT_VERSION của nó là 'raw-p1'"
    )

    body = c.post("/api/translations", json={"transcript_id": tid,
                                             "engine": INPROCESS_ENGINE_ID}).json()
    assert body["translation"]["prompt_version"] == expected
    assert repos.get_translation(body["translation"]["id"]).prompt_version == expected


def test_a_created_translation_is_consumed_by_the_real_handler(wired):
    """Đường THẬT đầu-cuối: HTTP -> hàng + job -> worker thật -> handler thật.

    Chỉ adapter model là giả. Không có bài này thì một payload sai khoá vẫn xanh
    ở bài trên (nó chỉ so khoá), còn ở đây worker phải THẬT SỰ dịch xong.
    """
    c, repos, specs, worker, _broker, mt_engines = wired
    tid, _ = _seed(repos)

    engine = _FakeMtEngine("gia-lap", engine_id=INPROCESS_ENGINE_ID)
    mt_engines[INPROCESS_ENGINE_ID] = engine

    r = c.post("/api/translations", json={"transcript_id": tid,
                                          "engine": INPROCESS_ENGINE_ID})
    assert r.status_code == 201, r.text
    tr_id = r.json()["translation"]["id"]

    while worker.tick():
        pass

    assert engine.batches == [[1]], (
        f"handler thật không nhận được segment nào: {engine.batches}"
    )
    stored = repos.get_translation(tr_id)
    assert stored.status == "done", f"trạng thái sau khi chạy: {stored.status}"
    # Nguồn của bản dịch là SEGMENTS CỦA TRANSCRIPT ("你好"), không phải bản dịch
    # tay đã có sẵn trong DB — engine chỉ được nhìn thấy văn bản nguồn.
    assert [s.text for s in stored.segments] == ["[vi] 你好"]
    assert engine.received_engine_id == INPROCESS_ENGINE_ID


def test_create_translation_rejects_an_unknown_engine_with_422(wired):
    """Id lạ là lỗi ĐẦU VÀO, và thông báo phải nói ĐÚNG nó không có trong registry.

    Khẳng định mỗi `status_code == 422` là chưa đủ: rơi về một engine khác (ví dụ
    `specs[0]`) rồi bị từ chối vì sai `kind` cũng ra 422 — cùng mã, KHÁC lý do, và
    thông báo khi đó nói về một engine mà người dùng không hề gõ. Đo thật với
    mutant `by_id(...)` -> `next(..., specs[0])`: body là
    `"engine không phải engine dịch: 'khong-co' (kind='asr')"` — nó BỊA ra rằng
    `khong-co` tồn tại và là engine ASR.

    Nên phép đỏ ở đây bám vào chính lời nói dối đó: một id không có trong registry
    thì thông báo KHÔNG được gán cho nó một `kind`.
    """
    c, repos, _specs, _worker, _broker, _mt = wired
    tid, _ = _seed(repos)
    r = c.post("/api/translations", json={"transcript_id": tid, "engine": "khong-co"})
    assert r.status_code == 422, r.text
    assert "khong-co" in r.text, f"lỗi phải nêu đúng id người dùng gửi: {r.text!r}"
    assert "kind=" not in r.text, (
        "id KHÔNG có trong registry không được gán cho một `kind` — thông báo kiểu "
        f"'... (kind=asr)' là bịa ra một engine có thật: {r.text!r}"
    )
    assert [j for j in repos.list_jobs() if j.type == "translate"] == []


def test_create_translation_rejects_an_asr_engine_with_422(wired):
    """`engine` phải là engine DỊCH: nhận id ASR là xếp một job dịch chắc chắn
    `KeyError` trong `mt_engines` (dict chỉ có engine `kind == "mt"`)."""
    c, repos, specs, _worker, _broker, _mt = wired
    tid, _ = _seed(repos)
    asr_id = of_kind(specs, "asr")[0].id

    r = c.post("/api/translations", json={"transcript_id": tid, "engine": asr_id})
    assert r.status_code == 422, r.text
    assert [j for j in repos.list_jobs() if j.type == "translate"] == []


def test_create_translation_rejects_an_unavailable_engine_with_409(tmp_path, monkeypatch):
    """Correction D · "chưa pull" bị từ chối Ở API, không để job chết ở worker.

    Nhánh này TẤT ĐỊNH: `registry.json` được nạp nguyên bản nhưng chỉ MỘT engine
    thật bị đổi `model_ref` thành một tên không máy nào pull được. Cách duy nhất
    để chắc chắn là không dựa vào việc máy đang chạy có pull gì.
    """
    from app.adapters.registry_file import load_registry, load_default_mt

    before = _snapshot_repo_data_dirs()
    main, _config, _data = _point_everything_at_tmp(
        tmp_path, monkeypatch, ollama_pulled=set())

    victim = "hy-mt-1.5-7b"
    specs = [dataclasses.replace(s, model_ref=NEVER_PULLED_MODEL_REF)
             if s.id == victim else s for s in load_registry()]
    monkeypatch.setattr(main, "load_registry", lambda: specs)
    monkeypatch.setattr(main, "load_default_mt", lambda: load_default_mt())

    repos, specs, worker, broker, mt_engines = main.build_components()
    _assert_repo_data_dirs_untouched(before)
    app = main.build_app(repos, specs, worker, broker, mt_engines)

    spec = by_id(specs, victim)
    assert spec.capabilities["available"] is False, (
        f"{victim}: model_ref {NEVER_PULLED_MODEL_REF!r} không thể đã được pull"
    )
    tid, _ = _seed(repos)
    # Đo TRƯỚC request: `_seed` đã có một bản dịch, nên "rỗng" là khẳng định sai.
    # Thứ phải đúng là request hỏng KHÔNG thêm hàng nào và KHÔNG xếp job nào.
    translations_before = len(repos.list_translations())

    with TestClient(app) as c:
        r = c.post("/api/translations", json={"transcript_id": tid, "engine": victim})
    assert r.status_code == 409, r.text
    assert victim in r.text, f"lỗi phải nêu đúng engine: {r.text!r}"
    assert [j for j in repos.list_jobs() if j.type == "translate"] == []
    assert len(repos.list_translations()) == translations_before, (
        "từ chối sớm nghĩa là KHÔNG ghi hàng `translations` mồ côi"
    )


def test_create_translation_rejects_an_unknown_transcript_with_404(wired):
    c, _repos, _specs, _worker, _broker, _mt = wired
    r = c.post("/api/translations", json={"transcript_id": 999,
                                          "engine": INPROCESS_ENGINE_ID})
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# GET /api/translations?transcript_id= — cờ `stale` TÍNH Ở SERVER
# ---------------------------------------------------------------------------

def test_list_returns_stale_flag_computed_server_side(wired):
    """`stale = transcripts.version > translations.transcript_version`, tính lại
    mỗi lần đọc. Không có cột `stale` nào được lưu, nên nó không thể "quên cập
    nhật" — nhưng cũng không thể đúng nếu route tự suy ở client.
    """
    c, repos, _specs, _worker, _broker, _mt = wired
    tid, tr_id = _seed(repos)

    rows = c.get(f"/api/translations?transcript_id={tid}").json()
    assert [r["id"] for r in rows] == [tr_id]
    assert rows[0]["stale"] is False
    assert rows[0]["engine"] == INPROCESS_ENGINE_ID
    assert rows[0]["target_lang"] == "vi"
    assert rows[0]["prompt_version"] == "raw-p1"
    assert rows[0]["status"] == "queued", (
        "giao diện phân biệt 'vừa xếp' với 'đã xong' bằng `status`"
    )

    # Sửa transcript qua CỔNG THẬT (tăng version) — không gán thẳng trường nào.
    repos.update_transcript_segments(
        tid, [Segment(i=1, start=0.0, end=1.0, text="你好呀")])

    rows = c.get(f"/api/translations?transcript_id={tid}").json()
    assert rows[0]["stale"] is True, "version transcript tăng thì bản dịch cũ là stale"
    assert rows[0]["transcript_version"] == 1, (
        "bản dịch vẫn phải nhớ nó dịch TỪ version nào"
    )


def test_list_returns_every_translation_of_the_transcript_newest_first(wired):
    c, repos, _specs, _worker, _broker, _mt = wired
    tid, first = _seed(repos)
    second = repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=INPROCESS_ENGINE_ID,
        target_lang="en", segments=[], prompt_version="raw-p1")
    other_tid, other = _seed(repos)

    rows = c.get(f"/api/translations?transcript_id={tid}").json()
    assert [r["id"] for r in rows] == [second, first], (
        "danh sách phải là của ĐÚNG transcript được hỏi, mới nhất trước"
    )
    assert {r["target_lang"] for r in rows} == {"vi", "en"}
    assert other not in [r["id"] for r in rows]


def test_list_requires_transcript_id(wired):
    c, _repos, _specs, _worker, _broker, _mt = wired
    assert c.get("/api/translations").status_code == 422


def test_list_unknown_transcript_is_404(wired):
    c, _repos, _specs, _worker, _broker, _mt = wired
    assert c.get("/api/translations?transcript_id=999").status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/translations/{id} — sửa tay MỘT segment
# ---------------------------------------------------------------------------

def test_patch_edits_one_segment_text_and_keeps_every_other_field(wired):
    """Sửa tay chỉ được đổi `text`.

    Segment có 13 trường, và `dataclasses.replace` là cách duy nhất giữ hết
    chúng: dựng `Segment(...)` bằng tay ở route sẽ nuốt `speaker`, `words`,
    `emotion`, `events`, `t`, `qa`, `suspect`... — đúng lỗi hai task trong giai
    đoạn này đã ship. Fixture dưới đây nhồi đủ trường để phép đỏ là thật.
    """
    c, repos, _specs, _worker, _broker, _mt = wired
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh",
                               segments=[Segment(i=1, start=0.0, end=1.0, text="你好")])
    full = Segment(i=1, start=0.0, end=1.0, text="Xin chào",
                   words=[Word(w="Xin", s=0.0, e=0.4)],
                   emotion="neutral", events=["music"], speaker="SPK_1",
                   avg_logprob=-0.2, no_speech_prob=0.01, suspect=True,
                   t="MT", qa=["thieu_dau"])
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine=INPROCESS_ENGINE_ID, target_lang="vi",
                                  segments=[full], prompt_version="raw-p1")

    r = c.patch(f"/api/translations/{tr_id}", json={"segments": [
        {"i": 1, "start": 0.0, "end": 1.0, "text": "Xin chào bạn"}]})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == tr_id
    assert r.json()["stale"] is False

    got = repos.get_translation(tr_id).segments[0]
    assert got.text == "Xin chào bạn"
    assert dataclasses.replace(got, text="Xin chào") == full, (
        "PATCH chỉ được đổi `text`; mọi trường khác phải là dữ liệu của bản gốc"
    )
    assert got.words == [Word(w="Xin", s=0.0, e=0.4)]
    assert got.speaker == "SPK_1"
    assert got.emotion == "neutral"
    assert got.events == ["music"]
    assert got.t == "MT"
    assert got.qa == ["thieu_dau"]
    assert got.suspect is True
    assert got.start == 0.0 and got.end == 1.0


def test_patch_ignores_client_supplied_timing_and_speaker(wired):
    """Client gửi `start`/`end`/`speaker` KHÁC bản gốc thì phải bị bỏ qua.

    `start`/`end` là thời lượng của bản GỐC (xem docstring của route): nghe theo
    client là phụ đề lệch tiếng, mà client thì không biết gì hơn dữ liệu đã lưu.
    Đây là mutant X7 của review Task 13: route cũ nhận thẳng `seg.start`/`seg.end`
    — đúng dạng code của brief — và CẢ TỆP vẫn xanh, nên bài này phải đỏ khi route
    làm thế. `speaker` nằm trong payload để ghim rằng nó cũng không đi qua được
    (`SegmentIn` không có trường đó, nên nó bị bỏ im lặng).
    """
    c, repos, _specs, _worker, _broker, _mt = wired
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh",
                               segments=[Segment(i=1, start=0.0, end=1.0, text="你好")])
    full = Segment(i=1, start=0.0, end=1.0, text="Xin chào",
                   words=[Word(w="Xin", s=0.0, e=0.4)],
                   emotion="neutral", events=["music"], speaker="SPK_1",
                   avg_logprob=-0.2, no_speech_prob=0.01, suspect=True,
                   t="MT", qa=["thieu_dau"])
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine=INPROCESS_ENGINE_ID, target_lang="vi",
                                  segments=[full], prompt_version="raw-p1")

    r = c.patch(f"/api/translations/{tr_id}", json={"segments": [
        {"i": 1, "start": 99.0, "end": 100.0, "text": "Xin chào bạn",
         "speaker": "SPK_9"}]})
    assert r.status_code == 200, r.text
    got = repos.get_translation(tr_id).segments[0]
    assert (got.start, got.end) == (0.0, 1.0), (
        "PATCH phải giữ thời lượng của bản GỐC, không nghe `start`/`end` của client"
    )
    assert got.speaker == "SPK_1", "client không được đổi người nói của bản gốc"
    assert dataclasses.replace(got, text="Xin chào") == full, (
        "PATCH chỉ được đổi `text`; mọi trường khác phải là dữ liệu của bản gốc"
    )


def test_patch_preserves_the_stored_segment_order(wired):
    """Sửa chữ MỘT dòng không được sắp xếp lại những dòng còn lại.

    Route cũ dựng lại danh sách bằng `sorted(edited)`, nên một bản dịch lưu
    `[(2,B),(1,A)]` đổi thành `[(1,A!),(2,B)]` chỉ vì người dùng sửa `i=1`. Thứ tự
    đã lưu là dữ liệu của bản gốc — cùng loại với `start`/`end`.
    """
    c, repos, _specs, _worker, _broker, _mt = wired
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh",
                               segments=[Segment(i=2, start=1.0, end=2.0, text="b"),
                                         Segment(i=1, start=0.0, end=1.0, text="a")])
    tr_id = repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=INPROCESS_ENGINE_ID,
        target_lang="vi", prompt_version="raw-p1",
        segments=[Segment(i=2, start=1.0, end=2.0, text="B"),
                  Segment(i=1, start=0.0, end=1.0, text="A")])
    before = [(s.i, s.text) for s in repos.get_translation(tr_id).segments]
    assert before == [(2, "B"), (1, "A")], (
        f"fixture phải lưu ĐÚNG thứ tự đã đưa vào, nhận được {before}"
    )

    r = c.patch(f"/api/translations/{tr_id}", json={"segments": [
        {"i": 1, "start": 0.0, "end": 1.0, "text": "A!"}]})
    assert r.status_code == 200, r.text
    got = [(s.i, s.text) for s in repos.get_translation(tr_id).segments]
    assert got == [(2, "B"), (1, "A!")], (
        "PATCH phải giữ thứ tự đã lưu, không sắp xếp lại theo `i`"
    )


def test_patch_keeps_the_segments_it_was_not_given(wired):
    """PATCH là sửa MỘT PHẦN: không gửi segment nào thì không được xoá segment nào."""
    c, repos, _specs, _worker, _broker, _mt = wired
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh",
                               segments=[Segment(i=1, start=0.0, end=1.0, text="a"),
                                         Segment(i=2, start=1.0, end=2.0, text="b")])
    tr_id = repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=INPROCESS_ENGINE_ID,
        target_lang="vi", prompt_version="raw-p1",
        segments=[Segment(i=1, start=0.0, end=1.0, text="A"),
                  Segment(i=2, start=1.0, end=2.0, text="B")])

    r = c.patch(f"/api/translations/{tr_id}", json={"segments": [
        {"i": 2, "start": 1.0, "end": 2.0, "text": "B!"}]})
    assert r.status_code == 200, r.text
    got = repos.get_translation(tr_id).segments
    assert [(s.i, s.text) for s in got] == [(1, "A"), (2, "B!")], (
        "segment không được gửi lên phải giữ nguyên, và thứ tự phải ổn định"
    )


def test_patch_rejects_segment_ids_that_do_not_exist(wired):
    """Id lạ là lỗi ĐẦU VÀO (422), không phải một segment mới được thêm vào."""
    c, repos, _specs, _worker, _broker, _mt = wired
    _tid, tr_id = _seed(repos)

    r = c.patch(f"/api/translations/{tr_id}", json={"segments": [
        {"i": 42, "start": 0.0, "end": 1.0, "text": "x"}]})
    assert r.status_code == 422, r.text
    assert "42" in r.text, f"lỗi phải nêu đúng id lạ: {r.text!r}"
    got = repos.get_translation(tr_id).segments
    assert [(s.i, s.text) for s in got] == [(1, "Xin chào")], (
        "một request hỏng không được ghi gì"
    )


def test_patch_with_no_segments_is_a_no_op(wired):
    c, repos, _specs, _worker, _broker, _mt = wired
    _tid, tr_id = _seed(repos)
    r = c.patch(f"/api/translations/{tr_id}", json={"segments": []})
    assert r.status_code == 200, r.text
    assert [s.text for s in repos.get_translation(tr_id).segments] == ["Xin chào"]


def test_patch_unknown_translation_is_404(wired):
    c, _repos, _specs, _worker, _broker, _mt = wired
    assert c.patch("/api/translations/999", json={"segments": []}).status_code == 404


def test_patch_reports_the_same_stale_flag_as_the_list_route(wired):
    """`stale` có MỘT nguồn sự thật, và `PATCH` cũng phải đọc nguồn đó.

    Trả cứng `False` ở `PATCH` là nói dối ngay sau khi người dùng vừa sửa một bản
    dịch đã lệch thời: giao diện nhận `stale: false` từ câu trả lời của chính thao
    tác sửa, rồi lần làm mới danh sách lại thấy `true`.
    """
    c, repos, _specs, _worker, _broker, _mt = wired
    tid, tr_id = _seed(repos)
    repos.update_transcript_segments(
        tid, [Segment(i=1, start=0.0, end=1.0, text="你好呀")])

    assert c.get(f"/api/translations?transcript_id={tid}").json()[0]["stale"] is True
    r = c.patch(f"/api/translations/{tr_id}", json={"segments": [
        {"i": 1, "start": 0.0, "end": 1.0, "text": "Xin chào bạn"}]})
    assert r.status_code == 200, r.text
    assert r.json()["stale"] is True, (
        "PATCH phải tính `stale` như `GET`, không trả cứng False"
    )


# ---------------------------------------------------------------------------
# Correction C — engine dịch mặc định phải VỪA tồn tại VỪA sẵn sàng
# ---------------------------------------------------------------------------

def test_build_components_exposes_prompt_version_next_to_available(wired):
    """Correction B: dữ liệu dẫn xuất được tính ở composition root.

    Mọi engine `mt` phải có `prompt_version` TRONG `capabilities`, cùng chỗ với
    `available` — nếu không thì route chỉ còn cách import adapter (bị cấm).
    """
    _c, _repos, specs, _worker, _broker, _mt = wired
    from app.adapters.mt.prompts import PROMPT_VERSION

    mt_specs = of_kind(specs, "mt")
    assert mt_specs, "registry.json phải có engine mt"
    for spec in mt_specs:
        assert "available" in spec.capabilities, spec.id
        assert spec.capabilities.get("prompt_version") == PROMPT_VERSION.get(
            spec.id, "unknown"), (
            f"{spec.id}: prompt_version phải tính ở build_components(); "
            f"nhận được {spec.capabilities.get('prompt_version')!r}"
        )
    assert by_id(specs, INPROCESS_ENGINE_ID).capabilities["prompt_version"] == "raw-p1"


def test_build_components_refuses_an_mt_default_that_is_not_available(
        tmp_path, monkeypatch):
    """Correction C · `available=False` chỉ đóng dropdown, KHÔNG đóng đường setting.

    Đo thật ở re-review Task 12: đặt `MT_DEFAULT_SETTING='hy-mt-1.5-7b'` trên máy
    chưa pull model đó sinh một hàng `translations` `queued` rồi job chết
    `KeyError` ở worker. Phải hỏng ở chỗ SỚM NHẤT — lúc dựng — kèm chỉ dẫn.
    """
    from app.adapters.registry_file import load_registry

    before = _snapshot_repo_data_dirs()
    main, _config, _data = _point_everything_at_tmp(
        tmp_path, monkeypatch, ollama_pulled=set())
    # Registry THẬT (để `default_mt = opus-mt` hợp lệ), nhưng setting của người
    # dùng trỏ vào một engine `ollama` chưa pull — đúng đường mà dropdown không
    # đóng được.
    victim = "hy-mt-1.5-7b"
    monkeypatch.setattr(main, "load_registry", load_registry)

    repos = SqliteRepos(main.DB_PATH, clock=SystemClock())
    repos.init_schema()
    repos.set_setting("default_mt_engine", victim)

    with pytest.raises(RuntimeError) as excinfo:
        main.build_components()
    _assert_repo_data_dirs_untouched(before)

    message = str(excinfo.value)
    assert victim in message, f"lỗi phải nêu ĐÚNG engine nào: {message!r}"
    assert "default_mt_engine" in message or "default_mt" in message, (
        f"lỗi phải nêu chỗ cần sửa: {message!r}"
    )


def test_build_components_still_accepts_an_available_mt_default(wired):
    """Nửa ĐỐI CHỨNG của correction C: mặc định đã ship (`opus-mt`, in-process)
    vẫn phải dựng được — nếu không thì phép kiểm mới chặn luôn khởi động bình
    thường, và mọi bài khác ở đây đỏ vì một lý do không liên quan.

    `wired` dựng xong ở trên chính là bằng chứng đó; bài này ghim THÊM chủ thể:
    mặc định thật của `registry.json` phải có mặt trong `mt_engines`.
    """
    _c, _repos, specs, _worker, _broker, mt_engines = wired
    from app.adapters.registry_file import load_default_mt

    declared = load_default_mt()
    assert declared == INPROCESS_ENGINE_ID, (
        f"registry.json đổi mặc định? Bài này ghim {INPROCESS_ENGINE_ID!r}, "
        f"nhận {declared!r}"
    )
    assert by_id(specs, declared).capabilities["available"] is True
    assert declared in mt_engines


def test_availability_of_a_real_registry_engine_holds_either_way(tmp_path, monkeypatch):
    """Correction E · Ollama ĐANG chạy trên máy này với ĐÚNG MỘT model đã pull.

    Bài này cố ý KHÔNG vá `ollama_available`, nên nó phải xanh trên cả máy có
    Ollama lẫn máy không, và trên mọi tập model đã pull — không hardcode giá trị
    nào. Quan hệ được ghim là hệ quả, không phải con số: engine có `available`
    ĐÚNG BẰNG việc nó có mặt trong `mt_engines`.
    """
    from app import config, main

    before = _snapshot_repo_data_dirs()
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(config, "LOG_DIR", data / "logs")
    monkeypatch.setattr(config, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "DB_PATH", data / "app.db")
    monkeypatch.setattr(main, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(main, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "LOG_DIR", data / "logs")
    # `ollama_available` KHÔNG bị vá ở đây: đây chính là bài đối chứng cho
    # `test_real_probe_tolerates_both_answers` bên `tests/test_mt_wiring.py`.

    repos, specs, _worker, _broker, mt_engines = main.build_components()
    _assert_repo_data_dirs_untouched(before)

    ollama_specs = [s for s in of_kind(specs, "mt") if s.runtime == "ollama"]
    assert ollama_specs, "registry.json phải còn engine ollama để bài này có nghĩa"
    for spec in ollama_specs:
        assert spec.capabilities["available"] in (True, False)
        assert (spec.id in mt_engines) is spec.capabilities["available"], (
            f"{spec.id}: available={spec.capabilities['available']} nhưng có "
            f"trong mt_engines: {spec.id in mt_engines}"
        )
    assert by_id(specs, INPROCESS_ENGINE_ID).capabilities["available"] is True
    assert INPROCESS_ENGINE_ID in mt_engines
    assert repos is not None


# ---------------------------------------------------------------------------
# I-3 (hàng `translations` phải theo số phận của job) và I-4 (một builder JSON
# cho mọi endpoint) — hai mục của review cuối nhánh
# ---------------------------------------------------------------------------

def test_cancelling_a_queued_translation_job_also_settles_the_translation(wired):
    """Huỷ một job `queued` phải rời hàng dịch khỏi `queued`, không chỉ bảng `jobs`.

    Job chưa chạy thì bị huỷ NGAY (`set_job_state`), và nó KHÔNG BAO GIỜ chạy
    handler — nên nếu chỉ `jobs` được đổi trạng thái thì hàng dịch đứng nguyên ở
    `queued` VĨNH VIỄN, không còn job nào đứng sau. `GET /api/translations` (Task
    13 phơi `status`) khi đó hiện một bản dịch "đang chờ" không bao giờ chạy: hai
    mặt của cùng một bản dịch nói hai chuyện.
    """
    c, repos, _specs, worker, _broker, _mt = wired
    tid, _ = _seed(repos)
    # `TestClient` đã khởi động luồng worker NỀN của app (`run_forever`), và nó
    # bốc job trong 0,05 s. Bài này cần job còn `queued` cho tới lúc gọi route
    # huỷ, nên luồng đó phải dừng TRƯỚC khi job được ghi — nếu không, kết quả phụ
    # thuộc việc luồng nền có kịp bốc job hay không, tức là một test chập chờn.
    worker.stop()

    created = c.post("/api/translations", json={"transcript_id": tid,
                                                "engine": INPROCESS_ENGINE_ID})
    assert created.status_code == 201, created.text
    body = created.json()
    job_id = body["job"]["id"]
    tr_id = body["translation"]["id"]
    assert repos.get_translation(tr_id).status == "queued"

    cancelled = c.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    assert repos.get_translation(tr_id).status == "cancelled", (
        "job đã `cancelled` mà bản dịch còn `queued` là trạng thái treo vĩnh viễn"
    )

    listed = c.get(f"/api/translations?transcript_id={tid}").json()
    # `_seed` đã để lại một bản dịch `queued` của chính nó, nên tìm ĐÚNG hàng vừa
    # tạo thay vì so cả danh sách — bài này nói về một bản dịch, không về số hàng.
    by_id_listed = {r["id"]: r for r in listed}
    assert by_id_listed[tr_id]["status"] == "cancelled", (
        "và API phải THẤY trạng thái đó, không chỉ DB"
    )
    assert by_id_listed[tr_id]["stale"] is False, (
        "đổi trạng thái không được đụng tới version đã dịch từ"
    )


def test_cancelling_a_queued_job_of_another_type_writes_no_translation(wired):
    """Job KHÔNG mang `translation_id` (mọi job `asr`/`ingest`/`export`) là NO-OP.

    Nhánh đối chiếu tra id từ payload; một job không có khoá đó không được làm gì
    cả — kể cả không được ném. Bài này là vế đối chứng của bài trên: nếu phép đối
    chiếu "đoán" id (ví dụ theo id job hay theo bản dịch mới nhất), nó sẽ ghi vào
    một hàng không liên quan.
    """
    c, repos, _specs, worker, _broker, _mt = wired
    tid, tr_id = _seed(repos)
    # Cùng lý do như bài trên: luồng worker nền dừng trước khi job được ghi, để
    # trạng thái job không phụ thuộc thời điểm.
    worker.stop()

    from app.domain.models import Job

    job = Job(id=None, workspace=1, type="ingest", engine=None, phase="ingest:-",
              payload={"source_id": 1})
    job_id = repos.add_job(job)

    assert c.post(f"/api/jobs/{job_id}/cancel").status_code == 200
    assert repos.get_translation(tr_id).status == "queued", (
        "job khác loại không được chạm vào hàng dịch nào"
    )


def test_the_two_endpoints_describe_a_translation_identically(wired):
    """I-4: CÙNG một hàng ⇒ CÙNG một object ở hai endpoint.

    `/api/translations` và `/api/transcripts/{id}` từng có hai builder riêng:
    một bên phát `transcript_version` + `status`, bên kia phát
    `translated_from_version` và KHÔNG có `status`. Client phải special-case theo
    endpoint, và endpoint chi tiết transcript — đúng cái Workspace 2 mở cho mỗi
    video — không phân biệt được một bản dịch `queued` với một bản dịch `done`.

    So `==` trên cả hai object là phép kiểm mạnh nhất: nó bắt mọi khoá thừa,
    thiếu, đổi tên VÀ mọi giá trị lệch, không chỉ hai khoá được nêu tên.
    """
    c, repos, _specs, worker, _broker, _mt = wired
    tid, tr_id = _seed(repos)
    # Luồng worker nền dừng trước: job `translate` đang `queued` trong `_seed`
    # không dành cho nó, và một lần bốc trúng sẽ ghi trạng thái khác vào đúng hàng
    # mà bài này đang ghim.
    worker.stop()
    # Trạng thái KHÁC `queued` để phép so phân biệt được "có `status`" với "có
    # `status` đúng": cả hai endpoint cùng rơi về `queued` cũng sẽ bằng nhau nếu
    # builder đọc nhầm hằng số.
    repos.set_translation_status(tr_id, "done")

    from_list = c.get(f"/api/translations?transcript_id={tid}").json()[0]
    from_detail = c.get(f"/api/transcripts/{tid}").json()["translations"][0]

    assert from_list == from_detail, (
        "hai endpoint mô tả CÙNG một hàng bằng hai hình dạng khác nhau:\n"
        f"  /api/translations      : {sorted(from_list)}\n"
        f"  /api/transcripts/{{id}} : {sorted(from_detail)}"
    )
    assert from_detail["status"] == "done"
    assert from_detail["transcript_version"] == 1
    assert "translated_from_version" not in from_detail, (
        "khoá cũ phải BIẾN MẤT, không phải sống song song: hai tên cho một cột là "
        "đúng thứ hai builder gây ra"
    )


def test_the_two_endpoints_agree_after_the_transcript_changes(wired):
    """Cùng builder, nhưng `stale` vẫn phải TÍNH LẠI: sửa transcript ⇒ cả hai đỏ cờ.

    Một builder dùng chung chỉ đáng tin nếu nó không biến `stale` thành hằng số:
    route danh sách tự tính từ version hiện tại, route chi tiết nhận version từ
    chính hàng transcript vừa đọc. Bài này sửa transcript qua CỔNG THẬT (tăng
    version) rồi so lại hai endpoint.
    """
    c, repos, _specs, worker, _broker, _mt = wired
    tid, _tr_id = _seed(repos)
    # Luồng worker nền dừng trước khi sửa transcript: job `translate` `queued` của
    # `_seed` không được bốc trong lúc bài này đang đo cờ `stale`.
    worker.stop()

    repos.update_transcript_segments(
        tid, [Segment(i=1, start=0.0, end=1.0, text="你好呀")])

    from_list = c.get(f"/api/translations?transcript_id={tid}").json()[0]
    from_detail = c.get(f"/api/transcripts/{tid}").json()["translations"][0]

    assert from_list["stale"] is True
    assert from_list == from_detail
