import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Dong } from "@/lib/studio";
import { mauLop, viecCuaDong, NHAN_LOP } from "@/lib/studio";
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

  /**
   * BAT/TAT TUNG LOP — kieu bang Layers trong Photoshop.
   *
   * Nguoi dung: "Layer nghia la nhu layer trong photoshop y. Ko phai dua vao so nguon, no chi
   * la chua doan nao doan nao xong luc bat layer nay thi no hien cac doan tren layer do".
   *
   * Mac dinh bat CA HAI: do la trang thai dang dung hien nay, va tat di la mot thay doi
   * nguoi dung khong yeu cau.
   */
  const [lopBat, setLopBat] = useState({ mot_nguon: true, hai_nguon: true });

  // Loc TRUOC khi xep lan: tat mot lop thi khoi cua lop do khong duoc ve, va khong
  // chiem cho trong `xepLan` (neu loc sau, cac khoi con lai van bi day xuong lan trong).
  const segmentsLoc = segments.filter((s) => s.layer === null || lopBat[s.layer]);
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
  /**
   * Khoang thoi gian VE cua tung doan — KHAC `s.start`/`s.end` o mot cho duy nhat:
   * doan OCR nam gon trong mot doan ASR thi keo cho bang doan ASR do.
   *
   * Nguoi dung: "timestamp dau cuoi thi keo cho bang cua asr vua swap y".
   *
   * Do duoc tren transcript #41: **25 cap ASR bao OCR** (23 cap bao MOT doan, 2 cap bao
   * HAI doan):
   *
   *     ASR i=1  [0.00-1.14]  bao  OCR i=0 [0.00-1.04]   ->  OCR [0.00-1.14]
   *     ASR i=7  [7.02-9.66]  bao  OCR i=8 [7.50-8.00]   ->  OCR [7.02-8.00]
   *                                OCR i=9 [8.00-9.10]   ->  OCR [8.00-9.66]
   *
   * Quy tac: ASR bao MOT OCR -> OCR lay nguyen [start, end] cua ASR. ASR bao NHIEU OCR
   * -> OCR dau lay `start` cua ASR, OCR cuoi lay `end` cua ASR, cac OCR giua giu nguyen.
   *
   * Chi doi KHOANG VE. `Segment.start`/`end` that giu nguyen — do la moc may do duoc,
   * ban long va xuat file van dung no.
   */
  const khoangVe = (() => {
    const dungSai = 0.05;
    const bao = (ngoai: Dong, trong: Dong) =>
      trong.start >= ngoai.start - dungSai &&
      trong.end <= ngoai.end + dungSai &&
      trong.end - trong.start < ngoai.end - ngoai.start;

    const asr = segmentsLoc.filter((s) => s.suspect);
    const ocr = segmentsLoc.filter((s) => !s.suspect);
    const keo = new Map<number, { start: number; end: number }>();

    for (const a of asr) {
      const trong = ocr.filter((o) => bao(a, o)).sort((x, y) => x.start - y.start);
      if (trong.length === 0) continue;
      trong.forEach((o, k) => {
        const dau = k === 0 ? a.start : o.start;
        const cuoi = k === trong.length - 1 ? a.end : o.end;
        keo.set(o.i, { start: dau, end: Math.max(dau + 0.01, cuoi) });
      });
    }
    // Tra MAP theo `s.i`, KHONG theo chi so mang: vong ve dung `segmentsLoc` (da loc
    // theo lop), nen chi so hai mang khac nhau. Tra theo khoa `i` thi khong lech.
    const ra = new Map<number, { start: number; end: number }>();
    for (const s of segmentsLoc) ra.set(s.i, keo.get(s.i) ?? { start: s.start, end: s.end });
    return ra;
  })();

  // XEP LAN THEO LOP — lop 1 la lan tren, lop 2 la lan duoi.
  //
  // Nguoi dung: "Bam theo LOP — lop 1 lan tren, lop 2 lan duoi".
  //
  // 🔴 BAN TRUOC SAI O DAY: `xepLan` chia lan theo CHONG LAN THOI GIAN, roi con doi cho
  // ASR/OCR theo `suspect`. Ket qua do duoc: tat lop 1 di (con 52 khoi cua lop 2) thi
  // timeline VAN con hai lan, vi lop 2 chua ca OCR lan ASR cua cung nhung cau do.
  //
  //     lop 1: 94 dong = 35 OCR + 59 ASR
  //     lop 2: 52 dong = 27 OCR + 25 ASR
  //
  // Nen lan va mau phai bam theo LOP, khong theo nguon chu. Trong cung mot lop, neu hai
  // khoi chong thoi gian (mot cau co ca OCR lan ASR cung thuoc lop do) thi khoi sau xuong
  // lan phu — nhung do la ngoai le, khong phai luat chia lan.
  const xepLan = (() => {
    const ra = new Map<number, { lan: number; rong: number; trai: number }>();

    // LAN CO DINH THEO LOP: lop 1 -> 0, lop 2 -> 1, chua ro -> 0.
    //
    // 🔴 BAN TRUOC SAI: `while (lan < cuoiMoiLan.length && ...) lan++` day XUYEN LOP.
    // Do tren #44 (146 doan):
    //
    //     ca hai lop  146 khoi
    //       top1  : 115 khoi = 52 OCR + 63 ASR
    //       top19 :  30 khoi =  8 OCR + 22 ASR   <- 8 dong LOP 1 nam o lan LOP 2
    //       top37 :   1 khoi =  1 OCR            <- lan thu ba, khong lop nao can
    //
    // Nguyen nhan: lop 1 co 7 cap dong CHONG THOI GIAN. Gap cap do, vong `while` day
    // khoi xuong `lan=1` — dung bang lan cua LOP 2. Nen lop 1 tran sang lan lop 2.
    //
    // LUAT DUNG: moi lop MOT lan rieng, khong bao gio day sang lan cua lop khac.
    // Trong cung lop ma hai khoi chong nhau thi khoi sau ve DE len khoi truoc — cung
    // lop chong nhau la chuyen that (mot cau co ca OCR lan ASR cung lop), va nguoi doc
    // can thay no de soat.
    for (const s of segmentsLoc) {
      const kv = khoangVe.get(s.i) ?? { start: s.start, end: s.end };
      const trai = kv.start * pxPerSec;
      const rong = Math.max(2, (kv.end - kv.start) * pxPerSec);
      ra.set(s.i, { lan: s.layer === "hai_nguon" ? 1 : 0, rong, trai });
    }
    return ra;
  })();

  const soLan = [...xepLan.values()].reduce((m, b) => Math.max(m, b.lan + 1), 1);
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
    <div className="border-t border-rule bg-panel-1">
      {/*
        BANG LOP — bat/tat tung lop, kieu bang Layers trong Photoshop.
        Nguoi dung: "bat layer nay thi no hien cac doan tren layer do".
        Mac dinh bat CA HAI: do la trang thai dang dung, tat di la thay doi khong ai yeu cau.
      */}
      <div className="flex items-center gap-1.5 border-b border-rule px-2 py-1">
        <span className="label-engraved mr-1 !text-ink-2">lớp</span>
        {(["mot_nguon", "hai_nguon"] as const).map((lop) => (
          <button
            key={lop}
            type="button"
            onClick={() => setLopBat((cu) => ({ ...cu, [lop]: !cu[lop] }))}
            aria-pressed={lopBat[lop]}
            title={`${NHAN_LOP[lop]} — ${lopBat[lop] ? "đang hiện" : "đang ẩn"}`}
            className={cn(
              "num rounded-sm border px-1.5 py-0.5 text-[10.5px] transition-colors",
              lopBat[lop]
                ? "border-signal bg-signal-soft text-ink-0"
                : "border-rule text-ink-2 hover:border-ink-1 hover:text-ink-1",
            )}
          >
            {NHAN_LOP[lop]}
          </button>
        ))}
        <span className="num ml-auto text-[10px] text-ink-2">
          {segmentsLoc.length}/{segments.length}
        </span>
      </div>

      <div
        ref={scrollRef}
        className="relative overflow-x-auto overflow-y-hidden bg-panel-0"
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
            {segmentsLoc.map((s) => {
              const b = xepLan.get(s.i)!;
              const bad = viecCuaDong(s).length > 0;
              const cur = s.i === currentId;
              const mau = mauLop(s);
              const chu = s.dich === "" ? s.text : s.dich;
              return (
                <div
                  key={s.i}
                  className={cn(
                    "group absolute overflow-hidden truncate rounded-sm border px-1.5 text-[10.5px] leading-[16px] whitespace-nowrap transition-colors",
                    cur
                      ? "z-10 border-signal bg-signal-soft text-ink-0"
                      : cn(mau.vien, mau.nen, "text-ink-1 hover:z-10"),
                    s.daDuyet && !cur && "border-ok/60",
                    bad && "hatch-left pl-3",
                  )}
                  style={{
                    // `b.trai`/`b.rong` den tu `xepLan`, da keo theo ASR bao no.
                    left: b.trai,
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
    </div>
  );
}
