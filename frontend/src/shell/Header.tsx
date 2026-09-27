/**
 * Dải trên cùng của khung ba vùng (spec UI §3).
 *
 * CHỈ có tên bàn làm việc. `StatusPill` (Ollama / VRAM / giai đoạn) KHÔNG nằm ở Task 4:
 * nó đọc `GET /api/status`, và in `queue_depth` ở đây sẽ là nơi THỨ HAI tính một đại
 * lượng backend đã tính (`Global Constraints`: CPS, `available`, số bản dịch bị ảnh
 * hưởng — cùng một lớp lỗi). Task 10 nối nó vào, cạnh thanh transport.
 */
export function Header() {
  return (
    <header className="shell__head">
      <h1 className="head__ten">PHÒNG THU BIÊN TẬP</h1>
    </header>
  );
}
