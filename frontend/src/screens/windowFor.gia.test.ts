/**
 * T7 — **CAI GIA CUA BAN VA D4**: `currentSegment` duoc them vao tap GHIM cua danh sach ao hoa.
 *
 * ## Vi sao tep nay ton tai
 *
 * Vong gom no Task 11 (`D4`) ghim THEM `currentSegment` (`EditScreen.windowFor(..., pinnedThem)`),
 * va khai gia phai tra trong comment (`EditScreen.tsx`, docblock `windowFor`): *"khi hai dong duoc
 * ghim nam XA nhau, khoang render la khoang giua chung ⇒ so hang trong DOM lon hon
 * `viewportH / rowH`"*. **Gia do CHUA AI DO.** Tep nay do no, va ghim BAT BIEN cua no.
 *
 * ⚠️ **DAY KHONG PHAI BANG CHUNG HINH THUC.** So hang JSX duoc render trong jsdom chi la MOT PHAN
 * cua cai gia: thoi gian layout/ve that, va chi phi cuon, **chi Chrome that do duoc**
 * (`e2e/plans/ban-ghi-dai-t7.json`). Neu chi doc tep nay ma ket luan "khong sao" thi do la mot ket
 * luan vuot qua phep do.
 *
 * ## Cong thuc (doc tu `src/lib/window.ts`)
 *
 * `soHang = end - start`, trong do `start = min(visibleStart, pinned, pinnedThem)` va
 * `end = max(visibleEnd, pinned + 1, pinnedThem + 1)` (kep theo `soDoan`).
 * ⇒ Khi hai chi so GHIM cach nhau `d`, `soHang >= d + 1`.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { windowFor } from "./EditScreen.tsx";

/** Tham so THAT cua man: `ROW_H`/`VIEWPORT_H`/`OVERSCAN` (xuat tu `EditScreen.tsx`). */
const ROW_H = 44;
const VIEWPORT_H = 480;
const OVERSCAN = 5;

/** So hang `windowFor` se render. */
function soHang(start, end) {
  return end - start;
}

