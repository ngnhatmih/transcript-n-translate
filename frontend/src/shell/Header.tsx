/**
 * Dải trên cùng của khung ba vùng (spec UI §3).
 *
 * Task 10 nối `StatusStrip` (§4.8: Ollama / VRAM / giai đoạn đang chạy) vào đây. Dữ liệu
 * vào qua **PROP**, và `Header` **KHÔNG** tự gọi API: `App` là nơi DUY NHẤT đọc
 * `/api/status` cho cả dải lẫn panel — hai nơi gọi cùng một endpoint là hai lượt đọc và
 * hai nguồn sự thật cho cùng một hàng dữ liệu (`useApi` không cache).
 *
 * KHÔNG in `queue_depth` ở đây: đó là đại lượng backend đã tính và HÀNG ĐỢI đã hiện
 * (`Global Constraints`: CPS, `available`, số bản dịch bị ảnh hưởng — cùng một lớp lỗi).
 */
import type { Status } from "../api/types.ts";
import { StatusStrip } from "../screens/OllamaDown.tsx";

export function Header({ status }: { status: Status | null }) {
  return (
    <header className="shell__head">
      <h1 className="head__ten">PHÒNG THU BIÊN TẬP</h1>
      <StatusStrip status={status} />
    </header>
  );
}
