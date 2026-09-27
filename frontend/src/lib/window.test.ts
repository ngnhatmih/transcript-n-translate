/**
 * Cua so hoa cho hang CAO DEU (Task 5) — HAI HAM THUAN.
 *
 * Khong React, khong DOM, khong `fetch`: file nay khong dung global nao, nen no
 * KHONG can `setupDom`/`teardownDom` va khong co be mat nhiem cheo duoi
 * `--test-isolation=none`. Do la ly do no khong co hook nao.
 *
 * Runner: `node --test --test-isolation=none` + loader SWC (`test/swc-loader.mjs`).
 * Vitest khong dung duoc o moi truong nay (xem phan ERRATA trong plan), nen o day
 * la `node:test` + `node:assert/strict`. Import `./window.ts` PHAI kem duoi `.ts`
 * (khuon giong `src/api/contract.test.ts`): loader dat `tsx` theo duoi tep, va Node
 * khong tu them duoi nao.
 *
 * Chay RIENG file nay tu `frontend/`:
 *   node --import ./test/swc-loader.mjs --test --test-isolation=none src/lib/window.test.ts
 * (`npm test -- window` KHONG loc duoc: script `test` co glob, tham so thua bi noi vao
 * chuoi lenh nen runner nhan mot duong dan khong ton tai. Xem ERRATA trong plan.)
 *
 * BON CHO CO Y KHAC BAN PLAN (brief Task 5 §1):
 * 1. `node:test` thay `vitest`.
 * 2. `withPinned` cua plan chi mo rong `start` => voi dong dang sua nam DUOI khoang
 *    no van khai `pinned: true` trong khi dong do khong duoc render. Test
 *    "GHIM: dong dang sua DUOI khoang hien thi ..." ghim dung lo hong do.
 * 3. `rowH <= 0`: quyet dinh la NEM loi (xem `window.ts`), va ghim bang test.
 * 4. Them bien `count = 0`, `scrollTop` am, va `scrollTop` lech boi so cua `rowH`.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { visibleRange, withPinned } from "./window.ts";

describe("cua so hoa hang cao deu", () => {
  it("tinh dung khoang hien thi", () => {
    assert.deepEqual(visibleRange(0, 400, 20, 2000, 0), { start: 0, end: 20 });
    assert.deepEqual(visibleRange(400, 400, 20, 2000, 0), { start: 20, end: 40 });
  });

  it("them overscan hai dau", () => {
    assert.deepEqual(visibleRange(400, 400, 20, 2000, 5), { start: 15, end: 45 });
  });

  it("khong vuot qua dau danh sach", () => {
    assert.equal(visibleRange(0, 400, 20, 2000, 5).start, 0);
  });

  it("khong vuot qua cuoi danh sach", () => {
    assert.equal(visibleRange(1e9, 400, 20, 30, 5).end, 30);
  });

  it("lam tron XUONG khi scrollTop lech khoi boi so cua rowH", () => {
    // Hang dau tien phai la hang CHUA diem scrollTop, khong phai hang gan nhat.
    // Thieu bai nay thi `Math.floor` doi thanh `Math.round` ma khong bai nao do.
    assert.equal(visibleRange(410, 400, 20, 2000, 0).start, 20);
  });

  it("count = 0 tra khoang RONG, khong am", () => {
    assert.deepEqual(visibleRange(0, 400, 20, 0, 0), { start: 0, end: 0 });
    assert.deepEqual(visibleRange(0, 400, 20, 0, 5), { start: 0, end: 0 });
  });

  it("scrollTop am khong keo start xuong duoi 0", () => {
    assert.deepEqual(visibleRange(-50, 400, 20, 2000, 0), { start: 0, end: 18 });
  });

  it("rowH <= 0 (hoac khong huu han) NEM loi ro rang, khong tra NaN/Infinity am tham", () => {
    // QUYET DINH, khong phai so suat: rowH la hang so bo cuc, gia tri <= 0 nghia la
    // loi lap trinh. Tra ve NaN thi moi so sanh deu false => danh sach RONG im lang.
    for (const rowH of [0, -20, Number.NaN, Number.POSITIVE_INFINITY]) {
      assert.throws(() => visibleRange(0, 400, rowH, 2000, 0), /rowH/,
        `rowH = ${rowH} phai nem loi co ten tham so`);
    }
  });

  it("GHIM: dong dang sua ngoai khoang hien thi van duoc render", () => {
    // Khong ghim thi ao hoa se thao dong dang go khoi DOM -> mat focus.
    // Day la U6 cua spec UI, va la cho de tu ban vao chan nhat.
    assert.deepEqual(withPinned({ start: 100, end: 120 }, 7), { start: 7, end: 120, pinned: true });
  });

  it("GHIM: dong dang sua trong khoang thi khong doi gi", () => {
    assert.deepEqual(withPinned({ start: 100, end: 120 }, 110), { start: 100, end: 120, pinned: false });
  });

  it("GHIM: khong co dong dang sua thi tra nguyen", () => {
    assert.deepEqual(withPinned({ start: 100, end: 120 }, null), { start: 100, end: 120, pinned: false });
  });

  it("GHIM: dong dang sua DUOI khoang hien thi cung phai duoc render", () => {
    // LO HONG CUA PLAN: ban plan chi mo rong `start`, nen voi `pinned` nam DUOI
    // khoang no tra `pinned: true` trong khi `pinned` khong nam trong khoang —
    // loi noi doi do chinh la thu khien ao hoa thao dong dang go khoi DOM.
    // (Bai "ngoai khoang" cua plan chi phu chieu TREN, nen loi nay vo hinh.)
    const r = withPinned({ start: 100, end: 120 }, 500);
    assert.equal(r.pinned, true);
    assert.deepEqual(r, { start: 100, end: 501, pinned: true });
  });

  it("GHIM: bat bien start <= pinned < end khi pinned !== null, voi MOI cap", () => {
    const caps: Array<[{ start: number; end: number }, number | null]> = [
      [{ start: 100, end: 120 }, 7],
      [{ start: 100, end: 120 }, 500],
      [{ start: 100, end: 120 }, 100],
      [{ start: 100, end: 120 }, 119],
      [{ start: 100, end: 120 }, null],
      [{ start: 0, end: 0 }, 0],
      [{ start: 0, end: 20 }, 0],
    ];
    for (const [range, pinned] of caps) {
      const r = withPinned(range, pinned);
      if (pinned !== null) {
        assert.ok(
          r.start <= pinned && pinned < r.end,
          `ghim ${pinned} phai nam trong [${r.start}, ${r.end})`,
        );
      }
    }
  });
});
