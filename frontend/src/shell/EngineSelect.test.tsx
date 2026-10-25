/**
 * Test `<EngineSelect/>` THAT trong jsdom (spec UI §3 — dropdown engine o header).
 *
 * Tieu chi cua Task 10: dropdown CHI liet ke engine `capabilities.available === true`,
 * va `available` phai DOC THANG tu `/api/registry` — KHONG duoc suy lai tu
 * `runtime`/`model_ref` o client (Global Constraints dong 25 + ERRATA #30 muc 4:
 * suy lai la tao NGUON SU THAT THU HAI cho cung mot dai luong).
 *
 * Vi sao jsdom: jsdom KHONG cho bang chung HINH THUC — no KHONG co layout, KHONG co CSS that.
 * ⇒ Tep nay do duoc HANH VI (option nao co trong DOM, chu nao, thuoc tinh nao), KHONG do duoc
 * HINH (dropdown cao bao nhieu, option xep ra sao).
 *
 * ⚠️ DINH CHINH (Task 12, ERRATA #40 + #46 muc 5): cau cu o day noi *"trinh duyet THAT BAT KHA
 * o moi truong nay"* — **SAI vi QUA RONG**. Menh de dung la: *"Chromium khong mo duoc DƯỚI
 * CÁC CHẾ ĐỘ SANDBOX HẠN CHẾ"*. ⇒ **Bang chung HINH THUC nam o tang Chrome that:
 * `frontend/e2e/`.** ⚠️ Tang do CHUA duoc chay trong luot Task 12 (xem bao cao).
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
 * ⚠️ KHONG co `@testing-library/user-event`, KHONG co `jest-dom`, KHONG co `vitest`
 * trong repo (`package.json`: chi `jsdom` + `@testing-library/react`) ⇒ dung `fireEvent`
 * xuat tu `@testing-library/react` va `node:assert/strict`.
 *
 * ⚠️ `npm run typecheck` KHONG kiem tep `.test.tsx` (bat bien: 0 tep `.test.` trong
 * `tsc --listFiles` — ERRATA #14 muc 1) ⇒ loi kieu trong tep nay CHI lo ra luc chay.
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import type { EngineSpec } from "../api/types.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

const consoleGoc = { error: console.error, warn: console.warn };
const tiengOn: string[] = [];

let render: (ui: unknown) => { container: HTMLElement; unmount: () => void };
let fireEvent: { change: (el: Element, init?: unknown) => void };
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let EngineSelect: (props: unknown) => unknown;

/**
 * Mot spec theo DUNG 9 khoa cua `EngineSpec`.
 *
 * `available` VANG MAT duoc phep va la su that cua backend: `_mark_availability` chi ghi
 * khoa nay cho engine `kind == "mt"` ⇒ **4 spec ASR khong co khoa `available`**
 * (ERRATA #2 muc 3). Nen tham so thu tu `available?: boolean` chu khong phai `false`.
 */
function spec(
  id: string,
  label: string,
  runtime: "inprocess" | "ollama",
  available?: boolean,
  modelRef = "model/ref",
  kind: "asr" | "mt" = "mt",
): EngineSpec {
  const capabilities: EngineSpec["capabilities"] = {};
  if (available !== undefined) capabilities.available = available;
  return {
    id,
    label,
    kind,
    runtime,
    model_ref: modelRef,
    vram_mb: 0,
    langs: ["zh"],
    capabilities,
    opts: {},
  };
}

/** `textContent` cua phan tu DAU TIEN khop `chon` — khong hoi ca DOM. */
function chu(goc: HTMLElement, chon: string): string {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.textContent ?? "";
}

/**
 * Khang dinh KHONG co phan tu nao khop `chon` — DEM, khong so sanh NODE.
 *
 * ⚠️ DO DUOC (ERRATA #14 muc 3 / #15 muc 1: 218 697 ms roi OOM): `assert.equal(<node DOM
 * song>, null)` o nhanh DO khien `assert` dinh dang CA cay fiber trong thong diep loi.
 * ⇒ moi khang dinh "khong co phan tu" o tep nay dem SO LUONG (mot con so).
 */
function khongCo(goc: HTMLElement, chon: string, msg: string): void {
  assert.equal(goc.querySelectorAll(chon).length, 0, msg);
}

/** Nhan cua MOI `option` dang co, theo thu tu trong DOM. */
function nhanOption(goc: HTMLElement): string[] {
  return [...goc.querySelectorAll("option")].map((o) => o.textContent ?? "");
}

