from ._common import SENSEVOICE, OPUS, asr, mt, result
from .contracts import PipelineContext

PIPELINE_ID = "sensevoice_opus"
MODEL_TAGS = ()


def run(context: PipelineContext):
    stages = []
    source = asr(context, SENSEVOICE, stages)
    raw = mt(context, OPUS, source, stages)
    return result(context, PIPELINE_ID, stages, source, raw, final=raw)
