import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * HAI ĐIỀU KHIỂN CỦA BẢNG "CÀI ĐẶT MODEL" — viết tay, không dùng `<select>`/`<input
 * type=radio>` trần.
 *
 * Vì sao `<select>` trần không đủ: danh sách xổ xuống của nó do HỆ ĐIỀU HÀNH vẽ, nên
 * `background`, `border-radius`, cỡ chữ và màu hover đều nằm ngoài tầm CSS — trên Windows
 * nó ra một hộp xám bo tròn của Chrome, lạc hẳn khỏi bảng graphite 2 px của ứng dụng. Muốn
 * danh sách mang đúng token của app thì phải tự vẽ `listbox`.
 *
 * Đổi lại, tôi phải tự lo phần mà `<select>` cho sẵn: bàn phím, `aria`, đóng khi bấm ra
 * ngoài. Ba thứ đó nằm trong `ChonModel` dưới đây, không rải ra nơi gọi.
 */

export interface LuaChon {
  id: string;
  label: string;
  available: boolean;
}

/** Ô chọn kiểu bảng đặc tả: một hàng có viền, danh sách xổ xuống vẽ bằng token của app. */
export function ChonModel({
  nhan,
  giaTri,
  ungVien,
  onChon,
  choPhepRong = false,
  nhanRong = "— không đặt —",
}: {
  /** `aria-label` của nút mở — cũng là thứ test bám vào. */
  nhan: string;
  giaTri: string;
  ungVien: LuaChon[];
  onChon: (id: string) => void;
  choPhepRong?: boolean;
  nhanRong?: string;
}) {
  const [mo, setMo] = useState(false);
  const nutRef = useRef<HTMLButtonElement>(null);
  const [viTri, setViTri] = useState({ left: 0, top: 0, width: 0 });

  const dangChon = ungVien.find((u) => u.id === giaTri);
  const chu = dangChon?.label ?? (giaTri === "" ? nhanRong : giaTri);

  //: Danh sách xổ xuống nằm trong PORTAL, không phải trong khung cuộn: khung của bảng có
  //: `overflow-y-auto`, nên một `absolute` bên trong sẽ bị CẮT ở đáy khung — đúng lúc chọn
  //: việc cuối cùng thì danh sách cụt. Đo bằng `getBoundingClientRect` của nút.
  useLayoutEffect(() => {
    if (!mo) return;
    const r = nutRef.current?.getBoundingClientRect();
    if (r === undefined) return;
    setViTri({ left: r.left, top: r.bottom + 4, width: r.width });
  }, [mo]);

  //: Đóng khi bấm ra ngoài / nhấn Escape. Đăng ký ở `document` (capture) để bấm vào một ô
  //: khác trong bảng cũng đóng ô này trước khi ô kia mở.
  useEffect(() => {
    if (!mo) return;
    const ngoai = (e: MouseEvent) => {
      const t = e.target as Node | null;
      if (t !== null && nutRef.current?.contains(t)) return;
      if (t !== null && (t as HTMLElement).closest?.("[data-chon-model]") !== null) return;
      setMo(false);
    };
    const phim = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();     // Escape đóng DANH SÁCH, không đóng cả bảng
        setMo(false);
      }
    };
    document.addEventListener("mousedown", ngoai, true);
    document.addEventListener("keydown", phim, true);
    return () => {
      document.removeEventListener("mousedown", ngoai, true);
      document.removeEventListener("keydown", phim, true);
    };
  }, [mo]);

  const chon = (id: string) => {
    onChon(id);
    setMo(false);
  };

  const muc = choPhepRong
    ? [{ id: "", label: nhanRong, available: true }, ...ungVien]
    : ungVien;

  return (
    <>
      <button
        ref={nutRef}
        type="button"
        aria-label={nhan}
        aria-haspopup="listbox"
        aria-expanded={mo}
        onClick={() => setMo((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setMo(true);
          }
        }}
        className={
          //: 🔴 `min-w-0` PHẢI có, dù bên trong đã `truncate`. Nút này là CON TRỰC TIẾP của
          //: một `grid` (`grid-cols-[26px_150px_1fr_1fr]`), mà item lưới mặc định
          //: `min-width: auto` — tức nó KHÔNG co xuống dưới bề rộng nội dung, nên chuỗi dài
          //: đẩy cột rộng ra và TRÀN khỏi khung. Đo được trên ảnh chủ dự án gửi: nhãn
          //: "Faster-Whisper large-v3 (chính xác hơn turbo)" chạy quá mép ô.
          "flex h-8 w-full min-w-0 items-center gap-1.5 rounded-sm border bg-panel-0 px-2 " +
          "text-left text-[12.5px] transition-colors duration-150 active:translate-y-px " +
          (mo
            ? "border-signal text-ink-0"
            : "border-rule text-ink-0 hover:border-ink-2")
        }
      >
        <span className="min-w-0 flex-1 truncate">{chu}</span>
        {/*: Dấu "có tuỳ chọn khác" — không dùng ký tự mũi tên của font hệ thống vì nó lệch
            baseline giữa các máy; một SVG 7 px thì canh đúng ở mọi nơi. */}
        <svg
          aria-hidden="true"
          viewBox="0 0 8 5"
          className={
            "size-[8px] shrink-0 transition-transform duration-150 " +
            (mo ? "rotate-180 text-signal" : "text-ink-2")
          }
        >
          <path d="M0 0l4 5 4-5z" fill="currentColor" />
        </svg>
      </button>

      {mo &&
        createPortal(
          <ul
            role="listbox"
            data-chon-model=""
            aria-label={nhan}
            style={{ left: viTri.left, top: viTri.top, width: viTri.width }}
            className="fixed z-[60] max-h-60 overflow-y-auto rounded-sm border border-rule bg-panel-2 py-1 shadow-2xl"
          >
            {muc.map((u) => {
              const chonRoi = u.id === giaTri;
              return (
                <li key={u.id || "__rong"}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={chonRoi}
                    onClick={() => chon(u.id)}
                    className={
                      "flex w-full items-center gap-2 px-2 py-1.5 text-left text-[12.5px] " +
                      "transition-colors duration-100 " +
                      (chonRoi
                        ? "bg-signal-soft text-ink-0"
                        : "text-ink-1 hover:bg-panel-3 hover:text-ink-0")
                    }
                  >
                    <span
                      aria-hidden="true"
                      className={"num w-3 text-[10px] " + (chonRoi ? "text-signal" : "text-ink-2")}
                    >
                      {chonRoi ? "◆" : ""}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{u.label}</span>
                    {!u.available && (
                      <span className="shrink-0 text-[10px] text-fault">chưa sẵn sàng</span>
                    )}
                  </button>
                </li>
              );
            })}
            {muc.length === 0 && (
              <li className="px-2 py-1.5 text-[12px] text-ink-2">không có lựa chọn nào</li>
            )}
          </ul>,
          document.body,
        )}
    </>
  );
}

