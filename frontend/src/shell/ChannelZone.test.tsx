/**
 * Test `<ChannelZone/>` THAT trong jsdom — **CHỌN ĐƯỢC KÊNH** (Task W1).
 *
 * VI SAO TỆP NÀY LÀ TỆP MỚI: trước W1, vùng KÊNH chỉ HIỆN các kênh (`<li>` + text), không
 * có đường nào CHỌN ⇒ `ui.channelId` luôn `null` và **mọi màn chỉ hiện trạng thái rỗng**
 * (ERRATA #32). Bài "bấm một kênh ⇒ màn Biên tập nhận bản ghi THẬT" nằm ở `App.test.tsx`
 * (nó cần cả shell + server thật); tệp này ghim ĐÚNG hợp đồng của control.
 *
 * ## Bốn điều tệp này ghim
 *
 *  1. **Mỗi mục là `<button type="button">`** — không phải `onClick` trên `<div>`/`<li>`:
 *     một affordance chỉ bấm chuột được là một affordance KHÔNG TỒN TẠI với bàn phím
 *     (spec UI §7/§12.5), và đó là lý do brief cấm `div` + `role`.
 *  2. **`aria-pressed` chỉ đúng ở mục đang chọn** — trạng thái máy đọc được.
 *  3. **Một dấu NHÌN THẤY được ở mục đang chọn** (glyph `▸`), KHÔNG chỉ đổi màu: màu một
 *     mình là thông tin chỉ-có-hình (ERRATA #15 muc 3 + spec UI §7).
 *  4. **`onSelect(id)` báo ĐÚNG id** — và component KHÔNG tự giữ "kênh đang chọn": nó là
 *     component ĐIỀU KHIỂN, nguồn sự thật là `UiState.channelId`.
 *
 * ## LUẬT DOM (ERRATA #9 muc 1/6): tệp này TỰ CHỨA
 *
 * Hook đặt/trả global nằm TRONG `describe()`; `console.error`/`console.warn` được TRẢ LẠI
 * trong `after`; KHÔNG đưa node DOM sống vào `assert` (ERRATA #14 muc 3).
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import type { Job, Source } from "../api/types.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

/** Hai kênh THẬT đúng tám khoá của `routes_sources._source_json`. */
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

