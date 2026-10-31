# phu-de-lab

Bàn làm việc phiên âm và dịch video Trung → Việt. Backend Python (FastAPI), frontend React 19 + TypeScript
build bằng **Rollup** (Vite đã bị loại — xem mục "Không dùng Vite").

## Chạy frontend

Hai tiến trình, hai cổng: **backend 8620**, **frontend 3100**.

```powershell
# 1) backend — http://127.0.0.1:8620
backend\.venv\Scripts\python.exe backend\run_api.py

# 2) frontend — http://127.0.0.1:3100
cd frontend
npm run dev
```

Mở **http://127.0.0.1:3100**.

Hai lệnh trên đã được **chạy thật** ở lượt viết tài liệu này (cây ở HEAD, cổng 8620/3100 trống trước khi chạy):

```
backend\.venv\Scripts\python.exe backend\run_api.py
  → GET http://127.0.0.1:8620/api/status  →  HTTP 200
    {"queue_depth":0,"running":[],"current_phase":null,"phase_switches":0,"vram":null,"ollama":"up"}
  → 8620 LISTENING

cd frontend; npm run dev
  → GET http://127.0.0.1:3100/           →  HTTP 200 (365 B)
  → GET http://127.0.0.1:3100/api/status →  HTTP 200  (proxy sang 8620, CÙNG thân JSON ở trên)
  → 3100 LISTENING
```

`npm run dev` chạy `frontend/dev-server.mjs`. Nó **tự build trước khi phục vụ**: Rollup được gọi
trong chính tiến trình đó (không `child_process`) và theo dõi tệp, rồi server phục vụ
`frontend/dist/` và proxy `/api/...` sang backend — nên lúc phát triển không có CORS. Sửa mã →
Rollup build lại (~0,3 s) → F5. **Không cần `npm run build` tay khi đang dev.**
Request đầu tiên chờ build đầu tiên xong; `GET /` trả `200`, không phải `404`.

### Cổng nào cấu hình được, cổng nào **KHÔNG**

| | Biến | Mặc định | Nguồn |
|---|---|---|---|
| backend | `PHUDE_HOST` | `127.0.0.1` | `backend/app/config.py:30` |
| backend | `PHUDE_PORT` | `8620` | `backend/app/config.py:31` |
| backend | `PHUDE_DB` | `<PHUDE_DATA>/app.db` | `backend/app/config.py:23` |
| backend | `PHUDE_DATA` | `backend/../data` | `backend/app/config.py:19` |
| dev-server | `PHUDE_BACKEND_PORT` | `8620` — **đích của proxy `/api`** | `frontend/dev-server.mjs:33` |
| dev-server | *(không có)* | `3100` — **CỨNG** | `frontend/dev-server.mjs:22` |

🔴 **CHỈ cổng BACKEND cấu hình được.** Cổng dev-server `3100` **cứng**, và đó là một QUYẾT ĐỊNH:
backend chỉ whitelist CORS đúng hai origin `http://localhost:3100` và `http://127.0.0.1:3100`
(`frontend/dev-server.mjs:30-32`). Đổi cổng dev-server là hỏng CORS, mà sửa CORS thì phải chạm
`backend/`. Server bind tường minh `127.0.0.1` — trên Windows `localhost` phân giải thành `::1`,
chỉ bind IPv6 là hỏng một trong hai origin.

Nếu cổng 3100 đang bị chiếm, dev-server **in thông báo rồi thoát** (`exit 1`), **không** tự nhảy
sang cổng khác (giữ nguyên tính chất strict-port).

### Không dùng Vite

Môi trường dựng hiện tại chặn named pipe, mà Vite 6 không có đường pre-bundle dependency nào ngoài
`esbuild` (tiến trình con với `stdio:'pipe'` → `EPERM`). Rollup chạy trong tiến trình nên không
chạm named pipe. `vite.config.ts` **không còn** trong repo và đừng thêm lại.

### Script trong `frontend/package.json`

| Lệnh | Việc |
|---|---|
| `npm run dev` | `node dev-server.mjs` — build-on-demand + watch + proxy, cổng 3100 |
| `npm run build` | `tsc --noEmit && rollup -c` → `frontend/dist/` |
| `npm run typecheck` | `tsc --noEmit`, không sinh tệp |
| `npm test` | `node --test --test-isolation=none` + loader SWC trong tiến trình. **Xem mục "Chạy contract test"** |
| `npm run e2e` | Tầng **CHROME THẬT**: `node e2e/session.mjs e2e/plans/bon-man.json --out e2e/anh` |
| `npm run e2e:phim` | `... e2e/plans/phim-va-12-5.json --out e2e/anh` (§11.4 + §12.5 bằng bàn phím thật) |
| `npm run e2e:t7` | `... e2e/plans/ban-ghi-dai-t7.json --out e2e/anh` (C1 + T7) |

`npm run build` chạy `tsc --noEmit` **trước** `rollup -c`, vì `rollup -c` một mình không kiểm kiểu:
thiếu bước đó thì một "build xanh" vẫn có thể kèm type sai.

⚠️ **`npm run e2e` KHÔNG còn là Playwright.** Script `playwright test` đã bị bỏ; tầng Chrome thật
dùng **CDP thuần** trong `frontend/e2e/`. Ba lệnh `e2e*` ghi ảnh vào `frontend/e2e/anh/` —
thư mục đó **đã được gitignore** (`.gitignore:14`), nên chạy xong `git status` vẫn RỖNG.
Đó **không** phải một phần của `npm test`: xem mục "Tầng CHROME THẬT" bên dưới.

### Test chạy bằng gì

**Không có Vitest** trong repo này (Vitest dựng trên Vite nên cũng chết). Có **`jsdom`** và
**`@testing-library/react`** trong `devDependencies`, và chúng chạy **thật**: harness
`frontend/test/dom.ts` dựng jsdom (`setupDom`) rồi test `await import("@testing-library/react")`
sau đó — vì React đọc `window`/`document` lúc nạp. Runner là runner có sẵn của Node 24:

- `.ts`/`.tsx` do `frontend/test/swc-loader.mjs` bóc (`module.registerHooks` + `@swc/core`, chạy
  trong tiến trình, không spawn).
- Test cấu trúc component dùng `react-dom/server.renderToStaticMarkup` — render React thật, không
  cần DOM; test có tương tác (click, focus, bàn phím, effect, state update) chạy trên jsdom qua
  `test/dom.ts`.
- ⚠️ **jsdom KHÔNG có layout, KHÔNG áp CSS, và KHÔNG hiện thực `play()`/`pause()`** ⇒ mọi khẳng
  định **hình thức** (bố cục, màu, kích thước, ảnh, font, bàn phím VẬT LÝ) **không** đến từ tầng
  này. Chúng đến từ **tầng Chrome thật** hoặc từ **ảnh** — hai lớp bằng chứng khác hẳn.

Hai chi tiết của lệnh test đều **bắt buộc**, thiếu là chết:

- `--test-isolation=none` — không có nó, runner spawn tiến trình con cho mỗi tệp test và chết
  `EPERM`.
- `--import ./test/swc-loader.mjs` — không có nó, mọi tệp `.tsx` chết
  `ERR_UNKNOWN_FILE_EXTENSION`. Kèm theo đó, script truyền glob
  `"**/*.test.{ts,tsx,mjs,js}"` vì discovery mặc định của Node 24 có chạy `.test.ts` nhưng
  **không** chạy `.test.tsx`.

### Chạy contract test — **PHẢI để 8620/8621 TRỐNG**

`src/api/contract.test.ts` chạy trên **backend THẬT**, không mock:

1. Nó **tự spawn** backend ở **8620** (`backend/.venv/Scripts/python.exe run_api.py`, cwd
   `backend/`) và đo trên **DB mà tiến trình con THỪA HƯỞNG** — `spawn` **không** truyền `env`,
   nên con đọc `PHUDE_DB`/`PHUDE_DATA` của **shell đang chạy**, và khi hai biến đó trống thì rơi
   về `data/app.db`. Khối này chỉ đo được trên DB **RỖNG**.
2. Nhánh **200** của route chi tiết nằm ở một backend **THỨ HAI, cổng 8621**, có DB gieo riêng
   (`PHUDE_DB`/`PHUDE_DATA`/`PHUDE_PORT`, `contract.test.ts:573-587,700`).

🔴 **VÌ VẬY: trỏ `PHUDE_DB`/`PHUDE_DATA` vào một thư mục RỖNG NGOÀI REPO trước khi chạy** —
`data/app.db` của workspace này **KHÔNG còn rỗng** (backend đã chạy thật ở các giai đoạn sau).
Đo được ngày `2026-10-25`, cùng một cây `d69ac3b`, hai môi trường:

| môi trường | kết quả | nghĩa |
|---|---|---|
| `PHUDE_DB`/`PHUDE_DATA` → thư mục rỗng ngoài repo | `tests 317 / pass 315 / fail 2 / cancelled 0`, EXIT=1 | **ĐÚNG** (hai bài đỏ DB-rỗng) |
| mặc định (con đọc `data/app.db` đã có dữ liệu) | `tests 317 / pass 307 / fail 0 / cancelled 10`, EXIT=1 | **LƯỢT BẨN** — 10 bài bị `before` HUỶ, không đo gì |

Dòng thứ hai là đúng cái bẫy mà mục này đang cảnh báo, chỉ đổi chiều: `fail 0` **trông đẹp hơn**
nền thật trong khi thực ra **không bài nào trong khối đó chạy**. Luật "`fail 0` mà `EXIT ≠ 0` là
lượt bẩn" (dưới) bắt được nó; đừng đọc `pass/fail` mà bỏ `cancelled`.

Lượt đo của tài liệu này (8620/8621 trống — kiểm bằng `Get-NetTCPConnection -LocalPort 8620`;
`PHUDE_DB`/`PHUDE_DATA` trỏ thư mục rỗng ngoài repo):

```
ℹ tests 370   ℹ suites 35   ℹ pass 368   ℹ fail 2   ℹ cancelled 0
ℹ skipped 0   ℹ todo 0      ℹ duration_ms 35486.345
EXIT=1
0 dòng "asynchronous activity" ; [guard thoat] 10/10 global da ve nguyen trang
```

Số **370** = **361** của lượt trước + **9 bài MÀN LỒNG TIẾNG** (tab thứ tư), và mỗi bài ghim một
lỗi ĐO ĐƯỢC trên app thật chứ không phải một quy ước:

* `src/screens/LongTiengScreen.test.tsx` (**9**): màn riêng thay cho khối nhét trong Đối chiếu —
  ba tầng của demo (cột kênh, dải thời gian, bảng dòng); ba trạng thái `vừa chỗ`/`nén`/`phải sửa`
  nói bằng CHỮ; `plan === null` KHÔNG được vẽ một dải rỗng trông như đã đo; bốn trạng thái của job
  (đang chạy có nút HUỶ, hỏng thì lỗi gọn trong `<details>` mà cửa vào VẪN mở); đổi kênh thì lựa
  chọn bản dịch cũ không được đi theo; cột `#` đếm từ 1 trong khi `take?i=` vẫn 0-based; và phép
  ghim hai chiều `.lt*` ↔ `app.css`.

