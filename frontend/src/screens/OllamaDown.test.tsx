/**
 * Test `<StatusStrip/>`, `<OllamaDown/>` va `<Header/>` THAT trong jsdom (spec UI §4.8:
 * "trang thai Ollama la trang thai HANG NHAT, khong phai toast"), cong MOT bai noi
 * `<App/>` voi `/api/status` + `/api/registry` qua HTTP THAT (server `node:http` trong
 * tien trinh, `listen(0)` xin cong trong — khong giam cong cua ai).
 *
 * VI SAO CO BAI `App` O DAY: hai component kia nhan du lieu qua PROP, nen chung mot minh
 * khong chung minh duoc rang APP THUC SU GOI `/api/status` va `/api/registry`. Bai cuoi
 * tep nay do dung duong do, bang SO DEM REQUEST PHIA SERVER.
 *
 * VI SAO `unknown` LA MOT BAI RIENG (khong gop vao `down`): `probe_ollama` tra `unknown`
 * khi cong TIMEOUT (chua do duoc), va `down` khi bi tu choi. Task 2 do tren may nay:
 * `/api/status` tra `ollama: "unknown"` (3/3 lan), con re-review do lai duoc `up` khi
 * Ollama chay ⇒ gia tri DOI THEO LUC, va `down` CHUA TUNG do duoc (ERRATA #2 muc 4).
 * Neu man chi hien voi `down` thi tren may nay man KHONG BAO GIO hien (plan dong 2737).
 * ⇒ Ba bai, ba trang thai; va `unknown` phai noi "chua do duoc", KHONG duoc bia "da tat".
 *
 * Vi sao jsdom chu khong Playwright: trinh duyet THAT BAT KHA o moi truong nay
 * (Chromium chet o `FATAL:mojo ... platform_channel.cc:187 ... Access is denied (0x5)`
 * vi Mojo dung NAMED PIPE — ERRATA #5 muc 3). jsdom KHONG phai trinh duyet: KHONG layout,
 * KHONG CSS that. ⇒ Tep nay do duoc HANH VI (panel co hien khong, chu nao, chu nao bi
 * loai), KHONG do duoc HINH (van cheo co ve ra khong, cham do o dau, panel cao bao nhieu).
 *
 * LUAT DOM (ERRATA #9 muc 1/6) — tep nay TU CHUA va khong dua vao thu tu:
 *   - MOI hook dat/tra global nam TRONG `describe()`: duoi `--test-isolation=none`, hook
 *     cap TEP bi node:test keo len GOC ca luot (moi `before` truoc MOI bai, moi `after`
 *     sau moi bai) — do bang dong ho chung, khong phai suy dien.
 *   - `setupDom`/`teardownDom` cua CHINH tep nay; khong gia dinh jsdom cua tep khac con
 *     song, va khong de lai global nao cho tep sau.
 *   - `console.error`/`console.warn` bi TAM THAY de bat tieng on va duoc TRA LAI trong
 *     `after` (chung cung la global: ERRATA #7 muc 3).
 *   - LUON chay TOAN BO `npm test`, khong chay le tep.
 *
 * ⚠️ KHONG co `@testing-library/user-event`, KHONG co `jest-dom`, KHONG co `vitest`
 * trong repo ⇒ `fireEvent` + `node:assert/strict`. KHONG dua DOM node song vao `assert`
 * (ERRATA #15 muc 1: 218 697 ms roi OOM) — dem so luong / doc `textContent` / `className`.
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import type { Server, ServerResponse } from "node:http";
import type { AddressInfo, Socket } from "node:net";

import type { EngineSpec, Registry, Status } from "../api/types.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

// ---------------------------------------------------------------------------
// Du lieu THAT dung hinh dang backend (`types.ts`, doc tu `routes_registry.py`)
// ---------------------------------------------------------------------------

const STATUS_HTTP: Status = {
  queue_depth: 1,
  running: [7],
  current_phase: "asr:faster-whisper-large",
  phase_switches: 3,
  vram: null,
  ollama: "unknown",
};

/** `available` CHI co tren `kind == "mt"` ⇒ hai spec ASR duoi day KHONG co khoa do. */
const REGISTRY_HTTP: Registry = {
  asr: [
    {
      id: "faster-whisper-large",
      label: "Faster Whisper Large",
      kind: "asr",
      runtime: "inprocess",
      model_ref: "large-v3",
      vram_mb: 0,
      langs: ["zh", "en"],
      capabilities: {},
      opts: {},
    },
  ],
  mt: [
    {
      id: "opus-mt",
      label: "OPUS-MT",
      kind: "mt",
      runtime: "inprocess",
      model_ref: "Helsinki-NLP/opus-mt-zh-vi",
      vram_mb: 0,
      langs: ["zh"],
      capabilities: { available: true, prompt_version: "raw-p1" },
      opts: {},
    },
    {
      id: "qwen2.5-7b",
      label: "Qwen 2.5 7B",
      kind: "mt",
      runtime: "ollama",
      model_ref: "qwen2.5:7b",
      vram_mb: 0,
      langs: ["zh"],
      capabilities: { available: false, prompt_version: "raw-p1" },
      opts: {},
    },
  ],
};

