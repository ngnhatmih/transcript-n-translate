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
  for (const { key, descriptor } of daLuu) {
    if (descriptor === undefined) {
      delete (globalThis as unknown as Record<string, unknown>)[key];
    } else {
      Object.defineProperty(globalThis, key, descriptor);
    }
  }
  daLuu = [];
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

export function teardownDom(): void {
  if (dom !== null) {
    dom.window.close();
    dom = null;
  }
  bridgeOrigin = "";
  traGlobal();
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