function makeJob(id: number, type: Job["type"], state: Job["state"], sourceId: number): Job {
  return {
    id,
    workspace: 1,
    type,
    engine: type === "asr" ? "faster-whisper-large" : null,
    phase: type === "asr" ? "asr:faster-whisper-large" : `${type}:-`,
    state,
    cancel_requested: false,
    attempts: 1,
    progress: 0.5,
    log_tail: "",
    error: null,
    payload: { source_id: sourceId, lang: "zh" },
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

/**
 * Job của CẢ HAI kênh: bản đồ bước phải theo TỪNG kênh, không phải một cục chung.
 *
 * Kênh 1 có `asr` #3 `done` RỒI `asr` #7 `running` (chạy lại — chuyện thật) ⇒ trạng thái
 * hiện tại là "đang chạy". Kênh 2 mới chỉ có job `ingest` ⇒ `phiên âm` phải là "chưa có job".
 */
const JOBS = new Map<number, Job>([
  [3, makeJob(3, "asr", "done", 1)],
  [5, makeJob(5, "ingest", "done", 1)],
  [7, makeJob(7, "asr", "running", 1)],
  [6, makeJob(6, "ingest", "queued", 2)],
]);

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

let render: (ui: unknown) => { container: HTMLElement; unmount: () => void };
let fireEvent: { click: (el: Element) => void };
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let ChannelZone: (props: unknown) => unknown;

/** Mục kênh (nút) của một kênh, tra theo CHỮ trong mục — không theo thứ tự mảng. */
function mucCua(container: HTMLElement, chuoi: string): HTMLButtonElement {
  const khop = [...container.querySelectorAll(".ch__item")].find(
    (el) => (el.textContent ?? "").includes(chuoi),
  );
  assert.ok(khop !== undefined, `khong thay muc kenh nao chua "${chuoi}"`);
  return khop as HTMLButtonElement;
}

/** Dấu NHÌN THẤY được của mục đang chọn (glyph trong `.ch__dau`), RỖNG nếu không chọn. */
function dauCua(muc: Element): string {
  return (muc.querySelector(".ch__dau")?.textContent ?? "").trim();
}

describe("ChannelZone: chon duoc KENH (Task W1)", () => {
  before(async () => {
    teardownDom();
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const man: any = await import("./ChannelZone.tsx");
    ChannelZone = man.ChannelZone;

    console.error = (...args: unknown[]): void => {
      tiengOn.push(`error: ${args.map(mo).join(" ")}`);
    };
    console.warn = (...args: unknown[]): void => {
      tiengOn.push(`warn: ${args.map(mo).join(" ")}`);
    };
  });

  beforeEach(() => {
    tiengOn.length = 0;
  });

  afterEach(() => {
    cleanup();
  });

  after(() => {
    console.error = consoleGoc.error;
    console.warn = consoleGoc.warn;
    teardownDom();
  });

  it("moi muc la `<button type=\"button\">` (ban phim dung duoc), va giu NGUYEN trang thai tung buoc", () => {
    const { container, unmount } = render(
      taoPhanTu(ChannelZone, {
        sources: SOURCES,
        jobs: JOBS,
        loading: false,
        error: null,
        selectedId: null,
        onSelect: () => {},
      }),
    );

    const mucs = [...container.querySelectorAll(".ch__item")];
    assert.equal(mucs.length, 2, "hai kenh ⇒ hai muc");
    for (const muc of mucs) {
      assert.equal(muc.tagName, "BUTTON", "muc kenh phai la NUT that");
      assert.equal(muc.getAttribute("type"), "button", "`type=button`: khong duoc submit form nao");
    }

    // BAN DO BUOC duoc giu nguyen: job co id LON NHAT cua moi buoc la trang thai HIEN TAI.
    const kenh1 = mucCua(container, "kenh-mot.wav").textContent ?? "";
    assert.ok(kenh1.includes("phiên âm: đang chạy"), `kenh 1 phai "phiên âm: đang chạy"; do duoc ${JSON.stringify(kenh1)}`);
    assert.ok(!kenh1.includes("phiên âm: xong"), "job asr #3 la LICH SU, khong duoc hien");
    const kenh2 = mucCua(container, "vid.example/kenh-hai").textContent ?? "";
    assert.ok(kenh2.includes("phiên âm: chưa có job"), `kenh 2 chua co job asr; do duoc ${JSON.stringify(kenh2)}`);

    assert.deepEqual(tiengOn, [], "render vung KENH khong duoc sinh tieng on console");
    unmount();
  });

  it("`aria-pressed` va DAU NHIN THAY duoc chi o muc DANG CHON", () => {
    const { container, unmount } = render(
      taoPhanTu(ChannelZone, {
        sources: SOURCES,
        jobs: JOBS,
        loading: false,
        error: null,
        selectedId: 1,
        onSelect: () => {},
      }),
    );

    const chon = mucCua(container, "kenh-mot.wav");
    const khongChon = mucCua(container, "vid.example/kenh-hai");

    assert.equal(chon.getAttribute("aria-pressed"), "true", "muc dang chon phai `aria-pressed=true`");
    assert.equal(khongChon.getAttribute("aria-pressed"), "false", "muc khong chon phai `aria-pressed=false`");

    // Dau NHIN THAY duoc: mot GLYPH, khong phai chi mau (spec UI §7 + ERRATA #15 muc 3).
    assert.equal(dauCua(chon), "▸", "muc dang chon phai co DAU nhin thay duoc");
    assert.equal(dauCua(khongChon), "", "muc khong chon KHONG duoc co dau do");

    assert.deepEqual(tiengOn, [], "hien muc dang chon khong duoc sinh tieng on console");
    unmount();
  });

  it("bam mot muc ⇒ `onSelect(id)` DUNG id; va doi `selectedId` thi dau CHUYEN theo (component dieu khien)", () => {
    const daChon: number[] = [];
    const { container, unmount } = render(
      taoPhanTu(ChannelZone, {
        sources: SOURCES,
        jobs: JOBS,
        loading: false,
        error: null,
        selectedId: null,
        onSelect: (id: number): void => {
          daChon.push(id);
        },
      }),
    );

    fireEvent.click(mucCua(container, "vid.example/kenh-hai"));
    assert.deepEqual(daChon, [2], "bam kenh 2 phai bao DUNG id 2");
    fireEvent.click(mucCua(container, "kenh-mot.wav"));
    assert.deepEqual(daChon, [2, 1]);

    // `selectedId` la PROP: bam xong ma prop khong doi thi KHONG duoc tu doi dau (mot ban
    // giu state cuc bo se truot dong nay — cung lop voi `Header`).
    assert.equal(dauCua(mucCua(container, "vid.example/kenh-hai")), "", "chua doi prop thi dau khong duoc nhay");

    assert.deepEqual(tiengOn, [], "bam muc kenh khong duoc sinh tieng on console");
    unmount();
  });
});
