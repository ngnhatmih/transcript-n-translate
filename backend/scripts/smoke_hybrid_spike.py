"""Spike ĐO: thiết kế "hybrid" rẻ hay đắt — đo TỈ LỆ đoạn phải dịch lại.

Câu hỏi
    Thiết kế được đề xuất: `opus-mt` dịch CẢ clip, rồi CHỈ những đoạn bị QA gắn
    cờ mới được `hy-mt` dịch lại từng đoạn một. Chi phí của thiết kế đó tỉ lệ với
    TỈ LỆ ĐOẠN BỊ GẮN CỜ, nên câu hỏi phải trả lời trước khi ai viết engine
    hybrid là: tỉ lệ đó bằng bao nhiêu, và giá thật là bao nhiêu giây.

Hai định nghĩa, và vì sao phải có hai
    * RỘNG — "đoạn cần `hy-mt`": bản dịch của `opus-mt` còn CHỮ HÁN (`lang:`) hoặc
      RỖNG (`empty:`) hoặc VI PHẠM GLOSSARY (`missing_term:`). Đây là định nghĩa
      của đề bài, và là bộ đoạn mà một engine hybrid sẽ đẩy sang `hy-mt`.
    * CHẶT — "chỉ cái `hy-mt` SỬA ĐƯỢC": còn chữ Hán hoặc rỗng. `cps:` (quá nhanh)
      và `length:` (quá dài/ngắn) là lỗi HÌNH DẠNG: `hy-mt` không biết cửa sổ thời
      gian của phụ đề và không bị ràng buộc bởi nó, nên dịch lại chỉ đổi chữ chứ
      không sửa được số đo — xếp chúng vào "cần hy-mt" là thổi phồng chi phí bằng
      những đoạn mà lần dịch thứ hai không có cơ chế nào để làm đúng hơn.
    Hai định nghĩa trả lời hai câu khác nhau, và bộ luật quyết định (bên dưới) đặt
    ngưỡng trên HAI con số khác nhau — nên cả hai phải được đo, không phải chọn.

Vì sao không có harness thứ hai
    Mỗi lượt đi qua `TranslateHandler` của sản phẩm, qua ĐÚNG
    `smoke_term_placeholder.run()` — tệp này chỉ gọi nó hai lần và cộng số. Không
    có driver thứ hai gọi thẳng `engine.translate`: một driver như vậy bỏ qua
    batching, alignment, bảo vệ thuật ngữ và `echo_guard`, tức là đo một đường
    ống khác với đường được hỏi. Hệ quả có ích: lượt `hy-mt` ở pha B dùng
    `capabilities.max_items_per_call = 1` của registry, nên "dịch lại từng đoạn
    một" là hành vi CỦA SẢN PHẨM chứ không phải một vòng lặp của kịch bản — nếu
    registry đổi số đó thì phép đo đổi theo và artifact ghi lại số đã dùng.

Vì sao phải GỌI LẠI `qa_translation` cho phép kiểm glossary
    `opus-mt` khai `glossary_prompt: false`, nên `qa_translation` báo MỘT issue
    cấp lượt `engine_no_glossary` và BỎ QUA phép kiểm `missing_term:` từng đoạn
    (nhánh `if supports_glossary:`). Đó là hành vi ĐÚNG của sản phẩm — một engine
    không nhận được ràng buộc thì không bị buộc tội vi phạm nó — nhưng nó có nghĩa
    là "đoạn bị glossary gắn cờ" KHÔNG tồn tại trong `qa_issues` của lượt
    `opus-mt`. Vì vậy pha A hỏi lại CHÍNH hàm đó với `supports_glossary=True` trên
    cùng đầu ra, và chỉ lấy các issue `missing_term:` từ lần hỏi thứ hai. Không
    viết lại phép so thuật ngữ ở đây: hai bản cài của cùng một luật là hai chỗ để
    trôi khỏi nhau, và bản thứ hai sẽ không được test nào canh.

Số đo (clip 115 đoạn `20261019-name-patch-smoke/large-v3-beam5-prevfalse.json`,
5 thuật ngữ `20261019-term-placeholder-smoke/glossary.json`; artifact ở
`data/experiments/accuracy-pipelines/20261019-hybrid-spike/`): xem
`hybrid-spike.json` — tệp đó là nguồn số, không phải docstring này. Bảng in ra ở
cuối lượt chạy có cùng các con số.

Bộ luật quyết định — ĐÃ ĐẶT TRƯỚC, và tệp này CHỈ BÁO, KHÔNG HÀNH ĐỘNG
    * RỘNG > ~20 % -> hybrid đắt, phải xem lại kế hoạch.
    * CHẶT < ~10 % -> hybrid rẻ, thiết kế (2.2) đi tiếp được trên cơ sở đó.
    Hai luật có thể cùng bắn (RỘNG 25 %, CHẶT 8 %): khi đó hai ngưỡng nói ngược
    nhau và việc của spike là PHƠI RA chuyện đó, không phải chọn hộ.

Ví dụ (một lệnh, không tham số — mặc định đã trỏ đúng clip/glossary/out-dir):
    python -B scripts\\smoke_hybrid_spike.py

    python -B scripts\\smoke_hybrid_spike.py \\
        --transcript ..\\data\\experiments\\accuracy-pipelines\\20261019-name-patch-smoke\\large-v3-beam5-prevfalse.json \\
        --glossary ..\\data\\experiments\\accuracy-pipelines\\20261019-term-placeholder-smoke\\glossary.json \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\20261019-hybrid-spike

Không thuộc bộ pytest: cần Ollama + model thật (~5,3 GB VRAM) và `opus-mt` nạp
trong tiến trình. Không sửa gì của sản phẩm: không đổi `default_mt`, không đổi
`DEFAULT_MAX_ITEMS`/`PROMPT_VERSION`, không sửa prompt/registry/module nào.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from collections import Counter
from dataclasses import replace

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import smoke_echo_guard as guard          # noqa: E402 - sau sys.path
import smoke_term_placeholder as smoke    # noqa: E402 - sau sys.path

from app.domain.models import Segment              # noqa: E402
from app.domain.mt_qa import QaLimits, qa_translation  # noqa: E402

#: Hai engine của phép đo này, đều là id trong `registry.json`. Cố ý KHÔNG tham số
#: hoá bằng cờ CLI: câu hỏi của spike là "opus-mt cả clip + hy-mt cho các đoạn bị
#: gắn cờ", nên đổi engine là một câu hỏi khác chứ không phải một tuỳ chọn.
ENGINE_OPUS = "opus-mt"
ENGINE_HY = "hy-mt-1.5-7b"

#: Đường dẫn mặc định — để "một lệnh, không tham số" là tái lập được.
DEFAULT_TRANSCRIPT = (BACKEND_DIR.parent / "data" / "experiments" / "accuracy-pipelines"
                      / "20261019-name-patch-smoke" / "large-v3-beam5-prevfalse.json")
DEFAULT_GLOSSARY = (BACKEND_DIR.parent / "data" / "experiments" / "accuracy-pipelines"
                    / "20261019-term-placeholder-smoke" / "glossary.json")
DEFAULT_OUT_DIR = (BACKEND_DIR.parent / "data" / "experiments" / "accuracy-pipelines"
                   / "20261019-hybrid-spike")

#: Issue CẤP ĐOẠN của `qa_translation`, dạng `<mã>:<i>` rồi `=` hoặc hết chuỗi.
#:
#: `(?==|$)` là bắt buộc, không phải cho đẹp: `echo:<n>/<m>` là issue CẤP LƯỢT do
#: `TranslateHandler` thêm sau `qa_translation`, và `echo:89/115` khớp `echo:\d+`
#: nếu không có ràng buộc ký tự kế tiếp — nó sẽ bị đọc thành "đoạn 89" và làm
#: phép đếm sai đúng ở lượt tệ nhất. `echo` cũng vì thế không nằm trong tập mã
#: dưới đây: nó không phải issue của `qa_translation`.
_SEGMENT_ISSUE = re.compile(r"^(lang|cps|length|missing_term|empty):(\d+)(?==|$)")

#: Hai tiền tố mà lần dịch lại bằng model khác CÓ THỂ sửa: dòng còn chữ Hán, dòng
#: rỗng. Đây là định nghĩa CHẶT.
_FIXABLE_ALWAYS = frozenset({"lang", "empty"})
#: Tiền tố glossary — định nghĩa RỘNG cộng thêm nó.
_FIXABLE_GLOSSARY = frozenset({"missing_term"})

#: Tỉ lệ (%) của hai ngưỡng trong bộ luật đã đặt trước. Hằng số ở đây để artifact
#: và bảng in ra KHÔNG thể lệch nhau, và để lần đọc lại thấy đúng ngưỡng đã dùng.
WIDE_THRESHOLD_PCT = 20.0
STRICT_THRESHOLD_PCT = 10.0

#: Thời gian đã đo của các cấu hình so sánh, TRÍCH TỪ artifact trên đĩa (không
#: phải số ước lượng): lô 30 + `echo_guard` sáu lượt 78,91–118,57 s và lô 15 ba
#: lượt 57,72–95,42 s — `docs/superpowers/reports/2026-10-21-echo-guard-ket-qua-am.md`
#: mục 2; `opus-mt` một mình 9,75–11,19 s (ba lô 8/15/30, cùng clip, cùng 5 thuật
#: ngữ: 11,19 / 9,83 / 9,75). Chép vào artifact để bảng so sánh tự đứng một mình,
#: và để lần chạy lại biết con số đối chứng đến từ đâu.
BASELINE_HY_BATCH30 = (78.91, 118.57)
BASELINE_HY_BATCH15 = (57.72, 95.42)
BASELINE_OPUS_ALONE = (9.75, 11.19)


def flags_by_segment(issues: list[str]) -> dict[int, list[str]]:
    """`{id đoạn: [mã issue, ...]}` — chỉ những issue GẮN ĐƯỢC vào một đoạn.

    Issue cấp lượt (`engine_no_glossary`, `echo:<n>/<m>`) bị bỏ qua ở đây nhưng
    vẫn nằm nguyên trong artifact (`qa_issues` của từng pha): chúng không nói
    được "đoạn NÀO phải dịch lại", mà đó là toàn bộ câu hỏi của spike.
    """
    out: dict[int, list[str]] = {}
    for issue in issues:
        match = _SEGMENT_ISSUE.match(str(issue))
        if match is None:
            continue
        out.setdefault(int(match.group(2)), []).append(match.group(1))
    return out


def _glossary_flag_issues(source_segments: list[Segment],
                          sentences: list[dict], terms: list) -> list[str]:
    """Issue của `qa_translation` khi phép kiểm glossary ĐƯỢC BẬT.

    Lý do đầy đủ ở docstring đầu tệp: `opus-mt` không khai `glossary_prompt`, nên
    lượt thật chỉ báo `engine_no_glossary` và bỏ qua `missing_term:`. Hàm này hỏi
    lại ĐÚNG hàm đó trên cùng đầu ra — không so thuật ngữ bằng tay ở đây.

    Hai danh sách phải khớp id và thứ tự (`qa_translation` ghép theo id, nhưng
    `check_alignment` đã bảo đảm thứ tự nên truyền cùng thứ tự là trung thực
    nhất). `replace(...)` giữ nguyên `start`/`end`/`words` của segment NGUỒN: cửa
    sổ thời gian là của phụ đề, không phải của bản dịch (`mt_qa._window`).
    """
    by_id = {s.i: s for s in source_segments}
    src = [by_id[s["i"]] for s in sentences]
    out = [replace(by_id[s["i"]], text=s["vi"]) for s in sentences]
    return qa_translation(src, out, glossary=terms, supports_glossary=True,
                          limits=QaLimits(), target_lang="vi")


def _han(text: str) -> int:
    """Số chữ Hán — CÙNG regex với `han_chars` của artifact `echo_guard`.

    Dùng chung một định nghĩa để cột "chữ Hán" của spike này so được với
    `20261019-echo-guard/batch-30.json` (0) và `20261019-echo-batch15-*` (0).
    """
    return len(guard.HAN.findall(text))


def _codes(issues: list[str]) -> list[str]:
    """Mã issue đã BỎ TRÙNG của một đoạn, giữ thứ tự xuất hiện."""
    seen: list[str] = []
    for issue in issues:
        if issue not in seen:
            seen.append(issue)
    return seen


def measure(transcript: pathlib.Path, glossary: pathlib.Path,
            out_dir: pathlib.Path) -> dict:
    """Chạy hai pha, ghi artifact của từng pha + bản tổng kết, trả bản tổng kết."""
    out_dir.mkdir(parents=True, exist_ok=True)
    terms = smoke._load_terms(glossary)
    source_segments = smoke._load_segments(transcript, None)
    source_text = {s.i: s.text for s in source_segments}

    # ------------------------------------------------------------------ pha A
    # `opus-mt` CẢ clip, không truyền `batch_items`: `None` = THEO ENGINE, và
    # `opus-mt` không khai `max_items_per_call` nên nó dùng `DEFAULT_MAX_ITEMS`
    # = 30 — đúng đường ship. Đây là (a) trong bảng so sánh.
    print("=== pha A · opus-mt · cả clip ===", flush=True)
    started = time.perf_counter()
    opus = smoke.run(transcript, glossary, out_dir / "opus-whole-clip", None,
                     label="whole-clip", engine_id=ENGINE_OPUS)
    opus_wall = round(time.perf_counter() - started, 2)
    print(f"    {opus['segments']} đoạn · {opus['seconds']} s · "
          f"{opus['llm_calls']} lời gọi · trạng thái {opus['translation_status']}",
          flush=True)

    codes_opus = flags_by_segment(opus["qa_issues"])
    # Phép kiểm glossary PHẢI hỏi riêng (xem docstring đầu tệp). Chỉ lấy
    # `missing_term:` từ lần hỏi đó — `lang:`/`cps:`/`length:` của nó là CÙNG dữ
    # liệu với lượt thật, lấy thêm là đếm hai lần.
    glossary_issues = _glossary_flag_issues(source_segments, opus["sentences"], terms)
    codes_glossary = {i: cs for i, cs in flags_by_segment(glossary_issues).items()
                      if any(c in _FIXABLE_GLOSSARY for c in cs)}

    codes: dict[int, list[str]] = {}
    for i in sorted(set(codes_opus) | set(codes_glossary)):
        codes[i] = _codes(codes_opus.get(i, []) + codes_glossary.get(i, []))

    wide_ids = sorted(i for i, cs in codes.items()
                      if any(c in _FIXABLE_ALWAYS or c in _FIXABLE_GLOSSARY
                             for c in cs))
    strict_ids = sorted(i for i, cs in codes.items()
                        if any(c in _FIXABLE_ALWAYS for c in cs))
    total = len(source_segments)
    wide_pct = round(100.0 * len(wide_ids) / total, 1) if total else 0.0
    strict_pct = round(100.0 * len(strict_ids) / total, 1) if total else 0.0

    # Theo TỪNG TIỀN TỐ, trên SỐ ĐOẠN (một đoạn hai cờ cùng tiền tố chỉ tính
    # một): câu hỏi là "bao nhiêu đoạn mang cờ này", không phải "bao nhiêu issue".
    by_prefix = Counter()
    for cs in codes.values():
        for code in set(cs):
            by_prefix[code] += 1
    # ... và số ISSUE THÔ, để thấy chỗ một đoạn bị nhiều thuật ngữ cùng thiếu.
    issues_by_prefix = Counter()
    for issues in (opus["qa_issues"], glossary_issues):
        for issue in issues:
            match = _SEGMENT_ISSUE.match(str(issue))
            if match is not None:
                issues_by_prefix[match.group(1)] += 1

    # ------------------------------------------------------------------ pha B
    # CHỈ các đoạn của định nghĩa RỘNG, qua đúng đường đã ship, `hy-mt`. Trần số
    # mục của engine này là 1 (`capabilities.max_items_per_call`), nên một lời gọi
    # = một đoạn: đó chính là "dịch lại từng đoạn một" của thiết kế hybrid, do
    # registry quyết định chứ không do vòng lặp ở đây.
    hymt = None
    hymt_wall = 0.0
    hymt_error: dict | None = None
    #: `True` khi lượt gộp hỏng và phải chạy lại TỪNG đoạn để vẫn có số. Hỏng ở
    #: đây thường là `EchoProblem`: cổng của sản phẩm từ chối cả lượt khi một đoạn
    #: vẫn chép nguyên chữ nguồn sau khi dịch lại — nghĩa là chính thiết kế hybrid
    #: không đóng được vòng cho đoạn đó, và đó là phát hiện, không phải sự cố.
    hymt_fallback = False
    hy_text: dict[int, str] = {}
    #: `hy-mt` có đang nằm trong VRAM TRƯỚC pha B không: `keep_alive` 30 phút giữ
    #: model sau lượt trước, nên nếu có thì thời gian nạp model đã KHÔNG được tính
    #: vào `seconds` của pha B — người đọc artifact phải thấy điều đó.
    model_loaded_before = guard._loaded_models()
    if wide_ids:
        print(f"=== pha B · hy-mt · {len(wide_ids)} đoạn bị gắn cờ "
              f"(một đoạn một lời gọi) ===", flush=True)
        started = time.perf_counter()
        try:
            hymt = smoke.run(transcript, glossary, out_dir / "hymt-flagged-only",
                             wide_ids, engine_id=ENGINE_HY)
        except Exception as exc:      # noqa: BLE001 - spike phải BÁO, không được chết
            hymt_error = {"type": type(exc).__name__, "message": str(exc)}
            print(f"    lượt gộp hỏng: {type(exc).__name__}: {exc}", flush=True)
        hymt_wall = round(time.perf_counter() - started, 2)
        if hymt is not None:
            for sentence in hymt["sentences"]:
                hy_text[sentence["i"]] = sentence["vi"]
        else:
            # Đường dự phòng: TỪNG đoạn một, mỗi đoạn một thư mục artifact riêng
            # (tên tệp của `smoke.run` khi có `positions` là cố định `smoke.json`,
            # nên không tách thư mục thì chúng ghi đè nhau). Tổng thời gian cộng
            # dồn từ chính `seconds` của từng lượt — cùng đại lượng với pha A.
            hymt_fallback = True
            per_segment: list[dict] = []
            started = time.perf_counter()
            for position in wide_ids:
                try:
                    one = smoke.run(transcript, glossary,
                                    out_dir / "hymt-flagged-only" / f"single-{position}",
                                    [position], engine_id=ENGINE_HY)
                except Exception as exc:  # noqa: BLE001 - một đoạn hỏng không được
                    # làm mất số của các đoạn còn lại
                    per_segment.append({"i": position, "seconds": None,
                                        "error": f"{type(exc).__name__}: {exc}"})
                    print(f"    đoạn {position}: {type(exc).__name__}", flush=True)
                    continue
                hy_text[position] = one["sentences"][0]["vi"]
                per_segment.append({"i": position, "seconds": one["seconds"],
                                    "qa_issues": one["qa_issues"]})
            hymt_wall = round(time.perf_counter() - started, 2)
            hymt = {"fallback_per_segment": per_segment}
        print(f"    {len(hy_text)}/{len(wide_ids)} đoạn có bản dịch mới · "
              f"{hymt_wall} s (tường)", flush=True)

    # Thời gian của pha B: `seconds` của handler khi lượt gộp chạy được, còn nếu
    # phải chạy từng đoạn thì cộng `seconds` của từng lượt — hai cách đều là thời
    # gian handler, không phải thời gian tường của kịch bản.
    if hymt is not None and "seconds" in hymt:
        hymt_seconds = hymt["seconds"]
        hymt_calls = hymt.get("llm_calls")
        hymt_status = hymt.get("translation_status")
    elif hymt is not None:
        per_turn = [row["seconds"] for row in hymt["fallback_per_segment"]
                    if row.get("seconds") is not None]
        hymt_seconds = round(sum(per_turn), 2)
        hymt_calls = sum(1 for row in hymt["fallback_per_segment"]
                         if row.get("seconds") is not None)
        hymt_status = None
    else:
        hymt_seconds = 0.0
        hymt_calls = 0
        hymt_status = None

    hybrid_seconds = round(opus["seconds"] + hymt_seconds, 2)
    hybrid_wall = round(opus_wall + hymt_wall, 2)

    # Chữ Hán và cờ `lang:` TRƯỚC/SAU trên đúng tập đoạn bị gắn cờ — phép so duy
    # nhất trả lời được "dịch lại có sửa được không".
    han_opus_flagged = sum(_han(s["vi"]) for s in opus["sentences"]
                           if s["i"] in set(wide_ids))
    han_after_flagged = sum(_han(text) for text in hy_text.values())
    lang_after = 0
    if hymt is not None and hymt.get("qa_issues"):
        lang_after = sum(1 for issue in hymt["qa_issues"]
                         if str(issue).startswith("lang:"))
    elif hymt is not None:
        for row in hymt["fallback_per_segment"]:
            lang_after += sum(1 for issue in row.get("qa_issues") or []
                              if str(issue).startswith("lang:"))

    segments: list[dict] = []
    for sentence in opus["sentences"]:
        i = sentence["i"]
        own = codes.get(i, [])
        segments.append({
            "i": i,
            "zh": source_text.get(i, ""),
            "vi_opus": sentence["vi"],
            "qa_codes": own,
            "needs_hy_wide": i in wide_ids,
            "needs_hy_strict": i in strict_ids,
            "han_opus": _han(sentence["vi"]),
            "vi_hy": hy_text.get(i),
            "han_hy": _han(hy_text[i]) if i in hy_text else None,
        })

    summary = {
        "experiment": "hybrid-spike",
        "note": ("Spike ĐO, không phải mã sản phẩm: đo tỉ lệ đoạn mà thiết kế "
                 "hybrid (opus-mt cả clip + hy-mt cho đoạn bị QA gắn cờ) phải "
                 "dịch lại, và giá thật của nó. Mọi lượt đi qua "
                 "`smoke_term_placeholder.run()` tức `TranslateHandler` đã ship."),
        "transcript": str(transcript),
        "glossary": [[t.term, t.translation] for t in terms],
        "segments": total,
        "definitions": {
            "wide": {
                "rule": ("đoạn mà bản dịch `opus-mt` còn chữ Hán (`lang:`) hoặc "
                         "rỗng (`empty:`) hoặc vi phạm glossary (`missing_term:`)"),
                "ids": wide_ids,
                "count": len(wide_ids),
                "total": total,
                "percent": wide_pct,
            },
            "strict": {
                "rule": ("đoạn còn chữ Hán (`lang:`) hoặc rỗng (`empty:`) — "
                         "`cps:`/`length:` là lỗi HÌNH DẠNG mà dịch lại không sửa được"),
                "ids": strict_ids,
                "count": len(strict_ids),
                "total": total,
                "percent": strict_pct,
            },
        },
        "flags": {
            #: Số ĐOẠN mang ít nhất một cờ của tiền tố này.
            "segments_by_prefix": dict(sorted(by_prefix.items())),
            #: Số ISSUE thô (một đoạn thiếu hai thuật ngữ = 2).
            "issues_by_prefix": dict(sorted(issues_by_prefix.items())),
            #: Issue cấp lượt, không gắn được vào đoạn nào — giữ nguyên văn.
            "run_level": [str(issue) for issue in opus["qa_issues"]
                          if _SEGMENT_ISSUE.match(str(issue)) is None],
            #: Cờ glossary lấy từ lần hỏi lại `qa_translation` với
            #: `supports_glossary=True` (xem docstring): lượt thật của `opus-mt`
            #: KHÔNG có `missing_term:` vì engine không nhận glossary qua prompt.
            "glossary_probe_issues": [str(issue) for issue in glossary_issues
                                      if str(issue).startswith("missing_term:")],
        },
        "phases": {
            "opus_whole_clip": {
                "engine": opus["engine"],
                "model_ref": opus["model_ref"],
                "batch_items": opus["batch_items"],
                "segments": opus["segments"],
                #: Thời gian TƯỜNG của lời gọi handler — cùng đại lượng với cột
                #: `seconds` của mọi artifact `echo_guard` (nên so được với
                #: 78,91–118,57 s), cộng `wall_seconds` bao cả việc dựng adapter.
                "seconds": opus["seconds"],
                "wall_seconds": opus_wall,
                "llm_calls": opus["llm_calls"],
                "translation_status": opus["translation_status"],
                "han_chars": sum(_han(s["vi"]) for s in opus["sentences"]),
                "qa_lang": sum(1 for issue in opus["qa_issues"]
                               if str(issue).startswith("lang:")),
                "qa_issues": [str(issue) for issue in opus["qa_issues"]],
            },
            "hymt_flagged_only": {
                "engine": ENGINE_HY,
                "batch_items": (hymt or {}).get("batch_items"),
                "max_items_per_call": ((hymt or {}).get("capabilities") or {}
                                       ).get("max_items_per_call"),
                "flagged": len(wide_ids),
                "seconds": hymt_seconds,
                "wall_seconds": hymt_wall,
                "llm_calls": hymt_calls,
                "translation_status": hymt_status,
                "translated": len(hy_text),
                "failed": len(wide_ids) - len(hy_text),
                "fallback_per_segment": hymt_fallback,
                "model_loaded_before": model_loaded_before,
                "error": hymt_error,
            },
        },
        "han_residue": {
            "flagged_segments": len(wide_ids),
            "before": han_opus_flagged,
            "after": han_after_flagged,
            "qa_lang_before": by_prefix.get("lang", 0),
            "qa_lang_after": lang_after,
        },
        "cost": {
            "opus_whole_clip_seconds": opus["seconds"],
            "hymt_flagged_seconds": hymt_seconds,
            #: Ước lượng hybrid = opus cả clip + hy-mt trên các đoạn bị gắn cờ.
            #: KHÔNG gồm phép kiểm QA (tất định, không model) và không gồm chi phí
            #: đổi model trong VRAM nếu sản phẩm phải nạp/đổ hai model luân phiên
            #: (đo riêng: `20261019-vram-sample`).
            "hybrid_estimate_seconds": hybrid_seconds,
            "hybrid_estimate_wall_seconds": hybrid_wall,
            "hymt_seconds_per_flagged_segment": (
                round(hymt_seconds / len(wide_ids), 3) if wide_ids else None),
        },
        "baselines": {
            "opus_alone": BASELINE_OPUS_ALONE,
            "hy_batch30_guard": BASELINE_HY_BATCH30,
            "hy_batch15_guard": BASELINE_HY_BATCH15,
            "source": ("docs/superpowers/reports/2026-10-21-echo-guard-ket-qua-am.md "
                       "mục 2 + artifact 20261019-echo-guard/batch-{15,30}.json"),
        },
        "decision": {
            "preset": "đặt trước, spike CHỈ BÁO — không hành động theo",
            "wide_rule": {
                "threshold_pct": WIDE_THRESHOLD_PCT,
                "measured_pct": wide_pct,
                "fires": wide_pct > WIDE_THRESHOLD_PCT,
                "means": "hybrid đắt -> phải xem lại kế hoạch",
            },
            "strict_rule": {
                "threshold_pct": STRICT_THRESHOLD_PCT,
                "measured_pct": strict_pct,
                "fires": strict_pct < STRICT_THRESHOLD_PCT,
                "means": "hybrid rẻ -> thiết kế (2.2) đi tiếp được trên cơ sở đó",
            },
        },
        "segments_detail": segments,
    }
    (out_dir / "hybrid-spike.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def print_summary(summary: dict) -> None:
    """Bảng kết luận — in ra để đọc được ngay, cùng số với `hybrid-spike.json`."""
    cost = summary["cost"]
    decision = summary["decision"]
    han = summary["han_residue"]
    wide = summary["definitions"]["wide"]
    strict = summary["definitions"]["strict"]
    print("")
    print("| định nghĩa | đoạn bị gắn cờ | /tổng | % |")
    print("|---|---|---|---|")
    print(f"| RỘNG — chữ Hán (`lang:`) HOẶC rỗng (`empty:`) HOẶC glossary "
          f"(`missing_term:`) | {wide['count']} | {wide['total']} | "
          f"{wide['percent']} |")
    print(f"| CHẶT — chữ Hán (`lang:`) HOẶC rỗng (`empty:`) | {strict['count']} | "
          f"{strict['total']} | {strict['percent']} |")
    print("")
    print(f"cờ theo tiền tố (số ĐOẠN): {summary['flags']['segments_by_prefix']}")
    print(f"cờ theo tiền tố (số ISSUE): {summary['flags']['issues_by_prefix']}")
    print(f"issue cấp lượt: {summary['flags']['run_level']}")
    print(f"glossary (hỏi lại với supports_glossary=True): "
          f"{summary['flags']['glossary_probe_issues']}")
    print("")
    print(f"chữ Hán trên {han['flagged_segments']} đoạn bị gắn cờ: "
          f"{han['before']} -> {han['after']} · cờ `lang:` "
          f"{han['qa_lang_before']} -> {han['qa_lang_after']}")
    print("")
    print("| cấu hình | giây |")
    print("|---|---|")
    print(f"| (a) opus-mt cả clip (đo hôm nay) | {cost['opus_whole_clip_seconds']} |")
    print(f"| (a') opus-mt cả clip (đã đo trước) | "
          f"{summary['baselines']['opus_alone'][0]}–"
          f"{summary['baselines']['opus_alone'][1]} |")
    print(f"| hy-mt trên {summary['phases']['hymt_flagged_only']['flagged']} đoạn bị "
          f"gắn cờ (đo hôm nay) | {cost['hymt_flagged_seconds']} |")
    print(f"| **hybrid = (a) + hy-mt trên đoạn cờ** | "
          f"**{cost['hybrid_estimate_seconds']}** |")
    print(f"| (b) hy-mt lô 30 + echo_guard (đã đo) | "
          f"{summary['baselines']['hy_batch30_guard'][0]}–"
          f"{summary['baselines']['hy_batch30_guard'][1]} |")
    print(f"| (c) hy-mt lô 15 + echo_guard (đã đo) | "
          f"{summary['baselines']['hy_batch15_guard'][0]}–"
          f"{summary['baselines']['hy_batch15_guard'][1]} |")
    print("")
    for key, label in (("wide_rule", "RỘNG"), ("strict_rule", "CHẶT")):
        rule = decision[key]
        state = "BẮN" if rule["fires"] else "không bắn"
        print(f"luật {label}: {rule['measured_pct']} % so với ngưỡng "
              f"{rule['threshold_pct']} % -> {state} ({rule['means']})")
    print("")
    print("Bộ luật chỉ được ĐỌC, không được thi hành: spike này không đổi mã sản phẩm.")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="smoke_hybrid_spike.py")
    parser.add_argument("--transcript", type=pathlib.Path, default=DEFAULT_TRANSCRIPT)
    parser.add_argument("--glossary", type=pathlib.Path, default=DEFAULT_GLOSSARY)
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    summary = measure(args.transcript, args.glossary, args.out_dir)
    print_summary(summary)
    print(f"\nđã ghi {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
