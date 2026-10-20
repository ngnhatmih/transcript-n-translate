"""Smoke THẬT của bảo vệ thuật ngữ bằng token: 7 câu vàng, hoặc cả clip.

Đây là đường CHẠY THẬT của `app/domain/term_placeholder.py`: nó dựng
`TranslateHandler` của sản phẩm với engine `hy-mt-1.5-7b` THẬT (Ollama) và một
repo trong bộ nhớ, nên mọi thứ đi qua ĐÚNG seam đã ship — che thuật ngữ trước khi
gọi adapter, khôi phục sau đó, và gắn cờ QA lên segment.

Vì sao dùng `TranslateHandler` chứ không gọi thẳng adapter
    Smoke này tồn tại để trả lời "policy Hán-Việt có được giữ không". Gọi thẳng
    `OllamaMtEngine.translate` thì bỏ qua chính chỗ cài cơ chế (seam trong
    `pipeline/translate.py`) và một smoke như vậy có thể XANH trong khi đường sản
    phẩm vẫn để model tự chọn âm.

Vì sao repo là bản trong bộ nhớ
    Bốn thứ handler cần (`translation`, `transcript`, `terms`, `llm_calls`) là dữ
    liệu vào, không phải thứ smoke này đo. DB thật chỉ thêm một tệp phải dọn; còn
    đường ĐỌC/GHI segment thì vẫn là code của handler.

Vì sao in cả câu KHÔNG có thuật ngữ
    Nhóm đó là đối chứng: nếu handler chạm vào cả những câu không có thuật ngữ thì
    text ra phải khác bản dịch thường — in ra để người đọc so bằng mắt, không chỉ
    tin vào một dòng "không đổi".

Không thuộc bộ pytest: cần Ollama + model thật (~5 GB VRAM), không có bài test giả
nào thay được nó.

`--engine` và `--batch-items` KHÔNG mở một đường thứ hai: chúng chỉ đổi hai giá trị
mà composition root cũng đổi được (`spec.id` của registry và
`TranslateHandler(batch_items=...)`). Chúng tồn tại vì hai phép ĐO cần chúng — quét
kích thước lô, và so `hy-mt-1.5-7b` với `opus-mt` trên cùng một tập câu. Đo kích
thước lô bằng cách sửa `DEFAULT_MAX_ITEMS` mới là thứ không được làm: như vậy mỗi
lần đo lại là một lần đổi mặc định của sản phẩm.

Ví dụ:
    python -B scripts\\smoke_term_placeholder.py --positions 14 23 47 64 96 100 113 \\
        --transcript ..\\data\\experiments\\...\\large-v3-beam5-prevfalse.json \\
        --glossary ..\\data\\experiments\\...\\glossary.json --out-dir ..\\data\\...
    python -B scripts\\smoke_term_placeholder.py --transcript ... --glossary ... \\
        --out-dir ... --engine opus-mt --batch-items 8
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.mt.ollama_mt import OllamaMtEngine  # noqa: E402 - sau sys.path
from app.adapters.mt.opus_mt import OpusMtEngine  # noqa: E402
from app.adapters.mt.prompts import PROMPT_VERSION  # noqa: E402
from app.adapters.registry_file import load_registry  # noqa: E402
from app.domain.models import Segment, Term  # noqa: E402
from app.domain.mt import DEFAULT_MAX_ITEMS  # noqa: E402
from app.domain.term_placeholder import (TOKEN_COLLISION,  # noqa: E402
                                         TOKEN_DUPLICATED, TOKEN_LOST,
                                         TOKEN_UNKNOWN, plan_terms)
from app.pipeline.translate import TranslateHandler  # noqa: E402

ENGINE_ID = "hy-mt-1.5-7b"
FLAGS = (TOKEN_LOST, TOKEN_DUPLICATED, TOKEN_UNKNOWN, TOKEN_COLLISION)
_TOKEN_IN_TEXT = re.compile(r"(?<![0-9A-Za-z])ZXQ\s*\d+", re.IGNORECASE)


class _Stored:
    """Hàng `translations`/`transcripts` tối thiểu mà handler đọc."""

    def __init__(self, segments, *, engine="", prompt_version=""):
        self.segments = segments
        self.chimera = None
        self.engine = engine
        self.prompt_version = prompt_version


class _Job:
    def __init__(self):
        self.id = None
        self.progress = 0.0
        self.cancel_requested = False


class _InMemoryRepos:
    """Repo trong bộ nhớ: đúng những phương thức `TranslateHandler` gọi."""

    def __init__(self, segments: list[Segment], terms: list[Term], *,
                 engine: str, prompt_version: str):
        self._transcript = _Stored(segments)
        self._translation = _Stored([], engine=engine, prompt_version=prompt_version)
        self._terms = terms
        self.llm_calls: list[dict] = []
        self.status: str | None = None
        self.qa_issues: list[str] = []

    def get_translation(self, translation_id):
        return self._translation

    def get_transcript(self, transcript_id):
        return self._transcript

    def list_terms(self, lang=None):
        return [t for t in self._terms if lang is None or t.lang == lang]

    def glossary_version(self):
        return 1

    def update_translation_segments(self, translation_id, segments):
        # GIỮ NGUYÊN object: smoke đọc lại chính các segment handler đã ghi, nên
        # nó đo đúng thứ được lưu, không phải một bản chép lại.
        self._translation.segments = list(segments)

    def set_translation_status(self, translation_id, status, **kw):
        self.status = status
        self.qa_issues = list(kw.get("qa_issues") or [])

    def set_transcript_status(self, transcript_id, status):
        pass

    def add_llm_call(self, **kw):
        self.llm_calls.append(kw)

    def list_llm_calls(self, job_id):
        return self.llm_calls


class _RecordingEngine:
    """Bọc engine THẬT, chỉ ghi lại CHUỖI nó nhận được.

    Chuỗi đó là bằng chứng duy nhất cho hai câu hỏi của smoke: câu có thuật ngữ đã
    được che chưa, và câu KHÔNG có thuật ngữ có đi qua y nguyên không.
    """

    def __init__(self, inner):
        self._inner = inner
        #: `{i: chuỗi engine nhận được}` — theo ID, nên không phụ thuộc thứ tự lô.
        self.received: dict[int, str] = {}

    @property
    def engine_id(self) -> str:
        return self._inner.engine_id

    @property
    def model_ref(self) -> str:
        return self._inner.model_ref

    @property
    def last_stats(self):
        return getattr(self._inner, "last_stats", None)

    def supports_glossary(self) -> bool:
        return self._inner.supports_glossary()

    def translate(self, batch, glossary, opts):
        for segment in batch:
            self.received[segment.i] = segment.text
        return self._inner.translate(batch, glossary, opts)

    def release(self) -> None:
        self._inner.release()


def _load_terms(path: pathlib.Path) -> list[Term]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Term(id=None, lang=str(item.get("lang", "zh")), term=str(item["term"]),
                 translation=str(item["translation"]),
                 approved=bool(item.get("approved", True))) for item in payload]


def _load_segments(path: pathlib.Path, positions: list[int] | None) -> list[Segment]:
    """Đọc segment theo VỊ TRÍ mảng; `i` = vị trí (tệp nguồn không có `i`).

    Vị trí được giữ nguyên làm `i` để báo cáo trỏ lại đúng dòng của tệp gốc.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload["segments"] if isinstance(payload, dict) else payload
    wanted = range(len(raw)) if positions is None else positions
    return [Segment(i=position, start=float(raw[position]["start"]),
                    end=float(raw[position]["end"]),
                    text=str(raw[position]["text"]))
            for position in wanted]


