"""API Workspace 2: tạo bản dịch (xếp job), liệt kê kèm cờ `stale`, sửa tay.

Bốn quyết định ở đây, và lý do chúng không hiển nhiên:

* **Từ chối engine chưa sẵn sàng Ở ĐÂY, không để job chết ở worker.** Một hàng
  `translations` `queued` cộng một job `translate` rồi `KeyError` trong
  `mt_engines` là hỏng SAU khi đã ghi dữ liệu; 409 lúc tạo là hỏng TRƯỚC khi ghi
  gì (bài học I-3). Cùng lý do, engine phải là `kind == "mt"`.
* **`prompt_version` đọc từ `spec.capabilities`, KHÔNG import adapter.** `app/api`
  bị cấm import `app.adapters` (`test_api_layer_does_not_import_adapters`), nên
  giá trị đó được `main.build_components()` tính sẵn cạnh `available` — cùng một
  khuôn: dữ liệu dẫn xuất tính ở composition root, tầng API chỉ tiêu thụ.
* **`stale` TÍNH Ở SERVER, mỗi lần đọc.** Client không tự suy: nó không biết
  version hiện tại của transcript, và một cột `stale` lưu sẵn thì mọi đường ghi
  khác phải nhớ cập nhật nó. Nguồn duy nhất là `transcript.version >
  translations.transcript_version`.
* **Sửa tay chỉ đổi `text`.** `PATCH` dựng lại segment bằng
  `dataclasses.replace`, KHÔNG bằng `Segment(...)` — dựng tay chỉ chép vài trường
  và nuốt `speaker`/`words`/`emotion`/`events`/`t`/`qa`/`suspect` (lỗi đã bị bắt
  ở review Task 7 và lặp lại hai lần trong giai đoạn này). `start`/`end` là thời
  lượng của bản GỐC: sửa chữ không được phép làm phụ đề lệch.
"""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_repos, get_specs
from app.domain.job_state import phase_of
from app.domain.models import Job
from app.domain.staleness import is_stale
from app.registry import by_id

router = APIRouter(prefix="/api/translations", tags=["translations"])


class CreateIn(BaseModel):
    transcript_id: int
    engine: str
    target_lang: str = "vi"


class SegmentIn(BaseModel):
    i: int
    start: float
    end: float
    text: str


class PatchIn(BaseModel):
    # Rỗng là NO-OP hợp lệ ("không sửa gì"), không phải dữ liệu hỏng: khác với
    # `PatchIn` của transcript, ở đây bản dịch có thể còn 0 segment (job vừa được
    # xếp, chưa dịch được dòng nào) nên `min_length=1` sẽ chặn một request đúng.
    segments: list[SegmentIn] = Field(default_factory=list)


def _summary(row, *, stale: bool) -> dict:
    return {
        "id": row.id,
        "transcript_id": row.transcript_id,
        "engine": row.engine,
        "target_lang": row.target_lang,
        "prompt_version": row.prompt_version,
        "transcript_version": row.transcript_version,
        "status": row.status,
        "stale": stale,
        "created_at": row.created_at,
    }


