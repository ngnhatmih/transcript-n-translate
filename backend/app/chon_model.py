"""Chọn model có DÒ REGISTRY: ai chạy được, ai là mặc định, job nên dùng ai.

Vì sao tệp này KHÔNG nằm trong `domain/`: nó phải đọc `registry.json`
(`app.adapters.registry_file`) và danh mục engine (`app.registry`) — hai thứ mà
`tests/test_layer_boundary.py` cấm `domain/` import. Luật thuần (used → fallback) ở lại
`domain/model_settings.py`; phần biết về DANH MỤC nằm ở đây, cùng tầng với `app/registry.py`.

Một nguồn sự thật, hai tầng: `model_settings.chon` quyết định, tệp này CHUẨN BỊ đầu vào
cho nó (tập id chạy được, id mặc định) — không viết lại luật lần thứ hai.
"""
from __future__ import annotations

from app.adapters.registry_file import load_default_asr, load_default_mt
from app.domain import model_settings as ms
from app.domain.model_settings import Task, task_by_id
from app.registry import (ASR_DEFAULT_SETTING, MT_DEFAULT_SETTING,
                          default_asr_engine, default_mt_engine)


def ung_vien_ids(task_id: str, specs) -> list[str]:
    """Id của mọi ứng viên của một việc, theo thứ tự danh mục."""
    task = task_by_id(task_id)
    if task.nguon == "registry":
        return [s.id for s in specs if s.kind == task.kind]
    if task.nguon == "burn":
        return list(ms.BURN_ENCODERS)
    return list(task.co_dinh)


def san_sang(task_id: str, specs, *, co_gpu: bool | None = None) -> set[str]:
    """Tập id ĐO ĐƯỢC là chạy được NGAY BÂY GIỜ, cho một việc.

    `co_gpu` chỉ dùng cho việc `burn` (phép dò ffmpeg nằm ở `pipeline.tach_nen`); bên
    gọi truyền vào để tệp này không phải gọi ra pipeline.

    ⚠️ `capabilities["available"]` CHỈ được ghi cho engine DỊCH (`main._mark_availability`
    bỏ qua mọi kind khác). Engine ASR/OCR chạy trong tiến trình và việc dựng được chúng đã
    được ghim bằng test adapter thật, nên THIẾU khoá = chưa ai dò = coi như chạy được. Coi
    thiếu là `False` sẽ làm mọi job ASR/OCR bị từ chối vì một khoá không ai ghi.
    """
    task = task_by_id(task_id)
    if task.nguon == "registry":
        return {s.id for s in specs
                if s.kind == task.kind and s.capabilities.get("available", True)}
    if task.nguon == "burn":
        return {ms.BURN_X264} | ({ms.BURN_NVENC} if co_gpu else set())
    return set(task.co_dinh)


def mac_dinh_cua(task_id: str, specs, repos) -> str | None:
    """Model "Khôi phục" của một việc: đúng thứ pipeline dùng khi chưa ai đặt gì.

    `asr`/`dich` đi qua ĐÚNG `default_asr_engine`/`default_mt_engine` mà lúc khởi động
    dùng — hai chỗ tự tính là hai chỗ để lệch.
    """
    task: Task = task_by_id(task_id)
    if task_id == "asr":
        try:
            return default_asr_engine(
                specs, declared=load_default_asr(),
                configured=repos.get_setting(ASR_DEFAULT_SETTING) or None)
        except KeyError:
            pass
    if task_id == "dich":
        try:
            return default_mt_engine(
                specs, declared=load_default_mt(),
                configured=repos.get_setting(MT_DEFAULT_SETTING) or None)
        except KeyError:
            pass
    if task.nguon == "burn":
        return ms.BURN_NVENC
    if task.co_dinh:
        return task.co_dinh[0]
    #: Registry khai một id KHÔNG có trong danh sách `specs` này (test dựng danh mục rút
    #: gọn, hoặc registry.json vừa bị sửa): rơi về ứng viên ĐẦU — đúng luật "phần tử đầu"
    #: mà `default_mt_engine` đã dùng ở nhánh cuối của nó, không bịa id nào.
    ids = ung_vien_ids(task_id, specs)
    return ids[0] if ids else None


def giai_quyet(task_id: str, *, yeu_cau: str | None, specs, repos,
               co_gpu: bool | None = None) -> tuple[str | None, str]:
    """Model SẼ dùng cho một job: `(id, lý do)`.

    Thứ tự: yêu cầu của client (`yeu_cau`) → model đang dùng đã lưu → mặc định của
    registry. Rồi luật `chon` áp lên: nếu model đó KHÔNG chạy được thì lấy model dự phòng
    đã lưu; không có dự phòng chạy được thì trả `(None, "khong-co")` để bên gọi TỪ CHỐI job
    kèm lý do — thà từ chối lúc xếp hàng còn hơn chết ở tận worker.
    """
    da_biet = set(ung_vien_ids(task_id, specs))
    san = san_sang(task_id, specs, co_gpu=co_gpu)
    da_luu = ms.doc_cai_dat(repos)[task_id]
    used = yeu_cau or da_luu["used"] or mac_dinh_cua(task_id, specs, repos)
    fallback = da_luu["fallback"]
    if yeu_cau is not None and yeu_cau not in da_biet:
        return None, "khong-co"
    engine, ly_do = ms.chon(used, fallback, san)
    if engine is not None and engine == used:
        return engine, "theo-yeu-cau" if yeu_cau else "dang-dung"
    return engine, ly_do
