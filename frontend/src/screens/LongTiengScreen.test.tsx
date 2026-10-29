/**
 * Test `<LongTiengScreen/>` THAT trong jsdom — màn LỒNG TIẾNG (tab thứ tư).
 *
 * ── VÌ SAO MÀN NÀY TỒN TẠI, VÀ VÌ SAO BÀI TEST NÀY GHIM ĐÚNG CHỖ ĐÓ ────────────────
 *
 * Bản đầu đặt khối lồng tiếng vào TRONG `.cmp__bans` của màn Đối chiếu. Đo trên Chrome thật:
 * một job `dub` hỏng từ trước chiếm mất chỗ của cả bản dịch — khối rộng **2004 px**, chữ tràn
 * ra ngoài khung, và ô giọng + nút biến mất (`co_o_giong: false`, `co_nut: false`).
 *
 * ⇒ Tệp này ghim BA luật, mỗi luật là một vế của lỗi đó:
 *   1. `plan === null` KHÔNG được vẽ một dải thời gian rỗng trông như đã đo;
 *   2. job ĐANG CHẠY có nút HUỶ; job ĐÃ HỎNG không được khoá cửa vào (ô giọng + nút vẫn còn);
 *   3. mọi lớp `.lt*` xuất hiện trong DOM phải có LUẬT trong `app.css`, và ngược lại.
 *
 * ⚠️ jsdom KHÔNG có layout và KHÔNG có CSS thật, nên tệp này đo HÀNH VI (cái gì trong DOM, lớp
 * nào, chữ nào, con số nào), KHÔNG đo HÌNH. Bằng chứng hình thức nằm ở tầng Chrome thật.
 *
 * ⚠️ KHÔNG có `@testing-library/user-event`, KHÔNG `jest-dom` trong repo (`package.json`: chỉ
 * `jsdom` + `@testing-library/react`) ⇒ `fireEvent` + `node:assert/strict`.
 *
 * ⚠️ MỌI hook global nằm TRONG `describe()`: dưới `--test-isolation=none`, hook cấp TỆP bị
 * `node:test` kéo lên GỐC cả lượt — đo được, không suy diễn.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { after, before, describe, it } from "node:test";

import { setupDom, teardownDom } from "../../test/dom.ts";
import type { DubPlan, Job, Segment, Source, TranslationDetail } from "../api/types.ts";

const consoleGoc = { error: console.error, warn: console.warn };
const tiengOn: string[] = [];

let render: (ui: unknown) => { container: HTMLElement; unmount: () => void };
let fireEvent: { click: (el: Element) => void; change: (el: Element, init: unknown) => void };
let cleanup: () => void;
let act: (cb: () => void) => void;
let waitFor: (cb: () => void, options?: { timeout?: number; interval?: number }) => Promise<void>;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let LongTiengScreen: (props: unknown) => unknown;

/** `textContent` của phần tử ĐẦU TIÊN khớp `chon`. */
function chu(goc: HTMLElement, chon: string): string {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.textContent ?? "";
}

function co(goc: HTMLElement, chon: string): boolean {
  return goc.querySelector(chon) !== null;
}

/** Nguồn tối thiểu — chỉ các khoá mà màn này ĐỌC. */
function nguon(id: number, origin: string, duration: number | null = 279): Source {
  return {
    id, kind: "file", origin, media_path: `m/${id}`, lang: "zh",
    duration, audio_path: "a.wav", created_at: "2026-01-01T00:00:00Z",
  } as Source;
}

function doan(i: number, start: number, end: number, text: string): Segment {
  return { i, start, end, text, suspect: false };
}

function banDich(id: number, segments: Segment[], status: "done" | "queued" = "done"): TranslationDetail {
  return {
    id, transcript_id: 5, engine: "opus-mt", target_lang: "vi",
    prompt_version: "p1", transcript_version: 1, status, stale: false,
    created_at: "2026-01-01T00:00:00Z",
    segments, cps: { max_cps: 21, rows: [] }, chimera: null,
  } as TranslationDetail;
}

/**
 * Kế hoạch có ĐỦ HAI trạng thái, và một dòng NÉN MẠNH (> 1,5×) — dựng từ số đo THẬT của một
 * lượt chạy trên máy Windows (take 1,06 / 1,02 / 0,52 / 1,86 s trên bốn chỗ 1,08 / 1,44 /
 * 0,92 / 2,36 s) rồi ĐẨY dòng đầu lên 1,86× để chạm nhánh amber.
 *
 * ⚠️ Vì sao phải đẩy: lượt chạy thật của bản dịch #1 cho CẢ BỐN dòng `vua` (tốc độ 1,00×) —
 * đo được. Một fixture toàn `vua` sẽ không bao giờ chạm nhánh amber, tức bài test sẽ XANH mà
 * không đo gì.
 *
 * 🔴 Trạng thái thứ ba `phai-sua` đã BỎ cùng trần nén 1,35 (spec 2026-10-29): tốc độ không
 * còn bị kẹp nên không dòng nào "không cứu được bằng tốc độ". Nay amber nghĩa là NÉN MẠNH.
 */
const PLAN: DubPlan = {
  translation_id: 11,
  tong_giay: 5.8,
  so_dong: 3,
  dem: { vua: 1, nen: 1, nen_manh: 1 },
  trung_vi_toc_do: 1.2,
  dong: [
    { i: 0, start: 0, end: 1.08, text: "Xin chào", take: 2.0, slot: 1.08, avail: 1.08,
      speed: 1.86, need: 1.86, trang_thai: "nen" },
    { i: 1, start: 1.08, end: 2.52, text: "Tạm biệt", take: 2.67, slot: 1.44, avail: 1.44,
      speed: 1.05, need: 1.03, trang_thai: "nen" },
    { i: 2, start: 2.52, end: 5.8, text: "Hẹn gặp lại", take: 1.5, slot: 3.28, avail: 3.28,
      speed: 1.0, need: 0.46, trang_thai: "vua" },
  ],
};

const DOAN = [
  doan(0, 0, 1.08, "Xin chào"),
  doan(1, 1.08, 2.52, "Tạm biệt"),
  doan(2, 2.52, 5.8, "Hẹn gặp lại"),
];

function jobDub(id: number, state: Job["state"], opts: {
  progress?: number; error?: string | null; translationId?: number;
} = {}): Job {
  return {
    id, workspace: 2, type: "dub", engine: "vieneu-v3-turbo",
    phase: "dub:vieneu-v3-turbo", state,
    progress: opts.progress ?? 0,
    log_tail: "",
    error: opts.error ?? null,
    payload: { translation_id: opts.translationId ?? 11, voice: null },
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
  } as Job;
}

