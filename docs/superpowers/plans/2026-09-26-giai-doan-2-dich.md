# Giai đoạn 2 — Workspace 2 (dịch) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend Workspace 2 chạy được đầu-cuối — văn bản đã bóc băng → bản dịch tiếng Việt qua OPUS-MT và Qwen2.5-3B, có glossary, QA tất định, và xuất phụ đề theo hình dạng spec.

**Architecture:** Giữ nguyên khuôn hexagonal-lite của Giai đoạn 1a (`domain/` thuần → `ports/` chỉ Protocol → `adapters/` → `pipeline/` → `api/`). Một bản dịch là **một job** `translate:<engine>`; bên trong handler chia lô, kiểm alignment, ghi kết quả **append theo thứ tự** nên `len(segments)` chính là tiến độ — không cần bảng mới.

**Tech Stack:** Python 3.10.5 · FastAPI · SQLite · `transformers` + Marian (OPUS-MT, in-process, CPU) · Ollama HTTP (Qwen2.5-3B) · pytest

**Spec:** `docs/superpowers/specs/2026-09-26-giai-doan-2-dich-design.md`

## ⚠️ HIỆU CHỈNH SAU TỰ SOÁT — ĐỌC TRƯỚC KHI LÀM BẤT CỨ TASK NÀO

Tự soát (bước bắt buộc của writing-plans) đã đối chiếu **mọi** tên hàm/kiểu trong plan với mã THẬT ở `32bf3df`, và
tìm ra những tên tôi đã viết **sai**. Mục này là **nguồn có thẩm quyền**: chỗ nào thân task mâu thuẫn với mục này
thì **mục này đúng**. (Việc gấp các hiệu chỉnh này vào thân từng task là bước kế tiếp, làm trước khi dispatch.)

1. `build_components()` trả **tuple 4 phần tử** `(repos, specs, worker, broker)` — `main.py:112`. **Không** phải
   dataclass, **không** có `mt_engines` hay `handlers` trong giá trị trả về.
2. `build_app(repos, specs, worker, broker) -> FastAPI` — `main.py:115`, **tham số vị trí**. Không nhận object components.
3. `create_app(*, repos, specs, media_dir, out_dir, worker=, log_dir=, broker=)` — `api/app.py:22`. Tham số là
   **`specs: list[EngineSpec]`**, không phải `registry`.
4. Dependency thật là `get_specs` (`api/deps.py:17`) trả **`list[EngineSpec]`**. **Không có** `get_registry`.
5. Tra engine theo id: `app.registry.by_id(specs, engine_id)` (`registry.py:54`). **Không có** `registry.get(...)`.
6. `EngineSpec` (`registry.py:19-37`) có **đúng** các trường: `id, label, kind ('asr'|'mt'), runtime
   ('inprocess'|'ollama'), model_ref, vram_mb, langs, capabilities: dict, opts: dict` + property `phase_key`.
   **Không có** `workspace`, `available`, `prompt_version`. Hệ quả:
   - "engine dịch" nhận biết bằng **`spec.kind == "mt"`**, không phải `workspace == 2`.
   - Sẵn sàng hay không: đặt vào **`spec.capabilities["available"]`** (dict này ghi được tại chỗ dù dataclass `frozen`).
   - Phiên bản prompt: **`PROMPT_VERSION[spec.id]`** từ `adapters/mt/prompts.py`, không phải thuộc tính spec.
   - Khoá giai đoạn: dùng luôn **`spec.phase_key`** (đã dựng qua `phase_of`), đừng tự nối chuỗi.
7. `PhaseQueueWorker` nhận `handlers` là **dict khoá theo `handles()`** — xem `main.py:83-93`.
8. `JobHandler.run(self, job, report: Callable[[float, str], None])` — `worker.py:24`. `report` nhận **HAI** tham số
   `(progress, message)`. Mọi chỗ trong thân task gọi `report("...")` **một** tham số là **sai**.
9. `SqliteRepos.add_translation` **đã tồn tại** (`sqlite_repos.py:203`), chữ ký:
   `(*, transcript_id, transcript_version, engine, target_lang, segments, prompt_version, glossary_version=None,
   qa_issues=None, tokens_in=None, tokens_out=None, duration_ms=None)`.
   ⇒ Task 6 chỉ **THÊM** `status: str = "queued"`, **không viết lại**.
10. `SqliteRepos._row_to_translation` **đã tồn tại** (`sqlite_repos.py:180`) ⇒ Task 6 chỉ thêm `status=row["status"]`.
11. `pipeline/export.py` công bố **`FORMATS`, `MEDIA_TYPES`, `artifact_name(stem, fmt, translated: bool)`** — dùng ở
    `routes_export.py:30,105`. **Không có** `render()`, và `artifact_name` **không** nhận `translation`/`bilingual`.
    ⇒ Task 15 phải **đọc `routes_export.py:84-110`** (route download đang chạy) rồi làm route mới theo **đúng** cách
    nó gọi `artifact_name`, thay vì tự nghĩ ra `render`.
12. `TranscribeHandler` **đã có** đường tự chuyển sang dịch: `_forward_to_translation` (`pipeline/transcribe.py:106`)
    và `_default_mt_engine` (`:114`). Và `main.py:109-110` đang **ép `auto_forward = "0"`**. ⇒ Task 12 phải:
    (a) đổi mặc định sang **"1"** khi đã có handler `translate`; (b) sửa `_forward_to_translation` để nó tạo **dòng
    `translations`** trước rồi mới tạo job với payload mới (`translation_id`, `transcript_id`, `engine_id`, ...) —
    nếu không, job dịch do auto-forward sinh ra sẽ hỏng payload và `TranslateHandler.run` ném `KeyError`.
13. `NotFound(LookupError)` tồn tại ở `sqlite_repos.py:21`. Trước khi viết `except KeyError`, **đọc** xem
    `get_transcript`/`get_translation` thực ném gì, sửa `except` cho khớp **thực tế**, và `pytest.raises` cũng phải
    đúng loại đó.
14. `capabilities` và `opts` là dict **dùng chung** cho mọi nơi giữ danh sách spec đã nạp (cảnh báo ở
    `registry.py:21-27`): ghi vào `spec.capabilities["available"]` là sửa **tại chỗ** — chấp nhận được vì
    `build_components()` nạp registry **một lần**, nhưng **không** được ghi vào đó trong route (mỗi request một lần).
15. 🔴 **`registry.json` ĐÃ KHAI ĐỦ CẢ BỐN ENGINE MT TỪ GIAI ĐOẠN 1a.** Cấu trúc thật là các mảng theo `kind`:
    `{_ghi_chu, default_asr, default_mt, asr: [...], mt: [...]}` — **không có** khoá `engines`. Mảng `mt` đã có
    `opus-mt`, `qwen2.5-3b`, `qwen2.5-7b`, **`hy-mt-1.5-7b`** (chú ý: id là `hy-mt-1.5-7b`, **không** phải
    `hy-mt1.5`), mỗi entry có `capabilities` gồm `glossary_prompt`, `glossary_patch`, `chimera`, `batch_json`.
    ⇒ **Task 12 Step 3 (thêm ba entry engine) PHẢI BỎ** — làm theo là **nhân bản entry** và `by_id()` sẽ trả
    bản đầu tiên. `default_mt` cũng **đã** là `"opus-mt"`.
16. `load_registry` nằm ở **`app/adapters/registry_file.py:12`**, không phải `app/registry.py`. Nó đọc mảng theo
    `_KINDS` và dựng `EngineSpec` với `kind=<tên mảng>`.
17. "Engine có hỗ trợ glossary không" đã có sẵn dữ liệu: **`spec.capabilities["glossary_prompt"]`**. Dùng nó làm
    nguồn sự thật cho `supports_glossary()` của engine Ollama, đừng hardcode `True` trong adapter.
18. Vì `registry.json` không có trường `available`, Task 12 **thêm** nó bằng cách ghi vào
    `spec.capabilities["available"]` lúc `build_components()` chạy: `runtime == "ollama"` ⇒ dò `ollama_available()`;
    `runtime == "inprocess"` ⇒ `True`. Đây là **dữ liệu dẫn xuất**, không phải sửa file JSON.

⚠️ **Trạng thái gấp hiệu chỉnh:** Task 1–5 **không** bị ảnh hưởng bởi mục nào ở trên (chúng chỉ tạo module `domain/`
thuần và migration), nên **chạy được ngay**. Các mục 1–18 phải được gấp vào thân Task **6, 11, 12, 13, 14, 15, 17**
trước khi dispatch các task đó.

## Global Constraints

- Python **3.10.5**, venv ở **`backend/.venv`**. Mọi lệnh pytest chạy từ **`backend/`**.
- `backend/pytest.ini` đã có `addopts = -q`. **KHÔNG** thêm `-q` lần nữa (`-qq` nuốt dòng "N passed").
- Trước khi tin một kết quả đỏ: xoá `__pycache__` rồi chạy `python -B -m pytest`. Bytecode cũ làm **cây đúng trông như hỏng**.
- **Không** `--amend`, **không** rebase. Sửa thì thêm commit mới.
- Scratch để **ngoài repo** (`$env:TEMP`). `git status --porcelain` phải sạch sau mỗi task.
- Suite **không** được tạo thư mục `data/` thật trong repo (bẫy `ensure_dirs()` đóng trên global của `app.config`).
- `app/domain/` chỉ import **stdlib** (allowlist + namespace `app.domain`). `app/ports/` chỉ chứa `Protocol`.
- **Không** file nào dưới `app/api/` được dùng `sqlite3`, `db_path`, `_connect(` — đi qua port.
- Mọi đường dẫn từ dữ liệu ngoài phải qua `app/domain/paths.py` (`safe_basename`, `resolve_within`).
- Khoá giai đoạn: `phase_of(job_type, engine) == f"{job_type}:{engine or '-'}"`. Job dịch lưu **`translate:<engine>`**.
- `releaser` đăng ký với governor **bắt buộc idempotent** (gọi lúc không có model đang nạp là no-op).
- Port nào cũng **không** `runtime_checkable`; không chỗ nào `isinstance`-kiểm port ⇒ thêm phương thức là an toàn.
- Mọi tuyên bố "xong" phải kèm **lệnh chính xác + dòng cuối nguyên văn**. Mọi test mới phải được chứng minh **không rỗng** bằng mutation: sửa mã → thấy đỏ → phục hồi → verify `git hash-object` == `git rev-parse HEAD:<path>`.
- Baseline trước khi bắt đầu: **517 passed** tại `32bf3df`.
- Cổng backend: **8620**. Ollama mặc định: **`http://127.0.0.1:11434`**. Model cache: `HF_HOME` (mặc định `D:\models\hf`).

## File Structure

**Tạo mới**

| Tệp | Trách nhiệm |
|---|---|
| `backend/app/domain/mt.py` | chia lô segment theo ngân sách ký tự |
| `backend/app/domain/alignment.py` | kiểm N vào/N ra + khớp id |
| `backend/app/domain/glossary_match.py` | thuật ngữ xuất hiện trong segment; segment bị ảnh hưởng khi glossary đổi |
| `backend/app/domain/mt_qa.py` | QA tất định sau dịch |
| `backend/app/adapters/mt/__init__.py` | gói |
| `backend/app/adapters/mt/prompts.py` | dựng prompt theo engine + `PROMPT_VERSION` |
| `backend/app/adapters/mt/opus_mt.py` | `OpusMtEngine` (Marian, CPU, không glossary) |
| `backend/app/adapters/mt/ollama_mt.py` | `OllamaMtEngine` (HTTP, `keep_alive`, token count, releaser) |
| `backend/app/pipeline/translate.py` | `TranslateHandler` |
| `backend/app/api/routes_translations.py` | `/api/translations` · `/api/transcripts/{id}/approve` · route export hình dạng spec |
| `backend/app/api/routes_glossary.py` | `/api/glossary` |
| `backend/scripts/download_mt_models.py` | tải trước model OPUS-MT |
| `backend/scripts/smoke_mt.py` | chạy thật, **in số** (segment, thời gian, token) |
| `backend/tests/test_mt_batching.py` · `test_mt_alignment.py` · `test_glossary_match.py` · `test_mt_qa.py` · `test_mt_prompts.py` · `test_mt_opus.py` · `test_mt_ollama.py` · `test_translate_handler.py` · `test_api_translations.py` · `test_api_glossary.py` · `test_schema_migration.py` · `test_mt_live.py` (marker) | test |

**Sửa**

| Tệp | Sửa gì |
|---|---|
| `backend/app/adapters/persist/schema.py` | `SCHEMA_VERSION = 2`; thêm `translations.status` |
| `backend/app/adapters/persist/sqlite_repos.py` | migration có thứ tự; `add_translation` lên port; `get_translation`, `update_translation_segments`, `set_translation_status`, `bump_glossary_version` |
| `backend/app/domain/models.py` | `Translation.status: str = "queued"` |
| `backend/app/ports/repos.py` | các phương thức translation ở trên |
| `backend/app/ports/mt.py` | **mới**: `MtEngine` Protocol (đặt trong `ports/`, không phải `adapters/`) |
| `backend/app/registry.py` | spec `opus-mt`, `qwen2.5-3b`; dò `available` cho Ollama |
| `backend/app/main.py` | dựng MT engine + `TranslateHandler`, đăng ký releaser, truyền vào API |
| `backend/app/api/app.py` | gắn router mới |
| `backend/requirements.txt` · `backend/scripts/install.ps1` | `transformers`, `sentencepiece`, `sacremoses` |
| `README.md` | cách chạy Giai đoạn 2 |

---

### Task 1: Migration schema v1 → v2 (`translations.status`)

**Vì sao task này đứng đầu:** `init_schema()` hiện chỉ chạy `CREATE TABLE IF NOT EXISTS` rồi **ghi đè** `schema_meta.version`. Thêm cột vào bảng đã tồn tại sẽ **âm thầm không xảy ra** trên DB Giai đoạn 1a đang có, mà version vẫn thành số mới ⇒ DB cũ chết với `no such column`. Mọi task sau đều ghi vào `translations.status`, nên phải có cột thật trước.

**Files:**
- Create: `backend/tests/test_schema_migration.py`
- Modify: `backend/app/adapters/persist/schema.py`
- Modify: `backend/app/adapters/persist/sqlite_repos.py:78-86`
- Modify: `backend/app/domain/models.py:135-149`

**Interfaces:**
- Consumes: không
- Produces: `SCHEMA_VERSION == 2` · `translations.status TEXT NOT NULL DEFAULT 'queued'` · `Translation.status: str = "queued"` · `SqliteRepos.init_schema()` migrate được DB v1

- [ ] **Step 1: Viết test đỏ — DB v1 rồi migrate**

```python
# backend/tests/test_schema_migration.py
"""Migration v1 -> v2 phải THẬT SỰ chạy trên DB cũ.

Bẫy: `init_schema()` cũ chạy `CREATE TABLE IF NOT EXISTS` (bỏ qua bảng đã có)
rồi ghi đè version. Nên DB v1 sẽ KHÔNG có cột `status` mà version vẫn là 2.
Test này dựng DB v1 nguyên văn rồi migrate, và kiểm cả dữ liệu cũ còn nguyên.
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
    assert version == str(SCHEMA_VERSION) == "2"


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


def test_fresh_database_is_created_at_current_version(tmp_path):
    db = tmp_path / "new.db"
    repos = SqliteRepos(db, clock=SystemClock())
    repos.init_schema()
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(translations)")}
    conn.close()
    assert "status" in cols
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_schema_migration.py
```
Kỳ vọng: `test_migration_adds_status_without_losing_rows` FAIL với `AssertionError: DB v1 migrate xong phải CÓ cột status`.

- [ ] **Step 3: Thêm cột vào schema hiện hành**

Trong `backend/app/adapters/persist/schema.py`: đổi `SCHEMA_VERSION = 1` thành `SCHEMA_VERSION = 2`, và trong `CREATE TABLE IF NOT EXISTS translations` thêm dòng ngay sau `prompt_version TEXT NOT NULL,`:

```sql
  status TEXT NOT NULL DEFAULT 'queued',
```

- [ ] **Step 4: Thêm bước migration có thứ tự vào `init_schema`**

Thay toàn bộ `init_schema` trong `backend/app/adapters/persist/sqlite_repos.py` (dòng 78-86):

```python
    #: Các bước migration, theo thứ tự tăng dần của `version`.
    #: Mỗi bước PHẢI idempotent: chạy lại trên DB đã migrate là no-op, không ném.
    _MIGRATIONS: tuple[tuple[int, str], ...] = (
        (2, "ALTER TABLE translations ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'"),
    )

    def _current_version(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
        return int(row[0]) if row is not None else 0

    def _column_names(self, conn: sqlite3.Connection, table: str) -> set[str]:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        """Áp các bước migration còn thiếu.

        `CREATE TABLE IF NOT EXISTS` KHÔNG thêm cột vào bảng đã tồn tại, nên một
        DB Giai đoạn 1a sẽ thiếu `translations.status` mà `schema_meta.version`
        vẫn bị ghi thành số mới — hỏng âm thầm. Vì vậy phải kiểm cột thật, không
        tin version.
        """
        version = self._current_version(conn)
        for target, ddl in self._MIGRATIONS:
            if version >= target:
                continue
            table = ddl.split()[2]
            column = ddl.split()[5]
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
```

- [ ] **Step 5: Thêm `status` vào dataclass `Translation`**

Trong `backend/app/domain/models.py`, trong `class Translation`, thêm ngay sau `target_lang: str = "vi"`:

```python
    status: str = "queued"           # queued | running | done | failed | cancelled
```

- [ ] **Step 6: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_schema_migration.py
```
Kỳ vọng: `3 passed`.

- [ ] **Step 7: Chạy cả suite — không được làm đỏ chỗ nào**

```bash
cd backend
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python -B -m pytest
```
Kỳ vọng: dòng cuối `520 passed`.

- [ ] **Step 8: Chứng minh test không rỗng (mutation)**

Bỏ dòng `status TEXT NOT NULL DEFAULT 'queued',` khỏi `SCHEMA_SQL` → chạy `tests/test_schema_migration.py` → phải thấy `1 failed` (`test_fresh_database_is_created_at_current_version`). Phục hồi, rồi verify:

```bash
git hash-object backend/app/adapters/persist/schema.py
git rev-parse HEAD:backend/app/adapters/persist/schema.py
```

- [ ] **Step 9: Commit**

```bash
git add backend/tests/test_schema_migration.py backend/app/adapters/persist/schema.py backend/app/adapters/persist/sqlite_repos.py backend/app/domain/models.py
git commit -m "feat(db): migration schema v2 - them translations.status"
```

---

### Task 2: `domain/mt.py` — chia lô theo ngân sách ký tự

**Files:**
- Create: `backend/tests/test_mt_batching.py`
- Create: `backend/app/domain/mt.py`

**Interfaces:**
- Consumes: `app.domain.models.Segment`
- Produces: `batch_segments(segments: list[Segment], *, max_chars: int) -> list[list[Segment]]` · `DEFAULT_MAX_CHARS: int`

An toàn khi thiếu `max_chars` hợp lệ: `max_chars <= 0` ⇒ `ValueError` (im lặng nhận giá trị vô nghĩa là bịa ra hành vi).

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_mt_batching.py
"""Chia lô theo ký tự. Hàm thuần nên test được không cần model.

Bất biến quan trọng nhất: GHÉP các lô theo thứ tự phải bằng ĐÚNG đầu vào — không
mất segment, không nhân bản, không đổi thứ tự. Một lô rỗng hoặc một segment bị
bỏ sẽ làm bản dịch lệch phụ đề mà không ai thấy.
"""
import pytest

from app.domain.models import Segment
from app.domain.mt import DEFAULT_MAX_CHARS, batch_segments


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1.0, text=text)


def test_empty_input_gives_no_batches():
    assert batch_segments([], max_chars=10) == []


def test_single_segment_is_its_own_batch():
    s = seg(1, "xin chào")
    assert batch_segments([s], max_chars=100) == [[s]]


def test_segments_pack_until_the_budget_would_be_exceeded():
    a, b, c = seg(1, "a" * 5), seg(2, "b" * 5), seg(3, "c" * 5)
    assert batch_segments([a, b, c], max_chars=10) == [[a, b], [c]]


def test_a_segment_longer_than_the_budget_is_not_dropped():
    big = seg(1, "x" * 50)
    small = seg(2, "y")
    assert batch_segments([big, small], max_chars=10) == [[big], [small]]


def test_no_segment_is_lost_or_duplicated_or_reordered():
    segs = [seg(i, "t" * (i % 7 + 1)) for i in range(1, 40)]
    out = batch_segments(segs, max_chars=13)
    assert [s.i for batch in out for s in batch] == [s.i for s in segs]
    assert all(batch for batch in out), "không được có lô rỗng"


def test_non_positive_budget_is_rejected():
    with pytest.raises(ValueError):
        batch_segments([seg(1, "a")], max_chars=0)


def test_default_budget_is_a_positive_int():
    assert isinstance(DEFAULT_MAX_CHARS, int) and DEFAULT_MAX_CHARS > 0
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_mt_batching.py
```
Kỳ vọng: `ModuleNotFoundError: No module named 'app.domain.mt'`.

