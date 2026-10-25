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
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { transformSync } from "@swc/core";

registerHooks({
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
