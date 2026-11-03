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
import type { Source } from "@/api/types";
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

/**
 * Một hàng `sources` — hình dạng ĐỌC TỪ `api/types.ts::Source`, không bịa khoá.
 *
 * 🔴 FIXTURE NÀY TỪNG SAI, VÀ NÓ LÀM MỘT BÀI TEST ĐỎ VÌ LÝ DO SAI. Bản trước khai
 * `name: "phude.mp4"` + `path: "/data/media/phude.mp4"` + `size: 1024` — ba khoá
 * KHÔNG có trong `Source`. Backend trả `origin` và `media_path`
 * (`routes_sources._source_json`), và `Studio.tsx:538` đọc `source.origin`. Với
 * fixture cũ, `fileName` là `undefined` nên KHÔNG có chữ `phude.mp4` nào trên màn
 * hình, và bài "bấm Phiên âm khi chưa có bản ghi" đỏ với "chưa nạp xong kênh" —
 * tôi đã tưởng là đợi quá ngắn, nâng timeout 1000 → 3000 ms, vẫn đỏ, vì lý do thật
 * là tên tệp không bao giờ được vẽ.
 *
 * Các bài cũ không lộ ra vì chúng đợi Ô PHỤ ĐỀ (`doiNapXong`), không đợi tên tệp.
 * Một fixture sai chỉ lộ ra khi có bài đầu tiên chạm đúng chỗ nó sai.
 */
const KENH = {
  id: 1,
  kind: "file",
  origin: "phude.mp4",
  media_path: "/data/media/phude.mp4",
  // 🔴 KHÁC `null`: nguồn này ĐÃ bóc xong âm thanh, nên bấm "Phiên âm" mới hợp lệ.
  //
  // Bản trước để `audio_path: null` và bài "bấm Phiên âm khi chưa có bản ghi phải tạo
  // job" vẫn XANH — vì lúc đó chưa có guard nào kiểm `audio_path`. Nay có (cả ở
  // `App.onBuoc` lẫn `POST /api/jobs` → 409), nên fixture phải mô phỏng đúng trạng
  // thái mà thao tác đó đòi: một video đã nạp xong.
  //
  // Nhánh "chưa có audio" có bài riêng bên dưới (`audio_path: null`).
  audio_path: "/data/media/phude.wav",
  lang: "zh",
  duration: 10,
  // Backend LUÔN trả khoá này (`_source_json`), kể cả khi chưa ai chọn vùng.
  // `null` = chưa chọn ⇒ giao diện dùng `VUNG_DOC_MAC_DINH`. Thiếu khoá ở fixture
  // thì test không bao giờ chạm nhánh thật của nó.
  vung_doc: null,
  created_at: "2026-01-01T00:00:00Z",
} satisfies Source;

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

// 🔴 `layer` LA BAT BUOC, khong phai trang tri.
//
// Fixture nay duoc viet truoc khi `Segment` co truong `layer`. Luc do khong sao vi
// `currentId` khong doc `layer`. Nhung tu khi su TU DONG CHON bam layer 1, mot dong
// thieu `layer` (= `undefined`) khong bao gio duoc chon — va nut "Dat vao" bien mat,
// lam bai test do voi 'Unable to find an accessible element with the role "button"
// and name /Dat vao/'.
//
// Them `layer: "mot_nguon"` cho DUNG du lieu that: day la mot dong OCR (suspect:
// false), va OCR LUON la mot_nguon.
const DOAN_GOC = { i: 0, start: 0, end: 2.04, text: "你绝对没吃过", suspect: false, layer: "mot_nguon" };
const DOAN_DICH = { i: 0, start: 0, end: 2.04, text: "Bạn chắc chắn chưa từng ăn", suspect: false, layer: "mot_nguon" };

const BAN_GHI = { ...TOM_TAT_BAN_GHI, segments: [DOAN_GOC] };
const BAN_DICH = { ...TOM_TAT_BAN_DICH, segments: [DOAN_DICH], cps: { max_cps: 21, rows: [] } };

