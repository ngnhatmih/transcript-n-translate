"""Test của Task 15: app factory, route sources/registry/status, và IngestHandler.

Ngoài 9 test route của brief còn hai nhóm test CHE hai lỗ hổng đã biết:

* `IngestHandler` — điểm vào của cả pipeline. Nó chỉ xuất hiện trong `main.py`
  và trong định nghĩa của chính nó; Task 19 thay nó bằng stub trong E2E, nên
  nếu không có test ở đây thì lớp thật này KHÔNG được chạy ở đâu cả.
* `SingleGpuGovernor.register()` — không có người gọi nào trước Task 15, nên
  `before_phase`/`after_phase` là hàm rỗng và model ASR không bao giờ được đổ.
"""
from __future__ import annotations

import asyncio
import ast
import dataclasses
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
from app.domain.models import Job, Segment, Source
from app.registry import EngineSpec, by_id
from tests.fakes import RecordingHandler, a_job


def _engine_specs() -> list[EngineSpec]:
    """Hai engine tối thiểu để `create_app()` dựng được app đầy đủ, không model."""
    return [
        EngineSpec(id="fw-large-v3-turbo", label="FW turbo", kind="asr",
                   runtime="inprocess", model_ref="large-v3-turbo", vram_mb=1600,
                   langs=("zh", "en"),
                   capabilities={"timestamps": True, "word_timestamps": True}, opts={}),
        EngineSpec(id="qwen2.5-7b", label="Qwen 7B", kind="mt", runtime="ollama",
                   model_ref="qwen2.5:7b", vram_mb=5200, langs=("zh", "en"),
                   capabilities={"glossary_prompt": True}, opts={}),
    ]


@pytest.fixture()
def client(tmp_path):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    app = create_app(repos=repos, specs=_engine_specs(), media_dir=tmp_path / "media",
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


def test_status_reports_the_vram_key_the_spec_promises(client):
    """API-04 (R77): spec §11 ghim `GET /api/status` trả cả VRAM.

    App ở fixture này dựng **không có** `vram_reader` (test chỉ đọc, không GPU),
    nên giá trị `None` là đúng nghĩa "chưa đọc được" — khoá vẫn có, JSON là
    `null` — cùng khuôn với `ollama: "unknown"`. Frontend code theo hình dạng hợp
    đồng nên nó đọc `body["vram"]`, không phải phòng thủ bằng `if "vram" in body`.

    Đường SẢN XUẤT (có reader, đo thật bằng `nvidia-smi`) được ghim ở
    `tests/test_status_vram.py` — đừng thêm reader vào fixture này: bài này đang
    đo đúng ca "không có đường đo", và trộn hai ca vào một fixture là làm nó mù.
    """
    body = client.get("/api/status").json()
    assert "vram" in body, sorted(body)
    assert body["vram"] is None
    assert body["vram_unit"] == "MiB", "đơn vị phải có kể cả khi chưa đo được"


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


def _upload_raw_multipart(client, filename_header: str):
    """POST multipart THÔ, để `filename=""` tới được tận route.

    `httpx` biến `files={"file": ("", ...)}` thành một trường FORM chuỗi, nên
    FastAPI trả 422 ngay ở khâu validate `UploadFile` và `safe_basename` KHÔNG
    hề chạy — một test như vậy xanh mà không chứng minh gì. Gửi thân multipart
    tự dựng thì Starlette giữ nguyên `filename=""` và `file.filename` mới thật
    sự là chuỗi rỗng.
    """
    boundary = "----phu-de-lab-doc09"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename_header}"\r\n'
        "Content-Type: video/mp4\r\n"
        "\r\n"
        "x\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="lang"\r\n'
        "\r\n"
        "zh\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    return client.post(
        "/api/sources/upload",
        content=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def test_upload_answers_422_for_an_empty_filename(client):
    """DOC-09 (N6): route upload KHÔNG lùi về `fallback` khi client gửi `""`.

    Cùng giá trị `""` mà `ExportHandler` lùi về `transcript-<id>` (xem
    `test_export.py::test_empty_stem_falls_back_instead_of_raising`), còn ở đây
    là lỗi ĐẦU VÀO của client ⇒ 422 nêu tên trường. Hai hành vi khác nhau là CỐ
    Ý, đã ghi ở docstring `safe_basename`; làm chúng giống nhau sẽ đỏ một trong
    hai test.
    """
    resp = _upload_raw_multipart(client, "")
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


def test_url_endpoint_rejects_a_downloaded_path_outside_the_media_root(client, monkeypatch):
    """I-6 · tên tệp do yt-dlp sinh ra (từ `%(id)s`, tức do site CHỌN) phải được
    chứng minh nằm trong `media_dir` TRƯỚC khi nó thành `media_path` trong DB.

    Đường đọc của cùng cột đó đã kiểm (`routes_media.py:125` dùng `resolve_within`);
    đường ghi thì chưa. Không có guard này, một hàng `sources` trỏ ra ngoài gốc
    media vẫn được tạo và ffprobe/ffmpeg đọc nó ở tận worker.
    """
    outside = client.tmp / "ngoai" / "thoat.mp4"
    outside.parent.mkdir()
    outside.write_bytes(b"x")

    def escapes(url, out_dir, on_progress=None, runner=None):
        return outside

    monkeypatch.setattr("app.api.routes_sources.ingest.download_url", escapes)
    resp = client.post("/api/sources/url",
                       json={"url": "https://example.com/v", "lang": "zh"})

    assert resp.status_code == 422, resp.text
    assert client.repos.list_sources() == [], (
        "không được lưu một `media_path` nằm ngoài gốc media"
    )
    assert [j for j in client.repos.list_jobs() if j.type == "ingest"] == [], (
        "không được xếp job ingest cho một đường dẫn bị từ chối"
    )


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


def _fw_tiny_spec() -> EngineSpec:
    """Một engine asr CÓ THẬT nhưng KHÁC mặc định — để test không xanh do trùng id."""
    return EngineSpec(id="fw-tiny", label="FW tiny", kind="asr", runtime="inprocess",
                      model_ref="tiny", vram_mb=200, langs=("zh", "en"),
                      capabilities={}, opts={})


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
    # Khẳng định bằng lớp PurePath TƯỜNG MINH (M8/RU-05): `pathlib.Path(r"D:\…")`
    # là `PurePosixPath` trên POSIX, nên `.name` trả CẢ chuỗi và bản cũ đỏ trên
    # CI Linux. Máy này Windows-only ⇒ ca POSIX ở đây là SUY LUẬN, không quan sát.
    assert pathlib.PurePosixPath(posix_style).name == "bai-giang.mp4"
    assert pathlib.PurePosixPath(posix_style).stem == "bai-giang"
    assert pathlib.PureWindowsPath(windows_style).name == "bai-giang.mp4"
    assert pathlib.PureWindowsPath(windows_style).stem == "bai-giang"

    source_id = repos.add_source(kind="file", origin="bai-giang.mp4",
                                 media_path=posix_style, lang="zh")
    # Đường dẫn kiểu POSIX đó là TUYỆT ĐỐI và nằm ngoài gốc media của test, nên
    # handler phải từ chối bằng guard I-6 (`resolve_within`): nó KHÔNG được bị
    # diễn giải lại thành đường dẫn tương đối dưới `media_dir` rồi đưa cho ffmpeg.
    # Khẳng định này khác `test_ingest_handler_raises_an_actionable_error_when_
    # media_is_missing` (test kia không truyền `media_root`, nên chỉ chạm nhánh
    # "tệp không tồn tại"); ở đây điều được ghim là phép phân giải đường dẫn.
    with pytest.raises(IngestError, match="ngoài gốc media"):
        IngestHandler(repos, media_root=media_dir).run(
            _ingest_job(source_id), lambda fraction, line: None)
    assert calls == [], "không được gọi ffmpeg trên đường dẫn sai"


