/**
 * Hàm DẪN XUẤT cho bàn làm việc mới — thuần, không React, không DOM, không `fetch`.
 *
 * 🔴 NGUỒN GỐC: đây là bản chuyển `_lovable-code/src/lib/studio.ts` (170 dòng) sang kiểu
 * dữ liệu THẬT của repo. Bản gốc định nghĩa `interface Segment` RIÊNG (18 đoạn mẫu tự
 * viết) — bê nguyên nó vào là dựng một nguồn sự thật thứ hai cho cùng khái niệm "đoạn".
 * Tệp này KHÔNG định nghĩa lại `Segment`: nó nhập từ `api/types.ts`.
 *
 * ## Ba đại lượng suy ra, và vì sao KHÔNG tự tính lại cái backend đã tính
 *
 *  - `cps` (ký tự/giây): bản gốc tự tính `text.replace(/\s/g,"").length / duration(s)`.
 *    Repo ĐÃ có `TranslationCps` từ `GET /api/translations/{id}` — backend tính trên giá
 *    trị CHƯA làm tròn và gửi kèm cờ `over` (xem docblock `TranslationCpsRow` trong
 *    `api/types.ts`: *"Client PHẢI đọc cờ này thay vì tự so `cps > max_cps`"*). Vì thế
 *    hàm ở đây KHÔNG tự suy CPS từ chữ; nó nhận bảng CPS của máy chủ.
 *    ⚠️ Bản gốc còn một lỗi đo được: `duration()` trả `Math.max(0.01, end-start)`, nên
 *    đoạn 1,2 s chứa 66 ký tự cho CPS ≈ 55 — nó báo "CPS cao" cho MỌI đoạn ngắn, kể cả
 *    bản dịch hoàn hảo. Dùng số của máy chủ thì lỗi đó không tái sinh.
 *
 *  - `nén` (tỉ lệ take/chỗ): repo có `take` thật trong `LongTiengScreen` (độ dài câu lồng
 *    tiếng đã tạo). Tỉ lệ này TÍNH Ở CLIENT được vì cả hai đầu đều là số đo của máy chủ.
 *
 *  - `nghi ngờ`: `Segment.suspect` là cờ CỦA BACKEND (xem `EditScreen.lyDoNghiNgo`). Không
 *    tính lại từ `no_speech_prob`/`avg_logprob`.
 */

import type {
  DubPlanRow,
  Job,
  Segment,
  Status,
  Transcript,
  TranslationCps,
  TranslationDetail,
} from "../api/types.ts";

/**
 * HÌNH DẠNG MỘT DÒNG MÀ `SegmentRow`/`Timeline`/`Studio` TIÊU THỤ.
 *
 * 🔴 VÌ SAO CẦN KIỂU NÀY: bản đã duyệt (`_lovable-code/src/lib/studio.ts:3..14`) khai
 * `interface Segment` RIÊNG với `translations` (Record engine→chữ), `chosen`, `take`,
 * `approved` — bốn trường mà backend KHÔNG có. Backend có `Segment.text` (bản gốc),
 * `Segment.t` (bản dịch đã lưu), `Segment.suspect`, và CPS/take đến từ hai route khác.
 *
 * Hai lựa chọn, và đây là lựa chọn ĐÃ CHỌN:
 *   (a) Chép nguyên kiểu của bản duyệt rồi BỊA giá trị cho bốn trường đó ⇒ dòng nào cũng
 *       có "take" và "approved" giả. Đó đúng là thứ repo này cấm.
 *   (b) Khai một kiểu TRUNG GIAN mang đúng những gì máy chủ gửi, cộng các trường SUY RA
 *       được từ số đo thật (`cps`, `cpsOver`, `tiLeNen`). Không trường nào là hằng số bịa.
 * Chọn (b). `Dong` dưới đây là kiểu đó.
 */
export interface Dong {
  /** `Segment.i` — khoá ghép với bảng CPS và với take. */
  i: number;
  start: number;
  end: number;
  /** Chữ BẢN GỐC (`Segment.text`). */
  text: string;
  /** Chữ BẢN DỊCH nếu đã có (`Segment.t` hoặc `TranslationDetail.segments[].t`); `""` nếu chưa. */
  dich: string;
  /** Cờ CỦA MÁY CHỦ (`Segment.suspect`) — không tính lại từ `avg_logprob`. */
  suspect: boolean;
  /** CPS của máy chủ (`TranslationCpsRow.cps`); `null` khi chưa có bản dịch. */
  cps: number | null;
  /** Cờ `over` của máy chủ — ĐỌC, không tự so `cps > max`. */
  cpsOver: boolean;
  /** Ngưỡng CPS của máy chủ (`TranslationCpsRow.max_cps`). */
  maxCps: number;
  /** Tỉ lệ take/chỗ; `null` khi CHƯA lồng đoạn này (khác `0`). */
  tiLeNen: number | null;
  /** Đã duyệt — tập cục bộ của `App`, không phải trường máy chủ (backend duyệt cả bản ghi). */
  daDuyet: boolean;
}

