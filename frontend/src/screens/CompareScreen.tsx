/**
 * §4.3 Màn ĐỐI CHIẾU — hai cột (nguồn / bản dịch) + CỘT CPS, segmented control chọn
 * bản dịch, GHIM bản B, và đánh dấu dòng VƯỢT NGƯỠNG ĐỌC (spec UI §4.3, §12.4).
 *
 * BỐN quyết định của tệp này, cả bốn đều là hệ quả của một phép đo:
 *
 * 1. **KHÔNG tính CPS ở client.** `TranslationDetail.cps` đến từ
 *    `GET /api/translations/{id}`, nơi con số được sinh bởi CÙNG hàm `mt_qa.cps_row`
 *    đã sinh chuỗi `cps:` trong `qa_issues` (xem `domain/mt_qa.py`). Tính lại ở đây là
 *    dựng nguồn sự thật thứ hai cho đúng đại lượng mà spec frontend §2 cấm — và
 *    `over` phải đọc từ backend vì nó so trên giá trị CHƯA làm tròn.
 * 2. **KHÔNG hiển thị `Infinity`/`NaN`.** Backend trả `cps: null` khi không đo được
 *    (cả hai cửa sổ đều không dương, `mt_qa` gọi là `nowindow`). Hiện `0` ở đó là bịa
 *    một tốc độ; hiện `—` là sự thật.
 * 3. **Màn KHÔNG tự `fetch`.** Dữ liệu vào qua PROP — cùng khuôn với `EditScreen`
 *    (Task 6) và `Transport` (Task 7): một chỗ gọi API cho mỗi màn là hai nguồn sự
 *    thật. Người gọi là đường CHỌN KÊNH, hiện CHƯA có (ERRATA #18 mục 4).
 * 4. **Glyph `⚠` ở dòng vượt ngưỡng là HÌNH THỨC do SPEC chỉ định, không phải emoji trang
 *    trí.** §4.3 nguyên văn: *"Dòng vượt ngưỡng đọc có `⚠` màu amber."*, và `grep -i emoji`
 *    trên spec = **0** ⇒ spec không cấm emoji; lệnh cấm là của PLAN và plan tự mâu thuẫn
 *    (ERRATA #19 mục 7). Mốc amber ở lề **và** `data-over-cps` vẫn GIỮ vì chúng phục vụ
 *    TIẾP CẬN (§7) — một glyph là tín hiệu chỉ-có-hình, không đọc được bằng screen reader.
 *
 * ⚠️ TRẦN CÒN LẠI (`ponytail:`) — **ĐÍNH CHÍNH (Task 13)**: câu cũ ở đây (*"trong app, `App`
 * truyền `transcript={null}` và `translations={[]}` vì chưa có đường CHỌN KÊNH, nên màn chỉ
 * render TRẠNG THÁI RỖNG"*) đã **HẾT ĐÚNG** từ Task W1 — `App.tsx:1196-1199` ghi đúng điều đó,
 * và mã hiện truyền `transcript={transcript.data}` / `translations={translations.data ?? []}`
 * (`App.tsx:1224-1225`). Trần còn lại là của **TẦNG ĐO**, không phải của sản phẩm: **chưa có
 * phép đo HÌNH THỨC nào cho `.cmp*` trên dữ liệu thật** — kế hoạch `frontend/e2e/plans/`
 * (`bon-man.json`, `ban-ghi-dai-t7.json`) chỉ đo computed style cho `.q__item`/`.q__ten` và
 * `.ed__khung`; ảnh `05-doi-chieu-cps-hai-chieu.png` **chỉ chứng minh BỐ CỤC/VẺ**, không
 * chứng minh nội dung. Mọi khẳng định về **NỘI DUNG** hai cột đến từ test truyền prop.
 * ĐƯỜNG NÂNG CẤP: thêm một bước đo `getComputedStyle` cho `.cmp*` (kèm một `khangDinh` cho số
 * dòng vượt ngưỡng) vào kế hoạch e2e, rồi khai nó vào `frontend/e2e/TIEU-CHI-12.md`.
 *
 * `ponytail:` GHIM là state CỤC BỘ của màn này. `UiState.pinnedB` + action `pinB` đã có
 * sẵn trong `state/reducer.ts` nhưng **thiếu action BỎ GHIM**, nên nối vào reducer là
 * việc của task CHỌN KÊNH (nó phải sở hữu cả `channelId` lẫn bản dịch đang chọn).
 * ĐƯỜNG NÂNG CẤP: truyền `pinnedB`/`onPinB` xuống và thêm một action bỏ ghim.
 *
 * ── CỬA VÀO "BẮT ĐẦU DỊCH" (Task W3) ────────────────────────────────────────────────
 *
 * Đo được TRƯỚC W3: `endpoints.createTranslation` **0 lượt gọi trong sản phẩm** ⇒ không có
 * cách nào BẮT ĐẦU một bản dịch từ giao diện; `endpoints.listEngines` **0** và
 * `<EngineSelect/>` (Task 10) **0 người gọi**. W3 là NGƯỜI GỌI ĐẦU TIÊN của cả hai, và cửa
 * vào được đặt ở ĐÂY — Đối chiếu là nơi bản dịch sống, và segmented control của nó đã là nơi
 * liệt kê bản dịch (một cửa vào, không phải ba).
 *
 * Nó hiện ở CẢ HAI trạng thái: khi chưa có bản dịch nào (khoảnh khắc người dùng cần nó nhất —
 * trạng thái rỗng phải có CÒ, không phải một câu "chưa có gì") và khi đã có (lối gọn
 * `+ bản dịch mới`).
 *
 * ⚠️ **CHỈ engine `kind === "mt"`** được đưa xuống `EngineSelect`. `App` làm phẳng
 * `[...asr, ...mt]` cho panel §4.8; nếu màn này cũng truyền ASR xuống thì client gửi một id
 * ASR và backend từ chối **422** — `routes_translations.py::create_translation`:
 * *"engine không phải engine dịch: … (kind='asr')"*. Lọc ở ĐÂY (một chiều), không ở `App`:
 * panel §4.8 CẦN cả ASR để nói cái gì còn chạy được.
 *
 * ⚠️ **KHÔNG tự áp `status === "done"` ở đây** (xem `macDinhId`), và **KHÔNG tự chọn bản
 * `done` mới nhất**: quyết định đó là của `App` (một chỗ, truyền xuống).
 *
 * ── DẢI CHỌN BẢN DỊCH RỜI KHỎI THANH CÔNG CỤ (nút xoá bản dịch) ─────────────────────
 *
 * Mỗi bản dịch có thêm một nút XOÁ hai bước (`NutXoa`). Chỗ đặt nó là một quyết định hình
 * thức, và lý do là một phép ĐO chứ không phải thẩm mỹ:
 *
 * * Nhét nút xoá vào đúng chip bản dịch trong `.cmp__thanh` ⇒ mỗi bản dịch thêm HAI phần tử
 *   vào thanh công cụ, cùng chỗ với ô chọn engine, nút "dịch", chip `◆ CHIMERA` và nút ghim.
 *   Với vài bản dịch, thanh đó tràn ngang và **chip CHIMERA bị đẩy ra ngoài `clientWidth`** —
 *   người dùng mất luôn đường vào chế độ Chimera mà không có dấu hiệu nào cho biết nó còn
 *   tồn tại.
 * * Vì vậy dải chọn bản dịch thành MỘT HÀNG RIÊNG của lưới `.cmp` (`.cmp__bans`, hàng 2),
 *   mỗi bản một dòng `bản dịch #N · engine · status` + `[xóa]`. Thanh công cụ vì thế KHÔNG
 *   mọc thêm phần tử nào — nó còn BỚT đi N chip.
 * * `getBoundingClientRect()`/`scrollWidth` là phép đo của TRÌNH DUYỆT THẬT; jsdom không có
 *   layout, nên bài ghim trong `CompareScreen.test.tsx` chỉ khẳng định được SỰ HIỆN DIỆN +
 *   THỨ TỰ + LỚP của chip CHIMERA và dải chi phí (xem bài `HINH THUC (XOÁ)`), không khẳng
 *   định được "không tràn". Một khẳng định về tràn ngang chỉ đứng vững khi đo trên Chrome
 *   thật — đừng thay nó bằng một `assert` trong jsdom.
 *
 * Nút xoá KHÔNG gọi API: `onXoa` là của `App` (gọi `DELETE /api/translations/{id}` rồi
 * `translations.reload()`), cùng khuôn "màn không tự `fetch`" của cả file này.
 */