/** Bộ trả lời mặc định cho một lượt nạp đầy đủ. */
function traMacDinh(duong: string, method: string): unknown {
  if (duong === "/sources" && method === "GET") return [KENH];
  if (duong === "/transcripts" && method === "GET") return [TOM_TAT_BAN_GHI];
  if (duong === "/transcripts/2" && method === "GET") return BAN_GHI;
  if (duong === "/translations/4" && method === "GET") return BAN_DICH;
  if (duong === "/jobs" && method === "GET") return [];
  // 🔴 `asr` PHAI khac RONG, khong phai cho dep. `POST /api/jobs` voi `type: "asr"`
  // BAT BUOC co `engine` (`routes_jobs.ENGINE_REQUIRED`), va giao dien lay ten engine
  // tu chinh response nay. Ban dau fixture tra `asr: []`, nen khong bai test nao tung
  // co engine de gui — va loi that tren san pham la **422 "job loại asr phải có
  // engine"** khi bam "Phien am". Mot fixture rong lam mot lop loi khong the lo ra.
  if (duong === "/registry" && method === "GET") {
    return {
      asr: [
        {
          id: "fw-large-v3", label: "Faster-Whisper large-v3", kind: "asr",
          runtime: "inprocess", model_ref: "large-v3", vram_mb: 3200, langs: ["zh"],
          capabilities: {}, opts: {},
        },
      ],
      mt: [],
    };
  }
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
        // Lọc theo ROUTE MỐC, không phải mọi PATCH. Bài này kiểm "một thao tác dời mốc
        // sinh ĐÚNG MỘT lệnh ghi vào route một-đoạn"; đếm mọi PATCH thì nó vỡ vì những
        // lệnh PATCH KHÔNG LIÊN QUAN — đo được: thêm `PATCH /api/sources/{id}/vung-doc`
        // (lưu vùng đọc OCR) làm bài này đỏ với "đo được 2" dù thao tác mốc vẫn đúng.
        //
        // Đây là sửa PHẠM VI cho khớp ý định, KHÔNG phải nới lỏng: nếu route mốc bị gọi
        // hai lần thì `length` vẫn là 2 và bài vẫn đỏ.
        const patch = bang.goi.filter(
          (g) => g.method === "PATCH" && g.url.startsWith("/api/transcripts/2/segments/"),
        );
        assert.equal(patch.length, 1, `phải có ĐÚNG MỘT PATCH mốc, đo được ${patch.length}`);
      });

      const patch = bang.goi.filter(
        (g) => g.method === "PATCH" && g.url.startsWith("/api/transcripts/2/segments/"),
      )[0]!;
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
        // Cùng lý do với bài trên: đếm PATCH của ROUTE MỐC, không phải mọi PATCH —
        // `PATCH /api/sources/{id}/vung-doc` (lưu vùng đọc OCR) cũng là PATCH và làm
        // phép đếm toàn cục lệch. Bất biến của bài này là "dời một mốc sinh đúng một
        // lệnh ghi mốc", không phải "cả app chỉ có một PATCH".
        assert.equal(
          bang.goi.filter(
            (g) => g.method === "PATCH" && g.url.startsWith("/api/transcripts/2/segments/"),
          ).length,
          1,
        );
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

/**
 * VÙNG ĐỌC OCR — đọc từ `source.vung_doc`, ghi qua `PATCH /api/sources/{id}/vung-doc`.
 *
 * Vì sao có nhóm này: bản đầu tôi giữ vùng trong một `useState` cục bộ, nên nó MẤT khi
 * tải lại trang — người dùng phải kéo khung lại cho mỗi video, và lần nào quên thì
 * watermark lọt vào phụ đề. Nay `sources` (nạp từ `GET /api/sources`) là nguồn sự thật
 * duy nhất, và các bài dưới ghim đúng ba trạng thái của cột:
 *
 *   `null` — chưa chọn ⇒ khung ở `VUNG_DOC_MAC_DINH` (`[0, 0.1, 1, 1]`)
 *   `[]`   — đã TẮT (nút ×) ⇒ KHÔNG có khung, chỉ có nút "bật lại"
 *   bốn số — khung ở đúng vùng đó
 *
 * 🔴 Cái bẫy phải ghim: `[]` là falsy, nên `vung_doc?.length ? ... : mặc_định` biến
 * "đã tắt" thành "dùng mặc định" — nút × trông như đã bấm mà watermark vẫn bị lọc.
 */
