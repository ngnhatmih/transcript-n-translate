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
import type { JobState, Segment, SourceLang, Transcript } from "../api/types.ts";
import { BangPhim } from "../keys/BangPhim.tsx";
import type { KeyAction } from "../keys/shortcuts.ts";
import { useShortcuts } from "../keys/useShortcuts.ts";
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
import type { KetQuaNap, NapThanhCong } from "./IntakeFrame.tsx";
import { QueueZone } from "./QueueZone.tsx";
import { Transport } from "./Transport.tsx";

/**
 * Trạng thái JOB `translate` của bản VỪA tạo, **GÓI KÈM HAI KHOÁ ĐỊNH DANH**.
 *
 * ⚠️ Vì sao không phải một `JobState` trần (vòng sửa `I1`, ERRATA #36 mục 4): một
 * `JobState` không kèm gì là dữ liệu của MỘT bản dịch nhưng hiển thị được như của BẤT KỲ
 * bản dịch nào đang xem. `id` + `kenh` + `tid` là ba khoá trả lời "job này là của ai":
 * `id` (bản dịch) để không dán nhãn job sang bản khác trong cùng bản ghi; `kenh` + `tid` để
 * id trần của kênh/bản ghi cũ không trỏ nhầm ở kênh/bản ghi mới.
 */
interface JobCuaBanMoi {
  id: number;
  kenh: number;
  tid: number;
  state: JobState;
}

/** Lỗi của lần tạo gần nhất, gói kèm kênh — xem `JobCuaBanMoi` ở trên về lý do. */
interface LoiCuaBanMoi {
  kenh: number;
  cau: string;
}

/**
 * Một tập job có ĐỔI so với mốc trước đó không — so HAI CHIỀU (job vào = xong; job rời =
 * chạy lại). Một sự kiện TIẾN ĐỘ của job đang chạy không đổi tập này.
 *
 * KHÔNG có trần ở đây, và đó là lý do dấu `ponytail:` đã BỎ khỏi câu này (Task 13): đây là
 * cùng một phép so mà vòng sửa W1 đã viết cho `/api/transcripts`, nay dùng cho HAI tập
 * (transcript và translate) — hai chỗ gọi, một định nghĩa. Một dấu `ponytail:` không nêu trần
 * là một món nợ không đòi được; chỗ này không nợ gì.
 */
function coChuyen(truoc: Set<number>, sau: Set<number>): boolean {
  for (const id of sau) if (!truoc.has(id)) return true;
  for (const id of truoc) if (!sau.has(id)) return true;
  return false;
}

