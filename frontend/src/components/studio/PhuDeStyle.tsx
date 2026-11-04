import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import {
  FONT_CHO_PHEP, hinhHocVideo, STYLE_MAC_DINH, styleChoAss, type PhuDeStyle,
} from "@/lib/phuDeStyle";
import { hopVideo } from "@/lib/hopVideo";
import { subtitleLines, type KhoiChu } from "@/api/endpoints";

/**
 * BẺ DÒNG như bản burn — tham lam theo TỪ, cùng file font, cùng bề ngang.
 *
 * 🔴 VÌ SAO PHẢI CÓ: `width: fit-content` + `maxWidth` KHÔNG co theo dòng đã bẻ (nó lấy
 * `max-content` rồi kẹp ở `maxWidth`), nên hộp trong bản xem trước rộng bằng CẢ bề ngang
 * bẻ dòng — đo được **1012 px** (93,7 % video) trong khi bản burn **449 px** (41,6 %).
 *
 * Luật y hệt `subtitle_format._do_khoi_chu` của backend (greedy theo từ, bẻ ở khoảng
 * trắng gần nhất, từ nào dài hơn cả dòng thì để nguyên) và cùng bề ngang
 * `PlayResX − 2·lề` — nếu hai bên bẻ khác nhau thì hộp và số dòng cũng khác nhau.
 *
 * Không có `canvas` (jsdom) thì trả MỘT dòng: không đo được thì không bẻ bừa.
 */
function beDong(chu: string, font: {
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  fontStyle: string;
}, rongKhaDung: number): string[] {
  const tu = chu.split(/\s+/).filter((x) => x !== "");
  if (tu.length <= 1) return [chu];
  let ctx: CanvasRenderingContext2D | null = null;
  try {
    ctx = document.createElement("canvas").getContext("2d");
  } catch {
    ctx = null;
  }
  if (ctx === null) return [chu];
  ctx.font = `${font.fontStyle} ${font.fontWeight} ${font.fontSize}px ${font.fontFamily}`;
  const rong = (s: string) => ctx!.measureText(s).width;

  const ra: string[] = [];
  let hien = "";
  for (const w of tu) {
    const thu = hien === "" ? w : hien + " " + w;
    if (hien !== "" && rong(thu) > rongKhaDung) {
      ra.push(hien);
      hien = w;
    } else {
      hien = thu;
    }
  }
  if (hien !== "") ra.push(hien);
  return ra.length > 0 ? ra : [chu];
}

/**
 * Bản xem trước phụ đề ĐÈ LÊN video.
 *
 * Vì sao phải đo khung bằng `ResizeObserver` chứ không dùng đơn vị CSS linh hoạt: kiểu chữ
 * được khai trong hệ `.ass` (1920×1080), và backend nhân tỉ lệ theo trục NGẮN của khung
 * THẬT. Muốn xem trước đúng thì phải biết kích thước thật của khung chứa video, rồi áp
 * CÙNG công thức (`hinhHocVideo` dùng y hệt `to_ass`), rồi thu bằng `transform`.
 *
 * 🔴 VÀ PHẢI ĐO HỘP HIỂN THỊ THẬT CỦA VIDEO, không phải khung chứa — xem `lib/hopVideo`:
 * `<video>` dùng `object-contain`, nên video dọc trong khung 16:9 chỉ chiếm ~31 % bề ngang.
 * Đặt chữ theo khung chứa thì chữ to gấp ~3 lần và trải ra ngoài hình.
 */
