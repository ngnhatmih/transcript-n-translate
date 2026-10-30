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
 * Đó là quyết định có ghi chép, không phải thiếu sót — xem
 * `docs/ERRATA.md` mục "vì sao không dùng TanStack Start".
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
    port: 5173,
    // Dev: chuyển `/api` sang backend, đúng khuôn `nginx.conf` của bản tĩnh cũ.
    // Production: nginx vẫn làm việc này (`location /api/`), Vite không tham gia.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8620",
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
