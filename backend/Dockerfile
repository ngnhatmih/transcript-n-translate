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
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY . .

# `PHUDE_HOST=0.0.0.0` là mệnh đề sống-còn: `config.API_HOST` mặc định `127.0.0.1`, mà
# trong container thì chỉ nghe loopback ⇒ map cổng ra ngoài không tới được.
# `HF_HOME=/models` vì mặc định trong `config.py` là đường Windows (`D:\models\hf`).
# `/models` là volume để model 1,6 GB không tải lại mỗi lần dựng lại image.
# `PHUDE_ASR_DEVICE=cpu` là mệnh đề sống-còn thứ hai: mặc định adapter là `cuda`, và
# trong container không có driver GPU ⇒ job `asr` chết với "CUDA driver version is
# insufficient". Đo được: thiếu dòng này thì upload đầu tiên FAILED.
ENV HF_HOME=/models \
    PHUDE_HOST=0.0.0.0 \
    PHUDE_PORT=8620 \
    PHUDE_DATA=/data \
    PHUDE_DB=/data/app.db \
    PHUDE_ASR_DEVICE=cpu \
    PYTHONUNBUFFERED=1

VOLUME ["/data", "/models"]
EXPOSE 8620

CMD ["python", "run_api.py"]
