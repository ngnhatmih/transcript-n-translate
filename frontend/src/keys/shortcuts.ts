/**
 * BẢNG PHÍM TẮT — **DỮ LIỆU**, không phải một chuỗi `if`/`switch` trong listener.
 *
 * Vì sao là một BẢNG (spec UI §11.4 là YÊU CẦU, không phải điểm cộng):
 *  1. `resolveKey` tra bảng ⇒ thêm/đổi phím là sửa DỮ LIỆU, và mọi hàng đo được độc lập;
 *  2. bảng phím tắt §11.4 **render từ chính bảng này** (`src/keys/BangPhim.tsx`) ⇒ nội dung
 *     hiển thị và hành vi thật **KHÔNG THỂ lệch nhau** — hai bản chép tay là hai nguồn sự thật,
 *     và bản thứ hai sẽ trôi (ERRATA #43 mục 2: "ghim QUAN HỆ, không ghim CHỮ").
 *
 * 🔴 NGUỒN CÓ THẨM QUYỀN LÀ SPEC UI §5.1 (bảng), KHÔNG phải brief D1 (ERRATA #44 mục 3):
 *   - `[`/`]` = **đặt mốc start/end TẠI ĐẦU ĐỌC** (spec §5.1 dòng 296, §5.2 dòng 310);
 *   - nudge = **`Shift+←/→` ±0,1 s** và **`Alt+←/→` ±1 s** (spec §5.1 dòng 300–301, §5.2 dòng 309).
 *   Đến trước task này, `App.tsx` gọi `nudgeDoan("start"/"end")` cho `[`/`]` — tức bảng phím của
 *   sản phẩm lệch nguồn spec ở ĐÚNG hai hàng này.
 *
 * Từ vựng `KeyAction` là **RIÊNG CỦA BÀN PHÍM**, KHÔNG phải `Action` của `state/reducer.ts`
 * (ERRATA #33 mục 1): `UiState` có bảy trường phẳng và **không** trường nào chứa mốc thời gian,
 * nên một hành động như `nudge` không thể là action của reducer — nó phải đi qua ĐƯỜNG GHI thật
 * (`App.xepHangGhi` → `PATCH /api/transcripts/{id}`).
 *
 * HAI LOẠI KHOÁ, phân biệt có chủ ý:
 *  - **PHÍM CHỮ/SỐ/MŨI TÊN** tra theo `key` + ĐÚNG các phím bổ trợ (`ctrl`/`alt`/`shift` phải khớp
 *    cả hai chiều: hàng khai `shift: true` thì sự kiện không được có `shift: false`, và ngược lại).
 *  - **PHÍM KÝ TỰ DẤU** (`?`, `[`, `]`) thì `shift` **KHÔNG** là khoá tra: `KeyboardEvent.key` đã
 *    mã hoá ký tự, và `?` là `Shift+/` trên bàn phím Mỹ nhưng là một phím trần trên layout khác.
 *    `metaKey` cũng KHÔNG được tra — spec ghi `Ctrl`; macOS dùng `Cmd` là **TRẦN đã khai**.
 */
import type { Mode } from "../state/reducer.ts";

/**
 * Từ vựng hành động của BÀN PHÍM.
 *
 * ⚠️ `by` của `nudge` là **GIÂY** (`-0,1` · `+0,1` · `-1` · `+1`), không phải "số bước": giá trị
 * này được CỘNG thẳng vào `Segment.start`/`end` trong `App.nudgeDoan`, nên đơn vị của nó phải là
 * đơn vị của mốc thời gian. (Plan Task 11 Step 1 viết `by: -1` / `by: -10` cho hai độ lớn 0,1 s và
 * 1 s — cùng hai độ lớn, khác đơn vị ghi; xem báo cáo task-11 §"lệch brief".)
 */