describe("App: vùng đọc OCR đọc từ nguồn, ghi qua PATCH", () => {
  it("vung_doc = null thì khung ở mặc định (bỏ 10% trên cùng)", async () => {
    chanFetch((duong, method) => traMacDinh(duong, method));
    try {
      render(<App />);
      await doiNapXong();

      const nhan = q().getByText(/OCR đọc vùng này/);
      assert.match(
        nhan.textContent ?? "",
        /y 10–100 %/,
        `khung mặc định phải bỏ 10% trên cùng, đọc được ${JSON.stringify(nhan.textContent)}`,
      );
    } finally {
      cleanup();
      traFetch();
    }
  });

  it("vung_doc = [] (nút × đã bấm) thì KHÔNG có khung, chỉ có nút bật lại", async () => {
    chanFetch((duong, method) => {
      if (duong === "/sources" && method === "GET") return [{ ...KENH, vung_doc: [] }];
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);
      await doiNapXong();

      // Đây là bài chặn cái bẫy truthiness: nếu `[]` bị đọc thành "chưa chọn" thì
      // khung mặc định hiện ra, và người dùng thấy lọc vùng vẫn bật dù đã tắt.
      assert.equal(
        q().queryByText(/OCR đọc vùng này/),
        null,
        "vung_doc = [] phải là TẮT: không được vẽ khung đọc nào",
      );
      assert.ok(
        q().getByText(/Vùng đọc: tắt/),
        "phải có nút bật lại khi vùng đọc đang tắt",
      );
    } finally {
      cleanup();
      traFetch();
    }
  });

  it("vung_doc = bốn số thì khung ở đúng vùng đó", async () => {
    chanFetch((duong, method) => {
      if (duong === "/sources" && method === "GET") {
        return [{ ...KENH, vung_doc: [0.0, 0.25, 1.0, 0.75] }];
      }
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);
      await doiNapXong();

      const nhan = q().getByText(/OCR đọc vùng này/);
      assert.match(nhan.textContent ?? "", /y 25–75 %/, nhan.textContent ?? "");
    } finally {
      cleanup();
      traFetch();
    }
  });

  it("bấm × gửi mode='tat', KHÔNG phải 'mac_dinh'", async () => {
    const bang = chanFetch((duong, method) => {
      if (duong === "/sources/1/vung-doc" && method === "PATCH") {
        return { ...KENH, vung_doc: [] };
      }
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);
      await doiNapXong();

      // `getByRole("button", { name })` chứ không `getByLabelText`: nút × mang
      // `aria-label` (nhãn của CHÍNH phần tử), không phải `<label for>` trỏ tới nó.
      // `getByLabelText` chỉ tìm `<label>`/`aria-labelledby` nên nó báo "Unable to
      // find a label" — đỏ vì truy vấn sai, không phải vì nút thiếu.
      q().getByRole("button", { name: "Tắt lọc vùng đọc" }).click();

      await waitFor(() => {
        const patch = bang.goi.filter((g) => g.method === "PATCH");
        assert.equal(patch.length, 1, `phải có đúng một PATCH, đo được ${patch.length}`);
      });
      const patch = bang.goi.filter((g) => g.method === "PATCH")[0]!;
      assert.equal(patch.url, "/api/sources/1/vung-doc");
      // Hai mode này KHÁC NHAU: "tat" = đọc cả khung, "mac_dinh" = quay lại vùng của
      // registry. Gửi nhầm thì nút × chỉ có tác dụng cho tới lần chạy sau.
      assert.deepEqual(JSON.parse(patch.body ?? "{}"), { mode: "tat" });
    } finally {
      cleanup();
      traFetch();
    }
  });
});

