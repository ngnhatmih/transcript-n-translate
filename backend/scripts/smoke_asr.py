"""Smoke test với model THẬT. Chạy sau khi cài xong:

    .venv\\Scripts\\python.exe scripts\\smoke_asr.py <duong-dan-audio> [zh|en] [engine-id]

`engine-id` mặc định là `fw-large-v3-turbo` (engine ASR mặc định của GĐ1a). Lần
chạy THẬT đầu tiên nên truyền một engine nhỏ — `fw-small` — để không phải tải
1,6 GB trước khi biết đường ống có thông hay không. Id có thật trong
`registry.json` là `fw-large-v3-turbo`, `fw-medium`, `fw-small` và
`sensevoice-small`; `tiny`/`fw-tiny` KHÔNG tồn tại, nên truyền vào là `by_id`
ném `KeyError` không kèm danh sách id.

Không thuộc bộ pytest vì nó tải model vài GB và cần GPU.

Hai ruling được cài ở đây:

* **R17** — console Windows mặc định là cp1252, mà script này in tiếng Trung và
  tiếng Việt. Thiếu `force_utf8_stdout()` thì lần chạy THẬT đầu tiên ném
  `UnicodeEncodeError` ngay dòng đầu có ký tự ngoài cp1252 (`→`, `⚠`). pytest
  không thấy lỗi này vì nó tự bắt UTF-8 — chỉ console mới lộ.
* **R60** — chỗ dựng engine đi qua đúng hàm dispatch của production
  (`app.adapters.asr.factory.engine_for`, cũng là thứ `app.main:_engine_factory`
  gọi). Thiếu `download_root` thì model ~1,6 GB rơi vào cache mặc định trên ổ C:.
  Và vì `huggingface_hub` đọc `HF_HOME` **ngay lúc import**, biến môi trường phải
  được đặt TRƯỚC khi chạm `faster_whisper` — `download_root=` một mình chưa đủ.
* **I-2** — bản trước tự dựng `FasterWhisperEngine` cho MỌI engine id, nên
  `sensevoice-small` bị chạy bằng sai adapter và script báo hỏng sai. Dispatch
  dùng chung với production là cách duy nhất để hai bên không trôi khỏi nhau.

R62 đã được xác minh với FunASR 1.2.6 trên SenseVoiceSmall: adapter yêu cầu
`output_timestamp=True`, nếu không kết quả chỉ có `key`/`text` và phải báo lỗi
thay vì tạo phụ đề sai thời gian.
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
    """Dựng engine ĐÚNG cách `app.main:_engine_factory` dựng nó (R60, I-2).

    Đi qua CÙNG một hàm dispatch (`app.adapters.asr.factory.engine_for`) thay vì
    tự dựng `FasterWhisperEngine`: bản cũ luôn trả faster-whisper cho MỌI id, nên
    `smoke_asr.py clip.mp4 zh sensevoice-small` báo hỏng vì dựng sai adapter —
    đúng thứ công cụ này tồn tại để đo.
    """
    cache_root = prepare_model_cache_env()  # TRƯỚC khi chạm faster_whisper
    from app.adapters.asr.factory import engine_for

    return engine_for(spec, download_root=cache_root)


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

    # R62/R68: 0 đoạn là THẤT BẠI, không phải "chạy được". Bản trước in
    # `OK` rồi thoát 0 với `0 đoạn | RTF = nan`, nên nó báo xanh cho đúng thất
    # bại mà nó tồn tại để bắt: nghiệm thu bước 5 đòi "ít nhất 1 đoạn có
    # start/end". Không có đoạn nghĩa là VAD bỏ hết hoặc giải mã hỏng — im lặng
    # ở đây nguy hiểm hơn hẳn một lần hỏng ồn ào.
    if not segments:
        print("THẤT BẠI: 0 đoạn — đường ống không sinh transcript nào. "
              "KHÔNG tính là smoke test đạt (xem R62/R68).")
        print(f"      engine={spec.id} model={spec.model_ref} "
              f"audio={audio.name} lang={lang} cache={cache_root}")
        engine.release()
        return 1

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
