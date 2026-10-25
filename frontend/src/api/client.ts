/**
 * Một chỗ DUY NHẤT biết base URL và biết cách biến lỗi HTTP thành lỗi có cấu trúc.
 *
 * `BASE` là đường dẫn TƯƠNG ĐỐI vì trong trình duyệt mọi request đi qua
 * `dev-server.mjs` ở cổng 3100, và nó proxy `/api/*` sang backend 8620. Nhờ vậy
 * không có origin nào bị hard-code trong mã chạy trong trình duyệt, và CORS
 * không bao giờ là chuyện của client này.
 */

export const BASE = "/api";

/**
 * Lỗi HTTP có CẤU TRÚC: `status` để phân nhánh (409 vs 422 vs 404), `detail` để
 * người đọc thấy LÝ DO backend đưa ra.
 *
 * Vì sao không ném `new Error("500")`: `routes_translations.create_translation`
 * phân biệt "engine không có trong registry" (422) với "engine chưa sẵn sàng"
 * (409), và `routes_jobs.retry_job` trả 409 kèm danh sách trạng thái chạy lại
 * được. Nuốt `detail` là biến ba câu trả lời khác nhau thành một câu "lỗi".
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Đọc `detail` ra khỏi body lỗi của FastAPI.
 *
 * Hai hình dạng, cả hai đều thật:
 *   - `HTTPException` (404/409/422 do route tự ném) ⇒ `{"detail": "câu tiếng Việt"}`
 *   - lỗi kiểm dữ liệu của FastAPI (422) ⇒ `{"detail": [{loc, msg, type}, …]}`
 *
 * Mảng bị `JSON.stringify` chứ không bị nuốt: nó nêu ĐÚNG tên trường sai, đúng
 * thứ người dùng cần để sửa.
 */
function detailOf(body: unknown, fallback: string): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const raw = (body as { detail: unknown }).detail;
    if (typeof raw === "string") return raw;
    if (raw !== undefined && raw !== null) return JSON.stringify(raw);
  }
  return fallback;
}

function jsonInit(body: unknown): RequestInit {
  if (body === undefined) return {};
  return { headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

async function call<T>(method: string, path: string, init: RequestInit = {}): Promise<T> {
  // Nhận cả URL TUYỆT ĐỐI: contract test và e2e chạy trong Node, nơi không có
  // `dev-server.mjs` làm proxy, nên chúng phải gọi thẳng 8620. Một dòng, không
  // thêm trạng thái — và trong trình duyệt mọi đường vẫn đi qua `BASE`.
  const url = /^https?:\/\//.test(path) ? path : `${BASE}${path}`;
  const response = await fetch(url, { method, ...init });

  if (!response.ok) {
    // Body lỗi KHÔNG phải lúc nào cũng là JSON (502 của proxy, HTML của một
    // proxy khác) — đọc hỏng thì rơi về `statusText`, không ném thêm một lỗi
    // thứ hai che mất lỗi thật.
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, detailOf(body, response.statusText));
  }

  // 204 (không có thân) không được gọi `json()`: `JSON.parse("")` ném.
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => call<T>("GET", path),
  post: <T>(path: string, body?: unknown) => call<T>("POST", path, jsonInit(body)),
  patch: <T>(path: string, body?: unknown) => call<T>("PATCH", path, jsonInit(body)),
  /**
   * `DELETE` — hai route xoá của backend trả **204 KHÔNG thân**.
   *
   * Vì sao vẫn dùng chung `call`: nó đã phân nhánh `status === 204` ở trên
   * (`response.json()` trên thân rỗng ném `JSON.parse("")`), nên đường xoá thừa
   * hưởng đúng phép kiểm đó thay vì có một bản sao thứ hai của cùng logic. Kiểu
   * trả về là `void` ở nơi gọi (`deleteSource`/`deleteTranslation`), không phải
   * một giá trị bịa ra cho một response không có nội dung.
   */
  del: <T>(path: string) => call<T>("DELETE", path),

  /**
   * Tải tệp lên (`POST /api/sources/upload`) — multipart, KHÔNG đặt
   * `content-type`: trình duyệt phải tự thêm `boundary`, và đặt tay thì body
   * không phân tích được ở phía FastAPI.
   */
  postForm: <T>(path: string, form: FormData) => call<T>("POST", path, { body: form }),
};
