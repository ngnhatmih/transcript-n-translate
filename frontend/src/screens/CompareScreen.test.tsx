/**
 * Test `<CompareScreen/>` THAT trong jsdom (spec UI §4.3) — HAI COT + COT CPS,
 * segmented control chon ban dich, GHIM ban B, va danh dau dong VUOT NGUONG DOC.
 *
 * Vi sao jsdom: jsdom KHONG cho bang chung HINH THUC — no KHONG co layout, KHONG co CSS that.
 * ⇒ Tep nay do duoc HANH VI (cai gi nam trong DOM, lop nao, chu nao, con so nao), KHONG do
 * duoc HINH (cot rong bao nhieu, duong ke 1px co hien ra khong, dau amber co nhin thay khong).
 *
 * ⚠️ DINH CHINH (Task 12, ERRATA #40 + #46 muc 5): cau cu o day noi *"trinh duyet THAT BAT KHA
 * o moi truong nay (Chromium chet o Mojo named pipe)"* — **SAI vi QUA RONG**. Menh de dung la:
 * *"Chromium khong mo duoc DƯỚI CÁC CHẾ ĐỘ SANDBOX HẠN CHẾ"*. ⇒ **Bang chung HINH THUC nam o
 * tang Chrome that: `frontend/e2e/`** (`e2e/plans/bon-man.json` do cot CPS + so dong ⚠).
 * ⚠️ Tang do CHUA duoc chay trong luot Task 12 (xem bao cao).
 *
 * LUAT DOM (ERRATA #9 muc 1/6) — tep nay TU CHUA va khong dua vao thu tu:
 *   - MOI hook dat/tra global nam TRONG `describe()`: duoi `--test-isolation=none`, hook
 *     cap TEP bi node:test keo len GOC ca luot (moi `before` truoc MOI bai, moi `after`
 *     sau moi bai) — do bang dong ho chung, khong phai suy dien.
 *   - `setupDom`/`teardownDom` cua CHINH tep nay; khong gia dinh jsdom cua tep khac con
 *     song, va khong de lai global nao cho tep sau.
 *   - `console.error`/`console.warn` bi TAM THAY de bat tieng on va duoc TRA LAI trong
 *     `after` (chung cung la global: ERRATA #7 muc 3).
 *   - LUON chay TOAN BO `npm test`, khong chay le tep: suy giam do nhiem cheo chi lo ra
 *     o luot day du.
 *
 * ⚠️ KHONG co `@testing-library/user-event` va KHONG co `jest-dom` trong repo (do
 * `package.json`: chi `jsdom` + `@testing-library/react`) ⇒ dung `fireEvent` xuat tu
 * `@testing-library/react` va `node:assert/strict`. `toHaveAttribute`/`toHaveTextContent`/
 * `toBeInTheDocument` KHONG ton tai o day.
 *
 * ⚠️ `npm run typecheck` KHONG kiem tep `.test.tsx` (`tsc --listFiles` khong co tep
 * `.test.` nao — ERRATA #10 muc 8/ERRATA #12 muc 3) ⇒ loi kieu trong tep nay CHI lo ra
 * luc chay, va `npm test` cua luot day du VON DA `EXIT=1` (hai bai `EMPTY_DB_MSG` do
 * chu y) nen EXIT KHONG phai kenh thong tin (ERRATA #11 muc 1).
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import type { EngineSpec, Segment, Transcript, TranslationDetail } from "../api/types.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

/**
 * Mot spec theo DUNG hinh dang `EngineSpec`. `available` CHI duoc ghi khi duoc truyen:
 * `_mark_availability` cua backend chi ghi khoa do cho `kind == "mt"` ⇒ ASR **THIEU** khoa
 * (ERRATA #2 muc 3), va "thieu khoa" KHONG phai la "dung duoc".
 */
function spec(
  id: string,
  label: string,
  available?: boolean,
  kind: "asr" | "mt" = "mt",
): EngineSpec {
  const capabilities: EngineSpec["capabilities"] = {};
  if (available !== undefined) capabilities.available = available;
  return {
    id,
    label,
    kind,
    runtime: "inprocess",
    model_ref: `model/${id}`,
    vram_mb: 0,
    langs: ["zh"],
    capabilities,
    opts: {},
  };
}

/** Ba spec theo DUNG hinh dang registry that: ASR (thieu `available`) + MT duoc + MT khong. */
const SPECS: EngineSpec[] = [
  spec("faster-whisper-large", "Faster Whisper Large", undefined, "asr"),
  spec("opus-mt", "OPUS-MT", true),
  spec("qwen2.5-3b", "Qwen 2.5 3B", false),
];

/**
 * FIXTURE MAU THUAN cho luat "chi `kind === "mt"`" — va no la thu DUY NHAT phan biet duoc
 * hai cach loc.
 *
 * ⚠️ VI SAO BAT BUOC (do duoc o luot mutation `W3-3`): `SPECS` o tren co ASR **THIEU** khoa
 * `available`, nen `EngineSelect` (loc `available === true`, luat Task 10) da loai no SAN —
 * bo luat `kind === "mt"` di thi ket qua Y HET, va mutant **SONG SOT 0 bai do**. Mot fixture
 * trong do hai luat TRUNG ket qua khong phan biet duoc gi (ERRATA #31 muc 3: fixture phai
 * dung hinh dang phan biet duoc).
 *
 * Hinh dang nay KHONG phai hinh dang backend sinh ra hôm nay (`_mark_availability` chi ghi
 * `available` cho `kind == "mt"`), nen no la mot MAU THUAN CO CHU Y: no ghim rang buoc
 * **`kind`**, chu khong ghim mot su trung hop cua du lieu hien tai.
 */
const SPECS_ASR_DUOC: EngineSpec[] = [
  spec("faster-whisper-large", "Faster Whisper Large", true, "asr"),
  spec("opus-mt", "OPUS-MT", true),
];

/** Mot doan theo dung 5 khoa LUON co cua `Segment` (`types.ts`). */
function doan(i: number, text: string, start = i, end = i + 2, suspect = false): Segment {
  return { i, start, end, text, suspect };
}

function banGhi(segments: Segment[]): Transcript {
  return {
    id: 1,
    source_id: 1,
    engine: "senseware",
    lang: "zh",
    version: 2,
    status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    translations: [],
    segments,
  };
}

/**
 * Mot ban dich CHI TIET: tom tat (9 khoa cua `Translation`) + `segments` + `cps`.
 *
 * `cps` o day la du lieu BACKEND: `over` la co DA TINH SAN, `cps` la SO. Bai test
 * khong bao gio tu suy `over` tu `cps`/`text` — lam the thi chinh bai test cung dang
 * vi pham quy tac ma no ton tai de ghim.
 */
function banDich(
  id: number,
  texts: string[],
  cps: { i: number; cps: number | null; over: boolean }[],
  opts: { stale?: boolean; maxCps?: number; engine?: string; status?: TranslationDetail["status"] } = {},
): TranslationDetail {
  return {
    id,
    transcript_id: 1,
    engine: opts.engine ?? "opus-mt",
    target_lang: "vi",
    prompt_version: "raw-p1",
    transcript_version: 1,
    status: opts.status ?? "done",
    stale: opts.stale ?? false,
    created_at: "2026-01-01T00:00:00Z",
    segments: texts.map((t, k) => doan(k + 1, t)),
    cps: {
      max_cps: opts.maxCps ?? 21,
      rows: cps.map((r) => ({
        i: r.i,
        chars: 10,
        window: 1,
        cps: r.cps,
        max_cps: opts.maxCps ?? 21,
        over: r.over,
      })),
    },
  };
}

