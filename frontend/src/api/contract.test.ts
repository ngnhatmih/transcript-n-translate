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
 *
 * BACKEND PHẢI ĐANG CHẠY. Khởi động: `cd backend` rồi
 * `./.venv/Scripts/python.exe run_api.py` (uvicorn chạy trong tiến trình, không
 * spawn con). Chạy đúng tệp này từ `frontend/`:
 *   node --import ./test/swc-loader.mjs --test --test-isolation=none src/api/contract.test.ts
 * (`npm test -- contract` KHÔNG lọc được: script có glob.)
 *
 * Ollama KHÔNG cần bật. "Ollama tắt" là trạng thái hợp lệ và được kiểm ở đây
 * (spec §4.8 dành hẳn một màn hình cho nó) — không bài nào phụ thuộc Ollama sống.
 */
import { before, describe, it } from "node:test";
import assert from "node:assert/strict";

import { ApiError, api } from "./client.ts";
import { exportUrl, mediaUrl, type ExportFormat } from "./endpoints.ts";
import type { OllamaState, Registry, Status, TranscriptSummary } from "./types.ts";

/** Origin THẬT của backend. Trong trình duyệt `BASE` là tương đối (proxy 3100 lo). */
const ORIGIN = "http://127.0.0.1:8620";
const API = `${ORIGIN}/api`;

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(`${API}${path}`);
  assert.ok(response.ok, `GET ${path} -> HTTP ${response.status}`);
  return response.json();
}

describe("hop dong API that (backend 8620)", () => {
  before(async () => {
    const probe = await fetch(`${API}/status`).catch(() => null);
    assert.ok(
      probe?.ok,
      "backend 8620 khong chay — khoi dong backend truoc khi chay test nay: " +
        "cd backend; ./.venv/Scripts/python.exe run_api.py",
    );
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
    // DB rỗng là trạng thái HỢP LỆ (máy này đang rỗng), nhưng khi đó vòng lặp
    // trên không chứng minh được gì về hình dạng. In số hàng ra để người đọc
    // biết bài này hôm nay có chạm dữ liệu thật hay không — không im lặng.
    console.log(`[contract] /api/transcripts: ${rows.length} hàng`);
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
