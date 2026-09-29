/**
 * Test HÀNH VI THẬT của `useShortcuts` — hook này là chỗ DUY NHẤT gắn `keydown` cho cả app.
 *
 * Vì sao phải có tệp riêng (không chỉ test `resolveKey`): `resolveKey` là hàm THUẦN, nên nó
 * KHÔNG chứng minh được ba mệnh đề của hook:
 *  1. **GUARD Ô NHẬP có HAI VẾ** — `suKien.target` VÀ `document.activeElement`. Một bài chỉ phát
 *     phím TRÊN `textarea` chỉ chạm vế `target` (ERRATA #45 mục 1(b): bỏ nửa `activeElement` cho
 *     **0 bài đỏ** ở vòng D1). Bài ở đây dựng một `input` THẬT trong cây, `focus()` nó, rồi phát
 *     phím từ `document.body` — vế `target` nói "không phải ô nhập", chỉ `activeElement` mới cứu
 *     được. Mutant `P2` (bỏ lần đọc `activeElement`) là bài này ĐỎ.
 *  2. **MỘT listener, ở `document`, và nó được DỌN** — ba vế đo được: số listener `keydown` đang
 *     sống trên `document` = 1; một sự kiện phát ra Ở `window` KHÔNG tới được handler (tức
 *     listener KHÔNG nằm ở `window`); và sau `unmount` thì handler không được gọi nữa.
 *  3. **`preventDefault` đúng chỗ**: phím ĐÃ XỬ LÝ thì chặn mặc định (Space không được CUỘN
 *     trang), phím KHÔNG xử lý và phím TRONG Ô NHẬP thì KHÔNG chặn (gõ dấu cách vào phụ đề vẫn
 *     phải ra dấu cách).
 *
 * Không mock module nào. `setupDom` phải chạy TRƯỚC khi import `@testing-library/react` và hook
 * (React đọc `window`/`document` lúc nạp) ⇒ hai import đó là `await import(...)` trong `before`.
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import { setupDom, teardownDom } from "../../test/dom.ts";
import type { KeyAction } from "./shortcuts.ts";

let render: (el: unknown) => { container: HTMLElement; rerender: (el: unknown) => void; unmount: () => void };
let fireEvent: (el: unknown, init: Record<string, unknown>) => boolean;
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let useShortcuts: (xuLy: (hd: KeyAction) => void, mode: "edit" | "compare" | "glossary") => void;

/** Tiếng ồn console của RIÊNG tệp này — mọi bài đều khẳng định nó rỗng. */
const tiengOn: string[] = [];
const consoleGoc = { error: console.error, warn: console.warn };

function mo(x: unknown): string {
  if (x instanceof Error) return `${x.name}: ${x.message}`;
  if (typeof x === "string") return x;
  return String(x);
}

/**
 * Khung tối thiểu: gọi hook, và (tuỳ bài) đặt MỘT ô nhập THẬT trong cây.
 *
 * ⚠️ Ô nhập phải nằm trong CÂY ĐÃ RENDER, không phải một `document.createElement` rời: mệnh đề
 * đang đo là "hook bỏ qua phím khi người dùng đang gõ trong ô nhập CỦA APP".
 */
function Khung({
  xuLy,
  mode,
  coONhap = false,
}: {
  xuLy: (hd: KeyAction) => void;
  mode: "edit" | "compare" | "glossary";
  coONhap?: boolean;
}): unknown {
  useShortcuts(xuLy, mode);
  return coONhap ? taoPhanTu("input", { "data-testid": "o-nhap" }) : taoPhanTu("div", null);
}

/**
 * Khung có **CONTROL NATIVE THẬT**: `<button>`, `<a href>` (đúng hai loại mà app dùng — bảng
 * phím tắt có nút `đóng`, `Transport` có ba nút XUẤT là `<a download>`) và một `<div tabindex>`
 * **KHÔNG phải** control (vế ngược: phím nóng vẫn phải chạy khi tiêu điểm ở một phần tử khác).
 */