- [ ] **Step 3: Viết hiện thực tối thiểu**

```python
# backend/app/domain/mt.py
"""Chia segment thành lô cho một lần gọi engine dịch.

Ngân sách tính bằng KÝ TỰ của văn bản nguồn — đơn vị duy nhất mà mọi engine đều
có, kể cả OPUS-MT vốn không trả token count. Giá trị cụ thể đo rồi chốt ở spec §12.
"""
from __future__ import annotations

from .models import Segment

#: Ngân sách mặc định. Số này là ĐIỂM KHỞI ĐẦU, không phải số đã tối ưu: spec §12
#: để ngỏ và Task 16 đo tỉ lệ lệch alignment theo kích thước lô rồi chốt lại.
DEFAULT_MAX_CHARS = 1200


def batch_segments(segments: list[Segment], *, max_chars: int) -> list[list[Segment]]:
    """Chia `segments` thành các lô liên tiếp, mỗi lô không quá `max_chars` ký tự.

    Một segment dài hơn ngân sách vẫn tạo một lô riêng chứa nó: bỏ nó đi là mất
    hẳn một dòng phụ đề.
    """
    if max_chars <= 0:
        raise ValueError(f"max_chars phải > 0, nhận {max_chars!r}")

    batches: list[list[Segment]] = []
    current: list[Segment] = []
    used = 0
    for s in segments:
        size = len(s.text)
        if current and used + size > max_chars:
            batches.append(current)
            current, used = [], 0
        current.append(s)
        used += size
    if current:
        batches.append(current)
    return batches
```

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_mt_batching.py
```
Kỳ vọng: `7 passed`.

- [ ] **Step 5: Mutation — chứng minh test không rỗng**

Đổi `if current and used + size > max_chars:` thành `if used + size > max_chars:` → `test_a_segment_longer_than_the_budget_is_not_dropped` và `test_no_segment_is_lost_or_duplicated_or_reordered` phải đỏ (sinh lô rỗng). Phục hồi và verify bằng `git hash-object` / `git rev-parse HEAD:<path>`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/mt.py backend/tests/test_mt_batching.py
git commit -m "feat(domain): chia lo segment theo ngan sach ky tu"
```

---

### Task 3: `domain/alignment.py` — kiểm N vào / N ra

**Files:**
- Create: `backend/tests/test_mt_alignment.py`
- Create: `backend/app/domain/alignment.py`

**Interfaces:**
- Consumes: `app.domain.models.Segment`
- Produces: `class AlignmentProblem(Exception)` với `.expected_ids: list[int]`, `.got_ids: list[int]`, `.reason: str` · `check_alignment(src: list[Segment], out: list[Segment]) -> None`

Đây là **bất biến then chốt** của cả phase: `translations.segments` chỉ chứa bản dịch khớp **đúng `i`** theo **đúng thứ tự**. Ghép lệch thứ tự làm phụ đề sai chỗ mà không có triệu chứng nào khác.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_mt_alignment.py
"""Kiểm alignment: engine phải trả ĐÚNG số segment, ĐÚNG id, ĐÚNG thứ tự.

Mọi engine LLM đều có lúc trả thiếu/thừa mục khi lô lớn. Nếu chỗ này không ném
lỗi thì bản dịch bị ghép lệch và phụ đề sai chỗ — hỏng âm thầm, không triệu chứng.
"""
import pytest

from app.domain.alignment import AlignmentProblem, check_alignment
from app.domain.models import Segment


def seg(i: int, text: str = "t") -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text)


def test_matching_ids_in_order_passes():
    check_alignment([seg(1), seg(2)], [seg(1, "vi1"), seg(2, "vi2")])


def test_missing_segment_raises_and_names_the_id():
    with pytest.raises(AlignmentProblem) as exc:
        check_alignment([seg(1), seg(2)], [seg(1, "vi1")])
    assert exc.value.expected_ids == [1, 2]
    assert exc.value.got_ids == [1]
    assert "2" in exc.value.reason


def test_extra_segment_raises():
    with pytest.raises(AlignmentProblem):
        check_alignment([seg(1)], [seg(1), seg(2)])


def test_wrong_order_raises():
    with pytest.raises(AlignmentProblem):
        check_alignment([seg(1), seg(2)], [seg(2), seg(1)])


def test_duplicate_id_raises():
    with pytest.raises(AlignmentProblem):
        check_alignment([seg(1), seg(2)], [seg(1), seg(1)])


def test_unknown_id_raises():
    with pytest.raises(AlignmentProblem):
        check_alignment([seg(1)], [seg(99)])


def test_empty_on_both_sides_passes():
    check_alignment([], [])
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_mt_alignment.py
```
Kỳ vọng: `ModuleNotFoundError: No module named 'app.domain.alignment'`.

- [ ] **Step 3: Viết hiện thực tối thiểu**

```python
# backend/app/domain/alignment.py
"""Bất biến alignment của một lô dịch.

Engine nhận `list[Segment]` và PHẢI trả về đúng bấy nhiêu `Segment`, cùng `i`,
cùng thứ tự. Adapter nào không bảo đảm được thì ném `AlignmentProblem` ở đây,
chứ KHÔNG trả về một list ngắn hơn: list ngắn là đúng kiểu thất bại âm thầm làm
lệch phụ đề.
"""
from __future__ import annotations

from .models import Segment


class AlignmentProblem(Exception):
    """Số lượng / id / thứ tự của kết quả engine không khớp đầu vào."""

    def __init__(self, expected_ids: list[int], got_ids: list[int], reason: str) -> None:
        super().__init__(reason)
        self.expected_ids = expected_ids
        self.got_ids = got_ids
        self.reason = reason


def check_alignment(src: list[Segment], out: list[Segment]) -> None:
    """Ném `AlignmentProblem` trừ khi `[s.i for s in out] == [s.i for s in src]`."""
    expected = [s.i for s in src]
    got = [s.i for s in out]

    if len(got) != len(expected):
        missing = [i for i in expected if i not in got]
        extra = [i for i in got if i not in expected]
        detail = []
        if missing:
            detail.append(f"thiếu id {missing}")
        if extra:
            detail.append(f"thừa id {extra}")
        raise AlignmentProblem(
            expected, got,
            f"engine trả {len(got)} mục, cần {len(expected)}" + (f" ({'; '.join(detail)})" if detail else ""),
        )
    if got != expected:
        raise AlignmentProblem(expected, got, f"thứ tự/id sai: nhận {got}, cần {expected}")
```

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_mt_alignment.py
```
Kỳ vọng: `7 passed`.

- [ ] **Step 5: Mutation — chứng minh test không rỗng**

Đổi `if got != expected:` thành `if False:` → `test_wrong_order_raises`, `test_duplicate_id_raises`, `test_unknown_id_raises` phải đỏ. Phục hồi và verify hash.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/alignment.py backend/tests/test_mt_alignment.py
git commit -m "feat(domain): bat bien alignment cho mot lo dich"
```

---

### Task 4: `domain/glossary_match.py` — thuật ngữ trong segment và segment bị ảnh hưởng

**Files:**
- Create: `backend/tests/test_glossary_match.py`
- Create: `backend/app/domain/glossary_match.py`

**Interfaces:**
- Consumes: `app.domain.models.Segment`, `app.domain.models.Term`
- Produces: `approved(terms: list[Term]) -> list[Term]` · `terms_in(text: str, terms: list[Term]) -> list[Term]` · `affected_segments(segments: list[Segment], old: list[Term], new: list[Term]) -> list[int]`

`affected_segments` là thứ trả lời câu *"glossary đổi thì bản dịch nào phải xem lại"* — spec §8.1. Không có nó thì tab Thuật ngữ ở frontend sau này không có đường nào biết.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_glossary_match.py
"""Glossary ảnh hưởng tới segment nào. Hàm thuần, test không cần model.

`affected_segments` so ÁNH XẠ thuật ngữ -> bản dịch, không chỉ so tập thuật ngữ:
đổi bản dịch của một thuật ngữ ĐANG xuất hiện cũng làm segment đó phải dịch lại.
"""
from app.domain.glossary_match import affected_segments, approved, terms_in
from app.domain.models import Segment, Term


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text)


def term(t: str, tr: str, *, ok: bool = True) -> Term:
    return Term(id=None, lang="zh", term=t, translation=tr, approved=ok)


def test_approved_filters_unapproved():
    assert [t.term for t in approved([term("a", "A"), term("b", "B", ok=False)])] == ["a"]


def test_terms_in_is_case_insensitive_substring():
    got = terms_in("Con Rồng bay", [term("rồng", "dragon"), term("phượng", "phoenix")])
    assert [t.term for t in got] == ["rồng"]


def test_terms_in_ignores_empty_term():
    assert terms_in("abc", [term("", "x")]) == []


def test_terms_in_reports_each_term_once_in_glossary_order():
    terms = [term("a", "A"), term("b", "B")]
    got = terms_in("a b a", terms)
    assert [t.term for t in got] == ["a", "b"]


def test_affected_is_empty_when_glossary_unchanged():
    segs = [seg(1, "con rồng")]
    g = [term("rồng", "dragon")]
    assert affected_segments(segs, g, g) == []


def test_affected_when_a_new_term_now_appears():
    segs = [seg(1, "con rồng"), seg(2, "con phượng")]
    old = [term("rồng", "dragon")]
    new = [term("rồng", "dragon"), term("phượng", "phoenix")]
    assert affected_segments(segs, old, new) == [2]


def test_affected_when_a_translation_changes_for_a_present_term():
    segs = [seg(1, "con rồng")]
    old = [term("rồng", "dragon")]
    new = [term("rồng", "long")]
    assert affected_segments(segs, old, new) == [1]


def test_affected_when_a_term_is_removed():
    segs = [seg(1, "con rồng")]
    old = [term("rồng", "dragon")]
    assert affected_segments(segs, old, []) == [1]


def test_a_term_not_present_anywhere_affects_nothing():
    segs = [seg(1, "con rồng")]
    assert affected_segments(segs, [], [term("phượng", "phoenix")]) == []
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_glossary_match.py
```
Kỳ vọng: `ModuleNotFoundError: No module named 'app.domain.glossary_match'`.

- [ ] **Step 3: Viết hiện thực tối thiểu**

```python
# backend/app/domain/glossary_match.py
"""Thuật ngữ glossary xuất hiện ở đâu, và glossary đổi thì segment nào phải dịch lại.

Chỉ thuật ngữ ĐÃ DUYỆT mới đi vào prompt và mới tính là ảnh hưởng — spec §8.1 và
§5. Glossary chưa duyệt là bản nháp của người dùng, không phải ràng buộc.
"""
from __future__ import annotations

from .models import Segment, Term


def approved(terms: list[Term]) -> list[Term]:
    return [t for t in terms if t.approved]


def terms_in(text: str, terms: list[Term]) -> list[Term]:
    """Các thuật ngữ nguồn xuất hiện trong `text`, theo thứ tự glossary.

    So khớp không phân biệt hoa thường. Thuật ngữ rỗng bị bỏ qua: chuỗi rỗng là
    chuỗi con của MỌI văn bản, nên nhận nó là nói mọi segment đều bị ảnh hưởng.
    """
    haystack = text.casefold()
    out: list[Term] = []
    seen: set[str] = set()
    for t in terms:
        needle = t.term.strip().casefold()
        if not needle or needle in seen:
            continue
        if needle in haystack:
            out.append(t)
            seen.add(needle)
    return out


def _mapping(segments: list[Segment], terms: list[Term]) -> dict[int, dict[str, str]]:
    return {s.i: {t.term.casefold(): t.translation for t in terms_in(s.text, terms)}
            for s in segments}


def affected_segments(segments: list[Segment], old: list[Term],
                      new: list[Term]) -> list[int]:
    """Id của các segment mà ÁNH XẠ thuật ngữ -> bản dịch đã đổi.

    So ánh xạ chứ không so tập thuật ngữ: đổi bản dịch của một thuật ngữ ĐANG
    xuất hiện làm bản dịch cũ sai, nên segment đó phải dịch lại.
    """
    before, after = _mapping(segments, old), _mapping(segments, new)
    return [s.i for s in segments if before[s.i] != after[s.i]]
```

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_glossary_match.py
```
Kỳ vọng: `10 passed`.

- [ ] **Step 5: Mutation — chứng minh test không rỗng**

Bỏ `if not needle or needle in seen: continue` (chỉ giữ `if needle in seen`) → `test_terms_in_ignores_empty_term` phải đỏ. Phục hồi và verify hash.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/glossary_match.py backend/tests/test_glossary_match.py
git commit -m "feat(domain): thuật ngữ trong segment + segment ảnh hưởng khi glossary đổi"
```

---

### Task 5: `domain/mt_qa.py` — QA tất định sau dịch

> ⚠️ **HIỆU CHỈNH SAU KHI LÀM (Task 5 đã xong ở `91aea83`) — hai chỗ brief dưới đây SAI, giữ lại làm hồ sơ:**
> 1. **Step 1 có 8 hàm `test_`, không phải 9.** Câu "Kỳ vọng: `9 passed`" ở Step 4 là sai; thực tế `8 passed`.
> 2. **Step 3 KHÔNG qua nổi Step 1 của chính nó** (`1 failed, 7 passed`), vì Step 1 dựng cửa sổ **output** bằng 0
>    trong khi Step 3 đo CPS theo **nguồn** ⇒ nhánh đó là code chết. Tệ hơn, **assertion của Step 1 khẳng định một
>    khiếm khuyết**: nó đòi một lời phàn nàn cho một dòng đọc được. Sự thật đã được kiểm bằng đọc
>    `subtitle_format.py:61,74,111` và `pipeline/export.py:80`: **phụ đề render thời gian NGUỒN**. Bản đã ship đo
>    theo cửa sổ nguồn trước, dùng cửa sổ bản dịch làm dự phòng, và in `cps:{i}=nowindow/{n}c` khi **không** cửa sổ
>    nào dương — không bịa ra `0.0s`.
> 3. **`max_len_ratio` phải là `5.0`**, không phải `4.0`: `qa_rules.LENGTH_RATIO_MAX` dùng **cùng phép đo** và đã
>    ship 5.0 vì 4.0 báo động giả. Đo thật: `你好世界 → Xin chào thế giới` = 4.25; `龙 → con rồng` = 8.00.
> 4. Test `test_zero_duration_does_not_divide_by_zero` của brief **đã bị thay** bằng bản mạnh hơn (so danh sách
>    chính xác + ghim `nowindow`) — việc sửa này là **đúng**, không phải nới test.
>
> Phần dưới giữ nguyên văn bản gốc để đối chiếu.

**Files:**
- Create: `backend/tests/test_mt_qa.py`
- Create: `backend/app/domain/mt_qa.py`

**Interfaces:**
- Consumes: `app.domain.models.Segment`, `Term`; `app.domain.glossary_match.terms_in`
- Produces: `QaLimits` (frozen dataclass) · `qa_translation(src: list[Segment], out: list[Segment], *, glossary: list[Term], supports_glossary: bool, limits: QaLimits = QaLimits()) -> list[str]`

Chuỗi issue có **tiền tố ổn định** để grep và test: `cps:`, `length:`, `missing_term:`, `engine_no_glossary`, `empty:`.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_mt_qa.py
"""QA tất định trên bản dịch. Không tốn model, nên phải chạy ở mọi lần dịch.

Mỗi issue có tiền tố ổn định để grep được trong `translations.qa_issues`.
"""
from app.domain.models import Segment, Term
from app.domain.mt_qa import QaLimits, qa_translation


def seg(i: int, text: str, *, dur: float = 1.0) -> Segment:
    return Segment(i=i, start=0.0, end=dur, text=text)


def term(t: str, tr: str) -> Term:
    return Term(id=None, lang="zh", term=t, translation=tr, approved=True)


LIMITS = QaLimits(max_cps=10.0, min_len_ratio=0.5, max_len_ratio=2.0)


def test_clean_translation_reports_nothing():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con rồng")]
    assert qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS) == []


