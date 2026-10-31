/**
 * Harness DOM cho test don vi CO TUONG TAC (jsdom + Testing Library).
 *
 * Vi sao ton tai: `useJobStream` la mot hook — khong co DOM thi khong co cach nao
 * chay no, va "da sua hook" ma khong chay duoc no la mot LOI KHAI khong do duoc.
 * ERRATA #5 muc 2 da do: jsdom + `@testing-library/react` cai duoc (bang cache
 * trong workspace) va chay THAT duoi `node --test --test-isolation=none`.
 *
 * `setupDom(origin)` phai duoc goi TRUOC khi import `@testing-library/react` va
 * truoc khi import hook (xem `src/state/useJobStream.test.ts`: no dung
 * `await import(...)` sau `setupDom`). React doc `window`/`document` luc nap.
 *
 * BAN QUYEN CUA HARNESS NAY: `--test-isolation=none` nghia la MOI tep test chay
 * trong CUNG mot tien trinh. Nen `teardownDom()` phai tra MOI global no da dat ve
 * nguyen ban — khong tra thi contract test (goi backend that) chay sau se di qua
 * cau noi URL va hong mot cach kho hieu.
 *
 * DO DUOC, khong phai suy dien (xem `test/dom.test.ts` va bao cao Task 3b): duoi
 * `--test-isolation=none`, hook `before`/`after` o CAP TEP bi node:test keo len
 * GOC cua ca luot chay — MOI `before` chay truoc MOI bai test, MOI `after` chay
 * sau MOI bai test. Nghia la mot suite DOM co the dang song trong luc cac tep test
 * khac dang chay. Do chinh la ly do `setupDom` KHONG duoc phep bo qua IM LANG mot
 * origin khac: suite sau se go cua server cua suite truoc ma khong co gi bao.
 */
import jsdom from "jsdom";

const { JSDOM } = jsdom;

/** Global ma harness nay dat ⇒ phai tra lai. Mot danh sach de khong bo sot cai nao. */
const MANAGED_GLOBALS = [
  "window",
  "document",
  "navigator",
  "HTMLElement",
  "Node",
  "Event",
  "MouseEvent",
  "getComputedStyle",
  "fetch",
  "IS_REACT_ACT_ENVIRONMENT",
  // Ba global duoi day duoc dat trong `setupDom` nhung TUNG khong co trong danh
  // sach nay — nghia la `teardownDom()` khong tra chung, va chung ro sang moi tep
  // test chay sau trong cung tien trinh (`--test-isolation=none`).
  "ResizeObserver",
  "scrollIntoView",
  "requestAnimationFrame",
  "cancelAnimationFrame",
] as const;

interface DaLuu {
  key: string;
  /** `undefined` nghia la global do TRUOC DO KHONG TON TAI ⇒ teardown phai XOA no. */
  descriptor: PropertyDescriptor | undefined;
}

let dom: InstanceType<typeof JSDOM> | null = null;

/** Anh chup trang thai global NGAY TRUOC lan `setupDom` hien hanh. */
let daLuu: DaLuu[] = [];

/**
 * Anh chup cua lan `setupDom` DAU TIEN — giu VINH VIEN, khong bao gio bi xoa.
 *
 * Vi sao can mot ban thu hai: `daLuu` bi xoa moi lan `teardownDom()` (no la anh chup
 * de TRA), nen sau khi tra xong thi khong con gi de doi chieu. Mot guard luc THOAT
 * TIEN TRINH can biet "trang thai nguyen ban cua tien trinh la gi" — va chi ban chup
 * DAU TIEN moi la nguyen ban: ban chup thu hai tro vao jsdom TRUNG GIAN (xem
 * `guardGlobalLucThoat`).
 */
let anhGoc: DaLuu[] = [];

/** Origin cua server test — dung de resolve URL tuong doi, KHONG phai de gia lap mang. */
let bridgeOrigin = "";

/** `fetch` THAT cua tien trinh. Ghi mot lan: cau noi cua chinh module nay khong bao
 *  gio duoc boc hai lan (boc chong thi moi lan rebuild lai tao them mot chuoi cau noi). */
