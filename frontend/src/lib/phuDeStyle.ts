/**
 * Kiểu chữ phụ đề — MỘT mô hình, ba nơi dùng.
 *
 * Ba nơi đó là: bản xem trước trên `<video>` trong studio, tệp `.ass` tải về
 * (`GET /api/export/{id}?format=ass&style=…`), và phụ đề BURN vào video lồng tiếng
 * (`POST /api/dubs` với `style`). Nếu mỗi nơi tự đặt kiểu riêng thì chúng trôi khỏi nhau,
 * và người dùng thấy một đằng, video ra một nẻo.
 *
 * vì sao ở `lib/` chứ không ở `components/studio/`: `api/endpoints.ts` cũng phải đọc nó
 * (để gắn vào URL xuất và payload lồng tiếng), mà tầng `api` import từ `components` là
 * import ngược chiều.
 */

/** Hệ toạ độ MẶC ĐỊNH của `.ass` — trùng `_ASS_KHUNG_MAC_DINH` bên backend. */
export const HE_GOC = { rx: 1920, ry: 1080 } as const;

export interface PhuDeStyle {
  /**
   * Font chữ. CHỈ những font có ở CẢ image burn lẫn trình duyệt — xem `FONT_CHO_PHEP`
   * bên backend. Chọn một font không có trong image burn thì chữ burn khác chữ xem trước,
   * đúng thứ đang sửa.
   */
  font: string;
  /** Cỡ chữ trong hệ 1920×1080 (`ASS: Fontsize`). */
  co: number;
  /** Màu chữ `#rrggbb`. */
  mauChu: string;
  /** Màu hộp/viền `#rrggbb`. */
  mauHop: string;
  /** Độ ĐỤC của hộp, 0..1 (CSS). `0` = trong suốt, `1` = đục hẳn. */
  doDucHop: number;
  dam: boolean;
  nghieng: boolean;
  /** Độ dày viền (`ASS: Outline`) — ở chế độ hộp đục, đây là ĐỆM ĐỀU của hộp. */
  vien: number;
  /**
   * Cỡ hộp RIÊNG, theo pixel trong hệ 1920×1080 — độc lập với cỡ chữ.
   *
   * `0` = TẮT: hộp suy từ `vien` như cũ. Khác `0` (cả hai số) thì backend vẽ hộp bằng
   * vector `\p1` và sự kiện chữ nhận `\bord0\shad0` để không tự vẽ hộp thứ hai.
   *
   * ĐO ĐƯỢC: hộp khai `400×120` ra đúng `400×120` ở cả `fs54` và `fs200`. Trần cứng
   * `PlayResX / 2` = 540 px trên hệ 1080 — vượt thì libass CẮT, nên `docStyle` kẹp sẵn.
   */
  rongHop: number;
  caoHop: number;
  /** `3` = hộp đục sau chữ; `1` = chỉ viền quanh nét chữ (`ASS: BorderStyle`). */
  kieuVien: 1 | 3;
  /** Đáy khối chữ cách mép dưới khung bao nhiêu, theo tỉ lệ chiều cao (0..0.5). */
  viTriDoc: number;
  /** Neo đáy: 1 = trái, 2 = giữa, 3 = phải (`ASS: Alignment`). */
  canLe: 1 | 2 | 3;
}

/**
 * Mặc định — phải TRÙNG `_ASS_KHUNG_MAC_DINH` bên backend, nếu không thì mở hộp thoại lần
 * đầu là đổi luôn hình dạng phụ đề dù người dùng chưa bấm gì.
 *
 * `doDucHop = 0,3725` không phải số tuỳ ý: `&HA0000000` có alpha ASS `0xA0 = 160`, mà
 * alpha ASS NGƯỢC với CSS, nên alpha CSS = `255 − 160 = 95`, và `95/255 = 0,3725`.
 */
export const STYLE_MAC_DINH: PhuDeStyle = {
  font: "Archivo",
  co: 54,
  mauChu: "#ffffff",
  mauHop: "#000000",
  doDucHop: 95 / 255,
  dam: false,
  nghieng: false,
  vien: 2,
  rongHop: 0,
  caoHop: 0,
  kieuVien: 3,
  viTriDoc: 0.06,
  canLe: 2,
};

/** Khoá `localStorage`. Đổi khoá là mất kiểu chữ của mọi người dùng đang có. */
export const KHOA_LUU = "phu-de-lab:phu-de-style";

/** Font chọn được — PHẢI trùng `FONT_CHO_PHEP` của backend (`subtitle_format.py`). */
export const FONT_CHO_PHEP: readonly string[] = ["Archivo", "IBM Plex Mono"];

function so(v: unknown, macDinh: number, thap: number, cao: number): number {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return macDinh;
  return Math.min(Math.max(n, thap), cao);
}

function mau(v: unknown, macDinh: string): string {
  return typeof v === "string" && /^#[0-9a-fA-F]{6}$/.test(v) ? v.toLowerCase() : macDinh;
}

/** Kho lưu tối thiểu cần cho mô hình này — `localStorage` hoặc một vật giả trong test. */
export type KhoLuu = Pick<Storage, "getItem" | "setItem"> | undefined;

/**
 * `localStorage` của môi trường, hoặc `undefined` khi không với tới được.
 *
 * 🔴 ĐỌC QUA HÀM, KHÔNG ĐỌC THẲNG `globalThis.localStorage`: ở chế độ chặn cookie, CHÍNH
 * phép ĐỌC thuộc tính đó cũng ném `SecurityError`, nên `try/catch` phải bao cả phép đọc.
 */
function khoMacDinh(): KhoLuu {
  try {
    return globalThis.localStorage ?? undefined;
  } catch {
    return undefined;
  }
}

