/**
 * BÀN LÀM VIỆC — màn hình chính của Phòng thu biên tập.
 *
 * 🔴 NGUỒN GỐC: `_lovable-code/src/components/studio/Studio.tsx` (596 dòng). Tệp này giữ
 * NGUYÊN hình học đo được của bản đã duyệt, nhưng nội dung là DỮ LIỆU THẬT của repo.
 *
 * 📏 SỐ ĐO trên bản đã duyệt (Chrome, 1680×1050, `getBoundingClientRect`):
 *      lưới gốc      : `52px 998px` (header + thân), `overflow: hidden`
 *      header        : 1680×52, pad-inline 16, gap 16, `border-b 1px --rule`
 *      ba cột        : **260px / 1376px / 44px**
 *      aside trái    : 260×998, `--panel-1`, `border-r 1px --rule`
 *      main          : 1376×998
 *      aside phải    : 44×998 (THU GỌN mặc định), `--panel-1`, `border-l 1px --rule`
 *      sân khấu      : 1376×260, pad 12, gap 16, `--panel-0`
 *        video       : 420×236 (`w-[min(42%,420px)]` + `aspect-video`), radius 2, viền 1px
 *      dải thời gian : 1376×160
 *      thanh góc nhìn: 1376×39, pad 6px 12px, gap 4px, `--panel-1`
 *      danh sách     : 1376×539, cuộn dọc
 *      dòng          : 1366×68, cột `88px 1fr auto`, gap-x 16, pad 10px 16px
 *
 * ## Vì sao màn này KHÔNG tự `fetch`
 *
 * Cùng luật với mọi màn cũ: `App` là nơi DUY NHẤT đọc API cho mỗi hàng dữ liệu. Màn này
 * nhận prop, báo callback.
 *
 * ## Cái KHÔNG có ở đây, và vì sao
 *
 *  - **Không `fakePeaks`**: bản gốc sinh sóng giả từ 18 đoạn mẫu. Sóng âm ở đây đọc THẬT
 *    từ URL media của máy chủ (`docSong`); đọc không được thì dải để trống, KHÔNG bịa.
 *  - **Không `SAMPLE_SEGMENTS`**: mọi đoạn đến từ `transcript`/`banDich`.
 *  - **Không `remux` giả bằng `setTimeout`**: trạng thái `Ghép nền` đọc từ job thật.
 *  - **Không `GLOSSARY` viết cứng**: thuật ngữ đến qua prop `thuatNgu`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Job, Segment, Source, SourceLang, TranslationCps, TranslationDetail, Transcript } from "../../api/types.ts";
import {
  BA_GOC_NHIN,
  bangBanDich,
  duongOng,
  lyDoChuaXuatDuoc,
  NHAN_LOAI_VIEC,
  type DauVaoDuongOng,
  type GocNhin,
  type LoaiViec,
  viecCuaBanGhi,
} from "../../lib/studio.ts";
import { formatTimecode } from "../../lib/timecode.ts";
import { ChannelZone, type KetQuaNap } from "./ChannelZone.tsx";
import { CommandPalette, type Lenh } from "./CommandPalette.tsx";
import { PipelineBar } from "./PipelineBar.tsx";
import { SegmentRow, type ThuatNgu } from "./SegmentRow.tsx";
import { Timeline } from "./Timeline.tsx";
import { docSong, usePlayer } from "./use-player.ts";

/** `JobState` của backend (5 giá trị) → trạng thái bước (4 giá trị). */
function tuJobState(s: Job["state"] | undefined): DauVaoDuongOng["dubState"] {
  if (s === undefined) return null;
  if (s === "done") return "done";
  if (s === "running") return "running";
  if (s === "queued") return "queued";
  if (s === "failed") return "failed";
  return "cancelled";
}

export interface StudioProps {
  source: Source | null;
  transcript: Transcript | null;
  banDich: TranslationDetail | null;
  cps: TranslationCps | null;
  jobs: readonly Job[];
  takeTheoDoan: ReadonlyMap<number, number>;
  daDuyet: ReadonlySet<number>;
  thuatNgu: readonly ThuatNgu[];
  mediaUrl: string | null;
  dangLuu: boolean;
  loiGhi: ReadonlyMap<number, string>;
  coFileXuat: boolean;
  onDuyet: (i: number) => void;
  onSuaChu: (i: number, chu: string) => void;
  onXuatSrt: () => void;
  onXuatVideo: () => void;
  onBuoc: (id: string) => void;
  onSuaMoc: (i: number, edge: "start" | "end", t: number) => void;
  onLongLai: (i: number) => void;

