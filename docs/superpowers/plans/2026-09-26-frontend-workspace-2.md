# Giai đoạn Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng bàn làm việc chạy trong trình duyệt cho bốn màn hình backend đã phục vụ được (Biên tập, Đối chiếu, Thuật ngữ, lỗi Ollama) + khung ba vùng + thanh transport, đủ để làm trọn luồng biên tập bằng bàn phím.

**Architecture:** SPA React 19 thuần client, **không router** — một shell với `mode ∈ {edit, compare, glossary}`. Trạng thái server nằm ở một tầng `fetch` mỏng cộng **đúng một** subscription SSE tới `/api/jobs/stream`; trạng thái client nằm trong một reducer. Không ghi kiểu đoán trước cho bản dịch.

**Tech Stack:** React 19 · TypeScript · **Rollup** + `dev-server.mjs` (Vite **bị loại** — xem ERRATA) · **`node --test --test-isolation=none`** + loader `@swc/core` trong tiến trình (Vitest **bị loại** — nó cần Vite/esbuild, mà esbuild **spawn**; **Testing Library thì DÙNG ĐƯỢC** — ERRATA #5 mục 2) · CSS thuần + custom property · font self-host woff2.

**Spec:** `docs/superpowers/specs/2026-09-26-frontend-workspace-2-design.md`

## Global Constraints

- **Node v24.16.0, npm 11.13.0** (đã đo; `pnpm` có nhưng dùng **npm** cho ít bộ phận hơn). Frontend ở `frontend/` **trong repo** `phu-de-lab`.
- Dev server **cổng 3100** (khớp `FRONTEND_DEV_ORIGINS` ở `backend/app/api/app.py:19`), proxy `/api` → `http://127.0.0.1:8620`.
- Backend **không** chạy sẵn: mọi test đầu-cuối phải **tự khởi động** nó và **tự tắt**. Cổng 8620 **tắt** — đừng giả định nó sống.
  ⚠️ **ĐÍNH CHÍNH (Task 4, `00535e1`):** câu *"và 11434 (Ollama) hiện đều **tắt**"* **SAI khi đo lại** —
  `netstat` cho `TCP 127.0.0.1:11434 … LISTENING` (PID 3408). **Đừng hard-code trạng thái Ollama**: nó **đổi theo lúc**
  (`up` đo được, `unknown` đo được, `down` **chưa từng** đo được). Mọi thứ chạm Ollama phải chịu được **cả ba**.
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
`getComputedStyle`) **vẫn trỏ vào jsdom đã `close()`** (⚠️ **câu `(đo được window.closed=false)` ở đây là SAI — xem ERRATA #9 mục 4; jsdom 30.1.1 KHÔNG phơi `closed`. Kết luận thì đúng và đã được ghim bằng một bài test ĐỎ trước khi sửa ở `494ddfb`, chỉ con số dẫn chứng là sai**).
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

## ⚠️ ERRATA #9 — Task 3b (`494ddfb`): **HOOK CẤP TỆP BỊ KÉO LÊN GỐC** — luật bắt buộc cho T5–T11

Task 3b vá xong hai lỗi **xanh giả** của harness (`setupDom` im lặng bỏ qua origin thứ hai; `teardownDom` chỉ trả
`fetch` trong khi 8 global khác vẫn trỏ vào jsdom đã chết). Nó kèm **bằng chứng ĐỎ trước khi sửa**
(`ℹ tests 2 / pass 0 / fail 2`, in ra `window: truoc=undefined / sau=[object Window]` …) và 4 mutation giết
**đúng** bài (`H1` chỉ giết bài "hai origin"; `H2`/`H3`/`H4` chỉ giết bài "trả hết global"). `H5` **sống sót** và
được khai thẳng là **nợ độ phủ**, không ghim bằng khẳng định giả. Nhưng nó tìm ra **một điều lớn hơn cả task**:

### 1. Dưới `--test-isolation=none`, **MỌI `before` chạy trước MỌI bài test, MỌI `after` chạy sau MỌI bài test**

Đo bằng probe 3 tệp + trace trên suite thật (log tạm rồi phục hồi byte-exact). Nghĩa là **hook ở CẤP TỆP bị kéo lên GỐC**:
`useJobStream.test.ts`'s `before` (gọi `setupDom`) chạy **trước bài đầu tiên của CẢ LƯỢT** — kể cả trước
`contract.test.ts` — và `after` (`teardownDom`) chạy **sau bài cuối cùng của CẢ LƯỢT**.
⇒ **Bề mặt nhiễm chéo RỘNG HƠN HẲN so với giả định trong brief của tôi** (brief giả định hook là theo tệp).

**LUẬT BẮT BUỘC CHO T5–T11:**
- **Bọc hook trong `describe()`** (`describe`-scoped hooks) cho **mọi** thứ đặt/trả global — **không** để `before`/`after`
  ở cấp tệp khi chúng sửa global. Hook theo suite mới thật sự theo suite.
- **Mỗi bài test DOM phải mở đầu bằng một `teardownDom()` "chuẩn hoá"** (hoặc tương đương) để không phụ thuộc thứ tự.
  Task 3b **đo cả hai cách** rồi mới chọn: thiếu lời gọi chuẩn hoá thì dưới `H1` **CẢ HAI** bài cùng đỏ
  ⇒ mutation **giết NHẦM bài** ⇒ bằng chứng rác. Nó **không** nới kỳ vọng của bài test để cho khớp.
- Vẫn chạy **TOÀN BỘ** `npm test` (không chạy lẻ tệp) — suy giảm do nhiễm chéo **chỉ** lộ ra ở lượt đầy đủ.

### 2. Một lời gọi `setupDom` = MỘT lần cài đặt

Ảnh chụp global chỉ lấy khi chưa có ⇒ `teardownDom()` trả về trạng thái **trước lần cài đặt ĐẦU TIÊN**, nhờ đó sau
bài "hai origin" tiến trình về **nguyên trạng** thay vì kẹt ở jsdom trung gian đã `close()`. Task 3b chọn
**"dựng lại"** thay vì **"ném lỗi"** ở `setupDom` lần hai — lý do: nhiều suite DOM trong một tiến trình là **bình thường**,
và chính bài test mà brief yêu cầu chỉ viết được với phương án này.

### 3. Chỗ Task 3b tự khai là CÒN CHƯA CHÍNH XÁC (sửa kèm task kế tiếp chạm tệp đó)

`frontend/test/dom.test.ts` dòng 19–21 vẫn viết "thứ tự bài là cố ý để ảnh chụp là trạng thái nguyên bản" —
**đúng khi chạy lẻ tệp, KHÔNG đúng trong lượt đầy đủ** (mục 1). Thứ bảo đảm hiện nay là **lời gọi chuẩn hoá ở dòng 69**.
Task 3b **không** sửa vì luật "một commit" và nó đã commit — đã ghi vào báo cáo.

### 4. Luật mới: **một con số trong BÁO CÁO REVIEW cũng là lời khai chưa kiểm**

ERRATA #4 mục 8 nói "một con số nằm trong LỜI KHAI cũng có thể nói dối" (về báo cáo implementer). Vòng này mở rộng:
tôi **chép** `window.closed === false` từ **báo cáo của reviewer** vào ERRATA #8 **mà không tự đo**, và Task 3b
đo ra **không tái lập được** (`jsdom` không phơi `closed`). ⇒ **Khi chuyển một con số từ BẤT KỲ báo cáo agent nào
(reviewer hay implementer) vào plan/ledger, phải TỰ ĐO trước.** Đây là lần thứ **BẢY** một con số/thủ tục của tôi
bị đo là sai trong giai đoạn này.

### 5. Một đính chính nhỏ về namespace của bằng chứng Task 3b

Số đếm của nó cho bài "hai origin": ĐỎ `server1=2, server2=0` (`request thu hai phai toi server2, body do duoc "server1"`),
XANH `server1=1, server2=1`. Và nó **tái lập được bẫy ERRATA #8 mục 1**:
`CRLF count: 162 | bytes: 6561 | Buffer.equals(baseline): false` rồi `git diff --quiet HEAD -- frontend EXIT=0`
— **byte đã khác mà git vẫn sạch**. Đây là bằng chứng độc lập thứ hai rằng quy trình cũ của tôi **không đủ chặt**.

### 6. Review Task 3b (`PASS`) — luật `describe()` ĐÚNG nhưng **CHƯA ĐỦ**: mỗi file DOM phải **TỰ CHỨA**

Review độc lập xác nhận hoisting bằng **BA phép đo khác nhau**: (a) 4 tệp trong cùng một lượt với **đồng hồ chung** —
`#01 t+0.47 A FILE-BEFORE` … `#03 t+3.55 D FILE-BEFORE` … `#04 t+4.32 A1 BODY` … `#21 t+7.21 D FILE-AFTER`
(mọi `before` cấp tệp **trước** bài test đầu tiên của cả lượt; mọi `after` **sau** bài cuối cùng);
(b) probe cho thấy **global do hook của tệp A cài thì NHÌN THẤY ĐƯỢC từ bài test của tệp B**;
(c) trace trên suite thật ghi ra tệp có mốc thời gian, không qua stdout. Và hook trong `describe()` **đúng là theo suite**.

**Nhưng nó đo thêm một điều tôi chưa nghĩ tới:** các **TỆP** chạy **tuần tự**, còn **hook thì hoist** ⇒ global do một file
cài **sống tới cuối CẢ LƯỢT**, và `teardownDom()` của file **SAU** **đóng luôn jsdom còn sống của file TRƯỚC**
(trace: `teardownDom dom=true` ở **4012 ms** đóng jsdom được cài ở **7 ms**; hiện **vô hại** chỉ vì bài cuối của file
trước đã xong ở **4003 ms** — tức đúng **9 ms** trước đó). Đây là loại "đúng nhờ may", không phải đúng nhờ thiết kế.

⇒ **LUẬT BỔ SUNG CHO T5–T11: mỗi file test DOM phải TỰ CHỨA.** Không được giả định jsdom/bắc cầu của mình **còn sống**
khi file khác đang chạy. Hệ quả thực dụng: đừng để state sống qua nhiều bài; đừng dựa vào thứ tự file; mọi thứ cần thiết
phải được cài trong hook **của chính file đó**.

### 7. Nợ độ phủ của harness — KHAI RA, và TRẢ Ở T5

- **`I1` (Important):** bất biến `if (daLuu.length === 0) luuGlobal();` (*"một `setupDom` = một lần cài đặt"*)
  **không bài test nào ghim**. Mutation `R4` (luôn chụp lại ảnh chụp global) làm **RÒ RỈ 10/10 global** mà
  `npm test` **vẫn `pass 35 / fail 2`** — chỉ một probe ở **`process exit`** mới bắt được.
  ⇒ **T5 PHẢI ghim bất biến này** (hoặc ghi vào sổ nợ **kèm cách đo**). Đây là loại lỗi mà test trong lượt
  **không** thấy được — nhớ khi viết test cho T5–T11 rằng **có thứ chỉ lộ ra ở `process exit`**.
- `R1` (`teardownDom` không xoá `bridgeOrigin`) và `R3` (bỏ idempotent cùng origin) **sống sót** ⇒ hai đường chưa ghim.
- `H5` (đường dựng lại không `close()` jsdom cũ) sống sót; reviewer **không** đo được nó có thật sự rò rỉ jsdom sống
  hay không (chỉ đo được "không bài nào bắt").
- **`M1`:** comment `frontend/test/dom.test.ts:19-21` nói *"thứ tự bài là cố ý"* — đúng khi **chạy lẻ tệp**,
  **KHÔNG** đúng trong **lượt đầy đủ**; thứ bảo đảm là lời gọi ở **dòng 69** (chứng minh bằng mutation `H1b`:
  bỏ dòng 69 ⇒ **CẢ HAI** bài cùng đỏ ⇒ mutation giết nhầm bài). **Sửa ở task kế tiếp chạm tệp đó.**
- **`M2`:** một trích đoạn trace trong báo cáo Task 3b **không còn tái lập trên mã đã commit**
  (nó lấy trước khi thêm lời gọi chuẩn hoá; kết luận đúng, bằng chứng cũ).
  ⇒ **Bài học: dán bằng chứng NGAY CẠNH trạng thái mã sinh ra nó** — bằng chứng tách khỏi mã là bằng chứng sẽ trôi.
- Reviewer **tự khai một sự cố của chính nó**: driver mutation sửa **hai điểm trên cùng một tệp** nhưng chụp backup
  riêng cho từng edit ⇒ lượt đầu để lại `dom.ts` ở **trạng thái mutant** khi lệnh kết thúc; nó phát hiện **trong chính
  lệnh đó**, khôi phục byte-exact, sửa driver (một backup mỗi **tệp**) rồi chạy lại.
  ⇒ **Luật cho mọi driver mutation: MỘT bản backup cho MỘT TỆP, không phải một backup cho một edit.**

## ⚠️ ERRATA #10 — Task 4 (`00535e1`): luật của tôi GÂY RA hỏng thật, và **bằng chứng phục hồi bất khả TRƯỚC commit**

Task 4 xong: `tests 50 / pass 48 / fail 2 / cancelled 0` EXIT=1, `typecheck` 0, `build` 0. Nó bác **bốn** chỗ nữa của
brief tôi (nâng tổng số sai của người điều phối lên **chín**), và **hai trong số đó là hệ quả trực tiếp của chính các
luật tôi vừa đặt ra** — đọc kỹ:

### 1. Luật "bọc hook trong `describe()`" (ERRATA #9) **gây ra hỏng thật** — và đó là bằng chứng nó cần thiết

`useJobStream.test.ts` (Task 3b) để `before/after` ở **cấp TỆP** ⇒ jsdom của nó sống **suốt lượt**.
`src/shell/App.test.tsx` đứng **TRƯỚC** theo thứ tự đường dẫn (`src/api` < `src/shell` < `src/state`) ⇒ lời gọi chuẩn hoá
của tệp mới **ĐÓNG jsdom đó**, và **ĐÚNG NĂM bài** chết `ReferenceError: document is not defined`
(đo ở lượt ĐỎ đầu: `tests 41 / pass 31 / fail 10`). Task 4 phải **bọc hook đó vào `describe()`** để sửa.
⇒ **Luật ERRATA #9 mục 1 không phải phòng xa: nó vừa cứu/ngăn một hỏng thật.** Giữ nguyên, và nhớ **thứ tự đường dẫn
quyết định tệp nào chạy trước** (`src/api` → `src/shell` → `src/state`).

### 2. HỆ QUẢ: căn cứ của `M1` (ERRATA #9 mục 7) **ĐÃ HẾT HIỆU LỰC** — đừng viết lại câu cũ

Brief tôi viết: *"thứ bảo đảm thật là lời gọi chuẩn hoá ở dòng ~69, chứng minh bằng `H1b`: bỏ dòng đó ⇒ cả hai bài cùng đỏ"*.
Điều đó **đúng trong bố cục CŨ**. Sau khi chuyển hook vào `describe()`, Task 4 **ĐO LẠI `H1b`** ⇒ `pass 48 / fail 2`,
**không giết bài nào**. Comment đã commit nói **sự thật đã đo**: thứ tự bài **KHÔNG** phải thứ bảo đảm; lời gọi chuẩn hoá
từ nay là **PHÒNG THỦ**, và `H1b` được ghi kèm **bố cục mà nó có hiệu lực**.
⇒ **Nếu Task 4 viết y brief thì comment mới sẽ là một câu SAI.** **Bài học: một kết luận đo được có THỜI HẠN — đổi bố cục
thì phải ĐO LẠI, và ghi kèm bố cục.** Đừng chép lại kết luận cũ vào tài liệu mới.

### 3. Quy trình "bốn phần" của ERRATA #8 **bất khả TRƯỚC commit** — và bất khả cho tệp MỚI

- `git diff --quiet HEAD -- frontend` **luôn EXIT=1 khi đang làm** (mọi thay đổi còn chưa commit). Nó chỉ đọc được **SAU commit**.
- Với **tệp MỚI**, `git rev-parse HEAD:<f>` **không thể tồn tại**:
  `fatal: path '…reducer.ts' exists on disk, but not in 'HEAD'` (đo với **bảy** tệp mới của Task 4).

⇒ **Quy trình ĐÚNG, thay cho câu cũ:** chụp một **baseline byte-exact NGAY TRƯỚC khi mutate** và chứng minh phục hồi bằng
**`Buffer.equals(baseline)` + hash của baseline**; chỉ những tệp **đã ở `HEAD`** mới so thêm được với `HEAD:<f>`;
`git diff --quiet` **chỉ đọc sau commit** (hoặc bỏ hẳn, vì `core.autocrlf` làm nó sạch dù byte đã khác).

### 4. Hai điều khác brief tôi nói sai

- **`Header.tsx`/`ChannelZone.tsx`/`QueueZone.tsx` chưa từng tồn tại** ⇒ **CREATE**, không phải Modify (đã vá ở Task 4 Files).
- **Cổng 11434 (Ollama) KHÔNG tắt** khi Task 4 đo (`LISTENING`, PID 3408) ⇒ đã vá ở `Global Constraints`.

### 5. Mutation tự bắt lỗi của chính implementer — ghi làm luật cho test SSE

Bài test stream của nó ban đầu **FLAKY** (phát sự kiện **trước khi** SSE mở ⇒ byte vào hư không) và có một **khẳng định
RỖNG** (`đang chạy` đã xanh sẵn nhờ job 7 trong ảnh chụp, không phải nhờ job 8). Mutation `MINE-4` bắt được; nó sửa:
**chờ `streams.size >= 1` trước khi phát**, và **khẳng định một chuỗi mà CHỈ job mục tiêu sinh ra được** (+ `10%`).
Sau đó 5 lượt `npm test` liên tiếp đều `pass 48 / fail 2`.
⇒ **Luật cho test SSE ở T5–T11:** (a) **chờ stream MỞ** rồi mới phát sự kiện; (b) mọi khẳng định phải dùng **dữ liệu mà
CHỈ mục tiêu sinh ra được** — một khẳng định xanh nhờ dữ liệu có sẵn trong ảnh chụp là **khẳng định rỗng**.

### 6. Nợ Task 4 khai ra (ghi nhận, chưa trả)

`lyDoCho` cho các nhánh `interrupted`/`cancelled`/`done`/`failed` **không bài nào ghim**; `abort()` của `useApi` là dòng
đúng nhưng **CHƯA QUAN SÁT ĐƯỢC** (endpoints không nhận `signal`) — khai ra, **không** gán test giả;
lưới ba vùng `214px/1fr/286px` **chưa được nhìn thấy** (chỉ khẳng định "không chạm `app.css`/`tokens.css`");
nợ harness `R1`/`R3`/`H5` **chưa trả** (Task 4 chỉ được giao `I1`/`M1`/`X1`).

### 7. ⚠️ ĐÍNH CHÍNH LẦN THỨ MƯỜI — tôi lại chép một lời khai SAI vào plan

**Câu tôi viết ở mục 6 bản trước — *"`Job` chỉ mang `workspace` ⇒ **không có đường job↔source**"* — là SAI.**
Review Task 4 (`CONDITIONAL PASS`, 1 Important = chính điều này) bác bỏ nó **bằng mã backend thật**:

- `backend/app/api/routes_jobs.py:68-76` — `_job_json` trả **`"payload": job.payload`** (đủ **15** khoá);
  `:155-157` — `GET /api/jobs` = `[_job_json(j) for j in repos.list_jobs()]`.
- `routes_jobs.py:26-36` — `IngestPayload.source_id` / `AsrPayload.source_id` là **hợp đồng BẮT BUỘC**.
- `pipeline/ingest.py:244-246` — tạo job `asr` với `payload={"source_id": …, "lang": …}`;
  `transcribe.py:75` — **đọc** `job.payload["source_id"]`.
- `domain/models.py:238-256` (`translation_id_of`) tự ghi: *"Suy ra từ payload là cách duy nhất đúng"*.
- Client **đã có chỗ chứa**: `types.ts` `Job.payload: Record<string, unknown>`, và `useJobStream` **giữ nguyên**
  `Job` từ ảnh chụp.

⇒ **Đường nối job↔source CHO `ingest`/`asr` LÀ CÓ** (qua `payload.source_id`). Vế **đúng** của lời khai:
`GET /api/sources` đúng **tám** khoá và **không có khoá bước nào** (đã đối chiếu `_source_json`), và bước **DỊCH** chỉ có
`translation_id` (đường dài) ⇒ **đèn hai bước đầy đủ** vẫn chưa dựng được.
⇒ **`ChannelZone.tsx:6-12`'s `ponytail:` TRẦN đang biện hộ bằng một điều SAI** — cùng lớp lỗi với docstring
`jobEvents.ts:26` ở Task 3. **Phải sửa ở vòng sửa của Task 4.**
⇒ **Và đây là lần thứ MƯỜI một con số/lời khai của tôi bị đo là sai.** Luật ERRATA #9 mục 4 (đo trước khi chép từ
báo cáo **reviewer**) nay mở rộng: **đo trước khi chép từ báo cáo IMPLEMENTER nữa** — tôi đã chép nguyên si.

### 8. `npm run typecheck` KHÔNG kiểm tệp test/harness nào — đo chính xác (M6 của review Task 4)

