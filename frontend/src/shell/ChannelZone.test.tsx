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
import { readFileSync } from "node:fs";

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
let waitFor: (cb: () => void, options?: { timeout?: number; interval?: number }) => Promise<void>;
let fireEvent: { click: (el: Element) => void; change: (el: Element, init: unknown) => void };
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let ChannelZone: (props: unknown) => unknown;

/**
 * Hàm nạp TIÊM cho các bài KHÔNG đo đường nạp (bài cũ của W1 phải giữ nguyên mệnh đề).
 *
 * ⚠️ Đây là chính cái seam mà brief W2 định nghĩa (`napTep(files, lang)`), không phải mock
 * `endpoints.ts`; đường HTTP THẬT nằm ở `App.test.tsx` (server `node:http` thật).
 */
const khongNap: (files: File[], lang: "zh" | "en") => Promise<[]> = async () => [];

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

/**
 * Cho tới khi một phần tử khớp `chon` thỏa `dieuKien` — **TÍN HIỆU**, không phải đồng hồ.
 *
 * ⚠️ Và tín hiệu phải là **ĐÚNG thứ bài sắp ĐỌC** (ERRATA #38 mục 2 / #39 mục 5): ở đây là chính
 * dòng kết quả nạp trong `.nap__kq`.
 */
async function choDong(
  container: HTMLElement,
  chon: string,
  dieuKien: (text: string) => boolean,
): Promise<string> {
  let cuoi = "";
  await waitFor(
    () => {
      const dong = [...container.querySelectorAll(chon)].map((el) => el.textContent ?? "");
      const thay = dong.find(dieuKien);
      assert.ok(thay !== undefined, `chua thay dong ${chon}; do duoc ${JSON.stringify(dong)}`);
      cuoi = thay;
    },
    { timeout: 5000, interval: 20 },
  );
  return cuoi;
}

