/**
 * Dung ban sao `dev-server.mjs` CO CONG DIEU KHIEN — dung cho phep kich A2 cua Task 12.
 *
 * ## Vi sao can mot ban sao, va ban sao duoc dung tu dau
 *
 * Cua so cua EVIDENCE §7 = handler loi cua proxy goi `writeHead` khi header DA gui. DO DUOC (bao
 * cao Task 12, T1): bon kich ban TCP THAT tu ngoai (RST sau header, chunked dut giua, 101 upgrade
 * roi chet, client huy giua body) deu cho `headersSent = false` ⇒ khong mo duoc cua so do. No la
 * MOT KHOANG THOI GIAN, khong phai mot hinh dang goi y.
 *
 * ⇒ Hai ve cua ban sao, moi ve vi mot ly do khac nhau:
 *  - **Cau hinh** (`PHUDE_BACKEND_PORT`) lay tu **WORKTREE** dang duoc do — neu khong, bai test se
 *    do mot ban KHONG co khai nien do.
 *  - **Handler loi** lay tu **BLOB `HEAD`** (ban KHONG kiem `headersSent`) — neu khong, cua so §7
 *    khong con ton tai va bai test **tu vo hieu** (phep do tu thoa man, ERRATA #26 muc 5).
 *    ⚠️ Chinh vi vay phep kich moi la "CO KICH": no do **PHAN CON LAI cua ban va** (khong duoc nem
 *    loi ra ngoai), chu KHONG do rang buoc "backend that bi cat" (da do o A1, khong kich).
 *
 * ⚠️ Ban sao PHAI nam CANH `dev-server.mjs` (cung thu muc `frontend/`), vi Node resolve
 * `./rollup.config.mjs` theo DUONG DAN TEP. Mot ban sao sau mot cap (vi du `.t12-tam/`) se chet
 * `ERR_MODULE_NOT_FOUND` — do la mot ket luan SAI ve san pham (da vap dung loi nay HAI lan).
 *
 * ## Cach kich — va vi sao phai CHON DUNG request
 *
 * ⚠️ DO DUOC (mot lan vap that): neu ghi lai MOI request di qua proxy thi `dangBay` chua ca nhung
 * request da DUT (vi du `/api/status` cua vong do readiness) ⇒ `res.headersSent` luc kich la
 * `true` ⇒ ban DAY DU cung nem ⇒ bai test bao mot loi KHONG TON TAI. Vi vay ban sao CHI ghi lai
 * khi duong dan mang `?t12=<nhan>` — do la mot lua chon TUONG MINH cua bai test.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

import { layKhoiHandler } from "./khoi-handler.mjs";

/** Nhan cua request duoc ghi lai (query `?t12=…`). Phai khop `test/dev-server.test.mjs`. */
export const NHAN = "t12";

/** Khoi handler loi KHONG guard — "cua so §7". */
export const HANDLER_GOC = [
  'proxied.on("error", () => {',
  '      res.writeHead(502, { "content-type": TYPES[".json"] }).end(\'{"error":"backend 8620 khong truy cap duoc"}\');',
  "    });",
].join("\n");

/** Ghi ban sao co cong dieu khien ra `dich`.
 *
 * `kieu`:
 *  - `"goc"` (mac dinh) — THAY khoi handler loi bang ban KHONG guard cua `HEAD` ⇒ do cua so §7.
 *  - `"nguyen"` — GIU NGUYEN handler cua worktree ⇒ do chinh ban dang duoc danh gia.
 *
 * Hai kieu nay la MOT PHEP DO DOI CHUNG: cung mot kich ban kich, cung mot ban sao — chi khac khoi
 * handler. Mot minh kieu `"nguyen"` khong chung minh duoc gi (no chi noi "ban va khong chet"), va
 * mot minh kieu `"goc"` cung vay (no chi noi "ban cu chet").
 *
 * ## Ket qua DO DUOC cua phep kich (bao cao Task 12, T1)
 *
 * | Request dang bay | `headersSent` luc kich | `goc` | `nguyen` |
 * |---|---|---|---|
 * | `/api/status` (da dut) | **true** | **`exit 1` + `ERR_HTTP_HEADERS_SENT`** | **SONG**, stderr sach |
 * | `/api/cham` (dang bay, backend nghi 900 ms) | false | `exit 1` | `exit 1` |
 *
 * ⇒ Cua so §7 tai lap duoc la **`headersSent = true`** (request DA gui header cho client). Cot thu
 * hai (`false`) thi CA HAI ban deu chet, vi `emit("error")` la mot phep tiem **khong dong bo voi
 * TCP**: luc handler chay thi socket da ghi header xuong duong truyen, con `res.headersSent` thi
 * con la `false`. Day la mot PHEP DO, khong phai mot loi khai — va no la ly do bai test chi do cot
 * thu nhat.
 */