def test_cps_over_limit_is_reported_with_the_id():
    src, out = [seg(1, "a")], [seg(1, "x" * 30, dur=1.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert any(i.startswith("cps:1=") for i in issues), issues


def test_zero_duration_does_not_divide_by_zero():
    src, out = [seg(1, "a")], [seg(1, "b", dur=0.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert any(i.startswith("cps:1=") for i in issues)


def test_too_short_and_too_long_translations_are_reported():
    src = [seg(1, "x" * 10)]
    short = [seg(1, "y")]
    long_ = [seg(1, "z" * 40)]
    assert any(i.startswith("length:1=") for i in
               qa_translation(src, short, glossary=[], supports_glossary=True, limits=LIMITS))
    assert any(i.startswith("length:1=") for i in
               qa_translation(src, long_, glossary=[], supports_glossary=True, limits=LIMITS))


def test_missing_required_term_is_reported():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con rong")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=True, limits=LIMITS)
    assert any(i.startswith("missing_term:1=") for i in issues), issues


def test_present_required_term_is_not_reported():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con rồng lớn")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=True, limits=LIMITS)
    assert not any(i.startswith("missing_term:") for i in issues)


def test_engine_without_glossary_support_gets_a_flag_not_a_missing_term():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con dragon")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=False, limits=LIMITS)
    assert "engine_no_glossary" in issues
    assert not any(i.startswith("missing_term:") for i in issues), \
        "engine không hỗ trợ glossary thì không được buộc tội thiếu thuật ngữ"


def test_empty_translated_text_is_reported():
    src, out = [seg(1, "con rồng")], [seg(1, "   ")]
    assert any(i.startswith("empty:1") for i in
               qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS))
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_mt_qa.py
```
Kỳ vọng: `ModuleNotFoundError: No module named 'app.domain.mt_qa'`.

- [ ] **Step 3: Viết hiện thực tối thiểu**

```python
# backend/app/domain/mt_qa.py
"""QA tất định sau dịch: CPS, tỉ lệ độ dài, thuật ngữ bắt buộc.

Không tốn model nên chạy ở MỌI lần dịch. Đây là lớp bắt lỗi rẻ nhất; ngưỡng cụ
thể cho tiếng Việt còn để ngỏ (spec §12) và đo trên dữ liệu thật.
"""
from __future__ import annotations

from dataclasses import dataclass

from .glossary_match import terms_in
from .models import Segment, Term


@dataclass(frozen=True)
class QaLimits:
    max_cps: float = 21.0          # ký tự mỗi giây; trên ngưỡng là khó đọc
    min_len_ratio: float = 0.25    # bản dịch ngắn hơn thế này là cụt
    max_len_ratio: float = 4.0     # dài hơn thế này là lan man / lặp


def qa_translation(src: list[Segment], out: list[Segment], *, glossary: list[Term],
                   supports_glossary: bool, limits: QaLimits = QaLimits()) -> list[str]:
    """Sinh danh sách issue. Rỗng nghĩa là không thấy vấn đề tất định nào.

    Giả định `check_alignment` đã chạy trước: `src` và `out` khớp id theo thứ tự.
    """
    issues: list[str] = []
    if not supports_glossary and glossary:
        # Thông tin, KHÔNG phải lỗi: engine này không có đường nào nhận glossary.
        issues.append("engine_no_glossary")

    by_id = {s.i: s for s in out}
    for s in src:
        t = by_id.get(s.i)
        if t is None:
            continue
        text = t.text.strip()
        if not text:
            issues.append(f"empty:{s.i}")
            continue

        duration = max(s.end - s.start, 0.0)
        # Chia cho 0 giây là vô nghĩa chứ không phải CPS vô hạn: báo issue thay vì
        # để ZeroDivisionError giết cả job dịch.
        cps = len(text) / duration if duration > 0 else float(len(text))
        if cps > limits.max_cps:
            issues.append(f"cps:{s.i}={cps:.1f}>{limits.max_cps}")

        base = max(len(s.text.strip()), 1)
        ratio = len(text) / base
        if ratio < limits.min_len_ratio or ratio > limits.max_len_ratio:
            issues.append(f"length:{s.i}={ratio:.2f}")

        if supports_glossary:
            # Thuật ngữ bắt buộc phải XUẤT HIỆN trong bản dịch. So không phân biệt
            # hoa thường vì tiếng Việt viết hoa đầu câu là chuyện bình thường.
            lowered = text.casefold()
            for term in terms_in(s.text, glossary):
                if term.translation.strip().casefold() not in lowered:
                    issues.append(f"missing_term:{s.i}={term.term}->{term.translation}")
    return issues
```

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_mt_qa.py
```
Kỳ vọng: `9 passed`.

- [ ] **Step 5: Mutation — chứng minh test không rỗng**

Đổi `if supports_glossary:` thành `if True:` → `test_engine_without_glossary_support_gets_a_flag_not_a_missing_term` phải đỏ. Phục hồi và verify hash.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/mt_qa.py backend/tests/test_mt_qa.py
git commit -m "feat(domain): QA tat dinh sau dich (CPS, do dai, thuat ngu)"
```

---

### Task 6: Port + adapter cho `translations` (đọc/ghi/checkpoint/trạng thái)

> 🔴 **HIỆU CHỈNH BẮT BUỘC CHO TASK NÀY — phần code ở Step 3/Step 4 dưới đây SAI so với mã thật. Mục này thắng.**
>
> **Ba thứ ĐÃ TỒN TẠI — chỉ THÊM, không viết lại:**
> - `SqliteRepos.add_translation` — `sqlite_repos.py:203`. Chữ ký thật:
>   `(*, transcript_id, transcript_version, engine, target_lang, segments, prompt_version, glossary_version=None, qa_issues=None, tokens_in=None, tokens_out=None, duration_ms=None)`.
>   ⇒ **Chỉ thêm** `status: str = "queued"` và ghi nó vào câu INSERT. **Không** đổi `target_lang` thành có default.
> - `SqliteRepos._row_to_translation` — `sqlite_repos.py:180`. ⇒ **Chỉ thêm** `status=row["status"]`.
> - `list_translations` / `list_translations_for_transcript` — đã có, không đụng.
>
> **Phải THÊM mới:** `get_translation`, `update_translation_segments`, `set_translation_status` (như Step 4), cộng khai báo tương ứng trên `ports/repos.py`.
>
> **HAI CHỖ CODE DƯỚI ĐÂY SAI, BỎ ĐI:**
> 1. **KHÔNG có tham số `error`.** Bảng `translations` **không có cột `error`** (`schema.py:30-44`) ⇒ truyền `error=`
>    là `no such column`. Lỗi của job đã nằm ở `jobs.error`; bản dịch không cần cột đó.
> 2. **KHÔNG thêm `bump_glossary_version`.** `upsert_term` **đã tự tăng** `glossary_version` ở
>    `sqlite_repos.py:468-471` (`INSERT ... ON CONFLICT DO UPDATE SET value = CAST(... AS INTEGER)+1`). Thêm hàm
>    đó rồi gọi ở Task 14 sẽ **tăng hai lần mỗi lần sửa glossary**. Thay vào đó hãy **ghim hành vi đã có** bằng một
>    test: gọi `upsert_term` hai lần thì `glossary_version()` tăng đúng 2. `glossary_version()` là getter có sẵn
>    (`sqlite_repos.py:453`).
>
> **`NotFound(LookupError)` tồn tại ở `sqlite_repos.py:21`.** **Đọc** xem `get_transcript` và các hàm anh em ném gì,
> rồi cho `except` trong Step 4 và `pytest.raises` trong test khớp **thực tế** — đừng mặc định là `KeyError`.
>
> 🔴 **Mục I3 của Task 1 chuyển sang đây và phải đóng tại đây:** `Translation.status` hiện **không được ghi và không
> được đọc ở đâu**, nên default của nó không được ghim đầu-cuối. Cụ thể: `add_translation` nhận và ghi `status`;
> `_row_to_translation` map nó; và có test chứng minh `get_translation` trả đúng `status` sau khi
> `set_translation_status` đổi nó — cộng test rằng `add_translation` mặc định ra `"queued"`.
> Nếu bỏ sót, cột này sẽ **mãi mãi đọc ra `"queued"`** dù `set_translation_status` ghi đúng, và
> `GET /api/translations` sẽ báo mọi bản dịch là đang chờ.
>
> **Đếm test:** brief **không** dự đoán số test nữa (bốn dự đoán trước của controller đều sai). Báo cáo số **thật**,
> và với mỗi test mới hãy chạy một mutation và **báo kết quả quan sát được** — kể cả "mutant này sống sót, và đây là
> lý do". Nếu brief dưới đây có ghi "Kỳ vọng: `6 passed`" thì đó là **số cũ**, chỉ để tham khảo.
>
> **Sandbox:** ghi vào `$env:TEMP` **bị từ chối** trong phiên này. Scratch để **ngoài repo nhưng trong workspace**
> rồi xoá.

**Vì sao cần:** hiện `add_translation` **chỉ có trên adapter, không có trên port** (phát hiện M-1 của review Task 18) — một phương thức mà production sắp cần lại không nằm trong giao diện. Và chưa có đường nào để checkpoint (`update_translation_segments`) hay đổi trạng thái. Không có ba phương thức đó thì `TranslateHandler` không viết được.

**Files:**
- Modify: `backend/app/ports/repos.py` (thêm vào khối `# translations`)
- Modify: `backend/app/adapters/persist/sqlite_repos.py`
- Create: `backend/tests/test_repos_translations.py`

**Interfaces:**
- Consumes: `app.domain.models.Translation`, `Segment`, `segments_to_json`/`segments_from_json`
- Produces (trên `Repos`):
  - `add_translation(*, transcript_id: int, transcript_version: int, engine: str, segments: list[Segment], prompt_version: str, target_lang: str = "vi", glossary_version: int | None = None, status: str = "queued") -> int`
  - `get_translation(translation_id: int) -> Translation`
  - `update_translation_segments(translation_id: int, segments: list[Segment]) -> None`
  - `set_translation_status(translation_id: int, status: str, *, qa_issues: list[str] | None = None, tokens_in: int | None = None, tokens_out: int | None = None, duration_ms: int | None = None, error: str | None = None) -> None`
  - `bump_glossary_version() -> int`

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_repos_translations.py
"""Đọc/ghi bảng `translations`: checkpoint append và trạng thái.

Checkpoint ghi APPEND theo thứ tự, nên `len(segments)` chính là tiến độ. Đó là
lý do không cần bảng `translation_segments` mới (spec §3).
"""
import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.models import Segment


@pytest.fixture
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text)


def _transcript(repos) -> int:
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    return repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo",
                                lang="zh", segments=[seg(1, "a"), seg(2, "b")])


def test_add_then_get_round_trips_segments(repos):
    tid = _transcript(repos)
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="opus-mt", segments=[seg(1, "vi")],
                                  prompt_version="opus-p1", glossary_version=3)
    got = repos.get_translation(tr_id)
    assert got.id == tr_id and got.engine == "opus-mt"
    assert got.transcript_version == 1 and got.glossary_version == 3
    assert got.target_lang == "vi"
    assert [s.text for s in got.segments] == ["vi"]
    assert got.status == "queued"


def test_checkpoint_appends_in_order(repos):
    tid = _transcript(repos)
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="opus-mt", segments=[],
                                  prompt_version="opus-p1")
    repos.update_translation_segments(tr_id, [seg(1, "vi1")])
    repos.update_translation_segments(tr_id, [seg(1, "vi1"), seg(2, "vi2")])
    assert [s.i for s in repos.get_translation(tr_id).segments] == [1, 2]


def test_set_status_records_qa_and_tokens(repos):
    tid = _transcript(repos)
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="opus-mt", segments=[],
                                  prompt_version="opus-p1")
    repos.set_translation_status(tr_id, "done", qa_issues=["cps:1=30.0"],
                                 tokens_in=10, tokens_out=20, duration_ms=1234)
    got = repos.get_translation(tr_id)
    assert got.status == "done"
    assert got.qa_issues == ["cps:1=30.0"]
    assert (got.tokens_in, got.tokens_out, got.duration_ms) == (10, 20, 1234)


def test_set_status_to_failed_keeps_segments_already_translated(repos):
    tid = _transcript(repos)
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="opus-mt", segments=[seg(1, "vi1")],
                                  prompt_version="opus-p1")
    repos.set_translation_status(tr_id, "failed")
    got = repos.get_translation(tr_id)
    assert got.status == "failed" and [s.i for s in got.segments] == [1]


def test_get_translation_missing_raises_keyerror(repos):
    with pytest.raises(KeyError):
        repos.get_translation(999)


def test_glossary_version_increases_monotonically(repos):
    first = repos.glossary_version()
    assert repos.bump_glossary_version() == first + 1
    assert repos.bump_glossary_version() == first + 2
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_repos_translations.py
```
Kỳ vọng: FAIL với `AttributeError: 'SqliteRepos' object has no attribute 'get_translation'` (hoặc `TypeError` ở `add_translation` vì thiếu tham số).

- [ ] **Step 3: Thêm năm phương thức vào port**

Trong `backend/app/ports/repos.py`, thay khối `# translations` hiện có bằng:

```python
    # translations
    def add_translation(self, *, transcript_id: int, transcript_version: int,
                        engine: str, segments: list[Segment], prompt_version: str,
                        target_lang: str = "vi", glossary_version: int | None = None,
                        status: str = "queued") -> int: ...
    def get_translation(self, translation_id: int) -> Translation: ...
    def update_translation_segments(self, translation_id: int,
                                    segments: list[Segment]) -> None: ...
    def set_translation_status(self, translation_id: int, status: str, *,
                               qa_issues: list[str] | None = None,
                               tokens_in: int | None = None,
                               tokens_out: int | None = None,
                               duration_ms: int | None = None,
                               error: str | None = None) -> None: ...
    def list_translations(self) -> list[Translation]: ...
    def list_translations_for_transcript(
        self, transcript_id: int) -> list[TranslationSummary]: ...
    def bump_glossary_version(self) -> int: ...
```

- [ ] **Step 4: Hiện thực trong `SqliteRepos`**

Thêm vào `backend/app/adapters/persist/sqlite_repos.py` (ngay sau các phương thức transcript), và **sửa `add_translation` cũ nếu nó đang thiếu tham số** — giữ nguyên hành vi cũ nếu test cũ còn dùng:

```python
    def add_translation(self, *, transcript_id: int, transcript_version: int,
                        engine: str, segments: list[Segment], prompt_version: str,
                        target_lang: str = "vi", glossary_version: int | None = None,
                        status: str = "queued") -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO translations(transcript_id, transcript_version, engine,"
                " target_lang, segments, prompt_version, glossary_version, status,"
                " created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (transcript_id, transcript_version, engine, target_lang,
                 segments_to_json(segments), prompt_version, glossary_version,
                 status, self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def _row_to_translation(self, row: sqlite3.Row) -> Translation:
        return Translation(
            id=row["id"], transcript_id=row["transcript_id"],
            transcript_version=row["transcript_version"], engine=row["engine"],
            segments=segments_from_json(row["segments"]),
            prompt_version=row["prompt_version"], target_lang=row["target_lang"],
            glossary_version=row["glossary_version"],
            qa_issues=json.loads(row["qa_issues"]) if row["qa_issues"] else [],
            tokens_in=row["tokens_in"], tokens_out=row["tokens_out"],
            duration_ms=row["duration_ms"], status=row["status"],
            created_at=row["created_at"],
        )

    def get_translation(self, translation_id: int) -> Translation:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM translations WHERE id=?",
                               (translation_id,)).fetchone()
        if row is None:
            raise KeyError(translation_id)
        return self._row_to_translation(row)

    def update_translation_segments(self, translation_id: int,
                                    segments: list[Segment]) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE translations SET segments=? WHERE id=?",
                         (segments_to_json(segments), translation_id))

    def set_translation_status(self, translation_id: int, status: str, *,
                               qa_issues: list[str] | None = None,
                               tokens_in: int | None = None,
                               tokens_out: int | None = None,
                               duration_ms: int | None = None,
                               error: str | None = None) -> None:
        """Ghi trạng thái và (tuỳ chọn) số liệu QA/token.

        Tham số `None` nghĩa là "không đụng tới cột đó", không phải "ghi NULL":
        một job hỏng giữa đường vẫn phải giữ token đã tiêu của các lô đã xong.
        """
        sets, args = ["status=?"], [status]
        for column, value in (("qa_issues", qa_issues), ("tokens_in", tokens_in),
                              ("tokens_out", tokens_out), ("duration_ms", duration_ms),
                              ("error", error)):
            if value is not None:
                sets.append(f"{column}=?")
                args.append(json.dumps(value, ensure_ascii=False)
                            if column == "qa_issues" else value)
        args.append(translation_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE translations SET {', '.join(sets)} WHERE id=?", args)

    def bump_glossary_version(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='glossary_version'").fetchone()
            nxt = (int(row[0]) if row is not None else 0) + 1
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('glossary_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(nxt),))
            return nxt
```

Đảm bảo `import json` và `from app.domain.models import (... segments_from_json, segments_to_json)` có mặt ở đầu tệp; thêm nếu thiếu.

- [ ] **Step 5: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_repos_translations.py
```
Kỳ vọng: `6 passed`.

- [ ] **Step 6: Cả suite — chú ý `add_translation` cũ**

```bash
cd backend
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python -B -m pytest
```
Kỳ vọng: `526 passed` (không được giảm). Nếu `add_translation` cũ có chữ ký khác và làm đỏ test cũ, **sửa chữ ký chứ không sửa test cũ cho vừa**.

- [ ] **Step 7: Mutation — chứng minh test không rỗng**

Đổi `if value is not None:` thành `if False:` trong `set_translation_status` → `test_set_status_records_qa_and_tokens` phải đỏ. Phục hồi và verify hash.

- [ ] **Step 8: Commit**

```bash
git add backend/app/ports/repos.py backend/app/adapters/persist/sqlite_repos.py backend/tests/test_repos_translations.py
git commit -m "feat(repos): doc/ghi/checkpoint/trang thai cho translations"
```

---

### Task 7: `ports/mt.py` — hợp đồng engine + engine giả dùng chung cho test

**Files:**
- Create: `backend/app/ports/mt.py`
- Create: `backend/tests/fakes_mt.py`
- Create: `backend/tests/test_mt_contract.py`
- Modify: `backend/app/domain/mt.py` (thêm `MtOpts`)

**Interfaces:**
- Consumes: `app.domain.models.Segment`, `Term`
- Produces: `MtOpts` (frozen dataclass, trong `app/domain/mt.py`) · `MtEngine` (Protocol, trong `app/ports/mt.py`) · `FakeMtEngine` (trong `tests/fakes_mt.py`) — **mọi task sau dùng lại nó**

Hợp đồng, và đây là chỗ dễ hiểu sai nhất: engine **giữ nguyên `i`, `start`, `end`** và **chỉ thay `text`**. Timestamp đến từ bản bóc băng, không phải từ engine — engine tự đặt timestamp là làm hỏng phụ đề.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_mt_contract.py
"""Hợp đồng `MtEngine`, ghim bằng engine giả dùng chung.

Điểm dễ sai nhất: engine GIỮ NGUYÊN i/start/end và chỉ thay text. Engine tự đặt
timestamp là làm hỏng phụ đề mà không ai thấy.
"""
from app.domain.models import Segment, Term
from app.domain.mt import MtOpts
from tests.fakes_mt import FakeMtEngine


def seg(i: int, text: str, *, start: float = 0.0) -> Segment:
    return Segment(i=i, start=start, end=start + 1.0, text=text,
                   words=None, speaker="S1")


def test_fake_preserves_identity_and_timing():
    eng = FakeMtEngine(mapping={"a": "A"})
    out = eng.translate([seg(5, "a", start=12.0)], [], MtOpts(source_lang="zh"))
    assert out[0].i == 5 and out[0].start == 12.0 and out[0].end == 13.0
    assert out[0].text == "A"


def test_fake_preserves_words_and_speaker():
    src = seg(1, "a", start=3.0)
    out = FakeMtEngine().translate([src], [], MtOpts(source_lang="zh"))
    assert out[0].speaker == "S1"


def test_fake_returns_exactly_one_output_per_input():
    eng = FakeMtEngine()
    batch = [seg(i, f"t{i}") for i in range(1, 6)]
    assert [s.i for s in eng.translate(batch, [], MtOpts(source_lang="zh"))] == [1, 2, 3, 4, 5]


def test_release_is_idempotent():
    eng = FakeMtEngine()
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    eng.release()
    eng.release()          # lần hai phải là no-op, không ném
    assert eng.release_count == 1


def test_fake_can_be_asked_to_break_alignment():
    eng = FakeMtEngine(drop_ids={2})
    out = eng.translate([seg(1, "a"), seg(2, "b")], [], MtOpts(source_lang="zh"))
    assert [s.i for s in out] == [1]


def test_source_and_target_lang_reach_the_engine():
    eng = FakeMtEngine()
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh", target_lang="vi"))
    assert eng.last_opts == MtOpts(source_lang="zh", target_lang="vi")


def test_supports_glossary_is_reported():
    assert FakeMtEngine().supports_glossary() is True
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_mt_contract.py
```
Kỳ vọng: `ModuleNotFoundError: No module named 'app.ports.mt'`.

- [ ] **Step 3: Thêm `MtOpts` vào `domain/mt.py`**

Thêm vào cuối `backend/app/domain/mt.py`:

```python
@dataclass(frozen=True)
class MtOpts:
    """Tham số của một lần gọi engine. Bất biến, nên so sánh được trong test."""
    source_lang: str
    target_lang: str = "vi"
```

(và thêm `from dataclasses import dataclass` ở đầu tệp nếu thiếu)

- [ ] **Step 4: Viết Protocol**

```python
# backend/app/ports/mt.py
"""Hợp đồng engine dịch. Chỉ Protocol — không hiện thực gì ở đây."""
from __future__ import annotations

from typing import Protocol

from app.domain.models import Segment, Term
from app.domain.mt import MtOpts


class MtEngine(Protocol):
    @property
    def engine_id(self) -> str: ...

    def supports_glossary(self) -> bool:
        """Engine này có đường nào nhận glossary không (spec §8.7.2)."""
        ...

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        """Dịch một lô.

        BẮT BUỘC: trả về đúng bấy nhiêu `Segment`, GIỮ NGUYÊN `i`, `start`, `end`,
        `speaker` và `words` của đầu vào, CHỈ thay `text`. Không bảo đảm được thì
        ném `app.domain.alignment.AlignmentProblem` — KHÔNG trả list ngắn hơn.
        """
        ...

    def release(self) -> None:
        """Đổ model khỏi VRAM. BẮT BUỘC idempotent: gọi lúc chưa nạp là no-op."""
        ...
```

- [ ] **Step 5: Viết engine giả dùng chung**

```python
# backend/tests/fakes_mt.py
"""Engine dịch giả cho test luồng: alignment, retry, hủy, checkpoint, QA.

Cố ý KHÔNG thông minh. Nó chỉ làm đúng hợp đồng, và có công tắc để hỏng đúng chỗ
cần hỏng (`drop_ids`, `fail_times`).
"""
from __future__ import annotations

from app.domain.models import Segment, Term
from app.domain.mt import MtOpts


class FakeMtEngine:
    def __init__(self, *, mapping: dict[str, str] | None = None,
                 drop_ids: set[int] | None = None,
                 fail_times: int = 0) -> None:
        self._mapping = mapping or {}
        self._drop_ids = drop_ids or set()
        self._fail_times = fail_times
        self.release_count = 0
        self.calls: list[list[int]] = []
        self.last_opts: MtOpts | None = None

    @property
    def engine_id(self) -> str:
        return "fake-mt"

    def supports_glossary(self) -> bool:
        return True

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("fake engine: hỏng theo kịch bản test")
        self.last_opts = opts
        self.calls.append([s.i for s in batch])
        out: list[Segment] = []
        for s in batch:
            if s.i in self._drop_ids:
                continue
            out.append(Segment(i=s.i, start=s.start, end=s.end,
                               text=self._mapping.get(s.text, f"[vi]{s.text}"),
                               words=s.words, speaker=s.speaker))
        return out

    def release(self) -> None:
        if self.release_count == 0:
            self.release_count = 1
```

