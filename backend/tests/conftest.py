from __future__ import annotations

import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def mo_hinh_mac_dinh() -> set[str]:
    """`model_ref` của engine DỊCH MẶC ĐỊNH mà phép dò Ollama phải thấy "đã pull".

    🔴 VÌ SAO CẦN (ERRATA #71). Nhiều fixture ghim `main.ollama_available` = `set()`
    ("chưa pull model nào") rồi gọi `build_components()` THẬT. Hồi `default_mt` là
    `deepseek-web` (`runtime: http`) thì chúng vẫn xanh — vì `available` của engine đó do
    phép dò MẠNG `127.0.0.1:8790` quyết, và cái gateway đó đang chạy. Tức các bài ấy phụ
    thuộc NGẦM vào một dịch vụ ngoài, và khi gateway tắt thì cả loạt bài đỏ dù mã đúng.

    Nay `default_mt` là engine Ollama, nên phép dò phải thấy đúng `model_ref` của nó —
    nếu không, `build_components()` ném ngay chỗ kiểm "engine mặc định phải SẴN SÀNG"
    (đúng thiết kế: nó là chỗ fail sớm nhất). Hàm này đọc registry để test không phải
    viết cứng tên model: đổi `default_mt` là các fixture tự theo.
    """
    import json

    from app import config

    #: `config.REGISTRY_PATH` chứ KHÔNG phải một đường tự ghép: bản đầu tôi ghép
    #: `BACKEND / "app" / "registry.json"` — sai một thư mục, và 8 bài đỏ với
    #: `FileNotFoundError` trông như lỗi sản phẩm.
    reg = json.loads(pathlib.Path(config.REGISTRY_PATH).read_text(encoding="utf-8"))
    mac_dinh = reg.get("default_mt")
    for entry in reg.get("mt", []):
        if entry.get("id") == mac_dinh and entry.get("runtime") == "ollama":
            return {entry["model_ref"]}
    return set()

