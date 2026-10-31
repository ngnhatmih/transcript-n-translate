/**
 * Driver CDP cho **Chrome THẬT** — chạy kế hoạch `nav/waitFor/waitText/click/radio/key/eval/shot`
 * trên app đang phục vụ ở `http://127.0.0.1:3100`.
 *
 * ## Vì sao Node thuần, không Playwright
 *
 * Node 24 có `WebSocket` toàn cục (undici) ⇒ không cần thư viện nào. `@playwright/test` **không**
 * có trong `package.json`, và script `"e2e": "playwright test"` cũ là một script **không bao giờ
 * chạy được** (ERRATA #5 mục 4 — đã bỏ ở Task 12).
 *
 * ## Vì sao tầng này KHÔNG nằm trong `npm test`
 *
 * Nó cần **quyền rộng** để mở Chrome, và trong sandbox bị hạn chế Chromium chết
 * (`FATAL:mojo… Access is denied (0x5)` — ERRATA #40: mệnh đề đúng là "không mở được DƯỚI CÁC CHẾ
 * ĐỘ SANDBOX HẠN CHẾ"). `npm test` phải chạy được ở mọi nơi ⇒ tầng này tách riêng, có README.
 *
 * ## LUẬT ĐO (ERRATA #47 mục 5 + mục 6) — ba luật được cài thẳng vào driver
 *
 * 1. **Kiểm URL TRƯỚC khi tác động** (`Page.navigate` + `waitFor` neo dữ liệu). Không bao giờ
 *    giả định tab đang mở là tab của mình (một script cũ đã `location.reload()` tab `x.com` của
 *    người dùng).
 * 2. **Luôn cài ĐẦU DÒ `keydown` trên trang** trước khi phát phím ⇒ phân biệt *"sự kiện KHÔNG
 *    TỚI"* với *"app KHÔNG XỬ LÝ"*. Thiếu đầu dò thì mọi kết luận "phím không chạy" đều là
 *    **artifact**. ⚠️ **Vòng sửa 1 (`I2`) đã sửa đúng chỗ này**: bản cũ cài đầu dò **một lần TRƯỚC
 *    bước `nav` đầu tiên** ⇒ điều hướng xoá nó, và `xoaDauDo` lại gắn mảng rỗng KHÔNG listener
 *    ⇒ đầu dò **không hề tồn tại lúc chạy**. Nay đầu dò được cài **sau mỗi `nav`** và **trước mỗi
 *    phím**, và một bước `key` đọc ra đầu dò **rỗng** làm **lượt đó ĐỎ** (không còn im lặng).
 * 3. **Phím phải có HÌNH DẠNG NGƯỜI THẬT**: `?` **kèm `Shift`**; `Enter` **kèm pha ký tự**
 *    (`text: "\r"`). Hai lần trong một lượt, "phím không chạy" là do **phép tiêm** (ERRATA #47
 *    mục 5).
 * 4. **Chờ theo TÍN HIỆU** (selector/chữ), `timeout` chỉ là HẠN CHÓT (ERRATA #35 mục 2).
 */
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

/** Chờ tối đa `ms`; dùng cho hạn chót, không phải nhịp. */
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Port CDP — KHÁC `9222` để không bao giờ đụng Chrome của người dùng. */
export const CDP_PORT = Number(process.env.PHUDE_CDP_PORT ?? 9229);

/** Kết nối tới Chrome đang chạy với `--remote-debugging-port=<CDP_PORT>`. */
export async function ketNoi({ port = CDP_PORT, timeoutMs = 30_000 } = {}) {
  const het = Date.now() + timeoutMs;
  for (;;) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return await moWebSocket(page, port);
    } catch {
      // Chrome chua len, hoac chua co tab nao — thu lai.
    }
    if (Date.now() > het) {
      throw new Error(
        `khong ket noi duoc CDP o cong ${port} sau ${timeoutMs} ms. `
        + "Chrome da mo voi `--remote-debugging-port` chua? (xem README.md)",
      );
    }
    await sleep(250);
  }
}

