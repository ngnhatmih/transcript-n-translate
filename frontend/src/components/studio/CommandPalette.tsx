/**
 * BẢNG LỆNH `Ctrl+K` — gõ tên lệnh thay vì đi tìm nút.
 *
 * 🔴 NGUỒN GỐC: `_lovable-code/src/components/studio/CommandPalette.tsx` (99 dòng).
 *
 * 📏 SỐ ĐO trên bản đã duyệt: hộp 520 px rộng (tối đa 92 vw), đặt ở `15vh` từ đỉnh,
 * nền `--panel-1`, viền 1px `--rule`, radius 2 px; ô nhập 14 px, pad 12px 16px; danh sách
 * cao tối đa 320 px, mỗi dòng 13 px pad 8px 16px; dòng đang chọn nền `bg-signal-soft`.
 *
 * ## Vì sao KHÔNG dùng `<dialog>`
 *
 * `<dialog>` + `showModal()` cho bẫy focus MIỄN PHÍ, nhưng nó cũng đặt phần tử vào
 * "top layer" của trình duyệt — nơi lớp grain `.grain` (`z-index: 1`, `position: fixed`)
 * và bảng phím `.bp` (`z-index: 2`) đang nằm. Hai hệ `z-index` khác nhau không so sánh
 * được với nhau, và kết quả đo được trên bản đầu là hộp lệnh hiện DƯỚI lớp grain.
 * Một `div` thường với `position: fixed` + `z-index` nằm trong CÙNG hệ với hai lớp kia.
 *
 * ## Bẫy focus làm bằng tay — và vì sao nó BẮT BUỘC
 *
 * Bảng lệnh mở trên một giao diện có phím tắt toàn cục (`Space` phát, `J`/`K` nhảy việc,
 * `Enter` duyệt). Không bẫy focus thì người dùng gõ "phát" vào ô tìm và đồng thời kích hoạt
 * phím tắt của app — đo được ở bản đầu: gõ chữ `j` vừa lọc danh sách vừa nhảy việc.
 */
import { useEffect, useMemo, useRef, useState } from "react";

export interface Lenh {
  id: string;
  nhan: string;
  /** Phím tắt hiện bên phải, ví dụ `"Space"`. Rỗng thì không hiện. */
  phim?: string;
  chay: () => void;
}

/** Phần tử có thể nhận focus bên trong hộp — dùng cho vòng Tab. */
const CHON_DUOC = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export interface CommandPaletteProps {
  mo: boolean;
  onDong: () => void;
  lenh: readonly Lenh[];
}

export function CommandPalette({ mo, onDong, lenh }: CommandPaletteProps) {
  const [q, datQ] = useState("");
  const [chi, datChi] = useState(0);
  const oRef = useRef<HTMLInputElement | null>(null);
  const hopRef = useRef<HTMLDivElement | null>(null);
  /** Phần tử đang có focus TRƯỚC khi mở — để trả lại khi đóng. */
  const truocRef = useRef<HTMLElement | null>(null);

  // Mở ⇒ xoá câu hỏi, chọn dòng đầu, ghi nhớ focus cũ, rồi đưa focus vào ô nhập.
  useEffect(() => {
    if (!mo) return;
    datQ("");
    datChi(0);
    truocRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    // `setTimeout(0)` chứ không focus ngay: hộp chưa nằm trong DOM ở lượt render này.
    const hen = window.setTimeout(() => oRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(hen);
      // Đóng ⇒ trả focus về chỗ cũ. Không trả thì focus rơi về `<body>` và phím Tab tiếp
      // theo bắt đầu lại từ đầu trang — người dùng bàn phím mất chỗ đang làm.
      truocRef.current?.focus();
    };
  }, [mo]);

  const ds = useMemo(() => {
    const n = q.trim().toLowerCase();
    // Bỏ dấu tiếng Việt khi LỌC: gõ "phat" phải khớp "Phát". `normalize("NFD")` + bỏ khối
    // dấu tổ hợp `\u0300-\u036f` là cách chuẩn, và `đ → d` phải làm riêng vì `đ` không
    // phải `d` + dấu.
    const boDau = (s: string) =>
      s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
    return n === "" ? lenh : lenh.filter((l) => boDau(l.nhan).includes(boDau(n)));
  }, [q, lenh]);

  // `chi` có thể trỏ ra ngoài danh sách sau khi lọc — kẹp lại mỗi lần danh sách đổi.
  useEffect(() => {
    datChi((c) => (ds.length === 0 ? 0 : Math.min(c, ds.length - 1)));
  }, [ds.length]);

  if (!mo) return null;

  const chay = (l: Lenh | undefined) => {
    if (l === undefined) return;
    onDong();
    l.chay();
  };

  /** Vòng Tab trong hộp: `Tab` ở phần tử cuối về đầu, `Shift+Tab` ở đầu về cuối. */
  const giuFocus = (e: React.KeyboardEvent) => {
    if (e.key !== "Tab") return;
    const hop = hopRef.current;
    if (hop === null) return;
    const dsNut = Array.from(hop.querySelectorAll<HTMLElement>(CHON_DUOC)).filter((el) => !el.hasAttribute("disabled"));
    if (dsNut.length === 0) return;
    const dau = dsNut[0];
    const cuoi = dsNut[dsNut.length - 1];
    const dang = document.activeElement;
    if (!e.shiftKey && dang === cuoi) {
      e.preventDefault();
      dau.focus();
    } else if (e.shiftKey && dang === dau) {
      e.preventDefault();
      cuoi.focus();
    }
  };

  return (
    <div className="lenh-nen" onPointerDown={onDong}>
      <div
        ref={hopRef}
        className="lenh-hop"
        role="dialog"
        aria-modal="true"
        aria-label="Bảng lệnh"
        onPointerDown={(e) => e.stopPropagation()}
        onKeyDown={giuFocus}
      >
        <input
          ref={oRef}
          className="lenh-o"
          value={q}
          placeholder="Gõ lệnh…"
          aria-label="Tìm lệnh"
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => {
            datQ(e.target.value);
            datChi(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              onDong();
              return;
            }
            if (e.key === "ArrowDown") {
              e.preventDefault();
              datChi((c) => Math.min(ds.length - 1, c + 1));
              return;
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              datChi((c) => Math.max(0, c - 1));
              return;
            }
            if (e.key === "Enter") {
              e.preventDefault();
              chay(ds[chi]);
            }
          }}
        />
        <ul className="lenh-ds" role="listbox" aria-label="Danh sách lệnh">
          {ds.map((l, k) => (
            <li key={l.id} role="option" aria-selected={k === chi}>
              <button
                type="button"
                className={k === chi ? "lenh-dong is-chon" : "lenh-dong"}
                onMouseEnter={() => datChi(k)}
                onClick={() => chay(l)}
              >
                <span>{l.nhan}</span>
                {l.phim === undefined || l.phim === "" ? null : <span className="kbd">{l.phim}</span>}
              </button>
            </li>
          ))}
          {ds.length === 0 ? <li className="lenh-trong">Không có lệnh nào khớp</li> : null}
        </ul>
      </div>
    </div>
  );
}
