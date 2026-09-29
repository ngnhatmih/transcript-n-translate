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
 * ## Vì sao deps là `[xuLy, mode]` — và vì sao KHÔNG có `useRef` giữ handler
 *
 * `App` truyền một hàm MỚI ở mỗi lượt render (nó đóng trên state của lượt đó), nên effect chạy lại
 * mỗi lượt render: **gỡ listener cũ rồi gắn listener mới**. Điều đó giữ nguyên cửa sổ một-lượt-commit
 * mà bài ghim `D1 NỀN MỚI HƠN (CỬA SỔ CHƯA GẮN LẠI)` đo: tại lượt commit có dữ liệu mới, listener
 * CŨ vẫn còn gắn (passive effect chưa flush), nên NỀN của lệnh ghi phải đọc từ ảnh chụp mới nhất
 * (`App.banGhiMoiNhat` — `useRef` gán ngay trong thân render).
 *
 * 🔴 **ĐÍNH CHÍNH (vòng sửa 1, `I-2`).** Chỗ này TRƯỚC ĐÂY khai: *"nếu thay bằng ref + deps `[]` thì
 * mutant `G1-BASE-CLOSURE` hết ĐỎ — tức bản refactor làm MẤT ĐỘ PHỦ của bài ghim"*. **SAI với chính
 * hình dạng được mô tả**, và tôi đã TỰ ĐO LẠI cả hai chiều trên cây này (`npm test` không cần —
 * `src/shell/App.test.tsx`, 66 bài; `G1-BASE-CLOSURE` = `const nenMayChu = hienTai;`):
 *   - `E11A` = `useRef` gán **trong THÂN render** + deps `[mode]` ⇒ **0 bài đỏ**;
 *   - `E11A + G1-BASE-CLOSURE` ⇒ **0 bài đỏ** (tái lập đúng con số cũ);
 *   - `E11B` = `useRef` gán **trong EFFECT** + **GIỮ** deps `[xuLy, mode]` + `G1-BASE-CLOSURE`
 *     ⇒ **1 bài đỏ**: `D1 NỀN MỚI HƠN (CỬA SỔ CHƯA GẮN LẠI)…`.
 * **Cơ chế:** với ref gán trong thân render, tại thời điểm phím thứ hai rơi (sau commit DOM, TRƯỚC
 * khi passive effect flush) `xuLyRef.current` **ĐÃ** là handler của lượt render mới ⇒ closure
 * `hienTai` = `transcript.data` **MỚI** ⇒ "đọc closure thay vì ref" **không còn khác biệt hành vi**.
 * Vậy `E11A` là **MUTANT TƯƠNG ĐƯƠNG** (một bản vá KHÁC cùng chữa một lỗi), **KHÔNG** phải "mất độ
 * nhạy": vế ngược được chứng minh bằng `E11B`, nơi handler THẬT SỰ cũ và bài ghim **vẫn đỏ**.
 *
 * ⇒ **Quyết định:** giữ `[xuLy, mode]` — nó là đường ĐƠN GIẢN NHẤT (không cần ref), và nó không
 * phải một ràng buộc sống-còn như câu cũ khai. ⚠️ **NỢ `#46` mục 10b:** vế (i) ("trên cây CHƯA sửa,
 * mutant cũ giết được bài") đã được tôi đo lại TRÊN CÂY `dedad0c` trong một worktree scratch:
 * `PREFIX-D1-DEPS-NUDGE-STALE` (bỏ `transcript.data` khỏi deps) ⇒ **1 tên đỏ**:
 * `D1 NỀN MỚI HƠN: bản ghi MÁY CHỦ mới hơn nền …` (`tests 54 / pass 53 / fail 1`); trên cây ĐÃ sửa
 * cùng hình dạng mutant đó **trơ** (nền đọc từ `useRef`), còn `G1-BASE-CLOSURE` mới là thứ ĐỎ.
 * Đo trên MỘT tệp (`App.test.tsx`), không phải toàn suite — ERRATA #46 mục 10b ghi **3 tên đỏ** cho
 * lượt toàn suite; hai tên còn lại không thuộc phạm vi đo này.
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
 * **HAI PHÍM KÍCH HOẠT của control native** (spec HTML): `Enter` và `Space`. Đây không phải "phím
 * nóng của app" mà là **cơ chế bấm của trình duyệt** cho `<button>`/`<a href>`/`<select>`/…
 * (`Enter` kích hoạt liên kết, `Space` kích hoạt nút).
 */
const PHIM_KICH_HOAT_CONTROL: ReadonlySet<string> = new Set(["Enter", " "]);

/**
 * Những phần tử mà TRÌNH DUYỆT kích hoạt bằng `Enter`/`Space`. `closest` đi LÊN cây nên nó bắt cả
 * `<span>` bên trong một `<button>` (nơi `keydown` thật sự nhắm tới).
 */
const CONTROL_NATIVE =
  'button, a[href], select, summary, input[type="button"], input[type="submit"], '
  + 'input[type="reset"], input[type="checkbox"], input[type="radio"]';

/**
 * Phím này có thuộc về một CONTROL NATIVE đang có tiêu điểm không (vòng sửa 1, `I-1`).
 *
 * 🔴 VÌ SAO CẦN (lỗi SẢN PHẨM đo được, không phải một lo ngại): `useShortcuts` gọi
 * `preventDefault()` cho **MỌI** phím tra được, và `Enter`/`Space` đều tra được ở `mode === "edit"`
 * (`startEdit`/`togglePlay`). `preventDefault()` trên `keydown` của một `<button>` **chặn chính cú
 * bấm của trình duyệt** ⇒ nút đang có tiêu điểm KHÔNG kích hoạt được — kể cả nút `đóng` của bảng
 * §11.4 (nó có `autoFocus`, nên tiêu điểm LUÔN ở đó khi bảng vừa mở). Probe hai chiều: bỏ guard ⇒
 * `defaultPrevented === true` và handler nhận `["startEdit","togglePlay"]`; có guard ⇒ `false`.
 *
 * Ba vế, mỗi vế có lý do riêng:
 *  - **`target`**, không `document.activeElement`: `keydown` của một cú bấm THẬT luôn được gửi tới
 *    phần tử đang có tiêu điểm, nên `target` là chỗ duy nhất cú bấm đó tồn tại. (Guard Ô NHẬP thì
 *    cần CẢ HAI vế — `#45` mục 1(b) — vì ở đó có ca ĐO ĐƯỢC: một sự kiện phát ra từ `body` trong
 *    khi tiêu điểm ở trong ô nhập. Với control native, ca tương ứng là một sự kiện TỔNG HỢP không
 *    có trong trình duyệt thật, nên thêm nửa đó chỉ tạo một mệnh đề không falsify được.)
 *  - **`closest`, không `===`**: `keydown` nhắm tới phần tử SÂU NHẤT, nên một chữ `<span>` trong
 *    nút vẫn là một cú bấm vào nút.
 *  - **Không có `Ctrl`/`Alt`/`Meta`**: phím nóng của app có phím bổ trợ (`Ctrl+Enter` = chạy job)
 *    và tổ hợp đó KHÔNG phải cú kích hoạt của control ⇒ nó vẫn thuộc về app.
 */
function phimCuaControlNative(suKien: KeyboardEvent): boolean {
  if (suKien.ctrlKey || suKien.altKey || suKien.metaKey) return false;
  if (!PHIM_KICH_HOAT_CONTROL.has(suKien.key)) return false;
  const dich = suKien.target;
  return dich instanceof HTMLElement && dich.closest(CONTROL_NATIVE) !== null;
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
      // (0) CONTROL NATIVE ĐANG CÓ TIÊU ĐIỂM ⇒ `Enter`/`Space` là cú bấm CỦA NÓ, không phải phím
      //     nóng của app. Phải đứng TRƯỚC `resolveKey` và trước `preventDefault` — xem docblock
      //     của `phimCuaControlNative` (`I-1`).
      if (phimCuaControlNative(suKien)) return;
      // HAI VẾ của guard ô nhập — xem docblock đầu tệp. `resolveKey` vẫn nhận `inField` như một
      // THAM SỐ (nó thuần, không đọc DOM); phép đọc DOM nằm ở đúng một chỗ là đây.
      const trongONhap =
        dangGoTrongONhap(suKien.target) || dangGoTrongONhap(document.activeElement);
      const hanhDong = resolveKey(suKien, mode, trongONhap);
      if (hanhDong === null) return;
      // Phím ĐÃ XỬ LÝ thì chặn mặc định: `Space` cuộn trang, `[`/`]` không có mặc định nhưng
      // `Ctrl+1/2/3` thì có. KHÔNG chặn khi hành động là `null` (phím của trình duyệt/extension),
      // KHÔNG chặn khi đang gõ trong ô nhập (dấu cách phải là dấu cách của phụ đề), và KHÔNG chặn
      // khi phím thuộc một control native đang có tiêu điểm (vế (0) ở trên).
      suKien.preventDefault();
      xuLy(hanhDong);
    }
    document.addEventListener("keydown", khiBamPhim);
    return () => document.removeEventListener("keydown", khiBamPhim);
  }, [xuLy, mode]);
}