async function moWebSocket(page, port) {
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.onopen = res;
    ws.onerror = () => rej(new Error(`khong mo duoc WebSocket CDP (cong ${port})`));
  });

  let seq = 0;
  const pending = new Map();
  const nhat = [];
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m);
      pending.delete(m.id);
      return;
    }
    nhat.push(m);
  };
  const send = (method, params = {}) =>
    new Promise((res, rej) => {
      const id = ++seq;
      pending.set(id, res);
      ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (pending.has(id)) {
          pending.delete(id);
          rej(new Error(`CDP ${method} khong tra loi sau 20 s`));
        }
      }, 20_000);
    });

  const goi = async (expression) => {
    const r = await send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (r.result?.exceptionDetails) {
      return { loi: r.result.exceptionDetails.text ?? "loi khong ro" };
    }
    return { giaTri: r.result?.result?.value };
  };

  await send("Page.enable");
  await send("Runtime.enable");
  await send("DOM.enable");
  return { send, goi, ws, port, nhat };
}

/* ────────────────────────────── DSL của kế hoạch ────────────────────────────── */

/** Chờ theo TÍN HIỆU: `chon` (selector) hoặc `chu` (chữ trong `body.innerText`). */
export async function cho(driver, { chon, chu, timeout = 20_000 }) {
  const het = Date.now() + timeout;
  for (;;) {
    const bieuThuc = chon !== undefined
      ? `!!document.querySelector(${JSON.stringify(chon)})`
      : `(document.body ? document.body.innerText : "").includes(${JSON.stringify(chu)})`;
    const kq = await driver.goi(bieuThuc);
    if (kq.giaTri === true) return true;
    if (Date.now() > het) return false;
    await sleep(100);
  }
}

/**
 * Cài ĐẦU DÒ `keydown` trên trang (bọc một lần, idempotent TRONG CÙNG một tài liệu).
 *
 * 🔴 Đây là thứ DUY NHẤT phân biệt *"sự kiện không tới"* với *"app không xử lý"* (ERRATA #47 mục 5).
 *
 * ⚠️ **VÒNG SỬA 1 (I2) — BẢN CŨ KHÔNG HỀ CÀI ĐẦU DÒ.** Hai lỗi, cả hai đo được:
 *  1. `chayKeHoach` gọi `caiDauDo` **TRƯỚC** bước `nav` đầu tiên ⇒ điều hướng tạo **tài liệu mới**
 *     và xoá luôn `window.__t12DauDo`; không ai cài lại ⇒ log của chính phiên chính ghi
 *     `"dau do da cai: KHONG"` và `dauDo: []` cho **cả 6** phím.
 *  2. `xoaDauDo` **TẠO** `window.__t12DauDo = []` mà **KHÔNG** gắn listener ⇒ dù có cài lại thì mỗi
 *     bước `key` (nó gọi `xoaDauDo` trước khi phát phím) vẫn xoá listener đã gắn.
 * ⇒ Nay: hàm cài nằm **TRÊN TRANG** (`__t12CaiDauDo`) và **idempotent theo cờ `__t12DauDoGan`**;
 * `xoaDauDo` xoá mảng **rồi CÀI LẠI**; `chayKeHoach` cài lại **sau mỗi `nav`** và **trước mỗi phím**.
 * Kèm theo: một bước `key` mà đầu đò **rỗng** là một lượt **ĐỎ** (xem `chayKeHoach`), không còn là
 * một con số vô nghĩa được ghi ra rồi bỏ qua.
 */
export async function caiDauDo(driver) {
  const kq = await driver.goi(`(() => {
    if (typeof window.__t12CaiDauDo !== "function") {
      window.__t12CaiDauDo = () => {
        if (window.__t12DauDoGan === true) return "da gan";
        window.__t12DauDoGan = true;
        if (!Array.isArray(window.__t12DauDo)) window.__t12DauDo = [];
        document.addEventListener("keydown", (e) => {
          window.__t12DauDo.push({
            key: e.key, code: e.code, shift: e.shiftKey, ctrl: e.ctrlKey, alt: e.altKey,
            defaultPrevented: e.defaultPrevented,
            dich: (e.target && (e.target.tagName || "")) + "#" + (e.target && (e.target.id || "")),
            luc: Date.now(),
          });
        }, true);
        return "da cai";
      };
    }
    return window.__t12CaiDauDo();
  })()`);
  return kq.loi ?? kq.giaTri;
}

