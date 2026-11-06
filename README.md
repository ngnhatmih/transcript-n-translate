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

## Đổi mặc định: ASR sang `fw-large-v3`, dịch sang `deepseek-web`

Hai khoá trong `backend/registry.json` là **DỮ LIỆU**, không phải literal trong code — đổi chúng là đổi mặc định của cả pipeline mà không sửa một dòng Python nào:

```json
"default_asr": "fw-large-v3",     // trước: fw-large-v3-turbo
"default_mt":  "deepseek-web",    // trước: opus-mt
```

Cả hai engine đều đã có sẵn trên máy này: `models--Systran--faster-whisper-large-v3` **3 203 MB** (khác `turbo` 1 547 MB), và gateway `whalegate` nghe ở `127.0.0.1:8790` với `GET /v1/models` → `200`, `deepseek-web` `available: true`.

### 🔴 `docker compose restart` KHÔNG nạp lại `registry.json`

Đây là cái bẫy đã đo được, và nó suýt làm tôi kết luận sai. Sau khi sửa `registry.json` trên máy và `docker compose restart api`, job dịch tự sinh vẫn chạy **`opus-mt`**:

```
id= 41 ws=2 type=translate engine=opus-mt  state=done
```

Nguyên nhân: container `COPY` code vào image **lúc build**, không mount. Đo hai nơi:

```
registry.json BEN TRONG container:  default_asr = fw-large-v3-turbo   default_mt = opus-mt
registry.json TREN MAY (đã sửa):    default_asr = fw-large-v3         default_mt = deepseek-web
```

Sửa bằng `docker cp backend\registry.json phu-de-lab-api-1:/app/registry.json`, rồi **đo lại để phát hiện 0 byte** (bẫy `docker compose cp` đã gặp trước đây):

```
size = 14179
default_asr = fw-large-v3
default_mt  = deepseek-web
```

Sau `restart`, job dịch tự sinh đổi đúng sang `deepseek-web` — đó là phép đo chứng minh, không phải suy luận.

### Tổng thời gian pipeline, đo trên video thật

Video `8f4b5304daf42569.mp4`: **278,546 s**, `1080×1920`, `h264 + aac 48 kHz`. Chạy trọn qua API thật (`POST /api/sources/upload` → `ingest` → `asr` → `translate`), mốc thời gian đọc từ `jobs.started_at`/`finished_at` trong DB của container:

| giai đoạn | engine | thời gian |
|---|---|---|
| upload (88,7 MB qua HTTP) | — | **0,5 s** |
| ingest (tách wav 16 kHz) | — | **≈ 0–2 s** |
| ASR | `fw-large-v3` | **25 s** / **13 s** (hai lượt, xem dưới) |
| dịch | `deepseek-web` | **14 s** / **12 s** |
| **TỔNG từ ingest bắt đầu đến dịch xong** | | **64,0 s = 1,1 phút** |

Hệ số: **0,230× thời gian thực** — video 4 phút 38 giây xử lý xong trong 64 giây.

⚠️ Vì sao có **hai** lượt ASR và hai lượt dịch: lượt chạy đầu (`upload` → job 42) tự sinh job ASR 43, và tôi lại `POST` thêm một job ASR 44 trên cùng source để chắc chắn engine mới được dùng. Cả hai đều `fw-large-v3` và cùng cho ra transcript, nên mỗi giai đoạn có hai số. Con số 64 s là của chuỗi **42 → 43 → 45** (một lượt trọn vẹn), không phải tổng của cả bốn job.

Đo riêng lẻ để đối chiếu (cùng video, cùng máy):

```
ASR  fw-large-v3, source 2   -> 21,1 s   (job 40, 103 đoạn)
dịch deepseek-web            -> 6,1 s và 12,1 s (job 45, 46; 103 đoạn)
ingest + ASR (lượt sạch)     -> 2,0 s + 38,4 s = 41,0 s tích luỹ
```

Con số ASR giao động **13–38 s** giữa các lượt là do lần đầu một engine phải **nạp model 3,2 GB vào VRAM** (`large-v3` nặng gấp đôi `turbo`); lượt sau model còn trong bộ nhớ nên nhanh hơn. Đây là lý do dòng "nạp engine" xuất hiện trong log job, và là thứ `SingleGpuGovernor` quản lý.

### Sáu bài test đã sửa vì đổi mặc định — và vì sao sửa đúng

Đổi hai khoá làm **8 bài đỏ + 11 lỗi setup**. Không bài nào là hồi quy; tất cả đều là test ghim mặc định cũ hoặc fixture thay registry rồi để mặc định thật đọc từ đĩa:

| bài | sửa gì |
|---|---|
| `test_registry.py` (2 bài) | ghim id mới `fw-large-v3` / `deepseek-web` |
| `test_mt_wiring.py` (2 bài) | ghim `default_mt` mới; bài "available là dò sống" nay kiểm **phép dò** (`_mark_availability`) thay vì đòi app dựng xong khi cả hai nguồn dò đều tắt |
| `test_api_sources.py` (3 chỗ) | fixture thay registry giả ⇒ phải thay **cả** `load_default_asr`; thêm ghim `openai_models_available` để suite không đọc môi trường (máy có whalegate hay không) |
| `test_api_translations.py` (1 bài) | bỏ ghim cứng `== "opus-mt"`, giữ vế đúng: mặc định đã ship phải **available** và có trong `mt_engines` |
| `test_e2e_fake.py` (1 chỗ) | fixture registry rút gọn ⇒ thêm `load_default_asr` |

Nguyên tắc rút ra: **một fixture thay `load_registry` bằng danh sách rút gọn thì phải thay luôn `load_default_*`**. Trước đây điều đó tình cờ đúng vì mặc định thật nằm trong danh sách; đổi mặc định là lộ ra chỗ dựa ngầm.

### Đo cuối (sau khi đổi mặc định)

```
npx tsc --noEmit                   EXIT_TS=0
npm test (frontend)                148 tests, 148 pass, 0 fail, EXIT_TEST=0
pytest (venv, Windows)             1424 passed, 15 deselected, EXIT_PYTEST=0
pipeline that (upload->dich xong)  64,0 s cho video 278,546 s = 0,230x thoi gian thuc
```

## 🔴 Pipeline ĐẦY ĐỦ gồm cả lồng tiếng: 158,1 s cho video 278,546 s

Con số `64,0 s` ở trên **chỉ đến `translate`** — nó KHÔNG phải pipeline đầy đủ. Chặng còn lại là lồng tiếng (TTS + tách nền `htdemucs` + trộn + remux + burn phụ đề), và nó tốn nhiều hơn cả ba chặng trước cộng lại.

Đo một lượt **liền mạch** trong một script (không thao tác chen giữa), trên `8f4b5304daf42569.mp4` 278,546 s:

| chặng | engine | thời gian |
|---|---|---|
| upload 88,7 MB + ingest | — | **2,0 s** |
| ASR | `fw-large-v3` | **32,3 s** |
| dịch | `deepseek-web` | **14,1 s** |
| **lồng tiếng** (TTS + `htdemucs` + trộn + remux + burn) | `vieneu-v3-turbo` | **108,8 s** |
| **TỔNG** | | **158,1 s = 2,6 phút** |

Hệ số **0,568× thời gian thực**. Lồng tiếng chiếm **69 %** tổng thời gian.

Tệp giao được (`dub-9.*`):

```
dub-9.mp4   252 169 196 B
  video: h264 1080x1920
  audio: aac 48000 Hz 2 kenh
  duration: 278.500000 s   (nguon 278,546 s)
  track phu de mem: 0      (chu nam trong PIXEL)
```

### ⚠️ Một con số 38,4 phút SAI, và vì sao nó sai

Lần đo đầu tiên tôi lấy hiệu `jobs.finished_at` của job dub trừ `jobs.started_at` của job ingest, ra **2 304 s = 38,4 phút**. Sai. Khoảng đó có:
- **400,7 s** rebuild image `api` (bắt buộc, xem mục dưới);
- thời gian tôi sửa 6 tệp test giữa các job.

Bài học: `finished_at(job cuối) − started_at(job đầu)` chỉ là thời gian pipeline khi **không có gì chen giữa**. Muốn đo pipeline thì phải chạy nó trong MỘT script liền mạch — đó là cách con số 158,1 s ra đời.

### 🔴 Container chạy code CŨ, và `grep` là cách phát hiện

Job dub đầu tiên (`#47`, `#48`) **không sinh `dub-*.mp4`** dù payload gửi `tron_nen: true`. Đo:

```
payload job 47 = {"translation_id": 7, "voice": null, "so_dong": null}   ← THIEU tron_nen
grep -n 'tron_nen' /app/app/api/routes_dubs.py   →  RONG, EXIT=0
wc -c /app/app/api/routes_dubs.py                →  8511     (tren may: 9219)
```

Container `COPY` code vào image **lúc build**. `docker compose restart` không nạp lại; `docker cp` từng tệp chỉ chữa được một tệp. Phải `docker compose build api` (**400,7 s**), rồi `docker compose up -d api`:

```
grep -c 'tron_nen' /app/app/api/routes_dubs.py  →  4
wc -c /app/app/api/routes_dubs.py               →  9219   (khớp máy)
default_asr = fw-large-v3   default_mt = deepseek-web
```

Sau đó `payload = {..., "tron_nen": true}` và log có `tách nền khỏi tiếng gốc (htdemucs)` → `remux vào video gốc` → `video lồng tiếng: dub-7.mp4 (246353 kB)`.

### Ràng buộc "không bao giờ chồng" — đo bằng số, không bằng lời

`dub-9.plan.json` có 103 dòng, mỗi dòng ghi `take`, `slot`, `avail`, `speed`. Đo chồng thật = `take/speed − avail` (thời lượng thật trừ cửa sổ từ `start` dòng này tới `start` dòng sau):

```
dem = {'vua': 41, 'nen': 62, 'nen_manh': 9}   trung_vi_toc_do = 1.077
so dong CHONG that: 2 / 103
  i=68  that=2.921 avail=2.920 du=0.001
  i=89  that=2.321 avail=2.320 du=0.001
tong thoi gian chong: 0.002 s
```

**2 ms tổng cộng trên 103 dòng** = sai số làm tròn (`speed` lưu 3 chữ số). Không nghe được, nhưng là **không phải 0 tuyệt đối** — và ràng buộc này bạn đặt là tuyệt đối nên nó được ghi đúng như đo được, không làm tròn thành "0".

Không dòng nào bị cắt chữ: `nen_manh` chỉ là nhãn CHẨN ĐOÁN (`speed > 1,5`, khó nghe), không phải trần chặn.

### Một cảnh báo trong log là của code CŨ

Job 47 in `19 dòng vượt trần 1.35× (nén tới trần, vẫn đè dòng sau)`. Chuỗi đó **không tồn tại** trong `dub.py` hiện tại — dòng 312 dùng ngưỡng `s > 1.5` và câu `đã nén đủ để không chồng, không cắt chữ`. Log của job 49 (code mới):

```
xong · 8 dòng phải nén trên 1,5× (đã nén đủ để không chồng, không cắt chữ): 12, 16, 21, 23, 32, 35, 58, 71
```

Khớp đúng `nen_manh: 8` trong `plan.json`. Đọc log cũ mà không đối chiếu mã là đọc một phiên bản phần mềm đã chết.

## ERRATA #61 — "OCR là chính" đã lỗi thời: nó XOÁ IM LẶNG lời nói mà OCR không đọc ra

**Phát hiện lúc:** chủ dự án đặt lại chính sách sau khi `ea0a78e` xong (dấu tích "Ghép nền").

### Giả định bị bác bỏ

`domain/nguon_chu.py` mở đầu bằng hợp đồng:

```python
if doan_ocr:
    return list(doan_ocr), f"dùng OCR: {len(doan_ocr)} dòng phụ đề đọc được từ hình"
```

Tức **OCR thắng TUYỆT ĐỐI**: chỉ cần đọc được MỘT dòng phụ đề cứng là bỏ toàn bộ ASR. Docblock
biện luận bằng số đo thật (OCR đúng 66,27 % so với ASR cùng đoạn; OCR phủ tới 1243 s còn ASR
dừng ở 1186,4 s) — những con số đó **vẫn đúng**, nhưng kết luận rút ra từ chúng thì sai.

### Vì sao sai

"Số dòng OCR nhiều hơn và chính xác hơn" là sự thật về **tổng thể**, không phải về **từng
đoạn**. Một video có phụ đề cứng ở 90 % thời lượng vẫn có những đoạn:

* phụ đề nằm NGOÀI `vung_doc` (người dùng kéo vùng đọc để loại watermark, và cắt mất phụ đề
  thật ở mép);
