"""`llm_calls.job_id` phải có index, và một DB CŨ phải tự nhận nó (nợ N-2).

Hai lý do khiến chỗ này đáng một tệp riêng:

* Handler dịch gom mọi hàng `llm_calls` của một job để cộng token/thời gian —
  đúng MỘT truy vấn cho mỗi bản dịch, nhưng không index thì nó quét cả bảng,
  mà bảng đó lớn lên một hàng mỗi lần gọi engine, của MỌI job.
* Index là một ĐỐI TƯỢNG MỚI, không phải một cột: `CREATE INDEX IF NOT EXISTS`
  trong `SCHEMA_SQL` chạy được trên DB đã tồn tại, nên nó KHÔNG cần một bước
  migration. Tệp này khoá vế đó lại — và nay khoá nó bằng ĐÚNG thứ nó nói
  (`_MIGRATIONS` không nhắc tới index), không bằng con số `SCHEMA_VERSION`:
  nhánh CHIMERA bump version lên 3 vì nó thêm một CỘT
  (`translations.chimera`), nên ghim con số ở đây sẽ nói sai lý do.

DB cũ được dựng bằng `V1_SQL` của `test_schema_migration` — nguyên văn schema
TRƯỚC bản này — nên đây đúng là "DB tạo trước khi thêm index".

Nhưng `V1_SQL` KHÔNG phải trạng thái thật của đĩa trước `b2ec7c6`: lúc đó
`SCHEMA_VERSION` đã là 2 (DB đã có `translations.status`, `sources.kind` CHECK,
`idx_jobs_state_phase`), chỉ thiếu mỗi index này. Vì vậy còn một ca thứ hai dựng
bằng `V2_SQL` — nguyên văn `SCHEMA_SQL` của `4a747e6` (commit cuối trước khi thêm
index), dán y nguyên chứ không suy diễn bằng `.replace()`.
"""
import sqlite3

from app.adapters.clock_system import SystemClock
from app.adapters.persist.schema import SCHEMA_SQL, SCHEMA_VERSION
from app.adapters.persist.sqlite_repos import SqliteRepos
from tests.test_schema_migration import V1_SQL

INDEX = "idx_llm_calls_job"

