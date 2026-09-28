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
import { useEffect, useReducer, useRef, useState } from "react";

import { endpoints } from "../api/endpoints.ts";
import type { JobState } from "../api/types.ts";
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
  // TASK W3 — BẮT ĐẦU DỊCH (cò của workspace 2)
  //
  // ĐO ĐƯỢC TRƯỚC W3: `endpoints.createTranslation` **0 lượt gọi trong sản phẩm** (grep
  // ngoài `endpoints.ts`) ⇒ không có cách nào bắt đầu một bản dịch từ giao diện. Cùng lượt
  // đo: `endpoints.listEngines` **0** và `<EngineSelect/>` **0 người gọi**.
  //
  // ⚠️ **MỘT điểm quyết định "bản dịch đang xem"** (vòng sửa W1 đã lập, `macDinhId`): `App`
  // là nơi DUY NHẤT đọc `/api/translations`, nên nó trả lời câu đó MỘT lần cho CẢ hai vùng
  // (`Transport.translationId` VÀ `CompareScreen.macDinhId`). W3 chỉ mở rộng câu trả lời đó
  // thêm một ưu tiên — bản VỪA TẠO — chứ **KHÔNG** dựng điểm quyết định thứ hai.
  // ---------------------------------------------------------------------------
  const [banMoiTao, datBanMoiTao] = useState<{ id: number; kenh: number } | null>(null);
  const [dangTao, datDangTao] = useState(false);
  /**
   * Trạng thái JOB `translate` của bản VỪA tạo, đọc từ `POST /api/translations`
   * (`TranslationCreated = { translation, job }`).
   *
   * ⚠️ Đây KHÔNG phải thanh tiến trình thứ hai: nó chỉ là TRẠNG THÁI, để cột phải nói ra
   * "đang dịch… · job: chờ gom lô" thay vì để RỖNG. Tiến trình THẬT (%) nằm ở job/SSE và
   * `useJobStream` đã hiện nó ở vùng HÀNG ĐỢI.
   */
  const [trangThaiJobMoi, datTrangThaiJobMoi] = useState<JobState | null>(null);
  /**
   * LỖI CỦA LẦN TẠO GẦN NHẤT — **NGUYÊN VĂN `ApiError.message`** (`"<status>: <detail>"`).
   *
   * ⚠️ Backend TỪ CHỐI TRƯỚC KHI GHI (`routes_translations.create_translation`: 422 engine
   * không có trong registry / không phải `kind == "mt"`; 409 engine chưa sẵn sàng), nên câu
   * tiếng Việt của nó là thứ DUY NHẤT đúng. Thay bằng "có lỗi xảy ra" là bỏ mất đúng thông
   * tin người dùng cần để sửa, và là UI tự đoán thay backend.
   */
  const [loiTao, datLoiTao] = useState<string | null>(null);

  /**
   * Tạo một bản dịch cho bản ghi đang mở — **MỘT** hàm, gọi từ `CompareScreen`.
   *
   * ⚠️ Body là `{ transcript_id, engine }`: **KHÔNG gửi `target_lang`**. Backend đã mặc định
   * `"vi"` (`CreateIn.target_lang: str = "vi"`); gửi cứng `"vi"` ở client là một **nguồn sự
   * thật thứ hai** cho cùng một giá trị (Global Constraints dòng 25).
   *
   * ⚠️ Sau khi tạo: **làm mới** danh sách (`translations.reload`) chứ **KHÔNG** tự chèn hàng
   * vào state — bản sao dữ liệu máy chủ cũng là nguồn sự thật thứ hai. Và bản vừa tạo PHẢI
   * trở thành bản đang xem (ưu tiên `banMoiTao` bên dưới), vì nó `queued` nên nếu không thì
   * người dùng bấm "dịch" và **không thấy gì xảy ra**.
   */
  async function taoBanDich(engine: string): Promise<void> {
    if (tid === null || ui.channelId === null) return;
    datDangTao(true);
    datLoiTao(null);
    try {
      const tao = await endpoints.createTranslation({ transcript_id: tid, engine });
      // ⚠️ Ghi KÈM kênh: ưu tiên này chỉ có nghĩa cho kênh đã tạo ra nó (xem `banDangXemId`).
      datBanMoiTao({ id: tao.translation.id, kenh: ui.channelId });
      // Trạng thái JOB của bản vừa tạo — cũng từ HTTP, không phải màn tự đoán.
      datTrangThaiJobMoi(tao.job.state);
      // Làm mới danh sách: hàng mới do MÁY CHỦ trả về ở lần đọc sau, không phải hàng ta tự chèn.
      translations.reload();
    } catch (loi: unknown) {
      // `useApi.messageOf` cũng đọc `Error.message`; ở đây đọc thẳng vì lời gọi này không đi
      // qua `useApi`. `ApiError.message` = `"<status>: <detail>"`.
      datLoiTao(loi instanceof Error ? loi.message : String(loi));
    } finally {
      datDangTao(false);
    }
  }

  // ---------------------------------------------------------------------------
  // NGÒI NỔ ĐỌC LẠI `/api/translations` — BẢO HIỂM THỨ TỰ (W3)
  //
  // `taoBanDich` ĐÃ gọi `translations.reload()`; ngòi này KHÔNG thay nó mà bù cho một khe
  // THẬT: `reload` chỉ tăng một con số, và nếu lần đọc lại đó kết thúc TRƯỚC khi React kịp
  // render với `banMoiTao` mới thì hai cập nhật nằm ở hai nhịp khác nhau. Điều kiện ở đây là
  // một TÍN HIỆU (hàng đã có trong ảnh chụp của máy chủ) — không phải một phép chờ theo đồng
  // hồ (ERRATA #35 mục 1/2), và nó chỉ chạy khi hàng vừa tạo CHƯA có trong danh sách.
  // ---------------------------------------------------------------------------
  const banMoiCoTrongDanhSach =
    banMoiTao !== null
    && (translations.data ?? []).some((row) => row.id === banMoiTao.id);

  useEffect(() => {
    if (translations.loading) return;
    if (banMoiTao === null) return;
    if (banMoiTao.kenh !== ui.channelId) return;
    if (banMoiCoTrongDanhSach) return;
    translations.reload();
    // `translations` là object MỚI mỗi lần render ⇒ đưa nó vào deps là vòng lặp vô hạn. Ba
    // tín hiệu dưới đây mới là thứ quyết định: hàng đã có chưa, đang đọc không, kênh nào.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [banMoiCoTrongDanhSach, translations.loading, banMoiTao, ui.channelId]);

  /**
   * Bản dịch ĐANG XEM — câu trả lời DUY NHẤT của `App`, truyền xuống cả `CompareScreen`
   * (`macDinhId`) lẫn `Transport` (`translationId`).
   *
   * Ưu tiên: bản VỪA TẠO (nếu còn thuộc kênh này và còn trong danh sách) → bản `done` mới
   * nhất. ⚠️ `banMoiTao.kenh !== ui.channelId` KHÔNG phải một quyết định thứ hai: đó là điều
   * kiện để ưu tiên này KHÔNG áp cho một kênh khác — `moiTao` là một id trần, và id trần của
   * kênh cũ trỏ vào hư không ở kênh mới.
   */
  const banDangXemId =
    banMoiTao !== null && banMoiTao.kenh === ui.channelId && banMoiCoTrongDanhSach
      ? banMoiTao.id
      : banDichXuat === null ? null : banDichXuat.id;

  /** Trạng thái JOB của bản vừa tạo (đến từ `POST /api/translations`, không phải màn tự đoán). */
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
            /* ⚠️ `macDinhId` là QUYẾT ĐỊNH CỦA CHÍNH `App`, truyền xuống thay vì để màn tự đoán
               lần thứ hai: `Transport` xuất đúng bản đó, và vùng Đối chiếu hiện đúng bản đó ⇒
               hai vùng KHÔNG THỂ nói khác nhau.
               Trước vòng sửa này, màn lấy `translations[0]` theo VỊ TRÍ MẢNG (route thật trả
               MỚI NHẤT TRƯỚC ⇒ hàng `queued`), nên người dùng đang ĐỌC một bản rỗng trong
               khi ba nút xuất trỏ vào bản `done` khác — đo được `SAME = false`
               (review W1 §B(8)).
               Task W3 mở rộng ĐÚNG một câu trả lời đó thêm một ưu tiên: bản VỪA TẠO đứng
               trước bản `done` mới nhất (`banDangXemId`), để bấm "dịch" xong là THẤY ngay bản
               mới (nó `queued`, nên nếu không ưu tiên thì người dùng không thấy gì xảy ra). */
            <CompareScreen
              transcript={transcript.data}
              translations={translations.data ?? []}
              macDinhId={banDangXemId}
              /* MỌI spec của registry: MÀN lọc `kind === "mt"` rồi đưa `EngineSelect` xuống
                 (backend trả 422 cho engine ASR — `routes_translations.py`), còn vùng §4.8 ở
                 trên vẫn cần CẢ ASR để nói cái gì còn chạy được. */
              specs={specs}
              onTaoBanDich={taoBanDich}
              dangTao={dangTao}
              loiTao={loiTao}
              trangThaiJob={trangThaiJobMoi}
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