* khung bị mờ/nhoè vì chuyển động, OCR không nhận ra chữ;
* phụ đề cứng xuất hiện muộn hơn lời nói vài giây, nên một đoạn ASR rơi vào khoảng trống.

Ở cả ba ca, ASR **nghe được lời nói thật** mà OCR không đọc ra. Chính sách cũ xoá nó, và
không để lại dấu vết nào: transcript chỉ còn các dòng OCR, `engine = "rapidocr"`, job `done`.
Người dùng mất lời thoại mà không có cách nào biết đã mất gì — đúng lớp lỗi mà repo này gọi
là "im lặng".

### Chính sách mới (chủ dự án đặt)

> "kết hợp asr nghe trước để biết đoạn nào nói. Sau đó duyệt qua ocr. Nếu đoạn nào tách từ
> asr mà có cả ocr rồi thì đè ocr lên dùng. Kể cả 1 đoạn asr có 2 đoạn ocr thì ưu tiên dùng
> 2 đoạn ocr đó mà bỏ đoạn 1 đoạn asr kia. Còn nếu đoạn nào mà có asr nhưng ko có ocr thì
> đoạn đấy có thể thuộc diện nghi ngờ (Nhưng đó là chỉ nếu đang bật ocr)"

Hiện thực ở `hop_nhat_theo_doan` (`domain/nguon_chu.py`):

| tình huống | kết quả |
|---|---|
| đoạn ASR có ≥1 dòng OCR đè lên | dùng **chữ OCR**, bỏ chữ ASR |
| một đoạn ASR chứa **hai** dòng OCR | giữ **cả hai** dòng OCR, bỏ đoạn ASR |
| đoạn ASR **không** có OCR nào đè lên | giữ đoạn ASR, đặt **`suspect = True`** |
| dòng OCR không đè lên ASR nào | **vẫn giữ** (ASR dừng sớm — 1186,4 s so với 1243 s) |

Đoạn nghi ngờ **được GIỮ**, không bị xoá: xoá là mất lời nói thật và người dùng không biết.
`suspect` đã có sẵn trong `Segment`, `to_json` ghi nó ra, và `viecCuaDong`
(`frontend/src/lib/studio.ts:169`) biến nó thành việc **"nghi ngờ phiên âm"** trong cột việc
— người dùng tự xem và tự quyết. Chuỗi này đã khép sẵn từ trước; ERRATA này chỉ làm cho nó
được dùng đúng.

### Hai cái bẫy đo được khi làm

**(1) Mốc thời gian OCR là mốc KHUNG HÌNH, không phải mốc lời nói.** In toàn bộ 77 dòng của
transcript #13: **mọi dòng dài đúng `0,50 s`**.

```
i=0   0.00 -> 0.50  '作为一个搞艺术的'
i=1   1.50 -> 2.00  '最苦恼的事就是'
i=4  29.50 -> 30.00  '有时为了给作品上价值'
```

Vì `gop_thanh_dong` (`domain/phu_de.py:276-291`) đặt `end = t_hộp_cuối + 1/fps`, fps = 2.
OCR chỉ biết "dòng này hiện ở khung nào", sai số ±0,5 s ở **mỗi** đầu; ASR có mốc ~0,1 s. So
khít hai bên là so hai đơn vị khác nhau. Nên phép so dùng `DUNG_SAI_OCR = 0,5` — đúng một
nhịp khung, tức độ phân giải THẬT của OCR, không phải số tuỳ ý.

**(2) Nhánh thứ BA của cột `engine`.** `transcribe.py` trước đây chỉ kiểm
`ly_do.startswith("dùng OCR")`, nên chuỗi mới `"hợp nhất OCR + ASR: …"` rơi vào `else` và ghi
**engine ASR** cho một bản mà phần lớn chữ đọc từ HÌNH — lịch sử nói dối đúng kiểu mà comment
ngay trên câu đó cảnh báo. Nay có ba nhánh: `rapidocr` / `ocr+asr` / engine ASR.

### Bài test cũ đỏ, và nó đỏ ĐÚNG

`test_run_dung_ocr_khi_handler_co_ocr_engine` ghim `t.engine == "rapidocr"`. Fixture của nó
cho `OcrGia` và `AsrGia` cùng trả đoạn `0.0-2.0`, nên nay đi qua nhánh hợp nhất và ghi
`"ocr+asr"`. Kỳ vọng được **đổi kèm lý do** (không nới test cho xanh), và thêm
`test_run_ghi_engine_rapidocr_khi_chi_co_ocr` với ASR trả `[]` để nhánh OCR-thuần vẫn bị ghim
— nếu ai làm hỏng `if doan_ocr and doan_asr` thành luôn-đúng thì bài đó đỏ.

### Ba phép phá, ba bài đỏ

```
A. if doan_ocr and doan_asr: -> if False:   (về chính sách cũ)   2 failed
B. suspect=True -> suspect=False                                 1 failed
C. đánh suspect cả khi chỉ có ASR                                1 failed
```

Vế **C** quan trọng nhất: "OCR bật mà đọc ra rỗng" KHÁC "không có OCR". Video không có phụ đề
cứng thì OCR trả `[]` **hợp lệ**; đánh dấu nghi ngờ tất cả sẽ biến một video sạch thành hàng
trăm việc giả.

### Đo cuối

```
pytest tests/test_nguon_chu.py        14 passed
pytest (toàn bộ)                      1460 passed, 15 deselected   EXIT_PYTEST=0
npx tsc --noEmit                      EXIT_TS=0
npm test                              196 tests, 196 pass, 0 fail  EXIT_TEST=0
```

Số nền README: `1451` → **`1460`** (+8 bài `nguon_chu`, +1 bài `transcribe`).

## ERRATA #62 — `goc` bị vứt ở SÁU chỗ, và chú thích trần trong JSX hiện ra giao diện

**Phát hiện lúc:** chủ dự án gửi ảnh chụp timeline có dải chữ chạy ngang, sau commit `6a345bc`.

### Việc đang làm

Chủ dự án chỉ ra hai ảnh chụp cạnh nhau: bật/tắt lớp 2 thì **độ dài khối thay đổi**, và
**lớp 1 trải nhiều làn** thay vì một. Mục tiêu chốt: *"layer 1 chỉ có 1 làn"*.

Nguyên nhân gốc đã đo được trước đó: chữ trên poster bị OCR đọc thành phụ đề, vì bốn luật
cũ của `loc_hinh_dang` đều là luật NỘI DUNG CHỮ (dài 3–40, ≤2 cụm số, không toàn Latinh,
không lặp liền tiếp) và cả sáu khối poster đều lọt qua. Cách tách duy nhất là **góc
nghiêng**, đo từ bốn điểm RapidOCR trả về.

### Giả định bị bác bỏ (lần 1 — XOÁ DỮ LIỆU)

Chủ dự án chốt hai vế cùng lúc:

    "neu bi nghieng thi ko doc"
    "van co luu nha dung xoa may cai nghieng chi la ko cho vao layer nao thoi"

Tôi đọc vế đầu rồi đặt `continue` ngay trong `loc_hinh_dang`. **Sai.** Đo được (job asr
`#152`): transcript `#46` còn **152 đoạn** thay vì 158 — sáu khối poster biến mất khỏi bản
ghi, không khôi phục được. Vế thứ hai của chủ dự án nói rõ phải GIỮ.

Sửa: bỏ `continue`, để hộp nghiêng đi hết pipeline rồi `nguon_chu` gán `layer = ""`.

### Giả định bị bác bỏ (lần 2 — cùng một lỗi, sáu chỗ)

Sau khi bỏ `continue`, tôi sửa `gop_thanh_dong` và đo unit test thấy giữ góc. Nhưng chạy
job thật vẫn `0/158` đoạn có `goc`. Truy từng tầng trong container mới thấy **sáu** chỗ tạo
`Hop`/`Segment` MỚI mà không chép `goc`:

| Chỗ | Job đo | Kết quả |
|---|---|---|
| `noi_manh_cung_dong` (2 nhánh) | `#154` → `#47` | `0/158` đoạn có `goc` |
| `gop_thanh_dong` (2 dòng) | `#152` → `#46` | 6 khối poster biến mất |
| `nguon_chu` (2 nhánh `Segment(...)`) | `#158` → `#49` | chỉ 4/6 khối có `goc` |
| `keo_dai_theo_asr` | `#160` → `#50` | đủ 6/6 khối |

Bài học: `Segment` là `@dataclass` **thuần**, nên mọi chỗ `Segment(...)` là một chỗ có thể
làm rơi trường. Sửa một chỗ rồi đo unit test **không đủ** — phải chạy job thật và đếm
`co truong 'goc'` trên JSON trả về.

### Giả định bị bác bỏ (lần 3 — frontend, ba chỗ)

Backend đúng rồi mà DOM vẫn ba làn. Ba chỗ nữa, mỗi chỗ đo riêng:

1. `segmentsLoc` giữ `s.layer === null` với ý định "dữ liệu cũ chưa có `layer`". Nhưng
   `null` giờ có nghĩa thứ hai: khối bị loại khỏi mọi lớp. Đo props React trên trình duyệt:
   `{tong: 158, layer_null: 6}` và `tops = {1: 113, 19: 5, 37: 1}`.
2. `khoangVe` kéo không chặn trên. `i=103 '"Vịt thật nhàn"'` gốc **0,50 s** bị kéo thành
   **9,85 s** (19,70×) vì ASR `i=98` `"Muốn"` [167.49–181.85] bao trùm; cái dải đó chồng lên
   `i=104`. Chặn 2×.
3. `xepLan` coi chồng **2 px** là phải xuống làn khác. Ở 40 px/s đó là 0,05 s — ngắn hơn
   một khung 25 fps. Đổi ngưỡng sang **0,5 s theo THỜI GIAN**, không theo pixel: ngưỡng
   pixel phụ thuộc `pxPerSec` nên cùng dữ liệu ra số làn khác nhau khi zoom.

Kết quả đo trên DOM:

    trước:  tops = {1: 113, 19: 5, 37: 1, 181: 38}
    sau  :  tops = {1: 113, 181: 38}

### Giả định bị bác bỏ (lần 4 — chú thích trần trong JSX)

Sau khi sửa xong, tôi thêm sáu dòng chú thích giải thích ngay sau thẻ mở
`<div className="absolute inset-x-0 bottom-0" ...>` — **không bọc trong `{/* */}`**.

Trong JSX, chữ nằm giữa các thẻ được React in ra như **VĂN BẢN**. Cả đoạn hiện thành một
dải chữ chạy ngang timeline. Chủ dự án phải chụp ảnh mới phát hiện.

`tsc --noEmit` **không báo** vì chữ trần trong JSX là cú pháp hợp lệ — nó chỉ render ra thứ
không ai muốn. Đã quét toàn bộ `src/**/*.tsx`: 0 dòng còn lại.

    document.body.innerText.includes('VE THEO')  ->  false
    tops                                          ->  {1: 113, 181: 38}

### Đo cuối

```
pytest (toàn bộ)      1497 passed, 15 deselected   EXIT_PYTEST=0
npx tsc --noEmit                                   EXIT_TS=0
npm test              237 tests, 237 pass, 0 fail  EXIT_TEST=0
npm run build                                      EXIT_BUILD=0
docker compose build web                           EXIT_IMG=0
```

Dữ liệu thật: transcript `#50` **158 đoạn**, 6 khối poster vẫn còn với `goc` thật
(`-12,05 … -14,80°`) và `layer = None`. Không khối nào bị xoá.

Số nền README giữ nguyên `1497` — không thêm bài test nào trong lượt này (hai bài ghim
`goc` đã thêm ở lượt trước: `test_gop_thanh_dong_CHEP_goc_tu_Hop`,
`test_noi_manh_cung_dong_CHEP_goc`, `test_goc_hop_tinh_tu_bon_diem`).

## ERRATA #63 — `needs_review` tách khỏi `status`, ký tự lạ, và BA giả thuyết bị bác bỏ

**Phát hiện lúc:** làm nốt ba việc còn treo sau `4bc96d5`.

### 1. Cờ QA: `status` là cờ SẴN SÀNG, không phải cờ CHẤT LƯỢNG

Việc treo ghi là *"`qa_issues` tới được HTTP nhưng `status` không đổi"*. Đo trước khi sửa
(52 bản dịch trong DB, workspace 2):

    cps:      4715 cờ    <- TỐC ĐỘ ĐỌC vượt ngưỡng
    length:    714 cờ    <- TỈ LỆ ĐỘ DÀI
    lang:       53 cờ    <- DÒNG DỊCH VẪN LÀ CHỮ GỐC
    echo:        2 cờ    <- CHÉP NGUYÊN VĂN

Nếu coi cả bốn là lỗi thì **51/52 bản dịch thành không dùng được**, vì `cps` kêu ở 4715
chỗ và một dòng 26 ký tự trong cửa sổ 1 giây là chuyện bình thường của phụ đề. Tách theo
bản chất: **3/52** có lỗi nội dung thật (id=22, 17, 12); 48/52 chỉ có số đo.

