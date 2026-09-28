/**
 * Test `<GlossaryScreen/>` THAT trong jsdom (spec UI §4.4 + tieu chi §12.3).
 *
 * VI SAO TEP NAY TON TAI, va vi sao no KHO: man Thuat ngu la man DUY NHAT trong
 * giai doan nay TU GOI API (khong nhan du lieu qua prop), nen so ban ghi bi anh
 * huong PHAI den tu ROUTE THAT. Mot stub o tang `endpoints` se XANH ke ca khi
 * `affectedPreview` ghep sai URL hoac route tra 405 — dung lop loi `I3` cua Task 8
 * (mot phep do tu thoa man). Vi vay tep nay DUNG BACKEND THAT + DB GIEO SCRATCH,
 * theo khuon `src/api/contract.test.ts`:
 *   - TU KHOI DONG backend (chi khi cong chua ai tra loi) va TU TAT;
 *   - chi tat pid cua CHINH NO, va CHUNG MINH cong thoi tra loi;
 *   - `EMPTY_DB_MSG` khi DB gieo rong: mot bai xanh-vi-khong-co-gi-de-do la im lang.
 *
 * HAI TANG DO HAI THU KHAC NHAU, va tep nay noi ro tung bai thuoc tang nao:
 *   - Nam bai dau di qua HTTP THAT (backend + DB gieo): bang thuật ngữ, chuoi
 *     `go -> affectedPreview -> so hien ra`, cau "chua duyet thi khong anh huong",
 *     hop dong THAM SO cua URL, va duong LƯU.
 *   - Bai cuoi chi DOC `app.css` (HINH THUC): mot test chi khang dinh `className`
 *     van XANH khi luat CSS bi xoa (ERRATA #15 muc 3, do duoc HAI CHIEU o Task 6).
 *
 * LUAT DOM (ERRATA #9 muc 1/6) — tep nay TU CHUA va khong dua vao thu tu:
 *   - MOI hook dat/tra global nam TRONG `describe()`: duoi `--test-isolation=none`,
 *     hook cap TEP bi node:test keo len GOC ca luot (moi `before` truoc MOI bai,
 *     moi `after` sau moi bai cua CA LUOT) — do bang dong ho chung, khong suy dien.
 *   - `setupDom`/`teardownDom` cua CHINH tep nay; khong gia dinh jsdom/backend cua
 *     tep khac con song. Phan harness backend bi LAP voi `contract.test.ts` la CO Y:
 *     luat "moi file DOM tu chua" khong cho phep dung chung trang thai.
 *   - `console.error`/`console.warn` bi TAM THAY de bat tieng on va duoc TRA LAI
 *     trong `after` (chung cung la global: ERRATA #7 muc 3).
 *   - MOI khang dinh tren `textContent`/`className`/`getAttribute`/SO LUONG, KHONG
 *     bao gio tren node DOM song: `assert.equal(<node>, null)` o nhanh DO do duoc
 *     218 697 ms roi OOM (ERRATA #14 muc 3 / #15 muc 1).
 *   - LUON chay TOAN BO `npm test`, khong chay le tep: suy giam do nhiem cheo chi
 *     lo ra o luot day du.
 *
 * ⚠️ KHONG co `@testing-library/user-event` va KHONG co `jest-dom` trong repo (do
 * `package.json`: chi `jsdom` + `@testing-library/react`) ⇒ dung `fireEvent` xuat tu
 * `@testing-library/react` va `node:assert/strict`.
 *
 * ⚠️ `npm run typecheck` KHONG kiem tep `.test.tsx` (bat bien: 0 tep `.test.` trong
 * `tsc --listFiles`) ⇒ loi kieu trong tep nay CHI lo ra luc chay, va `npm test` cua
 * luot day du VON DA `EXIT=1` (hai bai `EMPTY_DB_MSG` do chu y) nen EXIT KHONG phai
 * kenh thong tin (ERRATA #11 muc 1).
 *
 * ⚠️ CHUA AI NHIN THAY MAN HINH NAY TRONG TRINH DUYET THAT. jsdom KHONG phai trinh
 * duyet: KHONG layout, KHONG CSS that. ⇒ Tep nay do HANH VI (cai gi nam trong DOM,
 * lop nao, chu nao, con so nao), KHONG do HINH (bang rong bao nhieu, le amber co
 * nhin thay khong, chip `✕ trong` co dung mau khong).
 */
