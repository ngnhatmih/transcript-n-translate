# Giai đoạn Frontend — thiết kế

**Ngày:** 2026-09-26
**Trạng thái:** chờ người dùng duyệt trước khi viết plan
**Spec nền (không thay thế):**
- `docs/superpowers/specs/2026-09-25-phu-de-lab-ui-design.md` (giao diện — **nguồn có thẩm quyền về hình thức**)
- `docs/superpowers/specs/2026-09-25-phu-de-lab-design.md` (v3 — kiến trúc)
- `docs/superpowers/specs/2026-09-26-giai-doan-2-dich-design.md` (backend Workspace 2, đã ship)

**Tiền đề đã ship:** Giai đoạn 1a + Giai đoạn 2, nhánh `gd2-mt`, suite backend **821 passed**.

Spec này **không** lặp lại spec nền. Nó chốt phạm vi, các quyết định còn để mở, và những chỗ spec nền đã lỗi thời so với mã.

---

## 1. Mục tiêu & phạm vi

**Mục tiêu:** một bàn làm việc chạy được trong trình duyệt, phục vụ **bốn màn hình mà backend hôm nay đã phục vụ được**, đủ để làm trọn luồng biên tập bằng bàn phím (tiêu chí §12.5 của spec UI).

**Trong phạm vi:**

| Hạng mục | Quyết định |
|---|---|
| Khung | Ba vùng (KÊNH / BÀN LÀM VIỆC / HÀNG ĐỢI) + header + thanh transport. **Không router, không wizard.** |
| §4.1/4.2 Biên tập (+ rỗng) | Có |
| §4.3 Đối chiếu | Có (hai cột + CPS, N bản dịch dạng **segmented control**) |
| §4.4 Tab Thuật ngữ | Có, kèm **số bản dịch bị ảnh hưởng trước khi lưu** |
| §4.8 Lỗi Ollama | Có, là **trạng thái hạng nhất**, không phải toast |
| Transport / player | Có, dùng `GET /api/media/{source_id}` (đã hỗ trợ `Range`) |

**Ngoài phạm vi (hoãn có chủ ý):** §4.5 Chimera (backend hoãn cùng HY-MT1.5) · §4.6 bảng eval · §4.7 chấm tay (hai màn này cần **API eval chưa tồn tại**) · layout điện thoại (§10.4) · sáng/tối và tuỳ biến bảng màu (§10.1–2) · kéo-thả sắp xếp cột (§10.6).

---

## 2. Stack, và những gì CỐ Ý không dùng

**Dùng:** React 19 + TypeScript + **Vite**, dev server ở **cổng 3100** (khớp `FRONTEND_DEV_ORIGINS` đã có ở `backend/app/api/app.py:19`), proxy `/api` → `127.0.0.1:8620`.

**Cố ý KHÔNG dùng, kèm lý do:**

| Không dùng | Vì sao |
|---|---|
| **Tailwind** | Spec UI §2 đã chốt cứng bảng màu/thang chữ/khoảng cách, và §10 cấm đổi theme. Tailwind là plugin build + lớp tiện ích cho một hệ thống không có biến thể ⇒ không kiếm được gì. Dùng CSS + custom property. |
| **Thư viện quản lý trạng thái (TanStack Query, Redux…)** | Luồng dữ liệu là **một** SSE toàn cục đẩy trạng thái job + vài `GET`. Cache/invalidation của query library là trừu tượng không ai yêu cầu. Dùng hook + reducer. |
| **Sinh type từ `/openapi.json`** | Thêm dev-dependency **và** một bước phải nhớ chạy lại. Thứ nhỏ nhất sập khi shape trôi là **một contract test** trên backend thật — thứ ta đã làm vì chọn Playwright. Ít bộ phận hơn, và sập ồn ào hơn. |
| **`@tanstack/react-virtual`** | Hàng cao **đều**, nên cửa sổ hoá là ~30 dòng số học test được **không cần DOM**. Ghi trần bằng `ponytail:`; đổi sang react-virtual khi hàng cao khác nhau. |
| **Thư viện component (shadcn, Radix, MUI)** | Các thành phần ở §6 là đặc thù và ít; kéo cả một hệ vào để dùng vài thứ là lỗ. |

**Một xung đột đã giải quyết:** ponytail nói "một kiểm tra chạy được, không framework, không fixture". Dự án này đã có chuẩn nghiệm thu riêng (suite đầy đủ + mutation chứng minh test không rỗng) và ponytail **không được** đơn giản hoá thứ đã được yêu cầu rõ ràng. ⇒ **Chuẩn của dự án thắng.** Ponytail áp cho *thứ được dựng*, không áp cho *kỷ luật nghiệm thu*.

---

## 3. Kiến trúc client

