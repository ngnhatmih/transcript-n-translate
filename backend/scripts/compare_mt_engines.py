"""So sánh CHẤT LƯỢNG dịch của các engine MT trên CÙNG một đoạn ngắn — qua ĐƯỜNG SẢN PHẨM.

## Vì sao phải qua `TranslateHandler`, không phải gọi thẳng adapter

prompt của một engine là thứ SẢN PHẨM chọn: p2 cho các engine Ollama, `echo_retry`/
`echo_guard`/`term_placeholder` theo `capabilities` của hàng registry, và trần số mục theo
`max_items_per_call`. Gọi thẳng `engine.translate(...)` thì rơi về prompt MẶC ĐỊNH (p1) — bản
đã đo là chép nguyên chữ nguồn 43/44 đoạn trên `qwen2.5-3b`. Đo "chất lượng" mà dùng sai prompt
thì con số vô nghĩa. Script này dựng `TranslateHandler` thật trên một repo TRONG BỘ NHỚ
(`scripts/smoke_term_placeholder._InMemoryRepos`), nên không chạm DB của repo.

## Nó KHÔNG đo được gì

* **BLEU/MQM**: cần bản tham chiếu của NGƯỜI, và đó là non-goal của repo. Cái in ra là bản dịch
  để người đọc chấm, kèm các tín hiệu MÁY đo được (echo, chữ Hán còn, rỗng, số issue QA).
* **Chất lượng cả clip**: một đoạn ngắn chỉ nói về đoạn đó. Câu nguồn là chữ ASR thật, nên có
  câu đã rác sẵn (`我怎么动我躺`) — engine không thể dịch đúng một câu vô nghĩa, và điều đó KHÔNG
  phải lỗi của engine.
* **Tính tái lập của engine `http`**: `deepseek-web` đi qua một dịch vụ bên ngoài.

## Chạy

    # lấy đoạn từ app đang chạy (transcript #1, 5 đoạn đầu)
    .\\.venv\\Scripts\\python.exe -B scripts\\compare_mt_engines.py --so-doan 5

    # hoặc từ một artifact transcript trong repo
    .\\.venv\\Scripts\\python.exe -B scripts\\compare_mt_engines.py \\
        --transcript ..\\data\\experiments\\...\\large-v3-beam5-prevfalse.json --so-doan 5
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import smoke_term_placeholder as smoke  # noqa: E402 - sau sys.path
from app.domain.models import Segment  # noqa: E402
from app.domain.mt_qa import echoes_source, is_echo, qa_translation  # noqa: E402
from app.pipeline.translate import TranslateHandler  # noqa: E402
from app.registry import by_id  # noqa: E402

HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
MAC_DINH = ("opus-mt", "qwen2.5-3b", "qwen2.5-7b", "hy-mt-1.5-7b", "deepseek-web")


def lay_tu_api(api: str, transcript_id: int, tu: int, so_doan: int) -> list[Segment]:
    with urllib.request.urlopen(f"{api}/api/transcripts/{transcript_id}", timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [Segment(i=s["i"], start=s["start"], end=s["end"], text=s["text"])
            for s in data["segments"][tu:tu + so_doan]]


def lay_tu_tep(path: pathlib.Path, tu: int, so_doan: int) -> list[Segment]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Segment(i=i + tu, start=s["start"], end=s["end"], text=s["text"])
            for i, s in enumerate(data["segments"][tu:tu + so_doan])]


def do_mot_engine(engine_id: str, engine, caps: dict, doan: list[Segment]) -> dict:
    prompt_version = getattr(engine, "prompt_version", "unknown")
    repos = smoke._InMemoryRepos(doan, [], engine=engine_id,
                                 prompt_version=str(prompt_version))
    handler = TranslateHandler(repos, {engine_id: engine},
                               engine_capabilities={engine_id: caps})
    dong: list[str] = []
    loi: str | None = None
    t0 = time.perf_counter()
    try:
        handler.translate(translation_id=1, transcript_id=1, engine_id=engine_id,
                          source_lang="zh", target_lang="vi", job=smoke._Job(),
                          report=lambda _p, line: dong.append(line))
    except Exception as exc:  # noqa: BLE001 - một engine hỏng không được làm hỏng phép đo
        loi = f"{type(exc).__name__}: {exc}"[:300]
    giay = round(time.perf_counter() - t0, 2)
    try:
        engine.release()
    except Exception:  # noqa: BLE001
        pass

    out = list(repos._translation.segments or [])
    nguon = {s.i: s.text for s in doan}
    issues = qa_translation(doan, out, glossary=[], supports_glossary=False) if out else []
    return {
        "engine": engine_id,
        "prompt_version": str(prompt_version),
        "capabilities": {k: v for k, v in caps.items() if k != "available"},
        "seconds": giay,
        "llm_calls": len(repos.llm_calls),
        "status": repos.status,
        "error": loi,
        "echo_guard": [s.i for s in out
                       if echoes_source(nguon.get(s.i, ""), s.text,
                                        source_lang="zh", target_lang="vi")],
        "echo_qa": [s.i for s in out if is_echo(nguon.get(s.i, ""), s.text)],
        "han_left": [s.i for s in out if HAN.search(s.text)],
        "empty": [s.i for s in out if not s.text.strip()],
        "qa_issues": issues,
        "translations": [{"i": s.i, "text": s.text} for s in out],
        "log": dong,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compare_mt_engines.py")
    parser.add_argument("--api", default="http://127.0.0.1:3100")
    parser.add_argument("--transcript-id", type=int, default=1)
    parser.add_argument("--transcript", type=pathlib.Path, default=None,
                        help="artifact JSON của một transcript (thay cho --api)")
    parser.add_argument("--tu", type=int, default=0)
    parser.add_argument("--so-doan", type=int, default=5)
    parser.add_argument("--engines", default=",".join(MAC_DINH))
    parser.add_argument("--out-dir", type=pathlib.Path, default=None,
                        help="ghi artifact JSON vào thư mục này")
    args = parser.parse_args(argv)

    doan = (lay_tu_tep(args.transcript, args.tu, args.so_doan) if args.transcript
            else lay_tu_api(args.api, args.transcript_id, args.tu, args.so_doan))
    if not doan:
        print("KHÔNG lấy được đoạn nào — dừng (một phép đo 0 đoạn là phép đo vô nghĩa)")
        return 2

    from app import main as root

    _repos, specs, _worker, _broker, mt_engines = root.build_components()
    print(f"== {len(doan)} đoạn, từ i={doan[0].i}")
    for s in doan:
        print(f"   [{s.i}] {s.text}")

    ket: list[dict] = []
    for engine_id in [e.strip() for e in args.engines.split(",") if e.strip()]:
        engine = mt_engines.get(engine_id)
        if engine is None:
            ket.append({"engine": engine_id, "error": "engine KHÔNG dựng được "
                                                      "(available: false)"})
            continue
        ket.append(do_mot_engine(engine_id, engine, dict(by_id(specs, engine_id).capabilities),
                                 doan))

    print("\n== TỔNG HỢP (đường sản phẩm: prompt + capability của từng engine)")
    print(f"{'engine':<16} {'giây':>6} {'gọi':>4} {'status':<9} {'echo':>4} {'Hán':>4} "
          f"{'rỗng':>5} {'QA':>3}  lỗi")
    for k in ket:
        if "seconds" not in k:
            print(f"{k['engine']:<16} {'-':>6} {'-':>4} {'-':<9} {'-':>4} {'-':>4} {'-':>5} "
                  f"{'-':>3}  {k['error']}")
            continue
        print(f"{k['engine']:<16} {k['seconds']:>6} {k['llm_calls']:>4} "
              f"{str(k['status']):<9} {len(k['echo_guard']):>4} {len(k['han_left']):>4} "
              f"{len(k['empty']):>5} {len(k['qa_issues']):>3}  {k['error'] or ''}")

    print("\n== BẢN DỊCH THEO TỪNG ĐOẠN")
    for idx, s in enumerate(doan):
        print(f"\n[{s.i}] NGUỒN: {s.text}")
        for k in ket:
            if "translations" not in k:
                continue
            ban = next((t["text"] for t in k["translations"] if t["i"] == s.i), "(không có)")
            print(f"   {k['engine']:<16} {ban}")

    if args.out_dir is not None:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        dich = args.out_dir / f"compare-mt-{_dt.datetime.now():%Y%m%d-%H%M%S}.json"
        dich.write_text(json.dumps({
            "note": ("So sánh chất lượng trên MỘT ĐOẠN NGẮN, đường sản phẩm "
                     "(TranslateHandler). KHÔNG có bản tham chiếu của người ⇒ KHÔNG có BLEU/"
                     "MQM. Nguồn là chữ ASR thật nên có câu rác sẵn."),
            "doan": [{"i": s.i, "text": s.text} for s in doan],
            "ket_qua": ket,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[artifact] {dich}")
    return 0 if all("translations" in k for k in ket) else 1


if __name__ == "__main__":
    raise SystemExit(main())
