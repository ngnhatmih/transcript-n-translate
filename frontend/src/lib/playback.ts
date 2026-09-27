/**
 * HAI HAM THUAN cua thanh transport — khong React, khong DOM, khong `fetch`.
 *
 * Vi sao tach ra khoi `<Transport/>`: "phat toi moc cuoi cua doan thi tu nhay doan"
 * va "dau doc nam o dau track" deu la SO HOC. Nam trong component thi chung chi do
 * duoc GIAN TIEP qua DOM, va o moi truong nay phep do gian tiep do rat ngheo:
 * jsdom KHONG hien thuc `play()`/`pause()` (do duoc o `Transport.test.tsx`), khong
 * co layout va khong ap CSS. Tach ra day thi `node:test` thuong ghim duoc moi moc —
 * dung ly le plan da dung cho `window.ts` va `timecode.ts`.
 *
 * Ca hai ham deu NHAN gia tri da qua cua trinh duyet (`currentTime` cua phan tu
 * media, `duration` cua backend), nen ca hai phai chiu duoc gia tri vo nghia
 * (`NaN`, am, vuot khoang) ma KHONG nem va KHONG tra `NaN`: mot `NaN` lot vao
 * `style.left` hay vao chuoi timecode la mot loi NOI DOI im lang.
 */
import type { Segment } from "../api/types.ts";

/**
 * Chi so doan can nhay toi, hoac `null` khi KHONG nhay.
 *
 * Quyet dinh (moi cai co bai ghim o `playback.test.ts`):
 *  - `currentIndex === null` (khong phat doan nao) ⇒ `null`. Khong co "doan hien
 *    tai" thi khong co gi de "sang doan ke".
 *  - Chi so NGOAI khoang (`< 0`, `>= segments.length`) ⇒ `null`. Chi so cu con lai
 *    sau khi ban ghi doi la chuyen CO THAT, va doan `undefined` thi khong co `start`
 *    de dat lai vi tri phat.
 *  - **`currentTime <= segment.end` ⇒ `null`**: moc cuoi CON THUOC doan. Doi thanh
 *    `<` la doi hanh vi o dung mot moc, nen bai "dung BANG `segment.end`" ghim no.
 *  - **Vuot `segment.end` ⇒ doan KE**, va o doan CUOI thi `null` (khong co doan ke,
 *    khong bia chi so).
 *
 * Tra VE CHI SO chu khong tra vi tri giay: `Transport` moi la noi biet phai dat
 * `currentTime` ve `segments[i].start` — va khoang lang giua hai doan la thu bi
 * cu nhay nay bo qua, dung nhu ten cua no.
 */
export function nextSegmentAfter(
  currentTime: number,
  segments: Segment[],
  currentIndex: number | null,
): number | null {
  if (currentIndex === null) return null;
  const hienTai = segments[currentIndex];
  if (hienTai === undefined) return null;
  if (!(currentTime > hienTai.end)) return null;
  const ke = currentIndex + 1;
  return ke < segments.length ? ke : null;
}

/**
 * Vi tri dau doc tren track, tinh theo PHAN TRAM (`0`–`100`) de gan vao `style.left`.
 *
 *  - **Kep ve `[0, 100]`**: `currentTime` vuot `duration` la chuyen that (moc cuoi
 *    cua doan cuoi co the dai hon `duration` do lam tron), va mot dau doc chay ra
 *    ngoai track la mot loi hinh thuc khong gi bat duoc.
 *  - **Chua biet thoi luong ⇒ `0`**: `Source.duration` la du lieu backend va co the
 *    la `null` (URL chua do thoi luong). Chia cho `null`/`0`/`NaN` cho ra `NaN` hoac
 *    `Infinity`, va `style.left = "NaN%"` bi trinh duyet BO IM LANG — dau doc bien
 *    mat ma khong co gi bao.
 *  - **`duration` khong huu han ⇒ `0`**, ke ca `Infinity`: mot thoi luong vo cung la
 *    du lieu hong, khong phai "chua biet".
 */
export function readheadPercent(currentTime: number, duration: number | null): number {
  if (duration === null || !Number.isFinite(duration) || duration <= 0) return 0;
  if (!Number.isFinite(currentTime)) return 0;
  const phanTram = (currentTime / duration) * 100;
  return Math.min(100, Math.max(0, phanTram));
}
