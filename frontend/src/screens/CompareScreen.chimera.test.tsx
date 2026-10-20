/**
 * §4.5 CHE DO CHIMERA — dai canh bao chi phi DO DUOC + bon cua so ung vien moi dong.
 *
 * VI SAO TEP RIENG, khong nhet vao `CompareScreen.test.tsx`: tep kia ghim §4.3 (hai cot
 * + cot CPS + segmented control + ghim ban B) va dang xanh; tron them mot tinh nang vao
 * do lam mot bai do khong con chi ra duoc no thuoc ve nao. Hai tep cung render CUNG mot
 * component qua CUNG mot bo prop — do la "khai bao + quan he", khong phai ban sao.
 *
 * ⚠️ jsdom KHONG co layout va KHONG co CSS: tep nay do duoc HANH VI (phan tu nao co mat,
 * lop nao, chu nao, con so nao, quan he CHA-CON nao) va KHONG do duoc HINH (`grid-row`
 * that, be rong cot, tuong phan mau). Cac khang dinh HINH THUC nam o tang Chrome that
 * (`frontend/e2e/`) va o `chimera-report.md` — xem ERRATA #40.
 *
 * LUAT DOM cua repo (ERRATA #9 muc 1/6): hook dat/tra global nam TRONG `describe()`;
 * `setupDom`/`teardownDom` cua CHINH tep nay; `console.error/warn` duoc tam thay va tra
 * lai trong `after`.
 */