let fetchThat: typeof globalThis.fetch | null = null;

/** Cau noi URL hien hanh do chinh module nay tao (de nhan dien, khong boc lai no). */
let cauNoi: typeof globalThis.fetch | null = null;

/**
 * Ghi lai NGUYEN DESCRIPTOR cua tung global, khong chi gia tri: `navigator` cua
 * Node 24 la getter chi-doc, nen "khoi phuc gia tri" bat buoc phai la "khoi phuc
 * descriptor" — va "truoc do khong ton tai" phai duoc ghi la `undefined` de
 * teardown biet ma XOA thay vi dat thanh `undefined`.
 */
function luuGlobal(): void {
  daLuu = MANAGED_GLOBALS.map((key) => ({
    key,
    descriptor: Object.getOwnPropertyDescriptor(globalThis, key),
  }));
  // Ban chup DAU TIEN la nguyen ban cua tien trinh; cac lan sau la jsdom trung gian.
  if (anhGoc.length === 0) anhGoc = daLuu.map((muc) => ({ ...muc }));
}

/** Tra tung global ve dung trang thai da ghi: co truoc ⇒ dat lai, khong co truoc ⇒ XOA. */
function traGlobal(): void {
  traGlobalTheoAnh(daLuu);
  daLuu = [];
}

/**
 * `traGlobal` trên MỘT ảnh chụp cho trước.
 *
 * Tách ra vì `teardownDom()` trả nhóm DOM ở nhịp `setImmediate` sau (xem
 * `NHOM_DOM_HOAN`): lúc đó `daLuu` đã bị `traGlobal()` đặt rỗng, nên bản hoãn phải
 * giữ ảnh chụp của chính nó. Gộp hai đường làm một thì một trong hai sẽ đọc `daLuu`
 * rỗng và trả hu không.
 */
function traGlobalTheoAnh(anh: DaLuu[]): void {
  for (const { key, descriptor } of anh) {
    if (descriptor === undefined) {
      delete (globalThis as unknown as Record<string, unknown>)[key];
    } else {
      Object.defineProperty(globalThis, key, descriptor);
    }
  }
}

/** Dat mot global bang `defineProperty`: an toan voi global chi-co-getter cua Node. */
function datGlobal(key: string, value: unknown): void {
  Object.defineProperty(globalThis, key, {
    value,
    configurable: true,
    writable: true,
    enumerable: true,
  });
}