function KhungControl({
  xuLy,
  mode,
}: {
  xuLy: (hd: KeyAction) => void;
  mode: "edit" | "compare" | "glossary";
}): unknown {
  useShortcuts(xuLy, mode);
  return taoPhanTu(
    "div",
    null,
    taoPhanTu("button", { type: "button", "data-testid": "nut" }, "nút"),
    taoPhanTu("a", { href: "#x", "data-testid": "lien-ket" }, "liên kết"),
    taoPhanTu("div", { tabIndex: 0, "data-testid": "khong-phai-control" }, "khung"),
  );
}

/** Đếm số listener `keydown` đang sống trên `document` (thêm trừ bớt). */
function demListener(): { song: () => number; tra: () => void } {
  const themGoc = document.addEventListener;
  const botGoc = document.removeEventListener;
  let them = 0;
  let bot = 0;
  document.addEventListener = function (this: Document, loai: string, ...rest: unknown[]): void {
    if (loai === "keydown") them += 1;
    (themGoc as (...a: unknown[]) => void).call(this, loai, ...rest);
  } as typeof document.addEventListener;
  document.removeEventListener = function (this: Document, loai: string, ...rest: unknown[]): void {
    if (loai === "keydown") bot += 1;
    (botGoc as (...a: unknown[]) => void).call(this, loai, ...rest);
  } as typeof document.removeEventListener;
  return {
    song: () => them - bot,
    tra: () => {
      document.addEventListener = themGoc;
      document.removeEventListener = botGoc;
    },
  };
}

/** Một `keydown` THẬT phát ra từ `dich`, trả về chính sự kiện để đọc `defaultPrevented`. */
function bamPhim(dich: EventTarget, init: Record<string, unknown>): KeyboardEvent {
  const suKien = new window.KeyboardEvent("keydown", {
    bubbles: true,
    cancelable: true,
    ...init,
  });
  dich.dispatchEvent(suKien);
  return suKien;
}