/** Mot spec toi thieu cho cac bai chi dung PROP (khong qua HTTP). */
function spec(
  id: string,
  label: string,
  runtime: "inprocess" | "ollama",
  available?: boolean,
  kind: "asr" | "mt" = "mt",
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
    langs: ["zh"],
    capabilities,
    opts: {},
  };
}

const SPECS: EngineSpec[] = [
  spec("opus-mt", "OPUS-MT", "inprocess", true),
  spec("qwen2.5-3b", "Qwen 2.5 3B", "ollama", false),
];

/**
 * FIXTURE MAU THUAN (`Important #1` cua review Task 10): `runtime` va `available` noi NGUOC
 * nhau o CA HAI chieu.
 *
 * VI SAO BAT BUOC: hom nay hai tieu chi TRUNG ket qua tren du lieu that — panel chi hien khi
 * Ollama `down`/`unknown`, ma luc do `ollama_available()` = ∅ nen MOI spec `runtime === "ollama"`
 * deu co `available === false` (`app/main.py::_mark_availability`). Vi the mutation `M1` cua
 * reviewer (phan loai theo `runtime` thay vi `available`) **SONG SOT: 0 bai do**. Mot fixture
 * trong do hai tieu chi mau thuan la thu DUY NHAT phan biet duoc hai cach hieu.
 *
 *   - `opus-mt`: `runtime === "inprocess"` NHUNG `available === false` (model chua pull).
 *   - `qwen2.5-3b`: `runtime === "ollama"` NHUNG `available === true` (tien trinh song + da pull).
 */
const SPECS_MAU_THUAN: EngineSpec[] = [
  spec("opus-mt", "OPUS-MT", "inprocess", false),
  spec("qwen2.5-3b", "Qwen 2.5 3B", "ollama", true),
];

/**
 * FIXTURE DUNG HINH DANG THAT cua `/api/registry` (`Important #2`): registry that co **ASR**
 * (Faster-Whisper x3 + SenseVoice — ca bon **KHONG co khoa `available`**, vi
 * `_mark_availability` chi ghi khoa do cho `kind == "mt"`) **lan MT in-process** (OPUS-MT).
 *
 * VI SAO BAT BUOC: fixture `SPECS` o tren chi co MT ⇒ loi "panel noi ASR dich duoc" KHONG THE
 * lo ra (ERRATA #31 muc 3: fixture phai co DUNG hinh dang that — du loai `kind`).
 */
const SPECS_ASR_MT: EngineSpec[] = [
  spec("fw-large-v3-turbo", "Faster-Whisper large-v3-turbo", "inprocess", undefined, "asr"),
  spec("sensevoice-small", "SenseVoice-Small", "inprocess", undefined, "asr"),
  spec("opus-mt", "OPUS-MT", "inprocess", true),
  spec("qwen2.5-3b", "Qwen 2.5 3B", "ollama", false),
];

// ---------------------------------------------------------------------------
// Server `node:http` trong tien trinh — dem duoc request nao da THUC SU di ra
// ---------------------------------------------------------------------------

