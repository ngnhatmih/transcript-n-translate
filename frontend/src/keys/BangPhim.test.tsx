/**
 * Test BẢNG PHÍM TẮT §11.4 — panel PHẢI TỒN TẠI dưới dạng NHÌN THẤY ĐƯỢC, và nội dung của nó
 * phải là **CHÍNH bảng dữ liệu** của `shortcuts.ts`.
 *
 * ĐO ĐƯỢC TRƯỚC TASK 11 (Chrome thật, ERRATA #46 mục 5): `document.body.innerText` **không** chứa
 * `"Phím tắt"`, `"Shift"`, `"Alt"`; không phần tử nào có `class*="phim"`/`class*="tat"`. Tức bảng
 * phím tắt của spec **KHÔNG tồn tại** — spec §11.4 xếp nó là YÊU CẦU, không phải điểm cộng.
 *
 * Ba mệnh đề ở đây, và mỗi cái có một mutant:
 *  1. **MỘT NGUỒN** — số hàng và từng cặp (nhãn phím, việc) trong DOM === bảng dữ liệu. Mutant
 *     `P8` (chép tay bảng, lệch một hàng) là bài này ĐỎ.
 *  2. **NÓI RA PHÍM CHƯA CÓ ĐÍCH** — dấu `chưa nối` xuất hiện ĐÚNG những hàng mà `DA_NOI` không
 *     phủ (hai chiều: thiếu dấu ở hàng chưa nối, và thừa dấu ở hàng đã nối).
 *  3. **QUAN HỆ LUẬT ↔ LỚP** cho họ `bp*` — mọi lớp trong DOM phải có luật trong `app.css` và
 *     ngược lại (ERRATA #43 mục 2: ghim QUAN HỆ, không ghim CHỮ của luật). jsdom KHÔNG có layout
 *     và KHÔNG nạp `app.css`, nên hình thức thật **chỉ ảnh chụp Chrome thật** xác nhận được.
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { setupDom, teardownDom } from "../../test/dom.ts";
import { BANG_PHIM, DA_NOI } from "./shortcuts.ts";

let render: (el: unknown) => { container: HTMLElement; unmount: () => void };
let fireEvent: (el: unknown, init: Record<string, unknown>) => boolean;
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let BangPhim: (props: { onDong: () => void }) => unknown;

const tiengOn: string[] = [];
const consoleGoc = { error: console.error, warn: console.warn };

function mo(x: unknown): string {
  if (x instanceof Error) return `${x.name}: ${x.message}`;
  if (typeof x === "string") return x;
  return String(x);
}

/** MỌI khai báo của MỘT selector trong `app.css`, khai báo SAU THẮNG (đúng luật CSS khi độ đặc hiệu bằng nhau). */
function khaiBaoCua(css: string, chon: string): Map<string, string> {
  const ra = new Map<string, string>();
  const sach = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const phan of sach.split("}")) {
    const i = phan.lastIndexOf("{");
    if (i < 0) continue;
    const danhSachChon = phan.slice(0, i).split(",").map((s) => s.trim()).filter((s) => s !== "");
    if (!danhSachChon.includes(chon)) continue;
    for (const khai of phan.slice(i + 1).split(";")) {
      const hai = khai.indexOf(":");
      if (hai < 0) continue;
      ra.set(khai.slice(0, hai).trim(), khai.slice(hai + 1).trim());
    }
  }
  return ra;
}

/** Cặp (nhãn phím, việc) đọc từ DOM — thứ mà bài "MỘT NGUỒN" so với bảng dữ liệu. */
function hangTrongDom(container: HTMLElement): Array<[string, string]> {
  return [...container.querySelectorAll(".bp__dong")].map((el) => [
    el.querySelector(".bp__to-hop")?.textContent ?? "",
    el.querySelector(".bp__viec")?.textContent ?? "",
  ]);
}

