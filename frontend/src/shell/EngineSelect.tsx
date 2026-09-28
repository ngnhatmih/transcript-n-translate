/**
 * `<EngineSelect/>` — dropdown engine ở header (spec UI §3).
 *
 * LUẬT CỦA TASK 10: **chỉ** liệt kê engine `capabilities.available === true`, và
 * `available` **đọc THẲNG** từ `/api/registry`. Client **KHÔNG** suy lại từ
 * `runtime`/`model_ref`: bản vá Task 12 GĐ2 đã làm `available` nghĩa là "phục vụ được job
 * NGAY BÂY GIỜ" (tiến trình tới được **VÀ** `model_ref` đã pull) — suy lại ở client là
 * **nguồn sự thật thứ hai** cho cùng một đại lượng (Global Constraints dòng 25, ERRATA #30 mục 4).
 *
 * ⚠️ VÌ SAO `=== true` CHỨ KHÔNG `!== false`: `_mark_availability` chỉ ghi khoá `available`
 * cho engine `kind == "mt"` ⇒ mọi spec ASR **THIẾU** khoá này (ERRATA #2 mục 3). "Thiếu
 * khoá" nghĩa là **chưa đo được**, không phải "dùng được" ⇒ ASR không xuất hiện ở dropdown
 * này. Đó là hệ quả ĐO ĐƯỢC của luật, không phải suy diễn — xem báo cáo Task 10 (số spec
 * ASR và việc cả nhóm thiếu khoá được đo trên `/api/registry` thật bằng một lệnh).
 *
 * `ponytail:` TRẦN — component này **CHƯA có người gọi trong sản phẩm**: đường CHỌN
 * KÊNH/ENGINE chưa tồn tại (`selectChannel` có **0** lượt dispatch — ERRATA #18 mục 4).
 * Brief Task 10 chỉ đòi nó được **dựng ra**, nên nó KHÔNG được gắn vào `Header`/`App`:
 * gắn vào mà không có đường dispatch thì đó là mở thêm một đường ống mới không ai nói ra.
 * Hợp đồng của nó vì thế phải ĐẦY ĐỦ (`value` + `onValueChange`) — một ô chọn được mà
 * giá trị không được gửi đi là **một lời nói dối về khả năng sửa** (ERRATA #23 mục 3).
 * Nâng cấp: nối vào đường CHỌN KÊNH khi đường đó ra đời.
 */
import type { EngineSpec } from "../api/types.ts";

export interface EngineSelectProps {
  /** Mọi spec của registry (đã gộp `asr` + `mt`) — lọc ở ĐÂY, không lọc ở nơi gọi. */
  specs: EngineSpec[];
  /** `id` của engine đang chọn (điều khiển từ ngoài, như mọi `<select>` của React). */
  value: string;
  onValueChange: (id: string) => void;
}

export function EngineSelect({ specs, value, onValueChange }: EngineSelectProps) {
  const dungDuoc = specs.filter((s) => s.capabilities.available === true);

  return (
    <label className="eng">
      <span className="eng__nhan">ENGINE</span>
      <select
        className="eng__chon"
        value={value}
        // Không có lựa chọn nào thật thì ô chọn phải VÔ HIỆU: một ô chọn được mà không
        // có gì để chọn là một điều khiển nói dối.
        disabled={dungDuoc.length === 0}
        onChange={(e) => onValueChange(e.target.value)}
      >
        {dungDuoc.length === 0 ? (
          <option value="">không có engine nào dùng được</option>
        ) : (
          dungDuoc.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))
        )}
      </select>
    </label>
  );
}
