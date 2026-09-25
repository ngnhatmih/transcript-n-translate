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
    if ($LASTEXITCODE -ne 0) { throw "$what thất bại (mã thoát $LASTEXITCODE)" }
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

Write-Host "== 1/6 · venv ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { py -3.10 -m venv .venv }
Assert-LastExit "tạo venv"
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --no-cache-dir --upgrade pip
Assert-LastExit "nâng cấp pip"

Write-Host "== 2/6 · cache model về ổ D: (R60/R64) ==" -ForegroundColor Cyan
# `app/config.py:HF_HOME` chỉ là hằng số Python; `huggingface_hub` đọc BIẾN MÔI
# TRƯỜNG, và ModelScope đọc `MODELSCOPE_CACHE`. Đặt sớm để một lần hỏng ở bước
# sau vẫn để lại đúng chỗ chứa model.
$modelRoot = if ($env:HF_HOME) { $env:HF_HOME } else { "D:\models\hf" }
Set-UserEnvIfMissing "HF_HOME" $modelRoot
Set-UserEnvIfMissing "MODELSCOPE_CACHE" (Join-Path $modelRoot "modelscope")

Write-Host "== 3/6 · torch cu121 (TRƯỚC funasr) ==" -ForegroundColor Cyan
& $py -m pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 `
    --index-url https://download.pytorch.org/whl/cu121
Assert-LastExit "cài torch cu121"

Write-Host "== 4/6 · kiểm tra CUDA ==" -ForegroundColor Cyan
& $py -X utf8 -c @'
import torch, sys
ok = torch.cuda.is_available()
print('torch', torch.__version__, '| cuda available:', ok)
if not ok:
    sys.exit('THẤT BẠI: torch không thấy GPU. Dừng ở đây thay vì chạy CPU.')
print('device:', torch.cuda.get_device_name(0))
'@
Assert-LastExit "kiểm tra CUDA"

Write-Host "== 5/6 · setuptools/wheel, jieba RIÊNG, rồi phần còn lại ==" -ForegroundColor Cyan
& $py -m pip install --no-cache-dir --upgrade setuptools wheel
Assert-LastExit "cài setuptools + wheel"
# R70: `jieba` chỉ có sdist, KHÔNG có wheel Windows, và pip TREO ~30 phút (đo
# được trên đúng máy này: log đứng im ở 1389 byte, một tiến trình python đã ăn
# 1802 giây CPU) ở bước nó tự dựng build-isolation. Cài riêng với
# `--no-build-isolation` SAU khi setuptools+wheel đã có.
& $py -m pip install --no-cache-dir --no-build-isolation "jieba==0.42.1"
Assert-LastExit "cài jieba"
& $py -m pip install --no-cache-dir -r requirements.txt
Assert-LastExit "cài requirements.txt"

Write-Host "== 6/6 · ollama + yt-dlp ==" -ForegroundColor Cyan
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
Write-Host '  HF_HOME = D:\models\hf'
Write-Host '  MODELSCOPE_CACHE = D:\models\hf\modelscope'
Write-Host 'Shell đang mở chưa thấy biến mới — mở shell mới, hoặc đặt lại trong phiên này.'
Write-Host 'Tiếp theo: .\.venv\Scripts\python.exe -m pytest   (xem backend/README.md)'
