"""Hợp đồng văn bản của `scripts/install.ps1` (R17, R60, R64, R70).

Script này KHÔNG chạy được trong CI: nó cài vài GB và cần một GPU thật. Nên nó
KHÔNG có RED kiểu "chạy rồi đỏ" — thứ duy nhất ghim được ở đây là những dòng mà
ledger đã ĐO là hỏng trên đúng máy này:

* R70 · ``pip install -r requirements.txt`` TREO ~30 phút ở ``jieba`` (sdist
  19,2 MB, không có wheel Windows; log đứng im, 1802 giây CPU), và pip còn rất
  chậm khi đọc cache ⇒ mọi dòng pip phải có ``--no-cache-dir``, ``jieba`` phải
  cài riêng với ``--no-build-isolation`` SAU ``setuptools``+``wheel``.
* R17 · console Windows là cp1252, còn thông báo của script là tiếng Việt ⇒
  phải có ``PYTHONUTF8=1``.
* R60/R64 · ``HF_HOME``/``MODELSCOPE_CACHE`` chỉ đặt trong tiến trình thì lần
  chạy app SAU không thấy ⇒ phải đặt ở mức User.

Mỗi khẳng định dưới đây đã được chứng minh là CÓ THỂ ĐỎ bằng cách xoá đúng thứ
nó canh (xem `task-20-report.md`, mục "mutation log").
"""
from __future__ import annotations

import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parents[1]
INSTALL = BACKEND / "scripts" / "install.ps1"


def _code_lines() -> list[str]:
    """Chỉ dòng CODE: bỏ dòng trống và dòng bắt đầu bằng `#`.

    Không lọc thì chính khối chú thích giải thích ruling sẽ thoả mãn phép kiểm
    — một dạng test tự thoả mãn.
    """
    text = INSTALL.read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def _text() -> str:
    return INSTALL.read_text(encoding="utf-8")


def test_install_script_exists():
    assert INSTALL.exists(), "brief Task 20 yêu cầu backend/scripts/install.ps1"


def test_every_pip_install_disables_the_cache():
    """R70 · pip trong môi trường này rất chậm khi đọc cache."""
    offenders = [line for line in _code_lines()
                 if "pip install" in line and "--no-cache-dir" not in line]
    assert offenders == [], f"dòng pip thiếu --no-cache-dir: {offenders}"


def test_jieba_is_installed_separately_without_build_isolation():
    """R70 · `-r requirements.txt` một mình là lệnh TREO ĐO ĐƯỢC."""
    lines = _code_lines()
    jieba = [line for line in lines if "pip install" in line and "jieba" in line]
    assert jieba, "phải cài `jieba` riêng, không phó mặc cho `-r requirements.txt`"
    for line in jieba:
        assert "--no-build-isolation" in line, (
            f"`jieba` phải cài với --no-build-isolation: {line}"
        )
    requirements = [line for line in lines if "pip install" in line
                    and "-r requirements.txt" in line]
    assert requirements, "script phải cài `-r requirements.txt` cho phần còn lại"
    assert all("jieba" not in line for line in requirements), (
        "`jieba` không được nằm chung dòng với -r requirements.txt: đó đúng là "
        "lệnh đã treo"
    )


def test_setuptools_and_wheel_are_installed_before_jieba():
    """`--no-build-isolation` chỉ dùng được khi đã có setuptools+wheel."""
    lines = _code_lines()
    first = {}
    for index, line in enumerate(lines):
        if "pip install" not in line:
            continue
        if "setuptools" in line and "setuptools" not in first:
            first["setuptools"] = index
        if "jieba" in line and "jieba" not in first:
            first["jieba"] = index
    assert "setuptools" in first, "phải cài setuptools+wheel trước"
    assert "jieba" in first, "phải cài jieba"
    assert first["setuptools"] < first["jieba"], (
        "setuptools+wheel phải cài TRƯỚC jieba, nếu không --no-build-isolation "
        "không có gì để dùng"
    )


def test_torch_is_installed_before_the_rest_and_the_cuda_gate_stops_the_script():
    """Cài ngược thứ tự thì FunASR kéo torch CPU và mất GPU trong im lặng."""
    lines = _code_lines()
    torch_at = next((i for i, line in enumerate(lines) if "torch==" in line), None)
    requirements_at = next(
        (i for i, line in enumerate(lines)
         if "pip install" in line and "-r requirements.txt" in line), None)
    assert torch_at is not None, "phải ghim torch==2.5.1 từ index cu121"
    assert requirements_at is not None, "phải cài -r requirements.txt"
    assert torch_at < requirements_at, "torch PHẢI cài trước phần còn lại"

    text = _text()
    assert "torch.cuda.is_available()" in text, (
        "phải có cổng CUDA: chạy CPU mà không biết là kiểu hỏng tệ nhất"
    )
    assert "sys.exit" in text, "cổng CUDA phải THOÁT, không chỉ in cảnh báo"