/** Đọc kiểu đã lưu; dữ liệu hỏng/thiếu thì rơi về mặc định TỪNG trường, không cả khối. */
export function docStyle(kho: KhoLuu = khoMacDinh()): PhuDeStyle {
  try {
    const raw = kho?.getItem(KHOA_LUU);
    if (!raw) return { ...STYLE_MAC_DINH };
    const v = JSON.parse(raw) as Partial<PhuDeStyle>;
    return {
      font: FONT_CHO_PHEP.includes(String(v.font)) ? String(v.font) : STYLE_MAC_DINH.font,
      co: so(v.co, STYLE_MAC_DINH.co, 8, 400),
      mauChu: mau(v.mauChu, STYLE_MAC_DINH.mauChu),
      mauHop: mau(v.mauHop, STYLE_MAC_DINH.mauHop),
      doDucHop: so(v.doDucHop, STYLE_MAC_DINH.doDucHop, 0, 1),
      dam: v.dam === true,
      nghieng: v.nghieng === true,
      vien: so(v.vien, STYLE_MAC_DINH.vien, 0, 20),
      // 🔴 DƯỚI 40 px COI NHƯ TẮT. ĐO ĐƯỢC: nhập `1` thì hộp co còn ~0 px và chữ bị ép
      // thành một cột dọc (ảnh chủ dự án gửi). Một hộp nhỏ hơn một ký tự không phải là
      // "hộp nhỏ", nó là hộp hỏng — nên quy về 0 (tự co theo chữ) thay vì vẽ ra rác.
      rongHop: so(v.rongHop, 0, 0, 3840) < 40 ? 0 : so(v.rongHop, 0, 0, 3840),
      caoHop: so(v.caoHop, 0, 0, 3840) < 40 ? 0 : so(v.caoHop, 0, 0, 3840),
      kieuVien: v.kieuVien === 1 ? 1 : 3,
      viTriDoc: so(v.viTriDoc, STYLE_MAC_DINH.viTriDoc, 0, 0.5),
      canLe: v.canLe === 1 || v.canLe === 3 ? v.canLe : 2,
    };
  } catch {
    // JSON hỏng: dùng mặc định, KHÔNG ném.
    return { ...STYLE_MAC_DINH };
  }
}

export function luuStyle(s: PhuDeStyle, kho: KhoLuu = khoMacDinh()): void {
  try {
    kho?.setItem(KHOA_LUU, JSON.stringify(s));
  } catch {
    // Chặn ghi (hết quota, chế độ riêng tư) thì bỏ qua: kiểu chữ chỉ là tuỳ chọn hiển thị,
    // không được làm hỏng studio.
  }
}

/**
 * Đổi sang khối `style` mà backend hiểu (`subtitle_format._style_ass`).
 *
 * Tên khoá ở đây là snake_case vì đó là hợp đồng HTTP, không phải tên biến nội bộ của
 * giao diện — đổi tên này là đổi API.
 */
export function styleChoAss(s: PhuDeStyle): Record<string, unknown> {
  return {
    font: s.font,
    co: s.co,
    mau_chu: s.mauChu,
    mau_hop: s.mauHop,
    do_duc_hop: s.doDucHop,
    vien: s.vien,
    rong_hop: s.rongHop,
    cao_hop: s.caoHop,
    kieu_vien: s.kieuVien,
    dam: s.dam,
    nghieng: s.nghieng,
    can_le: s.canLe,
    offset_doc: s.viTriDoc,
  };
}

/**
 * Hình học của bản xem trước — CÙNG công thức backend dùng cho `.ass`.
 *
 * `tiLe = min(W/1920, H/1080)`: trục NGẮN quyết định, nên khung dọc 1080×1920 thu chữ
 * nhỏ lại đúng bằng `1080/1920`, vừa bề ngang mà không tràn mép.
 *
 * 🔴 BỎ SÀN 8 px (đã từng có, và nó là một lỗi ĐO ĐƯỢC). Khung video của studio chỉ rộng
 * ~132 px, nên cỡ chữ thật của `co = 30` trên video dọc 1080×1920 là **2,06 px**; sàn 8 px
 * thổi nó lên **gấp 3,9 lần**. Hậu quả đo trên chính app (đoạn 0:40.05, `co 30`, `vien 20`,
 * `cao_hop 180`, video 1080×1920):
 *
 *     bản burn : chữ 17 px trong khung 1080 → MỘT dòng, hộp 449 × 178
 *     bản xem  : chữ 8 px trong khung 132 → BA dòng, hộp 132 × 30
 *
 * Tức chữ trong bản xem trước to gấp ~3,9 lần nên nó bẻ dòng ở chỗ bản burn không bẻ, và
 * chữ thò ra ngoài hộp đen — đúng thứ chủ dự án báo "vẫn bị tràn".
 *
 * Đánh đổi: ở khung nhỏ, chữ đúng tỉ lệ thì KHÔNG đọc được (2 px). Đó là sự thật của
 * `co = 30` trên video 1080 px; muốn đọc thì mở video lớn (bấy giờ 30 × 0,5625 = 17 px).
 * Bản xem trước phải nói ĐÚNG cái sẽ burn, không phải một phiên bản phóng to của nó.
 */
export function hinhHoc(s: PhuDeStyle, rong: number, cao: number) {
  const tiLe = Math.min(rong / HE_GOC.rx, cao / HE_GOC.ry);
  return {
    // Sàn 0,1 px chỉ để không ra 0/âm khi khung chưa đo được — không phải sàn ĐỌC ĐƯỢC.
    coChu: Math.max(0.1, s.co * tiLe),
    vien: Math.max(0, s.vien * tiLe),
    cachDay: Math.min(Math.max(0, s.viTriDoc), 0.5) * cao,
    le: Math.max(0, 60 * tiLe),
  };
}
