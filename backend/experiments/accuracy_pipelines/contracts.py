from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.domain.models import Segment, Term


@dataclass
class PipelineContext:
    media_path: Path
    audio_path: Path
    source_lang: str
    target_lang: str
    workdir: Path
    output_dir: Path
    glossary: list[Term] = field(default_factory=list)
    models: dict[str, str] = field(default_factory=dict)
    frame_interval_seconds: int = 15
    ollama_base_url: str = "http://127.0.0.1:11434"
    audio_duration_seconds: float = 0.0
    temp_owner: Any = field(default=None, repr=False)

    def cleanup(self) -> None:
        if self.temp_owner is not None:
            self.temp_owner.cleanup()
            self.temp_owner = None


@dataclass
class PipelineStage:
    name: str
    model: str
    duration_ms: int
    status: str = "done"
    tokens_in: int | None = None
    tokens_out: int | None = None
    error: str | None = None


@dataclass
class PipelineResult:
    pipeline_id: str
    stages: list[PipelineStage]
    source_segments: list[Segment]
    raw_translation: list[Segment]
    corrected_segments: list[Segment] | None = None
    final_translation: list[Segment] | None = None
    metadata: dict = field(default_factory=dict)
