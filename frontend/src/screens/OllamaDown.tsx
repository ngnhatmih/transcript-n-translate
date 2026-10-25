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
 * ⚠️ HAI CÂU KHÁC NHAU, KHÔNG ĐƯỢC GỘP (review Task 10: `Important #1` + `#2`):
 *   - *"Bóc băng vẫn chạy được: …"* — nhóm `kind === "asr" && runtime === "inprocess"`
 *     (phiên âm chạy ngay trên máy, không cần Ollama). ⚠️ Điều kiện `runtime` là **nợ Task 10
 *     đóng kèm ở Task W1**: bản cũ chỉ lọc `kind === "asr"` nên khẳng định *"chạy ngay trên
 *     máy"* cho **MỌI** ASR **bất kể `runtime`** — hôm nay đúng **4/4** chỉ vì cả bốn ASR
 *     trong registry đều `inprocess`. Engine ASR **KHÔNG dịch câu nào**, nên nó không bao
 *     giờ được nằm trong câu "… vẫn **dịch** được" (spec UI §4.8 tách hai câu: *"Bóc băng
 *     vẫn chạy được"* ≠ engine dịch).
 *   - *"Còn/Không dùng được: …"* — nhóm `kind === "mt"`, chia theo `capabilities.available`
 *     mà **BACKEND** đã tính (`app/main.py::_mark_availability`); client ĐỌC THẲNG, và
 *     **thiếu khoá = KHÔNG dùng được** (cùng quy ước với `EngineSelect.tsx`).
 * `runtime` **KHÔNG** được dùng để suy "dùng được": đó là **tính lại ở client** một đại
 * lượng backend đã tính (`Global Constraints`), và hai tiêu chí chỉ TRÙNG kết quả trên dữ
 * liệu hôm nay vì panel chỉ hiện lúc Ollama `down`/`unknown` (`ollama_available()` = ∅).
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
        {/* Ba trạng thái, không phải hai:
            * `status === null` (chưa có phản hồi) ⇒ "chưa đọc được";
            * `vram === null` ⇒ "chưa đo được" — backend trả `null` TƯỜNG MINH khi
              không đọc được card; KHÔNG bịa số, và 0 KHÔNG phải giá trị thay thế
              (0 nói "card trống");
            * có số ⇒ in SỐ + ĐƠN VỊ backend nói (`vram_unit`). Client KHÔNG tự
              thêm đơn vị: `3200` trần trụi là con số vô nghĩa, còn tự gắn "MiB"
              là bịa một thứ backend chưa khẳng định. */}
        {status === null
          ? "chưa đọc được"
          : status.vram === null
            ? "chưa đo được"
            : `${status.vram} ${status.vram_unit}`}
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
  /** Registry đã gộp `asr` + `mt` — nguồn của TÊN engine trong BA câu "bóc băng / còn / không". */
  specs: EngineSpec[];
  /** Đọc lại `/api/status` (nút `[ Thử lại ]` của spec UI §4.8 → `useApi().reload`). */
  onRetry: () => void;
}

