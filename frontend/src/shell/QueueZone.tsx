/**
 * Vùng HÀNG ĐỢI (phải, 286px): "cái gì đang chạy, cái gì chờ, VÌ SAO chờ?" — spec UI §3.
 *
 * Nguồn sự thật là BẢN ĐỒ JOB của `useJobStream` (ảnh chụp `GET /api/jobs` cộng các
 * sự kiện SSE). Không có request riêng nào ở đây: hai nơi cùng đọc hàng đợi là hai
 * nguồn sự thật, và chúng trôi khỏi nhau ngay khi một sự kiện tới.
 *
 * ## TASK D2 — HAI LỆNH TRÊN MỖI HÀNG JOB (`huỷ` · `chạy lại`)
 *
 * ĐO ĐƯỢC TRƯỚC D2: `endpoints.cancelJob` và `endpoints.retryJob` **0 lượt gọi trong sản phẩm**
 * (grep ngoài `endpoints.ts`) ⇒ không có cách nào tác động lên một job từ giao diện.
 *
 * Ba mệnh đề hình thức + trung thực mà vùng này ghim:
 *  1. **Nút CHỈ hiện ở trạng thái hợp lệ**: `queued`/`running` mới có nút `huỷ`;
 *     `failed`/`interrupted` mới có nút `chạy lại`. Đừng để người dùng bấm rồi ăn 409 — nhưng
 *     `App` **vẫn** xử lý 409, vì trạng thái phía client có thể CŨ (một tab khác vừa chạy lại job).
 *  2. 🔴 **CÂU CHỮ TRUNG THỰC**: `cancelJob` trên job `running` **CHỈ ĐẶT CỜ** — trạng thái job
 *     KHÔNG đổi. Nên câu duy nhất được phép là *"đã yêu cầu huỷ"*; *"đã dừng"* là **NÓI DỐI**,
 *     không phải một lựa chọn văn phong.
 *  3. **Trạng thái job KHÔNG được sửa tại chỗ**: `daYeuCauHuy` chỉ nói *"giao diện đã yêu cầu gì"*,
 *     và câu đó chỉ sống trong ĐÚNG lượt chạy đã xin huỷ: nó biến mất ngay khi `job.state` khác
 *     trạng thái lúc gửi (máy chủ đã trả lời bằng một sự kiện SSE), và **`App` DỌN hẳn mục đó**
 *     (effect theo `jobs`) nên một lượt chạy MỚI quay lại đúng trạng thái cũ **không** làm câu cũ
 *     sống lại (`I3` của review D2). Bản đồ `jobs` vẫn là của `useJobStream` — vùng này chỉ ĐỌC nó.
 *
 * ⚠️ `ponytail:` TRẦN — BỐ CỤC của một hàng (nút và câu trạng thái nằm ở đâu) **chỉ đo được
 * bằng ẢNH hoặc `getComputedStyle` trong Chrome thật** (`frontend/e2e/plans/bon-man.json`):
 * jsdom không có layout. (ĐÍNH CHÍNH Task 12, ERRATA #40: câu cũ *"chỉ ảnh chụp trong trình
 * duyệt thật mới xác nhận được"* ngụ ý trình duyệt thật BẤT KHẢ — SAI; nó chỉ bất khả DƯỚI
 * CÁC CHẾ ĐỘ SANDBOX HẠN CHẾ. ⚠️ Tầng đó CHƯA chạy trong lượt Task 12.) Luật CSS của vùng này (`.q*`) NAY
 * ĐÃ CÓ trong `app.css` (reset `<ul>` + MỘT hàng `flex`, `I1` của review D2) và có bài ghim KHAI BÁO
 * + QUAN HỆ hai chiều ở `QueueZone.test.tsx`. `.q__item` **KHÔNG** khai `grid-template-*` (cố ý
 * `flex`): một lưới track CỐ ĐỊNH thì thêm con thứ N là tái sinh ERRATA #31 mục 1.
 */
import type { Job, JobState } from "../api/types.ts";