const consoleGoc = { error: console.error, warn: console.warn };
const tiengOn: string[] = [];

let render: (ui: unknown) => { container: HTMLElement; unmount: () => void };
let fireEvent: { click: (el: Element) => void; change: (el: Element, init: unknown) => void };
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let CompareScreen: (props: unknown) => unknown;
let getByRole: (container: HTMLElement, role: string, options?: { name?: RegExp | string }) => Element;

/** `textContent` cua phan tu DAU TIEN khop `chon` — khong hoi ca DOM. */
function chu(goc: HTMLElement, chon: string): string {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.textContent ?? "";
}

/** Thuoc tinh cua phan tu DAU TIEN khop `chon` (`null` neu khong co). */
function thuocTinh(goc: HTMLElement, chon: string, ten: string): string | null {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.getAttribute(ten);
}

/**
 * Khang dinh KHONG co phan tu nao khop `chon` — DEM, khong so sanh NODE.
 *
 * ⚠️ DO DUOC (ERRATA #14 muc 3 / #15 muc 1, 218 697 ms roi OOM): `assert.equal(<node DOM
 * song>, null)` o nhanh DO khien `assert` dinh dang CA cay fiber trong thong diep loi.
 * ⇒ moi khang dinh "khong co phan tu" o tep nay dem SO LUONG (mot con so).
 */
function khongCo(goc: HTMLElement, chon: string, msg: string): void {
  assert.equal(goc.querySelectorAll(chon).length, 0, msg);
}

/**
 * Phan tu DAU TIEN khop `chon` — tra ve NODE de doc `disabled`/`value`/bam.
 *
 * ⚠️ Khong bao gio dua node nay vao `assert` (ERRATA #14 muc 3: 218 697 ms roi OOM);
 * moi khang dinh la BOOLEAN hoac tren `getAttribute`/`textContent`.
 */
function phanTuTu(goc: HTMLElement, chon: string): Element {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el;
}

