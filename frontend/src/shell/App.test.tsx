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
  Job,
  Segment,
  Source,
  Transcript,
  TranscriptSummary,
  Translation,
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
 */
const TRANSCRIPTS: TranscriptSummary[] = [
  tomTat(2, 1, "faster-whisper-large", "zh", 1, "draft"),
  tomTat(5, 1, "faster-whisper-large", "zh", 2, "translated"),
  tomTat(3, 2, "sensevoice-small", "en", 1, "draft"),
];

/** `GET /api/transcripts/{id}` — ban DAY DU (co `segments`). */
const TRANSCRIPT_CHI_TIET: Record<number, Transcript> = {
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
 */
const TRANSLATIONS: Translation[] = [
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

const dem = {
  sources: 0,
  jobs: 0,
  stream: 0,
  loiSources: false,
  /**
   * Bon bo dem cho duong SUY DU LIEU cua W1. Chung la BANG CHUNG DUONG THAT: neu khong
   * dem duoc thi "man hien du lieu that" co the xanh vi mot ly do khac (du lieu den tu
   * dau do khong phai HTTP).
   */
  transcripts: 0,
  transcriptChiTiet: 0,
  translations: 0,
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
};
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
    dem.translations += 1;
    // Loc theo DUNG query param ma `endpoints.listTranslations` gui di
    // (`/api/translations?transcript_id=<id>`): tra het moi ban dich se lam man Doi chieu
    // hien ban dich cua KENH KHAC — dung lop loi "hai nguon su that" ma du an dang chan.
    const transcriptId = Number(new URL(url, "http://127.0.0.1").searchParams.get("transcript_id"));
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(TRANSLATIONS.filter((t) => t.transcript_id === transcriptId)));
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
let fireEvent: { click: (el: Element) => void };
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

/** Muc KENH (nut) chua `chuoi` — tra theo CHU, khong theo thu tu mang. */
function nutKenh(container: HTMLElement, chuoi: string): Element {
  const khop = [...container.querySelectorAll(".ch__item")].find(
    (el) => (el.textContent ?? "").includes(chuoi),
  );
  assert.ok(khop !== undefined, `khong thay muc kenh nao chua "${chuoi}"`);
  return khop as Element;
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
    dem.transcripts = 0;
    dem.transcriptChiTiet = 0;
    dem.translations = 0;
    dem.translationChiTiet = 0;
    dem.soYeuCauIdKhongHopLe = 0;
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
    // ⚠️ Cho theo TIN HIEU, khong khang dinh ngay: `transcript` va `translations` la HAI
    // `useApi` doc lap, nen "câu 1" co the hien TRUOC khi hai request `getTranslation` ket
    // thuc. Mot phep khang dinh ngay (`=== 2`) la mot phep do PHU THUOC THOI DIEM — do duoc
    // trong luot mutation `W1-5` (no do o dung dong nay, khong phai vi mutant).
    await waitFor(
      () => {
        assert.equal(dem.translationChiTiet, 2, "phai doc CHI TIET ca hai ban dich cua ban ghi");
      },
      { timeout: 5000, interval: 20 },
    );

    fireEvent.click(getByRole(container, "radio", { name: /đối chiếu/i }));

    // Bộ chọn bản dịch: hai hàng của bản ghi ⇒ hai nút chọn.
    await choPhanTu(
      container,
      '[data-testid="pick-11"]',
      (t) => t.includes("bản dịch"),
      "man Doi chieu khong nhan duoc danh sach ban dich THAT",
    );

    // ⚠️ Màn Đối chiếu mặc định chọn `translations[0]`, mà route that tra MOI NHAT TRUOC
    // (id 12 `queued`) ⇒ cột phải rỗng cho tới khi người dùng chọn bản `done`. Đó là hành vi
    // của Task 8, không phải của W1 — bài này chọn bản `done` (11) rồi mới đo CPS.
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
});
