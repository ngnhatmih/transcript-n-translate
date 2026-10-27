# Image CHẠY API (không phải image test, không phải image GPU).
#
# Chỉ chứa đường mặc định của sản phẩm: `fw-large-v3-turbo` (faster-whisper, CPU) và
# `opus-mt` (in-process). KHÔNG có SenseVoice (torch), KHÔNG có Ollama — xem
# `requirements-docker.txt` và README mục "Chạy bằng Docker".
FROM python:3.10-slim

# `ffmpeg` là BẮT BUỘC, không phải tiện ích: job `ingest` bóc âm thanh khỏi media bằng
# ffmpeg, thiếu nó thì mọi upload chết ở job đầu tiên.
#
# `libsndfile1` cũng BẮT BUỘC, và lý do hẹp hơn: `soundfile` (phụ thuộc của `vieneu` và của
# chính `DubHandler`) là một ctypes wrapper quanh thư viện C đó — wheel manylinux của nó CÓ
# kèm bản `.so`, nhưng đường TTS chạy trong venv riêng nên không chắc wheel nào được chọn;
# cài gói hệ thống là cách rẻ nhất để cả hai đường đều đọc/ghi được wav.
#
# `python3-venv` cần cho venv TTS bên dưới (`python:3.10-slim` không kèm `ensurepip` đầy đủ
# cho `-m venv` ở mọi biến thể).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libsndfile1 python3-venv \
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

# ── VENV RIÊNG CHO TTS (`vieneu`) ─────────────────────────────────────────────────────────
#
# ⚠️ VÌ SAO VẪN LÀ VENV RIÊNG, KHÔNG PHẢI `pip install vieneu` VÀO VENV CỦA APP:
# `vieneu 3.8.3` khai `huggingface_hub` KHÔNG kèm trần phiên bản, nên pip resolve lên `2.x`;
# còn `transformers 4.46` của app đòi `huggingface_hub <1.0` + `tokenizers <0.21`. Hai bộ đó
# không ở chung một venv được — đo được trên Windows: cài xong thì `import transformers` ném
# ImportError. Đường TTS vì thế ở `/opt/venv-tts`, và `main.py` trỏ tới nó qua
# `PHUDE_TTS_PYTHON`.
#
# ⚠️ VÌ SAO TRƯỚC ĐÂY HỎNG: `TTS_PYTHON` chọn theo `os.name`, nên trong container Linux nó
# trỏ `/app/.venv-tts/bin/python` — một đường KHÔNG TỒN TẠI, vì `backend/.dockerignore` loại
# `.venv-tts/` (nó là venv Windows, 751 MB, không dòng nào chạy được trên Linux). Đo được:
# mọi job `dub` trong container `failed` ở 5% với
# `RuntimeError: TTS không chạy được (/app/.venv-tts/Scripts/python.exe)`.
# Nay venv được DỰNG TRONG IMAGE bằng pip Linux, và `PHUDE_TTS_PYTHON` (ở `ENV` dưới) chỉ vào nó.
#
# ⚠️ VÌ SAO KHÔNG CÒN `--extra-index-url` Ở ĐÂY NỮA — và đây là một lần ĐỔI Ý có đo:
# Bản trước cố ý cài `vieneu` KHÔNG kèm torch (extra `cuda` kéo `torch==2.8.0` + bộ CUDA 12.8
# ~3,5 GB) để image gọn. Nhưng đo được rằng `v3turbo.py:161-169` chọn đường bằng
# `torch.cuda.is_available()`: KHÔNG có torch trong venv này ⇒ rơi vào ONNX/CPU. Hệ quả đo trên
# chính máy này: 6 dòng mất 64 giây, cả file 434 dòng (803,8 giây audio) ước ~12 phút.
#
# Số của tác giả (README §4, RTX 3060): CPU fp32 RTF 0,55–0,62 · GPU batched RTF 0,011–0,02
# ⇒ nhanh 25–50×. Với 434 dòng: ~12 phút → ~20 giây.
#
# ⚠️ VÌ SAO `2.5.1+cu121` CHỨ KHÔNG PHẢI `2.8.0` NHƯ EXTRA `cuda` PIN:
# (a) `2.5.1+cu121` ĐÃ có trong image cho venv app (dòng `torch==2.5.1` ở trên), cùng bộ
#     `nvidia-* 12.1` (2,7 GB) — cài bản 12.8 sẽ kéo THÊM bộ CUDA thứ hai song song.
# (b) Đọc mã `_v3_turbo_engine/`, nó chỉ dùng API có từ torch 2.0: `as_tensor`,
#     `from_numpy`, `full`, `stack`, `no_grad`, `scaled_dot_product_attention`. Không có
#     `torch.compile`, không `GradScaler` — nên `2.5.1` là đủ, và điều đó ĐO ĐƯỢC bằng cách
#     chạy thật, không phải suy từ số phiên bản.
# (c) `--index-url` (không phải `--extra-index-url`) cho đúng lượt cài này: chỉ hỏi host đó.
#
# ⚠️ VẪN LÀ VENV RIÊNG: `vieneu` kéo `huggingface_hub 2.x` + `tokenizers 0.23`, còn
# `transformers 4.46` của app đòi `huggingface_hub <1.0` + `tokenizers <0.21`. ĐO ĐƯỢC:
# bật `include-system-site-packages = true` cho venv này thì `import vieneu` ném
# `ImportError: tokenizers>=0.20,<0.21 is required ... found tokenizers==0.23.3`. Nên hai venv
# phải CÔ LẬP, và torch phải cài RIÊNG vào đây dù bản sao đã có bên venv app.
RUN python -m venv /opt/venv-tts \
 && /opt/venv-tts/bin/pip install --no-cache-dir --timeout 180 --upgrade pip \
 && /opt/venv-tts/bin/pip install --no-cache-dir --timeout 300 \
        --index-url https://download.pytorch.org/whl/cu121 \
        torch==2.5.1+cu121 torchaudio==2.5.1+cu121 \
 && /opt/venv-tts/bin/pip install --no-cache-dir --timeout 180 \
        vieneu==3.8.3 soundfile \
        'transformers>=4.46,<5' safetensors

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
    PHUDE_TTS_PYTHON=/opt/venv-tts/bin/python \
    LD_LIBRARY_PATH=/usr/local/lib/python3.10/site-packages/torch/lib \
    PYTHONUNBUFFERED=1

VOLUME ["/data", "/models"]
EXPOSE 8620

CMD ["python", "run_api.py"]
