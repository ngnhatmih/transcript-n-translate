/**
 * Test `timecode.ts` (Task 6) — HAI HAM THUAN: khong React, khong DOM, khong `fetch`.
 *
 * Vi sao khong co hook nao o tep nay: no khong cham global nao, nen duoi
 * `--test-isolation=none` (MOI tep chung MOT tien trinh) no khong co be mat nhiem cheo.
 * Cung khuon voi `src/lib/window.test.ts` (Task 5).
 *
 * Runner: `node --test --test-isolation=none` + loader SWC (`test/swc-loader.mjs`).
 * Vitest KHONG dung duoc o moi truong nay (xem ERRATA trong plan), nen o day la
 * `node:test` + `node:assert/strict`, va import `./timecode.ts` PHAI kem duoi `.ts`.
 *
 * Chay RIENG tep nay tu `frontend/`:
 *   node --import ./test/swc-loader.mjs --test --test-isolation=none src/lib/timecode.test.ts
 *
 * ⚠️ `npm test` (glob) KHONG loc duoc theo ten: chay toan bo.
 *
 * BAY CHO CO Y KHAC PLAN (brief Task 6 §1b) — moi cai deu co bai ghim:
 *  1. `formatTimecode` tinh tren TONG SO TRAM GIAY (`Math.round(seconds * 100)`) roi moi
 *     tach phut/giay/tram ⇒ lam tron o moc tram chu khong cat. `0.994 ⇒ 0:00.99` va
 *     `0.999 ⇒ 0:01.00` ghim dung dieu do.
 *  2. `3600 ⇒ "60:00.00"` la TRAN DA BIET (plan `ponytail:` co y bo truong GIO). Bai test
 *     ghim no, va `timecode.ts` ghi duong nang cap.
 *  3. `-1` bi KEP ve 0 (nudge ±0,1s cua spec UI §5.2 co the day moc xuong duoi 0).
 *  4. `NaN`/±`Infinity` NEM `RangeError` — va bai test ghim LOAI loi bang `instanceof`,
 *     khong bang regex: ERRATA #13 muc 2 do duoc rang `assert.throws(fn, /regex/)` khop
 *     MESSAGE chu KHONG khop TYPE.
 *  5. `parseTimecode` phai chiu duoc dau vao BAN va KHONG BAO GIO tra `NaN`.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { formatTimecode, parseTimecode } from "./timecode.ts";

describe("formatTimecode: M:SS.hh (khong co truong gio)", () => {
  it("dinh dang dung cac gia tri cua plan", () => {
    assert.equal(formatTimecode(0), "0:00.00");
    assert.equal(formatTimecode(4.12), "0:04.12");
    assert.equal(formatTimecode(724.3), "12:04.30");
    assert.equal(formatTimecode(3599.99), "59:59.99");
  });

  it("BIEN: lam tron o moc TRAM giay, khong CAT (0.994 ⇒ 0:00.99 / 0.999 ⇒ 0:01.00)", () => {
    // Cat (`Math.floor`) cho 0.999 ⇒ "0:00.99"; lam tron cho "0:01.00". Do la QUYET DINH:
    // timecode la vi tri tren truc thoi gian, lam tron ve moc tram gan nhat.
    assert.equal(formatTimecode(0.994), "0:00.99");
    assert.equal(formatTimecode(0.999), "0:01.00");
  });

  it("BIEN: dung nua tram giay lam tron LEN (4.125 ⇒ 0:04.13)", () => {
    assert.equal(formatTimecode(4.125), "0:04.13");
  });

  it("TRAN da biet: bo truong GIO ⇒ 3600 cho 60:00.00 (ponytail, co duong nang cap)", () => {
    assert.equal(formatTimecode(3600), "60:00.00");
  });

  it("giay AM bi KEP ve 0 (nudge ±0,1s co the day moc xuong duoi 0)", () => {
    assert.equal(formatTimecode(-1), "0:00.00");
    assert.equal(formatTimecode(-0.001), "0:00.00");
  });

  it("NaN/±Infinity NEM RangeError (khong tra mot chuoi NOI DOI)", () => {
    for (const x of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
      assert.throws(
        () => formatTimecode(x),
        RangeError,
        `formatTimecode(${x}) phai nem RangeError`,
      );
    }
    // ⚠️ ERRATA #13 muc 2: `assert.throws(fn, /regex/)` khop MESSAGE, KHONG khop TYPE —
    // mot `Error` cung thong diep lot qua. Muon ghim LOAI loi thi phai `instanceof`.
    try {
      formatTimecode(Number.NaN);
      assert.fail("formatTimecode(NaN) phai nem");
    } catch (e) {
      assert.ok(e instanceof RangeError, `phai la RangeError, do duoc ${String(e)}`);
      assert.match((e as Error).message, /seconds/);
    }
  });
});

describe("parseTimecode: nghich dao cua formatTimecode", () => {
  it("doc dung dinh dang (gia tri cua plan)", () => {
    assert.equal(parseTimecode("0:00.00"), 0);
    assert.equal(parseTimecode("12:04.30"), 724.3);
    assert.equal(parseTimecode("59:59.99"), 3599.99);
    assert.equal(parseTimecode("60:00.00"), 3600);
  });

  it("khoang trang hai dau duoc bo qua (dan tu clipboard)", () => {
    assert.equal(parseTimecode(" 1:00.00 "), 60);
  });

  it("ROUND-TRIP parse(format(x)) ≈ x trong sai so 0.01, ke ca gia tri LON", () => {
    for (const x of [0, 0.5, 4.12, 12.345, 724.3, 1234.5678, 3599.99, 3600]) {
      const lai = parseTimecode(formatTimecode(x));
      assert.ok(lai !== null, `parse(format(${x})) khong duoc null`);
      assert.ok(
        Math.abs(lai - x) <= 0.01,
        `round-trip x=${x} ⇒ ${lai}, lech ${Math.abs(lai - x)} > 0.01`,
      );
    }
  });

  it("DAU VAO BAN ⇒ null, KHONG BAO GIO NaN", () => {
    const ban: Array<string | null | undefined> = [
      "rác",
      "",
      "   ",
      "1:2",
      "1:2:3",
      "1:00",
      "1:60.00",
      "0:04.1",
      "0:04.123",
      "−1:00.00", // U+2212: dau tru Unicode, khong phai `-`
      "-1:00.00",
      "abc:12.34",
      "12:04.30x",
      "::",
      null,
      undefined,
    ];
    for (const x of ban) {
      const r = parseTimecode(x);
      assert.equal(r, null, `${JSON.stringify(x)} phai cho null, do duoc ${String(r)}`);
    }
  });

  it("moi ket qua la `null` hoac mot so HUU HAN (khong NaN, khong Infinity)", () => {
    const dauVao = ["0:00.00", "12:04.30", "rác", "", "1:2:3", null, undefined];
    for (const x of dauVao) {
      const r = parseTimecode(x);
      assert.ok(
        r === null || Number.isFinite(r),
        `${JSON.stringify(x)} ⇒ ${String(r)} khong phai null cung khong huu han`,
      );
    }
  });
});
