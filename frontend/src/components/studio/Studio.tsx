import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Command as CmdIcon, Film, Menu, Moon, Pause, Play, Repeat, Sun, Upload, Cpu, X } from "lucide-react";

import { mediaUrl, exportUrl, getPeaks } from "@/api/endpoints";
import type { DubPlanRow, Job, JobState, Source, Status, TranslationCps, TranslationDetail, Transcript } from "@/api/types";
import {
  BA_GOC_NHIN,
  dungDong,
  duongOng,
  lyDoChuaXuatDuoc,
  NGUONG_NEN,
  NHAN_LOAI_VIEC,
  raSrt,
  chuConLai,
  uocLuongTienDo,
  soVi,
  hangDoi,
  dongMayChu,
  tachTuKhac,
  viecCuaDong,
  viecCuaDongList,
  type BuocDuongOng,
  type Dong,
  type GocNhin,
  type LoaiViec,
  type Viec,
} from "@/lib/studio";
import { cn } from "@/lib/utils";
import { formatTimecode } from "@/lib/timecode";
import { usePlayer } from "./use-player";
import { Timeline, type BaoSong } from "./Timeline";
import { SegmentRow, type ViewMode } from "./SegmentRow";
import { PipelineBar } from "./PipelineBar";
import { CommandPalette, type Command } from "./CommandPalette";
import { PhuDeOverlay, PhuDeStyleDialog } from "./PhuDeStyle";
import { docStyle, luuStyle, type PhuDeStyle } from "@/lib/phuDeStyle";
import { VungDocKhung, type VungDoc } from "./VungDoc";

/**
 * BAN LAM VIEC — man hinh chinh cua Phong thu bien tap.
 *
 * NGUON GOC: `_lovable-code/src/components/studio/Studio.tsx` (596 dong).
 *
 * ## CAI GIU NGUYEN, VA CAI DA THAY
 *
 * Phan JSX (tu `return (` den het) GIU NGUYEN TUNG KY TU cua ban da duyet — moi
 * `className` Tailwind, moi co chu, moi khoang dem. Do la thu quyet dinh hinh hoc,
 * va no da duoc do.
 *
 * Phan LOGIC thay dung bon cho ma ban goc BIA du lieu:
 *
 *  1. `SAMPLE_SEGMENTS` (18 doan mau tu viet) -> `transcript.segments` THAT tu
 *     `GET /api/transcripts/{id}`, chuyen qua `dungDong()`.
 *  2. `fakePeaks()` (song gia sinh tu 18 doan mau) -> `decodePeaks()` doc THAT tu
 *     URL media cua may chu. Doc khong duoc thi dai TRONG, khong bia.
 *  3. `setRemux` chay bang `setTimeout` (gia lap 0->100%) -> trang thai buoc
 *     "Ghep nen" doc tu JOB THAT trong `GET /api/jobs`.
 *  4. `useState<Segment[]>` + `update()` sua cuc bo -> sua THAT qua
 *     `PATCH /api/translations/{id}`; duyet THAT qua `POST /api/transcripts/{id}/approve`.
 *
 * ## Bon truong KHONG CO trong backend, va cach xu ly
 *
 * Ban goc dinh nghia `Segment` voi `translations` (Record engine->chu), `chosen`,
 * `take`, `approved`. Backend KHONG co bon truong do. Xem `lib/studio.ts::Dong`:
 * moi truong o day hoac la du lieu may chu gui, hoac la so SUY RA tu du lieu may
 * chu (`tiLeNen` = take/chỗ, ca hai deu la so do). Khong co hang so bia.
 *
 * ## Vi sao KHONG con `theme` state
 *
 * Ban goc dat `document.documentElement.dataset.theme` trong `useEffect`. Repo giu
 * nguyen co che do (xem `styles.css` khoi `[data-theme="light"]`), nhung nut doi
 * che do nam trong header va trang thai van thuoc component nay.
 */

/**
 * Nhịp đồng hồ của THANH CHẠY, mili-giây.
 *
 * 250 ms: một bước nhảy 1/4 giây trên thanh dài hàng trăm pixel là dưới 1 pixel — mắt
 * không thấy giật, mà CPU không bị đốt. Nhịp này CHỈ chạy khi có bước đang chạy.
 *
 * Không dùng `NHIP_JOB_MS` (2000) của `App.tsx`: đó là nhịp HỎI MÁY CHỦ, và thanh chạy
 * cập nhật theo nó sẽ đứng yên 2 giây rồi nhảy một bước — trông như đang treo.
 */
const NHIP_DONG_HO_MS = 250;

const VIEWS: { id: ViewMode; label: string }[] = [
  { id: "edit", label: "Bien tap" },
  { id: "compare", label: "Doi chieu" },
  { id: "dub", label: "Long tieng" },
];

const KIND_LABEL: Record<LoaiViec, string> = {
  "nghi-ngo": "Nghi ngo",
  cps: "CPS cao",
  nen: "Nen manh",
};

export interface StudioProps {
  /** Danh sach kenh that (`GET /api/sources`). */
  sources: Source[];
  sourcesLoading: boolean;
  sourcesError: string | null;
  /** Kenh dang chon — `null` khi chua chon. */
  source: Source | null;
  onChonKenh: (id: number) => void;
  /** Ban ghi cua kenh dang chon (`GET /api/transcripts/{id}`), `null` khi chua co. */
  transcript: Transcript | null;
  /** Ban dich dang xem (`GET /api/translations/{id}`), `null` khi chua co. */
  banDich: TranslationDetail | null;
  /** CPS cua ban dich dang xem — SO cua may chu, khong tu tinh. */
  cps: TranslationCps | null;
  /** Take theo tung doan, tu `GET /api/dubs/{id}/plan`. Rong khi chua long. */
  /** Hang ke hoach long tieng theo `Segment.i` (`GET /api/dubs/{id}/plan`). Rong khi chua long. */
  keHoach: ReadonlyMap<number, DubPlanRow>;
  jobs: Job[];
  /**
   * `GET /api/status` — trạng thái máy chủ cho chân panel "Hàng đợi".
   *
   * `null` = chưa đọc được (đang nạp, hoặc route hỏng). Panel phải NÓI RÕ điều đó thay
   * vì in một con số cũ: `vram`/`ollama` đổi theo thời gian, và một dòng "vram 2524 MiB"
   * viết cứng là thứ người dùng đã bắt được (xem `hangDoi` trong `lib/studio.ts`).
   */
  mayChu: Status | null;
  /** Tap `Segment.i` da duyet — thuoc `App`, khong thuoc may chu. */
  daDuyet: ReadonlySet<number>;
  onDuyet: (i: number) => void;
  /** Sua chu ban dich cua MOT doan — goi `PATCH /api/translations/{id}`. */
  onSuaChu: (i: number, chu: string) => void;
  /** Sua MOC vao/ra cua mot doan — goi `PATCH /api/transcripts/{id}`. */
  onSuaMoc: (i: number, start: number, end: number) => Promise<void>;
  /** Xuat video — `App` quyet dinh dua tren du lieu that. */
  onXuatVideo: () => void;
  /** Chay lai mot buoc (nguoi dung bam vao buoc tren thanh duong ong). */
  onBuoc: (id: string) => void;
  /** Long lai MOT doan. */
  /** Nap tep tu dia — `App` goi `POST /api/sources/upload`. */
  onNapTep: (files: File[], lang: "zh" | "en") => Promise<unknown>;
  onLongLai: (i: number) => void;
  /** Thong bao loi tu tang tren, hien o day thay vi nuot. */
  loi?: string | null;
  /** So engine trong `GET /api/registry` — `null` khi chua doc duoc. */
  soEngine?: number | null;
  /** Vùng đọc OCR của nguồn đang mở; `null` = TẮT (đọc cả khung). */
  vungDoc: VungDoc | null;
  onVungDoc: (v: VungDoc | null) => void;
}

