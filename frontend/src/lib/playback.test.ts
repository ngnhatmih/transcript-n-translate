/**
 * Test HAI HAM THUAN cua thanh transport (`src/lib/playback.ts`) — `node:test`
 * THUONG: khong React, khong DOM, khong jsdom.
 *
 * Vi sao quyet dinh "toi moc cuoi cua doan thi sang doan ke" nam o DAY chu khong
 * nam trong `<Transport/>`: no la SO HOC. Do la dung ly le plan da dung cho
 * `src/lib/window.ts` va `src/lib/timecode.ts` — mot quyet dinh tach ra thanh ham
 * thuan thi ghim duoc moi moc ma KHONG can DOM, va khong phu thuoc vao thu ma
 * jsdom khong co.
 *
 * ⚠️ Va jsdom THAT SU khong co gi de phat media: do duoc o `Transport.test.tsx`
 * (`play()`/`pause()` khong duoc hien thuc, log `Not implemented`). Nen neu quyet
 * dinh nay nam trong component thi no CHI do duoc gian tiep qua DOM — va mot phep
 * do gian tiep khong noi duoc "moc cuoi cua doan cuoi thi khong con doan nao".
 *
 * Bien cua `Segment`: nam khoa LUON co (`i`, `start`, `end`, `text`, `suspect`) —
 * xem `src/api/types.ts`. Duoi day chi dung nam khoa do.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import type { Segment } from "../api/types.ts";
import { nextSegmentAfter, readheadPercent } from "./playback.ts";

function doan(i: number, start: number, end: number): Segment {
  return { i, start, end, text: `đoạn ${i}`, suspect: false };
}

/** Ba doan LIEN TIEP: [0,2) [2,4) [4,6). `Segment.i` trung chi so mang — dung du lieu that. */
const BA_DOAN: Segment[] = [doan(0, 0, 2), doan(1, 2, 4), doan(2, 4, 6)];

describe("nextSegmentAfter: phat toi moc cuoi cua doan thi sang doan ke", () => {
  it("TRONG doan thi KHONG nhay (mot ban 'nhay o moi su kien' la mot loi)", () => {
    assert.equal(nextSegmentAfter(0, BA_DOAN, 1), null);
    assert.equal(nextSegmentAfter(3.99, BA_DOAN, 1), null);
  });

  it("VUOT `segment.end` thi sang doan KE", () => {
    assert.equal(nextSegmentAfter(4.01, BA_DOAN, 1), 2);
    assert.equal(nextSegmentAfter(2.5, BA_DOAN, 0), 1);
  });

  it("dung BANG `segment.end` thi CHUA nhay: moc cuoi con THUOC doan", () => {
    // Quyet dinh nay phai ro, vi no la bien: `currentTime > end` moi la "da qua".
    // Doi thanh `>=` la doi HANH VI o dung mot moc, va bai nay ghim moc do.
    assert.equal(nextSegmentAfter(4, BA_DOAN, 1), null);
  });

  it("doan CUOI thi khong con doan nao de sang (tra `null`, khong phai chi so bia)", () => {
    assert.equal(nextSegmentAfter(99, BA_DOAN, 2), null);
  });

  it("khong phat doan nao (`currentIndex === null`) thi khong nhay", () => {
    assert.equal(nextSegmentAfter(4.01, BA_DOAN, null), null);
  });

  it("chi so NGOAI khoang (ban ghi vua doi, chi so cu con lai) thi khong nhay", () => {
    assert.equal(nextSegmentAfter(4.01, BA_DOAN, 3), null);
    assert.equal(nextSegmentAfter(4.01, BA_DOAN, -1), null);
    assert.equal(nextSegmentAfter(4.01, [], 0), null);
  });
});

describe("readheadPercent: vi tri dau doc tren track", () => {
  it("dau / giua / cuoi doan bang so", () => {
    assert.equal(readheadPercent(0, 120), 0);
    assert.equal(readheadPercent(60, 120), 50);
    assert.equal(readheadPercent(120, 120), 100);
  });

  it("kep ve [0,100]: vuot thoi luong thi dau doc dung o cuoi track", () => {
    assert.equal(readheadPercent(150, 120), 100);
    assert.equal(readheadPercent(-3, 120), 0);
  });

  it("CHUA biet thoi luong (`null` / 0 / khong huu han) ⇒ 0, khong chia cho 0", () => {
    // `Source.duration` la du lieu backend va co the la `null` (URL chua do thoi luong).
    // Tra `NaN` o day thi `style.left` thanh chuoi rac va dau doc bien mat IM LANG.
    assert.equal(readheadPercent(60, null), 0);
    assert.equal(readheadPercent(60, 0), 0);
    assert.equal(readheadPercent(60, Number.NaN), 0);
    assert.equal(readheadPercent(60, Number.POSITIVE_INFINITY), 0);
    assert.equal(readheadPercent(Number.NaN, 120), 0);
  });
});
