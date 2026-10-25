"""Spike: dich qua MOT endpoint OpenAI-compatible BAT KY (gateway hay API that).

Cau hoi cua spike (khong phai cau hoi san pham)
    Mot endpoint `/v1/chat/completions` co giu duoc HOP DONG JSON cua duong dich
    khong — dung so muc, dung `id`, khong rong — va gia phai tra la bao nhieu
    giay, bao nhieu loi hop dong? Ung dung that: `whalegate` (bien phien
    `chat.deepseek.com` thanh OpenAI API) hoac API chinh thuc. Script nay KHONG
    biet ben kia la ai va cung khong can biet: no chi noi giao thuc.

Vi sao khong viet mot driver thu hai
    No KHONG tu chia lo, tu ghep alignment hay tu kiem QA. No dung dung
    `TranslateHandler` cua san pham — cung batching, cung `parse_batch_response`,
    cung retry alignment, cung `qa_translation` — va chi thay ENGINE, dung kieu
    `scripts/smoke_echo_guard.py` thay engine bang mot `_CallRecorder`. Nho vay
    con so do duoc la cua DUONG SHIP, khong phai cua mot duong rieng de do.

Vi sao KHONG dung registry.json
    Mot engine chua do thi chua duoc khai. Script nay truyen
    `engine_capabilities={engine_id: {}}`, tuc engine KHONG co `echo_guard`,
    `term_placeholder` hay `name_patch` — dung su that cua mot endpoint la. Neu
    sau nay so do bien no thanh engine that thi do la mot buoc rieng, co test.

Canh bao ve tinh trung thuc cua artifact
    Artifact ghi `base_url` va `model` cua DUNG lan chay, va `note` noi ro day la
    spike giao thuc. Mot con so "DeepSeek" chi duoc phep trich dan khi `base_url`
    tro vao gateway va `note` da duoc doc. Day la cho de mot artifact bi doc nham
    la "do DeepSeek" trong khi no la mot lan chay Ollama.

Vi du
    # Endpoint OpenAI-compatible co san (Ollama), de kiem chinh script nay:
    .\\.venv\\Scripts\\python.exe -B scripts\\spike_openai_mt.py \\
        --transcript ..\\data\\experiments\\accuracy-pipelines\\20261019-name-patch-smoke\\large-v3-beam5-prevfalse.json \\
        --glossary ..\\data\\experiments\\accuracy-pipelines\\20261019-term-placeholder-clip\\glossary.json \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\20261025-spike-openai-mt \\
        --label ollama-v1-hy-mt --model hy-mt1.5-7b:q4_K_M --batch-items 30

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

import httpx  # noqa: E402 - sau sys.path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import smoke_term_placeholder as smoke  # noqa: E402 - sau sys.path
from app.adapters.mt.prompts import (system_prompt,  # noqa: E402
                                     user_prompt, parse_batch_response)
from app.domain.models import CallStats, Segment, Term  # noqa: E402
from app.domain.mt import MtOpts  # noqa: E402
from app.domain.mt_qa import echoes_source, is_echo  # noqa: E402
from app.pipeline.translate import TranslateHandler  # noqa: E402

#: Ten engine trong artifact. KHONG phai id trong `registry.json` — co y nhu vay,
#: de khong ai doc nham mot engine chua do la mot engine da khai.
ENGINE_ID = "openai-compat-spike"

#: Ten rieng cua endpoint trong artifact, de `note` noi dung su that.
DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"


class ContractError(RuntimeError):
    """Endpoint tra ve thu khong dung hop dong: JSON hong, sai so muc, sai id.

    Day la cau hoi CHINH cua spike, nen no phai la mot LOAI LOI rieng: `failed`
    vi mang khong dung khong duoc lan voi `failed` vi timeout.
    """


class OpenAiChatMt:
    """Engine toi thieu cho `/v1/chat/completions`.

    Chi lam dung ba viec: gui hai prompt, doc `choices[0].message.content`, giao
    chuoi do cho `parse_batch_response` (ham DUY NHAT trong du an bien phan hoi
    engine thanh `Segment`). Dat `max_tokens`, `top_p`, `stop`, `response_format`
    la tuy endpoint: gateway kieu web KHONG co cac tham so nay, nen mac dinh
    script chi gui nhung gi mot web-session co the nhan.
    """

    def __init__(self, base_url: str, model: str, *, api_key: str | None = None,
                 json_mode: str = "none", timeout_s: float = 600.0,
                 reasoning_effort: str | None = None,
                 client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._json_mode = json_mode
        self._reasoning_effort = reasoning_effort
        self._client = client if client is not None else httpx.Client()
        self._timeout_s = timeout_s
        #: Moi loi goi mot dict — nguon DUY NHAT cua `llm_calls` trong artifact.
        self.calls: list[dict] = []
        self.last_stats: CallStats | None = None

    # -- hop dong `MtEngine` ----------------------------------------------------
    def engine_id(self) -> str:
        return ENGINE_ID

    def model_ref(self) -> str:
        return self._model

    def prompt_version(self) -> str:
        return "hymt-json-p2"

    def supports_glossary(self) -> bool:
        return True

    def release(self) -> None:
        """Khong gi de do: endpoint la ben kia quan ly VRAM, khong phai ta."""

    # -- mot luot goi -----------------------------------------------------------
    def chat(self, system: str, user: str, *, temperature: float | None = None) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
        }
        # Nhiet do: gateway web KHONG nhan tham so nay, nen chi gui khi co yeu cau
        # ro rang. Mac dinh `None` = khong gui, tuc khong hua mot thu minh khong
        # dieu khien duoc.
        if temperature is not None:
            body["temperature"] = temperature
        if self._json_mode == "object":
            body["response_format"] = {"type": "json_object"}
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        record: dict[str, Any] = {
            "n": len(self.calls) + 1,
            "items": None,
            "ids": None,
            "seconds": None,
            "error": None,
            "contract_error": None,
        }
        self.calls.append(record)
        started = time.perf_counter()
        try:
            resp = self._client.post(f"{self._base_url}/chat/completions",
                                     json=body, headers=headers,
                                     timeout=self._timeout_s)
            record["status"] = resp.status_code
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            text = (exc.response.text or "")[:400]
            record["response_head"] = text
            raise
        except Exception as exc:                     # noqa: BLE001 - ghi lai roi nem
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            record["seconds"] = round(time.perf_counter() - started, 2)

        choices = data.get("choices")
        message = choices[0].get("message") if choices else None
        content = message.get("content") if isinstance(message, dict) else None
        usage = data.get("usage") or {}
        record["tokens_in"] = usage.get("prompt_tokens")
        record["tokens_out"] = usage.get("completion_tokens")
        self.last_stats = CallStats(
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            duration_ms=int((record["seconds"] or 0) * 1000),
        )
        if not isinstance(content, str) or not content.strip():
            record["contract_error"] = "empty-content"
            raise ContractError(f"endpoint tra `content` rong: {json.dumps(data)[:300]}")
        return content

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        if not batch:
            return []
        record = self.calls[-1] if self.calls else None
        if record is not None:
            record["items"] = len(batch)
            record["ids"] = [s.i for s in batch]
        content = self.chat(
            system_prompt(glossary, target_lang=opts.target_lang, engine_id=None),
            user_prompt(batch, source_lang=opts.source_lang,
                        target_lang=opts.target_lang, engine_id=None),
            temperature=opts.temperature)
        try:
            return parse_batch_response(content, batch)
        except Exception as exc:                    # noqa: BLE001 - phan loai lai
            if record is not None:
                record["contract_error"] = f"{type(exc).__name__}: {exc}"
                record["response_head"] = content[:400]
            raise


def _han_count(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def run(transcript: pathlib.Path, glossary: pathlib.Path, out_dir: pathlib.Path,
        *, label: str, base_url: str, model: str, api_key: str | None,
        batch_items: int | None, json_mode: str,
        reasoning_effort: str | None = None) -> dict:
    terms = smoke._load_terms(glossary)
    segments = smoke._load_segments(transcript, None)
    repos = smoke._InMemoryRepos(segments, terms, engine=ENGINE_ID,
                                 prompt_version="hymt-json-p2")
    engine = OpenAiChatMt(base_url, model, api_key=api_key, json_mode=json_mode,
                          reasoning_effort=reasoning_effort)
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
    except Exception as exc:                        # noqa: BLE001 - artifact phai co
        error = {"type": type(exc).__name__, "message": str(exc)[:800]}
    seconds = round(time.perf_counter() - started, 2)

    source = {s.i: s.text for s in segments}
    out = repos._translation.segments
    guard_echo = [s.i for s in out
                  if echoes_source(source.get(s.i, ""), s.text,
                                   source_lang="zh", target_lang="vi")]
    qa_echo = [s.i for s in out if is_echo(source.get(s.i, ""), s.text)]
    han_chars = sum(_han_count(s.text) for s in out)
    # Thuat ngu: doan nao NGUON co thuat ngu thi ban dich co rendering do khong —
    # day la cau hoi ma ca duong hybrid sinh ra de tra loi.
    term_rows: list[dict] = []
    for term in terms:
        for segment in out:
            zh = source.get(segment.i, "")
            if term.term and term.term in zh:
                term_rows.append({"i": segment.i, "term": term.term,
                                  "expect": term.translation,
                                  "hit": term.translation in segment.text})
    contract_failures = [c for c in engine.calls if c.get("contract_error")]
    http_failures = [c for c in engine.calls if c.get("error")]

    artifact = {
        "experiment": "spike-openai-mt",
        "note": (
            "SPIKE GIAO THUC, khong phai engine san pham va khong phai default. "
            f"Endpoint cua lan chay nay: {base_url} / model {model}. "
            "Chi duoc trich dan la 'DeepSeek' khi base_url tro vao gateway va "
            "nguoi doc da doi chieu truong nay."),
        "spike_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "engine": ENGINE_ID,
        "base_url": base_url,
        "model": model,
        "json_mode": json_mode,
        "reasoning_effort": reasoning_effort,
        "transcript": str(transcript),
        "glossary": [[t.term, t.translation] for t in terms],
        "segments": len(segments),
        "batch_items": batch_items,
        "seconds": seconds,
        "llm_calls": len(engine.calls),
        "contract_failures": len(contract_failures),
        "http_failures": len(http_failures),
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
                        help="ten tep artifact, vi du `ollama-v1-hy-mt`")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help="goc API OpenAI-compatible, co duoi `/v1` "
                             f"(mac dinh {DEFAULT_BASE_URL} = Ollama, de kiem "
                             "chinh script; gateway whalegate la "
                             "http://127.0.0.1:8790/v1)")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-env", default=None,
                        help="TEN bien moi truong chua API key (khong truyen key "
                             "tren dong lenh: no se nam trong history)")
    parser.add_argument("--batch-items", type=int, default=None,
                        help="tran so muc cua mot loi goi; bo trong = "
                             "`capabilities.max_items_per_call` (khong khai => 30)")
    parser.add_argument("--json-mode", choices=("none", "object"), default="none",
                        help="`object` gui `response_format: json_object` — "
                             "gateway web KHONG ho tro tham so nay, nen mac dinh "
                             "`none` la che do trung thuc voi gateway")
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
                   batch_items=args.batch_items, json_mode=args.json_mode,
                   reasoning_effort=args.reasoning_effort)
    print(f"endpoint      : {artifact['base_url']} / {artifact['model']}")
    print(f"seconds       : {artifact['seconds']}")
    print(f"llm_calls     : {artifact['llm_calls']} "
          f"(contract_failures={artifact['contract_failures']}, "
          f"http_failures={artifact['http_failures']})")
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
