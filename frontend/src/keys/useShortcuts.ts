/**
 * `useShortcuts` — **MỘT** listener `keydown` cho cả app, gắn ở `document`, và dọn được.
 *
 * ## Vì sao tập trung ở đây (và vì sao KHÔNG phải "dựng bàn phím từ số 0")
 *
 * Trước task này, `App.tsx` có một listener ở **`window`** chỉ nhận HAI phím (`[`/`]`) và gọi
 * thẳng `nudgeDoan`. Nó đã được đo bằng **bàn phím THẬT trong Chrome thật** (ERRATA #46 mục 5) —
 * gõ `[` trong ô sửa ⇒ server KHÔNG đổi `version`; cùng phím đó khi tiêu điểm ở `BODY` ⇒
 * `v1 → v2`. Task 11 **hợp nhất** nó vào đây, nên HÀNH VI GUARD phải giữ NGUYÊN:
 *
 *   `dangGoTrongONhap(suKien.target) || dangGoTrongONhap(document.activeElement)`
 *
 * Hai vế, không phải một:
 *  - `suKien.target` — NƠI phím được gõ;
 *  - `document.activeElement` — NƠI đang có tiêu điểm.
 *
 * Vì sao vẫn cần CẢ HAI dù `keydown` gửi tới phần tử đang có tiêu điểm: một sự kiện có thể được
 * phát ra từ `body`/`document` trong khi tiêu điểm nằm trong ô nhập (đo được: **nửa `activeElement`
 * bị bỏ ⇒ 0 bài đỏ** ở vòng D1 — ERRATA #45 mục 1(b)). Hai vế có HAI mutant độc lập: `P1` ở
 * `resolveKey` (nhánh `inField`) và `P2` ở đây (lần đọc `activeElement`).
 *
 * ## Vì sao `document` chứ không `window`
 *
 * `document` là tầng mà mọi phím ĐI QUA DOM đều tới, kể cả khi tiêu điểm ở `body`; `window` chỉ là
 * đích cuối của phép bong bóng. Và `document` là chỗ đo được: một sự kiện phát ra Ở `window` không
 * tới được listener ở `document` (bài `MỘT listener … KHÔNG ở window` trong tệp test).
 *
 * ## Vì sao deps là `[xuLy, mode]` — và đây là một RÀNG BUỘC, không phải một lựa chọn phong cách
 *
 * `App` truyền một hàm MỚI ở mỗi lượt render (nó đóng trên state của lượt đó), nên effect chạy lại
 * mỗi lượt render: **gỡ listener cũ rồi gắn listener mới**. Điều đó giữ nguyên cửa sổ một-lượt-commit
 * mà bài ghim `D1 NỀN MỚI HƠN (CỬA SỔ CHƯA GẮN LẠI)` đo: tại lượt commit có dữ liệu mới, listener
 * CŨ vẫn còn gắn (passive effect chưa flush), nên NỀN của lệnh ghi phải đọc từ ảnh chụp mới nhất
 * (`App.banGhiMoiNhat` — `useRef` gán ngay trong thân render).
 *
 * ⚠️ Nếu thay bằng "gắn MỘT lần với deps `[]` + giữ handler trong một `useRef`", cửa sổ đó biến mất
 * và mutant `G1-BASE-CLOSURE` (đọc closure thay vì ref) **hết ĐỎ** — tức bản refactor làm mất độ
 * phủ của chính bài ghim mà `#46` mục 11 giao cho task này giữ xanh. Đừng đổi.
 */
import { useEffect } from "react";

import type { Mode } from "../state/reducer.ts";
import { resolveKey } from "./shortcuts.ts";
import type { KeyAction } from "./shortcuts.ts";

/** Nơi nhận hành động đã tra được — `App` là người duy nhất biết phải LÀM gì. */
export type XuLyPhim = (hanhDong: KeyAction) => void;

/**
 * Phím có đang được gõ vào một Ô NHẬP không — `closest` đi LÊN cây DOM nên nó bắt cả
 * `input`/`textarea`/`select`/`[contenteditable]` và mọi con của chúng.
 *
 * Trả `false` cho `null`/`body`/phần tử khác: đó là những ca phím nóng PHẢI chạy.
 */
function dangGoTrongONhap(dich: EventTarget | null): boolean {
  return dich instanceof HTMLElement
    && dich.closest("input, textarea, select, [contenteditable]") !== null;
}

/**
 * Gắn bảng phím tắt (§5.1) cho cả app.
 *
 * `mode` được truyền xuống `resolveKey` như một phần của KHOÁ TRA: `setMode` không xoá
 * `editingSegment`, nên một listener không lọc `mode` vẫn thấy "một dòng đang sửa" sau khi người
 * dùng đã sang màn Đối chiếu — và một phím `[` ở đó là một lượt GHI vào bản ghi mà màn hình
 * không hề hiện ô sửa nào.
 */
export function useShortcuts(xuLy: XuLyPhim, mode: Mode): void {
  useEffect(() => {
    function khiBamPhim(suKien: KeyboardEvent): void {
      // HAI VẾ của guard ô nhập — xem docblock đầu tệp. `resolveKey` vẫn nhận `inField` như một
      // THAM SỐ (nó thuần, không đọc DOM); phép đọc DOM nằm ở đúng một chỗ là đây.
      const trongONhap =
        dangGoTrongONhap(suKien.target) || dangGoTrongONhap(document.activeElement);
      const hanhDong = resolveKey(suKien, mode, trongONhap);
      if (hanhDong === null) return;
      // Phím ĐÃ XỬ LÝ thì chặn mặc định: `Space` cuộn trang, `[`/`]` không có mặc định nhưng
      // `Ctrl+1/2/3` thì có. KHÔNG chặn khi hành động là `null` (phím của trình duyệt/extension)
      // và KHÔNG chặn khi đang gõ trong ô nhập (dấu cách phải là dấu cách của phụ đề).
      suKien.preventDefault();
      xuLy(hanhDong);
    }
    document.addEventListener("keydown", khiBamPhim);
    return () => document.removeEventListener("keydown", khiBamPhim);
  }, [xuLy, mode]);
}
