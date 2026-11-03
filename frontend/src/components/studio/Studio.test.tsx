/**
 * Test `Studio.tsx` — thành phần GHÉP, chạy trên DOM thật (jsdom).
 *
 * Vì sao cần: đo bằng `Select-String` trên 8 tệp test cũ, KHÔNG bài nào chạm
 * `Studio.tsx`. `lib/studio.test.ts` phủ tầng DẪN XUẤT (hàm thuần); tệp này phủ
 * tầng GHÉP — chỗ quyết định *bấm nút thì gọi prop nào*, và chỗ đã để lọt hai lỗi
 * thật (xem ERRATA #55):
 *
 *   1. `onStep("duyet")` `return` TRƯỚC khi gọi `onBuoc` ⇒ `POST /approve` không
 *      bao giờ chạy. Bài "bấm Duyệt gọi onBuoc" ghim điều đó.
 *   2. `onResize` kẹp `end` bằng `Math.min(player.duration, …)` khi `duration` là
 *      `NaN` ⇒ đoạn dài 0 giây. Bài "kéo mốc khi duration chưa biết" ghim điều đó.
 *
 * DOM: `test/dom.ts` (`setupDom` / `teardownDom`). `fetch` của jsdom được cầu nối
 * sang origin thật, nhưng tệp này KHÔNG cần mạng: mọi prop đều dựng tay, và ta
 * không đưa `source` nên không có lượt tải media/waveform nào.
 *
 * Runner: `node --test` + loader SWC. Tệp PHẢI là `.tsx` (loader đặt
 * `tsx: url.endsWith(".tsx")`); `.ts` chứa JSX sẽ chết lúc load.
 */
import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import type {
  DubPlanRow,
  Job,
  Segment,
  Source,
  Transcript,
  TranslationDetail,
} from "../../api/types.ts";
import { cleanup, fireEvent, render, waitFor, within } from "@testing-library/react";
import { Studio, type StudioProps } from "./Studio.tsx";
import { VUNG_DOC_MAC_DINH } from "./VungDoc.tsx";
import { setupDom, teardownDom } from "../../../test/dom.ts";

const ORIGIN = "http://127.0.0.1:8620";

beforeEach(() => {
  teardownDom();
  setupDom(ORIGIN);
});

afterEach(() => {
  cleanup();
  teardownDom();
});

/**
 * Truy van tren `document.body` HIEN TAI, khong qua `screen`.
 *
 * ⚠️ DO DUOC: `@testing-library/react` bind `screen` vao `document` tai thoi diem
 * MODULE DUOC NAP. `test/dom.ts` chi tao `document` trong `beforeEach`, tuc SAU khi
 * module nay nap ⇒ moi `screen.getByRole` nem
 *   `TypeError: For queries bound to document.body a global document has to be available`.
 * `within(document.body)` doc `document` LUC GOI, nen no luon thay jsdom hien hanh.
 */
function q() {
  return within(document.body);
}

// ---------------------------------------------------------------------------
// Dựng dữ liệu — chỉ trường mà `Studio` đọc, không bịa thêm.
// ---------------------------------------------------------------------------

function doan(p: Partial<Segment> & { i: number }): Segment {
  // 🔴 `layer` MAC DINH `"mot_nguon"`, khong phai `null`.
  //
  // `Timeline` loc `s.layer !== null && lopBat[s.layer]`. Fixture cu khong co `layer`,
  // nen `lopCua` tra `null` va MOI doan bi loai — 39 bai do voi "chua co o phu de nao".
  // Backend #50 gan `layer` cho CA 158 doan, nen fixture phai mo ta dung du lieu that.
  return { start: 0, end: 1, text: "", suspect: false, layer: "mot_nguon", ...p };
}

function banGhi(segments: Segment[]): Transcript {
  return {
    id: 2,
    source_id: 1,
    engine: "whisper",
    lang: "zh",
    version: 1,
    status: "translated",
    created_at: "2026-01-01T00:00:00Z",
    translations: [],
    segments,
  };
}

function banDichCua(segments: Segment[]): TranslationDetail {
  return {
    id: 4,
    transcript_id: 2,
    engine: "opus",
    lang: "vi",
    status: "done",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    segments,
    cps: { max_cps: 21, rows: [] },
  };
}

/**
 * `id` của bản dịch trong fixture — PHẢI khớp `banDichCua()`.
 *
 * 🔴 ĐO ĐƯỢC (bài test "Ghép nền" đỏ vì lý do này, không phải vì sản phẩm):
 * `banDichCua()` trả `id: 4`, còn job mẫu của tôi ghi `translation_id: 1`. `jobGhep`
 * lọc theo `translation_id === banDich.id`, nên nó ra rỗng và bước "Ghép nền" đứng ở
 * "chưa chạy" — đúng như nó phải, vì job đó thuộc một bản dịch KHÁC.
 *
 * Viết cứng `1` ở ba chỗ là ba cơ hội để lệch khỏi fixture; đọc từ chính `banDichCua()`
 * thì không thể lệch.
 */
const BAN_DICH_ID = banDichCua([]).id;

const KENH = {
  id: 1,
  kind: "file",
  name: "phude.mp4",
  path: "/data/media/phude.mp4",
  lang: "zh",
  size: 1024,
  duration: 10,
  created_at: "2026-01-01T00:00:00Z",
} as unknown as Source;

interface LoiGoi {
  ten: string;
  args: unknown[];
}