def test_ingest_handler_refuses_an_asr_engine_absent_from_the_registry(repos, tmp_path,
                                                                     monkeypatch):
    """I-3 · đừng xếp một job asr CHẮC CHẮN chết: hỏng ngay, nói rõ id và id có thật.

    Reproduced live: registry chỉ có `fw-tiny`, mặc định trỏ `fw-large-v3-turbo`
    ⇒ upload → `ingest:done` → `asr:failed` với `KeyError` trần ở tận worker.
    """
    from app.pipeline.ingest import IngestError, IngestHandler

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    media = media_dir / "v.mp4"
    media.write_bytes(b"video")
    _fake_extract(monkeypatch)
    repos.set_setting("default_asr_engine", "khong-co")

    source_id = repos.add_source(kind="file", origin="v.mp4",
                                 media_path=str(media), lang="zh")
    handler = IngestHandler(repos, specs=[_fw_tiny_spec()], media_root=media_dir)

    with pytest.raises(IngestError) as excinfo:
        handler.run(_ingest_job(source_id), lambda fraction, line: None)

    message = str(excinfo.value)
    assert "khong-co" in message, f"lỗi phải nêu id không có: {message!r}"
    assert "fw-tiny" in message, (
        f"lỗi phải liệt kê engine asr ĐANG CÓ để sửa được ngay: {message!r}"
    )
    assert [j for j in repos.list_jobs() if j.type == "asr"] == [], (
        "không được xếp một job asr đã biết là chết"
    )


def test_ingest_handler_takes_the_default_asr_engine_from_the_registry(repos, tmp_path,
                                                                      monkeypatch):
    """I-3 · mặc định đến từ registry.json, không phải hằng số trong code."""
    from app.pipeline.ingest import IngestHandler

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    media = media_dir / "v.mp4"
    media.write_bytes(b"video")
    _fake_extract(monkeypatch)

    source_id = repos.add_source(kind="file", origin="v.mp4",
                                 media_path=str(media), lang="zh")
    handler = IngestHandler(repos, specs=[_fw_tiny_spec()],
                            declared_default_asr="fw-tiny", media_root=media_dir)
    handler.run(_ingest_job(source_id), lambda fraction, line: None)

    asr = [j for j in repos.list_jobs() if j.type == "asr"]
    assert [j.engine for j in asr] == ["fw-tiny"], (
        "engine mặc định phải là dữ liệu của registry, không phải literal trong code"
    )
    assert asr[0].phase == js.phase_of("asr", "fw-tiny")


def test_ingest_handler_refuses_media_outside_the_media_root(repos, tmp_path, monkeypatch):
    """I-6 · `media_path` là DỮ LIỆU: ngoài gốc media ⇒ từ chối trước ffprobe/ffmpeg."""
    from app.pipeline.ingest import IngestError, IngestHandler

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    secret = tmp_path / "ngoai" / "secret.mp4"
    secret.parent.mkdir()
    secret.write_bytes(b"video")
    calls = _fake_extract(monkeypatch)

    source_id = repos.add_source(kind="file", origin="secret.mp4",
                                 media_path=str(secret), lang="zh")
    handler = IngestHandler(repos, media_root=media_dir)

    with pytest.raises(IngestError, match="ngoài"):
        handler.run(_ingest_job(source_id), lambda fraction, line: None)

    assert calls == [], "không được đưa đường dẫn ngoài gốc cho ffmpeg/ffprobe"
    assert [j for j in repos.list_jobs() if j.type == "asr"] == []


# --------------------------------------------------------------------------
# main.build_components — dây nối governor, và cấu hình chống job dịch chết
# --------------------------------------------------------------------------

ASR_SPEC = EngineSpec(id="fw-large-v3-turbo", label="FW turbo", kind="asr",
                      runtime="inprocess", model_ref="large-v3-turbo",
                      vram_mb=1600, langs=("zh", "en"), capabilities={}, opts={})
MT_SPEC = EngineSpec(id="qwen2.5-7b", label="Qwen", kind="mt", runtime="ollama",
                     model_ref="qwen2.5:7b", vram_mb=5200, langs=("zh",),
                     capabilities={}, opts={})


def _registry_with_the_shipped_mt_default(specs: list[EngineSpec]) -> list[EngineSpec]:
    """Registry giả + engine mặc định THẬT, khi danh sách chưa có nó.

    WQ-02/F3: composition root nay đối chiếu id mặc định với chính `specs` và
    hỏng NGAY lúc dựng khi không khớp, nên một registry rút gọn phải TỰ NHẤT
    QUÁN với mặc định đã ship — nếu không thì mọi test dùng fixture này đỏ vì
    một lý do không liên quan tới thứ nó đang kiểm. Id thật được thêm vào CUỐI
    danh sách `mt` để "phần tử đầu mảng" vẫn khác mặc định: đó chính là thứ khiến
    bài ghim dây nối `default_mt` có năng lực phát hiện.

    Task 13 (correction C): engine mặc định thêm vào đây là spec THẬT của
    `registry.json`, KHÔNG phải một `dataclasses.replace(MT_SPEC, ...)`. Bản cũ
    dựng một `opus-mt` giả mang `runtime="ollama"` và `model_ref="qwen2.5:7b"` —
    một engine KHÔNG hề tồn tại trong registry thật. Từ khi `build_components()`
    đòi engine mặc định phải SẴN SÀNG, một spec giả như vậy làm cả fixture đỏ vì
    lý do bịa: nó khai một engine `ollama` chưa pull. Lấy spec thật (in-process,
    `available=True` luôn đúng) vừa làm fixture trung thực với sản xuất, vừa khiến
    mọi bài dưới đây chạy trên engine mặc định CÓ THẬT.
    """
    from app.adapters.registry_file import load_default_mt, load_registry

    declared = load_default_mt()
    if declared is None or declared in {s.id for s in specs}:
        return list(specs)
    real = [s for s in load_registry() if s.id == declared]
    assert real, (
        f"registry.json khai `default_mt` = {declared!r} nhưng không có spec nào "
        f"mang id đó — sửa registry.json, đây không phải lỗi của fixture"
    )
    return list(specs) + real


