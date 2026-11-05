# QUY TẮC PHỤ ĐỀ — bản xem trước trên web và bản burn vào video

Tài liệu này là **hợp đồng**. Nó tồn tại vì đã có 6 lần "vẫn lệch / vẫn tràn" liên tiếp, mỗi
lần sửa một chỗ khác nhau. Đọc mục **Bẫy** trước khi sửa bất cứ dòng nào trong
`subtitle_format.py` hoặc `PhuDeStyle.tsx`.

## 1. Một nguồn sự thật

| Việc | Nơi quyết định | Không được làm |
|---|---|---|
| Bẻ dòng, đo bề rộng/chiều cao khối chữ | `backend/app/domain/subtitle_format.py::khoi_chu` (chỉ một hàm) | Không tự bẻ dòng ở frontend bằng `canvas` khi đã gọi được API (chỉ dùng khi API hỏng) |
| Cỡ chữ, viền, lề theo khung video | `to_ass` (khối `khung`) và `khoi_chu` (cùng một công thức) | Không tính riêng ở frontend rồi để lệch |
| Bề rộng/chiều cao hộp | `to_ass`: `max(rong_hop, rong_chữ + 2·viền)` | Không dùng `fit-content` + `maxWidth` (xem Bẫy 1) |
| Vị trí đáy | `pos_y = round(ry × (1 − offset_doc))` | Không bỏ qua `offset_doc` (Bẫy 4) |
| Kiểu chữ | `style` (localStorage của giao diện, gửi kèm mọi lời gọi) | Không để đường burn dùng mặc định khi người dùng đã đặt |

Giao diện gọi `POST /api/subtitles/lines` (`routes_subtitles.py`) để lấy `lines/rong/cao` —
đúng hàm mà bản burn dùng. Đó là lý do hai bên không thể bẻ dòng khác nhau nữa.

## 2. Hằng số — đổi một bên là lệch cả hai

| Tên | Giá trị | Nghĩa | Nguồn đo |
|---|---|---|---|
| `tiLe` | `min(videoW/1920, videoH/1080)` | quy đổi hệ thiết kế → hệ video | khung dọc 1080×1920 → 0,5625 |
| `_TI_LE_CHU` / `TI_LE_CHU_LIBASS` | **0,637** | Pillow/CSS px → px libass vẽ | burn nền xám: 87/139, 113/180, 175/277 |
| `_TI_LE_CHU_DAM` | **1,065** | thêm khi `dam = true` | libass vẽ 428 px, Pillow đo 402 px |
| bước dòng libass | **1,0 × `co`** | đỉnh dòng cách nhau đúng một cỡ chữ | 3 dòng ở 1366 / 1417 / 1468 với `co = 51` |
| bề ngang bẻ dòng | `videoW − 2·lề` | `rong_kha_dung` | lề = `round(60 × tiLe)` = 34 → 1012 px |
| neo | `\an2` (đáy-giữa) cho cả chữ và hộp | | |

Hai hằng số 0,637 và 1,065 là **số đo**, không phải toán học. Đổi file font thì phải đo lại.

## 3. Công thức (hệ pixel video = hệ `PlayRes`)

```
co_libass  = round(style.co × tiLe)              # Fontsize trong .ass
co_ve      = co_libass × 0,637                   # font-size để TRÌNH DUYỆT vẽ
bước_dòng  = co_libass                           # line-height của preview
viền       = round(style.vien × tiLe)            # đệm hộp, px video
lề         = round(60 × tiLe)                    # rong_kha_dung = videoW − 2·lề
khối_chữ   = nét_một_dòng + (số_dòng − 1) × bước_dòng
hộp_ngang  = max(rong_hop, rộng_dòng_dài_nhất + 2·viền)   # kẹp ≤ videoW
hộp_cao    = max(cao_hop, khối_chữ + 2·viền)
đáy_hộp    = round(videoH × (1 − offset_doc))    # offset = "Cách đáy"
```

Preview dựng **trong hệ pixel video** (khung `width: videoW px`) rồi thu bằng
`transform: scale(hop.rong / videoW)`. Mọi số ở trên dùng thẳng, không nhân tỉ lệ lần hai —
trừ `co_ve`, đó là chỗ duy nhất phải quy đổi.

## 4. Đường ống

```
style (localStorage)  ──►  /api/subtitles/lines ──►  lines + rong + cao
                                   │
video thật (videoW×videoH) ────────┴──►  preview: khung videoW px + scale()
                                          burn:    .ass + ffmpeg ass= filter
```

Burn: `DubHandler._tron_va_remux` → **lọc theo lớp** (`mot_dong_moi_cap`, ưu tiên lớp 1) →
`xep_hang_trong_lop` (đoạn sau đợi đoạn trước) → `export.render("ass", …, khung=…, style=…)`
→ ffmpeg `-vf ass=…`.

