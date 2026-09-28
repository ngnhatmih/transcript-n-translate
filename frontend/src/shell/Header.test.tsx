/**
 * Test `<Header/>` THAT trong jsdom — **bộ chọn CHẾ ĐỘ** (Task W1).
 *
 * VI SAO TỆP NÀY TỒN TẠI (và vì sao nó là tệp MỚI, không phải tệp được sửa): trước W1,
 * `Header` không có `radio` nào, nên `mode` của reducer **không có đường nào đổi** và hai
 * màn Đối chiếu / Thuật ngữ **không tới được** trong app thật (ERRATA #32). Tệp này ghim
 * ĐÚNG cái control đó ở tầng component; bài "đổi chế độ ⇒ màn đổi theo" nằm ở
 * `App.test.tsx` (nó cần `dispatch` của reducer, tức cần cả shell).
 *
 * ## Ba điều tệp này ghim, và vì sao không phải một
 *
 *  1. **`role="radiogroup"` + BA `input type="radio"` THẬT.** Không phải `div` + `role`:
 *     `input` native mới có hành vi bàn phím (mũi tên đổi lựa chọn trong cùng `name`), và
 *     spec UI §12.5 ĐÒI bàn phím làm được. Một `div role="radio"` sẽ xanh ở bài "có radio"
 *     nhưng không có bàn phím native — nên bài này khẳng định cả `tagName === "INPUT"`.
 *  2. **TÊN ĐỌC ĐƯỢC** của từng radio (`getByRole(..., {name})`) — đây chính là cách
 *     Task 12 tìm control (`findByRole("radio", {name:/thuật ngữ/i})`); nếu tên không gắn
 *     với `input` thì Task 12 vẫn không chạy được dù radio đã tồn tại.
 *  3. **`checked` theo PROP `mode`, và `onChange` BÁO VỀ `onModeChange`.** Header là
 *     component ĐIỀU KHIỂN: nó không giữ bản sao thứ hai của `UiState.mode` (cùng lý do
 *     `Transport` không giữ bản sao của `playing`).
 *
 * ## LUẬT DOM (ERRATA #9 muc 1/6): tệp này TỰ CHỨA
 *
 *  - MOI hook đặt/trả global nằm TRONG `describe()` (hook cấp TỆP bị kéo lên GỐC cả lượt
 *    dưới `--test-isolation=none`).
 *  - `console.error`/`console.warn` bị TẠM THAY để bắt tiếng ồn và TRẢ LẠI trong `after`.
 *  - KHÔNG đưa node DOM sống vào `assert` (218 697 ms rồi OOM — ERRATA #14 muc 3).
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import { setupDom, teardownDom } from "../../test/dom.ts";

/** Mô tả một giá trị mà KHÔNG gọi sâu vào nó (an toàn với node DOM đã bị close). */
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
let getByRole: (container: HTMLElement, role: string, options?: { name?: RegExp | string }) => Element;
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let Header: (props: unknown) => unknown;
/** Module `react` THAT — cần cho hook `useState` của component chủ sở hữu trong một bài test. */
let react: any;

/** Ba chế độ của `state/reducer.ts::Mode` — chép ra đây vì tệp này không import reducer. */
const BA_CHE_DO = ["Biên tập", "Đối chiếu", "Thuật ngữ"];

/** Tất cả `input[type=radio]` theo ĐÚNG thứ tự DOM. */
function cacRadio(container: HTMLElement): HTMLInputElement[] {
  return [...container.querySelectorAll('input[type="radio"]')] as HTMLInputElement[];
}

/** Nhãn HIỂN THỊ của một radio: `<label for=…>` là thứ người dùng đọc và bấm được. */
function nhanCua(container: HTMLElement, radio: HTMLInputElement): string {
  const label = container.querySelector(`label[for="${radio.id}"]`);
  assert.ok(label !== null, `radio "${radio.value}" khong co <label for> ⇒ nhan khong bam duoc`);
  return label.textContent ?? "";
}