- [ ] **Step 6: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_mt_contract.py
```
Kỳ vọng: `7 passed`.

- [ ] **Step 7: Mutation — chứng minh test không rỗng**

Đổi `if self.release_count == 0:` thành `self.release_count += 1` → `test_release_is_idempotent` phải đỏ. Phục hồi và verify hash.

- [ ] **Step 8: Commit**

```bash
git add backend/app/ports/mt.py backend/app/domain/mt.py backend/tests/fakes_mt.py backend/tests/test_mt_contract.py
git commit -m "feat(ports): hop dong MtEngine + engine gia dung chung cho test"
```

---

### Task 8: `adapters/mt/prompts.py` — dựng prompt và parse kết quả

**Files:**
- Create: `backend/app/adapters/mt/__init__.py`
- Create: `backend/app/adapters/mt/prompts.py`
- Create: `backend/tests/test_mt_prompts.py`

**Interfaces:**
- Consumes: `Segment`, `Term`, `MtOpts`; `app.domain.alignment.AlignmentProblem`
- Produces:
  - `PROMPT_VERSION: dict[str, str]` — khoá theo `engine_id`
  - `system_prompt(glossary: list[Term], *, target_lang: str) -> str`
  - `user_prompt(batch: list[Segment], *, source_lang: str, target_lang: str) -> str`
  - `parse_batch_response(raw: str, batch: list[Segment]) -> list[Segment]`

Đây là **dữ liệu thuần** — test được không cần model, nên mọi lỗi prompt/parse đều bắt được ở đây thay vì chỉ hiện ra khi có Ollama.

Ba failure mode thật của LLM được xử lý và ghim: bọc JSON trong ``` ``` ```, trả thiếu `id`, và trả JSON hỏng.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_mt_prompts.py
"""Dựng prompt và parse phản hồi. Không cần model — nên đây là chỗ bắt lỗi rẻ nhất.

Ba failure mode thật của LLM: bọc JSON trong ```, thiếu id, JSON hỏng.
"""
import pytest

from app.adapters.mt.prompts import (PROMPT_VERSION, parse_batch_response,
                                     system_prompt, user_prompt)
from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text, speaker="S1")


def term(t: str, tr: str) -> Term:
    return Term(id=None, lang="zh", term=t, translation=tr, approved=True)


def test_prompt_version_exists_for_both_shipped_engines():
    assert PROMPT_VERSION["qwen2.5-3b"] and PROMPT_VERSION["opus-mt"]


def test_system_prompt_carries_glossary_pairs():
    p = system_prompt([term("rồng", "dragon")], target_lang="vi")
    assert "rồng" in p and "dragon" in p


def test_system_prompt_without_glossary_says_nothing_about_terms():
    p = system_prompt([], target_lang="vi")
    assert "rồng" not in p and "glossary" not in p.lower()


def test_user_prompt_contains_every_id_and_text():
    p = user_prompt([seg(1, "a"), seg(2, "b")], source_lang="zh", target_lang="vi")
    assert '"i": 1' in p and '"i": 2' in p and "a" in p and "b" in p


def test_parse_maps_text_onto_input_timings():
    batch = [seg(1, "a"), seg(2, "b")]
    raw = '{"translations": [{"i": 1, "text": "A"}, {"i": 2, "text": "B"}]}'
    out = parse_batch_response(raw, batch)
    assert [s.text for s in out] == ["A", "B"]
    assert [s.i for s in out] == [1, 2]
    assert out[0].start == 1.0 and out[0].speaker == "S1", "timestamp/người nói phải lấy từ đầu vào"


def test_parse_strips_markdown_code_fences():
    batch = [seg(1, "a")]
    raw = '```json\n{"translations": [{"i": 1, "text": "A"}]}\n```'
    assert parse_batch_response(raw, batch)[0].text == "A"


def test_parse_raises_alignment_when_an_id_is_missing():
    batch = [seg(1, "a"), seg(2, "b")]
    raw = '{"translations": [{"i": 1, "text": "A"}]}'
    with pytest.raises(AlignmentProblem):
        parse_batch_response(raw, batch)


def test_parse_raises_alignment_when_an_id_is_alien():
    with pytest.raises(AlignmentProblem):
        parse_batch_response('{"translations": [{"i": 9, "text": "A"}]}', [seg(1, "a")])


def test_parse_raises_valueerror_on_broken_json():
    with pytest.raises(ValueError):
        parse_batch_response("không phải json", [seg(1, "a")])


def test_parse_raises_valueerror_when_translations_key_missing():
    with pytest.raises(ValueError):
        parse_batch_response('{"ket_qua": []}', [seg(1, "a")])


def test_parse_accepts_reordered_items_and_restores_input_order():
    batch = [seg(1, "a"), seg(2, "b")]
    raw = '{"translations": [{"i": 2, "text": "B"}, {"i": 1, "text": "A"}]}'
    out = parse_batch_response(raw, batch)
    assert [s.i for s in out] == [1, 2] and [s.text for s in out] == ["A", "B"]
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_mt_prompts.py
```
Kỳ vọng: `ModuleNotFoundError: No module named 'app.adapters.mt'`.

- [ ] **Step 3: Tạo gói và hiện thực**

```bash
cd backend
New-Item -ItemType File -Force app/adapters/mt/__init__.py
```

```python
# backend/app/adapters/mt/prompts.py
"""Dựng prompt cho engine LLM và parse phản hồi về `Segment`.

Dữ liệu thuần: không import model, không gọi mạng ⇒ test được ở mọi máy. Mọi thứ
có thể sai mà không cần model đều phải bị bắt ở đây.
"""
from __future__ import annotations

import json
import re

from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term

#: Phiên bản prompt theo engine. Ghi vào `translations.prompt_version` và
#: `llm_calls.prompt_version`, nên đổi prompt PHẢI đổi chuỗi này — nếu không thì
#: không phân biệt được bản dịch cũ và mới khi prompt thay đổi.
PROMPT_VERSION: dict[str, str] = {
    "qwen2.5-3b": "qwen-json-p1",
    "qwen2.5-7b": "qwen-json-p1",
    "opus-mt": "raw-p1",
}

_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")


def system_prompt(glossary: list[Term], *, target_lang: str) -> str:
    """Vai trò + quy tắc + glossary. Rỗng glossary thì KHÔNG nhắc tới thuật ngữ.

    Nhắc tới glossary khi không có thuật ngữ nào là mời model bịa ra ràng buộc.
    """
    lines = [
        f"Bạn là dịch giả chuyên nghiệp sang {target_lang}.",
        "Dịch sát nghĩa, giữ nguyên văn phong và mức trang trọng của bản gốc.",
        "Trả về DUY NHẤT một đối tượng JSON, không thêm chữ nào khác.",
    ]
    if glossary:
        lines.append("Bắt buộc dùng đúng các thuật ngữ sau:")
        lines.extend(f"- {t.term} => {t.translation}" for t in glossary)
    return "\n".join(lines)


def user_prompt(batch: list[Segment], *, source_lang: str, target_lang: str) -> str:
    items = [{"i": s.i, "text": s.text} for s in batch]
    return (
        f"Dịch từng mục từ {source_lang} sang {target_lang}.\n"
        "Giữ nguyên `i` của từng mục và trả đúng bấy nhiêu mục.\n"
        'Định dạng: {"translations": [{"i": <số>, "text": "<bản dịch>"}]}\n'
        f"Dữ liệu: {json.dumps(items, ensure_ascii=False)}"
    )


def parse_batch_response(raw: str, batch: list[Segment]) -> list[Segment]:
    """Ghép bản dịch vào ĐÚNG segment đầu vào, giữ nguyên timestamp/người nói."""
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"engine không trả JSON hợp lệ: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("translations"), list):
        raise ValueError("JSON thiếu khoá 'translations' hoặc sai kiểu")

    got: dict[int, str] = {}
    for item in data["translations"]:
        if not isinstance(item, dict) or "i" not in item or "text" not in item:
            raise ValueError(f"mục thiếu 'i' hoặc 'text': {item!r}")
        got[int(item["i"])] = str(item["text"])

    expected_ids = [s.i for s in batch]
    if sorted(got) != sorted(expected_ids):
        raise AlignmentProblem(expected_ids, sorted(got),
                               f"engine trả id {sorted(got)}, cần {sorted(expected_ids)}")

    # Duyệt theo batch để thứ tự đầu ra LUÔN bằng thứ tự đầu vào, kể cả khi model
    # trả mục xáo trộn.
    #
    # ⚠️ HIỆU CHỈNH SAU KHI LÀM (Task 8 đã xong ở `fc32ca8`): bản đầu của dòng này
    # dựng `Segment(i=…, start=…, end=…, text=…, words=…, speaker=…)` bằng tay, tức
    # chỉ chép 6/13 trường và ÂM THẦM NUỐT `emotion`, `events`, `avg_logprob`,
    # `no_speech_prob`, `suspect`, `t`, `qa` — ĐÚNG lỗi mà review Task 7 vừa bắt ở
    # `fakes_mt.py`. Dùng `replace` mới đúng. (Review Task 8 xác nhận `suspect` còn
    # bị lật `True` → `False`.) Ngoài ra bản đầu còn thiếu phép kiểm SỐ LƯỢNG mục
    # (nên id trùng bị nuốt im lặng), ép `str()` lên `text` không phải chuỗi (ra phụ
    # đề `"None"`), và để `int(item["i"])` ném `TypeError` trần — cả ba đã được vá ở
    # `fc32ca8`; xem `review-task-8.md` cho bản sửa đúng.
    return [replace(s, text=got[s.i]) for s in batch]
```

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_mt_prompts.py
```
Kỳ vọng: `11 passed`.

- [ ] **Step 5: Mutation — chứng minh test không rỗng**

Đổi `if sorted(got) != sorted(expected_ids):` thành `if False:` → `test_parse_raises_alignment_when_an_id_is_missing` và `..._alien` phải đỏ. Phục hồi và verify hash.

- [ ] **Step 6: Commit**

```bash
git add backend/app/adapters/mt/__init__.py backend/app/adapters/mt/prompts.py backend/tests/test_mt_prompts.py
git commit -m "feat(mt): dung prompt va parse phan hoi LLM"
```

---

### Task 9: `adapters/mt/opus_mt.py` — OPUS-MT (Marian, in-process, CPU)

**Files:**
- Create: `backend/app/adapters/mt/opus_mt.py`
- Create: `backend/tests/test_mt_opus.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/scripts/install.ps1`

**Interfaces:**
- Consumes: `MtEngine` contract, `MtOpts`, `Segment`, `Term`
- Produces: `OpusMtEngine(model_name: str = "Helsinki-NLP/opus-mt-zh-vi", *, device: str = "cpu")` với `engine_id == "opus-mt"`, `supports_glossary() -> False`, `translate(...)`, `release()`

**Quan trọng:** `supports_glossary()` trả `False`, và điều đó **phải chảy tới QA** thành cờ `engine_no_glossary` — spec §8.7.2 nói OPUS-MT không nhận prompt và UI phải cảnh báo. Không được để nó im lặng "thành công" với glossary bị bỏ qua.

Model được **tiêm vào** (`model_factory`) để test chạy được không cần tải 300 MB.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_mt_opus.py
"""OPUS-MT: Marian chạy trong tiến trình, KHÔNG có glossary, KHÔNG có token count.

Model được tiêm vào qua `model_factory` nên test này chạy được trên máy chưa tải
model. Phần chạy model thật nằm ở Task 16 (smoke), không phải ở đây.
"""
import pytest

from app.adapters.mt.opus_mt import OpusMtEngine
from app.domain.models import Segment, Term
from app.domain.mt import MtOpts


class _FakeTokenizer:
    def __call__(self, texts, return_tensors=None, padding=None, truncation=None):
        self.seen = list(texts)
        return {"input_ids": [[1, 2, 3] for _ in texts]}


class _FakeModel:
    def __init__(self, outputs):
        self._outputs = outputs
        self.generate_calls = 0
        self.to_calls = []

    def to(self, device):
        self.to_calls.append(device)
        return self

    def eval(self):
        return self

    def generate(self, **kwargs):
        self.generate_calls += 1
        n = len(kwargs["input_ids"])
        return [[10 + i] for i in range(n)]


class _FakeMarian:
    """Bắt chước `MarianMTModel` + tokenizer đủ để kiểm luồng, không kiểm chất lượng."""

    def __init__(self, translated: list[str]):
        self.translated = list(translated)
        self.tokenizer = _FakeTokenizer()
        self.model = _FakeModel(self.translated)

    def decode(self, ids, skip_special_tokens=True):
        return self.translated.pop(0)


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text, speaker="S1")


def test_supports_glossary_is_false():
    eng = OpusMtEngine(model_factory=lambda: _FakeMarian(["x"]))
    assert eng.supports_glossary() is False


def test_engine_id_is_stable():
    assert OpusMtEngine(model_factory=lambda: _FakeMarian([])).engine_id == "opus-mt"


def test_translate_preserves_identity_and_timing():
    marian = _FakeMarian(["vi1", "vi2"])
    eng = OpusMtEngine(model_factory=lambda: marian)
    out = eng.translate([seg(1, "a"), seg(2, "b")], [], MtOpts(source_lang="zh"))
    assert [s.text for s in out] == ["vi1", "vi2"]
    assert [s.i for s in out] == [1, 2]
    assert out[0].start == 1.0 and out[0].speaker == "S1"


def test_translate_returns_one_output_per_input_even_for_one_segment():
    marian = _FakeMarian(["vi"])
    eng = OpusMtEngine(model_factory=lambda: marian)
    assert len(eng.translate([seg(7, "a")], [], MtOpts(source_lang="zh"))) == 1


def test_glossary_is_accepted_but_ignored_not_rejected():
    """Chữ ký phải nhận glossary; engine bỏ qua nó và QA là chỗ báo cờ."""
    marian = _FakeMarian(["vi"])
    eng = OpusMtEngine(model_factory=lambda: marian)
    terms = [Term(id=None, lang="zh", term="rồng", translation="dragon", approved=True)]
    out = eng.translate([seg(1, "rồng")], terms, MtOpts(source_lang="zh"))
    assert out[0].text == "vi"


def test_model_is_loaded_lazily_and_only_once():
    built = []

    def factory():
        built.append(1)
        return _FakeMarian(["vi", "vi"])

    eng = OpusMtEngine(model_factory=factory)
    assert built == [], "chưa gọi translate thì chưa được nạp model"
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    eng.translate([seg(2, "b")], [], MtOpts(source_lang="zh"))
    assert len(built) == 1, "nạp model hai lần là lãng phí và rò VRAM"


def test_release_is_idempotent_and_forces_reload():
    marian = _FakeMarian(["vi", "vi"])
    eng = OpusMtEngine(model_factory=lambda: marian)
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    eng.release()
    eng.release()          # no-op, không ném
    eng.translate([seg(2, "b")], [], MtOpts(source_lang="zh"))
    assert marian.model.generate_calls == 2


def test_empty_batch_returns_empty_without_loading_model():
    built = []
    eng = OpusMtEngine(model_factory=lambda: (built.append(1), _FakeMarian([]))[1])
    assert eng.translate([], [], MtOpts(source_lang="zh")) == []
    assert built == []
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_mt_opus.py
```
Kỳ vọng: `ModuleNotFoundError: No module named 'app.adapters.mt.opus_mt'`.

- [ ] **Step 3: Viết hiện thực**

```python
# backend/app/adapters/mt/opus_mt.py
"""OPUS-MT (Marian) chạy trong tiến trình, CPU.

Không có glossary và không có token count — đúng như spec §8.7.2. Vì vậy
`supports_glossary()` trả False để QA sinh cờ `engine_no_glossary`, thay vì để
người dùng tưởng glossary đã được áp dụng.
"""
from __future__ import annotations

from typing import Callable

from app.domain.models import Segment, Term
from app.domain.mt import MtOpts

DEFAULT_MODEL = "Helsinki-NLP/opus-mt-zh-vi"


class OpusMtEngine:
    def __init__(self, model_name: str = DEFAULT_MODEL, *, device: str = "cpu",
                 model_factory: Callable[[], object] | None = None) -> None:
        self._model_name = model_name
        self._device = device
        self._factory = model_factory or self._default_factory
        self._marian: object | None = None

    def _default_factory(self) -> object:
        # Import trong hàm: `transformers` nặng và không phải máy nào cũng cài, nên
        # import ở cấp module sẽ làm đỏ cả suite ở máy chưa cài.
        from transformers import MarianMTModel, MarianTokenizer
        tokenizer = MarianTokenizer.from_pretrained(self._model_name)
        model = MarianMTModel.from_pretrained(self._model_name).to(self._device).eval()
        return _MarianBundle(tokenizer, model, self._device)

    @property
    def engine_id(self) -> str:
        return "opus-mt"

    def supports_glossary(self) -> bool:
        return False

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        if not batch:
            return []
        marian = self._ensure_loaded()
        texts = [s.text for s in batch]
        translated = marian.translate(texts)          # type: ignore[attr-defined]
        return [Segment(i=s.i, start=s.start, end=s.end, text=t,
                        words=s.words, speaker=s.speaker)
                for s, t in zip(batch, translated)]

    def release(self) -> None:
        if self._marian is None:
            return
        self._marian = None

    def _ensure_loaded(self) -> object:
        if self._marian is None:
            self._marian = self._factory()
        return self._marian


class _MarianBundle:
    """Bọc tokenizer + model thành một lời gọi `translate(list[str]) -> list[str]`."""

    def __init__(self, tokenizer: object, model: object, device: str) -> None:
        self.tokenizer = tokenizer
        self.model = model
        self.device = device

    def translate(self, texts: list[str]) -> list[str]:
        encoded = self.tokenizer(texts, return_tensors="pt", padding=True,   # type: ignore[operator]
                                 truncation=True)
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        generated = self.model.generate(**encoded)                            # type: ignore[attr-defined]
        return [self.tokenizer.decode(ids, skip_special_tokens=True)          # type: ignore[attr-defined]
                for ids in generated]