## 5. Checklist kiểm (chạy trước khi nói "xong")

1. `pytest backend/tests -q` → xanh.
2. `npm test` trong `frontend/` → xanh; `npx tsc --noEmit` → 0.
3. **Đo thật, không đoán.** Gọi `POST /api/subtitles/lines` với đúng style/khung và ghi lại
   `lines / rong / cao`.
4. Burn một khung ở mốc có phụ đề, đo trên ảnh: `hộp`, `chữ`, `đệm hai bên`, `đáy hộp`.
   Đệm phải ≈ `viền` (lệch ≤ 3 px), đáy hộp phải ≈ `videoH × (1 − offset)`.
5. Trong app, mở DevTools (hoặc `browser-harness`):
   `box.clientWidth === box.scrollWidth` — **bằng nhau mới là không tràn**;
   `font-size` của chữ ≈ `co_libass × 0,637`; `line-height` ≈ `co_libass`.
6. So ba số: `dòng dài nhất (preview)`, `dòng dài nhất (burn)`, `rong (API)` — phải cùng
   một thứ tự độ lớn; lệch > 5 % là có chỗ nhân tỉ lệ hai lần.

## 6. Bẫy — mỗi dòng là một lần đã trả giá

1. **`fit-content` + `maxWidth`**: `fit-content = min(max-content, maxWidth)` nên khi
   `max-content` > `maxWidth` hộp **rộng bằng `maxWidth`** chứ không co theo dòng đã bẻ
   (đo được: 1012 px thay vì 449). Bỏ `maxWidth` thì `<br>` không làm `max-content` nhỏ đi
   (đo được: 1963 px). **Phải cho mỗi dòng là một khối `<div>`** và bề rộng do API quyết.
2. **`font-size = co`**: libass vẽ nhỏ hơn ~0,637 lần so với Chrome cùng số (đo: cùng một
   dòng 917 px libass vs 1410 px Chrome). Thiếu `× 0,637` thì **hộp đúng mà chữ tràn** —
   đây là lỗi quay lại 3 lần.
3. **libass tự bẻ dòng khác mô phỏng**: dòng dài nhất dự kiến 922 px nhưng libass bẻ thành
   680 + 600 (đệm 132 px). Phải phát **`\N` tường minh**.
4. **`offset_doc` không nằm trong `_ASS_STYLE_CHO_PHEP`**: nó là tham số của `to_ass`, không
   phải trường `Style:`. Thêm vào danh sách trắng thì bị bỏ **im lặng** và burn rơi về 6 %
   (đo: hộp sát đáy trong khi web ở 79 %). Đọc nó ngay trong `to_ass` khi tham số tay `None`.
5. **Bước dòng ≠ nét chữ**: `nét × số_dòng` cho hộp thấp hơn khối chữ ⇒ dòng đầu nằm ngoài
   hộp (đo: hộp 109, chữ 132). Dùng `nét + (n−1) × co`.
6. **Chữ đậm rộng hơn**: `dam = true` làm chữ rộng thêm 1,065 (Pillow không biết).
7. **Hai làn hiển thị**: timeline giữ cả lớp 1 và lớp 2 để soát; **burn và xuất tệp phải lọc
   một dòng mỗi câu** (`mot_dong_moi_cap`), nếu không hai câu khác nhau chồng lên nhau
   (đo: 61 cặp chồng, 64,26 s).
8. **Rules of Hooks**: `useState`/`useEffect` đặt **sau** một `return` sớm làm cả trang thành
   "Trang này không tải được". Mọi hook phải nằm trước mọi `return`.
9. **Đo bằng `getBoundingClientRect` sau `transform`**: nó trả kích thước ĐÃ thu, nên muốn
   so với pixel video phải chia lại cho `scale` (hoặc đo trên khung 1080 px).
10. **`ffmpeg -ss` đặt TRƯỚC `-i`**: filter `ass` vẫn tính mốc từ 0, ảnh ra là phút 0 chứ
    không phải mốc cần xem. Đặt `-ss` sau `-i`.
11. **Mép MẢNH hộp phải là SỐ NGUYÊN**: hộp rộng quá `PlayResX/2` bị chia mảnh, và nếu mỗi
    mảnh được đặt bằng `\pos` làm tròn về `int` thì hai mép kề nhau rơi vào **hai cột khác
    nhau** — mỗi cột chỉ được phủ một nửa và nền video lọt qua thành **vạch dọc giữa hộp**.
    Đo được trên `dub-63.mp4`: cột 539/540 màu `(83,76,71)` trên nền `(216,208,192)`, trong
    khi bản xem trước bằng CSS thì sạch. Biên từng mảnh phải cộng dồn trên **số nguyên**, và
    `\pos` phải giữ `.5` (hàm `_so_ass`) — rasteriser của libass là subpixel. Đây là lỗi CHỈ
    thấy trên pixel, nên phải có bài **burn thật rồi đếm cột**; test đọc chuỗi `.ass` không
    bắt được. Xem ERRATA #78.

