# backend/scripts/install.ps1
# Cài môi trường backend. Chạy: pwsh -File backend/scripts/install.ps1
#
# THỨ TỰ QUAN TRỌNG: torch PHẢI cài trước funasr. Nếu không, FunASR kéo bản
# torch CPU và bạn mất GPU mà không có cảnh báo nào.
#
# Script này KHÔNG chạy trong CI: nó cài vài GB và cần một GPU thật. Vì vậy nó
# chỉ được ghim bằng các bất biến văn bản trong tests/test_install_script.py —
# đọc kỹ trước khi sửa, và nhớ rằng mọi dòng `pip install` đều phải có
# `--no-cache-dir`: pip trong môi trường này RẤT chậm khi đọc cache.

$ErrorActionPreference = "Stop"
# `$LASTEXITCODE` là biến TỰ ĐỘNG: trong một tiến trình `pwsh -File` còn tươi nó
# là `$null` cho tới khi có một lệnh NGOÀI nào chạy. Đặt 0 ở đây để trạng thái
# đầu là "chưa có lệnh ngoài nào hỏng" thay vì "chưa biết" — nhưng phép kiểm
# thật vẫn nằm ở `Assert-LastExit` bên dưới (xem chú thích ở đó), vì biến này
# có thể mang giá trị của một lệnh chạy TRƯỚC khi script bắt đầu: khi gọi
# `. .\install.ps1` trong một phiên đã có lệnh ngoài hỏng thì gán ở đây mới xoá
# được nó, còn `pwsh -File` là tiến trình mới nên chỉ cần phép kiểm null-safe.
$global:LASTEXITCODE = 0
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Split-Path -Parent $here
Set-Location $backend

# R17: console Windows mặc định là cp1252, còn mọi thông báo dưới đây (và heredoc
# Python ở bước 4) đều là tiếng Việt. Đặt ở đây để MỌI tiến trình con thừa
# hưởng; cổng CUDA còn truyền thêm `-X utf8` để không phụ thuộc vào thừa hưởng.
$env:PYTHONUTF8 = "1"

function Assert-LastExit([string]$what) {
    # `$ErrorActionPreference = "Stop"` KHÔNG áp cho lệnh NGOÀI (pip, py): mã
    # thoát khác 0 vẫn đi tiếp. Thiếu phép kiểm này thì "cài bằng một lệnh"
    # thành "cài nửa vời rồi chạy tiếp trong im lặng".
    #
    # `$null` phải được coi là THÀNH CÔNG, không phải thất bại: bước nào bị BỎ
    # QUA (ví dụ `Test-Path ".venv"` đã đúng nên không chạy `py -3.10 -m venv`)
    # thì không có lệnh ngoài nào chạy và `$LASTEXITCODE` vẫn là `$null`. So
    # sánh `$null -ne 0` là ĐÚNG, nên bản cũ ném "thất bại (mã thoát )" trên
    # MỌI máy đã có `.venv` — đúng máy này — ngay ở bước 1.
    if (@($null, 0) -notcontains $LASTEXITCODE) {
        throw "$what thất bại (mã thoát $LASTEXITCODE)"
    }
}

function Set-UserEnvIfMissing([string]$name, [string]$value) {
    # R60/R64: biến chỉ đặt trong tiến trình thì lần chạy app SAU không thấy.
    # Đặt ở mức User, và TÔN TRỌNG giá trị người dùng đã có.
    $current = [Environment]::GetEnvironmentVariable($name, "User")
    if ([string]::IsNullOrEmpty($current)) {
        [Environment]::SetEnvironmentVariable($name, $value, "User")
        $current = $value
        Write-Host "   đặt $name = $current (mức User)"
    } else {
        Write-Host "   giữ nguyên $name = $current (đã có ở mức User)"
    }
    Set-Item -Path "Env:$name" -Value $current
}

Write-Host "== 1/7 · venv ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { py -3.10 -m venv .venv }
Assert-LastExit "tạo venv"
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --no-cache-dir --upgrade pip
Assert-LastExit "nâng cấp pip"

Write-Host "== 2/7 · cache model về ổ D: (R60/R64) ==" -ForegroundColor Cyan
# `app/config.py:HF_HOME` chỉ là hằng số Python; `huggingface_hub` đọc BIẾN MÔI
# TRƯỜNG, và ModelScope đọc `MODELSCOPE_CACHE`. Đặt sớm để một lần hỏng ở bước
# sau vẫn để lại đúng chỗ chứa model.
$modelRoot = if ($env:HF_HOME) { $env:HF_HOME } else { "D:\models\hf" }
# Giá trị dưới đây được ĐẶT Ở MỨC USER, tức là còn sống sau khi script kết thúc:
# trỏ nó vào một ổ không tồn tại thì mọi lần tải model SAU đó đều hỏng ở một chỗ
# cách xa nguyên nhân. Kiểm ổ TRƯỚC khi ghim, rồi tạo thư mục — `D:\models\hf`
# mặc định không có sẵn trên máy mới.
$qualifier = Split-Path -Qualifier $modelRoot -ErrorAction SilentlyContinue
if ($qualifier -and -not (Test-Path $qualifier)) {
    throw "HF_HOME trỏ vào ổ không tồn tại: $modelRoot — đặt `$env:HF_HOME trước khi chạy"
}
try {
    New-Item -ItemType Directory -Force -Path $modelRoot | Out-Null
} catch {
    throw "không tạo được thư mục cache model: $modelRoot — $($_.Exception.Message)"
}
Set-UserEnvIfMissing "HF_HOME" $modelRoot
Set-UserEnvIfMissing "MODELSCOPE_CACHE" (Join-Path $modelRoot "modelscope")

