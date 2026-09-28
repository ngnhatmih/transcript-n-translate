/**
 * Khung ba vùng (spec UI §3) — vùng KÊNH, BÀN LÀM VIỆC, HÀNG ĐỢI + header + transport.
 *
 * Lưới CSS là của Task 1 (`src/styles/app.css`: hàng `head / auto / 1fr / transport`, cột
 * `214px / 1fr / 286px`, cộng MỘT lớp grain `fixed` + `pointer-events:none`). Hàng `auto`
 * thứ hai là chỗ của panel §4.8 (`Task 10`). MỖI con của `.shell` khai `grid-row` TƯỜNG
 * MINH — xem luật ở `.shell` trong `app.css`: auto-placement theo thứ tự DOM làm hàng `auto`
 * "cướp chỗ" của bàn làm việc khi panel vắng. Tệp này KHÔNG đổi lưới đó: nó chỉ đổ dữ liệu
 * THẬT vào hai vùng bên.
 *
 * `aria-hidden` trên `.grain`: lớp nhiễu là trang trí, không phải nội dung.
 */
import { useEffect, useReducer, useRef } from "react";

import { endpoints } from "../api/endpoints.ts";
import { CompareScreen } from "../screens/CompareScreen.tsx";
import { EditScreen } from "../screens/EditScreen.tsx";
import { GlossaryScreen } from "../screens/GlossaryScreen.tsx";
import { OllamaDown } from "../screens/OllamaDown.tsx";
import { chonTranscript, chonTranslation } from "../state/channelData.ts";
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
  // Task W1 đóng nốt hai action còn thiếu đường: `setMode` (bộ chọn chế độ ở `Header`)
  // và `selectChannel` (mỗi mục của vùng KÊNH) — trước W1 cả hai có **0 lượt dispatch**.
  const [ui, dispatch] = useReducer(reduce, initialState);
  // KÊNH: một lượt đọc `GET /api/sources`. `[]` vì đường dẫn không phụ thuộc gì.
  const sources = useApi(() => endpoints.listSources(), []);
  // HÀNG ĐỢI: MỘT subscription SSE cho cả app (ảnh chụp + sự kiện), không request riêng.
  const jobs = useJobStream();
  // §4.8 — TRẠNG THÁI HỆ THỐNG: MỘT lượt `GET /api/status` cho CẢ dải ở header LẪN panel.
  // `reload` của hook chính là nút `[ Thử lại ]`: nó tăng một con số, effect chạy lại, và
  // đó là một request THẬT mới (không cache, `useApi` TRẦN).
  const status = useApi(() => endpoints.status(), []);
  // REGISTRY: MỘT lượt `GET /api/registry`. Đây là NGUỒN DUY NHẤT của `capabilities.available`
  // — client KHÔNG suy lại từ `runtime`/`model_ref` (Global Constraints dòng 25).
  const engines = useApi(() => endpoints.registry(), []);
  const specs = engines.data === null ? [] : [...engines.data.asr, ...engines.data.mt];

  // ---------------------------------------------------------------------------
  // SUY DỮ LIỆU CHO BA MÀN (Task W1) — theo đúng comment cũ ở vùng BÀN LÀM VIỆC:
  // `listTranscripts()` → chọn bản ghi của kênh → `getTranscript(tid)`; và
  // `listTranslations(tid)` → `getTranslation` cho TỪNG hàng.
  // ---------------------------------------------------------------------------

  // DANH SÁCH TRANSCRIPT: MỘT lượt cho CẢ app (`[]` — đường dẫn không phụ thuộc gì), CỘNG
  // ngòi nổ đọc lại ở dưới (kênh đổi, hoặc job của kênh đang chọn chuyển trạng thái).
  // Đọc một lần rồi suy ra bản ghi đang mở, thay vì mỗi màn tự hỏi một câu khác nhau.
  const transcripts = useApi(() => endpoints.listTranscripts(), []);
  // QUY ƯỚC "id lớn nhất là hiện tại" nằm trong `channelData.chonTranscript` — CÙNG quy ước
  // với `ChannelZone.buocCuaKenh` (hai quy ước cho một câu hỏi là nguồn sự thật thứ hai).
  const banGhiTomTat = chonTranscript(transcripts.data ?? [], ui.channelId);
  const tid = banGhiTomTat === null ? null : banGhiTomTat.id;

  // BẢN GHI ĐANG MỞ. ⚠️ `channelId === null` ⇒ `tid === null` ⇒ `Promise.resolve(null)`:
  // KHÔNG được gọi `/api/transcripts/null` (đo được bằng số request ở server trong test).
  const transcript = useApi(
    () => (tid === null ? Promise.resolve(null) : endpoints.getTranscript(tid)),
    [tid],
  );

  // BẢN DỊCH CỦA BẢN GHI ĐÓ — **MỘT** hook, **N request** qua `Promise.all` (đúng comment
  // cũ: "translations lấy từ `endpoints.getTranslation` cho từng hàng của
  // `endpoints.listTranslations`"). ⚠️ KHÔNG gọi `useApi` trong vòng lặp: số hook phải cố
  // định giữa các lần render (Rules of Hooks), nên N request nằm TRONG một hook.
  // Kết quả đúng kiểu prop của `CompareScreen`: `TranslationDetail[]`.
  const translations = useApi(async () => {
    if (tid === null) return [];
    const rows = await endpoints.listTranslations(tid);
    return await Promise.all(rows.map((row) => endpoints.getTranslation(row.id)));
  }, [tid]);
  // Bản dịch để XUẤT: `status === "done"` và mới nhất (chưa xong thì chưa có nội dung dịch).
  const banDichXuat = chonTranslation(translations.data ?? []);

  // ---------------------------------------------------------------------------
  // NGÒI NỔ ĐỌC LẠI `/api/transcripts` (vòng sửa W1 #1 — `Minor #3`, LỖI CHỨC NĂNG)
  //
  // ĐO ĐƯỢC trước vòng sửa: danh sách transcript được đọc ĐÚNG MỘT lần với `deps = []`, và
  // `transcripts.reload` không được nối vào đâu (`grep '\.reload'` chỉ ra `status.reload`)
  // ⇒ sau khi job `ingest`/`asr` xong, BẢN GHI MỚI KHÔNG BAO GIỜ HIỆN cho tới khi tải lại
  // cả trang. W2 (nạp tệp) và W3 (bắt đầu dịch) đụng ngay chỗ này.
  //
  // HAI vế của một ngòi nổ, và cả hai đều phải có:
  //   (a) `ui.channelId` ĐỔI ⇒ đọc lại danh sách (bản ghi đang mở của kênh mới có thể chưa
  //       có trong ảnh chụp cũ). Ngòi này chạy một lần cho mỗi lần đổi kênh.
  //   (b) MỘT JOB CỦA KÊNH ĐANG CHỌN chuyển sang `done` ⇒ đọc lại. Đây là vế đóng lỗi
  //       "job xong mà danh sách không đổi".
  //
  // ⚠️ VẾ (b) SO VỚI BẢN ĐỒ JOB TRƯỚC ĐÓ, KHÔNG PHẢI "job nào đó đang `done`": gọi lại mỗi
  // nhịp SSE là BÃO REQUEST (mỗi sự kiện tiến độ ⇒ một `GET /api/transcripts`), và bài test
  // `khong bao request` đếm số request ở PHÍA SERVER để ghim đúng vế đó.
  // ⚠️ Và lần đổi kênh chỉ GHI LẠI MỐC, không tự kích: lần đọc lại của (a) xảy ra qua `deps`
  // `[ui.channelId]` của `banGhiTomTat`/`chonTranscript`. Gọi `reload()` ở đây nữa là HAI
  // request cho MỘT lần bấm kênh.
  // ---------------------------------------------------------------------------
  const jobDoneRef = useRef<Set<number> | null>(null);
  const kenhRef = useRef(ui.channelId);

  useEffect(() => {
    const kenhDoi = kenhRef.current !== ui.channelId;
    kenhRef.current = ui.channelId;

    const doneCuaKenh = new Set<number>();
    if (ui.channelId !== null) {
      for (const job of jobs.values()) {
        if (job.state !== "done") continue;
        // `payload` là `Record<string, unknown>`: đọc bằng KHOÁ CỤ THỂ và so qua một biến
        // `unknown` — cùng cách `ChannelZone.buocCuaKenh` đọc, không hứa gì về kiểu.
        const idTrongPayload: unknown = job.payload["source_id"];
        if (idTrongPayload !== ui.channelId) continue;
        doneCuaKenh.add(job.id);
      }
    }

    const truoc = jobDoneRef.current;
    jobDoneRef.current = doneCuaKenh;
    // Lần chạy ĐẦU chỉ ghi mốc: không có "trước đó" thì không có chuyển trạng thái nào cả.
    if (truoc === null || kenhDoi) return;

    // CHUYỂN TRẠNG THÁI, không phải TRẠNG THÁI: so HAI CHIỀU (job vào `done` = xong; job rời
    // `done` = chạy lại). Một sự kiện tiến độ của job đang chạy không đổi tập này ⇒ không đọc lại.
    let coChuyenTrangThai = false;
    for (const id of doneCuaKenh) {
      if (!truoc.has(id)) {
        coChuyenTrangThai = true;
        break;
      }
    }
    if (!coChuyenTrangThai) {
      for (const id of truoc) {
        if (!doneCuaKenh.has(id)) {
          coChuyenTrangThai = true;
          break;
        }
      }
    }
    if (coChuyenTrangThai) transcripts.reload();
  }, [jobs, ui.channelId]);

  // THỜI LƯỢNG: lấy từ `Source.duration` của kênh đang chọn — KHÔNG tự đo lại (client đo
  // lại là nguồn sự thật thứ hai, và `duration` của phần tử media là `NaN` cho tới khi tải
  // xong metadata).
  const kenhDangChon = sources.data?.find((source) => source.id === ui.channelId) ?? null;

  return (
    <div className="shell">
      <Header
        status={status.data}
        mode={ui.mode}
        onModeChange={(mode) => dispatch({ type: "setMode", mode })}
      />
      {/* §4.8 HẠNG NHẤT (không phải toast): panel là MỘT HÀNG RIÊNG của lưới `.shell`
          (hàng 2, track `auto`), ngay dưới header và TRÊN bàn làm việc — nó không đè lên
          nội dung, và không biến mất sau vài giây. `up` (hoặc chưa đọc được status) ⇒
          component trả `null` ⇒ hàng 2 KHÔNG CÒN CON NÀO nên co lại bằng không, và bàn
          làm việc VẪN ở hàng 3. Điều đó chỉ đúng vì CẢ BỐN con của `.shell` khai
          `grid-row` tường minh trong `app.css`; để auto-placement chia hàng theo thứ tự
          DOM thì hàng `auto` nuốt luôn bàn làm việc và thanh transport rơi vào `1fr`. */}
      <OllamaDown status={status.data} specs={specs} onRetry={status.reload} />
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
            selectedId={ui.channelId}
            onSelect={(id) => dispatch({ type: "selectChannel", id })}
          />
        </aside>
        {/* BÀN LÀM VIỆC: màn hiện theo `ui.mode` (xem khối dưới). Dữ liệu của CẢ BA màn
            đến từ MỘT chuỗi đọc ở trên (`listTranscripts` → `getTranscript` →
            `listTranslations` → `getTranslation`), và màn KHÔNG tự `fetch`: một chỗ gọi
            API cho mỗi màn là hai nguồn sự thật.
            `currentSegment` nối thẳng từ reducer: đó là CÙNG một đoạn mà thanh
            transport đang phát, nên lề amber của §4.1 và đầu đọc của §4.1 không thể
            nói hai chuyện khác nhau. */}
        <main className="shell__work">
          {/* Vùng giữa hiện theo `ui.mode` — BA chế độ của spec UI §3 (`Mode` ở
              `state/reducer.ts`), không phải router.
              Task W1 đóng hai TRẦN cũ: (1) bộ chọn chế độ ở `Header` dispatch `setMode`,
              nên màn Đối chiếu và tab Thuật ngữ nay TỚI ĐƯỢC; (2) vùng KÊNH dispatch
              `selectChannel`, nên `transcript`/`translations` là dữ liệu THẬT của bản ghi
              đang mở chứ không còn luôn `null`/`[]`.
              ⚠️ CÒN LẠI một TRẦN, và nó là sự thật: `CompareScreen` ghim bản B bằng state
              CỤC BỘ của chính nó, vì `reducer` chưa có action BỎ GHIM (`pinnedB` chỉ ghi
              được). Nâng cấp: truyền `pinnedB`/`onPinB` xuống + thêm action bỏ ghim. */}
          {ui.mode === "compare" ? (
            /* ⚠️ `macDinhId` là QUYẾT ĐỊNH CỦA CHÍNH `App` (`banDichXuat` — bản `done` mới
               nhất), truyền xuống thay vì để màn tự đoán lần thứ hai: `Transport` xuất đúng
               bản đó, và vùng Đối chiếu hiện đúng bản đó ⇒ hai vùng KHÔNG THỂ nói khác nhau.
               Trước vòng sửa này, màn lấy `translations[0]` theo VỊ TRÍ MẢNG (route thật trả
               MỚI NHẤT TRƯỚC ⇒ hàng `queued`), nên người dùng đang ĐỌC một bản rỗng trong
               khi ba nút xuất trỏ vào bản `done` khác — đo được `SAME = false`
               (review W1 §B(8)). */
            <CompareScreen
              transcript={transcript.data}
              translations={translations.data ?? []}
              macDinhId={banDichXuat === null ? null : banDichXuat.id}
            />
          ) : ui.mode === "glossary" ? (
            /* §4.4 tab THUẬT NGỮ (Task 9). Màn này KHÔNG nhận prop: nó độc lập với
               kênh đang mở, và nó TỰ gọi `listTerms`/`createTerm`/`patchTerm`/
               `affectedPreview`. Đó là khác biệt có chủ ý với `EditScreen`/
               `CompareScreen` ở trên — hai màn kia đọc bản ghi đang mở. */
            <GlossaryScreen />
          ) : (
            <EditScreen transcript={transcript.data} currentSegment={ui.currentSegment} />
          )}
        </main>
        <aside className="shell__queue">
          <QueueZone jobs={jobs} />
        </aside>
      </div>
      {/* Thanh transport (§4.1): phát, timecode, track có đầu đọc, ba nút xuất — Task 7.
          Task W1 nối BA prop dữ liệu của nó vào bản ghi đang mở: `sourceId` là kênh đang
          chọn, `segments` là đoạn của bản ghi đó, `duration` là `Source.duration` của
          CHÍNH kênh đó (backend đo — client không đo lại), và `translationId` là bản dịch
          `done` MỚI NHẤT. Chưa chọn kênh ⇒ cả ba vẫn `null`/`[]`, và thanh transport nói
          thật là chưa có gì để phát (nút vô hiệu, không `src`, không `href`). */}
      <footer className="shell__transport">
        <Transport
          sourceId={ui.channelId}
          duration={kenhDangChon === null ? null : kenhDangChon.duration}
          segments={transcript.data?.segments ?? []}
          translationId={banDichXuat === null ? null : banDichXuat.id}
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