describe("T7: cai gia cua D4 — GHIM HAI CHI SO XA NHAU lam no ra khoang giua", () => {
  it("T7 KHONG GHIM: cua so chi ~ viewportH/rowH + 2*overscan", () => {
    const k = windowFor(0, VIEWPORT_H, ROW_H, 600, OVERSCAN, null, null);
    // ceil((0+480)/44) + 5 = 11 + 5 = 16; start = max(0, 0-5) = 0.
    assert.deepEqual(k, { start: 0, end: 16, pinned: false });
    assert.equal(soHang(k.start, k.end), 16);
  });

  it("T7 MOT MOC GHIM o dong dau: KHONG no ra (moc nam trong cua so)", () => {
    const k = windowFor(0, VIEWPORT_H, ROW_H, 600, OVERSCAN, 1, null);
    assert.equal(soHang(k.start, k.end), 16, "ghim mot moc trong cua so thi khong doi gi");
  });

  it("🔴 T7 HAI MOC CACH XA `d` ⇒ so hang render >= d + 1 (BAT BIEN cua ban va D4)", () => {
    // Canh THAT: dang sua doan 1, `J`/`K`/`N` nhay toi doan 500 ⇒ moc cach nhau 499.
    // `scrollTop = 44 * 480` = 21120 px ~ dong 480 (dung bang "cuon toi noi dong 500").
    const k = windowFor(44 * 480, VIEWPORT_H, ROW_H, 600, OVERSCAN, 1, 500);
    assert.equal(k.start, 1, "start phai tut ve moc nho hon");
    assert.equal(k.end, 501, "end phai nang len moc lon hon + 1");
    assert.equal(soHang(k.start, k.end), 500);
    // Bat bien noi dung cua D4 — HAI menh de DOM phai dung:
    assert.ok(k.start <= 1 && 1 < k.end, "dong dang SUA phai nam trong khoang render");
    assert.ok(k.start <= 500 && 500 < k.end, "dong dang CHON phai nam trong khoang render");
  });

  it("🔴 T7 DO DUOC: khi moc cach xa HON cua so thi render ≈ `d + 2` (khong co tran)", () => {
    // ⚠️ Hai lan do dau SAI, va day la con so SUA LAI. `visibleRange` cho cua so `[0,16)` (16 hang,
    // da tinh `overscan`), va `withPinned` chi MO RONG: `end = max(16, moc + 1)`. Voi `moc = 1 + d`
    // (0-based) thi hang render = `max(16, d + 2)` — KHONG phai `d + 1`.
    // ⇒ Khang dinh QUAN HE (don dieu + gia tri do duoc), khong phai mot literal doan mo.
    let truoc = 0;
    for (const [d, mongDoi] of [[0, 16], [10, 16], [14, 16], [100, 102], [499, 501], [599, 600]]) {
      const k = windowFor(0, VIEWPORT_H, ROW_H, 600, OVERSCAN, 1, 1 + d);
      const so = soHang(k.start, k.end);
      assert.equal(so, mongDoi, `khoang cach ${d} ⇒ do duoc ${so}, ky vong ${mongDoi}`);
      assert.ok(so >= truoc, `so hang phai DON DIEU TANG theo d: d=${d} ⇒ ${so} < ${truoc}`);
      truoc = so;
    }
    // 🔴 KHANG DINH TRUNG TAM: khi moc cach xa HON cua so (`d > viewportH/rowH`), so hang render
    // di theo KHOANG CACH ⇒ `viewportH` KHONG chan duoc gi. DAY la cai gia cua D4.
    for (const d of [20, 100, 499]) {
      const k = windowFor(0, VIEWPORT_H, ROW_H, 600, OVERSCAN, 1, 1 + d);
      assert.equal(
        soHang(k.start, k.end),
        d + 2,
        `d=${d} > viewportH/rowH ⇒ phai render d+2 hang (do duoc ${soHang(k.start, k.end)})`,
      );
    }
    // Ca XAU NHAT do duoc: ban ghi 600 doan, sua doan 1, chon doan 600, KHONG cuon ⇒ render 600.
    const xauNhat = windowFor(0, VIEWPORT_H, ROW_H, 600, OVERSCAN, 1, 600);
    assert.equal(soHang(xauNhat.start, xauNhat.end), 600, "ca xau nhat: render CA ban ghi");
  });

  it("🔴 T7 CHI PHI DO DUOC: 500 hang = 22 000 px DOM, gap ~31 lan cua so thuong", () => {
    // `EditScreen` dat `.ed__dem-dau` cao `start * rowH`; phan DUOI chi con `(soDoan - end) * rowH`.
    // ⇒ khoang render chiem `(end - start) * rowH` px. Do la con so ma Chrome phai layout/ve.
    // Canh do: dang sua doan 1, CUON toi noi dong 500 (`scrollTop = 44 * 480`), roi chon doan 500.
    const k = windowFor(44 * 480, VIEWPORT_H, ROW_H, 600, OVERSCAN, 1, 500);
    assert.equal(soHang(k.start, k.end), 500, "start=1, end=501");
    const px = soHang(k.start, k.end) * ROW_H;
    assert.equal(px, 22_000);
    // ⚠️ Doi chieu DUNG CHO: cua so KHONG ghim o CUNG `scrollTop` la 26 hang (do duoc) — KHONG phai
    // 16 (16 la o `scrollTop = 0`). Lan do dau cua tep nay so sai cho va bao `704` (do duoc: 924).
    const cungCho = windowFor(44 * 480, VIEWPORT_H, ROW_H, 600, OVERSCAN, null, null);
    assert.equal(soHang(cungCho.start, cungCho.end), 21);
    assert.equal(soHang(cungCho.start, cungCho.end) * ROW_H, 924);
    // ⇒ Gia cua D4 trong canh nay: gap ~23 lan dien tich DOM phai layout.
    assert.ok(px / 924 > 23, `ty le phai > 23, do duoc ${px / 924}`);
    // Va so voi cua so o DAU danh sach (16 hang = 704 px) thi gap ~31 lan.
    const dauDanhSach = windowFor(0, VIEWPORT_H, ROW_H, 600, OVERSCAN, null, null);
    assert.equal(soHang(dauDanhSach.start, dauDanhSach.end) * ROW_H, 704);
    assert.ok(px / 704 > 31, `ty le phai > 31, do duoc ${px / 704}`);
  });
});
