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

from app.api.deps import get_chimera_plan, get_dirs, get_repos, get_specs
from app.api.routes_jobs import _job_json
from app.domain.chimera import Baseline, cost_json
from app.domain.job_state import phase_of
from app.domain.models import Job
from app.domain.mt_qa import QaLimits, cps_row
from app.domain.paths import PathOutsideRoot, resolve_within
from app.domain.staleness import is_stale, translation_summary_json
from app.pipeline.export import FORMATS, MEDIA_TYPES, artifact_name
from app.registry import by_id

router = APIRouter(prefix="/api/translations", tags=["translations"])


class CreateIn(BaseModel):
    transcript_id: int
    engine: str
    target_lang: str = "vi"
    #: Bật chế độ CHIMERA (§8.7.5, spec UI §4.5). Khi bật, `engine` chỉ còn là
    #: một phép kiểm hợp lệ: bản dịch do KẾ HOẠCH Chimera của registry quyết định,
    #: và `translations.engine` ghi engine PHA — engine thật sự viết ra chữ được
    #: giữ. Ghi id người dùng chọn ở đây là để hàng bản dịch tự nhận công của một
    #: engine không viết chữ nào.
    chimera: bool = False


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


def _baseline_for(repos, transcript_id: int) -> Baseline | None:
    """Chi phí THẬT của MỘT lượt dịch một-engine trên CHÍNH kênh này.

    Đây là CƠ SỞ ĐO của cảnh báo chi phí (§4.5, §9.2): thời gian và token của một
    hàng `translations` đã `done` của cùng transcript, chia cho số đoạn của nó rồi
    nhân lên. Không có hàng nào như vậy thì trả `None` và cảnh báo NÓI RA là chưa
    đo được — bịa một con số từ số đoạn là đúng thứ mà "phải ĐO ĐƯỢC" cấm.

    ⚠️ Hàng CHIMERA bị LOẠI khỏi cơ sở đo. Một lượt Chimera tốn `N+1` lời gọi, nên
    lấy nó làm mốc rồi nhân thêm `N+1` lần nữa là nhân đôi hệ số và thổi phồng cảnh
    báo lên gấp `N+1`. Nay trước sau gì cũng chỉ có một lượt dịch thường để so.
    """
    for row in repos.list_translations_for_transcript(transcript_id):
        if row.status != "done":
            continue
        try:
            full = repos.get_translation(row.id)
        except LookupError:
            continue
        if full.chimera is not None or full.duration_ms is None or not full.segments:
            continue
        return Baseline(translation_id=full.id, engine=full.engine,
                        segments=len(full.segments), duration_ms=full.duration_ms,
                        tokens_in=full.tokens_in, tokens_out=full.tokens_out)
    return None