class _RecordingEngine:
    def __init__(self) -> None:
        self.releases = 0

    def transcribe(self, audio_path: str, lang: str):
        return []

    def release(self) -> None:
        self.releases += 1


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
    `data/{media,logs,output}` của repo. Đo trên chính thư mục repo — `tmp_path`
    không thấy được điểm mù này.
    """
    created = [str(d) for d, existed in before.items() if not existed and d.exists()]
    assert not created, (
        "build_components() đã tạo thư mục THẬT trong repo: " + ", ".join(created)
        + ". Phải vá `app.config` (nơi `ensure_dirs()` đọc biến), không chỉ vá "
          "tên đã import vào `main` (M7/RU-04)."
    )


@pytest.fixture()
def built(tmp_path, monkeypatch):
    """Dựng `build_components()` thật, chỉ thay registry, engine nặng và đường dẫn.

    `DB_PATH`/`MEDIA_DIR` bị chuyển vào `tmp_path` để test không bao giờ đụng
    vào `data/` thật của repo. Phải vá CẢ `app.config`: `ensure_dirs()`
    (`config.py:38-40`) đọc biến toàn cục của chính module đó, nên vá mỗi tên đã
    import vào `main` là không đủ — `main.build_components()` vẫn tạo `data/`
    THẬT của repo (đúng cái bẫy đã biết ở Q5 của review Task 19). Khẳng định
    `_assert_repo_data_dirs_untouched` ngay dưới đây biến lời hứa đó thành thứ
    chạy được: bỏ các dòng vá `config` là MỌI test dùng fixture này đỏ.

    Task 12: `build_components()` trả TUPLE 5 phần tử, `mt_engines` ở CUỐI
    (correction A — không đổi sang dataclass), nên fixture trả thêm nó cho những
    bài cần ráp `build_app()`.
    """
    from app import config, main

    repo_data_before = _snapshot_repo_data_dirs()
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(config, "LOG_DIR", data / "logs")
    monkeypatch.setattr(config, "OUTPUT_DIR", data / "output")

    engine = _RecordingEngine()
    monkeypatch.setattr(main, "DB_PATH", data / "app.db")
    monkeypatch.setattr(main, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(main, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "LOG_DIR", data / "logs")
    monkeypatch.setattr(main, "load_registry",
                        lambda: _registry_with_the_shipped_mt_default([ASR_SPEC, MT_SPEC]))
    monkeypatch.setattr(main, "_engine_factory", lambda spec: engine, raising=False)
    # Task 12: composition root dò Ollama SỐNG để quyết định engine dịch nào tồn
    # tại. Fixture này không kiểm phép dò đó (nó có bài riêng ở
    # `tests/test_mt_wiring.py`), nên nó ghim kết quả thành "tắt" để suite không
    # phụ thuộc việc Ollama có đang chạy trên máy hay không.
    #
    # Fix round 1 (I-1): phép dò nay trả về TÊN model đã pull, và tập RỖNG nghĩa
    # là "không engine ollama nào phục vụ được" — cùng kết quả như bản cũ trả
    # `False`, nên Ý NGHĨA của fixture này không đổi, chỉ kiểu giá trị đổi.
    monkeypatch.setattr(main, "ollama_available", lambda *a, **k: set())
    repos, specs, worker, broker, mt_engines = main.build_components()
    _assert_repo_data_dirs_untouched(repo_data_before)
    return main, repos, specs, worker, engine, broker, mt_engines


def test_build_components_refuses_a_registry_that_cannot_satisfy_the_default_asr(
        monkeypatch, tmp_path):
    """I-3 · registry không có engine mặc định ⇒ hỏng NGAY lúc dựng, không tạo job chết.

    Đây là chỗ SỚM NHẤT có thể phát hiện: một tiến trình server dựng xong với
    cấu hình này sẽ nhận upload rồi đẻ ra job asr chắc chắn `KeyError` tận worker.
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
    # Registry THẬT khai báo `default_asr = fw-large-v3-turbo`; danh sách dưới
    # đây không có nó -> dựng app phải hỏng kèm chỉ dẫn.
    monkeypatch.setattr(main, "load_registry", lambda: [MT_SPEC])

    with pytest.raises(RuntimeError) as excinfo:
        main.build_components()

    message = str(excinfo.value)
    assert "fw-large-v3-turbo" in message, message
    assert "default_asr" in message, f"lỗi phải chỉ đúng khoá cần sửa: {message!r}"


