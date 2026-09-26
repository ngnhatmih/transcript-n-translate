"""API glossary: CRUD, version, và hệ quả — glossary đổi thì bản dịch nào phải xem lại.

Năm quyết định của tệp này, cả năm đều là hệ quả của một mục hiệu chỉnh hoặc một
lỗi đã trả giá trong chính giai đoạn này:

* **Mọi hành vi đi qua ĐƯỜNG THẬT** — `main.build_components()` +
  `main.build_app()` + `TestClient` — và `build_components()` trả nguyên TUPLE 5
  phần tử của nó, không bọc lại thành một đối tượng có `.repos`. Không có
  `.repos` nào trong sản phẩm: một bản bọc như vậy là assembly thứ hai để trôi
  (xem `tests/test_api_translations.py`, cùng khuôn).
* **Fixture KHÔNG dùng `monkeypatch.setenv("PHUDE_DATA", …)`.** `app/config.py`
  đọc biến môi trường ở THỜI ĐIỂM IMPORT (`config.py:19-23`), nên đặt biến sau
  khi `app.main` (và `app.config` theo nó) đã được import là no-op: `DB_PATH`
  vẫn là `backend/data/app.db` THẬT của repo, và `SqliteRepos(DB_PATH)` mở đúng
  tệp đó. Fixture ở đây chuyển đường dẫn bằng cách vá CHÍNH các hằng số của
  `app.config`, y như `tests/test_api_translations.py` — và
  `_assert_repo_data_dirs_untouched` biến lời hứa "không tạo `data/` thật" thành
  thứ chạy được.
* **`Segment(...)` chỉ được dựng cho fixture MỚI.** Không có chỗ nào trong tệp
  này sửa `text` của một segment đã có: engine giả dùng `dataclasses.replace`,
  vì dựng tay nuốt 7/13 trường (lỗi đã ship hai lần trong giai đoạn này).
* **`affected` là thứ được kiểm, không phải số job.** Một route sinh job cho
  MỌI transcript thì trông vẫn "có job" mà đã mất hẳn giá trị của tab Thuật ngữ
  — nên mỗi bài ở đây ghim danh sách id, và bài phủ định
  (`test_a_term_not_present_anywhere_affects_nothing`) ghim cả hai vế.
* **Sửa một thuật ngữ CHƯA duyệt là vô hại; duyệt lên và bỏ duyệt đều CÓ hại.**
  Đó là rule T4/F2 đã chốt ở `domain/glossary_match.py` (cả hai vế đi qua
  `approved()`), không phải hành vi bất đối xứng cần "sửa": bản nháp không đi
  vào prompt nên không ràng buộc bản dịch nào, còn duyệt/bỏ duyệt thì đổi ràng
  buộc.
"""
from __future__ import annotations

import dataclasses
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.domain.models import Segment

#: Engine `inprocess`, luôn sẵn sàng (`_mark_availability` trả `True` cho mọi
#: engine không `runtime == "ollama"`). Đây là engine mặc định đã ship.
INPROCESS_ENGINE_ID = "opus-mt"

#: Đúng năm khoá `TranslateHandler.run` đọc (`pipeline/translate.py:71-80`).
HANDLER_PAYLOAD_KEYS = {"translation_id", "transcript_id", "engine_id",
                        "source_lang", "target_lang"}


# ---------------------------------------------------------------------------
# Fixture: composition root THẬT, chỉ đường dẫn đĩa bị chuyển vào tmp_path
# ---------------------------------------------------------------------------

