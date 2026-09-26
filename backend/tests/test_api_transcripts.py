"""Task 18: route xem/sửa transcript (tăng version -> đánh stale) + export.

Fixture và phép kiểm ở đây lấy NGUYÊN từ brief, trừ hai chỗ phải khác:

* test "stale" của brief tự dựng bản dịch bằng
  `with client.repos._connect() as conn:` — đúng thứ luật cứng của dự án cấm
  trong `app/` VÀ cũng là thứ `test_api_sources.py::_PERSISTENCE_REACH` cấm
  trong `app/api`: đi qua `Repos`, không mở tệp SQLite. Test này dùng
  `repos.add_translation()` trên cổng.
* export/download phải khớp tên tệp của `pipeline/export.py`. Handler ghi
  `<stem>.vi.<fmt>` khi có bản dịch, nên `_artifact_name()` là một hàm DÙNG
  CHUNG; test `test_download_serves_the_pipeline_artifact_name` khoá lại đúng
  chỗ đó (brief chỉ kiểm một payload KHÔNG có bản dịch nên không bao giờ chạm
  tới nhánh `.vi`).

Số đo CPS của fixture, tính bằng `reading_cps` (không đoán):

    đoạn 0 · 大家好 · 3 ký tự / 3,0 s = **1,00 CPS**
    đoạn 1 · 今天我们要聊的是人工智能 · 12 ký tự / 2,0 s = **6,00 CPS**
    đoạn 2 · 这个模型它其实…… · 9 ký tự / 3,0 s = **3,00 CPS**

`CPS_WARN = 20,0` nên ở ngưỡng mặc định **không đoạn nào** bị gắn cờ. Hạ ngưỡng
xuống **5,0** — nằm giữa 3,00 và 6,00 — thì đúng đoạn 1 bị gắn cờ.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.domain.models import Segment


@pytest.fixture()
def client(tmp_path):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    sid = repos.add_source(kind="file", origin="a.mp4", media_path="m", lang="zh")
    segments = [
        Segment(i=0, start=0.0, end=3.0, text="大家好"),
        Segment(i=1, start=3.0, end=5.0, text="今天我们要聊的是人工智能"),
        Segment(i=2, start=5.0, end=8.0, text="这个模型它其实……",
                no_speech_prob=0.8, suspect=True),
    ]
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo",
                               lang="zh", segments=segments)
    app = create_app(repos=repos, specs=[], media_dir=tmp_path / "m",
                     out_dir=tmp_path / "o")
    with TestClient(app) as c:
        c.repos = repos
        c.tid = tid
        c.tmp = tmp_path
        yield c


def test_get_transcript_returns_segments_and_version(client):
    body = client.get(f"/api/transcripts/{client.tid}").json()
    assert body["version"] == 1
    assert [s["text"] for s in body["segments"]] == ["大家好", "今天我们要聊的是人工智能", "这个模型它其实……"]
    assert body["segments"][2]["suspect"] is True


def test_patch_segments_bumps_version(client):
    body = client.get(f"/api/transcripts/{client.tid}").json()
    segments = body["segments"]
    segments[0]["text"] = "Chào mọi người"
    resp = client.patch(f"/api/transcripts/{client.tid}", json={"segments": segments})
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    assert client.get(f"/api/transcripts/{client.tid}").json()["segments"][0]["text"] == "Chào mọi người"


def test_patch_rejects_malformed_segment(client):
    resp = client.patch(f"/api/transcripts/{client.tid}",
                        json={"segments": [{"start": 0.0}]})
    assert resp.status_code == 422


def test_readability_endpoint_flags_long_line(client):
    """Số đo THẬT của fixture, tính bằng `reading_cps` (không đoán):

        đoạn 0 · 大家好 · 3 ký tự / 3,0 s = **1,00 CPS**
        đoạn 1 · 今天我们要聊的是人工智能 · 12 ký tự / 2,0 s = **6,00 CPS**
        đoạn 2 · 这个模型它其实…… · 9 ký tự / 3,0 s = **3,00 CPS**

    `CPS_WARN = 20,0` nên ở ngưỡng mặc định **không đoạn nào** bị gắn cờ và phép
    kiểm vô nghĩa. Hạ ngưỡng xuống **5,0** — nằm giữa 3,00 và 6,00 — thì đúng đoạn
    1 bị gắn cờ.
    """
    body = client.get(f"/api/transcripts/{client.tid}/readability",
                      params={"threshold": 5.0}).json()
    assert body["threshold"] == 5.0
    flagged = [item["i"] for item in body["too_fast"]]
    assert 1 in flagged, "đoạn 1 = 6,00 CPS phải vượt ngưỡng 5,0"
    assert 0 not in flagged, "đoạn 0 = 1,00 CPS không được vượt ngưỡng 5,0"


def test_approve_moves_status_to_reviewed(client):
    resp = client.post(f"/api/transcripts/{client.tid}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "reviewed"


def test_stale_flag_is_computed_not_stored(client):
    """Bản dịch dịch từ v1, transcript lên v3 -> phải báo lỗi thời."""
    client.repos.add_llm_call(job_id=None, engine="qwen2.5-7b", model_ref="m",
                              prompt_version="v1", tokens_in=1, tokens_out=1,
                              duration_ms=1, ok=True, error=None)
    client.repos.add_translation(transcript_id=client.tid, transcript_version=1,
                                 engine="qwen2.5-7b", target_lang="vi",
                                 segments=[], prompt_version="v1")
    body = client.get(f"/api/transcripts/{client.tid}").json()
    assert body["translations"][0]["stale"] is False, "v1 == v1 nên chưa lỗi thời"

    segments = body["segments"]
    segments[0]["text"] = "sửa"
    client.patch(f"/api/transcripts/{client.tid}", json={"segments": segments})

    body = client.get(f"/api/transcripts/{client.tid}").json()
    assert body["version"] == 2
    assert body["translations"][0]["stale"] is True
    # I-4: endpoint chi tiết transcript dùng CHUNG builder với
    # `/api/translations`, nên khoá ở đây là `transcript_version` + `status`.
    # Trước bản vá, chỗ này phát `translated_from_version` và KHÔNG có `status`,
    # nên cùng một hàng đọc ở hai endpoint cho hai hình dạng khác nhau.
    assert body["translations"][0]["transcript_version"] == 1
    assert body["translations"][0]["status"] == "queued"


def test_export_creates_job_and_download_serves_file(client):
    resp = client.post("/api/export", json={"transcript_id": client.tid,
                                            "format": "srt", "bilingual": False})
    assert resp.status_code == 201
    job = resp.json()
    assert job["type"] == "export"

    # chạy handler trực tiếp vì test này không chạy worker
    from app.pipeline.export import ExportHandler
    from app.domain.models import Job
    handler = ExportHandler(client.repos, out_dir=client.tmp / "o")
    handler.run(Job(id=job["id"], workspace=1, type="export", engine=None,
                    phase="export:-", payload=job["payload"]), lambda p, line: None)
    client.repos.set_job_state(job["id"], "running")
    client.repos.set_job_state(job["id"], "done")

    dl = client.get(f"/api/export/{job['id']}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/x-subrip"), (
        "SRT dùng MIME application/x-subrip (media_types['srt']), KHÔNG phải text/plain"
    )
    assert "1\n00:00:00,000 --> 00:00:03,000\n大家好" in dl.text


def test_export_rejects_unknown_format(client):
    resp = client.post("/api/export", json={"transcript_id": client.tid, "format": "docx"})
    assert resp.status_code == 422


def test_export_before_job_done_is_409(client):
    """409 vì TRẠNG THÁI job, không phải vì thiếu tệp.

    Phải chạy handler trước khi tải: nếu tệp chưa tồn tại thì 409 và 410 cùng
    cho ra "không tải được", và một route bỏ hẳn phép kiểm trạng thái vẫn xanh.
    """
    resp = client.post("/api/export", json={"transcript_id": client.tid, "format": "srt"})
    job_id = resp.json()["id"]

    from app.pipeline.export import ExportHandler
    from app.domain.models import Job
    ExportHandler(client.repos, out_dir=client.tmp / "o").run(
        Job(id=job_id, workspace=1, type="export", engine=None, phase="export:-",
            payload=resp.json()["payload"]), lambda p, line: None)
    assert (client.tmp / "o" / f"transcript-{client.tid}.srt").is_file(), (
        "tệp PHẢI có sẵn, nếu không phép kiểm 409 ở dưới chỉ đang đo sự vắng mặt"
    )

    assert client.get(f"/api/export/{job_id}/download").status_code == 409


# --------------------------------------------------------------------------
# Tên tệp export: route phải là CÙNG một quy tắc với `pipeline/export.py`
# --------------------------------------------------------------------------

def test_download_serves_the_pipeline_artifact_name(client):
    """Handler ghi `<stem>.vi.<fmt>` khi payload có bản dịch — không phải `<stem>.<fmt>`.

    Brief tính đường dẫn tải bằng `out_dir / f"{stem}.{fmt}"`, tức bỏ qua hậu tố
    `.vi` mà `pipeline/export.py` (đã ship, có test riêng ở `test_export.py`)
    thêm vào. Payload có bản dịch vì thế cho ra 410 dù tệp nằm ngay đó.

    Payload ở đây đi qua `POST /api/jobs` chứ không phải `POST /api/export`:
    route export cố tình không nhận `translations` (bản dịch là việc của job
    `translate`), nên cách duy nhất có một hàng job THẬT mang bản dịch là tạo
    job thẳng. Cả handler lẫn route đều đọc payload TỪ HÀNG ĐÓ.
    """
    from app.pipeline.export import ExportHandler
    from app.domain.models import Job

    stored = client.post("/api/jobs", json={
        "workspace": 1, "type": "export",
        "payload": {"transcript_id": client.tid, "format": "srt",
                    "bilingual": True, "stem": f"transcript-{client.tid}",
                    "translations": ["Chào mọi người", "Hôm nay ta nói về AI",
                                     "Mô hình này…"]},
    }).json()

    ExportHandler(client.repos, out_dir=client.tmp / "o").run(
        client.repos.get_job(stored["id"]), lambda p, line: None)
    client.repos.set_job_state(stored["id"], "running")
    client.repos.set_job_state(stored["id"], "done")

    # Handler đã ghi đúng tệp mà route phải phục vụ.
    assert (client.tmp / "o" / f"transcript-{client.tid}.vi.srt").is_file()

    dl = client.get(f"/api/export/{stored['id']}/download")
    assert dl.status_code == 200, dl.text
    assert "Chào mọi người" in dl.text


def test_export_stem_cannot_escape_the_output_directory(client):
    """`stem` là dữ liệu BÊN NGOÀI: `../` không được ghi ra ngoài `out_dir`."""
    resp = client.post("/api/export", json={"transcript_id": client.tid,
                                            "format": "srt",
                                            "stem": "../thoat-ra-ngoai"})
    assert resp.status_code == 201
    job = resp.json()
    assert "/" not in job["payload"]["stem"] and ".." not in job["payload"]["stem"], (
        f"stem phải bị cắt về tên trần, nhận được {job['payload']['stem']!r}"
    )

    from app.pipeline.export import ExportHandler
    from app.domain.models import Job
    ExportHandler(client.repos, out_dir=client.tmp / "o").run(
        Job(id=job["id"], workspace=1, type="export", engine=None,
            phase="export:-", payload=job["payload"]), lambda p, line: None)
    client.repos.set_job_state(job["id"], "running")
    client.repos.set_job_state(job["id"], "done")

    assert not (client.tmp / "thoat-ra-ngoai.srt").exists()
    assert (client.tmp / "o" / "thoat-ra-ngoai.srt").is_file()
    assert client.get(f"/api/export/{job['id']}/download").status_code == 200


def test_export_rejects_a_stem_that_is_only_dotdot(client):
    resp = client.post("/api/export", json={"transcript_id": client.tid,
                                            "format": "srt", "stem": ".."})
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# Lỗi đầu vào khác: 404 (không có hàng) / 422 (định dạng, trạng thái)
# --------------------------------------------------------------------------

def test_missing_transcript_is_404_not_500(client):
    assert client.get("/api/transcripts/9999").status_code == 404
    assert client.patch("/api/transcripts/9999",
                        json={"segments": [{"i": 0, "start": 0.0, "end": 1.0,
                                            "text": "x"}]}).status_code == 404
    assert client.get("/api/transcripts/9999/readability").status_code == 404
    assert client.post("/api/transcripts/9999/approve").status_code == 404


def test_patch_rejects_unknown_status(client):
    body = client.get(f"/api/transcripts/{client.tid}").json()
    resp = client.patch(f"/api/transcripts/{client.tid}",
                        json={"segments": body["segments"], "status": "bịa"})
    assert resp.status_code == 422


def test_list_transcripts_omits_segments(client):
    """Danh sách không kèm segments: một transcript 2000 đoạn sẽ làm phình
    response mà trang danh sách không dùng tới."""
    body = client.get("/api/transcripts").json()
    assert [t["id"] for t in body] == [client.tid]
    assert "segments" not in body[0]


def test_approve_does_not_bump_version(client):
    """Duyệt là đổi TRẠNG THÁI, không phải sửa nội dung — version phải đứng yên,
    nếu không mọi bản dịch thành lỗi thời chỉ vì người dùng bấm 'duyệt'."""
    client.post(f"/api/transcripts/{client.tid}/approve")
    assert client.get(f"/api/transcripts/{client.tid}").json()["version"] == 1
