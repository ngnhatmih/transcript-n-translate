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

import type { Job, Source } from "../api/types.ts";
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

const dem = { sources: 0, jobs: 0, stream: 0, loiSources: false };
const streams = new Set<ServerResponse>();
const sockets = new Set<Socket>();

const server: Server = createServer((req, res) => {
  const url = req.url ?? "";
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

  it("HINH THUC: luoi .shell khai VI TRI (grid-row) cho ca BON con, khong de auto-placement", () => {
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");

    assert.match(appCss, /\.shell \{[^}]*display: grid/,
      "`.shell` phai la mot luoi CSS (co `display: grid`)");

    // Bon con cua `.shell` theo THU TU DOM trong `App.tsx`: header, panel (co the vang),
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
