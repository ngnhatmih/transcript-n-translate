/**
 * Test `App.tsx` — tầng NỐI API, chỗ duy nhất gọi `fetch`.
 *
 * Vì sao cần: đo bằng `Select-String`, không bài nào chạm `App.tsx`. `Studio.test.tsx`
 * phủ tầng GHÉP với prop dựng tay; tệp này phủ thứ nằm BÊN DƯỚI nó — chuỗi
 * `useEffect` → `endpoints.*` → `fetch` → `setState`, và bốn hành động ghi.
 *
 * Cách đo: chặn ở `fetch` (không chặn `endpoints.*`). Chặn ở tầng thấp nhất nghĩa là
 * bài test đi qua ĐÚNG đường sản phẩm: `endpoints` ghép `BASE`, `client.ts` gọi
 * `fetch`, `App` đọc response. Chặn ở `endpoints` sẽ bỏ qua toàn bộ tầng đó.
 *
 * ⚠️ `App` tự gọi mạng khi mount (`listSources`) và lặp `listJobs` mỗi 2 s. Bản ghi
 * `fetch` trả JSON theo ĐƯỜNG DẪN, nên không phụ thuộc thứ tự gọi.
 */
import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import { cleanup, render, waitFor, within } from "@testing-library/react";

import { App } from "./App.tsx";
import { setupDom, teardownDom } from "../test/dom.ts";

const ORIGIN = "http://127.0.0.1:8620";

beforeEach(() => {
  teardownDom();
  setupDom(ORIGIN);
});

afterEach(() => {
  cleanup();
  teardownDom();
});

function q() {
  return within(document.body);
}

interface LanGoi {
  url: string;
  method: string;
  body: string | null;
}

interface Bang {
  /** Trả JSON cho một đường dẫn (đã bỏ `/api`). `null` = 404. */
  tra: (duong: string, method: string) => unknown;
  goi: LanGoi[];
}

/**
 * Chặn `fetch` và trả JSON theo đường dẫn. Trả lại `fetch` cũ trong `finally` của
 * từng bài qua `traFetch`.
 */
