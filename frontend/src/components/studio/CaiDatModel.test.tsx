/**
 * Test cho bảng "Cài đặt model" (mở từ Ctrl+K → "Cài đặt model", ERRATA #80).
 *
 * Kiểm phần DÂY NỐI chạy được dưới harness này: panel dựng từ DỮ LIỆU THẬT backend trả,
 * việc chỉ có một ứng viên KHÔNG được vẽ ô dự phòng, "đang chạy: X (model dự phòng)" là
 * câu của backend chứ không phải giao diện tự suy, và hai nút gửi đúng thứ chúng hứa:
 * Lưu ⇒ `PUT` chỉ những dòng đã đổi; Khôi phục ⇒ ghi lại `mac_dinh`.
 *
 * ⚠️ HARNESS: `fireEvent.change` trên ô điều khiển KHÔNG chạy handler React dưới harness
 * này (đo được ở `PhuDeStyle.test.tsx`), nên các bài ở đây chỉ khẳng định thứ chúng đo
 * được — cấu trúc DOM, chữ hiện ra, và request thật. Đổi `<select>` được kiểm bằng đường
 * `Khôi phục` (nút bấm, chạy được) thay vì giả vờ rằng change đã chạy.
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import { cleanup, fireEvent, render } from "@testing-library/react";

import { setupDom, teardownDom } from "../../../test/dom.ts";
import type { ModelSettings } from "@/api/types.ts";
import { CaiDatModel } from "./CaiDatModel.tsx";

const ORIGIN = "http://127.0.0.1:8620";

const DU_LIEU: ModelSettings = {
  nhom_dich: "mt",
  nhom_dich_chon: ["mt", "llm"],
  tasks: [
    {
      id: "ocr", label: "OCR", nhom: "Phiên âm", locked: true,
      candidates: [{ id: "rapidocr", label: "RapidOCR", available: true, nhom: null }],
      used: "rapidocr", fallback: null,
      mac_dinh: { used: "rapidocr", fallback: null },
      hieu_luc: { engine: "rapidocr", ly_do: "dang-dung" },
    },
    {
      id: "asr", label: "ASR", nhom: "Phiên âm", locked: false,
      candidates: [
        { id: "fw-large-v3", label: "Whisper large-v3", available: true, nhom: null },
        { id: "fw-medium", label: "Whisper medium", available: true, nhom: null },
      ],
      used: "fw-large-v3", fallback: "fw-medium",
      mac_dinh: { used: "fw-large-v3", fallback: null },
      //: Đúng ca "model đang dùng không hoạt động": backend nói dự phòng đang chạy.
      hieu_luc: { engine: "fw-medium", ly_do: "du-phong" },
    },
    {
      id: "dich", label: "Dịch", nhom: "Dịch", locked: false,
      candidates: [
        { id: "opus-mt", label: "OPUS-MT", available: true, nhom: "mt" },
        { id: "qwen2.5-7b", label: "Qwen2.5-7B", available: false, nhom: "llm" },
      ],
      used: "opus-mt", fallback: null,
      mac_dinh: { used: "opus-mt", fallback: null },
      hieu_luc: { engine: "opus-mt", ly_do: "dang-dung" },
    },
    {
      id: "burn", label: "Burn phụ đề", nhom: "Ghép nền", locked: false,
      candidates: [
        { id: "h264_nvenc", label: "GPU NVENC", available: false, nhom: null },
        { id: "libx264", label: "CPU x264", available: true, nhom: null },
      ],
      used: "h264_nvenc", fallback: "libx264",
      mac_dinh: { used: "h264_nvenc", fallback: null },
      hieu_luc: { engine: "libx264", ly_do: "du-phong" },
    },
  ],
};

interface Goi {
  method: string;
  url: string;
  body: unknown;
}

function stubFetch(ds: ModelSettings = DU_LIEU): Goi[] {
  const goi: Goi[] = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
    goi.push({ method: init?.method ?? "GET", url: String(url), body });
    //: `PUT` trả lại bảng ĐÃ trộn — giống backend thật (nó trả `_bang(...)`).
    return new Response(JSON.stringify(ds), {
      status: 200, headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  return goi;
}

beforeEach(() => {
  teardownDom();
  setupDom(ORIGIN);
});

afterEach(() => {
  cleanup();
  teardownDom();
});

function mo() {
  return render(<CaiDatModel open onClose={() => {}} />);
}

async function cho() {
  await new Promise((r) => setTimeout(r, 30));
}

describe("CaiDatModel: bảng dựng từ dữ liệu THẬT của backend", () => {
  it("panel đóng thì KHÔNG vẽ gì, và KHÔNG gọi mạng", () => {
    const goi = stubFetch();
    render(<CaiDatModel open={false} onClose={() => {}} />);
    assert.equal(document.body.textContent, "");
    assert.equal(goi.length, 0, "open=false mà vẫn gọi API");
  });

  it("mở là gọi GET /api/model-settings rồi vẽ đủ nhóm và dòng", async () => {
    const goi = stubFetch();
    mo();
    await cho();
    assert.equal(goi[0].method, "GET");
    assert.match(goi[0].url, /\/api\/model-settings$/);
    const chu = document.body.textContent ?? "";
    for (const ten of ["Phiên âm", "Dịch", "Ghép nền", "OCR", "ASR", "Dịch", "Burn phụ đề"]) {
      assert.ok(chu.includes(ten), `thiếu "${ten}" trong panel: ${chu.slice(0, 200)}`);
    }
  });

  it("việc chỉ có MỘT ứng viên KHÔNG vẽ ô dự phòng, và nói rõ 'chỉ có một model'", async () => {
    stubFetch();
    mo();
    await cho();
    const chonDuPhong = [...document.body.querySelectorAll("select")]
      .map((s) => s.getAttribute("aria-label") ?? "");
    assert.ok(
      !chonDuPhong.some((n) => n.includes("dự phòng của OCR")),
      "OCR chỉ có một model mà vẫn vẽ ô dự phòng — ô nói dối rằng có thể chọn",
    );
    assert.ok(chonDuPhong.some((n) => n.includes("dự phòng của ASR")), chonDuPhong.join(" | "));
    assert.match(document.body.textContent ?? "", /chỉ có một model/);
  });

  it("câu 'đang chạy' là của BACKEND, kèm nhãn (dự phòng) khi model đang dùng không chạy được", async () => {
    stubFetch();
    mo();
    await cho();
    const chu = document.body.textContent ?? "";
    assert.match(chu, /đang chạy bằng model dự phòng:\s*fw-medium/, chu.slice(0, 400));
    assert.match(chu, /đang chạy bằng model dự phòng:\s*libx264/);
  });

  it("ứng viên chưa sẵn sàng được ghi rõ ngay trong danh sách", async () => {
    stubFetch();
    mo();
    await cho();
    assert.match(document.body.textContent ?? "", /GPU NVENC — chưa sẵn sàng/);
  });

  it("nhóm Dịch đang là MT ⇒ danh sách CHỈ có engine MT, không lẫn engine LLM", async () => {
    //: Nhóm là dữ liệu của engine (`runtime`), `nhom_dich` chỉ lọc thứ được HIỆN. Trộn
    //: hai nhóm vào một danh sách là mời chọn một model LLM rồi tưởng nó chạy offline.
    stubFetch();
    mo();
    await cho();
    const chon = [...document.body.querySelectorAll("select")]
      .find((s) => s.getAttribute("aria-label") === "model sử dụng của Dịch");
    assert.ok(chon, "không thấy ô chọn model của Dịch");
    const nhan = [...chon.options].map((o) => o.textContent ?? "");
    assert.deepEqual(nhan, ["OPUS-MT"], `nhóm MT mà lộ engine khác: ${nhan.join(" | ")}`);
  });

  it("nhóm Dịch có ô chọn MT hay LLM", async () => {
    stubFetch();
    mo();
    await cho();
    const radios = [...document.body.querySelectorAll("input[type=radio]")]
      .map((r) => r.parentElement?.textContent ?? "");
    assert.ok(radios.some((t) => t.includes("MT (dịch máy)")), radios.join(" | "));
    assert.ok(radios.some((t) => t.includes("LLM (mô hình ngôn ngữ)")), radios.join(" | "));
  });
});

describe("CaiDatModel: hai nút gửi đúng thứ chúng hứa", () => {
  it("bấm Lưu ⇒ PUT /api/model-settings, và không gửi dòng nào chưa ai đụng", async () => {
    const goi = stubFetch();
    mo();
    await cho();
    const luu = [...document.body.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").includes("Lưu cài đặt")) as HTMLButtonElement;
    assert.ok(luu, "không thấy nút Lưu cài đặt");
    fireEvent.click(luu);
    await cho();
    const put = goi.find((g) => g.method === "PUT");
    assert.ok(put, `không có PUT nào: ${JSON.stringify(goi.map((g) => g.method))}`);
    assert.match(put.url, /\/api\/model-settings$/);
    assert.deepEqual(put.body, { tasks: {} }, (
      "chưa đổi gì mà vẫn ghi đè cả bảng — mọi dòng chưa đụng sẽ bị ghi lại giá trị đang hiện"));
  });

  it("Khôi phục rồi Lưu ⇒ ghi ĐÚNG giá trị `mac_dinh` của backend cho MỌI việc", async () => {
    const goi = stubFetch();
    mo();
    await cho();
    const khoiPhuc = [...document.body.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").includes("Khôi phục")) as HTMLButtonElement;
    fireEvent.click(khoiPhuc);
    const luu = [...document.body.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").includes("Lưu cài đặt")) as HTMLButtonElement;
    fireEvent.click(luu);
    await cho();
    const put = goi.find((g) => g.method === "PUT");
    assert.ok(put, "không có PUT nào");
    const tasks = (put.body as { tasks: Record<string, { used: string | null; fallback: string | null }> }).tasks;
    assert.equal(tasks["asr"].used, "fw-large-v3");
    assert.equal(tasks["asr"].fallback, null);
    assert.equal(tasks["burn"].used, "h264_nvenc");
    assert.equal(tasks["ocr"].used, "rapidocr");
  });
});

describe("CaiDatModel: chỗ THỪA đã bị bỏ (và phím Escape)", () => {
  it("dòng 'đang chạy' KHÔNG được vẽ khi nó chỉ lặp lại model đang chọn", async () => {
    //: Bản đầu in "đang chạy: X" cho CẢ sáu dòng, kể cả khi X chính là giá trị đang hiện
    //: trong ô chọn ngay trên nó — sáu câu lặp lại không nói thêm gì. Nay dòng đó chỉ hiện
    //: khi đã rơi về dự phòng hoặc không còn đường nào.
    stubFetch({
      ...DU_LIEU,
      tasks: DU_LIEU.tasks.map((t) => ({
        ...t,
        hieu_luc: { engine: t.used, ly_do: "dang-dung" },
      })),
    });
    mo();
    await cho();
    assert.doesNotMatch(document.body.textContent ?? "", /đang chạy/);
  });

  it("Escape đóng bảng (chuột không phải đường duy nhất)", async () => {
    stubFetch();
    let dong = 0;
    render(<CaiDatModel open onClose={() => { dong += 1; }} />);
    await cho();
    fireEvent.keyDown(window, { key: "Escape" });
    assert.equal(dong, 1, "Escape phải đóng bảng");
  });

  it("model đang lưu NGOÀI nhóm đang chọn vẫn hiện trong ô, không thành ô rỗng", async () => {
    //: `<select>` của React không có giá trị nằm ngoài `options` thì hiển thị RỖNG. Đổi
    //: sang nhóm LLM khi đang dùng `opus-mt` (MT) mà lọc thẳng tay thì người dùng thấy ô
    //: trống và mất luôn lựa chọn cũ, không hiểu vì sao.
    stubFetch({
      ...DU_LIEU,
      nhom_dich: "llm",
      tasks: DU_LIEU.tasks.map((t) =>
        t.id === "dich" ? { ...t, used: "opus-mt" } : t,
      ),
    });
    mo();
    await cho();
    const chon = [...document.body.querySelectorAll("select")]
      .find((s) => s.getAttribute("aria-label") === "model sử dụng của Dịch");
    assert.ok(chon, "không thấy ô chọn của Dịch");
    const nhan = [...chon.options].map((o) => o.textContent ?? "");
    assert.ok(
      nhan.some((t) => t.includes("OPUS-MT")),
      `giá trị đang lưu bị bỏ khỏi danh sách: ${nhan.join(" | ")}`,
    );
  });
});