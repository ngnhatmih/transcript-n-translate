/**
 * Chay TANG CHROME THAT (Task 12, T2) — KHONG nam trong `npm test`.
 *
 * ## Cach dung (doc `README.md` truoc)
 *
 * ```
 * cd frontend
 * node e2e/session.mjs plans/bon-man.json --out C:/duong/dan/ngoai/repo/anh-t12
 * ```
 *
 * ## Cach ly moi truong (ba quy tac cung)
 *
 * 1. **KHONG BAO GIO cham 8620/8621** — do la cong CO CHU cua `src/api/contract.test.ts` (no tu
 *    spawn backend o 8620 va dua vao DB repo RONG). Backend e2e o **8631** (bieu thuc `PHUDE_E2E_PORT`),
 *    va dev-server tro vao do bang `PHUDE_BACKEND_PORT`.
 * 2. **KHONG BAO GIO doi cong dev-server** — `3100` VAN CUNG: backend chi whitelist CORS
 *    `http://localhost:3100` / `http://127.0.0.1:3100`, nen doi cong la hong CORS, ma sua CORS thi
 *    phai cham `backend/` (bi cam trong task frontend).
 * 3. **DB + media o scratch NGOAI repo** (`_seed-e2e/` canh repo) ⇒ chay xong xoa sach, khong lam
 *    ban `data/app.db` cua repo.
 *
 * ## Don dep
 *
 * `finally` tat dev-server, backend, Chrome (qua CDP `Browser.close` — cach DUY NHAT an toan khi
 * khong doc duoc `CommandLine`: ERRATA #41 muc 4) va xoa scratch. Cua so nao khong tat duoc thi
 * **in ra**, khong im lang.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { CDP_PORT, chayKeHoach, dongChrome, ketNoi, sleep } from "./cdp.mjs";

const E2E_DIR = fileURLToPath(new URL("./", import.meta.url));
const FRONTEND_DIR = fileURLToPath(new URL("../", import.meta.url));
const REPO_DIR = fileURLToPath(new URL("../../", import.meta.url));

const DEV_PORT = 3100; // CUNG — xem muc 2 o docblock.
const BACKEND_PORT = Number(process.env.PHUDE_E2E_PORT ?? 8631);
// ⚠️ CANH repo, KHONG PHAI trong repo. Hai lý do, cả hai đều ĐO ĐƯỢC:
//  (a) scratch không được làm bẩn cây repo;
//  (b) `seed.py` chép vào đây tính `BACKEND = Path(__file__).parents[1]/"phu-de-lab"/"backend"`
//      ⇒ `parents[1]` PHẢI là gốc workspace. Để trong repo thì nó thành `<repo>/phu-de-lab/backend`.
//  Hệ quả kèm theo (đúng ý định): `path.dirname(SCRATCH)` = gốc workspace = nơi `_seed/` thật sự nằm.
const SCRATCH = path.join(path.dirname(REPO_DIR), "_seed-e2e");
const BACKEND_DIR = path.join(REPO_DIR, "backend");
const VENV_PYTHON = process.platform === "win32"
  ? path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe")
  : path.join(BACKEND_DIR, ".venv", "bin", "python");

const CHROME = process.env.PHUDE_CHROME
  ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";

function thamSo() {
  const argv = process.argv.slice(2);
  const ra = { plan: null, out: null, giu: false };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--out") { ra.out = argv[i + 1]; i += 1; } else if (argv[i] === "--giu") { ra.giu = true; } else if (ra.plan === null) { ra.plan = argv[i]; }
  }
  if (ra.plan === null) {
    console.error("thiếu kế hoạch: node e2e/session.mjs <plan.json> [--out <thư mục ảnh>] [--giu]");
    process.exit(2);
  }
  ra.out = ra.out ?? path.join(E2E_DIR, "anh");
  return ra;
}

function congDangMo(port) {
  const kq = spawnSync(process.execPath, [
    "-e",
    `const s=require("node:net").connect({host:"127.0.0.1",port:${port}},()=>{s.destroy();process.exit(0)});`
    + "s.on('error',()=>process.exit(1));setTimeout(()=>process.exit(1),1000);",
  ], { stdio: "ignore" });
  return kq.status === 0;
}

async function choCong(port, mo, timeoutMs = 60_000) {
  const het = Date.now() + timeoutMs;
  while (Date.now() < het) {
    if (congDangMo(port) === mo) return true;
    await sleep(250);
  }
  return false;
}

/** Chay mot lenh Python cua backend va CHO no xong (khong spawn nen). */
function chayPython(script, args, { env = {} } = {}) {
  const kq = spawnSync(VENV_PYTHON, ["-B", script, ...args], {
    cwd: BACKEND_DIR,
    stdio: "inherit",
    windowsHide: true,
    env: { ...process.env, ...env },
  });
  if (kq.status !== 0) throw new Error(`python ${path.basename(script)} that bai (exit ${kq.status})`);
}