describe("useShortcuts: MỘT listener ở `document`, guard HAI VẾ, và dọn được", () => {
  before(async () => {
    teardownDom();
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl : rtl.default;
    render = api.render;
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const hook: any = await import("./useShortcuts.ts");
    useShortcuts = hook.useShortcuts;

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

  it("GUARD Ô NHẬP hai vế: `target` LẪN `document.activeElement` (và vế NGƯỢC phải chạy)", () => {
    const daGoi: KeyAction[] = [];
    const { container, unmount } = render(
      taoPhanTu(Khung, { xuLy: (hd: KeyAction) => daGoi.push(hd), mode: "edit", coONhap: true }),
    );
    const o = container.querySelector('[data-testid="o-nhap"]') as HTMLInputElement;
    assert.ok(o !== null, "ô nhập phải có THẬT trong cây đã render");

    // (1) VẾ NGƯỢC (ĐỐI CHỨNG DƯƠNG): tiêu điểm NGOÀI ô ⇒ handler PHẢI được gọi. Thiếu vế này thì
    //     một hook CHẾT cũng "qua" được vế âm bên dưới (ERRATA #45 mục 1(b): một chiều là không đủ).
    o.blur();
    bamPhim(document.body, { key: " " });
    assert.deepEqual(daGoi, [{ type: "togglePlay" }], "phím ngoài ô nhập phải tới được handler");

    // (2) VẾ ÂM, NỬA `suKien.target`: phím phát ra TỪ CHÍNH ô nhập.
    daGoi.length = 0;
    o.focus();
    bamPhim(o, { key: " " });
    assert.deepEqual(daGoi, [], "phím gõ TRONG ô nhập KHÔNG được tới handler (nửa `target`)");

    // (3) VẾ ÂM, NỬA `document.activeElement`: phím phát ra NGOÀI ô (`target` = body) mà tiêu điểm
    //     Ở TRONG ô. Đây là ca mà vòng D1 khai là "không có gì làm nó sai được" — mutant `P2`
    //     (bỏ lần đọc `activeElement`) là bài này ĐỎ.
    assert.equal(document.activeElement, o, "ca này chỉ có nghĩa khi tiêu điểm Ở TRONG ô nhập");
    daGoi.length = 0;
    bamPhim(document.body, { key: " " });
    assert.deepEqual(daGoi, [], "tiêu điểm trong ô nhập ⇒ phím từ body KHÔNG được tới handler");

    // (4) Và phím KHÔNG có trong bảng thì không tới handler ở đâu cả.
    o.blur();
    daGoi.length = 0;
    bamPhim(document.body, { key: "q" });
    assert.deepEqual(daGoi, [], "phím không có trong bảng ⇒ không có hành động nào");

    assert.deepEqual(tiengOn, [], "guard ô nhập không được sinh tiếng ồn console");
    unmount();
  });

  it("`preventDefault` ĐÚNG CHỖ: phím đã xử lý thì chặn, phím trong ô nhập thì KHÔNG", () => {
    const daGoi: KeyAction[] = [];
    const { container, unmount } = render(
      taoPhanTu(Khung, { xuLy: (hd: KeyAction) => daGoi.push(hd), mode: "edit", coONhap: true }),
    );
    const o = container.querySelector('[data-testid="o-nhap"]') as HTMLInputElement;

    // Space CUỘN TRANG theo mặc định của trình duyệt — một phím nóng đã xử lý mà không chặn mặc
    // định là một app vừa phát audio vừa nhảy trang.
    o.blur();
    const daXuLy = bamPhim(document.body, { key: " " });
    assert.equal(daXuLy.defaultPrevented, true, "phím ĐÃ XỬ LÝ phải `preventDefault`");
    // Vế ngược: phím không có trong bảng thì KHÔNG được chặn mặc định (nếu không, app nuốt phím
    // của trình duyệt/extension mà không làm gì).
    const khongXuLy = bamPhim(document.body, { key: "q" });
    assert.equal(khongXuLy.defaultPrevented, false, "phím KHÔNG xử lý thì không được chặn mặc định");
    // Và trong Ô NHẬP: dấu cách phải là DẤU CÁCH của phụ đề, không bị chặn.
    o.focus();
    const trongO = bamPhim(o, { key: " " });
    assert.equal(trongO.defaultPrevented, false, "gõ dấu cách trong ô sửa KHÔNG được bị chặn");

    assert.deepEqual(tiengOn, [], "preventDefault khong duoc sinh tieng on console");
    unmount();
  });

  it("CONTROL NATIVE đang có tiêu điểm: `Enter`/`Space` KHÔNG bị cướp và KHÔNG bị `preventDefault` (I-1)", () => {
    const daGoi: KeyAction[] = [];
    const { container, unmount } = render(
      taoPhanTu(KhungControl, { xuLy: (hd: KeyAction) => daGoi.push(hd), mode: "edit" }),
    );
    const nut = container.querySelector('[data-testid="nut"]') as HTMLButtonElement;
    const lienKet = container.querySelector('[data-testid="lien-ket"]') as HTMLAnchorElement;
    const khung = container.querySelector('[data-testid="khong-phai-control"]') as HTMLDivElement;
    assert.ok(nut !== null && lienKet !== null && khung !== null, "khung phải có đủ ba phần tử");

    // (1) `<BUTTON>`: `Enter` và `Space` là phím KÍCH HOẠT của nút (mặc định của trình duyệt).
    //     `preventDefault()` biến `KeyboardEvent.defaultPrevented` thành `true`, và đó CHÍNH LÀ cơ
    //     chế trình duyệt dùng để quyết định có kích hoạt nút hay không ⇒ nút đang có tiêu điểm
    //     (kể cả nút `đóng` của bảng §11.4) bấm bằng bàn phím KHÔNG được.
    nut.focus();
    // ⚠️ BOOLEAN, không `assert.equal(nodeA, nodeB)`: `assert` in node DOM KHÔNG giới hạn độ sâu
    // (ERRATA #14 mục 3: 218 697 ms rồi OOM) — và ở đây nó chỉ ĐỎ khi guard hỏng, tức đúng lúc
    // thông điệp cần đọc được.
    assert.ok(document.activeElement === nut, "ca này chỉ có nghĩa khi tiêu điểm Ở TRÊN nút");
    const eEnter = bamPhim(nut, { key: "Enter" });
    assert.equal(eEnter.defaultPrevented, false, "`Enter` trên <button> KHÔNG được bị chặn mặc định");
    const eSpace = bamPhim(nut, { key: " " });
    assert.equal(eSpace.defaultPrevented, false, "`Space` trên <button> KHÔNG được bị chặn mặc định");
    assert.deepEqual(daGoi, [], "phím KÍCH HOẠT của control native KHÔNG được tới handler của app");

    // (2) `<A HREF>`: `Enter` là phím kích hoạt của liên kết (ba nút XUẤT trong `Transport` là
    //     `<a download>`), nên nó thuộc cùng một lớp.
    lienKet.focus();
    const eLienKet = bamPhim(lienKet, { key: "Enter" });
    assert.equal(eLienKet.defaultPrevented, false, "`Enter` trên <a href> KHÔNG được bị chặn mặc định");
    assert.deepEqual(daGoi, [], "`Enter` trên <a href> KHÔNG được tới handler của app");

    // (2b) 🔴 `Space` thì NGƯỢC LẠI: một liên kết `a[href]` **KHÔNG** được trình duyệt kích hoạt
    //      bằng `Space` (spec HTML: cú kích hoạt của liên kết là `Enter`; `Space` chỉ cuộn trang).
    //      Nếu guard nhường theo MỘT danh sách selector chung cho cả hai phím thì khi tiêu điểm ở
    //      một `<a download>` — đúng BA NÚT XUẤT của `Transport` — phím `Space` toàn cục (phát/dừng)
    //      **IM LẶNG MẤT TÁC DỤNG**. Vế (2) ở trên và vế này phải ĐỎ được với hai mutant NGƯỢC CHIỀU
    //      (nhường quá rộng / quá hẹp) — một vế âm một mình không phân biệt được.
    assert.ok(document.activeElement === lienKet, "ca (2b) chỉ có nghĩa khi tiêu điểm Ở TRÊN liên kết");
    daGoi.length = 0;
    const eLienKetSpace = bamPhim(lienKet, { key: " " });
    assert.deepEqual(
      daGoi,
      [{ type: "togglePlay" }],
      "`Space` trên <a href> PHẢI tới handler của app (liên kết không kích hoạt bằng `Space`)",
    );
    assert.equal(
      eLienKetSpace.defaultPrevented,
      true,
      "`Space` trên <a href> vẫn phải chặn mặc định (cuộn trang) vì app ĐÃ xử lý nó",
    );

    // (3) PHÍM BỔ TRỢ không phải cú kích hoạt của control: `Ctrl+Enter` (hàng "chạy job") vẫn
    //     thuộc về APP dù tiêu điểm đang ở nút. Vế này ghim điều kiện "không có Ctrl/Alt/Meta".
    nut.focus();
    daGoi.length = 0;
    const eCtrl = bamPhim(nut, { key: "Enter", ctrlKey: true });
    assert.deepEqual(daGoi, [{ type: "runJob" }], "`Ctrl+Enter` trên một nút vẫn phải tới handler của app");
    assert.equal(eCtrl.defaultPrevented, true, "`Ctrl+Enter` (phím nóng của app) vẫn phải chặn mặc định");

    // (4) VẾ NGƯỢC (đối chứng dương) — tiêu điểm ở một phần tử KHÔNG phải control: phím nóng PHẢI
    //     chạy y như trước, và phím đã xử lý vẫn phải chặn mặc định. Thiếu vế này thì một hook
    //     "nuốt TẤT CẢ `Enter`/`Space`" cũng qua được hai vế trên.
    khung.focus();
    daGoi.length = 0;
    const eKhung = bamPhim(khung, { key: "Enter" });
    assert.deepEqual(daGoi, [{ type: "startEdit" }], "`Enter` NGOÀI control native vẫn phải mở ô sửa");
    assert.equal(eKhung.defaultPrevented, true, "phím ĐÃ XỬ LÝ (ngoài control) vẫn phải chặn mặc định");

    khung.blur();
    daGoi.length = 0;
    const eBody = bamPhim(document.body, { key: " " });
    assert.deepEqual(daGoi, [{ type: "togglePlay" }], "`Space` ngoài control native vẫn là phát/dừng");
    assert.equal(eBody.defaultPrevented, true, "`Space` ngoài control vẫn phải chặn cuộn trang");

    assert.deepEqual(tiengOn, [], "guard control native không được sinh tiếng ồn console");
    unmount();
  });

  it("MỘT listener `keydown`, ở `document` (KHÔNG ở `window`) — và nó được gỡ khi unmount", () => {
    const dem = demListener();
    try {
      const daGoi: KeyAction[] = [];
      const { unmount } = render(
        taoPhanTu(Khung, { xuLy: (hd: KeyAction) => daGoi.push(hd), mode: "edit" }),
      );
      assert.equal(dem.song(), 1, "sau mount phải có ĐÚNG MỘT listener `keydown` trên `document`");

      // Phím phát ra Ở `window` (không đi qua DOM) không thể tới một listener ở `document`:
      // đó là phép đo PHÂN BIỆT `document` với `window` — chỗ mà listener cũ nằm.
      daGoi.length = 0;
      const oWindow = new window.KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true });
      window.dispatchEvent(oWindow);
      assert.deepEqual(daGoi, [], "listener phải ở `document`, KHÔNG ở `window`");

      unmount();
      assert.equal(dem.song(), 0, "unmount phải GỠ listener (rò listener chỉ hiện sau vài lần đổi chế độ)");
    } finally {
      dem.tra();
    }
  });

  it("DỌN LISTENER: mount → unmount → bấm phím ⇒ handler KHÔNG được gọi lần nữa", () => {
    // Đếm bằng MỘT BIẾN `let`, không in DOM node, không đọc cây (bài học `218 697 ms rồi OOM`).
    let soLan = 0;
    const { unmount } = render(taoPhanTu(Khung, { xuLy: () => { soLan += 1; }, mode: "edit" }));
    bamPhim(document.body, { key: " " });
    assert.equal(soLan, 1, "đối chứng dương: lúc còn mount thì handler phải chạy");
    unmount();
    bamPhim(document.body, { key: " " });
    assert.equal(soLan, 1, "sau unmount, phím KHÔNG được gọi handler thêm lần nào");
  });

  it("hook TRUYỀN `mode` xuống `resolveKey`: phím của màn Biên tập không bắn ở màn khác", () => {
    const daGoi: KeyAction[] = [];
    const { unmount } = render(
      taoPhanTu(Khung, { xuLy: (hd: KeyAction) => daGoi.push(hd), mode: "compare" }),
    );
    bamPhim(document.body, { key: "[" });
    bamPhim(document.body, { key: "ArrowLeft", shiftKey: true });
    assert.deepEqual(daGoi, [], "`[` và nudge là phím của màn Biên tập ⇒ không bắn ở màn Đối chiếu");
    bamPhim(document.body, { key: " " });
    assert.deepEqual(daGoi, [{ type: "togglePlay" }], "nhưng phím phát/dừng là của MỌI màn");
    unmount();
  });
});