def test_build_components_refuses_a_registry_that_cannot_satisfy_the_default_mt(
        monkeypatch, tmp_path):
    """WQ-02/F3 · `default_mt` gõ sai phải hỏng NGAY lúc dựng, y như `default_asr`.

    `default_mt_engine` từng trả thẳng id đã khai báo mà không đối chiếu `specs`,
    nên một `default_mt` gõ sai trở thành engine của MỌI job `translate` một cách
    im lặng — GĐ1a chưa có handler `translate` nên job chỉ FAILED ở tận worker.
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
    monkeypatch.setattr(main, "load_registry", lambda: [ASR_SPEC, MT_SPEC])
    # Registry THẬT trỏ tới một id CÓ THẬT; ở đây giả lập một lần gõ sai khoá
    # `default_mt` trong registry.json.
    monkeypatch.setattr(main, "load_default_mt", lambda: "opus-mt-go-nham")

    with pytest.raises(RuntimeError) as excinfo:
        main.build_components()

    message = str(excinfo.value)
    assert "opus-mt-go-nham" in message, message
    assert "default_mt" in message, f"lỗi phải chỉ đúng khoá cần sửa: {message!r}"


def test_build_components_wires_the_ingest_guards_into_the_real_handler(built, tmp_path):
    """I-3 + I-6 · dây nối THẬT của `build_components()` phải mang hai guard theo.

    Không có bài này thì bỏ `specs=`/`media_root=` ở `main.py` vẫn xanh toàn bộ
    suite: handler vẫn dựng được, chỉ là nó không còn biết registry và gốc media.
    """
    from app.pipeline.ingest import IngestError

    main, repos, specs, worker, engine, broker, mt_engines = built
    handler = worker.handlers["ingest"]

    # I-6: media nằm NGOÀI gốc media -> từ chối trước khi chạm ffmpeg/ffprobe.
    outside = tmp_path / "ngoai" / "secret.mp4"
    outside.parent.mkdir()
    outside.write_bytes(b"video")
    sid = repos.add_source(kind="file", origin="secret.mp4",
                           media_path=str(outside), lang="zh")
    with pytest.raises(IngestError, match="ngoài"):
        handler.run(_ingest_job(sid), lambda fraction, line: None)

    # I-3: setting trỏ engine không có trong registry -> hỏng ngay, không xếp job asr.
    repos.set_setting("default_asr_engine", "khong-co")
    inside = pathlib.Path(main.MEDIA_DIR) / "trong.mp4"
    inside.write_bytes(b"video")
    sid2 = repos.add_source(kind="file", origin="trong.mp4",
                            media_path=str(inside), lang="zh")
    with pytest.raises(IngestError) as excinfo:
        handler.run(_ingest_job(sid2), lambda fraction, line: None)
    assert "khong-co" in str(excinfo.value)
    assert [j for j in repos.list_jobs() if j.type == "asr"] == []


def test_build_components_registers_every_asr_engine_with_the_governor(built):
    """`governor.register()` không có người gọi nào trước Task 15.

    Không có dây này thì `before_phase`/`after_phase` là hàm rỗng và model ASR
    KHÔNG BAO GIỜ được đổ — đúng cái mà hàng đợi theo giai đoạn sinh ra để làm.

    Task 13 (correction C): fixture nay có thêm engine mặc định THẬT `opus-mt`
    (in-process ⇒ luôn sẵn sàng), nên `governor._loaded` có thêm giai đoạn của nó.
    Khẳng định vì thế là "tập con + đúng một releaser cho ASR", không phải đẳng
    thức với một phần tử: ghim đẳng thức là ghim luôn số engine MT của fixture,
    một thứ không liên quan tới dây nối đang được kiểm.
    """
    main, repos, specs, worker, engine, broker, mt_engines = built
    governor = worker.governor

    assert ASR_SPEC.phase_key in governor._loaded
    assert ASR_SPEC.phase_key == js.phase_of("asr", "fw-large-v3-turbo")

    releaser = governor._loaded[ASR_SPEC.phase_key]
    assert getattr(releaser, "__self__", None) is worker.handlers["asr"]
    assert getattr(releaser, "__func__", None) is type(worker.handlers["asr"]).release

    # Mọi engine dịch ĐÃ DỰNG cũng phải có releaser riêng, khoá theo
    # `spec.phase_key` — thiếu vòng đó thì model dịch nằm mãi trong VRAM.
    for engine_id in mt_engines:
        assert by_id(specs, engine_id).phase_key in governor._loaded, (
            f"engine {engine_id} không có releaser trong governor"
        )


def test_registered_releaser_actually_unloads_the_loaded_model(built):
    """Kiểm tra cái releaser đã đăng ký là hàm ĐỔ MODEL, không phải hàm rỗng."""
    main, repos, specs, worker, engine, broker, mt_engines = built
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


def test_build_components_defaults_auto_forward_on_now_that_mt_exists(built):
    """Task 12 · `auto_forward` mặc định BẬT, và nay điều đó là ĐÚNG.

    GĐ1a ép '0' vì chưa có handler `translate`: bật thì mỗi nguồn bóc băng xong
    đẩy một job `translate` vào hàng đợi và worker đánh dấu nó FAILED. Nay handler
    đó đã được nối dây, nên mặc định phải là '1' — còn '0' nghĩa là bóc băng xong
    chẳng bao giờ có bản dịch.
    """
    main, repos, specs, worker, engine, broker, mt_engines = built

    assert repos.get_setting("auto_forward") == "1"
    assert set(worker.handlers) == {"ingest", "asr", "translate", "export", "dub"}


def test_build_components_does_not_overwrite_an_auto_forward_choice(built):
    """Người dùng đã đặt '0' thì `build_components()` không được ghi đè.

    Đặt '0' chứ không phải '1': từ Task 12 mặc định đã là '1', nên một bài đặt
    '1' rồi khẳng định '1' sẽ xanh kể cả khi dây "chỉ ghi khi chưa ai đặt" bị gỡ.
    """
    main, repos, specs, worker, engine, broker, mt_engines = built

    repos.set_setting("auto_forward", "0")
    main.build_components()
    assert repos.get_setting("auto_forward") == "0"


def test_build_components_registers_only_available_mt_engines(monkeypatch, tmp_path):
    """Engine MT CHƯA sẵn sàng không được đăng ký; engine sẵn sàng thì phải có.

    Fixture ghim `ollama_available()` = `set()` — tiến trình không trả lời được,
    hoặc chưa pull model nào (I-1 không phân biệt hai thứ đó: cả hai đều nghĩa là
    engine `ollama` không phục vụ được job) — còn spec mt của registry giả ở đây
    là runtime `ollama`, nên không giai đoạn dịch nào được mở. Bài đối chứng —
    dò sống trả về ĐÚNG `model_ref` thì giai đoạn dịch PHẢI có mặt — nằm ở
    `tests/test_mt_wiring.py::test_governor_has_a_releaser_for_every_mt_phase`.

    Task 13 (correction C): `_registry_with_the_shipped_mt_default` nay thêm spec
    THẬT của engine mặc định (`opus-mt`, in-process ⇒ luôn `available`), nên
    "rỗng" KHÔNG còn là khẳng định đúng. Thứ bài này ghim là quan hệ: mọi engine
    `available` đều có mặt, mọi engine không `available` đều vắng — và vế ĐỐI
    CHỨNG nằm ngay trong bài, không phải suy từ chỗ khác.
    """
    from app import config, main

    repo_data_before = _snapshot_repo_data_dirs()
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(config, "LOG_DIR", data / "logs")
    monkeypatch.setattr(config, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "load_registry",
                        lambda: _registry_with_the_shipped_mt_default([ASR_SPEC, MT_SPEC]))
    monkeypatch.setattr(main, "DB_PATH", data / "app.db")
    monkeypatch.setattr(main, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(main, "OUTPUT_DIR", data / "output")
    monkeypatch.setattr(main, "LOG_DIR", data / "logs")
    monkeypatch.setattr(main, "ollama_available", lambda *a, **k: set())
    repos, specs, worker, broker, mt_engines = main.build_components()
    _assert_repo_data_dirs_untouched(repo_data_before)

    mt_specs = [s for s in specs if s.kind == "mt"]
    available = {s.id for s in mt_specs if s.capabilities.get("available")}
    assert available, "vế đối chứng: engine in-process (opus-mt) PHẢI sẵn sàng"
    assert set(mt_engines) == available, (
        f"engine dựng được phải ĐÚNG BẰNG engine sẵn sàng: {sorted(mt_engines)} "
        f"vs {sorted(available)}"
    )
    # `MT_SPEC` là engine `ollama` và phép dò trả `set()`: nó phải VẮNG.
    assert MT_SPEC.id not in mt_engines, (
        "engine ollama chưa pull không được có engine trong `mt_engines`"
    )
    registered = set(worker.governor._loaded)  # noqa: SLF001 - chính dây nối
    assert ASR_SPEC.phase_key in registered
    assert registered == {ASR_SPEC.phase_key} | {s.phase_key for s in mt_specs
                                                 if s.capabilities.get("available")}


def test_build_components_wires_the_job_log_dir(built):
    """DC-03/F1 · composition root phải truyền `LOG_DIR` cho `SqliteRepos`.

    Ba bài DC-03 tự dựng `SqliteRepos(..., log_dir=...)`, nên gỡ dây
    `log_dir=LOG_DIR` ở `main.py` KHÔNG làm bài nào đỏ: `log_path` âm thầm quay
    lại thành cột chết trong production. Bài này chạy một job qua worker THẬT
    của `build_components()` rồi đòi tệp log nằm ĐÚNG `main.LOG_DIR` — gỡ dây
    là đỏ ngay.
    """
    main, repos, specs, worker, engine, broker, mt_engines = built
    worker.handlers["asr"] = RecordingHandler(job_type="asr")
    jid = repos.add_job(a_job(None, job_type="asr", engine=ASR_SPEC.id))

    while worker.tick():
        pass

    job = repos.get_job(jid)
    log_path = pathlib.Path(main.LOG_DIR) / f"job-{jid}.log"
    assert job.log_path == str(log_path), job.log_path
    assert log_path.is_file(), sorted(p.name for p in pathlib.Path(main.LOG_DIR).iterdir())
    assert "chạy job" in log_path.read_text(encoding="utf-8")


def test_build_components_wires_the_declared_default_mt_engine(built):
    """R58/WQ-02 · composition root phải nạp khoá `default_mt` và truyền cho handler.

    Không có dây này thì `TranscribeHandler` dựng bởi `main.py` rơi về phần tử
    ĐẦU của mảng `mt` — đúng thứ khoá `default_mt` sinh ra để chặn — mà không
    test nào đỏ. Registry ở fixture có `mt` đầu = `qwen2.5-7b`, còn `default_mt`
    THẬT (do `_registry_with_the_shipped_mt_default` thêm vào CUỐI mảng) là một
    id khác: hai giá trị khác nhau nên một dây nối đúng là thấy được. Bài này
    KHÔNG hard-code id mặc định — đổi `default_mt` trong `registry.json` sang
    một id hợp lệ khác là chuyện của `tests/test_registry.py`, không được làm
    bài ghim DÂY NỐI này đỏ oan.
    """
    from app.adapters.registry_file import load_default_mt

    main, repos, specs, worker, engine, broker, mt_engines = built
    declared = load_default_mt()

    handler = worker.handlers["asr"]
    assert handler._declared_default_mt == declared, (  # noqa: SLF001 - đọc thẳng dây nối
        "handler của composition root phải nhận ĐÚNG giá trị `load_default_mt()`"
    )
    # Task 12: `_forward_to_translation` nay tạo HÀNG `translations` trước, nên
    # nó đọc transcript thật — không còn gọi được với id tượng trưng.
    sid = repos.add_source(kind="file", origin="a.mp4", media_path="a.mp4", lang="zh")
    tid = repos.add_transcript(source_id=sid, engine=ASR_SPEC.id, lang="zh",
                               segments=[Segment(i=0, start=0.0, end=1.0, text="你好")])
    handler._forward_to_translation(tid, "zh")  # noqa: SLF001 - chính đường thật
    mt_jobs = [j for j in repos.list_jobs() if j.type == "translate"]
    first_mt = [s.id for s in specs if s.kind == "mt"][0]
    assert [j.engine for j in mt_jobs] == [declared], (
        "handler của composition root phải dùng khoá `default_mt`, không phải "
        f"phần tử đầu của mảng `mt` ({first_mt})"
    )
    translation = repos.get_translation(mt_jobs[0].payload["translation_id"])
    assert translation.transcript_id == tid
    assert translation.transcript_version == 1
    assert translation.engine == declared


def test_the_worker_and_the_stream_share_the_broker_of_the_assembled_app(built):
    """C1 của review: trong app ĐÃ RÁP, `/api/jobs/stream` không có producer.

    `build_components()` phải dựng ĐÚNG MỘT broker, và `main()` phải truyền
    chính nó cho `create_app()`: worker publish vào broker nào thì route phải
    đọc đúng broker đó. Bỏ dây `publish=` ở worker hoặc bỏ `broker=` ở app là
    stream im lặng vĩnh viễn dù job chạy xong — đúng thứ test này bắt.

    Engine/handler được thay bằng stub (đúng như `built` đã thay engine), còn
    repos/worker/app/broker là những thành phần THẬT của `main.py`.
    """
    main, repos, specs, worker, engine, broker, mt_engines = built
    worker.handlers["asr"] = RecordingHandler(job_type="asr")
    app = main.build_app(repos, specs, worker, broker)
    assert app.state.broker is broker, "app phải đọc đúng broker của build_components()"
    repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))

    async def run_a_job():
        sub = app.state.broker.subscribe()
        try:
            while worker.tick():
                pass
            collected: list[dict] = []
            for _ in range(4):
                event = await sub.wait(5)
                assert event is not None, f"worker không publish vào broker của app: {collected}"
                collected.append(event)
            return collected
        finally:
            app.state.broker.unsubscribe(sub)

    events = asyncio.run(run_a_job())
    assert [e["state"] for e in events] == [js.RUNNING, js.RUNNING, js.RUNNING, js.DONE], (
        events
    )
    assert events[-1]["phase"] == ASR_SPEC.phase_key, events


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

def _adapter_import_offenders(directory: pathlib.Path) -> list[str]:
    """Tệp + module `app.adapters` mà `directory` kéo vào, quét ĐỆ QUY (`rglob`).

    N3/RU-03: bản cũ dùng `glob("*.py")`, nên `app/api/<gói con>/` im lặng thoát
    lưới ngay khi `app/api` mọc thêm gói con. Tách thành hàm để chính cái tính
    đệ quy ấy đo được bằng một test (xem `test_api_adapter_guard_scans_subpackages`).
    """
    offenders: list[str] = []
    for py in sorted(directory.rglob("*.py")):
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
    return offenders


def test_api_layer_does_not_import_adapters():
    """`app/api` chỉ nói chuyện qua app.state; adapter là việc của `app/main.py`."""
    api_dir = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
    offenders = _adapter_import_offenders(api_dir)
    assert not offenders, "app/api không được kéo adapter vào:\n  " + "\n  ".join(offenders)


def test_api_adapter_guard_scans_subpackages(tmp_path):
    """N3/RU-03 · lưới phải đệ quy, nếu không một gói con là thoát sạch.

    Mutation chứng minh: đổi `rglob` về `glob("*.py")` trong
    `_adapter_import_offenders` ⇒ test này đỏ.
    """
    pkg = tmp_path / "goi_con"
    pkg.mkdir()
    (pkg / "_probe.py").write_text(
        "from app.adapters.persist import sqlite_repos\n", encoding="utf-8"
    )
    assert _adapter_import_offenders(tmp_path) == [
        "_probe.py: app.adapters.persist"
    ], "tệp trong gói con của app/api đã thoát khỏi lưới"


#: Thuộc tính của `Repos` mà `app/api` không được tự chạm (R74).
_PERSISTENCE_ATTRS = frozenset({"db_path", "_connect"})
#: Module mà `app/api` không được tự import (R74).
_PERSISTENCE_MODULE = "sqlite3"


def _constant_str(node: ast.AST) -> str | None:
    """Chuỗi hằng của một biểu thức, ghép được các mảnh `"db" + "_path"` (N2).

    Không có bước này thì `getattr(repos, "db" + "_path")` lọt qua phép so trên
    `Attribute.attr` — đúng cách viết mà bản quét chuỗi con cũ bỏ lọt.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _constant_str(node.left), _constant_str(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _persistence_reach(directory: pathlib.Path) -> list[str]:
    """Tên tệp + hành vi vi phạm ranh giới cổng, quét cả gói con.

    N2/RU-02: phân tích AST thay vì quét chuỗi con. Bản cũ vừa BỎ LỌT
    (`from sqlite3 import connect`; `getattr(repos, "db" + "_path")`) vừa BÁO
    NHẦM khi một tệp chỉ *nhắc* `db_path` trong docstring/comment. Ở đây chỉ
    `Import`/`ImportFrom`/`Attribute`/`getattr` thật mới bị tính — comment và
    docstring không sinh node tương ứng.
    """
    offenders: list[str] = []
    for py in sorted(directory.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if (alias.name == _PERSISTENCE_MODULE
                            or alias.name.startswith(_PERSISTENCE_MODULE + ".")):
                        offenders.append(f"{py.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if (module == _PERSISTENCE_MODULE
                        or module.startswith(_PERSISTENCE_MODULE + ".")):
                    offenders.append(f"{py.name}: from {module} import ...")
            elif isinstance(node, ast.Attribute):
                if node.attr in _PERSISTENCE_ATTRS:
                    offenders.append(f"{py.name}: attribute {node.attr}")
            elif isinstance(node, ast.Subscript):
                # F4: truy cập bằng KHOÁ (`repos.__dict__["db_path"]`,
                # `vars(repos)["_connect"]`). Bản quét chuỗi con cũ bắt được
                # dạng này; thiếu nhánh ở đây là lưới bị THU HẸP.
                key = _constant_str(node.slice)
                if key in _PERSISTENCE_ATTRS:
                    offenders.append(f"{py.name}: subscript {key}")
            elif isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Name) and func.id == "getattr"
                        and len(node.args) >= 2):
                    name = _constant_str(node.args[1])
                    if name in _PERSISTENCE_ATTRS:
                        offenders.append(f"{py.name}: getattr {name}")
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
    assert sorted(o.split(": ", 1)[1] for o in offenders) == [
        "attribute _connect", "attribute db_path", "import sqlite3",
    ], offenders


