"""Route đọc/ghi bảng "Cài đặt model" — model ĐANG DÙNG + model DỰ PHÒNG mỗi việc.

Vì sao có route này thay vì để giao diện tự đoán: danh sách ứng viên phải là DANH MỤC
THẬT (`registry.json` + hai bộ mã hoá burn), và "engine nào sẽ thực sự chạy" phải do
backend trả lời — giao diện không được tự suy ra từ `available` rồi hiển thị một kết luận
khác với thứ worker sẽ dùng.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_repos, get_specs
from app import chon_model
from app.domain import model_settings as ms
from app.domain.model_settings import NHOM_DICH, TASKS, Task
from app.registry import EngineSpec, of_kind

router = APIRouter(prefix="/api", tags=["settings"])


class TaskSettingIn(BaseModel):
    """Một dòng người dùng gửi lên. Thiếu khoá nào thì khoá đó KHÔNG bị đụng."""

    used: str | None = None
    fallback: str | None = None


class SettingsIn(BaseModel):
    tasks: dict[str, TaskSettingIn] = Field(default_factory=dict)
    nhom_dich: str | None = None


def _ung_vien(task: Task, specs: list[EngineSpec]) -> list[dict]:
    """Ứng viên của MỘT việc, kèm `available` ĐO ĐƯỢC.

    `dich` trả ứng viên của CẢ HAI nhóm (MT và LLM): nhóm chỉ đổi thứ được HIỆN, còn
    hợp lệ hay không là chuyện của cả danh mục — nếu không, đổi nhóm qua lại sẽ làm lựa
    chọn cũ thành id "không hợp lệ" và người dùng mất nó mà không hiểu vì sao.
    """
    if task.nguon == "registry":
        ra = []
        for spec in of_kind(specs, task.kind):
            nhom = ms.nhom_cua_dich(spec.runtime) if task.id == "dich" else None
            ra.append({
                "id": spec.id,
                "label": spec.label,
                "available": bool(spec.capabilities.get("available", True)),
                "nhom": nhom,
            })
        return ra
    if task.nguon == "burn":
        # Import trong hàm: `pipeline.tach_nen` kéo numpy/soundfile, còn route này phải
        # import được ở nơi chỉ có phần lõi (test domain, công cụ đọc registry).
        from app.pipeline import tach_nen

        co_gpu = tach_nen.co_nvenc()
        return [
            {"id": ma, "label": nhan,
             #: `libx264` nằm trong ffmpeg nên LUÔN chạy được; `h264_nvenc` chỉ chạy khi
             #: phép dò của chính `tach_nen` (một khung 320×240 mã hoá thật) nói có.
             "available": ma == ms.BURN_X264 or co_gpu,
             "nhom": None}
            for ma, nhan in ms.BURN_ENCODERS.items()
        ]
    # `fixed`: một id cố định, luôn sẵn sàng (nó là model đi kèm sản phẩm).
    return [{"id": ma, "label": ms.NHAN_CO_DINH.get(ma, ma), "available": True,
             "nhom": None} for ma in task.co_dinh]


def _mac_dinh(task: Task, specs: list[EngineSpec], repos) -> dict[str, str | None]:
    """Giá trị "Khôi phục": đúng thứ pipeline dùng khi chưa ai đặt gì.

    Không tự suy lại — gọi `model_settings.mac_dinh_cua`, nơi `asr`/`dich` đi qua ĐÚNG
    `default_asr_engine`/`default_mt_engine` mà lúc khởi động dùng. Hai chỗ tự tính là
    hai chỗ để lệch nhau.
    """
    return {"used": chon_model.mac_dinh_cua(task.id, specs, repos), "fallback": None}


def _bang(repos, specs: list[EngineSpec]) -> dict:
    """Payload của `GET /api/model-settings`."""
    da_dat = ms.doc_cai_dat(repos)
    nhom_dich = ms.doc_nhom_dich(repos)
    ra = []
    for task in TASKS:
        ung_vien = _ung_vien(task, specs)
        san_sang = {u["id"] for u in ung_vien if u["available"]}
        mac_dinh = _mac_dinh(task, specs, repos)
        used = da_dat[task.id]["used"] or mac_dinh["used"]
        fallback = da_dat[task.id]["fallback"] or mac_dinh["fallback"]
        engine, ly_do = ms.chon(used, fallback, san_sang)
        ra.append({
            "id": task.id,
            "label": task.label,
            "nhom": task.nhom,
            "note": task.note,
            #: Một ứng viên ⇒ giao diện KHÔNG vẽ ô "dự phòng": ô chỉ có một lựa chọn là
            #: ô nói dối rằng có thể chọn.
            "locked": len(ung_vien) <= 1,
            "candidates": ung_vien,
            "used": used,
            "fallback": fallback,
            "mac_dinh": mac_dinh,
            #: Engine SẼ chạy ngay bây giờ, do backend quyết — không phải giao diện suy.
            "hieu_luc": {"engine": engine, "ly_do": ly_do},
        })
    return {"tasks": ra, "nhom_dich": nhom_dich, "nhom_dich_chon": list(NHOM_DICH)}


@router.get("/model-settings")
def get_model_settings(repos=Depends(get_repos), specs=Depends(get_specs)):
    """Bảng cài đặt model, dựng từ danh mục THẬT + lựa chọn đã lưu."""
    return _bang(repos, list(specs))


@router.put("/model-settings")
def put_model_settings(body: SettingsIn, repos=Depends(get_repos),
                       specs=Depends(get_specs)):
    """Ghi lựa chọn. Từ chối id không có trong danh mục CỦA CHÍNH VIỆC ĐÓ.

    Từ chối ở đây là chỗ duy nhất chặn được một cấu hình chắc chắn hỏng: worker nhận job
    với engine không tồn tại thì chết ở `KeyError` sau khi hàng `translations` đã ghi, và
    người dùng chỉ thấy "job failed" chứ không thấy "bạn chọn sai model".
    """
    hop_le: dict[str, set[str]] = {}
    for task in TASKS:
        hop_le[task.id] = {u["id"] for u in _ung_vien(task, list(specs))}

    for task_id, gia_tri in body.tasks.items():
        if task_id not in hop_le:
            raise HTTPException(
                422, f"việc {task_id!r} không có trong bảng cài đặt model "
                     f"(có: {sorted(hop_le)})")
        for ten in ("used", "fallback"):
            gia = getattr(gia_tri, ten)
            if gia is not None and gia not in hop_le[task_id]:
                raise HTTPException(
                    422, f"model {gia!r} không có trong danh mục của việc {task_id!r} "
                         f"(có: {sorted(hop_le[task_id])})")
        if (gia_tri.used is not None and gia_tri.fallback is not None
                and gia_tri.used == gia_tri.fallback):
            raise HTTPException(
                422, f"model đang dùng và model dự phòng của {task_id!r} TRÙNG nhau "
                     f"({gia_tri.used!r}) — dự phòng phải là một model KHÁC")

    try:
        ms.ghi_cai_dat(
            repos,
            cap_nhat={k: {"used": v.used, "fallback": v.fallback}
                      for k, v in body.tasks.items()},
            nhom_dich=body.nhom_dich,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _bang(repos, list(specs))
