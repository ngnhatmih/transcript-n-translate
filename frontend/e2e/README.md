# Tầng **CHROME THẬT** (`frontend/e2e/`)

> ⚠️ **Tầng này KHÔNG nằm trong `npm test`.** Nó cần **quyền rộng** để mở Chrome, và trong sandbox
> bị hạn chế **Chromium chết** (`FATAL:mojo… Access is denied (0x5)`). Mệnh đề đúng là *"Chromium
> không mở được DƯỚI CÁC CHẾ ĐỘ SANDBOX HẠN CHẾ"* (ERRATA #40) — với `danger-full-access` thì
> `chrome --headless=new --dump-dom about:blank` cho **EXIT=0**.
>
> **jsdom = HÀNH VI/DOM. Chrome thật = HÌNH THỨC** (layout, CSS, ảnh, font, bàn phím vật lý).
> Hai tầng, không phải một.

## Chạy

```powershell
cd C:\Users\Admin\Desktop\ngn\deepseek\phu-de-lab\frontend
npm run e2e
```

hoặc chỉ định kế hoạch và chỗ ghi ảnh:

```powershell
node e2e/session.mjs e2e/plans/hat-tang-song.json --out C:\duong\dan\NGOAI-REPO\anh
```

`session.mjs` tự làm hết: gieo DB scratch **ngoài repo** → backend **8631** (không kèm worker) →
`vite dev` ở **3100** (proxy `/api` sang 8631) → Chrome headless + CDP **9229** → chạy kế hoạch →
đóng Chrome qua CDP → xoá scratch.

### ⚠️ Phải tắt container Docker trước khi chạy

`session.mjs` **từ chối chạy** nếu cổng `3100` hoặc `8620` đang bị chiếm — và đó chính là hai cổng
`docker compose up` đang giữ:

```powershell
docker compose stop web api
npm run e2e
docker compose start web api
```

`8620` là cổng **CÓ CHỦ** của `src/api/contract.test.ts` (xem mục 1 dưới). `3100` là cổng web mà
`vite dev` phải chiếm.

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `PHUDE_E2E_PORT` | `8631` | Cổng backend của tầng này. **Không bao giờ** là 8620/8621 |
| `PHUDE_E2E_DOAN` | `600` | Số đoạn của bản ghi DÀI |
| `PHUDE_E2E_SCRATCH` | `../_seed-e2e` (cạnh repo) | Chỗ ghi DB/media/tán chrome. ⚠️ Phải là thư mục **cạnh gốc workspace** (vì `seed.py` tính `parents[1]`), và **không** nằm trong repo |
| `PHUDE_CDP_PORT` | `9229` | Cổng CDP. **Không dùng 9222** (Chrome của người dùng có thể đang giữ) |
| `PHUDE_CHROME` | `C:/Program Files/Google/Chrome/Application/chrome.exe` | Đường dẫn `chrome.exe` |

`--giu` để giữ scratch lại mà soi. Không `--giu` thì scratch bị xoá trong `finally`.

## Ba quy tắc cứng đã cài trong mã

