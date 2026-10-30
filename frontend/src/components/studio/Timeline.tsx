import { useEffect, useRef } from "react";
import type { Dong } from "@/lib/studio";
import { viecCuaDong } from "@/lib/studio";
import { formatTimecode } from "@/lib/timecode";
import { cn } from "@/lib/utils";

interface Props {
  segments: Dong[];
  peaks: number[];
  duration: number;
  time: number;
  pxPerSec: number;
  currentId: number | null;
  onSeek: (t: number) => void;
  onSelect: (id: number) => void;
  onResize: (id: number, edge: "start" | "end", t: number) => void;
}

export function Timeline({
  segments,
  peaks,
  duration,
  time,
  pxPerSec,
  currentId,
  onSeek,
  onSelect,
  onResize,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const width = Math.max(1, duration * pxPerSec);
  const H = 96;

  /**
   * BE RONG KHOI DOAN = BE RONG THOI GIAN. Het. Khong noi, khong xep lan.
   *
   * 🔴 BA LAN SUA SAI, MOI LAN CO SO DO — ghi lai de khong lap lai:
   *
   *   Lan 1: dat nguong `>= 60px moi ve chu`. Do that: 46/438 doan ngan hon 1 s
   *          (2,4 .. 40 px) mat chu hoan toan — 10,5% so dong. Te hon ban goc.
   *
   *   Lan 2: noi `width` cho vua chu, giu `left = start * pxPerSec`.
   *          Do tren anh `_dan1.png`: khoi #1 rong 924 px (cau 70 ky tu) tran qua
   *          khoi #2 va #3 -> chu ba khoi DE nhau tren mot hang.
   *
   *   Lan 3: xep khoi vao cac LAN de khong de nhau.
   *          Do that: 9 lan cho 438 doan. Vung doan cao 9 x 26 = 234 px de hien
   *          dung ~10 cau dau. Them tran 420 px thi 215/438 khoi bi cat chu.
   *
   * SU THAT RUT RA, DO DUOC:
   *   #1  0,00->2,04s  rongTG= 81,6px  rongChu= 924px  (70 ky tu)
   *   #2  4,36->5,58s  rongTG= 48,8px  rongChu= 417px  (31 ky tu)
   *   #3  5,58->7,66s  rongTG= 83,2px  rongChu= 612px  (46 ky tu)
   *
   * Cau tieng Viet dai GAP 3-7 LAN cho thoi gian cua no. O 40 px/s KHONG THE vua
   * hien nguyen cau vua giu moc thoi gian — phai chon mot. Chon MOC THOI GIAN,
   * vi do la su that cua du lieu va la thu nguoi dung dung de can chinh.
   *
   * Nen: `width = (end - start) * pxPerSec` nhu ban goc cua Lovable, va `truncate`
   * de khoi hep hien "Ban chac chan chua..." thay vi cat giua tu. Phong to
   * (`pxPerSec` lon hon) thi doc duoc nhieu hon — do la viec cua thanh Thu phong.
   */

  // Chi con MOT lan: khung doan cao dung mot hang, khong phu thuoc du lieu.
  const CAO_DOAN = 32;

  // vẽ sóng
  //
  // 🔴 SÓNG NÀY ĐẾN TỪ ĐÂU (đo được, không đoán): `peaks` do `Studio` giải mã từ
  // `/api/media/{id}`. Đo trên trang thật:
  //
  //   fetch status=206 type=video/mp4
  //   blob size=238623268 sau 0.0s
  //   ... rồi KHÔNG có `decodeAudioData OK` lẫn `LOI` trong 45 giây.
  //
  // Tức `decodeAudioData` TREO trên container MP4 238 MB (AAC trong MP4), không lỗi.
  // Nên `peaks` luôn rỗng và canvas luôn trống — không phải lỗi vẽ.
  //
  // Vì vậy: khi `peaks` rỗng thì vẽ một DẢI PHẲNG MỎNG thay vì để trống hoàn toàn.
  // Đó là nói thật "chưa có sóng", khác với một khung đen khiến người dùng tưởng
  // dải thời gian hỏng.
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = width * dpr;
    c.height = H * dpr;
    const g = c.getContext("2d");
    if (!g) return;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, width, H);
    g.fillStyle = getComputedStyle(c).color;

    if (peaks.length === 0) {
      // Vạch giữa mảnh, đứt đoạn — dấu hiệu "chưa có dữ liệu sóng", không phải sóng thật.
      const y = H / 2;
      for (let x = 0; x < width; x += 6) g.fillRect(x, y, 2, 1);
      return;
    }

    const bw = width / peaks.length;
    peaks.forEach((p, i) => {
      const h = Math.max(1, p * (H - 12));
      g.fillRect(i * bw, (H - h) / 2, Math.max(1, bw - 0.6), h);
    });
  }, [peaks, width]);

  // cuộn theo đầu phát
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const x = time * pxPerSec;
    if (x < el.scrollLeft + 40 || x > el.scrollLeft + el.clientWidth - 80) {
      el.scrollLeft = x - el.clientWidth / 3;
    }
  }, [time, pxPerSec]);

  const toTime = (clientX: number) => {
    const r = scrollRef.current!.getBoundingClientRect();
    return (clientX - r.left + scrollRef.current!.scrollLeft) / pxPerSec;
  };

  const startDrag = (e: React.PointerEvent, id: number, edge: "start" | "end") => {
    e.stopPropagation();
    e.preventDefault();
    const move = (ev: PointerEvent) => onResize(id, edge, toTime(ev.clientX));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const ticks = Array.from({ length: Math.floor(duration / 5) + 1 }, (_, i) => i * 5);

  return (
    <div
      ref={scrollRef}
      className="relative overflow-x-auto overflow-y-hidden border-y border-rule bg-panel-0"
      role="slider"
      aria-label="Dòng thời gian"
      aria-valuemin={0}
      aria-valuemax={duration}
      aria-valuenow={time}
      tabIndex={0}
    >
      <div
        className="relative cursor-crosshair"
        style={{ width, height: 20 + H + CAO_DOAN }}
        onPointerDown={(e) => onSeek(toTime(e.clientX))}
      >
        {/* thước */}
        <div className="absolute inset-x-0 top-0 h-5 border-b border-rule">
          {ticks.map((t) => (
            <span
              key={t}
              className="num absolute top-1 text-[9.5px] text-ink-2"
              style={{ left: t * pxPerSec + 3 }}
            >
              {formatTimecode(t)}
            </span>
          ))}
        </div>
        <canvas
          ref={canvasRef}
          className="absolute left-0 top-5 text-wave"
          style={{ width, height: H }}
        />
        {/* khối đoạn — MỘT hàng, bề rộng = bề rộng thời gian, xem docblock `CAO_DOAN` */}
        <div className="absolute inset-x-0 bottom-0" style={{ height: CAO_DOAN }}>
          {segments.map((s) => {
            const bad = viecCuaDong(s).length > 0;
            const cur = s.i === currentId;
            const chu = s.dich === "" ? s.text : s.dich;
            return (
              <div
                key={s.i}
                className={cn(
                  "group absolute top-0.5 bottom-0.5 overflow-hidden truncate rounded-sm border px-1.5 text-[10.5px] leading-[22px] whitespace-nowrap transition-colors",
                  cur
                    ? "z-10 border-signal bg-signal-soft text-ink-0"
                    : "border-rule bg-panel-2 text-ink-1 hover:z-10 hover:border-ink-2",
                  s.daDuyet && !cur && "border-ok/60",
                  bad && "hatch-left pl-3",
                )}
                style={{ left: s.start * pxPerSec, width: (s.end - s.start) * pxPerSec }}
                onPointerDown={(e) => {
                  e.stopPropagation();
                  onSelect(s.i);
                }}
                title={`${chu} · ${formatTimecode(s.start)} → ${formatTimecode(s.end)}`}
              >
                {chu}
                <span
                  className="absolute inset-y-0 left-0 w-1.5 cursor-ew-resize opacity-0 group-hover:opacity-100 bg-signal/60"
                  onPointerDown={(e) => startDrag(e, s.i, "start")}
                  aria-label="Kéo giờ vào"
                />
                <span
                  className="absolute inset-y-0 right-0 w-1.5 cursor-ew-resize opacity-0 group-hover:opacity-100 bg-signal/60"
                  onPointerDown={(e) => startDrag(e, s.i, "end")}
                  aria-label="Kéo giờ ra"
                />
              </div>
            );
          })}
        </div>
        {/* đầu phát */}
        <div
          className="pointer-events-none absolute top-0 bottom-0 w-px bg-signal"
          style={{ left: time * pxPerSec }}
        >
          <span className="absolute -left-[4px] top-0 h-2 w-[9px] bg-signal [clip-path:polygon(0_0,100%_0,50%_100%)]" />
        </div>
      </div>
    </div>
  );
}
