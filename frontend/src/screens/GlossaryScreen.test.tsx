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
 * Sau du kien, moi cai phuc vu mot khang dinh:
 *   - transcript `1` (zh) CHUA `龙` ⇒ day la `affected` DUY NHAT khi thuat ngu `龙` doi;
 *   - HAI ban dich cua transcript `1` ⇒ phan biet "so BAN GHI" (1) voi "so BAN DICH"
 *     (2): route tra id TRANSCRIPT, va bai test ghim dung DON VI do;
 *   - transcript `2` (zh) chua `chó`, KHONG chua `mèo` ⇒ ve thu hai cua phep do so
 *     (thuat ngu khong xuat hien o dau ⇒ 0);
 *   - transcript `3` (zh) chua `犬`, va `犬 -> chó` DANG DUYET ⇒ mot hang DANG duyet
 *     RIENG cho bai `I2` GHI vao (bai do bo duyet mot hang that su). No phai la mot hang
 *     KHONG bai nao khac dung: moi bai trong tep dung CHUNG mot DB gieo, nen mot bai ghi
 *     de len du lieu ma bai khac dang khang dinh la mot phu thuoc THU TU — da do duoc
 *     HAI LAN trong tep nay (bai `LUU` doi `龙`, va ban nhap cua `I2` lam `HOP DONG THAM
 *     SO` + `BO DUYET qua FORM` do);
 *   - transcript `4` (zh) chua `馬`, va `馬 -> ngựa` **CHUA DUYET** ⇒ bai `I1b` dung no de
 *     lam cho ANH CHUP trong bo nho tro nen CU mot cach TAT DINH (man da nap xong, roi
 *     bai test tu DUYET `馬` qua route that; sau do `approved=false` trong form la mot lan
 *     BO DUYET ma anh chup cu khong biet) — do la ca duy nhat phan biet duoc "con so cua
 *     route THANG" voi "cau giai thich doan truoc THANG";
 *   - thuat ngu `龙 -> rồng` DANG DUYET (va `猫 -> ""` CHUA duyet, de bai bang co ca
 *     hang cho duyet lan chip `✕ trong`);
 *   - `鳥 -> chim` DANG DUYET va KHONG xuat hien o transcript nao ⇒ bai `I1c`: bo duyet
 *     mot hang DANG duyet ma khong ai dung phai hien CON SO `0`, KHONG duoc roi ve cau
 *     "ban nhap khong di vao prompt" (cau do NOI SAI ve trang thai cua hang);
 *   - `魚 -> cá` **CHUA duyet** va khong o transcript nao ⇒ bai `I1d` (anh chup CU + con so
 *     `0`): bai test tu duyet no qua route that SAU khi man da nap, nen LY DO hien ra phai
 *     theo may chu (`bo duyet`) chu khong theo anh chup (`ban nhap`). La hang RIENG vi `猫`
 *     (cung chua duyet, cung khong o transcript nao) da thuoc bai `BANG`.
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
repos.add_transcript(source_id=source_id, engine="fw-small", lang="zh",
                     segments=[Segment(i=1, start=0.0, end=2.0, text="犬")])
repos.add_transcript(source_id=source_id, engine="fw-small", lang="zh",
                     segments=[Segment(i=1, start=0.0, end=2.0, text="馬")])
for k in range(2):
    repos.add_translation(transcript_id=tid, transcript_version=1, engine="opus-mt",
                          target_lang="vi", prompt_version="opus-p1", status="done",
                          segments=[Segment(i=1, start=0.0, end=2.0, text="rong %d" % k)])
repos.upsert_term(lang="zh", term="龙", translation="rồng", note=None, approved=True)
repos.upsert_term(lang="zh", term="猫", translation="", note=None, approved=False)
repos.upsert_term(lang="zh", term="犬", translation="chó", note=None, approved=True)
repos.upsert_term(lang="zh", term="馬", translation="ngựa", note=None, approved=False)
repos.upsert_term(lang="zh", term="鳥", translation="chim", note=None, approved=True)
repos.upsert_term(lang="zh", term="魚", translation="cá", note=None, approved=False)
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

