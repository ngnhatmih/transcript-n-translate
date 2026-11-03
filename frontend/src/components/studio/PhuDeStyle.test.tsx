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
import { PhuDeStyleDialog } from "./PhuDeStyle.tsx";

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
    for (const nhan of ["Cỡ chữ", "Cỡ chữ (số)", "Màu chữ", "Kiểu nền", "Màu hộp",
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
