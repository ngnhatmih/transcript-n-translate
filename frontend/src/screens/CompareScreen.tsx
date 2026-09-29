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
 * ⚠️ TRẦN CỦA LƯỢT NÀY (`ponytail:`): trong app, `App` truyền `transcript={null}` và
 * `translations={[]}` vì chưa có đường CHỌN KÊNH, nên màn chỉ render TRẠNG THÁI RỖNG
 * NÓI THẬT. Mọi khẳng định về hai cột đến từ test truyền prop.
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
 */
import { useEffect, useState } from "react";

import type { EngineSpec, JobState, TranslationDetail, Transcript } from "../api/types.ts";
import { EngineSelect } from "../shell/EngineSelect.tsx";

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
  dangTao = false,
  loiTao = null,
  trangThaiJob = null,
}: Props) {
  const [chonId, datChonId] = useState<number | null>(null);
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
    // Trạng thái rỗng NÓI THẬT: không bịa một bản ghi nào để màn trông đầy đủ.
    return (
      <section className="cmp">
        <p className="cmp__rong" data-testid="rong">
          Chưa chọn kênh. Vùng KÊNH chưa có đường chọn bản ghi, nên chưa có gì để đối chiếu.
        </p>
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
      {/* Segmented control (U7: KHÔNG phải N tab) + nút ghim + CỬA VÀO "bắt đầu dịch". */}
      <div className="cmp__thanh" role="radiogroup" aria-label="Bản dịch">
        {translations.map((tr) => (
          <button
            key={tr.id}
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
                và `status` (đều của máy chủ). */}
            {`bản dịch #${tr.id} · ${tr.engine} · ${tr.status}${tr.stale ? " · lỗi thời" : ""}`}
          </button>
        ))}
        {coBanDich ? nutDich : null}
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

      {/* ⚠️ KHÔNG CÓ ENGINE MT NÀO DÙNG ĐƯỢC ⇒ nút VÔ HIỆU **và** một câu nói RÕ vì sao +
          cách sửa. Bài học §4.8 / ERRATA #30: đổi màu là KHÔNG ĐỦ — người dùng không được
          đoán. `available === true` là thuận tiện của client; **backend mới là thẩm quyền**
          (nó trả 409 nếu engine chưa sẵn sàng), nên lỗi của backend ở dưới vẫn phải hiện.
          ⚠️ Hai nhánh dưới đây nằm TRONG một `div` `.cmp__tin` — con THỨ NĂM của lưới `.cmp`,
          chứ không phải hai con rời. `app.css` khai **SÁU** track cho `.cmp`
          (`grid-template-rows: auto auto auto auto auto 1fr`) và MỖI con có `grid-row` tường
          minh: `.cmp__thanh` 1 · `.cmp__tin` 2 (co lại khi `:empty`) · `.cmp__nguong`/`.cmp__rong`
          3 · `.cmp__dau` 4 · `.cmp__danh-sach` 6 (hàng `1fr` **DUY NHẤT** — chỗ cuộn).
          ĐÓNG LÝ DO CỦA KHỐI NÀY: nếu hai nhánh dưới là hai con RỜI thì chúng là con thứ năm và
          thứ sáu, và hàng `1fr` (chỗ cuộn của danh sách) rơi vào một trong hai nhánh đó — đúng
          lỗi `Critical` C1 của ERRATA #36 mục 3. Khối chú thích này từng nói "BỐN con" khi
          `app.css` đã khai SÁU (đo được ở re-review W3 #1, `Minor` F3): chú thích mâu thuẫn với
          chính mã nó giải thích là một lời khai sai, nên nó được sửa cho khớp sự thật. */}
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
