/**
 * VÒNG THIẾT KẾ 1 — ghim "TẤM RỖNG" (`.rong`) va "TẤM LỖI" (`.tl`), cộng hai lỗi bố cục `L1`/`L2`.
 *
 * ## Vì sao tệp này tồn tại
 *
 * Năm trạng thái rỗng/lỗi của app trước vòng này mỗi chỗ là một `<p>` riêng, không có gì nói
 * chung, và **không chỗ nào nói cho người dùng biết LÀM GÌ TIẾP** — câu `CompareScreen` còn nói
 * ngược sự thật (*"Vùng KÊNH chưa có đường chọn bản ghi"*, SAI sau W1). Vòng này gom chúng vào
 * MỘT tiểu-ngôn-ngữ (`.rong`/`.tl`) và sửa câu sai. Tệp này ghim:
 *
 *   (1) **QUAN HỆ luật ↔ lớp, HAI CHIỀU** cho hai họ lớp mới (khuôn `.q*` của `QueueZone.test.tsx`
 *       và `W2 M4` của `ChannelZone.test.tsx`): xoá LUẬT mà giữ LỚP ⇒ ĐỎ; đổi TÊN LỚP mà giữ
 *       LUẬT ⇒ ĐỎ. Không ghim danh sách tên lớp nguyên văn (ERRATA #34 mục 1).
 *   (2) **BA TẦNG của một tấm rỗng** (kicker + MỘT câu mệnh lệnh + bóng ma trục thời gian) và
 *       **BA TẦNG của một tấm lỗi** (mã mono + nguyên nhân + câu NÓI RÕ CÁI GÌ CÒN CHẠY ĐƯỢC).
 *   (3) **CÂU SAI ở `CompareScreen` đã được sửa** — và câu SAI đó KHÔNG được quay lại.
 *   (4) `L1`/`L2`: **KHAI BÁO** trong `app.css` (vế jsdom làm được), ghép với vế CHROME THẬT ở
 *       `e2e/plans/rong-va-bo-cuc.json` — jsdom KHÔNG có layout, nên hình học thật (`top`,
 *       `height`, `scrollWidth`) chỉ đo được ở tầng kia. Hai vế, một mệnh đề.
 *
 * ## LUẬT DOM (ERRATA #9 mục 1/6): tệp này TỰ CHỨA
 *
 * Hook đặt/trả global nằm TRONG `describe()`; không đưa node DOM sống vào `assert` (ERRATA #14
 * mục 3); `console.error`/`console.warn` được trả lại trong `after`.
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { setupDom, teardownDom } from "../../test/dom.ts";

/** Các lớp `rong*` của cả họ — TÊN CHỈ DÙNG ĐỂ ĐỌC, không phải mệnh đề (xem bài (1)). */
const RONG_PREFIX = "rong";
const TL_PREFIX = "tl";

/**
 * MỌI khai báo của MỘT selector, khai báo SAU THẮNG (đúng luật CSS khi độ đặc hiệu bằng nhau).
 *
 * ⚠️ `RegExp(sel + "\\{[^}]*\\}")` chỉ đọc khối ĐẦU TIÊN khớp, nên một luật SAU ghi đè đi qua
 * XANH (ERRATA #42 mục 5). Vì vậy phải gom THEO TỪNG KHỐI rồi ghi đè theo thứ tự nguồn.
 */
function khaiBaoCua(css: string, chon: string): Map<string, string> {
  const ra = new Map<string, string>();
  for (const khoi of cacKhoi(css)) {
    if (!khoi.chon.split(",").some((s) => s.trim() === chon)) continue;
    for (const khai of khoi.than.split(";")) {
      const hai = khai.indexOf(":");
      if (hai < 0) continue;
      ra.set(khai.slice(0, hai).trim(), khai.slice(hai + 1).trim());
    }
  }
  return ra;
}

/** Tách `app.css` thành các khối `{chọn, thân}` — BỎ CHÚ THÍCH trước (một `}` trong chú thích cắt cụt). */
function cacKhoi(css: string): { chon: string; than: string }[] {
  const sach = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const ra: { chon: string; than: string }[] = [];
  for (const m of sach.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    ra.push({ chon: (m[1] ?? "").trim(), than: m[2] ?? "" });
  }
  return ra;
}

