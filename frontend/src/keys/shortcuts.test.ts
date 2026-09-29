/**
 * Test BẢNG PHÍM TẮT (spec UI §5.1 + §11.4) — `resolveKey` là hàm THUẦN: không React, không DOM.
 *
 * Vì sao tách khỏi `<App/>`: bảng phím là DỮ LIỆU, không phải hành vi của một màn hình. Ghim nó ở
 * đây thì mỗi hàng của bảng đo được **độc lập** với jsdom, và phép đo không phụ thuộc một lần
 * render nào (cùng lý lẽ `timecode.ts`/`window.ts` của các task trước).
 *
 * 🔴 NGUỒN CÓ THẨM QUYỀN LÀ SPEC, KHÔNG PHẢI BRIEF D1 (ERRATA #44 mục 3):
 *   - spec UI §5.1 dòng 296 + §5.2 dòng 310: `[`/`]` = **đặt mốc start/end TẠI ĐẦU ĐỌC**;
 *   - spec UI §5.1 dòng 300–301 + §5.2 dòng 309: nudge = **`Shift+←/→` (±0,1 s)** và
 *     **`Alt+←/→` (±1 s)**.
 * Trước task này, mã sản phẩm gán `[`/`]` cho nudge (`nudgeDoan("start"/"end")` trong `App.tsx`).
 * Bài `[`/`]` KHÔNG phải nudge ở dưới ghim đúng vế đã bị đảo đó.
 *
 * Chạy riêng tệp này từ `frontend/`:
 *   node --import ./test/swc-loader.mjs --test --test-isolation=none src/keys/shortcuts.test.ts
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { BANG_PHIM, DA_NOI, resolveKey } from "./shortcuts.ts";
import type { PhimBam, PhimTat } from "./shortcuts.ts";

/** Một sự kiện phím TỐI THIỂU — đúng những khoá mà `resolveKey` đọc (không cần `KeyboardEvent`). */
function phim(key: string, o: Partial<PhimBam> = {}): PhimBam {
  return { key, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...o };
}

/** Sự kiện ĐÚNG như hàng `pt` mô tả (dùng để chứng minh MỌI hàng của bảng đều tra được). */
function suKienCua(pt: PhimTat): PhimBam {
  return phim(pt.key, {
    ctrlKey: pt.ctrl ?? false,
    altKey: pt.alt ?? false,
    // Với phím KÝ TỰ DẤU (`?`, `[`, `]`) `shift` KHÔNG phải khoá tra (xem `shortcuts.ts`) ⇒ dựng
    // sự kiện có `shiftKey: true` là ca KHÓ NHẤT: nó vẫn phải tra ra.
    shiftKey: pt.key.length === 1 && !/[a-z0-9]/i.test(pt.key) ? true : (pt.shift ?? false),
  });
}

