/**
 * Ghep mot su kien SSE vao ban do job — ham THUAN: khong React, khong DOM,
 * khong `fetch`.
 *
 * Vi sao tach rieng khoi `useJobStream.ts`: phep ghep su kien vao `Map` la cho
 * de sai — va no khong can React de test, nen no duoc ghim bang `node:test`
 * thuan. (Hook thi nay cung duoc thi hanh that: xem
 * `src/state/useJobStream.test.ts`.)
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
 *   - `event.id === null` ⇒ tra `jobs` NGUYEN TRANG. Day truoc het la mot GUARD
 *     HEP KIEU: `JobEvent.id` la `number | null`, con `Map<number, Job>.get` doi
 *     `number`, nen bo nhanh nay thi `tsc` do `TS2345` (do duoc: review Task 3
 *     chay mutant chi-bo-guard va `typecheck` do hai diem). Ve HANH VI, hieu ung
 *     runtime cua no TRUNG voi nhanh "job chua co" ngay duoi (`Map.get(null)`
 *     tra `undefined`), nen hai bai test `id: null` va `job la` kiem CUNG MOT
 *     duong — dung ban chung nhu hai bat bien doc lap.
 *   - Job CHUA CO trong map ⇒ bo qua. Su kien chi co cac khoa cua `JobEvent`,
 *     trong khi `Job` co nhieu khoa hon (xem `src/api/types.ts`) — dung mot
 *     `Job` tu su kien la BIA du lieu sai kieu. Job moi den tu anh chup
 *     `GET /api/jobs`: `useJobStream` doc anh chup NGAY khi gap mot id la, chu
 *     khong doi den lan noi lai (xem `refreshSnapshot` o do).
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