  // ── NHỮNG ĐƯỜNG GHI CỦA TẦNG DỮ LIỆU CŨ (2026-10-30) ────────────────────────────
  // ⚠️ Mỗi prop dưới đây là một đường người dùng ĐÃ CÓ trong bản cũ và vẫn cần: nạp tệp,
  // tạo bản dịch, duyệt cả bản ghi, huỷ/chạy lại job, xoá kênh/bản dịch. Bản `Studio` đầu
  // tiên bỏ sót chúng, nên `App` khai ra mà không ai gọi — TypeScript bắt được 22 chỗ
  // (`TS6133`), và đó là phát hiện ĐÚNG: một đường ghi không có nút là một đường chết.
  //
  // `App` giữ nguyên mọi bất biến của chúng (hàng đợi ghi tuần tự, cờ "đang bay" theo đối
  // tượng, đọc lại từ máy chủ). `Studio` chỉ đặt nút và BÁO.

  /** Đang có MỘT lời gọi tạo bản dịch bay — khoá nút `dịch`. */
  dangTao: boolean;
  /** Engine `mt` của registry, để chọn engine trước khi bấm `dịch`. */
  specsMt: readonly { id: string; label: string }[];
  /** Tạo một bản dịch cho bản ghi đang mở, bằng engine đã chọn. */
  onTaoBanDich: (engine: string) => void;
  /** Câu lỗi của lần tạo gần nhất (nguyên văn `ApiError.message`), hoặc `null`. */
  loiTao: string | null;
  /** Chế độ CHIMERA (§4.5) — cờ của `App`, đi vào body của `createTranslation`. */
  chimera: boolean;
  onChimeraChange: (bat: boolean) => void;

  /** Nạp tệp — đường vào DUY NHẤT của app. */
  onNapTep: (files: File[], lang: SourceLang) => Promise<KetQuaNap[]>;
  /** Xoá một kênh. Ném khi máy chủ từ chối (câu tiếng Việt hiện nguyên văn). */
  onXoaKenh: (id: number) => Promise<void>;
  /** Xoá một bản dịch. */
  onXoaBanDich: (id: number) => Promise<void>;

  /** Duyệt CẢ BẢN GHI (`approveTranscript`) — khác `onDuyet` (duyệt TỪNG DÒNG, cục bộ). */
  onDuyetBanGhi: () => void;
  /** Đang có MỘT lời gọi duyệt bản ghi bay. */
  dangDuyetBanGhi: boolean;
  /** Lỗi của lần duyệt gần nhất, nguyên văn. */
  loiDuyet: string | null;

  /** Lồng tiếng CẢ bản dịch (đắt: 5–7 phút cho 461 dòng). */
  onLongTieng: (voice: string | null) => void;
  /** Huỷ lượt lồng đang chạy. */
  onHuyLongTieng: () => void;
  /** Lỗi của lần lồng gần nhất, nguyên văn. */
  loiLongTieng: string | null;

  /** Huỷ MỘT job — câu của giao diện chỉ được nói "đã YÊU CẦU huỷ". */
  onHuyJob: (id: number) => void;
  /** Chạy lại một job `failed`/`interrupted`. */
  onChayLaiJob: (id: number) => void;
  /** Job nào đang có một lệnh bay (khoá nút của chính nó). */
  dangLenh: ReadonlySet<number>;
  /** Job nào đã được GỬI YÊU CẦU HUỶ, kèm trạng thái lúc gửi. */
  daYeuCauHuy: ReadonlyMap<number, Job["state"]>;
  /** Câu lỗi của lệnh gần nhất, theo từng job. */
  loiLenh: ReadonlyMap<number, string>;

  /** Bóc lại bằng engine ASR khác — xếp một job `asr` MỚI cho nguồn của bản ghi đang mở. */
  onBocLai: (engine: string) => void;
  /** Đang có MỘT lời gọi `bóc lại` bay. */
  dangBocLai: boolean;
  /** Lỗi của lần `bóc lại` gần nhất, nguyên văn. */
  loiBocLai: string | null;
  /** Engine `asr` của registry, để chọn trước khi bóc lại. */
  specsAsr: readonly { id: string; label: string }[];