def _require_translation(repos, translation_id: int):
    """Đọc một bản dịch, đổi `LookupError` của cổng thành 404.

    `LookupError` chứ không phải lớp `NotFound` của adapter: route chỉ được biết
    cổng, và một hiện thực khác của cổng không phải kéo lớp của SQLite theo.
    """
    try:
        return repos.get_translation(translation_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


def _require_transcript(repos, transcript_id: int):
    try:
        return repos.get_transcript(transcript_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("", status_code=201)
def create_translation(body: CreateIn, repos=Depends(get_repos),
                       specs=Depends(get_specs)):
    """Tạo hàng `translations` TRƯỚC, rồi xếp ĐÚNG MỘT job `translate`.

    Thứ tự này bắt buộc: `TranslateHandler` tra hàng đó bằng `translation_id`
    trong payload, và ghi checkpoint/trạng thái lên nó. Không có hàng thì job tự
    sinh `NotFound`/`KeyError` ở tận worker.
    """
    try:
        spec = by_id(specs, body.engine)
    except KeyError as exc:
        raise HTTPException(
            422, f"engine không có trong registry: {body.engine!r}") from exc

    if spec.kind != "mt":
        # Nhận id ASR ở đây là xếp một job `translate` mà `mt_engines` chắc chắn
        # không có khoá đó — 422 ngay, không ghi gì.
        raise HTTPException(
            422, f"engine không phải engine dịch: {body.engine!r} "
                 f"(kind={spec.kind!r})")

    if not spec.capabilities.get("available"):
        # I-3: từ chối Ở ĐÂY, không để job chết trong worker.
        raise HTTPException(
            409, f"engine chưa sẵn sàng: {body.engine!r} "
                 f"(model chưa pull hoặc runtime không phục vụ được)")

    transcript = _require_transcript(repos, body.transcript_id)

    translation_id = repos.add_translation(
        transcript_id=transcript.id,
        # Version mà bản dịch này dịch TỪ, không phải version hiện tại lúc job
        # chạy: job có thể chạy sau khi người dùng sửa transcript, và khi đó bản
        # dịch phải được coi là lệch thời.
        transcript_version=transcript.version,
        engine=spec.id,
        target_lang=body.target_lang,
        segments=[],
        prompt_version=spec.capabilities.get("prompt_version", "unknown"),
        glossary_version=repos.glossary_version(),
        status="queued",
    )
    job = Job(id=None, workspace=2, type="translate", engine=spec.id,
              phase=phase_of("translate", spec.id),
              # ĐÚNG năm khoá `TranslateHandler.run` đọc. Thừa/thiếu một khoá là
              # job chết bằng `KeyError` sau khi hàng đã được ghi.
              payload={"translation_id": translation_id,
                       "transcript_id": transcript.id,
                       "engine_id": spec.id,
                       "source_lang": transcript.lang,
                       "target_lang": body.target_lang})
    job.id = repos.add_job(job)

    stored = repos.get_translation(translation_id)
    return {"translation": _summary(stored, stale=False),
            "job": {"id": job.id, "state": job.state, "phase": job.phase}}


@router.get("")
def list_translations(transcript_id: int, repos=Depends(get_repos)):
    """Bản dịch của MỘT transcript, mới nhất trước, kèm cờ `stale` TÍNH Ở ĐÂY."""
    transcript = _require_transcript(repos, transcript_id)
    return [
        _summary(row, stale=is_stale(transcript.version, row.transcript_version))
        for row in repos.list_translations_for_transcript(transcript_id)
    ]


@router.patch("/{translation_id}")
def patch_translation(translation_id: int, body: PatchIn,
                      repos=Depends(get_repos)):
    translation = _require_translation(repos, translation_id)

    known = {s.i for s in translation.segments}
    alien = [s.i for s in body.segments if s.i not in known]
    if alien:
        # Id lạ là lỗi ĐẦU VÀO, và phải bị từ chối TRƯỚC khi ghi: thêm một
        # segment không có ở bản gốc là bịa ra phụ đề không tồn tại.
        raise HTTPException(422, f"segment không thuộc bản dịch này: {alien}")

    edited = {s.i: s for s in translation.segments}
    for seg in body.segments:
        # CHỈ đổi `text`. `replace` giữ cả 13 trường; `start`/`end`/`speaker`/
        # `words` là dữ liệu của bản GỐC, không phải thứ client sửa được.
        edited[seg.i] = dataclasses.replace(edited[seg.i], text=seg.text)

    repos.update_translation_segments(translation_id,
                                      [edited[i] for i in sorted(edited)])
    # Sửa tay không đổi `transcript_version`: bản dịch vẫn dịch từ đúng bản
    # transcript cũ. Nên `stale` vẫn phải TÍNH LẠI từ version hiện tại của
    # transcript — trả cứng `False` ở đây là nói dối ngay sau khi người dùng vừa
    # sửa một bản dịch đã lệch thời (cùng nguồn sự thật với `list_translations`).
    fresh = _require_translation(repos, translation_id)
    current = _require_transcript(repos, fresh.transcript_id).version
    return _summary(fresh, stale=is_stale(current, fresh.transcript_version))
