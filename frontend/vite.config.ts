import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  // Bắt buộc vì sandbox chặn named pipe: Vite gọi exec("net use") để dò ổ đĩa mạng trên
  // Windows (optimizeSafeRealPathSync). exec() ném `spawn EPERM` NGAY, đồng bộ, và lỗi đó
  // không được bọc try/catch nên thoát thẳng ra request -> 500. preserveSymlinks: true làm
  // getRealPath() bỏ qua hẳn safeRealpathSync, nên không còn chạm tới exec đó.
  // (Repo một package, không symlink -> không có tác dụng phụ.)
  resolve: { preserveSymlinks: true },
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
