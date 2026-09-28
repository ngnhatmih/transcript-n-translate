"""Hợp đồng của `backend/README.md` (R73).

README dạy chạy `python -m pytest -q` trong khi `pytest.ini` **đã** có
`addopts = -q` ⇒ lệnh đó thành `-qq` và **mất dòng "N passed"**. Người làm đúng
theo tài liệu sẽ không biết bao nhiêu test đã chạy — đúng cái bẫy đã cắn ba lần
trong phiên này. Bài dưới chỉ soi những dòng LỆNH, để phần giải thích vẫn được
phép nhắc tới chế độ quiet.

Bài cuối tệp kiểm SỐ NỀN: nó từng ghim `798` trong khi suite có `799` (bài được
thêm ở `a428334`, cùng commit sửa README). Đếm bằng một lần `pytest --collect-only`
TRONG TIẾN TRÌNH CON, có `-p no:cacheprovider` để không ghi `.pytest_cache` vào
repo — một test không được phép làm bẩn cây nó đang kiểm.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

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


# ---------------------------------------------------------------------------
# Số nền của README phải khớp số bài THẬT (M-5 của review cuối)
# ---------------------------------------------------------------------------

_REPO_ROOT = BACKEND.parent


def _readme_baseline(text: str | None = None) -> tuple[int, int]:
    """`(passed, deselected)` đọc từ khối ``` ngay dưới dòng "Con số nền".

    Đọc bằng VỊ TRÍ (khối đầu tiên sau tiêu đề) chứ không quét mọi số trong tệp:
    README còn nhiều con số khác (`798`, `94 ký tự`, `219/149`) và một phép quét
    toàn văn sẽ bắt nhầm chúng. Tham số `text` chỉ để bài tự-kiểm ở dưới truyền
    vào một bản README giả.
    """
    lines = (_text() if text is None else text).splitlines()
    start = next(i for i, line in enumerate(lines) if "Con số nền" in line)
    fence = next(i for i in range(start, len(lines)) if lines[i].strip().startswith("```"))
    body = lines[fence + 1].strip()
    match = re.search(r"(\d+) passed, (\d+) deselected", body)
    assert match, f"không đọc được số nền từ README: {body!r}"
    return int(match.group(1)), int(match.group(2))


#: Dòng tổng kết của `--collect-only` khi `addopts = -q` đang bật (xem
#: `pytest.ini`), nay là `830/843 tests collected (13 deselected) in 1,07s`. Đọc
#: CẢ HAI vế của phân số chứ không chỉ một con số: lần chạy mặc định CHỌN `830`
#: bài nhưng chỉ `830` bài đó mới `passed` khi `ffmpeg`/`ffprobe` có mặt — thiếu
#: chúng thì `tests/test_ingest.py` skip cả module và số `passed` tụt xuống
#: `821`. Vì vậy "số bài chọn được" không bằng "số bài passed", và tệp này chỉ
#: được phép khẳng định thứ nó đo được.
#:
#: ⚠️ LUẬT: hai con số trên là SỐ BÀI TEST, nên mọi task backend THÊM/GỠ bài test
#: PHẢI cập nhật `backend/README.md` trong CÙNG commit — nếu không,
#: `test_readme_baseline_matches_the_tests_actually_collected` đỏ. Và khi cập nhật
#: thì cập nhật CẢ khối comment này: nó từng còn ghi `821/834` trong khi README đã
#: bump lên `830` — tức số cũ nằm ngay trong tệp tồn tại để ghim số.
_COLLECTED = re.compile(r"(\d+)/(\d+) tests? collected \((\d+) deselected\)")


