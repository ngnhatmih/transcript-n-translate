"""`llm_calls.job_id` phải có index, và một DB CŨ phải tự nhận nó (nợ N-2).

Hai lý do khiến chỗ này đáng một tệp riêng:

* Handler dịch gom mọi hàng `llm_calls` của một job để cộng token/thời gian —
  đúng MỘT truy vấn cho mỗi bản dịch, nhưng không index thì nó quét cả bảng,
  mà bảng đó lớn lên một hàng mỗi lần gọi engine, của MỌI job.
* Index là một ĐỐI TƯỢNG MỚI, không phải một cột: `CREATE INDEX IF NOT EXISTS`
  trong `SCHEMA_SQL` chạy được trên DB đã tồn tại, nên không cần migration và
  `SCHEMA_VERSION` phải giữ nguyên. Tệp này khoá cả hai vế đó lại.

DB cũ được dựng bằng `V1_SQL` của `test_schema_migration` — nguyên văn schema
TRƯỚC bản này — nên đây đúng là "DB tạo trước khi thêm index".
"""
import sqlite3

from app.adapters.clock_system import SystemClock
from app.adapters.persist.schema import SCHEMA_SQL, SCHEMA_VERSION
from app.adapters.persist.sqlite_repos import SqliteRepos
from tests.test_schema_migration import V1_SQL

INDEX = "idx_llm_calls_job"


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


def test_an_older_database_is_healed_without_a_migration(tmp_path):
    """DB dựng bằng schema CŨ (chưa có index) phải nhận index ở lần `init_schema`.

    Đồng thời ghim `SCHEMA_VERSION` không đổi: index là đối tượng mới nên
    `CREATE INDEX IF NOT EXISTS` tự chạy trên DB cũ, không cần bước migration
    nào và không được phép bump version.
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
    assert _version(db) == str(SCHEMA_VERSION) == "2", (
        "index KHÔNG phải lý do để đổi schema version"
    )
