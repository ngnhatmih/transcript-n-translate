/**
 * Khung ba vùng (spec UI §3) — vùng KÊNH, BÀN LÀM VIỆC, HÀNG ĐỢI + header + transport.
 *
 * Lưới CSS là của Task 1 (`src/styles/app.css`: hàng `head/1fr/transport`, cột
 * `214px / 1fr / 286px`, cộng MỘT lớp grain `fixed` + `pointer-events:none`). Tệp này
 * KHÔNG đổi lưới đó: nó chỉ đổ dữ liệu THẬT vào hai vùng bên.
 *
 * `aria-hidden` trên `.grain`: lớp nhiễu là trang trí, không phải nội dung.
 */
import { useReducer } from "react";

import { endpoints } from "../api/endpoints.ts";
import { CompareScreen } from "../screens/CompareScreen.tsx";
import { EditScreen } from "../screens/EditScreen.tsx";
import { initialState, reduce } from "../state/reducer.ts";
import { useApi } from "../state/useApi.ts";
import { useJobStream } from "../state/useJobStream.ts";
import { ChannelZone } from "./ChannelZone.tsx";
import { Header } from "./Header.tsx";
import { QueueZone } from "./QueueZone.tsx";
import { Transport } from "./Transport.tsx";

export function App() {
  // TRẠNG THÁI CLIENT: MỘT reducer cho cả shell (spec/plan: `src/state/reducer.ts`).
  // Task 7 là người gọi THẬT đầu tiên của nó: thanh transport ĐỌC `playing` +
  // `currentSegment` và GHI lại qua hai action `setPlaying`/`setCurrentSegment`.
  // Trước đó reducer chỉ có test — một tầng trạng thái không ai dùng là một tầng sẽ trôi.
  const [ui, dispatch] = useReducer(reduce, initialState);
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
        {/* BÀN LÀM VIỆC: màn Biên tập (§4.1) là màn ĐẦU TIÊN — Task 6.
            `transcript` là PROP (brief Task 6 §1): chưa có đường CHỌN KÊNH (vùng KÊNH
            của Task 4 mới chỉ hiện), nên chưa có bản ghi THẬT nào để đưa vào và `null`
            là sự thật của lượt này — TRẦN đã khai trong báo cáo task. Màn KHÔNG tự
            `fetch`: một chỗ gọi API cho mỗi màn là hai nguồn sự thật.
            `currentSegment` nối thẳng từ reducer: đó là CÙNG một đoạn mà thanh
            transport đang phát, nên lề amber của §4.1 và đầu đọc của §4.1 không thể
            nói hai chuyện khác nhau. */}
        <main className="shell__work">
          {/* Vùng giữa hiện theo `ui.mode` — BA chế độ của spec UI §3 (`Mode` ở
              `state/reducer.ts`), không phải router.
              ⚠️ TRẦN CỦA LƯỢT NÀY, hai lớp, và cả hai đều là trạng thái THẬT:
              (1) KHÔNG có UI nào dispatch `setMode`, nên hôm nay `mode` luôn là
                  `"edit"` và màn Đối chiếu CHƯA với tới được trong trình duyệt;
              (2) chưa có đường CHỌN KÊNH (ERRATA #18 mục 4) nên khi tới được thì
                  `CompareScreen` vẫn nhận `transcript={null}`/`translations={[]}` và
                  chỉ render trạng thái rỗng nói thật.
              Ngày có đường chọn kênh: `transcript` lấy từ bản ghi đang mở và
              `translations` lấy từ `endpoints.getTranslation` cho từng hàng của
              `endpoints.listTranslations` — không phải sửa gì trong `CompareScreen`. */}
          {ui.mode === "compare" ? (
            <CompareScreen transcript={null} translations={[]} />
          ) : (
            <EditScreen transcript={null} currentSegment={ui.currentSegment} />
          )}
        </main>
        <aside className="shell__queue">
          <QueueZone jobs={jobs} />
        </aside>
      </div>
      {/* Thanh transport (§4.1): phát, timecode, track có đầu đọc, ba nút xuất — Task 7.
          ⚠️ TRẦN của lượt này, cùng lớp với `transcript={null}` ở trên: chưa có đường
          CHỌN KÊNH nên `channelId` là `null`, chưa có đường chọn BẢN DỊCH nên
          `translationId` là `null`, và do đó `segments` là `[]`. Thanh transport KHÔNG
          tự bịa nguồn: nút phát VÔ HIỆU, không có `src`, ba nút xuất không có `href`.
          Ngày có đường chọn kênh thì ba prop đó lấy từ `ui.channelId` + bản ghi đang mở
          — không phải sửa gì trong `Transport.tsx`. */}
      <footer className="shell__transport">
        <Transport
          sourceId={ui.channelId}
          segments={[]}
          translationId={null}
          playing={ui.playing}
          currentSegment={ui.currentSegment}
          onPlayingChange={(playing) => dispatch({ type: "setPlaying", playing })}
          onSegmentChange={(i) => dispatch({ type: "setCurrentSegment", i })}
        />
      </footer>
      <div className="grain" aria-hidden />
    </div>
  );
}
