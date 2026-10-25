from __future__ import annotations

import math
import json
import re
import unicodedata
from dataclasses import replace
from typing import Callable

from app.domain.glossary_match import approved, terms_in
from app.domain.models import Segment, Term


class PipelineOutputError(ValueError):
    """A model output violated a pipeline contract and must not replace raw data."""


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_VI_NEGATION = re.compile(r"(?<!\w)(?:không|chưa|chẳng|đừng|chớ)(?!\w)", re.IGNORECASE)


def normalize_for_scoring(text: str) -> str:
    """Normalize Unicode and punctuation for scoring; keep saved text untouched."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(" " if unicodedata.category(char).startswith("P") else char
                   for char in text)
    return " ".join(text.split())


def align_hypothesis(reference: list[Segment], hypothesis: list[Segment], *,
                     lang: str) -> list[Segment]:
    """Map coarse ASR segments onto the reference timestamps without duplicating text."""
    grouped: list[list[str]] = [[] for _ in reference]
    for candidate in hypothesis:
        if not reference:
            break
        overlaps = [max(0.0, min(ref.end, candidate.end) - max(ref.start, candidate.start))
                    for ref in reference]
        if max(overlaps, default=0.0) > 0:
            index = max(range(len(reference)), key=lambda i: (overlaps[i], -i))
        else:
            center = (candidate.start + candidate.end) / 2
            index = min(range(len(reference)),
                        key=lambda i: (abs((reference[i].start + reference[i].end) / 2 - center), i))
        if candidate.text.strip():
            grouped[index].append(candidate.text.strip())
    separator = "" if lang in {"zh", "yue", "ja", "ko"} else " "
    return [replace(segment, text=separator.join(parts))
            for segment, parts in zip(reference, grouped)]


def _aligned(expected: list[Segment], actual: list[Segment], label: str) -> None:
    if len(expected) != len(actual):
        raise PipelineOutputError(f"{label}: segment count changed")
    for want, got in zip(expected, actual):
        if want.i != got.i:
            raise PipelineOutputError(f"{label}: segment ids/order changed")
        if not math.isclose(want.start, got.start, abs_tol=0.001):
            raise PipelineOutputError(f"{label}: segment {want.i} start time changed")
        if not math.isclose(want.end, got.end, abs_tol=0.001):
            raise PipelineOutputError(f"{label}: segment {want.i} end time changed")


def validate_asr_correction(
    original: list[Segment],
    corrected: list[Segment],
    *,
    alternatives: list[list[Segment]] = (),
) -> list[Segment]:
    """Accept only an unchanged hypothesis or text supported by another ASR."""
    _aligned(original, corrected, "ASR correction")
    for alternative in alternatives:
        _aligned(original, alternative, "ASR alternative")
    allowed = [{segment.text.strip() for segment in [original[index], *(
        alternative[index] for alternative in alternatives)]}
        for index in range(len(original))]
    for index, segment in enumerate(corrected):
        if not segment.text.strip():
            raise PipelineOutputError(f"ASR correction: segment {segment.i} is empty")
        if segment.text.strip() not in allowed[index]:
            raise PipelineOutputError(
                f"ASR correction: segment {segment.i} contains unsupported text"
            )
    return corrected


def validate_translation_edit(
    source: list[Segment],
    raw: list[Segment],
    edited: list[Segment],
    glossary: list[Term],
) -> list[Segment]:
    """Validate alignment, numbers, negation, and approved terminology."""
    _aligned(source, raw, "raw translation")
    _aligned(raw, edited, "translation edit")
    required_terms = approved(glossary)
    for source_segment, raw_segment, output_segment in zip(source, raw, edited):
        if not output_segment.text.strip():
            raise PipelineOutputError(
                f"translation edit: segment {output_segment.i} is empty"
            )
        if _NUMBER.findall(raw_segment.text) != _NUMBER.findall(output_segment.text):
            raise PipelineOutputError(
                f"translation edit: segment {output_segment.i} changed a number"
            )
        if (_VI_NEGATION.search(raw_segment.text)
                and not _VI_NEGATION.search(output_segment.text)):
            raise PipelineOutputError(
                f"translation edit: segment {output_segment.i} removed negation"
            )
        for term in terms_in(source_segment.text, required_terms):
            if term.translation.casefold() not in output_segment.text.casefold():
                raise PipelineOutputError(
                    f"translation edit: segment {output_segment.i} omitted glossary "
                    f"term {term.term!r} -> {term.translation!r}"
                )
    return edited


def _parse_segment_payload(payload: dict, batch: list[Segment], stage: str
                           ) -> list[Segment]:
    items = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) != len(batch):
        raise PipelineOutputError(f"{stage}: response must contain exactly {len(batch)} segments")
    parsed: list[Segment] = []
    for expected, item in zip(batch, items):
        if not isinstance(item, dict) or item.get("i") != expected.i:
            raise PipelineOutputError(f"{stage}: segment ids/order changed")
        text = item.get("text")
        if not isinstance(text, str):
            raise PipelineOutputError(f"{stage}: segment {expected.i} text is not a string")
        parsed.append(replace(expected, text=text.strip()))
    return parsed


def _merge_translation_payload(payload: dict, source: list[Segment], raw: list[Segment],
                               glossary: list[Term]) -> tuple[list[Segment], int]:
    items = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise PipelineOutputError("translation edit: response must contain a segments list")
    candidates: dict[int, dict] = {}
    duplicates: set[int] = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("i"), int):
            continue
        item_id = item["i"]
        if item_id in candidates:
            duplicates.add(item_id)
        candidates[item_id] = item
    merged: list[Segment] = []
    fallback_count = 0
    for src, draft in zip(source, raw):
        item = candidates.get(src.i)
        text = item.get("text") if item and src.i not in duplicates else None
        candidate = replace(draft, text=text.strip()) if isinstance(text, str) else draft
        accepted = isinstance(text, str) and bool(text.strip())
        try:
            validate_translation_edit([src], [draft], [candidate], glossary)
        except PipelineOutputError:
            candidate = draft
            accepted = False
        if not accepted:
            fallback_count += 1
        merged.append(candidate)
    return merged, fallback_count


def _add_stats(total: dict, row: dict) -> None:
    for key in ("tokens_in", "tokens_out", "duration_ms"):
        value = row.get(key)
        if value is not None:
            total[key] = total.get(key, 0) + int(value)


def reconcile_asr(primary: list[Segment], alternative: list[Segment], *, model: str,
                  lang: str, chat: Callable, base_url: str,
                  visual_facts: dict | None = None, batch_size: int = 20
                  ) -> tuple[list[Segment], list[Segment], dict]:
    """Choose between two timestamp-aligned hypotheses; never synthesize new speech."""
    aligned = align_hypothesis(primary, alternative, lang=lang)
    corrected: list[Segment] = []
    totals: dict = {}
    system = (
        "Bạn là bộ chọn transcript ASR. Chọn nguyên văn một trong hai giả thuyết "
        "cho từng id. Không viết lại, không suy diễn, không thêm lời nói. Chỉ chọn "
        "giả thuyết khác khi âm thanh/ngữ cảnh hỗ trợ rõ. Nếu không chắc, chọn "
        "Whisper. Trả JSON {\"segments\":[{\"i\":0,\"text\":\"...\"}]}."
    )
    for offset in range(0, len(primary), batch_size):
        batch = primary[offset:offset + batch_size]
        alt_batch = aligned[offset:offset + batch_size]
        items = [{"i": src.i, "whisper": src.text, "sensevoice": alt.text,
                  "whisper_suspect": src.suspect}
                 for src, alt in zip(batch, alt_batch)]
        prompt = (
            f"Ngôn ngữ: {lang}. Chọn một văn bản đúng nguyên văn trong mỗi cặp. "
            f"Bằng chứng hình ảnh chỉ dùng để phân biệt tên/ngữ cảnh, không được "
            f"tạo lời nói. Visual facts: {json.dumps(visual_facts or {}, ensure_ascii=False)}\n"
            f"Dữ liệu: {json.dumps(items, ensure_ascii=False)}"
        )
        payload, stats = chat(model, system, prompt, base_url=base_url)
        _add_stats(totals, stats)
        try:
            parsed = _parse_segment_payload(payload, batch, "ASR correction")
            for source, alt, candidate in zip(batch, alt_batch, parsed):
                if candidate.text not in {source.text.strip(), alt.text.strip()}:
                    corrected.append(source)
                    totals["fallback_segments"] = totals.get("fallback_segments", 0) + 1
                else:
                    corrected.append(candidate)
        except PipelineOutputError:
            if len(batch) == 1:
                raise
            # Retry malformed batches individually; keep ASR text constrained
            # to the two supplied hypotheses in every retry.
            for source, alt in zip(batch, alt_batch):
                single = [{"i": source.i, "whisper": source.text,
                           "sensevoice": alt.text, "whisper_suspect": source.suspect}]
                single_prompt = (
                    f"Ngôn ngữ: {lang}. Chọn một văn bản đúng nguyên văn trong cặp. "
                    f"Bằng chứng hình ảnh chỉ dùng để phân biệt tên/ngữ cảnh, không được "
                    f"tạo lời nói. Visual facts: "
                    f"{json.dumps(visual_facts or {}, ensure_ascii=False)}\n"
                    f"Dữ liệu: {json.dumps(single, ensure_ascii=False)}"
                )
                single_payload, single_stats = chat(model, system, single_prompt,
                                                    base_url=base_url)
                single_items = (single_payload.get("segments")
                                if isinstance(single_payload, dict) else None)
                if (isinstance(single_items, list) and len(single_items) == 1
                        and isinstance(single_items[0], dict)
                        and isinstance(single_items[0].get("text"), str)):
                    # One-item prompts are unambiguous even when a local LLM
                    # repeats the template id instead of the source id.
                    choice = single_items[0]["text"].strip()
                    if choice not in {source.text.strip(), alt.text.strip()}:
                        corrected.append(source)
                        totals["fallback_segments"] = totals.get("fallback_segments", 0) + 1
                    else:
                        corrected.append(replace(source, text=choice))
                else:
                    try:
                        corrected.extend(_parse_segment_payload(single_payload, [source],
                                                                "ASR correction"))
                    except PipelineOutputError:
                        corrected.append(source)
                        totals["fallback_segments"] = totals.get("fallback_segments", 0) + 1
                _add_stats(totals, single_stats)
    for index, candidate in enumerate(corrected):
        allowed = {primary[index].text.strip(), aligned[index].text.strip()}
        if candidate.text.strip() not in allowed:
            corrected[index] = primary[index]
            totals["fallback_segments"] = totals.get("fallback_segments", 0) + 1
    return validate_asr_correction(primary, corrected, alternatives=[aligned]), aligned, totals


def edit_translation(source: list[Segment], raw: list[Segment], glossary: list[Term], *,
                     model: str, source_lang: str, target_lang: str,
                     chat: Callable, base_url: str,
                     visual_facts: dict | None = None, batch_size: int = 20
                     ) -> tuple[list[Segment], dict]:
    """Improve fluency and cross-segment consistency while guarding meaning anchors."""
    _aligned(source, raw, "translation input")
    terms = approved(glossary)
    system = (
        f"Bạn là biên tập viên phụ đề {target_lang}. Sửa cho tự nhiên và nhất quán "
        "nhưng giữ nguyên ý, phủ định, số, tên, người nói và thuật ngữ bắt buộc. "
        "Không thêm giải thích hay thông tin mới. Chỉ sửa các mục được yêu cầu; "
        "trả JSON {\"segments\":[{\"i\":0,\"text\":\"...\"}]} đúng đủ id."
    )
    edited: list[Segment] = []
    totals: dict = {}
    for offset in range(0, len(source), batch_size):
        src_batch = source[offset:offset + batch_size]
        raw_batch = raw[offset:offset + batch_size]
        neighbors = []
        if offset:
            neighbors.append({"source": source[offset - 1].text,
                              "translation": raw[offset - 1].text})
        following = offset + len(src_batch)
        if following < len(source):
            neighbors.append({"source": source[following].text,
                              "translation": raw[following].text})
        pairs = [{"i": src.i, "source": src.text, "draft": out.text}
                 for src, out in zip(src_batch, raw_batch)]
        prompt = (
            f"Dịch từ {source_lang} sang {target_lang}. "
            f"Thuật ngữ bắt buộc: {json.dumps([{'term': t.term, 'translation': t.translation} for t in terms], ensure_ascii=False)}\n"
            f"Ngữ cảnh hình ảnh chỉ để hiểu tên/bối cảnh, không thêm chi tiết: "
            f"{json.dumps(visual_facts or {}, ensure_ascii=False)}\n"
            f"Mục kề để hiểu mạch, không được trả lại các mục này: "
            f"{json.dumps(neighbors, ensure_ascii=False)}\n"
            f"Chỉnh đúng các mục sau: {json.dumps(pairs, ensure_ascii=False)}"
        )
        payload, stats = chat(model, system, prompt, base_url=base_url)
        _add_stats(totals, stats)
        try:
            batch_edited, fallback_count = _merge_translation_payload(
                payload, src_batch, raw_batch, glossary)
            edited.extend(batch_edited)
            totals["fallback_segments"] = totals.get("fallback_segments", 0) + fallback_count
        except PipelineOutputError:
            if len(src_batch) == 1:
                raise
            # A malformed batch response is retried per segment with only the
            # immediate source/draft neighbors retained as context. This keeps
            # every subtitle addressable without accepting partial model output.
            for local_index, (src, draft) in enumerate(zip(src_batch, raw_batch)):
                absolute_index = offset + local_index
                single_neighbors = []
                if absolute_index:
                    single_neighbors.append({"source": source[absolute_index - 1].text,
                                             "translation": raw[absolute_index - 1].text})
                if absolute_index + 1 < len(source):
                    single_neighbors.append({"source": source[absolute_index + 1].text,
                                             "translation": raw[absolute_index + 1].text})
                single_pairs = [{"i": src.i, "source": src.text, "draft": draft.text}]
                single_prompt = (
                    f"Dịch từ {source_lang} sang {target_lang}. "
                    f"Thuật ngữ bắt buộc: {json.dumps([{'term': t.term, 'translation': t.translation} for t in terms], ensure_ascii=False)}\n"
                    f"Ngữ cảnh hình ảnh chỉ để hiểu tên/bối cảnh, không thêm chi tiết: "
                    f"{json.dumps(visual_facts or {}, ensure_ascii=False)}\n"
                    f"Mục kề để hiểu mạch, không được trả lại các mục này: "
                    f"{json.dumps(single_neighbors, ensure_ascii=False)}\n"
                    f"Chỉnh đúng các mục sau: {json.dumps(single_pairs, ensure_ascii=False)}"
                )
                single_payload, single_stats = chat(model, system, single_prompt,
                                                    base_url=base_url)
                _add_stats(totals, single_stats)
                batch_edited, fallback_count = _merge_translation_payload(
                    single_payload, [src], [draft], glossary)
                edited.extend(batch_edited)
                totals["fallback_segments"] = totals.get("fallback_segments", 0) + fallback_count
    return validate_translation_edit(source, raw, edited, glossary), totals
