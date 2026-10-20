from __future__ import annotations

import random
import unicodedata
from collections import Counter


_PUNCTUATION = str.maketrans({
    "，": ",", "。": ".", "！": "!", "？": "?", "：": ":",
    "；": ";", "、": ",", "“": '"', "”": '"', "‘": "'", "’": "'",
})


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_PUNCTUATION).casefold()
    return "".join(char for char in text
                   if not char.isspace() and not unicodedata.category(char).startswith("P"))


def char_error_rate(reference: str, hypothesis: str) -> float:
    """Character edit distance divided by reference length; empty/empty is exact."""
    ref = _normalized(reference)
    hyp = _normalized(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for row, left in enumerate(ref, start=1):
        current = [row]
        for col, right in enumerate(hyp, start=1):
            current.append(min(
                current[-1] + 1,
                previous[col] + 1,
                previous[col - 1] + (left != right),
            ))
        previous = current
    return previous[-1] / len(ref)


def err_breakdown(reference: str, hypothesis: str) -> dict[str, int | float]:
    """Return CER edit counts using a deterministic minimum-edit alignment."""
    ref, hyp = _normalized(reference), _normalized(hypothesis)
    rows = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        rows[i][0] = i
    for j in range(len(hyp) + 1):
        rows[0][j] = j
    for i, left in enumerate(ref, 1):
        for j, right in enumerate(hyp, 1):
            rows[i][j] = min(rows[i - 1][j] + 1, rows[i][j - 1] + 1,
                             rows[i - 1][j - 1] + (left != right))
    deletions = substitutions = insertions = 0
    i, j = len(ref), len(hyp)
    while i or j:
        if i and j and ref[i - 1] == hyp[j - 1] and rows[i][j] == rows[i - 1][j - 1]:
            i -= 1
            j -= 1
        elif i and j and rows[i][j] == rows[i - 1][j - 1] + 1:
            substitutions += 1
            i -= 1
            j -= 1
        elif i and rows[i][j] == rows[i - 1][j] + 1:
            deletions += 1
            i -= 1
        else:
            insertions += 1
            j -= 1
    errors = deletions + substitutions + insertions
    return {"del": deletions, "sub": substitutions, "ins": insertions,
            "errors": errors, "reference_chars": len(ref),
            "cer": errors / len(ref) if ref else (0.0 if not hyp else 1.0)}


def chrf(reference: str, hypothesis: str, *, max_order: int = 6,
         beta: float = 2.0) -> float:
    """Character n-gram F-beta score on a 0–100 scale (whitespace is ignored)."""
    if max_order < 1 or beta <= 0:
        raise ValueError("max_order and beta must be positive")
    ref = _normalized(reference)
    hyp = _normalized(hypothesis)
    if not ref or not hyp:
        return 100.0 if not ref and not hyp else 0.0

    precisions: list[float] = []
    recalls: list[float] = []
    for order in range(1, max_order + 1):
        ref_ngrams = Counter(ref[i:i + order] for i in range(len(ref) - order + 1))
        hyp_ngrams = Counter(hyp[i:i + order] for i in range(len(hyp) - order + 1))
        if not ref_ngrams or not hyp_ngrams:
            continue
        overlap = sum((ref_ngrams & hyp_ngrams).values())
        precisions.append(overlap / sum(hyp_ngrams.values()))
        recalls.append(overlap / sum(ref_ngrams.values()))

    if not precisions:
        return 0.0
    precision = sum(precisions) / len(precisions)
    recall = sum(recalls) / len(recalls)
    beta2 = beta * beta
    denominator = beta2 * precision + recall
    return 100.0 * (1 + beta2) * precision * recall / denominator if denominator else 0.0


def paired_bootstrap_ci(deltas: list[float], *, resamples: int = 5000,
                        seed: int = 20261019) -> tuple[float, tuple[float, float]]:
    """`(delta trung bình, CI95)` của hiệu số CER theo TỪNG cặp (candidate - baseline).

    Vì sao phải paired: hai cấu hình decode chạy trên ĐÚNG cùng caption, nên câu
    khó chung của cả hai bị triệt tiêu khi lấy hiệu số THEO CẶP; so hai phân bố
    rời sẽ thổi phương sai lên và che mất khác biệt nhỏ (dev: prevtrue -0,004).
    Delta âm = tốt hơn baseline.

    Resample CÓ hoàn lại trên các delta đã bốc cặp (bootstrap chuẩn, không tham
    số): 5 000 lần, seed cố định, nên chạy lại cho đúng cùng một CI. CI chứa 0 thì
    kết luận là "chưa phân biệt được", không phải "tốt hơn".
    """
    if not deltas:
        raise ValueError("paired bootstrap cần ít nhất một cặp")
    if resamples < 1:
        raise ValueError("resamples phải >= 1")
    mean = sum(deltas) / len(deltas)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(resamples):
        total = 0.0
        for _ in range(len(deltas)):
            total += deltas[rng.randrange(len(deltas))]
        means.append(total / len(deltas))
    means.sort()
    low = means[int(0.025 * (resamples - 1))]
    high = means[int(0.975 * (resamples - 1))]
    return mean, (low, high)