`tsc --listFiles` = **78** tệp *[⚠️ SỐ NÀY ĐÃ TRÔI: 78 → 79 → **81**. Đọc ERRATA #14 mục 1 — bất biến là **0 tệp `.test.`**, đừng dùng số tuyệt đối]*, **không có** `*.test.ts(x)` nào và **không có** `test/dom.ts`.
⇒ **"typecheck xanh" KHÔNG bao hàm "test/harness sạch kiểu"** — nợ `N-2` nay có số đo cụ thể.
Đối chứng dương của reviewer: cố tình tạo lỗi kiểu ⇒ `typecheck` EXIT=1 (nên phép đo **sống**, không phải vacuous).
**Hệ quả cho T5–T11:** một lỗi kiểu trong tệp test chỉ lộ ra **lúc chạy**, không lộ ở `typecheck`; và
**một khẳng định sai kiểu trong test có thể không bao giờ bị `tsc` bắt**.

### 9. Lỗ hổng độ phủ NGUY HIỂM NHẤT của Task 4 — nhãn ĐẢO mà 50 bài vẫn xanh

Mutation `S2` của reviewer: **đảo nhãn `đã tách tiếng` ↔ `chưa tách tiếng`** ⇒ **cả 50 bài vẫn xanh**.
Đây là chữ **người dùng đọc**, và nó nói ngược sự thật mà **không gì bắt được**. Các mutation sống sót khác:
`S1` (thứ tự hàng đợi), `S3` (định dạng duration), `APILOAD` (`useApi` reset `loading`/`error`), `REMOVEWAIT`
(bỏ khối chờ stream mở), `H1B` (0 bài — **xác nhận comment `M1` đã commit nói ĐÚNG**).
⇒ `S2` **phải được ghim** ở vòng sửa Task 4; phần còn lại ghi vào sổ nợ độ phủ.
⇒ **Và một điều reviewer nói thẳng:** nó **không chứng minh được** rằng bản vá FLAKY của implementer là **cần thiết**
(bỏ khối chờ stream vẫn `8/8` lượt xanh) ⇒ lời khai "test tôi từng FLAKY" là **chưa kiểm chứng**, không phải sai.

## ⚠️ ERRATA #11 — Task 4 ĐÓNG (`PASS`): **trong lượt ĐẦY ĐỦ, tín hiệu DUY NHẤT của guard là DÒNG STDERR**

Task 4 **ĐÓNG** sau vòng sửa `a90fc58`: re-review cho **`PASS`, 0 Critical / 0 Important / 5 Minor**.
Re-review tái lập độc lập cả hai vế của `S2` (**mutation sống sót trên bộ test CŨ** + **mutation giết đúng bài MỚI**),
và chứng minh witness guard **từ chối mutate** khi literal sai (`[TU CHOI MUTATE] … KHONG ghi tep nao. Tep nguyen trang: true`,
driver `EXIT=3`). Bốn điều nó đo được, phải nhớ:

### 1. ⚠️ SỬA ĐIỀU TÔI ĐÃ GHI SAI: EXIT **KHÔNG** phải kênh thông tin của guard trong lượt đầy đủ

Tôi ghi ở ERRATA #10 (và trong brief) rằng guard `process exit` cho tín hiệu bằng **`EXIT 0 → 1`**.
**Đo lại thì điều đó CHỈ đúng ở lượt chạy RIÊNG tệp DOM.** Trong **lượt ĐẦY ĐỦ** của dự án, `npm test` **vốn đã `EXIT=1`**
(hai bài `EMPTY_DB_MSG` đỏ chủ ý) ⇒ mutant `R4` để nguyên `EXIT=1`, **EXIT KHÔNG đổi**:
`ℹ tests 52 / pass 50 / fail 2 / cancelled 0` **EXIT=1** + dòng `[guard thoat] HARNESS DOM RO RI: 10/10 global CHUA ve nguyen trang`.
⇒ **Trong lượt đầy đủ, tín hiệu DUY NHẤT là DÒNG STDERR.**

**LUẬT CHO T5–T11:**
- Muốn biết guard có kêu hay không thì **phải grep dòng `[guard thoat]`** (hoặc chạy **riêng** các tệp DOM),
  **không** được đọc `EXIT` của lượt đầy đủ.
- **KHÔNG đăng ký guard trùng ở tệp khác** — hai guard cùng khẳng định một điều là hai nguồn sự thật.
- Và tổng quát hơn: **một tín hiệu chỉ nhìn thấy được bằng mắt trên stderr là một tín hiệu sẽ bị bỏ qua.**
  Khi dựa vào nó, hãy **viết ra cách kiểm** (lệnh grep cụ thể) ở nơi người sau đọc.

### 2. `ERRATA #7` mục 1 cần một nhánh cho lớp "LỖ HỔNG ĐỘ PHỦ" (không phải lỗi)

`ERRATA #7` mục 1 nói *"recipe chỉ là bằng chứng khi nó ĐỎ trên mã chưa sửa"*. Với **lỗ hổng độ phủ** (`S2`) thì
**không có mã sai để làm đỏ**: nhãn trong mã **vốn ĐÚNG**, thứ sai là **PHÉP ĐO**. Cách làm **trung thực** (và reviewer
xác nhận là đúng, không phải lách luật) là **chứng minh cả hai vế**:
1. **mutation SỐNG SÓT trên bộ test CŨ** (`pass 48 / fail 2` — y hệt lúc sạch) ⇒ chứng minh phép đo cũ **MÙ**;
2. **cùng mutation đó GIẾT ĐÚNG MỘT bài trên bộ test MỚI** ⇒ chứng minh bài mới **không rỗng**.
Và reviewer còn đo **vế mạnh nhất**: trên cùng mutant, bài `<App/>` kiểu **cả-DOM** (`container.textContent`) **VẪN XANH**
⇒ chứng minh **trực tiếp** rằng phép đo cả-DOM chính là thứ mù. ⇒ **Khi thêm bài ghim một lỗ hổng độ phủ, phải chứng minh
CẢ HAI vế, và nếu được thì chỉ ra phép đo CŨ mù ở đâu.**

### 3. "kèm `file:line`" là **NÓI QUÁ** — và đó là một mệnh đề SAI về bằng chứng

Báo cáo vòng sửa khai TRẦN mới viết *"kèm `file:line`"*. Reviewer mở từng nguồn: TRẦN dẫn **tệp + TÊN HÀM**, **không có
số dòng nào**. Nội dung TRẦN **đúng** (không mệnh đề sai nào), nhưng **cách mô tả bằng chứng của nó thì sai**.
⇒ **Một lời khai VỀ bằng chứng cũng là một lời khai có thể trôi.** Khi mô tả mình đã dẫn gì, hãy nói **đúng thứ mình dẫn**.

### 4. Ba nợ mới Task 4 khai ra (ghi nhận)

- **`jobs.id` là rowid KHÔNG `AUTOINCREMENT`** (`schema.py:48`, `sqlite_repos.py:364-375` INSERT không kèm id + `lastrowid`,
  hiện **0** `DELETE FROM jobs`). Quy ước *"id lớn nhất = hiện tại"* **an toàn HIỆN TẠI**, nhưng **phải ghi kèm** nếu sau này
  có đường **xoá** job (rowid có thể được **tái dùng**).
- **`ch__buoc` chỉ nói HAI bước đầu:** kênh đang **dịch** vẫn hiện `nạp: xong · phiên âm: xong` mà **không có tín hiệu**
  còn bước sau. Reviewer xác nhận đây là **nợ UX đã khai trong TRẦN**, **không** phải UI nói dối.
- **So sánh `===` với `payload.source_id`:** hợp đồng là **int**, nhưng nếu giá trị là **chuỗi số** thì nó **im lặng**
  thành "chưa có job" và **không bài nào ghim**. (Cùng họ với lớp "so sánh lỏng" — nhớ khi làm T5–T11.)
- Minor khác: hàng `NOJOBS` của báo cáo khai witness khớp **1 lần** nhưng literal đó khớp **2 lần** trong `App.tsx`
  (`git grep -c` = 2) — hiệu ứng thì tái lập được bằng literal scoped; và một **vết trôi** ở `task-4-report.md:72`
  (nói bốn hash còn lại "khớp HEAD", nhưng `App.tsx 587bf7e6…` là `00535e1:App.tsx`, còn HEAD nay `a89ba21d…`
  vì **chính vòng sửa đã viết lại `App.tsx`**).
- Reviewer **tự khai** một lỗi quy trình của nó: driver ghi backup **cạnh tệp đích** ⇒ **3 tệp `*.rev-baseline` lỡ nằm
  TRONG repo** (`frontend/src/shell/App.tsx.rev-baseline`, `ChannelZone.tsx.rev-baseline`, `frontend/test/dom.ts.rev-baseline`),
  phát hiện bằng `git status --porcelain`, **đã xoá cả ba** (count = 0), ảnh hưởng phép đo = **không**
  (không khớp glob test, không trong `tsconfig.include`, không phải entry rollup), và **đã khai ở đầu báo cáo**.
  ⇒ **Luật: backup của mutation để NGOÀI cây repo, hoặc dùng tên chắc chắn không khớp glob/`tsconfig`.**

## ⚠️ ERRATA #12 — Task 5 (`1ea45e5`): `git diff` **MÙ HOÀN TOÀN** với tệp chưa track; và mutation của tôi lại sai

Task 5 xong (`59`→`65` bài; `npm test` = `tests 65 / pass 63 / fail 2 / cancelled 0` EXIT=1; `typecheck` 0; `build` 0).
Nó sửa **lỗi thật** của plan (`withPinned` chỉ ghim đúng chiều TRÊN) — nhưng nó bác **ba** chỗ nữa của brief tôi.

### 1. ⚠️ `git diff --quiet HEAD -- frontend` in **EXIT=0** trong khi tệp **ĐANG LÀ MUTANT**

Đo được **8/8 lượt**: `window.ts` là tệp **MỚI chưa track**, mà `git diff` **không nhìn thấy tệp chưa track** —
nó không "thiếu chặt", nó **MÙ HOÀN TOÀN**. ⇒ Quy trình bốn phần của ERRATA #8/#10 nay có lý do thứ ba, mạnh nhất:
**với tệp mới, `git diff` không chứng minh được gì cả** — kể cả sau commit nó cũng chỉ nói về index.
**Bằng chứng phục hồi THẬT chỉ có: `Buffer.equals(baseline)` + hash tự tính (`bytes` + `sha256`).**

### 2. Mutation `W1` của TÔI SAI — lần thứ MƯỜI HAI

Brief tôi viết: *"`W1` điều kiện `withPinned` → `false` ⇒ bài 'GHIM ngoài khoảng' PHẢI đỏ"*.
**Đo được: bài đó XANH.** Lý do: với `pinned < range.start`, **nhánh `else` VỐN ĐÃ trả đúng** `{7, 120, true}`
⇒ bỏ điều kiện là **ĐỘT BIẾN TƯƠNG ĐƯƠNG** trên lớp đầu vào đó. `W1` **vẫn bị giết**, nhưng bởi bài *"trong khoảng"*
và bài *`pinned === null`* (đúng như dự đoán (d) trong brief).
Và **bài "ngoài khoảng" KHÔNG rỗng**: `W5` (bỏ phần mở rộng `start`) **giết nó**.
⇒ **Luật: khi một mutation không giết được bài mình nhắm, TRƯỚC KHI kết luận "bài rỗng", hãy hỏi mutation đó có phải
ĐỘT BIẾN TƯƠNG ĐƯƠNG không.** Với `withPinned`, chiều `pinned < start` và `pinned >= end` **không đối xứng**:
chiều dưới cần code mới để đúng, chiều trên thì **không** — nên chỉ có một mutation phân biệt được.

### 3. `tsc --listFiles` = **79** *[⚠️ đã trôi tiếp thành **81** — xem ERRATA #14 mục 1]*, không phải 78

`window.ts` là tệp **mới** và **được** `typecheck` (+1). Vế còn lại của ERRATA #10 mục 8 **vẫn đúng**:
**0** tệp `.test.` trong `listFiles` ⇒ `typecheck` không kiểm test/harness.

### 4. `git diff` mù (mục 1) + driver mutation CRASH để lại tệp ở trạng thái MUTANT

Driver lượt đầu **crash** (thiếu `mkdirSync(logs)`) và **để `window.ts` ở trạng thái MUTANT**; implementer phát hiện,
phục hồi **ngay**, chứng minh byte-exact bằng hash (`bytes = 2835`, `sha256 = 10f2f0ae…c665cf5` — **khớp baseline nó in
TRƯỚC khi mutate**), rồi **vá driver hai lớp**: `finally` + **`process.on("exit")` làm lưới an toàn**.
⇒ **Luật cho mọi driver mutation ở T6–T13: (a) `finally` PHẢI khôi phục; (b) thêm lưới `process.on("exit")`;
(c) in `bytes` + `sha256` của baseline TRƯỚC khi mutate, để phục hồi có cái mà đối chiếu.**
Đây là **lần thứ ba** một agent để lại tệp ở trạng thái mutant (2 lần trước: một re-reviewer 7,4 giờ; một re-reviewer khác).

### 5. Vi phạm luật "không `npx`" — tự khai, không ảnh hưởng sản phẩm

Implementer dùng **`npx --no-install tsc --listFiles` MỘT lần** (luật cấm `npx`), rồi **đo lại** bằng
`node ./node_modules/typescript/bin/tsc` ⇒ **cùng kết quả**, và **tự khai** trong báo cáo.
⇒ Không cần hành động (không chạm sản phẩm), nhưng **giữ luật**: dùng `node node_modules/...` trực tiếp, đừng `npx`.

### 6. `rowH <= 0`: quyết định đã chốt và ghim

Nó chọn **ném `RangeError`** với guard `!Number.isFinite(rowH) || rowH <= 0`, ghim **0 / −20 / NaN / Infinity**.
Nó khai thẳng: **không đo được** rằng ca này từng xảy ra trong sản phẩm. ⇒ Đây là **quyết định có ghi**, không phải sơ suất — đúng yêu cầu.

## ⚠️ ERRATA #13 — Task 5 ĐÓNG (`PASS`) + hai đính chính + nợ chuyển sang Task 6

Task 5 **ĐÓNG**: review độc lập cho **`PASS`, 0 Critical / 0 Important / 5 Minor**, và nó **chạy 13 mutation**,
tái lập **8/8** bảng của implementer. Ba điều nó đo được mà phải nhớ:

### 1. ⚠️ ĐÍNH CHÍNH ERRATA #12 mục 1 (lỗi thứ MƯỜI BA của tôi): `git diff` mù với tệp **CHƯA TRACK**, không phải "tệp mới"

Tôi viết *"`git diff` MÙ HOÀN TOÀN … kể cả sau commit nó cũng chỉ nói về index"*. **Vế sau KHÔNG chính xác.**
Đo ba ca:
| Ca | Kết quả |
|---|---|
| tệp **chưa track**, MỚI TẠO | `EXIT=0` ⇒ mù |
| tệp **chưa track**, ĐÃ SỬA | `EXIT=0` ⇒ mù |
| **`window.ts` ĐÃ TRACK** và ĐANG LÀ MUTANT | **`EXIT=1`** · `1 file changed, 1 insertion(+), 1 deletion(-)` ⇒ **THẤY** |

⇒ Câu đúng: **`git diff` mù trong lúc tệp còn CHƯA TRACK.** Sau `git add`/commit thì nó **thấy**.
Và **bằng chứng phục hồi THẬT** vẫn là: `Buffer.equals(baseline)` + **`bytes` + `sha256`** tự tính;
với tệp **đã ở `HEAD`** thì cộng `git hash-object == git rev-parse HEAD:<f>`.
⇒ **Hệ quả cho T6–T13: NGAY SAU khi tạo tệp mới, `git diff` không bảo vệ bạn — hãy tự in `bytes`+`sha256` trước khi mutate.**

### 2. `assert.throws(fn, /regex/)` khớp **MESSAGE**, KHÔNG khớp **TYPE**

Mutation `MINE-E` (`RangeError` → `Error`) **SỐNG SÓT** (`65/63/2`): bài test dùng `assert.throws(fn, /rowH/)`, mà
**regex chỉ khớp thông điệp** — một `TypeError` **cùng thông điệp** lọt qua. ⇒ **Luật cho T6–T13:** muốn ghim **LOẠI**
lỗi thì phải khẳng định **`instanceof`** (hoặc truyền **constructor** cho `assert.throws`), **đừng** chỉ đưa regex.

### 3. Nợ Task 5 (5 Minor, ghi nhận) — và **`M4` PHẢI vào brief Task 6**

- **`M4` (nguy cơ TÍCH HỢP THẬT):** `withPinned` có thể trả **`end > count`** — `withPinned({100,120}, 500)` ⇒ `end = 501`.
  `visibleRange` **kẹp theo `count`**, còn `withPinned` thì **không**, và **doc-comment KHÔNG nói**.
  ⇒ **Task 6 PHẢI TỰ KẸP `end` theo số đoạn** (hoặc gọi `withPinned` rồi kẹp), và **ghi lý do**.
- `M1`: cờ `pinned` tại **biên** `pinned === range.start` **không bài nào ghim** (mutation `MINE-B`: `>=` → `>` sống sót trên **CẢ HAI** bộ).
- `M2`: **kiểu** `RangeError` không được ghim (chính là `MINE-E` ở mục 2).
- `M3`: `withPinned` trả **`start` ÂM** khi `pinned` âm (`{0,20}, -1 → {-1,20}`).
- `M5`: câu chữ ERRATA #12 mục 1 hẹp hơn thực tế — đã sửa ở mục 1 trên.

### 4. Review chứng minh hai điều mà implementer KHÔNG khai (đáng chép vào cách làm brief)

- **`W2` — CHÍNH lỗi (c) của plan — SỐNG SÓT trên bộ bảy bài CŨ** (`tests 7 / pass 7 / fail 0`): phép đo cũ **MÙ HOÀN TOÀN**
  với lỗi ghim chiều DƯỚI. Đây là bằng chứng mạnh nhất rằng **brief phải sửa lỗi (c)** thay vì chép plan.
- **`MINE-C` (`ceil` → `floor`) sống sót bộ CŨ 7/7 VÀ bị giết bởi ĐÚNG MỘT bài MỚI** ⇒ đúng chuẩn **hai vế** của
  ERRATA #11 mục 2 (mutation sống sót trên bộ CŨ **+** giết đúng một bài trên bộ MỚI).

### 5. Ranh giới của bằng chứng Task 5 — phải nói đúng, đừng nói quá

Review chỉ chứng minh được `start <= pinned < end` là **ĐIỀU KIỆN CẦN** để dòng đang sửa nằm trong DOM,
**KHÔNG** phải điều kiện **ĐỦ** (vì `M4`). Và **hành vi thật** — ảo hoá tháo dòng đang gõ ⇒ **mất focus** (spec UI §8.3/U6) —
**CHƯA đo được**: chưa có caller (Task 6 mới dùng) và **không có trình duyệt**. ⇒ **Đừng ghi "đã kiểm U6".**

## ⚠️ ERRATA #14 — Task 6 (màn BIÊN TẬP): **token chưa có người dùng = tính năng chưa tồn tại**, và một DOM node trong `assert` là bom hẹn giờ

Task 6 xong (`d0b69bb` + `a0950cd`, **hai** commit): `npm test` = `tests 86 / suites 11 / pass 84 / fail 2 / cancelled 0`
EXIT=1, `typecheck` 0, `build` 0, **21 bài mới** (65 → 86), **19/19 mutation bị giết, 0 sống sót**.

### 1. Số `tsc --listFiles` **TRÔI** — 78 → 79 → **81**

Nó **tăng theo mỗi tệp nguồn mới** (`window.ts` +1, rồi `timecode.ts` + `EditScreen.tsx` +2).
⇒ **Luật (đúng tinh thần ERRATA #4 mục 7):** **đừng ghi số tuyệt đối** cho thứ trôi theo số tệp.
Ghi **LỆNH** + **BẤT BIẾN**:
```
node frontend/node_modules/typescript/bin/tsc --noEmit --listFiles -p frontend | Select-String "\.test\." | Measure-Object
```
**Bất biến: 0.** (Đã đo lại sau Task 6: tổng **81**, `\.test\.` = **0**.)

### 2. ⚠️ `app.css` PHẢI sửa — File list của plan (và brief tôi chép lại) **THIẾU**

`tokens.css` có `--suspect-hatch-*` **từ Task 1**, nhưng **chưa luật CSS nào dùng chúng**. Nghĩa là nếu chỉ thêm class
`is-suspect` mà không thêm luật vẽ vân thì:
- **test vẫn XANH** (nó khẳng định *class*),
- còn **sản phẩm KHÔNG có vân** — spec UI §2.5 ("nghi ngờ là **vân**, không phải màu") **không được thoả**.

⇒ **Bài học lớn: một token chưa có NGƯỜI TIÊU THỤ là một tính năng CHƯA TỒN TẠI**, và **một test khẳng định tên class
có thể xanh trong khi CSS không vẽ gì**. Đây là loại **xanh giả** mà **không test nào bắt được** trừ khi có người
**đọc `app.css`**. Task 6 đã sửa (+104 dòng, giữ CRLF) và **tự khai là lệch File list**.
⇒ **Cho T7–T13: khi một tính năng được mô tả bằng HÌNH THỨC (vân, lề, nhịp), hãy kiểm xem có LUẬT CSS nào thực sự
được thêm không, chứ đừng chỉ thêm class.** Và **brief phải liệt kê `app.css` khi task chạm hình thức.**

### 3. ⚠️ `assert.equal(<DOM node do React render>, null)` là **BOM HẸN GIỜ**

Đo được: nhánh **ĐỎ** của một bài test như thế làm `npm test` chạy **> 90 s** (lượt sạch **~6 s**).
Cùng mutant đó với trần **300 s** thì **xong bình thường và giết đúng bài** ⇒ không phải treo, mà là **chậm kinh khiếp**
khi `assert` phải **định dạng** một DOM node React khổng lồ trong **thông điệp lỗi**.
⇒ **LUẬT CHO T7–T13:** **đừng đưa một DOM node sống vào phép so sánh/khẳng định.**
Khẳng định trên **boolean** (`assert.ok(el === null)`), hoặc trên `textContent`/`className`/`getAttribute`.
Nếu không, **đường ĐỎ của chính test sẽ treo runner của mọi người sau** — và người sau sẽ tưởng đó là lỗi của họ.
Task 6 phát hiện điều này **trong vòng mutation của chính nó**, sửa bằng helper đếm, và **không `--amend`** (luật cấm)
⇒ **hai commit**; **không squash** khi hợp nhất (squash là viết lại lịch sử, đúng thứ luật cấm).

### 4. §4.2 **KHÔNG AI LÀM** — nợ tường minh, có lý do đo được

Plan **gán** "§4.1 (+ rỗng)" cho T6, nhưng brief **không giao** §4.2 (khung nét đứt `KÉO TỆP VÀO ĐÂY`), và Task 6 **không có
đường nạp tệp**: `uploadSource` **chưa được gọi ở đâu**, và backend upload **không có whitelist định dạng**
⇒ *"dòng mono liệt kê định dạng"* **không có nguồn trong mã**.
Implementer hiện **trạng thái rỗng NÓI THẬT** thay vì một lời hứa kéo-thả **không làm gì** — quyết định **đúng**.
⇒ **NỢ: §4.2 chưa được làm ở bất kỳ task nào. Phải giao tường minh, kèm quyết định về whitelist định dạng.**

### 5. Bốn nợ khác của Task 6

- **`App` gắn `<EditScreen transcript={null} />`** ⇒ **màn này CHƯA TỪNG render dữ liệu thật trong app** (chưa có đường
  **chọn kênh**). Mọi khẳng định về màn Biên tập hiện chỉ đến từ test truyền prop.
- **`viewportH` là prop mặc định `480`**, **không** đo `clientHeight` (đường đo không kiểm được ở đây nên implementer
  **không viết** — đúng).
- **`soDong` là ƯỚC LƯỢNG theo độ dài chuỗi**, **không** phải ngắt dòng thật ⇒ chiều cao cuộn có thể sai.
- **`parseTimecode` chưa có người gọi trong sản phẩm** (Task 7 mới dùng).
- **`E9` bị trần `90 s` CẮT NGANG** ⇒ bằng chứng của mutation đó **không đầy đủ** (`tests ? / pass ? / fail ?`, `log bytes=961`).
  Nó **tự khai**. ⇒ **Luật: một mutation bị CẮT thì KHÔNG được tính là "đã chạy"** — chạy lại với trần lớn hơn, hoặc ghi là chưa đo.

### 6. Một ranh giới tầng bằng chứng (đừng nói quá)

**jsdom kẹp `height` âm về `0px`** ⇒ mutation `E3` ghim `M4` ở tầng **`windowFor`** (hàm thuần), **KHÔNG** ở tầng **DOM**.
⇒ Nói đúng: *"`M4` được ghim ở tầng tính toán"*, **không** phải *"đệm âm không xảy ra trong DOM"*.
Và vẫn đúng như mọi task trước: **chưa ai nhìn thấy màn hình này trong trình duyệt thật** — jsdom **không có layout/CSS**,
nên **vân chéo, chiều cao hàng, lề amber, cuộn mượt 2000 dòng, giữ focus khi cuộn** đều **CHƯA được chứng minh**.

## ⚠️ ERRATA #15 — Task 6 ĐÓNG (`PASS`): con số THẬT của bẫy `assert`, và **một lời giải thích cơ chế cũng là một lời khai**

Task 6 **ĐÓNG**: review độc lập cho **`PASS`, 0 Critical / 0 Important / 4 Minor**. Nó **tái lập** cái bẫy, đo **10/10**
mutation (0 sống sót), và **bác một lời giải thích cơ chế** trong báo cáo.

### 1. ⚠️ Bẫy `assert` trên DOM node — SỐ ĐO THẬT (đắt nhất vòng này)

| Phép đo | Kết quả |
|---|---|
| `assert.equal(<DOM node React sống>, null)` ở **nhánh ĐỎ** | **218 697 ms** rồi **OOM**; lượt riêng khác **187 236 ms** |
| thông điệp lỗi | `head_message = "Array buffer allocation failed"`, `do_dai_message = 30` |
| `npm test` TOÀN BỘ lượt **SẠCH** | **5 398 ms** (5 lượt: 5 320–6 197 ms) |
| **đối chứng**: helper đếm | **1 ms** |
| **cơ chế**: `util.inspect` **có giới hạn depth** / **KHÔNG giới hạn** (đường `assert` đi) | **1 ms** / **187–219 s rồi OOM** |

⇒ **Cơ chế được XÁC NHẬN, không còn là suy đoán:** `assert` **định dạng không giới hạn độ sâu** giá trị trong thông điệp
lỗi, và một DOM node React là một đồ thị khổng lồ (có vòng) ⇒ **cấp phát bộ đệm khổng lồ ⇒ OOM**.
⇒ **LUẬT (giữ nguyên, nay có số):** **đừng đưa một DOM node sống vào phép so sánh/khẳng định.** Dùng **boolean**
(`assert.ok(el === null)`) hoặc `textContent`/`className`/`getAttribute`.
**Hệ quả thật:** nếu không, **đường ĐỎ của chính test sẽ treo/OOM runner của mọi người sau**, và họ sẽ tưởng đó là lỗi của họ.

⚠️ **Và một con số của implementer KHÔNG được kiểm chứng:** nó khai *"cùng mutant với trần **300 s** thì xong bình thường
(`86/83/3`)"*. Reviewer đo **một** khẳng định đã **218 s + OOM** ⇒ **300 s khó đủ**; nó **không chạy lại nguyên xi** nên
**con số đó CHƯA ĐO ĐƯỢC**. ⇒ Hàng `E9` trong bảng của Task 6 (`86/83/3/0`, trông như 18 mutation khác) **phải được đánh
dấu riêng** vì lượt đó dùng trần **300 s**. (Khớp ERRATA #14 mục 5: *một mutation bị CẮT thì không được tính là "đã chạy"*.)

### 2. ⚠️ MỘT LỜI GIẢI THÍCH CƠ CHẾ CŨNG LÀ MỘT LỜI KHAI — và lời này SAI

Báo cáo Task 6 viết *"jsdom **kẹp** `height` âm về `0px`"*. **SAI.** Đo được: **jsdom 30.1.1 BỎ khai báo âm**
(`style.height = ""`, computed `auto`) — nó **không** kẹp về `0px`.
May mắn: câu sai đó **chỉ nằm trong BÁO CÁO** (`task-6-report.md:106-107`, `:275`), **KHÔNG vào mã**
(grep `0px` trong `src` = **1** hit duy nhất, `EditScreen.test.tsx:186`, giá trị **đúng**).
**Kết luận mà nó bảo vệ vẫn ĐÚNG** (`E3` ghim `M4` ở tầng **`windowFor`**, không phải tầng DOM) — **chỉ cơ chế được kể sai**.
⇒ **Luật: khi giải thích VÌ SAO một phép đo cho kết quả đó, lời giải thích là một lời khai phải đo — không phải phần thưởng
cho một kết luận đúng.** Đây là lần thứ ba trong giai đoạn một **cơ chế** (không phải con số) bị kể sai:
`npm i`↔named pipe (ERRATA #5), "nguồn của `9 type`" (ERRATA #6), và giờ là jsdom↔`0px`.

### 3. ⚠️ Test chỉ ghim **`className`**, KHÔNG ghim **LUẬT CSS** — trần đã biết cho MỌI tính năng hình thức

Reviewer chứng minh **hai chiều**:
- gỡ **class** `is-suspect` ⇒ **đỏ đúng 1 bài**;
- **giữ class + XOÁ LUẬT CSS** ⇒ **vẫn XANH**.

⇒ Với **mọi** tính năng được mô tả bằng **hình thức** (vân, lề, nhịp, chiều cao), **một test xanh KHÔNG bao hàm CSS tồn tại**.
**Luật cho T7–T13: khi thêm một tính năng HÌNH THỨC, hãy ghim thêm một điều gì đó về CHÍNH LUẬT CSS** (rẻ nhất: một bài test
**đọc `app.css`** và khẳng định luật/token cần thiết **có mặt**), hoặc **khai rõ** đó là trần đã biết.
`app.css` của Task 6 có luật thật (dán ở báo cáo): `.ed__item.is-suspect { background-image: repeating-linear-gradient(…) }`
+ `.ed__item { border-left: var(--suspect-hatch-w) solid transparent }`; **3/3** token `--suspect-hatch-*` **có** người dùng;
**CRLF giữ** (baseline 2420 B / CR=85 → nay 5335 B / CR=189).

### 4. **13 TOKEN MỒ CÔI** còn lại — nợ cho T7–T13 (mỗi cái là một tính năng CHƯA tồn tại)

`--panel-1`, `--panel-3`, `--ok`, `--surface-step`, `--fs-note`, `--fs-line`, `--fs-read`, `--lh-tight`, `--row-1`,
`--sp-5`, `--sp-6`, `--dur-1`, `--ease-1`.
⇒ **Khi một task dùng tới một trong số này, phải thêm LUẬT thật** (không chỉ class), và **xoá cái không dùng** ở Task 13.

### 5. Hai khai báo phương pháp của reviewer (đáng chép thành luật)

1. Nó để **2 tệp scratch tạm trong `frontend/node_modules/_rev_task6/`** (đã gitignore, `git check-ignore` xác nhận) —
   **đã xoá**, `Test-Path` False, `git status` rỗng **trước và sau**. ⇒ Chấp nhận được **vì** nằm trong thư mục đã gitignore
   và **đã tự khai**; nhưng **mặc định vẫn là để scratch NGOÀI cây repo**.
2. **Nó VÔ TÌNH chạm INDEX của git:** `git --work-tree=<ngoài> checkout <rev>^ -- frontend/src/styles/app.css`
   **cập nhật cả index** ⇒ `MM frontend/src/styles/app.css`. Nó **không** commit/amend/rebase và đã khôi phục **không phá huỷ**
   bằng `git update-index --refresh` ⇒ `:file == HEAD:file == e8900ba2…`, status rỗng; worktree **chưa bao giờ** đổi byte.
   ⇒ **LUẬT: để ĐỌC nội dung cũ của một tệp, dùng `git show <rev>:<path>` — TUYỆT ĐỐI không dùng `git checkout <rev> -- <path>`,
   vì nó ghi cả index lẫn worktree.**

## ⚠️ ERRATA #16 — Task 7: `Range` được chứng minh bằng HTTP THẬT, và **tôi lại kể sai một cơ chế của jsdom**

Task 7 xong (`213e555`): `npm test` = `tests 106 / suites 14 / pass 104 / fail 2 / cancelled 0` EXIT=1, `typecheck` 0, `build` 0,
**+20 bài** (86 → 106), **10 mutation, 0 sống sót**.

### 1. ✅ `Range` của backend đã được CHỨNG MINH — ghi lại làm mẫu

Đo trên **backend THẬT** (`build_components`/`build_app`), **DB scratch ngoài repo**, một source với **WAV thật 64044 byte**,
cổng **8621**:
| Ca | Kết quả (nguyên văn) |
|---|---|
| `Range: bytes=0-99` | **`HTTP/1.1 206 Partial Content`** · `accept-ranges: bytes` · `content-range: bytes 0-99/64044` · thân **100 byte** |
| **đối chứng** không `Range` | `200 OK` · `content-length: 64044` |
| **đối chứng** `bytes=999999-` | **`416`** · `content-range: bytes */64044` |
Và **`sha256(thân 206) == sha256(100 byte đầu)`** ⇒ 206 trả **ĐÚNG LÁT BYTE**, không chỉ đúng độ dài.
⇒ Đây là **bằng chứng HTTP thật** cho tiêu chí của task, **không cần trình duyệt** — đúng cách chia đôi Step 4 mà brief đã yêu cầu.
⇒ **Điều vẫn CHƯA chứng minh:** *"seek trong trình duyệt thật"* — **chưa ai tua rồi nghe thật**. Đừng ghi là đã kiểm.

### 2. ⚠️ LỖI THỨ MƯỜI LĂM CỦA TÔI — tôi lại kể sai cơ chế jsdom

Brief tôi viết: *"jsdom KHÔNG có phát media: `play`/`pause` không được cài đặt **và `currentTime` có thể không đặt được**"*.
**Vế `currentTime` SAI.** Đo được: **jsdom 30.1.1 CÓ setter thật** cho `HTMLMediaElement.prototype.currentTime`
(`{get,set,enumerable,configurable}`; đặt `3` đọc lại `3`; `fireEvent.timeUpdate` thấy **đúng giá trị đó**) ⇒ bài "dây nối"
bơm **vị trí phát THẬT**, **không** cần `defineProperty`.
**Cái THẬT SỰ không hiện thực:** `play()`/`pause()` (log `Not implemented`, `play()` trả **`undefined`** chứ không phải
`Promise`), `duration = NaN`, `paused` **luôn `true`**. Hai phương thức đó bị **thay bằng spy trong `describe`**, **trả lại
trong `after`**, và **chính giới hạn đó được GHIM bằng một bài test trong repo** — làm đúng yêu cầu "khai rõ là giới hạn của jsdom".

⇒ **LUẬT: đừng nói "jsdom không làm được X" như một khối.** Hãy **đo TỪNG PHẦN** của X.
Đây là **lần thứ TƯ** trong giai đoạn một **cơ chế** bị kể sai (sau `npm i`↔named pipe, nguồn của `9 type`, jsdom↔`0px`) —
và lần này là **của tôi**. **Cơ chế là thứ phải đo, không phải thứ được suy ra từ tên thư viện.**

### 3. ✅ Luật "ghim LUẬT CSS" (ERRATA #15 mục 3) đã được ÁP DỤNG và CHỨNG MINH

Đo được: `[T7] HINH THUC: LUAT CSS … ✖ DO` trong khi **bảy bài chỉ ghim `className` VẪN XANH** ⇒ phép đo cũ **MÙ**,
và bài ghim luật **không rỗng** (đúng chuẩn hai vế của ERRATA #11 mục 2).
Luật thật đã thêm vào `app.css` (+101 dòng, CRLF): `.tp__timecode{font-family:var(--font-mono)}`,
`.tp__track{position:relative}`, `.tp__readhead{background:var(--signal)}`.
**Token mồ côi: 13 → 8** (5 token nay có người dùng: `--dur-1`, `--ease-1`, `--fs-note`, `--panel-1`, `--panel-3`).

### 4. ⚠️ `app.css` lại NGOÀI File list — lần thứ HAI liên tiếp

Task 6 và Task 7 **đều** phải sửa `app.css` mà **không** task nào được giao nó. ⇒ **Luật: bất kỳ task nào thêm HÌNH THỨC
đều phải liệt kê `frontend/src/styles/app.css` trong Files** (và `tokens.css` nếu chạm token). Đã vá Files của Task 7.

### 5. Nợ và điều chỉnh của Task 7

- **`src/lib/playback.ts` (+test)** được thêm **ngoài** Files để hàm thuần chạy được bằng `node:test` thường ⇒ **Files của
  Task 7 đã được vá** cho khớp.
- **⚠️ TRONG APP, THANH TRANSPORT LÀ TRẠNG THÁI RỖNG:** **chưa có đường CHỌN KÊNH** ⇒ `sourceId = ui.channelId = null`,
  `translationId = null`, `segments = []` ⇒ **nút phát VÔ HIỆU**, **không `src`**, **ba nút xuất không `href`**.
  Mọi khẳng định về thanh này hiện đến từ test truyền prop. ⇒ **Nợ: đường CHỌN KÊNH** (và nó chặn cả Task 6 lẫn 7 khỏi
  việc render dữ liệu thật).
- **Tiến bộ:** `App` nay dùng **`useReducer(reduce, initialState)`** — **người gọi THẬT đầu tiên** của reducer Task 4 —
  và nối `ui.currentSegment` vào `EditScreen`.
- **`T1` của brief MƠ HỒ:** nó chạy cả hai chiều (một thành `T10`). ⇒ **Luật: mutation phải được viết sao cho CHỈ CÓ MỘT
  cách hiểu**; nếu không, implementer phải tự chia thành hai mutation và nói ra.
- **`T4` giết 3 bài, không phải 1** (cả ba đều lấy vị trí phát từ chính listener) — **đúng**, không phải "giết nhầm":
  điều bắt buộc là **bài ĐỊNH giết phải đỏ**, và phải **nói rõ** nếu giết thêm.

## ⚠️ ERRATA #17 — Task 7 ĐÓNG (`PASS`) + HAI BẪY PHƯƠNG PHÁP mới cho mọi vòng sau

Task 7 **ĐÓNG**: review độc lập cho **`PASS`, 0 Critical / 0 Important / 5 Minor**. Nó **tự dựng lại** backend thật
(**cổng 8622**, DB scratch riêng, WAV thật 64 044 B — **sha256 trùng khít** tệp của implementer, `8731812716b414517…`),
tái lập **cả ba** ca `Range` + **`sha256(thân 206) == sha256(100 byte đầu)`**, và **`git diff --quiet HEAD -- frontend` EXIT=0
sau TỪNG mutation**.

**Hai phép đo của review đáng chép vào cách làm:**
- **V2 hai chiều:** xoá khai báo `background: var(--signal)` của `.tp__readhead` ⇒ `pass 103 / fail 3`, **ĐỎ đúng 1 bài**
  (bài `HINH THUC: LUAT CSS`), **8 bài chỉ ghim `className` VẪN XANH** ⇒ phép đo cũ **MÙ**. Gỡ `className="tp__readhead"`
  ⇒ ĐỎ **2** bài (`DAU DOC` + `TIMECODE`, vì `TIMECODE` cũng truy vấn selector đó ở `:417`).
- **V5 đi XA HƠN brief:** nó kiểm route xuất ở **mức HTTP** chứ không chỉ so với hàm —
  `?format=srt&bilingual=0` ⇒ 404, **`?format=pdf` ⇒ 422** (⇒ **tên tham số `format` được backend phân tích THẬT**),
  `bilingual=1` ⇒ 404; route thật `prefix="/api/export"`, `/{translation_id}`, `format: str="srt", bilingual: int=0`.
  ⇒ **Luật: so `href` với chính hàm `exportUrl` là CHƯA ĐỦ** — hàm có thể sai; phải chạm **route thật**.

### 1. ⚠️ BẪY PHƯƠNG PHÁP #1 — `spawnSync` với `stdio:'pipe'` chết **EPERM** trong sandbox

Mọi lệnh `git`/`npm` gọi từ Node phải đi qua **`cmd /c "<lệnh> > <tệp> 2>&1"`** với **`stdio:'inherit'`** và
**`windowsVerbatimArguments: true`**. Không làm thế thì **EPERM** (đúng ranh giới named-pipe đã ghi ở ERRATA #1).
⇒ Trong vòng này **hai lượt driver đầu đã TỪ CHỐI mutate** (không ghi tệp nào) **vì lý do đó** — tức luật
*"witness khớp ≠1 lần ⇒ TỪ CHỐI mutate"* đã hoạt động đúng. **Nhưng nếu bạn không biết bẫy này, bạn sẽ đọc nó là
"mutation sống sót" GIẢ.** ⇒ Ghi vào brief của T8–T13.

### 2. ⚠️ BẪY PHƯƠNG PHÁP #2 — `git show HEAD:<path>` trả **LF**, còn worktree là **CRLF**

⇒ `Buffer.equals(<worktree>, <"git show" output>)` cho **`false` HỢP LỆ** — **không phải** dấu hiệu tệp bị hỏng.
**Bằng chứng byte-exact ĐÚNG là:** `git hash-object <worktree> == git rev-parse HEAD:<path>`.
⇒ Đây là **chi tiết thứ ba** của cùng một cái bẫy `core.autocrlf` (ERRATA #8 mục 1, #13 mục 1):
**`git diff` sạch dù byte khác; `git diff` mù với tệp chưa track; và `git show` không so byte được với worktree.**

### 3. Nợ Task 7 (5 Minor — ghi nhận, chưa sửa)

- **`M5` (quan trọng nhất cho tương lai):** `viTriPhat` **cục bộ** trong `Transport` **KHÔNG reset khi đổi kênh**.
  Hôm nay **không với tới được** (chưa có đường chọn kênh), nhưng **sẽ thành lỗi thật** khi **đường CHỌN KÊNH** được làm.
  ⇒ **Nhớ khi giao task "chọn kênh".**
- **`M3`:** bài `GIOI HAN CUA JSDOM` chỉ đo **`play()`**, **không** đo `pause()`; và việc **hoàn nguyên spy là THỦ CÔNG** —
  lưới `guardGlobalLucThoat` **không phủ** `HTMLMediaElement.prototype`. Hôm nay **0 suite khác** chạm `play`/`pause`,
  nên không nhiễm chéo; **nhưng** suite nào sau này chạm thì sẽ nhiễm. ⇒ Cân nhắc **mở rộng lưới guard** cho prototype.
- **`M4`:** `<a>` không `href` + `aria-disabled` ⇒ trạng thái "vô hiệu" hiện **chỉ bằng thị giác** (quan sát a11y).
- **`M1`:** báo cáo §4 ghi *"7 bài"* nhưng **liệt kê 8 tên** (đo được: **8** vẫn xanh — nội dung đúng, **số lệch 1**).
  Lại là **một con số không kèm lệnh sinh ra nó** (ERRATA #4 mục 7).

### 4. Vẫn CHƯA chứng minh — đừng ghi "đã kiểm"

**seek/phát trong trình duyệt THẬT** (bất khả ở môi trường này); **layout/CSS/vị trí vẽ ra** của đầu đọc, màu amber,
chiều cao thanh (jsdom không có layout/CSS); **đường THÀNH CÔNG `200` của `/api/export` kèm thân phụ đề**
(DB scratch **không có bản dịch**); **nội dung bundle/trang chạy thật** (`build` chỉ xác nhận EXIT=0 + dòng `created dist`).

## ⚠️ ERRATA #18 — Task 8 DỪNG ĐÚNG LÚC: **CPS và cột phải KHÔNG có nguồn HTTP** + một lỗi 500 + một task bị THIẾU

Implementer Task 8 **dừng trước khi viết dòng mã nào** theo §2 của brief và báo cáo. Đó là **hành vi đúng** — brief đã
gài đúng cơ chế. Ba phát hiện, đều **đo được**:

### 1. ❌ `plan:1771` SAI: `qa_issues` KHÔNG tới được HTTP

- `stale` ✅ **CÓ**: `routes_translations.py:171` `_summary(row, stale=is_stale(...))`, thân thật có `"stale": false`.
- **Chuỗi `cps:` CÓ thật được sinh** — `mt_qa.py:92` = `f"cps:{s.i}={len(text)/duration:.1f}>{limits.max_cps}"`
  (**có cả số lẫn ngưỡng**), ghi vào DB (`translate.py:203`), đọc lại **chỉ vào domain object** (`sqlite_repos.py:224`).
- **Builder JSON DUY NHẤT** của bản dịch là `staleness.py:45-54` = **9 khoá**, **KHÔNG** có `qa_issues`.
- **Quét MỌI route GET: `qa_issues` có trong thân? `False` ở 12/12.**
⇒ Câu của plan *"`qa_issues` mang tiền tố `cps:` … tới `GET /api/translations`"* là **SAI** (lần thứ **MƯỜI SÁU** một
mệnh đề của plan/brief bị đo là sai).

### 2. ❌ Cột PHẢI cũng không có nguồn thật

`segments` của bản dịch **không có trong bất kỳ JSON nào**; **KHÔNG tồn tại route `GET /api/translations/{id}`**.
Đường HTTP **duy nhất** mang văn bản dịch là `GET /api/export/1?format=srt` ⇒ thân SRT **đã render**, **không** phải
segment có cấu trúc, và `endpoints.ts` không có wrapper.
Nguồn CPS **duy nhất** tới được HTTP là `routes_transcripts.py:121-137`, và nó đo **đoạn GỐC**
(`reading_cps(seg.text, seg.start, seg.end)`) — **không** đo được một hàng `translations`.
⇒ **2/4 mục "Produces" — trong đó có CỘT CPS — không có nguồn thật.** Không phải "thiếu một phần": **cột phải rỗng thì
hết là màn Đối chiếu.**

### 3. 🐞 LỖI 500 ĐO ĐƯỢC (kèm đối chứng)

`GET /api/transcripts/{id}/readability` **500** khi transcript có segment **thời lượng `<= 0`**:
`readability.py:15-16` trả **`inf`** → `routes_transcripts.py:134` cho lọt vào `too_fast` →
**`ValueError: Out of range float values are not JSON compliant`**.
**Đối chứng** cùng app, không có segment 0 giây ⇒ `200 {"threshold":20.0,"too_fast":[]}`.
**Trớ trêu đo được:** `qa_translation` **đã xử đúng** ca này (`mt_qa.py:83-90`, `nowindow`) — tức **nguồn CPS BỀN duy nhất
lại là nguồn KHÔNG được expose**, còn **nguồn được expose thì SẬP**.

### 4. ⚠️ MỘT TASK BỊ THIẾU TRONG PLAN: **ĐƯỜNG CHỌN KÊNH**

Đo được: `selectChannel` **KHÔNG được dispatch ở đâu trong mã sản phẩm**; `App` truyền `transcript={null}`,
`sourceId = ui.channelId = null`, `translationId = null`, `segments = []`.
⇒ Tasks 6, 7, 8 **đều render TRẠNG THÁI RỖNG** vì **không task nào sở hữu việc chọn kênh**. Đây là **lỗ trong plan**,
không phải lỗi của implementer nào.
⇒ **Phải giao tường minh một task "CHỌN KÊNH"** trước khi T9–T11 có thể render dữ liệu thật (và trước Task 12).
**Kèm nợ `M5` của Task 7:** khi có chọn kênh thì **`viTriPhat` của `Transport` phải được reset**.

### 5. QUYẾT ĐỊNH: **chọn A — thêm "Step 0: BACKEND" cho Task 8**

Đúng khuôn **plan đã dùng cho Task 9 Step 0** (*"thêm MỘT endpoint chỉ-đọc, vì §12.3 đòi thứ API chưa phục vụ được"*).
Phạm vi **hẹp**:
1. **Sửa lỗi 500** của `readability` (segment thời lượng `<= 0`) — theo đúng cách `mt_qa.py:83-90` (`nowindow`) đã làm,
   và **có test** (segment 0 giây ⇒ `200`, không `inf`).
2. **Thêm ĐÚNG MỘT endpoint chỉ-đọc** để §4.3 có nguồn thật. Yêu cầu:
   - nó phải trả **`segments` của BẢN DỊCH** (để dựng cột phải) **và** dữ liệu CPS **có cấu trúc**;
   - **client KHÔNG được parse một chuỗi hiển thị để lấy một con số nó hiển thị** ⇒ expose **SỐ**
     (`cps`, `max_cps`, cờ vượt ngưỡng) chứ không chỉ chuỗi `"cps:3=45.2>20"`;
   - 404 khi không có, theo **đúng quy ước route hiện có** (đọc `routes_translations.py` để bắt chước);
   - **client KHÔNG tính lại CPS** (spec §2) — nếu endpoint không đủ thì đó là **lỗi của endpoint**, không phải lý do tính ở client.
3. **Test backend + baseline:** **ĐO baseline pytest trên NHÁNH NÀY TRƯỚC**, rồi **không được giảm** (ledger ghi baseline
   của `gd3-frontend` là **821 passed / 13 deselected**; **đo lại, đừng tin con số đó**).
4. **Files phải được mở rộng** cho phần backend (`backend/app/api/...`, `backend/app/domain/readability.py`, test),
   **và** `frontend/src/api/types.ts` + `endpoints.ts` cho wrapper/type mới, **và** `frontend/src/styles/app.css`.
⇒ **Task 8 nay CHẠM BACKEND.** Đó là hệ quả **bắt buộc** của việc §12.4 đòi thứ API chưa phục vụ — và **giống hệt**
cách Task 9 đã được xử lý, nên **không phải mở rộng phạm vi tuỳ tiện**.
**Phương án B** (giữ nguyên backend) bị **loại**: nó phải ghi thẳng **§12.4 KHÔNG ĐẠT**, và "cột CPS" khi đó chỉ là CPS
của **bản GỐC** — không phải thứ tiêu chí yêu cầu. **Phương án C** (hoãn) cũng **không giải quyết gì**: hoãn Task 8
**không** tạo ra nguồn dữ liệu.

## ⚠️ ERRATA #19 — Task 8 ĐÓNG (`PASS`) + RULING về glyph `⚠` + bốn lỗi nhỏ phải vá

Task 8 **ĐÓNG**: review độc lập **`PASS`, 0 Critical / 3 Important / 10 Minor**, V1/V2/V5 đạt bằng phép đo của chính nó.

### 1. ✅ Cửa sổ đo là cửa sổ **NGUỒN** — chứng minh được **CẢ HAI CHIỀU**

Nó seed **đoạn NGUỒN `2.0→5.0` (3,0 s)** và **đoạn DỊCH `10.0→11.0` (1,0 s)**, backend thật ở cổng **8631**:
`{"i":1,"chars":40,"window":3.0,"cps":13.3,"max_cps":21.0,"over":false}` ⇒ **`window = 3.0` = độ dài NGUỒN**;
dùng cửa sổ **DỊCH** sẽ ra **`40.0`** và **lật `over` sang `true`**. Và chiều ngược lại được chứng minh bằng mutation
`BM3w` (đo trên cửa sổ bản dịch) ⇒ **2 bài đỏ**. Ca cả-hai-cửa-sổ-0 ⇒ `cps: null` (**không** `Infinity`, **không** bịa `0.0`).

### 2. ✅ `C2b`: cả hai vế được tái lập **đúng con số**

Reviewer **dựng lại bộ test CŨ (116 bài)** bằng cách ẩn `CompareScreen.test.tsx` khỏi glob + bản sao đã cắt đúng khối
`it("… dung bien")` (phục hồi byte-exact): bộ CŨ + `C2b` = `116/114/2` **y hệt lượt sạch** ⇒ **phép đo cũ MÙ**;
bộ CUỐI = `117/114/3` với **đúng một** bài đỏ `co 'over' cua backend thang phep so cua client o dung bien`.
`M5` (xoá **LUẬT CSS** giữ class `is-over`) giết **đúng** bài ghim luật trong khi **10 bài chỉ ghim class vẫn xanh**.

### 3. ⚠️ HAI ĐỊNH NGHĨA CPS **NGƯỢC NHAU TRÊN CÙNG DỮ LIỆU** — nợ THẬT, phải có task sở hữu

`readability.reading_cps` (**không** đếm khoảng trắng, `CPS_WARN=20.0`, đoạn **GỐC**) vs `mt_qa.cps_row`
(**có** đếm khoảng trắng, `max_cps=21.0`, đoạn **DỊCH**, cửa sổ **NGUỒN**):
cùng một chuỗi **82 ký tự / cửa sổ 4,0 s** ⇒ **`20.50 over=True`** vs **`20.50 over=False`**.
Con số của cùng một dòng có thể lệch **90,9 %** (**11,0** vs **21,0**).
Hôm nay chưa lộ vì **`/readability` có 0 caller ở frontend**; **ngay khi EditScreen nối nó, hai màn sẽ nói NGƯỢC NHAU
về cùng một dòng.** ⇒ **Phải giao tường minh** (task CHỌN KÊNH, hoặc task riêng) — chọn **MỘT** định nghĩa, hoặc nếu
hai định nghĩa là **cố ý** (nguồn vs dịch) thì **ngưỡng và cách đếm khoảng trắng phải thống nhất** và **phải ghi ra**.

### 4. ❌ HAI LỜI KHAI SAI TRONG MÃ SẢN PHẨM (phải sửa)

- **`routes_translations.py:188-190` khẳng định TUYỆT ĐỐI** *"… KHÔNG THỂ lệch nhau"*, nhưng đo được nó **chỉ đúng với
  `QaLimits()` MẶC ĐỊNH**: `schema.py:30-45` **không lưu ngưỡng**, `main.py:214` **không truyền `limits=`**.
  ⇒ Nếu ai truyền limits tuỳ biến thì docstring **sai**. (ERRATA #15 mục 2: lời giải thích cơ chế cũng là lời khai.)
- **Docstring kể SAI cơ chế lỗi 500:** `json.dumps({'cps': inf})` trả **`{"cps": Infinity}`** và **KHÔNG ném**;
  `ValueError` đến từ **`allow_nan=False` của `starlette.responses.JSONResponse.render`**.

### 5. ⚠️ Hợp đồng route MỚI **không được ghim ở phía client**

`contract.test.ts` có **0 hit** cho `/translations/{id}`, `TranslationDetail`, `TranslationCps`, `cps`, `max_cps`.
Ba interface mới **viết tay**, chỉ **backend** ghim ⇒ một lần **trôi shape** sẽ để **cả pytest lẫn `npm test` XANH**.
⚠️ **ĐÍNH CHÍNH (ERRATA #20 mục 2): câu "chỉ backend ghim" là QUÁ MẠNH.** Đo lại: `backend/tests/test_api_translations.py`
**ĐÃ ghim** `cps` là `float`, `max_cps == 21.0`, `over is True/False`, `chars`, `i`, `segments[].text`/`i`, `stale`, `404`.
Backend **chỉ mù** ở **`cps.max_cps` tầng TRÊN**, **`cps.rows[].window`**, **`segments[].start`/`end`** — và ca contract
mới nhắm **đúng ba chỗ đó**.
⇒ **Phải thêm ca contract**, và mốc tự nhiên là task **CHỌN KÊNH** (nơi `getTranslation` có người gọi) — **hoặc ngay bây giờ**.

### 6. Bốn Minor phải vá (đã giao vòng sửa)

- **`types.ts:14` trôi số:** khai **33/23**, **đo nay 36/26** (3 interface mới không cập nhật) — **đúng thứ ERRATA #4 mục 7 cấm**.
  ⇒ Sửa **bằng LỆNH**, hoặc bỏ số tuyệt đối.
- **`test_backend_readme.py:78-84`** còn ghi **`821/834`** sau khi bump **830/843** ⇒ **số cũ trong chính tệp ghim số**.
- **M3:** hai khoá cùng tên **`chars`** mang **hai nghĩa** (**21** vs **11** cho cùng một dòng) ⇒ đổi tên hoặc ghi rõ.
- **M4 — LỖ HỔNG ĐỘ PHỦ MỚI (reviewer tự tìm):** bỏ `is-pinned` ở **HÀNG ĐẦU CỘT** ⇒ `117/115/2` **SỐNG SÓT**
  (luật `grid-template-columns` 4 cột **không áp** cho đầu cột) ⇒ phải có bài ghim.

### 7. ⚠️ RULING: **DÙNG glyph `⚠`** — và PLAN này đã tự mâu thuẫn

Reviewer đo được: **spec UI §4.3 nguyên văn** = *"Dòng vượt ngưỡng đọc có `⚠` màu amber."*;
**`grep -i emoji` trên SPEC = 0** ⇒ **spec KHÔNG cấm emoji ở đâu cả**;
lệnh cấm nằm ở **PLAN** (`2026-09-26-frontend-workspace-2.md:1010` — *"- **Không emoji** trong code/nhãn/alt."*),
và chính plan khai luật đó *"không mâu thuẫn spec UI"*.
⇒ **PLAN tự mâu thuẫn**, và implementer đã **gán sai tài liệu** khi nói *"cùng tài liệu cấm emoji"*.
**RULING: spec UI là nguồn có thẩm quyền về HÌNH THỨC** (chính plan đã chốt thế, và §4.3 **đòi** glyph) ⇒ **phải render
glyph `⚠` trong dòng vượt ngưỡng**, **giữ thêm** mốc amber ở lề + `data-over-cps` (chúng phục vụ **tiếp cận**, §7).
Luật "không emoji" của plan **vẫn hiệu lực cho mọi thứ KHÁC** (không trang trí, không icon cảm xúc); nó **nhường** cho
một glyph **được spec chỉ định làm dấu hiệu nội dung**. ⇒ Đã vá dòng 1010 để ghi rõ **ngoại lệ này**.

### 8. Review KHÔNG tái lập được một phần lời khai (ghi đúng mức)

**5 lượt mutation backend đầu** chạy khi guard README còn đỏ. Reviewer **tái lập được CƠ CHẾ**
(mutation README `830→821` cho **đúng nguyên văn** `E assert (830, 13) == (821, 13)` + `1 failed, 4 passed`)
và **tái lập được HAI LƯỢT SẠCH** (`BM4r`/`BM7r`: `1 failed, 829 passed`, đúng 1 bài, **không** có guard trong danh sách đỏ) —
nhưng **KHÔNG** tái lập được **con số tổng của chính 5 lượt đó** (trạng thái trung gian **không có trong git**) ⇒ ghi là **chưa đo được**.

## ⚠️ ERRATA #20 — Task 8 vòng sửa #1b (`71f322b`): **`Buffer.equals` KHÔNG TỒN TẠI**, và lời khai của tôi về "backend mù" là QUÁ MẠNH

Vòng sửa #1b xong (**ba** việc còn lại của vòng #1): `npm test` = `tests 120 / suites 16 / pass 118 / fail 2 / cancelled 0`
EXIT=1 (117 → 120), pytest **`830 passed, 13 deselected`** EXIT=0 (**không đổi** ⇒ không phải sửa `backend/README.md`),
`typecheck` 0, `build` 0, byte-exact cả **bốn** tệp. Nó bác **hai** chỗ của brief tôi:

### 1. ❌ `Buffer.equals(baseline)` — API **KHÔNG CÓ THẬT**, và brief của tôi đã dùng nó suốt nhiều vòng

`Buffer` **không có** static `equals`. Chạy driver **nguyên văn** của tôi ném
**`TypeError: Buffer.equals is not a function`**. Agent in **cùng sự thật** bằng **`readback.equals(baseline)`** —
đó là **method trên instance**, mới là API thật.

⇒ **ĐÍNH CHÍNH CHO MỌI BRIEF TỪ NAY:** câu đúng là **`readback.equals(baseline) === true`**
(hoặc `Buffer.compare(a, b) === 0`). Câu *"`Buffer.equals(baseline) === true`"* mà tôi viết từ **ERRATA #8** trở đi
**gọi tên một API không tồn tại** — mọi agent trước đã **tự dịch** nó mà không ai báo. **Đây là lỗi thứ MƯỜI BẢY của tôi**,
và nó thuộc loại **nguy hiểm nhất**: một **thủ tục** sai chạy qua **nhiều vòng** mà không ai phát hiện, vì người sau
**đoán được ý** và làm đúng. ⇒ **Luật: khi một brief đưa LỆNH/API cụ thể, implementer phải CHẠY THỬ nó; nếu nó không
tồn tại thì BÁO, đừng lặng lẽ thay bằng thứ tương đương.** (Lần này đã báo — tốt.)

### 2. ❌ ERRATA #19 mục 5 QUÁ MẠNH: backend **CÓ** ghim phần lớn shape của route mới

Tôi viết *"shape của route mới **chỉ** được backend ghim"* như thể backend mù hoàn toàn. **Đo lại thì không:**
`backend/tests/test_api_translations.py` **ĐÃ ghim** `isinstance(row["cps"], float)`, `row["max_cps"] == 21.0`,
`row["over"] is True/False`, `row["i"]`, `row["chars"]`, `segments[].text`/`i`, `stale`, và **404**.
Đổi `cps` thành **chuỗi** hay đổi tên **`max_cps` ở tầng HÀNG** làm **pytest ĐỎ**.
**Chỗ backend THẬT SỰ mù** (`grep` = **0 hit**): **`cps.max_cps` ở tầng TRÊN**, **`cps.rows[].window`**,
**`segments[].start`/`end`**. Agent chọn mutation **đúng ba chỗ đó** ⇒ **phép đo của nó CHẶT HƠN lời khai của tôi**.
**Nếu nó làm theo trực giác của brief tôi** (đổi `cps` thành chuỗi) thì **pytest cũng đỏ** ⇒ **không chứng minh được gì**
về khoảng trống phía client. ⇒ **Luật: trước khi khẳng định "chỉ X ghim nó", hãy GREP xem X ghim tới đâu.**

**Và giá trị thật của ca contract mới được chứng minh bằng CÙNG một trạng thái mutate:**
`routes_translations.py`: `"window": r.window` → `"cua_so": r.window` ⇒ pytest **`35 passed`** (**MÙ**),
`contract.test.ts` **ĐỎ** (`tests 11 / pass 8 / fail 3`). Y hệt với `"max_cps"` → `"nguong"` và với việc **bỏ `start`**
của `segments`. ⇒ Client contract **thêm phạm vi thật**, không phải hình thức.

### 3. ✅ Lỗ hổng độ phủ đầu cột: CẢ HAI VẾ

Bộ **CŨ** + mutation bỏ `is-pinned` ở **HÀNG ĐẦU CỘT** ⇒ `117/115/2` **SỐNG SÓT** (y hệt lượt sạch).
Bộ **MỚI** ⇒ **`120/117/3`**, giết **đúng một** bài `GHIM: DAU COT cung nhan is-pinned…`.
⚠️ **ĐÍNH CHÍNH (ERRATA #21 mục 2):** tôi đã viết **`119/116/3`** ở đây — **KHÔNG tái lập được** trên cây đã commit;
đo lại là **`120/117/3`**, và con số cũ còn **mâu thuẫn nội bộ** với baseline sạch `120/118/2`. **Chất** ("giết đúng một bài")
**vẫn đúng**; chỉ **con số của tôi** sai.
Mutation thứ tư (rút `.cmp__dau.is-pinned,` khỏi `app.css`) cũng giết **đúng một** bài đó trong khi bài `HINH THUC`
cũ **vẫn xanh** ⇒ **luật CSS và class được ghim RIÊNG**, đúng ERRATA #15 mục 3.

### 4. ✅ Glyph `⚠` theo spec UI §4.3 — ĐỎ trước khi sửa

`AssertionError: dong VUOT nguong phai co glyph canh bao, dang co: 45.2CPS` ⇒ đã render `⚠` trong ô CPS,
**giữ** mốc amber ở lề + `data-over-cps`, **không** thêm emoji nào khác, khẳng định trên `textContent`
(**không** đưa DOM node sống vào `assert`). Mutation bỏ glyph giết **đúng một** bài.

### 5. ⚠️ BẪY: `pytest -q` **MẤT DÒNG TỔNG KẾT** — nhưng **KHÔNG phải** "môi trường này"

Log kết thúc ở `-- Docs: …` và **KHÔNG** có `35 passed`, **dù EXIT=0**. ⇒ **ĐỪNG đọc "thiếu dòng tổng kết" là
"chưa chạy xong"** — hãy **đọc EXIT**.
⚠️ **ĐÍNH CHÍNH (ERRATA #21 mục 1):** tôi gán nguyên nhân cho *"môi trường này"* — **SAI**. Nguyên nhân thật là
**`-q` trên CLI + `addopts = -q` trong `pytest.ini` = `-qq`**, và **`-qq` chính là thứ pytest dùng để BỎ dòng tổng kết**.
⇒ **Cách đúng: ĐỪNG truyền `-q`** (`pytest.ini` đã có sẵn). Đây **không** phải chuyện của sandbox, và nó sẽ **không**
tự khỏi ở môi trường khác.
(Cùng họ "đầu ra không chứa thứ bạn chờ": ERRATA #10 mục 8 — `typecheck` **không** kiểm tệp test.)

### 6. Hai điều nhỏ khác từ vòng này

- **"MỘT backup cho MỘT TỆP"**: agent **không tạo tệp backup nào** — nó giữ baseline **trong RAM** dạng Buffer byte-exact,
  `finally` ghi lại rồi in lại `equals === true`. **Tốt hơn** brief của tôi (không thể để rác lại).
- **Ba cảnh báo `LF will be replaced by CRLF` là VÔ HẠI:** hệ quả `core.autocrlf=true`; hai tệp TSX toàn LF,
  hai tệp kia toàn CRLF, **không tệp nào TRỘN**. ⇒ Cảnh báo đó **không** phải dấu hiệu tệp hỏng.
- **Không đo được (ghi đúng mức):** **màu amber thật** của glyph trong trình duyệt (jsdom **không** layout/CSS) —
  chỉ ghim được **glyph có trong `textContent`** + **luật CSS tồn tại**; và **nhánh `200` trên DB repo**
  (`data/app.db` vẫn rỗng — việc của Task 12). Nhánh 200 **đã** được đo trên **backend riêng ở 8621 với DB gieo scratch**
  (ngoài repo) ⇒ **cả hai vế tất định**; `after` chỉ tắt pid của chính nó **và chứng minh cổng thôi trả lời**.

## ⚠️ ERRATA #21 — TASK 8 ĐÓNG HOÀN TOÀN (`PASS` 0/0/5) — và ba món nợ TÀI LIỆU phải biết

Re-review vòng sửa Task 8: **`PASS`, 0 Critical / 0 Important / 5 Minor** (V1, V2, V5 đạt bằng phép đo độc lập).
**Task 8 xong.** Nó xác nhận **chiều ngược** của `ERRATA #20` mục 2 (mutation ở chỗ backend **CÓ** ghim ⇒ pytest **ĐỎ**:
`"cps"` → `str(round(...))` cho `3 failed, 32 passed`; `"max_cps"` tầng HÀNG → `"nguong"` cho `2 failed, 33 passed`
`KeyError: 'max_cps'`), và xác nhận danh sách **"backend mù đúng ba chỗ"** bằng grep **0 hit** kèm **đối chứng dương**
(`["cps"]["rows"][0]` **4 hit**; `row["max_cps"]/["chars"]/["over"]` **5 hit**; `segments[0]["i"]/["text"]`).

### 1. ⚠️ NỢ LỚN: tên API **SAI** đã lan ra **108 dòng / 32 tệp** trong ledger

Grep `.superpowers/sdd/2026-09-26-frontend-workspace-2/` thấy **108 dòng / 32 tệp** vẫn **khai** `Buffer.equals`
(**kể cả brief của chính tôi**, `task-8-report.md`, `review-task-4/5/6/7-report.md`, và **báo cáo vòng sửa này**
— tự mâu thuẫn: `:133` nói driver in `Buffer.equals(readback, baseline)` trong khi `:157` khai API đó **không tồn tại**).
⇒ **ĐỪNG sửa 108 dòng đó** — chúng là **bản ghi lịch sử**, và sửa chúng là viết lại lịch sử (đúng thứ luật cấm).
**Nhưng:** bất kỳ ai đọc lại các báo cáo đó phải biết **tên API trong đó là SAI**, còn **phép đo có thể vẫn ĐÚNG**
(các agent đã tự dịch sang `readback.equals(...)`). **Tên đúng từ nay: `readback.equals(baseline) === true`.**
⇒ Bài học: **một thủ tục sai tên, nếu đủ dễ đoán, sẽ sống rất lâu** — nó chỉ lộ ra khi có người **chạy nguyên văn** nó.

### 2. Ba Minor TÀI LIỆU còn nợ (ghi nhận, KHÔNG sửa vòng này)

- **`contract.test.ts:705`** — comment nói *"khoá đã đổi tên để phân biệt với `chars` của `mt_qa`"*, nhưng trong ngữ cảnh
  **`cps.rows[]`** thì khoá **CHÍNH LÀ `chars` của `mt_qa`** (**không** đổi tên); chỗ đổi tên là route **`readability`**.
  Comment này **ngược** với docstring **ĐÚNG** ở `mt_qa.py:120-122`. ⇒ Cùng lớp lỗi **"comment kể sai cơ chế"**
  (ERRATA #15 mục 2) — lần này nằm trong **tệp test**. **Sửa ở task kế tiếp chạm tệp đó.**
- **"`types.ts` bỏ MỌI số tuyệt đối" không đúng nghĩa chữ:** còn **`33`/`36`** ở **dòng 16** (kể **lịch sử** — chấp nhận được,
  vì nó kể *"tệp này đã nói dối bằng số bốn vòng liền"*, không phải một khẳng định hiện tại) và **"cộng hai bài 422"** ở **dòng 49**.
  ⇒ Câu **mô tả** việc đã làm là **quá mạnh**, không phải việc làm sai.
- **`U+23F8 ⏸`** có sẵn trong **COMMENT** ở `frontend/src/shell/QueueZone.tsx:21` — **không render**, **không** thuộc hai
  commit của Task 8. ⇒ Nợ nhỏ: nếu luật "không emoji" áp cho **cả comment**, thì đây là chỗ vi phạm; nhưng nó **không**
  tới tay người dùng. **Quyết định: để nguyên** (comment không phải UI), và ghi ra để người sau không ngạc nhiên.

### 3. Điều re-review **KHÔNG** đo được (ghi đúng mức — không suy luận thay)

- **Màu amber THẬT** của glyph trong trình duyệt (**jsdom không có layout/CSS**) — nó **cũng** không đo được; chỉ ghim được
  **glyph có trong `textContent`** + **luật CSS tồn tại**.
- **Nhánh `200` trên `data/app.db` THẬT** (vẫn **rỗng** — việc của **Task 12**). Nhánh 200 **chỉ** đo trên
  **backend riêng ở 8621 + DB gieo scratch**.
- **Toàn bộ 830 bài trên cây ĐÃ MUTATE** — chỉ chạy **tệp sở hữu route** (35 bài). Cơ sở hợp lý: **52** tệp test backend,
  chỉ `test_api_translations.py` gọi route chi tiết qua HTTP. ⇒ Chấp nhận, nhưng **phải nói ra**.
- **CPS của job MT thật**; `npm run e2e`/Playwright (**bị cấm**); khoảng `4555b43..HEAD`.
- Và reviewer **tự khai** một con số rác của **driver của nó** (`chuoi MOI xuat hien 13155 lan` — nó đếm **chuỗi rỗng**),
  **không** phải số đo. ⇒ **Đúng cách: gọi rác là rác.**

## ⚠️ ERRATA #22 — Task 9 (`b223ab4` + `4c357d1` + `48a84b4`): **`approved=false` có HAI nghĩa**, và một lỗi thật tìm ra SAU commit

Task 9 xong (3 commit): pytest **`835 passed, 13 deselected`** EXIT=0 (baseline **830** → +5), `npm test`
**`tests 128 / suites 17 / pass 126 / fail 2 / cancelled 0`** EXIT=1, `typecheck` 0, `build` 0, **12 lượt mutation** đủ bốn thứ.

### 1. ✅ `P3` được chứng minh bằng SỐ ĐO MẠNH NHẤT CÓ THỂ: **preview == kết quả ghi thật**

Trước Step 0, **gọi THẬT** (backend thật + DB scratch, cổng 8622):
`GET /api/glossary/affected -> HTTP 405 {"detail":"Method Not Allowed"}` — **405 chứ KHÔNG phải 404**,
vì `/{term_id}` **đã nuốt** `affected` (⇒ đúng cái bẫy thứ tự khai báo mà brief lo). Sau Step 0:
`200 {"affected":[1]}`. Ca **bỏ duyệt** (cùng term, cùng translation, chỉ khác `approved=false`) ⇒ **cũng** `{"affected":[1]}`.
Và **một `PATCH` THẬT trả `affected: [1]` — BẰNG ĐÚNG con số xem trước.**
⇒ Đây là bằng chứng mạnh nhất có thể cho `P3`: **số xem trước == số mà lần ghi thật trả**, không phải "trông hợp lý".

**Mutation `G2`** (lọc hàng đang sửa khỏi `old` — **đúng cái `M-3` đã bác**) giết **ĐÚNG** bài
`test_affected_preview_agrees_with_the_write_when_the_term_is_UNAPPROVED` (`1 failed, 834 passed`), phục hồi
`readback.equals(baseline) === true` + sha256 khớp. ⇒ **Đính chính `M-3` nay đã được GHIM**, không chỉ được viết ra.

### 2. 🔴 BÀI HỌC LỚN NHẤT — **`approved=false` có HAI NGHĨA**, và một trong hai **CÓ** ảnh hưởng

Bản đầu của màn hình khoá câu *"Thuật ngữ CHƯA DUYỆT: đổi nó không ảnh hưởng gì"* theo **cờ checkbox**.
**SAI**, vì `approved=false` gồm hai ca **ngược nhau**:
- **(a) nháp MỚI** ⇒ thật sự **không** ảnh hưởng;
- **(b) BỎ DUYỆT một hàng ĐANG được duyệt** ⇒ **GỠ một ràng buộc** ⇒ **CÓ** ảnh hưởng (`{"affected":[1]}`, đã đo).

Đường **(b) CÓ THẬT trong app** (bấm một hàng đang duyệt → bỏ tick), nên màn hình **nói SAI** ngay trước lúc Lưu
⇒ đúng lớp **"nhãn đảo"** của ERRATA #10 mục 9. **Đây là lỗi THẬT, tìm ra SAU khi đã commit tầng frontend** ⇒ commit thứ ba.

**LUẬT CHO T10–T13 (và cho mọi UI chạm "duyệt"):**
- **ĐỪNG bao giờ khoá một lời khẳng định vào GIÁ TRỊ BOOLEAN hiện tại.** Phải hỏi **trạng thái TRƯỚC ĐÓ** của hàng:
  `false` từ **chưa từng duyệt** ≠ `false` do **vừa bỏ duyệt**.
- **Và một câu brief dễ bị đọc sai, phải nói RIÊNG:** *"term chưa có trong DB ⇒ `{affected: []}`"* **ĐÚNG**, nhưng
  **KHÔNG** có nghĩa *"`approved=false` ⇒ luôn rỗng"* — sai khi thuật ngữ **đang** được duyệt.
  **Chính chỗ này làm bản nháp test ĐẦU của implementer sai, rồi thành lỗi thật trong UI.**
⇒ Ngoài ra nó còn sửa 3 thứ cùng lúc và **ghim bằng `M11`**: câu chữ *"bỏ duyệt glossary → N bản ghi"*,
**cột "Ảnh hưởng" hiện số CẢ KHI đã bỏ tick**, và hàng vào form bằng **NÚT `Sửa`** thay `<tr onClick>` (**bàn phím tới được**).

### 3. ⚠️ LỆCH ĐƠN VỊ — spec nói "bản DỊCH", route trả id TRANSCRIPT

Spec UI §4.4/§12.3 viết *"số **BẢN DỊCH** bị ảnh hưởng"*, nhưng route trả **id transcript**, và **KHÔNG route nào
trả số bản dịch**. ⇒ UI hiện **đúng đơn vị của route** (*"N bản GHI bị đánh dấu lỗi thời"*), **có bài test ghim đơn vị**,
và **KHÔNG** tự nhân/chia ở client (khuôn Task 8: *"endpoint không đủ thì đó là lỗi của endpoint"*).
**DB gieo có Ý hai bản dịch** cho transcript bị ảnh hưởng ⇒ client tự đếm sẽ ra **2**, route nói **1**, test ghim **1**.
⇒ **NỢ THẬT: muốn nói "bản dịch" thì ROUTE phải trả số bản dịch.** Đừng "sửa" bằng cách đếm ở client.

### 4. Nợ khác của Task 9

- **§4.4 khối dưới ("thuật ngữ xuất hiện ở đâu") KHÔNG LÀM:** `GET /api/transcripts` **cố ý** không kèm `segments`
  ⇒ **không có nguồn HTTP**. `ponytail:` TRẦN + đường nâng cấp (**route occurrences**) đã khai trong doc-comment.
- **`M9` — mutation SỐNG SÓT (lỗ hổng độ phủ ĐÃ KHAI):** bỏ nhánh `glossary` khỏi `App` không bài nào bắt,
  vì **không UI nào dispatch `setMode`** ⇒ không có đường đặt mode, nên **không thể** chứng minh hai vế. (Cùng gốc với
  lỗ thiếu **đường CHỌN KÊNH**.)
- **Token mồ côi 5 → 1:** `--ok`, `--fs-read`, `--row-1`, `--sp-5` nay **có người dùng thật**; **`--sp-6` VẪN mồ côi**.
- **`types.ts` bị sửa NGOÀI Files của brief — CHỈ comment, và đúng:** khối comment khai `AffectedPreview`/`Term`/
  `TermWithAffected` thuộc nhóm *"CHỈ đối chiếu MÃ NGUỒN"*, nhưng nay chúng **ĐÃ có bài soi qua HTTP thật**
  ⇒ để nguyên là **một câu SAI trong mã sản phẩm**.
- **`contract.test.ts:705` VẪN CÒN SAI** (comment kể sai cơ chế đổi tên khoá). Implementer **cố ý không chạm** (brief cho phép):
  hợp đồng tham số của route mới **đã** được ghim bằng **HTTP thật** trong `GlossaryScreen.test.tsx` (bài HỢP ĐỒNG THAM SỐ,
  `G4` giết nó), và thêm khối backend thứ ba chỉ **lặp lại phép đo** mà tốn thêm một tiến trình mỗi lượt `npm test`.
  ⇒ **Quyết định có ghi, không phải bỏ sót.** Sửa comment đó ở task kế tiếp chạm tệp.
- **Ba commit thay vì một-hai** — vì lỗi thật ở mục 2 tìm ra **sau** khi đã commit frontend; nó **từ chối `git reset --soft`**
  (*"đó là viết lại lịch sử"*). Tiền lệ: ERRATA #14 mục 3.
- **Số nền của brief lần này ĐÚNG CẢ HAI** (pytest `830/13`, npm `120/118/2/0`) — implementer **ghi ra** vì các brief trước
  từng sai số. Và nó **đã cập nhật `backend/README.md` (835/13, +826 cho máy thiếu `ffmpeg`) CÙNG khối comment trong
  `tests/test_backend_readme.py`, TRONG CÙNG commit backend** — guard **đã** kêu trước khi bump (`1 failed, 834 passed`).
  `app.css` +209 dòng (478 → 687), **CRLF=687 / LF-only=0** (không tệp nào trộn).

## ⚠️ ERRATA #23 — Review Task 9: **`CONDITIONAL PASS`**, CA THỨ BA của `approved=false` mà bản vá đầu BỎ SÓT

Review độc lập: **`CONDITIONAL PASS`, 0 Critical / 2 Important / 6 Minor** (V1, V4, V5, V6, V7 ĐẠT; **V2 KHÔNG ĐẠT**).

### 1. 🔴 `I1` — CA THỨ BA: **form MỚI + một thuật ngữ ĐANG DUYỆT + bỏ tick** vẫn nói "không ảnh hưởng gì"

Bản vá đầu (`48a84b4`) phân biệt **nháp mới** với **bỏ duyệt** bằng `hangDangSua !== null` — tức nó đòi **đang Sửa một hàng**.
**Nhưng `POST` upsert theo `(lang, term)`**, nên **form MỚI** (`editingId = null`) mà gõ một thuật ngữ **ĐANG ĐƯỢC DUYỆT** rồi bỏ tick
**CHÍNH LÀ bỏ duyệt** — và `dangBoDuyet` **không** nhận ra (vì `hangDangSua === null`), nên màn hình **vẫn** nói
*"CHƯA DUYỆT … không ảnh hưởng gì"*.

**Đo trên màn hình THẬT** (probe render `GlossaryScreen` + backend thật):
- câu xem trước: *"Thuật ngữ CHƯA DUYỆT: đổi nó không ảnh hưởng gì — bản nháp không đi vào prompt, nên không bản ghi nào
  bị đánh dấu lỗi thời."*
- câu **sau khi bấm Lưu**: *"Đã lưu. Máy chủ báo 1 bản ghi bị đánh dấu lỗi thời."* — và hàng **`犬` đổi `approved:true→false`**.
⇒ **Màn hình nói SAI ngay trước Lưu.** Tệ hơn: route cho **đúng bộ ba y hệt** bài test `CHUA DUYET`
(`term=龙, translation=long, approved=false`) trả **`{"affected":[1]}`** ⇒ **bài test đó đang GHIM CÂU SAI**, trong khi bài
`HOP DONG` **cùng tệp** ghim rằng route trả **khác rỗng** cho cùng dữ liệu vào. **`M11` KHÔNG bắt được ca này** (nó chỉ giết
đường "đang Sửa").

### 2. 🔴 `I2` — SỐ XEM TRƯỚC ≠ SỐ LẦN GHI: `patchTerm` KHÔNG gửi `term`, nhưng ô vẫn SỬA ĐƯỢC

Đang **Sửa một hàng đang duyệt** mà sửa ô **"Thuật ngữ"** rồi bỏ tick ⇒ xem trước *"⚠ bỏ duyệt glossary → **0 bản ghi**…"*
nhưng lưu *"Đã lưu. Máy chủ báo **1 bản ghi**…"*.
**Gốc:** `patchTerm` **KHÔNG gửi `term`** (`TermPatch` của backend **không có** trường `term`) **nhưng ô vẫn sửa được**
⇒ chữ người dùng gõ **bị bỏ IM LẶNG**, và preview được tính cho **một thuật ngữ KHÁC**.
⇒ **Tiêu chí `P3` vỡ trên một đường TỚI ĐƯỢC.** (Khớp Minor "ô Thuật ngữ sửa được nhưng PATCH không gửi term".)

### 3. LUẬT RÚT RA — và nó áp cho T10–T13

- **Một boolean có hai nghĩa thì phải liệt kê HẾT các đường tới được, không chỉ đường hiển nhiên.**
  Bản vá đầu xử **(a) nháp mới** và **(b) bỏ duyệt khi đang Sửa**; còn **(c) nháp mới trỏ vào một hàng ĐANG DUYỆT** —
  cùng bản chất với (b), chỉ khác **đường vào**. **`ERRATA #22` mục 2 đã đúng nhưng CHƯA ĐỦ.**
- **❗ VÀ ĐÂY LÀ GỐC CHUNG CỦA CẢ HAI LỖI: UI TỰ CHẶN CÂU TRẢ LỜI CỦA MÁY CHỦ BẰNG LOGIC CỤC BỘ.**
  Route **đã** tính đúng (`{"affected":[1]}` cho đúng bộ ba đó) — nhưng UI **không thèm hỏi** vì nó tự đoán
  "nháp thì vô hại". ⇒ **Luật: khi máy chủ đã trả lời được, HỎI NÓ; đừng đoán trước rồi mới hiển thị.**
  Nếu cần chặn để bớt request, thì chỉ được chặn theo **dữ liệu máy chủ đã cho** (ví dụ "term này chưa từng tồn tại
  trong danh sách"), **không** theo trạng thái form.
- **Và một ô sửa được mà giá trị không được gửi đi là một lời nói dối về khả năng sửa.** Hoặc gửi nó, hoặc **khoá nó lại**.

### 4. Những gì review **ĐÃ** xác nhận đạt (giữ nguyên, đừng làm lại)

- **V1 ĐẠT:** `405` trước / `200` sau + **`PATCH` thật trả `"affected":[1]` = ĐÚNG số xem trước**; route `@router.get("/affected")`
  dòng **189** < `patch("/{term_id}")` **243**.
- **V4 ĐẠT:** **9 mutation** của review, `G2` giết **đúng** `test_affected_preview_agrees_with_the_write_when_the_term_is_UNAPPROVED`
  (`{'affected': []} != {'affected': [1]}`); `G4` giết `HOP DONG THAM SO` + `LUU`; `M11` giết đúng một bài;
  **`M9` SỐNG SÓT tái lập** và review **chứng minh được "không thể có vế hai"**: `setMode` **chỉ** xuất hiện trong
  `reducer.test.ts` với `mode:"compare"` ⇒ cả app lẫn test **không** chạm nhánh glossary.
- **V5 ĐẠT:** route gọi **LẠI** `_recompute_affected` (dòng **226/230**, cùng hàm `_after_write` dùng); `old` không lọc;
  "đỏ trước" tái lập bằng cách chạy tệp test HEAD trên cây cũ (`5 failed, 18 passed`); guard README **trong cùng commit**
  `b223ab4`, kêu đúng `1 failed, 834 passed` + `(835,13)==(830,13)`; `835/848` và `test_ingest.py` 9 bài ⇒ `826`.
- **V6 ĐẠT:** pytest `835 passed, 13 deselected` EXIT=0; `npm test` **5/5** `128/17/126/2/0` EXIT=1; typecheck 0; build 0.
- **V7 ĐẠT:** ba commit **đúng luật** (ERRATA #14 mục 3 nguyên văn); `types.ts` diff **toàn comment**;
  `contract.test.ts` diff **RỖNG** ⇒ `:705` còn nguyên ⇒ **"có lý về chi phí NHƯNG vẫn là nợ"**
  (hợp đồng route giờ nằm trong tệp test DOM); và **một đính chính cho Task 9**: câu *"§4.4 khối dưới không có nguồn HTTP"*
  là **hơi quá** — `GET /api/transcripts` **đúng là** không kèm `segments`, **nhưng `/api/transcripts/{id}` THÌ CÓ**.
  Quyết định hoãn vẫn **đúng**, lý do **hơi quá**.

### 5. Minor — trong đó **một lời khai SAI về số đo** của implementer

- ❌ **Census EOL trong báo cáo implementer SAI:** nó ghi `app.css` **697/0** và *"8 tệp còn lại toàn LF"*.
  Đo được: **687/0** và **3 tệp CRLF**. ⇒ Lại là **con số không kèm lệnh**; và báo cáo **tự mâu thuẫn 687 vs 697**.
- Ô "Thuật ngữ" sửa được nhưng `PATCH` không gửi `term` (xem `I2`).
- Con số **826** cho máy thiếu `ffmpeg` **chỉ khớp SỐ HỌC** (review không gỡ `ffmpeg` để chạy thật) ⇒ ghi đúng mức.
- Reviewer **tự khai** một vi phạm: lượt `tsc --listFiles` đầu dùng **`npx --no-install`** (luật cấm `npx`) — đã chạy lại
  bằng binary cục bộ. **Tự khai, không ảnh hưởng kết quả.**

## ⚠️ ERRATA #24 — Task 9 vòng sửa #1 (`185a12f`): **ẢNH CHỤP dữ liệu máy chủ KHÔNG phải sự thật của máy chủ**

Vòng sửa xong (**một** commit, **3 tệp**, backend **không** đổi): pytest **`835 passed, 13 deselected`** EXIT=0,
`npm test` **`tests 132 / suites 17 / pass 130 / fail 2 / cancelled 0`** EXIT=1 (128 → 132), `typecheck` 0, `build` 0.
**Gốc chung đã xoá:** `affected.length > 0` **của ROUTE luôn thắng** mọi câu giải thích, và *"có phải bỏ duyệt không"*
suy từ **dữ liệu máy chủ đã cho** (danh sách `terms` đã tải, khoá `(lang, term)` — **đúng khoá `upsert_term` dùng**),
**không** từ trạng thái form. **Và nó tự tìm ra ba điều brief tôi KHÔNG giao:**

### 1. ⚠️ "Suy từ dữ liệu máy chủ" **VẪN CHƯA ĐỦ** — vì đó là một **ẢNH CHỤP**

Nếu ai đó **duyệt** thuật ngữ **SAU khi màn đã nạp**, ảnh chụp nói *"không phải bỏ duyệt"* trong khi **route nói có ảnh hưởng**
⇒ **cùng một lời nói dối, khác đường vào**. Nó dựng test làm ảnh chụp **CŨ một cách TẤT ĐỊNH**:
gieo `馬 -> ngựa` **chưa duyệt** + transcript 4 chứa `馬`; màn nạp xong; bài test **TỰ DUYỆT `馬` qua route THẬT** (`POST` ⇒ `201`);
rồi gõ `馬` + bỏ tick ⇒ route trả `{"affected":[4]}` ⇒ **phải hiện số**. Mutation **`M14`** (đặt câu giải thích **LÊN TRƯỚC** con số)
giết **đúng** bài đó.
⚠️ **Và một bẫy tinh tế nó tự ghi ra: `M14` có SỐ BYTE BẰNG baseline (`20643`) vì nó là phép ĐẢO THỨ TỰ THUẦN**
⇒ **"tệp có khác không?" sẽ MÙ**. Chỉ **witness + sha256** bắt được. ⇒ **Luật: mutation đảo thứ tự có thể KHÔNG đổi số byte —
đừng dùng kích thước tệp làm dấu hiệu.**

### 2. ⚠️ Một câu chữ DÙNG CHUNG cho hai nhánh sẽ nói sai về VIỆC đang xảy ra

**`I1c` — lỗi THẬT THỨ HAI trong chính bản vá của nó:** bỏ duyệt một hàng **đang duyệt** mà **không transcript nào dùng**
⇒ route trả **0**, và nhánh `0` của nó **viết cùng chuỗi** *"⚠ đổi glossary → 0 bản ghi"* ⇒ **đang BỎ DUYỆT mà câu chữ nói "đổi"**.
Đo trước khi sửa: `AssertionError: phai noi dung VIEC sap xay ra (bo duyet): ⚠ đổi glossary → 0 bản ghi…`.
⚠️ **ĐÍNH CHÍNH (ERRATA #26 mục 3): câu này SAI — tôi đã chép nguyên một lời khai SAI của implementer.**
Chuỗi `"⚠ đổi glossary → 0 bản ghi"` cho một lần **BỎ DUYỆT** **KHÔNG tái lập được từ revision nào ĐÃ COMMIT**;
trên `48a84b4`, lệnh `git show 48a84b4:frontend/src/screens/GlossaryScreen.tsx` in ra
`const viec = dangBoDuyet ? "bỏ duyệt glossary" : "đổi glossary"` ⇒ đường "đang Sửa" in **ĐÚNG**
`"bỏ duyệt glossary → 0 bản ghi"`, còn "đổi" chỉ hiện khi **KHÔNG** bỏ duyệt.
Chuỗi sai thuộc một **trạng thái TRUNG GIAN CHƯA COMMIT** của chính vòng #1.
⇒ **`I1c` vẫn có giá trị** (nó bắt một lỗi trong mã **đang viết trước khi commit**) **nhưng KHÔNG được kể như
một lời khai về CÂY ĐÃ COMMIT.** ⇒ **Luật: một lời khai về revision cũ phải TÁI LẬP ĐƯỢC TỪ REVISION ĐÃ COMMIT.**
Sửa: `viec` tính **MỘT lần cho CẢ HAI nhánh số**. Mutation **`M11`** (bỏ điều kiện `!laBoDuyet`) giết **đúng** `I1c`.
⇒ **Nếu chỉ làm đúng brief thì lỗi này ĐI TIẾP.** **Luật: khi hai nhánh chia sẻ một câu chữ mô tả HÀNH ĐỘNG,
hãy hỏi câu đó có đúng cho CẢ HAI không.**

### 3. ⚠️ Phụ thuộc THỨ TỰ trong test — **lần thứ HAI trong cùng một tệp**

Bản nháp đầu của `I2` **ghi vào hàng `龙` (id 1)** ⇒ làm `HOP DONG THAM SO` + `BO DUYET qua FORM` **đỏ ngay**.
Đã sửa: gieo thêm transcript 3 (`犬`) + hàng `犬 -> chó` đang duyệt, và cho `I2` ghi vào **HÀNG RIÊNG**;
bài `BANG` nay **tính số kỳ vọng TỪ ROUTE** thay vì hằng số trong test.
(**Lần đầu** cùng lớp lỗi: bài `LUU` đổi `龙`.) ⇒ **Luật: mỗi bài test phải ghi vào DỮ LIỆU RIÊNG của nó,
và kỳ vọng phải TÍNH TỪ NGUỒN, không hằng số.**

### 4. ✅ `I2` — chọn **KHOÁ ô**, và khoá **HAI LỚP** (vì một lớp KHÔNG đủ)

Nó **không** thêm trường `term` vào `TermPatch` (backend **không** nhận; gửi lên sẽ **bị bỏ im lặng**).
Khoá **cả `lang` lẫn `term`** (TermPatch không có trường nào). Khoá bằng **HAI lớp**: `readOnly`/`disabled` (**thuộc tính HTML**)
**VÀ** `onChange` **bỏ qua** khi `editingId !== null` (**hành vi**) — **vì jsdom VẪN phát được `change` bằng tay, nên thuộc tính một mình KHÔNG đủ**.
Màn **NÓI RA** vì sao khoá (`data-testid="khoa-danh-tinh"`). Mutation **`M13`** giết **đúng** bài `I2`.
⚠️ **Và test đó tự phát `change` để chứng minh LỚP HAI có tác dụng** — một bài test mà **phải vượt qua lớp một** mới đo được lớp hai.

### 5. Ba Minor đã sửa, và **một lời khai số đo SAI được sửa CẢ HAI báo cáo**

- **Census EOL của implementer SAI — đã sửa, KÈM LỆNH.** Đo lại: `app.css` **687/0** · `routes_glossary.py` **258/0** ·
  `test_api_glossary.py` **568/0** · `backend/README.md` **278/0** ⇒ **4 tệp CRLF** (không phải 1 hay 3), còn lại toàn LF,
  **không tệp nào TRỘN**. Và làm rõ **687 vs 697**: **687 là lúc REVIEW**, **697 là BÂY GIỜ** (vòng sửa thêm **10 dòng**
  `.gl__khoa`; `git show --stat 185a12f` ghi `app.css | 10 ++`) ⇒ con số **697 trong báo cáo vòng 1 là SAI ở thời điểm đó**,
  nay **tình cờ đúng**. (Review đếm "3 tệp CRLF" vì **tập tệp khác nhau** — nó tính cả `README.md`; đã kèm lệnh để ai cũng đếm lại được.)
- **Câu TRẦN "không có nguồn HTTP" đã sửa cho khớp sự thật:** `GET /api/transcripts` (danh sách) **không** kèm `segments`,
  **nhưng `/api/transcripts/{id}` THÌ CÓ** ⇒ dữ liệu **ghép được** bằng N request + tự quét `text`.
  Quyết định hoãn **không đổi**, và **LÝ DO THẬT** nay mới được nêu: làm thế là **dựng lại `glossary_match.terms_in` ở client**
  — **nguồn sự thật thứ hai** cho đúng quy tắc mà GĐ2 đã phải vá **hai lần** — cộng N request.
- **`contract.test.ts:705` VẪN chưa chạm** (diff tệp đó trong vòng này **RỖNG**) ⇒ **nợ còn nguyên**, đúng như review chốt:
  *"có lý về chi phí NHƯNG vẫn là nợ"*.

### 6. Mutation vòng này: **15 lượt, 1 sống sót có khai**

**14/14 giết ĐÚNG bài chỉ định** (G1⇒`CHUA DUYET`, G2⇒backend unapprove, G3⇒backend id +2, G4⇒`HOP DONG`+`LUU`,
G5⇒`XEM TRUOC` +8, M6⇒`LOI NAP`, M7⇒`XEM TRUOC`+`BO DUYET`, M8⇒backend writes-nothing +2, M10⇒`LUU`+`I2`,
M11⇒`I1c`, M12⇒`I1`+`I1c`, M13⇒`I2`, M14⇒`I1b`). **1 SỐNG SÓT: `M9`** (bỏ nhánh `glossary` khỏi `App`) — lỗ hổng độ phủ
**ĐÃ KHAI**, và review **đã độc lập chứng minh "không thể có vế hai"** (`setMode` **chỉ** xuất hiện trong `reducer.test.ts`
với `mode:"compare"`) ⇒ **là NỢ, không phải "đã kiểm"**. Guard witness **từ chối mutate một lần** (khớp 0 lần ⇒ ABSENT
⇒ **không ghi tệp nào**). Mọi lượt phục hồi byte-exact + sha256 trùng (**kể cả `M14`, nơi số byte bằng nhau**).
**Và `M11` ĐỔI VAI** (nay giết `I1c`, không còn giết đường "đang Sửa") — implementer **ghi rõ để không ai đọc bảng cũ**.

## ⚠️ ERRATA #25 — Re-review Task 9 vòng sửa #1: **một bài test đọc NGAY sau sự kiện thì MÙ với hiệu ứng DEBOUNCE**

Re-review: **`CONDITIONAL PASS`, 0 Critical / 1 Important / 4 Minor** (vòng trước 0/2/6). **R1, R2, R3, R5, R6, R7 ĐẠT.**
**`R4(b)` KHÔNG ĐẠT** — và đó là lý do duy nhất không cho `PASS`. **Và nó bác một lời khai TÔI đã ghi vào ERRATA #24 mục 4.**

### 1. 🔴 `I-1` — lớp khoá THỨ HAI có THẬT và có sức nặng, nhưng **KHÔNG được ghim**

Review **tách đôi** mutation `M13`:
- `M13a` (chỉ bỏ `readOnly`/`disabled`, **giữ** bỏ-qua `onChange`) ⇒ **giết đúng** bài `I2`;
- **`M13b` (chỉ bỏ bỏ-qua `onChange`, GIỮ thuộc tính) ⇒ SỐNG SÓT:** `ℹ pass 130 / ℹ fail 2` = **y lượt sạch**.

**Nguyên nhân ĐO ĐƯỢC:** bài `I2` đọc số xem trước **NGAY sau `fireEvent.change`** (dòng **663–666**), **TRƯỚC debounce 200 ms**
⇒ dù state có đổi thì **con số chưa kịp đổi**, nên bài test **không phân biệt được** hai lớp.
**Lớp hai VẪN CÓ THẬT** (probe ngoài repo, **chờ 1600 ms**): component thật giữ `term="犬" lang="zh"`,
`SO XEM TRUOC = 1 · SO LAN GHI = 1 · BANG NHAU = true`; bản `M13b` cho `SO XEM TRUOC = null · SO LAN GHI = 1 · BANG NHAU = false`
⇒ **lỗi `I2` quay lại TRONG KHI TOÀN BỘ `npm test` VẪN XANH.**
⇒ **Lời khai của implementer** *"test tự phát `change` để chứng minh lớp hai"* **và `ERRATA #24` mục 4 của TÔI**
(ghi rằng bài test *"phải vượt qua lớp một mới đo được lớp hai"*) **BỊ BÁC BỎ.**

**LUẬT MỚI:**
- **Một bài test đọc trạng thái NGAY sau khi phát sự kiện sẽ MÙ với mọi hiệu ứng DEBOUNCE.**
  Nếu hiệu ứng bị debounce, bài test phải **CHỜ QUA ngưỡng debounce** (hoặc **điều khiển đồng hồ**) trước khi khẳng định.
- **Khi một bản vá có N LỚP, phải mutate TỪNG LỚP RIÊNG.** `M13` (bỏ **cả hai**) giết bài test và **che mất** sự thật rằng
  **chỉ MỘT** lớp được ghim. Đây là **lần thứ hai** trong giai đoạn một mutation "gộp" che một lỗ hổng
  (lần đầu: `M4` của Task 3 là đột biến tương đương nhưng brief tôi tưởng nó phân biệt được).

### 2. ✅ Ba lỗi thật mà vòng sửa nhắm — **cả ba ĐẠT bằng phép đo của review** (đừng làm lại)

- **R1 ĐẠT — CA THỨ BA thật sự được sửa, đo trên màn hình thật:** `[PROBE new-third] XEM TRUOC SAU KHI BO TICK:
  "⚠ bỏ duyệt glossary → 1 bản ghi bị đánh dấu lỗi thời"` + `CAU SAU KHI LUU: "Đã lưu. Máy chủ báo 1 bản ghi…"`,
  form **MỚI** (nút ghi `"Lưu thuật ngữ"`), DB đổi `龙` → `approved:false`; **cùng seed trên cây `48a84b4` in**
  `"Thuật ngữ CHƯA DUYỆT: đổi nó không ảnh hưởng gì — …"` ⇒ **lỗi có thật, bản vá xoá THẬT.**
- **R2 ĐẠT — bài test từng ghim câu sai, nay đúng:** gọi trên **chính DB gieo của tệp test**:
  `lang=zh term=龙 translation=long approved=false -> 200 {"affected":[1]}` ·
  `lang=zh term=mèo translation=cat approved=false -> 200 {"affected":[]}` ⇒ bộ ba **CŨ** đúng là ghim câu sai,
  bộ ba **MỚI** (`mèo`) **thật sự rỗng**.
- **R5 ĐẠT:** `M11` giết **đúng** `I1c`; và **bẫy byte-bằng-nhau được xác nhận**:
  `[mutant] bytes=20643 sha256=fc3100e2…` so baseline `bytes=20643 sha256=2304778b…`
  ⇒ **byte BẰNG NHAU, sha256 KHÁC**, `fail 3`, đỏ **đúng một** `I1b`.

### 3. ✅ `R6` được đo **MẠNH** — đảo thứ tự CẢ 12 khối `it`

Review dựng bản sao **ngoài repo** và **đảo thứ tự cả 12 khối `it`** (chỉ đổi 6 import sang URL tuyệt đối):
`EXIT=0 · ℹ tests 12 · ℹ pass 12 · ℹ fail 0`; tệp gốc chạy một mình cũng **12/12**. Và **ở thứ tự đảo, ba bài GHI
(`LUU`, `I2`, `I1b`) chạy TRƯỚC `BANG`/`HOP DONG THAM SO` mà hai bài này VẪN XANH** ⇒ vế *"kỳ vọng tính TỪ ROUTE"* **là THẬT**.
⇒ **Đây là cách kiểm phụ thuộc thứ tự đúng: ĐẢO THỨ TỰ, đừng chỉ đọc mã.**

### 4. Bốn Minor — trong đó **hai cái là lời khai SAI cần sửa**

- **`M-1` — lời khai `I1c` về cây TRƯỚC sai phần câu chữ:** chuỗi `"⚠ đổi glossary → 0 bản ghi"` cho một lần **BỎ DUYỆT**
  **KHÔNG tái lập được từ revision nào đã commit**; trên `48a84b4` đường "đang Sửa" in **ĐÚNG**
  `"⚠ bỏ duyệt glossary → 0 bản ghi"`, còn "đổi" chỉ hiện khi **KHÔNG** bỏ duyệt.
  ⇒ **Lỗi thật trên cây cũ là một CÂU KHÁC** — và **một lời khai về revision cũ phải tái lập được TỪ REVISION ĐÃ COMMIT.**
- **`M-2` — lớp "ảnh chụp cũ" chỉ phủ ở nhánh `>0`:** ở nhánh **`0`**, UI **vẫn gọi một hàng ĐANG duyệt là "bản nháp"**
  (probe `new-stale-zero`: `POST … -> HTTP 201`, `MAY CHU SAU POST: [{"term":"鳥","approved":true}]`
  trong khi câu là *"Thuật ngữ CHƯA DUYỆT …"*). **Con số vẫn đúng `0`** nên chỉ **LÝ DO** sai — nhưng đó vẫn là **nói dối về lý do**.
- **`M-3`:** hằng số kỳ vọng còn sót (`hang-1/hang-2/trong-2/sua-1/sua-3/hang-3/anh-huong-1`, `giuNguyen.affected==[]`) —
  phụ thuộc **thứ tự GIEO**, không phải thứ tự **CHẠY** (nên R6 vẫn đạt).
- **`M-4`:** *"4 tệp CRLF"* chỉ đúng cho **tập 10 tệp**; **toàn cây: 71/168 tệp CRLF, 0 tệp TRỘN**.
- Ghi nhận thêm: **ô "Ảnh hưởng" của hàng đích hiện `—`** ở ca thứ ba (đo: `cot Anh huong cua hang 1: "—Sửa"`)
  **trong khi câu xem trước hiện `1`** ⇒ hai chỗ trên cùng màn hình nói khác nhau.

### 5. Điều review **KHÔNG** đo được (ghi đúng mức)

**"Bàn phím bị chặn thật sự"** (không trình duyệt, Playwright bất khả, `e2e` bị cấm); **`M9` không chạy lại**;
nghĩa của `I1b` khi `馬` **đã duyệt sẵn lúc nạp** (chạy 2 lần trong cùng tiến trình) — **mới suy luận**;
**"đỏ trước khi sửa" nguyên văn của `I1`/`I2`** (bản nháp trung gian **KHÔNG commit** ⇒ không tái lập được — và **review trước
đã từng nhắc điều này**); con số `826` cho máy thiếu `ffmpeg` (**mới khớp SỐ HỌC**);
nhánh `200` trên `data/app.db` thật (**Task 12**); `contract.test.ts:705`; và **mọi kết luận HÌNH** (không có ảnh render thật).

## ⚠️ ERRATA #26 — Task 9 vòng sửa #2 (`899495d`): **một tệp MUTANT bị dùng làm BASELINE cả một vòng**, và lớp "đúng nhưng KHÔNG QUAN SÁT ĐƯỢC"

Vòng sửa #2 xong (**một** commit, **2 tệp** `GlossaryScreen.tsx` + test; backend/`app.css`/`endpoints.ts`/`App.tsx`/`types.ts`
**không đổi**): pytest `835 passed, 13 deselected` EXIT=0 · `npm test` **`tests 133 / suites 17 / pass 131 / fail 2 / cancelled 0`**
EXIT=1 (132 → **133** = +`I1d`) · `typecheck` 0 · `build` 0. **18 lượt mutation, 15/15 giết ĐÚNG bài, 2 sống sót CÓ KHAI.**

### 1. ✅ `I-1` ĐÓNG — và **HAI LỚP nay có HAI mutation RIÊNG, hai output RIÊNG**

Trên cây **ĐÃ COMMIT** `185a12f`, chạy **riêng từng lớp**: `M13a` ⇒ `132/129/3` đỏ **tại `I2`** (18,4 ms);
**`M13b` ⇒ `132/130/2` = Y HỆT lượt sạch ⇒ SỐNG SÓT** — **tái lập ĐÚNG phép đo của review**, và nó **nhận lời khai của mình bị bác bỏ**.
**Sửa:** bài `I2` **chờ QUA ngưỡng debounce** rồi mới đọc số (`await act(async () => { await new Promise(r => setTimeout(r, 900)); })`,
**4,5×** `CHO_GO_MS = 200 ms`).
**Sau khi sửa, chạy RIÊNG từng lớp, CẢ HAI đều giết `I2`:**
- `M13a` ⇒ `pass 130 / fail 3`, đỏ tại `AssertionError: dang Sua thi o 'Thuat ngu' phai la readOnly` (**18,6 ms** — khẳng định **THUỘC TÍNH**);
- `M13b` ⇒ `pass 130 / fail 3`, đỏ tại `AssertionError: khong doc duoc con so nao trong: "Thuật ngữ CHƯA DUYỆT: …"` (**1150 ms** — khẳng định **SỐ**, **SAU debounce**).
⇒ **`ERRATA #25` mục 1 nay được THI HÀNH**, không chỉ được viết ra.

### 2. ✅ `M-2` ĐÓNG — và **LÝ DO nay đọc TỪ MÁY CHỦ**

Test mới `I1d` làm ảnh chụp cũ **TẤT ĐỊNH** (gieo `魚 -> cá` **chưa duyệt**, không transcript nào dùng; màn nạp xong;
test **TỰ DUYỆT `魚` qua route THẬT** (`POST` ⇒ `201`); rồi gõ `魚` + bỏ tick; route trả **0** vì không ai dùng `魚`).
**ĐỎ trước khi sửa:** `hang DANG duyet thi phai hien con so 0 kem chu 'ban ghi'; do duoc: "Thuật ngữ CHƯA DUYỆT: …"`.
**Sửa:** lý do đọc từ **`GET /api/glossary?lang=…`** — **một request ĐỌC THÊM chỉ khi ô "đã duyệt" đang TẮT** —
**gộp vào CÙNG một lần cập nhật state** với câu trả lời xem trước (`Promise.all`) để **con số và lý do không lệch nhau**;
ba giá trị `undefined`/`null`/`Term` phân biệt **"chưa đọc được" / "không có hàng" / "có hàng"**, và **khi CHƯA đọc được thì KHÔNG khẳng định lý do nào**.
**Hai lỗi phụ tự lộ ra khi sửa và đã sửa:** (1) dòng xem trước **nhảy chữ** (`đổi` → `bỏ duyệt` sau khi số đã hiện) ⇒ gộp một lần render;
(2) **con số CŨ còn nằm đó** khi input đã đổi ⇒ `datAffected(null)` đầu effect ("đang đếm…") — và **đây cũng chính là thứ**
làm cho một bài test chờ "con số MỚI" không thể khớp con số CŨ.
Mutation ghim: `M16` (suy lý do từ **ẢNH CHỤP** thay vì đọc lại) ⇒ `129/4`, đỏ `I1b` + `I1d`; `M11` ⇒ `129/4`, đỏ `I1c` + `I1d`.

### 3. ⚠️ ĐÍNH CHÍNH: **`ERRATA #24` mục 2 đã CHÉP một lời khai SAI** (đã sửa tại chỗ)

Tôi chép nguyên câu *"nhánh `0` viết cùng chuỗi `"⚠ đổi glossary → 0 bản ghi"` cho một lần bỏ duyệt"* — **SAI**:
chuỗi đó **không tái lập được từ revision nào đã commit**; trên `48a84b4` đường "đang Sửa" in **ĐÚNG** `"bỏ duyệt glossary → 0 bản ghi"`.
⇒ **`I1c` vẫn có giá trị** (bắt lỗi trong mã **đang viết trước commit**) nhưng **không được kể như lời khai về cây đã commit**.
Implementer **báo lại** (không tự sửa số của tôi) — **đúng cách**. ⇒ **Luật: một lời khai về revision cũ phải TÁI LẬP ĐƯỢC TỪ REVISION ĐÃ COMMIT.**

### 4. 🔴 `M-2` hiển thị ĐÓNG, và ⚠️ **SỰ CỐ LỚN: một tệp MUTANT bị dùng làm BASELINE cả một vòng**

- **Ô "Ảnh hưởng" của HÀNG ĐÍCH** nay bằng con số của dòng xem trước; hàng đích = `editingId === t.id` **HOẶC** hàng khớp
  **KHOÁ `(lang, term)`** của form. `M15` (bỏ vế khớp khoá) ⇒ `pass 130 / fail 3`, đỏ **đúng** `I1`.
- **SỰ CỐ (implementer TỰ KHAI đầy đủ):** lượt chạy driver mutation **ĐẦU TIÊN** bị **pipe vào một `Select-String` có regex KHÔNG HỢP LỆ**;
  bộ lọc chết, **node bị giết GIỮA mutation `G1`**, và nó **ĐỂ LẠI `GlossaryScreen.tsx` ở TRẠNG THÁI MUTANT** (mất nhánh câu "nháp").
  **Lượt sau lấy CHÍNH TỆP MUTANT đó làm BASELINE** ⇒ `CHUA DUYET` đỏ trong **MỌI** lượt (kể cả lượt mutation `M9` trên `App.tsx`),
  và **ba witness (`G1`/`M11`/`M14`) báo ABSENT/TỪ CHỐI** — **guard ĐÃ KÊU**, nhưng nó **đọc nó là "literal của tôi sai"
  thay vì "TỆP đang sai"**. Phát hiện bằng **ba dòng `[TU CHOI MUTATE]` + `git diff HEAD`**, **dựng lại đoạn bị xoá**,
  chạy lại **13/13 xanh**, rồi **đọc lại TOÀN BỘ diff (177 dòng)** để chắc không còn gì đi sẵn.
  **Chốt chặn đã thêm:** (1) **kiểm trước fingerprint 5 đầu văn** — phải khớp **đúng 1 lần**, thiếu ⇒ **`[DUNG NGAY]`, không chạy gì**;
  (2) lưới **`SIGINT`/`SIGTERM`/`SIGHUP`** khôi phục trước khi thoát; (3) **KHÔNG BAO GIỜ pipe driver qua một bộ lọc có thể chết** —
  ghi ra **tệp** rồi đọc tệp.
  ⇒ **BÀI HỌC LỚN: một witness bỗng nhiên TỪ CHỐI là tín hiệu về TỆP, không phải về LITERAL.**
  ⇒ Đây là **lần thứ TƯ** một agent để lại tệp ở trạng thái mutant — **lần này TỰ PHÁT HIỆN + TỰ KHAI ĐẦY ĐỦ**, và nó còn
  **audit cả diff** để bảo đảm không có "di sản" nào khác. **Đó là cách xử đúng.**

### 5. ⚠️ LỚP THỨ BA CỦA "MUTATION SỐNG SÓT": **ĐÚNG nhưng KHÔNG QUAN SÁT ĐƯỢC**

**`M14`** (bỏ vế **PHÒNG THỦ** `affected.length === 0`) ⇒ `131/2` **y hệt lượt sạch**. Nhưng nó **KHÔNG** phải lỗ hổng độ phủ
thường: theo luật `affected_segments`, **`laNhapThat` SUY RA `affected === []`**, nên trạng thái *"nháp MÀ có ảnh hưởng"*
chỉ tới được qua một **CUỘC ĐUA giữa hai lời gọi song song** ⇒ **không tồn tại phép đo tất định**.
⇒ Khai theo **`ERRATA #7` mục 5**, **KHÔNG** tính là "đã kiểm". ⇒ **Ba lớp của "mutation sống sót" nay đã rõ:**
(a) giết đúng bài (tốt); (b) **lỗ hổng độ phủ nâng cấp được** ⇒ sửa hoặc khai; (c) **KHÔNG QUAN SÁT ĐƯỢC do cấu trúc** ⇒ khai + nói RÕ VÌ SAO.
`M9` (nhánh `glossary` của `App`) vẫn là lỗ hổng **không có đường tới** — đã khai từ trước.

### 6. Hai Minor ghi nhận đúng mức

- **`M-3`** id hàng vẫn **phụ thuộc thứ tự GIEO** (không phải thứ tự CHẠY) ⇒ **`R6` vẫn đạt**; đường nâng cấp: tra hàng theo **CHỮ** (bài `I1d` đã làm vậy).
- **`M-4`** *"4 tệp CRLF"* chỉ đúng cho **tập 10 tệp**; **toàn cây tại HEAD này**: `CRLF=76 · LF-only=98 · TRỘN=0 · không-có-dòng-nào=5 · tổng=179`
  (review đo `71/168` — **khác ở TẬP TỆP**; **điều cả hai khớp và là điều quan trọng: 0 tệp TRỘN**).
- `contract.test.ts:705` **vẫn chưa chạm** (diff tệp đó **RỖNG**) ⇒ **nợ còn nguyên**.

## ⚠️ ERRATA #27 — Re-review Task 9 vòng sửa #2: **"KHÔNG QUAN SÁT ĐƯỢC" phải được CHỨNG MINH, không được TUYÊN BỐ**

Re-review vòng sửa #2: **`CONDITIONAL PASS`, 0 Critical / 1 Important / 4 Minor.** **R1, R2, R3, R4, R5, R7 ĐẠT** (đủ điều kiện
`PASS` cho ba mục trọng tâm); **chỉ `R6` KHÔNG ĐẠT** — và nó **bác bỏ** lời khai *"`M14` không quan sát được"*.

### 1. 🔴 `R6` — "KHÔNG TỒN TẠI PHÉP ĐO TẤT ĐỊNH" là **SAI**, và review đã **DỰNG RA** phép đo đó

Implementer khai: `M14` (bỏ vế **PHÒNG THỦ** `affected.length === 0`) sống sót vì *"nháp MÀ có ảnh hưởng"* chỉ tới được qua
**cuộc đua giữa hai lời gọi song song** ⇒ **không có phép đo tất định**.
- Vế **suy luận** của nó **ĐÚNG**: luật `affected_segments` (`backend/app/domain/glossary_match.py:76-88`) + **sweep route THẬT 6/6 hàng**
  ⇒ `laNhapThat` ⇒ `affected === []`.
- Nhưng **"không tồn tại phép đo tất định" là SAI.** Review dựng **probe2**, **chỉ điều khiển THỨ TỰ**, **mọi lời gọi đều là route THẬT**:
  **giữ** request `affectedPreview` lại → để `GET /api/glossary?lang=zh` trả *"chưa duyệt"* → **`POST` duyệt hàng đó** (`201`)
  → **thả** request ⇒ route trả **`{"affected":[1]}`** trong khi `laNhapThat = true`.
  Bản **NGUYÊN** in `"⚠ đổi glossary → 1 bản ghi…"` (**không nói dối**); bản **`M14`** in
  `"Thuật ngữ CHƯA DUYỆT: … không ảnh hưởng gì …"` ⇒ `[KET LUAN] phep do TAT DINH phan biet duoc M14? => true`.
⇒ **`M14` KHÔNG phải lớp (c) "không quan sát được do cấu trúc" — nó là lớp (b) LỖ HỔNG ĐỘ PHỦ NÂNG CẤP ĐƯỢC**,
và **đang được giao vá** (công thức ở §R6(b) của báo cáo review).

**LUẬT MỚI (quan trọng):** **"Không quan sát được" là một TUYÊN BỐ, không phải một miễn trừ.**
Muốn tuyên bố nó thuộc lớp (c), phải **chứng minh** rằng **mọi** đường tới trạng thái đó đều **không thể điều khiển tất định** —
và "hai lời gọi song song" **KHÔNG** tự động là bất khả: **thứ tự của hai lời gọi thường ĐIỀU KHIỂN ĐƯỢC**
(giữ một cái, đổi trạng thái máy chủ, rồi thả). ⇒ **Trước khi khai lớp (c), hãy thử điều khiển THỨ TỰ.**
(Đây là **lần thứ hai** trong giai đoạn một agent khai "không đo được" rồi người sau **đo được**:
lần đầu là `useJobStream` ở Task 3 — khi đó **jsdom + server `node:http`** biến "không đo được" thành **đo được**.)

### 2. ✅ Ba mục trọng tâm ĐẠT — và `R5` (không còn "di sản" mutant) đạt

- **`R1` ĐẠT:** `M13a` ⇒ `pass 130 / fail 3`, đỏ `I2` tại **19,6729 ms** (`dang Sua thi o 'Thuat ngu' phai la readOnly`);
  `M13b` ⇒ `pass 130 / fail 3`, đỏ `I2` tại **1171,1393 ms** (`khong doc duoc con so nao trong: "Thuật ngữ CHƯA DUYỆT: …"`).
  **Đối chứng âm trên `185a12f`** (đọc bằng `git show`, blob khớp): `OLD-M13b` = `132 / pass 130 / fail 2` = **y `OLD-CLEAN` ⇒ SỐNG SÓT**.
  ⇒ **Hai lớp, hai mutation, hai kết luận ngược nhau giữa cây cũ và cây mới** — đây là bằng chứng đúng cho một bản vá hai lớp.
- **`R3` ĐẠT:** đếm request THẬT — checkbox **BẬT ⇒ `listTerms(lang) = 0`**, **TẮT ⇒ `= 1`**;
  `MutationObserver` ghi `["⚠ đổi glossary → 1 …","đang đếm…","⚠ bỏ duyệt glossary → 1 …"]` ⇒ **không có khung hình nào
  "số đúng + lý do sai"**; khi đọc lại **thất bại** ⇒ `"⚠ đổi glossary → 0 bản ghi…"` và **không câu lý do nào**;
  `M16` ⇒ `129/4` đỏ **đúng `I1b`+`I1d`**; `M11` ⇒ `129/4` đỏ **đúng `I1c`+`I1d`**; `I1d` **tất định** (3/3 probe + 8 lượt `npm test` xanh).
- **`R5` ĐẠT:** `git diff HEAD` **RỖNG**; **10/10 byte-exact** (trước và sau mọi phép đo);
  **đọc diff TỪNG DÒNG** `GlossaryScreen.tsx` từ `185a12f` → HEAD (**177 dòng, 82+/40−**) ⇒ **không nhánh/câu nào bị mất**
  (3 nhánh `noiXemTruoc` vẫn đủ; câu `"CHƯA DUYỆT"` còn nguyên) ⇒ **"di sản" của sự cố mutant KHÔNG còn**;
  `npm test` **5/5** `133/17/131/2/0`.
  ⚠️ **Một mục CHƯA KIỂM ĐƯỢC:** **driver của implementer KHÔNG được commit** và scratch `_task9fix2` đã xoá
  ⇒ bộ **fingerprint 5 đầu văn + lưới `SIGINT`/`SIGTERM`/`SIGHUP`** mà nó khai là **CHƯA KIỂM ĐƯỢC**.
  ⇒ **Luật: nếu "chốt chặn của driver" là một phần của BẰNG CHỨNG, thì driver phải được COMMIT (hoặc chốt chặn phải được TRÌNH DIỄN).**
- **`R2` ĐẠT + một Minor sắc:** `CHO_GO_MS = 200`; 900 ms = **4,5×**; settle đo được **250 ms**; mutation **riêng** của review
  (`M13c`, bỏ bỏ-qua **chỉ ở ô "Thuật ngữ"**) **BỊ BẮT** (**1165,6827 ms**).
  ⚠️ **Nhưng hạ `900 → 50 ms` thì lượt SẠCH vẫn XANH (`131/2`) mà `M13b` VẪN ĐỎ (`130/3`, tại `"đang đếm…"`)
  ⇒ phát biểu *"phép chờ là CẦN THIẾT"* KHÔNG tái lập đúng như đã viết.**
  Thứ giết `M13b` ở 50 ms là **`datAffected(null)` đầu effect**, **không phải** phép chờ.
  ⇒ **Phép chờ là cần cho việc ĐỌC CON SỐ MỚI, không phải cho việc phân biệt hai lớp.** Ghi đúng mức.

### 3. Hai sự cố của CHÍNH REVIEWER (tự khai; chỉ chạm BẢN SAO, repo không bị chạm)

1. **Lưới `process.on("exit")` của nó khôi phục SAI baseline** — nó ghi tệp `185a12f` lên bản sao **SAU khi** lượt cuối đã
   khôi phục **đúng** về HEAD. Phát hiện vì probe cho hành vi **cũ**; đã sửa (lưới chỉ khôi phục về **HEAD**), dựng lại bản sao
   **byte-exact**, chạy lại toàn bộ probe.
   ⇒ **Luật: lưới an toàn phải khôi phục về TRẠNG THÁI ĐÍCH CỐ ĐỊNH (HEAD), không phải về "ảnh chụp lúc bắt đầu"** —
   nếu không, nó **phục hồi về một mutant cũ** và tạo ra bằng chứng sai.
2. **Phép đảo `it` lần đầu GỘP khối cuối** (mang **dòng đóng `describe`**) lên đầu ⇒ `describe` **đóng sớm** ⇒ `120/13` **GIẢ**;
   đã **tách dòng đóng** rồi chạy lại ⇒ `131/2`.
   ⇒ **Luật: khi đảo thứ tự khối test, phải xử lý dòng đóng của `describe` như một đơn vị RIÊNG.**

### 4. `R4`/`R7` ĐẠT, và tính trung thực được xác nhận

- **`R4`:** `M15` ⇒ `130/3` đỏ **đúng `I1`**; ca thứ ba trên màn hình thật (nút `"Lưu thuật ngữ"` = form **MỚI**):
  `XEM TRUOC = "⚠ bỏ duyệt glossary → 1 bản ghi…"` và `ô 'Anh huong' hang-1 = "1Sửa"` (hai hàng khác `"—Sửa"`) ⇒ **HAI CHỖ BẰNG NHAU**.
- **`R7`:** `typecheck` 0 · `build` 0 · `--listFiles` 85 dòng, **0** tệp `.test.` · pytest `835 passed, 13 deselected` EXIT=0 ·
  guard README `5 passed` EXIT=0 · `899495d` = **2 tệp, không gì ngoài `frontend/`**.
  **Trung thực:** **cả hai lời khai bị bác bỏ đã được sửa TẠI CHỖ** (3 khối đính chính ở báo cáo vòng 1 + §3 báo cáo vòng 2);
  **`M-3` xác nhận** (review tự đảo **13** khối `it` ⇒ `131/2` y lượt sạch); **`M-4` xác nhận từng số** (`CRLF=76 · LF=98 · TRỘN=0 · 5/179`).
- **Mutation còn sống: CHỈ `M14`** (xem mục 1) ⇒ **đang được vá**. `M9` review không chạy lại. **~22 lượt `npm test` đầy đủ**,
  **không lượt nào bị `timeoutMs` cắt**.

## ⚠️ ERRATA #28 — Task 9 vòng sửa #3 (`7fb23a1`): **CÁCH BIẾN MỘT "CUỘC ĐUA" THÀNH PHÉP ĐO TẤT ĐỊNH**, và một cái bẫy thời lượng

Vòng sửa #3 xong: **MỘT commit, MỘT tệp** (`frontend/src/screens/GlossaryScreen.test.tsx`, **+81 dòng**);
**KHÔNG tệp sản phẩm nào bị đụng** (`GlossaryScreen.tsx`/`app.css`/`endpoints.ts`/`App.tsx`/`types.ts`/`backend`: diff **RỖNG**).
pytest **`835 passed, 13 deselected`** EXIT=0 · `npm test` **`tests 134 / suites 17 / pass 132 / fail 2 / cancelled 0`** EXIT=1
(133 → **134** = +`I1e`) · `typecheck` 0 · `build` 0 · **18 lượt mutation, 16/16 giết ĐÚNG bài, 1 sống sót (`M9`, đã khai)**.

### 1. ✅ `R6` ĐÓNG — `M14` nay là **lớp (b) đã bịt**, không còn là lớp (c)

**CÔNG THỨC (đáng chép cho mọi "cuộc đua" ở T10–T13):** để biến một cuộc đua giữa **hai lời gọi song song** thành
**phép đo TẤT ĐỊNH**, hãy **điều khiển THỨ TỰ**, không đua:
1. **Bọc `globalThis.fetch` thành CẦU NỐI ĐIỀU KHIỂN THỨ TỰ** — request `/glossary/affected?` bị **GIỮ**, mọi request khác
   **đi thẳng**, và request bị giữ **VẪN đi HTTP THẬT khi được thả**. (Khai rõ: **không phải giả lập mạng.**)
2. Gõ input ⇒ lần **ĐỌC TRẠNG THÁI** (`GET /api/glossary?lang=…`) đi thẳng và trả *"chưa duyệt"*.
3. **CHỜ BẰNG TÍN HIỆU TƯỜNG MINH** (cầu nối bật cờ, qua `waitFor`) — **không** "chờ 200 ms rồi hy vọng".
4. **`POST` duyệt hàng đó qua route THẬT** (`201`) ⇒ máy chủ giờ nói *"đang duyệt"*.
5. **THẢ** request xem trước ⇒ route trả **`{"affected":[5]}`** trong khi ảnh chụp cũ nói `laNhapThat = true`.
6. Khẳng định: **PHẢI hiện SỐ** và **KHÔNG** được in câu *"không ảnh hưởng gì"*.
**Kết quả:** `✔ I1e: … (314,4057 ms)` · `tests 14 / pass 14 / fail 0` EXIT=0 ⇒ **thứ tự do TÍN HIỆU, không do CHỜ**
(314 ms, không phải ~900 ms). **Và `M14` GIẾT NÓ:** `tests 134 / pass 131 / fail 3` với `✖ I1e: … (8282,8592ms)`;
witness `PRESENT`; mutant `bytes=24106`; phục hồi `equals=true`.
Hai request được **gộp vào MỘT lần cập nhật state** (`Promise.all`) nên cặp `(lý do: nháp, số: 1)` là **trạng thái QUAN SÁT ĐƯỢC**.

### 2. ✅ `M-1` ĐÓNG — **cái phân biệt hai lớp là VIỆC XOÁ SỐ, không phải PHÉP CHỜ**

Implementer chạy **thí nghiệm hai yếu tố** (`task-9fix3-do-treo.mjs/.log`), **cả ba lượt phục hồi byte-exact**:
| Lượt | Cấu hình | Kết quả |
|---|---|---|
| `L1` | phép chờ **50 ms**, cây **SẠCH** | `tests 134 / pass 132 / fail 2` — **XANH** |
| `L2` | **50 ms** + `M13b` | `pass 131 / fail 3`, đỏ tại `khong doc duoc con so nao trong: "đang đếm…"` (**315 ms**) |
| `L3` | **900 ms** + `M13b` | `pass 131 / fail 3`, đỏ tại `khong doc duoc con so nao trong: "Thuật ngữ CHƯA DUYỆT: …"` (**1160 ms**) |
⇒ **Thứ phân biệt hai lớp là `datAffected(null)` ĐẦU EFFECT** (xoá con số **ngay khi input đổi**, **không cần debounce**),
**KHÔNG** phải phép chờ. **Phép chờ chỉ đổi HÌNH DẠNG bằng chứng**: ở 50 ms nó bắt được khung `"đang đếm…"`,
ở 900 ms nó bắt được **CON SỐ SAI**. Câu chữ trong `task-9-fix-round-2-report.md` đã sửa kèm bảng này.

### 3. ⚠️ MỘT CÁI BẪY ĐÁNG CHÉP: **THỜI LƯỢNG LÀ DẤU HIỆU**

Script thí nghiệm **lượt đầu** của implementer **có lỗi, và nó TỰ BẮT**: nó chỉ khôi phục `GLOSS` sau `L2`
⇒ **`L3` chạy trên tệp test VẪN CÒN 50 ms** ⇒ **`L3` là BẢN SAO CỦA `L2`**.
**Dấu hiệu DUY NHẤT** là **thời lượng `314 ms < 900 ms`** — tức **phép chờ mà nó TIN là 900 ms đã không xảy ra**.
Đã sửa (khôi phục **CẢ HAI** tệp + in `equals` cho **cả hai** + **in số lần `"setTimeout(resolve, 900)"` khớp** ở đầu `L3`) rồi chạy lại.
⇒ **Luật: khi một phép đo phụ thuộc vào một NGƯỠNG/THỜI LƯỢNG bạn tự đặt, hãy IN THỜI LƯỢNG ĐO ĐƯỢC và SO với ngưỡng đó.**
Một lượt chạy **nhanh hơn ngưỡng** là bằng chứng **ngưỡng chưa hề được áp** — không phải bằng chứng nó chạy tốt.

### 4. ✅ DRIVER LÀ BẰNG CHỨNG ⇒ **NAY ĐỌC LẠI ĐƯỢC**, và lời TỪ CHỐI đã được sửa để chỉ đúng nghi phạm

Publish vào `.superpowers/sdd/2026-09-26-frontend-workspace-2/` (**gitignore ⇒ `git status` vẫn RỖNG**):
`task-9fix3-mutate.mjs` (driver đầy đủ: **KIỂM TRƯỚC 5 đầu văn** + witness + `finally` + lưới `exit` + **`SIGINT`/`SIGTERM`/`SIGHUP`**
+ chế độ `verify`), `task-9fix3-run.log` (**18 lượt**, gồm **5/5** dòng `[kiem truoc] dau van khop 1 lan ⇒ OK`),
`task-9fix3-verify.log`, `task-9fix3-do-treo.mjs` + `.log`.
**Và điều đắt nhất: lời TỪ CHỐI nay NÓI ĐÚNG NGHI PHẠM** —
`[TU CHOI MUTATE] K0: co cap witness khong khop DUNG 1 lan. KHONG ghi tep nao. Tep nguyen trang: true — ⚠️ HOI NGAY: TEP co dang sai (di san mutant) khong?`
⇒ **Bài học của sự cố "tệp mutant làm baseline" (ERRATA #26 mục 4) đã được MÃ HOÁ VÀO CÔNG CỤ**, không chỉ nằm trong tài liệu.

### 5. ⚠️ Lưới an toàn nay khôi phục về **TRẠNG THÁI ĐÍCH**, và baseline được đối chiếu byte-exact

Lượt `verify` **sau commit** in **cả hai vế**:
`[baseline] … bytes=24131 sha256=002559ac…181d eol=LF | HEAD bytes=24131 sha256=002559ac…181d` (**cây làm việc == HEAD, byte-exact**)
và `[phuc hoi] readback.equals(HEAD) === true · bytes=24131 sha256=002559ac…181d`.
**Trước** commit, baseline là **cây làm việc** (chính là thứ được commit) — và nó được **đối chiếu byte-exact với HEAD NGAY SAU commit**:
**10/10 tệp** `git hash-object --path=<f>` == `git rev-parse HEAD:<f>`.
⇒ **`ERRATA #27` mục 3.1 nay được thi hành** (lưới khôi phục về **HEAD**, không về "ảnh chụp lúc bắt đầu").

### 6. Nợ còn lại của Task 9 (khai minh bạch, không chặn)

- **`M9`** (nhánh `glossary` của `App`): **không có đường nào tới được** (`setMode` **0** dispatch) ⇒ **nợ**, không phải "đã kiểm".
- **Lệch đơn vị "bản dịch" vs "bản ghi"**: vẫn là **nợ của ROUTE** (muốn nói "bản dịch" thì route phải trả số bản dịch).
- **`§4.4` khối dưới** ("thuật ngữ xuất hiện ở đâu") **vẫn không làm** — nay lý do đã đúng: làm thế là **dựng lại
  `glossary_match.terms_in` ở client** (nguồn sự thật thứ hai) + N request.
- **`contract.test.ts:705`** vẫn **chưa chạm** (diff tệp đó **RỖNG**) ⇒ nợ còn nguyên.
- **`M-3`** id hàng trong các bài **cũ** vẫn phụ thuộc **thứ tự GIEO**; `I1e` **tra hàng theo CHỮ** nên **không thêm** phụ thuộc mới.
- **Chưa ai nhìn thấy màn hình này trong trình duyệt thật** (`jsdom` không layout/CSS; `readOnly` không chặn devtools);
  `npm run e2e`/Playwright **bị cấm**; nhánh `200` trên `data/app.db` thật (**rỗng**) là việc của **Task 12**.

## ⚠️ ERRATA #29 — TASK 9 ĐÓNG (`PASS` 0/0/2): **cách chứng minh "request THẬT SỰ đi ra"**, và **trần `waitFor` giải thích đường ĐỎ chậm**

Re-review vòng sửa #3: **`PASS`, 0 Critical / 0 Important / 2 Minor.** **R1–R7 đều ĐẠT**, R1/R2/R3 bằng phép đo độc lập.
**TASK 9 XONG.** Bốn điều đáng chép:

### 1. ✅ CÁCH CHỨNG MINH "request bị GIỮ vẫn THẬT SỰ đi ra": **log ở tầng `undici`**

Review preload một hook ở **tầng `undici`** (`undici:request:create` / `undici:request:headers`) — **DƯỚI `fetch`**,
nên **một wrapper `fetch` KHÔNG THỂ giả** nó. Kết quả (**5/5 lượt cùng thứ tự**):
```
938 ms create  GET  /api/glossary?lang=zh
941 ms headers 200
970 ms create  POST /api/glossary
981 ms headers 201
982 ms create  GET  /api/glossary/affected?lang=zh&term=%E9%BE%8D&translation=long&approved=false
985 ms headers 200
```
⇒ request bị **GIỮ** chỉ **rời client SAU khi được thả**, và **ĐÃ tới server** (`200`); khe lý-do→POST chỉ **16–31 ms**, **5/5 lượt**.
⇒ **LUẬT: muốn chứng minh "request THẬT SỰ đi ra" mà không bị chính cái wrapper đánh lừa, hãy log ở TẦNG THẤP HƠN cái wrapper**
(ở đây: `undici`). Đây là mức bằng chứng mạnh hơn `server-test đếm request` khi client có bọc `fetch`.

### 2. ✅ `M14` bị giết, và **đồng bằng chứng chỉ chênh ĐÚNG MỘT bài**

`[witness] "if (affected.length === 0 && laNhapThat) {" khop 1 lan ⇒ PRESENT` · `[mutant] bytes=24106` ·
`ℹ tests 134 / pass 131 / fail 3` · `✖ I1e: … (8301,4985ms)` · `[phuc hoi] readback.equals(HEAD) === true`.
**Ba bài lá đỏ = `I1e` + ĐÚNG 2 bài `EMPTY_DB` nền** (đã đỏ trên cây sạch) ⇒ **chênh lệch ĐÚNG MỘT bài**.
⇒ **Cách đọc một mutation sạch: nêu TÊN các bài đỏ và trừ đi phần nền — "fail 3" một mình không nói gì.**

### 3. ✅ `I1e` điều khiển thứ tự bằng **TÍN HIỆU**: `0` `setTimeout`/`sleep` trong thân nó

`I1e` lẻ **5/5 XANH**, thời lượng **325,7175 / 322,4157 / 326,5724 / 304,2552 / 320,6855 ms** (ngưỡng review đặt: **900 ms** và **450 ms** — **ĐẠT cả hai**),
**EXIT=0**. `grep` toàn tệp: **0** `setTimeout`/`sleep` trong thân `I1e` (**dòng 690–761**) — thứ tự do **CỜ `daDocTrangThai`**
mà cính cầu nối bật. **Đảo 14 khối `it`** trên bản sao **NGOÀI repo** (dùng **junction** cho `node_modules`/`.venv`):
**`14/14` EXIT=0 ×2**, `I1e` **286/320 ms**.

### 4. ⚠️ **TRẦN `waitFor` GIẢI THÍCH ĐƯỜNG ĐỎ CHẬM** — một cách chẩn đoán đáng chép

Câu hỏi tôi đặt ở vòng trước (*"vì sao đường ĐỎ của `M14` chậm **8282 ms**?"*) **nay đã được đo**:
đó là **trần `waitFor({timeout: 8000, interval: 25})`** của helper `choChu` (**dòng 215–223**) **hết hạn** —
và **số học khớp**: `8295,76 − 8000 = 295,76 ms` ≈ **thời lượng đường XANH (304–327 ms)**, thông điệp lỗi khớp đúng `moTa` (**dòng 750**).
**Và log HTTP dưới `M14` Y HỆT lượt xanh** ⇒ **KHÔNG có phép chờ ẩn nào trên đường XANH**.
⇒ **LUẬT: khi một đường ĐỎ chậm bất thường, hãy kiểm xem nó có đang CHỜ HẾT TRẦN `waitFor`/timeout không**
(`thời lượng đỏ − trần ≈ thời lượng xanh` là dấu hiệu), **và so TRACE I/O của mutant với lượt xanh** để loại trừ phép chờ ẩn.

### 5. Nợ của Task 9 — **hai Minor, một trong đó là RỦI RO XANH GIẢ cần nhớ**

- **`M-1` (RỦI RO THẬT, chưa sửa):** **`I1e` KHÔNG tự khẳng định TIỀN ĐỀ của nó** (`laNhapThat === true`, tức hàng `龍`
  **chưa duyệt tại thời điểm đọc**). Hôm nay tiền đề **đúng** (seed `approved=False`; `龍` chỉ có trong seed/comment/`I1e`;
  lần đọc về **TRƯỚC** `POST` **16–31 ms**) và **`M14` giết được** — **nhưng nếu một bài SAU này duyệt `龍` TRƯỚC `I1e`
  thì `I1e` sẽ XANH GIẢ và `M14` sẽ SỐNG SÓT** (phép phá tiền đề **chưa được chạy**).
  ⇒ **Việc cần làm khi có dịp chạm `frontend/src/screens/GlossaryScreen.test.tsx`:** thêm **MỘT dòng** khẳng định tiền đề
  (`assert.ok(... laNhapThat ...)`) hoặc **đọc trạng thái máy chủ để chứng minh hàng đang chưa duyệt** ngay trước khi thả.
  **Ghi vào sổ nợ; đừng để nó trôi.**
- **`M-2`:** đường **ĐỎ** tốn **8,3 s** vì khẳng định cuối **chờ hết trần 8000 ms** (toàn suite dưới `M14` = **35,1 s** vs **27,0 s** sạch).
  Chấp nhận được, nhưng đường nâng cấp rẻ: **hạ trần cho khẳng định cuối**, hoặc **khẳng định trên giá trị đã bắt được** thay vì chờ.
- **`M9`** (nhánh `glossary` của `App`): **không đường nào tới** (`setMode` **0** dispatch) ⇒ **nợ đã khai từ trước**.
- **Lệch đơn vị "bản dịch" vs "bản ghi"**: **nợ của ROUTE**.
- **`§4.4` khối dưới** chưa làm — **lý do nay đã ĐÚNG**: làm thế là **dựng lại `glossary_match.terms_in` ở client** (nguồn sự thật thứ hai) + N request.
- **`contract.test.ts:705`** vẫn chưa chạm.
- **Chưa ai nhìn thấy màn hình này trong trình duyệt thật** (`e2e` bị cấm).
- **Và điều review nói thẳng là CHƯA ĐO ĐƯỢC:** **không có bộ đếm PHÍA SERVER** — "tới server" chứng minh bằng `headers 200`
  + **giá trị mà chỉ route thật mới tính được**; nó **chỉ tự chạy lại `M14`**, **17 lượt mutation còn lại là đọc `run.log`** đã publish;
  và **lượt chạy HỎNG ĐẦU của `do-treo.mjs` không có log** (chỉ xác nhận `[L3 vao]` + `L3 = 1159,99 ms > 900 ms`).

## ⚠️ ERRATA #30 — Task 10: **Step 4 BẤT KHẢ và có hại**, **`EngineSelect` không có chỗ ở trong plan**, và **"Ollama đang tắt" là câu SAI**

Soát Task 10 trước khi giao. **Bốn lỗi, hai trong đó là loại đã gây hại ở Giai đoạn trước.**

### 1. 🔴 **Step 4 BẤT KHẢ** (chụp ảnh cần TRÌNH DUYỆT) **và chỉ dẫn "bật Ollama" là SAI + CÓ HẠI**

Step 4 viết: *"mở app và chụp lại … Rồi **bật** Ollama (`ollama serve` nền), tải lại, chụp lại"*. **Ba lỗi chồng lên nhau:**
- **Chụp ảnh BẤT KHẢ** — ERRATA #5 mục 3: Chromium chết ở Mojo named pipe; `npm run e2e` **bị cấm**. Không có ảnh nào tồn tại được.
- **Bối cảnh dòng 2685 SAI:** *"máy này hiện **Ollama đang tắt**"*. **Đo lại: `11434 LISTENING`, PID 3408** (đo nhiều lần suốt
  Giai đoạn 3). Ollama **ĐANG CHẠY**. Câu "đang tắt" là **dữ kiện GĐ1a đã cũ**, và chính đính chính ngay dưới (dòng 2687)
  vẫn giữ nguyên khung "đang tắt" ⇒ **hai câu trong cùng một khối mâu thuẫn với phép đo**.
- ⇒ **Và vì thế "bật Ollama" là một SIDE EFFECT LÊN MÁY NGƯỜI DÙNG** (tiến trình của họ, không phải của agent).
  **LUẬT: agent KHÔNG được bật/tắt/khởi động lại/giết tiến trình Ollama của người dùng.** Đã ghi thẳng vào brief Task 10 §1(b).

**Thay bằng phép đo ĐO ĐƯỢC:** gọi `/api/status` + `/api/registry` **thật** (backend thật, DB scratch ngoài repo, tự tắt),
**dán nguyên văn thân JSON**, và **nói rõ trạng thái `ollama` ĐỔI THEO LÚC** (đã đo `unknown` **và** `up`; **`down` CHƯA TỪNG đo được**)
⇒ **cấm kết luận từ một lần đo**. Phần *hình thức* của panel: **khai là CHƯA chứng minh** (không có trình duyệt).
⇒ **Và đây là lần thứ TƯ một mệnh đề "bất khả" trong plan bị phép đo lật** (ba lần trước: `npm i`, jsdom + Testing Library,
trình duyệt). **LUẬT: mọi bước "mở app và nhìn" trong plan này đều phải bị coi là CHƯA KIỂM trước khi giao.**

### 2. ⚠️ **`EngineSelect` được Steps 1–3 ĐÒI nhưng KHÔNG có trong `Files` lẫn `## File Structure`**

Step 1 render `<EngineSelect …>`, Step 2 *"viết `OllamaDown.tsx` **+ `EngineSelect`**"*, Step 3 mutate nó —
nhưng mục `Files` (dòng 2694–2695) chỉ có `OllamaDown.tsx`/`.test.tsx` + `Header.tsx` + `App.tsx`,
và bảng `## File Structure` (dòng 1870–1872) **không có `EngineSelect`**.
⇒ **Một component không có chỗ ở là một component sẽ nằm nhờ trong tệp khác** ⇒ **mutation `O1` (bỏ lọc) sẽ chạm CÙNG tệp
với panel** ⇒ một mutation, hai chủ đề, không quy được trách nhiệm.
⇒ **Brief chốt: `frontend/src/shell/EngineSelect.tsx` + `.test.tsx`** (**tách tệp**), và **`ERRATA` này bổ sung nó vào `File Structure`**.
⇒ **LUẬT: một mục `Create` trong `Files` phải phủ HẾT mọi định danh mà Steps nhắc tới; nếu Steps render `<X/>` thì `X` phải có tệp.**

### 3. ✅ Điều plan làm ĐÚNG — và phải giữ: **màn phải hiện với CẢ `down` LẪN `unknown`**

Đính chính dòng 2687–2691 là **đúng và quan trọng** (cổng **timeout** chứ không **refused** ⇒ `unknown`). Brief Task 10 biến nó
thành **ba bài test cho ba trạng thái** (`up`/`down`/`unknown`) + **ba mutation tương ứng** (`O2` bỏ `unknown`, `O3` hiện cả khi `up`),
thay vì một mutation duy nhất của Step 3. **Và cấm đổi `probe_ollama` trả `down`** — `unknown` là **giá trị THẬT** ("chưa đo được").

### 4. ⚠️ **Bẫy `vitest`/`jest-dom`/`user-event` lại tái xuất** (Step 1) — và `available` là **nguồn sự thật thứ hai** nếu suy lại

Step 1 dùng `expect(...).toBeInTheDocument()` ⇒ **`node:test` + `node:assert/strict`**; **`user-event` KHÔNG có trong repo** ⇒ `fireEvent`.
Và **ràng buộc dòng 2722 (đọc thẳng `available`) phải được MÃ HOÁ THÀNH MUTATION `O6`** — một ràng buộc chữ không có mutation
là một ràng buộc chưa được bảo vệ.
⚠️ Và **`app.css` phải nằm trong `Files`** (ERRATA #16 mục 4) vì Task 10 **thêm hình thức** (dải trạng thái + panel).

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
  ⚠️ **NGOẠI LỆ (ERRATA #19 mục 7):** một glyph **được SPEC UI CHỈ ĐỊNH làm dấu hiệu NỘI DUNG** thì **phải render**.
  Spec UI §4.3 nguyên văn: *"Dòng vượt ngưỡng đọc có `⚠` màu amber."* — và **`grep -i emoji` trên SPEC = 0**,
  tức **spec KHÔNG cấm emoji**; lệnh cấm này là **của PLAN**, và plan từng khai nó *"không mâu thuẫn spec UI"* ⇒ **plan tự mâu thuẫn**.
  **Spec UI là nguồn có thẩm quyền về HÌNH THỨC** ⇒ glyph `⚠` **phải có** ở dòng vượt ngưỡng, **kèm** mốc amber ở lề
  + `data-over-cps` (hai thứ đó phục vụ **tiếp cận**). Luật này **vẫn hiệu lực cho mọi thứ khác**: không trang trí,
  không icon cảm xúc, không emoji trong alt/nhãn tuỳ tiện.
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
| `src/shell/EngineSelect.tsx` | dropdown engine — **lọc theo `capabilities.available === true` đọc thẳng từ `/api/registry`** (bổ sung bởi **ERRATA #30 mục 2**) |
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
- Modify: `frontend/src/shell/App.tsx`
- ⚠️ **ĐÍNH CHÍNH (Task 4, `00535e1`):** `Header.tsx`, `ChannelZone.tsx`, `QueueZone.tsx` **CHƯA BAO GIỜ TỒN TẠI**
  (`git log --all --name-only -- frontend/src/shell` chỉ có `App.tsx` từ `a2fffe1`) ⇒ chúng là **CREATE**, không phải Modify.
  Bản cũ của dòng này ghi "Modify" cả ba — **sai**, và brief của người điều phối đã chép lại nguyên si.

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
- ⚠️ **ĐÍNH CHÍNH (ERRATA #16 mục 4/5):** Task 7 **thực tế** còn phải **tạo `frontend/src/lib/playback.ts` + `playback.test.ts`**
  (để quyết định "tới mốc cuối thì sang đoạn kế" chạy được bằng `node:test` thường) và **sửa `frontend/src/styles/app.css`**
  (+101 dòng: `.tp__timecode`, `.tp__track`, `.tp__readhead`). **Bất kỳ task nào thêm HÌNH THỨC đều phải liệt kê `app.css`.**

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

> ⚠️ **ĐÍNH CHÍNH (ERRATA #30 mục 1): câu "máy này hiện Ollama đang tắt" ở trên là SAI và ĐÃ CŨ** — đo lại nhiều lần:
> **`11434 LISTENING`, PID 3408**; Ollama **ĐANG CHẠY**. Và `ollama` trả về **đổi theo lúc** (`unknown` **và** `up`; **`down` chưa từng đo được**).
> ⇒ **KHÔNG bật/tắt/`ollama serve`/giết PID 3408** — đó là tiến trình của NGƯỜI DÙNG.

**Bối cảnh đã đo:** máy này hiện **Ollama đang tắt**, nên đây không phải tình huống giả định — nó là trạng thái thật khi bạn mở app lần đầu. Dùng luôn nó để kiểm.

> 🔴 **ĐÍNH CHÍNH CỦA TASK 2 — câu "Ollama đang tắt" ở trên chỉ đúng MỘT NỬA, và màn này sẽ KHÔNG HIỆN nếu bạn làm theo trực giác.**
> Task 2 đo `/api/status` trên chính máy này: nó trả **`ollama: "unknown"`**, KHÔNG phải `"down"`. Vì cổng 11434 **timeout** (~300 ms, 3/3 lần) chứ không **refused** ⇒ `urlopen` bọc thành `URLError(reason=TimeoutError)` ⇒ `probe_ollama` rơi vào nhánh "chưa đo được" ⇒ `unknown`.
> ⇒ **Màn §4.8 phải hiện với CẢ `down` LẪN `unknown`.** Nếu bạn chỉ khoá theo `ollama === "down"` thì màn này **không bao giờ hiện trên máy này**, và mọi ảnh chụp nghiệm thu sẽ là màn trống — mà bạn sẽ tưởng component hỏng.
> Đừng "sửa" bằng cách đổi `probe_ollama` cho nó trả `down`: spec nói `unknown` là một giá trị **THẬT** ("chưa đo được"), biến nó thành `down` là **bịa ra một sự thật chưa đo** (docstring `probe_ollama` trong `backend/app/api/routes_registry.py` giải thích đúng điều này).
> Ví dụ render ở Step dưới dùng `ollama: "down"` — giá trị đó vẫn hợp lệ để kiểm, nhưng **phải có thêm một ca `unknown`**.

**Files:**
- Create: `frontend/src/screens/OllamaDown.tsx`, `frontend/src/screens/OllamaDown.test.tsx`
- Create: `frontend/src/shell/EngineSelect.tsx`, `frontend/src/shell/EngineSelect.test.tsx` (**bổ sung bởi ERRATA #30 mục 2** — Step 1/2/3 đòi nó mà mục `Files` gốc không có)
- Modify: `frontend/src/styles/app.css` (Task này **thêm hình thức** — ERRATA #16 mục 4)
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

- [ ] **Step 4: ĐO TRÊN MÁY THẬT — bản đã sửa (ERRATA #30 mục 1; bản gốc "chụp ảnh" là BẤT KHẢ)**
  - Gọi `/api/status` + `/api/registry` **thật** (backend thật, DB scratch **ngoài repo**, cổng trống, **tự tắt**), **dán nguyên văn thân JSON**,
    và **nói rõ trạng thái `ollama` đo được lúc đó** — kèm câu nói rõ **nó ĐỔI THEO LÚC** (`unknown`/`up` đều đã đo; `down` chưa từng) ⇒ **không kết luận gì từ một lần đo**.
  - ⚠️ **KHÔNG bật/tắt/`ollama serve`/giết PID 3408.** Không có ảnh chụp nào (không có trình duyệt) ⇒ **hình thức panel khai là CHƯA chứng minh**.
  - Ba trạng thái `up`/`down`/`unknown` được kiểm **bằng props** (ba bài test + ba mutation `O2`/`O3`), không bằng cách đổi máy.

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



