"""`DELETE /api/translations/{id}` — chỉ MỘT hàng, 404, và 409 khi có job dịch.

Vì sao tách khỏi `test_api_delete_sources.py`: hai route có cùng LUẬT 404/409
nhưng khác hẳn PHẠM VI (nguồn là cascade ba bảng + tệp; bản dịch là một hàng và
không có tệp). Gộp một tệp thì mỗi bài phải đọc cả hai ngữ cảnh mới biết nó đang
nói về cái nào.

Phạm vi là vế quan trọng nhất ở đây: xoá một bản dịch KHÔNG được chạm transcript
hay nguồn của nó. Một `DELETE` viết nhầm thành cascade sẽ làm mất bản ghi gốc —
thứ đắt nhất trong app — mà không có gì báo.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.domain import job_state as js
from app.domain.models import Job, Segment

ENGINE = "opus-mt"


@pytest.fixture()
def client(tmp_path):
    """Cùng khuôn với `test_api_delete_sources.py`: DB tạm + `media_dir` tạm."""
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    media = tmp_path / "media"
    media.mkdir()
    app = create_app(repos=repos, specs=[], media_dir=media, out_dir=tmp_path / "out")
    with TestClient(app) as c:
        c.repos = repos            # type: ignore[attr-defined]
        yield c


def _seed(repos) -> dict:
    """Một nguồn + một transcript + HAI bản dịch của CÙNG transcript.

    Hai bản dịch là điều kiện để phép ghim "chỉ hàng được chỉ định biến mất" có
    nghĩa: với một hàng, "xoá cả transcript" và "xoá đúng một hàng" cho cùng một
    hình dạng danh sách rỗng.
    """
    sid = repos.add_source(kind="file", origin="x.wav", media_path="/m/x.wav")
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh",
                               segments=[Segment(i=1, start=0.0, end=1.0,
                                                 text="你好")])
    ban = [repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=ENGINE, target_lang="vi",
        segments=[Segment(i=1, start=0.0, end=1.0, text=f"Xin chào {k}")],
        prompt_version="raw-p1") for k in (1, 2)]
    return {"source_id": sid, "transcript_id": tid, "translation_ids": ban}


def _a_translate_job(repos, translation_id: int, state: str = js.QUEUED) -> int:
    """Job `translate` mang ĐÚNG khoá mà `TranslateHandler` đọc."""
    job = Job(id=None, workspace=2, type="translate", engine=ENGINE,
              phase=js.phase_of("translate", ENGINE),
              payload={"translation_id": translation_id, "transcript_id": 1,
                       "engine_id": ENGINE, "source_lang": "zh",
                       "target_lang": "vi"})
    job.id = repos.add_job(job)
    if state != js.QUEUED:
        repos.set_job_state(job.id, state)
    return job.id


def test_delete_translation_removes_only_that_row(client):
    repos = client.repos          # type: ignore[attr-defined]
    du = _seed(repos)
    xoa, giu = du["translation_ids"]

    r = client.delete(f"/api/translations/{xoa}")

    assert r.status_code == 204, r.text
    assert r.content == b"", r.content

    with pytest.raises(LookupError):
        repos.get_translation(xoa)
    assert repos.get_translation(giu).id == giu, "bản dịch KHÁC phải còn nguyên"
    # Và phạm vi dừng ở bảng `translations`: transcript + nguồn KHÔNG được chạm.
    assert repos.get_transcript(du["transcript_id"]).id == du["transcript_id"]
    assert repos.get_source(du["source_id"]).id == du["source_id"]


def test_delete_an_unknown_translation_is_404_and_names_the_id(client):
    r = client.delete("/api/translations/424242")

    assert r.status_code == 404, r.text
    assert "424242" in r.json()["detail"], r.json()


def test_a_queued_translate_job_blocks_deletion_with_409(client):
    """Job `translate` mang `payload.translation_id` ⇒ 409 + id job, HÀNG CÒN.

    `TranslateHandler` ghi checkpoint vào hàng này sau mỗi lô (`update_translation_
    segments`), nên xoá dưới chân nó làm lô kế tiếp ném `NotFound` và job chết vì
    một lý do không liên quan tới dữ liệu.
    """
    repos = client.repos          # type: ignore[attr-defined]
    du = _seed(repos)
    xoa = du["translation_ids"][0]
    job_id = _a_translate_job(repos, xoa)

    r = client.delete(f"/api/translations/{xoa}")

    assert r.status_code == 409, r.text
    cau = r.json()["detail"]
    assert f"#{job_id}" in cau, cau
    assert str(xoa) in cau, cau
    assert repos.get_translation(xoa).id == xoa, "hàng phải CÒN sau 409"


def test_a_finished_translate_job_does_not_block_and_its_row_survives(client):
    repos = client.repos          # type: ignore[attr-defined]
    du = _seed(repos)
    xoa = du["translation_ids"][0]
    job_id = _a_translate_job(repos, xoa, state=js.RUNNING)
    repos.set_job_state(job_id, js.DONE)

    r = client.delete(f"/api/translations/{xoa}")

    assert r.status_code == 204, r.text
    with pytest.raises(LookupError):
        repos.get_translation(xoa)
    assert repos.get_job(job_id).state == js.DONE, "hàng `jobs` không bị xoá theo"
