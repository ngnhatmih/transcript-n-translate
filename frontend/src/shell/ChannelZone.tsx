/**
 * Vùng KÊNH (trái, 214px): "tôi đang có những tệp nào, cái nào xong bước nào?" — spec UI §3.
 *
 * Dữ liệu là `Source[]` THẬT từ `GET /api/sources` cộng BẢN ĐỒ JOB của `useJobStream`;
 * không có bản sao nào ở client, và không request riêng nào ở đây.
 *
 * ## Trạng thái từng bước — nối được tới đâu, và bằng gì
 *
 * ĐƯỜNG NỐI job → source là `job.payload.source_id`, và nó là HỢP ĐỒNG, không phải
 * suy đoán (đọc mã backend, kèm dòng):
 *   - `backend/app/api/routes_sources.py` `_enqueue_ingest` — job `ingest` với
 *     `payload={"source_id": source_id, "lang": lang}`.
 *   - `backend/app/pipeline/ingest.py` — job `asr` với `payload={"source_id": …, "lang": …}`
 *     (và chính nó ĐỌC `job.payload["source_id"]`).
 *   - `backend/app/api/routes_jobs.py` `_job_json` — `GET /api/jobs` TRẢ `payload`.
 *   - `IngestPayload`/`AsrPayload` trong cùng tệp: `source_id` là trường BẮT BUỘC.
 * Client đã có chỗ chứa từ trước: `types.ts::Job.payload: Record<string, unknown>`, và
 * `useJobStream` giữ nguyên `Job` từ ảnh chụp (sự kiện SSE chỉ ghi sáu khoá của nó).
 *
 * ## ĐƯỜNG CHỌN KÊNH (Task W1) — cái trước đây KHÔNG tồn tại
 *
 * Đo được trước W1: `selectChannel` **0 lượt dispatch** (chỉ có trong `reducer.ts` +
 * `reducer.test.ts`) ⇒ `ui.channelId` luôn `null` ⇒ `transcript={null}` ở MỌI màn, tức
 * **mọi màn chỉ hiện trạng thái rỗng** và thanh transport không có `src` (ERRATA #32).
 * W1 nối đúng một chỗ: mỗi mục là một NÚT gọi `onSelect(source.id)`; `App` biến nó thành
 * `dispatch({type:"selectChannel", id})`, và reducer xoá mọi vị trí gắn với kênh CŨ
 * (`reducer.ts` — đoạn đang phát / đang sửa / ghim bản B).
 *
 * ⚠️ Vùng này KHÔNG tự giữ "kênh đang chọn": `selectedId` là PROP. Một bản sao cục bộ sẽ
 * là nguồn sự thật thứ hai cho cùng một câu hỏi — và hai màn có thể nói hai chuyện khác nhau.
 *
 * ## `ponytail:` TRẦN — cái KHÔNG nối được, và vì sao
 *
 * 1. **Bước DỊCH không nối được ở Task 4.** Payload của job `translate` mang
 *    `translation_id`, không mang `source_id` (`backend/app/domain/models.py::translation_id_of`
 *    — docstring của nó nói payload là dấu nối DUY NHẤT, và id hai bảng không được đảm bảo
 *    trùng nhau). Đi tiếp `translation → transcript → source` cần danh sách
 *    transcript/translation, thứ Task 4 chưa đọc. ⇒ Vùng này hiện HAI bước đầu
 *    (`ingest`, `asr`), KHÔNG hiện bước dịch.
 * 2. **`GET /api/sources` không có khoá bước nào** (`_source_json` trả đúng tám khoá:
 *    `id, kind, origin, media_path, audio_path, duration, lang, created_at`) ⇒ mọi thứ về
 *    bước phải đến từ job, không được suy từ `duration`/`audio_path`.
 * 3. **NHIỀU job cho CÙNG một bước là chuyện thường** (chạy lại sau lỗi, hoặc một lần
 *    `asr` mới sau một lần xong). Nên "bước hiện tại" là một QUY ƯỚC, nói thẳng ra:
 *    **job có `id` LỚN NHẤT của mỗi bước là trạng thái HIỆN TẠI; job cũ hơn cùng bước là
 *    LỊCH SỬ và không được hiện.** Cơ sở: `jobs.id` là `INTEGER PRIMARY KEY`
 *    (`backend/app/adapters/persist/schema.py`), tức rowid, nên hàng chèn sau có id lớn hơn.
 *    Hệ quả ĐO ĐƯỢC của quy ước: một kênh có `asr` #3 `done` rồi `asr` #7 `running` hiện
 *    "phiên âm: đang chạy", KHÔNG hiện "xong" — và bài test ghim đúng điều đó.
 */