/** Ngưỡng nén mạnh — chép từ bản đã duyệt (`COMPRESS_LIMIT = 1.5`). */
export const NGUONG_NEN = 1.5;

/** Một VIỆC CẦN XỬ LÝ — ba loại, đúng ba nguồn dữ liệu thật. */
export type LoaiViec = "nghi-ngo" | "cps" | "nen";

export interface Viec {
  /** `Segment.i` — khoá ghép với dòng. */
  i: number;
  loai: LoaiViec;
  /** Nhãn người dùng đọc, ví dụ `"CPS 21,0"` hay `"nén 1,72×"`. */
  nhan: string;
}

/** Nhãn ba loại việc — hiện trên chip lọc và trên dòng. */
export const NHAN_LOAI_VIEC: Record<LoaiViec, string> = {
  "nghi-ngo": "Nghi ngờ",
  cps: "CPS cao",
  nen: "Nén mạnh",
};

/** Độ dài đoạn, giây. `0.01` là sàn để phép chia không nổ — CÙNG sàn với bản đã duyệt. */
export function doDai(seg: Pick<Segment, "start" | "end">): number {
  return Math.max(0.01, seg.end - seg.start);
}

/**
 * In số theo cách người Việt đọc: dấu phẩy thập phân.
 *
 * ⚠️ VÌ SAO KHÔNG `toLocaleString("vi")`: nó phụ thuộc ICU của môi trường chạy (Node bản
 * không có full-icu sẽ rơi về `en-US` và in `1.72`), nên CÙNG một con số hiện hai kiểu ở
 * hai máy. Hàm này chỉ đổi dấu chấm thành dấu phẩy trên chuỗi đã cố định số chữ số.
 */
export function soVi(x: number, chuSo: number): string {
  return x.toFixed(chuSo).replace(".", ",");
}

/**
/**
 * Tỉ lệ nén của một đoạn = `take / avail` — ĐỌC từ máy chủ, không tự chia.
 *
 * 🔴 SỬA MỘT CÔNG THỨC SAI ĐÃ ĐO ĐƯỢC. Bản trước tính `take / (end - start)`, tức
 * chia cho CHỖ của chính dòng đó. ĐO TRÊN MÁY CHỦ THẬT (`GET /api/dubs/4/plan`):
 *
 *     i=0  take=3.2  slot=2.04  avail=4.36  need=0.734  trang_thai="vua"
 *
 * Chia cho `slot` ra `3.2 / 2.04 = 1.57` ⇒ giao diện báo "NÉN 1,57×" cho một dòng
 * máy chủ đánh giá là `"vua"` (vừa). Sai ở MẪU SỐ: `avail` — cửa sổ tới dòng sau —
 * mới là trần thật của việc nén, vì câu lồng tiếng được phép tràn sang khoảng lặng
 * trước dòng kế. Đó là lý do `DubPlanRow.avail` tồn tại, và `need` chính là
 * `take / avail` ĐÃ TÍNH SẴN (xem docblock `DubPlanRow` trong `api/types.ts`).
 *
 * Vì thế hàm này KHÔNG chia gì cả khi có `need`: nó trả số của máy chủ. Chỉ khi
 * một hàng kế hoạch thiếu `need` (dữ liệu cũ) mới tự chia theo `avail`, và nếu
 * `avail` cũng không dương thì trả `null` — "không đo được", khác `0`.
 *
 * ⚠️ `null` KHÁC `0`: chỉ biết `take` khi đã lồng tiếng xong đoạn đó, nên "chưa có
 * take" không phải "take dài 0 giây". Trộn hai thứ đó là bịa ra một cảnh báo nén 0×
 * cho mọi đoạn chưa lồng.
 */
export function tiLeNen(d: DubPlanRow | null | undefined): number | null {
  if (d === null || d === undefined) return null;
  if (Number.isFinite(d.need) && d.need > 0) return d.need;
  if (Number.isFinite(d.take) && d.take > 0 && Number.isFinite(d.avail) && d.avail > 0) {
    return d.take / d.avail;
  }
  return null;
}
/** Bảng tra CPS theo `Segment.i`, dựng MỘT lần từ `TranslationCps` của máy chủ. */
export function bangCps(cps: TranslationCps | null | undefined): Map<number, { cps: number | null; over: boolean; maxCps: number }> {
  const m = new Map<number, { cps: number | null; over: boolean; maxCps: number }>();
  if (cps === null || cps === undefined) return m;
  for (const r of cps.rows) m.set(r.i, { cps: r.cps, over: r.over, maxCps: r.max_cps });
  return m;
}

