# BẢNG TIÊU CHÍ §12 — BẰNG CHỨNG NGHIỆM THU (TASK 12)

> **Vì sao tệp này tồn tại (và vì sao nó ĐƯỢC TRACK):** bảng này từng chỉ nằm trong
> `.superpowers/sdd/…` — thư mục **bị gitignore** (`git ls-files .superpowers` = **0**).
> ⇒ Bằng chứng nghiệm thu **không thuộc sản phẩm**: không ai checkout được nó. Re-review vòng sửa 1
> của Task 12 xếp đây là **Important (`I6`)** và đã đúng. Tệp này là bản **được track**.

## 1. Quy ước — mỗi dòng ĐÚNG **MỘT** lớp bằng chứng

| Lớp | Nghĩa | Không được suy ra gì thêm |
|---|---|---|
| `TÊN BÀI TEST` | có bài test chạy được, nêu **đúng tên bài** | **không** chứng minh bố cục/CSS |
| `ẢNH` | ảnh chụp **Chrome thật** | **không** chứng minh hành vi; **không** chứng minh chất lượng bản dịch |
| `ĐO COMPUTED STYLE` | `getComputedStyle` trong **Chrome thật** | **không** chứng minh hành vi |
| `CHƯA ĐO` | chưa ai đo | — |

🔴 **jsdom không có layout/CSS/audio** ⇒ mọi khẳng định **hình thức** ở đây **chỉ** đến từ tầng Chrome thật
hoặc từ ảnh. **Không** dòng nào được ghi "đã kiểm" bằng ảnh mà thực ra chỉ có test, và ngược lại.

## 2. Bảng

