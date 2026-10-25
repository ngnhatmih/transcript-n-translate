/**
 * BẢNG PHÍM TẮT HIỆN RA ĐƯỢC — yêu cầu của spec UI §11.4 (*"Thêm **bảng phím tắt** như một yêu
 * cầu, không phải điểm cộng"*), và §7 (*"Mọi hành động đều có phím tắt"*).
 *
 * ## Vì sao nội dung của nó KHÔNG phải một bảng chép tay
 *
 * Nó render từ **CHÍNH `BANG_PHIM`** — cũng là bảng mà `resolveKey` tra. Hai bản chép tay là hai
 * nguồn sự thật, và bản thứ hai (bảng in ra) trôi khỏi bản thứ nhất (bảng thi hành) mà không có gì
 * báo: người dùng đọc một phím, bấm nó, và app làm việc khác. Đó đúng là lớp lỗi ERRATA #43 mục 2
 * ("ghim QUAN HỆ, không ghim CHỮ"), áp lên DỮ LIỆU thay vì lên CSS.
 *
 * ## Vì sao nó có dấu `chưa nối`
 *
 * Ba phím spec §5.1 ghi mà sản phẩm CHƯA có đích (`S` tách dòng, `M` gộp dòng, `Ctrl+Enter` chạy
 * job cho kênh) vẫn phải có hàng trong bảng — spec ghi chúng, và `resolveKey` trả hành động cho
 * chúng. Nhưng in một phím mà bấm vào KHÔNG có gì xảy ra là một lời hứa suông. Dấu lấy từ `DA_NOI`
 * (nguồn duy nhất), nên nó không thể lệch với thứ `App` thật sự nối mà không làm bài test ĐỎ.
 *
 * ## Vì sao `position: fixed` (và vì sao nó KHÔNG phải một grid item)
 *
 * `.shell` khai BỐN track và mọi con khai `grid-row` tường minh (ERRATA #31 mục 1). Bảng này là
 * con CUỐI của `.shell`, nhưng `.bp` là lớp phủ `position: fixed` ⇒ nó ra khỏi luồng và **không**
 * tiêu thụ track nào — CÙNG cách `.grain`. Bỏ `position: fixed` là biến nó thành con thứ năm của
 * một lưới bốn track, tức tái sinh đúng lớp lỗi đã sai thật hai lần; bài ghim CSS ở tệp test cạnh
 * đây khẳng định chính khai báo đó.
 *
 * ## TRẦN đã khai
 *
 * `jsdom` không có layout, không nạp `app.css`, không có `z-index` thật ⇒ **hình thức của bảng chỉ
 * ẢNH CHỤP TRONG CHROME THẬT xác nhận được** (bài ghim ở đây chỉ khẳng định KHAI BÁO + QUAN HỆ
 * luật ↔ lớp). Bàn giao của Task 11 liệt kê đúng các lớp/testid để phiên chính chụp.
 */
import { BANG_PHIM, DA_NOI } from "./shortcuts.ts";

export interface BangPhimProps {
  /** Đóng bảng — do `App` quyết (nó giữ trạng thái mở/đóng, và `Esc` đi qua đường bàn phím chung). */
  onDong: () => void;
}

/** Id của tiêu đề, để `role="dialog"` có tên đọc được. Hằng số: hai chỗ phải khớp nhau. */
const ID_TIEU_DE = "bp-tieu-de";

export function BangPhim({ onDong }: BangPhimProps) {
  return (
    /* Lớp phủ: `position: fixed` + `inset: 0` — nó KHÔNG phải một con của lưới ba vùng. */
    <div className="bp">
      <section className="bp__khung" role="dialog" aria-modal="true" aria-labelledby={ID_TIEU_DE}>
        <header className="bp__dau">
          <h2 className="bp__tieu-de" id={ID_TIEU_DE}>
            Phím tắt
          </h2>
          {/* `autoFocus`: tiêu điểm phải ở TRONG bảng ngay khi mở. Nếu không, người dùng bàn phím
              vẫn đang ở màn phía sau trong khi một lớp phủ đang che nó. */}
          <button
            type="button"
            className="bp__dong-nut"
            data-testid="dong-bang-phim"
            autoFocus
            onClick={onDong}
          >
            đóng
          </button>
        </header>
        {/* `<ul>` có THẬT ⇒ phải được RESET trong `app.css` (cùng lớp lỗi `.q__danh-sach`). */}
        <ul className="bp__danh-sach">
          {BANG_PHIM.map((pt) => (
            <li className="bp__dong" data-testid={`phim-${pt.toHop}`} key={`${pt.key}-${pt.toHop}`}>
              <span className="bp__to-hop">{pt.toHop}</span>
              <span className="bp__viec">{pt.viec}</span>
              {DA_NOI.has(pt.action.type) ? null : (
                <span className="bp__chua-noi">chưa nối</span>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
