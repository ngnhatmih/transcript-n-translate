/**
 * Ghim CHINH harness DOM (`test/dom.ts`) — khong phai mot tinh nang, ma la thu moi
 * suite DOM cua T5–T11 se dung.
 *
 * Vi sao phai ghim: `--test-isolation=none` nghia la MOI tep test chung MOT tien
 * trinh (ERRATA #7 muc 3). Hai kieu hong cua harness nay deu thuoc loai XANH GIA —
 * suite sau chay dung nhung do sai thu:
 *
 *  1. `setupDom(origin2)` khi da co DOM cua `origin1` bi BO QUA IM LANG ⇒ fetch
 *     cua suite thu hai go cua server cua suite thu nhat (khong gi bao). Bai
 *     "hai origin" duoi day dung HAI server `node:http` THAT tren `listen(0)` va
 *     DEM so request moi server nhan — dem la bang chung, khong phai suy luan.
 *  2. `teardownDom()` tra `globalThis.fetch` nhung de TAM global khac
 *     (`window`, `document`, `navigator`, `HTMLElement`, `Node`, `Event`,
 *     `MouseEvent`, `getComputedStyle`) tro vao jsdom da `close()`. Bai
 *     "tra het global" so sanh THAM CHIEU (`===`) voi gia tri chup TRUOC
 *     `setupDom` — ke ca `undefined`.
 *
 * ⚠️ ĐÍNH CHÍNH (`M1`, trả ở Task 4). Bản đầu của đoạn này viết: *"thứ tự bài trong tệp
 * này là CỐ Ý để ảnh chụp là trạng thái nguyên bản"*. Câu đó ĐÚNG khi chạy LẺ tệp này,
 * nhưng SAI trong lượt ĐẦY ĐỦ: dưới `--test-isolation=none`, hook cấp TỆP bị node:test
 * kéo lên GỐC cả lượt chạy (mọi `before` trước MỌI bài, mọi `after` sau MỌI bài — đo
 * bằng đồng hồ chung, ERRATA #9 mục 1). Thứ tự KHAI BÁO trong tệp không mua được gì
 * khi cả lượt chạy chung một tiến trình.
 *
 * Thứ bảo đảm ảnh chụp là trạng thái NGUYÊN BẢN là LỜI GỌI CHUẨN HOÁ `teardownDom()` ở
 * đầu MỖI bài dưới đây — không phải thứ tự bài. Reviewer đã đo điều đó bằng mutation
 * `H1b` (bỏ lời gọi ⇒ CẢ HAI bài cùng đỏ) trong bố cục CŨ, khi `useJobStream.test.ts`
 * còn để `before` ở cấp TỆP: lúc đó jsdom của tệp kia sống suốt lượt, nên lời gọi ở đây
 * là thứ ĐÓNG nó.
 *
 * Task 4 chuyển hook của `useJobStream.test.ts` vào `describe()`, và việc đó KHÔNG tự
 * nguyện: thêm `src/shell/App.test.tsx` (đứng TRƯỚC theo thứ tự đường dẫn) làm đỏ ĐÚNG
 * NĂM bài của tệp kia bằng `ReferenceError: document is not defined` — vì chuẩn hoá của
 * tệp mới đóng jsdom mà hook cấp tệp của tệp cũ đã cài lúc t≈0. Sau khi chuyển, H1b được
 * ĐO LẠI và **không giết bài nào** (`pass 48 / fail 2`, đúng hai guard `EMPTY_DB_MSG`).
 * ⇒ Từ đây lời gọi chuẩn hoá là PHÒNG THỦ, không còn là thứ mà một mutation chứng minh:
 * nó ở lại vì mỗi bài DOM phải bắt đầu từ một trạng thái XÁC ĐỊNH, không phụ thuộc thứ
 * tự tệp (ERRATA #9 mục 6) — và vì một bài chết giữa chừng không được để jsdom lại cho
 * bài sau.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import type { Server } from "node:http";
import type { AddressInfo, Socket } from "node:net";

import { setupDom, teardownDom, guardGlobalLucThoat } from "./dom.ts";

// ⚠️ NO DEBT `I1` — guard luc THOAT TIEN TRINH, dang ky o cap MODULE (khong trong hook:
// no chi DANG KY mot listener, khong dat global nao). Ly do no phai ton tai o day thay vi
// mot bai test: mutation `R4` (`luuGlobal()` luon chup lai) lam ro ri 10/10 global ma
// `npm test` VAN XANH — khong bai nao trong luot chay thay duoc, vi moi bai deu tu chuan
// hoa truoc khi do. Xem `guardGlobalLucThoat()` trong `test/dom.ts`.
guardGlobalLucThoat();

/** Sau global ma `setupDom` dat vao `globalThis` — va `teardownDom` PHAI tra lai. */
const DOM_GLOBALS = [
  "window",
  "document",
  "navigator",
  "HTMLElement",
  "Node",
  "Event",
  "MouseEvent",
  "getComputedStyle",
  "fetch",
] as const;

