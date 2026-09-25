"""Bảo vệ quy tắc ranh giới tầng: `domain/` là logic thuần, `ports/` chỉ có Protocol.

Test này là lý do tồn tại của cả phân tầng. Nếu nó đỏ, ĐỪNG sửa test —
hãy sửa chỗ import sai.

Hai lỗ hổng đã đóng ở đây (I-4):

* `app/ports/` **không được** guard nào ràng buộc, nên luật "chỉ Protocol, không
  hiện thực" chỉ được thực thi bằng cách đọc code. Nay có guard riêng: import chỉ
  được là module chuẩn hoặc `app.domain`, và class cấp module phải là `Protocol`.
* guard của `domain/` là **danh sách đen**: thiếu `app.registry`/`app.main` nên
  một vòng `domain → app.registry` lọt sạch. Nay không gian tên `app.` là **danh
  sách trắng**: thêm tầng mới thì mặc định bị chặn.

Mọi guard ở đây đều có bài chứng minh nó ĐỎ được (tạo tệp thăm dò rồi xoá), vì
một lưới không bắt được gì thì không phải là lưới.
"""
from __future__ import annotations

import ast
import pathlib
import shutil
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
DOMAIN = BACKEND / "app" / "domain"
PORTS = BACKEND / "app" / "ports"

FORBIDDEN_ABSOLUTE = {
    "fastapi", "starlette", "uvicorn",
    "torch", "faster_whisper", "funasr", "modelscope", "transformers",
    "ctranslate2", "onnxruntime",
    "httpx", "requests",
    "sqlite3", "yt_dlp",
}
#: I-4: `app.registry` và `app.main` từng KHÔNG có trong danh sách này, nên
#: `from app.registry import by_id` trong `app/domain/` lọt qua.
FORBIDDEN_PREFIXES = ("app.adapters", "app.ports", "app.api", "app.pipeline",
                      "app.worker", "app.registry", "app.main")

#: Module chuẩn của ĐÚNG phiên bản Python đang chạy — danh sách trắng cho
#: `app/ports/`, thay vì danh sách đen (danh sách đen luôn thiếu một cái tên:
#: `import numpy`/`pydantic`/`yaml` từng lọt qua ở đây).
STDLIB = frozenset(sys.stdlib_module_names)

#: `app.*` được phép import XUỐNG. `app.config` là hằng số thuần, không import gì
#: từ app — quyền đó đã được ghim bởi `test_guard_allows_safe_app_modules`.
ALLOWED_APP_DOMAIN = ("app.config", "app.domain")
ALLOWED_APP_PORTS = ("app.domain",)


def _is_forbidden_absolute(name: str, *, allowed_app: tuple[str, ...],
                           stdlib_only: bool) -> bool:
    top = name.split(".")[0]
    if name == "app":
        return True
    if top == "app":
        # Danh sách TRẮNG cho không gian tên `app.`: một tầng mới mặc định bị
        # chặn, thay vì mặc định được phép (đúng lỗ hổng I-4).
        return not any(name == p or name.startswith(p + ".") for p in allowed_app)
    if top in FORBIDDEN_ABSOLUTE:
        return True
    if stdlib_only:
        return top not in STDLIB
    # `domain/`: giữ nguyên hành vi cũ với tên NGOÀI `app.` — bài
    # `test_guard_allows_safe_app_modules` ghim `import app_helpers` là hợp lệ.
    return False


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


def _py_files(directory: pathlib.Path) -> list[pathlib.Path]:
    if not directory.exists():
        return []
    return sorted(directory.rglob("*.py"))


def _domain_files() -> list[pathlib.Path]:
    return _py_files(DOMAIN)


def _import_offenders(directory: pathlib.Path, *, allowed_app: tuple[str, ...],
                      stdlib_only: bool) -> list[str]:
    offenders: list[str] = []
    for py in _py_files(directory):
        for name, level in _imports_of(py):
            if level != 0:
                continue
            if _is_forbidden_absolute(name, allowed_app=allowed_app,
                                      stdlib_only=stdlib_only):
                offenders.append(f"{py.name}: import {name}")
    return offenders