function mo(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined) return "undefined";
  if (value === null) return "null";
  const kind = typeof value;
  if (kind !== "object" && kind !== "function") return String(value);
  return Object.prototype.toString.call(value);
}

const consoleGoc = { error: console.error, warn: console.warn };
const tiengOn: string[] = [];

let render: (ui: unknown) => { container: HTMLElement; unmount: () => void };
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let KhungRong: (props: unknown) => unknown;
let TamLoi: (props: unknown) => unknown;
let maLoi: (message: string) => string;

let appCss = "";

/** Phần tử ĐẦU TIÊN khớp `chon` — trả NODE để đọc thuộc tính/lớp, KHÔNG bao giờ đưa vào `assert`. */
function phanTu(container: HTMLElement, chon: string): Element {
  const el = container.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el;
}

/** Tập lớp khớp một tiền tố, gom trên MỌI phần tử của cây. */
function lopTheo(container: HTMLElement, tienTo: string): Set<string> {
  const ra = new Set<string>();
  for (const el of container.querySelectorAll("*")) {
    for (const ten of el.classList) if (ten === tienTo || ten.startsWith(`${tienTo}__`)) ra.add(ten);
  }
  return ra;
}

/** Tập lớp mà `app.css` TẠO KIỂU cho một tiền tố (đọc từ SELECTOR, không phải từ TSX). */
function lopTrongCss(tienTo: string): Set<string> {
  const ra = new Set<string>();
  for (const khoi of cacKhoi(appCss)) {
    for (const m of khoi.chon.matchAll(new RegExp(`\\.(${tienTo}(?:__[a-z0-9-]+)?)`, "g"))) {
      ra.add(m[1] ?? "");
    }
  }
  ra.delete("");
  return ra;
}

function ve(ui: unknown): HTMLElement {
  return render(ui).container;
}

