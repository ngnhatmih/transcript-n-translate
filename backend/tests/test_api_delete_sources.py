"""`DELETE /api/sources/{id}` — cascade viết tay, tệp media, 404 và 409.

Vì sao tệp này tồn tại (đo được TRƯỚC tính năng): `grep -rn "delete" app/api/`
= **0 route**, và `schema.py` khai `REFERENCES sources(id)` mà KHÔNG có
`ON DELETE CASCADE` ⇒ trước đây KHÔNG có đường nào xoá một nguồn, kể cả từ tay
người dùng. Nay đường đó tồn tại, nên bốn bất biến của nó phải được ghim bằng
bài, không bằng lời khai:

* **Cascade là BA bảng, một giao dịch.** Xoá nguồn mà để lại transcript/bản dịch
  là để lại những hàng mồ côi hiện lên `GET /api/transcripts` như dữ liệu thật;
  `PRAGMA foreign_keys=ON` khiến SQLite từ chối thẳng nếu ta quên.
* **Tệp media chỉ bị xoá khi nằm trong `media_dir`.** Đường dẫn trong DB là dữ
  liệu, không phải quyền (`domain/paths.py`), và `unlink()` không hoàn tác được.
* **404 cho id lạ**, kèm id trong câu (client hiện nguyên văn `detail`).
* **409 khi còn job sống trỏ vào nguồn** — hàng phải còn nguyên sau đó.

Fixture dựng `SqliteRepos` + `create_app` trực tiếp (khuôn của
`tests/test_api_sources.py`) chứ không qua `main.build_components()`: bài ở đây
chỉ nói về đường HTTP + SQL, không nói về composition root, và cách này không
nạp registry/model nào.
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

#: Engine của mọi hàng dịch trong tệp này. Giá trị chỉ để đọc lại, không có
#: adapter nào được nạp: route DELETE không tra registry.
ENGINE = "opus-mt"


@pytest.fixture()
def client(tmp_path):
    """App đầy đủ trên một DB TẠM + một `media_dir` TẠM.

    ⚠️ KHÔNG trỏ vào `data/app.db` của repo (DB đó KHÔNG rỗng): mỗi bài ở đây
    khẳng định những thứ như "bảng `sources` rỗng đi một hàng", nên một DB có
    sẵn dữ liệu sẽ làm phép đếm vô nghĩa — và tệ hơn, phép đo sẽ XOÁ dữ liệu thật.
    """
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    media = tmp_path / "media"
    media.mkdir()
    app = create_app(repos=repos, specs=[], media_dir=media, out_dir=tmp_path / "out")
    with TestClient(app) as c:
        c.repos = repos            # type: ignore[attr-defined]
        c.tmp = tmp_path           # type: ignore[attr-defined]
        c.media = media            # type: ignore[attr-defined]
        yield c


def _seed(repos, media: pathlib.Path, *, ten: str = "a",
          audio: bool = True) -> dict:
    """Một nguồn + MỘT transcript + HAI bản dịch, cùng hai tệp THẬT trên đĩa.

    Hai bản dịch chứ không một: phép ghim "xoá nguồn xoá MỌI bản dịch của nó" chỉ
    có nghĩa khi có nhiều hơn một hàng để đếm. Hai tệp (media + audio) là hình
    dạng thật của một nguồn đã bóc tiếng (`set_source_audio`).
    """
    tep = media / f"{ten}.wav"
    tep.write_bytes(b"media-that")
    tieng = media / f"{ten}.16k.wav"
    if audio:
        tieng.write_bytes(b"audio-that")
    sid = repos.add_source(kind="file", origin=f"{ten}.wav",
                           media_path=str(tep), audio_path=str(tieng),
                           lang="zh", duration=1.0)
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo",
                               lang="zh",
                               segments=[Segment(i=1, start=0.0, end=1.0,
                                                 text="你好")])
    ban = [repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=ENGINE, target_lang="vi",
        segments=[Segment(i=1, start=0.0, end=1.0, text=f"Xin chào {k}")],
        prompt_version="raw-p1") for k in (1, 2)]
    return {"source_id": sid, "transcript_id": tid, "translation_ids": ban,
            "media_path": tep, "audio_path": tieng}


def _a_job(repos, *, job_type: str, payload: dict, state: str = js.QUEUED) -> int:
    """Ghi MỘT hàng `jobs` trạng thái `state` và trả id của nó.

    Job được ghi qua cổng thật (`add_job`), không qua fixture tự chế: đường nối
    của phép 409 là `payload` JSON như nó nằm trong DB, và một job dựng tay trong
    bộ nhớ sẽ không chứng minh được gì về hàng thật.
    """
    job = Job(id=None, workspace=1, type=job_type, engine=None,
              phase=js.phase_of(job_type, None), payload=payload)
    job.id = repos.add_job(job)
    if state != js.QUEUED:
        repos.set_job_state(job.id, state)
    return job.id


# ---------------------------------------------------------------------------
# Cascade: bản dịch + transcript + nguồn, và hàng KHÔNG liên quan còn nguyên
# ---------------------------------------------------------------------------

def test_delete_source_cascades_its_translations_transcripts_and_row(client):
    repos = client.repos          # type: ignore[attr-defined]
    media: pathlib.Path = client.media  # type: ignore[attr-defined]
    xoa = _seed(repos, media, ten="xoa")
    giu = _seed(repos, media, ten="giu")

    r = client.delete(f"/api/sources/{xoa['source_id']}")

    assert r.status_code == 204, r.text
    # 204 KHÔNG có thân (RFC 7231): một thân `null` là hình dạng mà vài client
    # coi là lỗi, và `client.ts` of frontend đã phân nhánh riêng cho 204.
    assert r.content == b"", r.content

    with pytest.raises(LookupError):
        repos.get_source(xoa["source_id"])
    with pytest.raises(LookupError):
        repos.get_transcript(xoa["transcript_id"])
    for tr_id in xoa["translation_ids"]:
        with pytest.raises(LookupError):
            repos.get_translation(tr_id)

    # HÀNG KHÔNG LIÊN QUAN phải nguyên vẹn — cả ba bảng, không chỉ nguồn.
    assert repos.get_source(giu["source_id"]).id == giu["source_id"]
    assert repos.get_transcript(giu["transcript_id"]).source_id == giu["source_id"]
    assert {t.id for t in repos.list_translations()} == set(giu["translation_ids"])
    assert [s.id for s in repos.list_sources()] == [giu["source_id"]]


def test_delete_source_removes_both_media_files(client):
    repos = client.repos          # type: ignore[attr-defined]
    media: pathlib.Path = client.media  # type: ignore[attr-defined]
    xoa = _seed(repos, media, ten="co-tieng")
    assert xoa["media_path"].exists() and xoa["audio_path"].exists()

    assert client.delete(f"/api/sources/{xoa['source_id']}").status_code == 204

    assert not xoa["media_path"].exists(), "media_path phải bị xoá khỏi đĩa"
    assert not xoa["audio_path"].exists(), "audio_path phải bị xoá khỏi đĩa"


def test_a_missing_media_file_is_not_an_error(client):
    """`audio_path` trỏ vào tệp KHÔNG có (nguồn chưa bóc tiếng, hoặc bị xoá tay).

    Thiếu tệp không được biến một lần xoá ĐÚNG thành 500: hàng `sources` là thứ
    người dùng yêu cầu xoá, còn tệp chỉ là thứ đi kèm.
    """
    repos = client.repos          # type: ignore[attr-defined]
    media: pathlib.Path = client.media  # type: ignore[attr-defined]
    xoa = _seed(repos, media, ten="thieu-tieng", audio=False)
    assert not xoa["audio_path"].exists()

    r = client.delete(f"/api/sources/{xoa['source_id']}")

    assert r.status_code == 204, r.text
    assert not xoa["media_path"].exists()
    with pytest.raises(LookupError):
        repos.get_source(xoa["source_id"])


def test_delete_source_refuses_to_unlink_anything_outside_the_media_dir(client):
    """`media_path` nằm NGOÀI `media_dir` ⇒ hàng bị xoá, tệp KHÔNG bị chạm.

    Đây là phép ghim của luật "đường dẫn trong DB là dữ liệu, không phải quyền":
    `unlink()` không hoàn tác được, nên một cột bị sửa tay (hoặc một nguồn `url`
    cũ trỏ ra ngoài) không được phép xoá tệp của người khác. Response vẫn 204 vì
    lý do người dùng yêu cầu — hàng `sources` — đã được thực hiện.
    """
    repos = client.repos          # type: ignore[attr-defined]
    tmp: pathlib.Path = client.tmp  # type: ignore[attr-defined]
    ngoai = tmp / "ngoai-media.wav"
    ngoai.write_bytes(b"khong-duoc-xoa")
    sid = repos.add_source(kind="file", origin="ngoai.wav",
                           media_path=str(ngoai), lang="zh")

    r = client.delete(f"/api/sources/{sid}")

    assert r.status_code == 204, r.text
    assert ngoai.exists(), "tệp NGOÀI media_dir KHÔNG được bị xoá"
    assert ngoai.read_bytes() == b"khong-duoc-xoa", "nội dung tệp phải nguyên vẹn"
    with pytest.raises(LookupError):
        repos.get_source(sid)


# ---------------------------------------------------------------------------
# 404 và 409
# ---------------------------------------------------------------------------

def test_delete_an_unknown_source_is_404_and_names_the_id(client):
    r = client.delete("/api/sources/987654")

    assert r.status_code == 404, r.text
    # Câu của CỔNG (`sqlite_repos.get_source`), không phải một câu tự chế: client
    # hiện nguyên văn `ApiError.message`, và id chính là thứ người dùng cần thấy.
    assert "987654" in r.json()["detail"], r.json()


def test_a_queued_job_referencing_the_source_blocks_deletion_with_409(client):
    """Job `queued` mang `payload.source_id` ⇒ 409, và HÀNG PHẢI CÒN.

    Vì sao TỪ CHỐI là hành vi an toàn: worker sẽ nhận job đó và `IngestHandler`/
    `TranscribeHandler` đọc `payload["source_id"]` rồi ghi transcript mới cho
    nguồn — xoá hàng dưới chân nó biến một lần chạy hợp lệ thành một job `failed`
    vì lý do không liên quan tới dữ liệu (hoặc, tệ hơn, một transcript trỏ vào
    nguồn đã mất).
    """
    repos = client.repos          # type: ignore[attr-defined]
    media: pathlib.Path = client.media  # type: ignore[attr-defined]
    xoa = _seed(repos, media, ten="dang-cho")
    job_id = _a_job(repos, job_type="ingest",
                    payload={"source_id": xoa["source_id"], "lang": "zh"})

    r = client.delete(f"/api/sources/{xoa['source_id']}")

    assert r.status_code == 409, r.text
    cau = r.json()["detail"]
    # ĐÍCH DANH id job: "có job đang chạy" mà không nói job nào thì người dùng
    # không biết phải huỷ cái gì.
    assert f"#{job_id}" in cau, cau
    assert str(xoa["source_id"]) in cau, cau

    # Hàng còn NGUYÊN — cả ba bảng, và cả tệp.
    assert repos.get_source(xoa["source_id"]).id == xoa["source_id"]
    assert repos.get_transcript(xoa["transcript_id"]).source_id == xoa["source_id"]
    assert len(repos.list_translations()) == 2
    assert xoa["media_path"].exists()


def test_a_running_job_referencing_the_source_blocks_deletion_too(client):
    """`running` cũng chặn — không chỉ `queued`.

    Đây là vế thứ hai của luật, và nó là vế NGUY HIỂM hơn: job `queued` chưa ghi
    gì, còn job `running` đang giữ checkpoint.
    """
    repos = client.repos          # type: ignore[attr-defined]
    media: pathlib.Path = client.media  # type: ignore[attr-defined]
    xoa = _seed(repos, media, ten="dang-chay")
    job_id = _a_job(repos, job_type="asr",
                    payload={"source_id": xoa["source_id"], "lang": "zh"},
                    state=js.RUNNING)

    r = client.delete(f"/api/sources/{xoa['source_id']}")

    assert r.status_code == 409, r.text
    assert f"#{job_id}" in r.json()["detail"], r.json()
    assert repos.get_source(xoa["source_id"]).id == xoa["source_id"]


def test_a_finished_job_does_not_block_and_its_row_survives(client):
    """Job `done` KHÔNG chặn xoá, và hàng `jobs` của nó KHÔNG bị xoá theo.

    Hai vế của cùng một quyết định: "đang bận" là điều kiện DUY NHẤT để từ chối,
    và `jobs` là LỊCH SỬ chạy chứ không phải con của nguồn — xoá nó theo nguồn là
    xoá dấu vết của một lần chạy thật (`mark_running_as_interrupted` giữ hàng lại
    vì đúng lý do đó).
    """
    repos = client.repos          # type: ignore[attr-defined]
    media: pathlib.Path = client.media  # type: ignore[attr-defined]
    xoa = _seed(repos, media, ten="da-xong")
    job_id = _a_job(repos, job_type="ingest",
                    payload={"source_id": xoa["source_id"], "lang": "zh"},
                    state=js.RUNNING)
    repos.set_job_state(job_id, js.DONE)

    r = client.delete(f"/api/sources/{xoa['source_id']}")

    assert r.status_code == 204, r.text
    with pytest.raises(LookupError):
        repos.get_source(xoa["source_id"])
    assert repos.get_job(job_id).state == js.DONE, (
        "hàng `jobs` KHÔNG được xoá theo nguồn — nó là lịch sử"
    )


def test_an_active_job_of_ANOTHER_source_does_not_block(client):
    """409 phân biệt TỪNG nguồn: job đang chạy trên nguồn B không cản xoá nguồn A.

    Thiếu bài này thì một predicate chỉ cần "có job sống nào đó" là xanh — trong
    khi lỗi thật (khoá sai, `==` sai) lại đúng ở hình dạng đó.
    """
    repos = client.repos          # type: ignore[attr-defined]
    media: pathlib.Path = client.media  # type: ignore[attr-defined]
    xoa = _seed(repos, media, ten="xoa-a")
    giu = _seed(repos, media, ten="giu-b")
    _a_job(repos, job_type="ingest",
           payload={"source_id": giu["source_id"], "lang": "zh"})

    r = client.delete(f"/api/sources/{xoa['source_id']}")

    assert r.status_code == 204, r.text
    assert repos.get_source(giu["source_id"]).id == giu["source_id"]
