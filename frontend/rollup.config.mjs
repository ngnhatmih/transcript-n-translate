// Cau hinh Rollup thay cho Vite.
//
// Vi sao: sandbox chan named pipe, nen moi tien trinh con spawn voi stdio:'pipe' deu EPERM.
// esbuild (service process) va Vite (exec("net use")) deu chet vi ly do do. Rollup chay
// TRONG tien trinh Node hien tai (native binding nap bang napi, khong spawn), nen no khong
// cham vao named pipe lan nao. Moi plugin duoi day cung chay trong tien trinh:
//   - @swc/core.transformSync : native binding, khong spawn
//   - interop CJS tu viet      : khong can @rollup/plugin-commonjs (khong cai duoc: npm cache EPERM)
//   - resolve bang import.meta.resolve : resolver cua chinh Node, khong spawn
// Khong co dependency nao ngoai rollup + @swc/core (ca hai da co san trong node_modules).
import { existsSync, readFileSync, rmSync } from "node:fs";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { transformSync } from "@swc/core";

const ROOT = dirname(fileURLToPath(import.meta.url));

// React 19 chi phat CJS (`exports.X = ...`), khong co entry ESM. Thay vi keo ca cay shim
// index.js (co re-nhanh process.env.NODE_ENV -> keo theo ca ban development 31k dong), tro
// thang toi file production da duoc dong goi san. Do la ban build that, khong phai ban dev.
const CJS_ENTRIES = {
  react: "react/cjs/react.production.js",
  "react/jsx-runtime": "react/cjs/react-jsx-runtime.production.js",
  "react/jsx-dev-runtime": "react/cjs/react-jsx-dev-runtime.production.js",
  "react-dom": "react-dom/cjs/react-dom.production.js",
  "react-dom/client": "react-dom/cjs/react-dom-client.production.js",
  scheduler: "scheduler/cjs/scheduler.production.js",
};

const EXTENSIONS = ["", ".tsx", ".ts", ".jsx", ".js", "/index.tsx", "/index.ts", "/index.js"];
const IS_NODE_MODULES = /[\\/]node_modules[\\/]/;

/** Phan giai moi specifier bang API cua Node / kiem tra ton tai file. Khong spawn gi. */
function resolvePlugin() {
  return {
    name: "resolve-nospawn",
    resolveId(source, importer) {
      if (CJS_ENTRIES[source] !== undefined) {
        const target = join(ROOT, "node_modules", CJS_ENTRIES[source]);
        return IS_NODE_MODULES.test(target) ? { id: target, moduleSideEffects: false } : target;
      }
      if (isAbsolute(source)) {
        for (const ext of EXTENSIONS) if (existsSync(source + ext)) return source + ext;
        return null;
      }
      if (source.startsWith(".")) {
        const base = resolve(dirname(importer), source);
        for (const ext of EXTENSIONS) if (existsSync(base + ext)) return base + ext;
        return null;
      }
      // Specifier "tran" (khong phai duong dan): de Node phan giai qua field `exports`.
      try {
        return fileURLToPath(import.meta.resolve(source));
      } catch {
        return null;
      }
    },
  };
}

/** TS/TSX -> ESM bang SWC native, chay trong tien trinh. Chi ap dung cho ma nguon cua ta. */
function swcPlugin() {
  return {
    name: "swc-nospawn",
    transform(code, id) {
      if (IS_NODE_MODULES.test(id) || !/\.[cm]?[jt]sx?$/.test(id)) return null;
      const out = transformSync(code, {
        filename: id,
        sourceMaps: true,
        jsc: {
          parser: {
            syntax: "typescript",
            tsx: id.endsWith(".tsx") || id.endsWith(".jsx"),
            decorators: false,
          },
          transform: { react: { runtime: "automatic", development: false } },
          target: "es2022",
        },
        module: { type: "es6" },
      });
      return { code: out.code, map: out.map ? JSON.parse(out.map) : null };
    },
  };
}

/**
 * Interop CommonJS -> ESM, tu viet, chay trong tien trinh.
 * Du cho React 19: file production CJS chi gom `exports.X = ...` o muc cao nhat va
 * `require("...")` tinh. Khong co `require` dong, khong co `__esModule`.
 */
