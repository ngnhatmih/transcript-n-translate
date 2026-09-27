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

/** `phase` theo dung dinh dang `job_state.phase_of` = "<type>:<engine|->". */
function makeJob(
  id: number,
  state: Job["state"],
  phase: string,
  progress: number,
): Job {
  return {
    id,
    workspace: 1,
    type: id === 7 ? "asr" : "translate",
    engine: id === 7 ? "faster-whisper-large" : "qwen2.5-7b",
    phase,
    state,
    cancel_requested: false,
    attempts: 1,
    progress,
    log_tail: "",
    error: null,
    payload: {},
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

const JOBS: Job[] = [
  makeJob(7, "running", "asr:faster-whisper-large", 0.35),
  makeJob(8, "queued", "translate:qwen2.5-7b", 0),
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

    // Trang thai tu ANH CHUP truoc: job 8 dang CHO.
    await choChu(container, "chờ gom lô");
    const jobsSauAnhChup = dem.jobs;

    // ⚠️ CHO STREAM THAT SU MO truoc khi ghi su kien. DO DUOC (khong phai gia thuyet):
    // anh chup duoc publish TRUOC khi hook mo stream, nen ghi ngay sau khi thay chu
    // "chờ gom lô" thi byte di vao `streams` RONG ⇒ su kien bi MAT, va bai test do vi
    // mot ly do khong lien quan gi toi thu no dinh do. Lan do that: mutation MINE-4 lam
    // bai nay do o dung cho nay.
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
    await choChu(container, "đang chạy · translate:qwen2.5-7b");
    await choChu(container, "10%");
    await waitFor(
      () => {
        const text = container.textContent ?? "";
        assert.ok(
          !text.includes("chờ gom lô"),
          `job 8 da chay thi khong duoc con hien "chờ gom lô"; do duoc: ${JSON.stringify(text.slice(0, 400))}`,
        );
      },
      { timeout: 5000, interval: 20 },
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
});
