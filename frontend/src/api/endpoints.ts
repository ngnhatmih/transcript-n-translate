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
  ChimeraCost,
  DubPlan,
  EngineSpec,
  GlossaryVersion,
  Job,
  JobType,
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
  TranslationDetail,
  TranslationSegmentPatch,
} from "./types.ts";

/**
 * Định dạng xuất — đúng khoá của `pipeline/export.py::FORMATS`.
 *
 * `json` là định dạng hai thứ tiếng kèm mốc thời gian của BẢN GỐC
 * (`domain/subtitle_format.py::to_json`): mỗi đoạn có `start`/`end` (giây, của bản
 * gốc), `text` (nguồn), `translation`, và một khối `meta` (bản dịch nào, engine
 * nào, prompt nào, `stale`). Ba định dạng kia chỉ có chữ, nên muốn ghép lại bản
 * gốc với bản dịch thì phải parse phụ đề.
 */
export type ExportFormat = "srt" | "vtt" | "ass" | "json";

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

/**
 * `DELETE /api/sources/{id}` — xoá MỘT kênh cùng mọi bản ghi/bản dịch của nó (**204**).
 *
 * Vì sao `Promise<void>` chứ không `Promise<Source>`: route trả **204 KHÔNG thân**
 * (`routes_sources.delete_source`), và `client.call` đã trả `undefined` cho đúng
 * mã đó. Bịa một hàng trả về ở đây là hứa một thứ backend không gửi.
 *
 * ⚠️ Hàm KHÔNG tự đọc lại danh sách: người gọi (`App`) gọi `sources.reload()` sau
 * khi hàm này xong — nguồn sự thật là máy chủ, không phải một bản sao cục bộ đã
 * bị cắt tay (cùng luật với mọi đường GHI khác của app).
 *
 * Hai nhánh lỗi mà NGƯỜI DÙNG phải đọc nguyên văn (backend đã viết tiếng Việt):
 * **404** (`source N không tồn tại`) và **409** (`job #k đang xếp hàng hoặc đang
 * chạy trên nó`) — `ApiError.message` đã là `"<status>: <detail>"`.
 */
export function deleteSource(sourceId: number): Promise<void> {
  return api.del<void>(`/sources/${sourceId}`);
}

// ---------------------------------------------------------------------------
// jobs — hàng đợi: tạo, liệt kê, xem, huỷ, chạy lại
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

/**
 * Body của `POST /api/jobs` — ĐÚNG `routes_jobs.JobIn`.
 *
 * Vì sao `engine` là TUỲ CHỌN chứ không bắt buộc: route chỉ đòi engine với
 * `type ∈ ENGINE_REQUIRED` (`{"asr"}`, cùng tệp), còn `ingest`/`export` không có engine nào để
 * chọn. Khai bắt buộc ở client sẽ là một lời hứa SAI về hợp đồng máy chủ.
 *
 * `type` là `JobType` (union của `types.ts`) chứ `string`: route trả **422** cho một loại không
 * nằm trong `PAYLOAD_SCHEMA`, và một union chặn lỗi đó ngay ở chỗ viết code thay vì ở chỗ chạy.
 *
 * `payload` KHÔNG được khai kiểu theo từng loại job ở đây: hợp đồng payload (`IngestPayload`/
 * `AsrPayload`/`ExportPayload`) do `PAYLOAD_SCHEMA` của route định nghĩa và nó được kiểm Ở MÁY
 * CHỦ trước khi ghi hàng (sai trường ⇒ 422 ngay, không phải một job `failed` ở worker). Client
 * chép lại hợp đồng đó là nguồn sự thật thứ hai — và nó sẽ trôi âm thầm.
 */
export interface JobCreate {
  workspace: number;
  type: JobType;
  engine?: string | null;
  payload?: Record<string, unknown>;
}

/**
 * `POST /api/jobs` — XẾP một job vào hàng đợi; máy chủ trả hàng `jobs` vừa tạo (**201**).
 *
 * ⚠️ Đây là đường DUY NHẤT để chạy lại việc bóc băng bằng một engine ASR khác: route `retry`
 * chỉ chạy lại CHÍNH job cũ (cùng engine, cùng payload), còn đổi engine thì phải là một job
 * `asr` MỚI. Không có hàm này, ô chọn engine ở màn Biên tập là một điều khiển bấm được mà không
 * gửi gì đi — đúng thứ repo này cấm.
 *
 * ⚠️ Hàm KHÔNG tự đọc lại gì sau khi tạo: job mới đi vào HÀNG ĐỢI qua SSE (`useJobStream`), và
 * bản ghi mới của nó hiện ra qua ngòi nổ đọc lại `/api/transcripts` khi job `asr` chuyển `done`.
 */