1. 🔴 **KHÔNG BAO GIỜ chạm 8620/8621.** Đó là cổng **CÓ CHỦ** của `src/api/contract.test.ts` — nó
   tự spawn backend ở 8620 và **dựa vào DB repo RỖNG**. Ai giữ 8620 ⇒ khối hợp đồng **sai giả**
   (đo được: `pass 254 / fail 0` khi bị chiếm, `252/2` khi trống — ERRATA #46 mục 4).
   `session.mjs` **từ chối chạy** nếu 8620/8621 đang mở.
2. 🔴 **KHÔNG BAO GIỜ đổi cổng web.** `3100` vẫn cứng: `backend/app/api/app.py:19` chỉ whitelist CORS
   `http://localhost:3100` / `http://127.0.0.1:3100`; đổi cổng là hỏng CORS, mà sửa CORS thì phải
   chạm `backend/`. Chỉ **cổng BACKEND** cấu hình được (`PHUDE_E2E_PORT`).
3. **DB + media ở scratch NGOÀI repo** (`_seed-e2e/`): chạy xong xoá sạch, `data/app.db` của repo
   không bị chạm.

## Lịch sử: tầng này đã CHẾT rồi được sửa (2026-10-31)

Đo được, không phải suy đoán. Commit đổi stack (`15d0646`) xoá `frontend/dev-server.mjs`, nhưng
`session.mjs:196` vẫn `spawn(process.execPath, ["dev-server.mjs"])` ⇒ mọi lượt chạy chết ở
`dev-server khong len`. Cả 5 plan cũ cũng trỏ selector của `screens/` và `shell/` đã bị xoá
(`.ed__khung`, `.ch__item`, `.q__ten`, `.shell__mid`) ⇒ không plan nào chạy được trên giao diện mới.

Đã sửa:

| chỗ | trước | sau |
|---|---|---|
| `session.mjs` | spawn `dev-server.mjs` (đã xoá) | spawn `node_modules/vite/bin/vite.js dev` |
| `vite.config.ts` | proxy cứng `http://127.0.0.1:8620`, cổng cứng `5173` | đọc `PHUDE_BACKEND_PORT` / `PHUDE_DEV_PORT` |
| `cdp.mjs` `waitFor`/`waitText` | trượt chỉ `console.log("⚠️ …")` ⇒ **`EXIT=0` xanh giả** | `throw` (trừ khi plan đặt `"required": false`) |
| 5 plan cũ | selector giao diện đã xoá | **xoá**; thay bằng `plans/hat-tang-song.json` |
| `package.json` | không có script nào gọi e2e | `npm run e2e` |

Ba lỗi trong chính plan đầu tiên, đều đo được và đã sửa:

- khoá `buoc` thay vì `steps` ⇒ `plan.steps ?? []` trả **mảng rỗng**, không bước nào chạy,
  `ket-qua.json` 2 byte, `EXIT=0` — **xanh giả**;
- `shot` đọc khoá `name`, tôi viết `ten` ⇒ ảnh tên `undefined.png`;
- `waitText "Phòng thu biên tập"` trượt vì chuỗi đó chỉ có trong `<title>`, tên trên header nằm
  trong `<h1>` (`Studio.tsx:688`) ⇒ đổi sang `waitFor h1` + `khangDinh` trên `textContent`.

Ngoài ra `_seed/serve_no_worker.py` (tài sản ngoài repo) truyền 5 tham số vị trí vào `build_app`,
nhưng M-13 đã bỏ tham số thứ năm ⇒ `TypeError: build_app() takes 4 positional arguments but 5 were
given`. Đã sửa: `build_app(repos, specs, worker, broker)`.

## Luật ĐO đã cài trong driver (`cdp.mjs`)

- **Kiểm URL trước khi tác động**, và không bao giờ tác động lên tab không phải của mình
  (ERRATA #47 mục 6: một script cũ đã `location.reload()` tab `x.com` của người dùng).
- **Luôn cài ĐẦU DÒ `keydown`** trước khi phát phím ⇒ phân biệt *"sự kiện KHÔNG TỚI"* với *"app
  KHÔNG XỬ LÝ"*. Cài **sau mỗi `nav`** và **trước mỗi phím**; một bước `key` đọc ra đầu dò RỖNG
  làm LƯỢT ĐÓ ĐỎ.
- **Bước `khangDinh`** (`{"do":"khangDinh","js":"…","thongDiep":"…"}`) là `assert`, **không** phải
  `log`. Từ 2026-10-31, `waitFor`/`waitText` trượt cũng `throw` theo cùng nguyên tắc: **cảnh báo
  không làm đỏ được lượt chạy thì không phải cổng kiểm**. Muốn chỉ ghi nhận thì đặt
  `"required": false` ngay trong plan — quyết định viết ra được, không phải dấu ⚠️ trôi qua log.
- **Phím gửi đúng HÌNH DẠNG NGƯỜI THẬT**: `?` **kèm `Shift`**; `Enter` **kèm pha ký tự**
  (`text: "\r"`). `phim()` **NÉM LỖI** với phím chưa khai hình dạng.
- **Chờ theo TÍN HIỆU** (`waitFor`/`waitText`); `timeout` chỉ là **hạn chót** (ERRATA #35 mục 2).
- ⚠️ **Đọc DOM NGAY sau khi một điều kiện SỚM hơn thoả là đọc SAI.** Đo được với chính plan
  `hat-tang-song.json`: ngay sau `h1` hiện, `soOThat=0`; sau `waitFor [aria-label^="Phụ đề đoạn"]`
  thì `soOThat=6`. `App` nạp theo chuỗi `sources → transcripts → transcripts/{id} →
  translations/{id}`, nên phải chờ tín hiệu **cuối** chuỗi.
- **Neo phép CHỜ lấy từ DỮ LIỆU gieo** (`seed-kenh-mot.wav`, `今天我們來說…`), không từ nhãn UI
  (ERRATA #42 mục 5).

## Kế hoạch có sẵn

| Kế hoạch | Việc |
|---|---|
| `plans/hat-tang-song.json` | **Chỉ chứng minh hạ tầng sống**: mở app, chờ thanh bước đường ống, đo `h1`, chờ ô phụ đề, khẳng định có ≥1 ô với dữ liệu THẬT từ backend 8631. Không kiểm giao diện sâu. |

Đo được ở lượt chạy cuối (`EXIT_E2E=0`):

```
[eval] {"soOThat":0,"dau":null}                    ← đo QUÁ SỚM, ngay sau h1
[eval] {"soOThat":6,"dau":"Phụ đề đoạn 1",
        "chu":"Chào mừng các bạn đến với chương trình hôm nay."}
[shot] ...\01-app-mo-duoc.png (114749 B)
```

## Cái tầng này **KHÔNG** chứng minh

- **Chất lượng bản dịch tiếng Việt** — ảnh chỉ chứng minh **bố cục/vẽ**. Muốn biết bản dịch tốt
  hay không thì phải **chạy engine thật**.
- **`Ctrl+1/2/3` cho phím VẬT LÝ.** CDP tiêm ở tầng **renderer**, nên nó **đi vòng qua** bảng
  accelerator của trình duyệt (ERRATA #47 mục 7). Phép đo này nói *"binding của app đúng KHI sự
  kiện tới nơi"*, **không** nói gì về một cú bấm tay. Cần **một phép đo của NGƯỜI**.
- **Audio.** `Range`/`play` không được đo ở đây.
- **Giao diện mới chưa có plan kiểm sâu.** `hat-tang-song.json` chỉ mở được trang và thấy dữ liệu.
  Các luồng thật (sửa chữ phụ đề → `PATCH`, kéo mốc timeline, bấm `duyệt` trên thanh bước) hiện
  được phủ ở tầng jsdom (`src/components/studio/Studio.test.tsx`, `src/App.test.tsx`), **chưa** ở
  tầng Chrome thật.