export function Studio(props: StudioProps) {
  const {
    sources,
    sourcesError,
    source,
    transcript,
    banDich,
    cps,
    keHoach,
    jobs,
    mayChu,
    daDuyet,
    onDuyet,
    onSuaMoc,
    onSuaChu,
    onXuatVideo,
    onBuoc,
    onLongLai,
    onNapTep,
    loi,
    soEngine,
    vungDoc,
    onVungDoc,
  } = props;

  const [currentId, setCurrentId] = useState<number | null>(null);
  const [view, setView] = useState<ViewMode>("edit");
  const [pxPerSec, setPxPerSec] = useState(40);
  const [bao, setBao] = useState<BaoSong>({ tren: [], duoi: [] });
  const [paletteOpen, setPaletteOpen] = useState(false);
  //: Kiểu chữ phụ đề — nạp từ `localStorage` ngay lần vẽ đầu, để bản xem trước không nháy
  //: từ mặc định sang kiểu đã lưu.
  const [kieuPhuDe, setKieuPhuDe] = useState<PhuDeStyle>(() => docStyle());
  const [styleOpen, setStyleOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [flashId, setFlashId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [queueOpen, setQueueOpen] = useState(false);
  const [issueFilter, setIssueFilter] = useState<LoaiViec | "all">("all");
  const [onlyIssues, setOnlyIssues] = useState(false);
  /**
   * DRAWER "VIEC CAN XU LY" — chi ton tai o man hinh NHO (`lg` tro xuong).
   *
   * Do that tren khung 375 px: cot viec rong 260 px + hang doi 44 px = 304 px,
   * con 71 px cho ban lam viec. Khong phai "chat" — do la khong dung duoc. Nen
   * duoi `lg` cot viec ROT KHOI luoi va thanh mot drawer truot tu trai.
   *
   * Mac dinh DONG: tren dien thoai, thu nguoi dung can dau tien la video va danh
   * sach phu de, khong phai mot danh muc viec chiem het man hinh khi vua mo.
   */
  const [viecMo, setViecMo] = useState(false);
  /**
   * TRẠNG THÁI LẠC QUAN — bước nào vừa được bấm thì ghi NGAY, trước khi job thật về.
   *
   * 🔴 LỖI THẬT, ĐO ĐƯỢC. Hai lần người dùng báo, cùng một gốc:
   *
   *   · *"#109 phiên âm · fw-large-v3-turbo — 5% … Nó cứ tick mãi"*  → bước giữ `done` cũ.
   *   · *"nên đổi state từ cái lúc ấn ý"*                            → bước không đổi khi bấm.
   *
   * Gốc: mọi `*State` trong `duongOng` suy từ `GET /api/jobs`, mà lượt hỏi cách nhau
   * `NHIP_JOB_MS = 2000` (`App.tsx:58`). Cộng thêm độ trễ mạng và thời gian `POST` ghi job
   * vào DB, người dùng bấm xong nhìn thấy trạng thái CŨ tới vài giây — rồi bấm lại.
   *
   * ĐO ĐƯỢC hậu quả trong lịch sử job: `#95/#96`, `#98/#99`, `#101/#102` là ba cặp job
   * `asr` cách nhau vài giây trên cùng một nguồn — thao tác bị lặp vì giao diện không
   * phản hồi.
   *
   * ## Vì sao một `Set` chứ không bốn cờ riêng
   *
   * Bốn cờ riêng là bốn bản sao của cùng một luật "đặt khi bấm, tan khi job thật tới", và
   * bản sao thứ tư sẽ lệch. Một `Set<id bước>` gom luật về một chỗ: `datLacQuan(id)` và
   * một `useEffect` tan cho mọi bước.
   *
   * ## Không áp cho `duyet` và `xuat`
   *
   * `duyet` chỉ `setDaDuyet` cục bộ — đổi ngay, không có độ trễ. `xuat` tải tệp trực tiếp
   * bằng thẻ `<a>`, cũng không qua job. Đặt cờ cho chúng là thêm trạng thái không bao giờ
   * tan đúng lúc.
   */
  const [lacQuan, setLacQuan] = useState<ReadonlySet<string>>(() => new Set());

  /**
   * ĐỒNG HỒ của THANH CHẠY — nhịp riêng, nhanh hơn `NHIP_JOB_MS` (2 giây).
   *
   * 🔴 VÌ SAO PHẢI CÓ: `tiLe` được suy từ `Date.now() - started_at`, nên nếu chỉ cập nhật
   * theo nhịp hỏi `/api/jobs` thì thanh chạy đứng yên 2 giây rồi nhảy một bước — trông như
   * đang treo, tức lại đúng cái cảm giác mà tính năng này sinh ra để diệt.
   *
   * 250 ms là đủ mượt cho mắt mà không đốt CPU: một bước nhảy 1/4 giây trên một
   * thanh dài hàng trăm pixel là dưới 1 pixel. Chỉ chạy khi CÓ bước đang chạy.
   */
  const [bayGio, setBayGio] = useState(() => Date.now());

  /** Đặt trạng thái lạc quan cho MỘT bước. Gọi ngay trong handler bấm, trước `onBuoc`. */
  const datLacQuan = useCallback((id: string) => {
    setLacQuan((cu) => {
      if (cu.has(id)) return cu;
      const moi = new Set(cu);
      moi.add(id);
      return moi;
    });
  }, []);

  const media: string | null = source === null ? null : mediaUrl(source.id);
  const player = usePlayer(media);
  const rowRefs = useRef(new Map<number, HTMLLIElement>());
  const fileRef = useRef<HTMLInputElement>(null);

  /** DONG THAT — dung tu ba nguon may chu, khong co gia tri bia. */
  const dong = useMemo<Dong[]>(
    () => dungDong(transcript, banDich, cps, keHoach, daDuyet),
    [transcript, banDich, cps, keHoach, daDuyet],
  );
  const daChonDau = useRef(false);
  useEffect(() => {
    if (daChonDau.current || dong.length === 0) return;
    daChonDau.current = true;
    // 🔴 LAY DONG DAU CUA LAYER 1, khong phai `dong[0]`.
    //
    // `dong[0]` la dong dau cua TOAN BO danh sach, va thu tu mang khong theo lop. Do
    // duoc tren #52: khoang 7,02-9,66 s chi co layer 2, nen mo video se to vang mot khoi
    // layer 2 — dung cai nguoi dung bao ("van di theo thu tu luc truoc khi loc layer").
    //
    // Layer 1 trong suot thi `null`: khong to khoi nao, playhead chay tu do.
    setCurrentId(dong.find((s) => s.layer === "mot_nguon")?.i ?? null);
  }, [dong]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 3200);
    return () => clearTimeout(t);
  }, [notice]);

  /**
   * Thong bao loi tu tang tren — KHONG nuot.
   *
   * ⚠️ HAI NGUON, khong phai mot. `loi` la loi cua cac HANH DONG GHI (PATCH, POST,
   * upload). `sourcesError` la loi cua luot nap DANH SACH KENH — mot duong khac han,
   * va no da tung bi nuot:
   *
   *   DO DUOC truoc khi sua: `App.tsx:84` goi `setSourcesError(...)`, `App.tsx:422`
   *   truyen `sourcesError={sourcesError}`, `Studio.tsx:84` KHAI bao no trong
   *   `StudioProps` — va khong mot dong nao DOC no. Grep toan `src/`: hai khai bao,
   *   bon cho ghi/truyen, KHONG cho doc. Nghia la khi `GET /api/sources` hong (backend
   *   chua len, sai cong, 500), nguoi dung thay mot danh sach kenh RONG va khong mot
   *   loi nao — khong phan biet duoc "chua co kenh nao" voi "khong doc duoc kenh".
   *
   * Do la dung loai khai bao chet ma repo nay xoa, va o day no khong chi chet: no lam
   * giao dien NOI DOI ve ly do trang dang trong.
   */
  useEffect(() => {
    if (loi === undefined || loi === null || loi === "") return;
    setNotice(loi);
  }, [loi]);

  useEffect(() => {
    if (sourcesError === undefined || sourcesError === null || sourcesError === "") return;
    // Giu nguyen cau cua tang duoi (thong diep cua `fetch`/FastAPI), chi noi RO no
    // thuoc phan nao — mot cau "Failed to fetch" tran trui khong cho biet hong o dau.
    setNotice(`Không nạp được danh sách kênh: ${sourcesError}`);
  }, [sourcesError]);

  /**
   * SONG AM — tinh O SERVER, khong giai ma trong trinh duyet.
   *
   * 🔴 DO DUOC, KHONG DOAN. Ban truoc `fetch(media)` roi `decodeAudioData`:
   *
   *     fetch status=206 type=video/mp4
   *     blob size=238623268 sau 0.0s
   *     ... roi KHONG co `decodeAudioData OK` lan `LOI` trong 45 giay.
   *
   * Tai xong ngay (do toc do: 318 MB/s) nhung `decodeAudioData` TREO tren container
   * MP4 238 MB — no chi giai ma CA tep va giu toan bo mau da giai ma trong bo nho.
   * Nen `peaks` luon rong va canvas luon trong.
   *
   * Cach lam chuan (Peaks.js cua BBC R&D, `waveform-data.js`) la tinh peaks o server,
   * client chi ve. Backend `GET /api/media/{id}/peaks` doc `audio_path` (WAV 16 kHz,
   * 40 MB) bang `ffmpeg astats`, tra JSON. Do duoc: 1,61 s cho 1249 s, 8 297 B
   * thay vi 238 MB.
   *
   * Ban goc cua Lovable dung `fakePeaks()` — may phat so gia (seed 7, Park-Miller)
   * nhan voi `sin(t * 7.3)`. Ham do KHONG duoc chuyen sang: ve song gia la bia du
   * lieu. That bai thi de TRONG va noi ro.
   */
  useEffect(() => {
    if (source === null) {
      setBao({ tren: [], duoi: [] });
      return;
    }
    let huy = false;
    void (async () => {
      try {
        // 200 000 điểm = 160 px/s (mức thu phóng lớn nhất) × 1249 s. Server trả
        // 124 924 điểm thật (10 ms/khung) — 2,5 điểm mỗi pixel ở 40 px/s.
        const r = await getPeaks(source.id, 200000);
        if (!huy) setBao({ tren: r.tren, duoi: r.duoi });
      } catch {
        if (!huy) {
          setBao({ tren: [], duoi: [] });
          setNotice("Khong doc duoc song am cua nguon — dai thoi gian de trong");
        }
      }
    })();
    return () => {
      huy = true;
    };
  }, [source]);

  /**
   * ĐỔI KÊNH THÌ QUÊN DÒNG ĐANG CHỌN — và chọn lại dòng ĐẦU của kênh mới.
   *
   * 🔴 LỖI THẬT, ĐO ĐƯỢC khi rà soát state: `currentId` là state CỤC BỘ của `Studio` và
   * không có gì reset nó khi `source` đổi. Đổi sang video khác thì `currentId` vẫn giữ số
   * dòng của video CŨ, và:
   *
   *   · video mới ÍT dòng hơn  ⇒ `current` thành `null`, panel sửa chữ trống rỗng mà
   *     không nói vì sao;
   *   · video mới NHIỀU dòng hơn ⇒ nó chọn một dòng CÙNG SỐ THỨ TỰ mà người dùng chưa hề
   *     bấm — và panel sửa chữ hiện nội dung của dòng đó như thể đang được chọn.
   *
   * Cùng lớp lỗi với `VungDoc` (một `useEffect` ghi đè dữ liệu người dùng mỗi lần nạp
   * trang): state cục bộ sống lâu hơn dữ liệu mà nó mô tả.
   *
   * ⚠️ KHÔNG đặt `null` rồi để yên: `Studio` TỰ CHỌN DÒNG ĐẦU khi có dòng (effect
   * `daChonDau` ở trên, có cờ chặn lặp). Đặt `null` ở đây thì effect kia không chạy lại
   * (`daChonDau` đã `true`), nên panel sửa chữ rỗng cho tới khi người dùng bấm một dòng.
   * Việc đúng là chọn dòng đầu CỦA KÊNH MỚI — cùng trạng thái mà một lần mở trang mang
   * lại, và cũng là thứ effect `daChonDau` muốn làm.
   *
   * `view`/`issueFilter`/`onlyIssues` KHÔNG reset: chúng là lựa chọn CÁCH XEM của người
   * dùng (đang ở chế độ đối chiếu, đang lọc "nghi ngờ"), không phải dữ liệu của một kênh
   * cụ thể. Reset chúng khi đổi kênh là cướp công cụ họ vừa bật.
   */
  useEffect(() => {
    setCurrentId(dong.find((s) => s.layer === "mot_nguon")?.i ?? null);
    // Chỉ khi ĐỔI KÊNH, không phải mỗi lần `dong` đổi (gõ một chữ cũng làm `dong` đổi, và
    // lúc đó cướp dòng đang chọn là hành vi sai).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source?.id]);

  /** VIEC — gop ba nguon that, dung luat "duyet roi thi het viec". */
  const issues = useMemo<Viec[]>(() => viecCuaDongList(dong), [dong]);
  const shownIssues = issueFilter === "all" ? issues : issues.filter((i) => i.loai === issueFilter);

  /** DEM theo loai — chip loc doc tu day. */
  const demTheoLoai = useMemo(() => {
    const m: Record<LoaiViec, number> = { "nghi-ngo": 0, cps: 0, nen: 0 };
    for (const v of issues) m[v.loai] += 1;
    return m;
  }, [issues]);

  /**
   * SAU BUOC CUA DUONG ONG — suy tu du lieu THAT.
   *
   * `ghepState` doc tu job `tron_nen` that; `dubState` tu job `dub` that. Ban goc
   * dung bien `remux` chay bang `setTimeout` — do la mo phong, khong phai trang thai.
   */
  /**
   * JOB LỒNG TIẾNG của bản dịch đang xem — job `dub` KHÔNG ghép nền.
   *
   * Hai chỗ sửa so với bản trước, cùng một lý do "phải đọc đúng dữ liệu":
   *
   *   1. `j.payload["translation_id"]` → `j.payload?.["translation_id"]`. `payload` là
   *      `Record<string, unknown>` nhưng dữ liệu qua JSON có thể thiếu hẳn trường này;
   *      đọc thẳng ném `Cannot read properties of undefined` (đo được: cả bộ test đỏ vì
   *      một job mẫu không có `payload`).
   *   2. `ds[ds.length - 1]` → `reduce(max id)`. Mảng `jobs` do máy chủ trả theo `id` TĂNG,
   *      nên `ds[ds.length - 1]` hiện đúng — nhưng đó là phụ thuộc vào THỨ TỰ MẢNG, thứ
   *      không nằm trong hợp đồng. Lấy theo `id` là đọc đúng thứ mà nó muốn nói: job mới
   *      nhất.
   *
   * Bản này KHÔNG lọc `tron_nen`: job `dub` có ghép nền vẫn là job lồng tiếng (nó làm cả
   * hai việc), nên bước "Lồng tiếng" phải thấy nó.
   */
  const jobDub = useMemo(() => {
    if (banDich === null) return null;
    const ds = jobs.filter(
      (j) =>
        j.type === "dub" &&
        (j.payload?.["translation_id"] as number | undefined) === banDich.id,
    );
    return ds.length === 0 ? null : ds.reduce((a, b) => (b.id > a.id ? b : a));
  }, [jobs, banDich]);

  /**
   * JOB GHÉP NỀN — và đây là chỗ bản trước lọc SAI LOẠI JOB.
   *
   * 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng: *"khi hoàn thành xong task nào đó thì phần refresh
   * lại để nó hiện ra dấu tích"*). Bản trước lọc:
   *
   *     j.type === "export" && j.payload["translation_id"] === banDich.id
   *
   * Hai trường đó KHÔNG CÙNG TỒN TẠI. Đo trên `GET /api/jobs` (108 job):
   *
   *     #64 export done {"transcript_id": 9, "format": "srt", ...}
   *     #65 export done {"transcript_id": 9, "format": "ass", ...}
   *
   * `ExportPayload` (`routes_jobs.py:95`) có `transcript_id`, `format`, `bilingual`,
   * `stem`, `translations` — KHÔNG có `translation_id`. Nên phép lọc luôn ra rỗng,
   * `jobGhep` luôn `null`, và hai bước "Ghép nền"/"Xuất" KHÔNG BAO GIỜ đạt `done` ⇒
   * không bao giờ hiện dấu tích, dù việc đã xong.
   *
   * Sự thật về hai việc này:
   *
   *   · GHÉP NỀN **không phải một loại job**. Nó là job `dub` chạy với
   *     `payload.tron_nen = true` (`dub.py:229-234`, `296`), và chính nó sinh ra
   *     `dub-{tid}.mp4` qua `_tron_va_remux`. Vì vậy phải lọc `type === "dub"` +
   *     `tron_nen` — không phải `export`.
   *   · `export` là XUẤT PHỤ ĐỀ (srt/ass) theo `transcript_id`, không liên quan tới video.
   *
   * `tron_nen` đọc bằng `=== true`, không bằng truthiness: `undefined` (job cũ không có
   * trường) phải KHÁC `true`. Truthiness sẽ biến mọi job `dub` cũ thành "đã ghép nền".
   */
  const jobGhep = useMemo(() => {
    if (banDich === null) return null;
    const ds = jobs.filter(
      (j) =>
        j.type === "dub" &&
        (j.payload?.["translation_id"] as number | undefined) === banDich.id &&
        j.payload?.["tron_nen"] === true,
    );
    return ds.length === 0 ? null : ds.reduce((a, b) => (b.id > a.id ? b : a));
  }, [jobs, banDich]);

  /**
   * JOB `ingest`/`asr` của NGUỒN đang mở — nguồn của trạng thái bước "Phiên âm".
   *
   * 🔴 VÌ SAO CẦN (lỗi thật, người dùng báo "phần phiên âm cũng ghi là chưa nạp chứ ko
   * ghi là đang chạy"): bước `asr` trước đây chỉ suy từ `transcript !== null`, nên suốt
   * 20 phút bóc băng thanh bước vẫn ghi "chưa nạp" và vẽ ô tròn RỖNG — không phân biệt
   * được "đang chạy" với "đã chết".
   *
   * Đọc CẢ `ingest` LẪN `asr` vì bấm "Phiên âm" trên video vừa nạp thì việc thật đang
   * chạy là `ingest` (bóc âm thanh); người dùng không phân biệt hai job nội bộ đó, họ
   * chỉ thấy một bước "Phiên âm" và cần biết nó đang chạy.
   *
   * Lấy job MỚI NHẤT theo `id` (danh sách đã `ORDER BY id`), không theo `created_at`:
   * hai job tạo trong cùng một giây sẽ so chuỗi thời gian cho kết quả tuỳ ý.
   */
  const jobAsr = useMemo(() => {
    if (source === null) return null;
    const ds = jobs.filter(
      (j) =>
        (j.type === "asr" || j.type === "ingest") &&
        // `j.payload` là `Record<string, unknown>` nhưng dữ liệu qua JSON có thể thiếu
        // hẳn trường này (job cũ, hoặc nguồn khác ghi). Đọc thẳng `j.payload["source_id"]`
        // ném `Cannot read properties of undefined` — đo được: cả 174 bài test đỏ vì một
        // job mẫu không có `payload`.
        (j.payload?.["source_id"] as number | undefined) === source.id,
    );
    return ds.length === 0 ? null : ds.reduce((a, b) => (b.id > a.id ? b : a));
  }, [jobs, source]);

  /**
   * Trạng thái job THẬT, đã trộn trạng thái lạc quan — dùng chung cho MỌI bước.
   *
   * Luật một chỗ: nếu bước đang có cờ lạc quan VÀ job thật chưa nói gì khác (`null` hoặc
   * `done` cũ), thì coi như `"running"`. Đây đúng là ca "chạy lại trên bản ghi đã có": job
   * cũ `done`, người dùng vừa bấm, job mới chưa về.
   *
   * Khi job thật tới với `queued`/`running`/`failed`/`interrupted`/`cancelled` thì trả
   * THẲNG trạng thái thật — cờ lạc quan không được che lỗi, và `useEffect` dưới sẽ dọn cờ.
   */
  const trangThai = useCallback(
    (id: string, that: JobState | null): JobState | null => {
      if (!lacQuan.has(id)) return that;
      if (that === null || that === "done") return "running";
      return that;
    },
    [lacQuan],
  );

  const cacBuoc: BuocDuongOng[] = useMemo(
    () =>
      duongOng({
        coBanGhi: transcript !== null,
        engineAsr: transcript === null ? null : transcript.engine,
        asrState: trangThai("asr", jobAsr === null ? null : jobAsr.state),
        coBanDich: banDich !== null,
        engineMt: banDich === null ? null : banDich.engine,
        soViec: issues.length,
        dubState: trangThai("long", jobDub === null ? null : jobDub.state),
        ghepState: trangThai("ghep", jobGhep === null ? null : jobGhep.state),
        coFileXuat: jobGhep !== null && jobGhep.state === "done",
      }),
    [transcript, banDich, issues.length, jobDub, jobGhep, jobAsr, trangThai],
  );

  // TỰ TAN trạng thái lạc quan khi `/api/jobs` đã mang tin THẬT về job này.
  //
  // Hai điều kiện tan, và vì sao đúng hai:
  //
  //   1. `jobAsr` đang `queued`/`running` ⇒ job thật đã tới, nó tự nói trạng thái. Giữ cờ
  //      lạc quan nữa thì vô hại nhưng vô nghĩa — nhánh `running` của `duongOng` thắng như
  //      nhau. Tan để lần bấm SAU còn dùng lại được cờ (nếu không tan, cờ `true` vĩnh viễn
  //      và mọi trạng thái `done` sau này bị che thành "đang phiên âm…").
  //   2. `jobAsr` `failed`/`interrupted` ⇒ lần chạy vừa hỏng. Phải HIỆN LỖI, không được che
  //      bằng trạng thái lạc quan — đó chính là kiểu nói dối mà cả hai lần sửa này đang diệt.
  //
  // Không tan khi `jobAsr === null`: đó là khoảng trễ đang chờ, đúng lúc cờ cần có tác dụng.
  // Không tan khi `jobAsr.state === "done"` mà `coBanGhi` chưa có: trạng thái thoáng qua
  // (worker ghi xong job trước khi giao diện kịp nạp transcript) — `duongOng` đã có nhánh
  // "đang nạp lại" cho nó, và cờ lạc quan nói cùng một điều.
  useEffect(() => {
    // Cặp `(id bước, job thật)` — job nào tới với trạng thái THẬT thì cờ của bước đó tan.
    const cap: Array<[string, JobState | null]> = [
      ["asr", jobAsr === null ? null : jobAsr.state],
      ["long", jobDub === null ? null : jobDub.state],
      ["ghep", jobGhep === null ? null : jobGhep.state],
    ];
    setLacQuan((cu) => {
      if (cu.size === 0) return cu;
      const moi = new Set(cu);
      for (const [id, that] of cap) {
        if (that === null) continue;            // chưa có job: đúng lúc cờ cần tác dụng
        if (that === "done") continue;          // `done` cũ: `trangThai` đã tự xử, xem dưới
        moi.delete(id);                         // queued/running/failed/... job tự nói
      }
      return moi.size === cu.size ? cu : moi;
    });
  }, [jobAsr, jobDub, jobGhep]);

  /**
   * GẮN ƯỚC LƯỢNG vào bước đang chạy — tính NGOÀI `duongOng` vì hàm đó là THUẦN và
   * không đọc đồng hồ (`uocLuongTienDo` nhận `bayGio` làm THAM SỐ, để test được bằng số cố
   * định thay vì `sleep`).
   *
   * Chỉ bước `asr` được ước lượng: đo được `translate` chạy 4–57 s và `dub` 29–265 s trên
   * cùng độ dài video, dao động quá rộng để trung vị có nghĩa. Thà không hiện gì còn hơn hiện
   * một thanh chạy sai nhịp.
   */
  const uocLuongAsr = useMemo(() => {
    // Khong can kiem `jobAsr.state === "running"` o day: `uocLuongTienDo` da co dong dau
    // `if (job.state !== "running") return null;`. DO DUOC: pha bo dieu kien lap do di thi
    // 3/3 bai test UI VAN XANH — tuc no la khai bao thua. Repo nay khong giu khai bao thua.
    if (jobAsr === null) return null;
    // LỊCH SỬ CỦA CHÍNH NGUỒN: nguồn ổn định theo nhóm qua các lần chạy (xem `uocLuongTienDo`).
    const lichSu = jobs.filter(
      (j) =>
        (j.type === "asr" || j.type === "ingest") &&
        (j.payload?.["source_id"] as number | undefined) === source?.id,
    );
    return uocLuongTienDo(
      jobAsr,
      source === null ? null : source.duration,
      lichSu,
      bayGio,
    );
  }, [jobAsr, jobs, source, bayGio]);

  // ĐỒNG HỒ CHỈ CHẠY KHI CÓ BƯỚC ĐANG CHẠY — `setInterval` vô điều kiện là bắt React
  // re-render 4 lần/giây suốt phiên làm việc, kể cả khi không có gì chạy.
  useEffect(() => {
    if (uocLuongAsr === null) return;
    const t = setInterval(() => setBayGio(Date.now()), NHIP_DONG_HO_MS);
    return () => clearInterval(t);
  }, [uocLuongAsr === null]);

  const cacBuocCoUocLuong: BuocDuongOng[] = useMemo(() => {
    if (uocLuongAsr === null) return cacBuoc;
    return cacBuoc.map((b) =>
      b.id === "asr"
        ? { ...b, tiLe: uocLuongAsr.tiLe, conLai: chuConLai(uocLuongAsr.conLaiGiay) }
        : b,
    );
  }, [cacBuoc, uocLuongAsr]);

  const lyDoXuat = useMemo(() => lyDoChuaXuatDuoc(cacBuocCoUocLuong), [cacBuocCoUocLuong]);

  const current = dong.find((s) => s.i === currentId) ?? null;

  /** Doan dang phat theo thoi gian — dung so do cua trinh phat. */
  // 🔴 PHU DE TREN VIDEO LAY DONG CUA LOP 1 (OCR), khong phai dong dau tien khop gio.
  //
  // Do duoc: `.find()` tra phan tu DAU TIEN khop `[start, end)`. Voi cap OCR/ASR cung cau,
  // ASR dai hon nen dung TRUOC trong mang (`dong` sap theo start, end):
  //
  //     i=0 [0.00-1.04]  OCR   "Lam mot nguoi lam nghe thuat"
  //     i=1 [0.00-1.14]  ASR   "Lam mot nguoi lam nghe thuat"
  //
  // Nguoi dung gui anh: phu de hien chu cua dong DUOI (ASR). Nhung tep xuat va ban long
  // da uu tien lop 1, nen man hinh phai khop voi tep — neu khong, nguoi doc nghe mot dang
  // va doc mot dang khac.
  //
  // Cung mot luat nhu `mot_dong_moi_cap` o backend: trong cac dong dang chay, chon dong
  // KHONG `suspect` (OCR) neu co; khong co thi lay dong dau.
  const playingSeg = (() => {
    // 🔴 CHI DOC LAYER 1. Khong bao gio nhay sang layer 2.
    //
    // Nguoi dung: "o dong tren la layer 1, no dang doc tu layer 1 va toi chi can doc tu
    // layer 1 thoi, chu ko duoc nhay sang layer 2".
    //
    // Va khi duoc hoi layer 1 trong thi lam gi: "De trong hoan toan".
    //
    // Nen ham chi con MOT buoc: tim dong layer 1 dang phu `player.time`. Khong co thi
    // tra `undefined` — phu de trong. Do duoc tren #43: 1884/5151 moc (moi 0,05 s)
    // khong co dong layer 1 nao, gom 7,02-9,66 s va 145,24-161,87 s.
    //
    // Layer 2 VAN CON trong `dong` — timeline ve du hai khoi, chi khong dung lam phu de.
    return dong.find(
      (s) => s.layer === "mot_nguon" && player.time >= s.start && player.time < s.end,
    );
  })();

  // 🔴 KHONG KHOI NAO DUOC CHON khi layer 1 trong — do duoc tren DOM that:
  //
  //     time=4.32  so_chon=1  "Ve len roi thi den di"
  //     time=5.82  so_chon=1  "Ve len roi thi den di"
  //     time=7.34  so_chon=0                            <- MAT
  //     time=9.36  so_chon=0                            <- MAT
  //
  // `playingSeg` la CHU tren video — chi doc layer 1, dung nhu yeu cau. Nhung
  // `currentId` la KHUNG DANG CHON trong danh sach, va no phai luon tro vao mot
  // khoi de nguoi dung biet minh dang o dau. Hai thu nay KHAC NHAU.
  //
  // Do duoc tren #43: 1884/5151 moc (moi 0,05 s) khong co dong layer 1, gom ca
  // 7,02-9,66 s. Neu dung chung `playingSeg` thi playhead chay qua ma khong khoi nao
  // duoc to vang.
  // 🔴 PHAI UU TIEN LAYER 1, giong het `playingSeg`. Neu khong, `find` lay dong DAU TIEN
  // phu `player.time` — va trong mang, dong layer 2 dung truoc dong layer 1 cua cung cau.
  //
  // Do duoc tren DB that tai 30,0 s:
  //
  //     i=19  [29.21-30.89]  hai_nguon  suspect=True   <- dung TRUOC trong mang
  //     i=20  [29.50-30.51]  hai_nguon  suspect=False  <- ban OCR, dang le phai duoc chon
  //
  // Nguoi dung gui anh: khoi vien vang dang o LAN DUOI (ban ASR), trong khi cung cau o
  // LAN TREN (ban OCR, xanh la) khong duoc chon. Vi `find` tra ve `i=19`.
  //
  // Sua: tim trong layer 1 truoc, khong co moi sang layer 2.
  // 🔴 CHON BAN OCR (suspect === false) TRUOC, vi do la ban duoc xep LAN TREN.
  //
  // Do duoc tren DB that tai 30,0 s — CA HAI deu la hai_nguon, nen uu tien `layer` KHONG
  // giai quyet duoc gi (do lai: layer 1 trong khoang 28-33 s = KHONG CO dong nao):
  //
  //     i=19  [29.21-30.89]  hai_nguon  suspect=True    ASR
  //     i=20  [29.50-30.51]  hai_nguon  suspect=False   OCR
  //
  // `xepLan` doi cho hai khoi nay: i=20 len lan 0 (top=1), i=19 xuong lan 1 (top=19).
  // Nhung `find` duyet MANG GOC, khong duyet lan — i=19 dung truoc nen no thang. Do tren
  // DOM: khoi vang o top=19 (ASR), con cung cau o top=1 (OCR, vien xanh la) khong duoc
  // chon. Nguoi dung: "current doan no nhe ra phai la cai tren ko phai cai duoi".
  // 🔴 CHI LAY LAYER 1 — giong `playingSeg`, KHONG roi xuong layer 2.
  //
  // Do duoc tren translation #52 (moc 0,5 s, ca video 245 s): **50 moc** ma layer 1
  // TRONG nhung `currentId` van chon mot khoi layer 2, vi `dangPhu` loc tu `dong`
  // (toan bo) chu khong theo `layer`:
  //
  //     t=   9.5  layer1 TRONG -> chon i=7   [ 7.02- 9.66] hai_nguon
  //     t=  33.0  layer1 TRONG -> chon i=23  [31.81-33.25] hai_nguon
  //     t=  49.5  layer1 TRONG -> chon i=34  [48.27-50.05] hai_nguon
  //
  // Nguoi dung: "toi thay no van di theo thu tu luc truoc khi loc theo layer".
  // Dung — `suspect === false` chi uu tien BAN OCR, no khong biet gi ve lop.
  //
  // Layer 1 trong thi KHONG to khoi nao. Do la hanh vi dung: playhead dang o mot
  // quang khong co phu de, va to vang mot khoi layer 2 se noi doi rang "day la cau
  // dang doc" trong khi tren video khong co chu nao.
  const dangPhu = dong.filter(
    (s) => s.layer === "mot_nguon" && player.time >= s.start && player.time < s.end,
  );
  const dongDangChon = dangPhu.find((s) => s.suspect === false) ?? dangPhu[0];
  // Dong dang chon phai la dong DANG PHAT, ke ca khi dang PAUSE va vua seek tay.
  //
  // Do duoc (nguoi dung gui anh): playhead o 0:30.00, `playingSeg` chon dung i=20 (OCR)
  // nhung khoi vien vang lai la i=19 (ASR) — vi dieu kien cu doi `player.playing`, nen
  // khi pause + seek thi `currentId` giu gia tri cu (tu lan click hoac lan phat truoc).
  // Dong dang chon phai la dong DANG PHAT, ke ca khi dang PAUSE va vua seek tay.
  //
  // 🔴 Khi layer 1 KHONG co dong nao tai moc nay thi phai BO CHON, khong giu dong cu.
  //
  // Do duoc (nguoi dung gui anh): playhead o ~7 s, layer 1 trong, nhung khoi vien vang
  // van la i=0 [0.00-1.04] — dong cu tu luc playhead con o dau phim. Ban truoc co
  // `if (playingSeg === undefined) return;` nen no giu nguyen `currentId`.
  // Dong dang chon phai la dong DANG PHAT — ca khi dang phat lan khi vua seek tay.
  //
  // Hai nguon doi `currentId`: nguoi dung BAM mot dong (`select`), va playhead di
  // chuyen. Phai phan biet, neu khong se giu dong cu mai:
  //
  //   - Dang phat: dong dang chon phai bam playhead, ke ca khi layer 1 trong (bo chon).
  //   - Dang pause: chi bo chon khi dong dang chon KHONG CON phu `player.time` — tuc
  //     nguoi dung vua seek di cho khac. Neu dong do van phu thi giu, vi do la lua
  //     chon cua nguoi dung khi bam vao no.
  //
  // Do duoc (nguoi dung gui anh): playhead o ~7 s, layer 1 trong, nhung khoi vien vang
  // van la i=0 [0.00-1.04] — dong cu tu luc playhead con o dau phim.
  // Chon khoi theo `dongDangChon` (LAYER 1), KHONG theo `playingSeg`.
  // `playingSeg` chi doc layer 1, nen o 7,02-9,66 s no la undefined va truoc day keo
  // theo `currentId = null` — playhead chay qua ma khong khoi nao duoc to vang.
  // Do duoc tren DOM that: time=7.34 so_chon=0, time=9.36 so_chon=0.
  //
  // `dongDangChon` tim TRONG LAYER 1. Khi layer 1 trong thi `i === null` va khoi dang
  // chon bi BO — playhead chay qua quang khong co phu de ma khong to vang khoi nao.
  //
  // 🔴 KHONG roi xuong layer 2 khi layer 1 trong. Do duoc tren #52: ban truoc roi xuong
  // layer 2 o **50 moc** (moi 0,5 s), va nguoi dung doc ra ngay: "toi thay no van di theo
  // thu tu luc truoc khi loc theo layer". To vang mot khoi layer 2 se noi doi rang "day la
  // cau dang doc" trong khi tren video khong co chu nao.
  //
  // Nguoi dung BAM mot khoi layer 2 thi van chon duoc — do la `select()`, y muon ro rang.
  // Chi rieng su TU DONG bam theo playhead moi bi gioi han o layer 1.
  useEffect(() => {
    const i = dongDangChon?.i ?? null;
    if (i === currentId) return;
    if (player.playing) {
      setCurrentId(i);
      return;
    }
    // 🔴 DANG PAUSE + `currentId === null`: PHAI CHON LAI, khong duoc `return`.
    //
    // Ban truoc `return` ngay o day, nen khi playhead dung trong mot quang layer 1
    // TRONG (currentId = null) roi nguoi dung seek toi mot doan CO phu de thi khong
    // khoi nao duoc to vang — mai mai, vi `null` khong bao gio thoat khoi nhanh nay.
    //
    // DO DUOC tren DOM that (translation #52): dat `currentTime = 110.2`, `paused = true`.
    // Khoi `"toi da tim duoc · 1:50.00 -> 1:50.50"` CO tren timeline va 110,2 nam TRONG
    // no, nhung `ring-signal` khong co — `chon=0`.
    //
    // Y dinh cua nhanh pause la GIU lua chon cua nguoi dung khi no van con phu thoi
    // diem hien tai. `null` khong phai mot lua chon de giu, nen phai roi xuong duoi.
    if (currentId !== null) {
      const cu = dong.find((s) => s.i === currentId);
      if (cu === undefined) return;
      if (player.time >= cu.start && player.time < cu.end) return;
    }
    setCurrentId(i);
  }, [player.playing, player.time, dongDangChon, currentId, dong]);

  useEffect(() => {
    if (currentId === null) return;
    rowRefs.current.get(currentId)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [currentId]);

  const select = useCallback(
    (i: number, seek = true) => {
      setCurrentId(i);
      const s = dong.find((x) => x.i === i);
      if (s && seek) {
        player.seek(s.start);
        if (player.loop) player.setLoop({ start: s.start, end: s.end });
      }
    },
    [dong, player],
  );

  /** Nhay toi viec ke tiep / truoc — CUNG luat voi ban da duyet. */
  const diViec = useCallback(
    (dir: 1 | -1) => {
      const ids = [...new Set(shownIssues.map((v) => v.i))];
      if (ids.length === 0) {
        setNotice("Het viec can xu ly");
        return;
      }
      const pos = currentId === null ? -1 : ids.indexOf(currentId);
      let next: number;
      if (pos === -1) {
        next = dir === 1 ? (ids.find((id) => id > (currentId ?? 0)) ?? ids[0]) : ids[ids.length - 1];
      } else next = ids[(pos + dir + ids.length) % ids.length];
      select(next);
      setFlashId(null);
      requestAnimationFrame(() => setFlashId(next));
    },
    [shownIssues, currentId, select],
  );

  /** DAT MOC vao/ra tai dau phat — ghi THAT qua `onSuaMoc` cua `App`. */
  const setEdge = useCallback(
    (edge: "start" | "end") => {
      if (current === null) return;
      const t = Math.round(player.time * 100) / 100;
      const start = edge === "start" ? Math.min(t, current.end - 0.1) : current.start;
      const end = edge === "end" ? Math.max(t, current.start + 0.1) : current.end;
      void onSuaMoc(current.i, start, end);
    },
    [current, player.time, onSuaMoc],
  );

  const toggleLoop = useCallback(() => {
    if (player.loop) player.setLoop(null);
    else if (current) {
      player.setLoop({ start: current.start, end: current.end });
      player.seek(current.start);
      player.play();
    }
  }, [player, current]);

  /**
   * XUAT — dung `exportUrl` cua backend, KHONG tu dung SRT o client.
   *
   * Ban goc tu ghep SRT bang `toSrt()` roi tai blob. Repo co route that
   * `GET /api/export/{id}?format=srt` — dung route do thi dinh dang, thu tu tham so
   * va kieu `bilingual` deu la chuyen cua backend, khong phai cua client.
   */
  const exportSrt = useCallback(() => {
    if (banDich === null) {
      setNotice("Chua co ban dich — khong xuat duoc");
      return;
    }
    const a = document.createElement("a");
    a.href = exportUrl(banDich.id, "srt", false);
    a.download = "";
    a.click();
  }, [banDich]);

  const onStep = useCallback(
    (id: string) => {
      if (id === "duyet") {
        // ─────────────────────────────────────────────────────────────────────
        // DO DUOC: nhanh nay TUNG NUOT su kien, nen `duyet` khong bao gio toi
        // route that.
        //
        // Bam nut "Duyet con 187 viec" tren thanh buoc: `request ghi: []`,
        // `notice: 0`. Nguyen nhan: `return` ngay duoi day, truoc khi goi
        // `onBuoc`. Trong khi do `App.onBuoc` CO nhanh `duyet` goi
        // `POST /api/transcripts/{id}/approve`.
        //
        // Hai viec KHAC NHAU, va ca hai deu can:
        //   1. `diViec(1)` — nhay toi viec dau tien con lai. Day la hanh vi ma
        //      nguoi dung mong doi khi bam "Duyet": duoc dua toi cho can sua.
        //   2. `onBuoc("duyet")` — ghi `status` cua CA BAN GHI qua route that.
        //      Khong goi thi `status` khong bao gio doi, va buoc "Long tieng"
        //      giu nguyen `state: "todo"` (`lib/studio.ts:263`) du nguoi dung da
        //      duyet het — giao dien noi doi.
        //
        // Thu tu: ghi TRUOC roi moi nhay. Ghi co the hong (route 404/500) va
        // `App` se dat `loi`; nhay truoc thi nguoi dung da roi khoi cho, khong
        // con thay thong bao loi gan voi hanh dong vua bam.
        // ─────────────────────────────────────────────────────────────────────
        onBuoc("duyet");
        if (issues.length > 0) diViec(1);
        else setNotice("Da duyet het");
        return;
      }
      if (id === "xuat") {
        if (lyDoXuat !== null) setNotice(`Chua xuat duoc: ${lyDoXuat}`);
        else onXuatVideo();
        return;
      }
      if (id === "long") {
        // Bấm "Lồng tiếng" trên thanh bước chỉ ĐỔI GÓC NHÌN — job `dub` do nút "Lồng lại"
        // trong panel tạo. Nhưng người dùng bấm bước này vì muốn lồng tiếng, và bước phải
        // phản hồi ngay thay vì đứng yên tới lượt hỏi `/api/jobs` kế tiếp.
        datLacQuan("long");
        setView("dub");
        return;
      }
      if (id === "dich") {
        setView("compare");
        return;
      }
      setView("edit");
      // ĐẶT TRẠNG THÁI LẠC QUAN NGAY, trước khi `onBuoc` kịp gửi request.
      //
      // `onBuoc("asr")` là `async`: nó `POST /api/jobs` rồi trả về, và bước chỉ đổi màu khi
      // `/api/jobs` (nhịp 2 s) mang job mới về. Người dùng bấm, thấy dấu tích cũ đứng yên,
      // và bấm lại — đo được trong lịch sử job: #95/#96, #98/#99, #101/#102 đều là cặp job
      // `asr` cách nhau vài giây, tức thao tác bị lặp vì giao diện không phản hồi.
      //
      // Đặt ở đây, KHÔNG trong `onBuoc`, vì `onBuoc` còn được gọi từ nơi khác (nút trong
      // panel, phím tắt) và ta chỉ muốn cờ này cho hành động bấm bước trên thanh đường ống.
      // Đặt trước `onBuoc` để request hỏng cũng đã đổi màu — và nếu hỏng thì `App` đặt `loi`,
      // effect tự tan cờ khi `jobAsr` mang `failed`.
      datLacQuan(id);
      onBuoc(id);
    },
    [issues.length, diViec, lyDoXuat, onXuatVideo, onBuoc],
  );

  const commands: Command[] = [
    { id: "play", label: player.playing ? "Tam dung" : "Phat", hint: "Space", run: player.toggle },
    { id: "next", label: "Viec ke tiep", hint: "J", run: () => diViec(1) },
    { id: "prev", label: "Viec truoc", hint: "K", run: () => diViec(-1) },
    { id: "ok", label: "Duyet doan dang chon", hint: "Enter", run: () => currentId !== null && onDuyet(currentId) },
    { id: "in", label: "Dat gio vao tai dau phat", hint: "I", run: () => setEdge("start") },
    { id: "out", label: "Dat gio ra tai dau phat", hint: "O", run: () => setEdge("end") },
    { id: "loop", label: "Bat/tat phat lap doan", hint: "L", run: toggleLoop },
    { id: "v1", label: "Xem: Bien tap", hint: "1", run: () => setView("edit") },
    { id: "v2", label: "Xem: Doi chieu", hint: "2", run: () => setView("compare") },
    { id: "v3", label: "Xem: Long tieng", hint: "3", run: () => setView("dub") },
    { id: "only", label: onlyIssues ? "Hien moi doan" : "Chi hien doan co van de", run: () => setOnlyIssues((v) => !v) },
    { id: "srt", label: "Tai phu de .srt", run: exportSrt },
    {
      id: "phu-de-hien-thi",
      label: "Chỉnh phụ đề hiển thị",
      hint: "Style",
      // Mở hộp thoại kiểu chữ. Kiểu này đi CẢ ba nơi: bản xem trước đè lên video, tệp
      // `.ass` tải về, và phụ đề burn vào video lồng tiếng (`api/endpoints.ts` đọc
      // `localStorage` khi dựng URL xuất và payload lồng tiếng).
      run: () => setStyleOpen(true),
    },
    { id: "open", label: "Mo video...", run: () => fileRef.current?.click() },
    { id: "theme", label: theme === "dark" ? "Che do sang" : "Che do toi", run: () => setTheme((t) => (t === "dark" ? "light" : "dark")) },
  ];

  /** PHIM TAT — CUNG tap phim voi ban da duyet. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
        return;
      }
      const tag = (e.target as HTMLElement).tagName;
      if (paletteOpen || tag === "INPUT" || tag === "TEXTAREA") {
        if (e.key === "Escape") (e.target as HTMLElement).blur();
        return;
      }
      const idx = dong.findIndex((s) => s.i === currentId);
      switch (e.key) {
        case " ":
          e.preventDefault();
          player.toggle();
          break;
        case "j":
        case "J":
          diViec(1);
          break;
        case "k":
        case "K":
          diViec(-1);
          break;
        case "Enter":
          if (currentId !== null) onDuyet(currentId);
          break;
        case "i":
        case "I":
          setEdge("start");
          break;
        case "o":
        case "O":
          setEdge("end");
          break;
        case "l":
        case "L":
          toggleLoop();
          break;
        case "ArrowDown":
          e.preventDefault();
          if (idx >= 0 && idx < dong.length - 1) select(dong[idx + 1].i);
          break;
        case "ArrowUp":
          e.preventDefault();
          if (idx > 0) select(dong[idx - 1].i);
          break;
        case "1":
          setView("edit");
          break;
        case "2":
          setView("compare");
          break;
        case "3":
          setView("dub");
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const visible = onlyIssues ? dong.filter((s) => viecCuaDong(s).length > 0) : dong;
  const reviewedCount = dong.filter((s) => s.daDuyet).length;
  const fileName = source === null ? "chua chon kenh" : source.origin;
  const remux = jobGhep === null ? 0 : jobGhep.progress;
  // ---------------------------------------------------------------------------
  // LOP TUONG THICH — de phan JSX cua ban da duyet bien dich NGUYEN VAN
  // ---------------------------------------------------------------------------
  //
  // Phan JSX (tu `return (` tro xuong) la BAN SAO TUNG KY TU cua
  // `_lovable-code/src/components/studio/Studio.tsx:271..596`. No goi nhung ten
  // ma ban goc dinh nghia cho mo hinh DU LIEU MAU cua no:
  //
  //     segments        -> `dong`                 (Dong[])
  //     steps           -> `cacBuoc`              (BuocDuongOng[])
  //     timecode(t)     -> `formatTimecode(t)`    (lib/timecode.ts)
  //     issue.kind      -> `viec.loai`
  //     issue.segmentId -> `viec.i`
  //     issue.label     -> `viec.nhan`
  //     update(...)     -> `onSuaChu` / `onSuaMoc`  (PATCH that)
  //     approve(...)    -> `onDuyet`               (POST that)
  //     loadFile(f)     -> `onNapTep` cua `App`    (upload that)
  //
  // Thay vi sua 326 dong JSX (moi lan sua la mot cho co the lech hinh hoc), khai
  // o day nhung ten do voi dung nghia THAT. Khong co hang so bia: moi ten duoi
  // day hoac tro thang vao du lieu may chu, hoac goi mot ham ghi that.

  // ---------------------------------------------------------------------------
  // LOP TUONG THICH — de phan JSX cua ban da duyet bien dich NGUYEN VAN
  // ---------------------------------------------------------------------------
  //
  // Phan JSX (tu `return (` tro xuong) la BAN SAO TUNG KY TU cua
  // `_lovable-code/src/components/studio/Studio.tsx:271..596`. No goi nhung ten
  // ma ban goc dinh nghia cho mo hinh DU LIEU MAU cua no. Bang anh xa:
  //
  //     segments        -> `dong`                  (Dong[])
  //     steps           -> `cacBuoc`               (BuocDuongOng[])
  //     timecode(t)     -> `formatTimecode(t)`     (lib/timecode.ts, CUNG dinh dang)
  //     s.id            -> `s.i`                   (khoa doan)
  //     i.segmentId     -> `i.i`                   (Viec)
  //     i.kind          -> `i.loai`                (Viec)
  //     i.label         -> `i.nhan`                (Viec)
  //     seg.translations[seg.chosen] -> `seg.dich` (ban dich THAT)
  //     seg.approved    -> `seg.daDuyet`
  //     update(...)     -> `onSuaChu` / `onSuaMoc` (PATCH that)
  //     approve(...)    -> `onDuyet`               (POST that)
  //     loadFile(f)     -> `onNapTep` cua `App`    (upload that)
  //
  // Thay vi sua 326 dong JSX (moi lan sua la mot cho co the lech hinh hoc), khai
  // o day nhung ten do voi dung nghia THAT. Khong co hang so bia.

  /** `segments` cua ban goc = danh sach dong THAT. */
  const segments = dong;

  /** `steps` cua ban goc = sau buoc suy tu du lieu THAT. */
  //
  // 🔴 DO DUOC: ban dau dong nay la `cacBuoc`, va no lam ca tinh nang uoc luong VO HIEU
  // — `cacBuocCoUocLuong` chi duoc truyen cho `lyDoXuat`, con `PipelineBar` nhan ban
  // CHUA gan `tiLe`. Bai test UI do dung: "Unable to find an accessible element with the
  // role \"progressbar\"".
  const steps = cacBuocCoUocLuong;

  /**
   * `timecode(t)` cua ban goc in `M:SS.ss`. Repo da co `formatTimecode` trong
   * `lib/timecode.ts` voi cung dinh dang — dung lai, khong viet ban thu hai.
   */
  const timecode = formatTimecode;

  /** `update(id, patch)` cua ban goc sua CUC BO. O day ghi THAT qua props. */
  const update = useCallback(
    (i: number, patch: (s: Dong) => Partial<Dong>) => {
      const truoc = dong.find((x) => x.i === i);
      if (truoc === undefined) return;
      const sau = patch(truoc);
      if (sau.dich !== undefined && sau.dich !== truoc.dich) onSuaChu(i, sau.dich);
      if (sau.start !== undefined || sau.end !== undefined) {
        void onSuaMoc(i, sau.start ?? truoc.start, sau.end ?? truoc.end);
      }
    },
    [dong, onSuaChu, onSuaMoc],
  );

  /** `approve(id)` cua ban goc lat co CUC BO. O day duyet THAT. */
  const approve = useCallback(
    (i: number | null) => {
      if (i === null) return;
      onDuyet(i);
    },
    [onDuyet],
  );

  // ───────────────────────────────────────────────────────────────────────────
  // DRAWER: dong bang `Escape`, va khong de trang nen cuon sau lop phu.
  //
  // Hai viec, ca hai deu la hau qua truc tiep cua viec drawer la `fixed`:
  //   1. `Escape` — khong co no thi ban phim khong co loi ra, va nguoi dung
  //      phai roi tay khoi ban phim de bam nut X. Mot lop phu dong duoc bang
  //      `Escape` la hanh vi quen thuoc cua moi dialog.
  //   2. `overflow: hidden` tren `body` — drawer la `fixed` nen trang VAN cuon
  //      o phia sau khi vuot tren lop phu. Do la loi kinh dien cua drawer:
  //      nguoi dung vuot de cuon danh sach trong drawer, va trang ben duoi
  //      chay theo. Khoa `body` khi mo, tra lai khi dong hoac unmount.
  // ───────────────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!viecMo) return;
    const khiPhim = (e: KeyboardEvent) => {
      if (e.key === "Escape") setViecMo(false);
    };
    document.addEventListener("keydown", khiPhim);
    const cu = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", khiPhim);
      document.body.style.overflow = cu;
    };
  }, [viecMo]);
  /**
   * `loadFile(f)` cua ban goc nap tep tu dia vao trinh phat.
   *
   * O day KHONG nap truc tiep: `App` moi la noi goi `POST /api/sources/upload`
   * (mot cho duy nhat doc/ghi API). Ham nay chi chuyen tiep.
   */
  const loadFile = useCallback(
    (f: File) => {
      void onNapTep([f], "zh");
    },
    [onNapTep],
  );


  /*
  KHUNG NGOAI — ba thay doi cho man hinh nho, va ly do DO DUOC cua tung cai:

  1. `h-screen overflow-hidden` -> `min-h-dvh lg:h-screen lg:overflow-hidden`.
     Do tren khung 375x667: ban cu khoa trang o 667 px va cat moi thu duoi
     man hinh; danh sach 438 doan khong bao gio cuon duoc. Dien thoai thi
     TRANG PHAI CUON DUOC — do la hanh vi nguoi dung mong doi, khong phai
     mot ngoai le. Tu `lg` tro len moi khoa lai, vi o do cot trai va danh
     sach co khung cuon rieng va khoa `h-screen` moi dung nghia.

  2. `grid-rows-[52px_1fr]` -> `lg:grid-rows-[52px_1fr]`. Tren dien thoai
     header cao hon 52 px khi ten buoc dai, nen mot hang co dinh se cat no.

  3. `grid-cols-[260px_1fr_auto]` -> `lg:grid-cols-[260px_1fr_auto]`.
     Do: 260 + 44 = 304 px tren 375 px, con 71 px cho ban lam viec. Duoi
     `lg` cot viec va hang doi deu ROT khoi luoi (xem hai `<aside>`).
  */
  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground lg:grid lg:h-screen lg:grid-rows-[52px_1fr] lg:overflow-hidden">
      {/* đầu trang */}
      <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-rule bg-panel-0 px-3 py-1.5 sm:gap-x-4 sm:px-4 sm:py-0 lg:flex-nowrap lg:py-0">
        {/*
          NUT MO DRAWER — chi hien duoi `lg`. Day la duong DUY NHAT toi danh muc
          viec tren dien thoai, nen no phai nam trong header chu khong bi an.
        */}
        <button
          onClick={() => setViecMo(true)}
          className="flex shrink-0 items-center gap-1.5 rounded-sm border border-rule px-2 py-1 text-[11.5px] text-ink-1 hover:border-ink-1 hover:text-ink-0 lg:hidden"
          aria-label="Mở danh sách việc cần xử lý"
          aria-expanded={viecMo}
        >
          <Menu className="size-3.5" />
          <span className="num">{issues.length}</span>
        </button>
        <h1 className="label-engraved shrink-0 !text-[11px] !text-ink-0">Phòng thu biên tập</h1>
        {/*
          Thanh buoc: `min-w-0 flex-1` de no co lai thay vi day header rong ra.
          Tren dien thoai no chiem HANG RIENG (`basis-full`), vi mot thanh 6 buoc
          khong the vua 375 px canh tieu de va hai nut.
        */}
        {/*
          DO O 768 px: `basis-full` tu `sm` (640) lam thanh buoc chiem CA mot hang,
          day header len 104 px va cat mat 13 px cua buoc cuoi (`pipeline.scrollW=749`
          so voi `w=736`). Tu 768 da du cho no nam cung hang voi tieu de va hai nut:
          do duoc `h1` ket thuc o x=274, con 494 px cho thanh buoc — thua 749-494.

          Nen moc la `md` chu khong phai `sm`: duoi `md` van la hang rieng (dien thoai
          that su khong the chia se hang), tu `md` tro len la cung hang.
        */}
        {/*
          DO O 768 px: can 1206 px (do tung con: 59 + 183 + 736 + 119 + 28 = 1125,
          cong 3 khe 48 va padding 32), chi co 768 — nen khoi buoc xuong hang va
          header cao 104 px. Nguyen nhan khong phai `basis` (no da la `auto` roi)
          ma la `flex-grow: 1`: khoi bi keo ra 736 px, va ben trong no `ol` rong
          749 px KHONG CO LAI duoc vi `overflow-x-auto` giu nguyen be rong noi dung.

          Nen tu `md`: `basis-0` (khong doi hoi cho truoc) + `overflow-visible` (de
          `ol` duoc phep co theo khung). Duoi `md` giu `basis-full` + `overflow-x-auto`:
          dien thoai that khong du cho 749 px, va cuon ngang o do la dung.
        */}
        <div className="order-last min-w-0 basis-full overflow-x-auto md:order-none md:basis-0 md:flex-1 md:overflow-visible">
          <PipelineBar steps={steps} onStep={onStep} />
        </div>
        <button
          onClick={() => setPaletteOpen(true)}
          className="hidden items-center gap-2 rounded-sm border border-rule px-2 py-1 text-[11.5px] text-ink-1 hover:border-ink-1 md:flex"
        >
          <CmdIcon className="size-3" /> Lệnh <span className="kbd">Ctrl K</span>
        </button>
        <button
          onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          className="ml-auto shrink-0 rounded-sm border border-rule p-1.5 text-ink-1 hover:border-ink-1 hover:text-ink-0 lg:ml-0"
          aria-label={theme === "dark" ? "Chuyển chế độ sáng" : "Chuyển chế độ tối"}
          title={theme === "dark" ? "Chế độ sáng" : "Chế độ tối"}
        >
          {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[260px_1fr_auto]">
        {/*
          MAN CHE + DRAWER "VIEC CAN XU LY" — chi duoi `lg`.

          Do tren khung 375 px: cot viec 260 px + hang doi 44 px = 304 px, con
          71 px cho ban lam viec. Nen duoi `lg` cot viec KHONG nam trong luoi;
          no la mot drawer truot tu trai, mo bang nut trong header.

          Ba thu phai co de drawer dung nghia, va ca ba deu la loi ich cu the:
            · man che bam-duoc  -> dong drawer bang cach bam ra ngoai, khong phai
                                   tim nut X;
            · `role="dialog"` + `aria-modal` -> trinh doc man hinh biet day la lop
                                   phu, khong phai mot phan cua trang;
            · `Escape` dong duoc  -> phim quen thuoc, va khong co no thi drawer
                                   thanh mot cai bay khong loi ra tren ban phim.
        */}
        {viecMo && (
          <div
            className="fixed inset-0 z-30 bg-panel-0/70 lg:hidden"
            onClick={() => setViecMo(false)}
            aria-hidden
          />
        )}
        <aside
          role={viecMo ? "dialog" : undefined}
          aria-modal={viecMo ? true : undefined}
          aria-label="Việc cần xử lý"
          className={cn(
            "flex min-h-0 flex-col bg-panel-1",
            // Duoi `lg`: drawer co dinh, truot bang `translate-x`.
            "fixed inset-y-0 left-0 z-40 w-[min(86vw,320px)] border-r border-rule shadow-2xl transition-transform duration-200",
            viecMo ? "translate-x-0" : "-translate-x-full",
            // Tu `lg`: tra ve cot binh thuong trong luoi, khong con lop phu.
            "lg:static lg:z-auto lg:w-auto lg:translate-x-0 lg:border-r lg:shadow-none",
          )}
        >
          <div className="border-b border-rule px-3 py-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="label-engraved">Việc cần xử lý</span>
              <span className={cn("num text-[18px]", issues.length ? "text-signal" : "text-ok")}>
                {issues.length}
              </span>
              <button
                onClick={() => setViecMo(false)}
                className="ml-auto rounded-sm border border-rule p-1 text-ink-1 hover:border-ink-1 hover:text-ink-0 lg:hidden"
                aria-label="Đóng danh sách việc"
              >
                <X className="size-3.5" />
              </button>
            </div>
            <div className="mt-2 h-1 overflow-hidden rounded-sm bg-panel-3">
              <div
                className="h-full bg-ok transition-all"
                style={{ width: `${(reviewedCount / segments.length) * 100}%` }}
              />
            </div>
            <p className="num mt-1 text-[10px] text-ink-2">
              đã duyệt {reviewedCount}/{segments.length} đoạn
            </p>
            {/*
              CHIP LOC — chi mot nut "Tat ca", khong lap lai bon loai.

              Bon chip cu (`Tat ca`/`Nghi ngo`/`CPS cao`/`Nen manh`) va ba nhom viec ben duoi
              noi CUNG mot chuyen bang HAI bo dieu khien, cung tro vao `issueFilter`. Hai bo
              dieu khien cho mot trang thai thi nguoi dung phai doan cai nao dang co hieu luc,
              va mot trong hai se hien trang thai cu. Giu lai: nut nay de XOA loc, ba nhom
              ben duoi de DAT loc.
            */}
            {issueFilter !== "all" && (
              <button
                onClick={() => setIssueFilter("all")}
                className="mt-3 rounded-sm border border-signal px-1.5 py-0.5 text-[10.5px] text-signal"
              >
                Bỏ lọc · xem tất cả <span className="num">{issues.length}</span>
              </button>
            )}
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {/*
              NHOM THEO LOAI VIEC, khong liet ke tung dong.

              DO THAT tren ban ghi that (438 doan, 185 viec): 160 viec la CPS, 24 la nen,
              1 la nghi ngo. Liet ke tung dong thi cot 260px bi lap kin boi 160 dong cung
              mot nhan "CPS x,y" — viec THAT (nen, nghi ngo) bi day xuong duoi day va khong
              bao gio thay. Mot danh muc gom 3 nhom noi dung dieu nguoi dung can biet:
              LOAI viec nao, BAO NHIEU, va bam vao thi loc danh sach doan theo loai do.

              Bam mot nhom = dat `issueFilter` (cung state voi chip loc phia tren), nen
              hai dieu khien khong the noi hai dieu khac nhau.
            */}
            {(["cps", "nen", "nghi-ngo"] as const).map((loai) => {
              const soLuong = issues.filter((v) => v.loai === loai).length;
              if (soLuong === 0) return null;
              const dangLoc = issueFilter === loai;
              return (
                <li key={loai}>
                  <button
                    onClick={() => setIssueFilter(dangLoc ? "all" : loai)}
                    className={cn(
                      "w-full border-b border-rule px-3 py-2.5 text-left transition-colors hover:bg-panel-2",
                      dangLoc && "bg-signal-soft",
                    )}
                    aria-pressed={dangLoc}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="label-engraved !text-fault">{NHAN_LOAI_VIEC[loai]}</span>
                      <span className="num shrink-0 text-[15px] text-ink-0">{soLuong}</span>
                    </div>
                    <p className="mt-1 text-[10.5px] text-ink-2">
                      {loai === "cps"
                        ? `vượt ngưỡng ${soVi(segments[0]?.maxCps ?? 0, 1)} cps`
                        : loai === "nen"
                          ? `take dài hơn ${soVi(NGUONG_NEN, 2)}× chỗ`
                          : "cờ nghi ngờ của máy chủ"}
                    </p>
                  </button>
                </li>
              );
            })}
            {/* Ba nhom dem — bam de LOC danh sach ben duoi. */}
            {/* Luôn hiện danh sách: chưa lọc thì đây là toàn bộ 185 việc, đã lọc thì là nhóm đó. */}
            {shownIssues.map((v) => {
              const s = segments.find((x) => x.i === v.i);
              if (s === undefined) return null;
              const soDoan = segments.findIndex((x) => x.i === v.i) + 1;
              return (
                <li key={`dong-${v.i}-${v.loai}`}>
                  <button
                    onClick={() => select(v.i)}
                    className={cn(
                      "w-full border-b border-rule px-3 py-1.5 text-left transition-colors hover:bg-panel-2",
                      currentId === v.i && "bg-signal-soft",
                    )}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="num shrink-0 text-[10.5px] text-ink-2">
                        #{soDoan} · {timecode(s.start)}
                      </span>
                      <span className="label-engraved shrink-0 !text-fault">{NHAN_LOAI_VIEC[v.loai]}</span>
                    </div>
                    <p className="mt-0.5 truncate text-[11.5px] text-ink-1">
                      {s.dich === "" ? s.text : s.dich}
                    </p>
                  </button>
                </li>
              );
            })}
            {shownIssues.length === 0 && (
              <li className="px-3 py-8 text-center text-[12px] text-ok">Không còn việc nào. Sẵn sàng xuất.</li>
            )}
          </ul>
          <div className="space-y-1 border-t border-rule px-3 py-2 text-[10.5px] text-ink-2">
            <div className="flex justify-between">
              <span>Việc kế / trước</span>
              <span>
                <span className="kbd">J</span> <span className="kbd">K</span>
              </span>
            </div>
            <div className="flex justify-between">
              <span>Duyệt</span>
              <span className="kbd">Enter</span>
            </div>
          </div>
        </aside>

        {/* bàn làm việc */}
        <main className="flex min-h-0 min-w-0 flex-col">
          {/* sân khấu */}
          {/*
            SAN KHAU — tren dien thoai video chiem HET chieu ngang, cot chu thong
            tin xuong duoi, va hang nut duoc phep xuong dong.

            Do tren khung 375 px: `w-[min(42%,420px)]` = 157 px, tuc video chi
            rong 157 px trong khi con 218 px bo trong ben canh chi de chua hai dong
            chu. Doi lai thanh `basis-full` duoi `sm`: video rong 351 px, cot chu
            xuong duoi. Tu `sm` tro len tra ve dung bo cuc cu.

            `flex-wrap` tren hang nut: 4 nut + dong thoi gian dai ~330 px, khong vua
            351 px. Ban cu de chung tran ra ngoai khung va bi cat.
          */}
          <div className="flex shrink-0 flex-col gap-3 bg-panel-0 p-2.5 sm:flex-row sm:gap-4 sm:p-3">
            <div className="relative aspect-video w-full shrink-0 overflow-hidden rounded-sm border border-rule bg-panel-1 sm:w-[min(42%,420px)]">
              {player.src ? (
                <video ref={player.videoRef} src={player.src} className="size-full object-contain" playsInline />
              ) : (
                <button
                  onClick={() => fileRef.current?.click()}
                  className="grid size-full place-items-center text-ink-2 hover:text-ink-1"
                >
                  <span className="flex flex-col items-center gap-2 text-[12px]">
                    <Film className="size-6" />
                    Bấm để mở video của bạn
                    <span className="text-[10.5px]">chưa chọn kênh</span>
                  </span>
                </button>
              )}
              {playingSeg && (
                <PhuDeOverlay
                  style={kieuPhuDe}
                  text={playingSeg.dich === "" ? playingSeg.text : playingSeg.dich}
                />
              )}
              {/*
                KHUNG VÙNG ĐỌC OCR — đè lên chính khung hình.
                Vì sao ở đây chứ không ở panel bên cạnh: người dùng phải THẤY watermark
                để kéo khung tới nó. Một ô số ở cột phải bắt họ quy đổi vị trí nhìn
                thấy sang toạ độ tỉ lệ trong đầu — và đoán sai thì hoặc watermark lọt,
                hoặc phụ đề thật bị cắt, cả hai đều im lặng.
                Chỉ hiện khi ĐÃ có video: chưa có hình thì không có gì để chọn vùng.
              */}
              {player.src !== null && <VungDocKhung vung={vungDoc} onChange={onVungDoc} />}
            </div>
            <div className="flex min-w-0 flex-1 flex-col justify-between py-1">
              <div>
                <p className="label-engraved">Tệp</p>
                <p className="num mt-1 truncate text-[12px] text-ink-0">{fileName}</p>
                {current && (
                  <div className="mt-4">
                    <p className="label-engraved">Đoạn #{segments.findIndex((x) => x.i === current.i) + 1}</p>
                    <p className="num mt-1 text-[12px] text-ink-1">
                      {timecode(current.start)} → {timecode(current.end)} ·{" "}
                      {(current.end - current.start).toFixed(2).replace(".", ",")} s
                    </p>
                    <div className="mt-2 flex gap-1.5 text-[11px]">
                      <button onClick={() => setEdge("start")} className="rounded-sm border border-rule px-2 py-0.5 text-ink-1 hover:border-ink-1">
                        Đặt vào <span className="kbd ml-1">I</span>
                      </button>
                      <button onClick={() => setEdge("end")} className="rounded-sm border border-rule px-2 py-0.5 text-ink-1 hover:border-ink-1">
                        Đặt ra <span className="kbd ml-1">O</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={player.toggle}
                  className="flex items-center gap-1.5 rounded-sm bg-signal px-3 py-1.5 text-[12px] font-semibold text-primary-foreground hover:bg-signal/90"
                >
                  {player.playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
                  {player.playing ? "Dừng" : "Phát"}
                </button>
                <button
                  onClick={toggleLoop}
                  className={cn(
                    "flex items-center gap-1.5 rounded-sm border px-2 py-1.5 text-[11.5px]",
                    player.loop ? "border-signal text-signal" : "border-rule text-ink-1 hover:border-ink-1",
                  )}
                  aria-pressed={!!player.loop}
                  title="Phát lặp đoạn đang chọn (L)"
                >
                  <Repeat className="size-3.5" /> Lặp đoạn
                </button>
                <span className="num ml-2 text-[12px] text-ink-0">
                  {timecode(player.time)} <span className="text-ink-2">/ {timecode(player.duration)}</span>
                </span>
                <button
                  onClick={() => fileRef.current?.click()}
                  className="ml-auto flex items-center gap-1.5 rounded-sm border border-rule px-2 py-1.5 text-[11.5px] text-ink-1 hover:border-ink-1"
                >
                  <Upload className="size-3.5" /> Mở video
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  accept="video/*,audio/*"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && void loadFile(e.target.files[0])}
                />
              </div>
            </div>
          </div>

          <Timeline
            segments={segments}
            bao={bao}
            duration={player.duration}
            time={player.time}
            pxPerSec={pxPerSec}
            currentId={currentId}
            onSeek={player.seek}
            onSelect={(id) => select(id)}
            onResize={(id, edge, t) =>
              update(id, (s) => {
                // ─────────────────────────────────────────────────────────────
                // DO DUOC: keo tay nam PHAI cua doan 0 (0,00 -> 2,04) lam `end`
                // THANH 0, tuc doan dai 0 giay, va `version` cua transcript tang
                // 4 -> 5.
                //
                // Nguyen nhan: `Math.min(player.duration, ...)`. Trong trinh
                // duyet chua nap metadata video (hoac khi chua chon kenh),
                // `player.duration` la **0** — va `Math.min(0, 2,7)` = 0. Mot
                // tran chua BIET gia tri lai duoc dung nhu mot tran bang 0, nen
                // no cat moi thu ve 0.
                //
                // `duration` chua biet thi KHONG DUOC lam tran. `0` khong phai
                // "khong co gioi han" theo nghia "bang 0" — no la "chua do duoc".
                // Chi kep khi `duration > 0` that su.
                //
                // San `s.start + 0.1` giu nguyen: doan khong duoc dai <= 0.
                // ─────────────────────────────────────────────────────────────
                const tranEnd = player.duration > 0 ? player.duration : Infinity;
                return edge === "start"
                  ? { start: Math.max(0, Math.min(t, s.end - 0.1)) }
                  : { end: Math.min(tranEnd, Math.max(t, s.start + 0.1)) };
              })
            }
          />

          {/* thanh góc nhìn */}
          {/*
            `flex-wrap` + `gap-y-1`: ba nhom dieu khien (3 nut goc nhin, mot hop
            kiem, mot thanh thu phong) dai ~420 px, khong vua 351 px tren dien
            thoai. Ban cu de chung tran ra va bi cat mat phan thu phong.
            `ml-auto` chi giu tu `sm` — khi da xuong dong thi `ml-auto` day thanh
            thu phong sang phai mot minh, trong nhu mot loi bo cuc.
          */}
          <div className="flex shrink-0 flex-wrap items-center gap-x-1 gap-y-1 border-b border-rule bg-panel-1 px-2 py-1.5 sm:px-3">
            {VIEWS.map((v, i) => (
              <button
                key={v.id}
                onClick={() => setView(v.id)}
                className={cn(
                  "rounded-sm px-2 py-1 text-[12px] transition-colors sm:px-2.5",
                  view === v.id ? "bg-panel-3 text-ink-0" : "text-ink-1 hover:text-ink-0",
                )}
                aria-pressed={view === v.id}
              >
                {v.label} <span className="kbd ml-1 !text-[9px]">{i + 1}</span>
              </button>
            ))}
            <label className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-ink-1 sm:ml-3">
              <input type="checkbox" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} className="accent-[var(--signal)]" />
              Chỉ đoạn có vấn đề
            </label>
            <label className="flex items-center gap-2 text-[11px] text-ink-2 sm:ml-auto">
              Thu phóng
              <input
                type="range"
                min={10}
                max={160}
                value={pxPerSec}
                onChange={(e) => setPxPerSec(+e.target.value)}
                className="w-20 accent-[var(--signal)] sm:w-24"
              />
            </label>
          </div>

          <ul className="min-h-0 flex-1 overflow-y-auto">
            {visible.map((s, thuTu) => (
              <SegmentRow
                key={s.i}
                ref={(el) => {
                  if (el) rowRefs.current.set(s.i, el);
                  else rowRefs.current.delete(s.i);
                }}
                seg={s}
                soThuTu={thuTu + 1}
                current={s.i === currentId}
                view={view}
                flash={flashId === s.i}
                onSelect={() => select(s.i, s.i !== currentId)}
                onText={(t) => update(s.i, () => ({ dich: t }))}
                onApprove={() => approve(s.i)}
                onPreview={() => {
                  player.setLoop(null);
                  select(s.i);
                  player.play();
                }}
                onRedub={() => {
                  // ĐẶT CỜ NGAY: `onLongLai` gửi `POST /api/dubs` rồi trả về, còn bước
                  // "Lồng tiếng" chỉ đổi khi `/api/jobs` mang job `dub` về (nhịp 2 s).
                  // Đo được hậu quả của việc không đặt: cặp job `dub` `#47/#48` trên cùng
                  // một bản dịch, cách nhau 47 giây — người dùng bấm lại vì không thấy gì.
                  datLacQuan("long");
                  datLacQuan("ghep");
                  onLongLai(s.i);
                  setNotice(`Đã lồng lại đoạn #${segments.findIndex((x) => x.i === s.i) + 1}`);
                }}
              />
            ))}
          </ul>
        </main>

        {/*
          HANG DOI — AN HOAN TOAN duoi `lg`.

          YEU CAU: "An cot Hang doi tren dien thoai". Khong phai thu nho: tren
          khung 375 px, mot cot 44 px chiem 12% chieu ngang chi de hien mot icon
          Cpu. Trang thai hang doi la thong tin PHU khi dang sua phu de, va no
          khong co duong nao de mo rong ra tren man hinh hep ma khong de len
          danh sach doan. Nen `hidden lg:flex` — khong ton tai duoi `lg`.
        */}
        <aside
          className={cn(
            "hidden min-h-0 flex-col border-l border-rule bg-panel-1 transition-[width] lg:flex",
            queueOpen ? "w-64" : "w-11",
          )}
        >
          <button
            onClick={() => setQueueOpen((o) => !o)}
            className="flex items-center gap-2 border-b border-rule px-3 py-3 text-ink-1 hover:text-ink-0"
            aria-expanded={queueOpen}
            title="Hàng đợi"
          >
            <Cpu className="size-4 shrink-0" />
            {queueOpen && <span className="label-engraved">Hàng đợi</span>}
            {!queueOpen && remux > 0 && remux < 100 && <span className="absolute size-1.5 translate-x-3 -translate-y-2 rounded-full bg-signal" />}
          </button>
          {queueOpen && (
            <ul className="text-[11.5px]">
              {/* DỮ LIỆU THẬT, KHÔNG PHẢI CHỮ VIẾT CỨNG.
                  Bản trước có bốn dòng `<QueueItem name="#37 phiên âm · faster-whisper"
                  state="xong" />` bê từ `_lovable-code`: chúng không đọc `jobs` nên job
                  đang chạy vẫn hiện "xong", và `#37`/`#4`/`#36`/`#38` có thể không tồn
                  tại. Người dùng đã gửi ảnh chụp panel đó và nói đúng: "hàng đợi ở đây
                  có ghi mấy cái đang chạy đâu". */}
              {hangDoi(jobs).map((d) => (
                <QueueItem
                  key={d.id}
                  name={`#${d.id} ${d.nhan}`}
                  state={
                    d.trangThai === "dang-chay"
                      ? d.phanTram === null
                        ? "đang chạy"
                        : `${d.phanTram}%`
                      : d.trangThai === "cho"
                        ? "chờ"
                        : d.trangThai === "xong"
                          ? "xong"
                          : "lỗi"
                  }
                  progress={d.phanTram ?? undefined}
                />
              ))}
              {jobs.length === 0 && (
                <li className="num border-b border-rule px-3 py-2 text-[10.5px] text-ink-2">
                  hàng đợi trống
                </li>
              )}
              <li className="num border-b border-rule px-3 py-2 text-[10.5px] text-ink-2">
                {dongMayChu(mayChu)}
              </li>
            </ul>
          )}
        </aside>
      </div>

      {notice && (
        <div className="fixed bottom-4 left-1/2 z-40 -translate-x-1/2 rounded-sm border border-rule bg-panel-2 px-4 py-2 text-[12px] text-ink-0 shadow-xl" role="status">
          {notice}
        </div>
      )}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
      <PhuDeStyleDialog
        open={styleOpen}
        onClose={() => setStyleOpen(false)}
        style={kieuPhuDe}
        // Ghi `localStorage` NGAY trong `onChange`, không qua `useEffect`: URL xuất và
        // payload lồng tiếng đọc thẳng từ `localStorage`, nên nếu chỉ ghi sau khi vẽ lại
        // thì một lượt bấm xuất ngay sau khi kéo thanh trượt có thể dùng kiểu CŨ.
        onChange={(s) => {
          setKieuPhuDe(s);
          luuStyle(s);
        }}
      />
    </div>
  );
}

function QueueItem({ name, state, progress }: { name: string; state: string; progress?: number }) {
  return (
    <li className="border-b border-rule px-3 py-2">
      <div className="flex justify-between gap-2">
        <span className="num truncate text-ink-0">{name}</span>
        <span className={cn("num", state === "xong" ? "text-ok" : "text-signal")}>{state}</span>
      </div>
      {progress !== undefined && (
        <div className="mt-1.5 h-0.5 overflow-hidden rounded-sm bg-panel-3">
          <div className="h-full bg-signal transition-all" style={{ width: `${progress}%` }} />
        </div>
      )}
    </li>
  );
}
