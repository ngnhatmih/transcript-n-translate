import { createFileRoute } from "@tanstack/react-router";

import { App } from "@/App";

/**
 * TRANG CHỦ — cả ứng dụng nằm ở đây.
 *
 * 🔴 NGUỒN GỐC: `_lovable-code/src/routes/index.tsx` (24 dòng) là
 * `createFileRoute("/")({ component: Studio })` cộng một `head()` khai tiêu đề và
 * thẻ meta. `head()` là API của TanStack Start (SSR) — app này dựng bằng Vite nên
 * không có nó; tiêu đề và meta đã nằm trong `index.html`.
 *
 * `component` là `App`, không phải `Studio`: route của TanStack Router gọi
 * component KHÔNG tham số, còn `Studio` nhận dữ liệu qua props. `App` là tầng nối
 * API — nó giữ `fetch` và state, rồi truyền xuống `Studio`. Nhờ vậy `Studio` vẫn
 * là bản sao nguyên văn phần JSX của bản đã duyệt.
 */
export const Route = createFileRoute("/")({
  component: App,
});
