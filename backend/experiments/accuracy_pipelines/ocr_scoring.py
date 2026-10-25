from __future__ import annotations

import unicodedata

from .metrics import err_breakdown


def _normalize(text: str, converter=None) -> str:
    text = unicodedata.normalize("NFKC", converter.convert(text) if converter else text)
    return "".join(char for char in text
                   if not char.isspace() and not unicodedata.category(char).startswith("P"))


def best_substring(reference: str, hypothesis: str, *, converter=None,
                   tolerance: int = 3) -> dict[str, int | float]:
    ref, hyp = _normalize(reference, converter), _normalize(hypothesis, converter)
    if not ref:
        return err_breakdown(ref, "")
    low, high = max(1, len(ref) - tolerance), min(len(hyp), len(ref) + tolerance)
    best = None
    for length in range(low, high + 1):
        for start in range(len(hyp) - length + 1):
            score = err_breakdown(ref, hyp[start:start + length])
            key = (score["errors"], abs(length - len(ref)))
            if best is None or key < best[0]:
                best = key, score
    if best is not None:
        return best[1]
    return err_breakdown(ref, "")


def _summarize(rows: list[dict], key: str) -> dict:
    values = [row[key] for row in rows]
    n = len(values)
    refs = sum(row["reference_chars"] for row in values)
    errors = sum(row["errors"] for row in values)
    return {
        "n": n,
        "del": sum(row["del"] for row in values),
        "sub": sum(row["sub"] for row in values),
        "ins": sum(row["ins"] for row in values),
        "errors": errors,
        "reference_chars": refs,
        "pooled_cer": errors / refs if refs else 0.0,
        "mean_cer": sum(row["cer"] for row in values) / n if n else 0.0,
    }


def per_caption_rows(observations: list[dict], segments: list[dict], *,
                     opencc=None, window_seconds: float = 2.0,
                     tolerance: int = 3) -> list[dict]:
    """MỘT hàng cho mỗi caption, giữ cả `global` lẫn `timed`.

    Tách khỏi `score_caption_observations` để phép so THEO CẶP (paired bootstrap)
    dùng ĐÚNG các con số mà bảng điểm dùng: nếu nơi tính CI tự dựng lại cửa sổ
    ±2 s thì hai chỗ có thể chọn hai tập caption khác nhau, và CI sẽ nói về một
    phép so khác với bảng điểm.

    Caption có OCR chuẩn hoá dưới 4 ký tự bị loại — ngưỡng này là của bảng điểm,
    nên nó nằm ở đây, một chỗ duy nhất.
    """
    refs = [item for item in observations
            if len(_normalize(str(item.get("ocr", "")), opencc)) >= 4]
    global_text = "".join(str(segment.get("text", "")) for segment in segments)
    rows: list[dict] = []
    for item in refs:
        midpoint = (float(item["start"]) + float(item["end"])) / 2
        nearby = [segment for segment in segments
                  if float(segment.get("end", 0)) >= midpoint - window_seconds
                  and float(segment.get("start", 0)) <= midpoint + window_seconds]
        timed = "".join(str(segment.get("text", "")) for segment in nearby)
        rows.append({
            "global": best_substring(item["ocr"], global_text,
                                     converter=opencc, tolerance=tolerance),
            "timed": best_substring(item["ocr"], timed,
                                    converter=opencc, tolerance=tolerance),
        })
    return rows


def score_caption_observations(observations: list[dict], segments: list[dict], *,
                              opencc=None, window_seconds: float = 2.0,
                              tolerance: int = 3) -> dict:
    """Score same OCR refs globally and within ±window_seconds of each midpoint."""
    rows = per_caption_rows(observations, segments, opencc=opencc,
                            window_seconds=window_seconds, tolerance=tolerance)
    return {
        "normalization": "OpenCC t2s; NFKC; strip whitespace and Unicode punctuation",
        "window_seconds": window_seconds,
        "substring_length_tolerance": tolerance,
        "global": _summarize(rows, "global"),
        "timed": _summarize(rows, "timed"),
    }