const dem = { status: 0, registry: 0, sources: 0, jobs: 0, stream: 0 };
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
  if (url.startsWith("/api/status")) {
    dem.status += 1;
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(STATUS_HTTP));
    return;
  }
  if (url.startsWith("/api/registry")) {
    dem.registry += 1;
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(REGISTRY_HTTP));
    return;
  }
  if (url.startsWith("/api/sources")) {
    dem.sources += 1;
    res.writeHead(200, { "content-type": "application/json" });
    res.end("[]");
    return;
  }
  if (url.startsWith("/api/jobs")) {
    dem.jobs += 1;
    res.writeHead(200, { "content-type": "application/json" });
    res.end("[]");
    return;
  }
  res.writeHead(404, { "content-type": "text/plain" });
  res.end("khong co route nay");
});

server.on("connection", (socket) => {
  sockets.add(socket);
  socket.on("close", () => sockets.delete(socket));
});

// ---------------------------------------------------------------------------
// Helper doc DOM (dem so luong, KHONG so sanh node)
// ---------------------------------------------------------------------------

const consoleGoc = { error: console.error, warn: console.warn };
const tiengOn: string[] = [];

/**
 * Mo ta mot gia tri ma KHONG goi sau vao no: `console.error` cua React nhan ca node DOM,
 * va doc sau vao mot node cua jsdom da `close()` la tu chuoc loi.
 */
function mo(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined) return "undefined";
  if (value === null) return "null";
  const kind = typeof value;
  if (kind !== "object" && kind !== "function") return String(value);
  return Object.prototype.toString.call(value);
}

let render: (ui: unknown) => { container: HTMLElement; unmount: () => void };
let fireEvent: { click: (el: Element) => void };
let cleanup: () => void;
let waitFor: (cb: () => void, options?: { timeout?: number; interval?: number }) => Promise<void>;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let StatusStrip: (props: unknown) => unknown;
let OllamaDown: (props: unknown) => unknown;
let Header: (props: unknown) => unknown;
let App: () => unknown;

/** `textContent` cua phan tu DAU TIEN khop `chon` — khong hoi ca DOM. */
function chu(goc: HTMLElement, chon: string): string {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.textContent ?? "";
}

/** Thuoc tinh cua phan tu DAU TIEN khop `chon`. */
function thuocTinh(goc: HTMLElement, chon: string, ten: string): string | null {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.getAttribute(ten);
}

/** Dem, khong so sanh NODE (ERRATA #15 muc 1: `assert.equal(<node>, null)` la bom hen gio). */
function khongCo(goc: HTMLElement, chon: string, msg: string): void {
  assert.equal(goc.querySelectorAll(chon).length, 0, msg);
}

/** Cho mot chuoi xuat hien trong DOM THAT — `waitFor` co han nen khong treo vo han. */
async function choChu(goc: HTMLElement, chuoi: string): Promise<void> {
  await waitFor(
    () => {
      const text = goc.textContent ?? "";
      assert.ok(text.includes(chuoi),
        `chua thay "${chuoi}" trong DOM; do duoc: ${JSON.stringify(text.slice(0, 400))}`);
    },
    { timeout: 8000, interval: 20 },
  );
}

/** `status` gia cho cac bai chi dung PROP — cung hinh dang `Status` cua backend. */
function status(ollama: Status["ollama"], vram: number | null = null): Status {
  return {
    queue_depth: 0,
    running: [],
    current_phase: null,
    phase_switches: 0,
    vram,
    ollama,
  };
}