/**
 * BẤM "PHIÊN ÂM" KHI CHƯA CÓ BẢN GHI — phải tạo job, không được im lặng.
 *
 * 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng báo: "ko ấn được"): `onBuoc` mở đầu bằng
 *
 *     if (transcript === null) { setLoi("chua co ban ghi …"); return; }
 *
 * nên kênh MỚI NẠP, chưa bóc băng lần nào, bấm "Phiên âm" thì KHÔNG có gì xảy ra:
 * không job, không loading, không hàng đợi. Nhưng bước `asr` không cần `transcript`
 * — nó cần `source_id`, và `POST /api/jobs` chỉ đọc `payload.source_id`. Guard kia
 * đã dùng điều kiện của BƯỚC SAU (`dich`/`duyet` cần bản ghi) để chặn BƯỚC TRƯỚC.
 *
 * Một job `asr` trên kênh chưa có bản ghi là trường hợp BÌNH THƯỜNG: đó là đường
 * đầu tiên của mọi kênh.
 */
describe("App: bấm 'Phiên âm' khi CHƯA có bản ghi vẫn tạo job", () => {
  it("gửi POST /api/jobs với source_id của kênh đang chọn", async () => {
    const bang = chanFetch((duong, method) => {
      // Chưa bóc băng: danh sách bản ghi RỖNG.
      if (duong === "/transcripts" && method === "GET") return [];
      // Route tạo job trả về một job `queued` — hình dạng của `routes_jobs._job_json`.
      if (duong === "/jobs" && method === "POST") {
        return {
          id: 91, workspace: 1, type: "asr", engine: "fw-large-v3",
          phase: "asr:fw-large-v3", state: "queued",
        };
      }
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);
      // KHÔNG `doiNapXong()`: nó đợi ô phụ đề có chữ, mà chưa có bản ghi thì không
      // có ô phụ đề nào. Đợi đúng thứ cần: kênh đã nạp (tên tệp hiện trên màn).
      //
      // ⚠️ `timeout: 3000` là BẮT BUỘC, không phải cho chắc: `waitFor` mặc định
      // 1000 ms, còn lượt nạp đầu chạy `sources` → `transcripts` → `registry` →
      // `peaks` qua `fetch` giả trong `jsdom`. Đo được: để mặc định thì bài này đỏ
      // với "chưa nạp xong kênh" — tức đỏ vì ĐỢI QUÁ NGẮN, không phải vì sản phẩm
      // sai. `doiNapXong()` ở các bài khác cũng dùng 3000 vì cùng lý do.
      await waitFor(
        () => {
          assert.ok(
            q().queryAllByText(/phude\.mp4/).length > 0,
            "chưa nạp xong kênh",
          );
        },
        { timeout: 3000 },
      );

      q().getByRole("button", { name: /Phiên âm/ }).click();

      await waitFor(() => {
        const tao = bang.goi.filter((g) => g.method === "POST" && g.url === "/api/jobs");
        assert.equal(
          tao.length, 1,
          `bấm "Phiên âm" phải tạo ĐÚNG MỘT job, đo được ${tao.length}. ` +
          `0 nghĩa là guard \`transcript === null\` đang chặn cả bước asr — ` +
          `người dùng bấm mà sản phẩm im lặng.`,
        );
      });

      const tao = bang.goi.filter((g) => g.method === "POST" && g.url === "/api/jobs")[0]!;
      const than = JSON.parse(tao.body ?? "{}") as Record<string, unknown>;
      assert.equal(than.type, "asr");
      // 🔴 `engine` BAT BUOC. Thieu no thi route tra 422 "job loại asr phải có engine"
      // — đo được trên sản phẩm: bấm "Phiên âm", hiện 422, không job nào được tạo.
      // Đây là vế mà bản test đầu tiên của tôi THIẾU, nên nó xanh trong khi sản phẩm
      // hỏng: nó chỉ kiểm `type`/`payload`/`workspace`, không kiểm thứ route đòi.
      assert.equal(
        than.engine, "fw-large-v3",
        `job asr phải mang engine lấy từ GET /api/registry, đo được ${JSON.stringify(than.engine)}`,
      );
      // `source_id` lấy từ KÊNH, không từ bản ghi (chưa có bản ghi nào).
      assert.deepEqual(than.payload, { source_id: 1 });
      // Job bóc băng thuộc workspace 1 — cùng con số `IngestHandler` dùng khi tự xếp job.
      assert.equal(than.workspace, 1);
    } finally {
      cleanup();
      traFetch();
    }
  });

  it("KHÔNG chọn kênh nào thì báo lỗi bằng tiếng Việt, không gửi job", async () => {
    const bang = chanFetch((duong, method) => {
      if (duong === "/sources" && method === "GET") return [];
      if (duong === "/transcripts" && method === "GET") return [];
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);
      await waitFor(() => {
        assert.ok(q().queryAllByText(/Bấm để mở video của bạn/).length > 0);
      });

      // Chưa chọn kênh: nút "Phiên âm" vẫn phải bấm được (không bị vô hiệu hoá im
      // lặng), và phản hồi phải là một CÂU TIẾNG VIỆT đọc được.
      q().getByRole("button", { name: /Phiên âm/ }).click();

      await waitFor(() => {
        assert.match(
          document.body.textContent ?? "",
          /chưa chọn kênh/,
          "phải nói rõ vì sao không chạy được, không im lặng",
        );
      });
      assert.equal(
        bang.goi.filter((g) => g.method === "POST" && g.url === "/api/jobs").length,
        0,
        "chưa chọn kênh thì KHÔNG được gửi job nào",
      );
    } finally {
      cleanup();
      traFetch();
    }
  });

  /**
   * NGUỒN CHƯA BÓC XONG ÂM THANH — bấm "Phiên âm" phải bị chặn KÈM CÂU GIẢI THÍCH.
   *
   * 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng báo: "tôi vừa thử mở một video khác thì hàng đợi
   * ko thấy gì"). Nạp video mới → job `ingest` xếp hàng → bấm "Phiên âm" NGAY → job
   * `asr` được tạo cho một nguồn CHƯA có `audio_path`, và `transcribe.py:212` ném:
   *
   *     FileNotFoundError: source 6 chưa có audio; job ingest phải chạy trước
   *
   * Hàng đợi thật lúc đó: `#94 ingest` source 6, `#95` và `#96 asr` source 6 — hai job
   * CHẮC CHẮN HỎNG đang chờ. Tệ hơn: `worker.tick()` chạy hết job của GIAI ĐOẠN hiện
   * tại trước khi đổi giai đoạn, nên hai job chết kia còn nằm TRƯỚC `ingest` và làm
   * nó chờ lâu hơn — người dùng thấy hàng đợi như đứng im.
   *
   * Bài này ghim vế GIAO DIỆN (không gửi request chắc chắn bị từ chối + nói rõ lý do).
   * Vế backend (409) ghim ở `backend/tests/test_api_jobs_sse.py`.
   */
  it("nguồn chưa có audio thì KHÔNG gửi job, và nói rõ đang chờ bóc âm thanh", async () => {
    const bang = chanFetch((duong, method) => {
      if (duong === "/sources" && method === "GET") {
        return [{ ...KENH, audio_path: null, duration: null }];
      }
      if (duong === "/transcripts" && method === "GET") return [];
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);
      await waitFor(
        () => {
          assert.ok(q().queryAllByText(/phude\.mp4/).length > 0, "chưa nạp xong kênh");
        },
        { timeout: 3000 },
      );

      q().getByRole("button", { name: /Phiên âm/ }).click();

      await waitFor(() => {
        assert.match(
          document.body.textContent ?? "",
          /chưa bóc xong âm thanh/,
          "phải nói rõ đang chờ bóc âm thanh, không im lặng",
        );
      });
      assert.equal(
        bang.goi.filter((g) => g.method === "POST" && g.url === "/api/jobs").length,
        0,
        "nguồn chưa có audio thì KHÔNG được gửi job asr — backend sẽ trả 409",
      );
    } finally {
      cleanup();
      traFetch();
    }
  });
});

