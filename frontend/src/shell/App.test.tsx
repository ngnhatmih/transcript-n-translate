/**
 * Test `<App/>` THAT: render that trong jsdom, va du lieu lay tu mot server
 * `node:http` THAT trong tien trinh (`listen(0)` xin cong trong — khong giam cong
 * cua ai). Khong mock module nao.
 *
 * Vi sao khong phai Playwright: trinh duyet THAT la BAT KHA o moi truong nay —
 * Chromium chet o `FATAL:mojo\public\cpp\platform_channel.cc:187 ... Access is
 * denied (0x5)` vi Mojo dung NAMED PIPE, ban tai ve va Edge/Chrome co san deu vay
 * (ERRATA #5 muc 3). jsdom KHONG phai trinh duyet: khong layout, khong CSS that.
 * ⇒ "khong co loi console" la dieu DUY NHAT tep nay do duoc ve phia hien thi.
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
  3: {
    ...tomTat(3, 2, "sensevoice-small", "en", 1, "draft"),
    segments: [doan(0, 0, 2, "bản kênh hai")],
  },
};

function banDich(
  id: number,
  transcriptId: number,
  status: Translation["status"],
): Translation {
  return {
    id,
    transcript_id: transcriptId,
    engine: "qwen2.5-7b",
    target_lang: "vi",
    prompt_version: "raw-p1",
    transcript_version: 2,
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
};

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
  if (url.startsWith("/api/jobs")) {
    dem.jobs += 1;
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(JOBS));
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
    res.end(JSON.stringify(dayDu));
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
    res.end(JSON.stringify(TRANSLATIONS.filter((t) => t.transcript_id === transcriptId)));
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
    res.end(JSON.stringify(SOURCES));
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
let App: () => unknown;
/**
 * `createElement`, KHONG goi thang `App()`: goi ham component ngoai chu trinh render
 * cua React thi `useState` nhan dispatcher `null` (`TypeError: Cannot read properties
 * of null (reading 'useState')`) — da do duoc, khong phai gia thuyet. Lay no qua
 * `import("react")` SAU `setupDom`, giong moi thu khac trong tep nay.
 */
let taoPhanTu: (type: unknown) => unknown;

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
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
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
    // ⚠️ CA MANG JOB: bai `I3` day mot job DICH vao anh chup (xem `themJobDich`), va job do
    // song sot sang bai sau thi "job cua BAN KHAC khong keo request" se DO vi mot job thua.
    JOBS.length = SO_JOB_GOC;
  });

  // `cleanup` cua Testing Library go DOM da render — khong cham vao global nao,
  // nen no KHONG bat buoc phai nam trong `describe`; dat o day vi no thuoc suite nay.
  afterEach(() => {
    cleanup();
  });

  after(async () => {
    traTiengOn();
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
});