describe("§4.8 trang thai Ollama: dai trang thai + panel hang nhat + dropdown engine", () => {
  let origin = "";

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
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    waitFor = api.waitFor;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const man: any = await import("./OllamaDown.tsx");
    StatusStrip = man.StatusStrip;
    OllamaDown = man.OllamaDown;
    const shell: any = await import("../shell/Header.tsx");
    Header = shell.Header;
    const app: any = await import("../shell/App.tsx");
    App = app.App;

    console.error = (...args: unknown[]): void => {
      tiengOn.push(`error: ${args.map((a) => mo(a)).join(" ")}`);
    };
    console.warn = (...args: unknown[]): void => {
      tiengOn.push(`warn: ${args.map((a) => mo(a)).join(" ")}`);
    };
  });

  beforeEach(() => {
    tiengOn.length = 0;
    dem.status = 0;
    dem.registry = 0;
    dem.sources = 0;
    dem.jobs = 0;
    dem.stream = 0;
  });

  afterEach(() => {
    cleanup();
  });

  after(async () => {
    console.error = consoleGoc.error;
    console.warn = consoleGoc.warn;
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

  // -------------------------------------------------------------------------
  // DAI TRANG THAI — ba trang thai, ba nghia KHAC NHAU
  // -------------------------------------------------------------------------

  it("dai trang thai noi DUNG ba trang thai ollama, khong gop `unknown` vao `down`", () => {
    const up = render(taoPhanTu(StatusStrip, { status: status("up", 3200) }));
    assert.equal(thuocTinh(up.container, ".stt", "data-ollama"), "up");
    assert.ok(chu(up.container, ".stt__ollama").includes("đang chạy"),
      "ollama === 'up' phai noi ro la dang chay");
    assert.ok(chu(up.container, ".stt__vram").includes("3200"),
      "vram co so thi phai hien SO do (khong duoc im lang)");
    up.unmount();

    const down = render(taoPhanTu(StatusStrip, { status: status("down") }));
    assert.equal(thuocTinh(down.container, ".stt", "data-ollama"), "down");
    assert.ok(chu(down.container, ".stt__ollama").includes("mất kết nối"),
      "ollama === 'down' phai noi ro la mat ket noi");
    assert.ok(chu(down.container, ".stt__vram").includes("chưa đo được"),
      "vram === null la CHUA DO DUOC (GĐ1a), khong duoc bia mot con so");
    down.unmount();

    const unknown = render(taoPhanTu(StatusStrip, { status: status("unknown") }));
    assert.equal(thuocTinh(unknown.container, ".stt", "data-ollama"), "unknown");
    assert.ok(chu(unknown.container, ".stt__ollama").includes("chưa đo được"),
      "ollama === 'unknown' phai noi 'chua do duoc', KHONG duoc noi 'mat ket noi'");
    assert.ok(!chu(unknown.container, ".stt__ollama").includes("mất kết nối"),
      "gop `unknown` vao `down` la BIA mot su that chua do");
    unknown.unmount();

    assert.deepEqual(tiengOn, [], "dai trang thai khong duoc sinh tieng on console");
  });

  it("dai trang thai khi status === null noi 'chua doc duoc' — gia tri THU TU, KHAC `unknown`", () => {
    // `status === null` = request con dang bay (hoac loi mang): CHUA DOC XONG. No KHAC
    // `unknown` ("backend da tra loi: chua do duoc ollama"). Truoc vong sua nay gia tri thu
    // tu `chua-doc-duoc` khong co LUAT CSS nao nen trung mau voi `unknown` (Minor #1).
    const { container, unmount } = render(taoPhanTu(StatusStrip, { status: null }));

    assert.equal(thuocTinh(container, ".stt", "data-ollama"), "chua-doc-duoc",
      "status === null phai mang gia tri RIENG, khong duoc dan nhan thanh `unknown`");
    assert.ok(chu(container, ".stt__ollama").includes("chưa đọc được"),
      "chua doc xong phai noi 'chua doc duoc'");
    assert.ok(!chu(container, ".stt__ollama").includes("chưa đo được"),
      "`chua-doc-duoc` KHONG duoc dung chung cau voi `unknown` — hai su that khac nhau");
    unmount();
  });

  it("Header dat dai trang thai vao header, canh ten ban lam viec", () => {
    const { container } = render(taoPhanTu(Header, { status: status("unknown") }));

    const head = chu(container, ".shell__head");
    assert.ok(head.includes("PHÒNG THU BIÊN TẬP"),
      "header phai giu ten ban lam viec — dai trang thai KHONG duoc thay no");
    assert.ok(head.includes("chưa đo được"),
      "header phai THAT SU dat dai trang thai vao, khong chi import roi bo quen");
    assert.equal(thuocTinh(container, ".stt", "data-ollama"), "unknown",
      "dai trang thai trong header phai mang dung trang thai nhan duoc");
  });

  // -------------------------------------------------------------------------
  // PANEL — hien voi `down` VA `unknown`, KHONG hien voi `up`
  // -------------------------------------------------------------------------

  it("panel KHONG hien khi ollama === 'up', va KHONG hien khi chua doc duoc status", () => {
    const up = render(taoPhanTu(OllamaDown, { status: status("up"), specs: SPECS, onRetry: () => {} }));
    khongCo(up.container, ".od", "ollama === 'up' thi KHONG duoc co panel nao");
    up.unmount();

    // `status === null` = CHUA DOC DUOC (request dang bay hoac loi). Do la trang thai
    // KHAC voi `unknown` (backend da tra loi, va cau tra loi la "chua do duoc ollama"):
    // khong duoc suy mot trong hai tu cai kia.
    const chuaDoc = render(taoPhanTu(OllamaDown, { status: null, specs: SPECS, onRetry: () => {} }));
    khongCo(chuaDoc.container, ".od", "chua doc duoc status thi khong duoc khang dinh gi");
    chuaDoc.unmount();
  });

  it("panel HIEN khi ollama === 'down'", () => {
    const { container } = render(taoPhanTu(OllamaDown, {
      status: status("down"),
      specs: SPECS,
      onRetry: () => {},
    }));

    assert.equal(container.querySelectorAll(".od").length, 1, "ollama === 'down' PHAI hien panel");
    assert.equal(thuocTinh(container, ".od", "data-ollama"), "down");
    assert.ok(chu(container, ".od__tieu-de").includes("Không kết nối được Ollama"),
      "tieu de phai la cau nguoi dung doc duoc, khong chi la ma trang thai");
  });

  it("panel HIEN khi ollama === 'unknown' va noi 'chua do duoc', KHONG bia 'down'", () => {
    const { container } = render(taoPhanTu(OllamaDown, {
      status: status("unknown"),
      specs: SPECS,
      onRetry: () => {},
    }));

    // Day la bai ma plan dong 2737 noi ro: chi khoa theo `down` thi man KHONG BAO GIO hien
    // tren may nay (do duoc `/api/status` -> `unknown`).
    assert.equal(container.querySelectorAll(".od").length, 1, "ollama === 'unknown' PHAI hien panel");
    assert.equal(thuocTinh(container, ".od", "data-ollama"), "unknown",
      "panel phai MANG dung trang thai that, khong duoc dan nhan thanh 'down'");
    assert.ok(chu(container, ".od__tieu-de").includes("Chưa đo được Ollama"),
      "tieu de cua `unknown` phai noi 'chua do duoc'");
    assert.ok(!chu(container, ".od__tieu-de").includes("Không kết nối được Ollama"),
      "`unknown` KHONG duoc dung chung tieu de voi `down` — do la hai su that khac nhau");
  });

  // -------------------------------------------------------------------------
  // NOI DUNG PANEL — ba dieu nguoi dung PHAI doc duoc (§12.6, spec UI §4.8)
  // -------------------------------------------------------------------------

  it("panel noi ro cai gi CON chay duoc: engine in-process (OPUS-MT)", () => {
    const { container } = render(taoPhanTu(OllamaDown, {
      status: status("down"),
      specs: SPECS,
      onRetry: () => {},
    }));

    const con = chu(container, ".od__con");
    assert.ok(con.includes("OPUS-MT"), `phai NEU TEN engine in-process; do duoc: ${JSON.stringify(con)}`);
    assert.ok(/còn dùng được/i.test(con), "phai noi RO la con dung duoc, khong chi liet ke ten");
    assert.ok(!con.includes("Qwen 2.5 3B"),
      "engine CAN Ollama khong duoc nam trong danh sach 'con chay duoc'");
  });

  it("panel noi ro cai gi KHONG chay duoc: engine can Ollama (Qwen)", () => {
    const { container } = render(taoPhanTu(OllamaDown, {
      status: status("down"),
      specs: SPECS,
      onRetry: () => {},
    }));

    const khong = chu(container, ".od__khong");
    assert.ok(khong.includes("Qwen 2.5 3B"),
      `phai NEU TEN engine can Ollama; do duoc: ${JSON.stringify(khong)}`);
    assert.ok(/không dùng được/i.test(khong), "phai noi RO la khong dung duoc");
    assert.ok(!khong.includes("OPUS-MT"),
      "engine in-process khong duoc nam trong danh sach 'khong chay duoc'");
  });

  it("phan loai theo `available`, KHONG theo `runtime`: FIXTURE MAU THUAN (ca hai chieu)", () => {
    // `SPECS_MAU_THUAN`: `runtime` va `available` noi nguoc nhau ⇒ bai nay phan biet duoc
    // hai cach hieu. Mutation `M1` cua reviewer (doi sang `runtime`) lam bai nay DO.
    const { container, unmount } = render(taoPhanTu(OllamaDown, {
      status: status("down"),
      specs: SPECS_MAU_THUAN,
      onRetry: () => {},
    }));

    const con = chu(container, ".od__con");
    const khong = chu(container, ".od__khong");

    // `runtime === "ollama"` NHUNG `available === true` (tien trinh song + model da pull)
    // ⇒ PHAI nam trong "con dung duoc". Suy tu `runtime` se BO sot no.
    assert.ok(con.includes("Qwen 2.5 3B"),
      `engine co available === true phai nam trong "con dung duoc"; do duoc: ${JSON.stringify(con)}`);
    assert.ok(!con.includes("OPUS-MT"),
      `engine co available === false KHONG duoc nam trong "con dung duoc"; do duoc: ${JSON.stringify(con)}`);
    // `runtime === "inprocess"` NHUNG `available === false` (model chua pull)
    // ⇒ PHAI nam trong "khong dung duoc". Suy tu `runtime` se liet ke no la dung duoc.
    assert.ok(khong.includes("OPUS-MT"),
      `engine co available === false phai nam trong "khong dung duoc"; do duoc: ${JSON.stringify(khong)}`);
    assert.ok(!khong.includes("Qwen 2.5 3B"),
      `engine co available === true KHONG duoc nam trong "khong dung duoc"; do duoc: ${JSON.stringify(khong)}`);

    unmount();
  });

  it("TACH theo `kind`: `.od__con` CHI neu MT — ASR di vao cau 'Boc bang' (hinh dang registry THAT)", () => {
    // SPECS_ASR_MT co ASR (KHONG co khoa `available`) + MT in-process: dung hinh dang that
    // cua `/api/registry`. Cau "… van DICH duoc" chi duoc neu engine `kind === "mt"`.
    const { container, unmount } = render(taoPhanTu(OllamaDown, {
      status: status("down"),
      specs: SPECS_ASR_MT,
      onRetry: () => {},
    }));

    const bocBang = chu(container, ".od__boc-bang");
    assert.ok(bocBang.includes("Bóc băng"),
      `phai co CAU RIENG cho boc bang (spec UI §4.8); do duoc: ${JSON.stringify(bocBang)}`);
    assert.ok(bocBang.includes("Faster-Whisper large-v3-turbo"),
      `ASR phai duoc neu ten trong cau BOC BANG; do duoc: ${JSON.stringify(bocBang)}`);
    assert.ok(bocBang.includes("SenseVoice-Small"),
      `ASR thu hai phai duoc neu ten trong cau BOC BANG; do duoc: ${JSON.stringify(bocBang)}`);
    assert.ok(!bocBang.includes("OPUS-MT"),
      `engine DICH khong duoc nam trong cau BOC BANG; do duoc: ${JSON.stringify(bocBang)}`);

    const con = chu(container, ".od__con");
    assert.ok(con.includes("OPUS-MT"),
      `MT available === true phai duoc neu ten; do duoc: ${JSON.stringify(con)}`);
    assert.ok(/còn dùng được/i.test(con), "cau nay phai noi RO la con dung duoc");
    assert.ok(!con.includes("Faster-Whisper") && !con.includes("SenseVoice"),
      `ASR KHONG dich cau nao ⇒ khong duoc nam trong cau "van dich duoc"; do duoc: ${JSON.stringify(con)}`);

    const khong = chu(container, ".od__khong");
    assert.ok(khong.includes("Qwen 2.5 3B"),
      `MT available === false phai nam trong "khong dung duoc"; do duoc: ${JSON.stringify(khong)}`);
    assert.ok(!khong.includes("Faster-Whisper") && !khong.includes("SenseVoice"),
      `ASR van boc bang duoc ⇒ khong duoc nam trong "khong dung duoc"; do duoc: ${JSON.stringify(khong)}`);

    unmount();
  });

  it("khong co engine nao (specs = []): HAI cau noi RO 'khong co engine nao', khong de trong", () => {
    // Do loi do phu `X8`: bo nhanh danh sach RONG cua `lietKe` ⇒ 0 bai do. Bai nay dong no.
    const { container, unmount } = render(taoPhanTu(OllamaDown, {
      status: status("down"),
      specs: [],
      onRetry: () => {},
    }));

    const con = chu(container, ".od__con");
    const khong = chu(container, ".od__khong");
    assert.ok(con.includes("không có engine nào"),
      `danh sach rong phai NOI RA, khong duoc de trong im lang; do duoc: ${JSON.stringify(con)}`);
    assert.ok(khong.includes("không có engine nào"),
      `danh sach rong phai NOI RA, khong duoc de trong im lang; do duoc: ${JSON.stringify(khong)}`);
    unmount();
  });

  it("panel noi ro CACH SUA — ca khi `down` LAN khi `unknown`", () => {
    for (const trangThai of ["down", "unknown"] as const) {
      const { container, unmount } = render(taoPhanTu(OllamaDown, {
        status: status(trangThai),
        specs: SPECS,
        onRetry: () => {},
      }));

      const sua = chu(container, ".od__sua");
      assert.ok(sua.includes("Cách sửa"),
        `panel (${trangThai}) phai noi ro CACH SUA, khong chi bao loi`);
      assert.ok(sua.includes("ollama serve"),
        `cach sua phai la mot viec LAM DUOC (lenh cu the); do duoc: ${JSON.stringify(sua)}`);
      unmount();
    }
    assert.deepEqual(tiengOn, [], "panel khong duoc sinh tieng on console");
  });

  it("panel co nut THU LAI that (goi lai duoc), khong phai mot nut chet", () => {
    let soLan = 0;
    const { container, unmount } = render(taoPhanTu(OllamaDown, {
      status: status("down"),
      specs: SPECS,
      onRetry: () => {
        soLan += 1;
      },
    }));

    const nut = container.querySelector('[data-testid="od-thu-lai"]');
    assert.ok(nut !== null, "spec UI §4.8 co `[ Thử lại ]` — phai co nut that");
    fireEvent.click(nut as Element);
    assert.equal(soLan, 1, "bam 'Thu lai' phai goi ra ngoai THAT, khong duoc nuot im lang");
    unmount();
  });

  // -------------------------------------------------------------------------
  // HINH THUC — ghim LUAT CSS, khong chi ghim ten lop (ERRATA #15 muc 3)
  // -------------------------------------------------------------------------

  it("HINH THUC: LUAT CSS cua dai trang thai + panel CO THAT trong `app.css`", () => {
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const tokensCss = readFileSync(new URL("../styles/tokens.css", import.meta.url), "utf8");

    const moc = "§4.8 Trạng thái Ollama (Task 10)";
    const viTri = appCss.indexOf(moc);
    assert.ok(viTri > 0, "app.css phai co KHOI LUAT cua Task 10, khong chi co class trong TSX");
    // ⚠️ Cat khối tới MỐC `/* ──` KẾ TIẾP, KHONG tới hết tệp (Minor #3b): luật của task SAU
    // them vao cuoi tệp sẽ tự chui vào "khối Task 10" và bị đem đi kiểm token.
    const mocKe = appCss.indexOf("/* ──", viTri + 1);
    const khoi = mocKe === -1 ? appCss.slice(viTri) : appCss.slice(viTri, mocKe);

    for (const chon of [".stt {", ".stt__cham {", ".od {", ".od__van {", ".od__sua {"]) {
      assert.ok(khoi.includes(chon), `app.css thieu luat "${chon}"`);
    }
    // Luat THAT, khong phai ten lop: day la nhung khai bao quyet dinh HINH DANG.
    assert.match(khoi, /\.stt__cham \{[^}]*border-radius: 50%/,
      "cham trang thai phai la mot CHAM (khong phai mot o vuong)");
    assert.match(khoi, /\.stt\[data-ollama="down"\] \.stt__cham \{[^}]*background: var\(--fault\)/,
      "`down` phai co LUAT VE THAT (mau loi), khong chi co thuoc tinh `data-ollama`");
    assert.match(khoi, /\.stt\[data-ollama="unknown"\] \.stt__cham \{[^}]*background: var\(--ink-2\)/,
      "`unknown` phai KHAC `down` ve hinh thuc: chua do duoc thi khong duoc to do nhu mot loi da xac nhan");
    // Gia tri THU TU `chua-doc-duoc` (status === null) phai co LUAT RIENG, va luat do phai
    // KHAC `unknown` — neu khong thi "chua doc xong" trung mau voi "chua do duoc" (Minor #1).
    const luatChuaDoc = /\.stt\[data-ollama="chua-doc-duoc"\] \.stt__cham \{([^}]*)\}/.exec(khoi);
    assert.ok(luatChuaDoc !== null,
      "`chua-doc-duoc` phai co LUAT CSS rieng, khong duoc roi ve mac dinh trung voi `unknown`");
    assert.ok(!/background:\s*var\(--ink-2\)/.test(luatChuaDoc[1]),
      "`chua-doc-duoc` phai KHAC `unknown`: mot cham to cung mau thi khong phan biet duoc hai thu");
    assert.match(khoi, /\.od__van \{[^}]*repeating-linear-gradient/,
      "spec UI §4.8 doi DAI VAN CHEO `--fault` o dinh cua so, khong phai mot duong ke lien");
    assert.match(khoi, /\.od__van \{[^}]*var\(--fault\)/,
      "van cua trang thai loi phai lay mau `--fault`");
    assert.match(khoi, /\.od__sua \{[^}]*border-left/,
      "dong CACH SUA phai co luat ve that (moc o le), khong chi la mot <p>");

    // Token nao khoi nay dung thi phai co dinh nghia THAT trong `tokens.css`.
    const dung = [...new Set([...khoi.matchAll(/var\((--[a-z0-9-]+)\)/g)].map((m) => m[1] ?? ""))];
    assert.ok(dung.length >= 4, `khoi Task 10 phai dung token that, do duoc ${dung.length}`);
    for (const token of dung) {
      assert.ok(tokensCss.includes(`${token}:`),
        `token ${token} duoc dung nhung KHONG dinh nghia trong tokens.css`);
    }
  });

  // -------------------------------------------------------------------------
  // DUONG THAT: App -> `/api/status` + `/api/registry` qua HTTP
  // -------------------------------------------------------------------------

  it("App goi /api/status + /api/registry THAT va do du lieu do vao dai trang thai + panel", async () => {
    const { container, unmount } = render(taoPhanTu(App));

    // `current_phase` KHONG the den tu dau khac ngoai HTTP: no nam trong than JSON cua
    // server cua bai nay, va khong co prop nao mang no vao.
    await choChu(container, "asr:faster-whisper-large");
    await choChu(container, "chưa đo được");
    assert.equal(thuocTinh(container, ".stt", "data-ollama"), "unknown",
      "trang thai `unknown` cua server phai di nguyen ven tới DOM");

    // Panel hien vi `unknown` (khong phai vi `down`), va ten engine lay tu `/api/registry`.
    assert.equal(container.querySelectorAll(".od").length, 1,
      "`unknown` tu HTTP phai lam panel HIEN — day chinh la dieu plan dong 2737 doi");
    await choChu(container, "OPUS-MT");
    assert.ok(chu(container, ".od__khong").includes("Qwen 2.5 7B"),
      "engine `available === false` trong registry that phai duoc neu la KHONG chay duoc");

    // BANG CHUNG duong THAT: server dem duoc request. Khong co no thi bai nay xanh vi
    // mot ly do khac (du lieu den tu dau do khong phai HTTP).
    assert.equal(dem.status, 1, `App phai goi /api/status dung MOT lan; do duoc ${dem.status}`);
    assert.equal(dem.registry, 1, `App phai goi /api/registry dung MOT lan; do duoc ${dem.registry}`);

    // Nut "Thu lai" phai THAT SU doc lai tu server (spec UI §4.8) — khong phai nut trang tri.
    fireEvent.click(container.querySelector('[data-testid="od-thu-lai"]') as Element);
    await waitFor(
      () => {
        assert.equal(dem.status, 2, `bam 'Thu lai' phai doc lai /api/status; do duoc ${dem.status}`);
      },
      { timeout: 8000, interval: 20 },
    );

    assert.deepEqual(tiengOn, [], "render <App/> THAT khong duoc sinh tieng on console");
    unmount();
  });
});