/**
 * MỌI việc cần xử lý của một bản ghi — ba nguồn, gộp lại.
 *
 * `daDuyet` là tập `Segment.i` người dùng đã duyệt: duyệt xong thì việc của đoạn đó BIẾN
 * MẤT (đúng hành vi bản đã duyệt: `issuesFor` trả `[]` khi `approved`). Tập này thuộc
 * `App`, không thuộc hàm này — hàm chỉ hỏi.
 */
export function viecCuaBanGhi(
  transcript: Transcript | null,
  cps: TranslationCps | null | undefined,
  keHoach: ReadonlyMap<number, DubPlanRow>,
  daDuyet: ReadonlySet<number>,
): Viec[] {
  if (transcript === null) return [];
  const bang = bangCps(cps);
  const ra: Viec[] = [];
  for (const seg of transcript.segments) {
    if (daDuyet.has(seg.i)) continue;
    if (seg.suspect) ra.push({ i: seg.i, loai: "nghi-ngo", nhan: "nghi ngờ phiên âm" });
    const c = bang.get(seg.i);
    if (c !== undefined && c.over) {
      // `cps === null` mà `over === true` là dữ liệu mâu thuẫn của máy chủ — in nhãn trơn
      // thay vì bịa một con số. Nhánh này KHÔNG xảy ra với backend hiện tại (cờ `over`
      // được tính từ `cps` khác `null`), nhưng nó là kiểu đọc an toàn.
      ra.push({ i: seg.i, loai: "cps", nhan: c.cps === null ? "CPS cao" : `CPS ${soVi(c.cps, 1)}` });
    }
    const tiLe = tiLeNen(keHoach.get(seg.i));
    if (tiLe !== null && tiLe > NGUONG_NEN) {
      ra.push({ i: seg.i, loai: "nen", nhan: `nén ${soVi(tiLe, 2)}×` });
    }
  }
  return ra;
}

/** Việc của MỘT đoạn — dùng cho nhãn ngay trên dòng. */
export function viecCuaDoan(viec: readonly Viec[], i: number): Viec[] {
  return viec.filter((v) => v.i === i);
}

// ---------------------------------------------------------------------------
// ĐƯỜNG ỐNG — sáu bước, bốn trạng thái
// ---------------------------------------------------------------------------

export type TrangThaiBuoc = "xong" | "dang-chay" | "bi-chan" | "chua";

/**
 * MOT BUOC cua duong ong.
 *
 * Ten truong TRUNG voi `Step` cua ban da duyet (`id`/`name`/`state`/`note`) de
 * `PipelineBar.tsx` — BAN SAO NGUYEN VAN cua `_lovable-code/src/components/studio/PipelineBar.tsx` —
 * bien dich duoc ma khong phai sua mot ky tu nao. Doi ten o day thi phai sua JSX,
 * va moi lan sua JSX la mot cho co the lech hinh hoc.
 */
export interface BuocDuongOng {
  id: string;
  /** Ten buoc, hien tren thanh duong ong. */
  name: string;
  /** Dong thu hai: engine da chay, hoac ly do bi chan. */
  note: string;
  /** Bon trang thai — TRUNG TEN voi `StepState` cua ban da duyet. */
  state: "done" | "running" | "blocked" | "todo";
}

/** Dau vao cua phep suy duong ong — TAT CA la du lieu may chu, khong co co cuc bo nao. */
export interface DauVaoDuongOng {
  /** Co ban ghi dang mo chua (`transcript !== null`). */
  coBanGhi: boolean;
  /** Engine ASR da sinh ra ban ghi — `null` khi chua co. */
  engineAsr: string | null;
  /**
   * Trạng thái job `ingest`/`asr` của NGUỒN đang mở — `null` khi không có job nào.
   *
   * 🔴 VÌ SAO PHẢI CÓ (lỗi thật, người dùng báo "phần phiên âm cũng ghi là chưa nạp
   * chứ ko ghi là đang chạy"): bước `asr` trước đây chỉ suy từ `coBanGhi`, nên suốt
   * quá trình job chạy — hàng chục phút với video 20 phút — thanh bước ghi "chưa nạp"
   * và vẽ ô tròn RỖNG. Người dùng không có cách nào biết sản phẩm đang làm việc hay
   * đã chết; chỉ hàng đợi ở chỗ khác mới nói.
   *
   * `queued`/`running` ⇒ bước đang chạy. `done` mà chưa có bản ghi là trạng thái
   * thoáng qua (worker ghi xong job trước khi giao diện kịp nạp lại) — hiện "đang nạp
   * lại" chứ không nói dối là "chưa nạp".
   */
  asrState: "queued" | "running" | "done" | "failed" | "interrupted" | "cancelled" | null;
  /** Có bản dịch nào `done` chưa. */
  coBanDich: boolean;
  /** Engine của bản dịch đang xem — `null` khi chưa có. */
  engineMt: string | null;
  /** Số việc cần xử lý còn lại. */
  soViec: number;
  /** Trạng thái job `dub` của bản dịch đang xem — `null` khi không có job. */
  dubState: "queued" | "running" | "done" | "failed" | "interrupted" | "cancelled" | null;
  /** Job `tron_nen` (ghép nền) — `null` khi chưa từng chạy. */
  ghepState: "queued" | "running" | "done" | "failed" | "interrupted" | "cancelled" | null;
  /** Đã có file `dub-{id}.mp4` để xuất chưa (đọc từ `kichThuocDub`). */
  coFileXuat: boolean;
}

