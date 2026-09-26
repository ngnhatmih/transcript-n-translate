"""Kiểu dữ liệu của registry và các phép tra cứu. Thuần, không đọc tệp.

Việc đọc tệp nằm ở adapters/registry_file.py.

Một ngoại lệ CÓ GHI NHẬN cho tính "thuần" ở trên: `ollama_available()` dò sống
tiến trình Ollama. Nó nằm đây theo đúng Step 4 của brief Task 12, và nó KHÔNG
kéo `httpx` vào lúc import (import nằm trong hàm) — module này vẫn import được ở
mọi tầng, kể cả nơi `httpx` chưa cài. Nếu sau này có chỗ dò Ollama dùng chung
(`app/api/routes_registry.probe_ollama` cũng đang dò), gộp chúng lại là việc của
task dọn dẹp, không phải lý do để bịa thêm một tầng nữa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.domain.job_state import phase_of

# `kind` là loại ENGINE trong registry; `phase_of` nhận loại JOB. Hai từ vựng
# này KHÁC nhau: engine dịch có kind "mt" nhưng job của nó là "translate"
# (plan §JOB_TYPES: ingest | asr | translate | export). Ánh xạ tường minh ở đây
# để `phase_key` không bao giờ tự bịa ra một tiền tố thứ ba.
_JOB_TYPE_OF_KIND = {"asr": "asr", "mt": "translate"}


@dataclass(frozen=True)
class EngineSpec:
    """Mô tả một engine. `frozen=True` chỉ chặn GÁN thuộc tính.

    `capabilities` và `opts` vẫn là dict nên `spec.capabilities[...] = ...` và
    `spec.opts[...] = ...` VẪN sửa được tại chỗ, và sửa thì hỏng cấu hình dùng
    chung cho mọi nơi giữ danh sách spec đã nạp. Hãy coi hai trường này là chỉ
    đọc. Việc cưỡng chế bằng kiểu bất biến thuộc task VRAM arbitration.
    """

    id: str
    label: str
    kind: str            # 'asr' | 'mt'  — loại ENGINE, không phải loại job
    runtime: str         # 'inprocess' | 'ollama'
    model_ref: str
    vram_mb: int
    langs: tuple[str, ...]
    capabilities: dict = field(default_factory=dict)
    opts: dict = field(default_factory=dict)

    @property
    def phase_key(self) -> str:
        """Khoá giai đoạn của hàng đợi. Bằng ĐÚNG chuỗi `Job.phase` lưu.

        `next_queued_for_phase` tra bằng equality, nên lệch một chữ cái là hàng
        đợi đứng im mà không ném exception. Vì vậy khoá được dựng qua chính
        `phase_of` với loại job thật, không tự nối chuỗi từ `kind`.
        """
        return phase_of(_JOB_TYPE_OF_KIND[self.kind], self.id)


def of_kind(specs: Iterable[EngineSpec], kind: str) -> list[EngineSpec]:
    return [s for s in specs if s.kind == kind]


def by_id(specs: Iterable[EngineSpec], engine_id: str) -> EngineSpec:
    for spec in specs:
        if spec.id == engine_id:
            return spec
    raise KeyError(f"engine {engine_id!r} không có trong registry")


#: Khoá trong `registry.json` khai báo engine ASR mặc định.
DEFAULT_ASR_KEY = "default_asr"

#: Khoá trong `registry.json` khai báo engine DỊCH mặc định (R58).
DEFAULT_MT_KEY = "default_mt"

#: Khoá trong bảng `settings` cho phép người dùng đè lên khai báo của registry.
ASR_DEFAULT_SETTING = "default_asr_engine"
MT_DEFAULT_SETTING = "default_mt_engine"

#: Giá trị dùng khi registry KHÔNG khai báo `default_asr` (giữ nguyên hành vi
#: của GĐ1a). Nó chỉ là ĐIỂM RƠI, không phải nguồn: hàm dưới vẫn phải chứng minh
#: id này có thật trong registry, nếu không thì hỏng ngay và nói rõ.
FALLBACK_ASR_ENGINE_ID = "fw-large-v3-turbo"


def default_asr_engine(specs: Iterable[EngineSpec], *, declared: str | None = None,
                       configured: str | None = None) -> str:
    """Engine ASR mặc định, đã CHỨNG MINH là có trong registry.

    Thứ tự ưu tiên: setting của người dùng (`configured`) -> khai báo của registry
    (`declared`) -> hằng số dự phòng của GĐ1a.

    Ném `KeyError` nêu ĐÚNG id, NGUỒN của nó, các engine đang có, và chỗ cần sửa.
    Đây là điểm hỏng SỚM: `ingest.py` từng hard-code `fw-large-v3-turbo` và tạo
    job asr với một id không có trong registry, nên upload xong mới nổ ở tận
    worker bằng `KeyError: engine 'fw-large-v3-turbo' không có trong registry`.
    """
    specs = list(specs)
    if configured:
        source = f"setting {ASR_DEFAULT_SETTING!r}"
        engine_id = configured
    elif declared:
        source = f"khoá {DEFAULT_ASR_KEY!r} trong registry"
        engine_id = declared
    else:
        source = "giá trị dự phòng của GĐ1a"
        engine_id = FALLBACK_ASR_ENGINE_ID

    available = [s.id for s in specs if s.kind == "asr"]
    if engine_id not in {s.id for s in specs}:
        raise KeyError(
            f"engine ASR mặc định {engine_id!r} ({source}) không có trong registry; "
            f"các engine asr đang có: {available}. "
            f"Sửa {DEFAULT_ASR_KEY!r} trong registry.json hoặc setting "
            f"{ASR_DEFAULT_SETTING!r} cho khớp."
        )
    return engine_id


def estimate_vram_mb(specs: Iterable[EngineSpec], engine_ids: Iterable[str]) -> int:
    specs = list(specs)
    return sum(by_id(specs, eid).vram_mb for eid in engine_ids)


#: Ollama mặc định nghe ở đây. `OLLAMA_HOST` (biến chính thức của Ollama) được
#: `routes_registry.probe_ollama` tôn trọng cho endpoint `/api/status`; ở đây
#: dùng hằng số tường minh để một biến môi trường dạng `host:port` (không scheme)
#: không âm thầm làm phép dò này trả `False` — đúng lỗi API-02 của GĐ1a.
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def ollama_available(base_url: str = DEFAULT_OLLAMA_BASE_URL,
                     timeout: float = 1.5) -> bool:
    """Ollama có sống không. Dò MỘT lần lúc dựng, KHÔNG dò mỗi request.

    Vì sao phải dò thật thay vì hardcode: một engine Ollama được khai "có sẵn"
    trong khi tiến trình Ollama không chạy thì job dịch sẽ được xếp vào hàng đợi
    rồi chết trong worker, thay vì bị từ chối SỚM ngay lúc dựng (đúng lỗi I-3 mà
    GĐ1a đã trả giá với engine ASR).

    Chỉ hỏi `/api/tags` có trả 200 hay không — tức "Ollama có sống", KHÔNG phải
    "model này đã pull". Phép dò theo từng model là việc khác, và nó sẽ đổi hành
    vi `available` của cả registry; ghi ở đây để không ai đọc nhầm phạm vi.

    Mọi lỗi (chưa cài `httpx`, cổng đóng, timeout, DNS) đều là `False`: câu hỏi
    là "có dùng được ngay bây giờ không", và câu trả lời an toàn cho một job sắp
    xếp hàng là "không".
    """
    import httpx

    try:
        with httpx.Client(timeout=timeout) as client:
            return client.get(f"{base_url.rstrip('/')}/api/tags").status_code == 200
    except Exception:
        return False


def default_mt_engine(specs: Iterable[EngineSpec], *, declared: str | None = None,
                      configured: str | None = None) -> str | None:
    """Engine DỊCH mặc định — chọn từ DỮ LIỆU, không từ thứ tự dòng (R58).

    Thứ tự ưu tiên: setting của người dùng (`configured`) -> khai báo
    `default_mt` của registry (`declared`) -> phần tử ĐẦU của danh sách `mt`.

    Vì sao cần dấu hiệu tường minh: trước R58 chỉ có nhánh cuối, nên đảo thứ tự
    mảng `mt` trong `registry.json` — hoặc thêm một model Ollama 5200 MB lên đầu
    — là đổi engine mặc định của cả pipeline một cách im lặng, không test nào ghim.

    Hai nhánh đầu là DỮ LIỆU do người viết cấu hình gõ tay, nên chúng phải được
    CHỨNG MINH là có thật — y như `default_asr_engine`, và ném `KeyError` nêu
    ĐÚNG id, NGUỒN của nó, các engine đang có, và chỗ cần sửa. Trước bản vá,
    `if declared: return declared` trả thẳng id mà không đối chiếu `specs`: một
    `default_mt` gõ sai im lặng trở thành engine của MỌI job `translate`, và
    GĐ1a chưa có handler `translate` nên nó chỉ hiện ra thành job FAILED ở worker.

    Nhánh cuối theo THỨ TỰ MẢNG là ĐIỂM RƠI có hợp đồng của `default_mt_engine`
    (registry không khai báo `default_mt` vẫn phải chạy, giữ nguyên hành vi cũ).
    Cấu hình đã ship luôn truyền `declared`, nên không đường sản xuất nào tới
    được nó — nhưng nó KHÔNG phải code chết: xoá đi là phá API công khai này.
    Ở nhánh đó id lấy từ chính `specs` nên không cần kiểm lại.
    """
    specs = list(specs)
    if configured:
        source = f"setting {MT_DEFAULT_SETTING!r}"
        engine_id = configured
    elif declared:
        source = f"khoá {DEFAULT_MT_KEY!r} trong registry"
        engine_id = declared
    else:
        mt_specs = [s for s in specs if s.kind == "mt"]
        return mt_specs[0].id if mt_specs else None

    available = [s.id for s in specs if s.kind == "mt"]
    if engine_id not in {s.id for s in specs}:
        raise KeyError(
            f"engine dịch mặc định {engine_id!r} ({source}) không có trong registry; "
            f"các engine mt đang có: {available}. "
            f"Sửa {DEFAULT_MT_KEY!r} trong registry.json hoặc setting "
            f"{MT_DEFAULT_SETTING!r} cho khớp."
        )
    return engine_id
