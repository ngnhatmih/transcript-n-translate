/**
 * Test HANH VI THAT cua `useJobStream` — hook nay truoc day chua duoc thi hanh o
 * dau, nen hai loi cua no (`I-2`: job MOI khong bao gio vao map; `I-3`: `attempt`
 * khong bao gio reset) chi la RUI RO DOC MA. Tep nay khien chung DO DUOC.
 *
 * Cach do: mot server `node:http` THAT trong tien trinh (`listen(0)` xin cong
 * trong, khong giam 8620 cua ai) phuc vu `/api/jobs` + `/api/jobs/stream`, va
 * hook chay that qua `renderHook`. Khong mock module nao; `globalThis.fetch`
 * chi bi boc de resolve URL TUONG DOI theo origin cua server test — do la CAU
 * NOI URL, khong phai gia lap mang (xem `test/dom.ts`).
 *
 * Thu tu bat buoc: `setupDom` TRUOC khi import `@testing-library/react` va hook
 * (React doc `window`/`document` luc nap) ⇒ hai import do la `await import(...)`
 * ben trong `before`.
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import type { ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import type { Socket } from "node:net";

import { setupDom, teardownDom } from "../../test/dom.ts";

/** Mot `Job` du 15 khoa — hook khong kiem tra khoa, nhung de giong du lieu that. */
function makeJob(id: number, state = "queued"): Record<string, unknown> {
  return {
    id,
    workspace: 1,
    type: "export",
    engine: null,
    phase: "-",
    state,
    cancel_requested: false,
    attempts: 0,
    progress: 0,
    log_tail: "",
    error: null,
    payload: {},
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

/** Mot su kien SSE that — dung dinh dang `format_sse` cua backend. */
function sse(event: unknown): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

function jobEvent(id: number, state: string, progress: number): Record<string, unknown> {
  return { id, state, progress, phase: "-", error: null, log_tail: "" };
}

const state = {
  /** anh chup tra ve theo tung lan goi; lan cuoi duoc dung lai mai. */
  snapshots: [[]] as unknown[][],
  /** so lan goi DAU tien tra 500 (de ep backoff leo thang). */
  jobsFailures: 0,
  jobsCalls: 0,
  jobsTimestamps: [] as number[],
  streamCalls: 0,
  streamTimestamps: [] as number[],
  /** dong stream ngay sau khi mo (de do "ket noi thanh cong roi dut"). */
  closeStreamImmediately: false,
  openStreams: new Set<ServerResponse>(),
  closedStreams: 0,
  sockets: new Set<Socket>(),
};

function resetState(): void {
  for (const res of [...state.openStreams]) {
    try {
      res.end();
    } catch {
      // da dong roi
    }
  }
  state.openStreams.clear();
  state.snapshots = [[]];
  state.jobsFailures = 0;
  state.jobsCalls = 0;
  state.jobsTimestamps = [];
  state.streamCalls = 0;
  state.streamTimestamps = [];
  state.closeStreamImmediately = false;
  state.closedStreams = 0;
}

/** Ghi su kien vao MOI stream dang mo. */
function emit(body: string): void {
  for (const res of state.openStreams) res.write(body);
}

const server = createServer((req, res) => {
  const url = req.url ?? "";
  if (url === "/api/jobs/stream") {
    state.streamCalls += 1;
    state.streamTimestamps.push(Date.now());
    if (state.closeStreamImmediately) {
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
      res.write(": connected\n\n");
      res.end();
      return;
    }
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
    res.write(": connected\n\n");
    state.openStreams.add(res);
    res.on("close", () => {
      state.closedStreams += 1;
      state.openStreams.delete(res);
    });
    return;
  }
  if (url.startsWith("/api/jobs")) {
    state.jobsCalls += 1;
    state.jobsTimestamps.push(Date.now());
    if (state.jobsFailures > 0) {
      state.jobsFailures -= 1;
      res.writeHead(500, { "content-type": "text/plain" });
      res.end("loi co y");
      return;
    }
    const index = Math.min(state.jobsCalls - 1, state.snapshots.length - 1);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(state.snapshots[index] ?? []));
    return;
  }
  res.writeHead(404, { "content-type": "text/plain" });
  res.end("khong co route nay");
});

server.on("connection", (socket) => {
  state.sockets.add(socket);
  socket.on("close", () => state.sockets.delete(socket));
});

let origin = "";
let renderHook: (callback: () => unknown) => { result: { current: any }; unmount: () => void };
let waitFor: (callback: () => void, options?: { timeout?: number; interval?: number }) => Promise<void>;
let cleanup: () => void;
let useJobStream: () => Map<number, any>;

// ⚠️ HOOK ĐÃ ĐƯỢC CHUYỂN VÀO `describe()` — chúng nằm NGAY DƯỚI, không ở cấp tệp.
//
// ĐO ĐƯỢC (không phải suy diễn, xem ERRATA #9 mục 1/6): dưới `--test-isolation=none`
// hook cấp TỆP bị node:test kéo lên GỐC cả lượt chạy. Với `before` ở cấp tệp, jsdom +
// cầu nối URL được cài lúc t≈0 và SỐNG TỚI CUỐI LƯỢT; một tệp DOM khác chạy TRƯỚC tệp
// này mà gọi `teardownDom()` để chuẩn hoá thì ĐÓNG LUÔN jsdom đó, và cả năm bài dưới
// đây chết `ReferenceError: document is not defined` dù chúng không sai gì.
// Đó là lần đo thật của Task 4: thêm `src/shell/App.test.tsx` (đứng TRƯỚC theo thứ tự
// đường dẫn) làm đỏ đúng năm bài này. Bọc hook trong `describe()` thì hook mới thật sự
// theo suite — và tệp này không còn áp một jsdom lên các tệp khác nữa.
//
// `teardownDOMSafe` giữ ở cấp tệp vì nó KHÔNG đặt/trả global: nó chỉ gọi `teardownDom`.

/** `teardownDom` tra `globalThis.fetch` ve nguyen ban — BAT BUOC vi `--test-isolation=none`. */
function teardownDOMSafe(): void {
  teardownDom();
}

const waitUntil = (condition: () => boolean, timeout = 5000, interval = 20): Promise<void> =>
  waitFor(
    () => {
      assert.ok(condition(), "dieu kien chua dat");
    },
    { timeout, interval },
  );

describe("useJobStream (server HTTP that trong tien trinh)", () => {
  before(async () => {
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
    const address = server.address() as AddressInfo;
    origin = `http://127.0.0.1:${address.port}`;
    // Chuan hoa TRUOC khi cai: khong dua vao viec tep khac da tra global hay chua.
    teardownDom();
    setupDom(origin);
    const rtl: any = await import("@testing-library/react");
    const api = rtl.renderHook === undefined ? rtl.default : rtl;
    renderHook = api.renderHook;
    waitFor = api.waitFor;
    cleanup = api.cleanup;
    const hook: any = await import("./useJobStream.ts");
    useJobStream = hook.useJobStream;
  });

  afterEach(() => {
    cleanup();
  });

  after(async () => {
    for (const res of [...state.openStreams]) {
      try {
        res.end();
      } catch {
        // da dong roi
      }
    }
    state.openStreams.clear();
    for (const socket of [...state.sockets]) socket.destroy();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    teardownDOMSafe();
  });

  beforeEach(() => {
    resetState();
  });

  it("anh chup dau tien vao map", async () => {
    state.snapshots = [[makeJob(1)]];
    const { result, unmount } = renderHook(() => useJobStream());

    await waitUntil(() => result.current.has(1));
    assert.equal(result.current.get(1)?.state, "queued");
    assert.equal(state.jobsCalls, 1, "phai doc anh chup dung mot lan");
    assert.equal(state.streamCalls, 1, "phai mo dung mot stream");
    unmount();
  });

  it("I-2: job MOI vao map qua lan doc lai anh chup, va GOP nhieu su kien la vao MOT request", async () => {
    // Anh chup thu nhat KHONG co job 2; lan doc lai thi CO.
    state.snapshots = [[makeJob(1)], [makeJob(1), makeJob(2)]];
    const { result, unmount } = renderHook(() => useJobStream());

    await waitUntil(() => result.current.has(1));
    assert.equal(state.jobsCalls, 1, "truoc khi co su kien la: dung mot lan doc anh chup");
    assert.equal(state.streamCalls, 1);

    // HAI su kien cho job 2 (id CHUA co trong map) di trong CUNG mot lan ghi ⇒
    // chung roi vao cung mot vong lap doc. Neu hook doc lai anh chup cho TUNG su
    // kien la thi `jobsCalls` se thanh 3; dung thiet ke thi chi 2.
    emit(
      sse(jobEvent(2, "running", 0.1))
      + sse(jobEvent(2, "done", 0.9)),
    );

    await waitUntil(() => result.current.get(2)?.progress === 0.9, 5000);

    assert.equal(state.jobsCalls, 2, "phai doc lai anh chup dung MOT lan (gop), khong phai hai");
    assert.equal(
      result.current.get(2)?.state,
      "done",
      "su kien da xep hang phai duoc ap SAU anh chup (neu khong thi map dung o trang thai cua anh chup)",
    );
    assert.equal(result.current.get(2)?.id, 2);
    unmount();
  });

  it("X1: su kien cho id DA BIET ⇒ cap nhat job do VA khong doc lai anh chup", async () => {
    // LO HONG DO PHU ma review Task 3 tim duoc: duong "id DA BIET ⇒ ap thang vao map"
    // khong bai nao ghim — xoa `publish(applyJobEvent(current, event))` van `4/4` xanh.
    // Bai nay ghim no bang HAI bang chung doc lap:
    //   (a) job trong map DOI that (state + progress), va
    //   (b) BO DEM request cua server KHONG tang ⇒ khong he co lan doc anh chup nao.
    // Dem la bang chung, khong phai suy luan. Mutation: xoa loi goi ap thang ⇒ bai nay DO.
    state.snapshots = [[makeJob(1)]];
    const { result, unmount } = renderHook(() => useJobStream());

    await waitUntil(() => result.current.has(1));
    assert.equal(result.current.get(1)?.state, "queued", "tien de: anh chup cho job 1 o queued");
    const docAnhChup = state.jobsCalls;

    emit(sse(jobEvent(1, "running", 0.42)));

    await waitUntil(() => result.current.get(1)?.state === "running");
    assert.equal(result.current.get(1)?.progress, 0.42, "su kien phai duoc ap THANG vao job da co");

    // Cho qua mot vong request (neu co) roi moi dem: mot lan doc anh chup sai cho se
    // tang bo dem ngay trong vong vai mili giay, khong phai sau 500ms cua `later`.
    await new Promise((resolve) => setTimeout(resolve, 200));
    assert.equal(state.jobsCalls, docAnhChup, "id DA BIET ⇒ khong duoc doc lai anh chup /api/jobs");
    unmount();
  });

  it("I-3: sau mot ket noi THANH CONG, lan noi lai dau tien dung delay nho nhat", async () => {
    state.snapshots = [[makeJob(1)]];
    // Hai lan doc anh chup dau tra 500 ⇒ `attempt` leo len 2 (delay 500ms roi 1000ms).
    state.jobsFailures = 2;
    // Ket noi thu ba thanh cong (co stream that) roi dut ngay.
    state.closeStreamImmediately = true;

    const { unmount } = renderHook(() => useJobStream());

    // Cho toi khi co it nhat bon lan doc anh chup: #1/#2 hong, #3 thanh cong, #4 la
    // lan noi lai dau tien sau khi ket noi thanh cong.
    await waitUntil(() => state.jobsCalls >= 4, 8000);

    const afterSuccess = state.jobsTimestamps[3]!;
    const success = state.jobsTimestamps[2]!;
    const gap = afterSuccess - success;

    assert.ok(
      gap >= 300,
      `lan noi lai phai DI QUA mot do tre (khong duoc noi lai tuc thi), do duoc ${gap}ms`,
    );
    assert.ok(
      gap < 1500,
      `sau ket noi thanh cong, delay phai ve muc nho nhat (khoang 500ms); do duoc ${gap}ms `
      + "⇒ backoff da leo thang don dieu, tuc `attempt` khong duoc reset",
    );
    unmount();
  });

  it("unmount: server thay ket noi DONG, va khong co request moi nao sau do", async () => {
    state.snapshots = [[makeJob(1)]];
    const { result, unmount } = renderHook(() => useJobStream());

    await waitUntil(() => result.current.has(1));
    await waitUntil(() => state.openStreams.size === 1);

    const jobsBefore = state.jobsCalls;
    const streamBefore = state.streamCalls;
    unmount();

    // Server phai THAY ket noi dong — `abort()` that, khong phai chi bo qua ket qua.
    await waitUntil(() => state.closedStreams >= 1, 3000);

    // 900ms > `reconnectDelay(0)` (500ms): neu vong noi lai con song thi da co
    // request moi trong khoang nay.
    await new Promise((resolve) => setTimeout(resolve, 900));
    assert.equal(state.jobsCalls, jobsBefore, "sau unmount khong duoc doc anh chup nua");
    assert.equal(state.streamCalls, streamBefore, "sau unmount khong duoc mo stream moi");
  });
});
