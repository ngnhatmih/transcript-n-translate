"""Cài đặt MODEL cho từng việc: model ĐANG DÙNG và model DỰ PHÒNG.

Luật duy nhất (chủ dự án đặt ra): **model dự phòng chỉ được dùng khi model đang dùng
KHÔNG chạy được**. Không có luật thứ hai kiểu "thử rồi thấy lỗi thì đổi" — một lượt
chạy đã tốn 5–7 phút TTS mà đổi model giữa đường thì kết quả là hai giọng trong một
phim.

## Vì sao là `settings` chứ không phải `registry.json`

`registry.json` khai CÓ NHỮNG ENGINE NÀO (dữ liệu của máy, đi kèm code). Còn "hôm nay
tôi muốn dịch bằng LLM, dự phòng bằng MT" là lựa chọn của NGƯỜI DÙNG trên máy đó — cùng
khuôn với `default_asr_engine`/`default_mt_engine` đã có sẵn trong bảng `settings`. Hai
thứ khác nhau nên nằm hai chỗ, và `registry.json` vẫn là nguồn duy nhất của danh mục.

## Sáu việc, và ba kiểu nguồn ứng viên

| việc | nguồn ứng viên | ghi chú |
|---|---|---|
| `ocr` | registry, kind `ocr` | hiện chỉ có 1 ứng viên |
| `asr` | registry, kind `asr` | |
| `dich` | registry, kind `mt` | chia hai NHÓM: MT (in-process) và LLM (ollama/http) |
| `tts` | hằng số | hiện chỉ có 1: `vieneu-v3-turbo` |
| `tach_giong` | hằng số | hiện chỉ có 1: `htdemucs` |
| `burn` | hằng số | `h264_nvenc` / `libx264` — việc duy nhất mà "dự phòng" đang là hành vi thật |

Ứng viên ĐƠN (ocr/tts/tách giọng) vẫn hiện trong bảng, nhưng `locked=True` và giao diện
KHÔNG vẽ ô "dự phòng" cho chúng: một ô chỉ có một lựa chọn là một ô nói dối rằng có thể
chọn. Muốn thêm ứng viên thì thêm dữ liệu (registry hoặc hằng số ở đây), không sửa route.

## Nhóm MT / LLM

`dich` chia theo `EngineSpec.runtime` — dữ liệu có sẵn, không thêm trường mới:
`inprocess` là MT (Marian/OPUS-MT, chạy trong tiến trình, không cần mạng); `ollama` và
`http` là LLM (cần model đã pull / endpoint sống). Nhóm đang chọn nằm ở setting
`model.dich.nhom`, và nó chỉ ảnh hưởng DANH SÁCH ứng viên hiện ra, không ảnh hưởng engine
đã lưu: đổi nhóm rồi quay lại nhóm cũ vẫn thấy lựa chọn cũ.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Engine TTS của sản phẩm. Một nguồn duy nhất — `routes_dubs` và bảng cài đặt đọc CÙNG
#: hằng số này, nên nhãn trong giao diện không thể lệch với engine thật được xếp job.
TTS_ENGINE = "vieneu-v3-turbo"

#: Model tách giọng/nhạc khỏi tiếng gốc (`pipeline/tach_nen.py::tach_nen`, htdemucs).
SEP_ENGINE = "htdemucs"

#: Hai bộ mã hoá của bước BURN. `h264_nvenc` cần driver NVIDIA + container có capability
#: `video`; `libx264` chạy trên mọi máy nên nó là DỰ PHÒNG tự nhiên — và đây chính là
#: hành vi `tach_nen.co_nvenc()` đã làm bằng tay trước khi có bảng cài đặt này.
BURN_NVENC = "h264_nvenc"
BURN_X264 = "libx264"
BURN_ENCODERS: dict[str, str] = {
    BURN_NVENC: "h264_nvenc (GPU)",
    BURN_X264: "libx264 (CPU)",
}

#: Tiền tố khoá trong bảng `settings`. Một chỗ duy nhất để đọc/ghi.
KEY_USED = "model.{task}.used"
KEY_FALLBACK = "model.{task}.fallback"
KEY_NHOM_DICH = "model.dich.nhom"

NHOM_MT = "mt"
NHOM_LLM = "llm"
NHOM_DICH = (NHOM_MT, NHOM_LLM)

#: `runtime` của engine DỊCH → nhóm người dùng nhìn thấy.
_NHOM_CUA_RUNTIME = {"inprocess": NHOM_MT, "ollama": NHOM_LLM, "http": NHOM_LLM}


@dataclass(frozen=True)
class Task:
    """Một dòng trong bảng "Cài đặt model"."""

    id: str
    label: str
    nhom: str
    #: `registry` = ứng viên lấy từ `specs` theo `kind`; `fixed` = hằng số trong tệp này;
    #: `burn` = hai bộ mã hoá của `pipeline/tach_nen.py`.
    nguon: str
    #: Chỉ có nghĩa khi `nguon == "registry"`.
    kind: str = ""
    #: Ứng viên khi `nguon == "fixed"` (một hoặc nhiều id cố định).
    co_dinh: tuple[str, ...] = ()


TASKS: tuple[Task, ...] = (
    Task("ocr", "OCR", "Phiên âm", "registry", kind="ocr"),
    Task("asr", "ASR", "Phiên âm", "registry", kind="asr"),
    Task("dich", "Dịch", "Dịch", "registry", kind="mt"),
    Task("tts", "TTS", "Lồng tiếng", "fixed", co_dinh=(TTS_ENGINE,)),
    Task("tach_giong", "Tách giọng", "Ghép nền", "fixed", co_dinh=(SEP_ENGINE,)),
    Task("burn", "Burn phụ đề", "Ghép nền", "burn"),
)

#: Nhãn cho ứng viên cố định (registry đã có `label` riêng của nó).
NHAN_CO_DINH = {
    TTS_ENGINE: "VieNeu v3 Turbo",
    SEP_ENGINE: "htdemucs",
    **BURN_ENCODERS,
}


def task_by_id(task_id: str) -> Task:
    for t in TASKS:
        if t.id == task_id:
            return t
    raise KeyError(f"việc {task_id!r} không có trong bảng cài đặt model")


def nhom_cua_dich(runtime: str) -> str | None:
    """Nhóm hiển thị của một engine dịch. `None` = runtime lạ (không đoán hộ)."""
    return _NHOM_CUA_RUNTIME.get(runtime)


def chon(used: str | None, fallback: str | None,
         san_sang: set[str]) -> tuple[str | None, str]:
    """Engine SẼ DÙNG, và một trong ba nhãn: `dang-dung` | `du-phong` | `khong-co`.

    Đây là toàn bộ luật của bảng cài đặt, viết thành hàm THUẦN để test được bằng số:

      * model đang dùng chạy được            ⇒ dùng nó (`dang-dung`);
      * không chạy được, dự phòng chạy được  ⇒ dùng dự phòng (`du-phong`);
      * cả hai không chạy được               ⇒ `None` (`khong-co`) — bên gọi phải NÓI RA
        cả hai id và lý do, không được lặng lẽ bỏ qua bước đó.

    `san_sang` là tập id ĐO ĐƯỢC là chạy được ngay bây giờ (model đã pull, endpoint sống,
    GPU có NVENC…). Hàm này không tự dò: nó không biết máy nào đang chạy nó.
    """
    if used and used in san_sang:
        return used, "dang-dung"
    if fallback and fallback in san_sang:
        return fallback, "du-phong"
    return None, "khong-co"


def doc_cai_dat(repos) -> dict[str, dict[str, str | None]]:
    """Đọc `{task_id: {"used": ..., "fallback": ...}}` từ bảng `settings`.

    Chuỗi RỖNG được coi là "chưa đặt", cùng lý do với `default_*` đã có: một ô bị xoá
    nội dung trong giao diện phải quay về mặc định, không phải thành một id rỗng được
    xếp vào job.
    """
    ra: dict[str, dict[str, str | None]] = {}
    for task in TASKS:
        used = repos.get_setting(KEY_USED.format(task=task.id)) or None
        fallback = repos.get_setting(KEY_FALLBACK.format(task=task.id)) or None
        ra[task.id] = {"used": used, "fallback": fallback}
    return ra


def doc_nhom_dich(repos) -> str:
    """Nhóm dịch đang chọn; giá trị lạ (tay sửa DB) rơi về `mt`, không ném."""
    nhom = (repos.get_setting(KEY_NHOM_DICH) or "").strip()
    return nhom if nhom in NHOM_DICH else NHOM_MT


def chon_burn(repos, *, co_gpu: bool) -> tuple[str, str]:
    """Bộ mã hoá của bước burn: `(id, lý do)`. Không bao giờ trả `None`.

    `libx264` nằm trong ffmpeg nên LUÔN chạy được, tức luôn có đường cùng — kể cả khi
    người dùng đặt `used = h264_nvenc` trên máy không có NVENC.
    """
    san = {BURN_X264} | ({BURN_NVENC} if co_gpu else set())
    da_luu = doc_cai_dat(repos)["burn"]
    used = da_luu["used"] or (BURN_NVENC if co_gpu else BURN_X264)
    engine, ly_do = chon(used, da_luu["fallback"] or BURN_X264, san)
    return engine or BURN_X264, ly_do


def ghi_cai_dat(repos, *, cap_nhat: dict[str, dict[str, str | None]],
                nhom_dich: str | None = None) -> None:
    """Ghi từng khoá. KHÔNG xoá khoá nào — "Khôi phục" ghi lại giá trị mặc định."""
    for task_id, gia_tri in cap_nhat.items():
        task_by_id(task_id)  # ném KeyError nếu giao diện gửi việc lạ
        for khoa, ten in ((KEY_USED, "used"), (KEY_FALLBACK, "fallback")):
            if ten in gia_tri:
                repos.set_setting(khoa.format(task=task_id), gia_tri[ten] or "")
    if nhom_dich is not None:
        if nhom_dich not in NHOM_DICH:
            raise ValueError(
                f"nhóm dịch {nhom_dich!r} không hợp lệ (có: {sorted(NHOM_DICH)})")
        repos.set_setting(KEY_NHOM_DICH, nhom_dich)
