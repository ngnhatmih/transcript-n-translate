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

  // vẽ sóng
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
        style={{ width, height: H + 52 }}
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
        {/* khối đoạn */}
        <div className="absolute inset-x-0 bottom-0 h-8">
          {segments.map((s) => {
            const bad = viecCuaDong(s).length > 0;
            const cur = s.i === currentId;
            return (
              <div
                key={s.i}
                className={cn(
                  "group absolute top-1 bottom-1 overflow-hidden text-ellipsis rounded-sm border px-1.5 text-[10.5px] leading-[22px] whitespace-nowrap transition-colors",
                  cur
                    ? "border-signal bg-signal-soft text-ink-0"
                    : "border-rule bg-panel-2 text-ink-1 hover:border-ink-2",
                  s.daDuyet && !cur && "border-ok/60",
                  bad && "hatch-left pl-3",
                )}
                style={{ left: s.start * pxPerSec, width: (s.end - s.start) * pxPerSec }}
                onPointerDown={(e) => {
                  e.stopPropagation();
                  onSelect(s.i);
                }}
                title={s.dich === "" ? s.text : s.dich}
              >
                {/*
                  CHU TRONG KHOI DOAN — chi hien khi khoi du rong.

                  DO THAT tren du lieu that: 438 doan trong 49669px, doan #1 rong 81,6px con
                  doan #2 rong 48,8px. Mot cau tieng Viet dai 40-60 ky tu can ~250px; ve no
                  trong 48px thi `overflow-hidden` cat con mot manh vo nghia ("Ban chac chan").

                  Nguong 60px la so DO, khong phai cam tinh: duoi 60px mot cau bat dau bang
                  mot tu tieng Viet thong thuong (~7 ky tu x 6,3px = 44px) cong padding 12px
                  da khong con cho. Duoi nguong do, khoi chi la mot vach thoi gian — dung
                  nghia cua no o muc thu phong 40px/s.
                */}
                {(s.end - s.start) * pxPerSec >= 60 && (s.dich === "" ? s.text : s.dich)}
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
