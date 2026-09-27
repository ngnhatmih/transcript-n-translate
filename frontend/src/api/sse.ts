/**
 * Parser SSE THUAN — khong React, khong DOM, khong `fetch`, khong mang.
 *
 * Vi sao no la mot ham rieng: hai loi cua tang nay khong the thay bang mat
 * thuong. Mot manh `data:` bi cat giua hai lan doc phai duoc ghep lai, va mot
 * dong rac khong duoc giet ca stream (mat ket noi vi mot su kien hong la mat
 * luon tien do cua moi job khac). O day no la ham thuan nen `node --test` ghim
 * duoc — xem `sse.test.ts`.
 *
 * Parser nay KHONG biet `JobEvent` la gi, va do la co y: no la parser SSE, khong
 * phai parser job. Cho ep kieu duy nhat nam o phia nguoi goi
 * (`src/state/useJobStream.ts`), noi mot su kien di qua duoc thanh `JobEvent`.
 */

/**
 * Parser ghep dan: `push` nhan mot manh tho, tra ve cac su kien JSON da hoan
 * chinh trong manh do (co the la mang rong).
 *
 * `ponytail:` TRAN — ghep theo dung mot dau phan cach la HAI lan xuong dong va
 * giu phan du trong bo dem. KHONG ho tro `event:`, `id:`, `retry:`, va KHONG
 * resume theo `Last-Event-ID`. Du cho stream MOT CHIEU cua app nay: doc
 * `backend/app/api/sse.py`, ham `format_sse` chi gui `data:`. Nang cap: dung
 * `EventSource` khi can resume theo id, hoac mot parser day du cua spec SSE.
 */
export function createSseParser() {
  let buf = "";
  return {
    push(chunk: string): unknown[] {
      buf += chunk;
      const out: unknown[] = [];
      let i: number;
      while ((i = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, i);
        // Giu phan DU cho lan doc sau: mot su kien bi cat giua hai manh chi duoc
        // chot khi cap xuong dong thu hai toi, va no co the nam trong manh sau.
        buf = buf.slice(i + 2);
        // Dong comment (`: connected`, `: heartbeat`) khong co tien to `data:`
        // nen no bi loc sach o day — no giu ket noi song, khong phai su kien.
        const data = raw
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trim())
          .join("");
        if (!data) continue;
        try {
          out.push(JSON.parse(data));
        } catch {
          // Bo qua su kien hong, giu stream song. Nem o day la dot luon ket noi
          // vi mot dong rac cua MOT job.
        }
      }
      return out;
    },
  };
}

/**
 * Do tre truoc lan thu lai thu `attempt` sau khi dut ket noi.
 *
 * `attempt` bat dau tu 0 (lan thu DAU tien sau khi dut) nen no tra ve `baseMs`.
 * Tang theo cap so muon va bi chan tren o `capMs`.
 *
 * `ponytail:` TRAN — khong jitter, khong doc header `Retry-After`, khong phan
 * biet loai loi: moi lan dut deu lui theo cung mot day. Nang cap: them jitter
 * khi nhieu tab cung noi lai, neu khong chung dap vao server cung mot nhip.
 */
export function reconnectDelay(attempt: number, baseMs = 500, capMs = 30_000): number {
  // `Math.min` la thu chan tran: `2 ** attempt` vuot `Number.MAX_SAFE_INTEGER`
  // roi thanh `Infinity`, va `Math.min(Infinity, capMs)` van la `capMs` —
  // khong co `NaN` nao lot ra.
  return Math.min(baseMs * 2 ** attempt, capMs);
}
