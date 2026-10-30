/**
 * Dải THỜI GIAN — thước + sóng âm vẽ bằng canvas + khối đoạn kéo được + đầu phát.
 *
 * 🔴 NGUỒN GỐC: `_lovable-code/src/components/studio/Timeline.tsx` (163 dòng). Giữ nguyên
 * HÌNH HỌC đo được, đổi hai chỗ:
 *
 *  1. **Khối đoạn hiện CHỮ BẢN DỊCH, không phải bản gốc** — bản gốc dùng
 *     `s.translations[s.chosen]` (mô hình hai bản dịch song song của nó). Repo có
 *     `TranslationDetail.segments`, nên chữ đi vào qua prop `chuCuaDoan`.
 *
 *  2. **Sóng âm là dữ liệu THẬT hoặc KHÔNG VẼ** — bản gốc nhận `peaks` từ `fakePeaks`
 *     khi chưa nạp tệp. Ở đây `peaks` rỗng thì canvas để trống (xem `use-player.docSong`).
 *
 * 📏 SỐ ĐO trên bản đã duyệt (Chrome, 1680×1050):
 *      khung ngoài : 1376×160, `border-y 1px --rule`, `background --panel-0`
 *      khung trong : 2200×148 (`width = duration * pxPerSec`, mặc định 40 px/s)
 *      thước       : cao 20 px, nhãn mỗi 5 giây, mono 9,5 px màu `--ink-2`
 *      canvas      : 2200×96, đặt tại `top: 20px`, màu sóng `--wave`
 *      khối đoạn   : cao 32 px ở đáy, `top: 1px bottom: 1px` bên trong, radius 2 px
 *      đầu phát    : 1 px rộng, cao hết khung, mũi tên `clip-path` 9×8 ở đỉnh
 *
 * ## Vì sao khối đoạn KHÔNG dùng phần trăm
 *
 * Bản gốc đặt `left: s.start * pxPerSec` và `width: (s.end - s.start) * pxPerSec` — toạ độ
 * TUYỆT ĐỐI theo px. Giữ đúng cách đó: phần trăm sẽ làm khối co giãn khi `pxPerSec` đổi
 * nhưng vị trí nhãn thước thì không, và hai thứ sẽ lệch nhau ngay ở mức phóng to 10 px/s.
 *
 * ## Vì sao kéo mép dùng `pointerdown` trên `window` chứ không `onMouseMove`
 *
 * Bản gốc gắn `pointermove`/`pointerup` lên `window` trong lúc kéo. Đó là cách DUY NHẤT
 * đúng: con trỏ rời khỏi khối đoạn (rất dễ xảy ra khi kéo) vẫn phải tiếp tục kéo, và một
 * `onMouseLeave` sẽ cắt ngang thao tác giữa chừng.
 */
import { useEffect, useRef } from "react";

import type { Segment } from "../../api/types.ts";
import { viecCuaDoan, type Viec } from "../../lib/studio.ts";

/** Cao thước, px. */
const CAO_THUOC = 20;
/** Cao canvas sóng, px. */
const CAO_SONG = 96;
/** Cao khối đoạn, px. */
const CAO_KHOI = 32;
/** Tổng cao khung trong = thước + sóng + khối. */
const CAO_TONG = CAO_THUOC + CAO_SONG + CAO_KHOI;

export interface TimelineProps {
  segments: readonly Segment[];
  /** Biên độ sóng ∈ [0,1]; MẢNG RỖNG = chưa đọc được, canvas để trống. */
  peaks: readonly number[];
  duration: number;
  time: number;
  pxPerSec: number;
  /** `Segment.i` đang chọn (đoạn sáng, có viền amber). */
  currentSegment: number | null;
  /** `Segment.i` ĐANG PHÁT (khác `currentSegment` khi người dùng chọn một đoạn nhưng chưa phát). */
  playingSegment: number | null;
  /** Chữ hiện trên khối đoạn — bản dịch đang xem, hoặc bản gốc khi chưa dịch. */
  chuCuaDoan: (seg: Segment) => string;
  /** Mọi việc cần xử lý — để khối đoạn có vân "nghi ngờ" và viền lỗi. */
  viec: readonly Viec[];
  onSeek: (t: number) => void;
  onSelect: (i: number) => void;
  /** Kéo mép ⇒ sửa mốc. `edge` là `"start"` hoặc `"end"`, `t` là giây mới. */
  onResize: (i: number, edge: "start" | "end", t: number) => void;
}

