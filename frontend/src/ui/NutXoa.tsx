/**
 * `NutXoa` — nút XOÁ **HAI BƯỚC** dùng chung cho hai vùng (Kênh và Đối chiếu).
 *
 * ## Vì sao hai bước, và vì sao KHÔNG `window.confirm`
 *
 * Xoá một kênh là xoá MỌI bản ghi + MỌI bản dịch của nó (`DELETE /api/sources/{id}`
 * — cascade ba bảng, không hoàn tác được), nên một cú bấm duy nhất là quá rẻ.
 *
 * Nhưng `window.confirm` KHÔNG dùng được ở đây, và lý do là một phép ĐO, không
 * phải sở thích: jsdom (bộ chạy của `npm test`) và harness trình duyệt của repo
 * chặn/ghi đè dialog native ⇒ không bài nào bấm được nút "OK" của nó, tức đường
 * đồng ý sẽ KHÔNG BAO GIỜ được chạy trong test. Một hộp thoại không đo được là
 * một hộp thoại không ghim được (bài học ERRATA #7 mục 5: đừng gán cho một dòng
 * chưa quan sát được một bài test giả).
 *
 * Nên bước xác nhận nằm TRONG DOM, bằng chữ: bấm lần một ⇒ nút đổi thành `xóa?`
 * và mọc thêm nút `hủy`; bấm lần hai ⇒ gọi API. Mọi trạng thái đều NÓI RA bằng
 * chữ, không chỉ bằng màu hay bằng `disabled` (spec UI §7):
 *
 *   · bình thường  → chữ `xóa`
 *   · đã hỏi       → chữ `xóa?` + nút `hủy` bên cạnh (đường HUỶ là một điều khiển
 *                    THẬT, bấm được bằng cả chuột lẫn bàn phím, không phải
 *                    "bấm ra ngoài")
 *   · đang gọi     → chữ `đang xóa…` (và nút bị khoá để cú bấm thứ ba không
 *                    thành lời gọi thứ hai)
 *   · lỗi          → NGUYÊN VĂN `ApiError.message` trong một `[role="alert"]`
 *
 * ## Lỗi hiện NGUYÊN VĂN, không thay bằng câu chung
 *
 * Backend từ chối TRƯỚC khi ghi và đã viết tiếng Việt: 404 `source 7 không tồn
 * tại`, 409 `không xoá được nguồn 7: job #12 đang xếp hàng hoặc đang chạy trên nó
 * — huỷ job đó trước rồi xoá`. Câu đó là thứ DUY NHẤT nói người dùng phải làm gì
 * (`huỷ job #12`), nên thay bằng "có lỗi xảy ra" là bỏ mất đúng thông tin cần
 * (cùng luật với `loiTao`/`loiChiPhi` của các màn).
 *
 * ## Ô lỗi LUÔN có mặt trong DOM
 *
 * Nó là một `[role="alert"]` **rỗng** khi không có lỗi, và `app.css` ẩn nó bằng
 * `:empty { display: none }`. Hai lý do: (a) vùng `aria-live` phải tồn tại TRƯỚC
 * khi nội dung được chèn vào thì trình đọc màn hình mới đọc nó; (b) phép ghim
 * hai chiều "mọi lớp CSS đều có trong DOM" của `ChannelZone.test.tsx`/
 * `CompareScreen.test.tsx` (ERRATA #34 mục 1) không phải học thêm một trạng thái
 * chỉ tồn tại sau một cú bấm lỗi.
 *
 * ## Component này KHÔNG gọi API
 *
 * `onXoa` là prop, do `App` cấp (`endpoints.deleteSource`/`deleteTranslation` +
 * `reload()`), đúng khuôn "màn không tự `fetch`" của cả giai đoạn: một chỗ gọi
 * API cho mỗi hành động. Hàm đó NÉM `ApiError` khi hỏng — component chỉ HIỆN.
 */
import { useState } from "react";

export interface NutXoaProps {
  /** Tên đối tượng bị xoá, cho `aria-label` — chữ trên nút quá ngắn để tự nói. */
  doiTuong: string;
  /** Lớp CSS của nút (mỗi vùng một lớp, xem `app.css`). */
  className: string;
  /** Lớp CSS của ô lỗi — PHẢI có luật trong `app.css` (xem khối đầu tệp). */
  classNameLoi: string;
  /** `data-testid` gốc; nút huỷ và ô lỗi lần lượt là `${testid}-huy`, `${testid}-loi`. */
  testid: string;
  /** Lời gọi XOÁ THẬT rồi ĐỌC LẠI danh sách; ném `ApiError` khi thất bại. */
  onXoa: () => Promise<void>;
}

export function NutXoa({
  doiTuong,
  className,
  classNameLoi,
  testid,
  onXoa,
}: NutXoaProps) {
  // Bước 1 (đã hỏi, chưa gửi) và "đang gửi" là HAI state riêng, không phải một:
  // nếu gộp, cú bấm thứ hai vừa gửi vừa giữ chữ `xóa?` và người dùng không biết
  // lời gọi đã đi hay chưa.
  const [dangHoi, datDangHoi] = useState(false);
  const [dangXoa, datDangXoa] = useState(false);
  const [loi, datLoi] = useState<string | null>(null);

  async function xoaThat(): Promise<void> {
    datDangXoa(true);
    datLoi(null);
    try {
      await onXoa();
      // KHÔNG tự xoá hàng khỏi danh sách: `onXoa` đã `reload()` và máy chủ trả
      // danh sách mới (nguồn sự thật là máy chủ). Ở đây chỉ trả nút về trạng
      // thái đầu cho trường hợp hàng vẫn còn (ví dụ reload chậm).
      datDangHoi(false);
    } catch (e: unknown) {
      // `ApiError.message` = `"<status>: <detail>"` (`api/client.ts`), nên nhánh
      // này giữ cả mã HTTP lẫn câu tiếng Việt của backend.
      datLoi(e instanceof Error ? e.message : String(e));
      datDangHoi(false);
    } finally {
      datDangXoa(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className={className}
        data-testid={testid}
        // Trạng thái MÁY đọc được, song song với chữ trên nút: chữ `xóa?` là
        // trạng thái NGƯỜI đọc được, `data-dang-xac-nhan` là thứ test/AT đọc.
        data-dang-xac-nhan={dangHoi ? "true" : "false"}
        // Tên đầy đủ: `xóa` một mình không nói xoá CÁI GÌ, và vùng Kênh có N nút
        // giống nhau (đúng lớp lỗi mà `aria-label` của §7 sinh ra để chặn).
        aria-label={`xóa ${doiTuong}`}
        disabled={dangXoa}
        onClick={() => {
          if (!dangHoi) {
            // CÚ BẤM THỨ NHẤT: chỉ đổi trạng thái, KHÔNG gọi API.
            datDangHoi(true);
            datLoi(null);
            return;
          }
          void xoaThat();
        }}
      >
        {dangXoa ? "đang xóa…" : dangHoi ? "xóa?" : "xóa"}
      </button>
      {dangHoi && !dangXoa ? (
        <button
          type="button"
          className={className}
          data-vai-tro="huy"
          data-testid={`${testid}-huy`}
          aria-label={`thôi, không xóa ${doiTuong}`}
          onClick={() => {
            datDangHoi(false);
            datLoi(null);
          }}
        >
          hủy
        </button>
      ) : null}
      <span
        className={classNameLoi}
        role="alert"
        data-testid={`${testid}-loi`}
      >
        {loi ?? ""}
      </span>
    </>
  );
}
