/**
 * Test `<QueueZone/>` THAT trong jsdom — **HUY JOB + CHAY LAI JOB** (Task D2), va **CAU CHU TRUNG
 * THUC** cua mot lan huy job dang chay.
 *
 * VI SAO TEP NAY LA TEP MOI: truoc D2, vung HANG DOI chi HIEN job (`<li>` + chu) — khong co duong
 * NAO tac dong len mot job (`cancelJob`/`retryJob` **0 luot goi trong san pham**). Bai DI QUA
 * DUONG THAT (bam ⇒ HTTP that ⇒ dem o PHIA MAY CHU) nam o `App.test.tsx` (no can ca shell + server
 * `node:http`); tep nay ghim DUNG hop dong cua control: trang thai nao co nut nao, cau chu ra sao,
 * va LUAT CSS ↔ CLASS cua bon hinh thuc moi.
 *
 * ## MENH DE TRUNG THUC (hop dong §2 cua brief)
 *
 * `cancelJob` tren job `running` **CHI DAT CO** — trang thai job khong doi o phia may chu. Nen cau
 * chu DUY NHAT duoc phep la *"đã yêu cầu huỷ"*; moi cau khang dinh trang thai ("đã dừng", "đã huỷ")
 * la mot LOI NOI DOI, khong phai mot lua chon van phong. Bai o day ghim CA HAI ve: cau dung CO MAT,
 * va hai cau SAI VANG MAT.
 *
 * ## LUAT DOM (ERRATA #9 muc 1/6): tep nay TU CHUA
 *
 * Hook dat/tra global nam TRONG `describe()`; `console.error`/`console.warn` duoc TRA LAI trong
 * `after`; KHONG dua node DOM song vao `assert` (ERRATA #14 muc 3).
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import type { Job, JobState } from "../api/types.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

/** Mot job dung muoi bon khoa cua `routes_jobs._job_json`. */
function makeJob(id: number, type: Job["type"], state: Job["state"], progress = 0.5): Job {
  return {
    id,
    workspace: 1,
    type,
    engine: type === "asr" ? "faster-whisper-large" : null,
    phase: type === "asr" ? "asr:faster-whisper-large" : `${type}:-`,
    state,
    cancel_requested: false,
    attempts: 1,
    progress,
    log_tail: "",
    error: null,
    payload: { source_id: 1, lang: "zh" },
    created_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

/**
 * Sau job, MOI trang thai mot lan — de "trang thai nao co nut nao" duoc do tren CA TAP GIA TRI cua
 * `JobState`, khong phai tren hai vi du.
 */
const JOBS = new Map<number, Job>([
  [1, makeJob(1, "ingest", "queued")],
  [2, makeJob(2, "asr", "running", 0.42)],
  [3, makeJob(3, "asr", "done", 1)],
  [4, makeJob(4, "asr", "failed", 0.3)],
  [5, makeJob(5, "asr", "interrupted", 0.6)],
  [6, makeJob(6, "asr", "cancelled")],
]);

/** Khong co gi de bao: hai ban do RONG (trang thai mac dinh cua vung). */
const KHONG_HUY: ReadonlyMap<number, JobState> = new Map();
const KHONG_LOI: ReadonlyMap<number, string> = new Map();

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
let fireEvent: { click: (el: Element) => void };
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let QueueZone: (props: unknown) => unknown;

/** Phan tu DAU TIEN khop `chon` — tra NODE de doc thuoc tinh/bam, KHONG bao gio dua vao `assert`. */
function phanTu(container: HTMLElement, chon: string): Element {
  const el = container.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el;
}

/** `textContent` cua phan tu DAU TIEN khop `chon`. */
function chu(container: HTMLElement, chon: string): string {
  return phanTu(container, chon).textContent ?? "";
}

/**
 * MOI khai bao cua MOT selector trong `app.css`, khai bao SAU THANG (dung luat CSS khi do dac hieu
 * bang nhau) — ⚠️ `RegExp(sel + "\\{[^}]*\\}")` chi doc khoi DAU TIEN khop, nen mot luat SAU ghi de
 * di qua XANH (ERRATA #42 muc 5).
 */
function khaiBaoCua(css: string, chon: string): Map<string, string> {
  const ra = new Map<string, string>();
  const sach = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const phan of sach.split("}")) {
    const i = phan.lastIndexOf("{");
    if (i < 0) continue;
    const danhSachChon = phan.slice(0, i).split(",").map((s) => s.trim()).filter((s) => s !== "");
    if (!danhSachChon.includes(chon)) continue;
    for (const khai of phan.slice(i + 1).split(";")) {
      const hai = khai.indexOf(":");
      if (hai < 0) continue;
      ra.set(khai.slice(0, hai).trim(), khai.slice(hai + 1).trim());
    }
  }
  return ra;
}

/** Tap LOP co THAT trong cay da render. */
function lopTrongDom(container: HTMLElement): Set<string> {
  const ra = new Set<string>();
  for (const el of container.querySelectorAll("*")) {
    for (const ten of el.classList) if (/^lenh/.test(ten)) ra.add(ten);
  }
  return ra;
}

/** Render vung HANG DOI voi mot ban do job + hai ban do trang thai lenh (mac dinh: rong). */
function renderQueue(
  jobs: Map<number, Job> = JOBS,
  daYeuCauHuy: ReadonlyMap<number, JobState> = KHONG_HUY,
  loiLenh: ReadonlyMap<number, string> = KHONG_LOI,
): { container: HTMLElement; unmount: () => void; huy: number[]; lai: number[] } {
  const huy: number[] = [];
  const lai: number[] = [];
  const kq = render(
    taoPhanTu(QueueZone, {
      jobs,
      daYeuCauHuy,
      loiLenh,
      onHuyJob: (id: number) => {
        huy.push(id);
      },
      onChayLaiJob: (id: number) => {
        lai.push(id);
      },
    }),
  );
  return { ...kq, huy, lai };
}

describe("QueueZone: huy job + chay lai job (Task D2)", () => {
  before(async () => {
    teardownDom();
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl : rtl.default;
    render = api.render;
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const vung: any = await import("./QueueZone.tsx");
    QueueZone = vung.QueueZone;

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

  it("D2 TRANG THAI → NUT: huy CHI o `queued`/`running`; chay lai CHI o `failed`/`interrupted`", () => {
    const { container, unmount, huy, lai } = renderQueue();

    // Bon job co nut HUY, DUNG id nao ra id do.
    assert.deepEqual(
      [...container.querySelectorAll('[data-testid^="huy-job-"]')].map((el) => el.getAttribute("data-testid")).sort(),
      ["huy-job-1", "huy-job-2"],
      "nút huỷ chỉ được có ở job `queued`/`running`",
    );
    assert.deepEqual(
      [...container.querySelectorAll('[data-testid^="lai-job-"]')].map((el) => el.getAttribute("data-testid")).sort(),
      ["lai-job-4", "lai-job-5"],
      "nút chạy lại chỉ được có ở job `failed`/`interrupted`",
    );

    fireEvent.click(phanTu(container, '[data-testid="huy-job-1"]'));
    fireEvent.click(phanTu(container, '[data-testid="lai-job-5"]'));
    assert.deepEqual(huy, [1], "bấm huỷ phải báo ĐÚNG id job");
    assert.deepEqual(lai, [5], "bấm chạy lại phải báo ĐÚNG id job");

    // Trang thai MAY doc duoc: moi dong mang `data-state` cua chinh no (va no den tu ban do job,
    // khong phai tu mot lop trang tri song song).
    for (const [id, state] of [[1, "queued"], [2, "running"], [6, "cancelled"]] as const) {
      assert.equal(
        phanTu(container, `[data-testid="job-${id}"]`).getAttribute("data-state"),
        state,
        `dong #${id} phai mang data-state cua no`,
      );
    }

    assert.deepEqual(tiengOn, [], "render vung HANG DOI khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 CÂU CHỮ: job `running` nói RA 'đã yêu cầu huỷ' — và KHÔNG BAO GIỜ nói 'đã dừng'", () => {
    // Ban do "da yeu cau huy" ghi TRANG THAI LUC GUI cho TUNG job: cau nay chi duoc hien khi trang
    // thai job VAN LA trang thai do (may chu chua xac nhan) — xem bai duoi.
    const { container, unmount } = renderQueue(
      JOBS,
      new Map<number, JobState>([[2, "running"]]),
    );

    assert.equal(
      chu(container, '[data-testid="huy-tin-2"]'),
      "đã yêu cầu huỷ",
      "job `running` chỉ được ĐẶT CỜ ⇒ câu chữ phải là 'đã YÊU CẦU huỷ'",
    );
    // VE AM: hai cau SAI khong duoc xuat hien o BAT KY dau trong vung.
    const ca = container.textContent ?? "";
    assert.ok(!ca.includes("đã dừng"), `KHÔNG được nói 'đã dừng' ở bất kỳ đâu; đo được ${JSON.stringify(ca)}`);
    assert.ok(
      !(container.querySelector('[data-testid="job-2"]')?.textContent ?? "").includes("đã huỷ"),
      "job `running` bị đặt cờ KHÔNG phải là 'đã huỷ'",
    );
    // LY DO CHO van la su that cua ban do job: "đang chạy".
    assert.match(chu(container, '[data-testid="job-2"]'), /đang chạy/);

    assert.deepEqual(tiengOn, [], "cau chu cua lenh huy khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 XÁC NHẬN TỪ MÁY CHỦ ⇒ câu 'đã yêu cầu huỷ' BIẾN MẤT (trạng thái vẫn do dữ liệu job quyết định)", () => {
    // Cung mot ban do "da yeu cau huy" (`2 → running`), nhung job da doi trang thai (su kien SSE o
    // `App`): cau cu KHONG con dung nua va phai bien mat, nhuong cho su that moi cua job.
    const daXacNhan = new Map<number, Job>([[2, makeJob(2, "asr", "cancelled", 0.42)]]);
    const { container, unmount } = renderQueue(daXacNhan, new Map<number, JobState>([[2, "running"]]));

    assert.equal(
      container.querySelectorAll('[data-testid="huy-tin-2"]').length,
      0,
      "trạng thái job đã đổi ⇒ câu 'đã yêu cầu huỷ' phải BIẾN MẤT",
    );
    assert.match(chu(container, '[data-testid="job-2"]'), /đã huỷ/, "trạng thái mới của job phải được NÓI RA");

    assert.deepEqual(tiengOn, [], "xac nhan tu may chu khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 LỖI NGUYÊN VĂN hiện CẠNH ĐÚNG job (khoá theo id, không phải một thông báo chung)", () => {
    const { container, unmount } = renderQueue(
      JOBS,
      KHONG_HUY,
      new Map<number, string>([[4, "409: job 4 không ở trạng thái chạy lại được (đang `done`)"]]),
    );

    assert.equal(
      chu(container, '[data-testid="loi-lenh-4"]'),
      "409: job 4 không ở trạng thái chạy lại được (đang `done`)",
      "câu lỗi phải là NGUYÊN VĂN `ApiError.message` (`<status>: <detail>`)",
    );
    assert.equal(
      container.querySelectorAll('[data-testid^="loi-lenh-"]').length,
      1,
      "câu lỗi chỉ được nằm ở ĐÚNG job của nó",
    );

    assert.deepEqual(tiengOn, [], "cau loi cua lenh khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 HÌNH THỨC: `.lenh*` của vùng HÀNG ĐỢI có LUẬT trong `app.css` VA có THAT trong DOM (hai chiều)", () => {
    // ⚠️ Bai nay ghim QUAN HE (ERRATA #34 muc 1 / #43 muc 2), khong ghim chu cua luat: xoa luat ma
    // giu `className` ⇒ DO; doi ten `className` trong DOM ma giu luat ⇒ DO.
    // ⚠️ Phep kiem HAI CHIEU tren CA HO `lenh*` (ke ca nut `duyệt` cua `EditScreen`) nam o
    // `App.test.tsx` (no render CA HAI vung). O day ghim tap con cua vung HANG DOI.
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const { container, unmount } = renderQueue(JOBS, new Map<number, JobState>([[2, "running"]]));

    const cuaVungNay = ["lenh", "lenh--huy", "lenh--lai", "lenh__tin"];
    const trongDom = lopTrongDom(container);
    for (const ten of cuaVungNay) {
      assert.ok(
        trongDom.has(ten),
        `lop \`${ten}\` phai co THAT trong DOM; do duoc ${JSON.stringify([...trongDom].sort())}`,
      );
      const khai = khaiBaoCua(appCss, `.${ten}`);
      assert.ok(khai.size > 0, `phai co LUAT \`.${ten}\` trong app.css (co khai bao THANG CUOC)`);
    }
    // KHAI BAO THANG CUOC: cau trang thai la mot KHOI chu rieng, khong nam cung dong voi nut.
    assert.equal(khaiBaoCua(appCss, ".lenh__tin").get("display"), "block");
    // Nut la NUT THAT (ban phim dung duoc), khong phai `div` + `role`.
    for (const chon of ['[data-testid="huy-job-1"]', '[data-testid="lai-job-4"]']) {
      const nut = phanTu(container, chon);
      assert.equal(nut.tagName, "BUTTON", `${chon} phai la NUT that`);
      assert.equal(nut.getAttribute("type"), "button", `${chon} phai co type=button`);
    }

    assert.deepEqual(tiengOn, [], "hinh thuc D2 cua vung HANG DOI khong duoc sinh tieng on console");
    unmount();
  });

  it("D2 HÌNH THỨC: `.q*` của vùng HÀNG ĐỢI có LUẬT trong `app.css` VA có THAT trong DOM (hai chiều)", () => {
    // DO DUOC TRUOC (`I1` cua review D2): `Select-String '^\.q' app.css` = **0** ⇒
    // `<ul class="q__danh-sach">` khong duoc reset (trinh duyet ve DAU DAU DONG + thut le mac dinh)
    // va cac `<span>` inline khong co `gap`/`margin` ⇒ chu DINH (`qwen2.5-3bđang chạy`). Bai ghim
    // hai chieu cua D2 loc `/^lenh/` nen ca ho `q*` nam NGOAI luat do — dung ba dieu khien MOI cua
    // D2 lai nam trong chinh `<li class="q__item">` do.
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");

    // (a) GHIM KHAI BAO, khong ghim CHU cua luat: ⚠️ `listStyleType` KHONG the ghim trong jsdom
    //     (khong bai nao nap `app.css` vao DOM, va jsdom khong co layout) ⇒ ghim KHAI BAO + QUAN HE.
    assert.match(
      appCss,
      /\.q__danh-sach \{[^}]*margin: 0[^}]*padding: 0[^}]*list-style: none/,
      '`<ul class="q__danh-sach">` phai duoc RESET (margin/padding/list-style) — cung khuon `.ch__danh-sach`',
    );
    const khaiItem = khaiBaoCua(appCss, ".q__item");
    assert.equal(khaiItem.get("display"), "flex", "`.q__item` phai la mot HANG flex (khai bao THANG CUOC)");
    assert.ok(
      khaiItem.get("gap") !== undefined,
      "`gap` la thu TACH cac `<span>` cua mot hang job; khong co no thi chu DINH vao nhau",
    );
    // 🔴 CO Y FLEX, KHONG GRID: `grid-template-*` la luoi track CO DINH ⇒ them con thu N la tai
    // sinh ERRATA #31 muc 1 (lop loi da sai that hai lan o `.shell`/`.cmp`).
    assert.equal(khaiItem.get("grid-template-rows"), undefined, "`.q__item` KHONG duoc khai luoi track co dinh");
    assert.equal(khaiItem.get("grid-template-columns"), undefined, "`.q__item` KHONG duoc khai luoi track co dinh");

    // (b) HAI CHIEU: moi LUAT `q*` phai co lop trong DOM, va moi LOP `q*` trong DOM phai co luat
    //     (tru mot CAN TREN da khai ngay duoi).
    const trongDom = new Set<string>();
    const gom = (container: HTMLElement): void => {
      for (const el of container.querySelectorAll("*")) {
        for (const ten of el.classList) if (/^q/.test(ten)) trongDom.add(ten);
      }
    };
    gom(renderQueue(JOBS, new Map<number, JobState>([[2, "running"]]), new Map<number, string>([[4, "x"]])).container);
    cleanup();
    // Trang thai RONG cua vung: `.q__rong` chi co o nhanh do ⇒ phai GOM, neu khong phep kiem (A)
    // se bao "LUAT MO COI" oan.
    gom(renderQueue(new Map<number, Job>(), KHONG_HUY, KHONG_LOI).container);

    const sachCss = appCss.replace(/\/\*[\s\S]*?\*\//g, "");
    const trongCss = new Set<string>();
    for (const m of sachCss.matchAll(/\.(q(?:__[a-z0-9-]+)?)/g)) trongCss.add(m[1] ?? "");
    trongCss.delete("");

    const moCoi = [...trongCss].filter((t) => !trongDom.has(t)).sort();
    assert.deepEqual(
      moCoi,
      [],
      `LUẬT MỒ CÔI: ${JSON.stringify(moCoi)} — luật này không lớp nào trong DOM mang, tức nó KHÔNG `
      + `tạo kiểu cho thứ gì. Lớp có trong DOM: ${JSON.stringify([...trongDom].sort())}`,
    );
    // CAN TREN da khai (dung khuon `NO_CHUA_CO_LUAT` cua `ChannelZone.test.tsx`): `.q__item--{state}`
    // la lop BIEN THE theo trang thai (dau trang tri, chua co luat nao, va them mot luat cho no KHONG
    // lam bai nay do), con `.q` lay hop cua `.shell__queue` — cung khuon `.ch` (cung chua co luat).
    const voLuat = [...trongDom]
      .filter((t) => !trongCss.has(t))
      .filter((t) => t !== "q" && !/^q__item--/.test(t))
      .sort();
    assert.deepEqual(
      voLuat,
      [],
      `LỚP KHÔNG CÓ LUẬT: ${JSON.stringify(voLuat)} — lớp này nằm trong DOM mà app.css không tạo kiểu `
      + `cho nó. Luật có trong app.css: ${JSON.stringify([...trongCss].sort())}`,
    );

    assert.deepEqual(tiengOn, [], "hinh thuc `.q*` cua vung HANG DOI khong duoc sinh tieng on console");
  });
});