def _relative_offenders(directory: pathlib.Path) -> list[str]:
    """`from .models import X` OK. `from ..adapters import Y` KHÔNG."""
    offenders: list[str] = []
    for py in _py_files(directory):
        for name, level in _imports_of(py):
            if level >= 2:
                offenders.append(f"{py.name}: {'..' * (level - 1)}{name}")
    return offenders


def _base_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
        else:                                   # pragma: no cover - hình dạng lạ
            names.add(ast.unparse(base))
    return names


def _implementation_offenders(directory: pathlib.Path) -> list[str]:
    """`ports/` chỉ khai báo HỢP ĐỒNG: class phải là `Protocol`, không hàm lạ."""
    offenders: list[str] = []
    for py in _py_files(directory):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if "Protocol" not in _base_names(node):
                    offenders.append(
                        f"{py.name}: class {node.name} không phải Protocol")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                offenders.append(
                    f"{py.name}: hàm {node.name} là hiện thực, không phải hợp đồng")
    return offenders


# ---------------------------------------------------------------------------
# app/domain — logic thuần
# ---------------------------------------------------------------------------

def test_domain_directory_exists():
    assert DOMAIN.is_dir(), f"thiếu thư mục {DOMAIN}"


def test_domain_has_no_forbidden_absolute_imports():
    offenders = _import_offenders(DOMAIN, allowed_app=ALLOWED_APP_DOMAIN,
                                  stdlib_only=False)
    assert not offenders, (
        "domain/ phải là logic thuần, không được import hạ tầng:\n  "
        + "\n  ".join(offenders)
    )


