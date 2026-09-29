/**
 * T7 — **CÁI GIÁ CỦA BẢN VÁ D4, VÀ CÁI TRẦN ĐÃ ĐẶT LÊN NÓ** (Task 12 vòng sửa 1).
 *
 * ## Vì sao tệp này tồn tại, và vì sao nó đã được VIẾT LẠI
 *
 * Vòng gom nợ Task 11 (`D4`) ghim THÊM `currentSegment` (`EditScreen.windowFor(..., pinnedThem)`),
 * và khai giá phải trả trong comment. **Lượt trước** tệp này đóng băng **cái giá VÔ HẠN** của bản
 * ghim đó: nó khẳng định `soHang == d + 2` như một "BẤT BIẾN của bản vá D4", và đo được `n=6000`
 * ⇒ **6 000 hàng / 264 000 px**. Review độc lập (`I4`) chỉ ra hai điều, cả hai đều ĐÚNG:
 *  1. **`d + 2` KHÔNG phải cận trên.** Đo bằng chính `windowFor`: `e=5,c=200` ⇒ **201 = d+6**;
 *     `e=100,c=295` ⇒ **296 = d+101**; `e=0,c=199` ⇒ 200 = d+1. Công thức đúng là
 *     `min(n, max(ve, c+1)) − min(vs, e)`, và nó **tăng theo `e`** nữa, không chỉ theo `d`.
 *  2. Một bài test khẳng định cái giá vô hạn là **biến một khiếm khuyết thành đặc tả**
 *     (`#44` mục 2): mọi bản đặt trần sau này sẽ làm nó ĐỎ.
 * ⇒ Vòng sửa 1 **đặt trần** (`tranGhimThem` / `ghimDuocChon` trong `EditScreen.tsx`), và tệp này
 * nay ghim **CÁI TRẦN**, không ghim cái giá vô hạn.
 *
 * ## Cái trần là gì (và nó KHÔNG bao gồm cái gì)
 *
 * `ghimDuocChon` chỉ trả về mốc khi nó nằm trong `tranGhimThem(...)` hàng quanh **cửa sổ đang
 * nhìn**; ngoài trần ⇒ `null` (không ghim, và `EditScreen` **cuộn khung tới** mốc đó).
 * ⇒ Giá của `D4` **có trần theo hằng số**, đo được: thêm **tối đa `TRẦN` hàng** so với không ghim.
 * ⚠️ Trần này **KHÔNG** bao gồm `editingSegment`: dòng đang gõ phải LUÔN ở trong DOM (U6, spec UI
 * §8.3 — tháo nó ra là MẤT FOCUS). Cái giá đó **có trước `D4`** (Task 6) và có chủ riêng; các số
 * `×23`/`×31` mà báo cáo cũ gán cho `D4` thực ra là giá của **bản ghim `editingSegment`** — xem
 * khối "ĐỐI CHỨNG ĐÚNG NGUỒN" ở cuối tệp (`I5`).
 *
 * ⚠️ **ĐÂY KHÔNG PHẢI BẰNG CHỨNG HÌNH THỨC.** Số hàng JSX trong jsdom chỉ là MỘT PHẦN của cái
 * giá: thời gian layout/vẽ thật, và việc khung **cuộn được** (C1), chỉ Chrome thật đo được
 * (`e2e/plans/ban-ghi-dai-t7.json`).
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { ghimDuocChon, tranGhimThem, windowFor } from "./EditScreen.tsx";

/** Tham số THAT cua man: `ROW_H`/`VIEWPORT_H`/`OVERSCAN` (xuat tu `EditScreen.tsx`). */
const ROW_H = 44;
const VIEWPORT_H = 480;
const OVERSCAN = 5;
/** Cửa sổ thường (không ghim gì) ở `scrollTop = 0`: `ceil(480/44) + 5` = 11 + 5 = 16 hàng. */
const CUA_SO = 16;

/** Số hàng `windowFor` sẽ render. */
function soHang(start: number, end: number): number {
  return end - start;
}

/** Số hàng render khi CHỈ có (`editingSegment` | `currentSegment`) được ghim, qua đúng đường của màn. */
function soHangCoGhim(
  cuon: number,
  soDoan: number,
  editing: number | null,
  current: number | null,
): number {
  const ghimThem = ghimDuocChon(current, cuon, VIEWPORT_H, ROW_H, soDoan, OVERSCAN);
  const k = windowFor(cuon, VIEWPORT_H, ROW_H, soDoan, OVERSCAN, editing, ghimThem);
  return soHang(k.start, k.end);
}

