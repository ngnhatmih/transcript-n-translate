/**
 * MOT ket noi SSE DUY NHAT cho ca app: `/api/jobs/stream` cua backend.
 *
 * Vi sao `fetch` + `ReadableStream` chu khong `EventSource`: `EventSource` khong
 * mang duoc header, khong huy duoc theo y muon (chi `close()`), va no la mot
 * duong MANG THU HAI nam ngoai `client.ts`. Plan chot mot duong duy nhat, nen
 * URL stream lay tu `BASE` — cung hang so ma moi request khac dung.
 *
 * Nguon su that la ANH CHUP `GET /api/jobs` (`endpoints.listJobs`), khong phai
 * su kien: mot su kien chi co cac khoa cua `JobEvent`, con `Job` co nhieu khoa
 * hon (`src/api/types.ts`). Su kien chi dung de CAP NHAT mot job da co — va khi
 * gap mot id CHUA co thi hook doc lai anh chup (xem `onEvent`).
 *
 * `ponytail:` TRAN — (a) khong jitter khi noi lai (nhieu tab se dap cung nhip);
 * (b) KHONG doc lai anh chup theo chu ky: mot job bi XOA o server van nam trong
 * map cho toi lan doc anh chup ke tiep (noi lai, hoac gap mot id la);
 * (c) khong dedupe theo `id` (backend da khong gui trung trong mot ket noi);
 * (d) `endpoints.listJobs()` khong mang `AbortSignal` nen request anh chup khong
 * huy duoc — no chi bi BO QUA bang co `disposed` (no `M-3` cua review).
 * Nang cap: jitter, doc lai anh chup theo chu ky, va `Last-Event-ID` khi backend
 * phat id.
 */
import { useEffect, useState } from "react";

import { BASE } from "../api/client.ts";
import { endpoints } from "../api/endpoints.ts";
import { createSseParser, reconnectDelay } from "../api/sse.ts";
import type { Job, JobEvent } from "../api/types.ts";
import { applyJobEvent } from "./jobEvents.ts";

/** Anh chup thanh ban do theo id — khoa ma moi thu khac trong hook dung. */
function snapshotToMap(rows: Job[]): Map<number, Job> {
  const next = new Map<number, Job>();
  for (const job of rows) next.set(job.id, job);
  return next;
}

/**
 * Ban do job dang song, cap nhat bang stream. Mot ket noi cho ca app.
 *
 * Hook nay duoc THI HANH THAT trong `src/state/useJobStream.test.ts` (server
 * `node:http` that trong tien trinh + jsdom + `renderHook`) — khong con la
 * "rui ro doc ma".
 */