/** Đọc đầu đò. */
export async function docDauDo(driver) {
  const kq = await driver.goi("JSON.stringify(window.__t12DauDo ?? [])");
  return JSON.parse(kq.giaTri ?? "[]");
}

/**
 * Xoá mảng sự kiện **VÀ BẢO ĐẢM** đầu đò đang gắn (idempotent ⇒ **đúng MỘT** listener).
 *
 * ⚠️ Bản cũ chỉ gán `window.__t12DauDo = []` — nó **xoá luôn** listener đã gắn ở lượt trước (nếu có),
 * nên mọi bước `key` đều đọc ra `[]` (I2). Nay việc xoá **không** được phép tháo đầu đò.
 * ⚠️ Và nó cũng **KHÔNG** được hạ cờ `__t12DauDoGan`: đo được một lần vap — hạ cờ rồi cài lại làm
 * **chồng listener** (2 sự kiện cho `?`, 3 cho `Escape` trong cùng một bước), tức một phép đếm
 * "đúng một sự kiện" sau này sẽ sai. Một tài liệu = một listener.
 */
export async function xoaDauDo(driver) {
  await driver.goi("(window.__t12DauDo = []), 'da xoa'");
  return caiDauDo(driver);
}

/**
 * Chờ TÀI LIỆU MỚI sẵn sàng sau `Page.navigate`.
 *
 * ⚠️ Cần thiết vì `Page.navigate` trả về **trước** khi tài liệu mới commit: một `Runtime.evaluate`
 * ngay sau đó có thể chạy trong tài liệu CŨ, và mọi thứ cài vào đó bị xoá khi tài liệu mới hiện ra.
 */
export async function choTaiLieu(driver, { timeout = 20_000, url = null } = {}) {
  const het = Date.now() + timeout;
  for (;;) {
    const kq = await driver.goi(
      "(() => ({ san: document.readyState, href: location.href, co: document.body !== null }))()",
    );
    const v = kq.giaTri;
    if (v && v.co === true && v.san !== "loading" && (url === null || v.href.startsWith(url))) {
      return v;
    }
    if (Date.now() > het) return null;
    await sleep(100);
  }
}

/**
 * Phát MỘT phím có HÌNH DẠNG NGƯỜI THẬT.
 *
 * Bảng hình dạng (do được, ERRATA #47 mục 5 / #13):
 *  - `?`      ⇒ `key: "?"`, `shiftKey: true` (gửi `?` trần là hình dạng KHÔNG TỒN TẠI trên bàn phím;
 *               bảng phím tắt sẽ KHÔNG mở, và đó là lỗi của phép tiêm).
 *  - `Enter`  ⇒ phải có **pha ký tự** `text: "\r"`, nếu không nút native không kích hoạt.
 *  - `Escape`/mũi tên ⇒ `rawKeyDown` + `keyUp`.
 */
