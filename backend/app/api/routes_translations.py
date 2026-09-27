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
* **Route export hình dạng spec §11 ở ĐÂY, và đi CHUNG `artifact_name()` với
  `pipeline/export.py`.** Spec ghim `GET /api/export/{translation_id}?format=&bilingual=`
  còn Giai đoạn 1a đã ship `POST /api/export` + `GET /api/export/{job_id}/download`.
  Đường CŨ không bị bỏ (nó đang chạy) và `routes_export.py` không bị sửa một byte:
  hai đường gặp nhau ở đúng ba thứ dùng chung — `FORMATS`, `MEDIA_TYPES` và
  `artifact_name()`. Tên tệp route này ghi là tên tệp handler của đường cũ ghi, và
  `tests/test_api_export_by_translation.py` so nội dung của hai đường cho CÙNG một
  bản dịch, nên chúng không thể trôi khỏi nhau mà không đỏ.
"""
from __future__ import annotations

import dataclasses
import pathlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.api.deps import get_dirs, get_repos, get_specs
from app.api.routes_jobs import _job_json
from app.domain.job_state import phase_of
from app.domain.models import Job
from app.domain.paths import PathOutsideRoot, resolve_within
from app.domain.staleness import is_stale, translation_summary_json
from app.pipeline.export import FORMATS, MEDIA_TYPES, artifact_name
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
    """Hình dạng JSON của một bản dịch — UỶ QUYỀN cho builder dùng chung.

    `stale` truyền vào chứ không tính lại ở đây vì đã có route đọc transcript
    ngay trước đó (`_require_transcript`) và biết version hiện tại; hai lần đọc
    cùng một hàng trong một request là hai chỗ để trôi. Giá trị đó được truyền
    thẳng vào builder chung nên hai endpoint không thể phát hai hình dạng khác
    nhau — xem
    `tests/test_api_translations.py::test_the_two_endpoints_describe_a_translation_identically`.
    """
    return translation_summary_json(row, stale=stale)


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
        # M-14: dùng `exc.args[0]`, KHÔNG tự ghép câu thứ hai và KHÔNG dùng
        # `str(exc)`. `KeyError.__str__` repr đối số của nó — `str(KeyError("x"))`
        # là `"'x'"`, kèm một cặp nháy kép — nên "dùng lại `str(exc)`" gửi cho
        # client một thông báo dính nháy lạ. `args[0]` là ĐỐI SỐ TRẦN mà `by_id`
        # truyền, tức cùng một lỗi chỉ còn MỘT hình dạng thông báo.
        raise HTTPException(422, exc.args[0]) from exc

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
    # `job` là hàng ĐÃ GHI đọc lại, không phải object trong bộ nhớ: mọi route tạo
    # việc khác (`routes_jobs._job_json`) trả CÙNG hình dạng này, và một object
    # ba khoá ở riêng đây là chỗ client phải special-case theo endpoint.
    return {"translation": _summary(stored, stale=False),
            "job": _job_json(repos.get_job(job.id))}


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

    # Thứ tự ĐÃ LƯU là dữ liệu, không phải thứ route được chuẩn hoá: đi theo
    # `translation.segments` (không `sorted`) nên sửa chữ một dòng không sắp xếp
    # lại các dòng còn lại. Vẫn không thể thêm hay bớt: mọi `s.i` đến từ chính
    # danh sách đã lưu.
    repos.update_translation_segments(
        translation_id, [edited[s.i] for s in translation.segments])
    # Sửa tay không đổi `transcript_version`: bản dịch vẫn dịch từ đúng bản
    # transcript cũ. Nên `stale` vẫn phải TÍNH LẠI từ version hiện tại của
    # transcript — trả cứng `False` ở đây là nói dối ngay sau khi người dùng vừa
    # sửa một bản dịch đã lệch thời (cùng nguồn sự thật với `list_translations`).
    fresh = _require_translation(repos, translation_id)
    current = _require_transcript(repos, fresh.transcript_id).version
    return _summary(fresh, stale=is_stale(current, fresh.transcript_version))


#: Router RIÊNG cho hình dạng spec §11 của route export.
#:
#: Không nằm trên `router` ở trên (router đó mang `prefix="/api/translations"`), và
#: cũng KHÔNG nằm trong `routes_export.py`: tệp đó sở hữu hai route cũ ĐANG CHẠY và
#: được giữ nguyên byte-for-byte. Hai đường gặp nhau ở `artifact_name()` chứ không ở
#: tệp nguồn — đó chính là thứ `tests/test_api_export_by_translation.py` ghim.
export_router = APIRouter(prefix="/api/export", tags=["export"])


@export_router.get("/{translation_id}", response_class=PlainTextResponse)
def export_translation(translation_id: int, format: str = "srt", bilingual: int = 0,
                       repos=Depends(get_repos), dirs=Depends(get_dirs)):
    """Xuất THẲNG nội dung phụ đề của một bản dịch (spec §11).

    Đường CŨ (`POST /api/export` -> job -> `GET /api/export/{job_id}/download`) vẫn
    là đường chạy job và ghi tệp chỉ mục `.json`; đường này trả nội dung ngay, không
    xếp job. Hai đường dùng CHUNG `FORMATS`/`MEDIA_TYPES`/`artifact_name()` của
    `pipeline/export.py`, nên cùng một bản dịch ⇒ cùng nội dung và cùng tên tệp.

    `translations` ở đây là danh sách SONG SONG với `transcript.segments` (cả ba
    định dạng tra theo VỊ TRÍ, không theo `seg.i`) — đúng bất biến của
    `domain/subtitle_format.py`, và đúng thứ `ExportHandler.run` dựng từ
    `payload["translations"]`.
    """
    fmt = format.lower()
    if fmt not in FORMATS:
        # Kiểm ĐỊNH DẠNG trước khi tra hàng: `format` là tham số của client còn id
        # là dữ liệu, và đây đúng thứ tự của `create_export` (route cũ). Đảo lại
        # thì `?format=pdf` trên một id lạ trả 404 và client tưởng id mới là sai.
        raise HTTPException(
            422, f"định dạng không hỗ trợ: {format!r} (có: {sorted(FORMATS)})")

    translation = _require_translation(repos, translation_id)
    transcript = _require_transcript(repos, translation.transcript_id)

    translations = [seg.text for seg in translation.segments]
    if len(translations) != len(transcript.segments):
        # KHÔNG để `_assert_lengths` của `subtitle_format` ném `ValueError` ra
        # thành 500: bản dịch lệch số đoạn là DỮ LIỆU bình thường (transcript bị
        # sửa sau khi dịch), không phải lỗi máy chủ. 409 cũng đúng lớp với đường
        # cũ: handler ném cùng `ValueError`, job thành `failed`, và
        # `GET /api/export/{job_id}/download` trả 409 "job chưa xong".
        raise HTTPException(
            409, f"bản dịch {translation_id} có {len(translations)} đoạn nhưng "
                 f"transcript {transcript.id} có {len(transcript.segments)} đoạn: "
                 f"dịch lại trước khi xuất")

    body = FORMATS[fmt](transcript.segments, translations=translations,
                        bilingual=bool(bilingual))

    # CÙNG `artifact_name()` với handler của đường cũ. `translated=True` vì route
    # này LUÔN xuất theo một hàng `translations` — quy tắc `.vi` nằm ở
    # `pipeline/export.py:92` (handler suy nó từ `payload["translations"] is not
    # None`), và hai chỗ tự ghép tên là hai chỗ trôi khỏi nhau.
    stem = f"transcript-{translation.transcript_id}"
    name = artifact_name(stem, fmt, translated=True)

    _materialise(pathlib.Path(dirs["out"]), name, body)

    return PlainTextResponse(body, media_type=MEDIA_TYPES.get(fmt, "text/plain"))


def _materialise(out_dir: pathlib.Path, name: str, body: str) -> pathlib.Path | None:
    """Ghi bản xuất ra `<out_dir>/<name>`, CHỈ khi `resolve_within` chứng minh được.

    Đường dẫn ghi của route này phải đi qua cùng hàm containment với mọi chỗ GHI
    khác trong dự án (`domain/paths.py`), đúng như phép đọc đã đi từ Giai đoạn 1a:
    `name` hôm nay là `artifact_name()` của một `stem` dựng từ `int` cộng một
    `format` đã whitelist, nhưng "hôm nay an toàn" không phải một bất biến — đó
    chính là cách lỗi `stem` chưa lọc của 1a sống sót qua nhiều vòng review.

    Không chứng minh được thì BỎ lần ghi trên đĩa và trả `None`: thân phụ đề đã
    nằm trong `PlainTextResponse`, nên client vẫn nhận đủ nội dung (route này
    KHÔNG phục vụ tệp, đường tải tệp là `GET /api/export/{job_id}/download`), còn
    một `500` vì thư mục đầu ra không phân giải được sẽ biến một lần xuất đọc được
    thành một lỗi máy chủ.

    `newline="\\n"` như `pipeline/export.py::_write_utf8`: mở ở chế độ văn bản mặc
    định thì Windows dịch mọi `\\n` thành `\\r\\n`, và tệp ghi ở đây sẽ không còn
    khớp với tệp mà handler ghi cho CÙNG một bản dịch.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        target = resolve_within(out_dir, out_dir / name)
    except PathOutsideRoot:
        return None
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return target
