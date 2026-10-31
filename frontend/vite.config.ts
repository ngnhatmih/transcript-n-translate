import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import { fileURLToPath } from "node:url";

/**
 * Vite + Tailwind v4 + TanStack Router.
 *
 * 🔴 NGUỒN GỐC: `_lovable-code/vite.config.ts` chỉ có
 *     `defineConfig({ tanstackStart: { server: { entry: "server" } } })`
 * vì nó bọc `@lovable.dev/vite-tanstack-config` — gói đó CÓ SẴN
 * `tanstackStart`, `viteReact`, `tailwindcss`, `tsConfigPaths`, `nitro`,
 * alias `@`, dedupe React và dò sandbox.
 *
 * Gói `@lovable.dev/*` KHÔNG cài được ngoài Lovable (nó là config riêng của
 * nền tảng đó), nên ở đây khai TƯỜNG MINH đúng những plugin mà gói kia bọc —
 * cùng thứ tự, cùng tuỳ chọn, để kết quả build trùng khớp:
 *
 *     TanStackRouterVite()  → sinh `routeTree.gen.ts` từ `src/routes/`
 *     react()               → JSX + Fast Refresh
 *     tailwindcss()         → Tailwind v4, đọc `@theme` trong `styles.css`
 *
 * ⚠️ KHÁC BIỆT DUY NHẤT so với Lovable: KHÔNG có `nitro`/`tanstackStart`.
 * Đó là quyết định có ghi chép, không phải thiếu sót — xem ERRATA #56 trong
 * `README.md` của repo ("vì sao không dùng TanStack Start").
 *
 * ⚠️ Chỗ này TỪNG trỏ tới `docs/ERRATA.md`, và ĐO ĐƯỢC LÀ TỆP ĐÓ KHÔNG TỒN TẠI
 * (`Test-Path docs\ERRATA.md` = False). ERRATA của repo nằm trong `README.md`.
 */
export default defineConfig({
  plugins: [
    TanStackRouterVite({
      target: "react",
      autoCodeSplitting: true,
      routesDirectory: "./src/routes",
      generatedRouteTree: "./src/routeTree.gen.ts",
    }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "0.0.0.0",
    // ── CỔNG VÀ ĐÍCH BACKEND ĐỌC TỪ MÔI TRƯỜNG ────────────────────────────────────────
    //
    // Hai biến, cả hai đều có lý do ĐO ĐƯỢC, không phải để cho linh hoạt:
    //
    //   `PHUDE_DEV_PORT`          mặc định 5173 — cổng dev thường.
    //   `PHUDE_BACKEND_PORT`      mặc định 8620 — cổng API thường.
    //
    // Vì sao cần: tầng `e2e/` (Chrome thật) gieo một DB RIÊNG vào scratch ngoài repo và
    // dựng backend ở **8631**, để KHÔNG BAO GIỜ chạm 8620 — cổng đó thuộc
    // `src/api/contract.test.ts`, và nó dựa vào DB repo RỖNG (ERRATA #46 mục 4: bị chiếm
    // thì khối hợp đồng cho `pass 254 / fail 0` SAI GIẢ thay vì `252/2`).
    //
    // Và cổng WEB của e2e phải là **3100**, không đổi được: `backend/app/api/app.py:19`
    // chỉ whitelist CORS `http://localhost:3100` / `http://127.0.0.1:3100`. Đổi cổng web
    // là hỏng CORS (đo được), mà sửa CORS thì phải chạm `backend/`.
    //
    // Trước tệp này, đích backend viết cứng `http://127.0.0.1:8620` và không có cách nào
    // trỏ sang 8631 ⇒ `e2e/session.mjs` phải spawn một `dev-server.mjs` riêng (đã bị xoá
    // cùng lúc đổi stack). Hai biến này thay đúng vai trò đó bằng cấu hình, không bằng
    // một tệp proxy thứ hai.
    port: Number(process.env.PHUDE_DEV_PORT ?? 5173),
    // Dev: chuyển `/api` sang backend, đúng khuôn `nginx.conf` của bản tĩnh cũ.
    // Production: nginx vẫn làm việc này (`location /api/`), Vite không tham gia.
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.PHUDE_BACKEND_PORT ?? "8620"}`,
        changeOrigin: true,
        // SSE (`/api/jobs/stream`) không được đệm — cùng lý do đã ghi trong
        // `nginx.conf` dòng 37: đệm thì thanh tiến trình đứng im.
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            if (proxyRes.headers["content-type"]?.includes("text/event-stream")) {
              proxyRes.headers["cache-control"] = "no-cache";
            }
          });
        },
      },
    },
  },
  build: {
    outDir: "dist",
    // Tên tệp CÓ hash nội dung: khác bản rollup cũ (`index.js` cố định) —
    // bản cũ phải khai `Cache-Control: no-cache` cho `/assets/` vì lý do đó
    // (xem `nginx.conf` dòng 42..52). Có hash thì trình duyệt tự tải bản mới.
    assetsDir: "assets",
    sourcemap: false,
  },
});