**Giả định bị bác bỏ (lần 1):** tôi đổi `status` thành `needs_review` khi có lỗi nội dung.
`test_e2e_fake.py::test_full_pipeline_from_upload_to_srt` **ĐỎ**, và nó đúng — câu khẳng
định trong bài ghi rõ hợp đồng:

    "endpoint này phải phân biệt được `queued` với `done`: đây là thứ giao diện
    Workspace 2 dùng để biết bản dịch đã sẵn sàng chưa"

Trộn hai nghĩa vào một khoá là làm hỏng thứ giao diện đang dựa vào. Sửa: `status` giữ
nguyên, cờ chất lượng đi ra khoá riêng `needs_review` (`co_loi_noi_dung()` trong
`staleness.py`). Ba bài test ghim ranh giới này.

### 2. Ký tự lạ — luật hẹp, đo được

Quét TỪNG KÝ TỰ của translation #52 (158 đoạn): đúng **một** ký tự nằm ngoài Hán / ASCII /
Latinh mở rộng — `Λ` U+039B GREEK CAPITAL LETTER LAMDA, trong logo `ΛNI` ở `i=140`.

Luật `coKyTuLa` trong `Timeline.tsx` bỏ khối như vậy khỏi timeline. Ba miền phải GIỮ:

    Han             U+4E00-9FFF, U+3400-4DBF
    ASCII           (mọi ký tự ascii)
    Latinh mở rộng  U+00C0-024F, U+1EA0-1EFF    <- chữ Việt CÓ DẤU

Miền thứ ba là bắt buộc: một luật "chỉ cho ASCII" sẽ xoá sạch mọi phụ đề tiếng Việt.

Đo trên DOM sau khi sửa: `tops = {1: 105, 181: 38}` — lớp 1 vẫn đúng một làn, bớt 8 khối.
`ΛNI` không còn trên timeline nhưng **vẫn còn trong bảng việc cần xử lý** bên dưới — đúng
ý: không vẽ, nhưng không giấu dòng dữ liệu.

**Giả định bị bác bỏ (lần 2):** bài test đầu tiên tôi viết dùng
`queryAllByDisplayValue("ΛNI")` và nó ĐỎ với `actual: 1` — nhưng đó là **ô nhập trong
bảng**, thứ `laRac` không điều khiển. Phải kiểm khối trên timeline (`div[title]`).

### 3. `khoangVe` so độ giống chữ — ĐO XONG, KHÔNG LÀM

Việc treo: `bao()` chỉ so thời gian nên `i=103` bị coi là "nằm trong" ASR `i=98`.

Đo độ giống chữ của **55 cặp** ASR-bao-OCR trên #52, tách theo "cặp rác" (khối có `goc`
nghiêng, hoặc logo) và "cặp phụ đề thật":

    ngưỡng 0.3: bỏ 5/7 rác, giữ 39/48 thật, CẮT OAN 9
    ngưỡng 0.6: bỏ 7/7 rác, giữ 34/48 thật, CẮT OAN 14

Muốn chặn hết rác phải cắt oan **14 cặp phụ đề thật**. Ba ca tệ nhất:

    0.105  asr i=98 ocr i=103 '"Vịt thật nhàn"'      <- PHỤ ĐỀ THẬT
    0.148  asr i=98 ocr i=99  '"Mây khói vào rừng sâu' <- PHỤ ĐỀ THẬT
    0.000  asr i=139 ocr i=140 'ΛNI'                 <- RÁC

`i=103` và `i=140` có độ giống **gần bằng nhau**. Không ngưỡng nào tách được: `i=98` chỉ
là một từ ("Muốn"), nên so với bất kỳ chuỗi dài nào cũng ra số thấp.

Chặn 2× đã có từ ERRATA #62 giữ thiệt hại ở 1,0 s thay vì 9,85 s. **Không thêm ngưỡng
giống chữ** — dừng ở đây thay vì đặt một con số tuỳ ý.

### 4. Ba dòng "nén" — nguyên nhân là OCR ĐỌC SAI, không phải thuật toán gộp

Đo lại sau #62: **3** dòng nén > 3× (trước ghi 2):

    i=66   [102.00-102.50]  0.50s  51 ký tự  nén 4.86x
    i=67   [102.50-103.17]  0.67s  51 ký tự  nén 3.62x
    i=113  [189.50-190.00]  0.50s  47 ký tự  nén 4.48x

Tưởng là `noi_manh_cung_dong` bỏ sót. Đo trực tiếp trong container thì hàm **chạy đúng**:
hai hộp cùng chữ, cùng dải `y` (tâm lệch 1,0 px, bề dày 75 px), cách 0,5 s → **nối thành
một**. Kiểm riêng: 2 hộp vào → 1 hộp ra.

Nguyên nhân thật, đọc từ transcript #50:

    i=66  [102.00-102.50]  '那岁不是处处都是c位'   <- OCR đọc '岂' thành '岁'
    i=67  [102.50-103.17]  '那不是处处都是c位'     <- đúng

Hai bản OCR của **cùng một dòng phụ đề**, khác nhau một ký tự do đọc sai. Luật đòi `text`
bằng tuyệt đối nên không nối — đúng theo thiết kế.

**Giả định bị bác bỏ (lần 3):** nới ngưỡng nối theo độ giống chữ. Đo 17 cặp "gần giống"
trong 15 giây:

    0.947  102.0 -> 103.0  '那岂不是处处都是c位' | '那不是处处都是c位'

Hai câu **khác nhau thật** (`岂不是` vs `不是`) đạt 0,947 — cao hơn cả cặp OCR-sai cần nối.
Nới ngưỡng sẽ nối chúng và **mất chữ**. 14/17 cặp còn lại là watermark `想想工作室…`.

Kết luận: `noi_manh_cung_dong` đòi `text` bằng tuyệt đối là ĐÚNG. Dòng nén là hệ quả của
OCR đọc sai, không sửa được ở tầng gộp mà không phá câu thật.

### Đo cuối

```
pytest (toàn bộ)      1500 passed, 15 deselected   EXIT_PYTEST=0
npx tsc --noEmit                                   EXIT_TS=0
npm test              238 tests, 238 pass, 0 fail  EXIT_TEST=0
npm run build                                      EXIT_BUILD=0
docker compose build web                           EXIT_IMG=0
```

DOM sau cả ba việc: `tops = {1: 105, 181: 38}` — lớp 1 một làn, lớp 2 một làn.

Số nền README: `1497` → **`1500`** (+3 bài `needs_review`/`status`).

## ERRATA #68 — ba nút bước "Lồng tiếng / Ghép nền / Xuất" bấm KHÔNG xếp job nào

**Phát hiện lúc:** chủ dự án gửi ảnh thanh bước (`Lồng tiếng · chưa chạy`,
`Ghép nền · cần lồng tiếng xong`, `Xuất · cần ghép nền`) và yêu cầu: *"làm tương tự cái nút
để ấn lồng tiếng và tách âm ở trên này. Và cả xuất nữa"*.

**Bốn chỗ hỏng, cùng một triệu chứng.** Đo bằng cách cắm bộ ghi `fetch` trong app
(không thực thi request, để không xếp job thật):

| bấm | trước | sau |
|---|---|---|
| Phiên âm | `POST /api/jobs {"type":"asr","engine":"fw-large-v3-turbo",…}` | (vẫn thế) |
| Lồng tiếng | **không request nào** | `POST /api/dubs {"tron_nen":null,…}` |
| Ghép nền | **không request nào** | `POST /api/dubs {"tron_nen":true,…}` |
| Xuất | **không request nào** (chỉ hiện "cần ghép nền") | `POST /api/dubs {"tron_nen":true,…}` + lời báo |

1. `Studio.onStep("long")` chỉ `datLacQuan` + `setView("dub")` rồi `return` — nên bước
   "Lồng tiếng" đổi màu sang "đang chạy…" mà **không có job nào**. Đây là lý do người dùng
   thấy "nút không ấn được": giao diện phản hồi, sản phẩm thì không làm gì.
2. `App.onBuoc` **không có nhánh `ghep`**. Ghép nền không phải loại job riêng — nó là job
   `dub` mang `payload.tron_nen = true`, và chính nó sinh `dub-{tid}.mp4`.
3. `endpoints.makeDub` **không gửi `tron_nen`**: body chỉ có `translation_id/voice/style`.
   Thiếu cờ đó thì `Studio.jobGhep` (lọc `type === "dub" && payload.tron_nen === true`) luôn
   `null` ⇒ `coFileXuat` luôn `false` ⇒ bước "Xuất" đứng ở "cần ghép nền" **vĩnh viễn**.
4. `onStep("xuat")` khi chưa có tệp chỉ `setNotice("Chua xuat duoc: …")` — bấm "Xuất" mà
   không có đường nào để CÓ tệp.

**Sửa:** `long`/`ghep` gọi `onBuoc` (kèm cổng chặn: chưa có bản dịch thì nói lý do, đang
chạy thì không xếp chồng); `makeDub(id, voice, tronNen)`; `App.onBuoc("ghep")` →
`makeDub(…, true)`; bấm "Xuất" khi chưa có tệp thì **tự xếp job ghép nền** rồi báo phải chờ,
có tệp rồi thì tải.

**Ghim:** `bấm bước Lồng tiếng XẾP job lồng tiếng`, `bấm bước Ghép nền XẾP job ghép`,
`bấm Xuất khi CHƯA có tệp…`, `bấm Xuất khi ĐÃ có tệp…` (`Studio.test.tsx`), và
`makeDub: tron_nen phải nằm trong BODY` (`endpoints.test.ts`).

### Đo cuối

```
npm test              269 pass, 0 fail              EXIT_TEST=0
npx tsc --noEmit                                    EXIT_TS=0
docker compose build web                            EXIT_BUILD=0
```

## ERRATA #69 — lồng tiếng XONG mà khung xem vẫn phát tiếng GỐC

**Phát hiện lúc:** chủ dự án: *"lồng tiếng xong rồi nhưng chưa nghe được ở trên vid"*.

**Nguyên nhân — hai lớp, cả hai đều thật:**

1. Khung xem phát `/api/media/<id>`: đó là tiếng của **video gốc**. Bản lồng `dub-<tid>.wav`
   đã nằm trên đĩa (đo được: `24726764` byte, 278,55 s) nhưng không có đường nào phát nó cùng
   hình.
2. Không thể mượn route `GET /api/dubs/{id}/download?format=wav`: `FileResponse(..., filename=)`
   gắn `Content-Disposition: attachment`, và Chrome coi URL đó là một lượt **TẢI XUỐNG** —
   `<audio>` không bao giờ phát (`readyState: 0`, `play()` không resolve). Chính repo này đã
   ghi lại hiện tượng đó ở route `take`; nên chỗ **nghe** phải là `inline`.

**Sửa:**

- Route mới `GET /api/dubs/{translation_id}/audio` — trả `dub-<tid>.wav` với
  `Content-Disposition: inline`, có `Range`. Đo được:
  `206 · audio/wav · inline; filename="dub-63.wav" · accept-ranges: bytes · content-range: bytes 0-99/24726764`.
- `usePlayer(media, giongLong)`: khi có bản lồng thì `<video>` bị **tắt tiếng** (hình giữ
  nguyên) và một thẻ `<audio>` phát đè, bám mốc mỗi lượt (kéo lại khi lệch quá 0,3 s).
  Tệp lồng hỏng thì **bật lại** tiếng gốc — không để khung xem câm im lặng.
- Nút cạnh "Phát": **"Âm: bản lồng" ⇄ "Âm: bản gốc"**, chỉ hiện khi job `dub` đã `done`
  (nghe được bản lồng không cần `tron_nen`).

**Đo trong app** (Chrome thật, đoạn 0:00, sau 2,5 s phát):

```
the audio app tao : src="/api/dubs/63/audio"  preload=auto  readyState=4
video.muted       : true
sau 2,5 s         : video 21,07 s   audio 21,00 s   => lech 0,063 s
```

**Ghim:** `test_route_nghe_ban_long_tra_INLINE_va_404_khi_chua_long` (backend) và ba bài
trong `Studio.test.tsx` (có nút + video tắt tiếng; bấm thì về tiếng gốc; chưa lồng xong thì
không có nút).

### Đo cuối

```
pytest (toàn bộ)      1523 passed, 15 deselected   EXIT_PYTEST=0
npm test              272 pass, 0 fail             EXIT_TEST=0
npx tsc --noEmit                                   EXIT_TS=0
```

## ERRATA #70 — "Ghép nền" chạy lại CẢ lượt lồng tiếng (TTS 5–7 phút) vì nó vẫn là job `dub`