describe("BangPhim: bảng phím tắt §11.4 render từ CHÍNH bảng dữ liệu", () => {
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
    const tep: any = await import("./BangPhim.tsx");
    BangPhim = tep.BangPhim;

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

  it("MỘT NGUỒN: từng hàng của DOM là một hàng của bảng dữ liệu (mutant `P8`: chép tay ⇒ ĐỎ)", () => {
    let soLanDong = 0;
    const { container, unmount } = render(taoPhanTu(BangPhim, { onDong: () => { soLanDong += 1; } }));

    // Bảng phải TỰ NÓI nó là gì — đây đúng chuỗi mà Chrome thật đo được là KHÔNG có.
    assert.match(
      container.textContent ?? "",
      /Phím tắt/,
      "bảng phải có tiêu đề `Phím tắt` (đo được trước task: chuỗi này KHÔNG tồn tại trong DOM)",
    );

    const trongDom = hangTrongDom(container);
    const trongBang = BANG_PHIM.map((pt): [string, string] => [pt.toHop, pt.viec]);
    assert.deepEqual(
      trongDom,
      trongBang,
      "DOM phải là CHÍNH bảng dữ liệu `BANG_PHIM`, cùng thứ tự, không chép tay một hàng nào",
    );
    // Và bảng phải thật sự mang hai phím mà phép đo Chrome thật tìm không thấy.
    const nhan = trongDom.map(([toHop]) => toHop);
    assert.ok(nhan.some((t) => t.includes("Shift")), "bảng phải in `Shift+…` (nudge ±0,1s)");
    assert.ok(nhan.some((t) => t.includes("Alt")), "bảng phải in `Alt+…` (nudge ±1s)");
    assert.equal(soLanDong, 0, "chưa bấm gì thì `onDong` không được gọi");

    assert.deepEqual(tiengOn, [], "bảng phím tắt không được sinh tiếng ồn console");
    unmount();
  });

  it("PHÍM CHƯA CÓ ĐÍCH được NÓI RA — dấu `chưa nối` đúng bằng phần bù của `DA_NOI` (hai chiều)", () => {
    const { container, unmount } = render(taoPhanTu(BangPhim, { onDong: () => {} }));

    const coDau: string[] = [];
    const thieuDau: string[] = [];
    for (const el of container.querySelectorAll(".bp__dong")) {
      const toHop = el.querySelector(".bp__to-hop")?.textContent ?? "";
      const hang = BANG_PHIM.find((pt) => pt.toHop === toHop);
      assert.ok(hang !== undefined, `hàng \`${toHop}\` phải có trong bảng dữ liệu`);
      const daNoi = DA_NOI.has(hang.action.type);
      const coChu = (el.querySelector(".bp__chua-noi")?.textContent ?? "").includes("chưa nối");
      if (coChu) coDau.push(toHop);
      // Hàng CHƯA NỐI mà KHÔNG mang dấu là một lời hứa suông — vế ngược của cùng mệnh đề.
      if (!daNoi && !coChu) thieuDau.push(toHop);
    }
    assert.deepEqual(
      coDau.sort(),
      ["Ctrl+Enter", "M", "S"],
      "dấu `chưa nối` phải nằm ĐÚNG ba hàng spec có mà sản phẩm chưa có đích",
    );
    assert.deepEqual(
      thieuDau,
      [],
      `hàng CHƯA NỐI mà KHÔNG mang dấu \`chưa nối\`: ${JSON.stringify(thieuDau)}`,
    );

    assert.deepEqual(tiengOn, [], "dau `chua noi` khong duoc sinh tieng on console");
    unmount();
  });

  it("ĐÓNG ĐƯỢC: nút `đóng` gọi `onDong`, và tiêu điểm nằm TRONG bảng khi vừa mở", () => {
    let soLanDong = 0;
    const { container, unmount } = render(
      taoPhanTu(BangPhim, {
        onDong: () => {
          soLanDong += 1;
        },
      }),
    );

    const khung = container.querySelector(".bp__khung") as HTMLElement;
    assert.ok(khung !== null, "panel phải có khung `.bp__khung`");
    assert.equal(khung.getAttribute("role"), "dialog", "bảng là một DIALOG (nó chặn phần còn lại)");
    assert.equal(khung.getAttribute("aria-modal"), "true");
    // Tiêu điểm phải nằm TRONG bảng ngay khi mở: nếu không, người dùng bàn phím vẫn đang ở màn
    // phía sau trong khi một lớp phủ đang che nó — và phím tiếp theo sẽ rơi vào màn đó.
    assert.ok(
      khung.contains(document.activeElement),
      `tiêu điểm phải ở TRONG bảng khi mở; đang ở ${String(document.activeElement?.tagName)}`,
    );

    fireEvent.click(container.querySelector('[data-testid="dong-bang-phim"]') as Element);
    assert.equal(soLanDong, 1, "nút `đóng` phải báo cho bên gọi");

    assert.deepEqual(tiengOn, [], "nut dong khong duoc sinh tieng on console");
    unmount();
  });

  it("HÌNH THỨC: họ lớp `bp*` có LUẬT trong `app.css` VÀ có THẬT trong DOM (hai chiều)", () => {
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const { container, unmount } = render(taoPhanTu(BangPhim, { onDong: () => {} }));

    const trongDom = new Set<string>();
    for (const el of container.querySelectorAll("*")) {
      for (const ten of el.classList) if (/^bp/.test(ten)) trongDom.add(ten);
    }
    const sachCss = appCss.replace(/\/\*[\s\S]*?\*\//g, "");
    const trongCss = new Set<string>();
    for (const m of sachCss.matchAll(/\.(bp(?:__[a-z0-9-]+)?)/g)) trongCss.add(m[1] ?? "");
    trongCss.delete("");

    // (a) MỌI khai báo phải có THẬT (không rỗng) ⇒ bắt được "có tên luật mà không tạo kiểu gì".
    for (const ten of trongDom) {
      assert.ok(
        khaiBaoCua(appCss, `.${ten}`).size > 0,
        `lớp \`${ten}\` nằm trong DOM mà app.css KHÔNG tạo kiểu cho nó`,
      );
    }
    // (b) KHÔNG luật mồ côi: luật nào cũng phải có lớp trong DOM.
    const moCoi = [...trongCss].filter((t) => !trongDom.has(t)).sort();
    assert.deepEqual(
      moCoi,
      [],
      `LUẬT MỒ CÔI: ${JSON.stringify(moCoi)} — luật này không lớp nào trong DOM mang. `
      + `Lớp có trong DOM: ${JSON.stringify([...trongDom].sort())}`,
    );

    // (c) KHAI BÁO THẮNG CUỘC: bảng là lớp PHỦ toàn trang (nó phải nằm TRÊN `.grain`), và danh
    //     sách phím phải được RESET như mọi `<ul>` khác của app (`.q__danh-sach`, `.ch__danh-sach`)
    //     — thiếu reset thì trình duyệt vẽ DẤU ĐẦU DÒNG + thụt lề.
    const khaiBp = khaiBaoCua(appCss, ".bp");
    assert.equal(khaiBp.get("position"), "fixed", "lớp phủ phải `position: fixed` (KHÔNG phải một con của lưới `.shell`)");
    assert.ok(khaiBp.get("z-index") !== undefined, "lớp phủ phải khai `z-index` để nằm TRÊN lớp grain");
    assert.match(
      appCss,
      /\.bp__danh-sach \{[^}]*margin: 0[^}]*padding: 0[^}]*list-style: none/,
      "`<ul class=\"bp__danh-sach\">` phải được RESET (margin/padding/list-style) — cùng khuôn `.q__danh-sach`",
    );

    assert.deepEqual(tiengOn, [], "hinh thuc `bp*` khong duoc sinh tieng on console");
    unmount();
  });
});
