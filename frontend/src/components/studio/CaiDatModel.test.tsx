/**
 * Test cho bảng "Cài đặt model" (Ctrl+K → "Cài đặt model", ERRATA #80–#82).
 *
 * Kiểm phần DÂY NỐI chạy được dưới harness: panel dựng từ dữ liệu THẬT backend trả, việc
 * chỉ có một ứng viên KHÔNG vẽ ô dự phòng, tên model hiện dưới tên việc, và ba luật của
 * nhóm MT/LLM (nhóm mở đầu theo model đang chạy; đổi nhóm đổi DANH SÁCH; đổi nhóm đổi luôn
 * GIÁ TRỊ nếu model cũ không thuộc nhóm mới).
 *
 * ⚠️ HARNESS: `fireEvent.change` trên ô điều khiển KHÔNG chạy handler React dưới harness này
 * (đo được ở `PhuDeStyle.test.tsx`). Đó là một phần lý do hai điều khiển của bảng được viết
 * tay: chúng là NÚT + `click`, và `click` thì chạy. Nên các bài ở đây bấm được thật, thay vì
 * giả vờ rằng `change` đã chạy.
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

let dap: ModelSettings = DU_LIEU;

function stubFetch(ds: ModelSettings = DU_LIEU): Goi[] {
  dap = ds;
  const goi: Goi[] = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
    goi.push({ method: init?.method ?? "GET", url: String(url), body });
    //: `PUT` trả lại bảng ĐÃ trộn — giống backend thật (nó trả `_bang(...)`).
    return new Response(JSON.stringify(dap), {
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

function cho() {
  return new Promise((r) => setTimeout(r, 40));
}

/** Nút mở một ô chọn, theo `aria-label`. */
function nutChon(nhan: string): HTMLButtonElement | undefined {
  return [...document.body.querySelectorAll("button")].find(
    (b) => b.getAttribute("aria-label") === nhan,
  ) as HTMLButtonElement | undefined;
}

/** Mở một ô chọn và đọc danh sách vừa hiện ra. */
async function moVaDoc(nhan: string): Promise<string[]> {
  const nut = nutChon(nhan);
  assert.ok(nut, `không thấy ô "${nhan}"`);
  fireEvent.click(nut);
  await cho();
  const hop = document.body.querySelector('[role="listbox"]');
  assert.ok(hop, `bấm "${nhan}" mà không mở danh sách`);
  //: Bỏ dấu "đang chọn" (◆) ở đầu mỗi dòng: nó là trang trí, không phải tên model.
  return [...hop.querySelectorAll('[role="option"]')].map((o) =>
    (o.textContent ?? "").replace(/^◆/, "").replace(/\s+/g, " ").trim(),
  );
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
    for (const ten of ["Phiên âm", "Dịch", "Ghép nền", "OCR", "ASR", "Burn phụ đề"]) {
      assert.ok(chu.includes(ten), `thiếu "${ten}" trong panel: ${chu.slice(0, 200)}`);
    }
  });

  it("việc chỉ có MỘT ứng viên KHÔNG vẽ ô dự phòng, và nói rõ 'chỉ có một model'", async () => {
    stubFetch();
    mo();
    await cho();
    assert.equal(nutChon("model dự phòng của OCR"), undefined,
      "OCR chỉ có một model mà vẫn vẽ ô dự phòng — ô nói dối rằng có thể chọn");
    assert.ok(nutChon("model dự phòng của ASR"), "ASR phải có ô dự phòng");
    assert.match(document.body.textContent ?? "", /chỉ có một model/);
  });

  it("TÊN MODEL hiện ngay dưới tên việc, kèm dự phòng nếu có", async () => {
    stubFetch();
    mo();
    await cho();
    const chu = document.body.textContent ?? "";
    //: Yêu cầu của chủ dự án: *"phần header của task phải hiện các tên model tương ứng ở dưới"*.
    assert.match(chu, /ASR\s*Whisper large-v3\s*· dự phòng: Whisper medium/, chu.slice(0, 600));
    assert.match(chu, /OCR\s*RapidOCR/);
    assert.match(chu, /Burn phụ đề\s*GPU NVENC\s*· dự phòng: CPU x264/);
  });

  it("câu 'đang chạy' là của BACKEND, chỉ hiện khi đã rơi về dự phòng", async () => {
    stubFetch();
    mo();
    await cho();
    const chu = document.body.textContent ?? "";
    assert.match(chu, /đang chạy bằng model dự phòng:\s*fw-medium/, chu.slice(0, 400));
    assert.match(chu, /đang chạy bằng model dự phòng:\s*libx264/);
  });

  it("ứng viên chưa sẵn sàng được ghi rõ TRONG danh sách xổ xuống", async () => {
    stubFetch();
    mo();
    await cho();
    const nhan = await moVaDoc("model sử dụng của Burn phụ đề");
    assert.ok(
      nhan.some((t) => t.includes("GPU NVENC") && t.includes("chưa sẵn sàng")),
      `danh sách phải nói rõ model chưa chạy được: ${nhan.join(" | ")}`,
    );
  });
});