def test_persistence_guard_catches_from_sqlite3_import(tmp_path):
    """N2/RU-02 · dạng import mà bản quét chuỗi con BỎ LỌT: `from sqlite3 import`."""
    (tmp_path / "rogue.py").write_text(
        "from sqlite3 import connect\n"
        "conn = connect('app.db')\n",
        encoding="utf-8",
    )
    assert _persistence_reach(tmp_path) == ["rogue.py: from sqlite3 import ..."]


def test_persistence_guard_catches_a_concatenated_getattr(tmp_path):
    """N2/RU-02 · `getattr(repos, "db" + "_path")` — chuỗi con không thấy, AST thấy."""
    (tmp_path / "rogue.py").write_text(
        'path = getattr(repos, "db" + "_path")\n',
        encoding="utf-8",
    )
    assert _persistence_reach(tmp_path) == ["rogue.py: getattr db_path"]


def test_persistence_guard_catches_a_keyed_reach(tmp_path):
    """N2/RU-02 + F4 · `repos.__dict__["db_path"]` và `vars(repos)["db" + "_connect"]`.

    Bản quét CHUỖI CON cũ bắt được cả hai dạng này (nó thấy `db_path` / `_connect(`
    trong mã nguồn), nên khi RU-02 chuyển sang AST mà thiếu nhánh `Subscript`
    thì lưới bị THU HẸP: truy cập bằng khoá lọt sạch. Bài này giữ đúng độ rộng cũ.
    """
    (tmp_path / "rogue.py").write_text(
        'path = repos.__dict__["db_path"]\n'
        'conn = vars(repos)["_connect"]\n'
        'other = repos.__dict__["db" + "_path"]\n',
        encoding="utf-8",
    )
    offenders = _persistence_reach(tmp_path)
    assert sorted({o.split(": ", 1)[1] for o in offenders}) == [
        "subscript _connect", "subscript db_path",
    ], offenders
    assert len(offenders) == 3, (
        f"khoá ghép mảnh (`'db' + '_path'`) cũng phải bị bắt: {offenders}"
    )


