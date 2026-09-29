/**
 * Test `<Transport/>` THAT trong jsdom: nut phat, timecode mono, track co dau doc,
 * ba nut xuat — va DAY NOI cua "phat toi moc cuoi cua doan thi tu nhay doan".
 *
 * ## Ba thu tep nay KHONG do duoc — khai ra, khong che
 *
 *  1. **Trinh duyet THAT la BAT KHA** (ERRATA #5 muc 3: Chromium chet o Mojo named
 *     pipe) ⇒ **"seek trong trinh duyet that" CHUA CHUNG MINH**. Bang chung HTTP
 *     `Range` nam o BAO CAO task (backend that + DB scratch + tep media that + curl
 *     `Range: bytes=0-99`), khong nam o tep nay.
 *  2. **jsdom KHONG giai ma media.** Do duoc ngay trong tep nay (bai "GIOI HAN CUA
 *     JSDOM"): `HTMLMediaElement.prototype.play`/`pause` KHONG duoc hien thuc — chung
 *     log `Not implemented: HTMLMediaElement's play() method` va `play()` tra
 *     `undefined` chu khong phai Promise. Vi vay hai phuong thuc do duoc THAY trong
 *     `describe` nay bang hai ham GHI LAI (spy). Do la **GO RO GIOI HAN CUA JSDOM**,
 *     KHONG phai gia lap nghiep vu: khang dinh la "thanh transport DA YEU CAU phat",
 *     khong phai "da nghe thay tieng". ⇒ **KHONG duoc doc tep nay la "da kiem phat nhac".**
 *     `currentTime` thi NGUOC LAI: jsdom 30.1.1 dat duoc that (co setter tren prototype,
 *     doc lai dung gia tri) ⇒ bai "DAY NOI" bom duoc vi tri phat THAT, khong phai do gian.
 *  3. **jsdom khong co layout va khong ap CSS** ⇒ `left` cua dau doc chi la mot KHAI
 *     BAO doc duoc, KHONG phai vi tri ve ra. Vi vay tep nay ghim RIENG mot bai doc
 *     `app.css`: mot test chi khang dinh `className` KHONG chung minh luat CSS ton tai
 *     (ERRATA #15 muc 3 — do duoc hai chieu o Task 6).
 *
 * ## Quyet dinh "toi moc cuoi thi sang doan ke" nam o DAU
 *
 * Trong `src/lib/playback.ts` (HAM THUAN) va duoc ghim bang `node:test` thuong o
 * `src/lib/playback.test.ts`. Tep nay chi ghim **DAY NOI**: listener `timeupdate` co
 * duoc gan khong, va khi su kien duoc bom vao thi co nhay dung luc khong.
 *
 * ## LUAT DOM (ERRATA #9 muc 1/6)
 *
 *  - MOI hook dat/tra global nam TRONG `describe()`: duoi `--test-isolation=none`,
 *    hook cap TEP bi node:test keo len GOC ca luot (moi `before` truoc MOI bai, moi
 *    `after` sau MOI bai) — do bang dong ho chung, khong phai suy dien.
 *  - `setupDom`/`teardownDom` cua CHINH tep nay; khong gia dinh jsdom cua tep khac con
 *    song, va khong de lai global nao cho tep sau. Hai ham spy tren prototype duoc tra
 *    lai TRONG `after`, TRUOC `teardownDom()`.
 *  - `console.error`/`console.warn` bi TAM THAY de bat tieng on va duoc TRA LAI trong `after`.
 *  - LUON chay TOAN BO `npm test`, khong chay le tep.
 *
 * ⚠️ **DUNG dua mot node DOM SONG vao `assert`**: do duoc o Task 6 la **218 697 ms roi
 * OOM** (`Array buffer allocation failed`) vi `assert` dinh dang gia tri trong thong
 * diep loi KHONG gioi han do sau (ERRATA #14 muc 3 + #15 muc 1). Moi khang dinh ve
 * "khong co phan tu" o day DEM so luong, moi so sanh node tra ve BOOLEAN.
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import type { Segment } from "../api/types.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

function doan(i: number, start: number, end: number): Segment {
  return { i, start, end, text: `đoạn ${i}`, suspect: false };
}

const BA_DOAN: Segment[] = [doan(0, 0, 2), doan(1, 2, 4), doan(2, 4, 6)];

/** Mo ta mot gia tri ma KHONG goi sau vao no (an toan voi node DOM da bi close). */
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
let fireEvent: {
  click: (el: Element) => void;
  timeUpdate: (el: Element) => void;
};
let cleanup: () => void;
/**
 * `waitFor` cua Testing Library — phep cho THEO TIN HIEU DOM (khong phai `sleep`).
 *
 * ⚠️ Vi sao can o tep nay (vong gom no, `D3`): cua so NGHE LAI (`data-nghe-lai`) mo ra roi dong lai
 * theo MOT khoang thoi gian, nen "da dong chua" la mot TIN HIEU phai CHO — va deadline cua `waitFor`
 * chi la TRAN, khong phai dieu kien thoat (`#35` muc 2).
 */