def _engine_and_capabilities(engine_id: str = ENGINE_ID):
    """Dựng adapter THẬT của `engine_id` theo `runtime` khai trong registry.

    Cùng ánh xạ mà composition root dùng (`main._build_mt_engines`): `ollama` ⇒
    `OllamaMtEngine` (HTTP, VRAM do Ollama quản), còn lại ⇒ `OpusMtEngine` (nạp
    model vào CHÍNH tiến trình này, CPU). Nhờ vậy phép so engine của Task 3 đi qua
    đúng hai adapter mà sản phẩm dùng, không phải một bản dựng tay thứ ba.
    """
    specs = load_registry()
    spec = next(s for s in specs if s.id == engine_id)
    if spec.runtime == "ollama":
        engine: object = OllamaMtEngine(
            spec.model_ref, engine_id=spec.id,
            supports_glossary=bool(spec.capabilities.get("glossary_prompt", False)),
        )
    else:
        engine = OpusMtEngine(spec.model_ref)
    return spec, engine


def _prompt_version(spec) -> str:
    """Version prompt THẬT của engine: `build_components` mới đặt nó vào
    `spec.capabilities`, còn `load_registry` thì không — nên đọc từ bảng gốc
    (`adapters/mt/prompts.PROMPT_VERSION`) thay vì ghi "unknown" vào artifact."""
    return str(PROMPT_VERSION.get(spec.id, "unknown"))