/**
 * Sáu bước của đường ống, suy từ dữ liệu máy chủ.
 *
 * 🔴 DUYỆT LÀ TUỲ CHỌN, KHÔNG PHẢI CỬA CHẶN (đổi hành vi, có chủ).
 *
 * Bản cũ để `soViec > 0` KHOÁ cả ba bước `long`/`ghep`/`xuat`: còn việc chưa duyệt thì
 * không được lồng tiếng, không được ghép nền, không được xuất. Chủ dự án bác bỏ: duyệt là
 * bước KIỂM TRA CHẤT LƯỢNG ai muốn làm thì làm, không phải giấy phép. Đã có bản dịch trong
 * tay thì nghe thử và xuất video là quyền của người dùng — bắt họ bấm "duyệt" cho có chỉ
 * làm chữ "duyệt" mất nghĩa.
 *
 * Nên `duyet` VẪN là một bước (hiện `còn N việc` như GỢI Ý) nhưng KHÔNG tham gia điều kiện
 * của ba bước sau. Điều kiện thật của từng bước là QUAN HỆ DỮ LIỆU, không phải quyền:
 *  - `long` cần có BẢN DỊCH — không có dòng nào thì TTS không có gì để đọc;
 *  - `ghep` cần `dubState === "done"` — không có bản lồng thì không có gì để trộn;
 *  - `xuat` cần `ghepState === "done"` — tệp cuối do chính bước ghép sinh ra.
 * Thiếu ba thứ đó thì bước sau KHÔNG CÓ ĐẦU VÀO, khác hẳn "chưa được phép".
 */
