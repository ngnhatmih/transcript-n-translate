/**
 * T1 §A — do duong CRASH cua `dev-server.mjs` (`ERR_HTTP_HEADERS_SENT`, EVIDENCE §7).
 *
 * ## Trang thai DO DUOC (khong phai suy luan) — BAN DA SUA O VONG SUA 1 (`I1`)
 *
 * 🔴 **CAU CU O DAY SAI, VA NO NAM TRONG MA.** Ban truoc viet: *"Bon kich ban tan cong TCP that …
 * deu cho `headersSent=false` ⇒ tien trinh KHONG thoat. Nghia la: duong crash la MOT CUA SO"* — va
 * ket luan do bi khang dinh thanh *"KHONG tai lap duoc tu ngoai bang TCP"*. **Sai.** Cau dung:
 *
 * > *"Loi `:97` **TAI LAP DUOC TU NGOAI BANG TCP THAT — TAT DINH 3/3 luot** khi upstream dang giu
 * > **mot response DAI (SSE)** ma **tien trinh backend chet**: `dev-server` goc thoat `EXIT=1` voi
 * > `ERR_HTTP_HEADERS_SENT` tai `:97`. **KHONG** tai lap duoc bang bon hinh dang **request/response
 * > NGAN** (RST sau header, chunked dut, 101 roi chet, client huy giua body) — vi tren Node 24 mot
 * > response ngan bi huy **khong** lam `ClientRequest` phat `'error'`; va `res.socket.destroy()`
 * > phia server **cung khong**. App that **luon** co mot SSE dang mo (`App.useJobStream`), nen
 * > duong crash la duong THAT, khong phai mot cua so ly thuyet."*
 *
 * ⇒ He qua len BAI TEST (day la ly do `A1b` ton tai): bai "TCP that" cu (`A1`) chi dung
 * **request/response NGAN**, nen no **KHONG thi hanh duong crash** — do duoc: mutant
 * `M1b-HANDLER-GOC` (tra nguyen khoi handler GOC) van de `A1` **XANH**. `A1b` dung dung kich ban
 * cua EVIDENCE §7 (giu response DAI roi **GIET TIEN TRINH** backend) ⇒ no **giet duoc** ban goc va
 * **xanh** ban va.
 *
 * ⚠️ Vi vay `A0` (doc ma nguon) **khong con la bai duy nhat** bat duoc `M1b`; no o lai nhu mot
 * khang dinh bo sung ve hinh dang khoi handler (va vi mot phep do hanh vi khong thay the duoc mot
 * khang dinh ve CAU TRUC cua ban va).
 *
 * 🔴 `PHUDE_DEBUG_PORT` KHONG dat thi khong co cong nao duoc mo — khong co be mat moi trong san pham.
 * 🔴 Cong dev-server KHONG cau hinh duoc (CORS cua backend chi whitelist 3100): tep nay dung DUNG
 * 3100 va **BO QUA** neu 3100 dang bi chiem. Cong backend thi cau hinh duoc (`PHUDE_BACKEND_PORT`),
 * va backend gia dung `listen(0)` ⇒ 8620/8621 (cong CO CHU cua `contract.test.ts`) khong bao gio bi chiem.
 */
