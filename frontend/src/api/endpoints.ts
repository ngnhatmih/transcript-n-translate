/**
 * Hàm theo nhóm endpoint — CHỈ những thứ bốn màn hình thật sự gọi.
 *
 * Không có wrapper cho endpoint chưa màn hình nào dùng: một hàm thừa ở đây là
 * một hợp đồng phải bảo trì mà không ai kiểm, và nó trôi âm thầm (đúng lớp lỗi
 * mà `contract.test.ts` sinh ra để bắt).
 *
 * Mọi đường dẫn ở đây TƯƠNG ĐỐI (`/api/...` qua `BASE`) trừ `mediaUrl`/`exportUrl`
 * — hai hàm đó trả URL cho thuộc tính `src`/`href` của trình duyệt, và trình
 * duyệt đi qua proxy 3100 như mọi request khác.
 */
import { api, BASE } from "./client.ts";
import type {
  AffectedPreview,
  EngineSpec,
  GlossaryVersion,
  Job,
  Registry,
  Source,
  SourceCreated,
  SourceLang,
  Status,
  Term,
  TermCreate,
  TermPatch,
  TermWithAffected,
  Transcript,
  TranscriptPatch,
  TranscriptSummary,
  Translation,
  TranslationCreate,
  TranslationCreated,
  TranslationSegmentPatch,
} from "./types.ts";

/** Định dạng xuất phụ đề — đúng khoá của `pipeline/export.py::FORMATS`. */
export type ExportFormat = "srt" | "vtt" | "ass";

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const text = search.toString();
  return text === "" ? "" : `?${text}`;
}

// ---------------------------------------------------------------------------
// sources — kênh vào: liệt kê, tải tệp, dán link
// ---------------------------------------------------------------------------

export function listSources(): Promise<Source[]> {
  return api.get<Source[]>("/sources");
}

export function getSource(sourceId: number): Promise<Source> {
  return api.get<Source>(`/sources/${sourceId}`);
}

/**
 * `POST /api/sources/upload` — multipart. `lang` là trường FORM, không phải
 * query (route khai `lang: str = Form(...)`), nên nó phải nằm trong `FormData`.
 */
export function uploadSource(file: File, lang: SourceLang = "zh"): Promise<SourceCreated> {
  const form = new FormData();
  form.set("file", file);
  form.set("lang", lang);
  return api.postForm<SourceCreated>("/sources/upload", form);
}

/** `POST /api/sources/url` — backend chỉ nhận http/https và `lang ∈ {zh, en}`. */
export function addSourceUrl(url: string, lang: SourceLang = "zh"): Promise<SourceCreated> {
  return api.post<SourceCreated>("/sources/url", { url, lang });
}

// ---------------------------------------------------------------------------
// jobs — hàng đợi: liệt kê, xem, huỷ, chạy lại
// ---------------------------------------------------------------------------

export function listJobs(): Promise<Job[]> {
  return api.get<Job[]>("/jobs");
}

export function getJob(jobId: number): Promise<Job> {
  return api.get<Job>(`/jobs/${jobId}`);
}

/** Job đang `queued` thì backend huỷ NGAY; job `running` chỉ được đặt cờ. */
export function cancelJob(jobId: number): Promise<Job> {
  return api.post<Job>(`/jobs/${jobId}/cancel`);
}

/** Chỉ chạy lại được job ở trạng thái `failed`/`interrupted` (backend trả 409 nếu không). */
export function retryJob(jobId: number): Promise<Job> {
  return api.post<Job>(`/jobs/${jobId}/retry`);
}

// ---------------------------------------------------------------------------
// transcripts — danh sách, chi tiết, sửa (tăng version), duyệt
// ---------------------------------------------------------------------------

/** KHÔNG kèm `segments` — route danh sách cố ý không kéo đoạn nào. */
export function listTranscripts(): Promise<TranscriptSummary[]> {
  return api.get<TranscriptSummary[]>("/transcripts");
}

export function getTranscript(transcriptId: number): Promise<Transcript> {
  return api.get<Transcript>(`/transcripts/${transcriptId}`);
}

/** Sửa nội dung là TĂNG `version` ⇒ mọi bản dịch cũ thành `stale`. */
export function patchTranscript(transcriptId: number, body: TranscriptPatch): Promise<Transcript> {
  return api.patch<Transcript>(`/transcripts/${transcriptId}`, body);
}

/** Duyệt KHÔNG tăng version — nó chỉ đổi `status` sang `reviewed`. */
export function approveTranscript(transcriptId: number): Promise<TranscriptSummary> {
  return api.post<TranscriptSummary>(`/transcripts/${transcriptId}/approve`);
}

// ---------------------------------------------------------------------------
// translations — tạo (xếp job), liệt kê, sửa tay
// ---------------------------------------------------------------------------

/** Tạo hàng `translations` rồi xếp ĐÚNG MỘT job `translate` (201). */
export function createTranslation(body: TranslationCreate): Promise<TranslationCreated> {
  return api.post<TranslationCreated>("/translations", body);
}

/** Bản dịch của MỘT transcript, mới nhất trước, kèm cờ `stale` tính ở server. */
export function listTranslations(transcriptId: number): Promise<Translation[]> {
  return api.get<Translation[]>(`/translations${query({ transcript_id: transcriptId })}`);
}

/** Sửa tay CHỈ đổi `text`; id lạ (không thuộc bản dịch) bị từ chối 422 trước khi ghi. */
export function patchTranslation(
  translationId: number,
  segments: TranslationSegmentPatch[],
): Promise<Translation> {
  return api.patch<Translation>(`/translations/${translationId}`, { segments });
}