function gieo() {
  mkdirSync(SCRATCH, { recursive: true });
  // ⚠️ Chep `seed.py` vao scratch thay vi viet lai: `seed.py` tinh `BACKEND` bang
  // `parents[1]/"phu-de-lab"/"backend"`, nen mot ban sao o `_seed-e2e/` CANH repo tro DUNG backend.
  // Chep lai cong thuc gieo o day se la nguon su that thu hai (ERRATA #43 muc 2).
  const seedGoc = path.join(path.dirname(SCRATCH), "_seed", "seed.py");
  if (!existsSync(seedGoc)) {
    throw new Error(
      `khong thay ${seedGoc}. Thu muc _seed/ la tai san NGOAI repo (ERRATA #42 muc 4) — `
      + "dung xoa no, va dung sinh ban sao thu hai cua cong thuc gieo.",
    );
  }
  writeFileSync(path.join(SCRATCH, "seed.py"), readFileSync(seedGoc), "utf8");
  writeFileSync(
    path.join(SCRATCH, "serve_no_worker.py"),
    readFileSync(path.join(path.dirname(SCRATCH), "_seed", "serve_no_worker.py")),
    "utf8",
  );
  chayPython(path.join(SCRATCH, "seed.py"), []);
  chayPython(path.join(E2E_DIR, "seed-dai.py"), [
    BACKEND_DIR,
    path.join(SCRATCH, "data", "app.db"),
    String(Number(process.env.PHUDE_E2E_DOAN ?? 600)),
  ]);
}

