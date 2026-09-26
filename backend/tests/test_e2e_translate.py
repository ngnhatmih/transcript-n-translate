"""Task 17 · Nghiệm thu ĐẦU-CUỐI Workspace 2, trên bộ ráp THẬT của production.

Đây là bài DUY NHẤT trong phase chạy trọn chuỗi §8.6 `draft -> reviewed ->
translated` qua `main.build_components()` + `main.build_app()` rồi tới tận tệp
phụ đề xuất ra. Nói chính xác: các bài khác **có** dùng bộ ráp thật
(`test_mt_wiring.py`, `test_e2e_fake.py`), nhưng không bài nào đi hết chuỗi
trạng thái đó:

* `test_api_*` dựng app bằng `create_app()` với repos tự tay — chúng kiểm HỢP
  ĐỒNG HTTP, không kiểm bộ ráp.
* `test_e2e_fake.py` (Task 19 của 1a) chạy trọn đường ống nhưng theo nhánh
  `auto_forward`: nó KHÔNG chạm `POST /api/translations`, và không khẳng định
  mốc `translated` của transcript.
* `test_mt_wiring.py` khẳng định dây nối `mt_engines`/governor nhưng cũng đi
  nhánh tự động, không đi qua route tạo bản dịch, và không khẳng định mốc
  `translated`.

## Vì sao fixture CHÉP từ `tests/test_api_sources.py` chứ không tự nghĩ ra

Bẫy M7 của Giai đoạn 1a (và đã lặp lại một lần ở Task 14 của plan này): đặt
`PHUDE_DATA`/`PHUDE_DB` bằng `monkeypatch.setenv` là **sai**, vì `config.py` đọc
biến môi trường **lúc import**. Test import `from app import main` ở đầu tệp, nên
`monkeypatch.setenv` chạy SAU đó và **không** chuyển hướng đường dẫn — bộ test sẽ
mở **DB thật của repo**. Đường đúng là vá THẲNG các hằng số module, và phải vá CẢ
`app.config`: `ensure_dirs()` closure trên biến toàn cục của chính `app.config`,
nên vá mỗi tên đã import vào `main` là không đủ.

`_assert_repo_data_dirs_untouched` dưới đây biến lời hứa đó thành thứ chạy được:
bỏ các dòng vá `config` là bài này đỏ.

## Engine giả: cắm vào ĐÚNG chỗ `main.py` dựng adapter

Registry dùng là `registry.json` **THẬT** — đây là nghiệm thu, và `default_mt`
thật (`opus-mt`) là một phần của thứ đang được nghiệm thu. Chỉ adapter nặng bị
thay: `main.OpusMtEngine` bị vá thành `tests/fakes_mt.FakeMtEngine` ngay chỗ
`_build_mt_engines` gọi nó, nên logic ráp dây (khoá dict theo `spec.id`, vòng
`governor.register`, `TranslateHandler(repos, mt_engines)`) vẫn là của
production. `ollama_available` bị ghim thành `set()` — "chưa pull model nào" —
nên các engine Ollama không sẵn sàng và không có lượt HTTP nào chạy.

Engine giả phải hỏng **theo cách thật** nếu một khoá payload biến mất: đó chính
là mutation M1 ở Step 3 của brief.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from app.domain.models import Segment
from tests.fakes_mt import FakeMtEngine

#: Engine dịch mặc định ĐÃ SHIP của `registry.json`. Bài này KHÔNG hard-code nó
#: trong fixture: giá trị được đọc từ registry thật ở dưới, và chỉ dùng làm khoá
#: để tra `mt_engines`. Đổi `default_mt` sang một engine in-process khác là việc
#: của `tests/test_registry.py`, không được làm bài nghiệm thu này đỏ oan.
DEFAULT_MT = "opus-mt"

#: Nguồn và bản dịch của hai segment. Độ dài được chọn để QA KHÔNG gắn cờ nào
#: (xem `_assert_qa_is_clean`): tỉ lệ độ dài 17/4 = 4,25 và 7/2 = 3,50 đều nằm
#: trong `[0.25, 5.0]`, còn CPS 17/3 ≈ 5,7 và 7/1 = 7,0 đều dưới 21,0.
SRC_1, SRC_2 = "你好世界", "成本"
OUT_1, OUT_2 = "Xin chào thế giới", "chi phí"

TERM_SRC, TERM_OUT = "成本", "chi phí"


# --------------------------------------------------------------------------
# Fixture: chép từ `tests/test_api_sources.py::built`, bổ sung `TestClient`
# --------------------------------------------------------------------------

def _repo_data_dirs() -> list[pathlib.Path]:
    """Bốn thư mục mà `ensure_dirs()` tạo cho cấu hình THẬT của repo.

    Đường dẫn suy từ `config.__file__`, KHÔNG từ `config.DATA_DIR`: chính
    `DATA_DIR` là thứ bị fixture vá, nên hỏi nó là hỏi kẻ vừa bị đổi.
    """
    from app import config

    root = pathlib.Path(config.__file__).resolve().parents[2] / "data"
    return [root, root / "media", root / "logs", root / "output"]


def _snapshot_repo_data_dirs() -> dict[pathlib.Path, bool]:
    """Trạng thái `data/` THẬT của repo, đo TRƯỚC khi gọi `build_components()`."""
    return {d: d.exists() for d in _repo_data_dirs()}


def _assert_repo_data_dirs_untouched(before: dict[pathlib.Path, bool]) -> None:
    """M7/RU-04 · bộ test KHÔNG được tạo `data/` thật.

    `ensure_dirs()` closure trên biến module của `app.config`, nên vá mỗi tên đã
    import vào `main` là KHÔNG đủ: `main.build_components()` vẫn tạo
    `data/{media,logs,output}` của repo.
    """
    created = [str(d) for d, existed in before.items() if not existed and d.exists()]
    assert not created, (
        "build_components() đã tạo thư mục THẬT trong repo: " + ", ".join(created)
        + ". Phải vá `app.config` (nơi `ensure_dirs()` đọc biến), không chỉ vá "
          "tên đã import vào `main` (M7/RU-04)."
    )


def _wired(tmp_path, monkeypatch, *, fail_times: int = 0):
    """Thân dùng chung của hai fixture ráp dây: `wired` (engine lành) và `wired_hong`.

    Fixture này cố ý KHÔNG dựng lại `PhaseQueueWorker`/`create_app`: chép lại
    assembly thì nó trôi khỏi `main.py` mà không test nào bắt (bài học Task 19
    của Giai đoạn 1a).

    Trả về `TestClient` chứ không phải app trần để hai thứ đi cùng nhau trong
    MỘT đối tượng: `repos` đọc thẳng qua cổng còn request đi qua `build_app()`,
    nên bài dưới vừa khẳng định được hợp đồng HTTP vừa đọc được trạng thái THẬT
    trong DB.

    `fail_times > 0` chỉ đổi ENGINE GIẢ (nó ném `RuntimeError` ngay lần
    `translate` ĐẦU TIÊN); route, worker, broker và registry vẫn là của
    production, nên bài "bản dịch hỏng" đi đúng đường ống thật (I-2).
    """
    from app import config, main
    from app.adapters.registry_file import load_registry

    #: I-1 · Đối số chạy vào adapter THẬT. `model_ref` được đọc từ
    #: `registry.json` THẬT qua `load_registry()` — KHÔNG hard-code chuỗi — nên
    #: registry đổi model_ref thì phép ghim này đi theo. Còn `main.py` truyền
    #: `spec.id` (`"opus-mt"`) là đỏ NGAY, vì production sẽ chết ở
    #: `MarianTokenizer.from_pretrained("opus-mt")` ở lần dịch thật đầu tiên
    #: (review Task 17, I-1/M5).
    registry_mt_ref = {s.id: s.model_ref for s in load_registry()}[DEFAULT_MT]

    repo_data_before = _snapshot_repo_data_dirs()
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(config, "LOG_DIR", data / "logs")
    monkeypatch.setattr(config, "OUTPUT_DIR", data / "output")

    monkeypatch.setattr(main, "DB_PATH", data / "app.db")
    monkeypatch.setattr(main, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(main, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "LOG_DIR", data / "logs")

    #: Registry là bản THẬT đã ship: `default_mt` = `opus-mt` (in-process) nên
    #: không phụ thuộc Ollama, và mọi bất biến của registry thật đều được chạy.
    #: Chỉ adapter nặng bị thay, ngay chỗ `_build_mt_engines` gọi nó.
    def fake_opus_factory(model_ref, **kwargs):
        """Giữ ĐÚNG chữ ký mà `_build_mt_engines` gọi: `OpusMtEngine(spec.model_ref)`.

        Chỗ nối này đã đỏ THẬT hai lần khác nhau khi viết bài, và cả hai đều là
        lý do nó được ghim ở cuối tệp:

        1. Chuyển tiếp `*args` (`FakeMtEngine(*args, **kwargs)`) ⇒ `TypeError:
           takes 1 positional argument but 2 positional arguments (and 1
           keyword-only argument) were given`, vì `FakeMtEngine` chỉ nhận
           tham số keyword.
        2. Chuyển `model_ref` thành keyword (`FakeMtEngine(model_ref=...)`) ⇒
           `TypeError: got an unexpected keyword argument 'model_ref'`, vì bản
           giả **không có** tham số đó — nó nhận thẳng `mapping`.

        Nên `model_ref` là thứ bản giả NUỐT và bỏ qua, đúng vai "adapter thay
        thế": nó chỉ cần chịu được cách gọi của production.

        Nuốt KHÔNG có nghĩa là không kiểm. Đối số nhận được vẫn phải là
        `model_ref` của registry (khẳng định ngay sau `build_components()`),
        vì một phép `assert model_ref` kiểu truthiness nuốt luôn cả `spec.id` —
        đúng lỗ I-1 mà review Task 17 tìm ra.
        """
        kwargs.setdefault("mapping", {SRC_1: OUT_1, SRC_2: OUT_2})
        engine = FakeMtEngine(fail_times=fail_times, **kwargs)
        #: Ghi lại ĐỐI SỐ mà production vừa truyền, để phép ghim dưới đây đọc
        #: được nó từ ĐÚNG engine mặc định mà `_build_mt_engines` đã dựng.
        engine.model_ref_seen = model_ref
        return engine

    monkeypatch.setattr(main, "OpusMtEngine", fake_opus_factory)
    #: "Ollama chết / chưa pull model nào" ⇒ không engine Ollama nào sẵn sàng,
    #: nên không lượt HTTP nào chạy và suite không phụ thuộc máy đang chạy gì.
    monkeypatch.setattr(main, "ollama_available", lambda *a, **k: set())
    #: Engine ASR thật nạp model ~1,6 GB; bài này không đi qua đường ASR.
    monkeypatch.setattr(main, "_engine_factory", lambda spec: _NeverUsedAsr(),
                        raising=False)

    repos, specs, worker, broker, mt_engines = main.build_components()
    _assert_repo_data_dirs_untouched(repo_data_before)

    #: Nghiệm thu chính cái bẫy M7: nếu fixture trôi về DB thật của repo thì
    #: khẳng định này là thứ duy nhất nói ra, vì `TestClient` vẫn xanh.
    assert pathlib.Path(main.DB_PATH) == data / "app.db", (
        f"DB phải nằm trong tmp_path, không phải DB thật của repo: {main.DB_PATH}"
    )
    assert DEFAULT_MT in mt_engines, (
        f"registry thật phải dựng được engine mặc định {DEFAULT_MT!r} ở chế độ "
        f"in-process; mt_engines = {sorted(mt_engines)}"
    )

    #: I-1 · Đối số chạy vào adapter THẬT phải là `model_ref` của registry,
    #: KHÔNG phải `spec.id`. `_build_mt_engines` gọi
    #: `OpusMtEngine(spec.model_ref)` BẰNG VỊ TRÍ, nên một phép `assert
    #: model_ref` (truthiness) không gác được gì: truyền `spec.id` cũng lọt.
    seen_ref = getattr(mt_engines[DEFAULT_MT], "model_ref_seen", None)
    assert seen_ref == registry_mt_ref, (
        f"`main.py` phải truyền `model_ref` của registry cho engine mặc định "
        f"{DEFAULT_MT!r}: đã nhận {seen_ref!r}, phải là {registry_mt_ref!r}"
    )

    app = main.build_app(repos, specs, worker, broker, mt_engines)
    with TestClient(app) as c:
        c.repos = repos          # type: ignore[attr-defined]
        c.worker = worker        # type: ignore[attr-defined]
        c.mt_engines = mt_engines  # type: ignore[attr-defined]
        yield c, repos, worker, mt_engines


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """`(TestClient, repos, worker, mt_engines)` — ráp bằng ĐÚNG hàm của `main.py`.

    Engine giả LÀNH: dùng cho đường thành công (bài F) và cho vế đối chứng
    "worker CHƯA chạy" (bài C). Vế "worker chạy và HỎNG" có fixture riêng dưới.
    """
    yield from _wired(tmp_path, monkeypatch)


@pytest.fixture()
def wired_hong(tmp_path, monkeypatch):
    """Như `wired`, nhưng engine giả hỏng ngay lần `translate` ĐẦU TIÊN (I-2).

    Chỉ engine đổi; mọi thứ khác vẫn là bộ ráp của production, nên đây là đường
    "worker CHẠY và HỎNG" thật — thứ mà bài C (worker chưa chạy) không phủ.
    """
    yield from _wired(tmp_path, monkeypatch, fail_times=1)


class _NeverUsedAsr:
    """ASR không nằm trên đường của bài này; nổ to nếu ai đó chạm tới nó."""

    def transcribe(self, audio_path: str, lang: str):
        raise AssertionError("bài nghiệm thu Workspace 2 không được chạm engine ASR")

    def release(self) -> None:
        return None


# --------------------------------------------------------------------------
# Helpers đi qua ĐƯỜNG THẬT, không gán thẳng trường của đối tượng
# --------------------------------------------------------------------------

def _transcript(repos) -> int:
    """Một transcript `draft` hai segment, gắn vào một source thật.

    `Segment` dựng bằng chính constructor của nó ở đây là hợp lệ: đây là dữ liệu
    NGUỒN của bài (thứ mà engine ASR thật sẽ sinh ra), không phải bản dịch. Chỗ
    bắt buộc dùng `dataclasses.replace` là khi SỬA một segment đã có — xem
    `routes_translations.patch_translation`.
    """
    sid = repos.add_source(kind="file", origin="bai-giang.mp4",
                           media_path="/m/bai-giang.mp4", lang="zh")
    return repos.add_transcript(
        source_id=sid, engine="fw-large-v3-turbo", lang="zh",
        segments=[Segment(i=1, start=0.0, end=3.0, text=SRC_1),
                  Segment(i=2, start=3.0, end=4.0, text=SRC_2)])


def _drain(worker, job_id: int) -> None:
    """Chạy worker THẬT cho tới khi job `job_id` rời khỏi hàng đợi.

    Bám vào trạng thái của ĐÚNG job đang được nghiệm thu thay vì đếm số vòng
    `tick()`: một job dịch chạy xong trong một vòng, còn `while worker.tick()`
    cũng nuốt luôn mọi job khác và làm phép đỏ trỏ sai chỗ khi có job lạ.
    """
    for _ in range(50):
        if worker.repos.get_job(job_id).state in ("done", "failed", "cancelled"):
            return
        worker.tick()
    raise AssertionError(
        f"job {job_id} không kết thúc sau 50 vòng tick: "
        f"{worker.repos.get_job(job_id).state!r}"
    )


def _assert_qa_is_clean(translation) -> None:
    """QA tất định phải SẠCH trên dữ liệu này — nếu không thì phép đỏ ở đây mới
    là thứ nói ra rằng con số trong README không tái tạo được."""
    assert translation.qa_issues == [], (
        f"QA gắn cờ trên dữ liệu đã chọn để sạch: {translation.qa_issues}"
    )


# --------------------------------------------------------------------------
# Nghiệm thu: trọn chuỗi draft -> reviewed -> translated, rồi tới tệp phụ đề
# --------------------------------------------------------------------------

def test_full_workspace_2_flow_from_draft_to_exported_srt(wired):
    """Bốn mốc của §8.6 + route tạo bản dịch + worker thật + export ra SRT.

    Đi qua `POST /api/glossary` cho thuật ngữ, `POST /api/translations` cho bản
    dịch, và `GET /api/export/{id}` cho tệp — tức mọi cửa vào của Workspace 2 mà
    người dùng thật có.
    """
    c, repos, worker, mt_engines = wired
    tid = _transcript(repos)

    # --- Mốc 1: `draft` do chính `add_transcript` đặt (không phải test bịa ra).
    assert repos.get_transcript(tid).status == "draft"

    # --- Mốc 2: `approve` đặt `reviewed`, KHÔNG phải `translated`.

    approved = c.post(f"/api/transcripts/{tid}/approve")
    assert approved.status_code == 200, approved.text
    assert repos.get_transcript(tid).status == "reviewed", (
        "ruling review Task 15: `approve` ghi `reviewed`, vì `translated` ngay "
        "lúc duyệt một transcript CHƯA có bản dịch nào là sai khi ghi"
    )
    assert repos.get_transcript(tid).version == 1, "duyệt KHÔNG được tăng version"

    # Thuật ngữ đi qua route THẬT; `approved=True` để nó vào prompt và vào QA.
    term = c.post("/api/glossary", json={"lang": "zh", "term": TERM_SRC,
                                         "translation": TERM_OUT, "approved": True})
    assert term.status_code == 201, term.text
    glossary_version = repos.glossary_version()
    assert glossary_version >= 1, "ghi thuật ngữ phải tăng `glossary_version`"

    # --- Tạo bản dịch qua route: hàng `translations` + ĐÚNG MỘT job `translate`.
    created = c.post("/api/translations",
                     json={"transcript_id": tid, "engine": DEFAULT_MT})
    assert created.status_code == 201, created.text
    body = created.json()
    tr_id = body["translation"]["id"]
    job_id = body["job"]["id"]
    assert body["translation"]["status"] == "queued"
    assert repos.get_transcript(tid).status == "reviewed", (
        "tạo bản dịch chưa xong thì transcript PHẢI còn ở `reviewed`"
    )

    # Payload là hợp đồng giữa route và handler: thiếu một khoá là job chết
    # bằng `KeyError` ở TẬN worker, sau khi hàng đã được ghi (bài học I-3).
    payload = repos.get_job(job_id).payload
    assert set(payload) == {"translation_id", "transcript_id", "engine_id",
                            "source_lang", "target_lang"}, payload
    assert payload["translation_id"] == tr_id
    assert payload["engine_id"] == DEFAULT_MT
    assert payload["source_lang"] == "zh" and payload["target_lang"] == "vi"

    # --- Worker THẬT của composition root chạy job.
    _drain(worker, job_id)
    job = repos.get_job(job_id)
    assert job.state == "done", f"{job.state}: {job.error}"

    # --- Mốc 3: `translated` do ĐƯỜNG HOÀN THÀNH DỊCH đặt, không phải `approve`.
    assert repos.get_transcript(tid).status == "translated", (
        "§8.6: `translated` chỉ được ghi khi bản dịch xong (TranslateHandler), "
        "và đây là chỗ duy nhất biết chắc điều đó"
    )

    translation = repos.get_translation(tr_id)
    assert translation.status == "done"
    assert translation.transcript_version == 1
    assert [s.i for s in translation.segments] == [1, 2], translation.segments
    assert [s.text for s in translation.segments] == [OUT_1, OUT_2]
    assert translation.glossary_version == glossary_version, (
        "dấu vết glossary của bản dịch phải là version ĐỌC LÚC CHẠY, không phải "
        "ảnh chụp trong payload"
    )
    _assert_qa_is_clean(translation)

    # Engine giả nhận ĐÚNG danh sách đã duyệt: dây `approved(list_terms(lang))`
    # trong `TranslateHandler` là thứ duy nhất đưa thuật ngữ tới engine.
    engine = mt_engines[DEFAULT_MT]
    assert engine.calls == [[1, 2]], engine.calls
    assert engine.last_glossary is not None
    assert [(t.term, t.translation) for t in engine.last_glossary] == [
        (TERM_SRC, TERM_OUT)], engine.last_glossary

    # --- Mốc 4: tệp phụ đề xuất ra từ CHÍNH bản dịch đó.
    exported = c.get(f"/api/export/{tr_id}", params={"format": "srt"})
    assert exported.status_code == 200, exported.text
    assert OUT_1 in exported.text and OUT_2 in exported.text, exported.text
    assert "--> " in exported.text, exported.text

    # Trạng thái không bị đường export làm hỏng.
    assert repos.get_translation(tr_id).status == "done"
    assert repos.get_transcript(tid).status == "translated"


def test_a_translation_that_never_ran_leaves_the_transcript_reviewed(wired):
    """VẾ ĐỐI CHỨNG của mốc `translated`: nó phải do LẦN DỊCH XONG sinh ra.

    Không có bài này thì một `approve` ghi luôn `translated` (hoặc một
    `create_translation` ghi `translated` cho hàng vừa xếp) vẫn xanh bài trên —
    vì ở đó cả hai mốc đều đã đi qua. Ở đây bản dịch được tạo nhưng worker
    KHÔNG được chạy, nên transcript phải còn nguyên `reviewed`.
    """
    c, repos, _worker, _mt_engines = wired
    tid = _transcript(repos)
    assert c.post(f"/api/transcripts/{tid}/approve").status_code == 200

    created = c.post("/api/translations",
                     json={"transcript_id": tid, "engine": DEFAULT_MT})
    assert created.status_code == 201, created.text

    assert repos.get_translation(created.json()["translation"]["id"]).status == "queued"
    assert repos.get_transcript(tid).status == "reviewed", (
        "job chưa chạy thì chưa có bản dịch nào để gọi transcript là `translated`"
    )


def test_a_failed_translation_leaves_the_transcript_reviewed(wired_hong):
    """I-2 · VẾ "và **KHÔNG** khi thất bại" của correction box B, qua đường ống THẬT.

    Bài F chỉ đi đường thành công; bài C chỉ chứng minh "worker CHƯA chạy" —
    không bài nào chứng minh "worker CHẠY và HỎNG". Mutation M4 của review Task 17
    (ghi `translated` trong nhánh `except Exception` của `translate.py`) giữ tệp
    này xanh trước khi có bài này, trong khi mốc `translated` lúc đó là lời nói
    dối trên chính bản dịch hỏng.

    Không gán thẳng trường nào của `translation`/`transcript`: cả hai trạng thái
    đều đến từ route thật → job thật → worker thật → `TranslateHandler` thật.
    """
    c, repos, worker, _mt_engines = wired_hong
    tid = _transcript(repos)
    assert c.post(f"/api/transcripts/{tid}/approve").status_code == 200

    created = c.post("/api/translations",
                     json={"transcript_id": tid, "engine": DEFAULT_MT})
    assert created.status_code == 201, created.text
    tr_id = created.json()["translation"]["id"]
    job_id = created.json()["job"]["id"]

    _drain(worker, job_id)
    job = repos.get_job(job_id)
    assert job.state == "failed", f"{job.state}: {job.error}"
    assert repos.get_translation(tr_id).status == "failed", (
        "engine ném lỗi thì hàng dịch phải để lại `failed`, không treo ở `queued`"
    )
    assert repos.get_transcript(tid).status == "reviewed", (
        "bản dịch HỎNG thì transcript phải còn `reviewed`: ghi `translated` ở "
        "nhánh `except Exception` là nói dối trên chính bản dịch hỏng đó (M4)"
    )


# --------------------------------------------------------------------------
# Chữ ký của bản giả: ghim cái đã đỏ THẬT ở lần chạy đầu
# --------------------------------------------------------------------------

def test_the_fake_mirrors_the_real_adapter_signature():
    """`OpusMtEngine` nhận `model_ref` VỊ TRÍ; `FakeMtEngine` không nhận nó.

    Đây không phải chi tiết hình thức. Khi viết bài nghiệm thu ở trên, chỗ nối
    này đã đỏ THẬT hai lần, theo hai cách ngược nhau:

    * chuyển tiếp `*args` ⇒ `TypeError: takes 1 positional argument but 2
      positional arguments (and 1 keyword-only argument) were given`;
    * đổi `model_ref` thành keyword ⇒ `TypeError: got an unexpected keyword
      argument 'model_ref'`.

    Cách sửa đúng là NUỐT `model_ref` và dựng bản giả bằng `mapping`. Một phép
    đổi chữ ký như vậy không tự bảo vệ mình, nên nó được ghim ở đây trên CẢ HAI
    đầu: adapter THẬT phải dựng được bằng một tham số vị trí (hợp đồng mà
    `_build_mt_engines` dựa vào), và bản giả phải dựng được bằng đúng cách gọi
    đó — bản giả chỉ chịu được cách gọi của production, không nhận `model_ref`.
    """
    import inspect

    from app.adapters.mt.opus_mt import OpusMtEngine

    spec_ref = "Helsinki-NLP/opus-mt-zh-vi"
    # Hợp đồng mà `_build_mt_engines` dựa vào, ghim bằng CHỮ KÝ: tham số ĐẦU
    # TIÊN của adapter thật nhận được VỊ TRÍ. Cố ý KHÔNG ghim TÊN tham số — nó
    # là `model_name`, không phải `model_ref`, và lần chạy thứ ba của bài này đã
    # đỏ vì tôi đoán tên đó. Tên là chuyện của adapter; thứ `main.py` dựa vào là
    # truyền được `spec.model_ref` bằng vị trí.
    first = list(inspect.signature(OpusMtEngine.__init__).parameters.values())[1]
    assert first.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, first

    # Bản THẬT dựng được bằng một tham số vị trí. Không nạp weight nào ở đây —
    # `OpusMtEngine.__init__` chỉ giữ tham chiếu, tới `translate()` mới nạp.
    real = OpusMtEngine(spec_ref)
    assert real.engine_id == DEFAULT_MT, real.engine_id

    # Bản giả dựng được bằng ĐÚNG cách gọi đó, và `model_ref` bị nuốt.
    def fake_factory(model_ref, **kwargs):
        assert model_ref
        kwargs.setdefault("mapping", {SRC_1: OUT_1, SRC_2: OUT_2})
        return FakeMtEngine(**kwargs)

    fake = fake_factory(spec_ref)
    assert isinstance(fake, FakeMtEngine)
    assert fake.engine_id != DEFAULT_MT, (
        "bản giả cố ý có `engine_id` khác `spec.id`: nếu chúng bằng nhau thì "
        "không còn chứng minh được rằng `main.py` đánh khoá `mt_engines` theo "
        "`spec.id` chứ không theo thuộc tính của engine"
    )
    # Và nó thật sự là thứ đã dịch: ghim rằng `mapping` đã tới được engine.
    assert [s.text for s in fake.translate(
        [Segment(i=1, start=0.0, end=3.0, text=SRC_1)], [], None)] == [OUT_1]
