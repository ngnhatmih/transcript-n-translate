/**
 * Test cho mô hình kiểu chữ phụ đề — hàm THUẦN trong `lib/phuDeStyle.ts`.
 *
 * ## Vì sao test hàm thuần
 *
 * Ba nơi dùng chung mô hình này (xem trước trên web, tệp `.ass` tải về, phụ đề burn vào
 * video lồng tiếng). Thứ dễ sai KHÔNG phải chỗ vẽ, mà là SỐ HỌC và TÊN KHOÁ: một tỉ lệ
 * tính theo trục sai làm chữ tràn mép trên video dọc, và một khoá sai tên làm backend bỏ
 * qua im lặng (nó bỏ khoá lạ, không báo lỗi).
 *
 * ## 🔴 Vì sao KHÔNG đụng `globalThis.localStorage`
 *
 * Lượt chạy dùng `--test-isolation=none`: MỌI tệp test chạy trong CÙNG một tiến trình, và
 * hook cấp tệp bị node:test kéo lên GỐC — nên một `afterEach` ghi đè global sẽ chạy sau
 * MỌI bài của cả lượt. Bản đầu của tệp này làm đúng thế và đo được hậu quả: 258 dòng lỗi
 * `TypeError: Invalid URL: [object Object]` ở các tệp KHÔNG liên quan.
 *
 * Nên `docStyle`/`luuStyle` nhận kho lưu làm THAM SỐ, và ở đây truyền vật giả.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  docStyle,
  HE_GOC,
  hinhHoc,
  KHOA_LUU,
  luuStyle,
  STYLE_MAC_DINH,
  styleChoAss,
  type KhoLuu,
} from "./phuDeStyle.ts";

function khoGia(batDau: Record<string, string> = {}) {
  const m = new Map(Object.entries(batDau));
  const kho: KhoLuu = {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
  } as KhoLuu;
  return { kho, m };
}

test("mặc định TRÙNG hằng của backend", () => {
  // Ba số này phải khớp `_ASS_KHUNG_MAC_DINH` / `_ASS_OFFSET_DOC_MAC_DINH` bên backend,
  // nếu không thì mở hộp thoại lần đầu là đổi luôn hình dạng phụ đề dù chưa bấm gì.
  assert.equal(STYLE_MAC_DINH.co, 54);
  assert.equal(STYLE_MAC_DINH.vien, 2);
  assert.equal(STYLE_MAC_DINH.kieuVien, 3);
  assert.equal(STYLE_MAC_DINH.canLe, 2);
  assert.equal(STYLE_MAC_DINH.viTriDoc, 0.06);
  // `&HA0000000` có alpha ASS 0xA0 = 160; alpha ASS NGƯỢC CSS nên alpha CSS = 95.
  assert.equal(Math.round(STYLE_MAC_DINH.doDucHop * 255), 95);
});

test("không có kho lưu thì vẫn ra mặc định, KHÔNG ném", () => {
  assert.deepEqual(docStyle(undefined), STYLE_MAC_DINH);
});

test("JSON hỏng thì rơi về mặc định TỪNG trường", () => {
  const { kho } = khoGia({ [KHOA_LUU]: '{"co": 999, "mauChu": "đỏ", "canLe": 7}' });
  const s = docStyle(kho);
  assert.equal(s.co, 400, "cỡ chữ phải bị kẹp về 400");
  assert.equal(s.mauChu, STYLE_MAC_DINH.mauChu, "màu sai định dạng phải về mặc định");
  assert.equal(s.canLe, 2, "canLe lạ phải về 2");
  assert.equal(s.vien, STYLE_MAC_DINH.vien, "trường vắng mặt phải về mặc định");
});

test("ghi rồi đọc lại thì trùng khớp", () => {
  const { kho } = khoGia();
  const s = { ...STYLE_MAC_DINH, co: 72, dam: true, canLe: 1 as const, viTriDoc: 0.2 };
  luuStyle(s, kho);
  assert.deepEqual(docStyle(kho), s);
});

test("styleChoAss dùng TÊN KHOÁ của backend, không phải tên biến giao diện", () => {
  const khoi = styleChoAss({ ...STYLE_MAC_DINH, co: 60, viTriDoc: 0.1, kieuVien: 1 });
  // Backend bỏ qua khoá lạ IM LẶNG, nên một khoá sai tên không gây lỗi — chỉ không có
  // tác dụng. Đó là lý do phải ghim đúng tên.
  assert.deepEqual(khoi, {
    co: 60,
    mau_chu: STYLE_MAC_DINH.mauChu,
    mau_hop: STYLE_MAC_DINH.mauHop,
    do_duc_hop: STYLE_MAC_DINH.doDucHop,
    vien: STYLE_MAC_DINH.vien,
    rong_hop: 0,
    cao_hop: 0,
    kieu_vien: 1,
    dam: false,
    nghieng: false,
    can_le: 2,
    offset_doc: 0.1,
  });
});

test("hinhHoc nhân tỉ lệ theo trục NGẮN — khung dọc không tràn", () => {
  const s = { ...STYLE_MAC_DINH, co: 60, vien: 2 };
  // Ngang 1920×1080: trục ngắn 1080 -> tỉ lệ 1.
  assert.equal(hinhHoc(s, HE_GOC.rx, HE_GOC.ry).coChu, 60);
  // Dọc 1080×1920: trục ngắn 1080 -> 1080/1920 = 0,5625.
  const doc = hinhHoc(s, 1080, 1920);
  assert.ok(
    Math.abs(doc.coChu - 33.75) < 1e-9,
    `cỡ chữ trên khung dọc phải là 33,75, đo được ${doc.coChu}`,
  );
  // Cách đáy tính theo CHIỀU CAO khung, không theo trục ngắn.
  assert.ok(Math.abs(doc.cachDay - 0.06 * 1920) < 1e-9);
});
