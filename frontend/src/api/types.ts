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
 * sập khi shape trôi là một contract test, và nó sập ỒN ÀO. Xem `contract.test.ts`.
 *
 * MỨC KIỂM THẬT của MỌI KIỂU đã export — đọc ra từ `contract.test.ts`, KHÔNG phải
 * lời hứa. ⚠️ KHÔNG viết con số vào khối này: ERRATA #4 mục 7 / #6 mục 1 cấm nó, và
 * chính tệp này đã nói dối bằng số BỐN vòng liên tiếp (lần cuối: khai 33 kiểu trong
 * khi đo được 36). Một khối comment liệt kê/đếm là nghĩa vụ bảo trì không ai canh.
 * Đếm bằng LỆNH, chạy từ `frontend/`:
 *   đếm MỌI kiểu đã export —
 *     Select-String -Path src/api/types.ts -Pattern '^export (interface|type) '
 *   đếm `export type` riêng — cùng lệnh, đổi mẫu thành '^export type '
 *   kiểu nào test chạm (quét CẢ `src/` lẫn `test/`) —
 *     $f = Get-ChildItem src,test -Recurse -File | Where-Object { $_.Name -match '\.test\.(ts|tsx|mjs|js)$' }
 *     $f | Select-String '\b<TenKieu>\b'
 *
 *   CÓ bài kiểm khoá (route được GỌI THẬT, response được soi từng khoá):
 *     `Status` (`GET /api/status`) · `Registry`, `EngineSpec`, `EngineCapabilities`
 *     (`GET /api/registry`) · `TranscriptSummary`, `Translation`
 *     (`GET /api/transcripts`) · `Transcript`, `Segment` (`GET /api/transcripts/{id}`)
 *     · `GlossaryVersion` (`GET /api/glossary/version`) · `TranslationDetail`,
 *     `TranslationCps`, `TranslationCpsRow` (`GET /api/translations/{id}` — Task 8,
 *     soi trên một backend có DB GIEO, vì DB repo rỗng).
 *     · `AffectedPreview`, `Term`, `TermWithAffected`: route `GET /api/glossary/affected`
 *     và `GET`/`POST`/`PATCH /api/glossary` (Task 9). Ba kiểu này được soi qua
 *     `src/screens/GlossaryScreen.test.tsx` trên một backend có DB GIEO, và bài ghim
 *     hợp đồng tham số ở đó khẳng định URL do `endpoints.affectedPreview` sinh ra
 *     được ROUTE THẬT chấp nhận — đổi tên một khoá hay một tham số làm nó đỏ.
 *     `Word` cũng được soi, nhưng CHỈ khi một segment thật sự CÓ khoá `words` —
 *     và khoá đó có thể là mảng RỖNG, xem `Segment` bên dưới.
 *
 *   CHỈ được đối chiếu MÃ NGUỒN (đọc `routes_*.py`/`models.py`); một lần trôi khoá
 *   ở nhóm này KHÔNG làm tệp test đỏ:
 *     - `SourceCreated`, `TranslationCreated`: chỉ có trong body của
 *       `POST /api/sources/*` và `POST /api/translations`. Gọi thật cần upload thật
 *       và một engine MT thật — Ollama đang tắt, nên không endpoint nào được gọi.
 *     - `JobSlim` (TYPE ALIAS, không phải interface — `Pick<Job, …>`): cùng body đó.
 *     - `JobEvent`: chỉ có trên SSE `/api/jobs/stream`; test không mở stream.
 *     - `Source`, `Job`: route `GET` CÓ thật, nhưng bài hiện tại chỉ khẳng định
 *       "là một mảng" — chưa soi khoá nào.
 *
 *   `*Create`/`*Patch` là BODY gửi LÊN (không phải response):
 *   `TranscriptPatch`, `TranslationSegmentPatch`, `TranslationCreate`, `TermCreate`,
 *   `TermPatch`. Đối chiếu với `routes_*.py` bằng cách đọc mã, cộng hai bài 422 đo
 *   TÊN trường (`transcript_id`, `lang`). Đừng nhóm theo HẬU TỐ: `TranslationCreated`
 *   và `SourceCreated` cũng kết thúc bằng "Created" nhưng là RESPONSE, đã ở nhóm 2;
 *   theo hậu tố `*Create|*Created|*Patch` thì nhóm này phình thêm hai tên SAI nhóm.
 *
 *   Các `type` union GIÁ TRỊ không có bài kiểm nào: `JobType`, `JobState`, `SourceLang`,
 *   `SourceKind`, `TranscriptStatus`, `TranslationStatus`, `EngineKind`,
 *   `EngineRuntime`. Không tệp `*.test.*` nào import hay nhắc chúng. Tất cả là union
 *   GIÁ TRỊ và đều là KIỂU CỦA MỘT TRƯỜNG của interface ở nhóm 1 hoặc nhóm 2
 *   (`JobState` còn ở `JobEvent`, `TranscriptStatus` còn ở `TranscriptPatch` nhóm
 *   3): `JobType`, `JobState` của `Job`; `SourceLang`, `SourceKind` của `Source`;
 *   `TranscriptStatus` của `TranscriptSummary` (KHÔNG phải trực tiếp của
 *   `Transcript` — nó thừa kế qua `extends`); `TranslationStatus` của
 *   `Translation`; `EngineKind`, `EngineRuntime` của `EngineSpec`. Nên tập giá trị
 *   của chúng chỉ được đối chiếu MÃ NGUỒN qua interface cha — KHÔNG qua một bài
 *   test ép tập giá trị.
 *
 *   `OllamaState` là `type` DUY NHẤT được test chạm: `contract.test.ts` import nó
 *   và ép `(["up","down","unknown"] as OllamaState[]).includes(body.ollama)` trong
 *   bài `/api/status` — kiểm TẬP GIÁ TRỊ, không phải soi khoá của route, nên nó
 *   KHÔNG thuộc nhóm 1. Nó là `type` của trường `Status.ollama`.
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
 * BẤT BIẾN của `to_json`: khoá tuỳ chọn chỉ xuất hiện khi có dữ liệu — `events`
 * và `qa` ghi bằng truthiness (`if self.events:`) nên danh sách RỖNG không bao
 * giờ thành khoá, còn `words` ghi bằng `if self.words is not None` nên `[]` VẪN
 * được ghi (đo trên route thật: PATCH `"words": []` ⇒ 200 ⇒ GET trả `"words":[]`).
 * Vắng khoá `words` và `words: []` vì thế KHÁC nhau về dữ liệu — cả hai đều nghĩa
 * là "không có mốc thời gian từng từ", nhưng chỉ vắng khoá mới là "engine không
 * sinh word timestamp"; đường ASR không sinh `[]` (`faster_whisper.py`: `words or
 * None`), còn PATCH thì nhận. Giao diện phải đọc theo hướng chỉ tin `words` khi
 * nó có PHẦN TỬ, đừng tin riêng chuyện "có khoá".
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
export type JobType = "ingest" | "asr" | "translate" | "export" | "dub";
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
  /**
   * Số đo của lượt dịch — `null` = KHÔNG ĐO ĐƯỢC (engine in-process không báo token), KHÁC `0`.
   *
   * Tuỳ chọn (`?`) vì client phải đọc được cả một hàng do bản máy chủ CŨ trả (không có khoá) —
   * nhưng khi CÓ khoá thì `null` là một câu trả lời thật, không phải "thiếu dữ liệu".
   */
  tokens_in?: number | null;
  tokens_out?: number | null;
  duration_ms?: number | null;
  /**
   * CHI PHÍ ƯỚC LƯỢNG (USD) = token ĐÃ ĐO × giá ĐÃ KHAI của engine trong `registry.json`.
   *
   * `null` khi không tính được (engine không khai giá, hoặc hàng chưa có token). KHÔNG phải
   * hoá đơn, và KHÔNG được hiển thị như một con số chắc chắn — cùng luật với khối chi phí
   * Chimera (§4.5): mọi chỗ hiện nó phải nói "ước lượng".
   */
  cost_usd?: number | null;
}

/**
 * CPS của MỘT đoạn dịch — SỐ, không phải một chuỗi hiển thị.
 *
 * Vì sao có mặt: `translations.qa_issues` giữ CPS dưới dạng CHUỖI (`"cps:3=45.2>21.0"`)
 * và chuỗi đó **không tới được HTTP** (0/12 route GET — đo ở ERRATA #18). Client KHÔNG
 * được parse một chuỗi hiển thị để lấy con số nó hiển thị, nên `GET /api/translations/{id}`
 * phát ra SỐ, sinh từ CÙNG hàm `mt_qa.cps_row` đã sinh chuỗi kia.
 */
export interface TranslationCpsRow {
  /** `Segment.i` — khoá để ghép một hàng CPS với dòng ở hai cột. */
  i: number;
  /** Số ký tự đã đếm (còn hiển thị được khi tốc độ không đo được). */
  chars: number;
  /** Cửa sổ thời gian đã dùng, giây — cửa sổ NGUỒN (dự phòng: cửa sổ bản dịch). */
  window: number;
  /** `null` = KHÔNG ĐO ĐƯỢC (cả hai cửa sổ đều không dương). KHÁC `0.0`. */
  cps: number | null;
  max_cps: number;
  /**
   * Cờ VƯỢT NGƯỠNG, tính ở server trên giá trị **CHƯA làm tròn**.
   *
   * Client PHẢI đọc cờ này thay vì tự so `cps > max_cps`: `cps` đã làm tròn để hiển
   * thị, nên ở đúng biên (21,04 CPS ⇒ hiện 21,0) phép so của client sẽ nói SAI.
   */
  over: boolean;
}

/** Ngưỡng CPS + một hàng cho mỗi đoạn dịch. */
export interface TranslationCps {
  max_cps: number;
  rows: TranslationCpsRow[];
}

/**
 * Chi tiết MỘT bản dịch — `GET /api/translations/{id}`.
 *
 * Gồm ĐỦ 9 khoá tóm tắt của `Translation` (dùng CHUNG builder nên hai route không thể
 * phát hai hình dạng cho một hàng) cộng hai thứ mà trước route này KHÔNG JSON nào có:
 * `segments` của BẢN DỊCH (cột phải của §4.3) và `cps` dạng số (cột CPS).
 */
export interface TranslationDetail extends Translation {
  segments: Segment[];
  cps: TranslationCps;
  /**
   * Dấu vết chế độ CHIMERA (§4.5). Backend LUÔN gửi khoá này — `null` trên một bản
   * dịch thường, và `null` KHÁC `{}`: `{}` nghĩa là "có chạy mà chưa có dữ liệu".
   *
   * ⚠️ Đánh dấu TUỲ CHỌN vì test truyền prop dựng tay, KHÔNG phải vì backend có thể
   * bỏ khoá — mọi hàng đọc từ `GET /api/translations/{id}` đều có nó.
   */
  chimera?: ChimeraRun | null;
}

/**
 * Một ỨNG VIÊN Chimera — phần KẾ HOẠCH (đọc trước khi chạy).
 *
 * Ứng viên là DỮ LIỆU của `registry.json` (`chimera.candidates`), nên giao diện
 * KHÔNG được hard-code số sáu hay tên engine nào: `declared`/`runnable` là hai con số
 * phải đọc từ response.
 */
export interface ChimeraCandidate {
  id: string;
  engine: string;
  label: string;
  /** `null` = ứng viên không khai nhiệt độ; adapter dùng mặc định của nó. */
  temperature: number | null;
  /**
   * Cảnh báo CHẤT LƯỢNG đã đo, đi KÈM cảnh báo chi phí mà §4.5 đòi.
   *
   * Vì sao nó là một trường chứ không phải câu chữ trong giao diện: `qwen2.5-3b` đã
   * đo được là CHÉP nguyên chữ nguồn, và một chế độ gọi nó sáu lần rồi "pha" sáu bản
   * chữ Hán là một chế độ vô dụng. Một cảnh báo chi phí không kèm cảnh báo chất
   * lượng là một lời mời dùng sai.
   */
  quality_note: string | null;
  available: boolean;
  /** Lý do KHÔNG chạy được, bằng chữ. `null` khi `available` là `true`. */
  reason: string | null;
}

/** Ước lượng chi phí của CẢ lượt Chimera, suy tỉ lệ từ một bản dịch THẬT đã xong. */
export interface ChimeraEstimate {
  calls_per_batch: number;
  /** `null` = KHÔNG ĐO ĐƯỢC (engine không trả token/thời gian). KHÁC `0`. */
  duration_ms: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
}

/** Bản dịch THẬT được dùng làm cơ sở đo — có `translation_id` và engine để đối chiếu. */
export interface ChimeraBaseline {
  translation_id: number | null;
  engine: string;
  segments: number;
  duration_ms: number | null;
  tokens_in: number | null;
  tokens_out: number | null;
}

/**
 * `GET /api/chimera/cost` — CẢNH BÁO CHI PHÍ hiện TRƯỚC khi người dùng bấm (§4.5).
 *
 * `estimate: null` là một câu trả lời HỢP LỆ, và `estimate_basis`/`estimate_hint` nói
 * vì sao chưa đo được cùng việc cần làm. Bịa một con số ở đây là làm hỏng đúng thứ
 * dòng 423 của spec UI đòi.
 */
export interface ChimeraCost {
  segments: number;
  /** Số ứng viên ĐÃ KHAI trong registry. */
  declared: number;
  /** Số ứng viên THẬT SỰ chạy được trên máy này. */
  runnable: number;
  /** Số lượt chạm engine cho MỘT lô: `runnable` ứng viên + ĐÚNG MỘT lượt pha. */
  calls_per_batch: number;
  /** Hệ số so với một lượt dịch một-engine. Bằng `calls_per_batch`. */
  multiplier: number;
  merge_engine: string;
  candidates: ChimeraCandidate[];
  baseline: ChimeraBaseline | null;
  estimate: ChimeraEstimate | null;
  estimate_basis: string;
  /** Việc cần làm khi `estimate` là `null`. `null` khi đã có số đo. */
  estimate_hint?: string | null;
}

/** Một ứng viên ĐÃ CHẠY (hoặc đã bị bỏ qua) trong bản ghi của một bản dịch. */
export interface ChimeraCandidateRun extends ChimeraCandidate {
  ran: boolean;
  /** Lý do bị bỏ qua / thất bại. `null` khi nó chạy được. */
  skipped: string | null;
  /** Số cờ QA của tầng 1 (§8.8) trên bản dịch của ứng viên này. */
  qa: number;
  /** Số đoạn VƯỢT NGƯỠNG ĐỌC. */
  cps_over: number;
  /**
   * Số đoạn DỊCH GIỐNG HỆT bản nguồn — phép đo trực tiếp của thất bại đã biết.
   *
   * ĐO ĐƯỢC trên máy này: bốn ứng viên `qwen2.5-3b`/`qwen2.5-7b` ở ba mức nhiệt độ cho
   * `echo = 6/6` (chép nguyên chữ Hán), còn `opus-mt` cho `0/6`.
   */
  echo: number;
  calls: number;
  tokens_in: number | null;
  tokens_out: number | null;
  duration_ms: number | null;
  /** Chữ của ứng viên này theo từng đoạn — nguồn của bốn cửa sổ xếp chồng ở §4.5. */
  segments: { i: number; text: string }[];
}

export interface ChimeraMerge {
  engine: string;
  calls: number;
  tokens_in: number | null;
  tokens_out: number | null;
  duration_ms: number | null;
  /** Đoạn đã LÙI VỀ MỎ NEO vì lượt pha hỏng. Rỗng = lượt pha chạy được. */
  fallback_segments: number[];
  fallback_reason: string | null;
  /**
   * Đoạn mà lượt pha trả về CHUỖI Y HỆT mỏ neo — lượt gọi thứ `N+1` không đổi lấy được gì.
   *
   * ⚠️ Tuỳ chọn: một hàng ghi trước bản này không có khoá. ĐO ĐƯỢC trên máy này: cả
   * sáu đoạn đều nằm trong danh sách này.
   */
  identical_segments?: number[];
  /** `Segment.i` (khoá CHUỖI, vì JSON) -> chỉ số 1-based của ứng viên làm mỏ neo. */
  anchor_by_segment: Record<string, number>;
}

/** `translations.chimera` — dấu vết đầy đủ của MỘT bản dịch chạy ở chế độ Chimera. */
export interface ChimeraRun {
  enabled: boolean;
  declared: number;
  run_count: number;
  ran_count: number;
  calls_per_batch: number;
  merge_engine: string;
  /** `{id_ứng_viên: số đoạn nó làm mỏ neo}`. */
  anchors: Record<string, number>;
  candidates: ChimeraCandidateRun[];
  merge: ChimeraMerge;
  /**
   * Số CHUỖI KHÁC NHAU giữa các ứng viên đã chạy, theo từng đoạn.
   *
   * `1` nghĩa là mọi ứng viên trả về y hệt nhau — lượt pha không có gì để pha, và đó
   * là con số khiến "chế độ đắt gấp N" trở thành một phép đo thay vì một lời khai.
   * ĐO ĐƯỢC: `qwen2.5-3b`/`qwen2.5-7b` ở ba nhiệt độ cho `1` ở cả sáu đoạn.
   *
   * ⚠️ Tuỳ chọn: hàng ghi trước bản này không có khoá.
   */
  distinct_by_segment?: Record<string, number>;
  estimate?: ChimeraEstimate | null;
  estimate_basis?: string;
  baseline?: ChimeraBaseline | null;
  segments?: number;
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
  /**
   * Bật chế độ CHIMERA (§8.7.5). Khi bật, `engine` chỉ còn là một phép kiểm hợp lệ:
   * kế hoạch ứng viên của registry quyết định, và `translations.engine` ghi engine
   * PHA — engine thật sự viết ra chữ được giữ.
   */
  chimera?: boolean;
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

/**
 * `GET /api/glossary/affected` — xem `affectedPreview` trong `endpoints.ts`.
 *
 * `affected` là id TRANSCRIPT (không phải số bản dịch): xem `TermWithAffected`. Route
 * này ra đời ở Task 9 Step 0 và được ghim qua HTTP thật bởi
 * `src/screens/GlossaryScreen.test.tsx`.
 */
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

/**
 * `GET /api/status`.
 *
 * `vram` là VRAM ĐANG DÙNG, backend đọc thật từ `nvidia-smi`; `null` nghĩa là
 * CHƯA ĐỌC ĐƯỢC (không GPU/không binary, hoặc app dựng không có reader) —
 * không bao giờ là 0, vì 0 là một con số nói "card trống".
 *
 * `vram_unit` đi kèm vì giao diện KHÔNG được tự thêm đơn vị mà backend không
 * nói: `3200` trần trụi là một con số vô nghĩa. Trường này có cả khi `vram` là
 * `null` — nó nói đơn vị của con số SẼ có nếu đo được.
 */
export interface Status {
  queue_depth: number;
  running: number[];
  current_phase: string | null;
  phase_switches: number;
  vram: number | null;
  vram_unit: string;
  ollama: OllamaState;
}