/** Bộ prop đầy đủ, mọi callback là bản ghi lời gọi để đếm. */
function dungThu(p: Partial<StudioProps> = {}): { props: StudioProps; goi: LoiGoi[] } {
  const goi: LoiGoi[] = [];
  const ghi =
    (ten: string) =>
    (...args: unknown[]): void => {
      goi.push({ ten, args });
    };

  const props: StudioProps = {
    sources: [KENH],
    sourcesLoading: false,
    sourcesError: null,
    source: null,
    onChonKenh: ghi("onChonKenh"),
    transcript: banGhi([
      doan({ i: 0, start: 0, end: 2.04, text: "你绝对没吃过" }),
      doan({ i: 1, start: 4.36, end: 5.58, text: "我这么多汤" }),
    ]),
    banDich: banDichCua([
      doan({ i: 0, start: 0, end: 2.04, text: "Bạn chắc chắn chưa từng ăn" }),
      doan({ i: 1, start: 4.36, end: 5.58, text: "Tôi nhiều nước dùng thế" }),
    ]),
    cps: null,
    keHoach: new Map<number, DubPlanRow>(),
    jobs: [] as Job[],
    daDuyet: new Set<number>(),
    onDuyet: ghi("onDuyet"),
    onSuaChu: ghi("onSuaChu"),
    onSuaMoc: async (...args: unknown[]) => {
      goi.push({ ten: "onSuaMoc", args });
    },
    onXuatVideo: ghi("onXuatVideo"),
    onBuoc: ghi("onBuoc"),
    onNapTep: async (...args: unknown[]) => {
      goi.push({ ten: "onNapTep", args });
    },
    onLongLai: ghi("onLongLai"),
    loi: null,
    soEngine: 3,
    vungDoc: VUNG_DOC_MAC_DINH,
    onVungDoc: ghi("onVungDoc"),
    ...p,
  };
  return { props, goi };
}

/** Tên các callback đã được gọi, theo thứ tự. */
function tenDaGoi(goi: LoiGoi[]): string[] {
  return goi.map((g) => g.ten);
}

// ---------------------------------------------------------------------------

describe("Studio: dựng được ở cả ba góc nhìn", () => {
  it("mặc định là Biên tập, hiện ô phụ đề của từng đoạn với chữ BẢN DỊCH", () => {
    const { props } = dungThu();
    render(<Studio {...props} />);
    const o = q().getAllByLabelText(/^Phụ đề đoạn/);
    assert.equal(o.length, 2);
    assert.equal((o[0] as HTMLInputElement).value, "Bạn chắc chắn chưa từng ăn");
  });

  it("góc nhìn Đối chiếu hiện CẢ bản gốc và bản dịch", () => {
    const { props } = dungThu();
    render(<Studio {...props} />);
    fireEvent.click(q().getByRole("button", { name: /^Doi chieu/ }));
    assert.ok(q().getAllByText("你绝对没吃过"), "phải thấy bản gốc");
    assert.ok(q().getAllByText("Bạn chắc chắn chưa từng ăn"), "phải thấy bản dịch");
  });

  it("góc nhìn Lồng tiếng hiện câu bản dịch", () => {
    const { props } = dungThu();
    render(<Studio {...props} />);
    fireEvent.click(q().getByRole("button", { name: /^Long tieng/ }));
    assert.ok(q().getAllByText("Bạn chắc chắn chưa từng ăn"));
  });

  it("chưa có bản ghi thì không nổ và không có ô phụ đề nào", () => {
    const { props } = dungThu({ transcript: null, banDich: null });
    render(<Studio {...props} />);
    assert.equal(q().queryAllByLabelText(/^Phụ đề đoạn/).length, 0);
  });
});

/**
 * Gọi THẲNG `onChange` mà React đã đăng ký trên phần tử.
 *
 * 🔴 ĐO ĐƯỢC, KHÔNG PHẢI LỰA CHỌN THẨM MỸ. Ba cách mô phỏng sự kiện đều KHÔNG
 * làm `onChange` chạy, dù `value` của ô có đổi:
 *
 *     fireEvent.change(el, …)                          -> goi = []
 *     fireEvent.input(el, …)                           -> goi = []
 *     native setter + dispatchEvent(new Event("input")) -> goi = []
 *     native setter + dispatchEvent(new Event("change")) -> goi = []
 *
 * Trong khi đó soi `__reactProps$…` trên chính phần tử cho thấy `onChange` LÀ một
 * function, `value` đúng, `disabled=false`, `readOnly=false`. Nguyên nhân: mỗi bài
 * `setupDom()` tạo một `document` MỚI, còn `@testing-library` giữ tham chiếu tới
 * `document` cũ, nên phép mô phỏng sự kiện đi vào cây đã chết.
 *
 * Gọi thẳng handler là phép đo ĐÚNG BẢN CHẤT của bài này: nó kiểm *"khi ô phụ đề
 * báo chuỗi mới thì Studio có chuyển đúng `i` và đúng chữ cho `onSuaChu` không"*,
 * chứ không kiểm React có gắn listener hay không (React tự bảo đảm điều đó, và
 * trình duyệt thật đã được đo ở ERRATA #55: `PATCH /api/translations/4` chạy).
 */
function goChu(el: HTMLInputElement, chu: string): void {
  let p: Record<string, unknown> | undefined;
  for (const k of Object.keys(el)) {
    if (k.startsWith("__reactProps")) {
      p = (el as unknown as Record<string, Record<string, unknown>>)[k];
    }
  }
  assert.ok(p !== undefined, "không tìm thấy react props trên ô phụ đề");
  const fn = p.onChange as ((e: unknown) => void) | undefined;
  assert.ok(typeof fn === "function", "ô phụ đề không có onChange");
  fn({ target: { value: chu } });
}