| # | Tiêu chí §12 (spec UI, nguyên văn rút gọn) | **LỚP BẰNG CHỨNG** | Chi tiết / số đo |
|---|---|---|---|
| **1** | *"Nhìn ảnh chụp không có logo vẫn nhận ra: **đây là app mà thời gian là trục dọc**"* | **ẢNH** | `02-bien-tap-nap-du-lieu-4-2.png` (rail thời gian bên trái từng dòng, và transport ở đáy). Thuần thị giác — **không** có bài test nào trả lời được câu này. |
| **2** | *"Nạp 3 tệp cùng lúc → thấy rõ tệp nào đang chạy, tệp nào chờ, **và vì sao chờ**"* | **TÊN BÀI TEST** (một phần) + **ẢNH** | Test: `IntakeFrame.test.tsx` (*"D) BẤM `nạp`…"*), `QueueZone.test.tsx` (*"D2 CÂU CHỮ TRUNG THỰC…"*, `data-state`). Ảnh: `01-bon-man-va-hang-doi-truoc-khi-chon-kenh.png`, `03-hang-doi-q-sau-va.png`. ⚠️ **TRẦN khai rõ:** kế hoạch e2e gieo **BA JOB của MỘT kênh**, **không phải ba TỆP** ⇒ vế *"3 tệp cùng lúc"* **chưa** được chứng minh end-to-end. |
| **3** | *"Sửa một thuật ngữ → thấy ngay **bao nhiêu bản dịch bị ảnh hưởng trước khi** bấm lưu"* | **TÊN BÀI TEST** | `src/screens/GlossaryScreen.test.tsx`: *"XEM TRƯỚC…"*, *"I1…"*, *"I1b/I1c/I1d/I1e"*, *"HỢP ĐỒNG THAM SỐ…"*. |
| **4** | *"Ở chế độ Đối chiếu, phát hiện được **dòng dịch vượt ngưỡng đọc** mà không phải tự đếm"* | **TÊN BÀI TEST** + **ẢNH** | Test: `CompareScreen.test.tsx` *"đánh dấu dòng VƯỢT NGƯỠNG…"*, *"`over` của backend thắng…"*, *"HÌNH THỨC: … glyph `⚠`"*. Ảnh: `05-doi-chieu-cps-hai-chieu.png` (có **cả hai chiều**: có cờ và không cờ). |
| **5** | *"Không chạm chuột lần nào vẫn làm được **toàn bộ phần biên tập**"* (§12.5: 6 bước) | **TÊN BÀI TEST** + **ẢNH** | **3/6 bước đo TRỰC TIẾP** (chuyển đoạn `J/K/N` · sửa dòng `Enter` · đổi chế độ `Ctrl+1/2/3`) **+ 3/6 bước spec KHÔNG gán phím** (soát · dịch · xuất) — đi được bằng bàn phím **native** nhưng **không** có bài đo riêng. ⚠️ `Esc` **không** phải một trong 6 bước (đây là chỗ cách đếm cũ tự mâu thuẫn). Ảnh: `20..23`. ⚠️ **TRẦN:** `Ctrl+1/2/3` là **phím VẬT LÝ chưa đo** — CDP tiêm ở tầng renderer nên **đi vòng** qua bảng accelerator của trình duyệt (ERRATA #47 mục 7). |
| **6** | *"Tắt Ollama → app nói rõ **cái gì còn chạy được**, cái gì không, và cách sửa"* | **TÊN BÀI TEST** | `src/screens/OllamaDown.test.tsx`: *"panel nói rõ cái gì CÒN chạy được…"*, *"…KHÔNG chạy được…"*, *"…CÁCH SỬA — cả `down` LẪN `unknown`"*, *"phân loại theo `available`…"*, *"TÁCH theo `kind`…"*. ⚠️ **TRẦN: KHÔNG có ảnh** — máy này Ollama **`up`** nên panel **VẮNG**; ảnh `08-ollama-down-neu-panel-hien.png` mang tên *"nếu panel hiện"* và **không** phải bằng chứng. |
| **7** | *"Bảng eval trả lời được 'engine nào tốt hơn' bằng **số**"* | **CHƯA ĐO — NGOÀI PHẠM VI** | **Theo quyết định của NGƯỜI DÙNG**: giai đoạn này chỉ làm **bốn màn**; **không** màn eval, không Chimera, không mobile, không đổi theme. Dòng **giữ nguyên**, không xoá. |

## 3. TRẦN của bảng này (mỗi mục có chủ)

1. **Tiêu chí 2** — ba **JOB** của một kênh, không phải ba **TỆP** (chủ: kế hoạch e2e).
2. **Tiêu chí 5** — 3/6 bước chỉ có bàn phím **native**, không có bài đo; và `Ctrl+1/2/3` là phím **vật lý** chưa đo (chủ: NGƯỜI, ERRATA #47 mục 7).
3. **Tiêu chí 6** — **không có ảnh** vì Ollama `up` (chủ: môi trường; lệnh cấm tắt `ollama`).
4. **Tiêu chí 7** — ngoài phạm vi theo quyết định người dùng.
5. **`seek`/`Range` trong Chrome thật chưa đo** (chủ: Task 12 khai; ảnh **không** chứng minh được).
6. **`.q*` và mọi khẳng định hình thức khác** chỉ có **ảnh + computed style** làm bằng chứng.

## 4. Cách tái lập (tầng Chrome thật)

```powershell
cd frontend
node e2e/session.mjs e2e/plans/bon-man.json        --out <thư mục NGOÀI repo>
node e2e/session.mjs e2e/plans/phim-va-12-5.json   --out <thư mục NGOÀI repo>
node e2e/session.mjs e2e/plans/ban-ghi-dai-t7.json --out <thư mục NGOÀI repo>
```

Mỗi lượt: gieo DB scratch **cạnh repo**, backend **8631**, dev-server **3100** (`PHUDE_BACKEND_PORT=8631`),
Chrome headless CDP **9229**, rồi **tự dọn**. ⚠️ Nó **từ chối** chạy nếu **8620/8621** đang mở (cổng **có chủ**
của `contract.test.ts`). Tầng này **KHÔNG** nằm trong `npm test` và cần **quyền rộng** (Chromium chết trong
sandbox bị hạn chế — ERRATA **#40**).

## 5. Số đo đã dùng cho các khẳng định **hình thức** (Chrome thật, lượt của phiên chính)

- **C1 (Critical đã sửa):** chỉ `.ed__khung` nhận `scrollTop` (`5000`; mọi tổ tiên `0`; `window_scrollY 0`);
  `clientHeight 765 / scrollHeight 26400`; `html_scrollHeight 900 = innerHeight`; cuộn `21120` ⇒ đọc lại `21120`;
  hàng `i=481` **có mặt trong DOM** sau khi cuộn; hàng đầu **đã rời**. Ảnh `10-c1-khung-cuon-that.png`.
- **Trần ghim (T7):** trong trần (`i=1`) ⇒ `{scrollTop:0, soHang:16}`; **ngoài trần** (`i=481`) ⇒
  `{soHang:22, scrollTop:20924, data-i 471..492}`; đáy danh sách ⇒ `data-i 578..599`, `scrollTop 25635`
  (**không còn màn hình trắng** — trước bản vá ảnh là **5 983 B trắng hoàn toàn**).
- **Bảng phím §11.4:** mở bằng **`Shift+?`**, **19 hàng**, đúng **3 hàng `CHƯA NỐI`** (`S`, `M`, `Ctrl+Enter`);
  `[` = *"đặt mốc start tại đầu đọc"*, `]` = *"đặt mốc end tại đầu đọc"*. Ảnh `04/20`.
- **`.q*`:** `ul.q__danh-sach{list-style:none}`, `li.q__item{display:flex;flex-wrap:wrap;gap:4px/8px}`;
  **khoảng cách** giữa `span.q__ten` và `span.q__ly-do` = **8 px** (= `column-gap`), đo được
  `{"tenKetThuc":1218,"lyDoBatDau":1226,"cach":8}` — **nguồn trên đĩa:** `_shots/t13/ket-qua.json`
  (và `_shots/t12/ket-qua.json` cho **cùng** con số).
  ⚠️ **Toạ độ TUYỆT ĐỐI phụ thuộc bề rộng khung nhìn ⇒ KHÔNG tái lập được** (kế hoạch e2e ghim
  `width 1440` — `plans/bon-man.json`, `cdp.mjs` áp bằng `Emulation.setDeviceMetricsOverride`); chỉ
  **khoảng cách** là bất biến, nên đây mới là thứ được ghi. Ảnh `03`.
  ⚠️ **ĐÍNH CHÍNH (review cuối Task 13, `I2`):** bản trước của dòng này viết *"đo ở **hai** bề rộng khung
  nhìn khác nhau (856→864; 1218→1226)"* — **câu chống lưng đó SAI**: không artefact nào chứa 856/864
  (cặp số ấy chỉ tồn tại trong hội thoại của phiên chính, không có tệp), và mỗi lượt e2e chỉ chạy **một**
  bề rộng. **Kết luận 8 px vẫn đúng**; chỉ câu dẫn chứng là sai và đã bị thay bằng nguồn trên đĩa.
