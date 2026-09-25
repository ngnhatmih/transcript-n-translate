"""Use case bóc băng. Ráp registry + engine + repos.

Bất biến: engine được GIỮ theo engine_id và chỉ tạo mới khi đổi engine. Nạp
lại model cho từng job là lãng phí 4-8 giây mỗi lần.
"""
from __future__ import annotations

import pathlib
from typing import Callable, Iterable

from app.domain import job_state as js
from app.domain.models import Job
from app.ports.asr import ASREngine
from app.ports.repos import Repos
from app.registry import EngineSpec, by_id

AUTO_FORWARD_SETTING = "auto_forward"


class EngineFactory:
    def __call__(self, spec: EngineSpec) -> ASREngine:  # pragma: no cover - Protocol
        raise NotImplementedError


class TranscribeHandler:
    def __init__(
        self,
        repos: Repos,
        specs: Iterable[EngineSpec],
        engine_factory: Callable[[EngineSpec], ASREngine],
        *,
        workdir: str | pathlib.Path,
    ) -> None:
        self._repos = repos
        self._specs = list(specs)
        self._factory = engine_factory
        self._workdir = pathlib.Path(workdir)
        self._engine: ASREngine | None = None
        self._engine_id: str | None = None

    def handles(self) -> str:
        return "asr"

    def _engine_for(self, engine_id: str) -> ASREngine:
        if self._engine is not None and self._engine_id == engine_id:
            return self._engine
        if self._engine is not None:
            self._engine.release()
            self._engine = None
        spec = by_id(self._specs, engine_id)
        self._engine = self._factory(spec)
        self._engine_id = engine_id
        return self._engine

    def release(self) -> None:
        if self._engine is not None:
            self._engine.release()
            self._engine = None
            self._engine_id = None

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        source_id = job.payload["source_id"]
        source = self._repos.get_source(source_id)
        if not source.audio_path:
            raise FileNotFoundError(
                f"source {source_id} chưa có audio; job ingest phải chạy trước"
            )
        audio = pathlib.Path(source.audio_path)
        if not audio.exists():
            raise FileNotFoundError(f"tệp audio không tồn tại: {audio}")

        lang = source.lang or "zh"
        report(0.05, f"nạp engine {job.engine}")
        engine = self._engine_for(job.engine or "")

        report(0.15, f"bóc băng {audio.name} (lang={lang})")
        segments = engine.transcribe(str(audio), lang)

        report(0.9, f"đã có {len(segments)} đoạn")
        transcript_id = self._repos.add_transcript(
            source_id=source_id, engine=job.engine or "", lang=lang, segments=segments,
        )
        report(0.95, f"lưu transcript #{transcript_id}")

        if (self._repos.get_setting(AUTO_FORWARD_SETTING, "1") or "1") == "1":
            self._forward_to_translation(source_id, transcript_id, lang)
            report(0.98, "đã tạo job dịch ở workspace 2")
        else:
            report(0.98, "giữ lại để sửa (auto_forward tắt)")
        report(1.0, "xong")

    def _forward_to_translation(self, source_id: int, transcript_id: int, lang: str) -> None:
        engine_id = self._default_mt_engine()
        self._repos.add_job(Job(
            id=None, workspace=2, type="translate", engine=engine_id,
            phase=js.phase_of("translate", engine_id),
            payload={"transcript_id": transcript_id, "source_id": source_id, "lang": lang},
        ))

    def _default_mt_engine(self) -> str | None:
        configured = self._repos.get_setting("default_mt_engine")
        if configured:
            return configured
        mt_specs = [s for s in self._specs if s.kind == "mt"]
        return mt_specs[0].id if mt_specs else None
