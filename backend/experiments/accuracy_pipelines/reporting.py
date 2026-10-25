from __future__ import annotations

from dataclasses import asdict

from .contracts import PipelineResult
from .metrics import char_error_rate, chrf


def _join(segments) -> str:
    return "".join(segment.text for segment in segments)


def build_report(results: list[PipelineResult], reference: dict | None = None) -> list[dict]:
    rows = []
    for item in results:
        source = _join(item.corrected_segments or item.source_segments)
        translation = _join(item.final_translation or item.raw_translation)
        source_ref = reference.get("source") if reference else None
        translation_ref = reference.get("translation") if reference else None
        rows.append({
            "pipeline_id": item.pipeline_id,
            "stages": [asdict(stage) for stage in item.stages],
            "source_cer": char_error_rate(source_ref, source) if source_ref is not None else None,
            "source_cer_before_context": char_error_rate(
                source_ref, _join(item.metadata["first_pass_segments"])
            ) if source_ref is not None and item.metadata.get("first_pass_segments") else None,
            "source_cer_after_context": char_error_rate(
                source_ref, _join(item.metadata["second_pass_segments"])
            ) if source_ref is not None and item.metadata.get("second_pass_segments") else None,
            "translation_chrf": chrf(translation_ref, translation)
            if translation_ref is not None else None,
            "alignment_coverage": (len(item.final_translation or item.raw_translation) /
                                   len(item.source_segments)) if item.source_segments else 0.0,
            "empty_outputs": sum(not segment.text.strip() for segment in
                                 (item.final_translation or item.raw_translation)),
            "models": item.metadata.get("models", []),
            "runtime_ms": sum(stage.duration_ms for stage in item.stages),
            "failure_stage": next((stage.name for stage in item.stages
                                   if stage.status != "done"), None),
            "qa_issues": item.metadata.get("qa_issues", []),
            "qa_issue_count": len(item.metadata.get("qa_issues", [])),
            "quality": "scored" if reference else "not_scored_no_reference",
        })
    return rows


def markdown_report(rows: list[dict], *, complete: bool) -> str:
    qa_issues = sum(row.get("qa_issue_count", 0) for row in rows)
    if not complete:
        status = "incomplete"
    elif qa_issues:
        status = f"complete; quality gate failed: {qa_issues} QA issue(s)"
    else:
        status = "complete; no QA issues detected"
    lines = ["# Pipeline comparison", "", f"Status: {status}", "",
             "No reference means quality is not scored; inspect the saved segment JSON manually.", "",
             "| Pipeline | CER ↓ | CER pass 1 ↓ | CER pass 2 ↓ | chrF ↑ | Alignment | Empty | QA | Runtime ms | Failure |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for row in rows:
        cer = "—" if row["source_cer"] is None else f"{row['source_cer']:.4f}"
        before = ("—" if row["source_cer_before_context"] is None
                  else f"{row['source_cer_before_context']:.4f}")
        after = ("—" if row["source_cer_after_context"] is None
                 else f"{row['source_cer_after_context']:.4f}")
        score = "—" if row["translation_chrf"] is None else f"{row['translation_chrf']:.2f}"
        lines.append(f"| {row['pipeline_id']} | {cer} | {before} | {after} | {score} | "
                     f"{row['alignment_coverage']:.1%} | {row['empty_outputs']} | "
                     f"{row['qa_issue_count']} | "
                     f"{row['runtime_ms']} | {row['failure_stage'] or '—'} |")
    return "\n".join(lines) + "\n"
