"""Use case bóc băng. Ráp registry + engine + repos.

Bất biến: engine được GIỮ theo engine_id và chỉ tạo mới khi đổi engine. Nạp
lại model cho từng job là lãng phí 4-8 giây mỗi lần.
"""
from __future__ import annotations

import pathlib
from typing import Callable, Iterable, Mapping

from app.domain import job_state as js
from app.domain.models import Job
from app.ports.asr import ASREngine
from app.ports.repos import Repos
from app.registry import (MT_DEFAULT_SETTING, EngineSpec, by_id,
                          default_mt_engine)

AUTO_FORWARD_SETTING = "auto_forward"

#: Ngôn ngữ đích của bản dịch tự sinh. Chưa phải setting (không có khoá nào
#: trong bảng `settings` cho nó), nhưng phải là HẰNG SỐ DÙNG CHUNG giữa hàng
#: `translations` và payload của job — lệch một chữ ở đây là bản dịch được ghi
#: bằng ngôn ngữ khác với thứ handler đọc từ payload.
DEFAULT_TARGET_LANG = "vi"


class TranscribeHandler:
    def __init__(
        self,
        repos: Repos,
        specs: Iterable[EngineSpec],
        engine_factory: Callable[[EngineSpec], ASREngine],
        *,
        workdir: str | pathlib.Path,
        declared_default_mt: str | None = None,
        prompt_versions: Mapping[str, str] | None = None,
    ) -> None:
        self._repos = repos
        self._specs = list(specs)
        self._factory = engine_factory
        self._workdir = pathlib.Path(workdir)
        #: Khoá `default_mt` của registry (R58/WQ-02), do `main.py` nạp. Vắng nó
        #: thì `_default_mt_engine` mới rơi về phần tử đầu của danh sách `mt`.
        self._declared_default_mt = declared_default_mt
        #: `{engine_id: prompt_version}` — DỮ LIỆU của `adapters/mt/prompts.py`,
        #: do composition root bơm vào. `add_translation` BẮT BUỘC có
        #: `prompt_version`, mà `pipeline/` không được biết adapter (chỉ
        #: `main.py` được phép), nên nó đi qua đây y như `declared_default_mt`.
        #: Vắng mặt thì ghi `"unknown"`: bịa ra một phiên bản prompt còn tệ hơn.
        self._prompt_versions = dict(prompt_versions or {})
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

        # R68, và cố ý đặt ở ĐÂY chứ không trong từng adapter: guard này phải
        # đúng cho MỌI engine. `SenseVoiceEngine` đã có guard riêng của nó
        # (adapters/asr/sensevoice.py), nhưng engine MẶC ĐỊNH của GĐ1a —
        # `fw-large-v3-turbo` — là `FasterWhisperEngine`, và nó không có guard
        # nào: audio im lặng (VAD bỏ hết) trả `[]` mà không ném, nên job thành
        # `done` kèm một transcript 0 đoạn. Một transcript rỗng trông y hệt một
        # lần bóc băng thành công mà không có tiếng nói, nên nó giấu mất lỗi
        # giải mã/thiếu model. Thà hỏng ồn ào còn hơn (xem R62).
        if not segments:
            raise RuntimeError(
                f"{job.engine}: không có đoạn nào — audio im lặng hay giải mã hỏng. "
                f"KHÔNG lưu transcript rỗng (R68)."
            )

        report(0.9, f"đã có {len(segments)} đoạn")
        transcript_id = self._repos.add_transcript(
            source_id=source_id, engine=job.engine or "", lang=lang, segments=segments,
        )
        report(0.95, f"lưu transcript #{transcript_id}")

        if (self._repos.get_setting(AUTO_FORWARD_SETTING, "1") or "1") == "1":
            self._forward_to_translation(transcript_id, lang)
            report(0.98, "đã tạo job dịch ở workspace 2")
        else:
            report(0.98, "giữ lại để sửa (auto_forward tắt)")
        report(1.0, "xong")

    def _forward_to_translation(self, transcript_id: int, lang: str) -> None:
        """Tạo HÀNG `translations` trước, rồi mới xếp job `translate`.

        Thứ tự này là bắt buộc, không phải phong cách: `TranslateHandler` ghi
        checkpoint và trạng thái lên hàng đó, và nó tra `translation_id` từ
        payload. Không có hàng thì job tự sinh sẽ `NotFound`/`KeyError` ở tận
        worker — đúng lớp lỗi mà Giai đoạn 1a đã trả giá (handler được dựng mà
        thiếu thứ nó cần).

        Payload là ĐÚNG năm khoá `TranslateHandler.run` đọc
        (`pipeline/translate.py:71-77`): `translation_id`, `transcript_id`,
        `engine_id`, `source_lang`, `target_lang`. `source_id` đã bị bỏ: handler
        dịch không đọc nó, còn nguồn thì tra được qua transcript.

        `transcript_version` là version của transcript VỪA tạo (đọc lại từ
        repo), không phải "version hiện tại" tại thời điểm job chạy — job có thể
        chạy sau khi người dùng sửa transcript, và khi đó bản dịch này phải được
        coi là lệch thời (`is_stale`).
        """
        engine_id = self._default_mt_engine()
        transcript = self._repos.get_transcript(transcript_id)
        translation_id = self._repos.add_translation(
            transcript_id=transcript_id,
            transcript_version=transcript.version,
            engine=engine_id or "",
            target_lang=DEFAULT_TARGET_LANG,
            segments=[],
            prompt_version=self._prompt_versions.get(engine_id or "", "unknown"),
            status="queued",
        )
        self._repos.add_job(Job(
            id=None, workspace=2, type="translate", engine=engine_id,
            phase=js.phase_of("translate", engine_id),
            payload={
                "translation_id": translation_id,
                "transcript_id": transcript_id,
                "engine_id": engine_id,
                "source_lang": lang,
                "target_lang": DEFAULT_TARGET_LANG,
            },
        ))

    def _default_mt_engine(self) -> str | None:
        """Engine dịch mặc định — DỮ LIỆU, không phải thứ tự dòng trong registry.

        R58/WQ-02: bản cũ lấy thẳng `mt_specs[0].id`, tức thứ tự mảng `mt` của
        `registry.json` quyết định engine mặc định của cả pipeline (hiện ra đúng
        `opus-mt` chỉ do may). Nay khoá `default_mt` do `main.py` nạp được ưu
        tiên; chỉ khi registry không khai báo gì thì mới rơi về phần tử đầu.
        """
        return default_mt_engine(
            self._specs,
            declared=self._declared_default_mt,
            configured=self._repos.get_setting(MT_DEFAULT_SETTING),
        )
