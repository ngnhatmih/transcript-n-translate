SCHEMA_VERSION = 4

SCHEMA_SQL = """
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
  -- Vùng đọc OCR của CHÍNH nguồn này, dạng JSON `[x0, y0, x1, y1]` theo tỉ lệ
  -- khung (0..1). NULL = chưa ai chọn, dùng `opts.vung_doc` của registry.
  -- `'[]'` = người dùng đã TẮT lọc vùng (nút ×) — khác hẳn NULL, xem
  -- `_vung_doc_tu_payload` trong `pipeline/transcribe.py`.
  --
  -- Vì sao lưu ở ĐÂY chứ không chỉ trong payload job: vùng watermark thuộc về
  -- VIDEO. Đo được `8f4b5304daf42569.mp4` (1080×1920) có watermark ở `y=35-102`,
  -- còn `ac5df767b9e0c878.mp4` (1280×720) ở chỗ khác. Người dùng kéo khung MỘT
  -- lần cho mỗi video; bắt họ kéo lại sau mỗi lần mở trang là dùng dữ liệu đã
  -- mất. Payload job vẫn giữ bản sao của lượt chạy đó (để biết job nào dùng vùng
  -- nào), nhưng nguồn mới là chỗ NHỚ.
  vung_doc TEXT,
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
  -- Chế độ CHIMERA (§8.7.5): một JSON gồm kế hoạch (N ứng viên + lượt pha), ước
  -- lượng chi phí ĐÃ GHI LÚC TẠO HÀNG (trước khi người dùng bấm), và số đo THẬT
  -- của từng ứng viên. NULL = hàng này không chạy ở chế độ Chimera.
  chimera TEXT,
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
-- Handler dịch gom token/thời gian của MỘT job bằng `WHERE job_id = ?`; không
-- index thì mỗi bản dịch quét cả bảng `llm_calls`, mà bảng đó dài thêm một hàng
-- mỗi lần gọi engine. Index là ĐỐI TƯỢNG MỚI (không phải cột), nên câu lệnh này
-- tự chạy trên DB đã tồn tại — KHÔNG cần migration và `SCHEMA_VERSION` giữ
-- nguyên.
CREATE INDEX IF NOT EXISTS idx_llm_calls_job ON llm_calls(job_id);

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
