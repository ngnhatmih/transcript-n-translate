/**
 * Test cho `hopVideo` — hàm THUẦN tính hộp hiển thị thật của video.
 *
 * Lý do tồn tại: mọi lớp đè lên video (chữ phụ đề xem trước, hộp vùng đọc OCR) đặt toạ độ
 * theo hộp này. Sai một tỉ lệ là chữ lệch khỏi bản burn và hộp OCR tràn ra ngoài hình —
 * đúng lỗi chủ dự án thấy trên ảnh chụp video dọc trong khung 16:9.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { hopVideo } from "./hopVideo.ts";

const GAN = (a: number, b: number) =>
  assert.ok(Math.abs(a - b) < 1e-9, `mong ${b}, thay ${a}`);

test("cùng tỉ lệ thì video phủ KÍN khung, không có viền", () => {
  const h = hopVideo(1920, 1080, 1920, 1080);
  GAN(h.trai, 0);
  GAN(h.tren, 0);
  GAN(h.rong, 1920);
  GAN(h.cao, 1080);
});

test("video DỌC trong khung NGANG: chừa hai bên, hình ở giữa", () => {
  // Khung 1600×900 (16:9), video 1080×1920 (dọc). tiLe = min(1600/1080, 900/1920)
  // = min(1,481, 0,469) = 0,469 -> cao = 900, rong = 1080 × 0,469 = 506,25.
  const h = hopVideo(1600, 900, 1080, 1920);
  GAN(h.cao, 900);
  GAN(h.rong, (1080 * 900) / 1920);
  GAN(h.trai, (1600 - (1080 * 900) / 1920) / 2);
  GAN(h.tren, 0);
});

test("video NGANG trong khung DỌC: chừa trên dưới", () => {
  // Khung 400×800, video 1920×1080. tiLe = min(400/1920, 800/1080) = 0,208 -> rong 400.
  const h = hopVideo(400, 800, 1920, 1080);
  GAN(h.rong, 400);
  GAN(h.trai, 0);
  GAN(h.cao, (1080 * 400) / 1920);
  GAN(h.tren, (800 - (1080 * 400) / 1920) / 2);
});

test("chưa biết kích thước video thì trả ĐÚNG khung chứa", () => {
  // Metadata chưa nạp: `videoWidth = 0`. Hành vi cũ phải giữ nguyên, nếu không lớp đè biến
  // mất trong khoảnh khắc đầu và chữ nháy một cái.
  const h = hopVideo(800, 450, 0, 0);
  GAN(h.trai, 0);
  GAN(h.tren, 0);
  GAN(h.rong, 800);
  GAN(h.cao, 450);
});

test("khung chứa chưa có kích thước thì trả 0×0, KHÔNG chia cho 0", () => {
  const h = hopVideo(0, 0, 1920, 1080);
  GAN(h.rong, 0);
  GAN(h.cao, 0);
  assert.ok(Number.isFinite(h.trai) && Number.isFinite(h.tren));
});
