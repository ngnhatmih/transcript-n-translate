from __future__ import annotations

import contextlib
import json
import pathlib
import sqlite3
from typing import Iterable, Iterator

from app.domain import job_state as js
from app.domain.models import (
    UNSETTLED_TRANSLATION_STATUSES, Job, Segment, Source, Term, Transcript,
    Translation, TranslationSummary, segments_from_json, segments_to_json,
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
        # `chimera` cho phép NULL và KHÔNG có default: một hàng cũ (và mọi hàng
        # dịch thường) mang NULL, nghĩa là "không chạy ở chế độ Chimera" — khác hẳn
        # `'{}'`, thứ sẽ nói "có chạy, mà không có ứng viên nào".
        (3, "translations", "chimera",
         "ALTER TABLE translations ADD COLUMN chimera TEXT"),
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

    def delete_source(self, source_id: int) -> None:
        """Xoá nguồn + MỌI transcript + MỌI bản dịch của nó, trong MỘT giao dịch.

        Ba vì sao của hình dạng này:

        * **Cascade viết tay.** `schema.py` khai `REFERENCES sources(id)` mà không
          có `ON DELETE CASCADE`. `_connect()` bật `PRAGMA foreign_keys=ON`, nên
          xoá nguồn khi còn transcript ném `FOREIGN KEY constraint failed`; còn
          nếu ai đó tắt ràng buộc thì lại để lại transcript mồ côi trỏ vào kênh
          đã mất — hiện lên `GET /api/transcripts` như một bản ghi thật.
        * **Thứ tự.** `translations.transcript_id` trỏ tới `transcripts`, nên bản
          dịch đi TRƯỚC transcript của nó, transcript đi trước nguồn.
        * **Một `_tx`.** Chết sau câu thứ hai mà câu thứ ba chưa chạy là dữ liệu
          lệch: một nguồn đã mất bản dịch nhưng vẫn còn transcript.

        `SELECT 1 FROM sources` TRƯỚC khi xoá là chỗ duy nhất phát hiện id lạ:
        `DELETE` không khớp hàng nào vẫn "thành công", nên chỉ nhìn `rowcount` của
        các câu sau là không đủ (chúng bằng 0 một cách hợp lệ khi nguồn không có
        transcript nào). Đọc trong CÙNG giao dịch để hai lời gọi song song không
        cùng thấy hàng rồi cùng xoá.

        KHÔNG chạm bảng `jobs` (job là lịch sử chạy, không phải con của nguồn) và
        KHÔNG chạm tệp trên đĩa — route xoá tệp SAU giao dịch này, xem
        `routes_sources.delete_source`.
        """
        with self._connect() as conn:
            with self._tx(conn):
                row = conn.execute("SELECT 1 FROM sources WHERE id=?",
                                   (source_id,)).fetchone()
                if row is None:
                    raise NotFound(f"source {source_id} không tồn tại")
                conn.execute(
                    "DELETE FROM translations WHERE transcript_id IN"
                    " (SELECT id FROM transcripts WHERE source_id=?)",
                    (source_id,),
                )
                conn.execute("DELETE FROM transcripts WHERE source_id=?", (source_id,))
                conn.execute("DELETE FROM sources WHERE id=?", (source_id,))

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
            duration_ms=row["duration_ms"], status=row["status"],
            # Cột có thể VẮNG trên một DB chưa migrate (migration chạy trong
            # `init_schema`, nhưng `_row_to_translation` cũng được gọi từ những
            # đường chỉ mở kết nối) — đọc bằng `getattr`-kiểu-dict ở đây là một
            # `IndexError` chờ sẵn. Dùng `row.keys()` để nói rõ ý định.
            chimera=_chimera_from_row(row),
            created_at=row["created_at"],
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
                        duration_ms: int | None = None,
                        chimera: dict | None = None,
                        status: str = "queued") -> int:
        """Ghi một bản dịch.

        `transcript_version` là version của transcript mà bản dịch này dịch TỪ —
        không phải version hiện tại của transcript. Đây chính là giá trị mà
        `is_stale()` so với version hiện tại; ghi nhầm thành "version hiện tại"
        thì mọi bản dịch vừa dịch xong đều trông như đã lỗi thời.

        `status` được GHI TƯỜNG MINH chứ không để cột tự lấy default: GĐ1a không
        có ai ghi cột này, nên default `'queued'` của schema chưa từng được ghim;
        một bản dịch tạo ra ở trạng thái khác phải đọc lên đúng trạng thái đó.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO translations(transcript_id, transcript_version, engine,"
                " target_lang, segments, prompt_version, glossary_version, qa_issues,"
                " tokens_in, tokens_out, duration_ms, chimera, status, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (transcript_id, transcript_version, engine, target_lang,
                 segments_to_json(segments), prompt_version, glossary_version,
                 json.dumps(qa_issues or [], ensure_ascii=False), tokens_in,
                 tokens_out, duration_ms,
                 None if chimera is None else json.dumps(chimera, ensure_ascii=False),
                 status, self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def get_translation(self, translation_id: int) -> Translation:
        """Một bản dịch đầy đủ (có `segments`) theo id.

        Ném `NotFound` chứ không trả `None`: người gọi là handler dịch, và một
        `None` lọt xuống đó sẽ thành `AttributeError` ở tận đâu đó thay vì một
        lỗi nói đúng thứ đang thiếu. Cùng loại lỗi với `get_transcript`.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM translations WHERE id=?",
                               (translation_id,)).fetchone()
        if row is None:
            raise NotFound(f"translation {translation_id} không tồn tại")
        return self._row_to_translation(row)

    def delete_translation(self, translation_id: int) -> None:
        """Xoá MỘT hàng `translations`; transcript và nguồn của nó GIỮ NGUYÊN.

        MỘT câu lệnh, nên không cần `_tx`: `DELETE` tự là một đơn vị nguyên tử, và
        `rowcount == 0` chính là phép kiểm id lạ — thay vì `SELECT` rồi `DELETE`
        (hai lần chạm hàng, và một cửa sổ để người khác xoá chen vào).

        Vì sao ném `NotFound` thay vì lặng lẽ trả về: route đã hứa **404** cho id
        không tồn tại, nên một lần xoá "thành công" trên hàng không có là câu trả
        lời nói dối (cùng quy ước với `update_translation_segments`).
        """
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM translations WHERE id=?", (translation_id,))
            if cur.rowcount == 0:
                raise NotFound(f"translation {translation_id} không tồn tại")

    def update_translation_segments(self, translation_id: int,
                                    segments: list[Segment]) -> None:
        """Checkpoint tiến độ: ghi ĐÈ `segments` bằng ĐÚNG danh sách được đưa.

        Adapter KHÔNG append: việc cộng dồn (`done + new`) là của người gọi, và
        người gọi phải truyền cả danh sách đã dịch tới lúc này (không phải lô vừa
        xong), nên `len(segments)` chính là tiến độ và không cần bảng
        `translation_segments` riêng (spec §3). Hệ quả: một danh sách NGẮN HƠN sẽ
        xoá việc đã ghi trước đó — đó là lý do người gọi phải tự cộng dồn. Không
        đụng `status`.

        Id không tồn tại ném `NotFound`: một `UPDATE` không khớp hàng nào vẫn
        "thành công", nên nuốt lỗi đó biến một id sai thành mất cả lô đã dịch,
        rồi lần ghi `status` sau cũng im lặng, và job báo `done` trên `segments`
        rỗng — đúng hợp đồng "`len(segments)` là tiến độ" bị phá mà không có tín
        hiệu nào. Đối xứng với `get_translation` và `update_transcript_segments`.
        """
        with self._connect() as conn:
            cur = conn.execute("UPDATE translations SET segments=? WHERE id=?",
                               (segments_to_json(segments), translation_id))
            if cur.rowcount == 0:
                raise NotFound(f"translation {translation_id} không tồn tại")

    def set_translation_status(self, translation_id: int, status: str, *,
                               qa_issues: list[str] | None = None,
                               tokens_in: int | None = None,
                               tokens_out: int | None = None,
                               duration_ms: int | None = None,
                               glossary_version: int | None = None) -> None:
        """Ghi trạng thái và (tuỳ chọn) số liệu QA/token/glossary.

        Tham số `None` nghĩa là "không đụng tới cột đó", không phải "ghi NULL":
        một job hỏng giữa đường vẫn phải giữ token đã tiêu của các lô đã xong.
        Cùng quy ước đó áp cho `glossary_version`: nó được ghi khi một lần DỊCH LẠI
        chạy xong (spec §8.1 — cột này là dấu vết duy nhất cho biết bản dịch đã
        dùng glossary nào), và một lần ghi `failed` không được xoá version đã có.

        Id không tồn tại ném `NotFound`, cùng lý do với
        `update_translation_segments`: nếu không, một checkpoint đã hụt vẫn được
        "đổi trạng thái" thành công trên hàng không tồn tại và job báo `done`.
        """
        sets, args = ["status=?"], [status]
        for column, value in (("qa_issues", qa_issues), ("tokens_in", tokens_in),
                              ("tokens_out", tokens_out), ("duration_ms", duration_ms),
                              ("glossary_version", glossary_version)):
            if value is not None:
                sets.append(f"{column}=?")
                args.append(json.dumps(value, ensure_ascii=False)
                            if column == "qa_issues" else value)
        args.append(translation_id)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE translations SET {', '.join(sets)} WHERE id=?", args)
            if cur.rowcount == 0:
                raise NotFound(f"translation {translation_id} không tồn tại")

    def set_translation_chimera(self, translation_id: int, data: dict | None) -> None:
        """Ghi ĐÈ cột `chimera`. `None` xoá dấu vết (đường chưa dùng tới).

        Ghi ĐÈ bằng ĐÚNG dict được đưa, cùng quy ước với
        `update_translation_segments`: người gọi giữ bản đã cộng dồn và truyền cả
        nó, nên hai lần ghi không thể trộn thành một bản nửa cũ nửa mới.

        Id không tồn tại ném `NotFound` — cùng lý do với mọi lệnh ghi khác ở đây.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE translations SET chimera=? WHERE id=?",
                (None if data is None else json.dumps(data, ensure_ascii=False),
                 translation_id))
            if cur.rowcount == 0:
                raise NotFound(f"translation {translation_id} không tồn tại")

    def list_translations_for_transcript(
            self, transcript_id: int) -> list[TranslationSummary]:
        """Tóm tắt bản dịch của MỘT transcript, mới nhất trước.

        Cố tình không `SELECT *`: cột `segments` là cả một bản dịch đã giải mã
        JSON, mà route chỉ cần biết bản dịch dịch từ version nào để tính `stale`.
        Danh sách này còn bị gọi cho TỪNG transcript ở route danh sách.

        V1 (lượt 3): kéo thêm `qa_issues` + `tokens_in`/`tokens_out`/`duration_ms`
        — BỐN CỘT, không phải `segments`. Cờ QA phải nhìn thấy được ngay ở danh
        sách (một cờ chỉ lộ ra khi mở từng bản dịch thì không phải một cờ), và đó
        là lý do chúng nằm trên `TranslationSummary` chứ không phải trên
        `Translation` mà thôi. Chi phí vẫn là bốn cột vô hướng; thứ bị bỏ lại
        vẫn đúng là `segments`.

        `qa_issues` NULL đọc lên thành `[]` chứ không `None`: cùng quy ước với
        `_row_to_translation`, và là hình dạng DUY NHẤT mà `qa_issues` có ở tầng
        này — client không phải phân biệt "vắng cờ" với "không có cờ".
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, transcript_id, transcript_version, engine, target_lang,"
                " prompt_version, status, created_at, qa_issues, tokens_in,"
                " tokens_out, duration_ms FROM translations"
                " WHERE transcript_id=? ORDER BY id DESC",
                (transcript_id,),
            ).fetchall()
        return [TranslationSummary(
            id=r["id"], transcript_id=r["transcript_id"],
            transcript_version=r["transcript_version"], engine=r["engine"],
            target_lang=r["target_lang"], prompt_version=r["prompt_version"],
            status=r["status"], created_at=r["created_at"],
            qa_issues=json.loads(r["qa_issues"] or "[]"),
            tokens_in=r["tokens_in"], tokens_out=r["tokens_out"],
            duration_ms=r["duration_ms"],
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

    def set_translations_status(self, translation_ids: list[int], status: str) -> int:
        """Ghi `status` cho nhiều hàng dịch, CHỈ những hàng chưa kết thúc.

        `IN (?,?,…)` dựng từ SỐ LƯỢNG id, không từ nội dung: giá trị vẫn là tham
        số `?` buộc, đúng quy ước của cả tệp này.

        Bộ lọc `status IN (?,?)` nằm trong CHÍNH câu UPDATE chứ không ở người gọi:
        nó là bất biến của phép đối chiếu (một hàng `done` là kết quả của một lần
        chạy thật, không được xoá bởi một lần quét muộn), và để nó ở người gọi là
        để mọi người gọi phải nhớ.
        """
        ids = [int(i) for i in translation_ids]
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE translations SET status=? WHERE id IN ({placeholders})"
                " AND status IN (?, ?)",
                (status, *ids, *UNSETTLED_TRANSLATION_STATUSES),
            )
            return int(cur.rowcount)

    def retry_job(self, job_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT state, attempts FROM jobs WHERE id=?",
                               (job_id,)).fetchone()
            if row is None:
                raise NotFound(f"job {job_id} không tồn tại")
            js.assert_transition(row["state"], js.QUEUED)
            # `cancel_requested=0` là một PHẦN của "chạy lại", không phải dọn
            # dẹp: `worker._run_one` HUỶ job ở ranh giới nếu cờ còn
            # (`worker.py:216`), nên bấm "chạy lại" trên một job từng bị xin huỷ
            # mà không xoá cờ thì job mới `queued` bị `cancelled` ngay lượt đầu:
            # người dùng thấy nút chạy lại vô tác dụng, còn log ghi "đã huỷ theo
            # yêu cầu" của một yêu cầu đã cũ.
            conn.execute(
                "UPDATE jobs SET state=?, attempts=attempts+1, finished_at=NULL,"
                " error=NULL, progress=0, cancel_requested=0 WHERE id=?",
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


def _chimera_from_row(row) -> dict | None:
    """Cột `chimera` của một hàng `translations` -> `dict`, hoặc `None`.

    Hàm cấp module chứ không phải phương thức: nó chỉ là một phép GIẢI MÃ, và nó
    được gọi từ `_row_to_translation`, nơi không có gì ngoài một hàng SQLite.

    `None` (không chạy Chimera) khác `{}` (chạy mà chưa có dữ liệu), nên cột NULL
    không bao giờ được đọc thành `{}`. Dùng `row.keys()` chứ không tin là cột luôn
    có: `_row_to_translation` cũng chạy trên một DB vừa được migration, và một
    `IndexError` ở đây sẽ đội lốt "hàng bản dịch hỏng".
    """
    if "chimera" not in row.keys():
        return None
    raw = row["chimera"]
    if raw is None:
        return None
    return json.loads(raw)
