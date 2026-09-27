# Giai đoạn Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng bàn làm việc chạy trong trình duyệt cho bốn màn hình backend đã phục vụ được (Biên tập, Đối chiếu, Thuật ngữ, lỗi Ollama) + khung ba vùng + thanh transport, đủ để làm trọn luồng biên tập bằng bàn phím.

**Architecture:** SPA React 19 thuần client, **không router** — một shell với `mode ∈ {edit, compare, glossary}`. Trạng thái server nằm ở một tầng `fetch` mỏng cộng **đúng một** subscription SSE tới `/api/jobs/stream`; trạng thái client nằm trong một reducer. Không ghi kiểu đoán trước cho bản dịch.

**Tech Stack:** React 19 · TypeScript · **Rollup** + `dev-server.mjs` (Vite **bị loại** — xem ERRATA) · **`node --test --test-isolation=none`** + loader `@swc/core` trong tiến trình (Vitest **và** Testing Library **bị loại** — xem `Q-1`) · Playwright · CSS thuần + custom property · font self-host woff2.

**Spec:** `docs/superpowers/specs/2026-09-26-frontend-workspace-2-design.md`

## Global Constraints

- **Node v24.16.0, npm 11.13.0** (đã đo; `pnpm` có nhưng dùng **npm** cho ít bộ phận hơn). Frontend ở `frontend/` **trong repo** `phu-de-lab`.
- Dev server **cổng 3100** (khớp `FRONTEND_DEV_ORIGINS` ở `backend/app/api/app.py:19`), proxy `/api` → `http://127.0.0.1:8620`.
- Backend **không** chạy sẵn: mọi test đầu-cuối phải **tự khởi động** nó và **tự tắt**. Cổng 8620 và 11434 (Ollama) hiện đều **tắt** — đừng giả định chúng sống.
- **CỐ Ý KHÔNG dùng:** Tailwind · thư viện quản lý trạng thái · sinh type từ `/openapi.json` · `@tanstack/react-virtual` · thư viện component. Lý do ở spec §2 — đổi ý thì phải nói ra, không lặng lẽ thêm.
- **ponytail mức `full`** áp cho *thứ được dựng*. Mọi chỗ cắt góc có trần đã biết phải có comment `ponytail:` nêu **trần** + **đường nâng cấp**.
- **Kỷ luật của dự án KHÔNG bị ponytail nới:** không amend/rebase; scratch **ngoài** repo; `$env:TEMP` **bị từ chối** nên scratch để trong workspace nhưng ngoài cây repo rồi xoá; mọi tuyên bố "xong" kèm **lệnh chính xác + dòng cuối nguyên văn**; mọi test mới phải chứng minh **không rỗng** bằng mutation (đổi mã → thấy đỏ → phục hồi → verify `git hash-object` == `git rev-parse HEAD:<path>` **và** byte trong không gian chuẩn hoá của git, vì `core.autocrlf=true` làm hash khớp trên CRLF).
- **Hành vi đi qua worker/API thì test phải đi qua ĐƯỜNG THẬT**, không gán thẳng trường của đối tượng giả. Task 11 của Giai đoạn 2 đã có một test huỷ *tự thoả mãn* xanh trong khi sản phẩm hỏng — cùng lớp lỗi với "chỉ component test với API giả" mà giai đoạn này đã từ chối.
- **Không tính lại ở client thứ backend đã tính:** CPS lấy từ backend, `available` lấy từ `/api/registry`, số bản dịch bị ảnh hưởng lấy từ `affected`. Hai nơi tính cùng một đại lượng là đúng thứ Giai đoạn 2 vừa phải đi vá.
- **API cần nhớ:** trên endpoint transcript, mục `translations[]` dùng khoá **`transcript_version`** (không phải `translated_from_version`) và **có** `status` + `transcript_id`.
- Baseline tham chiếu: backend **821 passed, 13 deselected** (`python -B -m pytest` từ `backend/`). Giai đoạn này **không** được làm giảm số đó.
- **Cài đặt ra ngoài workspace cần người dùng duyệt** — `npx playwright install` tải trình duyệt và sẽ bị sandbox từ chối. Dừng và hỏi, đừng tự vượt.

## ⚠️ ERRATA — công cụ đã đổi sau khi ĐO, đọc trước khi làm bất cứ task nào

Sandbox của phiên này **cấm named pipe** ⇒ mọi tiến trình spawn bằng `stdio:'pipe'` chết `EPERM`.
Đo được: `esbuild` không chạy được; Vite còn gọi `exec("net use")` (không bọc try) nên cũng chết;
và Vite 6 **không có** đường pre-bundle dependency nào ngoài esbuild ⇒ React 504, trang không vẽ.
⇒ **Vite bị loại.** Đã đo và chốt: **Rollup** (thuần JS, chạy trong tiến trình, không spawn) +
`dev-server.mjs` viết tay (chỉ `node:http`/`node:fs`). Commit `fa51e10` + `a2df315`.

| Plan viết | Đọc thành |
|---|---|
| `npm run dev` (Vite) | `npm run dev` → **`node dev-server.mjs`** (đã có; phục vụ `dist/` + proxy `/api` → 8620) |
| (không có) | `npm run build` → **`rollup -c`**; `npm run typecheck` → `tsc --noEmit` |
| `npm i -D vitest` | **KHÔNG cài Vitest** — nó dựng trên Vite nên cũng chết. Dùng **`node --test --test-isolation=none`** (có sẵn trong Node 24) |
| Testing Library | **KHÔNG dùng được** — `jsdom`/`@testing-library/react`/`happy-dom` đều **không có** và `npm i` bị chặn. Test component dùng `react-dom/server.renderToStaticMarkup`; xem `Q-1` |
| `npm test -- contract` | `npm test` (đã đổi trong `package.json`) — nếu gọi tay thì **`node --import ./test/swc-loader.mjs --test --test-isolation=none <tệp>`**. **`--test-isolation=none` là BẮT BUỘC**: thiếu nó runner spawn con và chết `EPERM` trên máy này |
| `import { describe, expect, it } from "vitest"` | `import { describe, it } from "node:test"` + `import assert from "node:assert/strict"` — `expect(x).toBe(y)` → `assert.equal(x, y)`, `toBeInTheDocument()` → `assert.ok(el)` |
| `frontend/package-lock.json` | **ĐÃ CŨ** (mô tả cây Vite cũ) vì `npm i` không ghi được cache trong sandbox. Phải `npm install` lại ở môi trường bình thường trước khi ai đó tin `npm ci` — implementer **không** được sửa tay tệp này |
| `npm i` bất kỳ | **CÓ THỂ CHẾT `EPERM`** ở `AppData\Local\npm-cache`. Nếu chết: báo lại, **đừng** xin vượt sandbox; tìm gói đã có trong `node_modules` hoặc viết tay |

**Bảng này áp cho MỌI khối mã mẫu ở MỌI task bên dưới.** Các khối đó vẫn còn viết theo Vitest / Testing Library / Vite —
đó là **chưa được vá**, không phải "đã đối chiếu". Khi làm một task, chuyển khối mã của nó theo bảng này và theo `Q-1`.
Đừng đọc một khối `import { describe, expect, it } from "vitest"` ở dưới rồi làm theo nó.

**Rollup config là 202 dòng 5 plugin** (`resolve-nospawn`, `cjs-inproc`, `swc-nospawn`, `css-inproc`,
`html-inproc`) cộng một guard `assert-no-bare-imports` **làm đỏ build** nếu còn bare import sót — guard đó là
thứ khiến "bundle chạy được" không phải là lời hứa suông. React 19 chỉ có CJS, nên có shim CJS→ESM viết tay;
đừng "dọn" nó đi.

## ⚠️ ERRATA #2 — sửa sau khi ĐO ở Task 2 (áp cho MỌI task còn lại)

Task 2 đo trên backend thật và tìm ra chín chỗ plan sai. **Không chỗ nào là suy đoán** — mỗi dòng dưới đây có lệnh hoặc quan sát kèm theo.

1. **Mẫu contract test của plan BẤT KHẢ trong Node.** Nó dùng `BASE = "/api"` (đường dẫn tương đối) rồi `fetch(\`${BASE}${path}\`)` ⇒ Node ném `TypeError: Failed to parse URL from /api/status`. Trình duyệt tự thêm origin; **Node thì không**. Test (và e2e) phải dùng **origin tuyệt đối** (`http://127.0.0.1:8620` trong test trực tiếp, hoặc `http://127.0.0.1:3100` khi đi qua proxy). `client.ts` **giữ** `BASE = "/api"` vì nó chạy trong trình duyệt — chỗ khác nhau là **có chủ ý**, đừng "thống nhất" chúng.
2. **`/api/registry` KHÔNG trả mảng phẳng và KHÔNG có khoá `engines`.** Nó trả **`{"asr":[…],"mt":[…]}`**. Mẫu của plan (`Array.isArray(body) ? body : body.engines`) sẽ ra `undefined`.
3. **`capabilities.available` + `prompt_version` CHỈ có trên engine `kind == "mt"`.** `_mark_availability` chỉ ghi `available` cho engine dịch. Đo trên máy này: **4 spec ASR không có khoá `available`**; `opus-mt` = `true`, `qwen2.5-3b`/`qwen2.5-7b`/`hy-mt-1.5-7b` = `false` (Ollama tắt). Mẫu của plan khẳng định `first.capabilities.available` trên `specs[0]` — mà `specs[0]` là ASR ⇒ sẽ đỏ.
4. **`/api/status` trên máy này trả `ollama: "unknown"`, KHÔNG phải `"down"`.** Đo 3/3 lần: `socket.create_connection(('127.0.0.1',11434), 0.3)` ⇒ `TimeoutError`, và `urlopen` bọc nó thành `URLError(reason=TimeoutError)` ⇒ `probe_ollama` rơi vào nhánh "chưa đo được" ⇒ `unknown`. Cổng 11434 **timeout** chứ không **refused**.
   🔴 **Hệ quả trực tiếp cho Task 10 (§4.8):** nếu màn đó chỉ khoá theo `ollama === "down"` thì nó **KHÔNG BAO GIỜ HIỆN trên máy này**, và mọi ảnh chụp nghiệm thu sẽ là màn trống. Task 10 **phải** xử `unknown` như một trạng thái thật (spec gọi nó là "chưa đo được", không phải "tắt"). Premise "trạng thái thật khi mở app lần đầu là Ollama tắt" chỉ đúng **một nửa**.