import { after, before, describe, it } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { rmSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import { connect } from "node:net";
import { fileURLToPath } from "node:url";

import { banCoCongDieuKhien } from "./dev-server-copy.mjs";

const FRONTEND_DIR = fileURLToPath(new URL("../", import.meta.url));
const DEV_SERVER = `${FRONTEND_DIR}dev-server.mjs`;
/** Backend GIA co mot route SSE — mot TIEN TRINH rieng de `kill()` duoc (xem `A1b`). */
const SSE_BACKEND = `${FRONTEND_DIR}test/t12-sse-backend.mjs`;

/** Cong dev-server — CUNG, khong cau hinh duoc (CORS cua backend chi whitelist 3100). */
const DEV_PORT = 3100;

/** Cho toi khi `dieuKien()` dung; `timeout` chi la HAN CHOT (ERRATA #35 muc 2). */
async function choToi(dieuKien, timeoutMs = 30_000, buocMs = 100) {
  const het = Date.now() + timeoutMs;
  for (;;) {
    let ok = false;
    try {
      ok = await dieuKien();
    } catch {
      ok = false;
    }
    if (ok) return true;
    if (Date.now() > het) return false;
    await new Promise((r) => setTimeout(r, buocMs));
  }
}

/** Cong dang LISTEN — do bang TCP that, khong doc bang nao cua he dieu hanh. */
function congDangMo(port) {
  return new Promise((resolve) => {
    const socket = connect({ host: "127.0.0.1", port }, () => {
      socket.destroy();
      resolve(true);
    });
    socket.on("error", () => resolve(false));
    socket.setTimeout(1000, () => {
      socket.destroy();
      resolve(false);
    });
  });
}


/** Dev-server THAT trong tien trinh con; stderr duoc giu lai de bat `ERR_HTTP_HEADERS_SENT`. */
function spawnDevServer(env) {
  const child = spawn(process.execPath, ["dev-server.mjs"], {
    cwd: FRONTEND_DIR,
    stdio: ["ignore", "ignore", "pipe"],
    windowsHide: true,
    env: { ...process.env, ...env },
  });
  const vet = [];
  child.stderr.on("data", (b) => vet.push(String(b)));
  child.vet = () => vet.join("");
  return child;
}

/**
 * Cho dev-server LEN hoac THOAT, va tra ve LY DO that.
 *
 * ⚠️ `fetch` tra loi KHONG tu no noi "dev-server hong": no co the la `EADDRINUSE` vi socket cua
 * bai TRUOC chua kip duoc tra (do duoc: bai ke tiep bao "khong goi duoc dev-server" trong 61 ms,
 * tuc dev-server da thoat ngay). Vi vay phai DOC stderr cua con va phan biet hai ca — neu khong,
 * mot loi ha tang bi bao nhu mot loi SAN PHAM.
 */
async function choDevServerLen(child, timeoutMs = 40_000) {
  const len = await choToi(async () => {
    if (child.exitCode !== null) return true; // da thoat ⇒ thoi cho
    const r = await fetch(`http://127.0.0.1:${DEV_PORT}/api/status`, {
      signal: AbortSignal.timeout(2000),
    });
    return r.status === 200;
  }, timeoutMs);
  return {
    len,
    thoat: child.exitCode !== null,
    stderr: child.vet().slice(0, 400),
  };
}

/**
 * Tat dev-server va CHO TOI KHI CONG 3100 THUC SU duoc tra.
 *
 * ⚠️ Cho `exitCode !== null` KHONG du: TCP dang o `TIME_WAIT`/`CLOSE_WAIT` thi lan spawn sau
 * (trong CUNG tep) se an `EADDRINUSE` va dev-server thoat NGAY ⇒ bai ke tiep bao "khong goi duoc
 * dev-server" — mot ket luan SAI ve san pham, chi vi thieu mot phep cho. Do duoc: `exitCode` la
 * `null` ngay sau `kill()`.
 */
async function dung(child) {
  if (child === null) return;
  if (child.exitCode === null && child.signalCode === null) {
    child.kill();
    await choToi(() => child.exitCode !== null || child.signalCode !== null, 8000, 50);
  }
  await choToi(async () => !(await congDangMo(DEV_PORT)), 15_000, 100);
}

/**
 * Backend GIA.
 *
 * Bon dang duong:
 *  - `/api/treo`  — gui header + nua body roi DUNG IM (do "bi cat giua duong").
 *  - `/api/cham`  — KHONG tra loi trong 900 ms (giu request o trang thai "chua co header").
 *  - `/api/goi`   — gui header + body DAY DU bang `end()` (response ket thuc ⇒ header DA gui).
 *  - con lai      — tra loi ngay.
 */
function backendGia() {
  const nhanDuoc = [];
  let cat = null;
  const server = createServer((req, res) => {
    nhanDuoc.push(req.url);
    if (req.url.startsWith("/api/treo")) {
      res.writeHead(200, { "content-type": "application/json" });
      res.write('{"nua');
      cat = () => res.socket !== null && res.socket.destroy();
      return;
    }
    if (req.url.startsWith("/api/cham")) {
      // Cho 900 ms moi tra loi: trong khoang do `res` cua proxy CHUA gui header nao.
      setTimeout(() => {
        if (!res.writableEnded) {
          res.writeHead(200, { "content-type": "application/json" }).end('{"ok":true}');
        }
      }, 900);
      return;
    }
    res.writeHead(200, { "content-type": "application/json" }).end('{"ok":true}');
  });
  return { server, nhanDuoc, cat: () => cat !== null && cat() };
}

function listen(server, port = 0) {
  return new Promise((r) => server.listen(port, "127.0.0.1", () => r(server.address().port)));
}

describe("dev-server.mjs: khong chet khi backend mat, va cong backend cau hinh duoc", () => {
  let coCong = false;

  before(async () => {
    coCong = await congDangMo(DEV_PORT);
  });

  after(async () => {
    await choToi(async () => !(await congDangMo(DEV_PORT)), 5000, 200);
    // Don TEP TAM minh tao ra. ⚠️ LIEET KÊ DUONG DAN, khong quet theo mau: mot glob o day co the
    // xoa nham thu khac; va ⚠️ KHONG bao gio xoa de quy mot thu muc co junction/symlink
    // (ERRATA #47 muc 8 — da xoa nham `frontend/node_modules` mot lan).
    // ⚠️ DO DUOC: ban dau cho nay chi xoa `dev-server.t12-dbg.mjs` (ten CU), nen hai ban sao
    // `dev-server.goc.mjs`/`dev-server.nguyen.mjs` o lai ⇒ `git status` BAN sau luot `npm test`.
    // Giu `PHUDE_GIU_BAN_SAO=1` de con soi khi phep do sai.
    if (process.env.PHUDE_GIU_BAN_SAO !== "1") {
      for (const ten of [
        "dev-server.goc.mjs",
        "dev-server.nguyen.mjs",
        "dev-server.t12-dbg.mjs",
        "dev-server.t12-goc.mjs",
        "dev-server.t12-nguyen.mjs",
      ]) {
        rmSync(`${FRONTEND_DIR}${ten}`, { force: true });
      }
      rmSync(`${FRONTEND_DIR}.t12-tam`, { recursive: true, force: true });
    }
  });

  it("A1) backend bi cat giua duong theo kich ban TCP that ⇒ dev-server SONG", async () => {
    if (coCong) {
      assert.ok(true, `cong ${DEV_PORT} dang bi chiem ⇒ bo qua phep do (khong ket luan gi)`);
      return;
    }
    const gia = backendGia();
    const bePort = await listen(gia.server);
    const child = spawnDevServer({ PHUDE_BACKEND_PORT: String(bePort) });
    try {
      const len = await choDevServerLen(child);
      assert.ok(
        len.len,
        `dev-server (cong ${DEV_PORT}) khong phuc vu duoc qua backend gia o ${bePort}: `
        + `thoat=${len.thoat} (exit ${child.exitCode}); stderr: ${len.stderr}. `
        + "Neu backend gia KHONG nhan duoc request nao thi `PHUDE_BACKEND_PORT` chua duoc noi.",
      );

      const treo = fetch(`http://127.0.0.1:${DEV_PORT}/api/treo`, {
        signal: AbortSignal.timeout(8000),
      }).then(
        (r) => ({ kind: "response", status: r.status }),
        (e) => ({ kind: "error", name: e.name }),
      );
      const daNhan = await choToi(() => gia.nhanDuoc.some((u) => u.startsWith("/api/treo")), 5000);
      assert.ok(daNhan, "backend gia khong nhan duoc /api/treo");
      await new Promise((r) => setTimeout(r, 200));

      gia.cat();
      const ketQua = await treo;
      await new Promise((r) => setTimeout(r, 700));

      assert.equal(
        child.exitCode,
        null,
        `dev-server THOAT (exit ${child.exitCode}) khi backend bi cat giua duong; stderr: `
        + `${child.vet().slice(0, 400)}`,
      );
      // ⚠️ DO DUOC: khi upstream gui header roi bi cat, proxy DA gui header cho client truoc do
      // (`up.pipe(res)` goi `res.writeHead(up.statusCode, ...)` NGAY trong callback 'response'),
      // nen `fetch` nhan **200** voi body DUT — KHONG phai 502. Khang dinh 502 o day la mot
      // khang dinh SAI ve co che (do duoc tren blob goc: `{"kind":"response","status":200}`).
      // Cai phai dung la: tien trinh SONG. Ma 502 chi xay ra khi loi den TRUOC header.
      assert.ok(
        ketQua.kind === "error" || ketQua.kind === "response",
        `request treo phai ket thuc (502 hoac dut that), do duoc: ${JSON.stringify(ketQua)}`,
      );
      const sau = await fetch(`http://127.0.0.1:${DEV_PORT}/api/status`, {
        signal: AbortSignal.timeout(3000),
      });
      assert.equal(sau.status, 200, "dev-server phai con phuc vu duoc sau khi backend bi cat");
      assert.equal(
        child.vet().includes("ERR_HTTP_HEADERS_SENT"),
        false,
        "khong duoc co ERR_HTTP_HEADERS_SENT trong stderr",
      );
    } finally {
      await dung(child);
      await new Promise((r) => gia.server.close(r));
    }
  });

  it("A1b) TCP THAT: upstream giu mot response DAI (SSE) roi CHET ⇒ ban GOC thoat (exit 1), ban va SONG", async () => {
    if (coCong) {
      assert.ok(true, `cong ${DEV_PORT} dang bi chiem ⇒ bo qua phep do (khong ket luan gi)`);
      return;
    }
    // 🔴 VI SAO BAI NAY TON TAI (`I1`, vong sua 1): `A1` chi dung **request/response NGAN**, va do
    // duoc la mutant `M1b-HANDLER-GOC` (tra nguyen khoi handler GOC) van de `A1` **XANH** — tuc
    // bai "TCP that" cu **KHONG thi hanh duong crash**. Duong crash that (EVIDENCE §7) can DUNG HAI
    // thu, va ca hai deu khong co trong `A1`:
    //   1. upstream dang giu **mot response DAI** (SSE) ⇒ `res.headersSent === true` tren proxy;
    //   2. **TIEN TRINH** backend CHET (khong phai socket bi huy) ⇒ `ClientRequest` moi phat `'error'`.
    //
    // ⇒ Phep do: backend SSE la mot TIEN TRINH RIENG (giet duoc), va bai chay HAI luot:
    //    - `san-pham` = **CHINH `dev-server.mjs`** (khong ban sao) ⇒ khang dinh ve SAN PHAM, va la
    //      thu lam mutant `M1b-HANDLER-GOC` DO vi dung no do chinh tep san pham;
    //    - `goc` = ban sao co khoi handler GOC (khong guard, khong `try/catch`) ⇒ **doi chung** rang
    //      cua so §7 CO THAT (neu khong co ve nay thi "san pham song" khong chung minh duoc gi).
    // ⚠️ `PHUDE_DEBUG_PORT` KHONG duoc dat o day: khong mo cong dieu khien nao — day la TCP THAT.
    const nuotBody = (r) => {
      if (r === null || r.body === null || typeof r.body.getReader !== "function") return;
      const doc = r.body.getReader();
      const vong = async () => {
        try {
          for (;;) {
            const { done } = await doc.read();
            if (done) return;
          }
        } catch {
          // Backend chet giua duong ⇒ loi o day la KET QUA CAN DO, khong phai loi cua bai test.
        }
      };
      vong();
    };

    const chayMotLuot = async (kieu) => {
      let bePort = null;
      const beVet = [];
      const be = spawn(process.execPath, [SSE_BACKEND], {
        cwd: FRONTEND_DIR,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
        env: { ...process.env, PHUDE_T12_SSE_PORT: "0" },
      });
      be.stdout.on("data", (b) => {
        const m = /PORT=(\d+)/.exec(String(b));
        if (m !== null) bePort = Number(m[1]);
      });
      be.stderr.on("data", (b) => beVet.push(String(b)));
      const dungBe = async () => {
        if (be.exitCode === null && be.signalCode === null) be.kill();
        await choToi(() => be.exitCode !== null || be.signalCode !== null, 8000, 50);
      };

      try {
        assert.ok(
          await choToi(() => bePort !== null, 10_000, 50),
          `backend SSE khong in ra PORT=; stderr: ${beVet.join("").slice(0, 300)}`,
        );

        const dich = kieu === "san-pham" ? DEV_SERVER : `${FRONTEND_DIR}dev-server.${kieu}.mjs`;
        if (kieu !== "san-pham") banCoCongDieuKhien(FRONTEND_DIR, dich, kieu);
        const child = spawn(process.execPath, [dich], {
          cwd: FRONTEND_DIR,
          stdio: ["ignore", "ignore", "pipe"],
          windowsHide: true,
          env: { ...process.env, PHUDE_BACKEND_PORT: String(bePort) },
        });
        const vet = [];
        child.stderr.on("data", (b) => vet.push(String(b)));
        try {
          const len = await choToi(async () => {
            if (child.exitCode !== null) return true;
            const r = await fetch(`http://127.0.0.1:${DEV_PORT}/api/status`, {
              signal: AbortSignal.timeout(2000),
            });
            return r.status === 200;
          }, 40_000);
          assert.ok(len, `luot ${kieu} khong len; stderr: ${vet.join("").slice(0, 400)}`);

          // Mo mot response DAI qua proxy. `fetch` resolve khi HEADER toi ⇒ proxy DA gui header.
          const r = await fetch(`http://127.0.0.1:${DEV_PORT}/api/sse`, {
            signal: AbortSignal.timeout(20_000),
          }).catch(() => null);
          assert.ok(
            r !== null && r.status === 200,
            `khong mo duoc SSE qua proxy o ${DEV_PORT} (backend ${bePort})`,
          );
          nuotBody(r);
          await new Promise((res) => setTimeout(res, 300));

          // 🔴 GIET TIEN TRINH UPSTREAM trong khi response CON MO — day la cua so §7.
          be.kill();
          await choToi(() => be.exitCode !== null || be.signalCode !== null, 8000, 50);
          await new Promise((res) => setTimeout(res, 1500));

          return {
            kieu,
            exit: child.exitCode,
            coLoiHeader: vet.join("").includes("ERR_HTTP_HEADERS_SENT"),
            stderr: vet.join("").slice(0, 500),
          };
        } finally {
          await dung(child);
        }
      } finally {
        await dungBe();
      }
    };

    // 🔴 LUOT 1 — **CHINH TEP SAN PHAM** (`dev-server.mjs`) phai SONG. Day la khang dinh lam mutant
    //    `M1b-HANDLER-GOC` (tra nguyen khoi handler GOC — khong guard, khong `try/catch`) **DO**:
    //    do duoc tren ban GOC, cung kich ban nay cho `exit 1` + `ERR_HTTP_HEADERS_SENT`.
    const sanPham = await chayMotLuot("san-pham");
    assert.equal(
      sanPham.exit,
      null,
      `SAN PHAM (\`dev-server.mjs\`) THOAT (exit ${sanPham.exit}) khi upstream chet giua mot response `
        + "DAI. Day chinh la loi o dong 97 cua EVIDENCE §7 (ERR_HTTP_HEADERS_SENT). "
        + `stderr: ${sanPham.stderr}`,
    );
    assert.equal(
      sanPham.coLoiHeader,
      false,
      `san pham khong duoc co ERR_HTTP_HEADERS_SENT; stderr: ${sanPham.stderr}`,
    );
    // 🔴 LUOT 2 — DOI CHUNG: ban GOC (handler khong guard, khong `try/catch`) PHAI CHET. Khong co
    //    ve nay thi "san pham song" khong chung minh duoc gi (co the kich ban nay khong bao gio
    //    cham duong crash).
    const goc = await chayMotLuot("goc");
    assert.notEqual(
      goc.exit,
      null,
      "ban GOC (handler khong guard) phai THOAT khi upstream chet giua mot response DAI — "
        + `neu khong, phep do KHONG trung cua so §7. stderr: ${goc.stderr}`,
    );
    assert.ok(
      goc.coLoiHeader,
      `ban GOC phai nem ERR_HTTP_HEADERS_SENT; stderr: ${goc.stderr}`,
    );
  });

  it("A0) TRUOC/SAU: `writeHead(502)` cua proxy PHAI nam sau mot lan kiem `headersSent`", () => {
    // 🔴 BAI NAY TON TAI VI MOT PHEP DO DOI CHUNG KHONG DU. Do duoc: handler CO guard va handler
    // KHONG guard chi phan biet duoc nhau o nhanh `res.headersSent === false` (chi dong
    // `writeHead(502)` moi nem duoc) — va o nhanh do thi CA HAI ban deu chet khi bi kich bang
    // `emit('error')` (vi phep tiem do khong dong bo voi TCP). Nhanh `res.destroy()` (da gui
    // header) thi ca hai ban deu song. ⇒ Do duoc: mutant `if (false)` SONG SOT qua bai A2.
    //
    // ⇒ Phai ghim o TANG MA NGUON: dong `res.writeHead(502 …)` PHAI duoc bao ve boi mot lan
    // kiem `res.headersSent` dung TRUOC no. Khong co bai nay thi ban va co the bi go ma khong
    // ai thay (ERRATA #45 muc 1: mot menh de khong co gi lam no sai duoc).
    const nguon = readFileSync(`${FRONTEND_DIR}dev-server.mjs`, "utf8");
    const viTriGuard = nguon.indexOf("if (res.headersSent) {");
    const viTriWrite = nguon.indexOf('res.writeHead(502, { "content-type": TYPES[".json"] })');
    assert.notEqual(viTriGuard, -1, "phai co `if (res.headersSent) {` trong dev-server.mjs");
    assert.notEqual(viTriWrite, -1, "phai con dong `res.writeHead(502, …)` cho nhanh chua gui header");
    assert.ok(
      viTriGuard < viTriWrite,
      "lan kiem `headersSent` phai nam TRUOC dong `writeHead(502)` — nguoc lai thi no vo dung",
    );
    // Va nhanh da gui header phai CAT socket, khong viet them gi (`res.destroy()`).
    assert.ok(
      nguon.includes("res.destroy();"),
      "nhanh da gui header phai `res.destroy()` — viet them vao response da gui la nem ra ngoai",
    );
  });

  it("A2) DOI CHUNG: handler loi KHONG guard GIET tien trinh, handler cua worktree thi khong", async () => {
    if (coCong) {
      assert.ok(true, `cong ${DEV_PORT} dang bi chiem ⇒ bo qua phep do (khong ket luan gi)`);
      return;
    }
    // Mot kich ban, HAI ban sao: chi khac khoi handler loi. Xem docblock `dev-server-copy.mjs`
    // ve ly do phep kich la mot PHEP TIEM CO CHU, va ve cot `headersSent` da do duoc.
    //
    // 🔴 TIN HIEU PHAI LA `finish`, KHONG phai mot vong `fetch` da xong — mot lan vap that:
    // ban dau bai nay danh dau request bang mot vong `fetch` roi moi kich, va no bao **PASS**
    // trong khi mutant `if (false)` (bo guard `headersSent`) **SONG SOT**. Nguyen nhan: `res` cua
    // vong `fetch` do van co `headersSent === false`. Cho `finish` ⇒ `headersSent === true`
    // ⇒ nhanh `res.destroy()` duoc thi hanh.
    const chayMotLuot = async (kieu) => {
      const dich = `${FRONTEND_DIR}dev-server.${kieu}.mjs`;
      banCoCongDieuKhien(FRONTEND_DIR, dich, kieu);
      const debugPort = kieu === "goc" ? 8898 : 8897;
      const nhan = `a2-${kieu}`;
      const gia = backendGia();
      const bePort = await listen(gia.server);
      const child = spawn(process.execPath, [dich], {
        cwd: FRONTEND_DIR,
        stdio: ["ignore", "ignore", "pipe"],
        windowsHide: true,
        env: {
          ...process.env,
          PHUDE_BACKEND_PORT: String(bePort),
          PHUDE_DEBUG_PORT: String(debugPort),
          PHUDE_T12_GUARD: "sau-finish",
        },
      });
      const vet = [];
      child.stderr.on("data", (b) => vet.push(String(b)));
      const ket = { kieu, vet: () => vet.join("") };
      try {
        const len = await choToi(async () => {
          const r = await fetch(`http://127.0.0.1:${DEV_PORT}/api/status`, {
            signal: AbortSignal.timeout(2000),
          });
          return r.status === 200;
        }, 40_000);
        assert.ok(len, `ban sao ${kieu} khong len; stderr: ${ket.vet().slice(0, 400)}`);
        assert.ok(await choToi(() => congDangMo(debugPort), 5000, 100), `cong ${debugPort} khong mo`);

        const xemMau = () =>
          fetch(`http://127.0.0.1:${debugPort}/debug/cho?t12=${nhan}`, {
            signal: AbortSignal.timeout(2000),
          }).then((r) => r.text(), () => "khong doc duoc");

        // Request mang nhan se bi kich, roi cho TIN HIEU `finish` (response DA gui header).
        const p = fetch(`http://127.0.0.1:${DEV_PORT}/api/status?t12=${nhan}`, {
          signal: AbortSignal.timeout(3000),
        }).then(
          (r) => ({ k: "res", s: r.status }),
          (e) => ({ k: "err", n: e.name }),
        );
        let mau = "khong doc duoc";
        const het = Date.now() + 5000;
        while (Date.now() < het) {
          mau = await xemMau();
          if (mau.includes("finish=true")) break;
          await new Promise((r) => setTimeout(r, 100));
        }
        ket.mau = mau;
        await p;

        // Kich handler loi. Tren ban `goc`, loi goi nay HONG vi tien trinh chet ngay ben trong
        // handler — do la BANG CHUNG, khong phai loi cua bai test.
        ket.kich = await fetch(`http://127.0.0.1:${debugPort}/debug/no?t12=${nhan}`, {
          signal: AbortSignal.timeout(4000),
        }).then(
          (r) => `http ${r.status}`,
          (e) => `hong: ${e.name}`,
        );
        await new Promise((r) => setTimeout(r, 1200));
        ket.exit = child.exitCode;
        ket.coLoiHeader = ket.vet().includes("ERR_HTTP_HEADERS_SENT");
        ket.request = await p;
      } finally {
        await dung(child);
        await new Promise((r) => gia.server.close(r));
      }
      return ket;
    };

    const goc = await chayMotLuot("goc");
    const nguyen = await chayMotLuot("nguyen");

    // 🔴 VE A — BAN GOC (blob `ccb4480`) CHET: day la RED cua ban va, va la loi EVIDENCE §7.
    assert.notEqual(
      goc.exit,
      null,
      "ban GOC (handler khong guard) phai THOAT khi handler loi chay — neu khong, phep kich "
        + `khong trung cua so §7 (mau=${goc.mau}; kich=${goc.kich})`,
    );
    assert.ok(
      goc.coLoiHeader,
      `ban GOC phai nem ERR_HTTP_HEADERS_SENT; stderr: ${goc.vet().slice(0, 400)}`,
    );
    // 🔴 VE B — BAN CUA WORKTREE SONG, stderr SACH.
    assert.equal(
      nguyen.exit,
      null,
      `ban cua WORKTREE THOAT (exit ${nguyen.exit}) khi handler loi chay (mau=${nguyen.mau}; `
        + `kich=${nguyen.kich}). Day la loi ERR_HTTP_HEADERS_SENT cua EVIDENCE §7. `
        + `stderr: ${nguyen.vet().slice(0, 500)}`,
    );
    assert.equal(
      nguyen.coLoiHeader,
      false,
      `ban cua WORKTREE khong duoc co ERR_HTTP_HEADERS_SENT; stderr: ${nguyen.vet().slice(0, 400)}`,
    );
    // 🔴 BANG CHUNG PHEP KICH ROI DUNG NHANH `res.destroy()`: response da `finish`
    // (header DA gui). Neu khang dinh nay sai thi bai test KHONG do nhanh `headersSent` —
    // va do la mot LO HONG DO PHU (mutant `if (false)` se SONG SOT).
    assert.ok(
      nguyen.mau.includes("finish=true"),
      `phep kich PHAI roi vao nhanh \`res.headersSent === true\`; doc lai duoc: ${nguyen.mau}`,
    );
  });

  it("B+C) PHUDE_BACKEND_PORT: request di toi DUNG cong backend da dat, va giu nguyen duong dan", async () => {
    if (coCong) {
      assert.ok(true, `cong ${DEV_PORT} dang bi chiem ⇒ bo qua phep do (khong ket luan gi)`);
      return;
    }
    const gia = backendGia();
    const bePort = await listen(gia.server);
    const child = spawnDevServer({ PHUDE_BACKEND_PORT: String(bePort) });
    try {
      const len = await choDevServerLen(child);
      assert.ok(
        len.len,
        `dev-server khong len: thoat=${len.thoat} (exit ${child.exitCode}); stderr: ${len.stderr}`,
      );

      const thay = await choToi(() => gia.nhanDuoc.length > 0, 5000);
      assert.ok(
        thay,
        `backend gia o cong ${bePort} KHONG nhan duoc request nao ⇒ proxy van di 8620 (cung). `
        + "Doi cong backend bang `PHUDE_BACKEND_PORT`.",
      );
      assert.ok(
        gia.nhanDuoc.includes("/api/status"),
        `duong dan phai duoc giu nguyen, do duoc: ${JSON.stringify(gia.nhanDuoc)}`,
      );
    } finally {
      await dung(child);
      await new Promise((r) => gia.server.close(r));
    }
  });

  it("D) KHONG dat env ⇒ mac dinh VAN la 8620 (cau 502 phai neu dung cong do)", async () => {
    if (coCong) {
      assert.ok(true, `cong ${DEV_PORT} dang bi chiem ⇒ bo qua phep do (khong ket luan gi)`);
      return;
    }
    const nam8620 = await congDangMo(8620);
    const child = spawnDevServer({ PHUDE_BACKEND_PORT: undefined });
    try {
      const r = await fetch(`http://127.0.0.1:${DEV_PORT}/api/status`, {
        signal: AbortSignal.timeout(8000),
      }).catch(() => null);
      if (r !== null && r.status === 502) {
        const body = await r.text();
        assert.ok(
          body.includes("8620"),
          `cau 502 phai neu dung cong mac dinh 8620, do duoc: ${JSON.stringify(body)}`,
        );
      } else {
        assert.ok(
          true,
          `8620 ${nam8620 ? "co" : "khong"} tra loi, proxy tra ${r === null ? "loi" : r.status} `
          + "⇒ bo qua phep do chuoi thong bao (khong ket luan gi)",
        );
      }
      assert.equal(child.exitCode, null, "dev-server khong duoc thoat");
    } finally {
      await dung(child);
    }
  });
});