```

- [ ] **Step 4: Thêm phụ thuộc**

Thêm vào `backend/requirements.txt` (ghim phiên bản — pip ở máy này chậm vì đọc cache, nên luôn `--no-cache-dir` khi cài):

```
transformers==4.46.3
sentencepiece==0.2.0
sacremoses==0.1.1
```

Và trong `backend/scripts/install.ps1`, thêm ba gói đó vào dòng pip của bước cài phụ thuộc, giữ `--no-cache-dir`. **Không** chạy `install.ps1` ở task này (nó cài GB); chỉ sửa nội dung và để `test_install_script.py` hiện có kiểm cú pháp.

- [ ] **Step 5: Cài ba gói và chạy test**

```bash
cd backend
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --disable-pip-version-check "transformers==4.46.3" "sentencepiece==0.2.0" "sacremoses==0.1.1"
python -B -m pytest tests/test_mt_opus.py
```
Kỳ vọng: `9 passed`.

- [ ] **Step 6: Cả suite**

```bash
cd backend
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python -B -m pytest
```
Kỳ vọng: `535 passed`.

- [ ] **Step 7: Mutation — chứng minh test không rỗng**

Đổi `if self._marian is None: return` trong `release()` thành `return` ngay đầu hàm → `test_release_is_idempotent_and_forces_reload` phải đỏ. Phục hồi và verify hash.

- [ ] **Step 8: Commit**

```bash
git add backend/app/adapters/mt/opus_mt.py backend/tests/test_mt_opus.py backend/requirements.txt backend/scripts/install.ps1
git commit -m "feat(mt): adapter OPUS-MT (Marian, CPU, khong glossary)"
```

---

### Task 10: `adapters/mt/ollama_mt.py` — Qwen2.5 qua Ollama

> 🔴 **HIỆU CHỈNH BẮT BUỘC CHO TASK NÀY (mục này thắng phần code bên dưới):**
> 1. **BỎ tham số `releaser_hook`.** Governor gọi thẳng `engine.release()` (Task 12 đăng ký nó), nên một hook **bên
>    trong** `release()` là thừa — và tệ hơn, nó cho phép người gọi **nhét việc vào đường đổ model**, đúng chỗ không
>    nên có side effect lạ. `release()` chỉ làm một việc: đổ model khỏi VRAM, idempotent.
> 2. **`supports_glossary()` phải là DỮ LIỆU, không phải hằng `True`.** Hiệu chỉnh 17: nguồn sự thật là
>    `spec.capabilities["glossary_prompt"]`. Adapter **không** có spec, nên nhận cờ đó qua constructor
>    (`supports_glossary: bool = True`) và Task 12 truyền từ spec. Test phải ghim **cả hai** giá trị.
> 3. **`model` là `model_ref` của registry, không phải chuỗi tôi bịa.** `registry.json` ghi
>    `"model_ref": "qwen2.5:3b-instruct-q4_K_M"`, không phải `"qwen2.5:3b"`. Task 12 truyền `model_ref` vào; mặc định
>    trong adapter chỉ để chạy được test. **Nếu tag đó không tồn tại trên Ollama thì đó là lỗi của `registry.json`** —
>    báo lại, đừng tự đổi tag trong adapter, vì Task 12's probe availability dựa vào chính tag đó.
> 4. **ĐO TRƯỚC, VIẾT SAU — đây là lý do task này tồn tại.** Các khoá tôi giả định dưới đây (`message.content`,
>    `prompt_eval_count`, `eval_count`, `total_duration`) là **giả định**, chưa từng đo trong dự án. Gọi thật
>    `POST /api/chat` rồi **dán nguyên văn** phản hồi vào báo cáo, và viết parser theo **số đo**, không theo mục này.
>    Nếu đo ra khác, **sửa parser**, đừng sửa test cho vừa.
> 5. **Đo `keep_alive` bằng `ollama ps`**: gọi với `keep_alive: "30m"` rồi `ollama ps`; gọi với `keep_alive: 0` rồi
>    `ollama ps` lại. Nếu `keep_alive: 0` **không** đổ model thì `release()` phải đổi cách. Ghi cả ba lần chạy
>    `ollama ps` nguyên văn.
> 6. Brief **không** dự đoán số test; báo số **thật**, và với mỗi test chạy mutation rồi báo **kết quả quan sát được**.
> 7. **Phục hồi mutation phải kiểm CẢ hash LẪN byte** — `core.autocrlf=true` làm `git hash-object` khớp trên nội dung
>    CRLF. So thêm với `git cat-file -p HEAD:<path>`. Sandbox từ chối ghi `$env:TEMP` và cả thư mục ngoài workspace.

**Files:**
- Create: `backend/tests/test_mt_ollama.py`
- Create: `backend/app/adapters/mt/ollama_mt.py`

**Interfaces:**
- Consumes: `MtEngine` contract, `prompts.py`, `MtOpts`, `CallStats`
- Produces: `OllamaMtEngine(model: str = "qwen2.5:3b", *, base_url: str = "http://127.0.0.1:11434", keep_alive: str = "30m", client=None, releaser_hook=None)` với `engine_id == "qwen2.5-3b"`, `supports_glossary() -> True`, `last_stats: CallStats | None`

**Quan trọng — đo trước, viết sau.** Hình dạng phản hồi của Ollama và tác dụng thật của `keep_alive` **chưa được đo trong dự án này**. Spec §5 ghi rõ phải đo bằng `ollama ps`. Vì vậy Step 1 là **thăm dò thật** rồi mới viết parser; nếu hình dạng đo được khác những gì dưới đây giả định, **sửa parser theo số đo, không sửa test cho vừa**.

- [ ] **Step 1: Thăm dò Ollama thật và ghi lại hình dạng**

Nếu Ollama chưa cài, cài trước (Task 16 làm phần cài đặt đầy đủ; ở đây chỉ cần nó chạy được):

```powershell
winget install --id Ollama.Ollama -e
ollama --version
ollama pull qwen2.5:3b
ollama ps
```

Rồi gọi thẳng API và **dán nguyên văn** phản hồi vào báo cáo task:

```powershell
$body = @{ model = "qwen2.5:3b"; stream = $false; format = "json"
  messages = @(@{ role = "user"; content = "Tra ve JSON: {""translations"":[{""i"":1,""text"":""xin chao""}]}" })
  keep_alive = "30m" } | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri http://127.0.0.1:11434/api/chat -Method Post -Body $body -ContentType "application/json" |
  ConvertTo-Json -Depth 6
ollama ps
```

Ghi lại: khoá nào chứa nội dung trả về, có `prompt_eval_count`/`eval_count` không, và `ollama ps` nói model còn nằm trong VRAM hay không. **Đây là bằng chứng cho `last_stats` và cho `release()`.**

- [ ] **Step 2: Viết test đỏ (client giả theo hình dạng đã đo)**

```python
# backend/tests/test_mt_ollama.py
"""OllamaMtEngine: HTTP, JSON, token count, releaser idempotent.

Client được TIÊM vào nên test chạy được không cần Ollama. Hình dạng phản hồi
trong `_FakeClient` phải khớp phản hồi THẬT đã đo ở Step 1 — nếu Ollama trả khác
thì sửa chỗ này theo số đo.
"""
import pytest

from app.adapters.mt.ollama_mt import OllamaMtEngine
from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Term
from app.domain.mt import MtOpts


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, replies):
        self._replies = list(replies)
        self.bodies = []

    def post(self, url, json=None, timeout=None):
        self.bodies.append({"url": url, "json": json, "timeout": timeout})
        return _Resp(self._replies.pop(0))


def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text, speaker="S1")


def reply(content: str, *, pin=11, pout=22):
    return {"message": {"role": "assistant", "content": content},
            "prompt_eval_count": pin, "eval_count": pout, "done": True}


def test_engine_id_and_glossary_support():
    eng = OllamaMtEngine(client=_FakeClient([]))
    assert eng.engine_id == "qwen2.5-3b"
    assert eng.supports_glossary() is True


def test_translate_parses_json_and_preserves_timing():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"Xin chào"}]}')])
    eng = OllamaMtEngine(client=client)
    out = eng.translate([seg(1, "你好")], [], MtOpts(source_lang="zh"))
    assert out[0].text == "Xin chào" and out[0].start == 1.0 and out[0].speaker == "S1"


def test_request_carries_model_json_format_and_keep_alive():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"x"}]}')])
    eng = OllamaMtEngine(model="qwen2.5:3b", keep_alive="30m", client=client)
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    body = client.bodies[0]["json"]
    assert body["model"] == "qwen2.5:3b"
    assert body["format"] == "json"
    assert body["keep_alive"] == "30m"
    assert body["stream"] is False


def test_glossary_reaches_the_system_message():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"x"}]}')])
    eng = OllamaMtEngine(client=client)
    terms = [Term(id=None, lang="zh", term="龙", translation="rồng", approved=True)]
    eng.translate([seg(1, "龙")], terms, MtOpts(source_lang="zh"))
    sent = client.bodies[0]["json"]["messages"]
    assert sent[0]["role"] == "system" and "rồng" in sent[0]["content"]


def test_token_counts_are_recorded():
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"x"}]}', pin=7, pout=9)])
    eng = OllamaMtEngine(client=client)
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    assert (eng.last_stats.tokens_in, eng.last_stats.tokens_out) == (7, 9)


def test_alignment_failure_is_raised_not_hidden():
    client = _FakeClient([reply('{"translations":[]}')])
    eng = OllamaMtEngine(client=client)
    with pytest.raises(AlignmentProblem):
        eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))


def test_release_calls_the_releaser_once_and_is_idempotent():
    calls = []
    eng = OllamaMtEngine(client=_FakeClient([]), releaser_hook=lambda: calls.append(1))
    eng.release()
    eng.release()
    assert calls == [1], "releaser phải idempotent: gọi lúc không có model là no-op"


def test_release_after_translate_unloads_and_is_safe_twice():
    calls = []
    client = _FakeClient([reply('{"translations":[{"i":1,"text":"x"}]}')])
    eng = OllamaMtEngine(client=client, releaser_hook=lambda: calls.append(1))
    eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
    eng.release()
    eng.release()
    assert len(calls) >= 1
    assert client.bodies[-1]["json"]["keep_alive"] == 0, "đổ model = gửi keep_alive 0"


def test_empty_batch_makes_no_http_call():
    client = _FakeClient([])
    eng = OllamaMtEngine(client=client)
    assert eng.translate([], [], MtOpts(source_lang="zh")) == []
    assert client.bodies == []


def test_http_error_becomes_runtimeerror_with_context():
    client = _FakeClient([_Resp({}, status=500)])
    eng = OllamaMtEngine(client=client)
    with pytest.raises(RuntimeError):
        eng.translate([seg(1, "a")], [], MtOpts(source_lang="zh"))
```

- [ ] **Step 3: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_mt_ollama.py
```
Kỳ vọng: `ModuleNotFoundError: No module named 'app.adapters.mt.ollama_mt'`.

- [ ] **Step 4: Viết hiện thực**

```python
# backend/app/adapters/mt/ollama_mt.py
"""Qwen2.5 qua Ollama. HTTP tới một tiến trình RIÊNG, nên VRAM do Ollama quản.

Vì Ollama tự quản VRAM, engine này đăng ký một releaser với governor để chỉ còn
MỘT đầu mối đổ model (spec §5). Releaser BẮT BUỘC idempotent.
"""
from __future__ import annotations

from typing import Callable

import httpx

from app.adapters.mt.prompts import PROMPT_VERSION, parse_batch_response, system_prompt, user_prompt
from app.domain.models import CallStats, Segment, Term
from app.domain.mt import MtOpts

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_KEEP_ALIVE = "30m"
_TIMEOUT_S = 300.0


class OllamaMtEngine:
    def __init__(self, model: str = "qwen2.5:3b", *, base_url: str = DEFAULT_BASE_URL,
                 keep_alive: str = DEFAULT_KEEP_ALIVE,
                 client: object | None = None,
                 releaser_hook: Callable[[], None] | None = None) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._keep_alive = keep_alive
        self._client = client or httpx.Client()
        self._releaser_hook = releaser_hook
        self._loaded = False
        self.last_stats: CallStats | None = None

    @property
    def engine_id(self) -> str:
        return self._model.split(":")[0]

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION.get(self.engine_id, "unknown")

    def supports_glossary(self) -> bool:
        return True

    def translate(self, batch: list[Segment], glossary: list[Term],
                  opts: MtOpts) -> list[Segment]:
        if not batch:
            return []
        body = {
            "model": self._model,
            "stream": False,
            "format": "json",              # Ollama ép đầu ra là JSON hợp lệ
            "keep_alive": self._keep_alive,
            "options": {"temperature": 0.1},
            "messages": [
                {"role": "system",
                 "content": system_prompt(glossary, target_lang=opts.target_lang)},
                {"role": "user",
                 "content": user_prompt(batch, source_lang=opts.source_lang,
                                        target_lang=opts.target_lang)},
            ],
        }
        resp = self._client.post(f"{self._base_url}/api/chat", json=body,
                                 timeout=_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        self._loaded = True
        self.last_stats = CallStats(
            tokens_in=data.get("prompt_eval_count"),
            tokens_out=data.get("eval_count"),
            duration_ms=int((data.get("total_duration") or 0) / 1_000_000) or None,
        )
        content = data.get("message", {}).get("content", "")
        return parse_batch_response(content, batch)

    def release(self) -> None:
        """Đổ model khỏi VRAM. Gọi lúc chưa nạp là NO-OP (hợp đồng idempotent)."""
        if not self._loaded:
            return
        self._loaded = False
        try:
            self._client.post(
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": [], "keep_alive": 0},
                timeout=30.0,
            )
        except Exception:
            # Không đổ được model thì đừng giết luồng đang chạy: VRAM sẽ được
            # Ollama tự thu hồi theo keep_alive. Nhưng trạng thái nội bộ đã hạ
            # xuống chưa-nạp, nên lần release sau không thử lại.
            pass
        if self._releaser_hook is not None:
            self._releaser_hook()
```

- [ ] **Step 5: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_mt_ollama.py
```
Kỳ vọng: `10 passed`.

- [ ] **Step 6: Mutation — chứng minh test không rỗng**

Đổi `if not self._loaded:` trong `release()` thành `if True:` → `test_release_calls_the_releaser_once_and_is_idempotent` phải đỏ. Phục hồi và verify hash.

- [ ] **Step 7: Commit**

```bash
git add backend/app/adapters/mt/ollama_mt.py backend/tests/test_mt_ollama.py
git commit -m "feat(mt): adapter Ollama cho Qwen2.5 (keep_alive, token count, releaser)"
```

---

### Task 11: `pipeline/translate.py` — `TranslateHandler`

> 🔴 **HIỆU CHỈNH BẮT BUỘC CHO TASK NÀY (mục này thắng phần code bên dưới):**
> 1. **`report` nhận HAI tham số.** Giao thức thật là
>    `JobHandler.run(self, job, report: Callable[[float, str], None])` — `worker.py:24`. **Mọi** chỗ trong code ở
>    Step 3 dưới đây gọi `report("...")` với **một** tham số là **SAI**; phải là `report(job.progress, "...")`.
>    Implementer phải **đọc `backend/app/worker.py:19-30`** trước khi viết, và đọc một handler đã ship
>    (`pipeline/transcribe.py`, `pipeline/export.py`) để bắt chước cách nó gọi `report`.
> 2. **`update_translation_segments` nay NÉM `NotFound`** khi `id` không tồn tại (vòng sửa Task 6, `ead5b4b`).
>    Nghĩa là một `id` sai **không còn im lặng**: handler phải để nó thành job `FAILED` với thông báo hành động được,
>    **không** nuốt lỗi. Đây chính là điều mà bản no-op im lặng đã che mất.
> 3. **Ai cộng dồn danh sách — đã chốt ở spec §3 (sửa sau Task 6):** **adapter CHỈ ghi đúng danh sách được đưa, nó
>    KHÔNG tự nối.** Handler giữ `done` trong bộ nhớ, `done.extend(translated)`, rồi gọi
>    `update_translation_segments(id, done)`. Vì vậy `len(done)` **là** tiến độ.
> 4. **`engines` được khoá theo `spec.id` của registry**, không theo `engine_id` của engine. Lý do đã đo ở Task 10:
>    quy tắc suy `engine_id` từ tag **không** tái tạo được id registry cho HY-MT (`hy-mt1.5-7b-q4_K_M` vs
>    `hy-mt-1.5-7b`) ⇒ khoá theo `engine_id` sẽ `KeyError`. Task 12 chịu trách nhiệm dựng dict đúng khoá; task này
>    chỉ cần `self._engines[engine_id]` và một test cho ca id lạ.
> 5. **Chữ ký thật của các hàm bạn gọi** (đọc lại trước khi viết):
>    `qa_translation(src, out, *, glossary, supports_glossary, limits)` với `QaLimits(max_len_ratio=5.0)` (đã sửa ở
>    Task 5) · `batch_segments(segments, *, max_chars)` · `check_alignment(src, out)` ném `AlignmentProblem` có
>    `.expected_ids`/`.got_ids`/`.reason` · `approved(terms)` · `MtOpts(source_lang, target_lang="vi")` ·
>    `MtEngine.translate(batch, glossary, opts)`.
> 6. **KHÔNG dựng `Segment` bằng tay** ở bất cứ đâu trong handler — engine đã trả `Segment` đúng; dùng lại chính
>    object đó. Hai task trước trong phase này đã ship lỗi dựng tay làm nuốt 7/13 trường.
> 7. Brief **không** dự đoán số test (sáu dự đoán của tôi đã sai). Báo số **thật**, và với mỗi test chạy mutation rồi
>    báo **kết quả quan sát được**, kể cả "mutant này sống sót, và đây là lý do".
> 8. **Phục hồi mutation phải kiểm CẢ hash LẪN byte** (`core.autocrlf=true` làm hash khớp trên CRLF). Sandbox từ chối
>    ghi `$env:TEMP` **và** ghi ra ngoài workspace — scratch để trong workspace nhưng ngoài cây repo, rồi xoá.

**Đây là task trung tâm của phase.** Nó ghép mọi thứ đã làm: chia lô, gọi engine, chính sách alignment ba bước, checkpoint, hủy, retry, QA.

**Files:**
- Create: `backend/app/pipeline/translate.py`
- Create: `backend/tests/test_translate_handler.py`

**Interfaces:**
- Consumes: `Repos`, `MtEngine`, `batch_segments`, `check_alignment`, `qa_translation`, `approved`, `AlignmentProblem`
- Produces: `DEFAULT_BATCH_CHARS: int` · `TranslateHandler(repos, engines: dict[str, MtEngine], *, batch_chars: int = DEFAULT_BATCH_CHARS, limits: QaLimits = QaLimits())` với:
  - `handles() -> str` trả `"translate"`
  - `run(job, report) -> None`
  - `translate(*, translation_id: int, transcript_id: int, engine_id: str, source_lang: str, target_lang: str, job) -> None`

**Chính sách alignment ba bước (spec §4.2)** — ghim đúng thứ tự:
1. Lô lệch ⇒ **retry một lần** với cùng lô.
2. Vẫn lệch ⇒ **hạ cấp xuống từng segment** (`batch_segments(..., max_chars=1)` là cách rẻ nhất để có lô 1 phần tử).
3. Vẫn sai ⇒ **`failed`**, giữ phần đã dịch, `RuntimeError` nêu rõ id nào thiếu.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_translate_handler.py
"""TranslateHandler: lô, alignment 3 bước, checkpoint, hủy, retry, QA.

Dùng engine GIẢ nên không cần model. Đây là chỗ ghim hành vi mà 1a đã trả giá để
học: xanh test không có nghĩa là chạy được, nên các test ở đây phải ĐỎ khi logic
đổi — mỗi test có một mutation tương ứng ở Step 5.
"""
import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.models import Segment
from app.domain.mt_qa import QaLimits
from app.pipeline.translate import TranslateHandler
from tests.fakes_mt import FakeMtEngine


class _Job:
    def __init__(self, job_id=1):
        self.id = job_id
        self.state = "running"
        self.progress = 0.0
        self.cancel_requested = False
        self.logs = []


@pytest.fixture
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def seg(i, text):
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text)


@pytest.fixture
def transcript(repos):
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    segs = [seg(i, f"câu {i}") for i in range(1, 6)]
    tid = repos.add_transcript(source_id=sid, engine="fw", lang="zh", segments=segs)
    return tid, segs


def _handler(repos, engine, **kw):
    return TranslateHandler(repos, {"fake-mt": engine}, **kw)


def test_handles_translate(repos):
    assert _handler(repos, FakeMtEngine()).handles() == "translate"


def test_all_segments_get_translated_in_order(repos, transcript):
    tid, segs = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")
    _handler(repos, FakeMtEngine()).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="vi", job=_Job())
    got = repos.get_translation(tr_id)
    assert [s.i for s in got.segments] == [1, 2, 3, 4, 5]
    assert got.status == "done"


def test_job_progress_reaches_one(repos, transcript):
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")
    job = _Job()
    _handler(repos, FakeMtEngine(), batch_chars=1).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="vi", job=job)
    assert job.progress == 1.0


def test_checkpoint_happens_every_batch(repos, transcript):
    """Hủy giữa đường phải còn phần đã dịch, nên checkpoint không được dồn tới cuối."""
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")
    seen = []
    engine = FakeMtEngine()
    real_translate = engine.translate

    def spy(batch, glossary, opts):
        seen.append(len(repos.get_translation(tr_id).segments))
        return real_translate(batch, glossary, opts)

    engine.translate = spy          # type: ignore[method-assign]
    _handler(repos, engine, batch_chars=1).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="vi", job=_Job())
    assert seen == [0, 1, 2, 3, 4], "trước mỗi lô, số segment đã ghi phải tăng dần"


def test_alignment_retry_happens_once_then_single_segment_fallback(repos, transcript):
    """Lô 5 phần tử lệch -> retry 1 lần -> hạ cấp TỪNG segment (5 lô 1 phần tử)."""
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")
    engine = FakeMtEngine(drop_ids={3})
    with pytest.raises(RuntimeError):
        _handler(repos, engine, batch_chars=10_000).translate(
            translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
            source_lang="zh", target_lang="vi", job=_Job())
    # Lô lớn: gọi 1 lần (lệch) + 1 lần retry (lệch) -> hạ cấp 5 lô 1 phần tử, trong
    # đó 4 lô thành công và lô id=3 hỏng.
    assert engine.calls[0] == [1, 2, 3, 4, 5]
    assert engine.calls[1] == [1, 2, 3, 4, 5], "bước (a): retry đúng MỘT lần"
    assert engine.calls[2:] == [[1], [2], [3], [4], [5]], "bước (b): hạ cấp từng segment"


def test_failure_keeps_what_was_already_translated(repos, transcript):
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")
    with pytest.raises(RuntimeError):
        _handler(repos, FakeMtEngine(drop_ids={3}), batch_chars=1).translate(
            translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
            source_lang="zh", target_lang="vi", job=_Job())
    got = repos.get_translation(tr_id)
    assert got.status == "failed"
    assert [s.i for s in got.segments] == [1, 2], "phần đã dịch trước chỗ hỏng phải còn"


def test_failure_message_names_the_missing_segment(repos, transcript):
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")
    with pytest.raises(RuntimeError) as exc:
        _handler(repos, FakeMtEngine(drop_ids={4}), batch_chars=1).translate(
            translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
            source_lang="zh", target_lang="vi", job=_Job())
    assert "4" in str(exc.value)


def test_cancel_between_batches_stops_and_marks_cancelled(repos, transcript):
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")
    job = _Job()
    engine = FakeMtEngine()
    real = engine.translate

    def cancel_after_first(batch, glossary, opts):
        out = real(batch, glossary, opts)
        job.cancel_requested = True
        return out

    engine.translate = cancel_after_first        # type: ignore[method-assign]
    _handler(repos, engine, batch_chars=1).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="vi", job=job)
    got = repos.get_translation(tr_id)
    assert got.status == "cancelled"
    assert len(got.segments) == 1, "hủy sau lô đầu thì chỉ có 1 segment"


def test_retry_resumes_from_first_missing_segment(repos, transcript):
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[],
                                  prompt_version="p1")
    with pytest.raises(RuntimeError):
        _handler(repos, FakeMtEngine(drop_ids={3}), batch_chars=1).translate(
            translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
            source_lang="zh", target_lang="vi", job=_Job())
    engine = FakeMtEngine()
    _handler(repos, engine, batch_chars=1).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="vi", job=_Job())
    assert engine.calls[0] == [3], "đã có 1,2 thì không được dịch lại"
    assert [s.i for s in repos.get_translation(tr_id).segments] == [1, 2, 3, 4, 5]


def test_qa_issues_are_written(repos, transcript):
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")
    lim = QaLimits(max_cps=0.001, min_len_ratio=0.0, max_len_ratio=1e9)
    _handler(repos, FakeMtEngine(), batch_chars=1, limits=lim).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="vi", job=_Job())
    assert any(i.startswith("cps:") for i in repos.get_translation(tr_id).qa_issues)


def test_engine_without_glossary_sets_the_flag(repos, transcript):
    tid, _ = transcript
    repos.upsert_term(lang="zh", term="câu 1", translation="cau 1",
                      note=None, approved=True)
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")

    class _NoGlossary(FakeMtEngine):
        def supports_glossary(self):
            return False

    _handler(repos, _NoGlossary(), batch_chars=1).translate(
        translation_id=tr_id, transcript_id=tid, engine_id="fake-mt",
        source_lang="zh", target_lang="vi", job=_Job())
    assert "engine_no_glossary" in repos.get_translation(tr_id).qa_issues


def test_unknown_engine_id_fails_before_touching_the_translation(repos, transcript):
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="khong-co", segments=[], prompt_version="p1")
    with pytest.raises(KeyError):
        _handler(repos, FakeMtEngine()).translate(
            translation_id=tr_id, transcript_id=tid, engine_id="khong-co",
            source_lang="zh", target_lang="vi", job=_Job())


def test_run_reads_the_job_payload(repos, transcript):
    tid, _ = transcript
    tr_id = repos.add_translation(transcript_id=tid, transcript_version=1,
                                  engine="fake-mt", segments=[], prompt_version="p1")
    job = _Job()
    job.payload = {"translation_id": tr_id, "transcript_id": tid,
                   "engine_id": "fake-mt", "source_lang": "zh", "target_lang": "vi"}
    _handler(repos, FakeMtEngine()).run(job, report=lambda line: None)
    assert repos.get_translation(tr_id).status == "done"
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_translate_handler.py
```
Kỳ vọng: `ModuleNotFoundError: No module named 'app.pipeline.translate'`.

