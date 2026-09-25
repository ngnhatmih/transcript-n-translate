"""Route chỉ đọc: registry engine và trạng thái hàng đợi."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.api.deps import get_repos, get_specs, get_worker

router = APIRouter(prefix="/api", tags=["registry"])

_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
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
def get_status(repos=Depends(get_repos), worker=Depends(get_worker)):
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
        "ollama": probe_ollama(),
    }


def probe_ollama(host: str = _OLLAMA_HOST,
                 timeout: float = _OLLAMA_PROBE_SECONDS) -> str:
    """'up' | 'down' | 'unknown'.

    GĐ1a chưa dùng Ollama để dịch (việc đó là Giai đoạn 2), nên `unknown` phải
    giữ nguyên là một giá trị THẬT: biến nó thành `down` là bịa ra một sự thật
    chưa đo. Hàm này viết bằng stdlib để `app/api` không kéo thêm phụ thuộc.
    """
    host = os.environ.get("OLLAMA_HOST", host)
    url = host.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        # Máy chủ không lắng nghe / sai cổng: kết luận được là đang tắt.
        return "down"
    except (TimeoutError, OSError, ValueError):
        return "unknown"
    return "up"
