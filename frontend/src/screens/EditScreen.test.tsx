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
import { readFileSync } from "node:fs";

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
  drop: (el: Element, init?: unknown) => boolean;
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

/** Phan tu DAU TIEN khop `chon` — tra NODE de doc thuoc tinh/bam, KHONG bao gio dua vao `assert`. */
function phanTu(container: HTMLElement, chon: string): Element {
  const el = container.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el;
}

/**
 * MOI khai bao cua MOT selector trong `app.css`, theo DUNG thu tu trong tep.
 *
 * ⚠️ VI SAO KHONG dung `RegExp(selector + "\\{[^}]*\\}")` nhu cac bai CSS truoc (ERRATA #42 muc 5 /
 * ERRATA #43 muc 2): `[^}]*` chi doc khoi luat DAU TIEN khop selector, nen mot luat SAU ghi DE
 * (`display:flex` roi `display:block`) di qua XANH trong khi khai bao THANG CUOC la `block`.
 * Ham nay doc HET cac khoi khop roi tra ve khai bao CUOI CUNG cua tung thuoc tinh — dung luat
 * "khai bao sau thang" cua CSS khi do dac hieu bang nhau.
 */
function khaiBaoCua(css: string, chon: string): Map<string, string> {
  const ra = new Map<string, string>();
  // ⚠️ BO COMMENT TRUOC KHI PHAN TICH. Do duoc HAI lan trong luot nay: (1) comment tieng Viet co
  // DAU PHAY nen `split(",")` ra nhung manh khong phai selector; (2) comment co DAU HAI CHAM
  // ("Đổi lại: …") nen `indexOf(":")` bat nham key va khai bao THAT (`grid-template-rows`) bi mat
  // ⇒ bai ghim doc ra `[]` va bao sai rang luat khong ton tai. Comment khong phai khai bao.
  const sach = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const phan of sach.split("}")) {
    const i = phan.lastIndexOf("{");
    if (i < 0) continue;
    const danhSachChon = phan
      .slice(0, i)
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s !== "");
    if (!danhSachChon.includes(chon)) continue;
    for (const khai of phan.slice(i + 1).split(";")) {
      const hai = khai.indexOf(":");
      if (hai < 0) continue;
      ra.set(khai.slice(0, hai).trim(), khai.slice(hai + 1).trim());
    }
  }
  return ra;
}