describe("Header: bo chon CHE DO (Task W1)", () => {
  before(async () => {
    // Chuẩn hoá TRƯỚC khi cài: không dựa vào việc tệp khác đã trả global hay chưa.
    teardownDom();
    // Origin chỉ để `fetch` tương đối resolve được — tệp này KHÔNG gọi mạng.
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    fireEvent = api.fireEvent;
    getByRole = api.getByRole;
    cleanup = api.cleanup;
    const reactModule: any = await import("react");
    react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const man: any = await import("./Header.tsx");
    Header = man.Header;

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

  it("radiogroup + BA `input type=\"radio\"` THAT (khong phai `div` + `role`)", () => {
    const { container, unmount } = render(
      taoPhanTu(Header, { status: null, mode: "edit", onModeChange: () => {} }),
    );

    const nhom = container.querySelectorAll('[role="radiogroup"]');
    assert.equal(nhom.length, 1, "phai co DUNG MOT nhom chon che do");

    const radios = cacRadio(container);
    assert.equal(radios.length, 3, "spec UI §3 co BA che do: Bien tap / Doi chieu / Thuat ngu");
    for (const radio of radios) {
      // `input` THAT ⇒ bàn phím native dùng được. `div` + `role="radio"` sẽ trượt dòng này.
      assert.equal(radio.tagName, "INPUT", "che do phai la input THAT, khong phai div + role");
    }
    assert.equal(
      container.querySelectorAll('div[role="radio"], span[role="radio"]').length,
      0,
      "khong duoc co radio GIA (div/span + role) ben canh radio that",
    );

    // TÊN ĐỌC ĐƯỢC — chính cách Task 12 tìm control này.
    for (const ten of BA_CHE_DO) {
      const tim = getByRole(container, "radio", { name: new RegExp(ten, "i") });
      assert.equal(tim.tagName, "INPUT", `radio "${ten}" phai tim duoc bang VAI TRO + TEN`);
    }
    // Va nhan HIEN THI dung ba chu cua spec (nguoi dung doc chu, khong doc `value`).
    assert.deepEqual(cacRadio(container).map((r) => nhanCua(container, r)), BA_CHE_DO);

    assert.deepEqual(tiengOn, [], "render Header khong duoc sinh tieng on console");
    unmount();
  });

  it("`checked` di theo PROP `mode` (ba che do, khong hard-code mot cai)", () => {
    for (const [mode, chiSo] of [["edit", 0], ["compare", 1], ["glossary", 2]] as const) {
      const { container, unmount } = render(
        taoPhanTu(Header, { status: null, mode, onModeChange: () => {} }),
      );
      const radios = cacRadio(container);
      assert.equal(
        radios.findIndex((r) => r.checked),
        chiSo,
        `mode "${mode}" ⇒ radio thu ${chiSo} phai duoc chon; do duoc ${JSON.stringify(radios.map((r) => r.checked))}`,
      );
      unmount();
    }
    assert.deepEqual(tiengOn, [], "doi `mode` khong duoc sinh tieng on console");
  });

  it("bam mot che do ⇒ BAO VE `onModeChange` (va KHONG tu giu state rieng)", () => {
    const daBao: string[] = [];

    // (a) VONG DI KIN: mot component giu `mode` (giong `App` voi `ui.mode`) ⇒ bam xong
    //     prop doi, va lua chon HIEN THI di theo. Day la duong THAT cua app.
    const ChuSoHuu = (): unknown => {
      const [mode, datMode] = react.useState("edit");
      return react.createElement(Header, {
        status: null,
        mode,
        onModeChange: (moi: string): void => {
          daBao.push(moi);
          datMode(moi);
        },
      });
    };
    const vong = render(taoPhanTu(ChuSoHuu));
    const radiosVong = cacRadio(vong.container);
    assert.equal(radiosVong[0].checked, true, "bat dau o che do 'edit'");

    fireEvent.click(radiosVong[2]);
    assert.deepEqual(daBao, ["glossary"], "bam 'Thuật ngữ' phai bao DUNG che do do len tren");
    assert.equal(radiosVong[2].checked, true, "prop doi ⇒ lua chon hien thi phai di theo");
    assert.equal(radiosVong[0].checked, false);

    fireEvent.click(radiosVong[0]);
    assert.deepEqual(daBao, ["glossary", "edit"]);
    assert.equal(radiosVong[0].checked, true);
    vong.unmount();

    // (b) Component ĐIỀU KHIỂN: `mode` la PROP, nen khi prop KHONG doi thi lua chon hien thi
    //     KHONG duoc tu nhay. Mot ban giu state cuc bo se truot dong nay — va do chinh la
    //     nguon su that thu hai ma W1 phai tranh.
    const coDinh = render(
      taoPhanTu(Header, { status: null, mode: "edit", onModeChange: () => {} }),
    );
    const radiosCoDinh = cacRadio(coDinh.container);
    fireEvent.click(radiosCoDinh[2]);
    assert.equal(radiosCoDinh[0].checked, true, "prop khong doi thi lua chon hien thi khong doi");
    assert.equal(radiosCoDinh[2].checked, false, "Header KHONG duoc tu giu mot ban sao cua `mode`");
    coDinh.unmount();

    assert.deepEqual(tiengOn, [], "bam che do khong duoc sinh tieng on console");
  });

  it("dai TRANG THAI cua Task 10 duoc GIU NGUYEN khi them bo chon che do", () => {
    // W1 them vao `Header`; no KHONG duoc lam roi dai trang thai ma Task 10 vua noi vao.
    const { container, unmount } = render(
      taoPhanTu(Header, {
        status: { queue_depth: 0, running: [], current_phase: null, phase_switches: 0, vram: null, ollama: "unknown" },
        mode: "edit",
        onModeChange: () => {},
      }),
    );

    const head = container.querySelector(".shell__head");
    assert.ok(head !== null, "Header phai render `.shell__head`");
    const chu = head.textContent ?? "";
    assert.ok(chu.includes("PHÒNG THU BIÊN TẬP"), "ten ban lam viec phai con");
    assert.ok(chu.includes("chưa đo được"), "dai trang thai (§4.8) phai con trong header");
    assert.equal(
      container.querySelector(".stt")?.getAttribute("data-ollama"),
      "unknown",
      "dai trang thai phai mang dung trang thai nhan duoc",
    );

    assert.deepEqual(tiengOn, [], "render day du khong duoc sinh tieng on console");
    unmount();
  });
});