  /** Bản dịch nào đang xem — cần để chọn bản trong danh sách. */
  danhSachBanDich: readonly { id: number; engine: string; status: string; stale: boolean }[];
  onChonBanDich: (id: number) => void;
  /** Câu "bản dịch đã lỗi thời so với bản ghi", hoặc `null`. */
  /** Câu "bản dịch đã lỗi thời so với bản ghi", hoặc `null`. */
  cauLoiThoi: string | null;

  // ── BỐN CÂU TRẢ LỜI CÒN LẠI (2026-10-30) ───────────────────────────────────────
  // Bốn khai báo này có từ trước và vẫn đúng; bản `Studio` đầu bỏ sót chỗ hiện nên chúng
  // thành khai báo chết (`TS6133`). Mỗi cái là một câu người dùng CẦN đọc.

  /**
   * Trạng thái job `translate` của bản VỪA TẠO — `null` khi không có job nào thuộc bản
   * đang xem trong kênh này.
   *
   * ⚠️ Đây KHÔNG phải thanh tiến trình thứ hai: nó là TRẠNG THÁI, để cột phải nói ra
   * "đang dịch…" thay vì để trống. Phần trăm THẬT nằm ở job/SSE.
   */
  trangThaiJobMoi: Job["state"] | null;

  /** Câu "bản đang xem chưa dịch xong — xuất bản N", hoặc `null` khi không lệch. */
  cauXuatCho: string | null;

  /** Chi phí ước lượng của chế độ CHIMERA (§4.5) — `null` khi chưa bật hoặc chưa đo được. */
  chiPhiChimera: { segments: number; calls_per_batch: number; multiplier: number } | null;
  dangDocChiPhi: boolean;
  loiChiPhi: string | null;

  /**
   * NGHE LẠI 300 ms quanh một mốc — yêu cầu của `App` sau mỗi lần nudge (spec UI §5.2).
   *
   * ⚠️ `lan` (số thứ tự) là bắt buộc: hai lần nudge về CÙNG một mốc là HAI yêu cầu khác
   * nhau, và một hiệu ứng chỉ phụ thuộc `giay` sẽ bỏ qua yêu cầu thứ hai.
   */
  ngheLai: { giay: number; lan: number } | null;

  // ── VÙNG KÊNH (2026-10-30) ─────────────────────────────────────────────────────
  // 🔴 NĂM prop này là ĐƯỜNG VÀO của cả app. Chúng từng nằm trong `ChannelZone` cũ; khi
  // tệp đó bị xoá, phép đo trên bản build cho `[class*=ch__]` = **0** — app không còn
  // cách nào nạp tệp, nên `transcript` mãi là `null` và bàn làm việc trống vĩnh viễn.
  sources: readonly Source[];
  sourcesLoading: boolean;
  sourcesError: string | null;
  onChonKenh: (id: number) => void;
  onXoaKenhDaCo: (id: number) => Promise<void>;
}