- [ ] **Step 3: Viết hiện thực**

```python
# backend/app/pipeline/translate.py
"""Handler dịch: một job cho MỘT bản dịch, batch hoá bên trong, checkpoint mỗi lô.

Vì sao một job chứ không nhiều job nhỏ: `translations` là một hàng, một version;
`Job.progress` biểu diễn được % của cả bản dịch; và API không bị rò chi tiết cài
đặt (spec §3).

Bất biến: `translations.segments` chỉ chứa bản dịch khớp ĐÚNG id đầu vào, theo
đúng thứ tự. Phần chưa dịch là THIẾU DÒNG, không bao giờ là dòng rỗng.
"""
from __future__ import annotations

from typing import Callable

from app.domain.alignment import AlignmentProblem, check_alignment
from app.domain.glossary_match import approved
from app.domain.models import Segment
from app.domain.mt import MtOpts
from app.domain.mt_qa import QaLimits, qa_translation
from app.domain.mt import batch_segments

DEFAULT_BATCH_CHARS = 1200


class TranslateHandler:
    def __init__(self, repos, engines: dict[str, object], *,
                 batch_chars: int = DEFAULT_BATCH_CHARS,
                 limits: QaLimits = QaLimits()) -> None:
        self._repos = repos
        self._engines = engines
        self._batch_chars = batch_chars
        self._limits = limits

    def handles(self) -> str:
        return "translate"

    def run(self, job, report: Callable[[str], None]) -> None:
        p = job.payload or {}
        self.translate(
            translation_id=int(p["translation_id"]),
            transcript_id=int(p["transcript_id"]),
            engine_id=str(p["engine_id"]),
            source_lang=str(p.get("source_lang") or "zh"),
            target_lang=str(p.get("target_lang") or "vi"),
            job=job,
            report=report,
        )

    def translate(self, *, translation_id: int, transcript_id: int, engine_id: str,
                  source_lang: str, target_lang: str, job,
                  report: Callable[[str], None] = lambda line: None) -> None:
        engine = self._engines[engine_id]        # KeyError = id sai, hỏng TRƯỚC khi ghi gì
        opts = MtOpts(source_lang=source_lang, target_lang=target_lang)
        glossary = approved(self._repos.list_terms(lang=source_lang))

        source = self._repos.get_transcript(transcript_id).segments
        done = list(self._repos.get_translation(translation_id).segments)
        done_ids = {s.i for s in done}
        if done:
            self._repos.set_translation_status(translation_id, "running")

        remaining = [s for s in source if s.i not in done_ids]
        batches = batch_segments(remaining, max_chars=self._batch_chars)
        total = len(source)

        for batch in batches:
            if job.cancel_requested:
                self._repos.set_translation_status(translation_id, "cancelled")
                job.progress = len(done) / total if total else 1.0
                return

            translated = self._translate_batch(engine, batch, glossary, opts, report)
            if translated is None:
                self._repos.set_translation_status(translation_id, "failed")
                missing = [s.i for s in batch]
                raise RuntimeError(f"lô dịch thất bại, thiếu segment {missing}")

            # Checkpoint: append theo thứ tự nên len(segments) LÀ tiến độ.
            done.extend(translated)
            self._repos.update_translation_segments(translation_id, done)
            job.progress = len(done) / total if total else 1.0
            report(f"đã dịch {len(done)}/{total}")

        issues = qa_translation(source, done, glossary=glossary,
                                supports_glossary=engine.supports_glossary(),
                                limits=self._limits)
        stats = getattr(engine, "last_stats", None)
        self._repos.set_translation_status(
            translation_id, "done", qa_issues=issues,
            tokens_in=getattr(stats, "tokens_in", None),
            tokens_out=getattr(stats, "tokens_out", None),
            duration_ms=getattr(stats, "duration_ms", None),
        )
        report(f"xong: {len(done)} segment, {len(issues)} issue QA")

    def _translate_batch(self, engine, batch: list[Segment], glossary, opts,
                         report) -> list[Segment] | None:
        """Chính sách alignment 3 bước (spec §4.2). Trả `None` khi thất bại hẳn."""
        for attempt in (1, 2):
            try:
                out = engine.translate(batch, glossary, opts)
                check_alignment(batch, out)
                return out
            except AlignmentProblem as exc:
                report(f"lệch alignment (lần {attempt}): {exc.reason}")

        # (b) Hạ cấp: lô lớn là lúc LLM hay hỏng nhất, nên dịch từng segment.
        report("hạ cấp xuống dịch từng segment")
        out: list[Segment] = []
        for s in batch:
            try:
                one = engine.translate([s], glossary, opts)
                check_alignment([s], one)
                out.append(one[0])
            except AlignmentProblem as exc:
                report(f"segment {s.i} thất bại: {exc.reason}")
                return None
        return out
```

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_translate_handler.py
```
Kỳ vọng: `13 passed`.

- [ ] **Step 5: Mutation — mỗi test quan trọng phải đỏ được**

| Mutation | Test phải đỏ |
|---|---|
| Bỏ `self._repos.update_translation_segments(...)` trong vòng lặp | `test_checkpoint_happens_every_batch` |
| Đổi `for attempt in (1, 2):` thành `for attempt in (1,):` | `test_alignment_retry_happens_once_then_single_segment_fallback` |
| Bỏ khối hạ cấp từng segment (trả `None` ngay) | `test_alignment_retry_happens_once_then_single_segment_fallback` |
| Bỏ `if job.cancel_requested:` | `test_cancel_between_batches_stops_and_marks_cancelled` |
| Bỏ `remaining = [s for s in source if s.i not in done_ids]` (dịch lại từ đầu) | `test_retry_resumes_from_first_missing_segment` |
| Bỏ `qa_issues=issues` khi ghi `done` | `test_qa_issues_are_written` |

Mỗi mutation: sửa → chạy → thấy đỏ đúng test đó → phục hồi → `git hash-object` == `git rev-parse HEAD:<path>`.

- [ ] **Step 6: Cả suite**

```bash
cd backend
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python -B -m pytest
```
Kỳ vọng: `548 passed`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/pipeline/translate.py backend/tests/test_translate_handler.py
git commit -m "feat(pipeline): TranslateHandler voi checkpoint, alignment 3 buoc, huy va retry"
```

---

### Task 12: Registry + nối dây vào composition root

**Files:**
- Modify: `backend/app/registry.py`
- Modify: `backend/registry.json`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_mt_wiring.py`

**Interfaces:**
- Consumes: `TranslateHandler`, `OpusMtEngine`, `OllamaMtEngine`, `build_components`, `build_app`
- Produces: `build_components()` trả thêm một phần tử `mt_engines: dict[str, MtEngine]`; `create_app(..., mt_engines=...)`; `registry.json` có `opus-mt` và `qwen2.5-3b` với `available` dò thật

**Đây là task mà Giai đoạn 1a đã trả giá:** `PhaseQueueWorker` được dựng mà **quên** `publish=`, nên SSE trơ suốt. Cùng loại lỗi ở đây là dựng `TranslateHandler` mà **quên** đưa `mt_engines` vào, hoặc quên `governor.register(...)`. Vì vậy: **dựng fixture qua `build_components()` thật**, không chép lại wiring.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_mt_wiring.py
"""Nối dây MT vào composition root, qua chính `build_components()` THẬT.

Không chép lại wiring trong fixture: 1a đã trả giá đúng ở đây khi fixture Task 19
tự dựng lại assembly của main.py rồi TRÔI khỏi nó mà không test nào bắt.
"""
import json

import pytest

from app import main


@pytest.fixture
def wiring(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ensure_dirs", lambda: None)
    monkeypatch.setenv("PHUDE_DATA", str(tmp_path))
    monkeypatch.setenv("PHUDE_DB", str(tmp_path / "app.db"))
    return main.build_components()


def test_build_components_exposes_mt_engines(wiring):
    assert "opus-mt" in wiring.mt_engines
    assert "qwen2.5-3b" in wiring.mt_engines


def test_translate_handler_is_registered_and_handles_translate(wiring):
    assert any(h.handles() == "translate" for h in wiring.handlers)


def test_translate_phase_key_is_translate_colon_engine(wiring):
    """Job dịch lưu `translate:<engine>`, KHÔNG phải `mt:<engine>`."""
    from app.domain.job_state import phase_of
    assert phase_of("translate", "qwen2.5-3b") == "translate:qwen2.5-3b"


def test_every_mt_engine_supports_the_contract(wiring):
    for engine_id, engine in wiring.mt_engines.items():
        assert engine.engine_id
        engine.release()        # phải idempotent, gọi lúc chưa nạp là no-op
        engine.release()
        assert isinstance(engine.supports_glossary(), bool), engine_id


def test_registry_declares_both_engines_with_availability():
    specs = json.loads((main.ROOT / "registry.json").read_text(encoding="utf-8"))
    mt = {e["id"]: e for e in specs["engines"] if e.get("workspace") == 2}
    assert mt["opus-mt"]["available"] in (True, False)
    assert mt["qwen2.5-3b"]["available"] in (True, False)
    assert mt["hy-mt1.5"]["available"] is False, "HY-MT1.5 hoãn thì phải nói là không có"


def test_app_exposes_the_same_engines_object(wiring, tmp_path):
    app = main.build_app(wiring)
    assert app.state.mt_engines is wiring.mt_engines
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_mt_wiring.py
```
Kỳ vọng: FAIL — `AttributeError: 'Components' object has no attribute 'mt_engines'` (hoặc `KeyError`), sau khi bạn đổi `build_components` trả về một object có thuộc tính thay vì tuple.

**Quyết định cần làm ở bước này:** hiện `build_components()` trả **tuple** và có 6 chỗ gọi trong test. Task này đổi nó thành `@dataclass Components` có tên trường. Lý do: tuple 5–6 phần tử đã tới hạn đọc được, và thêm trường thứ bảy vào tuple là mời gán nhầm thứ tự — đúng loại lỗi mà `publish=` đã gây ra. Cập nhật cả 6 chỗ gọi; **không** giữ tương thích tuple.

- [ ] **Step 3: Thêm spec engine vào `registry.json`**

Thêm vào mảng `engines` (giữ nguyên các engine workspace 1 đã có):

```json
{
  "id": "opus-mt", "label": "OPUS-MT (Marian, CPU)", "workspace": 2,
  "backend": "in-process", "vram_mb": 0, "supports_glossary": false,
  "available": true,
  "note": "Dịch từng câu rời, KHÔNG glossary. QA sẽ gắn cờ engine_no_glossary."
},
{
  "id": "qwen2.5-3b", "label": "Qwen2.5-3B (Ollama)", "workspace": 2,
  "backend": "ollama", "model_ref": "qwen2.5:3b", "vram_mb": 2500,
  "supports_glossary": true, "available": false,
  "note": "Chủ lực. Nhận glossary qua system prompt."
},
{
  "id": "hy-mt1.5", "label": "HY-MT1.5-7B (Hunyuan-MT)", "workspace": 2,
  "backend": "ollama", "model_ref": "hy-mt1.5:7b", "vram_mb": 4700,
  "supports_glossary": true, "available": false,
  "note": "HOÃN: GGUF cộng đồng + ollama create. Xem cột 'Ngoài phạm vi' của plan."
}
```

- [ ] **Step 4: `available` của Ollama phải DÒ THẬT, không hardcode**

Trong `backend/app/registry.py` thêm:

```python
def ollama_available(base_url: str = "http://127.0.0.1:11434", timeout: float = 1.5) -> bool:
    """Ollama có sống không. Dò một lần lúc dựng, KHÔNG dò mỗi request."""
    try:
        with httpx.Client(timeout=timeout) as c:
            return c.get(f"{base_url}/api/tags").status_code == 200
    except Exception:
        return False
```

Rồi trong `main.build_components()`, sau khi đọc `registry.json`, đặt `available` của mọi engine `backend == "ollama"` theo `ollama_available()`. **Lý do:** hardcode `true` cho một engine Ollama chưa cài thì job sẽ chết trong worker thay vì bị API từ chối sớm — đúng lỗi I-3 của 1a.

- [ ] **Step 5: Đổi `build_components()` sang dataclass và nối MT**

```python
@dataclass
class Components:
    repos: object
    registry: object
    governor: object
    worker: object
    broker: object
    handlers: list[object]
    mt_engines: dict[str, object]
```

Trong `build_components()`: dựng `mt_engines` gồm `OpusMtEngine()` và (chỉ khi Ollama sống) `OllamaMtEngine(model_ref)`; dựng `TranslateHandler(repos, mt_engines)`; thêm handler đó vào danh sách handler; và **đăng ký releaser cho Ollama** để governor là đầu mối duy nhất:

```python
    for engine_id, engine in mt_engines.items():
        spec = registry.get(engine_id)
        governor.register(phase_of("translate", engine_id), engine.release)
```

- [ ] **Step 6: `build_app` nhận và gắn `mt_engines`**

Thêm tham số `mt_engines` cho `create_app(...)` và gán `app.state.mt_engines = mt_engines`; `build_app(components)` truyền `components.mt_engines`.

- [ ] **Step 7: Cập nhật 6 chỗ gọi `build_components` trong test**

`tests/test_api_sources.py` và `tests/test_e2e_fake.py` đang unpack tuple. Đổi sang truy cập thuộc tính (`wired.repos`, `wired.worker`, …). **Không** thêm shim tương thích.

- [ ] **Step 8: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_mt_wiring.py
```
Kỳ vọng: `6 passed`.

- [ ] **Step 9: Cả suite**

```bash
cd backend
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python -B -m pytest
```
Kỳ vọng: `554 passed`.

- [ ] **Step 10: Mutation — hai dây nối phải đỏ được**

| Mutation | Test phải đỏ |
|---|---|
| Bỏ `TranslateHandler` khỏi danh sách handler | `test_translate_handler_is_registered_and_handles_translate` |
| Bỏ vòng `governor.register(...)` cho engine dịch | `test_every_mt_engine_supports_the_contract` (thêm assert `governor` có phase đó) |
| Hardcode `available: true` cho `hy-mt1.5` | `test_registry_declares_both_engines_with_availability` |

Phục hồi từng cái và verify hash.

- [ ] **Step 11: Commit**

```bash
git add backend/app/registry.py backend/registry.json backend/app/main.py backend/tests/test_mt_wiring.py backend/tests/test_api_sources.py backend/tests/test_e2e_fake.py
git commit -m "feat(main): noi MT vao composition root, doi build_components sang dataclass"
```

---

### Task 13: `api/routes_translations.py` — tạo, liệt kê, sửa tay

**Files:**
- Create: `backend/app/api/routes_translations.py`
- Create: `backend/tests/test_api_translations.py`
- Modify: `backend/app/api/app.py`

**Interfaces:**
- Consumes: `Repos` (qua `Depends(get_repos)`), `TranslateHandler` đã đăng ký, `segments_to_json`
- Produces: `router` với `POST /api/translations` · `GET /api/translations?transcript_id=` · `PATCH /api/translations/{id}`

**Cờ `stale` tính ở server** (spec §8): `stale = transcripts.version > translations.transcript_version`. Client không tự suy.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_api_translations.py
"""API bản dịch: tạo (sinh job), liệt kê kèm cờ stale, sửa tay."""
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.domain.models import Segment


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "ensure_dirs", lambda: None)
    monkeypatch.setenv("PHUDE_DATA", str(tmp_path))
    monkeypatch.setenv("PHUDE_DB", str(tmp_path / "app.db"))
    wired = main.build_components()
    return TestClient(main.build_app(wired)), wired


def _seed(wired) -> tuple[int, int]:
    sid = wired.repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = wired.repos.add_transcript(source_id=sid, engine="fw", lang="zh",
                                     segments=[Segment(i=1, start=0.0, end=1.0, text="你好")])
    tr_id = wired.repos.add_translation(transcript_id=tid, transcript_version=1,
                                        engine="opus-mt",
                                        segments=[Segment(i=1, start=0.0, end=1.0, text="Xin chào")],
                                        prompt_version="opus-p1")
    return tid, tr_id


def test_create_translation_enqueues_a_translate_job(client):
    c, wired = client
    tid, _ = _seed(wired)
    r = c.post("/api/translations", json={"transcript_id": tid, "engine": "opus-mt"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["translation"]["engine"] == "opus-mt"
    job = wired.repos.get_job(body["job"]["id"])
    assert job.type == "translate" and job.phase == "translate:opus-mt"
    assert job.payload["translation_id"] == body["translation"]["id"]


def test_create_translation_rejects_unknown_engine_with_422(client):
    c, wired = client
    tid, _ = _seed(wired)
    r = c.post("/api/translations", json={"transcript_id": tid, "engine": "khong-co"})
    assert r.status_code == 422


def test_create_translation_rejects_unavailable_engine_with_409(client):
    """Ollama không chạy thì từ chối Ở API, không để job chết trong worker."""
    c, wired = client
    tid, _ = _seed(wired)
    if wired.registry.get("qwen2.5-3b").available:
        pytest.skip("Ollama đang chạy trên máy này")
    r = c.post("/api/translations", json={"transcript_id": tid, "engine": "qwen2.5-3b"})
    assert r.status_code == 409


def test_create_translation_rejects_unknown_transcript_with_404(client):
    c, _ = client
    r = c.post("/api/translations", json={"transcript_id": 999, "engine": "opus-mt"})
    assert r.status_code == 404


def test_list_returns_stale_flag_computed_server_side(client):
    c, wired = client
    tid, tr_id = _seed(wired)
    assert c.get(f"/api/translations?transcript_id={tid}").json()[0]["stale"] is False
    wired.repos.update_transcript_segments(tid, [Segment(i=1, start=0.0, end=1.0, text="你好呀")])
    rows = c.get(f"/api/translations?transcript_id={tid}").json()
    assert rows[0]["stale"] is True, "version transcript tăng thì bản dịch cũ là stale"


def test_list_requires_transcript_id(client):
    c, _ = client
    assert c.get("/api/translations").status_code == 422


def test_patch_edits_one_segment_text_and_keeps_timing(client):
    c, wired = client
    _, tr_id = _seed(wired)
    r = c.patch(f"/api/translations/{tr_id}", json={"segments": [
        {"i": 1, "start": 0.0, "end": 1.0, "text": "Xin chào bạn"}]})
    assert r.status_code == 200, r.text
    got = wired.repos.get_translation(tr_id).segments[0]
    assert got.text == "Xin chào bạn" and got.end == 1.0


def test_patch_rejects_segment_ids_that_do_not_exist(client):
    c, wired = client
    _, tr_id = _seed(wired)
    r = c.patch(f"/api/translations/{tr_id}", json={"segments": [
        {"i": 42, "start": 0.0, "end": 1.0, "text": "x"}]})
    assert r.status_code == 422


def test_patch_unknown_translation_is_404(client):
    c, _ = client
    assert c.patch("/api/translations/999", json={"segments": []}).status_code == 404
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_api_translations.py
```
Kỳ vọng: `404` ở mọi request (`ModuleNotFoundError` sau khi tạo file, rồi `404` trước khi gắn router).