describe("resolveKey: bảng phím tắt §5.1 (hàm thuần)", () => {
  it("Space phát/dừng — và nó là phím của MỌI chế độ (không có `mode` trong hàng)", () => {
    assert.deepEqual(resolveKey(phim(" "), "edit", false), { type: "togglePlay" });
    assert.deepEqual(resolveKey(phim(" "), "compare", false), { type: "togglePlay" });
    assert.deepEqual(resolveKey(phim(" "), "glossary", false), { type: "togglePlay" });
  });

  it("KHÔNG cướp phím khi người dùng đang gõ trong ô nhập — MỌI hàng của bảng", () => {
    // Vì sao quét CẢ BẢNG chứ không một phím: mệnh đề của guard là "bảng phím KHÔNG cướp ký tự
    // của ô nhập", và một hàng quên nhánh `inField` là một hàng cướp phím. Đây cũng là vế bị
    // mutant `P1` (bỏ nhánh `inField`) giết.
    for (const pt of BANG_PHIM) {
      assert.equal(
        resolveKey(suKienCua(pt), pt.mode ?? "edit", true),
        null,
        `hàng \`${pt.toHop}\` phải bị BỎ QUA khi tiêu điểm ở trong ô nhập`,
      );
    }
  });

  it("MỌI hàng của bảng đều TRA ĐƯỢC (không có hàng chết) — và đúng chế độ của nó", () => {
    // Một hàng chỉ để HIỂN THỊ mà không tra ra được là một lời hứa suông của bảng §11.4.
    for (const pt of BANG_PHIM) {
      const cheDo = pt.mode ?? "edit";
      assert.deepEqual(
        resolveKey(suKienCua(pt), cheDo, false),
        pt.action,
        `hàng \`${pt.toHop}\` phải tra ra ĐÚNG hành động của nó ở chế độ \`${cheDo}\``,
      );
    }
  });

  it("[ và ] ĐẶT MỐC start/end TẠI ĐẦU ĐỌC — KHÔNG phải nudge (ERRATA #44 mục 3)", () => {
    assert.deepEqual(resolveKey(phim("["), "edit", false), { type: "setEdgeAtPlayhead", edge: "start" });
    assert.deepEqual(resolveKey(phim("]"), "edit", false), { type: "setEdgeAtPlayhead", edge: "end" });
    // `[`/`]` KHÔNG được là nudge: mutant `P9` (gọi lại `nudgeDoan`) phải làm bài này ĐỎ.
    assert.notDeepEqual(resolveKey(phim("["), "edit", false), { type: "nudge", edge: "start", by: -0.1 });
    // `?` là Shift+/ trên bàn phím Mỹ: `key` đã mã hoá ký tự nên Shift không được dùng làm khoá tra.
    assert.deepEqual(resolveKey(phim("?", { shiftKey: true }), "edit", false), { type: "toggleShortcuts" });
    assert.deepEqual(resolveKey(phim("?", { shiftKey: false }), "edit", false), { type: "toggleShortcuts" });
  });

  it("nudge = `Shift+←/→` ±0,1s và `Alt+←/→` ±1s — ĐÚNG DẤU và ĐÚNG ĐỘ LỚN", () => {
    assert.deepEqual(
      resolveKey(phim("ArrowLeft", { shiftKey: true }), "edit", false),
      { type: "nudge", edge: "start", by: -0.1 },
    );
    assert.deepEqual(
      resolveKey(phim("ArrowRight", { shiftKey: true }), "edit", false),
      { type: "nudge", edge: "end", by: 0.1 },
    );
    assert.deepEqual(
      resolveKey(phim("ArrowLeft", { altKey: true }), "edit", false),
      { type: "nudge", edge: "start", by: -1 },
    );
    assert.deepEqual(
      resolveKey(phim("ArrowRight", { altKey: true }), "edit", false),
      { type: "nudge", edge: "end", by: 1 },
    );
    // Không có phím bổ trợ ⇒ `←`/`→` TRẦN không phải nudge (chúng thuộc màn chấm tay, chưa có).
    assert.equal(resolveKey(phim("ArrowLeft"), "edit", false), null);
    assert.equal(resolveKey(phim("ArrowRight"), "edit", false), null);
  });

  it("`Ctrl+1/2/3` đổi chế độ — và `1` TRẦN thì KHÔNG (phím chấm điểm thuộc màn chưa có)", () => {
    assert.deepEqual(resolveKey(phim("1", { ctrlKey: true }), "edit", false), { type: "setMode", mode: "edit" });
    assert.deepEqual(resolveKey(phim("2", { ctrlKey: true }), "edit", false), { type: "setMode", mode: "compare" });
    assert.deepEqual(resolveKey(phim("3", { ctrlKey: true }), "edit", false), { type: "setMode", mode: "glossary" });
    // Đổi chế độ phải đi được từ MỌI chế độ — nếu không thì vào Thuật ngữ là KHÔNG RA ĐƯỢC.
    assert.deepEqual(resolveKey(phim("1", { ctrlKey: true }), "glossary", false), { type: "setMode", mode: "edit" });
    assert.equal(resolveKey(phim("1"), "edit", false), null);
    assert.equal(resolveKey(phim("1"), "compare", false), null);
  });

  it("`Enter`/`Esc`/`S`/`M`/`N`/`J`/`K`/`Ctrl+Enter` — ĐÚNG hàng của spec, không bịa phím", () => {
    assert.deepEqual(resolveKey(phim("Enter"), "edit", false), { type: "startEdit" });
    assert.deepEqual(resolveKey(phim("Escape"), "edit", false), { type: "endEdit" });
    assert.deepEqual(resolveKey(phim("s"), "edit", false), { type: "splitAtPlayhead" });
    assert.deepEqual(resolveKey(phim("m"), "edit", false), { type: "mergeWithNext" });
    assert.deepEqual(resolveKey(phim("n"), "edit", false), { type: "nextSuspect" });
    assert.deepEqual(resolveKey(phim("j"), "edit", false), { type: "segmentPrev" });
    assert.deepEqual(resolveKey(phim("k"), "edit", false), { type: "segmentNext" });
    assert.deepEqual(resolveKey(phim("Enter", { ctrlKey: true }), "edit", false), { type: "runJob" });
  });

  it("`mode` LÀ MỘT PHẦN CỦA KHOÁ TRA — phím của màn Biên tập không bắn ở màn khác", () => {
    // Vì sao quan trọng: `setMode` KHÔNG xoá `editingSegment`, nên một listener không lọc `mode`
    // vẫn còn một dòng "đang sửa" trong state khi người dùng đã sang màn Đối chiếu — và một phím
    // `[` ở đó là một lượt GHI vào bản ghi mà màn hình không hề hiện ô sửa nào.
    for (const cheDo of ["compare", "glossary"] as const) {
      assert.equal(resolveKey(phim("["), cheDo, false), null, `\`[\` không được bắn ở chế độ ${cheDo}`);
      assert.equal(resolveKey(phim("]"), cheDo, false), null);
      assert.equal(resolveKey(phim("Enter"), cheDo, false), null);
      assert.equal(resolveKey(phim("Escape"), cheDo, false), null);
      assert.equal(resolveKey(phim("ArrowLeft", { shiftKey: true }), cheDo, false), null);
      assert.equal(resolveKey(phim("ArrowRight", { altKey: true }), cheDo, false), null);
      assert.equal(resolveKey(phim("s"), cheDo, false), null);
      assert.equal(resolveKey(phim("m"), cheDo, false), null);
    }
    // Và vế ngược: phím CHỌN ĐOẠN / CHẾ ĐỘ / PHÁT là của cả ba màn (chúng không ghi gì).
    for (const cheDo of ["edit", "compare", "glossary"] as const) {
      assert.deepEqual(resolveKey(phim("k"), cheDo, false), { type: "segmentNext" });
      assert.deepEqual(resolveKey(phim("n"), cheDo, false), { type: "nextSuspect" });
      assert.deepEqual(resolveKey(phim("?", { shiftKey: true }), cheDo, false), { type: "toggleShortcuts" });
    }
  });

  it("phím KHÔNG có trong bảng ⇒ `null`, không ném (mutant `P6`)", () => {
    for (const key of ["q", "F5", "Backspace", "Tab", "4", "z"]) {
      assert.equal(resolveKey(phim(key), "edit", false), null, `\`${key}\` không có trong bảng`);
    }
    // Vế ngược: một phím CÓ trong bảng thì KHÔNG được trả `null` (nếu không, "trả null" là vô nghĩa).
    assert.notEqual(resolveKey(phim(" "), "edit", false), null);
  });

  it("BẢNG là MỘT NGUỒN: mọi hàng có nhãn + việc để hiển thị, và `DA_NOI` không bịa loại hành động", () => {
    assert.ok(BANG_PHIM.length >= 18, `bảng phải phủ bảng §5.1; đo được ${BANG_PHIM.length} hàng`);
    for (const pt of BANG_PHIM) {
      assert.ok(pt.toHop.length > 0, "mỗi hàng phải có NHÃN PHÍM để in ra bảng §11.4");
      assert.ok(pt.viec.length > 0, `hàng \`${pt.toHop}\` phải có VIỆC (chữ người dùng đọc)`);
      assert.ok(pt.action !== null, "hàng của bảng luôn mang một `KeyAction` (đã nối hay chưa là chuyện của `DA_NOI`)");
    }
    const coTrongBang = new Set(BANG_PHIM.map((pt) => pt.action?.type));
    for (const loai of DA_NOI) {
      assert.ok(
        coTrongBang.has(loai),
        `\`DA_NOI\` khai đã nối \`${loai}\` nhưng KHÔNG hàng nào của bảng trả hành động đó`,
      );
    }
    // Ba phím spec CÓ mà sản phẩm CHƯA có ĐÍCH — khai ra, không giấu (giết luôn một "bảng chép tay").
    const chuaNoi = BANG_PHIM.filter((pt) => pt.action !== null && !DA_NOI.has(pt.action.type));
    assert.deepEqual(
      chuaNoi.map((pt) => pt.toHop).sort(),
      ["Ctrl+Enter", "M", "S"],
      "danh sách phím CHƯA NỐI phải đúng ba phím này (nối thêm thì bỏ khỏi TRẦN, không sửa test)",
    );
  });
});
