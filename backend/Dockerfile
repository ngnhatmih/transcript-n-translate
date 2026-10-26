# Image CHẠY API (không phải image test, không phải image GPU).
#
# Chỉ chứa đường mặc định của sản phẩm: `fw-large-v3-turbo` (faster-whisper, CPU) và
# `opus-mt` (in-process). KHÔNG có SenseVoice (torch), KHÔNG có Ollama — xem
# `requirements-docker.txt` và README mục "Chạy bằng Docker".
FROM python:3.10-slim

# `ffmpeg` là BẮT BUỘC, không phải tiện ích: job `ingest` bóc âm thanh khỏi media bằng
# ffmpeg, thiếu nó thì mọi upload chết ở job đầu tiên.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài phụ thuộc TRƯỚC khi COPY mã nguồn: sửa một dòng Python không phải cài lại pip.
COPY requirements-docker.txt ./
# `torch` cài RIÊNG, với index riêng: `MarianMTModel` (OPUS-MT) cần nó, và bản CUDA
# mang theo `libcublas.so.12`/`cudnn` mà CTranslate2 cần cho GPU. Để index này trong
# `requirements-docker.txt` thì pip hỏi host đó cho MỌI gói và build FAILED (đo được:
# ReadTimeout khi resolve starlette) — nên nó chỉ áp cho đúng một gói ở đây.
# Máy không GPU: đổi `cu121` → `cpu` và `torch==2.5.1` → `torch==2.5.1+cpu`.
RUN pip install --no-cache-dir --timeout 120 \
        --extra-index-url https://download.pytorch.org/whl/cu121 torch==2.5.1 \
 && pip install --no-cache-dir --timeout 120 -r requirements-docker.txt

COPY . .

# `PHUDE_HOST=0.0.0.0` là mệnh đề sống-còn: `config.API_HOST` mặc định `127.0.0.1`, mà
# trong container thì chỉ nghe loopback ⇒ map cổng ra ngoài không tới được.
# `HF_HOME=/models` vì mặc định trong `config.py` là đường Windows (`D:\models\hf`).
# `/models` là volume để model 1,6 GB không tải lại mỗi lần dựng lại image.
# `LD_LIBRARY_PATH` trỏ vào `torch/lib`: trên Linux, CTranslate2 `dlopen`
# `libcublas.so.12` theo ĐƯỜNG NẠP của loader; `ensure_cuda_runtime()` của repo chỉ
# chèn vào `PATH` (đúng cho Windows). Thiếu dòng này thì GPU ASR chết với
# "Library cublas64_12.so is not found" — đúng lỗi R72 nhưng ở biến thể Linux.
# `PHUDE_ASR_DEVICE` KHÔNG đặt ở đây mà ở `docker-compose.yml`: image giữ trung lập,
# chỗ chọn máy có GPU hay không là chỗ triển khai.
ENV HF_HOME=/models \
    PHUDE_HOST=0.0.0.0 \
    PHUDE_PORT=8620 \
    PHUDE_DATA=/data \
    PHUDE_DB=/data/app.db \
    LD_LIBRARY_PATH=/usr/local/lib/python3.10/site-packages/torch/lib \
    PYTHONUNBUFFERED=1

VOLUME ["/data", "/models"]
EXPOSE 8620

CMD ["python", "run_api.py"]
