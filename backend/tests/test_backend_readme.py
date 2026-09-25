"""Hợp đồng của `backend/README.md` (R73).

README dạy chạy `python -m pytest -q` trong khi `pytest.ini` **đã** có
`addopts = -q` ⇒ lệnh đó thành `-qq` và **mất dòng "N passed"**. Người làm đúng
theo tài liệu sẽ không biết bao nhiêu test đã chạy — đúng cái bẫy đã cắn ba lần
trong phiên này. Bài dưới chỉ soi những dòng LỆNH, để phần giải thích vẫn được
phép nhắc tới chế độ quiet.
"""
from __future__ import annotations

import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]
README = BACKEND / "README.md"


def _text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_exists():
    assert README.exists(), "brief Task 20 yêu cầu backend/README.md"


def test_pytest_commands_do_not_repeat_the_quiet_flag():
    """R73 · `-q` đã nằm trong `pytest.ini`; thêm nữa là `-qq`."""
    commands = [line for line in _text().splitlines() if "-m pytest" in line]
    assert commands, "README phải dạy cách chạy pytest"
    redundant = [line for line in commands if "-q" in line]
    assert redundant == [], (
        f"pytest.ini đã có addopts = -q, bỏ -q khỏi README: {redundant}"
    )


def test_readme_documents_the_two_entry_points_it_owns():
    text = _text()
    assert "scripts/install.ps1" in text or "scripts\\install.ps1" in text, (
        "README phải nói cách cài"
    )
    assert "smoke_asr.py" in text, (
        "README phải nói smoke test model thật chạy thế nào"
    )
    assert "HF_HOME" in text, "phải nói cache model nằm ở đâu"
