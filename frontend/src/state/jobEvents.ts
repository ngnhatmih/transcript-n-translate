/**
 * Ghep mot su kien SSE vao ban do job — ham THUAN: khong React, khong DOM,
 * khong `fetch`.
 *
 * Vi sao tach rieng khoi `useJobStream.ts`: hook import `react` (CJS trong repo
 * nay) nen no chi duoc Playwright phu, con phep ghep su kien vao `Map` moi la
 * cho de sai — va no khong can React de test. Cung ly do plan dung de tach
 * parser SSE ra khoi hook.
 *
 * THU TU: su kien duoc ap theo dung thu tu nhan duoc. Backend gui chung theo
 * thu tu hang doi tren MOT ket noi (`backend/app/api/sse.py`, `stream_events`),
 * nen khong co chuyen "su kien cu de su kien moi" trong pham vi mot ket noi.
 */
import type { Job, JobEvent } from "../api/types.ts";

/**
 * Ap mot su kien len ban do job, tra ve ban do MOI.
 *
 * Bat bien:
 *   - `event.id === null` ⇒ tra `jobs` NGUYEN TRANG. `JobEvent.id` la
 *     `number | null`, nen `null` la du lieu that: khong co id thi khong co gi
 *     de cap nhat, va tra chinh map cu thi React khong ve lai vo ich.
 *   - Job CHUA CO trong map ⇒ bo qua. Su kien chi co cac khoa cua `JobEvent`,
 *     trong khi `Job` co nhieu khoa hon (xem `src/api/types.ts`) — dung mot
 *     `Job` tu su kien la BIA du lieu sai kieu. Job moi den tu anh chup
 *     `GET /api/jobs` ma `useJobStream` doc khi noi lai.
 *   - Job da co ⇒ chi ghi cac khoa ma su kien SO HUU. `workspace`, `type`,
 *     `attempts`, `created_at`, `payload`, … chi den tu anh chup, khong duoc
 *     dung toi.
 *   - KHONG sua `jobs` tai cho: tra `Map` moi va object job moi, vi React so
 *     sanh tham chieu.
 */
export function applyJobEvent(jobs: Map<number, Job>, event: JobEvent): Map<number, Job> {
  if (event.id === null) return jobs;

  const current = jobs.get(event.id);
  if (current === undefined) return jobs;

  const next = new Map(jobs);
  next.set(event.id, {
    ...current,
    state: event.state,
    progress: event.progress,
    phase: event.phase,
    error: event.error,
    log_tail: event.log_tail,
  });
  return next;
}
