/**
 * Khung ba vùng (spec UI §3) — vùng KÊNH, BÀN LÀM VIỆC, HÀNG ĐỢI + header + transport.
 *
 * Lưới CSS là của Task 1 (`src/styles/app.css`: hàng `head/1fr/transport`, cột
 * `214px / 1fr / 286px`, cộng MỘT lớp grain `fixed` + `pointer-events:none`). Tệp này
 * KHÔNG đổi lưới đó: nó chỉ đổ dữ liệu THẬT vào hai vùng bên.
 *
 * `aria-hidden` trên `.grain`: lớp nhiễu là trang trí, không phải nội dung.
 */
import { endpoints } from "../api/endpoints.ts";
import { useApi } from "../state/useApi.ts";
import { useJobStream } from "../state/useJobStream.ts";
import { ChannelZone } from "./ChannelZone.tsx";
import { Header } from "./Header.tsx";
import { QueueZone } from "./QueueZone.tsx";

export function App() {
  // KÊNH: một lượt đọc `GET /api/sources`. `[]` vì đường dẫn không phụ thuộc gì.
  const sources = useApi(() => endpoints.listSources(), []);
  // HÀNG ĐỢI: MỘT subscription SSE cho cả app (ảnh chụp + sự kiện), không request riêng.
  const jobs = useJobStream();

  return (
    <div className="shell">
      <Header />
      <div className="shell__mid">
        <aside className="shell__channels">
          {/* KÊNH nhận `jobs` để suy TRẠNG THÁI TỪNG BƯỚC qua `payload.source_id`
              (hợp đồng: `routes_jobs._job_json` trả `payload`; `IngestPayload`/
              `AsrPayload` buộc có `source_id`). Cùng MỘT bản đồ với HÀNG ĐỢI — không
              request thứ hai, không bản sao thứ hai. */}
          <ChannelZone
            sources={sources.data}
            jobs={jobs}
            loading={sources.loading}
            error={sources.error}
          />
        </aside>
        {/* BÀN LÀM VIỆC: màn hình Biên tập là Task 5–T11; Task 4 chỉ giữ đúng ô lưới. */}
        <main className="shell__work" />
        <aside className="shell__queue">
          <QueueZone jobs={jobs} />
        </aside>
      </div>
      {/* Thanh transport (phát/timecode/xuất) là Task 7 + Task 10. */}
      <footer className="shell__transport" />
      <div className="grain" aria-hidden />
    </div>
  );
}