5. **`.gitignore` thiếu `*.db-wal` + `*.db-shm`** — đã sửa ở `a56464f`. Lý do: SQLite WAL tạo hai tệp phụ khi DB đang mở, nên **chỉ cần chạy backend thật** (`python run_api.py` — việc **Task 12 bắt buộc** làm) là `git status` hiện `?? data/`, vi phạm luật "status phải rỗng".
6. **`"fail 0"` KHÔNG đồng nghĩa XANH.** Một `before` hook ném lỗi làm `node:test` in **`tests 9 / pass 0 / fail 0`** mà **`EXIT=1`**. Luật cũ ("nếu in `tests 1` thì glob đã mất") vẫn đúng nhưng **chưa đủ** — **luôn đọc EXIT kèm dòng tổng kết**. Không có exit code thì không có kết luận.
7. **Task 9 tiêu thụ `endpoints.affectedPreview` nhưng danh sách Files của Task 9 KHÔNG có `endpoints.ts`.** Nếu Task 2 không tạo thì Task 9 phải sửa một tệp dùng chung (hai người ghi). Task 2 đã tạo sẵn `affectedPreview` + `glossaryVersion` và ghi rõ trong comment rằng route `GET /api/glossary/affected` **ra đời ở Task 9** ⇒ **wrapper đó chưa chạy được cho tới Task 9**; đừng "sửa" nó thành chạy được bằng cách bịa route.
8. **`tsconfig.json` đã phải sửa ở Task 2, và có ĐÁNH ĐỔI phải nói thẳng.** `npm run typecheck` đỏ vì `TS2591` (không có `@types/node`, `npm i` bị chặn), `TS5097` (Node ESM bắt buộc đuôi `.ts` tường minh) và `TS18046`. Cách sửa đã dùng: `"allowImportingTsExtensions": true` + **`"exclude": ["src/**/*.test.ts","src/**/*.test.tsx"]`**.
   ⇒ **Hệ quả bắc cầu: `contract.test.ts` KHÔNG được `tsc` kiểm kiểu** — nợ `N-2` lan từ `frontend/test/` sang `src/`. Và **mọi test `.test.tsx` của T6/T8/T9/T10 cũng sẽ bị loại khỏi `tsc`**. Nghĩa là **"build xanh" KHÔNG bao hàm "test không có lỗi kiểu"** — test vẫn chạy nên lỗi kiểu sẽ lộ ở lúc chạy, nhưng đừng đọc "build xanh" là "type sạch cho cả test".
9. **Bài `translations[]` của contract test hiện RỖNG VỀ DỮ LIỆU** trên DB repo (`0 hàng`), nên nó chỉ được chứng minh không-rỗng nhờ một DB scratch gieo riêng. Muốn ghim thật thì **Task 12 phải gieo dữ liệu vào DB thật** trước khi chạy e2e — đó là lý do Task 12 tồn tại.

## Quy ước thẩm mỹ — spec UI thắng, skill chỉ là checklist

Spec `2026-09-25-phu-de-lab-ui-design.md` là **nguồn có thẩm quyền về hình thức** (bạn đã duyệt). Skill
`design-taste-frontend-v1` được dùng như **checklist**, không phải thẩm quyền thứ hai. Cụ thể:

**LẤY từ skill (đã đối chiếu, không mâu thuẫn spec UI):**
- **Grain/noise CHỈ trên một lớp `fixed` + `pointer-events:none`, KHÔNG bao giờ trên container cuộn** — tránh GPU repaint liên tục khi cuộn 2000 dòng. (Khớp §8.6 và **củng cố** nó bằng lý do.)
- **Chỉ animate `transform` và `opacity`**; không animate `top`/`left`/`width`/`height`.
- **Tiết chế `z-index`**: chỉ dùng cho tầng hệ thống (header dính, overlay), không rải `z-50` tuỳ tiện.
- **Trạng thái tương tác đầy đủ**: loading **dạng skeleton khớp kích thước bố cục** (không spinner tròn), trạng thái rỗng, trạng thái lỗi inline; phản hồi chạm bằng `translate`/`scale` nhẹ.
- **Form: nhãn TRÊN input, lỗi DƯỚI input**, khoảng cách nhất quán (dùng cho form Thuật ngữ, Task 9).
- **Kiểm tra `package.json` trước khi import bất kỳ thư viện nào** — không giả định gói tồn tại.
- **Không emoji** trong code/nhãn/alt.
- **Không `#000000`** — dùng off-black/charcoal; **tối đa MỘT màu nhấn**; không glow neon, không gradient text cho tiêu đề lớn.
  ⚠️ **ĐÍNH CHÍNH (review Task 1 bắt được):** tôi từng viết ở đây "độ bão hoà < 80% … đã đối chiếu, không mâu thuẫn". **Sai.**
  Spec §2.2 chốt `--signal:#FFB020` với HSL S = **100%**, và đó là **HIỆU ỨNG DUY NHẤT** của bảng màu. Spec thắng skill.
  `tokens.css:16` chép đúng spec ⇒ **giữ nguyên**, đừng "hạ bão hoà cho hợp skill". Luật còn hiệu lực chỉ là *tối đa MỘT màu nhấn*.

**KHÔNG lấy (và vì sao):**
- **Tailwind** (skill đòi cho 90% styling) — spec frontend §2 đã loại; và thêm một bước build nữa vào đúng chỗ vừa hỏng.
- **Framer Motion / GSAP / ThreeJS / thư viện icon (`@phosphor-icons`, `@radix-ui/react-icons`)** — dependency mới cho thứ chưa đo được nhu cầu, trong môi trường mà `npm i` **đang chết vì cache**. Ponytail rung 5.
- **`DESIGN_VARIANCE: 8`** (bất đối xứng, masonry, `padding-left: 20vw`) — spec UI §3 chốt **lưới ba vùng cố định 214px/286px**; bàn làm việc mật độ cao **không phải** landing page.
- **`MOTION_INTENSITY: 6`** (vi animation vĩnh viễn, magnetic button, parallax) — skill tự nói mức 4–7 dùng transition CSS; mức 6 của nó kéo theo Framer Motion. Spec UI §2.6 mới là nguồn.
- **`VISUAL_DENSITY: 4`** — sai hướng: bàn làm việc này gần "cockpit" hơn, và ở mức 8–10 thì chính skill nói **bỏ hộp card, dùng đường 1px** — đúng thứ spec UI §2.5/§4.1 đã yêu cầu.
- **Server Components (RSC)** — dự án là **SPA client-only, không router, không Next.js**.
- **Cấm `Inter`** — spec UI §2.1 đã chốt bộ chữ của nó (Archivo Expanded ở §4.2); spec thắng.

## Ruling sau review Task 1 — `CONDITIONAL PASS`, có **1 Critical**

Review độc lập ngày hôm nay, phạm vi `5d3a548..a2df315`. **Đã kiểm chứng thật** (không phải lời khai):
build xanh **344 ms**, bundle **665.147 B** khép kín, `from "react"` = **0**, `node --check` exit 0,
`dev-server.mjs` ở 3100 + proxy + **tính chất strict-port ĐẠT** (trùng cổng thì chết, không nhảy cổng),
tokens khớp spec §2 **từng giá trị** (11 màu khớp từng ký tự, grain **0,028 = 2,8%** đè đúng lên 0,035 sai của brief),
không Tailwind/component/icon lib, không `#000`, không emoji, grain **một lớp** `fixed`+`pointer-events:none`, không animation ngoài `transform`/`opacity`.

### Chặn — phải sửa TRƯỚC bước 1 của Task 2

**`C-1` (Critical) — `frontend/package.json:10` vẫn là `"test": "vitest run"`.**
Nguyên nhân là **lỗi của tôi**: tôi viết khối ERRATA ở commit `e7fbf29`, tức **sau** `a2df315`, nên `package.json` và `README.md`
**chưa từng được áp ERRATA lần nào**. Đây không phải bất cẩn lúc viết code.
Bằng chứng: `npm test` → `'vitest' is not recognized as an internal or external command`, `EXIT=1`; `node_modules/vitest` → `False`.
Hệ quả: plan gọi `npm test` **9 lần** (T2/T4/T5/T6/T8/T9/T10/T11) — mọi bước RED của giai đoạn đều đang dựa vào một lệnh chết.

**`I-1` (Important) — `README.md` mục "Chạy frontend" vẫn tả Vite**, trỏ `frontend/vite.config.ts` (**tệp đã bị xoá**),
dạy `tsc -b && vite build` và `vitest run`, không nhắc Rollup/`dev-server.mjs`/`node --test`, và bảo người dùng
`npm install` (chết `EPERM` ở sandbox này) rồi `npm run dev` **mà không build**.

**`I-2` (Important) — vòng lặp dev không tồn tại như plan tưởng.** `npm run dev` phục vụ `dist/` **tĩnh, không watcher, không build**:
rename `dist` ⇒ `GET /` trả **404**; sửa mã xong phải `npm run build` tay. Plan coi đây là vòng lặp nhanh cho 12 task còn lại.
**Ruling:** thêm build-on-demand (hoặc `--watch`) vào `dev-server.mjs`, **và** `npm run typecheck` là **bắt buộc** trong mọi báo cáo "xong" —
vì `npm run build` = `rollup -c` **không** chạy `tsc`, nên một task có thể báo "build xanh" trong khi type sai và người kiểm đang nhìn bundle cũ.
Bốn task (T4 Step 6, T6, T7 Step 4, T10 Step 4) ra lệnh "tự kiểm bằng mắt trên trình duyệt thật" — lệnh đó vô nghĩa nếu bundle đang phục vụ là bundle cũ.

### Ruling kỹ thuật — những thứ này phải chốt trước khi Task 2 xây lên trên

- **`I-3` — guard `assert-no-bare-imports` (`rollup.config.mjs:166-186`) KHÔNG BAO GIỜ CHẠY.** `onwarn` (`:199`) ném lỗi ở pha **build**,
  trước `generateBundle`, nên guard không tới được đúng ca nó sinh ra để bắt. Bảo vệ là **thật** nhưng công lao thuộc `onwarn`; cái tên được đặt thì nói dối.
  Bằng chứng: chèn `import "node:fs";` → `[!] Error: "node:fs" is imported by "src/main.tsx", but could not be resolved … at onwarn (rollup.config.mjs:199:90)`, `BUILD EXIT=1`,
  **không một dòng nào của guard**. **Ruling:** hoặc xoá guard, hoặc chuyển nó sang hook chạy được — không để lại thứ trông như đang bảo vệ mà không bảo vệ.
- **`I-4` — shim `cjs-inproc` (`:29-36, :64-119`) rất hẹp và thất bại IM LẶNG.** Nó chỉ đúng với đúng các tệp React nó được nắn.
  Gói CJS dùng `Object.defineProperty(exports,"__esModule")` ⇒ **build XANH, guard im lặng**, bundle chứa `exports` trần ⇒ `ReferenceError: exports is not defined` trong trình duyệt;
  CJS có `exports.default` ⇒ vỡ to; `react-dom/server` ⇒ `"util" could not be resolved`. **370 tệp** trong `node_modules` máy này khớp mẫu làm chết im lặng.
  **Ruling:** **không thêm dependency runtime mới mà không chạy probe** trên chính gói đó; và bất kỳ "build xanh" nào cũng phải kèm mở trang thật.
