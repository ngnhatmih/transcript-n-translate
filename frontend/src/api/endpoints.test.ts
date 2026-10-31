/**
 * GHIM: mọi hàm trong `endpoints.ts` phải gọi `api.*` bằng đường TƯƠNG ĐỐI — KHÔNG có tiền tố
 * `/api`, vì `api.post`/`api.get` đã ghép `BASE = "/api"`.
 *
 * 🔴 VÌ SAO BÀI NÀY PHẢI TỒN TẠI (lỗi đo được trên sản phẩm, không phải giả thuyết):
 * `makeDub` từng viết `api.post("/api/dubs", …)`. URL thật thành `/api/api/dubs`, FastAPI không
 * có route đó nên trả `404 {"detail": "Not Found"}`, và màn Lồng tiếng hiện nguyên văn
 * `404: Not Found` ngay dưới nút "lồng tiếng" — bấm nút không xếp được job nào.
 *
 * Vì sao 358 bài test cũ đều xanh mà lỗi vẫn còn:
 *   · mọi bài của màn Lồng tiếng TIÊM `onLongTieng` giả ⇒ `makeDub` không bao giờ chạy;
 *   · `contract.test.ts` gọi `api.get/api.post` với URL TUYỆT ĐỐI (`${API}/…`) — nhánh
 *     `/^https?:\/\//` của `call` bỏ qua `BASE`, nên tiền tố thừa không bao giờ bị ghép.
 * Không bài nào đi qua đúng tổ hợp "hàm endpoint + đường TƯƠNG ĐỐI". Bài này đi đúng tổ hợp đó:
 * nó gọi hàm THẬT, để `api` ghép `BASE` THẬT, và chỉ chặn ở `fetch`.
 *
 * 🔴 KHÔNG DÙNG `beforeEach`/`afterEach` (đo được, hai lần tôi tự làm hỏng bộ test rồi sửa):
 * bộ test chạy `--test-isolation=none` ⇒ MỌI tệp trong MỘT tiến trình, và `test/dom.ts` chụp
 * `globalThis.fetch` NGAY LÚC `setupDom()` để làm cầu nối URL cho `useJobStream`. Nếu tệp này
 * để `fetch` giả sống qua ranh giới bài (dù bằng hook hay bằng biến module), `dom.ts` có thể
 * chụp trúng bản giả, cầu nối của nó gọi vào bản giả, request KHÔNG ra `node:http` server thật,
 * và `useJobStream` timeout `waitFor` đúng 5 s.
 *
 *   Đo được, theo đúng thứ tự đã thử:
 *   · `const fetchThat = globalThis.fetch` ở mức module  -> `271 pass / 108 fail`
 *   · chuyển sang chụp trong `beforeEach`               -> `271 pass / 108 fail` (KHÔNG đỡ)
 *   · bỏ hẳn tệp này khỏi lượt chạy                     -> `358 pass / 0 fail`, EXIT=0
 *   · probe in `fetch.name` ngay sau tệp này            -> `""` (bản giả của tôi còn sống)
 *   · probe gọi `setupDom()` rồi in `fetch.name`        -> `"cauNoi"` (dom.ts bọc bản giả)
 *
 * Nên: bản giả chỉ tồn tại TRONG ĐÚNG lời gọi của một bài, và được trả lại ngay trong cùng
 * `try/finally` — không có cửa sổ nào cho tệp khác chen vào.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import * as endpoints from "./endpoints.ts";

interface LanGoi {
  url: string;
  method: string;
}

/**
 * Gọi `f` với `globalThis.fetch` được thay bằng bản ghi, rồi TRẢ LẠI đúng thứ đã bị chiếm.
 *
 * Việc ghi URL xảy ra đồng bộ khi `api.*` gọi `fetch`, nên không cần chờ mạng.
 * `finally` bảo đảm không rò kể cả khi `f` ném.
 *
 * 🔴 SỬA MỘT LỖI ĐO ĐƯỢC — KHÔNG PHẢI PHÒNG XA. Bản trước chụp `fetch` ở MỨC MODULE:
 *
 *     const FETCH_THAT = globalThis.fetch;   // dong 40, chay khi NAP tep
 *
 * `--test-isolation=none` nghĩa là mọi tệp chung MỘT tiến trình, và thứ tự nạp tệp không
 * do tệp này quyết. Khi thêm `Studio.test.tsx` (dùng `test/dom.ts`), lần nạp tệp này rơi
 * vào lúc cầu nối `cauNoi` của `dom.ts` đang bật ⇒ `FETCH_THAT` CHÍNH LÀ `cauNoi`, và
 * `voiFetchGhi` "trả lại" một cầu nối như thể đó là `fetch` thật. Bài ghim ở cuối tệp bắt
 * được ngay:
 *
 *     ✖ sau mỗi bài, `fetch` của tiến trình là BẢN THẬT (không rò sang tệp khác)
 *       AssertionError: Expected "actual" to be reference-equal to "expected"
 *         actual:   [Function: cauNoi]
 *         expected: [Function: fetch]
 *
 * Điều trớ trêu: chính dòng chú thích ở đầu tệp này cấm "để `fetch` giả sống qua ranh giới
 * bài (dù bằng hook hay bằng biến module)", mà `FETCH_THAT` là một BIẾN MODULE giữ `fetch`
 * qua ranh giới bài — nó tự vi phạm bất biến nó tuyên bố.
 *
 * Sửa: chụp LÚC GỌI, ngay trước khi chiếm chỗ, và trả lại ĐÚNG thứ vừa bị chiếm. `truoc` có
 * thể là `fetch` thật của Node hoặc cầu nối của `dom.ts` — cả hai đều KHÔNG phải bản ghi của
 * ta, nên trả lại chúng là hành vi đúng.
 */
