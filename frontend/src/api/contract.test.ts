/**
 * Contract test chạy trên BACKEND THẬT ở 8620 — không mock, không server giả.
 *
 * Vì sao tồn tại: Giai đoạn 2 đã đổi tên khoá `translated_from_version` →
 * `transcript_version` trên endpoint transcript. Một client viết tay (`types.ts`)
 * trôi theo kiểu đó trong IM LẶNG — mã vẫn biên dịch, trang vẫn vẽ, chỉ có con
 * số hiện sai. Đổi shape ở server PHẢI làm tệp này đỏ.
 *
 * Runner: `node --test --test-isolation=none` + loader SWC (`test/swc-loader.mjs`).
 * Vitest không dùng được ở môi trường này (xem `## ⚠️ ERRATA` trong plan) — nên
 * ở đây là `node:test` + `node:assert/strict`, không phải `expect`/`toHaveProperty`.
 * Chạy riêng tệp này từ `frontend/`:
 *   node --import ./test/swc-loader.mjs --test --test-isolation=none src/api/contract.test.ts
 * (`npm test -- contract` KHÔNG lọc được: script có glob.)
 *
 * BACKEND: TỰ KHỞI ĐỘNG. Đây là RÀNG BUỘC của plan (Global Constraints, dòng 17:
 * "Backend **không** chạy sẵn: mọi test đầu-cuối phải **tự khởi động** nó và **tự
 * tắt**"), không phải tiện ích. `before` dò `/api/status` trước; chỉ khi KHÔNG ai
 * trả lời nó mới `spawn` `backend/.venv/Scripts/python.exe run_api.py` với
 * `stdio: "ignore"` (sandbox cấm named pipe: `stdio: "pipe"` chết `EPERM`) rồi poll
 * `/api/status` tới 30 s; `after` tắt ĐÚNG tiến trình nó spawn. Backend do người
 * khác chạy thì KHÔNG spawn cái thứ hai và KHÔNG tắt nó.
 *
 * DỮ LIỆU: hai bài dưới đây ĐỎ khi DB rỗng — CỐ Ý. Một bài xanh-vì-không-có-gì-để-đo
 * là im lặng, còn spec §2 nói contract test phải sập ỒN ÀO khi shape trôi. DB repo
 * hiện 0 hàng (`data/app.db`); Task 12 gieo dữ liệu thật vào đó. Trên backend CÓ dữ
 * liệu thì hai bài này xanh.
 *
 * Ollama KHÔNG cần bật. "Ollama tắt" là trạng thái hợp lệ và được kiểm ở đây
 * (spec §4.8 dành hẳn một màn hình cho nó) — không bài nào phụ thuộc Ollama sống.
 */
import { after, before, describe, it } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { ApiError, api } from "./client.ts";
import { exportUrl, mediaUrl, type ExportFormat } from "./endpoints.ts";
import type {
  OllamaState,
  Registry,
  Status,
  Transcript,
  TranscriptSummary,
} from "./types.ts";

/** Origin THẬT của backend. Trong trình duyệt `BASE` là tương đối (proxy 3100 lo). */
const ORIGIN = "http://127.0.0.1:8620";
const API = `${ORIGIN}/api`;

/** Thư mục `backend/` — tính từ CHÍNH tệp này, không phụ thuộc cwd của người chạy. */
const BACKEND_DIR = fileURLToPath(new URL("../../../backend/", import.meta.url));
const VENV_PYTHON =
  process.platform === "win32"
    ? path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe")
    : path.join(BACKEND_DIR, ".venv", "bin", "python");

const PROBE_TIMEOUT_MS = 2_000;
const START_TIMEOUT_MS = 30_000;
const STOP_TIMEOUT_MS = 5_000;

/** Thông điệp cho người ĐỌC, không phải cho máy: nói việc phải làm. */
const EMPTY_DB_MSG =
  "DB rong: bai nay khong do duoc gi. Chay backend voi du lieu that, hoac xem Task 12 "
  + "(gieo du lieu vao data/app.db) truoc khi chay e2e/contract.";

/** Backend do CHÍNH tệp này spawn (null = không phải của mình ⇒ không được tắt). */
let spawnedPid: number | null = null;

