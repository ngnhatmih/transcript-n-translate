"""Test của Task 15: app factory, route sources/registry/status, và IngestHandler.

Ngoài 9 test route của brief còn hai nhóm test CHE hai lỗ hổng đã biết:

* `IngestHandler` — điểm vào của cả pipeline. Nó chỉ xuất hiện trong `main.py`
  và trong định nghĩa của chính nó; Task 19 thay nó bằng stub trong E2E, nên
  nếu không có test ở đây thì lớp thật này KHÔNG được chạy ở đâu cả.
* `SingleGpuGovernor.register()` — không có người gọi nào trước Task 15, nên
  `before_phase`/`after_phase` là hàm rỗng và model ASR không bao giờ được đổ.
"""
from __future__ import annotations

import io
import pathlib
import sys
import types

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.domain import job_state as js
from app.domain.models import Job, Source
from app.registry import EngineSpec


@pytest.fixture()
def client(tmp_path):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    specs = [
        EngineSpec(id="fw-large-v3-turbo", label="FW turbo", kind="asr",
                   runtime="inprocess", model_ref="large-v3-turbo", vram_mb=1600,
                   langs=("zh", "en"),
                   capabilities={"timestamps": True, "word_timestamps": True}, opts={}),
        EngineSpec(id="qwen2.5-7b", label="Qwen 7B", kind="mt", runtime="ollama",
                   model_ref="qwen2.5:7b", vram_mb=5200, langs=("zh", "en"),
                   capabilities={"glossary_prompt": True}, opts={}),
    ]
    app = create_app(repos=repos, specs=specs, media_dir=tmp_path / "media",
                     out_dir=tmp_path / "out")
    with TestClient(app) as c:
        c.repos = repos          # type: ignore[attr-defined]
        c.tmp = tmp_path         # type: ignore[attr-defined]
        yield c


# --------------------------------------------------------------------------
# Route: registry + status
# --------------------------------------------------------------------------

def test_registry_endpoint_lists_both_kinds(client):
    body = client.get("/api/registry").json()
    assert [e["id"] for e in body["asr"]] == ["fw-large-v3-turbo"]
    assert [e["id"] for e in body["mt"]] == ["qwen2.5-7b"]
    assert body["mt"][0]["vram_mb"] == 5200


def test_status_endpoint_reports_phase_and_queue(client):
    body = client.get("/api/status").json()
    assert body["queue_depth"] == 0
    assert body["current_phase"] is None
    assert body["ollama"] in {"unknown", "up", "down"}


def test_status_counts_queued_jobs_and_ignores_finished_ones(client):
    """`queue_depth` phải là số job đang CHỜ, không phải số job đã tạo."""
    created = client.post(
        "/api/sources/upload",
        files={"file": ("a.mp4", io.BytesIO(b"x"), "video/mp4")},
        data={"lang": "zh"},
    ).json()
    assert client.get("/api/status").json()["queue_depth"] == 1

    client.repos.set_job_state(created["job"]["id"], js.RUNNING)
    assert client.get("/api/status").json()["queue_depth"] == 0
    assert client.get("/api/status").json()["running"] == [created["job"]["id"]]


def test_status_is_visible_on_the_configured_router(client):
    assert client.get("/api/registry").status_code == 200
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/sources").status_code == 200


# --------------------------------------------------------------------------
# Route: upload
# --------------------------------------------------------------------------

