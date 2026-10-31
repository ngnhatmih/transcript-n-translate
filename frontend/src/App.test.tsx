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
  // 🔴 PHAI CO, khong phai cho dep. `Studio.tsx:242` goi `getPeaks(source.id, 200000)`
  // trong mot effect `async`. De `/peaks` roi vao `null` (⇒ 404 ⇒ `client.ts` nem)
  // thi nhanh `catch` chay `setBao` + `setNotice` SAU `await` — tuc SAU khi bai test
  // da ket thuc va `teardownDom()` da go `window`. Do duoc, nguyen van:
  //
  //   ℹ Error: Test "PATCH /api/transcripts/2/segments/0 …" generated asynchronous
  //     activity after the test ended. This activity created the error
  //     "ReferenceError: window is not defined" …
  //
  // Stack trace that (bat bang `process.on("uncaughtException")`):
  //   at react-dom-client.development.js:19555:13   ← `schedulerEvent = window.event`
  //   at Immediate.performWorkUntilDeadline (scheduler.development.js:45:48)
  //
  // Tra mot hinh dang RONG nhung HOP LE (dung shape `Peaks` cua route that: hai
  // mang song) thi khong co promise that bai nao song sot, va khong phai sua
  // `Studio` chi de test chay duoc. Song am rong la trang thai THAT: `peaks` la
  // duong `best-effort`, that bai thi dai thoi gian de trong (xem docblock
  // `Studio.tsx:230-241`).
  if (duong.startsWith("/media/") && duong.includes("/peaks") && method === "GET") {
    return { tren: [], duoi: [], so_dinh: 0, giay: 0 };
  }
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

/**
 * `onSuaMoc` — dời mốc của MỘT dòng.
 *
 * 🔴 BÀI NÀY GHIM ĐÚNG LỖI ERRATA #55. Bản cũ gọi
 * `patchTranscript(transcript.id, { segments: [...TOÀN BỘ...] })`: gửi 438 đoạn
 * (đo trên bản ghi thật) chỉ để dời MỘT mốc, `version` tăng, và mọi bản dịch
 * thành `stale`. Hai vế dưới đây khoá cả hai hậu quả đó, và vế nào cũng đo được
 * bằng số chứ không bằng lời hứa:
 *
 *   1. đường dẫn PHẢI là `/transcripts/2/segments/0` (route MỘT đoạn), thân chỉ
 *      có `start`/`end` — không có `segments`;
 *   2. KHÔNG được có lời gọi nào tới `PATCH /api/transcripts/2` (route gửi cả
 *      danh sách và tăng `version`).
 *
 * ⚠️ CÁCH KÍCH HOẠT — đo được, không phải chọn cho tiện:
 *
 *   · Kéo handle trên `Timeline` KHÔNG đo được ở tầng này. `startDrag`
 *     (`Timeline.tsx:316`) gọi `toTime(ev.clientX)` =
 *     `(clientX - rect.left + scrollLeft) / pxPerSec` (`Timeline.tsx:311`), mà
 *     jsdom trả `getBoundingClientRect()` toàn số 0 và không có `PointerEvent`
 *     ⇒ phép đo ra `NaN`/`0` và bài test sẽ nói dối về lý do nó đỏ. Phép đo kéo
 *     tay thuộc tầng Chrome thật (`frontend/e2e/`).
 *   · Đường ĐO ĐƯỢC ở đây là nút `Đặt vào` / `Đặt ra` (`Studio.tsx:947/950`) —
 *     cùng gọi `setEdge` → `onSuaMoc` như phím `I`/`O` (`Studio.tsx:495-501`),
 *     và không đi qua hình học.
 *   · Ô phụ đề KHÔNG dùng được: `onChange` của nó là `onSuaChu`
 *     (`PATCH /api/translations/{id}`, sửa CHỮ) — route khác, ý nghĩa khác.
 *
 * ⚠️ Đoạn 0 của `BAN_GHI` là `0 → 2.04`. `setEdge("start")` lấy
 * `t = round(player.time * 100)/100`; `usePlayer` khởi tạo `time = 0`
 * (`use-player.ts:33`) ⇒ `start = min(0, 2.04 - 0.1) = 0`. Vẫn là một lời gọi
 * PATCH thật, và mốc ra giữ nguyên `2.04` — đúng thứ cần đo (đường dẫn + thân).
 */
describe("App: dời một mốc gửi MỘT đoạn, không gửi cả danh sách", () => {
  /** Bấm nút theo tên hiển thị; `Đặt vào` mang thêm `<span class="kbd">I</span>`. */
  function bamNut(nhan: RegExp): void {
    q().getByRole("button", { name: nhan }).click();
  }

  it("PATCH /api/transcripts/2/segments/0 với thân chỉ có start/end", async () => {
    const bang = chanFetch((duong, method) => {
      // Route MỘT ĐOẠN trả lại bản ghi đã sửa mốc — đúng hình dạng route thật.
      if (duong === "/transcripts/2/segments/0" && method === "PATCH") {
        return { ...BAN_GHI, segments: [{ ...DOAN_GOC, start: 0.5, end: 2.5 }] };
      }
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);
      await doiNapXong();

      bamNut(/Đặt vào/);

      await waitFor(() => {
        const patch = bang.goi.filter((g) => g.method === "PATCH");
        assert.equal(patch.length, 1, `phải có ĐÚNG MỘT PATCH, đo được ${patch.length}`);
      });

      const patch = bang.goi.filter((g) => g.method === "PATCH")[0]!;
      // Vế 1: route MỘT ĐOẠN, không phải `/transcripts/2`.
      assert.equal(patch.url, "/api/transcripts/2/segments/0");
      // Vế 2: thân chỉ có start/end. `segments` xuất hiện ở đây là tái phạm #55.
      const than = JSON.parse(patch.body ?? "{}") as Record<string, unknown>;
      assert.deepEqual(Object.keys(than).sort(), ["end", "start"]);
      assert.equal(than.segments, undefined, "thân request KHÔNG được mang cả danh sách đoạn");
      // Vế 3: mốc RA không bị đụng — `setEdge("start")` chỉ đổi `start`.
      assert.equal(than.end, DOAN_GOC.end);
    } finally {
      cleanup();
      traFetch();
    }
  });

  it("KHÔNG gọi PATCH /api/transcripts/2 (route gửi cả danh sách, tăng version)", async () => {
    const bang = chanFetch((duong, method) => {
      if (duong === "/transcripts/2/segments/0" && method === "PATCH") {
        return { ...BAN_GHI, segments: [{ ...DOAN_GOC, start: 0.5, end: 2.5 }] };
      }
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);
      await doiNapXong();
      bamNut(/Đặt ra/);

      await waitFor(() => {
        assert.equal(bang.goi.filter((g) => g.method === "PATCH").length, 1);
      });

      const caDanhSach = bang.goi.filter(
        (g) => g.method === "PATCH" && g.url === "/api/transcripts/2",
      );
      assert.deepEqual(
        caDanhSach, [],
        "PATCH /api/transcripts/2 gửi TOÀN BỘ đoạn và TĂNG version ⇒ mọi bản dịch "
        + "thành stale (ERRATA #55). Phải dùng route MỘT ĐOẠN.",
      );
    } finally {
      cleanup();
      traFetch();
    }
  });
});
