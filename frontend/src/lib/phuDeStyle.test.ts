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
  hinhHocVideo,
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
    font: "Archivo",
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

test("hinhHocVideo: CÙNG công thức với bản burn (`to_ass`) — trục NGẮN quyết định", () => {
  const s = { ...STYLE_MAC_DINH, co: 60, vien: 2 };
  // Ngang 1920×1080: trục ngắn 1080 -> tỉ lệ 1.
  assert.equal(hinhHocVideo(s, HE_GOC.rx, HE_GOC.ry).coLibass, 60);
  // Dọc 1080×1920: trục ngắn 1080 -> 1080/1920 = 0,5625.
  const doc = hinhHocVideo(s, 1080, 1920);
  assert.ok(
    Math.abs(doc.coLibass - 33.75) < 1e-9,
    `cỡ chữ libass trên khung dọc phải là 33,75, đo được ${doc.coLibass}`,
  );
  //: Cỡ chữ để TRÌNH DUYỆT vẽ = cỡ libass × 0,637: đo được Chrome vẽ rộng gấp ~1,5 lần
  //: libass cùng số, nên thiếu hệ số này là chữ tràn khỏi hộp dù bề rộng hộp đúng.
  assert.ok(
    Math.abs(doc.coChu - 33.75 * 0.637) < 1e-9,
    `cỡ chữ VẼ phải là 33,75 × 0,637, đo được ${doc.coChu}`,
  );
  // Cách đáy tính theo CHIỀU CAO video, không theo trục ngắn.
  assert.ok(Math.abs(doc.cachDay - 0.06 * 1920) < 1e-9);
});

test("hinhHocVideo: cỡ chữ là pixel CỦA VIDEO, không phải của khung xem", () => {
  // 🔴 ĐO ĐƯỢC (chủ dự án: *"tìm cách để phụ đề trên web ko lệch so với bản burn"*).
  //
  // Video 1080×1920, `co = 30`: bản burn vẽ chữ **17 px** trong hệ `PlayRes` (đo trên ảnh
  // burn: chữ cao 10 px, cả câu rộng 428 px). Bản xem trước cũ trả cỡ chữ theo khung hiển
  // thị (~132 px) nên ra 2,06 px — Chrome không cho ký tự hẹp hơn ~1 px, và hộp xem trước
  // rộng 62 % khung trong khi bản burn 41,6 %.
  //
  // Nay hàm này trả ĐÚNG số của bản burn; bên vẽ dựng khối ở cỡ đó rồi thu bằng
  // `transform: scale()`, nên tỉ lệ khớp.
  const s = { ...STYLE_MAC_DINH, co: 30, vien: 20 };
  const h = hinhHocVideo(s, 1080, 1920);
  assert.ok(Math.abs(h.coLibass - 16.875) < 1e-9,
    `cỡ chữ libass phải là 30 × 0,5625 = 16,875, đo được ${h.coLibass}`);
  //: CHỮ VẼ RA phải nhỏ hơn: 16,875 × 0,637 = 10,75 px (xem `TI_LE_CHU_LIBASS`).
  assert.ok(Math.abs(h.coChu - 16.875 * 0.637) < 1e-9,
    `cỡ chữ VẼ phải là 16,875 × 0,637 = 10,75, đo được ${h.coChu}`);
  assert.ok(Math.abs(h.vien - 11.25) < 1e-9, `viền phải là 20 × 0,5625 = 11,25, đo được ${h.vien}`);
  assert.ok(Math.abs(h.le - 33.75) < 1e-9, `lề phải là 60 × 0,5625 = 33,75, đo được ${h.le}`);
  // Không phụ thuộc kích thước khung hiển thị — đó chính là điều làm hai bên lệch trước đây.
  const cungSo = hinhHocVideo(s, 1080, 1920);
  assert.deepEqual(h, cungSo);
});
