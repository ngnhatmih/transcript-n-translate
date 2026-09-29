// Dev server cho frontend: node:http + node:fs + API JS cua Rollup, KHONG dependency nao khac,
// KHONG spawn tien trinh con. Vite khong dung duoc trong sandbox nay (named pipe -> EPERM),
// nen day la duong thay the.
//   - BUILD ON DEMAND: `rollup.watch()` chay trong CHINH tien trinh nay, nap thang
//     `rollup.config.mjs`, nen khong co `child_process.spawn` nao (spawn stdio:'pipe' -> EPERM).
//   - Cho xong lan build DAU roi moi phuc vu: neu khong, `GET /` tra 404 trong luc build
//     (dung trieu chung review I-2 bat duoc).
//   - serve dist/ tinh (SPA fallback ve index.html)
//   - proxy /api/* sang backend 127.0.0.1:8620
//
// ponytail: khong HMR. Sua ma -> Rollup build lai (~350 ms) -> F5. Tran: mat trang thai trang khi
// F5. Duong nang cap: noi mot kenh SSE bao "build xong" roi `location.reload()` tu client, hoac
// doi sang Vite o moi truong khong chan named pipe.
// ponytail: build loi thi dist CU van duoc phuc vu (khong xoa dist truoc moi lan build). Tran: F5
// co the dang xem bundle cu trong khi terminal bao loi. Duong nang cap: ghi bundle vao dist.tmp
// roi doi ten nguyen tu khi thanh cong.
import { createServer, request as upstream } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, normalize, sep } from "node:path";
import { watch } from "rollup";

const PORT = 3100;

// Cong BACKEND — CAU HINH DUOC bang env, MAC DINH giu nguyen 8620.
//
// Vi sao can: tang Chrome that (Task 12) phai chay tren mot backend GIEO DB o cong rieng,
// vi 8620/8621 la cong CO CHU cua `src/api/contract.test.ts` (no tu spawn backend o 8620 va
// dua vao DB repo RONG — ERRATA #46 muc 4).
//
// 🔴 CHI cong backend duoc cau hinh. Cong dev-server (3100) VAN CUNG, va do la MOT QUYET DINH:
// backend chi whitelist CORS `http://localhost:3100` va `http://127.0.0.1:3100`, nen doi cong
// dev-server la hong CORS — ma sua CORS thi phai cham `backend/` (bi cam trong task frontend).
const BACKEND_PORT = Number(process.env.PHUDE_BACKEND_PORT ?? 8620);
const BACKEND = { host: "127.0.0.1", port: BACKEND_PORT };
const ROOT = new URL("./dist/", import.meta.url);
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};

// ---------------------------------------------------------------------------
// Build: Rollup trong tien trinh. `npm run build` (rollup -c) van la duong build mot lan;
// o day build lai moi khi tep doi.
// ---------------------------------------------------------------------------
const config = (await import("./rollup.config.mjs")).default;

let built = false; // da co it nhat mot lan build thanh cong => dist/ phuc vu duoc
let buildError = null;
let announceFirstBuild;
const firstBuild = new Promise((resolve) => (announceFirstBuild = resolve));

const watcher = watch({ ...config, watch: { clearScreen: false } });
watcher.on("event", (event) => {
  if (event.code === "START") {
    buildError = null;
  } else if (event.code === "BUNDLE_END") {
    if (!built) {
      built = true;
      announceFirstBuild();
      console.log(`[dev-server] build dau tien xong (${event.duration} ms) — http://127.0.0.1:${PORT}`);
    } else {
      console.log(`[dev-server] build lai xong (${event.duration} ms)`);
    }
  } else if (event.code === "ERROR") {
    buildError = event.error;
    // In ra doc duoc, khong phai stack tho: day la thu nguoi sua ma nhin thay.
    console.error(`[dev-server] BUILD LOI: ${event.error.message}`);
  }
});

/** Cho lan build dau (co tran), tra ve true neu dist/ da phuc vu duoc. */
async function waitForFirstBuild() {
  if (built) return true;
  await Promise.race([firstBuild, new Promise((resolve) => setTimeout(resolve, 30_000))]);
  return built;
}

