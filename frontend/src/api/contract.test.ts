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
 * KHỐI THỨ HAI (`GET /api/translations/{id}`) đi ngược lại: nó KHÔNG phụ thuộc DB của
 * repo, vì nó tự gieo một DB scratch ở thư mục tạm (ngoài repo) rồi dựng backend riêng
 * ở cổng 8621. Lý do: DB rỗng làm route chi tiết trả 404 cho MỌI id, nên nhánh 200 —
 * nhánh duy nhất mang `segments` + `cps` — không bao giờ chạy, và một khẳng định shape
 * không bao giờ chạy là một bài XANH-VÌ-KHÔNG-CÓ-GÌ-ĐỂ-ĐO.
 *
 * Ollama KHÔNG cần bật. "Ollama tắt" là trạng thái hợp lệ và được kiểm ở đây
 * (spec §4.8 dành hẳn một màn hình cho nó) — không bài nào phụ thuộc Ollama sống.
 */
import { after, before, describe, it } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
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
  TranslationDetail,
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

/**
 * KẾT QUẢ phép hỏi "DB của backend đang trả lời ở 8620 có rỗng không" — BA ca, không phải boolean.
 *
 * 🔴 VÌ SAO PHẢI HỎI CÂU NÀY (`I4` của review D2, đo được): phép dò cũ chỉ hỏi `/api/status` — một
 * route **không đụng tới DB** — nên một server LẠ đã gieo dữ liệu ở 8620 được nhận là "backend dùng
 * được", hai guard `EMPTY_DB_MSG` ở dưới thành **XANH**, và toàn bộ `fail` DỊCH ĐI HAI. Đo được CẢ
 * HAI trạng thái trên CÙNG một cây byte-exact: `pass 254 / fail 0 / EXIT=0` khi 8620 bị chiếm,
 * `pass 252 / fail 2 / EXIT=1` khi 8620 trống. Tức `fail` KHÔNG phải một thuộc tính của commit mà
 * của MÔI TRƯỜNG, và bất kỳ ai áp `fail − 2` sẽ ra số ÂM hoặc thiếu.
 *
 * 🔴 VÌ SAO TÁCH BA CA (`M-3` của re-review vòng sửa 1): hàm cũ gộp "DB KHÔNG rỗng" với "KHÔNG đọc
 * được danh sách" (fetch ném / timeout / trả object ⇒ `false`) rồi hook `before` khẳng định bằng
 * CHỮ *"DB của nó KHÔNG rỗng"* — một câu có thể SAI theo nghĩa đen (DB rỗng nhưng route danh sách
 * hỏng). Hai nguyên nhân khác nhau phải có hai câu khác nhau, cùng chuẩn "câu chữ trung thực" mà
 * cả task này theo đuổi.
 */
type DbCuaBackend =
  | { kind: "rong" }
  | { kind: "co-hang"; soHang: number }
  | { kind: "khong-doc-duoc"; lyDo: string };