let waitFor: (cb: () => void, opts?: { timeout?: number; interval?: number }) => Promise<void>;
/** `createElement` — goi ham component NGOAI chu trinh render se nem `useState` dispatcher null. */
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let Transport: (props: unknown) => unknown;
/** `<Transport/>` la component DIEU KHIEN: `playing` la prop, nen can mot chu so huu. */
let Thanh: (props: unknown) => unknown;
/**
 * Chu so huu `sourceId` — de DO duong "DOI KENH" (Task W1). `sourceId` la prop, nen muon
 * doi no giua hai lan render thi phai co mot component giu no (giong `UiState.channelId`
 * cua shell) va mot nut bam.
 */
let ThanhDoiKenh: (props: unknown) => unknown;
let exportUrl: (id: number, fmt?: "srt" | "vtt" | "ass", bilingual?: boolean) => string;
let mediaUrl: (id: number) => string;

/** Hai ham spy thay `play`/`pause` cua jsdom (xem muc 2 o dau tep). */
const daGoi = { play: 0, pause: 0, playTrenPhanTu: false, pauseTrenPhanTu: false };
let playGoc: (() => unknown) | null = null;
let pauseGoc: (() => unknown) | null = null;
let playGia: (() => unknown) | null = null;
let pauseGia: (() => unknown) | null = null;

/** `textContent` cua phan tu DAU TIEN khop `chon` — khong hoi ca DOM. */
function chu(container: HTMLElement, chon: string): string {
  const el = container.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.textContent ?? "";
}

/** Phan tu DAU TIEN khop `chon`, da kiem la CO — tra ve node cho viec doc thuoc tinh. */
function phanTu(container: HTMLElement, chon: string): Element {
  const el = container.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el;
}

