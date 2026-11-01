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
  return { start: 0, end: 1, text: "", suspect: false, ...p };
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