**Phát hiện lúc:** chủ dự án: *"tại sao ấn ghép nền thì nó chạy lại cả lồng tiếng"*.

**Nguyên nhân:** "Ghép nền" không phải một loại job — nó là job `dub` mang `tron_nen = true`
(xem ERRATA #68). Mà `DubHandler.run()` chạy theo đúng thứ tự cố định:

```
dòng 331   lay = self._tts([...])          <- TTS TOÀN BỘ bản dịch
dòng 362   master = rap(dat, ...)          <- ghép các take thành dub-<tid>.wav
dòng 374   if tron_nen: self._tron_va_remux(...)   <- CHỈ Ở ĐÂY mới trộn nền
```

Nên cờ `tron_nen` chỉ thêm việc ở CUỐI; nó không bỏ được việc ở ĐẦU. Bấm "Ghép nền" là chạy
lại toàn bộ TTS — 5–7 phút — cho một việc mà đầu vào `dub-<tid>.wav` đã nằm sẵn trên đĩa.

**Sửa:** thêm cờ `chi_tron` (cả `DubIn` ở `POST /api/dubs` và `DubPayload` ở
`POST /api/jobs`, vì cả hai đường đều vào `DubHandler.run`). Có cờ đó thì `run()`:

- đòi `dub-<tid>.wav` phải tồn tại; thiếu thì **NÉM** `chưa có bản lồng … chạy Lồng tiếng
  trước`, KHÔNG lặng lẽ chạy lại TTS;
- bỏ hẳn nhánh TTS và nhánh ghép take, đi thẳng vào `_tron_va_remux` với master đã có;
- báo `ghép nền từ bản lồng đã có: dub-63.wav (24726764 byte) — không chạy lại TTS`.

Giao diện: bước "Ghép nền" (và nhánh "Xuất chưa có tệp" tự xếp ghép nền) gửi
`chi_tron = true`, và **chặn sớm** khi job `dub` chưa `done` — nói "bấm Lồng tiếng trước"
thay vì xếp một job backend chắc chắn ném.

**Ghim:** `test_GHep_nen_dung_lai_ban_long_KHONG_chay_lai_TTS` (TTS không được gọi lần nào,
master không bị ghi đè, progress kết ở 1.0),
`test_GHep_nen_khi_CHUA_co_ban_long_thi_NEM_chu_khong_chay_lai_TTS`,
`makeDub: chi_tron phải nằm trong BODY`, và hai bài chặn sớm ở `Studio.test.tsx`.

### Đo cuối

```
pytest (toàn bộ)      1527 passed, 15 deselected   EXIT_PYTEST=0
npm test              274 pass, 0 fail             EXIT_TEST=0
npx tsc --noEmit                                   EXIT_TS=0
```

## ERRATA #71 — engine dịch mặc định bị TẮT dịch vụ ⇒ cả API không khởi động được

**Phát hiện lúc:** container `api` crash-loop (`Restarting (1)`), app trắng dữ liệu.

```
RuntimeError: engine dịch mặc định 'deepseek-web' không sẵn sàng: nó có trong registry
nhưng model chưa được pull hoặc runtime không phục vụ được
```

**Nguyên nhân:** `deepseek-web` là engine `runtime: "http"` trỏ `127.0.0.1:8790` (gateway
`whalegate`). Gateway tắt ⇒ `available = False` ⇒ `build_components()` ném ngay lúc khởi
động (đúng thiết kế "fail ở chỗ sớm nhất"), nhưng hệ quả là **không có API nào cả** — kể cả
những đường không liên quan dịch thuật.

**Xử lý TẠM (theo yêu cầu chủ dự án):** `default_mt` đổi `deepseek-web` → `hy-mt-1.5-7b`
(engine Ollama, model `hy-mt1.5-7b:q4_K_M` đã pull trên máy này), và setting
`default_mt_engine` trong DB cũng đặt về engine đó. Bật lại gateway rồi thì trả
`default_mt` về `deepseek-web` là xong.

**Sửa kèm — bộ test không được phụ thuộc lựa chọn đó.** Sáu bài đỏ vì chúng đọc FILE
`registry.json` để biết mặc định, hoặc vì fixture tự khai "Ollama đã pull mọi thứ". Nay:

- `tests/conftest.py::mo_hinh_mac_dinh()` đọc `config.REGISTRY_PATH` để biết `model_ref`
  của engine mặc định (không viết cứng id);
- fixture của `test_api_translations.py` và harness của `test_mt_wiring.py` **ghim**
  `main.load_default_mt` về `opus-mt` (in-process) — chúng kiểm ngữ nghĩa `available` và
  đường ống dịch, KHÔNG kiểm engine mặc định là cái nào;
- bài nào muốn nói về mặc định thì tự đặt lại (xem
  `test_build_components_refuses_an_mt_default_that_is_not_available`), và bài đối chứng
  `test_build_components_still_accepts_an_available_mt_default` đọc mặc định **đang có hiệu
  lực** qua `main.load_default_mt` thay vì đọc file.

## ERRATA #72 — hộp burn SAI CHIỀU CAO khi câu dài, và libass tự bẻ dòng khác mô phỏng

**Phát hiện lúc:** ảnh chủ dự án gửi — dòng đầu của phụ đề nằm **ngoài** hộp trắng (style
`co 91, vien 20, cao_hop 60`, câu dài thành 3 dòng).

**Hai lỗi, cùng lộ ra khi `cao_hop` nhỏ:**

1. **Chiều cao khối tính bằng `nét_chữ × số_dòng`.** Đo trên ảnh burn 3 dòng: đỉnh các dòng
   ở **1366 / 1417 / 1468** ⇒ **bước dòng = 51 px = 1,0 × cỡ chữ**; còn nét chữ (Pillow ×
   0,637) chỉ **29 px**. Công thức cũ cho hộp cao `29 × 3 = 87` (→ 109 với viền) trong khi
   khối chữ cao **132** ⇒ dòng 1 thò ra ngoài.
   Sửa: `cao = nét_một_dòng + (n−1) × co` (bước dòng = 1,0 em, SỐ ĐO với file Archivo đang
   ship — đổi font thì phải đo lại).

2. **libass tự bẻ dòng khác mô phỏng của backend.** Với câu 86 ký tự, mô phỏng báo dòng dài
   nhất **922 px** (hộp 944) nhưng libass bẻ thành **680 + 600**, để lại **đệm 132 px** mỗi
   bên thay vì 11. Sửa: `to_ass` phát **`\N` tường minh** khi có vẽ hộp ⇒ libass không tự bẻ,
   số dòng và dòng dài nhất do MỘT mô phỏng quyết định.

**Đo lại bản burn** (cùng style, 3 dòng):

```
trước: hộp 998 × 109 · chữ 132 cao (dòng 1 NGOÀI hộp)
sau  : hộp 998 × 153 · chữ nằm TRỌN trong hộp (route trả cao=131, +2·viền 11 = 153)
```

**Ghim:** `test_cao_khoi_chu_dung_BUOC_DONG_chu_khong_phai_net_chu` (tiêm font giả nên chạy
được cả trên máy không có file font: `cao == nét + (n−1)×51`, và KHÔNG được bằng `nét × n`).

## ERRATA #73 — phụ đề trên web lệch bản burn: hai bên bẻ dòng bằng HAI bộ đo

**Phát hiện lúc:** chủ dự án: *"tìm cách để phụ đề trên web ko lệch so với bản burn vào
video"*.

**Đo được** (style THẬT trong `localStorage`: `co 91, vien 20, cao_hop 180, dam true`,
video 1080×1920, câu *"Chi phí hiện tại … phí nhập là 5000"*):

| | số dòng | dòng | hộp | đệm |
|---|---|---|---|---|
| bản burn | 2 | 926 + 352 | 944 × 180 | 10 / 8 px |
| bản xem trước (trước) | 3 | 872 / 947 / 122 | 969 × 214 | 11,25 |
| bản xem trước (sau) | 2 | (cùng chuỗi với burn) | **947 × 180** | 11,25 |

**Bốn nguyên nhân, sửa theo thứ tự:**

1. **Cỡ chữ tính bằng pixel của KHUNG HIỂN THỊ** (~132 px) chứ không phải pixel video:
   `co 30` ra 2,06 px, mà ở cỡ đó Chrome không cho ký tự hẹp hơn ~1 px ⇒ tỉ lệ chữ/hộp
   lệch hẳn (đo được hộp xem 62 % khung, burn 41,6 %). Nay lớp đè dựng trong **hệ pixel
   video** (`hinhHocVideo` = đúng công thức `to_ass`) rồi thu cả khối bằng
   `transform: scale(hop.rong / videoW)`.
2. **libass TỰ bẻ dòng khác mô phỏng của backend**: mô phỏng báo dòng dài nhất 922 px (hộp
   944) nhưng libass bẻ thành 680 + 600, để lại **đệm 132 px** mỗi bên. Nay `to_ass` phát
   **`\N` tường minh** khi có vẽ hộp ⇒ libass không tự bẻ, số dòng do một mô phỏng quyết.
3. **`fit-content` + `maxWidth` không co theo dòng đã bẻ**: nó lấy `max-content` rồi kẹp ở
   `maxWidth`, nên hộp rộng bằng CẢ bề ngang bẻ dòng (1013 px). Bỏ `maxWidth` thì Chrome
   vẫn tính `max-content` của cả câu vì `<br>` không làm nó nhỏ đi (**1963 px**). Phải cho
   **mỗi dòng là một khối** ⇒ hộp = dòng dài nhất + 2·viền.
4. **Hai bộ đo khác nhau**: Pillow (burn) vs `canvas.measureText` (web) lệch ~10 % bề ngang
   chữ ở đúng chỗ quyết định bẻ dòng. Nay backend là **nguồn duy nhất**:
   `subtitle_format.khoi_chu()` + `POST /api/subtitles/lines`; `PhuDeOverlay` dùng thẳng
   `rong + 2·viền` từ route, `canvas` chỉ còn là đường dự phòng khi API chưa về.

**Lỗi thật đã vấp trong lúc làm, ghi lại:** đặt `useState`/`useEffect` **sau** một `return`
sớm ⇒ React ném *"Rendered more hooks than during the previous render"* và CẢ TRANG thành
*"Trang này không tải được"*. Hook đã chuyển lên trước mọi `return` sớm.

**Ghim:** `test_api_subtitles.py` (hình dạng route + không đo được thì trả một dòng),
`hinhHocVideo: cỡ chữ là pixel CỦA VIDEO`, và các bài hình học hộp ở `test_phu_de_style.py`.

## ERRATA #74 — phụ đề BURN đè nhau: đường burn không lọc theo lớp, đường xuất tệp thì có

**Phát hiện lúc:** chủ dự án: *"khi burn phụ đề có mấy cái bị đè nhau … tôi muốn nó đợi cái
được burn trước hết xong mới đến lượt cái sau"*, và giới hạn phạm vi: *"vẫn đang xét trong
layer 1 / làn 1 thôi"*.

**Đo được trên bản dịch #63** (đếm cặp chồng thời gian, sau khi lọc theo lớp):

```
TRƯỚC: 163 đoạn · 61 cặp chồng · tổng 64,26 s chồng
       ví dụ  7,02-8,00  lớp 1  "Thường xuyên phải chứng minh"
              7,02-9,66  lớp 2  "Thường xuyên phải chứng minh tác phẩm…"
SAU  : 110 đoạn · 0 cặp chồng
```

**Nguyên nhân:** timeline GIỮ CẢ HAI dòng của một câu (lớp 1 + lớp 2) để người đọc soát — đó
là chủ ý. Đường **xuất tệp** đã lọc (`ExportHandler.run` gọi `mot_dong_moi_cap`, có từ trước:
*"khi dùng phụ đề thì ưu tiên chặt đúng layer 1"*), nhưng đường **burn vào video**
(`DubHandler._tron_va_remux`) truyền thẳng `transcript.segments` — nên hai câu khác nhau của
hai lớp được vẽ chồng ở cùng một mốc.

**Sửa hai lớp bảo vệ, cùng một chỗ:**

1. **Lọc theo lớp** đúng như đường xuất tệp — chữ đi kèm lọc theo CÙNG chỉ số (lệch chỉ số
   là câu hiện ra lệch hàng).
2. **`phu_de.xep_hang_trong_lop`** — đoạn sau ĐỢI đoạn trước hiện xong: dời `start` lên đúng
   `end` của đoạn trước, GIỮ `end` (thà dài hơn còn hơn nuốt mất dòng), và **chỉ so trong
   cùng một lớp** (hai lớp là hai làn hiển thị, chồng nhau ở đó là bình thường). Với dữ liệu
   hiện tại bước này không đổi gì — nó là BẢO HIỂM cho dữ liệu mà hai dòng cùng lớp vẫn chồng.

**Ghim:** 8 bài trong `tests/test_dub.py` — 5 bài cho phép xếp hàng (dời đúng `end`, không
đụng lớp khác, không để đoạn 0 giây, không sửa danh sách gốc, danh sách rỗng), 1 bài dựng
`.ass` rồi đọc ngược `Dialogue` để khẳng định không còn hai dòng cùng lớp chồng nhau, 1 bài
khẳng định sau khi lọc theo lớp thì lớp 1 hết cặp chồng, 1 bài khẳng định giữ bản OCR thay vì
bản ASR.

### Đo cuối

```
pytest (toàn bộ)      1535 passed, 15 deselected   EXIT_PYTEST=0
npm test              275 pass, 0 fail             EXIT_TEST=0
npx tsc --noEmit                                   EXIT_TS=0
```

---

## ERRATA #75 — burn phụ đề mã hoá lại CẢ PHIM bằng CPU: 75 s mỗi lượt ghép, dù máy có GPU

**Phát hiện lúc:** chủ dự án: *"máy có gpu"* — sau khi `Ghép nền` đã hết chạy lại TTS
(ERRATA #70) và bản trộn đã được cache, câu hỏi còn lại là chỗ nào còn CHẬM. Đo ra: phần còn
lại của một lượt ghép gần như toàn bộ là **mã hoá lại video** để vẽ chữ vào từng khung hình.

**Vì sao phần đó không tránh được:** phụ đề cứng nằm trong PIXEL. Không có cờ nào copy được
một stream mà lại vẽ thêm chữ lên nó — `-c:v copy` là bỏ luôn phụ đề. Muốn nhanh thì chỉ còn
cách làm cho phép mã hoá nhanh hơn, tức là GPU.

**Đo được** (cùng film 4:38, 1080×1920, 8 355 khung, bản trộn `dub-63.tron.wav` đã cache nên
chỉ còn burn + remux; thời gian là của CẢ job, thăm dò mỗi 3 s nên thực tế trong khoảng ±3 s):

| bộ mã hoá | tham số | thời gian | dung lượng ra |
|---|---|---|---|
| `libx264` | `-preset medium -crf 18` | **75 s** | `237 997 kB` (238 MB) |
| `h264_nvenc` | `-preset p5 -rc vbr -cq 20 -b:v 0` | **37 s** | `375 325 kB` (366 MB) |
| `h264_nvenc` | `-preset p5 -rc vbr -cq 23 -b:v 0` | **39 s** | `271 247 kB` (265 MB) |

Hai dòng `h264_nvenc` là hai lần đo RIÊNG, không phải ngoại suy: `-cq 23` chạy hai lượt
(job #200 và #201, lượt sau trên image vừa build lại) và ra đúng cùng một dung lượng
`271 247 kB`. Tức là **nhanh gần gấp đôi** (75 s → 39 s), và cái giá là **+11 % dung lượng**
(265 MB so với 238 MB) — chọn `-cq 23` chứ không phải `-cq 20` chính vì lý do đó: `-cq` của
NVENC **không** tương đương `-crf` của x264, `-cq 20` phình ra +54 %.

**Ba lỗi đường đi, mỗi lỗi đều làm "máy có GPU" thành vô nghĩa:**

1. **Container không thấy thư viện mã hoá.** `nvidia-smi` chạy được, CUDA chạy được (TTS vẫn
   dùng GPU), nhưng `ffmpeg -c:v h264_nvenc` báo `Cannot load libnvidia-encode.so.1`. Docker
   chỉ mount `libnvidia-encode.so.1` khi được cấp capability `video`; compose đang để mặc
   định `compute,utility`. Sửa: thêm `NVIDIA_DRIVER_CAPABILITIES: compute,utility,video`.
2. **Phép dò ở khung quá nhỏ.** Dò bằng ffmpeg trên khung 64×64 bị NVENC từ chối: *"Frame
   Dimension less than the minimum supported value"* ⇒ `co_nvenc()` trả `False` trên một máy
   RTX 3070. Sửa: dò ở **320×240**.
3. **Dò lại mỗi lượt.** Kết quả được nhớ ở biến module (`_CO_NVENC`), nên mỗi tiến trình chỉ
   tốn một lần ffmpeg ~50 ms.

**Cách sửa** (`pipeline/tach_nen.py`): có NVENC thì `h264_nvenc -preset p5 -rc vbr -cq 23
-b:v 0`; không có thì `libx264 -preset medium -crf 18` — **giữ nguyên** hành vi cũ từng byte.
Và nếu NVENC hỏng GIỮA ĐƯỜNG (driver cũ, hết VRAM) thì bắt `CalledProcessError` rồi **làm
lại bằng CPU**, chứ không ném ra ngoài: một lượt ghép đã tách nền + trộn xong rồi, mất nó vì
GPU hắt hơi là mất 5–7 phút của người dùng.

**Ghim:** 5 bài trong `tests/test_tach_nen.py` — có GPU ⇒ đúng `h264_nvenc` + `-cq 23` và
KHÔNG còn `-crf`; không GPU ⇒ `libx264 -crf 18`; NVENC ném giữa đường ⇒ lần hai là `libx264`;
`co_nvenc()` chỉ dò MỘT lần và dò ở `s=320x240`; ffmpeg dò trả mã lỗi ⇒ `False` chứ không ném.
Không bài nào cần GPU: chúng thay `subprocess` của module bằng hàm chỉ ghi lại lệnh.

**Kiểm bằng mắt, không chỉ bằng số:** trích một khung ở 60 s từ `dub-63.mp4` bản NVENC, câu
*"Cùng sống lâu với trời đất"* hiện đúng trong hộp đen, chữ sắc, không khung xanh, không nhoè;
`ffprobe` báo `h264 1080×1920`, `8355` khung, `278,500 s` — bằng đúng film gốc.

### Đo cuối

```
pytest (toàn bộ)      1541 passed, 15 deselected, 11 warnings   EXIT_PYTEST=0
npm test              278 pass, 0 fail                           EXIT_TEST=0
```

---

## ERRATA #76 — bước "Lồng tiếng" ghi "đang chạy…" trong khi việc đang chạy là GHÉP NỀN

**Phát hiện lúc:** chủ dự án gửi ảnh thanh bước và hỏi: *"là sao nhỉ ấn xuất vẫn chạy lại
lồng tiếng"*. Trong ảnh, CẢ ba bước hiện: `Lồng tiếng — đang chạy…`, `Ghép nền — đang
chạy…`, `Xuất — cần ghép nền`.

**Đo được — TTS KHÔNG hề chạy lại.** Đối chiếu hàng đợi thật đúng lúc đó:

```
#202 dub done  payload {"translation_id":63,"tron_nen":true,"chi_tron":true,...}
     log    ghép nền từ bản lồng đã có: dub-63.wav (24726764 byte) — không chạy lại TTS
            dùng lại bản trộn đã có (dub-63.tron.wav) — chỉ burn lại phụ đề + remux
            video lồng tiếng: dub-63.mp4 (270022 kB)
     thời gian 06:25:09 → 06:25:47  (38 s; một lượt TTS thật là 5–7 phút)
```

Tức là backend làm đúng (ERRATA #70 vẫn còn tác dụng), và **chỉ giao diện nói sai**.

**Nguyên nhân:** bước "Lồng tiếng" đọc `dubState` từ `jobDub`, và `jobDub` **cố ý** không lọc
`tron_nen` — chú thích cũ trong `Studio.tsx` viết: *"job `dub` có ghép nền vẫn là job lồng
tiếng (nó làm cả hai việc), nên bước Lồng tiếng phải thấy nó"*. Câu đó **đã sai kể từ khi có
`chi_tron`**: lượt ghép nền không còn làm việc lồng tiếng nữa, nó chỉ trộn + burn + remux.
Nên một lượt burn đang chạy kéo bước "Lồng tiếng" (đã xong từ lâu) về "đang chạy…".

**Sửa:** tách đôi, vì hai câu hỏi khác nhau:

| biến | câu hỏi nó trả lời | lọc |
|---|---|---|
| `jobDub` | *đã có bản lồng chưa?* (nghe thử, chặn ghép nền) | mọi job `dub` của bản dịch |
| `jobLong` | *lượt lồng tiếng gần nhất thế nào?* (vẽ bước) | `chi_tron !== true` |

Điều kiện là `chi_tron !== true` chứ không phải `tron_nen !== true`: job ghép nền đời cũ
**có** chạy TTS và không mang `chi_tron` — nó vẫn là một lượt lồng tiếng thật, phải hiện đúng.

`trangThaiLong` = trạng thái của `jobLong`; nếu không có job nào như vậy thì chỉ dám nói
`done` khi có một job `dub` đã `done` (chính nó sinh ra `dub-{tid}.wav`) — **không** lấy trạng
thái của một lượt ghép nền đang chạy làm bằng chứng TTS đã chạy.

Kèm một chỗ cùng gốc: nút "Lồng tiếng" chặn bấm theo `jobDub`, tức đang ghép nền thì người
dùng bị từ chối lồng tiếng. Nay chặn theo `jobLong` — hai việc độc lập.

**Ghim:** 4 bài trong `Studio.test.tsx` — (1) job lồng tiếng `done` + job ghép nền `running`
⇒ bước Lồng tiếng là *đã lồng*, chỉ bước Ghép nền *đang chạy…* (đây đúng là ảnh chụp của chủ
dự án); (2) job lồng tiếng THẬT đang chạy ⇒ vẫn *đang chạy…* (vế chống sửa quá tay — bỏ hẳn
`dubState` là hỏng vế này); (3) chỉ có một job ghép nền đã `done` (dữ liệu cũ) ⇒ vẫn coi là
*đã lồng*; (4) đang ghép nền **không** chặn bấm Lồng tiếng.

### Đo cuối

```
npm test              282 pass, 0 fail                           EXIT_TEST=0
npx tsc --noEmit                                                 EXIT_TS=0
```

---

## ERRATA #77 — hàng đợi gọi lượt BURN PHỤ ĐỀ là "lồng tiếng", và gọi việc XUẤT `.ass` là "ghép nền"

**Phát hiện lúc:** chủ dự án hỏi đúng chỗ: *"cái burn video này hiện tại thuộc job nào nói rõ
ra"*, rồi ngay sau đó: *"khi chạy cái đó thì nó có đụng vào mấy cái khác trong phase ko?"*.

**Sự thật về chỗ burn nằm:** nó **không có loại job riêng**. `PAYLOAD_SCHEMA`
(`routes_jobs.py:196`) chỉ có bốn loại — `ingest`, `asr`, `dub`, `export`. Burn là một job
`dub` mang `tron_nen = true`; bản có thêm `chi_tron = true` thì **không chạy TTS**:

```
POST /api/dubs            → job type="dub", phase="dub:vieneu-v3-turbo"
DubHandler.run            dub.py:300
  └ chi_tron == true      dub.py:332   không chạy TTS, đi tiếp
    └ _tron_va_remux      dub.py:339
        ├ ghi dub-63.ass  dub.py:565   (lọc theo lớp + xếp hàng)
        └ tach_nen.remux(..., phu_de=ass)   dub.py:582
            └ ffmpeg -vf ass='…' + h264_nvenc -cq 23    tach_nen.py:305-315
```

Nên panel hàng đợi in **"lồng tiếng · vieneu-v3-turbo"** cho một lượt chỉ burn 39 s — đúng cái
làm chủ dự án tưởng TTS chạy lại — và in **"ghép nền"** cho job `export`, vốn chỉ ghi `.srt`/
`.ass` mà không đụng một khung hình nào. Hai nhãn sai, cùng một nguyên nhân: nhãn đọc `type`,
không đọc `payload`.

**Vì sao KHÔNG đổi `phase` (đây là phần trả lời câu hỏi thứ hai):** rất dễ "sửa cho đẹp" bằng
cách đặt phase riêng `burn:phude`, và nó phá hai thứ, cả hai đều im lặng:

1. **Thứ tự hàng đợi.** `Worker.tick` (`worker.py:139-165`) là FIFO TOÀN CỤC: bốc
   `oldest_queued()`, rồi hút **hết** job cùng `phase` (`next_queued_for_phase`, SQL
   `WHERE state='queued' AND phase=? ORDER BY id`, `sqlite_repos.py:589`) trước khi đổi giai
   đoạn. Một lượt burn mang phase riêng sẽ bị các job `dub` **mới hơn** vượt mặt, vì chúng
   cùng phase với giai đoạn đang chạy.
2. **VRAM.** `SingleGpuGovernor.before_phase` (`adapters/governor/single_gpu.py:38-41`) gọi
   **mọi** releaser của phase KHÁC. Vào `burn:phude` ⇒ model TTS bị đẩy khỏi VRAM; lượt lồng
   tiếng kế tiếp phải nạp lại. Cộng thêm `phase_switches` trong `GET /api/status` tăng vô ích.

**Sửa — chỉ ở chỗ hiển thị** (`frontend/src/lib/studio.ts::nhanJob`), đọc `payload` thật:

| job | payload | nhãn |
|---|---|---|
| `dub` | `chi_tron = true` | `ghép nền · burn phụ đề` (**không** in engine TTS) |
| `dub` | `tron_nen = true`, không `chi_tron` (đời cũ: chạy TTS rồi mới trộn) | `lồng tiếng + ghép nền` |
| `dub` | còn lại | `lồng tiếng · <engine>` |
| `export` | `format: "ass"` | `xuất phụ đề · ass` (trước đây ghi "ghép nền") |

Không đổi `phase`, không đổi loại job, không đổi payload — nên hàng đợi cũ trong DB vẫn đọc
được, và không có job nào bị xếp lại.

**Ghim:** 5 bài — 4 bài `nhanJob` trong `studio.test.ts` (burn không kèm engine TTS; job đời cũ
nói rõ làm cả hai việc; job lồng tiếng thường giữ nhãn cũ; `export` là *xuất phụ đề*, có và
không có `format`) và 1 bài trong `test_dub_handler.py` ghim `phase == "dub:<ENGINE_TTS>"` cho
job `chi_tron` — kèm docstring nêu đúng hai hậu quả nếu ai đó đổi nó.

### Đo cuối

```
pytest (toàn bộ)      1542 passed, 15 deselected   EXIT_PYTEST=0
npm test              286 pass, 0 fail             EXIT_TEST=0
npx tsc --noEmit                                   EXIT_TS=0
```

---

## ERRATA #78 — bản BURN có một VẠCH DỌC giữa hộp phụ đề, bản xem trước trên web thì không

**Phát hiện lúc:** chủ dự án gửi hai ảnh cạnh nhau — ảnh hộp trong hộp thoại "Chỉnh phụ đề
hiển thị" (sạch) và ảnh phóng to hộp trong video đã burn (có một **vạch dọc** chia đôi hộp) —
kèm câu *"bản web vs bản burn"*.

**Đo được** trên chính `dub-63.mp4` (khung 1080×1920, câu "Là một người làm nghề thuật" ở
giây 0,5; style `co 160`, `cao_hop 180`, `vien 20`, hộp đen đặc):

```
hộp: x 137→941 (805 px), y 1337→1516 (180 px)
cột không đen suốt cả chiều cao hộp: 539, 540
màu tại đó: (83,76,71) / (84,77,72)  — nền video (216,208,192) lọt qua ~45 %
```

Tức hộp **không** liền: đúng hai cột ở giữa chỉ được phủ một nửa, và vì hộp đen trên nền sáng
nên mắt thấy thành một đường kẻ.

**Nguyên nhân:** hộp rộng **806** > trần `PlayResX/2 = 540` (libass THU NHỎ một hình vẽ vượt
nửa bề ngang script — đo từ trước, xem ERRATA #72), nên hộp bị chia **hai mảnh**, mỗi mảnh
rộng **403 (số LẺ)**. Tâm mỗi mảnh vì thế là `.5`, mà bản cũ ghi `\pos` bằng `int(round(cx))`,
và `round` của Python làm tròn **chẵn**. Đọc thẳng tệp `.ass` của bản cũ (in ra ở đây nguyên
văn, không suy luận):

```
mảnh 1: {\an2\pos(338,...)} m 0 0 l 403 0 403 -180 0 -180   → mép 136,5 … 539,5
mảnh 2: {\an2\pos(742,...)} m 0 0 l 403 0 403 -180 0 -180   → mép 540,5 … 943,5
```

Hai mép lẽ ra phải trùng một đường thì lại **hở đúng 1 px** — nền video lọt qua khe đó, và trên
ảnh burn nó thành hai cột nửa phủ. Rasteriser của libass là subpixel, nên `int(round())` chính
là thứ đẩy mép ra khỏi toạ độ nguyên.

**Sửa** (`domain/subtitle_format.py`): biên ngang của từng mảnh tính bằng **SỐ NGUYÊN, cộng
dồn** (`canh_ngang[k] = canh_ngang[k-1] + bề rộng mảnh`), phần lệch ±1 px của hai lần làm tròn
dồn vào mảnh CUỐI; và `\pos` ghi bằng `_so_ass` — giữ `.5` (`\pos(338.5,…)` /
`\pos(741.5,…)`) thay vì ép về `int`. Hình học hộp KHÔNG đổi (đo lại sau khi sửa: vẫn
`x 137→941`, `y 1337→1516`).

**Đo lại sau khi sửa** (cùng khung, cùng câu, job #204 — 39 s, vẫn không chạy lại TTS):

```
hộp: x 137→941 (805 px), y 1337→1516 (180 px)          ← y hệt trước
cột không đen trong hộp: KHÔNG CÓ
màu tại 538…542: (0,0,2) (0,0,2) (0,0,2) (0,0,2) (0,0,2)
```

**Ghim 2 bài** trong `tests/test_phu_de_style.py`:

1. `test_mep_ngang_cua_manh_hop_la_SO_NGUYEN_va_KHOP_NHAU` — mọi mép là số nguyên và hai mảnh
   kề CHUNG đúng một mép. Đây là điều kiện để không cột nào bị phủ nửa.
2. `test_BURN_THAT_khong_co_cot_nao_ho_giua_hai_manh_hop` — **burn thật** một khung bằng ffmpeg
   rồi đếm cột. Bài này là bài duy nhất bắt được lỗi, vì lỗi nằm ở pixel chứ không ở chuỗi
   `.ass`: một test chỉ đọc số trong tệp sẽ xanh trong khi video vẫn có vạch.

Đã kiểm hai bài này **ĐỎ trên bản cũ** (đo được đúng thông báo: *"mép trái 136.5 KHÔNG nguyên"*
và *"hộp 806 px có 2 cột bị nền lọt qua, ví dụ [(539, (103, 101, 97)), …]"*), rồi **XANH sau khi
sửa**. Đo thêm 5 kiểu hộp khác (hộp hẹp 1 mảnh, hộp cao 960 chia 4 hàng, hộp vừa rộng vừa cao,
hộp đục 50 %): không kiểu nào còn cột/hàng hở, và hộp đục 50 % cũng không bị đậm gấp đôi ở
đường nối (vì các mảnh KHÔNG chồng nhau — chúng chia nhau đúng một mép nguyên).

### Đo cuối

```
pytest (toàn bộ)      1544 passed, 15 deselected   EXIT_PYTEST=0
npm test              286 pass, 0 fail             EXIT_TEST=0   (không đổi frontend)
```

---

## ERRATA #79 — chữ trong hộp LỆCH TÂM DỌC, và khi câu xuống dòng thì dính mép trên

**Phát hiện lúc:** chủ dự án: *"tôi thấy cái chữ trong box cứ bị lệch tâm trên và dưới kiểu gì
ý. khi có word wrap thì chữ sát với viền luôn"*, kèm hai ảnh burn.

**Đo được** (khung 1080×1920, style `co 160`, `cao_hop 180`, hộp đen đặc; lề đo giữa MÉP HỘP
và NÉT CHỮ). Số dưới đây lấy từ một **burn tổng hợp trên nền phẳng** cùng style/cùng hộp —
nền video thật làm ngưỡng "pixel chữ" nhiễu vài px, nên nền phẳng là phép đo sạch:

```
một dòng "Là một người làm nghề thuật" : lề trên 38 · lề dưới 77   → lệch 39
hai dòng (câu 18, wrap)                : lề trên  0 · lề dưới 33   → lệch 33, dòng đầu DÍNH mép
```

**Nguyên nhân:** bản cũ neo `\an2` (ĐÁY khối chữ của libass) rồi tự dịch lên
`(cao_hop − cao_chữ)/2`, trong đó `cao_chữ` là **chiều cao NÉT** đo bằng Pillow. Hai con số đó
là hai thứ khác nhau:

* `\an2` neo vào ĐÁY HỘP DÒNG của libass, nằm dưới đáy nét chữ đúng phần descender (đo được
  14 px với Archivo);
* `cao_chữ` của Pillow chỉ là nét, và chỉ cộng thêm `(n−1)·co` cho các dòng sau.

Sai số vì thế **nhân theo số dòng** — càng nhiều dòng, chữ càng bị đẩy lên, tới mức dòng đầu
chạm mép hộp (lề trên 0).

**Sửa:** để CHÍNH LIBASS căn, không tự đoán: `\an5` (neo GIỮA-DỌC) đặt tại tâm hộp
`y − cao_dong/2`. Không còn con số chiều cao nào của mình chen vào giữa, nên không còn phụ
thuộc số dòng hay font. Chỉ dùng `\an5` khi CÓ hộp: không hộp thì đáy khối chữ phải neo đúng
`\pos.y` (`offset_doc` tính theo đáy), đổi ở đó sẽ đẩy mọi phụ đề lên nửa khối chữ.

**Đo lại cùng phép đo** (burn tổng hợp, nền phẳng) và trên **bản burn thật** (job #206, 39 s,
vẫn không chạy lại TTS):

```
tổng hợp, một dòng : 57 / 58   → lệch 1     (trước: 38/77)
tổng hợp, hai dòng : 14 / 14   → lệch 0     (trước:  0/33, dòng đầu dính mép)
dub-63.mp4, một dòng: 67 / 58  → lệch 9     (nền video làm ngưỡng nhiễu; xem dưới)
dub-63.mp4, hai dòng: 14 / 14  → lệch 0     ← đúng ca chủ dự án gửi ảnh
```

9 px ở dòng cuối cùng là do NÉT của chính câu đó: "người", "nghề" có `g` thò xuống (descender),
nên nét không đối xứng quanh khối chữ — và nền video sáng ở đó làm phép đếm pixel chữ bắt thêm
vài hàng. Bản xem trước trên web cũng căn theo khối dòng (`justifyContent: center`) chứ không
theo nét, nên hai bên **cùng một cách căn** — đó mới là điều cần khớp.

**Kèm một lỗi im lặng phát hiện trong lúc đo:** phép đo chữ chỉ tra `/usr/share/fonts/...`
(đường của image Linux). Chạy API ngay trên Windows thì `PIL.ImageFont` không mở được file, phép
đo trả `0`, và hộp vector **BIẾN MẤT** — dù `rong_hop = 0` nghĩa là "bám chữ", không phải
"tắt hộp". Đo được trên máy này: `_do_khoi_chu('A', 'Archivo', 160, 960, True)` → `(0, 0, 0,
[])` và `.ass` không có `\p1` nào. Nay `_duong_font` thử đường HỆ THỐNG trước, rồi tới bản copy
trong repo (`backend/app/assets/fonts/`). Trong container không có gì đổi (đường hệ thống
thắng); trên Windows hộp hiện lại đúng.

**Ghim 3 bài** trong `test_phu_de_style.py`:

1. `test_text_dung_AN5_dat_o_TAM_hop` — sự kiện CHỮ phải neo `\an5` và `pos.y` phải bằng tâm
   hộp. Vế nhanh, chạy mọi máy, và chính là chỗ sinh ra lỗi.
2. `test_KHONG_CO_HOP_thi_van_neo_AN2_o_day` — vế chống sửa quá tay: không hộp thì vẫn `\an2`.
3. `test_BURN_THAT_chu_namGIUA_hop_ca_khi_XUONG_DONG` — burn thật rồi đo lề trên/dưới với câu
   một dòng VÀ câu hai dòng, đòi lệch ≤ 2 px. Bài này **tự bỏ qua kèm lý do** khi libass không
   dùng đúng file font (đo được trên Windows không cài Archivo: nét 165 px so với 89 px của
   Pillow) — thà nói rõ "không đo được ở đây" còn hơn hạ ngưỡng cho vừa, vì ngưỡng lỏng sẽ
   không bắt được lỗi thật (bản cũ lệch 29–33 px).

Hai bài `test_KHONG_DO_DUOC_chu_thi_khong_ve_hop` (backend) và `test_khong_co_font_thi_tra_
MOT_dong_chu_khong_bo_cau` (API) phải sửa theo: chúng mô phỏng "máy không có font" bằng cách làm
rỗng `_FONT_CHO_DUONG`, mà nay còn đường dự phòng trong repo — nên chúng chuyển sang chặn
`_duong_font`. Không sửa thì hai bài đó **kiểm nhầm điều chúng tuyên bố**.

### Đo cuối

```
pytest (toàn bộ)      1546 passed, 1 skipped, 15 deselected   EXIT_PYTEST=0
npm test              286 pass, 0 fail                        EXIT_TEST=0   (không đổi frontend)
```

(Bài bị skip là bài burn-thật ở trên, kèm lý do: máy này không cài font `Archivo` cho
fontconfig. Trong image API — nơi font đã cài — bài đó chạy; phép đo tương đương đã chạy tay
trong container và cho đúng `67/58` và `14/14`.)

---

## ERRATA #80 — "Cài đặt model": chọn model ĐANG DÙNG và model DỰ PHÒNG cho từng việc

**Yêu cầu của chủ dự án:** *"làm thêm 1 lệnh trong ctrl K để mở panel cài đặt model cho từng
task. Làm 2 mục là model mặc định và model sử dụng. Model mặc định được dùng khi model sử dụng
ko thể hoạt động. … với cả phần dịch thì làm thêm mục chọn dịch dùng mt hoặc llm"*.

**Sự thật về danh mục hiện có** (đọc `registry.json`, không chép từ ảnh mockup): sản phẩm có
**3 loại engine** — `asr` (5), `ocr` (1), `mt` (5) — cộng hai thứ KHÔNG phải engine trong
registry: TTS (`vieneu-v3-turbo`) và tách giọng (`htdemucs`), và bước burn có hai bộ mã hoá
thật (`h264_nvenc` / `libx264`). Bảng cài đặt vì thế có **sáu việc**, dựng từ dữ liệu thật:

| việc | ứng viên | ghi chú |
|---|---|---|
| OCR | `rapidocr` | một ứng viên ⇒ `locked` |
| ASR | 5 engine Faster-Whisper/SenseVoice | |
| Dịch | 5 engine, chia hai NHÓM | nhóm = `runtime`: `inprocess` → MT, `ollama`/`http` → LLM |
| TTS | `vieneu-v3-turbo` | một ứng viên ⇒ `locked` |
| Tách giọng | `htdemucs` | một ứng viên ⇒ `locked` |
| Burn phụ đề | `h264_nvenc`, `libx264` | việc duy nhất mà "dự phòng" đã là hành vi thật |

**KHÔNG bịa model.** Ảnh mockup ghi *PaddleOCR, Tesseract, NLLB-200, Google Translate, Gemini
2.5 Flash, Edge TTS, XTTS v2, UVR MDX-Net, FFmpeg*. Không cái nào trong số đó chạy trong sản
phẩm này, nên đưa chúng vào bảng là bán một lựa chọn không tồn tại — đúng loại "khai báo nói
dối" mà repo xoá. Bảng vẽ ra đúng thứ đang chạy được, và việc chỉ có một model thì hiện
**"chỉ có một model"** thay vì một ô dự phòng rỗng (ô chỉ có một lựa chọn là ô nói dối rằng có
thể chọn).

**Luật, viết thành hàm THUẦN** (`domain/model_settings.py::chon`):

```
model đang dùng chạy được            → dùng nó            ("dang-dung")
không chạy được, dự phòng chạy được   → dùng dự phòng      ("du-phong")
cả hai không chạy được               → None               ("khong-co")
```

`san_sang` (tập id chạy được) là ĐO ĐƯỢC, không phải suy đoán: engine Ollama phải có model
trong `/api/tags`, engine `http` phải có endpoint sống (`main._mark_availability`), còn
`h264_nvenc` phải qua phép dò 320×240 của chính `tach_nen.co_nvenc()`. `libx264` luôn chạy
được nên bước burn luôn có đường cùng.

**Đo được — bảng này KHÔNG phải đồ trang trí.** Ba dây nối thật, mỗi dây một bài ghim:

1. **Job `asr`**: client gửi engine không chạy được ⇒ job mang engine dự phòng
   (`job.engine == "asr-a"`, `phase == "asr:asr-a"`); không có dự phòng ⇒ **409** kèm câu chỉ
   dẫn, và **không job nào được xếp**.
2. **Job `dịch`**: cùng luật, và khi đổi sang engine dự phòng thì `spec` phải được đọc LẠI —
   `prompt_version`, `glossary_prompt` là dữ liệu của CHÍNH engine đó; dùng spec cũ là ghi một
   hàng `translations` mang engine dự phòng nhưng cấu hình của engine đã chọn.
3. **Bước burn**: `DubHandler` hỏi `chon_burn(repos, co_gpu=tach_nen.co_nvenc())` rồi truyền
   `ma_hoa_id` xuống `tach_nen.remux`; máy không NVENC mà đặt `h264_nvenc` ⇒ chạy `libx264` và
   **ghi ra log** là đang dùng dự phòng.

**Một chỗ phải tách tầng khi làm:** bản đầu tôi để `giai_quyet`/`san_sang`/`mac_dinh_cua` trong
`domain/model_settings.py`, và `tests/test_layer_boundary.py` đỏ ngay:
*`domain/ phải là logic thuần — model_settings.py: import app.registry`*. Đúng. Luật thuần ở
lại domain; phần biết về DANH MỤC chuyển sang `app/chon_model.py` (cùng tầng `app/registry.py`).

**Ghim:** 21 bài backend (`tests/test_model_settings.py`) + 9 bài frontend
(`CaiDatModel.test.tsx`) + 1 bài trong `Studio.test.tsx`. Bài quan trọng nhất là
`test_noi_day_job_ASR_dung_model_DU_PHONG` — không có nó thì bảng vẫn "lưu được" mà không đổi
gì, đúng kiểu khai báo chết.

### Đo cuối

```
pytest (toàn bộ)      1567 passed, 1 skipped, 15 deselected   EXIT_PYTEST=0
npm test              296 pass, 0 fail                        EXIT_TEST=0
npx tsc --noEmit                                              EXIT_TS=0
```

---

## ERRATA #81 — panel "Cài đặt model": trang trí lại, và bốn chỗ THỪA đã bị bỏ

**Yêu cầu:** *"trang trí lại một chút cái panel này cái nhỉ? Và có cái nào bị thừa ko"*.

### Bốn chỗ thừa (mỗi chỗ là một câu lặp lại hoặc một khai báo không ai đọc)

1. **`note` — trường chết VÀ nói sai.** Nó đi từ `domain` → route → `types.ts` → panel, nhưng
   giao diện chỉ nhét vào `title=` (tooltip của một `<span>` — gần như không ai thấy). Tệ hơn,
   nội dung của nó là *"Tự chọn theo máy: có NVENC thì dùng GPU"* — câu đó ĐÚNG trước khi có
   bảng cài đặt, và nay SAI: burn là một lựa chọn tường minh. Đã xoá khỏi cả bốn tầng.
2. **Tiêu đề cột lặp 12 lần.** Bản đầu để "Model sử dụng" / "Model mặc định (dự phòng)" bên
   trong TỪNG ô, tức sáu việc × hai nhãn = mười hai lần cùng một câu. Nay còn MỘT hàng tiêu đề
   dính trên cùng (`sticky top-0`) cho cả bảng.
3. **Nhãn nhóm lặp 4 lần.** Ở bước giữa, mỗi nhóm lại có thêm một hàng tiêu đề cột riêng. Nay
   nhãn nhóm là một dòng khắc + đường kẻ, không kèm lại tiêu đề cột.
4. **"đang chạy: X" lặp lại chính ô chọn.** Sáu dòng, dòng nào cũng in "đang chạy: <model vừa
   chọn ở trên>" — một câu không nói thêm gì. Nay nó CHỈ hiện khi model đang chạy KHÁC model
   đang chọn (`du-phong`) hoặc khi không còn đường nào chạy (`khong-co`), kèm một chấm amber.

### Ngôn ngữ thị giác: lấy từ chính ứng dụng

Ứng dụng này là "phòng thu biên tập": graphite ấm, MỘT màu nhấn amber, `Archivo` +
`IBM Plex Mono`, bán kính 2 px, đường kẻ 1 px, nhãn chữ hoa giãn chữ (`label-engraved`), số
canh cột (`num`). Bản trang trí lại vẽ bằng ĐÚNG sáu token đó — không bo tròn lớn, không bóng
đổ, không thẻ (card), không font mới, không màu mới. Cụ thể:

* mỗi việc là MỘT DÒNG của bảng đặc tả: số thứ tự mono `01…06`, tên việc, hai ô chọn;
* nhóm việc là nhãn khắc + đường kẻ chạy hết bề ngang, KHÔNG phải hộp có viền;
* vệt amber 2 px ở mép trên (cùng dấu hiệu "bề mặt đang mở" của panel Hàng đợi);
* nút chính tô amber đặc (`bg-signal`), nút phụ viền mảnh; `active:translate-y-px` cho phản hồi
  chạm; chuyển động chỉ `transition-colors/transform 150 ms` — không thư viện animation (dự án
  không có `framer-motion`, và bảng cài đặt không cần);
* trạng thái nạp là **skeleton đúng hình bảng** (3 nhóm × 2 dòng), không phải vòng xoay;
* `Esc` đóng bảng — trước đó panel này là hộp thoại DUY NHẤT bắt người dùng đi tìm chuột.

### Một lỗi do CHÍNH việc chụp ảnh bắt được, không phải do test

Lượt đầu của bản trang trí lại làm **cả trang thành "Trang này không tải được"**: tôi gom phần
nhóm dòng vào một `useMemo` đặt **sau** `if (!open) return null`. Số hook của lần render "đóng"
khác lần "mở" ⇒ React ném *"Rendered more hooks than during the previous render"* và error
boundary của app che cả trang. Đúng lỗi repo này đã ghi một lần (`ERRATA` cũ về Rules of Hooks).

Đo được: `npm test` vẫn XANH 12/12 ở tệp panel (mọi bài đều `open` ngay từ đầu, nên số hook
không đổi), chỉ bài của `Studio` (mở panel TỪ trạng thái đóng) mới lộ. Và vì nó ném ở lần
render thứ hai, cách duy nhất thấy chắc chắn là **mở panel thật trong Chrome**: ảnh chụp
1424×1005 qua CDP cho ra đúng màn hình lỗi. Nay phép gom nhóm là vòng lặp thường (sáu dòng thì
không cần nhớ), kèm ghi chú tại chỗ nói rõ vì sao KHÔNG được dùng hook ở đó.

### Kiểm bằng ảnh thật, không chỉ bằng số

Chụp bằng Chrome headless (CDP, `Runtime.evaluate` bấm nút "Lệnh" rồi lệnh "Cài đặt model"),
hai trạng thái:

* **bình thường** (mọi engine chạy được): sáu dòng, không dòng nào có câu "đang chạy" — đúng
  luật bỏ chỗ thừa;
* **có dự phòng** (đặt `dich.used = deepseek-web` — gateway đang tắt — `fallback = qwen2.5-7b`):
  dòng Dịch hiện chấm amber + `đang chạy bằng model dự phòng: qwen2.5-7b` dưới dạng mono, và
  `hieu_luc` của backend trả đúng `qwen2.5-7b (du-phong)`. Cài đặt được khôi phục về mặc định
  sau khi chụp.

**Ghim:** 3 bài mới trong `CaiDatModel.test.tsx` — (1) dòng "đang chạy" KHÔNG được vẽ khi nó
chỉ lặp lại model đang chọn; (2) `Esc` đóng bảng; (3) model đang lưu NGOÀI nhóm đang chọn vẫn
hiện trong ô chọn (nếu lọc thẳng tay thì `<select>` của React hiển thị ô RỖNG và người dùng mất
lựa chọn cũ mà không hiểu vì sao).

### Đo cuối

```
pytest (toàn bộ)      1567 passed, 1 skipped, 15 deselected   EXIT_PYTEST=0
npm test              299 pass, 0 fail                        EXIT_TEST=0
npx tsc --noEmit                                              EXIT_TS=0
```

---

## ERRATA #82 — dropdown/radio tự vẽ, nhóm MT/LLM lọc THẬT, và tên model dưới tên việc

**Yêu cầu:** *"sửa lại style của dropdown và radio button. Và ngoài ra khi chọn radio button
của cái llm hoặc mt thì phải thay đổi danh sách dropdown. MT thì hiện opus mt thôi. Và ngoài ra
khi lưu setting model xong thì phần header của task phải hiện các tên model tương ứng ở dưới."*

### 1. Dropdown và radio: viết tay, vì `<select>` trần không style được

Danh sách xổ xuống của `<select>` do HỆ ĐIỀU HÀNH vẽ — `background`, bo góc, cỡ chữ, màu hover
đều nằm ngoài tầm CSS, nên trên Windows nó ra một hộp xám bo tròn của Chrome, lạc hẳn khỏi bảng
graphite 2 px. Nay `components/studio/ChonModel.tsx` có hai điều khiển tự vẽ:

* `<ChonModel>` — nút mở + `role="listbox"` + `role="option"`, vẽ bằng token của app (nền
  `panel-2`, viền `rule`, dòng đang chọn có `◆` amber + `signal-soft`, model chưa chạy được ghi
  `chưa sẵn sàng` màu `fault`). Danh sách nằm trong **PORTAL**: khung bảng có `overflow-y-auto`,
  một `absolute` bên trong sẽ bị CẮT ở đáy khung — đúng lúc chọn việc cuối cùng thì danh sách cụt.
  Tự lo phần `<select>` cho sẵn: Escape đóng danh sách (không đóng cả bảng), bấm ra ngoài đóng,
  `aria-haspopup`/`aria-expanded`/`aria-selected`.
* `<ChonNhom>` — thanh gạt MT/LLM hai ô, vẫn là `<input type="radio">` THẬT (ẩn bằng `sr-only`)
  chứ không phải `<button>` đóng giả: `radiogroup` + radio mới cho trình đọc màn hình biết "một
  trong hai", và phím mũi tên mới đi được giữa hai lựa chọn.

Phụ: hai điều khiển là NÚT + `click` — và đó cũng là đường mà harness test bấm được
(`fireEvent.change` trên ô điều khiển không chạy handler React dưới harness này, xem
`PhuDeStyle.test.tsx`).

### 2. Đổi nhóm phải đổi DANH SÁCH — và đổi cả GIÁ TRỊ

**Lỗi thật, đo được:** đang ở nhóm MT mà danh sách vẫn có `hy-mt-1.5-7b` — một engine LLM. Nguyên
nhân: bản trước, để ô chọn không bị rỗng, tôi CHÈN LẠI model đang lưu vào danh sách đã lọc. Luật
đó sai. Nay:

* danh sách CHỈ còn engine của nhóm đang chọn — đo bằng ảnh chụp thật: MT ⇒ đúng một dòng
  `OPUS-MT (Marian)`;
* nếu model đang chọn không thuộc nhóm mới thì nó được **đổi sang ứng viên đầu của nhóm**
  (LLM ⇒ `Qwen2.5-3B (Ollama)`), và bản nháp được đánh dấu đổi — footer hiện `1 việc chưa lưu`,
  bấm Lưu là ghi thật;
* **nhóm MỞ ĐẦU lấy theo NHÓM CỦA MODEL ĐANG CHẠY**, không theo `nhom_dich` đã lưu. ĐO ĐƯỢC trên
  máy này: `nhom_dich = "mt"` nhưng model đang chạy là `hy-mt-1.5-7b` (LLM) — mở bảng theo nhóm
  cũ thì ô chọn TRỐNG ngay từ giây đầu, vì nhóm MT không chứa model đó.

### 3. Tên model dưới tên việc

Mỗi dòng giờ có: số thứ tự mono, **tên việc**, và ngay dưới nó **tên model đang dùng** (kèm
`· dự phòng: …` nếu có) — cột chọn bên phải bị cắt bằng dấu ba chấm khi tên dài, nên đây là chỗ
đọc được tên đầy đủ. Đo trên ảnh chụp: `ASR / Faster-Whisper large-v3 (chính xác hơn turbo)`,
`Dịch / HY-MT1.5-7B (Hunyuan-MT)`, `Burn phụ đề / GPU NVENC (nhanh gấp đôi, cần driver NVIDIA)`.

### Kiểm

`npm test` 301 bài (panel 14 bài, trong đó 3 bài mới: danh sách MT chỉ có opus-mt; bấm LLM đổi
danh sách NGAY và đổi giá trị; nhóm mở đầu theo model đang chạy). Ảnh chụp Chrome thật ở
1424×1005 xác nhận cả ba trạng thái: panel mở, danh sách MT (một dòng OPUS-MT), và sau khi bấm
LLM (giá trị thành Qwen2.5-3B, footer `1 việc chưa lưu`). Không bấm Lưu nên DB không đổi.

### Đo cuối

```
pytest (toàn bộ)      1567 passed, 1 skipped, 15 deselected   EXIT_PYTEST=0
npm test              301 pass, 0 fail                        EXIT_TEST=0
npx tsc --noEmit                                              EXIT_TS=0
```

---

## ERRATA #83 — thanh bước vẫn ghi `ocr+asr`, và một bài test đã CHẾT ÂM THẦM

**Yêu cầu:** *"với header đã đổi tên đâu vẫn hiện ocr+asr kìa (để tên ocr/tên asr), mấy cái task
kia nữa"*.

### 1. Ghi chú của thanh bước giờ là TÊN MODEL

Trước: `ocr+asr` (nhãn NGUỒN CHỮ của bản ghi, không phải engine), `deepseek-web` (id kỹ thuật),
`đã lồng` / `đã ghép` (không nói model nào). Nay, đo bằng cách đọc thẳng DOM của thanh bước trên
ứng dụng đang chạy:

```
["Phiên âm | RapidOCR + Faster-Whisper large-v3",
 "Dịch | DeepSeek web",
 "Duyệt | còn 207 việc",
 "Lồng tiếng | VieNeu v3 Turbo",
 "Ghép nền | htdemucs · GPU NVENC",
 "Xuất | kiểu chữ đã đổi — ghép lại"]
```

Ba quyết định trong đó, mỗi cái đều có lý do đo được:

* **`ocr+asr` được DỊCH thành tên model**, không in nguyên chuỗi: `transcript.engine` là nhãn
  nguồn chữ (`domain/nguon_chu.py`), nên `"ocr+asr"` phải ra `RapidOCR + Faster-Whisper large-v3`.
  Bản ghi chỉ do ASR thì chỉ hiện tên ASR — không gán oan OCR.
* **Bước "Dịch" kể tên engine CỦA BẢN DỊCH ĐANG MỞ**, không phải model vừa đặt trong bảng cài
  đặt: bản dịch #63 viết bởi `deepseek-web` trong khi bảng đang đặt `hy-mt-1.5-7b` — ghi chú mô
  tả BẢN ĐANG XEM, nên nó là "DeepSeek web". Nên `nhanModel` mang HAI loại khoá: `task.id` (model
  đang đặt) và `engine.id` (tên của model đã chạy).
* **"Ghép nền" kể CẢ HAI model** của bước đó (`htdemucs · GPU NVENC`): tách giọng rồi mã hoá lại
  hình.

Tên trong thanh bước được cắt phần giải thích trong ngoặc (`nhanNgan`): nhãn registry là câu giải
thích ("Faster-Whisper large-v3 (chính xác hơn turbo)"), còn thanh bước chỉ rộng ~200 px cho một
bước.

### 2. 🔴 Một bài test đã KHÔNG CHẠY suốt từ lúc được viết, và không ai thấy

Khi thêm bài cho `nhanNgan`, tôi phát hiện `npm test` báo **126** bài trong khi tệp có **133**
`it(`. Truy ra: `frontend/src/lib/studio.test.ts` khai `import { describe, it } from "node:test"`
nhưng ở CUỐI TỆP có một bài viết bằng **`test(...)`** — không import. `test` không tồn tại ⇒
`ReferenceError` ngay lúc NẠP MODULE ⇒ mọi thứ khai báo sau dòng đó (bài "bước Xuất: kiểu chữ đã
đổi…" và toàn bộ khối mới của tôi) **không bao giờ chạy**.

Vì sao không ai thấy, ba lớp chặn cùng lúc:

1. `tsconfig.json` **exclude `src/**/*.test.ts(x)`**, nên `tsc --noEmit` không hề đọc tệp test —
   `test is not defined` (TS2304) lẽ ra bị bắt ngay.
2. `npm test` chạy với `--test-isolation=none`; ở chế độ đó một ngoại lệ lúc nạp tệp bị NUỐT (đo
   được: cùng tệp chạy bằng `node --test` KHÔNG có cờ đó thì báo `✖ … ReferenceError: test is not
   defined`, `fail 1`, exit 1; có cờ thì exit 0, im lặng).
3. Bài đó là bài DUY NHẤT của nó (không nằm trong `describe`), nên không có "suite rỗng" nào để
   mắt nhận ra.

**Sửa:** `test(` → `it(`, và thêm một chặng `npm run test:load` CHẠY TRƯỚC `test`: nạp mọi tệp
test với `--test-name-pattern="__khong_bao_gio_chay__"` (không bài nào chạy) — vẫn đủ để một
ngoại lệ lúc nạp làm sập, mà chỉ tốn **~1 s**:

```
"test:load": "node --import ./test/swc-loader.mjs --test --test-name-pattern=\"__khong_bao_gio_chay__\" \"src/**/*.test.{ts,tsx}\"",
"test": "npm run test:load && node --import ./test/swc-loader.mjs --test --test-isolation=none \"src/**/*.test.{ts,tsx}\""
```

Đo được: `npm run test:load` trên 12 tệp = **1 s**, exit 0; khi tệp còn lỗi thì nó đỏ ngay.

**Bài chết âm thầm đó, khi được chạy lại, ĐÃ XANH** — tức hành vi "kiểu chữ đổi ⇒ nói phải ghép
lại" vẫn đúng; chỉ là từ trước tới nay chưa có gì canh nó.

### Đo cuối

```
pytest (toàn bộ)      1567 passed, 1 skipped, 15 deselected   EXIT_PYTEST=0
npm test              310 pass, 0 fail                        EXIT_TEST=0   (trước: 301 — 8 bài giờ mới chạy được + 1 bài thêm)
npx tsc --noEmit                                              EXIT_TS=0
```

---

## ERRATA #84 — đổi nhãn model sang TÊN NGẮN (danh sách đã được chủ dự án duyệt)

**Yêu cầu:** *"à cái list ở trên tôi duyệt nhá bn đổi vô đi"* — duyệt danh sách ở ERRATA #83.

Nhãn là DỮ LIỆU, nên chỉ sửa hai chỗ; không route nào, không component nào phải biết:

| chỗ | cũ | mới |
|---|---|---|
| `registry.json` (asr) | `Faster-Whisper large-v3 (chính xác hơn turbo)` | `Faster-Whisper large-v3` |
| `registry.json` (ocr) | `RapidOCR (PP-OCRv4, đọc phụ đề cứng)` | `RapidOCR` |
| `registry.json` (mt) | `OPUS-MT (Marian)` | `OPUS-MT` |
| `registry.json` (mt) | `Qwen2.5-3B (Ollama)` / `Qwen2.5-7B (Ollama)` | `Qwen2.5-3B` / `Qwen2.5-7B` |
| `registry.json` (mt) | `HY-MT1.5-7B (Hunyuan-MT)` | `HY-MT1.5-7B` |
| `registry.json` (mt) | `DeepSeek web (whalegate, qua mạng — KHÔNG mặc định)` | `DeepSeek web` |
| `domain/model_settings.py` | `VieNeu v3 Turbo (TTS tiếng Việt)` | `VieNeu v3 Turbo` |
| `domain/model_settings.py` | `htdemucs (Demucs)` | `htdemucs` |
| `domain/model_settings.py` | `GPU NVENC (nhanh gấp đôi, cần driver NVIDIA)` | `h264_nvenc (GPU)` |
| `domain/model_settings.py` | `CPU x264 (chậm hơn, luôn chạy được)` | `libx264 (CPU)` |

Giữ hậu tố `(GPU)` / `(CPU)` cho hai bộ mã hoá burn: đúng tên bộ mã hoá nhưng vẫn phân biệt
được cái nào cần driver NVIDIA — và `nhanNgan` cắt đúng phần đó khi hiện trên thanh bước
(`htdemucs · h264_nvenc`).

Đo trên ứng dụng đang chạy sau khi rebuild — đọc thẳng chữ trong DOM:

```
panel:      RapidOCR · Faster-Whisper large-v3 · HY-MT1.5-7B · VieNeu v3 Turbo ·
            htdemucs · h264_nvenc (GPU)        ← không còn chỗ nào tràn
thanh bước: RapidOCR + Faster-Whisper large-v3 · DeepSeek web · VieNeu v3 Turbo ·
            htdemucs · h264_nvenc
```

**Những gì KHÔNG đổi:** `id` của engine (job, `phase`, bảng `translations` vẫn dùng id — đổi id
là đổi khoá dữ liệu, không phải đổi nhãn), `model_ref`, `vram_mb`, `capabilities`. Nhãn của
`chimera.candidates` cũng giữ nguyên: chúng mô tả BIẾN THỂ PROMPT ("Qwen-3B nhiệt độ 0,1"), một
khái niệm khác, và không hiện trong bảng cài đặt model.

**Ghim:** không thêm bài mới. 40 bài sẵn có của `test_model_settings.py` +
`test_registry*.py` xanh sau khi đổi (chúng bám `id`, không bám nhãn — đúng như thiết kế), và
`nhanNgan` đã có bài kiểm việc cắt ngoặc với đúng dạng nhãn mới (`h264_nvenc (GPU)`).

### Đo cuối

```
pytest (toàn bộ)      1567 passed, 1 skipped, 15 deselected   EXIT_PYTEST=0
npm test              310 pass, 0 fail                        EXIT_TEST=0
npx tsc --noEmit                                              EXIT_TS=0
```


