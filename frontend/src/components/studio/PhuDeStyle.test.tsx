/**
 * Test cho hộp thoại "Chỉnh phụ đề hiển thị".
 *
 * Kiểm phần DÂY NỐI chạy được dưới harness này: hộp thoại MỞ ra với đủ ô điều khiển, nút
 * "về mặc định" trả NGUYÊN khối mặc định, Escape đóng, và `open=false` không vẽ gì.
 * Số học của bản xem trước đã ghim ở `lib/phuDeStyle.test.ts`.
 *
 * ## 🔴 BA ĐIỀU ĐO ĐƯỢC, ghi lại để không ai thử lại lần nữa
 *
 * Lượt chạy dùng `--test-isolation=none`: mọi tệp chạy trong CÙNG một tiến trình, và hook
 * cấp tệp bị kéo lên GỐC. Nên:
 *
 * 1. `beforeEach` phải `teardownDom()` TRƯỚC `setupDom()` — cùng khuôn `Studio.test.tsx`.
 *    Bản đầu của tôi chỉ gọi `setupDom`, và đo được hậu quả: 254/254 bài của CẢ lượt chạy
 *    đỏ, kể cả `timecode` không liên quan.
 * 2. KHÔNG dùng `screen` của testing-library: nó bind vào `document` tại thời điểm IMPORT,
 *    mà jsdom đã bị dựng lại sau đó. Truy vấn trên `document.body` hiện tại.
 * 3. KHÔNG assert đường `fireEvent.change`/`fireEvent.input` trên ô `<input>` điều khiển:
 *    đo được là handler React KHÔNG chạy (`daDoi.length` = 0), trong khi đường `click` trên
 *    nút thì chạy. Đó là giới hạn của harness, không phải của component — nên bài test chỉ
 *    khẳng định những gì nó thật sự đo được, thay vì một bài xanh giả.
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import { cleanup, fireEvent, render } from "@testing-library/react";

import { setupDom, teardownDom } from "../../../test/dom.ts";
import { STYLE_MAC_DINH, type PhuDeStyle } from "@/lib/phuDeStyle.ts";
import { PhuDeOverlay, PhuDeStyleDialog } from "./PhuDeStyle.tsx";

const ORIGIN = "http://127.0.0.1:8620";

beforeEach(() => {
  teardownDom();
  setupDom(ORIGIN);
});

afterEach(() => {
  cleanup();
  teardownDom();
});

function dung(o: Partial<{ open: boolean }> = {}) {
  const daDoi: PhuDeStyle[] = [];
  let dong = 0;
  render(
    <PhuDeStyleDialog
      open={o.open ?? true}
      onClose={() => {
        dong += 1;
      }}
      style={{ ...STYLE_MAC_DINH }}
      onChange={(s) => daDoi.push(s)}
    />,
  );
  return { daDoi, soLanDong: () => dong };
}

function co(aria: string): boolean {
  return document.body.querySelector(`[aria-label="${aria}"]`) !== null;
}

describe("PhuDeStyleDialog", () => {
  it("mở ra thì có đủ ô điều khiển của kiểu chữ", () => {
    dung();
    for (const nhan of ["Font", "Cỡ chữ", "Cỡ chữ (số)", "Màu chữ", "Kiểu nền", "Màu hộp",
                        "Độ đục của hộp", "Đệm hộp", "Đệm hộp (số)",
                        "Cỡ hộp ngang", "Cỡ hộp cao", "Canh lề", "Cách đáy khung"]) {
      assert.ok(co(nhan), `thiếu ô điều khiển "${nhan}"`);
    }
    assert.ok(document.body.querySelector('[role="dialog"]') !== null);
  });

  it("'về mặc định' trả NGUYÊN khối mặc định", () => {
    const { daDoi } = dung();
    const nut = [...document.body.querySelectorAll("button")].find(
      (b) => (b.textContent || "").trim() === "về mặc định",
    );
    assert.ok(nut !== undefined, "phải có nút 'về mặc định'");
    fireEvent.click(nut);
    assert.equal(daDoi.length, 1);
    assert.deepEqual(daDoi[0], STYLE_MAC_DINH);
  });

  it("Escape đóng hộp thoại", () => {
    const { soLanDong } = dung();
    fireEvent.keyDown(window, { key: "Escape" });
    assert.equal(soLanDong(), 1);
  });

  it("open=false thì không vẽ gì", () => {
    dung({ open: false });
    assert.equal(document.body.querySelector('[role="dialog"]'), null);
  });
});

describe("PhuDeOverlay: hộp CANH GIỮA khi đã có số từ backend", () => {
  it("có `rong` từ API ⇒ hộp rộng `rong + 2·viền` và có margin auto (canh giữa)", async () => {
    // 🔴 ĐO ĐƯỢC (ảnh chủ dự án gửi): hộp nằm lệch hẳn sang TRÁI. Nguyên nhân: nhánh có bề
    // rộng cụ thể đặt `left: 0` mà KHÔNG kèm `marginLeft/Right: auto`, nên hộp bám mép trái
    // thay vì canh giữa như `\an2` bên bản burn. Bài này ghim đúng hai thứ đó.
    //: 🔴 KHÔNG dùng `HTMLVideoElement`/`HTMLElement` toàn cục: harness này chỉ dựng
    //: `document`, không phơi các constructor đó ra global — đo được
    //: `ReferenceError: HTMLVideoElement is not defined`. Lấy lớp qua chính `document`.
    const V = document.createElement("video").constructor as unknown as { prototype: object };
    const H = document.createElement("div").constructor as unknown as { prototype: object };
    const goc = {
      vw: Object.getOwnPropertyDescriptor(V.prototype, "videoWidth"),
      vh: Object.getOwnPropertyDescriptor(V.prototype, "videoHeight"),
      cw: Object.getOwnPropertyDescriptor(H.prototype, "clientWidth"),
      ch: Object.getOwnPropertyDescriptor(H.prototype, "clientHeight"),
      fetch: globalThis.fetch,
    };
    Object.defineProperty(V.prototype, "videoWidth", { configurable: true, get: () => 1080 });
    Object.defineProperty(V.prototype, "videoHeight", { configurable: true, get: () => 1920 });
    Object.defineProperty(H.prototype, "clientWidth", { configurable: true, get: () => 132 });
    Object.defineProperty(H.prototype, "clientHeight", { configurable: true, get: () => 235 });
    globalThis.fetch = (async () => new Response(JSON.stringify({
      lines: ["mot dong"], rong: 400, cao: 58, co: 51, vien: 11, le: 34,
      rong_kha_dung: 1012,
    }), { status: 200, headers: { "content-type": "application/json" } })) as typeof fetch;

    const video = document.createElement("video");
    document.body.appendChild(video);
    try {
      render(
        <PhuDeOverlay
          //: `vien: 20` cho ĐÚNG style của chủ dự án: viền hiệu dụng = 20 × 0,5625 = 11,25
          //: ⇒ hộp = 400 + 2×11,25 = 422,5 (bản burn dùng cùng công thức).
          style={{ ...STYLE_MAC_DINH, co: 91, vien: 20, caoHop: 180,
                   kieuVien: 3, rongHop: 0 }}
          text="mot dong"
          videoRef={{ current: video }}
        />,
      );
      // chờ API (giả) trả về + một lượt render
      await new Promise((r) => setTimeout(r, 30));

      //: Hộp là phần tử DUY NHẤT có `min-height` (khung bao ngoài không có). Tìm theo
      //: `background` thì trượt — React ghi ra `background-color` hoặc `background:` tuỳ
      //: giá trị, và khung bao ngoài cũng có `position: absolute`.
      const hop = [...document.body.querySelectorAll("div")].find((e) =>
        (e.getAttribute("style") ?? "").includes("min-height"),
      );
      assert.ok(hop !== undefined, "phải có hộp");
      const style = hop.getAttribute("style") ?? "";
      assert.match(style, /margin-left:\s*auto/, `hộp phải canh giữa, đo được: ${style}`);
      assert.match(style, /margin-right:\s*auto/, `hộp phải canh giữa, đo được: ${style}`);
      assert.match(style, /width:\s*422\.5px/,
        `hộp phải rộng 400 + 2×11,25 = 422,5, đo được: ${style}`);
    } finally {
      //: Trả lại ĐÚNG thứ đã có. `videoWidth`/`clientWidth` là getter của LỚP CHA
      //: (`HTMLMediaElement.prototype`/`Element.prototype`), nên descriptor trên prototype
      //: của `video`/`div` là `undefined` — `defineProperty(..., undefined)` ném
      //: "Property description must be an object: undefined". Không có thì XOÁ.
      const tra = (obj: object, ten: string, d?: PropertyDescriptor): void => {
        if (d === undefined) delete (obj as Record<string, unknown>)[ten];
        else Object.defineProperty(obj, ten, d);
      };
      tra(V.prototype, "videoWidth", goc.vw);
      tra(V.prototype, "videoHeight", goc.vh);
      tra(H.prototype, "clientWidth", goc.cw);
      tra(H.prototype, "clientHeight", goc.ch);
      globalThis.fetch = goc.fetch;
      video.remove();
    }
  });
});