/** `m:ss` — nhãn thước, KHÔNG phải timecode đầy đủ (thước chỉ cần tới giây). */
function nhanThuoc(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function Timeline({
  segments,
  peaks,
  duration,
  time,
  pxPerSec,
  currentSegment,
  playingSegment,
  chuCuaDoan,
  viec,
  onSeek,
  onSelect,
  onResize,
}: TimelineProps) {
  const khungRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rong = Math.max(1, duration * pxPerSec);

  // ── VẼ SÓNG ──────────────────────────────────────────────────────────────────────
  // `devicePixelRatio` là bắt buộc: không nhân thì trên màn Retina (và trên Windows ở
  // 150 %) sóng bị vẽ ở nửa độ phân giải và trông nhoè — đo được trên ảnh chụp.
  useEffect(() => {
    const c = canvasRef.current;
    if (c === null) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.max(1, Math.round(rong * dpr));
    c.height = Math.max(1, Math.round(CAO_SONG * dpr));
    const g = c.getContext("2d");
    if (g === null) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, rong, CAO_SONG);
    if (peaks.length === 0) return; // chưa đọc được sóng ⇒ để trống, KHÔNG bịa
    g.fillStyle = getComputedStyle(c).color;
    const beRong = rong / peaks.length;
    peaks.forEach((p, idx) => {
      const cao = Math.max(1, Math.min(1, p) * (CAO_SONG - 12));
      g.fillRect(idx * beRong, (CAO_SONG - cao) / 2, Math.max(1, beRong - 0.6), cao);
    });
  }, [peaks, rong]);

  // ── CUỘN THEO ĐẦU PHÁT ───────────────────────────────────────────────────────────
  // Chỉ cuộn khi đầu phát RA KHỎI vùng nhìn thấy. Cuộn mọi khung hình là dải thời gian
  // trượt liên tục dưới mắt người đọc — không đọc được dòng nào.
  useEffect(() => {
    const el = khungRef.current;
    if (el === null) return;
    const x = time * pxPerSec;
    if (x < el.scrollLeft + 40 || x > el.scrollLeft + el.clientWidth - 80) {
      el.scrollLeft = Math.max(0, x - el.clientWidth / 3);
    }
  }, [time, pxPerSec]);

  /** Đổi `clientX` của con trỏ thành giây trên dải. */
  const raGiay = (clientX: number): number => {
    const el = khungRef.current;
    if (el === null) return 0;
    const r = el.getBoundingClientRect();
    return (clientX - r.left + el.scrollLeft) / pxPerSec;
  };

  const batDauKeo = (suKien: React.PointerEvent, i: number, edge: "start" | "end") => {
    suKien.stopPropagation();
    suKien.preventDefault();
    const di = (ev: PointerEvent) => onResize(i, edge, raGiay(ev.clientX));
    const tha = () => {
      window.removeEventListener("pointermove", di);
      window.removeEventListener("pointerup", tha);
      window.removeEventListener("pointercancel", tha);
    };
    window.addEventListener("pointermove", di);
    window.addEventListener("pointerup", tha);
    window.addEventListener("pointercancel", tha);
  };

  // Nhãn thước mỗi 5 giây. `duration` có thể là 0 (chưa `loadedmetadata`) ⇒ 0 nhãn.
  const soNhan = duration > 0 ? Math.floor(duration / 5) + 1 : 0;
  const nhan = Array.from({ length: soNhan }, (_, k) => k * 5);

  return (
    <div
      ref={khungRef}
      className="tl"
      role="slider"
      aria-label="Dòng thời gian"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(time)}
      tabIndex={0}
    >
      <div
        className="tl__trong"
        style={{ width: `${rong}px`, height: `${CAO_TONG}px` }}
        onPointerDown={(e) => onSeek(raGiay(e.clientX))}
      >
        {/* THƯỚC */}
        <div className="tl__thuoc" style={{ height: `${CAO_THUOC}px` }}>
          {nhan.map((t) => (
            <span key={t} className="tl__nhan" style={{ left: `${t * pxPerSec + 3}px` }}>
              {nhanThuoc(t)}
            </span>
          ))}
        </div>

        {/* SÓNG */}
        <canvas
          ref={canvasRef}
          className="tl__song"
          style={{ width: `${rong}px`, height: `${CAO_SONG}px`, top: `${CAO_THUOC}px` }}
        />

        {/* KHỐI ĐOẠN */}
        <div className="tl__khoi-hop" style={{ height: `${CAO_KHOI}px` }}>
          {segments.map((seg) => {
            const dsViec = viecCuaDoan(viec, seg.i);
            const lop = ["tl__khoi"];
            if (seg.i === currentSegment) lop.push("is-chon");
            if (seg.i === playingSegment) lop.push("is-phat");
            if (dsViec.some((v) => v.loai === "nghi-ngo")) lop.push("is-nghi-ngo");
            if (dsViec.some((v) => v.loai === "nen")) lop.push("is-nen");
            const chu = chuCuaDoan(seg);
            return (
              <div
                key={seg.i}
                className={lop.join(" ")}
                style={{
                  left: `${seg.start * pxPerSec}px`,
                  width: `${Math.max(6, (seg.end - seg.start) * pxPerSec)}px`,
                }}
                title={chu}
                onPointerDown={(e) => {
                  e.stopPropagation();
                  onSelect(seg.i);
                }}
              >
                {chu}
                {/* HAI TAY NẮM KÉO MÉP. Chỉ hiện khi rê chuột (CSS), nhưng LUÔN có trong DOM
                    và luôn bấm được — ẩn bằng `opacity` chứ không `display:none`. */}
                <span
                  className="tl__keo tl__keo--dau"
                  role="separator"
                  aria-label="Kéo giờ vào"
                  onPointerDown={(e) => batDauKeo(e, seg.i, "start")}
                />
                <span
                  className="tl__keo tl__keo--cuoi"
                  role="separator"
                  aria-label="Kéo giờ ra"
                  onPointerDown={(e) => batDauKeo(e, seg.i, "end")}
                />
              </div>
            );
          })}
        </div>

        {/* ĐẦU PHÁT */}
        <div className="tl__dau-phat" style={{ left: `${time * pxPerSec}px` }} aria-hidden="true">
          <span className="tl__mui" />
        </div>
      </div>
    </div>
  );
}