async function backendIsUp(): Promise<boolean> {
  try {
    const response = await fetch(`${API}/status`, {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    return response.ok;
  } catch {
    // Chưa lên (ECONNREFUSED) hoặc chưa trả lời kịp — cả hai đều là "chưa dùng được".
    return false;
  }
}

async function waitForBackend(timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await backendIsUp()) return true;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return backendIsUp();
}

/** Tắt ĐÚNG tiến trình mình spawn. Không có gì của mình ⇒ no-op. */
function stopSpawnedBackend(): void {
  if (spawnedPid === null) return;
  const pid = spawnedPid;
  spawnedPid = null;
  // `uvicorn.run` chạy TRONG tiến trình python (không spawn con), nên
  // `process.kill` là đủ. Vẫn gọi thêm `taskkill /T /F` để quét cả cây con —
  // nếu sau này `run_api.py` đổi sang reload/multi-worker thì không sót tiến trình mồ côi.
  // ĐO ĐƯỢC: `backend/.venv/Scripts/python.exe` là một LAUNCHER, nó đẻ tiến trình
  // python thật (Python310\python.exe) làm CON — nên một backend trông như HAI
  // tiến trình `python`. `process.kill` trên launcher kéo cả cây theo (đã đo: cổng
  // thôi trả lời); trong sandbox này `taskkill` trả `Access denied` nên nó chỉ là
  // lưới an toàn, không phải cơ chế chính.
  try {
    process.kill(pid);
  } catch {
    // Đã chết rồi — đích của hàm là "không còn sống", không phải "vừa giết".
  }
  try {
    spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
  } catch {
    // taskkill thiếu (không phải Windows) — `process.kill` ở trên đã lo phần đó.
  }
}

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(`${API}${path}`);
  assert.ok(response.ok, `GET ${path} -> HTTP ${response.status}`);
  return response.json();
}