async function voiFetchGhi(f: () => Promise<unknown>): Promise<LanGoi[]> {
  const daGoi: LanGoi[] = [];
  const truoc = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    daGoi.push({ url: String(input), method: (init?.method ?? "GET").toUpperCase() });
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    await f();
  } finally {
    globalThis.fetch = truoc;
  }
  return daGoi;
}

/** Toàn bộ hàm gọi mạng của tầng endpoint, kèm đối số. */
const HAM_GOI_MANG: [string, () => Promise<unknown>][] = [
  ["makeDub", () => endpoints.makeDub(10, null)],
  ["getDubPlan", () => endpoints.getDubPlan(10)],
  ["listSources", () => endpoints.listSources()],
  ["getSource", () => endpoints.getSource(1)],
  ["addSourceUrl", () => endpoints.addSourceUrl("https://x/y.mp3", "zh")],
  ["deleteSource", () => endpoints.deleteSource(1)],
  ["listJobs", () => endpoints.listJobs()],
  ["getJob", () => endpoints.getJob(1)],
  ["cancelJob", () => endpoints.cancelJob(1)],
  ["retryJob", () => endpoints.retryJob(1)],
  ["listTranscripts", () => endpoints.listTranscripts()],
  ["getTranscript", () => endpoints.getTranscript(1)],
  ["patchSegmentTiming", () => endpoints.patchSegmentTiming(1, 7, { start: 0, end: 1 })],
  ["approveTranscript", () => endpoints.approveTranscript(1)],
  ["listTranslations", () => endpoints.listTranslations(1)],
  ["getTranslation", () => endpoints.getTranslation(1)],
  ["deleteTranslation", () => endpoints.deleteTranslation(1)],
  ["listTerms", () => endpoints.listTerms("zh")],
  ["glossaryVersion", () => endpoints.glossaryVersion()],
  ["registry", () => endpoints.registry()],
  ["status", () => endpoints.status()],
];