def test_domain_has_no_cross_layer_relative_imports():
    offenders = _relative_offenders(DOMAIN)
    assert not offenders, (
        "domain/ không được import ngược lên tầng trên:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_itself_can_fail():
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


def test_guard_catches_the_app_registry_and_app_main_hole():
    """I-4 · đúng hai tên từng lọt qua danh sách đen: `app.registry` và `app.main`.

    Một vòng `domain -> app.registry` không chỉ sai về tầng: nó kéo cả registry
    (và có thể cả composition root) vào tầng được cho là thuần.
    """
    for index, source in enumerate(("from app.registry import by_id\n",
                                    "from app.main import build_components\n")):
        rogue = DOMAIN / f"_rogue_probe_app_hole_{index}.py"
        try:
            rogue.write_text(source, encoding="utf-8")
            with pytest.raises(AssertionError):
                test_domain_has_no_forbidden_absolute_imports()
        finally:
            rogue.unlink(missing_ok=True)


def test_guard_catches_forbidden_import_in_nested_package_init():
    """`__init__.py` cũng nằm trong `domain/**` nên phải bị quét.

    Dùng gói con tạm để không bao giờ đụng vào `app/domain/__init__.py` thật.
    Thư mục được dựng bằng `exist_ok=True` và việc dựng nằm TRONG `try`, nên
    một lần chạy bị ngắt giữa đường không thể khoá cứng cái lưới: rác còn lại
    của lần trước bị ghi đè rồi bị `finally` dọn sạch.
    """
    pkg = DOMAIN / "_guard_probe"
    try:
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text(
            "from app.adapters.persist import sqlite_repos\n", encoding="utf-8"
        )
        with pytest.raises(AssertionError):
            test_domain_has_no_forbidden_absolute_imports()
    finally:
        shutil.rmtree(pkg, ignore_errors=True)


def test_guard_flags_bare_import_app():
    """`import app` là import cả tầng ứng dụng — phải bị chặn."""
    rogue = DOMAIN / "_guard_probe_bare_app.py"
    try:
        rogue.write_text("import app\n", encoding="utf-8")
        with pytest.raises(AssertionError):
            test_domain_has_no_forbidden_absolute_imports()
    finally:
        rogue.unlink(missing_ok=True)


def test_guard_allows_safe_app_modules():
    """Chống bắt nhầm: `app.config`, `app.domain.*`, `app_helpers` đều hợp lệ."""
    safe = DOMAIN / "_guard_probe_safe.py"
    try:
        safe.write_text(
            "from app.config import DB_PATH\n"
            "from app.domain.models import Segment\n"
            "import app_helpers\n",
            encoding="utf-8",
        )
        test_domain_has_no_forbidden_absolute_imports()
    finally:
        safe.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# app/ports — chỉ Protocol (I-4)
# ---------------------------------------------------------------------------

def test_ports_directory_exists():
    assert PORTS.is_dir(), f"thiếu thư mục {PORTS}"


def test_ports_has_no_forbidden_absolute_imports():
    """`app/ports/` chỉ được import module chuẩn hoặc `app.domain`."""
    offenders = _import_offenders(PORTS, allowed_app=ALLOWED_APP_PORTS,
                                  stdlib_only=True)
    assert not offenders, (
        "ports/ chỉ được import module chuẩn + app.domain "
        "(nó là HỢP ĐỒNG, không được biết hạ tầng):\n  " + "\n  ".join(offenders)
    )


def test_ports_has_no_cross_layer_relative_imports():
    offenders = _relative_offenders(PORTS)
    assert not offenders, (
        "ports/ không được import ngược lên tầng trên:\n  " + "\n  ".join(offenders)
    )


def test_ports_declares_only_protocols():
    """`app/ports/` không được chứa hiện thực: class phải là `Protocol`."""
    offenders = _implementation_offenders(PORTS)
    assert not offenders, (
        "ports/ chỉ được khai báo Protocol, không hiện thực:\n  "
        + "\n  ".join(offenders)
    )


def test_ports_guard_catches_a_rogue_sqlite_import():
    """Lưới của `ports/` phải ĐỎ được, không phải một vòng lặp rỗng."""
    rogue = PORTS / "_rogue_probe_sqlite.py"
    try:
        rogue.write_text("import sqlite3\n", encoding="utf-8")
        with pytest.raises(AssertionError):
            test_ports_has_no_forbidden_absolute_imports()
    finally:
        rogue.unlink(missing_ok=True)


def test_ports_guard_catches_a_third_party_import_by_allowlist():
    """I-4 · danh sách TRẮNG: một thư viện ngoài stdlib không có trong danh sách
    đen cũ (`numpy`) vẫn phải bị chặn — đây chính là lỗ hổng của `domain/`."""
    rogue = PORTS / "_rogue_probe_numpy.py"
    try:
        rogue.write_text("import numpy\n", encoding="utf-8")
        with pytest.raises(AssertionError):
            test_ports_has_no_forbidden_absolute_imports()
    finally:
        rogue.unlink(missing_ok=True)


def test_ports_guard_catches_a_concrete_implementation():
    """Một class thường (không phải Protocol) trong `ports/` phải bị bắt."""
    rogue = PORTS / "_rogue_probe_impl.py"
    try:
        rogue.write_text(
            "class FakeRepos:\n"
            "    def get_job(self, job_id):\n"
            "        return None\n",
            encoding="utf-8",
        )
        with pytest.raises(AssertionError):
            test_ports_declares_only_protocols()
    finally:
        rogue.unlink(missing_ok=True)


def test_ports_guard_catches_a_module_level_function():
    """Hàm cấp module trong `ports/` cũng là hiện thực, không phải hợp đồng."""
    rogue = PORTS / "_rogue_probe_function.py"
    try:
        rogue.write_text("def helper() -> int:\n    return 1\n", encoding="utf-8")
        with pytest.raises(AssertionError):
            test_ports_declares_only_protocols()
    finally:
        rogue.unlink(missing_ok=True)


def test_ports_guard_allows_a_real_protocol():
    """Chống bắt nhầm: một `Protocol` thật (kể cả `typing.Protocol`) phải xanh."""
    safe = PORTS / "_guard_probe_safe.py"
    try:
        safe.write_text(
            "import typing\n"
            "from typing import Protocol\n"
            "\n"
            "from app.domain.models import Job\n"
            "\n"
            "\n"
            "class Tiny(Protocol):\n"
            "    def get_job(self, job_id: int) -> Job:\n"
            "        ...\n"
            "\n"
            "\n"
            "class AlsoTiny(typing.Protocol):\n"
            "    def list_jobs(self) -> list[Job]:\n"
            "        ...\n",
            encoding="utf-8",
        )
        test_ports_has_no_forbidden_absolute_imports()
        test_ports_declares_only_protocols()
    finally:
        safe.unlink(missing_ok=True)