def run(transcript: pathlib.Path, glossary: pathlib.Path, out_dir: pathlib.Path,
        positions: list[int] | None, label: str | None = None, *,
        engine_id: str = ENGINE_ID,
        batch_items: int | None = None) -> dict:
    terms = _load_terms(glossary)
    segments = _load_segments(transcript, positions)
    spec, engine = _engine_and_capabilities(engine_id)
    recorder = _RecordingEngine(engine)
    prompt_version = _prompt_version(spec)
    repos = _InMemoryRepos(segments, terms, engine=spec.id,
                           prompt_version=prompt_version)
    handler = TranslateHandler(
        repos, {spec.id: recorder},
        engine_capabilities={spec.id: dict(spec.capabilities)},
        # `batch_items=None` = THEO ENGINE, đúng như composition root: handler đọc
        # `capabilities.max_items_per_call` của registry (`hy-mt-1.5-7b` khai 1 vì
        # đo được 0/115 đoạn echo ở lô 1 so với 90/115 ở lô 30). Truyền một số cụ
        # thể thì số đó THẮNG capability — đó là đường dùng để QUÉT các lô khác,
        # và nó không đổi mặc định của sản phẩm.
        batch_items=batch_items,
    )
    job = _Job()
    started = time.perf_counter()
    handler.translate(translation_id=1, transcript_id=1, engine_id=spec.id,
                      source_lang="zh", target_lang="vi", job=job,
                      report=lambda _progress, line: print(line, flush=True))
    seconds = round(time.perf_counter() - started, 2)

    source = {s.i: s.text for s in segments}
    received = recorder.received
    out = repos._translation.segments

    planned = plan_terms(terms, source_lang="zh")
    sentences: list[dict] = []
    flags = {flag: 0 for flag in FLAGS}
    inserted = 0
    group_with = 0
    group_without = 0
    byte_identical_ok = True
    for segment in out:
        sent = received.get(segment.i, source.get(segment.i, ""))
        tokens = _TOKEN_IN_TEXT.findall(sent)
        inserted += len(tokens)
        renderings = [term for term in planned if term.term in source.get(segment.i, "")]
        present = {term.translation: term.translation in segment.text
                   for term in renderings}
        for flag in FLAGS:
            if flag in segment.qa:
                flags[flag] += 1
        if tokens:
            group_with += 1
        else:
            group_without += 1
            if sent != source.get(segment.i, ""):
                byte_identical_ok = False
        sentences.append({
            "i": segment.i,
            "zh": source.get(segment.i, ""),
            "received": sent,
            "vi": segment.text,
            "terms": [term.term for term in renderings],
            "tokens": tokens,
            "rendering_present_verbatim": present,
            "qa": list(segment.qa),
        })

    result = {
        "experiment": "term-placeholder-smoke",
        "engine": spec.id,
        "model_ref": spec.model_ref,
        "prompt_version": prompt_version,
        "capabilities": dict(spec.capabilities),
        "transcript": str(transcript),
        "glossary": [[t.term, t.translation] for t in terms],
        "positions": positions,
        "segments": len(segments),
        #: Trần số mục của MỘT lời gọi engine — chép vào artifact để lần chạy sau
        #: không phải suy từ code lúc đó (mặc định đã đổi một lần trong dự án).
        "batch_items": batch_items,
        "seconds": seconds,
        "tokens_inserted": inserted,
        "flags": flags,
        "group_with_tokens": group_with,
        "group_without_tokens": group_without,
        "group_without_tokens_byte_identical": byte_identical_ok,
        "translation_status": repos.status,
        "qa_issues": repos.qa_issues,
        "llm_calls": len(repos.llm_calls),
        "sentences": sentences,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "smoke.json" if positions else f"{label or 'clip'}.json"
    (out_dir / name).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="smoke_term_placeholder.py")
    parser.add_argument("--transcript", type=pathlib.Path, required=True)
    parser.add_argument("--glossary", type=pathlib.Path, required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--positions", type=int, nargs="+", default=None,
                        help="vị trí mảng của các câu cần dịch (bỏ trống = cả clip)")
    parser.add_argument("--label", default=None,
                        help="tên tệp kết quả khi chạy cả clip (mặc định `clip`)")
    parser.add_argument("--engine", default=ENGINE_ID,
                        help=f"id engine trong registry.json (mặc định {ENGINE_ID}); "
                             "`opus-mt` chạy in-process trên CPU")
    parser.add_argument("--batch-items", type=int, default=None,
                        help="trần SỐ MỤC của một lời gọi engine, chính là tham số "
                             "`batch_items` của TranslateHandler; bỏ trống = THEO "
                             "ENGINE (`capabilities.max_items_per_call`, mặc định "
                             f"{DEFAULT_MAX_ITEMS})")
    args = parser.parse_args(argv)

    result = run(args.transcript, args.glossary, args.out_dir, args.positions,
                 args.label, engine_id=args.engine, batch_items=args.batch_items)
    print("")
    print(f"engine {result['engine']} ({result['model_ref']}) · "
          f"{result['segments']} đoạn · {result['seconds']} s · "
          f"{result['llm_calls']} lời gọi · lô tối đa {result['batch_items']} mục")
    print(f"token đã chèn: {result['tokens_inserted']} · cờ: {result['flags']}")
    print(f"nhóm CÓ token: {result['group_with_tokens']} · "
          f"nhóm KHÔNG có token: {result['group_without_tokens']} "
          f"(byte-identical: {result['group_without_tokens_byte_identical']})")
    print("")
    for sentence in result["sentences"]:
        print(f"[{sentence['i']}] {sentence['vi']}")
    print("")
    print(f"đã ghi {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