async function main() {
  const { plan: planPath, out, giu } = thamSo();
  if (!existsSync(CHROME)) {
    throw new Error(
      `khong thay Chrome o ${CHROME}. Dat bien PHUDE_CHROME tro toi chrome.exe. `
      + "⚠️ Chrome CHI mo duoc voi quyen rong (ERRATA #40).",
    );
  }
  if (SCRATCH.startsWith(path.resolve(REPO_DIR))) {
    throw new Error(
      `scratch ${SCRATCH} nam TRONG repo ${REPO_DIR} — trai luat (xem chu thich o \`SCRATCH\`): `
      + "(a) lam ban cay repo; (b) `seed.py` chep vao do tinh `parents[1]/\"phu-de-lab\"/\"backend\"` "
      + "nen se tro SAI backend. Sua `SCRATCH` cho dung thay vi bo qua loi nay.",
    );
  }
  if (congDangMo(DEV_PORT)) {
    throw new Error(`cong ${DEV_PORT} dang bi chiem — tat tien trinh do truoc (tang nay khong tu nhay cong).`);
  }
  for (const cam of [8620, 8621]) {
    if (congDangMo(cam)) {
      throw new Error(`cong ${cam} dang bi chiem — do la cong CO CHU cua contract test; dung cham vao.`);
    }
  }
  const plan = JSON.parse(readFileSync(path.resolve(planPath), "utf8"));
  mkdirSync(out, { recursive: true });

  console.log(`[e2e] gieo DB o ${SCRATCH} (ngoai repo)`);
  gieo();

  const backendEnv = {
    ...process.env,
    PHUDE_DB: path.join(SCRATCH, "data", "app.db"),
    PHUDE_DATA: path.join(SCRATCH, "data"),
    PHUDE_PORT: String(BACKEND_PORT),
  };
  console.log(`[e2e] backend gieo DB o ${BACKEND_PORT} (khong kem worker)`);
  const backend = spawn(VENV_PYTHON, ["-B", path.join(SCRATCH, "serve_no_worker.py")], {
    cwd: BACKEND_DIR, stdio: "ignore", windowsHide: true, env: backendEnv,
  });

  const dev = spawn(process.execPath, ["dev-server.mjs"], {
    cwd: FRONTEND_DIR,
    stdio: ["ignore", "ignore", "pipe"],
    windowsHide: true,
    env: { ...process.env, PHUDE_BACKEND_PORT: String(BACKEND_PORT) },
  });
  const devErr = [];
  dev.stderr.on("data", (b) => devErr.push(String(b)));

  const chromeDir = path.join(SCRATCH, "chrome-profile");
  mkdirSync(chromeDir, { recursive: true });
  let chrome = null;
  let driver = null;

  try {
    if (!(await choCong(BACKEND_PORT, true, 60_000))) {
      throw new Error(`backend ${BACKEND_PORT} khong len (xem ${SCRATCH})`);
    }
    if (!(await choCong(DEV_PORT, true, 60_000))) {
      throw new Error(`dev-server khong len: ${devErr.join("").slice(0, 500)}`);
    }
    console.log(`[e2e] dev-server 3100 -> backend ${BACKEND_PORT}`);

    chrome = spawn(CHROME, [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      "--hide-scrollbars",
      `--remote-debugging-port=${CDP_PORT}`,
      `--user-data-dir=${chromeDir}`,
      `--window-size=${plan.width ?? 1440},${plan.height ?? 900}`,
      "about:blank",
    ], { stdio: "ignore", windowsHide: true });
    console.log(`[e2e] Chrome headless, CDP ${CDP_PORT} (pid ${chrome.pid})`);

    driver = await ketNoi({ port: CDP_PORT });
    // 🔴 LUAT 1 (ERRATA #47 muc 6): xac nhan trang TRUOC khi tac dong, va khong bao gio tac dong
    // len mot tab KHONG phai cua minh.
    const url = await driver.goi("location.href");
    console.log(`[e2e] trang hien tai: ${url.giaTri}`);

    const ket = await chayKeHoach(driver, plan, { outDir: out });
    writeFileSync(path.join(out, "ket-qua.json"), JSON.stringify(ket, null, 2), "utf8");
    console.log(`[e2e] xong — ket qua: ${path.join(out, "ket-qua.json")}`);
    console.log("⚠️ Anh chup CHI chung minh BO CUC/VE. Chung KHONG chung minh chat luong ban dich.");
  } finally {
    if (driver !== null) await dongChrome(driver);
    await sleep(800);
    if (chrome !== null && chrome.exitCode === null) {
      console.log("[e2e] Chrome chua tat sau Browser.close — tat tien trinh minh spawn");
      chrome.kill();
    }
    dev.kill();
    backend.kill();
    await sleep(500);
    const con = [BACKEND_PORT, DEV_PORT, CDP_PORT].filter((p) => congDangMo(p));
    if (con.length > 0) console.log(`⚠️ con cong dang mo: ${con.join(", ")} — kiem tra tay`);
    if (!giu) {
      // ⚠️ Xoa DUNG scratch minh tao ra. KHONG xoa de quy thu muc co junction (ERRATA #47 muc 8 —
      // da xoa nham `frontend/node_modules` mot lan).
      rmSync(SCRATCH, { recursive: true, force: true });
      console.log("[e2e] da xoa scratch");
    } else {
      console.log(`[e2e] --giu: scratch con o ${SCRATCH}`);
    }
  }
}

main().catch((e) => {
  console.error(`[e2e] LOI: ${e.message}`);
  process.exit(1);
});
