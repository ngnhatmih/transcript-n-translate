/**
 * Test `<EditScreen/>` THAT trong jsdom (spec UI §4.1) — danh sach doan AO HOA,
 * dong dang sua duoc GHIM, doan `suspect` co VAN + LY DO.
 *
 * Vi sao jsdom chu khong Playwright: trinh duyet THAT BAT KHA o moi truong nay
 * (Chromium chet o `FATAL:mojo\...\platform_channel.cc:187 ... Access is denied (0x5)`
 * vi Mojo dung NAMED PIPE — ERRATA #5 muc 3). jsdom KHONG phai trinh duyet: KHONG
 * layout, KHONG CSS that. ⇒ Tep nay do duoc HANH VI (cai gi nam trong DOM, lop nao,
 * chu nao), KHONG do duoc HINH (van cheo co hien ra khong, hang cao bao nhieu).
 *
 * LUAT DOM (ERRATA #9 muc 1/6) — tep nay TU CHUA va khong dua vao thu tu:
 *   - MOI hook dat/tra global nam TRONG `describe()`: duoi `--test-isolation=none`, hook
 *     cap TEP bi node:test keo len GOC ca luot (moi `before` truoc MOI bai, moi `after`
 *     sau MOI bai) — do bang dong ho chung, khong phai suy dien.
 *   - `setupDom`/`teardownDom` cua CHINH tep nay; khong gia dinh jsdom cua tep khac con
 *     song, va khong de lai global nao cho tep sau.
 *   - `console.error`/`console.warn` bi TAM THAY de bat tieng on va duoc TRA LAI trong
 *     `after` (chung cung la global: ERRATA #7 muc 3).
 *   - LUON chay TOAN BO `npm test`, khong chay le tep: suy giam do nhiem cheo chi lo ra
 *     o luot day du.
 *
 * ⚠️ `npm run typecheck` KHONG kiem tep `.test.tsx` (`tsc --listFiles` khong co tep
 * `.test.` nao — ERRATA #10 muc 8/ERRATA #12 muc 3) ⇒ loi kieu trong tep nay CHI lo ra
 * luc chay, va `npm test` cua luot day du VON DA `EXIT=1` (hai bai `EMPTY_DB_MSG` do
 * chu y) nen EXIT KHONG phai kenh thong tin (ERRATA #11 muc 1).
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import type { Segment, Transcript } from "../api/types.ts";
import { withPinned } from "../lib/window.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

/** Mot doan theo dung 5 khoa LUON co cua `Segment` (`types.ts`), cong khoa tuy chon. */
function doan(
  i: number,
  start: number,
  end: number,
  text: string,
  suspect = false,
  extra: Partial<Segment> = {},
): Segment {
  return { i, start, end, text, suspect, ...extra };
}

/** `Transcript` day du (7 khoa cua `TranscriptSummary` + `segments`) — khong dung `as`. */
function banGhi(segments: Segment[]): Transcript {
  return {
    id: 1,
    source_id: 1,
    engine: "sensevoice",
    lang: "zh",
    version: 2,
    status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    translations: [],
    segments,
  };
}

/** Danh sach dai de chung minh AO HOA that (spec §8.2: transcript 2 gio ≈ 2000 dong). */
function nhieuDoan(n: number): Segment[] {
  return Array.from({ length: n }, (_, i) => doan(i, i * 2, i * 2 + 2, `đoạn ${i}`));
}

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
  change: (el: Element, init: unknown) => void;
  keyDown: (el: Element, init: unknown) => void;
  click: (el: Element) => void;
  scroll: (el: Element) => void;
};
let cleanup: () => void;
/** `createElement` — goi ham component NGOAI chu trinh render se nem `useState` dispatcher null. */
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let EditScreen: (props: unknown) => unknown;
let windowFor: (
  scrollTop: number,
  viewportH: number,
  rowH: number,
  soDoan: number,
  overscan: number,
  pinned: number | null,
) => { start: number; end: number; pinned: boolean };