describe("T7: TRẦN của bản vá D4 — GHIM CHỈ TRONG MỘT CỬA SỔ CÓ TRẦN", () => {
  it("🔴 TRẦN ĐO ĐƯỢC: `tranGhimThem(480, 44, 5)` = 32 hàng (2 khung nhìn + overscan)", () => {
    // Đây là con số mà mọi thứ dưới đây ghim. Đổi nó (rộng hơn ⇒ giá lớn hơn; hoặc bỏ trần)
    // làm cả tệp này ĐỎ — đó là mục đích: một TRẦN phải là một ĐẶC TẢ, không phải một bình luận.
    assert.equal(tranGhimThem(VIEWPORT_H, ROW_H, OVERSCAN), 32);
    // Quan hệ (không phải literal đoán mơ): trần = 2 * (số hàng một khung nhìn + overscan).
    assert.equal(
      tranGhimThem(VIEWPORT_H, ROW_H, OVERSCAN),
      2 * (Math.ceil(VIEWPORT_H / ROW_H) + OVERSCAN),
    );
    // Và nó phải là một TRẦN THẬT: lớn hơn 0 (không ghim gì) và hữu hạn.
    assert.ok(tranGhimThem(VIEWPORT_H, ROW_H, OVERSCAN) > 0);
  });

  it("T7 KHONG GHIM: cua so chi ~ viewportH/rowH + 2*overscan", () => {
    const k = windowFor(0, VIEWPORT_H, ROW_H, 600, OVERSCAN, null, null);
    // ceil((0+480)/44) + 5 = 11 + 5 = 16; start = max(0, 0-5) = 0.
    assert.deepEqual(k, { start: 0, end: 16, pinned: false });
    assert.equal(soHang(k.start, k.end), CUA_SO);
  });

  it("T7 MOT MOC GHIM o dong dau: KHONG no ra (moc nam trong cua so)", () => {
    const k = windowFor(0, VIEWPORT_H, ROW_H, 600, OVERSCAN, 1, null);
    assert.equal(soHang(k.start, k.end), CUA_SO, "ghim mot moc trong cua so thi khong doi gi");
  });

  it("🔴 TRONG TRẦN ⇒ mốc vẫn được GHIM (mệnh đề DOM của D4 giữ nguyên trong trần)", () => {
    // `cuon = 0` ⇒ cửa sổ nhìn thấy là [0, 16); trần 32 ⇒ mốc tới 47 vẫn nằm trong trần.
    assert.equal(ghimDuocChon(16, 0, VIEWPORT_H, ROW_H, 600, OVERSCAN), 16, "ngay dưới cửa sổ");
    assert.equal(ghimDuocChon(47, 0, VIEWPORT_H, ROW_H, 600, OVERSCAN), 47, "sát mép trần");
    assert.equal(ghimDuocChon(48, 0, VIEWPORT_H, ROW_H, 600, OVERSCAN), null, "vượt trần 1 hàng");
    // Và khi đã ghim thì mốc PHẢI nằm trong khoảng render (bất biến nội dung của D4).
    const k = windowFor(
      0, VIEWPORT_H, ROW_H, 600, OVERSCAN, null,
      ghimDuocChon(47, 0, VIEWPORT_H, ROW_H, 600, OVERSCAN),
    );
    assert.ok(k.start <= 47 && 47 < k.end, "dong dang CHON phai nam trong khoang render");
    assert.equal(soHang(k.start, k.end), 48);
  });

  it("🔴 NGOÀI TRẦN ⇒ KHÔNG ghim (nên giá KHÔNG theo khoảng cách nữa)", () => {
    // Bốn cảnh mà lượt trước render 200..6000 hàng, nay phải về đúng cửa sổ thường.
    for (const [c, n] of [[200, 600], [295, 600], [500, 600], [5999, 6000]]) {
      assert.equal(
        ghimDuocChon(c, 0, VIEWPORT_H, ROW_H, n, OVERSCAN),
        null,
        `mốc ${c} nằm ngoài trần quanh cửa sổ [0,16) ⇒ KHÔNG được ghim`,
      );
      assert.equal(
        soHangCoGhim(0, n, null, c),
        CUA_SO,
        `mốc ${c} ngoài trần ⇒ render đúng cửa sổ thường, KHÔNG theo khoảng cách`,
      );
    }
    // Ca XẤU NHẤT mà lượt trước đo được: bản ghi 6000 đoạn, chọn đoạn 5999, KHÔNG cuộn.
    const xauNhat = windowFor(
      0, VIEWPORT_H, ROW_H, 6000, OVERSCAN, null,
      ghimDuocChon(5999, 0, VIEWPORT_H, ROW_H, 6000, OVERSCAN),
    );
    assert.equal(
      soHang(xauNhat.start, xauNhat.end),
      CUA_SO,
      "đo được 16 hàng — KHÔNG phải 6 000 hàng / 264 000 px của bản ghim vô điều kiện",
    );
  });

  it("🔴 BẤT BIẾN CỦA TRẦN: ghim trong trần thêm TỐI ĐA `TRẦN` hàng, với MỌI vị trí cuộn", () => {
    const TRẦN = tranGhimThem(VIEWPORT_H, ROW_H, OVERSCAN);
    const N = 6000;
    let xauNhatThem = 0;
    for (const cuon of [0, 44 * 3, 44 * 10, 44 * 100, 44 * 480, 44 * 3000, 44 * 5999]) {
      const khongGhim = soHangCoGhim(cuon, N, null, null);
      for (const c of [0, 1, 15, 16, 40, 47, 48, 100, 500, 481, 1000, 3000, 5999]) {
        const coGhim = soHangCoGhim(cuon, N, null, c);
        const them = coGhim - khongGhim;
        assert.ok(
          them <= TRẦN,
          `cuon=${cuon}, moc=${c}: ghim them ${them} hang > TRAN ${TRẦN} (do duoc ${coGhim} so voi ${khongGhim})`,
        );
        if (them > xauNhatThem) xauNhatThem = them;
      }
    }
    // Đối chứng DƯƠNG: trần này có được CHẠM tới — nếu không thì khẳng định trên là rỗng.
    assert.ok(xauNhatThem > 0, "ít nhất một cấu hình phải dùng tới trần");
    assert.ok(xauNhatThem <= TRẦN, `do duoc ${xauNhatThem}`);
  });

  it("🔴 ĐỐI CHỨNG ĐÚNG NGUỒN (I5): ×23/×31 là giá của bản ghim `editingSegment`, D4 thêm ~1%", () => {
    // `scrollTop = 44 * 480` = 21 120 px — cảnh "cuộn tới nơi dòng 500".
    const cuon = 44 * 480;
    // 1) KHÔNG ghim gì: 21 hàng.
    assert.equal(soHangCoGhim(cuon, 600, null, null), 21, "cua so thuong tai cho cuon nay");
    // 2) CHỈ ghim `editingSegment` = 1 (bản ghim có từ Task 6/U6): 495 hàng.
    assert.equal(soHangCoGhim(cuon, 600, 1, null), 495, "giá của `editingSegment` một mình");
    // 3) THÊM `D4` (chọn đoạn 500): 500 hàng ⇒ D4 chỉ thêm 5 hàng.
    assert.equal(soHangCoGhim(cuon, 600, 1, 500), 500, "giá khi có cả hai mốc ghim");
    const them = soHangCoGhim(cuon, 600, 1, 500) - soHangCoGhim(cuon, 600, 1, null);
    assert.equal(them, 5, "D4 thêm ĐÚNG 5 hàng");
    assert.ok(them / 495 < 0.02, `D4 thêm ~${Math.round((them / 495) * 100)}% — không phải ×23`);
    // ⇒ Hai tỉ lệ mà báo cáo cũ gán cho D4 là của bản ghim `editingSegment`:
    assert.ok(495 / 21 > 23, "×23 so với KHÔNG ghim — nhưng đó là giá của `editingSegment`");
    assert.ok(500 / 16 > 31, "×31 so với cửa sổ ở ĐẦU danh sách — cũng là giá của `editingSegment`");
    // Và tỉ lệ ĐÚNG của D4 trong chính cảnh đó:
    assert.ok((500 - 495) / 495 < 0.011, "D4 thêm ~1 % khi mốc chọn nằm trong tầm cuộn");
  });

  it("🔴 NGOÀI TRẦN + có `editingSegment` xa: giá còn lại là của U6, ĐÃ KHAI, không phải của D4", () => {
    // Ca này được khai TRẦN (kèm chủ = U6/Task 6) trong báo cáo vòng sửa 1: dòng đang GÕ phải
    // luôn ở trong DOM (spec UI §8.3), nên khi người dùng cuộn đi xa thì khoảng render vẫn dài
    // bằng khoảng cách tới nó. Đo ở đây để con số nằm trong mã, không nằm trong lời kể.
    const cuon = 44 * 480; // cuộn tới dòng ~480
    assert.equal(soHangCoGhim(cuon, 600, 1, null), 495, "ghim `editingSegment` = 1 ⇒ 495 hàng");
    // Nếu người dùng cuộn xuống ĐÁY, giá đó vẫn theo (đây là hệ quả của U6, có TRƯỚC D4):
    assert.equal(soHangCoGhim(44 * 580, 600, 1, null), 595, "cuộn gần đáy ⇒ ghim dòng 1 ⇒ 595 hàng");
    // Còn `D4` trong cùng cảnh đó KHÔNG thêm gì (mốc chọn 5999 nằm ngoài trần ⇒ không ghim):
    assert.equal(soHangCoGhim(44 * 580, 600, 1, 5999), 595, "D4 KHÔNG thêm hàng nào ở cảnh này");
  });
});
