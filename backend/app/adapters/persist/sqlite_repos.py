from __future__ import annotations

import contextlib
import json
import pathlib
import sqlite3
from typing import Iterable, Iterator

from app.domain import job_state as js
from app.domain.models import (
    Job, Segment, Source, Term, Transcript, Translation,
    TranslationSummary, segments_from_json, segments_to_json,
)
from app.ports.clock import Clock

from .schema import SCHEMA_SQL, SCHEMA_VERSION

LOG_TAIL_LINES = 100


class NotFound(LookupError):
    pass


class SqliteRepos:
    """Hiện thực Repos trên SQLite.

    Một kết nối cho mỗi LẦN GỌI (không phải mỗi luồng): `_connect()` mở mới rồi
    bỏ đi khi phương thức trả về. GĐ1a chỉ có một worker + các request FastAPI
    đọc, nên khoá ghi ở mức kết nối là đủ.

    CẢNH BÁO: `isolation_level=None` đặt kết nối vào chế độ autocommit, nên
    `with self._connect() as conn:` KHÔNG mở giao dịch và KHÔNG thể rollback —
    mỗi câu lệnh tự commit ngay khi chạy. Vì vậy phương thức nào ghi nhiều hơn
    một câu lệnh PHẢI tự bọc `with self._tx(conn):` (xem `upsert_term` và
    `update_transcript_segments`); nếu không, một lần chết giữa chừng sẽ để dữ
    liệu lệch nhau mà không có gì cuốn lại.
    """

    def __init__(self, db_path: str | pathlib.Path, *, clock: Clock,
                 log_dir: str | pathlib.Path | None = None) -> None:
        self.db_path = str(db_path)
        self._clock = clock
        #: `None` = không ghi log ra tệp (test dựng repos trần, hành vi cũ). Có
        #: giá trị thì mỗi job được một tệp `job-<id>.log` dưới thư mục này —
        #: spec §5.5: log đầy đủ nằm ở TỆP, `jobs.log_tail` chỉ giữ 100 dòng
        #: cuối cho UI. `main.py` truyền `config.LOG_DIR` (đã được
        #: `ensure_dirs()` tạo), nên cột `log_path` không còn là trường chết.
        self._log_dir = pathlib.Path(log_dir) if log_dir is not None else None

    # ---------- hạ tầng ----------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextlib.contextmanager
    def _tx(self, conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        """Giao dịch tường minh: `BEGIN IMMEDIATE` ... `COMMIT`, lỗi thì `ROLLBACK`.

        Cần thiết vì `isolation_level=None` khiến `with conn:` chỉ là no-op:
        không có `BEGIN` thì mỗi câu lệnh tự commit, nên đọc-rồi-ghi không còn
        là một khối nguyên tử và một lần chết giữa hai câu lệnh để lại dữ liệu
        lệch. `IMMEDIATE` (không phải `DEFERRED`) để khoá ghi được lấy ngay lúc
        mở, tránh hai người ghi cùng đọc một giá trị rồi cùng ghi đè nhau.
        """
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    #: Các bước migration, khai báo TƯỜNG MINH theo thứ tự tăng dần của `version`:
    #: `(version, table, column, ddl)`. Cố tình không tách tên bảng/cột ra từ
    #: chuỗi DDL: cách đó chỉ đúng với đúng một câu `ALTER TABLE ... ADD COLUMN`
    #: và sẽ phân tích sai ngay khi thêm bước thứ hai (đổi kiểu, backfill dữ
    #: liệu, `ALTER TABLE ... RENAME`).
    #:
    #: Mỗi bước PHẢI idempotent: chạy lại trên DB đã migrate là no-op, không ném.
    _MIGRATIONS: tuple[tuple[int, str, str, str], ...] = (
        (2, "translations", "status",
         "ALTER TABLE translations ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'"),
    )

    def _column_names(self, conn: sqlite3.Connection, table: str) -> set[str]:
        """Tên cột THẬT của bảng, đọc từ `PRAGMA table_info`.

        Đây là nguồn sự thật duy nhất về schema đang có trên đĩa — xem
        `_apply_migrations` để biết vì sao KHÔNG được tin `schema_meta.version`.
        """
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        """Áp mọi bước migration mà schema THẬT còn thiếu.

        `CREATE TABLE IF NOT EXISTS` KHÔNG thêm cột vào bảng đã tồn tại, nên một
        DB Giai đoạn 1a sẽ thiếu `translations.status` trong khi
        `schema_meta.version` vẫn bị ghi thành số mới — hỏng âm thầm. Vì vậy
        `version` chỉ dùng để SẮP THỨ TỰ các bước, tuyệt đối không dùng làm cổng
        chặn: một DB đã bị ghi nhầm version (đúng cái bug này) vẫn phải tự vá
        được ở lần chạy sau. Điều kiện duy nhất để bỏ qua một bước là cột đích đã
        có thật, nhờ đó chạy lại là no-op thay vì `duplicate column name`.
        """
        for _version, table, column, ddl in sorted(self._MIGRATIONS):
            if column in self._column_names(conn, table):
                continue
            conn.execute(ddl)

    def init_schema(self) -> None:
        pathlib.Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._apply_migrations(conn)
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

    def _row_to_source(self, row: sqlite3.Row) -> Source:
        return Source(id=row["id"], kind=row["kind"], origin=row["origin"],
                      media_path=row["media_path"], lang=row["lang"],
                      audio_path=row["audio_path"], duration=row["duration"],
                      created_at=row["created_at"])

    def get_source(self, source_id: int) -> Source:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise NotFound(f"source {source_id} không tồn tại")
        return self._row_to_source(row)

    def list_sources(self) -> list[Source]:
        """Nguồn mới nhất trước — cùng thứ tự với `list_transcripts`."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM sources ORDER BY id DESC").fetchall()
        return [self._row_to_source(r) for r in rows]

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

        Đọc version rồi ghi version+1 phải nằm trong CÙNG một giao dịch: nếu
        không, hai lời gọi song song cùng đọc version N và cùng ghi N+1, mất một
        lần tăng — và một bản dịch đáng lẽ bị coi là lỗi thời sẽ không bị.
        """
        with self._connect() as conn:
            with self._tx(conn):
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

    # ---------- translations ----------
    def _row_to_translation(self, row: sqlite3.Row) -> Translation:
        return Translation(
            id=row["id"], transcript_id=row["transcript_id"],
            transcript_version=row["transcript_version"], engine=row["engine"],
            segments=segments_from_json(row["segments"]),
            prompt_version=row["prompt_version"], target_lang=row["target_lang"],
            glossary_version=row["glossary_version"],
            qa_issues=json.loads(row["qa_issues"] or "[]"),
            tokens_in=row["tokens_in"], tokens_out=row["tokens_out"],
            duration_ms=row["duration_ms"], created_at=row["created_at"],
        )

    def list_translations(self) -> list[Translation]:
        """Bản dịch mới nhất trước — đối xứng với `list_transcripts`/`list_sources`.

        GĐ1a chưa có handler `translate` nên chưa có ai GHI bảng này; phương thức
        đọc vẫn phải có trên cổng, nếu không thì route bản dịch (Task 18) lại
        phải mở thẳng tệp SQLite đúng như `routes_sources.py` từng làm (R74).
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM translations ORDER BY id DESC").fetchall()
        return [self._row_to_translation(r) for r in rows]

    def add_translation(self, *, transcript_id: int, transcript_version: int,
                        engine: str, target_lang: str, segments: list[Segment],
                        prompt_version: str, glossary_version: int | None = None,
                        qa_issues: list[str] | None = None,
                        tokens_in: int | None = None, tokens_out: int | None = None,
                        duration_ms: int | None = None) -> int:
        """Ghi một bản dịch.

        `transcript_version` là version của transcript mà bản dịch này dịch TỪ —
        không phải version hiện tại của transcript. Đây chính là giá trị mà
        `is_stale()` so với version hiện tại; ghi nhầm thành "version hiện tại"
        thì mọi bản dịch vừa dịch xong đều trông như đã lỗi thời.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO translations(transcript_id, transcript_version, engine,"
                " target_lang, segments, prompt_version, glossary_version, qa_issues,"
                " tokens_in, tokens_out, duration_ms, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (transcript_id, transcript_version, engine, target_lang,
                 segments_to_json(segments), prompt_version, glossary_version,
                 json.dumps(qa_issues or [], ensure_ascii=False), tokens_in,
                 tokens_out, duration_ms, self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def list_translations_for_transcript(
            self, transcript_id: int) -> list[TranslationSummary]:
        """Tóm tắt bản dịch của MỘT transcript, mới nhất trước.

        Cố tình không `SELECT *`: cột `segments` là cả một bản dịch đã giải mã
        JSON, mà route chỉ cần biết bản dịch dịch từ version nào để tính `stale`.
        Danh sách này còn bị gọi cho TỪNG transcript ở route danh sách.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, transcript_id, transcript_version, engine, target_lang,"
                " prompt_version, created_at FROM translations"
                " WHERE transcript_id=? ORDER BY id DESC",
                (transcript_id,),
            ).fetchall()
        return [TranslationSummary(
            id=r["id"], transcript_id=r["transcript_id"],
            transcript_version=r["transcript_version"], engine=r["engine"],
            target_lang=r["target_lang"], prompt_version=r["prompt_version"],
            created_at=r["created_at"],
        ) for r in rows]

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
        if states is not None:
            if not states:
                # Lọc theo tập rỗng nghĩa là KHÔNG trạng thái nào khớp -> rỗng.
                # (`if states:` cũ trả về TẤT CẢ job; còn `IN ()` là cú pháp sai
                # trong SQLite nên không thể nhét thẳng tập rỗng vào IN.)
                return []
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
        """Nối một dòng vào log của job: `log_tail` (cho UI) + TỆP nếu có `log_dir`.

        `log_path` được gán ngay lần ghi log đầu tiên, nên cột đó (và hằng số
        `dirs["log"]` của `app.state`) không còn là hợp đồng chết của spec §5.5.
        Không có `log_dir` thì hành vi y hệt bản cũ: chỉ `log_tail`.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT log_tail FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise NotFound(f"job {job_id} không tồn tại")
            lines = (row["log_tail"] + "\n" + line).splitlines()[-LOG_TAIL_LINES:]
            path = self._append_to_job_log_file(job_id, line)
            if path is None:
                conn.execute("UPDATE jobs SET log_tail=? WHERE id=?",
                             ("\n".join(lines), job_id))
            else:
                conn.execute("UPDATE jobs SET log_tail=?, log_path=? WHERE id=?",
                             ("\n".join(lines), str(path), job_id))

    def _append_to_job_log_file(self, job_id: int, line: str) -> pathlib.Path | None:
        """Ghi thêm một dòng vào `<log_dir>/job-<id>.log`; `None` nếu không có `log_dir`."""
        if self._log_dir is None:
            return None
        path = self._log_dir / f"job-{job_id}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return path

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
        """Ghi một thuật ngữ và TĂNG `glossary_version`, trong CÙNG giao dịch.

        Hai câu lệnh phải nguyên tử với nhau: nếu hàng glossary landed mà
        `glossary_version` không tăng, glossary và version lệch nhau — mà
        `glossary_version` chính là thứ quyết định một bản dịch có lỗi thời hay
        không.

        Trả về id của hàng: `RETURNING id` cho id đúng ở cả nhánh INSERT lẫn
        nhánh `ON CONFLICT ... DO UPDATE` (nếu trả `lastrowid`, nhánh update cho
        ra 0 dù hàng có id thật).
        """
        with self._connect() as conn:
            with self._tx(conn):
                cur = conn.execute(
                    "INSERT INTO glossary(lang, term, translation, note, approved, created_at)"
                    " VALUES(?,?,?,?,?,?)"
                    " ON CONFLICT(lang, term) DO UPDATE SET translation=excluded.translation,"
                    " note=excluded.note, approved=excluded.approved"
                    " RETURNING id",
                    (lang, term, translation, note, int(approved), self._clock.now_iso()),
                )
                row = cur.fetchone()
                if row is None:
                    raise RuntimeError("upsert_term: RETURNING id không trả về hàng nào")
                term_id = int(row["id"])
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES('glossary_version', '1')"
                    " ON CONFLICT(key) DO UPDATE SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT)"
                )
            return term_id

    def list_terms(self, *, lang: str | None = None) -> list[Term]:
        sql = "SELECT * FROM glossary"
        params: tuple = ()
        if lang is not None:
            # `is not None`, không phải `if lang:`: lọc theo chuỗi rỗng là lọc
            # thật (và phải ra rỗng), không phải "bỏ lọc, trả mọi ngôn ngữ".
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
