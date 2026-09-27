/**
 * Kiểu dữ liệu của tầng API — VIẾT TAY theo JSON THẬT của backend.
 *
 * Nguồn của từng khoá (đọc mã, KHÔNG đoán từ tên dataclass):
 *   - `backend/app/domain/models.py`  — `Segment.to_json`, `Job.to_event`
 *   - `backend/app/domain/staleness.py` — `translation_summary_json` (MỘT builder
 *     cho cả `/api/translations` lẫn `translations[]` của `/api/transcripts`)
 *   - `backend/app/api/routes_*.py`   — các `_*_json` mà route thật sự trả
 *   - `backend/app/api/routes_registry.py` — `/api/registry` (khoá theo `kind`) và `/api/status`
 *
 * Vì sao viết tay thay vì sinh từ `/openapi.json`: spec §2 chốt rằng thứ nhỏ nhất
 * sập khi shape trôi là một contract test, và nó sập ỒN ÀO. Xem
 * `contract.test.ts` — mọi khoá dưới đây có bài kiểm trên backend thật.
 */

/** Một từ có mốc thời gian. Chỉ có khi engine thật sự sinh word timestamp. */
export interface Word {
  w: string;
  s: number;
  e: number;
}

/**
 * Một đoạn phụ đề (`models.py::Segment.to_json`).
 *
 * BẤT BIẾN của backend: khoá tuỳ chọn CHỈ xuất hiện khi engine thật sự sinh ra
 * nó — backend cố ý KHÔNG bịa `words: []` cho engine không có word timestamp
 * (docstring đầu `models.py`). Nên ở đây chúng là optional, và giao diện phải
 * phân biệt "không có" với "rỗng".
 */
export interface Segment {
  i: number;
  start: number;
  end: number;
  text: string;
  /** LUÔN có (kể cả `false`) — `to_json` ghi nó vô điều kiện. */
  suspect: boolean;
  words?: Word[];
  emotion?: string;
  events?: string[];
  speaker?: string;
  avg_logprob?: number;
  no_speech_prob?: number;
  /** Bản dịch tay của người dùng cho đoạn này, nếu có. */
  t?: string;
  qa?: string[];
}

/** Thứ tự dài của một hàng `jobs` (`routes_jobs._job_json`). */
export type JobType = "ingest" | "asr" | "translate" | "export";
export type JobState = "queued" | "running" | "done" | "failed" | "interrupted" | "cancelled";