export function banCoCongDieuKhien(frontendDir, dich, kieu = "goc") {
  if (kieu !== "goc" && kieu !== "nguyen") {
    throw new Error(`kieu khong hop le: ${kieu}`);
  }
  const worktree = readFileSync(`${frontendDir}dev-server.mjs`, "utf8");
  const crlf = worktree.includes("\r\n");
  const handlerHienTai = layKhoiHandler(worktree, 'proxied.on("error"').khoi;
  const handlerGoc = crlf ? HANDLER_GOC.replace(/\n/g, "\r\n") : HANDLER_GOC;
  if (handlerHienTai === handlerGoc) {
    throw new Error(
      "handler loi cua WORKTREE da la ban KHONG guard ⇒ phep kich A2 khong con do duoc cua so §7",
    );
  }
  const neoPort = "const PORT = 3100;";
  const neoGan = "    req.pipe(proxied);";
  for (const [neo, soLan] of [[neoPort, 1], [neoGan, 1]]) {
    if ((worktree.split(neo).length - 1) !== soLan) {
      throw new Error(`worktree khong con dung hinh dang da do: ${JSON.stringify(neo)}`);
    }
  }

  const chuanHoa = (khoi) => (crlf ? khoi.join("\n").replace(/\n/g, "\r\n") : khoi.join("\n"));
  const chen = chuanHoa([
    "// ── CHI DE DO (Task 12, ve A2): cong dieu khien tren cong RIENG, chi mo khi dat",
    "// `PHUDE_DEBUG_PORT`. Khong dat ⇒ khong co cong nao, khong co be mat moi trong san pham.",
    "//",
    "// `/debug/treo` doc lai trang thai (KHONG cham vao `res` nao), `/debug/no` kich handler loi",
    "// cua request DA CHON (`?t12=<nhan>`) va tra ve `headersSent` NGAY TRUOC khi kich.",
    "const dangBay = new Map();",
    "let lanKich = 0;",
    "if (process.env.PHUDE_DEBUG_PORT) {",
    "  const { createServer: taoCongDieuKhien } = await import(\"node:http\");",
    "  taoCongDieuKhien((dq, tra) => {",
    "    const q = new URL(dq.url ?? \"/\", \"http://127.0.0.1\");",
    "    const nhan = q.searchParams.get(\"t12\") ?? \"t12\";",
    "    const bay = dangBay.get(nhan);",
    "    if (q.pathname === \"/debug/cho\") {",
    "      // TIN HIEU, khong phai dong ho: `finish` = response nay DA GUI HEADER xong.",
    "      // ⚠️ DO DUOC (mot lan vap that): mot vong `fetch` da xong KHONG bao ham dieu nay —",
    "      // `res.headersSent` van co the la false. Neu do bang vong `fetch` thi phep kich roi",
    "      // vao SAI nhanh, va mutant `if (false)` (bo guard) SONG SOT.",
    "      tra.writeHead(200, { \"content-type\": \"text/plain\" });",
    "      tra.write(\"soCap=\" + dangBay.size + \";\" + [...dangBay.entries()].map(",
    "        (cap) => cap[0] + \":\" + (cap[1].daGui ? \"finish=true\" : \"finish=false\")).join(\",\"));",
    "      tra.end();",
    "      return;",
    "    }",
    "    if (q.pathname === \"/debug/no\") {",
    "      if (bay === undefined) { tra.writeHead(409).end(\"khong co request mang nhan \" + nhan); return; }",
    "      lanKich += 1;",
    "      // ⚠️ DO DUOC: handler CO guard va handler KHONG guard chi PHAN BIET duoc nhau o nhanh",
    "      // `res.headersSent === false` (chi dong `writeHead(502)` moi nem duoc). Nhanh",
    "      // `res.destroy()` (da gui header) thi CA HAI ban deu song — nghia la mutant",
    "      // `if (false)` SONG SOT neu bai test chi do nhanh do. Vi vay bai test phai ghim",
    "      // `if (res.headersSent)` o TANG MA NGUON (xem `dev-server.test.mjs`, bai",
    "      // \"A0) TRUOC/SAU …\") — mot khang dinh TRUNG THUC ve gioi han cua phep kich nay.",
    "      tra.writeHead(200, { \"content-type\": \"text/plain\" })",
    "        .end(\"da kich; daGui=\" + bay.daGui);",
    "      bay.proxied.emit(\"error\", new Error(\"T12 kich lan \" + lanKich + \": upstream bao loi\"));",
    "      return;",
    "    }",
    "    tra.writeHead(404).end();",
    "  }).listen(Number(process.env.PHUDE_DEBUG_PORT), \"127.0.0.1\");",
    "}",
    "",
  ]);

  // Ghi lai cap (`proxied`, `res`) CHI khi duong dan mang `?t12=<nhan>` — xem docblock.
  // `daGui` duoc dat bang su kien `finish` cua `res` (TIN HIEU, khong phai dong ho).
  const neoGhi = chuanHoa([
    "    if (process.env.PHUDE_DEBUG_PORT) {",
    "      const nhan = (req.url ?? \"\").match(/[?&]t12=([^&]+)/);",
    "      if (nhan !== null) {",
    "        const muc = { proxied, res, daGui: false };",
    "        res.on(\"finish\", () => { muc.daGui = true; });",
    "        dangBay.set(decodeURIComponent(nhan[1]), muc);",
    "      }",
    "    }",
    neoGan,
  ]);

  const ra = (kieu === "goc" ? worktree.replace(handlerHienTai, handlerGoc) : worktree)
    .replace(neoGan, neoGhi)
    .replace(neoPort, chen + neoPort);
  mkdirSync(dirname(dich), { recursive: true });
  writeFileSync(dich, ra, "utf8");
  return dich;
}