export function duongOng(d: DauVaoDuongOng): BuocDuongOng[] {
  /**
   * BƯỚC `asr` — thứ tự xét, và vì sao thứ tự CŨ SAI.
   *
   * 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng: *"#109 phiên âm · fw-large-v3-turbo — 5% khi mà như
   * này ý thì state của cái header phiên âm cx phải đổi state. Nó cứ tick mãi"*).
   *
   * Bản trước xét `coBanGhi` TRƯỚC TIÊN:
   *
   *     const buocAsr = d.coBanGhi
   *       ? { note: d.engineAsr ?? "", state: "done" }
   *       : d.asrState === "running" ? … : …
   *
   * Đo trên dữ liệu thật: nguồn 6 đã có BA transcript (#23, #24, #26) từ các job `asr`
   * `done` trước đó, nên `coBanGhi === true`. Khi người dùng bấm chạy lại, job **#109**
   * (`asr`, `running`, `prog=0.05`, `created=15:41:22`) đang chạy — nhưng nhánh đầu thắng,
   * bước vẫn vẽ dấu tích và ghi engine cũ. Suốt 20 phút bóc băng, thanh bước nói "xong".
   *
   * Docblock cũ biện luận cho thứ tự đó: *"một job `asr` cũ còn `queued` trong hàng đợi
   * (người dùng bấm hai lần) không được làm bước đã xong trông như đang chạy lại"*. Lập
   * luận ấy đúng cho job CŨ, và sai cho job MỚI HƠN bản ghi — mà chạy lại chính là ca đó.
   *
   * Thứ tự đúng:
   *
   *   1. Job ĐANG CHẠY/ĐANG CHỜ ⇒ `running`. Một job đang chạy là sự thật MỚI HƠN bản ghi
   *      cũ; nó không thể "cũ" theo nghĩa docblock lo, vì hàng đợi chạy FIFO và job `queued`
   *      của lần bấm trước sẽ chạy TRƯỚC job mới. Nếu nó còn `queued` sau khi đã có bản ghi
   *      thì nó sắp chạy thật, và bước nói "chờ tới lượt" là đúng.
   *   2. `failed`/`interrupted` ⇒ `blocked`, kèm lý do đọc được. Xét TRƯỚC `coBanGhi`: người
   *      dùng vừa bấm chạy lại và job hỏng thì họ cần thấy "lỗi", không phải dấu tích của
   *      bản ghi cũ.
   *   3. ĐÃ CÓ BẢN GHI ⇒ `done`. Bản ghi là bằng chứng bền nhất khi không có job nào đang
   *      nói khác.
   *   4. `done` MÀ CHƯA CÓ BẢN GHI ⇒ "đang nạp lại". Trạng thái thoáng qua: worker ghi xong
   *      job trước khi giao diện kịp `GET /api/transcripts`.
   *   5. Còn lại (`null`, `cancelled`) ⇒ "chưa nạp".
   */
  const buocAsr: BuocDuongOng =
    d.asrState === "running"
      ? { id: "asr", name: "Phiên âm", note: "đang phiên âm…", state: "running" }
      : d.asrState === "queued"
        ? { id: "asr", name: "Phiên âm", note: "chờ tới lượt", state: "running" }
        : d.asrState === "failed"
          ? { id: "asr", name: "Phiên âm", note: "lỗi — xem hàng đợi", state: "blocked" }
          : d.asrState === "interrupted"
            ? { id: "asr", name: "Phiên âm", note: "bị ngắt — chạy lại được", state: "blocked" }
            : d.coBanGhi
              ? { id: "asr", name: "Phiên âm", note: d.engineAsr ?? "", state: "done" }
              : d.asrState === "done"
                ? { id: "asr", name: "Phiên âm", note: "đang nạp lại…", state: "running" }
                : { id: "asr", name: "Phiên âm", note: "chưa nạp", state: "todo" };

  const buocDich: BuocDuongOng = d.coBanDich
    ? { id: "dich", name: "Dịch", note: d.engineMt ?? "", state: "done" }
    : { id: "dich", name: "Dịch", note: d.coBanGhi ? "chưa dịch" : "chờ phiên âm", state: d.coBanGhi ? "blocked" : "todo" };

  // GỢI Ý, không phải cổng: `blocked` ở đây chỉ nói "còn việc nên xem", và
  // `lyDoChuaXuatDuoc` KHÔNG đọc bước này (xem dưới).
  const buocDuyet: BuocDuongOng =
    !d.coBanDich
      ? { id: "duyet", name: "Duyệt", note: "chờ bản dịch", state: "todo" }
      : d.soViec > 0
        ? { id: "duyet", name: "Duyệt", note: `còn ${d.soViec} việc`, state: "blocked" }
        : { id: "duyet", name: "Duyệt", note: "hết việc", state: "done" };

  /** Job → trạng thái bước. `failed` KHÁC `cancelled`: hỏng thì phải sửa, huỷ thì không. */
  const tuJob = (id: string, name: string, noteChay: string, s: DauVaoDuongOng["dubState"]): BuocDuongOng => {
    if (s === null) return { id, name, note: "chưa chạy", state: "todo" };
    if (s === "done") return { id, name, note: noteChay, state: "done" };
    if (s === "running") return { id, name, note: "đang chạy…", state: "running" };
    if (s === "queued") return { id, name, note: "chờ tới lượt", state: "running" };
    if (s === "failed") return { id, name, note: "lỗi — xem hàng đợi", state: "blocked" };
    if (s === "interrupted") return { id, name, note: "bị ngắt — chạy lại được", state: "blocked" };
    return { id, name, note: "đã huỷ", state: "todo" };
  };

  // Lồng tiếng KHÔNG cần duyệt — nó cần có bản dịch. Chưa có bản dịch thì nói đúng
  // lý do đó ("chờ bản dịch"), đừng mượn chữ "duyệt" để giải thích một chuyện khác.
  const buocLong: BuocDuongOng = !d.coBanDich
    ? { id: "long", name: "Lồng tiếng", note: "chờ bản dịch", state: "todo" }
    : tuJob("long", "Lồng tiếng", "đã lồng", d.dubState);

  const buocGhep: BuocDuongOng =
    d.dubState !== "done" && d.ghepState === null
      ? { id: "ghep", name: "Ghép nền", note: "cần lồng tiếng xong", state: "todo" }
      : tuJob("ghep", "Ghép nền", "đã ghép", d.ghepState);

  // Xuất KHÔNG đọc `soViec`. Lý do chưa xuất được chỉ còn hai: chưa ghép nền xong, hoặc
  // đã ghép xong nhưng chưa có tệp (job xuất chưa chạy / chưa ghi ra đĩa).
  const buocXuat: BuocDuongOng = d.coFileXuat
    ? { id: "xuat", name: "Xuất", note: "sẵn sàng", state: "done" }
    : {
        id: "xuat",
        name: "Xuất",
        note: d.ghepState !== "done" ? "cần ghép nền" : "chưa có tệp",
        state: "todo",
      };

  return [buocAsr, buocDich, buocDuyet, buocLong, buocGhep, buocXuat];
}