import { useEffect, useState } from "react";

import type {
  ChimeraCost,
  ChimeraRun,
  EngineSpec,
  Job,
  JobState,
  TranslationDetail,
  Transcript,
} from "../api/types.ts";
import { EngineSelect } from "../shell/EngineSelect.tsx";
import { NutXoa } from "../ui/NutXoa.tsx";
import { KhungRong } from "../ui/TrangRong.tsx";

interface Props {
  /** Bản ghi đang mở; `null` = chưa chọn kênh (trạng thái THẬT của app hôm nay). */
  transcript: Transcript | null;
  /** Bản dịch của bản ghi đó, ĐÃ kèm `segments` + `cps` (`TranslationDetail`). */
  translations: TranslationDetail[];
  /**
   * Bản dịch MẶC ĐỊNH khi người dùng CHƯA tự chọn — quyết định của BÊN GỌI.
   *
   * ⚠️ Vì sao nó là một PROP chứ không phải một `useState(translations[0]?.id ?? null)`:
   * "bản dịch đang xem" có HAI người trả lời trong cùng một màn (`Transport` xuất bản
   * `chonTranslation` = `done` mới nhất, còn màn này lấy `translations[0]` theo VỊ TRÍ MẢNG)
   * ⇒ người dùng xuất bản 11 trong khi đang đọc bản 12 rỗng, và **không** câu nào nói vì sao
   * (đo được: cột phải `["","",""]`, CPS `["—CPS","—CPS","—CPS"]`, `SAME = false`; review W1 §B(8)).
   *
   * ⚠️ **VÀ KHÔNG được tự áp `status === "done"` ở đây.** Làm thế là CHÉP LẠI `chonTranslation`
   * (`state/channelData.ts`) — hai bản cài đặt của MỘT quy ước, tức nguồn sự thật thứ hai, và
   * lỗi quay lại ngay lần sau ai đó đổi quy ước. `App` là nơi DUY NHẤT đọc `/api/translations`,
   * nên nó trả lời MỘT lần rồi đưa CÙNG câu trả lời cho `Transport` VÀ màn này: khi đó hai vùng
   * KHÔNG THỂ nói khác nhau — đó là một BẤT BIẾN, không phải một sự trùng hợp.
   *
   * Vẫn là FALLBACK (không phải giá trị khởi tạo của state): prop đổi thì lựa chọn chưa-có-chủ
   * đi theo, còn lựa chọn người dùng đã bấm thì được tôn trọng.
   */
  macDinhId?: number | null;
  /**
   * MỌI spec của `/api/registry` (đã gộp `asr` + `mt`) — màn LỌC `kind === "mt"` rồi đưa
   * xuống `EngineSelect` (nó lọc tiếp `available === true`, luật của Task 10).
   */
  specs?: EngineSpec[];
  /**
   * Tạo một bản dịch cho bản ghi đang mở. **CỦA `App`** — màn này KHÔNG tự gọi API (cùng
   * khuôn với mọi màn khác của giai đoạn: dữ liệu vào qua PROP, một chỗ gọi API cho mỗi màn).
   */
  onTaoBanDich?: (engine: string) => void;
  /**
   * Người dùng bấm một bản dịch khác trong segmented control — **BÁO LÊN `App`**.
   *
   * ⚠️ VI SAO PHẢI BÁO LÊN (vòng sửa W3 #1, bất biến `I2` — ERRATA #36 mục 4): `chonId` là
   * state CỤC BỘ, nên khi người dùng đổi bản thì VÙNG NÀY đổi theo nhưng `App.banDangXemId`
   * thì không (nó vẫn ưu tiên bản VỪA TẠO). ĐO ĐƯỢC: chọn bản 12 (`queued`, KHÔNG có job) sau
   * khi tạo bản 13 ⇒ cột phải của bản 12 hiện `"đang dịch… · job: chờ gom lô"` — job CỦA BẢN 13
   * — và ba nút XUẤT cũng trỏ bản 13. Không có prop này thì "một điểm quyết định" là một lời
   * tuyên bố SAI: có hai điểm, một ở `App` và một ở đây.
   */
  onChonBanDich?: (id: number) => void;
  /**
   * Job `dub` GẦN NHẤT của bản dịch đang chọn, hoặc `null` nếu chưa lồng lần nào.
   *
   * Vì sao là PROP chứ không tự fetch: `App` đã có `jobs` (một lần đọc `/api/jobs` + SSE) —
   * màn này đọc thêm một lần nữa là hai nguồn cho cùng câu "job lồng tiếng tới đâu rồi".
   */
  dubJob?: Job | null;
  /**
   * Xếp một job lồng tiếng cho bản dịch đang chọn. `voice = null` = giọng mặc định của engine.
   * KHÔNG truyền prop này ⇒ khối lồng tiếng không render (màn chỉ-đọc).
   */
  onLongTieng?: (voice: string | null) => void;
  /** Lỗi của lần xếp job lồng tiếng — **NGUYÊN VĂN `ApiError.message`** (404/409 tiếng Việt). */
  loiLongTieng?: string | null;
  /** Lời gọi tạo bản dịch đang bay ⇒ nút không cho bấm lần thứ hai. */
  dangTao?: boolean;
  /**
   * Lỗi của lần tạo gần nhất — **NGUYÊN VĂN `ApiError.message`**.
   *
   * ⚠️ Backend TỪ CHỐI TRƯỚC KHI GHI (409 "engine chưa sẵn sàng", 422 "engine không phải
   * engine dịch") và câu của nó đã là tiếng Việt ⇒ UI **không được đoán thay backend** và
   * **không được thay bằng một chữ chung**: người dùng cần đúng câu nói vì sao.
   */
  loiTao?: string | null;
  /**
   * Trạng thái JOB `translate` của bản dịch VỪA tạo (`TranslationCreated.job.state`).
   *
   * Chỉ có sau khi tạo: nó là thứ duy nhất biết job đang `queued` hay `running`, và nó đến từ
   * HTTP (`POST /api/translations` trả `{translation, job}`). ⚠️ KHÔNG dựng thanh tiến trình
   * thứ hai: tiến trình THẬT nằm ở job/SSE và `useJobStream` đã hiện nó ở vùng HÀNG ĐỢI.
   */
  trangThaiJob?: JobState | null;
  /**
   * CHẾ ĐỘ CHIMERA ĐANG BẬT (§4.5). Là state của `App`, không phải của màn này —
   * cùng khuôn với `macDinhId`: màn chỉ BAO, `App` quyết định, vì `App` là nơi gọi
   * `POST /api/translations` và cờ này đi vào body đó.
   */
  chimera?: boolean;
  /** Người dùng bấm chip ⇒ BÁO LÊN `App`. Màn không tự lật cờ. */
  onChimeraChange?: (bat: boolean) => void;
  /**
   * CẢNH BÁO CHI PHÍ đã đọc (`GET /api/chimera/cost`), `null` = chưa có.
   *
   * ⚠️ Màn này KHÔNG tự gọi endpoint đó — cùng luật với mọi màn khác của dự án
   * ("một chỗ gọi API cho mỗi màn"): `App` đọc, màn hiện.
   */
  chiPhi?: ChimeraCost | null;
  /** Lời gọi đang bay ⇒ dải hiện trạng thái ĐANG ĐO (khung khớp bố cục, không spinner). */
  dangDocChiPhi?: boolean;
  /** Lỗi của lần đọc — NGUYÊN VĂN `ApiError.message`; UI không được đoán thay backend. */
  loiChiPhi?: string | null;
  /**
   * XOÁ MỘT BẢN DỊCH — **của `App`**: nó gọi `DELETE /api/translations/{id}` rồi
   * `translations.reload()`, nên danh sách mới là của MÁY CHỦ, không phải một bản
   * cục bộ đã cắt tay.
   *
   * ⚠️ Trả `Promise` vì nút xoá hai bước phải nói ra `đang xóa…` và lỗi NGUYÊN
   * VĂN của backend (`NutXoa`) — 409 `job #k đang xếp hàng` là câu người dùng cần
   * đọc để biết phải huỷ job nào.
   *
   * `undefined` ⇒ không có nút xoá nào: đó là trạng thái của nơi dựng màn này chỉ
   * để ĐỌC (bài test cũ, hoặc vỏ chưa nối đường xoá).
   */
  onXoa?: (id: number) => Promise<void>;
}

