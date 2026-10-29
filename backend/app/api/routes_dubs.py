"""Hai route của đường lồng tiếng: xếp job + tải file.

Vì sao chỉ hai, và vì sao KHÔNG có route "trạng thái lồng tiếng":
`POST /api/jobs` đã là đường xếp job của MỌI loại, và trạng thái của một job `dub` đã nằm trong
`GET /api/jobs` như mọi job khác — giao diện lọc `type === "dub"` là đủ. Thêm một route trạng
thái cho riêng dub là nguồn sự thật thứ hai cho cùng một câu hỏi.

Tên tệp là TẤT ĐỊNH (`dub-<translation_id>.<định dạng>`), nên route tải không cần bảng DB:
file có thì trả, không có thì 404 kèm câu nói phải làm gì.
"""
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import get_dirs, get_repos, get_worker
from app.pipeline.dub import DUOI_TAI_DUOC

router = APIRouter(prefix="/api/dubs", tags=["dubs"])

#: Engine TTS của đường này. KHÔNG phải một hàng registry: chỉ có MỘT engine TTS, và nó chạy ở
#: venv riêng (`scripts/tts_batch.py`), nên một hàng registry chỉ để hiện trong danh sách engine
#: là dữ liệu không ai đọc.
ENGINE_TTS = "vieneu-v3-turbo"


class DubIn(BaseModel):
    translation_id: int = Field(ge=1)
    voice: str | None = None
    so_dong: int | None = Field(default=None, ge=1)
    #: Trộn NHẠC/TIẾNG ĐỘNG của video gốc vào bản lồng, rồi xuất thêm `dub-<tid>.mp4`.
    #: `None` = theo mặc định của môi trường (`DubHandler(tron_nen=...)`); `False` = chỉ
    #: bản lồng sạch; `True` = bắt buộc trộn. Đo được giá của `True`: +66 s và 555 MiB
    #: VRAM cho phim 20,8 phút — nên nó là lựa chọn THEO JOB, không phải mặc định ngầm.
    tron_nen: bool | None = None


@router.post("", status_code=201)
def create_dub(body: DubIn, repos=Depends(get_repos), worker=Depends(get_worker),
               dirs=Depends(get_dirs)):
    """Xếp một job `dub` cho MỘT bản dịch. Từ chối sớm khi chưa có bản dịch hoặc chưa có worker."""
    try:
        ban = repos.get_translation(body.translation_id)
    except LookupError as exc:
        raise HTTPException(404, f"bản dịch {body.translation_id} không tồn tại") from exc
    if not (ban.segments or []):
        raise HTTPException(409, f"bản dịch #{body.translation_id} chưa có dòng nào để lồng tiếng")
    if worker is None:
        raise HTTPException(409, "không có worker trong tiến trình này — job sẽ không bao giờ chạy")

    # TỪ CHỐI SỚM khi máy này không có đường TTS. Đo được: image Linux không có `vieneu`, nên
    # job được nhận rồi `failed` ở 5% và người dùng chỉ biết sau khi chờ. `san_sang()` là câu
    # trả lời của chính handler (một nguồn sự thật), không phải một phép dò thứ hai ở route.
    # ⚠️ Một handler tự dựng (test) không khai đường dẫn thì `san_sang()` trả `True` — nó không
    # có ý kiến gì về môi trường, và đoán hộ nó là bịa.
    handler = (getattr(worker, "handlers", None) or {}).get("dub")
    san_sang = getattr(handler, "san_sang", None)
    if san_sang is not None:
        duoc, vi_sao = san_sang()
        if not duoc:
            raise HTTPException(409, vi_sao)

    from app.domain.models import Job

    job = Job(id=None, workspace=2, type="dub", engine=ENGINE_TTS,
              phase=f"dub:{ENGINE_TTS}",
              payload={"translation_id": body.translation_id, "voice": body.voice,
                       "so_dong": body.so_dong, "tron_nen": body.tron_nen})
    job_id = repos.add_job(job)
    return {"job": {"id": job_id, "type": "dub", "state": repos.get_job(job_id).state,
                    "translation_id": body.translation_id}}


def _thu_muc(dirs) -> pathlib.Path:
    """Thư mục chứa bản lồng tiếng — CÙNG nguồn với handler (`output/dubs`)."""
    return pathlib.Path(dirs["out"]) / "dubs"


@router.get("/{translation_id}/plan")
def plan(translation_id: int, dirs=Depends(get_dirs)):
    """Kế hoạch tốc độ của lượt lồng GẦN NHẤT — số đo TỪNG dòng cho bảng ở màn Lồng tiếng.

    `null` (không phải 404) khi chưa lồng lần nào: "chưa có số đo" và "không có bản dịch" là hai
    câu khác nhau, và màn hình phải phân biệt được. Tệp là DẪN XUẤT của một lượt chạy (xem
    `DubHandler._ghi_ke_hoach`) — thiếu nó thì giao diện nói chưa đo, KHÔNG bịa số.
    """
    import json as _json

    tep = _thu_muc(dirs) / f"dub-{translation_id}.plan.json"
    if not tep.is_file():
        return None
    return _json.loads(tep.read_text(encoding="utf-8"))


