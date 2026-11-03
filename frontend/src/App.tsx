import { useCallback, useEffect, useMemo, useState } from "react";

import {
  approveTranscript,
  createTranslation,
  endpoints,
  getDubPlan,
  getTranscript,
  getTranslation,
  listSources,
  patchSegmentTiming,
  patchSourceVungDoc,
  patchTranslation,
  registry,
  status,
} from "@/api/endpoints";
import type {
  DubPlanRow,
  Job,
  Source,
  Status,
  TranslationCps,
  TranslationDetail,
  Transcript,
} from "@/api/types";
import { Studio } from "@/components/studio/Studio";
import { VUNG_DOC_MAC_DINH, type VungDoc } from "@/components/studio/VungDoc";

/**
 * TANG NOI API — CHO DUY NHAT doc/ghi backend.
 *
 * 🔴 VI SAO TACH KHOI `Studio`:
 *   `Studio.tsx` la BAN SAO NGUYEN VAN phan JSX cua `_lovable-code/.../Studio.tsx`
 *   (326 dong). Neu nhet `fetch` vao do thi moi lan API doi hinh dang lai phai sua
 *   JSX, va moi lan sua JSX la mot cho co the lech hinh hoc da do. Tach ra day:
 *   `Studio` nhan du lieu qua props, khong biet `fetch` la gi.
 *
 *   Ban goc `shell/App.tsx` (1 780 dong) lam NGUOC LAI — no vua giu state, vua goi
 *   API, vua dung 27 props cho `Studio`, vua chua bon man hinh khac. Tepe nay chi
 *   lam dung mot viec: nap du lieu cho `Studio` va chuyen tiep bon hanh dong ghi.
 *
 * ## Bay du lieu, dung bay nguon THAT
 *
 *   `sources`        GET /api/sources
 *   `source`         phan tu duoc chon trong `sources`
 *   `transcript`     GET /api/transcripts/{id}   (ban ghi cua source dang chon)
 *   `banDich`        GET /api/translations/{id}  (ban dich moi nhat cua transcript)
 *   `cps`            `banDich.cps` — SO CUA MAY CHU, khong tu tinh
 *   `keHoach`        GET /api/dubs/{id}/plan     (CA HANG ke hoach, co `need` may chu tinh san)
 *   `jobs`           GET /api/jobs               (trang thai buoc + hang doi)
 *
 * ⚠️ `daDuyet` la tap CUC BO, khong phai truong may chu: backend duyet CA BAN GHI
 * (`POST /api/transcripts/{id}/approve`), khong duyet tung dong. Tap nay chi de
 * giao dien danh dau "da xem" — no KHONG duoc gui len nhu mot su that.
 */

/** Nhip lam moi cua `GET /api/jobs` — du job chay lau, khong can SSE o day. */
const NHIP_JOB_MS = 2000;

/**
 * Nhip lam moi cua `GET /api/status` — CHAM hon `jobs` la chu y.
 *
 * `vram` phai hoi `nvidia-smi`/ollama, dat hon mot truy van SQLite, va no khong can min
 * toi 2 giay: con so do chi de nguoi dung biet may con cho hay da day.
 */
const NHIP_MAY_CHU_MS = 5000;

/**
 * DẤU VÂN TAY của hàng đợi: chỉ đổi khi có job ĐỔI TRẠNG THÁI.
 *
 * 🔴 VÌ SAO CẦN (lỗi thật, người dùng báo "khi mở một video mới thì phải refresh trang
 * nó mới refresh state"): `jobs` được làm mới mỗi 2 giây, nhưng `sources` và
 * `transcript` chỉ nạp MỘT LẦN. Nên khi job `ingest` xong và ghi `audio_path`/
 * `duration` vào nguồn, giao diện vẫn giữ bản `source` cũ với `audio_path: null` — nó
 * tưởng video chưa bóc xong âm thanh, và bản ghi mới do job `asr` tạo ra không bao giờ
 * hiện. Chỉ F5 mới thấy.
 *
 * Vì sao KHÔNG đưa `jobs` vào deps của hai effect đó: `setJobs` tạo một MẢNG MỚI mỗi
 * 2 giây kể cả khi không có gì đổi, nên deps `[jobs]` sẽ gọi `GET /api/sources` +
 * `GET /api/transcripts` + `GET /api/transcripts/{id}` mỗi 2 giây, mãi mãi. Dấu vân
 * tay chỉ đổi khi một job thật sự chuyển trạng thái.
 *
 * KHÔNG gồm `progress`: nó đổi liên tục trong lúc chạy (mỗi checkpoint), nên dấu vân
 * tay sẽ đổi suốt một job dài — đúng thứ cần tránh. Chỉ `state` quyết định "job này đã
 * sinh ra dữ liệu mới hay chưa".
 */
function dauVanTay(jobs: readonly Job[]): string {
  return jobs.map((j) => `${j.id}:${j.state}`).join(",");
}