def test_persistence_guard_ignores_a_docstring_that_merely_says_db_path(tmp_path):
    """N2/RU-02 · chỉ NHẮC `db_path` trong docstring/comment thì KHÔNG phải vi phạm.

    Bản quét chuỗi con báo nhầm tệp này (đo được: `comment.py: db_path` → 1
    offender), nên lưới cũ vừa thủng vừa ồn.
    """
    (tmp_path / "comment.py").write_text(
        '"""Tệp này chỉ nhắc db_path trong docstring, không hề chạm tệp SQLite."""\n'
        "# comment cũng nhắc db_path và _connect(\n"
        "VALUE = 1\n",
        encoding="utf-8",
    )
    assert _persistence_reach(tmp_path) == []


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


# --------------------------------------------------------------------------
# C-1 / API-01: tên tệp client gửi lên phải DÙNG ĐƯỢC trên hệ tệp này
#
# `safe_basename` chỉ cắt đường dẫn, nên `a*b?.mp4` đi thẳng vào `open()` (500)
# và `CON` biến thành thiết bị console: `open("CON", "rb")` chặn VÔ HẠN, trên
# event loop, nên cả server đứng. Hai nhóm test ở đây khoá cả hai nửa: vị từ
# từ chối (unit) và route thật trả 4xx kịp thời (tích hợp).
# --------------------------------------------------------------------------

#: Ký tự nằm NGOÀI bộ cho phép: nhóm Windows-illegal, ký tự điều khiển, và các
#: ký tự "hợp lệ trên POSIX nhưng không mở được thành tệp ở đây".
#:
#: A1 (đo được): bộ cho phép cũ là `[A-Za-z0-9._-]`, nên `ảnh.mp4` và
#: `Zh-请您欣赏.ogg` bị `POST /api/sources/upload` trả **422** — chặn đúng người
#: dùng tiếng Trung/tiếng Việt ở cửa vào. Chữ có dấu và chữ Hán nay NẰM TRONG bộ
#: cho phép (xem `_UNICODE_FILENAMES`); bảng từ chối dưới đây chỉ còn những thứ
#: thật sự không mở được: ký tự điều khiển, `< > : " | ? *`, khoảng trắng và
#: ngoặc. `ảnh.mp4` đã được CHUYỂN sang bảng hợp lệ, không phải bị xoá.
_UNSAFE_FILENAMES = [
    "a*b.mp4", "a?b.mp4", "a|b.mp4", "a<b.mp4", "a>b.mp4", 'a"b.mp4',
    "ab:c.mp4", "a.b:c.mp4", "a\x01b.mp4", "a b.mp4", "a(b).mp4", "a[b].mp4",
]

#: Tên KHÔNG phải ASCII phải đi qua nguyên vẹn (A1). Đây là tên tệp thật của
#: người dùng Việt/Trung, không phải đầu vào tấn công.
_UNICODE_FILENAMES = [
    "ảnh.mp4",                      # tiếng Việt có dấu (NFC)
    "bài-giảng-01.mp4",
    "đường-dẫn.wav",
    "Zh-请您欣赏.ogg",               # tên THẬT của clip Wikimedia ở `_realpipe/`
    "日本語の音声.m4a",
    "中文-音频.wav",
]

#: Thiết bị dành riêng của Windows: trần, có đuôi, và HOA/thường trộn — Windows
#: so khớp không phân biệt hoa/thường và bỏ qua phần mở rộng.
_RESERVED_DEVICE_FILENAMES = [
    "CON", "con", "Con", "CON.mp4", "con.mp4", "Con.TXT", "CON.tar.gz",
    "PRN", "prn.wav", "AUX", "aux.mp4", "NUL", "nul.mp4",
    "COM1", "com1", "COM1.mp4", "COM9", "com9.wav",
    "LPT1", "lpt1", "LPT1.mp4", "LPT9", "lpt9.wav",
]

#: Windows cắt khoảng trắng/dấu chấm cuối tên, nên `x.mp4.` mở ra `x.mp4`:
#: tên gửi lên và tên trên đĩa không còn là một.
_TRAILING_DOT_OR_SPACE_FILENAMES = ["trailing.", "trailing ", "x.mp4."]

_REJECTED_FILENAMES = (
    _UNSAFE_FILENAMES + _RESERVED_DEVICE_FILENAMES + _TRAILING_DOT_OR_SPACE_FILENAMES
)


@pytest.mark.parametrize("name", _UNSAFE_FILENAMES)
def test_safe_basename_rejects_characters_that_are_not_safe_on_disk(name):
    """Bộ ký tự hẹp: `* ? | < > : "` nổ 500 trong `open()` (đã đo)."""
    from app.domain.paths import InvalidBasename, safe_basename

    with pytest.raises(InvalidBasename) as excinfo:
        safe_basename(name)
    assert "tên tệp" in str(excinfo.value)


@pytest.mark.parametrize("name", _RESERVED_DEVICE_FILENAMES)
def test_safe_basename_rejects_windows_reserved_device_names(name):
    """`open("CON", "rb")` không mở tệp mà mở THIẾT BỊ console và chặn vô hạn."""
    from app.domain.paths import InvalidBasename, safe_basename

    with pytest.raises(InvalidBasename) as excinfo:
        safe_basename(name)
    assert "tên tệp" in str(excinfo.value)


@pytest.mark.parametrize("name", _TRAILING_DOT_OR_SPACE_FILENAMES)
def test_safe_basename_rejects_a_trailing_dot_or_space(name):
    from app.domain.paths import InvalidBasename, safe_basename

    with pytest.raises(InvalidBasename) as excinfo:
        safe_basename(name)
    assert "tên tệp" in str(excinfo.value)


def test_safe_basename_keeps_every_legitimate_name():
    """Siết tên KHÔNG được làm rơi tên thật, `None` hay phép cắt đường dẫn."""
    from app.domain.paths import safe_basename

    assert safe_basename("bai-giang.mp4") == "bai-giang.mp4"
    assert safe_basename("bai_giang-01.tar.gz") == "bai_giang-01.tar.gz"
    assert safe_basename(r"C:\media\x.mp4") == "x.mp4"
    assert safe_basename("a/b/x.mp4") == "x.mp4"
    assert safe_basename(None) == "upload.bin"
    assert safe_basename(None, fallback="khac.bin") == "khac.bin"


