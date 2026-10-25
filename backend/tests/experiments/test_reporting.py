from app.domain.models import Segment
from experiments.accuracy_pipelines.contracts import PipelineResult, PipelineStage
from experiments.accuracy_pipelines.reporting import build_report, markdown_report


def test_report_labels_reference_metrics_unavailable_without_reference():
    result = PipelineResult("baseline", [PipelineStage("asr", "fw-small", 10)],
                            [Segment(i=0, start=0, end=1, text="你好")],
                            [Segment(i=0, start=0, end=1, text="Xin chào")],
                            final_translation=[Segment(i=0, start=0, end=1, text="Xin chào")])

    report = build_report([result], reference=None)

    assert report[0]["source_cer"] is None
    assert report[0]["translation_chrf"] is None
    assert report[0]["quality"] == "not_scored_no_reference"


def test_report_scores_both_reference_fields():
    result = PipelineResult("baseline", [],
                            [Segment(i=0, start=0, end=1, text="你好")],
                            [Segment(i=0, start=0, end=1, text="Xin chao")],
                            final_translation=[Segment(i=0, start=0, end=1, text="Xin chao")])

    report = build_report([result], reference={"source": "你好", "translation": "Xin chao"})

    assert report[0]["source_cer"] == 0
    assert report[0]["translation_chrf"] == 100


def test_report_scores_before_and_after_contextual_asr_passes():
    first = [Segment(i=0, start=0, end=1, text="山头")]
    second = [Segment(i=0, start=0, end=1, text="汕头")]
    result = PipelineResult("glossary", [], first, [], corrected_segments=second,
                            metadata={"first_pass_segments": first,
                                      "second_pass_segments": second})

    report = build_report([result], reference={"source": "汕头", "translation": ""})

    assert report[0]["source_cer_before_context"] == 0.5
    assert report[0]["source_cer_after_context"] == 0


def test_markdown_report_does_not_call_qa_failure_a_clean_completion():
    result = PipelineResult("qwen", [], [], [], metadata={"qa_issues": ["lang:0=source"]})
    report = build_report([result])

    markdown = markdown_report(report, complete=True)

    assert "quality gate failed: 1 QA issue(s)" in markdown
