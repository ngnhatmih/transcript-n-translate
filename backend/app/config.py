"""Cấu hình đường dẫn và hằng số vận hành.

Chỉ đọc biến môi trường, không import gì từ app. Được phép import ở mọi tầng.
"""
from __future__ import annotations

import os
import pathlib

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


def _env_path(name: str, default: pathlib.Path) -> pathlib.Path:
    raw = os.environ.get(name)
    return pathlib.Path(raw).expanduser() if raw else default


DATA_DIR = _env_path("PHUDE_DATA", PROJECT_DIR / "data")
MEDIA_DIR = DATA_DIR / "media"
LOG_DIR = DATA_DIR / "logs"
OUTPUT_DIR = DATA_DIR / "output"
DB_PATH = _env_path("PHUDE_DB", DATA_DIR / "app.db")

REGISTRY_PATH = _env_path("PHUDE_REGISTRY", BACKEND_DIR / "registry.json")

HF_HOME = os.environ.get("HF_HOME", r"D:\models\hf")
OLLAMA_MODELS = os.environ.get("OLLAMA_MODELS", r"D:\models\ollama")

API_HOST = os.environ.get("PHUDE_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("PHUDE_PORT", "8620"))

# Ngưỡng nghiệp vụ — sao chép từ spec, KHÔNG tự đoán lại
SUSPECT_NO_SPEECH_PROB = 0.6
SUSPECT_AVG_LOGPROB = -1.0

#: Nơi Ollama nghe khi `OLLAMA_HOST` không được đặt. Hằng số này là NGUỒN DUY NHẤT
#: của địa chỉ đó trong toàn bộ mã sản xuất (M-10 của review cuối): trước đây
#: endpoint bị mã hoá ở bốn chỗ và chúng BẤT ĐỒNG — `routes_registry` đọc env (lúc
#: import ở một chỗ, lúc gọi ở chỗ khác), `registry.ollama_available` ghim mặc định
#: lúc ĐỊNH NGHĨA, còn adapter `OllamaMtEngine` thì không đọc `OLLAMA_HOST` chút
#: nào. Hệ quả thật: đặt `OLLAMA_HOST` trỏ nơi khác thì `/api/status` báo theo
#: env, còn phép dò availability và MỌI lời gọi dịch thật đi `127.0.0.1` ⇒ mọi
#: engine Ollama đọc `available: false` ⇒ tạo job bị 409.
OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434"


def resolve_ollama_base_url(host: str | None = None) -> str:
    """Địa chỉ cơ sở của Ollama — ĐỌC ENV LÚC GỌI, không phải lúc import.

    Ba tính chất, mỗi tính chất là một lỗi đã trả giá:

    * **Đọc `OLLAMA_HOST` lúc GỌI.** Một hằng số đọc env lúc import (bản cũ của
      `routes_registry._OLLAMA_HOST`) không tác động được bằng
      `monkeypatch.setenv`, tức không test nào ghim được hành vi thật, và một
      tiến trình đổi env sau khi import vẫn đi địa chỉ cũ.
    * **Chuẩn hoá y như `probe_ollama` đang làm**: thiếu `://` thì thêm
      `http://` (dạng chính thức của `OLLAMA_HOST` là `host:port` KHÔNG scheme —
      thiếu scheme thì `urllib`/`httpx` hiểu sai loại URL), và BỎ `/` cuối để
      không sinh `//api/tags`.
    * **`OLLAMA_HOST` THẮNG tham số `host`.** Giữ nguyên thứ tự ưu tiên mà
      `probe_ollama` đã có: `OLLAMA_HOST` là cấu hình của CÁI MÁY ("Ollama chạy ở
      đâu trên box này"), còn tham số là giá trị mặc định của người gọi. Đổi thứ
      tự này là đổi hợp đồng đang chạy, và nó sẽ đổi IM LẶNG — không bài nào
      trong `tests/` khẳng định thứ tự đó: bài duy nhất `setenv("OLLAMA_HOST")`
      (`test_ollama_probe.py`) gọi `probe_ollama()` KHÔNG tham số, nên nó không
      nói gì về env-vs-tham-số. Chỉ có ghi chú này giữ hợp đồng.
    """
    raw = os.environ.get("OLLAMA_HOST")
    if raw is None:
        raw = host if host is not None else OLLAMA_DEFAULT_BASE_URL
    if "://" not in raw:
        raw = "http://" + raw
    return raw.rstrip("/")


def resolve_openai_base_url(declared: str | None = None) -> str | None:
    """Địa chỉ endpoint OpenAI-compatible — ĐỌC ENV LÚC GỌI, env THẮNG `registry.json`.

    Vì sao cần một biến môi trường khi `base_url` đã là DỮ LIỆU trong hàng registry: **cùng
    một hàng phải chạy được ở hai chỗ với hai địa chỉ KHÁC nhau**. Chạy thẳng trên máy thì
    gateway ở `http://127.0.0.1:8790/v1`; chạy trong container thì `127.0.0.1` là **chính
    container**, còn gateway nằm ở máy chủ (`http://host.docker.internal:8790/v1`). Đo được:
    hàng `deepseek-web` trong container trả `available: false` với `base_url` của registry.

    Đây đúng lớp lỗi **M-10** của Ollama (`OLLAMA_HOST` + `resolve_ollama_base_url`), nên
    dùng cùng khuôn: một hàm, đọc env lúc GỌI (để `monkeypatch.setenv` ghim được), và được
    dùng bởi **cả** phép dò `available` lẫn lúc dựng adapter — hai chỗ đọc hai địa chỉ khác
    nhau là giao diện hứa một engine rồi job gửi văn bản tới chỗ khác.

    `None`/chuỗi rỗng ở env ⇒ giữ nguyên giá trị khai trong registry (không có mặc định:
    một endpoint mặc định là một lời hứa về dịch vụ bên ngoài mà ta không kiểm soát).
    """
    env = os.environ.get("PHUDE_OPENAI_BASE_URL")
    if isinstance(env, str) and env.strip():
        return env.strip().rstrip("/")
    return declared


def ensure_dirs() -> None:
    for d in (DATA_DIR, MEDIA_DIR, LOG_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