import type { Job, JobState, JobType, Source } from "../api/types.ts";
import { NhapGon } from "./IntakeFrame.tsx";
import type { NapTep } from "./IntakeFrame.tsx";

export interface ChannelZoneProps {
  /** `null` = chưa có dữ liệu (đang đọc, hoặc lỗi — xem `loading`/`error`). */
  sources: Source[] | null;
  /** Bản đồ job của `useJobStream` — nguồn duy nhất của trạng thái bước. */
  jobs: Map<number, Job>;
  loading: boolean;
  error: string | null;
  /**
   * Id kênh ĐANG CHỌN (`UiState.channelId`); `null` = chưa chọn kênh nào.
   *
   * ⚠️ Đây là PROP, không phải state cục bộ: nguồn sự thật của "kênh nào đang mở" nằm
   * trong MỘT chỗ (`state/reducer.ts`), và `Transport`/`EditScreen`/`CompareScreen` đọc
   * cùng giá trị đó. Giữ một bản sao ở đây là mở đường cho hai màn nói hai chuyện khác nhau.
   */
  selectedId: number | null;
  /** Yêu cầu chọn kênh — BEN GOI ghi lại (`dispatch({type:"selectChannel"})`). */
  onSelect: (id: number) => void;
  /**
   * HÀM NẠP TỆP dùng chung với khung §4.2 — xem `NhapGon` ở cuối vùng này và
   * `src/shell/IntakeFrame.tsx`.
   *
   * ⚠️ Vì sao vùng KÊNH cũng có cửa nạp (§12.2 *"nạp 3 tệp cùng lúc"*): **khi ĐÃ có kênh**,
   * vùng giữa đang hiện danh sách đoạn nên khung §4.2 KHÔNG còn ở đó — không có lối này thì
   * tệp thứ 2..N **không có cửa nào** vào app.
   */
  onNapTep: NapTep;
}

/** `duration` là GIÂY (số thực) do backend đo — client chỉ ĐỊNH DẠNG, không đo lại. */
function thoiLuong(giay: number | null): string {
  if (giay === null) return "chưa đo thời lượng";
  const tong = Math.round(giay);
  return `${Math.floor(tong / 60)}:${String(tong % 60).padStart(2, "0")}`;
}

/**
 * Hai bước ĐẦU mà một `Source` nối được tới qua `payload.source_id`. Bước `translate`
 * KHÔNG có ở đây vì payload của nó mang `translation_id` — xem TRẦN ở đầu tệp.
 */
const BUOC_NGUON: ReadonlyArray<{ type: JobType; ten: string }> = [
  { type: "ingest", ten: "nạp" },
  { type: "asr", ten: "phiên âm" },
];

/** Chữ cho `JobState` — chỉ ĐỔI NGÔN NGỮ, không sinh một đại lượng mới. */
const CHU_STATE: Record<JobState, string> = {
  queued: "đang chờ",
  running: "đang chạy",
  done: "xong",
  failed: "lỗi",
  interrupted: "bị ngắt",
  cancelled: "đã huỷ",
};

/**
 * Trạng thái HIỆN TẠI của MỘT bước, suy từ các job mang `payload.source_id` của kênh đó.
 *
 * QUY ƯỚC (vì nhiều job cùng một bước là chuyện thường — xem TRẦN ở đầu tệp): job có
 * `id` LỚN NHẤT là hiện tại, job cũ hơn là lịch sử. Không có job nào ⇒ "chưa có job"
 * (KHÁC với "chưa chạy": client không biết gì về bước đó, và nói "chưa chạy" là bịa).
 */