/**
 * Câu "vì sao chưa xuất được" — dùng cho nút Xuất bị vô hiệu.
 *
 * ⚠️ Trả CÂU, không trả cờ: cùng khuôn `Transport.xuatCho` (xem docblock ở `App.tsx`) —
 * một cờ `disabled` không nói được người dùng phải làm gì tiếp.
 */
export function lyDoChuaXuatDuoc(buoc: readonly BuocDuongOng[]): string | null {
  const xuat = buoc.find((b) => b.id === "xuat");
  if (xuat === undefined) return null;
  return xuat.state === "done" ? null : xuat.note;
}

// ---------------------------------------------------------------------------
// MÔ HÌNH BA GÓC NHÌN
// ---------------------------------------------------------------------------

/** Ba góc nhìn của bàn làm việc — đổi CÁCH MỘT DÒNG hiển thị, không đổi màn. */
export type GocNhin = "bien-tap" | "doi-chieu" | "long-tieng";

export const BA_GOC_NHIN: ReadonlyArray<{ id: GocNhin; nhan: string; phim: string }> = [
  { id: "bien-tap", nhan: "Biên tập", phim: "1" },
  { id: "doi-chieu", nhan: "Đối chiếu", phim: "2" },
  { id: "long-tieng", nhan: "Lồng tiếng", phim: "3" },
];

/**
 * Tách chữ thành từ, ĐÁNH DẤU từ khác nhau giữa hai bản — dùng cho góc nhìn Đối chiếu.
 *
 * ⚠️ Bản gốc so theo `Set` chữ thường, nên "Hà" và "hà" coi là GIỐNG nhau, còn "Hà," và
 * "Hà" coi là KHÁC (dấu phẩy dính vào từ). Hàm này bóc dấu câu hai đầu từ trước khi so —
 * một phép so ít sai hơn, và vẫn không cần thuật toán LCS (không đáng cho một nhãn phụ).
 */
export function tachTuKhac(a: string, b: string): ReadonlyArray<{ chu: string; khac: boolean }> {
  const chuan = (s: string) => s.replace(/^[\p{P}\p{S}]+|[\p{P}\p{S}]+$/gu, "").toLowerCase();
  const coA = new Set(a.split(/\s+/).filter(Boolean).map(chuan));
  return b
    .split(/(\s+)/)
    .map((manh) => {
      if (/^\s+$/.test(manh) || manh === "") return { chu: manh, khac: false };
      return { chu: manh, khac: !coA.has(chuan(manh)) };
    });
}

// ---------------------------------------------------------------------------
// SRT — xuất phụ đề
// ---------------------------------------------------------------------------

/** `HH:MM:SS,mmm` — định dạng SRT, không phải định dạng hiển thị. */
function gioSrt(t: number): string {
  const ms = Math.round(Math.max(0, t) * 1000);
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  const r = ms % 1000;
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  return `${p(h)}:${p(m)}:${p(s)},${p(r, 3)}`;
}

/**
 * Xuất SRT từ các đoạn — dùng chữ của bản dịch đang xem (`TranslationDetail.segments`).
 *
 * ⚠️ `i` của SRT là SỐ THỨ TỰ 1..N, không phải `Segment.i`: hai thứ trùng nhau hôm nay
 * nhưng không phải cùng một khái niệm, và một bản ghi đã xoá đoạn giữa sẽ làm chúng lệch.
 */
export function raSrt(segments: readonly Segment[]): string {
  return segments
    .map((s, idx) => `${idx + 1}\n${gioSrt(s.start)} --> ${gioSrt(s.end)}\n${s.t ?? s.text}\n`)
    .join("\n");
}

/** Câu chữ của một đoạn ở một góc nhìn — MỘT chỗ quyết, ba chỗ đọc. */
export function chuCuaDoan(seg: Segment, goc: GocNhin, banDich: Map<number, string>): string {
  if (goc === "bien-tap") return seg.text;
  // Đối chiếu và Lồng tiếng đều đọc BẢN DỊCH; khác nhau ở phần phụ đi kèm.
  return banDich.get(seg.i) ?? seg.t ?? "";
}

/** Bản đồ `Segment.i → chữ bản dịch`, dựng từ `TranslationDetail.segments`. */
export function bangBanDich(detail: TranslationDetail | null): Map<number, string> {
  const m = new Map<number, string>();
  if (detail === null) return m;
  for (const s of detail.segments) m.set(s.i, s.t ?? s.text);
  return m;
}

// ---------------------------------------------------------------------------
// DỰNG `Dong[]` TỪ DỮ LIỆU THẬT — cầu nối duy nhất giữa API và giao diện
// ---------------------------------------------------------------------------

