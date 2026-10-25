/**
 * Timecode `M:SS.hh` — HAI HAM THUAN: khong React, khong DOM, khong `fetch`.
 *
 * Nguon cua dinh dang: spec UI §4.1 — thanh transport hien `0:04.12 / 12:04.30`, cot
 * mono (IBM Plex Mono). Nen chuoi la `phut:giay.tram`, giay VA tram luon du hai chu so,
 * con phut KHONG dem so chu so (`0:04.12` nhung `12:04.30`).
 *
 * `ponytail:` TRAN — CO Y bo truong GIO. Phu de trong pham vi nay ngan hon mot gio, nen
 * `3600` giay cho `"60:00.00"` chu khong `"1:00:00.00"`. Do la tran DA BIET va duoc ghim
 * bang test (`timecode.test.ts`). Duong nang cap khi co tep dai hon: them mot nhom
 * `(\d+):` nua vao CA HAI ham va tra `"h:mm:ss.hh"` — phai doi cung luc, vi `parseTimecode`
 * la nghich dao cua `formatTimecode` tren dung bo gia tri ma no sinh ra.
 */

/**
 * DINH DANG mot so giay thanh `M:SS.hh`.
 *
 * Tinh tren TONG SO TRAM GIAY (`Math.round(seconds * 100)`) roi moi tach phut/giay/tram.
 * Lam nguoc lai (tach giay truoc roi lam tron tung phan) se sai o moc tram: `0.999` se
 * thanh `"0:00.99"` trong khi moc tram gan nhat la `1.00`.
 *
 * QUYET DINH (moi cai co bai ghim):
 * - **Lam tron**, khong cat: `0.999 ⇒ "0:01.00"`, `0.994 ⇒ "0:00.99"`.
 * - **Giay AM bi kep ve 0**: nudge ±0,1s cua spec UI §5.2 co the day mot moc xuong duoi 0,
 *   va mot timecode am la vi tri vo nghia. Cung khuon voi `visibleRange` (`src/lib/window.ts`)
 *   kep `scrollTop` am ve 0.
 * - **`NaN`/±`Infinity` NEM `RangeError`**: day la gia tri vo nghia (payload hong), va mot
 *   chuoi timecode bia ra tu no la mot loi noi doi ma khong gi bat duoc. Cung khuon voi
 *   quyet dinh `rowH <= 0` cua `window.ts`: hong o NGAY CHO va noi ro ten tham so, thay vi
 *   tra ve mot gia tri trong nhu that.
 */
export function formatTimecode(seconds: number): string {
  if (!Number.isFinite(seconds)) {
    throw new RangeError(`formatTimecode: seconds phai la so huu han, do duoc ${seconds}`);
  }
  const tongTram = Math.max(0, Math.round(seconds * 100));
  const phut = Math.floor(tongTram / 6000);
  const conLai = tongTram % 6000;
  const giay = Math.floor(conLai / 100);
  const tram = conLai % 100;
  return `${phut}:${haiChuSo(giay)}.${haiChuSo(tram)}`;
}

/**
 * DOC mot chuoi `M:SS.hh` thanh so giay, hoac `null` neu chuoi khong thuoc dinh dang.
 *
 * Bat bien: bo gia tri ma ham nay nhan dung bang bo gia tri `formatTimecode` SINH RA
 * (phut khong am, giay `00`–`59`, dung hai chu so tram, khong co truong gio). Nho vay
 * `parseTimecode(formatTimecode(x))` lai ra `x` trong sai so mot tram giay, va mot chuoi
 * nhu `"-1:00.00"` hay `"1:2:3"` bi TU CHOI thay vi duoc dien giai thanh mot vi tri.
 *
 * Tra `null` chu KHONG BAO GIO tra `NaN`: mot `NaN` lot ra ngoai se lam moi so sanh sau
 * do thanh `false` va hong IM LANG (dung ly do `window.ts` nem loi thay vi tra `NaN`).
 * Khoang trang hai dau duoc bo qua vi gia tri nay den tu mot o nhap / clipboard.
 */
export function parseTimecode(text: string | null | undefined): number | null {
  if (typeof text !== "string") return null;
  const khop = /^(\d+):([0-5]\d)\.(\d{2})$/.exec(text.trim());
  if (khop === null) return null;
  const phut = Number(khop[1]);
  const giay = Number(khop[2]);
  const tram = Number(khop[3]);
  // Tinh tren TONG SO TRAM GIAY roi moi chia: cong ba so thuc (`phut * 60 + giay + tram / 100`)
  // se tich luỹ sai so o chu so cuoi, va phep ghim round-trip se bat duoc dieu do.
  return (phut * 6000 + giay * 100 + tram) / 100;
}

function haiChuSo(n: number): string {
  return String(n).padStart(2, "0");
}