export interface QueueZoneProps {
  /** Job theo id — đúng cái `useJobStream()` trả về, không sao chép. */
  jobs: Map<number, Job>;
  /**
   * Job nào đã được **GỬI YÊU CẦU HUỶ**, kèm **TRẠNG THÁI LÚC GỬI** (`App.huyJob`).
   *
   * ⚠️ Đây không phải trạng thái của job: câu *"đã yêu cầu huỷ"* chỉ được render khi
   * `job.state` VẪN BẰNG trạng thái lúc gửi — máy chủ xác nhận thì nó biến mất.
   *
   * ⚠️ Và nó phải BIẾN MẤT VĨNH VIỄN cho lượt chạy đó, không chỉ tới lần đổi trạng thái kế tiếp:
   * `App` DỌN mục nào có `job.state` khác trạng thái lúc gửi, nên `running + huỷ ⇒ failed ⇒
   * chạy lại ⇒ running` KHÔNG làm câu cũ hiện lại (`I3` của review D2). Vùng này chỉ ĐỌC bản đồ;
   * nếu nó tự quyết định "còn hiệu lực hay không" thì đó là nguồn sự thật thứ hai.
   */
  daYeuCauHuy: ReadonlyMap<number, JobState>;
  /** Câu lỗi **NGUYÊN VĂN** (`ApiError.message`, `"<status>: <detail>"`) của lệnh gần nhất, theo id job. */
  loiLenh: ReadonlyMap<number, string>;
  /** Yêu cầu huỷ một job — BÊN GỌI ghi (`App.huyJob`, đi qua hàng đợi ghi của D1). */
  onHuyJob: (id: number) => void;
  /** Yêu cầu chạy lại một job — BÊN GỌI ghi (`App.chayLaiJob`). */
  onChayLaiJob: (id: number) => void;
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

/** Job này có được phép HUỶ không — `queued` bị huỷ ngay, `running` chỉ được đặt cờ (hợp đồng §2). */
function huyDuoc(job: Job): boolean {
  return job.state === "queued" || job.state === "running";
}

/** Job này có được phép CHẠY LẠI không — backend chỉ nhận `failed`/`interrupted` (409 nếu khác). */
function chayLaiDuoc(job: Job): boolean {
  return job.state === "failed" || job.state === "interrupted";
}

export function QueueZone({ jobs, daYeuCauHuy, loiLenh, onHuyJob, onChayLaiJob }: QueueZoneProps) {
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
          <li
            key={job.id}
            className={`q__item q__item--${job.state}`}
            data-testid={`job-${job.id}`}
            /* Trạng thái MÁY đọc được của chính hàng — cùng nguồn với chữ bên trong (`lyDoCho`). */
            data-state={job.state}
          >
            <span className="q__ten">
              {`#${job.id} ${job.type}${job.engine === null ? "" : ` · ${job.engine}`}`}
            </span>
            {/* LÝ DO CHỜ là nội dung chính của vùng này (U2) — không phải tooltip. */}
            <span className="q__ly-do">{lyDoCho(job)}</span>
            {/* `progress` là số thực 0..1 backend đưa; đây chỉ là định dạng phần trăm. */}
            <span className="q__tien-do">{`${Math.round(job.progress * 100)}%`}</span>
            {huyDuoc(job) ? (
              <button
                type="button"
                className="lenh lenh--huy"
                data-testid={`huy-job-${job.id}`}
                onClick={() => onHuyJob(job.id)}
              >
                huỷ
              </button>
            ) : null}
            {chayLaiDuoc(job) ? (
              <button
                type="button"
                className="lenh lenh--lai"
                data-testid={`lai-job-${job.id}`}
                onClick={() => onChayLaiJob(job.id)}
              >
                chạy lại
              </button>
            ) : null}
            {/* 🔴 CÂU CHỮ TRUNG THỰC: "đã YÊU CẦU huỷ" — KHÔNG BAO GIỜ "đã dừng". Nó gắn với trạng
                thái LÚC GỬI, nên khi máy chủ xác nhận (SSE đổi `job.state`) thì nó BIẾN MẤT. ⚠️ Và
                nó biến mất VĨNH VIỄN cho lượt chạy đó — không phải "tới khi job quay lại đúng trạng
                thái này": `App` DỌN mục đã rời trạng thái lúc gửi (`I3` của review D2), nên một lượt
                `chạy lại` về `running` KHÔNG làm câu của lượt CŨ sống lại. */}
            {daYeuCauHuy.get(job.id) === job.state ? (
              <span className="lenh__tin" data-testid={`huy-tin-${job.id}`}>
                đã yêu cầu huỷ
              </span>
            ) : null}
            {/* LỖI CỦA LỆNH, NGUYÊN VĂN (`<status>: <detail>`) — khoá theo ĐÚNG id job, không phải
                một thông báo chung của vùng. */}
            {loiLenh.has(job.id) ? (
              <span className="lenh__tin" data-testid={`loi-lenh-${job.id}`}>
                {loiLenh.get(job.id)}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
