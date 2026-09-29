/**
 * HAI TAM CUA "CHUA CO GI" VA "KHONG DOC DUOC" — dung chung cho nam cho trong app.
 *
 * ## Vi sao mot mo-dun rieng
 *
 * Nam cho (xem `design-round-1-brief.md` §1) truoc day moi cho TU VE mot `<p>` rieng: bon chu
 * trang tri khac nhau, khong co gi noi chung, va khong cho nao noi cho nguoi dung biet **lam gi
 * tiep**. Menh de cua vong nay la *"blank slate = BONG MA cua hinh dang sap toi"* — va mot bong ma
 * thi phai la CUNG MOT hinh dang o ca nam cho, neu khong nguoi doc khong hoc duoc gi.
 *
 * ## Hai hinh dang, KHAC NHAU ve y nghia (khong duoc gop)
 *
 * - `KhungRong` — **rong**: khong co gi de lam. Ba tang: kicker mono, MOT cau MENH LENH (nguoi
 *   dung lam gi tiep), va **bong ma truc thoi gian** = nét đứt doc 1px cao ~3 hang + 2..3 rail
 *   mono `--:--.--`. Truc DOC la "neo khac biet" cua app nay (thoi gian la mot truc doc, xem
 *   `.ed__rail`/`.ed__item`): bong ma do noi truoc HINH DANG se toi, khong phai mot anh minh hoa.
 * - `TamLoi` — **loi**: mot cai gi do HONG. Hinh dang khac han: van cheo `--fault` o dinh (cung
 *   khuon `.od__van` cua panel §4.8), ma loi **mono**, nguyen nhan, va **cau noi ro CAI GI CON
 *   CHAY DUOC**. Cau cuoi la khuon TRUNG THUC cua `.od__*`: mot loi khong duoc phep lam nguoi dung
 *   tuong rang ca app da chet.
 *
 * ## Luat cua vong nay (brief §4)
 *
 * - Chi animate `transform`/`opacity`, MOT lan, `--dur-vao`/`--ease-vao` (xem `app.css`).
 * - KHONG spinner, KHONG emoji, KHONG anh minh hoa, KHONG doi mau nen vung.
 * - `aria-hidden` cho phan TRANG TRI (van, truc, rail): chung khong mang thong tin nao ma cau chu
 *   khong mang. Mot trinh doc man hinh khong duoc doc `--:--.--` nhu mot gia tri that.
 * - `role="alert"`: do NGUOI GOI quyet dinh (chi `TamLoi` cua vung KENH can no — xem
 *   `ChannelZone.tsx`), nen no la mot prop chu khong phai mot hang so trong tep nay.
 */
import type { ReactNode } from "react";

/**
 * Mã lỗi đọc được từ `ApiError.message` (`"<status>: <detail>"`).
 *
 * ⚠️ ĐÂY LÀ MỘT PHÉP TRÍCH XUẤT, KHÔNG PHẢI MỘT PHÉP ĐOÁN: chuỗi `"502: Bad Gateway"` có mã ở
 * ĐẦU thì mã là `502`; chuỗi không có mã (ví dụ `"Failed to fetch"`) thì trả `"LỖI"` — KHÔNG bịa
 * một con số. Và nó NHẬN ĐÚNG `error` THÔ, không phải câu đã gói:
 * đo được một lần khi gói trước (`maLoi(\`không đọc được kênh: ${error}\`)`) — câu đã gói KHÔNG
 * bắt đầu bằng ba chữ số, nên hàm trả `"LỖI"` và tấm lỗi in `LỖI` HAI LẦN (kicker + mã). Đó là
 * lý do `TamLoi` nhận `ma` như một PROP: chỗ gọi là nơi DUY NHẤT biết chuỗi thô.
 */
export function maLoi(message: string): string {
  const m = /^(\d{3})\b/.exec(message.trim());
  return m === null ? "LỖI" : (m[1] ?? "LỖI");
}

/**
 * Bong ma cua noi dung sap toi: truc thoi gian DOC ve bang net dut 1px + vai rail mono.
 *
 * Ba rail la ba hang cua danh sach doan se toi (`.ed__item` cao `--row-2`), nen chieu cao bong ma
 * la `--row-2 * 3`. `--:--.--` la hinh dang mốc thoi gian cua `formatTimecode` (xem
 * `lib/timecode.ts`) khi CHUA co so — mot gia tri CHUA do duoc, khong phai mot gia tri gia.
 */
function BongMaTrucThoiGian() {
  return (
    <div className="rong__ma" aria-hidden="true">
      <span className="rong__truc" />
      <span className="rong__ray">--:--.--</span>
      <span className="rong__ray">--:--.--</span>
      <span className="rong__ray">--:--.--</span>
    </div>
  );
}

export interface KhungRongProps {
  /** Kicker mono in hoa: `TRỐNG` / `CHƯA CHỌN`. */
  kicker: string;
  /** MOT cau MENH LENH — nguoi dung lam gi tiep, khong phai mo ta trang thai. */
  lenh: string;
  /** Lop RIENG cua cho goi (vi du `ed__rong`), giu nguyen ten lop cu. */
  className?: string;
  /** `data-testid` do cho goi dat. */
  testid?: string;
}

export function KhungRong({ kicker, lenh, className, testid }: KhungRongProps) {
  return (
    <div className={`rong${className === undefined ? "" : ` ${className}`}`} data-testid={testid}>
      <p className="rong__kicker">{kicker}</p>
      <p className="rong__lenh">{lenh}</p>
      <BongMaTrucThoiGian />
    </div>
  );
}

export interface TamLoiProps {
  /** Kicker mono in hoa: `LỖI`. */
  kicker: string;
  /** Mã lỗi, do CHỖ GỌI trích từ chuỗi THÔ (`maLoi(error)`). Xem `maLoi` để biết vì sao không tự trích. */
  ma: string;
  /** Cau NGUYEN VAN cua loi (thuong la `ApiError.message`), in nguyen ven — khong viet lai. */
  lyDo: string;
  /** Cau noi ro CAI GI CON CHAY DUOC. Phai la mot su that kiem duoc, khong phai mot loi an ui. */
  con: string;
  /** Lop RIENG cua cho goi (vi du `ch__loi`), giu nguyen ten lop cu. */
  className?: string;
  /** `role` — vung KENH can `alert`; hai cho kia khong. */
  role?: "alert" | "status";
  /** `data-testid` do cho goi dat. */
  testid?: string;
  /** Cho de chen them (vi du nut thu lai) — component nay khong biet ve duong thu lai. */
  children?: ReactNode;
}

export function TamLoi({ kicker, ma, lyDo, con, className, role, testid, children }: TamLoiProps) {
  return (
    <section
      className={`tl${className === undefined ? "" : ` ${className}`}`}
      role={role}
      data-testid={testid}
    >
      <div className="tl__van" aria-hidden="true" />
      <p className="tl__kicker">{kicker}</p>
      {/* Ma loi la MOT GIA TRI CUA MAY ⇒ mono, va la thu duy nhat trong tam duoc to `--fault`.
          ⚠️ Cau nguyen van o duoi VAN mang ca ma (`"502: Bad Gateway"`), nen ma xuat hien hai lan
          trong tam. Do la CO Y: con dau la mot con DAU de quet bang mat, cau duoi la su that
          khong mat chu nao (nhieu bai test khang dinh CA HAI ve — xem bao cao vong 1). */}
      <p className="tl__ma">{ma}</p>
      <p className="tl__ly-do">{lyDo}</p>
      <p className="tl__con">{con}</p>
      {children}
    </section>
  );
}