**Không router.** Một shell duy nhất với biến `mode ∈ {edit, compare, glossary}`. Hai màn đo lường của spec UI thay toàn bộ vùng giữa — nhưng chúng **ngoài phạm vi**, nên `mode` chỉ có ba giá trị.

**Phân chia trạng thái — chỗ dễ hỏng nhất:**

- **Trạng thái server** nằm ở một tầng dữ liệu mỏng: hàm `fetch` theo nhóm API, cộng **đúng một** subscription tới `/api/jobs/stream`. Backend chỉ có **một** stream toàn cục; mở hai là sai thiết kế.
- Stream gửi **ảnh chụp trước** rồi mới tới sự kiện. Mất kết nối ⇒ nối lại có backoff, và **khi nối lại thì đọc ảnh chụp mới**, không tin trạng thái cũ.
- **Trạng thái client** (kênh đang chọn, đoạn đang phát, dòng đang sửa, hệ số ghim bản B) nằm trong **một reducer**, không nhét vào cache server.
- **Không ghi kiểu đoán trước (optimistic) cho bản dịch.** Backend sở hữu alignment và QA; client gửi rồi **đọc lại**. Một bản dịch hiển thị khác thứ đã lưu đúng là loại nói dối mà Giai đoạn 2 vừa bịt hai lần.

**Kiểu dữ liệu:** viết tay trong `src/api/types.ts`, và **một** contract test chạy trên backend thật khẳng định shape của những endpoint client dùng. Đổi tên khoá ở server (như `translated_from_version` → `transcript_version` ở Giai đoạn 2) phải làm **đỏ** contract test.

---

## 4. Bốn màn hình

**§4.1 BIÊN TẬP.** Rail thời gian + danh sách đoạn ảo hoá. Đoạn đang phát có lề amber + đầu đọc chạy dọc rail; đoạn `suspect` có vân chéo kèm **lý do** (`nhạc nền`, `nghi ngờ`), đọc từ trường `qa`/`suspect` của `Segment`. **Dòng đang sửa phải được ghim** để cửa sổ hoá không lấy mất focus — đây là U6 và là chỗ dễ tự bắn vào chân nhất.

**§4.3 ĐỐI CHIẾU.** Ruột vùng giữa thành hai cột + CPS. N bản dịch là **segmented control** (không phải N tab — U7), **ghim bản B** để so. Cột CPS **lấy ngưỡng từ backend** (đã có `readability` + `mt_qa`), **không** tính lại ở client: hai nơi tính cùng một đại lượng là đúng thứ Giai đoạn 2 vừa phải đi vá.

**§4.4 THUẬT NGỮ.** CRUD glossary. Trước khi lưu, hiện **bao nhiêu bản dịch bị ảnh hưởng** từ trường `affected` mà route đã trả, rồi mới sinh job dịch lại. Đổi thuật ngữ **chưa duyệt** thì không ảnh hưởng gì (đúng luật backend) — UI phải nói rõ điều đó thay vì để người dùng đoán.

**§4.8 LỖI OLLAMA.** Đọc `/api/status` + `/api/registry`. Nói rõ **cái gì còn chạy được, cái gì không, và cách sửa**. Dropdown engine chỉ hiện engine có `available` — chỗ mà bản vá Task 12 của Giai đoạn 2 trở nên có ích.

**Transport.** `GET /api/media/{source_id}`, seek bằng `Range`. Ba nút xuất gọi route export hình dạng spec `GET /api/export/{translation_id}?format=&bilingual=`.

**Bàn phím (yêu cầu, không phải điểm cộng — spec UI §5.1):** phát/dừng, nhảy đoạn, `[` `]` chỉnh mốc, nudge, nghe lại, chuyển mode, duyệt, xuất. **Mọi** thao tác biên tập phải làm được mà không chạm chuột.

---

## 5. Hệ thống thiết kế

Lấy nguyên từ spec UI §2 (chữ, màu, không gian, bề mặt, chuyển động) thành **custom property** trong một `tokens.css`. Font **self-host woff2, không CDN** (§8.1) — app chạy offline. **Grain phủ toàn trang bằng MỘT lớp `pointer-events:none`** (§8.6), không lặp trong từng component. "Nghi ngờ" là **vân**, không phải màu (§2.5) — nên nó phải sống trong CSS, không trong logic.

---

## 6. Nghiệm thu

**Đơn vị (Vitest):** cửa sổ hoá (kể cả ghim dòng), chuyển timecode, đọc CPS, reducer, **parser SSE** (ảnh chụp + sự kiện xen kẽ, mảnh `data:` bị cắt giữa hai lần đọc), và contract test shape API trên backend thật.

**Đầu-cuối (Playwright trên backend thật với engine giả, theo khuôn `test_e2e_fake.py` / `test_e2e_translate.py`):** nạp tệp → bóc băng → soát/sửa dòng → duyệt → dịch → đối chiếu → sửa thuật ngữ thấy số ảnh hưởng → xuất. Mỗi màn hình ít nhất một lần chạy thật trong trình duyệt.