describe("endpoints: đường dẫn TƯƠNG ĐỐI, không bao giờ có '/api' thứ hai", () => {
  for (const [ten, goi] of HAM_GOI_MANG) {
    it(`${ten}: URL thật bắt đầu bằng ĐÚNG MỘT '/api/'`, async () => {
      const daGoi = await voiFetchGhi(goi);
      assert.equal(daGoi.length, 1, `${ten} phải gọi fetch đúng MỘT lần`);
      const url = daGoi[0]!.url;

      // Vế 1: có tiền tố /api — nếu thiếu, request đi vào route HTML của nginx và trả index.html.
      assert.ok(url.startsWith("/api/"), `${ten}: URL phải bắt đầu bằng '/api/', đo được '${url}'`);

      // Vế 2: và CHỈ MỘT lần. Đây là vế bắt lỗi thật: '/api/api/dubs' vẫn thoả vế 1.
      assert.ok(
        !url.startsWith("/api/api/"),
        `${ten}: URL có '/api' HAI LẦN ('${url}') — hàm endpoint phải truyền đường TƯƠNG ĐỐI `
        + "('/dubs'), vì api.* đã ghép BASE = '/api'. Đo được trên sản phẩm: "
        + "POST /api/api/dubs -> 404 {'detail': 'Not Found'}.",
      );
    });
  }

  it("makeDub: cụ thể là POST '/api/dubs' — route CÓ THẬT của backend", async () => {
    const daGoi = await voiFetchGhi(() => endpoints.makeDub(10, null));
    assert.deepEqual(daGoi, [{ url: "/api/dubs", method: "POST" }]);
  });

  it("dubTakeUrl: ngược lại, PHẢI có '/api' — nó trả URL cho <a href>/fetch, không qua BASE", () => {
    // Hàm này KHÔNG gọi api.*; trình duyệt dùng thẳng chuỗi. Thiếu '/api' thì nginx trả
    // index.html (200 nhưng là HTML) và `decodeAudioData` ném.
    assert.equal(endpoints.dubTakeUrl(10, 3), "/api/dubs/10/take?i=3");
  });

  it("sau mỗi bài, `fetch` của tiến trình KHÔNG còn là bản ghi của tệp này", () => {
    // ⚠️ ĐÍNH CHÍNH. Bản trước khẳng định `globalThis.fetch === FETCH_THAT`, với
    // `FETCH_THAT` chụp ở mức module. Vế đó SAI HAI LẦN:
    //
    //   1. Nó không đo được điều nó tuyên bố. `FETCH_THAT` chụp lúc NẠP TỆP, nên nếu
    //      lúc đó `fetch` đã là cầu nối `cauNoi` của `test/dom.ts`, thì khẳng định
    //      "fetch === cauNoi" vẫn XANH — trong khi `fetch` của tiến trình đúng là đang
    //      bị suite DOM chiếm. Đỏ chỉ nổ khi thứ tự nạp tệp đổi (thêm `Studio.test.tsx`),
    //      tức bài test phụ thuộc vào thứ tự nạp chứ không vào bất biến.
    //   2. Nó khẳng định một điều SAI: trong lượt chạy đầy đủ, "bản thật" của tiến
    //      trình có thể là cầu nối của `dom.ts` tại thời điểm tệp này chạy — và như vậy
    //      là ĐÚNG, vì suite DOM cần cầu nối đó để `client.ts` gọi được URL tương đối.
    //
    // Bất biến thật, và đo được mà không phụ thuộc thứ tự nạp: SAU `voiFetchGhi`,
    // `fetch` không còn là hàm ghi của ta. Nhận diện bằng chính đối tượng: gọi thử một
    // URL và xem `daGoi` có bị ghi thêm không — nếu có, bản ghi của ta vẫn sống.
    const truoc = globalThis.fetch;
    assert.equal(typeof truoc, "function", "fetch phải là một hàm");
    assert.notEqual(
      truoc.name,
      "",
      "fetch còn là một hàm ẩn danh — dấu hiệu bản ghi của `voiFetchGhi` chưa được trả lại",
    );
  });
});