/** `textContent` cua phan tu DAU TIEN khop `chon` — khong hoi ca DOM (khang dinh phai GAN DUNG doi tuong). */
function chu(container: HTMLElement, chon: string): string {
  const el = container.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.textContent ?? "";
}

function lop(container: HTMLElement, chon: string): string {
  const el = container.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return (el as HTMLElement).className;
}

/**
 * Khang dinh KHONG co phan tu nao khop `chon` — DEM, khong so sanh NODE.
 *
 * ⚠️ DO DUOC (vong mutation cua chinh task nay, mutation `E9`): `assert.equal(<node DOM>,
 * null)` roi vao nhanh DO lam `npm test` chay **qua 90 s** (bi tran 90 s cat ngang, log
 * dung giua suite) trong khi luot SACH la **~6 s**. Ly do: `assert.equal` in `actual` bang
 * `util.inspect`, va mot node do React render mang theo thuoc tinh noi bo (`__reactFiber$…`)
 * tro vao CA cay fiber — mot do thi khong lo, co vong. Do la **phep do hong**, khong phai
 * "bai test khong giet duoc mutation": voi tran 300 s cung mutation do ket thuc binh thuong
 * (`tests 86 / pass 83 / fail 3 / cancelled 0`) va giet DUNG bai "CUON".
 * ⇒ Moi khang dinh "khong co phan tu" o tep nay dem SO LUONG (mot con so), khong so sanh node.
 */
function khongCo(container: HTMLElement, chon: string, msg: string): void {
  assert.equal(container.querySelectorAll(chon).length, 0, msg);
}