function cjsPlugin() {
  return {
    name: "cjs-inproc",
    transform(code, id) {
      if (!IS_NODE_MODULES.test(id) || !id.endsWith(".js")) return null;
      if (!/\brequire\(|\bmodule\.exports\b|\bexports\./.test(code)) return null;

      const specs = [];
      const withRequires = code
        .replace(/process\.env\.NODE_ENV/g, '"production"')
        .replace(/require\(\s*["']([^"']+)["']\s*\)/g, (_match, spec) => {
          let index = specs.indexOf(spec);
          if (index < 0) index = specs.length, specs.push(spec);
          return `__cjsRequire${index}`;
        });

      const names = new Set();
      for (const match of code.matchAll(/(?:^|[^.\w$])exports\.([A-Za-z_$][\w$]*)\s*=/gm)) {
        names.add(match[1]);
      }

      const body = withRequires
        .replace(/\bmodule\.exports\b/g, "__cjsModule.exports")
        .replace(/(?<![.\w$])exports\./g, "__cjsModule.exports.");

      // Ten local phai co tien to rieng: file CJS cua React khai bao ca `Children`,
      // `Component`... o pham vi module, nen `export const Children = ...` se trung ten.
      const out = [
        ...specs.map((spec, index) => `import __cjsRequire${index} from ${JSON.stringify(spec)};`),
        "const __cjsModule = { exports: {} };",
        body,
        "export default __cjsModule.exports;",
        ...[...names].map((name) => `const __cjsExport_${name} = __cjsModule.exports.${name};`),
        `export { ${[...names].map((name) => `__cjsExport_${name} as ${name}`).join(", ")} };`,
      ].join("\n");

      return { code: out, map: null, moduleSideEffects: false };
    },
  };
}

/** CSS: gom thu tu import thanh mot file duy nhat, khong keo them dependency. */
function cssPlugin() {
  const sheets = [];
  return {
    name: "css-inproc",
    load(id) {
      if (!id.endsWith(".css")) return null;
      sheets.push(readFileSync(id, "utf8"));
      return "export default undefined;";
    },
    generateBundle() {
      if (sheets.length === 0) return;
      this.emitFile({ type: "asset", fileName: "assets/index.css", source: sheets.join("\n") });
    },
  };
}

/** index.html nguon la nguon duy nhat; thay the script dev tro sang bundle da build. */
function htmlPlugin() {
  return {
    name: "html-inproc",
    generateBundle() {
      const source = readFileSync(join(ROOT, "index.html"), "utf8");
      const html = source.replace(
        /<script[^>]*src="\/src\/main\.tsx"[^>]*><\/script>/,
        '<link rel="stylesheet" href="/assets/index.css" />\n    <script type="module" src="/assets/index.js"></script>',
      );
      if (html === source) this.error("index.html: khong tim thay the <script src=/src/main.tsx> de thay");
      this.emitFile({ type: "asset", fileName: "index.html", source: html });
    },
  };
}

/** Cua chan cuoi: bundle phai la ESM khép kín, khong con specifier "tran" nao. */
function guardPlugin() {
  const BARE = /(?:^|[^\w$.])(?:import|export)\s*(?:[^"'();]*?\bfrom\s*)?["'](?!\.|\/)[^"']+["']/gm;
  return {
    name: "assert-no-bare-imports",
    generateBundle(_options, bundle) {
      for (const file of Object.values(bundle)) {
        if (file.type !== "chunk") continue;
        for (const imported of file.imports) {
          if (!imported.startsWith(".") && !imported.startsWith("/")) {
            this.error(`bundle con import "tran" chua phan giai: ${imported}`);
          }
        }
        const leftover = file.code.match(BARE);
        if (leftover) this.error(`bundle con specifier "tran": ${leftover.join(", ")}`);
      }
    },
  };
}

rmSync(join(ROOT, "dist"), { recursive: true, force: true });

export default {
  input: join(ROOT, "src", "main.tsx"),
  output: {
    dir: join(ROOT, "dist"),
    format: "es",
    entryFileNames: "assets/index.js",
    chunkFileNames: "assets/[name]-[hash].js",
    assetFileNames: "assets/[name][extname]",
    sourcemap: true,
  },
  plugins: [resolvePlugin(), cjsPlugin(), swcPlugin(), cssPlugin(), htmlPlugin(), guardPlugin()],
  onwarn(warning, warn) {
    if (warning.code === "UNRESOLVED_IMPORT" || warning.code === "MISSING_EXPORT") throw new Error(warning.message);
    warn(warning);
  },
};
