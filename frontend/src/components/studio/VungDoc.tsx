import { useCallback, useEffect, useRef, useState } from "react";

/**
 * VÙNG ĐỌC OCR — khung kéo-thả đè lên chính khung hình video.
 *
 * ## Vì sao có component này
 *
 * OCR đọc *mọi* chữ trong khung, kể cả watermark và logo. Đo được trên
 * `8f4b5304daf42569.mp4` (1080×1920): watermark `想想工作室` + `bilibili` ở
 * `y=35-102, x=697-1051`, còn phụ đề thật ở `y=532-619` và `y=1435-1495`. Không
 * giới hạn vùng đọc thì 30/32 dòng watermark **lọt** qua tầng lọc 4 — vì tầng đó chỉ
 * bỏ hộp nằm NGOÀI khoảng có tiếng nói, mà watermark hiện CÙNG LÚC với lời thoại.
 *
 * ## Vì sao kéo-thả chứ không phải bốn ô số
 *
 * Vùng phụ thuộc VIDEO, không phụ thuộc engine: video dọc 1080×1920 có watermark ở
 * góc trên phải, video ngang 1280×720 ở chỗ khác. Người dùng nhìn thấy watermark ở
 * đâu thì kéo khung tới đó — khớp trực tiếp với thứ họ đang nhìn, không phải quy đổi
 * sang toạ độ tỉ lệ trong đầu rồi gõ số.
 *
 * ## Vì sao toạ độ TỈ LỆ, không phải pixel
 *
 * `<video>` được hiển thị nhỏ hơn nhiều so với khung gốc (`object-contain` trong một
 * hộp `aspect-video`), và kích thước hiển thị đổi theo cửa sổ. Nhưng backend cần toạ
 * độ theo tỉ lệ khung GỐC, vì `ffmpeg` trích khung ở độ phân giải gốc. Nên mọi phép
 * tính ở đây theo tỉ lệ `0..1` của **hộp chứa video đang hiển thị**, và chỉ đổi sang
 * pixel khi vẽ.
 *
 * ## Nút ×
 *
 * `vung === null` nghĩa là TẮT lọc vùng — OCR đọc cả khung, đúng hành vi trước khi có
 * tính năng này. Nút × đưa về trạng thái đó; nút "Bật lại" dựng khung mặc định.
 * Hai trạng thái này phải phân biệt được với "chưa chọn gì", nên kiểu là
 * `VungDoc | null` và `null` mang nghĩa TẮT (xem `_vung_doc_tu_payload` ở backend:
 * `[]` cũng là TẮT, `không có khoá` mới là "dùng mặc định").
 */

/** `[x0, y0, x1, y1]` theo tỉ lệ `0..1` của khung hình GỐC. */
export type VungDoc = readonly [number, number, number, number];

/**
 * Vùng mặc định — bỏ 10 % trên cùng.
 *
 * ĐO ĐƯỢC trên `8f4b5304daf42569.mp4`: watermark ở `y=35-102` trên khung cao 1920,
 * tức `1,8 %..5,3 %`. Bỏ 10 % là đủ tách mà không cắt phụ đề thật (dòng gần nhất ở
 * `y=532`, tức 27,7 %).
 *
 * Vì sao vẫn đặt mặc định dù nó chỉ đúng cho một video: nó là điểm XUẤT PHÁT để người
 * dùng kéo, rẻ hơn nhiều so với bắt đầu từ "cả khung" rồi phải tự tìm watermark.
 */
export const VUNG_DOC_MAC_DINH: VungDoc = [0, 0.1, 1, 1];

/** Cạnh nhỏ nhất của khung, theo tỉ lệ — chặn khung co về 0 rồi không kéo lại được. */
const TOI_THIEU = 0.05;

export type TayKeo = "move" | "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

const KEP = (v: number) => Math.min(1, Math.max(0, v));

/**
 * Chuột → vùng mới. Hàm THUẦN, tách khỏi DOM để test được không cần trình duyệt.
 *
 * `dx`/`dy` là thay đổi theo tỉ lệ (đã chia cho kích thước hộp hiển thị), không phải
 * pixel. `tay` quyết định cạnh nào dịch: `move` dời cả khung, `n` chỉ đổi `y0`, `ne`
 * đổi `y1` và `x1`, v.v.
 */