describe("VÒNG THIẾT KẾ 1: tấm rỗng + tấm lỗi, và hai lỗi bố cục L1/L2", () => {
  before(async () => {
    teardownDom();
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl : rtl.default;
    render = api.render;
    cleanup = api.cleanup;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;

    const ui: any = await import("./TrangRong.tsx");
    KhungRong = ui.KhungRong;
    TamLoi = ui.TamLoi;
    maLoi = ui.maLoi;

    appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");

    console.error = (...args: unknown[]): void => {
      tiengOn.push(`error: ${args.map(mo).join(" ")}`);
    };
    console.warn = (...args: unknown[]): void => {
      tiengOn.push(`warn: ${args.map(mo).join(" ")}`);
    };
  });

  beforeEach(() => {
    tiengOn.length = 0;
  });

  afterEach(() => {
    cleanup();
  });

  after(() => {
    console.error = consoleGoc.error;
    console.warn = consoleGoc.warn;
    teardownDom();
  });

  // -------------------------------------------------------------------------
  // (1) QUAN HỆ LUẬT ↔ LỚP, HAI CHIỀU — cho CẢ HAI họ lớp mới
  // -------------------------------------------------------------------------

  it("HÌNH THỨC: `.rong*` và `.tl*` của `app.css` và của DOM KHỚP NHAU (hai chiều)", () => {
    // Cây DOM gom từ MỌI nhánh của hai component — một tấm rỗng và một tấm lỗi cùng lúc, nên
    // mọi lớp của hai họ đều có mặt. Lớp nào KHÔNG gom được thì nó là luật mồ côi, và bài này đỏ.
    const container = ve(
      taoPhanTu("div", null, [
        taoPhanTu(KhungRong, { key: "a", kicker: "TRỐNG", lenh: "làm việc gì đó tiếp" }),
        taoPhanTu(TamLoi, {
          key: "b",
          kicker: "LỖI",
          lyDo: "502: Bad Gateway",
          con: "một câu nói rõ cái gì còn chạy được",
        }),
      ]),
    );

    for (const tienTo of [RONG_PREFIX, TL_PREFIX]) {
      const trongCss = lopTrongCss(tienTo);
      const trongDom = lopTheo(container, tienTo);
      assert.ok(trongCss.size >= 5, `phải đọc được các lớp \`${tienTo}*\` từ app.css; đo được ${trongCss.size}`);

      const moCoi = [...trongCss].filter((t) => !trongDom.has(t)).sort();
      assert.deepEqual(
        moCoi,
        [],
        `LUẬT MỒ CÔI: ${JSON.stringify(moCoi)} — luật này không lớp nào trong DOM mang, tức nó KHÔNG `
        + `tạo kiểu cho thứ gì. Lớp có trong DOM: ${JSON.stringify([...trongDom].sort())}`,
      );

      const voLuat = [...trongDom].filter((t) => !trongCss.has(t)).sort();
      assert.deepEqual(
        voLuat,
        [],
        `LỚP KHÔNG CÓ LUẬT: ${JSON.stringify(voLuat)} — lớp này nằm trong DOM mà app.css không tạo `
        + `kiểu cho nó. Luật có trong app.css: ${JSON.stringify([...trongCss].sort())}`,
      );
    }

    assert.deepEqual(tiengOn, [], "hai tấm không được sinh tiếng ồn console");
  });

  // -------------------------------------------------------------------------
  // (2) BA TẦNG của một tấm rỗng + BA TẦNG của một tấm lỗi
  // -------------------------------------------------------------------------

  it("TẤM RỖNG: kicker mono + MỘT câu mệnh lệnh + BÓNG MA trục thời gian DỌC (nét đứt, 3 rail)", () => {
    const container = ve(
      taoPhanTu(KhungRong, {
        kicker: "TRỐNG",
        lenh: "hàng đợi trống — nạp tệp hoặc bấm «dịch» để đẩy một việc vào đây",
      }),
    );

    assert.equal(
      (phanTu(container, ".rong__kicker").textContent ?? "").trim(),
      "TRỐNG",
      "tầng 1 phải là kicker, và nó phải là chữ của chỗ gọi",
    );

    // Tầng 2: MỘT câu, và nó là câu của chỗ gọi — không phải một câu chung chung do component bịa.
    const lenh = (phanTu(container, ".rong__lenh").textContent ?? "").trim();
    assert.match(lenh, /hàng đợi trống/);
    assert.equal(
      container.querySelectorAll(".rong__lenh").length,
      1,
      "ĐÚNG MỘT câu mệnh lệnh — hai câu là hai mệnh lệnh, và người đọc không biết câu nào là việc",
    );

    // Tầng 3: bóng ma. Ba rail mono + MỘT đường trục.
    assert.equal(container.querySelectorAll(".rong__ray").length, 3, "bóng ma phải có 3 rail (3 hàng sắp tới)");
    assert.equal(container.querySelectorAll(".rong__truc").length, 1, "bóng ma phải có ĐÚNG MỘT đường trục");
    for (const ray of container.querySelectorAll(".rong__ray")) {
      assert.equal(ray.textContent, "--:--.--", "rail phải là mốc CHƯA đo được, không phải một số bịa");
    }

    // PHẦN TRANG TRÍ không được đọc lên: trục và rail không mang thông tin nào mà câu chữ không có.
    assert.equal(
      phanTu(container, ".rong__ma").getAttribute("aria-hidden"),
      "true",
      "bóng ma là TRANG TRÍ ⇒ phải `aria-hidden`",
    );

    // KHAI BÁO: trục là NÉT ĐỨT và nó DỌC (`border-left`), không phải một đường ngang.
    const truc = khaiBaoCua(appCss, ".rong__truc");
    assert.match(truc.get("border-left") ?? "", /dashed/, "trục thời gian phải vẽ NÉT ĐỨT");
    assert.equal(truc.get("width"), undefined, "trục là một đường 1 px (`border-left`), không phải một khối có bề rộng");
    const ma = khaiBaoCua(appCss, ".rong__ma");
    assert.match(ma.get("min-height") ?? "", /--row-2/, "bóng ma cao BA hàng ⇒ chiều cao phải suy từ nhịp dọc `--row-2`");
    assert.match(ma.get("flex-direction") ?? "", /column/, "trục thời gian là DỌC ⇒ bóng ma xếp theo cột");

    assert.deepEqual(tiengOn, [], "tấm rỗng không được sinh tiếng ồn console");
  });

  it("TẤM LỖI: mã MONO + nguyên nhân NGUYÊN VĂN + câu NÓI RÕ CÁI GÌ CÒN CHẠY ĐƯỢC", () => {
    const container = ve(
      taoPhanTu(TamLoi, {
        kicker: "LỖI",
        ma: "502",
        lyDo: "502: Bad Gateway",
        con: "Nạp tệp vẫn chạy được: ô «nạp tệp» ở trên gửi thẳng lên máy chủ.",
        role: "alert",
        testid: "loi-thu",
      }),
    );

    assert.equal((phanTu(container, ".tl__ma").textContent ?? "").trim(), "502", "mã lỗi phải được TRÍCH ra thành một giá trị mono");
    assert.match(
      phanTu(container, ".tl__ly-do").textContent ?? "",
      /^502: Bad Gateway$/,
      "nguyên nhân phải là chuỗi NGUYÊN VĂN — không viết lại, không rút gọn",
    );
    assert.match(
      phanTu(container, ".tl__con").textContent ?? "",
      /vẫn chạy được/,
      "tấm lỗi phải nói rõ CÁI GÌ CÒN CHẠY ĐƯỢC (khuôn trung thực của panel §4.8)",
    );
    assert.equal(phanTu(container, "[data-testid=loi-thu]").getAttribute("role"), "alert", "`role` là PROP, không phải hằng số trong component");

    // KHAI BÁO: mã là MONO, và vân ở đỉnh là VÂN (`repeating-linear-gradient`), không phải nền đỏ.
    assert.match(khaiBaoCua(appCss, ".tl__ma").get("font-family") ?? "", /--font-mono/, "mã lỗi là giá trị của MÁY ⇒ mono");
    assert.match(
      khaiBaoCua(appCss, ".tl__van").get("background-image") ?? "",
      /repeating-linear-gradient/,
      "§2.2 quy tắc 3: `--fault` không bao giờ TÔ NỀN — nó là VÂN (cùng khuôn `.od__van`)",
    );
    assert.match(
      khaiBaoCua(appCss, ".tl__con").get("border-left") ?? "",
      /--signal/,
      "câu 'còn chạy được' là tin TỐT ⇒ lề amber, cùng khuôn `.od__sua` (§2.2 quy tắc 1)",
    );

    // MÃ KHÔNG ĐOÁN: một chuỗi không có mã HTTP thì trả `LỖI`, không bịa một con số.
    const khongMa = ve(taoPhanTu(TamLoi, { kicker: "LỖI", ma: maLoi("Failed to fetch"), lyDo: "Failed to fetch", con: "x" }));
    assert.equal((phanTu(khongMa, ".tl__ma").textContent ?? "").trim(), "LỖI", "không có mã thì phải nói `LỖI`, không bịa số");

    // 🔴 VÀ MÃ KHÔNG ĐƯỢC ĐOÁN TỪ CÂU ĐÃ GÓI. Đo được một lần khi gói trước: chỗ gọi truyền
    // `maLoi(\`không đọc được kênh: ${error}\`)` — câu đã gói KHÔNG bắt đầu bằng ba chữ số, nên
    // hàm trả `"LỖI"` và tấm lỗi in `LỖI` HAI LẦN (kicker + mã). `ma` là PROP chính vì thế: chỗ
    // gọi là nơi DUY NHẤT còn giữ chuỗi THÔ.
    const goi = ve(
      taoPhanTu(TamLoi, {
        kicker: "LỖI",
        ma: maLoi("502: Bad Gateway"),
        lyDo: "không đọc được kênh: 502: Bad Gateway",
        con: "x",
      }),
    );
    assert.equal((phanTu(goi, ".tl__ma").textContent ?? "").trim(), "502", "mã phải trích từ chuỗi THÔ, không từ câu đã gói");
    assert.notEqual(
      (phanTu(goi, ".tl__kicker").textContent ?? "").trim(),
      (phanTu(goi, ".tl__ma").textContent ?? "").trim(),
      "kicker và mã KHÔNG được trùng chữ — `LỖI` hai lần là một lỗi đã đo được",
    );
    assert.match(phanTu(goi, ".tl__ly-do").textContent ?? "", /không đọc được kênh: 502: Bad Gateway/, "câu nguyên văn vẫn nguyên vẹn");

    assert.deepEqual(tiengOn, [], "tấm lỗi không được sinh tiếng ồn console");
  });

  // -------------------------------------------------------------------------
  // (3) CÂU SAI ở CompareScreen — đã sửa, và phải Ở YÊN như thế
  // -------------------------------------------------------------------------

  it("CompareScreen: câu SAI sau W1 ('Vùng KÊNH chưa có đường chọn bản ghi') KHÔNG được quay lại", async () => {
    const man: any = await import("../screens/CompareScreen.tsx");
    const container = ve(taoPhanTu(man.CompareScreen, { transcript: null, translations: [] }));

    const chu = phanTu(container, '[data-testid="rong"]').textContent ?? "";
    // VẾ ÂM: mệnh đề SAI. W1 đã nối `selectChannel` vào từng mục kênh
    // (`ChannelZone.tsx`), nên "chưa có đường chọn" là một lời nói ngược sự thật.
    assert.ok(
      !chu.includes("chưa có đường chọn"),
      `câu cũ nói ngược sự thật (kênh CHỌN ĐƯỢC rồi) và không được quay lại; đo được ${JSON.stringify(chu)}`,
    );
    // VẾ DƯƠNG: sự thật còn lại — CHƯA CHỌN — và MỘT mệnh lệnh nói chọn ở đâu.
    assert.match(chu, /Chưa chọn kênh/, "phải nói ra sự thật của lượt này: CHƯA chọn kênh");
    assert.match(chu, /bấm một kênh ở vùng KÊNH/, "và phải nói người dùng LÀM GÌ TIẾP, không chỉ mô tả trạng thái");

    assert.deepEqual(tiengOn, [], "trạng thái rỗng của Đối chiếu không được sinh tiếng ồn console");
  });

  // -------------------------------------------------------------------------
  // (4) NĂM CHỖ DÙNG: giữ NGUYÊN tên lớp cũ, và tên đó PHẢI còn luật
  // -------------------------------------------------------------------------

  it("NĂM chỗ dùng giữ nguyên lớp cũ, và mỗi lớp cũ vẫn có LUẬT trong app.css", () => {
    // Đây là vế "KHAI BÁO" của luật ghim: đổi tên lớp ở TSX mà giữ luật ⇒ luật thành mồ côi; xoá
    // luật mà giữ lớp ⇒ lớp không còn được tạo kiểu. Hai vế đó được hai bài (1) và bài này ghim.
    for (const ten of ["ed__rong", "q__rong", "cmp__rong", "ch__loi", "gl__loi"]) {
      // `.ch__loi` là NỢ đã khai (`NO_CHUA_CO_LUAT` của `ChannelZone.test.tsx`): nó KHÔNG có luật
      // riêng, và hình dạng của nó đến từ `.tl`. Nên vế "có luật" chỉ áp cho bốn lớp kia.
      if (ten === "ch__loi") continue;
      assert.ok(
        khaiBaoCua(appCss, `.${ten}`).size > 0,
        `\`.${ten}\` phải còn LUẬT trong app.css — đó là chỗ neo của bài ghim QUAN HỆ`,
      );
    }
    // `.tl` cung cấp hình dạng cho `.ch__loi`, nên nợ đó KHÔNG còn là "không có hình dạng nào".
    assert.ok(khaiBaoCua(appCss, ".tl").size > 0, "`.ch__loi` mượn hình dạng của `.tl` ⇒ `.tl` phải có luật");
    // `.tl` KHÔNG được khai lưới track cố định: thêm một con (ví dụ nút thử lại) là tái sinh
    // ERRATA #31 mục 1 ở đúng chỗ dễ sai nhất (`.shell`/`.cmp` đã sai THẬT hai lần).
    for (const ten of ["rong", "tl"]) {
      assert.equal(khaiBaoCua(appCss, `.${ten}`).get("grid-template-rows"), undefined, `\`.${ten}\` không được khai lưới track cố định`);
      assert.equal(khaiBaoCua(appCss, `.${ten}`).get("grid-template-columns"), undefined, `\`.${ten}\` không được khai lưới track cố định`);
      assert.equal(khaiBaoCua(appCss, `.${ten}`).get("display"), "flex", `\`.${ten}\` phải là flex (thêm con không thể 'cướp chỗ')`);
    }
  });

  // -------------------------------------------------------------------------
  // (5) L1 / L2 — vế KHAI BÁO (vế HÌNH HỌC ở tầng Chrome thật)
  // -------------------------------------------------------------------------

  it("L1 KHAI BÁO: nhãn TRÊN ô nhập, ba điều khiển cùng MỘT băng chiều cao, ô kiểm căn giữa băng", () => {
    // Nhãn nằm TRÊN ô nhập: `.gl__o--duyet` phải là CỘT (bản cũ là HÀNG ⇒ cao 14,25 px và bị
    // `align-items: end` của `.gl__form` đẩy lệch 14 px so với ô nhập — đo trong Chrome thật).
    assert.equal(
      khaiBaoCua(appCss, ".gl__o--duyet").get("flex-direction"),
      "column",
      "`L1`: nhãn `Đã duyệt` phải nằm TRÊN ô, không nằm cạnh — nếu không nó không cùng trục với bốn ô kia",
    );
    // Ba điều khiển CÙNG một băng: cùng một KHAI BÁO (`--row-1`), không phải ba con số trùng nhau
    // một cách tình cờ (chiều cao ô nhập đến từ số liệu font ⇒ trôi theo font/máy).
    assert.match(
      khaiBaoCua(appCss, ".gl__nhap").get("height") ?? "",
      /--row-1/,
      "`L1`: ô nhập phải khai băng chiều cao CÓ TÊN",
    );
    assert.match(khaiBaoCua(appCss, ".gl__luu").get("height") ?? "", /--row-1/, "`L1`: nút `Lưu thuật ngữ` cùng băng với ô nhập");
    assert.match(khaiBaoCua(appCss, ".gl__duyet").get("height") ?? "", /--row-1/, "`L1`: ô kiểm cùng băng với ô nhập");
    // `align-items: center` — điều khiển nằm GIỮA băng của nó (ô kiểm 13 px trong băng 32 px).
    assert.equal(
      khaiBaoCua(appCss, ".gl__duyet-bang").get("align-items"),
      "center",
      "`L1`: điều khiển trong hàng phải `align-items: center`",
    );
    assert.match(
      khaiBaoCua(appCss, ".gl__duyet-bang").get("height") ?? "",
      /--row-1/,
      "`L1`: băng của ô kiểm phải cao ĐÚNG bằng băng của ô nhập",
    );
  });

  it("L2 KHAI BÁO: ô chọn tệp của trình duyệt KHÔNG còn được vẽ, điều khiển là nút THẬT của app", () => {
    // 🔴 ĐO ĐƯỢC (Chrome thật, 2003/2560/1280 px): KHÔNG có `scrollWidth > clientWidth` ở bất kỳ
    // cấp nào — cách sửa mà brief §2 đề nghị (`min-width: 0` + `flex-wrap` + truncate) KHÔNG với
    // tới được cái tràn THẬT, vì cái tràn đó nằm trong phần do TRÌNH DUYỆT vẽ (widget file có bề
    // rộng nội tại cố định 212 px / 192 px, `text-overflow` không áp cho nội dung UA vẽ).
    // ⇒ Ghim KHAI BÁO: ô thật bị che PHẦN VẼ (1×1 + `clip-path`), nên nội dung của nó không còn
    // do UA vẽ nữa.
    const o = khaiBaoCua(appCss, ".nap__o-tep");
    assert.equal(o.get("position"), "absolute", "`L2`: ô thật phải ra khỏi luồng (không chiếm bề rộng nội tại)");
    assert.equal(o.get("width"), "1px", "`L2`: ô thật còn 1×1");
    assert.match(o.get("clip-path") ?? "", /inset\(50%\)/, "`L2`: phần VẼ của ô thật bị cắt hẳn");
    // ⚠️ KHÔNG được `display: none` / `visibility: hidden`: cả hai đưa ô ra khỏi cây tiêu điểm và
    // khỏi trình đọc màn hình ⇒ bàn phím mất đường chọn tệp. Đây là vế ÂM của cùng một mệnh đề.
    assert.equal(o.get("display"), undefined, "`L2`: KHÔNG được `display: none` (mất đường bàn phím)");
    assert.equal(o.get("visibility"), undefined, "`L2`: KHÔNG được `visibility: hidden` (mất đường trình đọc màn hình)");
    assert.notEqual(o.get("opacity"), "0", "`L2`: KHÔNG `opacity: 0` (vòng tiêu điểm sẽ vô hình)");

    // Vòng tiêu điểm của ô thật được VẼ LÊN CHÍNH NÚT — nên thứ tự DOM (`input` rồi `label`) là
    // một phần của mệnh đề, không phải một chi tiết trình bày.
    const khop = cacKhoi(appCss).some(
      (k) => k.chon.includes(".nap__o-tep:focus-visible + .nap__nut-tep"),
    );
    assert.ok(khop, "`L2`: phải có luật vẽ vòng tiêu điểm của ô thật lên nút (`+` = nút NGAY SAU ô trong DOM)");

    // Điều khiển là NÚT THẬT của app: mặt nhãn khắc + đường kẻ 1 px (không phải widget hệ thống).
    const nut = khaiBaoCua(appCss, ".nap__nut-tep");
    assert.match(nut.get("font-family") ?? "", /--font-label/, "`L2`: nút chọn tệp phải dùng mặt nhãn khắc của app");
    assert.match(nut.get("border") ?? "", /--rule/, "`L2`: nút phải theo khuôn đường kẻ 1 px (§2.3), không phải nút hệ thống");

    // Tên tệp TỰ CẮT được — và nó chỉ là bản TÓM TẮT: câu đầy đủ ở `.nap__chon-tam` không bị cắt.
    const ten = khaiBaoCua(appCss, ".nap__ten-tep");
    assert.equal(ten.get("min-width"), "0", "`L2`: flex con phải có `min-width: 0`, nếu không nó không co được");
    assert.equal(ten.get("text-overflow"), "ellipsis", "`L2`: tên tệp phải ellipsize");
    assert.equal(ten.get("white-space"), "nowrap", "`L2`: tên tệp phải trên MỘT dòng thì ellipsis mới có nghĩa");
    assert.equal(ten.get("overflow"), "hidden", "`L2`: phải `overflow: hidden` thì mới cắt");
    assert.equal(
      khaiBaoCua(appCss, ".nap__chon-tam").get("white-space"),
      undefined,
      "`L2`: câu ĐẦY ĐỦ dưới hàng KHÔNG được `nowrap` — nó phải xuống dòng được (nó là bản không cắt)",
    );

    // Hàng chứa nút phải cho phép co: `min-width: 0` trên flex con của nó.
    assert.equal(khaiBaoCua(appCss, ".nap__chon-tep").get("min-width"), "0", "`L2`: nhóm chọn tệp phải co được");
  });

  it("L2: hai lối nạp cùng một hình dạng — lối gọn cũng bỏ widget của trình duyệt", () => {
    // MỘT luật, HAI lối vào (điểm thiết kế chính của §4.2). Nếu chỉ sửa khung giữa thì lối gọn ở
    // cột KÊNH 213 px vẫn còn widget 192 px bị UA cắt chữ — đúng cái người dùng chụp ảnh.
    const g = khaiBaoCua(appCss, ".ch__nap-o");
    assert.equal(g.get("position"), "absolute", "`L2`: lối GỌN cũng phải bỏ phần vẽ của widget");
    assert.match(g.get("clip-path") ?? "", /inset\(50%\)/);
    assert.match(
      khaiBaoCua(appCss, ".ch__nap-nut").get("font-family") ?? "",
      /--font-label/,
      "`L2`: nút của lối gọn cũng là nút THẬT của app",
    );
    assert.equal(
      khaiBaoCua(appCss, ".ch__nap-tep").get("min-width"),
      "0",
      "`L2`: nhóm chọn tệp của lối gọn phải co được trong cột 213 px",
    );
  });

  it("PHẢN HỒI XÚC GIÁC: mọi lệnh có `:active`, và nó chỉ nhích `transform`", () => {
    // Brief §4: `:active` phải có phản hồi xúc giác, và chỉ `transform`/`opacity` được animate.
    const khoi = cacKhoi(appCss).filter((k) => /\.(lenh|nap__nut|gl__luu|od__thu-lai):active/.test(k.chon));
    assert.ok(khoi.length > 0, "phải có ít nhất một luật `:active` cho các lệnh");
    const than = khoi.map((k) => k.than).join("\n");
    assert.match(than, /transform:\s*translateY\(1px\)/, "phản hồi xúc giác là một cú nhích 1 px");
    assert.ok(
      !/transition[^;]*\b(width|height|top|left)\b/.test(than),
      "KHÔNG được animate `top`/`left`/`width`/`height` (brief §4)",
    );

    // Và chuyển động VÀO chỉ chạy MỘT lần, chỉ `transform`/`opacity`.
    // ⚠️ Không đọc `@keyframes` bằng `cacKhoi`: nó cắt khối theo `[^{}]*`, mà `@keyframes` LỒNG
    // `from`/`to` — nên khối cha không bao giờ khớp và phép đếm ra 0 (đo được ở lượt chạy đầu).
    // Đọc thẳng trên văn bản ĐÃ BỎ CHÚ THÍCH, và dừng ở `}` ĐẦU TIÊN đứng ở đầu dòng (khối cha).
    const sachCss = appCss.replace(/\/\*[\s\S]*?\*\//g, "");
    const kf = /@keyframes vao-mot-lan\s*\{([\s\S]*?)\n\}/.exec(sachCss);
    assert.ok(kf !== null, "phải có chuyển động vào `vao-mot-lan`");
    const thanKf = kf[1] ?? "";
    assert.match(thanKf, /opacity/, "chuyển động vào dùng `opacity`");
    assert.match(thanKf, /transform/, "chuyển động vào dùng `transform`");
    assert.ok(
      !/\b(top|left|width|height)\s*:/.test(thanKf),
      `chuyển động vào KHÔNG được animate \`top\`/\`left\`/\`width\`/\`height\` (brief §4); đo được ${JSON.stringify(thanKf)}`,
    );
    for (const ten of ["rong", "tl"]) {
      // ⚠️ KHÔNG dùng `khaiBaoCua` ở đây: nó trả khai báo SAU CÙNG, và khối CUỐI của `.rong`/`.tl`
      // là khối `@media (prefers-reduced-motion: reduce) { … animation: none }` — đúng về hành vi,
      // nhưng nó che mất khai báo chuyển động. Nên đọc MỌI khối của selector này.
      const than = cacKhoi(appCss)
        .filter((k) => k.chon.split(",").some((s) => s.trim() === `.${ten}`))
        .map((k) => k.than)
        .join("\n");
      assert.match(than, /vao-mot-lan/, `\`.${ten}\` dùng CHÍNH chuyển động vào dùng chung (không phải một bản sao thứ hai)`);
      assert.match(than, /var\(--dur-vao\)/, `\`.${ten}\` vào bằng chuyển động MỘT lần CÓ TÊN (\`--dur-vao\`), không phải một hằng số chép tay`);
      assert.match(than, /animation:\s*none/, `\`.${ten}\` phải TẮT chuyển động khi người dùng xin \`prefers-reduced-motion\``);
    }
  });
});