@router.post("", status_code=201)
def create_translation(body: CreateIn, repos=Depends(get_repos),
                       specs=Depends(get_specs),
                       chimera_plan=Depends(get_chimera_plan)):
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

    chimera_data = None
    if body.chimera:
        # Ba lời từ chối ở đây đều là 409 TRƯỚC khi ghi, cùng lớp với I-3: một job
        # Chimera được xếp rồi mới chết ở worker là một hàng `translations` nằm lại
        # ở `queued` mà không ai giải thích.
        if chimera_plan is None or chimera_plan.declared == 0:
            raise HTTPException(
                409, "chế độ Chimera chưa dùng được: registry không khai báo ứng "
                     "viên nào (khoá `chimera.candidates`)")
        if chimera_plan.run_count == 0:
            need = ", ".join(sorted({c.engine for c in chimera_plan.candidates}))
            raise HTTPException(
                409, f"chế độ Chimera chưa dùng được: KHÔNG ứng viên nào chạy được "
                     f"(cần model của: {need}; xem `GET /api/chimera/cost`)")
        # `engine` của hàng = engine PHA: nó là engine THẬT SỰ viết ra chữ được giữ
        # lại, nên nó là câu trả lời đúng cho cột `engine`. Ai viết thì xem
        # `chimera.candidates[].engine` — đó là chỗ kể cả câu chuyện.
        try:
            spec = by_id(specs, chimera_plan.merge_engine)
        except KeyError as exc:
            raise HTTPException(
                409, f"engine pha {chimera_plan.merge_engine!r} không có trong registry"
            ) from exc
        if not spec.capabilities.get("available"):
            raise HTTPException(
                409, f"engine pha {chimera_plan.merge_engine!r} chưa sẵn sàng: model "
                     f"chưa được pull, hoặc runtime không phục vụ được")

        # CẢNH BÁO CHI PHÍ được TÍNH Ở ĐÂY, ghi vào hàng, và vì thế nó là CÙNG con
        # số mà giao diện đã hiện TRƯỚC khi người dùng bấm. Tính lại ở cuối lượt
        # chạy là so hai con số khác nhau rồi gọi đó là "đối chiếu".
        cost = cost_json(chimera_plan, segments=len(transcript.segments),
                         baseline=_baseline_for(repos, transcript.id))
        chimera_data = {
            "enabled": True,
            "declared": cost["declared"],
            "run_count": cost["runnable"],
            "calls_per_batch": cost["calls_per_batch"],
            "merge_engine": chimera_plan.merge_engine,
            "estimate": cost["estimate"],
            "estimate_basis": cost["estimate_basis"],
            "baseline": cost["baseline"],
            "segments": cost["segments"],
        }

    translation_id = repos.add_translation(
        transcript_id=transcript.id,
        # Version mà bản dịch này dịch TỪ, không phải version hiện tại lúc job
        # chạy: job có thể chạy sau khi người dùng sửa transcript, và khi đó bản
        # dịch phải được coi là lệch thời.
        transcript_version=transcript.version,
        engine=spec.id,
        target_lang=body.target_lang,
        segments=[],
        # Một lượt Chimera được viết bởi prompt PHA, không phải prompt dịch: hai
        # chuỗi khác nhau, và `translations.prompt_version` tồn tại để phân biệt
        # chúng. Cả hai giá trị đều là DỮ LIỆU do composition root đặt vào
        # `spec.capabilities` — tầng API không import `app.adapters`.
        prompt_version=spec.capabilities.get(
            "chimera_prompt_version" if body.chimera else "prompt_version", "unknown"),
        glossary_version=repos.glossary_version(),
        chimera=chimera_data,
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


@router.get("/{translation_id}")
def get_translation(translation_id: int, repos=Depends(get_repos)):
    """Chi tiết MỘT bản dịch: đoạn ĐÃ DỊCH + CPS dạng SỐ — nguồn cho §4.3.

    Vì sao cần một route riêng thay vì thêm khoá vào `GET /api/translations`: hình
    dạng của một phần tử trong danh sách đã được KÝ thành hợp đồng (`contract.test.ts`
    ghim nó trên backend thật), nên mở rộng nó là phá hợp đồng đã ký. Trước route
    này KHÔNG JSON nào mang `segments` của bản dịch, và `qa_issues` — nơi chuỗi
    `cps:` sống — không xuất hiện trong MỘT response HTTP nào, nên màn Đối chiếu
    không có nguồn nào cho cột phải và cho cột CPS.

    CPS KHÔNG được tính lại ở đây. `mt_qa.cps_row` là chỗ DUY NHẤT tính nó, và cũng
    là chỗ sinh chuỗi `cps:` trong `qa_issues`, nên client không phải parse một chuỗi
    hiển thị để lấy con số nó hiển thị.

    ⚠️ ĐIỀU KIỆN của "cùng một chỗ tính", nói cho đúng (ERRATA #15 mục 2: một lời
    giải thích cơ chế cũng là một lời khai): hai đường chỉ chắc chắn khớp nhau khi
    `QaLimits` dùng để SINH `qa_issues` đúng bằng `QaLimits()` mà route dùng ở đây.
    Hôm nay đúng như vậy — `main.py` dựng `TranslateHandler(repos, mt_engines)` và
    không truyền `limits=`, nên cả hai đi bằng mặc định. Nhưng ngưỡng **không được
    lưu** cùng hàng `translations` (`schema.py` không có cột nào cho nó), nên một
    đường chạy với `QaLimits` tuỳ biến sẽ làm con số của route lệch khỏi chuỗi đã
    ghi trong `qa_issues` — và lệch IM LẶNG.
    `ponytail:` TRẦN: "con số của route = con số của `qa_issues`" chỉ đúng trong
    điều kiện `QaLimits()` mặc định. ĐƯỜNG NÂNG CẤP: lưu ngưỡng (`max_cps`) cùng hàng
    `translations` lúc `TranslateHandler` ghi kết quả, rồi route đọc ngưỡng ĐÃ LƯU
    thay vì dựng `QaLimits()` mới.

    `segments` là đoạn của BẢN DỊCH, nhưng cửa sổ thời gian để đo CPS vẫn là cửa sổ
    NGUỒN (`mt_qa._window`): đó mới là khoảng người xem thật sự thấy dòng dịch.
    Đoạn nguồn không có `i` tương ứng thì `cps_row(t, t)` rơi về cửa sổ bản dịch —
    quy tắc dự phòng đã có sẵn, không phải quy tắc mới.

    `cps.rows[].over` là thứ client phải đọc, KHÔNG phải tự so `cps > max_cps`:
    `over` so trên giá trị chưa làm tròn, còn `cps` đã làm tròn để hiển thị nên ở
    đúng biên (21,04 CPS ⇒ hiện 21,0) phép so của client sẽ nói sai.
    """
    row = _require_translation(repos, translation_id)
    transcript = _require_transcript(repos, row.transcript_id)
    limits = QaLimits()
    source_by_id = {s.i: s for s in transcript.segments}
    rows = [cps_row(source_by_id.get(t.i, t), t, limits=limits)
            for t in row.segments]
    return {
        **_summary(row, stale=is_stale(transcript.version, row.transcript_version)),
        # Dấu vết CHIMERA (§4.5): kế hoạch N ứng viên, ƯỚC LƯỢNG chi phí đã hiện
        # TRƯỚC khi bấm, và số đo THẬT của từng ứng viên + lượt pha. `None` = hàng
        # này không chạy ở chế độ Chimera — KHÁC `{}` ("chạy mà chưa có dữ liệu").
        "chimera": getattr(row, "chimera", None),
        "segments": [s.to_json() for s in row.segments],
        "cps": {
            "max_cps": limits.max_cps,
            "rows": [
                {
                    "i": r.i,
                    "chars": r.chars,
                    "window": r.window,
                    "cps": None if r.cps is None else round(r.cps, 1),
                    "max_cps": r.max_cps,
                    "over": r.over,
                }
                for r in rows
            ],
        },
    }


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


#: Router RIÊNG cho chế độ CHIMERA (§8.7.5, spec UI §4.5).
#:
#: Không nằm trên `router` ở trên (router đó mang `prefix="/api/translations"`), và
#: cũng không nằm trong `routes_translations.export_router`: nó là một TÀI NGUYÊN
#: khác — "chế độ Chimera tốn bao nhiêu" không thuộc về một bản dịch nào cả, nên
#: nó phải trả lời được TRƯỚC khi có bản dịch nào tồn tại (§4.5: cảnh báo chi phí
#: hiện trước khi người dùng bấm).
chimera_router = APIRouter(prefix="/api/chimera", tags=["chimera"])


@chimera_router.get("/cost")
def chimera_cost(transcript_id: int, repos=Depends(get_repos),
                 chimera_plan=Depends(get_chimera_plan)):
    """CẢNH BÁO CHI PHÍ của một lượt Chimera trên kênh này — ĐO ĐƯỢC, không câu chữ.

    Trả về: sáu ứng viên ĐÃ KHAI kèm cờ chạy được và lý do không chạy được, số ứng
    viên THẬT SỰ chạy, số lượt chạm engine cho một lô (`N ứng viên + 1 lượt pha`),
    và ƯỚC LƯỢNG thời gian/token suy từ một bản dịch thường ĐÃ CHẠY XONG trên chính
    kênh này (`estimate_basis` nói rõ nó đo từ đâu).

    `estimate: null` là một câu trả lời HỢP LỆ và đi kèm lý do — "chưa đo được"
    khác hẳn "bằng không", và cảnh báo chi phí mà bịa số thì không cảnh báo được gì.
    """
    if chimera_plan is None or chimera_plan.declared == 0:
        raise HTTPException(
            503, "registry chưa khai báo chế độ Chimera (khoá `chimera.candidates`)")
    transcript = _require_transcript(repos, transcript_id)
    return cost_json(chimera_plan, segments=len(transcript.segments),
                     baseline=_baseline_for(repos, transcript.id))


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