/**
 * Dựng danh sách dòng từ HAI nguồn THẬT: bản ghi (bản gốc) và bản dịch.
 *
 * 🔴 SỬA MỘT HIỂU SAI ĐÃ ĐO ĐƯỢC. Lần đầu tệp này coi `transcript.segments[].text`
 * là "bản gốc" và `translation.segments[].t` là "bản dịch". ĐO TRÊN MÁY CHỦ THẬT:
 *
 *     GET /api/translations/4  ->  segments[0].text = "Bạn chắc chắn chưa từng ăn món mì lạnh..."
 *                                  segments[0].t    = ""
 *
 * `text` là TIẾNG VIỆT, tức BẢN DỊCH, và `t` rỗng. Đối chiếu mã nguồn
 * `backend/app/api/routes_translations.py:323` — `"segments": [s.to_json() for s in
 * row.segments]` — `row` là HÀNG BẢN DỊCH, nên `segments` ở route này là đoạn của
 * BẢN DỊCH, KHÔNG phải của bản ghi. Docblock route nói đúng câu đó ở dòng 301:
 * *"`segments` là đoạn của BẢN DỊCH"*.
 *
 * Vì thế hai nguồn phải đọc từ hai route khác nhau:
 *
 *   - BẢN GỐC (`text`)  <- `GET /api/transcripts/{id}` -> `segments[].text`
 *   - BẢN DỊCH (`dich`) <- `GET /api/translations/{id}` -> `segments[].text`
 *                          (bản dịch tay đã lưu `t` được ưu tiên khi có)
 *
 * Ghép theo `Segment.i`. Đoạn nào bản dịch không có thì `dich = ""` — câu trả lời
 * thật cho "chưa dịch đoạn này", khác với chép bản gốc vào chỗ bản dịch.
 *
 * `cps`/`cpsOver`/`maxCps` vẫn đọc từ `TranslationCpsRow` của máy chủ. KHÔNG tự
 * tính `chữ.length / (end-start)`: bản đã duyệt làm thế và nó báo "CPS cao" cho
 * MỌI đoạn ngắn (xem docblock đầu tệp).
 *
 * `tiLeNen` <- `takeTheoDoan` (từ `DubPlanRow.take`), `null` khi chưa lồng đoạn đó.
 *
 * ⚠️ `maxCps` khi CHƯA có bảng CPS là `0`, không phải một ngưỡng chọn sẵn: nó chỉ
 * được đọc khi `cpsOver === true`, mà cờ đó chỉ `true` khi máy chủ đã trả một hàng
 * có ngưỡng. Khai một ngưỡng mặc định ở đây là dựng nguồn sự thật thứ hai.
 */
export function dungDong(
  transcript: Transcript | null,
  banDich: TranslationDetail | null,
  cps: TranslationCps | null | undefined,
  keHoach: ReadonlyMap<number, DubPlanRow>,
  daDuyet: ReadonlySet<number>,
): Dong[] {
  if (transcript === null) return [];
  const bang = bangCps(cps);
  // Bản dịch theo `Segment.i` — `text` của route đó LÀ bản dịch; `t` là bản sửa tay.
  const banDichTheoI = new Map<number, string>();
  if (banDich !== null) {
    for (const s of banDich.segments) banDichTheoI.set(s.i, s.t !== undefined && s.t !== null ? s.t : s.text);
  }
  return transcript.segments.map((seg) => {
    const c = bang.get(seg.i);
    return {
      i: seg.i,
      start: seg.start,
      end: seg.end,
      text: seg.text,
      dich: banDichTheoI.get(seg.i) ?? "",
      suspect: seg.suspect,
      cps: c === undefined ? null : c.cps,
      cpsOver: c === undefined ? false : c.over,
      maxCps: c === undefined ? 0 : c.maxCps,
      tiLeNen: tiLeNen(keHoach.get(seg.i)),
      daDuyet: daDuyet.has(seg.i),
    };
  });
}

/** Việc của MỘT dòng, đọc từ chính dòng đó — dùng cho nhãn trên `SegmentRow`. */
export function viecCuaDong(d: Dong): Viec[] {
  // Duyệt rồi thì hết việc — CÙNG luật với `issuesFor` của bản đã duyệt (`approved ⇒ []`).
  if (d.daDuyet) return [];
  const ra: Viec[] = [];
  if (d.suspect) ra.push({ i: d.i, loai: "nghi-ngo", nhan: "nghi ngờ phiên âm" });
  if (d.cpsOver) {
    ra.push({ i: d.i, loai: "cps", nhan: d.cps === null ? "CPS cao" : `CPS ${soVi(d.cps, 1)}` });
  }
  if (d.tiLeNen !== null && d.tiLeNen > NGUONG_NEN) {
    ra.push({ i: d.i, loai: "nen", nhan: `nén ${soVi(d.tiLeNen, 2)}×` });
  }
  return ra;
}

/** Mọi việc của cả danh sách dòng — chip lọc và số đếm đọc từ đây. */
export function viecCuaDongList(ds: readonly Dong[]): Viec[] {
  return ds.flatMap(viecCuaDong);
}

