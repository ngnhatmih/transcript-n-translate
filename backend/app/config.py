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


def ensure_dirs() -> None:
    for d in (DATA_DIR, MEDIA_DIR, LOG_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