const g = globalThis as unknown as Record<string, unknown>;

/** Mo ta mot gia tri global ma KHONG goi getter cua no (an toan voi window da close). */
function mo(value: unknown): string {
  if (value === undefined) return "undefined";
  if (value === null) return "null";
  const kind = typeof value;
  if (kind !== "object" && kind !== "function") return `${kind} ${String(value)}`;
  return Object.prototype.toString.call(value);
}

function coActEnvironment(): boolean {
  return Object.prototype.hasOwnProperty.call(globalThis, "IS_REACT_ACT_ENVIRONMENT");
}

/**
 * `teardownDom` phai tra NGUYEN TRANG moi global no da dat:
 * - co truoc ⇒ dung LAI dung tham chieu do (`===`);
 * - khong co truoc ⇒ phai bi XOA, khong duoc de lai `undefined`.
 */
test("teardownDom tra HET global ve dung gia tri truoc setupDom (khong chi fetch)", () => {
  // Bat dau tu mot trang thai XAC DINH: dong jsdom ma suite/bai TRUOC co the con giu.
  // ⚠️ Truoc Task 4, cho nay la thu ĐÓNG jsdom cua `useJobStream.test.ts` — hook cấp TỆP
  // của tệp đó bị kéo lên GỐC nên jsdom của nó sống suốt lượt chạy (ERRATA #9 mục 1).
  // Task 4 đã bọc hook đó vào `describe()`, nên từ đây lời gọi này là PHÒNG THỦ: nó bảo
  // đảm bài này bắt đầu sạch bất kể tệp nào chạy trước và bất kể bài trước có chết giữa
  // chừng hay không. Đo lại `H1b` sau khi chuyển hook: bỏ lời gọi này KHÔNG giết bài nào
  // — xem đầu tệp để có số đo, đừng đọc câu này như một bất biến được mutation chứng minh.
  teardownDom();

  // Tien de, va la mot yeu cau doc lap cua brief: `setupDom` LUON bat co act, nen
  // `teardownDom` phai XOA no khi truoc do no khong ton tai — khong duoc de lai `true`.
  assert.equal(
    coActEnvironment(),
    false,
    "teardownDom phai XOA IS_REACT_ACT_ENVIRONMENT (khong duoc de lai gia tri cu)",
  );

  const truoc = new Map<string, unknown>(DOM_GLOBALS.map((key) => [key, g[key]]));
  const actTruoc = coActEnvironment();

  setupDom("http://127.0.0.1:9");

  // WITNESS: chung minh `setupDom` THAT SU dat cac global — neu khong thi bai nay rong
  // (mot bai xanh vi khong do duoc gi cung la xanh gia).
  const witness: string[] = [];
  for (const key of DOM_GLOBALS) {
    if (g[key] === truoc.get(key)) witness.push(`${key} khong doi`);
  }
  if (g.IS_REACT_ACT_ENVIRONMENT !== true) witness.push("IS_REACT_ACT_ENVIRONMENT khong duoc bat");
  assert.deepEqual(
    witness,
    [],
    `tien de cua bai nay khong dung (setupDom khong dat global nao do):\n  ${witness.join("\n  ")}`,
  );

  teardownDom();

  const ro: string[] = [];
  for (const key of DOM_GLOBALS) {
    const sau = g[key];
    if (sau !== truoc.get(key)) {
      ro.push(`${key}: truoc=${mo(truoc.get(key))} / sau=${mo(sau)}`);
    }
  }
  if (coActEnvironment() !== actTruoc) {
    ro.push(`IS_REACT_ACT_ENVIRONMENT: truoc=${actTruoc} / sau=${coActEnvironment()}`);
  }

  assert.deepEqual(
    ro,
    [],
    "teardownDom CHUA tra het global (con tro vao jsdom da close()) — so sanh la THAM CHIEU `===`:\n  "
      + ro.join("\n  "),
  );
});