/**
 * HÀNG ĐỢI ĐỔI TRẠNG THÁI ⇒ DỮ LIỆU PHẢI TỰ NẠP LẠI, KHÔNG CẦN F5.
 *
 * 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng báo: "khi mở một video mới thì phải refresh trang nó
 * mới refresh state"). `jobs` được làm mới mỗi `NHIP_JOB_MS` = 2000 ms, nhưng `sources`
 * và `transcript` chỉ nạp MỘT LẦN:
 *
 *     useEffect(() => { void napKenh() }, [napKenh])        // napKenh co deps []
 *     useEffect(() => { … getTranscript … }, [sourceId])    // chi khi doi kenh
 *
 * Nên khi job `ingest` chạy xong và ghi `audio_path`/`duration` vào nguồn, giao diện
 * vẫn giữ bản `source` chụp lúc mở trang với `audio_path: null` — nó tưởng video chưa
 * bóc xong âm thanh. Bản ghi do job `asr` tạo ra cũng không hiện. Chỉ F5 mới thấy.
 *
 * Vì sao KHÔNG đưa `jobs` thẳng vào deps: `setJobs` tạo MẢNG MỚI mỗi 2 giây kể cả khi
 * không có gì đổi, nên deps `[jobs]` sẽ gọi lại ba route mỗi 2 giây, mãi mãi. Dùng
 * `dauVanTay(jobs)` = chuỗi `id:state` — so sánh GIÁ TRỊ, chỉ đổi khi có job chuyển
 * trạng thái thật.
 *
 * Bài này đo đúng chuỗi đó: `/sources` trả `audio_path: null` ở lần gọi ĐẦU, rồi (sau
 * khi một job `ingest` xuất hiện ở `done`) trả `audio_path` thật. Không có dấu vân tay
 * thì giao diện mãi mãi thấy `null`.
 */