describe("EngineSelect: dropdown CHI liet ke engine phuc vu duoc NGAY BAY GIO", () => {
  before(async () => {
    // Chuan hoa TRUOC khi cai: khong dua vao viec tep khac da tra global hay chua.
    teardownDom();
    // Origin chi de `fetch` tuong doi resolve duoc; tep nay KHONG goi mang nao
    // (du lieu vao qua PROP — cung khuon voi CompareScreen/GlossaryScreen).
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const man: any = await import("./EngineSelect.tsx");
    EngineSelect = man.EngineSelect;

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

  // `cleanup` cua Testing Library go DOM da render — khong cham vao global nao.
  afterEach(() => {
    cleanup();
  });

  after(() => {
    console.error = consoleGoc.error;
    console.warn = consoleGoc.warn;
    teardownDom();
  });

  it("liet ke engine available === true va BO engine available === false", () => {
    const { container } = render(taoPhanTu(EngineSelect, {
      specs: [
        spec("opus-mt", "OPUS-MT", "inprocess", true),
        spec("qwen2.5-3b", "Qwen 2.5 3B", "ollama", false),
      ],
      value: "opus-mt",
      onValueChange: () => {},
    }));

    assert.deepEqual(nhanOption(container), ["OPUS-MT"],
      "dropdown phai co DUNG engine available === true; engine available === false (Qwen) bi loai");
    assert.deepEqual(tiengOn, [], "render dropdown khong duoc sinh tieng on console");
  });

  it("available DOC THANG tu registry: KHONG suy tu runtime/model_ref (CA HAI chieu)", () => {
    // Chieu 1: `runtime === "inprocess"` nhung registry noi `available === false`
    //   (model chua pull) ⇒ KHONG duoc liet ke. Suy tu runtime se liet ke SAU.
    // Chieu 2: `runtime === "ollama"` nhung registry noi `available === true`
    //   (tien trinh song VA model da pull) ⇒ PHAI duoc liet ke. Suy tu runtime se BO SAU.
    const { container } = render(taoPhanTu(EngineSelect, {
      specs: [
        spec("opus-mt", "OPUS-MT", "inprocess", false, "Helsinki-NLP/opus-mt-zh-vi"),
        spec("qwen2.5-7b", "Qwen 2.5 7B", "ollama", true, "qwen2.5:7b"),
      ],
      value: "",
      onValueChange: () => {},
    }));

    assert.deepEqual(nhanOption(container), ["Qwen 2.5 7B"],
      "chi `capabilities.available` quyet dinh; `runtime`/`model_ref` KHONG duoc suy lai o client");
  });

  it("engine KHONG co khoa `available` (ASR) khong duoc liet ke — available chi co tren kind mt", () => {
    const { container } = render(taoPhanTu(EngineSelect, {
      specs: [
        spec("faster-whisper-large", "Faster Whisper Large", "inprocess", undefined, "large-v3", "asr"),
        spec("opus-mt", "OPUS-MT", "inprocess", true),
      ],
      value: "opus-mt",
      onValueChange: () => {},
    }));

    assert.deepEqual(nhanOption(container), ["OPUS-MT"],
      "thieu khoa `available` KHONG phai la `available` ⇒ khong duoc doan la dung duoc");
  });

  it("khong co engine nao dung duoc thi NOI RA va VO HIEU hoa, khong hien mot option trong", () => {
    const { container } = render(taoPhanTu(EngineSelect, {
      specs: [spec("qwen2.5-3b", "Qwen 2.5 3B", "ollama", false)],
      value: "",
      onValueChange: () => {},
    }));

    assert.deepEqual(nhanOption(container), ["không có engine nào dùng được"],
      "khong co engine nao thi phai NOI RA, khong duoc de dropdown rong im lang");
    const chon = container.querySelector(".eng__chon") as HTMLSelectElement | null;
    assert.ok(chon !== null, "phai co the `select`");
    assert.equal(chon.disabled, true,
      "khong co lua chon nao that thi o chon phai VO HIEU — mot o chon duoc ma khong co gi la mot loi noi doi");
  });

  it("chon mot engine thi PHAT RA id cua no", () => {
    const nhan: string[] = [];
    const { container } = render(taoPhanTu(EngineSelect, {
      specs: [
        spec("opus-mt", "OPUS-MT", "inprocess", true),
        spec("qwen2.5-7b", "Qwen 2.5 7B", "ollama", true),
      ],
      value: "opus-mt",
      onValueChange: (id: string) => nhan.push(id),
    }));

    // Gia tri hien hanh la `value` DIEU KHIEN tu ngoai: doc lai tu DOM de chung minh
    // prop da tới that, khong phai mot thuoc tinh bia them.
    assert.equal((container.querySelector(".eng__chon") as HTMLSelectElement).value, "opus-mt",
      "`value` phai duoc dieu khien that tu prop");

    fireEvent.change(container.querySelector(".eng__chon") as Element, {
      target: { value: "qwen2.5-7b" },
    });

    assert.deepEqual(nhan, ["qwen2.5-7b"],
      "chon engine phai phat ra DUNG id cua no, khong duoc nuot im lang");
  });

  it("HINH THUC: LUAT CSS cua dropdown CO THAT trong `app.css`", () => {
    // ERRATA #15 muc 3 (do duoc HAI CHIEU o Task 6): mot test chi khang dinh `className`
    // van XANH khi luat CSS bi xoa. Cach re nhat de ghim luat: DOC tep CSS.
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const moc = "§4.8 Trạng thái Ollama (Task 10)";
    const viTri = appCss.indexOf(moc);
    assert.ok(viTri > 0, "app.css phai co KHOI LUAT cua Task 10, khong chi co class trong TSX");
    // ⚠️ Cat khối tới MỐC `/* ──` KẾ TIẾP, KHONG tới hết tệp (Minor #3b): luật của task SAU
    // them vao cuoi tệp sẽ tự chui vào "khối Task 10" và bị đem đi kiểm token.
    const mocKe = appCss.indexOf("/* ──", viTri + 1);
    const khoi = mocKe === -1 ? appCss.slice(viTri) : appCss.slice(viTri, mocKe);

    assert.ok(khoi.includes(".eng__nhan {"), "app.css thieu luat `.eng__nhan`");
    assert.ok(khoi.includes(".eng__chon {"), "app.css thieu luat `.eng__chon`");
    assert.match(khoi, /\.eng__chon \{[^}]*font-family: var\(--font-mono\)/,
      "o chon engine phai la MONO (ten engine la ma may, khong phai cau van)");
    assert.match(khoi, /\.eng__chon:disabled \{[^}]*color: var\(--ink-2\)/,
      "o chon VO HIEU phai co luat ve that, khong chi co thuoc tinh `disabled`");
  });
});