describe("Studio: sửa chữ gọi onSuaChu với ĐÚNG i và chữ mới", () => {
  it("gõ vào ô đoạn 0 gọi onSuaChu(0, chuỗiMới)", () => {
    const { props, goi } = dungThu();
    render(<Studio {...props} />);
    const o = q().getAllByLabelText(/^Phụ đề đoạn/)[0] as HTMLInputElement;
    goChu(o, "chữ đã sửa");
    const sua = goi.filter((g) => g.ten === "onSuaChu");
    assert.equal(sua.length, 1, `phải gọi đúng một lần, đo được ${JSON.stringify(tenDaGoi(goi))}`);
    assert.deepEqual(sua[0].args, [0, "chữ đã sửa"]);
  });

  it("gõ vào ô đoạn 1 gọi onSuaChu(1, …) — không lệch chỉ số", () => {
    const { props, goi } = dungThu();
    render(<Studio {...props} />);
    const o = q().getAllByLabelText(/^Phụ đề đoạn/)[1] as HTMLInputElement;
    goChu(o, "đoạn hai");
    const sua = goi.filter((g) => g.ten === "onSuaChu");
    assert.equal(sua.length, 1);
    assert.deepEqual(sua[0].args, [1, "đoạn hai"]);
  });
});

describe("Studio: đổi kênh thì QUÊN dòng đang chọn", () => {
  /**
   * 🔴 LỖI THẬT, ĐO ĐƯỢC khi rà soát toàn bộ state: `currentId` là state CỤC BỘ của
   * `Studio`, và KHÔNG có gì reset nó khi `source` đổi. Đổi sang video khác thì
   * `currentId` vẫn giữ số dòng của video CŨ:
   *
   *   · video mới ÍT dòng hơn  ⇒ `current` thành `null`, panel sửa chữ trống rỗng mà
   *     không nói vì sao;
   *   · video mới NHIỀU dòng hơn ⇒ nó chọn một dòng CÙNG SỐ THỨ TỰ mà người dùng chưa hề
   *     bấm.
   *
   * Cùng lớp lỗi với `VungDoc` (một `useEffect` ghi đè dữ liệu người dùng mỗi lần nạp
   * trang): state cục bộ sống lâu hơn dữ liệu mà nó mô tả.
   *
   * ⚠️ Trạng thái ĐÚNG sau khi đổi kênh KHÔNG phải "không chọn dòng nào": `Studio` tự
   * chọn dòng ĐẦU khi có dòng (effect `daChonDau`). Nên phép đo là: chọn dòng 1 của kênh
   * A, đổi sang kênh B, và panel sửa chữ phải quay về dòng 0 — không được giữ dòng 1.
   *
   * Kênh B cố ý có CÙNG bộ dòng, nên nếu không reset thì số thứ tự 1 vẫn khớp và nội dung
   * của kênh A vẫn hiện. Đó là thứ cần bắt; cho kênh B ít dòng hơn thì `current` thành
   * `null` và bài test xanh vì lý do khác.
   */
  it("chọn dòng 1 ở kênh A, đổi sang kênh B ⇒ quay về dòng 0, không giữ dòng 1", async () => {
    const { props } = dungThu({ source: KENH });
    const { rerender } = render(<Studio {...props} />);

    // 🔴 PHÉP ĐO PHẢI ĐỌC THỨ THỰC SỰ PHỤ THUỘC `currentId`.
    //
    // Hai lần sai trước, ghi lại vì cả hai đều cho bài test XANH khi đã gỡ effect reset
    // (tức test GIẢ):
    //
    //   1. Chọn dòng bằng `goChu` (chỉ phát `onChange`). `onSelect` gắn vào
    //      `<li onClick={onSelect}>` (`SegmentRow.tsx:64-66`), nên gõ vào ô KHÔNG đổi
    //      `currentId` — chưa bao giờ có dòng nào được chọn.
    //   2. Đọc `value` của ô đoạn 0. Đo được: `SegmentRow` chỉ dùng `current` để tô nền
    //      (`bg-signal-soft`), vẽ vạch `w-[3px]`, và đổi màu số thứ tự — KHÔNG dùng nó
    //      cho giá trị ô nhập. Nên giá trị ô đoạn 0 luôn như nhau dù `currentId` là gì.
    //
    // Thứ DUY NHẤT đọc được bằng chữ và phụ thuộc thẳng `currentId` là khối
    // `Đoạn #N` (`Studio.tsx:1027-1032`): nó chỉ hiện khi `current !== null`, và `N`
    // tính từ vị trí của `current` trong danh sách.
    const hang1 = q()
      .getAllByRole("listitem")
      .find((li) => li.querySelector('[aria-label="Phụ đề đoạn 1"]') !== null);
    assert.ok(hang1, "không tìm được hàng của đoạn 1 để bấm");
    fireEvent.click(hang1);

    await waitFor(() => {
      assert.match(
        document.body.textContent ?? "",
        /Đoạn #2/,
        "bấm hàng đoạn 1 mà khối 'Đoạn #' không chuyển sang #2 — phép đo sau vô nghĩa",
      );
    });

    rerender(<Studio {...props} source={{ ...KENH, id: 2 }} />);

    await waitFor(() => {
      assert.match(
        document.body.textContent ?? "",
        /Đoạn #1/,
        "đổi kênh mà khối 'Đoạn #' VẪN ở #2 — `currentId` chưa reset theo `source.id`, " +
        "nên nó đang trỏ vào dòng cùng số thứ tự của kênh cũ",
      );
    });
  });
});