export function App() {
  const [sources, setSources] = useState<Source[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [sourceId, setSourceId] = useState<number | null>(null);

  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [banDich, setBanDich] = useState<TranslationDetail | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  /** `GET /api/status` — `null` = chua doc duoc, khac "0 MiB". */
  const [mayChu, setMayChu] = useState<Status | null>(null);
  const [keHoach, setKeHoach] = useState<ReadonlyMap<number, DubPlanRow>>(new Map());
  const [daDuyet, setDaDuyet] = useState<ReadonlySet<number>>(new Set());
  const [loi, setLoi] = useState<string | null>(null);

  const source = useMemo(
    () => (sourceId === null ? null : (sources.find((s) => s.id === sourceId) ?? null)),
    [sources, sourceId],
  );

  /**
   * VÙNG ĐỌC OCR của nguồn đang mở — dẫn xuất từ `source.vung_doc`, KHÔNG phải state
   * riêng.
   *
   * 🔴 VÌ SAO DẪN XUẤT CHỨ KHÔNG GIỮ STATE (đây là đính chính của chính tôi): bản đầu
   * tôi để `useState<VungDoc | null>(VUNG_DOC_MAC_DINH)` vì cho rằng đây là tham số
   * của MỘT LƯỢT bóc băng. Sai ở hai điểm, cả hai đều đo được:
   *
   *   1. Nó mất khi tải lại trang, nên người dùng phải kéo khung lại cho mỗi video —
   *      trong khi vùng watermark là thuộc tính của VIDEO (`8f4b5304daf42569.mp4` có
   *      watermark ở `y=35-102`, `ac5df767b9e0c878.mp4` ở chỗ khác).
   *   2. Một state song song với DB là hai nguồn sự thật cho cùng một con số. Sau khi
   *      lưu, cái nào thắng? Không có câu trả lời đúng, chỉ có thứ tự ghi.
   *
   * Nay `sources` (nạp từ `GET /api/sources`) là nguồn sự thật DUY NHẤT, và
   * `onVungDoc` ghi qua `PATCH` rồi thay hàng trong danh sách bằng hàng máy chủ trả về.
   *
   * Ba trạng thái của cột, đọc THẲNG không qua truthiness:
   *   `null`/`undefined` — chưa chọn ⇒ dùng `VUNG_DOC_MAC_DINH`
   *   `[]`               — đã TẮT lọc vùng (nút ×) ⇒ `null` cho khung
   *   bốn số             — vùng đã chọn
   *
   * ⚠️ `vung_doc?.length ? ... : mặc_định` là SAI: `[]` falsy nên nút × biến thành
   * "dùng mặc định", và watermark vẫn bị lọc dù người dùng đã tắt.
   */
  const vungDoc: VungDoc | null = useMemo(() => {
    const v = source?.vung_doc;
    if (v === null || v === undefined) return VUNG_DOC_MAC_DINH;
    if (v.length === 0) return null;
    return [v[0], v[1], v[2], v[3]];
  }, [source]);

  /** KENH — nap mot lan khi mo trang, va moi khi mot job `ingest` xong. */
  const napKenh = useCallback(async () => {
    setSourcesLoading(true);
    try {
      const ds = await listSources();
      setSources(ds);
      setSourcesError(null);
      // Chon kenh dau tien mot lan, khong ghi de lua chon cua nguoi dung.
      setSourceId((cu) => (cu === null && ds.length > 0 ? ds[0].id : cu));
    } catch (e) {
      setSourcesError(e instanceof Error ? e.message : String(e));
    } finally {
      setSourcesLoading(false);
    }
  }, []);

  /**
   * Danh sách kênh — nạp khi mở trang VÀ mỗi khi hàng đợi đổi trạng thái.
   *
   * 🔴 `soJob` trong deps chính là bản sửa cho "phải refresh trang nó mới refresh
   * state". Không có nó thì `ingest` chạy xong (ghi `audio_path`/`duration`) mà
   * `sources` vẫn là bản chụp lúc mở trang: `source.audio_path` còn `null`, nên guard
   * "chưa bóc xong âm thanh" báo sai và người dùng tưởng video chưa nạp.
   *
   * `soJob` là CHUỖI (xem `dauVanTay`), nên phép so sánh của React là so GIÁ TRỊ: hai
   * chuỗi giống nhau thì effect không chạy lại, dù `jobs` là mảng mới mỗi 2 giây.
   */
  const soJob = useMemo(() => dauVanTay(jobs), [jobs]);

  // 🔴 EFFECT NAY TUNG BI XOA NHAM — ghi lai de khong lap lai.
  //
  // Luc sua loi chon transcript theo `version`, toi viet lai ca mot khoi `useEffect`
  // va cat luon effect nay. Hau qua do duoc: App chi goi `GET /api/status`,
  // `GET /api/jobs`, `GET /api/registry` — KHONG he goi `GET /api/sources`. Nen
  // `sourceId` mai la `null`, khong bao gio nap transcript, va 14 bai test doi o phu
  // de deu do voi "chua nap xong: chua co o phu de nao".
  //
  // `soJob` trong deps: job `ingest` xong la luc `audio_path`/`duration` doi, va khong
  // co gi khac bao cho effect nay biet.
  useEffect(() => {
    void napKenh();
  }, [napKenh, soJob]);

  useEffect(() => {
    if (sourceId === null) {
      setTranscript(null);
      return;
    }
    let huy = false;
    void (async () => {
      try {
        const ds = await endpoints.listTranscripts();
        const cuaKenh = ds.filter((t) => t.source_id === sourceId);
        if (cuaKenh.length === 0) {
          if (!huy) setTranscript(null);
          return;
        }
        // 🔴 CHON THEO `id`, KHONG THEO `version` — loi that, do duoc 2026-11-02.
        //
        // `version` la SO LAN SUA cua ban ghi, khong phai so thu tu ban ghi. Do
        // tren nguon 6 ngay sau khi chay lai phien am:
        //
        //     #42  version=1   created=2026-11-02T17:14:42Z   <- BAN MOI NHAT
        //     #41  version=2   created=2026-11-01T18:46:33Z   <- ban CU, bi sua 2 lan
        //
        // Ban truoc dung `reduce((a,b) => b.version > a.version ? b : a)`, nen no chon
        // #41 — ban CU — chi vi ban do tung bi chinh tay hai lan. Hau qua do duoc: chay
        // lai phien am sinh ra #42 nhung giao dien VAN mo #41 (va ban dich #43 cua no),
        // nen moi phep do tren man hinh deu ra so lieu cu (94/52 thay vi 124/22).
        //
        // `id` la so tu tang cua lan ghi, nen `id` lon nhat = ban ghi moi nhat.
        const moiNhat = cuaKenh.reduce((a, b) => (b.id > a.id ? b : a));
        const day = await getTranscript(moiNhat.id);
        if (!huy) setTranscript(day);
      } catch (e) {
        if (!huy) setLoi(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      huy = true;
    };
    // `soJob` — job `asr` xong là lúc một bản ghi MỚI xuất hiện, và không có gì khác
    // báo cho effect này biết. Thiếu nó thì bản ghi mới chỉ hiện sau khi F5.
  }, [sourceId, soJob]);

  /**
   * BAN DICH dang xem cua ban ghi — `done` va MOI NHAT.
   *
   * `TranscriptSummary.translations` da co san trong `transcript`, nen khong goi
   * them `listTranslations`. Chon `done` vi mot ban dich dang chay chua co
   * `segments` day du — hien no la hien mot ban dang do.
   */
  useEffect(() => {
    if (transcript === null) {
      setBanDich(null);
      return;
    }
    const xong = transcript.translations.filter((t) => t.status === "done");
    if (xong.length === 0) {
      setBanDich(null);
      return;
    }
    const moiNhat = xong.reduce((a, b) => (b.id > a.id ? b : a));
    let huy = false;
    void (async () => {
      try {
        const day = await getTranslation(moiNhat.id);
        if (!huy) setBanDich(day);
      } catch (e) {
        if (!huy) setLoi(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      huy = true;
    };
  }, [transcript]);

  /** CPS — lay THANG tu ban dich, khong tu chia chu cho giay. */
  const cps: TranslationCps | null = banDich === null ? null : banDich.cps;

  /**
   * TRẠNG THÁI MÁY CHỦ — nguồn của chân panel "Hàng đợi" (`vram`, `ollama`,
   * `queue_depth`).
   *
   * 🔴 VÌ SAO PHẢI CÓ (lỗi thật, người dùng gửi ảnh chụp panel và nói "hàng đợi ở đây
   * có ghi mấy cái đang chạy đâu"): panel đó in `ollama đang chạy · vram 2524 MiB` VIẾT
   * CỨNG trong JSX, bê từ `_lovable-code`. Nó không đọc route nào, nên nó nói một con số
   * không liên quan tới máy đang chạy.
   *
   * Đo được `GET /api/status` trả:
   *
   *     {"queue_depth":0,"running":[],"current_phase":null,"phase_switches":6,
   *      "vram":1518,"vram_unit":"MiB","ollama":"up"}
   *
   * Nhịp RIÊNG, chậm hơn `jobs`: `vram` đọc qua `nvidia-smi`/ollama nên đắt hơn một
   * truy vấn SQLite, và nó không cần mịn tới 2 giây.
   */
  useEffect(() => {
    let huy = false;
    const nap = async () => {
      try {
        const s = await status();
        if (!huy) setMayChu(s);
      } catch {
        // `null` = CHƯA ĐỌC ĐƯỢC, khác "0 MiB". Panel nói rõ điều đó (`dongMayChu`).
        if (!huy) setMayChu(null);
      }
    };
    void nap();
    const t = setInterval(() => void nap(), NHIP_MAY_CHU_MS);
    return () => {
      huy = true;
      clearInterval(t);
    };
  }, []);

  /** JOB — nap lai theo nhip; day cung la nguon trang thai cua sau buoc duong ong. */
  useEffect(() => {
    let huy = false;
    const nap = async () => {
      try {
        const ds = await endpoints.listJobs();
        if (!huy) setJobs(ds);
      } catch {
        // Loi mang o day khong duoc xoa du lieu dang co — chi khong cap nhat them.
      }
    };
    void nap();
    const t = setInterval(() => void nap(), NHIP_JOB_MS);
    return () => {
      huy = true;
      clearInterval(t);
    };
  }, []);

  /**
   * KE HOACH LONG TIENG theo tung dong — chi goi khi DA co ban dich.
   *
   * Giu CA HANG `DubPlanRow`, khong chi `take`: hang do co `need` = `take / avail`
   * DA TINH SAN o may chu. Ban truoc chi lay `take` roi client tu chia cho `slot`,
   * ra `3.2 / 2.04 = 1.57` cho mot dong may chu danh gia `"vua"` (do that tren
   * `GET /api/dubs/4/plan`). Xem `lib/studio.ts::tiLeNen`.
   *
   * `null` = chua long lan nao, va luc do bang RONG (khong phai bang 0).
   */
  useEffect(() => {
    if (banDich === null) {
      setKeHoach(new Map());
      return;
    }
    let huy = false;
    void (async () => {
      try {
        const plan = await getDubPlan(banDich.id);
        if (huy) return;
        const m = new Map<number, DubPlanRow>();
        if (plan !== null) for (const d of plan.dong) m.set(d.i, d);
        setKeHoach(m);
      } catch {
        if (!huy) setKeHoach(new Map());
      }
    })();
    return () => {
      huy = true;
    };
    // 🔴 `soJob` CHỨ KHÔNG PHẢI `jobs` (lỗi thật, đo được khi rà soát state).
    //
    // Bản trước để `[banDich, jobs]`, mà `jobs` là MẢNG MỚI mỗi 2 giây (`setJobs` trong
    // effect polling) kể cả khi không có gì đổi. Nên `GET /api/dubs/{id}/plan` chạy lại
    // MỖI 2 GIÂY, MÃI MÃI, suốt thời gian trang mở — trong khi kế hoạch lồng tiếng chỉ
    // đổi khi một job `dub` chuyển trạng thái. Đó đúng là cái bẫy đã sửa ở hai effect
    // `sources`/`transcript` bằng `soJob`, nhưng bị để nguyên ở đây.
    //
    // `soJob` là chuỗi `id:state`, so sánh theo GIÁ TRỊ: chỉ đổi khi job đổi trạng thái.
  }, [banDich, soJob]);

  // -------------------------------------------------------------------------
  // BON HANH DONG GHI — moi hanh dong goi DUNG mot route
  // -------------------------------------------------------------------------

  /**
   * Lưu vùng đọc OCR — `PATCH /api/sources/{id}/vung-doc`.
   *
   * Vì sao ghi NGAY khi người dùng thả chuột, không đợi tới lúc bấm "Phiên âm": họ
   * vừa chỉ ra một sự thật về video (watermark ở đâu), và sự thật đó phải sống qua lần
   * tải lại trang. Đợi tới lúc chạy job thì một lần đóng tab là mất.
   *
   * `vung === null` là nút ×: gửi `mode: "tat"`, KHÔNG gửi `mode: "mac_dinh"`. Hai thứ
   * đó khác nhau — "tắt" nghĩa là đọc cả khung, "mặc định" nghĩa là quay lại vùng của
   * registry. Gửi nhầm thì nút × chỉ có tác dụng cho tới lần chạy sau.
   *
   * Cập nhật lạc quan TRƯỚC rồi ghi thật (cùng luật với `onSuaChu`): khung phải theo
   * chuột ngay, không giật về vị trí cũ trong lúc chờ mạng. Máy chủ trả về hàng `Source`
   * đã ghi, và hàng đó THAY hàng trong danh sách — nhờ vậy giao diện luôn hiện đúng
   * thứ DB đang có, không phải bản cục bộ vừa đoán.
   */
  const onVungDoc = useCallback(
    (v: VungDoc | null) => {
      if (sourceId === null) return;
      setSources((cu) =>
        cu.map((s) =>
          s.id === sourceId
            ? { ...s, vung_doc: v === null ? [] : [v[0], v[1], v[2], v[3]] }
            : s,
        ),
      );
      void (async () => {
        try {
          const da = await patchSourceVungDoc(
            sourceId,
            v === null
              ? { mode: "tat" }
              : { mode: "dat", vung_doc: [v[0], v[1], v[2], v[3]] },
          );
          setSources((cu) => cu.map((s) => (s.id === da.id ? da : s)));
        } catch (e) {
          setLoi(e instanceof Error ? e.message : String(e));
          // Ghi hỏng thì nạp lại danh sách: khung đang hiện một vùng mà DB KHÔNG có,
          // và để nguyên là nói dối về thứ đã lưu.
          void napKenh();
        }
      })();
    },
    [sourceId, napKenh],
  );

  /** Duyet mot dong: tap CUC BO cua giao dien, khong goi route (backend duyet ca ban ghi). */
  const onDuyet = useCallback((i: number) => {
    setDaDuyet((cu) => {
      const moi = new Set(cu);
      if (moi.has(i)) moi.delete(i);
      else moi.add(i);
      return moi;
    });
  }, []);

  /** Sua CHU cua mot dong — `PATCH /api/translations/{id}`. */
  const onSuaChu = useCallback(
    (i: number, chu: string) => {
      if (banDich === null) return;
      const dong = banDich.segments.find((s) => s.i === i);
      if (dong === undefined) return;
      // Cap nhat lac quan truoc, roi ghi that. Loi thi `loi` hien ra, khong nuot.
      setBanDich((cu) =>
        cu === null
          ? cu
          : { ...cu, segments: cu.segments.map((s) => (s.i === i ? { ...s, t: chu } : s)) },
      );
      void (async () => {
        try {
          await patchTranslation(banDich.id, [
            { i, start: dong.start, end: dong.end, text: chu },
          ]);
          // `patchTranslation` tra TOM TAT (`Translation`), KHONG co `segments`/`cps`.
          // Doc lai bang `getTranslation` de giu nguyen kieu `TranslationDetail`.
          const day = await getTranslation(banDich.id);
          setBanDich(day);
        } catch (e) {
          setLoi(e instanceof Error ? e.message : String(e));
        }
      })();
    },
    [banDich],
  );

  /**
   * Sua MOC cua mot dong — `PATCH /api/transcripts/{id}/segments/{i}`.
   *
   * 🔴 ERRATA #55: ban cu goi `patchTranscript(transcript.id, {segments: [...438
   * dong...]})`, tuc gui TOAN BO danh sach chi de doi mot moc. Ba hau qua do duoc:
   *
   *   1. 438 doan di qua day cho mot thao tac 0,1 giay;
   *   2. `update_transcript_segments` TANG `version`;
   *   3. `is_stale = translated_from_version < transcript_version` ⇒ MOI ban dich
   *      thanh `stale` — nguoi dung chi doi mot moc mà mat ca ban dich da duyet.
   *
   * Moc thuoc BAN GHI (khong thuoc ban dich) nen duong dan van duoi `/transcripts`,
   * nhung la route MOT DOAN, va route do CO Y khong tang `version`: doi moc khong
   * lam cau chu doi, nen ban dich van dung nghia (xem docblock route trong
   * `backend/app/api/routes_transcripts.py`).
   */
  const onSuaMoc = useCallback(
    async (i: number, start: number, end: number) => {
      if (transcript === null) return;
      try {
        const moi = await patchSegmentTiming(transcript.id, i, { start, end });
        setTranscript(moi);
      } catch (e) {
        setLoi(e instanceof Error ? e.message : String(e));
      }
    },
    [transcript],
  );

  /** Xuat video — `App` quyet dinh dua tren du lieu THAT: phai co ban dich da long. */
  const onXuatVideo = useCallback(() => {
    if (banDich === null) {
      setLoi("chua co ban dich — khong xuat duoc");
      return;
    }
    const a = document.createElement("a");
    a.href = `/api/dubs/${banDich.id}/download?format=mp4`;
    a.click();
  }, [banDich]);

  /**
   * Du lieu may chu cho o "He thong" — `GET /api/registry`.
   *
   * Nap MOT lan: registry la danh muc engine, no khong doi trong mot phien.
   *
   * 🔴 `engineAsr` KHONG chi de hien thi: `POST /api/jobs` voi `type: "asr"` BAT BUOC
   * co `engine` (`routes_jobs.ENGINE_REQUIRED = {"asr"}`), va thieu no thi route tra
   * **422 "job loại asr phải có engine"**. Do duoc tren san pham: bam "Phien am" ->
   * 422, khong job nao duoc tao. Ban dau toi chi giu `engineCount` (mot con so de
   * hien "N engine") nen khong co ten engine nao de gui.
   *
   * Lay engine ASR DAU TIEN cua registry chu KHONG hard-code `fw-large-v3`: danh muc
   * la du lieu (`backend/registry.json`), va mot ten viet cung trong giao dien se
   * 422 ngay khi ai do doi registry — dung loai loi chi lo ra luc chay.
   *
   * ⚠️ KHOI NAY PHAI KHAI BAO TRUOC `onBuoc`. Ban sua dau tien dat no o CUOI ham
   * (canh cho `return`), va `onBuoc` o tren doc `engineAsr` -> `tsc` chan:
   *
   *   src/App.tsx(531,14): error TS2448: Block-scoped variable 'engineAsr' used
   *   before its declaration.
   *
   * Va vi module khong bien dich duoc, CA 172 bai test do — khong phai vi hanh vi sai
   * ma vi khong co gi chay. Tri hieu ung "TDZ" cua `const`.
   */
  const [engineCount, setEngineCount] = useState<number | null>(null);
  const [engineAsr, setEngineAsr] = useState<string | null>(null);
  //: Id các engine DỊCH của registry (`GET /api/registry` -> `mt`). Cần DANH SÁCH chứ không
  //: chỉ phần tử đầu: bước `Dịch` phải kiểm được engine của bản dịch đang xem còn hợp lệ
  //: không trước khi dùng lại nó (xem `onBuoc("dich")`).
  const [engineMt, setEngineMt] = useState<string[]>([]);
  useEffect(() => {
    void (async () => {
      try {
        const r = await registry();
        // `Registry` co hai mang theo KIND: `asr` va `mt`. Khong co truong `engines`.
        setEngineCount(r.asr.length + r.mt.length);
        setEngineAsr(r.asr.length > 0 ? r.asr[0].id : null);
        setEngineMt(r.mt.map((e) => e.id));
      } catch {
        // Doc khong duoc thi `null` = CHUA DOC DUOC, khac 0 engine.
        setEngineCount(null);
        setEngineAsr(null);
        setEngineMt([]);
      }
    })();
  }, []);

  /**
   * Chay lai mot buoc — chi bon buoc CO route that.
   *
   * 🔴 GUARD PHAI THEO TUNG BUOC, KHONG CHAN CA HAM (loi that, do duoc).
   *
   * Ban truoc mo dau bang:
   *
   *     if (transcript === null) {
   *       setLoi("chua co ban ghi — khong chay duoc buoc nao");
   *       return;
   *     }
   *
   * Nghia la kenh MOI NAP, chua boc bang lan nao, bam "Phien am" thi KHONG CO GI
   * xay ra: khong job, khong loading, khong hang doi. Nguoi dung bam ma san pham
   * im lang — dung kieu hong ma ca nhanh OCR vua phai sua ba lan.
   *
   * Nhung buoc `asr` KHONG CAN `transcript`: no can `source_id`, va `POST /api/jobs`
   * chi doi `payload.source_id`. Chinh nhanh ben duoi doc `transcript.source_id`,
   * tuc guard kia da dung mot dieu kien cua BUOC SAU de chan BUOC TRUOC. Mot job
   * `asr` chay tren mot kenh chua co ban ghi la truong hop BINH THUONG — do la
   * duong dau tien cua moi kenh.
   *
   * Nen moi buoc tu kiem dieu kien cua no:
   *   `asr`           -> can `source` (kenh dang chon), KHONG can `transcript`
   *   `dich`,`duyet`  -> can `transcript`
   *   `long`          -> can `banDich`
   *   `export`        -> can `banDich` (va `onXuatVideo` lo phan con lai)
   */
  const onBuoc = useCallback(
    (id: string) => {
      if (id === "asr") {
        // Kenh dang chon, khong phai ban ghi. `workspace` la 1 vi job `asr` thuoc
        // workspace boc bang — cung con so `IngestHandler` dung khi no tu xep job.
        if (source === null) {
          setLoi("chưa chọn kênh — không chạy được bước Phiên âm");
          return;
        }
        // `engine` BAT BUOC cho job `asr` (`routes_jobs.ENGINE_REQUIRED`). Thieu no
        // thi route tra 422 "job loại asr phải có engine" — do duoc tren san pham
        // truoc khi co dong nay.
        //
        // `engineAsr === null` nghia la CHUA DOC DUOC registry (dang nap, hoac
        // `GET /api/registry` hong). Khong gui job trong trang thai do: gui mot
        // `engine` rong thi nhan 422, con doan mot ten thi co the sai. Noi ro rang.
        if (engineAsr === null) {
          setLoi("chưa đọc được danh mục engine ASR — thử lại sau khi trang nạp xong");
          return;
        }
        // 🔴 NGUỒN CHƯA CÓ AUDIO THÌ CHƯA BÓC BĂNG ĐƯỢC.
        //
        // DO DUOC (nguoi dung bao "mo mot video khac thi hang doi ko thay gi"): nap
        // video moi -> `ingest` xep hang -> bam "Phien am" NGAY -> job `asr` duoc tao
        // cho mot nguon CHUA co audio, va `transcribe.py:212` nem
        // `FileNotFoundError: source 6 chua co audio; job ingest phai chay truoc`.
        // Hang doi that luc do: #94 ingest source 6, #95 va #96 asr source 6 — hai job
        // CHAC CHAN HONG dang cho, va chung con lam `ingest` phai cho lau hon vi
        // worker chay het job cua GIAI DOAN hien tai truoc khi doi giai doan.
        //
        // Backend nay cung chan (409, xem `routes_jobs.create_job`), nhung chan o day
        // de nguoi dung doc duoc cau giai thich NGAY thay vi mot ma loi, va de khong
        // sinh ra mot request chac chan bi tu choi.
        //
        // `audio_path === null` la dieu kien DUNG (chinh `TranscribeHandler` doc no de
        // mo tep). Kiem `duration` se chan nham mot nguon co audio hop le ma ffprobe
        // khong doc duoc do dai.
        if (source.audio_path === null) {
          setLoi(
            "video này chưa bóc xong âm thanh — chờ job “Nạp” trong hàng đợi xong rồi bấm lại",
          );
          return;
        }
        void (async () => {
          try {
            await endpoints.createJob({
              type: "asr",
              engine: engineAsr,
              workspace: 1,
              // KHÔNG gửi `vung_doc` ở đây nữa — vùng đã lưu ở CHÍNH NGUỒN
              // (`sources.vung_doc`, ghi qua `PATCH /api/sources/{id}/vung-doc` mỗi
              // lần người dùng thả chuột), và `TranscribeHandler.run` đọc nó làm tầng
              // giữa: payload job > vùng của nguồn > `opts.vung_doc` của registry.
              //
              // Vì sao bỏ khỏi payload thay vì gửi kèm: payload là "lượt chạy NÀY dùng
              // vùng nào", còn cột nguồn là bộ nhớ dài hạn. Gửi kèm cả hai thì có hai
              // bản sao của cùng một con số, và khi chúng lệch nhau (người dùng kéo
              // khung rồi bấm "Phiên âm" trước khi PATCH xong) thì không ai biết bản
              // nào đúng. Một nguồn sự thật, đọc từ nguồn.
              payload: { source_id: source.id },
            });
          } catch (e) {
            setLoi(e instanceof Error ? e.message : String(e));
          }
        })();
        return;
      }
      // Ba buoc con lai deu chay TREN mot ban ghi da co, nen guard dat o day —
      // sau nhanh `asr`, khong phai truoc ca ham.
      if (transcript === null) {
        setLoi("chưa có bản ghi — bước này cần bóc băng trước");
        return;
      }
      if (id === "dich") {
        // 🔴 `engine` phải là ENGINE DỊCH lấy từ registry — KHÔNG phải `transcript.engine`.
        //
        // ĐO ĐƯỢC (chủ dự án báo ngay sau khi nút Dịch được nối): bấm Dịch ->
        // **422: engine 'ocr+asr' không có trong registry**. `transcript.engine` là nhãn
        // NGUỒN CHỮ (`"ocr+asr"` khi OCR và ASR cùng đọc ra), không phải một engine dịch.
        // Danh mục thật (`GET /api/registry`) có `mt: ['opus-mt', 'qwen2.5-3b',
        // 'qwen2.5-7b', 'hy-mt-1.5-7b', 'deepseek-web']` — `ocr+asr` không nằm trong đó.
        //
        // Chọn engine, ưu tiên giữ ĐÚNG engine người dùng đã dùng cho bản ghi này — kể cả
        // khi lượt gần nhất HỎNG (đó chính là ca đang sửa: lượt `deepseek-web` hỏng vì 429,
        // và rơi về `opus-mt` là đổi engine mà không ai yêu cầu, chất lượng khác hẳn).
        //
        //   1. engine của bản dịch MỚI NHẤT còn trong registry (bất kể `status`);
        //   2. engine của bản dịch đang mở;
        //   3. engine MT ĐẦU TIÊN của registry — cùng nguyên tắc với `engineAsr`: danh mục
        //      là dữ liệu, không viết cứng tên engine trong giao diện.
        const daDung = transcript.translations.filter((t) => engineMt.includes(t.engine));
        const moiNhat = daDung.reduce<(typeof daDung)[number] | null>(
          (a, b) => (a === null || b.id > a.id ? b : a), null);
        const engine = moiNhat?.engine
          ?? (banDich !== null && engineMt.includes(banDich.engine)
            ? banDich.engine
            : engineMt[0]);
        if (engine === undefined) {
          setLoi("chưa đọc được danh mục engine dịch — thử tải lại trang");
          return;
        }
        void (async () => {
          try {
            await createTranslation({ transcript_id: transcript.id, engine });
          } catch (e) {
            setLoi(e instanceof Error ? e.message : String(e));
          }
        })();
        return;
      }
      if (id === "long") {
        if (banDich === null) {
          setLoi("chua co ban dich — khong long tieng duoc");
          return;
        }
        void (async () => {
          try {
            await endpoints.makeDub(banDich.id, null);
          } catch (e) {
            setLoi(e instanceof Error ? e.message : String(e));
          }
        })();
        return;
      }
      // ───────────────────────────────────────────────────────────────────────
      // BUOC `duyet` — DO DUOC LA NO TUNG KHONG LAM GI.
      //
      // Bam nut "Duyet con 186 viec" tren thanh buoc: `request ghi: []`,
      // `notice: 0`. Nguyen nhan: `onBuoc` chi co nhanh cho `asr`/`dich`/`long`,
      // con `duyet` roi xuong cuoi ham va khong lam gi. Trong khi do
      // `approveTranscript` duoc IMPORT o dong 4 nhung KHONG CO CHO NAO GOI —
      // dung loai khai bao chet ma repo nay xoa.
      //
      // ⚠️ PHAI PHAN BIET HAI THU TRUNG TEN "duyet":
      //   · `onDuyet(i)` (dong 218) — tap CUC BO cua giao dien, danh dau MOT
      //     dong da xem. KHONG goi route, va CO Y nhu vay: backend khong co
      //     khai niem duyet tung dong.
      //   · buoc `duyet` o day — duyet CA BAN GHI, `POST /api/transcripts/{id}/
      //     approve`, doi `status` thanh `reviewed`.
      // Day chinh la ly do nut thanh buoc phai goi route that: no la duong DUY
      // NHAT de `status` cua transcript duoc ghi.
      //
      // Route KHONG tang `version` (docstring `routes_transcripts.py:10-12`:
      // duyet khong sua mot ky tu nao), nen sau khi goi chi can doc lai
      // transcript de lay `status` moi — khong phai nap lai ban dich.
      // ───────────────────────────────────────────────────────────────────────
      if (id === "duyet") {
        void (async () => {
          try {
            const moi = await approveTranscript(transcript.id);
            // `approveTranscript` tra `TranscriptSummary` (KHONG co `segments`),
            // nen giu nguyen mang doan dang co va chi thay phan tom tat.
            setTranscript((cu) => (cu === null ? cu : { ...cu, ...moi }));
          } catch (e) {
            setLoi(e instanceof Error ? e.message : String(e));
          }
        })();
        return;
      }
      // `ghep`/`xuat` la hanh dong cua nut Xuat, khong phai job rieng.
    },
    // 🔴 `source` VA `engineAsr` PHAI co trong deps — thieu mot cai la closure dong bang.
    //
    // Do duoc (lan 1): deps cu la `[transcript, banDich]`, nen `onBuoc` duoc tao mot lan
    // voi `source = null` (lan render dau, `sources` con rong) va KHONG BAO GIO duoc tao
    // lai khi `sources` nap xong. Hau qua: bam "Phien am" tren mot kenh DA HIEN TEN van
    // roi vao `if (source === null)` -> "chua chon kenh" -> khong job nao. Do nguyen van:
    //
    //   GOI TRUOC KHI BAM: 5  SAU: 5
    //   CO THONG BAO 'chua chon kenh': true
    //
    // Do duoc (lan 2, cung loai loi): `engineAsr` duoc doc trong than ham nhung khong co
    // trong deps, nen no giu `null` tu lan render dau va bam "Phien am" bao "chua doc
    // duoc danh muc engine ASR" du registry da ve. Sua ca hai cung luc — sua mot cai roi
    // de cai kia la lap lai dung loi vua sua.
    //
    // Luat: bat ky gia tri nao doc TRONG callback deu phai co trong deps cua no.
    // `engineMt` theo đúng luật đó: bước `Dịch` đọc nó để chọn engine.
    [source, engineAsr, engineMt, transcript, banDich],
  );

  /** Long lai MOT doan — backend long ca ban dich, nen day la long lai CA BAN. */
  const onLongLai = useCallback(
    (i: number) => {
      if (banDich === null) return;
      setLoi(`da xep long lai ca ban dich (doan #${i} khong long rieng duoc)`);
      void (async () => {
        try {
          await endpoints.makeDub(banDich.id, null);
        } catch (e) {
          setLoi(e instanceof Error ? e.message : String(e));
        }
      })();
    },
    [banDich],
  );

  /** Nap tep tu dia — `POST /api/sources/upload`, roi nap lai danh sach kenh. */
  const onNapTep = useCallback(
    async (files: File[], lang: "zh" | "en") => {
      for (const f of files) {
        try {
          await endpoints.uploadSource(f, lang);
        } catch (e) {
          setLoi(e instanceof Error ? e.message : String(e));
        }
      }
      await napKenh();
    },
    [napKenh],
  );

  return (
    <Studio
      sources={sources}
      sourcesLoading={sourcesLoading}
      sourcesError={sourcesError}
      source={source}
      onChonKenh={setSourceId}
      transcript={transcript}
      banDich={banDich}
      cps={cps}
      keHoach={keHoach}
      jobs={jobs}
      mayChu={mayChu}
      daDuyet={daDuyet}
      onDuyet={onDuyet}
      onSuaChu={onSuaChu}
      onSuaMoc={onSuaMoc}
      onXuatVideo={onXuatVideo}
      onBuoc={onBuoc}
      onLongLai={onLongLai}
      onNapTep={onNapTep}
      loi={loi}
      soEngine={engineCount}
      vungDoc={vungDoc}
      onVungDoc={onVungDoc}
    />
  );
}
