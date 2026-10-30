import { useCallback, useEffect, useMemo, useState } from "react";

import {
  approveTranscript,
  createTranslation,
  endpoints,
  getDubPlan,
  getTranscript,
  getTranslation,
  listSources,
  patchTranscript,
  patchTranslation,
  registry,
} from "@/api/endpoints";
import type {
  DubPlanRow,
  Job,
  Source,
  TranslationCps,
  TranslationDetail,
  Transcript,
} from "@/api/types";
import { Studio } from "@/components/studio/Studio";

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

export function App() {
  const [sources, setSources] = useState<Source[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [sourceId, setSourceId] = useState<number | null>(null);

  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [banDich, setBanDich] = useState<TranslationDetail | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [keHoach, setKeHoach] = useState<ReadonlyMap<number, DubPlanRow>>(new Map());
  const [daDuyet, setDaDuyet] = useState<ReadonlySet<number>>(new Set());
  const [loi, setLoi] = useState<string | null>(null);

  const source = useMemo(
    () => (sourceId === null ? null : (sources.find((s) => s.id === sourceId) ?? null)),
    [sources, sourceId],
  );

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

  useEffect(() => {
    void napKenh();
  }, [napKenh]);

  /**
   * BAN GHI cua kenh dang chon.
   *
   * `GET /api/transcripts` tra TOM TAT (khong co `segments`), nen phai di tiep mot
   * buoc `getTranscript`. Chon ban ghi MOI NHAT (`version` lon nhat) — do la ban
   * backend vua ghi, khong phai mot ban cu con `stale`.
   */
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
        const moiNhat = cuaKenh.reduce((a, b) => (b.version > a.version ? b : a));
        const day = await getTranscript(moiNhat.id);
        if (!huy) setTranscript(day);
      } catch (e) {
        if (!huy) setLoi(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      huy = true;
    };
  }, [sourceId]);

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
  }, [banDich, jobs]);

  // -------------------------------------------------------------------------
  // BON HANH DONG GHI — moi hanh dong goi DUNG mot route
  // -------------------------------------------------------------------------

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

  /** Sua MOC cua mot dong — `PATCH /api/transcripts/{id}` (moc thuoc BAN GHI, khong thuoc ban dich). */
  const onSuaMoc = useCallback(
    async (i: number, start: number, end: number) => {
      if (transcript === null) return;
      try {
        const moi = await patchTranscript(transcript.id, {
          segments: transcript.segments.map((s) => (s.i === i ? { ...s, start, end } : s)),
        });
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

  /** Chay lai mot buoc — chi bon buoc CO route that. */
  const onBuoc = useCallback(
    (id: string) => {
      if (transcript === null) {
        setLoi("chua co ban ghi — khong chay duoc buoc nao");
        return;
      }
      if (id === "asr") {
        void (async () => {
          try {
            await endpoints.createJob({
              type: "asr",
              workspace: transcript.id,
              payload: { source_id: transcript.source_id },
            });
          } catch (e) {
            setLoi(e instanceof Error ? e.message : String(e));
          }
        })();
        return;
      }
      if (id === "dich") {
        void (async () => {
          try {
            await createTranslation({ transcript_id: transcript.id, engine: transcript.engine });
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
    [transcript, banDich],
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

  /**
   * Du lieu may chu cho o "He thong" — `GET /api/registry`.
   *
   * Nap MOT lan: registry la danh muc engine, no khong doi trong mot phien.
   */
  const [engineCount, setEngineCount] = useState<number | null>(null);
  useEffect(() => {
    void (async () => {
      try {
        const r = await registry();
        // `Registry` co hai mang theo KIND: `asr` va `mt`. Khong co truong `engines`.
        setEngineCount(r.asr.length + r.mt.length);
      } catch {
        // Doc khong duoc thi `null` = CHUA DOC DUOC, khac 0 engine.
        setEngineCount(null);
      }
    })();
  }, []);

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
    />
  );
}