describe("Studio: nút duyệt trên DÒNG là tập cục bộ, không gọi onBuoc", () => {
  it("bấm 'duyệt' trong dòng gọi onDuyet(i), KHÔNG gọi onBuoc", () => {
    const { props, goi } = dungThu();
    render(<Studio {...props} />);
    fireEvent.click(q().getByRole("button", { name: "duyet doan 1" }));
    assert.deepEqual(tenDaGoi(goi), ["onDuyet"]);
    assert.deepEqual(goi[0].args, [0]);
  });

  it("dòng đã duyệt thì nút đổi nhãn thành 'bỏ duyệt'", () => {
    const { props } = dungThu({ daDuyet: new Set([0]) });
    render(<Studio {...props} />);
    assert.ok(q().getByRole("button", { name: "bo duyet doan 1" }));
  });
});

describe("Studio: bước 'duyet' trên thanh đường ống PHẢI gọi onBuoc (ERRATA #55)", () => {
  it("bấm bước Duyệt gọi onBuoc('duyet') — đây là đường DUY NHẤT ghi status", () => {
    // Trước khi sửa: `onStep` bắt `id === "duyet"` rồi `return` trước `onBuoc`, nên
    // `POST /api/transcripts/{id}/approve` không bao giờ chạy. Bài này ghim chiều
    // ngược lại: `onBuoc` PHẢI được gọi với đúng mã "duyet".
    const { props, goi } = dungThu();
    render(<Studio {...props} />);
    fireEvent.click(q().getByRole("button", { name: /^Duyệt/ }));
    assert.ok(
      tenDaGoi(goi).includes("onBuoc"),
      `phải gọi onBuoc, đo được ${JSON.stringify(tenDaGoi(goi))}`,
    );
    const buoc = goi.filter((g) => g.ten === "onBuoc");
    assert.deepEqual(buoc[0].args, ["duyet"]);
  });

  it("bấm bước Duyệt đưa đoạn đầu tiên có việc vào tầm nhìn (giữ hành vi cũ)", () => {
    // ⚠️ ĐO ĐƯỢC: `SegmentRow` KHÔNG đặt `aria-current` lên dòng đang chọn — nó chỉ
    // đổi lớp (`bg-signal-soft`) và vẽ một vạch `bg-signal` bên trái. Vì vậy phép đo
    // `[aria-current="true"]` cho 0 phần tử, KHÔNG phải vì "nhảy tới việc" hỏng.
    //
    // Đo bằng thứ có thật: `scrollIntoView` được gọi trên dòng của đoạn 0. `test/dom.ts`
    // cài một stub rỗng, nên ở đây ta ĐẾM lời gọi bằng cách bọc lại stub đó.
    const { props } = dungThu({
      transcript: banGhi([
        doan({ i: 0, start: 0, end: 2, text: "a", suspect: true }),
        doan({ i: 1, start: 3, end: 4, text: "b", suspect: true }),
      ]),
    });
    const daGoi: string[] = [];
    const goc = window.Element.prototype.scrollIntoView;
    window.Element.prototype.scrollIntoView = function scrollIntoView() {
      daGoi.push(this.getAttribute("data-i") ?? this.tagName);
    };
    try {
      render(<Studio {...props} />);
      fireEvent.click(q().getByRole("button", { name: /^Duyệt/ }));
    } finally {
      window.Element.prototype.scrollIntoView = goc;
    }
    assert.ok(daGoi.length > 0, "phải gọi scrollIntoView cho việc đầu tiên");
  });

  it("bước Xuất khi chưa có tệp thì KHÔNG gọi onXuatVideo", () => {
    const { props, goi } = dungThu();
    render(<Studio {...props} />);
    fireEvent.click(q().getByRole("button", { name: /^Xuất/ }));
    assert.ok(!tenDaGoi(goi).includes("onXuatVideo"), "chưa có tệp thì không xuất");
  });
});

describe("Studio: bước Dịch và Lồng tiếng chỉ ĐỔI GÓC NHÌN, không chạy job", () => {
  it("bấm bước Dịch không gọi onBuoc", () => {
    const { props, goi } = dungThu();
    render(<Studio {...props} />);
    fireEvent.click(q().getByRole("button", { name: /^Dịch/ }));
    assert.ok(!tenDaGoi(goi).includes("onBuoc"));
  });

  it("bấm bước Lồng tiếng không gọi onBuoc", () => {
    // ⚠️ Có HAI thứ tên "Lồng tiếng": nút đổi góc nhìn (`VIEWS`, nhãn "Long tieng"
    // KHÔNG dấu) và bước trên thanh đường ống (tên "Lồng tiếng" CÓ dấu). Chọn theo
    // đúng chuỗi của bước để không trúng nút kia.
    const { props, goi } = dungThu();
    render(<Studio {...props} />);
    fireEvent.click(q().getByRole("button", { name: /^Lồng tiếng/ }));
    assert.ok(!tenDaGoi(goi).includes("onBuoc"));
  });
});

describe("Studio: thông báo lỗi từ tầng trên được HIỆN, không nuốt", () => {
  it("prop `loi` hiện thành chữ trên màn hình", () => {
    const { props } = dungThu({ loi: "máy chủ trả 500" });
    render(<Studio {...props} />);
    assert.ok(q().getByText(/máy chủ trả 500/));
  });
});