/** Tap LOP co THAT trong cay da render — nua "TEN LOP TRONG DOM" cua phep ghim QUAN HE. */
function lopTrongDom(container: HTMLElement): Set<string> {
  const ra = new Set<string>();
  for (const el of container.querySelectorAll("*")) {
    const c = el.getAttribute("class");
    if (c === null) continue;
    for (const ten of c.split(/\s+/)) if (ten !== "") ra.add(ten);
  }
  return ra;
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
    const { container, unmount } = render(
      taoPhanTu(EditScreen, { transcript: null, onNapTep: async () => [] }),
    );

    assert.equal(container.querySelectorAll("[data-i]").length, 0, "khong duoc render hang nao");
    assert.match(container.textContent ?? "", /chưa có bản ghi/);

    assert.deepEqual(tiengOn, [], "trang thai rong khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // TASK W2 — TRANG THAI RONG LA KHUNG §4.2 (spec UI: *"Vung giua la khung ke net dut"*)
  //
  // DO DUOC TRUOC W2: `uploadSource` **0 luot goi** va `frontend/src` **khong co**
  // `type="file"`/`onDrop` ⇒ ve khung "KÉO TỆP VÀO ĐÂY" ma tha tep vao khong co gi xay ra la
  // mot giao dien NOI DOI, nen Task 6 CO Y khong ve no (xem docstring cua man). Nay duong NAP
  // CO THAT, nen loi hua do phai duoc giu — va no phai nam o VUNG GIUA, khong phai mot the nho.
  // -------------------------------------------------------------------------

  it("W2 TRANG THAI RONG: vung giua la KHUNG §4.2 (khung + dong mono), va keo-tha di DUNG vao ham nap cua App", async () => {
    const daTha: string[][] = [];
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: null,
        onNapTep: async (files: File[]) => {
          daTha.push(files.map((t) => t.name));
          return [];
        },
      }),
    );

    // (a) Khung §4.2 NAM TRONG VUNG GIUA cua man Bien tap — va cau "chua co ban ghi" van con
    //     (no la SU THAT cua trang thai nay, khong phai thu bi thay the).
    assert.ok(container.querySelector(".ed .nap__khung") !== null, "khung §4.2 phai nam trong `.ed`");
    assert.match(container.textContent ?? "", /KÉO TỆP VÀO ĐÂY/);
    assert.match(container.textContent ?? "", /chưa có bản ghi/);

    // (b) Duong NAP di qua CHINH `onNapTep` (mot ham cua `App`, khong phai mot duong thu hai
    //     trong man nay) — do bang `fireEvent.drop`, tuc dung su kien ma trinh duyet phat ra.
    const tep = new File([new Uint8Array([1, 2, 3])], "a.wav", { type: "audio/wav" });
    fireEvent.drop(container.querySelector('[data-testid="nap-khung-keo"]') as Element, {
      dataTransfer: { files: [tep] },
    });
    assert.deepEqual(daTha, [["a.wav"]], "`drop` phai goi ham nap cua ben goi voi DUNG tep");

    assert.deepEqual(tiengOn, [], "trang thai rong cua W2 khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // TASK D1 — O SUA co NUT + DAU NUDGE + CAU TRANG THAI (man la NOI RA, khong chi doi mau)
  // -------------------------------------------------------------------------

  it("D1 O SUA: nut luu/huy + hai dau nudge + cau trang thai/loi co mat; `huy`/`Esc` KHONG ghi gi", () => {
    const daLuu: Array<[number, string]> = [];
    let soHuy = 0;
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi([doan(0, 0, 2, "câu không sửa"), doan(1, 2, 4, "câu một")]),
        editingSegment: 1,
        onCommitEdit: (i: number, text: string): void => {
          daLuu.push([i, text]);
        },
        onCancelEdit: (): void => {
          soHuy += 1;
        },
      }),
    );

    // (1) DONG DANG SUA: lop `is-editing`, o nhap la `textarea`, va chu trong o la chu HIEN CO.
    assert.match(lop(container, '[data-i="1"]'), /is-editing/);
    const o = phanTu(container, '[data-testid="o-sua"]') as HTMLTextAreaElement;
    assert.equal(o.value, "câu một", "o nhap phai mang DUNG chu hien co cua dong");
    // Hai MOC cua dong dang sua phai NHIN THAY duoc: nudge ma khong thay ket qua la mot phep do mu.
    assert.equal(chu(container, '[data-testid="moc-doan"]'), "0:02.00 → 0:04.00");

    // (2) HAI DAU NUDGE: `[` cho moc BAT DAU, `]` cho moc KET THUC — chu tren nut NOI RA chieu.
    assert.match(chu(container, '[data-testid="nudge-start"]'), /\[/);
    assert.match(chu(container, '[data-testid="nudge-start"]'), /0,1s/);
    assert.match(chu(container, '[data-testid="nudge-end"]'), /\]/);
    assert.match(chu(container, '[data-testid="nudge-end"]'), /0,1s/);

    // (3) NUT HUY: goi `onCancelEdit`, va TUYET DOI khong goi `onCommitEdit`.
    fireEvent.click(phanTu(container, '[data-testid="huy-doan"]'));
    assert.equal(soHuy, 1, "nut huy phai bao cho ben goi biet la HUY");
    assert.deepEqual(daLuu, [], "`huy` KHONG duoc ghi gi");

    // (4) `Enter` tra chu MOI cho ben goi...
    fireEvent.change(o, { target: { value: "chữ mới" } });
    fireEvent.keyDown(o, { key: "Enter" });
    assert.deepEqual(daLuu, [[1, "chữ mới"]], "`Enter` phai tra chu MOI (ban nhap) cho ben goi");
    // ...va `Esc` HUY, khong ghi them lan nao.
    fireEvent.keyDown(o, { key: "Escape" });
    assert.equal(soHuy, 2, "`Esc` phai bao HUY");
    assert.deepEqual(daLuu, [[1, "chữ mới"]], "`Esc` KHONG duoc ghi gi");

    assert.deepEqual(tiengOn, [], "o sua cua D1 khong duoc sinh tieng on console");
    unmount();
  });

  it("HINH THUC (D1): luat CSS KHOP TEN LOP trong DOM + `.ed` khai DU track va `grid-row` cho tung con", () => {
    // Render DAY DU trang thai cua D1 trong MOT lan: dang sua + dang luu + co cau loi + co cau
    // "loi thoi" ⇒ tap lop trong DOM la tap lop ma bon luat moi phai phuc vu.
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi([doan(0, 0, 2, "câu 1"), doan(1, 2, 4, "câu 2")]),
        editingSegment: 1,
        dangLuu: true,
        loiGhi: "422: segment không hợp lệ: thiếu khoá 'text'",
        cauLoiThoi: "bản dịch đã lỗi thời so với bản ghi",
      }),
    );

    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const coTrongDom = lopTrongDom(container);

    // (a) QUAN HE: moi lop cua D1 phai vua co LUAT (co khai bao THANG CUOC, khong rong) vua co
    //     THAT trong DOM. Mutation hai chieu: xoa luat giu class ⇒ do; doi ten class trong DOM
    //     giu luat ⇒ do. Khong ve nao khang dinh CHU cua luat (lop loi da tai phat bon lan).
    const lopD1 = [
      ".ed__sua-boc",
      ".ed__sua",
      ".ed__moc",
      ".ed__sua-thanh",
      ".ed__nudge",
      ".ed__nut--luu",
      ".ed__nut--huy",
      ".ed__ghi",
      ".ed__ghi--loi",
      ".ed__loi-thoi",
    ];
    for (const chon of lopD1) {
      const ten = chon.slice(1);
      assert.ok(
        coTrongDom.has(ten),
        `lop \`${ten}\` phai co THAT trong DOM (rules<->DOM: ${JSON.stringify([...coTrongDom].filter((t) => t.startsWith("ed")).sort())})`,
      );
      const khai = khaiBaoCua(appCss, chon);
      assert.ok(khai.size > 0, `phai co LUAT \`${chon}\` trong app.css (co khai bao THANG CUOC)`);
    }

    // (b) KHAI BAO THANG CUOC (khong phai "co o dau do"): `.ed__sua-boc` va `.ed__sua-thanh` la
    //     FLEX; mot luat SAU ghi de thanh `block` lam bai nay DO (mutation `D1-12` trong bang
    //     mutation cua `task-d1-report.md`; mot so cho con goi no la `D1-M4` — CUNG mot mutation).
    assert.equal(khaiBaoCua(appCss, ".ed__sua-boc").get("display"), "flex");
    assert.equal(khaiBaoCua(appCss, ".ed__sua-thanh").get("display"), "flex");
    assert.equal(khaiBaoCua(appCss, ".ed__moc").get("display"), "flex");

    // (c) LUOI `.ed` (ERRATA #31 muc 1): cau "loi thoi" la CON THU HAI cua mot luoi tung khai
    //     DUNG MOT track ⇒ phai khai them track VA vi tri cho TUNG con. Khong ghim nguyen van
    //     danh sach track (ghim the la dong bang so luong track).
    const trackEd = (khaiBaoCua(appCss, ".ed").get("grid-template-rows") ?? "")
      .split(/\s+/)
      .filter((t) => t !== "");
    assert.ok(
      trackEd.length >= 3,
      `\`.ed\` phai khai DU track cho BA con (cau loi thoi + thanh tren + khung danh sach); do duoc ${JSON.stringify(trackEd)}`,
    );
    function hangCua(chon: string): number {
      const khai = khaiBaoCua(appCss, chon).get("grid-row");
      assert.ok(khai !== undefined, `\`${chon}\` phai khai \`grid-row\` TUONG MINH (ERRATA #31 muc 1)`);
      const khop = /^(\d+)/.exec(khai);
      assert.ok(khop !== null, `\`grid-row\` cua \`${chon}\` phai bat dau bang mot so; do duoc ${khai}`);
      return Number(khop[1]);
    }
    // ⚠️ DINH CHINH SO CUA D1 (D2): `.ed` nay co BA con (cau loi thoi · thanh tren cua D2 ·
    // khung danh sach) nen khung danh sach lui xuong track 3. Menh de KHONG doi: "moi con khai
    // `grid-row` tuong minh, va khung danh sach nam o track CUOI (cho cuon)".
    assert.equal(hangCua(".ed__khung"), 3, "khung danh sach nam track `1fr` (track CUOI)");
    assert.equal(hangCua(".ed__loi-thoi"), 1, "cau 'loi thoi' nam track `auto` (co lai khi vang)");
    assert.ok(coTrongDom.has("ed__khung") && coTrongDom.has("ed__loi-thoi"));

    // (d) NOI DUNG cua hai cau: cau "loi thoi" la MOT cau doc duoc, va no la vung thong bao.
    assert.equal(
      phanTu(container, '[data-testid="loi-thoi"]').textContent,
      "bản dịch đã lỗi thời so với bản ghi",
    );
    assert.match(phanTu(container, '[data-testid="loi-thoi"]').getAttribute("class") ?? "", /(^|\s)ed__loi-thoi(\s|$)/);
    assert.equal(phanTu(container, '[data-testid="loi-thoi"]').getAttribute("role"), "status");
    assert.equal(chu(container, '[data-testid="dang-luu"]'), "đang lưu…");
    // LOI GHI la NGUYEN VAN `ApiError.message` (`<status>: <detail>`) — khong phai mot cau chung.
    assert.equal(
      chu(container, '[data-testid="loi-ghi"]'),
      "422: segment không hợp lệ: thiếu khoá 'text'",
    );

    assert.deepEqual(tiengOn, [], "hinh thuc D1 khong duoc sinh tieng on console");
    unmount();
  });

  // ===========================================================================
  // TASK D2 — NUT `duyet` O MAN BIEN TAP
  //
  // Man nay KHONG tu goi API (xem khoi dau tep): no BAO bang `onDuyet`, con `App` moi la nguoi
  // goi `approveTranscript` + DOC LAI. Trang thai ban ghi (`transcript.status`) la du lieu CUA MAY
  // CHU di qua prop — man chi RENDER no ra chu.
  // ===========================================================================

  it("D2 DUYET: nút `duyệt` CHỈ có khi CÓ bản ghi đang mở, và bấm thì BÁO LÊN (màn không tự gọi API)", () => {
    const soLan: number[] = [];
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi([doan(0, 0, 2, "câu 1")]),
        onDuyet: (): void => {
          soLan.push(1);
        },
      }),
    );

    // TRANG THAI BAN GHI noi ra bang CHU — va no la du lieu cua may chu (`Transcript.status`).
    assert.equal(chu(container, '[data-testid="trang-thai-ban-ghi"]'), "trạng thái: draft");
    fireEvent.click(phanTu(container, '[data-testid="duyet-ban-ghi"]'));
    assert.equal(soLan.length, 1, "bấm `duyệt` phải BÁO cho bên gọi (màn không tự gọi API)");

    assert.deepEqual(tiengOn, [], "nut duyet khong duoc sinh tieng on console");
    unmount();

    // TRANG THAI RONG: khong co ban ghi ⇒ KHONG co nut (khong the duyet mot thu khong ton tai).
    const rong = render(taoPhanTu(EditScreen, { transcript: null, onNapTep: async () => [] }));
    assert.equal(
      rong.container.querySelectorAll('[data-testid="duyet-ban-ghi"]').length,
      0,
      "chưa có bản ghi đang mở ⇒ KHÔNG được có nút duyệt",
    );
    assert.equal(
      rong.container.querySelectorAll('[data-testid="trang-thai-ban-ghi"]').length,
      0,
      "chưa có bản ghi ⇒ cũng không có câu trạng thái nào",
    );
    rong.unmount();
  });

  it("HINH THUC (D2): thanh trên khai `grid-row` (`.ed` ba track) + LUẬT ↔ CLASS của nút duyệt và câu trạng thái", () => {
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi([doan(0, 0, 2, "câu 1"), doan(1, 2, 4, "câu 2")]),
        dangDuyet: true,
        loiDuyet: "404: transcript 3 không tồn tại",
        cauLoiThoi: "bản dịch đã lỗi thời so với bản ghi",
      }),
    );

    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const coTrongDom = lopTrongDom(container);

    // (a) QUAN HE LUAT ↔ CLASS (hai chieu): mot `className` trong TSX khong ve gi ca.
    for (const ten of ["ed__thanh", "ed__trang-thai", "lenh--duyet", "lenh__tin"]) {
      assert.ok(
        coTrongDom.has(ten),
        `lop \`${ten}\` phai co THAT trong DOM; do duoc ${JSON.stringify([...coTrongDom].filter((t) => t.startsWith("ed") || t.startsWith("lenh")).sort())}`,
      );
      const khai = khaiBaoCua(appCss, `.${ten}`);
      assert.ok(khai.size > 0, `phai co LUAT \`.${ten}\` trong app.css (co khai bao THANG CUOC)`);
    }

    // (b) LUOI `.ed` (ERRATA #31 muc 1): thanh tren la CON THU HAI ⇒ phai khai them track VA vi tri
    //     cho TUNG con. Khong ghim NGUYEN VAN danh sach track (ghim the la dong bang so luong track).
    const trackEd = (khaiBaoCua(appCss, ".ed").get("grid-template-rows") ?? "")
      .split(/\s+/)
      .filter((t) => t !== "");
    assert.ok(
      trackEd.length >= 3,
      `\`.ed\` phai khai DU track cho BA con (cau loi thoi + thanh tren + khung danh sach); do duoc ${JSON.stringify(trackEd)}`,
    );
    assert.equal(khaiBaoCua(appCss, ".ed__thanh").get("grid-row"), "2", "thanh tren nam track `auto` rieng");
    assert.equal(khaiBaoCua(appCss, ".ed__khung").get("grid-row"), "3", "khung danh sach van o track CUOI (cho cuon)");
    assert.equal(khaiBaoCua(appCss, ".ed__loi-thoi").get("grid-row"), "1");

    // (c) CHU: hai cau cua D2 la CHU that, va cau loi la NGUYEN VAN `ApiError.message`.
    assert.equal(chu(container, '[data-testid="dang-duyet"]'), "đang duyệt…");
    assert.equal(
      chu(container, '[data-testid="loi-duyet"]'),
      "404: transcript 3 không tồn tại",
      "câu lỗi phải là NGUYÊN VĂN `ApiError.message` (`<status>: <detail>`) của đường lỗi DUY NHẤT "
      + "mà route `approve` có (`_require_transcript` ⇒ 404, `routes_transcripts.py`)",
    );
    assert.equal(chu(container, '[data-testid="trang-thai-ban-ghi"]'), "trạng thái: draft");

    assert.deepEqual(tiengOn, [], "hinh thuc D2 cua man Bien tap khong duoc sinh tieng on console");
    unmount();
  });

  it("HINH THUC (D2): MOI con TRỰC TIẾP của `.ed` khai `grid-row`, và SỐ con ≤ SỐ track đã khai", () => {
    // DO DUOC TRUOC (`I5` cua review D2): them mot CON THU TU vao `.ed` (0 luat, 0 `grid-row`) cho
    // **0 bai do**. Moi bai ghim truoc do chi kiem mot DANH SACH TEN LOP viet cung, nen mot con
    // CHUA TUNG CO TEN trong danh sach do di qua tu do — dung lop loi ERRATA #31 muc 1 (da sai
    // HAI lan that: `.shell`, `.cmp`). Bai nay ghim QUAN HE con↔track, khong ghim danh sach ten.
    const { container, unmount } = render(
      taoPhanTu(EditScreen, {
        transcript: banGhi([doan(0, 0, 2, "câu 1"), doan(1, 2, 4, "câu 2")]),
        cauLoiThoi: "bản dịch đã lỗi thời so với bản ghi",
      }),
    );
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");

    const conCuaEd = [...container.querySelectorAll(".ed > *")].map(
      (el) => (el.getAttribute("class") ?? "").split(/\s+/)[0] ?? "",
    );
    assert.ok(
      conCuaEd.length >= 2,
      `\`.ed\` phai co it nhat hai con de phep ghim co nghia; do duoc ${JSON.stringify(conCuaEd)}`,
    );
    for (const ten of conCuaEd) {
      const khai = khaiBaoCua(appCss, `.${ten}`).get("grid-row");
      assert.ok(
        khai !== undefined,
        `con \`.${ten}\` của \`.ed\` phải khai \`grid-row\` TƯỜNG MINH (ERRATA #31 mục 1); `
        + `con đọc được từ DOM: ${JSON.stringify(conCuaEd)}`,
      );
    }
    const trackEd = (khaiBaoCua(appCss, ".ed").get("grid-template-rows") ?? "")
      .split(/\s+/)
      .filter((t) => t !== "");
    assert.ok(
      conCuaEd.length <= trackEd.length,
      `\`.ed\` khai ${trackEd.length} track nhưng có ${conCuaEd.length} con — thêm một con vào một `
      + `lưới cố định là một thay đổi BỐ CỤC (ERRATA #31 mục 1): ${JSON.stringify(conCuaEd)}`,
    );

    assert.deepEqual(tiengOn, [], "khoi luoi cua .ed khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 DUYET: nút `duyệt` VÔ HIỆU khi bản ghi đã `reviewed` (không mời một lệnh không đổi gì)", () => {
    // DO DUOC TRUOC (`B-2` cua review D2): `duyet-ban-ghi` KHONG co `disabled`, va KHONG bai nao
    // khang dinh nut hien/vo hieu theo `status` ⇒ mutant them `disabled` cho **0 bai do**.
    // ⚠️ Vi sao `disabled` ma khong AN nut: cau `trạng thái: reviewed` ngay canh da noi su that
    // bang CHU (§7), con mot nut bam duoc ma khong doi gi la mot affordance NOI DOI.
    function kiem(status: Transcript["status"], voHieu: boolean): void {
      const { container, unmount } = render(
        taoPhanTu(EditScreen, {
          transcript: { ...banGhi([doan(0, 0, 2, "câu 1")]), status },
        }),
      );
      assert.equal(chu(container, '[data-testid="trang-thai-ban-ghi"]'), `trạng thái: ${status}`);
      const nut = phanTu(container, '[data-testid="duyet-ban-ghi"]') as HTMLButtonElement;
      assert.equal(nut.tagName, "BUTTON", "nút duyệt vẫn phải là một NÚT thật");
      assert.equal(
        nut.disabled,
        voHieu,
        `status=${status} ⇒ nút duyệt phải ${voHieu ? "VÔ HIỆU" : "bật"}: backend chỉ UPDATE `
        + "`status` (không đụng `version`), nên bấm lại một bản ghi đã `reviewed` không đổi gì",
      );
      unmount();
    }
    kiem("draft", false);
    kiem("translated", false);
    kiem("reviewed", true);
  });
});
