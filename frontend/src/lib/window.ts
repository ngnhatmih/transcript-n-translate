/**
 * Cua so hoa cho danh sach hang CAO DEU (spec UI §8.2) — HAI HAM THUAN.
 *
 * Khong React, khong DOM, khong `fetch`: nham de kiem bang so hoc, khong can harness DOM.
 *
 * `ponytail:` ham nay chi dung khi MOI hang cao bang nhau. Doan dai xuong dong lam
 * hang cao khac nhau, luc do phai DO cao that tung hang — duong nang cap la
 * `@tanstack/react-virtual`. Spec §2 co y KHONG keo dependency do vao chi vi vai
 * dong so hoc; keo vao thi phai noi ra, khong duoc lang le.
 */

/**
 * Khoang hang can render cho mot khung nhin cao `viewportH` bat dau tu `scrollTop`.
 *
 * `rowH <= 0` (hoac `NaN`/`Infinity`) NEM `RangeError` — day la QUYET DINH, khong phai
 * so suat. `rowH` la hang so bo cuc, gia tri vo ly nghia la loi lap trinh; neu tra ve
 * `NaN` thi moi so sanh deu `false` va danh sach RONG IM LANG, con nem loi thi hong o
 * ngay cho va noi ro ten tham so. Duong khac (kep ve mot hang) da bi loai vi no che
 * loi lap trinh.
 *
 * `scrollTop` am (con lua khi quan tinh) duoc kep ve 0 qua `Math.max` cua `start`.
 */
export function visibleRange(
  scrollTop: number,
  viewportH: number,
  rowH: number,
  count: number,
  overscan: number,
): { start: number; end: number } {
  if (!Number.isFinite(rowH) || rowH <= 0) {
    throw new RangeError(`visibleRange: rowH phai la so huu han lon hon 0, do duoc ${rowH}`);
  }
  const first = Math.floor(scrollTop / rowH);
  return {
    start: Math.max(0, first - overscan),
    end: Math.min(count, Math.ceil((scrollTop + viewportH) / rowH) + overscan),
  };
}

/**
 * Mo rong khoang de dong dang sua LUON nam trong DOM (spec UI §8.3, U6).
 *
 * Bat bien: khi `pinned !== null` thi `start <= pinned < end` LUON dung. Vi vay phai mo
 * rong CA HAI dau:
 * - `pinned` nam TREN khoang (`pinned < start`) ⇒ ha `start` xuong `pinned`.
 * - `pinned` nam DUOI khoang (`pinned >= end`) ⇒ nang `end` len `pinned + 1`.
 *
 * Ban dau chi mo rong `start`. Voi dong dang sua nam DUOI, ham tra `pinned: true` trong
 * khi dong do KHONG nam trong khoang ⇒ ao hoa thao dung dong dang go khoi DOM ⇒ MAT
 * FOCUS, dung thu spec UI §8.3/U6 cam. Test chieu TREN khong bat duoc loi do.
 *
 * `pinned` da nam trong khoang thi tra nguyen (`pinned: false`) — khong noi rong vo ich.
 * Ngoai hop dong, `pinned` la chi so doan khong am hoac `null`; ham khong kep `start` ve 0
 * vi kep se pha bat bien voi chi so am (dau vao vo nghia), va bat bien la thu dang ghim.
 */
export function withPinned(
  range: { start: number; end: number },
  pinned: number | null,
): { start: number; end: number; pinned: boolean } {
  if (pinned === null || (pinned >= range.start && pinned < range.end)) {
    return { start: range.start, end: range.end, pinned: false };
  }
  return {
    start: Math.min(range.start, pinned),
    end: Math.max(range.end, pinned + 1),
    pinned: true,
  };
}
