"""Đo `DEFAULT_MAX_CHARS` (nợ đã ghi: "chưa từng bị ép") — trần KÝ TỰ có phải
trần THẬT của một lời gọi engine?

Câu hỏi của phép đo
    `mt.DEFAULT_MAX_CHARS = 1200` chưa từng bị chạm: lô lớn nhất từng đo chỉ **94
    ký tự**, nên giữ 1200 nghĩa là *"không có cơ sở để đổi"*, KHÔNG phải *"đã xác
    nhận 1200 đúng"*. Và `batch_segments` có HAI ngân sách: `max_chars` (1200) và
    `max_items` (`TranslateHandler.DEFAULT_MAX_ITEMS = 30`).

    Vậy câu hỏi hẹp hơn, và đo được: **một lời gọi 3600 ký tự / 24 mục có giữ được
    hợp đồng không?** Nếu CÓ, thì 1200 không phải ngưỡng hỏng — nó chỉ là mức bảo
    thủ, và trần thật là **số mục**, không phải số ký tự.

Cách đo
    Transcript TỔNG HỢP (không lấy từ clip thật, để không rò đáp án vào phép đo),
    mỗi đoạn một câu tiếng Trung hợp lệ, độ dài đặt trước. Chạy `TranslateHandler`
    THẬT với engine THẬT, `engine_capabilities={}` (KHÔNG echo_guard, KHÔNG
    term_placeholder) — tức đo đúng hợp đồng thô của engine.

    Mỗi lượt một dòng trong artifact: số mục, số ký tự, giây, có lỗi alignment
    không. Cộng thêm số đoạn bị chép nguyên văn ở đầu ra cuối.

Dùng
    .\\.venv\\Scripts\\python.exe -B scripts\\measure_batch_chars.py \\
        --engine qwen2.5-3b \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\20261025-batch-chars

    Chạy hết bốn cấu hình trong MỘT tiến trình (engine nạp một lần); `--only` để
    chạy lẻ một cấu hình khi cần đo lại.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import smoke_term_placeholder as smoke  # noqa: E402 - sau sys.path
from app.adapters.mt.prompts import system_prompt, user_prompt  # noqa: E402
from app.domain.models import Segment  # noqa: E402
from app.domain.mt import MtOpts, batch_segments  # noqa: E402
from app.domain.mt_qa import echoes_source  # noqa: E402
from app.pipeline.translate import TranslateHandler  # noqa: E402

#: Câu tiếng Trung HỢP LỆ, KHÁC NHAU — không lấy câu nào từ clip thật, và cố ý
#: không lặp một câu: lần đo đầu lặp đúng một câu 5 lần/đoạn và `qwen2.5-3b` rơi
#: vào "prediction aborted, token repeat limit reached" ngay lô đầu — đo được
#: nhưng đo SAI thứ (repeat, không phải trần ký tự). Một câu lặp là một cái bẫy
#: của CHÍNH phép đo, không phải thuộc tính của dữ liệu thật.
CAU = [
    "今天我们来讨论一个很重要的问题，关于这个城市的历史和文化。",
    "街上的人比平时多了不少，摊位上摆满了各种各样的东西。",
    "他从小就喜欢画画，后来考上了美术学院，一直住在这里。",
    "这家店的老板已经做了三十多年，手艺是父亲传下来的。",
    "天色渐渐暗下来，远处的灯一盏一盏亮起来，风也凉了。",
    "我们沿着河走了一段路，看到几座很老的桥，石头都磨圆了。",
    "她说自己不太会说话，但是做事情很认真，从不马虎。",
    "每年到了这个时候，外面回来的人特别多，车站里全是行李。",
    "这栋楼原来是仓库，后来改成了书店，保留了原来的砖墙。",
    "下午的课结束以后，学生们三三两两走出校门，边走边聊。",
]

#: Bốn cấu hình. Hai cấu hình đầu có đoạn DÀI (150 ký tự) để ngân sách KÝ TỰ là
#: cái chặn trước; cấu hình ba đặt ngân sách ký tự CAO HƠN tổng độ dài, để trần
#: SỐ MỤC (30) là cái chặn; cấu hình bốn dùng đoạn NGẮN (25 ký tự) đúng cỡ phụ đề
#: thật, để thấy trần số mục mới là thứ chặn trong thực tế.
CONFIGS = [
    {"key": "dai-150x24-cs1200", "seg_chars": 150, "n": 24, "batch_chars": 1200},
    {"key": "dai-150x24-cs3000", "seg_chars": 150, "n": 24, "batch_chars": 3000},
    {"key": "dai-150x24-cs8000", "seg_chars": 150, "n": 24, "batch_chars": 8000},
    {"key": "ngan-25x60-cs1200", "seg_chars": 25, "n": 60, "batch_chars": 1200},
]


def _text_of(length: int, seed: int) -> str:
    """Chuỗi tiếng Trung đúng `length` ký tự, KHÁC nhau giữa các mục.

    Ghép từ pool `CAU` theo một phép xoay phụ thuộc `seed` (không lặp lại cùng
    một câu liền nhau), rồi cắt đúng độ dài — cắt giữa câu là bình thường với phụ
    đề, và nó cũng là thứ dữ liệu thật có.
    """
    head = f"{seed}、" if seed < 100 else ""
    body = ""
    k = 0
    while len(head + body) < length:
        body += CAU[(seed + k) % len(CAU)]
        k += 1
    return (head + body)[:length]


def _segments(seg_chars: int, n: int) -> list[Segment]:
    return [Segment(i=i, start=float(i), end=float(i) + 1.0,
                    text=_text_of(seg_chars, i))
            for i in range(1, n + 1)]


class _Recorder:
    """Ghi mỗi lời gọi: số mục, số ký tự, giây, loại lỗi."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[dict] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def translate(self, batch, glossary, opts):
        record = {"n": len(self.calls) + 1, "items": len(batch),
                  "chars": sum(len(s.text) for s in batch), "error": None}
        self.calls.append(record)
        started = time.perf_counter()
        try:
            out = self._inner.translate(batch, glossary, opts)
        except Exception as exc:                   # noqa: BLE001 - phân loại rồi ném
            record["error"] = type(exc).__name__
            record["message"] = str(exc)[:300]
            raise
        finally:
            record["seconds"] = round(time.perf_counter() - started, 2)
        stats = getattr(self._inner, "last_stats", None)
        if stats is not None:
            record["tokens_in"], record["tokens_out"] = stats.tokens_in, stats.tokens_out
        return out