Write-Host "== 3/7 · torch cu121 (TRƯỚC funasr) ==" -ForegroundColor Cyan
& $py -m pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 `
    --index-url https://download.pytorch.org/whl/cu121
Assert-LastExit "cài torch cu121"

Write-Host "== 4/7 · kiểm tra CUDA ==" -ForegroundColor Cyan
& $py -X utf8 -c @'
import torch, sys
ok = torch.cuda.is_available()
print('torch', torch.__version__, '| cuda available:', ok)
if not ok:
    sys.exit('THẤT BẠI: torch không thấy GPU. Dừng ở đây thay vì chạy CPU.')
print('device:', torch.cuda.get_device_name(0))
'@
Assert-LastExit "kiểm tra CUDA"

Write-Host "== 5/7 · setuptools/wheel, jieba RIÊNG, rồi phần còn lại ==" -ForegroundColor Cyan
& $py -m pip install --no-cache-dir --upgrade setuptools wheel
Assert-LastExit "cài setuptools + wheel"
# R70: `jieba` chỉ có sdist, KHÔNG có wheel Windows, và pip TREO ~30 phút (đo
# được trên đúng máy này: log đứng im ở 1389 byte, một tiến trình python đã ăn
# 1802 giây CPU) ở bước nó tự dựng build-isolation. Cài riêng với
# `--no-build-isolation` SAU khi setuptools+wheel đã có.
& $py -m pip install --no-cache-dir --no-build-isolation "jieba==0.42.1"
Assert-LastExit "cài jieba"
# Task 9: ba gói của OPUS-MT (Marian) cài chung dòng này. Chúng có wheel trên
# Windows nên KHÔNG dính kiểu treo của `jieba` (R70) — chỉ `jieba` mới cần
# `--no-build-isolation` và một dòng riêng. Nêu tường minh ở đây để engine dịch
# duy nhất chạy được offline hiện ra trong log cài đặt thay vì lẫn trong `-r`.
& $py -m pip install --no-cache-dir -r requirements.txt `
    "transformers==4.46.3" "sentencepiece==0.2.0" "sacremoses==0.1.1"
Assert-LastExit "cài requirements.txt"

Write-Host "== 6/7 · cổng import faster_whisper (R71) ==" -ForegroundColor Cyan
# R71: `pip install` XANH không có nghĩa là `import` chạy được. faster_whisper
# 1.1.1 làm `import requests` trong utils.py, còn huggingface_hub 1.x đã bỏ phụ
# thuộc đó — nên thiếu `requests` thì cả đường ASR chết ở runtime trong khi mọi
# test vẫn xanh. Cổng này biến lần hỏng đó thành một lần DỪNG CÀI ĐẶT, đúng chỗ
# và đúng lúc. `requests==2.32.3` được ghim trong requirements.txt (không lặp
# lại ở đây: mọi dòng pip đều phải có --no-cache-dir, xem test_install_script).
& $py -X utf8 -c @'
import sys
try:
    import requests, faster_whisper
except Exception as exc:
    sys.exit(f'THẤT BẠI: import nổ {type(exc).__name__}: {exc}')
print('requests', requests.__version__)
print('faster_whisper', faster_whisper.__version__, '| import OK')
'@
Assert-LastExit "import faster_whisper"

Write-Host "== 7/7 · ollama + yt-dlp ==" -ForegroundColor Cyan
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "   ollama đã có sẵn"
} else {
    Write-Host "   chưa có ollama — cài bằng: winget install Ollama.Ollama" -ForegroundColor Yellow
}
if (-not (Get-Command yt-dlp -ErrorAction SilentlyContinue)) {
    & $py -m pip install --no-cache-dir --upgrade yt-dlp
    Assert-LastExit "cài yt-dlp"
}

Write-Host ""
Write-Host "XONG. Biến môi trường đã đặt ở mức User:" -ForegroundColor Green
Write-Host "  HF_HOME = $modelRoot"
Write-Host "  MODELSCOPE_CACHE = $(Join-Path $modelRoot 'modelscope')"
Write-Host 'Shell đang mở chưa thấy biến mới — mở shell mới, hoặc đặt lại trong phiên này.'
Write-Host 'Tiếp theo: .\.venv\Scripts\python.exe -m pytest   (xem backend/README.md)'