describe("hop dong API that (backend 8620)", () => {
  before(async () => {
    // Backend của NGƯỜI KHÁC: không spawn thêm, và `after` sẽ không tắt nó.
    if (await backendIsUp()) return;

    let spawnError: string | null = null;
    const child = spawn(VENV_PYTHON, ["run_api.py"], {
      cwd: BACKEND_DIR,
      stdio: "ignore",
      windowsHide: true,
    });
    child.on("error", (error: Error) => {
      spawnError = error.message;
    });
    // `unref()`: handle của tiến trình con KHÔNG được giữ cho event loop sống.
    // Không có dòng này thì một lần `kill` thất bại biến "test đỏ" thành "runner
    // TREO VÔ HẠN" (đo được: `node --test` in xong tổng kết nhưng không thoát, vì
    // ChildProcess còn sống giữ handle). Muốn đỏ thì `after` bên dưới đã lo — nó
    // poll cổng và `assert.fail` nếu backend còn sống.
    child.unref();
    spawnedPid = typeof child.pid === "number" ? child.pid : null;

    if (await waitForBackend(START_TIMEOUT_MS)) return;

    const reason = spawnError === null ? "khong ro loi" : spawnError;
    stopSpawnedBackend();
    assert.fail(
      `backend 8620 khong len sau ${START_TIMEOUT_MS / 1000}s. Lenh da chay: `
      + `${VENV_PYTHON} run_api.py (cwd=${BACKEND_DIR}); loi spawn: ${reason}. `
      + "Chay tay lenh do de xem traceback.",
    );
  });

  after(async () => {
    // "TỰ TẮT" của Global Constraints: chỉ tắt cái mình spawn.
    const killed = spawnedPid;
    stopSpawnedBackend();
    if (killed === null) return;
    // Và phải CHỨNG MINH nó đã tắt: cổng thôi trả lời NGAY TRONG tiến trình test.
    // Chỉ gọi kill rồi tin là chưa đủ — một backend mồ côi sẽ khiến lần chạy sau
    // dùng nhầm backend cũ mà không ai biết.
    const deadline = Date.now() + STOP_TIMEOUT_MS;
    while (Date.now() < deadline) {
      if (!(await backendIsUp())) return;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    assert.fail(`backend 8620 (pid ${killed}) vẫn sống sau khi kill — còn tiến trình mồ côi`);
  });

  it("GET /api/status: khoá mà giao diện đọc", async () => {
    const body = (await getJson("/status")) as Status;
    for (const key of ["queue_depth", "running", "current_phase", "phase_switches", "vram", "ollama"]) {
      assert.ok(Object.hasOwn(body, key), `thiếu khoá ${key}`);
    }
    assert.equal(typeof body.queue_depth, "number");
    assert.ok(Array.isArray(body.running), "running phải là mảng id job");
    assert.ok(
      (["up", "down", "unknown"] as OllamaState[]).includes(body.ollama),
      `ollama lạ: ${String(body.ollama)}`,
    );
    // GĐ1a trả `vram: null` TƯỜNG MINH (khoá vẫn có). Null là giá trị thật, không
    // phải khoá thiếu — frontend đọc thẳng `body.vram`, không phòng thủ bằng `in`.
    assert.ok(body.vram === null || typeof body.vram === "number", "vram phải là null hoặc số");
  });

  it("GET /api/registry: khoá theo kind (asr/mt), KHÔNG phải mảng phẳng", async () => {
    const body = await getJson("/registry");
    assert.ok(!Array.isArray(body), "registry phải là {asr, mt} — không phải một mảng");
    const registry = body as Registry;
    for (const kind of ["asr", "mt"] as const) {
      assert.ok(Object.hasOwn(registry, kind), `thiếu nhóm ${kind}`);
      const specs = registry[kind];
      assert.ok(Array.isArray(specs) && specs.length > 0, `nhóm ${kind} phải là mảng không rỗng`);
      for (const spec of specs) {
        for (const key of [
          "id", "label", "kind", "runtime", "model_ref", "vram_mb", "langs", "capabilities", "opts",
        ]) {
          assert.ok(Object.hasOwn(spec, key), `${kind}/${String(spec.id)}: thiếu khoá ${key}`);
        }
        assert.equal(spec.kind, kind, `${String(spec.id)}: kind phải khớp nhóm`);
        assert.ok(Array.isArray(spec.langs), `${String(spec.id)}: langs phải là mảng`);
        assert.equal(typeof spec.vram_mb, "number");
      }
    }
  });

  it("GET /api/registry: engine dịch có capabilities.available + prompt_version", async () => {
    const registry = (await getJson("/registry")) as Registry;
    assert.ok(registry.mt.length > 0, "registry phải có ít nhất một engine dịch");
    for (const spec of registry.mt) {
      // `available` = "phục vụ được job NGAY BÂY GIỜ" (tiến trình tới được VÀ
      // model_ref có trong /api/tags) — main.py chỉ ghi khoá này cho kind "mt".
      assert.ok(
        Object.hasOwn(spec.capabilities, "available"),
        `${spec.id}: thiếu capabilities.available`,
      );
      assert.equal(typeof spec.capabilities.available, "boolean", `${spec.id}: available phải là boolean`);
      assert.equal(
        typeof spec.capabilities.prompt_version,
        "string",
        `${spec.id}: thiếu capabilities.prompt_version`,
      );
      if (spec.runtime === "inprocess") {
        assert.equal(
          spec.capabilities.available,
          true,
          `${spec.id}: engine in-process không có tiến trình ngoài nào để hỏi ⇒ luôn available`,
        );
      }
    }
  });

  it("GET /api/transcripts|jobs|sources|glossary: mảng JSON", async () => {
    for (const path of ["/transcripts", "/jobs", "/sources", "/glossary"]) {
      const body = await getJson(path);
      assert.ok(Array.isArray(body), `${path} phải trả một mảng`);
    }
  });

  it("GET /api/transcripts: hàng tóm tắt có translations[] và KHÔNG kèm segments", async () => {
    const rows = (await getJson("/transcripts")) as TranscriptSummary[];

    // ĐỎ khi rỗng là CHỦ Ý: vòng lặp dưới chỉ chứng minh được hình dạng khi có
    // hàng thật. Xanh-vì-rỗng là im lặng — đúng thứ spec §2 từ chối.
    assert.notEqual(rows.length, 0, EMPTY_DB_MSG);

    let translationsSeen = 0;
    for (const row of rows) {
      for (const key of [
        "id", "source_id", "engine", "lang", "version", "status", "created_at", "translations",
      ]) {
        assert.ok(Object.hasOwn(row, key), `transcript ${row.id}: thiếu khoá ${key}`);
      }
      assert.ok(
        !Object.hasOwn(row, "segments"),
        `transcript ${row.id}: route DANH SÁCH không được kèm segments`,
      );
      translationsSeen += row.translations.length;
      for (const translation of row.translations) {
        // Khoá `transcript_version` (KHÔNG phải `translated_from_version`) là
        // đúng thứ Giai đoạn 2 đổi tên — và là lý do tệp này tồn tại.
        for (const key of [
          "id", "transcript_id", "engine", "target_lang", "prompt_version",
          "transcript_version", "status", "stale", "created_at",
        ]) {
          assert.ok(Object.hasOwn(translation, key), `bản dịch ${translation.id}: thiếu khoá ${key}`);
        }
        assert.ok(
          !Object.hasOwn(translation, "translated_from_version"),
          `bản dịch ${translation.id}: khoá cũ translated_from_version đã bị đổi tên`,
        );
      }
    }
    // Khoá `transcript_version` nằm trên HÀNG BẢN DỊCH: transcript có mà bản dịch
    // không thì vòng lặp trên vẫn không soi được gì, và phép đổi tên mà bài này
    // sinh ra để bắt sẽ đi qua xanh. Nên thiếu bản dịch cũng là ĐỎ.
    assert.notEqual(
      translationsSeen,
      0,
      "DB khong co BAN DICH nao: khoa `transcript_version` chi nam tren hang `translations`, "
      + "nen bai nay khong do duoc gi. " + EMPTY_DB_MSG,
    );
    console.log(
      `[contract] /api/transcripts: ${rows.length} hàng, ${translationsSeen} bản dịch`,
    );
  });

  it("GET /api/transcripts/{id}: Transcript + Segment (suspect LUÔN có, khoá khác tuỳ engine)", async () => {
    const rows = (await getJson("/transcripts")) as TranscriptSummary[];
    assert.notEqual(rows.length, 0, EMPTY_DB_MSG);

    let segmentsSeen = 0;
    let wordsSeen = 0;
    for (const row of rows) {
      const body = (await getJson(`/transcripts/${row.id}`)) as Transcript;
      // `Transcript` = `TranscriptSummary` + `segments` (routes_transcripts._transcript_json).
      for (const key of [
        "id", "source_id", "engine", "lang", "version", "status", "created_at",
        "translations", "segments",
      ]) {
        assert.ok(Object.hasOwn(body, key), `transcript ${row.id}: thiếu khoá ${key}`);
      }
      assert.equal(body.id, row.id, "GET /{id} phải trả ĐÚNG transcript đã hỏi");
      assert.ok(Array.isArray(body.segments), `transcript ${row.id}: segments phải là mảng`);
      segmentsSeen += body.segments.length;

      for (const seg of body.segments) {
        const where = `segment ${row.id}/${seg.i}`;
        // BỐN khoá `to_json` ghi VÔ ĐIỀU KIỆN, cộng `suspect` (ghi ở dưới cùng,
        // không nằm trong `if` nào) — năm khoá này KHÔNG được phép vắng.
        for (const key of ["i", "start", "end", "text"]) {
          assert.ok(Object.hasOwn(seg, key), `${where}: thiếu khoá ${key}`);
        }
        assert.equal(typeof seg.i, "number", `${where}: i phải là số`);
        assert.equal(typeof seg.start, "number", `${where}: start phải là số`);
        assert.equal(typeof seg.end, "number", `${where}: end phải là số`);
        assert.equal(typeof seg.text, "string", `${where}: text phải là chuỗi`);
        assert.ok(
          Object.hasOwn(seg, "suspect"),
          `${where}: \`suspect\` phải LUÔN có (kể cả false) — to_json ghi nó vô điều kiện`,
        );
        assert.equal(typeof seg.suspect, "boolean", `${where}: suspect phải là boolean`);

        // Nhóm TUỲ CHỌN: chỉ có khi engine thật sự sinh ra. Ở đây KHÔNG được
        // assert "luôn có" — bất biến của models.py là không bịa khoá rỗng.
        if (Object.hasOwn(seg, "words")) {
          assert.ok(
            Array.isArray(seg.words) && seg.words.length > 0,
            `${where}: \`words\` chỉ được ghi khi engine có word timestamp`,
          );
          for (const word of seg.words ?? []) {
            for (const key of ["w", "s", "e"]) {
              assert.ok(Object.hasOwn(word, key), `${where}/word: thiếu khoá ${key}`);
            }
            assert.equal(typeof word.w, "string", `${where}/word: w phải là chuỗi`);
            assert.equal(typeof word.s, "number", `${where}/word: s phải là số`);
            assert.equal(typeof word.e, "number", `${where}/word: e phải là số`);
          }
          wordsSeen += 1;
        }
        if (Object.hasOwn(seg, "emotion")) {
          assert.equal(typeof seg.emotion, "string", `${where}: emotion phải là chuỗi`);
        }
        if (Object.hasOwn(seg, "speaker")) {
          assert.equal(typeof seg.speaker, "string", `${where}: speaker phải là chuỗi`);
        }
        if (Object.hasOwn(seg, "t")) {
          assert.equal(typeof seg.t, "string", `${where}: t phải là chuỗi`);
        }
        if (Object.hasOwn(seg, "avg_logprob")) {
          assert.equal(typeof seg.avg_logprob, "number", `${where}: avg_logprob phải là số`);
        }
        if (Object.hasOwn(seg, "no_speech_prob")) {
          assert.equal(typeof seg.no_speech_prob, "number", `${where}: no_speech_prob phải là số`);
        }
        // `to_json` ghi `events`/`qa` bằng `if self.events:` — danh sách RỖNG không
        // bao giờ được ghi ra, nên "có khoá" kéo theo "không rỗng".
        if (Object.hasOwn(seg, "events")) {
          assert.ok(
            Array.isArray(seg.events) && seg.events.length > 0,
            `${where}: events chỉ được ghi khi khác rỗng (\`if self.events:\`)`,
          );
        }
        if (Object.hasOwn(seg, "qa")) {
          assert.ok(
            Array.isArray(seg.qa) && seg.qa.length > 0,
            `${where}: qa chỉ được ghi khi khác rỗng (\`if self.qa:\`)`,
          );
        }
      }
    }
    // Transcript có mà đoạn không: bài này chưa chạm một `Segment` nào ⇒ ĐỎ, cùng
    // lý do với bài `translations[]` ở trên.
    assert.notEqual(
      segmentsSeen,
      0,
      "Khong transcript nao co SEGMENT: bai nay khong do duoc khoa nao cua `Segment`. " + EMPTY_DB_MSG,
    );
    console.log(
      `[contract] /api/transcripts/{id}: ${rows.length} transcript, ${segmentsSeen} segment, `
      + `${wordsSeen} segment có words`,
    );
  });

  it("GET /api/glossary/version: {glossary_version}", async () => {
    const body = (await getJson("/glossary/version")) as { glossary_version: number };
    assert.ok(Object.hasOwn(body, "glossary_version"), "thiếu khoá glossary_version");
    assert.equal(typeof body.glossary_version, "number");
  });

  it("GET /api/translations thiếu transcript_id ⇒ 422 (tên tham số query)", async () => {
    const response = await fetch(`${API}/translations`);
    assert.equal(response.status, 422, "thiếu transcript_id phải là 422, không phải 200");
    assert.match(JSON.stringify(await response.json()), /transcript_id/);
  });

  it("mediaUrl/exportUrl trỏ ĐÚNG route thật (404 = có route, không có hàng)", async () => {
    // 404 (không phải 405/422) nghĩa là ĐÚNG path và ĐÚNG tên tham số đường dẫn.
    const media = await fetch(`${ORIGIN}${mediaUrl(999999)}`);
    assert.equal(media.status, 404, `mediaUrl -> ${mediaUrl(999999)}`);

    const url = exportUrl(999999, "srt", false);
    assert.equal(url, "/api/export/999999?format=srt&bilingual=0");
    const exported = await fetch(`${ORIGIN}${url}`);
    assert.equal(exported.status, 404, `exportUrl -> ${url}`);

    // Định dạng LẠ phải bị từ chối 422 nêu tên tham số. Nếu query param không
    // tên `format`, route rơi về mặc định "srt" và câu trả lời sẽ là 404 (thiếu
    // hàng) — nên 422 chính là bằng chứng tên tham số đúng.
    const badFormat = await fetch(`${ORIGIN}${exportUrl(999999, "pdf" as ExportFormat)}`);
    assert.equal(badFormat.status, 422, "format lạ phải là 422");
    assert.match(JSON.stringify(await badFormat.json()), /định dạng không hỗ trợ/);
  });

  it("api.get/api.post: ApiError mang status VÀ detail đọc từ {detail} của FastAPI", async () => {
    // (a) HTTPException ⇒ detail là CHUỖI tiếng Việt của route, không phải "Not Found".
    await assert.rejects(
      () => api.get(`${API}/jobs/999999`),
      (error: unknown) => {
        assert.ok(error instanceof ApiError, `phải ném ApiError, nhận ${String(error)}`);
        assert.equal(error.status, 404);
        assert.ok(error.detail.includes("999999"), `detail phải nêu LÝ DO, nhận: ${error.detail}`);
        assert.ok(error.message.includes(error.detail), "message phải chứa detail");
        return true;
      },
    );

    // (b) 422 kiểm dữ liệu của FastAPI ⇒ detail là MẢNG, phải đọc ra chứ không bị nuốt.
    //     Không ghi gì: pydantic từ chối TRƯỚC khi route chạm repo.
    await assert.rejects(
      () => api.post(`${API}/glossary`, {}),
      (error: unknown) => {
        assert.ok(error instanceof ApiError, `phải ném ApiError, nhận ${String(error)}`);
        assert.equal(error.status, 422);
        assert.match(error.detail, /lang/, "detail của 422 phải nêu tên trường thiếu");
        return true;
      },
    );
  });
});