export function keoVung(
  goc: VungDoc,
  tay: TayKeo,
  dx: number,
  dy: number,
): VungDoc {
  let [x0, y0, x1, y1] = goc;

  if (tay === "move") {
    // Dời cả khung: kẹp để không ra ngoài, và giữ NGUYÊN bề rộng/cao. Kẹp từng cạnh
    // riêng sẽ làm khung co lại khi đập mép — đó là hành vi của resize, không phải
    // của move.
    const rong = x1 - x0;
    const cao = y1 - y0;
    x0 = Math.min(1 - rong, Math.max(0, x0 + dx));
    y0 = Math.min(1 - cao, Math.max(0, y0 + dy));
    return [x0, y0, x0 + rong, y0 + cao];
  }

  if (tay.includes("w")) x0 = KEP(x0 + dx);
  if (tay.includes("e")) x1 = KEP(x1 + dx);
  if (tay.includes("n")) y0 = KEP(y0 + dy);
  if (tay.includes("s")) y1 = KEP(y1 + dy);

  // Chặn bề rộng/cao về 0 và chặn cạnh vượt qua cạnh đối diện: một khung lật ngược
  // (`x0 > x1`) sẽ được backend từ chối, và lỗi đó hiện ở tận lúc chạy job.
  if (x1 - x0 < TOI_THIEU) {
    if (tay.includes("w")) x0 = x1 - TOI_THIEU;
    else x1 = x0 + TOI_THIEU;
  }
  if (y1 - y0 < TOI_THIEU) {
    if (tay.includes("n")) y0 = y1 - TOI_THIEU;
    else y1 = y0 + TOI_THIEU;
  }
  return [KEP(x0), KEP(y0), KEP(x1), KEP(y1)];
}

/** `[0.0234, 0.1, 1, 0.87]` → `"x 2–100 % · y 10–87 %"`. Số nguyên %, dấu phẩy thập phân. */
export function moTaVung(v: VungDoc): string {
  // `Math.round` chứ không cắt: người dùng kéo bằng mắt, và "2 %" đọc được còn
  // "2,34 %" thì không — trong khi chênh lệch đó (0,34 % của 1920 px = 6 px) không
  // ai nhắm tới được bằng chuột.
  const so = (x: number) => String(Math.round(x * 100)).replace(".", ",");
  return `x ${so(v[0])}–${so(v[2])} % · y ${so(v[1])}–${so(v[3])} %`;
}

export type VungDocProps = {
  /** Vùng hiện tại; `null` = TẮT lọc vùng. */
  vung: VungDoc | null;
  onChange: (v: VungDoc | null) => void;
  /** Khoá theo nguồn: đổi video thì khung phải về mặc định, không mang vùng cũ sang. */
  sourceId: number | null;
};