- **`I-5` — font self-host (§2.1) KHÔNG CÓ CHỦ.** 0 tệp `.woff2` trong repo, không `frontend/public/`, không `@font-face` ⇒ ba mặt chữ hiện chỉ là **cái tên**, render thật bằng `system-ui`.
  Bảng phủ sóng gán §2.1 cho Task 1 nhưng danh sách tệp của Task 1 không có nó, và **cả 13 task không task nào** tạo font.
  **Ruling:** giao lại cho **Task 1 (bổ sung)**, và phải là **variable font** vì `--font-label` cần trục `wdth` (Archivo Expanded) — không có trục đó thì "nhãn khắc" bất khả.
  Chưa có font thì **mọi ảnh chụp dùng làm bằng chứng nghiệm thu ở T4/T6/T8/T10 đều là `system-ui`**, tức không phán được "đúng bản sắc".
- **`Q-1` — ĐÃ CHỐT BẰNG ĐO (không còn mở): test chạy bằng `node --test --test-isolation=none` + một loader SWC trong tiến trình.**
  Đo trên máy này, trên nhánh này:

  | Phép thử | Kết quả |
  |---|---|
  | `node --test src/__probe.test.ts` (mặc định) | **`EPERM` (`errno -4048`, `syscall: spawn`)** — runner spawn tiến trình con cho mỗi tệp test, cùng bẫy named-pipe đã giết Vite |
  | `node --test --test-isolation=none src/__probe.test.ts` | `✔ … pass 1 fail 0`, **exit 0** — và **TypeScript chạy nguyên bản**, `interface` không cần build |
  | `.tsx` **không** loader | `TypeError [ERR_UNKNOWN_FILE_EXTENSION]: Unknown file extension ".tsx"` |
  | `.tsx` + `--import ./__swc_loader.mjs` (dùng `module.registerHooks` + `@swc/core`) | `✔ JSX + renderToStaticMarkup khong can DOM … pass 1 fail 0`, **exit 0** |
  | `jsdom`, `@testing-library/react`, `@testing-library/dom`, `happy-dom` | **`False`** — đều không có, và `npm i` bị chặn |

  **Ruling:**
  1. Runner là **`node --test --test-isolation=none`**. `--test-isolation=none` là **bắt buộc**, không phải tuỳ chọn — thiếu nó thì mọi test chết `EPERM`.
  2. Test `.tsx` chạy qua một **loader `@swc/core` trong tiến trình** (`module.registerHooks`, `transformSync` — napi, **không spawn**). Loader là ~20 dòng; **phải có test ghim chính nó**, vì nó là hạ tầng của mọi test UI.
  3. **Không có DOM ⇒ không `jsdom`, không Testing Library.** Test cấu trúc component dùng **`react-dom/server.renderToStaticMarkup`** — render React **thật**, không cần DOM. Đây không phải giả lập.
  4. **Hệ quả phải nói thẳng:** test đơn vị **không mô phỏng được tương tác** (click, focus, bàn phím, effect, state update). Mọi thứ thuộc loại đó — đặc biệt **§12.5 "toàn bộ luồng biên tập không cần chuột"** của T11 — **chỉ** chứng minh được bằng Playwright trên backend thật. Trong T6/T8/T9/T10, test Testing Library mà plan mô tả phải viết lại thành: (a) khẳng định **mã HTML render ra**, và (b) khẳng định **hàm thuần** (reducer, parser, formatter) — không mô phỏng sự kiện.
  5. Vì thế `T11` (bàn phím) **không được** tuyên bố "xong" chỉ bằng test đơn vị. Không có bước Playwright thì chưa chứng minh được gì cho §12.5.

### Minor + ghi nhận

- `M-1` — `EADDRINUSE` chết bằng stack thô, không thông báo đọc được. Tính chất strict-port vẫn **ĐẠT**; chỉ là thông báo.
- `G-1` — `npm run build` **không** typecheck (xem `I-2`).
- `G-2` — `package-lock.json` cũ ⇒ `npm ci` **phải** fail; **không Critical** vì ERRATA đã ghi, cấm sửa tay, và không task nào dùng `npm ci`.
- `G-3` — `fa51e10` một mình là cây **không build được** (nó chỉ xoá `vite.config.ts`). Tách hai commit là thật về nội dung; câu chuyện pathspec **bất khả kiểm chứng** từ git.
- **Bài học mutation, ghi lại vì tôi đã sai:** probe mutation tôi đưa trong brief (`import { readFileSync } from "node:fs"` **không dùng**) **không kiểm tra được gì** —
  SWC elide import không dùng nên build vẫn XANH. Phải dùng **import còn sống** (`import "node:fs";`) mới đỏ.
  Đây là **lần thứ hai trong phiên này** một dự đoán của tôi về phép kiểm sai (lần trước: 7 dự đoán sai về số test / mutant nào chết).
  Từ đây: mọi probe mutation phải dùng thứ **có tác dụng thật**, và phải nói rõ nó chứng minh được gì.

## File Structure

**Tạo mới** (tất cả dưới `frontend/`)

| Tệp | Trách nhiệm |
|---|---|
| `package.json` · `tsconfig.json` · `rollup.config.mjs` · `dev-server.mjs` · `test/swc-loader.mjs` | cấu hình: cổng 3100, proxy `/api`, build Rollup, runner `node --test --test-isolation=none` + loader SWC |
| `index.html` | một trang, không route |
| `src/main.tsx` | gắn React vào `#root` |
| `src/styles/tokens.css` | custom property lấy từ spec UI §2 |
| `src/styles/app.css` | bố cục ba vùng + transport; **một** lớp grain `pointer-events:none` |
| `src/styles/fonts/` | woff2 self-host (**không CDN**) |
| `src/api/types.ts` | type viết tay theo JSON **thật** của backend |
| `src/api/client.ts` | `fetch` wrapper: một chỗ biết base URL, ném lỗi có cấu trúc |
| `src/api/endpoints.ts` | hàm theo nhóm: sources, jobs, transcripts, translations, glossary, registry, status, export, media |
| `src/api/sse.ts` | parser SSE thuần (ảnh chụp + sự kiện, `data:` bị cắt giữa hai lần đọc) |
| `src/state/reducer.ts` | trạng thái client: kênh chọn, đoạn phát, dòng sửa, mode, ghim bản B |
| `src/state/useJobStream.ts` | **một** subscription SSE, backoff, đọc lại ảnh chụp khi nối lại |
| `src/state/useApi.ts` | `fetch` + trạng thái loading/lỗi, không cache |
| `src/lib/window.ts` | cửa sổ hoá hàng cao đều + ghim dòng (thuần, test không cần DOM) |
| `src/lib/timecode.ts` | định dạng/đọc timecode `0:04.12 / 12:04.30` (thuần) |
| `src/shell/App.tsx` · `Header.tsx` · `ChannelZone.tsx` · `QueueZone.tsx` · `Transport.tsx` | khung |
| `src/screens/EditScreen.tsx` · `CompareScreen.tsx` · `GlossaryScreen.tsx` | ba màn |
| `src/screens/OllamaDown.tsx` | trạng thái §4.8 |
| `src/keys/shortcuts.ts` | bảng phím tắt + bộ xử lý (thuần, test được) |
| `src/api/contract.test.ts` | contract test chạy trên **backend thật** |
| `e2e/seed.ts` · `e2e/*.spec.ts` | gieo DB + Playwright bốn màn hình |

**Sửa:** `README.md` (mục chạy frontend), `.gitignore` (`frontend/node_modules`, `frontend/dist`, `test-results/`).

---

### Task 1: Khung dựng được — Vite + React 19 + TS ở cổng 3100

> **✅ ĐÃ XONG — và các bước dưới đây là bản GỐC THỜI VITE, đã bị ERRATA đè.** Thực tế đã giao: `rollup.config.mjs` + `dev-server.mjs` (không Vite), commit `a2fffe1`·`ffe8613`·`fa51e10`·`a2df315`.
> **Đừng chạy lại các bước này.** Chúng giữ ở đây làm hồ sơ. Ba việc còn nợ của Task 1 nằm ở mục `## Ruling sau review Task 1`: `C-1` (script `test`), `I-1` (README), `I-2` (vòng lặp dev), `I-5` (font).

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/shell/App.tsx`, `frontend/src/styles/tokens.css`, `frontend/src/styles/app.css`
- Modify: `.gitignore`, `README.md`

**Interfaces:**
- Consumes: không
- Produces: `npm run dev` phục vụ ở **3100** và proxy `/api` sang **8620**; `App` là shell rỗng ba vùng; token CSS đặt tên theo spec UI §2

- [ ] **Step 1: Khởi tạo và cài đúng thứ cần**

```bash
cd frontend
npm init -y
npm i react@19 react-dom@19
npm i -D vite@^6 @vitejs/plugin-react typescript @types/react @types/react-dom
```

Không cài gì khác. Nếu một bước nào đó thôi thúc bạn thêm `tailwindcss`, `@tanstack/*`, `zustand`, `@mui/*` — đó là thứ spec §2 đã cố ý loại; dừng lại.

Rồi **ghi `scripts` vào `package.json`** — `npm init -y` **không** tạo chúng, và plan này dạy `npm run dev` / `npm test` / `npm run e2e` ở nhiều task sau:

```json
{
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "e2e": "playwright test"
  }
}
```

Giữ nguyên các trường khác mà `npm init -y` đã tạo.

- [ ] **Step 2: `vite.config.ts` — cổng và proxy**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3100,
    strictPort: true,          // trùng cổng thì BÁO, không lặng lẽ nhảy cổng khác:
                               // backend chỉ cho CORS hai origin ở 3100
    proxy: { "/api": "http://127.0.0.1:8620" },
  },
});
```

- [ ] **Step 3: `tokens.css` — custom property từ spec UI §2**

Đọc `docs/superpowers/specs/2026-09-25-phu-de-lab-ui-design.md` §2.1 (chữ), §2.2 (màu), §2.3 (không gian), §2.4 (bề mặt), §2.6 (chuyển động) rồi chép **giá trị thật** vào:

```css
:root {
  /* màu, chữ, khoảng cách, bề mặt, chuyển động — giá trị chép từ spec UI §2 */
  --grain-opacity: 0.035;
  color-scheme: dark;          /* §10.1: chỉ MỘT chế độ tối, không chuyển đổi */
}
```

Ô nào spec UI không ghi giá trị cụ thể thì bạn **chọn** và ghi vào đây; đừng để `TBD`.

- [ ] **Step 4: `app.css` — lưới ba vùng + MỘT lớp grain**

```css
.shell { display: grid; grid-template-rows: 48px 1fr 56px; height: 100vh; }
.shell__mid { display: grid; grid-template-columns: 214px 1fr 286px; min-height: 0; }
/* §8.6: grain là MỘT lớp phủ toàn trang, không lặp trong từng component */
.grain { position: fixed; inset: 0; pointer-events: none; opacity: var(--grain-opacity); z-index: 1; }
```

`214px` và `286px` là số của spec UI §3, không phải số của bạn.

- [ ] **Step 5: `App.tsx` — shell rỗng nhưng đúng hình dạng**

```tsx
export function App() {
  return (
    <div className="shell">
      <header className="shell__head" />
      <div className="shell__mid">
        <aside className="shell__channels" />
        <main className="shell__work" />
        <aside className="shell__queue" />
      </div>
      <footer className="shell__transport" />
      <div className="grain" aria-hidden />
    </div>
  );
}
```

- [ ] **Step 6: Chạy và TỰ KIỂM bằng số, không bằng mắt**

```bash
cd frontend
npm run dev   # nền
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3100/
```

Kỳ vọng: `200`. Rồi kiểm proxy **thật sự** chuyển tiếp — khởi động backend ở cửa sổ khác và:

```bash
curl -s http://127.0.0.1:3100/api/status
```

Kỳ vọng: JSON của backend (không phải HTML của Vite). Nếu trả HTML thì proxy **sai** — sửa trước khi đi tiếp.

- [ ] **Step 7: `.gitignore` và `README.md`**

Thêm `frontend/node_modules/`, `frontend/dist/`, `frontend/test-results/`. README thêm mục "Chạy frontend": hai lệnh (backend, frontend) và cổng của từng cái.

- [ ] **Step 8: Commit**

```bash
git add frontend .gitignore README.md
git commit -m "feat(fe): khung Vite + React 19 o cong 3100, proxy /api sang 8620"
```

---

### Task 2: Tầng API — type viết tay + wrapper + contract test

**Vì sao không sinh type:** spec §2 chốt rằng thứ **nhỏ nhất** sập khi shape trôi là một contract test, và nó sập **ồn ào**; codegen thêm một dev-dependency **và** một bước phải nhớ chạy lại.

**Files:**
- Create: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/endpoints.ts`, `frontend/src/api/contract.test.ts`
- Modify: `frontend/package.json` (**`test` → `node --test`**, xem `C-1`), `frontend/test/swc-loader.mjs` (nếu Task 1 chưa tạo)

