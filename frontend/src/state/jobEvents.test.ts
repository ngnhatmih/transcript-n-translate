/**
 * Test cua `applyJobEvent` — ham THUAN: khong DOM, khong React.
 *
 * Vi sao tach khoi `useJobStream.ts`: tep do import `react`, ma `react` la CJS
 * trong repo nay, nen hook chi duoc phu o TANG CHROME THAT (`frontend/e2e/`, Task 12 —
 * ⚠️ ĐÍNH CHÍNH Minor m3 của vòng sửa 1: câu cũ ghi *"Playwright ở Task 12"*, nhưng
 * **Playwright KHÔNG còn tồn tại trong repo**; tầng Chrome nay dùng **CDP thuần**).
 * Logic ghep su kien vao `Map` thi khong can React, va no la cho DE SAI: su kien
 * `id: null`, job chua co trong map, va map goc bi sua tai cho.
 *
 * Chay tu `frontend/`:
 *   node --import ./test/swc-loader.mjs --test --test-isolation=none src/state/jobEvents.test.ts
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import type { Job, JobEvent } from "../api/types.ts";
import { applyJobEvent } from "./jobEvents.ts";

/**
 * Mot `Job` DU MOI KHOA — dung lam anh chup. Cac gia tri duoc chon de phan biet
 * duoc voi gia tri cua su kien: neu ham lo lay mot truong tu su kien de ghi de
 * mot truong chi anh chup moi co, bai test se thay.
 *
 * Tap khoa cua `Job` dai hon han `JobEvent` — xem `src/api/types.ts`, hai
 * interface do. Do dai do la LY DO ham nay khong duoc bia mot `Job`.
 */
function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 1,
    workspace: 7,
    type: "asr",
    engine: "faster-whisper",
    phase: "chuan bi",
    state: "queued",
    cancel_requested: false,
    attempts: 3,
    progress: 0,
    log_tail: "log cu",
    error: null,
    payload: { source_id: 42 },
    created_at: "2026-01-01T00:00:00",
    started_at: null,
    finished_at: null,
    ...overrides,
  };
}

function makeEvent(overrides: Partial<JobEvent> = {}): JobEvent {
  return {
    id: 1,
    state: "running",
    progress: 0.5,
    phase: "asr",
    error: null,
    log_tail: "dong log moi",
    ...overrides,
  };
}

describe("applyJobEvent", () => {
  it("ghi dung nam khoa ma su kien so huu, giu nguyen phan chi anh chup moi co", () => {
    const jobs = new Map<number, Job>([[1, makeJob()]]);
    const next = applyJobEvent(
      jobs,
      makeEvent({ state: "running", progress: 0.5, phase: "asr", error: "loi", log_tail: "dong log moi" }),
    );

    const updated = next.get(1);
    assert.ok(updated !== undefined, "job da co trong map phai duoc cap nhat");
    assert.equal(updated.state, "running");
    assert.equal(updated.progress, 0.5);
    assert.equal(updated.phase, "asr");
    assert.equal(updated.error, "loi");
    assert.equal(updated.log_tail, "dong log moi");

    // Phan CHI anh chup moi co: su kien 6 khoa khong dui duoc mot `Job`, nen
    // ghi de chung la lam MAT du lieu (hoac bia ra du lieu sai kieu).
    assert.equal(updated.workspace, 7);
    assert.equal(updated.type, "asr");
    assert.equal(updated.attempts, 3);
    assert.equal(updated.engine, "faster-whisper");
    assert.equal(updated.created_at, "2026-01-01T00:00:00");
    assert.deepEqual(updated.payload, { source_id: 42 });
  });

  it("id null thi tra map NGUYEN TRANG, khong them khoa nao", () => {
    // `JobEvent.id` la `number | null` (xem `types.ts`), nen `null` la du lieu
    // THAT chu khong phai ca hiem. Khong co id thi khong co gi de cap nhat.
    const jobs = new Map<number, Job>([[1, makeJob()]]);
    const next = applyJobEvent(jobs, makeEvent({ id: null }));

    assert.equal(next, jobs, "khong co gi doi thi tra dung map cu, khong copy");
    assert.equal(next.size, jobs.size);
    assert.equal(next.has(1), true);
    assert.equal(next.get(1), jobs.get(1));
  });

  it("job chua co trong map thi BO QUA, khong bia mot Job tu su kien", () => {
    const jobs = new Map<number, Job>([[1, makeJob()]]);
    const next = applyJobEvent(jobs, makeEvent({ id: 99, state: "done", progress: 1 }));

    assert.equal(next.has(99), false, "khong duoc bia Job: su kien khong du khoa");
    assert.equal(next.size, jobs.size);
    assert.equal(next.get(1), jobs.get(1), "job khac khong duoc dung toi");
  });

  it("khong sua map goc va tra ve mot Map MOI", () => {
    // React so sanh THAM CHIEU: sua tai cho thi khong co lan ve lai nao, con tra
    // ve chinh map cu thi `useState` coi nhu khong doi. Ca hai deu la loi im lang.
    const original = makeJob();
    const jobs = new Map<number, Job>([[1, original]]);

    const next = applyJobEvent(jobs, makeEvent({ state: "done", progress: 1 }));

    assert.notEqual(next, jobs, "phai la Map MOI");
    assert.equal(jobs.get(1), original, "map goc khong duoc thay object Job");
    assert.equal(jobs.get(1)?.state, "queued", "map goc khong duoc doi state");
    assert.equal(jobs.get(1)?.progress, 0, "map goc khong duoc doi progress");
    assert.notEqual(next.get(1), original, "ban ghi moi phai la object MOI");
    assert.equal(next.get(1)?.state, "done");
  });
});
