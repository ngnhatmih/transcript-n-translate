/**
 * Hai hàm THUẦN suy ra "đang mở bản ghi nào" và "đang xem bản dịch nào" (Task W1).
 *
 * Vì sao tách ra khỏi `App.tsx`: hai câu hỏi này là hai QUY ƯỚC (mới nhất theo `id`), và
 * quy ước thì phải đo được. Chúng KHÔNG import React, KHÔNG `fetch`, KHÔNG đọc DOM ⇒ test
 * chạy bằng `node:test` thường, không cần jsdom (xem `channelData.test.ts`).
 *
 * ⚠️ **QUY ƯỚC "`id` LỚN NHẤT LÀ HIỆN TẠI" Ở ĐÂY PHẢI GIỐNG HỆT `ChannelZone.buocCuaKenh`**
 * (`src/shell/ChannelZone.tsx`): cùng một câu hỏi mà có hai quy ước khác nhau là **nguồn sự
 * thật thứ hai**. Cơ sở của quy ước là như nhau ở cả hai chỗ: `id` là `INTEGER PRIMARY KEY`
 * (rowid) của SQLite, nên hàng chèn SAU có `id` lớn hơn — đó là lý do "mới nhất" đọc được
 * từ dữ liệu mà không cần thêm khoá thời gian nào.
 *
 * ⚠️ **THỨ TỰ BACKEND TRẢ KHÔNG ĐƯỢC GIẢ ĐỊNH**: cả hai hàm duyệt HẾT mảng và so `id`,
 * không lấy phần tử đầu/cuối. Test cố ý dùng mảng KHÔNG sắp xếp theo `id` và đặt phần tử
 * "mới nhất" ở GIỮA để một bản "lấy hàng đầu" hay "lấy hàng cuối" đều đỏ.
 */
import type { TranscriptSummary, Translation } from "../api/types.ts";

/**
 * Bản ghi đang mở của MỘT kênh: hàng có `source_id === channelId` và `id` LỚN NHẤT.
 *
 * `channelId === null` (chưa chọn kênh) ⇒ `null` — và đó cũng là điều kiện để `App` KHÔNG
 * gọi endpoint theo `null` (xem `App.tsx`). Không có hàng nào khớp ⇒ `null`, KHÔNG bịa.
 */
export function chonTranscript(
  rows: TranscriptSummary[],
  channelId: number | null,
): TranscriptSummary | null {
  if (channelId === null) return null;
  let moiNhat: TranscriptSummary | null = null;
  for (const row of rows) {
    if (row.source_id !== channelId) continue;
    if (moiNhat === null || row.id > moiNhat.id) moiNhat = row;
  }
  return moiNhat;
}

/**
 * Bản dịch để XUẤT/ĐỐI CHIẾU: hàng có `status === "done"` và `id` LỚN NHẤT.
 *
 * Vì sao phải lọc `status`: `listTranslations` trả MỌI hàng của bản ghi, kể cả hàng vừa
 * được xếp (`queued`) hay đang chạy — chúng **chưa có nội dung dịch**. Lấy một hàng như vậy
 * làm nguồn cho `translationId` là ba nút xuất trỏ vào một bản dịch rỗng.
 *
 * Không có hàng `done` nào ⇒ `null` (nút xuất không có `href` — nói thật là chưa xuất được).
 */
export function chonTranslation(rows: Translation[]): Translation | null {
  let moiNhat: Translation | null = null;
  for (const row of rows) {
    if (row.status !== "done") continue;
    if (moiNhat === null || row.id > moiNhat.id) moiNhat = row;
  }
  return moiNhat;
}
