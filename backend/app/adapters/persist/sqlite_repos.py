from __future__ import annotations

import json
import pathlib
import sqlite3
from typing import Iterable

from app.domain import job_state as js
from app.domain.models import (
    Job, Segment, Source, Term, Transcript,
    segments_from_json, segments_to_json,
)
from app.ports.clock import Clock

from .schema import SCHEMA_SQL, SCHEMA_VERSION

LOG_TAIL_LINES = 100


class NotFound(LookupError):
    pass


class SqliteRepos:
    """Hiện thực Repos trên SQLite.

    Một kết nối cho mỗi luồng gọi. GĐ1a chỉ có một worker + các request FastAPI
    đọc, nên khoá ghi ở mức kết nối là đủ.
    """

    def __init__(self, db_path: str | pathlib.Path, *, clock: Clock) -> None:
        self.db_path = str(db_path)
        self._clock = clock

    # ---------- hạ tầng ----------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self) -> None:
        pathlib.Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES('version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    # ---------- sources ----------
    def add_source(self, *, kind: str, origin: str, media_path: str,
                   lang: str | None = None, audio_path: str | None = None,
                   duration: float | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO sources(kind, origin, media_path, audio_path, duration, lang, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (kind, origin, media_path, audio_path, duration, lang, self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def get_source(self, source_id: int) -> Source:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise NotFound(f"source {source_id} không tồn tại")
        return Source(id=row["id"], kind=row["kind"], origin=row["origin"],
                      media_path=row["media_path"], lang=row["lang"],
                      audio_path=row["audio_path"], duration=row["duration"],
                      created_at=row["created_at"])

    def set_source_audio(self, source_id: int, audio_path: str, duration: float) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sources SET audio_path=?, duration=? WHERE id=?",
                         (audio_path, duration, source_id))

    # ---------- transcripts ----------
    def add_transcript(self, *, source_id: int, engine: str, lang: str,
                       segments: list[Segment]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO transcripts(source_id, engine, lang, segments, version, status, created_at)"
                " VALUES(?,?,?,?,1,'draft',?)",
                (source_id, engine, lang, segments_to_json(segments), self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def _row_to_transcript(self, row: sqlite3.Row) -> Transcript:
        return Transcript(
            id=row["id"], source_id=row["source_id"], engine=row["engine"],
            lang=row["lang"], segments=segments_from_json(row["segments"]),
            version=row["version"], status=row["status"], created_at=row["created_at"],
        )

    def get_transcript(self, transcript_id: int) -> Transcript:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM transcripts WHERE id=?", (transcript_id,)).fetchone()
        if row is None:
            raise NotFound(f"transcript {transcript_id} không tồn tại")
        return self._row_to_transcript(row)

    def list_transcripts(self) -> list[Transcript]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM transcripts ORDER BY id DESC").fetchall()
        return [self._row_to_transcript(r) for r in rows]

    def update_transcript_segments(self, transcript_id: int,
                                  segments: list[Segment]) -> int:
        """Ghi segments và TĂNG version. Trả về version mới.

        Version tăng là cơ chế duy nhất khiến bản dịch cũ thành 'lỗi thời'.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT version FROM transcripts WHERE id=?",
                               (transcript_id,)).fetchone()
            if row is None:
                raise NotFound(f"transcript {transcript_id} không tồn tại")
            new_version = int(row["version"]) + 1
            conn.execute("UPDATE transcripts SET segments=?, version=? WHERE id=?",
                         (segments_to_json(segments), new_version, transcript_id))
            return new_version

    def set_transcript_status(self, transcript_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE transcripts SET status=? WHERE id=?", (status, transcript_id))

    # ---------- jobs ----------
    def add_job(self, job: Job) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO jobs(workspace, type, engine, phase, state, cancel_requested,"
                " attempts, progress, log_tail, log_path, error, payload, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job.workspace, job.type, job.engine, job.phase, job.state,
                 int(job.cancel_requested), job.attempts, job.progress, job.log_tail,
                 job.log_path, job.error, json.dumps(job.payload or {}, ensure_ascii=False),
                 job.created_at or self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"], workspace=row["workspace"], type=row["type"], engine=row["engine"],
            phase=row["phase"], state=row["state"],
            cancel_requested=bool(row["cancel_requested"]), attempts=row["attempts"],
            progress=row["progress"], log_tail=row["log_tail"], log_path=row["log_path"],
            error=row["error"], payload=json.loads(row["payload"] or "{}"),
            created_at=row["created_at"], started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    def get_job(self, job_id: int) -> Job:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise NotFound(f"job {job_id} không tồn tại")
        return self._row_to_job(row)

    def list_jobs(self, *, states: tuple[str, ...] | None = None) -> list[Job]:
        sql = "SELECT * FROM jobs"
        params: tuple = ()
        if states:
            sql += f" WHERE state IN ({','.join('?' * len(states))})"
            params = tuple(states)
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_job(r) for r in rows]

    def oldest_queued(self) -> Job | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE state=? ORDER BY id LIMIT 1", (js.QUEUED,)
            ).fetchone()
        return self._row_to_job(row) if row else None

    def next_queued_for_phase(self, phase: str) -> Job | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE state=? AND phase=? ORDER BY id LIMIT 1",
                (js.QUEUED, phase),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def set_job_state(self, job_id: int, state: str, *, error: str | None = None) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise NotFound(f"job {job_id} không tồn tại")
            if row["state"] == state:
                # Ghi lại ĐÚNG trạng thái hàng đang có không phải một "chuyển"
                # nên bảng transition không áp dụng: `queued -> queued` không có
                # trong `_TRANSITIONS` (self-loop bị cấm) nhưng gọi nó là lỗi thì
                # sai — người gọi chỉ đang bảo đảm trạng thái, không đổi nó.
                # Chuyển thật vẫn phải qua `assert_transition` ngay dưới đây, nên
                # `done -> running` vẫn nổ InvalidTransition như cũ.
                return
            js.assert_transition(row["state"], state)
            now = self._clock.now_iso()
            if state == js.RUNNING:
                conn.execute(
                    "UPDATE jobs SET state=?, started_at=COALESCE(started_at, ?), error=NULL WHERE id=?",
                    (state, now, job_id))
            elif state in (js.DONE, js.FAILED, js.INTERRUPTED, js.CANCELLED):
                conn.execute(
                    "UPDATE jobs SET state=?, finished_at=?, error=COALESCE(?, error) WHERE id=?",
                    (state, now, error, job_id))
            else:
                conn.execute("UPDATE jobs SET state=?, finished_at=NULL, error=? WHERE id=?",
                             (state, error, job_id))

    def set_job_progress(self, job_id: int, progress: float) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET progress=? WHERE id=?",
                         (max(0.0, min(1.0, float(progress))), job_id))

    def append_job_log(self, job_id: int, line: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT log_tail FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise NotFound(f"job {job_id} không tồn tại")
            lines = (row["log_tail"] + "\n" + line).splitlines()[-LOG_TAIL_LINES:]
            conn.execute("UPDATE jobs SET log_tail=? WHERE id=?",
                         ("\n".join(lines), job_id))

    def request_cancel(self, job_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (job_id,))

    def mark_running_as_interrupted(self) -> int:
        """Gọi lúc khởi động. Không có nó thì worker chết giữa job sẽ để job
        treo vĩnh viễn ở `running` và giao diện hiện 'đang chạy' mãi mãi."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE jobs SET state=?, finished_at=? WHERE state=?",
                (js.INTERRUPTED, self._clock.now_iso(), js.RUNNING),
            )
            return int(cur.rowcount)

    def retry_job(self, job_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT state, attempts FROM jobs WHERE id=?",
                               (job_id,)).fetchone()
            if row is None:
                raise NotFound(f"job {job_id} không tồn tại")
            js.assert_transition(row["state"], js.QUEUED)
            conn.execute(
                "UPDATE jobs SET state=?, attempts=attempts+1, finished_at=NULL,"
                " error=NULL, progress=0 WHERE id=?",
                (js.QUEUED, job_id),
            )

    # ---------- glossary / settings / calls ----------
    def upsert_term(self, *, lang: str, term: str, translation: str,
                    note: str | None, approved: bool) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO glossary(lang, term, translation, note, approved, created_at)"
                " VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(lang, term) DO UPDATE SET translation=excluded.translation,"
                " note=excluded.note, approved=excluded.approved",
                (lang, term, translation, note, int(approved), self._clock.now_iso()),
            )
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('glossary_version', '1')"
                " ON CONFLICT(key) DO UPDATE SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT)"
            )
            return int(cur.lastrowid or 0)

    def list_terms(self, *, lang: str | None = None) -> list[Term]:
        sql = "SELECT * FROM glossary"
        params: tuple = ()
        if lang:
            sql += " WHERE lang=?"
            params = (lang,)
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Term(id=r["id"], lang=r["lang"], term=r["term"],
                     translation=r["translation"], note=r["note"],
                     approved=bool(r["approved"]), created_at=r["created_at"])
                for r in rows]

    def glossary_version(self) -> int:
        return int(self.get_setting("glossary_version", "0") or "0")

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def add_llm_call(self, *, job_id: int | None, engine: str, model_ref: str | None,
                     prompt_version: str | None, tokens_in: int | None,
                     tokens_out: int | None, duration_ms: int | None,
                     ok: bool, error: str | None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO llm_calls(job_id, engine, model_ref, prompt_version,"
                " tokens_in, tokens_out, duration_ms, ok, error, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (job_id, engine, model_ref, prompt_version, tokens_in, tokens_out,
                 duration_ms, int(ok), error, self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def list_llm_calls(self, job_id: int | None = None) -> list[dict]:
        sql = "SELECT * FROM llm_calls"
        params: tuple = ()
        if job_id is not None:
            sql += " WHERE job_id=?"
            params = (job_id,)
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
