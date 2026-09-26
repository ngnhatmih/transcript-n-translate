# phu-de-lab · backend

## Cài đặt

```powershell
pwsh -File scripts/install.ps1
```

`install.ps1` cài torch cu121 **trước** funasr và **dừng lại** nếu
`torch.cuda.is_available()` trả False — chạy CPU mà không biết là kiểu hỏng tệ nhất.

Script cũng đặt `HF_HOME` và `MODELSCOPE_CACHE` ở **mức User** (mặc định
`D:\models\hf` và `D:\models\hf\modelscope`) để model không rơi vào ổ C:.
`HF_HOME` là **biến môi trường**, không phải hằng số trong `app/config.py`:
`huggingface_hub` đọc nó ngay lúc import. Shell đang mở chưa thấy biến mới —
mở shell mới, hoặc đặt lại trong phiên này:

```powershell
$env:HF_HOME = "D:\models\hf"
$env:MODELSCOPE_CACHE = "D:\models\hf\modelscope"
```

`jieba` (phụ thuộc của `funasr`) chỉ có bản sdist, không có wheel Windows, và pip
treo hàng chục phút ở bước tự dựng build-isolation cho nó. Vì vậy script cài
`setuptools` + `wheel`, rồi cài riêng `jieba` với `--no-build-isolation`, rồi mới
cài phần còn lại. Mọi dòng pip đều dùng `--no-cache-dir` — đọc cache là thứ làm
pip chậm một cách bệnh hoạn trên máy này.

## Chạy

```powershell
.\.venv\Scripts\python.exe run_api.py      # http://127.0.0.1:8620
```

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest                        # toàn bộ, không cần model
.\.venv\Scripts\python.exe -m pytest -m live                # CHẠM model thật (OPUS-MT + Ollama)
.\.venv\Scripts\python.exe scripts\smoke_asr.py clip.mp4 zh # model thật, cần GPU
```

Đừng thêm cờ quiet vào lệnh pytest: `pytest.ini` đã có `addopts = -q`, thêm nữa
là thành chế độ im lặng gấp đôi và **mất dòng "N passed"** — khi đó không ai biết
bao nhiêu test đã chạy.

`pytest.ini` cũng đã có `-m "not live"`, nên lần chạy mặc định **bỏ qua** các bài
chạm model thật trong `tests/test_mt_live.py`. Đó là chủ ý: máy chưa tải weight
không được đỏ vì lý do không liên quan tới code. Muốn chạy chúng thì `-m live`, và
mỗi lần chạy như vậy là một lần **ĐO** — đừng thay bằng test giả.

`scripts/smoke_asr.py` **không** thuộc bộ pytest: nó tải model ~1,6 GB và cần
GPU. Nó tự ép UTF-8 cho stdout (console Windows mặc định cp1252, còn script in
tiếng Trung/Việt) và tự đặt cache model trước khi nạp `faster_whisper`.

### Smoke test DỊCH — in ra SỐ, và thoát khác 0 khi không có gì để dịch

```powershell
# 1) tải weight OPUS-MT trước, để lần chạy thật đầu tiên không phải chờ mạng
$env:HF_HOME = "D:\models\hf"
.\.venv\Scripts\python.exe -B scripts\download_mt_models.py

# 2) chạy THẬT cả hai engine trên cùng một tệp
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py clip.wav zh opus-mt vi
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py clip.wav zh qwen2.5-3b vi

# 3) chỉ đo đường DỊCH (không cần âm thanh), và chỉ ra engine bóc băng khác
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py --synthetic opus-mt
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py clip.wav zh qwen2.5-3b vi --asr fw-large-v3-turbo
```

`smoke_mt.py` **không** thuộc bộ pytest: nó nạp weight thật và gọi Ollama thật.
Nó in **số** cho mỗi lần chạy (segment vào/ra, thời gian, `tokens_in`/
`tokens_out`) và mã thoát phản ánh kết quả thật:

| mã | nghĩa |
|----|-------|
| `0` | dịch được, số segment ra **bằng** số vào |
| `1` | chạy được nhưng đường ống SAI: **0 segment**, lệch alignment, hoặc bản dịch rỗng |
| `2` | sai cách dùng, hoặc không thấy tệp |
| `3` | không dựng/nạp được engine (thiếu weight, Ollama tắt, id sai) |

**`0` segment KHÔNG phải thành công.** Một lần chạy "xanh" trên không có gì đúng
là kiểu thất bại mà Giai đoạn 1a đã trả giá (19 task xanh trong khi đường ASR chết
vì chưa từng ai chạy nó), nên nó thoát khác 0 kèm lý do.

`--asr <id>` chọn engine bóc băng (mặc định `fw-small`). Id **không có** trong
`registry.json` bị từ chối kèm danh sách id có thật — `fw-tiny` là ví dụ: nó từng
nằm trong tài liệu nhưng **không tồn tại** trong registry.

`tokens_in`/`tokens_out` chỉ có ở engine chạy qua Ollama (`qwen2.5-3b`,
`qwen2.5-7b`, `hy-mt-1.5-7b`); OPUS-MT chạy trong tiến trình và không có token
count, nên nó in `None` chứ **không** in `0` — "chưa đo được" khác "nhanh bằng không".

`download_mt_models.py` in ra đường dẫn cache THẬT và dung lượng THẬT. Nó đặt
`HF_HOME` **trước** khi import `transformers`, vì `huggingface_hub` đọc biến đó
ngay lúc import: đặt sau thì model rơi vào cache mặc định trên ổ C: dù dòng log
in ra đường dẫn đúng.

## Chưa kiểm chứng

* **Hình dạng thật của `timestamp` từ SenseVoice/FunASR.** Ba hình dạng
  (`start`+`end` số · cặp phẳng `[b, k]` · danh sách cặp `[[b, k], ...]`) đã được
  ghim bằng test với `model_factory` giả, nhưng **chưa lần nào chạy model thật**:
  `funasr` không có trong venv và không được tải model ở đây. Nếu hình dạng thật
  khác cả ba, `SenseVoiceEngine` sẽ **nổ** kèm danh sách khoá hiện có — đó là tín
  hiệu mong muốn, không phải lỗi cần vá im lặng.
* **Nhánh tải `yt-dlp` thật** (khi `runner is None`): đã được chạy qua một
  `yt_dlp` giả, chưa lần nào tải thật.
* **RTF + thời gian nạp model**: hai số này chỉ có sau khi chạy
  `smoke_asr.py` với GPU; chúng là đầu vào cho bảng benchmark ở GĐ1b.

## Ghi chú kiến trúc

`app/domain/` là logic thuần — `tests/test_layer_boundary.py` **sẽ đỏ** nếu ai đó
import `torch`, `sqlite3`, `fastapi` hay `httpx` vào đó. Đó là chủ ý, đừng sửa test.

`app/worker.py` gom lô theo **cặp (loại job, engine)**, không phải theo
`asr`/`mt`. Lý do: người dùng đổi được model cho từng job, nên gom theo loại job
là vô dụng.

Audio **im lặng** làm job `asr` thành `FAILED`, **không** sinh transcript rỗng
(xem `tests/test_silent_audio.py`). Một transcript rỗng trông y hệt một lần bóc
băng thành công, nên nó giấu mất lỗi thật.