function chanFetch(tra: Bang["tra"]): Bang {
  const bang: Bang = { tra, goi: [] };
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    bang.goi.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
    const duong = url.replace(/^https?:\/\/[^/]+/, "").replace(/^\/api/, "");
    const duLieu = tra(duong, method);
    if (duLieu === null) {
      return new Response(JSON.stringify({ detail: "Not Found" }), {
        status: 404,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(JSON.stringify(duLieu), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  return bang;
}

function traFetch(): void {
  // `teardownDom()` cũng đặt lại cầu nối; ở đây chỉ cần gỡ bản ghi của ta.
  globalThis.fetch = globalThis.fetch;
}

// ---------------------------------------------------------------------------
// Dữ liệu giả — hình dạng ĐỌC TỪ `api/types.ts`, không bịa thêm khoá.
// ---------------------------------------------------------------------------

const KENH = {
  id: 1,
  kind: "file",
  name: "phude.mp4",
  path: "/data/media/phude.mp4",
  lang: "zh",
  size: 1024,
  duration: 10,
  created_at: "2026-01-01T00:00:00Z",
};

const TOM_TAT_BAN_DICH = {
  id: 4,
  transcript_id: 2,
  engine: "opus",
  lang: "vi",
  status: "done",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
};

const TOM_TAT_BAN_GHI = {
  id: 2,
  source_id: 1,
  engine: "whisper",
  lang: "zh",
  version: 1,
  status: "translated",
  created_at: "2026-01-01T00:00:00Z",
  translations: [TOM_TAT_BAN_DICH],
};

const DOAN_GOC = { i: 0, start: 0, end: 2.04, text: "你绝对没吃过", suspect: false };
const DOAN_DICH = { i: 0, start: 0, end: 2.04, text: "Bạn chắc chắn chưa từng ăn", suspect: false };

const BAN_GHI = { ...TOM_TAT_BAN_GHI, segments: [DOAN_GOC] };
const BAN_DICH = { ...TOM_TAT_BAN_DICH, segments: [DOAN_DICH], cps: { max_cps: 21, rows: [] } };

/** Bộ trả lời mặc định cho một lượt nạp đầy đủ. */
function traMacDinh(duong: string, method: string): unknown {
  if (duong === "/sources" && method === "GET") return [KENH];
  if (duong === "/transcripts" && method === "GET") return [TOM_TAT_BAN_GHI];
  if (duong === "/transcripts/2" && method === "GET") return BAN_GHI;
  if (duong === "/translations/4" && method === "GET") return BAN_DICH;
  if (duong === "/jobs" && method === "GET") return [];
  if (duong === "/registry" && method === "GET") return { asr: [], mt: [] };
  if (duong.startsWith("/dubs/") && duong.endsWith("/plan") && method === "GET") return null;
  return null;
}

/**
 * Đợi `App` nạp XONG CẢ CHUỖI: `sources` → `transcripts` → `transcripts/{id}` →
 * `translations/{id}`.
 *
 * 🔴 ĐO ĐƯỢC, KHÔNG PHẢI CHỜ CHO CHẮC. Bản đầu đợi "có ô phụ đề" — và nó đợi QUÁ
 * SỚM: `Studio` dựng ô phụ đề ngay khi có `transcript` (bản ghi), TRƯỚC khi
 * `getTranslation` trả về. Lúc đó `banDich === null`, nên `dungDong` cho `dich = ""`
 * và bài test đọc được `value === ""` — đỏ ở bài "hiện chữ BẢN DỊCH" (thật ra đỏ vì
 * đợi sai chỗ, không phải vì sản phẩm sai), và xanh GIẢ ở bài route (nó thấy
 * `GET /api/translations/4` chưa kịp phát).
 *
 * Đợi đúng điều kiện CUỐI của chuỗi: ô phụ đề đã có chữ bản dịch. `traMacDinh` trả
 * bản dịch `"Bạn chắc chắn chưa từng ăn"`, nên đây là mốc đo được.
 */
async function doiNapXong(): Promise<void> {
  await waitFor(
    () => {
      const ds = q().queryAllByLabelText(/^Phụ đề đoạn/);
      assert.ok(ds.length > 0, "chưa nạp xong: chưa có ô phụ đề nào");
      const dau = ds[0] as HTMLInputElement;
      assert.ok(
        dau.value !== "",
        `chưa nạp xong: ô phụ đề đầu còn rỗng (bản dịch chưa về). value=${JSON.stringify(dau.value)}`,
      );
    },
    { timeout: 3000 },
  );
}

// ---------------------------------------------------------------------------

describe("App: nạp dữ liệu thật qua fetch và dựng Studio", () => {
  it("gọi ĐÚNG các route của lượt nạp đầu, qua tiền tố /api", async () => {
    const bang = chanFetch(traMacDinh);
    try {
      render(<App />);
      await doiNapXong();
      const duong = bang.goi.map((g) => `${g.method} ${g.url}`);
      // `client.ts` ghép `BASE = "/api"`; URL tuyệt đối vì jsdom cần origin.
      assert.ok(duong.some((d) => d === "GET /api/sources"), `thiếu GET /api/sources: ${duong.join(", ")}`);
      assert.ok(duong.some((d) => d === "GET /api/transcripts"), `thiếu GET /api/transcripts: ${duong.join(", ")}`);
      assert.ok(duong.some((d) => d === "GET /api/transcripts/2"), `thiếu GET /api/transcripts/2: ${duong.join(", ")}`);
      assert.ok(duong.some((d) => d === "GET /api/translations/4"), `thiếu GET /api/translations/4: ${duong.join(", ")}`);
    } finally {
      cleanup();
      traFetch();
    }
  });

  it("không bao giờ gọi '/api/api/…' — bẫy đã đo được trên sản phẩm", async () => {
    const bang = chanFetch(traMacDinh);
    try {
      render(<App />);
      await doiNapXong();
      const haiLan = bang.goi.filter((g) => g.url.includes("/api/api/"));
      assert.deepEqual(haiLan, [], "có URL '/api' HAI LẦN");
    } finally {
      cleanup();
      traFetch();
    }
  });

  it("hiện chữ BẢN DỊCH trong ô phụ đề (hai route khác nhau ghép theo i)", async () => {
    chanFetch(traMacDinh);
    try {
      render(<App />);
      await doiNapXong();
      const o = q().getAllByLabelText(/^Phụ đề đoạn/)[0] as HTMLInputElement;
      assert.equal(o.value, "Bạn chắc chắn chưa từng ăn");
    } finally {
      cleanup();
      traFetch();
    }
  });

  it("nguồn lỗi 500 hiện thành chữ, không nuốt im lặng", async () => {
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ detail: "hỏng" }), {
        status: 500,
        headers: { "content-type": "application/json" },
      })) as typeof fetch;
    try {
      render(<App />);
      await waitFor(() => {
        assert.ok(
          document.body.textContent !== null && /500|hỏng/.test(document.body.textContent),
          "không thấy thông báo lỗi trên màn hình",
        );
      });
    } finally {
      cleanup();
      traFetch();
    }
  });
});
