"""Đo các BIẾN THỂ PROMPT cho `hy-mt-1.5-7b` bằng SỐ ĐOẠN ECHO, cùng 115 đoạn.

Vì sao phải là một tệp riêng chứ không phải `sweep_mt_batch.py`: tệp kia đi qua
ĐÚNG đường ship (`TranslateHandler`), mà đường ship chỉ có MỘT prompt. Ở đây thứ
được thay đổi CHÍNH LÀ prompt, nên phép đo phải đứng ngoài đường đó — và vì vậy
nó cũng phải nói rõ mình đứng ngoài ở đâu: ba biến thể dạng dòng (`zh-lines`,
`zh-two-col`, `native-one`) cần TẮT `format: "json"` của adapter (đoạn văn xuôi bị
ép vào JSON thì không còn là văn xuôi), tức muốn ship biến thể đó thì
`OllamaMtEngine.chat` phải có thêm một tham số — việc đó chỉ nên làm SAU khi có số
đo ở đây.

Cái được đo, và chỉ cái đó: **số đoạn `is_echo`** (`app/domain/mt_qa.py`) trên
cùng 115 đoạn, cùng model, cùng `keep_alive`. Không chấm chất lượng bản dịch ở
đây — một biến thể echo = 0 vẫn có thể dịch dở; nó chỉ chứng minh model ĐÃ dịch.

Nguồn của mẫu prompt: model card chính thức của Hunyuan-MT-7B
(`huggingface.co/tencent/Hunyuan-MT-7B`) —

    把下面的文本翻译成<target_language>，不要额外解释。

    <source_text>

và model card ghi rõ "our model does not have the default system_prompt", nên
biến thể `zh-*` đặt chỉ dẫn vào LƯỢT NGƯỜI DÙNG và để system rỗng. Model card
cũng khuyến nghị `temperature 0.7 / top_k 20 / top_p 0.6 /
repetition_penalty 1.05`, trong khi adapter đang gửi `temperature 0.1` — biến thể
`native-one-card` đo xem bộ tham số đó có cắt được vòng chép nguồn không.

Ví dụ:
    python -B scripts\\sweep_prompt_variants.py --batch 30 \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\...\\prompts
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

import httpx  # noqa: E402 - sau sys.path

from app.adapters.mt.prompts import (parse_batch_response, system_prompt,  # noqa: E402
                                     user_prompt)
from app.domain.models import Segment  # noqa: E402
from app.domain.mt_qa import is_echo  # noqa: E402

MODEL = "hy-mt1.5-7b:q4_K_M"
BASE_URL = "http://127.0.0.1:11434"
KEEP_ALIVE = "30m"
#: Tham số của adapter (`ollama_mt._TEMPERATURE`) — mốc so sánh.
ADAPTER_OPTIONS = {"temperature": 0.1}
#: Tham số model card khuyến nghị cho Hunyuan-MT-7B.
CARD_OPTIONS = {"temperature": 0.7, "top_k": 20, "top_p": 0.6,
                "repetition_penalty": 1.05}
TARGET = "越南语"
_TWO_COL = re.compile(r"^\s*(\d+)\s*[|｜]\s*(.*)$")


def _chat(user: str, *, system: str = "", fmt: str | None,
          options: dict) -> tuple[str, float]:
    body = {
        "model": MODEL, "stream": False, "keep_alive": KEEP_ALIVE,
        "options": dict(options),
        "messages": ([{"role": "system", "content": system}] if system else [])
                    + [{"role": "user", "content": user}],
    }
    if fmt is not None:
        body["format"] = fmt
    data = httpx.post(f"{BASE_URL}/api/chat", json=body, timeout=120).json()
    return (data["message"]["content"], data["total_duration"] / 1e9)


def _chunks(items: list[Segment], size: int) -> list[list[Segment]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _parse_json(content: str, batch: list[Segment]) -> tuple[list[Segment], str | None]:
    try:
        return parse_batch_response(content, batch), None
    except Exception as exc:            # noqa: BLE001 - đây là phép ĐO, không phải sản phẩm
        return [], f"{type(exc).__name__}: {exc}"


def _parse_lines(content: str, batch: list[Segment]) -> tuple[list[Segment], str | None]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    lines = [re.sub(r"^\d+[.、)]\s*", "", line) for line in lines]
    if len(lines) != len(batch):
        return [], f"trả {len(lines)} dòng, cần {len(batch)}"
    return [Segment(i=s.i, start=s.start, end=s.end, text=t)
            for s, t in zip(batch, lines)], None


def _parse_two_col(content: str,
                   batch: list[Segment]) -> tuple[list[Segment], str | None]:
    got: dict[int, str] = {}
    for line in content.splitlines():
        match = _TWO_COL.match(line)
        if match:
            got[int(match.group(1))] = match.group(2).strip()
    missing = [s.i for s in batch if not got.get(s.i)]
    if missing:
        return [], f"thiếu id {missing[:5]} ({len(missing)}/{len(batch)})"
    return [Segment(i=s.i, start=s.start, end=s.end, text=got[s.i])
            for s in batch], None


def _parse_plain(content: str, batch: list[Segment]) -> tuple[list[Segment], str | None]:
    text = content.strip()
    if not text:
        return [], "rỗng"
    return [Segment(i=batch[0].i, start=batch[0].start, end=batch[0].end,
                    text=text)], None


# --- bốn biến thể prompt cho CẢ LÔ, một biến thể cho TỪNG ĐOẠN -----------------

def v_p2_json(batch: list[Segment], options: dict):
    content, secs = _chat(user_prompt(batch, source_lang="zh", target_lang="vi"),
                          system=system_prompt([], target_lang="vi"),
                          fmt="json", options=options)
    out, err = _parse_json(content, batch)
    return out, err, secs


def v_zh_json(batch: list[Segment], options: dict):
    items = json.dumps([{"i": s.i, "text": s.text} for s in batch], ensure_ascii=False)
    user = (f"把下面的文本翻译成{TARGET}，不要额外解释。\n"
            f'按 {{"translations": [{{"i": <số>, "text": "<译文>"}}]}} 返回，i 保持不变。\n'
            f"数据: {items}")
    content, secs = _chat(user, fmt="json", options=options)
    out, err = _parse_json(content, batch)
    return out, err, secs


def v_zh_lines(batch: list[Segment], options: dict):
    user = (f"把下面的文本翻译成{TARGET}，不要额外解释。\n"
            "每行翻译一条，按原顺序输出，不要编号，不要添加任何其他内容。\n\n"
            + "\n".join(s.text for s in batch))
    content, secs = _chat(user, fmt=None, options=options)
    out, err = _parse_lines(content, batch)
    return out, err, secs


def v_zh_two_col(batch: list[Segment], options: dict):
    user = (f"把下面的文本翻译成{TARGET}，不要额外解释。\n"
            "每行输出 `<i> | <译文>`，i 原样保留，不要添加任何其他内容。\n\n"
            + "\n".join(f"{s.i} | {s.text}" for s in batch))
    content, secs = _chat(user, fmt=None, options=options)
    out, err = _parse_two_col(content, batch)
    return out, err, secs


def v_native_one(batch: list[Segment], options: dict):
    content, secs = _chat(f"把下面的文本翻译成{TARGET}，不要额外解释。\n\n"
                          f"{batch[0].text}", fmt=None, options=options)
    out, err = _parse_plain(content, batch)
    return out, err, secs


VARIANTS = {
    "p2-json": (v_p2_json, ADAPTER_OPTIONS, "đường ship hiện tại (đối chứng)"),
    "zh-json": (v_zh_json, ADAPTER_OPTIONS, "chỉ dẫn model card, vẫn JSON"),
    "zh-lines": (v_zh_lines, ADAPTER_OPTIONS, "chỉ dẫn model card, mỗi dòng một câu"),
    "zh-two-col": (v_zh_two_col, ADAPTER_OPTIONS, "chỉ dẫn model card, dạng `i | câu`"),
    "native-one": (v_native_one, ADAPTER_OPTIONS, "model card, MỘT đoạn mỗi lời gọi"),
    "native-one-card": (v_native_one, CARD_OPTIONS,
                        "model card + tham số model card (t=0,7, top_k 20…)"),
}


def run_variant(name: str, items: list[Segment], batch: int) -> dict:
    fn, options, note = VARIANTS[name]
    size = 1 if name.startswith("native-one") else batch
    started = time.perf_counter()
    translated: list[Segment] = []
    errors: list[str] = []
    calls = 0
    for chunk in _chunks(items, size):
        calls += 1
        try:
            out, err, _secs = fn(chunk, options)
        except Exception as exc:        # noqa: BLE001 - đây là phép ĐO
            # Một lời gọi TIMEOUT/HTTP hỏng là một KẾT QUẢ, không phải lý do để
            # mất cả bảng: biến thể `zh-json` đã đo được ca này (model sinh mãi
            # không dừng, httpx ReadTimeout) — dừng biến thể đó tại đây và ghi
            # lại lý do, thay vì đổ cả lượt đo.
            errors.append(f"lô bắt đầu {chunk[0].i}: {type(exc).__name__}: {exc}")
            break
        if err:
            errors.append(f"lô bắt đầu {chunk[0].i}: {err}")
            continue
        translated.extend(out)
    seconds = round(time.perf_counter() - started, 2)

    by_id = {s.i: s for s in items}
    echoed = [s.i for s in translated if is_echo(by_id[s.i].text, s.text)]
    han = sum(len(re.findall(r"[\u4e00-\u9fff]", s.text)) for s in translated)
    return {
        "variant": name,
        "note": note,
        "batch_items": size,
        "options": options,
        "seconds": seconds,
        "calls": calls,
        "translated": len(translated),
        "missing": len(items) - len(translated),
        "echo_ids": echoed,
        "echo": len(echoed),
        "han_chars": han,
        "errors": errors[:5],
        "texts": {str(s.i): s.text for s in translated},
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="sweep_prompt_variants.py")
    parser.add_argument("--transcript", type=pathlib.Path, required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--batch", type=int, default=30)
    parser.add_argument("--variants", nargs="+", default=list(VARIANTS))
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    raw = json.loads(args.transcript.read_text(encoding="utf-8"))
    segments = raw["segments"] if isinstance(raw, dict) else raw
    items = [Segment(i=position, start=float(item["start"]),
                     end=float(item["end"]), text=str(item["text"]))
             for position, item in enumerate(segments)]
    print(f"{len(items)} đoạn · lô {args.batch} · model {MODEL}", flush=True)

    results = []
    for name in args.variants:
        result = run_variant(name, items, args.batch)
        results.append(result)
        path = args.out_dir / f"{name}.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"[{name:16}] {result['seconds']:>7} s · {result['calls']:>3} lời gọi · "
              f"echo {result['echo']:>3}/{len(items)} · Hán {result['han_chars']:>4} · "
              f"thiếu {result['missing']}"
              + (f" · LỖI {result['errors'][0]}" if result["errors"] else ""),
              flush=True)

    (args.out_dir / "summary.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "texts"} for r in results],
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nđã ghi {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
