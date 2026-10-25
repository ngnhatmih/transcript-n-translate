"""Đo `N-…`: lô 25 mục nằm GIỮA clip — sạch vì CỠ, hay vì nó là ĐUÔI clip?

Nợ đang mở (README mục "Nợ Giai đoạn 2", và `docs/.../echo-guard-ket-qua-am.md` §6):
mọi lời gọi **25 mục** đo được tới nay đều sạch, nhưng **tất cả** đều là **đuôi
clip** (id 90–114, tức 30+30+30+25). Vì vậy "25 mục an toàn" chưa được chứng
minh: nó có thể chỉ là "đuôi clip sạch".

Phép đo này tách hai biến đó bằng đúng một lượt chạy: cùng clip 115 đoạn, cùng
engine, nhưng chia lô **25 mục** ⇒ các lô `0–24`, `25–49`, `50–74` nằm GIỮA clip,
và lô `100–114` là đuôi. Nếu lô 25 mục GIỮA clip bị chép thì kết luận cũ sai; nếu
sạch cả bốn lô thì "cỡ 25" mới có cơ sở — vẫn chỉ trên clip này.

Không bật `echo_guard` (`engine_capabilities={}`): cổng sẽ dịch lại và che mất
đúng thứ cần thấy.

Dùng:
    .\\.venv\\Scripts\\python.exe -B scripts/measure_batch_25.py \\
        --transcript ..\\data\\experiments\\accuracy-pipelines\\20261019-name-patch-smoke\\large-v3-beam5-prevfalse.json \\
        --glossary ..\\data\\experiments\\accuracy-pipelines\\20261019-term-placeholder-smoke\\glossary.json \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\20261025-batch-25
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
from app.domain.mt import batch_segments  # noqa: E402
from app.domain.mt_qa import echoes_source, is_echo  # noqa: E402
from app.pipeline.translate import TranslateHandler  # noqa: E402


class _Recorder:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls: list[dict] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def translate(self, batch, glossary, opts):
        record = {"n": len(self.calls) + 1, "items": len(batch),
                  "ids": [s.i for s in batch], "error": None}
        self.calls.append(record)
        started = time.perf_counter()
        try:
            return self._inner.translate(batch, glossary, opts)
        except Exception as exc:                   # noqa: BLE001
            record["error"] = type(exc).__name__
            raise
        finally:
            record["seconds"] = round(time.perf_counter() - started, 2)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="measure_batch_25.py")
    parser.add_argument("--transcript", type=pathlib.Path, required=True)
    parser.add_argument("--glossary", type=pathlib.Path, required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--engine", default="hy-mt-1.5-7b")
    parser.add_argument("--batch-items", type=int, default=25)
    args = parser.parse_args(argv)

    terms = smoke._load_terms(args.glossary)
    segments = smoke._load_segments(args.transcript, None)
    spec, engine = smoke._engine_and_capabilities(args.engine)
    recorder = _Recorder(engine)
    repos = smoke._InMemoryRepos(segments, terms, engine=spec.id,
                                 prompt_version=smoke._prompt_version(spec))
    handler = TranslateHandler(
        repos, {spec.id: recorder},
        engine_capabilities={spec.id: {}},     # KHONG echo_guard: do hop dong THO
        batch_items=args.batch_items,
    )
    job = smoke._Job()
    started = time.perf_counter()
    error = None
    try:
        handler.translate(translation_id=1, transcript_id=1, engine_id=spec.id,
                          source_lang="zh", target_lang="vi", job=job,
                          report=lambda _p, line: print(line, flush=True))
    except Exception as exc:                       # noqa: BLE001
        error = {"type": type(exc).__name__, "message": str(exc)[:400]}
    seconds = round(time.perf_counter() - started, 2)

    source = {s.i: s.text for s in segments}
    out = {s.i: s.text for s in repos._translation.segments}
    planned = batch_segments(segments, max_chars=1200, max_items=args.batch_items)
    rows = []
    for index, batch in enumerate(planned, start=1):
        copied = [s.i for s in batch
                  if echoes_source(source.get(s.i, ""), out.get(s.i, ""),
                                   source_lang="zh", target_lang="vi")]
        rows.append({
            "batch": index,
            "first_id": batch[0].i,
            "last_id": batch[-1].i,
            "items": len(batch),
            "copied": len(copied),
            "mid_clip": batch[-1].i < segments[-1].i,
        })

    artifact = {
        "experiment": "batch-25-mid-clip",
        "note": ("Tach hai bien: CO LO vs VI TRI. Lô 25 mục nằm giữa clip là thứ "
                 "duy nhất tách được '25 mục an toàn' khỏi 'đuôi clip sạch'. "
                 "engine_capabilities={} nen KHONG co echo_guard."),
        "measured_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "engine": spec.id,
        "model_ref": spec.model_ref,
        "batch_items": args.batch_items,
        "transcript": str(args.transcript),
        "segments": len(segments),
        "seconds": seconds,
        "llm_calls": len(recorder.calls),
        "calls": recorder.calls,
        "batches": rows,
        "accepted_segments": len(out),
        "translation_status": repos.status,
        "error": error,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"batch-{args.batch_items}.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")

    print(f"\n{len(rows)} lo theo ke hoach, {len(recorder.calls)} loi goi, {seconds} s")
    for row in rows:
        tag = "GIUA" if row["mid_clip"] else "DUOI"
        print(f"  lo {row['batch']}: id {row['first_id']}..{row['last_id']} "
              f"({row['items']} muc, {tag}) chep {row['copied']}/{row['items']}")
    print(f"artifact: {path}")
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
