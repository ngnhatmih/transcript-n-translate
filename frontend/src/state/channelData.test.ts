/**
 * Test hai hàm THUẦN của `channelData.ts` — KHÔNG cần jsdom (không React, không DOM,
 * không `fetch`), nên tệp này chạy bằng `node:test` thường như `src/lib/*.test.ts`.
 *
 * VI SAO HAI HÀM NÀY TỒN TẠI: `App` phải suy ra "bản ghi nào đang mở" và "bản dịch nào
 * đang xem" từ hai danh sách do backend trả. Hai câu hỏi đó là hai QUY ƯỚC, và quy ước
 * nằm trong mã thì phải đo được mà không cần dựng cả shell.
 *
 * ⚠️ QUY ƯỚC "id LỚN NHẤT LÀ HIỆN TẠI" phải GIỐNG HỆT `ChannelZone.buocCuaKenh`
 * (cùng một câu hỏi, hai câu trả lời khác nhau = nguồn sự thật thứ hai). Và **thứ tự
 * backend trả KHÔNG được giả định** — mọi mảng dưới đây cố ý KHÔNG sắp xếp theo `id`,
 * và phần tử "mới nhất" được đặt ở GIỮA mảng để một bản "lấy hàng đầu" hay "lấy hàng
 * cuối" đều đỏ.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import type { Translation, TranscriptSummary } from "../api/types.ts";
import { chonTranscript, chonTranslation } from "./channelData.ts";

/** Một hàng `GET /api/transcripts` — chỉ những khoá mà hai hàm này ĐỌC. */
function tomTat(id: number, sourceId: number): TranscriptSummary {
  return {
    id,
    source_id: sourceId,
    engine: "faster-whisper-large",
    lang: "zh",
    version: 1,
    status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    translations: [],
  };
}

/** Một hàng `GET /api/translations` — chỉ những khoá mà hai hàm này ĐỌC. */
function banDich(id: number, status: Translation["status"]): Translation {
  return {
    id,
    transcript_id: 5,
    engine: "qwen2.5-7b",
    target_lang: "vi",
    prompt_version: "raw-p1",
    transcript_version: 1,
    status,
    stale: false,
    created_at: "2026-01-01T00:00:00Z",
  };
}

describe("chonTranscript: ban ghi MOI NHAT cua kenh dang chon", () => {
  it("mang RONG ⇒ null", () => {
    assert.equal(chonTranscript([], 1), null);
  });

  it("dung MOT hang ⇒ hang do (ke ca khi no thuoc kenh khac thi null)", () => {
    const mot = tomTat(4, 1);
    assert.equal(chonTranscript([mot], 1), mot);
    assert.equal(chonTranscript([mot], 2), null, "hang cua kenh khac KHONG duoc tra ve");
  });

  it("nhieu hang KHONG sap xep theo id ⇒ MOI NHAT (khong phai dau/cuoi mang)", () => {
    // Kenh 1 co BA ban ghi. Mang backend tra KHONG theo `id`, va ban MOI NHAT (9) nam o
    // GIUA ⇒ "lay hang dau" (3) va "lay hang cuoi" (5) deu sai.
    const rows = [tomTat(3, 1), tomTat(9, 1), tomTat(5, 1), tomTat(12, 2)];
    const chon = chonTranscript(rows, 1);
    assert.ok(chon !== null, "kenh 1 co ba ban ghi ⇒ phai chon duoc mot");
    assert.equal(chon.id, 9, `phai chon ban ghi MOI NHAT (id 9); do duoc id ${chon?.id}`);
  });

  it("LOC theo `source_id` — khong lay ban ghi cua kenh khac (ke ca ban moi hon)", () => {
    // id 12 thuoc kenh 2 va LON HON moi id cua kenh 1: mot ban bo điều kiện `source_id`
    // se tra ve no.
    const rows = [tomTat(3, 1), tomTat(12, 2), tomTat(9, 1)];
    const chon = chonTranscript(rows, 1);
    assert.equal(chon?.id, 9, "ban ghi cua kenh 2 KHONG duoc lot vao ket qua");
    assert.equal(chonTranscript(rows, 2)?.id, 12);
  });

  it("`channelId === null` ⇒ null, du danh sach co hang", () => {
    assert.equal(chonTranscript([tomTat(3, 1)], null), null);
  });
});

describe("chonTranslation: ban dich MOI NHAT co status 'done'", () => {
  it("mang RONG ⇒ null", () => {
    assert.equal(chonTranslation([]), null);
  });

  it("dung MOT hang done ⇒ hang do", () => {
    const mot = banDich(11, "done");
    assert.equal(chonTranslation([mot]), mot);
  });

  it("nhieu hang KHONG sap xep theo id ⇒ MOI NHAT trong so cac ban 'done'", () => {
    // Ba ban `done` (3, 9, 5) va mot ban `running` co id LON NHAT (14). Ban `done` moi nhat
    // la 9 — nam GIUA mang ⇒ "dau"/"cuoi" deu sai, va "bo qua status" se tra ve 14.
    const rows = [banDich(3, "done"), banDich(14, "running"), banDich(9, "done"), banDich(5, "done")];
    const chon = chonTranslation(rows);
    assert.ok(chon !== null, "co ba ban done ⇒ phai chon duoc mot");
    assert.equal(chon.id, 9, `phai chon ban done MOI NHAT (id 9); do duoc id ${chon?.id}`);
    assert.equal(chon.status, "done");
  });

  it("BO QUA moi ban chua xong — du no moi hon ban da xong", () => {
    const rows = [banDich(9, "done"), banDich(14, "queued"), banDich(15, "failed"), banDich(16, "cancelled")];
    assert.equal(chonTranslation(rows)?.id, 9, "chi `status === 'done'` moi duoc chon");
  });

  it("khong co ban nao 'done' ⇒ null (KHONG roi ve mot ban chua xong)", () => {
    assert.equal(chonTranslation([banDich(14, "running"), banDich(15, "queued")]), null);
  });
});
