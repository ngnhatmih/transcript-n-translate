/**
 * Vùng KÊNH (trái, 214px): "tôi đang có những tệp nào?" — spec UI §3.
 *
 * Dữ liệu là `Source[]` THẬT từ `GET /api/sources`; không có bản sao nào ở client.
 *
 * `ponytail:` TRẦN — "trạng thái từng bước" (ASR xong chưa, dịch xong chưa) CHƯA hiện
 * được ở đây, và đây là lý do ĐO ĐƯỢC: `GET /api/sources` trả đúng tám khoá
 * (`src/api/types.ts::Source`) và KHÔNG có khoá trạng thái nào; `Job` thì có `state`
 * nhưng chỉ mang `workspace`, không mang `source_id`, nên client không có đường nối
 * job với source. Suy ra "bước" từ `duration`/`audio_path` là BỊA một đại lượng mà
 * backend chưa từng phát biểu. Nâng cấp: khi backend trả bước đã xong cho từng source
 * (hoặc `payload.source_id` thành hợp đồng), hiện đèn hai bước như mock của spec.
 *
 * Vì vậy ở đây chỉ hiện những gì backend THẬT SỰ nói: tên, cách vào (file/url), ngôn
 * ngữ, và độ dài. Chúng cũng là tín hiệu bước thật: `audio_path === null` nghĩa là
 * chưa tách được tiếng, `duration === null` nghĩa là chưa đo được độ dài.
 */
import type { Source } from "../api/types.ts";

export interface ChannelZoneProps {
  /** `null` = chưa có dữ liệu (đang đọc, hoặc lỗi — xem `loading`/`error`). */
  sources: Source[] | null;
  loading: boolean;
  error: string | null;
}

/** `duration` là GIÂY (số thực) do backend đo — client chỉ ĐỊNH DẠNG, không đo lại. */
function thoiLuong(giay: number | null): string {
  if (giay === null) return "chưa đo thời lượng";
  const tong = Math.round(giay);
  return `${Math.floor(tong / 60)}:${String(tong % 60).padStart(2, "0")}`;
}

export function ChannelZone({ sources, loading, error }: ChannelZoneProps) {
  if (error !== null) {
    return (
      <div className="ch">
        <p className="ch__loi" role="alert">{`không đọc được kênh: ${error}`}</p>
      </div>
    );
  }

  if (sources === null) {
    return (
      <div className="ch">
        {/* `loading` luôn đúng ở nhánh này với `useApi`; nhánh còn lại là phòng thủ. */}
        <p className="ch__cho">{loading ? "đang đọc kênh…" : "chưa có dữ liệu kênh"}</p>
      </div>
    );
  }

  if (sources.length === 0) {
    return (
      <div className="ch">
        <p className="ch__rong">chưa có kênh nào — nạp liệu ở màn hình Biên tập</p>
      </div>
    );
  }

  return (
    <div className="ch">
      <ul className="ch__danh-sach">
        {sources.map((source) => (
          <li key={source.id} className="ch__item">
            <span className="ch__ten">{source.origin}</span>
            <span className="ch__meta">
              {`${source.kind} · ${source.lang ?? "chưa rõ ngôn ngữ"} · ${thoiLuong(source.duration)}`}
            </span>
            <span className="ch__tieng">
              {source.audio_path === null ? "chưa tách tiếng" : "đã tách tiếng"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