def test_safe_basename_tu_choi_moi_dau_hai_cham_ke_ca_tien_to_giong_o_dia():
    """`a:b.mp4` bi TU CHOI, khong bi cat thanh `b.mp4`.

    🔴 BAI CU DOI DIEU NGUOC LAI, VA NO SAI — do duoc, khong doan:

        >>> pathlib.PurePath("a:b.mp4")
        .name='a:b.mp4'  .drive=''  .parts=('a:b.mp4',)
        >>> pathlib.PurePath("C:\\media\\x.mp4".replace("\\","/"))
        .name='x.mp4'    .drive=''  .parts=('C:', 'media', 'x.mp4')

    Docblock cu khang dinh "`a:b.mp4` la o dia `a:` + ten `b.mp4` voi
    `pathlib`". Tren Linux dieu do SAI: `.drive` la `''`, `.name` giu nguyen
    `a:b.mp4`. `PurePath` chi tach o dia khi he dieu hanh la Windows; san pham
    chay trong Docker Linux.

    Va quan trong hon: `"ab:c.mp4"` nam trong `_UNSAFE_FILENAMES` ngay trong
    tep nay va PHAI nem `InvalidBasename`. Neu bai cu dung thi mot trong hai
    bai phai sai — khong the vua tu choi `ab:c.mp4` vua cat `a:b.mp4` thanh
    `b.mp4` bang cung mot quy tac `:`.

    `safe_basename` tu choi MOI dau hai cham, khong phu thuoc nen tang: `:`
    lam `open()` nem `OSError` tren Windows va la ky tu khong an toan o moi
    noi. Do truc tiep ba ten:

        'a:b.mp4'   -> NEM: ten tep chua ky tu khong an toan: ':' 
        'x:y.mp4'   -> NEM
        'ab:c.mp4'  -> NEM

    Con duong dan Windows THAT (`C:\\media\\x.mp4`) van dung: `.parts` tach
    `'C:'` thanh mot thanh phan rieng va `.name` la `'x.mp4'`, nen no di qua
    nhu moi thanh phan duong dan khac — do la hanh vi repo da chot.
    """
    from app.domain.paths import InvalidBasename, safe_basename

    for ten in ("a:b.mp4", "x:y.mp4", "ab:c.mp4"):
        with pytest.raises(InvalidBasename) as excinfo:
            safe_basename(ten)
        assert "tên tệp" in str(excinfo.value), ten

    # Duong dan Windows that van bi cat dung — day la dieu bai cu MUON noi.
    assert safe_basename("C:\\media\\x.mp4") == "x.mp4"



# --------------------------------------------------------------------------
# A1: tên tệp KHÔNG phải ASCII (tiếng Trung, tiếng Việt có dấu) phải qua được.
#
# ĐO ĐƯỢC trước bản vá: `POST /api/sources/upload` với `Zh-请您欣赏.ogg` trả
# **422** `tên tệp chứa ký tự không an toàn` — với một sản phẩm Trung -> Việt thì
# đó là chặn đúng người dùng ở cửa vào. Bản vá KHÔNG nới đường thoát: vẫn cắt
# thành phần đường dẫn và vẫn từ chối mọi ký tự không mở được thành tệp.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", _UNICODE_FILENAMES)
def test_safe_basename_keeps_a_non_ascii_name_whole(name):
    """A1: chữ có dấu/Hán là tên HỢP LỆ, không phải "ký tự không an toàn"."""
    from app.domain.paths import safe_basename

    assert safe_basename(name) == name


def test_safe_basename_still_strips_the_path_off_a_non_ascii_name():
    """A1 KHÔNG được mở lại đường thoát: tên Unicode vẫn bị cắt về tên trần."""
    from app.domain.paths import InvalidBasename, safe_basename

    assert safe_basename("请您欣赏/../../../thoat.ogg") == "thoat.ogg"
    assert safe_basename("../../中文/请您欣赏.ogg") == "请您欣赏.ogg"
    assert safe_basename(r"..\..\请您欣赏.ogg") == "请您欣赏.ogg"
    with pytest.raises(InvalidBasename):
        safe_basename("中文/..")


def test_upload_accepts_a_non_ascii_filename_and_keeps_it_inside_media(client):
    """A1 RED TRƯỚC: ca này trả **422**. Sau bản vá: **201** + tệp nằm trong
    `media/`, tên theo nội dung (16 hex + đuôi của tên gốc), byte nguyên vẹn."""
    import hashlib

    payload = b"du-lieu-tieng-trung-that"
    resp = client.post("/api/sources/upload",
                       files={"file": ("Zh-请您欣赏.ogg", io.BytesIO(payload), "audio/ogg")},
                       data={"lang": "zh"})
    assert resp.status_code == 201, resp.text
    media = client.tmp / "media"
    stored = pathlib.Path(resp.json()["source"]["media_path"])
    assert stored.parent == media, f"tệp phải nằm trong media/: {stored}"
    assert stored.name == f"{hashlib.sha256(payload).hexdigest()[:16]}.ogg"
    assert stored.read_bytes() == payload
    assert resp.json()["source"]["origin"] == "Zh-请您欣赏.ogg", (
        "tên gốc của người dùng phải được giữ trong `sources.origin`"
    )


def test_upload_writes_no_path_outside_media_for_a_non_ascii_path_name(client, monkeypatch):
    """A1 + containment: tên Unicode có `../` vẫn chỉ được GHI trong `media/`.

    Bám vào ĐƯỜNG DẪN THẬT của lần mở ghi đầu tiên (như bài chặn event loop ở
    trên), không bám vào tệp cuối: tệp cuối do `Path.replace` đổi tên theo nội
    dung, nên một bản vá bỏ phép cắt đường dẫn vẫn để tệp cuối nằm trong `media/`
    trong khi lần GHI ĐẦU đã rơi ra ngoài. Mutant "trả thẳng tên client gửi lên"
    chết ở chính khẳng định `parent == media` này.
    """
    import builtins

    media = (client.tmp / "media").resolve()
    opened: list[pathlib.Path] = []
    real_open = builtins.open

    def spy_open(file, *args, **kwargs):
        if isinstance(file, pathlib.Path) and "w" in (args[0] if args else kwargs.get("mode", "r")):
            opened.append(file)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    resp = client.post(
        "/api/sources/upload",
        files={"file": ("请您欣赏/../../../thoat-ra-ngoai.ogg",
                        io.BytesIO(b"x" * 32), "audio/ogg")},
        data={"lang": "zh"})
    assert resp.status_code == 201, resp.text
    assert opened, "route upload phải mở một tệp trong media/ để ghi"
    for path in opened:
        assert path.resolve().parent == media, f"ghi ra ngoài media/: {path}"
    assert not (client.tmp / "thoat-ra-ngoai.ogg").exists()
    assert not (client.tmp.parent / "thoat-ra-ngoai.ogg").exists()
    assert resp.json()["source"]["origin"] == "请您欣赏/../../../thoat-ra-ngoai.ogg"


#: Trần của MỘT thành phần đường dẫn trên NTFS là 255 ký tự. Tên 302 ký tự toàn
#: ký tự an toàn đi lọt qua cả ba phép kiểm cũ (không kết thúc bằng dấu chấm,
#: không phải thiết bị, khớp `_SAFE_CHARS`) rồi làm `open()` ném `OSError` ở tận
#: `_copy_upload` ⇒ route upload trả **500** cho một lỗi ĐẦU VÀO. Cùng lớp lỗi mà
#: `a*b.mp4` và `CON` đã trả giá (C-1/API-01): hỏng ở `open()` thay vì 422.
_OVERLONG_FILENAME = "a" * 302

#: Tên ĐÚNG BẰNG trần: phải đi qua. Không có vế này thì một trần đặt lệch
#: (`>= 255`, hay `> 200`) vẫn làm bài trên xanh.
_MAX_LENGTH_FILENAME = "a" * 255


def test_safe_basename_rejects_a_name_longer_than_the_filesystem_limit():
    """Tên dài quá trần của hệ tệp là lỗi ĐẦU VÀO, không phải lỗi máy chủ.

    Đo được trước bản vá: route upload trả 500 (xem
    `test_upload_answers_422_for_an_overlong_filename` ngay dưới).
    """
    from app.domain.paths import InvalidBasename, safe_basename

    with pytest.raises(InvalidBasename) as excinfo:
        safe_basename(_OVERLONG_FILENAME)
    assert "tên tệp" in str(excinfo.value)


def test_safe_basename_keeps_a_name_exactly_at_the_filesystem_limit():
    """Vế đối chứng của trần: 255 ký tự là tên HỢP LỆ, không được từ chối."""
    from app.domain.paths import safe_basename

    assert safe_basename(_MAX_LENGTH_FILENAME) == _MAX_LENGTH_FILENAME