/**
 * NHÃN HÀNG ĐỢI — dựng từ `jobs` THẬT, không phải chữ viết cứng.
 *
 * 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng gửi ảnh chụp panel "Hàng đợi" và nói: *"hàng đợi ở
 * đây có ghi mấy cái đang chạy đâu"*). Panel đó chứa bốn dòng VIẾT CỨNG trong JSX:
 *
 *     <QueueItem name="#37 phiên âm · faster-whisper" state="xong" />
 *     <QueueItem name="#4 dịch · opus-mt" state="xong" />
 *     <QueueItem name="#36 lồng tiếng · vieneu-v3" state="xong" />
 *     <QueueItem name="#38 ghép nền · htdemucs" state={...} />
 *     <li>ollama đang chạy · vram 2524 MiB</li>
 *
 * Đó là dữ liệu mẫu bê từ `_lovable-code`. Nó KHÔNG đọc `jobs` và KHÔNG đọc
 * `GET /api/status`, nên nó không bao giờ phản ánh hàng đợi thật — job đang chạy vẫn
 * hiện "xong", còn `#37`/`#4`/`#36`/`#38` có thể không tồn tại. Người dùng nhìn panel
 * ấy để biết máy đang làm gì, và nó nói dối.
 *
 * Ba trạng thái phải phân biệt được bằng MẮT:
 *
 *   `running`  — đang chạy ngay bây giờ, kèm % nếu `progress` > 0
 *   `queued`   — đã vào hàng đợi, chưa tới lượt
 *   còn lại    — kết thúc rồi (`done`/`failed`/`interrupted`/`cancelled`)
 *
 * Không đọc `current_phase` của `/api/status` để đoán job nào đang chạy: `running` là
 * MẢNG ID do chính worker ghi, đúng hơn một chuỗi phase ghép từ (loại, engine) — hai
 * job cùng phase là chuyện bình thường.
 */
export interface DongHangDoi {
  id: number;
  /** Tên hiển thị: "phiên âm · fw-large-v3-turbo". */
  nhan: string;
  /** Trạng thái để tô màu — trùng bộ chữ của `JobState`, không phải chuỗi tự do. */
  trangThai: "dang-chay" | "cho" | "xong" | "loi";
  /** 0..100 khi đang chạy và có tiến độ; `null` thì không vẽ thanh. */
  phanTram: number | null;
}

/** Nhãn tiếng Việt của `JobType` — HIỂN THỊ, không phải khoá dữ liệu. */
const TEN_LOAI: Record<string, string> = {
  ingest: "nạp",
  asr: "phiên âm",
  translate: "dịch",
  dub: "lồng tiếng",
  export: "ghép nền",
};

/**
 * Danh sách job để hiện trong panel hàng đợi, MỚI NHẤT TRƯỚC.
 *
 * `gioiHan` mặc định 8: panel rộng 256 px và cao bằng cột phải; hàng đợi thật đã đo được
 * 96 job, đổ hết vào đó thì không đọc được gì. Cắt ở đây chứ không ở JSX để test đo được
 * đúng phép cắt.
 *
 * Sắp theo `id` GIẢM DẦN, không theo `created_at`: hai job tạo trong cùng một giây thì so
 * chuỗi thời gian cho kết quả tuỳ ý, còn `id` là thứ tự chèn thật.
 */
export function hangDoi(jobs: readonly Job[], gioiHan = 8): DongHangDoi[] {
  return [...jobs]
    .sort((a, b) => b.id - a.id)
    .slice(0, gioiHan)
    .map((j) => {
      const ten = TEN_LOAI[j.type] ?? j.type;
      const nhan = j.engine === null ? `${ten}` : `${ten} · ${j.engine}`;
      if (j.state === "running") {
        const pt = j.progress > 0 && j.progress < 1 ? Math.round(j.progress * 100) : null;
        return { id: j.id, nhan, trangThai: "dang-chay" as const, phanTram: pt };
      }
      if (j.state === "queued") return { id: j.id, nhan, trangThai: "cho" as const, phanTram: null };
      if (j.state === "done") return { id: j.id, nhan, trangThai: "xong" as const, phanTram: null };
      return { id: j.id, nhan, trangThai: "loi" as const, phanTram: null };
    });
}

/** Dòng chân panel: GPU/VRAM và ollama, đọc từ `GET /api/status`. */
export function dongMayChu(s: Status | null): string {
  if (s === null) return "chưa đọc được trạng thái máy";
  const phan = [`hàng đợi ${s.queue_depth}`, `ollama ${s.ollama}`];
  if (s.vram !== null) phan.push(`vram ${s.vram} ${s.vram_unit}`);
  return phan.join(" · ");
}