export function PhuDeOverlay({
  style,
  text,
  videoRef,
}: {
  style: PhuDeStyle;
  text: string;
  /** Thẻ `<video>` để đọc tỉ lệ thật. Thiếu nó thì đo theo khung chứa (hành vi cũ). */
  videoRef?: React.RefObject<HTMLVideoElement | null>;
}) {
  const hopRef = useRef<HTMLDivElement>(null);
  const [khung, setKhung] = useState({ rong: 0, cao: 0 });
  const [tiLeVideo, setTiLeVideo] = useState({ rong: 0, cao: 0 });

  useLayoutEffect(() => {
    const el = hopRef.current;
    if (el === null) return;
    const do_ = () => {
      setKhung({ rong: el.clientWidth, cao: el.clientHeight });
      const v = videoRef?.current;
      setTiLeVideo({ rong: v?.videoWidth ?? 0, cao: v?.videoHeight ?? 0 });
    };
    do_();
    // `ResizeObserver` có thể không có trong môi trường test — bỏ qua là an toàn, vì khi đó
    // kích thước đã đọc được một lần ở trên và bản xem trước vẫn hiện (chỉ không tự co giãn).
    const v = videoRef?.current;
    v?.addEventListener("loadedmetadata", do_);
    v?.addEventListener("resize", do_);
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(do_);
    ro?.observe(el);
    return () => {
      ro?.disconnect();
      v?.removeEventListener("loadedmetadata", do_);
      v?.removeEventListener("resize", do_);
    };
  }, [videoRef]);

  //: 🔴 DÒNG LẤY TỪ BACKEND, KHÔNG tự bẻ. Bản burn bẻ bằng Pillow, `canvas` của trình duyệt
  //: cho câu trả lời KHÁC (~10 % bề ngang chữ ở đúng chỗ quyết định bẻ dòng), nên tự bẻ ở
  //: đây là hai bên lệch SỐ DÒNG. `beDong` chỉ còn là đường DỰ PHÒNG khi chưa gọi được API.
  //:
  //: ⚠️ HOOK NÀY PHẢI NẰM TRƯỚC MỌI `return` SỚM. Bản đầu tôi đặt nó ngay chỗ dùng (sau
  //: `if (text === "" …) return …`), và React ném "Rendered more hooks than during the
  //: previous render" → cả trang thành "Trang này không tải được". Rules of Hooks không
  //: phải hình thức: một `return` sớm ở giữa là đủ để số hook đổi giữa hai lượt render.
  const [khoiApi, setKhoiApi] = useState<KhoiChu | null>(null);
  //: Khoá phụ thuộc là CHUỖI của style: `style` là object, so sánh tham chiếu sẽ gọi lại
  //: API mỗi lượt render (Studio re-render theo `player.time`, tức ~60 lần/giây).
  const styleKhoa = JSON.stringify(style);
  useEffect(() => {
    if (tiLeVideo.rong <= 0 || tiLeVideo.cao <= 0 || text === "") return;
    let con = true;
    subtitleLines(text, [tiLeVideo.rong, tiLeVideo.cao],
                  JSON.parse(styleKhoa) as Record<string, unknown>)
      .then((r) => {
        if (con) setKhoiApi(r);
      })
      .catch(() => {
        // API hỏng ⇒ giữ đường dự phòng (canvas). Không được làm sập khung xem.
        if (con) setKhoiApi(null);
      });
    return () => {
      con = false;
    };
  }, [text, styleKhoa, tiLeVideo.rong, tiLeVideo.cao]);

  const hop = hopVideo(khung.rong, khung.cao, tiLeVideo.rong, tiLeVideo.cao);

  //: Chưa đo được hộp video (jsdom, hoặc video chưa có metadata) thì KHÔNG vẽ: hộp vẽ theo
  //: kích thước khung CHỨA là một hộp sai, và sai im lặng còn tệ hơn không vẽ.
  if (text === "" || hop.rong === 0 || hop.cao === 0
      || tiLeVideo.rong <= 0 || tiLeVideo.cao <= 0) {
    return <div ref={hopRef} className="pointer-events-none absolute inset-0" />;
  }

  // ── DỰNG TRONG HỆ PIXEL CỦA VIDEO, RỒI THU BẰNG `transform` ─────────────────────────
  //
  // 🔴 ĐÂY LÀ CÁCH HẾT LỆCH SO VỚI BẢN BURN (chủ dự án: *"tìm cách để phụ đề trên web ko
  // lệch so với bản burn vào video"*). Đặt `font-size` theo px của khung hiển thị (bản cũ)
  // thì ở khung 132 px, `co = 30` ra 2,06 px — Chrome không cho ký tự hẹp hơn ~1 px, nên
  // 85 ký tự chiếm 82 px (0,96 px/ký tự) trong khi bản burn cần 0,61: hộp xem trước rộng
  // 62 % khung, bản burn 41,6 %.
  //
  // Nay mọi số tính bằng pixel VIDEO — đúng hệ `PlayRes` của `.ass` (`hinhHocVideo` dùng
  // Y HỆT công thức `to_ass`) — và CẢ KHỐI được thu bằng `scale(hop.rong / videoW)`.
  // Layout chạy ở cỡ chữ THẬT (17 px), nơi số đo của trình duyệt đáng tin; phép thu là
  // tuyến tính nên tỉ lệ chữ / hộp / khung khớp bản burn.
  const h = hinhHocVideo(style, tiLeVideo.rong, tiLeVideo.cao);
  const sx = hop.rong / tiLeVideo.rong;
  const coHop = style.kieuVien === 3;
  const hopRieng = coHop && style.caoHop > 0;
  const ngangTuDong = hopRieng && style.rongHop <= 0;
  //: `rong_hop` / `cao_hop` ĐÃ là pixel của VIDEO (`to_ass` dùng thẳng, chỉ kẹp theo
  //: `PlayRes`) nên trong hệ này KHÔNG nhân tỉ lệ gì thêm — nhân nữa là nhân hai lần.
  const wHop = style.rongHop;
  const hHop = style.caoHop;
  //: Bề ngang libass bẻ dòng = `PlayResX − 2·lề` (`rong_kha_dung` bên `to_ass`).
  const rongKhaDung = Math.max(40, tiLeVideo.rong - 2 * h.le);
  //: BẺ DÒNG NGAY Ở ĐÂY, y hệt luật của bản burn (tham lam theo TỪ, bề ngang
  //: `PlayResX − 2·lề`) và bằng CÙNG file font.
  //:
  //: 🔴 VÌ SAO PHẢI TỰ BẺ: `width: fit-content` + `maxWidth` KHÔNG co theo dòng đã bẻ —
  //: nó lấy `max-content` rồi kẹp ở `maxWidth`, nên hộp rộng bằng CẢ bề ngang bẻ dòng.
  //: ĐO ĐƯỢC trên app: hộp xem trước **1012 px** (93,7 % bề ngang video) trong khi bản
  //: burn **449 px** (41,6 %) cho đúng câu đó. Có dòng tường minh rồi thì `max-content`
  //: CHÍNH LÀ dòng dài nhất, và hộp mới bám chữ được như bản burn.
  const dongChu = khoiApi !== null && khoiApi.lines.length > 0
    ? khoiApi.lines
    : beDong(text, {
        fontFamily: style.font + ", system-ui, sans-serif",
        fontSize: h.coChu,
        fontWeight: style.dam ? 700 : 400,
        fontStyle: style.nghieng ? "italic" : "normal",
      }, rongKhaDung);
  const caoDong = h.coChu * 1.25;
  //: Chiều cao hộp = `max(cao_hop, chữ + 2·viền)` — ĐÚNG luật `to_ass`.
  const caoHopThat = Math.max(
    hHop,
    (khoiApi !== null && khoiApi.cao > 0 ? khoiApi.cao : dongChu.length * caoDong) + 2 * h.vien,
  );
  //: Bề rộng hộp khi API đã trả số: `rong + 2·viền` (đúng `to_ass`), khỏi phụ thuộc
  //: `max-content` của trình duyệt — chính chỗ từng làm hộp rộng 1013/1963 px.
  const rongKhoiThat = khoiApi !== null && khoiApi.rong > 0
    ? Math.min(tiLeVideo.rong, khoiApi.rong + 2 * h.vien)
    : null;
  const noiDung = {
    fontFamily: style.font + ", system-ui, sans-serif",
    fontSize: `${h.coChu}px`,
    lineHeight: 1.25,
    fontWeight: style.dam ? 700 : 400,
    fontStyle: style.nghieng ? "italic" : "normal",
    color: style.mauChu,
    textAlign: (style.canLe === 1 ? "left" : style.canLe === 3 ? "right" : "center") as
      "left" | "right" | "center",
    //: Dòng do TA bẻ ⇒ cấm trình duyệt bẻ lại (bẻ lại là hai bên lệch nhau lần nữa).
    whiteSpace: "pre" as const,
  };

  return (
    <div ref={hopRef} className="pointer-events-none absolute inset-0">
      <div
        style={{
          position: "absolute",
          left: hop.trai,
          top: hop.tren,
          width: tiLeVideo.rong,
          height: tiLeVideo.cao,
          transform: `scale(${sx})`,
          transformOrigin: "top left",
        }}
      >
        <div
          className="absolute"
          style={{
            // Neo trong HỘP VIDEO, không trong khung chứa: `left/top` là viền đen bị bỏ.
            ...(hopRieng
              ? (ngangTuDong
                  // ngang = 0: hộp ÔM CHỮ.
                  //
                  // 🔴 CÓ SỐ TỪ BACKEND THÌ DÙNG THẲNG `rong + 2·viền` — đó đúng là công
                  // thức `to_ass` dùng để vẽ hộp. Không có (API chưa về / hỏng) thì lùi về
                  // `fit-content` với các dòng đã bẻ: `max-content` khi đó là dòng dài nhất.
                  ? { left: 0, right: 0,
                      width: rongKhoiThat !== null ? rongKhoiThat : "fit-content",
                      ...(rongKhoiThat === null
                        ? { marginLeft: "auto", marginRight: "auto" } : {}),
                      minHeight: caoHopThat, boxSizing: "border-box" as const }
                  : { left: (tiLeVideo.rong - wHop) / 2, width: wHop,
                      minHeight: caoHopThat, boxSizing: "border-box" as const })
              : { left: h.le, width: rongKhaDung }),
            ...(hopRieng ? { display: "flex", flexDirection: "column" as const,
                             alignItems: style.canLe === 1 ? "flex-start"
                               : style.canLe === 3 ? "flex-end" : "center",
                             justifyContent: "center" } : {}),
            // `cachDay` đã ở hệ pixel video: đáy hộp cách đáy KHUNG HÌNH đúng bằng
            // `offset_doc` — cùng mốc `pos_y = round(cao × (1 − offset))` bên `to_ass`.
            bottom: h.cachDay,
            ...noiDung,
            ...(coHop
              ? {
                  // Độ đục của hộp đi qua `rgba` chứ không qua `opacity` của cả khối:
                  // `opacity` sẽ làm mờ LUÔN chữ, trong khi `.ass` chỉ trong suốt cái hộp.
                  background: rgba(style.mauHop, style.doDucHop),
                  // Đệm = `vien` ĐỦ BỐN PHÍA, đúng như bản burn cộng `2·viền` vào cả hai
                  // chiều (`rong_dong = max(rong_hop, chữ + 2·viền)`).
                  padding: hopRieng ? Math.max(0, h.vien)
                    : `${Math.max(1, h.vien)}px ${Math.max(2, h.vien * 2)}px`,
                }
              : {
                  // Chỉ viền quanh NÉT chữ: CSS không có viền chữ, nên dựng bằng 4 bóng lệch.
                  textShadow: [
                    `${h.vien}px 0 0 ${style.mauHop}`,
                    `-${h.vien}px 0 0 ${style.mauHop}`,
                    `0 ${h.vien}px 0 ${style.mauHop}`,
                    `0 -${h.vien}px 0 ${style.mauHop}`,
                  ].join(", "),
                }),
          }}
        >
          {/*: MỖI DÒNG LÀ MỘT KHỐI, không phải `<br>`.
                🔴 ĐO ĐƯỢC: với `<br>`, `max-content` của hộp vẫn tính CẢ CÂU trên một
                dòng (hộp ra **1963 px** trong khi dòng dài nhất chỉ **947**) — Chrome
                không trừ `<br>` khi tính `max-content`, nên `fit-content` không ôm chữ.
                Ba khối thì bề rộng hộp = bề rộng khối rộng nhất = đúng dòng dài nhất. */}
          {dongChu.map((d, i) => (
            <div key={i}>{d}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * Đo hộp hiển thị thật của video trong một phần tử chứa — dùng cho lớp đè KHÔNG phải React
 * (hộp vùng đọc OCR đặt theo `%` của phần tử cha).
 *
 * Trả `null` khi chưa đo được: bên gọi phải coi đó là "chưa vẽ", không phải "hộp 0×0".
 */
export function dungHopVideo(
  chua: HTMLElement | null,
  video: HTMLVideoElement | null,
): { trai: number; tren: number; rong: number; cao: number } | null {
  if (chua === null) return null;
  const hop = hopVideo(chua.clientWidth, chua.clientHeight, video?.videoWidth ?? 0,
                       video?.videoHeight ?? 0);
  return hop.rong > 0 && hop.cao > 0 ? hop : null;
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
 * Khung xem trước: CHÍNH video đang mở, kèm chữ đè lên nó.
 *
 * Vì sao một thẻ `<video>` RIÊNG chứ không dời thẻ của studio vào đây: dời thì mất trạng
 * thái phát ở khung chính, và đóng hộp thoại là video nhảy về đầu. Thẻ này `muted`, nhảy
 * tới đúng mốc đang xem khi mở, và có thanh kéo riêng để soi các câu khác nhau.
 *
 * Chữ lấy theo CÙNG luật với khung chính (`playingSeg`): đoạn LỚP 1 phủ thời điểm hiện tại,
 * hiện bản dịch nếu có. Khác luật là bản xem trước dạy người dùng một điều mà video thật
 * không làm.
 */
export function PhuDePreviewPlayer({
  src,
  doan,
  style,
  batDau,
}: {
  src: string | null;
  doan: Array<{ start: number; end: number; text: string; dich: string; layer: string | null }>;
  style: PhuDeStyle;
  batDau: number;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [luc, setLuc] = useState(batDau);
  // 🔴 `batDau` chỉ được dùng để ĐẶT MỐC MỘT LẦN khi mở. Không đưa nó vào dependency:
  // `player.time` đổi MỖI FRAME khi video đang phát, nên effect sẽ chạy lại liên tục và
  // kéo khung xem trước giật về mốc cũ — không xem được gì.
  const mocDau = useRef(batDau);
  mocDau.current = batDau;

  useEffect(() => {
    const v = videoRef.current;
    if (v === null) return;
    const den = () => {
      try {
        v.currentTime = mocDau.current;
      } catch {
        // Chưa có metadata thì `currentTime` ném; bỏ qua, `loadedmetadata` sẽ gọi lại.
      }
    };
    v.addEventListener("loadedmetadata", den);
    den();
    return () => v.removeEventListener("loadedmetadata", den);
  }, [src]);

  const dang = doan.find((s) => s.layer === "mot_nguon" && luc >= s.start && luc < s.end);

  return (
    <div className="mb-3">
      <div className="relative aspect-video w-full overflow-hidden rounded-sm border border-rule bg-panel-0">
        <video
          ref={videoRef}
          src={src ?? undefined}
          muted
          playsInline
          className="size-full object-contain"
          onTimeUpdate={(e) => setLuc(e.currentTarget.currentTime)}
        />
        {dang && (
          <PhuDeOverlay
            style={style}
            text={dang.dich === "" ? dang.text : dang.dich}
            videoRef={videoRef}
          />
        )}
      </div>
      <div className="mt-1 flex items-center gap-2">
        <button
          onClick={() => {
            const v = videoRef.current;
            if (v === null) return;
            if (v.paused) void v.play();
            else v.pause();
          }}
          className="rounded-sm border border-rule px-2 py-0.5 text-[11.5px] text-ink-1 hover:border-ink-1"
        >
          phát / dừng
        </button>
        <span className="tabular-nums text-[11px] text-ink-2">{luc.toFixed(2)} s</span>
      </div>
    </div>
  );
}

/**
 * Hộp thoại chỉnh phụ đề hiển thị. Mở bằng lệnh "Chỉnh phụ đề hiển thị" trong bảng lệnh.
 *
 * Mọi thay đổi gọi `onChange` NGAY (không có nút Lưu): người dùng đang nhìn khung xem trước
 * ngay trên các ô điều khiển, nên thấy kết quả tức thì là cách duy nhất để chỉnh bằng mắt.
 */
export function PhuDeStyleDialog({
  open,
  onClose,
  style,
  onChange,
  preview,
  toiDaNgang = 1920,
  toiDaCao = 1080,
}: {
  open: boolean;
  onClose: () => void;
  style: PhuDeStyle;
  onChange: (s: PhuDeStyle) => void;
  /** Khung xem trước (video + chữ) đặt ngay dưới tiêu đề. */
  preview?: React.ReactNode;
  /**
   * Trần CỦA CHÍNH VIDEO, tính bằng pixel thật (`videoWidth`/`videoHeight`).
   *
   * 🔴 ĐO ĐƯỢC (chủ dự án: *"kéo max ngang rồi mà chưa thấy khớp cỡ video lắm"*): trần
   * từng là hằng số 1080. Video 1920 px rộng thì 1080 chỉ còn **56 %** bề ngang — kéo max
   * vẫn hụt. Trần phải là bề ngang THẬT, và `to_ass` cũng kẹp theo `PlayResX` = bề ngang
   * đó, nên hai đầu khớp nhau.
   */
  toiDaNgang?: number;
  toiDaCao?: number;
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
        className="w-[460px] max-w-[92vw] rounded-sm border border-rule bg-panel-1 p-4 shadow-2xl"
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

        {/* KHUNG XEM TRƯỚC — video THẬT đang mở, cùng thẻ `<video>` với chữ đè lên nó.
            Chỉnh tham số mà không thấy kết quả trên chính khung hình thì phải đoán, và
            đoán sai phải quay lại sửa — vòng lặp đó là lý do khung này tồn tại. */}
        {preview}

        <Truong nhan="Font">
          <select
            value={style.font}
            onChange={(e) => dat({ font: e.target.value })}
            className="rounded-sm border border-rule bg-panel-0 px-2 py-1 text-[12.5px] text-ink-0 outline-none"
            aria-label="Font"
          >
            {FONT_CHO_PHEP.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        </Truong>

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

        {/* 🔴 MỘT ô, HAI nghĩa — vì `.ass` chỉ có MỘT trường cho cả hai.
            `Style: … BorderStyle, Outline …`: `Outline` là ĐỘ DÀY VIỀN khi
            `BorderStyle = 1`, và là ĐỆM CỦA HỘP khi `BorderStyle = 3`. */}
        <Truong nhan={style.kieuVien === 3 ? "Đệm hộp" : "Độ dày viền"}>
          <input
            type="range"
            min={0}
            max={20}
            value={style.vien}
            onChange={(e) => dat({ vien: Number(e.target.value) })}
            className="w-24 accent-signal"
            aria-label={style.kieuVien === 3 ? "Đệm hộp" : "Độ dày viền"}
          />
          <input
            type="number"
            min={0}
            max={20}
            value={style.vien}
            onChange={(e) => dat({ vien: Number(e.target.value) })}
            className={oNhap}
            aria-label={style.kieuVien === 3 ? "Đệm hộp (số)" : "Độ dày viền (số)"}
          />
        </Truong>

        {/* CỠ HỘP RIÊNG — độc lập với cỡ chữ. Để `0` là TẮT (hộp suy từ đệm như cũ).
            Backend vẽ hộp bằng vector `\p1`; trần cứng là `PlayResX / 2` = 540 px. */}
        {style.kieuVien === 3 && (
          <>
            <Truong nhan="Cỡ hộp ngang">
              <input
                type="number"
                min={0}
                max={toiDaNgang}
                step={10}
                value={style.rongHop}
                onChange={(e) => dat({ rongHop: Number(e.target.value) })}
                className={oNhap}
                aria-label="Cỡ hộp ngang"
              />
            </Truong>
            <Truong nhan="Cỡ hộp cao">
              <input
                type="number"
                min={0}
                max={toiDaCao}
                step={10}
                value={style.caoHop}
                onChange={(e) => dat({ caoHop: Number(e.target.value) })}
                className={oNhap}
                aria-label="Cỡ hộp cao"
              />
            </Truong>
            <p className="mt-1 text-[11px] leading-4 text-ink-2">
              Để <span className="kbd">0</span> là hộp tự co theo chữ (dưới 40 px cũng coi là tắt).
              Tối đa <span className="num">{toiDaNgang}</span> × <span className="num">{toiDaCao}</span> px (bằng cỡ video).
            </p>
          </>
        )}

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
