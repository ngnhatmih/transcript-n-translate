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
