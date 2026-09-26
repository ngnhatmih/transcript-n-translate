"""Task 15: duyệt transcript cho Workspace 2 + route export ĐÚNG hình dạng spec.

Spec §11 ghi `GET /api/export/{translation_id}?format=&bilingual=`, còn Giai đoạn 1a
đã ship `POST /api/export` + `GET /api/export/{job_id}/download`. Hai đường phải
không trôi khỏi nhau — cùng `artifact_name()` nên cùng TÊN TỆP — và ba bài
`test_both_export_routes_*` dưới đây ghim điều đó bằng so sánh nội dung.

Bốn chỗ khác brief, và lý do:

* **Fixture.** `monkeypatch.setenv("PHUDE_DATA", …)` của brief chạy SAU
  `from app import main`, mà `app/config.py` đọc biến môi trường lúc IMPORT, nên nó
  KHÔNG chuyển hướng được đường dẫn: `build_components()` sẽ mở DB THẬT của repo.
  Fixture ở đây chép khuôn của `tests/test_api_sources.py` — vá hằng số của
  `app.config` (`ensure_dirs()` closure trên biến của chính module đó, nên vá mỗi
  tên đã import vào `main` là KHÔNG đủ) LẪN các tên đã import vào `main` — và
  `_assert_repo_data_dirs_untouched` biến lời hứa "không tạo `data/` thật" thành
  thứ chạy được.
* **`wired` là TUPLE của `build_components()`**, không bọc lại: `build_app(wired)`
  của brief là `TypeError` (hàm cần 5 tham số) và tuple không có `.repos`.
* **Job của đường CŨ tạo bằng `POST /api/jobs`.** `POST /api/export` cố tình KHÔNG
  nhận `translations` (xem `test_api_transcripts.py::
  test_download_serves_the_pipeline_artifact_name`): bản dịch là việc của job
  `translate`, và `ExportHandler` đọc `payload["translations"]` từ HÀNG JOB. Mở
  rộng hợp đồng đầu vào của route đang chạy chỉ để vừa một bài test là đúng thứ
  hướng dẫn "đừng đổi chữ ký hàm đang chạy" cấm, nên đường CŨ ở đây đi qua ĐÚNG
  đường công khai dành cho payload có bản dịch.
* **Không dựng `Segment(...)` để suy ra đoạn dịch.** Đoạn NGUỒN của fixture là dữ
  liệu đầu vào (mọi test trong repo đều seed như vậy), còn đoạn DỊCH được suy bằng
  `dataclasses.replace(s, text=…)` — đúng cách `adapters/mt/opus_mt.py` sinh ra nó,
  nên không nuốt trường nào.
"""
from __future__ import annotations