// ---------------------------------------------------------------------------
// DẤU TÍCH CỦA BƯỚC "GHÉP NỀN" — phải hiện khi việc đã XONG.
//
// 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng: *"khi hoàn thành xong task nào đó thì phần refresh
// lại để nó hiện ra dấu tích"*). `jobGhep` lọc:
//
//     j.type === "export" && j.payload["translation_id"] === banDich.id
//
// Hai trường đó KHÔNG CÙNG TỒN TẠI. Đo trên `GET /api/jobs` (108 job):
//
//     #64 export done {"transcript_id": 9, "format": "srt", ...}
//     #65 export done {"transcript_id": 9, "format": "ass", ...}
//
// `ExportPayload` (`routes_jobs.py:95`) có `transcript_id`/`format`/`bilingual`/`stem`/
// `translations` — KHÔNG có `translation_id`. Nên phép lọc luôn rỗng, `jobGhep` luôn
// `null`, và hai bước "Ghép nền"/"Xuất" KHÔNG BAO GIỜ đạt `done` ⇒ không bao giờ có dấu
// tích, dù `dub-{tid}.mp4` đã nằm trên đĩa.
//
// Sự thật: GHÉP NỀN không phải một loại job — nó là job `dub` với
// `payload.tron_nen = true` (`dub.py:229-234`, `296`), chính nó sinh ra mp4.
// ---------------------------------------------------------------------------

/** Job mẫu — chỉ những trường mà `Studio` đọc. */
/**
 * Trạng thái bước "Phiên âm" hiện trên thanh đường ống.
 *
 * Đọc `title` (chính là `note`) và chữ trong nút, KHÔNG đọc màu/nền: `state` là dữ liệu,
 * `bg-*` là trình bày — đổi bảng màu không được làm đỏ bài test.
 *
 * `PipelineBar.tsx` không đặt `aria-label`; `title={s.note}` là chỗ duy nhất mang `note` ra
 * ngoài DOM, nên nó là thứ phải đọc.
 */
function buocTheoTen(ten: string): { chu: string; ghiChu: string; ten: string; nut: HTMLElement } {
  // Tim TRONG `<ol aria-label="Cac buoc xu ly">`.
  // ⚠️ DO DUOC: tim ngoai pham vi do khop HAI nut cung ten "Long tieng" — nut doi goc nhin
  // (`Studio.tsx:74`) va nut buoc tren thanh duong ong — nen `getByRole` NEM con
  // `getAllByRole` thi bam nham nut.
  const thanh = q().getByLabelText("Các bước xử lý");
  const nut = within(thanh)
    .getAllByRole("button")
    .find((b) => (b.textContent ?? "").startsWith(ten)) as HTMLElement | undefined;
  if (nut === undefined) throw new Error(`khong tim thay nut buoc '${ten}'`);
  return { chu: nut.textContent ?? "", ghiChu: nut.getAttribute("title") ?? "", ten, nut };
}

function buocAsr(): { chu: string; ghiChu: string } {
  const b = buocTheoTen("Phiên âm");
  return { chu: b.chu, ghiChu: b.ghiChu };
}

function job(p: Partial<Job> & { id: number }): Job {
  return {
    workspace: 1,
    type: "dub",
    engine: null,
    phase: "dub:-",
    state: "queued",
    cancel_requested: false,
    attempts: 0,
    progress: 0,
    log_tail: "",
    error: null,
    payload: {},
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
    ...p,
  };
}

describe("Studio: bước Ghép nền hiện dấu tích khi job dub tron_nen xong", () => {
  it("có job dub tron_nen done ⇒ bước Ghép nền done (dấu tích hiện)", () => {
    const { props } = dungThu({
      source: KENH,
      jobs: [
        job({
          id: 70,
          type: "dub",
          state: "done",
          payload: { translation_id: BAN_DICH_ID, tron_nen: true },
        }),
      ],
    });
    render(<Studio {...props} />);
    // `PipelineBar` vẽ `s.note` dưới tên bước; bước done mang nhãn "đã ghép".
    assert.match(
      document.body.textContent ?? "",
      /đã ghép/,
      "job dub tron_nen đã done mà bước Ghép nền KHÔNG hiện 'đã ghép' — dấu tích không " +
      "bao giờ hiện vì phép lọc tìm `export` + `translation_id` (không cùng tồn tại)",
    );
  });

  it("job dub KHÔNG tron_nen thì Ghép nền vẫn chưa xong", () => {
    // Vế chống sửa quá tay: nếu ai đó bỏ điều kiện `tron_nen`, mọi job lồng tiếng đều
    // thành "đã ghép nền" và dấu tích hiện sai — video chưa hề có bản trộn nền.
    const { props } = dungThu({
      source: KENH,
      jobs: [job({ id: 71, type: "dub", state: "done", payload: { translation_id: BAN_DICH_ID } })],
    });
    render(<Studio {...props} />);
    assert.doesNotMatch(
      document.body.textContent ?? "",
      /đã ghép/,
      "job dub KHÔNG tron_nen mà bước Ghép nền báo 'đã ghép' — thiếu điều kiện tron_nen",
    );
  });

  it("job dub tron_nen còn đang chạy ⇒ chưa có dấu tích", () => {
    const { props } = dungThu({
      source: KENH,
      jobs: [
        job({
          id: 72,
          type: "dub",
          state: "running",
          payload: { translation_id: BAN_DICH_ID, tron_nen: true },
        }),
      ],
    });
    render(<Studio {...props} />);
    assert.doesNotMatch(document.body.textContent ?? "", /đã ghép/);
  });
});