export function Studio(props: StudioProps) {
  const {
    source,
    transcript,
    banDich,
    cps,
    jobs,
    takeTheoDoan,
    daDuyet,
    thuatNgu,
    mediaUrl,
    dangLuu,
    loiGhi,
    coFileXuat,
    onDuyet,
    onSuaChu,
    onXuatSrt,
    onXuatVideo,
    onBuoc,
    onSuaMoc,
    onLongLai,
    sources,
    sourcesLoading,
    sourcesError,
    onChonKenh,
    onXoaKenhDaCo,
    onNapTep,
  } = props;

  const [goc, datGoc] = useState<GocNhin>("bien-tap");
  const [pxPerSec, datPxPerSec] = useState(40);
  const [locViec, datLocViec] = useState<LoaiViec | "tat-ca">("tat-ca");
  const [chiCoViec, datChiCoViec] = useState(false);
  const [moLenh, datMoLenh] = useState(false);
  const [song, datSong] = useState<number[]>([]);
  const [thongBao, datThongBao] = useState<string | null>(null);
  const [chon, datChon] = useState<number | null>(null);
  const [hangDoiMo, datHangDoiMo] = useState(false);

  const player = usePlayer(mediaUrl);
  const dongRef = useRef(new Map<number, HTMLLIElement>());

  /** Bản đồ `Segment.i → chữ bản dịch`. Một chỗ dựng, ba chỗ đọc. */
  const banDichMap = useMemo(() => bangBanDich(banDich), [banDich]);

  /** Đoạn để HIỂN THỊ: mốc từ bản ghi, chữ bản dịch áp lên `t`. */
  const doan = useMemo<Segment[]>(() => {
    const ds = transcript?.segments ?? [];
    return ds.map((s) => {
      const chu = banDichMap.get(s.i);
      return chu === undefined ? s : { ...s, t: chu };
    });
  }, [transcript, banDichMap]);

  /**
   * MỌI việc cần xử lý. ⚠️ Dùng `transcript` làm nguồn, không dùng `banDich.segments`:
   * CPS của máy chủ tính trên cửa sổ NGUỒN và gắn với `Segment.i` của bản GHI.
   */
  const viec = useMemo(
    () => viecCuaBanGhi(transcript, cps, takeTheoDoan, daDuyet),
    [transcript, cps, takeTheoDoan, daDuyet],
  );

  const demTheoLoai = useMemo(() => {
    const dem: Record<LoaiViec, number> = { "nghi-ngo": 0, cps: 0, nen: 0 };
    for (const v of viec) dem[v.loai] += 1;
    return dem;
  }, [viec]);

  /** Việc đang hiện sau khi lọc — chip lọc ở cột trái quyết định. */
  const viecHien = useMemo(
    () => (locViec === "tat-ca" ? viec : viec.filter((v) => v.loai === locViec)),
    [viec, locViec],
  );

  /** Đoạn đang hiện trong danh sách. `chiCoViec` lọc theo tập `Segment.i` có việc. */
  const doanHien = useMemo(() => {
    if (!chiCoViec) return doan;
    const coViec = new Set(viecHien.map((v) => v.i));
    return doan.filter((s) => coViec.has(s.i));
  }, [doan, chiCoViec, viecHien]);

  /** Đoạn ĐANG PHÁT — suy từ `player.time`, nửa khoảng `[start, end)`. */
  const dangPhat = useMemo(() => {
    const t = player.time;
    for (const s of doan) if (t >= s.start && t < s.end) return s.i;
    return null;
  }, [doan, player.time]);

  /** Đoạn ĐANG CHỌN: ưu tiên lựa chọn tay, rồi tới đoạn đang phát, rồi đoạn đầu. */
  const doanChon = chon ?? dangPhat ?? (doan.length > 0 ? doan[0].i : null);

  /** Job `dub` và `tron_nen` của bản dịch đang xem. */
  const jobDub = useMemo(
    () =>
      jobs.find(
        (j) =>
          j.type === "dub" &&
          banDich !== null &&
          (j.payload["translation_id"] === banDich.id || j.payload["tid"] === banDich.id),
      ),
    [jobs, banDich],
  );
  // ⚠️ KHONG co job `tron_nen`: `JobType` cua backend la
  // `"ingest" | "asr" | "translate" | "export" | "dub"` — DA DO. Viec tron nen la mot BUOC
  // BEN TRONG job `dub` (payload `tron_nen`), khong phai mot job rieng, nen khong co gi de
  // tim o day. Buoc `ghep` vi the nhan `null` va hien "can long tieng xong".
  const cacBuoc = useMemo(
    () =>
      duongOng({
        coBanGhi: transcript !== null,
        engineAsr: transcript?.engine ?? null,
        coBanDich: banDich !== null,
        engineMt: banDich?.engine ?? null,
        soViec: viec.length,
        dubState: tuJobState(jobDub?.state),
        ghepState: null,
        coFileXuat,
      }),
    [transcript, banDich, viec.length, jobDub, coFileXuat],
  );

  const lyDoXuat = lyDoChuaXuatDuoc(cacBuoc);

  /** Đoạn đang chọn, dạng đầy đủ — dùng cho khối thông tin ở sân khấu. */
  const doanDayDu = useMemo(() => doan.find((s) => s.i === doanChon) ?? null, [doan, doanChon]);

  // ── SÓNG ÂM THẬT ────────────────────────────────────────────────────────────────
  // Đọc lại mỗi khi ĐỔI TỆP (không phải mỗi lần đổi kênh hay đổi bản dịch): `docSong`
  // giải mã cả tệp, nên gọi thừa là một phép đo 240 MB lặp lại vô ích.
  useEffect(() => {
    let huy = false;
    datSong([]);
    if (mediaUrl === null) return;
    void docSong(mediaUrl).then((kq) => {
      if (!huy) datSong(kq);
    });
    return () => {
      huy = true;
    };
  }, [mediaUrl]);

  // Thông báo tự tắt — 3,2 giây, đúng nhịp bản đã duyệt.
  useEffect(() => {
    if (thongBao === null) return;
    const hen = window.setTimeout(() => datThongBao(null), 3200);
    return () => window.clearTimeout(hen);
  }, [thongBao]);

  /** Chọn một đoạn: đặt lựa chọn tay + tua đầu phát tới đầu đoạn. */
  const chonDoan = useCallback(
    (i: number) => {
      datChon(i);
      const s = doan.find((x) => x.i === i);
      if (s !== undefined) player.seek(s.start);
    },
    [doan, player],
  );

  /** Đi tới việc kế/trước trong danh sách ĐANG LỌC. Hết vòng thì quay lại đầu. */
  const diViec = useCallback(
    (huong: 1 | -1) => {
      const ds = [...new Set(viecHien.map((v) => v.i))];
      if (ds.length === 0) {
        datThongBao("Hết việc cần xử lý");
        return;
      }
      const viTri = doanChon === null ? -1 : ds.indexOf(doanChon);
      let ke: number;
      if (viTri === -1) ke = huong === 1 ? ds[0] : ds[ds.length - 1];
      else ke = ds[(viTri + huong + ds.length) % ds.length];
      chonDoan(ke);
    },
    [viecHien, doanChon, chonDoan],
  );


  /** Bật/tắt phát lặp đoạn đang chọn. */
  const batTatLap = useCallback(() => {
    if (player.loop !== null) {
      player.setLoop(null);
      return;
    }
    if (doanDayDu === null) return;
    player.setLoop({ start: doanDayDu.start, end: doanDayDu.end });
    player.seek(doanDayDu.start);
    player.play();
  }, [player, doanDayDu]);

  /** Đặt giờ vào/ra tại ĐẦU PHÁT hiện tại. */
  const datMoc = useCallback(
    (edge: "start" | "end") => {
      if (doanDayDu === null) return;
      onSuaMoc(doanDayDu.i, edge, Math.round(player.time * 100) / 100);
    },
    [doanDayDu, player.time, onSuaMoc],
  );

  /** Lệnh của bảng `Ctrl+K`. */
  const lenh = useMemo<Lenh[]>(
    () => [
      { id: "phat", nhan: player.playing ? "Tạm dừng" : "Phát", phim: "Space", chay: player.toggle },
      { id: "ke", nhan: "Việc kế tiếp", phim: "J", chay: () => diViec(1) },
      { id: "truoc", nhan: "Việc trước", phim: "K", chay: () => diViec(-1) },
      { id: "duyet", nhan: "Duyệt đoạn đang chọn", phim: "Enter", chay: () => { if (doanChon !== null) onDuyet(doanChon); } },
      { id: "vao", nhan: "Đặt giờ vào tại đầu phát", phim: "I", chay: () => datMoc("start") },
      { id: "ra", nhan: "Đặt giờ ra tại đầu phát", phim: "O", chay: () => datMoc("end") },
      { id: "lap", nhan: player.loop === null ? "Bật phát lặp đoạn" : "Tắt phát lặp đoạn", phim: "L", chay: batTatLap },
      { id: "goc1", nhan: "Xem: Biên tập", phim: "1", chay: () => datGoc("bien-tap") },
      { id: "goc2", nhan: "Xem: Đối chiếu", phim: "2", chay: () => datGoc("doi-chieu") },
      { id: "goc3", nhan: "Xem: Lồng tiếng", phim: "3", chay: () => datGoc("long-tieng") },
      { id: "chi-viec", nhan: chiCoViec ? "Hiện mọi đoạn" : "Chỉ hiện đoạn có vấn đề", chay: () => datChiCoViec((v) => !v) },
      { id: "srt", nhan: "Tải phụ đề .srt", chay: onXuatSrt },
      { id: "video", nhan: "Tải video hoàn chỉnh", chay: onXuatVideo },
    ],
    [player, diViec, doanChon, onDuyet, datMoc, batTatLap, chiCoViec, onXuatSrt, onXuatVideo],
  );

  // ── PHÍM TẮT TOÀN CỤC ───────────────────────────────────────────────────────────
  // `Ctrl+K` mở bảng lệnh; khi bảng mở hoặc đang gõ trong ô nhập thì MỌI phím tắt khác
  // đứng im. Không chặn thì gõ "phat" vào ô tìm vừa lọc vừa phát video.
  useEffect(() => {
    const nghe = (e: KeyboardEvent) => {
      const dich = e.target;
      const dangGo = dich instanceof HTMLElement && (dich.tagName === "INPUT" || dich.tagName === "TEXTAREA" || dich.isContentEditable);

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        datMoLenh((m) => !m);
        return;
      }
      if (moLenh || dangGo) return;

      switch (e.key) {
        case " ":
          e.preventDefault();
          player.toggle();
          break;
        case "j":
        case "J":
          e.preventDefault();
          diViec(1);
          break;
        case "k":
        case "K":
          e.preventDefault();
          diViec(-1);
          break;
        case "Enter":
          if (doanChon !== null) {
            e.preventDefault();
            onDuyet(doanChon);
          }
          break;
        case "i":
        case "I":
          e.preventDefault();
          datMoc("start");
          break;
        case "o":
        case "O":
          e.preventDefault();
          datMoc("end");
          break;
        case "l":
        case "L":
          e.preventDefault();
          batTatLap();
          break;
        case "1":
          datGoc("bien-tap");
          break;
        case "2":
          datGoc("doi-chieu");
          break;
        case "3":
          datGoc("long-tieng");
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", nghe);
    return () => window.removeEventListener("keydown", nghe);
  }, [moLenh, player, diViec, doanChon, onDuyet, datMoc, batTatLap]);

  // Cuộn dòng đang chọn vào vùng nhìn thấy.
  useEffect(() => {
    if (doanChon === null) return;
    dongRef.current.get(doanChon)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [doanChon]);

  /** Bấm một bước đường ống ⇒ nhảy tới chỗ liên quan. */
  const bamBuoc = useCallback(
    (id: string) => {
      if (id === "duyet") {
        if (viec.length > 0) diViec(1);
        else datThongBao("Đã duyệt hết");
        return;
      }
      if (id === "long") {
        datGoc("long-tieng");
        return;
      }
      if (id === "dich") {
        datGoc("doi-chieu");
        return;
      }
      if (id === "xuat") {
        if (lyDoXuat !== null) datThongBao(`Chưa xuất được: ${lyDoXuat}`);
        else onXuatVideo();
        return;
      }
      datGoc("bien-tap");
      onBuoc(id);
    },
    [viec.length, diViec, lyDoXuat, onXuatVideo, onBuoc],
  );

  const daDuyetCount = daDuyet.size;
  const tiLeDuyet = doan.length === 0 ? 0 : (daDuyetCount / doan.length) * 100;

  return (
    <div className="studio">
      {/* ── HEADER ─────────────────────────────────────────────────────────────── */}
      <header className="studio__dau">
        <h1 className="head__ten">PHÒNG THU BIÊN TẬP</h1>
        <div className="studio__do">
          <PipelineBar buoc={cacBuoc} onBuoc={bamBuoc} />
        </div>
        <button type="button" className="studio__lenh-nut" onClick={() => datMoLenh(true)}>
          Lệnh <span className="kbd">Ctrl K</span>
        </button>
      </header>

      {/* ── THÂN: BA CỘT ───────────────────────────────────────────────────────── */}
      <div className="studio__than">
        {/* CỘT TRÁI — HỘP VIỆC */}
        <aside className="studio__trai">
          {/* VÙNG KÊNH — ĐƯỜNG VÀO của cả app (xem `ChannelZone`). Nó nằm TRÊN hộp việc
              trong CÙNG cột 260px: thêm một cột thứ tư là đổi hình học đã đo. */}
          <ChannelZone
            sources={sources}
            selectedId={source === null ? null : source.id}
            loading={sourcesLoading}
            error={sourcesError}
            onSelect={onChonKenh}
            onNapTep={onNapTep}
            onXoa={onXoaKenhDaCo}
          />
          <aside className="hop-viec" aria-label="Việc cần xử lý">
          <div className="hop-viec__dau">
            <div className="hop-viec__hang">
              <span className="nhan-khac">Việc cần xử lý</span>
              <span className={viec.length > 0 ? "hop-viec__so is-canh-bao" : "hop-viec__so"}>{viec.length}</span>
            </div>
            <div className="hop-viec__thanh" role="progressbar" aria-valuemin={0} aria-valuemax={doan.length} aria-valuenow={daDuyetCount}>
              <div className="hop-viec__thanh-ruot" style={{ width: `${tiLeDuyet}%` }} />
            </div>
            <p className="hop-viec__dem">
              đã duyệt {daDuyetCount}/{doan.length} đoạn
            </p>
            <div className="hop-viec__chip-hop">
              <button
                type="button"
                className={locViec === "tat-ca" ? "chip is-chon" : "chip"}
                onClick={() => datLocViec("tat-ca")}
              >
                Tất cả <span className="num">{viec.length}</span>
              </button>
              {(Object.keys(NHAN_LOAI_VIEC) as LoaiViec[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  className={locViec === k ? "chip is-chon" : "chip"}
                  onClick={() => datLocViec(k)}
                >
                  {NHAN_LOAI_VIEC[k]} <span className="num">{demTheoLoai[k]}</span>
                </button>
              ))}
            </div>
          </div>

          <ul className="hop-viec__ds">
            {viecHien.map((v) => {
              const s = doan.find((x) => x.i === v.i);
              return (
                <li key={`${v.i}-${v.loai}`}>
                  <button
                    type="button"
                    className={doanChon === v.i ? "hop-viec__dong is-chon" : "hop-viec__dong"}
                    onClick={() => chonDoan(v.i)}
                  >
                    <div className="hop-viec__dong-dau">
                      <span className="nhan-khac nhan-khac--loi">{v.nhan}</span>
                      <span className="num hop-viec__gio">{s === undefined ? "" : formatTimecode(s.start)}</span>
                    </div>
                    <p className="hop-viec__chu">{s?.t ?? s?.text ?? ""}</p>
                  </button>
                </li>
              );
            })}
            {viecHien.length === 0 ? (
              <li className="hop-viec__trong">Không còn việc nào. Sẵn sàng xuất.</li>
            ) : null}
          </ul>

          <div className="hop-viec__chan">
            <div className="hop-viec__phim">
              <span>Việc kế / trước</span>
              <span><span className="kbd">J</span> <span className="kbd">K</span></span>
            </div>
            <div className="hop-viec__phim">
              <span>Duyệt</span>
              <span className="kbd">Enter</span>
            </div>
          </div>
          </aside>
        </aside>

        {/* CỘT GIỮA — BÀN LÀM VIỆC */}
        <main className="studio__giua">
          {/* SÂN KHẤU */}
          <div className="san-khau">
            <div className="san-khau__video">
              {mediaUrl !== null ? (
                <video ref={player.videoRef} src={mediaUrl} className="san-khau__pt" playsInline preload="metadata" />
              ) : (
                <div className="san-khau__trong">
                  <p>chưa chọn kênh</p>
                  <p className="san-khau__phu">chọn một tệp ở cột KÊNH bên trái</p>
                </div>
              )}
              {dangPhat !== null ? (
                <p className="san-khau__phu-de">{doan.find((s) => s.i === dangPhat)?.t ?? doan.find((s) => s.i === dangPhat)?.text ?? ""}</p>
              ) : null}
            </div>

            <div className="san-khau__phai">
              <div>
                <p className="nhan-khac">Tệp</p>
                <p className="san-khau__ten">{source?.origin ?? "—"}</p>
                {doanDayDu !== null ? (
                  <div className="san-khau__doan">
                    <p className="nhan-khac">Đoạn #{doanDayDu.i}</p>
                    <p className="num san-khau__moc">
                      {formatTimecode(doanDayDu.start)} → {formatTimecode(doanDayDu.end)} ·{" "}
                      {(doanDayDu.end - doanDayDu.start).toFixed(2).replace(".", ",")} s
                    </p>
                    <div className="san-khau__nut-hang">
                      <button type="button" className="nut-nho" onClick={() => datMoc("start")}>
                        Đặt vào <span className="kbd">I</span>
                      </button>
                      <button type="button" className="nut-nho" onClick={() => datMoc("end")}>
                        Đặt ra <span className="kbd">O</span>
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>

              <div className="san-khau__dieu-khien">
                <button type="button" className="nut-chinh" onClick={player.toggle}>
                  {player.playing ? "Dừng" : "Phát"}
                </button>
                <button
                  type="button"
                  className={player.loop === null ? "nut-nho" : "nut-nho is-chon"}
                  onClick={batTatLap}
                  aria-pressed={player.loop !== null}
                  title="Phát lặp đoạn đang chọn (L)"
                >
                  Lặp đoạn
                </button>
                <span className="num san-khau__gio">
                  {formatTimecode(player.time)}{" "}
                  <span className="san-khau__tong">/ {formatTimecode(player.duration)}</span>
                </span>
              </div>
            </div>
          </div>

          {/* DẢI THỜI GIAN */}
          <Timeline
            segments={doan}
            peaks={song}
            duration={player.duration > 0 ? player.duration : (source?.duration ?? 0)}
            time={player.time}
            pxPerSec={pxPerSec}
            currentSegment={doanChon}
            playingSegment={dangPhat}
            chuCuaDoan={(s) => s.t ?? s.text}
            viec={viec}
            onSeek={player.seek}
            onSelect={chonDoan}
            onResize={onSuaMoc}
          />

          {/* THANH GÓC NHÌN */}
          <div className="goc-nhin">
            {BA_GOC_NHIN.map((g) => (
              <button
                key={g.id}
                type="button"
                className={goc === g.id ? "goc-nhin__nut is-chon" : "goc-nhin__nut"}
                onClick={() => datGoc(g.id)}
                aria-pressed={goc === g.id}
              >
                {g.nhan} <span className="kbd">{g.phim}</span>
              </button>
            ))}
            <label className="goc-nhin__loc">
              <input type="checkbox" checked={chiCoViec} onChange={(e) => datChiCoViec(e.target.checked)} />
              Chỉ đoạn có vấn đề
            </label>
            <label className="goc-nhin__thu-phong">
              Thu phóng
              <input
                type="range"
                min={10}
                max={160}
                value={pxPerSec}
                onChange={(e) => datPxPerSec(Number(e.target.value))}
              />
            </label>
          </div>

          {/* DANH SÁCH ĐOẠN */}
          <ul className="ds-doan">
            {doanHien.map((s) => (
              <SegmentRow
                key={s.i}
                ref={(el) => {
                  if (el === null) dongRef.current.delete(s.i);
                  else dongRef.current.set(s.i, el);
                }}
                seg={s}
                current={s.i === doanChon}
                goc={goc}
                banDich={banDichMap.get(s.i) ?? null}
                daDuyet={daDuyet.has(s.i)}
                take={takeTheoDoan.get(s.i) ?? null}
                viec={viec}
                thuatNgu={thuatNgu}
                dangLuu={dangLuu}
                loiGhi={loiGhi.get(s.i) ?? null}
                onSelect={() => chonDoan(s.i)}
                onSuaChu={(chu) => onSuaChu(s.i, chu)}
                onDuyet={() => onDuyet(s.i)}
                onNgheThu={() => {
                  player.setLoop({ start: s.start, end: s.end });
                  player.seek(s.start);
                  player.play();
                }}
                onLongLai={() => onLongLai(s.i)}
              />
            ))}
          </ul>
        </main>

        {/* CỘT PHẢI — HÀNG ĐỢI THU GỌN */}
        <aside className={hangDoiMo ? "hang-doi is-mo" : "hang-doi"} aria-label="Hàng đợi">
          <button
            type="button"
            className="hang-doi__nut"
            onClick={() => datHangDoiMo((m) => !m)}
            aria-expanded={hangDoiMo}
            title="Hàng đợi"
          >
            <span className="hang-doi__icon" aria-hidden="true">▤</span>
            {hangDoiMo ? <span className="nhan-khac">Hàng đợi</span> : null}
          </button>
          {hangDoiMo ? (
            <ul className="hang-doi__ds">
              {jobs.length === 0 ? (
                <li className="hang-doi__trong">chưa có job nào</li>
              ) : (
                jobs.map((j) => (
                  <li key={j.id} className="hang-doi__job">
                    <div className="hang-doi__job-dau">
                      <span className="num hang-doi__job-ten">#{j.id} {j.type}</span>
                      <span className={j.state === "done" ? "hang-doi__tt is-xong" : "hang-doi__tt"}>{j.state}</span>
                    </div>
                    {j.progress > 0 && j.progress < 100 ? (
                      <div className="hang-doi__tien-do">
                        <div className="hang-doi__tien-do-ruot" style={{ width: `${j.progress}%` }} />
                      </div>
                    ) : null}
                  </li>
                ))
              )}
            </ul>
          ) : null}
        </aside>
      </div>

      {/* THÔNG BÁO */}
      {thongBao === null ? null : (
        <div className="thong-bao" role="status">{thongBao}</div>
      )}

      <CommandPalette mo={moLenh} onDong={() => datMoLenh(false)} lenh={lenh} />
    </div>
  );
}