export async function phim(driver, ten, { shift = false, ctrl = false, alt = false } = {}) {
  const HINH_DANG = {
    "?": { key: "?", text: "?", code: "Slash", windowsVirtualKeyCode: 191, shift: true },
    "/": { key: "/", text: "/", code: "Slash", windowsVirtualKeyCode: 191 },
    Enter: { key: "Enter", text: "\r", code: "Enter", windowsVirtualKeyCode: 13 },
    Escape: { key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 },
    " ": { key: " ", text: " ", code: "Space", windowsVirtualKeyCode: 32 },
    ArrowLeft: { key: "ArrowLeft", code: "ArrowLeft", windowsVirtualKeyCode: 37 },
    ArrowRight: { key: "ArrowRight", code: "ArrowRight", windowsVirtualKeyCode: 39 },
    "[": { key: "[", text: "[", code: "BracketLeft", windowsVirtualKeyCode: 219 },
    "]": { key: "]", text: "]", code: "BracketRight", windowsVirtualKeyCode: 221 },
    "+": { key: "+", text: "+", code: "Equal", windowsVirtualKeyCode: 187, shift: true },
    n: { key: "n", text: "n", code: "KeyN", windowsVirtualKeyCode: 78 },
    j: { key: "j", text: "j", code: "KeyJ", windowsVirtualKeyCode: 74 },
    k: { key: "k", text: "k", code: "KeyK", windowsVirtualKeyCode: 75 },
    s: { key: "s", text: "s", code: "KeyS", windowsVirtualKeyCode: 83 },
    m: { key: "m", text: "m", code: "KeyM", windowsVirtualKeyCode: 77 },
    "0": { key: "0", text: "0", code: "Digit0", windowsVirtualKeyCode: 48 },
    "1": { key: "1", text: "1", code: "Digit1", windowsVirtualKeyCode: 49 },
    "2": { key: "2", text: "2", code: "Digit2", windowsVirtualKeyCode: 50 },
    "3": { key: "3", text: "3", code: "Digit3", windowsVirtualKeyCode: 51 },
  };
  const hd = ten.length === 1 && /[a-zA-Z]/.test(ten)
    ? { key: ten, text: ten, code: `Key${ten.toUpperCase()}`, windowsVirtualKeyCode: ten.toUpperCase().charCodeAt(0) }
    : HINH_DANG[ten];
  if (hd === undefined) {
    throw new Error(
      `chua khai hinh dang cho phim ${JSON.stringify(ten)}. Them vao bang o \`phim()\` — `
      + "⛔ DUNG gui mot hinh dang doan mo: mot phim sai hinh dang se duoc doc nham la loi san pham.",
    );
  }
  const shiftKey = shift || hd.shift === true;
  const ctrlKey = ctrl;
  const altKey = alt;
  const chung = {
    key: hd.key,
    code: hd.code,
    windowsVirtualKeyCode: hd.windowsVirtualKeyCode,
    nativeVirtualKeyCode: hd.windowsVirtualKeyCode,
    modifiers: (shiftKey ? 8 : 0) | (ctrlKey ? 2 : 0) | (altKey ? 1 : 0),
  };
  await driver.send("Input.dispatchKeyEvent", {
    type: "rawKeyDown", ...chung,
  });
  if (typeof hd.text === "string") {
    await driver.send("Input.dispatchKeyEvent", { type: "char", text: hd.text, ...chung });
  }
  await driver.send("Input.dispatchKeyEvent", { type: "keyUp", ...chung });
  return { key: hd.key, shiftKey, ctrlKey, altKey, coPhaKyTu: typeof hd.text === "string" };
}

/** Chụp ảnh vào `outDir/ten.png`. `clip` (tuỳ chọn) = `{x,y,width,height,scale}` để ZOOM một vùng. */
export async function chup(driver, ten, outDir, clip = null) {
  const tham = { format: "png" };
  if (clip !== null) tham.clip = { ...clip, scale: clip.scale ?? 1 };
  const r = await driver.send("Page.captureScreenshot", tham);
  if (typeof r.result?.data !== "string") {
    throw new Error(`Page.captureScreenshot khong tra du lieu cho ${ten}`);
  }
  mkdirSync(outDir, { recursive: true });
  const dich = path.join(outDir, `${ten}.png`);
  const buf = Buffer.from(r.result.data, "base64");
  writeFileSync(dich, buf);
  console.log(`[shot] ${dich} (${buf.length} B)`);
  return dich;
}