/**
 * Con so DAU TIEN trong mot o, doc tu `textContent` (khong bao gio tu node DOM song).
 *
 * Dung cho cac phep so "hai con so phai BANG nhau" (so xem truoc vs so lan ghi): parse
 * `textContent` la cach duy nhat doc duoc con so ma khong cham vao node.
 */
function soTrong(goc: HTMLElement, chon = '[data-testid="affected-preview"]'): number {
  const text = chu(goc, chon);
  const khop = /(\d+)/.exec(text);
  assert.ok(khop !== null, `khong doc duoc con so nao trong: ${JSON.stringify(text)}`);
  return Number(khop[1]);
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

    // Thanh dem cua §4.4 (`5 thuật ngữ · 4 đã duyệt`) phai khop DU LIEU CUA ROUTE —
    // va hai con so ky vong duoc DOC LAI tu route ngay tai day, khong phai hang so
    // trong test: bai LUU o duoi ghi THEM mot thuat ngu, va mot bai khang dinh mot
    // con so cung se phu thuoc vao viec bai nao chay truoc (do duoc: ban nhap dau cua
    // bai "BO DUYET qua FORM" do dung vi bai LUU da chay truoc no).
    const rows = (await (await fetch("/api/glossary?lang=zh")).json()) as {
      approved: boolean;
    }[];
    assert.ok(rows.length >= 2, `${EMPTY_DB_MSG} (doc duoc ${rows.length} hang)`);
    const soDuyet = rows.filter((r) => r.approved).length;
    const dongDem = chu(container, '[data-testid="dem"]');
    assert.match(dongDem, new RegExp(`\\b${rows.length}\\b`),
      `thanh dem phai noi so thuat ngu cua route, dang co: ${dongDem}`);
    assert.match(dongDem, new RegExp(`\\b${soDuyet}\\b`),
      `thanh dem phai noi so DA DUYET cua route, dang co: ${dongDem}`);
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

  it("CHUA DUYET: nhap MOI (term chua co trong DB) thi noi ro la khong anh huong gi", async () => {
    // ⚠️ BAN DAU BAI NAY DUNG BO BA (`term=龙`, `translation=long`, `approved=false`) VA
    // GHIM CAU "khong anh huong gi" — mot LOI NOI SAI duoc ghim bang test. Do lai tren
    // route that (cong 8624, DB gieo):
    //   A) GET /api/glossary/affected?lang=zh&term=龙&translation=long&approved=false
    //      -> HTTP 200 BODY: {"affected":[1]}
    // `龙` DANG duoc duyet va transcript `1` chua no ⇒ bo tick o do la BO DUYET mot rang
    // buoc ⇒ CO anh huong. Cau "khong anh huong gi" chi dung cho mot NHAP MOI, nen bai nay
    // nay do bang `mèo`: khong co trong glossary VA khong co trong transcript nao
    // (`lang=zh&term=mèo&translation=cat&approved=false` -> `{"affected":[]}`, do o dong D).
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("龙"), "bang chua nap xong");

    go(container, '[data-testid="o-thuat-ngu"]', "mèo");
    go(container, '[data-testid="o-ban-dich"]', "cat");
    // Truoc khi tat: route tra RONG cho bo ba nay (nhap moi + approved=true cung rong vi
    // `mèo` khong xuat hien o dau) ⇒ day khong phai mot con so bi doi tick lam mat.
    await choChu(container, '[data-testid="affected-preview"]', (t) => /\b0\b/.test(t),
      "nhap moi khong xuat hien o dau phai cho ra 0");

    // Tat "da duyet" ⇒ cau nay PHAI la CHU, khong phai chi mot mau khac: mot test ghim
    // lop CSS khong chung minh nguoi dung doc duoc gi (ERRATA #15 muc 3).
    fireEvent.click(container.querySelector('[data-testid="o-da-duyet"]') as Element);

    const cau = await choChu(
      container,
      '[data-testid="affected-preview"]',
      (t) => /không ảnh hưởng gì/i.test(t),
      "nhap MOI + chua duyet thi phai NOI RO la khong anh huong gi",
    );
    assert.match(cau, /chưa duyệt/i,
      `cau phai noi ro LY DO la "chua duyet", dang co: ${cau}`);
    assert.doesNotMatch(cau, /\b1\b/,
      `chua duyet thi khong duoc hien mot con so anh huong: dang co ${cau}`);

    assert.deepEqual(tiengOn, [], "doi trang thai duyet khong duoc sinh tieng on console");
    unmount();
  });

  it("I1: form MOI + thuat ngu DANG DUOC DUYET + bo tick ⇒ PHAI hien SO, khong duoc noi 'khong anh huong gi'", async () => {
    // DUONG VAO THU BA cua cung mot loi (review vong #1 bat): `POST` upsert theo
    // `(lang, term)`, nen go mot thuat ngu DA CO trong form MOI roi bo tick CHINH LA
    // bo duyet no. Do lai tren route that:
    //   A) ?lang=zh&term=龙&translation=long&approved=false -> HTTP 200 {"affected":[1]}
    // Ban va truoc chi nhin `editingId` (`hangDangSua`) nen khong nhan ra ca nay va van
    // noi "khong anh huong gi" — man hinh noi SAI ngay truoc khi Luu, trong khi lan Luu
    // that su bao "1 ban ghi". Cach sua: suy tu DU LIEU MAY CHU DA CHO (danh sach `terms`
    // da tai), khong tu trang thai form.
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("rồng"), "bang chua nap xong");

    go(container, '[data-testid="o-thuat-ngu"]', "龙");     // DANG co trong glossary
    go(container, '[data-testid="o-ban-dich"]', "long");
    await choChu(container, '[data-testid="affected-preview"]', (t) => /\b1\b/.test(t),
      "chua do duoc so anh huong truoc khi bo tick");

    fireEvent.click(container.querySelector('[data-testid="o-da-duyet"]') as Element);

    const cau = await choChu(
      container,
      '[data-testid="affected-preview"]',
      (t) => /\b1\b/.test(t),
      "bo duyet mot thuat ngu DANG duyet (du form la MOI) PHAI hien so",
    );
    assert.doesNotMatch(cau, /không ảnh hưởng gì/i,
      `day la BO DUYET mot rang buoc dang co ⇒ khong duoc noi "khong anh huong gi": ${cau}`);
    assert.match(cau, /bỏ duyệt/i,
      `cau phai noi dung VIEC sap xay ra (bo duyet), dang co: ${cau}`);

    // ⚠️ HAI CHO TREN CUNG MOT MAN HINH PHAI NOI CUNG MOT CON SO. Do duoc (review vong #2):
    // o "Anh huong" cua HANG DICH hien `—Sua` trong khi dong xem truoc hien `1` ⇒ hai cho
    // noi khac nhau ve cung mot lan ghi. Cot do phai tinh cho hang ma lan ghi se GHI DE —
    // tuc hang khop KHOA `(lang, term)` cua form, khong chi hang dang mo bang nut Sua.
    assert.match(chu(container, '[data-testid="anh-huong-1"]'), /^1(?!\d)/,
      "o 'Anh huong' cua HANG DICH phai bang con so cua dong xem truoc, khong duoc de `—`");

    assert.deepEqual(tiengOn, [], "bo tick tren form moi khong duoc sinh tieng on console");
    unmount();
  });

  it("I1b: anh chup trong bo nho CU ⇒ con so cua ROUTE van THANG loi doan truoc", async () => {
    // Nua thu hai cua ban va `I1`. Sau khi suy "co phai bo duyet khong" tu DU LIEU MAY CHU,
    // van con mot duong de UI noi SAI: anh chup `terms` da CU. Bai nay lam no CU mot cach
    // TAT DINH — man nap xong (anh chup: `馬` CHUA duyet), roi bai test TU DUYET `馬` qua
    // route that. Luc do, voi cung bo ba (`馬`, `ngựa`, `approved=false`):
    //   - anh chup cu noi "khong phai bo duyet" (→ neu UI doan truoc, no se noi vo hai);
    //   - ROUTE noi `{"affected":[4]}` (transcript `4` chua `馬`) — do la su that.
    // Luat cua ban va: `affected.length > 0` LUON thang moi cau giai thich. Bai nay ghim
    // dung luat do, va no la ca DUY NHAT phan biet duoc hai thu tu do.
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("馬"), "bang chua nap xong");

    // Doi trang thai MAY CHU sau khi man da nap: DUYET `馬` len (route that, HTTP that).
    const them = await fetch("/api/glossary", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ lang: "zh", term: "馬", translation: "ngựa", approved: true }),
    });
    assert.equal(them.status, 201, `duyet \`馬\` qua route that phai la 201, nhan ${them.status}`);

    // Trong man: cung bo ba do, nhung `approved=false` ⇒ BO DUYET mot rang buoc DANG co
    // tren may chu (va anh chup trong bo nho khong biet dieu do).
    go(container, '[data-testid="o-thuat-ngu"]', "馬");
    go(container, '[data-testid="o-ban-dich"]', "ngựa");
    fireEvent.click(container.querySelector('[data-testid="o-da-duyet"]') as Element);

    const cau = await choChu(
      container,
      '[data-testid="affected-preview"]',
      (t) => /\b1\b/.test(t),
      "con so cua ROUTE phai thang loi doan truoc dua tren anh chup CU",
    );
    assert.doesNotMatch(cau, /không ảnh hưởng gì/i,
      `route noi CO anh huong ⇒ khong duoc noi vo hai: ${cau}`);
    // Lý do cũng phải theo MÁY CHỦ đọc lại: `馬` vừa được duyệt qua route thật, nên việc
    // bỏ tick là GỠ một ràng buộc (`bỏ duyệt`), không phải "đổi" — kể cả khi ảnh chụp đã
    // tải (lúc `馬` còn chưa duyệt) nói khác. Đây là vế `>0` của cùng lỗi `M-2` ở `I1d`.
    assert.match(cau, /bỏ duyệt/i, `phai noi dung VIEC sap xay ra (bo duyet): ${cau}`);

    assert.deepEqual(tiengOn, [], "anh chup cu khong duoc sinh tieng on console");
    unmount();
  });

  it("I1c: bo duyet mot hang DANG duyet ma KHONG ai dung ⇒ van la CON SO `0`, khong phai cau 'nhap vo hai'", async () => {
    // Cung ho voi `I1`, nhung o CON SO 0 — cho duy nhat cau giai thich con co the chen vao
    // giua. `鳥` DANG duyet va khong xuat hien o transcript nao, nen bo duyet no khong lam
    // ban dich nao phai xem lai (`affected` = []), NHUNG no KHONG phai mot ban nhap: cau
    // "ban nhap khong di vao prompt" o day la mot cau NOI SAI ve trang thai cua hang.
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("chim"), "bang chua nap xong");

    go(container, '[data-testid="o-thuat-ngu"]', "鳥");
    go(container, '[data-testid="o-ban-dich"]', "chim");
    fireEvent.click(container.querySelector('[data-testid="o-da-duyet"]') as Element);

    const cau = await choChu(
      container,
      '[data-testid="affected-preview"]',
      (t) => /\b0\b/.test(t) && /bản ghi/i.test(t),
      "bo duyet mot hang DANG duyet phai hien con so 0, khong phai cau 'nhap vo hai'",
    );
    assert.doesNotMatch(cau, /không ảnh hưởng gì/i,
      `hang nay DANG duyet ⇒ khong duoc goi no la ban nhap: ${cau}`);
    assert.match(cau, /bỏ duyệt/i, `phai noi dung VIEC sap xay ra (bo duyet): ${cau}`);

    assert.deepEqual(tiengOn, [], "bo duyet hang khong dung o dau khong duoc sinh tieng on console");
    unmount();
  });

  it("I1d: anh chup CU + con so `0` ⇒ LY DO cung phai theo MAY CHU, khong duoc goi hang DANG duyet la 'ban nhap'", async () => {
    // Review vong #2 bat (`M-2`): nhanh `0` van goi mot hang DANG duyet la "ban nhap".
    // Probe `new-stale-zero`: `POST … -> HTTP 201`, may chu co `{"term":"魚","approved":true}`,
    // trong khi cau hien ra la *"Thuật ngữ CHƯA DUYỆT …"*. Con so `0` DUNG, chi LY DO sai.
    //
    // ⇒ Ly do cung phai suy tu DU LIEU MAY CHU DOC LAI LUC QUYET DINH, khong tu anh chup da
    // tai: `魚` duoc gieo CHUA duyet va khong transcript nao chua no, nen sau khi bai test
    // tu duyet no qua route that, anh chup trong bo nho noi "khong phai bo duyet" trong khi
    // may chu noi nguoc lai. `魚` la hang RIENG: `猫` (cung chua duyet, cung khong o
    // transcript nao) da thuoc bai `BANG` (hang cho duyet + chip `✕ trong`), nen duyet no o
    // day se lam bai do do khi thu tu chay doi (review do R6 bang cach DAO 12 khoi `it`).
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("cá"), "bang chua nap xong");

    const duyet = await fetch("/api/glossary", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ lang: "zh", term: "魚", translation: "cá", approved: true }),
    });
    assert.equal(duyet.status, 201, `duyet \`魚\` qua route that phai la 201, nhan ${duyet.status}`);

    go(container, '[data-testid="o-thuat-ngu"]', "魚");
    go(container, '[data-testid="o-ban-dich"]', "cá");
    fireEvent.click(container.querySelector('[data-testid="o-da-duyet"]') as Element);

    const cau = await choChu(
      container,
      '[data-testid="affected-preview"]',
      (t) => /\b0\b/.test(t) && /bản ghi/i.test(t),
      "hang DANG duyet thi phai hien con so 0 kem chu 'ban ghi'",
    );
    assert.doesNotMatch(cau, /không ảnh hưởng gì|CHƯA DUYỆT/i,
      `may chu dang co hang NAY o trang thai DUYET ⇒ khong duoc goi no la ban nhap: ${cau}`);
    assert.match(cau, /bỏ duyệt/i, `phai noi dung VIEC sap xay ra (bo duyet): ${cau}`);

    assert.deepEqual(tiengOn, [], "ly do sai khong duoc sinh tieng on console");
    unmount();
  });

  it("I2: dang SUA thi 'nguon' + 'thuat ngu' la KHOÁ — thu duoc xem truoc == thu duoc ghi", async () => {
    // Review vong #1 bat: `TermPatch` cua backend KHONG co truong `term` (va khong co
    // `lang`), nen `patchTerm` khong gui chung. Nhung o "Thuat ngu" VAN sua duoc ⇒ chu
    // nguoi dung go bi bo IM LANG, va so XEM TRUOC tinh cho mot thuat ngu KHAC voi thuat
    // ngu se duoc GHI. Do la cung lop "thu duoc xem truoc ≠ thu duoc ghi".
    //
    // Cach chua: khoa DANH TINH cua hang khi dang Sua — o `readOnly`, select `disabled`,
    // VA ham `onChange` BO QUA thay doi (khong chi dua vao thuoc tinh HTML: jsdom van
    // phat duoc su kien `change` bang tay, nen thuoc tinh mot minh khong du).
    //
    // ⚠️ Bai nay GHI (bo duyet mot hang that), nen no phai dung mot hang KHONG bai nao
    // khac dung: `犬` (id 3) va transcript `3`. Ban nhap dau tien dung `龙` (id 1) va lam
    // HAI bai khac do (`HOP DONG THAM SO`, `BO DUYET qua FORM`) — do la phu thuoc thu tu
    // trong mot tep dung CHUNG mot DB gieo.
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("犬"), "bang chua nap xong");

    fireEvent.click(container.querySelector('[data-testid="sua-3"]') as Element);

    const oTerm = container.querySelector('[data-testid="o-thuat-ngu"]') as HTMLInputElement;
    const oLang = container.querySelector('[data-testid="o-lang"]') as HTMLSelectElement;
    assert.equal(oTerm.readOnly, true, "dang Sua thi o 'Thuat ngu' phai la readOnly");
    assert.equal(oLang.disabled, true, "dang Sua thi select 'Nguon' phai VO HIEU (PATCH khong gui lang)");
    assert.match(chu(container, '[data-testid="khoa-danh-tinh"]'), /.+/,
      "phai NOI RA vi sao hai o do bi khoa, khong im lang");

    // Bo duyet hang dang sua ⇒ xem truoc la 1 (route that: bo duyet `犬` ⇒ [3]).
    fireEvent.click(container.querySelector('[data-testid="o-da-duyet"]') as Element);
    const xemTruoc = await choChu(container, '[data-testid="affected-preview"]', (t) => /\b1\b/.test(t),
      "bo duyet hang dang sua phai hien so 1");
    assert.doesNotMatch(xemTruoc, /không ảnh hưởng gì/i, `khong duoc noi vo hai: ${xemTruoc}`);

    // Thu "sua" o khoa bang tay: jsdom VAN phat duoc `change`. Neu component nghe theo thi
    // so xem truoc se tinh cho mot thuat ngu khong co o dau (⇒ 0) trong khi lan Luu ghi cho
    // `犬` (⇒ 1) — hai con so khac nhau, va do la loi `I2`.
    const CHU_GO_SAI = "KHONG-DUOC-GHI";
    fireEvent.change(oTerm, { target: { value: CHU_GO_SAI } });
    fireEvent.change(oLang, { target: { value: "en" } });

    // ⚠️ PHAI CHO QUA NGUONG DEBOUNCE ROI MOI DOC SO. Bản đầu của bài này đọc NGAY sau
    // `fireEvent.change` (trước `CHO_GO_MS` = 200 ms), nên **nó MÙ với mọi hiệu ứng
    // debounce**: state có đổi thì con số cũng chưa kịp đổi. Đo được (review vòng #2):
    // mutation chỉ bỏ lớp BỎ QUA `onChange` (giữ `readOnly`/`disabled`) **SỐNG SÓT** —
    // `ℹ pass 130 / ℹ fail 2` y hệt lượt sạch — nghĩa là bài test chỉ ghim được LỚP MỘT.
    // ⇒ Luật (ERRATA #25 mục 1): một bài đọc trạng thái NGAY sau khi phát sự kiện là một
    // bài MÙ với debounce; và một bản vá có N lớp thì phải mutate TỪNG LỚP RIÊNG.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 900));
    });

    const soXemTruoc = soTrong(container);

    await act(async () => {
      fireEvent.click(container.querySelector('[data-testid="luu"]') as Element);
      const het = Date.now() + 8000;
      while (Date.now() < het && container.querySelector('[data-testid="da-luu"]') === null) {
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
    });
    const soDaLuu = soTrong(container, '[data-testid="da-luu"]');
    assert.equal(soDaLuu, soXemTruoc,
      `so XEM TRUOC (${soXemTruoc}) phai BANG so lan GHI (${soDaLuu}): `
      + "hong o day nghia la thu duoc xem truoc khac thu duoc ghi");

    // Va hang trong bang van la `犬` — chu go vao o khoa khong duoc di dau ca.
    await choChu(container, '[data-testid="hang-3"]', (t) => t.includes("犬"),
      "hang 3 phai giu nguyen thuat ngu `犬`");
    assert.doesNotMatch(chu(container, '[data-testid="hang-3"]'), new RegExp(CHU_GO_SAI),
      "chu go vao o KHOÁ khong duoc xuat hien trong bang");

    assert.deepEqual(tiengOn, [], "sua hang khong duoc sinh tieng on console");
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
    // Bai nay la bai GHI DUY NHAT cua tep, va no ghi mot thuat ngu MOI (`chó`, chi co
    // trong transcript thu hai) — no KHONG sua `龙`/`猫` cua DB gieo. Ly do: moi bai
    // trong tep nay dung CHUNG mot backend + mot DB gieo, nen mot bai ghi de len du
    // lieu ma bai khac dang khang dinh la mot phu thuoc THU TU (do duoc: ban nhap dau
    // cua bai "BO DUYET qua FORM" do vi bai nay da chay truoc no va doi `龙`).
    const truoc = (await (await fetch("/api/glossary/version")).json()) as {
      glossary_version: number;
    };

    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("rồng"), "bang chua nap xong");

    go(container, '[data-testid="o-thuat-ngu"]', "chó");
    go(container, '[data-testid="o-ban-dich"]', "dog");
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

    // Bang phai NAP LAI tu route: thuat ngu vua ghi hien ra.
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("dog"),
      "sau khi luu, bang khong nap lai du lieu tu route");

    assert.deepEqual(tiengOn, [], "luu thuat ngu khong duoc sinh tieng on console");
    unmount();
  });

  it("BO DUYET qua FORM: bo tick o mot hang DANG DUYET phai hien SO, khong duoc noi 'khong anh huong gi'", async () => {
    // DO DUOC: mot thuat ngu DANG DUYET ma bi BO DUYET la GO mot rang buoc ⇒ ban dich cu
    // sai ⇒ CO anh huong (route that: cung `term` + cung `translation`, chi khac `approved`,
    // cho `{"affected":[1]}`). Nhanh "chua duyet ⇒ khong anh huong gi" chi DUNG cho mot
    // thuat ngu CHUA TUNG duoc duyet; ap no cho ca truong hop BO DUYET la mot cau NOI SAI
    // — dung lop loi "nhan dao" ma ERRATA #10 muc 9 do duoc o Task 4: chu NGUOI DUNG DOC
    // noi nguoc su that, va khong bai nao bat duoc.
    //
    // Bai nay cung ghim AFFORDANCE: hang duoc dua vao form bang mot NUT (khong phai
    // `<tr onClick>`), vi mot duong chi-bam-chuot duoc la mot duong khong ton tai voi
    // ban phim (spec §7 / §12.5).
    const { container, unmount } = render(taoPhanTu(GlossaryScreen));
    await choChu(container, '[data-testid="bang"]', (t) => t.includes("rồng"), "bang chua nap xong");

    fireEvent.click(container.querySelector('[data-testid="sua-1"]') as Element);
    const oDuyet = container.querySelector('[data-testid="o-da-duyet"]') as HTMLInputElement;
    assert.equal(oDuyet.checked, true, "hang 1 dang DUYET ⇒ o 'da duyet' phai bat sau khi bam Sua");
    assert.match(
      (container.querySelector('[data-testid="o-thuat-ngu"]') as HTMLInputElement).value,
      /龙/,
      "bam Sua phai dua DUNG hang do vao form",
    );

    fireEvent.click(oDuyet);                       // BO DUYET mot hang DANG duyet

    const cau = await choChu(
      container,
      '[data-testid="affected-preview"]',
      (t) => /\b1\b/.test(t),
      "BO DUYET mot hang dang duyet PHAI hien so anh huong",
    );
    assert.doesNotMatch(cau, /không ảnh hưởng gì/i,
      `bo duyet la GO mot rang buoc ⇒ khong duoc noi "khong anh huong gi": ${cau}`);
    assert.match(cau, /bản ghi/i, `phai giu DUNG DON VI (ban ghi/transcript): ${cau}`);

    // Cot "Anh huong" cua chinh hang do cung phai hien so, khong duoc de `—`.
    // ⚠️ `/^1/` chu khong `/\b1\b/`: trong o nay con co nut "Sửa" ngay sau con so, va
    // `\b` KHONG ton tai giua hai ky tu WORD (`1` va `S`) — mot khang dinh dung `\b` o
    // day do vi ly do KY TU, khong phai vi san pham sai (do duoc: `actual: '1Sửa'`).
    assert.match(chu(container, '[data-testid="anh-huong-1"]'), /^1(?!\d)/,
      "cot Anh huong cua hang dang sua phai hien so cua route");

    assert.deepEqual(tiengOn, [], "bo duyet qua form khong duoc sinh tieng on console");
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