describe("App: hàng đợi đổi trạng thái thì tự nạp lại, không cần F5", () => {
  it("nguồn chuyển từ chưa-có-audio sang có-audio khi job ingest xong", async () => {
    let lanSources = 0;
    let lanJobs = 0;
    const bang = chanFetch((duong, method) => {
      if (duong === "/sources" && method === "GET") {
        lanSources += 1;
        // Lần đầu: ingest chưa xong. Từ lần sau: đã xong.
        return lanSources === 1
          ? [{ ...KENH, audio_path: null, duration: null }]
          : [KENH];
      }
      if (duong === "/transcripts" && method === "GET") return [];
      if (duong === "/jobs" && method === "GET") {
        // 🔴 ĐẾM RIÊNG, KHÔNG buộc vào `lanSources`: hai route chạy SONG SONG, nên
        // điều kiện `lanSources === 1` phụ thuộc THỨ TỰ hai promise — đo được là nó
        // làm bài test đỏ sai ("đo được 1 lần") dù sản phẩm đúng. Đếm riêng thì phép
        // đo chỉ nói về chính route này.
        //
        // Job `ingest` xuất hiện từ lần gọi `/jobs` THỨ HAI, ở trạng thái `done` —
        // đúng cái làm `dauVanTay` đổi từ "" sang "5:done".
        lanJobs += 1;
        return lanJobs === 1
          ? []
          : [{ id: 5, workspace: 1, type: "ingest", engine: null,
               phase: "ingest:-", state: "done" }];
      }
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);

      // Bước 1: trạng thái ĐẦU là chưa có audio — bấm "Phiên âm" phải bị chặn.
      await waitFor(
        () => {
          assert.ok(q().queryAllByText(/phude\.mp4/).length > 0, "chưa nạp xong kênh");
        },
        { timeout: 3000 },
      );
      q().getByRole("button", { name: /Phiên âm/ }).click();
      await waitFor(() => {
        assert.match(
          document.body.textContent ?? "",
          /chưa bóc xong âm thanh/,
          "trước khi ingest xong phải báo chưa có âm thanh",
        );
      });

      // Bước 2: KHÔNG bấm gì, KHÔNG F5. Chỉ chờ nhịp `GET /api/jobs` kế tiếp mang về
      // job `ingest` đã `done` — và `sources` phải được nạp LẠI.
      //
      // `timeout: 8000` vì nhịp là 2000 ms và còn phải chờ hai lượt: một lượt thấy job,
      // một lượt nạp lại nguồn. Đo được: để mặc định 1000 ms thì bài này đỏ vì đợi quá
      // ngắn, không phải vì sản phẩm sai.
      await waitFor(
        () => {
          assert.ok(
            lanSources >= 2,
            `GET /api/sources phải được gọi lại khi hàng đợi đổi (đo được ${lanSources} lần). ` +
            `1 lần nghĩa là effect còn deps cũ — phải F5 mới thấy video mới.`,
          );
        },
        { timeout: 8000 },
      );

      // Và bằng chứng người dùng thấy được: guard "chưa bóc xong âm thanh" không còn
      // chặn nữa, nên bấm "Phiên âm" lần này gửi ĐÚNG MỘT job.
      q().getByRole("button", { name: /Phiên âm/ }).click();
      await waitFor(
        () => {
          const tao = bang.goi.filter((g) => g.method === "POST" && g.url === "/api/jobs");
          assert.equal(
            tao.length, 1,
            `sau khi ingest xong phải gửi được job, đo được ${tao.length}`,
          );
        },
        { timeout: 3000 },
      );
    } finally {
      cleanup();
      traFetch();
    }
  });

  /**
   * KẾ HOẠCH LỒNG TIẾNG KHÔNG ĐƯỢC GỌI LẠI MỖI 2 GIÂY.
   *
   * 🔴 LỖI THẬT, ĐO ĐƯỢC khi rà soát toàn bộ state: effect `keHoach` có deps
   * `[banDich, jobs]`. `jobs` là MẢNG MỚI mỗi `NHIP_JOB_MS` = 2000 ms (`setJobs` trong
   * effect polling tạo mảng mới kể cả khi không có gì đổi), nên `GET
   * /api/dubs/{id}/plan` chạy lại MỖI 2 GIÂY, MÃI MÃI, suốt thời gian trang mở.
   *
   * Đó đúng là cái bẫy đã sửa ở hai effect `sources`/`transcript` bằng `soJob`, nhưng bị
   * để nguyên ở đây — và tệ hơn: `soJob` chỉ đổi khi job chuyển TRẠNG THÁI, còn `jobs`
   * đổi mỗi nhịp.
   *
   * Phép đo: đếm số lần gọi `/plan`, chờ QUA hai nhịp polling, rồi đòi con số không đổi.
   */
  it("GET /api/dubs/{id}/plan KHÔNG bị gọi lại mỗi nhịp polling", async () => {
    let lanPlan = 0;
    chanFetch((duong, method) => {
      if (duong.startsWith("/dubs/") && duong.endsWith("/plan") && method === "GET") {
        lanPlan += 1;
        return null;
      }
      return traMacDinh(duong, method);
    });
    try {
      render(<App />);
      await doiNapXong();
      const sauKhiNap = lanPlan;
      assert.ok(sauKhiNap >= 1, `phải gọi /plan ít nhất một lần, đo được ${sauKhiNap}`);

      // Chờ QUA hai nhịp polling (2 × 2000 ms) rồi mới đo. Đợi 1 giây thì bài test xanh
      // dù sản phẩm vẫn gọi lại — phép đo phải dài hơn nhịp nó định bắt.
      await new Promise((r) => setTimeout(r, 5200));

      assert.equal(
        lanPlan,
        sauKhiNap,
        `GET /plan bị gọi lại ${lanPlan - sauKhiNap} lần trong 5,2 giây — deps còn ` +
        `\`jobs\` (mảng mới mỗi 2 giây) thay vì \`soJob\`. Đo được tổng ${lanPlan} lần.`,
      );
    } finally {
      cleanup();
      traFetch();
    }
  });
});