export interface Job {
  id: number;
  workspace: number;
  type: JobType;
  engine: string | null;
  phase: string;
  state: JobState;
  cancel_requested: boolean;
  attempts: number;
  progress: number;
  log_tail: string;
  error: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

/**
 * Hình dạng job RÚT GỌN mà `routes_sources._job_json` trả trong body của
 * `POST /api/sources/upload` và `POST /api/sources/url`.
 *
 * Đây KHÔNG phải `Job` thiếu vài trường vì lười: đó là một hàm khác, ở một tệp
 * khác, và nó cố ý chỉ trả sáu khoá. Client đọc `payload`/`progress` từ response
 * upload sẽ nhận `undefined` — nên kiểu phải nói ra, không để `Job` che mất.
 */
export type JobSlim = Pick<Job, "id" | "workspace" | "type" | "engine" | "phase" | "state">;

/**
 * Sự kiện SSE của `/api/jobs/stream` — ĐÚNG `Job.to_event()` (`models.py`).
 *
 * MỘT nguồn cho cả `worker._emit` lẫn ảnh chụp đầu stream; lệch khoá là sự kiện
 * vừa bị gửi trùng vừa bị bỏ sót (docstring `to_event`).
 */
export interface JobEvent {
  id: number | null;
  state: JobState;
  progress: number;
  phase: string;
  error: string | null;
  log_tail: string;
}

/** `routes_sources.ALLOWED_LANGS` — hai ngôn ngữ nguồn backend nhận. */
export type SourceLang = "zh" | "en";
export type SourceKind = "file" | "url";

/** Một hàng `sources` (`routes_sources._source_json`). */
export interface Source {
  id: number;
  kind: SourceKind;
  origin: string;
  media_path: string;
  audio_path: string | null;
  duration: number | null;
  lang: SourceLang | null;
  created_at: string;
}

export type TranscriptStatus = "draft" | "reviewed" | "translated";
export type TranslationStatus = "queued" | "running" | "done" | "failed" | "cancelled";

/**
 * Một hàng bản dịch ĐÃ TÓM TẮT — `domain/staleness.py::translation_summary_json`.
 *
 * Khoá ở đây là `transcript_version`, KHÔNG phải `translated_from_version`
 * (Giai đoạn 2 đổi tên; hai endpoint từng phát hai hình dạng khác nhau và bài
 * `test_the_two_endpoints_describe_a_translation_identically` ghim chúng bằng nhau).
 * `status` và `id` là thứ phân biệt một job vừa xếp với một bản dịch đã xong.
 *
 * `segments` KHÔNG có ở tầng HTTP: builder cố ý bỏ nó (kéo theo là giải mã JSON
 * của cả một bản dịch cho mỗi hàng trong danh sách). Muốn có đoạn dịch thì đọc
 * `GET /api/transcripts/{id}`… cũng không có: `Transcript.segments` là đoạn GỐC.
 */
export interface Translation {
  id: number;
  transcript_id: number;
  engine: string;
  target_lang: string;
  prompt_version: string;
  transcript_version: number;
  status: TranslationStatus;
  /** TÍNH Ở SERVER mỗi lần đọc (`is_stale`), không lưu cột — client không tự suy. */
  stale: boolean;
  created_at: string;
}

/**
 * Transcript KHÔNG kèm `segments` — hình dạng của `GET /api/transcripts`
 * (route danh sách cố ý không kéo đoạn nào) và của `POST /api/transcripts/{id}/approve`.
 */
export interface TranscriptSummary {
  id: number;
  source_id: number;
  engine: string;
  lang: string;
  version: number;
  status: TranscriptStatus;
  created_at: string;
  /** Mọi bản dịch của transcript này, dạng tóm tắt — xem `Translation`. */
  translations: Translation[];
}

/** Transcript ĐẦY ĐỦ của `GET /api/transcripts/{id}` và `PATCH /api/transcripts/{id}`. */
export interface Transcript extends TranscriptSummary {
  segments: Segment[];
}

/** `PATCH /api/transcripts/{id}` (`routes_transcripts.PatchIn`). */
export interface TranscriptPatch {
  /** Backend từ chối mảng rỗng (`min_length=1`): không đoạn nào là dữ liệu hỏng. */
  segments: Segment[];
  status?: TranscriptStatus;
}

/** `PATCH /api/translations/{id}` (`routes_translations.SegmentIn` + `PatchIn`). */
export interface TranslationSegmentPatch {
  i: number;
  start: number;
  end: number;
  text: string;
}

/** `POST /api/translations` (`routes_translations.CreateIn`). */
export interface TranslationCreate {
  transcript_id: number;
  engine: string;
  target_lang?: string;
}

/** Body của `POST /api/translations`: hàng bản dịch + ĐÚNG MỘT job `translate`. */
export interface TranslationCreated {
  translation: Translation;
  job: Job;
}

/** Body của `POST /api/sources/upload` và `POST /api/sources/url`. */
export interface SourceCreated {
  source: Source;
  job: JobSlim;
}

/** Một hàng `glossary` (`routes_glossary._json`). */
export interface Term {
  id: number;
  lang: string;
  term: string;
  translation: string;
  note: string | null;
  approved: boolean;
  created_at: string;
}

/**
 * `POST`/`PATCH /api/glossary` trả hàng vừa ghi CỘNG `affected`.
 *
 * `affected` là id TRANSCRIPT (không phải segment, không phải số đếm): id của
 * transcript có ít nhất một đoạn bị ảnh hưởng. Giao diện đếm `affected.length`
 * và đối chiếu với danh sách bản dịch — nó KHÔNG được tự tính lại (spec §2).
 */
export interface TermWithAffected extends Term {
  affected: number[];
}

/** `POST /api/glossary` (`routes_glossary.TermIn`). */
export interface TermCreate {
  lang: string;
  term: string;
  translation: string;
  note?: string | null;
  approved?: boolean;
}

/** `PATCH /api/glossary/{id}` (`routes_glossary.TermPatch`) — trường vắng giữ nguyên. */
export interface TermPatch {
  translation?: string;
  note?: string | null;
  approved?: boolean;
}

/** `GET /api/glossary/version`. */
export interface GlossaryVersion {
  glossary_version: number;
}

/** `GET /api/glossary/affected` — xem `affectedPreview` trong `endpoints.ts`. */
export interface AffectedPreview {
  affected: number[];
}

export type EngineKind = "asr" | "mt";
export type EngineRuntime = "inprocess" | "ollama";

/**
 * `spec.capabilities` — dict TỰ DO của `registry.json`, nhưng hai khoá dưới đây
 * do `app/main.py` ghi thêm và là thứ giao diện ĐỌC.
 *
 * `available` nghĩa là "engine này phục vụ được job NGAY BÂY GIỜ": tiến trình tới
 * được **VÀ** `model_ref` có trong `/api/tags` (đã pull). "Ollama sống" là điều
 * kiện cần nhưng KHÔNG đủ — tiến trình sống là tín hiệu riêng của `/api/status`.
 * `available` CHỈ có trên engine `kind === "mt"`; engine ASR không có khoá này.
 */
export interface EngineCapabilities {
  available?: boolean;
  prompt_version?: string;
  /** Cờ khác của registry: `glossary_prompt`, `glossary_patch`, `chimera`, … */
  [flag: string]: boolean | string | number | undefined;
}

/**
 * Một engine trong registry (`asdict(EngineSpec)` + `langs` thành mảng).
 *
 * `opts` và `capabilities` là hai dict tự do — đọc chúng bằng khoá cụ thể, đừng
 * duyệt rồi đoán kiểu.
 */
export interface EngineSpec {
  id: string;
  label: string;
  kind: EngineKind;
  runtime: EngineRuntime;
  model_ref: string;
  vram_mb: number;
  langs: string[];
  capabilities: EngineCapabilities;
  opts: Record<string, unknown>;
}

/**
 * `GET /api/registry` — khoá theo `kind`, KHÔNG phải một mảng phẳng.
 *
 * Route dựng `{"asr": [...], "mt": [...]}` rồi `setdefault(spec.kind, [])`, nên
 * giao diện đọc `registry.mt` chứ không `registry[0]`.
 */
export interface Registry {
  asr: EngineSpec[];
  mt: EngineSpec[];
}

/**
 * `routes_registry.probe_ollama`. `unknown` là giá trị THẬT: timeout/DNS chưa
 * phân giải được nghĩa là CHƯA ĐO ĐƯỢC, không phải "đang tắt". §4.8 phải nói
 * đúng ba trạng thái này, không gộp `unknown` vào `down`.
 */
export type OllamaState = "up" | "down" | "unknown";

/** `GET /api/status`. `vram` là `null` TƯỜNG MINH (GĐ1a chưa đo được) — khoá vẫn có. */
export interface Status {
  queue_depth: number;
  running: number[];
  current_phase: string | null;
  phase_switches: number;
  vram: number | null;
  ollama: OllamaState;
}
