// Ghim `test/swc-loader.mjs` — ha tang cua moi test UI sau nay.
//
// TEN TEP LA `.tsx`, KHONG PHAI `.ts`: loader dat `tsx: url.endsWith(".tsx")`, nen mot tep `.ts`
// khong duoc phep chua JSX. Do duoc (probe truc tiep `transformSync` voi `tsx:false` tren JSX):
// no nem `x Unterminated regexp literal` ngay luc load, ca hai bai khong chay duoc.
// (Ban dau cho nay trich thong diep la "Syntax Error ... transformSync" — dung ban chat
// 「nem luc load」nhung SAI nguyen van; vong re-review do lai va sua.)
// Brief/plan ghi `swc-loader.test.ts` — do la cho sai cua plan, xem bao cao.
//
// Khong co DOM trong moi truong nay (khong jsdom, khong Testing Library, npm i bi chan), nen
// render React THAT bang `renderToStaticMarkup` va khang dinh chuoi HTML. Do khong phai gia lap:
// day la output that cua react-dom.
//
// Hai bai, khong phai mot: bai (a) chung minh file .tsx chay duoc qua duong goi ham; bai (b)
// dung JSX that nen no chung minh chinh duong JSX.
//
// Mutation da DO (vong re-review chay lai): bo
// `transform: { react: { runtime: "automatic" } }` khoi loader => `fail 2`: CA HAI bai do
// (`ReferenceError: React is not defined` o :20 va :26). Ly do: `fixtures/Probe.tsx` CUNG la
// TSX chua JSX, nen mat runtime JSX thi chinh fixture khong bien dich duoc.
// ⚠️ Ban dau cho nay viet "(b) DO, (a) van XANH — tuc (b) moi la bai ghim runtime JSX".
// DO LA SUY DIEN SAI, doan truoc khi chay; vong re-review do duoc ca hai deu do. Sua lai o day
// thay vi de mot comment noi doi ve bang chinh phep do cua no.
// Vay hai bai KHAC suc manh o cho nao? O `--import`: bo han no => `ERR_UNKNOWN_FILE_EXTENSION`,
// tuc bai (a) ghim chinh LOADER chu khong chi duong JSX.
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
