SCHEMA_VERSION = 1

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