export type KeyAction =
  | { type: "togglePlay" }
  | { type: "segmentPrev" }
  | { type: "segmentNext" }
  | { type: "nextSuspect" }
  | { type: "startEdit" }
  | { type: "endEdit" }
  | { type: "setMode"; mode: Mode }
  | { type: "setEdgeAtPlayhead"; edge: "start" | "end" }
  | { type: "nudge"; edge: "start" | "end"; by: number }
  | { type: "splitAtPlayhead" }
  | { type: "mergeWithNext" }
  | { type: "runJob" }
  | { type: "toggleShortcuts" };

/**
 * Một sự kiện phím TỐI THIỂU — đúng năm khoá mà bảng đọc.
 *
 * Cố ý KHÔNG nhận `KeyboardEvent`: `resolveKey` phải THUẦN (không DOM), và một `KeyboardEvent`
 * thật thoả mãn interface này bằng cấu trúc. Nhờ vậy bài test không cần `as` và cũng không cần
 * một `document` nào.
 */
export interface PhimBam {
  key: string;
  ctrlKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  metaKey: boolean;
}

/** Một HÀNG của bảng: khoá tra (phím + phím bổ trợ + chế độ) và hai thứ để IN RA. */
export interface PhimTat {
  /** `KeyboardEvent.key` — `" "` cho Space, `"ArrowLeft"` cho mũi tên. */
  key: string;
  /** Bắt buộc có `Ctrl` (spec: `Ctrl+1/2/3`, `Ctrl+Enter`). */
  ctrl?: boolean;
  /** Bắt buộc có `Alt` (spec: `Alt+←/→`). */
  alt?: boolean;
  /** Bắt buộc có `Shift` (spec: `Shift+←/→`). Bỏ trống với phím KÝ TỰ DẤU — xem đầu tệp. */
  shift?: boolean;
  /** Chỉ có hiệu lực ở CHẾ ĐỘ này. Bỏ trống = mọi chế độ (Space, chọn đoạn, đổi chế độ, bảng phím, `Esc`). */
  mode?: Mode;
  /** NHÃN in ra bảng §11.4 — chữ người dùng đọc, không phải `key` của trình duyệt. */
  toHop: string;
  /** VIỆC nó làm — cột "Việc" của spec §5.1. */
  viec: string;
  action: KeyAction;
}

/**
 * BẢNG PHÍM — chép từ bảng §5.1 của spec UI, **mỗi hàng MỘT phím**.
 *
 * ⚠️ Spec ghi gộp (`Shift+←/→`, `Ctrl+1/2/3`); ở đây tách thành một hàng cho mỗi phím vì đó là
 * đơn vị mà `resolveKey` tra được và đơn vị mà bài test ghim được. Cột "Việc" giữ nguyên chữ của
 * spec cho từng vế.
 *
 * ⚠️ HAI LOẠI HÀNG, và loại thứ hai phải NÓI RA:
 *  - phím có ĐÍCH THẬT trong sản phẩm — nằm trong `DA_NOI`;
 *  - phím **spec CÓ mà sản phẩm CHƯA có đích** (`S` tách dòng, `M` gộp dòng, `Ctrl+Enter` chạy job):
 *    `resolveKey` VẪN trả hành động (bảng §11.4 phải phủ §5.1), nhưng `App` **không nối**, và
 *    `BangPhim` in dấu `chưa nối` cho đúng những hàng đó. Dấu đó lấy từ `DA_NOI` — nguồn duy nhất.
 *
 * Hàng `?` KHÔNG có trong bảng §5.1: spec §11.4 đòi bảng phím tắt phải TỒN TẠI nhưng không ghi
 * phím nào mở nó. `?` là lựa chọn của task này (quy ước chung của công cụ), và nó nằm ngay trong
 * bảng để bảng tự khai mình.
 *
 * 🔴 HÀNG `Esc` KHÔNG CÓ `mode` (vòng sửa 1, `I-1`) — và đây là một ĐÍNH CHÍNH, không phải một
 * nới lỏng: `?` mở bảng §11.4 ở **MỌI** chế độ, nên `Esc` phải tra ra ở **MỌI** chế độ, nếu không
 * thì lớp phủ `aria-modal` **không đóng được bằng bàn phím ở 2/3 chế độ** (đo trong Chrome thật:
 * ở `edit` thì đóng, ở `glossary` thì vẫn mở). Việc `Esc` làm gì khi bảng đang mở do `App` quyết
 * (`case "endEdit"`: đóng bảng trước, `Esc` lần hai mới thoát ô sửa), nên hàng DỮ LIỆU chỉ cần
 * tra ra; nhãn `viec` phải nói cả hai việc, vì bảng §11.4 in chính nhãn đó.
 * ⚠️ Vế "phím của màn Biên tập không bắn ở màn khác" VẪN ĐÚNG cho `[`, `]`, `Enter`, nudge, `S`,
 * `M` — chúng chỉ có nghĩa khi có một dòng ĐANG SỬA.
 */