export function createJob(body: JobCreate): Promise<Job> {
  return api.post<Job>("/jobs", body);
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

/**
 * Chi tiết MỘT bản dịch: đoạn ĐÃ DỊCH + CPS dạng SỐ — nguồn của §4.3 (màn Đối chiếu).
 *
 * Vì sao cần route riêng thay vì đọc từ danh sách: hình dạng của một phần tử trong
 * `GET /api/translations` đã được KÝ thành hợp đồng (`contract.test.ts` ghim nó trên
 * backend thật), và nó KHÔNG mang `segments` của bản dịch — trước route này không JSON
 * nào có chúng, nên cột phải của màn Đối chiếu không có nguồn.
 *
 * ⚠️ Hàm này CHƯA được màn nào gọi: `CompareScreen` nhận dữ liệu qua PROP (cùng khuôn
 * `EditScreen`/`Transport`), và người gọi nó là đường **CHỌN KÊNH** — đường đó CHƯA tồn
 * tại (ERRATA #18 mục 4), nên `App` mới truyền `translations={[]}`. Wrapper ở đây là
 * hợp đồng cho task CHỌN KÊNH, không phải một hàm đã chạy trong sản phẩm.
 */
export function getTranslation(translationId: number): Promise<TranslationDetail> {
  return api.get<TranslationDetail>(`/translations/${translationId}`);
}

/** Sửa tay CHỈ đổi `text`; id lạ (không thuộc bản dịch) bị từ chối 422 trước khi ghi. */
export function patchTranslation(
  translationId: number,
  segments: TranslationSegmentPatch[],
): Promise<Translation> {
  return api.patch<Translation>(`/translations/${translationId}`, { segments });
}

/**
 * `DELETE /api/translations/{id}` — xoá MỘT bản dịch, transcript của nó giữ nguyên (**204**).
 *
 * Cùng hình dạng với `deleteSource` (và cùng ba nhánh lỗi: 404 id lạ, 409 khi còn
 * job `translate` sống). Người gọi đọc lại danh sách bằng `translations.reload()`.
 */
export function deleteTranslation(translationId: number): Promise<void> {
  return api.del<void>(`/translations/${translationId}`);
}

// ---------------------------------------------------------------------------
// chimera — cảnh báo chi phí, ĐỌC TRƯỚC khi bấm
// ---------------------------------------------------------------------------

/**
 * Cảnh báo chi phí của MỘT lượt Chimera trên kênh này (§4.5, §9.2).
 *
 * Vì sao nó là một endpoint riêng chứ không phải một khoá của `/api/translations`:
 * câu hỏi "chế độ này tốn bao nhiêu" phải trả lời được TRƯỚC khi có bản dịch nào
 * tồn tại — nếu không thì "hiện trước khi người dùng bấm" là một lời hứa không có
 * đường thực hiện.
 *
 * ⚠️ `estimate: null` là câu trả lời HỢP LỆ ("chưa đo được"), kèm `estimate_basis`
 * và `estimate_hint`. Client KHÔNG được tự tính một con số thay thế.
 */
export function chimeraCost(transcriptId: number): Promise<ChimeraCost> {
  return api.get<ChimeraCost>(`/chimera/cost${query({ transcript_id: transcriptId })}`);
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
 * ĐỈNH SÓNG ÂM của một nguồn — tính Ở SERVER, trả JSON.
 *
 * 🔴 VÌ SAO KHÔNG GIẢI MÃ TRONG TRÌNH DUYỆT (đo được): client từng
 * `fetch('/api/media/1')` rồi `decodeAudioData`. Đo trên trang thật:
 *
 *   fetch status=206 type=video/mp4
 *   blob size=238623268 sau 0.0s
 *   ... rồi KHÔNG có `decodeAudioData OK` lẫn `LOI` trong 45 giây.
 *
 * Tải xong ngay (318 MB/s) nhưng `decodeAudioData` TREO trên container MP4 238 MB:
 * nó chỉ giải mã CẢ tệp và giữ toàn bộ mẫu đã giải mã trong bộ nhớ.
 *
 * Cách làm chuẩn (Peaks.js của BBC R&D) là tính peaks ở server, client chỉ vẽ.
 * Backend đọc `audio_path` (WAV 16 kHz, 40 MB) bằng `ffmpeg astats` — đo được
 * 1,61 s cho 1249 s, trả 8 297 B thay vì 238 MB.
 */
export function getPeaks(
  sourceId: number,
  soDinh?: number,
): Promise<{ tren: number[]; duoi: number[]; so_dinh: number; giay: number }> {
  // `api.get` TU ghep `BASE` (client.ts:61), nen duong o day KHONG co `/api`.
  // Ban truoc truyen `${BASE}/media/...` -> thanh `/api/api/media/1/peaks` -> 404.
  return api.get<{ tren: number[]; duoi: number[]; so_dinh: number; giay: number }>(
    `/media/${sourceId}/peaks${query(soDinh === undefined ? {} : { so_dinh: soDinh })}`,
  );
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
/**
 * Xếp MỘT job lồng tiếng cho một bản dịch. Trạng thái và file tải KHÔNG cần hàm riêng: job nằm
 * trong `GET /api/jobs` như mọi job khác, còn file là một `<a href>` tới
 * `/api/dubs/{id}/download?format=…` (tải file không phải một lời gọi `fetch`).
 *
 * 🔴 ĐƯỜNG DẪN Ở ĐÂY KHÔNG CÓ `/api` — `api.post` đã ghép `BASE = "/api"`. Viết `"/api/dubs"`
 * thành URL THẬT là `/api/api/dubs`, FastAPI không có route đó nên trả
 * `404 {"detail": "Not Found"}`, và màn Lồng tiếng hiện nguyên văn `404: Not Found` ngay dưới
 * nút. ĐO ĐƯỢC: `POST http://127.0.0.1:3100/api/api/dubs` -> `404 · {"detail": "Not Found"}`,
 * trong khi `POST /api/dubs` -> `201 · {"job": {...}}`.
 *
 * Vì sao lỗi này lọt qua 358 bài test: mọi bài của màn Lồng tiếng đều TIÊM `onLongTieng` giả,
 * nên `makeDub` không bao giờ chạy; còn `contract.test.ts` gọi `api.get/api.post` với URL
 * TUYỆT ĐỐI (`${API}/...`), đường mà `call` bỏ qua `BASE`. Không bài nào đi qua đúng tổ hợp
 * "hàm endpoint + đường TƯƠNG ĐỐI". Bài ghim ở `endpoints.test.ts` bắt đúng tổ hợp đó.
 */
export const makeDub = (translationId: number, voice: string | null) =>
  api.post<{ job: { id: number; type: string; state: string; translation_id: number } }>(
    "/dubs", { translation_id: translationId, voice });

/**
 * Kế hoạch tốc độ của lượt lồng GẦN NHẤT — số đo TỪNG dòng cho bảng ở màn Lồng tiếng.
 *
 * `null` = CHƯA lồng lần nào (route trả `null`, không phải 404). Ba câu phải phân biệt được:
 * "chưa có số đo" (`null`), "không có bản dịch" (lỗi HTTP), và "có số đo" (object).
 */
export const getDubPlan = (translationId: number): Promise<DubPlan | null> =>
  api.get<DubPlan | null>(`/dubs/${translationId}/plan`);

/** Đường NGHE THỬ một dòng: wav của take đã ép tốc độ, cắt từ master (route không chạy TTS). */
export const dubTakeUrl = (translationId: number, i: number): string =>
  `/api/dubs/${translationId}/take?i=${i}`;

export const endpoints = {
  makeDub,
  getDubPlan,
  dubTakeUrl,
  listSources,
  getSource,
  uploadSource,
  addSourceUrl,
  deleteSource,
  listJobs,
  getJob,
  cancelJob,
  retryJob,
  createJob,
  listTranscripts,
  getTranscript,
  patchTranscript,
  approveTranscript,
  createTranslation,
  listTranslations,
  getTranslation,
  patchTranslation,
  deleteTranslation,
  listTerms,
  createTerm,
  patchTerm,
  chimeraCost,
  glossaryVersion,
  affectedPreview,
  registry,
  listEngines,
  status,
  mediaUrl,
  getPeaks,
  exportUrl,
};
