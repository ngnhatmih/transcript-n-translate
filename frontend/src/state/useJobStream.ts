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
 * hon (`src/api/types.ts`). Su kien chi dung de CAP NHAT mot job da co.
 *
 * `ponytail:` TRAN — (a) khong jitter khi noi lai (nhieu tab se dap cung nhip);
 * (b) khong phat lai su kien da lo: mot su kien cho job CHUA co trong anh chup
 * bi bo qua (xem `applyJobEvent`) va chi duoc hoa giai o lan doc anh chup sau;
 * (c) khong dedupe theo `id` — backend da khong gui trung trong mot ket noi
 * (`stream_events` khu trung theo noi dung anh chup). Nang cap: jitter + doc
 * lai anh chup theo chu ky, hoac `Last-Event-ID` khi backend phat id.
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
 * Chua ai import hook nay o Task 3 (Task 4 moi noi no vao shell), nen o day no
 * chi duoc `tsc` kiem kieu; hanh vi mang do Playwright phu o Task 12.
 */
export function useJobStream(): Map<number, Job> {
  const [jobs, setJobs] = useState<Map<number, Job>>(() => new Map<number, Job>());

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    /** Hen lan noi lai. `attempt` bat dau tu 0 cho lan thu DAU sau khi dut. */
    function later(attempt: number): void {
      if (disposed) return;
      timer = setTimeout(() => {
        void connect(attempt + 1);
      }, reconnectDelay(attempt));
    }

    async function connect(attempt: number): Promise<void> {
      if (disposed) return;

      // Anh chup TRUOC, stream SAU: neu doc anh chup sau khi mo stream thi mot
      // su kien toi trong luc cho HTTP se bi ghi de boi anh chup CU.
      try {
        const rows = await endpoints.listJobs();
        if (disposed) return;
        setJobs(snapshotToMap(rows));
      } catch {
        later(attempt);
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
          for (const raw of parser.push(decoder.decode(value, { stream: true }))) {
            // Cho EP KIEU DUY NHAT cua ca tuyen, va nam DUNG o day: parser SSE
            // tra `unknown[]` (no khong biet `JobEvent` la gi), con `JobEvent`
            // la hop dong cua rieng `/api/jobs/stream`.
            const event = raw as JobEvent;
            // Cap nhat theo ham: closure khong duoc giu `jobs` cu, va React chi
            // ve lai khi `applyJobEvent` tra ve mot `Map` MOI.
            setJobs((previous) => applyJobEvent(previous, event));
          }
        }
      } catch {
        // Dut mang, 502 cua proxy, hoac `abort()` luc cleanup — ca ba deu di
        // xuong cung mot duong: hen noi lai (cleanup thi `later` tu chan).
      }
      later(attempt);
    }

    void connect(0);

    return () => {
      disposed = true;
      if (timer !== undefined) clearTimeout(timer);
      // Cleanup THAT SU dong ket noi dang mo: khong co no thi backend giu mot
      // subscriber cho moi lan mount lai (React StrictMode mount hai lan).
      controller.abort();
    };
    // Mang rong: moi thu hook can deu la hang so module hoac tham so, nen khong
    // co phien ban state cu nao bi giu trong closure.
  }, []);

  return jobs;
}
