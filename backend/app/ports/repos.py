"""Giao diện lưu trữ. Chỉ là Protocol — không hiện thực gì ở đây."""
from __future__ import annotations

from typing import Protocol

from app.domain.models import (CallStats, Job, Segment, Source, Term, Transcript,
                               Translation, TranslationSummary)


class Repos(Protocol):
    # sources
    def add_source(self, *, kind: str, origin: str, media_path: str,
                   lang: str | None = None, audio_path: str | None = None,
                   duration: float | None = None) -> int: ...
    def get_source(self, source_id: int) -> Source: ...
    def list_sources(self) -> list[Source]: ...
    def set_source_audio(self, source_id: int, audio_path: str, duration: float) -> None: ...
    def delete_source(self, source_id: int) -> None:
        """Xoá MỘT nguồn cùng MỌI transcript và MỌI bản dịch của nó.

        Vì sao cascade phải TƯỜNG MINH chứ không dựa vào schema: `schema.py` khai
        `REFERENCES sources(id)`/`REFERENCES transcripts(id)` mà KHÔNG có
        `ON DELETE CASCADE`, nên `DELETE FROM sources` khi còn transcript sẽ bị
        `PRAGMA foreign_keys=ON` từ chối (`FOREIGN KEY constraint failed`) — và
        nếu ai đó tắt ràng buộc thì thứ ở lại là transcript mồ côi, hiện lên
        `GET /api/transcripts` và trỏ vào một kênh không còn tồn tại. Ba câu lệnh
        (translations → transcripts → sources) PHẢI nằm trong CÙNG một giao dịch:
        chết giữa chừng ở câu thứ hai là để lại một nguồn đã mất bản dịch nhưng
        còn transcript.

        Thứ tự là bắt buộc: `translations.transcript_id` trỏ tới `transcripts`, nên
        bản dịch phải đi TRƯỚC transcript của nó.

        Id không tồn tại ném `LookupError` (cùng lớp `NotFound` với `get_source`),
        không phải no-op: người gọi là một route `DELETE` đã hứa 404 cho id lạ, và
        một lần xoá "thành công" trên hàng không có là câu trả lời sai.

        Hàm này KHÔNG chạm bảng `jobs` và KHÔNG chạm tệp trên đĩa: quyết định
        "có được xoá không" (409 khi còn job sống) là của tầng route, còn tệp
        media nằm NGOÀI giao dịch SQLite (xem `routes_sources.delete_source`).
        """
        ...
    def delete_translation(self, translation_id: int) -> None:
        """Xoá MỘT hàng `translations`. Không chạm transcript của nó.

        Bản dịch là con của transcript, nên xoá con không cần cascade. Id không
        tồn tại ném `LookupError`, cùng lý do với `delete_source`.
        """
        ...

    # transcripts
    def add_transcript(self, *, source_id: int, engine: str, lang: str,
                       segments: list[Segment]) -> int: ...
    def get_transcript(self, transcript_id: int) -> Transcript: ...
    def list_transcripts(self) -> list[Transcript]: ...
    def update_transcript_segments(self, transcript_id: int,
                                   segments: list[Segment]) -> int: ...
    def update_transcript_segment_timing(self, transcript_id: int, i: int,
                                         start: float, end: float) -> None:
        """Đổi MỐC của ĐÚNG MỘT đoạn. **KHÔNG** tăng `version`.

        Vì sao không tăng version — đây là quyết định hợp đồng, không phải tối ưu:

        `version` là "bản phiên âm này đã đổi NỘI DUNG CHỮ". Nó tồn tại để
        `is_stale(transcript_version, translated_from_version)` biết một bản dịch
        đã dịch từ bản ghi cũ. Sửa `start`/`end` KHÔNG làm bản dịch sai nghĩa:
        câu chữ vẫn là câu đó, bản dịch vẫn đúng. Chỉ có thời điểm đổi.

        Trước phương thức này, mọi lần kéo một mốc đi qua
        `PATCH /api/transcripts/{id}`, tức gửi TOÀN BỘ danh sách đoạn và
        `update_transcript_segments` tăng version ⇒ MỌI bản dịch thành `stale`
        chỉ vì người dùng dời một mốc 0,1 giây (ERRATA #55).

        ⚠️ Hệ quả phải nói ra: sửa mốc KHÔNG làm bản dịch lỗi thời, nên một bản
        dịch đã `stale` từ trước vẫn `stale` sau khi sửa mốc — đúng, vì nó vẫn
        dịch từ bản ghi cũ.
        """
        ...
    def set_transcript_status(self, transcript_id: int, status: str) -> None: ...

    # translations
    def add_translation(self, *, transcript_id: int, transcript_version: int,
                        engine: str, target_lang: str, segments: list[Segment],
                        prompt_version: str, glossary_version: int | None = None,
                        qa_issues: list[str] | None = None,
                        tokens_in: int | None = None, tokens_out: int | None = None,
                        duration_ms: int | None = None,
                        status: str = "queued") -> int: ...
    def get_translation(self, translation_id: int) -> Translation: ...
    def update_translation_segments(self, translation_id: int,
                                    segments: list[Segment]) -> None: ...
    def set_translation_status(self, translation_id: int, status: str, *,
                               qa_issues: list[str] | None = None,
                               tokens_in: int | None = None,
                               tokens_out: int | None = None,
                               duration_ms: int | None = None,
                               glossary_version: int | None = None) -> None: ...
    def list_translations(self) -> list[Translation]: ...
    def list_translations_for_transcript(
        self, transcript_id: int) -> list[TranslationSummary]: ...

    # jobs
    def add_job(self, job: Job) -> int: ...
    def get_job(self, job_id: int) -> Job: ...
    def list_jobs(self, *, states: tuple[str, ...] | None = None) -> list[Job]: ...
    def oldest_queued(self) -> Job | None: ...
    def next_queued_for_phase(self, phase: str) -> Job | None: ...
    def set_job_state(self, job_id: int, state: str, *,
                      error: str | None = None) -> None:
        """Chuyển trạng thái job, có kiểm tra bảng transition.

        Hiện thực PHẢI đọc trạng thái hiện tại từ hàng (không tin giá trị truyền
        vào) rồi gọi `job_state.assert_transition(current, state)` TRƯỚC khi ghi,
        nên một chuyển không hợp lệ ném `InvalidTransition` và không đụng vào hàng.

        Ghi lại ĐÚNG trạng thái hàng đang có là NO-OP (idempotent), KHÔNG ném lỗi:
        `queued -> queued` không có trong bảng transition, mà người gọi chỉ đang
        bảo đảm trạng thái chứ không đổi nó. Hệ quả cần biết trước: gọi
        `set_job_state(id, FAILED, error="...")` trên một hàng đã `failed` sẽ GIỮ
        NGUYÊN `error` cũ — nhánh làm mới error đó là không tới được.
        """
        ...
    def set_job_progress(self, job_id: int, progress: float) -> None: ...
    def append_job_log(self, job_id: int, line: str) -> None: ...
    def request_cancel(self, job_id: int) -> None: ...
    def mark_running_as_interrupted(self) -> int: ...
    def set_translations_status(self, translation_ids: list[int], status: str) -> int:
        """Ghi CÙNG một trạng thái cho nhiều hàng `translations`, trả số hàng đã sửa.

        Dùng để đối chiếu một bản dịch với SỐ PHẬN của job đứng sau nó: job bị
        huỷ lúc còn `queued` hoặc bị ngắt giữa lúc chạy thì KHÔNG còn gì chạm
        vào hàng dịch nữa, nên nó phải rời `queued`/`running` — nếu không
        `translations.status` đứng nguyên ở `queued` VĨNH VIỄN và
        `GET /api/translations` (Task 13 phơi cột này) hiện một bản dịch "đang
        chờ" không bao giờ chạy.

        Danh sách rỗng là NO-OP trả `0`, không phải lỗi: người gọi tra id từ
        payload job, và một job không mang `translation_id` (mọi job `asr`/
        `ingest`/`export`) là chuyện bình thường.

        Hiện thực KHÔNG được ghi đè một hàng đã ở trạng thái kết thúc
        (`done`/`failed`/`cancelled`): `done` là kết quả của một lần chạy thật, và
        một lần đối chiếu muộn không được xoá nó. Hai trạng thái còn sửa được là
        `app.domain.models.UNSETTLED_TRANSLATION_STATUSES`.
        """
        ...
    def retry_job(self, job_id: int) -> None: ...

    # glossary / settings / calls
    def upsert_term(self, *, lang: str, term: str, translation: str,
                    note: str | None, approved: bool) -> int: ...
    def list_terms(self, *, lang: str | None = None) -> list[Term]: ...
    def glossary_version(self) -> int: ...
    def get_setting(self, key: str, default: str | None = None) -> str | None: ...
    def set_setting(self, key: str, value: str) -> None: ...
    def add_llm_call(self, *, job_id: int | None, engine: str, model_ref: str | None,
                     prompt_version: str | None, tokens_in: int | None,
                     tokens_out: int | None, duration_ms: int | None,
                     ok: bool, error: str | None) -> int: ...
    def list_llm_calls(self, job_id: int | None = None) -> list[dict]: ...
    def token_stats(self) -> list[dict]:
        """Thống kê token của MỌI lời gọi engine, gộp theo `(engine, model_ref)`.

        Mỗi hàng: `engine`, `model_ref`, `calls`, `ok_calls`, `tokens_in`, `tokens_out`,
        `duration_ms`. Tổng nào chưa đo được thì là `None` — engine in-process (`opus-mt`)
        không có token, và "không đo được" KHÔNG được thay bằng `0` (một số 0 đọc như "đã đo
        và bằng không", trong khi sự thật là engine đó không báo gì).
        """
        ...