def _repo_data_dirs() -> list[pathlib.Path]:
    """Bốn thư mục mà `ensure_dirs()` tạo cho cấu hình THẬT của repo.

    Suy từ `config.__file__`, KHÔNG từ `config.DATA_DIR`: chính `DATA_DIR` là
    thứ fixture vá, nên hỏi nó là hỏi kẻ vừa bị đổi.
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
    )


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """`(client, repos, worker, mt_engines)` của `build_components()` THẬT.

    Trả đúng những phần tử mà bài cần, lấy từ TUPLE NGUYÊN của
    `build_components()` — không dựng lại `PhaseQueueWorker`/`TranslateHandler`
    và không bọc tuple thành đối tượng có `.repos` (thuộc tính đó không tồn tại
    trong sản phẩm).
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
    # Phép dò Ollama bị ghim `set()` ⇒ `available=False` một cách TẤT ĐỊNH, nên
    # bài này không cá cược vào việc máy đang chạy đã pull model nào.
    monkeypatch.setattr(main, "ollama_available", lambda *a, **k: set())

    repos, specs, worker, broker, mt_engines = main.build_components()
    _assert_repo_data_dirs_untouched(before)
    app = main.build_app(repos, specs, worker, broker, mt_engines)
    with TestClient(app) as client:
        yield client, repos, worker, mt_engines


_ZH = {"lang": "zh", "term": "龙", "translation": "rồng", "approved": True}


def _seed_transcript(repos, *, text: str = "龙", lang: str = "zh") -> int:
    """Một source + transcript MỘT segment, trả `transcript_id`."""
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    return repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang=lang,
                                segments=[Segment(i=1, start=0.0, end=1.0, text=text)])


def _seed_done_translation(repos, transcript_id: int, *,
                           engine: str = INPROCESS_ENGINE_ID,
                           target_lang: str = "vi") -> int:
    """Một hàng `translations` đã `done` với 0 segment (job chưa chạy)."""
    return repos.add_translation(
        transcript_id=transcript_id, transcript_version=1, engine=engine,
        target_lang=target_lang, segments=[], prompt_version="raw-p1",
        status="done")


def _queued_jobs(repos) -> list:
    return repos.list_jobs(states=("queued",))


class _FakeMtEngine:
    """Engine dịch GIẢ cắm vào ĐÚNG dict `mt_engines` của composition root.

    Chỉ đổi `text` qua `dataclasses.replace` — KHÔNG dựng `Segment(...)` bằng tay
    (13 trường; dựng tay là cách hai task trong giai đoạn này nuốt 7 trường).
    """

    def __init__(self, model_ref: str) -> None:
        self.model_ref = model_ref
        self.batches: list[list[int]] = []
        self.opts = None
        self.last_stats = None

    def supports_glossary(self) -> bool:
        return True

    def translate(self, batch, glossary, opts):
        self.batches.append([s.i for s in batch])
        self.opts = opts
        return [dataclasses.replace(s, text=f"[{opts.target_lang}] {s.text}")
                for s in batch]

    def release(self) -> None:
        return None


# ---------------------------------------------------------------------------
# GET / POST — đọc và ghi glossary
# ---------------------------------------------------------------------------

def test_get_is_an_empty_list_on_a_fresh_database(wired):
    c, _repos, _worker, _mt = wired
    r = c.get("/api/glossary")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_post_creates_a_term(wired):
    c, _repos, _worker, _mt = wired
    r = c.post("/api/glossary", json=_ZH)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["term"] == "龙"
    assert body["lang"] == "zh"
    assert body["translation"] == "rồng"
    assert body["approved"] is True
    assert body["note"] is None
    assert isinstance(body["id"], int)
    assert body["created_at"]
    # Không có transcript nào ⇒ không ảnh hưởng gì và không xếp job nào.
    assert body["affected"] == []
    assert _queued_jobs(_repos) == []


def test_get_filters_by_lang(wired):
    c, _repos, _worker, _mt = wired
    c.post("/api/glossary", json=_ZH)
    c.post("/api/glossary", json={"lang": "en", "term": "dragon",
                                  "translation": "rồng", "approved": True})
    assert [t["term"] for t in c.get("/api/glossary?lang=zh").json()] == ["龙"]
    assert len(c.get("/api/glossary").json()) == 2


def test_upsert_same_lang_and_term_does_not_duplicate(wired):
    c, _repos, _worker, _mt = wired
    c.post("/api/glossary", json={"lang": "zh", "term": "龙",
                                  "translation": "rồng", "approved": False})
    c.post("/api/glossary", json={"lang": "zh", "term": "龙",
                                  "translation": "long", "approved": True})
    rows = c.get("/api/glossary?lang=zh").json()
    assert len(rows) == 1 and rows[0]["translation"] == "long"
    assert rows[0]["approved"] is True