describe("ChannelZone: chon duoc KENH (Task W1)", () => {
  before(async () => {
    teardownDom();
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    waitFor = api.waitFor;
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
        onNapTep: khongNap,
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
        onNapTep: khongNap,
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
        onNapTep: khongNap,
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

  // -------------------------------------------------------------------------
  // TASK W2 — LỐI NẠP GỌN Ở VÙNG KÊNH (§12.2: nạp tệp thứ 2..N khi ĐÃ có kênh)
  //
  // VÌ SAO NÓ TỒN TẠI: khi đã có bản ghi, vùng giữa hiện danh sách đoạn nên khung §4.2 KHÔNG còn
  // ở đó ⇒ nếu vùng KÊNH không có cửa nạp thì tệp thứ 2..N **không có cửa nào** vào app. Đó là
  // lý do lối này phải **LUÔN tới được** — kể cả khi danh sách rỗng, đang đọc, hay đang lỗi.
  // -------------------------------------------------------------------------

  it("W2 LỐI GỌN: LUÔN tới được (có kênh · rỗng · đang đọc · lỗi), và nhận NHIỀU tệp", () => {
    for (const ca of [
      { ten: "DA CO KENH", props: { sources: SOURCES, loading: false, error: null } },
      { ten: "RONG", props: { sources: [], loading: false, error: null } },
      { ten: "DANG DOC", props: { sources: null, loading: true, error: null } },
      { ten: "LOI", props: { sources: null, loading: false, error: "500: nguồn dữ liệu hỏng" } },
    ]) {
      const { container, unmount } = render(
        taoPhanTu(ChannelZone, {
          ...ca.props,
          jobs: JOBS,
          selectedId: null,
          onSelect: () => {},
          onNapTep: khongNap,
        }),
      );
      const o = container.querySelector('[data-testid="ch-nap-o-tep"]');
      assert.ok(o !== null, `ca ${ca.ten}: loi nap gon KHONG toi duoc (khong co o chon tep)`);
      assert.equal(
        (o as HTMLInputElement).getAttribute("type"),
        "file",
        `ca ${ca.ten}: o nap gon phai la o chon tep`,
      );
      assert.ok(
        (o as HTMLInputElement).hasAttribute("multiple"),
        `ca ${ca.ten}: thieu \`multiple\` ⇒ khong nap duoc 3 tep cung luc (§12.2)`,
      );
      unmount();
    }
  });

  it("W2 LỐI GỌN: chọn tệp ⇒ đi vào CÙNG hàm nạp (seam), và kết quả hiện bằng CHỮ", async () => {
    const goi: string[][] = [];
    const { container, unmount } = render(
      taoPhanTu(ChannelZone, {
        sources: SOURCES,
        jobs: JOBS,
        loading: false,
        error: null,
        selectedId: null,
        onSelect: () => {},
        onNapTep: async (files: File[]) => {
          goi.push(files.map((t) => t.name));
          return [
            { ten: files[0]?.name ?? "", ok: true, sourceId: 21 },
            { ten: files[1]?.name ?? "", ok: false, loi: "422: tệp rỗng" },
          ];
        },
      }),
    );

    // `fireEvent.change` với `File` THAT; jsdom khong co layout nen day la duong DUY NHAT do duoc.
    const a = new File([new Uint8Array([1, 2, 3])], "moi.wav", { type: "audio/wav" });
    const b = new File([new Uint8Array([])], "rong.wav", { type: "audio/wav" });
    fireEvent.change(container.querySelector('[data-testid="ch-nap-o-tep"]') as Element, {
      target: { files: [a, b] },
    });

    // ⚠️ Cho DUNG tin hieu ma bai sap doc: DONG KET QUA. Do la dau ra cua cung mot luot nap.
    const xong = await choDong(container, ".nap__kq", (t) => t.includes("moi.wav"));
    const loi = await choDong(container, ".nap__kq", (t) => t.includes("rong.wav"));
    assert.match(xong, /đã nạp — kênh 21/, "ket qua TUNG tep phai hien bang CHU (kem id kenh)");
    assert.match(loi, /422: tệp rỗng/, "cau loi cua backend phai hien NGUYEN VAN");
    assert.deepEqual(goi, [["moi.wav", "rong.wav"]], "loi gon phai goi DUNG ham nap voi DUNG tep");

    assert.deepEqual(tiengOn, [], "loi nap gon khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // HINH THUC — ghim LUAT CSS cua BO CHON CHE DO + MUC KENH DANG CHON
  //
  // VI SAO BAI NAY TON TAI (do duoc, KHONG phai suy luan): mutation `B7-css` xoa TAM khoi
  // luat `.cd*` + `.ch__item[aria-pressed="true"]` + `.ch__dau` ma GIU nguyen
  // `className`/`aria-pressed`/glyph. Tren CAY TRUOC vong sua do duoc
  // `tests 180 / pass 178 / fail 2 / cancelled 0`, tuc **0 bai do them**: ba bai DOM o tren
  // chi khang dinh `className`/`aria-pressed`/glyph, va mot `className` trong TSX KHONG ve gi ca
  // (ERRATA #15 muc 3, do duoc HAI CHIEU o Task 6). Bon tinh nang HINH THUC cua T6–T10 deu co
  // mot bai DOC `app.css`; W1 la ngoai le duy nhat. Sau khi them bai nay, cung mutation do
  // `tests 185 / pass 182 / fail 3` ⇒ **dung MOT bai do them**, va no la bai nay.
  //
  // ⚠️ BAI NAY GHIM **QUAN HE**, KHONG GHIM NGUYEN VAN KHOI LUAT/TEN CLASS: ghim literal la
  // DONG BANG hinh thuc (ERRATA #34 muc 1) — them/bot mot khai bao o noi khac van phai XANH.
  // Moi assertion khang dinh mot KHAI BAO trong luat VA mot QUAN HE (trang thai `:checked` /
  // `[aria-pressed="true"]` ↔ hinh thuc; glyph ↔ le cua o; hai luat bo cuc voi nhau).
  // -------------------------------------------------------------------------

  it("HINH THUC: LUAT CSS cua BO CHON CHE DO + MUC KENH DANG CHON CO THAT trong `app.css`", () => {
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");

    // (1) QUAN HE giua hai luat: bo chon che do chi nam tren MOT hang neu hang header la flex.
    assert.match(appCss, /\.shell__head \{[^}]*display: flex/,
      "bo chon che do chi nam MOT hang neu `.shell__head` la flex");
    assert.match(appCss, /\.cd \{[^}]*display: flex[^}]*align-items: center/,
      "nhom chon che do phai la MOT hang flex can doc giua (nhan nam CANH o radio)");

    // (2) QUAN HE trang thai -> hinh thuc: chu cua nhan phai SANG len theo `:checked` cua
    //     chinh o radio BEN CANH no (`+`) — khong phai theo mot lop rieng (lop rieng la
    //     nguon su that thu hai cho cung mot cau hoi "che do nao dang chon").
    assert.match(appCss, /\.cd__radio:checked \+ \.cd__nhan \{[^}]*color: var\(--ink-0\)/,
      "che do DANG CHON phai doi hinh thuc bang QUAN HE `:checked + nhan`");

    // (3) QUAN HE trang thai MAY doc duoc -> hinh thuc: luat to hinh thuc cua muc KENH phai
    //     KEYED tren chinh `[aria-pressed="true"]` (cung nguon su that voi thuoc tinh ma
    //     screen reader doc), khong phai mot lop trang tri song song.
    assert.match(appCss, /\.ch__item\[aria-pressed="true"\] \{[^}]*border-left-color: var\(--signal\)/,
      'muc DANG CHON phai doi hinh thuc bang chinh `[aria-pressed="true"]`');

    // (4) DAU NHIN THAY duoc (khong chi doi MAU): glyph phai duoc DINH VI trong o.
    assert.match(appCss, /\.ch__dau \{[^}]*position: absolute[^}]*left: var\(--sp-2\)/,
      "glyph `▸` phai duoc dinh vi tuyet doi o le trai muc kenh");
  });

  it("W2 M4: `<ul class=\"ch__danh-sach\">` phai co LUAT RESET trong `app.css` (nợ Task 4/W1 đóng kèm)", () => {
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");

    // DO DUOC TRUOC VONG SUA (review W2 §9.6): SAU lop cua vung KENH (`.ch`, `.ch__danh-sach`,
    // `.ch__dong`, `.ch__rong`, `.ch__loi`, `.ch__cho`) co **0 luat** trong `app.css` (do bang
    // `Select-String -SimpleMatch`: 0 cho ca sau; so sanh `.ch__item` = 3, `.ch__nap` = 9), va
    // `main.tsx` chi nap `tokens.css` + `app.css` nen KHONG co stylesheet thu hai.
    // He qua: `<ul class="ch__danh-sach">` khong duoc reset `list-style`/`padding` ⇒ trinh duyet
    // ve DAU DAU DONG + thut le mac dinh.
    //
    // ⚠️ Day la NO cua Task 4/W1, KHONG phai viec cua W2 — vong sua W2 dong phan RE NHAT (reset
    // `<ul>`) va KHAI phan con lai (`.ch`, `.ch__dong`, `.ch__rong`, `.ch__loi`, `.ch__cho` van
    // chua co luat). ⚠️ Va jsdom KHONG co layout ⇒ "danh sach hien dau dau dong" chi chung minh
    // duoc bang LUAT nay + mot ANH chup trong trinh duyet THAT (o day KHONG co anh nao).
    assert.match(
      appCss,
      /\.ch__danh-sach \{[^}]*margin: 0[^}]*padding: 0[^}]*list-style: none/,
      '`<ul class="ch__danh-sach">` phai duoc RESET (margin/padding/list-style)',
    );
  });

  /**
   * Cac khoi luat cua `app.css` (da bo chu thich) — doc VAN BAN, khong hoi jsdom (no khong co CSS).
   * Cung khuon voi `IntakeFrame.test.tsx`.
   */
  function cacKhoi(css: string): { chon: string; than: string }[] {
    const sach = css.replace(/\/\*[\s\S]*?\*\//g, "");
    const ra: { chon: string; than: string }[] = [];
    for (const m of sach.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      ra.push({ chon: (m[1] ?? "").trim(), than: m[2] ?? "" });
    }
    return ra;
  }

  /** Tap lop `ch*` ma `app.css` TAO KIEU (ten lop trong SELECTOR, khong phai `className` trong TSX). */
  function lopChTrongCss(khoi: { chon: string; than: string }[]): Set<string> {
    const ra = new Set<string>();
    for (const k of khoi) {
      for (const m of k.chon.matchAll(/\.(ch(?:__[a-z0-9-]+)?)/g)) ra.add(m[1] ?? "");
    }
    ra.delete("");
    return ra;
  }

  /**
   * NAM lop cua vung KENH **CHUA CO LUAT NAO** trong `app.css` — KHAI RA, khong che
   * (`app.css:1429-1440`, bao cao W2 §5.4, comment bai `W2 M4`).
   *
   * ⚠️ Vi sao phai khai: phep ghim hai chieu o DUOI khang dinh "moi lop trong DOM deu co luat".
   * Voi nam lop nay, menh de do SAI ngay hom nay — nhung no la NO da khai (Task 4/W1), khong phai
   * mot loi moi. Danh sach nay la mot phep khai, va no chi duoc PHEP la tap CON cua cac lop khong
   * co luat: dong not mot mon no (them luat) KHONG lam bai do.
   */
  const NO_CHUA_CO_LUAT: ReadonlySet<string> = new Set([
    "ch",
    "ch__dong",
    "ch__rong",
    "ch__loi",
    "ch__cho",
  ]);

  it("P3 (nợ W2 đóng kèm): LUẬT `.ch*` ↔ CLASS `ch*` KHỚP NHAU (hai chiều) — đổi tên class trong DOM mà giữ luật ⇒ ĐỎ", async () => {
    // ---------------------------------------------------------------------------
    // ⚠️ VI SAO BAI NAY TON TAI — do duoc, KHONG phai suy luan (mutant `P3` cua re-review W2):
    // doi `className` trong DOM (`ch__danh-sach` → `ch__danh-sach-doi-ten`) ma GIU NGUYEN luat
    // trong `app.css` ⇒ `fail 2`, **0 bai do**. Tuc luat `.ch__danh-sach` tro thanh LUAT MO COI
    // (dung lop `ERRATA #36 muc 5`) ma khong ai thay. Bai `W2 M4` ngay tren ghim CHU CUA LUAT,
    // khong ghim QUAN HE luat ↔ class; va `ChannelZone.test.tsx` truoc do KHONG co bai hai chieu nao.
    //
    // Bai nay ghim QUAN HE, KHONG ghim danh sach ten lop nguyen van (ERRATA #34 muc 1):
    //   (A) MOI lop `ch*` ma `app.css` TAO KIEU phai XUAT HIEN trong DOM THAT ⇒ luat mo coi = DO;
    //   (B) MOI lop `ch*` trong DOM THAT phai duoc `app.css` tao kieu (tru nam lop NO da khai).
    // ---------------------------------------------------------------------------
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const trongCss = lopChTrongCss(cacKhoi(appCss));

    const trongDom = new Set<string>();
    const gom = (container: HTMLElement): void => {
      for (const el of container.querySelectorAll("*")) {
        for (const ten of el.classList) if (/^ch(__|$)/.test(ten)) trongDom.add(ten);
      }
    };

    // (1) CO KENH: `ch`, `ch__danh-sach`, `ch__dong`, `ch__item`, `ch__dau`, `ch__ten`, `ch__meta`,
    //     `ch__tieng`, `ch__buoc` + loi nap gon `ch__nap*`.
    const co = render(
      taoPhanTu(ChannelZone, {
        sources: SOURCES,
        jobs: JOBS,
        loading: false,
        error: null,
        selectedId: 1,
        onSelect: () => {},
        onNapTep: khongNap,
      }),
    );
    gom(co.container);
    co.unmount();

    // (2) BA trang thai CON LAI cua vung (moi trang thai mot lop CHI co o do).
    for (const props of [
      { sources: [], loading: false, error: null },
      { sources: null, loading: true, error: null },
      { sources: null, loading: false, error: "500: nguồn dữ liệu hỏng" },
    ]) {
      const c = render(
        taoPhanTu(ChannelZone, {
          ...props,
          jobs: JOBS,
          selectedId: null,
          onSelect: () => {},
          onNapTep: khongNap,
        }),
      );
      gom(c.container);
      c.unmount();
    }

    // (3) HAI trang thai CHI ton tai khi mot luot nap CHUA tra: `.ch__nap-cho` (dang nap) va
    //     `.ch__nap-bo-qua` (luot chon bi bo qua). Phai GOM, neu khong phep kiem (A) se bao chung
    //     la "LUAT MO COI" oan.
    const cTreo = render(
      taoPhanTu(ChannelZone, {
        sources: SOURCES,
        jobs: JOBS,
        loading: false,
        error: null,
        selectedId: null,
        onSelect: () => {},
        onNapTep: () => new Promise<never[]>(() => {}),
      }),
    );
    const o = cTreo.container.querySelector('[data-testid="ch-nap-o-tep"]') as Element;
    const a = new File([new Uint8Array([1, 2, 3])], "mot.wav", { type: "audio/wav" });
    fireEvent.change(o, { target: { files: [a] } });
    await waitFor(
      () => {
        assert.equal(cTreo.container.querySelectorAll(".ch__nap-cho").length, 1, "chua thay `.ch__nap-cho`");
      },
      { timeout: 5000, interval: 20 },
    );
    gom(cTreo.container);
    fireEvent.change(o, { target: { files: [new File([new Uint8Array([4])], "hai.wav")] } });
    await waitFor(
      () => {
        assert.equal(cTreo.container.querySelectorAll(".ch__nap-bo-qua").length, 1, "chua thay `.ch__nap-bo-qua`");
      },
      { timeout: 5000, interval: 20 },
    );
    gom(cTreo.container);
    cTreo.unmount();

    assert.ok(trongCss.size >= 12, `phai doc duoc cac lop \`ch*\` tu app.css; do duoc ${trongCss.size}`);
    assert.ok(trongDom.size >= 12, `phai thu duoc cac lop \`ch*\` tu DOM; do duoc ${trongDom.size}`);

    // (A) LUAT ⇒ LOP.
    const moCoi = [...trongCss].filter((ten) => !trongDom.has(ten)).sort();
    assert.deepEqual(
      moCoi,
      [],
      `LUAT MO COI: ${JSON.stringify(moCoi)} — luat nay khong lop nao trong DOM mang, tuc no KHONG `
      + `tao kieu cho thu gi. Lop co trong DOM: ${JSON.stringify([...trongDom].sort())}`,
    );

    // (B) LOP ⇒ LUAT.
    const voLuat = [...trongDom].filter((ten) => !trongCss.has(ten) && !NO_CHUA_CO_LUAT.has(ten)).sort();
    assert.deepEqual(
      voLuat,
      [],
      `LOP KHONG CO LUAT: ${JSON.stringify(voLuat)} — lop nay nam trong DOM nhung app.css khong tao `
      + `kieu cho no, va no KHONG nam trong danh sach NO da khai. Luat co trong app.css: `
      + `${JSON.stringify([...trongCss].sort())}`,
    );
  });
});
