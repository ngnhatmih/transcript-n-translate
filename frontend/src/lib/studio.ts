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

import type { Segment, Transcript, TranslationCps, TranslationDetail } from "../api/types.ts";

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
 * Tỉ lệ nén của một đoạn = độ dài take / độ dài chỗ. `null` khi KHÔNG có take.
 *
 * ⚠️ `null` KHÁC `0`: `LongTiengScreen` chỉ biết `take` khi đã lồng tiếng xong đoạn đó,
 * nên "chưa có take" không phải "take dài 0 giây". Trộn hai thứ đó là bịa ra một cảnh báo
 * nén 0× cho mọi đoạn chưa lồng.
 */
export function tiLeNen(take: number | null | undefined, seg: Pick<Segment, "start" | "end">): number | null {
  if (take === null || take === undefined) return null;
  if (!Number.isFinite(take) || take <= 0) return null;
  return take / doDai(seg);
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
  takeTheoDoan: ReadonlyMap<number, number>,
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
    const tiLe = tiLeNen(takeTheoDoan.get(seg.i), seg);
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

export interface BuocDuongOng {
  id: string;
  ten: string;
  /** Dòng thứ hai: engine đã chạy, hoặc lý do bị chặn. */
  ghiChu: string;
  trangThai: TrangThaiBuoc;
}

/** Đầu vào của phép suy đường ống — TẤT CẢ là dữ liệu máy chủ, không có cờ cục bộ nào. */
export interface DauVaoDuongOng {
  /** Có bản ghi đang mở chưa (`transcript !== null`). */
  coBanGhi: boolean;
  /** Engine ASR đã sinh ra bản ghi — `null` khi chưa có. */
  engineAsr: string | null;
  /** Có bản dịch nào `done` chưa. */
  coBanDich: boolean;
  /** Engine của bản dịch đang xem — `null` khi chưa có. */
  engineMt: string | null;
  /** Số việc cần xử lý còn lại. */
  soViec: number;
  /** Trạng thái job `dub` của bản dịch đang xem — `null` khi không có job. */
  dubState: "queued" | "running" | "done" | "failed" | "cancelled" | null;
  /** Job `tron_nen` (ghép nền) — `null` khi chưa từng chạy. */
  ghepState: "queued" | "running" | "done" | "failed" | "cancelled" | null;
  /** Đã có file `dub-{id}.mp4` để xuất chưa (đọc từ `kichThuocDub`). */
  coFileXuat: boolean;
}

/**
 * Sáu bước của đường ống, suy từ dữ liệu máy chủ.
 *
 * ⚠️ THỨ TỰ CỦA `if` LÀ NGHĨA: `duyet` đứng TRƯỚC `long`/`ghep`/`xuat` vì ba bước sau bị
 * chặn khi còn việc chưa duyệt. Đảo thứ tự là để một bước "xong" nói dối khi thật ra nó
 * chưa được phép chạy.
 */
export function duongOng(d: DauVaoDuongOng): BuocDuongOng[] {
  const buocAsr: BuocDuongOng = d.coBanGhi
    ? { id: "asr", ten: "Phiên âm", ghiChu: d.engineAsr ?? "", trangThai: "xong" }
    : { id: "asr", ten: "Phiên âm", ghiChu: "chưa nạp", trangThai: "chua" };

  const buocDich: BuocDuongOng = d.coBanDich
    ? { id: "dich", ten: "Dịch", ghiChu: d.engineMt ?? "", trangThai: "xong" }
    : { id: "dich", ten: "Dịch", ghiChu: d.coBanGhi ? "chưa dịch" : "chờ phiên âm", trangThai: d.coBanGhi ? "bi-chan" : "chua" };

  const buocDuyet: BuocDuongOng =
    !d.coBanDich
      ? { id: "duyet", ten: "Duyệt", ghiChu: "chờ bản dịch", trangThai: "chua" }
      : d.soViec > 0
        ? { id: "duyet", ten: "Duyệt", ghiChu: `còn ${d.soViec} việc`, trangThai: "bi-chan" }
        : { id: "duyet", ten: "Duyệt", ghiChu: "hết việc", trangThai: "xong" };

  /** Job → trạng thái bước. `failed` KHÁC `cancelled`: hỏng thì phải sửa, huỷ thì không. */
  const tuJob = (id: string, ten: string, ghiChuChay: string, s: DauVaoDuongOng["dubState"]): BuocDuongOng => {
    if (s === null) return { id, ten, ghiChu: "chưa chạy", trangThai: "chua" };
    if (s === "done") return { id, ten, ghiChu: ghiChuChay, trangThai: "xong" };
    if (s === "running") return { id, ten, ghiChu: "đang chạy…", trangThai: "dang-chay" };
    if (s === "queued") return { id, ten, ghiChu: "chờ tới lượt", trangThai: "dang-chay" };
    if (s === "failed") return { id, ten, ghiChu: "lỗi — xem hàng đợi", trangThai: "bi-chan" };
    return { id, ten, ghiChu: "đã huỷ", trangThai: "chua" };
  };

  // Lồng tiếng chỉ ĐƯỢC PHÉP chạy khi đã duyệt xong — cùng luật với bản đã duyệt.
  const buocLong: BuocDuongOng =
    d.soViec > 0 && d.dubState === null
      ? { id: "long", ten: "Lồng tiếng", ghiChu: "cần duyệt xong", trangThai: "chua" }
      : tuJob("long", "Lồng tiếng", "đã lồng", d.dubState);

  const buocGhep: BuocDuongOng =
    d.dubState !== "done" && d.ghepState === null
      ? { id: "ghep", ten: "Ghép nền", ghiChu: "cần lồng tiếng xong", trangThai: "chua" }
      : tuJob("ghep", "Ghép nền", "đã ghép", d.ghepState);

  const buocXuat: BuocDuongOng = d.coFileXuat
    ? { id: "xuat", ten: "Xuất", ghiChu: "sẵn sàng", trangThai: "xong" }
    : {
        id: "xuat",
        ten: "Xuất",
        ghiChu: d.soViec > 0 ? "cần duyệt xong" : d.ghepState !== "done" ? "cần ghép nền" : "chưa có tệp",
        trangThai: "chua",
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
  return xuat.trangThai === "xong" ? null : xuat.ghiChu;
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