/** Props tối thiểu: MỘT nguồn, MỘT bản dịch, đủ callback. */
function props(thayDoi: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    sourceId: 1,
    translations: [banDich(11, DOAN)],
    macDinhId: 11,
    onChonBanDich: () => {},
    dubJob: null,
    onLongTieng: () => {},
    onHuy: () => {},
    loiLongTieng: null,
    ...thayDoi,
  };
}

/** Chờ tới khi kế hoạch được vẽ xong — theo DOM, không theo đồng hồ. */
async function choKeHoach(container: HTMLElement): Promise<void> {
  await waitFor(
    () => {
      assert.ok(
        co(container, '[data-testid="lt-dai"]'),
        `dải thời gian chưa vẽ; DOM: ${JSON.stringify((container.textContent ?? "").slice(0, 200))}`,
      );
    },
    { timeout: 4000, interval: 20 },
  );
}

/**
 * ⚠️ WEBAUDIO GIẢ, và vì sao phải giả: màn này phát take bằng `fetch` → `decodeAudioData` →
 * `AudioBufferSourceNode.start()`, KHÔNG bằng thẻ `<audio>`. Lý do đo được: trên app thật, phần
 * tử media của Chrome trong phiên kiểm treo ở `readyState: 0` / `networkState: 2` ngay cả với
 * WAV dựng trong bộ nhớ (blob URL, không mạng), trong khi `decodeAudioData` trên ĐÚNG tệp đó
 * trả `ok · 48000 Hz · 2.56 s`. Nên đường phát đi qua WebAudio.
 *
 * JSDOM không có WebAudio, nên bộ giả này ghi lại MỌI lượt nạp và phát — đó là căn cứ để bài
 * test ghim đúng route, đúng chỉ số dòng, và ghim rằng bấm lần hai thì DỪNG.
 */
interface NhatKyAm {
  /** URL đã `fetch` để phát, theo thứ tự. */
  daNap: string[];
  /** Số lần một nguồn được `start()`. */
  soLanPhat: number;
  /** Số lần `stop()` được gọi trên nguồn đang kêu. */
  soLanDung: number;
}

/** Lắp WebAudio giả vào `window`; trả về nhật ký để bài test đọc. */
function lapWebAudioGia(): NhatKyAm {
  const nk: NhatKyAm = { daNap: [], soLanPhat: 0, soLanDung: 0 };
  class NguonGia {
    buffer: unknown = null;
    onended: (() => void) | null = null;
    connect(): void {}
    start(): void { nk.soLanPhat += 1; }
    stop(): void {
      nk.soLanDung += 1;
      // Trình duyệt thật bắn `ended` sau `stop()`; gọi đồng bộ ở đây để trạng thái UI kịp hạ.
      const f = this.onended;
      this.onended = null;
      if (f !== null) f();
    }
  }
  class CtxGia {
    state = "running";
    sampleRate = 48_000;
    destination = {};
    async resume(): Promise<void> {}
    async close(): Promise<void> {}
    createBufferSource(): NguonGia { return new NguonGia(); }
    async decodeAudioData(byte: ArrayBuffer): Promise<unknown> {
      // Đòi byte THẬT: một lần nạp rỗng nghĩa là `fetch` không trả gì, và bài test phải đỏ.
      if (byte.byteLength === 0) throw new Error("decodeAudioData nhận 0 byte");
      return { duration: 1, sampleRate: 48_000, numberOfChannels: 1 };
    }
  }
  // ⚠️ LẮP VÀO CẢ `window` LẪN `globalThis`, và đây là một lỗi đo được: `setupDom` dựng một
  // `window` RIÊNG của jsdom rồi gán vào `globalThis.window`, nên `window` KHÔNG phải
  // `globalThis`. Code màn đọc `window.AudioContext` (đúng với trình duyệt thật), vì thế lắp
  // mỗi `globalThis` thì nó không thấy gì và ba bài đỏ với "phải nạp byte qua WebAudio" —
  // trong khi `decodeAudioData` chưa từng được gọi.
  const w = globalThis as unknown as {
    AudioContext?: unknown; window?: { AudioContext?: unknown };
  };
  w.AudioContext = CtxGia;
  if (w.window !== undefined) w.window.AudioContext = CtxGia;
  return nk;
}