import { after, afterEach, before, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { setupDom, teardownDom } from "../../test/dom.ts";

/** Thu muc `backend/` — tinh tu CHINH tep nay, khong phu thuoc cwd cua nguoi chay. */
const BACKEND_DIR = fileURLToPath(new URL("../../../backend/", import.meta.url));
const VENV_PYTHON =
  process.platform === "win32"
    ? path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe")
    : path.join(BACKEND_DIR, ".venv", "bin", "python");

const PROBE_TIMEOUT_MS = 2_000;
const START_TIMEOUT_MS = 30_000;
const STOP_TIMEOUT_MS = 5_000;

/** Cong RIENG cua tep nay. 8620 = backend repo, 8621 = khoi route chi tiet cua contract. */
const SEED_PORT = 8623;

/**
 * Thong diep cho nguoi DOC, khong phai cho may: noi viec phai lam.
 *
 * DB gieo rong ⇒ moi bai duoi day khong do duoc gi, va mot bai xanh-vi-khong-co-gi
 * la im lang — dung thu spec §2 tu choi.
 */
const EMPTY_DB_MSG =
  "DB gieo rong: bai nay khong do duoc gi. Xem traceback cua buoc gieo ngay tren "
  + "dong nay (no chay bang venv cua backend, khong can model/GPU/mang).";

/**
 * Chuong trinh gieo DB scratch — chay bang venv cua backend, KHONG can model/GPU/mang.
 *
 * Gieo bang chinh `SqliteRepos` (khong viet SQL tay) de rang buoc schema duoc giu.
 * Bon du kien, moi cai phuc vu mot khang dinh:
 *   - transcript `1` (zh) CHUA `龙` ⇒ day la `affected` DUY NHAT khi thuat ngu `龙` doi;
 *   - HAI ban dich cua transcript `1` ⇒ phan biet "so BAN GHI" (1) voi "so BAN DICH"
 *     (2): route tra id TRANSCRIPT, va bai test ghim dung DON VI do;
 *   - transcript `2` (zh) chua `chó`, KHONG chua `mèo` ⇒ ve thu hai cua phep do so
 *     (thuat ngu khong xuat hien o dau ⇒ 0);
 *   - thuat ngu `龙 -> rồng` DANG DUYET (va `猫 -> ""` CHUA duyet, de bai bang co ca
 *     hang cho duyet lan chip `✕ trong`).
 */
const SEED_PY = `
import sys

backend, db = sys.argv[1], sys.argv[2]
sys.path.insert(0, backend)

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.models import Segment

repos = SqliteRepos(db, clock=SystemClock())
repos.init_schema()
source_id = repos.add_source(kind="file", origin="seed.wav", media_path="seed.wav",
                             lang="zh", duration=2.0)
tid = repos.add_transcript(source_id=source_id, engine="fw-small", lang="zh",
                           segments=[Segment(i=1, start=0.0, end=2.0, text="龙")])
repos.add_transcript(source_id=source_id, engine="fw-small", lang="zh",
                     segments=[Segment(i=1, start=0.0, end=2.0, text="chó")])
for k in range(2):
    repos.add_translation(transcript_id=tid, transcript_version=1, engine="opus-mt",
                          target_lang="vi", prompt_version="opus-p1", status="done",
                          segments=[Segment(i=1, start=0.0, end=2.0, text="rong %d" % k)])
repos.upsert_term(lang="zh", term="龙", translation="rồng", note=None, approved=True)
repos.upsert_term(lang="zh", term="猫", translation="", note=None, approved=False)
print("[glossary-test] da gieo transcript", tid, "thuat ngu", len(repos.list_terms(lang="zh")))
`;

const SEED_ORIGIN = `http://127.0.0.1:${SEED_PORT}`;

const consoleGoc = { error: console.error, warn: console.warn };
const tiengOn: string[] = [];

let render: (ui: unknown) => { container: HTMLElement; unmount: () => void };
let fireEvent: { click: (el: Element) => void; change: (el: Element, init: unknown) => void };
let waitFor: (cb: () => void, options?: { timeout?: number; interval?: number }) => Promise<void>;
let act: (cb: () => Promise<void>) => Promise<void>;
let cleanup: () => void;
let taoPhanTu: (type: unknown, props?: unknown) => unknown;
let GlossaryScreen: () => unknown;
let endpoints: typeof import("../api/endpoints.ts").endpoints;

/** `textContent` cua phan tu DAU TIEN khop `chon` — khong hoi ca DOM. */
function chu(goc: HTMLElement, chon: string): string {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.textContent ?? "";
}

/** So phan tu khop `chon` — DEM, khong so sanh NODE (ERRATA #14 muc 3). */
function dem(goc: HTMLElement, chon: string): number {
  return goc.querySelectorAll(chon).length;
}

/** Thuoc tinh cua phan tu DAU TIEN khop `chon` (`null` neu khong co). */
function thuocTinh(goc: HTMLElement, chon: string, ten: string): string | null {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay phan tu "${chon}" trong DOM`);
  return el.getAttribute(ten);
}

/** Cho toi khi `chon` ton tai VA `dieuKien(text)` dung; noi ro DOM that khi hong. */
async function choChu(
  goc: HTMLElement,
  chon: string,
  dieuKien: (text: string) => boolean,
  moTa: string,
): Promise<string> {
  let cuoi = "";
  await waitFor(
    () => {
      const el = goc.querySelector(chon);
      const text = el === null ? "" : el.textContent ?? "";
      assert.ok(el !== null && dieuKien(text), `${moTa}; do duoc: ${JSON.stringify(text)}`);
      cuoi = text;
    },
    { timeout: 8000, interval: 25 },
  );
  return cuoi;
}

/** Go mot gia tri vao o nhap (mot lan `change`, khong phai tung ky tu). */
function go(goc: HTMLElement, chon: string, value: string): void {
  const el = goc.querySelector(chon);
  assert.ok(el !== null, `khong thay o nhap "${chon}"`);
  fireEvent.change(el, { target: { value } });
}

describe("GlossaryScreen: §4.4 tab THUAT NGU tren BACKEND THAT (DB gieo, cong rieng)", () => {
  /** Thu muc scratch (ngoai repo) va pid backend cua CHINH khoi nay. */
  let seedDir: string | null = null;
  let seedPid: number | null = null;

  async function seedBackendIsUp(): Promise<boolean> {
    try {
      const response = await fetch(`${SEED_ORIGIN}/api/status`, {
        signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /** Tat DUNG cay tien trinh minh spawn; khong co gi cua minh ⇒ no-op. */
  function stopSeedBackend(): void {
    if (seedPid === null) return;
    const pid = seedPid;
    seedPid = null;
    try {
      process.kill(pid);
    } catch {
      // Da chet roi — dich cua ham la "khong con song", khong phai "vua giet".
    }
    try {
      spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
    } catch {
      // taskkill thieu (khong phai Windows) — `process.kill` o tren da lo phan do.
    }
  }

  before(async () => {
    seedDir = mkdtempSync(path.join(tmpdir(), "phude-glossary-"));
    const dbPath = path.join(seedDir, "app.db");
    const seedScript = path.join(seedDir, "seed.py");
    writeFileSync(seedScript, SEED_PY, "utf8");

    // `stdio: "inherit"` chu KHONG `"pipe"`: trong sandbox nay `pipe` chet EPERM, va
    // mot luot spawn hong se trong y nhu "khong co du lieu" (ERRATA #17 muc 1).
    const seeded = spawnSync(VENV_PYTHON, [seedScript, BACKEND_DIR, dbPath], {
      cwd: BACKEND_DIR,
      stdio: "inherit",
      windowsHide: true,
    });
    assert.equal(seeded.status, 0, `gieo DB scratch that bai. ${EMPTY_DB_MSG}`);

    let spawnError: string | null = null;
    const child = spawn(VENV_PYTHON, ["run_api.py"], {
      cwd: BACKEND_DIR,
      stdio: "ignore",
      windowsHide: true,
      env: {
        ...process.env,
        PHUDE_DB: dbPath,
        PHUDE_DATA: path.join(seedDir, "data"),
        PHUDE_PORT: String(SEED_PORT),
      },
    });
    child.on("error", (error: Error) => {
      spawnError = error.message;
    });
    // `unref()`: handle cua tien trinh con khong duoc giu cho event loop song.
    child.unref();
    seedPid = typeof child.pid === "number" ? child.pid : null;

    const deadline = Date.now() + START_TIMEOUT_MS;
    let up = false;
    while (Date.now() < deadline) {
      if (await seedBackendIsUp()) {
        up = true;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    if (!up) {
      stopSeedBackend();
      assert.fail(
        `backend ${SEED_PORT} (DB gieo) khong len sau ${START_TIMEOUT_MS / 1000}s; loi spawn: `
        + `${spawnError === null ? "khong ro" : spawnError}. Chay tay: PHUDE_DB=<scratch>/app.db `
        + `PHUDE_PORT=${SEED_PORT} "${VENV_PYTHON}" run_api.py (cwd=${BACKEND_DIR}).`,
      );
    }

    // Chuan hoa TRUOC khi cai: khong dua vao viec tep khac da tra global hay chua.
    teardownDom();
    // Origin THAT: `client.ts` goi `fetch("/api/…")` TUONG DOI, va cau noi cua
    // `test/dom.ts` bien no thanh URL tuyet doi toi backend vua dung.
    setupDom(SEED_ORIGIN);

    const rtl: any = await import("@testing-library/react");
    const api = rtl.render === undefined ? rtl.default : rtl;
    render = api.render;
    fireEvent = api.fireEvent;
    waitFor = api.waitFor;
    act = api.act;
    cleanup = api.cleanup;
    const reactModule: any = await import("react");
    const react = reactModule.createElement === undefined ? reactModule.default : reactModule;
    taoPhanTu = react.createElement;
    const man: any = await import("./GlossaryScreen.tsx");
    GlossaryScreen = man.GlossaryScreen;
    const ep: any = await import("../api/endpoints.ts");
    endpoints = ep.endpoints === undefined ? ep : ep.endpoints;

    console.error = (...args: unknown[]): void => {
      tiengOn.push(`error: ${args.map((a) => String(a)).join(" ")}`);
    };
    console.warn = (...args: unknown[]): void => {
      tiengOn.push(`warn: ${args.map((a) => String(a)).join(" ")}`);
    };
  });

  beforeEach(() => {
    tiengOn.length = 0;
  });

  afterEach(() => {
    cleanup();
  });

  after(async () => {
    console.error = consoleGoc.error;
    console.warn = consoleGoc.warn;
    const killed = seedPid;
    stopSeedBackend();
    if (killed !== null) {
      // Phai CHUNG MINH da tat, khong chi goi kill roi tin (cung luat voi contract.test.ts).
      const deadline = Date.now() + STOP_TIMEOUT_MS;
      let stopped = false;
      while (Date.now() < deadline) {
        if (!(await seedBackendIsUp())) {
          stopped = true;
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
      if (!stopped) {
        assert.fail(`backend ${SEED_PORT} (pid ${killed}) van song sau khi kill — con mo coi`);
      }
    }
    teardownDom();
    if (seedDir !== null) {
      try {
        rmSync(seedDir, { recursive: true, force: true });
      } catch {
        // Windows co the giu lock `.db` them mot nhip; thu muc nam trong TEMP cua HDH,
        // ngoai repo, nen mot lan don that bai khong lam ban `git status`.
      }
    }
  });

  // -------------------------------------------------------------------------
  // TANG HTTP THAT: bang thuật ngữ den tu `listTerms`
  // -------------------------------------------------------------------------

  it("BANG: thuật ngữ den tu ROUTE THAT, hang cho duyet co le amber va chip `✕ trong`", async () => {
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));

    // Hai hang den tu `GET /api/glossary` cua DB gieo — khong phai tu mot fixture
    // trong tep test. Neu `listTerms` ghep sai URL thi bai nay do ngay.
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("龙") && t.includes("rồng"),
      "bang khong hien thuat ngu cua DB gieo");
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("猫"),
      "bang thieu hang thu hai cua DB gieo");

    // Thanh dem cua §4.4: `5 thuật ngữ · 4 đã duyệt` — hai con so nay dem tu du lieu
    // vua nap, nen chung phai khop DB gieo (2 thuat ngu, 1 da duyet).
    const dongDem = chu(container, '[data-testid="dem"]');
    assert.match(dongDem, /\b2\b/, `thanh dem phai noi so thuat ngu, dang co: ${dongDem}`);
    assert.match(dongDem, /\b1\b/, `thanh dem phai noi so DA DUYET, dang co: ${dongDem}`);
    assert.match(dongDem, /đã duyệt/i, `thanh dem phai noi ro "da duyet", dang co: ${dongDem}`);

    // Hang CHUA duyet: le trai amber la HINH THUC (§4.4), nhung lop phai CO that tren
    // dung hang — va luat CSS cho lop do duoc ghim o bai cuoi tep.
    const hangChoDuyet = container.querySelector('[data-testid="hang-2"]');
    assert.ok(hangChoDuyet !== null, "phai co hang cho duyet (thuat ngu chua duyet)");
    assert.equal(
      (hangChoDuyet as HTMLElement).className.includes("is-cho-duyet"),
      true,
      "hang CHUA duyet phai mang lop `is-cho-duyet`",
    );
    const hangDaDuyet = container.querySelector('[data-testid="hang-1"]');
    assert.ok(hangDaDuyet !== null, "phai co hang da duyet");
    assert.equal(
      (hangDaDuyet as HTMLElement).className.includes("is-cho-duyet"),
      false,
      "hang DA duyet khong duoc mang lop `is-cho-duyet` — mot lop luon hien la mat tin hieu",
    );

    // §4.4: "Hang chua co ban dich co chip `✕ trong` mau loi." Thuat ngu `猫` co
    // `translation` RONG trong DB gieo, nen chip phai hien o DUNG hang do.
    const chip = chu(container, '[data-testid="trong-2"]');
    assert.match(chip, /trống/i, `chip cua hang trong phai noi "trong", dang co: ${chip}`);
    assert.equal(dem(container, '[data-testid="trong-1"]'), 0,
      "hang CO ban dich khong duoc mang chip `trong`");

    // Nhan nam TREN o nhap (spec §4.4/checklist): `<label for>` tro dung id cua input.
    for (const [nhan, id] of [["thuật ngữ", "gl-term"], ["bản dịch", "gl-translation"],
      ["đã duyệt", "gl-approved"]] as const) {
      const nhanEl = [...container.querySelectorAll("label")].find(
        (l) => (l.textContent ?? "").toLowerCase().includes(nhan) && l.getAttribute("for") === id,
      );
      assert.ok(nhanEl !== undefined, `thieu <label for="${id}"> cho "${nhan}"`);
      assert.equal(container.querySelectorAll(`#${id}`).length, 1,
        `label for="${id}" nhung khong co dung mot phan tu id do`);
    }

    assert.deepEqual(tiengOn, [], "render man Thuat ngu khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // TANG HTTP THAT: chuoi `go -> affectedPreview -> so hien ra` (§12.3)
  // -------------------------------------------------------------------------

  it("XEM TRUOC: go thuat ngu ⇒ so anh huong den tu ROUTE THAT (va dung DON VI)", async () => {
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("龙"), "bang chua nap xong");

    // `approved` MAC DINH la bat: nguoi dung go mot thuat ngu + ban dich la de DUNG no.
    const daDuyet = container.querySelector('[data-testid="o-da-duyet"]') as HTMLInputElement;
    assert.equal(daDuyet.checked, true, "o 'da duyet' phai bat san");

    go(container, '[data-testid="o-thuat-ngu"]', "龙");
    go(container, '[data-testid="o-ban-dich"]', "long");

    // So nay PHAI den tu route: DB gieo co DUNG MOT transcript chua `龙`, va HAI ban
    // dich cua no. Mot client tu dem ban dich se ra 2; mot stub o tang `endpoints` se
    // xanh ke ca khi URL sai. Khang dinh o day phan biet duoc ca hai.
    const xemTruoc = await choChu(
      container,
      '[data-testid="affected-preview"]',
      (t) => /\b1\b/.test(t) && /bản ghi/i.test(t),
      "so anh huong chua hien ra tu route",
    );
    assert.doesNotMatch(xemTruoc, /\b2\b/,
      `route tra id TRANSCRIPT, khong phai so BAN DICH: dang co ${xemTruoc}`);
    assert.match(xemTruoc, /ảnh hưởng|đánh dấu lỗi thời/i,
      `phai noi ro day la anh huong, dang co: ${xemTruoc}`);

    // VE THU HAI cua phep do: mot thuat ngu KHONG xuat hien o dau ⇒ 0. Khong co ve
    // nay thi mot con so CUNG nhac dinh trong ma client cung di qua xanh.
    go(container, '[data-testid="o-thuat-ngu"]', "mèo");
    const khongDau = await choChu(
      container,
      '[data-testid="affected-preview"]',
      (t) => /\b0\b/.test(t),
      "thuat ngu khong xuat hien o dau phai cho ra 0",
    );
    assert.doesNotMatch(khongDau, /\b1\b/,
      `0 khong duoc lan voi 1: dang co ${khongDau}`);

    assert.deepEqual(tiengOn, [], "go trong form khong duoc sinh tieng on console");
    unmount();
  });

  it("CHUA DUYET: noi ro bang CHU nguoi dung doc duoc la khong anh huong gi", async () => {
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("龙"), "bang chua nap xong");

    go(container, '[data-testid="o-thuat-ngu"]', "龙");
    go(container, '[data-testid="o-ban-dich"]', "long");
    await choChu(container, '[data-testid="affected-preview"]', (t) => /\b1\b/.test(t),
      "chua do duoc so anh huong truoc khi tat 'da duyet'");

    // Tat "da duyet" ⇒ cau nay PHAI la CHU, khong phai chi mot mau khac: mot test ghim
    // lop CSS khong chung minh nguoi dung doc duoc gi (ERRATA #15 muc 3).
    fireEvent.click(container.querySelector('[data-testid="o-da-duyet"]') as Element);

    const cau = await choChu(
      container,
      '[data-testid="affected-preview"]',
      (t) => /không ảnh hưởng gì/i.test(t),
      "chua duyet thi phai NOI RO la khong anh huong gi",
    );
    assert.match(cau, /chưa duyệt/i,
      `cau phai noi ro LY DO la "chua duyet", dang co: ${cau}`);
    assert.doesNotMatch(cau, /\b1\b/,
      `chua duyet thi khong duoc hien mot con so anh huong: dang co ${cau}`);

    assert.deepEqual(tiengOn, [], "doi trang thai duyet khong duoc sinh tieng on console");
    unmount();
  });

  it("HOP DONG THAM SO: URL do `affectedPreview` sinh ra duoc ROUTE THAT chap nhan", async () => {
    // ⚠️ `endpoints.affectedPreview` la ham VIET TAY o client: no co the ghep sai ten
    // tham so (`approved` → `duyet`) ma MOI bai khac van xanh neu chung chi doc ket qua
    // da duoc lam sach. Bai nay BAT chinh URL no sinh ra roi goi lai THAT:
    //   - sai ten tham so BAT BUOC ⇒ 422;
    //   - sai ten `approved` ⇒ route roi ve mac dinh `False` ⇒ ket qua RONG.
    // Day dung lop loi `I3` cua Task 8 (so `href` voi chinh ham la CHUA DU).
    const that = globalThis.fetch;
    let batDuoc = "";
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      batDuoc = String(input);
      return that(input, init);
    }) as typeof fetch;

    let coAnhHuong: { affected: number[] };
    try {
      coAnhHuong = await endpoints.affectedPreview({
        lang: "zh", term: "龙", translation: "long", approved: true,
      });
    } finally {
      globalThis.fetch = that;
    }

    assert.match(batDuoc, /\/api\/glossary\/affected\?/,
      `ham phai goi route /api/glossary/affected, dang goi: ${batDuoc}`);

    // Chinh URL do, goi lai THAT: 200 (khong 422/405) VA dung ngu nghia.
    const lai = await fetch(batDuoc);
    assert.equal(lai.status, 200,
      `route that phai CHAP NHAN URL do ham sinh ra, nhan HTTP ${lai.status}: ${batDuoc}`);
    const than = (await lai.json()) as { affected: number[] };
    assert.deepEqual(than, coAnhHuong, "goi lai chinh URL do phai cho cung ket qua");

    assert.notEqual(coAnhHuong.affected.length, 0,
      "`approved=true` tren mot thuat ngu DANG DUYET va co transcript chua no PHAI bao anh huong: "
      + `nhan ${JSON.stringify(coAnhHuong)} (rong nghia la ten tham so "approved" khong toi duoc route)`);

    // HAI VE CON LAI co dinh CUNG `term` + CUNG `translation`, chi khac co `approved`
    // ⇒ chung CON LAP ten tham so `approved` khoi moi thu khac:
    //   - `approved=true`  ⇒ khong doi gi (hang dang duyet, giu nguyen) ⇒ rong;
    //   - `approved=false` ⇒ BO DUYET mot rang buoc ⇒ ban dich cu sai ⇒ [1].
    // Mot client ghep sai ten (`approved` → `duyet`) lam CA HAI roi ve mac dinh `False`:
    // ve thu nhat thanh [1] ⇒ bai nay DO. Do la lop loi `I3` ma bai nay sinh ra de bat.
    const giuNguyen = await endpoints.affectedPreview({
      lang: "zh", term: "龙", translation: "rồng", approved: true,
    });
    assert.deepEqual(giuNguyen.affected, [],
      "`approved=true` voi dung cap (term, translation) dang luu ⇒ khong doi gi ⇒ phai rong");

    const boDuyet = await endpoints.affectedPreview({
      lang: "zh", term: "龙", translation: "rồng", approved: false,
    });
    assert.deepEqual(boDuyet.affected, coAnhHuong.affected,
      "`approved=false` la BO DUYET mot rang buoc DANG co ⇒ phai bao anh huong "
      + `(nhan ${JSON.stringify(boDuyet)}): co "approved" duoc phan tich THAT su`);

    assert.deepEqual(tiengOn, [], "goi preview truc tiep khong duoc sinh tieng on console");
  });

  // -------------------------------------------------------------------------
  // TANG HTTP THAT: duong LƯU — va rang buoc "client KHONG goi gi de tang version"
  // -------------------------------------------------------------------------

  it("LUU: POST tu tang version DUNG MOT lan, client khong goi gi them, bang nap lai", async () => {
    const truoc = (await (await fetch("/api/glossary/version")).json()) as {
      glossary_version: number;
    };

    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("rồng"), "bang chua nap xong");

    go(container, '[data-testid="o-thuat-ngu"]', "龙");
    go(container, '[data-testid="o-ban-dich"]', "long");
    await choChu(container, '[data-testid="affected-preview"]', (t) => /\b1\b/.test(t),
      "chua do duoc so anh huong truoc khi luu");

    // Cửa sổ `act` phải MỞ suốt lời gọi ghi: chuỗi `.then` của POST cập nhật state
    // SAU khi `fireEvent.click` trả về, nên không giữ `act` thì React báo
    // "An update to GlossaryScreen inside a test was not wrapped in act(...)" — một
    // tiếng ồn của MÔI TRƯỜNG TEST, không phải lỗi sản phẩm, nhưng nó làm phép đo
    // "không có tiếng ồn console" mất nghĩa.
    await act(async () => {
      fireEvent.click(container.querySelector('[data-testid="luu"]') as Element);
      const het = Date.now() + 8000;
      while (Date.now() < het && container.querySelector('[data-testid="da-luu"]') === null) {
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
    });

    // Câu xác nhận phải đến từ THÂN response của lần ghi (nó mang `affected`), không
    // phải từ một lời gọi xem trước thứ hai.
    const daLuu = await choChu(container, '[data-testid="da-luu"]', (t) => /đã lưu/i.test(t),
      "bam Luu khong thay cau xac nhan");
    assert.match(daLuu, /\b1\b/, `thong bao phai mang so anh huong cua lan ghi: ${daLuu}`);

    // Mang luoi THAT cua rang buoc "POST da tu tang version ben trong `upsert_term`":
    // sau DUNG MOT lan bam Luu, version phai +1. Neu client goi them mot duong bump nao
    // khac thi con so nay thanh +2 — va moi ban dich se trong "loi thoi" som hon thuc te.
    const sau = (await (await fetch("/api/glossary/version")).json()) as {
      glossary_version: number;
    };
    assert.equal(sau.glossary_version, truoc.glossary_version + 1,
      `mot lan Luu phai tang version DUNG MOT lan: ${truoc.glossary_version} -> ${sau.glossary_version}`);

    // Bang phai NAP LAI tu route: ban dich vua sua hien ra.
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("long"),
      "sau khi luu, bang khong nap lai du lieu tu route");

    assert.deepEqual(tiengOn, [], "luu thuat ngu khong duoc sinh tieng on console");
    unmount();
  });

  // -------------------------------------------------------------------------
  // TANG HTTP THAT: lane LOI — mot server THAT tra 500
  // -------------------------------------------------------------------------

  it("LOI NAP: loi API phai HIEN RA cho nguoi doc, khong im lang", async () => {
    // Lane nay KHONG the di qua backend cua DB gieo: no can mot loi HTTP thuc su, va
    // khong route nao cua backend tra 500 khi duoc hoi dung. Nen o day la mot server
    // `node:http` THAT tra 500 kem `detail` dung hinh dang FastAPI — request van la HTTP
    // that, chi co SERVER la khac. (Con so anh huong thi KHONG bao gio di qua lane nay:
    // no luon la route that cua backend o tren.)
    //
    // Bai nay khong phai chuyen hinh thuc: nhanh loi la nhanh DUY NHAT khong di qua
    // duong thanh cong, va mot `ReferenceError` trong chinh nhanh do (ten setter sai)
    // KHONG lam bai nao khac do — `npm run typecheck` moi bat duoc no.
    const hong: Server = createServer((_req, res) => {
      res.writeHead(500, { "content-type": "application/json" });
      res.end(JSON.stringify({ detail: "bảng thuật ngữ hỏng (cố ý)" }));
    });
    await new Promise<void>((resolve) => hong.listen(0, "127.0.0.1", () => resolve()));
    const { port } = hong.address() as AddressInfo;

    try {
      // Origin KHAC ⇒ `setupDom` dung lai cau noi (khong bo qua im lang — ERRATA #8 muc 2).
      setupDom(`http://127.0.0.1:${port}`);
      const { container, unmount } = render(taoPhanTu(GlossaryScreen));

      const loi = await choChu(
        container,
        '[data-testid="loi-nap"]',
        (t) => /hỏng \(cố ý\)/.test(t),
        "loi 500 cua server khong hien ra DOM",
      );
      // `ApiError.message` = "<status>: <detail>" ⇒ ca ma HTTP lan cau tieng Viet cua
      // backend deu phai co mat, khong bi nuot thanh mot cau "loi" chung chung.
      assert.match(loi, /500/, `loi phai mang ca ma HTTP: ${loi}`);
      // Va bang phai NOI THAT la khong co du lieu, khong duoc im lang voi bang rong.
      assert.match(chu(container, '[data-testid="dem"]'), /\b0\b/,
        "khong doc duoc bang thi thanh dem phai noi 0, khong duoc de nguyen");
      unmount();
    } finally {
      // `closeAllConnections` truoc `close`: `fetch` cua Node giu ket noi keep-alive,
      // nen chi goi `close()` la cho vo han.
      hong.closeAllConnections();
      await new Promise<void>((resolve) => hong.close(() => resolve()));
      // Tra cau noi ve backend cua DB gieo cho bai cuoi (bai CSS khong cham DOM, nhung
      // de nguyen mot origin da chet la thu se cam bay nguoi sau).
      setupDom(SEED_ORIGIN);
    }
  });

  // -------------------------------------------------------------------------
  // TANG HINH THUC: ghim LUAT CSS, khong chi ghim ten lop (ERRATA #15 muc 3)
  // -------------------------------------------------------------------------

  it("HINH THUC: LUAT CSS cua man Thuat ngu CO THAT trong `app.css`, moi token deu co dinh nghia", () => {
    // DO DUOC HAI CHIEU o Task 6: mot test chi khang dinh `className` VAN XANH khi luat
    // CSS bi xoa. Cach re nhat de ghim luat: DOC tep CSS.
    const appCss = readFileSync(new URL("../styles/app.css", import.meta.url), "utf8");
    const tokensCss = readFileSync(new URL("../styles/tokens.css", import.meta.url), "utf8");

    // Moc phai khop TUNG KY TU voi chu thich trong `app.css` (co dau, khong phai ASCII):
    // mot moc sai lam bai nay bao "thieu khoi luat" trong khi khoi luat CO that.
    const moc = "§4.4 Màn THUẬT NGỮ (Task 9)";
    const viTri = appCss.indexOf(moc);
    assert.ok(viTri > 0, "app.css phai co KHOI LUAT cua man Thuat ngu, khong chi co class trong TSX");
    const khoi = appCss.slice(viTri);

    for (const chon of [".gl {", ".gl__bang {", ".gl__hang {", ".gl__nhan {", ".gl__xem-truoc {"]) {
      assert.ok(khoi.includes(chon), `app.css thieu luat "${chon}"`);
    }

    // Bon luat THAT, khong phai ten lop:
    assert.match(khoi, /\.gl \{[^}]*display: grid/,
      "man Thuat ngu phai la mot LUOI (bang + form), khong phai khoi chu chay");
    assert.match(khoi, /\.gl__hang\.is-cho-duyet \{[^}]*border-left-color: var\(--signal\)/,
      "hang CHUA duyet phai co LUAT VE THAT (le amber §4.4), khong chi co ten lop `is-cho-duyet`");
    assert.match(khoi, /\.gl__trong \{[^}]*var\(--fault\)/,
      "chip `✕ trong` phai dung mau LOI `--fault` (§4.4), khong chi la mot chu thuong");
    assert.match(khoi, /\.gl__nhan \{[^}]*display: block/,
      "nhan phai nam TREN o nhap ⇒ no phai la mot khoi rieng, khong nam cung dong");

    // Token nao khoi nay dung thi phai co dinh nghia THAT trong `tokens.css`.
    const dung = [...new Set([...khoi.matchAll(/var\((--[a-z0-9-]+)\)/g)].map((m) => m[1] ?? ""))];
    assert.ok(dung.length >= 4, `khoi Thuat ngu phai dung token that, do duoc ${dung.length}`);
    for (const token of dung) {
      assert.ok(tokensCss.includes(`${token}:`),
        `token ${token} duoc dung nhung KHONG dinh nghia trong tokens.css`);
    }
  });
});
