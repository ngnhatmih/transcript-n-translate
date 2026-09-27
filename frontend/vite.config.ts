import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Bắt buộc, không phải sở thích: mặc định của Vite là host `localhost`, mà trên Windows
    // Node phân giải `localhost` thành ::1 — chỉ IPv6 được bind, còn http://127.0.0.1:3100
    // bị từ chối kết nối. Backend chỉ cho CORS đúng hai origin, trong đó có
    // http://127.0.0.1:3100, và lệnh tự kiểm của Task 1 curl đúng địa chỉ đó.
    host: "127.0.0.1",
    port: 3100,
    strictPort: true, // trùng cổng thì BÁO, không lặng lẽ nhảy cổng khác:
    // backend chỉ cho CORS hai origin ở 3100
    proxy: { "/api": "http://127.0.0.1:8620" },
  },
});