export function setupDom(origin: string): void {
  // 🔴 HUY việc trả nhóm DOM đã hẹn (xem `NHOM_DOM_HOAN`). Lượt `teardownDom` trước
  // có thể còn chờ `setImmediate`; nếu lần này cài jsdom mới rồi mới để bản hoãn cũ
  // chạy, nó sẽ trả global về trạng thái CŨ và xoá mất jsdom vừa dựng.
  huyTraDom();
  if (dom !== null) {
    // Cung origin: cau noi da tro dung cho ⇒ khong co gi phai lam (idempotent, CO CHU Y).
    if (origin === bridgeOrigin) return;

    // Origin KHAC: CAM bo qua im lang. Chon "DUNG LAI" thay vi "nem loi" vi T5–T11 se
    // co nhieu suite DOM tren cung mot tien trinh ⇒ goi lan hai voi origin moi la viec
    // BINH THUONG, khong phai loi cua nguoi goi. Nem loi chi buoc noi goi tu xu ly mot
    // tinh huong binh thuong; dung lai thi `fetch("/api/…")` di dung server.
    dom.window.close();
    dom = null;
  }

  // Anh chup chi lay khi CHUA co: nhieu lan `setupDom` (dung lai theo origin moi) trong
  // cung mot suite la MOT lan cai dat, nen `teardownDom()` phai tra ve trang thai NGAY
  // TRUOC lan cai dat DAU TIEN — ke ca khi global dang tro vao jsdom song cua suite khac.
  // Lay lai anh chup o moi lan rebuild se khien teardown tra ve mot jsdom TRUNG GIAN
  // (da bi close) thay vi trang thai ma suite nay thua huong.
  if (daLuu.length === 0) luuGlobal();
  bridgeOrigin = origin;
  dom = new JSDOM("<!doctype html><html><body></body></html>", {
    url: origin,
    // `pretendToBeVisual` bat `requestAnimationFrame` — React dung no de lap lich.
    pretendToBeVisual: true,
  });

  const w = dom.window;
  datGlobal("window", w);
  datGlobal("document", w.document);
  datGlobal("HTMLElement", w.HTMLElement);
  datGlobal("Node", w.Node);
  datGlobal("Event", w.Event);
  datGlobal("MouseEvent", w.MouseEvent);
  datGlobal("getComputedStyle", w.getComputedStyle.bind(w));
  // `globalThis.navigator` cua Node 24 la getter chi-doc ⇒ phai defineProperty,
  // gan truc tiep (`g.navigator = ...`) khong nem nhung cung khong doi gi.
  datGlobal("navigator", w.navigator);
  // React 19 chi cho `act()` chay khi co co nay.
  datGlobal("IS_REACT_ACT_ENVIRONMENT", true);

  // ───────────────────────────────────────────────────────────────────────────
  // `ResizeObserver` — jsdom KHONG CO, trinh duyet THAT co.
  //
  // Do duoc: render `Studio` nem `ReferenceError: ResizeObserver is not defined`
  // tai `Timeline.tsx:246` (`new ResizeObserver(...)` trong `useEffect`). Do la
  // THIEU HUT CUA HA TANG TEST, khong phai loi cua `Timeline` — nen sua o day,
  // KHONG them phep kiem `typeof ResizeObserver` vao ma san pham chi de test
  // chay duoc (lam vay la ha ma san pham xuong muc test).
  //
  // Stub nay KHONG BAO GIO GOI callback: trong jsdom moi phan tu co kich thuoc 0,
  // nen khong co thay doi kich thuoc nao that su. No chi lam cho `observe`/
  // `unobserve`/`disconnect` khong no.
  // ───────────────────────────────────────────────────────────────────────────
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  datGlobal("ResizeObserver", ResizeObserverStub);

  // ───────────────────────────────────────────────────────────────────────────
  // `Element.prototype.scrollIntoView` — jsdom KHONG CAI, trinh duyet THAT co.
  //
  // Do duoc: `Studio.tsx:250` goi `rowRefs.current.get(i)?.scrollIntoView(...)`
  // trong `useEffect` khi dong dang chon doi. jsdom nem
  // `TypeError: rowRefs.current.get(...)?.scrollIntoView is not a function`.
  // cung loai thieu hut ha tang nhu `ResizeObserver` — sua o day, khong them
  // phep kiem `typeof` vao ma san pham.
  // ───────────────────────────────────────────────────────────────────────────
  w.Element.prototype.scrollIntoView = function scrollIntoView(): void {};
  datGlobal(
    "scrollIntoView",
    w.Element.prototype.scrollIntoView,
  );

  // ───────────────────────────────────────────────────────────────────────────
  // `requestAnimationFrame` / `cancelAnimationFrame` — jsdom KHONG dat len
  // `globalThis` du da bat `pretendToBeVisual: true`.
  //
  // DO DUOC: khi render `App` (no dung `Studio` -> `Timeline`), `useEffect` cua
  // `Timeline` goi `requestAnimationFrame(X)` va nem
  //   ReferenceError: requestAnimationFrame is not defined
  // => `useEffect` chet giua chung, `setKhungNhin` khong bao gio chay, va moi phep
  // do ve sau trong cung bai deu nhin mot cay React chua hoan tat.
  //
  // `pretendToBeVisual` chi gan hai ham nay len `window`; ma `Timeline` goi ten
  // TRAN, khong qua `window.`, nen phai co tren `globalThis`.
  // ───────────────────────────────────────────────────────────────────────────
  if (typeof w.requestAnimationFrame === "function") {
    datGlobal("requestAnimationFrame", w.requestAnimationFrame.bind(w));
    datGlobal("cancelAnimationFrame", w.cancelAnimationFrame.bind(w));
  } else {
    // Du phong: neu jsdom khong bat `pretendToBeVisual` thi van phai co, khong thi moi
    // `useEffect` dung khung hinh deu nem. `setTimeout(0)` la ban thay the dung nghia
    // "chay o khung hinh ke tiep", khong phai mot ham rong.
    datGlobal("requestAnimationFrame", (cb: FrameRequestCallback) =>
      setTimeout(() => cb(Date.now()), 0) as unknown as number);
    datGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  }

  // CAU NOI URL — KHONG phai gia lap mang: request van la HTTP THAT di ra server
  // that trong tien trinh (xem `useJobStream.test.ts`). Ly do can: `client.ts`
  // goi `fetch("/api/…")` TUONG DOI, ma `fetch` cua Node nem
  // `TypeError: Failed to parse URL from /api/...`.
  const hienTai = globalThis.fetch;
  if (fetchThat === null || hienTai !== cauNoi) fetchThat = hienTai;
  const inner = fetchThat;
  cauNoi = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    if (typeof input === "string" && input.startsWith("/")) {
      return inner(`${bridgeOrigin}${input}`, init);
    }
    return inner(input as RequestInfo, init);
  };
  datGlobal("fetch", cauNoi);
}