export function buocCuaKenh(sourceId: number, type: JobType, jobs: Job[]): string {
  const cuaBuoc = jobs.filter((job) => {
    if (job.type !== type) return false;
    // `payload` là `Record<string, unknown>`: đọc bằng KHOÁ CỤ THỂ, và so qua một biến
    // `unknown` để không hứa hẹn gì về kiểu của giá trị backend gửi.
    const idTrongPayload: unknown = job.payload["source_id"];
    return idTrongPayload === sourceId;
  });
  if (cuaBuoc.length === 0) return "chưa có job";
  const moiNhat = cuaBuoc.reduce((a, b) => (b.id > a.id ? b : a));
  return CHU_STATE[moiNhat.state];
}

export function ChannelZone({
  sources,
  jobs,
  loading,
  error,
  selectedId,
  onSelect,
  onNapTep,
}: ChannelZoneProps) {
  // ⚠️ LỐI NẠP GỌN ĐỨNG NGOÀI MỌI NHÁNH NỘI DUNG — đó là điều kiện để nó **LUÔN tới được**:
  // đang đọc, lỗi, chưa có kênh, và ĐÃ có kênh (§12.2 cần đúng ca cuối: khung §4.2 ở vùng giữa
  // đã biến mất khi có bản ghi).
  //
  // ⚠️ Nó dùng CÙNG `napTep` của `App` với khung giữa — không có bản sao thứ hai của đường nạp.
  const napGon = <NhapGon napTep={onNapTep} />;

  if (error !== null) {
    return (
      <div className="ch">
        {napGon}
        <p className="ch__loi" role="alert">{`không đọc được kênh: ${error}`}</p>
      </div>
    );
  }

  if (sources === null) {
    // `loading` luôn đúng ở nhánh này với `useApi`; nhánh còn lại là phòng thủ.
    return (
      <div className="ch">
        {napGon}
        <p className="ch__cho">{loading ? "đang đọc kênh…" : "chưa có dữ liệu kênh"}</p>
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className="ch">
        {napGon}
        <p className="ch__rong">chưa có kênh nào — nạp tệp ở ô trên</p>
      </div>
    );
  }

  const dsJob = [...jobs.values()];

  return (
    <div className="ch">
      {/* Khi ĐÃ có kênh thì đây là lối nạp DUY NHẤT còn tới được — xem `onNapTep`. */}
      {napGon}
      <ul className="ch__danh-sach">
        {sources.map((source) => {
          const dangChon = source.id === selectedId;
          return (
            <li key={source.id} className="ch__dong">
              {/* MỘT NÚT, không phải `<div onClick>`: `button` native mới focus được bằng
                  Tab và kích hoạt được bằng Enter/Space (spec UI §7 + §12.5). `type="button"`
                  để nó không bao giờ thành nút submit của một form nào.
                  `aria-pressed` là trạng thái MÁY đọc được; dấu `▸` bên dưới là trạng thái
                  NGƯỜI đọc được — hai thứ khác nhau, và chỉ đổi MÀU là không đủ (spec UI §7:
                  thông tin không được chỉ nằm ở màu). */}
              <button
                type="button"
                className="ch__item"
                aria-pressed={dangChon}
                onClick={() => onSelect(source.id)}
              >
                {/* Dấu NHÌN THẤY được của mục đang chọn. Ô này LUÔN có mặt (rỗng khi không
                    chọn) để bề rộng không nhảy khi đổi kênh. */}
                <span className="ch__dau" aria-hidden>{dangChon ? "▸" : ""}</span>
                <span className="ch__ten">{source.origin}</span>
                <span className="ch__meta">
                  {`${source.kind} · ${source.lang ?? "chưa rõ ngôn ngữ"} · ${thoiLuong(source.duration)}`}
                </span>
                {/* Sự thật CỦA CHÍNH `sources`: đã tách được tiếng hay chưa (`audio_path`). */}
                <span className="ch__tieng">
                  {source.audio_path === null ? "chưa tách tiếng" : "đã tách tiếng"}
                </span>
                {/* Trạng thái TỪNG BƯỚC, suy từ job mang `payload.source_id` — xem TRẦN đầu tệp. */}
                <span className="ch__buoc">
                  {BUOC_NGUON.map((buoc) => `${buoc.ten}: ${buocCuaKenh(source.id, buoc.type, dsJob)}`).join(" · ")}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
