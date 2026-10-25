"""Migration v1 -> v3 phải THẬT SỰ chạy trên DB cũ.

Bẫy: `init_schema()` cũ chạy `CREATE TABLE IF NOT EXISTS` (bỏ qua bảng đã có)
rồi ghi đè version. Nên DB v1 sẽ KHÔNG có cột `status` mà version vẫn là 2.
Test này dựng DB v1 nguyên văn rồi migrate, và kiểm cả dữ liệu cũ còn nguyên.

`SCHEMA_VERSION = 3` (nhánh CHIMERA) thêm cột `translations.chimera` — cột, nên nó
PHẢI có bước migration; bước đó chạy trên DB v1 theo cùng đường với `status`. Con
số version được ghim ở đây như một phép kiểm THỨ HAI, độc lập với hằng số trong
mã: sửa `SCHEMA_VERSION` mà quên migration thì bài này đỏ.
"""
import sqlite3

from app.adapters.clock_system import SystemClock
from app.adapters.persist.schema import SCHEMA_VERSION
from app.adapters.persist.sqlite_repos import SqliteRepos

V1_SQL = """
CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sources (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, origin TEXT NOT NULL,
  media_path TEXT NOT NULL, audio_path TEXT, duration REAL, lang TEXT, created_at TEXT NOT NULL);
CREATE TABLE transcripts (id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL, engine TEXT NOT NULL,
  lang TEXT NOT NULL, segments TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL);
CREATE TABLE translations (id INTEGER PRIMARY KEY, transcript_id INTEGER NOT NULL,
  transcript_version INTEGER NOT NULL, engine TEXT NOT NULL, target_lang TEXT NOT NULL DEFAULT 'vi',
  segments TEXT NOT NULL, prompt_version TEXT NOT NULL, glossary_version INTEGER, qa_issues TEXT,
  tokens_in INTEGER, tokens_out INTEGER, duration_ms INTEGER, created_at TEXT NOT NULL);
CREATE TABLE jobs (id INTEGER PRIMARY KEY, workspace INTEGER NOT NULL, type TEXT NOT NULL, engine TEXT,
  phase TEXT NOT NULL, state TEXT NOT NULL, cancel_requested INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0, progress REAL NOT NULL DEFAULT 0,
  log_tail TEXT NOT NULL DEFAULT '', log_path TEXT, error TEXT, payload TEXT,
  created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT);
CREATE TABLE llm_calls (id INTEGER PRIMARY KEY, job_id INTEGER, engine TEXT NOT NULL, model_ref TEXT,
  prompt_version TEXT, tokens_in INTEGER, tokens_out INTEGER, duration_ms INTEGER,
  ok INTEGER NOT NULL, error TEXT, created_at TEXT NOT NULL);
CREATE TABLE glossary (id INTEGER PRIMARY KEY, lang TEXT NOT NULL, term TEXT NOT NULL,
  translation TEXT NOT NULL, note TEXT, approved INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, UNIQUE(lang, term));
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _make_v1(db) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(V1_SQL)
    conn.execute("INSERT INTO schema_meta(key, value) VALUES('version', '1')")
    conn.execute("INSERT INTO sources(id, kind, origin, media_path, created_at)"
                 " VALUES(1, 'file', 'x', '/m/x.mp4', '2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO translations(id, transcript_id, transcript_version, engine,"
                 " segments, prompt_version, created_at)"
                 " VALUES(7, 1, 1, 'opus-mt', '[]', 'p1', '2026-01-01T00:00:00Z')")
    conn.commit()
    conn.close()


def test_migration_adds_status_without_losing_rows(tmp_path):
    db = tmp_path / "old.db"
    _make_v1(db)

    repos = SqliteRepos(db, clock=SystemClock())
    repos.init_schema()

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(translations)")}
    row = conn.execute("SELECT id, transcript_version, status FROM translations").fetchone()
    version = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
    src = conn.execute("SELECT origin FROM sources WHERE id=1").fetchone()
    conn.close()

    assert "status" in cols, "DB v1 migrate xong phải CÓ cột status"
    assert row == (7, 1, "queued"), "hàng cũ phải còn nguyên và nhận default 'queued'"
    assert src == ("x",), "dữ liệu bảng khác không được mất"
    assert version == str(SCHEMA_VERSION) == "3"


def test_migration_adds_the_chimera_trace_column(tmp_path):
    """Cột `translations.chimera` của nhánh CHIMERA phải tới được DB CŨ.

    Ba vế, và vế thứ ba mới là vế dễ sai: cột phải TỒN TẠI; hàng cũ phải mang
    `NULL` (KHÔNG phải `'{}'` — `{}` nghĩa là "có chạy Chimera mà không có dữ
    liệu", một lời khai khác hẳn); và cổng đọc phải trả `None` cho hàng đó.
    """
    db = tmp_path / "old.db"
    _make_v1(db)

    repos = SqliteRepos(db, clock=SystemClock())
    repos.init_schema()

    conn = sqlite3.connect(db)
    info = {r[1]: (r[3], r[4]) for r in conn.execute("PRAGMA table_info(translations)")}
    stored = conn.execute("SELECT chimera FROM translations WHERE id=7").fetchone()
    conn.close()

    assert "chimera" in info, "DB v1 migrate xong phải CÓ cột chimera"
    assert info["chimera"] == (0, None), (
        "cột chimera phải cho phép NULL (`notnull=0`) và KHÔNG có default: một "
        f"hàng cũ không được tự nhận một giá trị, nhận {info['chimera']!r}"
    )
    assert stored == (None,), "hàng cũ phải mang NULL, không phải chuỗi rỗng"
    assert repos.get_translation(7).chimera is None, (
        "cổng đọc phải biến NULL thành `None` — `{}` là một câu trả lời KHÁC"
    )


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "old.db"
    _make_v1(db)
    SqliteRepos(db, clock=SystemClock()).init_schema()
    repos = SqliteRepos(db, clock=SystemClock())
    repos.init_schema()          # chạy lần hai không được ném

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
    conn.close()
    assert n == 1, "migrate hai lần không được nhân bản dữ liệu"


def test_migration_heals_database_stamped_v2_without_status_column(tmp_path):
    """Đúng trạng thái `init_schema()` CŨ để lại: version đã là '2', cột thì chưa có.

    `CREATE TABLE IF NOT EXISTS` bỏ qua bảng đã tồn tại, còn version thì bị ghi
    đè, nên một DB Giai đoạn 1a có thể mang `schema_meta.version = '2'` mà vẫn
    thiếu `translations.status`. Nếu bước migration tin vào `version` (dùng nó
    làm cổng chặn) thì đúng cái DB này sẽ KHÔNG BAO GIỜ được vá — đó là bug mà
    Task 1 tồn tại để dập. Test này khoá hành vi tự vá đó lại.
    """
    db = tmp_path / "poisoned.db"
    _make_v1(db)

    conn = sqlite3.connect(db)
    conn.execute("UPDATE schema_meta SET value='2' WHERE key='version'")
    conn.commit()
    before = {r[1] for r in conn.execute("PRAGMA table_info(translations)")}
    conn.close()
    assert "status" not in before, "dựng cảnh nhiễm độc: version '2' nhưng còn thiếu cột"

    SqliteRepos(db, clock=SystemClock()).init_schema()

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(translations)")}
    row = conn.execute("SELECT id, transcript_version, status FROM translations").fetchone()
    version = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
    src = conn.execute("SELECT origin FROM sources WHERE id=1").fetchone()
    conn.close()

    assert "status" in cols, "version nói '2' mà thiếu cột: init_schema phải tự vá"
    assert row == (7, 1, "queued"), "hàng cũ phải sống sót và nhận default 'queued'"
    assert src == ("x",), "dữ liệu bảng khác không được mất"
    # ⚠️ ĐÍNH CHÍNH: bản trước ghim "version phải GIỮ NGUYÊN '2'". Câu đó chỉ đúng
    # khi version hiện hành LÀ 2. Từ nhánh CHIMERA, `SCHEMA_VERSION` là 3, nên
    # `init_schema()` đóng dấu 3 — và đó vẫn là hành vi đúng: version là con dấu
    # "schema hiện hành", KHÔNG phải cổng chặn migration (vế "không dùng version
    # làm cổng" ở docstring trên mới là bất biến, và nó vẫn được ghim: cột `status`
    # được vá trên một DB mang version '2').
    assert version == str(SCHEMA_VERSION) == "3", (
        "init_schema() đóng dấu version HIỆN HÀNH, và việc vá vẫn theo CỘT"
    )


def test_fresh_database_is_created_at_current_version(tmp_path):
    db = tmp_path / "new.db"
    repos = SqliteRepos(db, clock=SystemClock())
    repos.init_schema()
    conn = sqlite3.connect(db)
    info = {r[1]: (r[3], r[4]) for r in conn.execute("PRAGMA table_info(translations)")}
    version = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
    conn.close()
    assert "status" in info
    assert "chimera" in info, "DB mới phải có cột chimera ngay từ SCHEMA_SQL"
    assert version == str(SCHEMA_VERSION) == "3", "DB mới phải mang version hiện hành"
    assert info["status"] == (1, "'queued'"), (
        "cột status trên DB mới phải NOT NULL DEFAULT 'queued'"
    )
