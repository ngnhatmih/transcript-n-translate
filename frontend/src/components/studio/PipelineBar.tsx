/**
 * SÁU BƯỚC của đường ống trên header — bản tách riêng khỏi `Header.tsx` để header chỉ
 * còn việc bố cục.
 *
 * 🔴 NGUỒN GỐC: `_lovable-code/src/components/studio/PipelineBar.tsx` (53 dòng).
 *
 * 📏 SỐ ĐO trên bản đã duyệt (`getBoundingClientRect`, 1680×1050):
 *      một bước       : 120×35, pad 4px 8px, gap 8px, radius 2px, hover `--panel-2`
 *      chấm trạng thái: 16×16, bo tròn hoàn toàn, viền 1px
 *      dòng tên       : 12px / 500 / `--ink-0`
 *      dòng ghi chú   : 9,5px / 400 / `--ink-2`, mono
 *
 * ## Bốn trạng thái = BỐN HÌNH DẠNG, không phải bốn sắc
 *
 * | trạng thái  | chấm                    | ghi chú          | nghĩa                      |
 * |-------------|-------------------------|------------------|----------------------------|
 * | `xong`      | đặc `--ok`, có dấu ✓    | `--ink-2`        | đã làm xong                |
 * | `dang-chay` | rỗng viền `--ok`, nhấp nháy | `--ink-2`    | đang chạy / chờ tới lượt   |
 * | `bi-chan`   | đặc `--signal`          | `--signal`       | CẦN người dùng làm gì đó   |
 * | `chua`      | rỗng viền `--ink-2`     | `--ink-2`        | chưa tới lượt              |
 *
 * Chấm LUÔN có viền (kể cả khi rỗng) nên sáu chấm thẳng hàng và bề rộng không nhảy khi
 * trạng thái đổi — đó là lý do `border` nằm ngoài mọi nhánh `[data-trang-thai]`.
 *
 * ⚠️ Nhấp nháy là tín hiệu THỨ HAI. Tín hiệu thứ nhất là `aria-label` đọc ra "đang chạy",
 * và `prefers-reduced-motion` (đầu `app.css`) tắt animation.
 */
import type { BuocDuongOng, TrangThaiBuoc } from "../../lib/studio.ts";

/** Nhãn đọc được cho trình đọc màn hình — KHÔNG hiện trên màn. */
const NHAN: Record<TrangThaiBuoc, string> = {
  xong: "xong",
  "dang-chay": "đang chạy",
  "bi-chan": "bị chặn",
  chua: "chưa làm",
};

/** Dấu ✓ vẽ nội tuyến. */
function Tick() {
  return (
    <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true" focusable="false">
      <path d="M1.6 5.2 L3.9 7.5 L8.4 2.6" fill="none" stroke="currentColor" strokeWidth="1.7"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export interface PipelineBarProps {
  buoc: readonly BuocDuongOng[];
  /** Bấm một bước ⇒ nhảy tới chỗ liên quan. Không truyền thì các bước chỉ để đọc. */
  onBuoc?: (id: string) => void;
}

export function PipelineBar({ buoc, onBuoc }: PipelineBarProps) {
  return (
    <ol className="do__danh-sach" aria-label="Đường ống xử lý">
      {buoc.map((b) => (
        <li key={b.id} className="do__o">
          <button
            type="button"
            className="do__buoc"
            data-trang-thai={b.trangThai}
            onClick={onBuoc === undefined ? undefined : () => onBuoc(b.id)}
            aria-label={`${b.ten} — ${NHAN[b.trangThai]}${b.ghiChu === "" ? "" : `, ${b.ghiChu}`}`}
          >
            <span className="do__cham" aria-hidden="true">
              {b.trangThai === "xong" ? <Tick /> : null}
            </span>
            <span className="do__chu">
              <span className="do__ten">{b.ten}</span>
              {b.ghiChu === "" ? null : <span className="do__ghi-chu">{b.ghiChu}</span>}
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
