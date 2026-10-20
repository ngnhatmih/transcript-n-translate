from ._common import asr, mt, result
from .contracts import PipelineContext

PIPELINE_ID = "baseline"
MODEL_TAGS = ()


def run(context: PipelineContext):
    stages = []
    source = asr(context, context.models["baseline_asr"], stages)
    raw = mt(context, context.models["baseline_mt"], source, stages)
    return result(context, PIPELINE_ID, stages, source, raw, final=raw)
