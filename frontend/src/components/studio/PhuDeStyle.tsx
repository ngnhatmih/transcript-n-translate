import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { hinhHoc, STYLE_MAC_DINH, type PhuDeStyle } from "@/lib/phuDeStyle";

/**
 * Bản xem trước phụ đề ĐÈ LÊN video.
 *
 * Vì sao phải đo khung bằng `ResizeObserver` chứ không dùng đơn vị CSS linh hoạt: kiểu chữ
 * được khai trong hệ `.ass` (1920×1080), và backend nhân tỉ lệ theo trục NGẮN của khung
 * THẬT. Muốn xem trước đúng thì phải biết kích thước thật của khung chứa video, rồi áp
 * CÙNG công thức (`hinhHoc`).
 */
export function PhuDeOverlay({ style, text }: { style: PhuDeStyle; text: string }) {
  const hopRef = useRef<HTMLDivElement>(null);
  const [khung, setKhung] = useState({ rong: 0, cao: 0 });

  useLayoutEffect(() => {
    const el = hopRef.current;
    if (el === null) return;
    const do_ = () => setKhung({ rong: el.clientWidth, cao: el.clientHeight });
    do_();
    // `ResizeObserver` có thể không có trong môi trường test — bỏ qua là an toàn, vì khi đó
    // kích thước đã đọc được một lần ở trên và bản xem trước vẫn hiện (chỉ không tự co giãn).
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(do_);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (text === "") return <div ref={hopRef} className="pointer-events-none absolute inset-0" />;

  const h = hinhHoc(style, khung.rong, khung.cao);
  // Chưa đo được khung thì KHÔNG vẽ: vẽ với `coChu = 0` sẽ hiện một chấm chữ ở góc, tệ hơn
  // là không hiện gì.
  if (khung.cao === 0) return <div ref={hopRef} className="pointer-events-none absolute inset-0" />;

  const coHop = style.kieuVien === 3;
  const noiDung = {
    fontSize: `${h.coChu}px`,
    lineHeight: 1.25,
    fontWeight: style.dam ? 700 : 400,
    fontStyle: style.nghieng ? "italic" : "normal",
    color: style.mauChu,
    textAlign: style.canLe === 1 ? "left" : style.canLe === 3 ? "right" : "center",
    // `BorderStyle 3` = hộp đục sau chữ. CSS tương đương là nền + đệm; đệm lấy theo độ dày
    // viền đã nhân tỉ lệ để hộp không sát chữ hơn bản burn.
    ...(coHop
      ? { background: style.mauHop, opacity: 1, padding: `${Math.max(1, h.vien)}px ${Math.max(2, h.vien * 2)}px`, borderRadius: 2 }
      : {
          // Chỉ viền quanh NÉT chữ: CSS không có viền chữ, nên dựng bằng 4 bóng lệch.
          textShadow: [
            `${h.vien}px 0 0 ${style.mauHop}`,
            `-${h.vien}px 0 0 ${style.mauHop}`,
            `0 ${h.vien}px 0 ${style.mauHop}`,
            `0 -${h.vien}px 0 ${style.mauHop}`,
          ].join(", "),
        }),
  } as const;

  return (
    <div ref={hopRef} className="pointer-events-none absolute inset-0">
      <div
        className="absolute"
        style={{
          left: h.le,
          right: h.le,
          bottom: h.cachDay,
          // Độ đục của hộp đi qua `rgba` chứ không qua `opacity` của cả khối: `opacity` sẽ
          // làm mờ LUÔN chữ, trong khi `.ass` chỉ trong suốt cái hộp.
          ...noiDung,
          ...(coHop
            ? {
                background: rgba(style.mauHop, style.doDucHop),
                padding: `${Math.max(1, h.vien)}px ${Math.max(2, h.vien * 2)}px`,
                borderRadius: 2,
              }
            : {}),
        }}
      >
        {text}
      </div>
    </div>
  );
}

function rgba(hex: string, doDuc: number): string {
  const s = hex.replace("#", "");
  const r = parseInt(s.slice(0, 2), 16);
  const g = parseInt(s.slice(2, 4), 16);
  const b = parseInt(s.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${Math.min(Math.max(doDuc, 0), 1)})`;
}

function Truong({ nhan, children }: { nhan: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center justify-between gap-3 py-1.5 text-[12.5px] text-ink-1">
      <span className="shrink-0">{nhan}</span>
      <span className="flex items-center gap-2">{children}</span>
    </label>
  );
}

const oNhap =
  "w-16 rounded-sm border border-rule bg-panel-0 px-2 py-1 text-right text-[12.5px] text-ink-0 outline-none focus:border-signal";

/**
 * Hộp thoại chỉnh phụ đề hiển thị. Mở bằng lệnh "Chỉnh phụ đề hiển thị" trong bảng lệnh.
 *
 * Mọi thay đổi gọi `onChange` NGAY (không có nút Lưu): người dùng đang nhìn bản xem trước
 * phía sau hộp thoại, nên thấy kết quả tức thì là cách duy nhất để chỉnh bằng mắt.
 */
export function PhuDeStyleDialog({
  open,
  onClose,
  style,
  onChange,
}: {
  open: boolean;
  onClose: () => void;
  style: PhuDeStyle;
  onChange: (s: PhuDeStyle) => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const dat = (v: Partial<PhuDeStyle>) => onChange({ ...style, ...v });

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-start justify-center bg-panel-0/70 pt-[12vh] backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="w-[420px] max-w-[92vw] rounded-sm border border-rule bg-panel-1 p-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Chỉnh phụ đề hiển thị"
      >
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-[13.5px] font-medium text-ink-0">Chỉnh phụ đề hiển thị</h2>
          <button
            onClick={() => onChange({ ...STYLE_MAC_DINH })}
            className="text-[11.5px] text-ink-2 hover:text-ink-0"
          >
            về mặc định
          </button>
        </div>

        <Truong nhan="Cỡ chữ">
          <input
            type="range"
            min={8}
            max={160}
            value={style.co}
            onChange={(e) => dat({ co: Number(e.target.value) })}
            className="w-28 accent-signal"
            aria-label="Cỡ chữ"
          />
          <input
            type="number"
            min={8}
            max={400}
            value={style.co}
            onChange={(e) => dat({ co: Number(e.target.value) })}
            className={oNhap}
            aria-label="Cỡ chữ (số)"
          />
        </Truong>

        <Truong nhan="Màu chữ">
          <input
            type="color"
            value={style.mauChu}
            onChange={(e) => dat({ mauChu: e.target.value })}
            className="h-6 w-10 cursor-pointer rounded-sm border border-rule bg-transparent"
            aria-label="Màu chữ"
          />
        </Truong>

        <Truong nhan="Kiểu nền">
          <select
            value={style.kieuVien}
            onChange={(e) => dat({ kieuVien: Number(e.target.value) === 1 ? 1 : 3 })}
            className="rounded-sm border border-rule bg-panel-0 px-2 py-1 text-[12.5px] text-ink-0 outline-none"
            aria-label="Kiểu nền"
          >
            <option value={3}>hộp đục</option>
            <option value={1}>chỉ viền chữ</option>
          </select>
        </Truong>

        {style.kieuVien === 3 && (
          <>
            <Truong nhan="Màu hộp">
              <input
                type="color"
                value={style.mauHop}
                onChange={(e) => dat({ mauHop: e.target.value })}
                className="h-6 w-10 cursor-pointer rounded-sm border border-rule bg-transparent"
                aria-label="Màu hộp"
              />
            </Truong>
            <Truong nhan="Độ đục">
              <input
                type="range"
                min={0}
                max={100}
                value={Math.round(style.doDucHop * 100)}
                onChange={(e) => dat({ doDucHop: Number(e.target.value) / 100 })}
                className="w-28 accent-signal"
                aria-label="Độ đục của hộp"
              />
              <span className="w-9 text-right tabular-nums text-[12px] text-ink-2">
                {Math.round(style.doDucHop * 100)}%
              </span>
            </Truong>
          </>
        )}

        <Truong nhan="Độ dày viền">
          <input
            type="number"
            min={0}
            max={20}
            value={style.vien}
            onChange={(e) => dat({ vien: Number(e.target.value) })}
            className={oNhap}
            aria-label="Độ dày viền"
          />
        </Truong>

        <Truong nhan="Canh lề">
          <select
            value={style.canLe}
            onChange={(e) => dat({ canLe: Number(e.target.value) as 1 | 2 | 3 })}
            className="rounded-sm border border-rule bg-panel-0 px-2 py-1 text-[12.5px] text-ink-0 outline-none"
            aria-label="Canh lề"
          >
            <option value={1}>trái</option>
            <option value={2}>giữa</option>
            <option value={3}>phải</option>
          </select>
        </Truong>

        <Truong nhan="Cách đáy">
          <input
            type="range"
            min={0}
            max={50}
            value={Math.round(style.viTriDoc * 100)}
            onChange={(e) => dat({ viTriDoc: Number(e.target.value) / 100 })}
            className="w-28 accent-signal"
            aria-label="Cách đáy khung"
          />
          <span className="w-9 text-right tabular-nums text-[12px] text-ink-2">
            {Math.round(style.viTriDoc * 100)}%
          </span>
        </Truong>

        <div className="mt-1 flex gap-4">
          <label className="flex items-center gap-1.5 text-[12.5px] text-ink-1">
            <input
              type="checkbox"
              checked={style.dam}
              onChange={(e) => dat({ dam: e.target.checked })}
              className="accent-signal"
            />
            đậm
          </label>
          <label className="flex items-center gap-1.5 text-[12.5px] text-ink-1">
            <input
              type="checkbox"
              checked={style.nghieng}
              onChange={(e) => dat({ nghieng: e.target.checked })}
              className="accent-signal"
            />
            nghiêng
          </label>
        </div>

        <p className="mt-3 border-t border-rule pt-2 text-[11.5px] leading-4 text-ink-2">
          Kiểu này dùng cho cả bản xem trước, tệp <code className="kbd">.ass</code> tải về,
          và phụ đề burn vào video lồng tiếng.
        </p>

        <div className="mt-3 flex justify-end">
          <button
            onClick={onClose}
            className={cn(
              "rounded-sm border border-rule px-3 py-1.5 text-[12.5px] text-ink-0",
              "hover:border-signal hover:bg-signal-soft",
            )}
          >
            Xong
          </button>
        </div>
      </div>
    </div>
  );
}