interface ServerTest {
  origin: string;
  dem: () => number;
  dong: () => Promise<void>;
}

/** Server `node:http` THAT tren cong trong (`listen(0)`) — khong giam cong cua ai. */
async function moServer(nhan: string): Promise<ServerTest> {
  let dem = 0;
  const sockets = new Set<Socket>();
  const server: Server = createServer((_req, res) => {
    dem += 1;
    res.writeHead(200, { "content-type": "text/plain" });
    res.end(nhan);
  });
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.on("close", () => sockets.delete(socket));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
  const { port } = server.address() as AddressInfo;
  return {
    origin: `http://127.0.0.1:${port}`,
    dem: () => dem,
    dong: () =>
      new Promise<void>((resolve) => {
        for (const socket of [...sockets]) socket.destroy();
        sockets.clear();
        server.close(() => resolve());
      }),
  };
}

/**
 * `setupDom` goi lan hai voi origin KHAC khong duoc IM LANG bo qua: request tuong
 * doi sau do phai toi server THU HAI, va `document` phai la DOM MOI.
 */
test("setupDom lan hai voi origin KHAC: fetch phai toi server2, khong duoc im lang bo qua", async () => {
  const mot = await moServer("server1");
  const hai = await moServer("server2");
  const loi: string[] = [];
  try {
    // Trang thai XAC DINH truoc khi do (cung ly do nhu bai "tra het global").
    teardownDom();

    setupDom(mot.origin);
    const domMot = globalThis.document;

    // WITNESS: cau noi URL chay that va dang tro server1.
    const bodyMot = await (await fetch("/api/x")).text();
    if (bodyMot !== "server1") loi.push(`request dau phai toi server1, body do duoc "${bodyMot}"`);
    if (mot.dem() !== 1) loi.push(`server1 phai nhan dung mot request, do duoc ${mot.dem()}`);
    if (hai.dem() !== 0) loi.push(`server2 chua duoc goi, do duoc ${hai.dem()}`);

    // Lan goi thu hai voi ORIGIN KHAC — tren ma chua sua thi day la `return` im lang.
    setupDom(hai.origin);

    const domHai = globalThis.document;
    if (domHai === domMot) {
      loi.push("setupDom(origin2) KHONG dung lai DOM: `document` van la jsdom cu");
    }

    const bodyHai = await (await fetch("/api/x")).text();
    if (hai.dem() !== 1) loi.push(`server2 phai nhan dung mot request, do duoc ${hai.dem()}`);
    if (mot.dem() !== 1) loi.push(`server1 KHONG duoc nhan them request, do duoc ${mot.dem()}`);
    if (bodyHai !== "server2") loi.push(`request thu hai phai toi server2, body do duoc "${bodyHai}"`);

    assert.deepEqual(
      loi,
      [],
      `"hai origin" hong (so request: server1=${mot.dem()}, server2=${hai.dem()}):\n  ${loi.join("\n  ")}`,
    );
  } finally {
    teardownDom();
    await mot.dong();
    await hai.dong();
  }
});
