# Giai đoạn Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng bàn làm việc chạy trong trình duyệt cho bốn màn hình backend đã phục vụ được (Biên tập, Đối chiếu, Thuật ngữ, lỗi Ollama) + khung ba vùng + thanh transport, đủ để làm trọn luồng biên tập bằng bàn phím.

**Architecture:** SPA React 19 thuần client, **không router** — một shell với `mode ∈ {edit, compare, glossary}`. Trạng thái server nằm ở một tầng `fetch` mỏng cộng **đúng một** subscription SSE tới `/api/jobs/stream`; trạng thái client nằm trong một reducer. Không ghi kiểu đoán trước cho bản dịch.

**Tech Stack:** React 19 · TypeScript · **Rollup** + `dev-server.mjs` (Vite **bị loại** — xem ERRATA) · **`node --test --test-isolation=none`** + loader `@swc/core` trong tiến trình (Vitest **bị loại** — nó cần Vite/esbuild, mà esbuild **spawn**; **Testing Library thì DÙNG ĐƯỢC** — ERRATA #5 mục 2) · CSS thuần + custom property · font self-host woff2.

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
- **`npx playwright install` là VÔ NGHĨA ở đây — đừng thử lại, đừng xin duyệt.** Không chỉ bị từ chối khi tải:
  **Chromium không thể khởi động** (`FATAL:mojo…platform_channel.cc:187 … Access is denied (0x5)`), bản tải về **và**
  Edge/Chrome có sẵn đều vậy (ERRATA #5 mục 3). Cần thêm gói npm thì dùng công thức ERRATA #5 mục 1 —
  việc đó ghi trong workspace nên **không cần duyệt**.

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
| Testing Library | ⚠️ **ĐÃ LẬT Ở ERRATA #5 — DÙNG ĐƯỢC.** Kết luận cũ (*"đều không có và `npm i` bị chặn"*) **SAI**: chỉ cần `--cache` trong workspace. `jsdom` + `@testing-library/react` **cài được VÀ chạy thật** dưới `node --test --test-isolation=none` (đã đo click thật `bam 0 → bam 1`, EXITCODE=0). ⇒ Dùng cho **TƯƠNG TÁC** ở T5–T11; `react-dom/server.renderToStaticMarkup` vẫn tốt cho render thuần. **Chi phí:** jsdom cộng ~12 s mỗi tiến trình test |
| `npm test -- contract` | `npm test` (đã đổi trong `package.json`) — nếu gọi tay thì **`node --import ./test/swc-loader.mjs --test --test-isolation=none <tệp>`**. **`--test-isolation=none` là BẮT BUỘC**: thiếu nó runner spawn con và chết `EPERM` trên máy này |
| `import { describe, expect, it } from "vitest"` | `import { describe, it } from "node:test"` + `import assert from "node:assert/strict"` — `expect(x).toBe(y)` → `assert.equal(x, y)`, `toBeInTheDocument()` → `assert.ok(el)` |
| `frontend/package-lock.json` | **ĐÃ CŨ** (mô tả cây Vite cũ) — nhưng nay **CẬP NHẬT ĐƯỢC TẠI CHỖ** bằng công thức ERRATA #5, nên vế *"phải làm ở môi trường bình thường"* **không còn đúng**. Implementer **vẫn KHÔNG** được sửa tay tệp này: chỉ `npm` được ghi nó. `npm ci` (`G-2`) chỉ đúng **sau khi** lockfile được `npm install` lại |
| `npm i` bất kỳ | ⚠️ **ĐÃ SỬA Ở ERRATA #5.** Chết `EPERM` vì **cache nằm NGOÀI workspace** (`open '…\AppData\Local\npm-cache\_cacache\tmp\***'`), **KHÔNG** phải named pipe. Cách đúng: `npm i [-D] <gói> --cache C:\Users\Admin\Desktop\ngn\deepseek\.npm-cache --ignore-scripts` ⇒ **đã đo chạy được** (`added 56 packages in 5s`, EXITCODE=0). Sau MỖI lần thêm gói: chạy lại `npm test` **ngay** — nhưng **đừng so một con số tuyệt đối** (chính dòng này từng ghi `16/14/2` và nó cũ ngay sau Task 3). Điều phải đúng: **đỏ đúng hai bài `EMPTY_DB_MSG`, không có bài đỏ thứ ba, `cancelled 0`** |

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
   ⚠️ **ĐÍNH CHÍNH (re-review Task 2 đo lại — Ghi nhận 10): giá trị này ĐỔI THEO TRẠNG THÁI MÁY, không phải hằng số của máy.** Lần đo thứ hai (Ollama **đang chạy**) cho `/api/status` → **`ollama:"up"`**. Vậy **hai** giá trị khác nhau đã thấy trên **cùng một máy**: `unknown` (Ollama tắt, cổng timeout) và `up` (Ollama chạy).
   ⇒ **Kết luận cho Task 10 vì thế MẠNH HƠN, không yếu đi:** màn §4.8 **phải xử cả ba** `up`/`down`/`unknown`, và **không được giả định** giá trị nào là "trạng thái thật của máy này". Đáng chú ý: `down` (cổng **refused**) **chưa từng** xuất hiện trong cả hai lần đo — nên đừng viết test chỉ với `down`.
5. **`.gitignore` thiếu `*.db-wal` + `*.db-shm`** — đã sửa ở `a56464f`. Lý do: SQLite WAL tạo hai tệp phụ khi DB đang mở, nên **chỉ cần chạy backend thật** (`python run_api.py` — việc **Task 12 bắt buộc** làm) là `git status` hiện `?? data/`, vi phạm luật "status phải rỗng".
6. **`"fail 0"` KHÔNG đồng nghĩa XANH.** Một `before` hook ném lỗi làm `node:test` in **`tests 9 / pass 0 / fail 0`** mà **`EXIT=1`**. Luật cũ ("nếu in `tests 1` thì glob đã mất") vẫn đúng nhưng **chưa đủ** — **luôn đọc EXIT kèm dòng tổng kết**. Không có exit code thì không có kết luận.
7. **Task 9 tiêu thụ `endpoints.affectedPreview` nhưng danh sách Files của Task 9 KHÔNG có `endpoints.ts`.** Nếu Task 2 không tạo thì Task 9 phải sửa một tệp dùng chung (hai người ghi). Task 2 đã tạo sẵn `affectedPreview` + `glossaryVersion` và ghi rõ trong comment rằng route `GET /api/glossary/affected` **ra đời ở Task 9** ⇒ **wrapper đó chưa chạy được cho tới Task 9**; đừng "sửa" nó thành chạy được bằng cách bịa route.
8. **`tsconfig.json` đã phải sửa ở Task 2, và có ĐÁNH ĐỔI phải nói thẳng.** `npm run typecheck` đỏ vì `TS2591` (không có `@types/node`, `npm i` bị chặn), `TS5097` (Node ESM bắt buộc đuôi `.ts` tường minh) và `TS18046`. Cách sửa đã dùng: `"allowImportingTsExtensions": true` + **`"exclude": ["src/**/*.test.ts","src/**/*.test.tsx"]`**.
   ⇒ **Hệ quả bắc cầu: `contract.test.ts` KHÔNG được `tsc` kiểm kiểu** — nợ `N-2` lan từ `frontend/test/` sang `src/`. Và **mọi test `.test.tsx` của T6/T8/T9/T10 cũng sẽ bị loại khỏi `tsc`**. Nghĩa là **"build xanh" KHÔNG bao hàm "test không có lỗi kiểu"** — test vẫn chạy nên lỗi kiểu sẽ lộ ở lúc chạy, nhưng đừng đọc "build xanh" là "type sạch cho cả test".
   **Và đây là một ĐÁNH ĐỔI, không phải "hết đường"** (review Task 2 bổ sung): 9 lỗi kia chỉ đến từ **MỘT** nguyên nhân — `@types/node` vắng (TS2591 cho `node:test`/`node:assert/strict`, và TS18046 là hệ quả của `assert.ok` mất assertion-signature). Một **khai báo ambient viết tay (~15 dòng)** cho `node:test`+`node:assert/strict` là đủ để đưa tệp test trở lại tầm `tsc`; giá của nó là một stub **có thể trôi** khỏi API thật. Task 2 **từ chối** stub đó vì nó **bịa API** — quyết định hợp lý — nhưng phải ghi là **quyết định có đánh đổi**, và nếu về sau ai muốn "build xanh bao hàm type sạch cho test" thì đây là đường.
9. **Bài `translations[]` của contract test hiện RỖNG VỀ DỮ LIỆU** trên DB repo (`0 hàng`), nên nó chỉ được chứng minh không-rỗng nhờ một DB scratch gieo riêng. Muốn ghim thật thì **Task 12 phải gieo dữ liệu vào DB thật** trước khi chạy e2e — đó là lý do Task 12 tồn tại.

## ⚠️ ERRATA #3 — hệ quả của vòng sửa Task 2 (áp cho Tasks 3–12)

Vòng sửa Task 2 (`166c2a9` + `f5a625b`) đóng 2 Critical + I-1, và **đổi hành vi** ở hai chỗ. Ba điều dưới đây là hệ quả, phải đọc trước khi làm Task 3.

1. **`contract.test.ts` nay TỰ KHỞI ĐỘNG backend** (`stdio:"ignore"` + poll 250 ms × 30 s; chỉ spawn khi `/api/status` chưa trả lời; `after` chỉ tắt **pid của chính nó** và **chứng minh** cổng thôi trả lời).
   ⇒ **Task 2 Step 3 (khoảng dòng 496) nay SAI**: nó viết *"Kỳ vọng: đỏ vì backend chưa chạy (`backend 8620 khong chay`)"*. Với hành vi mới, backend tắt thì test **tự khởi động rồi XANH** — nên đọc câu đó là "kỳ vọng đỏ" sẽ tưởng một hồi quy. Đây là **hành vi đúng theo `Global Constraints` dòng 17** (*"Backend **không** chạy sẵn: mọi test đầu-cuối phải **tự khởi động** nó và **tự tắt**"*).
   ⚠️ **Và một chỗ brief của người điều phối trích SAI:** nó nói *"bảng preflight ghi rõ cả hai phải tự khởi động backend"* — **không có bảng preflight nào trong plan** (`grep -i preflight` trên plan = **0 hit**). Bảng preflight nằm ở **ledger**, không ở plan. Chỗ duy nhất trong plan đỡ cho ràng buộc này là `Global Constraints` dòng 17. Đừng trích một nguồn không tồn tại.
2. **`npm test` trên DB repo (0 hàng) nay là `EXIT=1` với 2 bài ĐỎ CHỦ Ý.** Đó là C-2: contract test **phải sập ồn ào** khi không có dữ liệu để đo, thay vì xanh-vì-rỗng (spec §2). Hai guard: **≥1 transcript có segment** và **≥1 hàng `translations`**.
   ⇒ **Cổng "suite xanh" cho Tasks 3–11 phải đọc lại:** trên máy này, `npm test` đỏ **2 bài** là **đúng** cho tới khi có dữ liệu. Đừng "sửa" nó bằng cách nới guard, và đừng coi 2 đỏ đó là hồi quy của task mình. **Đọc EXIT kèm danh sách bài đỏ** — 2 bài đúng tên là trạng thái hợp lệ; bài thứ ba là hồi quy thật.
3. **Task 12 PHẢI gieo ĐỦ HAI THỨ vào `data/app.db` thật**: một transcript **có segment**, **và ≥1 hàng `translations`**. Thiếu một trong hai thì guard của Task 2 vẫn đỏ sau Task 12, và e2e sẽ đỏ vì lý do không liên quan tới thứ nó kiểm. Đây là lý do Task 12 tồn tại (ngoài Playwright) — xem thêm ERRATA #2 mục 9.

**Đính chính nhỏ về `Segment`** (brief của người điều phối đếm sai): `Segment` có **5 khoá LUÔN có** (`i`, `start`, `end`, `text`, **`suspect`**) + **8 khoá TUỲ CHỌN** (`words`, `emotion`, `events`, `speaker`, `avg_logprob`, `no_speech_prob`, `t`, `qa`). Brief ghi "13 khoá" nhưng chỉ liệt kê 11 và **bỏ sót `avg_logprob` + `no_speech_prob`**. Và nhóm "chỉ đối chiếu mã nguồn" là **8** `interface` + **1** `type` = **9 KIỂU** (không phải 9 interface, và không phải 5).

## ⚠️ ERRATA #4 — hệ quả của vòng sửa #3 Task 2 (áp cho MỌI task còn lại)

**Vòng sửa #3** (`c65090b` + `3a7d84f`, chỉ comment của `frontend/src/api/types.ts`). Bốn điều phải nhớ:

1. **Một con số viết trong comment là một con số SẼ TRÔI, và brief của người điều phối có thể là nguồn của con số sai.**
   Re-review `c8180f1` bắt `I1`: header `types.ts` khai `9 type`, đếm thật **10**. Gốc **không phải** implementer —
   **brief của người điều phối ra lệnh viết con số đó**. Và trong lúc sửa, implementer **tự tạo lại đúng loại lỗi đó**
   (`c65090b` xếp `OllamaState` vào nhóm "type không có bài kiểm" trong khi nó có **2** hit) rồi tự bắt ở `3a7d84f`.
   ⇒ **Luật mới, áp cho mọi header/comment của giai đoạn này: mỗi con số phải đi kèm LỆNH sinh ra nó.**
   Con số không có lệnh sinh ra nó là con số sẽ trôi lần nữa. Và **đừng chép số từ brief**: brief cũng sai.
2. **BẪY CÚ PHÁP: viết glob chứa `**/` BÊN TRONG khối `/** … */` sẽ ĐÓNG COMMENT SỚM.**
   `src/**/*.test.ts` chứa chuỗi `*/` ⇒ comment kết thúc giữa dòng, phần còn lại thành **mã**, `tsc` đỏ `TS1127`/parse error.
   Đo được ở `3a7d84f`. **Cách viết an toàn:** `Get-ChildItem src -Recurse -Filter *.test.ts` (không có `*/`),
   hoặc chèn khoảng trắng `* /`. **Áp cho mọi doc-comment của Tasks 3–13.**
   Cùng họ: ký tự Unicode ngoài ASCII (`⊂` U+2282) làm `tsc` đỏ `TS1127` — viết bằng chữ.
   Và **đừng ghi số dòng cứng** (`(dòng 326)`) vào comment: nó lệch ngay khi tệp đổi (đã đo: 326 → 349).
   ⚠️ **ĐỪNG CHÉP mẫu `src` + `**` + `/*.test.ts` ở trên vào bất kỳ doc-comment nào** — vòng kiểm chứng bắt được
   rằng chính ERRATA này và báo cáo của implementer **đã chép lại mẫu đó**, nên ai copy nguyên văn sẽ **tái hiện
   `TS1127`**. Khi cần nói về mẫu nguy hiểm, hãy **mô tả nó bằng chữ** ("glob hai-sao có chứa dấu sao-rồi-gạch-chéo"),
   và chỉ dán **dạng an toàn**.
3. **Số dòng mà `node --test` báo là số dòng của JS ĐÃ SINH, không phải của `.ts`** — nhưng nó vẫn in dưới nhãn `.ts`.
   **NGUYÊN NHÂN ĐÃ TRUY ĐƯỢC** (vòng kiểm chứng `verify-task-2-fix-round-3`, mạnh hơn giả thuyết ban đầu):
   `test/swc-loader.mjs:26` trả `{format, source, shortCircuit}` — **KHÔNG có `sourceMap`, `out.map = undefined`** —
   và script test **không** bật `--enable-source-maps`. Khớp tuyệt đối: `gen:222` là `it("GET /api/transcripts: …")`,
   `gen:226` là `assert.notEqual(rows.length, 0, EMPTY_DB_MSG);`. Độ lệch **KHÔNG ĐỀU**: đo 10 mẫu, delta **12…34**,
   `all equal? false`.
   ⇒ **Định danh bài đỏ bằng TIÊU ĐỀ, không bằng số dòng runner.** Hai đường nâng cấp nếu ai cần số dòng đúng:
   (a) cho loader trả `sourceMap` (swc có `sourceMaps: true`) **và** chạy node với `--enable-source-maps`;
   (b) chấp nhận và luôn dùng tiêu đề. **Đừng** "sửa" bằng cách tin số dòng.
   ⚠️ **Và một đính chính cho chính ERRATA này:** con số `+25/+66` tôi từng dẫn là **ghép chéo hai bài** (292 là
   assertion của bài #2, không phải của bài #1) — xem `verify-task-2-fix-round-3-report.md`. Ghép đúng trong cùng
   bài: bài #1 `it` +20, assertion +21; bài #2 +22, +22. **Bài học lặp lại lần thứ ba: một con số không kèm lệnh
   sinh ra nó thì tôi sẽ đọc sai nó.**
4. **Một khoảng `A..B` KHÔNG phải "những gì commit B làm".** Brief của người điều phối khai phạm vi
   `4a1e33c..c8180f1` là "2 tệp"; thật ra là **3**, vì chính người điều phối commit `5dd0616` (sửa plan này)
   **nằm giữa hai mốc**. Muốn nói về một commit thì dùng `git show --stat B`.
5. **Ruling về `M1` (reviewer nói docstring `Segment` mâu thuẫn — người điều phối và implementer đều cho là SAI):**
   câu *"chỉ tin `words` khi nó có PHẦN TỬ"* là **quy tắc cho BÊN ĐỌC dữ liệu**, không phải ràng buộc kiểu; nó **khớp**
   với `words?: Word[]` (mảng rỗng nghĩa là "không có mốc thời gian từng từ"). `contract.test.ts` tự ghi điều này
   (*"'có khoá' chỉ suy ra 'không phải undefined', KHÔNG suy ra 'khác rỗng'"*). **Giữ nguyên docstring.**
   Reviewer đã đọc một quy tắc tiêu thụ dữ liệu như một ràng buộc kiểu — **reviewer cũng sai được, và phải phản biện.**
6. **Nợ `N-6` (backend, ngoài phạm vi giai đoạn này):** một hàng `transcripts` có payload hỏng trong cột `segments`
   làm **sập CẢ** `GET /api/transcripts` bằng 500, không chỉ hàng đó (`list_transcripts` gọi `_row_to_transcript`
   cho mọi hàng). Đo được với `words` = chuỗi / số / mảng số. **Một hàng hỏng giết cả danh sách.**
7. **LUẬT MẠNH HƠN MỤC 1 — ĐỪNG VIẾT CON SỐ VÀO COMMENT. HÃY VIẾT LỆNH.**
   Mục 1 nói "mỗi con số phải kèm lệnh sinh ra nó". Task 2 đã chứng minh **như thế vẫn chưa đủ**: khối header
   `types.ts` tốn **BỐN vòng sửa** và có **BỐN lần liên tiếp một con số nói dối** —
   (1) `9 type` (thật 10, **nguồn là brief của người điều phối**); (2) `c65090b` xếp `OllamaState` vào nhóm
   "không có bài kiểm" (thật 2 hit); (3) `3a7d84f` viết "**Ba** nhóm" trong khi có **bốn**; (4) bản nháp vòng #4
   **đếm `JobSlim` hai lần**. **Không lần nào bắt được bằng cách ĐỌC** — cả bốn đều cần một lệnh.
   ⇒ **Quy tắc cho Tasks 3–13: nêu LỆNH (kèm `cwd`), để người đọc tự đếm.** Chỉ khi buộc phải có số thì số đó
   phải do lệnh in ra và **dán ngay cạnh**. Một khối comment liệt kê/đếm là **nghĩa vụ bảo trì không ai canh**.
8. **Lời khai trong TIN NHẮN cũng phải bị đo.** Vòng kiểm chứng #2 bác bỏ một con số **không tái lập được bằng
   bất kỳ bộ lọc nào**: implementer khai "chỉ bỏ comment thì ra **200** dòng", nhưng đo thật là 366 dòng,
   167 dòng comment ⇒ `366 − 167 = 199`; bỏ comment + dòng rỗng ⇒ **170**; giữ dòng rỗng ⇒ 337/367.
   ⇒ **Khi chuyển tiếp một con số từ báo cáo agent sang brief/tài liệu, phải tự đo trước** — người điều phối
   đã lặp lại con số đó mà không đo. **Một con số nằm trong lời khai cũng là một con số có thể nói dối.**

## ⚠️ ERRATA #5 — BA KẾT LUẬN "BẤT KHẢ" CỦA PLAN ĐÃ BỊ BÁC BỎ BẰNG ĐO (đọc trước MỌI task còn lại)

Vòng điều tra bắt đầu từ một câu hỏi hẹp ("Task 12 có chạy được không?") và kết thúc bằng việc **lật ba kết luận**
mà cả giai đoạn đang dựa vào. Mọi phép đo làm ở scratch **ngoài repo**; mỗi dòng dưới đây có errno/syscall/đường dẫn.

### 1. `npm i` **KHÔNG** bị chặn — chỉ cần đặt cache TRONG workspace

Chính ERRATA này (dòng 44) đã ghi *"`npm i` bất kỳ **CÓ THỂ CHẾT `EPERM`** ở `AppData\Local\npm-cache`"* —
**nửa sau của câu đó là manh mối, và chưa ai thử hệ quả của nó.** Đo:

| Lệnh | Kết quả |
|---|---|
| `npm i -D @playwright/test` (cache mặc định) | ❌ `FetchError … EPERM: operation not permitted, open 'C:\Users\Admin\AppData\Local\npm-cache\_cacache\tmp\***'` |
| `npm i -D @playwright/test --cache C:\Users\Admin\Desktop\ngn\deepseek\.npm-cache` | ✅ `added 3 packages in 2s`, **EXITCODE=0** |
| `npm i -D jsdom @testing-library/react --cache <ws>` | ✅ `added 56 packages in 5s`, **EXITCODE=0** |
| `npm i @swc/core` (có postinstall) | ❌ `EXITCODE=-4048` (postinstall **spawn**) |
| `npm i @swc/core --ignore-scripts` | ✅ `added 4 packages`, **EXITCODE=0** — và `transformSync` **chạy đúng** (`SWC_OK`) |

⇒ **Lỗi KHÔNG phải named pipe.** Nó là `open` bị từ chối trên **đường dẫn cache NGOÀI workspace**.
⇒ **Công thức BẮT BUỘC cho mọi lệnh cài trong giai đoạn này:**
`npm i [-D] <gói> --cache C:\Users\Admin\Desktop\ngn\deepseek\.npm-cache --ignore-scripts`
(`--ignore-scripts` để postinstall không spawn — đã đo `@swc/core` **vẫn chạy đúng** sau đó).
Và **sau MỌI lần thêm dependency vào `frontend/`**: chạy lại `npm test` ngay — và **đừng so một con số tuyệt đối**
(con số đó sẽ trôi theo từng task; chính dòng này từng ghi `16/14/2` và nó **cũ ngay** sau Task 3, xem ERRATA #6 mục 3).
Điều phải đúng là: **số bài đỏ vẫn ĐÚNG hai guard `EMPTY_DB_MSG`** và **không có bài đỏ thứ ba**, `cancelled 0`.
Nếu harness chết (hoặc có bài đỏ khác) thì **hoàn tác ngay**.

### 2. jsdom + Testing Library **DÙNG ĐƯỢC** — kết luận cũ ở `Q-1` SAI

`Q-1` dòng 220 chốt: *"`jsdom`, `@testing-library/react`, `@testing-library/dom`, `happy-dom` — đều **không có**,
và **`npm i` bị chặn**"*. Vế thứ hai sai (mục 1) ⇒ **cả kết luận sai**. Không chỉ cài được — nó **chạy THẬT**
dưới `node --test --test-isolation=none`:

```
BEFORE_CLICK bam 0
AFTER_CLICK bam 1
✔ jsdom + RTL: render that va click that (93.361ms)
ℹ tests 1 / pass 1 / fail 0 / cancelled 0      EXITCODE=0
```

⇒ **`Q-1` mục 3 ("Không có DOM ⇒ không jsdom, không Testing Library") BỊ BÁC BỎ.**
⇒ **`Q-1` mục 4** ("test đơn vị KHÔNG mô phỏng được tương tác") **không còn đúng**: click/focus/bàn phím
**mô phỏng được**, chạy **trong tiến trình**, **không spawn**.
⇒ **Dòng 40, dòng 416 và Step 3 của Task 6 (dòng 895) phải đọc theo ERRATA này.**
**Chi phí phải biết:** jsdom làm mỗi tiến trình test chậm thêm **~12 s** (đo `duration_ms 12974`, phần lớn là import jsdom).

### 3. Playwright / trình duyệt thật **BẤT KHẢ** — và ĐÂY mới là named pipe thật

| Bước | Kết quả |
|---|---|
| Cài `@playwright/test` | ✅ (mục 1) |
| `playwright install chromium` | ❌ `Failed to download … caused by **spawn EPERM**`; stack `Object.fork` → `downloadBrowserWithProgressBarOutOfProcess` |
| `chromium.launch({executablePath: msedge.exe})` — Edge **CÓ SẴN** trên máy | ❌ `spawn EPERM`; call log có cờ **`--remote-debugging-pipe`** |
| Tự spawn Edge `stdio:'ignore'` + `--remote-debugging-port=9222` (để `connectOverCDP`, tránh pipe) | ⚠️ spawn **được**, nhưng `cdp_up: false` |
| Bắt stderr của chính Edge | ❌ **`FATAL:mojo\public\cpp\platform_channel.cc:187] Check failed: . : Access is denied. (0x5)`**; exit `2147483651` |

**NGUYÊN NHÂN GỐC: Chromium tự dùng NAMED PIPE cho IPC (Mojo) của chính nó.** Không phải chuyện tải về,
không phải chuyện Playwright, không phải chuyện quyền chạy tệp.
⇒ **Trình duyệt KHÔNG THỂ khởi động trong sandbox này** — bản tải về **hay** Edge/Chrome **có sẵn** đều vậy.
⇒ **Task 12 theo đúng hình dạng plan (`playwright test` trên trình duyệt thật) là BẤT KHẢ.** Xem mục 4.

### 4. Hệ quả bắt buộc — đổi Task 12 và T11, và KHÔNG được hứa thứ không đo được

1. `"e2e": "playwright test"` trong `frontend/package.json` là **script KHÔNG BAO GIỜ chạy được** —
   cùng lớp lỗi với `C-1` (`"test": "vitest run"`). Phải **sửa hoặc bỏ**, và **nói ra**.
2. **Task 12 đổi hình dạng:** thay "trình duyệt thật" bằng **(a)** test **tương tác** bằng jsdom + Testing Library
   chạy trên **backend THẬT**, và **(b)** render bốn màn hình bằng **dữ liệu thật**. Vẫn phải gieo **đủ hai thứ**
   vào `data/app.db` (ERRATA #3 mục 3) — lý do đó **không đổi**.
3. **T11 (bàn phím) nay CHỨNG MINH ĐƯỢC** bằng jsdom (`fireEvent.keyDown`/`userEvent`, khẳng định trên DOM thật).
   Plan cũ nói §12.5 *"chỉ chứng minh được bằng Playwright"* — **nay chứng minh được mà không cần trình duyệt.**
4. **Điều KHÔNG đo được, phải nói thẳng với người dùng:** **chưa ai từng thấy giao diện này chạy trong một
   trình duyệt thật.** jsdom **không phải** trình duyệt: **không layout, không CSS thật, không audio, không `Range`.**
   ⇒ Các tiêu chí nghiệm thu **thuộc hình thức/thị giác** (spec UI §12) và **phát audio** (`Range`, T7)
   vẫn **CHƯA ĐƯỢC CHỨNG MINH** — không được ghi là "đạt".

### 5. Luật mới: mọi câu "bất khả" phải kèm errno + syscall + đường dẫn

Cả ba kết luận sai ở trên cùng một dạng: **một nguyên nhân được SUY RA rồi được truyền đi như sự thật.**
`npm i` bị gán cho named pipe (sai — là cache path); Testing Library bị gán cho "`npm i` bị chặn" (sai theo hệ quả).
⇒ Bất kỳ câu "X bất khả trong môi trường này" viết vào plan/ledger **phải kèm errno + syscall + đường dẫn** của lần đo,
**ngày đo**, và **lệnh tái lập**. Không có ba thứ đó thì đó là **giả thuyết**, không phải **ràng buộc**.

## ⚠️ ERRATA #6 — hệ quả của Task 3 (áp cho Tasks 4–13): **MUTATION PHẢI ĐƯỢC KIỂM, KHÔNG ĐƯỢC TIN**

Task 3 (`2d21cb2`) xong và tự nó bác bỏ **bốn** điều brief của người điều phối khẳng định. Cả bốn đều thuộc
**cùng một dạng: một lời khai chưa được đo đã được viết như sự thật** — đúng thứ ERRATA #4 mục 8 đã cảnh báo.

1. **Con số của brief lại sai:** brief ghi `Job` có **14** khoá; đo thật **`Job keys = 15`** (`JobEvent keys = 6`).
   Đây là lần thứ **năm** trong giai đoạn này một con số do người điều phối đưa ra là sai.
   ⇒ **Implementer PHẢI đo lại mọi con số nhận từ brief, và báo lại nếu lệch.**
2. **MỘT MUTATION CHỈ LÀ BẰNG CHỨNG KHI NÓ (a) BIÊN DỊCH ĐƯỢC, (b) THỰC SỰ ĐỔI HÀNH VI, (c) GIẾT ĐÚNG BÀI.**
   Brief đưa 5 mutation; **hai trong số đó không dùng được nguyên văn**:
   - **`M1` (`while` → `if`) không biên dịch được:** để lại `continue` nằm ngoài vòng lặp ⇒ SWC
     `Syntax Error: A 'continue' statement can only jump to a label of an enclosing iteration statement`
     ⇒ **cả tệp test không nạp được** ⇒ mọi bài "đỏ" vì **lý do sai** — bằng chứng rác. Phải bỏ kèm nhánh `continue`.
   - **`M4` (bỏ `if (event.id === null) return jobs;`) là ĐỘT BIẾN TƯƠNG ĐƯƠNG:** `Map.get(null)` trả `undefined`,
     nên chính nhánh "job chưa có trong map" **đã nuốt `null`** ⇒ mutation này **KHÔNG** giết được bài `id: null`
     (đo: `tests 4 / pass 4 / fail 0`, EXIT=0). Brief khẳng định nó "phải đỏ" là **SAI với chính thiết kế brief quy định**.
     Implementer đã **không nới test cho khớp kỳ vọng sai**; nó thêm `M8` (bỏ **cả hai** nhánh no-op + bịa `Job`)
     và `M8` giết **cả** bài `id: null` **lẫn** bài "job lạ" (`tests 4 / pass 2 / fail 2`, EXIT=1).
3. **`npm test` khi có tệp KHÔNG NẠP ĐƯỢC thì số `tests` TĂNG, không giảm** — Node tính tệp không nạp được là
   **một mục**. Brief khai "khi ĐỎ phải in `tests 16`", thực tế in **17**. ⇒ **ĐỪNG dùng một con số tuyệt đối
   làm dấu hiệu "glob còn nguyên".** Dấu hiệu ĐÚNG: **tệp mới CÓ được thu thập** (nó xuất hiện như một bài),
   và số bài đỏ **đúng bằng hai guard `EMPTY_DB_MSG`**. (Sửa luôn câu ở ERRATA #5 mục 1 nói `16/14/2`.)
4. **Mutation giết NHẦM bài cũng là bằng chứng rác:** `M3` (`buf = ""`) với bài *"ghép lại mảnh bị cắt"* viết
   y như brief lại làm đỏ **bài khác** (`trả NHIỀU sự kiện từ một lần đọc`) — vì dạng cắt trong brief xảy ra
   **trước khi có sự kiện nào hoàn chỉnh**, nên `buf = ""` chưa từng chạy. Cách sửa **đúng**: **thêm ca**
   *"một sự kiện XONG rồi một sự kiện bị cắt"* cho bài đó, **không** nới bài test. Sau đó `M3` giết đúng bài.
5. **BẪY `\r\n` IM LẶNG (đáng nhớ cho mọi mutation từ đây):** hai tệp mới là **LF thuần**; một phép thay thế
   literal có `\r\n` **không khớp và không báo lỗi**, trong khi phép kiểm "tệp có đổi không" **vẫn báo `True`**
   ⇒ hai lần chạy `M4`/`M8` đầu tiên là **bằng chứng rác**. ⇒ **Sau mỗi mutation, phải kiểm "cái đã đổi là cái
   mình ĐỊNH đổi"** (ví dụ `nhánh guard còn trong mutant? False`) — **không** chỉ "tệp có khác không".
6. **`id === null` là GUARD HẸP KIỂU, không phải nhánh hành vi riêng.** Hiệu ứng runtime của nó **trùng** với nhánh
   "job chưa có trong map"; nó vẫn phải giữ vì `Map<number, Job>.get` cần `number`. ⇒ Hệ quả: bài test `id: null`
   và bài "job lạ" **kiểm cùng một đường**. Docstring phải nói đúng điều đó (không được bán nó như hai bất biến
   độc lập), và Tasks 4–13 **không** được lặp lại kiểu "hai bài này độc lập" khi chúng không độc lập.

## ⚠️ ERRATA #7 — hệ quả của vòng sửa #1 Task 3 (`bc0dcae`): **RECIPE PHẢI ĐỎ TRƯỚC KHI SỬA**

Vòng sửa #1 Task 3 dựng được **harness DOM thật** (jsdom + Testing Library + server `node:http` trong tiến trình)
và nhờ đó **hai rủi ro đọc mã trở thành lỗi đo được**. Nó cũng bác **bốn** điểm nữa của brief người điều phối —
nâng tổng số recipe/số liệu sai của người điều phối trong giai đoạn này lên **sáu**. Bốn luật mới:

1. **MỘT RECIPE ĐO LỖI CHỈ LÀ BẰNG CHỨNG KHI NÓ ĐỎ TRÊN MÃ CHƯA SỬA.** Recipe `I-3` của brief —
   *"kết nối thành công rồi server đóng stream"* — **không đo được** lỗi nó tuyên bố đo: nếu **chưa hề có lần đứt nào**
   thì `attempt` đang bằng `0`, nên "delay nhỏ nhất" là **đúng ngay cả khi bug còn nguyên**. Phải **ép backoff leo thang
   TRƯỚC** rồi mới cho kết nối thành công. Implementer làm đúng và ghi lại **trạng thái ĐỎ trước khi sửa**:
   `ℹ tests 4 / pass 2 / fail 2` EXIT=1, với `AssertionError: … do duoc 2014ms ⇒ backoff da leo thang don dieu`.
   ⇒ **Luật: mọi recipe/vòng sửa phải kèm BẰNG CHỨNG ĐỎ trên mã chưa sửa.** Không có nó thì không biết phép đo
   có phân biệt được gì hay không. (Đây là TDD áp cho chính *phép đo*, không chỉ cho test.)
2. **`AbortSignal.timeout` KHÔNG phải lưới chống treo** khi mọi thứ chạy trong **cùng một tiến trình**: nó huỷ một
   `fetch`, **không** làm một promise không bao giờ về tự kết thúc. Thứ chặn treo là **hạn của vòng CHỜ** —
   dùng `waitFor` của Testing Library (có timeout) cho mọi chỗ chờ. Brief gợi ý sai cơ chế này.
3. **`--test-isolation=none` nghĩa là MỌI tệp test dùng CHUNG MỘT TIẾN TRÌNH.** ⇒ Bất kỳ thay đổi **global** nào
   (`globalThis.fetch`, `window`, `document`, `IS_REACT_ACT_ENVIRONMENT`) **PHẢI được trả lại nguyên trạng trong teardown**,
   nếu không các suite sau sẽ chạy trên một môi trường đã bị sửa và hỏng theo cách **rất khó lần**.
   Implementer đã làm đúng (`teardownDom()` trả `globalThis.fetch` về nguyên bản) và nêu rõ lý do.
   ⇒ **Áp cho T5–T11**: mọi harness DOM phải có `teardownDom` tương ứng, và phải chạy **toàn bộ** `npm test`
   (không chạy lẻ tệp) để chứng minh không có nhiễm chéo.
4. **`npm i` với `package-lock.json` CŨ sẽ PRUNE gói thừa** — đo được: `added 50 packages, removed 55 packages`
   (dọn sạch tàn dư cây Vite/Vitest cũ; `vite`, `vitest`, `@playwright` nay **đều vắng**, còn `react`, `react-dom`,
   `rollup`, `@swc/core`, `typescript`, `jsdom`, `@testing-library/react` **đều có**). Và **`package-lock.json` được
   viết lại** (1619 dòng) ⇒ nợ `G-2`/dòng 43 ("lockfile cũ, `npm ci` phải fail") **đã được hoà giải một phần**.
   ⇒ Sau **mọi** lệnh cài: chạy lại **cả ba** cổng (`npm test`, `typecheck`, `build`), và **kiểm `node_modules`
   còn những gói đang dùng** — một lần prune có thể lấy đi thứ bạn cần.

5. **Một dòng "đúng nhưng không quan sát được" phải được khai là không quan sát được.** `decoder.decode()` xả cuối
   (`useJobStream.ts`) **không thể tạo thêm sự kiện nào**: parser chỉ phát khi thấy `\n\n` (ASCII, luôn nằm **sau**
   JSON), còn `decode(stream: true)` chỉ giữ **chuỗi byte cuối chưa hoàn chỉnh** — ở cuối stream nó không bao giờ
   hoàn chỉnh được nữa. Implementer thêm dòng đó nhưng **không** có test ghim và **không** khai "đã kiểm".
   ⇒ **Đó là cách đúng để ghi một dòng không đo được.** Tasks 4–13 phải làm y vậy thay vì gán cho nó một bài test giả.

## ⚠️ ERRATA #8 — re-review Task 3 (`bc0dcae`, **PASS**): **`git diff` KHÔNG chứng minh phục hồi byte-exact**

Task 3 **ĐÓNG** (`PASS`, 0 Critical / 0 Important / 8 Minor). Re-review tái lập độc lập trạng thái ĐỎ trên mã chưa
sửa (đúng ERRATA #7 mục 1), và 4/4 mutation bắt buộc giết **đúng** bài chỉ định (`splice(0,1)` cho
`actual: 3, expected: 2`; xoá `retryAttempt = 0;` cho `2008ms` thay vì `503ms`). Nó cũng để lại **hai phát hiện
lớn hơn chính task**:

### 1. QUY TRÌNH CHỨNG MINH PHỤC HỒI CỦA DỰ ÁN ĐANG THIẾU — `git diff --quiet` KHÔNG ĐỦ

Repo này có **`core.autocrlf`**. Đo được: **mỗi lần phục hồi sau mutation in
`warning: … LF will be replaced by CRLF …` nhưng `git diff --quiet` VẪN `EXIT=0`**.
⇒ **`git diff` MỘT MÌNH không chứng minh được tệp đã trở về byte-exact.**

**Quy trình ĐÚNG, thay thế mọi câu "chứng minh `git diff --quiet HEAD` EXIT=0" trong các brief trước:**
1. Giữ **bản gốc trong bộ nhớ** trước khi mutate;
2. so **`Buffer.equals(orig) === true`** (hoặc hash tự tính trên byte thật);
3. **và** blob hash == `git hash-object <f>` == `git rev-parse HEAD:<f>`;
4. **và** in **witness** `PRESENT`/`ABSENT` để chứng minh *cái đã đổi là cái định đổi* (ERRATA #6 mục 5).
`git diff --quiet` chỉ còn là **kiểm phụ**, không bao giờ là bằng chứng duy nhất.

### 2. HARNESS DOM CÓ MỘT LỖ HỔNG PHẢI VÁ TRƯỚC T5 — và nó thuộc loại "xanh giả"

`frontend/test/dom.ts`: `teardownDom()` **chỉ** trả `globalThis.fetch` và xoá `IS_REACT_ACT_ENVIRONMENT`;
**8 global khác** (`window`, `document`, `navigator`, `HTMLElement`, `Node`, `Event`, `MouseEvent`,
`getComputedStyle`) **vẫn trỏ vào jsdom đã `close()`** (đo được `window.closed=false`).
Và `setupDom()` có `if (dom !== null) return;` ⇒ **lần gọi thứ hai với origin KHÁC bị bỏ qua IM LẶNG.**
Với `--test-isolation=none` (**mọi tệp test chung MỘT tiến trình**, ERRATA #7 mục 3), T5–T11 sẽ dựng nhiều suite
DOM ⇒ lần gọi thứ hai trỏ nhầm server mà **không có gì báo**. ⇒ **Phải vá trước T5** (đang làm ở Task 3b).

### 3. Bốn lỗ hổng ĐỘ PHỦ (không phải lời khai sai — ghi nhận là nợ)

Reviewer tự nghĩ và tìm được **4 mutation sống sót**, mỗi cái chỉ ra một đường **không bài nào ghim**:
`X1` đường "id **ĐÃ BIẾT** → áp thẳng" (xoá `publish(applyJobEvent(current, event))` vẫn 4/4 xanh);
`X2` lý do đặt `retryAttempt = 0;` ở **byte đầu tiên** thay vì ngay sau `response.ok`;
`X3` đường **drain** cho sự kiện lạ tới **trong lúc** request ảnh chụp đang bay;
`X4` `slice(5)`→`slice(6)` vẫn là **đột biến tương đương** (hai bài parser mới không đóng lỗ này).
⇒ Nợ độ phủ, **không** được coi là "đã kiểm".

### 4. Hai câu SAI còn nằm trong tệp sản phẩm (phải sửa, rẻ)

- `frontend/test/swc-loader.test.tsx:9` vẫn viết *"khong co DOM … npm i bi chan"* — **SAI** từ ERRATA #5
  (`jsdom` + Testing Library **đã cài và đang chạy**). Sửa ở Task 3b.
- `frontend/package.json` còn `"e2e": "playwright test"` trong khi **`@playwright/test` đã bị prune** khỏi
  `node_modules` ⇒ script **chết vì thiếu binary**. Task 12 đã được giao việc bỏ/sửa.

### 5. Một đính chính về phương pháp của CHÍNH tôi

Brief của tôi nhiều lần yêu cầu *"chứng minh `git diff --quiet HEAD` EXIT=0"* như **bằng chứng phục hồi**.
Với `core.autocrlf`, câu đó **không chứng minh được** điều nó tuyên bố. Đây là lần thứ **sáu** một thủ tục của
tôi bị một reviewer/implementer đo ra là **chưa đủ chặt**. Giữ nguyên tinh thần: **người điều phối cũng phải bị đo.**

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
  | `jsdom`, `@testing-library/react`, `@testing-library/dom`, `happy-dom` | **`False`** — đều không có, và `npm i` bị chặn — ⚠️ **PHÉP ĐO NÀY ĐÃ BỊ BÁC BỎ Ở ERRATA #5 MỤC 2.** Cài được bằng `--cache` trong workspace, và **chạy thật** (click thật đã đo, EXITCODE=0). Dòng này giữ lại làm **dấu vết của một kết luận sai** — đừng đọc nó như ràng buộc |

  **Ruling:**
  1. Runner là **`node --test --test-isolation=none`**. `--test-isolation=none` là **bắt buộc**, không phải tuỳ chọn — thiếu nó thì mọi test chết `EPERM`.
  2. Test `.tsx` chạy qua một **loader `@swc/core` trong tiến trình** (`module.registerHooks`, `transformSync` — napi, **không spawn**). Loader là ~20 dòng; **phải có test ghim chính nó**, vì nó là hạ tầng của mọi test UI.
  3. ~~**Không có DOM ⇒ không `jsdom`, không Testing Library.**~~ ⚠️ **BỊ BÁC BỎ Ở ERRATA #5 MỤC 2** — `jsdom` + `@testing-library/react` **cài được VÀ chạy thật**. `renderToStaticMarkup` **vẫn giữ** cho render thuần (rẻ hơn ~12 s, không cần DOM) nhưng **không còn là cách DUY NHẤT**, và **không đủ** cho tương tác.
  4. ~~**Hệ quả phải nói thẳng:** test đơn vị **không mô phỏng được tương tác** (click, focus, bàn phím, effect, state update).~~ ⚠️ **BỊ BÁC BỎ Ở ERRATA #5 MỤC 2.** Tương tác **mô phỏng được** bằng jsdom + Testing Library, **trong tiến trình, không spawn**. Và lý do "chỉ Playwright làm được" **cũng không còn**, vì **Playwright bất khả** (ERRATA #5 mục 3: Chromium chết ở Mojo named pipe). ⇒ T6/T8/T9/T10/T11 phải có test **tương tác THẬT**, không chỉ (a) mã HTML render ra và (b) hàm thuần.
  5. Vì thế `T11` (bàn phím) **không được** tuyên bố "xong" chỉ bằng test đơn vị — nhưng **nay có đường**: jsdom + `fireEvent.keyDown`/`userEvent`, khẳng định **trên DOM thật**, cho §12.5. ⚠️ Vẫn **KHÔNG** chứng minh được: **layout, CSS thật, audio/`Range`** — jsdom không phải trình duyệt (ERRATA #5 mục 4.4). Đừng ghi "đạt" cho những tiêu chí đó.

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
| `e2e/seed.py` · `e2e/*.test.tsx` | gieo DB + **jsdom/Testing Library** bốn màn hình trên backend THẬT (Playwright **bất khả** — ERRATA #5 mục 3) |

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

**Vitest: KHÔNG cài** — nó dựng trên Vite, mà Vite cần `esbuild`, và `esbuild` **spawn** nên vẫn chết `EPERM`. ⚠️ **Nhưng jsdom và Testing Library thì CÀI ĐƯỢC VÀ CHẠY ĐƯỢC** — câu cũ *"Cả ba đều không dùng được ở môi trường này"* **đã bị bác bỏ ở ERRATA #5 mục 2** (đo được cả cài đặt lẫn click thật). Dùng chúng cho **TƯƠNG TÁC** ở T5–T11, với công thức cài ở ERRATA #5 mục 1.
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

- [ ] **Step 3: Test ĐỎ cho màn Biên tập** (**Testing Library + jsdom — ĐÃ DÙNG ĐƯỢC**, xem ERRATA #5 mục 2: khẳng định **tương tác THẬT** trên DOM thật, cộng khẳng định **hàm thuần**; `fetch` **giả** ở tầng `endpoints` — không phải tầng `window`):

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
    # ⚠️ ĐÍNH CHÍNH (review Task 2 bắt, M-3). Bản đầu của plan viết
    #   old = [t for t in repos.list_terms(lang=lang) if t.term != term]
    # tức LOẠI TRỪ hàng đang sửa khỏi trạng thái cũ. CÁCH ĐÓ SAI, và chính
    # backend này đã đo: docstring `_recompute_affected` (routes_glossary.py:92-98)
    # nói thẳng nó mất giá trị `approved` CŨ nên ca BỎ DUYỆT không bao giờ báo ảnh
    # hưởng — "Đo được: ... test_unapproving_a_term_also_affects_the_translations_
    # that_use_it đỏ với `[] == [1]`". Bài đó TỒN TẠI và đang xanh với mã hiện tại.
    # Trạng thái cũ là trạng thái THẬT trước khi ghi ⇒ KHÔNG lọc gì cả.
    old = repos.list_terms(lang=lang)
    # `neue` thì lọc đúng như backend làm: thay hàng cùng `term` bằng hàng mới.
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

### Task 12: Bốn màn hình trên backend THẬT — jsdom + Testing Library (**Playwright BẤT KHẢ**, xem ERRATA #5 mục 3)

**⚠️ TÊN TASK ĐÃ ĐỔI.** Bản cũ là *"Playwright trên backend THẬT"*. Playwright **không chạy được** ở đây:
Chromium chết ở `FATAL:mojo\public\cpp\platform_channel.cc:187 … Access is denied (0x5)` — **chính trình duyệt**
dùng named pipe cho IPC của nó, nên bản tải về **và** Edge/Chrome có sẵn trên máy **đều không khởi động được**
(đo đủ 5 bước ở ERRATA #5 mục 3). **Đừng thử lại `npx playwright install`.**

**Cái KHÔNG đổi — và là lý do task này tồn tại:** phải chạy trên **backend THẬT với DB đã gieo đủ hai thứ**
(ERRATA #3 mục 3: một transcript **có segment** **và** ≥1 hàng `translations`), vì guard của `contract.test.ts`
vẫn đỏ nếu thiếu. Và **không** được dựng engine/endpoint giả chỉ để test (spec §6).

**Cái ĐỔI:** thay `page.click(...)` của Playwright bằng **`fireEvent`/`userEvent` của Testing Library trên jsdom**,
gọi vào **cùng những component thật** và **cùng backend thật qua HTTP thật**. Đây **không** phải test giả lập:
nó render React thật, chạy effect thật, gửi request thật, đọc response thật.

**⚠️ GIỚI HẠN PHẢI GHI VÀO BÁO CÁO, KHÔNG ĐƯỢC GIẤU:** jsdom **không phải trình duyệt** — không layout,
không CSS thật, không audio/`Range`, không `getBoundingClientRect` có nghĩa. ⇒ **"Giao diện chạy được trong
trình duyệt thật" vẫn là điều CHƯA AI CHỨNG MINH.** Task này **không** được tuyên bố điều đó.

**Files:**
- Create: `frontend/test/dom.ts` (setup jsdom dùng chung), `frontend/e2e/seed.py`, `frontend/e2e/harness.ts`,
  `frontend/e2e/edit.test.tsx`, `frontend/e2e/compare.test.tsx`, `frontend/e2e/glossary.test.tsx`,
  `frontend/e2e/ollama-down.test.tsx`
- Modify: `frontend/package.json` (thêm `jsdom` + `@testing-library/react` **bằng công thức ERRATA #5 mục 1**;
  **sửa hoặc bỏ** script `"e2e": "playwright test"` — nó là script không bao giờ chạy được)

**Interfaces:**
- Consumes: toàn bộ app đã dựng
- Produces: `npm test` bao gồm bốn tệp `e2e/*.test.tsx` — tự khởi động backend trên DB gieo, chạy bốn màn hình,
  tự tắt; và **một dòng trung thực** về việc gì chưa đo được

- [ ] **Step 1: `e2e/seed.py` — gieo thẳng DB, không cần model**

Dùng chính `SqliteRepos` của backend (đừng viết SQL tay: `add_transcript`, `add_translation`, `upsert_term`, `add_job` đã có, và chúng giữ được ràng buộc schema):

```python
"""Gieo mot DB day du de UI doc. KHONG can model, KHONG can GPU.

Vi sao: test (jsdom + Testing Library) dieu khien tien trinh server THAT, nen khong tiem duoc engine
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

- [ ] **Step 2: `harness.ts` + `test/dom.ts` — backend do test tự dựng, và một jsdom thật**

`test/dom.ts` dựng `JSDOM` + gán global (`window`, `document`, `navigator`, `HTMLElement`, …) và bật
`IS_REACT_ACT_ENVIRONMENT`. **Đã đo cách này chạy** (ERRATA #5 mục 2).

`harness.ts`: khởi backend bằng `spawn` với `PHUDE_DB`/`PHUDE_DATA` trỏ vào **thư mục tạm trong workspace,
ngoài repo** (`$env:TEMP` bị từ chối), chạy `seed.py` trước, poll `/api/status`, và **tắt trong teardown**
(chỉ tắt pid của chính nó — bắt chước `contract.test.ts`, kể cả `child.unref()` để một lần kill hỏng không
treo `node --test` mãi).

⚠️ **Bẫy URL tương đối — phải xử lý, đừng để implementer tự phát hiện:** `client.ts` gọi `fetch("/api/…")`
và **`fetch` của Node KHÔNG resolve URL tương đối**. `jsdom` cũng không đổi được điều đó (jsdom không cấp
`fetch`). ⇒ Trong `test/dom.ts`, bọc `globalThis.fetch` bằng một hàm **resolve URL tương đối theo origin của
backend thật** (ví dụ `http://127.0.0.1:8620`), và ghi rõ trong comment rằng đây là **cầu nối URL**, không phải
giả lập mạng — request vẫn đi HTTP thật. **Không** được thay `fetch` bằng stub dữ liệu.

- [ ] **Step 3: Bốn màn hình, mỗi cái một tiêu chí ở spec §8 — viết bằng Testing Library**

```tsx
// e2e/glossary.test.tsx
test("doi mot thuat ngu thi thay SO BAN DICH BI ANH HUONG truoc khi luu", async () => {
  render(createElement(App));                      // component THAT, khong phai ban sao
  fireEvent.click(await screen.findByRole("radio", { name: /thuật ngữ/i }));
  fireEvent.change(screen.getByLabelText(/thuật ngữ/i), { target: { value: "câu 1" } });
  fireEvent.change(screen.getByLabelText(/bản dịch/i), { target: { value: "cau mot" } });
  // tieu chi §12.3: so ban dich bi anh huong hien TRUOC khi bam luu
  await waitFor(() => assert.match(screen.getByTestId("affected-preview").textContent ?? "", /1/));
});
```

- `ollama-down.test.tsx` khẳng định panel nói rõ **cái gì còn chạy được** khi Ollama tắt (§12.6).
  ⚠️ Trạng thái Ollama trên máy này **đổi theo lúc** (`up` đã đo được, `unknown` đã đo được, `down` **chưa từng** đo được)
  ⇒ test phải chịu được **cả ba**, và **không** được giả định `down`.
- `edit.test.tsx` phủ sửa dòng + đoạn `suspect` có nhãn lý do.
- `compare.test.tsx` phủ segmented control + cột CPS.

**Bắt buộc:** mỗi test phải đi qua **`fetch` thật tới 8620** — **cấm** stub tầng `client.ts`/`endpoints.ts`
trong bốn tệp này (đó chính là thứ task này tồn tại để tránh). Nếu một màn hình không render được vì thiếu
dữ liệu, **sửa `seed.py`**, đừng stub.

- [ ] **Step 4: Chạy và ghi số**

```bash
cd frontend && npm test
```
Kỳ vọng: bốn test mới **xanh trên DB gieo**, `cancelled 0`, và dán **dòng tổng kết nguyên văn** vào báo cáo.
Trên `data/app.db` **rỗng** thì hai guard `EMPTY_DB_MSG` **vẫn đỏ** — đó là trạng thái đúng (ERRATA #3 mục 2).
Rồi mutation: đổi `data-over-cps` ở `CompareScreen` thành luôn `"false"` ⇒ test Đối chiếu phải đỏ.

- [ ] **Step 5: Commit** — `test(fe): bon man hinh tren backend that voi du lieu gieo (jsdom + RTL, Playwright bat kha)`

⚠️ **Và phải viết vào báo cáo đúng một câu trung thực:** *chưa có bằng chứng nào cho việc giao diện chạy trong
một trình duyệt thật; jsdom không có layout/CSS/audio.* Nếu implementer bỏ câu đó, coi như task **chưa xong**.

---

### Task 13: Tài liệu + thu hoạch nợ `ponytail:`

**Files:**
- Modify: `README.md`
- Create: `.superpowers/sdd/<plan>/ponytail-debt.md` (ngoài repo)

- [ ] **Step 1: Gom mọi dấu `ponytail:` trong `frontend/`** bằng `grep -rn "ponytail:" frontend/src` và chép vào một bảng: **tệp · trần · đường nâng cấp**. Dấu nào thiếu trần thì **sửa ngay** — một dấu không nêu trần là nợ không đòi được.
- [ ] **Step 2: README** — mục "Chạy frontend": hai lệnh, hai cổng, và **cách chạy contract test** (phải có backend đang chạy). ⚠️ **`npm run e2e` KHÔNG còn** — Playwright bất khả (ERRATA #5 mục 3); bốn màn hình nay chạy trong `npm test`.
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
| §6 `node --test` + **jsdom/Testing Library** trên backend thật (Playwright bất khả) + luật dự án | **T2**, **T12** |
| §7 dấu `ponytail:` nêu trần + vòng thu hoạch nợ | **T5**, **T13** |
| §8 chín tiêu chí nghiệm thu | **T6/T7/T8/T9/T10** (1–5), **T12** (1, 3, 4, 6), **T2** (7), **T5** (8), **T13** (9) |

## Tự soát (writing-plans)

1. **Placeholder:** không có `TBD`/`TODO`. Chỗ tôi **cố ý** để người làm tự chọn là giá trị màu/chữ nào spec UI không ghi số — và plan nói rõ **phải chọn rồi ghi vào `tokens.css`**, không được để trống.
2. **Mâu thuẫn nội bộ:** không. `available` chỉ đọc từ backend (T10) và T8 cũng nói CPS chỉ đọc từ backend — cùng một luật, hai chỗ.
3. **Nhất quán kiểu:** `Segment`/`Job`/`Translation` định nghĩa **một lần** ở `src/api/types.ts` (T2) và mọi task sau tiêu thụ từ đó; `formatTimecode`/`parseTimecode` chỉ ở `src/lib/timecode.ts` (T6); `visibleRange`/`withPinned` chỉ ở `src/lib/window.ts` (T5).
4. **Phạm vi:** 13 task, mỗi task một deliverable kiểm được độc lập. Không task nào phụ thuộc task **sau** nó.
5. **Rủi ro đã biết:** `npx playwright install` **vô nghĩa** (T12 — Chromium bất khả, ERRATA #5 mục 3); `tokens.css` phụ thuộc việc đọc spec UI §2 (T1 Step 3); giá trị CPS/`available` đến từ backend nên **backend phải chạy** cho contract test và e2e — plan nói rõ ở T2 Step 3 và T12 Step 2.

## Những gì plan này KHÔNG làm (hoãn có chủ ý)

§4.5 Chimera · §4.6 bảng eval · §4.7 chấm tay 20 câu · layout điện thoại (§10.4) · sáng/tối và tuỳ biến bảng màu (§10.1–2) · kéo-thả sắp xếp cột (§10.6).



