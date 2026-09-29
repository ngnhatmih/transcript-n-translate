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
   `backend/`) và **dựa vào DB của repo đang RỖNG** (`data/app.db`).
2. Nhánh **200** của route chi tiết nằm ở một backend **THỨ HAI, cổng 8621**, có DB gieo riêng
   (`PHUDE_DB`/`PHUDE_DATA`/`PHUDE_PORT`, `contract.test.ts:573-587,700`).

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

Lượt đo của tài liệu này (8620/8621 trống trước khi chạy):

```
ℹ tests 308   ℹ suites 30   ℹ pass 306   ℹ fail 2   ℹ cancelled 0
ℹ skipped 0   ℹ todo 0      ℹ duration_ms 32295.5656
EXIT=1   ·   wall 32,6 s
0 dòng "asynchronous activity" ; [guard thoat] 10/10 global da ve nguyen trang
```

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
cache npm, nên đừng chạy lại khi `node_modules/` đã có. `package-lock.json` đang cũ (nó mô tả cây
Vite cũ), vì vậy `npm ci` sẽ fail cho tới khi có người `npm install` lại ở môi trường bình thường.

Cấu hình frontend: `frontend/rollup.config.mjs` (build) · `frontend/dev-server.mjs` (cổng, proxy,
watch) · `frontend/tsconfig.json` (kiểu) · `frontend/test/swc-loader.mjs` (loader test) · token
thiết kế ở `frontend/src/styles/tokens.css` (giá trị chép từ
`docs/superpowers/specs/2026-09-25-phu-de-lab-ui-design.md` §2).

Chi tiết backend: `backend/README.md`.

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

### CHƯA LÀM (có chủ ý)

| Chưa làm | Ghi chú |
|---|---|
| **Bảng eval §4.6/§4.7** | ⚠️ **NGOÀI PHẠM VI THEO QUYẾT ĐỊNH CỦA NGƯỜI DÙNG** — giai đoạn này chỉ làm **bốn màn** (`frontend/e2e/TIEU-CHI-12.md:30`). Tiêu chí §12 số 7 giữ nguyên dòng, **không** xoá. |
| **Chimera §4.5** | chưa làm (cùng quyết định trên). |
| **Layout điện thoại** | chưa làm. |
| **Sáng/tối & đổi theme** | chưa làm. |
| **Kéo-thả sắp xếp cột** | chưa làm. |
| **"Thuật ngữ cấm" của spec §8 (QA tất định)** | **CHƯA LÀM** và đây là chỗ ghi nhận chính thức; cần một quyết định về mô hình dữ liệu trước (`backend/README.md:209-217`). |

### CHƯA BIẾT / CHƯA ĐO (trung thực)

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

- **`DEFAULT_MAX_CHARS` chưa đo** — xem ở trên (`backend/README.md:192-198`).
- **Chất lượng dịch chưa đánh giá** — xem ở trên (`backend/README.md:199-205`).
- **`retry_job` không xoá `cancel_requested`** — `backend/app/adapters/persist/sqlite_repos.py:525-536`
  chỉ `UPDATE jobs SET state=?, attempts=attempts+1, finished_at=NULL, error=NULL, progress=0`, **không
  đụng** cột `cancel_requested`; trong khi `backend/app/worker.py:215-221` (`_run_one`) **huỷ job ở
  ranh giới nếu cờ còn**. ⇒ job đã xin huỷ → `failed` → bấm **chạy lại** có thể bị `cancelled` ở
  lượt mới. **Có TRƯỚC D2** (ERRATA **#46 mục 9**). Đây là nợ **`backend/`**: task frontend **không**
  được chạm vào, nên ghi ra chứ không sửa.
- **`N-9` — route export GHI TỆP trên một `GET`** (nợ Giai đoạn 2, **CHƯA đóng**, *chờ người dùng quyết* —
  design spec §7 dòng 111 và §9 dòng 135). Mã vẫn ghi tệp: `backend/app/api/routes_translations.py:282`
  (`@export_router.get("/{translation_id}")`) → `:330` `_materialise(...)` → `:354` `out_dir.mkdir(...)`
  → `:359-360` `target.open("w")` + `write`. ⚠️ **ĐÍNH CHÍNH một lời khai SAI của phiên chính:** ở vòng
  Task 13 tôi đã ra lệnh *"đừng ghi nợ này là còn mở"* vì ánh xạ sai `N-9` → `M-3`. Cái **đã** đóng ở
  Giai đoạn 2 là **`containment`** (`resolve_within`, `:355-358`, có bài ghim trong
  `backend/tests/test_api_export_by_translation.py`), **không phải** gỡ side effect. ⇒ Mục này **phải**
  nằm trong danh sách còn mở (xem ERRATA **#48** mục 1).

