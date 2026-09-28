/**
 * `<StatusStrip/>` + `<OllamaDown/>` — **§4.8 Trạng thái Ollama, HẠNG NHẤT** (spec UI
 * §4.8: "không phải toast"; lý do: đây là lỗi phổ biến nhất của một app local, và app
 * *không dùng được* nếu thiếu — một toast bay qua rồi biến mất là thiết kế sai).
 *
 * HAI THỨ trong một mô-đun, vì chúng là hai hình dạng của CÙNG một trạng thái đọc từ
 * CÙNG một lượt `/api/status`:
 *   - `StatusStrip` — dải luôn hiện ở header (Ollama / VRAM / giai đoạn đang chạy);
 *   - `OllamaDown`  — panel ở đỉnh cửa sổ, chỉ hiện khi Ollama **không dùng được**.
 *
 * ⚠️ BA TRẠNG THÁI, HAI CÁI LÀ "KHÔNG DÙNG ĐƯỢC", VÀ CHÚNG KHÁC NHAU:
 * `probe_ollama` trả `up` / `down` / `unknown`. `unknown` là giá trị **THẬT** ("chưa đo
 * được": cổng **timeout**, chưa phân giải được) — **KHÔNG** phải "đang tắt". Trên máy này
 * `/api/status` đã trả **`unknown`** (Task 2, 3/3 lần) và **`up`** (re-review, lúc Ollama
 * chạy); **`down`** (cổng **refused**) **chưa từng** đo được (ERRATA #2 mục 4).
 * ⇒ Nếu panel chỉ hiện với `down` thì **trên máy này nó KHÔNG BAO GIỜ hiện** (plan dòng
 * 2737) — và biến `unknown` thành `down` để "cho nó hiện" là **bịa một sự thật chưa đo**
 * (docstring `probe_ollama` trong `backend/app/api/routes_registry.py`).
 * ⇒ `unknown` có **tiêu đề riêng** và nói rõ "chưa đo được"; `data-ollama` giữ nguyên giá
 * trị thật để CSS và bài test không gộp hai thứ làm một.
 *
 * ⚠️ `status === null` (chưa đọc xong / lỗi mạng) là trạng thái THỨ BA về phía client, và
 * nó KHÁC cả hai: không có dữ liệu thì panel **không khẳng định gì** (render `null`).
 *
 * Dữ liệu vào qua **PROP**: `App` là nơi DUY NHẤT gọi `/api/status` và `/api/registry`
 * (`useApi` không cache — hai nơi gọi là hai lượt đọc, hai nguồn sự thật).
 */
import type { EngineSpec, OllamaState, Status } from "../api/types.ts";

const NHAN_OLLAMA: Record<OllamaState, string> = {
  up: "đang chạy",
  down: "mất kết nối",
  unknown: "chưa đo được",
};

/** Dải luôn hiện ở header: Ollama / VRAM / giai đoạn đang chạy (spec UI §3 dòng 154). */
export function StatusStrip({ status }: { status: Status | null }) {
  const ollama = status === null ? null : status.ollama;
  return (
    <div className="stt" data-ollama={ollama ?? "chua-doc-duoc"}>
      <span className="stt__ollama">
        <span className="stt__cham" aria-hidden />
        {"Ollama: "}
        {ollama === null ? "chưa đọc được" : NHAN_OLLAMA[ollama]}
      </span>
      <span className="stt__vram">
        {"VRAM: "}
        {/* GĐ1a: backend trả `null` TƯỜNG MINH (chưa có API đọc VRAM) — "chưa đo được",
            không được bịa một con số. Khi có số thì in SỐ; client KHÔNG tự thêm đơn vị
            mà backend không nói. */}
        {status === null || status.vram === null ? "chưa đo được" : String(status.vram)}
      </span>
      <span className="stt__gd">
        {"GĐ: "}
        {status === null || status.current_phase === null ? "chưa chạy gì" : status.current_phase}
      </span>
    </div>
  );
}

/** Liệt kê tên engine cho câu văn; danh sách rỗng phải NÓI RA, không để trống. */
function lietKe(ds: EngineSpec[]): string {
  return ds.length === 0 ? "không có engine nào" : ds.map((s) => s.label).join(", ");
}

export interface OllamaDownProps {
  status: Status | null;
  /** Registry đã gộp `asr` + `mt` — nguồn của TÊN engine trong hai câu "còn/không". */
  specs: EngineSpec[];
  /** Đọc lại `/api/status` (nút `[ Thử lại ]` của spec UI §4.8 → `useApi().reload`). */
  onRetry: () => void;
}

export function OllamaDown({ status, specs, onRetry }: OllamaDownProps) {
  // `up` ⇒ KHÔNG có gì để báo. `null` ⇒ CHƯA ĐỌC ĐƯỢC, cũng không được khẳng định gì.
  if (status === null || status.ollama === "up") return null;

  const chuaDo = status.ollama === "unknown";
  // `runtime` ở đây chỉ dùng để CHỌN CÂU (engine nào cần Ollama), KHÔNG dùng để suy
  // `available` — hai đại lượng khác nhau, xem `EngineSelect`.
  const con = specs.filter((s) => s.runtime === "inprocess");
  const khong = specs.filter((s) => s.runtime === "ollama");

  return (
    <section className="od" data-ollama={status.ollama}>
      <div className="od__van" aria-hidden />
      <p className="od__tieu-de">
        {chuaDo ? "Chưa đo được Ollama" : "Không kết nối được Ollama"}
      </p>
      <p className="od__ly-do">
        {chuaDo
          ? "Chưa đo được: không có tín hiệu trả lời từ Ollama. Đây KHÁC với \"đã tắt\" — chưa đo được thì chưa kết luận được là nó tắt."
          : "Ollama không trả lời hoặc đã tắt, nên mọi engine cần nó đều không dịch được ngay bây giờ."}
      </p>
      <p className="od__con">
        Còn dùng được: {lietKe(con)} — engine in-process (không cần Ollama) vẫn dịch được.
      </p>
      <p className="od__khong">
        Không dùng được: {lietKe(khong)} — engine cần Ollama không dịch được.
      </p>
      <p className="od__sua">
        Cách sửa: mở terminal và chạy <code>ollama serve</code>, rồi bấm Thử lại.
      </p>
      <button className="od__thu-lai" type="button" data-testid="od-thu-lai" onClick={onRetry}>
        Thử lại
      </button>
    </section>
  );
}