function buildFailurePage() {
  return [
    "<h1>Chua build duoc frontend</h1>",
    "<p>Rollup watch dang loi, nen <code>dist/</code> khong ton tai. Doc loi trong terminal.</p>",
    buildError === null ? "" : `<pre>${String(buildError.message).replace(/[<>&]/g, "")}</pre>`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------
const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");

  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
    const proxied = upstream(
      { ...BACKEND, path: url.pathname + url.search, method: req.method, headers: { ...req.headers, host: `${BACKEND.host}:${BACKEND.port}` } },
      (up) => {
        res.writeHead(up.statusCode, up.headers);
        up.pipe(res);
      },
    );
    // LOI UPSTREAM — KHONG duoc nem ra ngoai.
    //
    // 🔴 Do duoc (EVIDENCE §7): neu handler nay goi `writeHead` SAU khi header da gui (upstream
    // gui header + nua body roi bi cat), `node:http` nem `ERR_HTTP_HEADERS_SENT` NGAY TRONG
    // handler ⇒ mot loi `error` khong ai bat ⇒ CA TIEN TRINH dev-server thoat (`exit 1`).
    // Nguoi dung chi thay app bien mat, khong ro ly do. Vi vay phai re NHANH theo `headersSent`:
    //   - da gui header ⇒ chi con duong dung: cat socket (`res.destroy()`), khong viet them gi;
    //   - chua gui ⇒ 502 doc duoc, va cau neu DUNG cong dang tro (khong hard-code 8620).
    proxied.on("error", (error) => {
      if (res.headersSent) {
        res.destroy();
        return;
      }
      try {
        res.writeHead(502, { "content-type": TYPES[".json"] }).end(
          JSON.stringify({ error: `backend ${BACKEND.host}:${BACKEND.port} khong truy cap duoc: ${error.message}` }),
        );
      } catch {
        // Chan CUOI: mot loi khi tra loi khong bao gio duoc phep giet ca tien trinh.
        res.destroy();
      }
    });
    req.pipe(proxied);
    return;
  }

  if (!(await waitForFirstBuild())) {
    res.writeHead(503, { "content-type": TYPES[".html"] }).end(buildFailurePage());
    return;
  }

  // normalize + cat tien to "..": khong cho di ra ngoai dist/
  const rel = normalize(url.pathname).replace(/^([.][.][\\/])+/, "").replace(/^[\\/]+/, "");
  // Duong dan co duoi file ma khong ton tai thi 404 that, khong tra HTML — neu khong, mot
  // bundle bi thieu se hien ra nhu loi MIME "text/html" kho lan nguyen nhan.
  const candidates =
    rel === "" || rel.endsWith("/") ? [`${rel}index.html`] : extname(rel) === "" ? [rel, "index.html"] : [rel];
  for (const candidate of candidates) {
    try {
      const body = await readFile(new URL(candidate.split(sep).join("/"), ROOT));
      res.writeHead(200, { "content-type": TYPES[extname(candidate)] ?? "application/octet-stream" }).end(body);
      return;
    } catch {
      // thu ung vien ke tiep
    }
  }
  res.writeHead(404, { "content-type": TYPES[".html"] }).end("<h1>404</h1>");
});

// M-1: trung cong phai bao doc duoc, nhung VAN khong nhay cong (backend chi cho CORS hai origin
// o 3100 — nhay cong im lang la sai, giu nguyen tinh chat strict-port).
server.on("error", (error) => {
  if (error.code === "EADDRINUSE") {
    console.error(
      `[dev-server] cong ${PORT} dang bi tien trinh khac chiem. Tat tien trinh do roi chay lai.\n` +
        `[dev-server] KHONG tu nhay sang cong khac: backend chi cho CORS http://localhost:${PORT} va http://127.0.0.1:${PORT}.`,
    );
    process.exit(1);
  }
  console.error(`[dev-server] loi server: ${error.message}`);
  process.exit(1);
});

server.listen(PORT, "127.0.0.1");