// ---------------------------------------------------------------------------
// TRẠNG THÁI LẠC QUAN CỦA BƯỚC "PHIÊN ÂM" — đổi NGAY lúc bấm
//
// 🔴 LỖI THẬT, ĐO ĐƯỢC (người dùng: "nên đổi state từ cái lúc ấn ý").
//
// `asrState` suy từ `jobAsr`, mà `jobAsr` chỉ có sau khi `GET /api/jobs` trả về. Hai độ trễ
// cộng lại:
//
//   1. nhịp hỏi `NHIP_JOB_MS = 2000` — tối đa 2 giây trước lượt hỏi kế tiếp;
//   2. độ trễ mạng + thời gian `POST /api/jobs` trả về (job phải được GHI vào DB rồi mới
//      lọt vào danh sách).
//
// Trong khoảng đó bước vẫn vẽ dấu tích của bản ghi CŨ. Người dùng bấm, thấy không có gì đổi,
// và bấm lại — đo được trong lịch sử job: #95/#96, #98/#99, #101/#102 đều là cặp job `asr`
// cách nhau vài giây, tức thao tác bị lặp vì giao diện không phản hồi.
// ---------------------------------------------------------------------------

describe("Studio: bước Phiên âm đổi trạng thái NGAY lúc bấm", () => {
  it("bấm Phiên âm khi đã có bản ghi cũ ⇒ bước đổi sang 'đang phiên âm…' ngay, chưa cần job", () => {
    // Đây đúng là ca người dùng báo: nguồn đã có bản ghi (nên bước đang tick), bấm chạy lại.
    const { props } = dungThu({ source: KENH, jobs: [] as Job[] });
    render(<Studio {...props} />);

    assert.equal(buocAsr().ghiChu, 'whisper', 'truoc khi bam: buoc ghi engine cua ban ghi cu (banGhi() dung engine: whisper)');

    fireEvent.click(q().getByRole("button", { name: /^Phiên âm/ }));

    assert.equal(
      buocAsr().ghiChu,
      "đang phiên âm…",
      "bấm xong phải đổi NGAY; còn ghi engine cũ nghĩa là vẫn đợi /api/jobs (tới 2 giây)",
    );
  });

  it("bấm Phiên âm vẫn gọi onBuoc('asr') — đổi màu KHÔNG được thay việc gửi job", () => {
    // Vế ngược lại: nếu chỉ đổi state mà quên `onBuoc` thì giao diện nói dối là đang chạy
    // trong khi không có job nào được tạo — tệ hơn lỗi gốc.
    const { props, goi } = dungThu({ source: KENH, jobs: [] as Job[] });
    render(<Studio {...props} />);
    fireEvent.click(q().getByRole("button", { name: /^Phiên âm/ }));
    assert.deepEqual(
      goi.filter((g) => g.ten === "onBuoc").map((g) => g.args[0]),
      ["asr"],
      "phải gửi đúng một lời gọi onBuoc('asr')",
    );
  });

  it("job asr THẬT về với state 'running' ⇒ vẫn 'đang phiên âm…', không nhấp nháy về tick", () => {
    const { props, rerender } = (() => {
      const r = dungThu({ source: KENH, jobs: [] as Job[] });
      const { rerender: rr } = render(<Studio {...r.props} />);
      return { props: r.props, rerender: rr };
    })();
    fireEvent.click(q().getByRole("button", { name: /^Phiên âm/ }));
    assert.equal(buocAsr().ghiChu, "đang phiên âm…");

    rerender(
      <Studio
        {...props}
        jobs={[job({ id: 109, type: "asr", state: "running", payload: { source_id: KENH.id } })]}
      />,
    );
    assert.equal(
      buocAsr().ghiChu,
      "đang phiên âm…",
      "job thật đã tới thì trạng thái phải GIỮ NGUYÊN, không được nhảy về tick",
    );
  });

  it("job asr THẬT về với state 'failed' ⇒ HIỆN LỖI, cờ lạc quan phải tan", () => {
    // Che lỗi bằng trạng thái lạc quan là kiểu nói dối mà cả hai lần sửa này đang diệt.
    const r = dungThu({ source: KENH, jobs: [] as Job[] });
    const { rerender } = render(<Studio {...r.props} />);
    fireEvent.click(q().getByRole("button", { name: /^Phiên âm/ }));

    rerender(
      <Studio
        {...r.props}
        jobs={[job({ id: 110, type: "asr", state: "failed", payload: { source_id: KENH.id } })]}
      />,
    );
    assert.equal(buocAsr().ghiChu, "lỗi — xem hàng đợi", "job hỏng phải hiện lỗi, không che");
  });

  it("job asr 'done' mà cờ lạc quan ĐÃ TAN ⇒ về tick, không kẹt ở 'đang phiên âm…'", () => {
    // Bài này ghim vế dễ hỏng nhất: nếu effect KHÔNG BAO GIỜ tắt cờ thì sau lần bấm đầu,
    // mọi trạng thái `done` sau này bị che thành "đang phiên âm…" VĨNH VIỄN.
    const r = dungThu({ source: KENH, jobs: [] as Job[] });
    const { rerender } = render(<Studio {...r.props} />);
    fireEvent.click(q().getByRole("button", { name: /^Phiên âm/ }));

    // 1. job thật `running` -> cờ tan.
    rerender(
      <Studio
        {...r.props}
        jobs={[job({ id: 111, type: "asr", state: "running", payload: { source_id: KENH.id } })]}
      />,
    );
    // 2. job xong -> `done` + đã có bản ghi -> phải về engine, KHÔNG kẹt.
    rerender(
      <Studio
        {...r.props}
        jobs={[job({ id: 111, type: "asr", state: "done", payload: { source_id: KENH.id } })]}
      />,
    );
    assert.doesNotMatch(
      buocAsr().ghiChu,
      /đang phiên âm/,
      "cờ lạc quan không tan -> bước kẹt ở 'đang phiên âm…' mãi mãi",
    );
  });
});

