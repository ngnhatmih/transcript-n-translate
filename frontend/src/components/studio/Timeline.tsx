import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Dong } from "@/lib/studio";
import { viecCuaDong } from "@/lib/studio";
import { formatTimecode } from "@/lib/timecode";
import { cn } from "@/lib/utils";


/**
 * ĐƯỜNG BAO SÓNG ÂM hai phía, 0..1, do server tính (`GET /api/media/{id}/peaks`).
 *
 * Hai phía KHÔNG nhất thiết bằng nhau: âm thanh thật có pha lệch, và đó là thứ
 * Premiere Pro / Audition / DaVinci Resolve vẽ ra. Một cột đối xứng quanh trục
 * giữa là kiểu "bar waveform" của player nhạc — thô hơn hẳn.
 */
export interface BaoSong {
  /** Biên độ phía trên trục, 0..1. */
  tren: number[];
  /** Độ LỚN biên độ phía dưới trục, 0..1 (client vẽ ngược lên). */
  duoi: number[];
}

interface Props {
  segments: Dong[];
  bao: BaoSong;
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
  bao,
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
  /** Vùng nhìn thấy: `[batDau, batDau + rongNhin)` theo px của dải thời gian. */
  const [khungNhin, setKhungNhin] = useState({ batDau: 0, rong: 1200 });
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
  // 🔴 ĐƯỜNG BAO LIÊN TỤC, KHÔNG PHẢI CỘT RỜI.
  //
  // Bốn lần trước tôi vẽ `fillRect` từng vạch với khe hở giữa chúng. Đó là kiểu
  // "bar waveform" của player nhạc (SoundCloud, mấy trình nghe nhạc). Premiere
  // Pro, Audition, DaVinci Resolve KHÔNG vẽ vậy: chúng vẽ ĐƯỜNG BAO — một đường
  // liên tục phía trên, một đường phía dưới, tô kín ở giữa, không khe hở.
  //
  // Ba khác biệt, cả ba đều đo được:
  //
  //   1. KHÔNG KHE. `lineTo` nối liền từng pixel; không `barGap`, không
  //      `rongVach - 0.6`. Ở 40 px/s, khe 0,6 px nhân 16 656 vạch là 10 000 px
  //      trống rải khắp dải — mắt đọc ra "răng cưa", không ra sóng.
  //
  //   2. HAI PHÍA ĐỘC LẬP. `bao.tren[i]` và `bao.duoi[i]` là hai số khác nhau
  //      (đo được: 99,8% số điểm khác nhau), vì âm thanh thật có pha lệch.
  //      Vẽ đối xứng qua trục giữa là bịa.
  //
  //   3. ĐỘ PHÂN GIẢI THEO PIXEL, KHÔNG THEO SỐ ĐIỂM. Server trả 124 924 điểm
  //      (10 ms/khung); canvas rộng 49 969 px ở 40 px/s → 2,5 điểm mỗi pixel.
  //      Mỗi pixel lấy MIN/MAX của nhóm điểm nó phủ, nên cột cuối luôn đúng
  //      biên độ đỉnh — không bị lấy mẫu thưa làm mất đỉnh.
  //
  // Màu: tô đặc bằng `fill`, và vẽ thêm đường viền mảnh cùng màu để mép trên
  // sắc nét ở màn hình retina (nếu chỉ `fill`, mép bị hoà vào nền).
  // ───────────────────────────────────────────────────────────────────────────
  // CANVAS CHỈ PHỦ KHUNG NHÌN, KHÔNG PHỦ CẢ DẢI.
  //
  // 🔴 LỖI ĐO ĐƯỢC: canvas backing store đánh địa chỉ bằng số 16-BIT, nên bề
  // rộng tối đa là 65 535 px. Vượt qua là canvas IM LẶNG KHÔNG VẼ — `width`
  // vẫn đúng, `getContext` vẫn trả về, nhưng mọi `fill`/`fillRect` biến mất,
  // không lỗi, không cảnh báo. Đo trực tiếp bằng Chrome:
  //
  //      32767x56 -> canvas 32767x56  ve duoc=CO
  //      60000x56 -> canvas 60000x56  ve duoc=CO
  //      65535x56 -> canvas 65535x56  ve duoc=CO      <- 2^16 - 1
  //      65536x56 -> canvas 65536x56  ve duoc=TRONG   <- 2^16, hong dung tai day
  //      99938x56 -> canvas 99938x56  ve duoc=TRONG
  //
  // Và dải thời gian của tệp này VƯỢT ngưỡng đó ngay khi kéo thu phóng:
  //
  //       40 px/s -> width =  49 969 px   ve duoc
  //       80 px/s -> width =  99 939 px   TRONG  <- song mat tu day
  //      120 px/s -> width = 149 908 px   TRONG
  //      160 px/s -> width = 199 878 px   TRONG
  //
  // Đó chính là lý do kéo thu phóng lên là sóng biến mất. Không phải thiếu dữ
  // liệu, không phải `bao` rỗng.
  //
  // 🔴 CÁCH SỬA: canvas rộng bằng KHUNG NHÌN, cuộn thì vẽ lại phần đang thấy.
  // Premiere Pro, Audition, Resolve đều làm vậy — không trình dựng nào giữ một
  // bitmap khổng lồ cho cả dòng thời gian. `width` của KHUNG CHỨA vẫn là
  // `duration * pxPerSec` (thanh cuộn và khối đoạn cần đúng thời gian); chỉ
  // canvas là theo khung nhìn.
  //
  // Chi phí: mỗi lần cuộn vẽ lại `rongNhin` cột (≈1 200) thay vì 199 878 — rẻ
  // hơn, và luôn vẽ được ở mọi mức thu phóng.
  // ───────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;

