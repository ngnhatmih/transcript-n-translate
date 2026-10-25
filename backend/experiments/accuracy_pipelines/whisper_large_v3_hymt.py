"""Full Whisper large-v3 + HY-MT, for accuracy-first comparison on 8GB GPUs."""
from __future__ import annotations

from app.adapters.asr.cuda_runtime import ensure_cuda_runtime
from app.adapters.asr.faster_whisper import to_segments
from app.config import HF_HOME
from app.domain.segmentation import normalize

from ._common import HYMT, mt, result, stage_call
from .contracts import PipelineContext

PIPELINE_ID = "whisper_large_v3_hymt"
MODEL_TAGS = ("hy-mt1.5-7b:q4_K_M",)
MODEL_REF = "Systran/faster-whisper-large-v3"
COMPUTE_TYPE = "int8_float16"
BEAM_SIZE = 5


def transcribe(audio_path, lang: str, *, initial_prompt: str | None = None,
               hotwords: str | None = None):
    # CTranslate2's CUDA runtime on Windows depends on torch's DLL search path.
    ensure_cuda_runtime()
    from faster_whisper import WhisperModel

    model = WhisperModel(MODEL_REF, device="cuda", compute_type=COMPUTE_TYPE,
                         download_root=str(HF_HOME))
    try:
        iterator, _info = model.transcribe(
            str(audio_path), language=lang, beam_size=BEAM_SIZE,
            vad_filter=True, word_timestamps=True,
            condition_on_previous_text=False, without_timestamps=False,
            initial_prompt=initial_prompt, hotwords=hotwords,
        )
        raw = [{
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
            "avg_logprob": getattr(segment, "avg_logprob", None),
            "no_speech_prob": getattr(segment, "no_speech_prob", None),
            "words": [{"word": word.word, "start": word.start, "end": word.end}
                      for word in (getattr(segment, "words", None) or [])],
        } for segment in iterator]
        segments = normalize(to_segments(raw))
        if not segments:
            raise RuntimeError(f"{MODEL_REF} returned no transcript segments")
        return segments
    finally:
        del model


def run(context: PipelineContext):
    stages = []
    source = stage_call(stages, "asr", f"{MODEL_REF} ({COMPUTE_TYPE}, beam={BEAM_SIZE})",
                        lambda: transcribe(context.audio_path, context.source_lang))
    translated = mt(context, HYMT, source, stages)
    return result(context, PIPELINE_ID, stages, source, translated, final=translated)