def _collect_counts(marker: list[str]) -> tuple[int, int]:
    """`(selected, deselected)` mà pytest THU ĐƯỢC với một cách chọn marker.

    KHÔNG thêm `-q` vào lệnh: `pytest.ini` đã có `addopts = -q`, và thêm nữa là
    `-qq` — đúng cái bẫy mà ba bài đầu tệp này tồn tại để chặn. `-p
    no:cacheprovider` giữ `.pytest_cache` khỏi cây repo mà bài này đang kiểm.
    """
    out = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "--collect-only", "-p",
         "no:cacheprovider", *marker],
        cwd=BACKEND, capture_output=True, text=True, check=True,
    ).stdout
    match = _COLLECTED.search(out)
    assert match, f"không đọc được số bài thu được:\n{out}"
    return int(match.group(1)), int(match.group(3))


def test_readme_baseline_matches_the_tests_actually_collected():
    """Số nền trong README phải khớp số bài THẬT mà lần chạy mặc định chọn.

    README tự nói con số này tồn tại "để phát hiện TRÔI: một thay đổi làm nó giảm
    là một bài đã bị gỡ". Nhưng nó chỉ phát hiện được trôi nếu chính nó ĐÚNG: nó
    từng ghi `798` trong khi suite có `799` (bài được thêm ở `a428334`, cùng commit
    đã sửa README), nên mọi lần chạy đều báo lệch +1 giả. Một con số canh trôi mà
    không ai canh lại nó là một lời hứa, không phải một phép kiểm.

    Đếm bằng HAI lần `--collect-only` trong tiến trình con, mỗi lần đúng một bộ
    luật của `pytest.ini`:

    * mặc định (`-m "not live"` sẵn trong ini) ⇒ vế trái của lần chạy mặc định;
    * `-m live` ⇒ vế phải (`deselected`).

    Khớp theo SỐ LƯỢNG, không theo tên: đổi tên một bài không làm nó đỏ, gỡ một
    bài thì có. Tiến trình con không đệ quy: `--collect-only` không chạy bài nào.
    """
    selected, deselected = _collect_counts(["-m", "not live"])
    readme_passed, readme_deselected = _readme_baseline()
    assert (selected, deselected) == (readme_passed, readme_deselected), (
        f"README ghim {readme_passed} passed + {readme_deselected} deselected, "
        f"nhưng lần chạy mặc định CHỌN {selected} bài và bỏ {deselected}. Số nền "
        "tồn tại để phát hiện trôi — cập nhật nó trong `backend/README.md` nếu "
        "thay đổi là cố ý."
    )
    # Vế `-m live` phải bù đúng phần còn lại, nếu không thì `pytest.ini` đã đổi
    # luật marker và phép đếm ở trên đang so hai tập khác nhau.
    live_selected, _ = _collect_counts(["-m", "live"])
    assert live_selected == deselected, (
        f"`-m live` chọn {live_selected} bài nhưng lần chạy mặc định bỏ "
        f"{deselected}: hai phép đếm không còn là hai nửa của một tập"
    )


def test_the_baseline_check_can_fail(tmp_path):
    """Lưới phải ĐỎ được: một README ghim số sai thì phép kiểm phải ném.

    Bài trên chỉ có răng nếu phép so của nó thật sự đỏ khi số lệch. Đo bằng chính
    hàm đọc README trên một bản giả có số nền sai, chứ không chạy lại cả suite.
    """
    wrong = tmp_path / "README.md"
    wrong.write_text(
        "## Kiểm thử\n\nCon số nền của lần chạy mặc định:\n\n"
        "```\n1 passed, 0 deselected, 1 warning\n```\n",
        encoding="utf-8",
    )
    readme_passed, readme_deselected = _readme_baseline(
        wrong.read_text(encoding="utf-8"))
    assert (readme_passed, readme_deselected) == (1, 0), (
        "hàm đọc phải lấy đúng số từ bản giả; nếu nó đọc sai thì bài trên cũng "
        "đang so một con số sai"
    )
    assert _readme_baseline() != (readme_passed, readme_deselected), (
        "README THẬT phải khác bản giả này, nếu không thì phép đỏ ở đây vô nghĩa"
    )
