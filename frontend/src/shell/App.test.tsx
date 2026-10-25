/**
 * Test `<App/>` THAT: render that trong jsdom, va du lieu lay tu mot server
 * `node:http` THAT trong tien trinh (`listen(0)` xin cong trong — khong giam cong
 * cua ai). Khong mock module nao.
 *
 * Vi sao jsdom: jsdom KHONG cho bang chung HINH THUC — no khong co layout, khong co CSS that.
 * ⇒ "khong co loi console" la dieu DUY NHAT tep nay do duoc ve phia hien thi.
 *
 * ⚠️ DINH CHINH (Task 12, ERRATA #40 + #46 muc 5): cau cu o day noi *"trinh duyet THAT la BAT
 * KHA o moi truong nay"* — **SAI vi QUA RONG**. Menh de dung la: *"Chromium khong mo duoc
 * DƯỚI CÁC CHẾ ĐỘ SANDBOX HẠN CHẾ"*; voi quyen rong thi Chrome chay duoc (do duoc).
 * ⇒ **Bang chung HINH THUC nam o tang Chrome that: `frontend/e2e/`.** ⚠️ Tang do CHUA duoc
 * chay trong luot Task 12 (xem bao cao).
 *
 * LUAT DOM (ERRATA #9 muc 1/6) — tep nay tu chua va khong dua vao thu tu:
 *   - MOI hook dat/tra global nam TRONG `describe()`: duoi `--test-isolation=none`,
 *     hook cap TEP bi node:test keo len GOC ca luot (moi `before` truoc MOI bai,
 *     moi `after` sau MOI bai) — do bang dong ho chung, khong phai suy dien.
 *   - `setupDom`/`teardownDom` cua CHINH tep nay: khong gia dinh jsdom cua tep khac
 *     con song, va khong de lai global nao cho tep sau.
 *   - `console.error`/`console.warn` bi TAM THAY de bat tieng on, va duoc TRA LAI
 *     nguyen trang trong `after` (chung la global: ERRATA #7 muc 3).
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import type { Server, ServerResponse } from "node:http";
import type { AddressInfo, Socket } from "node:net";

import type {
  EngineSpec,
  Job,
  Registry,
  Segment,
  Source,
  Transcript,
  TranscriptSummary,
  Translation,
  TranslationCreated,
  TranslationDetail,
} from "../api/types.ts";
import { BANG_PHIM, DA_NOI } from "../keys/shortcuts.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

/** Du lieu THAT dung hinh dang backend: `Source` (8 khoa) va `Job` (15 khoa). */
const SOURCES: Source[] = [
  {
    id: 1,
    kind: "file",
    origin: "kenh-mot.wav",
    media_path: "media/1.wav",
    audio_path: "media/1.16k.wav",
    duration: 754.2,
    lang: "zh",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: 2,
    kind: "url",
    origin: "https://vid.example/kenh-hai",
    media_path: "media/2.mp4",
    audio_path: null,
    duration: null,
    lang: "en",
    created_at: "2026-01-01T00:00:00Z",
  },
];

/**
 * `phase` theo dung dinh dang `job_state.phase_of` = "<type>:<engine|->", va `payload`
 * theo dung hop dong `routes_jobs.PAYLOAD_SCHEMA`: `ingest`/`asr` mang `source_id`,
 * `translate` mang `translation_id` (KHONG mang `source_id`).
 */
function makeJob(
  id: number,
  type: Job["type"],
  state: Job["state"],
  phase: string,
  progress: number,
  payload: Record<string, unknown> = {},
): Job {
  const engine = phase.split(":")[1];
  return {
    id,
    workspace: 1,
    type,
    engine: engine === undefined || engine === "-" ? null : engine,
    phase,
    state,
    cancel_requested: false,
    attempts: 1,
    progress,
    log_tail: "",
    error: null,
    payload,
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

const JOBS: Job[] = [
  // KENH 1 — ingest XONG, mot job asr CU da xong, roi mot job asr MOI dang chay.
  // Hai job asr tren CUNG mot kenh la chuyen THAT (chay lai), nen cap nay ghim luon
  // QUY UOC "job co id LON NHAT cua moi buoc la trang thai HIEN TAI".
  makeJob(3, "asr", "done", "asr:faster-whisper-large", 1, { source_id: 1, lang: "zh" }),
  makeJob(5, "ingest", "done", "ingest:-", 1, { source_id: 1, lang: "zh" }),
  makeJob(7, "asr", "running", "asr:faster-whisper-large", 0.35, { source_id: 1, lang: "zh" }),
  // KENH 2 — ingest dang CHO, va CHUA co job phien am nao.
  makeJob(6, "ingest", "queued", "ingest:-", 0, { source_id: 2, lang: "en" }),
  // Job DICH: payload mang `translation_id`, KHONG mang `source_id` ⇒ khong duoc tinh
  // cho kenh nao (duong dai translation -> transcript -> source, xem TRAN o ChannelZone).
  makeJob(8, "translate", "queued", "translate:qwen2.5-7b", 0, { translation_id: 42 }),
];

/** So job cua anh chup goc — `beforeEach` cat `JOBS` ve dung do dai nay (xem `themJobDich`). */
const SO_JOB_GOC = JOBS.length;

/**
 * ANH GOC cua ca MANG `JOBS` (khong chi do dai) — `beforeEach` dung lai CHINH anh nay.
 *
 * ⚠️ VI SAO KHONG chi `JOBS.length = SO_JOB_GOC` (D2): hai route MOI (`cancel`/`retry`) THAY THE
 * mot phan tu cua mang (khong sua tai cho object goc), nen cat do dai KHONG du tra mang ve anh goc
 * ⇒ mot job da bi doi trang thai o bai TRUOC song sot sang bai SAU va lam phep do XANH gia.
 */
const JOBS_GOC: Job[] = [...JOBS];

/**
 * Them MOT job `translate` vao anh chup `/api/jobs` — de bai `I3` phat duoc mot su kien
 * CHUYEN TRANG THAI cho DUNG ban dich dang xem.
 *
 * ⚠️ VI SAO CAN: su kien SSE (`useJobStream`) chi ghi SAU khoa cua mot `Job`
 * (state/progress/phase/error/log_tail/cancel_requested) va KHONG mang `payload`. Nen
 * `payload.translation_id` cua mot job CHI den tu anh chup `/api/jobs` ⇒ muon co mot job DICH
 * co `translation_id` (ban vua tao, id khong biet truoc) thi phai co no trong `JOBS` TRUOC khi
 * stream mo. `emit` voi mot id CHUA BIET thi bi hook bo qua (do la duong "id da biet").
 */
function themJobDich(id: number, state: Job["state"], translationId: number): void {
  JOBS.push(makeJob(id, "translate", state, "translate:opus-mt", 0, { translation_id: translationId }));
}

/**
 * Them MOT job `failed`/`interrupted` vao anh chup `/api/jobs` (D2).
 *
 * ⚠️ VI SAO CAN: anh chup goc KHONG co job nao o hai trang thai do ⇒ nut CHAY LAI (chi hien cho
 * `failed`/`interrupted`, §3 cua brief) khong co cho de xuat hien, va bai "409 ⇒ nguyen van" cung
 * khong co duong. Job duoc THEM chu khong sua job goc: `JOBS_GOC` tra mang ve anh sach moi bai.
 */
function themJobLoi(id: number, type: Job["type"], state: Job["state"], sourceId: number): void {
  JOBS.push(
    makeJob(
      id,
      type,
      state,
      type === "asr" ? "asr:faster-whisper-large" : `${type}:-`,
      0.4,
      { source_id: sourceId, lang: "zh" },
    ),
  );
}

/** Mot doan THAT: `Segment` co nam khoa LUON co; o day chi can duong hien thi. */
function doan(i: number, start: number, end: number, text: string): Segment {
  return { i, start, end, text, suspect: false };
}

function tomTat(
  id: number,
  sourceId: number,
  engine: string,
  lang: string,
  version: number,
  status: TranscriptSummary["status"],
): TranscriptSummary {
  return {
    id,
    source_id: sourceId,
    engine,
    lang,
    version,
    status,
    created_at: "2026-01-01T00:00:00Z",
    translations: [],
  };
}

/**
 * `GET /api/transcripts` — danh sach TOM TAT, va CO Y **KHONG sap xep theo `id`**.
 *
 * KENH 1 co HAI ban ghi: id 2 (CU) va id 5 (MOI). Ban CU dung TRUOC trong mang ⇒ mot ban
 * "lay hang dau tien khop" se chon id 2, va bai `CHON KENH` duoi day se DO. Do la quy uoc
 * "id LON NHAT la hien tai" — cung quy uoc voi `ChannelZone.buocCuaKenh` (xem
 * `src/state/channelData.ts`).
 *
 * ⚠️ `let` chu khong `const`: bai "job `asr` xong ⇒ BAN GHI MOI hien ra" (vong sua W1 #1,
 * `Minor #3`) THEM mot hang vao chinh mang nay — do la cach duy nhat mot lan doc lai
 * `/api/transcripts` chung minh duoc bang DOM, chu khong bang mot loi khai.
 */
let TRANSCRIPTS: TranscriptSummary[] = [
  tomTat(2, 1, "faster-whisper-large", "zh", 1, "draft"),
  tomTat(5, 1, "faster-whisper-large", "zh", 2, "translated"),
  tomTat(3, 2, "sensevoice-small", "en", 1, "draft"),
];

/** `GET /api/transcripts/{id}` — ban DAY DU (co `segments`). */
let TRANSCRIPT_CHI_TIET: Record<number, Transcript> = {
  5: {
    ...tomTat(5, 1, "faster-whisper-large", "zh", 2, "translated"),
    segments: [doan(0, 0, 2, "câu 1"), doan(1, 2, 4, "câu 2"), doan(2, 4, 6, "câu 3")],
  },
  2: {
    ...tomTat(2, 1, "faster-whisper-large", "zh", 1, "draft"),
    segments: [doan(0, 0, 2, "bản cũ kênh một")],
  },
  /**
   * KENH HAI (#3) la `ben ghi CUA D1`: BON doan, va doan CUOI mang DU cac truong TUY CHON cua
   * `Segment` (`suspect`/`qa`/`events`/`words`/`t`/`avg_logprob`).
   *
   * ⚠️ VI SAO KHONG dung ban ghi #5 cua kenh mot: bai "Doi chieu" khang dinh
   * `cotCps.length === 3`, ma so o CPS = SO DOAN cua ban ghi ⇒ them mot doan vao #5 lam DO mot
   * bai dang co. Ban ghi #3 chi duoc hai bai "DOI KENH" cham toi, va ca hai chi doi chu cua
   * doan DAU. Mot ban ghi RIENG cho D1 khong lam yeu khang dinh nao.
   *
   * ⚠️ Va day chinh la GIA DOI ma D1 phai tra: `TranscriptPatch.segments` buoc gui TOAN BO mang
   * (backend `min_length=1`), nen mot ban dung lai `Segment` chi voi `{i,start,end,text}` se XOA
   * AM THAM `suspect`/`qa` cua MOI dong. Doan thu tu la cho do duoc dieu do.
   *
   * ⚠️ HAI dong `suspect` (i = 1 VA i = 3) — vong sua 1, `M-3`: fixture cu chi co MOT dong nghi ngo
   * (i = 3, dong CUOI), nen "N khong vong" KHONG falsify duoc (tai dong cuoi thi ban VONG va ban
   * KHONG VONG deu dung yen). Dong thu hai o GIUA bien menh de do thanh mot menh de co mutant lam no
   * sai duoc: ban VONG se nhay nguoc ve i = 1. i = 1 chi mang `suspect` (khong `qa`/`events`/...):
   * doan thu tu van la doan DUY NHAT do duoc "giu nguyen moi truong tuy chon".
   */
  3: {
    ...tomTat(3, 2, "sensevoice-small", "en", 1, "draft"),
    segments: [
      doan(0, 0, 2, "bản kênh hai"),
      { ...doan(1, 2, 4, "dòng hai"), suspect: true },
      doan(2, 4, 6, "dòng ba"),
      {
        i: 3,
        start: 6,
        end: 8,
        text: "dòng bốn",
        suspect: true,
        qa: ["nhạc nền"],
        events: ["bgm"],
        words: [{ w: "bốn", s: 6, e: 7 }],
        t: "bốn (dịch tay)",
        avg_logprob: -0.42,
      },
    ],
  },
};

/**
 * `stale` TINH O SERVER, khong luu — dung `is_stale` cua backend
 * (`domain/staleness.py`: `translated_from < version_hien_tai`).
 *
 * ⚠️ VI SAO FIXTURE PHAI TINH CHU KHONG DUOC HARD-CODE `false`: cau "ban dich da loi thoi" cua D1
 * chi la SU THAT neu co mot MAY CHU noi no. Mot fixture tra `stale: false` co dinh se lam bai ghim
 * do luon (hoac xanh luon) vi mot ly do khong lien quan gi toi san pham.
 */
function staleCua(row: Translation): boolean {
  const versionHienTai = TRANSCRIPT_CHI_TIET[row.transcript_id]?.version ?? row.transcript_version;
  return row.transcript_version < versionHienTai;
}

function banDich(
  id: number,
  transcriptId: number,
  status: Translation["status"],
  transcriptVersion = 2,
): Translation {
  return {
    id,
    transcript_id: transcriptId,
    engine: "qwen2.5-7b",
    target_lang: "vi",
    prompt_version: "raw-p1",
    transcript_version: transcriptVersion,
    status,
    stale: false,
    created_at: "2026-01-01T00:00:00Z",
  };
}

/**
 * `GET /api/translations?transcript_id=…` — MOI NHAT TRUOC nhu route that.
 *
 * Ban ghi 5 co HAI ban dich: id 11 `done` va id 12 `queued`. `chonTranslation` phai chon
 * 11 (`status === "done"`, moi nhat) ⇒ `translationId` cua thanh transport la 11.
 *
 * ⚠️ `let` chu khong `const`: bai W3 "ban vua tao tro thanh ban dang xem" THEM mot hang vao
 * chinh mang nay qua duong THAT (`POST /api/translations` o server), roi lan doc lai
 * `/api/translations` phai thay no. Do la cach duy nhat phan biet "CO lam moi danh sach" voi
 * "tu chen hang vao state" bang DOM.
 */
let TRANSLATIONS: Translation[] = [
  banDich(12, 5, "queued"),
  banDich(11, 5, "done"),
  banDich(7, 2, "done"),
  /**
   * Ban dich CUA BAN GHI #3 (kenh hai) — `transcript_version: 1` = DUNG version hien tai cua ban
   * ghi #3, nen truoc khi ghi no KHONG loi thoi, va sau MOT lan PATCH (version ⇒ 2) no THANH loi
   * thoi. Do la cach do cau "ban dich da loi thoi" bang SU THAT cua may chu, khong bang mot co
   * hard-code trong fixture.
   */
  banDich(4, 3, "done", 1),
];

/**
 * `GET /api/translations/{id}` — CHI TIET: `segments` cua BAN DICH + `cps` dang SO.
 *
 * Cot CPS cua man Doi chieu chi co nguon TU DAY (ERRATA #18: `qa_issues` khong toi duoc
 * HTTP) ⇒ con so `4.2`/`30.5` duoi day la thu phan biet "doc tu backend" voi "tu parse".
 */
const TRANSLATION_CHI_TIET: Record<number, TranslationDetail> = {
  11: {
    ...banDich(11, 5, "done"),
    segments: [doan(0, 0, 2, "câu một (dịch)"), doan(1, 2, 4, "câu hai (dịch)"), doan(2, 4, 6, "câu ba (dịch)")],
    cps: {
      max_cps: 21,
      rows: [
        { i: 0, chars: 5, window: 1.2, cps: 4.2, max_cps: 21, over: false },
        { i: 1, chars: 6, window: 1.0, cps: 6.0, max_cps: 21, over: false },
        { i: 2, chars: 7, window: 1.1, cps: 30.5, max_cps: 21, over: true },
      ],
    },
  },
  12: { ...banDich(12, 5, "queued"), segments: [], cps: { max_cps: 21, rows: [] } },
  7: { ...banDich(7, 2, "done"), segments: [], cps: { max_cps: 21, rows: [] } },
  4: {
    ...banDich(4, 3, "done", 1),
    segments: [
      doan(0, 0, 2, "bản kênh hai (dịch)"),
      doan(1, 2, 4, "dòng hai (dịch)"),
      doan(2, 4, 6, "dòng ba (dịch)"),
      doan(3, 6, 8, "dòng bốn (dịch)"),
    ],
    cps: {
      max_cps: 21,
      rows: [
        { i: 0, chars: 5, window: 1.0, cps: 5.0, max_cps: 21, over: false },
        { i: 1, chars: 5, window: 1.0, cps: 5.0, max_cps: 21, over: false },
        { i: 2, chars: 5, window: 1.0, cps: 5.0, max_cps: 21, over: false },
        { i: 3, chars: 5, window: 1.0, cps: 5.0, max_cps: 21, over: false },
      ],
    },
  },
};

/**
 * `GET /api/registry` THAT (hinh dang `Registry`: `{asr:[], mt:[]}`, KHONG phai mang phang —
 * ERRATA #2 muc 2). `available` CHI co tren `kind == "mt"`; spec ASR duoi day **THIEU** khoa do.
 *
 * ⚠️ VI SAO FIXTURE PHAI CO CA ASR LAN MT: neu mot ban sua nao day truyen `[...asr, ...mt]`
 * xuong o chon engine dich thi client se gui id ASR, va backend tra **422**
 * (`routes_translations.py::create_translation`, nhanh `spec.kind != "mt"`). Fixture CHI co MT
 * thi loi do KHONG THE lo ra (ERRATA #31 muc 3: fixture phai dung hinh dang THAT).
 */
function spec(
  id: string,
  label: string,
  runtime: EngineSpec["runtime"],
  available: boolean | undefined,
  kind: EngineSpec["kind"] = "mt",
): EngineSpec {
  const capabilities: EngineSpec["capabilities"] = {};
  if (available !== undefined) capabilities.available = available;
  return {
    id,
    label,
    kind,
    runtime,
    model_ref: `model/${id}`,
    vram_mb: 0,
    langs: ["zh", "en"],
    capabilities,
    opts: {},
  };
}

const REGISTRY_HTTP: Registry = {
  asr: [spec("faster-whisper-large", "Faster Whisper Large", "inprocess", undefined, "asr")],
  mt: [
    spec("opus-mt", "OPUS-MT", "inprocess", true),
    // Ollama dang chay nhung model chua pull ⇒ `available === false` ⇒ KHONG duoc liet ke.
    spec("qwen2.5-7b", "Qwen 2.5 7B", "ollama", false),
  ],
};

/**
 * `let` chu khong `const`: bai "khong co engine MT nao dung duoc" doi fixture sang mot registry
 * ma MOI MT deu `available === false` — va `beforeEach` tra ve dung anh luc nap module.
 */
let REGISTRY: Registry = REGISTRY_HTTP;

/** `GET /api/status` — Ollama `up` ⇒ panel §4.8 tra `null` (khong co gi de canh bao). */
const STATUS_HTTP = {
  queue_depth: 1,
  running: [7],
  current_phase: "asr:faster-whisper-large",
  phase_switches: 3,
  vram_unit: "MiB",
  vram: null,
  ollama: "up" as const,
};

const dem = {
  sources: 0,
  jobs: 0,
  stream: 0,
  loiSources: false,
  registry: 0,
  /**
   * So lan `POST /api/translations` toi noi nhan — BANG CHUNG DUONG THAT cho cua vao "bat dau
   * dich": khong dem duoc o PHIA SERVER thi "bam nut ⇒ co ban dich moi" co the xanh vi mot ly
   * do khac (du lieu den tu dau do khong phai HTTP).
   */
  postTranslations: 0,
  /** Body JSON THAT cua lan POST gan nhat, va header `content-type` cua no. */
  bodyTao: null as Record<string, unknown> | null,
  /** Chuoi JSON THO (nguyen van) cua lan POST gan nhat — de bao cao dan duoc BYTE client gui. */
  rawTao: "",
  contentTypeTao: "",
  /** Bat de `POST /api/translations` tra 409 kem cau tieng Viet cua backend (ca loi THAT). */
  loiTao: false,
  /**
   * Trang thai JOB `translate` ma server tra trong body 201 — de bai "queued phai noi ra trang
   * thai kem trang thai JOB" khong phai BIA mot chuoi trong test.
   */
  jobTao: "queued" as "queued" | "running",
  /**
   * Bon bo dem cho duong SUY DU LIEU cua W1. Chung la BANG CHUNG DUONG THAT: neu khong
   * dem duoc thi "man hien du lieu that" co the xanh vi mot ly do khac (du lieu den tu
   * dau do khong phai HTTP).
   */
  transcripts: 0,
  transcriptChiTiet: 0,
  translations: 0,
  /**
   * So lan `GET /api/translations/{id}` — bo dem TOAN CUC, **KHONG duoc dung lam PHEP CHO**.
   *
   * ⚠️ VI SAO (vong sua W3 #2, `Important` F1 cua re-review): no la mot CON SO TICH LUY, khong
   * phai mot dai luong CUA BAI NAY — mot request con dang bay cua bai TRUOC ha canh SAU
   * `beforeEach` (no tra bo dem ve 0) cung lam no tang, nen `waitFor(() => assert.equal(dem.
   * translationChiTiet, N))` co the KHONG BAO GIO bang N (do duoc: `3 !== 2`, `4 !== 2`). Nay
   * moi phep cho di qua `choDanhSachBanDich` (DOM THAT). Bo dem o lai lam BANG CHUNG DUONG THAT
   * khi can probe (log request theo `id`), khong lam phep cho.
   */
  translationChiTiet: 0,
  /**
   * So request mang mot id KHONG HOP LE (thieu, `null`, `0`, khong nguyen) tren duong dan
   * hoac tren query `transcript_id`.
   *
   * ⚠️ VI SAO CAN BO DEM NAY thay vi `dem.transcriptChiTiet === 0`: cac bo dem theo endpoint
   * la bo dem TOAN CUC, va mot request CON DANG BAY cua bai TRUOC co the ha canh trong bai
   * SAU ⇒ mot phep khang dinh "== 0" co the DO vi ly do khong lien quan. Do duoc that trong
   * luot mutation `W1-4`/`W1-5`: bai "CHUA CHON KENH" do vi request cua bai truoc, khong
   * phai vi mutant. Bo dem nay chi tang khi id THAT SU sai, nen no do DUNG menh de "KHONG
   * goi endpoint theo `null`" va khong phu thuoc thu tu bai.
   */
  soYeuCauIdKhongHopLe: 0,
  /**
   * So lan `GET /api/transcripts/{id}` theo TUNG id — do o PHIA SERVER.
   *
   * VI SAO CAN: bai "ngoi no doc lai" phai chung minh KHONG BAN GHI NAO KHAC bi doc lai, chu
   * khong chi "co mot ban ghi moi xuat hien".
   */
  transcriptTheoId: {} as Record<number, number>,
  /**
   * BAO NHIEU LAN `POST /api/sources/upload` toi noi nhan — **BANG CHUNG DUONG THAT PHIA SERVER**
   * cua duong NAP (vong sua W2 #1, `Important` I1).
   *
   * ⚠️ VI SAO PHAI DEM O PHIA SERVER: truoc vong sua nay, `App.napTep` **khong duoc bai nao thi
   * hanh** — mutant dau doc (`throw` o cau dau cua `napTep`) cho suite VAN `fail 2`, tuc `W2-1`
   * (bo `sources.reload()`), `W2-2` (bo `selectChannel`), `W2-5b` (nuot loi trong `App`) va `W2-6`
   * (chon kenh ca khi MOI tep loi) deu SONG SOT. Mot loi khai "da bam nut" khong phan biet duoc
   * "request da di" voi "du lieu den tu dau do khong phai HTTP"; bo dem nay thi phan biet duoc.
   */
  upload: 0,
  /** URL NGUYEN VAN cua request nap — de khang dinh `lang` KHONG di bang query (`W2-4`). */
  uploadUrl: "",
  /** Header `content-type` NGUYEN VAN — phai la `multipart/form-data; boundary=…`. */
  uploadContentType: "",
  /** THAN REQUEST o dang BYTE THO (khong qua `JSON.parse`, khong qua mot thu vien multipart). */
  uploadRaw: null as Buffer | null,
  /** Ten cac PHAN multipart, boc tu byte tho — `["file","lang"]` khi hop dong dung. */
  uploadPhan: [] as string[],
  /** Gia tri cua phan `lang`, doc tu THAN cua phan do (khong phai tu query). */
  uploadLang: null as string | null,
  /** Ten tep (theo thu tu gui) va BYTE cua tung tep — de khang dinh byte di NGUYEN VEN. */
  uploadTenTep: [] as string[],
  uploadByteTep: [] as number[][],
  /** Ten tep ma server TU CHOI bang 422 kem cau tieng Viet NGUYEN VAN cua backend. */
  uploadLoiTheoTen: [] as string[],
  /** Bat de MOI tep bi tu choi 422 — dung cho bai "MOI tep loi ⇒ KHONG doi kenh". */
  uploadLoiToanBo: false,
  /**
   * D1 — DUONG GHI `PATCH /api/transcripts/{id}`, dem o PHIA SERVER.
   *
   * ⚠️ VI SAO PHAI DEM O PHIA MAY CHU: "bam luu ⇒ co chu moi hien ra" co the xanh vi mot ly do
   * khac (chu moi den tu DRAFT trong state chu khong tu dia). Chi bo dem nay phan biet duoc
   * "request da DI RA" voi "giao dien tu sua state tai cho".
   */
  patch: 0,
  /** So lan PATCH theo TUNG id — bo dem tich luy KHONG duoc dung lam phep cho (ERRATA #37 muc 1). */
  patchTheoId: {} as Record<number, number>,
  /** Body JSON THAT cua lan PATCH gan nhat, va chuoi JSON THO (de bao cao duoc BYTE client gui). */
  patchBody: null as { segments?: Segment[]; status?: string } | null,
  patchRaw: "",
  /**
   * THAN THO cua MOI lan PATCH, theo THU TU may chu nhan duoc.
   *
   * ⚠️ VI SAO CAN (C1): `patchBody` chi giu lan CUOI, nên một cuộc đua mất-cập-nhật chỉ lộ ra khi
   * so DUOC body cua lan ghi THU HAI voi gia tri ma lan ghi THU NHAT da ghi. Khong co mang nay thi
   * khong the dan nguyen van "body PATCH thu hai" — va do la bang chung duy nhat cua C1.
   */
  patchBodies: [] as string[],
  /** So PATCH da TRA XONG (co phan hoi) — dung lam CHUNG NHAN CHONG LAN cua bai C1. */
  patchXong: 0,
  /**
   * Do TRE (ms) ma route PATCH tra loi — mac dinh 0.
   *
   * ⚠️ CHI bai `D1 CHỒNG LẤN` bat no: lam cham phan hoi la cach DUY NHAT khien hai lan bam CHAC
   * CHAN chong lan (dung khuon chan doan cua review), nen ket qua khong phu thuoc toc do may.
   */
  patchTre: 0,
  /** Version TRUOC lan PATCH cuoi, do o PHIA SERVER — khong suy tu phia client. */
  versionTruocPatch: {} as Record<number, number>,
  /** Bat de PATCH tra 422 kem cau tieng Viet NGUYEN VAN cua backend (nhanh LOI GHI). */
  patchLoi: false,
  /**
   * Task 11 / vòng sửa 1 (`I-3`) — SỐ LỜI GỌI `play()` và `pause()` trên `HTMLMediaElement`.
   *
   * ⚠️ VÌ SAO ĐẾM ĐƯỢC DÙ JSDOM KHÔNG CÓ ÂM THANH: `before` đã bịt hai hàm đó bằng hàm rỗng (jsdom
   * không hiện thực chúng, và chúng log `Not implemented` ra `console.error` — thứ tệp này ghim là
   * không được có). Bịt một hàm KHÔNG phải là làm nó không đo được: lời gọi vẫn ĐI QUA đây, nên bộ
   * đếm là bằng chứng trực tiếp cho mệnh đề "nudge ⇒ nghe lại". Lý do TRẦN cũ (*"jsdom không hiện
   * thực `play()` ⇒ không ghim được nghe lại"*) lẫn hai thứ: nó chặn việc NGHE, không chặn việc GHIM.
   */
  play: 0,
  pause: 0,
  /**
   * Bat de fixture dong dien MOT NGUOI GHI KHAC ngay SAU khi tra loi PATCH: may chu len
   * `version` them MOT va doi chu cua doan 0.
   *
   * ⚠️ VI SAO CAN (nghia vu ghim cua D1, ERRATA #45 muc 4): ve `vuaGhi.version > hienTai.version`
   * cua nen "ban ghi vua gui" chi quan sat duoc khi CO mot ban ghi may chu MOI HON nen. Khong co
   * nguoi ghi khac thi `hienTai.version` luon BANG `vuaGhi.version`, hai nhanh cho CUNG ket qua.
   */
  nguoiGhiKhac: false,
  // ---------------------------------------------------------------------------
  // D2 — BA LENH GHI MOI (`approve` · `cancel` · `retry`), dem o PHIA MAY CHU.
  //
  // ⚠️ VI SAO PHAI DEM O PHIA MAY CHU: "bam nut ⇒ co gi do xay ra" co the xanh vi mot ly do khac
  // (giao dien tu doi chu/trang thai tai cho). Chi bo dem nay phan biet duoc "request da DI RA"
  // voi "giao dien tu sua state" — va no cung la bang chung cua bai CHONG TRUNG LAP.
  // ---------------------------------------------------------------------------
  approve: 0,
  approveTheoId: {} as Record<number, number>,
  /** Do tre (ms) cua route approve — chi bai CHONG TRUNG LAP bat (de hai lan bam CHONG lan). */
  approveTre: 0,
  /**
   * `dem.patchXong` DO DUOC luc request approve toi noi.
   *
   * ⚠️ Day la bang chung approve DI QUA HANG DOI GHI cua D1: mot PATCH cham dang bay ⇒ neu approve
   * di THANG (khong xep hang) thi no toi noi khi `patchXong` con 0.
   */
  approveSauPatch: -1,
  approveXong: 0,
  /** Bat de approve tra **404** kem cau NGUYEN VAN cua backend (nhanh LOI DUYET; route `approve`
      chi co 404/200 — xem comment tai nhanh do). */
  approveLoi: false,
  cancel: 0,
  cancelTheoId: {} as Record<number, number>,
  cancelTre: 0,
  cancelSauPatch: -1,
  cancelXong: 0,
  retry: 0,
  retryTheoId: {} as Record<number, number>,
  retryTre: 0,
  retrySauPatch: -1,
  retryXong: 0,
  /**
   * MA HTTP ma fixture retry DA TRA cho lan goi gan nhat.
   *
   * ⚠️ VI SAO CAN (`M-1` cua re-review vong sua 1): bang mutation cua vong truoc ke
   * `F3-RETRY-409-FAILED` (bo guard DIEU KIEN cua fixture) la DO — DO LAI thi **0 do**, vi bai
   * test tu dat `job21.state = "done"` nen no khong bao gio di vao nhanh guard. Con so NAY la
   * tin hieu DUONG de bai moi ghim duoc chinh guard do: trang thai CHAY LAI DUOC ⇒ 200.
   */
  retryTrangThai: 0,
  /** Bat nhanh 409 cua retry. ⚠️ CHI co hieu luc khi trang thai THAT cua job KHONG chay lai duoc
      (`failed`/`interrupted` la `RETRYABLE_STATES` ⇒ backend KHONG BAO GIO tra 409 cho chung). */
  retry409: false,
  // ---------------------------------------------------------------------------
  // ITEM 5 — `POST /api/jobs` (BÓC LẠI bằng engine ASR khác), đếm ở PHÍA MÁY CHỦ.
  //
  // ⚠️ VÌ SAO PHẢI ĐẾM Ở PHÍA MÁY CHỦ: "bấm `bóc lại` ⇒ có job mới" có thể xanh vì một lý do
  // khác (hàng đợi tự đổi do SSE, hoặc do fixture). Chỉ bộ đếm này + BODY THẬT phân biệt được
  // "request đã ĐI RA với đúng engine/source" với "giao diện tự bịa ra một job".
  //
  // ⚠️ TÊN KHOÁ PHẢI TRÁNH `jobTao`: khoá đó ĐÃ CÓ ở trên (trạng thái JOB mà server trả trong
  // body 201 của `POST /api/translations`, kiểu `"queued" | "running"`). Một bản nháp của item
  // này đặt bộ đếm số đếm TRÙNG tên đó ⇒ khoá ĐỨNG SAU trong object literal thắng ⇒ server fixture
  // trả `job.state = 0` ⇒ cột phải của màn Đối chiếu in *"job: undefined"* và bài
  // `W3 BAT DAU DICH` ĐỎ. ĐO ĐƯỢC (không phải giả thuyết): đó đúng là câu đã xuất hiện trong DOM
  // thật của lượt chạy. Vì thế các khoá dưới đây mang hậu tố/tiền tố KHÁC hẳn.
  // ---------------------------------------------------------------------------
  jobMoi: 0,
  /** Body JSON THẬT của lần `POST /api/jobs` gần nhất. */
  bodyJobMoi: null as Record<string, unknown> | null,
  /** Chuỗi JSON THÔ của lần đó — để báo cáo được BYTE client gửi. */
  rawJobMoi: "",
  /** Độ trễ (ms) của route tạo job — chỉ bài "đang bay" bật, để cửa sổ đo là xác định. */
  jobMoiTre: 0,
  /** Số lời gọi tạo job đã TRẢ XONG (chứng nhân hai chiều của trạng thái "đang bay"). */
  jobMoiXong: 0,
  /** Bật để route tạo job trả 422 kèm câu NGUYÊN VĂN của backend (nhánh LỖI). */
  jobMoiLoi: false,
  // ---------------------------------------------------------------------------
  // ĐƯỜNG XOÁ KÊNH (`DELETE /api/sources/{id}`), đếm ở PHÍA MÁY CHỦ.
  //
  // ⚠️ VÌ SAO PHẢI ĐẾM Ở PHÍA MÁY CHỦ: "bấm xoá hai lần ⇒ kênh biến mất" có thể xanh vì một
  // lý do khác (giao diện tự cắt hàng khỏi danh sách). Chỉ bộ đếm này phân biệt được "request đã
  // ĐI RA" với "giao diện tự sửa state tại chỗ" — và cú bấm ĐẦU TIÊN (bước xác nhận) phải để nó
  // bằng 0.
  // ---------------------------------------------------------------------------
  xoaSource: 0,
  xoaTheoId: {} as Record<number, number>,
  /**
   * Id kênh mà máy chủ ĐÃ XOÁ. Route `GET /api/sources` phải QUÊN chúng — chỉ trả 204 mà danh
   * sách còn hàng thì "đọc lại danh sách" là một lời khai không kiểm được.
   *
   * ⚠️ GIỮ DẠNG DANH SÁCH PHỤ, KHÔNG `splice` khỏi `SOURCES`: `beforeEach` khôi phục mảng bằng
   * `SOURCES.length = SO_SOURCE_GOC` (nó giả định chỉ có `push`), nên một hàng bị cắt khỏi GIỮA
   * mảng sẽ để lại lỗ và phép khôi phục đọc ra `undefined`.
   */
  xoaDaXoa: [] as number[],
  /** Bật để route xoá trả 409 kèm câu NGUYÊN VĂN của backend (job đang xếp hàng/đang chạy). */
  xoaLoi: false,
};

/**
 * Xoa MOI bo dem/gia tri cua BA LENH GHI MOI ve goc — dung chung cho `beforeEach` va cho cac bai
 * phai tu dat lai moc GIUA bai.
 *
 * ⚠️ VI SAO LA MOT HELPER (bai hoc `M5` cua review D1): mot lan reset thieu mot bo dem lam khang
 * dinh SAU moc reset doc gia tri CU va XANH gia. Dem tay tung bo dem la cach de sai.
 */
function xoaDemLenh(): void {
  dem.approve = 0;
  dem.approveTheoId = {};
  dem.approveTre = 0;
  dem.approveSauPatch = -1;
  dem.approveXong = 0;
  dem.approveLoi = false;
  dem.cancel = 0;
  dem.cancelTheoId = {};
  dem.cancelTre = 0;
  dem.cancelSauPatch = -1;
  dem.cancelXong = 0;
  dem.retry = 0;
  dem.retryTheoId = {};
  dem.retryTre = 0;
  dem.retrySauPatch = -1;
  dem.retryXong = 0;
  dem.retryTrangThai = 0;
  dem.retry409 = false;
}

/**
 * Xoa MOI bo dem/gia tri cua duong GHI ve goc — DUNG CHUNG cho `beforeEach` va cho cac bai phai
 * tu dat lai moc giua bai (M5 cua review: reset thieu `patchBody`/`versionTruocPatch` lam mot
 * khang dinh SAU moc reset doc body CU va XANH gia).
 */
function xoaDemGhi(): void {
  dem.patch = 0;
  dem.patchTheoId = {};
  dem.patchBody = null;
  dem.patchRaw = "";
  dem.patchBodies = [];
  dem.patchXong = 0;
  dem.patchTre = 0;
  dem.versionTruocPatch = {};
  dem.patchLoi = false;
}

/** Xoa hai bo dem cua duong MEDIA (`play`/`pause` — vong sua 1, `I-3`). */
function xoaDemMedia(): void {
  dem.play = 0;
  dem.pause = 0;
}

/**
 * Xoa MOI bo dem/gia tri cua duong TAO JOB (`POST /api/jobs`, item 5) ve goc.
 *
 * ⚠️ VI SAO LA MOT HELPER: cung bai hoc `M5` cua review D1 — mot lan reset thieu mot bo dem lam
 * khang dinh SAU moc reset doc gia tri CU va XANH gia. `bodyJobMoi`/`rawJobMoi` la hai thu DE QUEN
 * nhat.
 */
function xoaDemBocLai(): void {
  dem.jobMoi = 0;
  dem.bodyJobMoi = null;
  dem.rawJobMoi = "";
  dem.jobMoiTre = 0;
  dem.jobMoiXong = 0;
  dem.jobMoiLoi = false;
}

/**
 * Xoa MOI bo dem/gia tri cua duong XOA KENH ve goc.
 *
 * Cung bai hoc `M5` cua review D1 — MOT helper, khong liet ke tay: `xoaDaXoa` la thu DE QUEN
 * nhat, va mot id con sot lai trong do lam moi bai sau thay mot kenh "da bi xoa" ma khong co
 * request nao.
 */
function xoaDemXoa(): void {
  dem.xoaSource = 0;
  dem.xoaTheoId = {};
  dem.xoaDaXoa = [];
  dem.xoaLoi = false;
}

/** Them mot ban ghi MOI vao ca hai route — dung cho ngoi no doc lai (`Minor #3`). */
function themBanGhiMoi(id: number, sourceId: number, text: string): void {
  TRANSCRIPTS = [...TRANSCRIPTS, tomTat(id, sourceId, "faster-whisper-large", "zh", 3, "translated")];
  TRANSCRIPT_CHI_TIET = {
    ...TRANSCRIPT_CHI_TIET,
    [id]: { ...tomTat(id, sourceId, "faster-whisper-large", "zh", 3, "translated"), segments: [doan(0, 0, 2, text)] },
  };
}

/** So KENH cua anh chup goc — `beforeEach` cat `SOURCES` ve dung do dai nay. */
const SO_SOURCE_GOC = SOURCES.length;

/** Tep THAT cua Node (`File` la global cua Node o day) — khong phai mot object gia hinh dang tep. */
function tepThat(ten: string, byte: number[] = [1, 2, 3], type = "audio/wav"): File {
  return new File([new Uint8Array(byte)], ten, { type });
}

/**
 * BOC multipart **TU BYTE THO** — khong dung thu vien, khong `JSON.parse`, khong doc query.
 *
 * ⚠️ VI SAO PHAI BOC TU BYTE (vong sua W2 #1, `Important` I2): mutation `W2-4` doi `lang` tu
 * **truong FORM** sang **query** (`api.postForm("/sources/upload?lang=…")`) VI PHAM hop dong
 * backend (`lang: str = Form(DEFAULT_LANG)`) ma suite cu **khong thay** — vi khong bai nao doc
 * than request THAT. Phep do nay lam no DO: URL co query ⇒ khang dinh URL that bai, va danh sach
 * phan tut ve `["file"]` ⇒ khang dinh phan that bai.
 *
 * Ham tra ve TEN TUNG PHAN + `filename` + THAN cua phan (dang `Buffer`, tuc byte nguyen ven).
 */
function bocMultipart(
  raw: Buffer,
  contentType: string,
): { ten: string; filename: string | null; than: Buffer }[] {
  const khop = /boundary=([^;]+)/.exec(contentType);
  assert.ok(khop !== null, `content-type khong co boundary: ${JSON.stringify(contentType)}`);
  const vach = Buffer.from(`--${khop[1] ?? ""}`, "latin1");
  const ra: { ten: string; filename: string | null; than: Buffer }[] = [];
  let i = raw.indexOf(vach);
  while (i >= 0) {
    let dau = i + vach.length;
    const hai = raw.subarray(dau, dau + 2).toString("latin1");
    if (hai === "--") break; // vach KET THUC
    if (hai === "\r\n") dau += 2;
    const vachSau = raw.indexOf(vach, dau);
    if (vachSau < 0) break;
    let cuoi = vachSau;
    if (raw.subarray(cuoi - 2, cuoi).toString("latin1") === "\r\n") cuoi -= 2;
    const ca = raw.subarray(dau, cuoi);
    const cach = ca.indexOf(Buffer.from("\r\n\r\n", "latin1"));
    assert.ok(cach >= 0, "mot phan multipart khong co dong trong phan cach header/than");
    const header = ca.subarray(0, cach).toString("latin1");
    ra.push({
      ten: /name="([^"]*)"/.exec(header)?.[1] ?? "",
      filename: /filename="([^"]*)"/.exec(header)?.[1] ?? null,
      than: ca.subarray(cach + 4),
    });
    i = vachSau;
  }
  return ra;
}

/**
 * CHU cua muc KENH dang chon (`aria-pressed="true"`), hoac `null` neu khong muc nao dang chon.
 *
 * ⚠️ Doc tu DOM THAT, khong tu prop/state: menh de cua cac bai W2 la "kenh nao DANG duoc chon",
 * va `aria-pressed` chinh la thu `ChannelZone` render ra tu `selectedId`.
 */
function kenhDangChon(container: HTMLElement): string | null {
  const chon = [...container.querySelectorAll(".ch__item")].filter(
    (el) => el.getAttribute("aria-pressed") === "true",
  );
  assert.ok(chon.length <= 1, `chi duoc co NHIEU NHAT mot muc kenh dang chon; do duoc ${chon.length}`);
  return chon.length === 0 ? null : (chon[0].textContent ?? "");
}

/**
 * XU LY THAT mot `POST /api/translations`: ghi hang vao ca hai route GIONG backend
 * (`routes_translations.create_translation` ghi hang `queued` voi 0 doan, roi xep DUNG MOT job
 * `translate`) va tra `201` kem `TranslationCreated = { translation, job }`.
 *
 * Tra ve CHINH body da tra, de bai test doc duoc trang thai JOB THAT thay vi bia mot chuoi.
 */
function taoBanDichTheoYeuCau(body: Record<string, unknown>): TranslationCreated {
  const transcriptId = Number(body["transcript_id"]);
  const engine = String(body["engine"]);
  const id = Math.max(...TRANSLATIONS.map((t) => t.id)) + 1;
  const moi: Translation = {
    id,
    transcript_id: transcriptId,
    engine,
    // Backend tu dien `"vi"` khi client KHONG gui `target_lang` (`CreateIn.target_lang: str = "vi"`).
    target_lang: "vi",
    prompt_version: "raw-p1",
    transcript_version: TRANSCRIPT_CHI_TIET[transcriptId]?.version ?? 1,
    status: "queued",
    stale: false,
    created_at: "2026-01-01T00:00:00Z",
  };
  // MOI NHAT TRUOC — dung thu tu route that tra ve.
  TRANSLATIONS = [moi, ...TRANSLATIONS];
  TRANSLATION_CHI_TIET[id] = {
    ...moi,
    // Ban dich VUA XEP: chua dich duoc doan nao (0 segment).
    segments: [],
    cps: { max_cps: 21, rows: [] },
  };
  const job = makeJob(20 + id, "translate", dem.jobTao, `translate:${engine}`, 0, { translation_id: id });
  return { translation: moi, job };
}

/** Anh chup cua hai fixture TRANSCRIPT luc nap module — `beforeEach` tra ve dung anh nay. */
const TRANSCRIPTS_GOC: TranscriptSummary[] = TRANSCRIPTS;
const TRANSCRIPT_CHI_TIET_GOC: Record<number, Transcript> = TRANSCRIPT_CHI_TIET;
const TRANSLATIONS_GOC: Translation[] = TRANSLATIONS;
const streams = new Set<ServerResponse>();
const sockets = new Set<Socket>();

const server: Server = createServer((req, res) => {
  const url = req.url ?? "";
  // KIEM ID NGAY TAI CUA SERVER: menh de cua bai "KHONG goi endpoint theo `null`" noi ve
  // REQUEST, nen no phai duoc do o phia nhan request.
  const trenDuong = /\/api\/(?:transcripts|translations)\/([^/?]+)/.exec(url);
  if (trenDuong !== null) {
    const id = Number(trenDuong[1]);
    if (!Number.isInteger(id) || id <= 0) dem.soYeuCauIdKhongHopLe += 1;
  }
  if (url.includes("transcript_id=")) {
    const id = Number(new URL(url, "http://127.0.0.1").searchParams.get("transcript_id"));
    if (!Number.isInteger(id) || id <= 0) dem.soYeuCauIdKhongHopLe += 1;
  }
  if (url === "/api/jobs/stream") {
    dem.stream += 1;
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
    res.write(": connected\n\n");
    streams.add(res);
    res.on("close", () => streams.delete(res));
    return;
  }
  // ---------------------------------------------------------------------------
  // D2 — HAI LENH TREN HANG DOI: huy job · chay lai job
  //
  // ⚠️ PHai kiem NHANH NAY TRUOC `url.startsWith("/api/jobs")` va phai PHAN NHANH THEO METHOD:
  // nhanh kia khong phan nhanh theo method, nen mot `POST /api/jobs/7/cancel` se bi no NUOT va
  // tra ve MOT MANG JOB (dung cai bay ma tep nay da canh bao cho `/api/translations`).
  // ---------------------------------------------------------------------------
  const khopLenh = /^\/api\/jobs\/(\d+)\/(cancel|retry)$/.exec(url);
  if (khopLenh !== null) {
    if (req.method !== "POST") {
      res.writeHead(405, { "content-type": "application/json" });
      res.end(JSON.stringify({ detail: "chi nhan POST" }));
      return;
    }
    const id = Number(khopLenh[1]);
    const chayLai = khopLenh[2] === "retry";
    if (chayLai) {
      dem.retry += 1;
      dem.retryTheoId[id] = (dem.retryTheoId[id] ?? 0) + 1;
      // Do luc request TOI NOI: PATCH nao da TRA XONG? (bang chung DI QUA hang doi ghi)
      dem.retrySauPatch = dem.patchXong;
    } else {
      dem.cancel += 1;
      dem.cancelTheoId[id] = (dem.cancelTheoId[id] ?? 0) + 1;
      dem.cancelSauPatch = dem.patchXong;
    }
    const traLenh = (): void => {
      const vitri = JOBS.findIndex((j) => j.id === id);
      if (vitri < 0) {
        if (chayLai) dem.retryTrangThai = 404;
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ detail: `job ${id} không tồn tại` }));
        return;
      }
      const job = JOBS[vitri];
      if (chayLai) {
        // ⚠️ FIXTURE PHAI KHOP DIEU HE THONG THAT SU LAM (`I2` cua review D2). 409 CHI co that khi
        // trang thai THAT cua job KHONG nam trong `RETRYABLE_STATES` (`job_state.py`:
        // `frozenset({failed, interrupted})`), va cau chu la NGUYEN VAN cua `routes_jobs.retry_job`:
        // `f"chỉ chạy lại được job ở trạng thái {sorted(js.RETRYABLE_STATES)}"`.
        // Fixture CU ban 409 cho CHINH mot job `failed` — ca BAT KHA (backend khong bao gio lam the),
        // va ban mot cau khong ton tai trong `backend/`.
        if (dem.retry409 && job.state !== "failed" && job.state !== "interrupted") {
          dem.retryTrangThai = 409;
          res.writeHead(409, { "content-type": "application/json" });
          res.end(JSON.stringify({
            detail: "chỉ chạy lại được job ở trạng thái ['failed', 'interrupted']",
          }));
          dem.retryXong += 1;
          return;
        }
        // Chay lai ⇒ job ve `queued` (backend xep lai hang doi). THAY the phan tu, khong sua object goc.
        JOBS[vitri] = { ...job, state: "queued", progress: 0, cancel_requested: false };
        dem.retryTrangThai = 200;
        dem.retryXong += 1;
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify(JOBS[vitri]));
        return;
      }
      // ⚠️ HOP DONG §2, VA NO LA MENH DE TRUNG THUC CUA CẢ TASK NAY: job `queued` bi huy NGAY;
      // job `running` CHI duoc DAT CO `cancel_requested` — trang thai VAN LA `running`, va anh
      // chup `/api/jobs` VAN noi `running` cho tới khi co su kien SSE.
      JOBS[vitri] = job.state === "running"
        ? { ...job, cancel_requested: true }
        : { ...job, state: "cancelled" };
      dem.cancelXong += 1;
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(JOBS[vitri]));
    };
    const treLenh = chayLai ? dem.retryTre : dem.cancelTre;
    if (treLenh > 0) setTimeout(traLenh, treLenh);
    else traLenh();
    return;
  }
  // ---------------------------------------------------------------------------
  // ITEM 5 — TẠO JOB (`POST /api/jobs`): đường DUY NHẤT để bóc lại bằng một engine ASR khác.
  //
  // ⚠️ Phải đứng TRƯỚC nhánh `url.startsWith("/api/jobs")` dưới đây: nhánh đó KHÔNG phân nhánh
  // theo method, nên một `POST /api/jobs` sẽ bị nó NUỐT và trả về MẢNG job cho một request TẠO
  // — đúng cái bẫy đã ghi cho `/api/translations` và `/api/sources/upload`.
  // ---------------------------------------------------------------------------
  if (url === "/api/jobs" && req.method === "POST") {
    dem.jobMoi += 1;
    let raw = "";
    req.on("data", (chunk) => { raw += String(chunk); });
    req.on("end", () => {
      dem.rawJobMoi = raw;
      let body: Record<string, unknown> = {};
      try { body = JSON.parse(raw) as Record<string, unknown>; } catch { body = {}; }
      dem.bodyJobMoi = body;
      const tra = (): void => {
        dem.jobMoiXong += 1;
        if (dem.jobMoiLoi) {
          // 422 NGUYÊN VĂN của `routes_jobs.create_job` ⇒ `raise HTTPException(422, str(exc))`
          // với `exc` từ `registry.by_id` (`KeyError(f"engine {engine_id!r} không có trong
          // registry")`). ⚠️ DẤU NHÁY KÉP bọc ngoài là của `str(KeyError(...))` (nó trả `repr`
          // của tham số), KHÔNG phải do test tự thêm — một fixture bỏ nó đi là một câu mà máy
          // chủ KHÔNG BAO GIỜ nói, và nó sẽ làm bài "lỗi nguyên văn" xanh với một câu sai.
          res.writeHead(422, { "content-type": "application/json" });
          res.end(JSON.stringify({
            detail: "\"engine 'fw-large-v3' không có trong registry\"",
          }));
          return;
        }
        // Hang job TRA VE theo dung `_job_json` (15 khoa cua `Job`) + 201 nhu route that.
        const job = makeJob(
          90 + dem.jobMoi,
          "asr",
          "queued",
          `asr:${String(body["engine"])}`,
          0,
          (body["payload"] ?? {}) as Record<string, unknown>,
        );
        res.writeHead(201, { "content-type": "application/json" });
        res.end(JSON.stringify(job));
      };
      if (dem.jobMoiTre > 0) setTimeout(tra, dem.jobMoiTre);
      else tra();
    });
    return;
  }
  if (url.startsWith("/api/jobs")) {
    dem.jobs += 1;
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(JOBS));
    return;
  }
  // ---------------------------------------------------------------------------
  // D2 — DUYET BAN GHI (`POST /api/transcripts/{id}/approve`)
  //
  // ⚠️ Phai dat TRUOC nhanh PATCH va TRUOC nhanh GET `/api/transcripts/` (hai nhanh do khop tien
  // to va khong phan biet duoc `/approve`).
  // ---------------------------------------------------------------------------
  const khopDuyet = /^\/api\/transcripts\/(\d+)\/approve$/.exec(url);
  if (khopDuyet !== null) {
    if (req.method !== "POST") {
      res.writeHead(405, { "content-type": "application/json" });
      res.end(JSON.stringify({ detail: "chi nhan POST" }));
      return;
    }
    const id = Number(khopDuyet[1]);
    dem.approve += 1;
    dem.approveTheoId[id] = (dem.approveTheoId[id] ?? 0) + 1;
    dem.approveSauPatch = dem.patchXong;
    const traDuyet = (): void => {
      if (dem.approveLoi) {
        // ⚠️ DUONG LOI DUY NHAT cua route `approve` la **404** (`routes_transcripts.py`:
        // `_require_transcript` ⇒ `HTTPException(404, str(exc))`; `grep 'không duyệt được' backend/`
        // = 0, tuc KHONG co nhanh 422 nao). Cau duoi day la NGUYEN VAN `NotFound` cua cong
        // (`sqlite_repos.get_transcript`: `f"transcript {transcript_id} không tồn tại"`).
        // Fixture CU phat 422 + mot cau TU NGHI ⇒ duong loi duy nhat tung chay cho `approve` la mot
        // ma trang thai KHONG TON TAI tren route do (`I2` cua review D2).
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ detail: `transcript ${id} không tồn tại` }));
        dem.approveXong += 1;
        return;
      }
      const cu = TRANSCRIPTS.find((t) => t.id === id);
      if (cu === undefined) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ detail: `transcript ${id} không tồn tại` }));
        return;
      }
      // ⚠️ DUYET **KHONG** TANG `version` (hop dong `endpoints.approveTranscript` + docstring
      // `routes_transcripts.approve`): chi doi `status` sang `reviewed`. Mot fixture tang version o
      // day se lam bai "duyet KHONG tang version" XANH gia.
      TRANSCRIPTS = TRANSCRIPTS.map((t) => (t.id === id ? { ...t, status: "reviewed" } : t));
      const dayDu = TRANSCRIPT_CHI_TIET[id];
      if (dayDu !== undefined) {
        TRANSCRIPT_CHI_TIET = { ...TRANSCRIPT_CHI_TIET, [id]: { ...dayDu, status: "reviewed" } };
      }
      dem.approveXong += 1;
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(TRANSCRIPTS.find((t) => t.id === id)));
    };
    if (dem.approveTre > 0) setTimeout(traDuyet, dem.approveTre);
    else traDuyet();
    return;
  }
  if (req.method === "PATCH" && url.startsWith("/api/transcripts/")) {
    // ⚠️ PHAN NHANH THEO METHOD va dat TRUOC nhanh GET `/api/transcripts/` (nhanh do khong phan
    // nhanh theo method, nen mot PATCH se bi no NUOT va tra ve mot BAN GHI CHUA SUA — dung cai bay
    // ma tep nay da canh bao cho `/api/translations`).
    dem.patch += 1;
    const id = Number(url.split("/")[3]);
    dem.patchTheoId[id] = (dem.patchTheoId[id] ?? 0) + 1;
    let raw = "";
    req.on("data", (chunk) => { raw += String(chunk); });
    req.on("end", () => {
      // BODY THAT, doc tu chinh request — khong phai mot gia tri test tu nghi ra.
      dem.patchRaw = raw;
      // ⚠️ GIU MOI body theo THU TU (C1): chi co `patchBody` (lan cuoi) thi khong dan duoc
      // "body PATCH thu hai" — bang chung duy nhat phan biet duoc "lan sau ghi de lan truoc".
      dem.patchBodies.push(raw);
      let body: { segments?: Segment[]; status?: string } = {};
      try { body = JSON.parse(raw) as { segments?: Segment[]; status?: string }; } catch { body = {}; }
      dem.patchBody = body;
      const cu = TRANSCRIPT_CHI_TIET[id];
      // Do tre CO DIEU KHIEN: chi bai C1 bat (`dem.patchTre`), mac dinh 0 ms ⇒ moi bai khac
      // khong doi hanh vi.
      const traLoi = (): void => {
        if (cu === undefined) {
          res.writeHead(404, { "content-type": "application/json" });
          res.end(JSON.stringify({ detail: `transcript ${id} không tồn tại` }));
          return;
        }
        if (dem.patchLoi) {
          // 422 NGUYEN VAN cua backend (`routes_transcripts.patch_transcript` ⇒ 422 khi mot doan
          // thieu khoa). Client phai hien CAU NAY, khong duoc thay bang mot chu chung.
          res.writeHead(422, { "content-type": "application/json" });
          res.end(JSON.stringify({ detail: "segment không hợp lệ: thiếu khoá 'text'" }));
          dem.patchXong += 1;
          return;
        }
        // ⚠️ GIONG BACKEND THAT: `routes_transcripts.patch_transcript` goi
        // `SqliteRepos.update_transcript_segments`, va ham do GHI segments roi TANG version DUNG MOT
        // (`sqlite_repos.py`: doc version + ghi version+1 trong CUNG mot giao dich). `stale` KHONG
        // duoc luu — no duoc TINH lai moi lan doc (`staleCua`), dung nhu `is_stale` cua backend.
        dem.versionTruocPatch[id] = cu.version;
        const version = cu.version + 1;
        // Object MOI, khong sua tai cho: anh chup `TRANSCRIPT_CHI_TIET_GOC` phai nguyen ven qua
        // `beforeEach` (sua tai cho se lam moi bai sau thay du lieu cua bai truoc).
        TRANSCRIPT_CHI_TIET = {
          ...TRANSCRIPT_CHI_TIET,
          [id]: { ...cu, segments: body.segments ?? [], version },
        };
        TRANSCRIPTS = TRANSCRIPTS.map((t) => (t.id === id ? { ...t, version } : t));
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify(TRANSCRIPT_CHI_TIET[id]));
        dem.patchXong += 1;
        // ⚠️ NGUOI GHI KHAC (nghia vu ghim cua D1): mot lan ghi KHAC ha canh NGAY SAU khi phan hoi
        // PATCH nay duoc gui di ⇒ lan DOC LAI ke tiep thay mot ban ghi `version` CAO HON ban ma
        // CHINH duong ghi nay vua gui (`vuaGhi.version < hienTai.version`). Phan hoi o tren da mang
        // ban TRUOC khi nguoi khac ghi (dung thu tu THAT cua mot cuoc dua).
        if (dem.nguoiGhiKhac) {
          const daGhi = TRANSCRIPT_CHI_TIET[id];
          TRANSCRIPT_CHI_TIET = {
            ...TRANSCRIPT_CHI_TIET,
            [id]: {
              ...daGhi,
              version: daGhi.version + 1,
              segments: daGhi.segments.map((s) =>
                s.i === 0 ? { ...s, text: "bản kênh hai (người khác sửa)" } : s),
            },
          };
          TRANSCRIPTS = TRANSCRIPTS.map((t) => (t.id === id ? { ...t, version: daGhi.version + 1 } : t));
        }
      };
      if (dem.patchTre > 0) setTimeout(traLoi, dem.patchTre);
      else traLoi();
    });
    return;
  }
  if (url.startsWith("/api/transcripts/")) {
    // ⚠️ Phai kiem NHANH NAY TRUOC `/api/transcripts`: `/api/transcripts/5` cung khop
    // tien to ngan, va mot lan doc chi tiet bi dem nham thanh lan doc danh sach se lam
    // phep do "MOT luot cho ca app" noi doi.
    dem.transcriptChiTiet += 1;
    const id = Number(url.split("/")[3]);
    dem.transcriptTheoId[id] = (dem.transcriptTheoId[id] ?? 0) + 1;
    const dayDu = TRANSCRIPT_CHI_TIET[id];
    if (dayDu === undefined) {
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ detail: `khong co transcript ${id}` }));
      return;
    }
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(dayDu));
    return;
  }
  if (url.startsWith("/api/transcripts")) {
    dem.transcripts += 1;
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(TRANSCRIPTS));
    return;
  }
  if (url.startsWith("/api/translations/")) {
    dem.translationChiTiet += 1;
    const id = Number(url.split("/")[3]);
    const dayDu = TRANSLATION_CHI_TIET[id];
    if (dayDu === undefined) {
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ detail: `khong co translation ${id}` }));
      return;
    }
    res.writeHead(200, { "content-type": "application/json" });
    // `stale` do MAY CHU tinh moi lan doc (xem `staleCua`) — khong phai mot co luu san.
    res.end(JSON.stringify({ ...dayDu, stale: staleCua(dayDu) }));
    return;
  }
  if (url.startsWith("/api/translations")) {
    // ⚠️ PHAN NHANH THEO METHOD: `POST /api/translations` (tao ban dich) KHONG duoc roi vao
    // nhanh GET danh sach — no se tra mot MANG cho mot request tao, va bai "bam dich ⇒ POST
    // toi server" se do vi mot ly do chang lien quan gi tới cua vao.
    if (req.method === "POST") {
      dem.postTranslations += 1;
      dem.contentTypeTao = req.headers["content-type"] ?? "";
      let raw = "";
      req.on("data", (chunk) => { raw += String(chunk); });
      req.on("end", () => {
        // BODY THAT, doc tu chinh request — khong phai mot gia tri test tu nghi ra. `rawTao`
        // giu NGUYEN VAN chuoi JSON de bao cao dan duoc byte ma client gui di.
        dem.rawTao = raw;
        let body: Record<string, unknown> = {};
        try { body = JSON.parse(raw) as Record<string, unknown>; } catch { body = {}; }
        dem.bodyTao = body;
        if (dem.loiTao) {
          // 409 NGUYEN VAN cua backend (`routes_translations.py`): engine chua san sang.
          // ⚠️ Client phai hien CAU NAY, khong duoc thay bang mot chu chung.
          res.writeHead(409, { "content-type": "application/json" });
          res.end(JSON.stringify({
            detail: "engine chưa sẵn sàng: 'opus-mt' (model chưa pull hoặc runtime không phục vụ được)",
          }));
          return;
        }
        res.writeHead(201, { "content-type": "application/json" });
        res.end(JSON.stringify(taoBanDichTheoYeuCau(body)));
      });
      return;
    }
    dem.translations += 1;
    // Loc theo DUNG query param ma `endpoints.listTranslations` gui di
    // (`/api/translations?transcript_id=<id>`): tra het moi ban dich se lam man Doi chieu
    // hien ban dich cua KENH KHAC — dung lop loi "hai nguon su that" ma du an dang chan.
    const transcriptId = Number(new URL(url, "http://127.0.0.1").searchParams.get("transcript_id"));
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(
      TRANSLATIONS.filter((t) => t.transcript_id === transcriptId)
        .map((t) => ({ ...t, stale: staleCua(t) })),
    ));
    return;
  }
  if (url.startsWith("/api/registry")) {
    dem.registry += 1;
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(REGISTRY));
    return;
  }
  if (url.startsWith("/api/status")) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(STATUS_HTTP));
    return;
  }
  if (url.startsWith("/api/glossary")) {
    // Man THUAT NGU (Task 9) tu goi endpoint cua no khi `mode === "glossary"`. Tra bang
    // RONG la du lieu THAT cua luot nay (DB repo rong) — va nho vay bai "bam Thuat ngu ⇒
    // man hien" khang dinh duoc man da THAT SU nap xong, khong phai dang cho.
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify([]));
    return;
  }
  if (req.method === "DELETE" && url.startsWith("/api/sources/")) {
    // ⚠️ PHẢI ĐỨNG TRƯỚC nhánh `/api/sources` bên dưới: nhánh đó KHÔNG phân nhánh theo
    // method, nên một `DELETE` sẽ bị nó nuốt và trả về MẢNG `SOURCES` (200) — đúng cái bẫy
    // mà tệp này đã cảnh báo cho `/api/translations` và `/api/sources/upload`.
    dem.xoaSource += 1;
    const id = Number(url.split("/")[3]);
    dem.xoaTheoId[id] = (dem.xoaTheoId[id] ?? 0) + 1;
    if (dem.xoaLoi) {
      // 409 NGUYÊN VĂN của backend: `routes_sources.delete_source` +
      // `app/api/delete_guard.mot_loi_409` — câu này nêu ĐÍCH DANH id job.
      res.writeHead(409, { "content-type": "application/json" });
      res.end(JSON.stringify({
        detail: `không xoá được nguồn ${id}: job #7 đang xếp hàng hoặc đang chạy trên nó `
          + `— huỷ job đó trước rồi xoá`,
      }));
      return;
    }
    if (!SOURCES.some((s) => s.id === id)) {
      // 404 NGUYÊN VĂN của cổng (`sqlite_repos.get_source`).
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ detail: `source ${id} không tồn tại` }));
      return;
    }
    // Máy chủ PHẢI QUÊN hàng đã xoá: chỉ trả 204 mà `GET /api/sources` còn hàng thì "đọc lại
    // danh sách" là một lời khai không kiểm được (xem `dem.xoaDaXoa`).
    dem.xoaDaXoa.push(id);
    // 204 KHÔNG thân — đúng hình dạng `routes_sources.delete_source` (và `client.call` đã
    // phân nhánh riêng cho 204, không gọi `json()`).
    res.writeHead(204);
    res.end();
    return;
  }
  if (url.startsWith("/api/sources/upload")) {
    // ⚠️ DUONG NAP — phai kiem NHANH NAY TRUOC `/api/sources`, va phai phan nhanh theo METHOD.
    // Nhanh `/api/sources` (duoi day) khong phan nhanh theo method, nen mot
    // `POST /api/sources/upload` se bi no NUOT va tra ve MANG `SOURCES` — dung cai bay ma
    // `App.test.tsx` da canh bao cho `/api/translations` o tren.
    if (req.method !== "POST") {
      res.writeHead(405, { "content-type": "application/json" });
      res.end(JSON.stringify({ detail: "chi nhan POST" }));
      return;
    }
    dem.upload += 1;
    // URL NGUYEN VAN (ke ca query neu co): do la thu phan biet `lang` trong BODY voi `lang`
    // trong QUERY — mutation `W2-4` lam no khac di.
    dem.uploadUrl = url;
    dem.uploadContentType = req.headers["content-type"] ?? "";
    const manh: Buffer[] = [];
    req.on("data", (chunk: Buffer) => { manh.push(chunk); });
    req.on("end", () => {
      // ⚠️ BYTE THO, khong qua `String(chunk)` (nhu nhanh JSON o tren): than multipart mang BYTE
      // cua tep, va mot phep do "byte di nguyen ven" chi co nghia neu doc tu chinh buffer nhan duoc.
      const raw = Buffer.concat(manh);
      dem.uploadRaw = raw;
      const phan = bocMultipart(raw, dem.uploadContentType);
      dem.uploadPhan = phan.map((p) => p.ten);
      const phanTep = phan.find((p) => p.ten === "file");
      const phanLang = phan.find((p) => p.ten === "lang");
      dem.uploadLang = phanLang === undefined ? null : phanLang.than.toString("utf8");
      const ten = phanTep?.filename ?? "";
      if (phanTep !== undefined) {
        dem.uploadTenTep.push(ten);
        dem.uploadByteTep.push([...phanTep.than]);
      }
      if (dem.uploadLoiToanBo || dem.uploadLoiTheoTen.includes(ten)) {
        // 422 NGUYEN VAN cua backend (`routes_sources.upload` ⇒ `HTTPException(422, "tệp rỗng")`).
        res.writeHead(422, { "content-type": "application/json" });
        res.end(JSON.stringify({ detail: "tệp rỗng" }));
        return;
      }
      // KENH MOI di vao CHINH mang ma `GET /api/sources` tra ve — nen "danh sach kenh duoc doc
      // lai" la menh de DO DUOC: hang moi chi xuat hien neu co mot lan doc lai THAT.
      const idMoi = Math.max(...SOURCES.map((s) => s.id)) + 1;
      const moi: Source = {
        id: idMoi,
        kind: "file",
        origin: ten,
        media_path: `media/${idMoi}.bin`,
        audio_path: null,
        duration: null,
        lang: dem.uploadLang === "en" ? "en" : "zh",
        created_at: "2026-01-01T00:00:00Z",
      };
      SOURCES.push(moi);
      const job = makeJob(40 + idMoi, "ingest", "queued", "ingest:-", 0, {
        source_id: idMoi,
        lang: moi.lang,
      });
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ source: moi, job }));
    });
    return;
  }
  if (url.startsWith("/api/sources")) {
    dem.sources += 1;
    if (dem.loiSources) {
      // Loi THAT cua FastAPI: `client.ts` doc `detail` ra khoi body, nen cau tieng
      // Viet cua backend phai di duoc tới nguoi doc — khong bi nuot thanh "500".
      res.writeHead(500, { "content-type": "application/json" });
      res.end(JSON.stringify({ detail: "nguồn dữ liệu hỏng (cố ý)" }));
      return;
    }
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(SOURCES.filter((s) => !dem.xoaDaXoa.includes(s.id))));
    return;
  }
  res.writeHead(404, { "content-type": "text/plain" });
  res.end("khong co route nay");
});

server.on("connection", (socket) => {
  sockets.add(socket);
  socket.on("close", () => sockets.delete(socket));
});

/** Ghi mot su kien SSE vao MOI stream dang mo — dung dinh dang `format_sse`. */
function emit(body: string): void {
  for (const res of streams) res.write(body);
}

function sse(event: unknown): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

/**
 * Mo ta mot gia tri ma KHONG goi sau vao no: `console.error` cua React nhan ca
 * node DOM, va doc sau vao mot node cua jsdom da `close()` la tu chuoc loi.
 */
function mo(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined) return "undefined";
  if (value === null) return "null";
  const kind = typeof value;
  if (kind !== "object" && kind !== "function") return String(value);
  return Object.prototype.toString.call(value);
}

const consoleGoc = { error: console.error, warn: console.warn };
const tiengOn: string[] = [];

function batTiengOn(): void {
  console.error = (...args: unknown[]): void => {
    tiengOn.push(`error: ${args.map(mo).join(" ")}`);
  };
  console.warn = (...args: unknown[]): void => {
    tiengOn.push(`warn: ${args.map(mo).join(" ")}`);
  };
}

function traTiengOn(): void {
  console.error = consoleGoc.error;
  console.warn = consoleGoc.warn;
}

let origin = "";
let render: (ui: unknown) => { container: HTMLElement; unmount: () => void };
let waitFor: (cb: () => void, options?: { timeout?: number; interval?: number }) => Promise<void>;
/** Tim theo VAI TRO + TEN DOC DUOC — dung cach Task 12 tim control che do. */
let getByRole: (container: HTMLElement, role: string, options?: { name?: RegExp | string }) => Element;
/** ⚠️ `fireEvent`, KHONG `userEvent`: repo KHONG co `@testing-library/user-event`. */
let fireEvent: {
  click: (el: Element) => void;
  change: (el: Element, init: unknown) => void;
  drop: (el: Element, init?: unknown) => boolean;
};
let cleanup: () => void;
/**
 * `act` của chính React (RTL re-export) — cần cho phép đo DUY NHẤT của tệp này phát một
 * `KeyboardEvent` THÔ (không qua `fireEvent`) để đọc được `defaultPrevented`: `fireEvent` chỉ
 * trả `!defaultPrevented`, còn mệnh đề của guard control native nói về chính cờ đó.
 */
let act: (cb: () => void) => void;
let App: () => unknown;
/**
 * `createElement`, KHONG goi thang `App()`: goi ham component ngoai chu trinh render
 * cua React thi `useState` nhan dispatcher `null` (`TypeError: Cannot read properties
 * of null (reading 'useState')`) — da do duoc, khong phai gia thuyet. Lay no qua
 * `import("react")` SAU `setupDom`, giong moi thu khac trong tep nay.
 */
let taoPhanTu: (type: unknown) => unknown;

/**
 * `play`/`pause` NGUYÊN BẢN của `HTMLMediaElement` trong jsdom — `before` thay chúng bằng hàm rỗng
 * (jsdom KHÔNG hiện thực hai hàm này và log `Not implemented` ra `console.error`, mà tệp này ghim
 * "không tiếng ồn console"), `after` trả lại. Xem comment đầy đủ ở `before`.
 */
let playGoc: (() => unknown) | null = null;
let pauseGoc: (() => unknown) | null = null;

/** Cho chuoi xuat hien trong DOM THAT — `waitFor` co han nen khong treo vo han. */
async function choChu(container: HTMLElement, chuoi: string): Promise<void> {
  await waitFor(
    () => {
      const text = container.textContent ?? "";
      assert.ok(
        text.includes(chuoi),
        `chua thay "${chuoi}" trong DOM; do duoc: ${JSON.stringify(text.slice(0, 400))}`,
      );
    },
    { timeout: 5000, interval: 20 },
  );
}

/**
 * Text cua TUNG phan tu khop `chon` — can cho cac khang dinh phai GAN DUNG doi tuong.
 *
 * Vi sao khong duoc dung `container.textContent.includes(...)`: review vong #1 do duoc
 * rang dao hai nhan "đã tách tiếng"/"chưa tách tiếng" trong `ChannelZone` lam CA NAM
 * MUOI bai van xanh — vi kiem ca DOM chi hoi "hai chuoi nay co xuat hien o dau do
 * khong", ma sau khi dao thi ca hai VAN xuat hien, chi la gan sai kenh.
 */
function textCua(container: HTMLElement, chon: string): string[] {
  return [...container.querySelectorAll(chon)].map((el) => el.textContent ?? "");
}

/**
 * Cho `ms` mili giay NHUNG di qua `waitFor`.
 *
 * ⚠️ VI SAO KHONG dung `await new Promise(r => setTimeout(r, ms))`: do duoc o luot chay dau
 * cua bai "khong bao request" — mot su kien SSE cap nhat state React NGOAI `act()`, va mot
 * `setTimeout` TRAN roi vao dung cua so do ⇒ `console.error` ban ra
 * *"An update to App inside a test was not wrapped in act(...)"*, lam bai "khong tieng on
 * console" DO vi mot ly do KHONG lien quan den menh de dang do. `waitFor` cua Testing Library
 * boc callback trong `asyncWrapper` (co `act`), nen cho qua no thi im lang.
 *
 * ⚠️ **`choNhip` la mot `sleep` THUAN, khong phai mot phep cho theo tin hieu** (ERRATA #35
 * muc 2): dieu kien thoat `Date.now() >= xong` la ham cua DONG HO nen no LUON tro thanh dung.
 * Cho nay la cho DUY NHAT con dung no trong tep (3 luot kia la cua W1, do "khong bao request"
 * can mot KHOANG LANG de mot request co the tới noi nhan). Moi phep do MOI phai dung `choHaiNhip`
 * hoac mot `waitFor` theo dung tin hieu can doc.
 */
async function choNhip(ms: number): Promise<void> {
  const xong = Date.now() + ms;
  await waitFor(
    () => {
      assert.ok(Date.now() >= xong, `chua du ${ms} ms`);
    },
    { timeout: ms + 2000, interval: 25 },
  );
}

/**
 * Cho HAI vong microtask cua chinh `queueMicrotask` — du de bat ky `.then()` nao cua mot
 * `fetch` ALREADY-QUEUED chay xong, nhung KHONG cho dong ho chay.
 *
 * ⚠️ VI SAO CO HAM NAY (dinh chinh `Minor #2` cua review W3): bao cao W3 khai *"0 phep cho
 * theo dong ho duoc them"* — **SAI**: bai `W3 KHONG CO ENGINE` goi `choNhip(250)`, va `choNhip`
 * la `sleep` THUAN. Do la mot phep do YEU: no khong khang dinh duoc dieu gi ngoai "da qua
 * 250 ms". Voi mot khang dinh PHU DINH o PHIA SERVER (`dem.postTranslations === 0`) thi thu can
 * khong phai la THOI GIAN ma la mot CO HOI cho mot request CO THE tới noi nhan. Hai vong
 * microtask lam dung dieu do, va lam no *manh hon*: neu mot handler DA goi `fetch`, `.then()`
 * cua no se chay trong hai vong nay va bo dem o server se khac 0.
 *
 * ⚠️ Gioi han phai khai: hai vong microtask KHONG bao gio qua duoc mot `setTimeout`/I/O that,
 * nen day KHONG phai mot phep cho "moi thu da xong" — no chi ghim menh de *"khong co request
 * nao duoc GUI RA dong bo hoac trong hai vong microtask ke tiep"*. Do la dung menh de cua bai
 * do (nut VO HIEU thi khong duoc goi API), va no MANH HON `choNhip(250)` o cho: no khong the
 * xanh chi vi dong ho da chay.
 */
async function choHaiNhip(): Promise<void> {
  await new Promise<void>((resolve) => queueMicrotask(resolve));
  await new Promise<void>((resolve) => queueMicrotask(resolve));
}

/** Cho toi khi MOT phan tu khop `chon` thoa `dieuKien`; nem loi doc duoc kem DOM that. */
async function choPhanTu(
  container: HTMLElement,
  chon: string,
  dieuKien: (text: string) => boolean,
  moTa: string,
): Promise<string> {
  let cuoi = "";
  await waitFor(
    () => {
      const khop = textCua(container, chon).find(dieuKien);
      assert.ok(
        khop !== undefined,
        `${moTa}; do duoc: ${JSON.stringify(textCua(container, chon))}`,
      );
      cuoi = khop;
    },
    { timeout: 5000, interval: 20 },
  );
  return cuoi;
}

/**
 * Cho toi khi MOT phan tu khop `chon` thoa `dieuKien` DOC TREN CHINH NODE (khong phai text).
 *
 * ⚠️ Vi sao can ban thu hai: `aria-checked`/`aria-pressed` la trang thai MAY doc duoc, va
 * mot phep cho theo CHU khong phan biet duoc "ban 11 dang duoc chon" voi "ban 11 dang co mat"
 * (ca hai deu lam `textContent` chua chuoi do). Cho theo THUOC TINH la cho theo dung tin hieu
 * ma bai test sap khang dinh.
 */
async function choPhuHop(
  container: HTMLElement,
  chon: string,
  dieuKien: (el: Element) => boolean,
  moTa: string,
): Promise<void> {
  await waitFor(
    () => {
      const khop = [...container.querySelectorAll(chon)].find(dieuKien);
      assert.ok(
        khop !== undefined,
        `${moTa}; do duoc: ${JSON.stringify([...container.querySelectorAll(chon)].map((el) => el.getAttribute("aria-checked") ?? el.getAttribute("aria-pressed")))}`,
      );
    },
    { timeout: 5000, interval: 20 },
  );
}

/**
 * PHEP DO `SAME` (bat bien `I2`, ERRATA #36 muc 4): so ban ma VUNG DOI CHIEU dang chon voi
 * ban ma THANH TRANSPORT tro toi — hai con so doc tu DOM THAT.
 *
 * ⚠️ Vi sao doc tu DOM chu khong tu prop: mot bai test truyen prop thi do CHINH no dang do,
 * con `data-translation-id` la thu `Transport` THUC SU render ra tu `translationId`.
 */
async function soSanhHaiVung(container: HTMLElement): Promise<{ chon: number; xuat: number }> {
  const dangChon = [...container.querySelectorAll('[data-testid^="pick-"]')].filter(
    (el) => el.getAttribute("aria-checked") === "true",
  );
  assert.equal(dangChon.length, 1, `phai co DUNG MOT ban dich dang chon; do duoc ${dangChon.length}`);
  const chon = Number((dangChon[0].getAttribute("data-testid") ?? "").replace("pick-", ""));
  const xuat = Number(phanTu(container, ".tp__xuat").getAttribute("data-translation-id"));
  assert.ok(Number.isInteger(chon) && chon > 0, `khong doc duoc ban dang chon; do duoc ${chon}`);
  assert.ok(Number.isInteger(xuat) && xuat > 0,
    `khong doc duoc ban ma thanh transport tro toi; do duoc ${JSON.stringify(phanTu(container, ".tp__xuat").getAttribute("data-translation-id"))}`);
  return { chon, xuat };
}

/**
 * Phan tu DAU TIEN khop `chon` — tra ve NODE de doc thuoc tinh/bam.
 *
 * ⚠️ Khong bao gio dua node nay vao `assert`: `assert` dinh dang gia tri trong thong diep
 * loi KHONG gioi han do sau, va mot node DOM cua React la mot do thi khong lo ⇒ do duoc o
 * Task 6 la **218 697 ms roi OOM** (ERRATA #14 muc 3). Moi khang dinh o day la BOOLEAN
 * (`assert.ok(el !== null)`) hoac tren `textContent`/`getAttribute`.
 */
function phanTu(container: HTMLElement, chon: string): Element {
  const el = container.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el;
}

/** `textContent` cua phan tu DAU TIEN khop `chon`. */
function chu(container: HTMLElement, chon: string): string {
  return phanTu(container, chon).textContent ?? "";
}

/**
 * Id BAN DICH ma ba nut XUAT tro toi — doc tu `href` THAT cua nut xuat.
 *
 * ⚠️ KHONG doc `data-translation-id`: do la `translationId` (ban DANG XEM), KHONG phai ban SE
 * XUAT (xem `Transport`). Hai cau hoi khac nhau, va `F2` cua re-review W3 #1 chinh la cho chung
 * lech nhau: ban dang xem `done` ma `href` van tro ban `done` moi nhat.
 */
function idXuat(container: HTMLElement): number | null {
  const href = phanTu(container, ".tp__xuat").getAttribute("href");
  if (href === null) return null;
  const khop = /^\/api\/export\/(\d+)\?/.exec(href);
  return khop === null ? null : Number(khop[1]);
}

/** Muc KENH (nut) chua `chuoi` — tra theo CHU, khong theo thu tu mang. */
function nutKenh(container: HTMLElement, chuoi: string): Element {
  const khop = [...container.querySelectorAll(".ch__item")].find(
    (el) => (el.textContent ?? "").includes(chuoi),
  );
  assert.ok(khop !== undefined, `khong thay muc kenh nao chua "${chuoi}"`);
  return khop as Element;
}

/**
 * Cho vung Doi chieu co DU so HANG ban dich trong DOM THAT — **DUNG dau ra ma bai sap doc**.
 *
 * ⚠️ THAY CHO `waitFor(() => assert.equal(dem.translationChiTiet, N))` (vong sua W3 #2, `Important`
 * F1 cua re-review). Bo dem do la mot **SO TICH LUY O PHIA SERVER**, va no KHONG phai mot dai luong
 * CUA BAI NAY: mot request CON DANG BAY cua bai TRUOC ha canh SAU `beforeEach` (no tra bo dem ve 0)
 * cung lam no tang. DO DUOC bang log request phia server (xem bao cao vong sua #2): mot lan doc
 * CHI TIET cua mot transcript KHAC roi vao bai sau va lam bo dem khong bao gio bang con so bai
 * mong ⇒ `waitFor` het han va bao `3 !== 2` / `4 !== 2`.
 *
 * ⚠️ Va phep cho nay MANH HON, khong yeu hon: mot hang `pick-` chi co mat khi `GET
 * /api/translations/{id}` cua MOI hang da ket thuc va React da COMMIT — tuc no cho dung thu bai
 * sap doc, va no khong the xanh (hay do) vi mot request cua bai khac.
 */
async function choDanhSachBanDich(container: HTMLElement, soLuong: number): Promise<void> {
  await waitFor(
    () => {
      const hang = container.querySelectorAll('[data-testid^="pick-"]');
      assert.equal(
        hang.length,
        soLuong,
        `phai co ${soLuong} hang ban dich cua ban ghi trong vung Doi chieu`,
      );
    },
    { timeout: 5000, interval: 20 },
  );
}

/**
 * Di DUONG THAT toi vung Doi chieu: cho kenh that, bam kenh, doi radio "Đối chiếu", roi cho
 * `soLuong` HANG ban dich trong DOM.
 *
 * ⚠️ `soLuong > 0` la mot phep cho THEO TIN HIEU DOM — khong theo dong ho, va khong theo bo dem
 * tich luy o phia server (xem `choDanhSachBanDich`). `transcript` va `translations` la HAI `useApi`
 * doc lap, nen mot hang `pick-` chi xuat hien khi ca hai da xong. Voi `soLuong === 0` thi khong
 * cho: bai "chua co ban dich nao" CAN trang thai rong that.
 */
async function toiDoiChieu(container: HTMLElement, soLuong: number): Promise<void> {
  await choChu(container, "kenh-mot.wav");
  fireEvent.click(nutKenh(container, "kenh-mot.wav"));
  await choChu(container, "câu 1");
  fireEvent.click(getByRole(container, "radio", { name: /đối chiếu/i }));
  if (soLuong > 0) await choDanhSachBanDich(container, soLuong);
}

/**
 * Mo man BIEN TAP cua KENH HAI (ban ghi #3) — BON doan, doan cuoi mang `suspect`/`qa`.
 *
 * ⚠️ Cho theo TIN HIEU DOM, khong theo dong ho va khong theo bo dem tich luy o phia may chu: ten
 * kenh, roi CHU CUA DOAN CUOI. Chu do chi co khi `GET /api/transcripts/3` da xong VA React da
 * commit ⇒ dung thu bai sap doc (ERRATA #38 muc 2/#39 muc 3).
 */
async function toiBienTapBonDoan(container: HTMLElement): Promise<void> {
  await choChu(container, "kenh-hai");
  fireEvent.click(nutKenh(container, "kenh-hai"));
  await choChu(container, "bản kênh hai");
  await choChu(container, "dòng bốn");
}

/** Bam mot dong ⇒ cho toi khi dong do THANH O SUA (tin hieu DOM that), roi tra ve chinh o do. */
async function moOSua(container: HTMLElement, i: number): Promise<HTMLTextAreaElement> {
  fireEvent.click(phanTu(container, `[data-i="${i}"] button`));
  await choPhuHop(
    container,
    `[data-i="${i}"]`,
    (el) => (el.getAttribute("class") ?? "").split(/\s+/).includes("is-editing"),
    `dong ${i} chua thanh o sua`,
  );
  const o = container.querySelector(`[data-i="${i}"] textarea`);
  assert.ok(o !== null, `dong ${i} phai la mot O SUA (textarea)`);
  return o as HTMLTextAreaElement;
}

/**
 * NUDGE bằng bàn phím THEO SPEC: `Shift+←/→` = ±0,1s, `Alt+←/→` = ±1s (spec UI §5.1 dòng 300–301,
 * §5.2 dòng 309).
 *
 * ⚠️ VÌ SAO CÓ HELPER NÀY: trước Task 11, **bảy** bài trong tệp này bấm `[`/`]` cho nudge — ĐÚNG
 * "bảng phím của brief D1", **SAI nguồn spec** (ERRATA #44 mục 3: `[`/`]` = đặt mốc TẠI ĐẦU ĐỌC).
 * Ánh xạ mới nằm ở MỘT chỗ, nên lần đổi sau không phải sửa bảy bài bằng tay (và không có bài nào
 * bị bỏ sót).
 */
function bamNudge(moc: "start" | "end", buoc: 0.1 | 1 = 0.1): void {
  fireEvent.keyDown(document.body, {
    key: moc === "start" ? "ArrowLeft" : "ArrowRight",
    shiftKey: buoc === 0.1,
    altKey: buoc === 1,
  });
}

/**
 * Đặt ĐẦU ĐỌC của phần tử media THẬT trong cây rồi phát `timeupdate` — đúng đường mà trình duyệt
 * báo vị trí phát. jsdom hiện thực `currentTime` như một thuộc tính THẬT (đo được: gán 3,25 ⇒ đọc
 * lại 3,25), nên "mốc tại đầu đọc" ĐO ĐƯỢC ở đây; thứ KHÔNG đo được ở đây là ÂM THANH (jsdom không
 * có codec/`play()`) — xem TRẦN trong báo cáo task-11.
 */
function datDauDoc(container: HTMLElement, giay: number): void {
  const media = phanTu(container, "audio.tp__media") as HTMLAudioElement;
  media.currentTime = giay;
  fireEvent.timeUpdate(media);
}

describe("App: KENH THAT + HANG DOI THAT tu server node:http trong tien trinh", () => {
  before(async () => {
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
    const { port } = server.address() as AddressInfo;
    origin = `http://127.0.0.1:${port}`;
    // Chuan hoa TRUOC khi cai: khong dua vao viec tep khac da tra global hay chua.
    teardownDom();
    setupDom(origin);
    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    waitFor = api.waitFor;
    getByRole = api.getByRole;
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    act = api.act;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    // ⚠️ BỊT MỘT LỖ CỦA JSDOM — cùng lý do và cùng cách `Transport.test.tsx` (mục 2 ở đầu tệp đó):
    // jsdom KHÔNG hiện thực `HTMLMediaElement.play()`/`pause()`; hai hàm đó log
    // `Not implemented: HTMLMediaElement's play() method` ra `console.error`, và CHÍNH TỆP NÀY ghim
    // "không tiếng ồn console". Bài `T11 PHÁT / TẠM DỪNG` bấm `Space` nên đường đó được thi hành
    // THẬT. Đây KHÔNG phải mock nghiệp vụ: `Transport` vẫn gọi `play()`/`pause()` trên CHÍNH phần
    // tử media đã render — chỉ có phần "phát tiếng" (jsdom không có) là bị bịt.
    const w: any = (globalThis as any).window;
    playGoc = w.HTMLMediaElement.prototype.play;
    pauseGoc = w.HTMLMediaElement.prototype.pause;
    w.HTMLMediaElement.prototype.play = function (): unknown {
      dem.play += 1;
      return undefined;
    };
    w.HTMLMediaElement.prototype.pause = function (): void {
      dem.pause += 1;
    };
    batTiengOn();
    const shell: any = await import("./App.tsx");
    App = shell.App;
  });

  beforeEach(() => {
    tiengOn.length = 0;
    dem.sources = 0;
    dem.jobs = 0;
    dem.stream = 0;
    dem.loiSources = false;
    dem.registry = 0;
    dem.postTranslations = 0;
    dem.bodyTao = null;
    dem.rawTao = "";
    dem.contentTypeTao = "";
    dem.loiTao = false;
    dem.jobTao = "queued";
    REGISTRY = REGISTRY_HTTP;
    dem.transcripts = 0;
    dem.transcriptChiTiet = 0;
    dem.translations = 0;
    dem.translationChiTiet = 0;
    dem.soYeuCauIdKhongHopLe = 0;
    dem.transcriptTheoId = {};
    // DUONG NAP: moi bo dem/gia tri cua fixture phai ve 0/goc, neu khong mot luot nap cua bai
    // TRUOC song sot sang bai SAU va lam phep do "co dung MOT lan nap" xanh (hay do) vo nghia.
    dem.upload = 0;
    dem.uploadUrl = "";
    dem.uploadContentType = "";
    dem.uploadRaw = null;
    dem.uploadPhan = [];
    dem.uploadLang = null;
    dem.uploadTenTep = [];
    dem.uploadByteTep = [];
    dem.uploadLoiTheoTen = [];
    dem.uploadLoiToanBo = false;
    // DUONG GHI (D1): MOT helper, khong liet ke tay — M5 cua review do duoc rang mot lan reset
    // thieu `patchBody`/`versionTruocPatch` lam khang dinh SAU moc reset doc body CU va XANH gia.
    xoaDemGhi();
    // BA LENH GHI MOI (D2): cung ly do — MOT helper, khong liet ke tay.
    xoaDemLenh();
    // DUONG MEDIA (vong sua 1, I-3): hai bo dem nay cung la bo dem TICH LUY ⇒ phai ve 0 moi bai.
    xoaDemMedia();
    // DUONG TAO JOB (item 5): cung ly do — MOT helper, khong liet ke tay.
    xoaDemBocLai();
    // DUONG XOA KENH: cung ly do — MOT helper, khong liet ke tay.
    xoaDemXoa();
    dem.nguoiGhiKhac = false;
    // ⚠️ CA MANG KENH: mot luot nap THEM mot hang THAT (`SOURCES.push`) ⇒ khong cat ve anh goc thi
    // bai sau se thay kenh cua bai truoc, va "kenh MOI xuat hien" xanh ngay ca khi khong doc lai.
    SOURCES.length = SO_SOURCE_GOC;
    // Fixture tra ve DUNG anh luc nap module: bai "ban ghi moi hien ra" them mot hang, va
    // mot hang song sot sang bai sau se lam moi phep do "MOT luot doc" noi doi.
    TRANSCRIPTS = TRANSCRIPTS_GOC;
    TRANSCRIPT_CHI_TIET = TRANSCRIPT_CHI_TIET_GOC;
    // ⚠️ CA MANG BAN DICH: bai W3 them mot hang THAT qua `POST` o server, va hang do song sot
    // sang bai sau thi "ban vua tao tro thanh ban dang xem" se xanh ngay ca khi khong co gi moi.
    TRANSLATIONS = TRANSLATIONS_GOC;
    // ⚠️ CA MANG JOB, KHONG CHI DO DAI: bai `I3` day mot job DICH vao anh chup (xem `themJobDich`),
    // va job do song sot sang bai sau thi "job cua BAN KHAC khong keo request" se DO vi mot job thua.
    // D2 them: hai route `cancel`/`retry` THAY THE mot phan tu cua mang, nen cat do dai khong du —
    // phai dung lai dung ANH GOC (`JOBS_GOC`).
    assert.equal(JOBS_GOC.length, SO_JOB_GOC, "anh goc cua JOBS phai giu nguyen so job");
    JOBS.length = 0;
    JOBS.push(...JOBS_GOC);
  });

  // `cleanup` cua Testing Library go DOM da render — khong cham vao global nao,
  // nen no KHONG bat buoc phai nam trong `describe`; dat o day vi no thuoc suite nay.
  afterEach(() => {
    cleanup();
  });

  after(async () => {
    traTiengOn();
    // TRẢ `play`/`pause` CỦA JSDOM về nguyên trạng TRƯỚC `teardownDom`: global/suite sau phải thừa
    // hưởng đúng trạng thái mà tệp này nhận (cùng luật với `Transport.test.tsx`).
    const w: any = (globalThis as any).window;
    if (w !== undefined && playGoc !== null && pauseGoc !== null) {
      w.HTMLMediaElement.prototype.play = playGoc;
      w.HTMLMediaElement.prototype.pause = pauseGoc;
    }
    for (const res of [...streams]) {
      try {
        res.end();
      } catch {
        // da dong roi
      }
    }
    streams.clear();
    for (const socket of [...sockets]) socket.destroy();
    sockets.clear();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    teardownDom();
  });

  it("hien kenh THAT va hang doi THAT (chi tiet tung buoc + LY DO CHO), khong tieng on console", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    // KENH: hai ten tep den tu server, khong phai tu mot fixture trong test.
    await choChu(container, "kenh-mot.wav");
    await choChu(container, "https://vid.example/kenh-hai");
    await choChu(container, "zh");
    // Tin hieu buoc THAT ma backend co noi: da tach tieng / chua, va chua do thoi luong.
    await choChu(container, "đã tách tiếng");
    await choChu(container, "chưa tách tiếng");
    await choChu(container, "chưa đo thời lượng");

    // HANG DOI: job dang chay va job dang cho, moi cai kem LY DO lay tu phase+state.
    await choChu(container, "asr:faster-whisper-large");
    await choChu(container, "đang chạy");
    await choChu(container, "translate:qwen2.5-7b");
    await choChu(container, "chờ gom lô");

    // BANG CHUNG duong THAT: server dem duoc request. Khong co no thi bai nay
    // xanh vi mot ly do khac (du lieu den tu dau do khong phai HTTP).
    assert.equal(dem.sources, 1, "App phai goi /api/sources dung MOT lan");
    assert.ok(dem.jobs >= 1, `phai doc anh chup /api/jobs, do duoc ${dem.jobs}`);
    assert.ok(dem.stream >= 1, `phai mo /api/jobs/stream, do duoc ${dem.stream}`);

    assert.deepEqual(tiengOn, [], "render <App/> THAT khong duoc sinh tieng on console");
    unmount();
  });

  it("stream sut su kien cho id DA BIET: hang doi doi theo, khong doc lai anh chup", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    // Trang thai tu ANH CHUP truoc: RIENG job 8 dang cho. Khong the hoi ca DOM "co chu
    // chờ gom lô khong": job 6 (ingest cua kenh 2) CUNG dang cho ⇒ phep do se RONG.
    await choPhanTu(
      container,
      ".q__item",
      (t) => t.includes("#8 ") && t.includes("chờ gom lô"),
      "job 8 chua hien la dang cho",
    );
    const jobsSauAnhChup = dem.jobs;

    // ⚠️ Cho stream THAT SU mo truoc khi ghi su kien.
    // DO DUOC: mot lan chay mutation (MINE-4, vong truoc) bai nay do voi DOM cho thay
    // job 8 VAN o trang thai anh chup sau khi `emit` ⇒ su kien khong tới DOM.
    // SUY RA (chua chung minh duoc): nguyen nhan la `emit` roi vao luc `streams` con
    // RONG, vi hook publish anh chup TRUOC roi moi mo stream. Reviewer vong #1 do
    // mutation REMOVEWAIT (bo khoi cho nay) va no **KHONG** giết bài nào ⇒ nguyen nhan
    // do KHONG tái lập được, nên đây là phòng thủ, không phải bất biến đã chứng minh.
    await waitFor(
      () => {
        assert.ok(streams.size >= 1, "hook chua mo /api/jobs/stream");
      },
      { timeout: 5000, interval: 20 },
    );

    // Mot su kien THAT di qua `node:http` → parser SSE → map job → DOM.
    emit(sse({ id: 8, state: "running", progress: 0.1, phase: "translate:qwen2.5-7b", error: null, log_tail: "" }));

    // Chuoi nay CHI job 8 moi sinh ra duoc: job 7 dang chay voi phase "asr:…". Neu chi
    // cho chu "đang chạy" thi job 7 (dang chay san trong anh chup) da lam bai test XANH
    // ngay ca khi su kien khong he tới — mot phep do rong.
    const item8 = await choPhanTu(
      container,
      ".q__item",
      (t) =>
        t.includes("#8 ")
        && t.includes("đang chạy · translate:qwen2.5-7b")
        && t.includes("10%"),
      "job 8 khong duoc cap nhat tu su kien stream",
    );
    assert.ok(
      !item8.includes("chờ gom lô"),
      `job 8 da chay thi khong duoc con hien "chờ gom lô"; do duoc: ${JSON.stringify(item8)}`,
    );
    assert.equal(
      dem.jobs,
      jobsSauAnhChup,
      "su kien cho id DA BIET khong duoc keo them mot lan doc anh chup /api/jobs",
    );

    assert.deepEqual(tiengOn, [], "cap nhat qua stream khong duoc sinh tieng on console");
    unmount();
  });

  it("loi API phai HIEN RA cho nguoi doc (khong im lang, khong chi vao console)", async () => {
    // Nhanh loi cua `useApi` + `ChannelZone`: neu khong bai nao ghim thi mot thay doi
    // lam loi bi nuot se di qua XANH — dung loai "xanh gia".
    dem.loiSources = true;
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "không đọc được kênh");
    // `ApiError.message` = "<status>: <detail>", nen ca ma HTTP lan cau tieng Viet cua
    // backend deu phai co mat trong DOM.
    await choChu(container, "500");
    await choChu(container, "nguồn dữ liệu hỏng (cố ý)");

    assert.deepEqual(tiengOn, [], "mot loi HTTP phai di ra DOM, khong duoc chi ghi console");
    unmount();
  });

  it("S2: hai nhan 'đã tách tiếng' / 'chưa tách tiếng' phai GAN DUNG kenh (ca hai chieu)", async () => {
    // Lo hong do review vong #1 DO DUOC: dao hai nhan nay trong `ChannelZone` thi
    // `npm test` van `pass 48 / fail 2` — CA NAM MUOI bai xanh. Ly do: bai cu chi hoi
    // "hai chuoi nay co xuat hien dau do trong DOM khong", ma sau khi dao thi CA HAI
    // van xuat hien, chi la gan SAI KENH. Day la chu NGUOI DUNG DOC, noi nguoc su that.
    const { container, unmount } = render(taoPhanTu(App));

    const kenh1 = await choPhanTu(
      container, ".ch__item", (t) => t.includes("kenh-mot.wav"), "khong thay kenh 1 trong DOM",
    );
    const kenh2 = await choPhanTu(
      container, ".ch__item", (t) => t.includes("vid.example/kenh-hai"), "khong thay kenh 2 trong DOM",
    );

    // `audio_path` cua kenh 1 la mot duong dan THAT ⇒ "đã tách tiếng"; cua kenh 2 la
    // `null` ⇒ "chưa tách tiếng". Khang dinh CA HAI CHIEU tren TUNG kenh.
    assert.ok(kenh1.includes("đã tách tiếng"), `kenh 1 phai "đã tách tiếng"; do duoc ${JSON.stringify(kenh1)}`);
    assert.ok(!kenh1.includes("chưa tách tiếng"), `kenh 1 KHONG duoc hien "chưa tách tiếng"; do duoc ${JSON.stringify(kenh1)}`);
    assert.ok(kenh2.includes("chưa tách tiếng"), `kenh 2 phai "chưa tách tiếng"; do duoc ${JSON.stringify(kenh2)}`);
    assert.ok(!kenh2.includes("đã tách tiếng"), `kenh 2 KHONG duoc hien "đã tách tiếng"; do duoc ${JSON.stringify(kenh2)}`);

    assert.deepEqual(tiengOn, [], "hien trang thai kenh khong duoc sinh tieng on console");
    unmount();
  });

  it("I1: trang thai TUNG BUOC cua kenh suy tu payload.source_id cua job (job moi nhat thang)", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    const kenh1 = await choPhanTu(
      container, ".ch__item", (t) => t.includes("kenh-mot.wav"), "khong thay kenh 1 trong DOM",
    );
    const kenh2 = await choPhanTu(
      container, ".ch__item", (t) => t.includes("vid.example/kenh-hai"), "khong thay kenh 2 trong DOM",
    );

    // KENH 1: `ingest` #5 xong; `asr` co HAI job — #3 (done) va #7 (running).
    // QUY UOC dang ghim: job co id LON NHAT cua moi buoc la trang thai HIEN TAI, nen
    // ket qua phai la "đang chạy" chu KHONG phai "xong" (job #3 la LICH SU).
    assert.ok(kenh1.includes("nạp: xong"), `kenh 1 phai "nạp: xong"; do duoc ${JSON.stringify(kenh1)}`);
    assert.ok(kenh1.includes("phiên âm: đang chạy"), `kenh 1 phai "phiên âm: đang chạy"; do duoc ${JSON.stringify(kenh1)}`);
    assert.ok(!kenh1.includes("phiên âm: xong"), `job asr #3 la lich su, khong duoc hien; do duoc ${JSON.stringify(kenh1)}`);

    // KENH 2: `ingest` #6 dang cho, va CHUA co job phien am nao.
    assert.ok(kenh2.includes("nạp: đang chờ"), `kenh 2 phai "nạp: đang chờ"; do duoc ${JSON.stringify(kenh2)}`);
    assert.ok(kenh2.includes("phiên âm: chưa có job"), `kenh 2 phai "phiên âm: chưa có job"; do duoc ${JSON.stringify(kenh2)}`);

    assert.deepEqual(tiengOn, [], "hien trang thai buoc khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // W1 — HAI DUONG NOI (che do + kenh), DI QUA DUONG THAT
  //
  // Truoc W1 do duoc: `setMode` **0 luot dispatch** va `selectChannel` **0 luot
  // dispatch** ⇒ khong roi duoc man Bien tap, va moi man chi hien trang thai rong.
  // Bon bai duoi day bam/nhin tren DOM THAT, voi du lieu tu server `node:http` THAT
  // trong tien trinh — khong mock `client.ts`/`endpoints.ts`, khong `fetch` gia.
  // -------------------------------------------------------------------------

  it("CHON KENH: bam mot kenh ⇒ EditScreen nhan BAN GHI THAT, Transport co `src` + thoi luong backend", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    // Chua bam: KHONG duoc goi endpoint nao theo `null` (xem bai `CHUA CHON KENH`).
    await choChu(container, "kenh-mot.wav");
    assert.equal(dem.soYeuCauIdKhongHopLe, 0, "chua chon kenh ⇒ khong request nao duoc mang id null/0");

    fireEvent.click(nutKenh(container, "kenh-mot.wav"));

    // EDITSCREEN: ban ghi THAT cua kenh 1 — va la ban MOI NHAT (id 5), khong phai ban cu
    // (id 2, dung TRUOC trong mang ma server tra).
    await choChu(container, "câu 1");
    await choChu(container, "câu 3");
    const chuTrongMan = textCua(container, ".ed__chu").join(" | ");
    assert.ok(
      !chuTrongMan.includes("bản cũ kênh một"),
      `phai mo ban ghi MOI NHAT cua kenh; do duoc ${JSON.stringify(chuTrongMan)}`,
    );
    assert.ok(
      !chuTrongMan.includes("bản kênh hai"),
      `KHONG duoc lan du lieu cua kenh khac; do duoc ${JSON.stringify(chuTrongMan)}`,
    );

    // ⚠️ CHO THU 16 CUA LOP "CHO A ROI DOC B" (ERRATA #38 muc 2). Hai `choChu` o tren cho
    // CHU cua `transcript` (doan van cua `EditScreen`), nhung ba khang dinh duoi day doc
    // `href` cua `translations` — HAI `useApi` DOC LAP trong `App` (`transcript` va
    // `translations`), va `translations` con la mot CHUOI hai request
    // (`listTranslations` -> `getTranslation` cho tung hang). DO DUOC (probe cua vong nay):
    // tiem 300 ms vao `/api/translations` — nguon bai KHONG cho — ⇒ bai DO ngay voi `href`
    // con `null`; cham `transcript` thi khong lam bai do.
    // ⇒ Cho DUNG tin hieu bai sap DOC: ba nut xuat CO `href`. Khong phai mot dong ho, va
    // khong phai mot bo dem tich luy o phia server (bai hoc `F1` cua re-review W3 #2).
    // Khang dinh ben duoi KHONG doi mot chu.
    await choPhuHop(
      container,
      ".tp__xuat",
      (el) => el.getAttribute("href") !== null,
      "ba nut xuat chua co `href` (ban dich `done` cua ban ghi chua nap xong)",
    );

    // TRANSPORT: `src` tu kenh dang chon; tong thoi luong lay tu `Source.duration` (754.2 s
    // ⇒ `12:34.20`), KHONG do lai tu phan tu media. `translationId` la ban dich `done` moi
    // nhat (id 11) ⇒ ba nut xuat CO `href`.
    assert.equal(phanTu(container, "audio").getAttribute("src"), "/api/media/1");
    assert.equal(chu(container, ".tp__timecode"), "0:00.00 / 12:34.20");
    assert.equal(
      phanTu(container, ".tp__xuat").getAttribute("href"),
      "/api/export/11?format=srt&bilingual=0",
      "nut xuat phai tro vao ban dich `done` moi nhat cua ban ghi dang mo",
    );
    // Va trong CA luot nay, khong request nao duoc phep mang id null/0.
    assert.equal(dem.soYeuCauIdKhongHopLe, 0, "khong request nao duoc mang id null/0");

    assert.deepEqual(tiengOn, [], "chon kenh khong duoc sinh tieng on console");
    unmount();
  });

  it("XOÁ KÊNH: hai bước ⇒ DELETE + ĐỌC LẠI danh sách; kênh ĐANG CHỌN bị xoá ⇒ BỎ CHỌN", async () => {
    // ⚠️ BẤT BIẾN ĐƯỢC GHIM Ở ĐÂY: xoá kênh đang mở KHÔNG được để app trỏ vào một id đã chết.
    // `App.xoaKenh` làm điều đó bằng `clearChannel` (cùng bộ vị trí mà `selectChannel` dọn khi
    // ĐỔI kênh), và phép đo dưới đây đọc DOM THẬT: không còn `.ch__item[aria-pressed="true"]`,
    // và màn Biên tập rơi về trạng thái rỗng "chưa có bản ghi".
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    // CHỌN kênh 1 bằng nút CHỌN (không phải nút xoá) để có một lựa chọn thật cần được dọn.
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    assert.ok((kenhDangChon(container) ?? "").includes("kenh-mot.wav"), "kênh 1 phải đang được chọn");

    const nut = phanTu(container, '[data-testid="xoa-kenh-1"]');
    // CÚ BẤM THỨ NHẤT: chỉ mở bước xác nhận. Bộ đếm ở PHÍA MÁY CHỦ phải bằng 0 — đó là bằng
    // chứng duy nhất phân biệt "nút đổi chữ" với "request đã đi".
    fireEvent.click(nut);
    assert.equal((nut.textContent ?? "").trim(), "xóa?", "cú bấm đầu phải hỏi lại bằng CHỮ");
    assert.equal(dem.xoaSource, 0, "cú bấm ĐẦU không được gọi API (đếm ở phía server)");

    // CÚ BẤM THỨ HAI: ĐÚNG MỘT `DELETE /api/sources/1`, rồi `sources.reload()`.
    fireEvent.click(nut);
    await waitFor(
      () => {
        assert.equal(dem.xoaSource, 1, `phải có ĐÚNG MỘT DELETE; đo được ${dem.xoaSource}`);
        assert.equal(dem.xoaTheoId[1], 1, "đúng id kênh đã bấm");
      },
      { timeout: 5000, interval: 20 },
    );
    // Hàng biến mất KHÔNG phải vì client tự cắt state: máy chủ giả chỉ quên nó khi ĐÃ nhận
    // request, và hàng chỉ đi khỏi DOM sau lần `GET /api/sources` kế tiếp.
    await waitFor(
      () => {
        assert.equal(
          container.querySelectorAll('[data-testid="xoa-kenh-1"]').length,
          0,
          "kênh đã xoá phải biến mất sau lần ĐỌC LẠI danh sách",
        );
      },
      { timeout: 5000, interval: 20 },
    );
    assert.ok(
      dem.sources >= 2,
      `phải có một lần đọc lại /api/sources sau khi xoá; đo được ${dem.sources}`,
    );
    assert.equal(kenhDangChon(container), null, "kênh đang chọn bị xoá ⇒ app KHÔNG được trỏ vào id chết");
    await choChu(container, "chưa có bản ghi để biên tập");

    assert.deepEqual(tiengOn, [], "luồng xoá kênh không được sinh tiếng ồn console");
    unmount();
  });

  it("XOÁ KÊNH 409: job đang xếp hàng ⇒ hiện NGUYÊN VĂN câu backend, kênh CÒN, lựa chọn KHÔNG đổi", async () => {
    // ⚠️ Vì sao câu này phải hiện NGUYÊN VĂN: 409 của backend nêu ĐÍCH DANH id job
    // (`delete_guard.mot_loi_409`), và đó là thứ duy nhất nói người dùng phải huỷ cái gì.
    // Thay bằng "có lỗi xảy ra" là bỏ mất đúng thông tin cần để sửa.
    dem.xoaLoi = true;
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    const nut = phanTu(container, '[data-testid="xoa-kenh-2"]');
    fireEvent.click(nut);
    fireEvent.click(nut);

    await choPhanTu(
      container,
      '[data-testid="xoa-kenh-2-loi"]',
      (t) => t.includes("đang xếp hàng"),
      "câu 409 của backend chưa hiện trong ô lỗi của nút xoá",
    );
    assert.equal(dem.xoaSource, 1, "request PHẢI đã đi ra — lỗi đến từ máy chủ, không phải từ client");
    assert.ok(
      (container.querySelector('[data-testid="xoa-kenh-2-loi"]')?.textContent ?? "").includes("#7"),
      "câu lỗi phải nêu ĐÍCH DANH id job đang chặn",
    );
    // Kênh CÒN: 409 nói "chưa xoá được", nên hàng phải nguyên chỗ (và mọi kênh khác cũng vậy).
    assert.ok(container.querySelector('[data-testid="xoa-kenh-2"]') !== null, "kênh phải còn sau 409");
    assert.equal(dem.xoaDaXoa.length, 0, "máy chủ KHÔNG được xoá hàng nào");
    assert.equal(kenhDangChon(container), null, "lượt xoá hỏng không được đổi kênh đang chọn");

    assert.deepEqual(tiengOn, [], "luồng xoá lỗi không được sinh tiếng ồn console");
    unmount();
  });

  it("CHE DO (M9): bam radio 'Thuật ngữ' ⇒ GlossaryScreen HIEN — nhanh `glossary` lan dau TOI DUOC", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    // ⚠️ Tim bang VAI TRO + TEN DOC DUOC — dung cach Task 12 lam
    // (`findByRole("radio", {name:/thuật ngữ/i})`), va la thu TRUOC W1 khong ton tai.
    await choChu(container, "kenh-mot.wav");
    assert.equal(
      container.querySelectorAll(".gl").length,
      0,
      "chua bam gi thi KHONG duoc co man THUAT NGU nao",
    );
    const radio = getByRole(container, "radio", { name: /thuật ngữ/i });

    fireEvent.click(radio);

    // Man THUAT NGU THAT SU nap xong tu server: bang rong THAT va dong dem cua no.
    await choChu(container, "Chưa có thuật ngữ nào");
    await choPhanTu(
      container,
      '[data-testid="dem"]',
      (t) => t.includes("0 thuật ngữ") && t.includes("0 đã duyệt"),
      "GlossaryScreen khong nap duoc bang thuật ngữ",
    );
    assert.equal(container.querySelectorAll(".ed").length, 0, "doi che do phai ROI man Bien tap");

    assert.deepEqual(tiengOn, [], "doi che do khong duoc sinh tieng on console");
    unmount();
  });

  it("CHE DO: 'Đối chiếu' sau khi chon kenh ⇒ thay COT CPS dang SO tu `TranslationDetail.cps`", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    // ⚠️ CHO THEO TIN HIEU DOM, khong khang dinh ngay va KHONG doi mot bo dem tich luy o phia
    // server: `transcript` va `translations` la HAI `useApi` doc lap, nen "câu 1" co the hien
    // TRUOC khi hai request `getTranslation` ket thuc (mot phep khang dinh ngay la mot phep do
    // PHU THUOC THOI DIEM — do duoc trong luot mutation `W1-5`). Bo dem `dem.translationChiTiet`
    // TUNG duoc dung lam phep cho o day, nhung no la so TICH LUY cua ca tien trinh: mot request
    // con dang bay cua bai TRUOC ha canh sau `beforeEach` cung lam no tang (xem
    // `choDanhSachBanDich`). Nay cho DUNG hai hang `pick-` ma bai sap doc.

    fireEvent.click(getByRole(container, "radio", { name: /đối chiếu/i }));
    await choDanhSachBanDich(container, 2);

    // Bộ chọn bản dịch: hai hàng của bản ghi ⇒ hai nút chọn.
    await choPhanTu(
      container,
      '[data-testid="pick-11"]',
      (t) => t.includes("bản dịch"),
      "man Doi chieu khong nhan duoc danh sach ban dich THAT",
    );

    // ⚠️ Vong sua W1 #1: bai nay TUNG phai bam `pick-11` de do duoc CPS, vi man Doi chieu
    // mac dinh roi vao `translations[0]` = ban 12 `queued` (route that tra MOI NHAT TRUOC)
    // ⇒ cot phai rong. Nay `App` truyen `macDinhId` (ban `done` moi nhat) xuong, nen mac
    // dinh CHINH LA ban 11 va khong con buoc "di vong qua loi" nao. Bai
    // "MOT ban dich duy nhat: ba nut XUAT va vung DOI CHIEU tro CUNG mot ban" ghim dung bat bien do.
    fireEvent.click(phanTu(container, '[data-testid="pick-11"]'));

    // Nguong CPS lay tu `TranslationDetail.cps.max_cps` + so doan DA DO cua CHI TIET (3) —
    // mot CON SO cua backend, khong phai chuoi tu parse.
    await choChu(container, "ngưỡng 21 CPS · nguồn: 3 đoạn đã đo");
    // Cột phải: chữ THAT của bản dịch (không phải chữ của bản gốc).
    const cotPhai = textCua(container, '[data-testid="col-right"]');
    assert.ok(
      cotPhai.some((t) => t.includes("câu một (dịch)")),
      `cot phai phai la BAN DICH; do duoc ${JSON.stringify(cotPhai)}`,
    );
    // Cot CPS: so da dinh dang tu `cps` (khong phai chuoi tu parse), va dong vuot nguong
    // van duoc danh dau bang `data-over-cps` cua backend.
    const cotCps = textCua(container, '[data-testid="col-cps"]');
    assert.equal(cotCps.length, 3, `phai co CPS cho ca ba doan; do duoc ${JSON.stringify(cotCps)}`);
    assert.ok(cotCps[0].includes("4.2"), `doan 0 phai la 4.2 CPS; do duoc ${JSON.stringify(cotCps[0])}`);
    assert.ok(cotCps[2].includes("30.5"), `doan 2 phai la 30.5 CPS; do duoc ${JSON.stringify(cotCps[2])}`);
    assert.equal(
      phanTu(container, '[data-testid="row-2"]').getAttribute("data-over-cps"),
      "true",
      "co vuot nguong do BACKEND tinh phai duoc mang xuong DOM",
    );

    assert.deepEqual(tiengOn, [], "doi sang Doi chieu khong duoc sinh tieng on console");
    unmount();
  });

  it("CHE DO: radio 'Biên tập' dua duong QUAY VE man Bien tap (ca ba radio deu di het mot vong)", async () => {
    // `Minor #2` cua review W1: hai radio dau co bai dau-cuoi (`Thuật ngữ`, `Đối chiếu`),
    // con duong QUAY VE `mode === "edit"` chua bao gio duoc di tren shell THAT — no chi duoc
    // phu theo THANH PHAN (`Header.test.tsx` bam `radiosVong[0]` + `reducer.test.ts`), tuc la
    // ghep suy luan chu khong phai mot luot chay. Bai nay di het mot vong tren DOM that.
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    assert.ok(container.querySelectorAll(".ed").length > 0, "mac dinh phai la man BIEN TAP");

    // ROI khoi Bien tap sang Thuat ngu...
    fireEvent.click(getByRole(container, "radio", { name: /thuật ngữ/i }));
    await choChu(container, "Chưa có thuật ngữ nào");
    assert.equal(container.querySelectorAll(".ed").length, 0, "doi che do phai ROI man Bien tap");

    // ...roi QUAY VE bang chinh radio thu ba. Man Bien tap phai NAP LAI (khong chi doi nhan).
    fireEvent.click(getByRole(container, "radio", { name: /biên tập/i }));
    await choChu(container, "câu 1");
    assert.ok(
      container.querySelectorAll(".ed").length > 0,
      "bam radio 'Biên tập' phai dua man Bien tap TRO LAI DOM",
    );
    assert.equal(
      container.querySelectorAll(".gl").length,
      0,
      "quay ve Bien tap thi man Thuat ngu phai BIEN MAT",
    );

    assert.deepEqual(tiengOn, [], "di het mot vong ba che do khong duoc sinh tieng on console");
    unmount();
  });

  it("CHUA CHON KENH: KHONG goi endpoint theo `null` (do bang so request o SERVER)", async () => {
    // Bo dem la TOAN CUC (moi bai deu mount mot `<App/>`), nen "MOT luot doc danh sach" duoc
    // do bang HIEU so truoc/sau cua CHINH bai nay.
    const truoc = dem.transcripts;
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    // Man Bien tap noi SU THAT cua no (chua co ban ghi nao de mo).
    await choChu(container, "chưa có bản ghi để biên tập");
    await waitFor(
      () => {
        assert.ok(dem.transcripts - truoc >= 1, "chua doc `/api/transcripts`");
      },
      { timeout: 5000, interval: 20 },
    );

    // MOT luot doc danh sach cho ca app: khong man nao tu hoi lai cau hoi do.
    assert.equal(dem.transcripts - truoc, 1, "danh sach transcript doc DUNG MOT lan cho ca app");
    // ...va KHONG request nao sinh ra tu mot `channelId === null`. Do o PHIA SERVER, tren
    // chinh id cua request — nen no khong phu thuoc viec request cua bai khac con dang bay.
    assert.equal(dem.soYeuCauIdKhongHopLe, 0, "`channelId === null` ⇒ khong request nao mang id null/0");

    assert.deepEqual(tiengOn, [], "trang thai chua chon kenh khong duoc sinh tieng on console");
    unmount();
  });

  it("DOI KENH: danh sach `/api/transcripts` KHONG duoc doc lai (do bang so request o SERVER)", async () => {
    // ---------------------------------------------------------------------------
    // `Minor #2` cua re-review W1: bao cao KHAI (va reviewer do duoc) *"doi kenh chi GHI
    // LAI MOC ⇒ khong sinh 2 request"*, nhung KHONG bai nao GHIM tinh chat do.
    // Do duoc: `PROBE-KENH danh-sach truoc=1 sau=1 delta=0`.
    //
    // Vi sao mot loi khai khong co bai ghim la mot khe DO PHU THAT: `transcripts` la
    // `useApi(..., [])` — mot lan cho CA app — va ban ghi dang mo duoc suy ra qua `deps`
    // `[ui.channelId]` cua `chonTranscript`. Nen neu sau nay ai them
    // `transcripts.reload()` vao nhanh doi kenh thi HAI request cho MOT lan bam, ma
    // KHONG bai nao do: bai `CHUA CHON KENH` khong bao gio bam kenh, con bai `CHON KENH`
    // chi khang dinh du lieu dung (mot lan doc lai THUA van cho ra dung du lieu).
    //
    // ⚠️ Bo dem o PHIA SERVER (`dem.transcripts`, tang trong `createServer`), khong phai
    // mot bo dem o client: mot `fetch` bi boc o client co the dem sai thu, con day la so
    // lan request THUC SU toi noi nhan.
    // ---------------------------------------------------------------------------
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    // Moc do SAU khi kenh 1 da mo xong: lan doc danh sach luc mount da xay ra TRUOC moc nay,
    // nen hieu so duoi day chi con do duoc nhung lan doc do viec DOI KENH keo theo.
    const truoc = dem.transcripts;

    fireEvent.click(nutKenh(container, "kenh-hai"));

    // Cho TIN HIEU doi kenh THANH SU xay ra (khong phai mot `setTimeout` hy vong): muc kenh
    // thu hai mang `aria-pressed="true"` VA ban ghi cua chinh kenh do da vao DOM.
    await waitFor(
      () => {
        assert.equal(
          phanTu(container, '.ch__item[aria-pressed="true"]').textContent?.includes("kenh-hai"),
          true,
          "chua thay muc kenh thu hai duoc chon (`aria-pressed=\"true\"`)",
        );
      },
      { timeout: 5000, interval: 20 },
    );
    await choChu(container, "bản kênh hai");

    // (1) TINH CHAT DUOC GHIM: doi kenh ⇒ **0** request danh sach `/api/transcripts`.
    assert.equal(
      dem.transcripts - truoc,
      0,
      "doi kenh KHONG duoc doc lai danh sach transcript: ban ghi dang mo suy ra tu `deps` "
      + `[ui.channelId], mot lan doc lai nua la HAI request cho MOT lan bam; do duoc +${dem.transcripts - truoc}`,
    );
    // (2) VE NGUOC LAI — neu bang chung duy nhat la "delta = 0" thi mot bai KHONG BAO GIO
    //     doc duoc gi cung xanh. Doi kenh PHAI keo theo DUNG MOT lan doc BAN GHI chi tiet
    //     (route khac: `/api/transcripts/{id}`), nen phep do (1) khong the xanh vi ca hai
    //     request deu khong xay ra.
    assert.equal(
      dem.transcriptTheoId[3],
      1,
      `ban ghi cua kenh hai (#3) phai duoc doc dung MOT lan; do duoc ${JSON.stringify(dem.transcriptTheoId)}`,
    );

    assert.deepEqual(tiengOn, [], "doi kenh khong duoc sinh tieng on console");
    unmount();
  });

  it("MOT ban dich duy nhat: ba nut XUAT va vung DOI CHIEU tro CUNG mot ban (mac dinh = ban `done`)", async () => {
    // ---------------------------------------------------------------------------
    // `Important #1` cua review W1 (§B(8)) — phep do `SAME`.
    //
    // FIXTURE nay dung hinh dang ma route THAT tra ve: `TRANSLATIONS` co id 12 `queued`
    // DUNG TRUOC id 11 `done` (moi nhat truoc). Truoc vong sua: `App` xuat ban 11 con
    // `<CompareScreen>` mac dinh `translations[0]` = ban 12 `queued` (rong) ⇒ cot phai
    // `["","",""]`, CPS `["—CPS","—CPS","—CPS"]`, dong nguong "nguon: 0 doan da do",
    // va `SAME = false` — nguoi dung doc mot ban trong khi xuat mot ban khac, khong cau
    // nao noi vi sao.
    // ---------------------------------------------------------------------------
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    // ⚠️ Cho DUNG dau ra DOM ma bai sap doc: ba nut XUAT co `href` (chi co khi danh sach ban
    // dich da ve va co mot ban `done`).
    //
    // ⚠️ THAY CHO `waitFor(() => assert.equal(dem.translationChiTiet, 2))` (vong sua W3 #2): do la
    // mot bo dem TICH LUY o PHIA SERVER, khong phai dai luong cua bai nay — mot request con dang
    // bay cua bai TRUOC ha canh sau `beforeEach` cung lam no tang (do duoc: `3 !== 2` / `4 !== 2`;
    // xem `choDanhSachBanDich` va bao cao vong sua #2). Phep do "hai ban dich da duoc doc" khong
    // mat: no nam o `choDanhSachBanDich(container, 2)` ngay duoi, tren DOM THAT.
    await waitFor(
      () => {
        assert.ok(
          phanTu(container, ".tp__xuat").getAttribute("href") !== null,
          "nut xuat chua co `href` ⇒ danh sach ban dich chua ve",
        );
      },
      { timeout: 5000, interval: 20 },
    );

    // VUNG XUAT (thanh transport, luon co mat): href = ban `done` moi nhat (id 11).
    const href = phanTu(container, ".tp__xuat").getAttribute("href");
    assert.ok(href !== null, "nut xuat phai co `href` khi da co ban dich `done`");
    const xuatId = Number(/^\/api\/export\/(\d+)\?/.exec(href ?? "")?.[1]);
    assert.equal(xuatId, 11, `ba nut xuat phai tro vao ban \`done\` moi nhat; do duoc ${JSON.stringify(href)}`);

    fireEvent.click(getByRole(container, "radio", { name: /đối chiếu/i }));
    await choDanhSachBanDich(container, 2);
    await choPhanTu(
      container,
      '[data-testid="pick-11"]',
      (t) => t.includes("bản dịch"),
      "man Doi chieu khong nhan duoc danh sach ban dich THAT",
    );

    // VUNG DOI CHIEU: khang dinh tren HANG `aria-checked="true"` — trang thai MAY doc duoc,
    // khong phai mot lop trang tri. `pick-12` (`queued`) KHONG duoc la hang dang chon.
    const dangChon = [...container.querySelectorAll('[data-testid^="pick-"]')].filter(
      (el) => el.getAttribute("aria-checked") === "true",
    );
    assert.equal(dangChon.length, 1, `phai co DUNG MOT ban dich dang chon; do duoc ${dangChon.length}`);
    const chonId = Number((dangChon[0].getAttribute("data-testid") ?? "").replace("pick-", ""));
    assert.equal(
      phanTu(container, '[data-testid="pick-12"]').getAttribute("aria-checked"),
      "false",
      "ban `queued` moi nhat KHONG duoc la ban dang xem",
    );
    assert.equal(chonId, xuatId, `SAME = ${chonId === xuatId}: vung Doi chieu dang xem ${chonId}, con ba nut xuat tro vao ${xuatId}`);

    // Cot phai = CHU THAT cua chinh ban dich do (khong con rong vi mac dinh roi vao ban `queued`).
    const cotPhai = textCua(container, '[data-testid="col-right"]');
    assert.ok(
      cotPhai.some((t) => t.includes("câu một (dịch)")),
      `cot phai phai la NOI DUNG cua ban dang xem; do duoc ${JSON.stringify(cotPhai)}`,
    );
    // Dong nguong doc tu CHI TIET cua cung ban dich do: "3 doan da do" chu khong phai 0.
    await choChu(container, "ngưỡng 21 CPS · nguồn: 3 đoạn đã đo");

    assert.deepEqual(tiengOn, [], "mac dinh ban dich khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // NGOI NO DOC LAI `Minor #3` — LỖI CHỨC NĂNG: danh sach transcript doc MOT lan
  // -------------------------------------------------------------------------
  // Do duoc truoc vong sua: `useApi(..., [])` + `transcripts.reload` khong noi vao dau
  // ⇒ job `ingest`/`asr` xong thi BAN GHI MOI khong bao gio hien ra. Bai duoi day do CA
  // HAI VE ma ERRATA #11 muc 2 doi: (i) ban ghi moi HIEN RA, (ii) KHONG BAO REQUEST.

  it("job `asr` cua kenh dang chon chuyen `done` ⇒ BAN GHI MOI hien ra (khong phai tai lai trang)", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    // Moc do SAU khi da chon kenh (xem bai "khong bao request" ngay duoi ve ly do).
    const truoc = dem.transcripts;

    // Stream THAT SU mo truoc khi ghi su kien.
    await waitFor(
      () => {
        assert.ok(streams.size >= 1, "hook chua mo /api/jobs/stream");
      },
      { timeout: 5000, interval: 20 },
    );

    // ⚠️ BAN GHI MOI CHI XUAT HIEN O SERVER SAU KHI JOB XONG. Do la thu lam phep do co nghia:
    // anh chup luc mount KHONG co no, nen no chi co the tới DOM qua mot lan DOC LAI.
    // (Them no truoc khi render thi lan doc dau tien da thay, va bai test se XANH ngay ca khi
    // khong co ngoi no nao — mot phep do RONG.)
    emit(sse({ id: 7, state: "done", progress: 1, phase: "asr:faster-whisper-large", error: null, log_tail: "" }));
    themBanGhiMoi(9, 1, "câu một của bản mới");

    // (i) BAN GHI MOI HIEN RA — chi co the den tu mot lan doc lai `/api/transcripts`.
    await waitFor(
      () => {
        assert.ok(
          dem.transcriptTheoId[9] === 1,
          `ban ghi moi (#9) phai duoc doc dung MOT lan; do duoc ${JSON.stringify(dem.transcriptTheoId)}`,
        );
      },
      { timeout: 5000, interval: 20 },
    );
    await choChu(container, "câu một của bản mới");
    assert.ok(
      dem.transcripts - truoc >= 1,
      `job xong phai keo mot lan doc lai /api/transcripts; do duoc ${dem.transcripts - truoc}`,
    );

    assert.deepEqual(tiengOn, [], "doc lai danh sach khong duoc sinh tieng on console");
    unmount();
  });

  it("ngoi no doc lai KHONG thanh BAO REQUEST: chi CHUYEN TRANG THAI moi keo mot request", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    await waitFor(
      () => {
        assert.ok(streams.size >= 1, "hook chua mo /api/jobs/stream");
      },
      { timeout: 5000, interval: 20 },
    );
    // Moc do SAU khi mount + sau khi chon kenh: phep do la HIEU so, nen no khong phu thuoc
    // viec request cua mot bai khac con dang bay (cung ly do da ghi o bo dem `soYeuCauIdKhongHopLe`).
    let truoc = dem.transcripts;

    // (A) su kien TIEN DO cua mot job DANG CHAY (`running`, khong doi trang thai) ⇒ KHONG doc lai.
    emit(sse({ id: 7, state: "running", progress: 0.4, phase: "asr:faster-whisper-large", error: null, log_tail: "" }));
    await choPhanTu(
      container,
      ".q__item",
      (t) => t.includes("#7 ") && t.includes("đang chạy") && t.includes("40%"),
      "su kien tien do khong tới DOM (nen phep do se RONG)",
    );
    await choNhip(250);
    assert.equal(
      dem.transcripts - truoc,
      0,
      `mot su kien TIEN DO khong duoc keo request doc lai; do duoc ${dem.transcripts - truoc}`,
    );

    // (B) su kien lap lai DUNG trang thai cu (job #3 da `done`) ⇒ cung KHONG doc lai.
    truoc = dem.transcripts;
    emit(sse({ id: 3, state: "done", progress: 1, phase: "asr:faster-whisper-large", error: null, log_tail: "" }));
    await choNhip(250);
    assert.equal(
      dem.transcripts - truoc,
      0,
      `mot su kien KHONG doi trang thai khong duoc keo request doc lai; do duoc ${dem.transcripts - truoc}`,
    );

    // (C) CHUYEN TRANG THAI THAT (`running` ⇒ `done`) ⇒ DUNG MOT request doc lai.
    truoc = dem.transcripts;
    emit(sse({ id: 7, state: "done", progress: 1, phase: "asr:faster-whisper-large", error: null, log_tail: "" }));
    await waitFor(
      () => {
        assert.ok(
          dem.transcripts - truoc >= 1,
          "chuyen trang thai sang `done` PHAI keo mot lan doc lai /api/transcripts",
        );
      },
      { timeout: 5000, interval: 20 },
    );
    await choNhip(250);
    assert.equal(
      dem.transcripts - truoc,
      1,
      `mot lan chuyen trang thai = DUNG MOT request (khong phai mot request moi nhip SSE); do duoc ${dem.transcripts - truoc}`,
    );

    assert.deepEqual(tiengOn, [], "ngoi no doc lai khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // HINH THUC — ghim LUAT CSS cua LUOI `.shell` (ERRATA #31 muc 1 + muc 4)
  //
  // Vi sao DOC TEP CSS chu khong hoi DOM: jsdom KHONG co layout, KHONG tinh CSS
  // (`getComputedStyle` khong cho biet `.shell__mid` nam o hang nao) ⇒ phep do DUY NHAT
  // con lai la doc chinh van ban CSS. Day la chung minh TINH, khong phai mot anh chup.
  //
  // ⚠️ TUYET DOI KHONG ghim `grid-template-rows` (bon gia tri track): ghim nhu vay la
  // DONG BANG chinh loi `Critical #1` — loi la KHONG CO VI TRI, khong phai con so cua track.
  // Phai ghim VI TRI (`grid-row`) cua TUNG con.
  // -------------------------------------------------------------------------

  it("HINH THUC (X7): luoi .shell khai VI TRI cho ca BON con VA KHOP CAP hang↔con (.od↔auto, .shell__mid↔1fr)", () => {
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");

    assert.match(appCss, /\.shell \{[^}]*display: grid/,
      "`.shell` phai la mot luoi CSS (co `display: grid`)");

    // (i) Bon con cua `.shell` theo THU TU DOM trong `App.tsx`: header, panel (co the vang),
    // ban lam viec, transport. Moi con phai khai VI TRI TUONG MINH: bo `grid-row` di thi
    // auto-placement dat theo thu tu DOM ⇒ khi panel vang, `.shell__mid` roi vao track `auto`
    // va transport roi vao `1fr`, con track `--transport-h` bo trong.
    assert.match(appCss, /\.shell__head \{[^}]*grid-row: 1\b/,
      "`.shell__head` phai khai `grid-row: 1` (hang header, `--head-h`)");
    assert.match(appCss, /\.od \{[^}]*grid-row: 2\b/,
      "`.od` (panel §4.8) phai khai `grid-row: 2` — do la track `auto` co lai khi panel vang");
    assert.match(appCss, /\.shell__mid \{[^}]*grid-row: 3\b/,
      "`.shell__mid` phai khai `grid-row: 3` — neu khong no bi auto-placement day len hang `auto`");
    assert.match(appCss, /\.shell__transport \{[^}]*grid-row: 4\b/,
      "`.shell__transport` phai khai `grid-row: 4` (`--transport-h`), khong duoc roi vao `1fr`");

    // (ii) KHOP CAP hang ↔ con: hang ma `.od` tro toi phai la `auto`, hang ma `.shell__mid`
    // tro toi phai la `1fr`.
    //
    // ⚠️ VI SAO PHAI CO VE NAY (do duoc o re-review Task 10, ERRATA #34 muc 1): ve (i) chi
    // khang dinh `grid-row` TON TAI, nen mutation `X7` (dua `.shell` ve BA track) **LOT**
    // — vi tri van dung nhung track ma no tro toi da doi. Ve (ii) ghim QUAN HE, va quan he
    // nay ghim BANG CHINH luat `.shell`:
    //   - KHONG ghim nguyen van bon track ⇒ ghim nguyen van la DONG BANG so luong track,
    //     dung thu review goc cam;
    //   - va pre-fix `e044d0b` (khong con nao khai `grid-row`) van DO o ve (i).
    const khoiShell = /\.shell \{[^}]*\}/.exec(appCss);
    assert.ok(khoiShell !== null, "khong doc duoc KHOI luat `.shell` trong app.css");
    const dongTrack = /grid-template-rows:\s*([^;]+);/.exec(khoiShell[0]);
    assert.ok(dongTrack !== null, "`.shell` phai khai `grid-template-rows`");
    const track = dongTrack[1].trim().split(/\s+/);

    function hangCua(chon: string): number {
      const khoi = new RegExp(`\\${chon} \\{[^}]*\\}`).exec(appCss);
      assert.ok(khoi !== null, `khong doc duoc khoi luat "${chon}"`);
      const hang = /grid-row:\s*(\d+)/.exec(khoi[0]);
      assert.ok(hang !== null, `"${chon}" phai khai mot \`grid-row\` dang so`);
      return Number(hang[1]);
    }

    const hangOd = hangCua(".od");
    const hangMid = hangCua(".shell__mid");
    assert.notEqual(hangOd, hangMid, "panel §4.8 va ban lam viec KHONG duoc dung CUNG mot hang");
    assert.equal(
      track[hangOd - 1],
      "auto",
      `hang ${hangOd} (cho \`.od\`) phai la track \`auto\`; do duoc ${JSON.stringify(track)}`,
    );
    assert.equal(
      track[hangMid - 1],
      "1fr",
      `hang ${hangMid} (cho \`.shell__mid\`) phai la track \`1fr\`; do duoc ${JSON.stringify(track)}`,
    );
    assert.ok(
      track.length >= Math.max(hangOd, hangMid),
      `luat \`.shell\` phai khai DU so hang ma cac con tro toi; do duoc ${JSON.stringify(track)}`,
    );
  });

  it("HINH THUC: .shell__head la HANG FLEX — thay doi bo cuc cua Task 10 duoc GHI RA va GHIM", () => {
    // Diff cua Task 10 them `display:flex; align-items:center; gap; padding-inline` vao
    // `.shell__head` (doi tu khoi sang hang flex) NHUNG khong khai trong danh sach lech, va
    // mutation `M2` (bo `display:flex`) ⇒ 0 bai do (ERRATA #31 muc 4). Bai nay ghim no.
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");

    assert.match(appCss, /\.shell__head \{[^}]*display: flex/,
      "`.shell__head` phai la HANG FLEX: dai trang thai nam CANH ten ban lam viec (khong xuong dong)");
    assert.match(appCss, /\.shell__head \{[^}]*align-items: center/,
      "hang flex phai can doc giua: ten ban lam viec va dai trang thai cung mot truc");
  });

  // -------------------------------------------------------------------------
  // TASK W3 — BAT DAU DICH, DI QUA DUONG THAT (server `node:http` trong tien trinh)
  //
  // Do duoc TRUOC W3: `endpoints.createTranslation` **0 luot goi trong san pham**,
  // `endpoints.listEngines` **0**, `<EngineSelect/>` **0 nguoi goi** ⇒ khong co cach nao BAT
  // DAU mot ban dich tu giao dien. Bon bai duoi day bam nut THAT va do o PHIA SERVER.
  // -------------------------------------------------------------------------

  it("W3 BAT DAU DICH: bam nut 'dich' ⇒ POST /api/translations voi body {transcript_id, engine}", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    // ⚠️ Kenh 1, ban ghi 5, ban dich 11 `done` + 12 `queued` ⇒ phai doc CHI TIET ca hai.
    await toiDoiChieu(container, 2);

    // (a) CUA VAO CO THAT: o chon engine + nut "dich".
    const nut = await choPhanTu(
      container,
      '[data-testid="tao-ban-dich"]',
      (t) => t.length > 0,
      "vung Doi chieu khong co cua vao 'bat dau dich'",
    );
    assert.ok(nut.length > 0, "nut 'dich' phai co chu");

    // O chon engine: CHI engine `kind === "mt"` VA `available === true` cua `/api/registry` THAT.
    // ⚠️ ASR nam trong registry (fixture dung hinh dang that) nen mot ban sua truyen
    // `[...asr, ...mt]` xuong se lam dong nay DO — va backend se tra 422.
    const loai = textCua(container, '[data-testid="tao-ban-dich"]')
      .concat([...container.querySelectorAll("option")].map((o) => o.textContent ?? ""));
    assert.ok(loai.some((t) => t.includes("OPUS-MT")), `o chon phai liet ke MT dung duoc; do duoc ${JSON.stringify(loai)}`);
    assert.ok(
      !loai.some((t) => t.includes("Faster Whisper")),
      `KHONG duoc liet ke ASR o o chon engine DICH (backend tra 422); do duoc ${JSON.stringify(loai)}`,
    );
    assert.ok(dem.registry >= 1, "phai doc `/api/registry` de biet engine nao dung duoc");

    // (b) BAM ⇒ POST THAT.
    fireEvent.click(phanTu(container, '[data-testid="tao-ban-dich"]'));
    // ⚠️ Cho DUNG thu sap doc: `dem.bodyTao` (server da doc XONG body). Phep cho cu la
    // `dem.postTranslations === 1` — bo dem do tang NGAY khi server NHAN request, con body duoc
    // ghi MUON HON (`req.on("end")`), nen do dung khuon "cho A roi doc B" ma B duoc ghi SAU A.
    await waitFor(
      () => {
        assert.ok(dem.bodyTao !== null, "server chua doc duoc body JSON nao");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.equal(dem.postTranslations, 1, "bam 'dich' phai gui DUNG MOT `POST /api/translations`");

    // (c) BODY THAT, doc o PHIA SERVER tu chinh request.
    const body = dem.bodyTao;
    assert.ok(body !== null, "server khong doc duoc body JSON nao");
    assert.equal(body["transcript_id"], 5, `body phai mang transcript_id cua ban ghi dang mo; do duoc ${JSON.stringify(body)}`);
    assert.equal(body["engine"], "opus-mt", `body phai mang engine DANG CHON; do duoc ${JSON.stringify(body)}`);
    // ⚠️ `target_lang` KHONG duoc gui: backend mac dinh `"vi"` (`CreateIn.target_lang: str = "vi"`),
    // gui cung la NGUON SU THAT THU HAI (brief §2).
    assert.equal(
      "target_lang" in body,
      false,
      `client KHONG duoc gui target_lang (backend tu mac dinh "vi"); do duoc ${JSON.stringify(body)}`,
    );
    assert.match(dem.contentTypeTao, /application\/json/,
      `POST phai gui content-type JSON; do duoc ${JSON.stringify(dem.contentTypeTao)}`);
    // NGUYEN VAN chuoi JSON ma client gui: hai khoa, khong khoa thua nao. Khang dinh tren
    // CHUOI (khong chi tren object da parse) vi no ghim luon thu tu khoa — thu ma mot ban sua
    // "sap xep lai body" se doi, va do la mot thay doi hop dong dang biet.
    assert.equal(
      dem.rawTao,
      `{"transcript_id":5,"engine":"opus-mt"}`,
      `body JSON THAT client gui phai la DUNG hai khoa do; do duoc ${JSON.stringify(dem.rawTao)}`,
    );

    // (d) HANG MOI XUAT HIEN tu mot lan DOC LAI danh sach (khong tu chen vao state): id 13 la
    //     hang server da ghi va `GET /api/translations` moi tra ve.
    await choPhanTu(
      container,
      '[data-testid="pick-13"]',
      (t) => t.includes("bản dịch"),
      "hang ban dich MOI khong xuat hien ⇒ danh sach khong duoc lam moi",
    );
    assert.ok(dem.translations >= 2, `phai doc lai danh sach ban dich; do duoc ${dem.translations}`);

    // (e) BAN VUA TAO tro thanh BAN DANG XEM — cung cau tra loi ma thanh transport dung.
    const dangChon = [...container.querySelectorAll('[data-testid^="pick-"]')].filter(
      (el) => el.getAttribute("aria-checked") === "true",
    );
    assert.equal(dangChon.length, 1, `phai co DUNG MOT ban dich dang chon; do duoc ${dangChon.length}`);
    assert.equal(
      (dangChon[0].getAttribute("data-testid") ?? "").replace("pick-", ""),
      "13",
      "ban VUA TAO phai la ban DANG XEM, khong phai ban `done` cu",
    );

    // (f) Ban moi la `queued` ⇒ cot phai NOI RA trang thai + trang thai JOB THAT, KHONG RONG.
    const cotPhai = textCua(container, '[data-testid="col-right"]');
    assert.equal(cotPhai.length, 3, `ban ghi co ba doan ⇒ ba o cot phai; do duoc ${JSON.stringify(cotPhai)}`);
    for (const o of cotPhai) {
      assert.match(o, /đang dịch/,
        `ban dich queued ⇒ cot phai phai noi ra trang thai (khong duoc rong); do duoc ${JSON.stringify(cotPhai)}`);
      // Trang thai JOB that den tu body 201 cua server (`{translation, job}`), khong bia o test.
      assert.match(o, /chờ gom lô/,
        `phai kem trang thai JOB THAT (job dang o trang thai 'queued'); do duoc ${JSON.stringify(cotPhai)}`);
    }

    assert.deepEqual(tiengOn, [], "bat dau dich khong duoc sinh tieng on console");
    unmount();
  });

  it("W3 LOI BACKEND: 409 ⇒ hien NGUYEN VAN cau tieng Viet cua backend, khong thay bang chu chung", async () => {
    dem.loiTao = true;
    const { container, unmount } = render(taoPhanTu(App));

    await toiDoiChieu(container, 2);
    const truoc = [...container.querySelectorAll('[data-testid^="pick-"]')].length;
    assert.equal(truoc, 2, "ban ghi nay co hai ban dich truoc khi bam");

    fireEvent.click(phanTu(container, '[data-testid="tao-ban-dich"]'));
    await waitFor(
      () => {
        assert.equal(dem.postTranslations, 1, "phai gui DUNG MOT `POST /api/translations`");
      },
      { timeout: 5000, interval: 20 },
    );

    // CAU NGUYEN VAN cua backend — do o PHIA SERVER roi doi chieu voi DOM (khong chep tay).
    const cau = "engine chưa sẵn sàng: 'opus-mt' (model chưa pull hoặc runtime không phục vụ được)";
    await choChu(container, cau);

    // Va khong co hang moi nao: backend TU CHOI TRUOC KHI GHI, nen UI cung khong duoc bia ra hang.
    assert.equal(
      [...container.querySelectorAll('[data-testid^="pick-"]')].length,
      2,
      "409 ⇒ KHONG co ban dich moi nao duoc them vao danh sach",
    );
    assert.equal(container.querySelectorAll('[data-testid="pick-13"]').length, 0,
      "409 ⇒ khong duoc co hang ban dich 13 nao");

    assert.deepEqual(tiengOn, [], "loi backend phai di ra DOM, khong duoc chi ghi console");
    unmount();
  });

  it("W3 KHONG CO ENGINE: moi MT deu `available === false` ⇒ nut VO HIEU + noi RO cach sua, va KHONG goi API", async () => {
    // Dung hinh dang THAT cua mot may chua pull model: MT co trong registry nhung `available`
    // false (do `app/main.py::_mark_availability`). Registry VAN co ASR ⇒ bai nay cung chung
    // minh ASR khong duoc tinh la engine dich.
    REGISTRY = {
      asr: [spec("faster-whisper-large", "Faster Whisper Large", "inprocess", undefined, "asr")],
      mt: [spec("qwen2.5-7b", "Qwen 2.5 7B", "ollama", false)],
    };
    const { container, unmount } = render(taoPhanTu(App));

    await toiDoiChieu(container, 2);

    const nut = phanTu(container, '[data-testid="tao-ban-dich"]') as HTMLButtonElement;
    assert.equal(nut.disabled, true, "khong co engine MT dung duoc ⇒ nut 'dich' phai VO HIEU");
    // ⚠️ ERRATA #30 / §4.8: doi mau la KHONG DU — phai noi RO VI SAO va CACH SUA.
    const ly = chu(container, '[data-testid="ly-do-khong-dich"]');
    assert.match(ly, /không có engine dịch nào dùng được/i,
      `phai noi RO vi sao; do duoc ${JSON.stringify(ly)}`);
    assert.match(ly, /(ollama|pull)/i, `phai noi RO CACH SUA; do duoc ${JSON.stringify(ly)}`);

    fireEvent.click(nut);
    // ⚠️ Dinh chinh `Minor #2` cua review W3: cho nay TUNG la `choNhip(250)` — mot `sleep`
    // THUAN (dieu kien thoat `Date.now() >= xong` luon tro thanh dung), va bao cao W3 khai
    // "0 phep cho theo dong ho duoc them" la SAI. Nay dung `choHaiNhip()`: hai vong microtask
    // du de mot `fetch` DA duoc goi chay tới server, va no KHONG the xanh chi vi dong ho da chay.
    // Menh de duoc ghim khong doi: nut VO HIEU thi khong duoc gui request nao.
    await choHaiNhip();
    assert.equal(dem.postTranslations, 0, "nut VO HIEU thi KHONG duoc goi API nao");

    assert.deepEqual(tiengOn, [], "nhanh khong co engine khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // VONG SUA W3 #1 — `I1`: hai state ANH EM cua `banMoiTao` ro ri THAT
  //
  // `banMoiTao` DA duoc ghim theo kenh (vong W3 goc lam dung). Nhung `trangThaiJobMoi` va
  // `loiTao` do CUNG `taoBanDich` ghi ma KHONG kem kenh va khong effect nao don:
  //   (a) chon mot ban dich KHAC ⇒ cot phai bi dan nhan job cua ban VUA TAO;
  //   (b) doi kenh ⇒ cau 409 cua kenh CU van nam trong khay tin.
  // Hai bai duoi day do tren DOM THAT (du lieu tu server `node:http` trong tien trinh).
  // -------------------------------------------------------------------------

  it("W3 I1: chon ban dich KHAC ⇒ cot phai KHONG duoc dan nhan job cua ban VUA TAO", async () => {
    // ---------------------------------------------------------------------------
    // ⚠️ HAI BAN NHAP DAU CUA BAI NAY LA NHUNG PHEP DO RONG — ghi lai de khong lap lai:
    //
    // (1) Dung ban 11 (`done`, 3 doan da dich): cot phai cua no la CHU THAT, nen `chuODichTrong`
    //     (ham DUY NHAT noi ra trang thai job) KHONG BAO GIO duoc goi. Do duoc: mutation
    //     `I1-bo-ve-kenh` va `I1-bo-dieu-kien-id` deu KHONG giet duoc bai.
    // (2) Co gang ep "cua so chi tiet chua ve" bang cach giu response (1200/1500/3000/6000 ms),
    //     bang `MutationObserver`, bang doc ngay sau `act`, bang bam "dich" lan hai: CA BON deu
    //     0/N mau. Ly do: `useApi` KHONG xoa `data` cu khi `reload()`, va chi tiet cua mot ban
    //     dich luon ve truoc khi nguoi dung kip bam.
    //
    // Cach DUOC: ban dich 12 — `queued`, KHONG co doan nao, VA KHONG co job nao. No co san trong
    // fixture (`chonTranslation` KHONG chon no vi no khong `done`), nen chon no bang DOM la TAT
    // DINH, va cot phai cua no di qua `chuODichTrong` tu dau den cuoi bai.
    //
    // Luong: (0) ban 11 la ban dang xem (mac dinh) ⇒ cot phai la CHU THAT, khong co `job:`;
    //        (1) bam "dich" ⇒ tao ban 13 (`queued`) + job ⇒ ban 13 la ban dang xem, cot phai
    //            PHAI co `job:` (khang dinh ve NGUOC LAI);
    //        (2) chon ban 12 (`queued`, KHONG co job) ⇒ cot phai KHONG duoc mang nhan job CUA
    //            BAN 13. Do duoc truoc vong sua: `"đang dịch… · job: chờ gom lô"`.
    // ---------------------------------------------------------------------------
    const { container, unmount } = render(taoPhanTu(App));

    await toiDoiChieu(container, 2);
    // (0) VE NGUOC LAI TRUOC: ban 11 la ban dang xem, va cot phai cua no KHONG co `job:`.
    await choPhuHop(
      container,
      '[data-testid="pick-11"]',
      (el) => el.getAttribute("aria-checked") === "true",
      "ban 11 (`done` moi nhat) phai la ban dang xem truoc khi tao",
    );
    const cotPhaiTruoc = textCua(container, '[data-testid="col-right"]');
    for (const o of cotPhaiTruoc) {
      assert.ok(
        !o.includes("job:"),
        `ban 11 (done, KHONG co job) khong duoc co nhan job TRUOC khi tao; do duoc ${JSON.stringify(cotPhaiTruoc)}`,
      );
    }

    // (1) BAM "dich" ⇒ tao ban 13 (`queued`), no tro thanh ban DANG XEM.
    fireEvent.click(phanTu(container, '[data-testid="tao-ban-dich"]'));
    await waitFor(
      () => {
        assert.equal(dem.postTranslations, 1, "phai gui DUNG MOT `POST /api/translations`");
      },
      { timeout: 5000, interval: 20 },
    );
    await choPhanTu(
      container,
      '[data-testid="pick-13"]',
      (t) => t.includes("bản dịch"),
      "hang ban dich MOI khong xuat hien ⇒ danh sach khong duoc lam moi",
    );
    const cotPhai13 = textCua(container, '[data-testid="col-right"]');
    for (const o of cotPhai13) {
      assert.match(o, /job:/, `ban 13 (queued) PHAI duoc noi ra trang thai job; do duoc ${JSON.stringify(cotPhai13)}`);
    }

    // (2) ⚠️ MENH DE NOI DUNG CUA `I1`: CHON BAN 12. Ban 12 la `queued`, KHONG co job nao, nen
    // cot phai cua no KHONG duoc mang nhan job cua ban 13 — ca hai deu la "dang dich…" nhung chi
    // ban 13 moi co job.
    fireEvent.click(phanTu(container, '[data-testid="pick-12"]'));
    await choPhuHop(
      container,
      '[data-testid="pick-12"]',
      (el) => el.getAttribute("aria-checked") === "true",
      "chua chon duoc ban 12 trong segmented control",
    );
    const cotPhaiSauKhiDoi = textCua(container, '[data-testid="col-right"]');
    assert.equal(cotPhaiSauKhiDoi.length, 3,
      `ba doan ⇒ ba o cot phai; do duoc ${JSON.stringify(cotPhaiSauKhiDoi)}`);
    // PHEP DO PHAI THUC SU DI QUA `chuODichTrong` — neu khong no la mot PHEP DO RONG.
    assert.ok(
      cotPhaiSauKhiDoi.every((t) => t.includes("đang dịch")),
      `ban 12 (queued, 0 doan) ⇒ cot phai phai noi ra trang thai; do duoc ${JSON.stringify(cotPhaiSauKhiDoi)}`,
    );
    // ⚠️ DIEU DO DUOC TRUOC VONG SUA (giu lai lam bang chung): `banDangXemId` van la 13 (ban
    // VUA TAO duoc uu tien, va no da co trong danh sach sau `reload`), nen cot phai cua ban 12
    // hien `"đang dịch… · job: chờ gom lô"` — job CUA BAN 13. Do la `I1` o dung hinh dang ma
    // brief mo ta, va no KHONG phai mot cua so thoi gian: no dung YEN cho tới khi nguoi dung
    // doi kenh hoac tai lai trang.
    for (const o of cotPhaiSauKhiDoi) {
      assert.ok(
        !o.includes("job:"),
        `ban 12 (queued, KHONG co job) KHONG duoc mang nhan job cua ban 13; do duoc `
        + `${JSON.stringify(cotPhaiSauKhiDoi)}`,
      );
    }

    assert.deepEqual(tiengOn, [], "doi ban dich khong duoc sinh tieng on console");
    unmount();
  });

  it("W3 I1: doi KENH ⇒ cau 409 cua kenh CU khong con trong DOM (reset `loiTao`)", async () => {
    dem.loiTao = true;
    const { container, unmount } = render(taoPhanTu(App));

    await toiDoiChieu(container, 2);
    fireEvent.click(phanTu(container, '[data-testid="tao-ban-dich"]'));
    const cau = "engine chưa sẵn sàng: 'opus-mt' (model chưa pull hoặc runtime không phục vụ được)";
    await choChu(container, cau);
    assert.equal(
      container.querySelectorAll('[data-testid="loi-tao"]').length,
      1,
      "cau 409 phai hien TRUOC khi doi kenh (neu khong phep do duoi day la RONG)",
    );

    // DOI KENH: kenh 2 (id 2) — ban ghi cua no la id 3.
    fireEvent.click(nutKenh(container, "kenh-hai"));
    await choPhuHop(
      container,
      '.ch__item[aria-pressed="true"]',
      (el) => (el.textContent ?? "").includes("kenh-hai"),
      "chua thay muc kenh thu hai duoc chon (`aria-pressed=\"true\"`)",
    );
    await choChu(container, "bản kênh hai");

    // ⚠️ MENH DE NOI DUNG CUA `I1` (nhanh doi kenh): cau 409 la cua kenh CU.
    assert.equal(
      container.querySelectorAll('[data-testid="loi-tao"]').length,
      0,
      "doi kenh ⇒ cau 409 cua kenh CU KHONG duoc con trong DOM; "
      + `do duoc ${JSON.stringify(textCua(container, '[data-testid="loi-tao"]'))}`,
    );
    assert.equal(
      (container.textContent ?? "").includes(cau),
      false,
      `toan bo DOM cua kenh MOI khong duoc chua cau 409 cua kenh CU; do duoc `
      + `${JSON.stringify((container.textContent ?? "").slice(-200))}`,
    );

    // ⚠️⚠️ VE THU HAI — va day moi la ve BAT BUOC phai co:
    // DO DUOC (mutation `I1-bo-reset` KHONG giet duoc bai nao khi bai chi co ve thu nhat):
    // ve "doi kenh ⇒ cau 409 bien mat" xanh NGAY CA KHI KHONG CO effect don, vi chinh BO LOC
    // `loiTao.kenh === ui.channelId` da lam no bien mat. Nhung khi do `loiTao` VAN CON trong
    // state, nen QUAY VE kenh cu thi cau 409 CU hiện LAI nhu moi. Day la ve duy nhat phan biet
    // "don that" voi "chi che di", va no cung la dieu ma ban sua brief yeu cau ("reset `loiTao`
    // khi doi kenh").
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choPhuHop(
      container,
      '.ch__item[aria-pressed="true"]',
      (el) => (el.textContent ?? "").includes("kenh-mot.wav"),
      "chua quay lai duoc kenh mot",
    );
    await choChu(container, "câu 1");
    assert.equal(
      container.querySelectorAll('[data-testid="loi-tao"]').length,
      0,
      "QUAY VE kenh cu ⇒ mot cau 409 cua mot lan bam DA CU khong duoc hien lai nhu moi; "
      + `do duoc ${JSON.stringify(textCua(container, '[data-testid="loi-tao"]'))}`,
    );

    assert.deepEqual(tiengOn, [], "doi kenh sau 409 khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // VONG SUA W3 #1 — `I2`: "MOT diem quyet dinh" phai la MOT bieu thuc
  //
  // Do duoc o review W3: `CompareScreen.macDinhId` = `banDangXemId` con
  // `Transport.translationId` = `banDichXuat.id` ⇒ HAI bieu thuc, va mutant `W3-17` (doi
  // `Transport` sang bien kia) cho **0 bai do**. Comment *"hai vung KHONG THE noi khac nhau"*
  // da SAI. Bai duoi day ghim bat bien do bang HAI CON SO doc tu DOM THAT.
  // -------------------------------------------------------------------------

  it("W3 I2 (SAME): vung Doi chieu dang xem ban nao thi thanh transport cung tro DUNG ban do", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    await toiDoiChieu(container, 2);
    // ⚠️ CHO THEO TIN HIEU truoc khi doc — va tin hieu do phai la DUNG THU SAP DOC. Do duoc trong
    // chien dich mutation: vot `W3-16`/`W3-10`/`I3-doc-theo-trang-thai` lam bai nay DO them
    // ("phai co DUNG MOT ban dich dang chon; do duoc 0") — tuc no FLAKY khi may cham.
    await choPhanTu(
      container,
      '[data-testid="pick-11"]',
      (t) => t.includes("bản dịch"),
      "vung Doi chieu chua commit xong danh sach ban dich",
    );
    // ⚠️ CHO THEO DUNG TIN HIEU MA PHEP DO SAP DOC: `aria-checked="true"` tren hang 11.
    // ⚠️ DINH CHINH vong sua #2: `toiDoiChieu` TUNG doi `dem.translationChiTiet === 2` (bo dem o
    // PHIA SERVER) — do la mot CON SO TICH LUY khong thuoc bai nay: mot request con dang bay cua
    // bai TRUOC ha canh sau `beforeEach` cung lam no tang, va bai nay do vi ly do do (do duoc
    // `3 !== 2` / `4 !== 2`; xem bao cao vong sua #2 va `choDanhSachBanDich`). Nay no cho DOM.
    // Cho theo `aria-checked` dong not khe "server dem xong ≠ React da commit".
    await choPhuHop(
      container,
      '[data-testid="pick-11"]',
      (el) => el.getAttribute("aria-checked") === "true",
      "ban `done` moi nhat (11) chua duoc chon lam ban dang xem",
    );
    // Moc 1: TRUOC khi tao — ca hai vung phai cung tro ban `done` 11.
    const sameTruoc = await soSanhHaiVung(container);
    assert.equal(sameTruoc.chon, 11,
      `truoc khi tao, ban dang xem phai la ban \`done\` 11 (khong phai ban \`queued\` 12); do duoc ${sameTruoc.chon}`);
    assert.equal(sameTruoc.chon, sameTruoc.xuat,
      `SAME = false: vung Doi chieu dang xem ${sameTruoc.chon}, con ba nut xuat tro vao ${sameTruoc.xuat}`);

    // Moc 2: SAU khi bam "dich" — ban VUA TAO (13, `queued`) la ban DANG XEM, va do la ca hai
    // vung cung phai noi. Day moi la moc ma `W3-17` tung LOT.
    fireEvent.click(phanTu(container, '[data-testid="tao-ban-dich"]'));
    await choPhanTu(
      container,
      '[data-testid="pick-13"]',
      (t) => t.includes("bản dịch"),
      "hang ban dich MOI khong xuat hien ⇒ danh sach khong duoc lam moi",
    );
    await choPhuHop(
      container,
      '[data-testid="pick-13"]',
      (el) => el.getAttribute("aria-checked") === "true",
      "ban VUA TAO (13) chua tro thanh ban dang xem",
    );
    const sameSau = await soSanhHaiVung(container);
    assert.equal(sameSau.chon, 13,
      `sau khi tao, ban VUA TAO (13) phai la ban dang xem; do duoc ${sameSau.chon}`);
    assert.equal(sameSau.chon, sameSau.xuat,
      `SAME = false: vung Doi chieu dang xem ${sameSau.chon}, con ba nut xuat tro vao ${sameSau.xuat}`);

    // Va vi ban 13 CHUA dich xong (0 doan) nen no khong co noi dung de xuat: thanh transport
    // phai NOI RA ban nao se duoc xuat, chu khong im lang xuat mot ban khac.
    const cho = chu(container, '[data-testid="xuat-cho"]');
    assert.match(cho, /13/, `cau noi ro phai neu ban DANG XEM (13); do duoc ${JSON.stringify(cho)}`);
    assert.match(cho, /11/, `cau noi ro phai neu ban SE DUOC XUAT (11); do duoc ${JSON.stringify(cho)}`);

    assert.deepEqual(tiengOn, [], "bat bien SAME khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // VONG SUA W3 #2 — `Important` F2: mot CAU NOI SAI ve du lieu cua NGUOI DUNG
  //
  // DO DUOC (probe cua re-review W3 #1, nguyen van):
  //   RR-PROBE-2 XUATCHO="bản đang xem (11) chưa dịch xong — xuất bản 13" HREF=/api/export/13?…
  //   TOKEN=11
  // trong khi ban 11 **DA `done`** (3 doan da dich). Fixture cu CHI co MOT ban `done` cho ban ghi
  // 5, nen KHONG bai nao nhin thay ca nay: dieu kien cu (`exportableId !== translationId`) noi
  // "chua dich xong" cho MOI ly do lech id, ke ca ly do nguoc lai.
  // -------------------------------------------------------------------------

  it("W3 I2 (XUAT): ban dang xem DA `done` ⇒ ba nut XUAT tro CHINH no, va KHONG duoc noi 'chua dich xong'", async () => {
    // FIXTURE CO **HAI** BAN `done` cho ban ghi 5: 11 (cu) va 13 (MOI NHAT), cong 12 `queued`.
    // Ban se duoc NGUOI DUNG chon la 11 — mot ban `done` NHUNG KHONG phai moi nhat. Do dung la ca
    // ma fixture mot-ban-`done` khong the sinh ra.
    TRANSLATIONS = [...TRANSLATIONS, banDich(13, 5, "done")];
    TRANSLATION_CHI_TIET[13] = {
      ...banDich(13, 5, "done"),
      segments: [doan(0, 0, 2, "câu một (bản 13)")],
      cps: { max_cps: 21, rows: [] },
    };

    const { container, unmount } = render(taoPhanTu(App));

    // Ba hang ban dich cua ban ghi 5 trong DOM THAT.
    await toiDoiChieu(container, 3);

    // (0) MAC DINH: ban `done` MOI NHAT (13) la ban dang xem ⇒ xuat 13 va KHONG co cau nao.
    await choPhuHop(
      container,
      '[data-testid="pick-13"]',
      (el) => el.getAttribute("aria-checked") === "true",
      "ban `done` moi nhat (13) phai la ban dang xem truoc khi nguoi dung chon",
    );
    assert.equal(idXuat(container), 13,
      `mac dinh: ban dang xem (13, done moi nhat) cung la ban duoc xuat; do duoc ${idXuat(container)}`);
    assert.equal(
      container.querySelectorAll('[data-testid="xuat-cho"]').length,
      0,
      "mac dinh hai id BANG nhau ⇒ khong co gi de giai thich, KHONG duoc co cau nao",
    );

    // (1) NGUOI DUNG BAM CHON BAN 11 — ban DA `done` nhung KHONG phai ban `done` moi nhat.
    fireEvent.click(phanTu(container, '[data-testid="pick-11"]'));
    await choPhuHop(
      container,
      '[data-testid="pick-11"]',
      (el) => el.getAttribute("aria-checked") === "true",
      "chua chon duoc ban 11 trong segmented control",
    );

    // (2) MENH DE CUA F2: ban dang xem DA dich xong ⇒ ba nut XUAT phai tro CHINH ban do.
    //     Day la ve ma ban cu VI PHAM: no ghi de lua chon cua nguoi dung bang ban `done` moi nhat.
    assert.equal(idXuat(container), 11,
      "ban dang xem (11) DA `done` ⇒ ba nut XUAT phai tro 11; ghi de bang ban `done` moi nhat (13) la "
      + `ghi de LUA CHON cua nguoi dung; do duoc ${idXuat(container)}`);

    // (3) VA cau "chua dich xong" KHONG duoc noi ra — no KHONG dung su that (11 DA dich xong).
    assert.equal(
      container.querySelectorAll('[data-testid="xuat-cho"]').length,
      0,
      "ban 11 DA `done` ⇒ cau 'chua dich xong' la mot CAU SAI; do duoc "
      + `${JSON.stringify(textCua(container, '[data-testid="xuat-cho"]'))}`,
    );

    // (4) VE NGUOC LAI — cau do PHAI co khi ly do la THAT: chon ban 12 (`queued`, 0 doan).
    fireEvent.click(phanTu(container, '[data-testid="pick-12"]'));
    await choPhuHop(
      container,
      '[data-testid="pick-12"]',
      (el) => el.getAttribute("aria-checked") === "true",
      "chua chon duoc ban 12 trong segmented control",
    );
    const cau = await choPhanTu(
      container,
      '[data-testid="xuat-cho"]',
      (t) => t.includes("12") && t.includes("13"),
      "ban 12 (`queued`) ⇒ phai co cau noi ro ban nao se duoc xuat",
    );
    assert.match(cau, /chưa dịch xong/,
      `ban 12 THAT SU chua dich xong ⇒ cau phai noi dung su that; do duoc ${JSON.stringify(cau)}`);
    assert.equal(idXuat(container), 13,
      `ban 12 chua co noi dung ⇒ xuat ban \`done\` moi nhat (13); do duoc ${idXuat(container)}`);

    assert.deepEqual(tiengOn, [], "chon ban dich khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // VONG SUA W3 #2 — `Minor #3`: `failed`/`cancelled` KHONG co bai ghim nao
  //
  // DO DUOC (re-review W3 #1): mutation `RR-I3-bo-failed-cancelled` (chi giu `done` trong ngoi no
  // doc lai) ⇒ **0 bai do** — hai nhanh `failed`/`cancelled` cua ngoi no KHONG duoc ghim. Bai nay
  // ghim CA HAI bang DOM THAT (cot phai noi SU THAT cua ban dich, khong phai mot loi khai).
  // -------------------------------------------------------------------------

  it("W3 I3 (ket thuc KHONG thanh cong): job `translate` `failed`/`cancelled` ⇒ cot phai noi SU THAT", async () => {
    // HAI job `translate` cua CUNG ban dich 13, ca hai vao anh chup o trang thai `running` (KHONG
    // nam trong tap "da ket thuc") ⇒ moi lan mot trong hai chuyen sang mot trang thai KET THUC la
    // mot lan CHUYEN TRANG THAI, tuc keo DUNG MOT lan doc lai danh sach ban dich.
    themJobDich(33, "running", 13);
    themJobDich(34, "running", 13);

    const { container, unmount } = render(taoPhanTu(App));

    await toiDoiChieu(container, 2);
    await waitFor(
      () => {
        assert.ok(streams.size >= 1, "hook chua mo /api/jobs/stream");
      },
      { timeout: 5000, interval: 20 },
    );

    fireEvent.click(phanTu(container, '[data-testid="tao-ban-dich"]'));
    await choPhanTu(
      container,
      '[data-testid="pick-13"]',
      (t) => t.includes("bản dịch"),
      "hang ban dich MOI khong xuat hien ⇒ danh sach khong duoc lam moi",
    );

    // (A) JOB DICH `failed` — server tra ve ban dich 13 `status: "failed"` o lan doc ke tiep.
    //     Chu "dich loi" chi co the tới DOM qua mot lan DOC LAI `/api/translations`.
    TRANSLATION_CHI_TIET[13] = {
      ...banDich(13, 5, "failed"),
      segments: [],
      cps: { max_cps: 21, rows: [] },
    };
    TRANSLATIONS = TRANSLATIONS.map((t) => (t.id === 13 ? banDich(13, 5, "failed") : t));

    emit(sse({ id: 33, state: "failed", progress: 1, phase: "translate:opus-mt", error: "loi dich", log_tail: "" }));
    // ⚠️ Cho DUNG O MA BAI SAP DOC (`.cmp__dich`), KHONG phai `choChu(container, "dịch lỗi")`:
    // chu do con xuat hien o vung HANG DOI (nhan trang thai job) va o do no doi NGAY khi su kien
    // SSE tới — tuc mot phep cho "A" trong khi bai doc "B" (dung lop loi ERRATA #35 muc 1, va ban
    // nhap dau cua chinh bai nay da mac: no doc duoc `dịch lỗi` cu con lai sau buoc `cancelled`).
    await choPhanTu(
      container,
      '[data-testid="col-right"]',
      (t) => t.includes("dịch lỗi"),
      "ban dich `failed` chua tới COT PHAI (mot lan doc lai `/api/translations` phai keo no tới)",
    );
    const cotPhaiFailed = textCua(container, '[data-testid="col-right"]');
    assert.ok(
      cotPhaiFailed.every((t) => t.includes("dịch lỗi")),
      `ban dich \`failed\` ⇒ cot phai phai noi 'dich loi' o MOI o; do duoc ${JSON.stringify(cotPhaiFailed)}`,
    );
    assert.ok(
      !cotPhaiFailed.some((t) => t.includes("đang dịch")),
      `ban dich \`failed\` ⇒ cot phai KHONG duoc con noi 'dang dich…'; do duoc ${JSON.stringify(cotPhaiFailed)}`,
    );

    // (B) NHANH `cancelled` — job THU HAI cua cung ban dich do (tap "da ket thuc" doi tu {33}
    //     sang {33,34} ⇒ mot lan chuyen trang thai NUA, tuc mot lan doc lai nua).
    TRANSLATION_CHI_TIET[13] = {
      ...banDich(13, 5, "cancelled"),
      segments: [],
      cps: { max_cps: 21, rows: [] },
    };
    TRANSLATIONS = TRANSLATIONS.map((t) => (t.id === 13 ? banDich(13, 5, "cancelled") : t));

    emit(sse({ id: 34, state: "cancelled", progress: 1, phase: "translate:opus-mt", error: null, log_tail: "" }));
    // Cung ly do: cho DUNG `col-right`, khong phai chu "đã huỷ" o vung HANG DOI (no doi ngay,
    // truoc khi lan doc lai danh sach ban dich kip ve).
    await choPhanTu(
      container,
      '[data-testid="col-right"]',
      (t) => t.includes("đã huỷ"),
      "ban dich `cancelled` chua tới COT PHAI (mot lan doc lai `/api/translations` phai keo no tới)",
    );
    const cotPhaiCancelled = textCua(container, '[data-testid="col-right"]');
    assert.ok(
      cotPhaiCancelled.every((t) => t.includes("đã huỷ")),
      `ban dich \`cancelled\` ⇒ cot phai phai noi 'da huy' o MOI o; do duoc ${JSON.stringify(cotPhaiCancelled)}`,
    );
    assert.ok(
      !cotPhaiCancelled.some((t) => t.includes("đang dịch")),
      `ban dich \`cancelled\` ⇒ cot phai KHONG duoc con noi 'dang dich…'; do duoc ${JSON.stringify(cotPhaiCancelled)}`,
    );

    assert.deepEqual(tiengOn, [], "job dich ket thuc KHONG thanh cong khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // VONG SUA W3 #1 — `I3`: job dich XONG ma khong doc lai `translations`
  //
  // Do duoc (doc ma + `grep`): `translations.reload()` chi co MOT call site (trong
  // `taoBanDich`), nen job `translate` chay xong thi hang van `queued` va cot phai van noi
  // "dang dich…" MAI MAI. Bai duoi day do CA HAI VE ma ERRATA #11 muc 2 doi:
  //   (i)  cot phai DOI KHOI "dang dich…" khi job chuyen `running ⇒ done`;
  //   (ii) so request o PHIA SERVER: tien do ⇒ 0, lap trang thai cu ⇒ 0, `running ⇒ done` ⇒ 1.
  // -------------------------------------------------------------------------

  it("W3 I3: job `translate` chuyen `running` ⇒ `done` ⇒ cot phai THOI noi 'dang dich…'", async () => {
    // Job DICH cua ban vua tao se la id 33 (`makeJob(20 + id)` voi id 13 — xem
    // `taoBanDichTheoYeuCau`), nhung id do chi biet SAU khi POST xong. Vi vay bai nay day job
    // vao anh chup NGAY TRUOC khi stream mo, roi moi bam "dich" — `payload.translation_id` chi
    // den tu anh chup (su kien SSE khong mang `payload`).
    themJobDich(33, "running", 13);

    const { container, unmount } = render(taoPhanTu(App));

    await toiDoiChieu(container, 2);
    await waitFor(
      () => {
        assert.ok(streams.size >= 1, "hook chua mo /api/jobs/stream");
      },
      { timeout: 5000, interval: 20 },
    );

    fireEvent.click(phanTu(container, '[data-testid="tao-ban-dich"]'));
    await choPhanTu(
      container,
      '[data-testid="pick-13"]',
      (t) => t.includes("bản dịch"),
      "hang ban dich MOI khong xuat hien ⇒ danh sach khong duoc lam moi",
    );
    // Moc do SAU khi moi thu da on dinh: phep do la HIEU so, nen no khong phu thuoc request
    // cua phan mount con dang bay.
    const truoc = dem.translations;
    const cotPhaiTruoc = textCua(container, '[data-testid="col-right"]');
    assert.ok(
      cotPhaiTruoc.every((t) => t.includes("đang dịch")),
      `TRUOC khi job xong, cot phai phai noi 'dang dich…' (neu khong phep do la RONG); do duoc `
      + `${JSON.stringify(cotPhaiTruoc)}`,
    );

    // (A) su kien TIEN DO cua job DANG CHAY ⇒ KHONG doc lai danh sach ban dich.
    // ⚠️ CHO THEO TIN HIEU, KHONG THEO DONG HO (ERRATA #35 muc 1/2, brief §2 I3): cho tới khi
    // su kien TIEN DO da tới DOM (`.q__item` cua job #33 mang `40%`) — luc do su kien da duoc
    // xu ly XONG qua `useJobStream` → React → DOM, va mot effect co goi `reload()` thi request
    // da duoc GUI RA TRUOC moc do. Sau khi DOM cho thay su kien da xu ly, mot vong microtask la
    // du de request do tới noi nhan. (Truoc day cho nay la `choNhip(250)` — mot `sleep` THUAN.)
    emit(sse({ id: 33, state: "running", progress: 0.4, phase: "translate:opus-mt", error: null, log_tail: "" }));
    await choPhanTu(
      container,
      ".q__item",
      (t) => t.includes("#33 ") && t.includes("40%"),
      "su kien TIEN DO cua job 33 khong tới DOM (nen phep do se RONG)",
    );
    await choHaiNhip();
    assert.equal(
      dem.translations - truoc,
      0,
      `mot su kien TIEN DO khong duoc keo request doc lai danh sach ban dich (BAO REQUEST); `
      + `do duoc ${dem.translations - truoc}`,
    );

    // (B) su kien lap lai DUNG trang thai cu ⇒ cung KHONG doc lai.
    emit(sse({ id: 33, state: "running", progress: 0.4, phase: "translate:opus-mt", error: null, log_tail: "" }));
    await choHaiNhip();
    assert.equal(
      dem.translations - truoc,
      0,
      `mot su kien KHONG doi trang thai khong duoc keo request doc lai; do duoc ${dem.translations - truoc}`,
    );

    // May chu TRA LOI BAN DICH DA XONG o lan doc ke tiep — do la thu lam phep do co nghia:
    // anh chup luc mount la ban `queued` rong, nen chu dich CHI co the tới DOM qua mot lan DOC LAI.
    TRANSLATION_CHI_TIET[13] = {
      ...banDich(13, 5, "done"),
      segments: [doan(0, 0, 2, "câu một (dịch xong)"), doan(1, 2, 4, "câu hai (dịch xong)"), doan(2, 4, 6, "câu ba (dịch xong)")],
      cps: {
        max_cps: 21,
        rows: [
          { i: 0, chars: 5, window: 1.2, cps: 4.2, max_cps: 21, over: false },
          { i: 1, chars: 6, window: 1.0, cps: 6.0, max_cps: 21, over: false },
          { i: 2, chars: 7, window: 1.1, cps: 30.5, max_cps: 21, over: true },
        ],
      },
    };
    TRANSLATIONS = TRANSLATIONS.map((t) => (t.id === 13 ? banDich(13, 5, "done") : t));

    // (C) CHUYEN TRANG THAI THAT (`running` ⇒ `done`) ⇒ DUNG MOT lan doc lai.
    emit(sse({ id: 33, state: "done", progress: 1, phase: "translate:opus-mt", error: null, log_tail: "" }));
    await waitFor(
      () => {
        assert.ok(
          dem.translations - truoc >= 1,
          "chuyen trang thai sang `done` PHAI keo mot lan doc lai /api/translations",
        );
      },
      { timeout: 5000, interval: 20 },
    );
    // (i) COT PHAI DOI KHOI "dang dich…": day la menh de noi dung cua `I3`.
    await choChu(container, "câu một (dịch xong)");
    const cotPhaiSau = textCua(container, '[data-testid="col-right"]');
    assert.ok(
      cotPhaiSau.some((t) => t.includes("dịch xong")),
      `job xong ⇒ cot phai phai hien CHU DICH THAT; do duoc ${JSON.stringify(cotPhaiSau)}`,
    );
    assert.ok(
      !cotPhaiSau.some((t) => t.includes("đang dịch")),
      `job xong ⇒ cot phai KHONG duoc con noi 'đang dịch…' (I3: no dung MAI MAI neu khong doc lai); `
      + `do duoc ${JSON.stringify(cotPhaiSau)}`,
    );

    // (ii) DUNG MOT request (khong phai mot request moi nhip SSE).
    // ⚠️ VA PHEP DO NAY CO MOT VE THU HAI, do duoc khi mutation `I3-doc-moi-nhip` (doc lai vo
    // dieu kien moi khi effect chay) tung LOT: mot su kien LAP LAI trang thai cu SAU khi job da
    // xong cung KHONG duoc keo them request nao. Neu thieu ve nay thi "doc lai moi nhip" va
    // "doc lai theo chuyen trang thai" cho KET QUA Y HET trong bai nay.
    // Cho theo TIN HIEU: `choChu` ngay tren da doi chu dich tới DOM, tuc lan doc lai DA hoan tat
    // (request tới noi nhan + response + render). Mot vong microtask la du cho phan con lai.
    await choHaiNhip();
    assert.equal(
      dem.translations - truoc,
      1,
      `mot lan chuyen trang thai = DUNG MOT request (khong phai mot request moi nhip SSE); `
      + `do duoc ${dem.translations - truoc}`,
    );
    emit(sse({ id: 33, state: "done", progress: 1, phase: "translate:opus-mt", error: null, log_tail: "" }));
    await choHaiNhip();
    await choHaiNhip();
    assert.equal(
      dem.translations - truoc,
      1,
      `mot su kien LAP LAI trang thai cu SAU khi job da xong cung khong duoc keo request; `
      + `do duoc ${dem.translations - truoc}`,
    );

    assert.deepEqual(tiengOn, [], "ngoi no doc lai ban dich khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // TASK W2 VONG SUA #1 — `Important` I1: `App.napTep` PHAI duoc THI HANH.
  //
  // DO DUOC TRUOC VONG SUA (mutant dau doc): chen `throw` lam CAU DAU cua `App.napTep` ⇒ suite
  // VAN `tests 215 / fail 2 / cancelled 0`, tuc KHONG bai nao chay qua ham do ⇒ `W2-1` (bo
  // `sources.reload()`), `W2-2` (bo `dispatch(selectChannel)`), `W2-5b` (nuot loi trong `App`) va
  // `W2-6` (chon kenh ca khi MOI tep loi) deu SONG SOT.
  //
  // Bon bai duoi day di qua DOM THAT (bam nut o khung §4.2 / doi tep o loi nap gon) toi tan
  // `App.napTep`, voi server `node:http` THAT trong tien trinh: khong mock `endpoints.ts`/
  // `client.ts`, khong `fetch` gia. Chung ghim BON menh de (a)(b)(c)(d) cua brief §1.
  //
  // ⚠️ MOI phep cho o day cho DUNG tin hieu ma khang dinh NGAY SAU do DOC (ERRATA #38 muc 2 /
  // #39 muc 5): dong ket qua `.nap__kq`, so request o PHIA SERVER, roi hang `.ch__item` + trang
  // thai `aria-pressed` cua no.
  // -------------------------------------------------------------------------

  it("W2 I1 (KHUNG §4.2): tệp ĐẦU LỖI + tệp SAU THÀNH CÔNG ⇒ đọc LẠI danh sách kênh (đếm ở SERVER) và chọn kênh của TỆP THÀNH CÔNG ĐẦU TIÊN", async () => {
    // Tep DAU tien LOI (422 nguyen van cua backend), tep THU HAI thanh cong ⇒ phep do phan biet
    // duoc "tep dau tien" voi "tep THANH CONG dau tien" (mot `find(kq => true)` se chon tep loi).
    dem.uploadLoiTheoTen = ["hong.wav"];
    const { container, unmount } = render(taoPhanTu(App));

    await choChu(container, "kenh-mot.wav");
    const nguonTruoc = dem.sources;

    // KHUNG §4.2 o VUNG GIUA (trang thai khoi dong: chua chon kenh nao ⇒ `transcript === null`).
    fireEvent.change(phanTu(container, '[data-testid="nap-o-tep"]'), {
      target: { files: [tepThat("hong.wav", [1, 2]), tepThat("tot.wav", [3, 4, 5])] },
    });
    fireEvent.click(phanTu(container, '[data-testid="nap-nut"]'));

    // (d) LOI CUA BACKEND HIEN NGUYEN VAN, va ket qua TUNG TEP hien bang CHU.
    const dongLoi = await choPhanTu(
      container,
      ".nap__kq",
      (t) => t.includes("hong.wav"),
      "khong thay dong ket qua cua tep LOI",
    );
    assert.equal(
      dongLoi,
      "hong.wav: LỖI — 422: tệp rỗng",
      "cau loi cua backend phai hien NGUYEN VAN (khong duoc thay bang 'co loi xay ra')",
    );
    const dongXong = await choPhanTu(
      container,
      ".nap__kq",
      (t) => t.includes("tot.wav"),
      "khong thay dong ket qua cua tep THANH CONG",
    );
    assert.match(dongXong, /^tot\.wav: đã nạp — kênh \d+$/, "ket qua tep thanh cong phai kem id KENH");

    // (a) DANH SACH KENH DUOC DOC LAI — dem o PHIA SERVER. Mot loi khai "da bam nut" khong phan
    // biet duoc "request doc lai da di" voi "du lieu den tu mot cho khac".
    await waitFor(
      () => {
        assert.ok(
          dem.sources > nguonTruoc,
          `sau luot nap PHAI co mot lan doc lai /api/sources; do duoc ${dem.sources} (truoc ${nguonTruoc})`,
        );
      },
      { timeout: 5000, interval: 20 },
    );

    // ... VA hang kenh MOI chi co the den tu lan doc lai do (fixture CHI them hang khi co request).
    const kenhMoi = await choPhanTu(
      container,
      ".ch__item",
      (t) => t.includes("tot.wav"),
      "kenh MOI khong xuat hien trong danh sach ⇒ `sources.reload()` khong duoc goi",
    );
    assert.ok(!kenhMoi.includes("hong.wav"), "tep LOI khong duoc tao kenh nao");

    // (b) KENH CUA TEP THANH CONG DAU TIEN duoc CHON — khong phai tep dau (no loi), va khong phai
    // "khong chon gi".
    await waitFor(
      () => {
        const chon = kenhDangChon(container);
        assert.ok(
          chon !== null && chon.includes("tot.wav"),
          `kenh cua tep THANH CONG DAU TIEN phai duoc chon; do duoc ${JSON.stringify(chon)}`,
        );
      },
      { timeout: 5000, interval: 20 },
    );

    // BANG CHUNG DUONG THAT: hai tep ⇒ HAI request multipart, dung thu tu nguoi dung dua vao.
    assert.equal(dem.upload, 2, "hai tep ⇒ DUNG HAI request nap toi server");
    assert.deepEqual(dem.uploadTenTep, ["hong.wav", "tot.wav"], "thu tu tep phai duoc giu");
    assert.deepEqual(tiengOn, [], "mot luot nap THAT khong duoc sinh tieng on console");
    unmount();
  });

  it("W2 I1 (MỌI TỆP LỖI): kênh ĐANG CHỌN không đổi, và KHÔNG hàng kênh nào được thêm", async () => {
    dem.uploadLoiToanBo = true;
    const { container, unmount } = render(taoPhanTu(App));
    await choChu(container, "kenh-mot.wav");

    // CHON kenh 1 TRUOC: phai co mot trang thai "dang chon" ma luot nap loi co the lam thay doi.
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    await waitFor(
      () => {
        const chon = kenhDangChon(container);
        assert.ok(
          chon !== null && chon.includes("kenh-mot.wav"),
          `kenh 1 phai duoc chon TRUOC luot nap; do duoc ${JSON.stringify(chon)}`,
        );
      },
      { timeout: 5000, interval: 20 },
    );
    const soHangTruoc = container.querySelectorAll(".ch__item").length;
    const nguonTruoc = dem.sources;

    // Sau khi DA chon kenh, khung §4.2 khong con o vung giua ⇒ loi nap dung la loi NAP GON.
    fireEvent.change(phanTu(container, '[data-testid="ch-nap-o-tep"]'), {
      target: { files: [tepThat("hong.wav")] },
    });
    await choPhanTu(
      container,
      ".nap__kq",
      (t) => t.includes("hong.wav: LỖI — 422: tệp rỗng"),
      "ket qua cua luot nap loi khong tới DOM",
    );
    // Luot nap van PHAI doc lai danh sach (do la gia re nhat de danh sach khong lech may chu) —
    // cho DUNG tin hieu do TRUOC khi khang dinh "khong doi kenh", neu khong phep do se RONG.
    await waitFor(
      () => {
        assert.ok(
          dem.sources > nguonTruoc,
          `luot nap PHAI doc lai danh sach; do duoc ${dem.sources} (truoc ${nguonTruoc})`,
        );
      },
      { timeout: 5000, interval: 20 },
    );

    assert.equal(
      container.querySelectorAll(".ch__item").length,
      soHangTruoc,
      "MOI tep loi ⇒ KHONG duoc them hang kenh nao",
    );
    const chon = kenhDangChon(container);
    assert.ok(
      chon !== null && chon.includes("kenh-mot.wav"),
      `MOI tep loi ⇒ kenh dang chon KHONG duoc doi (chon mot kenh CU la hanh vi SAI — ` +
        `do la chinh mutation W2-6); do duoc ${JSON.stringify(chon)}`,
    );
    assert.equal(dem.upload, 1, "mot tep ⇒ MOT request nap");
    assert.deepEqual(tiengOn, [], "luot nap loi khong duoc sinh tieng on console");
    unmount();
  });

  it("W2 I1 (LỐI GỌN ChannelZone): CÙNG hàm nạp ⇒ đọc lại danh sách + chọn kênh của tệp THÀNH CÔNG ĐẦU TIÊN", async () => {
    dem.uploadLoiTheoTen = ["hong.wav"];
    const { container, unmount } = render(taoPhanTu(App));
    await choChu(container, "kenh-mot.wav");
    const nguonTruoc = dem.sources;

    // LOI NAP GON: chon tep la nap NGAY (khong nut trung gian). Tep dau LOI, tep sau THANH CONG.
    fireEvent.change(phanTu(container, '[data-testid="ch-nap-o-tep"]'), {
      target: { files: [tepThat("hong.wav"), tepThat("tot.wav")] },
    });
    await choPhanTu(
      container,
      ".nap__kq",
      (t) => t.includes("hong.wav: LỖI — 422: tệp rỗng"),
      "loi GON: ket qua cua tep loi khong tới DOM",
    );
    await waitFor(
      () => {
        assert.ok(
          dem.sources > nguonTruoc,
          `loi GON cung PHAI doc lai danh sach kenh; do duoc ${dem.sources} (truoc ${nguonTruoc})`,
        );
      },
      { timeout: 5000, interval: 20 },
    );
    await choPhanTu(
      container,
      ".ch__item",
      (t) => t.includes("tot.wav"),
      "loi GON: kenh moi khong xuat hien ⇒ khong di vao CUNG ham nap",
    );
    await waitFor(
      () => {
        const chon = kenhDangChon(container);
        assert.ok(
          chon !== null && chon.includes("tot.wav"),
          `loi GON: kenh cua tep THANH CONG DAU TIEN phai duoc chon; do duoc ${JSON.stringify(chon)}`,
        );
      },
      { timeout: 5000, interval: 20 },
    );
    assert.equal(dem.upload, 2, "loi GON: hai tep ⇒ DUNG HAI request nap");
    assert.deepEqual(tiengOn, [], "loi GON nap tep khong duoc sinh tieng on console");
    unmount();
  });

  it("W2 I2: `lang` là TRƯỜNG FORM trong multipart THẬT (bóc từ BYTE THÔ); URL KHÔNG query; tệp đuôi LẠ vẫn được GỬI", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await choChu(container, "kenh-mot.wav");

    // ⚠️ Duoi LA (`.xyzla`) + content-type `application/octet-stream`: day la HANH VI ma cau
    // "tep duoi khac van gui duoc" dua vao (`M5`). Client KHONG duoc loc dinh dang — backend
    // cung khong chan duoi nao (doc `routes_sources.py`: `_safe_name` chi giu `suffix`).
    const byte = [0, 1, 2, 250, 255];
    fireEvent.change(phanTu(container, '[data-testid="nap-o-tep"]'), {
      target: { files: [tepThat("bai-hat.xyzla", byte, "application/octet-stream")] },
    });
    fireEvent.change(phanTu(container, '[data-testid="nap-tep-lang"]'), { target: { value: "en" } });
    fireEvent.click(phanTu(container, '[data-testid="nap-nut"]'));
    await choPhanTu(
      container,
      ".nap__kq",
      (t) => t.includes("bai-hat.xyzla"),
      "ket qua nap khong tới DOM",
    );

    assert.equal(dem.upload, 1, "mot tep ⇒ MOT request multipart toi server");
    // (1) URL: `lang` KHONG di bang query. Mutation `W2-4` (Form ⇒ query) lam dong nay DO.
    assert.equal(
      dem.uploadUrl,
      "/api/sources/upload",
      "URL nap KHONG duoc mang query — `lang` la truong FORM, khong phai query",
    );
    assert.equal(
      new URL(dem.uploadUrl, origin).search,
      "",
      "query cua URL nap phai RONG",
    );
    // (2) content-type: multipart THAT, co boundary.
    assert.match(
      dem.uploadContentType,
      /^multipart\/form-data; boundary=/,
      `content-type phai la multipart co boundary; do duoc ${JSON.stringify(dem.uploadContentType)}`,
    );

    // (3) BYTE THO: khang dinh phep do doc tu CHINH buffer nhan duoc, khong phai tu mot object da
    // duoc phan tich san.
    const raw = dem.uploadRaw;
    assert.ok(raw !== null, "server phai ghi lai duoc BYTE THO cua request");
    assert.ok(raw.length > 0, `byte tho phai khac rong; do duoc ${raw === null ? 0 : raw.length}`);
    assert.ok(
      raw.includes(Buffer.from('name="lang"', "latin1")),
      'byte tho PHAI chua phan `name="lang"` ⇒ `lang` nam TRONG BODY, khong o query',
    );
    assert.ok(raw.includes(Buffer.from('name="file"', "latin1")), 'byte tho phai chua phan `name="file"`');

    // (4) BOC TU BYTE THO: dung hai phan, theo thu tu [file, lang]; `lang` la GIA TRI CUA PHAN;
    // ten tep va BYTE di nguyen ven.
    assert.deepEqual(
      dem.uploadPhan,
      ["file", "lang"],
      "multipart PHAI co dung hai phan [file, lang]; mutation W2-4 lam no tut ve [file]",
    );
    assert.equal(dem.uploadLang, "en", "`lang` phai la gia tri cua MOT PHAN trong body");
    assert.deepEqual(dem.uploadTenTep, ["bai-hat.xyzla"], "client KHONG duoc loc duoi tep");
    assert.deepEqual(dem.uploadByteTep, [byte], "BYTE cua tep phai di NGUYEN VEN qua multipart");

    // ⚠️ Cho luot DOC LAI do `napTep` phat ra di HET duong (hang kenh moi len DOM) TRUOC khi ket
    // thuc bai. Khong cho thi mot request con dang bay ha canh SAU khi bai ket thuc — va (do duoc)
    // runner bao *"generated asynchronous activity after the test ended"* kem
    // `ReferenceError: window is not defined`, tuc `EXIT=1` vi mot ly do KHONG lien quan den menh de.
    await choPhanTu(
      container,
      ".ch__item",
      (t) => t.includes("bai-hat.xyzla"),
      "kenh moi (duoi LA) khong xuat hien ⇒ danh sach kenh khong duoc doc lai",
    );

    assert.deepEqual(tiengOn, [], "nap multipart khong duoc sinh tieng on console");
    unmount();
  });

  // =========================================================================
  // TASK D1 — DUONG GHI DAU TIEN CUA WORKSPACE 1: SUA DONG + NUDGE MOC
  //
  // DO DUOC TRUOC D1: `endpoints.patchTranscript` **0 luot goi trong san pham**,
  // `startEdit`/`endEdit` **0 luot dispatch** (chi co trong `reducer.ts` va `reducer.test.ts`),
  // `nudge` **0 handler** (chi co trong hai comment cua `lib/timecode*`).
  //
  // ⚠️ Mot ban dung lai `Segment` chi voi `{i,start,end,text}` se XOA AM THAM `suspect`/`qa`/
  // `events`/`words` cua MOI dong (backend buoc gui TOAN BO mang — `min_length=1`). Bon bai duoi
  // day do o PHIA MAY CHU (body JSON that, so request that).
  // =========================================================================

  it("D1 SỬA DÒNG: Enter ⇒ PATCH gửi TOÀN BỘ segments, CHỈ MỘT phần tử đổi `text`, dòng khác GIỮ `suspect`/`qa`", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    const goc = TRANSCRIPT_CHI_TIET_GOC[3].segments;
    assert.equal(goc.length, 4, "ban ghi cua D1 phai co BON doan");

    // (1) VÀO: bấm dòng 1 ⇒ dòng đó thành Ô NHẬP chứa ĐÚNG chữ hiện có.
    const o = await moOSua(container, 1);
    assert.equal(o.value, "dòng hai", "ô nhập phải chứa ĐÚNG chữ hiện có của dòng");

    // (2) SỬA + `Enter`.
    fireEvent.change(o, { target: { value: "dòng hai (đã sửa)" } });
    fireEvent.keyDown(o, { key: "Enter" });

    // (3) XONG ⇒ ĐỌC LẠI: chờ ĐÚNG thứ sắp đọc — chữ ĐÃ LƯU trong DOM (nguồn sự thật là máy chủ).
    await choPhanTu(
      container,
      ".ed__chu",
      (t) => t.includes("dòng hai (đã sửa)"),
      "dòng chưa hiện chữ ĐÃ LƯU sau khi ghi (thiếu bước ĐỌC LẠI bản ghi)",
    );
    await choPhuHop(
      container,
      '[data-i="1"]',
      (el) => !(el.getAttribute("class") ?? "").includes("is-editing"),
      "ghi xong phải THOÁT ô sửa",
    );

    // (4) BODY THẬT ở PHÍA MÁY CHỦ.
    assert.equal(dem.patch, 1, "một lần lưu ⇒ ĐÚNG MỘT PATCH");
    assert.equal(dem.patchTheoId[3], 1);
    const body = dem.patchBody;
    assert.ok(body !== null, "server phải đọc được body JSON của PATCH");
    const segments = body.segments;
    assert.ok(Array.isArray(segments), "body phải mang khoá `segments` là MẢNG");
    // (a) TOÀN BỘ mảng: backend TỪ CHỐI mảng rỗng (`min_length=1`), và gửi MỘT đoạn là XOÁ mọi
    //     đoạn khác. Mutation `D1-1` (gửi một đoạn) làm dòng này ĐỎ.
    assert.equal(segments.length, 4, "body phải chứa TOÀN BỘ 4 đoạn, không chỉ đoạn vừa sửa");
    assert.deepEqual(segments.map((s) => s.i), [0, 1, 2, 3]);
    // (b) ĐÚNG MỘT phần tử đổi `text`.
    const soDoi = segments.filter((s, k) => s.text !== goc[k].text).length;
    assert.equal(soDoi, 1, `đúng MỘT đoạn được đổi \`text\`; đo được ${soDoi}`);
    assert.equal(segments[1].text, "dòng hai (đã sửa)");
    // (c) CHỐNG MẤT DỮ LIỆU: mọi đoạn KHÔNG sửa đi lên NGUYÊN VẸN — kể cả `suspect`/`qa`/
    //     `events`/`words`/`t` của dòng 4. Mutation `D1-2` (dựng lại Segment thiếu trường) ĐỎ.
    assert.deepEqual(segments[0], goc[0]);
    assert.deepEqual(segments[2], goc[2]);
    assert.deepEqual(segments[3], goc[3], "dòng 4 phải giữ NGUYÊN `suspect`/`qa`/`events`/`words`/`t`");
    assert.equal(segments[3].suspect, true);
    assert.deepEqual(segments[3].qa, ["nhạc nền"]);
    assert.deepEqual(segments[3].events, ["bgm"]);
    assert.equal(segments[3].text, "dòng bốn", "chữ của dòng 4 KHÔNG được bị đụng tới");
    assert.equal(body.status, undefined, "PATCH sửa dòng KHÔNG được kèm `status`");
    // (d) Máy chủ THẬT SỰ đã ghi: version tăng đúng một, và bản ghi đọc lại mang chữ mới.
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, (dem.versionTruocPatch[3] ?? 0) + 1);
    assert.equal(TRANSCRIPT_CHI_TIET[3].segments[1].text, "dòng hai (đã sửa)");

    assert.deepEqual(tiengOn, [], "ghi mot dong khong duoc sinh tieng on console");
    unmount();
  });

  it("D1 HUỶ: `Esc` và NÚT HUỶ đều THOÁT ô sửa mà KHÔNG ghi gì (0 PATCH ở phía máy chủ)", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    // (1) `Esc`.
    const o = await moOSua(container, 1);
    fireEvent.change(o, { target: { value: "bản nháp bị bỏ" } });
    fireEvent.keyDown(o, { key: "Escape" });
    await choPhuHop(
      container,
      '[data-i="1"]',
      (el) => !(el.getAttribute("class") ?? "").includes("is-editing"),
      "`Esc` chưa thoát ô sửa",
    );
    assert.equal(chu(container, '[data-i="1"] .ed__chu'), "dòng hai", "`Esc` phải để dòng về ĐÚNG chữ cũ");

    // (2) NÚT HUỶ.
    const o2 = await moOSua(container, 1);
    fireEvent.change(o2, { target: { value: "bản nháp 2" } });
    fireEvent.click(phanTu(container, '[data-testid="huy-doan"]'));
    await choPhuHop(
      container,
      '[data-i="1"]',
      (el) => !(el.getAttribute("class") ?? "").includes("is-editing"),
      "nút huỷ chưa thoát ô sửa",
    );
    assert.equal(chu(container, '[data-i="1"] .ed__chu'), "dòng hai");

    // (3) KHÔNG GHI — đếm ở PHÍA MÁY CHỦ. Hai vế: (i) hai vòng microtask (không có `fetch` nào
    //     được GỬI RA đồng bộ), và (ii) một KHOẢNG LẶNG — cùng loại phép chờ mà ĐỐI CHỨNG DƯƠNG
    //     của bài nudge dùng để thấy một PATCH thật tới nơi. Giới hạn phải khai: đây là một
    //     khoảng lặng CÓ HIỆU CHUẨN, không phải một chứng minh tuyệt đối.
    await choHaiNhip();
    assert.equal(dem.patch, 0, "Esc/nút huỷ KHÔNG được ghi gì");
    await choNhip(150);
    assert.equal(dem.patch, 0, "Esc/nút huỷ KHÔNG được ghi gì (kể cả sau khoảng lặng)");
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, 1, "version KHÔNG được tăng khi huỷ");

    assert.deepEqual(tiengOn, [], "huy sua khong duoc sinh tieng on console");
    unmount();
  });

  it("D1 NUDGE: `Shift+→` đổi `end` +0,1 · `Shift+←` đổi `start` −0,1 · `Alt+→/←` đổi ±1 (so SỐ trên body máy chủ nhận) — TỚI ĐƯỢC ĐĨA", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    const goc = TRANSCRIPT_CHI_TIET_GOC[3].segments;
    await moOSua(container, 1);

    // Mốc NHÌN THẤY được của dòng đang sửa: nudge mà không thấy kết quả là một phép đo MÙ.
    assert.equal(chu(container, '[data-testid="moc-doan"]'), "0:02.00 → 0:04.00");

    // 🔴 BẢNG PHÍM ĐÃ ĐỔI Ở TASK 11 (ERRATA #44 mục 3): nudge = `Shift+←/→` (±0,1s) và `Alt+←/→`
    // (±1s) — ĐÚNG spec §5.1 dòng 300–301; còn `[`/`]` = **đặt mốc tại ĐẦU ĐỌC** (bài riêng
    // `T11 MỐC TẠI ĐẦU ĐỌC`). Bảy bài trong tệp này từng bấm `[`/`]` cho nudge: đúng BẢNG PHÍM CỦA
    // BRIEF D1, SAI NGUỒN SPEC. ⚠️ Phím vẫn phát Ở `document.body`, KHÔNG ở `textarea` (vòng sửa
    // I3): phím phát ra từ ô nhập bị bỏ qua, và hành vi đó có bài riêng `D1 GÕ TRONG Ô SỬA`.

    // (1) `Shift+→` ⇒ `end` +0,1.
    bamNudge("end");
    await choChu(container, "0:02.00 → 0:04.10");
    assert.equal(dem.patch, 1, "nudge `]` phải TỚI ĐƯỢC ĐĨA (đếm ở phía máy chủ)");
    const sau1 = dem.patchBody?.segments ?? [];
    assert.equal(sau1.length, 4, "nudge cũng phải gửi TOÀN BỘ segments");
    assert.ok(
      Math.abs(sau1[1].end - (goc[1].end + 0.1)) < 1e-9,
      `\`]\` phải đổi \`end\` +0,1; đo được ${sau1[1].end}`,
    );
    assert.equal(sau1[1].start, goc[1].start, "`]` KHÔNG được đụng tới `start`");
    assert.equal(sau1[1].text, goc[1].text, "nudge KHÔNG được đụng tới chữ");
    assert.deepEqual(sau1[3], goc[3], "nudge cũng phải giữ NGUYÊN mọi trường của dòng khác");

    // (2) `Shift+←` ⇒ `start` −0,1 — vế "KHÔNG CHỒNG LẤN": phép chờ DOM ở giữa bảo đảm lần ghi thứ
    //     nhất đã ĐỌC LẠI xong trước khi bấm lần hai. ⚠️ Vế CHỒNG LẤN (đúng ca đang hỏng ở C1)
    //     KHÔNG được ghim ở đây — xem bài `D1 CHỒNG LẤN` ngay dưới, bài đó bỏ phép chờ và làm
    //     chậm phản hồi PATCH. Tên/comment cũ của mục này khai nó ghim "đọc lại sau khi ghi" ở ca
    //     chồng lấn — lời khai đó MẠNH HƠN thứ bài ghim (I4 của review, ERRATA #44 mục 1).
    bamNudge("start");
    await choChu(container, "0:01.90 → 0:04.10");
    assert.equal(dem.patch, 2, "hai lần nudge ⇒ HAI lần ghi");
    const sau2 = dem.patchBody?.segments ?? [];
    assert.ok(
      Math.abs(sau2[1].start - (goc[1].start - 0.1)) < 1e-9,
      `\`Shift+←\` phải đổi \`start\` −0,1; đo được ${sau2[1].start}`,
    );
    assert.ok(
      Math.abs(sau2[1].end - (goc[1].end + 0.1)) < 1e-9,
      `nudge thứ hai (KHÔNG chồng lấn) phải GIỮ \`end\` = 4,1; đo được ${sau2[1].end}`,
    );

    // (3) `Alt+→` ⇒ `end` **+1** (KHÔNG phải +0,1): vế thứ hai của spec §5.1 dòng 301 — vế mà bảng
    //     phím cũ của sản phẩm KHÔNG có. Đây là chỗ một mutant "dùng chung bước 0,1" phải ĐỎ.
    bamNudge("end", 1);
    await choChu(container, "0:01.90 → 0:05.10");
    assert.equal(dem.patch, 3, "ba lần nudge ⇒ BA lần ghi");
    const sau3 = dem.patchBody?.segments ?? [];
    assert.ok(
      Math.abs(sau3[1].end - (goc[1].end + 0.1 + 1)) < 1e-9,
      `\`Alt+→\` phải đổi \`end\` +1 so với giá trị ĐÃ LƯU (4,1); đo được ${sau3[1].end}`,
    );
    assert.equal(sau3[1].start, sau2[1].start, "`Alt+→` KHÔNG được đụng tới `start`");

    // (4) `Alt+←` ⇒ `start` −1.
    bamNudge("start", 1);
    await choChu(container, "0:00.90 → 0:05.10");
    assert.equal(dem.patch, 4, "bốn lần nudge ⇒ BỐN lần ghi");
    const sau4 = dem.patchBody?.segments ?? [];
    assert.ok(
      Math.abs(sau4[1].start - (goc[1].start - 0.1 - 1)) < 1e-9,
      `\`Alt+←\` phải đổi \`start\` −1 so với giá trị ĐÃ LƯU (1,9); đo được ${sau4[1].start}`,
    );
    assert.deepEqual(sau4[3], goc[3], "nudge ±1 cũng phải giữ NGUYÊN mọi trường của dòng khác");

    assert.deepEqual(tiengOn, [], "nudge khong duoc sinh tieng on console");
    unmount();
  });

  it("D1 CHỒNG LẤN: hai lần ghi KHÔNG chờ nhau ⇒ lần SAU không XOÁ lần TRƯỚC (một hàng đợi cho MỌI đường ghi)", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    const goc = TRANSCRIPT_CHI_TIET_GOC[3].segments;
    await moOSua(container, 1);

    // ⚠️ ĐÂY LÀ BÀI GHIM `C1` (mất-cập-nhật ÂM THẦM) VÀ NÓ PHẢI **CHỒNG** ĐƯỢC HAI LẦN GHI.
    //
    // C1 không có triệu chứng: không exception, không 4xx, `version` vẫn tăng. Nó chỉ lộ ra khi
    // HAI lần ghi chồng lên nhau rồi so bản đã lưu. Khuôn TẤT ĐỊNH (đúng khuôn chẩn đoán của
    // review): làm CHẬM phản hồi PATCH (250 ms) + KHÔNG chờ gì giữa hai lần bấm.
    dem.patchTre = 250;
    const truoc = Date.now();
    bamNudge("end"); // lần ghi 1: end 4,0 → 4,1
    bamNudge("start"); // lần ghi 2: start 2,0 → 1,9 — KHÔNG chờ
    // CHỨNG NHÂN CHỒNG LẤN: lúc bấm phím thứ hai, CHƯA một phản hồi PATCH nào xong (đo đồng bộ ⇒
    // không phụ thuộc tốc độ máy). Không có dòng này thì bài có thể "xanh vì hai lần ghi KHÔNG
    // chồng nhau" — đúng thứ I4 của review cảnh báo.
    assert.equal(dem.patchXong, 0, "hai lần bấm phải CHỒNG LẤN: lần hai xảy ra khi lần một CHƯA xong");

    // Chờ tín hiệu Ở PHÍA MÁY CHỦ (hai body đã tới nơi) — KHÔNG chờ DOM, để mutant đỏ NGAY.
    await waitFor(
      () => {
        assert.equal(dem.patchBodies.length, 2, "hai lần bấm ⇒ HAI lần ghi (không lần nào bị bỏ)");
      },
      { timeout: 5000, interval: 20 },
    );

    // BODY PATCH THỨ NHẤT: `]` đã ghi `end` = 4,1.
    const b1 = JSON.parse(dem.patchBodies[0]) as { segments: Segment[] };
    assert.ok(
      Math.abs(b1.segments[1].end - (goc[1].end + 0.1)) < 1e-9,
      `body PATCH thứ nhất phải mang \`end\` = 4,1; đo được ${b1.segments[1].end}`,
    );
    // 🔴 BODY PATCH **THỨ HAI** — BẰNG CHỨNG CỦA `C1`. Nó PHẢI mang `end` = 4,1 (thay đổi của lần
    //    ghi TRƯỚC); mã cũ gửi `end` = 4,0 (bản ghi CŨ) và máy chủ XOÁ ÂM THẦM nudge thứ nhất.
    const b2 = JSON.parse(dem.patchBodies[1]) as { segments: Segment[] };
    assert.ok(
      Math.abs(b2.segments[1].end - (goc[1].end + 0.1)) < 1e-9,
      `body PATCH THỨ HAI phải GIỮ \`end\` = 4,1 (không được tính từ bản ghi CŨ); đo được ${b2.segments[1].end}`,
    );
    assert.ok(
      Math.abs(b2.segments[1].start - (goc[1].start - 0.1)) < 1e-9,
      `body PATCH thứ hai phải mang \`start\` = 1,9; đo được ${b2.segments[1].start}`,
    );
    // Và KHÔNG body nào được mang giá trị CŨ — khẳng định này không phụ thuộc THỨ TỰ hai request
    // tới nơi (một cuộc đua thật có thể đảo thứ tự; chỉ một phép so "mọi body" mới bắt được nó).
    const cacEnd = dem.patchBodies.map((raw) => (JSON.parse(raw) as { segments: Segment[] }).segments[1].end);
    assert.ok(
      cacEnd.every((e) => Math.abs(e - (goc[1].end + 0.1)) < 1e-9),
      `KHÔNG body nào được mang \`end\` CŨ (4,0) — mỗi lần ghi phải tính từ bản MỚI; đo được ${JSON.stringify(cacEnd)}`,
    );

    // Cuối cùng: ĐỌC LẠI thấy CẢ HAI thay đổi còn nguyên (và bản ghi trên "đĩa" của fixture cũng vậy).
    await choChu(container, "0:01.90 → 0:04.10");
    assert.equal(TRANSCRIPT_CHI_TIET[3].segments[1].start, goc[1].start - 0.1, "`start` 1,9 phải còn");
    assert.equal(TRANSCRIPT_CHI_TIET[3].segments[1].end, goc[1].end + 0.1, "`end` 4,1 KHÔNG được bị xoá");
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, 3, "hai lần ghi ⇒ version tăng ĐÚNG HAI lần");
    assert.ok(Date.now() - truoc >= 250, "phép đo phải THẬT SỰ đi qua độ trễ đã tiêm (không chồng giả)");
    // ⚠️ CHUNG NHAN HAI CHIEU (nghia vu ghim cua D1, ERRATA #45 muc 4): dong `patchXong === 0` o
    // TREN chi khang dinh MOT chieu, nen mot bo dem HANG 0 di qua no ma khong ai thay. Ve duoi day
    // buoc bo dem phai THAT SU dem.
    assert.ok(
      dem.patchXong >= 1,
      `chứng nhân chồng lấn \`dem.patchXong\` phải THẬT SỰ đếm (hai chiều); đo được ${dem.patchXong}`,
    );

    assert.deepEqual(tiengOn, [], "hai lan ghi chong lan khong duoc sinh tieng on console");
    unmount();
  });

  it("D1 GÕ TRONG Ô SỬA: gõ `[`/`]` như KÝ TỰ trong ô sửa ⇒ 0 request (đếm ở PHÍA MÁY CHỦ)", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    const goc = TRANSCRIPT_CHI_TIET_GOC[3].segments;
    await moOSua(container, 1);

    // ĐỐI CHỨNG DƯƠNG — CÙNG bài, CÙNG phím nudge (`Shift+→`), CÙNG server; chỉ khác NƠI phát
    // phím: bấm ở `document.body` (không phải ô nhập) ⇒ phím nóng PHẢI tới được đĩa. Và ĐỘ TRỄ THẬT
    // của nó được ĐO ⇒ khoảng lặng ở vế âm là khoảng lặng ĐÃ HIỆU CHUẨN (ERRATA #39 mục 1).
    const truocDuong = Date.now();
    bamNudge("end");
    await choChu(container, "0:02.00 → 0:04.10");
    const doTre = Date.now() - truocDuong;
    assert.equal(dem.patch, 1, "đối chứng dương: phím nudge NGOÀI ô nhập phải tới được đĩa");

    // VẾ ÂM (I3): gõ `[`/`]` NHƯ KÝ TỰ trong ô sửa — người dùng đang viết phụ đề, ví dụ
    // `[nhạc nền]`. Danh sách phím nóng ở `window` KHÔNG được cướp ký tự ⇒ **0 request**.
    // ⚠️ Trước vòng sửa, chính bài `D1 NUDGE` dispatch đúng hai phím này trên `textarea` rồi
    // khẳng định `dem.patch === 1`: nó ghi lại LỖI như thể là đặc tả ĐÚNG (ERRATA #44 mục 2).
    xoaDemGhi();
    const o = phanTu(container, '[data-testid="o-sua"]');
    fireEvent.keyDown(o, { key: "[" });
    fireEvent.keyDown(o, { key: "]" });
    await choHaiNhip();
    assert.equal(dem.patch, 0, "gõ `[`/`]` trong ô sửa KHÔNG được ghi gì");
    await choNhip(Math.max(doTre, 50) + 100);
    assert.equal(
      dem.patch,
      0,
      "gõ `[`/`]` trong ô sửa KHÔNG được ghi gì (sau khoảng lặng đã hiệu chuẩn)",
    );
    // Mốc đã lưu KHÔNG được nhích thêm 0,1s, và version chỉ tăng ĐÚNG MỘT lần (của đối chứng dương).
    assert.equal(chu(container, '[data-testid="moc-doan"]'), "0:02.00 → 0:04.10");
    assert.equal(TRANSCRIPT_CHI_TIET[3].segments[1].end, goc[1].end + 0.1);
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, 2, "version chỉ tăng ĐÚNG MỘT lần (của đối chứng dương)");

    assert.deepEqual(tiengOn, [], "go trong o sua khong duoc sinh tieng on console");
    unmount();
  });

  it("D1 NUDGE KHÔNG CÓ DÒNG ĐANG SỬA: `[`/`]` KHÔNG LÀM GÌ (0 request, đếm ở PHÍA MÁY CHỦ)", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    // ĐỐI CHỨNG DƯƠNG — CÙNG bài, CÙNG phím nudge, CÙNG server, chỉ khác "có dòng đang sửa": phím
    // `Shift+→` CÓ đường tới đĩa, và ĐỘ TRỄ THẬT của nó được ĐO ⇒ khoảng lặng ở vế âm là khoảng
    // lặng ĐÃ HIỆU CHUẨN (ERRATA #39 muc 1: mot phep do khong phan biet duoc "da sua" voi "tiem
    // nham cho" la phep do vo gia tri). ⚠️ Bấm ở `document.body` (KHÔNG ở `textarea`): từ vòng sửa
    // I3, phím phát ra từ ô nhập bị bỏ qua, còn phím ngoài ô mới là đường nudge thật.
    await moOSua(container, 1);
    const truocDuong = Date.now();
    bamNudge("end");
    await choChu(container, "0:02.00 → 0:04.10");
    const doTre = Date.now() - truocDuong;
    assert.equal(dem.patch, 1, "đối chứng dương: nudge khi ĐANG sửa phải tới được đĩa");

    // Thoát ô sửa ⇒ KHÔNG còn dòng nào đang sửa.
    fireEvent.keyDown(phanTu(container, '[data-testid="o-sua"]'), { key: "Escape" });
    await choPhuHop(
      container,
      '[data-i="1"]',
      (el) => !(el.getAttribute("class") ?? "").includes("is-editing"),
      "chưa thoát ô sửa",
    );

    // M5 cua review: reset PHAI du qua bon bo dem (`patchBody`/`versionTruocPatch` truoc day bi bo
    // sot ⇒ mot khang dinh sau moc nay doc body CU va XANH gia) — nay di qua MOT helper.
    xoaDemGhi();
    // CẢ HAI HỌ phím của màn Biên tập đều phải TRƠ khi không có dòng đang sửa: nudge (`Shift+←/→`)
    // và "đặt mốc tại đầu đọc" (`[`/`]`).
    bamNudge("end");
    bamNudge("start");
    fireEvent.keyDown(document.body, { key: "]" });
    fireEvent.keyDown(document.body, { key: "[" });
    await choHaiNhip();
    assert.equal(dem.patch, 0, "không có dòng đang sửa ⇒ KHÔNG được có request nào");
    await choNhip(Math.max(doTre, 50) + 100);
    assert.equal(
      dem.patch,
      0,
      "không có dòng đang sửa ⇒ KHÔNG được có request nào (sau khoảng lặng đã hiệu chuẩn)",
    );
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, 2, "version chỉ tăng ĐÚNG MỘT lần (của đối chứng dương)");

    assert.deepEqual(tiengOn, [], "nudge khi khong sua dong khong duoc sinh tieng on console");
    unmount();
  });

  it("D1 LỖI GHI: PATCH 422 ⇒ màn hiện NGUYÊN VĂN `ApiError.message`, GIỮ bản nháp, và ghi lại được", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    dem.patchLoi = true;

    const o = await moOSua(container, 1);
    fireEvent.change(o, { target: { value: "dòng hai (sửa)" } });
    fireEvent.keyDown(o, { key: "Enter" });
    assert.equal(
      await choPhanTu(
        container,
        '[data-testid="loi-ghi"]',
        (t) => t.length > 0,
        "không thấy câu báo lỗi ghi",
      ),
      "422: segment không hợp lệ: thiếu khoá 'text'",
      "câu lỗi phải là NGUYÊN VĂN `ApiError.message` (`<status>: <detail>`)",
    );
    // Lỗi KHÔNG được nuốt bản nháp: người dùng còn nguyên chữ để bấm lưu lại.
    assert.equal(
      (phanTu(container, '[data-testid="o-sua"]') as HTMLTextAreaElement).value,
      "dòng hai (sửa)",
      "ghi lỗi KHÔNG được xoá bản nháp",
    );
    assert.match(
      phanTu(container, '[data-i="1"]').getAttribute("class") ?? "",
      /is-editing/,
      "ghi lỗi thì VẪN ở trong ô sửa",
    );
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, 1, "PATCH lỗi KHÔNG được tăng version");

    // Bản ghi lại được sau khi lỗi qua đi — và câu lỗi BIẾN MẤT.
    dem.patchLoi = false;
    fireEvent.keyDown(phanTu(container, '[data-testid="o-sua"]'), { key: "Enter" });
    await choPhanTu(
      container,
      ".ed__chu",
      (t) => t.includes("dòng hai (sửa)"),
      "lần ghi lại không tới được đĩa",
    );
    await waitFor(
      () => {
        assert.equal(
          container.querySelectorAll('[data-testid="loi-ghi"]').length,
          0,
          "câu lỗi cũ phải BIẾN MẤT sau khi ghi được",
        );
      },
      { timeout: 5000, interval: 20 },
    );
    assert.equal(dem.patch, 2, "hai lần bấm lưu ⇒ HAI request (lần đầu 422, lần sau xong)");
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, 2);

    assert.deepEqual(tiengOn, [], "loi ghi khong duoc sinh tieng on console");
    unmount();
  });

  it("D1 LỖI THỜI: ghi xong ⇒ bản dịch của bản ghi thành `stale` (MÁY CHỦ tính) ⇒ màn NÓI RA", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    // TÍN HIỆU "danh sách bản dịch đã đọc xong": ba nút xuất có `href` (bản 31 `done`). Đọc câu
    // "lỗi thời" mà CHƯA biết danh sách đã về là một phép đo phụ thuộc thời điểm.
    await choPhuHop(
      container,
      ".tp__xuat",
      (el) => el.getAttribute("href") !== null,
      "bản dịch của bản ghi chưa nạp xong",
    );
    assert.equal(
      phanTu(container, ".tp__xuat").getAttribute("href"),
      "/api/export/4?format=srt&bilingual=0",
    );
    assert.equal(
      container.querySelectorAll('[data-testid="loi-thoi"]').length,
      0,
      "CHƯA sửa gì thì KHÔNG được nói 'lỗi thời'",
    );
    assert.equal(dem.patch, 0);

    const o = await moOSua(container, 1);
    fireEvent.change(o, { target: { value: "dòng hai (đã sửa)" } });
    fireEvent.keyDown(o, { key: "Enter" });

    const cau = await choPhanTu(
      container,
      '[data-testid="loi-thoi"]',
      (t) => t.length > 0,
      "màn không NÓI RA rằng bản dịch đã lỗi thời so với bản ghi",
    );
    assert.equal(cau, "bản dịch đã lỗi thời so với bản ghi");
    // Và cờ đó là SỰ THẬT CỦA MÁY CHỦ: version đã tăng, và `stale` được TÍNH LẠI ở lần đọc sau.
    assert.equal(dem.versionTruocPatch[3], 1);
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, 2);
    const banCuaBanGhi3 = TRANSLATIONS.filter((t) => t.id === 4)[0];
    assert.ok(banCuaBanGhi3 !== undefined, "fixture phải có bản dịch 4 của bản ghi 3");
    assert.equal(banCuaBanGhi3.transcript_version, 1, "bản dịch đã dịch từ version 1");
    assert.equal(staleCua(banCuaBanGhi3), true, "version hiện tại 2 > 1 ⇒ máy chủ nói LỖI THỜI");

    assert.deepEqual(tiengOn, [], "cau loi thoi khong duoc sinh tieng on console");
    unmount();
  });

  // ===========================================================================
  // TASK D2 — DUYET BAN GHI + HUY/CHAY LAI JOB
  //
  // Ba duong GHI MOI, ca ba di qua CUNG mot hang doi ghi cua D1 (`xepHangGhi`) — vi hai lan ghi
  // CHONG LAN la lop loi KHONG CO TRIEU CHUNG (ERRATA #44 muc 1), va D2 them BA thao tac vao cung
  // lop rui ro do. Moi thao tac co: (a) bai DI QUA DUONG THAT (dem o PHIA MAY CHU), (b) bai CHONG
  // TRUNG LAP (bam hai lan KHONG cho ⇒ DUNG MOT request), (c) DOC LAI nguon su that.
  // ===========================================================================

  it("D2 DUYET: bấm `duyệt` ⇒ ĐÚNG MỘT POST /approve, màn hiện `reviewed` (ĐỌC LẠI), và `version` KHÔNG tăng", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    const versionTruoc = TRANSCRIPT_CHI_TIET[3].version;

    // TRANG THAI BAN GHI la du lieu CUA MAY CHU: truoc khi bam no la `draft` (fixture).
    assert.equal(
      chu(container, '[data-testid="trang-thai-ban-ghi"]'),
      "trạng thái: draft",
      "trang thai ban ghi phai duoc NOI RA bang CHU (du lieu cua may chu)",
    );
    assert.equal(dem.approve, 0, "chua bam thi chua duoc co request nao");

    fireEvent.click(phanTu(container, '[data-testid="duyet-ban-ghi"]'));

    // TIN HIEU DUNG THU SAP DOC: `reviewed` trong DOM — no CHI den tu lan DOC LAI ban ghi.
    const sau = await choPhanTu(
      container,
      '[data-testid="trang-thai-ban-ghi"]',
      (t) => t.includes("reviewed"),
      "màn không hiện trạng thái `reviewed` sau khi duyệt (thiếu bước ĐỌC LẠI bản ghi)",
    );
    assert.equal(sau, "trạng thái: reviewed");
    assert.equal(dem.approve, 1, "bấm `duyệt` ⇒ ĐÚNG MỘT request approve ở PHÍA MÁY CHU");
    assert.deepEqual(dem.approveTheoId, { 3: 1 }, "request phải mang ĐÚNG id bản ghi đang mở");
    // 🔴 DUYET **KHONG** TANG `version` (khac `patchTranscript`): neu no tang thi moi ban dich cua
    // ban ghi thanh `stale` vi mot thao tac KHONG sua noi dung.
    assert.equal(
      TRANSCRIPT_CHI_TIET[3].version,
      versionTruoc,
      "duyệt KHÔNG được tăng `version` (hợp đồng `endpoints.approveTranscript`)",
    );
    assert.equal(TRANSCRIPT_CHI_TIET[3].status, "reviewed");

    assert.deepEqual(tiengOn, [], "duyet ban ghi khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 DUYET: nói ra `đang duyệt…` khi lời gọi đang bay, và LỖI NGUYÊN VĂN khi backend từ chối", async () => {
    dem.approveLoi = true;
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    // (1) BACKEND TU CHOI ⇒ hien NGUYEN VAN `ApiError.message` (`<status>: <detail>`).
    fireEvent.click(phanTu(container, '[data-testid="duyet-ban-ghi"]'));
    assert.equal(
      await choPhanTu(container, '[data-testid="loi-duyet"]', (t) => t.length > 0, "không thấy câu báo lỗi duyệt"),
      "404: transcript 3 không tồn tại",
      "câu lỗi phải là NGUYÊN VĂN `ApiError.message` của ĐƯỜNG LỖI DUY NHẤT mà route `approve` có "
      + "(`_require_transcript` ⇒ 404, `routes_transcripts.py`), không phải một câu tự nghĩ",
    );
    assert.equal(
      chu(container, '[data-testid="trang-thai-ban-ghi"]'),
      "trạng thái: draft",
      "duyệt LỖI thì trạng thái của máy chủ KHÔNG được đổi",
    );

    // (2) TRANG THAI "DANG DUYET" phai la CHU (§7: thong tin khong duoc chi nam o mau) — do bang
    //     mot phan hoi CHAM de cua so do la xac dinh, khong phai mot cuoc dua.
    dem.approveLoi = false;
    dem.approveTre = 200;
    fireEvent.click(phanTu(container, '[data-testid="duyet-ban-ghi"]'));
    assert.equal(
      chu(container, '[data-testid="dang-duyet"]'),
      "đang duyệt…",
      "trong lúc lời gọi đang bay, màn phải NÓI RA là đang duyệt",
    );
    await waitFor(
      () => {
        assert.equal(container.querySelectorAll('[data-testid="dang-duyet"]').length, 0, "câu `đang duyệt…` phải BIẾN MẤT khi xong");
      },
      { timeout: 5000, interval: 20 },
    );
    await choPhanTu(container, '[data-testid="trang-thai-ban-ghi"]', (t) => t.includes("reviewed"), "duyệt xong mà trạng thái không đổi");
    assert.equal(dem.approve, 2, "hai lần bấm ⇒ HAI request (lần đầu 422, lần sau xong)");

    assert.deepEqual(tiengOn, [], "loi duyet khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 DUYET CHỐNG TRÙNG LẶP: bấm hai lần KHÔNG chờ ⇒ ĐÚNG MỘT request ở PHÍA MÁY CHU", async () => {
    // Lam CHAM phan hoi: do la cach DUY NHAT khien hai lan bam CHAC CHAN chong lan (khuon C1 cua D1).
    dem.approveTre = 250;
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    const truoc = Date.now();
    const nut = phanTu(container, '[data-testid="duyet-ban-ghi"]');
    fireEvent.click(nut);
    fireEvent.click(nut); // KHONG cho
    assert.equal(dem.approveXong, 0, "hai lần bấm phải CHỒNG LẤN: lần hai xảy ra khi lần một CHƯA xong");
    await waitFor(
      () => {
        assert.equal(dem.approveXong, 1, "lời gọi duyệt chưa trả về");
      },
      { timeout: 5000, interval: 20 },
    );
    await choChu(container, "reviewed");
    // 🔴 KHANG DINH O PHIA MAY CHU: mot lan bam thu hai lot qua guard se thanh HAI request.
    assert.equal(dem.approve, 1, "bấm `duyệt` HAI lần KHÔNG chờ ⇒ chỉ được có MỘT request");
    assert.ok(Date.now() - truoc >= 250, "phép đo phải THẬT SỰ đi qua độ trễ đã tiêm (không chồng giả)");
    // CHỨNG NHÂN HAI CHIỀU: `approveXong` vừa phải BẰNG 0 lúc chồng lấn, vừa phải `>= 1` lúc xong —
    // một bộ đếm HẰNG 0 sẽ lọt qua vế thứ nhất mà không ai thấy.
    assert.equal(dem.approveXong, 1, "chứng nhân `approveXong` phải THẬT SỰ đếm (hai chiều)");

    assert.deepEqual(tiengOn, [], "bam duyet hai lan khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 HUY JOB `running`: câu chữ là 'đã YÊU CẦU huỷ' (KHÔNG phải 'đã dừng'), và TRẠNG THÁI vẫn do SSE quyết định", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await choPhanTu(container, '[data-testid="huy-job-7"]', () => true, "job `running` chưa có nút huỷ");
    const dong7 = (): string => chu(container, '[data-testid="job-7"]');
    assert.match(dong7(), /đang chạy/, "trước khi bấm, dòng job phải nói SỰ THẬT của máy chủ: đang chạy");

    fireEvent.click(phanTu(container, '[data-testid="huy-job-7"]'));
    // CAU CHU — va no phai nam CANH CHINH job do (khong phai mot thong bao chung cua vung).
    const tin = await choPhanTu(
      container,
      '[data-testid="huy-tin-7"]',
      (t) => t.length > 0,
      "không thấy câu nói ra yêu cầu huỷ cạnh job đang chạy",
    );
    assert.equal(tin, "đã yêu cầu huỷ", "job `running` chỉ được ĐẶT CỜ ⇒ phải nói 'đã YÊU CẦU huỷ'");
    assert.ok(
      !dong7().includes("đã dừng"),
      `giao diện KHÔNG được nói 'đã dừng' khi job mới chỉ được đặt cờ; đo được ${JSON.stringify(dong7())}`,
    );
    assert.ok(
      !dong7().includes("đã huỷ"),
      `job \`running\` bị đặt cờ KHÔNG phải là 'đã huỷ'; đo được ${JSON.stringify(dong7())}`,
    );
    assert.match(dong7(), /đang chạy/, "trạng thái job VẪN là `running` — nguồn sự thật là máy chủ");
    assert.equal(dem.cancel, 1, "bấm huỷ ⇒ ĐÚNG MỘT request ở phía máy chủ");
    assert.deepEqual(dem.cancelTheoId, { 7: 1 });
    // ⚠️ FIXTURE PHAI KHOP DIEU HE THONG THAT SU LAM: huy job `running` CHI dat co.
    assert.equal(JOBS.find((j) => j.id === 7)?.state, "running", "fixture: job `running` KHÔNG bị đổi trạng thái");
    assert.equal(JOBS.find((j) => j.id === 7)?.cancel_requested, true, "fixture: chỉ ĐẶT CỜ `cancel_requested`");

    // ⚠️ SU KIEN SSE MOI DOI DUOC TRANG THAI (`useJobStream` la NGUON DUY NHAT): mot ban tu sua
    // `Map` job tai cho se lam dong nay XANH GIA (no da noi 'da huy' TRUOC khi may chu noi).
    emit(sse({ id: 7, state: "cancelled", progress: 0.35, phase: "asr:faster-whisper-large", error: null, log_tail: "" }));
    await choPhuHop(
      container,
      '[data-testid="job-7"]',
      (el) => (el.textContent ?? "").includes("đã huỷ"),
      "sự kiện SSE không tới được dòng job",
    );
    assert.equal(
      container.querySelectorAll('[data-testid="huy-tin-7"]').length,
      0,
      "máy chủ đã XÁC NHẬN (`cancelled`) ⇒ câu 'đã yêu cầu huỷ' phải BIẾN MẤT",
    );

    assert.deepEqual(tiengOn, [], "huy job running khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 HUY JOB `queued`: request đi ra, và giao diện KHÔNG tự đổi trạng thái (SSE mới là nguồn)", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await choPhanTu(container, '[data-testid="huy-job-6"]', () => true, "job `queued` chưa có nút huỷ");
    assert.match(chu(container, '[data-testid="job-6"]'), /chờ gom lô/);

    fireEvent.click(phanTu(container, '[data-testid="huy-job-6"]'));
    const tin = await choPhanTu(
      container,
      '[data-testid="huy-tin-6"]',
      (t) => t.length > 0,
      "không thấy câu nói ra yêu cầu huỷ cạnh job đang chờ",
    );
    // Job `queued` bi huy NGAY o backend — nhung CLIENT khong co bang chung nao ngoai SU KIEN, nen
    // cau no noi ra van la cau ve YEU CAU, khong phai mot loi khang dinh ve trang thai.
    assert.equal(tin, "đã yêu cầu huỷ", "câu chữ phải nói ra YÊU CẦU, không khẳng định trạng thái");
    assert.equal(dem.cancel, 1, "bấm huỷ ⇒ ĐÚNG MỘT request ở phía máy chủ");
    assert.match(
      chu(container, '[data-testid="job-6"]'),
      /chờ gom lô/,
      "chưa có sự kiện SSE thì trạng thái HIỂN THỊ không được tự đổi (không tự sửa map job)",
    );
    assert.equal(JOBS.find((j) => j.id === 6)?.state, "cancelled", "fixture: job `queued` bị huỷ NGAY");

    assert.deepEqual(tiengOn, [], "huy job queued khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 CHAY LAI: nút CHỈ có ở `failed`/`interrupted`; bấm ⇒ POST /retry; 409 ⇒ NGUYÊN VĂN câu backend", async () => {
    themJobLoi(21, "asr", "failed", 2);
    themJobLoi(22, "translate", "interrupted", 2);
    const { container, unmount } = render(taoPhanTu(App));
    await choPhanTu(container, '[data-testid="lai-job-21"]', () => true, "job `failed` chưa có nút chạy lại");
    await choPhanTu(container, '[data-testid="lai-job-22"]', () => true, "job `interrupted` chưa có nút chạy lại");

    // (c) KHONG co nut o trang thai khac: khong de nguoi dung bam roi an 409 (nhung 409 VAN phai
    //     duoc xu ly — trang thai client thay co the CU, xem ngay duoi).
    for (const [chon, moTa] of [
      ['[data-testid="lai-job-3"]', "job `done`"],
      ['[data-testid="lai-job-6"]', "job `queued`"],
      ['[data-testid="lai-job-7"]', "job `running`"],
      ['[data-testid="huy-job-3"]', "job `done` (nút huỷ)"],
      ['[data-testid="huy-job-21"]', "job `failed` (nút huỷ)"],
    ] as const) {
      assert.equal(container.querySelectorAll(chon).length, 0, `${moTa} KHÔNG được có nút này`);
    }

    // (1) 409: MAY CHU tu choi vi trang thai THAT cua no khong chay lai duoc. Day la ca "trang thai
    //     phia client da CU" (brief §3.4): UI dang hien `failed` (nen nut chay lai CO mat) nhung
    //     ban ghi phia may chu da o `done`. ⚠️ Fixture CU ban 409 cho chinh mot job `failed` — ca
    //     BAT KHA, vi `failed` NAM TRONG `RETRYABLE_STATES` (`job_state.py`) nen backend khong bao
    //     gio tra 409 cho no.
    dem.retry409 = true;
    const job21 = JOBS.find((j) => j.id === 21);
    assert.ok(job21 !== undefined, "fixture: job 21 phải có trong ảnh chụp /api/jobs");
    job21.state = "done";
    fireEvent.click(phanTu(container, '[data-testid="lai-job-21"]'));
    assert.equal(
      await choPhanTu(container, '[data-testid="loi-lenh-21"]', (t) => t.length > 0, "không thấy câu lỗi chạy lại"),
      "409: chỉ chạy lại được job ở trạng thái ['failed', 'interrupted']",
      "409 phải hiện NGUYÊN VĂN câu của backend (`routes_jobs.retry_job`), không phải một câu tự nghĩ",
    );

    // (2) Chay lai THANH CONG: request di ra, cau loi CU bien mat, va trang thai HIEN THI van la
    //     su that cua lan doc truoc (chua co su kien SSE nao).
    dem.retry409 = false;
    job21.state = "failed"; // MAY CHU chap nhan chay lai trang thai nay
    fireEvent.click(phanTu(container, '[data-testid="lai-job-21"]'));
    await waitFor(
      () => {
        assert.equal(dem.retry, 2, "lần chạy lại thứ hai chưa tới máy chủ");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.deepEqual(dem.retryTheoId, { 21: 2 }, "hai lần bấm ⇒ hai request, ĐÚNG job 21");
    await choPhuHop(
      container,
      '[data-testid="job-21"]',
      () => container.querySelectorAll('[data-testid="loi-lenh-21"]').length === 0,
      "câu lỗi cũ phải BIẾN MẤT khi lệnh mới được gửi",
    );
    assert.equal(JOBS.find((j) => j.id === 21)?.state, "queued", "fixture: chạy lại ⇒ job về `queued`");

    assert.deepEqual(tiengOn, [], "chay lai job khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 FIXTURE RETRY: guard 409 CHỈ cho trạng thái KHÔNG chạy lại được (trạng thái ca + câu chữ, hai vế)", async () => {
    // 🔴 VÌ SAO BÀI NÀY TỒN TẠI (`M-1` của re-review vòng sửa 1): bỏ RIÊNG guard điều kiện của
    // fixture (`dem.retry409 && job.state !== "failed" && job.state !== "interrupted"`) cho **0
    // bài đỏ** — vì bài `D2 CHAY LAI` tự đặt `job21.state = "done"` nên nó KHÔNG BAO GIỜ đi vào
    // nhánh guard. Hàng `F3-RETRY-409-FAILED` trong bảng mutation của vòng trước vì thế chỉ đỏ
    // được nhờ vế CÂU CHỮ. Bài này ghim TÁCH hai vế, và vế (1) là vế chưa từng có gì làm nó sai
    // được: trạng thái THẬT chạy lại được ⇒ fixture phải đi đường 200.
    themJobLoi(21, "asr", "failed", 2);
    const { container, unmount } = render(taoPhanTu(App));
    await choPhanTu(container, '[data-testid="lai-job-21"]', () => true, "job `failed` chưa có nút chạy lại");

    // (1) VẾ "TRẠNG THÁI CA": `retry409` BẬT, nhưng trạng thái THẬT của job NẰM TRONG
    //     `RETRYABLE_STATES` (`failed`) ⇒ backend thật KHÔNG BAO GIỜ trả 409 cho nó. Tín hiệu
    //     DƯƠNG là MÃ HTTP fixture đã trả (200), không phải sự VẮNG MẶT của một câu lỗi.
    dem.retry409 = true;
    assert.equal(
      JOBS.find((j) => j.id === 21)?.state,
      "failed",
      "fixture: job 21 phải ĐANG ở trạng thái CHẠY LẠI ĐƯỢC — nếu không thì vế này đo sai ca",
    );
    fireEvent.click(phanTu(container, '[data-testid="lai-job-21"]'));
    await waitFor(
      () => {
        assert.equal(dem.retryXong, 1, "lời gọi chạy lại chưa trả về");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.equal(
      dem.retryTrangThai,
      200,
      "cờ `retry409` KHÔNG được đè lên một trạng thái CHẠY LẠI ĐƯỢC: fixture phải trả 200 "
      + "(`RETRYABLE_STATES` = failed/interrupted là bất biến của backend thật)",
    );
    assert.equal(
      container.querySelectorAll('[data-testid="loi-lenh-21"]').length,
      0,
      "chạy lại được ⇒ giao diện KHÔNG được hiện câu 409 (chưa có lỗi nào để nói)",
    );

    // (2) VẾ "CÂU CHỮ" + VẾ "TRẠNG THÁI CA" của nhánh 409: trạng thái THẬT không chạy lại được
    //     (`done`) trong khi client còn thấy `failed` (trạng thái client CŨ) ⇒ ĐÚNG 409, ĐÚNG câu
    //     NGUYÊN VĂN của `routes_jobs.retry_job`.
    const job21 = JOBS.find((j) => j.id === 21);
    assert.ok(job21 !== undefined, "fixture: job 21 phải có trong ảnh chụp /api/jobs");
    job21.state = "done";
    fireEvent.click(phanTu(container, '[data-testid="lai-job-21"]'));
    assert.equal(
      await choPhanTu(
        container,
        '[data-testid="loi-lenh-21"]',
        (t) => t.length > 0,
        "không thấy câu lỗi chạy lại",
      ),
      "409: chỉ chạy lại được job ở trạng thái ['failed', 'interrupted']",
      "409 phải hiện NGUYÊN VĂN câu của backend (`routes_jobs.retry_job`)",
    );
    assert.equal(dem.retryTrangThai, 409, "trạng thái THẬT không chạy lại được ⇒ fixture phải trả 409");

    assert.deepEqual(tiengOn, [], "ghim guard cua fixture retry khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 CHAY LAI CHỐNG TRÙNG LẶP: bấm hai lần KHÔNG chờ ⇒ ĐÚNG MỘT request ở PHÍA MÁY CHU", async () => {
    themJobLoi(21, "asr", "failed", 2);
    dem.retryTre = 250;
    const { container, unmount } = render(taoPhanTu(App));
    await choPhanTu(container, '[data-testid="lai-job-21"]', () => true, "job `failed` chưa có nút chạy lại");

    const truoc = Date.now();
    const nut = phanTu(container, '[data-testid="lai-job-21"]');
    fireEvent.click(nut);
    fireEvent.click(nut); // KHONG cho
    assert.equal(dem.retryXong, 0, "hai lần bấm phải CHỒNG LẤN: lần hai xảy ra khi lần một CHƯA xong");
    await waitFor(
      () => {
        assert.equal(dem.retryXong, 1, "lời gọi chạy lại chưa trả về");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.equal(dem.retry, 1, "bấm `chạy lại` HAI lần KHÔNG chờ ⇒ chỉ được có MỘT request");
    assert.ok(Date.now() - truoc >= 250, "phép đo phải THẬT SỰ đi qua độ trễ đã tiêm (không chồng giả)");
    assert.equal(dem.retryXong, 1, "chứng nhân `retryXong` phải THẬT SỰ đếm (hai chiều)");

    assert.deepEqual(tiengOn, [], "bam chay lai hai lan khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 HUY CHỐNG TRÙNG LẶP: bấm hai lần KHÔNG chờ ⇒ ĐÚNG MỘT request ở PHÍA MÁY CHU", async () => {
    dem.cancelTre = 250;
    const { container, unmount } = render(taoPhanTu(App));
    await choPhanTu(container, '[data-testid="huy-job-7"]', () => true, "job `running` chưa có nút huỷ");

    const truoc = Date.now();
    const nut = phanTu(container, '[data-testid="huy-job-7"]');
    fireEvent.click(nut);
    fireEvent.click(nut); // KHÔNG chờ
    assert.equal(dem.cancelXong, 0, "hai lần bấm phải CHỒNG LẤN: lần hai xảy ra khi lần một CHƯA xong");
    await waitFor(
      () => {
        assert.equal(dem.cancelXong, 1, "lời gọi huỷ chưa trả về");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.equal(dem.cancel, 1, "bấm `huỷ` HAI lần KHÔNG chờ ⇒ chỉ được có MỘT request");
    assert.ok(Date.now() - truoc >= 250, "phép đo phải THẬT SỰ đi qua độ trễ đã tiêm (không chồng giả)");
    assert.equal(dem.cancelXong, 1, "chứng nhân `cancelXong` phải THẬT SỰ đếm (hai chiều)");

    assert.deepEqual(tiengOn, [], "bam huy hai lan khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 DUYET: câu lỗi duyệt của bản ghi CŨ không sống qua một lần ĐỔI KÊNH", async () => {
    // CÙNG lớp lỗi mà vòng sửa W3 đã đóng cho `loiTao` (ERRATA #36 muc 4): một state của bản ghi CŨ
    // sống qua lần đổi kênh thì câu 422 của nó hiện cạnh thanh trên của bản ghi MỚI.
    dem.approveLoi = true;
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    fireEvent.click(phanTu(container, '[data-testid="duyet-ban-ghi"]'));
    await choPhanTu(container, '[data-testid="loi-duyet"]', (t) => t.length > 0, "không thấy câu lỗi duyệt");

    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    assert.equal(
      container.querySelectorAll('[data-testid="loi-duyet"]').length,
      0,
      "câu lỗi duyệt của bản ghi CŨ phải BIẾN MẤT khi đổi kênh",
    );
    assert.deepEqual(tiengOn, [], "doi kenh khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 MỘT HÀNG ĐỢI GHI: `duyệt` và `huỷ` bấm trong lúc một PATCH đang bay ⇒ tới máy chủ SAU khi PATCH xong", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    await choPhanTu(container, '[data-testid="huy-job-7"]', () => true, "job `running` chưa có nút huỷ");

    // Lam CHAM phan hoi PATCH ⇒ cua so chong lan la TAT DINH, khong phu thuoc toc do may.
    dem.patchTre = 250;
    const o = await moOSua(container, 1);
    fireEvent.change(o, { target: { value: "dòng hai (đã sửa)" } });
    fireEvent.keyDown(o, { key: "Enter" }); // PATCH đang bay
    fireEvent.click(phanTu(container, '[data-testid="huy-job-7"]')); // KHÔNG chờ
    fireEvent.click(phanTu(container, '[data-testid="duyet-ban-ghi"]')); // KHÔNG chờ
    assert.equal(dem.patchXong, 0, "PATCH phải còn ĐANG BAY lúc hai lệnh kia được bấm (không chồng giả)");

    await waitFor(
      () => {
        assert.equal(dem.cancel, 1, "lệnh huỷ chưa tới máy chủ");
        assert.equal(dem.approve, 1, "lệnh duyệt chưa tới máy chủ");
      },
      { timeout: 5000, interval: 20 },
    );
    // 🔴 BANG CHUNG DI QUA HANG DOI GHI CUA D1: luc request TOI NOI, PATCH da TRA XONG. Mot lenh
    // di THANG (khong xep hang) se toi noi khi `patchXong` con 0.
    assert.ok(
      dem.cancelSauPatch >= 1,
      `huỷ tới máy chủ khi PATCH CHƯA xong (patchXong=${dem.cancelSauPatch}) ⇒ nó KHÔNG đi qua hàng đợi ghi`,
    );
    assert.ok(
      dem.approveSauPatch >= 1,
      `duyệt tới máy chủ khi PATCH CHƯA xong (patchXong=${dem.approveSauPatch}) ⇒ nó KHÔNG đi qua hàng đợi ghi`,
    );
    assert.equal(dem.patch, 1, "một lần lưu ⇒ ĐÚNG MỘT PATCH");
    assert.deepEqual(tiengOn, [], "ba lenh ghi chong lan khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 HUY RỒI CHẠY LẠI: câu 'đã yêu cầu huỷ' KHÔNG sống lại trên một LƯỢT CHẠY MỚI", async () => {
    // DO DUOC TRUOC (`I3` cua review D2): `daYeuCauHuy` chi duoc GHI, KHONG BAO GIO duoc DON, va
    // phep render so `get(id) === job.state`. Trinh tu duoi day HOP LE tung buoc:
    //   job `running` + huy ⇒ worker NEM LOI ⇒ `failed` ⇒ bam `chay lai` ⇒ `running`
    //   ⇒ cau "đã yêu cầu huỷ" cua luot CU hien lai tren mot luot chay MOI TINH.
    const { container, unmount } = render(taoPhanTu(App));
    await choPhanTu(container, '[data-testid="huy-job-7"]', () => true, "job `running` chưa có nút huỷ");

    fireEvent.click(phanTu(container, '[data-testid="huy-job-7"]'));
    await choPhanTu(
      container,
      '[data-testid="huy-tin-7"]',
      (t) => t.length > 0,
      "không thấy câu 'đã yêu cầu huỷ'",
    );

    // (2) worker NEM LOI ⇒ FAILED. `worker.py` bo qua co huy o nhanh `except` (phep kiem co chi toi
    //     duoc o duong THANH CONG) ⇒ day la mot trang thai CO THAT, khong phai mot gia dinh.
    emit(sse({
      id: 7, state: "failed", progress: 0.4, phase: "asr:faster-whisper-large",
      error: "model lỗi", log_tail: "",
    }));
    await choPhanTu(container, '[data-testid="lai-job-7"]', () => true, "job `failed` chưa có nút chạy lại");
    assert.equal(
      container.querySelectorAll('[data-testid="huy-tin-7"]').length,
      0,
      "job đổi trạng thái ⇒ câu 'đã yêu cầu huỷ' phải BIẾN MẤT (máy chủ đã trả lời bằng một sự kiện)",
    );

    // (3) CHAY LAI ⇒ MOT LUOT CHAY MOI. Phia CLIENT van thay `failed` (su kien SSE chua toi), tuc
    //     loi hua CU khong con thuoc ve bat cu trang thai nao dang hien.
    fireEvent.click(phanTu(container, '[data-testid="lai-job-7"]'));
    await waitFor(
      () => {
        assert.equal(dem.retry, 1, "lệnh chạy lại chưa tới máy chủ");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.equal(
      container.querySelectorAll('[data-testid="huy-tin-7"]').length,
      0,
      "chạy lại ⇒ lời hứa của lượt CŨ không còn thuộc về lượt MỚI (client còn thấy `failed`)",
    );

    // (4) Luot chay MOI bat dau THAT SU: SSE dua job ve `running` — DUNG trạng thái LÚC GỬI.
    emit(sse({
      id: 7, state: "running", progress: 0, phase: "asr:faster-whisper-large",
      error: null, log_tail: "",
    }));
    await choPhuHop(
      container,
      '[data-testid="job-7"]',
      (el) => (el.textContent ?? "").includes("đang chạy"),
      "sự kiện SSE không tới được dòng job",
    );
    assert.equal(
      container.querySelectorAll('[data-testid="huy-tin-7"]').length,
      0,
      "LƯỢT CHẠY MỚI ở ĐÚNG trạng thái lúc gửi ⇒ giao diện KHÔNG được nói 'đã yêu cầu huỷ' (chưa ai yêu cầu lượt này)",
    );

    assert.deepEqual(tiengOn, [], "huy roi chay lai khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 HUY RỒI CHẠY LẠI (MỤC GHI SAU KHI JOB ĐÃ RỜI): lời hứa 'đã yêu cầu huỷ' không được sống sót", async () => {
    // 🔴 VÌ SAO BÀI NÀY TỒN TẠI (`I-2` của re-review vòng sửa 1): bài ngay trên chỉ chạy trình tự
    // nơi mục `daYeuCauHuy` được GHI khi job VẪN ở trạng thái lúc gửi — và phép dọn cũ là
    // EDGE-TRIGGERED theo `[jobs]`, nên nó chỉ loại mục khi `jobs` đổi. Nếu mục được ghi SAU khi
    // job đã rời trạng thái đó thì KHÔNG lượt dọn nào chạy nữa: mục nằm lại, và khi job quay lại
    // ĐÚNG trạng thái lúc gửi thì câu SAI hiện lại. Trình tự dưới đây là trình tự của re-review
    // (`F1-INSERT-AFTER-LEAVE`: lệnh huỷ trả về SAU khi `failed` đã tới), nay là bài ghim thường trực.
    dem.cancelTre = 400;
    const { container, unmount } = render(taoPhanTu(App));
    await choPhanTu(container, '[data-testid="huy-job-7"]', () => true, "job `running` chưa có nút huỷ");

    fireEvent.click(phanTu(container, '[data-testid="huy-job-7"]'));
    assert.equal(dem.cancelXong, 0, "phép đo chỉ có nghĩa khi lệnh huỷ CÒN BAY (mục chưa được ghi)");

    // (1) worker NÉM LỖI ⇒ `FAILED` tới TRƯỚC khi lệnh huỷ trả về (`worker.py` bỏ qua cờ huỷ ở
    //     nhánh `except`). Đây là trạng thái CÓ THẬT, không phải một giả định của bài test.
    //     ⚠️ ĐIỀU KIỆN TIÊN QUYẾT: kênh SSE đã MỞ — đo ở PHÍA MÁY CHỦ (`dem.stream`); phát một
    //     sự kiện lên một kênh chưa mở là một sự kiện MẤT, và bài test sẽ đỏ vì một lý do khác.
    await waitFor(
      () => {
        assert.ok(dem.stream >= 1, `chưa mở /api/jobs/stream; đo được ${dem.stream}`);
      },
      { timeout: 5000, interval: 20 },
    );
    await waitFor(
      () => {
        assert.equal(
          dem.cancelXong,
          0,
          "lệnh huỷ đã trả về TRƯỚC khi `failed` tới ⇒ bài này mất đúng thứ tự nó cần đo",
        );
        if (container.querySelector('[data-testid="lai-job-7"]') === null) {
          emit(sse({
            id: 7, state: "failed", progress: 0.4, phase: "asr:faster-whisper-large",
            error: "model lỗi", log_tail: "",
          }));
        }
        assert.ok(
          container.querySelector('[data-testid="lai-job-7"]') !== null,
          "job `failed` chưa có nút chạy lại",
        );
      },
      { timeout: 2000, interval: 20 },
    );

    // (2) MỤC ĐƯỢC GHI **SAU** KHI JOB ĐÃ RỜI trạng thái lúc gửi. Tín hiệu DƯƠNG rằng client đã
    //     xử lý xong lệnh huỷ: lệnh `chạy lại` bị guard `dangLenh` giữ trong suốt lúc huỷ CÒN BAY,
    //     nên nó chỉ tới được máy chủ SAU khi `try/finally` của lệnh huỷ chạy — đúng lượt ghi đã
    //     đặt mục này. Vòng `waitFor` bấm lại cho tới khi request thật sự đi ra.
    await waitFor(
      () => {
        if (dem.retry === 0) fireEvent.click(phanTu(container, '[data-testid="lai-job-7"]'));
        assert.equal(dem.cancel, 1, "lệnh huỷ chưa tới máy chủ ⇒ mục `daYeuCauHuy` chưa được ghi");
        assert.equal(dem.retry, 1, "lệnh chạy lại chưa tới được máy chủ (guard `dangLenh` vẫn giữ?)");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.equal(
      container.querySelectorAll('[data-testid="huy-tin-7"]').length,
      0,
      "job đang ở `failed` ⇒ KHÔNG được nói 'đã yêu cầu huỷ' (đúng ngay lúc này)",
    );

    // (3) LƯỢT CHẠY MỚI quay lại ĐÚNG trạng thái LÚC GỬI: mục CŨ không được khiến câu sai hiện lại.
    emit(sse({
      id: 7, state: "running", progress: 0, phase: "asr:faster-whisper-large",
      error: null, log_tail: "",
    }));
    await choPhuHop(
      container,
      '[data-testid="job-7"]',
      (el) => (el.textContent ?? "").includes("đang chạy"),
      "sự kiện SSE không tới được dòng job",
    );
    assert.equal(
      container.querySelectorAll('[data-testid="huy-tin-7"]').length,
      0,
      "LƯỢT CHẠY MỚI ở ĐÚNG trạng thái lúc gửi ⇒ giao diện KHÔNG được nói 'đã yêu cầu huỷ' (chưa ai yêu cầu lượt này)",
    );

    assert.deepEqual(tiengOn, [], "muc ghi sau khi job da roi khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 DUYET: trạng thái 'đang duyệt…' thuộc về BẢN GHI + KÊNH của nó (đổi kênh ⇒ không rò sang bản ghi khác)", async () => {
    // DO DUOC TRUOC (`I3b` cua review D2): `dangDuyet` la mot co GLOBAL va KHONG duoc don khi doi
    // kenh ⇒ thanh tren cua kenh MOI noi "đang duyệt…" trong khi chua ai duyet ban ghi do.
    dem.approveTre = 600; // loi goi CON BAY khi doi kenh (du de phép đo dưới đây không phải cuộc đua)
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container); // kenh HAI, ban ghi #3

    fireEvent.click(phanTu(container, '[data-testid="duyet-ban-ghi"]'));
    assert.equal(
      chu(container, '[data-testid="dang-duyet"]'),
      "đang duyệt…",
      "trong lúc lời gọi đang bay, màn phải NÓI RA là đang duyệt",
    );

    // (1) DOI KENH trong luc lenh CON BAY: cau do thuoc ve ban ghi + kenh CU.
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    assert.equal(dem.approveXong, 0, "phép đo chỉ có nghĩa khi lời gọi CÒN BAY (không chồng giả)");
    assert.equal(
      container.querySelectorAll('[data-testid="dang-duyet"]').length,
      0,
      "thanh trên của kênh MỚI KHÔNG được nói 'đang duyệt…' — chưa ai duyệt bản ghi này",
    );

    // (2) BAN GHI MOI co lenh RIENG: co "dang bay" cua ban ghi CU khong duoc NUOT lan bam nay.
    //     ⚠️ Do tre cua lenh MOI nho (150ms): phep do o (3) phai roi DUNG vao cua so "lenh CU da
    //     xong, lenh MOI con bay", va chang `waitFor` duoi day (interval 20ms) du de bat trung no.
    dem.approveTre = 150;
    fireEvent.click(phanTu(container, '[data-testid="duyet-ban-ghi"]'));
    await waitFor(
      () => {
        assert.equal(dem.approve, 2, "lệnh duyệt của bản ghi MỚI không tới được máy chủ");
      },
      { timeout: 5000, interval: 20 },
    );
    // (3) `finally` cua lenh CU khong duoc XOA co cua lenh MOI (dang bay): lenh moi chi xong khi
    //     PHIA MAY CHU da tra loi no, khong phai khi lenh CU ket thuc.
    assert.equal(
      dem.approveXong,
      1,
      "phép đo (3) phải nằm ĐÚNG cửa sổ: lệnh CŨ đã xong (1) và lệnh MỚI còn BAY (chưa thành 2)",
    );
    assert.equal(
      container.querySelectorAll('[data-testid="dang-duyet"]').length,
      1,
      "lệnh CŨ xong KHÔNG được xoá câu 'đang duyệt…' của lệnh MỚI đang bay",
    );
    assert.deepEqual(dem.approveTheoId, { 3: 1, 5: 1 }, "mỗi bản ghi ĐÚNG MỘT request, đúng id của nó");

    await waitFor(
      () => {
        assert.equal(dem.approveXong, 2, "lời gọi duyệt thứ hai chưa trả về");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.deepEqual(tiengOn, [], "doi kenh giua luc duyet khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 DUYET: đích của lệnh chốt LÚC GỬI — xếp hàng rồi ĐỔI KÊNH vẫn duyệt ĐÚNG bản ghi đã bấm", async () => {
    // DO DUOC TRUOC (`A6` cua review D2): mutant `APPROVE-LATE-BIND` (doc ban ghi LUC THI HANH)
    // cho **0 bai do** ⇒ khong bai nao phan biet duoc "chot dich luc GUI" voi "doc lai luc thi hanh".
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container); // kenh HAI, ban ghi #3
    await choPhanTu(container, '[data-testid="huy-job-7"]', () => true, "job `running` chưa có nút huỷ");

    // Mot PATCH CHAM dang bay ⇒ lenh `duyet` duoc XEP HANG, tuc no thi hanh SAU khi ban ghi da doi.
    dem.patchTre = 250;
    const o = await moOSua(container, 1);
    fireEvent.change(o, { target: { value: "dòng hai (đã sửa)" } });
    fireEvent.keyDown(o, { key: "Enter" });
    fireEvent.click(phanTu(container, '[data-testid="duyet-ban-ghi"]'));
    assert.equal(dem.patchXong, 0, "PATCH phải còn ĐANG BAY lúc lệnh duyệt được bấm");
    assert.equal(dem.approve, 0, "lệnh duyệt KHÔNG được gửi trước khi PATCH xong (nó xếp hàng)");

    // DOI KENH trong lúc lệnh còn XẾP HÀNG: ban ghi dang mo bay gio la #5 (kenh MOT), khong phai #3.
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    await waitFor(
      () => {
        assert.equal(dem.approve, 1, "lệnh duyệt chưa tới máy chủ");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.deepEqual(
      dem.approveTheoId,
      { 3: 1 },
      "lệnh duyệt phải tác động bản ghi ĐÃ BẤM (#3), không phải bản ghi đang mở SAU khi đổi kênh (#5)",
    );
    await waitFor(
      () => {
        assert.equal(dem.approveXong, 1, "lời gọi duyệt chưa trả về");
      },
      { timeout: 5000, interval: 20 },
    );
    assert.deepEqual(tiengOn, [], "doi kenh trong luc lenh xep hang khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 HÌNH THỨC: `.lenh*` (duyệt · huỷ · chạy lại · câu trạng thái) có LUẬT trong app.css VA có THAT trong DOM", async () => {
    // ⚠️ VI SAO BAI NAY TON TAI: mot `className` trong TSX KHONG ve gi ca. Lop loi nay da tai phat
    // NAM lan (`X7`, luat mo coi khi doi ten luat, `flex` ghi de, `P3`, va `G8`). Bai nay ghim
    // QUAN HE HAI CHIEU (ERRATA #34 muc 1 / #43 muc 2), KHONG ghim danh sach ten lop nguyen van.
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    themJobLoi(21, "asr", "failed", 2);
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    await choPhanTu(container, '[data-testid="huy-job-7"]', () => true, "job `running` chưa có nút huỷ");
    await choPhanTu(container, '[data-testid="lai-job-21"]', () => true, "job `failed` chưa có nút chạy lại");

    const lopTrongDom = new Set<string>();
    const gom = (): void => {
      for (const el of container.querySelectorAll("*")) {
        for (const ten of el.classList) if (/^lenh/.test(ten)) lopTrongDom.add(ten);
      }
    };
    gom(); // nút `duyệt` (EditScreen) + nút `huỷ` (job running) + nút `chạy lại` (job failed)
    // Câu "đã yêu cầu huỷ" (`.lenh__tin`) chỉ có mặt SAU khi bấm ⇒ phải bấm rồi gom lại.
    fireEvent.click(phanTu(container, '[data-testid="huy-job-7"]'));
    await choPhanTu(container, '[data-testid="huy-tin-7"]', (t) => t.length > 0, "không thấy câu 'đã yêu cầu huỷ'");
    gom();

    const trongCss = new Set<string>();
    for (const m of appCss.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/\.(lenh[a-z0-9_-]*)/g)) {
      trongCss.add(m[1] ?? "");
    }
    trongCss.delete("");
    assert.ok(trongCss.size >= 4, `phải đọc được các lớp \`lenh*\` từ app.css; đo được ${trongCss.size}`);
    assert.ok(lopTrongDom.size >= 4, `phải thu được các lớp \`lenh*\` từ DOM; đo được ${lopTrongDom.size}`);

    const moCoi = [...trongCss].filter((t) => !lopTrongDom.has(t)).sort();
    assert.deepEqual(
      moCoi,
      [],
      `LUẬT MỒ CÔI: ${JSON.stringify(moCoi)} — luật này không lớp nào trong DOM mang, tức nó KHÔNG `
      + `tạo kiểu cho thứ gì. Lớp có trong DOM: ${JSON.stringify([...lopTrongDom].sort())}`,
    );
    const voLuat = [...lopTrongDom].filter((t) => !trongCss.has(t)).sort();
    assert.deepEqual(
      voLuat,
      [],
      `LỚP KHÔNG CÓ LUẬT: ${JSON.stringify(voLuat)} — lớp này nằm trong DOM mà app.css không tạo kiểu `
      + `cho nó. Luật có trong app.css: ${JSON.stringify([...trongCss].sort())}`,
    );

    // KHAI BAO THANG CUOC (khong phai "co o dau do"): thanh tren cua man Bien tap la FLEX, va cau
    // trang thai la mot KHOI chu rieng (khong nam cung dong voi nut).
    assert.match(appCss, /\.ed__thanh \{[^}]*display: flex/, "`.ed__thanh` phải là một HÀNG flex");
    assert.match(appCss, /\.lenh__tin \{[^}]*display: block/, "câu trạng thái phải là một KHỐI chữ riêng");

    assert.deepEqual(tiengOn, [], "hinh thuc D2 khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 NHÃN TAB BẢN DỊCH: đảo thứ tự MẢNG ⇒ nhãn KHÔNG đổi (không đánh số theo vị trí)", async () => {
    // DO DUOC TRUOC (anh chup that, ERRATA #41 muc 3a): nhan cu la `bản dịch {k + 1} · {engine}`,
    // tuc DANH TINH CUA MOT BAN DICH la VI TRI CUA NO TRONG MANG — them/bot mot ban dich la moi nhan
    // sau doi so. Nhan BEN VUNG phai lay tu chinh du lieu cua hang (`id`, `engine`, `status`).
    const nhanCua = (container: HTMLElement): Map<string, string> =>
      new Map(
        [...container.querySelectorAll('[data-testid^="pick-"]')].map(
          (el) => [el.getAttribute("data-testid") ?? "", el.textContent ?? ""] as const,
        ),
      );

    const mot = render(taoPhanTu(App));
    await toiDoiChieu(mot.container, 2);
    const truoc = nhanCua(mot.container);
    mot.unmount();
    const nhan11 = truoc.get("pick-11") ?? "";
    assert.notEqual(nhan11, "", "phải đọc được nhãn của bản dịch 11");
    assert.notEqual(nhan11, truoc.get("pick-12"), "hai bản dịch khác nhau phải có nhãn KHÁC nhau");
    assert.ok(nhan11.includes("qwen2.5-7b"), `nhãn phải nói ra ENGINE; đo được ${JSON.stringify(nhan11)}`);

    // DAO MANG: route trả về ĐÚNG thứ tự của mảng fixture, nên nhãn cũ (theo vị trí) sẽ đổi hết.
    TRANSLATIONS = [...TRANSLATIONS].reverse();
    const hai = render(taoPhanTu(App));
    await toiDoiChieu(hai.container, 2);
    const sau = nhanCua(hai.container);
    assert.equal(sau.get("pick-11"), nhan11, "đảo thứ tự mảng KHÔNG được đổi nhãn của bản dịch 11");
    assert.equal(sau.get("pick-12"), truoc.get("pick-12"), "đảo thứ tự mảng KHÔNG được đổi nhãn của bản dịch 12");
    assert.deepEqual([...sau.keys()].sort(), [...truoc.keys()].sort(), "tập bản dịch không đổi");

    assert.deepEqual(tiengOn, [], "nhan tab ban dich khong duoc sinh tieng on console");
    hai.unmount();
  });

  // ===========================================================================
  // NGHIA VU GHIM CUA D1 (ERRATA #45 muc 4) — ba MENH DE MOI cua vong sua D1 khong co gi lam
  // chung sai duoc. Ba bai duoi day BUOC chung phai co.
  // ===========================================================================

  it("D1 TIÊU ĐIỂM TRONG Ô NHẬP: phím phát ra NGOÀI ô (`target`=body) mà tiêu điểm Ở TRONG ô ⇒ 0 request", async () => {
    // ⚠️ NUA MENH DE BI THIEU: bai cu chi phat phim TREN `textarea` ⇒ no chi cham nua
    // `suKien.target` cua guard. Bo nua `document.activeElement` ⇒ 0 bai do (do duoc o re-review).
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    const goc = TRANSCRIPT_CHI_TIET_GOC[3].segments;
    const o = await moOSua(container, 1);

    // DOI CHUNG DUONG (da hieu chuan): tieu diem KHONG o o nhap ⇒ cung phim, cung server, toi duoc
    // dia; do tre THAT cua no duoc DO ⇒ khoang lang o ve am la khoang lang DA HIEU CHUAN.
    o.blur();
    assert.notEqual(document.activeElement, o, "đối chứng dương phải có tiêu điểm NGOÀI ô nhập");
    const truocDuong = Date.now();
    bamNudge("end");
    await choChu(container, "0:02.00 → 0:04.10");
    const doTre = Date.now() - truocDuong;
    assert.equal(dem.patch, 1, "đối chứng dương: tiêu điểm ngoài ô ⇒ phím nudge tới được đĩa");

    // VE DUOC GHIM: tieu diem O TRONG o nhap, nhung phim duoc PHAT RA tu NGOAI o (`target` = body).
    xoaDemGhi();
    o.focus();
    assert.equal(document.activeElement, o, "ca này chỉ có nghĩa khi tiêu điểm Ở TRONG ô nhập");
    bamNudge("end");
    await choHaiNhip();
    assert.equal(dem.patch, 0, "tiêu điểm trong ô nhập ⇒ KHÔNG được ghi gì");
    await choNhip(Math.max(doTre, 50) + 100);
    assert.equal(
      dem.patch,
      0,
      "tiêu điểm trong ô nhập ⇒ KHÔNG được ghi gì (sau khoảng lặng đã hiệu chuẩn)",
    );
    assert.equal(chu(container, '[data-testid="moc-doan"]'), "0:02.00 → 0:04.10", "mốc đã lưu KHÔNG được nhích thêm");
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, 2, "version chỉ tăng ĐÚNG MỘT lần (của đối chứng dương)");
    assert.equal(TRANSCRIPT_CHI_TIET[3].segments[1].end, goc[1].end + 0.1);

    assert.deepEqual(tiengOn, [], "tieu diem trong o nhap khong duoc sinh tieng on console");
    unmount();
  });

  it("D1 NỀN MỚI HƠN: bản ghi MÁY CHỦ mới hơn nền ⇒ lần ghi sau tính từ MÁY CHỦ (không kéo bản CŨ về)", async () => {
    // ⚠️ VE `vuaGhi.version > hienTai.version` CUA NEN: no chi quan sat duoc khi CO mot ban ghi may
    // chu MOI HON ban ma chinh duong ghi nay vua gui. Do la ca ma `dem.nguoiGhiKhac` dung ra.
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    const goc = TRANSCRIPT_CHI_TIET_GOC[3].segments;
    await moOSua(container, 1);

    // Nguoi ghi KHAC ha canh giua phan hoi PATCH va lan DOC LAI ⇒ may chu thanh version 3 voi chu
    // cua doan 0 da doi.
    dem.nguoiGhiKhac = true;
    const truoc = Date.now();
    bamNudge("end"); // lần ghi 1: end 4,0 → 4,1
    // TIN HIEU: DOM doc lai thay CHU CUA NGUOI KHAC ⇒ `transcript.data` da la ban `version` 3.
    await choPhuHop(
      container,
      '[data-i="0"] .ed__chu',
      (el) => (el.textContent ?? "").includes("người khác sửa"),
      "chưa đọc lại được bản ghi MỚI HƠN của máy chủ",
    );
    assert.equal(TRANSCRIPT_CHI_TIET[3].version, 3, "fixture: người ghi khác phải đẩy version lên 3");
    assert.equal(dem.patchXong, 1, "lần ghi thứ nhất phải đã xong");
    assert.equal(chu(container, '[data-testid="moc-doan"]'), "0:02.00 → 0:04.10", "nudge thứ nhất phải còn trong DOM");

    // LAN GHI THU HAI phai tinh tu ban MOI (version 3) ⇒ giu nguyen thay doi cua nguoi khac.
    bamNudge("start"); // lần ghi 2: start 2,0 → 1,9
    await waitFor(
      () => {
        assert.equal(dem.patchBodies.length, 2, "hai lần bấm ⇒ HAI lần ghi (không lần nào bị bỏ)");
      },
      { timeout: 5000, interval: 20 },
    );
    const b2 = JSON.parse(dem.patchBodies[1]) as { segments: Segment[] };
    assert.equal(
      b2.segments[0].text,
      "bản kênh hai (người khác sửa)",
      "lần ghi sau phải tính từ bản MỚI HƠN của máy chủ — gửi bản CŨ là XOÁ ÂM THẦM thay đổi của người khác",
    );
    assert.ok(
      Math.abs(b2.segments[1].start - (goc[1].start - 0.1)) < 1e-9,
      `lần ghi sau vẫn phải mang thay đổi của chính nó; đo được ${b2.segments[1].start}`,
    );
    assert.ok(Math.abs(b2.segments[1].end - (goc[1].end + 0.1)) < 1e-9);
    assert.ok(Date.now() - truoc >= 0);

    assert.deepEqual(tiengOn, [], "nen moi hon khong duoc sinh tieng on console");
    unmount();
  });

  it("D1 NỀN MỚI HƠN (CỬA SỔ CHƯA GẮN LẠI): phím thứ hai rơi ĐÚNG lúc DOM đã mới mà effect chưa chạy lại ⇒ vẫn phải gửi nền MỚI", async () => {
    // 🔴 VÌ SAO BÀI NÀY TỒN TẠI (`I-1` của re-review vòng sửa 1): bài ngay trên chờ bằng `waitFor`
    // (macrotask) nên nó chỉ đỏ khi lượt flush passive effect của React tới MUỘN hơn vòng poll —
    // đo được 1/33 lượt. Trong cửa sổ đó listener CŨ còn gắn, `nudgeDoan` đọc `transcript.data`
    // của closure CŨ ⇒ gửi bản CŨ và XOÁ ÂM THẦM thay đổi của người khác (họ C1). Đây KHÔNG phải
    // flake: mutant `D1-DEPS-NUDGE-STALE` cho ĐỎ đúng bài ngay trên.
    // Bài này ĐIỀU KHIỂN THỨ TỰ bằng `MutationObserver`: callback của nó là MICROTASK, chạy ngay
    // sau lượt commit DOM của React và TRƯỚC lượt flush passive effect ⇒ cửa sổ trở thành TẤT ĐỊNH.
    // ⚠️ Bài ghim chỉ đọc HÀNH VI (bàn phím ở `window` + body PATCH ở máy chủ + chữ trong DOM),
    // KHÔNG đọc cấu trúc của listener ⇒ Task 11 đổi nó thành `useShortcuts` vẫn giữ nguyên giá trị.
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    const goc = TRANSCRIPT_CHI_TIET_GOC[3].segments;
    await moOSua(container, 1);

    // Người ghi KHÁC hạ cánh ngay sau phản hồi PATCH: máy chủ lên `version` và đổi chữ của đoạn 0.
    dem.nguoiGhiKhac = true;
    // (2) ĐIỀU KHIỂN THỨ TỰ bằng `MutationObserver`: callback của nó là MICROTASK, chạy ngay sau lượt
    //     commit DOM của React (lượt đọc lại đã trả bản `version` mới) và TRƯỚC lượt flush passive
    //     effect — đúng cái cửa sổ mà `waitFor` chỉ bắt được 1/33 lượt. Phím thứ hai được bấm NGAY
    //     TRONG callback đó.
    //     ⚠️ `window.MutationObserver` chứ KHÔNG phải global trần: `test/dom.ts` chỉ cài một DANH
    //     SÁCH global cố định (không có `MutationObserver`) — đo được bằng
    //     `ReferenceError: MutationObserver is not defined`.
    const daBamLanHai = { value: false };
    const theoDoi = new window.MutationObserver(() => {
      if (daBamLanHai.value) return;
      const dong = container.querySelector('[data-i="0"]');
      if (dong === null || !(dong.textContent ?? "").includes("người khác sửa")) return;
      daBamLanHai.value = true;
      bamNudge("start"); // lần ghi 2: start 2,0 → 1,9
    });
    try {
      theoDoi.observe(container, { subtree: true, childList: true, characterData: true });
      bamNudge("end"); // lần ghi 1: end 4,0 → 4,1
      await waitFor(
        () => {
          assert.equal(dem.patchBodies.length, 2, "phím thứ hai không tới được đường ghi");
        },
        { timeout: 5000, interval: 20 },
      );
      assert.ok(
        daBamLanHai.value,
        "phép đo chỉ có nghĩa khi phím thứ hai được bấm TỪ TRONG cửa sổ DOM-đã-mới",
      );
      const b2 = JSON.parse(dem.patchBodies[1]) as { segments: Segment[] };
      assert.equal(
        b2.segments[0].text,
        "bản kênh hai (người khác sửa)",
        "phím thứ hai rơi trong cửa sổ effect chưa gắn lại ⇒ nền vẫn phải là ảnh chụp "
        + "MỚI NHẤT của máy chủ; gửi bản CŨ ở đây là XOÁ ÂM THẦM thay đổi của người khác",
      );
      assert.ok(
        Math.abs(b2.segments[1].start - (goc[1].start - 0.1)) < 1e-9,
        `lần ghi sau vẫn phải mang thay đổi của chính nó; đo được ${b2.segments[1].start}`,
      );
      assert.ok(Math.abs(b2.segments[1].end - (goc[1].end + 0.1)) < 1e-9);
    } finally {
      theoDoi.disconnect();
    }

    // (3) DỌN NHỮNG LƯỢT CÒN BAY **TRONG BÀI**. Tín hiệu DƯƠNG: `moc-doan` chỉ đổi khi lượt ĐỌC LẠI
    //     sau lần ghi thứ hai đã hạ cánh (`transcript.data` là sự thật của máy chủ) — đếm ở PHÍA
    //     MÁY CHỦ (`dem.patchXong`) là quá sớm: con số đó lên ngay khi fixture trả lời, TRƯỚC khi
    //     client xử lý phản hồi.
    //     ⚠️ VÌ SAO PHẢI DỌN: lượt commit cuối để lại một callback của scheduler (`setImmediate`) cho
    //     `flushPassiveEffects`, và callback đó đọc `window.event` (`react-dom-client.development.js`
    //     dòng 19555). Nếu nó chạy SAU `teardownDom` thì `window` đã bị xoá ⇒ đo được khi chạy RIÊNG
    //     tệp này: `ReferenceError: window is not defined` + EXIT=1 dù 57/57 bài xanh (lượt chạy
    //     chung không lộ, vì `after` cấp tệp bị node:test kéo lên gốc lượt chạy).
    await choChu(container, "0:01.90 → 0:04.10");
    // Hai nhịp `waitFor` (mỗi nhịp còn tự drain một `setTimeout(0)`) ⇒ cả pha timers lẫn pha check
    // của event loop chạy xong TRONG bài. Dùng `waitFor` chứ không `await setTimeout` trần: RTL tắt
    // `IS_REACT_ACT_ENVIRONMENT` trong lượt chờ, nên một update hạ cánh muộn KHÔNG sinh tiếng on.
    await waitFor(() => { assert.ok(true, "nhịp dọn 1"); }, { timeout: 2000, interval: 10 });
    await waitFor(() => { assert.ok(true, "nhịp dọn 2"); }, { timeout: 2000, interval: 10 });

    assert.deepEqual(tiengOn, [], "cua so chua gan lai khong duoc sinh tieng on console");
    unmount();
  });

  // ===========================================================================
  // TASK 11 — BÀN PHÍM §5.1 + BẢNG PHÍM §11.4 + CHUỖI §12.5 ĐI BẰNG BÀN PHÍM.
  //
  // ⚠️ Bàn phím KHÔNG phải thứ được dựng từ số 0 ở task này: `App.tsx` đã có một listener ở
  // `window` nhận `[`/`]` và gọi `nudgeDoan`, đã được đo bằng bàn phím THẬT trong Chrome thật
  // (ERRATA #46 mục 5). Việc của task là HỢP NHẤT nó thành `src/keys/useShortcuts.ts` (MỘT
  // listener ở `document`, guard HAI vế giữ nguyên) và TRẢ NỢ ÁNH XẠ: `[`/`]` = đặt mốc tại đầu
  // đọc, nudge = `Shift+←/→` (±0,1s) và `Alt+←/→` (±1s) — ERRATA #44 mục 3.
  // ===========================================================================

  it("T11 MỐC TẠI ĐẦU ĐỌC: `[`/`]` đặt mốc = `media.currentTime` (KHÔNG phải nudge) — và đọc đầu đọc LÚC BẤM", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    const goc = TRANSCRIPT_CHI_TIET_GOC[3].segments;
    await moOSua(container, 1);

    // (1) `]` ⇒ mốc `end` = ĐẦU ĐỌC 3,2. Ba vế phủ định đi kèm là thứ phân biệt "đặt mốc" với
    //     "nudge": không phải `end + 0,1`, và `start` không bị đụng tới.
    datDauDoc(container, 3.2);
    fireEvent.keyDown(document.body, { key: "]" });
    await choChu(container, "0:02.00 → 0:03.20");
    assert.equal(dem.patch, 1, "`]` phải TỚI ĐƯỢC ĐĨA (đếm ở phía máy chủ)");
    const sau1 = dem.patchBody?.segments ?? [];
    assert.ok(
      Math.abs(sau1[1].end - 3.2) < 1e-9,
      `\`]\` phải đặt \`end\` = ĐẦU ĐỌC 3,2; đo được ${sau1[1].end}`,
    );
    assert.ok(
      Math.abs(sau1[1].end - (goc[1].end + 0.1)) > 1e-9,
      "`]` KHÔNG được hành xử như nudge (+0,1) — đó là bảng phím của brief D1, đã bị bác",
    );
    assert.equal(sau1[1].start, goc[1].start, "`]` KHÔNG được đụng tới `start`");
    assert.deepEqual(sau1[3], goc[3], "đặt mốc cũng phải giữ NGUYÊN mọi trường của dòng khác");

    // (2) `[` ⇒ mốc `start` = đầu đọc 1,5, và mốc `end` đã đặt (3,2) phải CÒN.
    datDauDoc(container, 1.5);
    fireEvent.keyDown(document.body, { key: "[" });
    await choChu(container, "0:01.50 → 0:03.20");
    assert.equal(dem.patch, 2, "hai lần đặt mốc ⇒ HAI lần ghi");
    const sau2 = dem.patchBody?.segments ?? [];
    assert.ok(Math.abs(sau2[1].start - 1.5) < 1e-9, `\`[\` phải đặt \`start\` = 1,5; đo được ${sau2[1].start}`);
    assert.ok(Math.abs(sau2[1].end - 3.2) < 1e-9, `mốc \`end\` đã đặt phải CÒN; đo được ${sau2[1].end}`);

    // (3) ĐẦU ĐỌC ĐƯỢC ĐỌC **LÚC BẤM**, KHÔNG phải lúc hàng đợi thi hành. Đây là ca mà một bản cài
    //     "đọc `currentTime` trong việc đã xếp hàng" sẽ sai: PATCH đầu đang BAY (250 ms), đầu đọc
    //     chạy tiếp ngay sau cú bấm, nên mốc phải là 2,5 chứ không phải 4,4.
    dem.patchTre = 250;
    datDauDoc(container, 2.5);
    fireEvent.keyDown(document.body, { key: "]" });
    datDauDoc(container, 4.4);
    await choChu(container, "0:01.50 → 0:02.50");
    assert.equal(dem.patch, 3, "ba lần đặt mốc ⇒ BA lần ghi");
    const sau3 = dem.patchBody?.segments ?? [];
    assert.ok(
      Math.abs(sau3[1].end - 2.5) < 1e-9,
      `mốc phải là ĐẦU ĐỌC LÚC BẤM (2,5), không phải vị trí sau đó (4,4); đo được ${sau3[1].end}`,
    );

    assert.deepEqual(tiengOn, [], "dat moc tai dau doc khong duoc sinh tieng on console");
    unmount();
  });

  it("T11 NGHE LẠI SAU NUDGE: mốc mới ⇒ TUA + `play()`, dừng sau 300 ms; ĐANG PHÁT thì KHÔNG cắt; KHÔNG nudge thì KHÔNG nghe lại (I-3)", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    await moOSua(container, 1);
    const media = phanTu(container, "audio.tp__media") as HTMLAudioElement;
    xoaDemGhi();
    xoaDemMedia();

    // (1) MẶT TRÁI, đo TRƯỚC vế dương: `]` = **ĐẶT MỐC TẠI ĐẦU ĐỌC**, KHÔNG phải nudge (spec §5.1
    //     dòng 296 vs §5.2 dòng 309) ⇒ KHÔNG được nghe lại. Một bản cài "mọi lượt ghi đều nghe lại"
    //     đi qua được hết các vế dưới và ĐỔ ở đây.
    datDauDoc(container, 3.2);
    fireEvent.keyDown(document.body, { key: "]" });
    await choChu(container, "0:02.00 → 0:03.20");
    assert.equal(dem.patch, 1, "`]` phải TỚI ĐƯỢC ĐĨA (đếm ở phía máy chủ)");
    assert.equal(dem.play, 0, "`]` KHÔNG được nghe lại (spec gán việc nghe lại cho NUDGE)");
    assert.equal(dem.pause, 0, "`]` KHÔNG được mở/đóng một cửa sổ nghe nào");
    assert.ok(media.getAttribute("data-nghe-lai") === null, "không cửa sổ nghe nào được mở");

    // (2) NUDGE ⇒ TUA tới MỐC MỚI rồi PHÁT. Chờ theo TÍN HIỆU (`data-nghe-lai` MỞ), KHÔNG theo đồng
    //     hồ: `bamNudge` chỉ xếp hàng ghi, nên yêu cầu nghe lại tới SAU khi máy chủ nhận.
    xoaDemGhi();
    xoaDemMedia();
    bamNudge("end", 0.1);
    await choPhuHop(
      container,
      "audio.tp__media",
      (el) => el.getAttribute("data-nghe-lai") === "1",
      "một cú nudge phải MỞ cửa sổ nghe lại",
    );
    // 🔴 MỐC MỞ, đọc NGAY SAU tín hiệu DOM vừa thấy (không phải một `sleep`): nó dùng để GHIM ĐỘ
    //    DÀI cửa sổ ở vế (3). Đây là `#47` mục 3 — lỗ hổng ở cấp **GIÁ TRỊ**: đổi `NGHE_LAI_MS`
    //    300 → 4000 (tôi tự đo lại trên cây TRƯỚC lượt này: `292/290/2`, **0 bài đỏ**, lượt chạy
    //    dài 31,1 s so với 23,3 s của nền — cửa sổ THẬT SỰ dài 4 s mà không bài nào bắt) cho 0 đỏ,
    //    vì bài cũ chỉ hỏi *"cuối cùng thì cửa sổ có ĐÓNG không"* ⇒ nó ghim SỰ TỒN TẠI của lời gọi,
    //    không ghim GIÁ TRỊ.
    const tMo = Date.now();
    assert.equal(dem.play, 1, "nudge phải YÊU CẦU `play()` (đếm được vì `play()` bị bịt để ĐẾM)");
    const mocMoi = 3.3; // = 3,2 (mốc `]` vừa đặt ở vế (1)) + 0,1 (bước nudge)
    assert.ok(
      Math.abs(media.currentTime - mocMoi) < 1e-9,
      `đầu đọc phải TUA tới MỐC MỚI ${mocMoi}; đo được ${media.currentTime}`,
    );

    // (3) CỬA SỔ ĐÓNG sau 300 ms. TÍN HIỆU là thuộc tính biến mất; deadline của `waitFor` chỉ là
    //     TRẦN (ERRATA #35 mục 2: một `sleep` có điều kiện thoát là hàm của ĐỒNG HỒ thì luôn đúng).
    await choPhuHop(
      container,
      "audio.tp__media",
      (el) => el.getAttribute("data-nghe-lai") === null,
      "hết `NGHE_LAI_MS` cửa sổ nghe lại phải ĐÓNG",
    );
    // 🔴 GHIM ĐỘ DÀI (`#47` mục 3): `t_close − t_open` phải nằm giữa HAI TRẦN, và KHÔNG đọc hằng
    //    số của sản phẩm (đọc hằng số chỉ ghim lại chính lời khai, không ghim giá trị). Điều kiện
    //    thoát của phép đo là hai TÍN HIỆU DOM ở trên; đồng hồ chỉ làm CỰC ĐẠI/CỰC TIỂU, nên đây
    //    KHÔNG phải một `sleep` (ERRATA #35/#38/#39 — đã cắn bốn lần).
    //    ⚠️ SÀN 150 ms là RỘNG, không phải con số của spec: `tMo` được đọc SAU khi tín hiệu mở được
    //    phát hiện (độ trễ phát hiện ≤ một nhịp `interval` của `waitFor`), nên phép đo có thể NHỎ
    //    hơn 300 ms một chút. Sàn chỉ để bắt một cửa sổ NGẮN HƠN HẲN (mutant 30 ms: đo được ≤ ~50 ms,
    //    hoặc tín hiệu mở không bao giờ thấy ⇒ ĐỎ).
    const tDong = Date.now();
    const doDai = tDong - tMo;
    assert.ok(
      doDai >= 150 && doDai <= 1500,
      `cửa sổ nghe lại phải dài ~300 ms (spec UI §5.2 dòng 309); `
      + `đo được ${doDai} ms — ngoài khoảng [150, 1500]`,
    );
    assert.equal(dem.pause, 1, "hết cửa sổ phải `pause()` — nghe một đoạn rồi DỪNG");
    assert.ok(
      Math.abs(media.currentTime - mocMoi) < 1e-9,
      "đóng cửa sổ KHÔNG được đổi vị trí đã tua",
    );
    // Mốc mới đã tới được ĐĨA và hiện ra trong DOM. Khẳng định này để SAU phép đo độ dài: một phép
    // chờ vì chữ khác không được phép làm nhiễu khoảng thời gian đang đo.
    await choChu(container, "0:02.00 → 0:03.30");

    // (4) ĐANG PHÁT ⇒ nudge chỉ TUA, KHÔNG CẮT việc đang nghe. ⚠️ Khẳng định PHỦ ĐỊNH ("không
    //     `pause()` nào") chỉ có nghĩa khi có một MỐC THỜI GIAN để đứng lên ⇒ chờ tín hiệu cửa sổ
    //     ĐÓNG trước, rồi mới đếm. Đây chính là chỗ một bản cài "luôn `pause()` sau 300 ms" ĐỎ.
    fireEvent.keyDown(document.body, { key: " " });
    await choPhuHop(
      container,
      ".tp__phat",
      (el) => el.getAttribute("aria-pressed") === "true",
      "`Space` phải phát",
    );
    xoaDemMedia();
    bamNudge("end", 0.1);
    await choPhuHop(
      container,
      "audio.tp__media",
      (el) => el.getAttribute("data-nghe-lai") === "1",
      "đang phát: cửa sổ nghe lại vẫn phải MỞ (tua tới mốc mới)",
    );
    await choPhuHop(
      container,
      "audio.tp__media",
      (el) => el.getAttribute("data-nghe-lai") === null,
      "đang phát: cửa sổ nghe lại vẫn phải ĐÓNG (mốc thời gian để khẳng định vế phủ định)",
    );
    assert.equal(dem.pause, 0, "ĐANG PHÁT ⇒ nudge KHÔNG được `pause()` (không cắt việc đang nghe)");
    assert.equal(dem.play, 1, "ĐANG PHÁT ⇒ chỉ có `play()` của chính cửa sổ nghe lại");
    assert.equal(
      phanTu(container, ".tp__phat").getAttribute("aria-pressed"),
      "true",
      "nút phát vẫn phải nói ĐÚNG trạng thái đang phát sau một cú nudge",
    );
    assert.ok(
      Math.abs(media.currentTime - 3.4) < 1e-9,
      `đang phát: đầu đọc vẫn phải ở MỐC MỚI 3,4; đo được ${media.currentTime}`,
    );

    assert.deepEqual(tiengOn, [], "nghe lai sau nudge khong duoc sinh tieng on console");
    unmount();
  });

  it("T11 PHÁT / TẠM DỪNG: `Space` đổi `aria-pressed` false → true → false (vế THỨ HAI mới là vế ghim)", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    // Có kênh đang chọn ⇒ thanh transport có nguồn, tức đường `play()`/`pause()` được thi hành THẬT.
    await toiBienTapBonDoan(container);
    assert.equal(
      phanTu(container, ".tp__phat").getAttribute("aria-pressed"),
      "false",
      "chưa phát thì `aria-pressed` phải là false",
    );

    fireEvent.keyDown(document.body, { key: " " });
    await choPhuHop(
      container,
      ".tp__phat",
      (el) => el.getAttribute("aria-pressed") === "true",
      "`Space` phải PHÁT",
    );
    // 🔴 VẾ GHIM: lần bấm THỨ HAI. Một bản cài "phím phát luôn đặt `playing = true`" đi qua được vế
    // thứ nhất và ĐỔ ở đây (mutant `P4`).
    fireEvent.keyDown(document.body, { key: " " });
    await choPhuHop(
      container,
      ".tp__phat",
      (el) => el.getAttribute("aria-pressed") === "false",
      "`Space` lần thứ hai phải TẠM DỪNG (trạng thái phải đảo, không phải luôn `true`)",
    );

    assert.deepEqual(tiengOn, [], "phat/tam dung bang ban phim khong duoc sinh tieng on console");
    unmount();
  });

  it("T11 CHUYỂN ĐOẠN + SỬA DÒNG: `K`/`J` đổi dòng đang chọn (KẸP ở hai đầu), `Enter` mở ô sửa CỦA NÓ", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    assert.deepEqual(
      [...container.querySelectorAll(".ed__item.is-current")].map((el) => el.getAttribute("data-i")),
      [],
      "chưa bấm gì thì KHÔNG dòng nào đang chọn",
    );

    // (1) `K` = dòng sau. Chưa chọn gì ⇒ dòng ĐẦU.
    fireEvent.keyDown(document.body, { key: "k" });
    await choPhuHop(
      container,
      '[data-i="0"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "`K` phải chọn dòng ĐẦU khi chưa có dòng nào đang chọn",
    );

    // (2) KẸP Ở ĐẦU: `J` tại dòng 0 KHÔNG được VÒNG xuống dòng cuối. Vế phủ định mới là vế phân
    //     biệt "kẹp" với "vòng" — một bản cài vòng sẽ làm dòng 3 thành `is-current` và bài ĐỎ.
    fireEvent.keyDown(document.body, { key: "j" });
    await choPhuHop(
      container,
      '[data-i="0"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "`J` tại dòng ĐẦU phải KẸP (dòng 0 vẫn đang chọn)",
    );
    assert.equal(
      container.querySelector('[data-i="3"].is-current'),
      null,
      "`J` tại dòng đầu KHÔNG được VÒNG xuống dòng cuối",
    );

    // (3) Đi tiếp tới dòng 2, rồi `Enter` mở ô sửa CỦA DÒNG ĐANG CHỌN (không phải dòng 0).
    fireEvent.keyDown(document.body, { key: "k" });
    await choPhuHop(
      container,
      '[data-i="1"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "`K` phải đi tới dòng 1",
    );
    fireEvent.keyDown(document.body, { key: "k" });
    await choPhuHop(
      container,
      '[data-i="2"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "`K` phải đi tới dòng 2",
    );
    fireEvent.keyDown(document.body, { key: "Enter" });
    await choPhuHop(
      container,
      '[data-i="2"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-editing"),
      "`Enter` phải mở ô sửa của DÒNG ĐANG CHỌN",
    );
    assert.equal(
      container.querySelector('[data-i="0"].is-editing'),
      null,
      "`Enter` KHÔNG được mở ô sửa của một dòng khác",
    );
    assert.equal(
      (phanTu(container, '[data-i="2"] textarea') as HTMLTextAreaElement).value,
      "dòng ba",
      "ô sửa phải mang chữ của DÒNG ĐANG CHỌN",
    );

    assert.deepEqual(tiengOn, [], "chuyen doan bang ban phim khong duoc sinh tieng on console");
    unmount();
  });

  it("T11 N: `N` nhảy tới đoạn NGHI NGỜ kế tiếp (bỏ qua dòng không nghi ngờ) — và KHÔNG VÒNG khi hết", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    // Bản ghi #3 có HAI dòng nghi ngờ: `i = 1` và `i = 3` (xem fixture). Vòng sửa 1 (`M-3`): fixture
    // cũ chỉ có MỘT dòng (`i = 3`, dòng CUỐI) ⇒ cả bản VÒNG lẫn bản KHÔNG VÒNG đều đứng yên ở đó,
    // tức mệnh đề "không vòng" không có gì làm nó sai được. Với dòng thứ hai ở GIỮA, bản VÒNG nhảy
    // ngược về `i = 1` sau khi đã ở `i = 3` ⇒ bài này ĐỎ.

    // (1) Chưa chọn dòng nào ⇒ dòng nghi ngờ ĐẦU TIÊN (`i = 1`), nhảy QUA dòng 0 (không nghi ngờ).
    fireEvent.keyDown(document.body, { key: "n" });
    await choPhuHop(
      container,
      '[data-i="1"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "`N` phải nhảy tới dòng NGHI NGỜ ĐẦU TIÊN (i=1), không phải dòng kế tiếp",
    );
    assert.equal(
      container.querySelector('[data-i="0"].is-current'),
      null,
      "`N` KHÔNG được dừng ở một dòng không nghi ngờ",
    );

    // (2) `N` lần hai ⇒ dòng nghi ngờ KẾ TIẾP (`i = 3`), bỏ qua `i = 2`.
    fireEvent.keyDown(document.body, { key: "n" });
    await choPhuHop(
      container,
      '[data-i="3"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "`N` phải nhảy tới dòng NGHI NGỜ KẾ TIẾP (i=3), bỏ qua i=2",
    );
    assert.equal(
      container.querySelector('[data-i="2"].is-current'),
      null,
      "`N` KHÔNG được dừng ở dòng không nghi ngờ i=2",
    );

    // (3) HẾT dòng nghi ngờ ⇒ ĐỨNG YÊN. Vế phân biệt "soát XUÔI" với "đi vòng": bản VÒNG sẽ nhảy về
    //     `i = 1` (một cú nhảy NGƯỢC, làm người đang soát mất chỗ). Đọc NGAY sau `fireEvent`: RTL bọc
    //     nó trong `act`, nên lượt commit của React đã xong (cùng cách các khẳng định phủ định khác).
    fireEvent.keyDown(document.body, { key: "n" });
    assert.equal(
      container.querySelector(".ed__item.is-current")?.getAttribute("data-i"),
      "3",
      "`N` tại dòng nghi ngờ CUỐI phải ĐỨNG YÊN (KHÔNG vòng về dòng nghi ngờ đầu)",
    );

    assert.deepEqual(tiengOn, [], "nhay toi doan nghi ngo khong duoc sinh tieng on console");
    unmount();
  });

  it("T11 J/K/N trong danh sách DÀI (ảo hoá CẮT dòng ra): HAI VẾ — trong TRẦN thì GHIM, ngoài TRẦN thì CUỘN tới", async () => {
    // 🔴 HAI VẾ (Task 12 vòng sửa 1, `I4(d)` — thay cho bài một-vế của lượt trước).
    //
    // Mệnh đề của `D4` là mệnh đề **DOM**: dòng vừa chọn phải có MẶT trong DOM. Nhưng bản ghim
    // VÔ ĐIỀU KIỆN làm khoảng render dài ĐÚNG BẰNG khoảng cách giữa hai mốc — đo được `n=6000`,
    // `e=1`, `c=5999` ⇒ **6 000 hàng / 264 000 px**, tức giá không có trần theo dữ liệu. Từ vòng
    // sửa 1, mốc chọn **chỉ được ghim trong TRẦN** (`EditScreen.tranGhimThem` = 2 khung nhìn =
    // **32 hàng** với `480/44/5`), và NGOÀI trần thì `EditScreen` **CUỘN khung tới** nó.
    //
    //  - **VẾ A — TRONG TRẦN** (i = 40, cửa sổ ban đầu [0,16), trần ⇒ tới 47): dòng đó PHẢI có mặt
    //    trong DOM **và khung KHÔNG được cuộn**. Vế này ghim được TRỌN VẸN trong jsdom (không cần
    //    layout) — và nó là vế chứng minh bản ghim còn sống.
    //  - **VẾ B — NGOÀI TRẦN** (i = 500): dòng đó PHẢI có mặt trong DOM **vì khung ĐÃ CUỘN TỚI**
    //    (khẳng định `scrollTop > 0`). Vế "và nó THẬT SỰ nhìn thấy được trên màn hình" **chỉ
    //    Chrome thật đo được** (`e2e/plans/ban-ghi-dai-t7.json`, bước `T7-G`) — jsdom không có
    //    layout, nên ở đây chỉ ghim được *"đã cuộn"* chứ không ghim được *"đã nhìn thấy"*.
    const dai: Segment[] = Array.from(
      { length: 600 },
      (_, i) => doan(i, i * 2, i * 2 + 2, `đoạn dài ${i}`),
    );
    dai[1] = { ...dai[1], suspect: true };
    dai[40] = { ...dai[40], suspect: true };
    dai[500] = { ...dai[500], suspect: true };
    TRANSCRIPT_CHI_TIET = {
      ...TRANSCRIPT_CHI_TIET,
      3: { ...TRANSCRIPT_CHI_TIET_GOC[3], segments: dai },
    };

    const { container, unmount } = render(taoPhanTu(App));
    await choChu(container, "kenh-hai");
    fireEvent.click(nutKenh(container, "kenh-hai"));
    await choChu(container, "đoạn dài 0");

    // ⚠️ HAI NHỊP DỌN TRONG BÀI (cùng kỹ thuật đã dùng để đóng rò async ở `c575192`): `useShortcuts`
    // gắn lại listener mỗi lượt render (deps `[xuLy, mode]`), nên listener CŨ trong "cửa sổ
    // một-lượt-commit" đọc `transcript.data` của lượt TRƯỚC (`null`) ⇒ một phím rơi ĐÚNG cửa sổ đó
    // bị NUỐT IM LẶNG. Đây là `waitFor` — một phép cho theo NHỊP, không phải `sleep`.
    // ⚠️ Vòng sửa 1 KHÔNG thêm chỗ dùng mới nào cho kỹ thuật này (nó chỉ được giữ nguyên ở đây).
    await waitFor(() => { assert.ok(true, "nhịp dọn 1"); }, { timeout: 2000, interval: 10 });
    await waitFor(() => { assert.ok(true, "nhịp dọn 2"); }, { timeout: 2000, interval: 10 });
    assert.equal(
      document.activeElement,
      document.body,
      "ca này chỉ có nghĩa khi tiêu điểm ở BODY (guard ô nhập sẽ nuốt phím toàn cục)",
    );

    const khung = container.querySelector(".ed__khung") as HTMLElement;
    assert.ok(khung !== null, "danh sách phải nằm trong một khung cuộn (C1)");

    // ĐỐI CHỨNG DƯƠNG của cả hai vế: CHƯA chọn thì ảo hoá phải cắt CẢ HAI dòng ra. Thiếu vế này
    // thì "có mặt" có thể đúng một cách vô nghĩa (một danh sách không hề ảo hoá).
    assert.equal(
      container.querySelector('[data-i="40"]'),
      null,
      "chưa chọn thì dòng 40 phải NGOÀI cửa sổ (nếu không, danh sách này không ảo hoá thật)",
    );
    assert.equal(
      container.querySelector('[data-i="500"]'),
      null,
      "chưa chọn thì dòng 500 cũng phải NGOÀI cửa sổ",
    );

    // (1) `N` lần đầu ⇒ dòng nghi ngờ ĐẦU (i=1, vẫn TRONG cửa sổ).
    fireEvent.keyDown(document.body, { key: "n" });
    await choPhuHop(
      container,
      '[data-i="1"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "`N` phải chọn dòng nghi ngờ đầu (i=1)",
    );

    // (2) 🔴 VẾ A — `N` lần hai ⇒ i=40, NGOÀI cửa sổ nhưng TRONG TRẦN (40 < 16 + 32).
    fireEvent.keyDown(document.body, { key: "n" });
    await choPhuHop(
      container,
      '[data-i="40"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "TRONG TRẦN ⇒ dòng vừa chọn phải có MẶT trong DOM",
    );
    assert.equal(
      khung.scrollTop,
      0,
      "TRONG TRẦN thì đường bù là GHIM, KHÔNG phải cuộn — khung phải đứng yên",
    );
    assert.ok(
      container.querySelectorAll("[data-i]").length <= 48,
      "TRONG TRẦN ⇒ tối đa cửa sổ (16) + TRẦN (32) hàng; đo được "
        + `${container.querySelectorAll("[data-i]").length}`,
    );

    // (3) 🔴 VẾ B — `N` lần ba ⇒ i=500, NGOÀI TRẦN (`500 > 16 + 32 - 1`) ⇒ KHÔNG ghim, và đường bù
    //     là CUỘN khung tới nó. Sau khi cuộn, dòng đó nằm trong cửa sổ nên vẫn có mặt.
    fireEvent.keyDown(document.body, { key: "n" });
    await choPhuHop(
      container,
      '[data-i="500"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "NGOÀI TRẦN ⇒ phải CUỘN tới dòng 500 (và dòng đó vào cửa sổ nên vẫn có MẶT trong DOM)",
    );
    assert.ok(
      khung.scrollTop > 0,
      "NGOÀI TRẦN ⇒ khung PHẢI đã cuộn tới (đây là đường bù của bản ghim có trần; "
        + `đo được scrollTop=${khung.scrollTop})`,
    );
    assert.ok(
      container.querySelectorAll("[data-i]").length <= 48,
      "NGOÀI TRẦN ⇒ số hàng vẫn là cửa sổ thường, KHÔNG nở theo khoảng cách; đo được "
        + `${container.querySelectorAll("[data-i]").length}`,
    );

    // (4) `K`/`J` đi MỘT dòng một lần quanh chỗ đang cuộn ⇒ vẫn trong trần, vẫn phải có mặt.
    fireEvent.keyDown(document.body, { key: "k" });
    await choPhuHop(
      container,
      '[data-i="501"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "`K` chọn dòng 501 (sát cửa sổ ⇒ trong trần) ⇒ dòng đó phải có MẶT trong DOM",
    );
    fireEvent.keyDown(document.body, { key: "j" });
    await choPhuHop(
      container,
      '[data-i="500"]',
      (el) => (el.getAttribute("class") ?? "").includes("is-current"),
      "`J` phải quay lại dòng 500 (và dòng đó vẫn phải có MẶT trong DOM)",
    );

    assert.deepEqual(
      tiengOn,
      [],
      "di chuyen dong bang ban phim trong danh sach dai khong duoc sinh tieng on console",
    );
    unmount();
  });

  it("T11 ĐỔI CHẾ ĐỘ: `Ctrl+2` / `Ctrl+3` / `Ctrl+1` đổi MÀN (quan sát trên ĐẦU RA ĐÃ RENDER)", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    assert.ok(container.querySelector(".ed") !== null, "bắt đầu ở màn Biên tập");

    fireEvent.keyDown(document.body, { key: "2", ctrlKey: true });
    await choPhuHop(container, ".cmp", () => true, "`Ctrl+2` phải hiện màn Đối chiếu");
    assert.equal(container.querySelector(".ed"), null, "màn Biên tập phải BIẾN MẤT (không chỉ thêm màn mới)");

    fireEvent.keyDown(document.body, { key: "3", ctrlKey: true });
    await choPhuHop(container, ".gl", () => true, "`Ctrl+3` phải hiện tab Thuật ngữ");
    assert.equal(container.querySelector(".cmp"), null, "màn Đối chiếu phải biến mất");

    // Vế ngược: `Ctrl+1` phải QUAY VỀ được — nếu không thì vào Thuật ngữ là KHÔNG RA.
    fireEvent.keyDown(document.body, { key: "1", ctrlKey: true });
    await choPhuHop(container, ".ed", () => true, "`Ctrl+1` phải quay về màn Biên tập");
    assert.equal(container.querySelector(".gl"), null, "tab Thuật ngữ phải biến mất");

    assert.deepEqual(tiengOn, [], "doi che do bang ban phim khong duoc sinh tieng on console");
    unmount();
  });

  it("T11 BẢNG PHÍM §11.4: `?` mở bảng TỪ CHÍNH bảng dữ liệu, `Esc` ĐÓNG bảng (không thoát ô sửa), và bảng chặn phím khác", async () => {
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    await moOSua(container, 1);

    // (1) `?` mở bảng. Đo được TRƯỚC task (Chrome thật): chuỗi `Phím tắt` KHÔNG tồn tại trong DOM.
    fireEvent.keyDown(document.body, { key: "?", shiftKey: true });
    await choPhuHop(container, ".bp", () => true, "`?` phải mở bảng phím tắt");
    assert.match(container.textContent ?? "", /Phím tắt/, "bảng phải TỰ NÓI nó là gì");
    const hang = [...container.querySelectorAll(".bp__dong")];
    assert.equal(
      hang.length,
      BANG_PHIM.length,
      "bảng §11.4 phải in ĐÚNG số hàng của bảng dữ liệu (một nguồn, không chép tay)",
    );
    assert.deepEqual(
      hang.map((el) => [
        el.querySelector(".bp__to-hop")?.textContent ?? "",
        el.querySelector(".bp__viec")?.textContent ?? "",
        el.querySelector(".bp__chua-noi") === null ? "đã nối" : "chưa nối",
      ]),
      BANG_PHIM.map((pt) => [
        pt.toHop,
        pt.viec,
        DA_NOI.has(pt.action.type) ? "đã nối" : "chưa nối",
      ]),
      // ⚠️ VÒNG SỬA 1 (`M-2`): chỗ này TRƯỚC ĐÂY chỉ so CỘT NHÃN PHÍM (`.bp__to-hop`) ⇒ mutant đổi
      // cột VIỆC (`P8b`: chép tay lệch một hàng) cho **0 bài đỏ ở tầng `App`** — biên phủ chỉ nằm ở
      // `BangPhim.test.tsx`. Nay so CẢ HÀNG: nhãn + VIỆC + dấu `chưa nối`. Ba cột đó là toàn bộ thứ
      // bảng §11.4 in ra, nên một hàng lệch ở BẤT KỲ cột nào cũng là "hai nguồn sự thật".
      "từng HÀNG của DOM phải là một HÀNG của bảng dữ liệu (nhãn + việc + dấu `chưa nối`), cùng thứ tự",
    );

    // (2) BẢNG ĐANG MỞ ⇒ nó CHẶN các phím khác. `[` lúc này có một dòng đang sửa, nên nếu nó lọt
    //     qua thì đó là một lượt GHI vào bản ghi sau lưng một lớp phủ đang che màn hình.
    xoaDemGhi();
    fireEvent.keyDown(document.body, { key: "[" });
    fireEvent.keyDown(document.body, { key: "]" });
    await choHaiNhip();
    assert.equal(dem.patch, 0, "bảng đang mở ⇒ phím của màn Biên tập KHÔNG được ghi gì");

    // (3) `Esc` ĐÓNG BẢNG, và KHÔNG nuốt luôn ô sửa: `Esc` lần hai mới là "thoát sửa".
    fireEvent.keyDown(document.body, { key: "Escape" });
    // ⚠️ Đọc NGAY sau `fireEvent`: RTL bọc nó trong `act`, nên lượt commit của React đã xong — cùng
    // cách các khẳng định phủ định khác của tệp này đọc DOM (không chờ theo đồng hồ).
    assert.equal(container.querySelector(".bp"), null, "`Esc` phải đóng bảng phím tắt");
    assert.ok(
      (phanTu(container, '[data-i="1"]').getAttribute("class") ?? "").includes("is-editing"),
      "`Esc` đóng bảng KHÔNG được thoát ô sửa (một phím, một việc)",
    );
    fireEvent.keyDown(document.body, { key: "Escape" });
    await choPhuHop(
      container,
      '[data-i="1"]',
      (el) => !(el.getAttribute("class") ?? "").includes("is-editing"),
      "`Esc` lần hai (bảng đã đóng) phải THOÁT ô sửa",
    );

    assert.deepEqual(tiengOn, [], "bang phim khong duoc sinh tieng on console");
    unmount();
  });

  it("T11 ĐÓNG BẢNG Ở MỌI CHẾ ĐỘ: `?` mở ở `glossary` ⇒ `Esc` ĐÓNG bảng; nút `đóng` đang có tiêu điểm KHÔNG bị nuốt `Enter`/`Space` (I-1)", async () => {
    // HAI VẾ của `I-1`, đo trên ĐẦU RA ĐÃ RENDER (không phải trên `resolveKey`):
    //  (a) bảng §11.4 mở được ở MỌI chế độ (`?` không có `mode`), nên `Esc` phải ĐÓNG được ở mọi
    //      chế độ. Phiên chính đo trong Chrome thật: ở `edit` thì đóng, ở `glossary` thì VẪN MỞ
    //      (hàng `Escape` khi đó còn `mode: "edit"` ⇒ `resolveKey` trả `null`).
    //  (b) nút `đóng` của chính bảng có `autoFocus`; ở `mode === "edit"` app gọi `preventDefault()`
    //      cho MỌI phím tra được, kể cả `Enter`/`Space` — phím KÍCH HOẠT của `<button>`.
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    // Sang chế độ THUẬT NGỮ (chế độ mà vế (a) hỏng).
    fireEvent.keyDown(document.body, { key: "3", ctrlKey: true });
    await choPhuHop(container, ".gl", () => true, "`Ctrl+3` phải hiện tab Thuật ngữ");
    assert.ok(container.querySelector(".ed") === null, "màn Biên tập phải biến mất");

    fireEvent.keyDown(document.body, { key: "?", shiftKey: true });
    await choPhuHop(container, ".bp", () => true, "`?` phải mở bảng phím tắt Ở MỌI chế độ");
    const nut = phanTu(container, '[data-testid="dong-bang-phim"]');
    // ⚠️ KHẲNG ĐỊNH BOOLEAN, không `assert.equal(nodeA, nodeB)`: `assert` định dạng `actual`/
    // `expected` KHÔNG giới hạn độ sâu, và một node DOM của React là một đồ thị khổng lồ ⇒ đo được
    // ở mutant `MODE-ESCAPE-BACK` (lượt này): bài ĐỎ ⇒ 90 s rồi `RangeError: Array buffer
    // allocation failed`, và cú OOM đó làm bài SAU hỏng theo (`fetch failed` ⇒ một bài đỏ GIẢ).
    // Đây đúng lớp ERRATA #14 mục 3.
    assert.ok(document.activeElement === nut, "tiêu điểm phải ở TRONG bảng (autoFocus) ngay khi mở");

    // (b) NÚT ĐANG CÓ TIÊU ĐIỂM ⇒ `Enter`/`Space` thuộc về NÓ. Phát `KeyboardEvent` THÔ để đọc
    //     `defaultPrevented` (cơ chế trình duyệt dùng để quyết định kích hoạt nút hay không) và
    //     để `target` là CHÍNH nút — đúng đường một người dùng bàn phím đi.
    const eEnter = new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    act(() => {
      nut.dispatchEvent(eEnter);
    });
    assert.equal(eEnter.defaultPrevented, false, "`Enter` trên nút `đóng` KHÔNG được bị chặn mặc định");
    const eSpace = new window.KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true });
    act(() => {
      nut.dispatchEvent(eSpace);
    });
    assert.equal(eSpace.defaultPrevented, false, "`Space` trên nút `đóng` KHÔNG được bị chặn mặc định");
    // ⚠️ jsdom KHÔNG tự sinh cú `click` từ `keydown` trên `<button>` (đó là việc của trình duyệt
    // thật) ⇒ vế "nút ĐƯỢC kích hoạt" chỉ Chrome thật trả lời được (TRẦN, chủ: Task 12). Vế ĐO
    // ĐƯỢC ở đây là hai hệ quả của việc app NUỐT phím: `defaultPrevented` và việc app làm một
    // VIỆC KHÁC — `Space` là phát/dừng, nên nếu nó lọt tới handler thì `aria-pressed` đổi.
    assert.equal(
      phanTu(container, ".tp__phat").getAttribute("aria-pressed"),
      "false",
      "`Space` trên nút `đóng` KHÔNG được làm app phát/tạm dừng",
    );
    assert.ok(container.querySelector(".bp") !== null, "chưa bấm gì để đóng thì bảng phải CÒN");

    // (a) `Esc` ĐÓNG bảng ở chế độ Thuật ngữ — phát từ chính nút đang có tiêu điểm (như người dùng).
    fireEvent.keyDown(nut, { key: "Escape" });
    assert.ok(
      container.querySelector(".bp") === null,
      "`Esc` phải đóng bảng phím tắt ở chế độ Thuật ngữ",
    );
    assert.ok(container.querySelector(".gl") !== null, "`Esc` chỉ đóng BẢNG, không đổi chế độ");

    assert.deepEqual(tiengOn, [], "dong bang o che do Thuat ngu khong duoc sinh tieng on console");
    unmount();
  });

  it("T11 PHÍM CHƯA CÓ ĐÍCH: `S` / `M` / `Ctrl+Enter` (spec CÓ, sản phẩm CHƯA có đích) ⇒ 0 request và DOM không đổi", async () => {
    // ⚠️ Danh sách phím lấy TỪ CHÍNH BẢNG (`BANG_PHIM` trừ `DA_NOI`) — không liệt kê tay. Nhờ vậy
    // nếu sau này một phím trong số đó ĐƯỢC NỐI mà quên bỏ khỏi `DA_NOI`, bài này ĐỎ (bảng đang
    // nói dối), và nếu một phím ĐÃ NỐI bị bỏ nối thì bài của chính nó ĐỎ.
    const chuaNoi = BANG_PHIM.filter((pt) => !DA_NOI.has(pt.action.type));
    assert.deepEqual(
      chuaNoi.map((pt) => pt.toHop).sort(),
      ["Ctrl+Enter", "M", "S"],
      "TRẦN đã khai: đúng ba phím của spec chưa có đích trong sản phẩm",
    );

    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);
    await moOSua(container, 1);
    xoaDemGhi();
    const truoc = container.innerHTML;

    for (const pt of chuaNoi) {
      fireEvent.keyDown(document.body, {
        key: pt.key,
        ctrlKey: pt.ctrl ?? false,
        altKey: pt.alt ?? false,
        shiftKey: pt.shift ?? false,
      });
    }
    await choHaiNhip();
    assert.equal(dem.patch, 0, "phím chưa có đích KHÔNG được ghi gì");
    assert.equal(dem.postTranslations, 0, "phím chưa có đích KHÔNG được tạo bản dịch/job nào");
    assert.equal(container.innerHTML, truoc, "phím chưa có đích KHÔNG được đổi DOM");

    assert.deepEqual(tiengOn, [], "phim chua co dich khong duoc sinh tieng on console");
    unmount();
  });

  // ===========================================================================
  // ITEM 5 — BÓC LẠI BẰNG ENGINE ASR KHÁC (`POST /api/jobs`) VÀ RAIL HAI MỐC
  //
  // Hai mệnh đề, cùng một cò: (1) bấm `bóc lại` ⇒ ĐÚNG MỘT `POST /api/jobs` với `workspace: 1`,
  // `type: "asr"`, `engine` ĐANG CHỌN và `payload.source_id` của BẢN GHI đang mở — đo ở PHÍA MÁY
  // CHỦ, trên BODY THẬT; (2) trạng thái của lời gọi được NÓI RA bằng CHỮ (đang bay / lỗi nguyên
  // văn), và điều khiển VÔ HIỆU khi đang bay.
  //
  // ⚠️ VẾ "job xong ⇒ bản ghi mới hiện ra" KHÔNG được đo lại ở đây: nó đã có bài ghim riêng
  // (`W1` — "job `asr` xong ⇒ BẢN GHI MỚI hiện ra", ngòi nổ `/api/transcripts`). Đường này chỉ
  // XẾP job, cố ý không `reload()` gì — xem docblock `bocLai`.
  // ===========================================================================

  it("BÓC LẠI: bấm ⇒ ĐÚNG MỘT `POST /api/jobs` (workspace 1 · type asr · engine ĐANG CHỌN · payload.source_id của bản ghi đang mở), và nói ra 'đang bóc lại…'", async () => {
    // Độ trễ để cửa sổ "đang bay" là XÁC ĐỊNH, không phải một cuộc đua (cùng khuôn `approveTre`).
    dem.jobMoiTre = 200;
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container); // kênh HAI, bản ghi #3 (source_id 2, lang "en")

    // Ô chọn ASR phải có lựa chọn TRƯỚC khi bấm: registry của fixture có ĐÚNG MỘT engine ASR, và
    // `transcript.engine` ("sensevoice-small") KHÔNG có trong đó ⇒ chọn sẵn engine đầu tiên.
    const chon = phanTu(container, '[data-testid="chon-engine-asr"]') as HTMLSelectElement;
    assert.deepEqual(
      [...chon.querySelectorAll("option")].map((o) => o.getAttribute("value")),
      ["faster-whisper-large"],
      "ô chọn ASR phải lấy engine từ `/api/registry` (spec ASR thiếu `capabilities.available` ⇒ "
      + "nếu lọc theo khoá đó thì danh sách RỖNG)",
    );
    assert.equal(chon.value, "faster-whisper-large");
    assert.equal(dem.jobMoi, 0, "chưa bấm thì chưa được có request nào");

    fireEvent.click(phanTu(container, '[data-testid="boc-lai"]'));

    // (1) TRẠNG THÁI NÓI RA BẰNG CHỮ + HAI ĐIỀU KHIỂN VÔ HIỆU (một nút bấm được mà không gửi gì
    //     là một lời nói dối), trong lúc lời gọi CHẮC CHẮN còn bay (trễ 200 ms ở server).
    assert.equal(
      chu(container, '[data-testid="dang-boc-lai"]'),
      "đang bóc lại…",
      "trong lúc lời gọi đang bay, màn phải NÓI RA là đang bóc lại",
    );
    assert.equal(
      (phanTu(container, '[data-testid="boc-lai"]') as HTMLButtonElement).disabled,
      true,
      "đang bay ⇒ nút phải VÔ HIỆU",
    );
    assert.equal(
      (phanTu(container, '[data-testid="chon-engine-asr"]') as HTMLSelectElement).disabled,
      true,
      "đang bay ⇒ ô chọn engine phải VÔ HIỆU (đổi engine giữa lúc bay là bấm vào một id không đi đâu)",
    );

    await waitFor(
      () => {
        assert.equal(dem.jobMoiXong, 1, "lời gọi tạo job chưa trả về");
      },
      { timeout: 5000, interval: 20 },
    );
    await waitFor(
      () => {
        assert.equal(
          container.querySelectorAll('[data-testid="dang-boc-lai"]').length,
          0,
          "câu `đang bóc lại…` phải BIẾN MẤT khi xong",
        );
      },
      { timeout: 5000, interval: 20 },
    );

    // (2) BẰNG CHỨNG DUONG THAT Ở PHÍA MÁY CHỦ: ĐÚNG MỘT request, và body là HỢP ĐỒNG của
    //     `routes_jobs.JobIn` + `AsrPayload` — `payload.source_id` là của BẢN GHI ĐANG MỞ (#3 ⇒
    //     source 2), không phải một id hard-code.
    assert.equal(dem.jobMoi, 1, "bấm `bóc lại` ⇒ ĐÚNG MỘT request tạo job");
    assert.deepEqual(
      dem.bodyJobMoi,
      {
        workspace: 1,
        type: "asr",
        engine: "faster-whisper-large",
        payload: { source_id: 2, lang: "en" },
      },
      "body phải là ĐÚNG hợp đồng `POST /api/jobs` của route (engine ASR đang chọn, source của bản "
      + "ghi đang mở); body thật: " + dem.rawJobMoi,
    );
    // Xong ⇒ hai điều khiển bật lại, và KHÔNG có câu lỗi nào.
    assert.equal(
      (phanTu(container, '[data-testid="boc-lai"]') as HTMLButtonElement).disabled,
      false,
      "xong ⇒ nút phải bấm được lần nữa",
    );
    assert.equal(
      container.querySelectorAll('[data-testid="loi-boc-lai"]').length,
      0,
      "không có lỗi ⇒ không được có câu lỗi",
    );

    assert.deepEqual(tiengOn, [], "boc lai thanh cong khong duoc sinh tieng on console");
    unmount();
  });

  it("BÓC LẠI: bấm HAI lần KHÔNG chờ ⇒ ĐÚNG MỘT request ở PHÍA MÁY CHU (guard theo NGUỒN)", async () => {
    // Làm CHẬM phản hồi: cách DUY NHẤT khiến hai lần bấm CHẮC CHẮN chồng lấn (khuôn `C1`/`D2`).
    dem.jobMoiTre = 250;
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    const nut = phanTu(container, '[data-testid="boc-lai"]');
    fireEvent.click(nut);
    fireEvent.click(nut); // KHÔNG chờ
    assert.equal(dem.jobMoiXong, 0, "hai lần bấm phải CHỒNG LẤN: lần hai xảy ra khi lần một CHƯA xong");
    await waitFor(
      () => {
        assert.equal(dem.jobMoiXong, 1, "lời gọi tạo job chưa trả về");
      },
      { timeout: 5000, interval: 20 },
    );
    // 🔴 KHANG DINH O PHIA MAY CHU: mot lan bam thu hai lot qua guard se thanh HAI job `asr` cho
    // CUNG mot nguon ⇒ hai ban ghi trung, va `chonTranscript` (id lon nhat) doi ban dang mo vo co.
    assert.equal(dem.jobMoi, 1, "bấm HAI lần KHÔNG chờ ⇒ chỉ được có MỘT request tạo job");

    assert.deepEqual(tiengOn, [], "bam hai lan khong duoc sinh tieng on console");
    unmount();
  });

  it("BÓC LẠI: lỗi là NGUYÊN VĂN `ApiError.message`, và nó KHÔNG sống qua một lần ĐỔI KÊNH", async () => {
    dem.jobMoiLoi = true;
    const { container, unmount } = render(taoPhanTu(App));
    await toiBienTapBonDoan(container);

    fireEvent.click(phanTu(container, '[data-testid="boc-lai"]'));
    const cau = await choPhanTu(
      container,
      '[data-testid="loi-boc-lai"]',
      (t) => t.length > 0,
      "không thấy câu báo lỗi của lời gọi `bóc lại`",
    );
    // NGUYÊN VĂN `<status>: <detail>` — câu tiếng Việt của `registry.by_id` (đi qua
    // `routes_jobs.create_job` ⇒ `HTTPException(422, str(exc))`), KHÔNG phải một câu chung.
    assert.equal(cau, '422: "engine \'fw-large-v3\' không có trong registry"');
    // Lỗi KHÔNG được khoá nút: người dùng phải bấm lại được (sau khi sửa registry/chọn engine khác).
    assert.equal(
      (phanTu(container, '[data-testid="boc-lai"]') as HTMLButtonElement).disabled,
      false,
      "lỗi ⇒ nút phải bật lại (nếu không thì một lần 422 là ngõ cụt)",
    );
    assert.equal(dem.jobMoi, 1);

    // ĐỔI KÊNH ⇒ câu 422 của nguồn CŨ không được nằm cạnh thanh trên của nguồn MỚI (cùng lỗi
    // `I1` mà vòng sửa W3 đã đóng cho `loiTao`, và `I3b` cho cờ "đang bay").
    await choChu(container, "kenh-mot.wav");
    fireEvent.click(nutKenh(container, "kenh-mot.wav"));
    await choChu(container, "câu 1");
    await waitFor(
      () => {
        assert.equal(
          container.querySelectorAll('[data-testid="loi-boc-lai"]').length,
          0,
          "câu lỗi của nguồn CŨ phải biến mất khi đổi kênh",
        );
      },
      { timeout: 5000, interval: 20 },
    );

    assert.deepEqual(tiengOn, [], "loi boc lai khong duoc sinh tieng on console");
    unmount();
  });
});
