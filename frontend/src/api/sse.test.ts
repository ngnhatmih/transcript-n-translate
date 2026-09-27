/**
 * Test cua parser SSE — ham THUAN: khong DOM, khong mang, khong React.
 *
 * Vi sao tach khoi `useJobStream.ts`: tep do import `react`, ma `react` la CJS
 * trong repo nay, nen no chi duoc Playwright phu o Task 12. Parser thi khong can
 * gi ngoai `JSON.parse`, nen no duoc ghim o day bang `node --test` (Vitest khong
 * dung duoc trong sandbox nay — xem ERRATA trong plan).
 *
 * Dinh dang THAT cua backend (doc `backend/app/api/sse.py`, ham `format_sse` va
 * `stream_events`): moi su kien la `data: {json}` roi HAI lan xuong dong, con
 * dong comment (`: connected`, `: heartbeat`) KHONG co tien to `data:`. Do la ly
 * do bai "bo qua dong comment" ton tai: coi `: connected` la su kien thi su kien
 * DAU TIEN cua moi ket noi la rac, va khong bai nao khac bat duoc loi do.
 *
 * Chay tu `frontend/` bang `npm test` (script co glob; loc theo ten tep khong
 * hoat dong vi glob nam trong `package.json`).
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { createSseParser, reconnectDelay } from "./sse.ts";

describe("parser SSE", () => {
  it("tach duoc mot su kien hoan chinh", () => {
    const p = createSseParser();
    assert.deepEqual(p.push('data: {"id":1}\n\n'), [{ id: 1 }]);
  });

  it("ghep lai manh bi cat giua hai lan doc", () => {
    const p = createSseParser();
    assert.deepEqual(p.push('data: {"id"'), []); // chua du de chot su kien
    assert.deepEqual(p.push(':1}\n\n'), [{ id: 1 }]); // xong o lan doc sau

    // Ca thu hai, va day moi la ca lam bai nay khac bai "cat DUNG o ranh gioi":
    // manh dau chua MOT su kien da xong ROI mot su kien bi cat. Phan du cua su
    // kien bi cat phai con nguyen trong bo dem — xoa sach bo dem (`buf = ""`) thi
    // phan du do mat VINH VIEN va bai nay phai do.
    assert.deepEqual(p.push('data: {"id":2}\n\ndata: {"id"'), [{ id: 2 }]);
    assert.deepEqual(p.push(':3}\n\n'), [{ id: 3 }]);
    // Manh thu tu noi tiep dung cho: neu phan du bi lech offset thi su kien sau
    // se hong hoac mat.
    assert.deepEqual(p.push('data: {"id":4}\n\n'), [{ id: 4 }]);
  });

  it("bo qua dong comment giu nhip tim", () => {
    const p = createSseParser();
    // `: connected` la byte DAU TIEN backend gui cho moi ket noi, va
    // `: heartbeat` gui moi khi im — ca hai deu KHONG phai su kien.
    assert.deepEqual(p.push(": connected\n\n"), []);
    assert.deepEqual(p.push(": heartbeat\n\n"), []);
    // Va comment khong duoc lam mat su kien di kem sau no.
    assert.deepEqual(p.push('data: {"id":7}\n\n'), [{ id: 7 }]);
  });

  it("tra NHIEU su kien tu mot lan doc", () => {
    const p = createSseParser();
    assert.deepEqual(p.push('data: {"id":1}\n\ndata: {"id":2}\n\n'), [{ id: 1 }, { id: 2 }]);
  });

  it("json hong thi bo qua su kien do, khong nem", () => {
    // Mot su kien hong khong duoc giet ca stream: mat ket noi vi mot dong rac la
    // mat luon tien do cua moi job khac.
    const p = createSseParser();
    assert.deepEqual(p.push("data: {khong-phai-json}\n\n"), []);
    // Stream phai CON SONG sau su kien hong.
    assert.deepEqual(p.push('data: {"id":3}\n\n'), [{ id: 3 }]);
  });

  it("su kien bi cat DUNG o ranh gioi xuong dong", () => {
    // Khac bai "ghep lai manh bi cat": o day manh dau ket thuc bang DUNG mot
    // xuong dong, nen cap `\n\n` chi hien ra khi manh sau toi. `indexOf("\n\n")`
    // phai giu nguyen phan du thay vi coi mot `\n` la ket thuc su kien.
    const p = createSseParser();
    assert.deepEqual(p.push('data: {"id":1}\n'), []);
    assert.deepEqual(p.push("\n"), [{ id: 1 }]);
  });
});

describe("reconnectDelay", () => {
  it("attempt dau tra baseMs, attempt giua gap doi, attempt lon cham cap", () => {
    // Ba gia tri thuoc ba mien khac nhau cua ham: goc, dang nhan doi, va da bi
    // chan. Chi ghim goc thi nhanh chan tren khong duoc kiem.
    assert.equal(reconnectDelay(0), 500);
    assert.equal(reconnectDelay(3), 4000);
    assert.equal(reconnectDelay(10), 30_000);
  });

  it("attempt rat lon van la so huu han, khong Infinity/NaN", () => {
    // `2 ** attempt` tran thanh `Infinity` o attempt du lon; neu khong co
    // `Math.min` thi mot lan dut ket noi se dat hen gio bang `Infinity`.
    const delay = reconnectDelay(5000);
    assert.ok(Number.isFinite(delay), `phai huu han, nhan ${delay}`);
    assert.equal(delay, 30_000);
  });

  it("baseMs/capMs la tham so, khong phai hang so cua module", () => {
    assert.equal(reconnectDelay(0, 100, 250), 100);
    assert.equal(reconnectDelay(5, 100, 250), 250);
  });
});