export const BANG_PHIM: readonly PhimTat[] = [
  { key: " ", toHop: "Space", viec: "phát / dừng", action: { type: "togglePlay" } },
  { key: "j", toHop: "J", viec: "dòng trước", action: { type: "segmentPrev" } },
  { key: "k", toHop: "K", viec: "dòng sau", action: { type: "segmentNext" } },
  {
    key: "Enter",
    mode: "edit",
    toHop: "Enter",
    viec: "sửa dòng đang chọn",
    action: { type: "startEdit" },
  },
  {
    key: "Escape",
    toHop: "Esc",
    viec: "thoát sửa / đóng bảng phím tắt",
    action: { type: "endEdit" },
  },
  {
    key: "[",
    mode: "edit",
    toHop: "[",
    viec: "đặt mốc start tại đầu đọc",
    action: { type: "setEdgeAtPlayhead", edge: "start" },
  },
  {
    key: "]",
    mode: "edit",
    toHop: "]",
    viec: "đặt mốc end tại đầu đọc",
    action: { type: "setEdgeAtPlayhead", edge: "end" },
  },
  {
    key: "ArrowLeft",
    shift: true,
    mode: "edit",
    toHop: "Shift+←",
    viec: "nudge mốc thời gian ±0,1s",
    action: { type: "nudge", edge: "start", by: -0.1 },
  },
  {
    key: "ArrowRight",
    shift: true,
    mode: "edit",
    toHop: "Shift+→",
    viec: "nudge mốc thời gian ±0,1s",
    action: { type: "nudge", edge: "end", by: 0.1 },
  },
  {
    key: "ArrowLeft",
    alt: true,
    mode: "edit",
    toHop: "Alt+←",
    viec: "nudge ±1s",
    action: { type: "nudge", edge: "start", by: -1 },
  },
  {
    key: "ArrowRight",
    alt: true,
    mode: "edit",
    toHop: "Alt+→",
    viec: "nudge ±1s",
    action: { type: "nudge", edge: "end", by: 1 },
  },
  {
    key: "s",
    mode: "edit",
    toHop: "S",
    viec: "tách dòng tại đầu đọc",
    action: { type: "splitAtPlayhead" },
  },
  {
    key: "m",
    mode: "edit",
    toHop: "M",
    viec: "gộp với dòng dưới",
    action: { type: "mergeWithNext" },
  },
  {
    key: "n",
    toHop: "N",
    viec: "nhảy tới đoạn nghi ngờ kế tiếp",
    action: { type: "nextSuspect" },
  },
  {
    key: "1",
    ctrl: true,
    toHop: "Ctrl+1",
    viec: "Biên tập",
    action: { type: "setMode", mode: "edit" },
  },
  {
    key: "2",
    ctrl: true,
    toHop: "Ctrl+2",
    viec: "Đối chiếu",
    action: { type: "setMode", mode: "compare" },
  },
  {
    key: "3",
    ctrl: true,
    toHop: "Ctrl+3",
    viec: "Thuật ngữ",
    action: { type: "setMode", mode: "glossary" },
  },
  {
    key: "Enter",
    ctrl: true,
    toHop: "Ctrl+Enter",
    viec: "chạy job cho kênh đang chọn",
    action: { type: "runJob" },
  },
  {
    key: "?",
    toHop: "?",
    viec: "mở / đóng bảng phím tắt",
    action: { type: "toggleShortcuts" },
  },
];