    // Bề rộng canvas = bề rộng khung nhìn, KHÔNG phải cả dải. `khungNhin.rong`
    // do effect theo dõi cuộn cập nhật; mặc định 1200 để lần vẽ đầu có gì đó.
    const rongVe = Math.max(1, Math.min(khungNhin.rong, 16384));
    c.width = Math.floor(rongVe * dpr);
    c.height = Math.floor(H * dpr);
    // Dịch canvas tới đúng vị trí đang nhìn, để nó phủ lên phần dải tương ứng.
    c.style.width = `${rongVe}px`;
    c.style.transform = `translateX(${khungNhin.batDau}px)`;

    const g = c.getContext("2d");
    if (!g) return;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, rongVe, H);

    const soDiem = Math.min(bao.tren.length, bao.duoi.length);
    if (soDiem === 0) {
      // Vạch giữa mảnh, đứt đoạn — nói thật "chưa có sóng", không vẽ sóng giả.
      g.fillStyle = getComputedStyle(c).color;
      const y = H / 2;
      for (let x = 0; x < rongVe; x += 6) g.fillRect(x, y, 2, 1);
      return;
    }

    const giua = H / 2;
    // Trừ 2 px mỗi phía để đỉnh cao nhất không chạm mép canvas.
    const bien = giua - 2;

    // Chỉ số điểm đầu/cuối của VÙNG ĐANG NHÌN trong mảng `bao`. Đây là phép
    // quy đổi px -> chỉ số, nên cuộn tới đâu vẽ đúng dữ liệu tới đó.
    const tiLe = soDiem / width;
    const diemDau = khungNhin.batDau * tiLe;
    const soDiemNhin = Math.max(1, rongVe * tiLe);

    // Số cột = số pixel nguyên của canvas nhìn thấy.
    const soCot = Math.max(1, Math.floor(rongVe));
    const buoc = soDiemNhin / soCot;

    // Dựng hai mảng biên độ theo cột, lấy MAX cho cả hai phía — đỉnh là đỉnh,
    // lấy trung bình sẽ làm phẳng đúng chỗ có tiếng nói.
    const tren = new Float32Array(soCot);
    const duoi = new Float32Array(soCot);
    for (let x = 0; x < soCot; x++) {
      const dau = Math.floor(diemDau + x * buoc);
      const cuoi = Math.max(dau + 1, Math.floor(diemDau + (x + 1) * buoc));
      let t = 0;
      let d = 0;
      for (let j = dau; j < cuoi && j < soDiem; j++) {
        const vt = bao.tren[j]!;
        const vd = bao.duoi[j]!;
        if (vt > t) t = vt;
        if (vd > d) d = vd;
      }
      tren[x] = t;
      duoi[x] = d;
    }

    // ĐƯỜNG BAO: một path kín đi qua đỉnh trên từ trái sang phải, rồi qua đáy
    // dưới từ phải về trái. `fill` một lần cho cả dải — liền, không khe.
    const mau = getComputedStyle(c).color;
    g.beginPath();
    g.moveTo(0, giua - tren[0]! * bien);
    for (let x = 1; x < soCot; x++) {
      const y = giua - tren[x]! * bien;
      g.lineTo(x, y);
    }
    for (let x = soCot - 1; x >= 0; x--) {
      const y = giua + duoi[x]! * bien;
      g.lineTo(x, y);
    }
    g.closePath();
    g.fillStyle = mau;
    g.fill();

    // Trục giữa: một sợi mảnh, mờ — mốc để mắt đọc biên độ hai phía.
    g.globalAlpha = 0.35;
    g.fillRect(0, giua - 0.5, rongVe, 1);
    g.globalAlpha = 1;
  }, [bao, width, khungNhin]);

  // ───────────────────────────────────────────────────────────────────────────
  // THEO DÕI CUỘN + ĐỔI BỀ RỘNG KHUNG.
  //
  // Đây là thứ làm canvas-theo-khung-nhìn hoạt động: mỗi lần cuộn hoặc resize,
  // cập nhật `[batDau, batDau + rong)` rồi effect vẽ chạy lại. Dùng
  // `useLayoutEffect` để vẽ xong TRƯỚC khi trình duyệt sơn khung hình — nếu
  // dùng `useEffect` thì có một khung hình canvas trống, mắt thấy nhấp nháy.
  //
  // `passive: true`: listener cuộn không được gọi `preventDefault`, và đánh dấu
  // passive cho trình duyệt biết để không phải chờ — cuộn mượt hơn.
  //
  // `setKhungNhin` chỉ gọi khi giá trị ĐỔI thật: so sánh trước khi set để một
  // lần cuộn 60 lần/giây không tạo 60 lần render vô ích.
  // ───────────────────────────────────────────────────────────────────────────
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const capNhat = () => {
      const batDau = Math.floor(el.scrollLeft);
      const rong = Math.ceil(el.clientWidth);
      setKhungNhin((cu) =>
        cu.batDau === batDau && cu.rong === rong ? cu : { batDau, rong },
      );
    };

    capNhat();
    el.addEventListener("scroll", capNhat, { passive: true });

    // `ResizeObserver` chứ không phải `window.resize`: khung này còn đổi bề rộng
    // khi cột trái co dãn hay thanh bên đóng/mở, mà `window.resize` không bắt
    // được những lúc đó.
    const theoDoi = new ResizeObserver(capNhat);
    theoDoi.observe(el);

    return () => {
      el.removeEventListener("scroll", capNhat);
      theoDoi.disconnect();
    };
  }, []);

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
        {/*
          Bề rộng và vị trí do effect vẽ đặt (`c.style.width`,
          `c.style.transform`) — KHÔNG khai trong JSX, vì React sẽ ghi đè lại
          `width` của cả dải và canvas lại vượt ngưỡng 65 535 px.
        */}
        <canvas
          ref={canvasRef}
          className="absolute left-0 top-5 text-wave"
          style={{ height: H }}
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