// ---------------------------------------------------------------------------
// glossary — thuật ngữ và hệ quả của nó
// ---------------------------------------------------------------------------

export function listTerms(lang?: string): Promise<Term[]> {
  return api.get<Term[]>(`/glossary${query({ lang })}`);
}

/** Ghi thuật ngữ (upsert theo `(lang, term)`) và trả LUÔN `affected`. */
export function createTerm(body: TermCreate): Promise<TermWithAffected> {
  return api.post<TermWithAffected>("/glossary", body);
}

/** Sửa MỘT PHẦN: trường vắng mặt giữ nguyên giá trị đã lưu. */
export function patchTerm(termId: number, body: TermPatch): Promise<TermWithAffected> {
  return api.patch<TermWithAffected>(`/glossary/${termId}`, body);
}

/**
 * `glossary_version` hiện tại — ĐỌC, không ghi.
 *
 * Client KHÔNG gọi gì để "tăng version": `POST /api/glossary` tự tăng bên trong
 * `upsert_term`. Hàm này tồn tại để giao diện BIẾT version, không phải để đổi nó.
 */
export function glossaryVersion(): Promise<GlossaryVersion> {
  return api.get<GlossaryVersion>("/glossary/version");
}

/**
 * Số bản dịch bị ảnh hưởng TRƯỚC khi lưu (spec UI §12.3).
 *
 * ⚠️ Route này (`GET /api/glossary/affected`) CHƯA có trong backend ở Task 2 —
 * nó được thêm ở Task 9 Step 0, và trả `{"affected": [...]}` bằng cách gọi LẠI
 * chính `affected_segments` mà `POST`/`PATCH` dùng. Hàm ở đây là hợp đồng
 * `endpoints.affectedPreview` mà `GlossaryScreen` (Task 9) tiêu thụ; client
 * KHÔNG được tự tính lại con số này (spec frontend §2).
 */
export function affectedPreview(params: {
  lang: string;
  term: string;
  translation: string;
  approved?: boolean;
}): Promise<AffectedPreview> {
  return api.get<AffectedPreview>(
    `/glossary/affected${query({
      lang: params.lang,
      term: params.term,
      translation: params.translation,
      // `approved` là query param boolean; backend khai `approved: bool = False`,
      // nên `false` phải gửi thành "false" chứ không được bỏ khoá đi — bỏ đi thì
      // backend rơi về mặc định `False`, tức ĐÚNG giá trị ta muốn, nhưng gửi
      // tường minh giữ cho URL nói ra ý định.
      approved: params.approved === undefined ? undefined : String(params.approved),
    })}`,
  );
}

// ---------------------------------------------------------------------------
// registry + status — hai endpoint chỉ đọc của §4.8 và dropdown engine
// ---------------------------------------------------------------------------

/** Danh sách engine theo `kind`. Giao diện đọc thẳng từ đây, KHÔNG hard-code. */
export function registry(): Promise<Registry> {
  return api.get<Registry>("/registry");
}

/** Như `registry()` nhưng làm phẳng hai nhóm thành một mảng để dựng dropdown. */
export async function listEngines(): Promise<EngineSpec[]> {
  const body = await registry();
  return [...body.asr, ...body.mt];
}

/** Trạng thái hàng đợi + Ollama + VRAM cho dải trạng thái ở header. */
export function status(): Promise<Status> {
  return api.get<Status>("/status");
}

// ---------------------------------------------------------------------------
// URL cho trình duyệt — không phải hàm fetch
// ---------------------------------------------------------------------------

/**
 * `src` của trình phát. Backend phục vụ `Range`, nên trình duyệt tự seek được;
 * client KHÔNG tự đọc khoảng byte nào.
 */
export function mediaUrl(sourceId: number): string {
  return `${BASE}/media/${sourceId}`;
}

/**
 * URL xuất phụ đề của MỘT bản dịch (spec §11). Trả nội dung ngay, không xếp job.
 *
 * Ba nút xuất của thanh transport dùng ĐÚNG hàm này — không tự ghép URL ở client,
 * vì `format` sai tên là 422 và thứ tự tham số là chuyện của backend.
 */
export function exportUrl(
  translationId: number,
  format: ExportFormat = "srt",
  bilingual = false,
): string {
  // `bilingual` là `int` ở backend (0/1), không phải `bool` chuỗi.
  return `${BASE}/export/${translationId}${query({ format, bilingual: bilingual ? 1 : 0 })}`;
}

/**
 * Bản gom nhóm của mọi hàm trên.
 *
 * Tồn tại vì các task sau gọi CẢ HAI kiểu: `endpoints.listSources()` (Task 4,
 * Task 9, Task 10) và `import { getTranscript }` (Task 8). Hai lối vào cùng một
 * tập hàm — không có bản sao logic nào ở đây, chỉ có tên.
 */
export const endpoints = {
  listSources,
  getSource,
  uploadSource,
  addSourceUrl,
  listJobs,
  getJob,
  cancelJob,
  retryJob,
  listTranscripts,
  getTranscript,
  patchTranscript,
  approveTranscript,
  createTranslation,
  listTranslations,
  patchTranslation,
  listTerms,
  createTerm,
  patchTerm,
  glossaryVersion,
  affectedPreview,
  registry,
  listEngines,
  status,
  mediaUrl,
  exportUrl,
};
