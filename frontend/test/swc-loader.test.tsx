// Ghim `test/swc-loader.mjs` — ha tang cua moi test UI sau nay.
//
// TEN TEP LA `.tsx`, KHONG PHAI `.ts`: loader dat `tsx: url.endsWith(".tsx")`, nen mot tep `.ts`
// khong duoc phep chua JSX. Do duoc: dat bai (b) trong `.ts` thi SWC nem
// `Syntax Error ... transformSync` ngay luc load, ca hai bai khong chay duoc. Brief/plan ghi
// `swc-loader.test.ts` — do la cho sai cua plan, xem bao cao.
//
// Khong co DOM trong moi truong nay (khong jsdom, khong Testing Library, npm i bi chan), nen
// render React THAT bang `renderToStaticMarkup` va khang dinh chuoi HTML. Do khong phai gia lap:
// day la output that cua react-dom.
//
// Hai bai, khong phai mot: bai (a) chi chung minh file .tsx chay duoc qua duong goi ham; bai (b)
// dung JSX that nen no chung minh chinh duong JSX. Mutation da do: bo
// `transform: { react: { runtime: "automatic" } }` khoi loader => (b) DO vi `React is not defined`,
// (a) van XANH — tuc (b) moi la bai ghim runtime JSX.
import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { Probe } from "./fixtures/Probe.tsx";

test("a) .tsx chay duoc: goi ham component truc tiep roi render that ra HTML", () => {
  const html = renderToStaticMarkup(Probe({ label: "xin chao" }));
  assert.equal(html, '<span class="probe">xin chao</span>');
});

test("b) duong JSX that (khong phai goi ham) qua loader SWC", () => {
  const html = renderToStaticMarkup(<Probe label="xin chao" />);
  assert.equal(html, '<span class="probe">xin chao</span>');
});