@router.get("/{translation_id}/take")
def take(translation_id: int, i: int, dirs=Depends(get_dirs)):
    """NGHE THỬ một dòng: trả wav của take đã ép tốc độ cho dòng `i` của bản dịch.

    Vì sao cần: người dùng phải nghe được một dòng TRƯỚC khi chờ cả clip (461 dòng ≈ 5–7 phút).
    Route này KHÔNG chạy TTS — nó chỉ trả đoạn đã cắt từ master, nên nó không thể sinh ra một
    lượt lồng thứ hai. Dòng nào không có trong kế hoạch thì 404 kèm câu nói phải làm gì.
    """
    import json as _json

    import soundfile as sf

    ke_hoach = _thu_muc(dirs) / f"dub-{translation_id}.plan.json"
    master = _thu_muc(dirs) / f"dub-{translation_id}.wav"
    if not ke_hoach.is_file() or not master.is_file():
        raise HTTPException(404, f"chưa có bản lồng tiếng cho bản dịch #{translation_id} "
                                 f"(chạy lồng tiếng trước)")
    du_lieu = _json.loads(ke_hoach.read_text(encoding="utf-8"))
    dong = next((d for d in du_lieu.get("dong", []) if d.get("i") == i), None)
    if dong is None:
        raise HTTPException(404, f"bản lồng tiếng của bản dịch #{translation_id} không có dòng {i}")

    # Cắt ĐÚNG đoạn của dòng: từ `start` tới `start + take/tốc độ` — take đã ép tốc độ nên dài
    # hơn `take` gốc một chút, và lấy theo `end` của dòng là sai khi take ngắn hơn chỗ.
    mau, sr = sf.read(str(master), dtype="float32", always_2d=False)
    if mau.ndim > 1:
        mau = mau.mean(axis=1)
    dai = float(dong["take"]) / max(float(dong["speed"]), 1e-6)
    dau = max(0, int(round(float(dong["start"]) * sr)))
    cuoi = min(len(mau), dau + max(1, int(round(dai * sr))))
    doan = mau[dau:cuoi]
    if doan.size == 0:
        raise HTTPException(404, f"dòng {i} của bản dịch #{translation_id} không có tiếng")

    import tempfile

    tam = pathlib.Path(tempfile.mkdtemp(prefix="take-")) / f"take-{translation_id}-{i}.wav"
    sf.write(str(tam), doan, sr, subtype="PCM_16")
    # ⚠️ KHÔNG truyền `filename=` ở đây. ĐO ĐƯỢC: `FileResponse(..., filename=...)` khiến
    # Starlette thêm `Content-Disposition: attachment`, và Chrome coi URL đó là một lượt TẢI
    # XUỐNG chứ không phải nguồn phát. Triệu chứng đo trên app thật: thẻ `<audio>` có `src`
    # đúng, `play()` trả Promise nhưng KHÔNG BAO GIỜ resolve, `readyState: 0`,
    # `networkState: 2` (LOADING), `duration: null`, và Resource Timing RỖNG — chưa từng có
    # request nào. Cùng URL đó qua `fetch` trả đủ `200 · audio/wav · 245804` byte, và thẻ
    # `<audio>` dựng tay cũng treo y hệt, nên lỗi ở HEADER chứ không ở React.
    #
    # Route `download` bên dưới VẪN truyền `filename=`: ở đó `attachment` là đúng ý (bấm là
    # lưu tệp). Chỉ route NGHE mới cần `inline`.
    return FileResponse(tam, media_type="audio/wav",
                        headers={"Content-Disposition": f'inline; filename="{tam.name}"'})


@router.get("/{translation_id}/download")
def download(translation_id: int, format: str = "wav", dirs=Depends(get_dirs)):
    """Tải một định dạng của bản lồng tiếng. 404 nói RÕ: chưa lồng hay sai định dạng."""
    dinh_dang = format.lower().lstrip(".")
    # `DUOI_TAI_DUOC` chứ không `DINH_DANG`: `mp4` chỉ tồn tại khi job chạy với
    # `tron_nen`, và nó KHÔNG sinh từ master audio — xem docstring hằng số đó.
    if dinh_dang not in DUOI_TAI_DUOC:
        raise HTTPException(404, f"định dạng {format!r} không hỗ trợ "
                                 "(có: " + ", ".join(DUOI_TAI_DUOC) + ")")
    tep = _thu_muc(dirs) / f"dub-{translation_id}.{dinh_dang}"
    if not tep.is_file():
        raise HTTPException(404, f"chưa có bản lồng tiếng cho bản dịch #{translation_id} "
                                 f"(chạy lồng tiếng trước)")
    return FileResponse(tep, media_type="application/octet-stream", filename=tep.name)
