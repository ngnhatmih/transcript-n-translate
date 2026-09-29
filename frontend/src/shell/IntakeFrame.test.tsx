/**
 * Test `<IntakeFrame/>` + `<NhapGon/>` THAT trong jsdom — **CỬA VÀO CỦA WORKSPACE 1** (§4.2).
 *
 * ## Vì sao tệp này tồn tại
 *
 * ĐO ĐƯỢC TRƯỚC W2: `endpoints.uploadSource` **0 lượt gọi trong sản phẩm**, và trong
 * `frontend/src` **không có** `type="file"`, **không có** `onDrop`/`dataTransfer` ⇒ workspace 1
 * (audio → text) không có cửa vào. Tệp này ghim HÌNH DÁNG của cửa đó và HAI luật dễ mất nhất:
 * `onDragOver` **phải** `preventDefault` (thiếu thì trình duyệt MỞ tệp), và kết quả TỪNG tệp phải
 * hiện **bằng CHỮ** (kể cả câu lỗi nguyên văn của backend).
 *
 * ## Ranh giới của phép đo — nói đúng mức
 *
 * `napTep` ở đây là một hàm ĐƯỢC TIÊM (chính cái seam mà brief W2 định nghĩa:
 * `napTep(files, lang) → Promise<KetQuaNap[]>`). Nó **KHÔNG** phải mock `endpoints.ts`/`client.ts`
 * (hai tệp đó không bị chạm) và **KHÔNG** phải `fetch` giả: đường HTTP THẬT — multipart thật,
 * `lang` tới dưới dạng trường FORM, câu 422 nguyên văn của backend — nằm ở `src/shell/App.test.tsx`
 * (server `node:http` thật trong tiến trình, `fetch` thật).
 *
 * ⚠️ jsdom KHÔNG phải trình duyệt: nó không có layout/CSS thật, nên "khung kẻ nét đứt" ở đây chỉ
 * được chứng minh bằng **VĂN BẢN LUẬT CSS** + quan hệ luật↔class, KHÔNG phải bằng mắt.
 *
 * LUAT DOM (ERRATA #9 muc 1/6): tep nay TU CHUA; hook dat/tra global nam TRONG `describe()`;
 * `console.error`/`console.warn` duoc tra lai trong `after`; KHONG dua node DOM song vao `assert`
 * (ERRATA #14 muc 3 — mot node React trong `assert` tung lam runner chay 218 697 ms roi OOM).
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import type { SourceLang } from "../api/types.ts";
import type { KetQuaNap, NapTep } from "./IntakeFrame.tsx";
import { setupDom, teardownDom } from "../../test/dom.ts";

/** Mo ta mot gia tri ma KHONG goi sau vao no (an toan voi node DOM da bi close). */
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
let waitFor: (cb: () => void, options?: { timeout?: number; interval?: number }) => Promise<void>;
let fireEvent: {
  change: (el: Element, init: unknown) => void;
  click: (el: Element) => void;
  dragOver: (el: Element, init?: unknown) => boolean;
  drop: (el: Element, init?: unknown) => boolean;
};
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let IntakeFrame: (props: unknown) => unknown;
let NhapGon: (props: unknown) => unknown;

/** Phan tu DAU TIEN khop `chon` — tra ve NODE de doc thuoc tinh/bam (khong bao gio vao `assert`). */
function phanTu(container: HTMLElement, chon: string): Element {
  const el = container.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el;
}

/** `textContent` cua MOI phan tu khop `chon` — khang dinh phai GAN DUNG doi tuong. */
function textCua(container: HTMLElement, chon: string): string[] {
  return [...container.querySelectorAll(chon)].map((el) => el.textContent ?? "");
}

/**
 * Cho tới khi một phần tử khớp `chon` thỏa `khop` — **TÍN HIỆU**, không phải đồng hồ.
 *
 * ⚠️ Và tín hiệu phải là **ĐÚNG thứ bài sắp ĐỌC** (ERRATA #38 mục 2 / #39 mục 5): ở đây mọi phép
 * chờ đọc chính `.nap__kq` — dòng kết quả mà khẳng định ngay sau đó đọc.
 */