export function VungDocKhung({ vung, onChange, sourceId }: VungDocProps) {
  const hopRef = useRef<HTMLDivElement | null>(null);
  const [dangKeo, setDangKeo] = useState<{
    tay: TayKeo;
    batDauX: number;
    batDauY: number;
    goc: VungDoc;
    rong: number;
    cao: number;
  } | null>(null);

  /**
   * Đổi video ⇒ đặt lại khung về mặc định.
   *
   * Vì sao phải làm: vùng đo cho video dọc 1080×1920 (watermark góc trên phải) áp lên
   * video ngang 1280×720 sẽ cắt mất một dải phụ đề thật — và không có gì báo. Mang
   * vùng của video trước sang video sau là dùng dữ liệu của một video khác.
   */
  const daKhoa = useRef<number | null>(null);
  useEffect(() => {
    if (sourceId === null || sourceId === daKhoa.current) return;
    daKhoa.current = sourceId;
    onChange(VUNG_DOC_MAC_DINH);
  }, [sourceId, onChange]);

  useEffect(() => {
    if (dangKeo === null) return;
    const onMove = (e: PointerEvent) => {
      const dx = (e.clientX - dangKeo.batDauX) / dangKeo.rong;
      const dy = (e.clientY - dangKeo.batDauY) / dangKeo.cao;
      onChange(keoVung(dangKeo.goc, dangKeo.tay, dx, dy));
    };
    const onUp = () => setDangKeo(null);
    // `setPointerCapture` không dùng được vì tay kéo có thể rời khỏi phần tử; nghe
    // trên `window` để khung vẫn theo chuột khi con trỏ ra ngoài hộp video.
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [dangKeo, onChange]);

  const batDau = useCallback(
    (tay: TayKeo) => (e: React.PointerEvent) => {
      if (vung === null) return;
      const hop = hopRef.current;
      if (hop === null) return;
      // `preventDefault` để không bôi đen chữ trong khung khi kéo.
      e.preventDefault();
      e.stopPropagation();
      const r = hop.getBoundingClientRect();
      setDangKeo({
        tay,
        batDauX: e.clientX,
        batDauY: e.clientY,
        goc: vung,
        rong: r.width,
        cao: r.height,
      });
    },
    [vung],
  );

  if (sourceId === null) return null;

  // ── TẮT: chỉ còn một nút để bật lại. ────────────────────────────────────────
  if (vung === null) {
    return (
      <button
        onClick={() => onChange(VUNG_DOC_MAC_DINH)}
        className="absolute left-2 top-2 z-20 rounded-sm border border-rule bg-panel-0/90 px-2 py-1 text-[10.5px] text-ink-1 backdrop-blur-sm hover:border-ink-1 hover:text-ink-0"
        title="OCR đang đọc CẢ khung — watermark và logo sẽ bị đọc như chữ phụ đề"
      >
        Vùng đọc: tắt · bật lại
      </button>
    );
  }

  const [x0, y0, x1, y1] = vung;
  const nen: React.CSSProperties = {
    left: `${x0 * 100}%`,
    top: `${y0 * 100}%`,
    width: `${(x1 - x0) * 100}%`,
    height: `${(y1 - y0) * 100}%`,
  };

  /** Một tay kéo. `vi tri` là lớp CSS đặt nó ở đúng cạnh/góc. */
  const tayKeo = (tay: TayKeo, viTri: string, conTro: string) => (
    <span
      onPointerDown={batDau(tay)}
      className={`absolute z-10 ${viTri}`}
      style={{ cursor: conTro, touchAction: "none" }}
      aria-hidden
    />
  );

  return (
    <>
      {/*
        LỚP PHỦ NGOÀI KHUNG — bốn dải tối, không phải một lớp mờ toàn khung.
        Vì sao: người dùng cần THẤY vùng bị loại (để biết watermark đã nằm trong đó),
        chứ không phải thấy cả khung tối đều rồi đoán khung ở đâu.
      */}
      <div className="pointer-events-none absolute inset-0 z-10">
        <div className="absolute inset-x-0 top-0 bg-panel-0/55" style={{ height: `${y0 * 100}%` }} />
        <div className="absolute inset-x-0 bottom-0 bg-panel-0/55" style={{ height: `${(1 - y1) * 100}%` }} />
        <div
          className="absolute left-0 bg-panel-0/55"
          style={{ top: `${y0 * 100}%`, height: `${(y1 - y0) * 100}%`, width: `${x0 * 100}%` }}
        />
        <div
          className="absolute right-0 bg-panel-0/55"
          style={{ top: `${y0 * 100}%`, height: `${(y1 - y0) * 100}%`, width: `${(1 - x1) * 100}%` }}
        />
      </div>

      {/* KHUNG — vùng OCR ĐƯỢC đọc. */}
      <div
        ref={hopRef}
        style={nen}
        className="absolute z-20 border-2 border-dashed border-[var(--accent,#7dd3fc)]"
      >
        {/*
          Nút × — TẮT lọc vùng. Đặt TRONG khung thay vì cạnh video để nó luôn đi theo
          vùng người dùng đang chỉnh; một nút ở góc hộp video sẽ nằm ngoài vùng khi
          khung bị kéo xuống dưới.
        */}
        <button
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => onChange(null)}
          className="absolute -right-2.5 -top-2.5 z-30 grid size-5 place-items-center rounded-full border border-rule bg-panel-0 text-[11px] leading-none text-ink-1 hover:border-ink-1 hover:text-ink-0"
          title="Tắt lọc vùng — OCR sẽ đọc cả khung, kể cả watermark"
          aria-label="Tắt lọc vùng đọc"
        >
          ×
        </button>

        {/* Thân: dời cả khung. */}
        <span
          onPointerDown={batDau("move")}
          className="absolute inset-0 block"
          style={{ cursor: "move", touchAction: "none" }}
          aria-hidden
        />

        {/* Bốn cạnh. Vùng chạm 10 px để bắt được bằng ngón tay. */}
        {tayKeo("n", "inset-x-0 -top-1 h-2.5", "ns-resize")}
        {tayKeo("s", "inset-x-0 -bottom-1 h-2.5", "ns-resize")}
        {tayKeo("w", "inset-y-0 -left-1 w-2.5", "ew-resize")}
        {tayKeo("e", "inset-y-0 -right-1 w-2.5", "ew-resize")}
        {/* Bốn góc — ưu tiên cao hơn cạnh vì chúng chồng lên nhau ở góc. */}
        {tayKeo("nw", "-left-1 -top-1 size-3 z-20", "nwse-resize")}
        {tayKeo("ne", "-right-1 -top-1 size-3 z-20", "nesw-resize")}
        {tayKeo("sw", "-left-1 -bottom-1 size-3 z-20", "nesw-resize")}
        {tayKeo("se", "-right-1 -bottom-1 size-3 z-20", "nwse-resize")}

        {/* Nhãn: nói RÕ vùng này dùng để làm gì, và số đo hiện tại. */}
        <span className="pointer-events-none absolute -top-6 left-0 whitespace-nowrap rounded-sm bg-panel-0/90 px-1.5 py-0.5 text-[10px] text-ink-1 backdrop-blur-sm">
          OCR đọc vùng này · {moTaVung(vung)}
        </span>
      </div>
    </>
  );
}
