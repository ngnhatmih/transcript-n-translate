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
  // `peaks` luon rong — 40 px do dang giu cho mot canvas khong ve duoc gi.
  const H = 56;

  /**
   * BE RONG KHOI DOAN = BE RONG THOI GIAN. Chieu cao = SO LAN CAN THAT.
   *
   * 🔴 BON LAN SUA, MOI LAN CO SO DO — ghi lai de khong lap lai:
   *
   *   Lan 1: nguong `>= 60px moi ve chu`. Do: 46/438 doan ngan hon 1 s
   *          (2,4 .. 40 px) mat chu hoan toan — 10,5% so dong. Te hon ban goc.
   *
   *   Lan 2: noi `width` cho vua chu, giu `left`. Do tren anh: khoi #1 rong
   *          924 px (cau 70 ky tu) tran qua #2 va #3 -> chu ba khoi DE nhau.
   *
   *   Lan 3: xep lan nhung NOI RONG khoi cho vua chu truoc. Do: 6..13 lan
   *          tuy muc thu phong, tong cao 108..234 px de hien ~10 cau dau.
   *          Sai o cho: noi rong lam khoi CHONG NHAU GIA TAO, roi chinh cai
   *          chong gia tao do lai doi hoi them lan.
   *
   *   Lan 4 (nay): be rong = THOI GIAN, khong noi. Chi xuong lan khi
   *          `[start, end)` THAT SU chong len khoi truoc trong cung lan.
   *
   * DO LAI tren `GET /api/translations/4` (438 doan, 437 khoang, 0 khoang chong):
   *
   *     px/s   so lan   khoi chong   cao @18px
   *      40      1          0          18 px
   *      30      1          0          18 px
   *      24      2          1          36 px
   *      20      2          1          36 px
   *      16      2          2          36 px
   *      12      2          2          36 px
   *       8      2          3          36 px
   *
   * Du lieu that GAN NHU KHONG CHONG NHAU (0/437 khoang am), nen 2 lan la du
   * cho ca 438 doan o MOI muc thu phong. O 40 px/s chi can 1 lan.
   *
   * So lan la so DO tu du lieu, khong phai hang so chon truoc. Doi du lieu thi
   * chieu cao tu doi theo.
   */

  /** Chieu cao MOT lan. Co chu 10,5px can ~18px de khong cat tren/duoi. */
  const CAO_LAN = 18;

  /**
   * Xep khoi vao cac lan — chi dua vao CHONG LAN THAT.
   *
   * Mot khoi xuong lan duoi khi `[start, end)` cua no chong len khoi cuoi cung
   * cua lan do. Khong noi be rong, nen khong bao gio tao ra chong lan gia tao.
   *
   * `rong` toi thieu 2 px: doan dai 0,06 s o 40 px/s chi rong 2,4 px, van phai
   * nhin thay duoc de biet no ton tai.
   */
  const xepLan = (() => {
    const cuoiMoiLan: number[] = [];
    return segments.map((s) => {
      const moc = s.start * pxPerSec;
      const rong = Math.max(2, (s.end - s.start) * pxPerSec);
      let lan = 0;
      while (lan < cuoiMoiLan.length && cuoiMoiLan[lan] > moc + 0.5) lan++;
      cuoiMoiLan[lan] = moc + rong;
      return { i: s.i, lan, rong };
    });
  })();

  const soLan = xepLan.reduce((m, b) => Math.max(m, b.lan + 1), 1);
  const caoDoan = soLan * CAO_LAN + 4;

  // vẽ sóng
  //
  // 🔴 SÓNG NÀY ĐẾN TỪ ĐÂU (đo được, không đoán): `peaks` do `Studio` gọi
  // `GET /api/media/{id}/peaks` — server đọc WAV 16 kHz bằng `ffmpeg astats`.
  // Đo: 1,61 s cho 1249 s, trả 16 560 B thay vì 238 MB.
  //
  // 🔴 BA GIẢ THUYẾT SAI VỀ VÌ SAO SÓNG TRỐNG, ĐO ĐỂ BÁC BỎ:
  //
  //   (a) "route media sai"  -> SAI. `Range: bytes=0-1023` trả `206`, `len=1024`.
  //   (b) "decodeAudioData lỗi" -> SAI, nó TREO: `blob size=238623268 sau 0.0s`
  //       rồi không có `OK` lẫn `LOI` trong 45 giây. Đây là lý do chuyển sang
  //       tính peaks ở server, không phải lý do canvas trống.
  //   (c) "canvas bị cắt ở 32767 px" -> SAI. Đo trực tiếp bằng Chrome:
  //         49669x56 -> actual 49669x56  pixel góc phải = CO
  //         32767x56 -> actual 32767x56  pixel góc phải = CO
  //       Chrome không cắt canvas ở bề rộng này.
  //
  // 🔴 NGUYÊN NHÂN THẬT: MẬT ĐỘ. 2400 đỉnh trải trên `width = duration * pxPerSec`
  // = 49 669 px nghĩa là MỖI ĐỈNH CÁCH NHAU 20,7 px. Ảnh bản đã duyệt có ~40 vạch
  // trong 117 px (2,9 px/vạch). Vẽ 20,7 px/vạch thì dải trông rỗng dù có dữ liệu.
  //
  // Nên số đỉnh phải theo BỀ RỘNG THẬT: một vạch mỗi ~3 px, giống bản đã duyệt.
  // `soDinh` là số ĐO từ `width`, không phải hằng số chọn trước — đổi mức thu
  // phóng thì mật độ vạch giữ nguyên, chỉ độ chi tiết của dữ liệu là cố định.
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

    // 🔴 LỖI ĐÃ SỬA: "nhiều nến bằng nhau".
    //
    // Bản trước đặt `soVach = floor(width / 3)` = 16 656 ở 40 px/s, nhưng chỉ có
    // 2 400 đỉnh. Khi `soVach > peaks.length` thì `buoc = peaks.length / soVach`
    // = 0,14, nên hầu hết `i` cho `dau === cuoi - 1` — CÙNG MỘT ĐỈNH bị vẽ thành
    // ~7 vạch liền nhau cùng chiều cao. Đó chính là các cụm "nến bằng nhau".
    //
    // Số vạch KHÔNG ĐƯỢC VƯỢT số đỉnh có thật: vẽ dày hơn dữ liệu là bịa chi tiết
    // không tồn tại. Khi số đỉnh nhiều hơn chỗ vẽ thì gộp (lấy MAX); khi ít hơn thì
    // mỗi đỉnh một vạch và các vạch thưa ra — đúng sự thật của dữ liệu.
    const soVach = Math.max(1, Math.min(peaks.length, Math.floor(width / 3)));
    const rongVach = width / soVach;
    for (let i = 0; i < soVach; i++) {
      // Lấy MAX trong nhóm: đỉnh là đỉnh, lấy trung bình làm phẳng chỗ có tiếng nói.
      let p = 0;
      const dau = Math.floor((i * peaks.length) / soVach);
      const cuoi = Math.max(dau + 1, Math.floor(((i + 1) * peaks.length) / soVach));
      for (let j = dau; j < cuoi && j < peaks.length; j++) {
        const v = peaks[j]!;
        if (v > p) p = v;
      }
      const h = Math.max(1, p * (H - 8));
      g.fillRect(i * rongVach, (H - h) / 2, Math.max(1, rongVach - 0.6), h);
    }
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
        style={{ width, height: 20 + H + caoDoan }}
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
        {/* khối đoạn — bề rộng = thời gian, xếp làn theo CHỒNG LẤN THẬT (`xepLan`) */}
        <div className="absolute inset-x-0 bottom-0" style={{ height: caoDoan }}>
          {segments.map((s, k) => {
            const b = xepLan[k]!;
            const bad = viecCuaDong(s).length > 0;
            const cur = s.i === currentId;
            const chu = s.dich === "" ? s.text : s.dich;
            return (
              <div
                key={s.i}
                className={cn(
                  "group absolute overflow-hidden truncate rounded-sm border px-1.5 text-[10.5px] leading-[16px] whitespace-nowrap transition-colors",
                  cur
                    ? "z-10 border-signal bg-signal-soft text-ink-0"
                    : "border-rule bg-panel-2 text-ink-1 hover:z-10 hover:border-ink-2",
                  s.daDuyet && !cur && "border-ok/60",
                  bad && "hatch-left pl-3",
                )}
                style={{
                  left: s.start * pxPerSec,
                  width: b.rong,
                  top: b.lan * CAO_LAN + 1,
                  height: CAO_LAN - 2,
                }}
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