describe("CaiDatModel: nhóm MT/LLM đổi DANH SÁCH và đổi GIÁ TRỊ", () => {
  it("nhóm Dịch có thanh gạt MT / LLM (radio thật)", async () => {
    stubFetch();
    mo();
    await cho();
    const radios = [...document.body.querySelectorAll('input[type="radio"]')];
    assert.equal(radios.length, 2, `phải có đúng hai lựa chọn nhóm, đo được ${radios.length}`);
    const nhan = radios.map((r) => r.parentElement?.textContent ?? "");
    assert.ok(nhan.some((t) => t === "MT"), nhan.join(" | "));
    assert.ok(nhan.some((t) => t === "LLM"), nhan.join(" | "));
  });

  it("đang MT ⇒ danh sách CHỈ có engine MT (opus-mt), không lẫn LLM", async () => {
    stubFetch();
    mo();
    await cho();
    const nhan = await moVaDoc("model sử dụng của Dịch");
    assert.deepEqual(nhan, ["OPUS-MT"],
      `nhóm MT mà lộ engine khác: ${nhan.join(" | ")}`);
  });

  it("bấm LLM ⇒ danh sách đổi sang engine LLM NGAY, không cần lưu", async () => {
    stubFetch();
    mo();
    await cho();
    const nutLlm = [...document.body.querySelectorAll("label")].find(
      (l) => (l.textContent ?? "") === "LLM",
    );
    assert.ok(nutLlm, "không thấy nhãn LLM");
    fireEvent.click(nutLlm.querySelector("input") as HTMLInputElement);
    await cho();

    //: FIX CỦA CHỦ DỰ ÁN: chọn LLM thì danh sách phải đổi theo, và vì `opus-mt` là engine
    //: MT nên giá trị phải chuyển sang engine LLM đầu tiên — không được để ô rỗng.
    const nhan = await moVaDoc("model sử dụng của Dịch");
    assert.equal(nhan.length, 1, `nhóm LLM phải chỉ còn engine LLM: ${nhan.join(" | ")}`);
    assert.match(nhan[0], /Qwen2\.5-7B/, `nhóm LLM mà danh sách không đổi: ${nhan.join(" | ")}`);
    assert.match(document.body.textContent ?? "", /1 việc chưa lưu/,
      "đổi nhóm kéo theo đổi model nên phải có thay đổi chưa lưu");
  });

  it("nhóm MỞ ĐẦU lấy theo model đang chạy, không theo nhóm đã lưu", async () => {
    //: Dữ liệu thật của máy này: `nhom_dich = "mt"` nhưng model đang chạy là `hy-mt-1.5-7b`
    //: (LLM). Mở bảng mà lọc theo nhóm cũ thì ô chọn TRỐNG ngay từ giây đầu.
    stubFetch({
      ...DU_LIEU,
      nhom_dich: "mt",
      tasks: DU_LIEU.tasks.map((t) =>
        t.id === "dich" ? { ...t, used: "qwen2.5-7b" } : t,
      ),
    });
    mo();
    await cho();
    const nhan = await moVaDoc("model sử dụng của Dịch");
    assert.ok(
      nhan.some((t) => t.includes("Qwen2.5-7B")),
      `nhóm mở đầu phải theo model đang chạy: ${nhan.join(" | ")}`,
    );
    assert.ok(!nhan.some((t) => t.includes("OPUS-MT")), nhan.join(" | "));
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

  it("Escape đóng bảng (chuột không phải đường duy nhất)", async () => {
    stubFetch();
    let dong = 0;
    render(<CaiDatModel open onClose={() => { dong += 1; }} />);
    await cho();
    fireEvent.keyDown(window, { key: "Escape" });
    assert.equal(dong, 1, "Escape phải đóng bảng");
  });

  it("dòng 'đang chạy' KHÔNG được vẽ khi nó chỉ lặp lại model đang chọn", async () => {
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
});
