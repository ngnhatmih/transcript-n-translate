import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./shell/App";
// FONT nạp TRƯỚC `tokens.css`: `--font-label`/`--font-mono` chỉ là TÊN, còn `@font-face`
// mới là thứ làm tên đó có mặt chữ. Đặt sau cũng chạy, nhưng đặt trước thì khai báo font
// đã sẵn sàng trước khung hình đầu — cùng lý do `preload` đứng trước `stylesheet`.
import "./styles/_font.css";
import "./styles/tokens.css";
// 🔴 GIAO DIỆN MỚI (2026-10-30): ba tệp dưới thay `app.css` cũ (3 096 dòng, đã xoá cùng bốn
// màn cũ). Thứ tự nạp LÀ NGHĨA: `_studio-phan2` sau `_studio` để phần dòng phụ đề / hàng
// đợi / bảng lệnh thắng khi hai bên chạm cùng một lớp; `_duong-ong` nạp cuối vì nó chỉ
// chỉnh thanh đường ống ở header.
//
// ⚠️ VÌ SAO KHÔNG `@import`: trình duyệt tải tệp `@import` THEO CHUỖI (sau khi đã tải tệp
// chứa nó), nên mỗi lần nạp trang là thêm một vòng mạng và một khung hình nhấp nháy không
// có style. Ba `import` ở đây được bundler gộp thành MỘT tệp CSS lúc build — đo được trên
// bản build: chỉ có `dist/assets/index-*.css`, không có tệp CSS thứ hai.
import "./styles/_studio.css";
import "./styles/_studio-phan2.css";
import "./styles/_duong-ong.css";
// Bảng phím tắt §11.4 — tệp RIÊNG vì nó là hệ con độc lập (lớp phủ toàn trang, `z-index`
// riêng) và vì `app.css` cũ đã bị xoá cùng bốn màn: khi đó `Select-String '^\.bp'` trên ba
// tệp kia trả **0**, tức bảng phím rơi về chữ trần. Xem khối đầu `_bang-phim.css`.
import "./styles/_kenh.css";
import "./styles/_bang-phim.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html phải có #root");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