⚠️ **Ba lỗi nữa chỉ ẢNH CHỤP mới bắt được, và cả ba đều đã sửa:**
1. `getDubPlan` gọi `/api/dubs/...` trong khi `api.get` đã ghép `BASE = "/api"` ⇒ URL thật là
   `/api/api/dubs/10/plan` ⇒ 404. Đo được trên app thật: gọi từ trong trang thì đường ĐÚNG trả
   200 (`null`), còn màn vẫn hiện "không đọc được số đo: 404: Not Found". Mutation: trả lại đường
   lặp ⇒ `pass 2 / fail 6`, thông điệp in đúng `/api/api/dubs/11/plan`.
2. Ba câu "chưa đo" khác nhau cho ba nguyên nhân khác nhau — bản đầu nói "chọn một bản dịch" cả
   khi CHƯA CHỌN KÊNH, tức chỉ sai việc phải làm.
3. Cột `#` in thẳng `s.i` (0-based) nên hiện `00, 01, 02…`; ảnh chụp cho thấy nó lệch một so với
   cột `GIỜ`. Sửa ở chỗ HIỂN THỊ, còn `data-testid` và `take?i=` giữ chỉ số gốc.

⚠️ **Hai lần bài test này XANH GIẢ, và cả hai đều bị bắt bằng mutation:**

1. Bài "đổi kênh" đầu tiên render HAI instance riêng biệt, nên nó xanh kể cả khi bỏ `useEffect`
   reset — mutant SỐNG (`pass 8 / fail 0`). Sửa sang `rerender` CÙNG instance thì đo lại mới đúng
   cơ chế.
2. Đo lại lần hai phát hiện `useEffect` reset đó **là mã chết**: bỏ nó đi, `aria-checked` của bản
   dịch kênh mới VẪN là `"true"`, vì `find` trượt thì `chon` tự rơi về `macDinhId`. Nó đã bị XOÁ,
   và lý do đo được ghi ngay chỗ nó từng nằm.

Phép ghim CSS mới cũng được kiểm mutation: đổi `.lt__take--phai-sua` → `…X` (luật mồ côi) và xoá
luật `.lt__dem-dai` (lớp không luật) đều làm bài hình thức ĐỎ với đúng tên lớp; khôi phục thì xanh.

**2 bài của lượt trước** vẫn nguyên:
* `src/screens/CompareScreen.test.tsx` (**1**): bốn trạng thái của job `dub` nói bằng CHỮ, năm
  đường tải dựng từ id, và — quan trọng hơn — **job `failed` KHÔNG được khoá nút**: bản đầu đặt ô
  giọng + nút trong nhánh `dub === null`, nên một lượt hỏng làm mất luôn đường thử lại (đo trên
  app thật: `co_o_giong: false`, `co_nut: false`). Nó cũng ghim câu lỗi dài nằm trong `<details>`
  (`summary` nói trạng thái bằng chữ, nguyên văn `job.error` ở trong) — trước đó khối rộng 2004 px
  và chữ tràn ra ngoài khung.
* `src/shell/App.test.tsx` (**1**): job `dub` `failed` KHÔNG được đại diện cho bản dịch trong
  `dubJobCuaBan`, nên cửa vào vẫn mở. Bài này đi qua `App` thật trên server `node:http` trong tiến
  trình — không gọi hàm cục bộ, vì gọi thẳng nó là đo một bản sao.

Đã kiểm **mutation** cho phép ghim CSS mới: đổi `.dub__loi` → `.dub__loi-bay` (và cả `.dub__loiX`)
làm bài "mồ côi" của `CompareScreen.test.tsx` **ĐỎ** với thông điệp nêu đúng tên lớp mồ côi; khôi
phục thì xanh. ⚠️ Lượt đầu nó **SỐNG** với hậu tố CHỮ HOA vì regex lớp chỉ có `[a-z0-9_-]` — đã
thêm `A-Z` và ghi lý do ngay trong bài.

