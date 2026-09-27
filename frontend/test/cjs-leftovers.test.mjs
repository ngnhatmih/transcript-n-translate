// Test ghim phep kiem CJS con sot. Mutation da do: bo `Object.defineProperty(exports, ...)` khoi
// fixture thi bai 1 DO (khong bat duoc gi) — tuc bai khong rong. Xem bao cao I-4.
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

test("KHONG bao dong gia voi bundle da shim dung (do tren bundle that 665144 ky tu)", () => {
  const shimmed = [
    "const __cjsModule = { exports: {} };",
    "__cjsModule.exports.probeValue = 41;",
    'const __cjsRequire0 = 1;',
    "const __cjsExport_probeValue = __cjsModule.exports.probeValue;",
    "export { __cjsExport_probeValue as probeValue };",
  ].join("\n");
  assert.deepEqual(findCjsLeftovers(shimmed), []);
});
