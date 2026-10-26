"""Spike: dich qua MOT endpoint OpenAI-compatible BAT KY (gateway hay API that).

Cau hoi cua spike (khong phai cau hoi san pham)
    Mot endpoint `/v1/chat/completions` co giu duoc HOP DONG DAU RA cua duong dich
    khong — du so muc, dung `id`, khong rong — va gia phai tra la bao nhieu giay,
    bao nhieu loi hop dong? Ung dung that: `whalegate` (bien phien
    `chat.deepseek.com` thanh OpenAI API) hoac API chinh thuc. Script nay KHONG
    biet ben kia la ai va cung khong can biet: no chi noi giao thuc.

Vi sao khong viet mot driver thu hai
    No KHONG tu chia lo, tu ghep alignment hay tu kiem QA. No dung dung
    `TranslateHandler` cua san pham — cung batching, cung retry alignment, cung
    `qa_translation` — va chi thay ENGINE, dung kieu `scripts/smoke_echo_guard.py`
    thay engine bang mot `_CallRecorder`. Nho vay con so do duoc la cua DUONG
    SHIP, khong phai cua mot duong rieng de do.

    Engine do la adapter THAT trong `app/adapters/mt/openai_chat_mt.py`, khong
    phai mot ban sao trong script: mot adapter chi de do la adapter khong ai
    chay, va no troi khoi san pham ngay tuan sau.

Vi sao KHONG dung registry.json
    Mot engine chua do thi chua duoc khai. Script nay truyen
    `engine_capabilities={engine_id: {}}`, tuc engine KHONG co `echo_guard`,
    `term_placeholder` hay `name_patch` — dung su that cua mot endpoint la.

Canh bao ve tinh trung thuc cua artifact
    Artifact ghi `base_url`, `model`, `contract` cua DUNG lan chay, va `note` noi
    ro day la spike giao thuc. Mot con so "DeepSeek" chi duoc phep trich dan khi
    `base_url` tro vao gateway va nguoi doc da doc `note`.

Vi du
    # Endpoint OpenAI-compatible co san (Ollama), de kiem chinh script nay:
    .\\.venv\\Scripts\\python.exe -B scripts\\spike_openai_mt.py \\
        --transcript ..\\data\\experiments\\accuracy-pipelines\\20261019-name-patch-smoke\\large-v3-beam5-prevfalse.json \\
        --glossary ..\\data\\experiments\\accuracy-pipelines\\20261019-term-placeholder-smoke\\glossary.json \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\20261025-spike-openai-mt \\
        --label ollama-v1-hy-mt-lines-b30 --model hy-mt1.5-7b:q4_K_M \\
        --contract lines --batch-items 30

    # Cung script, doi base-url sang gateway (khong doi gi khac):
    ... --base-url http://127.0.0.1:8790/v1 --model deepseek-chat --api-key-env DS_KEY
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import sys
import time
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import smoke_term_placeholder as smoke  # noqa: E402 - sau sys.path
from app.adapters.mt.openai_chat_mt import OpenAiChatMt  # noqa: E402
from app.domain.alignment import AlignmentProblem  # noqa: E402
from app.domain.mt_qa import echoes_source, is_echo  # noqa: E402
from app.pipeline.translate import TranslateHandler  # noqa: E402

#: Ten engine trong artifact. KHONG phai id trong `registry.json` — co y nhu vay,
#: de khong ai doc nham mot engine chua do la mot engine da khai.
ENGINE_ID = "openai-compat-spike"

#: Endpoint mac dinh = Ollama, vi no la thu DUY NHAT co san tren may nay va noi
#: cung giao thuc. Gateway that la `http://127.0.0.1:8790/v1`.
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"


class _Recorder:
    """Ghi MOI loi goi thanh mot hang: so muc, ids, giay, va LOAI loi.

    Loai loi la cau hoi chinh cua spike: `alignment` (endpoint tra sai so dong /
    sai id) khac `http` (mang, 500) khac `other`. Gop chung vao "failed" la lam
    mat dung thu can do.
    """

    def __init__(self, inner: OpenAiChatMt) -> None:
        self._inner = inner
        self.calls: list[dict] = []

    def __getattr__(self, name: str) -> Any:      # engine_id, release, ...
        return getattr(self._inner, name)

    def translate(self, batch, glossary, opts):
        record: dict = {"n": len(self.calls) + 1, "items": len(batch),
                        "ids": [s.i for s in batch], "error": None,
                        "kind": None}
        self.calls.append(record)
        started = time.perf_counter()
        try:
            out = self._inner.translate(batch, glossary, opts)
        except Exception as exc:                  # noqa: BLE001 - phan loai roi nem
            record["error"] = f"{type(exc).__name__}: {exc}"[:500]
            if isinstance(exc, AlignmentProblem):
                record["kind"] = "alignment"
            else:
                name = type(exc).__name__
                record["kind"] = "http" if name.startswith("HTTP") else "other"
            record["seconds"] = round(time.perf_counter() - started, 2)
            raise
        record["seconds"] = round(time.perf_counter() - started, 2)
        stats = getattr(self._inner, "last_stats", None)
        if stats is not None:
            record["tokens_in"] = stats.tokens_in
            record["tokens_out"] = stats.tokens_out
        return out


def _han_count(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def run(transcript: pathlib.Path, glossary: pathlib.Path, out_dir: pathlib.Path,
        *, label: str, base_url: str, model: str, api_key: str | None,
        batch_items: int | None, contract: str, json_mode: str,
        temperature: float | None = None, max_tokens: int | None = None,
        reasoning_effort: str | None = None) -> dict:
    terms = smoke._load_terms(glossary)
    segments = smoke._load_segments(transcript, None)
    adapter = OpenAiChatMt(model, base_url=base_url, engine_id=ENGINE_ID,
                           api_key=api_key, contract=contract,
                           json_mode=json_mode, temperature=temperature,
                           max_tokens=max_tokens,
                           reasoning_effort=reasoning_effort)
    engine = _Recorder(adapter)
    repos = smoke._InMemoryRepos(segments, terms, engine=ENGINE_ID,
                                 prompt_version=adapter.prompt_version)
    handler = TranslateHandler(
        repos, {ENGINE_ID: engine},
        # Engine nay KHONG khai capability nao: chua do thi chua khai. Doi lai,
        # duong di la duong CU tung byte — dung thu can do.
        engine_capabilities={ENGINE_ID: {}},
        batch_items=batch_items,
    )
    job = smoke._Job()
    started = time.perf_counter()
    error: dict | None = None
    try:
        handler.translate(translation_id=1, transcript_id=1, engine_id=ENGINE_ID,
                          source_lang="zh", target_lang="vi", job=job,
                          report=lambda _progress, line: print(line, flush=True))
    except Exception as exc:                      # noqa: BLE001 - artifact phai co
        error = {"type": type(exc).__name__, "message": str(exc)[:800]}
    seconds = round(time.perf_counter() - started, 2)

    source = {s.i: s.text for s in segments}
    out = repos._translation.segments
    guard_echo = [s.i for s in out
                  if echoes_source(source.get(s.i, ""), s.text,
                                   source_lang="zh", target_lang="vi")]
    qa_echo = [s.i for s in out if is_echo(source.get(s.i, ""), s.text)]
    han_chars = sum(_han_count(s.text) for s in out)
    term_rows: list[dict] = []
    for term in terms:
        for segment in out:
            zh = source.get(segment.i, "")
            if term.term and term.term in zh:
                term_rows.append({"i": segment.i, "term": term.term,
                                  "expect": term.translation,
                                  "hit": term.translation in segment.text})

    kinds = {"alignment": 0, "http": 0, "other": 0}
    for call in engine.calls:
        if call["kind"] in kinds:
            kinds[call["kind"]] += 1

    artifact = {
        "experiment": "spike-openai-mt",
        "note": (
            "SPIKE GIAO THUC, khong phai engine san pham va khong phai default. "
            f"Endpoint cua lan chay nay: {base_url} / model {model} / "
            f"contract {contract}. Chi duoc trich dan la 'DeepSeek' khi base_url "
            "tro vao gateway va nguoi doc da doi chieu truong nay."),
        "spike_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "engine": ENGINE_ID,
        "base_url": base_url,
        "model": model,
        "contract": contract,
        "json_mode": json_mode,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "reasoning_effort": reasoning_effort,
        "transcript": str(transcript),
        "glossary": [[t.term, t.translation] for t in terms],
        "segments": len(segments),
        "batch_items": batch_items,
        "seconds": seconds,
        "llm_calls": len(engine.calls),
        "failed_calls": sum(1 for c in engine.calls if c["error"]),
        "failed_by_kind": kinds,
        "calls": engine.calls,
        "accepted_segments": len(out),
        "translation_status": repos.status,
        "qa_issues": repos.qa_issues,
        "han_chars": han_chars,
        "echo_segments_guard": len(guard_echo),
        "echo_ids_guard": guard_echo,
        "echo_segments_qa": len(qa_echo),
        "terms_expected": len(term_rows),
        "terms_hit": sum(1 for row in term_rows if row["hit"]),
        "terms": term_rows,
        "error": error,
        "sentences": [{"i": s.i, "zh": source.get(s.i, ""), "vi": s.text,
                       "qa": list(s.qa)} for s in out],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{label}.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="spike_openai_mt.py")
    parser.add_argument("--transcript", type=pathlib.Path, required=True)
    parser.add_argument("--glossary", type=pathlib.Path, required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--label", required=True,
                        help="ten tep artifact, vi du `ollama-v1-hy-mt-lines-b30`")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help="goc API OpenAI-compatible, co duoi `/v1` "
                             f"(mac dinh {DEFAULT_BASE_URL} = Ollama, de kiem "
                             "chinh script; gateway whalegate la "
                             "http://127.0.0.1:8790/v1)")
    parser.add_argument("--model", required=True)
    parser.add_argument("--contract", choices=("json", "lines"), default="json",
                        help="hop dong DAU RA: `json` (chi dung khi endpoint bao "
                             "dam JSON) hay `lines` (endpoint khong co grammar)")
    parser.add_argument("--api-key-env", default=None,
                        help="TEN bien moi truong chua API key (khong truyen key "
                             "tren dong lenh: no se nam trong history)")
    parser.add_argument("--batch-items", type=int, default=None,
                        help="tran so muc cua mot loi goi; bo trong = "
                             "`capabilities.max_items_per_call` (khong khai => 30)")
    parser.add_argument("--json-mode", choices=("none", "object"), default="none",
                        help="`object` gui `response_format: json_object` — "
                             "gateway web KHONG ho tro tham so nay")
    parser.add_argument("--temperature", type=float, default=None,
                        help="bo trong = KHONG gui (gateway web bo qua tham so nay)")
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="bo trong = KHONG gui")
    parser.add_argument("--reasoning-effort", default=None,
                        help="chi co y nghia voi gateway ho tro DeepThink")
    parser.add_argument("--timeout-s", type=float, default=600.0)
    args = parser.parse_args(argv)

    api_key = None
    if args.api_key_env:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            print(f"LOI: bien moi truong {args.api_key_env} rong hoac khong co",
                  file=sys.stderr)
            return 2

    artifact = run(args.transcript, args.glossary, args.out_dir, label=args.label,
                   base_url=args.base_url, model=args.model, api_key=api_key,
                   batch_items=args.batch_items, contract=args.contract,
                   json_mode=args.json_mode, temperature=args.temperature,
                   max_tokens=args.max_tokens,
                   reasoning_effort=args.reasoning_effort)
    kinds = artifact["failed_by_kind"]
    print(f"endpoint      : {artifact['base_url']} / {artifact['model']} "
          f"/ contract {artifact['contract']}")
    print(f"seconds       : {artifact['seconds']}")
    print(f"llm_calls     : {artifact['llm_calls']} "
          f"(failed={artifact['failed_calls']}: alignment={kinds['alignment']}, "
          f"http={kinds['http']}, other={kinds['other']})")
    print(f"accepted      : {artifact['accepted_segments']}/"
          f"{artifact['segments']}  status={artifact['translation_status']}")
    print(f"chinese left  : {artifact['han_chars']}  "
          f"echo(guard)={artifact['echo_segments_guard']}  "
          f"echo(qa)={artifact['echo_segments_qa']}")
    print(f"glossary      : {artifact['terms_hit']}/{artifact['terms_expected']} "
          "doan-chua-thuat-ngu co rendering")
    if artifact["error"]:
        print(f"error         : {artifact['error']['type']}: "
              f"{artifact['error']['message'][:200]}")
    return 0 if artifact["error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