- [ ] **Step 3: Viết router**

```python
# backend/app/api/routes_translations.py
"""API Workspace 2: tạo bản dịch, liệt kê kèm cờ stale, sửa tay."""
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_dirs, get_registry, get_repos
from app.domain.job_state import phase_of
from app.domain.models import Job, Segment

router = APIRouter(prefix="/api/translations", tags=["translations"])


class CreateIn(BaseModel):
    transcript_id: int
    engine: str
    target_lang: str = "vi"


class SegmentIn(BaseModel):
    i: int
    start: float
    end: float
    text: str


class PatchIn(BaseModel):
    segments: list[SegmentIn] = Field(default_factory=list)


def _summary(repos, tr, *, stale: bool) -> dict:
    return {"id": tr.id, "transcript_id": tr.transcript_id, "engine": tr.engine,
            "target_lang": tr.target_lang, "prompt_version": tr.prompt_version,
            "transcript_version": tr.transcript_version, "stale": stale,
            "created_at": tr.created_at}


@router.post("", status_code=201)
def create_translation(body: CreateIn, repos=Depends(get_repos),
                       registry=Depends(get_registry)):
    spec = registry.get(body.engine)
    if spec is None or getattr(spec, "workspace", 2) != 2:
        raise HTTPException(422, f"engine không phải engine dịch: {body.engine!r}")
    if not getattr(spec, "available", False):
        # Từ chối Ở ĐÂY, không để job chết trong worker (bài học I-3 của 1a).
        raise HTTPException(409, f"engine chưa sẵn sàng: {body.engine!r}")
    try:
        transcript = repos.get_transcript(body.transcript_id)
    except KeyError as exc:
        raise HTTPException(404, f"không có transcript {body.transcript_id}") from exc

    tr_id = repos.add_translation(
        transcript_id=transcript.id, transcript_version=transcript.version,
        engine=body.engine, segments=[], prompt_version=spec.prompt_version,
        target_lang=body.target_lang, glossary_version=repos.glossary_version(),
        status="queued")
    job = Job(id=None, workspace=2, type="translate", engine=body.engine,
              phase=phase_of("translate", body.engine),
              payload={"translation_id": tr_id, "transcript_id": transcript.id,
                       "engine_id": body.engine, "source_lang": transcript.lang,
                       "target_lang": body.target_lang})
    job.id = repos.add_job(job)
    return {"translation": _summary(repos, repos.get_translation(tr_id), stale=False),
            "job": {"id": job.id, "state": job.state, "phase": job.phase}}


@router.get("")
def list_translations(transcript_id: int, repos=Depends(get_repos)):
    try:
        current = repos.get_transcript(transcript_id).version
    except KeyError as exc:
        raise HTTPException(404, f"không có transcript {transcript_id}") from exc
    return [_summary(repos, repos.get_translation(s.id), stale=current > s.transcript_version)
            for s in repos.list_translations_for_transcript(transcript_id)]


@router.patch("/{translation_id}")
def patch_translation(translation_id: int, body: PatchIn, repos=Depends(get_repos)):
    try:
        tr = repos.get_translation(translation_id)
    except KeyError as exc:
        raise HTTPException(404, f"không có bản dịch {translation_id}") from exc
    known = {s.i for s in tr.segments}
    alien = [s.i for s in body.segments if s.i not in known]
    if alien:
        raise HTTPException(422, f"segment không thuộc bản dịch này: {alien}")
    edited = {s.i: s for s in tr.segments}
    for s in body.segments:
        edited[s.i] = Segment(i=s.i, start=s.start, end=s.end, text=s.text,
                              speaker=edited[s.i].speaker, words=edited[s.i].words)
    repos.update_translation_segments(translation_id, [edited[i] for i in sorted(edited)])
    return _summary(repos, repos.get_translation(translation_id), stale=False)
```

- [ ] **Step 4: Gắn router**

Trong `backend/app/api/app.py`, thêm `from app.api import routes_translations` và `app.include_router(routes_translations.router)` **trước** các router có tham số đường dẫn động khác.

- [ ] **Step 5: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_api_translations.py
```
Kỳ vọng: `8 passed`.

- [ ] **Step 6: Mutation — chứng minh test không rỗng**

Đổi `stale=current > s.transcript_version` thành `stale=False` → `test_list_returns_stale_flag_computed_server_side` phải đỏ. Phục hồi, verify hash.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes_translations.py backend/tests/test_api_translations.py backend/app/api/app.py
git commit -m "feat(api): route translations (tao, liet ke kem co stale, sua tay)"
```

---

### Task 14: `api/routes_glossary.py` — CRUD + "glossary đổi thì bản dịch nào phải xem lại"

> 🔴 **HIỆU CHỈNH BẮT BUỘC CHO TASK NÀY (mục này thắng phần code bên dưới):**
> 1. **KHÔNG gọi `repos.bump_glossary_version()`** trong `create_term`/`patch_term`. Hàm đó **không tồn tại và không
>    được thêm** — `upsert_term` **đã tự tăng** `glossary_version` (`sqlite_repos.py:468-471`). Gọi thêm là **tăng hai
>    lần mỗi lần sửa glossary**, và mọi bản dịch sẽ trông "lỗi thời so với glossary" sớm hơn thực tế.
> 2. **KHÔNG dùng `repos.list_translations()`** để tìm bản dịch bị ảnh hưởng: nó trả `Translation` **đầy đủ**, tức
>    **giải mã JSON của mọi bản dịch trong DB**. Duyệt `repos.list_transcripts()` rồi gọi
>    `repos.list_translations_for_transcript(t.id)` cho từng transcript, và chỉ đụng tới những transcript thật sự bị
>    ảnh hưởng.
> 3. `affected_segments` nay so ánh xạ của **thuật ngữ đã duyệt** ở cả hai phía (ruling T4/F2), nên `_recompute_affected`
>    truyền **danh sách thô** là đúng — đừng lọc trước khi gọi, nếu không ca "bỏ duyệt" sẽ không bao giờ được phát hiện.
> 4. Endpoint `GET /api/glossary/version` **không có trong spec §11** — nó là tiện ích tôi thêm cho test. Giữ nếu thấy
>   rẻ, nhưng **ghi rõ trong báo cáo** rằng nó là phần thêm ngoài spec.
> 5. Brief **không** dự đoán số test nữa; báo cáo số **thật**. Sandbox từ chối ghi `$env:TEMP` — scratch để ngoài repo
>    nhưng trong workspace rồi xoá.

**Files:**
- Create: `backend/app/api/routes_glossary.py`
- Create: `backend/tests/test_api_glossary.py`
- Modify: `backend/app/api/app.py`

**Interfaces:**
- Consumes: `repos.upsert_term`, `list_terms`, `bump_glossary_version`, `affected_segments`, `TranslateHandler`
- Produces: `router` với `GET /api/glossary?lang=` · `POST /api/glossary` · `PATCH /api/glossary/{id}`

Mỗi lần glossary đổi: **bump `glossary_version`**, tính `affected_segments` cho **mọi** bản dịch của ngôn ngữ đó, và sinh job **"Dịch lại · do glossary đổi"** cho những bản dịch có ít nhất một segment ảnh hưởng (spec §8.1).

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_api_glossary.py
"""Glossary: CRUD, tăng version, và sinh job dịch lại cho bản dịch bị ảnh hưởng."""
import pytest
from fastapi.testclient import TestClient

from app.domain.models import Segment


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "ensure_dirs", lambda: None)
    monkeypatch.setenv("PHUDE_DATA", str(tmp_path))
    monkeypatch.setenv("PHUDE_DB", str(tmp_path / "app.db"))
    wired = main.build_components()
    return TestClient(main.build_app(wired)), wired


def test_post_creates_a_term(client):
    c, _ = client
    r = c.post("/api/glossary", json={"lang": "zh", "term": "龙", "translation": "rồng",
                                      "approved": True})
    assert r.status_code == 201 and r.json()["term"] == "龙"


def test_get_filters_by_lang(client):
    c, _ = client
    c.post("/api/glossary", json={"lang": "zh", "term": "龙", "translation": "rồng", "approved": True})
    c.post("/api/glossary", json={"lang": "en", "term": "dragon", "translation": "rồng", "approved": True})
    assert [t["term"] for t in c.get("/api/glossary?lang=zh").json()] == ["龙"]
    assert len(c.get("/api/glossary").json()) == 2


def test_upsert_same_lang_and_term_does_not_duplicate(client):
    c, _ = client
    c.post("/api/glossary", json={"lang": "zh", "term": "龙", "translation": "rồng", "approved": False})
    c.post("/api/glossary", json={"lang": "zh", "term": "龙", "translation": "long", "approved": True})
    rows = c.get("/api/glossary?lang=zh").json()
    assert len(rows) == 1 and rows[0]["translation"] == "long"


def test_patch_edits_translation_and_approval(client):
    c, _ = client
    term_id = c.post("/api/glossary", json={"lang": "zh", "term": "龙",
                                            "translation": "rồng", "approved": False}).json()["id"]
    r = c.patch(f"/api/glossary/{term_id}", json={"approved": True})
    assert r.status_code == 200 and r.json()["approved"] is True


def test_patch_unknown_term_is_404(client):
    c, _ = client
    assert c.patch("/api/glossary/999", json={"approved": True}).status_code == 404


def test_changing_glossary_bumps_version(client):
    c, wired = client
    before = wired.repos.glossary_version()
    c.post("/api/glossary", json={"lang": "zh", "term": "龙", "translation": "rồng", "approved": True})
    assert wired.repos.glossary_version() == before + 1
    assert c.get("/api/glossary/version").json()["glossary_version"] == before + 1


def test_changing_glossary_enqueues_retranslate_for_affected_translation(client):
    c, wired = client
    sid = wired.repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = wired.repos.add_transcript(source_id=sid, engine="fw", lang="zh", segments=[
        Segment(i=1, start=0.0, end=1.0, text="龙"), Segment(i=2, start=1.0, end=2.0, text="mèo")])
    wired.repos.add_translation(transcript_id=tid, transcript_version=1, engine="opus-mt",
                                segments=[], prompt_version="opus-p1", status="done")
    assert wired.repos.list_jobs(states=("queued",)) == []

    r = c.post("/api/glossary", json={"lang": "zh", "term": "龙",
                                      "translation": "rồng", "approved": True})
    assert r.status_code == 201
    affected = r.json()["affected"]
    assert affected == [tid], "chỉ transcript có segment chứa 龙 mới bị ảnh hưởng"
    queued = wired.repos.list_jobs(states=("queued",))
    assert len(queued) == 1 and queued[0].type == "translate"
    assert "glossary" in queued[0].payload["reason"]


def test_a_term_not_present_anywhere_affects_nothing(client):
    c, wired = client
    sid = wired.repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = wired.repos.add_transcript(source_id=sid, engine="fw", lang="zh",
                                     segments=[Segment(i=1, start=0.0, end=1.0, text="mèo")])
    wired.repos.add_translation(transcript_id=tid, transcript_version=1, engine="opus-mt",
                                segments=[], prompt_version="opus-p1", status="done")
    r = c.post("/api/glossary", json={"lang": "zh", "term": "龙",
                                      "translation": "rồng", "approved": True})
    assert r.json()["affected"] == []
    assert wired.repos.list_jobs(states=("queued",)) == []
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_api_glossary.py
```
Kỳ vọng: `404` ở mọi request.

- [ ] **Step 3: Viết router**

```python
# backend/app/api/routes_glossary.py
"""Glossary CRUD + hệ quả: glossary đổi thì biết bản dịch nào phải dịch lại.

`affected` là giá trị chính của tab Thuật ngữ ở frontend: đổi một thuật ngữ mà
không biết bản dịch nào phải xem lại thì glossary chỉ là một cuốn từ điển rời.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_repos
from app.domain.glossary_match import affected_segments
from app.domain.job_state import phase_of
from app.domain.models import Job, Term

router = APIRouter(prefix="/api/glossary", tags=["glossary"])


class TermIn(BaseModel):
    lang: str
    term: str
    translation: str
    note: str | None = None
    approved: bool = False


class TermPatch(BaseModel):
    translation: str | None = None
    note: str | None = None
    approved: bool | None = None


def _json(t: Term) -> dict:
    return {"id": t.id, "lang": t.lang, "term": t.term, "translation": t.translation,
            "note": t.note, "approved": t.approved, "created_at": t.created_at}


def _old_glossary_of(repos, lang: str, term_text: str) -> list[Term]:
    return [t for t in repos.list_terms(lang=lang) if t.term != term_text]


def _enqueue_retranslate(repos, *, affected: list[int], lang: str) -> list[int]:
    """Sinh job 'Dịch lại · do glossary đổi' cho MỌI bản dịch đã xong bị ảnh hưởng."""
    job_ids: list[int] = []
    for summary in repos.list_translations():
        if summary.transcript_id not in affected:
            continue
        job = Job(id=None, workspace=2, type="translate", engine=summary.engine,
                  phase=phase_of("translate", summary.engine),
                  payload={"translation_id": summary.id,
                           "transcript_id": summary.transcript_id,
                           "engine_id": summary.engine, "source_lang": lang,
                           "target_lang": summary.target_lang,
                           "reason": "glossary đổi"})
        job_ids.append(repos.add_job(job))
    return job_ids


def _recompute_affected(repos, lang: str, term_text: str) -> list[int]:
    old = _old_glossary_of(repos, lang, term_text)
    new = repos.list_terms(lang=lang)
    out: list[int] = []
    for t in repos.list_transcripts():
        if t.lang != lang:
            continue
        if affected_segments(t.segments, old, new):
            out.append(t.id)
    return out


@router.get("")
def list_glossary(lang: str | None = None, repos=Depends(get_repos)):
    return [_json(t) for t in repos.list_terms(lang=lang)]


@router.get("/version")
def get_version(repos=Depends(get_repos)):
    return {"glossary_version": repos.glossary_version()}


@router.post("", status_code=201)
def create_term(body: TermIn, repos=Depends(get_repos)):
    term_id = repos.upsert_term(lang=body.lang, term=body.term,
                                translation=body.translation, note=body.note,
                                approved=body.approved)
    repos.bump_glossary_version()
    affected = _recompute_affected(repos, body.lang, body.term)
    _enqueue_retranslate(repos, affected=affected, lang=body.lang)
    out = _json([t for t in repos.list_terms(lang=body.lang) if t.id == term_id][0])
    out["affected"] = affected
    return out


@router.patch("/{term_id}")
def patch_term(term_id: int, body: TermPatch, repos=Depends(get_repos)):
    existing = [t for t in repos.list_terms() if t.id == term_id]
    if not existing:
        raise HTTPException(404, f"không có thuật ngữ {term_id}")
    t = existing[0]
    repos.upsert_term(lang=t.lang, term=t.term,
                      translation=body.translation if body.translation is not None else t.translation,
                      note=body.note if body.note is not None else t.note,
                      approved=body.approved if body.approved is not None else t.approved)
    repos.bump_glossary_version()
    affected = _recompute_affected(repos, t.lang, t.term)
    _enqueue_retranslate(repos, affected=affected, lang=t.lang)
    out = _json([x for x in repos.list_terms(lang=t.lang) if x.id == term_id][0])
    out["affected"] = affected
    return out
```

- [ ] **Step 4: Gắn router** vào `backend/app/api/app.py`.

- [ ] **Step 5: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_api_glossary.py
```
Kỳ vọng: `8 passed`.

- [ ] **Step 6: Mutation — chứng minh test không rỗng**

| Mutation | Test phải đỏ |
|---|---|
| Bỏ `repos.bump_glossary_version()` trong `create_term` | `test_changing_glossary_bumps_version` |
| `_enqueue_retranslate` trả `[]` ngay đầu hàm | `test_changing_glossary_enqueues_retranslate_for_affected_translation` |
| `affected` luôn là mọi transcript | `test_a_term_not_present_anywhere_affects_nothing` |

Phục hồi từng cái và verify hash.

- [ ] **Step 7: Cả suite**

```bash
cd backend
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python -B -m pytest
```
Kỳ vọng: `568 passed`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/routes_glossary.py backend/tests/test_api_glossary.py backend/app/api/app.py
git commit -m "feat(api): glossary CRUD + job dich lai khi glossary doi"
```

---

### Task 15: Duyệt transcript + route export đúng hình dạng spec

**Files:**
- Modify: `backend/app/api/routes_translations.py`
- Create: `backend/tests/test_api_export_by_translation.py`

**Interfaces:**
- Consumes: `app.pipeline.export` (`artifact_name()`, handler export hiện có), `routes_export` cũ (`POST /api/export` + `GET /api/export/{job_id}/download`)
- Produces: `POST /api/transcripts/{id}/approve` · `GET /api/export/{translation_id}?format=&bilingual=`

**Quyết định đã chốt (spec §7):** thêm route **đúng spec** và **giữ** route cũ; ghim bằng test rằng hai đường cho **cùng nội dung** cho cùng một bản dịch. Bỏ route cũ là phá thứ đang chạy mà không có gì bù.

- [ ] **Step 1: Viết test đỏ**

```python
# backend/tests/test_api_export_by_translation.py
"""Duyệt transcript và route export hình dạng spec, CÙNG NỘI DUNG với route cũ.

