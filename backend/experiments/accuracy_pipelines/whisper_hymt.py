from ._common import WHISPER, HYMT, asr, mt, result
from .contracts import PipelineContext

PIPELINE_ID = "whisper_hymt"
MODEL_TAGS = ("hy-mt1.5-7b:q4_K_M",)


def run(context: PipelineContext):
    stages = []
    source = asr(context, WHISPER, stages)
    raw = mt(context, HYMT, source, stages)
    return result(context, PIPELINE_ID, stages, source, raw, final=raw)
