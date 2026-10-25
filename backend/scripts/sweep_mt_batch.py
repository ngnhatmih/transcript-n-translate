"""Quét KÍCH THƯỚC LÔ và đo thời gian qua ĐÚNG đường dịch đã ship.

Đây KHÔNG phải một driver thứ hai: mọi lần dịch đều đi qua
`smoke_term_placeholder.run` — cùng `TranslateHandler`, cùng seam che thuật ngữ,
cùng repo trong bộ nhớ. Tệp này chỉ làm ba việc mà smoke không làm: lặp nhiều lần,
đổi `batch_items`, và gom số đo thành bảng.

Vì sao đo bằng `batch_items` chứ không sửa `DEFAULT_MAX_ITEMS`
    Trần số mục của một lời gọi engine là THAM SỐ của handler
    (`domain/mt.py:DEFAULT_MAX_ITEMS` chỉ là giá trị mặc định). Sửa hằng số đó để
    đo rồi sửa lại là đổi mặc định của SẢN PHẨM hai lần cho một phép đo, và lần
    quên sửa lại thì mặc định đã đổi mà không có số nào bảo vệ. Truyền tham số thì
    phép đo đi qua đúng nhánh code sản phẩm chạy.

Vì sao có một lượt KHỞI ĐỘNG riêng (không tính vào bảng)
    Lượt gọi đầu tiên của phiên phải NẠP model từ đĩa vào VRAM; các lượt sau chỉ
    trả chi phí suy luận. Số nạp đó rơi vào lô ĐẦU TIÊN của bảng và làm nó trông
    chậm hơn các lô khác — một khác biệt do THỨ TỰ chứ không do kích thước lô. Nên
    lượt khởi động được chạy trước, ghi riêng ở `warmup_seconds`, và bị loại khỏi
    mọi con số trung vị.

Vì sao đếm chữ Hán trong bản dịch
    Lúc viết phép đo này, giả thuyết là "lô lệch alignment bị hạ cấp xuống dịch
    từng câu nên một phần câu ra lẫn tiếng Trung". SỐ ĐO BÁC BỎ giả thuyết đó: các
    lượt chạy NHIỀU chữ Hán nhất lại là những lượt KHÔNG hạ cấp lần nào (lô 30, 4
    lời gọi, 89/115 đoạn là chữ nguồn). Chữ Hán ở đây là model CHÉP NGUYÊN chữ
    nguồn chứ không phải dịch dở dang. Vẫn giữ phép đếm này vì nó là con số ĐẾM
    ĐƯỢC, kiểm lại được trên artifact, và nó bắt đúng kiểu hỏng nặng nhất mà mọi
    cờ khác đều bỏ sót (`check_alignment` vẫn khớp số mục).

Vì sao bắt stdout của từng lượt
    `TranslateHandler` báo mọi lần lệch alignment và mọi lần hạ cấp qua `report`
    (smoke in ra stdout). Đó là dấu vết duy nhất cho biết lô lớn có bị hạ cấp
    không, mà nguyên nhân phương sai thời gian chính là các lần hạ cấp đó.

SỐ ĐO (RTX 3070 8 GB, Ollama 0.34.4, `hy-mt1.5-7b:q4_K_M`, clip 115 đoạn
`20261019-name-patch-smoke/large-v3-beam5-prevfalse.json`, 5 thuật ngữ; mỗi lượt
chạy ĐÃ nạp model trước đó nên các số dưới đây KHÔNG gồm thời gian nạp):

    lô | lần | trung vị | min   | max   | lời gọi | hạ cấp | chữ Hán | QA
     8 |   3 | 63,54 s  | 62,15 | 73,24 | 33–42   |     7  | 0–54    | 113–116
    15 |   3 | 44,11 s  | 43,96 | 44,36 | 8       |     0  | 181     | 123–124
    30 |   3 | 32,89 s  | 32,84 | 57,24 | 4–35    |     1  | 389–629 | 117

Ba kết luận mà bảng đó trả lời (và chúng ngược với kỳ vọng "lô nhỏ là an toàn"):

* Lô nhỏ GIẢM mạnh nhưng KHÔNG XOÁ chữ Hán còn sót: lô 8 vẫn để 8/115 đoạn là chữ
  nguồn (2 trong 3 lượt), lô 15 là 29/115, lô 30 là 59–89/115.
* Lô nhỏ KHÔNG xoá phương sai thời gian. Nguồn phương sai là hạ cấp alignment:
  lô 30 có lượt chỉ 4 lời gọi (32,84 s) và lượt 35 lời gọi (57,24 s). Lô 15 mới là
  chỗ phương sai biến mất (0,4 s), và đó là do KHÔNG lô nào lệch, không phải do
  "nhỏ".
* `token_lost` bằng 0 ở MỌI lô trong bảng, nên lô nhỏ không cải thiện được nó (một
  lượt chạy nguội lô 30 ngoài bảng có 1 lần `token_lost`: model thay token bằng
  "một cách đổi mới" thay vì bỏ cả câu).

Điều quan trọng nhất mà cột "chữ Hán" che mất: chữ Hán còn sót = số đoạn model CHÉP
NGUYÊN chữ nguồn (`echo`), và QA gắn đúng bấy nhiêu cờ `lang:` — lô 30 có 89 cờ
`lang:` trong 117 issue, lô 8 có 8 trong 114. Tức chữ Hán không phải "dịch hỏng một
nửa" mà là "không dịch", và nó ĐI QUA được `check_alignment` (số mục vẫn khớp) nên
không có lần hạ cấp nào báo hiệu.

Ví dụ:
    python -B scripts\\sweep_mt_batch.py --batches 8 15 30 --runs 3 \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\...\\batch-sweep
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib
import re
import statistics
import sys
import time

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import smoke_term_placeholder as smoke  # noqa: E402 - sau sys.path

#: Chữ Hán (CJK Unified Ideographs). Chỉ đếm khối cơ bản: đủ để bắt "câu Việt lẫn
#: chữ Trung", và một lớp ký tự mở rộng thêm vào sẽ làm con số khó tái lập.
HAN = re.compile(r"[\u4e00-\u9fff]")
#: Hai câu của `report` đánh dấu đúng nguyên nhân phương sai thời gian.
_DOWNGRADE = "hạ cấp"
_MISALIGN = "lệch alignment"
_FAILED_SEGMENT = "thất bại"


def measure(result: dict, log: str) -> dict:
    """Số đo của MỘT lượt chạy, suy từ artifact mà `smoke.run` đã trả."""
    vi = [s["vi"] for s in result["sentences"]]
    return {
        "engine": result["engine"],
        "batch_items": result["batch_items"],
        "seconds": result["seconds"],
        "llm_calls": result["llm_calls"],
        "flags": dict(result["flags"]),
        "token_lost": result["flags"].get(smoke.TOKEN_LOST, 0),
        "token_duplicated": result["flags"].get(smoke.TOKEN_DUPLICATED, 0),
        "token_unknown": result["flags"].get(smoke.TOKEN_UNKNOWN, 0),
        "token_collision_in_source": result["flags"].get(smoke.TOKEN_COLLISION, 0),
        "qa_issues": len(result["qa_issues"]),
        "han_chars": sum(len(HAN.findall(t)) for t in vi),
        "segments_with_han": sum(1 for t in vi if HAN.search(t)),
        "downgrades": log.count(_DOWNGRADE),
        "misaligned_batches": log.count(_MISALIGN),
        "failed_segments": log.count(_FAILED_SEGMENT),
        "translation_status": result["translation_status"],
        "segments": result["segments"],
    }


def one_run(transcript: pathlib.Path, glossary: pathlib.Path,
            out_dir: pathlib.Path, batch_items: int, label: str,
            engine_id: str) -> dict:
    buffer = io.StringIO()
    started = time.time()
    with contextlib.redirect_stdout(buffer):
        result = smoke.run(transcript, glossary, out_dir, None, label,
                           engine_id=engine_id, batch_items=batch_items)
    ended = time.time()
    row = measure(result, buffer.getvalue())
    #: Mốc epoch để ghép với log `nvidia-smi` của phép đo VRAM: hai tệp log độc
    #: lập không có mốc chung thì không cắt ra được cửa sổ của một lượt chạy.
    row["started_at"] = round(started, 3)
    row["ended_at"] = round(ended, 3)
    row["label"] = label
    return row


def summarise(rows: list[dict], batch_items: int) -> dict:
    seconds = [r["seconds"] for r in rows]
    return {
        "batch_items": batch_items,
        "runs": len(rows),
        "median_seconds": round(statistics.median(seconds), 2),
        "min_seconds": min(seconds),
        "max_seconds": max(seconds),
        "spread_seconds": round(max(seconds) - min(seconds), 2),
        "llm_calls": sorted({r["llm_calls"] for r in rows}),
        "token_lost": sum(r["token_lost"] for r in rows),
        "token_duplicated": sum(r["token_duplicated"] for r in rows),
        "token_unknown": sum(r["token_unknown"] for r in rows),
        "token_collision_in_source": sum(r["token_collision_in_source"] for r in rows),
        "qa_issues": sorted({r["qa_issues"] for r in rows}),
        "han_chars": sorted({r["han_chars"] for r in rows}),
        "segments_with_han": sorted({r["segments_with_han"] for r in rows}),
        "downgrades": sum(r["downgrades"] for r in rows),
        "misaligned_batches": sum(r["misaligned_batches"] for r in rows),
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="sweep_mt_batch.py")
    parser.add_argument("--transcript", type=pathlib.Path, required=True)
    parser.add_argument("--glossary", type=pathlib.Path, required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--batches", type=int, nargs="+", default=[8, 15, 30])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--engine", default=smoke.ENGINE_ID)
    parser.add_argument("--no-warmup", action="store_true",
                        help="bỏ lượt khởi động (chỉ dùng khi model ĐÃ nạp sẵn)")
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    warmup: dict | None = None
    if not args.no_warmup:
        print("khởi động (nạp model, KHÔNG tính vào bảng)…", flush=True)
        warmup = one_run(args.transcript, args.glossary, args.out_dir, args.batches[0],
                         "warmup", args.engine)
        print(f"  khởi động xong: {warmup['seconds']} s", flush=True)

    for batch_items in args.batches:
        for index in range(args.runs):
            label = f"b{batch_items}-r{index + 1}"
            row = one_run(args.transcript, args.glossary, args.out_dir, batch_items,
                          label, args.engine)
            row["run"] = index + 1
            rows.append(row)
            print(f"[{label}] {row['seconds']} s · {row['llm_calls']} lời gọi · "
                  f"hạ cấp {row['downgrades']} · Hán {row['han_chars']} · "
                  f"token_lost {row['token_lost']} · QA {row['qa_issues']}",
                  flush=True)

    summary = [summarise([r for r in rows if r["batch_items"] == b], b)
               for b in args.batches]
    report = {
        "experiment": "mt-batch-sweep",
        "engine": args.engine,
        "transcript": str(args.transcript),
        "glossary": str(args.glossary),
        "warmup_seconds": warmup["seconds"] if warmup else None,        "runs": rows,
        "summary": summary,
    }
    (args.out_dir / "sweep.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("")
    print("lô | lần | trung vị s | min | max | lời gọi | hạ cấp | Hán | token_lost")
    for row in summary:
        print(f"{row['batch_items']:>3} | {row['runs']} | {row['median_seconds']:>10} "
              f"| {row['min_seconds']} | {row['max_seconds']} | "
              f"{row['llm_calls']} | {row['downgrades']} | {row['han_chars']} | "
              f"{row['token_lost']}")
    print("")
    print(f"đã ghi {args.out_dir / 'sweep.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
