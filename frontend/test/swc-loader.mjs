// Loader test duy nhat cua giai doan nay: `node --test` khong biet .ts/.tsx, nen khong co no
// thi moi test UI chet `ERR_UNKNOWN_FILE_EXTENSION`.
//
// Vi sao khong dung duoc thu khac: sandbox chan named pipe, nen moi loader spawn tien trinh con
// (ts-node, tsx, esbuild) deu EPERM. `module.registerHooks` la hook DONG BO chay trong chinh tien
// trinh hien tai, con `@swc/core` la native binding (napi) — khong spawn. Cung ly do da loai Vite.
//
// Day la ha tang cua MOI test UI sau nay: mot loader hong lam 12 task sau do gia. Vi vay
// `test/swc-loader.test.tsx` ghim chinh no bang duong JSX that.
// (Ban dau cho nay ghi `.test.ts` — SAI duoi tep; `aac8765` sua o PLAN nhung bo sot comment nay.
// Vong re-review bat. Duoi `.tsx` la bat buoc: loader dat `tsx: url.endsWith(".tsx")`.)
//
// ⚠️ CAN HAI HOOK, KHONG PHAI MOT (do duoc khi viet `Studio.test.tsx`):
//   · `load`    bien dich .ts/.tsx. Khong co no: `ERR_UNKNOWN_FILE_EXTENSION`.
//   · `resolve` phan giai alias `@` va duong dan KHONG duoi.
// Chi co `load` thi `import … from "@/api/types"` (ben trong `Studio.tsx`) chet
// `ERR_MODULE_NOT_FOUND: Cannot find package '@/api'` — vi `package.json` KHONG co
// truong `imports`, con Vite lo alias nay luc build. Test chay bang `node` thi phai
// tu lam. Va vi `Studio.tsx` import `./use-player` (khong duoi), `resolve` cung phai
// thu them `.ts`/`.tsx` — dung luat phan giai cua bundler.
import { registerHooks } from "node:module";
import { existsSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve as resolvePath } from "node:path";
import { transformSync } from "@swc/core";

/** Goc `src/` — cung gia tri voi alias `@` trong `vite.config.ts`. */
const GOC_SRC = resolvePath(dirname(fileURLToPath(import.meta.url)), "..", "src");

/** Thu cac duoi ma bundler thu, theo dung thu tu do. */
const DUOI = [".ts", ".tsx", ".mjs", ".js", "/index.ts", "/index.tsx"];

/**
 * Tra ve duong dan THAT cua mot specifier, hoac null.
 *
 * ⚠️ `existsSync` DUNG cho ca THU MUC. Ban dau ham nay chi hoi `existsSync` va tra ve
 * ngay, nen `import "./Studio.tsx"` phan giai duoc nhung mot specifier tro vao thu muc
 * tra ve DUONG DAN THU MUC -> `EISDIR: illegal operation on a directory, read`.
 * Phai hoi `statSync(...).isFile()`.
 */
function timTep(goc) {
  const laTep = (p) => {
    try {
      return statSync(p).isFile();
    } catch {
      return false;
    }
  };
  if (laTep(goc)) return goc;
  for (const d of DUOI) {
    const thu = goc + d;
    if (laTep(thu)) return thu;
  }
  return null;
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    // 1. Alias `@/…` -> `<frontend>/src/…`
    if (specifier.startsWith("@/")) {
      const goc = resolvePath(GOC_SRC, specifier.slice(2));
      const tep = timTep(goc);
      if (tep !== null) return { url: pathToFileURL(tep).href, shortCircuit: true };
    }

    // 2. Duong dan tuong doi KHONG duoi (`./use-player`, `../api/types`)
    if ((specifier.startsWith("./") || specifier.startsWith("../")) && context.parentURL) {
      const goc = resolvePath(dirname(fileURLToPath(context.parentURL)), specifier);
      const tep = timTep(goc);
      if (tep !== null) return { url: pathToFileURL(tep).href, shortCircuit: true };
    }

    return nextResolve(specifier, context);
  },

  load(url, context, nextLoad) {
    if (url.startsWith("file:") && (url.endsWith(".tsx") || url.endsWith(".ts"))) {
      const tsx = url.endsWith(".tsx");
      const out = transformSync(readFileSync(new URL(url), "utf8"), {
        filename: new URL(url).pathname,
        jsc: { parser: { syntax: "typescript", tsx }, target: "es2022",
               transform: { react: { runtime: "automatic" } } },
        module: { type: "es6" },
      });
      return { format: "module", source: out.code, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});