**Interfaces:**
- Consumes: cổng 3100/proxy của Task 1
- Produces: `type Job`, `Source`, `Transcript`, `Segment`, `Translation`, `Term`, `EngineSpec`, `Status` · `api.get/post/patch` ném `ApiError` có `status` và `detail` · các hàm trong `endpoints.ts` · suite `node --test` chạy được bằng `npm test`

- [ ] **Step 1: Dựng runner `node --test` — KHÔNG cài gì**

**Không cài Vitest, không cài jsdom, không cài Testing Library.** Cả ba đều không dùng được ở môi trường này (đo rồi — xem `Q-1`).
Task này **không có bước `npm install` nào**.

Tạo `frontend/test/swc-loader.mjs` — loader duy nhất khiến `.tsx` chạy được, dùng `module.registerHooks` (hook **đồng bộ**, chạy trong tiến trình) cộng `@swc/core` (`transformSync`, napi — **không spawn**):

```js
import { registerHooks } from "node:module";
import { readFileSync } from "node:fs";
import { transformSync } from "@swc/core";

registerHooks({
  load(url, context, nextLoad) {
    if (url.startsWith("file:") && (url.endsWith(".tsx") || url.endsWith(".ts"))) {
      const tsx = url.endsWith(".tsx");
      const out = transformSync(readFileSync(new URL(url), "utf8"), {
        filename: new URL(url).pathname,
        jsc: { parser: { syntax: "typescript", tsx }, target: "es2022",
               transform: { react: { runtime: "automatic" } } },
        module: { type: "es6" },
      });
      return { format: "module", source: out.code, shortCircuit: true };
    }
    return nextLoad(url, context);
  },
});
```

Khai `scripts` (đây là bản **đã áp ERRATA**; `package.json` hiện tại còn `vitest run` — sửa luôn):

```json
{
  "type": "module",
  "scripts": {
    "dev": "node dev-server.mjs",
    "build": "tsc --noEmit && rollup -c",
    "typecheck": "tsc --noEmit",
    "test": "node --import ./test/swc-loader.mjs --test --test-isolation=none \"**/*.test.{ts,tsx,mjs,js}\"",
    "e2e": "playwright test"
  }
}
```

**BỐN** điều **bắt buộc**, không phải tuỳ chọn — mỗi điều đã được đo là nguyên nhân gây chết:

1. **`--test-isolation=none`**: thiếu nó, runner `node --test` spawn tiến trình con cho mỗi tệp test và chết
   `EPERM (errno -4048, syscall: spawn)` — đúng cái bẫy named-pipe đã giết Vite.
2. **`--import ./test/swc-loader.mjs`**: thiếu nó, mọi tệp `.tsx` chết `ERR_UNKNOWN_FILE_EXTENSION`.
   (Tệp `.ts` **không** cần loader — Node 24 tự bóc kiểu; nhưng cứ để loader lo cả hai cho nhất quán.)
3. **`build` phải gồm `tsc --noEmit`**: `rollup -c` **không** kiểm kiểu, nên nếu tách rời thì một task có thể báo
   "build xanh" trong khi type sai. Bốn task sau (T4 Step 6, T6, T7 Step 4, T10 Step 4) ra lệnh "tự kiểm bằng mắt trên trình duyệt thật".
4. **GLOB LÀ BẮT BUỘC — thiếu nó là XANH GIẢ, và đây là lỗi nặng nhất mà plan này từng có.**
   Plan bản đầu ghi script **không glob**. Implementer đo được: lệnh y nguyên
   `node --import ./test/swc-loader.mjs --test --test-isolation=none`
   → `✔ test\swc-loader.mjs`, `tests 1 pass 1 fail 0`, **LITERAL_EXIT=0**.
   Nghĩa là nó chỉ **nạp chính loader như một "tệp test" rỗng**, còn **hai bài thật không hề chạy** — mà exit vẫn 0.
   Nguyên nhân: **Node 24 discovery mặc định chạy `**/*.test.ts` nhưng KHÔNG chạy `**/*.test.tsx`.**
   Vì plan đặt tên mọi test màn hình là `EditScreen.test.tsx`, `CompareScreen.test.tsx`, … nên **8–10 task sẽ làm RED/GREEN
   trên những bài không bao giờ chạy**, và mọi báo cáo "test xanh" của giai đoạn sẽ là **giả**.
   Có glob (`"**/*.test.{ts,tsx,mjs,js}"`) → `tests 2 pass 2`; sau vòng `I-4` → `tests 6 pass 6` (người điều phối tự chạy, exit 0).
   **Luật cho mọi task:** nếu `npm test` in `tests 1` thì glob đã mất — **dừng lại và sửa**, đừng đọc "pass 1" là xanh.
   Đủ **cả bốn**: `--test-isolation=none` + `--import` + **glob** + `tsc --noEmit` trong `build`.

Ghim chính loader bằng test của nó — nó là hạ tầng của **mọi** test UI, một loader hỏng làm 12 task sau đỏ giả:

⚠️ **Tên tệp phải là `.tsx`, KHÔNG phải `.ts`** (plan từng ghi `.ts` — đó là lỗi của plan, implementer bắt được).
Loader đặt `tsx: url.endsWith(".tsx")`, nên một tệp `.ts` **không được phép chứa JSX**: để bài dùng JSX trong `.ts` thì SWC ném
`Syntax Error` **ngay lúc load** và **cả hai** bài không chạy được. Quy tắc cho mọi task sau: **tệp test nào chứa JSX thì đuôi phải là `.tsx`.**

```tsx
// frontend/test/swc-loader.test.tsx
import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { Probe } from "./fixtures/Probe.tsx";

// (a) chỉ chứng minh tệp .tsx chạy được qua đường GỌI HÀM
test("a) .tsx chạy được: gọi hàm component rồi render thật ra HTML", () => {
  assert.equal(renderToStaticMarkup(Probe({ label: "xin chao" })),
               '<span class="probe">xin chao</span>');
});

// (b) dùng JSX THẬT — đây mới là bài ghim đường JSX
test("b) đường JSX thật qua loader SWC", () => {
  assert.equal(renderToStaticMarkup(<Probe label="xin chao" />),
               '<span class="probe">xin chao</span>');
});
```

**Hai bài, không phải một** — và đó không phải hình thức.
⚠️ **ĐÍNH CHÍNH (vòng re-review Task 1 đo lại — câu gốc ở đây SAI):** plan bản đầu viết *"Bỏ `runtime: "automatic"` ⇒ **(b) ĐỎ** còn **(a) vẫn XANH**; tức chỉ (b) ghim được runtime JSX"*.
**Đo được: `fail 2` — CẢ HAI bài đỏ** (`ReferenceError: React is not defined` ở cả hai), vì `fixtures/Probe.tsx` **cũng là TSX chứa JSX**, nên mất runtime JSX thì chính fixture không biên dịch được. Hai bài **không** khác sức mạnh dưới mutation đó.
**Hai bài khác sức mạnh ở chỗ khác:** bỏ hẳn `--import` ⇒ `ERR_UNKNOWN_FILE_EXTENSION`, tức bài (a) ghim chính **LOADER**, không chỉ đường JSX.
(`Probe` render ra `<span class="probe">`, không phải `<p>`.)

`frontend/test/fixtures/Probe.tsx` là một component 3 dòng có một prop. **Mutation để chứng minh test không rỗng:**
xoá `transform: { react: { runtime: "automatic" } }` khỏi loader ⇒ tệp dùng JSX phải đỏ; khôi phục ⇒ xanh.
Nếu nó **không** đỏ, mutation của bạn sai, không phải test đúng.

**Không** tạo `vitest.config.ts`, **không** tạo `vite.config.ts`. Cấu hình test nằm ở `scripts` — một nguồn sự thật.

- [ ] **Step 2: Viết contract test ĐỎ trước — và nó phải chạy trên BACKEND THẬT**

```ts
// frontend/src/api/contract.test.ts
/**
 * Chạy trên backend THẬT ở 8620. Test này tồn tại vì Giai đoạn 2 đã đổi tên khoá
 * `translated_from_version` -> `transcript_version` và một client viết tay sẽ trôi
 * trong im lặng. Đổi shape ở server PHẢI làm file này đỏ.
 */
import { beforeAll, describe, expect, it } from "vitest";
import { BASE } from "./client";

const up = async (path: string) => {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
};

describe("hop dong API that", () => {
  beforeAll(async () => {
    const r = await fetch(`${BASE}/api/status`).catch(() => null);
    if (!r?.ok) throw new Error("backend 8620 khong chay — khoi dong backend truoc khi chay test nay");
  });

  it("GET /api/registry tra danh sach engine co truong available", async () => {
    const body = await up("/api/registry");
    const specs = Array.isArray(body) ? body : body.engines;
    const first = specs[0];
    for (const key of ["id", "label", "kind", "runtime", "model_ref", "vram_mb"]) {
      expect(first, `thieu khoa ${key}`).toHaveProperty(key);
    }
    expect(first.capabilities).toHaveProperty("available");
  });

  it("GET /api/status co ollama va vram", async () => {
    const body = await up("/api/status");
    expect(body).toHaveProperty("ollama");
    expect(body).toHaveProperty("vram");
  });

  it("GET /api/transcripts tra mang", async () => {
    expect(Array.isArray(await up("/api/transcripts"))).toBe(true);
  });
});
```