def test_pythonutf8_is_set_for_every_child_process():
    """R17 · thông báo tiếng Việt + heredoc Python trên console cp1252."""
    text = _text()
    assert re.search(r'\$env:PYTHONUTF8\s*=\s*["\']1["\']', text), (
        "install.ps1 phải đặt $env:PYTHONUTF8 = \"1\" cho tiến trình con"
    )
    assert "-X utf8" in text, (
        "cổng CUDA nên tự truyền -X utf8 thay vì chỉ tin vào thừa hưởng"
    )


def test_child_failures_stop_the_script():
    """`$ErrorActionPreference` KHÔNG áp cho lệnh ngoài (pip/py).

    Thiếu phép kiểm mã thoát thì "cài bằng một lệnh" thành "cài nửa vời rồi
    chạy tiếp trong im lặng" — đúng loại im lặng đã hai lần bị chẩn đoán sai.
    """
    lines = _code_lines()
    assert any("Assert-LastExit" in line and "function" in line for line in lines), (
        "phải có hàm kiểm mã thoát của lệnh ngoài"
    )
    pip_lines = [i for i, line in enumerate(lines) if "pip install" in line]
    checked = [i for i, line in enumerate(lines) if line.startswith("Assert-LastExit")]
    assert checked, "phải gọi Assert-LastExit sau các lệnh ngoài"
    assert max(pip_lines) < max(checked), "lần cài cuối vẫn phải được kiểm"


def test_model_cache_is_pinned_at_user_scope():
    """R60/R64 · biến chỉ đặt trong tiến trình thì lần chạy app sau không thấy."""
    text = _text()
    assert re.search(r'SetEnvironmentVariable\([^)]*["\']User["\']', text), (
        "phải đặt biến ở mức User, không chỉ trong tiến trình install.ps1"
    )
    assert '"HF_HOME"' in text, "phải ghim HF_HOME"
    assert '"MODELSCOPE_CACHE"' in text, (
        "thiếu MODELSCOPE_CACHE thì SenseVoice + fsmn-vad + ct-punc rơi về ổ C:"
    )


def test_last_exit_code_check_treats_null_as_success():
    """H1 · `$LASTEXITCODE` là `$null` khi bước đó KHÔNG chạy lệnh ngoài nào.

    Trên máy đã có `backend\\.venv`, `if (-not (Test-Path ".venv"))` không chạy
    `py -3.10 -m venv`, nên `$LASTEXITCODE` vẫn là `$null`; `$null -ne 0` là
    ĐÚNG và bản cũ ném `tạo venv thất bại (mã thoát )` ngay bước 1. Đúng máy
    này có `.venv`, nên lệnh cài trong README hỏng thật, không phải giả định.
    """
    text = _text()
    assert "$LASTEXITCODE" in text, "phải kiểm mã thoát của lệnh ngoài"
    assert re.search(r"@\(\s*\$null\s*,\s*0\s*\)\s*-notcontains\s+\$LASTEXITCODE", text), (
        "phép kiểm phải null-safe: coi `$null` là THÀNH CÔNG "
        "(`@($null, 0) -notcontains $LASTEXITCODE`), nếu không thì mọi lần chạy "
        "lại khi `.venv` đã có đều ném ở bước 1"
    )
    assert not re.search(r"\$LASTEXITCODE\s+-ne\s+0", text), (
        "`$LASTEXITCODE -ne 0` là ĐÚNG khi giá trị là `$null` — không được quay lại"
    )


def test_step_labels_are_one_consistent_series():
    """L3 · nhãn bước từng nhảy `1/6..4/6` rồi `5/7..7/7`."""
    labels = re.findall(r"==\s*(\d+)/(\d+)\s*·", _text())
    assert labels, "phải có nhãn bước dạng `== N/M · ...`"
    denominators = {total for _step, total in labels}
    assert denominators == {"7"}, (
        f"mọi nhãn phải cùng một mẫu số, thực tế: {sorted(denominators)}"
    )
    steps = [int(step) for step, _total in labels]
    assert steps == list(range(1, 8)), f"nhãn bước phải là 1..7 liên tục: {steps}"


def test_hf_home_default_is_checked_for_an_existing_drive():
    """M2 · `HF_HOME` bị ghim ở mức User, không được trỏ vào ổ không tồn tại."""
    text = _text()
    assert "Split-Path -Qualifier" in text, (
        "phải tách ổ của $modelRoot để kiểm nó có thật trước khi ghim ở mức User"
    )
    assert re.search(r"Test-Path\s+\$qualifier", text), (
        "phải Test-Path ổ đó; ghim `D:\\models\\hf` trên máy không có D: thì mọi "
        "lần tải model SAU đều hỏng ở một chỗ cách xa nguyên nhân"
    )
    assert "New-Item -ItemType Directory" in text, (
        "thư mục cache phải được tạo; mặc định D:\\models\\hf không có sẵn"
    )


def test_final_banner_prints_the_actual_cache_root():
    """L4 · banner từng in cứng `D:\\models\\hf` kể cả khi $modelRoot khác."""
    text = _text()
    assert re.search(r"Write-Host\s+[\"']\s*HF_HOME\s*=\s*\$modelRoot", text), (
        "banner phải in $modelRoot, không in giá trị mặc định"
    )
    assert "HF_HOME = D:\\models\\hf" not in text, (
        "không được in cứng giá trị mặc định: nó sai khi người dùng đã đặt HF_HOME"
    )
