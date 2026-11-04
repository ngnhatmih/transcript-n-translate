/**
 * Chép `jassub/dist` vào `public/jassub` trước mỗi lần dev/build.
 *
 * 🔴 VÌ SAO KHÔNG COMMIT THƯ MỤC NÀY: nó là ~5 MB wasm + sourcemap của một gói đã nằm
 * trong `node_modules` (có `package-lock.json` ghim phiên bản). Chép lại từ gói là bản sao
 * DUY NHẤT đúng phiên bản; commit một bản sao là chỗ thứ hai có thể trôi.
 *
 * 🔴 VÌ SAO PHẢI PHỤC VỤ TĨNH: `exports` của `jassub` chặn subpath, nên
 * `import("jassub/dist/worker/…?url")` làm Vite ném
 * `Rollup failed to resolve import`; và worker tự `import()` các chunk cạnh nó
 * (`./renderers/*.js`), nên phải chép NGUYÊN thư mục `dist`, không chỉ worker + wasm.
 */
import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const goc = dirname(dirname(fileURLToPath(import.meta.url)));
const nguon = join(goc, "node_modules", "jassub", "dist");
const dich = join(goc, "public", "jassub");

await rm(dich, { recursive: true, force: true });
await mkdir(dich, { recursive: true });
await cp(nguon, dich, { recursive: true });
console.log(`jassub: chép ${nguon} -> ${dich}`);
