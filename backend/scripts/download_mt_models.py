"""Tải trước model OPUS-MT để lần chạy THẬT đầu tiên không phải chờ mạng.

`HF_HOME` phải trỏ ổ còn chỗ: ổ C: của máy này chỉ còn ~26 GB, còn D: ~59 GB.
Đường mặc định `D:\\models\\hf` của dự án CHƯA TỪNG được đi qua ở Giai đoạn 1a.

Vì sao phải là script riêng thay vì để `OpusMtEngine` tự tải: lần gọi `translate()`
đầu tiên trộn hai thứ rất khác nhau — tải ~300 MB qua mạng và suy luận — nên một
lần hỏng vì mạng trông y hệt một lần hỏng vì model. Tách ra thì mỗi thứ hỏng ở
đúng chỗ của nó, và smoke test sau đó đo được thời gian SUY LUẬN thật.

Thứ tự quan trọng: `huggingface_hub` đọc `HF_HOME` NGAY LÚC IMPORT (R60), còn
`transformers` kéo `huggingface_hub` vào. Nên biến môi trường phải được đặt TRƯỚC
khi `transformers` được import — nếu không, model rơi vào cache mặc định trên ổ C:
dù ta có in ra đường dẫn đúng.

Dùng:
    $env:HF_HOME = "D:\\models\\hf"
    .\\.venv\\Scripts\\python.exe -B scripts\\download_mt_models.py
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def resolve_hf_home() -> str:
    """Chốt `HF_HOME` TRƯỚC khi bất cứ thư viện nào đọc nó (R60).

    Trả về đường dẫn THẬT SỰ sẽ dùng, sau khi đã ghim vào `os.environ`. Gọi hàm
    này cũng là cách duy nhất để script in ra đúng chỗ model sẽ nằm: đọc
    `app.config.HF_HOME` một mình là hằng số Python, không phải thứ
    `huggingface_hub` nhìn thấy.
    """
    from app.config import HF_HOME

    os.environ.setdefault("HF_HOME", HF_HOME)
    return os.environ["HF_HOME"]


def main() -> int:
    root = resolve_hf_home()
    print(f"HF_HOME = {root!r}")
    if not os.environ.get("HF_HOME"):
        print("CẢNH BÁO: chưa đặt HF_HOME — model sẽ vào cache mặc định trên ổ C:")

    # Import SAU khi `HF_HOME` đã được ghim. `transformers` nặng nên import trong
    # hàm, cùng lý do với `OpusMtEngine._default_factory` (import ở cấp module sẽ
    # làm đỏ mọi thứ trên máy chưa cài `transformers`).
    from app.adapters.mt.opus_mt import DEFAULT_MODEL
    from transformers import MarianMTModel, MarianTokenizer

    print(f"đang tải {DEFAULT_MODEL} ...")
    MarianTokenizer.from_pretrained(DEFAULT_MODEL)
    MarianMTModel.from_pretrained(DEFAULT_MODEL)

    # Nói ra ĐƯỜNG DẪN THẬT và DUNG LƯỢNG THẬT: "tải xong" mà không nói nặng bao
    # nhiêu thì không phân biệt được một lần tải đủ với một lần rơi vào cache cũ.
    root_path = pathlib.Path(root)
    size = sum(p.stat().st_size for p in root_path.rglob("*") if p.is_file())
    print(f"OK: đã tải {DEFAULT_MODEL} — cache {root!r} hiện {size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
