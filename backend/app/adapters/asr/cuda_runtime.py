"""R72 · Chuẩn bị DLL runtime CUDA TRƯỚC khi CTranslate2 chạm GPU.

Lỗi thật, đo được trên đúng máy này bằng `scripts/smoke_asr.py` với model `tiny`
(`.venv` đã cài `torch==2.5.1+cu121`, GPU là RTX 3070, driver 566.36):

    [1/3] nạp tiny ...
          nạp xong sau 5.1s
    [2/3] bóc băng synth-zh.wav (lang=zh) ...
      File "...\\faster_whisper\\transcribe.py", line 1358, in encode
        return self.model.encode(features, to_cpu=to_cpu)
    RuntimeError: Library cublas64_12.dll is not found or cannot be loaded

`ctranslate2` KHÔNG kèm `cublas64_12.dll` (nó chỉ kèm `cudnn64_9.dll`). Trên
Windows, bản `cublas64_12.dll` duy nhất có trong venv này nằm ở
`torch\\lib\\`, và thư mục đó chỉ được thêm vào đường tìm DLL **khi torch được
nạp**. Vì vậy CTranslate2 tạo được model nhưng nổ ngay ở lần `encode()` đầu
tiên — tức là ở giữa một job, sau khi đã tải xong model.

Phép đo A/B (ba tiến trình mới, cùng model, cùng audio — xem report Task 20):

    from faster_whisper import WhisperModel          -> RuntimeError cublas64_12.dll
    import torch; from faster_whisper import ...     -> OK
    import torch; os.add_dll_directory(torch/lib);   -> OK

Nên `ensure_cuda_runtime()` phải chạy TRƯỚC `from faster_whisper import ...` ở
mọi chỗ nạp model. `import torch` KHÔNG được phép làm sập việc nạp: đây chỉ là
tối ưu đường tìm DLL, còn nếu torch hỏng thì `WhisperModel(...)` sẽ tự báo lỗi
thật của nó — thông báo đó hữu ích hơn nhiều so với một `ImportError` từ đây.
"""
from __future__ import annotations

import os

_TORCH_LIB_ON_PATH = False


def torch_lib_dir() -> str | None:
    """Đường dẫn `torch/lib`, hoặc None nếu torch không có/không nạp được."""
    try:
        import torch  # noqa: PLC0415 - cố ý nạp muộn, xem docstring
    except Exception:  # noqa: BLE001 - torch hỏng KHÔNG được làm sập việc nạp model
        return None
    return os.path.join(os.path.dirname(torch.__file__), "lib")


def ensure_cuda_runtime() -> str | None:
    """Nạp torch (và do đó đường tìm DLL của nó) trước khi CTranslate2 chạm GPU.

    Idempotent. Trả về đường dẫn `torch/lib` khi tìm được, `None` khi không.
    """
    global _TORCH_LIB_ON_PATH
    lib = torch_lib_dir()
    if lib is None or not os.path.isdir(lib):
        return None
    if not _TORCH_LIB_ON_PATH:
        # `add_dll_directory` một mình KHÔNG đủ trên máy này (đã đo: vẫn
        # RuntimeError); thứ thật sự có tác dụng là chính việc torch được nạp.
        # Giữ thêm hai dòng này vì chúng rẻ và giúp cả trường hợp DLL phụ thuộc.
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            try:
                add_dll_directory(lib)
            except OSError:
                pass
        os.environ["PATH"] = lib + os.pathsep + os.environ.get("PATH", "")
        _TORCH_LIB_ON_PATH = True
    return lib