/**
 * Trạng thái của MỘT bản dịch, nói ra bằng chữ — không suy từ `segments.length`.
 *
 * `TranslationStatus` là dữ liệu của backend (`routes_translations`), nên bản dịch `queued`
 * mà danh sách trả về vẫn nói đúng nó đang xếp hàng; `status` KHÔNG phải thứ client tự đoán.
 */
function chuTrangThai(trangThai: TranslationDetail["status"]): string {
  switch (trangThai) {
    case "queued":
      return "đang dịch…";
    case "running":
      return "đang dịch…";
    case "failed":
      return "dịch lỗi";
    case "cancelled":
      return "đã huỷ";
    case "done":
      // `done` mà đoạn này vẫn trống: bản dịch thiếu đoạn đó (lệch số đoạn) — nói SỰ THẬT,
      // đừng im lặng để người đọc tưởng ô trống là "chưa tải xong".
      return "chưa có đoạn này";
  }
}

/** Trạng thái JOB, nói ra bằng chữ — đến từ `TranslationCreated.job.state`. */
function chuTrangThaiJob(trangThai: JobState): string {
  switch (trangThai) {
    case "queued":
      return "chờ gom lô";
    case "running":
      return "đang chạy";
    case "done":
      return "xong";
    case "failed":
      return "lỗi";
    case "interrupted":
      return "bị ngắt";
    case "cancelled":
      return "đã huỷ";
  }
}

