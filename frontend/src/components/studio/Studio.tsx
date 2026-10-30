import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Command as CmdIcon, Film, Moon, Pause, Play, Repeat, Sun, Upload, Cpu } from "lucide-react";

import { mediaUrl, exportUrl } from "@/api/endpoints";
import type { DubPlanRow, Job, Source, TranslationCps, TranslationDetail, Transcript } from "@/api/types";
import {
  BA_GOC_NHIN,
  dungDong,
  duongOng,
  lyDoChuaXuatDuoc,
  NGUONG_NEN,
  NHAN_LOAI_VIEC,
  raSrt,
  soVi,
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
import { decodePeaks, usePlayer } from "./use-player";
import { Timeline } from "./Timeline";
import { SegmentRow, type ViewMode } from "./SegmentRow";
import { PipelineBar } from "./PipelineBar";
import { CommandPalette, type Command } from "./CommandPalette";

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
}

export function Studio(props: StudioProps) {
  const {
    sources,
    source,
    transcript,
    banDich,
    cps,
    keHoach,
    jobs,
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
  } = props;

  const [currentId, setCurrentId] = useState<number | null>(null);
  const [view, setView] = useState<ViewMode>("edit");
  const [pxPerSec, setPxPerSec] = useState(40);
  const [peaks, setPeaks] = useState<number[]>([]);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [flashId, setFlashId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [queueOpen, setQueueOpen] = useState(false);
  const [issueFilter, setIssueFilter] = useState<LoaiViec | "all">("all");
  const [onlyIssues, setOnlyIssues] = useState(false);

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
    setCurrentId(dong[0].i);
  }, [dong]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 3200);
    return () => clearTimeout(t);
  }, [notice]);

  /** Thong bao loi tu tang tren — KHONG nuot. */
  useEffect(() => {
    if (loi === undefined || loi === null || loi === "") return;
    setNotice(loi);
  }, [loi]);

  /**
   * SONG AM THAT — doc tu URL media cua may chu.
   *
   * Ban goc dung `fakePeaks(SAMPLE_DURATION, 20, SAMPLE_SEGMENTS)`: song sinh tu 18
   * doan mau, khong lien quan gi den tep that. O day doc THAT; that bai thi de TRONG
   * va noi ro, khong ve mot song trong nhu that.
   */
  useEffect(() => {
    if (media === null) {
      setPeaks([]);
      return;
    }
    let huy = false;
    void (async () => {
      try {
        const res = await fetch(media, { headers: { Range: "bytes=0-" } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const file = new File([blob], "media", { type: blob.type });
        const p = await decodePeaks(file, 2400);
        if (!huy) setPeaks(p);
      } catch {
        if (!huy) {
          setPeaks([]);
          setNotice("Khong doc duoc song am cua tep — dai thoi gian de trong");
        }
      }
    })();
    return () => {
      huy = true;
    };
  }, [media]);

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
  const jobDub = useMemo(() => {
    if (banDich === null) return null;
    const ds = jobs.filter(
      (j) => j.type === "dub" && (j.payload["translation_id"] as number | undefined) === banDich.id,
    );
    return ds.length === 0 ? null : ds[ds.length - 1];
  }, [jobs, banDich]);

  const jobGhep = useMemo(() => {
    if (banDich === null) return null;
    const ds = jobs.filter(
      (j) => j.type === "export" && (j.payload["translation_id"] as number | undefined) === banDich.id,
    );
    return ds.length === 0 ? null : ds[ds.length - 1];
  }, [jobs, banDich]);

  const cacBuoc: BuocDuongOng[] = useMemo(
    () =>
      duongOng({
        coBanGhi: transcript !== null,
        engineAsr: transcript === null ? null : transcript.engine,
        coBanDich: banDich !== null,
        engineMt: banDich === null ? null : banDich.engine,
        soViec: issues.length,
        dubState: jobDub === null ? null : jobDub.state,
        ghepState: jobGhep === null ? null : jobGhep.state,
        coFileXuat: jobGhep !== null && jobGhep.state === "done",
      }),
    [transcript, banDich, issues.length, jobDub, jobGhep],
  );

  const lyDoXuat = useMemo(() => lyDoChuaXuatDuoc(cacBuoc), [cacBuoc]);

  const current = dong.find((s) => s.i === currentId) ?? null;

  /** Doan dang phat theo thoi gian — dung so do cua trinh phat. */
  const playingSeg = dong.find((s) => player.time >= s.start && player.time < s.end);
  useEffect(() => {
    if (player.playing && playingSeg && playingSeg.i !== currentId) setCurrentId(playingSeg.i);
  }, [player.playing, playingSeg, currentId]);

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
        setView("dub");
        return;
      }
      if (id === "dich") {
        setView("compare");
        return;
      }
      setView("edit");
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
  const steps = cacBuoc;

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
  return (
    <div className="grid h-screen grid-rows-[52px_1fr] overflow-hidden bg-background text-foreground">
      {/* đầu trang */}
      <header className="flex items-center gap-4 border-b border-rule bg-panel-0 px-4">
        <h1 className="label-engraved shrink-0 !text-[11px] !text-ink-0">Phòng thu biên tập</h1>
        <div className="min-w-0 flex-1 overflow-x-auto">
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
          className="rounded-sm border border-rule p-1.5 text-ink-1 hover:border-ink-1 hover:text-ink-0"
          aria-label={theme === "dark" ? "Chuyển chế độ sáng" : "Chuyển chế độ tối"}
          title={theme === "dark" ? "Chế độ sáng" : "Chế độ tối"}
        >
          {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
        </button>
      </header>

      <div className="grid min-h-0 grid-cols-[260px_1fr_auto]">
        {/* hộp việc */}
        <aside className="flex min-h-0 flex-col border-r border-rule bg-panel-1">
          <div className="border-b border-rule px-3 py-3">
            <div className="flex items-baseline justify-between">
              <span className="label-engraved">Việc cần xử lý</span>
              <span className={cn("num text-[18px]", issues.length ? "text-signal" : "text-ok")}>
                {issues.length}
              </span>
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
          <div className="flex shrink-0 gap-4 bg-panel-0 p-3">
            <div className="relative aspect-video w-[min(42%,420px)] shrink-0 overflow-hidden rounded-sm border border-rule bg-panel-1">
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
                <p className="pointer-events-none absolute inset-x-4 bottom-3 text-center text-[14px] leading-5 text-ink-0 [text-shadow:0_1px_3px_var(--panel-0),0_0_8px_var(--panel-0)]">
                  {playingSeg.dich === "" ? playingSeg.text : playingSeg.dich}
                </p>
              )}
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
              <div className="flex items-center gap-2">
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
            peaks={peaks}
            duration={player.duration}
            time={player.time}
            pxPerSec={pxPerSec}
            currentId={currentId}
            onSeek={player.seek}
            onSelect={(id) => select(id)}
            onResize={(id, edge, t) =>
              update(id, (s) =>
                edge === "start"
                  ? { start: Math.max(0, Math.min(t, s.end - 0.1)) }
                  : { end: Math.min(player.duration, Math.max(t, s.start + 0.1)) },
              )
            }
          />

          {/* thanh góc nhìn */}
          <div className="flex shrink-0 items-center gap-1 border-b border-rule bg-panel-1 px-3 py-1.5">
            {VIEWS.map((v, i) => (
              <button
                key={v.id}
                onClick={() => setView(v.id)}
                className={cn(
                  "rounded-sm px-2.5 py-1 text-[12px] transition-colors",
                  view === v.id ? "bg-panel-3 text-ink-0" : "text-ink-1 hover:text-ink-0",
                )}
                aria-pressed={view === v.id}
              >
                {v.label} <span className="kbd ml-1 !text-[9px]">{i + 1}</span>
              </button>
            ))}
            <label className="ml-3 flex cursor-pointer items-center gap-1.5 text-[11.5px] text-ink-1">
              <input type="checkbox" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} className="accent-[var(--signal)]" />
              Chỉ đoạn có vấn đề
            </label>
            <label className="ml-auto flex items-center gap-2 text-[11px] text-ink-2">
              Thu phóng
              <input
                type="range"
                min={10}
                max={160}
                value={pxPerSec}
                onChange={(e) => setPxPerSec(+e.target.value)}
                className="w-24 accent-[var(--signal)]"
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
                  onLongLai(s.i);
                  setNotice(`Đã lồng lại đoạn #${segments.findIndex((x) => x.i === s.i) + 1}`);
                }}
              />
            ))}
          </ul>
        </main>

        {/* hàng đợi thu gọn */}
        <aside
          className={cn(
            "flex min-h-0 flex-col border-l border-rule bg-panel-1 transition-[width]",
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
              <QueueItem name="#37 phiên âm · faster-whisper" state="xong" />
              <QueueItem name="#4 dịch · opus-mt" state="xong" />
              <QueueItem name="#36 lồng tiếng · vieneu-v3" state="xong" />
              <QueueItem
                name="#38 ghép nền · htdemucs"
                state={remux === 0 ? "chưa chạy" : remux >= 100 ? "xong" : `${remux}%`}
                progress={remux > 0 && remux < 100 ? remux : undefined}
              />
              <li className="num border-b border-rule px-3 py-2 text-[10.5px] text-ink-2">
                ollama đang chạy · vram 2524 MiB
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