def run_one(engine_id: str, cfg: dict) -> dict:
    spec, engine = smoke._engine_and_capabilities(engine_id)
    recorder = _Recorder(engine)
    segments = _segments(cfg["seg_chars"], cfg["n"])
    repos = smoke._InMemoryRepos(segments, [], engine=spec.id,
                                 prompt_version=smoke._prompt_version(spec))
    handler = TranslateHandler(
        repos, {spec.id: recorder},
        # KHÔNG capability: đo hợp đồng THÔ. `echo_guard` sẽ che mất đúng thứ
        # cần thấy (một lời gọi bị chép nguyên văn).
        engine_capabilities={spec.id: {}},
        batch_chars=cfg["batch_chars"],
        # `batch_items=None` ⇒ trần số mục theo `DEFAULT_MAX_ITEMS` (30). Đây là
        # biến số THỨ HAI, và chính nó là thứ cấu hình ba/bốn muốn để lộ.
        batch_items=None,
    )
    # Số lô THEO LÝ THUYẾT, tính trước khi chạy: nếu lời gọi thật nhiều hơn, đó
    # là hạ cấp do lỗi; nếu ít hơn, code chia lô khác mô tả.
    planned = [{"items": len(b), "chars": sum(len(s.text) for s in b)}
               for b in batch_segments(segments, max_chars=cfg["batch_chars"],
                                       max_items=30)]
    job = smoke._Job()
    started = time.perf_counter()
    error = None
    try:
        handler.translate(translation_id=1, transcript_id=1, engine_id=spec.id,
                          source_lang="zh", target_lang="vi", job=job,
                          report=lambda _p, line: print(line, flush=True))
    except Exception as exc:                       # noqa: BLE001 - artifact phải có
        error = {"type": type(exc).__name__, "message": str(exc)[:500]}
    seconds = round(time.perf_counter() - started, 2)

    source = {s.i: s.text for s in segments}
    out = repos._translation.segments
    echoed = [s.i for s in out
              if echoes_source(source.get(s.i, ""), s.text,
                               source_lang="zh", target_lang="vi")]
    han = sum(1 for s in out for ch in s.text if "\u4e00" <= ch <= "\u9fff")
    return {
        "config": cfg,
        "engine": spec.id,
        "model_ref": spec.model_ref,
        "planned_batches": planned,
        "seconds": seconds,
        "calls": recorder.calls,
        "alignment_failures": sum(1 for c in recorder.calls if c["error"]),
        "accepted_segments": len(out),
        "translation_status": repos.status,
        "qa_issues": repos.qa_issues,
        "echo_segments": len(echoed),
        "han_chars": han,
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="measure_batch_chars.py")
    parser.add_argument("--engine", default="qwen2.5-3b",
                        help="id engine trong registry.json (mặc định engine 3B: nhanh)")
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--only", default=None,
                        help="chạy đúng một cấu hình theo `key` (khi cần đo lại)")
    args = parser.parse_args(argv)

    configs = [c for c in CONFIGS if args.only is None or c["key"] == args.only]
    if not configs:
        print(f"LOI: khong co cau hinh nao khop --only {args.only!r}", file=sys.stderr)
        return 2

    results = []
    for cfg in configs:
        print(f"=== {cfg['key']}: {cfg['n']} doan x {cfg['seg_chars']} ky tu, "
              f"batch_chars={cfg['batch_chars']}", flush=True)
        result = run_one(args.engine, cfg)
        print(f"    {result['seconds']} s · {len(result['calls'])} loi goi · "
              f"alignment_failures={result['alignment_failures']} · "
              f"echo={result['echo_segments']} · status={result['translation_status']}",
              flush=True)
        results.append(result)

    artifact = {
        "experiment": "batch-chars",
        "note": ("Đo TRẦN KÝ TỰ của một lời gọi engine. Transcript TỔNG HỢP, không "
                 "lấy từ clip thật. `engine_capabilities={}` nên KHÔNG có echo_guard: "
                 "đoạn bị chép nguyên văn là SỐ ĐO, không phải lỗi bị che."),
        "measured_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "engine": args.engine,
        "default_max_chars": 1200,
        "default_max_items": 30,
        "results": results,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "batch-chars.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"\nartifact: {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
