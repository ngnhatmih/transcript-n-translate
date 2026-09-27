/**
 * Test `<CompareScreen/>` THAT trong jsdom (spec UI §4.3) — HAI COT + COT CPS,
 * segmented control chon ban dich, GHIM ban B, va danh dau dong VUOT NGUONG DOC.
 *
 * Vi sao jsdom chu khong Playwright: trinh duyet THAT BAT KHA o moi truong nay
 * (Chromium chet o `FATAL:mojo\...\platform_channel.cc:187 ... Access is denied (0x5)`
 * vi Mojo dung NAMED PIPE — ERRATA #5 muc 3). jsdom KHONG phai trinh duyet: KHONG
 * layout, KHONG CSS that. ⇒ Tep nay do duoc HANH VI (cai gi nam trong DOM, lop nao,
 * chu nao, con so nao), KHONG do duoc HINH (cot rong bao nhieu, duong ke 1px co hien
 * ra khong, dau amber co nhin thay khong).
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

import type { Segment, Transcript, TranslationDetail } from "../api/types.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

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
  opts: { stale?: boolean; maxCps?: number; engine?: string } = {},
): TranslationDetail {
  return {
    id,
    transcript_id: 1,
    engine: opts.engine ?? "opus-mt",
    target_lang: "vi",
    prompt_version: "raw-p1",
    transcript_version: 1,
    status: "done",
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
let fireEvent: { click: (el: Element) => void };
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let CompareScreen: (props: unknown) => unknown;

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
    // Day la trang thai THAT trong app hom nay: `App` chua co duong CHON KENH
    // (ERRATA #18 muc 4) nen no truyen `transcript={null}`.
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
  // HINH THUC: ghim LUAT CSS, khong chi ghim ten lop (ERRATA #15 muc 3)
  // -------------------------------------------------------------------------

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
