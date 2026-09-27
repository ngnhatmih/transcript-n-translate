// Phep kiem "bundle con ma CJS chua duoc shim khong" — tach rieng khoi rollup.config.mjs de test
// duoc bang `node --test` (nap rollup.config.mjs la rmSync dist + chay build, khong test duoc).
//
// Vi sao can: shim `cjs-inproc` trong rollup.config.mjs la shim TU VIET, rat hep — no chi doi duoc
// `exports.X = ...`, `module.exports`, `require("...")`. Goi CJS dung dang khac (vi du
// `Object.defineProperty(exports, "__esModule", { value: true })` — dung dang ma nhieu goi tren npm
// dung) di qua build XANH, guard im lang, roi bundle chua `exports` tran va trinh duyet nem
// `ReferenceError: exports is not defined`. Day chinh la lo hong ma "build xanh" khong bat duoc.
//
// Ba mau duoi day da do tren bundle THAT (React 19 + react-dom, 665144 ky tu):
//   - `exports` tran: 5 lan, NHUNG ca 5 deu la property key trong `{ exports: {} }` cua chinh shim
//     (`const __cjsModule = { exports: {} }`). Vi vay phai loai truong hop theo sau la `:`.
//   - `module.exports` tran: 0 (shim doi thanh `__cjsModule.exports`)
//   - `require(` tran: 0 (shim doi thanh `__cjsRequire0(`)
export const CJS_LEFTOVER_PATTERNS = [
  {
    name: "exports tran (khong phai __cjsModule.exports)",
    // (?![\w$:]) loai `exports:` (property key cua chinh shim) va `exportsFoo`.
    re: /(?:^|[^.\w$])exports(?![\w$:])/,
  },
  {
    name: "module.exports tran",
    re: /(?:^|[^.\w$])module\s*\.\s*exports(?![\w$])/,
  },
  {
    name: "require(...) tran",
    re: /(?:^|[^.\w$])require\s*\(/,
  },
];

/** Tra ve danh sach mau CJS con sot trong `code` (rong = sach). */
export function findCjsLeftovers(code) {
  const hits = [];
  for (const { name, re } of CJS_LEFTOVER_PATTERNS) {
    const match = re.exec(code);
    if (match === null) continue;
    const sample = code.slice(match.index, match.index + 64).split("\n")[0].trim();
    hits.push({ name, sample });
  }
  return hits;
}