- [ ] **Step 3: Chạy để thấy ĐỎ**

```bash
cd frontend && npm test -- contract
```

Kỳ vọng: đỏ vì **backend chưa chạy** (`backend 8620 khong chay`). Đó là RED thật, không phải RED giả. Rồi khởi động backend và chạy lại — vẫn phải đỏ, lần này vì `./client` chưa tồn tại.

- [ ] **Step 4: `client.ts` và `types.ts`**

```ts
// client.ts
export const BASE = "/api";        // proxy cua dev-server.mjs lo phan con lai

export class ApiError extends Error {
  constructor(readonly status: number, readonly detail: string) {
    super(`${status}: ${detail}`);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    // detail cua FastAPI la {detail: "..."} — doc no ra de nguoi doc thay LY DO,
    // khong phai chi thay "500".
    const detail = await r.json().catch(() => ({ detail: r.statusText }));
    throw new ApiError(r.status, String(detail.detail ?? r.statusText));
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

export const api = {
  get: <T>(p: string) => call<T>("GET", p),
  post: <T>(p: string, b?: unknown) => call<T>("POST", p, b),
  patch: <T>(p: string, b?: unknown) => call<T>("PATCH", p, b),
};
```

`types.ts` viết tay đúng **JSON thật** — mở `backend/app/domain/models.py` (`to_json`) và `backend/app/api/*.py` để lấy tên khoá, **đừng** đoán từ tên dataclass. Bắt đầu bằng `Segment`, `Job`, `Source`, `Transcript`, `Translation`, `Term`, `EngineSpec`, `Status`.

- [ ] **Step 5: `endpoints.ts` — một hàm cho mỗi thứ client thật sự gọi**

Chỉ những endpoint bốn màn hình cần: sources (list/upload/url), jobs (list/get/cancel/retry), transcripts (list/get/patch/approve), translations (create/list/patch), glossary (list/create/patch), registry, status, export URL, media URL. **Không** viết wrapper cho endpoint chưa có màn hình dùng.

- [ ] **Step 6: Chạy để XANH**

```bash
cd frontend && npm test -- contract
```

Kỳ vọng: `3 passed` (backend đang chạy). Rồi **chứng minh test không rỗng**: sửa tạm `contract.test.ts` đòi một khoá không tồn tại (`expect(first).toHaveProperty("khong_co_khoa_nay")`) ⇒ phải đỏ; phục hồi.

- [ ] **Step 7: Commit**

```bash
git add frontend
git commit -m "feat(fe): tang API + contract test chay tren backend that"
```

---

### Task 3: Parser SSE + một subscription duy nhất

**Vì sao parser là hàm thuần:** nó là chỗ dễ sai nhất (mảnh `data:` bị cắt giữa hai lần đọc, ảnh chụp rồi mới tới sự kiện) và nó **test được không cần DOM**. Tách nó ra thì test được bằng **`node --test` thuần**, không cần trình duyệt.

**Files:**
- Create: `frontend/src/api/sse.ts`, `frontend/src/api/sse.test.ts`, `frontend/src/state/useJobStream.ts`

**Interfaces:**
- Consumes: `api`, `types` (Task 2)
- Produces: `createSseParser(): { push(chunk: string): unknown[] }` · `useJobStream(): Map<number, Job>` — **một** kết nối cho cả app

- [ ] **Step 1: Viết test ĐỎ cho parser**

```ts
// frontend/src/api/sse.test.ts
import { describe, expect, it } from "vitest";
import { createSseParser } from "./sse";

describe("parser SSE", () => {
  it("tach duoc mot su kien hoan chinh", () => {
    const p = createSseParser();
    expect(p.push('data: {"id":1}\n\n')).toEqual([{ id: 1 }]);
  });

  it("ghep lai manh bi cat giua hai lan doc", () => {
    const p = createSseParser();
    expect(p.push('data: {"id"')).toEqual([]);          // chua du
    expect(p.push(':1}\n\n')).toEqual([{ id: 1 }]);     // xong o lan sau
  });

  it("bo qua dong comment giu nhip tim", () => {
    const p = createSseParser();
    expect(p.push(": ping\n\n")).toEqual([]);
  });

  it("tra NHIEU su kien tu mot lan doc", () => {
    const p = createSseParser();
    expect(p.push('data: {"id":1}\n\ndata: {"id":2}\n\n')).toEqual([{ id: 1 }, { id: 2 }]);
  });

  it("json hong thi bo qua su kien do, khong nem", () => {
    // Mot su kien hong khong duoc giet ca stream: mat ket noi vi mot dong rac la
    // mat luon tien do cua moi job khac.
    const p = createSseParser();
    expect(p.push("data: {khong-phai-json}\n\n")).toEqual([]);
  });
});
```

- [ ] **Step 2: Chạy để thấy ĐỎ**

```bash
cd frontend && npm test -- sse
```
Kỳ vọng: `Failed to resolve import "./sse"`.

- [ ] **Step 3: Viết parser**

```ts
// frontend/src/api/sse.ts
/** Parser SSE thuần: nhận mảnh thô, trả về các sự kiện JSON đã hoàn chỉnh.
 *
 * `ponytail:` ghep theo `\n\n` va giu phan du trong bo dem. Du cho stream mot
 * chieu cua app nay (khong co `event:`/`id:`/`retry:`). Nang cap: dung
 * `EventSource` hoac mot parser day du khi can resume theo `Last-Event-ID`.
 */
export function createSseParser() {
  let buf = "";
  return {
    push(chunk: string): unknown[] {
      buf += chunk;
      const out: unknown[] = [];
      let i: number;
      while ((i = buf.indexOf("\n\n")) !== -1) {
        const raw = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const data = raw
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trim())
          .join("");
        if (!data) continue;                       // comment giu nhip tim
        try {
          out.push(JSON.parse(data));
        } catch {
          // bo qua su kien hong, giu stream song — xem chu thich o test
        }
      }
      return out;
    },
  };
}
```

- [ ] **Step 4: Chạy để XANH**, rồi mutation: đổi `while ((i = buf.indexOf("\n\n")) !== -1)` thành `if (...)` ⇒ test "tra NHIỀU sự kiện" phải đỏ. Phục hồi và verify hash + byte.

- [ ] **Step 5: `useJobStream.ts` — đúng MỘT kết nối**

Dùng `fetch` + `ReadableStream` (không `EventSource`, vì cần mang theo header/thống nhất một đường `client.ts`), `AbortController` để đóng, backoff khi đứt, và **khi nối lại thì đọc lại ảnh chụp** bằng `GET /api/jobs` trước khi tin sự kiện mới. Test: một hàm `reconnectDelay(attempt, base)` thuần, ghim vài giá trị; phần mạng để Playwright phủ.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/sse.ts frontend/src/api/sse.test.ts frontend/src/state/useJobStream.ts
git commit -m "feat(fe): parser SSE thuan + mot subscription job cho ca app"
```

---

### Task 4: Reducer trạng thái client + shell nối được dữ liệu

**Files:**
- Create: `frontend/src/state/reducer.ts`, `frontend/src/state/reducer.test.ts`, `frontend/src/state/useApi.ts`
- Modify: `frontend/src/shell/App.tsx`, `frontend/src/shell/Header.tsx`, `frontend/src/shell/ChannelZone.tsx`, `frontend/src/shell/QueueZone.tsx`

**Interfaces:**
- Consumes: `endpoints`, `useJobStream` (Task 2–3)
- Produces: `type UiState`, `initialState`, `reduce(state, action)` · `<App/>` hiện kênh thật + hàng đợi thật

- [ ] **Step 1: Test ĐỎ cho reducer**

```ts
// frontend/src/state/reducer.test.ts
import { describe, expect, it } from "vitest";
import { initialState, reduce } from "./reducer";

describe("reducer trang thai client", () => {
  it("chon kenh thi dat kenh do va xoa doan dang phat", () => {
    // Doi kenh ma giu doan dang phat cu la hien thi noi dung cua kenh A trong
    // khung cua kenh B — dung loai "noi doi" ma giai doan 2 vua phai bit.
    const s = reduce({ ...initialState, channelId: 1, currentSegment: 9 },
                     { type: "selectChannel", id: 2 });
    expect(s.channelId).toBe(2);
    expect(s.currentSegment).toBeNull();
  });

  it("doi mode thi giu kenh va doan dang phat", () => {
    const s = reduce({ ...initialState, channelId: 1, currentSegment: 9 },
                     { type: "setMode", mode: "compare" });
    expect(s.mode).toBe("compare");
    expect(s.channelId).toBe(1);
    expect(s.currentSegment).toBe(9);
  });

  it("khong cho ghim ban B trung ban A", () => {
    const s = reduce({ ...initialState, pinnedB: null },
                     { type: "pinB", id: 3, aId: 3 });
    expect(s.pinnedB).toBeNull();
  });
});
```

- [ ] **Step 2: Chạy để thấy ĐỎ** — `npm test -- reducer` ⇒ `Failed to resolve import "./reducer"`.

- [ ] **Step 3: `reducer.ts`** — ba trường hợp trên cộng `setPlaying`, `setCurrentSegment`, `startEdit`/`endEdit`, `setError`. Giữ **một** object, không lồng sâu.

- [ ] **Step 4: `useApi.ts`** — `useApi(fn, deps) -> {data, error, loading, reload}` bằng `useEffect` + `AbortController`. Không cache, không dedupe: chưa đo được nhu cầu.

- [ ] **Step 5: Nối `App.tsx`** — `useApi(() => endpoints.listSources())`, `useJobStream()`, và render `ChannelZone` (danh sách tệp + trạng thái từng bước) và `QueueZone` (job đang chạy/chờ **kèm lý do chờ** lấy từ `phase` + `state`). Giữ nguyên lưới CSS của Task 1.

- [ ] **Step 6: Chạy cả suite** — `npm test`. Rồi tự kiểm bằng mắt **một lần** trên trình duyệt thật rằng không có lỗi console, và ghi lại ảnh chụp màn hình vào `.superpowers/` (không vào repo).

- [ ] **Step 7: Commit** — `feat(fe): reducer trang thai client + shell noi du lieu that`.

---

### Task 5: Cửa sổ hoá hàng cao đều + GHIM dòng đang sửa

**Vì sao tự viết:** hàng cao đều ⇒ đây là số học, và **test được không cần DOM**. Spec UI §8.2/§8.3 nói transcript 2 giờ ≈ 2000 dòng và dòng đang sửa phải được ghim.

**Files:**
- Create: `frontend/src/lib/window.ts`, `frontend/src/lib/window.test.ts`

**Interfaces:**
- Consumes: không (thuần)
- Produces: `visibleRange(scrollTop, viewportH, rowH, count, overscan) -> {start, end}` · `withPinned(range, pinnedIndex) -> {start, end, pinned: boolean}`

- [ ] **Step 1: Test ĐỎ**

```ts
// frontend/src/lib/window.test.ts
import { describe, expect, it } from "vitest";
import { visibleRange, withPinned } from "./window";

