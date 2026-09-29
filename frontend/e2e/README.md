# Tầng **CHROME THẬT** (`frontend/e2e/`) — Task 12 · T2

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
node e2e/session.mjs e2e/plans/bon-man.json --out C:\duong\dan\NGOAI-REPO\anh-t12
```

`session.mjs` tự làm hết: gieo DB scratch **ngoài repo** → backend **8631** (không kèm worker) →
dev-server **3100** (`PHUDE_BACKEND_PORT=8631`) → Chrome headless + CDP **9229** → chạy kế hoạch →
đóng Chrome qua CDP → xoá scratch.

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `PHUDE_E2E_PORT` | `8631` | Cổng backend của tầng này. **Không bao giờ** là 8620/8621 |
| `PHUDE_E2E_DOAN` | `600` | Số đoạn của bản ghi DÀI (cho T7) |
| `PHUDE_CDP_PORT` | `9229` | Cổng CDP. **Không dùng 9222** (Chrome của người dùng có thể đang giữ) |
| `PHUDE_CHROME` | `C:/Program Files/Google/Chrome/Application/chrome.exe` | Đường dẫn `chrome.exe` |

`--giu` để giữ scratch lại mà soi. Không `--giu` thì scratch bị xoá trong `finally`.

## Ba quy tắc cứng đã cài trong mã

1. 🔴 **KHÔNG BAO GIỜ chạm 8620/8621.** Đó là cổng **CÓ CHỦ** của `src/api/contract.test.ts` — nó
   tự spawn backend ở 8620 và **dựa vào DB repo RỖNG**. Ai giữ 8620 ⇒ khối hợp đồng **sai giả**
   (đo được: `pass 254 / fail 0` khi bị chiếm, `252/2` khi trống — ERRATA #46 mục 4).
   `session.mjs` **từ chối chạy** nếu 8620/8621 đang mở.
2. 🔴 **KHÔNG BAO GIỜ đổi cổng dev-server.** `3100` vẫn cứng: backend chỉ whitelist CORS
   `http://localhost:3100` / `http://127.0.0.1:3100`; đổi cổng là hỏng CORS, mà sửa CORS thì phải
   chạm `backend/` (bị cấm trong task frontend). Chỉ **cổng BACKEND** cấu hình được
   (`PHUDE_BACKEND_PORT`, mặc định 8620 — xem `dev-server.mjs`).
3. **DB + media ở scratch NGOÀI repo** (`_seed-e2e/`): chạy xong xoá sạch, `data/app.db` của repo
   không bị chạm.

## Luật ĐO đã cài trong driver (`cdp.mjs`)

- **Kiểm URL trước khi tác động**, và không bao giờ tác động lên tab không phải của mình
  (ERRATA #47 mục 6: một script cũ đã `location.reload()` tab `x.com` của người dùng).
- **Luôn cài ĐẦU DÒ `keydown`** trước khi phát phím ⇒ phân biệt *"sự kiện KHÔNG TỚI"* với *"app
  KHÔNG XỬ LÝ"*. Thiếu đầu dò thì mọi kết luận "phím không chạy" là **artifact**.
- **Phím gửi đúng HÌNH DẠNG NGƯỜI THẬT**: `?` **kèm `Shift`**; `Enter` **kèm pha ký tự**
  (`text: "\r"`). Hai lần trong một lượt, "phím không chạy" là do **phép tiêm** (ERRATA #47 mục 5).
  `phim()` **NÉM LỖI** với phím chưa khai hình dạng — cố ý: một hình dạng đoán mò sẽ bị đọc nhầm
  thành lỗi sản phẩm.
- **Chờ theo TÍN HIỆU** (`waitFor`/`waitText`); `timeout` chỉ là **hạn chót** (ERRATA #35 mục 2).
- **Neo phép CHỜ lấy từ DỮ LIỆU gieo** (`seed-kenh-mot.wav`, `今天我們來說…`, `ban-ghi-dai-600.wav`),
  không từ nhãn UI (ERRATA #42 mục 5).

## Kế hoạch có sẵn

| Kế hoạch | Việc | Ảnh |
|---|---|---|
| `plans/bon-man.json` | Bốn màn + bảng phím §11.4 + hàng đợi `.q*` (đối chứng bản vá `c575192`), computed style + toạ độ thật của `.q__ten`/`.q__ly-do` | `01..08` |
| `plans/phim-va-12-5.json` | §11.4 + §12.5 bằng **bàn phím thật**, kèm đầu đò `keydown` cho từng phím | `20..23` |
| `plans/ban-ghi-dai-t7.json` | **T7** — cái giá của bản vá D4: số hàng có mặt trong DOM khi hai mốc ghim cách xa ~500 đoạn | `10..12` |

Chạy lần lượt (không chạy song song: cùng cổng CDP):

```powershell
$out = "C:\Users\Admin\Desktop\ngn\deepseek\_shots\t12"
node e2e/session.mjs e2e/plans/bon-man.json          --out $out
node e2e/session.mjs e2e/plans/phim-va-12-5.json     --out $out
node e2e/session.mjs e2e/plans/ban-ghi-dai-t7.json   --out $out
```

Mỗi lượt ghi `ket-qua.json` cạnh ảnh: **mọi bước + giá trị đo được** (đó là bằng chứng, không phải
log cho vui).

## Cái tầng này **KHÔNG** chứng minh

- **Chất lượng bản dịch tiếng Việt** — ảnh chỉ chứng minh **bố cục/vẽ**. Muốn biết bản dịch tốt
  hay không thì phải **chạy engine thật**.
- **`Ctrl+1/2/3` cho phím VẬT LÝ.** CDP tiêm ở tầng **renderer**, nên nó **đi vòng qua** bảng
  accelerator của trình duyệt (ERRATA #47 mục 7). Phép đo này nói *"binding của app đúng KHI sự
  kiện tới nơi"*, **không** nói gì về một cú bấm tay. Cần **một phép đo của NGƯỜI**.
- **Audio.** `Range`/`play` không được đo ở đây.