describe("Transport: nut phat, timecode mono, track co dau doc, ba nut xuat", () => {
  before(async () => {
    // Chuan hoa TRUOC khi cai: khong dua vao viec tep khac da tra global hay chua.
    teardownDom();
    // Origin chi de `fetch` tuong doi resolve duoc; tep nay khong goi mang nao.
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    waitFor = api.waitFor;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const api2: any = await import("../api/endpoints.ts");
    exportUrl = api2.exportUrl;
    mediaUrl = api2.mediaUrl;
    const man: any = await import("./Transport.tsx");
    Transport = man.Transport;

    // Chu so huu `playing` cua suite nay — dung `useState` THAT cua React, khong phai
    // mot bien ngoai: component duoc viet la DIEU KHIEN (giong `UiState` cua shell).
    Thanh = (props: any): unknown => {
      const [playing, datPlaying] = react.useState(false);
      return react.createElement(Transport, { ...props, playing, onPlayingChange: datPlaying });
    };

    // Chu so huu `sourceId` cho bai DOI KENH: bam nut ⇒ `sourceId` doi ⇒ `Transport` duoc
    // render lai voi prop moi (dung cach `App` lam khi `selectChannel` doi `ui.channelId`).
    ThanhDoiKenh = (props: any): unknown => {
      const [sourceId, datSourceId] = react.useState<number | null>(3);
      return react.createElement(
        "div",
        null,
        react.createElement(
          "button",
          { type: "button", "data-testid": "doi-kenh", onClick: () => datSourceId(4) },
          "doi kenh",
        ),
        react.createElement(Transport, { ...props, sourceId }),
      );
    };

    // ⚠️ THAY `play`/`pause` CUA JSDOM — khong phai gia lap nghiep vu, ma la go ro mot
    // gioi han DA DO: jsdom khong hien thuc hai phuong thuc nay (chung log
    // "Not implemented" va `play()` tra `undefined`). Neu khong thay, moi lan bam phat
    // se do mot dong "Not implemented" vao `console.error` — va chinh `App.test.tsx`
    // ghim rang render `<App/>` KHONG duoc sinh tieng on console.
    const w: any = (globalThis as any).window;
    playGoc = w.HTMLMediaElement.prototype.play;
    pauseGoc = w.HTMLMediaElement.prototype.pause;
    playGia = function (this: unknown): unknown {
      daGoi.play += 1;
      daGoi.playTrenPhanTu = this === w.document.querySelector("audio");
      return Promise.resolve();
    };
    pauseGia = function (this: unknown): unknown {
      daGoi.pause += 1;
      daGoi.pauseTrenPhanTu = this === w.document.querySelector("audio");
      return undefined;
    };
    w.HTMLMediaElement.prototype.play = playGia;
    w.HTMLMediaElement.prototype.pause = pauseGia;

    console.error = (...args: unknown[]): void => {
      tiengOn.push(`error: ${args.map(mo).join(" ")}`);
    };
    console.warn = (...args: unknown[]): void => {
      tiengOn.push(`warn: ${args.map(mo).join(" ")}`);
    };
  });

  beforeEach(() => {
    tiengOn.length = 0;
    daGoi.play = 0;
    daGoi.pause = 0;
    daGoi.playTrenPhanTu = false;
    daGoi.pauseTrenPhanTu = false;
  });

  afterEach(() => {
    cleanup();
  });

  after(() => {
    console.error = consoleGoc.error;
    console.warn = consoleGoc.warn;
    const w: any = (globalThis as any).window;
    if (w !== undefined && playGoc !== null && pauseGoc !== null) {
      w.HTMLMediaElement.prototype.play = playGoc;
      w.HTMLMediaElement.prototype.pause = pauseGoc;
    }
    teardownDom();
  });

  it("RONG: chua chon kenh ⇒ nut phat VO HIEU, khong co `src`, ba nut xuat khong co `href`", () => {
    const { container, unmount } = render(
      taoPhanTu(Transport, { sourceId: null, segments: [], translationId: null }),
    );

    // Khong co nguon thi KHONG duoc co `src`: mot phan tu media tro vao `/api/media/null`
    // la mot request 422 ma khong ai doc.
    assert.equal(phanTu(container, "audio").hasAttribute("src"), false, "khong co nguon thi khong co `src`");
    const nut = phanTu(container, ".tp__phat");
    assert.equal((nut as HTMLButtonElement).disabled, true, "khong co gi de phat thi nut phai VO HIEU");
    assert.equal(nut.getAttribute("aria-pressed"), "false");
    assert.match(container.textContent ?? "", /chưa chọn kênh/);

    // Ba nut xuat VAN phai CO MAT (chung la bat bien cua thanh transport), nhung
    // khong duoc co `href` khi chua co ban dich nao.
    const xuat = [...container.querySelectorAll(".tp__xuat")];
    assert.equal(xuat.length, 3, "thanh transport luon co dung BA nut xuat");
    for (const a of xuat) {
      assert.equal(a.hasAttribute("href"), false, "chua co ban dich thi khong duoc co href");
      assert.equal(a.getAttribute("aria-disabled"), "true");
    }

    assert.deepEqual(tiengOn, [], "trang thai rong khong duoc sinh tieng on console");
    unmount();
  });

  it("BA NUT XUAT: `href` BANG DUNG `endpoints.exportUrl(...)` — khong tu ghep URL o client", () => {
    const { container, unmount } = render(
      taoPhanTu(Transport, { sourceId: 3, segments: BA_DOAN, translationId: 7, duration: 6 }),
    );

    const xuat = [...container.querySelectorAll(".tp__xuat")];
    assert.equal(xuat.length, 3, "phai co dung BA nut xuat");
    const href = xuat.map((a) => a.getAttribute("href"));

    // (a) Bang DUNG ket qua cua ham that — menh de cua brief, va cung la menh de cua
    //     `Global Constraints`: client KHONG tinh lai thu backend da tinh.
    assert.deepEqual(href, [
      exportUrl(7, "srt", false),
      exportUrl(7, "vtt", false),
      exportUrl(7, "ass", false),
    ]);
    // (b) Va bang DUNG chuoi ma route that sinh ra (doc tu backend: xem bai DOI CHIEU
    //     ROUTE THAT). Ve (a) mot minh la mot phep do TU THOA MAN: neu `exportUrl` sai
    //     thi ca hai ve cua phep so sanh sai giong nhau.
    assert.deepEqual(href, [
      "/api/export/7?format=srt&bilingual=0",
      "/api/export/7?format=vtt&bilingual=0",
      "/api/export/7?format=ass&bilingual=0",
    ]);
    for (const a of xuat) {
      assert.equal(a.getAttribute("aria-disabled"), null, "co ban dich roi thi KHONG duoc vo hieu");
      assert.equal(a.hasAttribute("download"), true, "nut xuat la duong TAI TEP");
    }

    assert.deepEqual(tiengOn, [], "dung ba nut xuat khong duoc sinh tieng on console");
    unmount();
  });

  it("BA NUT XUAT: tham so `bilingual` duoc CHUYEN TIEP, khong hard-code", () => {
    const { container, unmount } = render(
      taoPhanTu(Transport, { sourceId: 3, segments: BA_DOAN, translationId: 7, bilingual: true }),
    );

    const href = [...container.querySelectorAll(".tp__xuat")].map((a) => a.getAttribute("href"));
    assert.deepEqual(href, [
      exportUrl(7, "srt", true),
      exportUrl(7, "vtt", true),
      exportUrl(7, "ass", true),
    ]);
    assert.match(href[0] ?? "", /bilingual=1/, "`bilingual` la `int` (0/1) o backend, khong phai bool chuoi");

    unmount();
  });

  it("DOI CHIEU ROUTE THAT: URL client sinh ra khop khai bao trong backend", () => {
    // Khong the chay backend that o day (bai nay khong goi mang), nhung co the doc
    // CHINH tep route: ten tham so va hinh dang duong dan la hop dong giua hai phia.
    const xuat = readFileSync(
      new URL("../../../backend/app/api/routes_translations.py", import.meta.url),
      "utf8",
    );
    const media = readFileSync(
      new URL("../../../backend/app/api/routes_media.py", import.meta.url),
      "utf8",
    );

    assert.ok(xuat.includes('export_router = APIRouter(prefix="/api/export"'), "tien to route xuat da doi");
    assert.ok(xuat.includes('@export_router.get("/{translation_id}"'), "route xuat da doi hinh dang");
    assert.ok(xuat.includes('format: str = "srt", bilingual: int = 0'), "ten/thu tu tham so export da doi");
    assert.ok(media.includes('router = APIRouter(prefix="/api/media"'), "tien to route media da doi");
    assert.ok(media.includes('@router.get("/{source_id}")'), "route media da doi hinh dang");

    assert.ok(exportUrl(7, "srt", false).startsWith("/api/export/7?"), "URL xuat phai nam duoi tien to do");
    assert.ok(mediaUrl(3).startsWith("/api/media/3"), "URL media phai nam duoi tien to do");
    assert.equal(mediaUrl(3), "/api/media/3", "`mediaUrl` chi la duong dan tuong doi qua proxy 3100");
  });

  it("NUT PHAT: nhan va `aria-pressed` doi dung khi phat / tam dung", () => {
    const { container, unmount } = render(
      taoPhanTu(Thanh, { sourceId: 3, segments: BA_DOAN, translationId: 7, duration: 6 }),
    );

    const nut = phanTu(container, ".tp__phat");
    assert.equal(nut.getAttribute("aria-pressed"), "false", "chua phat thi `aria-pressed` phai la false");
    assert.equal(nut.textContent, "phát");

    fireEvent.click(nut);
    assert.equal(nut.getAttribute("aria-pressed"), "true", "dang phat thi `aria-pressed` phai la true");
    assert.equal(nut.textContent, "tạm dừng");

    fireEvent.click(nut);
    assert.equal(nut.getAttribute("aria-pressed"), "false", "tam dung thi phai quay lai false");
    assert.equal(nut.textContent, "phát");

    assert.deepEqual(tiengOn, [], "bam phat/tam dung khong duoc sinh tieng on console");
    unmount();
  });

  it("PHAT: bam phat ⇒ YEU CAU `play()`; bam tam dung ⇒ YEU CAU `pause()`", () => {
    const { container, unmount } = render(
      taoPhanTu(Thanh, { sourceId: 3, segments: BA_DOAN, translationId: 7, duration: 6 }),
    );
    const nut = phanTu(container, ".tp__phat");

    // Chua bam: KHONG duoc goi gi. Mot component goi `pause()` luc mount la mot loi
    // im lang (va duoi jsdom no do "Not implemented" ra console ⇒ lam do `App.test.tsx`).
    assert.equal(daGoi.play, 0, "chua bam phat thi khong duoc goi `play()`");
    assert.equal(daGoi.pause, 0, "mount KHONG duoc goi `pause()`");

    fireEvent.click(nut);
    assert.equal(daGoi.play, 1, "bam phat phai YEU CAU phat dung MOT lan");
    assert.ok(daGoi.playTrenPhanTu, "`play()` phai duoc goi tren CHINH phan tu media da render");

    fireEvent.click(nut);
    assert.equal(daGoi.pause, 1, "bam tam dung phai YEU CAU dung dung MOT lan");
    assert.ok(daGoi.pauseTrenPhanTu, "`pause()` phai duoc goi tren CHINH phan tu media da render");

    assert.deepEqual(tiengOn, [], "yeu cau phat/dung khong duoc sinh tieng on console");
    unmount();
  });

  it("DAY NOI: listener `timeupdate` duoc gan ⇒ toi moc cuoi cua doan thi NHAY doan", () => {
    const nhay: number[] = [];
    const { container, unmount } = render(
      taoPhanTu(Transport, {
        sourceId: 3,
        segments: BA_DOAN,
        translationId: 7,
        duration: 6,
        currentSegment: 1,
        onSegmentChange: (i: number): void => {
          nhay.push(i);
        },
      }),
    );

    const audio = phanTu(container, "audio") as HTMLAudioElement;

    // (a) CHUA toi moc cuoi cua doan 1 ([2,4)): KHONG nhay. Thieu ve nay thi mot ban
    //     "nhay o moi su kien" cung xanh — dung loai phep do RONG ma review Task 4
    //     do duoc o nhan dao `S2`.
    audio.currentTime = 3.5;
    fireEvent.timeUpdate(audio);
    assert.deepEqual(nhay, [], "chua vuot `segment.end` thi KHONG duoc nhay doan");
    assert.equal(audio.currentTime, 3.5, "khong nhay thi khong duoc dong vao vi tri phat");

    // (b) VUOT moc cuoi: bao nhay sang doan ke VA dat lai vi tri phat ve `start` cua
    //     doan do — do chinh la cu NHAY, khong phai chi la mot thong bao.
    audio.currentTime = 4.4;
    fireEvent.timeUpdate(audio);
    assert.deepEqual(nhay, [2], "vuot `segment.end` thi phai bao nhay sang doan 2");
    assert.equal(audio.currentTime, BA_DOAN[2].start, "nhay doan thi phai dat lai vi tri phat");

    assert.deepEqual(tiengOn, [], "su kien `timeupdate` khong duoc sinh tieng on console");
    unmount();
  });

  it("DOI KENH: vi tri phat ve 0 khi `sourceId` doi — va mount KHONG goi `pause()`", () => {
    // NO cua Task 7 (`M5`): `viTriPhat` la state CUC BO, khong duoc reset khi `sourceId` doi
    // ⇒ dau doc giu vi tri cua kenh CU. Hom do chua voi toi duoc (chua co duong chon kenh);
    // Task W1 lam duong do ton tai, nen no thanh loi THAT.
    const { container, unmount } = render(
      taoPhanTu(ThanhDoiKenh, { segments: BA_DOAN, translationId: 7, duration: 120 }),
    );

    const audio = phanTu(container, "audio") as HTMLAudioElement;
    const dau = phanTu(container, ".tp__readhead") as HTMLElement;
    assert.equal(daGoi.pause, 0, "mount KHONG duoc goi `pause()` (App.test.tsx ghim khong tieng on)");

    audio.currentTime = 64.5;
    fireEvent.timeUpdate(audio);
    assert.equal(chu(container, ".tp__timecode"), "1:04.50 / 2:00.00");
    assert.equal(dau.style.left, "53.75%", "dau doc da chay theo vi tri phat");

    fireEvent.click(phanTu(container, '[data-testid="doi-kenh"]'));

    // DOI KENH ⇒ vi tri phat cua kenh CU phai bi xoa, khong duoc mang sang kenh moi.
    assert.equal(
      chu(container, ".tp__timecode"),
      "0:00.00 / 2:00.00",
      "doi kenh thi vi tri phat phai ve 0 (giu vi tri cu = hien vi tri cua kenh CU)",
    );
    assert.equal(dau.style.left, "0%", "dau doc phai ve dau track");
    // `src` doi theo kenh MOI — chung minh day la mot lan doi kenh THAT, khong phai mot
    // lan render lai vo nghia.
    assert.equal(phanTu(container, "audio").getAttribute("src"), "/api/media/4");
    // Chua tung phat thi doi kenh KHONG duoc sinh them mot co che dung thu hai nao.
    assert.equal(daGoi.pause, 0, "chua phat thi doi kenh khong duoc goi `pause()`");

    assert.deepEqual(tiengOn, [], "doi kenh khong duoc sinh tieng on console");
    unmount();
  });

  it("DAU DOC: vi tri doc chay theo `currentTime`/`duration`; track dung o cuoi khi vuot", () => {
    // ⚠️ `currentSegment: null` la CO Y, va no duoc DO ra tu mot lan do: ban dau bai nay
    // dung `currentSegment: 1` voi `currentTime = 60`, va `left` do duoc la
    // `3.3333333333333335%` chu khong phai `50%` — vi 60 giay VUOT `segment.end` = 4 cua
    // doan 1, nen cu nhay cua `Transport` da dat lai vi tri phat ve `start` = 4 cua doan 2.
    // Tuc CU NHAY dang chay dung; bai nay muon do DAU DOC, nen no tat duong nhay bang
    // `currentSegment: null` (khong phat doan nao thi khong co gi de sang).
    const { container, unmount } = render(
      taoPhanTu(Transport, {
        sourceId: 3,
        segments: BA_DOAN,
        translationId: 7,
        duration: 120,
        currentSegment: null,
      }),
    );

    const dau = phanTu(container, ".tp__readhead") as HTMLElement;
    const audio = phanTu(container, "audio") as HTMLAudioElement;
    assert.equal(dau.style.left, "0%", "chua phat thi dau doc o dau track");

    audio.currentTime = 60;
    fireEvent.timeUpdate(audio);
    assert.equal(dau.style.left, "50%", "60/120 giay ⇒ dau doc o giua track");

    audio.currentTime = 150;
    fireEvent.timeUpdate(audio);
    assert.equal(dau.style.left, "100%", "vuot thoi luong thi dau doc dung o cuoi, khong tran ra ngoai");

    assert.deepEqual(tiengOn, [], "chay dau doc khong duoc sinh tieng on console");
    unmount();
  });

  it("TIMECODE: chuoi `M:SS.hh / M:SS.hh` theo du lieu backend; chua biet thoi luong thi `--:--.--`", () => {
    const mot = render(
      taoPhanTu(Transport, { sourceId: 3, segments: BA_DOAN, translationId: 7, duration: 120 }),
    );
    const audio = phanTu(mot.container, "audio") as HTMLAudioElement;
    assert.equal(chu(mot.container, ".tp__timecode"), "0:00.00 / 2:00.00");
    audio.currentTime = 64.5;
    fireEvent.timeUpdate(audio);
    assert.equal(chu(mot.container, ".tp__timecode"), "1:04.50 / 2:00.00");
    mot.unmount();

    // `Source.duration` la du lieu backend va co the la `null` (URL chua do thoi luong).
    // Hien mot tong so bia ra tu `NaN` la mot loi noi doi — va `formatTimecode` NEM
    // `RangeError` voi gia tri khong huu han.
    const hai = render(
      taoPhanTu(Transport, { sourceId: 3, segments: BA_DOAN, translationId: 7, duration: null }),
    );
    assert.equal(chu(hai.container, ".tp__timecode"), "0:00.00 / --:--.--");
    const dau = phanTu(hai.container, ".tp__readhead") as HTMLElement;
    assert.equal(dau.style.left, "0%", "chua biet thoi luong thi dau doc khong co cho de chay");
    hai.unmount();

    assert.deepEqual(tiengOn, [], "hien timecode khong duoc sinh tieng on console");
  });

  it("GIOI HAN CUA JSDOM (do duoc): `play()` KHONG duoc hien thuc ⇒ tra `undefined` + log `Not implemented`", () => {
    // Bai nay do CHINH jsdom, khong do `Transport`: no la bang chung cho viec tep nay
    // THAY `play`/`pause` bang spy. Neu jsdom hien thuc chung that thi viec thay do la
    // thua — va phep do duoi day se do.
    const w: any = (globalThis as any).window;
    w.HTMLMediaElement.prototype.play = playGoc;
    try {
      const el = w.document.createElement("audio");
      const ketQua = el.play();
      assert.equal(ketQua, undefined, "jsdom tra `undefined` chu KHONG phai Promise");
      assert.ok(
        tiengOn.some((dong) => dong.includes("Not implemented: HTMLMediaElement's play() method")),
        `jsdom phai bao chua hien thuc play(); do duoc: ${JSON.stringify(tiengOn)}`,
      );
    } finally {
      w.HTMLMediaElement.prototype.play = playGia;
    }
  });

  it("NGHE LAI: `play()` bị TỪ CHỐI (autoplay) ⇒ cửa sổ vẫn mở rồi đóng, KHÔNG `unhandledRejection`", async () => {
    // 🔴 TRẦN #7 của báo cáo vòng trước khai *"không dựng được ca `play()` bị từ chối trong jsdom"*
    // — **SAI**: chính TỆP NÀY sở hữu stub `play()` (xem `before`), nên ca từ chối là MỘT DÒNG
    // (`return Promise.reject(...)`), và jsdom KHÔNG cần âm thanh để đo HÀNH VI của nhánh bắt lỗi.
    // Vế được ghim: nhánh `.catch` trong effect nghe lại của `Transport` — bỏ nó đi thì promise bị
    // từ chối thành `unhandledRejection`, mà trên cây TRƯỚC lượt này **0 bài đỏ** (tôi tự đo: bỏ
    // `.catch(() => {})` ⇒ `292/290/2`, đúng hai guard nền `EMPTY_DB_MSG`).
    const w: any = (globalThis as any).window;
    const roi: unknown[] = [];
    const batRoi = (ly: unknown): void => {
      roi.push(ly);
    };
    let soLanGoi = 0;
    process.on("unhandledRejection", batRoi);
    w.HTMLMediaElement.prototype.play = function (): unknown {
      soLanGoi += 1;
      return Promise.reject(new Error("autoplay bị từ chối (NotAllowedError)"));
    };
    try {
      const { container, unmount } = render(
        taoPhanTu(Transport, {
          sourceId: 3,
          segments: BA_DOAN,
          translationId: 7,
          duration: 120,
          ngheLai: { giay: 3.3, lan: 1 },
        }),
      );
      const media = phanTu(container, "audio") as HTMLAudioElement;

      // (1) Cửa sổ MỞ: yêu cầu nghe lại vẫn phải chạy tới cùng — một cú `play()` bị từ chối KHÔNG
      //     được nuốt luôn cửa sổ (người dùng vẫn phải thấy trạng thái đang nghe lại).
      await waitFor(
        () => {
          assert.equal(
            media.getAttribute("data-nghe-lai"),
            "1",
            "yêu cầu nghe lại phải MỞ cửa sổ dù `play()` bị từ chối",
          );
        },
        { timeout: 5000, interval: 20 },
      );
      assert.equal(soLanGoi, 1, "cửa sổ nghe lại phải YÊU CẦU `play()`");
      assert.ok(
        Math.abs(media.currentTime - 3.3) < 1e-9,
        `cửa sổ nghe lại phải TUA tới mốc 3,3; đo được ${media.currentTime}`,
      );

      // (2) Cửa sổ ĐÓNG theo TÍN HIỆU DOM. Đây cũng là khoảng thời gian mà một `unhandledRejection`
      //     (nếu có) PHẢI được phát ra ⇒ khẳng định ở (3) không cần một `sleep` riêng.
      await waitFor(
        () => {
          assert.equal(media.getAttribute("data-nghe-lai"), null, "hết cửa sổ phải ĐÓNG");
        },
        { timeout: 5000, interval: 20 },
      );
      assert.equal(daGoi.pause, 1, "hết cửa sổ (đang không phát) phải `pause()`, không cắt gì khác");

      // (3) VẾ GHIM: từ chối KHÔNG được thành `unhandledRejection`, và không được sinh tiếng ồn.
      assert.deepEqual(roi, [], "`play()` bị từ chối KHÔNG được thành `unhandledRejection`");
      assert.deepEqual(tiengOn, [], "từ chối autoplay không được sinh tiếng ồn console");
      unmount();
    } finally {
      w.HTMLMediaElement.prototype.play = playGia;
      process.off("unhandledRejection", batRoi);
    }
  });

  it("HINH THUC: LUAT CSS cua thanh transport CO THAT trong `app.css`, va moi token deu co dinh nghia", () => {
    // ERRATA #15 muc 3 (do duoc HAI CHIEU o Task 6): mot test chi khang dinh
    // `className` van XANH khi luat CSS bi xoa. Cach re nhat de ghim luat: DOC tep CSS.
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const tokensCss = readFileSync(new URL("../styles/tokens.css", import.meta.url), "utf8");

    const moc = "Thanh TRANSPORT (Task 7)";
    const viTri = appCss.indexOf(moc);
    assert.ok(viTri > 0, "app.css phai co KHOI LUAT cua thanh transport, khong chi co class trong TSX");
    const khoi = appCss.slice(viTri);

    for (const chon of [".tp {", ".tp__phat {", ".tp__timecode {", ".tp__track {", ".tp__readhead {", ".tp__xuat {"]) {
      assert.ok(khoi.includes(chon), `app.css thieu luat "${chon}"`);
    }
    // Luat THAT, khong phai ten lop: ba khai bao quyet dinh hinh dang cua thanh nay.
    assert.match(khoi, /\.tp__timecode \{[^}]*font-family: var\(--font-mono\)/, "timecode phai la COT MONO");
    assert.match(khoi, /\.tp__track \{[^}]*position: relative/, "track phai la moc toa do cho dau doc");
    assert.match(khoi, /\.tp__readhead \{[^}]*background: var\(--signal\)/, "dau doc la den amber");

    // Va TOKEN nao khoi nay dung thi phai co dinh nghia THAT trong `tokens.css` (ERRATA
    // #15 muc 4: mot token khong co nguoi dung la mot tinh nang CHUA TON TAI — va nguoc
    // lai, mot `var(--x)` khong dinh nghia la mot khai bao chet).
    const dung = [...new Set([...khoi.matchAll(/var\((--[a-z0-9-]+)\)/g)].map((m) => m[1] ?? ""))];
    assert.ok(dung.length >= 4, `khoi transport phai dung token that, do duoc ${dung.length}`);
    for (const token of dung) {
      assert.ok(tokensCss.includes(`${token}:`), `token ${token} duoc dung nhung KHONG dinh nghia trong tokens.css`);
    }
  });
});