describe("cua so hoa hang cao deu", () => {
  it("tinh dung khoang hien thi", () => {
    expect(visibleRange(0, 400, 20, 2000, 0)).toEqual({ start: 0, end: 20 });
    expect(visibleRange(400, 400, 20, 2000, 0)).toEqual({ start: 20, end: 40 });
  });

  it("them overscan hai dau", () => {
    expect(visibleRange(400, 400, 20, 2000, 5)).toEqual({ start: 15, end: 45 });
  });

  it("khong vuot qua dau danh sach", () => {
    expect(visibleRange(0, 400, 20, 2000, 5).start).toBe(0);
  });

  it("khong vuot qua cuoi danh sach", () => {
    expect(visibleRange(1e9, 400, 20, 30, 5).end).toBe(30);
  });

  it("GHIM: dong dang sua ngoai khoang hien thi van duoc render", () => {
    // Khong ghim thi ao hoa se thao dong dang go khoi DOM -> mat focus.
    // Day la U6 cua spec UI, va la cho de tu ban vao chan nhat.
    expect(withPinned({ start: 100, end: 120 }, 7)).toEqual({ start: 7, end: 120, pinned: true });
  });

  it("GHIM: dong dang sua trong khoang thi khong doi gi", () => {
    expect(withPinned({ start: 100, end: 120 }, 110)).toEqual({ start: 100, end: 120, pinned: false });
  });

  it("GHIM: khong co dong dang sua thi tra nguyen", () => {
    expect(withPinned({ start: 100, end: 120 }, null)).toEqual({ start: 100, end: 120, pinned: false });
  });
});
```

- [ ] **Step 2: Chạy để thấy ĐỎ** — `npm test -- window`.

- [ ] **Step 3: Viết `window.ts`**

```ts
// frontend/src/lib/window.ts
/** Cua so hoa cho hang CAO DEU.
 *
 * `ponytail:` chi dung cho `rowHeight` co dinh. Hang cao khac nhau (doan dai
 * xuong dong) can do cao that -> thay bang `@tanstack/react-virtual`. Spec §2
 * co y KHONG keo dependency do vao chi vi 30 dong so hoc.
 */
export function visibleRange(scrollTop: number, viewportH: number, rowH: number,
                             count: number, overscan: number) {
  const first = Math.floor(scrollTop / rowH);
  return {
    start: Math.max(0, first - overscan),
    end: Math.min(count, Math.ceil((scrollTop + viewportH) / rowH) + overscan),
  };
}

/** Mo rong khoang de dong dang sua luon nam trong DOM (spec UI §8.3, U6). */
export function withPinned(range: { start: number; end: number }, pinned: number | null) {
  if (pinned === null || (pinned >= range.start && pinned < range.end)) {
    return { ...range, pinned: false };
  }
  return { start: Math.min(range.start, pinned), end: range.end, pinned: true };
}
```

- [ ] **Step 4: XANH + mutation** — đổi `withPinned`'s điều kiện thành `false` ⇒ test GHIM ngoài khoảng phải đỏ. Phục hồi, verify hash + byte.

- [ ] **Step 5: Commit** — `feat(fe): cua so hoa hang cao deu + ghim dong dang sua`.

---

### Task 6: §4.1 Màn BIÊN TẬP

**Files:**
- Create: `frontend/src/screens/EditScreen.tsx`, `frontend/src/screens/EditScreen.test.tsx`, `frontend/src/lib/timecode.ts`, `frontend/src/lib/timecode.test.ts`
- Modify: `frontend/src/shell/App.tsx`

**Interfaces:**
- Consumes: `window.ts` (Task 5), `endpoints`, `useJobStream`
- Produces: `formatTimecode(seconds) -> "0:04.12"` · `parseTimecode(text) -> number | null` · màn Biên tập hiện danh sách đoạn ảo hoá, sửa dòng được, và `suspect` có vân + lý do

- [ ] **Step 1: Test ĐỎ cho timecode** — `formatTimecode(4.12) === "0:04.12"`, `formatTimecode(724.3) === "12:04.30"`, `parseTimecode("12:04.30") === 724.3`, `parseTimecode("rác") === null`, `formatTimecode(3599.99) === "59:59.99"`. Chạy ⇒ đỏ.

- [ ] **Step 2: Viết `timecode.ts`** — `ponytail:` cố ý bỏ giờ (`h:mm:ss`); phụ đề dài nhất trong phạm vi này dưới một giờ, thêm khi có tệp dài hơn.

- [ ] **Step 3: Test ĐỎ cho màn Biên tập** (**KHÔNG Testing Library — không có DOM**; xem `Q-1`. Khẳng định **mã HTML** qua `renderToStaticMarkup` + khẳng định **hàm thuần**; `fetch` **giả** ở tầng `endpoints` — không phải tầng `window`):

```tsx
// frontend/src/screens/EditScreen.test.tsx
it("danh dau doan nghi ngo bang VAN va LY DO, khong chi bang mau", async () => {
  // Spec UI §2.5: "nghi ngo" la van, khong phai mau. Neu chi co mau thi nguoi
  // mu mau se mat thong tin, va spec §7 doi hoi kha nang tiep can.
  render(<EditScreen transcript={transcriptVoiMotDoanSuspect()} />);
  expect(await screen.findByText("nhạc nền")).toBeInTheDocument();
  expect(screen.getByTestId("seg-suspect").className).toContain("is-suspect");
});
```

- [ ] **Step 4: Viết `EditScreen.tsx`** — rail thời gian bên trái, danh sách dùng `visibleRange` + `withPinned`, đoạn đang phát có class lề amber, đoạn `suspect` có class vân + nhãn lý do lấy từ `Segment.qa`/`suspect`. Sửa dòng: `contentEditable` **không** dùng — dùng `<textarea>` tự giãn, đơn giản hơn và kiểm soát được focus.

- [ ] **Step 5: XANH + mutation** — bỏ nhãn lý do ⇒ test phải đỏ. Phục hồi, verify.

- [ ] **Step 6: Commit** — `feat(fe): man Bien tap voi danh sach ao hoa va doan nghi ngo`.

---

### Task 7: Thanh transport + player `Range`

**Files:**
- Create: `frontend/src/shell/Transport.tsx`, `frontend/src/shell/Transport.test.tsx`
- Modify: `frontend/src/shell/App.tsx`

**Interfaces:**
- Consumes: `endpoints.mediaUrl(sourceId)`, `endpoints.exportUrl(translationId, fmt, bilingual)`
- Produces: `<Transport/>` với nút phát, timecode mono, track có đầu đọc, ba nút xuất; phát tới mốc cuối của đoạn thì tự nhảy đoạn

- [ ] **Step 1: Test ĐỎ** — (a) bấm phát rồi tạm dừng thì `aria-pressed`/nhãn đổi đúng; (b) `timeupdate` vượt `segment.end` thì phát sự kiện "sang đoạn kế"; (c) ba nút xuất trỏ tới `/api/export/<id>?format=srt|vtt|ass`, **không** tự ghép URL ở client (dùng `endpoints.exportUrl`).

- [ ] **Step 2: Viết `Transport.tsx`** — `<audio>` (hoặc `<video>` khi nguồn là video) với `src` từ `endpoints.mediaUrl`. **Không** tự viết seek: trình duyệt đã làm, và backend đã hỗ trợ `Range`. `ponytail:` dùng phần tử media gốc thay vì một player library.

- [ ] **Step 3: XANH + mutation** — bỏ phép kiểm "vượt `segment.end`" ⇒ test (b) đỏ. Phục hồi.

- [ ] **Step 4: Tự kiểm bằng trình duyệt thật** rằng seek được (đây là thứ test đơn vị không chứng minh được): mở một source có media thật, tua vài lần, ghi lại rằng `Range` trả `206` — chụp `Network` hoặc `curl -H "Range: bytes=0-99" -i`. Dán output vào báo cáo.

- [ ] **Step 5: Commit** — `feat(fe): thanh transport + player dung Range cua backend`.

---

### Task 8: §4.3 Màn ĐỐI CHIẾU

**Files:**
- Create: `frontend/src/screens/CompareScreen.tsx`, `frontend/src/screens/CompareScreen.test.tsx`
- Modify: `frontend/src/shell/App.tsx`

**Interfaces:**
- Consumes: `endpoints.listTranslations(transcriptId)`, `endpoints.getTranscript(id)`
- Produces: hai cột (nguồn / bản dịch) + cột CPS; **segmented control** chọn bản dịch; **ghim bản B**; đánh dấu dòng vượt ngưỡng đọc

- [ ] **Step 1: Test ĐỎ**

```tsx
it("danh dau dong vuot nguong doc bang COT CPS, khong phai bang mau don thuan", async () => {
  // Tieu chi §12.4: phat hien duoc dong dich vuot nguong DOC ma khong phai tu dem.
  // Nguong den TU BACKEND (spec §6) — client khong tu tinh lai.
  render(<CompareScreen transcript={t} translations={[trVuotNguong]} />);
  const row = await screen.findByTestId("row-3");
  expect(row).toHaveAttribute("data-over-cps", "true");
  expect(within(row).getByText(/CPS/)).toBeInTheDocument();
});

it("chon ban dich khac thi cot phai doi theo, cot trai khong doi", async () => {
  render(<CompareScreen transcript={t} translations={[trA, trB]} />);
  await userEvent.click(screen.getByRole("radio", { name: /bản dịch 2/i }));
  expect(screen.getByTestId("col-right")).toHaveTextContent(trB.segments[0].text);
  expect(screen.getByTestId("col-left")).toHaveTextContent(t.segments[0].text);
});

