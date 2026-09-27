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
 * trong CUNG mot tien trinh. Nen `teardownDom()` phai tra `globalThis.fetch` ve
 * nguyen ban — khong tra thi contract test (goi backend that) chay sau se di qua
 * cau noi URL va hong mot cach kho hieu.
 */
import jsdom from "jsdom";

const { JSDOM } = jsdom;

let dom: InstanceType<typeof JSDOM> | null = null;
let realFetch: typeof globalThis.fetch | null = null;

/** Origin cua server test — dung de resolve URL tuong doi, KHONG phai de gia lap mang. */
let bridgeOrigin = "";

export function setupDom(origin: string): void {
  if (dom !== null) return;
  bridgeOrigin = origin;
  dom = new JSDOM("<!doctype html><html><body></body></html>", {
    url: origin,
    // `pretendToBeVisual` bat `requestAnimationFrame` — React dung no de lap lich.
    pretendToBeVisual: true,
  });

  const w = dom.window;
  const g = globalThis as unknown as Record<string, unknown>;
  g.window = w;
  g.document = w.document;
  g.HTMLElement = w.HTMLElement;
  g.Node = w.Node;
  g.Event = w.Event;
  g.MouseEvent = w.MouseEvent;
  g.getComputedStyle = w.getComputedStyle.bind(w);
  // `globalThis.navigator` cua Node 24 la getter chi-doc ⇒ phai defineProperty,
  // gan truc tiep (`g.navigator = ...`) khong nem nhung cung khong doi gi.
  Object.defineProperty(globalThis, "navigator", {
    value: w.navigator,
    configurable: true,
    writable: true,
  });
  // React 19 chi cho `act()` chay khi co co nay.
  g.IS_REACT_ACT_ENVIRONMENT = true;

  // CAU NOI URL — KHONG phai gia lap mang: request van la HTTP THAT di ra server
  // that trong tien trinh (xem `useJobStream.test.ts`). Ly do can: `client.ts`
  // goi `fetch("/api/…")` TUONG DOI, ma `fetch` cua Node nem
  // `TypeError: Failed to parse URL from /api/...`.
  realFetch = globalThis.fetch;
  const inner = realFetch;
  g.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    if (typeof input === "string" && input.startsWith("/")) {
      return inner(`${bridgeOrigin}${input}`, init);
    }
    return inner(input as RequestInfo, init);
  };
}

export function teardownDom(): void {
  if (realFetch !== null) {
    (globalThis as unknown as Record<string, unknown>).fetch = realFetch;
    realFetch = null;
  }
  if (dom !== null) {
    dom.window.close();
    dom = null;
  }
  delete (globalThis as unknown as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT;
}