/**
 * Nhóm global phải sống thêm MỘT nhịp scheduler, không phải trả ngay.
 *
 * 🔴 VÌ SAO — đo được, có stack trace, và hai giả thuyết đầu của tôi đều SAI:
 *
 * Triệu chứng (chỉ xuất hiện sau khi `App.test.tsx` có nhóm "dời một mốc"):
 *
 *   ℹ Error: Test "PATCH /api/transcripts/2/segments/0 ..." generated asynchronous
 *     activity after the test ended. This activity created the error
 *     "ReferenceError: window is not defined" and would have caused the test to
 *     fail, but instead triggered an uncaughtException event.
 *
 * Bắt bằng `process.on("uncaughtException")` thì ra stack THẬT:
 *
 *   ReferenceError: window is not defined
 *     at react-dom-client.development.js:19555:13
 *     at Immediate.performWorkUntilDeadline (scheduler.development.js:45:48)
 *     at process.processImmediate (node:internal/timers:504:21)
 *
 * Giả thuyết 1 — `requestAnimationFrame` — SAI: probe đo được `0 raf` treo ở MỌI
 * lượt teardown.
 * Giả thuyết 2 — promise `getPeaks` setState sau `await` — SAI: `Studio.tsx:253`
 * và `:255` đều nằm trong `if (!huy)`, tức sản phẩm ĐÃ đúng, và stub `/peaks`
 * vẫn không hết lỗi.
 *
 * Sự thật, đọc ở `react-dom-client.development.js:19549-19560`: trong `commitRoot`,
 * nếu `finishedWork.subtreeFlags & 10256` (hoặc `flags & 10256`) khác 0 thì React
 * gọi `scheduleCallback$1(NormalPriority$1, …)`, và THÂN callback đó mở đầu bằng
 * `schedulerEvent = window.event`. Đó là việc xả **passive effect**: nó đã được
 * XẾP LỊCH trong lúc commit, chạy ở macrotask sau qua `scheduler`, và `act()`
 * KHÔNG xả nó (đã thử: `act` có mặt, `window` còn sống, lỗi vẫn còn).
 *
 * Sửa: trả `fetch` NGAY (bất biến của harness — tệp kế tiếp phải thấy `fetch`
 * thật, xem docblock dưới), nhưng hoãn nhóm DOM đúng một nhịp `setImmediate` để
 * scheduler có `window` mà đọc.
 *
 * ⚠️ VÌ SAO KHÔNG HOÃN TẤT CẢ: đã thử và đo được — hoãn cả `fetch` thì
 * `App.test.tsx` rồi `api/contract.test.ts` trong cùng tiến trình làm contract
 * chết với "backend 8620 khong len sau 30s" (probe: `fetch.name=""`,
 * `window=object`), vì `fetch` còn là cầu nối trỏ `bridgeOrigin` cũ đã chết.
 *
 * ⚠️ VÌ SAO KHÔNG HOÃN `requestAnimationFrame`: đã thử và đo được — `App.test.tsx`
 * đỏ 4 bài với `ReferenceError: requestAnimationFrame is not defined`, vì
 * `Timeline` gọi nó trong `useEffect` của lượt `setupDom` kế tiếp.
 */