// ---------------------------------------------------------------------------
// BA BUOC CON LAI CUNG PHAI DOI NGAY — nguoi dung: "tim cac state khac xem no cung
// nen nhu the".
//
// DO DUOC buoc nao that su co do tre khi bam:
//
//   asr   POST /api/jobs            -> can co lac quan  (da lam o khoi tren)
//   long  POST /api/dubs            -> can co lac quan
//   ghep  POST /api/dubs(tron_nen)  -> can co lac quan
//   duyet setDaDuyet cuc bo         -> KHONG co do tre, khong can co
//   xuat  the <a> tai tep truc tiep -> KHONG qua job, khong can co
//
// Hau qua do duoc cua viec thieu co o `long`: cap job `dub` **#47/#48** tren cung mot ban
// dich, tao cach nhau **47 giay** — nguoi dung bam lai vi buoc khong phan hoi.
// ---------------------------------------------------------------------------

describe("Studio: buoc Long tieng / Ghep nen cung doi NGAY luc bam", () => {
  it("bam buoc Long tieng => buoc doi sang dang chay ngay, chua can job dub", () => {
    const { props } = dungThu({ source: KENH, jobs: [] as Job[] });
    render(<Studio {...props} />);

    const truoc = buocTheoTen("Lồng tiếng");
    fireEvent.click(truoc.nut);

    assert.equal(
      buocTheoTen("Lồng tiếng").ghiChu,
      "đang chạy…",
      "bam xong phai doi ngay; con 'chua chay' nghia la van doi /api/jobs (toi 2 giay)",
    );
  });

  it("bam Long lai mot doan => goi onLongLai va doi buoc Long tieng ngay", () => {
    const { props, goi } = dungThu({ source: KENH, jobs: [] as Job[] });
    render(<Studio {...props} />);

    // Goc nhin Long tieng moi co nut "Long lai" (`SegmentRow.tsx:133` — `view === "dub"`).
    //
    // ⚠️ DO DUOC: `getByRole("button", { name: /^Long tieng/ })` NEM vi khop HAI nut —
    // nut doi goc nhin (`Studio.tsx:74`) va nut buoc tren thanh duong ong. Phai chon nut
    // doi goc nhin, va no la nut co `textContent` DUNG BANG "Long tieng".
    // ⚠️ DO DUOC: nhan nut la "Long tieng 3" — co ca SO PHIM TAT o cuoi
    // (`Studio.tsx:1288` in `{v.label} <span class="kbd">{i + 1}</span>`), nen so sanh
    // `textContent === "Long tieng"` khong bao gio khop. Phai dung `startsWith`.
    const doiGocNhin = q()
      .getAllByRole("button")
      .find((b) => (b.textContent ?? "").trim().startsWith("Long tieng")) as
      | HTMLElement
      | undefined;
    assert.ok(doiGocNhin, "khong tim thay nut doi goc nhin 'Long tieng'");
    fireEvent.click(doiGocNhin);

    const nut = q()
      .getAllByRole("button")
      .find((b) => (b.getAttribute("aria-label") ?? "") === "Lồng lại") as HTMLElement | undefined;
    assert.ok(nut, "khong tim thay nut 'Long lai' o goc nhin Long tieng");
    fireEvent.click(nut);

    assert.deepEqual(
      goi.filter((g) => g.ten === "onLongLai").map((g) => g.args[0]),
      [0],
      "phai goi onLongLai dung mot lan voi doan #0",
    );
    assert.equal(
      buocTheoTen("Lồng tiếng").ghiChu,
      "đang chạy…",
      "bam Long lai phai doi buoc Long tieng NGAY",
    );
  });

  it("co lac quan cua Long tieng TAN khi job dub that ve done", () => {
    // Ve de hong nhat, giong bai cua `asr`: co khong tan thi buoc ket o "dang chay…" mai.
    const r = dungThu({ source: KENH, jobs: [] as Job[] });
    const { rerender } = render(<Studio {...r.props} />);
    fireEvent.click(buocTheoTen("Lồng tiếng").nut);
    assert.equal(buocTheoTen("Lồng tiếng").ghiChu, "đang chạy…");

    rerender(
      <Studio
        {...r.props}
        jobs={[
          job({ id: 200, type: "dub", state: "running", payload: { translation_id: BAN_DICH_ID } }),
        ]}
      />,
    );
    rerender(
      <Studio
        {...r.props}
        jobs={[
          job({ id: 200, type: "dub", state: "done", payload: { translation_id: BAN_DICH_ID } }),
        ]}
      />,
    );
    assert.doesNotMatch(
      buocTheoTen("Lồng tiếng").ghiChu,
      /đang chạy/,
      "co lac quan khong tan -> buoc Long tieng ket o 'dang chay…' mai mai",
    );
  });

  it("job dub THAT ve voi failed => hien loi, co lac quan khong che", () => {
    const r = dungThu({ source: KENH, jobs: [] as Job[] });
    const { rerender } = render(<Studio {...r.props} />);
    fireEvent.click(buocTheoTen("Lồng tiếng").nut);

    rerender(
      <Studio
        {...r.props}
        jobs={[
          job({ id: 201, type: "dub", state: "failed", payload: { translation_id: BAN_DICH_ID } }),
        ]}
      />,
    );
    assert.equal(buocTheoTen("Lồng tiếng").ghiChu, "lỗi — xem hàng đợi");
  });
});