export function useJobStream(): Map<number, Job> {
  const [jobs, setJobs] = useState<Map<number, Job>>(() => new Map<number, Job>());

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    // Ban do MOI NHAT nhin tu trong effect. Hook la NGUOI GHI DUY NHAT (moi thay
    // doi di qua `publish`), nen mot bien closure la du va khong bao gio cu —
    // va no cho phep hoi "id nay da co trong map chua?" ngay luc nhan su kien,
    // dieu ma `setJobs(previous => …)` khong lam duoc (updater phai THUAN).
    let current = new Map<number, Job>();

    // Su kien cho id CHUA co trong map: khong the ap (su kien chi co khoa cua
    // `JobEvent`, khong dui duoc mot `Job`). Chung duoc xep hang, va anh chup
    // duoc doc lai MOT lan cho ca lo.
    const pendingUnknown: JobEvent[] = [];
    let refreshing = false;

    function publish(next: Map<number, Job>): void {
      current = next;
      setJobs(next);
    }

    /**
     * Doc lai anh chup roi ap cac su kien da xep hang.
     *
     * GOP: `refreshing` bao dam nhieu su kien la lien tiep chi ton MOT request
     * dang bay. Khong co no thi mot lo su kien la se thanh mot lo request, dung
     * luc backend vua sinh job moi.
     */
    function refreshSnapshot(): void {
      if (disposed || refreshing) return;
      refreshing = true;
      void endpoints.listJobs()
        .then((rows) => {
          if (disposed) return;
          const queued = pendingUnknown.splice(0);
          let next = snapshotToMap(rows);
          // Ap SAU anh chup: su kien la thu moi hon du lieu anh chup.
          for (const event of queued) next = applyJobEvent(next, event);
          publish(next);
        })
        .catch(() => {
          // Khong doc duoc anh chup: giu map cu. Su kien da xep hang bi bo —
          // lan doc anh chup ke tiep (noi lai) se hoa giai.
          pendingUnknown.length = 0;
        })
        .finally(() => {
          refreshing = false;
          // Su kien la den trong luc request dang bay, sau khi da lay hang doi:
          // con thi mo them mot lan doc nua, neu khong chung nam lai vo thoi han.
          if (!disposed && pendingUnknown.length > 0) refreshSnapshot();
        });
    }

    /** Mot su kien tu stream: cap nhat neu id da biet, doc lai anh chup neu chua. */
    function onEvent(event: JobEvent): void {
      if (event.id === null) return;
      if (!current.has(event.id)) {
        pendingUnknown.push(event);
        refreshSnapshot();
        return;
      }
      publish(applyJobEvent(current, event));
    }

    /** Hen lan noi lai. `attempt` bat dau tu 0 cho lan thu DAU sau khi dut. */
    function later(attempt: number): void {
      if (disposed) return;
      timer = setTimeout(() => {
        void connect(attempt + 1);
      }, reconnectDelay(attempt));
    }

    async function connect(attempt: number): Promise<void> {
      if (disposed) return;
      // `retryAttempt` chu khong dung thang tham so: no bi dat lai ve 0 khi ket
      // noi THANH CONG, va gia tri do moi la thu `later` duoc nhan.
      let retryAttempt = attempt;

      // Anh chup TRUOC, stream SAU: neu doc anh chup sau khi mo stream thi mot
      // su kien toi trong luc cho HTTP se bi ghi de boi anh chup CU.
      try {
        const rows = await endpoints.listJobs();
        if (disposed) return;
        publish(snapshotToMap(rows));
      } catch {
        later(retryAttempt);
        return;
      }

      const parser = createSseParser();
      const decoder = new TextDecoder();
      try {
        const response = await fetch(`${BASE}/jobs/stream`, {
          signal: controller.signal,
          headers: { accept: "text/event-stream" },
        });
        if (!response.ok || response.body === null) {
          throw new Error(`stream tra ${response.status}`);
        }
        const reader = response.body.getReader();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          // BYTE DAU TIEN moi la "ket noi thanh cong" that su: `response.ok`
          // chi chung minh tay bat tay HTTP (mot proxy co the tra 200 roi khong
          // gui byte nao), con mot byte chay ra thi stream dang song. Dat o day
          // thi mot ket noi dai khong con lam backoff leo thang don dieu toi
          // tran 30 s cho nhung lan dut sau nay.
          retryAttempt = 0;
          for (const raw of parser.push(decoder.decode(value, { stream: true }))) {
            // Cho EP KIEU DUY NHAT cua ca tuyen, va nam DUNG o day: parser SSE
            // tra `unknown[]` (no khong biet `JobEvent` la gi), con `JobEvent`
            // la hop dong cua rieng `/api/jobs/stream`.
            onEvent(raw as JobEvent);
          }
        }
        // XA byte con lai: mot ky tu UTF-8 nhieu byte bi cat o ranh gioi cuoi
        // nam lai trong `decoder` chu khong trong `value` nao nua.
        for (const raw of parser.push(decoder.decode())) {
          onEvent(raw as JobEvent);
        }
      } catch {
        // Dut mang, 502 cua proxy, hoac `abort()` luc cleanup — ca ba deu di
        // xuong cung mot duong: hen noi lai (cleanup thi `later` tu chan).
      }
      later(retryAttempt);
    }

    void connect(0);

    return () => {
      disposed = true;
      if (timer !== undefined) clearTimeout(timer);
      // Cleanup THAT SU dong ket noi dang mo: khong co no thi backend giu mot
      // subscriber cho moi lan mount lai (React StrictMode mount hai lan).
      controller.abort();
    };
    // Mang rong: moi thu hook can deu la hang so module hoac bien cua chinh
    // effect nay, nen khong co phien ban state cu nao bi giu trong closure.
  }, []);

  return jobs;
}
