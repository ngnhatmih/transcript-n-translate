"""Smoke test với model THẬT. Chạy sau khi cài xong:

    .venv\\Scripts\\python.exe scripts\\smoke_asr.py <duong-dan-audio> [zh|en] [engine-id]

`engine-id` mặc định là `fw-large-v3-turbo` (engine ASR mặc định của GĐ1a). Lần
chạy THẬT đầu tiên nên truyền một engine nhỏ — `tiny` — để không phải tải 1,6 GB
trước khi biết đường ống có thông hay không.

Không thuộc bộ pytest vì nó tải model vài GB và cần GPU.

Hai ruling được cài ở đây:

* **R17** — console Windows mặc định là cp1252, mà script này in tiếng Trung và
  tiếng Việt. Thiếu `force_utf8_stdout()` thì lần chạy THẬT đầu tiên ném
  `UnicodeEncodeError` ngay dòng đầu có ký tự ngoài cp1252 (`→`, `⚠`). pytest
  không thấy lỗi này vì nó tự bắt UTF-8 — chỉ console mới lộ.
* **R60** — đây là chỗ gọi `FasterWhisperEngine` **thứ hai** (chỗ kia là
  `app.main:_engine_factory`). Thiếu `download_root` thì model ~1,6 GB rơi vào
  cache mặc định trên ổ C:. Và vì `huggingface_hub` đọc `HF_HOME` **ngay lúc
  import**, biến môi trường phải được đặt TRƯỚC khi chạm `faster_whisper` —
  `download_root=` một mình chưa đủ.

CHƯA kiểm chứng (R62): hình dạng THẬT của khoá `timestamp` mà FunASR trả về chỉ
xác nhận được bằng một lần chạy `SenseVoiceEngine` thật (`funasr` không có trong
venv này). Đừng suy ra từ đây — đọc `docs`/report của Task 20.
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def force_utf8_stdout(stream=None) -> bool:
    """Ép UTF-8 cho stdout và trả về True nếu làm được (R17).

    `errors="replace"` là cố ý: mục đích là KHÔNG BAO GIỜ chết vì một ký tự,
    kể cả khi terminal không hiển thị được nó. Trả `False` khi stdout đã bị
    chuyển hướng sang một đối tượng không `reconfigure` được — khi đó không có
    gì để sửa và cũng không được ném lỗi.
    """
    stream = sys.stdout if stream is None else stream
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return False
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        return False
    return True


def prepare_model_cache_env() -> str:
    """Trỏ cache model về ổ D: TRƯỚC khi thư viện nào đọc biến môi trường (R60).

    `huggingface_hub` đọc `HF_HOME` NGAY LÚC IMPORT, và nó được nạp gián tiếp
    khi `faster_whisper` được import trong `FasterWhisperEngine._load()`. Vì vậy
    hàm này phải chạy TRƯỚC `build_engine()`.

    Cùng hợp đồng với `app.main:_prepare_local_model_caches`; hai chỗ gọi đó
    được ghim khỏi trôi khỏi nhau bằng `tests/test_model_cache_env.py`.
    """
    from app.config import HF_HOME

    os.environ.setdefault("HF_HOME", HF_HOME)
    os.environ.setdefault("MODELSCOPE_CACHE",
                          str(pathlib.Path(HF_HOME) / "modelscope"))
    return os.environ["HF_HOME"]


def build_engine(spec):
    """Dựng engine ĐÚNG cách `app.main:_engine_factory` dựng nó (R60)."""
    cache_root = prepare_model_cache_env()  # TRƯỚC khi chạm faster_whisper
    from app.adapters.asr.faster_whisper import FasterWhisperEngine

    return FasterWhisperEngine(spec, download_root=cache_root)


def main() -> int:
    force_utf8_stdout()

    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    audio = pathlib.Path(sys.argv[1])
    lang = sys.argv[2] if len(sys.argv) > 2 else "zh"
    # Cho phép chọn engine: lần chạy THẬT đầu tiên phải chạy được với model NHỎ
    # NHẤT trước, nếu không thì "kiểm tra đường ống" bị trói vào một lần tải 1,6 GB.
    engine_id = sys.argv[3] if len(sys.argv) > 3 else "fw-large-v3-turbo"
    if not audio.exists():
        print(f"không thấy tệp: {audio}")
        return 2

    from app.adapters.registry_file import load_registry
    from app.registry import by_id

    spec = by_id(load_registry(), engine_id)
    cache_root = prepare_model_cache_env()
    print(f"[1/3] nạp {spec.model_ref} ...")
    print(f"      cache model: {cache_root}  <-- ghi số này vào eval/report.md nếu nó KHÁC ổ D:")
    t0 = time.perf_counter()
    engine = build_engine(spec)
    engine._load()  # noqa: SLF001 - smoke test đo thời gian nạp
    print(f"      nạp xong sau {time.perf_counter() - t0:.1f}s  <-- ghi số này vào eval/report.md")

    print(f"[2/3] bóc băng {audio.name} (lang={lang}) ...")
    t1 = time.perf_counter()
    segments = engine.transcribe(str(audio), lang)
    elapsed = time.perf_counter() - t1

    duration = segments[-1].end if segments else 0.0
    rtf = elapsed / duration if duration else float("nan")
    print(f"[3/3] {len(segments)} đoạn trong {elapsed:.1f}s "
          f"| RTF = {rtf:.3f}  <-- ghi số này vào eval/report.md")

    for seg in segments[:5]:
        flag = " ⚠NGHI NGỜ" if seg.suspect else ""
        words = "có word-ts" if seg.words else "không word-ts"
        print(f"  {seg.start:7.2f} → {seg.end:7.2f}  {seg.text}{flag}  [{words}]")
    if len(segments) > 5:
        print(f"  ... và {len(segments) - 5} đoạn nữa")

    engine.release()
    print("OK — có timestamp cấp đoạn, engine chạy được.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