/**
 * ---------------------------------------------------------------------------
 * BÀN PHÍM (Task 11) — `App` là NƠI NỐI, `src/keys/` là nơi TRA.
 *
 * ĐO ĐƯỢC TRƯỚC TASK 11 (đính chính brief bản 2): bàn phím **ĐÃ TỒN TẠI** ở đây — một listener ở
 * **`window`**, guard hai vế, chỉ nhận `[`/`]` và gọi thẳng `nudgeDoan`. Nó đã được đo bằng **bàn
 * phím THẬT trong Chrome thật** (ERRATA #46 mục 5: gõ `[` trong ô sửa ⇒ server `v1 → v1`; cùng
 * phím đó khi tiêu điểm ở `BODY` ⇒ `v1 → v2`). Việc của task này là **hợp nhất** nó vào
 * `src/keys/useShortcuts.ts` (MỘT listener ở `document`, guard GIỮ NGUYÊN hai vế) và **trả nợ ánh
 * xạ**: `[`/`]` = đặt mốc TẠI ĐẦU ĐỌC, nudge = `Shift+←/→` (±0,1s) và `Alt+←/→` (±1s) — ERRATA
 * #44 mục 3.
 *
 * ⚠️ (Chỗ này từng có `dangGoTrongONhap` — nó đã CHUYỂN vào `src/keys/useShortcuts.ts`, không bị
 * bỏ: ba bài ghim `D1 GÕ TRONG Ô SỬA` / `D1 TIÊU ĐIỂM TRONG Ô NHẬP` canh đúng hành vi đó.)
 *
 * ⚠️ `xuLyPhim` là MỘT HÀM MỚI ở mỗi lượt render, và đó là điều `useShortcuts` dựa vào: effect của
 * nó chạy lại mỗi lượt render ⇒ listener cũ vẫn gắn trong đúng cửa sổ một-lượt-commit mà bài
 * `D1 NỀN MỚI HƠN (CỬA SỔ CHƯA GẮN LẠI)` đo. NỀN của lệnh ghi vì thế vẫn phải đọc từ
 * `banGhiMoiNhat.current` (ảnh chụp mới nhất), không phải từ closure.
 * ---------------------------------------------------------------------------
 */
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
  // REGISTRY: MỘT lượt `GET /api/registry` cho CẢ app — đọc qua `endpoints.listEngines`
  // (chính hàm đó LÀM PHẲNG `{asr, mt}` thành một mảng, việc mà `App` từng tự làm), nên đây
  // cũng là NGƯỜI GỌI ĐẦU TIÊN của nó: trước W3, `listEngines` có **0** lượt gọi trong sản
  // phẩm (`grep listEngines` chỉ ra `endpoints.ts`).
  // Đây là NGUỒN DUY NHẤT của `capabilities.available` — client KHÔNG suy lại từ
  // `runtime`/`model_ref` (Global Constraints dòng 25), và KHÔNG đọc lại `kind` để đoán.
  const engines = useApi(() => endpoints.listEngines(), []);
  const specs = engines.data ?? [];

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
   * ⚠️ **GÓI KÈM HAI KHOÁ ĐỊNH DANH, KHÔNG PHẢI MỘT `JobState` TRẦN** — đây là vòng sửa
   * `I1` của review W3 (ERRATA #36 mục 4). ĐO ĐƯỢC trước vòng sửa: `trangThaiJobMoi` là
   * một `JobState` không kèm gì, nên nó được nối vào cột phải của **BẤT KỲ** bản dịch nào
   * đang được chọn; chọn bản `11` (`done`, KHÔNG có job) ⇒ cột phải hiện
   * `"chưa có đoạn này · job: chờ gom lô"` — **job của bản 13**.
   *
   * `kenh` + `tid` là hai khoá của một bản ghi/bản dịch: `id` một mình KHÔNG đủ, vì id hai
   * kênh khác nhau có thể trùng và id trần của kênh cũ trỏ vào hư không ở kênh mới (cùng
   * lý do đã ghi cho `banMoiTao`). `tid` chặn nốt nhánh "cùng kênh nhưng ĐỔI BẢN GHI".
   *
   * ⚠️ Đây KHÔNG phải thanh tiến trình thứ hai: nó chỉ là TRẠNG THÁI, để cột phải nói ra
   * "đang dịch… · job: chờ gom lô" thay vì để RỖNG. Tiến trình THẬT (%) nằm ở job/SSE và
   * `useJobStream` đã hiện nó ở vùng HÀNG ĐỢI.
   */
  const [trangThaiJobMoi, datTrangThaiJobMoi] = useState<JobCuaBanMoi | null>(null);
  /**
   * LỖI CỦA LẦN TẠO GẦN NHẤT — **NGUYÊN VĂN `ApiError.message`** (`"<status>: <detail>"`).
   *
   * ⚠️ **GÓI KÈM KÊNH** (vòng sửa `I1`, ERRATA #36 mục 4): `loiTao` cũ là một `string` trần,
   * nên câu **409 của kênh CŨ** vẫn nằm trong `.cmp__tin` sau khi đổi kênh. Nay nó chỉ được
   * truyền xuống khi `kenh === ui.channelId`, VÀ `useEffect` dưới đây dọn nó khi kênh đổi.
   *
   * ⚠️ Backend TỪ CHỐI TRƯỚC KHI GHI (`routes_translations.create_translation`: 422 engine
   * không có trong registry / không phải `kind == "mt"`; 409 engine chưa sẵn sàng), nên câu
   * tiếng Việt của nó là thứ DUY NHẤT đúng. Thay bằng "có lỗi xảy ra" là bỏ mất đúng thông
   * tin người dùng cần để sửa, và là UI tự đoán thay backend.
   */
  const [loiTao, datLoiTao] = useState<LoiCuaBanMoi | null>(null);
  /**
   * BẢN DỊCH NGƯỜI DÙNG TỰ BẤM CHỌN — nâng lên `App` để nó là **MỘT** điểm quyết định (bat
   * bien `I2`, ERRATA #36 muc 4).
   *
   * ⚠️ VI SAO KHONG THE GIU NO O `CompareScreen` (do duoc khi mutation `I1-chon-ban-12`):
   * `CompareScreen` co state `chonId` CUC BO, nen khi nguoi dung bam mot ban khac thi VUNG DOI
   * CHIEU doi theo nhung `App.banDangXemId` thi KHONG — no van la ban VUA TAO (`banMoiTao` duoc
   * uu tien, xem duoi). He qua DO DUOC: chon ban 12 (`queued`, KHONG co job) sau khi tao ban 13
   * ⇒ cot phai cua no hien `"đang dịch… · job: chờ gom lô"` (job CUA BAN 13), vi `banDangXemId`
   * van la 13. Va vi `banDangXemId` con la `translationId` cua `Transport`, ba nut XUAT cung tro
   * sai ban.
   *
   * Ghi kem `kenh` + `tid` — cung ly do nhu `banMoiTao`: id tran cua kenh/ban ghi cu tro vao hu
   * khong o kenh/ban ghi moi.
   */
  const [banDaChon, datBanDaChon] = useState<{ id: number; kenh: number; tid: number } | null>(null);

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
      // Trạng thái JOB của bản vừa tạo — cũng từ HTTP, không phải màn tự đoán. Kèm CẢ kênh
      // lẫn bản ghi: một `JobState` trần là thứ đã rò rỉ sang bản dịch khác (`I1`).
      datTrangThaiJobMoi({ id: tao.translation.id, kenh: ui.channelId, tid, state: tao.job.state });
      // Làm mới danh sách: hàng mới do MÁY CHỦ trả về ở lần đọc sau, không phải hàng ta tự chèn.
      translations.reload();
    } catch (loi: unknown) {
      // `useApi.messageOf` cũng đọc `Error.message`; ở đây đọc thẳng vì lời gọi này không đi
      // qua `useApi`. `ApiError.message` = `"<status>: <detail>"`.
      datLoiTao({ kenh: ui.channelId, cau: loi instanceof Error ? loi.message : String(loi) });
    } finally {
      datDangTao(false);
    }
  }

  // ---------------------------------------------------------------------------
  // TASK W2 — NẠP TỆP §4.2: **MỘT** hàm, **HAI** lối vào (đường vào của workspace 1)
  //
  // ĐO ĐƯỢC TRƯỚC W2: `endpoints.uploadSource` **0 lượt gọi trong sản phẩm**, và trong
  // `frontend/src` **không có** `type="file"`, **không có** `onDrop`/`dataTransfer` ⇒ workspace 1
  // (audio → text) KHÔNG CÓ CỬA VÀO: người dùng không có cách nào đưa tệp của họ vào app.
  //
  // ⚠️ VÌ SAO HÀM NẰM Ở ĐÂY, KHÔNG Ở HAI COMPONENT: `App` là nơi DUY NHẤT giữ `sources` (danh
  // sách kênh) và `dispatch`, nên cũng là nơi duy nhất biết phải LÀM MỚI cái gì và CHỌN kênh nào.
  // `IntakeFrame` (khung giữa §4.2) và `NhapGon` (lối gọn ở vùng KÊNH, cho §12.2 *"nạp 3 tệp cùng
  // lúc"*) chỉ HIỂN THỊ; cả hai gọi CHÍNH hàm này. Viết lần thứ hai ở một component là hai nguồn
  // sự thật cho cùng một luật — và có bài ghim cấu trúc: `uploadSource` chỉ được gọi ở ĐÂY.
  // ---------------------------------------------------------------------------
  /**
   * Nạp TỆP **LẦN LƯỢT** rồi làm mới danh sách kênh và chọn kênh của tệp **THÀNH CÔNG ĐẦU TIÊN**.
   *
   * ⚠️ **LẦN LƯỢT, KHÔNG `Promise.all`**: với `Promise.all`, một tệp lỗi làm cả lô thành một lỗi
   * gộp, và kết quả của các tệp KHÁC trở nên mơ hồ — người dùng không biết tệp nào đã vào. §12.2
   * đòi thấy rõ **từng** tệp, nên từng tệp phải có kết quả riêng.
   *
   * ⚠️ **`loi` là `ApiError.message` NGUYÊN VĂN** (`"<status>: <detail>"` — câu tiếng Việt của
   * backend, ví dụ `422 "tệp rỗng"`). Thay bằng "có lỗi xảy ra" là bỏ mất đúng thông tin người
   * dùng cần để sửa. Nhánh `instanceof Error` giữ luôn lỗi mạng.
   *
   * ⚠️ **KHÔNG tự chèn hàng vào state**: hàng kênh mới chỉ đến từ `sources.reload()` (lần đọc
   * `/api/sources` kế tiếp do MÁY CHỦ trả về). Một bản sao dữ liệu máy chủ ở client là **nguồn sự
   * thật thứ hai** (Global Constraints của plan).
   *
   * ⚠️ **MỌI tệp lỗi ⇒ KHÔNG đổi kênh.** Kênh hiện tại là ngữ cảnh người dùng đang làm việc; một
   * lượt nạp thất bại không có quyền dịch chuyển nó. (Và nếu chọn "kênh đầu tiên" trong trường
   * hợp đó thì màn hình nhảy sang một kênh CŨ mà người dùng không hề yêu cầu — đó là hành vi sai
   * đã có mutation `W2-6` ghim.)
   *
   * ⚠️ **BẢN GHI THÌ CHƯA CÓ**: route nạp chỉ xếp job `ingest`, nên ngay sau lượt nạp này kênh mới
   * hiện `nạp: đang chờ` (từ job, qua `ChannelZone`) và vùng giữa vẫn là trạng thái rỗng — giao
   * diện nói ĐÚNG sự thật trạng thái, không hứa một bản ghi đã có.
   */
  async function napTep(files: File[], lang: SourceLang): Promise<KetQuaNap[]> {
    const ketQua: KetQuaNap[] = [];
    for (const tep of files) {
      try {
        const tao = await endpoints.uploadSource(tep, lang);
        // Id kênh mới = `created.source.id` (`SourceCreated = { source, job }`), KHÔNG phải
        // `job.id`: job là hàng của bảng jobs, hai bảng không được đảm bảo trùng id.
        ketQua.push({ ten: tep.name, ok: true, sourceId: tao.source.id });
      } catch (loi: unknown) {
        ketQua.push({
          ten: tep.name,
          ok: false,
          loi: loi instanceof Error ? loi.message : String(loi),
        });
      }
    }
    // LÀM MỚI danh sách kênh — kể cả khi mọi tệp lỗi (lượt lỗi không tạo hàng nào, và một lần
    // đọc lại là giá rẻ nhất để danh sách không lệch khỏi máy chủ).
    sources.reload();
    // TỆP THÀNH CÔNG ĐẦU TIÊN (theo thứ tự người dùng đưa vào), không phải "kết quả đầu tiên":
    // vị từ phải là `ok`, nếu không thì một tệp lỗi sẽ được "chọn" và màn hình đứng yên.
    const dauTien = ketQua.find((kq): kq is NapThanhCong => kq.ok);
    if (dauTien !== undefined) dispatch({ type: "selectChannel", id: dauTien.sourceId });
    return ketQua;
  }

  // ---------------------------------------------------------------------------
  // TASK D1 — ĐƯỜNG GHI ĐẦU TIÊN CỦA WORKSPACE 1: **SỬA DÒNG** + **NUDGE MỐC**
  //
  // ĐO ĐƯỢC TRƯỚC D1: `endpoints.patchTranscript` **0 lượt gọi trong sản phẩm**;
  // `startEdit`/`endEdit` **0 lượt dispatch** (chỉ có trong `reducer.ts` và `reducer.test.ts`);
  // `nudge` **0 handler** (chỉ có trong hai comment của `lib/timecode*`); `EditScreen`
  // **không nhận callback ghi nào**. ⇒ `patchTranscript` chưa có người gọi, `nudge` chưa có đích.
  //
  // ⚠️ **BẪY MẤT DỮ LIỆU (vế quan trọng nhất của task này):** `PATCH /api/transcripts/{id}` nhận
  // `{segments: Segment[]}` và backend **TỪ CHỐI mảng rỗng** (`min_length=1`) ⇒ muốn sửa MỘT dòng
  // thì phải gửi **TOÀN BỘ** mảng. `Segment` còn có `suspect`/`qa`/`events`/`words`/`t`. Một bản
  // dựng lại `Segment` chỉ với `{i,start,end,text}` sẽ **XOÁ ÂM THẦM** các trường đó của MỌI dòng.
  // ⇒ Luật ở đây: **đọc bản ghi HIỆN TẠI, chỉ sửa TRƯỜNG CẦN SỬA trên ĐÚNG MỘT phần tử, giữ
  // nguyên mọi trường khác, rồi gửi CẢ mảng.**
  //
  // ⚠️ Và **nguồn sự thật là MÁY CHỦ**: ghi xong KHÔNG tự sửa state tại chỗ — chỉ `reload()`.
  // ---------------------------------------------------------------------------
  const [dangLuuDoan, datDangLuuDoan] = useState(false);
  /**
   * LỖI GHI — **NGUYÊN VĂN `ApiError.message`** (`"<status>: <detail>"`, câu tiếng Việt của
   * backend, ví dụ `422 "segment không hợp lệ: …"`). Thay bằng "có lỗi xảy ra" là bỏ mất đúng
   * thông tin người dùng cần để sửa (cùng lý do `loiTao` của W3 và `loi` của `napTep`).
   */
  const [loiGhiDoan, datLoiGhiDoan] = useState<string | null>(null);

  /**
   * HÀNG ĐỢI GHI — **MỘT cổng chặn cho MỌI đường ghi** (ERRATA #44 mục 1).
   *
   * ⚠️ VÌ SAO (C1 — mất-cập-nhật âm thầm): bốn lối vào dùng chung một đường ghi — nút `lưu`,
   * `Enter`, hai phím `[`/`]`, hai nút nudge. Nếu chúng chạy SONG SONG thì mỗi lần ghi tính body
   * từ `transcript.data` của **lần render của chính nó**, tức cùng một **bản ghi CŨ**; lần ghi SAU
   * gửi giá trị cũ và **XOÁ ÂM THẦM** kết quả lần trước, `version` vẫn tăng, KHÔNG một lỗi nào.
   * `disabled={dangLuu}` ở nút là bảo vệ **tầng giao diện** — nó không bảo vệ bàn phím, và không
   * bảo vệ hai lối ghi khác nhau vào cùng một tài nguyên.
   *
   * ⇒ Mọi việc ghi đi qua `xepHangGhi` (một chuỗi promise giữ trong `useRef`), nên hai lần ghi
   * CHỒNG LẤN được thi hành **tuần tự**, và bài `D1 CHỒNG LẤN` ghim đúng điều đó.
   */
  const hangDoiGhi = useRef<Promise<void>>(Promise.resolve());

  /**
   * BẢN GHI mà **chính đường ghi này** vừa gửi lên máy chủ (kèm `version` máy chủ trả về).
   *
   * ⚠️ VÌ SAO CẦN — và vì sao "xếp hàng rồi đọc lại `transcript.data`" là **KHÔNG ĐỦ**: `reload()`
   * của `useApi` chỉ tăng một bộ đếm; lượt `GET` thật chạy trong **effect của lần render sau**,
   * nên tới lượt lần ghi thứ hai thì `transcript.data` **VẪN LÀ BẢN CŨ** (hàng đợi một mình vẫn
   * mất-cập-nhật). Đây là NỀN của lần ghi kế tiếp, dùng khi nó MỚI HƠN (`version` lớn hơn) dữ liệu
   * đang có; khi máy chủ đã trả về bản mới hơn thì **dữ liệu máy chủ thắng** — nguồn sự thật vẫn
   * là máy chủ, đúng như luật "không tự sửa state tại chỗ" ở dưới.
   */
  const banGhiVuaGhi = useRef<{ id: number; version: number; segments: Segment[] } | null>(null);

  /**
   * ẢNH CHỤP **MỚI NHẤT** của bản ghi đang mở — cập nhật ở MỖI lần render.
   *
   * 🔴 VÌ SAO CẦN (`I-1` của re-review vòng sửa 1 — ĐO ĐƯỢC, KHÔNG phải flake): listener `keydown`
   * sống trong một effect, nên giữa lượt React commit DOM của bản ghi MỚI và lượt effect chạy lại,
   * listener CŨ vẫn còn gắn. `nudgeDoan` của closure cũ đọc `transcript.data` của CHÍNH lần render
   * ấy ⇒ lần ghi tính từ bản CŨ và **XOÁ ÂM THẦM** thay đổi của người khác (họ C1: `version` vẫn
   * tăng, không một lỗi nào). `banGhiVuaGhi` KHÔNG cứu được ca này: nó chỉ biết bản do CHÍNH đường
   * ghi này vừa gửi, còn bản mới ở đây đến từ một lượt ĐỌC LẠI. Trước vòng sửa, ca này bị khai là
   * "flake 1/33"; nó **falsify được** bằng mutant `D1-DEPS-NUDGE-STALE` (bỏ `transcript.data` khỏi
   * deps của listener) — ERRATA #45 mục 1 áp cho cả một phép đo, không chỉ cho mệnh đề.
   *
   * ⚠️ Chỉ **NỀN** của lệnh ghi được đọc mới nhất. **ĐÍCH** của lệnh (id bản ghi) vẫn chốt LÚC GỬI
   * — bất biến của F7 (`D2 DUYET: đích của lệnh chốt LÚC GỬI`), và bản vá này không được phá nó.
   *
   * ⚠️ Phép gán nằm trong THÂN component, KHÔNG trong effect: nó phải xảy ra ngay ở lượt render
   * đã có dữ liệu mới, TRƯỚC lượt flush passive effect — đúng cái cửa sổ đang hở.
   */
  const banGhiMoiNhat = useRef<Transcript | null>(transcript.data);
  banGhiMoiNhat.current = transcript.data;

  /**
   * ĐẦU ĐỌC (giây) — nhịp `timeupdate` GẦN NHẤT của phần tử media, do `Transport` BÁO LÊN
   * (`TransportProps.onDauDoc`).
   *
   * ⚠️ VÌ SAO `useRef` chứ không `useState`: `timeupdate` bắn ~4 lần/giây; đưa nó vào state là một
   * lượt render cho mỗi nhịp, và reducer thì **không có trường giây nào** (`UiState` bảy trường
   * phẳng) — đúng lý do `Transport.viTriPhat` là state CỤC BỘ ở đó.
   *
   * ⚠️ VÌ SAO `App` GIỮ NÓ: `[`/`]` = *"đặt mốc start/end TẠI ĐẦU ĐỌC"* (spec §5.1 dòng 296), và
   * phần tử media nằm trong `Transport`.
   *
   * ⚠️ **ĐỌC LÚC BẤM, KHÔNG ĐỌC TRONG HÀNG ĐỢI**: giá trị được chốt ngay ở `xuLyPhim` rồi mới
   * `xepHangGhi`. Đọc nó bên trong việc đã xếp hàng là lấy vị trí đầu đọc SAU khi người dùng bấm
   * (đo được ở bài `T11 MỐC TẠI ĐẦU ĐỌC`, vế (3): PATCH đầu đang bay 250 ms, đầu đọc chạy tiếp ⇒
   * mốc vẫn phải là vị trí lúc bấm).
   */
  const dauDocRef = useRef(0);

  /**
   * YÊU CẦU **NGHE LẠI** quanh mốc vừa nudge (spec UI §5.2 dòng 309) — `Transport` là nơi thi hành
   * (nó giữ phần tử media).
   *
   * ⚠️ VÌ SAO CÓ `lan` (số thứ tự) chứ không chỉ `giay`: hai lần nudge LIÊN TIẾP về cùng một mốc
   * (ví dụ `Shift+→` rồi `Alt+←`... hoặc gõ lại cùng phím khi mốc đã ở biên) là HAI yêu cầu KHÁC
   * NHAU, và một `useEffect` phụ thuộc `[giay]` sẽ bỏ qua yêu cầu thứ hai vì giá trị không đổi.
   * `lan` làm mỗi yêu cầu một ĐỐI TƯỢNG MỚI ⇒ hiệu ứng chạy lại, không cần so sánh nội dung.
   *
   * ⚠️ VÌ SAO `useState` (một lượt render) mà không phải `useRef`: đây là ĐẦU VÀO của một hiệu ứng
   * trong component KHÁC; `ref` là dữ liệu không kích hoạt render, nên `Transport` sẽ không bao giờ
   * thấy nó.
   */
  const [ngheLai, datNgheLai] = useState<{ giay: number; lan: number } | null>(null);
  /** Số thứ tự yêu cầu nghe lại — xem `datNgheLai` phía trên. */
  const demNgheLai = useRef(0);

  /**
   * BẢNG PHÍM TẮT §11.4 đang MỞ hay không. Mặc định ĐÓNG (nó che màn hình).
   *
   * ⚠️ Khi mở, `xuLyPhim` CHẶN mọi phím khác trừ chính nó và `Esc`: một lớp phủ `aria-modal` đang
   * che màn hình mà phím `[` vẫn ghi vào bản ghi phía sau là một thao tác người dùng KHÔNG NHÌN
   * THẤY.
   */
  const [moBangPhim, datMoBangPhim] = useState(false);

  /**
   * MỘT chỗ GHI duy nhất cho cả hai thao tác của D1 (`luu` và `nudge`).
   *
   * `sua` là hàm THUẦN áp lên ĐÚNG đoạn cần sửa; mọi đoạn khác đi lên NGUYÊN VẸN.
   * Trả về **ĐOẠN ĐÃ GỬI** (`Segment`) khi máy chủ đã nhận, `null` khi không có gì để ghi hoặc khi
   * ghi lỗi.
   *
   * ⚠️ VÌ SAO TRẢ `Segment` CHỨ KHÔNG PHẢI `boolean` (vòng sửa 1, `I-3`): "nghe lại 300 ms" của
   * §5.2 cần **ĐÚNG giá trị đã ghi** để tua đầu đọc tới. Tính lại mốc ở ngoài là **định nghĩa thứ
   * hai** của cùng một phép cộng — và nó sẽ lệch đúng ở ca `banGhiMoiNhat`/`banGhiVuaGhi` mới hơn
   * (nền của lệnh ghi không phải ảnh chụp của lượt render). Đoạn trả về là đoạn SUY RA TỪ CHÍNH
   * `nen` mà lệnh ghi đã dùng, nên hai con số không thể lệch.
   *
   * ⚠️ `hienTai.segments.length === 0` / không tìm thấy đoạn ⇒ **KHÔNG gửi gì**: backend từ chối
   * mảng rỗng (`min_length=1`), và một PATCH rỗng là một lỗi 422 vô nghĩa với người dùng.
   *
   * ⚠️ **NỀN đọc từ `banGhiMoiNhat.current`** (ảnh chụp mới nhất), KHÔNG từ closure của lần render
   * đã gọi hàm này: xem docblock của `banGhiMoiNhat` — đó là vế chặn ghi-đè-âm-thầm khi listener
   * chưa được gắn lại. `banGhiId` (ĐÍCH) vẫn là tham số, tức vẫn chốt LÚC GỬI.
   */
  async function ghiDoan(
    banGhiId: number,
    i: number,
    sua: (seg: Segment) => Segment,
  ): Promise<Segment | null> {
    const hienTai = transcript.data;
    if (hienTai === null || hienTai.id !== banGhiId) return null;
    // NỀN = ảnh chụp MỚI NHẤT cùng id. `hienTai` chỉ là đường lùi khi ảnh chụp mới nhất thuộc một
    // BẢN GHI KHÁC (người dùng vừa đổi kênh/bản ghi) — lấy chữ của bản ghi khác làm nền là một
    // cách ghi-đè khác, không phải một cách chữa.
    const moiNhat = banGhiMoiNhat.current;
    const nenMayChu = moiNhat !== null && moiNhat.id === banGhiId ? moiNhat : hienTai;
    const vuaGhi = banGhiVuaGhi.current;
    const nen =
      vuaGhi !== null && vuaGhi.id === banGhiId && vuaGhi.version > nenMayChu.version
        ? vuaGhi.segments
        : nenMayChu.segments;
    const doanHienTai = nen.find((seg) => seg.i === i);
    if (doanHienTai === undefined) return null;
    const doanMoi = sua(doanHienTai);
    const segments = nen.map((seg) => (seg.i === i ? doanMoi : seg));
    datDangLuuDoan(true);
    datLoiGhiDoan(null);
    let traVe: Transcript;
    try {
      traVe = await endpoints.patchTranscript(banGhiId, { segments });
    } catch (loi: unknown) {
      datLoiGhiDoan(loi instanceof Error ? loi.message : String(loi));
      return null;
    } finally {
      datDangLuuDoan(false);
    }
    // Nhớ ĐÚNG bản ghi máy chủ vừa trả về (`version` đã tăng) ⇒ lần ghi kế tiếp trong hàng đợi
    // tính từ bản MỚI, không tính từ bản cũ trong closure.
    banGhiVuaGhi.current = { id: banGhiId, version: traVe.version, segments: traVe.segments };
    // ĐỌC LẠI cả hai đường: bản ghi (chữ/mốc đã lưu) VÀ danh sách bản dịch — vì `stale` do MÁY
    // CHỦ tính lại sau khi `version` tăng, nên câu "đã lỗi thời" chỉ đúng nếu danh sách được đọc
    // lại. Không tự sửa state tại chỗ: bản sao dữ liệu máy chủ ở client là nguồn sự thật thứ hai.
    transcript.reload();
    translations.reload();
    return doanMoi;
  }

  /**
   * **CỔNG DUY NHẤT** của mọi việc ghi: xếp `viec` vào SAU việc đang chạy (hàng đợi), và biến mọi
   * lỗi (kể cả lỗi lập trình) thành câu báo trạng thái thay vì một `unhandledRejection`.
   *
   * ⚠️ Nhận một HÀM (`() => Promise`), KHÔNG nhận một promise đã khởi động: một promise được tạo
   * ngay tại chỗ gọi nghĩa là việc ghi **ĐÃ BẮT ĐẦU** — nó không thể xếp hàng, và đó chính là C1.
   * `.catch` nằm TRONG mỗi mắt xích nên một lần ghi lỗi không làm đứt hàng đợi.
   */
  function xepHangGhi(viec: () => Promise<void>): void {
    hangDoiGhi.current = hangDoiGhi.current.then(viec).catch((loi: unknown) => {
      datLoiGhiDoan(loi instanceof Error ? loi.message : String(loi));
    });
  }

  // ---------------------------------------------------------------------------
  // TASK D2 — BA LỆNH GHI MỚI: DUYỆT BẢN GHI · HUỶ JOB · CHẠY LẠI JOB
  //
  // ĐO ĐƯỢC TRƯỚC D2 (grep ngoài `endpoints.ts`): `approveTranscript` **0 lượt gọi trong sản
  // phẩm**, `cancelJob` **0**, `retryJob` **0** ⇒ không có cách nào duyệt một bản ghi, và không có
  // cách nào tác động lên một job đang chạy/đang chờ.
  //
  // ⚠️ CẢ BA đi qua **CÙNG MỘT hàng đợi ghi** của D1 (`xepHangGhi`) — ERRATA #44 mục 1: hai lần
  // ghi CHỒNG LẤN là lớp lỗi KHÔNG CÓ TRIỆU CHỨNG (không exception, không 4xx, `version` vẫn
  // tăng), và D2 thêm BA thao tác vào đúng lớp rủi ro đó — ca đắt nhất là "duyệt trong lúc một
  // lượt ghi khác đang bay". Hàng đợi thi hành chúng TUẦN TỰ, nên lệnh sau không tính từ một bản
  // ghi đã cũ.
  // ---------------------------------------------------------------------------
  /**
   * BẢN GHI (id + kênh) đang có **MỘT lời gọi `duyệt` BAY**, hoặc `null`.
   *
   * ⚠️ VÌ SAO `{id, kenh}` chứ không một `boolean` (đo được, `I3b` của review D2): một cờ GLOBAL
   * không được dọn khi đổi kênh ⇒ thanh trên của kênh MỚI nói *"đang duyệt…"* trong khi chưa ai
   * duyệt bản ghi đó; và `finally` của lệnh CŨ sẽ xoá cờ của lệnh MỚI đang bay (mở toang guard
   * chống trùng lặp của nó). Đây là cùng một câu hỏi với `banDaChon`/`loiTao`: trạng thái của một
   * lệnh phải mang THEO đối tượng mà nó thuộc về.
   *
   * ⚠️ Đối chiếu `loiDuyet`/`loiLenh`: `loiDuyet` đã được dọn trong effect đổi kênh; `loiLenh` khoá
   * theo id JOB (hàng đợi là của cả app, không thuộc kênh nào) nên nó đúng như đang có.
   */
  const [dangDuyet, datDangDuyet] = useState<{ id: number; kenh: number | null } | null>(null);
  /**
   * LỖI DUYỆT — **NGUYÊN VĂN `ApiError.message`** (`"<status>: <detail>"`), cùng lý do `loiTao`
   * và `loiGhiDoan`: câu tiếng Việt của backend là thứ DUY NHẤT đúng.
   */
  const [loiDuyet, datLoiDuyet] = useState<string | null>(null);
  /**
   * Job nào đang có **MỘT lệnh bay** (`Set` id) — **GUARD CHỐNG TRÙNG LẶP**, và nó là cổng DUY
   * NHẤT: không có `disabled` song song ở nút, vì hai cơ chế cho một câu hỏi là hai nguồn sự thật
   * (và cái thứ hai sẽ là một mệnh đề không có gì làm nó sai được — ERRATA #45 mục 1).
   */
  const [dangLenh, datDangLenh] = useState<ReadonlySet<number>>(() => new Set<number>());
  /**
   * Job nào đã được **GỬI YÊU CẦU HUỶ**, kèm **TRẠNG THÁI LÚC GỬI**.
   *
   * ⚠️ Đây KHÔNG phải một nguồn trạng thái job thứ hai: nó không nói job đang ở đâu, nó nói
   * **giao diện đã yêu cầu gì**. Nó chỉ được RENDER khi `job.state` VẪN LÀ trạng thái lúc gửi —
   * máy chủ xác nhận (sự kiện SSE) thì câu đó **BIẾN MẤT** và nhường chỗ cho sự thật mới của job.
   * Lời hứa đó chỉ sống trong ĐÚNG lượt chạy đã xin huỷ: effect NGAY DƯỚI đây DỌN mục nào có
   * `job.state` khác trạng thái lúc gửi. `jobs` vẫn là bản đồ của `useJobStream` và **không có
   * dòng nào ở đây sửa nó tại chỗ**.
   */
  const [daYeuCauHuy, datDaYeuCauHuy] = useState<ReadonlyMap<number, JobState>>(() => new Map());
  /**
   * DỌN `daYeuCauHuy` — lời hứa "đã yêu cầu huỷ" KHÔNG được sống lại trên một lượt chạy mới.
   *
   * 🔴 VÌ SAO PHẢI CÓ (đo được, `I3` của review D2): chỗ GHI duy nhất là `huyJob`, và phép render so
   * `get(id) === job.state`. Trình tự `running + huỷ` ⇒ worker **NÉM LỖI** ⇒ `FAILED` (nhánh
   * `except` của `worker._run_one` bỏ qua cờ huỷ; phép kiểm cờ chỉ tới được ở đường THÀNH CÔNG) ⇒
   * bấm `chạy lại` ⇒ `running` làm câu đó **HIỆN LẠI** trên một lượt chạy mới tinh — một phát ngôn
   * SAI, đúng lớp lỗi mà cả task này tồn tại để chặn.
   *
   * ⚠️ VÌ SAO KHÔNG KHOÁ THEO `{state, attempts}` (brief gợi ý — ĐO ĐƯỢC LÀ KHÔNG ĐỦ): `attempts`
   * KHÔNG nằm trong sự kiện SSE (`Job.to_event()` chỉ có `id`/`state`/`progress`/`phase`/`error`/
   * `log_tail`), `applyJobEvent` cố ý KHÔNG đụng tới nó (*"`attempts` … chỉ đến từ ảnh chụp"*), và
   * `chayLaiJob` không đọc lại ảnh chụp ⇒ sau `retry_job` (backend TĂNG `attempts`) CLIENT vẫn giữ
   * `attempts` CŨ, nên khoá cũ khớp lại y như trước. Mệnh đề đúng không phải "cùng trạng thái và
   * cùng số lần chạy" mà là "**CHƯA TỪNG RỜI khỏi trạng thái lúc gửi**": quan sát thấy job ở trạng
   * thái KHÁC (hoặc job biến mất khỏi bản đồ) là lời hứa hết hiệu lực — không phụ thuộc việc client
   * có kịp thấy `attempts` mới hay không.
   *
   * Trả về CHÍNH `cu` khi không có gì để dọn ⇒ React bỏ qua lượt render đó (không vòng lặp).
   *
   * ⚠️ **`daYeuCauHuy` CŨNG nằm trong deps** (`I-2` của re-review vòng sửa 1 — đo được): phép dọn
   * chỉ theo `[jobs]` là **edge-triggered theo `jobs`**, nên một mục được GHI *sau khi* job đã rời
   * trạng thái lúc gửi thì **không lượt dọn nào chạy nữa** — mục nằm lại vĩnh viễn, và khi job quay
   * lại ĐÚNG trạng thái đó (một lượt chạy mới) thì câu "đã yêu cầu huỷ" của lượt CŨ **hiện lại**.
   * Đưa `daYeuCauHuy` vào deps làm phép dọn chạy cả khi **bản thân bảng mục** đổi. Hội tụ: lượt
   * chạy lại của effect thấy mọi mục còn lại đều hợp lệ (đó là điều kiện để chúng sống sót) nên nó
   * trả CHÍNH `cu` và React bỏ qua lượt render ⇒ không vòng lặp.
   */
  useEffect(() => {
    datDaYeuCauHuy((cu) => {
      const conHieuLuc = new Map<number, JobState>();
      for (const [id, trangThai] of cu) {
        if (jobs.get(id)?.state === trangThai) conHieuLuc.set(id, trangThai);
      }
      return conHieuLuc.size === cu.size ? cu : conHieuLuc;
    });
  }, [jobs, daYeuCauHuy]);
  /** Câu lỗi **NGUYÊN VĂN** của lệnh gần nhất, theo TỪNG job (khoá = id job). */
  const [loiLenh, datLoiLenh] = useState<ReadonlyMap<number, string>>(() => new Map());

  /**
   * DUYỆT bản ghi đang mở — nút ở thanh trên của màn Biên tập (`EditScreen.onDuyet`).
   *
   * ⚠️ **DUYỆT KHÔNG TĂNG `version`** (khác `patchTranscript`): `endpoints.approveTranscript` khai
   * điều đó, và backend chỉ đổi `status` (`routes_transcripts.approve` — "Cố ý KHÔNG đụng tới
   * segments/version"). Nếu nó tăng thì mọi bản dịch của bản ghi thành `stale` vì một thao tác
   * KHÔNG sửa nội dung.
   *
   * ⚠️ Xong thì **ĐỌC LẠI** bản ghi (`transcript.reload()`) — `status` là dữ liệu của MÁY CHỦ,
   * không tự sửa state tại chỗ. ⚠️ Chỉ đọc lại CHI TIẾT, không đọc lại danh sách: `status` không
   * được dùng ở đâu khác, và một lượt `GET` thừa là một đường không ai ghim.
   *
   * ⚠️ **ĐƯỜNG LỖI DUY NHẤT của route này là 404** (`_require_transcript` ⇒ `HTTPException(404,
   * str(exc))`, với `exc` từ cổng: `transcript {id} không tồn tại`); route `approve` KHÔNG có nhánh
   * 422 nào (`grep 'không duyệt được' backend/` = 0). Fixture của `App.test.tsx` vì thế phát ĐÚNG
   * 404 + ĐÚNG câu đó — một fixture phát 422 với câu tự nghĩ là một đường KHÔNG TỒN TẠI (`I2`).
   */
  function duyetBanGhi(): void {
    const hienTai = transcript.data;
    if (hienTai === null) return;
    const kenhLucGui = ui.channelId;
    // GUARD chống trùng lặp — theo ĐÚNG BẢN GHI: hai lần bấm trên CÙNG một bản ghi không chờ nhau
    // ⇒ vẫn MỘT request (bài `D2 DUYET CHỐNG TRÙNG LẶP`), nhưng cờ "đang bay" của bản ghi này
    // KHÔNG được chặn một bản ghi KHÁC vừa được mở sau khi đổi kênh.
    if (dangDuyet !== null && dangDuyet.id === hienTai.id && dangDuyet.kenh === kenhLucGui) return;
    datDangDuyet({ id: hienTai.id, kenh: kenhLucGui });
    datLoiDuyet(null);
    xepHangGhi(async () => {
      try {
        // 🔴 ĐÍCH CHỐT **LÚC GỬI**: `hienTai` là bản ghi của CHÍNH lần render đã nhận cú bấm, không
        // phải thứ đang mở lúc hàng đợi thi hành. Đổi kênh (hoặc chọn bản ghi khác) trong lúc lệnh
        // còn XẾP HÀNG vì một PATCH chậm ⇒ lệnh vẫn phải tác động bản ghi ĐÃ BẤM (ERRATA #44 mục 1,
        // cùng họ với `huyJob` chốt `trangThaiLucGui` trước khi vào hàng đợi).
        await endpoints.approveTranscript(hienTai.id);
        transcript.reload();
      } catch (loi: unknown) {
        datLoiDuyet(loi instanceof Error ? loi.message : String(loi));
      } finally {
        // Chỉ XOÁ cờ của CHÍNH mình: một lệnh MỚI (bản ghi khác) đang bay không được mở khoá bởi
        // `finally` của lệnh CŨ — nếu không thì câu "đang duyệt…" của bản ghi mới biến mất sớm và
        // guard chống trùng lặp của nó mở toang.
        datDangDuyet((cu) =>
          cu !== null && cu.id === hienTai.id && cu.kenh === kenhLucGui ? null : cu,
        );
      }
    });
  }

  /**
   * HUỶ một job — nút trên **mỗi hàng `queued`/`running`** của vùng HÀNG ĐỢI.
   *
   * 🔴 CÂU CHỮ LÀ MỆNH ĐỀ TRUNG THỰC CỦA CẢ TASK NÀY (hợp đồng §2): job `queued` bị huỷ **NGAY**,
   * còn job `running` **CHỈ ĐƯỢC ĐẶT CỜ** (`cancel_requested`) — trạng thái VẪN LÀ `running` cho
   * tới khi có một sự kiện SSE khác. Nên giao diện chỉ được nói *"đã YÊU CẦU huỷ"*; **KHÔNG** được
   * nói *"đã dừng"*. Chính vì vậy lời hứa đó không nằm ở đây mà ở `QueueZone` (nơi render), và nó
   * gắn với `job.state` hiện tại: SSE đổi trạng thái thì câu ấy biến mất.
   */
  function huyJob(id: number): void {
    const job = jobs.get(id);
    // THUẦN KIỂU, không phải một guard hành vi: không có job thì cũng không có nút nào để bấm.
    if (job === undefined) return;
    if (dangLenh.has(id)) return; // GUARD chống trùng lặp
    const trangThaiLucGui = job.state;
    datDangLenh((cu) => new Set(cu).add(id));
    datLoiLenh((cu) => {
      const moi = new Map(cu);
      moi.delete(id);
      return moi;
    });
    xepHangGhi(async () => {
      try {
        await endpoints.cancelJob(id);
        datDaYeuCauHuy((cu) => new Map(cu).set(id, trangThaiLucGui));
      } catch (loi: unknown) {
        datLoiLenh((cu) => new Map(cu).set(id, loi instanceof Error ? loi.message : String(loi)));
      } finally {
        datDangLenh((cu) => {
          const moi = new Set(cu);
          moi.delete(id);
          return moi;
        });
      }
    });
  }

  /**
   * CHẠY LẠI một job `failed`/`interrupted` — nút **CHỈ hiện ở hai trạng thái đó** (`QueueZone`).
   *
   * ⚠️ Vẫn phải xử lý **409**: trạng thái phía client có thể CŨ (job đã được chạy lại ở một tab
   * khác), và khi đó câu của backend phải hiện **NGUYÊN VĂN**.
   *
   * `ponytail:` TRẦN — chạy lại THÀNH CÔNG thì giao diện **không nói gì**: trạng thái job chỉ đến
   * từ `useJobStream`, và một câu "đã yêu cầu chạy lại" sẽ là một mệnh đề nữa cần ghim. Nâng cấp:
   * nói ra bằng cùng khuôn "yêu cầu" như `huyJob` (và ghim nó).
   */
  function chayLaiJob(id: number): void {
    if (dangLenh.has(id)) return; // GUARD chống trùng lặp
    datDangLenh((cu) => new Set(cu).add(id));
    datLoiLenh((cu) => {
      const moi = new Map(cu);
      moi.delete(id);
      return moi;
    });
    xepHangGhi(async () => {
      try {
        await endpoints.retryJob(id);
      } catch (loi: unknown) {
        datLoiLenh((cu) => new Map(cu).set(id, loi instanceof Error ? loi.message : String(loi)));
      } finally {
        datDangLenh((cu) => {
          const moi = new Set(cu);
          moi.delete(id);
          return moi;
        });
      }
    });
  }

  /**
   * `Enter`/nút `lưu` ⇒ GHI chữ mới. Xong thì `endEdit` (đóng ô sửa) — nhưng **chỉ khi ghi được**:
   * một lượt ghi LỖI phải để người dùng Ở LẠI trong ô sửa với nguyên bản nháp của họ.
   */
  async function luuDoan(i: number, text: string): Promise<void> {
    const hienTai = transcript.data;
    if (hienTai === null) return;
    const daGui = await ghiDoan(hienTai.id, i, (seg) => ({ ...seg, text }));
    if (daGui !== null) dispatch({ type: "endEdit" });
  }

  /**
   * NUDGE mốc của **dòng ĐANG SỬA** — `by` là **SỐ GIÂY** được CỘNG vào mốc (`-0,1` · `+0,1` ·
   * `-1` · `+1`). Nudge đi qua `ghiDoan` ⇒ **TỚI ĐƯỢC ĐĨA**, không chỉ đổi state cục bộ.
   *
   * 🔴 BẢNG PHÍM ĐÃ TRẢ VỀ ĐÚNG NGUỒN SPEC Ở TASK 11 (ERRATA #44 mục 3): spec UI §5.1 dòng
   * 300–301 + §5.2 dòng 309 gán nudge cho **`Shift+←/→` (±0,1s)** và **`Alt+←/→` (±1s)**; còn
   * `[`/`]` = *"đặt mốc start/end TẠI ĐẦU ĐỌC"*, nay là hàm `datMocTaiDauDoc` ngay dưới. Trước
   * task này hàm này bị gọi bởi `[`/`]` với bước CỨNG 0,1s — đúng bảng phím của brief D1, sai
   * nguồn spec.
   *
   * ⚠️ `by` mang DẤU: `resolveKey` đã chốt chiều (`start` đi cùng số âm, `end` cùng số dương), nên
   * ở đây chỉ có MỘT phép cộng — thêm một `if (moc === "start")` nữa là định nghĩa chiều lần thứ
   * hai (và nó sẽ âm thầm bỏ qua `Alt+←` = −1).
   *
   * ⚠️ **KHÔNG có dòng nào đang sửa ⇒ KHÔNG LÀM GÌ** (0 request — bài `D1 NUDGE KHÔNG CÓ DÒNG
   * ĐANG SỬA` đếm ở PHÍA MÁY CHỦ). Guard `i === null` là **phòng thủ TRÙNG LẶP CÓ CHỦ Ý**, KHÔNG
   * phải thứ đang chặn việc ghi: mutant bỏ nó ra (`P9` của D1) cho **0 bài đỏ** vì `ghiDoan` CŨNG
   * từ chối (`!nen.some(seg => seg.i === i)` không khớp đoạn nào khi `i === null`).
   *
   * ⚠️ **KHÔNG clamp** mốc: `formatTimecode` đã kẹp giây âm về 0 (và có bài ghim riêng ở
   * `timecode.test.ts`), nên kẹp lần hai ở đây là hai định nghĩa cho một luật.
   *
   * 🔊 **NGHE LẠI 300 ms** (spec UI §5.2 dòng 309: *"mỗi lần nudge phát lại 300ms quanh mốc mới để
   * nghe ngay"*): sau khi máy chủ ĐÃ NHẬN, `App` phát một YÊU CẦU nghe lại xuống `Transport`, nơi
   * duy nhất chạm được phần tử media. Vị trí tua = **mốc của CHÍNH đoạn mà lệnh ghi vừa gửi**
   * (`daGui[moc]` — cùng một phép cộng, cùng một nền), không phải một phép tính lại ở ngoài.
   * ⚠️ Hai quyết định, nói ra: (i) yêu cầu đi SAU khi ghi xong, nên nó không bao giờ phát một mốc
   * chưa được lưu; (ii) nudge bằng CHUỘT (hai nút ở `EditScreen`) đi qua đúng hàm này ⇒ cũng nghe
   * lại — spec gán nudge cho bàn phím, nhưng "nghe lại" là hệ quả của HÀNH ĐỘNG nudge, không của
   * phím.
   */
  async function nudgeDoan(moc: "start" | "end", by: number): Promise<void> {
    const i = ui.editingSegment;
    if (i === null) return;
    const hienTai = transcript.data;
    if (hienTai === null) return;
    const daGui = await ghiDoan(hienTai.id, i, (seg) =>
      moc === "start" ? { ...seg, start: seg.start + by } : { ...seg, end: seg.end + by },
    );
    if (daGui !== null) {
      datNgheLai({ giay: daGui[moc], lan: demNgheLai.current++ });
    }
  }

  /**
   * ĐẶT MỐC của dòng ĐANG SỬA **TẠI ĐẦU ĐỌC** (`[` = start, `]` = end) — spec UI §5.1 dòng 296 +
   * §5.2 dòng 310: *"`[` và `]` đặt mốc tại vị trí đầu đọc — nhanh hơn kéo chuột rất nhiều"*.
   *
   * ⚠️ `giay` là THAM SỐ, không phải một lần đọc `dauDocRef` ở đây: xem docblock của `dauDocRef`
   * — giá trị phải được chốt LÚC BẤM. Và đây KHÔNG phải nudge: mốc được GÁN BẰNG, không cộng
   * thêm (mutant `P9` — `[` gọi lại `nudgeDoan` — là bài `T11 MỐC TẠI ĐẦU ĐỌC` ĐỎ).
   *
   * ⚠️ Không có dòng đang sửa ⇒ không làm gì (0 request), cùng luật với `nudgeDoan`.
   */
  async function datMocTaiDauDoc(moc: "start" | "end", giay: number): Promise<void> {
    const i = ui.editingSegment;
    if (i === null) return;
    const hienTai = transcript.data;
    if (hienTai === null) return;
    await ghiDoan(hienTai.id, i, (seg) =>
      moc === "start" ? { ...seg, start: giay } : { ...seg, end: giay },
    );
  }

  /**
   * CHỌN ĐOẠN kề (`J` = dòng trước, `K` = dòng sau — spec UI §5.1 dòng 297).
   *
   * Đây là đường BÀN PHÍM cho bước "chuyển đoạn" của §12.5; nó chỉ dispatch `setCurrentSegment`,
   * tức CÙNG đường mà cú bấm/nhảy đoạn của thanh transport đã dùng — không mở đường ghi nào.
   *
   * ⚠️ **KẸP hai đầu, KHÔNG vòng**: `J` ở dòng ĐẦU giữ nguyên dòng đầu. Một vòng lặp làm người
   * dùng đang soát xuôi bị ném về dòng cuối — và bài `T11 CHUYỂN ĐOẠN` ghim đúng vế đó.
   * ⚠️ Chưa chọn dòng nào ⇒ chọn dòng ĐẦU cho cả hai phím: "dòng trước" của một lựa chọn rỗng
   * không có nghĩa, còn nhảy vào dòng cuối thì bất ngờ.
   */
  function nhayDoan(buoc: number): void {
    const doan = transcript.data?.segments ?? [];
    if (doan.length === 0) return;
    const viTri = ui.currentSegment === null
      ? -1
      : doan.findIndex((seg) => seg.i === ui.currentSegment);
    const ke = viTri < 0 ? 0 : Math.min(Math.max(viTri + buoc, 0), doan.length - 1);
    dispatch({ type: "setCurrentSegment", i: doan[ke].i });
  }

  /**
   * NHẢY TỚI ĐOẠN NGHI NGỜ KẾ TIẾP (`N` — spec UI §5.1 dòng 299).
   *
   * "Kế tiếp" = chỉ số LỚN HƠN dòng đang chọn; `suspect` là cờ **của MÁY CHỦ** (`Segment.suspect`,
   * backend tính) — client KHÔNG suy lại từ `no_speech_prob`/`avg_logprob` (Global Constraints).
   *
   * ⚠️ Hết dòng nghi ngờ ⇒ **KHÔNG LÀM GÌ** (không vòng về dòng nghi ngờ đầu): đây là phép soát
   * XUÔI, một cú nhảy ngược là mất chỗ đang đọc. Vế "không vòng" nay **CÓ BÀI GHIM** (vòng sửa 1,
   * `M-3`): fixture bản ghi #3 có HAI dòng nghi ngờ (`i = 1` và `i = 3`), nên bản cài VÒNG sẽ nhảy
   * ngược về `i = 1` và bài `T11 N` ĐỎ. Trước vòng sửa, fixture chỉ có MỘT dòng nghi ngờ ở dòng
   * CUỐI, và ở đó cả hai bản cài đều đứng yên — một mệnh đề không có gì làm nó sai được.
   */
  function nhayNghiNgo(): void {
    const doan = transcript.data?.segments ?? [];
    const viTri = ui.currentSegment === null
      ? -1
      : doan.findIndex((seg) => seg.i === ui.currentSegment);
    const ke = doan.find((seg, k) => k > viTri && seg.suspect === true);
    if (ke === undefined) return;
    dispatch({ type: "setCurrentSegment", i: ke.i });
  }

  /**
   * NƠI DUY NHẤT biến một `KeyAction` thành việc thật. `App` là người biết state và các đường
   * ghi, nên `src/keys/` chỉ TRA bảng còn nối dây nằm ở đây (ERRATA #33 mục 1).
   *
   * ⚠️ **GUARD Ô NHẬP (I3, ERRATA #44 mục 2) KHÔNG nằm ở đây** — nó nằm ở `useShortcuts` (và ở
   * `resolveKey` qua tham số `inField`), và điều đó có chủ ý: một phím gõ trong ô sửa phải không
   * tới được hàm NÀY, chứ không phải tới rồi mới bị bỏ. Không có guard thì người dùng gõ `[` trong
   * phụ đề (`[nhạc nền]`) là **GHI vào máy chủ** mỗi ký tự: `version` tăng, bản dịch thành `stale`,
   * mốc bị dịch. ⚠️ Trước vòng sửa D1, CHÍNH bài test của commit đó dispatch `[` trên `textarea`
   * rồi khẳng định `dem.patch === 1` — tức nó ghi lại LỖI như thể là đặc tả ĐÚNG.
   */
  function xuLyPhim(hanhDong: KeyAction): void {
    // BẢNG ĐANG MỞ ⇒ nó CHẶN mọi phím khác (trừ chính nó và `Esc`): một lớp phủ đang che màn hình
    // mà phím `[` vẫn ghi vào bản ghi phía sau là một thao tác người dùng KHÔNG NHÌN THẤY.
    if (moBangPhim && hanhDong.type !== "toggleShortcuts" && hanhDong.type !== "endEdit") return;
    switch (hanhDong.type) {
      case "toggleShortcuts":
        datMoBangPhim((cu) => !cu);
        return;
      case "togglePlay":
        dispatch({ type: "setPlaying", playing: !ui.playing });
        return;
      case "segmentPrev":
        nhayDoan(-1);
        return;
      case "segmentNext":
        nhayDoan(1);
        return;
      case "nextSuspect":
        nhayNghiNgo();
        return;
      case "startEdit":
        // `Enter` = sửa DÒNG ĐANG CHỌN (spec §5.1 dòng 298 + §5.2 dòng 307). Không có dòng đang
        // chọn ⇒ không mở ô sửa nào (mở dòng 0 là đoán ý người dùng). Dọn lỗi ghi của lượt trước —
        // CÙNG việc mà lối chuột làm (`EditScreen.onStartEdit` ở dưới).
        if (ui.currentSegment === null) return;
        datLoiGhiDoan(null);
        dispatch({ type: "startEdit", i: ui.currentSegment });
        return;
      case "endEdit":
        // `Esc` khi bảng đang mở = ĐÓNG BẢNG, không phải thoát ô sửa: một phím, một việc, và việc
        // gần nhất với thứ đang che màn hình. `Esc` lần hai mới thoát ô sửa (bài ghim hai vế).
        if (moBangPhim) {
          datMoBangPhim(false);
          return;
        }
        dispatch({ type: "endEdit" });
        return;
      case "setMode":
        dispatch({ type: "setMode", mode: hanhDong.mode });
        return;
      case "setEdgeAtPlayhead": {
        // 🔴 CHỐT ĐẦU ĐỌC **LÚC BẤM** (xem `dauDocRef`), rồi mới xếp hàng. Đọc bên trong việc đã
        // xếp hàng là lấy vị trí SAU cú bấm.
        const giay = dauDocRef.current;
        xepHangGhi(() => datMocTaiDauDoc(hanhDong.edge, giay));
        return;
      }
      case "nudge":
        xepHangGhi(() => nudgeDoan(hanhDong.edge, hanhDong.by));
        return;
      // BA PHÍM SPEC CÓ MÀ SẢN PHẨM CHƯA CÓ ĐÍCH. Chúng VẪN được `resolveKey` trả về (bảng §11.4
      // phải phủ bảng §5.1) nhưng KHÔNG được nối: `S` tách dòng và `M` gộp dòng cần một phép biến
      // đổi danh sách đoạn (đánh lại số `i`) mà không endpoint nào sở hữu; `Ctrl+Enter` ("chạy job
      // cho kênh đang chọn") không có đường nào trong app (`createTranslation` là DỊCH, một việc
      // khác). `BangPhim` in dấu `chưa nối` cho đúng ba hàng này (nguồn: `DA_NOI`), và bài
      // `T11 PHÍM CHƯA CÓ ĐÍCH` ghim rằng chúng vẫn TRƠ (0 request, DOM không đổi).
      // ⚠️ KHÔNG có `default`: union `KeyAction` là ĐÓNG, nên thêm một hành động mới mà quên nối
      // thì TypeScript báo ngay ở đây.
      case "splitAtPlayhead":
      case "mergeWithNext":
      case "runJob":
        return;
    }
  }

  // MỘT listener `keydown` cho cả app, ở `document` (trước Task 11 nó ở `window` và chỉ nhận
  // `[`/`]`). `ui.mode` đi vào KHOÁ TRA của `resolveKey`: phím của màn Biên tập không bắn ở màn
  // khác — `setMode` không xoá `editingSegment`, nên thiếu vế đó thì một phím `[` ở màn Đối chiếu
  // vẫn GHI vào bản ghi trong khi không có ô sửa nào trên màn hình.
  useShortcuts(xuLyPhim, ui.mode);

  // ---------------------------------------------------------------------------
  // ĐIỀU **KHÔNG** LÀM Ở ĐÂY — một "ngòi nổ đọc lại bảo hiểm" (đã đo, đừng thêm lại)
  //
  // Một `useEffect` gọi `translations.reload()` khi hàng vừa tạo CHƯA có trong danh sách từng
  // nằm ở đây. Lượt mutation `W3-4b` vô hiệu hoá nó ⇒ **0 bài đỏ** (`tests 196 / pass 194 /
  // fail 2 / cancelled 0`), tức đó là mã CHẾT chứ không phải một lưới an toàn: mỗi lần chạy,
  // nó chỉ thấy `translations.loading === true` (ngay sau `reload()` của `taoBanDich`) rồi
  // thoát, và tới khi lần đọc đó xong thì hàng mới ĐÃ có trong danh sách. Giữ nó lại là một
  // lượt `GET /api/translations` thừa và một đường không ai ghim.
  // `ponytail:` TRẦN: nếu sau này có đường ghi khác KHÔNG tự `reload`, nâng cấp bằng một hàm
  // "ghi rồi đọc lại" dùng chung (một chỗ), chứ không phải thêm một effect đoán ý.
  // ---------------------------------------------------------------------------
  const banMoiCoTrongDanhSach =
    banMoiTao !== null
    && (translations.data ?? []).some((row) => row.id === banMoiTao.id);

  /**
   * Bản dịch ĐANG XEM — câu trả lời DUY NHẤT của `App`, truyền xuống cả `CompareScreen`
   * (`macDinhId`) lẫn `Transport` (`translationId`).
   *
   * Ưu tiên: bản NGƯỜI DÙNG TỰ BẤM CHỌN → bản VỪA TẠO (nếu còn thuộc kênh/bản ghi này và còn
   * trong danh sách) → bản `done` mới nhất. ⚠️ Các vế `kenh`/`tid`/`trongDanhSach` KHÔNG phải
   * những quyết định thứ hai: chúng là điều kiện để một id trần KHÔNG áp cho một kênh/bản ghi
   * khác — id trần của kênh cũ trỏ vào hư không ở kênh mới.
   *
   * ⚠️ VẾ "NGƯỜI DÙNG TỰ BẤM CHỌN" ĐỨNG ĐẦU là hệ quả của một phép đo (mutation
   * `I1-chon-ban-12`): khi nó không có, `banMoiTao` che mất lựa chọn của người dùng, và cột phải
   * của bản họ chọn bị dán nhãn job CỦA BẢN VỪA TẠO.
   */
  const banDangXemId =
    banDaChon !== null
    && banDaChon.kenh === ui.channelId
    && banDaChon.tid === tid
    && (translations.data ?? []).some((row) => row.id === banDaChon.id)
      ? banDaChon.id
      : banMoiTao !== null && banMoiTao.kenh === ui.channelId && banMoiCoTrongDanhSach
        ? banMoiTao.id
        : banDichXuat === null ? null : banDichXuat.id;

  /**
   * HÀNG ĐẦY ĐỦ của bản đang xem — cần `status` để trả lời câu *"nó đã dịch xong chưa"*.
   *
   * ⚠️ VÌ SAO PHẢI CÓ (vòng sửa W3 #2, `Important` F2 của re-review): `Transport` cũ tự đoán
   * lý do của sự lệch id và **đoán SAI**. Probe của reviewer trên fixture có **HAI** bản `done`:
   *   `XUATCHO="bản đang xem (11) chưa dịch xong — xuất bản 13" HREF=/api/export/13?… TOKEN=11`
   * trong khi bản **11 ĐÃ `done`**. Sự lệch id có **HAI** lý do khác nhau, và `status` là thứ duy
   * nhất phân biệt được chúng ⇒ nó phải được đọc ở nơi có dữ liệu (đây), không phải ở `Transport`.
   */
  const banDangXem =
    banDangXemId === null
      ? null
      : (translations.data ?? []).find((row) => row.id === banDangXemId) ?? null;

  /**
   * BẢN SẼ ĐƯỢC XUẤT — **MỘT** nguồn quyết định (ERRATA #36 mục 4; vòng sửa W3 #2, F2).
   *
   * Luật: bản ĐANG XEM đã `done` ⇒ xuất **chính nó**; ngược lại (nó `queued`/`running`/
   * `failed`/`cancelled`, tức chưa có nội dung để xuất) ⇒ xuất bản `done` mới nhất.
   *
   * ⚠️ Trước vòng sửa, chỗ này LUÔN là `banDichXuat.id` (bản `done` mới nhất), nên lựa chọn của
   * người dùng bị **ghi đè để XUẤT**: chọn bản 11 (`done`) mà ba nút vẫn trỏ bản 13. Đó là một
   * câu hỏi KHÁC với `banDangXemId` (bản đang ĐỌC) — nhưng câu trả lời của nó phải TÔN TRỌNG
   * lựa chọn đó khi lựa chọn ấy đã có nội dung để xuất.
   */
  const banDangXemDaDichXong = banDangXem !== null && banDangXem.status === "done";
  const idXuatDuoc = banDangXemDaDichXong
    ? banDangXem.id
    : banDichXuat === null
      ? null
      : banDichXuat.id;

  /**
   * CÂU NÓI RA khi ba nút xuất trỏ vào một bản KHÁC bản đang xem — do `App` QUYẾT, `Transport`
   * chỉ render (xem `TransportProps.xuatCho`).
   *
   * ⚠️ Điều kiện ở đây là điều kiện **ĐÚNG**: câu này chỉ được nói khi (a) hàng của bản đang xem
   * CÓ THẬT trong dữ liệu, (b) `status` của nó **KHÁC** `done` — tức nó thật sự chưa có nội dung
   * để xuất, và (c) có một bản khác để xuất. Thiếu (b) thì câu nói NGƯỢC sự thật đúng như probe
   * `RR-PROBE-2` đã đo.
   */
  const cauXuatCho =
    banDangXem !== null && !banDangXemDaDichXong && idXuatDuoc !== null
      ? `bản đang xem (${banDangXem.id}) chưa dịch xong — xuất bản ${idXuatDuoc}`
      : null;

  /**
   * Trạng thái JOB của bản vừa tạo, **CHỈ khi nó thuộc ĐÚNG bản dịch đang xem VÀ ĐÚNG kênh**
   * — hai khoá, không phải một (vòng sửa `I1`, ERRATA #36 mục 4).
   *
   * ĐO ĐƯỢC trước vòng sửa: `trangThaiJobMoi` được truyền xuống TRẦN, nên chọn bản `11`
   * (`done`, KHÔNG có job) sau khi tạo bản `13` ⇒ cột phải hiện
   * `"chưa có đoạn này · job: chờ gom lô"` — **job của bản 13**. Vế `id` một mình đã đủ cho
   * ca ĐÓ, nhưng vế `kenh` là bắt buộc cho ca ĐỔI KÊNH: id hai kênh khác nhau có thể trùng,
   * và `banMoiTao` đã phải ghim theo kênh vì đúng lý do này.
   */
  const trangThaiJobCuaBanDangXem =
    trangThaiJobMoi !== null
    && trangThaiJobMoi.kenh === ui.channelId
    && trangThaiJobMoi.id === banDangXemId
      ? trangThaiJobMoi.state
      : null;

  /**
   * Lỗi tạo **CHỈ khi nó thuộc ĐÚNG kênh đang chọn**. Xem `loiTao` ở trên: câu 409 của kênh
   * cũ từng nằm lại trong `.cmp__tin` sau khi đổi kênh.
   */
  const loiTaoCuaKenhDangChon =
    loiTao !== null && loiTao.kenh === ui.channelId ? loiTao.cau : null;

  /**
   * CÂU NÓI RA khi bản dịch của bản ghi đang mở đã **LỖI THỜI** so với bản ghi (spec UI §5.2:
   * *"Mọi thay đổi làm `transcripts.version` tăng → bản dịch cũ thành `stale`"*).
   *
   * ⚠️ Cờ `stale` là của **MÁY CHỦ** (`domain/staleness.is_stale`, TÍNH LẠI mỗi lần đọc vì nó
   * không được lưu ở đâu) — `App` **KHÔNG** tự so `transcript_version` với `version`: hai nơi
   * tính cùng một đại lượng là đúng thứ Global Constraints cấm.
   *
   * ⚠️ Và câu này **KHÔNG được im lặng**: người dùng vừa sửa một dòng, nên mọi bản dịch đã có
   * không còn khớp bản ghi nữa. `App` quyết CÂU rồi truyền xuống (cùng khuôn `Transport.xuatCho`),
   * `EditScreen` chỉ render.
   */
  const cauLoiThoi = (translations.data ?? []).some((row) => row.stale)
    ? "bản dịch đã lỗi thời so với bản ghi"
    : null;

  /**
   * ĐỔI KÊNH ⇒ DỌN mọi state của lần tạo thuộc kênh CŨ (vòng sửa `I1`, ERRATA #36 mục 4:
   * *"reset `loiTao` khi đổi kênh"*).
   *
   * ⚠️ Vì sao vẫn cần effect này khi hai giá trị truyền xuống ĐÃ có vế `kenh`: (1) `loiTao`
   * của kênh cũ sẽ SỐNG LẠI nếu người dùng quay về kênh đó — một câu 409 của một lần bấm đã
   * cũ vẫn hiện như mới; (2) đó là điều kiện để hai state anh em này không tích tụ dữ liệu
   * của kênh khác. `dangTao` KHÔNG dọn ở đây: một lời gọi POST đang bay vẫn phải khoá nút
   * `dịch` cho tới khi nó trả về (`finally` của `taoBanDich` mới là chỗ mở khoá).
   */
  useEffect(() => {
    datBanMoiTao(null);
    datTrangThaiJobMoi(null);
    datLoiTao(null);
    datBanDaChon(null);
    // LỖI GHI của D1 cũng thuộc BẢN GHI đang mở: để nó sống qua một lần đổi kênh là một câu 422
    // của bản ghi KHÁC hiện như mới (cùng lý do `loiTao` ở trên).
    datLoiGhiDoan(null);
    // LỖI DUYỆT của D2 cũng vậy: câu 422 của bản ghi CŨ không được nằm cạnh thanh trên của bản ghi
    // MỚI (cùng lớp lỗi `I1` mà vòng sửa W3 đã đóng cho `loiTao`).
    datLoiDuyet(null);
    // Và CỜ "đang bay" của lệnh duyệt: nó thuộc về bản ghi + kênh CŨ (`I3b`), nên để nó sống qua
    // một lần đổi kênh là thanh trên của kênh MỚI tự nói *"đang duyệt…"*.
    datDangDuyet(null);
  }, [ui.channelId]);

  /**
   * Người dùng bấm một bản dịch khác trong segmented control ⇒ `App` ghi lại lựa chọn đó.
   *
   * Đây là NỐI DÂY, không phải một điểm quyết định thứ hai: lựa chọn này chỉ có nghĩa trong
   * kênh + bản ghi hiện tại, và nó đi vào CHÍNH biến `banDangXemId` ở trên.
   */
  function chonBanDich(id: number): void {
    if (tid === null || ui.channelId === null) return;
    datBanDaChon({ id, kenh: ui.channelId, tid });
  }

  // ---------------------------------------------------------------------------
  // NGÒI NỔ ĐỌC LẠI `/api/transcripts` (vòng sửa W1 #1 — `Minor #3`, LỖI CHỨC NĂNG)
  //
  // ĐO ĐƯỢC trước vòng sửa: danh sách transcript được đọc ĐÚNG MỘT lần với `deps = []`, và
  // `transcripts.reload` không được nối vào đâu (`grep '\.reload'` chỉ ra `status.reload`)
  // ⇒ sau khi job `ingest`/`asr` xong, BẢN GHI MỚI KHÔNG BAO GIỜ HIỆN cho tới khi tải lại
  // cả trang. W2 (nạp tệp) và W3 (bắt đầu dịch) đụng ngay chỗ này.
  //
  // BA vế của ngòi nổ, và cả ba đều phải có:
  //   (a) `ui.channelId` ĐỔI ⇒ đọc lại danh sách (bản ghi đang mở của kênh mới có thể chưa
  //       có trong ảnh chụp cũ). Ngòi này chạy một lần cho mỗi lần đổi kênh.
  //   (b) MỘT JOB `ingest`/`asr` CỦA KÊNH ĐANG CHỌN chuyển sang `done` ⇒ đọc lại. Đây là vế
  //       đóng lỗi "job xong mà danh sách không đổi".
  //   (c) MỘT JOB `translate` chuyển sang `done` (hoặc `failed`/`cancelled`) ⇒ đọc lại
  //       `/api/translations`. Đây là vế đóng `I3` của review W3 (ERRATA #36 mục 4).
  //
  // ⚠️ VẾ (b)/(c) SO VỚI BẢN ĐỒ JOB TRƯỚC ĐÓ, KHÔNG PHẢI "job nào đó đang `done`": gọi lại
  // mỗi nhịp SSE là BÃO REQUEST (mỗi sự kiện tiến độ ⇒ một `GET`), và bài test
  // `khong bao request` đếm số request ở PHÍA SERVER để ghim đúng vế đó.
  // ⚠️ Và lần đổi kênh chỉ GHI LẠI MỐC, không tự kích: lần đọc lại của (a) xảy ra qua `deps`
  // `[ui.channelId]` của `banGhiTomTat`/`chonTranscript`. Gọi `reload()` ở đây nữa là HAI
  // request cho MỘT lần bấm kênh.
  // ---------------------------------------------------------------------------
  /** Tập job ĐÃ-CHUYỂN-TRẠNG-THÁI-BỎ của kênh đang chọn: `done` cho ingest/asr, và
      `done`/`failed`/`cancelled` cho translate. So HAI CHIỀU (vào/ra) như W1 đã làm. */
  const jobDoneRef = useRef<Set<number> | null>(null);
  const translateKetThucRef = useRef<Set<number> | null>(null);
  const kenhRef = useRef(ui.channelId);

  useEffect(() => {
    const kenhDoi = kenhRef.current !== ui.channelId;
    kenhRef.current = ui.channelId;

    const doneCuaKenh = new Set<number>();
    const ketThucDichCuaKenh = new Set<number>();
    for (const job of jobs.values()) {
      // `payload` là `Record<string, unknown>`: đọc bằng KHOÁ CỤ THỂ và so qua một biến
      // `unknown` — cùng cách `ChannelZone.buocCuaKenh` đọc, không hứa gì về kiểu.
      const idTrongPayload: unknown = job.payload["source_id"];
      if (job.type === "translate") {
        // ⚠️ Payload của job `translate` mang `translation_id`, KHÔNG mang `source_id`
        // (`backend/app/domain/models.py::translation_id_of`), nên không suy được kênh từ nó.
        // Đây là lý do vế (c) KHÔNG lọc theo kênh mà lọc theo BẢN DỊCH ĐANG XEM — xem dưới.
        if (job.state !== "done" && job.state !== "failed" && job.state !== "cancelled") continue;
        const idBanDich: unknown = job.payload["translation_id"];
        if (idBanDich !== banDangXemId) continue;
        ketThucDichCuaKenh.add(job.id);
        continue;
      }
      if (job.state !== "done") continue;
      if (idTrongPayload !== ui.channelId) continue;
      doneCuaKenh.add(job.id);
    }

    const truoc = jobDoneRef.current;
    const truocDich = translateKetThucRef.current;
    jobDoneRef.current = doneCuaKenh;
    translateKetThucRef.current = ketThucDichCuaKenh;
    // Lần chạy ĐẦU chỉ ghi mốc: không có "trước đó" thì không có chuyển trạng thái nào cả.
    if (truoc === null || truocDich === null || kenhDoi) return;

    // CHUYỂN TRẠNG THÁI, không phải TRẠNG THÁI: so HAI CHIỀU (job vào `done` = xong; job rời
    // `done` = chạy lại). Một sự kiện tiến độ của job đang chạy không đổi tập này ⇒ không đọc lại.
    if (coChuyen(truoc, doneCuaKenh)) transcripts.reload();

    // (c) JOB DỊCH KẾT THÚC ⇒ đọc lại `/api/translations`. CÙNG khuôn chuyển-trạng-thái ở
    // trên, nên một nhịp TIẾN ĐỘ (`running` 0.4 → 0.6) KHÔNG keo request nào, còn
    // `running ⇒ done` keo ĐÚNG MỘT.
    //
    // ⚠️ Vì sao `translations.reload()` là thứ ĐÚNG ở đây (và là thứ DUY NHẤT): bản dịch vừa
    // xong có `segments` chỉ đến từ `GET /api/translations/{id}` — client không được tự sinh
    // chữ dịch. Không có vế này thì hàng vẫn `queued` và cột phải vẫn nói "đang dịch…" MÃI MÃI
    // cho tới khi người dùng đổi kênh hoặc tải lại trang (`I3`).
    if (coChuyen(truocDich, ketThucDichCuaKenh)) translations.reload();
  }, [jobs, ui.channelId, banDangXemId, transcripts.reload, translations.reload]);

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
            /* W2: lối nạp GỌN ở vùng KÊNH — CÙNG hàm `napTep` với khung §4.2 ở vùng giữa.
               Nó tồn tại vì khi ĐÃ có kênh thì vùng giữa hiện danh sách đoạn, nên khung §4.2
               không còn ở đó (§12.2 cần nạp được tệp thứ 2..N). */
            onNapTep={napTep}
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
               lần thứ hai. Trước vòng sửa W1, màn lấy `translations[0]` theo VỊ TRÍ MẢNG
               (route thật trả MỚI NHẤT TRƯỚC ⇒ hàng `queued`), nên người dùng đang ĐỌC một
               bản rỗng trong khi ba nút xuất trỏ vào bản `done` khác — đo được `SAME = false`
               (review W1 §B(8)).
               Task W3 mở rộng ĐÚNG một câu trả lời đó thêm một ưu tiên: bản VỪA TẠO đứng
               trước bản `done` mới nhất (`banDangXemId`), để bấm "dịch" xong là THẤY ngay bản
               mới (nó `queued`, nên nếu không ưu tiên thì người dùng không thấy gì xảy ra).

               ⚠️ **ĐÍNH CHÍNH `I2` (ERRATA #36 mục 4): câu "hai vùng KHÔNG THỂ nói khác
               nhau" ở đây TỪNG SAI.** Ở `73a9a18` cả hai vùng dùng `banDichXuat.id`; ở HEAD
               trước vòng sửa này, vùng này = `banDangXemId` còn `Transport.translationId` =
               `banDichXuat.id` — HAI biểu thức, và mutant `W3-17` (đổi `Transport` sang biến
               kia) cho **0 bài đỏ**, tức bất biến này KHÔNG được ghim.
               Nay `Transport` nhận **CÙNG** `banDangXemId`, nên câu đó ĐÚNG LẠI, và bài
               `SAME` trong `App.test.tsx` ghim nó (W3-17 nay ĐỎ). `Transport` nhận thêm
               `exportableId` = bản `done` mới nhất — đó KHÔNG phải điểm quyết định thứ hai mà
               là câu trả lời cho một câu hỏi KHÁC ("bản nào có nội dung để xuất"), và khi nó
               khác `translationId` thì thanh transport phải NÓI RA. */
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
              /* ⚠️ HAI PROP NAY ĐI QUA MỘT BỘ LỌC HAI KHOÁ (`I1`, ERRATA #36 mục 4):
                 `trangThaiJobCuaBanDangXem` chỉ khác `null` khi job thuộc ĐÚNG bản dịch
                 đang xem VÀ ĐÚNG kênh; `loiTaoCuaKenhDangChon` chỉ khác `null` khi câu lỗi
                 thuộc ĐÚNG kênh đang chọn. Truyền `trangThaiJobMoi`/`loiTao` TRẦN ở đây
                 chính là lỗi đã đo được: chọn bản 11 (`done`) ⇒ cột phải hiện job của bản 13. */
              loiTao={loiTaoCuaKenhDangChon}
              trangThaiJob={trangThaiJobCuaBanDangXem}
              /* Lựa chọn của người dùng đi LÊN `App` (xem `banDaChon`): nếu giữ nó ở state cục
                 bộ của màn thì `banDangXemId` — và do đó cả `Transport` — vẫn là bản VỪA TẠO. */
              onChonBanDich={chonBanDich}
            />
          ) : ui.mode === "glossary" ? (
            /* §4.4 tab THUẬT NGỮ (Task 9). Màn này KHÔNG nhận prop: nó độc lập với
               kênh đang mở, và nó TỰ gọi `listTerms`/`createTerm`/`patchTerm`/
               `affectedPreview`. Đó là khác biệt có chủ ý với `EditScreen`/
               `CompareScreen` ở trên — hai màn kia đọc bản ghi đang mở. */
            <GlossaryScreen />
          ) : (
            /* W2: `onNapTep` di xuong `EditScreen` ⇒ khung §4.2 o TRANG THAI RONG cua vung giua.
               Cung MOT ham voi loi nap gon o vung KENH — xem `napTep` o tren.
               D1: `editingSegment` (state TRUOC DAY CHET — 0 dispatch, 0 nguoi doc) nay co nguoi
               dung that, va BON callback ghi di xuong. Man nay KHONG goi API: no chi BAO. */
            <EditScreen
              transcript={transcript.data}
              currentSegment={ui.currentSegment}
              onNapTep={napTep}
              editingSegment={ui.editingSegment}
              onStartEdit={(i) => {
                // Mo mot luot sua MOI ⇒ cau loi cua luot truoc khong con thuoc ve no.
                datLoiGhiDoan(null);
                dispatch({ type: "startEdit", i });
              }}
              onCommitEdit={(i, text) => xepHangGhi(() => luuDoan(i, text))}
              onCancelEdit={() => dispatch({ type: "endEdit" })}
              /* Lối CHUỘT của nudge = bước ±0,1s (cùng bước với `Shift+←/→`). `±1s` (`Alt+←/→`)
                 CHỈ có ở bàn phím — thêm hai nút nữa là một affordance mới không task nào sở hữu,
                 và mọi đường mới phải có bài ghim (ERRATA #43 mục 1). Đã khai trong báo cáo. */
              onNudge={(moc) => xepHangGhi(() => nudgeDoan(moc, moc === "start" ? -0.1 : 0.1))}
              dangLuu={dangLuuDoan}
              loiGhi={loiGhiDoan}
              cauLoiThoi={cauLoiThoi}
              /* D2: nut `duyet` o thanh tren cua man. Man chi BAO — `App` goi
                 `approveTranscript` roi DOC LAI ban ghi (`status` la du lieu cua MAY CHU). */
              onDuyet={duyetBanGhi}
              /* "ĐANG DUYỆT…" LÀ CÂU CỦA **BẢN GHI ĐANG MỞ TRONG KÊNH ĐANG CHỌN**, không phải một
                 cờ toàn cục: lời gọi của bản ghi CŨ (kênh khác) không được nói thay bản ghi này. */
              dangDuyet={
                dangDuyet !== null
                && transcript.data !== null
                && dangDuyet.id === transcript.data.id
                && dangDuyet.kenh === ui.channelId
              }
              loiDuyet={loiDuyet}
            />
          )}
        </main>
        <aside className="shell__queue">
          {/* D2: vùng HÀNG ĐỢI nhận BA prop nữa — hai lệnh (`huỷ`/`chạy lại`) và hai bản đồ NÓI RA
              trạng thái của CHÍNH các lệnh đó. ⚠️ Bản đồ job vẫn là của `useJobStream`: `App`
              KHÔNG sửa nó tại chỗ sau khi bấm (xem `daYeuCauHuy`). */}
          <QueueZone
            jobs={jobs}
            daYeuCauHuy={daYeuCauHuy}
            loiLenh={loiLenh}
            onHuyJob={huyJob}
            onChayLaiJob={chayLaiJob}
          />
        </aside>
      </div>
      {/* Thanh transport (§4.1): phát, timecode, track có đầu đọc, ba nút xuất — Task 7.
          Task W1 nối BA prop dữ liệu của nó vào bản ghi đang mở: `sourceId` là kênh đang
          chọn, `segments` là đoạn của bản ghi đó, `duration` là `Source.duration` của
          CHÍNH kênh đó (backend đo — client không đo lại). Chưa chọn kênh ⇒ cả ba vẫn
          `null`/`[]`, và thanh transport nói thật là chưa có gì để phát (nút vô hiệu,
          không `src`, không `href`).

          ⚠️ `translationId` là **CÙNG MỘT BIỂU THỨC** với `CompareScreen.macDinhId`
          (`banDangXemId`) — đây là bất biến `I2` (ERRATA #36 mục 4), và nó có bài ghim
          `SAME` trong `App.test.tsx`. Trước vòng sửa, chỗ này là `banDichXuat.id`: HAI biểu
          thức, và comment nói "hai vùng KHÔNG THỂ nói khác nhau" là SAI.

          ⚠️ `exportableId` là câu hỏi KHÁC ("bản nào CÓ NỘI DUNG để xuất"), và câu trả lời của nó
          là `idXuatDuoc` — **do chính `App` quyết** (bản đang xem đã `done` ⇒ xuất chính nó;
          ngược lại mới lấy bản `done` mới nhất). `xuatCho` là CÂU giải thích của cùng quyết định
          đó, cũng do `App` quyết: `Transport` KHÔNG tự đoán lý do của sự lệch id nữa (nó không có
          `status` của bản đang xem, và đoán sai — probe `RR-PROBE-2` của re-review W3 #1). */}
      <footer className="shell__transport">
        <Transport
          sourceId={ui.channelId}
          duration={kenhDangChon === null ? null : kenhDangChon.duration}
          segments={transcript.data?.segments ?? []}
          translationId={banDangXemId}
          exportableId={idXuatDuoc}
          xuatCho={cauXuatCho}
          playing={ui.playing}
          currentSegment={ui.currentSegment}
          onPlayingChange={(playing) => dispatch({ type: "setPlaying", playing })}
          onSegmentChange={(i) => dispatch({ type: "setCurrentSegment", i })}
          /* TASK 11: đầu đọc BÁO LÊN để `[`/`]` đặt được mốc "tại đầu đọc" (spec §5.1 dòng 296).
             Nó vào một `useRef`, KHÔNG vào state: `timeupdate` bắn ~4 lần/giây và reducer không có
             trường giây nào — cùng lý do `Transport.viTriPhat` là state cục bộ ở đó. */
          onDauDoc={(giay) => {
            dauDocRef.current = giay;
          }}
          /* TASK 11 (vòng sửa 1, `I-3`): MỘT YÊU CẦU NGHE LẠI sau mỗi lần nudge (spec §5.2 dòng
             309). `Transport` mới là nơi thi hành được (nó giữ phần tử media) — `App` chỉ nói
             "tua tới mốc này và nghe 300 ms". */
          ngheLai={ngheLai}
        />
      </footer>
      <div className="grain" aria-hidden />
      {/* BẢNG PHÍM TẮT §11.4 — CON CUỐI của `.shell`, nhưng **KHÔNG phải một grid item**:
          `.bp` là lớp phủ `position: fixed` (bài ghim CSS trong `src/keys/BangPhim.test.tsx`
          khẳng định đúng khai báo đó), nên nó ra khỏi luồng và **không** tiêu thụ track nào —
          CÙNG cách `.grain` ở trên. ⚠️ Nếu ai bỏ `position: fixed` thì nó thành con thứ năm của
          một lưới khai BỐN track: đó là ERRATA #31 mục 1, và bài ghim CSS là chỗ chặn.
          Chỉ render khi MỞ (mặc định đóng — nó che màn hình). */}
      {moBangPhim ? <BangPhim onDong={() => datMoBangPhim(false)} /> : null}
    </div>
  );
}
