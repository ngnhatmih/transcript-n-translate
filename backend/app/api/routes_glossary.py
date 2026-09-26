"""Glossary CRUD + hệ quả: glossary đổi thì bản dịch nào phải dịch lại.

`affected` là giá trị chính của tab Thuật ngữ ở frontend: đổi một thuật ngữ mà
không biết bản dịch nào phải xem lại thì glossary chỉ là một cuốn từ điển rời.

Năm quyết định ở đây, và lý do chúng không hiển nhiên:

* **KHÔNG có `bump_glossary_version()`.** `repos.upsert_term` đã tăng
  `glossary_version` trong CÙNG giao dịch với hàng glossary
  (`sqlite_repos.py:538-541`): nếu hàng landed mà version không tăng thì glossary
  và version lệch nhau, mà version chính là thứ quyết định một bản dịch có lệch
  thời hay không. Gọi thêm một lần bump ở route là tăng HAI lần mỗi lần sửa
  glossary, và mọi bản dịch trông "lỗi thời so với glossary" sớm hơn thực tế.
  Mức tăng thật đã được ghim ở tầng adapter
  (`tests/test_repos_translations.py::test_upsert_term_bumps_glossary_version_once_per_call`).
* **KHÔNG dùng `repos.list_translations()`.** Nó trả `Translation` ĐẦY ĐỦ, tức
  giải mã blob JSON `segments` của MỌI bản dịch trong DB chỉ để lọc theo
  `transcript_id`. Đường đúng: `list_transcripts()` (đằng nào cũng phải đọc để
  tính `affected`) rồi `list_translations_for_transcript()` cho TỪNG transcript
  THẬT SỰ bị ảnh hưởng, và `list_translations_for_transcript` cố tình không
  `SELECT *`.
* **`old` là glossary đọc TRƯỚC khi ghi, và cả hai vế truyền THÔ.** Không lọc
  `approved()` trước khi gọi `affected_segments` — hàm đó tự lọc trên CẢ HAI vế
  (rule T4/F2), và lọc trước sẽ nuốt mất ca "BỎ duyệt". Và `old` phải là trạng
  thái THẬT trước khi ghi, không phải "danh sách hiện tại trừ hàng vừa sửa": cách
  loại trừ đó xoá luôn giá trị `approved` cũ nên ca bỏ duyệt không bao giờ được
  phát hiện (chi tiết + phép đo ở `_recompute_affected`).
* **Sửa một thuật ngữ CHƯA duyệt thì KHÔNG ảnh hưởng gì.** Bản nháp không được
  nhét vào prompt, nên nó không ràng buộc bản dịch nào. Đây là hành vi có chủ ý
  đã ghim ở Task 4, không phải bất đối xứng cần "sửa".
* **Job dịch lại mang ĐÚNG khoá payload `TranslateHandler.run` đọc.** Thừa/thiếu
  một khoá là job chết bằng `KeyError` ở TẬN worker, sau khi hàng đã được ghi
  (bài học I-3). `reason` và `glossary_version` là thêm vào có chủ ý: spec §8.1
  yêu cầu job mang theo `glossary_version` mới, còn `reason` là thứ phân biệt
  "do glossary đổi" với "do người dùng bấm Dịch".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_repos
from app.domain.glossary_match import affected_segments
from app.domain.job_state import phase_of
from app.domain.models import Job, Term

router = APIRouter(prefix="/api/glossary", tags=["glossary"])

#: Nhãn hiện trên job mà người dùng thấy: "Dịch lại · do glossary đổi" (spec §8.1).
RETRANSLATE_REASON = "dịch lại do glossary đổi"


class TermIn(BaseModel):
    lang: str
    term: str
    translation: str
    note: str | None = None
    approved: bool = False


class TermPatch(BaseModel):
    translation: str | None = None
    note: str | None = None
    approved: bool | None = None


def _json(t: Term) -> dict:
    return {"id": t.id, "lang": t.lang, "term": t.term, "translation": t.translation,
            "note": t.note, "approved": t.approved, "created_at": t.created_at}


def _term_of(repos, lang: str, term_id: int) -> Term:
    """Hàng vừa ghi, đọc LẠI từ cổng.

    Không dựng `Term` từ body: giá trị trả về phải là thứ ĐÃ LƯU (kể cả trường
    route không sửa), không phải thứ client vừa gửi lên.
    """
    for t in repos.list_terms(lang=lang):
        if t.id == term_id:
            return t
    raise HTTPException(500, f"vừa ghi thuật ngữ {term_id} nhưng không đọc lại được")


def _recompute_affected(repos, *, lang: str, old: list[Term],
                        new: list[Term]) -> list[int]:
    """Id TRANSCRIPT (không phải segment) có ít nhất một segment bị ảnh hưởng.

    `old`/`new` là HAI TRẠNG THÁI THẬT của glossary cùng ngôn ngữ: `old` đọc
    TRƯỚC khi ghi, `new` đọc SAU khi ghi, cả hai truyền THÔ (không lọc
    `approved()`) vì `affected_segments` tự lọc trên cả hai vế.

    Vì sao `old` phải đọc TRƯỚC khi ghi, chứ không phải suy ra bằng cách loại
    hàng vừa sửa khỏi danh sách hiện tại: cách "loại trừ" đó làm mất luôn giá trị
    `approved` CŨ của hàng, nên ca **BỎ duyệt** so `approved([]) == {}` với
    `approved([hàng mới, chưa duyệt]) == {}` và không bao giờ báo ảnh hưởng —
    đúng ca mà mục hiệu chỉnh #7 nói PHẢI báo. Đo được: với cách loại trừ,
    `test_unapproving_a_term_also_affects_the_translations_that_use_it` đỏ với
    `[] == [1]`.

    Chỉ xét transcript ĐÚNG ngôn ngữ của glossary: cùng một chữ ở hai ngôn ngữ là
    hai danh tính, nên `list_terms` phải lọc theo `lang` (mặc định của cổng là
    MỌI ngôn ngữ) và transcript khác ngôn ngữ không được tính.
    """
    out: list[int] = []
    for t in repos.list_transcripts():
        if t.lang != lang:
            continue
        if affected_segments(t.segments, old, new):
            out.append(t.id)
    return out


def _enqueue_retranslate(repos, *, affected: list[int], lang: str) -> list[int]:
    """Sinh job "Dịch lại · do glossary đổi" cho MỌI bản dịch của transcript bị ảnh hưởng.

    KHÔNG lọc theo `status`: hàng đang `queued`/`running`/`failed` tại lúc
    glossary đổi vẫn phải chạy lại. Một bộ lọc `status == "done"` sẽ bỏ IM LẶNG
    đúng những bản dịch chưa xong — tức là những hàng duy nhất còn có thể dịch
    sai — nên ở đây chấp nhận cái giá: một hàng chưa xong có thể nhận hai job,
    job thừa chỉ tốn thêm một lượt engine. Đây là lựa chọn có chủ ý, "job trùng"
    thay vì "bản dịch bị bỏ quên", và cũng không có idempotency guard:
    `TranslateHandler` đọc lại glossary HIỆN TẠI lúc nó chạy, nên hai job cho
    cùng một hàng tính ra cùng một kết quả.

    `affected` là id TRANSCRIPT do `_recompute_affected` trả về, và mọi id trong
    đó đều thuộc `lang` (đó là điều kiện để lọt vào danh sách), nên
    `source_lang=lang` là dữ liệu suy ra được chứ không phải phỏng đoán.

    Với mỗi transcript bị ảnh hưởng mới hỏi `list_translations_for_transcript`:
    `list_translations()` trả `Translation` đầy đủ và giải mã JSON của mọi bản
    dịch trong DB, kể cả bản dịch của transcript không liên quan.
    """
    glossary_version = repos.glossary_version()
    job_ids: list[int] = []
    for transcript_id in affected:
        for summary in repos.list_translations_for_transcript(transcript_id):
            job = Job(id=None, workspace=2, type="translate", engine=summary.engine,
                      phase=phase_of("translate", summary.engine),
                      payload={
                          # ĐÚNG năm khoá `TranslateHandler.run` đọc.
                          "translation_id": summary.id,
                          "transcript_id": summary.transcript_id,
                          "engine_id": summary.engine,
                          "source_lang": lang,
                          "target_lang": summary.target_lang,
                          # Dấu vết của lần dịch lại này (spec §8.1). Handler
                          # hiện KHÔNG đọc khoá này — nó vẫn được ghi để job tự
                          # nói được nó ra đời vì glossary đã sang version nào.
                          "glossary_version": glossary_version,
                          "reason": RETRANSLATE_REASON,
                      })
            job_ids.append(repos.add_job(job))
    return job_ids


def _after_write(repos, *, lang: str, term_id: int, old: list[Term]) -> dict:
    """Hệ quả chung của POST và PATCH: tính `affected` rồi xếp job dịch lại.

    Dùng chung một đường cho cả hai lối ghi: hai bản sao của cùng một biểu thức
    là hai chỗ để trôi, và đây chính là thứ tab Thuật ngữ đọc. `old` là glossary
    của `lang` đọc TRƯỚC khi ghi (xem `_recompute_affected`).
    """
    new = repos.list_terms(lang=lang)
    affected = _recompute_affected(repos, lang=lang, old=old, new=new)
    _enqueue_retranslate(repos, affected=affected, lang=lang)
    out = _json(_term_of(repos, lang, term_id))
    out["affected"] = affected
    return out


@router.get("")
def list_glossary(lang: str | None = None, repos=Depends(get_repos)):
    """Mọi thuật ngữ, hoặc chỉ của một ngôn ngữ khi có `?lang=`."""
    return [_json(t) for t in repos.list_terms(lang=lang)]


@router.get("/version")
def get_glossary_version(repos=Depends(get_repos)):
    """`glossary_version` hiện tại — tiện ích ĐỌC, KHÔNG có trong spec §11.

    Spec §11 chỉ liệt kê `GET`/`POST`/`PATCH /api/glossary`. Route này được thêm
    để đọc version qua CÙNG đường HTTP thay vì với tay vào `repos`; nó chỉ gọi
    getter có sẵn trên cổng và không ghi gì. Ghi rõ ở đây (và trong báo cáo Task
    14) để người đọc sau không tưởng nó là hợp đồng của spec.
    """
    return {"glossary_version": repos.glossary_version()}


@router.post("", status_code=201)
def create_term(body: TermIn, repos=Depends(get_repos)):
    """Ghi một thuật ngữ (upsert theo `(lang, term)`) — version tăng TRONG upsert."""
    old = repos.list_terms(lang=body.lang)      # TRƯỚC khi ghi: xem _recompute_affected
    term_id = repos.upsert_term(lang=body.lang, term=body.term,
                                translation=body.translation, note=body.note,
                                approved=body.approved)
    return _after_write(repos, lang=body.lang, term_id=term_id, old=old)


@router.patch("/{term_id}")
def patch_term(term_id: int, body: TermPatch, repos=Depends(get_repos)):
    """Sửa MỘT PHẦN một thuật ngữ: trường không gửi lên giữ nguyên giá trị đã lưu."""
    existing = [t for t in repos.list_terms() if t.id == term_id]
    if not existing:
        raise HTTPException(404, f"không có thuật ngữ {term_id}")
    t = existing[0]
    old = repos.list_terms(lang=t.lang)         # TRƯỚC khi ghi: xem _recompute_affected
    # `upsert_term` là đường ghi DUY NHẤT của glossary (và là đường duy nhất tăng
    # version), nên PATCH đi qua nó thay vì thêm một `update_term` thứ hai.
    repos.upsert_term(
        lang=t.lang, term=t.term,
        translation=body.translation if body.translation is not None else t.translation,
        note=body.note if body.note is not None else t.note,
        approved=body.approved if body.approved is not None else t.approved)
    return _after_write(repos, lang=t.lang, term_id=term_id, old=old)