def test_post_persists_the_note(wired):
    c, _repos, _worker, _mt = wired
    body = c.post("/api/glossary", json=dict(_ZH, note="rồng là linh vật")).json()
    assert body["note"] == "rồng là linh vật"
    assert c.get("/api/glossary?lang=zh").json()[0]["note"] == "rồng là linh vật"


# ---------------------------------------------------------------------------
# PATCH /api/glossary/{id}
# ---------------------------------------------------------------------------

def test_patch_edits_translation_and_approval(wired):
    c, _repos, _worker, _mt = wired
    term_id = c.post("/api/glossary", json=dict(_ZH, approved=False)).json()["id"]
    r = c.patch(f"/api/glossary/{term_id}", json={"approved": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approved"] is True
    assert body["id"] == term_id
    assert body["translation"] == "rồng", "trường không gửi lên phải giữ nguyên"

    r = c.patch(f"/api/glossary/{term_id}", json={"translation": "long"})
    assert r.json()["translation"] == "long"
    assert r.json()["approved"] is True, "PATCH là sửa MỘT PHẦN"


def test_patch_unknown_term_is_404(wired):
    c, _repos, _worker, _mt = wired
    assert c.patch("/api/glossary/999", json={"approved": True}).status_code == 404


# ---------------------------------------------------------------------------
# glossary_version — getter đã có, KHÔNG có hàm bump riêng (mục hiệu chỉnh #1)
# ---------------------------------------------------------------------------

def test_changing_glossary_bumps_version_exactly_once(wired):
    """Ghim mục hiệu chỉnh #1 ở tầng API: MỘT lần ghi glossary ⇒ version +ĐÚNG 1.

    `upsert_term` đã tăng version trong cùng giao dịch
    (`sqlite_repos.py:538-541`), nên một lần bump thứ hai ở route — đúng dòng
    `repos.bump_glossary_version()` mà brief gợi ý — làm con số này thành
    `before + 2`: mọi bản dịch trông lệch thời so với glossary sớm hơn thực tế.
    Hàm bump đó KHÔNG tồn tại trên cổng và không được thêm.
    """
    c, repos, _worker, _mt = wired
    before = repos.glossary_version()
    c.post("/api/glossary", json=_ZH)
    assert repos.glossary_version() == before + 1
    assert c.get("/api/glossary/version").json()["glossary_version"] == before + 1
    assert not hasattr(repos, "bump_glossary_version")


def test_patch_bumps_version_exactly_once_too(wired):
    c, repos, _worker, _mt = wired
    term_id = c.post("/api/glossary", json=_ZH).json()["id"]
    before = repos.glossary_version()
    r = c.patch(f"/api/glossary/{term_id}", json={"translation": "long"})
    assert r.status_code == 200, r.text
    assert repos.glossary_version() == before + 1
    assert c.get("/api/glossary/version").json()["glossary_version"] == before + 1


# ---------------------------------------------------------------------------
# Hệ quả: glossary đổi ⇒ transcript/bản dịch nào phải dịch lại
# ---------------------------------------------------------------------------

def test_changing_glossary_enqueues_retranslate_for_affected_translation(wired):
    c, repos, _worker, _mt = wired
    tid = _seed_transcript(repos, text="龙")
    _seed_done_translation(repos, tid)
    # Transcript KHÁC không chứa thuật ngữ: nó không được lọt vào `affected`.
    other = _seed_transcript(repos, text="mèo")
    _seed_done_translation(repos, other)
    assert _queued_jobs(repos) == []

    r = c.post("/api/glossary", json=_ZH)
    assert r.status_code == 201, r.text
    assert r.json()["affected"] == [tid], (
        "chỉ transcript có segment chứa 龙 mới bị ảnh hưởng"
    )
    queued = _queued_jobs(repos)
    assert len(queued) == 1, f"chỉ bản dịch bị ảnh hưởng mới được xếp lại: {queued}"
    assert queued[0].type == "translate"
    assert queued[0].workspace == 2
    assert "glossary" in queued[0].payload["reason"]


def test_a_term_not_present_anywhere_affects_nothing(wired):
    c, repos, _worker, _mt = wired
    tid = _seed_transcript(repos, text="mèo")
    _seed_done_translation(repos, tid)
    r = c.post("/api/glossary", json=_ZH)
    assert r.json()["affected"] == []
    assert _queued_jobs(repos) == []


def test_an_unapproved_term_affects_nothing(wired):
    """Mục hiệu chỉnh #7: bản nháp KHÔNG đi vào prompt nên không ràng buộc gì.

    Đây là hành vi có chủ ý của `affected_segments` (cả hai vế qua `approved()`),
    có test ở Task 4 — đừng "sửa" để nó báo ảnh hưởng.
    """
    c, repos, _worker, _mt = wired
    tid = _seed_transcript(repos, text="龙")
    _seed_done_translation(repos, tid)
    r = c.post("/api/glossary", json=dict(_ZH, approved=False))
    assert r.json()["approved"] is False
    assert r.json()["affected"] == []
    assert _queued_jobs(repos) == []


def test_approving_a_term_affects_the_translations_that_use_it(wired):
    """Duyệt lên là THÊM một ràng buộc ⇒ bản dịch cũ sai ⇒ phải dịch lại."""
    c, repos, _worker, _mt = wired
    tid = _seed_transcript(repos, text="龙")
    _seed_done_translation(repos, tid)
    term_id = c.post("/api/glossary", json=dict(_ZH, approved=False)).json()["id"]
    assert _queued_jobs(repos) == [], "nháp thì chưa ràng buộc gì"

    r = c.patch(f"/api/glossary/{term_id}", json={"approved": True})
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == [tid]
    assert len(_queued_jobs(repos)) == 1


def test_unapproving_a_term_also_affects_the_translations_that_use_it(wired):
    """BỎ duyệt là GỠ một ràng buộc ⇒ bản dịch cũ cũng sai.

    Đây chính là ca mà việc LỌC TRƯỚC `approved()` ở route sẽ nuốt mất (mục hiệu
    chỉnh #3/#7): lọc `old`/`new` rồi mới gọi `affected_segments` thì hai vế bằng
    nhau và không ai biết bản dịch vừa mất ràng buộc.
    """
    c, repos, _worker, _mt = wired
    tid = _seed_transcript(repos, text="龙")
    _seed_done_translation(repos, tid)
    term_id = c.post("/api/glossary", json=_ZH).json()["id"]
    # Thuật ngữ vừa được duyệt lên đã xếp MỘT job; phép đỏ ở dưới phải đo PHẦN
    # TĂNG, không phải tổng số, nếu không nó chỉ đang đếm lại job cũ.
    before = {j.id for j in _queued_jobs(repos)}
    assert len(before) == 1

    r = c.patch(f"/api/glossary/{term_id}", json={"approved": False})
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == [tid]
    fresh = {j.id for j in _queued_jobs(repos)} - before
    assert len(fresh) == 1, f"bỏ duyệt phải xếp thêm đúng một job dịch lại: {fresh}"
    new_job = [j for j in _queued_jobs(repos) if j.id in fresh][0]
    assert new_job.payload["transcript_id"] == tid


def test_changing_an_existing_terms_translation_affects_translations_that_use_it(wired):
    """Giá trị CHÍNH của tab Thuật ngữ: đổi bản dịch của một thuật ngữ đang dùng.

    `old` phải là glossary TRƯỚC lần ghi (hàng vừa sửa bị loại khỏi vế "trước"),
    nếu không thì hai vế đều mang giá trị MỚI và phép so ánh xạ luôn rỗng — bản
    dịch đang dùng `rồng` sẽ không bao giờ được báo là phải xem lại khi thuật ngữ
    đổi thành `long`.
    """
    c, repos, _worker, _mt = wired
    term_id = c.post("/api/glossary", json=_ZH).json()["id"]
    # Transcript + bản dịch có SAU khi thuật ngữ đã tồn tại, nên phép đỏ ở dưới
    # không thể đến từ việc thuật ngữ vừa xuất hiện.
    tid = _seed_transcript(repos, text="龙")
    _seed_done_translation(repos, tid)
    assert _queued_jobs(repos) == []

    r = c.patch(f"/api/glossary/{term_id}", json={"translation": "long"})
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == [tid]
    assert len(_queued_jobs(repos)) == 1


def test_a_term_of_another_language_does_not_affect_this_language(wired):
    """Cùng một chữ ở hai ngôn ngữ là hai danh tính — `list_terms(lang=…)` phải lọc.

    Transcript `zh` chứa `龙`; một thuật ngữ `en` cũng tên `龙` không được làm nó
    phải dịch lại.
    """
    c, repos, _worker, _mt = wired
    tid = _seed_transcript(repos, text="龙", lang="zh")
    _seed_done_translation(repos, tid)
    r = c.post("/api/glossary", json={"lang": "en", "term": "龙",
                                      "translation": "dragon", "approved": True})
    assert r.json()["affected"] == []
    assert _queued_jobs(repos) == []


def test_a_transcript_without_any_translation_is_reported_but_enqueues_nothing(wired):
    """`affected` đếm TRANSCRIPT bị ảnh hưởng; job thì sinh cho BẢN DỊCH (spec §8.1).

    Transcript chưa có bản dịch nào vẫn phải xuất hiện trong `affected` — đó là
    câu trả lời cho "bản dịch nào phải xem lại" khi người dùng còn chưa dịch — mà
    không có gì để xếp job.
    """
    c, repos, _worker, _mt = wired
    tid = _seed_transcript(repos, text="龙")
    r = c.post("/api/glossary", json=_ZH)
    assert r.json()["affected"] == [tid]
    assert _queued_jobs(repos) == []


def test_the_retranslate_job_is_consumed_by_the_real_handler(wired):
    """Đường THẬT đầu-cuối: HTTP → job → worker thật → `TranslateHandler` thật.

    Chỉ adapter model là giả. Không có bài này thì một payload sai khoá vẫn xanh
    ở bài trên (nó chỉ so `reason`), còn ở đây worker phải THẬT SỰ dịch xong bằng
    chính payload mà route vừa sinh.
    """
    c, repos, worker, mt_engines = wired
    tid = _seed_transcript(repos, text="龙")
    tr_id = _seed_done_translation(repos, tid)

    engine = _FakeMtEngine("gia-lap")
    mt_engines[INPROCESS_ENGINE_ID] = engine

    body = c.post("/api/glossary", json=_ZH).json()
    assert body["affected"] == [tid]
    queued = _queued_jobs(repos)
    assert len(queued) == 1
    job = queued[0]
    # Năm khoá handler ĐỌC phải có mặt với đúng giá trị; thừa/thiếu một khoá là
    # job chết `KeyError` ở tận worker, sau khi hàng đã được ghi.
    assert HANDLER_PAYLOAD_KEYS <= set(job.payload), job.payload
    # Khoá `glossary_version` (spec §8.1) phải được ghim THEO TÊN: phép so
    # tập-con ở trên không đỏ khi khoá này biến mất, nên nó từng sống sót qua
    # đúng mutant "payload bỏ glossary_version". Giá trị là version đọc LÚC XẾP
    # JOB — ở đây chỉ có một lần ghi nên nó bằng version hiện tại của glossary.
    assert job.payload["glossary_version"] == repos.glossary_version() == 1
    assert job.payload["translation_id"] == tr_id
    assert job.payload["transcript_id"] == tid
    assert job.payload["engine_id"] == INPROCESS_ENGINE_ID
    assert job.payload["source_lang"] == "zh"
    assert job.payload["target_lang"] == "vi"
    assert job.phase == f"translate:{INPROCESS_ENGINE_ID}"

    while worker.tick():
        pass

    assert engine.batches == [[1]], (
        f"handler thật không nhận được segment nào: {engine.batches}"
    )
    assert (engine.opts.source_lang, engine.opts.target_lang) == ("zh", "vi")
    stored = repos.get_translation(tr_id)
    assert stored.status == "done", f"trạng thái sau khi chạy: {stored.status}"
    assert [s.text for s in stored.segments] == ["[vi] 龙"]
