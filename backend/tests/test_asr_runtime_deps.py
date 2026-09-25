"""R71 · `faster_whisper` cần `requests`, và `requests` phải được GHIM.

Lỗi thật đã đo được trên đúng máy này (không phải lo xa):

    $ .\\.venv\\Scripts\\python.exe -c "import faster_whisper"
    File "...\\faster_whisper\\utils.py", line 8, in <module>
        import requests
    ModuleNotFoundError: No module named 'requests'

`faster_whisper 1.1.1` làm `import requests` trong `utils.py`, còn
`huggingface_hub` 1.x đã BỎ phụ thuộc `requests`. Nghĩa là một môi trường cài
ĐÚNG `faster-whisper==1.1.1` vẫn có `import faster_whisper` nổ, và TOÀN BỘ
đường ASR chết ở runtime — trong khi 359 test vẫn xanh, vì không test nào chạm
vào module đó (`FasterWhisperEngine._load()` import nó BÊN TRONG hàm, sau khi
`model_factory` đã được bơm).

Vì vậy file này ghim **KHAI BÁO**, không phải hành vi: bộ pytest không được
import `faster_whisper` mỗi lần chạy (nó nặng, và import nó trong test là biến
suite thành thứ phụ thuộc môi trường — đúng thứ vừa làm lỗi này vô hình).
"""
from __future__ import annotations

import pathlib
import re
import subprocess

BACKEND = pathlib.Path(__file__).resolve().parents[1]
REQUIREMENTS = BACKEND / "requirements.txt"
INSTALL = BACKEND / "scripts" / "install.ps1"
VENV_PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"

# R71 phải được ghim ở đúng một chỗ: requirements.txt. install.ps1 không được
# lặp lại một dòng pip riêng cho nó — luật "--no-cache-dir trên MỌI dòng pip"
# của test_install_script.py sẽ đỏ ngay, và hai nguồn sự thật thì trôi khỏi nhau.
REQUIRED_PACKAGE = "requests"

_PIN = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)\s*==\s*(?P<version>[^\s;]+)")


def _requirement_lines() -> list[str]:
    """Dòng khai báo thật: bỏ dòng trống và dòng bắt đầu bằng `#`."""
    return [line.strip() for line in
            REQUIREMENTS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")]


def _declared_pins() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in _requirement_lines():
        match = _PIN.match(line)
        if match:
            out[match.group("name").lower()] = match.group("version")
    return out


def test_requests_is_declared_and_version_pinned_in_requirements():
    """R71 · thiếu dòng này thì `import faster_whisper` nổ ở runtime.

    Phép kiểm CỐ Ý đòi `==`: một dòng `requests` không ghim cũng đủ làm import
    chạy, nhưng để môi trường trôi thì lần hỏng sau không tái lập được.
    """
    pins = _declared_pins()
    assert REQUIRED_PACKAGE in pins, (
        f"requirements.txt phải ghim `{REQUIRED_PACKAGE}==<version>`: faster_whisper "
        "1.1.1 import nó trong utils.py, huggingface_hub 1.x không còn kéo nó theo. "
        f"Hiện có: {sorted(pins) or 'không có dòng ghim nào'}"
    )
    assert pins[REQUIRED_PACKAGE], "phải ghim một version cụ thể, không để trôi"


def test_install_ps1_mentions_the_same_pin_and_gates_the_import():
    """`install.ps1` phải nhắc đúng version đó VÀ có cổng import.

    Cổng import là thứ biến "pip xanh" thành "import chạy được": cài xong vẫn
    phải chứng minh `import faster_whisper` không nổ, ngay tại chỗ.
    """
    text = INSTALL.read_text(encoding="utf-8")
    version = _declared_pins()[REQUIRED_PACKAGE]
    assert f"{REQUIRED_PACKAGE}=={version}" in text, (
        f"install.ps1 phải nhắc `{REQUIRED_PACKAGE}=={version}`, cùng version với "
        "requirements.txt — hai chỗ lệch nhau là môi trường mới lại hỏng"
    )
    assert "import faster_whisper" in text, (
        "install.ps1 phải có cổng `import faster_whisper`: pip cài xanh không "
        "chứng minh được import chạy được (R71 là đúng ví dụ đó)"
    )


def test_the_installed_venv_actually_has_the_package():
    """Môi trường ĐANG dùng phải thật sự có `requests`.

    Chạy trong tiến trình con với `PYTHONPATH` RỖNG và cwd ngoài `backend/`:
    nếu để nguyên, `pythonpath = .` của pytest.ini có thể khiến một module tên
    `requests.py` nằm trong repo được import thay cho gói thật, và phép kiểm sẽ
    xanh vì lý do sai.
    """
    if not VENV_PYTHON.exists():
        import pytest
        pytest.skip(f"chưa có venv tại {VENV_PYTHON}")
    env = {"PYTHONPATH": "", "PYTHONIOENCODING": "utf-8", "SYSTEMROOT": "C:\\Windows"}
    proc = subprocess.run(  # noqa: S603 - đường dẫn cố định, không có shell
        [str(VENV_PYTHON), "-B", "-c",
         f"import {REQUIRED_PACKAGE}; print({REQUIRED_PACKAGE}.__version__)"],
        cwd=str(BACKEND.parent), env=env,
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"`import {REQUIRED_PACKAGE}` trong venv thất bại — faster_whisper sẽ nổ "
        f"y hệt.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert proc.stdout.strip(), "phải in ra version thật của gói đã cài"