**Engine giả đến từ đâu — quyết định, vì backend không có cơ chế plugin stub.** Fake engine của backend được tiêm **trong tiến trình pytest**; Playwright thì điều khiển một **tiến trình server thật**, nên không tiêm được như vậy. Cách làm:

- **Phần lớn màn hình chỉ ĐỌC**, nên chúng được phủ bằng cách **gieo thẳng dữ liệu vào DB** (một script tạo source + transcript + translation + glossary + job với trạng thái mong muốn) rồi Playwright chỉ mở UI. Không cần model, không cần GPU, chạy nhanh và tất định.
- **Vài luồng thật sự khởi động job** (nạp tệp → bóc băng; tạo bản dịch) chạy trên **engine thật đã có sẵn**: ASR bằng một model nhỏ, MT bằng `opus-mt` hoặc `qwen2.5-3b` (đã pull). Số lần chạy thật giữ **ít** và ghi lại **số đo**, đúng khuôn "một lần chạy thật phải có số" mà hai giai đoạn trước đã dùng.
- **Không** dựng thêm một endpoint/registry giả chỉ để test — đó là bộ phận chạy được trong sản phẩm mà chỉ test dùng.

**Luật giữ nguyên từ hai giai đoạn trước:** không amend/rebase; scratch ngoài repo; mọi tuyên bố kèm lệnh chính xác + dòng cuối nguyên văn; **mọi test mới phải chứng minh không rỗng** bằng mutation; và **hành vi đi qua đường thật thì test phải đi qua đường thật** — không gán thẳng trường của đối tượng giả, vì Task 11 của Giai đoạn 2 đã có một test huỷ *tự thoả mãn* xanh trong khi sản phẩm hỏng.

**Chi phí phải xin phép:** `npx playwright install` tải trình duyệt **ra ngoài workspace** ⇒ sẽ bị sandbox từ chối và cần người dùng duyệt, giống lúc cài Ollama.

---

## 7. Nợ phải khai

- **`ponytail:`** là quy ước chính thức của giai đoạn này cho những chỗ cắt góc có trần đã biết (ví dụ cửa sổ hoá chỉ đúng với hàng cao đều). Mỗi dấu phải nêu **trần** và **đường nâng cấp**. Vòng dọn cuối gom chúng lại — "để sau" không được thành "không bao giờ".
- **Nợ Giai đoạn 2 chưa trả:** vòng dọn Minor gần nhất **chưa có reviewer độc lập**; `N-9` (route export **ghi tệp trên một `GET`**) chờ người dùng quyết; `DEFAULT_MAX_CHARS = 1200` **chưa từng bị ép**; chất lượng dịch **chưa đánh giá**. Giai đoạn frontend **không** tự động trả những món này, nhưng **không được che** chúng.
- **Chưa đo được ở môi trường này:** hành vi thật của trình duyệt (Playwright cần duyệt tải), và mọi thứ phụ thuộc GPU.

---

## 8. Tiêu chí nghiệm thu

1. Bốn màn hình chạy được trong trình duyệt thật, ở cổng 3100, nói chuyện với backend thật ở 8620.
2. Làm trọn luồng biên tập **không chạm chuột** (trừ thao tác nạp tệp ban đầu — giới hạn của trình duyệt, không phải của thiết kế).
3. Nạp nhiều tệp → thấy rõ tệp nào chạy, tệp nào chờ, **và vì sao chờ**.
4. Đổi một thuật ngữ → thấy **số bản dịch bị ảnh hưởng** trước khi lưu.
5. Chế độ Đối chiếu chỉ ra được **dòng vượt ngưỡng đọc** mà không phải tự đếm, và ngưỡng đó **đến từ backend**.
6. Tắt Ollama → app nói rõ cái gì còn chạy được và cách sửa; dropdown không mời chọn engine không phục vụ được.
7. Contract test **đỏ** khi một khoá JSON của server đổi tên.
8. Danh sách 2000 dòng vẫn cuộn mượt và **không mất focus** khi đang sửa một dòng.
9. Mọi dấu `ponytail:` đều nêu trần + đường nâng cấp.

---

## 9. Những gì spec này KHÔNG quyết

- Ngưỡng CPS hiển thị trên UI (lấy từ backend, nhưng cách trình bày thì chưa).
- Bố cục chính xác trong từng vùng — thuộc spec UI §3/§4, spec này chỉ chốt phạm vi.
- Có dùng Web Worker cho việc gì không (YAGNI cho tới khi đo được).
- Chuyện `N-9` của Giai đoạn 2 (route export ghi tệp trên `GET`) — người dùng quyết.