Spec §11 ghi `GET /api/export/{translation_id}?format=&bilingual=`, còn 1a đã ship
`POST /api/export` + `GET /api/export/{job_id}/download`. Hai đường phải không trôi
khỏi nhau — cùng `artifact_name()` nên cùng tên tệp, và test này ghim điều đó.
"""
import pytest
from fastapi.testclient import TestClient

from app.domain.models import Segment


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "ensure_dirs", lambda: None)
    monkeypatch.setenv("PHUDE_DATA", str(tmp_path))
    monkeypatch.setenv("PHUDE_DB", str(tmp_path / "app.db"))
    wired = main.build_components()
    return TestClient(main.build_app(wired)), wired


def _ready(wired) -> tuple[int, int]:
    sid = wired.repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    tid = wired.repos.add_transcript(source_id=sid, engine="fw", lang="zh", segments=[
        Segment(i=1, start=0.0, end=1.0, text="你好"),
        Segment(i=2, start=1.0, end=2.0, text="再见")])
    tr_id = wired.repos.add_translation(
        transcript_id=tid, transcript_version=1, engine="opus-mt", prompt_version="opus-p1",
        segments=[Segment(i=1, start=0.0, end=1.0, text="Xin chào"),
                  Segment(i=2, start=1.0, end=2.0, text="Tạm biệt")],
        status="done")
    return tid, tr_id


def test_approve_moves_transcript_to_workspace_2(client):
    c, wired = client
    tid, _ = _ready(wired)
    r = c.post(f"/api/transcripts/{tid}/approve")
    assert r.status_code == 200 and r.json()["status"] == "translated"
    assert wired.repos.get_transcript(tid).status == "translated"


def test_approve_unknown_transcript_is_404(client):
    c, _ = client
    assert c.post("/api/transcripts/999/approve").status_code == 404


def test_export_by_translation_returns_srt(client):
    c, wired = client
    _, tr_id = _ready(wired)
    r = c.get(f"/api/export/{tr_id}?format=srt")
    assert r.status_code == 200, r.text
    assert "-->" in r.text
    assert "Xin chào" in r.text and "Tạm biệt" in r.text


def test_export_bilingual_contains_source_and_translation(client):
    c, wired = client
    _, tr_id = _ready(wired)
    r = c.get(f"/api/export/{tr_id}?format=srt&bilingual=1")
    assert "你好" in r.text and "Xin chào" in r.text


def test_export_rejects_bad_format_with_422(client):
    c, wired = client
    _, tr_id = _ready(wired)
    assert c.get(f"/api/export/{tr_id}?format=pdf").status_code == 422


def test_export_unknown_translation_is_404(client):
    c, _ = client
    assert c.get("/api/export/999?format=srt").status_code == 404


def test_both_export_routes_produce_the_same_bytes(client):
    """Route cũ và route spec phải cho CÙNG nội dung — chúng dùng chung artifact_name()."""
    c, wired = client
    _, tr_id = _ready(wired)
    spec_route = c.get(f"/api/export/{tr_id}?format=srt").text

    created = c.post("/api/export", json={"translation_id": tr_id, "format": "srt"})
    assert created.status_code in (200, 201), created.text
    job_id = created.json()["job"]["id"]
    for _ in range(50):                      # worker chạy nền; chờ ngắn, có trần
        job = wired.repos.get_job(job_id)
        if job.state in ("done", "failed"):
            break
        wired.worker.tick()
    assert wired.repos.get_job(job_id).state == "done"
    old_route = c.get(f"/api/export/{job_id}/download").text
    assert spec_route == old_route
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ**

```bash
cd backend
python -B -m pytest tests/test_api_export_by_translation.py
```
Kỳ vọng: `404` ở các test route mới.

- [ ] **Step 3: Viết hai route**

Thêm vào `backend/app/api/routes_translations.py`:

```python
@router.post("/api/transcripts/{transcript_id}/approve", tags=["transcripts"])
def approve_transcript(transcript_id: int, repos=Depends(get_repos)):
    try:
        repos.get_transcript(transcript_id)
    except KeyError as exc:
        raise HTTPException(404, f"không có transcript {transcript_id}") from exc
    repos.set_transcript_status(transcript_id, "translated")
    return {"id": transcript_id, "status": "translated"}


@router.get("/api/export/{translation_id}", tags=["export"])
def export_translation(translation_id: int, format: str = "srt", bilingual: int = 0,
                       repos=Depends(get_repos), dirs=Depends(get_dirs)):
    """Hình dạng spec §11. Dùng CHUNG `artifact_name()` với route cũ nên hai đường
    không thể trôi khỏi nhau."""
    from app.domain.subtitle_format import FORMATS
    from app.pipeline.export import artifact_name, render

    if format not in FORMATS:
        raise HTTPException(422, f"định dạng không hỗ trợ: {format!r}")
    try:
        tr = repos.get_translation(translation_id)
    except KeyError as exc:
        raise HTTPException(404, f"không có bản dịch {translation_id}") from exc
    source = repos.get_transcript(tr.transcript_id).segments
    body = render(tr.segments, fmt=format, source=source, bilingual=bool(bilingual))
    name = artifact_name(tr, fmt=format, bilingual=bool(bilingual))
    pathlib.Path(dirs["output"]).mkdir(parents=True, exist_ok=True)
    (pathlib.Path(dirs["output"]) / name).write_text(body, encoding="utf-8")
    return PlainTextResponse(body, media_type=MEDIA_TYPES[format])
```

Dùng đúng tên hàm/thuộc tính mà `backend/app/pipeline/export.py` và
`backend/app/domain/subtitle_format.py` **thực có** — đọc hai tệp đó trước khi viết, và nếu tên khác thì dùng tên thật (đừng đổi tên hàm đang chạy để vừa plan).

- [ ] **Step 4: Chạy test để chắc chắn nó XANH**

```bash
cd backend
python -B -m pytest tests/test_api_export_by_translation.py
```
Kỳ vọng: `7 passed`.

- [ ] **Step 5: Mutation — chứng minh test không rỗng**

Đổi `bilingual=bool(bilingual)` thành `bilingual=False` → `test_export_bilingual_contains_source_and_translation` phải đỏ. Đổi `if format not in FORMATS` thành `if False` → `test_export_rejects_bad_format_with_422` phải đỏ. Phục hồi cả hai, verify hash.

- [ ] **Step 6: Cả suite + commit**

```bash
cd backend
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python -B -m pytest
```
Kỳ vọng: `575 passed`.

```bash
git add backend/app/api/routes_translations.py backend/tests/test_api_export_by_translation.py
git commit -m "feat(api): duyet transcript + route export theo hinh dang spec"
```

---

### Task 16: Cài Ollama, ĐO `keep_alive`, và chạy thật cả hai engine

**Đây là task quyết định Giai đoạn 2 có thật hay chỉ xanh test.** Giai đoạn 1a đã trả giá: 19 task xanh mà đường ASR chết ở hai chỗ không test nào chạm, vì **chưa từng ai chạy nó**.

**Files:**
- Create: `backend/scripts/download_mt_models.py`
- Create: `backend/scripts/smoke_mt.py`
- Create: `backend/tests/test_mt_live.py`
- Modify: `backend/scripts/install.ps1`
- Modify: `README.md`

**Interfaces:**
- Produces: `smoke_mt.py <wav|video> <source_lang> <engine_id>` in ra **số** và **exit code** phản ánh kết quả thật

- [ ] **Step 1: Cài Ollama và kéo model**

```powershell
winget install --id Ollama.Ollama -e
ollama --version
ollama pull qwen2.5:3b
ollama list
```
Nếu `winget` hỏng hoặc mạng chặn: **dừng và báo thẳng**, không thay bằng test giả.

- [ ] **Step 2: ĐO `keep_alive` bằng `ollama ps` — đây là điều spec §5 để ngỏ**

```powershell
ollama ps                                 # trước khi gọi: model nào đang nạp?
# gọi một lần /api/chat với keep_alive "30m", rồi:
ollama ps                                 # model còn nằm trong VRAM không?
# gọi /api/chat với keep_alive 0, rồi:
ollama ps                                 # đã đổ chưa?
```

Ghi **nguyên văn** cả ba lần `ollama ps` vào báo cáo. Nếu `keep_alive: 0` **không** đổ model, thì `OllamaMtEngine.release()` phải đổi cách (ví dụ gọi `POST /api/generate` với `keep_alive: 0`), và **plan này sửa theo số đo** — không giữ code theo giả định.

- [ ] **Step 3: Viết script tải model OPUS-MT trước**

```python
# backend/scripts/download_mt_models.py
"""Tải trước model OPUS-MT để lần chạy thật đầu tiên không phải chờ mạng.

`HF_HOME` phải trỏ ổ còn chỗ: ổ C: của máy này chỉ còn ~26 GB, còn D: ~59 GB.
Đường mặc định `D:\models\hf` của dự án CHƯA TỪNG được đi qua ở Giai đoạn 1a.
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.adapters.mt.opus_mt import DEFAULT_MODEL


def main() -> int:
    root = os.environ.get("HF_HOME")
    print(f"HF_HOME = {root!r}")
    if not root:
        print("CẢNH BÁO: chưa đặt HF_HOME — model sẽ vào cache mặc định trên ổ C:")
    from transformers import MarianMTModel, MarianTokenizer
    MarianTokenizer.from_pretrained(DEFAULT_MODEL)
    MarianMTModel.from_pretrained(DEFAULT_MODEL)
    print(f"OK: đã tải {DEFAULT_MODEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Viết smoke test IN RA SỐ**

```python
# backend/scripts/smoke_mt.py
"""Chạy THẬT một lần dịch và in ra số. Không có số nghĩa là chưa xong.

Dùng: python -B scripts/smoke_mt.py <media> <source_lang> <engine_id> [target_lang]
Thoát khác 0 nếu không dịch được segment nào — 'xanh với 0 segment' là báo cáo sai.
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.adapters.mt.opus_mt import OpusMtEngine          # noqa: E402
from app.domain.models import Segment                      # noqa: E402
from app.domain.mt import MtOpts                           # noqa: E402


def build_engine(engine_id: str):
    if engine_id == "opus-mt":
        return OpusMtEngine()
    if engine_id.startswith("qwen"):
        from app.adapters.mt.ollama_mt import OllamaMtEngine
        return OllamaMtEngine(model="qwen2.5:3b")
    raise SystemExit(f"engine chưa hỗ trợ trong smoke: {engine_id!r}")


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    media, source_lang, engine_id = argv[1], argv[2], argv[3]
    target_lang = argv[4] if len(argv) > 4 else "vi"

    # Bóc băng bằng đường ỐNG THẬT của sản phẩm, không tự viết lại.
    from app.adapters.asr.factory import build_asr_engine
    asr = build_asr_engine("fw-tiny")
    t0 = time.perf_counter()
    segments = asr.transcribe(media, lang=source_lang)
    print(f"[1/3] bóc băng: {len(segments)} segment trong {time.perf_counter() - t0:.1f}s")
    if not segments:
        print("THẤT BẠI: không có segment nào để dịch")
        return 1

    sample = segments[:20]
    engine = build_engine(engine_id)
    t0 = time.perf_counter()
    out = engine.translate(sample, [], MtOpts(source_lang=source_lang,
                                              target_lang=target_lang))
    elapsed = time.perf_counter() - t0

    print(f"[2/3] dịch {len(sample)} segment bằng {engine_id} trong {elapsed:.1f}s")
    if len(out) != len(sample):
        print(f"THẤT BẠI: alignment sai — vào {len(sample)}, ra {len(out)}")
        return 1
    stats = getattr(engine, "last_stats", None)
    print(f"      tokens_in={getattr(stats, 'tokens_in', None)} "
          f"tokens_out={getattr(stats, 'tokens_out', None)}")
    for s, t in list(zip(sample, out))[:5]:
        print(f"      {s.i:>4}  {s.text[:40]!r} -> {t.text[:40]!r}")

    print(f"[3/3] OK — {len(out)}/{len(sample)} segment, {elapsed:.1f}s, "
          f"engine={engine_id}, glossary={engine.supports_glossary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 5: Chạy thật cả hai engine và ghi số**

```bash
cd backend
$env:HF_HOME = "D:\models\hf"
.\.venv\Scripts\python.exe -B scripts/download_mt_models.py
.\.venv\Scripts\python.exe -B scripts/smoke_mt.py "$env:TEMP\synth-zh.wav" zh opus-mt
.\.venv\Scripts\python.exe -B scripts/smoke_mt.py "$env:TEMP\synth-zh.wav" zh qwen2.5-3b
```
Dán **nguyên văn** cả hai lần chạy vào báo cáo. Kỳ vọng: OPUS-MT trả đủ segment (chất lượng có thể kém — đó là lý do Qwen là chủ lực); Qwen trả đủ segment và có `tokens_in/out`.

**Nếu Qwen không trả đủ segment ở 20 mục:** ghi lại tỉ lệ hỏng, giảm `DEFAULT_BATCH_CHARS` trong `app/domain/mt.py` theo số đo, và ghi con số mới vào báo cáo. Đây chính là lý do spec §12 để ngỏ kích thước lô.

- [ ] **Step 6: Test live có marker (không làm đỏ máy khác)**

```python
# backend/tests/test_mt_live.py
"""Test CHẠM model thật. Mặc định BỊ BỎ QUA để máy khác không đỏ oan.

Chạy: python -B -m pytest -m live
"""
import pytest

from app.adapters.mt.opus_mt import OpusMtEngine
from app.domain.models import Segment
from app.domain.mt import MtOpts

pytestmark = pytest.mark.live


def test_opus_mt_translates_real_text_zh_to_vi():
    eng = OpusMtEngine()
    out = eng.translate([Segment(i=1, start=0.0, end=1.0, text="你好")], [],
                        MtOpts(source_lang="zh", target_lang="vi"))
    assert len(out) == 1 and out[0].text.strip(), "model thật phải trả chữ, không rỗng"


def test_release_then_reload_works():
    eng = OpusMtEngine()
    eng.release()
    eng.release()
    out = eng.translate([Segment(i=1, start=0.0, end=1.0, text="再见")], [],
                        MtOpts(source_lang="zh", target_lang="vi"))
    assert out[0].text.strip()
```

Đăng ký marker trong `backend/pytest.ini`:

```ini
markers =
    live: chạm model thật; mặc định bỏ qua (dùng -m live để chạy)
```

Và thêm `addopts = -q -m "not live"` — nhưng **giữ đúng một** `-q`.

- [ ] **Step 7: Chạy test live và cả suite**

```bash
cd backend
python -B -m pytest -m live
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python -B -m pytest
```
Kỳ vọng: `2 passed` cho lần đầu; suite mặc định `575 passed` (bỏ qua 2 test live).

- [ ] **Step 8: Commit**

```bash
git add backend/scripts/download_mt_models.py backend/scripts/smoke_mt.py backend/tests/test_mt_live.py backend/pytest.ini README.md
git commit -m "feat(mt): cai Ollama, do keep_alive, smoke test co so, test live co marker"
```

---

### Task 17: Nghiệm thu đầu-cuối + tài liệu

**Files:**
- Create: `backend/tests/test_e2e_translate.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: toàn bộ API đã dựng
- Produces: một test đầu-cuối chạy qua `build_components()` thật

- [ ] **Step 1: Viết test đầu-cuối (engine giả, chạy ở mọi máy)**

```python
# backend/tests/test_e2e_translate.py
"""Đầu-cuối Workspace 2 với engine GIẢ: duyệt transcript -> tạo bản dịch ->
worker dịch -> QA -> export. Dựng qua `build_components()` THẬT.

Bài học Task 19 của 1a: fixture tự chép lại wiring của main.py thì nó TRÔI mà
không test nào bắt. Nên ở đây thay engine thật bằng engine giả SAU khi đã dựng
xong, chứ không dựng lại assembly.
"""
import pytest
from fastapi.testclient import TestClient

from app.domain.models import Segment
from tests.fakes_mt import FakeMtEngine


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "ensure_dirs", lambda: None)
    monkeypatch.setenv("PHUDE_DATA", str(tmp_path))
    monkeypatch.setenv("PHUDE_DB", str(tmp_path / "app.db"))
    wired = main.build_components()
    wired.mt_engines["opus-mt"] = FakeMtEngine(mapping={"你好": "Xin chào"})
    return TestClient(main.build_app(wired)), wired


def _transcript(wired) -> int:
    sid = wired.repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    return wired.repos.add_transcript(source_id=sid, engine="fw", lang="zh", segments=[
        Segment(i=1, start=0.0, end=1.0, text="你好"),
        Segment(i=2, start=1.0, end=2.0, text="再见")])


def test_full_workspace_2_flow(client):
    c, wired = client
    tid = _transcript(wired)
    assert c.post(f"/api/transcripts/{tid}/approve").status_code == 200

    created = c.post("/api/translations", json={"transcript_id": tid, "engine": "opus-mt"})
    assert created.status_code == 201, created.text
    tr_id = created.json()["translation"]["id"]
    job_id = created.json()["job"]["id"]

    for _ in range(50):
        if wired.repos.get_job(job_id).state in ("done", "failed"):
            break
        wired.worker.tick()

    assert wired.repos.get_job(job_id).state == "done", wired.repos.get_job(job_id).error
    tr = wired.repos.get_translation(tr_id)
    assert tr.status == "done"
    assert [s.i for s in tr.segments] == [1, 2]
    assert tr.segments[0].text == "Xin chào"
    assert tr.qa_issues == [] or isinstance(tr.qa_issues, list)

    exported = c.get(f"/api/export/{tr_id}?format=srt")
    assert exported.status_code == 200 and "Xin chào" in exported.text
```

- [ ] **Step 2: Chạy test để chắc chắn nó ĐỎ rồi XANH**

```bash
cd backend
python -B -m pytest tests/test_e2e_translate.py
```
Kỳ vọng lượt đầu: đỏ ở `assert ... == "done"` (handler chưa nối đúng payload) hoặc xanh ngay nếu các task trước đã đúng — **nếu xanh ngay, ghi rõ trong báo cáo là không có RED**, và chứng minh không rỗng bằng mutation ở Step 3.

- [ ] **Step 3: Mutation — chứng minh test không rỗng**

Đổi `job.payload` trong `routes_translations.create_translation` bỏ `"translation_id"` → test phải đỏ. Phục hồi, verify hash.

- [ ] **Step 4: Cập nhật README**

Thêm mục "Giai đoạn 2 — Workspace 2" gồm: cách cài (`transformers`, Ollama, `ollama pull qwen2.5:3b`) · cách chạy (`python -B scripts/smoke_mt.py ...`) · cách chạy test live (`python -B -m pytest -m live`) · và **câu nói thẳng** rằng HY-MT1.5 + Chimera chưa làm, frontend chưa làm.

- [ ] **Step 5: Cả suite và commit**

```bash
cd backend
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
python -B -m pytest
```
Kỳ vọng: `576 passed`.

```bash
git add backend/tests/test_e2e_translate.py README.md
git commit -m "test(e2e): nghiem thu dau-cuoi workspace 2 + tai lieu"
```

---

## Spec coverage — đối chiếu từng mục của spec với task

| Mục spec | Task |
|---|---|
| §2 kiến trúc `domain/ports/adapters/pipeline/api` | T2–T7 (domain/ports), T8–T10 (adapters), T11 (pipeline), T13–T15 (api) |
| §2.1 `mt.py` chia lô | **T2** |
| §2.1 `alignment.py` | **T3** |
| §2.1 `glossary_match.py` | **T4** |
| §2.1 `mt_qa.py` | **T5** |
| §2.2 `MtEngine` + `Repos` mở rộng | **T6**, **T7** |
| §2.3 `prompts.py` · `opus_mt.py` · `ollama_mt.py` | **T8**, **T9**, **T10** |
| §3 luồng một lần dịch + checkpoint + hủy + retry | **T11** |
| §4.1 prompt theo engine + cờ OPUS-MT không glossary | **T8**, **T5**, **T10** |
| §4.2 chính sách alignment ba bước | **T11** |
| §5 VRAM/Ollama `keep_alive` + releaser + fail sớm | **T10**, **T12**, **T16** |
| §6 migration v1→v2 + `translations.status` | **T1** |
| §7 API (translations, glossary, approve, export hình dạng spec) | **T13**, **T14**, **T15** |
| §8 QA tất định + cờ `stale` | **T5**, **T13** |
| §8.1 glossary đổi ⇒ ảnh hưởng + job dịch lại + `glossary_version` | **T4**, **T6**, **T14** |
| §9 cách test (engine giả, live có marker, mutation, không tạo `data/`) | mọi task; **T16**, **T17** |
| §10 rủi ro (Ollama chưa cài, `keep_alive` chưa đo, ổ C: ít chỗ) | **T16** (đo), **T12** (fail sớm) |
| §11 tiêu chí nghiệm thu 1–10 | **T16** (1), **T17** (2), **T11** (3,4), **T14** (5), **T5** (6), **T1** (7), **T15** (8), mọi task (9,10) |

## Những gì plan này KHÔNG làm (hoãn có chủ ý)

HY-MT1.5 · chế độ Chimera · toàn bộ frontend · glossary tự đề xuất bằng LLM · dịch sang đích ngôn ngữ khác `vi` ·
bỏ route export cũ.