async function choKetQua(container: HTMLElement, khop: RegExp): Promise<string> {
  let cuoi = "";
  await waitFor(
    () => {
      const dong = textCua(container, ".nap__kq");
      const thay = dong.find((t) => khop.test(t));
      assert.ok(thay !== undefined, `chua thay dong ket qua ${khop}; do duoc ${JSON.stringify(dong)}`);
      cuoi = thay;
    },
    { timeout: 5000, interval: 20 },
  );
  return cuoi;
}

/**
 * Cho tới khi có ĐÚNG `soLuong` phần tử khớp `chon` — tín hiệu của một TRẠNG THÁI.
 *
 * ⚠️ Khai riêng (không dùng `choKetQua`) vì đây là phép chờ cho một trạng thái, không phải cho một
 * dòng kết quả; và nó chờ ĐÚNG thứ bài (G) sắp đọc — không theo đồng hồ (ERRATA #35 mục 1/2).
 */
async function choCoLop(container: HTMLElement, chon: string, soLuong: number): Promise<void> {
  await waitFor(
    () => {
      assert.equal(
        container.querySelectorAll(chon).length,
        soLuong,
        `chua thay ${soLuong} phan tu "${chon}"`,
      );
    },
    { timeout: 5000, interval: 20 },
  );
}

/** Một lời gọi `napTep` đã được ghi lại — BẰNG CHỨNG ĐƯỜNG THẬT của seam. */
interface LanGoi {
  ten: readonly string[];
  lang: SourceLang;
}

/**
 * Hàm nạp TIÊM: ghi lại lời gọi rồi trả kết quả ĐÃ ĐỊNH. Xem "Ranh giới của phép đo" ở đầu tệp.
 */
function napTepGhi(goi: LanGoi[], ketQua: (files: readonly File[]) => KetQuaNap[]): NapTep {
  return async (files, lang) => {
    goi.push({ ten: files.map((t) => t.name), lang });
    return ketQua(files);
  };
}

/**
 * Một promise KHÔNG BAO GIỜ trả — để đo được TRẠNG THÁI "đang nạp…".
 *
 * ⚠️ Cố ý không có đường "thả": nếu thả, `setState` rơi vào một microtask NGOÀI `act` và React in
 * `not wrapped in act(...)` — đúng lớp lỗi đã làm nhiễu bộ đo ở `GlossaryScreen` (ERRATA #38 mục 3).
 * Một promise treo không bao giờ reject nên cũng không sinh unhandled rejection.
 */
function treo(): Promise<KetQuaNap[]> {
  return new Promise<KetQuaNap[]>(() => {});
}

/** Tệp THẬT của jsdom/Node — không phải một object giả hình dạng tệp. */
function tep(ten: string, byte: number[] = [1, 2, 3], type = "audio/wav"): File {
  return new File([new Uint8Array(byte)], ten, { type });
}

/** Cac khoi luat cua `app.css` (da bo chu thich) — doc VAN BAN, khong hoi jsdom (no khong co CSS). */
function cacKhoi(css: string): { chon: string; than: string }[] {
  const sach = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const ra: { chon: string; than: string }[] = [];
  for (const m of sach.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    ra.push({ chon: (m[1] ?? "").trim(), than: m[2] ?? "" });
  }
  return ra;
}

/** Than cua MOI luat ap cho mot lop — theo TUNG selector trong danh sach selector. */
function thanCua(khoi: { chon: string; than: string }[], lop: string): string {
  return khoi
    .filter((k) => k.chon.split(",").some((s) => s.trim().split(/\s+/).includes(`.${lop}`)))
    .map((k) => k.than)
    .join("\n");
}

/** Tap lop `nap*`/`ch__nap*` ma `app.css` TAO KIEU. */
function lopTrongCss(khoi: { chon: string; than: string }[]): Set<string> {
  const ra = new Set<string>();
  for (const k of khoi) {
    for (const lop of k.chon.matchAll(/\.((?:ch__)?nap[a-z0-9_-]*)/g)) ra.add(lop[1] ?? "");
  }
  ra.delete("");
  return ra;
}