export function OllamaDown({ status, specs, onRetry }: OllamaDownProps) {
  // `up` ⇒ KHÔNG có gì để báo. `null` ⇒ CHƯA ĐỌC ĐƯỢC, cũng không được khẳng định gì.
  if (status === null || status.ollama === "up") return null;

  const chuaDo = status.ollama === "unknown";
  // HAI CÂU HỎI KHÁC NHAU, HAI NGUỒN KHÁC NHAU — và KHÔNG được lẫn:
  //   - "engine này phục vụ được NGAY BÂY GIỜ không" ⇒ `capabilities.available`, đại lượng
  //     BACKEND đã tính. Client ĐỌC THẲNG; THIẾU KHOÁ = KHÔNG dùng được (cùng quy ước với
  //     `EngineSelect.tsx:35`). `runtime` KHÔNG quyết định điều đó: `runtime:"ollama"` vẫn có
  //     thể `available:true` (tiến trình sống + model đã pull), và `runtime:"inprocess"` vẫn
  //     có thể `available:false` (model chưa pull) ⇒ suy từ `runtime` là nguồn sự thật thứ hai.
  //   - "engine này chạy Ở ĐÂU" ⇒ `runtime`, và câu *"chạy ngay trên máy"* chỉ đúng cho
  //     `runtime === "inprocess"`. Đo được: hôm nay cả **4/4** ASR trong registry đều
  //     `inprocess`, nên một bản lọc chỉ theo `kind === "asr"` **nói đúng một cách tình cờ** —
  //     một ASR chạy qua Ollama sẽ bị khẳng định "chạy ngay trên máy" trong khi nó cần model
  //     đã pull. Fixture `SPECS_ASR_OLLAMA` trong test ghim đúng ca đó.
  //   - "engine này thuộc BƯỚC nào" ⇒ `kind` (`asr` = bóc băng, `mt` = dịch). ASR không dịch
  //     câu nào nên không được nằm trong câu "… vẫn dịch được" (spec UI §4.8 tách hai câu).
  // ⚠️ Vì sao nhóm `bocBang` lọc thêm `runtime`: câu của nó KHẲNG ĐỊNH một điều kiện chạy
  // ("không cần Ollama"), nên nó phải nói về nhóm engine mà điều kiện đó ĐÚNG. Hệ quả đã
  // biết và khai ra: một ASR `runtime === "ollama"` KHÔNG được nêu tên ở bất kỳ câu nào
  // (nó không phải engine DỊCH, và câu "chạy ngay trên máy" thì không đúng với nó) — không
  // câu nào ở đây khẳng định nó dùng được.
  const bocBang = specs.filter((s) => s.kind === "asr" && s.runtime === "inprocess");
  const con = specs.filter((s) => s.kind === "mt" && s.capabilities.available === true);
  const khong = specs.filter((s) => s.kind === "mt" && s.capabilities.available !== true);

  return (
    /* NỢ Task 10 ĐÓNG KÈM (D2): panel này là một VÙNG THÔNG BÁO — `role="status"` để trình đọc
       màn hình ĐỌC NÓ RA khi nó xuất hiện (panel không phải toast, và nó chỉ hiện khi Ollama không
       dùng được). ⚠️ Spec UI KHÔNG đòi điều này cho §4.8 ⇒ đây là **NỢ**, không phải một vi phạm;
       nhưng một mệnh đề không có gì làm nó sai được thì phải được GHIM (ERRATA #45 mục 1) — nên
       `OllamaDown.test.tsx` khẳng định chính thuộc tính này. */
    <section className="od" role="status" data-ollama={status.ollama}>
      <div className="od__van" aria-hidden />
      <p className="od__tieu-de">
        {chuaDo ? "Chưa đo được Ollama" : "Không kết nối được Ollama"}
      </p>
      <p className="od__ly-do">
        {chuaDo
          ? "Chưa đo được: không có tín hiệu trả lời từ Ollama. Đây KHÁC với \"đã tắt\" — chưa đo được thì chưa kết luận được là nó tắt."
          : "Ollama không trả lời hoặc đã tắt, nên mọi engine cần nó đều không dịch được ngay bây giờ."}
      </p>
      <p className="od__boc-bang">
        Bóc băng vẫn chạy được: {lietKe(bocBang)} — bước phiên âm chạy ngay trên máy, không cần Ollama.
      </p>
      {/* Câu DỊCH chỉ nói về engine `kind === "mt"`. "Vì sao" và "cách sửa" nằm ở
          `.od__ly-do`/`.od__sua` — ở đây KHÔNG suy lại nguyên nhân từ `runtime`. */}
      <p className="od__con">
        Còn dùng được: {lietKe(con)} — những engine dịch này vẫn dịch được ngay bây giờ.
      </p>
      <p className="od__khong">
        Không dùng được: {lietKe(khong)} — những engine dịch này chưa dịch được ngay bây giờ.
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
