// Test ghim phep kiem CJS con sot.
//
// Mutation DA DO de chung minh test khong rong: xoa mau "exports tran" khoi CJS_LEFTOVER_PATTERNS
// trong build/cjs-leftovers.mjs => bai 1 DO (`pass 4 fail 1`, exit 1); khoi phuc => XANH (`pass 5`).
// Phai pha THU NO BAO VE, khong phai pha fixture: bo dong `Object.defineProperty(exports, ...)`
// khoi fixture KHONG lam bai 1 do, vi dong `exports.probeValue = 41;` con lai van khop mau
// (lookahead chi loai `[\w$:]`, ma o day `exports` theo sau la `.`) — da do, dung khai mot mutation
// khong that.
import { test } from "node:test";
import assert from "node:assert/strict";

import { findCjsLeftovers } from "../build/cjs-leftovers.mjs";

// Dung nguyen dang CJS ma 370 tep trong node_modules cua may nay dung va shim cjs-inproc KHONG doi duoc.
const CJS_ESMODULE_FIXTURE = [
  '"use strict";',
  'Object.defineProperty(exports, "__esModule", { value: true });',
  "exports.probeValue = 41;",
].join("\n");

test("bat duoc mau Object.defineProperty(exports, \"__esModule\", ...) — thu build xanh van lot", () => {
  const hits = findCjsLeftovers(CJS_ESMODULE_FIXTURE);
  assert.ok(hits.length > 0, "phai bat duoc `exports` tran");
  assert.ok(
    hits.some((hit) => hit.name.includes("exports")),
    `mau bat duoc phai la exports tran, nhan duoc: ${JSON.stringify(hits)}`,
  );
});

test("bat duoc require() tran va module.exports tran", () => {
  assert.equal(findCjsLeftovers('var a = require("./x");').length, 1);
  assert.equal(findCjsLeftovers("module.exports = { a: 1 };").length, 1);
});

test("sample KHONG duoc rong khi `exports` dung dau dong (thong bao loi phai co bang chung)", () => {
  const hits = findCjsLeftovers('"use strict";\nexports.probeValue = 41;');
  assert.equal(hits.length, 1);
  assert.ok(hits[0].sample.length > 0, `sample rong: ${JSON.stringify(hits[0])}`);
  assert.ok(hits[0].sample.includes("exports"), `sample phai chua dinh danh: ${JSON.stringify(hits[0])}`);
});

// Ten bai noi DUNG pham vi cua no: day la chuoi NAM DONG TU DUNG, khong phai bundle that.
// (Ban dau bai ten la "... do tren bundle that 665144 ky tu" — ten do nhan mot phep do bai
// KHONG lam. Tinh khong-bao-dong-gia tren bundle THAT duoc `npm run build` chung minh: guard
// `assert-no-cjs-leftovers` chay o `generateBundle` tren bundle that, va build XANH.)
test("KHONG bao dong gia voi chuoi da shim dung (nam dong tu dung)", () => {
  const shimmed = [
    "const __cjsModule = { exports: {} };",
    "__cjsModule.exports.probeValue = 41;",
    'const __cjsRequire0 = 1;',
    "const __cjsExport_probeValue = __cjsModule.exports.probeValue;",
    "export { __cjsExport_probeValue as probeValue };",
  ].join("\n");
  assert.deepEqual(findCjsLeftovers(shimmed), []);
});