const NHOM_DOM_HOAN = [
  "window",
  "document",
  "HTMLElement",
  "Node",
  "Event",
  "MouseEvent",
  "getComputedStyle",
  "navigator",
] as const;

/** Việc trả nhóm DOM đã hẹn; `setupDom`/`teardownDom` sau huỷ nó (xem `huyTraDom`). */
let traDomHoan: ReturnType<typeof setImmediate> | null = null;

/** Huỷ việc trả nhóm DOM đã hẹn. Gọi ở đầu `setupDom()` và đầu `teardownDom()`. */
function huyTraDom(): void {
  if (traDomHoan !== null) {
    clearImmediate(traDomHoan);
    traDomHoan = null;
  }
}

export function teardownDom(): void {
  // Lượt teardown TRƯỚC có thể còn đang chờ nhịp `setImmediate`. Không huỷ thì bản
  // hoãn cũ sẽ trả global về trạng thái CŨ và xoá mất jsdom vừa dựng — lỗi phụ
  // thuộc thời điểm, đúng loại khó tái hiện nhất.
  huyTraDom();
  // Chụp ảnh TRƯỚC khi `traGlobal()` xoá `daLuu`; bản hoãn cần đúng ảnh này.
  const anhDeTra = daLuu;
  const domDeDong = dom;
  dom = null;
  bridgeOrigin = "";
  // 🔴 TRẢ NGAY nhóm KHÔNG-DOM (`fetch`, `IS_REACT_ACT_ENVIRONMENT`, `rAF`, …) — bất
  // biến của harness: tệp kế tiếp phải thấy `fetch` THẬT. Nhóm DOM thì để nhịp sau.
  // Bản đầu tôi gọi `traGlobal()` ở đây, mà nó trả CẢ nhóm DOM ⇒ `window` biến mất
  // NGAY; probe đo được `[probe] setImmediate cua toi CHAY, window=undefined`, tức
  // bản hoãn chẳng hoãn được gì. Lọc phải làm ở CẢ HAI đường.
  traGlobalTheoAnh(anhDeTra.filter((m) => !(NHOM_DOM_HOAN as readonly string[]).includes(m.key)));
  daLuu = [];
  // Nhóm DOM: trả ở nhịp sau, để scheduler React xả nốt passive effect.
  traDomHoan = setImmediate(() => {
    traDomHoan = null;
    if (domDeDong !== null) domDeDong.window.close();
    traGlobalTheoAnh(anhDeTra.filter((m) => (NHOM_DOM_HOAN as readonly string[]).includes(m.key)));
  });
  // ───────────────────────────────────────────────────────────────────────────
  // DO DUOC: hai bien module nay PHAI duoc dat lai, khong chi `traGlobal()`.
  //
  // Trieu chung do duoc (bai `endpoints.test.ts:173` do sau khi them
  // `Studio.test.tsx`):
  //
  //   sau moi bai, `fetch` cua tien trinh la BAN THAT (khong ro sang tep khac)
  //   AssertionError: Expected "actual" to be reference-equal to "expected"
  //     actual:   [Function: cauNoi]
  //     expected: [Function: fetch]
  //
  // Nguyen nhan: `cauNoi` giu cau noi CU, `fetchThat` giu `fetch` THAT cua lan dau.
  // `traGlobal()` tra `fetch` ve descriptor da chup — nhung neu lan `setupDom` ke
  // tiep chay TRUOC khi `traGlobal` kip tra (hoac `fetch` hien tai da la `cauNoi`),
  // thi `if (fetchThat === null || hienTai !== cauNoi)` BO QUA viec cap nhat, va
  // `cauNoi` moi lai duoc dat lam `fetch` ⇒ `fetch` cua tien trinh tro vao mot
  // ham cua harness nay vinh vien.
  //
  // Dat lai ca hai ve `null`/rong: lan `setupDom` sau se doc `globalThis.fetch`
  // luc do (da la ban that) va boc lai tu dau.
  // ───────────────────────────────────────────────────────────────────────────
  cauNoi = null;
  fetchThat = null;
}