describe("IntakeFrame + NhapGon: §4.2 cua vao NAP TEP (khung net dut + ket qua TUNG tep)", () => {
  before(async () => {
    // Chuan hoa TRUOC khi cai: khong dua vao viec tep khac da tra global hay chua.
    teardownDom();
    // Origin chi de `fetch` tuong doi resolve duoc; tep nay KHONG goi mang nao.
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    waitFor = api.waitFor;
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const man: any = await import("./IntakeFrame.tsx");
    IntakeFrame = man.IntakeFrame;
    NhapGon = man.NhapGon;

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

  it("A) KHUNG §4.2: KÉO TỆP VÀO ĐÂY (nhãn khắc) + dòng mono định dạng, và dòng mono NÓI RÕ nó là gợi ý", () => {
    const { container, unmount } = render(taoPhanTu(IntakeFrame, { napTep: napTepGhi([], () => []) }));

    // Khung net dut: lop `nap__khung` la HINH THUC cua §4.2; luat CSS cua no duoc ghim o bai (G).
    const khung = phanTu(container, ".nap__khung");
    const chu = khung.textContent ?? "";
    assert.match(chu, /KÉO TỆP VÀO ĐÂY/, `khung phai mang chu cua §4.2; do duoc ${JSON.stringify(chu)}`);

    // Dong mono: THONG TIN. No phai noi duoc dinh dang nao duong ong doc duoc...
    const dinhDang = textCua(container, ".nap__dinh-dang").join("");
    assert.match(dinhDang, /wav/, "dong mono phai liet ke dinh dang nhan duoc");
    assert.match(dinhDang, /mp4/, "dong mono phai liet ke ca dinh dang video (ffmpeg doc duoc)");
    // ... VA phai trung thuc ve viec backend KHONG chan duoi nao (khong phai mot loi hua).
    // Do la su that doc tu `backend/app/api/routes_sources.py`: `_safe_name` chi giu `suffix`.
    assert.match(
      dinhDang,
      /backend không chặn đuôi nào/,
      `dong mono phai noi ro no la GOI Y, khong phai phep kiem; do duoc ${JSON.stringify(dinhDang)}`,
    );

    assert.deepEqual(tiengOn, [], "khung rong khong duoc sinh tieng on console");
    unmount();
  });

  it("B) Ô CHỌN TỆP: `type=file` + `multiple` (§12.2), KHÔNG `accept` (client khong duoc chan tep), nut `nap` mo khoa khi da chon", () => {
    const { container, unmount } = render(taoPhanTu(IntakeFrame, { napTep: napTepGhi([], () => []) }));

    const o = phanTu(container, '[data-testid="nap-o-tep"]') as HTMLInputElement;
    assert.equal(o.getAttribute("type"), "file");
    // §12.2: "nap 3 tep cung luc" ⇒ thieu `multiple` la khong nap duoc qua mot lan chon.
    assert.ok(o.hasAttribute("multiple"), "o chon tep PHAI co `multiple` (§12.2)");
    // ⚠️ KHONG `accept`: keo-tha BO QUA `accept`, nen no khong phai phep kiem — va backend khong
    // chan duoi nao, nen mot bo loc o client la NGUON SU THAT THU HAI (mat tep ma backend van
    // nhan). Bai nay ghim su VANG MAT do.
    assert.equal(o.getAttribute("accept"), null, "KHONG duoc loc dinh dang o client (`accept`)");

    const nut = phanTu(container, '[data-testid="nap-nut"]') as HTMLButtonElement;
    assert.equal(nut.disabled, true, "chua chon tep nao ⇒ nut `nap` phai VO HIEU");
    assert.match(
      container.textContent ?? "",
      /chưa chọn tệp nào/,
      "trang thai 'chua chon tep' phai duoc NOI RA bang chu (khong chi la nut mo di)",
    );

    fireEvent.change(o, { target: { files: [tep("a.wav"), tep("b.wav")] } });
    assert.equal(nut.disabled, false, "da chon tep ⇒ nut `nap` phai mo khoa");
    assert.match(container.textContent ?? "", /đã chọn 2 tệp/, "so tep da chon phai hien bang CHU");

    assert.deepEqual(tiengOn, [], "chon tep khong duoc sinh tieng on console");
    unmount();
  });

  it("C) NGÔN NGỮ: CHỈ `zh`/`en` (dung `ALLOWED_LANGS` cua backend), va mot gia tri LA khong di vao lan nap", async () => {
    const goi: LanGoi[] = [];
    const napTep = napTepGhi(goi, (files) => [
      { ten: files[0]?.name ?? "", ok: true, sourceId: 9 },
    ]);
    const { container, unmount } = render(taoPhanTu(IntakeFrame, { napTep }));

    const chon = phanTu(container, '[data-testid="nap-tep-lang"]') as HTMLSelectElement;
    assert.deepEqual(
      [...chon.options].map((o) => o.value),
      ["zh", "en"],
      "o chon ngon ngu CHI duoc co zh/en (backend tra 422 voi moi gia tri khac)",
    );

    // Mot gia tri LA (khong den tu danh sach `option`) KHONG duoc di vao request: backend se tra
    // 422, nhung cai phai dung o day la client khong bao gio GUI mot ngon ngu ngoai `ALLOWED_LANGS`.
    fireEvent.change(chon, { target: { value: "ja" } });
    fireEvent.change(phanTu(container, '[data-testid="nap-o-tep"]'), {
      target: { files: [tep("a.wav")] },
    });
    fireEvent.click(phanTu(container, '[data-testid="nap-nut"]'));
    // ⚠️ Cho DUNG tin hieu ma bai sap doc: dong ket qua = luot nap DA XONG (state da commit, nen
    // nut `nap` da mo khoa cho luot sau). Cho theo `goi.length` khong bao dam state da ve.
    await choKetQua(container, /a\.wav: đã nạp — kênh 9/);
    assert.equal(goi.length, 1, "mot lan bam = MOT loi goi nap");
    assert.equal(goi[0]?.lang, "zh", "gia tri la `ja` KHONG duoc thanh ngon ngu cua lan nap");

    // Va gia tri THAT SU chon duoc thi phai di theo: `en`.
    fireEvent.change(chon, { target: { value: "en" } });
    fireEvent.click(phanTu(container, '[data-testid="nap-nut"]'));
    await waitFor(() => assert.equal(goi.length, 2), { timeout: 5000, interval: 20 });
    assert.equal(goi[1]?.lang, "en", "ngon ngu nguoi dung chon phai di theo lan nap");

    assert.deepEqual(tiengOn, [], "chon ngon ngu khong duoc sinh tieng on console");
    unmount();
  });

  it("D) BẤM `nạp`: gọi hàm nạp dùng chung với ĐÚNG tệp + ngôn ngữ, và hiện kết quả TỪNG TỆP bằng CHỮ (kể cả câu lỗi NGUYÊN VĂN)", async () => {
    // Câu lỗi dưới đây là NGUYÊN VĂN của backend cho tệp rỗng:
    // `backend/app/api/routes_sources.py::upload` ⇒ `HTTPException(422, "tệp rỗng")`, và
    // `client.ts` biến nó thành `ApiError.message = "422: tệp rỗng"`.
    const goi: LanGoi[] = [];
    const napTep = napTepGhi(goi, (files) => [
      { ten: files[0]?.name ?? "", ok: true, sourceId: 7 },
      { ten: files[1]?.name ?? "", ok: false, loi: "422: tệp rỗng" },
    ]);
    const { container, unmount } = render(taoPhanTu(IntakeFrame, { napTep }));

    fireEvent.change(phanTu(container, '[data-testid="nap-o-tep"]'), {
      target: { files: [tep("a.wav", [1, 2, 3]), tep("rong.wav", [])] },
    });
    fireEvent.click(phanTu(container, '[data-testid="nap-nut"]'));

    // MỘT lời gọi cho MỘT lần bấm, mang ĐÚNG hai tệp theo thứ tự người dùng đưa vào.
    await waitFor(() => assert.equal(goi.length, 1), { timeout: 5000, interval: 20 });
    assert.deepEqual(goi[0]?.ten, ["a.wav", "rong.wav"], "thu tu tep phai duoc giu");
    assert.equal(goi[0]?.lang, "zh", "ngon ngu mac dinh = `DEFAULT_LANG` cua backend (`zh`)");

    // KET QUA TUNG TEP, bang CHU: mot tep vao duoc (kem id KENH), mot tep bi tu choi (kem cau loi).
    await choKetQua(container, /a\.wav: đã nạp — kênh 7/);
    const loi = await choKetQua(container, /rong\.wav: LỖI/);
    assert.match(loi, /422: tệp rỗng/, "cau loi cua backend phai hien NGUYEN VAN");

    assert.deepEqual(tiengOn, [], "nap tep khong duoc sinh tieng on console");
    unmount();
  });

  it("E) KÉO-THẢ: `onDragOver` PHẢI `preventDefault` (thieu ⇒ trinh duyet MO tep), va `onDrop` doc `dataTransfer.files`", async () => {
    const goi: LanGoi[] = [];
    const napTep = napTepGhi(goi, (files) =>
      files.map((t) => ({ ten: t.name, ok: true, sourceId: 3 })),
    );
    const { container, unmount } = render(taoPhanTu(IntakeFrame, { napTep }));
    const khung = phanTu(container, '[data-testid="nap-khung-keo"]');

    // (1) `defaultPrevented` — doc tu CHINH su kien. Listener nay nam tren container (root cua
    // React), tuc chay SAU handler uy nhiem cua React, nen no thay dung gia tri cuoi cung.
    // ⚠️ Do bang TIN HIEU, khong bang "da goi ham": jsdom khong co dieu huong de ma do hau qua.
    let daChan: boolean | null = null;
    container.addEventListener("dragover", (s: Event) => {
      daChan = s.defaultPrevented;
    });
    const traVe = fireEvent.dragOver(khung, { dataTransfer: { files: [tep("a.wav")] } });
    assert.equal(
      daChan,
      true,
      "`onDragOver` PHAI goi `preventDefault` — thieu dong do thi trinh duyet MO tep thay vi cho tha",
    );
    assert.equal(traVe, false, "su kien `dragover` phai bi HUY mac dinh (gia tri dispatchEvent tra ve)");

    // (2) THA tep ⇒ nap NGAY, voi dung nhung tep nam trong `dataTransfer.files`.
    fireEvent.drop(khung, {
      dataTransfer: { files: [tep("a.wav"), tep("b.mp4", [9, 9], "video/mp4")] },
    });
    await waitFor(() => assert.equal(goi.length, 1), { timeout: 5000, interval: 20 });
    assert.deepEqual(goi[0]?.ten, ["a.wav", "b.mp4"], "`onDrop` phai doc `e.dataTransfer.files`");

    await choKetQua(container, /a\.wav: đã nạp — kênh 3/);
    await choKetQua(container, /b\.mp4: đã nạp — kênh 3/);

    assert.deepEqual(tiengOn, [], "keo-tha khong duoc sinh tieng on console");
    unmount();
  });

  it("F) LỐI GỌN `NhapGon` (vùng KÊNH): cùng seam nạp, nạp NGAY khi chọn tệp, và kết quả hiện bằng CHỮ", async () => {
    const goi: LanGoi[] = [];
    const napTep = napTepGhi(goi, (files) => [
      { ten: files[0]?.name ?? "", ok: true, sourceId: 12 },
      { ten: files[1]?.name ?? "", ok: false, loi: "422: tệp rỗng" },
    ]);
    const { container, unmount } = render(taoPhanTu(NhapGon, { napTep }));

    const o = phanTu(container, '[data-testid="ch-nap-o-tep"]') as HTMLInputElement;
    assert.equal(o.getAttribute("type"), "file");
    assert.ok(o.hasAttribute("multiple"), "loi gon cung phai nhan NHIEU tep (§12.2: tep thu 2..N)");
    assert.equal(o.getAttribute("accept"), null, "loi gon cung KHONG duoc loc dinh dang o client");

    fireEvent.change(o, { target: { files: [tep("c.wav"), tep("rong.wav", [])] } });
    // GON: khong co nut trung gian — chon tep la nap.
    await waitFor(() => assert.equal(goi.length, 1), { timeout: 5000, interval: 20 });
    assert.deepEqual(goi[0]?.ten, ["c.wav", "rong.wav"]);

    await choKetQua(container, /c\.wav: đã nạp — kênh 12/);
    const loi = await choKetQua(container, /rong\.wav: LỖI/);
    assert.match(loi, /422: tệp rỗng/, "loi gon cung phai hien cau loi NGUYEN VAN cua backend");

    assert.deepEqual(tiengOn, [], "loi gon khong duoc sinh tieng on console");
    unmount();
  });

  it("G) HÌNH THỨC: LUẬT ↔ CLASS KHỚP NHAU (hai chiều) + các QUAN HỆ hình thức của §4.2", async () => {
    // ---------------------------------------------------------------------------
    // ⚠️ VI SAO BAI NAY TON TAI: mot `className` trong TSX KHONG ve gi ca — do duoc HAI CHIEU o
    // Task 6 (ERRATA #15 muc 3). Va lop `Minor #1` cua W3 (ERRATA #36 muc 5) la MOT LOP MOI:
    // **DOI TEN LUAT trong `app.css` ma GIU `className`** ⇒ 0 bai do — class van trong DOM, luat
    // van "co trong tep", nhung **KHONG CON KHOP NHAU**. Bai nay ghim QUAN HE HAI CHIEU do
    // (ERRATA #34 muc 1: ghim QUAN HE, khong ghim nguyen van):
    //   (A) MOI lop `nap*`/`ch__nap*` ma `app.css` TAO KIEU phai XUAT HIEN trong DOM THAT;
    //   (B) MOI lop nhu vay trong DOM THAT phai duoc `app.css` tao kieu.
    // ⚠️ KHONG ghim danh sach ten lop nguyen van: them mot lop moi (co luat + co dung) phai lam
    // bai XANH.
    // ---------------------------------------------------------------------------
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const khoi = cacKhoi(appCss);

    const lopTrongDom = new Set<string>();
    const gom = (container: HTMLElement): void => {
      for (const el of container.querySelectorAll("*")) {
        for (const lop of el.classList) {
          if (/^(ch__)?nap/.test(lop)) lopTrongDom.add(lop);
        }
      }
    };

    // (1) Trang thai CO BAN cua khung: khung + o chon + nut + vung ket qua (rong).
    gom(render(taoPhanTu(IntakeFrame, { napTep: napTepGhi([], () => []) })).container);
    // (2) NhapGon voi mot luot nap THANH CONG + mot luot LOI ⇒ sinh `.nap__kq`, `--xong`, `--loi`.
    const cGon = render(
      taoPhanTu(NhapGon, {
        napTep: napTepGhi([], (files) => [
          { ten: files[0]?.name ?? "", ok: true, sourceId: 1 },
          { ten: files[1]?.name ?? "", ok: false, loi: "422: tệp rỗng" },
        ]),
      }),
    ).container;
    fireEvent.change(phanTu(cGon, '[data-testid="ch-nap-o-tep"]'), {
      target: { files: [tep("a.wav"), tep("rong.wav", [])] },
    });
    await choCoLop(cGon, ".nap__kq", 2);
    gom(cGon);

    // (3) Trang thai DANG NAP (`.nap__cho` cua khung, `.ch__nap-cho` cua loi gon) — chi ton tai khi
    // promise CHUA tra ⇒ phai do bang mot promise TREO.
    const cTreo = render(taoPhanTu(IntakeFrame, { napTep: () => treo() })).container;
    fireEvent.change(phanTu(cTreo, '[data-testid="nap-o-tep"]'), { target: { files: [tep("a.wav")] } });
    fireEvent.click(phanTu(cTreo, '[data-testid="nap-nut"]'));
    await choCoLop(cTreo, ".nap__cho", 1);
    gom(cTreo);
    const cGonTreo = render(taoPhanTu(NhapGon, { napTep: () => treo() })).container;
    fireEvent.change(phanTu(cGonTreo, '[data-testid="ch-nap-o-tep"]'), {
      target: { files: [tep("a.wav")] },
    });
    await choCoLop(cGonTreo, ".ch__nap-cho", 1);
    gom(cGonTreo);

    const trongCss = lopTrongCss(khoi);
    assert.ok(trongCss.size >= 12, `phai doc duoc cac lop nap* tu app.css; do duoc ${trongCss.size}`);
    assert.ok(lopTrongDom.size >= 12, `phai thu duoc cac lop nap* tu DOM; do duoc ${lopTrongDom.size}`);

    // (A) LUAT ⇒ LOP: luat mo coi (khong lop nao mang ten do) lam bai DO.
    const moCoi = [...trongCss].filter((lop) => !lopTrongDom.has(lop)).sort();
    assert.deepEqual(
      moCoi,
      [],
      `LUAT MO COI: ${JSON.stringify(moCoi)} — luat nay khong lop nao trong DOM mang, tuc no KHONG `
      + `tao kieu cho thu gi. Lop co trong DOM: ${JSON.stringify([...lopTrongDom].sort())}`,
    );

    // (B) LOP ⇒ LUAT: lop trong DOM ma khong co luat nao ap cho no cung lam bai DO.
    const voLuat = [...lopTrongDom].filter((lop) => !trongCss.has(lop)).sort();
    assert.deepEqual(
      voLuat,
      [],
      `LOP KHONG CO LUAT: ${JSON.stringify(voLuat)} — lop nay nam trong DOM nhung app.css khong tao `
      + `kieu cho no. Luat co trong app.css: ${JSON.stringify([...trongCss].sort())}`,
    );

    // Cac QUAN HE HINH THUC cua §4.2 — class ↔ khai bao, doc tu CHINH van ban luat.
    assert.match(
      thanCua(khoi, "nap__khung"),
      /dashed/,
      "khung §4.2 phai la net DUT (`dashed`) — do la hinh thuc spec UI §4.2 dat ten",
    );
    const thanKeo = thanCua(khoi, "nap__keo");
    assert.match(
      thanKeo,
      /var\(--font-label\)/,
      "`KÉO TỆP VÀO ĐÂY` phai dung mat nhan khac (Archivo Expanded) cua §2.1",
    );
    assert.match(
      thanKeo,
      /var\(--track-label\)/,
      "nhan khac phai GIAN RONG (`--track-label`) — chu cua §4.2 khong phai heading web",
    );
    assert.match(
      thanCua(khoi, "nap__dinh-dang"),
      /var\(--font-mono\)/,
      "dong dinh dang phai la dong MONO cua §2.1",
    );
    // *"Khong phai mot the nho giua man hinh"*: khung phai GROW de chiem vung giua. Mot the nho se
    // la `flex: 0 0 auto` (hoac khong co `flex` nao) — mot bien the lam luat vo nghia ma bai chi
    // khang dinh "co `border`" KHONG bat duoc.
    assert.match(
      thanCua(khoi, "nap__khung"),
      /flex:\s*1(\s+1\s+auto)?/,
      "khung §4.2 phai GROW trong vung giua (khong phai mot the nho giua man hinh)",
    );

    assert.deepEqual(tiengOn, [], "trang thai dang nap khong duoc sinh tieng on console");
    cleanup();
  });

  it("H) MỘT hàm nạp: `uploadSource` chi duoc goi o `App.tsx` — khong co duong nap thu hai", () => {
    // Bat bien cua brief W2 ("MỘT hàm nạp, hai lối vào — đừng viết hai lần") o dang KIEM DUOC:
    // đếm CALL SITE trong chính mã nguồn. `IntakeFrame.tsx`/`ChannelZone.tsx` chỉ được gọi
    // `napTep` (PROP) — chúng không được tự chạm tầng API.
    const demGoi = (duong: string): number => {
      const nguon = readFileSync(new URL(duong, import.meta.url), "utf8");
      return (nguon.match(/uploadSource\(/g) ?? []).length;
    };
    assert.equal(demGoi("./App.tsx"), 1, "`App.tsx` phai la noi DUY NHAT goi `endpoints.uploadSource`");
    assert.equal(demGoi("./IntakeFrame.tsx"), 0, "khung §4.2 KHONG duoc tu goi `uploadSource`");
    assert.equal(demGoi("./ChannelZone.tsx"), 0, "loi gon o vung KENH KHONG duoc tu goi `uploadSource`");
  });
});