**7 bài của lượt sửa trước** (ERRATA #50 + #51) vẫn nguyên:

* `src/styles/hinh-thuc.test.ts` (**5**): `.ch__ten` phải `overflow-wrap: anywhere`, và
  `nginx.conf` phải nâng `client_max_body_size` + trả JSON cho `413` + `no-cache` cho bản tĩnh.
* `src/shell/ChannelZone.test.tsx` (**1**): NỀN của mục đang chọn thuộc về **HÀNG**
  (`li.ch__dong.is-chon`), không thuộc nút chọn — nền khai trên nút hụt đúng phần nút co lại để
  nhường chỗ cho `xóa`/`hủy` (đo được: hàng 213 px vs nút 182 px, và 145 px khi hiện hai nút).

Đã kiểm **mutation** cho cả hai: `anywhere` → `break-word` và `2048m` → `1m` làm đúng hai bài của
`hinh-thuc` đỏ (`pass 3 / fail 2`); bỏ luật `.ch__dong.is-chon` (hoặc trả `background` về
`.ch__item[aria-pressed="true"]`) làm bài nền đỏ; bỏ lớp `is-chon` khỏi TSX cũng làm nó đỏ.

🔴 **Trước mọi lượt `npm test`, 8620 và 8621 phải TRỐNG.** Nếu ai đang giữ 8620, khối hợp đồng
nhận một server LẠ đã gieo dữ liệu là "backend dùng được": hai guard DB-rỗng thành **XANH** và
toàn bộ `fail` **DỊCH ĐI HAI** — đo được **cả hai trạng thái trên CÙNG một cây byte-exact**:
`pass 254 / fail 0 / EXIT=0` khi 8620 bị chiếm, `pass 252 / fail 2 / EXIT=1` khi 8620 trống
(`contract.test.ts:104-109`, ERRATA #46 mục 4).

**HAI BÀI ĐỎ KHI DB RỖNG LÀ ĐÚNG TRẠNG THÁI**, không phải lỗi. Chúng đỏ vì DB của repo rỗng nên
bài **không đo được gì**, và "xanh vì rỗng là im lặng" — đúng thứ spec từ chối
(`contract.test.ts:348-350,382-387`). Trên cây hiện tại, **đúng HAI** tên đỏ:

```
✖ GET /api/transcripts: hàng tóm tắt có translations[] và KHÔNG kèm segments
✖ GET /api/transcripts/{id}: Transcript + Segment (suspect LUÔN có, khoá khác tuỳ engine)
```

🔴 **Phép đo hợp lệ là DANH SÁCH TÊN BÀI ĐỎ, KHÔNG phải `fail − 2`.** Nền này **không hermetic**:
`fail` là một thuộc tính của **MÔI TRƯỜNG**, không phải của commit (chính vì thế con số dịch đi
hai khi 8620 bị chiếm). Ai áp `fail − 2` sẽ ra số ÂM hoặc thiếu. Và theo ERRATA #47 mục 1:
**một lượt có `fail 0` mà `EXIT ≠ 0` là LƯỢT BẨN** — phải kiểm `EXIT` + `uncaughtException`,
không chỉ `pass/fail`.

### Tầng CHROME THẬT (`frontend/e2e/`)

Tầng này mở **Chrome thật** và đo **HÌNH THỨC** (layout, CSS, ảnh, font, bàn phím) — thứ jsdom
**không** làm được. **jsdom = HÀNH VI/DOM. Chrome thật = HÌNH THỨC. Hai tầng, không phải một.**

```powershell
cd frontend
npm run e2e                              # bon-man   -> 8 ảnh
npm run e2e:phim                         # §11.4 + §12.5 -> 4 ảnh
npm run e2e:t7                           # C1 + T7   -> 4 ảnh
# hoặc chỉ định chỗ ghi ảnh NGOÀI repo:
node e2e/session.mjs e2e/plans/bon-man.json --out <thư mục NGOÀI repo>
```

- 🔴 **KHÔNG nằm trong `npm test`.** Ba lệnh trên đã được chạy thật ở lượt viết tài liệu này:
  **`EXIT=0` cả bốn lượt** (ba lệnh `npm run e2e*` ghi vào `frontend/e2e/anh/`, và một lượt
  `--out` ra ngoài repo).
- **Cổng riêng: 8631** (backend, `PHUDE_E2E_PORT`) · **3100** (dev-server, `PHUDE_BACKEND_PORT=8631`)
  · **9229** (CDP, `PHUDE_CDP_PORT`). **Không bao giờ** là 8620/8621.
- **Nó TỪ CHỐI chạy nếu 8620/8621 đang mở** — đó là cổng CÓ CHỦ của `contract.test.ts`
  (`e2e/session.mjs:162-165`).
- ⚠️ **Cần QUYỀN RỘNG**: trong sandbox bị hạn chế, **Chromium chết**
  (`FATAL:mojo… Access is denied (0x5)`). Mệnh đề đúng là *"Chromium không mở được DƯỚI CÁC CHẾ ĐỘ
  SANDBOX HẠN CHẾ"* — ERRATA #40; dưới `danger-full-access` thì chạy được.
- Một lượt chỉ được coi là **ĐẠT** khi **`EXIT=0`**: một bước `khangDinh` sai, hoặc một bước `key`
  có đầu dò `keydown` RỖNG, đều làm lượt chạy `EXIT=1`.

📄 **Đọc thêm (hai tệp, không chép lại nội dung ở đây):**
- **`frontend/e2e/README.md`** — cách chạy, biến môi trường, ba quy tắc cứng đã cài trong mã, và
  **cái tầng này KHÔNG chứng minh**.
- **`frontend/e2e/TIEU-CHI-12.md`** — **BẢNG TIÊU CHÍ §12** (bằng chứng nghiệm thu), **được TRACK
  trong git**. Mỗi dòng **đúng MỘT lớp bằng chứng** (`TÊN BÀI TEST` / `ẢNH` / `ĐO COMPUTED STYLE`
  / `CHƯA ĐO`), kèm **danh sách TRẦN có chủ**, cách tái lập, và số đo hình thức. Đây là **nguồn
  duy nhất** của bảng đó — **đừng viết lại nó ở chỗ khác.**

**Ảnh thô + `ket-qua.json` nằm NGOÀI repo** (không commit, và không nên commit):
`C:\Users\Admin\Desktop\ngn\deepseek\_shots\t12b\` (lượt sau cùng, **đã có C1 sửa** — 16 ảnh +
`ket-qua.json`) và `...\_shots\t12\` (lượt trước — 15 ảnh + `ket-qua.json`). Lệnh tái sinh chính là
ba lệnh `npm run e2e*` ở trên (hoặc thêm `--out <đường dẫn ngoài repo>` để ghi ra chỗ khác).

**Ảnh chỉ chứng minh BỐ CỤC/VẺ.** Chúng **không** chứng minh chất lượng bản dịch, **không** chứng
minh hành vi, và **không** chứng minh một cú bấm phím VẬT LÝ.

### Cài dependency

`frontend/node_modules/` **đã có sẵn** trong cây làm việc hiện tại. Trên một máy sạch thì bước đầu
là `cd frontend; npm install` — nhưng ở môi trường dựng hiện tại lệnh đó **có thể chết `EPERM`** ở
cache npm, nên đừng chạy lại khi `node_modules/` đã có.
⚠️ **ĐÍNH CHÍNH (review cuối Task 13, `I1`):** câu cũ ở đây nói *"`package-lock.json` đang cũ (nó mô tả
cây Vite cũ), vì vậy `npm ci` sẽ fail"* — **SAI**. Đo được: lock (1 963 dòng) có **0** hit
`vite`/`vitest`/`playwright`; khối gốc `:7-24` **trùng khít** `package.json`; lock **đã tái sinh** khi bỏ
Vite (`ffe8613` có 4 hit → `bc0dcae` có 0). Và `npm ci` **đã chạy THÀNH CÔNG** trong chính phiên này —
`npm ci --prefer-offline --no-audit --no-fund` ⇒ **EXIT=0, 71 gói, 12,5 s** — sau khi `node_modules` bị
xoá nhầm; `npm ls --depth=0` sau đó cho **đúng 9 gói**, không thiếu/không lạ.

Cấu hình frontend: `frontend/rollup.config.mjs` (build) · `frontend/dev-server.mjs` (cổng, proxy,
watch) · `frontend/tsconfig.json` (kiểu) · `frontend/test/swc-loader.mjs` (loader test) · token
thiết kế ở `frontend/src/styles/tokens.css` (giá trị chép từ
`docs/superpowers/specs/2026-09-25-phu-de-lab-ui-design.md` §2).

Chi tiết backend: `backend/README.md`.

## Chạy bằng Docker

Hai service, một lệnh — **có GPU và có Ollama**:

```powershell
docker compose up --build      # web http://127.0.0.1:3100 · api http://127.0.0.1:8620
```

Lần đầu `api` tải model (~1,6 GB) vào volume `hf-models`, nên phút đầu chậm — `healthcheck`
có `start_period: 120s` vì lý do đó.

**TRONG image**: FastAPI + `ffmpeg` (bắt buộc cho job `ingest`) + faster-whisper + **torch CUDA**
+ opus-mt; `nginx` phục vụ bản tĩnh và proxy `/api` (tắt `proxy_buffering` cho SSE).
**GPU**: `gpus: all` — cả `opus-mt` (torch) lẫn `faster-whisper` (CTranslate2 + cuBLAS) chạy
trên card. **Ollama KHÔNG nằm trong compose**: container trỏ về Ollama của **máy chủ**
(`OLLAMA_HOST=http://host.docker.internal:11434` + `extra_hosts: host-gateway`), nên 4 engine
MT (`opus-mt`, `qwen2.5-3b`, `qwen2.5-7b`, `hy-mt-1.5-7b`) đều `available: true` — không chép
5 GB model vào volume thứ hai.

Bốn chỗ **phải** sửa để image chạy được — mỗi chỗ là một lượt chạy ĐỎ, không phải suy luận:

| triệu chứng | nguyên nhân | cách sửa (đã có trong repo) |
|---|---|---|
| map cổng ra ngoài không tới | `API_HOST` mặc định `127.0.0.1`: trong container là chỉ nghe loopback | `PHUDE_HOST=0.0.0.0` |
| `asr` FAILED: *CUDA driver version is insufficient* (khi image chưa có GPU) | adapter mặc định `cuda`, container không có driver | `gpus: all` + `PHUDE_ASR_DEVICE=cuda` (`cpu` cho máy không GPU) |
| `asr` FAILED: *Library cublas… is not found* dù có GPU | CTranslate2 `dlopen` cuBLAS theo đường NẠP; `ensure_cuda_runtime()` chỉ chèn `PATH` (đúng cho Windows) | `LD_LIBRARY_PATH=…/torch/lib` trong `Dockerfile` |
| `translate` FAILED: *MarianMTModel requires the PyTorch library* | `opus-mt` cần torch | cài `torch==2.5.1` **riêng** với index `whl/cu121` (để index đó trong `requirements` thì pip hỏi host đó cho mọi gói và build FAILED vì ReadTimeout) |

Hai chỗ **nữa** — không làm image hỏng, mà làm **đường web** sai (đúng đường người dùng đi), cả hai
đều là lượt dùng THẬT chứ không phải suy luận:

| triệu chứng | nguyên nhân | cách sửa (đã có trong repo) |
|---|---|---|
| nạp một tệp thật ⇒ `413: Request Entity Too Large`, câu **tiếng Anh**, và **không** có dòng nào trong log `api` | `client_max_body_size` mặc định của nginx là **1 MB** — tệp thử trong repo đã **8,5 MB** nên MỌI tệp thật bị chặn Ở PROXY, trước khi tới FastAPI; body lỗi là HTML nên `client.ts` rơi về `statusText` | `client_max_body_size 2048m` + `error_page 413` trả JSON `{"detail": …}` **tiếng Việt** |
| build lại ảnh xong, trình duyệt vẫn chạy **bản CŨ** (đo được: CSS trong ảnh có `overflow-wrap: anywhere`, Chrome vẫn báo `normal`) | Rollup xuất tên **cố định** `index.js`/`index.css` ⇒ URL không đổi khi nội dung đổi, và nginx không gửi `Cache-Control` nào | `add_header Cache-Control "no-cache"` cho `/assets/` và `/` (vẫn `304` khi tệp không đổi) |

Lượt xác nhận (Docker 29.4.2 + Compose v5.1.3, RTX 3070):

| phép đo | kết quả |
|---|---|
| `nvidia-smi` trong container | `2995 MiB` (card thấy được) |
| `/api/status` | `vram: 3013 MiB` + `vram_unit: MiB`, `ollama: up` |
| `/api/registry` | 4/4 engine MT `available: true` |
| ASR trong container (GPU) | **12,3 s** cho clip 278 s (CPU phải vài phút) |
| dịch qua Ollama của máy chủ (`qwen2.5-3b`) | `done` sau **139,5 s**, export SRT **200 · 6 816 byte** |
| `web /` và `web /api/status` (proxy nginx) | **200** / **200** |
| nạp **8,5 MB** qua **nginx** (`:3100`) | **201** — trước khi sửa: **413** |
| khai `Content-Length` 5 GB (vượt trần) | **413** + `{"detail": "tệp quá lớn — … 2048 MB"}` |

⚠️ Bản dịch của `qwen2.5-3b` trong lượt đó **chép nguyên chữ nguồn** — đó là hành vi **đã ghi
trong tài liệu** của model này với chữ ASR thật (mục "CHƯA BIẾT" bên dưới), **không** phải lỗi
Docker. Máy không GPU: đổi `torch` sang bản `cpu` và bỏ `gpus: all` + `PHUDE_ASR_DEVICE`.
Ảnh: `api` **9,64 GB** (torch CUDA), `web` **97 MB**.

## CHƯA làm / CHƯA biết

Mục này **không tô hồng**. Câu nào chưa đo thì ghi **CHƯA ĐO**.

### ĐÃ LÀM (giai đoạn frontend này)

- **Bốn màn**: **Biên tập** (`screens/EditScreen.tsx`), **Đối chiếu** (`screens/CompareScreen.tsx`),
  **Thuật ngữ** (`screens/GlossaryScreen.tsx`), và **panel lỗi Ollama** (`screens/OllamaDown.tsx`).
- **Khung ba vùng** (`shell/App.tsx`: kênh · vùng giữa · hàng đợi) + **đường CHỌN KÊNH** (Task W1)
  + **đường NẠP TỆP** (Task W2).
- **Transport** (`shell/Transport.tsx`): phát/tạm dừng, timecode mono, track đầu đọc, ba nút xuất,
  tự nhảy sang đoạn kế khi phát tới mốc cuối.
- **Bảng phím tắt §11.4** và đường bàn phím §5.1/§12.5 (Task 11) — **`?` mở bảng phím tắt**.
- **Tầng Chrome thật** (`frontend/e2e/`) + **bảng tiêu chí §12 được TRACK**
  (`frontend/e2e/TIEU-CHI-12.md`).
- **Chimera §4.5** — làm ở nhánh `chimera`, có trên cây này sau lượt gộp: chip amber + dải cảnh
  báo chi phí + N ô ứng viên + dòng hợp nhất (`screens/CompareScreen.tsx`,
  `screens/CompareScreen.chimera.test.tsx`), kế hoạch Chrome 61 bước
  (`frontend/e2e/plans/chimera.json` + `seed-chimera.py`), ảnh + `ket-qua.json` ngoài repo
  (`_shots/chimera-2026-10-20/`), báo cáo bàn giao
  `.superpowers/sdd/2026-09-26-frontend-workspace-2/chimera-report.md`.
  ⚠️ **TRẦN đo được, đừng đọc dòng trên thành "Chimera tốt hơn":** với bộ ứng viên trên máy này
  (`qwen2.5-3b`/`qwen2.5-7b` **nhại bản nguồn** 6/6), bản hợp nhất **giống từng byte** bản của mỏ
  neo `opus-mt` ⇒ chế độ Chimera tiêu 6 lượt gọi để ra đúng thứ **một** lượt `opus-mt` cho ra.
  **Chi phí lưu ở transcript dài: ĐO ĐƯỢC bằng số học, không cần lượt chạy mới** — một hàng
  `chimera` thật trong `data/app.db` (105 đoạn, 6 ứng viên) chiếm **28 866 byte** ⇒
  **275 byte/đoạn** ⇒ 600 đoạn ≈ **0,16 MB** một bản dịch. `O(đoạn × ứng viên)` không phải
  một trần đáng lo. Còn **ETA trên hàng đợi** (§4.5): **không làm** — ước lượng hiện sai
  22–39% (luôn cao), nên một ETA là con số bịa; làm khi có mô hình chi phí đúng hơn.

### CHƯA LÀM (có chủ ý)

| Chưa làm | Ghi chú |
|---|---|
| **Bảng eval §4.6/§4.7** | ⚠️ **NGOÀI PHẠM VI THEO QUYẾT ĐỊNH CỦA NGƯỜI DÙNG** — giai đoạn này chỉ làm **bốn màn** (`frontend/e2e/TIEU-CHI-12.md:30`). Tiêu chí §12 số 7 giữ nguyên dòng, **không** xoá. |
| **Layout điện thoại** | chưa làm. |
| **Sáng/tối & đổi theme** | chưa làm. |
| **Kéo-thả sắp xếp cột** | chưa làm. |
| **"Thuật ngữ cấm" của spec §8 (QA tất định)** | **CHƯA LÀM**, đã ghi nhận chính thức. **Quyết định:** hoãn tới khi có **cổng QA đọc nó** — hôm nay chưa route/handler nào tiêu thụ danh sách cấm, nên chọn mô hình dữ liệu lúc này là đoán. |

**Quyết định các mục trên (chốt, không phải "chờ"):**

- **Bảng eval §4.6/§4.7 · layout điện thoại · sáng/tối · kéo-thả cột** — **KHÔNG làm** trong
  giai đoạn này (ngoài phạm vi đã thoả thuận).
- **"Thuật ngữ cấm"** — **KHÔNG làm** tới khi có cổng QA tiêu thụ; làm khi có cổng đó (dữ liệu
  lúc ấy mới tự chỉ ra nó thuộc `glossary` hay bảng riêng).
- **Chất lượng dịch (BLEU/MQM)** — **KHÔNG làm**: không có tham chiếu của người để chấm, nên
  mọi điểm số bây giờ là bịa. Làm khi có bản dịch tham chiếu cho một tập câu.
- **Hai định nghĩa CPS (20,0 vs 21,0)** — **ĐỂ NGUYÊN, đã tài liệu hoá**: hợp nhất là đổi
  ngưỡng sản phẩm, và không có số nào cho thấy ngưỡng hiện tại sai.

### CHƯA BIẾT / CHƯA ĐO (trung thực)

#### Engine dịch: mặc định là `opus-mt`; `qwen2.5-3b` CHỈ dịch được chữ SẠCH

**Ghi ở đây vì đây là mục "cái chưa biết" của repo, và đây là điều người dùng phải biết trước khi chọn engine.**

**Engine dịch mặc định = `opus-mt`.** Trên máy này `qwen2.5-3b` (Ollama) **chỉ dịch được chữ SẠCH**: với
chữ ASR THẬT (vỡ câu · lẫn Phồn thể · sai từ) nó **CHÉP NGUYÊN VĂN bản gốc** — đo được **43/44 đoạn**
trên một clip tiếng Trung thật (fw-tiny → 44 đoạn → `qwen2.5-3b` qua `POST /api/translations`), và bản
"dịch" đó vẫn được ghi `status=done` + `transcript=translated`.

- **Prompt mạnh hơn KHÔNG cứu được.** Prompt `qwen-json-p2` (thêm một câu cấm chép nguyên văn, tổng quát
  hoá theo ngôn ngữ đích) làm **chữ sạch** chuyển từ chép sang dịch thật (**8/8** qua đường API thật),
  nhưng chữ ASR thật **vẫn** bị chép (43/44). Một prompt mạnh gấp đôi cũng không đổi kết quả.
- **KHÔNG phải lỗi hạ tầng/API.** Với `temperature=0.1` kết quả **tất định theo nội dung prompt** (cùng
  chuỗi byte ⇒ cùng kết quả; `seed=7` không đổi gì; bỏ `format:json` vẫn chép y hệt). Giả thuyết
  *prompt-cache* và *model vừa nạp lại* đã bị **bác bỏ bằng phép đo** (cache HIT toàn phần + prompt khác
  ⇒ dịch; đổ model rồi gọi đúng prompt của app ⇒ vẫn chép). Nên đây là hành vi của **model + nội dung chữ
  nguồn**, không phải của một tầng nào trong repo.
- **KHÔNG phải "engine hỏng hoàn toàn"**: `qwen2.5-3b` **dịch được** chữ Trung well-formed (8/8 câu sạch
  qua API thật; 40/40 mục sạch trong một lô đo riêng). Mô tả đúng là *"không dùng được cho đường ASR"*,
  không phải *"hỏng"*.

**Hệ quả cho người dùng:** muốn có bản dịch dùng được cho **đường ASR** ⇒ **dùng `opus-mt`**. Trên cùng
clip đó `opus-mt` cho **44/44 đoạn tiếng Việt, 0/118 ký tự Hán** (đo ở lượt trước).

**Cờ QA nay QUAN SÁT ĐƯỢC, nhưng vẫn CHƯA phải CỬA CHẶN.** QA tất định bắt ca chép bằng tiền tố `lang:`
(`lang:<i>=source:han<n>` khi dòng vẫn là chữ Hán; `lang:<i>=residue:han<n>` khi dòng đã tiếng Việt mà còn
sót Hán), và nay `GET /api/translations/{id}` + `GET /api/translations?transcript_id=` trả thêm
**`qa_issues`** (mảng) cùng **`tokens_in`/`tokens_out`/`duration_ms`**. Hai điều cố ý **KHÔNG** làm ở đây:

- **`status` KHÔNG đổi ngữ nghĩa**: một bản dịch còn cờ `lang:...=source:` **vẫn** `done`. Chặn/đổi
  `status` theo cờ là **quyết định sản phẩm**, chưa làm (nó sẽ làm đỏ bài ghim
  `backend/tests/test_api_translations.py::test_a_created_translation_is_consumed_by_the_real_handler`,
  bài ghim `status == "done"` cho một engine giả).
- **Hiển thị cờ trong giao diện CHƯA làm** — đó là việc **frontend**, phải làm trên **nhánh frontend**;
  `frontend/` ở nhánh backend này không được sửa một byte. Cờ ra tới HTTP nghĩa là **có đường**, chưa
  phải là **có người đọc nó**.

⚠️ **ĐÍNH CHÍNH một câu đã cũ trong chính mục này** (nó có trước lượt này, không phải do lượt này làm
sai): câu *"chưa có bản dịch nào chạy qua engine thật trong các vòng này"* ở gạch đầu dòng đầu tiên
**không còn đúng** — `opus-mt` và `qwen2.5-3b` **đã chạy thật** trên một clip tiếng Trung thật ở hai lượt
gần nhất (xem `backend/README.md` và hai báo cáo trong `.superpowers/sdd/2026-09-26-frontend-workspace-2/`).
Thứ **vẫn** đúng là chưa có BLEU/MQM và chưa có người đọc duyệt.

- 🔴 **Chất lượng bản dịch tiếng Việt CHƯA TỪNG ĐƯỢC ĐÁNH GIÁ.** Chưa có điểm BLEU/MQM, chưa có
  người đọc duyệt, và **chưa có bản dịch nào chạy qua engine thật trong các vòng này**
  (`backend/README.md:199-205`, `frontend/e2e/TIEU-CHI-12.md:13`). Không có tuyên bố nào về chất
  lượng ở đây. Lỗi **thấy được trên đầu ra thật** thì có ghi lại: `opus-mt` **cắt cụt câu** và dịch
  成本 thành `"10%"`; `qwen2.5-3b` **để sót chữ Hán** (`dịch字`, `việc字幕`).
- **`seek`/`Range` trong Chrome thật CHƯA ĐO.** Không kế hoạch e2e nào đo `currentTime`/`Range`;
  ảnh **không** chứng minh được. Thứ duy nhất đã đo là phía **MÁY CHỦ** (HTTP `Range` ⇒ 206)
  (`frontend/e2e/TIEU-CHI-12.md` §3 mục 5, `frontend/e2e/README.md`).
- **`Ctrl+1/2/3` là phím VẬT LÝ chưa đo.** CDP tiêm ở tầng **renderer**, nên nó **đi vòng qua**
  bảng accelerator của trình duyệt: phép đo nói *"binding của app đúng KHI sự kiện tới nơi"*,
  **không** nói gì về một cú bấm tay. Nghi Chromium không gửi accelerator chuyển tab tới trang
  (ERRATA **#47 mục 7**). Cần **một phép đo của NGƯỜI**.
- **`J`/`K`/`N` "nhìn thấy được" (cuộn tới dòng) chỉ là TRẦN.** Vế DOM có bài ghim; vế *"mắt thấy
  nó cuộn tới"* chỉ có **ảnh**, không có khẳng định tự động (`TIEU-CHI-12.md` §3 mục 2, mục 5).
- **Ảnh chụp chỉ chứng minh BỐ CỤC/VẺ**, không chứng minh nội dung hay hành vi.
- **Chưa đo:** "thời gian phản hồi khi nhảy" (`T7-D` cũ để `null`); chất lượng bản dịch; và
  `DEFAULT_MAX_CHARS = 1200` — **CHƯA TỪNG BỊ ÉP**, lô lớn nhất đo được chỉ **94 ký tự**
  (`backend/README.md:192-198`).
- **Tầng Chrome chưa đo `editingSegment`**: cả ba lượt `ban-ghi-dai-t7` đều cho `"editing":0`.
- **Tiêu chí §12 số 2** chứng minh **ba JOB của một kênh**, **không phải ba TỆP**.
- **Tiêu chí §12 số 6 KHÔNG có ảnh**: máy này Ollama **`up`** nên panel **VẮNG**; ảnh
  `08-ollama-down-neu-panel-hien.png` mang tên *"nếu panel hiện"* và **không** phải bằng chứng.

### HAI ĐỊNH NGHĨA CPS (nợ tài liệu Giai đoạn 2 — ghi mà **KHÔNG** sửa cái nào)

Repo có **HAI** định nghĩa "CPS" khác nhau, ở hai module khác nhau, và **cả hai đều đang chạy**:

| | `readability` | `mt_qa.cps_row` |
|---|---|---|
| **Số ký tự** | **BỎ** khoảng trắng: `len("".join(text.split()))` | **CÓ** đếm khoảng trắng (chỉ `strip()` hai đầu): `len(text.strip())` |
| **Ngưỡng** | `CPS_WARN = 20.0` (`>`) | `QaLimits.max_cps = 21.0` (`>`) |
| **Cửa sổ** | cửa sổ của chính đoạn **NGUỒN** (`seg.start`→`seg.end`) | cửa sổ **NGUỒN** `src`, dự phòng cửa sổ bản dịch khi cửa sổ nguồn `<= 0` |
| **Tính trên** | **nguồn** — `transcript.segments` | **cửa sổ nguồn**, đo trên **đoạn DỊCH** |

Đường dẫn + số dòng (**tự đọc trong `backend/` ở lượt này; chỉ ĐỌC, KHÔNG sửa**):

- `readability`: `backend/app/domain/readability.py:9` (`CPS_WARN = 20.0`) ·
  `:12-18` (`reading_cps`, `chars = len("".join(text.split()))`) · gọi từ
  `backend/app/api/routes_transcripts.py:159-160` (`cps = reading_cps(seg.text, seg.start, seg.end)`,
  `if cps > threshold`), trên `transcript.segments` = **nguồn**
  (`routes_transcripts.py:153`). Route phát khoá tên **`chars_no_space`**
  (`routes_transcripts.py:145-149,154`).
- `mt_qa.cps_row`: `backend/app/domain/mt_qa.py:24` (`max_cps: float = 21.0`) ·
  `:82-102` (`cps_row`; `text = out.text.strip()` ở `:95`, `cps = len(text) / window` ở `:100`) ·
  `:33-53` (`_window` — cửa sổ NGUỒN) · gọi từ `backend/app/api/routes_translations.py:218` và
  `backend/app/domain/mt_qa.py:159`.

⚠️ **KHÁC NHAU CÓ CHỦ Ý hay là NỢ? — câu trả lời đọc từ mã: đây là NỢ TÀI LIỆU, không phải một
thiết kế hai-định-nghĩa.** Bằng chứng: (a) `mt_qa.py:120-122` nói *"Hai tên khác nhau là cố ý"* —
nhưng đó là nói về **TÊN KHOÁ** (`chars` vs `chars_no_space`), **không** nói gì về việc **hai ngưỡng
khác nhau** (20.0 vs 21.0) hay hai phép đếm ký tự khác nhau; (b) `mt_qa.py:3-4` tự khai *"ngưỡng cụ
thể cho tiếng Việt **còn để ngỏ** (spec §12) và đo trên dữ liệu thật"*; (c) `routes_transcripts.py:146-148`
gọi việc hai khoá cùng tên mà khác nghĩa là *"đúng thứ khiến người sau đọc sai số"*. ⇒ **Hai định
nghĩa này là nợ phải ghi, không phải một quyết định đã chốt.** Lượt này **không sửa cái nào**
(`backend/` là chỉ-đọc theo luật của task).

### Nợ Giai đoạn 2 còn mở (đúng thực tế)

- ✅ **ĐÃ ĐÓNG — `DEFAULT_MAX_CHARS = 1200` nay đã được ÉP.** Lượt đo
  `20261025-batch-chars` (`backend/scripts/measure_batch_chars.py`, transcript tổng hợp,
  `qwen2.5-3b`, không `echo_guard`): lô **30 mục / 750 ký tự** chạy sạch, lô **24 mục / 3600 ký
  tự** làm **cả lượt `failed`** ⇒ biến quyết định là **số KÝ TỰ**, không phải số mục; ngưỡng vỡ
  đo được nằm giữa **3000** và **3600** ký tự; 1200 là bảo thủ ~2,5× và còn làm echo giảm
  (8 mục: 16/24 · 20 mục: 24/24). ⚠️ n = 1 mỗi cấu hình, một engine — xem bảng đầy đủ trong
  `backend/README.md` mục "Giới hạn".
- **Chất lượng dịch chưa đánh giá** — xem ở trên (`backend/README.md:199-205`).
- ✅ **ĐÃ ĐÓNG — `retry_job` không xoá `cancel_requested`.** (Nợ ghi từ ERRATA **#46 mục 9**.)
  `retry_job` nay `UPDATE ... cancel_requested=0` (`backend/app/adapters/persist/sqlite_repos.py`),
  vì `worker._run_one` **huỷ job ở ranh giới nếu cờ còn** — không xoá thì "chạy lại" trên một job
  từng bị xin huỷ sẽ `queued` rồi `cancelled` ngay lượt đầu. Hai bài ghim: tầng repo
  (`tests/test_repos.py::test_retry_clears_a_stale_cancel_request`) và tầng HTTP
  (`tests/test_api_jobs_sse.py::test_retry_through_the_api_clears_a_stale_cancel_request`).
  Mutation đã chạy: bỏ `cancel_requested=0` ⇒ **cả hai** bài đỏ. Lưu ý đường đi được là `failed`
  và `interrupted`: `cancelled` **không** nằm trong `RETRYABLE_STATES`, nên ca hỏng là "xin huỷ
  nhưng job kết thúc `failed` trước ranh giới".
- ✅ **ĐÃ ĐÓNG — `N-9` route export GHI TỆP trên một `GET`.** (Nợ design spec §7 dòng 111 / §9 dòng 135;
  đừng nhầm với `containment`, thứ đã đóng từ Giai đoạn 2 — xem ERRATA **#48** mục 1.)
  Cách vá (chốt sau khi gộp nhánh `gd2-mt`): route **KHÔNG ghi đĩa nữa** — bỏ hẳn lần ghi, bỏ
  `_materialise`, bỏ `dependency` `dirs` của route này. Thân phụ đề nằm trọn trong response, nên không có
  tệp nào để lại và `GET` không còn tác dụng phụ. Đường GHI duy nhất còn lại là đường job (`POST
  /api/export` → `GET /api/export/{job_id}/download`).
  ⚠️ **Một bản vá khác của cùng nợ đã bị loại:** bản `?save=1` (mặc định không ghi, có cờ thì ghi) cũng
  làm `GET` sạch, nhưng để lại **một tham số không người gọi nào trong production dùng** — đúng loại khai
  báo chết mà repo này xoá. Hai bản không thể cùng tồn tại: cái giá của bản `save` là một đường ghi phải
  giữ và bảo vệ (`resolve_within`, byte-exact, mutation), mà không ai dùng.
  Bài ghim: `tests/test_api_export_by_translation.py` (bản của `gd2-mt`) khẳng định **route spec không để
  lại tệp nào** ngay trong helper dùng chung, nên mọi bài đi qua nó đều ghim vế đó.


## ERRATA #54 — `PATCH /api/transcripts/{id}` THAY TOÀN BỘ danh sách đoạn

**Phát hiện lúc:** kiểm tương tác thật trên UI (sau commit `bdbcb18`).
**Mức:** mất dữ liệu thật. **Trạng thái:** đã khôi phục, xem mục "Khôi phục".

### Tôi đã làm gì

Sau khi `POST /api/transcripts/2/approve` đổi `status` `translated` → `reviewed` (đúng),
tôi muốn **trả `status` về như cũ** để không để lại dấu vết trên dữ liệu thật. Tôi gọi:

```
PATCH /api/transcripts/2
{"segments": [{"i":0,"start":0.93,"end":2.04,"text":"你绝对没吃过这样的东北烤冷面","speaker":null}],
 "status": "translated"}
```

Kết quả đo được:

```
status=200
body: {"id":2,...,"version":4,...}
GET /transcripts/2  ->  status='translated'  version=4  so segment=1
```

**438 đoạn → 1 đoạn.** `version` 3 → 4. Bản dịch 4 (438 đoạn, `transcript_version=1`) thành
`stale` vì version đã lên 4.

### Giả định của tôi, và nó sai ở đâu

Tôi giả định `PATCH /api/transcripts/{id}` là **bản vá từng phần**: gửi đoạn nào thì sửa đoạn
đó, các đoạn khác giữ nguyên. Đó là cách `PATCH /api/translations/{id}` hành xử — route đó tra
`known = {s.i for s in translation.segments}`, rồi `edited[seg.i] = replace(...)`, nên chỉ những
`i` được gửi mới đổi và **không thể thêm hay bớt**.

Route transcript **không** như vậy. `PatchIn.segments` ở `routes_transcripts.py:36-40` là
`list[dict]` với `min_length=1` — nó là **DANH SÁCH MỚI THAY THẾ**, không phải bản vá. Đọc lại
docstring đầu tệp mới thấy ý định: *"Sửa nội dung là TĂNG VERSION"*, và version là thứ duy nhất
khiến bản dịch cũ thành lỗi thời. Hành vi thay-thế là **đúng thiết kế**; sai là ở phía người gọi.

Điều đáng ghi không phải "tôi gọi sai route", mà là: **hai route cùng tên `PATCH`, cùng tham số
`segments`, hành xử khác nhau mà không có gì ở chữ ký nói ra.** `translations` là bản vá theo
`i`; `transcripts` là thay thế toàn bộ. Một người (hoặc một agent) đã quen cái thứ nhất sẽ phá
dữ liệu bằng cái thứ hai — và triệu chứng duy nhất là một con số `version` tăng thêm 1, thứ
không ai nhìn.

⇒ **Nợ ghi lại, KHÔNG sửa lượt này:** hai route nên khác tên (`PUT` cho thay-thế, `PATCH` cho
bản vá), hoặc `PatchIn` của transcript nên nhận `replace_all: bool = False` và từ chối khi
thiếu cờ đó. Chưa sửa vì nó là thay đổi hợp đồng API, cần chốt riêng.

### Khôi phục — đo được, không phỏng đoán

Không có backup `app.db` (`/data/app.db` là bản duy nhất, 2 314 240 B). Đường cứu đến từ hai
nguồn **cùng sinh ra từ `transcript 2`**:

1. `translation 3` (`opus-mt`, cùng `transcript 2`, 438 đoạn) — mỗi đoạn giữ trường `words`:
   danh sách ký tự tiếng Trung kèm mốc thời gian. Đó là **bản gốc nguyên vẹn**.
2. `/data/output/dubs/dub-4.plan.json` — 438 dòng có `i`/`start`/`end`, sinh từ chính bản dịch 4.

Ghep lai (`backend/_khoi_phuc_t2.py`), kiem tra TRUOC khi ghi:

```
transcript 2 hien tai: 1 doan, version=4, status=translated
translation 3: 438 doan, transcript_version=1
plan: 438 dong
--- kiem tra truoc khi ghi ---
  so doan dung lai : 438
  lech moc voi plan: 0
  doan khong co words: 2
  doan co text rong : 2
  tong thoi luong    : 871.23 s
```

`lech moc voi plan: 0` là điều kiện quan trọng nhất — nó chứng minh `words` của bản dịch 3 thuộc
đúng 438 đoạn của transcript 2, không phải một lần chạy ASR khác.

**Hai đoạn không khôi phục được:** `i=277` (724,67–729,899) và `i=278` (729,899–733,82). ASR
không trả `words` cho hai đoạn đó (chúng là lời bình chèn, không phải phụ đề). Ghi `text=""` và
`suspect=true` — **không bịa tiếng Trung từ bản dịch**, vì chữ bịa không còn đường phát hiện.
Giao diện sẽ hiện chúng là đoạn nghi ngờ, đúng sự thật.

Ghi lại **giữ `version=4`**, không lùi về 3: lùi version là nói dối rằng transcript chưa từng bị
sửa, và bản dịch 4 — sinh từ version 1 — vẫn phải mang cờ `stale` đúng sự thật.

Kết quả sau khi ghi:

```
so doan: 438  version=4  status=translated
GET /transcripts/2: status=200 so segment=438 version=4 status='translated'
  segments[0]: start=0 end=2.04 text='你绝对没吃过这样的东北烤冷面'
  segments[277]: text='' suspect=True
```

### Bài học

Một phép "khôi phục trạng thái" không phải phép đọc. Trước khi gọi một route ghi để dọn dấu vết
của một route ghi khác, phải đọc **thân route đó**, không suy từ tên và tham số. Và: dữ liệu
thật không có backup thì mọi lệnh ghi thử phải chạy trên bản sao — lượt này không có bản sao, chỉ
có may mắn là `words` của một bản dịch khác đủ để dựng lại.
## ERRATA #55 — hai lỗi im lặng trên thanh bước và trên Timeline

**Phát hiện lúc:** kiểm tương tác thật trên UI (sau commit `bdbcb18`, cùng lượt với ERRATA #54).
**Mức:** một nút không làm gì; một thao tác ghi hỏng dữ liệu. **Trạng thái:** đã sửa, đã đo lại.

### Lỗi 1 — nút "Duyệt" trên thanh bước không gửi một request nào

Đo trên trình duyệt thật, bắt `window.fetch`:

```
bấm "Duyệt còn 186 việc"  ->  request ghi: []   notice: 0
```

Hai nguyên nhân, cả hai đều đo được:

1. `approveTranscript` được **import** ở `App.tsx:4` nhưng **không chỗ nào gọi**.
   Grep toàn `src/`: chỉ có dòng import, định nghĩa trong `endpoints.ts`, và một
   dòng trong `endpoints.test.ts`. Đúng loại khai báo chết repo này xoá.
2. `Studio.tsx:376` `onStep` bắt `id === "duyet"` rồi `return` **trước khi** gọi
   `onBuoc`, nên kể cả khi `App.onBuoc` có nhánh `duyet` thì nó cũng không bao
   giờ chạy. Hai chỗ cùng xử lý một mã, và chỗ đầu nuốt sự kiện.

Hệ quả không chỉ là "bấm không thấy gì": `POST /api/transcripts/{id}/approve` là
**đường duy nhất** ghi `status` của transcript. Không ai gọi nó thì `status` mãi
là `translated`, và bước "Lồng tiếng" giữ `state: "todo"` (`lib/studio.ts:263`)
dù người dùng đã duyệt hết — giao diện nói dối về trạng thái thật.

Sửa: `onStep` gọi `onBuoc("duyet")` **trước** rồi mới `diViec(1)`. Ghi trước vì
route có thể hỏng (404/500) và `App` đặt `loi`; nhảy trước thì người dùng đã rời
chỗ và không còn thấy thông báo lỗi gắn với hành động vừa bấm.

Đo lại sau khi sửa:

```
bấm "Duyệt còn 187 việc"
  -> POST /api/transcripts/2/approve   status=200
API: status 'translated' -> 'reviewed'   version=4 (KHÔNG đổi)   so segment=438 (KHÔNG đổi)
```

Đúng hợp đồng của route (`routes_transcripts.py:10-12`: duyệt không sửa một ký tự
nào, nên không tăng version).

### Lỗi 2 — kéo tay nắm phải trên Timeline làm đoạn dài 0 giây

Đo: kéo tay nắm phải của đoạn 0 (`0,00 → 2,04`) từ `x=338` sang `x=368`.

```
PATCH /api/transcripts/2   status=200
  doan 0 gui len: start=0  end=0        <- dai 0 giay
API sau do: i=0 start=0 end=0 dai=0 | version 4 -> 5
```

Nguyên nhân nằm ở `Studio.tsx:985`:

```js
{ end: Math.min(player.duration, Math.max(t, s.start + 0.1)) }
```

`player.duration` là **`NaN`** khi trình duyệt chưa nạp metadata video — đo được
`document.querySelector('video').duration === NaN`. `Math.min(NaN, 2.7)` trả
`NaN`, và giá trị `NaN` đi vào `update()` → `onSuaMoc` → JSON thành `null`/`0`.

Một trần **chưa biết** bị dùng như một trần **bằng 0**, nên nó cắt mọi thứ về 0.
`0` không có nghĩa "không giới hạn"; nó có nghĩa "chưa đo được".

Sửa: chỉ kẹp khi `duration > 0` thật sự, còn không thì `Infinity`.

```js
const tranEnd = player.duration > 0 ? player.duration : Infinity;
```

Đo lại, cùng thao tác, cùng toạ độ:

```
durationVideo = NaN
kéo 338 -> 368 px
  -> 1 request PATCH /api/transcripts/2  status=200
     doan 0 gui len: start=0  end=2.68984375     <- KHONG con 0
     tong 438 doan (khong mat doan nao)
API: i=0 0 -> 2.69 dai=2.69 | dai<=0: 0 | moc am: 0 | moc giam dan: 0
```

### Một điều KHÔNG sửa, và lý do

Kéo mốc gọi `PATCH /api/transcripts/{id}` và gửi **toàn bộ 438 đoạn**. Đó là hệ
quả trực tiếp của hợp đồng route (xem ERRATA #54): `PatchIn.segments` là danh sách
THAY THẾ, không phải bản vá. Nó cũng có nghĩa mỗi lần kéo một mốc là `version`
tăng thêm 1, làm bản dịch thành `stale`.

Đó là hành vi **đúng theo thiết kế hiện tại** (mốc thời gian thuộc bản ghi, và sửa
bản ghi thì version phải tăng — nếu không, bản dịch cũ sẽ không bao giờ được đánh
dấu lỗi thời khi phụ đề đổi độ dài). Nhưng nó đắt: kéo 5 mốc = 5 lần ghi 200 KB và
5 lần bản dịch thành `stale`.

⇒ **Nợ ghi lại, KHÔNG sửa lượt này:** cần một route riêng cho mốc
(`PATCH /api/transcripts/{id}/segments/{i}`) chỉ ghi một đoạn, và một quyết định
rõ ràng xem sửa mốc có nên tăng version hay không. Cả hai là thay đổi hợp đồng API,
phải chốt riêng.

### Bài học

Một nút "không có phản ứng" có thể là hai lỗi độc lập chồng lên nhau (import chết
+ nhánh `return` sớm). Và `NaN` không phải "không có giá trị" trong số học — nó là
giá trị lan truyền: `Math.min(NaN, x)` là `NaN`, và `NaN` xuống tầng ghi thành dữ
liệu hỏng. Chỗ nào có `Math.min`/`Math.max` với một biến "có thể chưa biết", chỗ
đó cần một phép kiểm `> 0` tường minh.
## ERRATA #56 — "TanStack Start" đã chốt là KHÔNG dùng, nhưng chưa ai ghi ra

**Trạng thái:** đóng một quyết định treo. **Không** phải một lỗi mới phát hiện khi chạy.

### Quyết định

Stack của `frontend/` là **Vite SPA thuần**, không SSR, không server Node:

```
vite.config.ts   TanStackRouterVite() + react() + tailwindcss()
                 KHÔNG có tanstackStart, KHÔNG có nitro
package.json     KHÔNG có @tanstack/react-start, @tanstack/start, nitro, vinxi
docker-compose   hai service: api (python) và web (nginx) — KHÔNG có service Node
```

Đo bằng lệnh, không đọc tên gói:

```
Select-String -Path frontend\vite.config.ts -Pattern 'tanstackStart|nitro'
  -> chi khop trong COMMENT, khong co trong `plugins:`
$j = Get-Content frontend\package.json -Raw
  '@tanstack/react-start' -> KHONG   'nitro' -> KHONG   'vinxi' -> KHONG
Select-String -Path docker-compose.yml -Pattern '^  [a-z-]+:'
  -> api, web   (khong co service Node nao)
```

`web` là `nginx` phục vụ `frontend/dist`, và `nginx.conf` chuyển `/api/` sang `api`.
`vite.config.ts` có `server.proxy` cho `/api` — đó là **dev**, không phải production.

### Vì sao không dùng TanStack Start

Bản Lovable bọc `@lovable.dev/vite-tanstack-config`; gói đó CÓ SẴN `tanstackStart`,
`nitro`, `tsConfigPaths`, alias `@`, dedupe React và dò sandbox. Gói `@lovable.dev/*`
**không cài được ngoài Lovable**. Dựng lại tay phần `nitro`/`tanstackStart` nghĩa là
tự viết một tầng SSR + một server Node chỉ để phục vụ một app **không có route nào cần
SSR**: toàn bộ dữ liệu đến từ `GET /api/*` sau khi trang đã tải, và mọi màn hình đều
đọc state cục bộ của trình duyệt (video, timeline, waveform).

Đổi lại, SPA thuần cho ba thứ đáng giá:

1. `nginx` phục vụ tệp tĩnh — không thêm tiến trình, không thêm cổng, không thêm
   điểm chết khi khởi động.
2. `dist/` là đầu ra duy nhất; deploy là `docker cp dist/... nginx:/usr/share/nginx/html/`
   (đã dùng suốt lượt này).
3. Build 1,67 s, bundle 328 kB entry + 74 kB chunk app — đo được, không phải ước lượng.

### Hai tham chiếu CHẾT đã sửa

Comment trong `vite.config.ts` và `src/main.tsx` trỏ tới `docs/ERRATA.md` với câu
"xem mục *vì sao không dùng TanStack Start*". Đo:

```
Test-Path docs\ERRATA.md   ->  False
```

Tệp đó **không tồn tại**. ERRATA của repo nằm trong chính `README.md` (các mục
`## ERRATA #<n>`). Một tham chiếu tới tệp không ai mở được không phải tài liệu — nó là
lời chỉ dẫn sai, và nó khiến người đọc tin rằng quyết định đã được ghi ở đâu đó.

Cả hai chỗ nay trỏ về `README.md` (mục này), và ghi rõ rằng chúng từng trỏ sai.

### Nợ còn lại, KHÔNG sửa lượt này

`frontend/e2e/` (Playwright) có thư mục và `README.md` nhưng chưa có bài chạy được
trong CI. Bộ test thật hiện tại là `node --test` (127 bài). Hoặc viết bài e2e thật, hoặc
xoá thư mục — nhưng đó là quyết định riêng, cần đo thời gian chạy trước.
## ERRATA #57 — prop `sourcesError` là khai báo chết: lỗi nạp kênh bị nuốt

**Phát hiện lúc:** viết `App.test.tsx` (bài "nguồn lỗi 500 hiện thành chữ, không nuốt im lặng").
**Mức:** giao diện nói dối về lý do trang trống. **Trạng thái:** đã sửa, đã đo lại.

### Số đo

Grep toàn `src/` cho `sourcesError`:

```
App.tsx:59    const [sourcesError, setSourcesError] = useState<string | null>(null);
App.tsx:84      setSourcesError(e instanceof Error ? e.message : String(e));
App.tsx:422   sourcesError={sourcesError}
Studio.tsx:84   sourcesError: string | null;
```

**Hai khai báo, hai chỗ ghi, một chỗ truyền — và KHÔNG một dòng nào ĐỌC.** `Studio` nhận
prop này rồi bỏ đó. Vì thế `setSourcesError` là một hàm chỉ để nuốt lỗi.

Hệ quả đo được: khi `GET /api/sources` hỏng (backend chưa lên, sai cổng, 500), người dùng
thấy **danh sách kênh rỗng và không một lời nào**. Không phân biệt được *"chưa có kênh
nào"* với *"không đọc được kênh"* — hai tình huống cần hai hành động khác nhau.

Bài test bắt được nó theo đúng cách: cho `fetch` trả 500 cho mọi route, rồi khẳng định
`document.body.textContent` có chữ báo lỗi. Đỏ, vì không có gì được render.

### Sửa

Nối vào chuỗi `notice` sẵn có — cùng khuôn với `loi` (lỗi của các hành động ghi):

```tsx
useEffect(() => {
  if (sourcesError === undefined || sourcesError === null || sourcesError === "") return;
  setNotice(`Không nạp được danh sách kênh: ${sourcesError}`);
}, [sourcesError]);
```

Giữ nguyên câu của tầng dưới (thông điệp của `fetch`/FastAPI), chỉ nói rõ nó thuộc phần
nào — một câu `"Failed to fetch"` trần trụi không cho biết hỏng ở đâu.

Kèm theo: `sourcesError` phải được **destructure** trong `Studio`. Nó đã khai trong
`StudioProps` từ trước nhưng chưa lấy ra, nên lần dùng đầu tiên làm `tsc` đỏ ngay:

```
src/components/studio/Studio.tsx(213,9): error TS2304: Cannot find name 'sourcesError'.
```

Đó là bằng chứng thêm rằng prop này chưa từng được dùng: nếu đã dùng, lỗi biên dịch đã
nổ từ lâu.

### Bài học

`tsc` **không** bắt được prop khai mà không đọc — nó chỉ bắt *dùng* một cái tên không tồn
tại. Một prop chết nằm im qua mọi lần build xanh, và cái giá của nó không phải là một dòng
thừa: nó là một đường báo lỗi bị cắt. Cách duy nhất bắt được là một bài test khẳng định
**lỗi phải hiện ra**, chứ không phải khẳng định "component render được".

### Phụ: hai global nữa của jsdom

Viết bài test này lộ thêm `ReferenceError: requestAnimationFrame is not defined` —
`pretendToBeVisual: true` chỉ gắn hai hàm đó lên `window`, còn `Timeline` gọi tên trần.
`ResizeObserver` và `Element.prototype.scrollIntoView` đã thêm ở lượt trước; cả ba nay nằm
trong `MANAGED_GLOBALS` để `teardownDom()` trả lại — trước đó chúng rò sang mọi tệp test
chạy sau, vì `--test-isolation=none` dùng chung một tiến trình.
## ERRATA #58 — `safe_basename` cắt tên khác nhau trên Windows và Linux

**Phát hiện lúc:** chạy `pytest` bằng `.venv` trên máy chủ (Windows) thay vì trong container.
**Mức:** tên tệp nguy hiểm được chấp nhận và **âm thầm đổi tên** trên Windows. **Trạng thái:** đã sửa, đã đo cả hai nền tảng.

### Số đo

```
tests/test_api_sources.py::test_safe_basename_tu_choi_moi_dau_hai_cham_ke_ca_tien_to_giong_o_dia
E  Failed: DID NOT RAISE <class 'app.domain.paths.InvalidBasename'>
```

Hai nền tảng, cùng một hàm, hai hợp đồng:

| | `PurePath("a:b.mp4")` | `safe_basename("a:b.mp4")` |
|---|---|---|
| Windows (máy chủ) | `.drive='a:'` `.name='b.mp4'` | **`'b.mp4'`** — không ném |
| Linux (container) | `.drive=''` `.name='a:b.mp4'` | `InvalidBasename` — ném |

### Nguyên nhân

`pathlib.PurePath` chọn lớp con theo **hệ điều hành đang chạy**: `PureWindowsPath` trên
Windows, `PurePosixPath` trên Linux. Hai lớp tách ổ đĩa khác nhau. Trên Windows, dấu `:`
bị coi là ổ đĩa nên **biến mất** trước khi tới `_reject_unsafe_name`:

```python
plain = pathlib.PurePath(name.replace("\\", "/")).name   # ← dòng gây lỗi
```

Tên client gửi lên là dữ liệu không tin được. Trên Windows nó được **chấp nhận với một
cái tên khác** — tệp ghi xuống đĩa không còn là tệp người dùng gửi.

### Sửa

Đường dẫn do client gửi luôn được hiểu theo cú pháp POSIX (`\` đã đổi thành `/` ngay
trên), nên cắt theo `/` là đúng nghĩa ở mọi nền tảng:

```python
plain = name.replace("\\", "/").rsplit("/", 1)[-1]
```

Đo lại — hai nền tảng cho **cùng kết quả**:

| tên | Windows | Linux |
|---|---|---|
| `a:b.mp4` | NÉM | NÉM |
| `x:y.mp4` | NÉM | NÉM |
| `ab:c.mp4` | NÉM | NÉM |
| `C:/media/x.mp4` | `'x.mp4'` | `'x.mp4'` |
| `..\..\x.mp4` | `'x.mp4'` | `'x.mp4'` |
| `a/` | NÉM | NÉM |
| `CON` | NÉM | NÉM |
| `a//b.mp4` | `'b.mp4'` | `'b.mp4'` |

### Bài học về CÁCH ĐO — quan trọng hơn lỗi

Lỗi này nằm im rất lâu vì **test chạy trong container Linux**, nơi hành vi đúng. Đó là
chạy test trên nền tảng **khác** nền tảng phát triển, nên nó chỉ bắt được lỗi của Linux.

Nhưng lần này tôi đã đo sai theo chiều ngược lại trước đó: chạy `pytest` trong container
`api` và thấy `1407 passed` — trong khi `requirements-docker.txt:8` ghi rõ image **cố ý**
thiếu `pytest`. Lượt đó chạy được chỉ vì container còn `pip install` dư từ lần trước.
Một môi trường không được định nghĩa bởi image thì kết quả của nó không tái lập được.

Hai điều rút ra:

1. **Chạy suite ở môi trường mà nó được định nghĩa cho** — với repo này là `.venv` trên
   máy chủ (`requirements.txt` có `pytest==8.3.4`), không phải image chạy sản phẩm.
2. **Một lỗi phụ thuộc nền tảng chỉ lộ ra khi chạy trên cả hai nền tảng.** Nếu chỉ có
   một môi trường, hãy biết mình đang mù phía nào — và ghi ra, thay vì coi "xanh" là
   "đúng".

### Đo cuối

```
pytest (venv, Windows)   1412 passed, 15 deselected, EXIT_PYTEST=0
npm test (frontend)      145 pass, 0 fail, EXIT=0
npx tsc --noEmit         EXIT_TS=0
npx vite build           EXIT_BUILD=0
```
## ERRATA #59 — kéo MỘT mốc từng gửi cả 438 đoạn và làm mọi bản dịch thành `stale`

**Phát hiện lúc:** rà các khoản nợ còn lại; `onSuaMoc` trong `frontend/src/App.tsx` gọi `patchTranscript(id, { segments: [...TOÀN BỘ...] })`.
**Mức:** mỗi lần người dùng dời một mốc 0,1 giây, `version` của bản phiên âm tăng ⇒ `is_stale()` biến **mọi** bản dịch thành `stale` ⇒ giao diện mời dịch lại từ đầu. **Trạng thái:** đã sửa, đã đo trong jsdom **và** trong Chrome thật.

### Số đo

Bản ghi thật trong DB: transcript `2`, `version=8`, **438 đoạn**. Đường cũ gửi toàn bộ 438 đoạn cho một thao tác chỉ đổi hai số thực.

Đường mới — `PATCH /api/transcripts/{id}/segments/{i}`, thân chỉ `{start, end}`:

```
[khangDinh] PATCH /api/transcripts/2/segments/{i co that} phai tra 200           dung=true
[eval]      {"status":200,"i":"1","soDoan":600,"start":0.5,"end":2.5,"version":1}
[khangDinh] ca HAI moc phai duoc GHI THAT (0.5 / 2.5)                            dung=true
[khangDinh] response phai con DU 600 doan                                        dung=true
[eval]      doc LAI tu SQLite: {"version":1,"soDoan":600,"start":0.5,"end":2.5}
[khangDinh] moc phai doc lai duoc tu SQLite                                      dung=true
[khangDinh] `version` KHONG duoc tang khi doi mot moc                            dung=true
[khangDinh] so doan phai NGUYEN VEN truoc/sau                                    dung=true
[eval]      doan KHONG ton tai: {"status":422}
[khangDinh] doan KHONG ton tai phai tra 422                                      dung=true
EXIT_E2E=0
```

Vế "`version` không tăng" được đo bằng **đối chiếu TRƯỚC/SAU** hai request độc lập, không so với một hằng số: `{"version":1,...}` trước, `{"version":1,...}` sau.

### Vì sao KHÔNG tăng `version`

`version` nghĩa là "**nội dung CHỮ** của bản phiên âm đã đổi"; nó tồn tại để `is_stale(transcript_version, translated_from_version)` biết bản dịch đã dịch từ bản ghi cũ. Dời một mốc không làm câu chữ đổi, nên bản dịch vẫn đúng nghĩa — chỉ đổi thời điểm. Tăng version ở đây biến một thao tác vô hại thành "dịch lại từ đầu".

Hệ quả nói thẳng: một bản dịch **đã** `stale` từ trước vẫn `stale` sau khi dời mốc. Đúng — nó vẫn dịch từ bản ghi cũ.

### Ba tầng đã sửa

| tầng | tệp | thay đổi |
|---|---|---|
| cổng | `backend/app/ports/repos.py` | `update_transcript_segment_timing(transcript_id, i, start, end)`; ném `LookupError`, **không** `NotFound` |
| adapter | `backend/app/adapters/persist/sqlite_repos.py` | `dataclasses.replace` đúng đoạn khớp `seg.i`, `UPDATE transcripts SET segments=?` — **cột `version` vắng mặt có chủ ý** |
| route | `backend/app/api/routes_transcripts.py` | `@router.patch("/{transcript_id}/segments/{i}")`; `_require_transcript` trước ⇒ 404, `LookupError` còn lại ⇒ 422 |
| client | `frontend/src/api/endpoints.ts`, `types.ts`, `App.tsx` | `patchSegmentTiming()`; **xoá** `patchTranscript`/`TranscriptPatch` (khai báo chết) |

Route chỉ biết **cổng**: nó bắt `LookupError`, không import `NotFound` của SQLite — kéo lớp adapter vào tầng HTTP là vi phạm chính docblock của `_require_transcript`.

### Bài học về CÁCH ĐO — lần này là một phép XANH GIẢ tự tạo

Sau khi viết xong route, tôi thêm hai bài vào `frontend/src/App.test.tsx` và chúng **đỏ** với `0 !== 1` (không có PATCH nào). Nguyên nhân: tôi kích hoạt qua ô phụ đề, mà `onChange` của ô đó là `onSuaChu` (`PATCH /api/translations/{id}`, sửa **chữ**) — route khác, ý nghĩa khác. Tôi đã viết một bài test đo sai đường rồi tưởng sản phẩm hỏng.

Đường kích hoạt **đo được** là nút `Đặt vào` / `Đặt ra` (`Studio.tsx:947/950`) — cùng gọi `setEdge` → `onSuaMoc` như phím `I`/`O`, và không đi qua hình học. Kéo handle `Timeline` **không** đo được ở tầng jsdom: `toTime()` (`Timeline.tsx:311`) cần `getBoundingClientRect().left` mà jsdom trả toàn số 0 ⇒ phép đo ra `NaN`. Phép đo kéo tay thuộc tầng Chrome thật.

Và bài test đó lộ ra một lỗi **thứ hai**, chỉ trong harness:

```
ℹ Error: Test "PATCH /api/transcripts/2/segments/0 ..." generated asynchronous
  activity after the test ended. This activity created the error
  "ReferenceError: window is not defined" ...
```

Bắt bằng `process.on("uncaughtException")` thì ra stack thật:

```
ReferenceError: window is not defined
  at react-dom-client.development.js:19555:13     ← schedulerEvent = window.event
  at Immediate.performWorkUntilDeadline (scheduler.development.js:45:48)
```

Hai giả thuyết đầu của tôi **đều sai**, và cả hai đều bị phép đo bác bỏ:

1. *`requestAnimationFrame` còn treo* — probe in ra `0 raf` ở **mọi** lượt teardown.
2. *promise `getPeaks` setState sau `await`* — `Studio.tsx:253` và `:255` đều nằm trong `if (!huy)`, tức sản phẩm **đã** đúng.

Sự thật: trong `commitRoot`, nếu `finishedWork.subtreeFlags & 10256` khác 0 thì React gọi `scheduleCallback$1(...)`, và thân callback đó mở đầu bằng `schedulerEvent = window.event`. Đó là việc xả **passive effect** đã xếp lịch từ lúc commit; nó chạy ở macrotask sau, **sau** khi `teardownDom()` đã gỡ `globalThis.window`. `act()` không xả được nó (đã thử: `act` có mặt, `window` còn sống, lỗi vẫn còn).

Cách sửa đúng — và đây là chỗ dễ hỏng nhất — phải **tách đôi** việc trả global:

- nhóm **không-DOM** (`fetch`, `IS_REACT_ACT_ENVIRONMENT`, `requestAnimationFrame`, …) trả **ĐỒNG BỘ**, vì `--test-isolation=none` nghĩa là tệp test kế tiếp chạy ngay sau đó và phải thấy `fetch` thật;
- nhóm **DOM** (`window`, `document`, `HTMLElement`, `Node`, `Event`, `MouseEvent`, `getComputedStyle`, `navigator`) trả ở nhịp `setImmediate` sau, để scheduler có `window` mà đọc.

Hai lần thử sai, mỗi lần đều đo được hậu quả cụ thể:

| thử | hậu quả đo được |
|---|---|
| hoãn **cả** `fetch` | `App.test.tsx` → `api/contract.test.ts` cùng tiến trình: contract chết với `backend 8620 khong len sau 30s` (probe: `fetch.name=""`, `window=object`), dù chạy một mình thì 11/11 xanh |
| hoãn DOM **và** `requestAnimationFrame` | `App.test.tsx` đỏ 4 bài: `ReferenceError: requestAnimationFrame is not defined` |
| lọc nhóm DOM ở đường **hoãn** mà quên đường **đồng bộ** | probe: `[probe] setImmediate cua toi CHAY, window=undefined` — bản hoãn chẳng hoãn được gì |

### Đo cuối (sau ERRATA #59)

```
npx tsc --noEmit                   EXIT_TS=0
npm test (frontend)                148 tests, 148 pass, 0 fail, EXIT_TEST=0
pytest (venv, Windows)             1419 passed, 15 deselected, EXIT_PYTEST=0
npm run e2e (Chrome that)          EXIT_E2E=0
```

`npm test` chỉ xanh khi **cổng 8620 trống**: `frontend/src/api/contract.test.ts` tự `spawn` backend thật, nên container `phu-de-lab-api-1` đang giữ 8620 sẽ làm 11 bài contract timeout sau 30 s. Đó là điều kiện MÔI TRƯỜNG, không phải hồi quy — và nó đã được ghi ở `frontend/e2e/README.md` trước lượt này.

## ERRATA #60 — video lồng tiếng KHÔNG có phụ đề, và `.ass` khai sai hệ toạ độ

**Phát hiện lúc:** người dùng hỏi thẳng "video cuối có phụ đề + lồng tiếng + tách giọng ra khỏi vid là được". Trước đó tôi đã trả lời "tách âm: mã đủ nhưng chưa đo được lần sinh `dub-*.mp4` nào" — đúng, và khi đo thì lộ hai lỗi.
**Mức:** `dub-<id>.mp4` **không có chữ nào**; và sau khi thêm bước burn thì chữ **tràn ra ngoài khung**. **Trạng thái:** đã sửa, đã đo bằng ảnh chụp khung hình thật.

### Lỗi 1 — pipeline không có bước burn phụ đề

`grep` cả `backend/app/pipeline/dub.py` cho `srt|ass|subtitle|drawtext|burn` ra **rỗng** (ngoài phần xuất tệp rời). Nghĩa là:

| Việc | Trước |
|---|---|
| tách nền `htdemucs` | ✅ `dub.py:336` |
| trộn tiếng lồng + nền, remux video | ✅ `remux()` |
| **phụ đề nằm trong MP4** | ❌ **không có đường nào** |

Phụ đề chỉ tồn tại dưới dạng `.srt`/`.ass` **rời**. "Video cuối có phụ đề" là một lời hứa không có đường thực hiện.

### Sửa

`tach_nen.remux()` nhận thêm `phu_de: Path | None`. `None` (mặc định) giữ **nguyên từng byte** hành vi cũ (`-c:v copy`, không re-encode, không đọc tệp phụ đề). Có tệp thì bắt buộc re-encode (`-c:v libx264 -crf 18 -pix_fmt yuv420p`) vì chữ phải được VẼ vào từng khung hình — không có cách nào copy được.

`dub.py` sinh `.ass` bằng **đúng** `export.render()` mà ba nút xuất của giao diện dùng — không tự ghép chuỗi ASS (hai đường sinh phụ đề là hai chỗ để style và thời điểm trôi khỏi nhau).

### Lỗi 2 — `.ass` khai cứng `1920×1080` cho video DỌC

Bản burn đầu tiên chạy xong, `dub-1.mp4` ra 88,9 MB. Nhìn ảnh mới biết sai:

```
...n công trình của mình đáng g...        ← cắt cả hai đầu
```

Đo được nguyên nhân:

| Số đo | Hậu quả |
|---|---|
| `PlayResX: 1920` / `PlayResY: 1080` (hằng cứng) | video là **1080×1920** → libass co giãn cả hệ toạ độ |
| `Style ... 54` cỡ chữ, `MarginL/R: 60` | 60 px theo hệ 1920 chỉ còn ~34 px thật trên khung 1080 |
| `WrapStyle: 2` | "chỉ xuống dòng ở `\N`" ⇒ dòng **693 ký tự** (`Bố! Bố! …`) KHÔNG được bẻ |

Sửa: `to_ass(..., khung=(rong, cao))`. `khung=None` giữ nguyên `1920×1080`/cỡ `54`/`WrapStyle: 2` **từng byte** (đường xuất tệp rời không biết video nào — đổi mặc định là đổi kết quả của mọi lượt xuất cũ mà không ai yêu cầu). Có `khung` thì `PlayRes` = khung thật, cỡ chữ/viền/lề co theo `min(rong/1920, cao/1080)` (trục NGẮN — chữ phải vừa cả hai chiều), và `WrapStyle: 0` để libass tự bẻ dòng.

### Đo cuối — ảnh chụp khung hình thật, không phải suy luận

Bốn mốc thời gian, bốn câu, **tất cả trọn vẹn trong khung**:

| t | Phụ đề Việt |
|---|---|
| 1 s | `Như một tác phẩm nghệ thuật.` |
| 20 s | `Đây là cốt lõi của tiểu nhi.` |
| 45 s | `Nó có thể đạt đến 2.000.` |
| 60 s | `Cả thiên đường lẫn thiên đường.` |

Tệp giao được:

```
dub-1.mp4   246,482,157 B   2026-10-31 18:14
  video : h264 1080x1920 yuv420p
  audio : aac 2 kenh 48000 Hz
  do dai: 278.5 s
  phu de mem: 0        ← chữ nằm trong PIXEL, đúng ý "burn cứng"
```

`278,5 s` khớp nguồn `278,546 s`. Không có track phụ đề mềm, đúng thiết kế.

### Một lỗi nữa, do chính tôi tạo và `try/except` che mất

Bản đầu của bước burn dùng thẳng biến `ban` của `run()` bên trong `_tron_va_remux` — nó **không nằm trong tầm với**:

```
[0.94] không burn được phụ đề (NameError: name 'ban' is not defined) — video vẫn có tiếng lồng, thiếu chữ
[0.96] video lồng tiếng: dub-1.mp4 (86899 kB) · KHÔNG có phụ đề
EXIT_DUB=0
```

`EXIT=0`, job "xong", tệp 88,9 MB — và **không có một chữ nào**. Đây đúng là kiểu hỏng im lặng mà một `except` rộng che mất. Sửa bằng cách truyền `chu_dich` xuống từ `run()` (nơi đã có `ban`), và giữ `except` — nhưng câu log phải nói **đúng thứ thiếu**, kèm `type(exc).__name__` và `str(exc)`, để lần sau đọc log là biết ngay.

### Một giới hạn phải nói thẳng, không phải lỗi bỏ sót

Phụ đề cứng tiếng Trung của video gốc (`压在2,000以内`) và logo `bilibili` **vẫn nằm nguyên** trong hình, và ở một số khung chúng **đè lên vùng chữ Việt**. Chúng đã ở trong pixel từ trước khi ta có tệp; không có cờ ffmpeg nào tách được chữ đã burn. Muốn xoá phải OCR + inpaint từng khung — việc khác hẳn, và không nằm trong yêu cầu.

### Đo cuối (sau ERRATA #60)

```
npx tsc --noEmit                   EXIT_TS=0
npm test (frontend)                148 tests, 148 pass, 0 fail, EXIT_TEST=0
pytest (venv, Windows)             1424 passed, 15 deselected, EXIT_PYTEST=0
job dub that (tron_nen=True)       76,1 s -> dub-1.mp4 246 482 157 B, EXIT_DUB=0
```

Năm bài mới trong `backend/tests/test_export.py` ghim hệ toạ độ, và **đã chứng minh không xanh giả**: phá `if khung is not None:` thành `if False:` ⇒ `3 failed, 40 passed` (đúng ba bài về khung), khôi phục ⇒ `43 passed`.