import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "@tanstack/react-router";

import "./styles.css";
import { getRouter } from "./router";

/**
 * DIEM VAO CUA SPA.
 *
 * NGUON GOC: ban Lovable KHONG co tep nay — TanStack Start tu sinh diem vao
 * (`src/start.ts` + `src/server.ts` cua no lo phan SSR). Vi app nay la SPA do Vite
 * dung (xem docblock `vite.config.ts`), can dung mot tep noi `createRoot` voi router.
 *
 * ⚠️ Tep nay TUNG tro toi `docs/ERRATA.md` — DO DUOC LA TEP DO KHONG TON TAI
 * (`Test-Path docs\ERRATA.md` = False). ERRATA cua repo nay nam trong `README.md`
 * (cac muc `## ERRATA #<n>`); mot tham chieu toi tep khong ai mo duoc la mot loi
 * dan sai, khong phai tai lieu.
 *
 * Thu tu import co nghia:
 *   1. `./styles.css` — Tailwind bien dich `@theme`/`@utility` o day. Nap TRUOC
 *      router de lop `* { border-color }` va `body { font-family }` co mat truoc
 *      luot ve dau, neu khong khung hinh dau hien font du phong roi nhay.
 *   2. `./router` — sinh sau khi plugin `TanStackRouterVite` da ghi
 *      `src/routeTree.gen.ts` (buoc build/dev cua Vite chay truoc khi nap module).
 */
const rootEl = document.getElementById("root");
if (rootEl === null) {
  throw new Error('khong thay <div id="root"> trong index.html');
}

createRoot(rootEl).render(
  <StrictMode>
    <RouterProvider router={getRouter()} />
  </StrictMode>,
);