def test_upload_creates_source_and_ingest_job(client):
    payload = b"khong-phai-video-that-nhung-du-de-luu"
    resp = client.post(
        "/api/sources/upload",
        files={"file": ("bai-giang.mp4", io.BytesIO(payload), "video/mp4")},
        data={"lang": "zh"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"]["origin"] == "bai-giang.mp4"
    assert body["source"]["kind"] == "file"
    assert body["job"]["type"] == "ingest"
    assert body["job"]["workspace"] == 1

    stored = client.tmp / "media" / pathlib.Path(body["source"]["media_path"]).name
    assert stored.exists() and stored.read_bytes() == payload

    # Tệp phải nằm trên đĩa ĐÚNG chỗ mà `media_path` trỏ tới. Brief chỉ so tên
    # tệp; một `media_path` sai thư mục vẫn lọt qua phép so đó.
    assert pathlib.Path(body["source"]["media_path"]) == stored


def test_upload_rejects_unknown_lang(client):
    resp = client.post("/api/sources/upload",
                       files={"file": ("a.mp4", io.BytesIO(b"x"), "video/mp4")},
                       data={"lang": "klingon"})
    assert resp.status_code == 422


def test_upload_rejects_empty_file(client):
    resp = client.post("/api/sources/upload",
                       files={"file": ("a.mp4", io.BytesIO(b""), "video/mp4")},
                       data={"lang": "zh"})
    assert resp.status_code == 422


def test_upload_copies_every_byte_and_ignores_path_components(client):
    """Tệp lớn hơn một khối phải được ghi đủ, và tên tệp không được thoát ra ngoài.

    Hai điều không test nào khác chạm tới: vòng `while chunk := await file.read()`
    chỉ chạy hai lần khi tệp vượt `_CHUNK`, và tên tệp là dữ liệu do client gửi
    lên nên `../` phải bị cắt trước khi ghép vào thư mục media.
    """
    payload = b"A" * (1024 * 1024 + 17)
    resp = client.post(
        "/api/sources/upload",
        files={"file": ("../thoat-ra-ngoai.mp4", io.BytesIO(payload), "video/mp4")},
        data={"lang": "zh"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    media_dir = (client.tmp / "media").resolve()
    stored = pathlib.Path(body["source"]["media_path"]).resolve()
    assert stored.parent == media_dir, "tên tệp có thể thoát khỏi thư mục media"
    assert stored.read_bytes() == payload
    assert not (client.tmp / "thoat-ra-ngoai.mp4").exists()


def test_safe_name_strips_every_path_component():
    """I3: khoá TRỰC TIẾP phép cắt đường dẫn, không đi qua route.

    Test tích hợp ở trên (`test_upload_copies_every_byte_and_ignores_path_components`)
    KHÔNG bắt được việc bỏ `.name`: tệp thoát ra ngoài chỉ trong tích tắc rồi bị
    `target.replace(final)` kéo về trong `media_dir`, nên mọi khẳng định chạy sau
    request đều xanh (mutation M2 của vòng review: 32/32 vẫn xanh khi bỏ `.name`).
    Ở đây phép khẳng định nằm ngay trên hàm thuần nên bỏ `.name` là đỏ ngay.
    """
    from app.api.routes_sources import _safe_name

    assert _safe_name("../x.mp4") == "x.mp4"
    assert _safe_name("..\\..\\x.mp4") == "x.mp4"
    assert _safe_name("C:\\media\\x.mp4") == "x.mp4"
    assert _safe_name("a/b/x.mp4") == "x.mp4"
    assert _safe_name("x.mp4") == "x.mp4"


def test_safe_name_rejects_names_that_are_not_files():
    """M4: `pathlib.Path("..").name == ".."` nên `..` LỌT qua `.name`, và
    `media_dir / ".."` là thư mục CHA -> `open()` nổ 500. Client gửi rác thì
    phải nhận 4xx, không phải lỗi máy chủ."""
    from fastapi import HTTPException

    from app.api.routes_sources import _safe_name

    for bad in ("", ".", "..", "x/..", "..\\.."):
        with pytest.raises(HTTPException) as excinfo:
            _safe_name(bad)
        assert excinfo.value.status_code == 422, bad
        assert "tên tệp" in str(excinfo.value.detail), bad


@pytest.mark.parametrize("bad", ["..", "x/..", "..\\..", "."])
def test_upload_answers_422_for_a_filename_that_is_not_a_file(client, bad):
    """M4 qua đường thật: upload với tên `..` phải là 422 (đã xác nhận 500)."""
    resp = client.post(
        "/api/sources/upload",
        files={"file": (bad, io.BytesIO(b"x"), "video/mp4")},
        data={"lang": "zh"},
    )
    assert resp.status_code == 422, resp.text
    assert "tên tệp" in resp.text


def test_missing_lang_form_field_falls_back_to_zh(client):
    """`lang` là trường form tuỳ chọn; thiếu thì mặc định 'zh', không phải 422."""
    resp = client.post("/api/sources/upload",
                       files={"file": ("a.mp4", io.BytesIO(b"x"), "video/mp4")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"]["lang"] == "zh"
    assert body["job"]["type"] == "ingest"


# --------------------------------------------------------------------------
# Route: url
# --------------------------------------------------------------------------

def test_url_endpoint_creates_url_source(client, monkeypatch):
    def fake_download(url, out_dir, on_progress=None, runner=None):
        import pathlib
        p = pathlib.Path(out_dir) / "vid.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return p

    monkeypatch.setattr("app.api.routes_sources.ingest.download_url", fake_download)
    resp = client.post("/api/sources/url", json={"url": "https://example.com/v", "lang": "zh"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"]["kind"] == "url"
    assert body["source"]["origin"] == "https://example.com/v"
    assert body["job"]["type"] == "ingest"


def test_url_endpoint_rejects_non_http(client):
    resp = client.post("/api/sources/url", json={"url": "ftp://x/y", "lang": "zh"})
    assert resp.status_code == 422


def test_url_endpoint_reports_download_failure_as_422(client, monkeypatch):
    """yt-dlp hỏng (mất mạng, video bị chặn) là lỗi đầu vào của người dùng."""
    from app.pipeline import ingest

    def boom(url, out_dir, on_progress=None, runner=None):
        raise ingest.IngestError("không tải được video")

    monkeypatch.setattr("app.api.routes_sources.ingest.download_url", boom)
    resp = client.post("/api/sources/url",
                       json={"url": "https://example.com/v", "lang": "zh"})
    assert resp.status_code == 422, resp.text
    assert "không tải được video" in resp.text


# --------------------------------------------------------------------------
# Route: list / detail
# --------------------------------------------------------------------------

def test_list_sources_returns_newest_first(client):
    for n in range(3):
        client.post("/api/sources/upload",
                    files={"file": (f"v{n}.mp4", io.BytesIO(b"x"), "video/mp4")},
                    data={"lang": "zh"})
    body = client.get("/api/sources").json()
    assert [s["origin"] for s in body] == ["v2.mp4", "v1.mp4", "v0.mp4"]


def test_list_sources_is_empty_before_any_upload(client):
    assert client.get("/api/sources").json() == []


def test_list_sources_goes_through_the_port_not_the_database_file(tmp_path):
    """I2/R74: route chỉ nói chuyện qua `Repos`, không mở thẳng tệp SQLite.

    Repos giả ở đây CHỈ có `list_sources()` — cố ý không có `db_path` lẫn
    `_connect`, đúng như một hiện thực khác của cổng. Bản cũ
    (`getattr(repos, "db_path")` rồi `sqlite3.connect`) trả 500 cho stub này;
    đi qua cổng thì trả đúng dữ liệu.
    """
    class _PortOnlyRepos:
        def list_sources(self):
            return [Source(id=7, kind="file", origin="a.mp4", media_path="m/a.mp4",
                           lang="zh", audio_path=None, duration=None, created_at="")]

    app = create_app(repos=_PortOnlyRepos(), specs=[], media_dir=tmp_path / "media",
                     out_dir=tmp_path / "out")
    with TestClient(app) as c:
        resp = c.get("/api/sources")

    assert resp.status_code == 200, resp.text
    assert resp.json() == [{
        "id": 7, "kind": "file", "origin": "a.mp4", "media_path": "m/a.mp4",
        "audio_path": None, "duration": None, "lang": "zh", "created_at": "",
    }]


def test_get_source_by_id_and_404_for_unknown(client):
    created = client.post(
        "/api/sources/upload",
        files={"file": ("a.mp4", io.BytesIO(b"x"), "video/mp4")},
        data={"lang": "zh"},
    ).json()
    source_id = created["source"]["id"]

    body = client.get(f"/api/sources/{source_id}").json()
    assert body["id"] == source_id
    assert body["origin"] == "a.mp4"

    assert client.get("/api/sources/987654").status_code == 404


def test_cors_allows_frontend_dev_origin(client):
    resp = client.options("/api/registry", headers={
        "Origin": "http://localhost:3100",
        "Access-Control-Request-Method": "GET",
    })
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3100"


# --------------------------------------------------------------------------
# IngestHandler — không có test nào khác chạm tới lớp này
# --------------------------------------------------------------------------

@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "h.db", clock=SystemClock())
    r.init_schema()
    return r


def _fake_extract(monkeypatch, *, duration: float = 3.5, content: bytes = b"wav"):
    """Chặn ffmpeg: ghi một tệp wav giả và ghi lại tham số đã gọi."""
    from app.pipeline import ingest

    calls: list[dict] = []

    def fake(media_path, out_dir, *, stem=None):
        calls.append({"media": pathlib.Path(media_path),
                      "out_dir": pathlib.Path(out_dir), "stem": stem})
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{stem or pathlib.Path(media_path).stem}.wav"
        target.write_bytes(content)
        return target, duration

    monkeypatch.setattr(ingest, "extract_audio", fake)
    return calls


def _ingest_job(source_id: int) -> Job:
    return Job(id=None, workspace=1, type="ingest", engine=None,
               phase=js.phase_of("ingest", None),
               payload={"source_id": source_id})


def test_ingest_handler_declares_the_ingest_job_type():
    from app.pipeline.ingest import IngestHandler

    assert IngestHandler(object()).handles() == "ingest"


def test_ingest_handler_extracts_audio_and_creates_asr_job(repos, tmp_path, monkeypatch):
    from app.pipeline.ingest import IngestHandler

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    media = media_dir / "bai-giang.mp4"
    media.write_bytes(b"video")
    calls = _fake_extract(monkeypatch, duration=3.5)

    source_id = repos.add_source(kind="file", origin="bai-giang.mp4",
                                 media_path=str(media), lang="zh")
    job_id = repos.add_job(Job(id=None, workspace=1, type="ingest", engine=None,
                               phase=js.phase_of("ingest", None),
                               payload={"source_id": source_id, "lang": "zh"}))
    job = repos.get_job(job_id)

    handler = IngestHandler(repos)
    lines: list[str] = []
    handler.run(job, lambda fraction, line: lines.append(line))

    # 1. ffmpeg được gọi trên đúng tệp media, đúng thư mục, đúng stem.
    assert [c["media"] for c in calls] == [media]
    assert calls[0]["out_dir"] == media_dir, "mặc định audio_dir là thư mục của media"
    assert calls[0]["stem"] == "bai-giang"

    source = repos.get_source(source_id)
    assert source.audio_path is not None
    assert pathlib.Path(source.audio_path).exists(), "wav phải có thật trên đĩa"
    assert pathlib.Path(source.audio_path).read_bytes() == b"wav"
    assert source.duration == pytest.approx(3.5)

    asr = [j for j in repos.list_jobs() if j.type == "asr"]
    assert len(asr) == 1, "ingest phải tạo ĐÚNG một job asr"
    assert asr[0].payload["source_id"] == source_id
    assert asr[0].payload["lang"] == "zh"
    assert asr[0].engine == "fw-large-v3-turbo", "engine mặc định của registry GĐ1a"
    assert asr[0].phase == js.phase_of("asr", "fw-large-v3-turbo")
    assert asr[0].workspace == 1
    assert asr[0].state == js.QUEUED
    assert lines, "handler phải báo tiến độ qua report()"


def test_ingest_handler_honours_explicit_audio_dir(repos, tmp_path, monkeypatch):
    from app.pipeline.ingest import IngestHandler

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    media = media_dir / "v.mp4"
    media.write_bytes(b"video")
    audio_dir = tmp_path / "audio"
    calls = _fake_extract(monkeypatch)

    source_id = repos.add_source(kind="file", origin="v.mp4",
                                 media_path=str(media), lang="en")
    IngestHandler(repos, audio_dir=audio_dir).run(
        _ingest_job(source_id), lambda fraction, line: None)

    assert calls[0]["out_dir"] == audio_dir
    assert pathlib.Path(repos.get_source(source_id).audio_path).parent == audio_dir


def test_ingest_handler_preserves_the_explicit_language(repos, tmp_path, monkeypatch):
    from app.pipeline.ingest import IngestHandler

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    media = media_dir / "v.mp4"
    media.write_bytes(b"video")
    _fake_extract(monkeypatch)

    source_id = repos.add_source(kind="file", origin="v.mp4",
                                 media_path=str(media), lang="en")
    IngestHandler(repos).run(_ingest_job(source_id), lambda fraction, line: None)

    asr = [j for j in repos.list_jobs() if j.type == "asr"]
    assert asr[0].payload["lang"] == "en", "không được ghi đè ngôn ngữ đã khai báo"


def test_ingest_handler_marks_the_default_language_as_a_fallback(repos, tmp_path, monkeypatch):
    """Nguồn không khai báo `lang` (vd. do Task 19 nạp thẳng) vẫn phải ra 'zh'.

    Dòng log của nhánh dự phòng phải PHÂN BIỆT ĐƯỢC với ngôn ngữ do người dùng
    khai báo — nếu không, 'zh' giả định trá hình thành 'zh' đã chọn.
    """
    from app.pipeline.ingest import IngestHandler

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    media = media_dir / "khong-ro-ngon-ngu.mp4"
    media.write_bytes(b"video")
    _fake_extract(monkeypatch)

    source_id = repos.add_source(kind="file", origin="khong-ro-ngon-ngu.mp4",
                                 media_path=str(media), lang=None)
    lines: list[str] = []
    IngestHandler(repos).run(_ingest_job(source_id),
                             lambda fraction, line: lines.append(line))

    asr = [j for j in repos.list_jobs() if j.type == "asr"]
    assert asr[0].payload["lang"] == "zh"
    fallback_lines = [line for line in lines if "chưa khai báo" in line]
    assert fallback_lines, f"thiếu dấu vết của nhánh dự phòng: {lines!r}"


def test_ingest_handler_raises_an_actionable_error_when_media_is_missing(repos, tmp_path):
    from app.pipeline.ingest import IngestHandler, IngestError

    missing = tmp_path / "media" / "bien-mat.mp4"
    source_id = repos.add_source(kind="file", origin="bien-mat.mp4",
                                 media_path=str(missing), lang="zh")

    with pytest.raises(IngestError) as excinfo:
        IngestHandler(repos).run(_ingest_job(source_id), lambda fraction, line: None)

    message = str(excinfo.value)
    assert "bien-mat.mp4" in message, f"lỗi phải nêu tên tệp: {message!r}"
    assert str(source_id) in message, f"lỗi phải nêu source id: {message!r}"
    assert [j for j in repos.list_jobs() if j.type == "asr"] == [], (
        "media thiếu thì không được tạo job asr"
    )


def test_media_path_is_taken_from_pathlib_not_string_splitting(repos, tmp_path, monkeypatch):
    """`media_path` có thể là chuỗi kiểu POSIX dù chạy trên Windows.

    Brief định vị tệp đã lưu bằng `media_path.split("/")[-1]`. Trên Windows phép
    cắt đó trả về NGUYÊN đường dẫn (không có '/' nào), còn
    `Path(tmp) / "media" / <đường dẫn tuyệt đối>` lại THAY thế vế trái — nên
    test cũ xanh do may mắn chứ không do đúng. `pathlib` cho đúng kết quả trên cả
    hai kiểu dấu phân cách, và đó là thứ route + handler dùng.
    """
    from app.pipeline.ingest import IngestHandler, IngestError

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "bai-giang.mp4").write_bytes(b"video")
    calls = _fake_extract(monkeypatch)

    posix_style = "/data/media/bai-giang.mp4"
    windows_style = r"D:\data\media\bai-giang.mp4"
    for raw in (posix_style, windows_style):
        assert pathlib.Path(raw).name == "bai-giang.mp4"
        assert pathlib.Path(raw).stem == "bai-giang"

    source_id = repos.add_source(kind="file", origin="bai-giang.mp4",
                                 media_path=posix_style, lang="zh")
    # Đường dẫn kiểu POSIX đó không trỏ tới tệp nào trên máy này -> phải hỏng
    # ồn ào và TUYỆT ĐỐI không được gọi ffmpeg trên đường dẫn sai.
    with pytest.raises(IngestError):
        IngestHandler(repos).run(_ingest_job(source_id), lambda fraction, line: None)
    assert calls == []


# --------------------------------------------------------------------------
# main.build_components — dây nối governor, và cấu hình chống job dịch chết
# --------------------------------------------------------------------------

ASR_SPEC = EngineSpec(id="fw-large-v3-turbo", label="FW turbo", kind="asr",
                      runtime="inprocess", model_ref="large-v3-turbo",
                      vram_mb=1600, langs=("zh", "en"), capabilities={}, opts={})
MT_SPEC = EngineSpec(id="qwen2.5-7b", label="Qwen", kind="mt", runtime="ollama",
                     model_ref="qwen2.5:7b", vram_mb=5200, langs=("zh",),
                     capabilities={}, opts={})


class _RecordingEngine:
    def __init__(self) -> None:
        self.releases = 0

    def transcribe(self, audio_path: str, lang: str):
        return []

    def release(self) -> None:
        self.releases += 1


@pytest.fixture()
def built(tmp_path, monkeypatch):
    """Dựng `build_components()` thật, chỉ thay registry, engine nặng và đường dẫn.

    `DB_PATH`/`MEDIA_DIR` bị chuyển vào `tmp_path` để test không bao giờ đụng
    vào `data/` thật của repo.
    """
    from app import main

    engine = _RecordingEngine()
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(main, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(main, "load_registry", lambda: [ASR_SPEC, MT_SPEC])
    monkeypatch.setattr(main, "_engine_factory", lambda spec: engine, raising=False)
    repos, specs, worker = main.build_components()
    return main, repos, specs, worker, engine


def test_build_components_registers_every_asr_engine_with_the_governor(built):
    """`governor.register()` không có người gọi nào trước Task 15.

    Không có dây này thì `before_phase`/`after_phase` là hàm rỗng và model ASR
    KHÔNG BAO GIỜ được đổ — đúng cái mà hàng đợi theo giai đoạn sinh ra để làm.
    """
    main, repos, specs, worker, engine = built
    governor = worker.governor

    assert set(governor._loaded) == {ASR_SPEC.phase_key}
    assert ASR_SPEC.phase_key == js.phase_of("asr", "fw-large-v3-turbo")

    releaser = governor._loaded[ASR_SPEC.phase_key]
    assert getattr(releaser, "__self__", None) is worker.handlers["asr"]
    assert getattr(releaser, "__func__", None) is type(worker.handlers["asr"]).release


def test_registered_releaser_actually_unloads_the_loaded_model(built):
    """Kiểm tra cái releaser đã đăng ký là hàm ĐỔ MODEL, không phải hàm rỗng."""
    main, repos, specs, worker, engine = built
    handler = worker.handlers["asr"]

    # Nạp engine vào handler bằng đúng đường mà `run()` đi. Gọi thẳng hàm riêng
    # ở đây là cố ý: `run()` đòi audio + engine thật, còn thứ đang được kiểm là
    # liên kết handler -> factory.
    loaded = handler._engine_for(ASR_SPEC.id)  # noqa: SLF001 - xem chú thích trên
    assert loaded is engine

    releaser = worker.governor._loaded[ASR_SPEC.phase_key]
    releaser()
    assert engine.releases == 1, "releaser đã đăng ký không đổ model"

    # Idempotent: gọi lại không được nổ (worker gọi cả before_phase lẫn after_phase).
    releaser()
    assert engine.releases == 1

    # Và đường thật của worker cũng phải đổ model khi rời giai đoạn sang một
    # giai đoạn KHÁC. Nạp lại engine trước đã, nếu không thì không có gì để đổ
    # và phép khẳng định sẽ đúng một cách vô nghĩa.
    handler._engine_for(ASR_SPEC.id)
    worker.governor.before_phase(js.phase_of("translate", "qwen2.5-7b"))
    assert engine.releases == 2, "before_phase của giai đoạn khác không đổ model ASR"


def test_build_components_defaults_auto_forward_off_until_mt_exists(built):
    """`auto_forward` mặc định BẬT, mà GĐ1a chưa có handler 'translate'.

    Bật thì mỗi nguồn bóc băng xong sẽ đẩy một job `translate` vào hàng đợi, và
    worker (đúng như Task 9 khoá lại) đánh dấu nó FAILED. Nên mặc định phải là
    '0' cho tới khi có Giai đoạn 2.
    """
    main, repos, specs, worker, engine = built

    assert repos.get_setting("auto_forward") == "0"
    assert set(worker.handlers) == {"ingest", "asr", "export"}


def test_build_components_does_not_overwrite_an_auto_forward_choice(built):
    """Người dùng đã đặt '1' thì `build_components()` không được ghi đè."""
    main, repos, specs, worker, engine = built

    repos.set_setting("auto_forward", "1")
    main.build_components()
    assert repos.get_setting("auto_forward") == "1"


def test_build_components_only_registers_asr_engines(monkeypatch, tmp_path):
    """Engine MT không được đăng ký: GĐ1a chạy nó qua Ollama, không qua handler này."""
    from app import main

    monkeypatch.setattr(main, "load_registry", lambda: [ASR_SPEC, MT_SPEC])
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(main, "LOG_DIR", tmp_path / "logs")
    repos, specs, worker = main.build_components()

    assert set(worker.governor._loaded) == {ASR_SPEC.phase_key}


def test_engine_factory_points_the_faster_whisper_cache_at_the_configured_disk():
    """Ruling: không để ~1.6 GB model rơi vào cache mặc định ở ổ C:.

    Chỉ chạm tham số, không nạp model: `faster_whisper` được thay bằng stub.
    """
    from app import config, main
    from app.adapters.asr.faster_whisper import FasterWhisperEngine

    seen: dict = {}

    class _StubModel:
        def __init__(self, model_ref, **kwargs):
            seen["model_ref"] = model_ref
            seen.update(kwargs)

    stub = types.ModuleType("faster_whisper")
    stub.WhisperModel = _StubModel
    stub.BatchedInferencePipeline = object
    sys.modules["faster_whisper"] = stub
    try:
        engine = main._engine_factory(ASR_SPEC)
        assert isinstance(engine, FasterWhisperEngine)
        engine._load()
    finally:
        sys.modules.pop("faster_whisper", None)

    assert seen["download_root"] == config.HF_HOME
    assert seen["model_ref"] == "large-v3-turbo"


# --------------------------------------------------------------------------
# Cấu trúc gói
# --------------------------------------------------------------------------

def test_api_layer_does_not_import_adapters():
    """`app/api` chỉ nói chuyện qua app.state; adapter là việc của `app/main.py`."""
    import ast

    api_dir = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
    offenders: list[str] = []
    for py in sorted(api_dir.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            offenders += [f"{py.name}: {n}" for n in names
                          if n.startswith("app.adapters")]
    assert not offenders, "app/api không được kéo adapter vào:\n  " + "\n  ".join(offenders)


# Từ khoá cho thấy `app/api` tự chạm vào TỆP SQLite thay vì đi qua `Repos`.
_PERSISTENCE_REACH = ("db_path", "_connect(", "import sqlite3")


def _persistence_reach(directory: pathlib.Path) -> list[str]:
    """Tên tệp + từ khoá vi phạm ranh giới cổng, quét cả gói con."""
    offenders: list[str] = []
    for py in sorted(directory.rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        offenders += [f"{py.name}: {needle}" for needle in _PERSISTENCE_REACH
                      if needle in text]
    return offenders


def test_api_layer_never_reaches_for_the_persistence_file():
    """R74: `app/api` đi qua `Repos`; mở tệp DB là việc của adapter.

    Đây là mắt lưới còn thiếu: `test_api_layer_does_not_import_adapters` chỉ bắt
    tên module bắt đầu bằng `app.adapters`, nên một `import sqlite3` trần và một
    `getattr(repos, "db_path")` lọt qua sạch sẽ (đúng thứ R74 mô tả).
    `backend/app/main.py` là composition root — chỗ DUY NHẤT được biết
    `SqliteRepos` — nên nó nằm ngoài thư mục bị quét ở đây.
    """
    api_dir = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
    offenders = _persistence_reach(api_dir)
    assert not offenders, (
        "app/api không được tự mở tệp SQLite (dùng phương thức trên `Repos`):\n  "
        + "\n  ".join(offenders)
    )


def test_persistence_guard_catches_a_rogue_api_file(tmp_path):
    """Lưới phải bắt được thật, không phải vòng lặp rỗng."""
    (tmp_path / "rogue.py").write_text(
        "import sqlite3\n"
        "conn = repos._connect()\n"
        "path = repos.db_path\n",
        encoding="utf-8",
    )
    offenders = _persistence_reach(tmp_path)
    assert sorted(o.split(": ", 1)[1] for o in offenders) == sorted(_PERSISTENCE_REACH), (
        offenders
    )


def test_main_module_is_importable_without_starting_a_server():
    """`app.main` chỉ được dựng đối tượng; việc chạy server nằm trong `main()`."""
    import app.main as main_mod

    assert callable(main_mod.main)
    assert callable(main_mod.build_components)


def test_run_api_entrypoint_exists_and_defers_to_main():
    backend = pathlib.Path(__file__).resolve().parents[1]
    text = (backend / "run_api.py").read_text(encoding="utf-8")
    assert "from app.main import main" in text
    assert "__main__" in text
