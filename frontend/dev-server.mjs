// Dev/prod server cho frontend: node:http + node:fs, khong dependency, khong spawn tien trinh con.
// Vite khong dung duoc trong sandbox nay (named pipe -> EPERM), nen day la duong thay the.
//   - serve dist/ tinh (SPA fallback ve index.html)
//   - proxy /api/* sang backend 127.0.0.1:8620
import { createServer, request as upstream } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, normalize, sep } from "node:path";

const ROOT = new URL("./dist/", import.meta.url);
const PORT = 3100;
const BACKEND = { host: "127.0.0.1", port: 8620 };
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

createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");

  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
    const proxied = upstream(
      { ...BACKEND, path: url.pathname + url.search, method: req.method, headers: { ...req.headers, host: `${BACKEND.host}:${BACKEND.port}` } },
      (up) => {
        res.writeHead(up.statusCode, up.headers);
        up.pipe(res);
      },
    );
    proxied.on("error", () => {
      res.writeHead(502, { "content-type": TYPES[".json"] }).end('{"error":"backend 8620 khong truy cap duoc"}');
    });
    req.pipe(proxied);
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
}).listen(PORT, "127.0.0.1", () => console.log(`http://127.0.0.1:${PORT}`));