async def _post_upload(media_root: pathlib.Path, filename: str,
                       payload: bytes = b"x") -> int:
    """Upload qua ĐÚNG app ASGI, trong tiến trình; trả về mã trạng thái.

    `raise_app_exceptions=False`: lỗi máy chủ phải hiện ra thành 500 để test
    khẳng định được "4xx, không phải 500" thay vì chỉ thấy traceback.
    """
    import httpx

    repos = SqliteRepos(media_root / "upload-probe.db", clock=SystemClock())
    repos.init_schema()
    app = create_app(repos=repos, specs=_engine_specs(),
                     media_dir=media_root / "media", out_dir=media_root / "out")
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/sources/upload",
            files={"file": (filename, payload, "video/mp4")},
            data={"lang": "zh"},
        )
    return resp.status_code


def _upload_status_within(media_root: pathlib.Path, filename: str,
                          timeout: float = 5.0) -> int:
    """Gọi upload trong MỘT LUỒNG DAEMON có trần thời gian.

    Không dùng `client` fixture cho nhóm ca này: `TestClient.__exit__` phải join
    đúng event loop, nên nếu request treo thì teardown treo luôn cả suite. Một
    luồng daemon thì bỏ rơi được, nên "treo vô hạn" trở thành "test đỏ".
    """
    import threading

    result: dict = {}

    def run() -> None:
        try:
            result["status"] = asyncio.run(_post_upload(media_root, filename))
        except BaseException as exc:  # noqa: BLE001 - chuyển nguyên vẹn sang luồng test
            result["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        pytest.fail(f"upload(filename={filename!r}) không trả về trong {timeout}s — "
                    "request đang chặn event loop (đúng ca `CON` của C-1)")
    if "error" in result:
        raise result["error"]
    return result["status"]


@pytest.mark.parametrize("name", _REJECTED_FILENAMES)
def test_upload_answers_422_for_an_unsafe_filename_and_never_hangs(tmp_path, name):
    """Lỗi ĐẦU VÀO phải là 422 — không 500, và tuyệt đối không treo (C-1)."""
    status = _upload_status_within(tmp_path, name)
    assert status == 422, f"filename={name!r} -> {status}, phải là 422"


@pytest.mark.parametrize("name", ["CON", "con.mp4"])
def test_upload_answers_422_promptly_for_a_reserved_device_name(tmp_path, name):
    """Ca nặng nhất của C-1, đo riêng: `CON` từng không bao giờ trả về."""
    status = _upload_status_within(tmp_path, name, timeout=5.0)
    assert status == 422, f"filename={name!r} -> {status}, phải là 422"


def test_upload_answers_422_for_an_overlong_filename(tmp_path):
    """Trần độ dài qua ĐƯỜNG THẬT: 302 ký tự an toàn ⇒ 422, không phải 500.

    Đi qua `_upload_status_within` — hàm này gọi `_post_upload`, tức app ASGI
    THẬT với `raise_app_exceptions=False`, trong một luồng daemon có trần thời
    gian — chứ không gọi `safe_basename` trần: thứ hỏng trước bản vá là mã TRẠNG
    THÁI của route, `open()` ném `OSError` trong `_copy_upload` và FastAPI biến
    nó thành 500.
    """
    status = _upload_status_within(tmp_path, _OVERLONG_FILENAME)
    assert status == 422, f"filename dài {len(_OVERLONG_FILENAME)} -> {status}, phải là 422"


def test_upload_still_accepts_a_normal_filename(client):
    """Siết tên không được chặn tên thật: 201 + tên theo nội dung như cũ.

    API-06 (R40): spec §8.1 ghi `<sha256>`, code cố ý rút còn **16 hex**. Hai
    khẳng định dưới đây ghim đúng hợp đồng đó: tên tệp là tiền tố 16 ký tự của
    digest THẬT, và dài ĐÚNG 16 (không phải 8, không phải 64). Bỏ `[:16]` hoặc
    đổi độ dài là đỏ.
    """
    import hashlib

    payload = b"du-lieu-that"
    resp = client.post("/api/sources/upload",
                       files={"file": ("bai_giang-01.mp4", io.BytesIO(payload), "video/mp4")},
                       data={"lang": "zh"})
    assert resp.status_code == 201, resp.text
    stored = pathlib.Path(resp.json()["source"]["media_path"])
    assert stored.parent == client.tmp / "media"
    assert stored.name == f"{hashlib.sha256(payload).hexdigest()[:16]}.mp4"
    assert len(stored.stem) == 16, (
        f"tên theo nội dung phải là 16 hex (quyết định của API-06), thấy "
        f"{stored.stem!r} dài {len(stored.stem)}"
    )
    assert stored.read_bytes() == payload


def test_upload_route_keeps_its_blocking_io_off_the_event_loop(client, monkeypatch):
    """I-1 / API-01(b): bản tương đương của test route media
    (`test_api_media_range.py::test_the_media_endpoint_is_sync_so_fastapi_runs_it_in_a_threadpool`).

    Route là `async def`, nên `open()`/`write()`, `sha256_file` và `Path.replace`
    chạy thẳng trong thân route là CHẶN event loop: một tệp 2 GB giữ server đứng
    suốt lượt băm và `/api/jobs/stream` không gửi được gì.

    Test bám vào LUỒNG THẬT thay vì chữ ký: ghi lại luồng của (a) lần MỞ GHI tệp
    trong `media/` (chế độ `wb`, tức vòng ghi), (b) `sha256_file`, (c) `Path.replace`,
    rồi so với luồng chạy thân route (`_safe_name` được gọi ngay trong thân
    `async def`). Đẩy bất kỳ phần nào trở lại event loop là đỏ, và mỗi phần có
    một khẳng định riêng nên thông báo đỏ chỉ đúng thủ phạm.
    """
    import builtins
    import threading

    from app.api import routes_sources
    from app.pipeline import ingest

    media_dir = client.tmp / "media"
    seen: dict = {}
    real_open = builtins.open
    real_safe = routes_sources._safe_name
    real_hash = ingest.sha256_file
    real_replace = pathlib.Path.replace

    def spy_open(file, *args, **kwargs):
        if isinstance(file, pathlib.Path) and file.parent == media_dir:
            mode = args[0] if args else kwargs.get("mode", "r")
            seen.setdefault(f"open:{mode}", set()).add(threading.get_ident())
        return real_open(file, *args, **kwargs)

    def spy_safe(*args, **kwargs):
        seen["route"] = threading.get_ident()
        return real_safe(*args, **kwargs)

    def spy_hash(*args, **kwargs):
        seen["hash"] = threading.get_ident()
        return real_hash(*args, **kwargs)

    def spy_replace(self, target):
        seen["replace"] = threading.get_ident()
        return real_replace(self, target)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(routes_sources, "_safe_name", spy_safe)
    monkeypatch.setattr(ingest, "sha256_file", spy_hash)
    monkeypatch.setattr(pathlib.Path, "replace", spy_replace)

    resp = client.post("/api/sources/upload",
                       files={"file": ("bai-giang.mp4", io.BytesIO(b"du-lieu"), "video/mp4")},
                       data={"lang": "zh"})
    assert resp.status_code == 201, resp.text

    # `open:rb` (lần ĐỌC lại để băm) cũng được ghi, nhưng khẳng định của nó nằm
    # ở chân `hash`; ở đây chỉ đòi ba chân phải có mặt.
    assert {"open:wb", "route", "hash", "replace"} <= set(seen), seen
    assert seen["open:wb"], "route upload không mở tệp nào trong media/ để ghi"
    for what in ("open:wb", "hash", "replace"):
        idents = seen[what] if what.startswith("open:") else {seen[what]}
        assert seen["route"] not in idents, (
            f"{what} chạy CÙNG luồng với thân route `async def` => đang chặn event loop")