it("ghim ban B thi hien them cot so sanh", async () => {
  render(<CompareScreen transcript={t} translations={[trA, trB]} />);
  await userEvent.click(screen.getByRole("button", { name: /ghim bản B/i }));
  expect(await screen.findByTestId("col-pinned")).toHaveTextContent(trA.segments[0].text);
});
```

- [ ] **Step 2: Chạy để thấy ĐỎ**, rồi viết `CompareScreen.tsx`.

**Quy tắc không được vi phạm:** CPS và `stale` **đọc từ dữ liệu backend trả** (`qa_issues` mang tiền tố `cps:`, và `stale` đã tính sẵn ở `GET /api/translations`). Client **không** tính lại CPS. Nếu backend chưa trả đủ để hiển thị một cột, đó là **lỗi của backend** cần báo lại — không phải lý do để tính lại ở client (spec §2).

- [ ] **Step 3: XANH + mutation** — đổi `data-over-cps` thành luôn `"false"` ⇒ test 1 đỏ. Phục hồi.

- [ ] **Step 4: Commit** — `feat(fe): man Doi chieu voi cot CPS tu backend + ghim ban B`.

---

### Task 9: §4.4 Tab THUẬT NGỮ — số ảnh hưởng TRƯỚC khi lưu

**Files:**
- Create: `frontend/src/screens/GlossaryScreen.tsx`, `frontend/src/screens/GlossaryScreen.test.tsx`
- Modify: `frontend/src/shell/App.tsx`
- Modify (**backend, xem Step 0**): `backend/app/api/routes_glossary.py`, `backend/tests/test_api_glossary.py`

**Interfaces:**
- Consumes: `endpoints.listTerms`, `createTerm`, `patchTerm`, **`affectedPreview`**
- Produces: bảng thuật ngữ + form; trước khi lưu hiện **số bản dịch bị ảnh hưởng**; và nói rõ đổi thuật ngữ **chưa duyệt** thì không ảnh hưởng gì

- [ ] **Step 0: BACKEND — thêm MỘT endpoint chỉ-đọc, vì §12.3 đòi thứ API chưa phục vụ được**

Spec UI §12.3: *"Sửa một thuật ngữ → thấy ngay bao nhiêu bản dịch bị ảnh hưởng **trước khi bấm lưu**"*. Backend hiện chỉ trả `affected` **sau** khi ghi (`POST`/`PATCH`). Tính lại ở client **bị cấm** bởi spec frontend §2 — nó tạo nguồn sự thật thứ hai cho đúng đại lượng Giai đoạn 2 vừa phải đi vá.

Thêm vào `routes_glossary.py`:

```python
@router.get("/affected")
def affected_preview(lang: str, term: str, translation: str, approved: bool = False,
                     repos=Depends(get_repos)):
    """Chỉ-đọc: con số mà `POST`/`PATCH` SẼ trả. Gọi LẠI chính `affected_segments`.

    Cố ý không tính lại: hai chỗ tính cùng một đại lượng là đúng lớp lỗi mà
    Giai đoạn 2 phải đi vá hai lần.
    """
    old = [t for t in repos.list_terms(lang=lang) if t.term != term]
    neue = [t for t in repos.list_terms(lang=lang) if t.term != term]
    neue.append(Term(id=None, lang=lang, term=term, translation=translation,
                     approved=approved))
    out = []
    for t in repos.list_transcripts():
        if t.lang != lang:
            continue
        if affected_segments(t.segments, old, neue):
            out.append(t.id)
    return {"affected": out}
```

Đường dẫn phải đứng **trước** `/{term_id}` nếu không FastAPI sẽ khớp `affected` thành một `term_id` — kiểm bằng cách gọi thật.

Test đỏ trước: tạo một term chưa có trong DB, gọi `GET /api/glossary/affected?lang=zh&term=mới&translation=x` ⇒ phải trả `{"affected": []}`; rồi gieo một transcript chứa `mới` ⇒ phải trả đúng id đó. Chạy `python -B -m pytest tests/test_api_glossary.py` từ `backend/`.

- [ ] **Step 1: Test ĐỎ**

```tsx
it("hien so ban dich bi anh huong TRUOC khi nguoi dung bam luu", async () => {
  // Tieu chi §12.3. Backend tra `affected` trong cung response POST/PATCH
  // (route glossary, Task 14 cua GD2) — nen client KHONG duoc tu doan.
  render(<GlossaryScreen />);
  await userEvent.type(await screen.findByLabelText(/thuật ngữ/i), "rồng");
  await userEvent.type(screen.getByLabelText(/bản dịch/i), "dragon");
  expect(await screen.findByTestId("affected-preview")).toHaveTextContent(/\d+/);
});

it("noi ro sua thuat ngu CHUA DUYET thi khong anh huong gi", async () => {
  // Luat that cua backend (ruling T4/F2): ban nhap khong duoc ap, nen doi no
  // khong lam ban dich nao phai xem lai. UI phai noi dieu do, khong de nguoi
  // dung tu doan roi tuong tinh nang hong.
  render(<GlossaryScreen />);
  await userEvent.click(await screen.findByLabelText(/đã duyệt/i)); // tat di
  expect(await screen.findByTestId("affected-preview")).toHaveTextContent(/không ảnh hưởng/i);
});
```

- [ ] **Step 2: Chạy ĐỎ** ⇒ viết `GlossaryScreen.tsx`.

**Ràng buộc:** `POST /api/glossary` **đã** tự tăng `glossary_version` bên trong `upsert_term` (Giai đoạn 2 ruling T6). Client **không** gọi thêm gì để "tăng version"; muốn biết version thì đọc `GET /api/glossary/version`.

- [ ] **Step 3: XANH + mutation** — bỏ nhánh "chưa duyệt" ⇒ test 2 đỏ. Phục hồi.

- [ ] **Step 4: Commit** — `feat(fe): tab Thuat ngu voi so ban dich bi anh huong truoc khi luu`.

---

### Task 10: §4.8 Trạng thái Ollama TẮT — hạng nhất, không phải toast

**Bối cảnh đã đo:** máy này hiện **Ollama đang tắt**, nên đây không phải tình huống giả định — nó là trạng thái thật khi bạn mở app lần đầu. Dùng luôn nó để kiểm.

> 🔴 **ĐÍNH CHÍNH CỦA TASK 2 — câu "Ollama đang tắt" ở trên chỉ đúng MỘT NỬA, và màn này sẽ KHÔNG HIỆN nếu bạn làm theo trực giác.**
> Task 2 đo `/api/status` trên chính máy này: nó trả **`ollama: "unknown"`**, KHÔNG phải `"down"`. Vì cổng 11434 **timeout** (~300 ms, 3/3 lần) chứ không **refused** ⇒ `urlopen` bọc thành `URLError(reason=TimeoutError)` ⇒ `probe_ollama` rơi vào nhánh "chưa đo được" ⇒ `unknown`.
> ⇒ **Màn §4.8 phải hiện với CẢ `down` LẪN `unknown`.** Nếu bạn chỉ khoá theo `ollama === "down"` thì màn này **không bao giờ hiện trên máy này**, và mọi ảnh chụp nghiệm thu sẽ là màn trống — mà bạn sẽ tưởng component hỏng.
> Đừng "sửa" bằng cách đổi `probe_ollama` cho nó trả `down`: spec nói `unknown` là một giá trị **THẬT** ("chưa đo được"), biến nó thành `down` là **bịa ra một sự thật chưa đo** (docstring `probe_ollama` trong `backend/app/api/routes_registry.py` giải thích đúng điều này).
> Ví dụ render ở Step dưới dùng `ollama: "down"` — giá trị đó vẫn hợp lệ để kiểm, nhưng **phải có thêm một ca `unknown`**.

**Files:**
- Create: `frontend/src/screens/OllamaDown.tsx`, `frontend/src/screens/OllamaDown.test.tsx`
- Modify: `frontend/src/shell/Header.tsx`, `frontend/src/shell/App.tsx`

**Interfaces:**
- Consumes: `endpoints.status()`, `endpoints.registry()`
- Produces: dải trạng thái ở header (Ollama lên/xuống, VRAM, giai đoạn đang chạy) + khi Ollama xuống thì **panel nói rõ cái gì còn chạy được, cái gì không, và cách sửa**; dropdown engine chỉ liệt kê engine `capabilities.available === true`

- [ ] **Step 1: Test ĐỎ**

```tsx
it("Ollama xuong thi noi RO cai gi con chay duoc", async () => {
  // Tieu chi §12.6. Khong duoc chi hien "Ollama: down" — nguoi dung phai biet
  // engine in-process (OPUS-MT) VAN dich duoc, con Qwen thi khong.
  render(<OllamaDown status={{ ollama: "down", vram: null }} specs={specsVoiOpusAvailable()} />);
  expect(screen.getByText(/OPUS-MT/)).toBeInTheDocument();
  expect(screen.getByText(/còn dùng được/i)).toBeInTheDocument();
  expect(screen.getByText(/cách sửa|ollama serve/i)).toBeInTheDocument();
});

it("dropdown chi liet ke engine available", () => {
  render(<EngineSelect specs={[specAvailable("opus-mt"), specUnavailable("qwen2.5-3b")]} />);
  expect(screen.getByRole("option", { name: /OPUS-MT/ })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /Qwen/ })).toBeNull();
});
```

- [ ] **Step 2: Chạy ĐỎ** ⇒ viết `OllamaDown.tsx` + `EngineSelect`.

**Ràng buộc:** `available` **đọc thẳng** từ `/api/registry`; client **không** tự suy từ `runtime`/`model_ref`. Bản vá Task 12 của Giai đoạn 2 đã làm `available` nghĩa là "phục vụ được job ngay bây giờ" — suy lại ở client là tạo nguồn sự thật thứ hai.

- [ ] **Step 3: XANH + mutation** — cho `EngineSelect` bỏ lọc ⇒ test 2 đỏ. Phục hồi.

- [ ] **Step 4: Tự kiểm trên máy thật** — Ollama đang tắt, nên mở app và chụp lại rằng panel hiện đúng. Rồi **bật** Ollama (`ollama serve` nền), tải lại, chụp lại trạng thái ngược. Dán cả hai ảnh vào `.superpowers/` và nói rõ trong báo cáo.

- [ ] **Step 5: Commit** — `feat(fe): trang thai Ollama tat la hang nhat + dropdown loc theo available`.

---

### Task 11: Bàn phím — yêu cầu, không phải điểm cộng

Spec UI §5.1 và tiêu chí §12.5: **không chạm chuột vẫn làm được toàn bộ phần biên tập**. Đây là lý do spec §11.4 ghi bảng phím tắt là **yêu cầu**.

**Files:**
- Create: `frontend/src/keys/shortcuts.ts`, `frontend/src/keys/shortcuts.test.ts`, `frontend/src/keys/useShortcuts.ts`

**Interfaces:**
- Consumes: `parseTimecode`, `formatTimecode` (Task 6)
- Produces: `resolveKey(event, mode) -> Action | null` (thuần, test được không cần DOM) · `useShortcuts(dispatch)` gắn listener ở tầng document

- [ ] **Step 1: Test ĐỎ**

```ts
// frontend/src/keys/shortcuts.test.ts
import { describe, expect, it } from "vitest";
import { resolveKey } from "./shortcuts";

const k = (key: string, o: Partial<KeyboardEvent> = {}) =>
  ({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...o }) as KeyboardEvent;

