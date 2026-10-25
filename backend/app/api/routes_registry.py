"""Route chỉ đọc: registry engine và trạng thái hàng đợi."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.api.deps import get_repos, get_specs, get_vram_reader, get_worker
from app.config import resolve_ollama_base_url
from app.domain.vram import VRAM_UNIT

router = APIRouter(prefix="/api", tags=["registry"])

_OLLAMA_PROBE_SECONDS = 0.3


@router.get("/registry")
def get_registry(specs=Depends(get_specs)):
    """Danh sách engine theo `kind`. Frontend đọc thẳng từ đây, không hard-code."""
    out: dict[str, list[dict]] = {"asr": [], "mt": []}
    for spec in specs:
        payload = asdict(spec)
        # `langs` là tuple trong EngineSpec nhưng mảng trong JSON. `asdict` giữ
        # nguyên tuple, mà jsonable_encoder của FastAPI cũng đổi được, nên dòng
        # này chỉ để hình dạng payload không phụ thuộc phiên bản FastAPI.
        payload["langs"] = list(spec.langs)
        out.setdefault(spec.kind, []).append(payload)
    return out


@router.get("/status")
def get_status(repos=Depends(get_repos), worker=Depends(get_worker),
               vram_reader=Depends(get_vram_reader)):
    """Trạng thái để giao diện hiện băng-rôn.

    `worker` là None khi app được dựng mà chưa có worker (test, hoặc chế độ chỉ
    đọc), nên mọi trường của nó đọc qua `getattr` với mặc định.
    """
    queued = repos.list_jobs(states=("queued",))
    running = repos.list_jobs(states=("running",))
    return {
        "queue_depth": len(queued),
        "running": [j.id for j in running],
        "current_phase": getattr(worker, "current_phase", None),
        "phase_switches": getattr(worker, "phase_switches", 0),
        # API-04 (R77): spec §11 ghim `GET /api/status` trả cả VRAM. Số là VRAM
        # ĐANG DÙNG, do composition root đặt vào `app.state.vram_reader`
        # (`adapters/gpu.py` đọc `nvidia-smi`) — KHÔNG phải `vram_mb` khai báo
        # trong registry, vốn là số cho bộ điều phối.
        # Không có reader, hoặc đọc hỏng ⇒ `None` TƯỜNG MINH (khoá vẫn có, JSON
        # là `null`) — cùng khuôn với `ollama: "unknown"`: frontend đọc
        # `body["vram"]` chứ không phòng thủ bằng `if "vram" in body`, và "chưa
        # biết" là một giá trị nói thật, không được thay bằng 0.
        "vram": vram_reader() if vram_reader is not None else None,
        # Đơn vị đi KÈM số, vì giao diện KHÔNG được tự thêm đơn vị mà backend
        # không nói (`screens/OllamaDown.tsx`): "3200" trần trụi là một con số vô
        # nghĩa. Khi `vram` là `null` thì trường này vẫn có — nó nói đơn vị SẼ
        # dùng nếu đo được, không nói rằng đã đo được.
        "vram_unit": VRAM_UNIT,
        # API-03 (M6): `probe_ollama` chạy MỖI request (tối đa ~300 ms khi host
        # không tới được). Quyết định của GĐ1a: GIỮ NGUYÊN — route này là `def`
        # nên FastAPI chạy nó trong threadpool, không chặn event loop, và
        # `/api/status` chỉ được poll thưa; cache TTL (hoặc tách endpoint riêng)
        # là việc của GĐ2. Đây là quyết định hoãn CÓ GHI NHẬN, không phải thiếu test.
        "ollama": probe_ollama(),
    }


def probe_ollama(host: str | None = None,
                 timeout: float = _OLLAMA_PROBE_SECONDS) -> str:
    """'up' | 'down' | 'unknown'.

    GĐ1a chưa dùng Ollama để dịch (việc đó là Giai đoạn 2), nên `unknown` phải
    giữ nguyên là một giá trị THẬT: biến nó thành `down` là bịa ra một sự thật
    chưa đo. Hàm này viết bằng stdlib để `app/api` không kéo thêm phụ thuộc.

    API-02 (M5) — hai chỗ phân loại sai đã sửa ở đây:

    * `OLLAMA_HOST` chính thức của Ollama là dạng `host:port` KHÔNG có scheme.
      Thiếu `http://`, `urllib` không có handler nào cho kiểu URL đó và ném
      `URLError('unknown url type: ...')` ⇒ một Ollama ĐANG CHẠY vẫn bị báo
      `down`. Chuỗi đã có `://` thì giữ nguyên.
    * `urlopen` bọc MỌI lỗi tầng vận chuyển vào `URLError.reason`, kể cả
      `socket.timeout` của pha KẾT NỐI. Timeout là "chưa đo được" ⇒ `unknown`;
      `ConnectionRefusedError` mới là "có máy nhưng không ai nghe" ⇒ `down`.
      Thứ tự `except` giữ `URLError` trước vì nó là lớp con của `OSError`.
    * `socket.gaierror` (DNS không phân giải được TÊN) cũng là "chưa đo được":
      chưa hỏi được ai cả thì không được kết luận `down`. Cùng loại: `reason` là
      một CHUỖI (`'no host given'`, `'unknown url type'`) — URL/host không dựng
      nổi, tức lỗi cấu hình chứ không phải câu trả lời của ai.

    M-10: địa chỉ KHÔNG còn được đọc ở đây. `resolve_ollama_base_url` là nguồn
    duy nhất (đọc `OLLAMA_HOST` lúc GỌI, chuẩn hoá `://` và `/` cuối), dùng
    chung với `registry.ollama_available` và với `base_url` của engine mà
    `app/main.py` dựng — ba đường, một địa chỉ.
    """
    url = resolve_ollama_base_url(host) + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.gaierror)):
            # Chưa đo được: host có thể sống mà chỉ chậm/mất gói, hoặc tên chưa
            # phân giải được nên CHƯA hỏi được ai.
            return "unknown"
        if isinstance(reason, ConnectionRefusedError):
            # Cổng đóng: kết luận được là đang tắt.
            return "down"
        if isinstance(reason, str):
            # URL/host không dựng nổi (`'no host given'`, `'unknown url type'`):
            # lỗi CẤU HÌNH, chưa có câu hỏi nào được gửi đi ⇒ chưa đo được.
            return "unknown"
        # Còn lại (đã phân giải được tên nhưng không tới được host ở tầng
        # socket): ĐÃ hỏi, không ai trả lời ⇒ `down`.
        return "down"
    except (TimeoutError, OSError, ValueError):
        return "unknown"
    return "up"
