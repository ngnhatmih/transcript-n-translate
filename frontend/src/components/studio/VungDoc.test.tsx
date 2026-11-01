/**
 * Test cho `keoVung` — hàm THUẦN quyết định hình học của khung chọn vùng đọc OCR.
 *
 * ## Vì sao test hàm thuần chứ không test chuột
 *
 * `VungDocKhung` nghe `pointermove` trên `window` và đổi toạ độ chuột thành tỉ lệ. Phần
 * đó là cầu nối DOM, kiểm bằng `jsdom` chỉ chứng minh "có gọi listener" — trong khi thứ
 * dễ sai là SỐ HỌC: kẹp biên, giữ nguyên bề rộng khi dời, chặn cạnh vượt qua nhau.
 *
 * ## Ba lỗi mà bộ test này tồn tại để chặn
 *
 *  1. **Kẹp từng cạnh khi `move`** ⇒ khung CO LẠI khi đập mép, vì `x0` bị kẹp ở 0 còn
 *     `x1` vẫn cộng `dx`. Người dùng kéo sang trái và thấy khung nhỏ dần.
 *  2. **Cho `x0 >= x1`** ⇒ backend từ chối (`x0 < x1` là điều kiện của
 *     `_vung_doc_tu_payload`), và lỗi hiện ở tận lúc chạy job, không phải lúc kéo.
 *  3. **Không có sàn kích thước** ⇒ khung co về 0, không còn chỗ để bắt lại bằng chuột,
 *     và vùng rỗng làm OCR trả `[]` "hợp lệ" ⇒ pipeline lặng lẽ rơi về ASR.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { keoVung, moTaVung, VUNG_DOC_MAC_DINH, type VungDoc } from "./VungDoc.tsx";

const GAN = (a: number, b: number, sai = 1e-9) =>
  assert.ok(Math.abs(a - b) < sai, `mong ${b}, thay ${a}`);

test("move doi CA khung va giu nguyen be rong, cao", () => {
  const goc: VungDoc = [0.2, 0.3, 0.6, 0.7];
  const ra = keoVung(goc, "move", 0.1, 0.05);
  GAN(ra[0], 0.3);
  GAN(ra[1], 0.35);
  GAN(ra[2], 0.7);
  GAN(ra[3], 0.75);
  // Bề rộng và chiều cao KHÔNG đổi — đó là điều phân biệt move với resize.
  GAN(ra[2] - ra[0], 0.4);
  GAN(ra[3] - ra[1], 0.4);
});

test("move dap mep thi TRUOT, khong CO LAI", () => {
  // Lỗi 1: kẹp từng cạnh làm bề rộng co từ 0,4 xuống 0,2 khi đập mép trái.
  const goc: VungDoc = [0.2, 0.3, 0.6, 0.7];
  const ra = keoVung(goc, "move", -0.5, 0);
  GAN(ra[0], 0);
  GAN(ra[2], 0.4, 1e-9);
  GAN(ra[2] - ra[0], 0.4);
  GAN(ra[3] - ra[1], 0.4);
});

test("move dap mep phai cung truot, khong co lai", () => {
  const goc: VungDoc = [0.2, 0.3, 0.6, 0.7];
  const ra = keoVung(goc, "move", 0.9, 0);
  GAN(ra[2], 1);
  GAN(ra[0], 0.6, 1e-9);
  GAN(ra[2] - ra[0], 0.4);
});

test("keo canh n chi doi y0, khong cham x hay y1", () => {
  const goc: VungDoc = [0.2, 0.3, 0.6, 0.7];
  const ra = keoVung(goc, "n", 0.5, -0.1);
  GAN(ra[0], 0.2);
  GAN(ra[1], 0.2);
  GAN(ra[2], 0.6);
  GAN(ra[3], 0.7);
});

test("keo goc ne doi y0 va x1, KHONG cham x0 hay y1", () => {
  // Góc `ne` = trên-phải: nó dịch CẠNH TRÊN (`y0`) và CẠNH PHẢI (`x1`). `x0` và `y1`
  // là hai cạnh đối diện, phải đứng yên.
  //
  // 🔴 Bài này từng SAI Ở CHÍNH TÔI: bản đầu tôi viết `GAN(ra[1], 0.3)` (mong `y0`
  // không đổi) và nó đỏ với `mong 0.3, thay 0.19999999999999998`. Code đúng, kỳ vọng
  // sai — `ne` chứa `"n"` nên `y0` PHẢI đổi. Một bài test viết theo trực giác "góc thì
  // chỉ đổi một cạnh" sẽ ghim một hình học không tồn tại.
  const goc: VungDoc = [0.2, 0.3, 0.6, 0.7];
  const ra = keoVung(goc, "ne", 0.1, -0.1);
  GAN(ra[0], 0.2); // x0 không đổi
  GAN(ra[1], 0.2); // y0 + dy
  GAN(ra[2], 0.7); // x1 + dx
  GAN(ra[3], 0.7); // y1 không đổi
});

test("keo goc sw doi y1 va x0, KHONG cham x1 hay y0", () => {
  const goc: VungDoc = [0.2, 0.3, 0.6, 0.7];
  const ra = keoVung(goc, "sw", 0.1, -0.1);
  GAN(ra[0], 0.3); // x0 + dx
  GAN(ra[1], 0.3); // y0 không đổi
  GAN(ra[2], 0.6); // x1 không đổi
  GAN(ra[3], 0.6); // y1 + dy
});

test("moi canh luon nam trong [0, 1]", () => {
  const goc: VungDoc = [0.4, 0.4, 0.6, 0.6];
  for (const tay of ["n", "s", "e", "w", "ne", "nw", "se", "sw", "move"] as const) {
    for (const [dx, dy] of [
      [-5, -5],
      [5, 5],
      [-5, 5],
      [5, -5],
    ]) {
      const ra = keoVung(goc, tay, dx, dy);
      for (const v of ra) {
        assert.ok(v >= 0 && v <= 1, `tay=${tay} dx=${dx} dy=${dy} -> ${v} ngoai [0,1]`);
      }
    }
  }
});

test("keo canh TRAI qua phai thi dung o san, khong lat nguoc", () => {
  // Lỗi 2: `x0 > x1` — backend từ chối, nhưng lỗi hiện ở tận lúc chạy job.
  const goc: VungDoc = [0.2, 0.3, 0.3, 0.7];
  const ra = keoVung(goc, "w", 0.5, 0);
  assert.ok(ra[0] < ra[2], `x0=${ra[0]} phai < x1=${ra[2]}`);
  assert.ok(ra[2] - ra[0] >= 0.05 - 1e-9, `be rong ${ra[2] - ra[0]} nho hon san 0,05`);
});

test("keo canh PHAI qua trai thi dung o san", () => {
  const goc: VungDoc = [0.2, 0.3, 0.3, 0.7];
  const ra = keoVung(goc, "e", -0.5, 0);
  assert.ok(ra[2] > ra[0], `x1=${ra[2]} phai > x0=${ra[0]}`);
  assert.ok(ra[2] - ra[0] >= 0.05 - 1e-9);
});

test("keo canh TREN xuong duoi thi dung o san", () => {
  const goc: VungDoc = [0.2, 0.3, 0.6, 0.35];
  const ra = keoVung(goc, "n", 0, 0.5);
  assert.ok(ra[1] < ra[3], `y0=${ra[1]} phai < y1=${ra[3]}`);
});

test("keo canh DUOI len tren thi dung o san", () => {
  const goc: VungDoc = [0.2, 0.3, 0.6, 0.35];
  const ra = keoVung(goc, "s", 0, -0.5);
  assert.ok(ra[3] > ra[1], `y1=${ra[3]} phai > y0=${ra[1]}`);
});

test("khong doi gi thi vung khong doi", () => {
  const goc: VungDoc = [0.13, 0.27, 0.91, 0.64];
  for (const tay of ["move", "n", "s", "e", "w", "ne", "nw", "se", "sw"] as const) {
    const ra = keoVung(goc, tay, 0, 0);
    for (let k = 0; k < 4; k++) GAN(ra[k], goc[k]);
  }
});

test("VUNG_DOC_MAC_DINH bo 10 phan tram tren cung", () => {
  // ĐO ĐƯỢC: watermark `8f4b5304daf42569.mp4` ở y=35-102 trên khung cao 1920
  // (1,8 %..5,3 %), phụ đề thật gần nhất ở y=532 (27,7 %). Bỏ 10 % là đủ tách.
  assert.deepEqual([...VUNG_DOC_MAC_DINH], [0, 0.1, 1, 1]);
});

test("moTaVung doc duoc bang mat, dung dau phay thap phan", () => {
  // Số nguyên % chứ không phải 2,34 %: người dùng kéo bằng mắt, và 6 px trên khung
  // 1920 không ai nhắm tới được bằng chuột.
  assert.equal(moTaVung([0, 0.1, 1, 1]), "x 0–100 % · y 10–100 %");
  assert.equal(moTaVung([0.1234, 0.5, 0.9876, 0.75]), "x 12–99 % · y 50–75 %");
});