/**
 * Những loại hành động mà `App` **THẬT SỰ NỐI** với một đường có đích.
 *
 * Vì sao cần một danh sách riêng thay vì `action: null`: brief đòi `resolveKey` **vẫn trả hành
 * động** cho phím spec ghi mà sản phẩm chưa có đích (nếu trả `null` thì bảng §11.4 sẽ âm thầm
 * thiếu hàng, hoặc tệ hơn: phải chép tay một bảng thứ hai để in). Danh sách này là **NGUỒN DUY
 * NHẤT** cho dấu `chưa nối` trên bảng, và nó có bài ghim HAI CHIỀU:
 *  - `shortcuts.test.ts`: hàng nào không thuộc `DA_NOI` thì phải là đúng ba phím đã khai;
 *  - `App.test.tsx` (`T11 PHÍM CHƯA CÓ ĐÍCH`): bấm đúng những phím đó ⇒ **0 request** và DOM không
 *    đổi. Nếu một phím trong số đó được nối thêm mà QUÊN bỏ khỏi `DA_NOI`, bài đó ĐỎ (bảng đang
 *    nói dối).
 */
export const DA_NOI: ReadonlySet<KeyAction["type"]> = new Set<KeyAction["type"]>([
  "togglePlay",
  "segmentPrev",
  "segmentNext",
  "nextSuspect",
  "startEdit",
  "endEdit",
  "setMode",
  "setEdgeAtPlayhead",
  "nudge",
  "toggleShortcuts",
]);

/** Phím KÝ TỰ DẤU: `key` đã mã hoá ký tự ⇒ `Shift` không phải khoá tra (xem đầu tệp). */
function laKyTuDau(key: string): boolean {
  return key.length === 1 && !/[a-z0-9]/i.test(key);
}

/** Một hàng có khớp sự kiện này không — khớp CẢ HAI CHIỀU trên `ctrl`/`alt`/`shift`. */
function khop(pt: PhimTat, suKien: PhimBam, mode: Mode): boolean {
  if (pt.key !== suKien.key) return false;
  if ((pt.ctrl ?? false) !== suKien.ctrlKey) return false;
  if ((pt.alt ?? false) !== suKien.altKey) return false;
  if (!laKyTuDau(pt.key) && (pt.shift ?? false) !== suKien.shiftKey) return false;
  return pt.mode === undefined || pt.mode === mode;
}

/**
 * TRA một sự kiện phím thành hành động, hoặc `null`.
 *
 * THUẦN: không DOM, không `document`, không React. `inField` là **tham số**, không phải một lần
 * đọc `document.activeElement` ở đây — phép đọc đó thuộc `useShortcuts`, và hai vế đó có hai
 * mutant ĐỘC LẬP (`P1`: bỏ nhánh `inField`; `P2`: bỏ lần đọc `activeElement`).
 *
 * `mode` là một phần của KHOÁ TRA: phím của màn Biên tập (`Enter`, `[`, `]`, nudge, `S`, `M`)
 * chỉ có hiệu lực ở `mode === "edit"` — `setMode` KHÔNG xoá `editingSegment`, nên một listener
 * không lọc `mode` vẫn còn "một dòng đang sửa" trong state khi người dùng đã sang màn khác, và một
 * phím `[` ở đó là một lượt GHI mà màn hình không hề hiện ô sửa nào.
 * ⚠️ `Esc` là NGOẠI LỆ CÓ CHỦ Ý (vòng sửa 1, `I-1`): bảng §11.4 mở được ở mọi chế độ nên `Esc`
 * phải tra ra ở mọi chế độ — xem docblock của `BANG_PHIM`.
 */
export function resolveKey(suKien: PhimBam, mode: Mode, inField: boolean): KeyAction | null {
  // Ô NHẬP ĐƯỢC ƯU TIÊN TUYỆT ĐỐI: người dùng đang gõ phụ đề, không phải đang điều khiển app.
  if (inField) return null;
  for (const pt of BANG_PHIM) {
    if (khop(pt, suKien, mode)) return pt.action;
  }
  return null;
}