async function docDbCuaBackend(): Promise<DbCuaBackend> {
  try {
    const response = await fetch(`${API}/transcripts`, {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    if (!response.ok) {
      return { kind: "khong-doc-duoc", lyDo: `GET /api/transcripts -> HTTP ${response.status}` };
    }
    const rows: unknown = await response.json();
    if (!Array.isArray(rows)) {
      return { kind: "khong-doc-duoc", lyDo: `GET /api/transcripts khong tra mot mang (${typeof rows})` };
    }
    return rows.length === 0 ? { kind: "rong" } : { kind: "co-hang", soHang: rows.length };
  } catch (loi: unknown) {
    return { kind: "khong-doc-duoc", lyDo: loi instanceof Error ? loi.message : String(loi) };
  }
}

/**
 * KHẲNG ĐỊNH dùng chung cho **CẢ HAI** nhánh dò backend: server LẠ ở 8620 và server do CHÍNH tệp
 * này spawn.
 *
 * 🔴 VÌ SAO PHẢI GỌI Ở **CẢ HAI** (`I-3` của re-review vòng sửa 1 — đo được): phép dò cũ chỉ hỏi
 * câu này ở nhánh "server lạ". Nhánh **spawn** — nhánh BÌNH THƯỜNG khi 8620 trống — không khẳng
 * định gì về DB, mà `spawn` KHÔNG truyền `env` nên tiến trình con **thừa hưởng** `PHUDE_DATA` /
 * `PHUDE_DB` của người chạy. Đo được: gieo một DB chỉ bằng hai biến môi trường đó ⇒
 * `tests 11 / pass 11 / fail 0 / cancelled 0 / **EXIT=0**`, **0 tên đỏ** — đúng cái "nền dịch đi hai
 * mà không ai thấy" của `I4`, chỉ khác đường vào. Và đường vào này **đã được lên kế hoạch**: chú
 * thích đầu tệp này nói Task 12 sẽ gieo dữ liệu thật vào `data/app.db`.
 *
 * Hỏi **chính tiến trình vừa lên** (qua `/api/transcripts` của nó) chứ không tự suy đường dẫn DB
 * từ `process.env`: cái cần kiểm là DB mà backend **THẬT SỰ** dùng, không phải cái mình đoán.
 */
/**
 * KHẲNG ĐỊNH dùng chung cho **CẢ HAI** nhánh dò backend: server LẠ ở 8620 và server do CHÍNH tệp
 * này spawn. Điều kiện là DB **PHẢI CÓ HÀNG** — không phải rỗng.
 *
 * 🔴 VÌ SAO ĐIỀU KIỆN ĐÃ ĐẢO (đo được, ba lần chạy trên cùng cây byte-exact):
 * Bản trước khẳng định DB phải RỖNG, với lý do "khối này chỉ đo được trên DB rỗng". Nhưng chính
 * hai bài con bên dưới (`GET /api/transcripts` và `GET /api/transcripts/{id}`) lại `assert.notEqual(
 * rows.length, 0, EMPTY_DB_MSG)` — chúng cần CÓ hàng để đo hình dạng thật, và tự gọi đó là "xanh
 * vì rỗng là im lặng". Hai điều kiện LOẠI TRỪ NHAU, nên không trạng thái DB nào làm cả khối xanh:
 *
 *   · DB có dữ liệu (container thật ở 8620) ⇒ hook `assert.fail`, 10 bài bị CANCEL
 *   · DB rỗng (scratch)                      ⇒ `pass 9 / fail 2`, hai bài EMPTY_DB_MSG đỏ
 *
 * Đo được cả hai, và chính comment cũ ở đây tự nói trạng thái XANH là khi DB đã gieo dữ liệu:
 * `tests 11 / pass 11 / fail 0 / cancelled 0 / EXIT=0`. Tức guard đang chặn đúng cái trạng thái
 * mà nó cần. Nay guard kiểm chiều NGƯỢC LẠI: DB rỗng ⇒ `assert.fail` với câu nói rõ phải gieo
 * dữ liệu trước; DB có hàng ⇒ đi tiếp.
 *
 * 🔴 PHẦN CÒN GIỮ NGUYÊN GIÁ TRỊ (`I4` của review D2): guard vẫn hỏi CHÍNH backend đang trả lời
 * (qua `/api/transcripts` của nó) chứ không suy đường dẫn DB từ `process.env` — cái cần kiểm là
 * DB mà backend THẬT SỰ dùng, không phải cái mình đoán. Và một server ở 8620 trả lời được nhưng
 * KHÔNG đọc được danh sách vẫn phải ĐỎ, không được coi là "chắc là ổn".
 */
async function khangDinhDbCoHang(ai: string, cachXuLy: string): Promise<void> {
  const db = await docDbCuaBackend();
  if (db.kind === "co-hang") return;
  const suThat = db.kind === "rong"
    ? "DB của nó RỖNG (0 bản ghi)"
    : `KHONG đọc được danh sách bản ghi (${db.lyDo})`;
  assert.fail(
    `${ai} đang trả lời nhưng ${suThat}. Khối này đo hình dạng trên DỮ LIỆU THẬT, nên nó cần một `
    + "DB ĐÃ GIEO HÀNG: hai bài `GET /api/transcripts` bên dưới tự gọi trạng thái rỗng là "
    + "`EMPTY_DB_MSG` (xanh-vì-rỗng là im lặng — spec §2). " + cachXuLy,
  );
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

/** Như `getJson`, nhưng trên backend 8621 (DB gieo) của khối route chi tiết. */
async function getSeedJson(path: string): Promise<unknown> {
  const response = await fetch(`${SEED_API}${path}`);
  assert.ok(response.ok, `GET ${path} -> HTTP ${response.status} (backend 8621, DB gieo)`);
  return response.json();
}

describe("hop dong API that (backend 8620)", () => {
  before(async () => {
    // Backend của NGƯỜI KHÁC: không spawn thêm, và `after` sẽ không tắt nó — NHƯNG nó phải là
    // backend mà khối này giả định: DB ĐÃ CÓ HÀNG. Hai bài `GET /api/transcripts` bên dưới đo
    // hình dạng trên dữ liệu thật và tự gọi trạng thái rỗng là `EMPTY_DB_MSG`; chạy trên DB rỗng
    // thì chúng đỏ (đo được: `pass 9 / fail 2`). Guard hỏi CHÍNH server đang trả lời, nên nó bắt
    // được cả trường hợp server lạ ở 8620 dùng một DB khác với cái mình tưởng.
    if (await backendIsUp()) {
      await khangDinhDbCoHang(
        `${ORIGIN} (backend của NGƯỜI KHÁC)`,
        "Hãy chạy backend đó trên DB đã gieo dữ liệu (hoặc để cổng TRỐNG cho tệp này tự spawn).",
      );
      return;
    }

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

    if (await waitForBackend(START_TIMEOUT_MS)) {
      // 🔴 NHÁNH **TỰ SPAWN** CŨNG PHẢI HỎI CÂU THỨ HAI (`I-3` của re-review vòng sửa 1 — đo được).
      // `spawn` ở trên KHÔNG truyền `env`, nên tiến trình con THỪA HƯỞNG `PHUDE_DATA`/`PHUDE_DB`
      // của người chạy. Điều đó có hai mặt, và cả hai đều phải bị bắt:
      //   · trỏ vào DB RỖNG ⇒ `pass 9 / fail 2` (hai bài EMPTY_DB_MSG đỏ) — ồn ào, tự báo.
      //   · trỏ vào DB đã gieo ⇒ trạng thái ĐÚNG của tệp này (`tests 11 / pass 11 / fail 0`).
      // Guard hỏi CHÍNH tiến trình vừa lên, nên câu trả lời là sự thật của cái DB nó đang dùng
      // (không phải một đường dẫn mình đoán từ env) — và một DB rỗng bị gọi đích danh thay vì
      // lặng lẽ làm hai bài kia đỏ mà không ai hiểu vì sao.
      await khangDinhDbCoHang(
        `${ORIGIN} (backend do CHÍNH tệp này spawn)`,
        "`spawn` ở trên KHÔNG truyền `env`, nên tiến trình con THỪA HƯỞNG `PHUDE_DATA`/`PHUDE_DB`: "
        + "hãy để hai biến đó trỏ vào một DB ĐÃ GIEO HÀNG (hoặc bỏ chúng đi để dùng `data/app.db`) "
        + "trước khi chạy `npm test`.",
      );
      return;
    }

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
    for (const key of ["queue_depth", "running", "current_phase", "phase_switches",
      "vram", "vram_unit", "ollama"]) {
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
// Đơn vị đi KÈM số — và có cả khi `vram` là null (nó nói đơn vị SẼ dùng).
assert.equal(typeof body.vram_unit, "string", "vram_unit phải là chuỗi");
assert.ok(body.vram_unit.length > 0, "vram_unit không được rỗng");
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
        // assert "luôn có" — bất biến của models.py là không BỊA một khoá mà
        // engine không sinh ra (đúng cho cả `words`: xem ngay dưới).
        //
        // `words` là NGOẠI LỆ của nhóm này, và chỗ này TỪNG nói dối về nó:
        // `to_json` ghi `words` bằng `if self.words is not None`, KHÔNG phải
        // truthiness như `events`/`qa` ngay dưới đây — nên `[]` VẪN được ghi.
        // Đo trên route thật: `PATCH /api/transcripts/{id}` với `"words": []`
        // trả 200, và `GET` sau đó trả nguyên `"words":[]` (lưu y nguyên trong
        // cột `segments`); ASR thì không sinh `[]` (`faster_whisper.py` truyền
        // `words or None`) nhưng PATCH nhận raw dict, nên `[]` tới được. Vì vậy
        // "có khoá" ở đây chỉ suy ra "không phải `undefined`", KHÔNG suy ra
        // "khác rỗng". Vế "engine có word timestamp thì phải khác rỗng" là bất
        // biến của ĐƯỜNG ASR, không phải của khoá này; vòng lặp này đọc
        // `GET /api/transcripts/{id}` — một đường không phân biệt được segment
        // nào do ASR sinh — nên nó KHÔNG được assert vế đó.
        if (Object.hasOwn(seg, "words")) {
          assert.ok(
            Array.isArray(seg.words),
            `${where}: \`words\` phải là mảng khi có khoá (rỗng là hợp lệ: \`is not None\`)`,
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

// ═════════════════════════════════════════════════════════════════════════════════
// Route MỚI của Task 8: `GET /api/translations/{id}` — `TranslationDetail` + CPS dạng SỐ
// ═════════════════════════════════════════════════════════════════════════════════

/**
 * VÌ SAO KHỐI NÀY TỒN TẠI: `TranslationDetail`, `TranslationCps`, `TranslationCpsRow` là ba
 * interface VIẾT TAY trong `types.ts`, và trước khối này `contract.test.ts` có **0 hit** cho
 * `cps` / `max_cps`. Nghĩa là shape của route mới chỉ được phía BACKEND ghim: đổi `cps` thành
 * CHUỖI (`"45.2"`), hay `max_cps` thành `"21.0"`, thì **cả `pytest` lẫn `npm test` VẪN XANH**
 * — hai guard duy nhất của tệp này chỉ soi `/api/transcripts`. Một lần trôi như thế là IM LẶNG,
 * đúng thứ spec §2 từ chối.
 *
 * VÌ SAO PHẢI LÀ BACKEND THỨ HAI (8621), không dùng lại 8620: DB của repo **RỖNG**
 * (`data/app.db`), nên `/api/translations/{id}` trên 8620 trả **404 cho MỌI id** — nhánh 200,
 * tức nhánh DUY NHẤT mang `segments` + `cps`, **KHÔNG BAO GIỜ CHẠY**, và một khẳng định shape
 * không bao giờ chạy là XANH-VÌ-KHÔNG-CÓ-GÌ-ĐỂ-ĐO. Khối này vì thế **gieo một DB SCRATCH** ở
 * thư mục tạm của hệ điều hành (**NGOÀI repo**, nên không bẩn `git status`) rồi dựng backend
 * riêng ở 8621 bằng `PHUDE_DB` / `PHUDE_DATA` / `PHUDE_PORT`.
 *
 * HỆ QUẢ — cả hai vế đều TẤT ĐỊNH, đây KHÔNG phải "chịu được hai trạng thái": id thật ⇒ 200 +
 * shape, id không tồn tại ⇒ 404. Khối 8620 ở trên **không bị chạm vào**: nó vẫn đo trạng thái
 * THẬT của repo (hai guard `EMPTY_DB_MSG` đỏ), và đó là trạng thái đúng.
 *
 * "TỰ TẮT" (Global Constraints): khối này chỉ tắt pid của **CHÍNH NÓ**, và **chứng minh** cổng
 * 8621 thôi trả lời trước khi kết thúc — cùng khuôn với khối 8620 ở trên.
 */
const SEED_ORIGIN = "http://127.0.0.1:8621";
const SEED_API = `${SEED_ORIGIN}/api`;

/**
 * Chương trình gieo DB scratch — chạy bằng venv của backend, KHÔNG cần model, GPU hay mạng.
 *
 * 🔴 `SEED_PY` LẶP với `src/screens/GlossaryScreen.test.tsx` (T6 của Task 12): **QUYẾT ĐỊNH LÀ ĐỂ
 * LẶP**, không phải bỏ sót. Hai bản gieo HAI THỨ KHÁC NHAU (bản này: 3 đoạn + 1 bản dịch `opus-mt`
 * để đo shape `cps`; bản kia: 5 transcript + 7 thuật ngữ để đo `affectedPreview`), và luật "mỗi
 * file DOM tự chứa" cấm dùng chung trạng thái. Gộp vào một module sẽ biến khối HỢP ĐỒNG này thành
 * phụ thuộc của một module khác — đổi fixture cho màn Thuật ngữ có thể làm khối hợp đồng ĐỎ hoặc
 * (tệ hơn) XANH mà không ai thấy. ⇒ Cái giá là ~30 dòng lặp, VÀ nó phải được khai (dòng này).
 *
 * Gieo bằng chính `SqliteRepos` (không viết SQL tay) để ràng buộc schema được giữ, đúng cách
 * mà Task 12 đã được giao. Hai đoạn được chọn để **cả hai nhánh** của route chi tiết đều chạy:
 * `i=2` có cửa sổ 0 ở CẢ nguồn lẫn bản dịch ⇒ `cps: null` (KHÁC `0.0`), còn `i=3` dịch 60 ký
 * tự trong 1,0 s ⇒ `cps` 60,0 > ngưỡng 21,0 ⇒ `over: true`.
 */
const SEED_PY = `
import sys

backend, db = sys.argv[1], sys.argv[2]
sys.path.insert(0, backend)

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.models import Segment

repos = SqliteRepos(db, clock=SystemClock())
repos.init_schema()
source_id = repos.add_source(kind="file", origin="seed.wav", media_path="seed.wav",
                             lang="zh", duration=8.0)
source = [
    Segment(i=1, start=0.0, end=2.0, text="你好"),
    Segment(i=2, start=0.0, end=0.0, text="空"),
    Segment(i=3, start=0.0, end=1.0, text="今天我们要聊的是人工智能"),
]
dich = [
    Segment(i=1, start=0.0, end=2.0, text="Xin chao"),
    Segment(i=2, start=0.0, end=0.0, text="trong"),
    Segment(i=3, start=0.0, end=1.0, text="x" * 60),
]
transcript_id = repos.add_transcript(source_id=source_id, engine="fw-small", lang="zh",
                                     segments=source)
translation_id = repos.add_translation(transcript_id=transcript_id, transcript_version=1,
                                       engine="opus-mt", target_lang="vi",
                                       prompt_version="opus-p1", status="done",
                                       segments=dich)
print("[contract] da gieo transcript", transcript_id, "ban dich", translation_id)
`;

describe("hop dong route MOI: GET /api/translations/{id} (backend 8621, DB gieo)", () => {
  /** Thư mục scratch (ngoài repo) và pid backend của CHÍNH khối này. */
  let seedDir: string | null = null;
  let seedPid: number | null = null;

  async function seedBackendIsUp(): Promise<boolean> {
    try {
      const response = await fetch(`${SEED_API}/status`, {
        signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /** Tắt ĐÚNG cây tiến trình mình spawn; không có gì của mình ⇒ no-op. */
  function stopSeedBackend(): void {
    if (seedPid === null) return;
    const pid = seedPid;
    seedPid = null;
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

  before(async () => {
    seedDir = mkdtempSync(path.join(tmpdir(), "phude-contract-"));
    const dbPath = path.join(seedDir, "app.db");
    const seedScript = path.join(seedDir, "seed.py");
    writeFileSync(seedScript, SEED_PY, "utf8");

    // `stdio: "inherit"` chứ KHÔNG `"pipe"`: trong sandbox này `pipe` chết EPERM, và một
    // lượt spawn hỏng sẽ trông y như "không có dữ liệu" (ERRATA #17 mục 1).
    const seeded = spawnSync(VENV_PYTHON, [seedScript, BACKEND_DIR, dbPath], {
      cwd: BACKEND_DIR,
      stdio: "inherit",
      windowsHide: true,
    });
    assert.equal(
      seeded.status,
      0,
      "gieo DB scratch that bai (xem traceback python ngay tren dong nay) — "
      + "khong co du lieu thi bai duoi day khong do duoc shape nao",
    );

    let spawnError: string | null = null;
    const child = spawn(VENV_PYTHON, ["run_api.py"], {
      cwd: BACKEND_DIR,
      stdio: "ignore",
      windowsHide: true,
      env: {
        ...process.env,
        PHUDE_DB: dbPath,
        PHUDE_DATA: path.join(seedDir, "data"),
        PHUDE_PORT: "8621",
      },
    });
    child.on("error", (error: Error) => {
      spawnError = error.message;
    });
    child.unref();
    seedPid = typeof child.pid === "number" ? child.pid : null;

    const deadline = Date.now() + START_TIMEOUT_MS;
    while (Date.now() < deadline) {
      if (await seedBackendIsUp()) return;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    stopSeedBackend();
    assert.fail(
      `backend 8621 (DB gieo) khong len sau ${START_TIMEOUT_MS / 1000}s; loi spawn: `
      + `${spawnError === null ? "khong ro" : spawnError}. Chay tay: PHUDE_DB=<scratch>/app.db `
      + `PHUDE_PORT=8621 "${VENV_PYTHON}" run_api.py (cwd=${BACKEND_DIR}).`,
    );
  });

  after(async () => {
    const killed = seedPid;
    stopSeedBackend();
    if (killed !== null) {
      // Phải CHỨNG MINH đã tắt, không chỉ gọi kill rồi tin (cùng luật với khối 8620).
      const deadline = Date.now() + STOP_TIMEOUT_MS;
      let stopped = false;
      while (Date.now() < deadline) {
        if (!(await seedBackendIsUp())) {
          stopped = true;
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      if (!stopped) {
        assert.fail(`backend 8621 (pid ${killed}) van song sau khi kill — con tien trinh mo coi`);
      }
    }
    if (seedDir !== null) {
      try {
        rmSync(seedDir, { recursive: true, force: true });
      } catch {
        // Windows co the giu lock `.db` them mot nhip; thu muc nam trong TEMP cua HDH,
        // ngoai repo, nen mot lan don that bai khong lam ban `git status`.
      }
    }
  });

  it("GET /api/translations/{id}: segments i/start/end/text, cps SỐ·null, over BOOL; id lạ ⇒ 404", async () => {
    // Lấy id qua ĐƯỜNG THẬT (không đọc thẳng id đã gieo): nếu route danh sách trôi shape
    // thì bài này đỏ ngay ở bước lấy id, thay vì đo một id cứng có thể không còn tồn tại.
    const rows = (await getSeedJson("/transcripts")) as TranscriptSummary[];
    const ids = rows.flatMap((row) => row.translations.map((tr) => tr.id));
    assert.notEqual(
      ids.length,
      0,
      "DB gieo khong co BAN DICH nao ⇒ bai nay khong do duoc shape cua route chi tiet. "
      + "Xem traceback cua buoc gieo o tren. " + EMPTY_DB_MSG,
    );

    let rowsSeen = 0;
    let nullCpsSeen = 0;
    let overSeen = 0;
    for (const id of ids) {
      const response = await fetch(`${SEED_API}/translations/${id}`);
      assert.equal(response.status, 200, `GET /api/translations/${id} -> HTTP ${response.status}`);
      const body = (await response.json()) as TranslationDetail;

      // `segments` là đoạn của BẢN DỊCH (cột phải của §4.3) — bốn khoá `to_json` ghi VÔ
      // ĐIỀU KIỆN, nên chúng KHÔNG được phép vắng.
      assert.ok(Array.isArray(body.segments), `ban dich ${id}: segments phải là mảng`);
      assert.notEqual(body.segments.length, 0, `ban dich ${id}: DB gieo phải có đoạn thật`);
      for (const seg of body.segments) {
        const where = `ban dich ${id}/segment ${String(seg.i)}`;
        for (const key of ["i", "start", "end", "text"]) {
          assert.ok(Object.hasOwn(seg, key), `${where}: thiếu khoá ${key}`);
        }
        assert.equal(typeof seg.i, "number", `${where}: i phải là số`);
        assert.equal(typeof seg.start, "number", `${where}: start phải là số`);
        assert.equal(typeof seg.end, "number", `${where}: end phải là số`);
        assert.equal(typeof seg.text, "string", `${where}: text phải là chuỗi`);
      }

      // `cps` dạng SỐ là CẢ LÝ DO route này tồn tại: `translations.qa_issues` giữ CPS dưới
      // dạng chuỗi (`"cps:3=45.2>21.0"`) và chuỗi đó KHÔNG tới HTTP, nên client không được
      // parse một chuỗi hiển thị để lấy con số nó hiển thị — và cũng không được tự tính.
      assert.ok(Array.isArray(body.cps.rows), `ban dich ${id}: cps.rows phải là mảng`);
      assert.equal(typeof body.cps.max_cps, "number",
        `ban dich ${id}: cps.max_cps phải là SỐ, nhận ${JSON.stringify(body.cps.max_cps)}`);
      assert.ok(Number.isFinite(body.cps.max_cps),
        `ban dich ${id}: cps.max_cps phải hữu hạn, nhận ${JSON.stringify(body.cps.max_cps)}`);
      assert.notEqual(body.cps.rows.length, 0, `ban dich ${id}: DB gieo phải có hàng CPS`);

      for (const r of body.cps.rows) {
        const where = `ban dich ${id}/cps row ${String(r.i)}`;
        assert.equal(typeof r.i, "number", `${where}: i phải là số`);
        // ⚠️ ĐÍNH CHÍNH (D2, nợ đã khai từ Task 2): comment cũ khai *"khoá đã đổi tên để phân biệt
        // với `chars` của mt_qa"* — SAI. Route này phát ĐÚNG tên `chars` của `mt_qa.CpsRow`
        // (`domain/mt_qa.py`: `chars=len(text.strip())`, **CÓ** đếm khoảng trắng), nên tên khoá ở
        // đây KHÔNG đổi. Chỗ ĐỔI TÊN để phân biệt là `chars_no_space` của
        // `routes_transcripts.qa_fast` (bỏ khoảng trắng) — cùng tên `chars` mà khác nghĩa là đúng
        // thứ khiến người sau đọc sai số, và `routes_transcripts.py:145-149` đã ghi rõ điều đó.
        assert.equal(typeof r.chars, "number",
          `${where}: chars phải là số (số ký tự của mt_qa.CpsRow.chars — len(text.strip()), CÓ khoảng trắng)`);
        assert.equal(typeof r.window, "number", `${where}: window phải là số`);
        assert.equal(typeof r.max_cps, "number", `${where}: max_cps phải là số`);
        if (r.cps === null) {
          // `null` = KHÔNG ĐO ĐƯỢC (cả hai cửa sổ đều không dương), KHÁC `0.0`. Nó là một
          // giá trị THẬT của route, không phải khoá thiếu.
          nullCpsSeen += 1;
        } else {
          assert.equal(typeof r.cps, "number",
            `${where}: cps phải là SỐ hoặc null, KHÔNG phải chuỗi — nhận ${JSON.stringify(r.cps)}`);
          assert.ok(Number.isFinite(r.cps),
            `${where}: cps phải hữu hạn — Infinity/NaN là dữ liệu hỏng, không phải "hơi nhanh": `
            + `${JSON.stringify(r.cps)}`);
        }
        assert.equal(typeof r.over, "boolean",
          `${where}: cờ over phải là BOOL, KHÔNG phải chuỗi — nhận ${JSON.stringify(r.over)}`);
        if (r.over) overSeen += 1;
        rowsSeen += 1;
      }
    }
    // Cả HAI nhánh của route phải thật sự chạy, nếu không thì bài này chỉ đo nửa route.
    assert.notEqual(nullCpsSeen, 0, "khong co hang `cps: null` nao ⇒ nhanh `nowindow` chua duoc do");
    assert.notEqual(overSeen, 0, "khong co hang `over: true` nao ⇒ nhanh vuot nguong chua duoc do");

    // id KHÔNG tồn tại ⇒ 404 (quy ước của `_require_translation`), không phải 200 rỗng và
    // không phải 500. Trên một backend CÓ dữ liệu, 404 ở đây nói "thiếu HÀNG", không phải
    // "route hỏng" — đó là lý do phép đo này phải chạy trên backend đã gieo.
    const missing = await fetch(`${SEED_API}/translations/999999`);
    assert.equal(missing.status, 404, "id khong ton tai phai la 404");

    console.log(
      `[contract] /api/translations/{id}: ${ids.length} ban dich, ${rowsSeen} hang CPS `
      + `(${nullCpsSeen} hang cps:null, ${overSeen} hang over)`,
    );
  });
});