describe("bang phim tat", () => {
  it("Space phat/dung khi khong o trong o nhap", () => {
    expect(resolveKey(k(" "), "edit", false)).toEqual({ type: "togglePlay" });
  });

  it("KHONG cuop phim khi nguoi dung dang go trong o nhap", () => {
    // Neu khong co phep kiem nay thi go dau cach trong o sua se lam dung audio —
    // loi kho chiu nhat cua moi app co ban phim tat.
    expect(resolveKey(k(" "), "edit", true)).toBeNull();
  });

  it("[ va ] nudge moc thoi gian", () => {
    expect(resolveKey(k("["), "edit", false)).toEqual({ type: "nudge", edge: "start", by: -1 });
    expect(resolveKey(k("]"), "edit", false)).toEqual({ type: "nudge", edge: "end", by: 1 });
  });

  it("1/2/3 doi mode", () => {
    expect(resolveKey(k("2"), "edit", false)).toEqual({ type: "setMode", mode: "compare" });
    expect(resolveKey(k("3"), "edit", false)).toEqual({ type: "setMode", mode: "glossary" });
  });

  it("phim khong co trong bang thi tra null, khong nem", () => {
    expect(resolveKey(k("q"), "edit", false)).toBeNull();
  });
});
```

- [ ] **Step 2: Chạy ĐỎ** ⇒ viết `shortcuts.ts` (bảng dữ liệu + một hàm tra, không `switch` dài).

- [ ] **Step 3: `useShortcuts.ts`** — gắn `keydown` ở `document`, bỏ qua khi `document.activeElement` là `input`/`textarea`/`[contenteditable]` (đây là **phép kiểm thật**, và test ở Step 1 ghim nó bằng tham số `inField`), và **dọn listener** trong cleanup — rò listener là loại lỗi chỉ hiện sau vài lần đổi mode.

- [ ] **Step 4: XANH + mutation** — bỏ nhánh `inField` ⇒ test 2 đỏ. Phục hồi.

- [ ] **Step 5: Kiểm bằng TAY trên trình duyệt** rằng đi được trọn: chọn tệp → chuyển đoạn → sửa dòng → nudge mốc → duyệt → đối chiếu → xuất, **không chạm chuột**. Ghi lại danh sách phím đã bấm. Nếu một bước buộc phải dùng chuột thì đó là **lỗi của plan này**, báo lại chứ không bỏ qua.

- [ ] **Step 6: Commit** — `feat(fe): bang phim tat cho toan bo luong bien tap`.

---

### Task 12: Playwright trên backend THẬT — dữ liệu gieo vào DB, engine thật

**⚠️ Task này cần người dùng duyệt trước khi chạy:** `npx playwright install` tải trình duyệt **ra ngoài workspace** và sẽ **bị sandbox từ chối**. Dừng và hỏi; **đừng** tự vượt sandbox.

**Vì sao gieo DB thay vì dựng engine giả:** backend **không có** cơ chế plugin stub — fake engine của nó được tiêm **trong tiến trình pytest**, còn Playwright điều khiển một **tiến trình server thật**. Dựng thêm endpoint/registry giả chỉ để test là thêm bộ phận chạy trong sản phẩm mà chỉ test dùng (spec §6).

**Files:**
- Create: `frontend/playwright.config.ts`, `frontend/e2e/fixtures.ts`, `frontend/e2e/seed.py`, `frontend/e2e/edit.spec.ts`, `frontend/e2e/compare.spec.ts`, `frontend/e2e/glossary.spec.ts`, `frontend/e2e/ollama-down.spec.ts`

**Interfaces:**
- Consumes: toàn bộ app đã dựng
- Produces: `npm run e2e` khởi động backend + frontend, gieo dữ liệu, chạy bốn spec, tắt cả hai

- [ ] **Step 1: `e2e/seed.py` — gieo thẳng DB, không cần model**

Dùng chính `SqliteRepos` của backend (đừng viết SQL tay: `add_transcript`, `add_translation`, `upsert_term`, `add_job` đã có, và chúng giữ được ràng buộc schema):

```python
"""Gieo mot DB day du de UI doc. KHONG can model, KHONG can GPU.

Vi sao: Playwright dieu khien tien trinh server THAT, nen khong tiem duoc engine
gia nhu pytest. Phan lon man hinh chi DOC, nen gieo du lieu la du — va no chay
nhanh, tat dinh, khong phu thuoc mang.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.models import Segment

def seed(db_path: str, media_dir: str) -> None:
    """`media_dir` phai la thu muc THAT trong workspace (ngoai repo).

    ⚠️ Phai ghi mot tep media THAT vao do: `Transport` lay `src` tu
    `GET /api/media/{source_id}`, va mot `media_path` khong ton tai lam player
    404 ngay o spec Bien tap — hong vi ly do chang lien quan gi toi UI.
    `soundfile` da co trong venv backend nen ghi wav vai giay la du.
    """
    import soundfile as sf, numpy as np, pathlib
    media = pathlib.Path(media_dir) / "seed.wav"
    media.parent.mkdir(parents=True, exist_ok=True)
    sf.write(media, np.zeros(6 * 16000, dtype="float32"), 16000)

    repos = SqliteRepos(db_path, clock=SystemClock())
    repos.init_schema()
    sid = repos.add_source(kind="file", origin="seed.wav",
                           media_path=str(media), lang="zh", duration=6.0)
    segs = [Segment(i=i, start=float(i), end=float(i) + 1, text=f"câu {i}",
                    suspect=(i == 3), qa=["nhạc nền"] if i == 3 else []) for i in range(1, 6)]
    tid = repos.add_transcript(source_id=sid, engine="fw-small", lang="zh", segments=segs)
    repos.add_translation(transcript_id=tid, transcript_version=1, engine="opus-mt",
                          target_lang="vi", prompt_version="opus-p1", status="done",
                          segments=[Segment(i=i, start=float(i), end=float(i) + 1,
                                            text="x" * (40 if i == 3 else 5)) for i in range(1, 6)])
    repos.upsert_term(lang="zh", term="câu 1", translation="cau 1", note=None, approved=True)
    print(f"seeded source={sid} transcript={tid}")
```

- [ ] **Step 2: `fixtures.ts` — backend + frontend do test tự dựng**

`webServer` của Playwright cho frontend; backend thì khởi bằng `spawn` với `PHUDE_DB`/`PHUDE_DATA` trỏ vào **thư mục tạm trong workspace, ngoài repo** (`$env:TEMP` bị từ chối), gọi `seed.py` trước, và **tắt trong teardown**. Cổng 8620 và 11434 hiện đều tắt — test phải chịu được cả hai trạng thái.

- [ ] **Step 3: Bốn spec, mỗi spec một tiêu chí ở spec §8**

```ts
// e2e/glossary.spec.ts
test("doi mot thuat ngu thi thay SO BAN DICH BI ANH HUONG truoc khi luu", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("radio", { name: /thuật ngữ/i }).click();
  await page.getByLabel(/thuật ngữ/i).fill("câu 1");
  await page.getByLabel(/bản dịch/i).fill("cau mot");
  await expect(page.getByTestId("affected-preview")).toHaveText(/1/);   // tieu chi §12.3
});
```

`ollama-down.spec.ts` chạy khi Ollama **tắt** (trạng thái hiện tại của máy) và khẳng định panel nói rõ cái gì còn chạy được (§12.6). `edit.spec.ts` phủ sửa dòng + đoạn `suspect` có nhãn lý do. `compare.spec.ts` phủ segmented control + cột CPS.

- [ ] **Step 4: Chạy và ghi số**

```bash
cd frontend && npm run e2e
```
Kỳ vọng: bốn spec xanh, và dán **dòng tổng kết nguyên văn** vào báo cáo. Rồi mutation: đổi `data-over-cps` ở `CompareScreen` thành luôn `"false"` ⇒ spec Đối chiếu phải đỏ.

- [ ] **Step 5: Commit** — `test(fe): bon spec Playwright tren backend that voi du lieu gieo`.

---

### Task 13: Tài liệu + thu hoạch nợ `ponytail:`

**Files:**
- Modify: `README.md`
- Create: `.superpowers/sdd/<plan>/ponytail-debt.md` (ngoài repo)

- [ ] **Step 1: Gom mọi dấu `ponytail:` trong `frontend/`** bằng `grep -rn "ponytail:" frontend/src` và chép vào một bảng: **tệp · trần · đường nâng cấp**. Dấu nào thiếu trần thì **sửa ngay** — một dấu không nêu trần là nợ không đòi được.
- [ ] **Step 2: README** — mục "Chạy frontend": hai lệnh, hai cổng, và **cách chạy contract test** (phải có backend đang chạy) cùng `npm run e2e`.
- [ ] **Step 3: Ghi vào README phần CHƯA làm của giai đoạn này** (bốn màn hình đã làm; eval §4.6/§4.7, Chimera §4.5, layout điện thoại, đổi theme **chưa làm**), và **nợ Giai đoạn 2 vẫn mở** (route export ghi tệp trên `GET`; `DEFAULT_MAX_CHARS` chưa đo; chất lượng dịch chưa đánh giá).
- [ ] **Step 4: Commit** — `docs(fe): cach chay frontend + gom no ponytail`.

---

## Spec coverage — đối chiếu từng mục của spec với task

| Mục spec | Task |
|---|---|
| §2 stack, cổng 3100, proxy, danh sách CỐ Ý không dùng | **T1** (cấu hình), và mọi task đều bị ràng buộc bởi nó |
| §3 không router + `mode` + một SSE + reducer + không optimistic | **T3** (SSE), **T4** (reducer) |
| §3 type viết tay + contract test | **T2** |
| §4.1 Biên tập (+ rỗng) | **T6** |
| §4.3 Đối chiếu | **T8** |
| §4.4 Thuật ngữ + số ảnh hưởng | **T9** |
| §4.8 Lỗi Ollama hạng nhất + dropdown theo `available` | **T10** |
| §4 Transport/player `Range` + ba nút xuất | **T7** |
| §4 bàn phím toàn luồng | **T11** |
| §5 tokens, font self-host, MỘT lớp grain | **T1** |
| §6 `node --test` + Playwright trên backend thật + luật dự án | **T2**, **T12** |
| §7 dấu `ponytail:` nêu trần + vòng thu hoạch nợ | **T5**, **T13** |
| §8 chín tiêu chí nghiệm thu | **T6/T7/T8/T9/T10** (1–5), **T12** (1, 3, 4, 6), **T2** (7), **T5** (8), **T13** (9) |

## Tự soát (writing-plans)

1. **Placeholder:** không có `TBD`/`TODO`. Chỗ tôi **cố ý** để người làm tự chọn là giá trị màu/chữ nào spec UI không ghi số — và plan nói rõ **phải chọn rồi ghi vào `tokens.css`**, không được để trống.
2. **Mâu thuẫn nội bộ:** không. `available` chỉ đọc từ backend (T10) và T8 cũng nói CPS chỉ đọc từ backend — cùng một luật, hai chỗ.
3. **Nhất quán kiểu:** `Segment`/`Job`/`Translation` định nghĩa **một lần** ở `src/api/types.ts` (T2) và mọi task sau tiêu thụ từ đó; `formatTimecode`/`parseTimecode` chỉ ở `src/lib/timecode.ts` (T6); `visibleRange`/`withPinned` chỉ ở `src/lib/window.ts` (T5).
4. **Phạm vi:** 13 task, mỗi task một deliverable kiểm được độc lập. Không task nào phụ thuộc task **sau** nó.
5. **Rủi ro đã biết:** `npx playwright install` cần duyệt (T12); `tokens.css` phụ thuộc việc đọc spec UI §2 (T1 Step 3); giá trị CPS/`available` đến từ backend nên **backend phải chạy** cho contract test và e2e — plan nói rõ ở T2 Step 3 và T12 Step 2.

## Những gì plan này KHÔNG làm (hoãn có chủ ý)

§4.5 Chimera · §4.6 bảng eval · §4.7 chấm tay 20 câu · layout điện thoại (§10.4) · sáng/tối và tuỳ biến bảng màu (§10.1–2) · kéo-thả sắp xếp cột (§10.6).



