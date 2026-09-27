/**
 * Vùng HÀNG ĐỢI (phải, 286px): "cái gì đang chạy, cái gì chờ, VÌ SAO chờ?" — spec UI §3.
 *
 * Nguồn sự thật là BẢN ĐỒ JOB của `useJobStream` (ảnh chụp `GET /api/jobs` cộng các
 * sự kiện SSE). Không có request riêng nào ở đây: hai nơi cùng đọc hàng đợi là hai
 * nguồn sự thật, và chúng trôi khỏi nhau ngay khi một sự kiện tới.
 */
import type { Job } from "../api/types.ts";

export interface QueueZoneProps {
  /** Job theo id — đúng cái `useJobStream()` trả về, không sao chép. */
  jobs: Map<number, Job>;
}

/**
 * LÝ DO CHỜ — suy từ `phase` + `state`, không từ `progress`/`log_tail`.
 *
 * Vì sao `phase` chứ không tự đoán: backend đã tính giai đoạn của từng job
 * (`domain/job_state.phase_of` = "<type>:<engine|->"), và nó gom lô THEO giai đoạn —
 * nên giai đoạn chính là câu trả lời cho "vì sao chờ". Spec UI §3 vẽ đúng câu đó
 * ("⏸ MT·qwen2.5-7b — chờ gom lô").
 *
 * `phase === "-"` được coi là CHƯA RÕ giai đoạn: dạng của `phase_of` là
 * "<type>:<engine|->", nên một dấu "-" trơ là chỗ engine vắng — đừng in nó ra như một
 * giai đoạn có thật.
 */
export function lyDoCho(job: Job): string {
  const phase = job.phase === "-" || job.phase === "" ? "" : ` · ${job.phase}`;
  switch (job.state) {
    case "running":
      return `đang chạy${phase}`;
    case "queued":
      return `chờ gom lô${phase}`;
    case "failed":
      return job.error === null ? "lỗi" : `lỗi · ${job.error}`;
    case "interrupted":
      return "bị ngắt";
    case "cancelled":
      return "đã huỷ";
    case "done":
      return "xong";
  }
}

/** Job đang chạy lên trước, rồi tới job chờ, rồi tới phần còn lại — trong nhóm thì theo id. */
function thuTu(job: Job): number {
  if (job.state === "running") return 0;
  if (job.state === "queued") return 1;
  return 2;
}

export function QueueZone({ jobs }: QueueZoneProps) {
  const hang = [...jobs.values()].sort((a, b) => thuTu(a) - thuTu(b) || a.id - b.id);

  if (hang.length === 0) {
    return (
      <div className="q">
        <p className="q__rong">hàng đợi trống</p>
      </div>
    );
  }

  return (
    <div className="q">
      <ul className="q__danh-sach">
        {hang.map((job) => (
          <li key={job.id} className={`q__item q__item--${job.state}`}>
            <span className="q__ten">
              {`#${job.id} ${job.type}${job.engine === null ? "" : ` · ${job.engine}`}`}
            </span>
            {/* LÝ DO CHỜ là nội dung chính của vùng này (U2) — không phải tooltip. */}
            <span className="q__ly-do">{lyDoCho(job)}</span>
            {/* `progress` là số thực 0..1 backend đưa; đây chỉ là định dạng phần trăm. */}
            <span className="q__tien-do">{`${Math.round(job.progress * 100)}%`}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