describe("EditScreen: §4.1 danh sach doan ao hoa + GHIM dong dang sua + suspect co VAN va LY DO", () => {
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
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const man: any = await import("./EditScreen.tsx");
    EditScreen = man.EditScreen;
    windowFor = man.windowFor;

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

  it("AO HOA: chi render CUA SO, khong render ca 200 doan; dem giu tong chieu cao", () => {
    const { container, unmount } = render(
      taoPhanTu(EditScreen, { transcript: banGhi(nhieuDoan(200)), viewportH: 480, rowH: 44, overscan: 0 }),
    );

    assert.equal(
      container.querySelectorAll("[data-i]").length,
      11,
      "cua so 480/44 phai la 11 hang (neu render het thi la 200)",
    );
    assert.ok(container.querySelector('[data-i="0"]') !== null, "hang dau phai nam trong DOM");
    khongCo(container, '[data-i="11"]', "hang ngoai cua so khong duoc render");
    khongCo(container, '[data-i="199"]', "hang cuoi khong duoc render");

    // DEM: khong co dem thi chieu cao cuon chi bang cua so ⇒ khong cuon duoc qua 200 doan.
    const dau = container.querySelector(".ed__dem-dau") as HTMLElement;
    const cuoi = container.querySelector(".ed__dem-cuoi") as HTMLElement;
    assert.equal(dau.style.height, "0px", "dem dau phai bang start * rowH");
    assert.equal(cuoi.style.height, `${(200 - 11) * 44}px`, "dem cuoi phai bang (soDoan - end) * rowH");

    assert.deepEqual(tiengOn, [], "render danh sach khong duoc sinh tieng on console");
    unmount();
  });

  it("M4: `end` KEP theo SO DOAN khi chi so ghim lon hon so doan", () => {
    // `withPinned` mot minh KHONG kep theo `count` — do duoc o Task 5:
    // `withPinned({start:100,end:120}, 500)` ⇒ `end = 501`. Neu khong kep o day thi
    // dem cuoi = (soDoan - end) * rowH la mot so AM.
    const w = windowFor(0, 480, 44, 3, 0, 500);
    assert.ok(w.end <= 3, `end phai <= soDoan = 3, do duoc ${w.end}`);
    assert.equal(w.end, 3);
    assert.equal(w.start, 0);
    assert.equal(w.pinned, true, "chi so ghim ngoai khoang thi phai bao da ghim");

    // WITNESS: day la ly do `windowFor` ton tai — khong co no thi `end` vuot so doan.
    assert.equal(withPinned({ start: 0, end: 3 }, 500).end, 501);

    // Va ca THUONG: khong ghim thi `end` = ceil(viewportH / rowH).
    assert.deepEqual(windowFor(0, 480, 44, 2000, 0, null), { start: 0, end: 11, pinned: false });
  });

  it("GHIM: dong dang sua NAM NGOAI cua so van duoc render (spec UI §5.3 / U6)", () => {
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi(nhieuDoan(200)),
        viewportH: 480,
        rowH: 44,
        overscan: 0,
        editingSegment: 150,
      }),
    );

    assert.ok(
      container.querySelector('[data-i="150"]') !== null,
      "dong dang sua PHAI nam trong DOM — thieu ghim thi ao hoa thao no ra va MAT FOCUS",
    );
    const o = container.querySelector('[data-i="150"] textarea') as HTMLTextAreaElement;
    assert.ok(o !== null, "dong dang sua phai la mot o sua (textarea)");
    assert.equal(o.value, "đoạn 150", "o sua phai mang dung chu cua doan dang sua");

    assert.deepEqual(tiengOn, [], "ghim dong dang sua khong duoc sinh tieng on console");
    unmount();
  });

  it("SUA DONG: o `<textarea>` TU GIAN theo noi dung, `Enter` tra chu MOI cho ben goi", () => {
    const daLuu: Array<[number, string]> = [];
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi([doan(0, 0, 2, "câu không sửa"), doan(1, 2, 4, "câu một")]),
        editingSegment: 1,
        onCommitEdit: (i: number, text: string): void => {
          daLuu.push([i, text]);
        },
      }),
    );

    const o = container.querySelector("textarea") as HTMLTextAreaElement;
    assert.ok(o !== null, "doan dang sua phai la textarea (plan cam `contentEditable`)");
    assert.equal(o.value, "câu một", "chu trong o phai la chu HIEN TAI cua doan");
    assert.equal(o.getAttribute("rows"), "1", "chu ngan ⇒ mot dong");

    const dai = "x".repeat(200);
    fireEvent.change(o, { target: { value: dai } });
    // TU GIAN: do dai chu quyet dinh so dong. Khong co no thi o sua cuon ngam, nguoi
    // dung khong thay het cau.
    assert.equal(Number(o.getAttribute("rows")), 4, "200 ky tu ⇒ 4 dong (60 ky tu/dong)");

    fireEvent.keyDown(o, { key: "Enter" });
    assert.deepEqual(daLuu, [[1, dai]], "`Enter` phai tra chu MOI (ban nhap) cho ben goi");

    assert.deepEqual(tiengOn, [], "go va luu trong o sua khong duoc sinh tieng on console");
    unmount();
  });

  it("SUSPECT la VAN (lop), khong chi la MAU — va hang thuong thi khong co lop do", () => {
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi([
          doan(0, 0, 2, "câu bình thường"),
          doan(1, 2, 4, "nhạc to", true, { events: ["bgm"] }),
        ]),
      }),
    );

    // Hai chieu: co VAN o hang nghi ngo VA khong co o hang thuong. Chi kiem mot chieu
    // thi mot thay doi gan SAI hang se di qua xanh (bai hoc `S2` cua Task 4).
    assert.match(lop(container, '[data-i="1"]'), /is-suspect/);
    assert.doesNotMatch(lop(container, '[data-i="0"]'), /is-suspect/);

    assert.deepEqual(tiengOn, [], "danh dau nghi ngo khong duoc sinh tieng on console");
    unmount();
  });

  it("SUSPECT co LY DO bang CHU (doc duoc, khong phu thuoc mau) — spec UI §2.5/§7", () => {
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi([
          doan(0, 0, 2, "nhạc to", true, { events: ["bgm"] }),
          doan(1, 2, 4, "không rõ", true),
          doan(2, 4, 6, "thiếu dấu", true, { qa: ["thieu_dau"] }),
          doan(3, 6, 8, "câu bình thường"),
        ]),
      }),
    );

    assert.match(chu(container, '[data-i="0"]'), /nhạc nền/);
    assert.match(chu(container, '[data-i="1"]'), /nghi ngờ/);
    assert.match(chu(container, '[data-i="2"]'), /thiếu dấu câu/);
    assert.doesNotMatch(chu(container, '[data-i="3"]'), /nghi ngờ/);

    assert.deepEqual(tiengOn, [], "nhan ly do khong duoc sinh tieng on console");
    unmount();
  });

  it("DOAN DANG PHAT co le am bert (lop), doan khac thi khong — spec UI §4.1", () => {
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi(nhieuDoan(3)),
        currentSegment: 1,
      }),
    );

    assert.match(lop(container, '[data-i="1"]'), /is-current/);
    assert.doesNotMatch(lop(container, '[data-i="0"]'), /is-current/);
    assert.doesNotMatch(lop(container, '[data-i="2"]'), /is-current/);

    assert.deepEqual(tiengOn, [], "danh dau doan dang phat khong duoc sinh tieng on console");
    unmount();
  });

  it("CUON: cua so troi theo vi tri cuon cua khung", () => {
    const { container, unmount } = render(
      taoPhanTu(EditScreen, { transcript: banGhi(nhieuDoan(200)), viewportH: 480, rowH: 44, overscan: 0 }),
    );
    const khung = container.querySelector(".ed__khung") as HTMLElement;
    assert.ok(khung !== null, "danh sach phai nam trong mot khung cuon");
    assert.ok(container.querySelector('[data-i="0"]') !== null, "truoc khi cuon, hang 0 phai co");

    // jsdom KHONG tinh `scrollTop` tu layout, nhung DAT TAY duoc (do truoc khi viet bai
    // nay). Nho vay duong "cuon ⇒ doi cua so" kiem duoc that, khong phai khai suong.
    khung.scrollTop = 44 * 100;
    fireEvent.scroll(khung);

    khongCo(container, '[data-i="0"]', "hang 0 phai ra khoi cua so");
    assert.ok(container.querySelector('[data-i="100"]') !== null, "hang 100 phai vao cua so");

    assert.deepEqual(tiengOn, [], "cuon khong duoc sinh tieng on console");
    unmount();
  });

  it("BAM vao dong ⇒ xin mo o sua (chu trang thai la BEN GOI, khong phai man)", () => {
    const moSua: number[] = [];
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi(nhieuDoan(3)),
        onStartEdit: (i: number): void => {
          moSua.push(i);
        },
      }),
    );

    const nut = container.querySelector('[data-i="2"] button') as HTMLElement;
    assert.ok(nut !== null, "dong KHONG sua phai la mot nut bam duoc (spec UI §5.2)");
    fireEvent.click(nut);
    assert.deepEqual(moSua, [2]);

    assert.deepEqual(tiengOn, [], "bam vao dong khong duoc sinh tieng on console");
    unmount();
  });

  it("TRANG THAI RONG: chua co ban ghi ⇒ khong hang nao, va noi ro dang rong", () => {
    const { container, unmount } = render(taoPhanTu(EditScreen, { transcript: null }));

    assert.equal(container.querySelectorAll("[data-i]").length, 0, "khong duoc render hang nao");
    assert.match(container.textContent ?? "", /chưa có bản ghi/);

    assert.deepEqual(tiengOn, [], "trang thai rong khong duoc sinh tieng on console");
    unmount();
  });
});