## 7. Liên quan

- `ERRATA` #66 (chia mảnh hộp), #67 (chữ đậm), #72 (`\N` + bước dòng), #73 (một nguồn bẻ
  dòng), #74 (burn đè nhau), #78 (vạch hở giữa hai mảnh).
- Test canh: `backend/tests/test_phu_de_style.py`, `test_api_subtitles.py`, `test_dub.py`;
  `frontend/src/lib/phuDeStyle.test.ts`, `frontend/src/components/studio/PhuDeStyle.test.tsx`.

## 8. Nhánh thứ hai: xem trước bằng CHÍNH libass (`PhuDeLibass`)

Đường CSS ở trên phải **mô phỏng** libass, nên mỗi hằng số sai một chút là lệch — và đã 6
lần phải sửa từng cái. Nhánh này bỏ hẳn việc mô phỏng: nó nạp **đúng file `.ass`** mà bản
burn dùng và cho **libass biên dịch sang WebAssembly** (`jassub`) vẽ.

```
editor ──► to_ass() trên backend ──► .ass ──┬──► jassub (wasm libass)  → preview
                                            └──► ffmpeg `ass=` filter   → burn
```

Vì sao chọn `jassub` chứ không tự viết lại: nó LÀ libass (cùng upstream), nên bẻ dòng,
kerning, hình học hộp và vị trí do cùng một bộ máy quyết định. `SubtitlesOctopus` cùng hướng
(cũng libass wasm); `ASS.js` (DOM/CSS) thì KHÔNG đảm bảo khớp pixel với ffmpeg.

### Bật/tắt

Khoá riêng trong `localStorage`: `phu-de-lab:phu-de-libass` = `"1"`/`"0"`, hoặc ô chọn
**"Xem trước bằng libass (wasm)"** trong hộp thoại kiểu chữ. **Mặc định TẮT**: đường CSS là
đường có test và là đường dự phòng; nhánh này là để so và để chuyển sang khi đã kiểm.

### Asset

`frontend/scripts/copy-jassub.mjs` chép `node_modules/jassub/dist` → `public/jassub/` trước
`npm run dev`/`npm run build` (`predev`/`prebuild`). Thư mục đó **không commit** (`.gitignore`):
nó là ~5 MB wasm của một gói đã ghim phiên bản trong `package-lock.json`.

Hai điều bắt buộc, đều là lỗi đã gặp:

1. **Không import subpath của gói**: `import("jassub/dist/worker/…?url")` làm Vite ném
   `Rollup failed to resolve import` (vì `exports` của gói chặn subpath). Phải phục vụ tĩnh
   `/jassub/wasm/…`. Và worker tự `import()` các chunk cạnh nó (`./renderers/*.js`), nên phải
   chép **nguyên** `dist`, không chỉ worker + wasm.
2. **`vite.config.ts` phải có `worker: { format: "es" }`**: `jassub` dựng Worker kiểu module,
   còn Vite mặc định `iife` cho worker ⇒ build ném
   `Invalid value "iife" for option "worker.format"`.

### Điều kiện để khớp (không thể bỏ qua)

- **Cùng file font**, không chỉ cùng tên: preview nạp `/fonts/Archivo.ttf` (bản sao của
  `backend/app/assets/fonts/Archivo.ttf`); ffmpeg nạp đúng file đó qua `fontsdir`/`fc-cache`.
- `PlayResX/Y` lấy từ chính `.ass` backend sinh — không khai lại ở đâu khác.
- **Không để CSS tự tính lại** cỡ chữ/hộp khi đang ở nhánh này: canvas của `jassub` phủ lên
  hình, `PhuDeOverlay` không được vẽ song song.
- Phiên bản libass của `jassub` và của `ffmpeg` có thể khác nhau, `fontconfig` và cấu hình
  shaping cũng vậy. **Cùng libass không bảo đảm giống từng pixel** — nó bảo đảm cùng LUẬT
  (bẻ dòng, bố cục hộp, neo, ngắt dòng tường minh), đó mới là thứ đang làm hai bên lệch.

### Trạng thái kiểm

- `tsc` 0, `npm test` 276 pass, `npm run build` 0. ✅
- **Chưa chụp được ảnh so sánh trong app**: `browser-harness` bị hộp thoại
  "Allow remote debugging?" của Chrome chặn ở lượt đó. Cần bấm Allow rồi:
  1. bật ô chọn libass, tua tới một mốc có phụ đề;
  2. chụp khung, đo hộp đen; so với hộp đo trên ảnh burn cùng mốc (mục 5, bước 4);
  3. `canvas` phải có kích thước > 0 và có nội dung (không trắng trơn).
