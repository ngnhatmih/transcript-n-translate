"""`resolve_openai_base_url` — env THẮNG registry, và cả phép dò lẫn adapter đọc CÙNG một địa chỉ.

Sự cố đo được: hàng `deepseek-web` khai `base_url: http://127.0.0.1:8790/v1`, chạy trong container
(`docker compose up`) thì `/api/registry` trả `available: false` — vì trong container `127.0.0.1`
là CHÍNH container, còn gateway nằm ở máy chủ. Đây đúng lớp M-10 của `OLLAMA_HOST`, nên biến
`PHUDE_OPENAI_BASE_URL` ra đời với cùng khuôn — và cùng MỘT hàm cho cả hai chỗ đọc.
"""
from __future__ import annotations

import pytest

from app import config, main
from app.adapters.registry_file import load_registry


def _spec_http():
    specs = [s for s in load_registry() if s.runtime == "http"]
    assert specs, "registry phải có ít nhất một hàng `runtime: http`"
    return specs[0]


def test_thieu_env_thi_giu_nguyen_base_url_trong_registry(monkeypatch):
    monkeypatch.delenv("PHUDE_OPENAI_BASE_URL", raising=False)
    spec = _spec_http()
    assert main._http_engine_opts(spec)["base_url"] == spec.opts["base_url"]  # noqa: SLF001


def test_env_thang_registry_va_duoc_chuan_hoa(monkeypatch):
    monkeypatch.setenv("PHUDE_OPENAI_BASE_URL", "http://host.docker.internal:8790/v1/")
    spec = _spec_http()
    assert main._http_engine_opts(spec)["base_url"] == "http://host.docker.internal:8790/v1"  # noqa: SLF001
    # Cùng một hàm cho phép DÒ: nếu phép dò và lúc dựng engine đọc hai địa chỉ khác nhau thì
    # giao diện hứa một engine rồi job gửi văn bản của người dùng tới chỗ khác (lớp M-10).
    da_hoi: list[str] = []

    def gia_models(base, *, api_key=None, timeout=1.5, client=None):
        da_hoi.append(base)
        return {spec.model_ref}

    monkeypatch.setattr(main, "openai_models_available", gia_models)
    assert main._http_engine_ready(spec, {}) is True  # noqa: SLF001
    assert da_hoi == ["http://host.docker.internal:8790/v1"], da_hoi


def test_env_rong_thi_khong_phai_mot_dia_chi(monkeypatch):
    monkeypatch.setenv("PHUDE_OPENAI_BASE_URL", "   ")
    assert config.resolve_openai_base_url("http://127.0.0.1:8790/v1") == "http://127.0.0.1:8790/v1"


def test_none_giu_nguyen_none(monkeypatch):
    monkeypatch.delenv("PHUDE_OPENAI_BASE_URL", raising=False)
    assert config.resolve_openai_base_url(None) is None