describe("CompareScreen: §4.3 hai cot + cot CPS + segmented control + ghim ban B", () => {
  before(async () => {
    // Chuan hoa TRUOC khi cai: khong dua vao viec tep khac da tra global hay chua.
    teardownDom();
    // Origin chi de `fetch` tuong doi resolve duoc; tep nay KHONG goi mang nao
    // (man hinh nhan du lieu qua PROP — cung khuon voi Task 6/7).
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    getByRole = api.getByRole;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const man: any = await import("./CompareScreen.tsx");
    CompareScreen = man.CompareScreen;

    console.error = (...args: unknown[]): void => {
      tiengOn.push(`error: ${args.map((a) => String(a)).join(" ")}`);
    };
    console.warn = (...args: unknown[]): void => {
      tiengOn.push(`warn: ${args.map((a) => String(a)).join(" ")}`);
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

  // -------------------------------------------------------------------------
  // Cot CPS — du lieu BACKEND, khong phai mau don thuan (spec UI §12.4)
  // -------------------------------------------------------------------------

  it("danh dau dong VUOT NGUONG bang COT CPS co SO, khong phai bang mau don thuan", () => {
    const t = banGhi([doan(1, "你好"), doan(3, "今天我们要聊的是人工智能")]);
    const tr = banDich(7, ["Xin chao", "Hom nay chung ta se noi ve tri tue nhan tao"],
      [{ i: 1, cps: 8, over: false }, { i: 3, cps: 45.2, over: true }]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [tr] }));

    // Khang dinh tren THUOC TINH + CHU, khong tren node: `data-over-cps` la thu
    // khien nguoi dung "phat hien duoc dong vuot nguong ma khong phai tu dem".
    assert.equal(thuocTinh(container, '[data-testid="row-3"]', "data-over-cps"), "true",
      "dong 3 = 45,2 CPS > nguong 21 phai duoc danh dau");
    assert.equal(thuocTinh(container, '[data-testid="row-1"]', "data-over-cps"), "false",
      "dong 1 = 8 CPS khong vuot nguong thi khong duoc danh dau");

    // Cot CPS phai co CON SO va DON VI, khong chi mot vet mau.
    const oCps = chu(container, '[data-testid="row-3"] [data-testid="col-cps"]');
    assert.match(oCps, /45[.,]2/, `o CPS phai hien con so cua backend, dang co: ${oCps}`);
    assert.match(oCps, /CPS/i, `o CPS phai noi ro don vi, dang co: ${oCps}`);

    // Nguong hien ra phai la nguong CUA BACKEND, khong phai mot so trong ma client.
    assert.match(chu(container, '[data-testid="nguong"]'), /21/,
      "nguong CPS hien tren UI phai den tu backend");
    assert.deepEqual(tiengOn, [], "render khong duoc sinh tieng on console");
  });

  it("CPS hien DUNG CON SO cua backend, khong tinh lai o client", () => {
    // Bay ro rang: van ban 10 ky tu / cua so 1,0s ⇒ mot client tu tinh se ra 10,0 va
    // ket luan "khong vuot". Backend noi 42,0 va `over: true`. Hien gi la bai nay do.
    const t = banGhi([doan(1, "你好")]);
    const tr = banDich(7, ["abcdefghij"], [{ i: 1, cps: 42, over: true }]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [tr] }));

    const oCps = chu(container, '[data-testid="row-1"] [data-testid="col-cps"]');
    assert.match(oCps, /42/, `phai hien 42 (so cua backend), dang co: ${oCps}`);
    assert.doesNotMatch(oCps, /\b10\b/, "10 la con so mot client TU TINH se ra — khong duoc hien");
    assert.equal(thuocTinh(container, '[data-testid="row-1"]', "data-over-cps"), "true",
      "co `over` phai lay TU BACKEND, khong duoc tu so `cps > max_cps`");
  });

  it("doan KHONG DO DUOC CPS hien trung thuc, khong hien 0 va khong hien Infinity", () => {
    // Backend tra `cps: null` khi ca hai cua so deu khong duong (`mt_qa` goi la
    // `nowindow`). Hien `0` o day la BIA mot toc do; hien `Infinity` la ro ri loi
    // serialize ra giao dien.
    const t = banGhi([doan(1, "你好")]);
    const tr = banDich(7, ["Xin chao"], [{ i: 1, cps: null, over: false }]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [tr] }));

    const oCps = chu(container, '[data-testid="row-1"] [data-testid="col-cps"]');
    assert.doesNotMatch(oCps, /Infinity|NaN/, `khong duoc ro ri so khong serialize duoc: ${oCps}`);
    assert.doesNotMatch(oCps, /\b0\b/, `khong do duoc KHONG phai la 0: ${oCps}`);
    assert.equal(thuocTinh(container, '[data-testid="row-1"]', "data-over-cps"), "false",
      "khong do duoc khong phai la vuot nguong");
  });

  it("co `over` cua backend thang phep so cua client o dung bien", () => {
    // Lo hong do duoc (ERRATA #11 muc 2): mutation "client tu so `cps > max_cps`"
    // SONG SOT tren bo test truoc khi co bai nay (`pass 114 / fail 2` — y het luot
    // sach, tuc phep do cu MU). Ly do: moi ca cu deu co `cps` cach xa nguong, nen
    // tu so hay doc co deu ra cung mot ket qua.
    //
    // Ca o DAY nam DUNG bien: 21,04 CPS lam tron de hien thi la 21,0 — BANG nguong.
    // Client tu so se noi "khong vuot"; backend da so tren gia tri CHUA lam tron va
    // noi `over: true`.
    const t = banGhi([doan(1, "你好")]);
    const tr = banDich(7, ["Viet dai"], [{ i: 1, cps: 21, over: true }], { maxCps: 21 });

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [tr] }));

    assert.match(chu(container, '[data-testid="row-1"] [data-testid="col-cps"]'), /21[.,]0/,
      "so HIEN THI la 21,0 — bang nguong, nen no khong tu phan biet duoc gi");
    assert.equal(thuocTinh(container, '[data-testid="row-1"]', "data-over-cps"), "true",
      "co `over` phai lay TU BACKEND: tu so `cps > max_cps` o dung bien nay se noi SAI");
  });

  it("HINH THUC: dong VUOT NGUONG co glyph `⚠` (spec UI §4.3), dong khong vuot thi KHONG", () => {
    // ERRATA #19 muc 7 (RULING cua nguoi dieu phoi): spec UI §4.3 nguyen van — "Dong vuot
    // nguong doc co `⚠` mau amber."; `grep -i emoji` tren SPEC = 0 ⇒ spec KHONG cam emoji,
    // lenh cam nam o PLAN va plan tu mau thuan. Spec UI la nguon co tham quyen ve HINH THUC
    // ⇒ glyph PHAI render. Luat "khong emoji" VAN hieu luc cho moi thu KHAC.
    //
    // Khang dinh tren `textContent`, KHONG tren node DOM song: `assert.equal(<node>, null)` o
    // nhanh DO do duoc 218 697 ms roi OOM (ERRATA #14 muc 3 / #15 muc 1).
    const t = banGhi([doan(1, "你好"), doan(3, "今天我们要聊的是人工智能")]);
    const tr = banDich(7, ["Xin chao", "Hom nay chung ta se noi ve tri tue nhan tao"],
      [{ i: 1, cps: 8, over: false }, { i: 3, cps: 45.2, over: true }]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [tr] }));

    const vuot = chu(container, '[data-testid="row-3"] [data-testid="col-cps"]');
    const khongVuot = chu(container, '[data-testid="row-1"] [data-testid="col-cps"]');
    assert.match(vuot, /⚠/, `dong VUOT nguong phai co glyph canh bao, dang co: ${vuot}`);
    assert.doesNotMatch(khongVuot, /⚠/,
      `dong KHONG vuot nguong khong duoc co glyph — mot glyph luon hien la mat tin hieu: ${khongVuot}`);
    // Moc amber o le + `data-over-cps` phai CON (chung phuc vu TIEP CAN §7, khong bi glyph thay).
    assert.equal(thuocTinh(container, '[data-testid="row-3"]', "data-over-cps"), "true");
    assert.equal(thuocTinh(container, '[data-testid="row-1"]', "data-over-cps"), "false");
  });

  // -------------------------------------------------------------------------
  // Segmented control + GHIM ban B
  // -------------------------------------------------------------------------

  it("chon ban dich khac thi cot PHAI doi theo, cot TRAI khong doi", () => {
    const t = banGhi([doan(1, "你好"), doan(2, "谢谢")]);
    const a = banDich(7, ["Xin chao", "Cam on"], [{ i: 1, cps: 8, over: false }, { i: 2, cps: 4, over: false }]);
    const b = banDich(9, ["Chao ban", "Da ta"], [{ i: 1, cps: 9, over: false }, { i: 2, cps: 5, over: false }]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [a, b] }));

    // Mac dinh: ban dich DAU tien.
    assert.match(chu(container, '[data-testid="row-1"] [data-testid="col-right"]'), /Xin chao/);
    assert.match(chu(container, '[data-testid="row-1"] [data-testid="col-left"]'), /你好/);

    fireEvent.click(container.querySelector('[data-testid="pick-9"]') as Element);

    assert.match(chu(container, '[data-testid="row-1"] [data-testid="col-right"]'), /Chao ban/,
      "chon ban dich khac thi cot phai phai doi");
    assert.match(chu(container, '[data-testid="row-1"] [data-testid="col-left"]'), /你好/,
      "cot TRAI la ban GOC: no KHONG duoc doi theo ban dich duoc chon");
    assert.doesNotMatch(chu(container, '[data-testid="row-1"] [data-testid="col-left"]'), /Chao ban/);
  });

  it("GHIM ban B thi hien them cot so sanh, va bo ghim thi cot do bien mat", () => {
    const t = banGhi([doan(1, "你好")]);
    const a = banDich(7, ["Xin chao"], [{ i: 1, cps: 8, over: false }]);
    const b = banDich(9, ["Chao ban"], [{ i: 1, cps: 9, over: false }]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [a, b] }));

    khongCo(container, '[data-testid="col-pinned"]', "chua ghim thi khong duoc co cot so sanh");

    fireEvent.click(container.querySelector('[data-testid="ghim"]') as Element);

    // Ban dich DANG CHON la `a`, nen "ban B" duoc ghim la ban CON LAI (`b`).
    assert.match(chu(container, '[data-testid="col-pinned"]'), /Chao ban/,
      "ghim ban B phai hien cot so sanh voi ban dich CON LAI");
    assert.match(chu(container, '[data-testid="row-1"] [data-testid="col-right"]'), /Xin chao/,
      "ghim khong duoc lam doi ban dich dang chon");

    fireEvent.click(container.querySelector('[data-testid="ghim"]') as Element);
    khongCo(container, '[data-testid="col-pinned"]', "bo ghim thi cot so sanh phai bien mat");
  });

  it("GHIM: DAU COT cung nhan `is-pinned` — luat luoi bon cot khong tu ap cho dau cot", () => {
    // LO HONG DO PHU DO DUOC (ERRATA #19 muc 6, M4): bo `is-pinned` o HANG DAU COT thi bo
    // test CU (`117/115/2`) SONG SOT — do lai y het luot sach. Ly do: bai `HINH THUC` chi
    // DOC LUAT CSS trong `app.css`, no KHONG do xem DAU COT co that su nhan lop do khong,
    // nen mot dau cot ba cot nam tren than bon cot di qua XANH.
    const t = banGhi([doan(1, "你好")]);
    const a = banDich(7, ["Xin chao"], [{ i: 1, cps: 8, over: false }]);
    const b = banDich(9, ["Chao ban"], [{ i: 1, cps: 9, over: false }]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [a, b] }));

    // Dem/lay LOP cua phan tu, khong so sanh NODE (ERRATA #14 muc 3 / #15 muc 1).
    const dauCotCoLop = (): boolean => {
      const dau = container.querySelector(".cmp__dau") as HTMLElement | null;
      assert.ok(dau !== null, "phai co dau cot `.cmp__dau`");
      return dau.classList.contains("is-pinned");
    };

    assert.equal(dauCotCoLop(), false, "chua ghim thi DAU COT khong duoc co `is-pinned`");
    fireEvent.click(container.querySelector('[data-testid="ghim"]') as Element);
    assert.equal(dauCotCoLop(), true,
      "ghim roi thi DAU COT phai nhan `is-pinned` — khong thi dau cot lech mot cot so voi than");
    fireEvent.click(container.querySelector('[data-testid="ghim"]') as Element);
    assert.equal(dauCotCoLop(), false, "bo ghim thi dau cot phai bo lop theo");

    // Va lop do phai co LUAT THAT ap cho DAU COT: neu `app.css` chi mo cot thu tu cho
    // `.cmp__dong` thi dau cot van lech, du lop co tren phan tu (ERRATA #15 muc 3).
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    assert.match(appCss, /\.cmp__dau\.is-pinned[^{}]*\{[^}]*grid-template-columns:/,
      "app.css phai mo COT THU TU cho `.cmp__dau.is-pinned`, khong chi cho `.cmp__dong.is-pinned`");
  });

  it("chi co MOT ban dich thi nut GHIM khong moi ghim mot ban khong ton tai", () => {
    const t = banGhi([doan(1, "你好")]);
    const a = banDich(7, ["Xin chao"], [{ i: 1, cps: 8, over: false }]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [a] }));

    const nut = container.querySelector('[data-testid="ghim"]') as HTMLButtonElement;
    assert.ok(nut !== null, "nut ghim phai ton tai de noi that la chua ghim duoc");
    assert.equal(nut.disabled, true, "khong co ban B nao thi nut ghim phai VO HIEU, khong im lang");
  });

  it("ban dich loi thoi duoc danh dau — co `stale` cung den tu backend", () => {
    const t = banGhi([doan(1, "你好")]);
    const cu = banDich(7, ["Xin chao"], [{ i: 1, cps: 8, over: false }], { stale: true });
    const moi = banDich(9, ["Chao ban"], [{ i: 1, cps: 8, over: false }]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [cu, moi] }));

    assert.equal(thuocTinh(container, '[data-testid="pick-7"]', "data-stale"), "true");
    assert.equal(thuocTinh(container, '[data-testid="pick-9"]', "data-stale"), "false");
  });

  // -------------------------------------------------------------------------
  // Trang thai RONG noi THAT (ERRATA #14 muc 5 / #17 muc 3)
  // -------------------------------------------------------------------------

  it("RONG: chua chon kenh thi noi that, khong bia mot ban ghi nao", () => {
    // ⚠️ CHU THICH CU SUA O VONG THIET KE 1: ban cu viet *"`App` chua co duong CHON KENH
    // (ERRATA #18 muc 4)"* — dieu do KHONG con dung sau W1 (`ChannelZone` da noi `selectChannel`
    // vao tung muc kenh). Trang thai `transcript === null` nay KHONG phai "khong co duong", ma la
    // "nguoi dung CHUA chon" — dung cai ma cau chu cua `CompareScreen` da noi SAI (va da sua).
    const { container } = render(taoPhanTu(CompareScreen, { transcript: null, translations: [] }));

    const chuRong = chu(container, '[data-testid="rong"]');
    assert.match(chuRong, /.+/, "trang thai rong phai NOI mot dieu gi do, khong duoc im lang");
    khongCo(container, '[data-testid^="row-"]', "khong co du lieu thi khong duoc render dong nao");
    assert.deepEqual(tiengOn, [], "trang thai rong khong duoc sinh tieng on console");
  });

  it("RONG: co ban ghi nhung CHUA co ban dich thi van hien cot goc va noi ro", () => {
    const t = banGhi([doan(1, "你好"), doan(2, "谢谢")]);

    const { container } = render(taoPhanTu(CompareScreen, { transcript: t, translations: [] }));

    assert.match(chu(container, '[data-testid="row-1"] [data-testid="col-left"]'), /你好/,
      "cot GOC la du lieu that, phai hien du khong co ban dich nao");
    assert.equal(chu(container, '[data-testid="row-1"] [data-testid="col-right"]'), "",
      "chua co ban dich thi cot phai de TRONG, khong duoc dien mot chu nao");
    assert.match(chu(container, '[data-testid="chua-dich"]'), /.+/, "phai noi ro la chua co ban dich");
    khongCo(container, '[data-testid="nguong"]', "khong co ban dich thi khong co nguong nao de noi");
  });

  // -------------------------------------------------------------------------
  // TASK W3 — CUA VAO "BAT DAU DICH" (spec UI §4.3)
  //
  // Do duoc TRUOC W3: `endpoints.createTranslation` **0 luot goi trong san pham**,
  // `endpoints.listEngines` **0**, va `<EngineSelect/>` **0 nguoi goi** ⇒ KHONG co cach nao
  // BAT DAU mot ban dich tu giao dien. Bon bai duoi day ghim CUA DO.
  // -------------------------------------------------------------------------

  it("CUA DICH: chua co ban dich nao thi CUA vao PHAI hien (trang thai rong co CO, khong phai cau 'chua co gi')", () => {
    const t = banGhi([doan(1, "你好")]);
    const goi: string[] = [];

    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: t,
      translations: [],
      specs: SPECS,
      onTaoBanDich: (engine: string) => goi.push(engine),
    }));

    assert.ok((container.textContent ?? "").includes("chưa có bản dịch"),
      "man phai noi that la chua co ban dich nao");

    // o chon engine: CHI engine `kind === "mt"` VA `available === true` (loc nam o
    // `EngineSelect`, Task 10 — W3 la NGUOI GOI DAU TIEN cua no).
    const o = phanTuTu(container, "select");
    assert.equal(o.getAttribute("disabled"), null,
      "co engine dich dung duoc thi o chon KHONG duoc vo hieu");
    assert.equal((o as HTMLSelectElement).value, "opus-mt", "engine MT dung duoc dau tien phai duoc chon san");

    const loai = [...container.querySelectorAll("option")].map((x) => x.textContent ?? "");
    assert.deepEqual(loai, ["OPUS-MT"],
      `CHI engine kind==="mt" VA available===true duoc liet ke; do duoc ${JSON.stringify(loai)}`);
    assert.ok(!loai.includes("Faster Whisper Large"),
      "KHONG duoc truyen ASR xuong o chon engine dich: backend tra 422 (routes_translations.py:120)");

    // Nut "dich" phai CO THAT, bam duoc, va phat ra engine DANG CHON.
    const nut = phanTuTu(container, '[data-testid="tao-ban-dich"]') as HTMLButtonElement;
    assert.equal(nut.disabled, false, "co engine MT dung duoc thi nut 'dich' phai bam duoc");
    fireEvent.click(nut);
    assert.deepEqual(goi, ["opus-mt"], "bam 'dich' phai phat ra id engine DANG CHON");

    assert.deepEqual(tiengOn, [], "trang thai rong co cua vao khong duoc sinh tieng on console");
  });

  it("CUA DICH: DA co ban dich thi cua vao VAN hien (loi gon '+ bản dịch mới')", () => {
    const t = banGhi([doan(1, "你好")]);
    const a = banDich(7, ["Xin chao"], [{ i: 1, cps: 8, over: false }]);

    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: t,
      translations: [a],
      specs: SPECS,
      onTaoBanDich: () => {},
    }));

    const nut = phanTuTu(container, '[data-testid="tao-ban-dich"]') as HTMLButtonElement;
    assert.equal(nut.disabled, false, "co engine MT dung duoc thi cua vao van bam duoc");
    assert.match(nut.textContent ?? "", /bản dịch mới/,
      "da co ban dich thi cua vao la LOI GON '+ ban dich moi', khong bien mat");

    assert.deepEqual(tiengOn, [], "render lai cua vao khong duoc sinh tieng on console");
  });

  it("CUA DICH: KHONG co engine MT nao dung duoc ⇒ nut VO HIEU + noi RO vi sao va cach sua", () => {    const t = banGhi([doan(1, "你好")]);

    // Bon hinh dang deu la "khong co engine dich dung duoc": thieu han `specs`, mang rong,
    // MT `available === false`, va chi co ASR (thieu khoa `available` — ERRATA #2 muc 3).
    for (const specs of [
      undefined,
      [],
      [spec("qwen2.5-3b", "Qwen 2.5 3B", false)],
      [spec("faster-whisper-large", "Faster Whisper Large", undefined, "asr")],
    ] as (EngineSpec[] | undefined)[]) {
      const goi: string[] = [];
      const { container } = render(taoPhanTu(CompareScreen, {
        transcript: t,
        translations: [],
        specs,
        onTaoBanDich: (engine: string) => goi.push(engine),
      }));

      const nut = phanTuTu(container, '[data-testid="tao-ban-dich"]') as HTMLButtonElement;
      assert.equal(nut.disabled, true,
        `khong co engine MT dung duoc thi nut 'dich' phai VO HIEU; specs=${JSON.stringify(specs)}`);
      // ⚠️ ERRATA #30 / bai hoc §4.8: doi mau la KHONG DU — phai noi RO VI SAO va CACH SUA.
      const ly = chu(container, '[data-testid="ly-do-khong-dich"]');
      assert.match(ly, /không có engine dịch nào dùng được/i,
        `phai noi RO vi sao nut vo hieu; do duoc ${JSON.stringify(ly)}`);
      assert.match(ly, /(ollama|pull|model)/i,
        `phai noi RO CACH SUA (khong chi doi mau); do duoc ${JSON.stringify(ly)}`);

      fireEvent.click(nut);
      assert.deepEqual(goi, [], "nut VO HIEU thi bam KHONG duoc phat ra loi goi nao");
    }

    assert.deepEqual(tiengOn, [], "nhanh 'khong co engine' khong duoc sinh tieng on console");
  });

  it("BAN DICH `queued`: cot PHAI khong duoc RONG — phai noi ra 'dang dich…' kem trang thai job", () => {
    // ⚠️ W3-6: ban dich VUA TAO la `queued` va CHUA co doan nao. Neu man de cot phai rong thi
    // nguoi dung bam "dich" va khong thay gi xay ra ⇒ tuong app hong (brief §5).
    // ⚠️ Khong bia % tien do: tien do THAT nam o vung HANG DOI (`useJobStream`), khong o day.
    const t = banGhi([doan(1, "你好"), doan(2, "谢谢")]);
    const moi = banDich(13, [], [], { status: "queued" });

    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: t,
      translations: [moi],
      specs: SPECS,
      onTaoBanDich: () => {},
      trangThaiJob: "queued",
    }));

    for (const i of [1, 2]) {
      const phai = chu(container, `[data-testid="row-${i}"] [data-testid="col-right"]`);
      assert.match(phai, /đang dịch/,
        `ban dich queued thi cot phai PHai noi ra trang thai; dong ${i} do duoc ${JSON.stringify(phai)}`);
      assert.match(phai, /job/,
        `phai kem trang thai JOB (that), khong chi mot chu chung; dong ${i} do duoc ${JSON.stringify(phai)}`);
      assert.match(chu(container, `[data-testid="row-${i}"] [data-testid="col-left"]`), /你好|谢谢/,
        "cot TRAI van la du lieu GOC that — khong bi trang thai cua ban dich thay the");
    }
    assert.equal(container.querySelectorAll('[data-testid="col-right"]').length, 2,
      "moi dong van phai co o cot phai — khong duoc bo o di");

    assert.deepEqual(tiengOn, [], "trang thai queued khong duoc sinh canh bao console");
  });

  it("CUA DICH: luat `kind === \"mt\"` LA MOT rang buoc THAT, khong phai su trung hop cua du lieu", () => {
    // ⚠️ MUTANT `W3-3` (bo `kind === "mt"`) **SONG SOT** tren fixture `SPECS` vi ASR o do
    // THIEU khoa `available` ⇒ `EngineSelect` loai no SAN, va bo luat `kind` di thi ket qua
    // Y HET. Bai nay dung fixture MAU THUAN (`SPECS_ASR_DUOC`): mot ASR **co**
    // `available: true` — khi do chi `kind` moi loai duoc no.
    const t = banGhi([doan(1, "你好")]);
    const goi: string[] = [];

    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: t,
      translations: [],
      specs: SPECS_ASR_DUOC,
      onTaoBanDich: (engine: string) => goi.push(engine),
    }));

    const loai = [...container.querySelectorAll("option")].map((x) => x.textContent ?? "");
    assert.deepEqual(loai, ["OPUS-MT"],
      `ASR co \`available: true\` VAN khong duoc liet ke: luat la \`kind === "mt"\`, va backend tra 422 cho ASR (routes_translations.py); do duoc ${JSON.stringify(loai)}`);

    // ...va engine GUI DI cung phai la MT: bam nut phai phat ra `opus-mt`, khong bao gio ASR.
    fireEvent.click(phanTuTu(container, '[data-testid="tao-ban-dich"]'));
    assert.deepEqual(goi, ["opus-mt"],
      `client KHONG duoc gui mot id ASR (backend tra 422); do duoc ${JSON.stringify(goi)}`);

    assert.deepEqual(tiengOn, [], "loc engine khong duoc sinh canh bao console");
  });

  it("BAN DICH `queued` co vai doan DA DICH: doan chua dich moi noi trang thai (khong nuot chu that)", () => {
    const t = banGhi([doan(1, "你好"), doan(2, "谢谢")]);
    const dangChay = banDich(13, ["Xin chao"], [{ i: 1, cps: 4, over: false }], { status: "running" });

    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: t,
      translations: [dangChay],
      specs: SPECS,
      onTaoBanDich: () => {},
      trangThaiJob: "running",
    }));

    assert.match(chu(container, '[data-testid="row-1"] [data-testid="col-right"]'), /Xin chao/,
      "doan DA dich phai hien CHU THAT, khong bi trang thai de len");
    assert.match(chu(container, '[data-testid="row-2"] [data-testid="col-right"]'), /đang dịch/,
      "doan CHUA dich phai noi ra trang thai, khong de rong");

    assert.deepEqual(tiengOn, [], "ban dich dang chay khong duoc sinh tieng on console");
  });

  // -------------------------------------------------------------------------
  // HINH THUC: ghim LUAT CSS, khong chi ghim ten lop (ERRATA #15 muc 3)
  // -------------------------------------------------------------------------

  it("HINH THUC (W3): nut 'dich' vo hieu phai co LUAT `[disabled]` THAT, va o chon bi khoa theo LUAT `:disabled`", () => {
    // 🔴 ERRATA #15 muc 3 + ERRATA #34 muc 2: task W3 THEM HINH THUC MOI ⇒ phai co bai ghim
    // **LUAT** trong `app.css`, khong chi `className`/`disabled` trong DOM. Task 10 de lai mot
    // TRAN dung loai nay (`EngineSelect` chi duoc ghim bang `className`) — khong lap lai.
    //
    // ⚠️ VA GHIM **QUAN HE** (ERRATA #34 muc 1): khong chi "co khai bao X", ma "khi KHONG co
    // engine MT dung duoc thi NUT `.cmp__nut-dich` va O CHON `.eng__chon` deu bi vo hieu —
    // va CAI BI VO HIEU do co LUAT trong `app.css`". Bai nay doc CHINH VAN BAN CSS + doc
    // trang thai THAT trong DOM, nen no DO neu thieu mot trong hai ve.
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");

    // (a) LUAT THAT: nut vo hieu phai co luat `:disabled` — xoa luat ma giu class ⇒ bai DO.
    assert.match(appCss, /\.cmp__nut-dich:disabled \{[^}]*color: var\(--ink-2\)/,
      "`.cmp__nut-dich:disabled` phai co LUAT THAT trong app.css (khong chi thuoc tinh `disabled` trong DOM)");
    assert.match(appCss, /\.cmp__nut-dich \{[^}]*cursor: pointer/,
      "`.cmp__nut-dich` phai la mot NUT bam duoc (co luat `cursor: pointer`), khong phai mot nhan");

    // (b) HAI CHIEU cua cung mot ve: khong chi KHONG CHON (`:disabled`) phai co luat, ma luat
    //     do phai doi CA CON TRO — mot thay doi `cursor: pointer` ⇒ `cursor: default` cung
    //     phai lam bai nay DO, neu khong bai chi khang dinh "co mot khoi ten nhu the".
    assert.match(appCss, /\.cmp__nut-dich:disabled \{[^}]*cursor: default/,
      "nut vo hieu phai doi CA CON TRO (`cursor: default`), khong chi doi mau chu");

    // (c) o chon engine bi khoa: LUAT `:disabled` cua `.eng__chon` phai CON (Task 10 ghim no).
    assert.match(appCss, /\.eng__chon:disabled \{[^}]*background: var\(--panel-1\)/,
      "`.eng__chon:disabled` phai co LUAT THAT: o chon bi khoa phai doi BE MAT, khong chi doi thuoc tinh");

    // (d) QUAN HE: dung luc KHONG co engine MT dung duoc thi ca hai deu VO HIEU trong DOM
    //     (va ca hai deu co LUAT o tren ap cho chung) — quan he nay khong the xanh neu thieu
    //     mot trong hai ve.
    const t = banGhi([doan(1, "你好")]);
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: t,
      translations: [],
      specs: [spec("qwen2.5-3b", "Qwen 2.5 3B", false)],
      onTaoBanDich: () => {},
    }));
    assert.equal((phanTuTu(container, '[data-testid="tao-ban-dich"]') as HTMLButtonElement).disabled, true,
      "khong co engine MT dung duoc ⇒ nut 'dich' VO HIEU");
    assert.equal((phanTuTu(container, "select") as HTMLSelectElement).disabled, true,
      "cung luc do o chon engine cung VO HIEU — hai ve cua CUNG mot su that");

    // (e) ⚠️ MUTANT `W3-10` (doi `className` cua NUT sang mot lop KHONG co luat nao) tung
    //     **SONG SOT**: hai khang dinh tren KHONG he doc `className`, nen luat CSS bi mo coi ma
    //     bai van XANH. Day la ve thu ba cua cung mot quan he: phan tu THAT trong DOM phai
    //     mang DUNG lop ma `app.css` khai luat (dung bai hoc ERRATA #15 muc 3 — "lop" va
    //     "luat" phai duoc ghim CUNG NHAU).
    const lopNut = (phanTuTu(container, '[data-testid="tao-ban-dich"]').getAttribute("class") ?? "").split(/\s+/);
    assert.ok(lopNut.includes("cmp__nut-dich"),
      `nut phai mang lop \`cmp__nut-dich\` — do moi la lop co LUAT trong app.css; do duoc ${JSON.stringify(lopNut)}`);
  });

  it("HINH THUC (C1): `.cmp` khai DU track cho so con CO MAT, va TUNG con co `grid-row` tro dung track", () => {
    // ---------------------------------------------------------------------------
    // 🔴 `Critical` C1 cua review W3 (ERRATA #36 muc 3) — DUNG LOP LOI cua `Critical #1`
    // Task 10 (ERRATA #31 muc 1), lan thu HAI. DO DUOC truoc khi sua, o dung trang thai
    // rong cua W3 (`translations: []`, registry toan MT `available: false`):
    //     so con = 5 ; so track = 4 ; con = [.cmp__thanh, .cmp__tin, .cmp__rong,
    //     .cmp__dau, .cmp__danh-sach] ; `.cmp__tin:empty` = false
    // Nam item vao bon track ⇒ `.cmp__dau` chiem hang `1fr` va `.cmp__danh-sach` roi vao
    // mot hang IMPLICIT `auto` ⇒ danh sach khong cuon duoc, dau cot gian ra.
    //
    // ⚠️ BAI NAY GHIM **QUAN HE**, KHONG GHIM NGUYEN VAN (ERRATA #34 muc 1):
    //   (i)  so con CO MAT  ≤  so track da khai  — doc so con tu DOM THAT, so track tu
    //        CHINH `app.css`; KHONG khang dinh "co dung sau gia tri `auto auto …`";
    //   (ii) TUNG con co `grid-row` tro vao mot track CO THAT (1 ≤ hang ≤ so track) va
    //        HAI con khac nhau khong dung cung mot hang khi ca hai cung co mat;
    //   (iii) hang `1fr` — cho cuon cua danh sach — thuoc ve `.cmp__danh-sach`, khong
    //        thuoc `.cmp__dau` (day la menh de noi dung cua C1, va no DO khi `.cmp` ve
    //        bon track vi khi do `grid-template-rows` chi con `auto auto auto 1fr`).
    // ⇒ Mutation "dua `.cmp` ve BON track" lam bai DO (ve (i) va ve (iii)).
    // ---------------------------------------------------------------------------
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    // ⚠️ BO CHU THICH truoc khi parse: mot dau `}` nam trong chu thich se cat CUT khoi luat
    // (do duoc: ban nhap dau tien cua khoi chu thich C1 lam phep cat tra ve `so track = 0`).
    const cssTran = appCss.replace(/\/\*[\s\S]*?\*\//g, "");

    /**
     * MOI khoi luat khai selector nay NHU MOT selector TRON VEN.
     *
     * ⚠️ Vi sao khong dung `new RegExp("\\" + selector + " \\{[^}]*\\}")`: selector nay xuat
     * hien trong nhieu luat (`.cmp__dau`, `.cmp__dau.is-pinned`, `.cmp__tin`, `.cmp__tin:empty`),
     * nen `[^}]*` cua mot luat DUNG TRUOC no se nuot luon khoi luat that ⇒ phep do bao
     * "khong khai `grid-row`" trong khi no CO khai. Do duoc o ban nhap dau (bai DO vi ly do sai).
     */
    function cacKhoi(selector: string): string[] {
      const khoa = `\\${selector}(?![a-zA-Z0-9_-])[^{}]*\\{([^{}]*)\\}`;
      return [...cssTran.matchAll(new RegExp(khoa, "g"))].map((m) => m[1] ?? "");
    }

    function khoi(selector: string, vi: string): string {
      const ds = cacKhoi(selector);
      assert.ok(ds.length > 0, `khong doc duoc khoi luat "${selector}" trong app.css (${vi})`);
      return ds[0];
    }

    /** So track ma khoi luat `.cmp` khai, doc tu CHINH van ban CSS. */
    function soTrack(selector: string): number {
      const dong = /grid-template-rows:\s*([^;]+);/.exec(khoi(selector, "lay so track"));
      assert.ok(dong !== null, `"${selector}" phai khai \`grid-template-rows\``);
      return dong[1].trim().split(/\s+/).length;
    }

    /**
     * `grid-row` dang so ma BAT KY khoi luat nao khai — `null` neu khong khoi nao khai.
     *
     * ⚠️ Phai quet MOI khoi: mot con co the co nhieu luat (`.cmp__tin` va `.cmp__tin:empty`),
     * va `grid-row` chi can khai o MOT trong chung. Doi hoi no nam trong khoi DAU TIEN la mot
     * phep do SAI (ban nhap dau cua bai nay DO vi dung ly do do).
     */
    function hangCua(selector: string): number | null {
      for (const than of cacKhoi(selector)) {
        const hang = /grid-row:\s*(\d+)/.exec(than);
        if (hang !== null) return Number(hang[1]);
      }
      return null;
    }

    const track = soTrack(".cmp");
    const trackCua = /grid-template-rows:\s*([^;]+);/
      .exec(khoi(".cmp", "lay danh sach track"))?.[1].trim().split(/\s+/) ?? [];

    const t = banGhi([doan(1, "你好"), doan(2, "谢谢")]);
    // HAI trang thai THAT cua W3 cho cung mot ban ghi da chon:
    //   (a) RONG: chua co ban dich nao + khong MT nao dung duoc ⇒ khay tin co 2 nhanh,
    //       `.cmp__tin:empty` = FALSE (day la trang thai sinh ra C1);
    //   (b) DAY: co hai ban dich, con thu sau `.cmp__danh-sach` cung co mat.
    const trangThai = [
      {
        ten: "RONG (khay tin CO noi dung)",
        props: { translations: [], specs: [spec("qwen2.5-3b", "Qwen 2.5 3B", false)] },
      },
      {
        ten: "DAY (co ban dich)",
        props: {
          translations: [banDich(11, ["câu một (dịch)"], [{ i: 1, cps: 4.2, over: false }])],
          specs: SPECS,
        },
      },
    ];

    const trackDaGhim = new Map<string, number>();
    for (const tt of trangThai) {
      const { container } = render(taoPhanTu(CompareScreen, {
        transcript: t,
        onTaoBanDich: () => {},
        ...tt.props,
      }));
      const con = [...container.querySelectorAll(".cmp > *")];
      // PHEP DO BAT BUOC cua brief §8: in ra SO CON CO MAT va SO TRACK.
      console.log(`C1 ${tt.ten}: so con CO MAT = ${con.length} ; so track da khai = ${track}`);

      // (i) QUAN HE: so con CO MAT ≤ so track.
      assert.ok(
        con.length <= track,
        `${tt.ten}: luoi khai ${track} track nhung co ${con.length} con CO MAT — it nhat mot con `
        + `se roi vao hang IMPLICIT (auto), va hang \`1fr\` bi con khac chiem; do duoc `
        + `${JSON.stringify(con.map((el) => (el.getAttribute("class") ?? "").trim()))}`,
      );

      // (ii) TUNG con co `grid-row` tuong minh, tro vao mot track CO THAT.
      for (const el of con) {
        const lop = (el.getAttribute("class") ?? "").trim().split(/\s+/)[0] ?? "";
        const hang = hangCua(`.${lop}`);
        assert.ok(
          hang !== null,
          `\`.${lop}\` la mot con CO MAT cua \`.cmp\` nhung KHONG khai \`grid-row\` ⇒ no do `
          + `auto-placement dat, va do la co che sinh ra C1 (ERRATA #31 muc 1)`,
        );
        assert.ok(
          hang >= 1 && hang <= track,
          `\`.${lop}\` tro vao hang ${hang} nhung \`.cmp\` chi khai ${track} track `
          + `⇒ no roi vao mot hang IMPLICIT; do duoc ${JSON.stringify(trackCua)}`,
        );
        const cu = trackDaGhim.get(lop);
        if (cu !== undefined) {
          assert.equal(cu, hang, `\`.${lop}\` phai tro vao CUNG mot hang o moi trang thai (${cu} vs ${hang})`);
        }
        trackDaGhim.set(lop, hang);
      }
    }

    // (iii) HANG `1fr` THUOC VE DANH SACH, KHONG THUOC VE DAU COT — menh de noi dung cua C1.
    const hangDau = hangCua(".cmp__dau");
    const hangDanhSach = hangCua(".cmp__danh-sach");
    assert.ok(hangDau !== null && hangDanhSach !== null, "ca `.cmp__dau` lan `.cmp__danh-sach` phai khai `grid-row`");
    assert.notEqual(hangDau, hangDanhSach, "dau cot va danh sach KHONG duoc dung CUNG mot hang");
    assert.equal(
      trackCua[hangDanhSach - 1],
      "1fr",
      `hang ${hangDanhSach} (cho \`.cmp__danh-sach\`) phai la track \`1fr\` — do la cho CUON cua danh sach; `
      + `do duoc track[${hangDanhSach - 1}] = ${JSON.stringify(trackCua[hangDanhSach - 1])}, `
      + `toan bo track = ${JSON.stringify(trackCua)}`,
    );
    assert.notEqual(
      trackCua[hangDau - 1],
      "1fr",
      `hang ${hangDau} (cho \`.cmp__dau\`) KHONG duoc la track \`1fr\`: do la loi C1 (dau cot gian ra, `
      + `danh sach khong cuon duoc); do duoc ${JSON.stringify(trackCua)}`,
    );

    // (iv) HANG `1fr` LA HANG **DUY NHAT** DUOC GIAN — ve phu con thieu (re-review W3 #1, `Minor #1`).
    //
    // DO DUOC: mutation `RR-2fr` (`auto auto auto auto auto 1fr` → `auto auto auto auto 1fr 1fr`,
    // tuc hang 5 — hang RONG — cung thanh `1fr`) lam danh sach cuon CHI CON MOT NUA chieu cao,
    // nhung **0 bai do** — vi (iii) chi khang dinh *"hang cua `.cmp__danh-sach` LA `1fr`"* va
    // *"hang cua `.cmp__dau` KHONG la `1fr`"*; no KHONG khang dinh **khong con hang `1fr` nao khac**.
    // ⇒ Phep dem duoi day ghim dung menh de "DUY NHAT": them mot `1fr` thu hai ⇒ DO.
    const soHangGian = trackCua.filter((t) => t === "1fr").length;
    assert.equal(
      soHangGian,
      1,
      `\`.cmp\` chi duoc co DUNG MOT hang \`1fr\` (cho cuon cua danh sach); do duoc ${soHangGian} `
      + `trong ${JSON.stringify(trackCua)} — mot hang \`1fr\` THUA (vi du hang 5 rong) lam danh sach `
      + `cuon mat mot nua chieu cao`,
    );
    assert.equal(
      trackCua.indexOf("1fr"),
      hangDanhSach - 1,
      `hang \`1fr\` DUY NHAT phai la hang ${hangDanhSach} (cho \`.cmp__danh-sach\`); `
      + `do duoc ${JSON.stringify(trackCua)}`,
    );
  });

  it("HINH THUC (mồ côi): MOI lop `.cmp` ma `app.css` tao kieu PHAI co trong DOM THAT, va NGUOC LAI", () => {
    // ---------------------------------------------------------------------------
    // 🔴 LOP LO HONG DO PHU MOI cua review W3 (`Minor #1`, ERRATA #36 muc 5): ba mutant
    // `W3-14/15/16` **DOI TEN LUAT trong `app.css` ma GIU `className` trong TSX** ⇒ 0 bai do.
    // Class van nam trong DOM, luat van "co trong tep", nhung **KHONG CON KHOP NHAU** — luat
    // mo coi. Bai ghim CSS cu chi khang dinh *"mot vai luat CO TON TAI"*, nen no MU voi dung
    // lop loi nay.
    //
    // Bai nay ghim QUAN HE HAI CHIEU (ERRATA #34 muc 1 — quan he, khong nguyen van):
    //   (A) MOI lop `.cmp*` ma `app.css` tao kieu PHAI xuat hien trong DOM THAT (bat `W3-14/15/16`:
    //       doi ten luat ⇒ ten moi khong co lop nao trong DOM ⇒ DO);
    //   (B) MOI lop `.cmp*` co trong DOM THAT PHAI duoc `app.css` tao kieu (bat `W3-10`: doi
    //       `className` sang mot lop khong co luat ⇒ DO).
    // ⚠️ KHONG ghim danh sach ten lop nguyen van: them mot lop moi (co luat + co dung) phai
    // lam bai XANH, khong phai DO.
    // ---------------------------------------------------------------------------
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const cssTran = appCss.replace(/\/\*[\s\S]*?\*\//g, "");

    /** Tap lop `.cmp*` ma `app.css` tao kieu — theo TUNG selector, khong theo ca danh sach. */
    function lopTrongCss(): Set<string> {
      const ra = new Set<string>();
      // Chi nhan selector TOAN cuc bat dau bang `.cmp`: `[^{}]*` de khong dinh luat long nhau,
      // va `(^|})` de khong nhan selector nam trong mot danh sach cua luat khac (vi du
      // `.cmp__chon[aria-checked="true"]` van la cua `.cmp` — no PHAI duoc tinh).
      for (const m of cssTran.matchAll(/(?:^|\})\s*([^{}]*?)\{/g)) {
        for (const lop of (m[1] ?? "").matchAll(/\.(cmp[a-z0-9_-]*)/g)) ra.add(lop[1] ?? "");
      }
      ra.delete("");
      return ra;
    }

    /** Tap lop `cmp*` co trong DOM that cua tat ca cac trang thai tuan tu. */
    const lopTrongDom = new Set<string>();
    for (const props of [
      { transcript: null, translations: [], specs: SPECS },
      { transcript: banGhi([doan(1, "你好")]), translations: [], specs: [spec("qwen2.5-3b", "Qwen 2.5 3B", false)] },
      { transcript: banGhi([doan(1, "你好")]), translations: [], specs: SPECS },
      { transcript: banGhi([doan(1, "你好")]), translations: [banDich(11, ["Xin chao"], [{ i: 1, cps: 4, over: true }])], specs: SPECS },
      { transcript: banGhi([doan(1, "你好"), doan(2, "谢谢")]), translations: [banDich(13, [], [], { status: "queued" })], specs: SPECS, trangThaiJob: "queued" as const },
      // ⚠️ HAI trang thai PHAI co mat o day vi chung la noi DUY NHAT sinh ra hai lop:
      //   (a) `cmp__ghim-cot` chi co khi GHIM ban B ⇒ can >= 2 ban dich VA bam nut ghim;
      //   (b) `cmp__loi-tao` chi co khi loi tao khac `null`.
      // Neu thieu mot trong hai, bai (A) se bao "luat mo coi" cho mot luat CO that — do la
      // mot phep do SAI (da do duoc o ban nhap dau: `["cmp__ghim-cot","cmp__loi-tao"]`).
      {
        transcript: banGhi([doan(1, "你好")]),
        translations: [banDich(11, ["Xin chao"], [{ i: 1, cps: 4, over: false }]), banDich(12, [], [], { status: "queued" })],
        specs: SPECS,
        loiTao: "409: engine chua san sang",
        bamGhim: true,
      },
    ] as (Record<string, unknown> & { bamGhim?: boolean })[]) {
      const { container } = render(taoPhanTu(CompareScreen, { onTaoBanDich: () => {}, ...props }));
      if (props.bamGhim === true) fireEvent.click(phanTuTu(container, '[data-testid="ghim"]'));
      for (const el of container.querySelectorAll("*")) {
        for (const lop of el.classList) if (lop.startsWith("cmp")) lopTrongDom.add(lop);
      }
    }

    const trongCss = lopTrongCss();
    assert.ok(trongCss.size >= 15, `phai doc duoc cac lop .cmp* tu app.css; do duoc ${trongCss.size}`);
    assert.ok(lopTrongDom.size >= 15, `phai thu duoc cac lop .cmp* tu DOM; do duoc ${lopTrongDom.size}`);

    // (A) LUAT ⇒ LOP: luat mo coi (khong lop nao mang ten do) lam bai DO.
    const moCoi = [...trongCss].filter((lop) => !lopTrongDom.has(lop)).sort();
    assert.deepEqual(
      moCoi,
      [],
      `LUAT MO COI trong app.css: ${JSON.stringify(moCoi)} — luat nay khong lop nao trong DOM mang, `
      + `tuc no KHONG tao kieu cho thu gi (lop W3-14/15/16: doi ten luat ma giu className). `
      + `Lop co trong DOM: ${JSON.stringify([...lopTrongDom].sort())}`,
    );

    // (B) LOP ⇒ LUAT: lop trong DOM ma khong co luat nao ap cho no cung lam bai DO.
    const voLuat = [...lopTrongDom].filter((lop) => !trongCss.has(lop)).sort();
    assert.deepEqual(
      voLuat,
      [],
      `LOP KHONG CO LUAT: ${JSON.stringify(voLuat)} — lop nay nam trong DOM nhung app.css khong `
      + `tao kieu cho no (lop W3-10: doi className sang mot lop khong co luat). `
      + `Luat co trong app.css: ${JSON.stringify([...trongCss].sort())}`,
    );
  });

  it("HINH THUC: LUAT CSS cua man Doi chieu CO THAT trong `app.css`, va moi token deu co dinh nghia", () => {
    // ERRATA #15 muc 3 (do duoc HAI CHIEU o Task 6): mot test chi khang dinh
    // `className` van XANH khi luat CSS bi xoa. Cach re nhat de ghim luat: DOC tep CSS.
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const tokensCss = readFileSync(new URL("../styles/tokens.css", import.meta.url), "utf8");

    // Moc phai khop TUNG KY TU voi chu thich trong `app.css` (co dau, khong phai ASCII):
    // ban nhap dau cua bai nay dung "Man DOI CHIEU" va do la mot phep do SAI — no bao
    // "app.css thieu khoi luat" trong khi khoi luat CO that. Da do lai va sua.
    const moc = "Màn ĐỐI CHIẾU (Task 8)";
    const viTri = appCss.indexOf(moc);
    assert.ok(viTri > 0, "app.css phai co KHOI LUAT cua man Doi chieu, khong chi co class trong TSX");
    const khoi = appCss.slice(viTri);

    for (const chon of [".cmp {", ".cmp__dong {", ".cmp__goc {", ".cmp__dich {", ".cmp__cps {"]) {
      assert.ok(khoi.includes(chon), `app.css thieu luat "${chon}"`);
    }
    // Luat THAT, khong phai ten lop: bon khai bao quyet dinh HINH DANG cua man nay.
    assert.match(khoi, /\.cmp \{[^}]*display: grid/, "hai cot + cot CPS phai la mot LUOI");
    assert.match(khoi, /\.cmp__cps \{[^}]*font-family: var\(--font-mono\)/,
      "cot CPS la SO va phai xep thang cot ⇒ phai la MONO");
    assert.match(khoi, /\.cmp__dong\.is-over \{[^}]*var\(--signal\)/,
      "dong vuot nguong phai co LUAT VE THAT (moc amber), khong chi co ten lop `is-over`");
    assert.match(khoi, /\.cmp__dong\.is-pinned \{[^}]*grid-template-columns:/,
      "ghim ban B phai mo them COT THAT trong luoi, khong chi doi ten lop");

    // Token nao khoi nay dung thi phai co dinh nghia THAT trong `tokens.css`.
    const dung = [...new Set([...khoi.matchAll(/var\((--[a-z0-9-]+)\)/g)].map((m) => m[1] ?? ""))];
    assert.ok(dung.length >= 4, `khoi Doi chieu phai dung token that, do duoc ${dung.length}`);
    for (const token of dung) {
      assert.ok(tokensCss.includes(`${token}:`), `token ${token} duoc dung nhung KHONG dinh nghia trong tokens.css`);
    }
  });
});