// ---------------------------------------------------------------------------
// THANH CHAY TREN BUOC — uoc luong tien do khi backend khong bao
//
// 🔴 VI SAO CAN: `Job.progress` dung nguyen o `0.05` suot thoi gian chay (do duoc tren
// job #113) roi nhay thang `1.0`. Nen giao dien truoc day chi biet hai trang thai, va
// nguoi dung nhin mot vong xoay dung yen khong biet con bao lau.
// ---------------------------------------------------------------------------

describe("Studio: buoc dang chay co thanh uoc luong tien do", () => {
  it("job asr running co started_at + duration => hien thanh chay voi tiLe", () => {
    // `started_at` cach 'bay gio' 92 s; mo hinh nhanh cho video 279 s la 18 s, nen
    // tiLe se cham tran 97 % — dieu quan trong la THANH PHAI CO, khong phai con so.
    const batDau = new Date(Date.now() - 92_000).toISOString();
    const { props } = dungThu({
      source: KENH,
      jobs: [
        job({ id: 300, type: "asr", state: "running", started_at: batDau, payload: { source_id: KENH.id } }),
      ],
    });
    render(<Studio {...props} />);
    const thanh = q().getAllByRole("progressbar");
    assert.equal(thanh.length, 1, "phai co dung mot thanh chay");
    const now = Number(thanh[0].getAttribute("aria-valuenow"));
    assert.ok(Number.isFinite(now) && now > 0, `aria-valuenow phai la so duong, do duoc ${now}`);
    assert.ok(now <= 97, `tiLe khong duoc cham 100 khi job con chay, do duoc ${now}`);
  });

  it("job asr running NHUNG thieu started_at => KHONG ve thanh, khong bia so", () => {
    // Thanh dung yen la kieu noi doi te hon khong co thanh: no trong nhu dang chay ma
    // thuc ra khong biet gi.
    const { props } = dungThu({
      source: KENH,
      jobs: [
        job({ id: 301, type: "asr", state: "running", started_at: null, payload: { source_id: KENH.id } }),
      ],
    });
    render(<Studio {...props} />);
    assert.equal(q().queryAllByRole("progressbar").length, 0);
  });

  it("job translate running => KHONG ve thanh (dao dong qua rong de uoc luong)", () => {
    // Do duoc `translate` chay 4-57 s tren cung do dai video. Mot thanh chay sai nhip
    // te hon khong co thanh nao.
    const batDau = new Date(Date.now() - 10_000).toISOString();
    const { props } = dungThu({
      source: KENH,
      jobs: [
        job({ id: 302, type: "translate", state: "running", started_at: batDau, payload: {} }),
      ],
    });
    render(<Studio {...props} />);
    assert.equal(q().queryAllByRole("progressbar").length, 0);
  });
});


// 🔴 KY TU LA khong phai loi noi — do duoc tren translation #52.
//
// Quet TUNG KY TU cua 158 doan: dung MOT ky tu la trong toan bo, va no la logo
// 'ΛNI' (U+039B GREEK CAPITAL LETTER LAMDA) nam trong cau noi. No chiem mot o
// tren timeline va day cac khoi that xuong lan phu.
//
// Ba mien phai GIU: Han (chu goc Trung), ASCII (chu Viet khong dau + so), va
// Latinh mo rong (chu Viet CO DAU). Mien thu ba la bat buoc — mot luat 'chi cho
// ASCII' se xoa sach moi phu de tieng Viet.
it("bo khoi chi chua KY TU LA (logo) khoi TIMELINE, giu chu Viet co dau", async () => {
  // 🔴 Kiem tren TIMELINE, khong phai o nhap cua bang ben duoi.
  //
  // Ban dau toi viet `queryAllByDisplayValue("ΛNI")` va no DO voi `actual: 1` —
  // nhung do la o nhap trong bang, thu ma `laRac` KHONG dieu khien. Khoi tren
  // timeline moi la thu bi loc. Do lai cho dung doi tuong.
  const { props } = dungThu({
    transcript: banGhi([
      doan({ i: 0, start: 0, end: 1, text: "ΛNI" }),
      doan({ i: 1, start: 1, end: 2, text: "你会在山上看到" }),
    ]),
    banDich: banDichCua([
      doan({ i: 0, start: 0, end: 1, text: "ΛNI" }),
      doan({ i: 1, start: 1, end: 2, text: "Bạn sẽ thấy trên núi" }),
    ]),
  });
  const { container } = render(<Studio {...props} />);
  await waitFor(() => {
    assert.ok(q().queryAllByDisplayValue("Bạn sẽ thấy trên núi").length > 0,
      "chua nap xong: chua co o phu de nao");
  });
  // Khoi tren timeline la `div` co `title` chua khoang thoi gian.
  const tieuDe = [...container.querySelectorAll("div[title]")]
    .map((e) => e.getAttribute("title") || "");
  assert.ok(!tieuDe.some((x) => x.includes("ΛNI")),
    "logo ΛNI phai bi bo khoi timeline, do duoc: " + JSON.stringify(tieuDe.slice(0, 6)));
  assert.ok(tieuDe.some((x) => x.includes("Bạn sẽ thấy trên núi")),
    "chu Viet co dau phai CON tren timeline, do duoc: " + JSON.stringify(tieuDe.slice(0, 6)));
});