/** Một khoảng thời gian, đơn vị giây; `null` = KHÔNG ĐO ĐƯỢC (`—`, không phải `0,0s`). */
function giay(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Một số token; `null` = engine không báo (OPUS-MT chạy trong tiến trình). */
function token(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : String(n);
}

/**
 * Số token của một bản dịch, nối vào nhãn — chuỗi RỖNG khi không ĐO ĐƯỢC.
 *
 * Chỉ hiện khi CÓ CẢ HAI số: `engine in-process` (OPUS-MT) không báo token nào, và một nửa
 * (`1956→—`) là hình dạng mà người đọc phải tự diễn giải. Hai số đều thiếu thì im lặng, y như
 * nhãn cũ — không `0`, không `—`.
 *
 * Dạng `vào→ra` là dạng ĐÃ có trong khối chi phí Chimera (§4.5: `256→110 token`), nên người
 * đọc gặp cùng một thứ tự ở cả hai chỗ.
 */
function soToken(tr: Pick<TranslationDetail, "tokens_in" | "tokens_out">): string {
  const vao = tr.tokens_in;
  const ra = tr.tokens_out;
  if (typeof vao !== "number" || typeof ra !== "number") return "";
  return ` · ${token(vao)}→${token(ra)} token`;
}

/**
 * Chi phí ƯỚC LƯỢNG của một bản dịch — `null` = KHÔNG TÍNH ĐƯỢC, và khi đó trả chuỗi RỖNG.
 *
 * Rỗng chứ không phải `$0,000`: engine chạy trên máy này (OPUS-MT, Ollama) không có giá dịch
 * vụ, và `translations.tokens_in` của nó là `null` — hiện `$0,000` là nói hai điều sai cùng
 * lúc ("đã đo" + "miễn phí"). Tiền tố `~` vì đây là token ĐÃ ĐO × giá ĐÃ KHAI, không phải
 * hoá đơn; cùng luật với khối chi phí Chimera.
 *
 * Bốn chữ số thập phân khi dưới 1 xu: một lô 5 đoạn tốn ~$0,0002, và `toFixed(3)` sẽ làm nó
 * thành `$0,000` — tức một con số trông như không tốn gì.
 */
function chiPhiUsd(v: number | null | undefined): string {
  if (typeof v !== "number") return "";
  const so = v < 0.01 ? v.toFixed(4) : v.toFixed(3);
  return ` · ~$${so.replace(".", ",")}`;
}

/**
 * Tên các ENGINE không chạy được, KHÔNG trùng — vế "nói rõ cái thiếu" của §4.5.
 *
 * Trả về ENGINE chứ không phải ứng viên: ba ứng viên cùng thiếu `qwen2.5-7b` phải
 * hiện một lần. Đây là điều người dùng cần biết để sửa (`ollama pull` cái gì).
 */
function engineThieu(chiPhi: ChimeraCost): string[] {
  return [...new Set(chiPhi.candidates.filter((c) => !c.available).map((c) => c.engine))];
}

/** Cảnh báo CHẤT LƯỢNG đã khai của các ứng viên — đi KÈM cảnh báo chi phí. */
function canhBaoChatLuong(chiPhi: ChimeraCost): { engine: string; note: string }[] {
  const ra: { engine: string; note: string }[] = [];
  for (const c of chiPhi.candidates) {
    if (c.quality_note === null) continue;
    if (ra.some((x) => x.engine === c.engine)) continue;
    ra.push({ engine: c.engine, note: c.quality_note });
  }
  return ra;
}

/** Cột phải của một đoạn CHƯA có chữ dịch: trạng thái của bản dịch + trạng thái JOB (nếu có). */
function chuODichTrong(ban: TranslationDetail, trangThaiJob: JobState | null): string {
  const job = trangThaiJob === null ? "" : ` · job: ${chuTrangThaiJob(trangThaiJob)}`;
  return `${chuTrangThai(ban.status)}${job}`;
}

/** Cột nào đang được chọn làm bản A (bản dịch hiện ở cột phải). */
export function CompareScreen({
  transcript,
  translations,
  macDinhId = null,
  specs = [],
  onTaoBanDich,
  onChonBanDich,
  dubJob = null,
  onLongTieng,
  loiLongTieng = null,
  dangTao = false,
  loiTao = null,
  trangThaiJob = null,
  chimera = false,
  onChimeraChange,
  chiPhi = null,
  dangDocChiPhi = false,
  loiChiPhi = null,
  onXoa,
}: Props) {
  const [chonId, datChonId] = useState<number | null>(null);
  // Giong doc cho luot long tieng: chuoi RONG = de engine dung giong mac dinh.
  const [giong, datGiong] = useState("");
  const [ghim, datGhim] = useState(false);
  // ENGINE ĐANG CHỌN là state CỤC BỘ của màn này: `App` không cần biết nó cho tới lúc bấm
  // "dịch" (khi đó `onTaoBanDich(engine)` mang nó lên). Giữ nó ở đây là một chỗ, không hai.
  const [engine, datEngine] = useState("");

  // ⚠️ ENGINE DỊCH = `kind === "mt"`. Xem khối đầu tệp: backend trả **422** cho một engine
  // ASR (`routes_translations.py`, nhánh `spec.kind != "mt"`), nên ASR KHÔNG được xuống đây.
  const specsMt = specs.filter((s) => s.kind === "mt");
  // `available === true` là luật CỦA `EngineSelect` (Task 10) — màn này KHÔNG đọc lại khoá đó
  // để quyết định, nó chỉ cần biết có lựa chọn nào không (để chọn sẵn cái đầu tiên).
  const dungDuoc = specsMt.filter((s) => s.capabilities.available === true);
  const khoaDungDuoc = dungDuoc.map((s) => s.id).join(",");

  // Chọn sẵn engine MT dùng được ĐẦU TIÊN (một `<select>` không có lựa chọn hợp lệ là một ô
  // trống), và bỏ lựa chọn cũ khi nó không còn dùng được. Phụ thuộc là CHUỖI ID đã join, không
  // phải mảng: mảng là đối tượng mới ở mỗi lần render ⇒ effect chạy lại vô ích.
  useEffect(() => {
    const dung = khoaDungDuoc === "" ? [] : khoaDungDuoc.split(",");
    if (!dung.includes(engine)) datEngine(dung[0] ?? "");
  }, [khoaDungDuoc, engine]);

  if (transcript === null) {
    // 🔴 CÂU SAI SAU W1 — SỬA Ở ĐÂY. Bản cũ viết *"Vùng KÊNH chưa có đường chọn bản ghi, nên chưa
    // có gì để đối chiếu."* — **SAI**. W1 đã nối `selectChannel` vào TỪNG mục của vùng KÊNH
    // (`ChannelZone.tsx`: mỗi `.ch__item` là một `<button>` gọi `onSelect(id)`), nên KÊNH **CHỌN
    // ĐƯỢC RỒI**. Cái còn thiếu KHÔNG phải một đường — nó là một LƯỢT CHỌN của người dùng. Câu cũ
    // nói ngược sự thật và đẩy người đọc đi tìm một tính năng đã có.
    //
    // Câu mới nói ĐÚNG hai vế và là một MỆNH LỆNH, không phải một lời báo trạng thái:
    //   (a) chưa chọn kênh nào — sự thật của lượt này;
    //   (b) chọn Ở ĐÂU — vùng KÊNH bên trái, và chọn xong thì bản ghi mở ra.
    // ⚠️ `data-testid="rong"` và lớp `cmp__rong` GIỮ NGUYÊN: đó là hai chỗ neo của bài ghim.
    return (
      <section className="cmp">
        <KhungRong
          className="cmp__rong"
          testid="rong"
          kicker="CHƯA CHỌN"
          lenh="Chưa chọn kênh — bấm một kênh ở vùng KÊNH bên trái để mở bản ghi, rồi đối chiếu."
        />
      </section>
    );
  }

  // Bản A: id người dùng ĐÃ CHỌN (nếu còn trong danh sách), rồi tới quyết định của BÊN GỌI
  // (`macDinhId` — cùng câu trả lời mà `Transport` dùng để xuất), rồi mới tới hàng đầu.
  // `find` trả `undefined` khi prop đổi và id cũ trỏ vào hư không — đó là lý do phải kiểm.
  // ⚠️ `chonId` là state CỤC BỘ chỉ để ý ĐỊNH ngay trong lượt bấm; SỰ THẬT vẫn được báo lên
  // `App` qua `onChonBanDich`, và `App` trả lại qua `macDinhId` (xem prop `onChonBanDich`).
  const chon =
    translations.find((tr) => tr.id === chonId) ??
    translations.find((tr) => tr.id === macDinhId) ??
    translations[0] ??
    null;
  // Bản B: bản KHÁC bản A. Ghim chính bản đang chọn là so một hàng với chính nó
  // (`reducer.pinB` từ chối đúng ca đó) — ở đây đơn giản là không có gì để ghim.
  const ghimBan = ghim ? translations.find((tr) => tr.id !== chon?.id) ?? null : null;
  const dub = dubJob ?? null;

  // DẤU VẾT CHIMERA của bản đang xem (§4.5). `null` = bản dịch thường ⇒ KHÔNG có
  // ngăn ứng viên nào, và đó là một trạng thái KHÁC hẳn "có chạy mà chưa có dữ liệu".
  const chimeraRun: ChimeraRun | null = chon?.chimera ?? null;
  // Chữ của TỪNG ứng viên theo `Segment.i`, dựng MỘT lần cho cả danh sách: tra trong
  // mảng `segments` của mỗi ứng viên ở từng dòng là O(số_dòng × số_ứng_viên × số_đoạn).
  const uvTheoI = (chimeraRun?.candidates ?? []).map(
    (c) => new Map(c.segments.map((s) => [s.i, s.text])),
  );

  const dichTheoI = new Map((chon?.segments ?? []).map((s) => [s.i, s]));
  const cpsTheoI = new Map((chon?.cps.rows ?? []).map((r) => [r.i, r]));
  const ghimTheoI = new Map((ghimBan?.segments ?? []).map((s) => [s.i, s]));

  // CỬA VÀO "BẮT ĐẦU DỊCH" — MỘT nút, `disabled` khi không có engine MT nào dùng được HOẶC
  // khi lời gọi trước còn đang bay. Nhãn đổi theo việc ĐÃ có bản dịch hay chưa (trạng thái
  // rỗng phải có CÒ), nhưng vẫn là CÙNG một phần tử: một cửa vào, không phải hai.
  const coBanDich = translations.length > 0;
  const nutDich = (
    <span className="cmp__tao">
      <EngineSelect specs={specsMt} value={engine} onValueChange={datEngine} />
      <button
        type="button"
        className="cmp__nut-dich"
        data-testid="tao-ban-dich"
        disabled={dungDuoc.length === 0 || dangTao}
        onClick={() => {
          if (onTaoBanDich !== undefined) onTaoBanDich(engine);
        }}
      >
        {dangTao ? "đang xếp…" : coBanDich ? "+ bản dịch mới" : "dịch"}
      </button>
    </span>
  );

  return (
    <section className="cmp">
      {/* THANH CÔNG CỤ — hàng 1 của lưới `.cmp`. BỐN điều khiển CỐ ĐỊNH: ô chọn engine,
          nút "dịch", chip CHIMERA, nút ghim. ⚠️ Dải chọn bản dịch KHÔNG còn ở đây (nó ở
          `.cmp__bans`, hàng 2): mỗi bản dịch thêm một nút xoá, nên nhét chúng vào thanh này
          sẽ đẩy chip CHIMERA ra ngoài vùng nhìn thấy — một điều khiển không thấy được là
          một điều khiển mất tích (xem `app.css` `.cmp__bans`). */}
      <div className="cmp__thanh">
        {coBanDich ? nutDich : null}
        {/* §4.5 NGUYÊN VĂN: *"Bật bằng chip amber trên thanh công cụ."* Chip này là
            CÙNG một phần tử ở cả hai trạng thái (bật/tắt) — `aria-pressed` là thứ nói
            trạng thái, không phải việc nó biến mất khi tắt. `--signal` chỉ có MỘT
            nghĩa (đang hoạt động), nên chip bật mới được viền amber. */}
        <button
          type="button"
          className="cmp__chimera-chip"
          data-testid="chimera-chip"
          aria-pressed={chimera}
          onClick={() => {
            if (onChimeraChange !== undefined) onChimeraChange(!chimera);
          }}
        >
          ◆ CHIMERA
        </button>
        <button
          type="button"
          className="cmp__ghim"
          data-testid="ghim"
          aria-pressed={ghimBan !== null}
          // Một bản dịch thì không có "bản B" nào để ghim: nút VÔ HIỆU thay vì im lặng
          // làm một việc không có kết quả.
          disabled={translations.length < 2}
          onClick={() => datGhim((cu) => !cu)}
        >
          Ghim bản B
        </button>
      </div>

      {/* DẢI CHỌN BẢN DỊCH — hàng 2: mỗi bản dịch MỘT DÒNG `bản dịch #N · engine · status`
          (nút chọn) + nút XOÁ hai bước cạnh nó. Hai nút là ANH EM, không lồng nhau:
          `<button>` KHÔNG được chứa `<button>` (trình duyệt tự đóng thẻ ngoài ⇒ DOM thật
          khác JSX, và cú bấm rơi vào phần tử khác).
          MỌI trạng thái của bước xoá NÓI RA bằng chữ (`xóa` → `xóa?` + `hủy` → `đang xóa…`,
          và lỗi là NGUYÊN VĂN `ApiError.message`) — không chỉ bằng màu. */}
      <div className="cmp__bans" role="radiogroup" aria-label="Bản dịch">
        {translations.map((tr) => (
          <div key={tr.id} className="cmp__ban">
            <button
              type="button"
              role="radio"
              aria-checked={tr.id === chon?.id}
              className="cmp__chon"
              data-testid={`pick-${tr.id}`}
              data-stale={String(tr.stale)}
              onClick={() => {
                datChonId(tr.id);
                // BÁO LÊN `App`: lựa chọn này phải trở thành `banDangXemId` (xem prop
                // `onChonBanDich`), nếu không thì `Transport` và nhãn job vẫn bám bản VỪA TẠO.
                if (onChonBanDich !== undefined) onChonBanDich(tr.id);
              }}
            >
              {/* NHÃN BỀN (D2) — KHÔNG đánh số theo VỊ TRÍ MẢNG.
                  ĐO ĐƯỢC TRƯỚC (ảnh chụp thật, ERRATA #41 mục 3a): nhãn cũ là `bản dịch {k + 1} ·
                  {engine}`, tức DANH TÍNH của một bản dịch là CHỖ ĐỨNG của nó trong mảng — thêm/bớt
                  một bản dịch là mọi nhãn sau đổi số, và cùng một bản dịch mang hai tên khác nhau ở
                  hai lần đọc. Nay danh tính lấy từ CHÍNH DỮ LIỆU CỦA HÀNG: `id` (duy nhất), `engine`
                  và `status` (đều của máy chủ).
                  CHI PHÍ nối vào CUỐI nhãn và để RỖNG khi không tính được: đây là câu trả lời cho
                  "engine này tốn bao nhiêu" — thứ người dùng cần để chọn engine — và nó phải đứng
                  cạnh tên engine, không phải trong một khối riêng phải bấm mới thấy. */}
              {`bản dịch #${tr.id} · ${tr.engine} · ${tr.status}${tr.stale ? " · lỗi thời" : ""}${soToken(tr)}${chiPhiUsd(tr.cost_usd)}`}
            </button>
            {onXoa === undefined ? null : (
              <NutXoa
                doiTuong={`bản dịch #${tr.id}`}
                className="cmp__xoa"
                classNameLoi="cmp__xoa-loi"
                testid={`xoa-ban-${tr.id}`}
                onXoa={() => onXoa(tr.id)}
              />
            )}
          </div>
        ))}
      </div>
        {/* LỒNG TIẾNG — nằm TRONG danh sách bản dịch nên KHÔNG thêm con cho lưới `.cmp`
            (mỗi con của lưới có `grid-row` tường minh — xem test hình thức). Bốn trạng thái,
            mỗi trạng thái NÓI BẰNG CHỮ: chưa lồng → nút; đang chạy → `đang lồng tiếng… N%`;
            xong → năm đường tải (dựng từ id, không cần thêm route trạng thái); lỗi → NGUYÊN VĂN
            `job.error` của backend (409/422 của nó đã là tiếng Việt và nêu đúng việc phải làm). */}
        {onLongTieng === undefined || chon === null ? null : (
          <div className="dub" data-testid="dub-khoi">
            <span className="nhan">Lồng tiếng</span>
            {dub === null ? (
              <>
                <input className="dub__giong" type="text" value={giong}
                  placeholder="giọng (bỏ trống = mặc định)"
                  aria-label="giọng đọc cho lượt lồng tiếng"
                  onChange={(e) => datGiong(e.target.value)} />
                <button type="button" className="dub__nut" data-testid="dub-nut"
                  onClick={() => onLongTieng(giong.trim() === "" ? null : giong.trim())}>
                  lồng tiếng
                </button>
              </>
            ) : dub.state === "queued" || dub.state === "running" ? (
              <span className="dub__tin" data-testid="dub-dang-chay">
                {dub.state === "queued" ? "chờ tới lượt" : "đang lồng tiếng…"}{" "}
                {Math.round(dub.progress * 100)}%
              </span>
            ) : dub.state === "done" ? (
              <span className="dub__tai" data-testid="dub-tai">
                đã có · tải:
                {["wav", "mp3", "aac", "m4a", "flac"].map((dinhDang) => (
                  <a key={dinhDang} className="dub__nut-tai"
                    data-testid={`dub-tai-${dinhDang}`}
                    href={`/api/dubs/${chon.id}/download?format=${dinhDang}`} download>
                    {dinhDang}
                  </a>
                ))}
              </span>
            ) : (
              <span className="dub__loi" data-testid="dub-loi">{dub.error ?? dub.state}</span>
            )}
            {loiLongTieng === null ? null : (
              <span className="dub__loi" data-testid="dub-loi-tao">{loiLongTieng}</span>
            )}
          </div>
        )}

      {/* §4.5 NGUYÊN VĂN: *"Dải cảnh báo chéo chạy ngang"*, và `app.css` khai **BẢY**
          track cho `.cmp` (`auto auto auto auto auto auto 1fr`) với `grid-row` tường minh
          cho MỌI con: `.cmp__thanh` 1 · `.cmp__bans` 2 · `.cmp__chi-phi` 3 ·
          `.cmp__tin` 4 · `.cmp__nguong`/`.cmp__rong` 5 · `.cmp__dau` 6 ·
          `.cmp__danh-sach` 7 (hàng `1fr` DUY NHẤT — chỗ cuộn). Đây là ERRATA #31 mục 1:
          thêm một con vào lưới có `grid-template-rows` cố định mà không khai track +
          `grid-row` là một lỗi IM LẶNG (đã sai ba lần trong dự án này). `.cmp__bans` là con
          MỚI của lưới này (dải chọn bản dịch, tách khỏi thanh công cụ) và nó lấy hàng 2, nên
          MỌI hàng phía dưới dời xuống MỘT bậc — con số ở trên là con số ĐANG CHẠY, không phải
          con số cũ.
          Chi phí hiện TRƯỚC khi bấm là điều kiện để chế độ này dùng được: `estimate` là
          số ĐO ĐƯỢC từ một bản dịch thật đã chạy xong, và `null` là câu trả lời hợp lệ
          ("chưa đo được") — KHÔNG bịa một con số. */}
      {chimera ? (
        <div className="cmp__chi-phi" data-testid="chimera-chi-phi">
          {loiChiPhi !== null ? (
            <p data-testid="chimera-loi">{loiChiPhi}</p>
          ) : chiPhi === null ? (
            dangDocChiPhi ? (
              <p data-testid="chimera-dang-do">
                <span className="cmp__cp-ky">◆</span> CHẾ ĐỘ CHIMERA · đang đo chi phí…
                (đọc <code>GET /api/chimera/cost</code>)
              </p>
            ) : null
          ) : (
            <>
              <p data-testid="chimera-mot-lan">
                <span className="cmp__cp-ky">◆</span> CHẾ ĐỘ CHIMERA ·{" "}
                {chiPhi.calls_per_batch} lượt gọi model cho mỗi lô · chậm ~
                {chiPhi.multiplier}× · VRAM không tăng (chạy tuần tự)
              </p>
              <p data-testid="chimera-so-ung-vien">
                {chiPhi.runnable}/{chiPhi.declared} ứng viên chạy được NGAY BÂY GIỜ · engine
                pha <code>{chiPhi.merge_engine}</code>
              </p>
              {engineThieu(chiPhi).length === 0 ? null : (
                <p data-testid="chimera-thieu">
                  thiếu: {engineThieu(chiPhi).join(", ")} — model chưa được pull, hoặc
                  runtime không phục vụ được
                </p>
              )}
              <p data-testid="chimera-uoc-luong">
                {chiPhi.estimate === null ? (
                  <>
                    {chiPhi.estimate_basis}
                    {chiPhi.estimate_hint ? ` ${chiPhi.estimate_hint}` : ""}
                  </>
                ) : (
                  <>
                    ước lượng:{" "}
                    <span className="cmp__cp-so">{giay(chiPhi.estimate.duration_ms)}</span>{" "}
                    · <span className="cmp__cp-so">{token(chiPhi.estimate.tokens_in)}</span>
                    {"→"}
                    <span className="cmp__cp-so">{token(chiPhi.estimate.tokens_out)}</span>{" "}
                    token · {chiPhi.estimate_basis}
                  </>
                )}
              </p>
              {/* Cảnh báo CHẤT LƯỢNG đi KÈM cảnh báo chi phí: một ứng viên đã đo được là
                  chép nguyên nguồn thì gọi nó thêm năm lần không làm bản dịch tốt hơn. */}
              {canhBaoChatLuong(chiPhi).map((cb) => (
                <p key={cb.engine} data-testid={`chimera-chat-luong-${cb.engine}`}>
                  ⚠ chất lượng · {cb.engine}: {cb.note}
                </p>
              ))}
            </>
          )}
        </div>
      ) : null}

      {/* ⚠️ KHÔNG CÓ ENGINE MT NÀO DÙNG ĐƯỢC ⇒ nút VÔ HIỆU **và** một câu nói RÕ vì sao +
          cách sửa. Bài học §4.8 / ERRATA #30: đổi màu là KHÔNG ĐỦ — người dùng không được
          đoán. `available === true` là thuận tiện của client; **backend mới là thẩm quyền**
          (nó trả 409 nếu engine chưa sẵn sàng), nên lỗi của backend ở dưới vẫn phải hiện.
          ⚠️ Hai nhánh dưới đây nằm TRONG một `div` `.cmp__tin` — MỘT con của lưới `.cmp`
          (hàng 4), chứ không phải hai con rời. `app.css` khai **BẢY** track cho `.cmp`
          (`grid-template-rows: auto auto auto auto auto auto 1fr`) và MỖI con có `grid-row`
          tường minh: `.cmp__thanh` 1 · `.cmp__bans` 2 · `.cmp__chi-phi` 3 · `.cmp__tin` 4
          (co lại khi `:empty`) · `.cmp__nguong`/`.cmp__rong` 5 · `.cmp__dau` 6 ·
          `.cmp__danh-sach` 7 (hàng `1fr` **DUY NHẤT** — chỗ cuộn).
          ĐÓNG LÝ DO CỦA KHỐI NÀY: nếu hai nhánh dưới là hai con RỜI thì chúng chiếm thêm hai
          hàng, và hàng `1fr` (chỗ cuộn của danh sách) rơi vào một trong hai nhánh đó — đúng
          lỗi `Critical` C1 của ERRATA #36 mục 3. ⚠️ Con số ở khối này TỪNG lệch với chính
          `app.css` (nói "BỐN con" khi CSS khai SÁU; rồi nói SÁU khi CSS khai BẢY): nó được
          sửa lại theo đúng số track ĐANG CHẠY khi `.cmp__bans` được thêm vào lưới — chú thích
          mâu thuẫn với mã nó giải thích là một lời khai sai. */}
      <div className="cmp__tin">
        {dungDuoc.length === 0 ? (
          <p className="cmp__ly-do-khong-dich" data-testid="ly-do-khong-dich">
            Không có engine dịch nào dùng được: mọi engine dịch trong registry đều có
            <code> available: false</code> — model chưa được pull, hoặc Ollama chưa chạy. Cách sửa:
            bật Ollama rồi <code>ollama pull</code> model của engine đó, sau đó tải lại trang.
          </p>
        ) : null}

        {/* LỖI CỦA BACKEND, NGUYÊN VĂN (`ApiError.message` = "<status>: <detail>"): backend từ
            chối TRƯỚC khi ghi, nên câu của nó là thứ duy nhất đúng — thay bằng "có lỗi xảy ra"
            là bỏ mất đúng thông tin người dùng cần để sửa. */}
        {loiTao === null ? null : (
          <p className="cmp__loi-tao" data-testid="loi-tao">{loiTao}</p>
        )}

        {coBanDich ? null : (
          <div className="cmp__cua" data-testid="cua-dich">
            <p className="cmp__cua-nhan">Bản ghi này chưa có bản dịch nào.</p>
            <p className="cmp__cua-phu">
              Chọn engine dịch rồi bấm "dịch" để bắt đầu. Cột NGUỒN bên dưới là dữ liệu thật.
            </p>
            {nutDich}
          </div>
        )}
      </div>

      {chon === null ? (
        <p className="cmp__rong" data-testid="chua-dich">
          Bản ghi này chưa có bản dịch nào. Cột NGUỒN bên dưới là dữ liệu thật.
        </p>
      ) : (
        <p className="cmp__nguong" data-testid="nguong">
          ngưỡng {chon.cps.max_cps} CPS · nguồn: {chon.cps.rows.length} đoạn đã đo
        </p>
      )}

      <div className={"cmp__dau" + (ghimBan !== null ? " is-pinned" : "")}>
        <span className="cmp__nhan">Nguồn</span>
        <span className="cmp__nhan">Bản dịch</span>
        <span className="cmp__nhan">CPS</span>
        {ghimBan !== null ? <span className="cmp__nhan">Bản B</span> : null}
      </div>

      <ol className={"cmp__danh-sach" + (ghimBan !== null ? " is-pinned" : "")}>
        {transcript.segments.map((seg) => {
          const cps = cpsTheoI.get(seg.i);
          const over = cps?.over === true;
          const chuDich = dichTheoI.get(seg.i)?.text;
          return (
            <li
              key={seg.i}
              className={"cmp__dong" + (over ? " is-over" : "")}
              data-testid={`row-${seg.i}`}
              data-over-cps={String(over)}
            >
              <span className="cmp__goc" data-testid="col-left">{seg.text}</span>
              {/* ⚠️ BẢN DỊCH `queued`/`running` CHƯA có đoạn nào ⇒ ô này KHÔNG được để RỖNG:
                  người dùng vừa bấm "dịch", một cột phải trống nghĩa là "app hỏng". Nói ra
                  TRẠNG THÁI của bản dịch + trạng thái JOB (dữ liệu thật), KHÔNG bịa % tiến
                  trình: tiến trình thật nằm ở job/SSE và vùng HÀNG ĐỢI đã hiện nó.
                  Đoạn ĐÃ dịch vẫn hiện CHỮ THẬT của nó — trạng thái không được nuốt chữ. */}
              <span className="cmp__dich" data-testid="col-right">
                {chuDich ?? (chon === null ? "" : chuODichTrong(chon, trangThaiJob))}
                {/* §4.5 NGUYÊN VĂN: *"Mỗi dòng đã xử lý được mở rộng: bản hợp nhất ở
                    trên (đánh ◆, kèm HỢP NHẤT TỪ 6 ỨNG VIÊN · hyp 3 · 1.4s), và 6 ứng
                    viên xếp chồng bên dưới, ứng viên được chọn sáng hơn."*
                    Bốn vế đều là DỮ LIỆU của máy chủ:
                      · `ran_count` — số ứng viên THẬT SỰ chạy, không phải số đã khai;
                      · `anchor_by_segment[i]` — `hyp` của dòng này, chỉ số 1-based
                        trong danh sách ĐÃ KHAI (backend tính, không suy ở client);
                      · `merge.duration_ms` — thời gian THẬT của lượt pha;
                      · `identical_segments` / `fallback_segments` — hai sự thật khó
                        nói nhất, và cả hai đều được NÓI RA thay vì im lặng.
                    `distinct_by_segment` là con số khiến "chế độ đắt gấp N" kiểm được:
                    `1` nghĩa là mọi ứng viên giống hệt nhau, tức lượt pha không có gì
                    để pha (ĐO ĐƯỢC: đúng vậy với bốn ứng viên qwen trên máy này). */}
                {chimeraRun === null ? null : (
                  <span className="cmp__uv-boc" data-testid={`ung-vien-${seg.i}`}>
                    <span className="cmp__hop-nhat" data-testid={`hop-nhat-${seg.i}`}>
                      ◆ HỢP NHẤT TỪ {chimeraRun.ran_count} ỨNG VIÊN · hyp{" "}
                      {chimeraRun.merge.anchor_by_segment[String(seg.i)] ?? "—"} ·{" "}
                      {giay(chimeraRun.merge.duration_ms)}
                      {chimeraRun.merge.fallback_segments.includes(seg.i) ? (
                        <span data-testid={`lui-${seg.i}`}> · lùi về mỏ neo</span>
                      ) : null}
                      {chimeraRun.merge.identical_segments?.includes(seg.i) ? (
                        <span data-testid={`khong-doi-${seg.i}`}>
                          {" "}· lượt pha không đổi gì so với mỏ neo
                        </span>
                      ) : null}
                      {chimeraRun.distinct_by_segment?.[String(seg.i)] === undefined ? null : (
                        <span data-testid={`khac-nhau-${seg.i}`}>
                          {" "}· {chimeraRun.distinct_by_segment[String(seg.i)]} bản khác nhau
                        </span>
                      )}
                    </span>
                    {chimeraRun.candidates.map((ungVien, k) => {
                      const duocChon =
                        (chimeraRun.merge.anchor_by_segment[String(seg.i)] ?? 0) === k + 1;
                      const chuUv = uvTheoI[k]?.get(seg.i);
                      return (
                        <span
                          key={ungVien.id}
                          className={"cmp__uv" + (duocChon ? " is-chon" : "")}
                          data-testid={`uv-${seg.i}-${ungVien.id}`}
                        >
                          <span className="cmp__uv-nhan">{ungVien.id}</span>
                          <span className="cmp__uv-chu">
                            {/* ⚠️ `skipped` là trạng thái LÚC LƯỢT CHẠY ĐÓ, còn dải
                                `chimera-so-ung-vien` ở trên là kế hoạch NGAY BÂY GIỜ.
                                Hai câu đúng ở hai thời điểm khác nhau, nên câu này phải
                                NÓI RA mốc của nó: đo được trên DB thật, dải ghi
                                "6/6 ứng viên chạy được" trong khi ô c6 của bản đang xem
                                ghi "engine chưa được pull" — người đọc thấy mâu thuẫn mà
                                không có gì giải thích. */}
                            {chuUv ??
                              (typeof ungVien.skipped === "string"
                                ? `trong lượt này: ${ungVien.skipped}`
                                : "không chạy")}
                          </span>
                        </span>
                      );
                    })}
                  </span>
                )}
              </span>
              <span className="cmp__cps" data-testid="col-cps">
                {cps === undefined || cps.cps === null ? "—" : cps.cps.toFixed(1)}
                {/* §4.3 NGUYÊN VĂN: "Dòng vượt ngưỡng đọc có `⚠` màu amber." Glyph này do
                    SPEC UI chỉ định làm dấu hiệu NỘI DUNG, không phải emoji trang trí ⇒ nó
                    thuộc NGOẠI LỆ của luật "không emoji" (ERRATA #19 mục 7: spec UI là nguồn
                    có thẩm quyền về HÌNH THỨC, và `grep -i emoji` trên spec = 0).
                    Màu amber đến từ `.cmp__dong.is-over .cmp__cps`; mốc amber ở lề +
                    `data-over-cps` GIỮ NGUYÊN vì chúng phục vụ TIẾP CẬN (§7) — glyph một mình
                    là tín hiệu chỉ-có-hình, không đọc được bằng screen reader. */}
                {over ? <span className="cmp__canh-bao">⚠</span> : null}
                <span className="cmp__don-vi">CPS</span>
              </span>
              {ghimBan !== null ? (
                <span className="cmp__ghim-cot" data-testid="col-pinned">
                  {ghimTheoI.get(seg.i)?.text ?? ""}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