#: `SCHEMA_SQL` NGUYÊN VĂN của `backend/app/adapters/persist/schema.py` tại commit
#: `4a747e6` (`git show 4a747e6:backend/app/adapters/persist/schema.py`) — schema
#: v2 đúng như nó nằm trên đĩa TRƯỚC `b2ec7c6`, tức TRƯỚC index. Dán nguyên văn
#: là chủ ý: suy diễn bằng
#: `SCHEMA_SQL.replace("CREATE INDEX IF NOT EXISTS idx_llm_calls_job ON "
#: "llm_calls(job_id);", "")` sẽ thành no-op im lặng ngay khi ai đó đổi chữ trong
#: dòng DDL (thêm khoảng trắng, đổi tên index) — `V2_SQL` khi đó VẪN có index, DB
#: dựng ra đã sẵn thứ cần kiểm, và ca v2 xanh vô nghĩa.
V2_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('file','url')),
  origin TEXT NOT NULL,
  media_path TEXT NOT NULL,
  audio_path TEXT,
  duration REAL,
  lang TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  engine TEXT NOT NULL,
  lang TEXT NOT NULL,
  segments TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS translations (
  id INTEGER PRIMARY KEY,
  transcript_id INTEGER NOT NULL REFERENCES transcripts(id),
  transcript_version INTEGER NOT NULL,
  engine TEXT NOT NULL,
  target_lang TEXT NOT NULL DEFAULT 'vi',
  segments TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  glossary_version INTEGER,
  qa_issues TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  duration_ms INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  workspace INTEGER NOT NULL CHECK(workspace IN (1,2)),
  type TEXT NOT NULL,
  engine TEXT,
  phase TEXT NOT NULL,
  state TEXT NOT NULL,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  progress REAL NOT NULL DEFAULT 0,
  log_tail TEXT NOT NULL DEFAULT '',
  log_path TEXT,
  error TEXT,
  payload TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_state_phase ON jobs(state, phase, id);

CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY,
  job_id INTEGER,
  engine TEXT NOT NULL,
  model_ref TEXT,
  prompt_version TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  duration_ms INTEGER,
  ok INTEGER NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS glossary (
  id INTEGER PRIMARY KEY,
  lang TEXT NOT NULL,
  term TEXT NOT NULL,
  translation TEXT NOT NULL,
  note TEXT,
  approved INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(lang, term)
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


def _init(db) -> None:
    SqliteRepos(db, clock=SystemClock()).init_schema()


def _index_names(db) -> set[str]:
    conn = sqlite3.connect(db)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    return names


def _version(db) -> str:
    conn = sqlite3.connect(db)
    value = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
    conn.close()
    return value


def test_fresh_database_gets_the_index(tmp_path):
    """DB dựng mới phải có index, VÀ query planner phải dùng nó.

    Khẳng định thứ hai mạnh hơn `sqlite_master` có tên: một index sai cột vẫn
    xuất hiện ở đó mà truy vấn gom của handler dịch thì vẫn quét bảng. Truy vấn
    dưới đây đúng hình dạng phép gom đó (`WHERE job_id = ?`).
    """
    assert f"CREATE INDEX IF NOT EXISTS {INDEX} ON llm_calls(job_id)" in SCHEMA_SQL, (
        "SCHEMA_SQL phải khai index trên llm_calls(job_id) — DB mới lấy schema từ đó"
    )
    db = tmp_path / "new.db"
    _init(db)
    assert INDEX in _index_names(db), (
        "DB dựng mới phải có index trên llm_calls(job_id); không có nghĩa là "
        "`init_schema()` chưa từng chạy câu lệnh đó"
    )
    conn = sqlite3.connect(db)
    plan = " ".join(
        str(row[3]) for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT COUNT(*), SUM(tokens_in), SUM(tokens_out),"
            " SUM(duration_ms) FROM llm_calls WHERE job_id = 1")
    )
    conn.close()
    assert INDEX in plan, f"query planner không dùng index: {plan!r}"


def test_the_index_is_not_a_migration_step():
    """Index là ĐỐI TƯỢNG, `_MIGRATIONS` là các bước THÊM CỘT.

    Đây là cách ghim vế "index không cần migration" mà không phụ thuộc con số
    `SCHEMA_VERSION` (nhánh CHIMERA bump nó vì một CỘT khác). Một index lọt vào
    `_MIGRATIONS` là dấu hiệu ai đó tin sai về `CREATE INDEX IF NOT EXISTS`, và nó
    sẽ hỏng ở lần chạy thứ hai trên DB đã có index.
    """
    flat = " ".join(" ".join(str(part) for part in step)
                    for step in SqliteRepos._MIGRATIONS)
    assert INDEX not in flat, (
        f"`{INDEX}` phải do `SCHEMA_SQL` tạo, không phải một bước migration: {flat!r}"
    )


def test_an_older_database_is_healed_without_a_migration(tmp_path):
    """DB dựng bằng schema CŨ (chưa có index) phải nhận index ở lần `init_schema`.

    Và nó nhận được mà KHÔNG cần bước migration nào cho index: cùng lần
    `init_schema()` đó có chạy các bước thêm cột của phiên bản hiện hành, nhưng
    index đến từ `CREATE INDEX IF NOT EXISTS` trong `SCHEMA_SQL` — câu lệnh tự
    chạy được trên một bảng đã tồn tại.
    """
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(V1_SQL)
    conn.execute("INSERT INTO schema_meta(key, value) VALUES('version', '1')")
    conn.commit()
    conn.close()
    assert INDEX not in _index_names(db), "dựng cảnh: DB cũ phải CHƯA có index"

    _init(db)

    assert INDEX in _index_names(db), (
        "init_schema() trên DB cũ phải tạo index — nếu không thì mọi DB đã tồn "
        "tại vẫn quét cả bảng và cần một migration thật"
    )
    assert _version(db) == str(SCHEMA_VERSION) == "3", (
        "init_schema() đóng dấu version HIỆN HÀNH; ở nhánh này nó là 3 vì cột "
        "`translations.chimera`, KHÔNG vì index — xem "
        "`test_the_index_is_not_a_migration_step`"
    )


def test_a_v2_database_without_the_index_is_healed(tmp_path):
    """DB v2 THẬT (đúng thứ trên đĩa trước `b2ec7c6`) phải nhận index.

    Ca `v1` ở trên KHÔNG phủ được trạng thái này. Một hồi quy kiểu "tối ưu khởi
    động" — gate `conn.executescript(SCHEMA_SQL)` sau `if version < SCHEMA_VERSION`
    — giữ ca v1 **XANH** (`1 < 2` nên vẫn chạy) trong khi MỌI DB v2 thật vĩnh
    viễn không nhận index (`2 < 2` là sai), tức không cần migration nào chạy nữa.
    Chỉ một ca dựng đúng v2 mới ghim được vế đó.
    """
    assert INDEX not in V2_SQL, (
        "V2_SQL phải là schema TRƯỚC index; nếu dòng DDL trong đó đổi chữ mà V2_SQL "
        "được suy diễn bằng .replace() thì phép cắt là no-op, DB 'v2' đã có sẵn đúng "
        "thứ cần kiểm và ca này sẽ XANH vô nghĩa"
    )
    db = tmp_path / "v2.db"
    conn = sqlite3.connect(db)
    conn.executescript(V2_SQL)
    conn.execute("INSERT INTO schema_meta(key, value) VALUES('version', '2')")
    conn.commit()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(translations)")}
    conn.close()
    assert "status" in cols, "dựng cảnh: V2_SQL phải là v2 THẬT (đã có status)"
    assert INDEX not in _index_names(db), "dựng cảnh: DB v2 phải CHƯA có index"

    _init(db)

    assert INDEX in _index_names(db), (
        "DB v2 — đúng trạng thái trên đĩa trước b2ec7c6, version '2' và ĐÃ có cột "
        "status nên không migration nào chạy — vẫn phải nhận index từ chính "
        "`executescript(SCHEMA_SQL)`; gate nó sau `version < SCHEMA_VERSION` là bỏ "
        "rơi mọi DB đang tồn tại"
    )
    assert _version(db) == str(SCHEMA_VERSION), (
        "init_schema() đóng dấu version HIỆN HÀNH lên DB vừa được heal. KHÔNG ghim "
        "một chữ số cụ thể ở đây: `SCHEMA_VERSION` đã là 3 từ commit Chimera "
        "(cột `translations.chimera`), tức nó đổi vì một LÝ DO KHÁC — ghim "
        "\"2\" là ghim một sự kiện lịch sử, không phải một bất biến. Bất biến "
        "thật của mục này là index KHÔNG phải một bước migration: nó là "
        "`CREATE INDEX IF NOT EXISTS` trong `SCHEMA_SQL`, chạy trên DB đã tồn tại."
    )