/**
 * Nhóm MT / LLM — hai lựa chọn, dạng thanh gạt, KHÔNG phải hai ô tròn hệ điều hành vẽ.
 *
 * Vẫn là `<input type="radio">` THẬT (ẩn bằng `sr-only`) chứ không phải `<button>` đóng
 * giả: `radiogroup` + radio mới cho trình đọc màn hình biết "một trong hai", và phím mũi
 * tên mới đi được giữa hai lựa chọn.
 */
export function ChonNhom({
  nhan,
  giaTri,
  luaChon,
  onChon,
}: {
  nhan: string;
  giaTri: string;
  luaChon: Array<{ id: string; label: string }>;
  onChon: (id: string) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={nhan}
      className="inline-flex items-center gap-0.5 rounded-sm border border-rule bg-panel-0 p-0.5"
    >
      {luaChon.map((o) => {
        const chon = giaTri === o.id;
        return (
          <label
            key={o.id}
            className={
              "cursor-pointer rounded-sm px-2 py-0.5 text-[11.5px] transition-colors duration-150 " +
              "active:translate-y-px " +
              (chon
                ? "bg-signal font-semibold text-panel-0"
                : "text-ink-1 hover:bg-panel-3 hover:text-ink-0")
            }
          >
            <input
              type="radio"
              name={nhan}
              className="sr-only"
              checked={chon}
              onChange={() => onChon(o.id)}
            />
            {o.label}
          </label>
        );
      })}
    </div>
  );
}