import { after, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

import type {
  ChimeraCost,
  Segment,
  Transcript,
  TranslationDetail,
} from "../api/types.ts";
import { setupDom, teardownDom } from "../../test/dom.ts";

function doan(i: number, text: string): Segment {
  return { i, start: i, end: i + 2, text, suspect: false };
}

function banGhi(segments: Segment[]): Transcript {
  return {
    id: 1,
    source_id: 1,
    engine: "fw-large-v3-turbo",
    lang: "zh",
    version: 2,
    status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    translations: [],
    segments,
  };
}

/** Mot ban dich CHI TIET, khong kem dau vet Chimera (`chimera: null`). */
function banDichThuong(id: number, texts: string[]): TranslationDetail {
  return {
    id,
    transcript_id: 1,
    engine: "opus-mt",
    target_lang: "vi",
    prompt_version: "raw-p1",
    transcript_version: 1,
    status: "done",
    stale: false,
    created_at: "2026-01-01T00:00:00Z",
    chimera: null,
    segments: texts.map((t, k) => doan(k + 1, t)),
    cps: {
      max_cps: 21,
      rows: texts.map((_t, k) => ({
        i: k + 1,
        chars: 10,
        window: 1,
        cps: 10,
        max_cps: 21,
        over: false,
      })),
    },
  };
}

const CHI_PHI: ChimeraCost = {
  segments: 2,
  declared: 6,
  runnable: 4,
  calls_per_batch: 5,
  multiplier: 5,
  merge_engine: "qwen2.5-3b",
  candidates: [
    { id: "c1", engine: "opus-mt", label: "OPUS-MT", temperature: null,
      quality_note: null, available: true, reason: null },
    { id: "c2", engine: "qwen2.5-3b", label: "Qwen-3B 0,1", temperature: 0.1,
      quality_note: "ĐÃ ĐO: engine này CHÉP nguyên chữ nguồn 43/44 đoạn.",
      available: true, reason: null },
    { id: "c5", engine: "qwen2.5-7b", label: "Qwen-7B", temperature: 0.1,
      quality_note: null, available: false, reason: "model chưa được pull" },
    { id: "c6", engine: "hy-mt-1.5-7b", label: "HY-MT", temperature: 0.1,
      quality_note: null, available: false, reason: "model chưa được pull" },
  ],
  baseline: { translation_id: 7, engine: "qwen2.5-3b", segments: 2,
              duration_ms: 3000, tokens_in: 256, tokens_out: 110 },
  estimate: { calls_per_batch: 5, duration_ms: 15000, tokens_in: 1280,
              tokens_out: 550 },
  estimate_basis: "đo từ bản dịch #7 (qwen2.5-3b): 3000 ms / 2 đoạn",
  estimate_hint: null,
};

/** Ban dich CO dau vet Chimera: 4 ung vien chay, mot luot pha. */
function banDichChimera(): TranslationDetail {
  const base = banDichThuong(9, ["Câu gộp một", "Câu gộp hai"]);
  return {
    ...base,
    engine: "qwen2.5-3b",
    prompt_version: "chimera-merge-p1",
    chimera: {
      enabled: true,
      declared: 6,
      run_count: 4,
      ran_count: 4,
      calls_per_batch: 5,
      merge_engine: "qwen2.5-3b",
      anchors: { c1: 1, c2: 1 },
      candidates: [
        {
          id: "c1", engine: "opus-mt", label: "OPUS-MT", temperature: null,
          quality_note: null, available: true, reason: null,
          ran: true, skipped: null, qa: 1, cps_over: 0, echo: 0, calls: 1,
          tokens_in: null, tokens_out: null, duration_ms: null,
          segments: [{ i: 1, text: "Câu opus một" }, { i: 2, text: "Câu gộp hai" }],
        },
        {
          id: "c2", engine: "qwen2.5-3b", label: "Qwen-3B 0,1", temperature: 0.1,
          quality_note: null, available: true, reason: null,
          ran: true, skipped: null, qa: 4, cps_over: 0, echo: 2, calls: 1,
          tokens_in: 256, tokens_out: 110, duration_ms: 2315,
          segments: [{ i: 1, text: "第一句" }, { i: 2, text: "第二句" }],
        },
        {
          id: "c5", engine: "qwen2.5-7b", label: "Qwen-7B", temperature: 0.1,
          quality_note: null, available: false, reason: "model chưa được pull",
          ran: false, skipped: "model chưa được pull", qa: 0, cps_over: 0, echo: 0,
          calls: 0, tokens_in: null, tokens_out: null, duration_ms: null,
          segments: [],
        },
        {
          id: "c6", engine: "hy-mt-1.5-7b", label: "HY-MT", temperature: 0.1,
          quality_note: null, available: false, reason: "model chưa được pull",
          ran: false, skipped: "model chưa được pull", qa: 0, cps_over: 0, echo: 0,
          calls: 0, tokens_in: null, tokens_out: null, duration_ms: null,
          segments: [],
        },
      ],
      merge: {
        engine: "qwen2.5-3b", calls: 1, tokens_in: 669, tokens_out: 147,
        duration_ms: 1037,
        fallback_segments: [],
        fallback_reason: null,
        identical_segments: [2],
        anchor_by_segment: { "1": 1, "2": 2 },
      },
      estimate: { calls_per_batch: 5, duration_ms: 15000, tokens_in: 1280,
                  tokens_out: 550 },
      estimate_basis: "đo từ bản dịch #7 (qwen2.5-3b): 3000 ms / 2 đoạn",
      baseline: null,
      segments: 2,
    },
  };
}

const consoleGoc = { error: console.error, warn: console.warn };
const tiengOn: string[] = [];

let render: (ui: unknown) => { container: HTMLElement; unmount: () => void };
let fireEvent: { click: (el: Element) => void };
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let CompareScreen: (props: unknown) => unknown;

/** `textContent` cua phan tu DAU TIEN khop `chon` — khong hoi ca DOM. */
function chu(goc: HTMLElement, chon: string): string {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.textContent ?? "";
}

function dem(goc: HTMLElement, chon: string): number {
  return goc.querySelectorAll(chon).length;
}

function thuocTinh(goc: HTMLElement, chon: string, ten: string): string | null {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.getAttribute(ten);
}

function laConTrucTiep(goc: HTMLElement, chonCon: string, chonCha: string): boolean {
  const con = goc.querySelector(chonCon);
  const cha = goc.querySelector(chonCha);
  assert.ok(con !== null && cha !== null, "thieu phan tu de kiem quan he cha-con");
  return con.parentElement === cha;
}

describe("§4.5 CHE DO CHIMERA", () => {
  before(async () => {
    teardownDom();
    setupDom("http://127.0.0.1:9");

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    fireEvent = api.fireEvent;
    cleanup = api.cleanup;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const man: any = await import("./CompareScreen.tsx");
    CompareScreen = man.CompareScreen;

    console.error = (...args: unknown[]): void => {
      tiengOn.push(`error: ${args.map((a) => String(a)).join(" ")}`);
    };
    console.warn = (...args: unknown[]): void => {
      tiengOn.push(`warn: ${args.map((a) => String(a)).join(" ")}`);
    };
  });

  after(() => {
    cleanup();
    console.error = consoleGoc.error;
    console.warn = consoleGoc.warn;
    teardownDom();
    assert.deepEqual(tiengOn, [], `React keu len tieng on:\n${tiengOn.join("\n")}`);
  });

  beforeEach(() => {
    cleanup();
  });

  const nen = [banGhi([doan(1, "第一句"), doan(2, "第二句")])];

  // ---------------------------------------------------------------- cai CHIP
  it("chip CHIMERA nam tren thanh cong cu, va bam thi BAO LEN App", () => {
    const daBam: boolean[] = [];
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
      chimera: false,
      onChimeraChange: (bat: boolean) => daBam.push(bat),
    }));
    assert.equal(
      thuocTinh(container, '[data-testid="chimera-chip"]', "aria-pressed"), "false",
      "chip phai noi TRANG THAI cua no bang `aria-pressed`, khong chi bang mau",
    );
    fireEvent.click(container.querySelector('[data-testid="chimera-chip"]')!);
    assert.deepEqual(daBam, [true], "man chi BAO len `App`, khong tu bat co");
  });

  it("chip dang BAT thi `aria-pressed` la true", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
      chimera: true,
      chiPhi: CHI_PHI,
    }));
    assert.equal(
      thuocTinh(container, '[data-testid="chimera-chip"]', "aria-pressed"), "true",
    );
  });

  // ------------------------------------------------------- dai CANH BAO CHI PHI
  it("dai chi phi la CON TRUC TIEP cua luoi `.cmp` (khai bao + quan he)", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
      chimera: true,
      chiPhi: CHI_PHI,
    }));
    assert.ok(
      laConTrucTiep(container, '[data-testid="chimera-chi-phi"]', ".cmp"),
      "dai chi phi phai la MOT CON cua luoi `.cmp` — do la ve ma `app.css` phai khai "
      + "them mot track va mot `grid-row` (ERRATA #31 muc 1)",
    );
  });

  it("chua doc duoc chi phi ⇒ dai noi DANG DO, khong dung spinner tron", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
      chimera: true,
      chiPhi: null,
      dangDocChiPhi: true,
    }));
    const dai = chu(container, '[data-testid="chimera-chi-phi"]');
    assert.ok(/đang đo/i.test(dai), `dai phai noi dang do, nhan duoc: ${dai}`);
    assert.equal(
      dem(container, '[data-testid="chimera-chi-phi"] .bp-spinner'), 0,
      "khong dung spinner tron: trang thai dang chay la SKELETON/khoi khop bo cuc",
    );
  });

  it("loi doc chi phi ⇒ NGUYEN VAN cau cua backend", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
      chimera: true,
      loiChiPhi: "503: registry chưa khai báo chế độ Chimera (khoá `chimera.candidates`)",
    }));
    const dai = chu(container, '[data-testid="chimera-chi-phi"]');
    assert.ok(
      dai.includes("503: registry chưa khai báo chế độ Chimera"),
      `loi phai nguyen van, nhan duoc: ${dai}`,
    );
  });

  it("co so do ⇒ hien so ung vien THAT, he so, uoc luong, va TEN cai thieu", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
      chimera: true,
      chiPhi: CHI_PHI,
    }));
    const dai = chu(container, '[data-testid="chimera-chi-phi"]');
    assert.ok(dai.includes("5 lượt gọi model cho mỗi lô"), dai);
    assert.ok(dai.includes("~5×"), `he so phai la 5, nhan duoc: ${dai}`);
    assert.ok(/4\s*\/\s*6 ứng viên/.test(dai), `phai noi 4/6, nhan duoc: ${dai}`);
    // 🔴 MOC THOI GIAN: con so nay la KE HOACH NGAY BAY GIO, con o ung vien `c5`/`c6`
    // ben duoi in `skipped` cua LUOT CHAY DO. Do tren DB that: dai ghi "6/6 ung vien
    // chay duoc" trong khi o c6 cua ban dang xem ghi "engine chua duoc pull" — hai cau
    // dung o hai thoi diem khac nhau ma khong co gi noi ra. Tu nay dai phai noi ro moc.
    assert.ok(dai.includes("NGAY BÂY GIỜ"),
      `dai phai noi ro day la trang thai NGAY BAY GIO, nhan duoc: ${dai}`);
    const thieu = chu(container, '[data-testid="chimera-thieu"]');
    assert.ok(thieu.includes("qwen2.5-7b") && thieu.includes("hy-mt-1.5-7b"),
      `phai neu TEN engine thieu, nhan duoc: ${thieu}`);
    const uoc = chu(container, '[data-testid="chimera-uoc-luong"]');
    assert.ok(uoc.includes("15.0s"), `uoc luong 15000 ms = 15,0s, nhan duoc: ${uoc}`);
    assert.ok(uoc.includes("1280") && uoc.includes("550"), uoc);
    assert.ok(uoc.includes("#7"), `phai noi do tu dau, nhan duoc: ${uoc}`);
  });

  it("canh bao CHAT LUONG di kem canh bao chi phi", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
      chimera: true,
      chiPhi: CHI_PHI,
    }));
    const dai = chu(container, '[data-testid="chimera-chi-phi"]');
    assert.ok(
      dai.includes("CHÉP nguyên chữ nguồn"),
      `cau canh bao chat luong cua ung vien phai hien TRUOC khi bam: ${dai}`,
    );
  });

  it("chua do duoc uoc luong ⇒ noi ro VI SAO va LAM GI", () => {
    const chuaDo: ChimeraCost = {
      ...CHI_PHI,
      baseline: null,
      estimate: null,
      estimate_basis: "chưa đo được: chưa có bản dịch nào của kênh này chạy xong kèm thời gian THẬT",
      estimate_hint: "Chạy xong MỘT bản dịch bằng một engine Ollama rồi đọc lại cảnh báo này.",
    };
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
      chimera: true,
      chiPhi: chuaDo,
    }));
    const uoc = chu(container, '[data-testid="chimera-uoc-luong"]');
    assert.ok(uoc.includes("chưa đo được"), uoc);
    assert.ok(uoc.includes("engine Ollama"), `phai noi LAM GI, nhan duoc: ${uoc}`);
  });

  it("khong bat Chimera ⇒ KHONG co dai chi phi", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
      chimera: false,
      chiPhi: CHI_PHI,
    }));
    assert.equal(dem(container, '[data-testid="chimera-chi-phi"]'), 0);
  });

  // ------------------------------------------------- BON CUA SO UNG VIEN MOI DONG
  it("ban dich KHONG chimera ⇒ khong co ngan ung vien nao", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichThuong(1, ["a", "b"])],
    }));
    assert.equal(dem(container, '[data-testid="ung-vien-1"]'), 0);
    assert.equal(dem(container, '[data-testid="hop-nhat-1"]'), 0);
  });

  it("ban dich CO chimera ⇒ moi dong co ban HOP NHAT + N ung vien xep chong", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichChimera()],
      macDinhId: 9,
    }));
    const hopNhat = chu(container, '[data-testid="hop-nhat-1"]');
    assert.ok(hopNhat.includes("◆"), `ban hop nhat phai danh dau ◆: ${hopNhat}`);
    assert.ok(hopNhat.includes("4 ỨNG VIÊN"), `phai noi so ung vien THAT: ${hopNhat}`);
    assert.ok(hopNhat.includes("hyp 1"), `dong 1 co mo neo la c1 ⇒ hyp 1: ${hopNhat}`);
    assert.ok(hopNhat.includes("1.0s"), `1037 ms ⇒ 1,0s: ${hopNhat}`);

    assert.equal(
      dem(container, '[data-testid="ung-vien-1"] [data-testid^="uv-1-"]'), 4,
      "BON ung vien DA KHAI phai xep chong duoi ban hop nhat (ke ca cai khong chay)",
    );
    assert.equal(
      dem(container, '[data-testid="uv-1-c1"].is-chon'), 1,
      "ung vien duoc chon (mo neo) phai SANG HON ⇒ co lop `is-chon`",
    );
    assert.equal(
      dem(container, '[data-testid="uv-1-c2"].is-chon'), 0,
      "ung vien khong duoc chon KHONG duoc mang lop `is-chon`",
    );
    const uvC2 = chu(container, '[data-testid="uv-1-c2"]');
    assert.ok(uvC2.includes("第一句"), `ung vien phai hien CHU THAT cua no: ${uvC2}`);
    const uvC5 = chu(container, '[data-testid="uv-1-c5"]');
    assert.ok(
      uvC5.includes("model chưa được pull"),
      `ung vien khong chay duoc phai noi LY DO ngay tai dong: ${uvC5}`,
    );
  });

  it("dong 2 co mo neo KHAC ⇒ hyp 2, va ung vien c2 sang hon", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichChimera()],
      macDinhId: 9,
    }));
    assert.ok(chu(container, '[data-testid="hop-nhat-2"]').includes("hyp 2"));
    assert.equal(dem(container, '[data-testid="uv-2-c2"].is-chon'), 1);
    assert.equal(dem(container, '[data-testid="uv-2-c1"].is-chon'), 0);
  });

  it("doan ma luot PHA khong doi gi so voi mo neo ⇒ NOI RA", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichChimera()],
      macDinhId: 9,
    }));
    assert.equal(
      dem(container, '[data-testid="khong-doi-2"]'), 1,
      "doan 2 nam trong `merge.identical_segments` ⇒ phai co mot cau noi ra",
    );
    assert.equal(
      dem(container, '[data-testid="khong-doi-1"]'), 0,
      "doan 1 luot pha CO doi ⇒ khong duoc gan nhan 'khong doi'",
    );
  });

  it("doan LUI VE MO NEO ⇒ noi ra bang chu, khong im lang", () => {
    const ban = banDichChimera();
    ban.chimera!.merge.fallback_segments = [1];
    ban.chimera!.merge.fallback_reason = "lượt pha thất bại: thiếu segment [1]";
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [ban],
      macDinhId: 9,
    }));
    const dong = chu(container, '[data-testid="hop-nhat-1"]');
    assert.ok(/lùi về mỏ neo/i.test(dong), `phai noi da lui ve mo neo: ${dong}`);
  });

  // ------------------------------------------------------------------ regression
  it("van giu nguyen hai cot + cot CPS cua §4.3", () => {
    const { container } = render(taoPhanTu(CompareScreen, {
      transcript: nen[0],
      translations: [banDichChimera()],
      macDinhId: 9,
    }));
    assert.equal(dem(container, '[data-testid="col-left"]'), 2);
    assert.equal(dem(container, '[data-testid="col-right"]'), 2);
    assert.equal(dem(container, '[data-testid="col-cps"]'), 2);
  });
});
