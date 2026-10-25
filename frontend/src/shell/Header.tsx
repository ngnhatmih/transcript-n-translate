/**
 * Dải trên cùng của khung ba vùng (spec UI §3).
 *
 * Task 10 nối `StatusStrip` (§4.8: Ollama / VRAM / giai đoạn đang chạy) vào đây. Dữ liệu
 * vào qua **PROP**, và `Header` **KHÔNG** tự gọi API: `App` là nơi DUY NHẤT đọc
 * `/api/status` cho cả dải lẫn panel — hai nơi gọi cùng một endpoint là hai lượt đọc và
 * hai nguồn sự thật cho cùng một hàng dữ liệu (`useApi` không cache).
 *
 * KHÔNG in `queue_depth` ở đây: đó là đại lượng backend đã tính và HÀNG ĐỢI đã hiện
 * (`Global Constraints`: CPS, `available`, số bản dịch bị ảnh hưởng — cùng một lớp lỗi).
 *
 * ## Bộ chọn CHẾ ĐỘ (Task W1) — và vì sao nó là ba `input` NATIVE
 *
 * Trước W1, `mode` của reducer **không có đường nào đổi**: đo được `setMode` **0 lượt
 * dispatch** ⇒ màn Đối chiếu và tab Thuật ngữ **không tới được** trong app thật (ERRATA #32),
 * và Task 12 click một `radio` **không tồn tại**.
 *
 * Ba lựa chọn ở đây là **`<input type="radio">` THẬT** trong một `role="radiogroup"`, KHÔNG
 * phải `div` + `role="radio"`: chỉ `input` native mới có hành vi bàn phím của nhóm radio
 * (Tab vào nhóm, mũi tên đổi lựa chọn trong cùng `name`), và spec UI §12.5 ĐÒI bàn phím
 * làm được toàn bộ phần biên tập. Một `div role="radio"` sẽ qua được bài "có radio" mà
 * **mất bàn phím native** — nên bài test ghim cả `tagName === "INPUT"`.
 *
 * `checked` theo PROP `mode` và `onChange` chỉ **BÁO VỀ** `onModeChange`: `Header` là
 * component ĐIỀU KHIỂN, không giữ bản sao thứ hai của `UiState.mode` (cùng lý do `Transport`
 * không giữ bản sao của `playing` — một tầng trạng thái thứ hai là một tầng sẽ trôi).
 */
import type { Status } from "../api/types.ts";
import type { Mode } from "../state/reducer.ts";
import { StatusStrip } from "../screens/OllamaDown.tsx";

/** Ba chế độ của spec UI §3, theo THỨ TỰ hiển thị. Nhãn là chữ người dùng đọc. */
const BA_CHE_DO: ReadonlyArray<{ mode: Mode; nhan: string }> = [
  { mode: "edit", nhan: "Biên tập" },
  { mode: "compare", nhan: "Đối chiếu" },
  { mode: "glossary", nhan: "Thuật ngữ" },
];

export interface HeaderProps {
  status: Status | null;
  /** `UiState.mode` — chế độ đang hiện ở vùng giữa. */
  mode: Mode;
  /** Yêu cầu đổi chế độ — BEN GOI giu su that (reducer). */
  onModeChange: (mode: Mode) => void;
}

export function Header({ status, mode, onModeChange }: HeaderProps) {
  return (
    <header className="shell__head">
      <h1 className="head__ten">PHÒNG THU BIÊN TẬP</h1>
      {/* `name` chung là thứ biến ba `input` thành MỘT nhóm radio của trình duyệt (mũi tên
          di chuyển trong nhóm). `htmlFor` + `id` để bấm được vào chữ, và để TÊN ĐỌC ĐƯỢC
          của radio là nhãn — đó cũng là cách Task 12 tìm control này. */}
      <div className="cd" role="radiogroup" aria-label="Chế độ làm việc">
        {BA_CHE_DO.map(({ mode: cheDo, nhan }) => (
          <span key={cheDo} className="cd__o">
            <input
              className="cd__radio"
              type="radio"
              id={`che-do-${cheDo}`}
              name="che-do"
              value={cheDo}
              checked={mode === cheDo}
              onChange={() => onModeChange(cheDo)}
            />
            <label className="cd__nhan" htmlFor={`che-do-${cheDo}`}>{nhan}</label>
          </span>
        ))}
      </div>
      <StatusStrip status={status} />
    </header>
  );
}