import dataclasses
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.domain.models import Segment


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


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """`build_components()` + `build_app()` THẬT; chỉ đường dẫn đĩa bị chuyển đi.

    Trả `(client, repos, out_dir, worker)` — các phần tử NGUYÊN BẢN của
    `build_components()`, không bọc lại. Registry vẫn là `registry.json` THẬT và
    engine vẫn là adapter thật mà `_build_mt_engines` dựng; thứ duy nhất bị thay ở
    đây là đường dẫn đĩa và câu trả lời của phép dò Ollama (ghim `set()`, để suite
    không phụ thuộc việc máy đang chạy có pull model nào).
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
    monkeypatch.setattr(main, "ollama_available", lambda *a, **k: set())

    repos, specs, worker, broker, mt_engines = main.build_components()
    _assert_repo_data_dirs_untouched(before)
    app = main.build_app(repos, specs, worker, broker, mt_engines)

    with TestClient(app) as client:
        client.repos = repos            # type: ignore[attr-defined]
        yield client, repos, app.state.dirs["out"], worker


#: Hai đoạn nguồn + hai bản dịch TƯƠNG ỨNG. Bản dịch suy bằng `dataclasses.replace`
#: từ chính đoạn nguồn (giữ nguyên `i`/`start`/`end`, chỉ đổi `text`) — cùng cách
#: `adapters/mt/opus_mt.py` sinh đoạn dịch.
_SOURCE = [Segment(i=1, start=0.0, end=1.0, text="你好"),
           Segment(i=2, start=1.0, end=2.0, text="再见")]
_VIETNAMESE = ["Xin chào", "Tạm biệt"]


def _ready(repos) -> tuple[int, int]:
    """Một source + transcript + một bản dịch `done`, trả `(transcript_id, tr_id)`."""
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh",
                               segments=list(_SOURCE))
    translated = [dataclasses.replace(seg, text=text)
                  for seg, text in zip(_SOURCE, _VIETNAMESE)]
    tr_id = repos.add_translation(
        transcript_id=tid, transcript_version=1, engine="opus-mt",
        target_lang="vi", segments=translated, prompt_version="opus-p1",
        status="done")
    return tid, tr_id


def _translation_texts(repos, translation_id: int) -> list[str]:
    """Bản dịch ĐÃ LƯU, dưới dạng danh sách text mà `payload` job export mang."""
    return [s.text for s in repos.get_translation(translation_id).segments]


def _run_the_old_route(c, repos, worker, tid: int, translations: list[str], *,
                       fmt: str = "srt", bilingual: bool = False) -> str:
    """Chạy ĐƯỜNG CŨ trọn vẹn: xếp job -> worker -> handler -> tải về.

    Trả NỘI DUNG tải được từ `GET /api/export/{job_id}/download`. Job mang ĐÚNG
    danh sách `translations` đã lưu của bản dịch, nên nội dung dưới đây là nội dung
    của CÙNG một bản dịch mà route spec xuất.
    """
    created = c.post("/api/jobs", json={
        "workspace": 1, "type": "export",
        "payload": {"transcript_id": tid, "format": fmt, "bilingual": bilingual,
                    "stem": f"transcript-{tid}", "translations": translations},
    })
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    for _ in range(50):                      # worker chạy nền; chờ ngắn, có trần
        if repos.get_job(job_id).state in ("done", "failed"):
            break
        worker.tick()
    job = repos.get_job(job_id)
    assert job.state == "done", job.error

    dl = c.get(f"/api/export/{job_id}/download")
    assert dl.status_code == 200, dl.text
    return dl.text


# ---------------------------------------------------------------------------
# POST /api/transcripts/{id}/approve — bàn giao sang Workspace 2
# ---------------------------------------------------------------------------

def test_approve_moves_transcript_to_workspace_2(wired):
    c, repos, _out, _worker = wired
    tid, _ = _ready(repos)

    r = c.post(f"/api/transcripts/{tid}/approve")

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "translated"
    assert repos.get_transcript(tid).status == "translated"


def test_approve_unknown_transcript_is_404(wired):
    c, _repos, _out, _worker = wired
    assert c.post("/api/transcripts/999/approve").status_code == 404


# ---------------------------------------------------------------------------
# GET /api/export/{translation_id} — hình dạng spec §11
# ---------------------------------------------------------------------------

def test_export_by_translation_returns_srt(wired):
    c, repos, _out, _worker = wired
    _, tr_id = _ready(repos)

    r = c.get(f"/api/export/{tr_id}?format=srt")

    assert r.status_code == 200, r.text
    assert "-->" in r.text
    assert "Xin chào" in r.text and "Tạm biệt" in r.text
    # Cùng MIME với đường cũ (`MEDIA_TYPES` của pipeline, không phải text/plain):
    # `application/x-subrip` là thứ trình phát nhận ra phụ đề.
    assert r.headers["content-type"].startswith("application/x-subrip")


def test_export_bilingual_contains_source_and_translation(wired):
    c, repos, _out, _worker = wired
    _, tr_id = _ready(repos)

    r = c.get(f"/api/export/{tr_id}?format=srt&bilingual=1")

    assert r.status_code == 200, r.text
    assert "你好" in r.text and "Xin chào" in r.text


def test_export_without_bilingual_omits_the_source(wired):
    """Mặc định `bilingual=0` là CHỈ bản dịch — vế đối chứng của bài trên."""
    c, repos, _out, _worker = wired
    _, tr_id = _ready(repos)

    r = c.get(f"/api/export/{tr_id}?format=srt")

    assert r.status_code == 200, r.text
    assert "你好" not in r.text


def test_export_defaults_to_srt(wired):
    """`format` có mặc định `srt` (spec §11 ghi `?format=` là tuỳ chọn)."""
    c, repos, _out, _worker = wired
    _, tr_id = _ready(repos)

    default = c.get(f"/api/export/{tr_id}")
    explicit = c.get(f"/api/export/{tr_id}?format=srt")

    assert default.status_code == 200, default.text
    assert default.text == explicit.text


def test_export_accepts_an_uppercase_format_like_the_old_route(wired):
    """`?format=SRT` là CÙNG định dạng, không phải 422.

    `create_export` (đường cũ) hạ `payload.format` xuống chữ thường trước khi kiểm;
    route spec làm y hệt, nên hai đường nhận cùng một tập đầu vào.
    """
    c, repos, _out, _worker = wired
    _, tr_id = _ready(repos)

    upper = c.get(f"/api/export/{tr_id}?format=SRT")
    lower = c.get(f"/api/export/{tr_id}?format=srt")

    assert upper.status_code == 200, upper.text
    assert upper.text == lower.text
    assert upper.headers["content-type"].startswith("application/x-subrip")


def test_export_rejects_bad_format_with_422(wired):
    c, repos, _out, _worker = wired
    _, tr_id = _ready(repos)
    assert c.get(f"/api/export/{tr_id}?format=pdf").status_code == 422


def test_export_checks_the_format_before_looking_up_the_translation(wired):
    """Định dạng sai là lỗi ĐẦU VÀO, phải báo trước cả khi id không tồn tại.

    Cùng thứ tự với route cũ (`create_export` kiểm `fmt` rồi mới tra transcript):
    đảo lại thì `?format=pdf` trên một id lạ trả 404 và client tưởng id mới là thứ
    sai.
    """
    c, _repos, _out, _worker = wired
    assert c.get("/api/export/999?format=pdf").status_code == 422


def test_export_unknown_translation_is_404(wired):
    c, _repos, _out, _worker = wired
    assert c.get("/api/export/999?format=srt").status_code == 404


def test_export_with_segment_counts_out_of_step_is_409(wired):
    """Bản dịch không còn khớp bản gốc (transcript bị sửa sau khi dịch).

    `_assert_lengths` của `domain/subtitle_format.py` ném `ValueError`, tức một
    route không phòng bị sẽ trả 500 cho một ca DỮ LIỆU hoàn toàn bình thường. 409
    cũng đúng lớp với đường cũ: ở đó handler ném cùng `ValueError` nên job `failed`
    và `GET /api/export/{job_id}/download` trả 409 ("job chưa xong").
    """
    c, repos, _out, _worker = wired
    tid, tr_id = _ready(repos)
    repos.update_transcript_segments(
        tid, [*_SOURCE, Segment(i=3, start=2.0, end=3.0, text="第三段")])

    assert c.get(f"/api/export/{tr_id}?format=srt").status_code == 409


# ---------------------------------------------------------------------------
# Hai đường KHÔNG được trôi khỏi nhau
# ---------------------------------------------------------------------------

def test_both_export_routes_produce_the_same_bytes(wired):
    """Route cũ và route spec phải cho CÙNG nội dung cho CÙNG một bản dịch."""
    c, repos, _out, worker = wired
    tid, tr_id = _ready(repos)

    spec_route = c.get(f"/api/export/{tr_id}?format=srt").text
    old_route = _run_the_old_route(c, repos, worker, tid,
                                   _translation_texts(repos, tr_id))

    assert spec_route == old_route


@pytest.mark.parametrize("fmt,bilingual", [("srt", True), ("vtt", False),
                                           ("ass", True)])
def test_both_export_routes_agree_for_every_format(wired, fmt, bilingual):
    """Cùng bất biến cho CẢ BA định dạng, và cho cả hai chế độ song ngữ.

    Không thừa: `to_srt` tra bản dịch theo `n - 1` còn `to_vtt`/`to_ass` tra theo
    vị trí của `enumerate`, và `.vi` chỉ xuất hiện khi có bản dịch — ba định dạng
    là ba đường sinh nội dung khác nhau, không phải một đường lặp lại.
    """
    c, repos, _out, worker = wired
    tid, tr_id = _ready(repos)

    spec_route = c.get(
        f"/api/export/{tr_id}?format={fmt}&bilingual={int(bilingual)}").text
    old_route = _run_the_old_route(c, repos, worker, tid,
                                   _translation_texts(repos, tr_id),
                                   fmt=fmt, bilingual=bilingual)

    assert spec_route == old_route


def test_both_routes_write_byte_identical_files(wired):
    """Không chỉ cùng nội dung TRẢ VỀ: cùng TỆP trên đĩa, từng byte một.

    `Path.read_text()` dịch `\\r\\n` thành `\\n`, nên một route ghi bằng
    `Path.write_text()` mặc định (Windows: CRLF) vẫn cho ra nội dung "giống nhau"
    khi đọc lại — đúng lớp lỗi mà `pipeline/export.py::_write_utf8` ra đời để chặn.
    Bài này đọc BYTE THÔ, và xoá tệp trước khi gọi route spec để byte đọc sau
    CHẮC CHẮN do route spec ghi ra.
    """
    c, repos, out_dir, worker = wired
    tid, tr_id = _ready(repos)
    target = out_dir / f"transcript-{tid}.vi.srt"

    _run_the_old_route(c, repos, worker, tid, _translation_texts(repos, tr_id))
    from_handler = target.read_bytes()
    target.unlink()

    r = c.get(f"/api/export/{tr_id}?format=srt")

    assert r.status_code == 200, r.text
    from_spec_route = target.read_bytes()
    assert from_spec_route == from_handler
    assert b"\r\n" not in from_spec_route, "phải là LF, như `_write_utf8` của handler"
    assert from_spec_route.decode("utf-8") == r.text


def test_the_spec_route_materialises_the_same_artifact_name(wired):
    """Cùng `artifact_name()` ⇒ cùng TÊN TỆP, không chỉ cùng nội dung.

    Tên `transcript-<transcript_id>.vi.<fmt>` là tên mà `ExportHandler` ghi và
    `GET /api/export/{job_id}/download` đi tìm (nó tự tính lại từ payload job). Hai
    chỗ ghép tên bằng tay là hai chỗ trôi khỏi nhau — đó là lý do `artifact_name()`
    tồn tại, và bài này ghim route spec vào ĐÚNG nguồn đó.
    """
    c, repos, out_dir, worker = wired
    tid, tr_id = _ready(repos)

    r = c.get(f"/api/export/{tr_id}?format=srt")
    assert r.status_code == 200, r.text
    assert (out_dir / f"transcript-{tid}.vi.srt").is_file(), (
        sorted(p.name for p in out_dir.iterdir()))

    _run_the_old_route(c, repos, worker, tid, _translation_texts(repos, tr_id))

    # Đường cũ ghi CÙNG tệp đó, không phải một tệp thứ hai nằm cạnh.
    assert [p.name for p in out_dir.iterdir() if p.suffix == ".srt"] == [
        f"transcript-{tid}.vi.srt"]