describe("LongTiengScreen", () => {
  let fetchGoc: typeof globalThis.fetch;
  /** Nhật ký WebAudio giả của bài ĐANG chạy — `lapWebAudioGia()` trả về nó trong `before`. */
  let nkAm: NhatKyAm;

  before(async () => {
    console.error = (...a: unknown[]) => { tiengOn.push(a.map(String).join(" ")); };
    console.warn = (...a: unknown[]) => { tiengOn.push(a.map(String).join(" ")); };

    // ⚠️ `setupDom` PHẢI đứng TRƯỚC mọi `import` của React / Testing Library: React đọc
    // `window`/`document` NGAY LÚC NẠP module, nên nạp trước rồi mới dựng DOM thì nó giữ
    // tham chiếu tới `document` của Node (không tồn tại) — đo được: `ReferenceError: document
    // is not defined` cho CẢ BẢY bài. Origin là một URL giả: màn này KHÔNG tự gọi mạng ngoài
    // `/plan`, mà `fetch` bị chặn ngay dưới đây.
    setupDom("http://127.0.0.1:9");

    // ⚠️ LẮP WEBAUDIO GIẢ **SAU** `setupDom`, và đây là một lỗi đo được: bản trước gọi nó ở
    // ĐẦU `before`, lúc `window` CHƯA TỒN TẠI (nó do `setupDom` dựng), nên dòng dò in ra
    // `{"window":"khong co window"}` và bộ giả chỉ nằm trên `globalThis`. Code màn đọc
    // `window.AudioContext` — đúng với trình duyệt thật — nên nó không thấy gì, `decodeAudioData`
    // chưa từng chạy, và ba bài đỏ với "phải nạp byte qua WebAudio" trong khi nguyên nhân là
    // THỨ TỰ LẮP.
    nkAm = lapWebAudioGia();

    const rtl = await import("@testing-library/react");
    render = rtl.render as unknown as typeof render;
    fireEvent = rtl.fireEvent as unknown as typeof fireEvent;
    cleanup = rtl.cleanup;
    act = rtl.act as unknown as typeof act;
    waitFor = rtl.waitFor as unknown as typeof waitFor;

    const React = await import("react");
    taoPhanTu = ((type: unknown, p?: unknown) =>
      React.createElement(type as never, p as never)) as unknown as typeof taoPhanTu;

    ({ LongTiengScreen } = (await import("./LongTiengScreen.tsx")) as unknown as {
      LongTiengScreen: typeof LongTiengScreen;
    });

    // `getDubPlan` đi qua `api.get` ⇒ `fetch`. Chặn ở ĐÚNG tầng đó, và chỉ trả lời route
    // `/plan`: mọi URL khác là lỗi của bài test, không phải im lặng trả `null`.
    fetchGoc = globalThis.fetch;
    globalThis.fetch = (async (dau: unknown) => {
      const url = String(dau);
      // SO DUNG CHUOI, khong dung `includes("/plan")`: ban dau cua `getDubPlan` viet
      // `/api/dubs/...` trong khi `api.get` da ghep `BASE = "/api"` ⇒ URL that la
      // `/api/api/dubs/11/plan` ⇒ 404 "Not Found". DO DUOC tren app that.
      if (url === "/api/dubs/11/plan") {
        return new Response(JSON.stringify(PLAN), {
          status: 200, headers: { "content-type": "application/json" },
        });
      }
      // NGHE THỬ đi qua `fetch` (WebAudio cần byte), nên route `/take` phải trả nội dung THẬT.
      // Ghi URL lại để bài test ghim đúng chỉ số 0-BASED mà route nhận.
      if (url.startsWith("/api/dubs/") && url.includes("/take?i=")) {
        nkAm.daNap.push(url);
        return new Response(new Uint8Array([82, 73, 70, 70, 0, 0, 0, 0]), {
          status: 200, headers: { "content-type": "audio/wav" },
        });
      }
      throw new Error(`bai test khong cho mot request nao khac: ${url}`);
    }) as typeof globalThis.fetch;
  });

  after(() => {
    // `cleanup()` phải chạy khi DOM CÒN SỐNG (nó gỡ cây React khỏi `document`), nên nó đứng
    // TRƯỚC `teardownDom()`.
    cleanup();
    globalThis.fetch = fetchGoc;
    console.error = consoleGoc.error;
    console.warn = consoleGoc.warn;
    teardownDom();
  });

  // -------------------------------------------------------------------------
  // HÌNH DẠNG CƠ BẢN: HAI tầng — dải chọn bản dịch, rồi bảng dòng
  // -------------------------------------------------------------------------

  it("HAI TẦNG: dải chọn bản dịch + bảng dòng, và KHÔNG có cột kênh thứ hai", async () => {
    const { container, unmount } = render(taoPhanTu(LongTiengScreen, props()));

    assert.ok(co(container, '[data-testid="lt-man"]'), "màn phải có gốc `lt-man`");
    // ⚠️ ĐO ĐƯỢC trên ảnh chụp app thật: bản đầu vẽ lại danh sách kênh NGAY TRONG màn này trong
    // khi shell đã có cột kênh bên trái — mỗi tệp hiện hai lần, và hai bản sao có hai trạng thái
    // chọn riêng. Kênh do shell chọn và chỉ đi xuống qua `sourceId`, nên bài này ghim sự VẮNG
    // MẶT đó, không chỉ sự có mặt của hai tầng còn lại.
    assert.equal(co(container, ".lt__kenh"), false,
      "KHÔNG được có cột kênh trong màn: shell đã có, và hai bản sao là hai trạng thái chọn");
    assert.equal(co(container, ".lt__nguon"), false,
      "KHÔNG được có nút kênh trong màn: kênh do shell chọn");

    assert.ok(co(container, '[data-testid="lt-bans"]'), "phải có dải chọn bản dịch");
    assert.equal(chu(container, '[data-testid="lt-ban-11"]').includes("bản dịch #11"), true,
      "chip bản dịch phải nói số hiệu");

    for (const i of [0, 1, 2]) {
      assert.ok(co(container, `[data-testid="lt-dong-${i}"]`), `thiếu dòng ${i} của bảng`);
    }
    assert.equal(chu(container, '[data-testid="lt-dong-0"]').includes("Xin chào"), true,
      "dòng phải hiện câu CỦA BẢN DỊCH");

    await choKeHoach(container);

    assert.deepEqual(tiengOn, [], "màn không được sinh tiếng ồn console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // TẦNG 2 — KẾ HOẠCH: ba trạng thái, và `null` KHÔNG phải một dải rỗng
  // -------------------------------------------------------------------------

  it("KẾ HOẠCH: hai trạng thái + nén mạnh nói bằng CHỮ, dải thời gian vẽ đủ ba cửa sổ", async () => {
    const { container, unmount } = render(taoPhanTu(LongTiengScreen, props()));
    await choKeHoach(container);

    assert.equal(container.querySelectorAll(".lt__cap").length, 3,
      "dải thời gian phải có một cửa sổ cho MỖI dòng của kế hoạch");
    assert.equal(container.querySelectorAll(".lt__take").length, 3, "mỗi cửa sổ một thanh take");

    assert.equal(container.querySelectorAll(".lt__take--nen-manh").length, 1,
      "phải có ĐÚNG MỘT thanh amber (dòng nén mạnh > 1,5×)");
    // HAI thanh nén: dòng 0 (nén mạnh 1,86×) và dòng 1 (nén nhẹ 1,05×). Trạng thái thứ ba
    // `phai-sua` đã bỏ cùng trần 1,35, nên dòng 0 nay là `nen` + class `nen-manh`.
    assert.equal(container.querySelectorAll(".lt__take--nen").length, 2,
      "phải có ĐÚNG HAI thanh nén (một nén mạnh, một nén nhẹ)");
    assert.equal(container.querySelectorAll(".lt__take--vua").length, 1, "phải có ĐÚNG MỘT thanh vừa");

    const dauDai = chu(container, ".lt__dau-dai");
    assert.match(dauDai, /trung vị 1,20×/,
      `đầu dải phải nói trung vị của kế hoạch (dấu phẩy thập phân); đo được ${JSON.stringify(dauDai)}`);
    assert.match(dauDai, /vừa chỗ 1 · nén 1 · nén mạnh 1/,
      `ba con số đếm phải là của KẾ HOẠCH; đo được ${JSON.stringify(dauDai)}`);

    assert.equal(chu(container, '[data-testid="lt-dong-0"]').includes("nén mạnh"), true,
      "dòng nén trên 1,5× phải nói 'nén mạnh'");
    assert.equal(chu(container, '[data-testid="lt-dong-1"]').includes("nén"), true,
      "dòng bị nén phải nói 'nén'");
    assert.equal(chu(container, '[data-testid="lt-dong-2"]').includes("vừa chỗ"), true,
      "dòng vừa chỗ phải nói 'vừa chỗ'");

    assert.deepEqual(tiengOn, [], "kế hoạch không được sinh tiếng ồn console");
    unmount();
  });

  it("CHƯA ĐO: `plan = null` KHÔNG được vẽ một dải rỗng trông như đã đo", async () => {
    const truoc = globalThis.fetch;
    globalThis.fetch = (async (dau: unknown) => {
      const url = String(dau);
      // SO DUNG CHUOI, khong dung `includes("/plan")`: ban dau cua `getDubPlan` viet
      // `/api/dubs/...` trong khi `api.get` da ghep `BASE = "/api"` ⇒ URL that la
      // `/api/api/dubs/11/plan` ⇒ 404 "Not Found". DO DUOC tren app that.
      if (url === "/api/dubs/11/plan") {
        return new Response("null", { status: 200, headers: { "content-type": "application/json" } });
      }
      throw new Error(`khong cho request khac: ${url}`);
    }) as typeof globalThis.fetch;
    try {
      const { container, unmount } = render(taoPhanTu(LongTiengScreen, props()));

      await waitFor(
        () => { assert.ok(co(container, '[data-testid="lt-chua-do"]'), "phải nói ra 'chưa đo'"); },
        { timeout: 4000, interval: 20 },
      );

      assert.equal(co(container, '[data-testid="lt-dai"]'), false,
        "KHÔNG được vẽ dải thời gian khi chưa có số đo: một dải rỗng trông như mọi thứ đều vừa");
      assert.match(chu(container, '[data-testid="lt-chua-do"]'), /chưa lồng lần nào/,
        "câu phải nói ĐÚNG việc phải làm");
      // ⚠️ Và câu đó chỉ đúng khi ĐÃ có kênh + bản dịch. Đo được trên app thật: bản đầu nói
      // "chọn một bản dịch để lồng tiếng" cả khi CHƯA CHỌN KÊNH — sai việc phải làm, vì việc
      // đầu tiên là chọn KÊNH ở cột trái. Ba nguyên nhân ⇒ ba câu.
      const { container: chuaKenh, unmount: go2 } = render(taoPhanTu(LongTiengScreen, {
        sourceId: null, translations: [],
        macDinhId: null, dubJob: null,
        onLongTieng: () => {}, onHuy: () => {}, loiLongTieng: null,
      }));
      await waitFor(
        () => { assert.ok(co(chuaKenh, '[data-testid="lt-chua-do"]'), "phải nói ra 'chưa đo'"); },
        { timeout: 4000, interval: 20 },
      );
      assert.match(chu(chuaKenh, '[data-testid="lt-chua-do"]'), /chọn một kênh/,
        "CHƯA chọn kênh ⇒ câu phải nói chọn KÊNH, không phải chọn bản dịch");
      go2();

      assert.ok(co(container, '[data-testid="lt-dong-0"]'),
        "bảng dòng phải còn khi chưa có kế hoạch");
      assert.equal(chu(container, '[data-testid="lt-dong-0"]').includes("chưa đo"), true,
        "ô take của dòng chưa đo phải nói 'chưa đo', KHÔNG phải 0,00s");

      unmount();
    } finally {
      globalThis.fetch = truoc;
    }
  });

  // -------------------------------------------------------------------------
  // TẦNG 3 — BỐN TRẠNG THÁI CỦA JOB, và đường HUỶ
  // -------------------------------------------------------------------------

  it("ĐANG ĐỌC: `translations` chưa về KHÔNG được nói thành `không có bản dịch`", async () => {
    // ⚠️ ĐO ĐƯỢC trên ảnh chụp app thật: trang vừa tải lại thì `translations` CHƯA VỀ, và màn
    // nói "kênh này chưa có bản dịch" — trong khi chính kênh đó có bản dịch #10 với 434 dòng.
    // "Chưa đọc xong" và "đọc xong, không có" là hai sự thật khác nhau. Đây là `null ≠ 0` áp
    // cho quyền sở hữu: chưa biết KHÔNG được nói thành không có.
    const { container, unmount } = render(taoPhanTu(LongTiengScreen, {
      sourceId: 1, translations: [], dangDocBanDich: true, macDinhId: null,
      onChonBanDich: () => {}, dubJob: null, onLongTieng: () => {}, onHuy: () => {},
      loiLongTieng: null,
    }));
    await waitFor(
      () => { assert.ok(co(container, '[data-testid="lt-chua-do"]'), "phải nói ra một trạng thái"); },
      { timeout: 4000, interval: 20 },
    );
    const cau = chu(container, '[data-testid="lt-chua-do"]');
    assert.match(cau, /đang đọc bản dịch/,
      `đang tải ⇒ câu phải nói ĐANG ĐỌC; đo được ${JSON.stringify(cau)}`);
    assert.doesNotMatch(cau, /chưa có bản dịch/,
      `đang tải KHÔNG được khẳng định "chưa có"; đo được ${JSON.stringify(cau)}`);
    unmount();
  });

  it("JOB: bốn trạng thái nói bằng chữ, đang chạy có nút HUỶ, và lỗi nằm gọn trong `<details>`", async () => {
    // (1) CHƯA LỒNG: ô giọng + nút có mặt.
    const chua = render(taoPhanTu(LongTiengScreen, props())).container;
    assert.ok(co(chua, '[data-testid="lt-nut"]'), "chưa lồng ⇒ phải có nút lồng tiếng");
    assert.equal(co(chua, "input.lt__giong"), true, "chưa lồng ⇒ phải có ô giọng");
    assert.equal(co(chua, '[data-testid="lt-huy"]'), false, "chưa chạy ⇒ KHÔNG có nút huỷ");

    // (2) ĐANG CHẠY: có % và có nút HUỶ; KHÔNG còn nút lồng (không xếp hai job).
    const chay = render(taoPhanTu(LongTiengScreen, props({
      dubJob: jobDub(41, "running", { progress: 0.42 }),
    }))).container;
    assert.equal(chu(chay, '[data-testid="lt-dang-chay"]'), "đang lồng tiếng… 42%",
      "phải nói bằng CHỮ + phần trăm của job");
    assert.ok(co(chay, '[data-testid="lt-huy"]'), "đang chạy ⇒ PHẢI có nút huỷ");
    assert.equal(co(chay, '[data-testid="lt-nut"]'), false,
      "đang chạy ⇒ không được có nút xếp thêm một job nữa");

    // (3) XONG: năm đường tải, dựng từ id bản dịch ĐANG CHỌN.
    const xong = render(taoPhanTu(LongTiengScreen, props({
      dubJob: jobDub(42, "done", { progress: 1, translationId: 11 }),
    }))).container;
    const tai = [...xong.querySelectorAll('[data-testid="lt-tai"] a')];
    assert.deepEqual(
      tai.map((a) => a.getAttribute("href")),
      ["wav", "mp3", "aac", "m4a", "flac"].map((d) => `/api/dubs/11/download?format=${d}`),
      "mỗi định dạng một đường, trỏ đúng route và đúng id bản dịch đang chọn",
    );
    assert.equal(tai.every((a) => a.hasAttribute("download")), true,
      "mỗi đường tải phải là `<a download>` (tải file), không phải một lời gọi JS");

    // (4) HỎNG: `<summary>` nói trạng thái bằng chữ; mở ra thì NGUYÊN VĂN. NÚT VẪN CÒN — đó là
    //     vế đã đo được trên app thật (`co_nut: false` ở bản đầu).
    const cauLoi = "409: chưa có worker — chạy `phude worker`";
    const hong = render(taoPhanTu(LongTiengScreen, props({
      dubJob: jobDub(43, "failed", { error: cauLoi }),
    }))).container;
    assert.ok(co(hong, '[data-testid="lt-loi-hop"]'),
      "job lỗi phải có hộp lỗi (details), không phải một dòng chữ tràn ngang");
    assert.equal(chu(hong, '[data-testid="lt-loi"]'), "lỗi lồng tiếng — mở để xem",
      "`summary` nói trạng thái bằng CHỮ, không phải bằng một vết lỗi dài");
    assert.equal(chu(hong, '[data-testid="lt-loi-nguyen-van"]'), cauLoi,
      "mở ra thì phải là NGUYÊN VĂN `job.error` — không cắt, không dịch lại");
    assert.ok(co(hong, '[data-testid="lt-nut"]'),
      "job lỗi KHÔNG được khoá nút: người dùng phải thử lại được sau khi sửa môi trường");
    assert.equal(co(hong, "input.lt__giong"), true, "job lỗi KHÔNG được làm mất ô giọng");

    // (5) LỖI XẾP JOB (HTTP, khác lỗi job): nguyên văn `ApiError.message`, KHÔNG xoá nút.
    const loiTao = render(taoPhanTu(LongTiengScreen, props({
      loiLongTieng: "404: không có bản dịch #99",
    }))).container;
    assert.equal(chu(loiTao, '[data-testid="lt-loi-tao"]'), "404: không có bản dịch #99",
      "lỗi xếp job phải hiện NGUYÊN VĂN");
    assert.ok(co(loiTao, '[data-testid="lt-nut"]'),
      "lỗi xếp job không được xoá nút: người dùng phải bấm lại được");

    assert.deepEqual(tiengOn, [], "bốn trạng thái không được sinh tiếng ồn console");
  });

  it("HUỶ: bấm nút huỷ gọi ĐÚNG MỘT lần `onHuy`, và nút biến mất khi job không còn sống", async () => {
    let soLan = 0;
    const { container, unmount } = render(taoPhanTu(LongTiengScreen, props({
      dubJob: jobDub(41, "queued"),
      onHuy: () => { soLan += 1; },
    })));

    const nut = container.querySelector('[data-testid="lt-huy"]');
    assert.ok(nut !== null, "job `queued` cũng phải huỷ được — nó đang chiếm chỗ trong hàng đợi");
    fireEvent.click(nut);
    assert.equal(soLan, 1, `bấm một lần ⇒ đúng MỘT lời gọi; đo được ${soLan}`);

    const xong = render(taoPhanTu(LongTiengScreen, props({
      dubJob: jobDub(42, "done", { progress: 1 }),
    }))).container;
    assert.equal(co(xong, '[data-testid="lt-huy"]'), false, "job đã xong ⇒ KHÔNG có nút huỷ");

    unmount();
  });

  it("ĐỔI KÊNH: lựa chọn bản dịch CŨ bị bỏ khi CÙNG một màn đổi kênh", async () => {
    // ⚠️ Ghim lỗi ĐO ĐƯỢC trên app thật: `chonId` sống dai qua lần đổi kênh, nên màn hiện
    // `translations[0]` của kênh MỚI trong khi `App` vẫn giữ id của kênh CŨ — hai vùng nói hai
    // bản khác nhau (lỗi `I2`).
    //
    // ⚠️⚠️ VÀ ĐÂY LÀ CHỖ DỄ TỰ LỪA NHẤT: bản đầu của bài này render HAI lần riêng biệt, nên nó
    // XANH kể cả khi bỏ `useEffect` reset — đo được bằng mutation (mutant SỐNG, `pass 8 / fail 0`).
    // Hai instance mới thì `chonId` vốn đã là `null`; chỉ CÙNG một instance đổi `sourceId` mới
    // chạm đúng cơ chế. Nên bài này dùng `rerender` với props mới.
    const banA = banDich(11, DOAN);
    const banB = banDich(77, [doan(0, 0, 1.0, "câu của kênh B")]);
    const gocProps = {
      sourceId: 1,
      dubJob: null, onLongTieng: () => {}, onHuy: () => {},
      loiLongTieng: null,
    };

    const { container, rerender, unmount } = render(taoPhanTu(LongTiengScreen, {
      ...gocProps, translations: [banA], macDinhId: 11,
    }));
    await choKeHoach(container);

    // Chọn TAY bản dịch #11 của kênh A ⇒ `chonId = 11`.
    fireEvent.click(container.querySelector('[data-testid="lt-ban-11"]') as Element);
    await waitFor(
      () => {
        const el = container.querySelector('[data-testid="lt-ban-11"]');
        assert.equal(el?.getAttribute("aria-checked"), "true", "chưa chọn được bản dịch #11");
      },
      { timeout: 3000, interval: 20 },
    );

    // CÙNG instance, props mới: kênh B, chỉ có bản dịch #77, `macDinhId = 77`.
    rerender(taoPhanTu(LongTiengScreen, {
      ...gocProps, sourceId: 2, translations: [banB], macDinhId: 77,
    }));
    await waitFor(
      () => {
        const el = container.querySelector('[data-testid="lt-ban-77"]');
        assert.equal(el?.getAttribute("aria-checked"), "true",
          "kênh B phải chọn bản dịch #77 của CHÍNH nó — không được giữ lựa chọn #11 của kênh A");
      },
      { timeout: 4000, interval: 20 },
    );
    assert.equal(container.querySelectorAll('[data-testid="lt-ban-11"]').length, 0,
      "kênh B không được hiện bản dịch #11 của kênh A");

    unmount();
  });

  it("SỐ DÒNG: người đọc đếm từ 1, còn `take?i=` vẫn là chỉ số 0-based của `Segment`", async () => {
    // ⚠️ ĐO ĐƯỢC trên ảnh chụp app thật: cột `#` hiện `00, 01, 02…` vì nó in thẳng `s.i`, vốn
    // 0-based. Người dùng đếm dòng từ 1, và cột `GIỜ` ngay cạnh cũng đọc theo cách đó. Sửa chỉ ở
    // chỗ HIỂN THỊ, không ở dữ liệu: `data-testid` và `take?i=` phải giữ chỉ số gốc, nếu không
    // route cắt nhầm đoạn.
    const { container, unmount } = render(taoPhanTu(LongTiengScreen, props()));
    await choKeHoach(container);

    const so = [...container.querySelectorAll(".lt__so")].map((e) => e.textContent);
    assert.deepEqual(so, ["01", "02", "03"],
      `cột # phải đếm từ 1; đo được ${JSON.stringify(so)}`);

    // Nhưng khoá của dòng VẪN là chỉ số gốc — mở dòng 2 (chỉ số 1) rồi đọc href.
    fireEvent.click(container.querySelector('[data-testid="lt-dong-1"]') as Element);
    await waitFor(
      () => {
        assert.ok(container.querySelector('[data-testid="lt-nghe-1"]') !== null,
          "chưa mở được dòng chỉ số 1");
      },
      { timeout: 3000, interval: 20 },
    );
    // Nút nghe là `<button>` phát TẠI CHỖ qua WebAudio, nên không có `href` lẫn thẻ `<audio>`:
    // căn cứ để ghim là URL mà WebAudio đã `fetch`, và nó CHỈ xuất hiện sau khi bấm. Đó cũng là
    // điều cần ghim: đường take dùng chỉ số 0-BASED (1), không phải số hiển thị (2).
    fireEvent.click(container.querySelector('[data-testid="lt-nghe-1"]') as Element);
    await waitFor(
      () => {
        assert.ok(nkAm.daNap.length > 0, "bấm 'nghe take' phải nạp byte qua WebAudio");
      },
      { timeout: 3000, interval: 20 },
    );
    assert.deepEqual(nkAm.daNap, ["/api/dubs/11/take?i=1"],
      "route take phải dùng chỉ số 0-BASED (1), không phải số hiển thị (2)");
    assert.match(chu(container, ".lt__sua-ghi, .lt__sua"), /Dòng 02/,
      "nhãn trong ô sửa cũng phải đếm từ 1");

    unmount();
  });

  it("NGHE THỬ: bấm là PHÁT tại chỗ, bấm lại là DỪNG, đổi dòng thì dòng cũ dừng", async () => {
    // ⚠️ BỐN ĐIỀU BÀI NÀY GHIM, mỗi điều ứng với một lỗi ĐO ĐƯỢC:
    //   1. Nút là `<button>` KHÔNG có `href` — bản đầu là `<a href=… download>`, nên bấm vào là
    //      trình duyệt TẢI tệp wav và không có âm thanh nào phát ra trên trang.
    //   2. Bấm phát ⇒ WebAudio NẠP byte của ĐÚNG route `take?i=<chỉ số 0-based>` và `start()`
    //      một nguồn. Không dùng `<audio>`: đo trên app thật, phần tử media của Chrome treo ở
    //      `readyState: 0` ngay cả với WAV dựng trong bộ nhớ, trong khi `decodeAudioData` trên
    //      đúng tệp đó trả `ok`. Nên đường phát là WebAudio, và căn cứ để ghim là NHẬT KÝ của nó.
    //   3. Bấm LẦN HAI ⇒ `stop()` nguồn đang kêu và chữ về `nghe take` — KHÔNG nạp lại tệp.
    //   4. Bấm dòng KHÁC ⇒ nguồn cũ bị `stop()` TRƯỚC, chỉ một nguồn kêu tại một thời điểm.
    const truoc = tiengOn.length;
    const truocNap = nkAm.daNap.length;
    const truocPhat = nkAm.soLanPhat;
    const truocDung = nkAm.soLanDung;
    const { container, unmount } = render(taoPhanTu(LongTiengScreen, props()));
    await choKeHoach(container);

    fireEvent.click(container.querySelector('[data-testid="lt-dong-1"]') as Element);
    await waitFor(
      () => {
        assert.ok(
          container.querySelector('[data-testid="lt-nghe-1"]') !== null,
          "mở dòng phải hiện nút NGHE THỬ",
        );
      },
      { timeout: 3000, interval: 20 },
    );

    // (1) Nút phải là `<button>`, không phải `<a download>`.
    const nut = container.querySelector('[data-testid="lt-nghe-1"]');
    assert.equal(nut?.tagName, "BUTTON",
      `nút nghe phải là <button> (phát tại chỗ), không phải ${nut?.tagName} (tải tệp)`);
    assert.equal(nut?.getAttribute("href"), null, "nút nghe KHÔNG được có href — href là để tải");

    // (2) PHÁT: WebAudio nạp đúng route và `start()` đúng một nguồn.
    fireEvent.click(nut as Element);
    await waitFor(
      () => {
        assert.equal(nkAm.soLanPhat - truocPhat, 1, "bấm 'nghe take' phải PHÁT một nguồn");
      },
      { timeout: 3000, interval: 20 },
    );
    assert.deepEqual(nkAm.daNap.slice(truocNap), ["/api/dubs/11/take?i=1"],
      "đường phát phải trỏ đúng route take, đúng id và đúng chỉ số 0-based của dòng");
    assert.equal(
      container.querySelector('[data-testid="lt-nghe-1"]')?.textContent?.trim(), "dừng",
      "khi đang phát, nút phải đổi chữ thành 'dừng' — chữ là thứ duy nhất nói trạng thái",
    );

    // (3) DỪNG: bấm lại ⇒ `stop()` đúng nguồn, chữ về `nghe take`, KHÔNG nạp lại tệp.
    fireEvent.click(container.querySelector('[data-testid="lt-nghe-1"]') as Element);
    await waitFor(
      () => {
        assert.equal(nkAm.soLanDung - truocDung, 1, "bấm lần hai phải DỪNG nguồn đang kêu");
      },
      { timeout: 3000, interval: 20 },
    );
    assert.equal(
      container.querySelector('[data-testid="lt-nghe-1"]')?.textContent?.trim(), "nghe take",
      "dừng xong nút phải về chữ 'nghe take'",
    );
    assert.equal(nkAm.daNap.length - truocNap, 1,
      "bấm DỪNG không được nạp lại tệp — dừng là dừng, không phải phát lại");

    // (4) ĐỔI DÒNG: dòng cũ dừng TRƯỚC, dòng mới phát, chỉ một nguồn kêu tại một thời điểm.
    const truocDoi = { phat: nkAm.soLanPhat, dung: nkAm.soLanDung, nap: nkAm.daNap.length };
    fireEvent.click(container.querySelector('[data-testid="lt-nghe-1"]') as Element);
    await waitFor(
      () => {
        assert.equal(nkAm.soLanPhat - truocDoi.phat, 1, "dòng 1 phải phát lại được");
      },
      { timeout: 3000, interval: 20 },
    );
    fireEvent.click(container.querySelector('[data-testid="lt-dong-2"]') as Element);
    await waitFor(
      () => {
        assert.ok(container.querySelector('[data-testid="lt-nghe-2"]') !== null,
          "chưa mở được dòng chỉ số 2");
      },
      { timeout: 3000, interval: 20 },
    );
    fireEvent.click(container.querySelector('[data-testid="lt-nghe-2"]') as Element);
    await waitFor(
      () => {
        assert.equal(nkAm.soLanPhat - truocDoi.phat, 2, "dòng 2 phải phát được");
      },
      { timeout: 3000, interval: 20 },
    );
    assert.equal(nkAm.daNap[nkAm.daNap.length - 1], "/api/dubs/11/take?i=2",
      "phát dòng khác phải nạp take của dòng đó (chỉ số 0-based)");
    assert.equal(nkAm.soLanDung - truocDoi.dung, 1,
      "phát dòng khác phải DỪNG dòng cũ trước — hai nguồn cùng kêu là hai dòng chồng tiếng");

    assert.deepEqual(tiengOn.slice(truoc), [],
      `nghe thử không được sinh tiếng ồn console; đo được ${JSON.stringify(tiengOn.slice(truoc))}`);
    unmount();
  });

  // -------------------------------------------------------------------------
  // TẦNG HÌNH THỨC — ĐỌC `app.css`: mọi lớp `.lt*` phải có LUẬT, và ngược lại
  // -------------------------------------------------------------------------

  it("HÌNH THỨC: mọi lớp `.lt*` trong DOM đều có LUẬT trong `app.css`, và ngược lại", async () => {
    const mocTiengOn = tiengOn.length;
    // Vì sao bài này đọc TỆP: một test chỉ khẳng định `className` vẫn XANH khi luật CSS bị xoá
    // (ERRATA #15 mục 3, đo được HAI CHIỀU ở Task 6). Nên nó so HAI TẬP.
    // ⚠️ PHẢI gom lớp trên NHIỀU LẦN RENDER, không phải một: mỗi trạng thái của job vẽ một tập
    // lớp khác nhau (`lt__tin` chỉ khi đang chạy, `lt__tai` chỉ khi xong, `lt__chua-do` chỉ khi
    // chưa đo, `lt__nut--huy` chỉ khi huỷ được). Một lần render duy nhất khiến phép so hai tập
    // báo "luật mồ côi" cho những lớp CÓ DÙNG thật — đo được: tám lớp bị báo oan ở lượt đầu.
    const trongDom = new Set<string>();
    const gomLop = (goc: HTMLElement): void => {
      for (const el of goc.querySelectorAll("*")) {
        for (const lop of el.classList) {
          // ⚠️ `A-Z` phải có: lượt đo đầu của phép ghim này cho một mutant `.lt__loiX` SỐNG vì
          // regex chỉ có `[a-z0-9_-]` và cắt cụt tên lớp — mutant sống, bài test xanh giả.
          if (/^lt[A-Za-z0-9_-]*$/.test(lop)) trongDom.add(lop);
        }
      }
    };

    // (1) chưa lồng + kế hoạch có + ô sửa MỞ (lớp của `.lt__sua`, `.lt__nghe`).
    const mot = render(taoPhanTu(LongTiengScreen, props()));
    await choKeHoach(mot.container);
    fireEvent.click(mot.container.querySelector('[data-testid="lt-dong-1"]') as Element);
    await waitFor(
      () => {
        assert.ok(mot.container.querySelector('[data-testid="lt-nghe-1"]') !== null,
          "chưa mở được ô sửa — bài hình thức sẽ bỏ sót lớp của ô đó");
      },
      { timeout: 3000, interval: 20 },
    );
    // (1b) Bấm "nghe take" ⇒ WebAudio PHÁT. Không còn thẻ `<audio>` (lý do ở bài NGHE THỬ):
    // màn phát qua `decodeAudioData` + `AudioBufferSourceNode`, nên căn cứ là nhật ký WebAudio.
    const truocPhatHT = nkAm.soLanPhat;
    fireEvent.click(mot.container.querySelector('[data-testid="lt-nghe-1"]') as Element);
    await waitFor(
      () => {
        assert.equal(nkAm.soLanPhat - truocPhatHT, 1,
          "chưa tới trạng thái ĐANG PHÁT (WebAudio phải `start()` một nguồn sau cú bấm)");
      },
      { timeout: 3000, interval: 20 },
    );
    const mocSauKhiNghe = tiengOn.length;
    gomLop(mot.container);
    mot.unmount();

    // (2) đang chạy: `lt__tin`, `lt__nut--huy`.
    const chay = render(taoPhanTu(LongTiengScreen, props({
      dubJob: jobDub(41, "running", { progress: 0.42 }),
    })));
    await choKeHoach(chay.container);
    gomLop(chay.container);
    chay.unmount();

    // (3) xong: `lt__tai`, `lt__nut-tai`.
    const xong = render(taoPhanTu(LongTiengScreen, props({
      dubJob: jobDub(42, "done", { progress: 1 }),
    })));
    await choKeHoach(xong.container);
    gomLop(xong.container);
    xong.unmount();

    // (4) hỏng: `lt__loi-hop`, `lt__loi`, `lt__loi-nguyen-van`, `lt__loi-tao`.
    const hong = render(taoPhanTu(LongTiengScreen, props({
      dubJob: jobDub(43, "failed", { error: "x" }),
      loiLongTieng: "409: chưa có worker",
    })));
    await choKeHoach(hong.container);
    gomLop(hong.container);
    hong.unmount();

    // (5) chưa đo: `lt__chua-do`.
    const truocFetch = globalThis.fetch;
    globalThis.fetch = (async (dau: unknown) => {
      if (String(dau) === "/api/dubs/11/plan") {
        return new Response("null", { status: 200, headers: { "content-type": "application/json" } });
      }
      throw new Error(`khong cho request khac: ${String(dau)}`);
    }) as typeof globalThis.fetch;
    try {
      const chuaDo = render(taoPhanTu(LongTiengScreen, props()));
      await waitFor(
        () => {
          assert.ok(chuaDo.container.querySelector('[data-testid="lt-chua-do"]') !== null,
            "chưa tới được trạng thái 'chưa đo'");
        },
        { timeout: 3000, interval: 20 },
      );
      gomLop(chuaDo.container);
      chuaDo.unmount();
    } finally {
      globalThis.fetch = truocFetch;
    }

    // (6) chưa chọn kênh: `lt__rong`, `lt__rong--giua`.
    const rong = render(taoPhanTu(LongTiengScreen, {
      sourceId: null, translations: [], macDinhId: null,
      dubJob: null, onLongTieng: () => {}, onHuy: () => {},
      loiLongTieng: null,
    }));
    gomLop(rong.container);
    rong.unmount();
    assert.ok(trongDom.size >= 20,
      `DOM phải có nhiều lớp lt* (đo được ${trongDom.size}) — nếu ít, phép so vô nghĩa`);

    const css = readFileSync(
      path.join(process.cwd(), "src", "styles", "app.css"), "utf8",
    );
    const trongCss = new Set<string>();
    for (const m of css.matchAll(/\.(lt[A-Za-z0-9_-]*)/g)) trongCss.add(m[1]);

    // (2b) LỖI PHÁT: `fetch` của route take trả 404 ⇒ màn phải hiện `.lt__dang-nghe--loi` ở ĐÚNG
    // dòng. Phải kích hoạt TƯỜNG MINH: nếu bỏ bước này, luật `--loi` bị coi là "mồ côi" và bài
    // test ĐỎ dù luật đó có dùng thật. Bản trước bắn `dispatchEvent("error")` trên thẻ `<audio>`;
    // đường phát giờ là WebAudio nên lỗi phải đến từ chỗ THẬT của nó là phản hồi HTTP.
    const loiPhat = render(taoPhanTu(LongTiengScreen, props()));
    await choKeHoach(loiPhat.container);
    fireEvent.click(loiPhat.container.querySelector('[data-testid="lt-dong-1"]') as Element);
    await waitFor(
      () => {
        assert.ok(loiPhat.container.querySelector('[data-testid="lt-nghe-1"]') !== null,
          "chưa mở được ô sửa để thử lỗi phát");
      },
      { timeout: 3000, interval: 20 },
    );
    const truocFetchLoi = globalThis.fetch;
    globalThis.fetch = (async (dau: unknown) => {
      const url = String(dau);
      if (url === "/api/dubs/11/plan") {
        return new Response(JSON.stringify(PLAN), {
          status: 200, headers: { "content-type": "application/json" },
        });
      }
      if (url.includes("/take?i=")) return new Response("hỏng", { status: 404 });
      throw new Error(`khong cho request khac: ${url}`);
    }) as typeof globalThis.fetch;
    try {
      fireEvent.click(loiPhat.container.querySelector('[data-testid="lt-nghe-1"]') as Element);
      await waitFor(
        () => {
          assert.ok(loiPhat.container.querySelector(".lt__dang-nghe--loi") !== null,
            "take trả 404 phải hiện câu lỗi ở đúng dòng");
        },
        { timeout: 3000, interval: 20 },
      );
      assert.match(chu(loiPhat.container, ".lt__dang-nghe--loi"), /dòng 2/,
        "câu lỗi phải nói DÒNG nào — số người đọc đếm, tức 1-based");
    } finally {
      globalThis.fetch = truocFetchLoi;
    }
    // Gom lớp của nhánh LỖI PHÁT — thiếu dòng này thì `.lt__dang-nghe--loi` có trong DOM mà
    // `trongDom` không biết, và phép so hai tập báo nó là "luật mồ côi" (đo được đúng như vậy).
    gomLop(loiPhat.container);
    loiPhat.unmount();

    const thieuLuat = [...trongDom].filter((l) => !trongCss.has(l)).sort();
    assert.deepEqual(thieuLuat, [],
      `lớp có trong DOM nhưng KHÔNG có luật trong app.css: ${JSON.stringify(thieuLuat)}`);

    const luatMoCoi = [...trongCss].filter((l) => !trongDom.has(l)).sort();
    assert.deepEqual(luatMoCoi, [],
      `luật trong app.css nhưng KHÔNG lớp nào dùng: ${JSON.stringify(luatMoCoi)}`);

    // ⚠️ `tiengOn` là BỘ ĐẾM TÍCH LUỸ của cả tệp (mỗi bài thêm vào), nên so nó với `[]` ở bài
    // thứ bảy là so với tiếng ồn của SÁU BÀI TRƯỚC — đo được: đúng cái bẫy này làm bài xanh giả
    // ở lượt đầu. Mốc phải chốt ngay đầu bài, và nó bỏ qua cú bấm `<a download>` ở trên (lý do
    // ghi tại chỗ bấm).
    // ⚠️ Nhiễu của JSDOM, lọc ĐÚNG một dạng: `HTMLMediaElement.play()` không được cài đặt nên
    // jsdom in `Not implemented: HTMLMediaElement's play() method`. Trình duyệt thật có cài đặt,
    // nên đây là giới hạn môi trường test, không phải lỗi màn này. Mọi tiếng ồn khác vẫn ĐỎ.
    const laNhieuMedia = (d: string): boolean =>
      /^Not implemented: HTMLMediaElement's (play|pause)\(\) method$/.test(
        d.replace(/^error: /, "").trim(),
      );
    assert.deepEqual(tiengOn.slice(mocSauKhiNghe).filter((d) => !laNhieuMedia(d)), [],
      `bài hình thức không được sinh tiếng ồn console: ${JSON.stringify(tiengOn.slice(mocSauKhiNghe).slice(0, 2))}`);
  });
});
