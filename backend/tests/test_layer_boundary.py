"""Bảo vệ quy tắc: domain/ là logic thuần, không biết gì về hạ tầng.

Test này là lý do tồn tại của cả phân tầng. Nếu nó đỏ, ĐỪNG sửa test —
hãy sửa chỗ import sai.
"""
from __future__ import annotations

import ast
import pathlib
import shutil

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
DOMAIN = BACKEND / "app" / "domain"

FORBIDDEN_ABSOLUTE = {
    "fastapi", "starlette", "uvicorn",
    "torch", "faster_whisper", "funasr", "modelscope", "transformers",
    "ctranslate2", "onnxruntime",
    "httpx", "requests",
    "sqlite3", "yt_dlp",
}
FORBIDDEN_PREFIXES = ("app.adapters", "app.ports", "app.api", "app.pipeline", "app.worker")


def _is_forbidden_absolute(name: str) -> bool:
    top = name.split(".")[0]
    if top in FORBIDDEN_ABSOLUTE:
        return True
    if name == "app":
        return True
    return any(name == p or name.startswith(p + ".") for p in FORBIDDEN_PREFIXES)


def _imports_of(path: pathlib.Path) -> list[tuple[str, int]]:
    """Trả về (tên module, mức tương đối). Mức 0 = import tuyệt đối."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            out.append((node.module or "", node.level or 0))
    return out


def _domain_files() -> list[pathlib.Path]:
    if not DOMAIN.exists():
        return []
    return sorted(DOMAIN.rglob("*.py"))


def test_domain_directory_exists():
    assert DOMAIN.is_dir(), f"thiếu thư mục {DOMAIN}"


def test_domain_has_no_forbidden_absolute_imports():
    offenders: list[str] = []
    for py in _domain_files():
        for name, level in _imports_of(py):
            if level != 0:
                continue
            if _is_forbidden_absolute(name):
                offenders.append(f"{py.name}: import {name}")
    assert not offenders, (
        "domain/ phải là logic thuần, không được import hạ tầng:\n  "
        + "\n  ".join(offenders)
    )


def test_domain_has_no_cross_layer_relative_imports():
    """`from .models import X` OK. `from ..adapters import Y` KHÔNG."""
    offenders: list[str] = []
    for py in _domain_files():
        for name, level in _imports_of(py):
            if level >= 2:
                offenders.append(f"{py.name}: {'..' * (level - 1)}{name}")
    assert not offenders, (
        "domain/ không được import ngược lên tầng trên:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_itself_can_fail(tmp_path):
    """Kiểm tra cái lưới: nếu domain/ có file import torch thì test phải bắt được."""
    rogue = DOMAIN / "_rogue_probe.py"
    rogue.write_text("import torch\n", encoding="utf-8")
    try:
        with pytest.raises(AssertionError):
            test_domain_has_no_forbidden_absolute_imports()
    finally:
        rogue.unlink()


def test_guard_catches_cross_layer_absolute_import():
    """Lưới phải bắt được import tuyệt đối xuyên tầng, không chỉ tên thư viện.

    `from app.adapters.persist import x` có top-level là "app" nên cách so khớp
    tuyệt đối cũ để lọt; test này khoá lại hành vi đúng.
    """
    rogue = DOMAIN / "_rogue_probe_adapters.py"
    rogue.write_text(
        "from app.adapters.persist import sqlite_repos\n", encoding="utf-8"
    )
    try:
        with pytest.raises(AssertionError):
            test_domain_has_no_forbidden_absolute_imports()
    finally:
        rogue.unlink()


def test_guard_catches_forbidden_import_in_nested_package_init():
    """`__init__.py` cũng nằm trong `domain/**` nên phải bị quét.

    Dùng gói con tạm để không bao giờ đụng vào `app/domain/__init__.py` thật.
    """
    pkg = DOMAIN / "_guard_probe"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from app.adapters.persist import sqlite_repos\n", encoding="utf-8"
    )
    try:
        with pytest.raises(AssertionError):
            test_domain_has_no_forbidden_absolute_imports()
    finally:
        shutil.rmtree(pkg)


def test_guard_flags_bare_import_app():
    """`import app` là import cả tầng ứng dụng — phải bị chặn."""
    rogue = DOMAIN / "_guard_probe_bare_app.py"
    rogue.write_text("import app\n", encoding="utf-8")
    try:
        with pytest.raises(AssertionError):
            test_domain_has_no_forbidden_absolute_imports()
    finally:
        rogue.unlink()


def test_guard_allows_safe_app_modules():
    """Chống bắt nhầm: `app.config`, `app.domain.*`, `app_helpers` đều hợp lệ."""
    safe = DOMAIN / "_guard_probe_safe.py"
    safe.write_text(
        "from app.config import DB_PATH\n"
        "from app.domain.models import Segment\n"
        "import app_helpers\n",
        encoding="utf-8",
    )
    try:
        test_domain_has_no_forbidden_absolute_imports()
    finally:
        safe.unlink()