/** Chạy một kế hoạch. Mỗi bước trả về kết quả và được in ra (log là bằng chứng). */
export async function chayKeHoach(driver, plan, { outDir }) {
  const ket = [];
  const ghi = (buoc, kq) => {
    ket.push({ buoc, ...kq });
    console.log(`[${buoc.do}] ${JSON.stringify(kq)}`);
  };

  await caiDauDo(driver);
  if (plan.width && plan.height) {
    await driver.send("Emulation.setDeviceMetricsOverride", {
      width: plan.width, height: plan.height, deviceScaleFactor: 1, mobile: false,
    });
  }

  for (const buoc of plan.steps ?? []) {
    switch (buoc.do) {
      case "nav": {
        await driver.send("Page.navigate", { url: buoc.url });
        // 🔴 I2: tài liệu MỚI xoá mọi thứ đã cài trên `window` ⇒ phải chờ nó commit RỒI cài lại
        // đầu đò `keydown`. Bản cũ cài một lần TRƯỚC vòng lặp nên đầu đò không tồn tại lúc chạy.
        const tai = await choTaiLieu(driver, { url: buoc.url });
        const trangThai = await caiDauDo(driver);
        ghi(buoc, { url: buoc.url, taiLieu: tai, dauDo: trangThai });
        break;
      }
      case "khung": {
        // Doi KHUNG NHIN giua hai buoc cua CUNG mot tai lieu: mot phep do "o >= 2000 px" va mot
        // phep do "o 1280 px" phai chay tren CUNG mot DOM/DL, neu khong thi hai con so khong so
        // duoc voi nhau. `plan.width/height` chi dat duoc MOT lan, truoc moi buoc.
        // ⚠️ Doi khung nhin lam layout reflow ⇒ phai cho mot nhip TRUOC khi doc
        // `getBoundingClientRect`/`scrollWidth`, neu khong doc ra so cua khung CU.
        await driver.send("Emulation.setDeviceMetricsOverride", {
          width: buoc.width, height: buoc.height, deviceScaleFactor: 1, mobile: false,
        });
        await sleep(buoc.sauMs ?? 400);
        ghi(buoc, { width: buoc.width, height: buoc.height });
        break;
      }
      case "khangDinh": {
        // 🔴 I2: `assert`, KHÔNG phải `log`. Một tiền đề sai phải làm LƯỢT ĐÓ ĐỎ (exit 1) —
        // nếu không, mọi con số đo được sau nó là số vô nghĩa mà không ai biết.
        const kq = await driver.goi(buoc.js);
        const dung = kq.giaTri === true;
        ghi(buoc, { nhan: buoc.log ?? buoc.thongDiep ?? buoc.js.slice(0, 60), dung, giaTri: kq.loi ?? kq.giaTri });
        if (!dung) {
          throw new Error(
            `KHANG DINH TIEN DE THAT BAI: ${buoc.thongDiep ?? buoc.log ?? buoc.js} `
            + `(do duoc: ${JSON.stringify(kq.loi ?? kq.giaTri)})`,
          );
        }
        break;
      }
      case "waitFor": {
        const ok = await cho(driver, { chon: buoc.selector, timeout: buoc.timeout });
        ghi(buoc, { selector: buoc.selector, thay: ok });
        // 🔴 ĐO ĐƯỢC: bản cũ chỉ `console.log("⚠️ KHONG thay …")` rồi đi tiếp, nên một
        // bước chờ TRƯỢT vẫn cho `EXIT=0`. Đo được thật: plan `hat-tang-song.json` chạy
        // tới `[waitText] {"text":"Phòng thu biên tập","thay":false}` mà lượt chạy vẫn
        // XANH — một phép "xanh giả" đúng lớp lỗi mà bước `khangDinh` sinh ra để chống.
        //
        // Cảnh báo không làm đỏ được lượt chạy thì không phải cổng kiểm. Muốn chỉ ghi
        // nhận mà không chặn thì đặt `"required": false` NGAY TRONG PLAN — đó là quyết
        // định viết ra được, không phải một dấu ⚠️ trôi qua log.
        if (!ok && buoc.required !== false) {
          throw new Error(
            `KHONG thay ${JSON.stringify(buoc.selector)} trong ${buoc.timeout ?? "?"} ms`
            + (buoc.log ? ` — ${buoc.log}` : ""),
          );
        }
        if (!ok) console.log(`  (bo qua, required=false) khong thay ${buoc.selector}`);
        break;
      }
      case "waitText": {
        const ok = await cho(driver, { chu: buoc.text, timeout: buoc.timeout });
        ghi(buoc, { text: buoc.text, thay: ok });
        if (!ok && buoc.required !== false) {
          throw new Error(
            `KHONG thay chu ${JSON.stringify(buoc.text)} trong ${buoc.timeout ?? "?"} ms`
            + (buoc.log ? ` — ${buoc.log}` : ""),
          );
        }
        if (!ok) console.log(`  (bo qua, required=false) khong thay chu ${JSON.stringify(buoc.text)}`);
        break;
      }
      case "url": {
        const kq = await driver.goi("location.href");
        ghi(buoc, { url: kq.giaTri });
        break;
      }
      case "click": {
        const kq = await driver.goi(`(() => {
          const e = document.querySelector(${JSON.stringify(buoc.selector)});
          if (e === null) return "khong thay";
          e.click();
          return "da bam";
        })()`);
        ghi(buoc, { selector: buoc.selector, ketQua: kq.giaTri });
        break;
      }
      case "clickChu": {
        // Bam phan tu DAU TIEN co `textContent` chua chuoi — neo theo DU LIEU, khong theo class.
        const kq = await driver.goi(`(() => {
          const tat = [...document.querySelectorAll(${JSON.stringify(buoc.chon ?? "button, a, summary, label")})];
          const t = tat.find((e) => (e.textContent || "").includes(${JSON.stringify(buoc.text)}));
          if (t === undefined) return "khong thay";
          t.click();
          return "da bam " + (t.tagName || "");
        })()`);
        ghi(buoc, { text: buoc.text, ketQua: kq.giaTri });
        break;
      }
      case "radio": {
        const kq = await driver.goi(`(() => {
          const rs = [...document.querySelectorAll('input[type=radio]')];
          const t = rs.find((x) => {
            const l = x.closest("label") || x.parentElement;
            return l && new RegExp(${JSON.stringify(buoc.label)}, "i").test(l.textContent || "");
          });
          if (t === undefined) return "khong thay radio";
          t.click();
          return "da bam";
        })()`);
        ghi(buoc, { label: buoc.label, ketQua: kq.giaTri });
        break;
      }
      case "key": {
        // 🔴 I2: cài lại đầu đò NGAY TRƯỚC khi phát phím (idempotent trong cùng tài liệu) — kể cả
        // khi kế hoạch không có bước `nav` nào sau lần điều hướng cuối.
        await xoaDauDo(driver);
        const hd = await phim(driver, buoc.key, {
          shift: buoc.shift, ctrl: buoc.ctrl, alt: buoc.alt,
        });
        await sleep(buoc.sauMs ?? 150);
        const dau = await docDauDo(driver);
        ghi(buoc, { ...hd, dauDo: dau });
        // 🔴 I2: ĐẦU ĐÒ RỖNG = LƯỢT ĐỎ. Không có khẳng định này thì một đầu đò chết im lặng cho ra
        // `dauDo: []` và mọi kết luận "app không xử lý phím" đều là ARTIFACT (ERRATA #47 mục 5).
        // `choDauDo: false` chỉ dùng cho phím mà kế hoạch KHAI RÕ là không tới được trang.
        if (dau.length === 0 && buoc.choDauDo !== false) {
          throw new Error(
            `DAU DO keydown RONG sau khi phát phím ${JSON.stringify(buoc.key)}: sự kiện KHÔNG tới `
            + "trang (hoặc đầu đò không được cài) ⇒ mọi kết luận \"app không xử lý\" ở lượt này là "
            + "ARTIFACT. Xem ERRATA #47 mục 5.",
          );
        }
        break;
      }
      case "eval": {
        const kq = await driver.goi(buoc.js);
        ghi(buoc, { nhan: buoc.log ?? buoc.js.slice(0, 60), giaTri: kq.loi ?? kq.giaTri });
        break;
      }
      case "shot": {
        await chup(driver, buoc.name, outDir, buoc.clip ?? null);
        break;
      }
      case "cho": {
        await cho(driver, { chon: buoc.chon, chu: buoc.chu, timeout: buoc.timeout });
        break;
      }
      default:
        ghi(buoc, { loi: `buoc khong hieu: ${JSON.stringify(buoc)}` });
    }
  }
  return ket;
}

/** Đóng Chrome qua CDP — cách DUY NHẤT an toàn khi không đọc được CommandLine (ERRATA #41 mục 4). */
export async function dongChrome(driver) {
  try {
    await driver.send("Browser.close");
  } catch {
    // Chrome co the da tat.
  }
}
