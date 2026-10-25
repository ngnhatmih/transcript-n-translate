"""Kiểu dữ liệu của registry và các phép tra cứu. Thuần, không đọc tệp.

Việc đọc tệp nằm ở adapters/registry_file.py.

Một ngoại lệ CÓ GHI NHẬN cho tính "thuần" ở trên: `ollama_available()` dò sống
tiến trình Ollama. Nó nằm đây theo đúng Step 4 của brief Task 12, và nó KHÔNG
kéo `httpx` vào lúc import (import nằm trong hàm) — module này vẫn import được ở
mọi tầng, kể cả nơi `httpx` chưa cài.

Hai phép dò Ollama (`ollama_available` ở đây và `routes_registry.probe_ollama`)
vẫn là hai hàm vì chúng trả lời hai câu hỏi KHÁC nhau: "model nào đã pull" và
"tiến trình có sống". Thứ đã được gộp ở `M-10` là ĐỊA CHỈ: cả hai (và `base_url`
của engine mà `main.py` dựng) nay đi qua `app.config.resolve_ollama_base_url`,
nguồn duy nhất đọc `OLLAMA_HOST`.

Fix round 1 (I-1): `ollama_available()` nay trả TÊN các model đã pull, không
phải một `bool`. "Ollama sống" là điều kiện CẦN nhưng KHÔNG ĐỦ để một engine
`runtime == "ollama"` phục vụ được job — còn phải có model trong `/api/tags`.
Câu hỏi "tiến trình Ollama có sống không" là tín hiệu RIÊNG của `/api/status`
(`routes_registry.probe_ollama`), không phải của trường `capabilities["available"]`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.config import resolve_ollama_base_url
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
    #: 'inprocess' (opus-mt, Marian chạy trong tiến trình) | 'ollama' (LLM qua
    #: `/api/chat`) | 'http' (một endpoint OpenAI-compatible, cấu hình ở `opts`).
    #: Giá trị lạ KHÔNG bị đoán: `app/main.py::_build_mt_engines` ném lỗi kèm
    #: danh sách runtime đang hỗ trợ.
    runtime: str
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


#: Ollama mặc định nghe ở đâu: hằng số nằm ở `app/config.py` (`M-10`), KHÔNG
#: chép lại ở đây. `OLLAMA_HOST` được `app.config.resolve_ollama_base_url` đọc
#: LÚC GỌI, và cả ba đường dùng nó — phép dò dưới đây, `probe_ollama` của
#: `/api/status`, và `base_url` của engine mà `app/main.py` dựng. Trước bản vá
#: endpoint bị mã hoá bốn chỗ và bất đồng: đặt `OLLAMA_HOST` trỏ nơi khác thì
#: `/api/status` báo theo env trong khi phép dò (và mọi lời gọi dịch thật) đi
#: `127.0.0.1` ⇒ mọi engine Ollama đọc `available: false` ⇒ tạo job bị 409.


def ollama_available(base_url: str | None = None,
                     timeout: float = 1.5) -> set[str]:
    """TÊN các model Ollama đã pull. Dò MỘT lần lúc dựng, KHÔNG dò mỗi request.

    Trả về `set()` khi KHÔNG dùng được — tiến trình chết, cổng đóng, timeout,
    DNS hỏng, chưa cài `httpx`, hoặc phản hồi dị dạng. Tập RỖNG là câu trả lời
    an toàn: câu hỏi của người gọi luôn là "engine này phục vụ được job NGAY BÂY
    GIỜ không", và một tiến trình không trả lời được thì câu trả lời là "không".
    Vì vậy "Ollama chết" và "Ollama sống nhưng chưa pull model nào" cho ra CÙNG
    một kết quả ở đây — và đó là điều đúng cho `available`, vì cả hai đều nghĩa
    là không engine `ollama` nào chạy được. Ai cần phân biệt "sống/chết" thì hỏi
    `/api/status` (`app/api/routes_registry.probe_ollama`).

    Vì sao phải dò thật thay vì hardcode: một engine Ollama được khai "có sẵn"
    trong khi tiến trình Ollama không chạy thì job dịch sẽ được xếp vào hàng đợi
    rồi chết trong worker, thay vì bị từ chối SỚM ngay lúc dựng (đúng lỗi I-3 mà
    GĐ1a đã trả giá với engine ASR).

    Fix round 1 (I-1): bản cũ chỉ hỏi `/api/tags` có trả 200 hay không, tức
    "Ollama có sống" — KHÔNG phải "model này đã pull". Hệ quả đo được trên máy
    chỉ có `qwen2.5:3b-instruct-q4_K_M`: `GET /api/registry` vẫn khai
    `available: true` cho `qwen2.5-7b` và `hy-mt-1.5-7b`, người dùng chọn một
    engine mà API nói đã sẵn sàng, rồi job chết ở tận worker (`KeyError`) —
    đúng lớp lỗi I-3 của GĐ1a. Nay tên model được đọc từ chính phản hồi ĐÃ GỌI
    đó, và người gọi chỉ còn một phép kiểm thành viên cho mỗi engine.

    Tên đọc từ `models[].name`/`model` — đúng chuỗi người dùng gõ `ollama pull`,
    ví dụ `qwen2.5:3b-instruct-q4_K_M`, nên nó so KHỚP TUYỆT ĐỐI với
    `spec.model_ref`. Giữ luôn cả `name` lẫn `model`: Ollama trả `model` ở các
    bản cũ và `name` ở các bản mới, và bỏ sót một khoá thì một model ĐÃ pull bị
    coi là thiếu — tức lại rơi về đúng lỗi "engine sẵn sàng mà job chết".

    M-10: `base_url` mặc định là `None` chứ KHÔNG phải một hằng số. Mặc định của
    tham số được đánh giá LÚC ĐỊNH NGHĨA HÀM, nên một hằng số ở đây sẽ ghim địa
    chỉ ngay lúc import và `monkeypatch.setenv("OLLAMA_HOST", ...)` không tác
    động được — đúng lỗi mà bản vá này đóng lại. `None` ⇒ phân giải LÚC GỌI qua
    `app.config.resolve_ollama_base_url` (nguồn duy nhất của địa chỉ đó).
    """
    import httpx

    if base_url is None:
        base_url = resolve_ollama_base_url()

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/tags")
            if resp.status_code != 200:
                return set()
            data = resp.json()
    except Exception:
        return set()

    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return set()
    names: set[str] = set()
    for entry in models:
        if not isinstance(entry, dict):
            continue
        for key in ("name", "model"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                names.add(value)
    return names


def openai_models_available(base_url: str, *, api_key: str | None = None,
                            timeout: float = 1.5,
                            client=None) -> set[str]:
    """TÊN model một endpoint OpenAI-compatible khai ở `GET /models`.

    Cùng hợp đồng với `ollama_available`, vì người gọi là cùng một chỗ
    (`app/main.py::_mark_availability`) và cùng một câu hỏi: "engine này phục vụ
    được job NGAY BÂY GIỜ không". Tập RỖNG khi không dùng được — endpoint chết,
    cổng đóng, timeout, 401 vì thiếu khoá, phản hồi dị dạng. Tập rỗng là câu trả
    lời an toàn: một endpoint không trả lời được thì không phục vụ được.

    `client` để test tiêm được mà không chạm mạng (đúng khuôn `OllamaMtEngine`);
    `api_key` chỉ đi trong header, KHÔNG bao giờ vào URL hay thông báo lỗi.
    """
    import httpx

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        if client is not None:
            resp = client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        else:
            with httpx.Client(timeout=timeout) as owned:
                resp = owned.get(f"{base_url.rstrip('/')}/models", headers=headers)
        if resp.status_code != 200:
            return set()
        data = resp.json()
    except Exception:
        return set()

    models = data.get("data") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return set()
    # `id` là khoá của OpenAI; nhận thêm `name`/`model` vì các bản tương thích
    # (vLLM, LM Studio, llama.cpp) không thống nhất một khoá.
    names: set[str] = set()
    for entry in models:
        if not isinstance(entry, dict):
            continue
        for key in ("id", "name", "model"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                names.add(value)
    return names


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
