from __future__ import annotations

from app.domain.staleness import is_stale


def test_translation_from_current_version_is_fresh():
    assert is_stale(transcript_version=5, translated_from_version=5) is False


def test_translation_from_old_version_is_stale():
    assert is_stale(transcript_version=5, translated_from_version=3) is True


def test_first_translation_is_never_stale():
    assert is_stale(transcript_version=1, translated_from_version=1) is False


def test_same_second_edits_still_detected():
    """Đây chính là lý do dùng version thay vì timestamp: hai lần sửa trong
    cùng một giây vẫn phân biệt được."""
    assert is_stale(transcript_version=8, translated_from_version=7) is True


def _hang(**kw):
    """Hang ban dich toi thieu cho `translation_summary_json`."""
    from types import SimpleNamespace
    goc = dict(id=1, transcript_id=1, engine="mt", target_lang="vi",
               prompt_version="p1", transcript_version=1, status="done",
               created_at="2026-01-01T00:00:00Z", qa_issues=[])
    goc.update(kw)
    return SimpleNamespace(**goc)


def test_needs_review_bat_cho_loi_NOI_DUNG():
    """`lang:` va `echo:` la BAN DICH SAI — co `needs_review` phai bat.

    DO DUOC tren 52 ban dich trong DB (workspace 2):

        cps:      4715 co   <- toc do doc, SO DO
        length:    714 co   <- ti le do dai, SO DO
        lang:       53 co   <- dong dich VAN la chu goc, BAN DICH SAI
        echo:        2 co   <- chep nguyen van, BAN DICH SAI

    Chi 3/52 ban dich co loi noi dung (id=22, 17, 12). Neu gop ca `cps` va
    `length` thi 48/52 ban dich bi gan co sai.
    """
    from app.domain.staleness import translation_summary_json

    a = translation_summary_json(_hang(qa_issues=["lang:1=source:han5/latin4"]), stale=False)
    assert a["needs_review"] is True
    b = translation_summary_json(_hang(qa_issues=["echo:0=1.00"]), stale=False)
    assert b["needs_review"] is True
    c = translation_summary_json(_hang(qa_issues=["lang:376=residue:han2"]), stale=False)
    assert c["needs_review"] is True


def test_needs_review_TAT_cho_so_do():
    """`cps:` va `length:` la SO DO — khong duoc bat `needs_review`.

    Mot dong 26 ky tu trong cua so 1 giay la chuyen binh thuong cua phu de.
    """
    from app.domain.staleness import translation_summary_json

    a = translation_summary_json(_hang(qa_issues=["cps:0=26.0>21.0"]), stale=False)
    assert a["needs_review"] is False
    b = translation_summary_json(_hang(qa_issues=["length:3=2.40"]), stale=False)
    assert b["needs_review"] is False
    c = translation_summary_json(_hang(qa_issues=[]), stale=False)
    assert c["needs_review"] is False


def test_status_KHONG_bi_doi_boi_co_chat_luong():
    """`status` la co SAN SANG, khong phai co CHAT LUONG.

    DA THU VA DA BO: ban dau toi doi `status` thanh `needs_review` khi co loi
    noi dung, va `test_e2e_fake.py::test_full_pipeline_from_upload_to_srt` DO.
    Cau khang dinh trong bai do ghi ro hop dong:

        "endpoint nay phai phan biet duoc `queued` voi `done`: day la thu giao
        dien Workspace 2 dung de biet ban dich da san sang chua"

    Tron hai nghia vao mot khoa la lam hong thu giao dien dang dua vao. Co
    chat luong di ra khoa rieng `needs_review`.
    """
    from app.domain.staleness import translation_summary_json

    co_loi = translation_summary_json(_hang(status="done",
                                        qa_issues=["lang:1=source:han5/latin4"]), stale=False)
    assert co_loi["status"] == "done", (
        "status phai giu nghia SAN SANG, do duoc %r" % co_loi["status"])
    assert co_loi["needs_review"] is True

    xong = translation_summary_json(_hang(status="done", qa_issues=["cps:0=26.0>21.0"]), stale=False)
    assert xong["status"] == "done"
    assert xong["needs_review"] is False

    dang_chay = translation_summary_json(_hang(status="queued", qa_issues=[]), stale=False)
    assert dang_chay["status"] == "queued"
