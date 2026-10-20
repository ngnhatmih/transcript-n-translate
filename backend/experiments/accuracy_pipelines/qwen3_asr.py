from __future__ import annotations

import math
import os
import pathlib
import sys
import gc
from typing import Callable

from app.domain.models import Segment


_END_PUNCTUATION = frozenset("。！？；!?;")
_MAX_GROUP_CHARS = 22
_MAX_GROUP_SECONDS = 4.0


def segments_from_timestamps(items) -> list[Segment]:
    """Group Qwen's aligned Chinese characters into short timed phrases."""
    groups: list[Segment] = []
    text: list[str] = []
    group_start = group_end = previous_start = None

    def flush() -> None:
        nonlocal text, group_start, group_end
        phrase = "".join(text).strip()
        if phrase:
            groups.append(Segment(i=len(groups), start=group_start, end=group_end, text=phrase))
        text, group_start, group_end = [], None, None

    for item in items or []:
        token = str(getattr(item, "text", "")).strip()
        if not token:
            continue
        start = getattr(item, "start_time", None)
        end = getattr(item, "end_time", None)
        if (isinstance(start, bool) or isinstance(end, bool)
                or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or not math.isfinite(start) or not math.isfinite(end)
                or start < 0 or end < start):
            raise ValueError(f"Qwen ASR returned an invalid timestamp for {token!r}: {start!r}-{end!r}")
        if previous_start is not None and start < previous_start:
            raise ValueError("Qwen ASR timestamps are not ordered")
        previous_start = start
        if group_start is None:
            group_start = float(start)
        group_end = float(end)
        text.append(token)
        if (token[-1] in _END_PUNCTUATION or len("".join(text)) >= _MAX_GROUP_CHARS
                or group_end - group_start >= _MAX_GROUP_SECONDS):
            flush()

    flush()
    if not groups:
        raise RuntimeError("Qwen ASR returned no aligned transcript")
    return groups


def _model_paths() -> tuple[pathlib.Path, pathlib.Path]:
    model_path = pathlib.Path(os.environ.get("QWEN3_ASR_MODEL_PATH", ""))
    aligner_path = pathlib.Path(os.environ.get("QWEN3_ASR_ALIGNER_PATH", ""))
    if not model_path.is_dir() or not aligner_path.is_dir():
        raise RuntimeError(
            "Qwen3-ASR needs local model and aligner directories. Set "
            "QWEN3_ASR_MODEL_PATH and QWEN3_ASR_ALIGNER_PATH; expected "
            "Qwen/Qwen3-ASR-0.6B and Qwen/Qwen3-ForcedAligner-0.6B."
        )
    package_path = os.environ.get("QWEN3_ASR_RUNTIME_PATH")
    if package_path:
        package_path = str(pathlib.Path(package_path).resolve())
        if not pathlib.Path(package_path).is_dir():
            raise RuntimeError(f"QWEN3_ASR_RUNTIME_PATH does not exist: {package_path}")
        if package_path not in sys.path:
            sys.path.insert(0, package_path)
    return model_path, aligner_path


def _load_asr_model():
    model_path, _aligner_path = _model_paths()
    import torch
    from qwen_asr import Qwen3ASRModel

    return Qwen3ASRModel.from_pretrained(
        str(model_path), dtype=torch.float16, device_map="cuda:0",
        max_inference_batch_size=1, max_new_tokens=4096,
    )


def _load_aligner():
    _model_path, aligner_path = _model_paths()
    import torch
    from qwen_asr import Qwen3ForcedAligner

    return Qwen3ForcedAligner.from_pretrained(
        str(aligner_path), dtype=torch.float16, device_map="cuda:0",
    )


def _clear_cuda_cache() -> None:
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001 - best-effort cleanup
        pass


def transcribe_with_model(audio_path: str | pathlib.Path, lang: str, context: str,
                          *, model_factory: Callable | None = None,
                          aligner_factory: Callable | None = None) -> list[Segment]:
    """Run ASR then free it before loading the small forced aligner."""
    language = "Chinese" if lang.lower() in {"zh", "zh-cn", "zh-hans"} else lang
    model = (model_factory or _load_asr_model)()
    try:
        recognized = model.transcribe(
            audio=str(audio_path), language=language, context=[context],
            return_time_stamps=False,
        )
        text = str(getattr(recognized[0], "text", "")).strip() if recognized else ""
    finally:
        model = None
        _clear_cuda_cache()
    if not text:
        raise RuntimeError("Qwen3-ASR returned an empty transcript")

    aligner = (aligner_factory or _load_aligner)()
    try:
        aligned = aligner.align(audio=str(audio_path), text=text, language=language)
        if aligned:
            first = aligned[0]
            if hasattr(first, "items"):
                aligned = first.items
            elif isinstance(first, (list, tuple)):
                aligned = first
        return segments_from_timestamps(aligned)
    finally:
        aligner = None
        _clear_cuda_cache()