/** Hai descriptor co mo ta CUNG mot trang thai khong? Khong goi getter nao ca. */
function descriptorBang(
  a: PropertyDescriptor | undefined,
  b: PropertyDescriptor | undefined,
): boolean {
  if (a === undefined || b === undefined) return a === b;
  return (
    Object.is(a.value, b.value)
    && Object.is(a.get, b.get)
    && Object.is(a.set, b.set)
    && a.writable === b.writable
    && a.enumerable === b.enumerable
    && a.configurable === b.configurable
  );
}

/**
 * Mo ta mot descriptor ma KHONG goi getter cua no: `navigator` cua Node 24 la getter
 * chi-doc, va sau khi jsdom bi `close()` thi doc sau vao `window` la tu chuoc loi.
 */
function moTa(descriptor: PropertyDescriptor | undefined): string {
  if (descriptor === undefined) return "khong ton tai";
  if (descriptor.get !== undefined || descriptor.set !== undefined) return "getter/setter";
  const value: unknown = descriptor.value;
  if (value === undefined) return "undefined";
  if (value === null) return "null";
  const kind = typeof value;
  if (kind !== "object" && kind !== "function") return `${kind} ${String(value)}`;
  return Object.prototype.toString.call(value);
}

/**
 * GHIM BAT BIEN `if (daLuu.length === 0) luuGlobal();` — "mot `setupDom` = MOT lan cai dat".
 *
 * Vi sao phai la mot guard luc THOAT TIEN TRINH, khong phai mot bai test: mutation `R4`
 * (luon chup lai anh chup global) lam RO RI 10/10 global ma `npm test` VAN XANH
 * (`pass`/`fail` khong doi mot bai nao) — do la loai loi ma khong bai test nao TRONG
 * luot chay nhin thay duoc, vi moi bai deu tu chuan hoa truoc khi do. Chi mot phep do o
 * `process exit` moi bat duoc.
 *
 * Cach do: so `Object.getOwnPropertyDescriptor` HIEN TAI cua tung global trong
 * `MANAGED_GLOBALS` voi descriptor chup o lan `setupDom` DAU TIEN (`anhGoc`). So
 * DESCRIPTOR chu khong chi gia tri: `navigator` la getter, nen "khoi phuc gia tri" ma
 * khong khoi phuc descriptor la mot trang thai khac.
 *
 * Goi ham nay MOT lan, o cap MODULE cua mot tep test DOM (xem `test/dom.test.ts`).
 * No chi DANG KY mot listener — khong doi global nao.
 */
export function guardGlobalLucThoat(): void {
  process.on("exit", () => {
    if (anhGoc.length === 0) {
      process.stderr.write(
        "[guard thoat] khong co lan setupDom nao ⇒ khong co global nao phai kiem\n",
      );
      return;
    }

    const ro: string[] = [];
    for (const { key, descriptor } of anhGoc) {
      const hienTai = Object.getOwnPropertyDescriptor(globalThis, key);
      if (!descriptorBang(hienTai, descriptor)) {
        ro.push(`  ${key}: truoc=${moTa(descriptor)} / sau=${moTa(hienTai)}`);
      }
    }

    if (ro.length === 0) {
      process.stderr.write(
        `[guard thoat] ${anhGoc.length}/${anhGoc.length} global da ve nguyen trang `
        + "(so descriptor, khong chi gia tri)\n",
      );
      return;
    }

    process.stderr.write(
      `[guard thoat] HARNESS DOM RO RI: ${ro.length}/${anhGoc.length} global CHUA ve nguyen trang\n`
      + `${ro.join("\n")}\n`
      + "  Moi global phai duoc tra ve DUNG descriptor chup o lan `setupDom` DAU TIEN.\n"
      + "  Nguyen nhan thuong gap: bo `if (daLuu.length === 0)` trong `luuGlobal()` ⇒ teardown tra\n"
      + "  ve anh chup cua jsdom TRUNG GIAN (da close) thay vi trang thai nguyen ban.\n"
      + "  Day la thu summary cua node:test KHONG thay duoc — no chi lo ra o `process exit`.\n",
    );
    process.exitCode = 1;
  });
}

