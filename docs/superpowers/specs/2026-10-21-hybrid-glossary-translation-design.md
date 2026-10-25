# Thiết kế: đường dịch hybrid để cưỡng chế thuật ngữ

Ngày: 2026-10-21 · Nhánh: `codex/accuracy-first-pipelines` · Trạng thái: **chờ duyệt, chưa có mã**

## 1. Vấn đề

`opus-mt` là engine dịch mặc định: nhanh (≈ 11,9 s cho clip 115 đoạn), nhưng khai
`glossary_prompt: false` và không có `term_placeholder`, nên **không có đường nào** để bắt
nó dùng thuật ngữ đã duyệt. Đo trên clip thử: 7/7 đoạn có thuật ngữ đều thiếu rendering
glossary, và QA chỉ nói được một câu ở cấp lượt (`engine_no_glossary`).

`hy-mt` thì cưỡng chế được thuật ngữ (token + khôi phục, đã đo 7/7), nhưng dịch cả clip thì
đắt: 78,91 – 118,57 s ở lô 30, 57,72 – 95,42 s ở lô 15, vì có chế độ chép nguồn theo lô.

**Hybrid** = để `opus-mt` dịch cả clip, rồi chỉ những đoạn **có thuật ngữ** mới được
`hy-mt` dịch lại một mình. Đo spike: 7 đoạn bị kích hoạt, thêm 5,23 s ⇒ tổng **17,09 s**,
tức **1,31–1,41×** opus và **rẻ hơn hy-mt một mình 3,4–7,6×**.

## 2. Hybrid KHÔNG phải là gì (ghi trước để khỏi quảng cáo quá)

Trên clip này hybrid **không** bắt được chữ Hán (opus vốn 0/115) và **không** sửa `cps:`/
`length:` — sau khi dịch lại, `cps:` còn 6/7, có đoạn tệ hơn vì rendering glossary dài
(`cps:14=43,7`). Nó cũng **không** cứu loại lỗi opus từng mắc mà QA không gắn cờ ("Utah"
cho 福州, "- Vâng, thưa sếp" cho 长). Giá trị của nó là **cưỡng chế thuật ngữ**, không phải
tăng độ chính xác tổng quát.

## 3. Ba quyết định

### 3.1 Kích hoạt: đoạn chứa thuật ngữ đã duyệt — KHÔNG dùng cờ QA

Lý do đo được: `missing_term` **không tồn tại** trong lượt chạy thật của `opus-mt`; QA chỉ
gắn `engine_no_glossary` ở cấp lượt, vì engine không khai glossary. Spike phải *hỏi lại*
`qa_translation` với `supports_glossary=True` mới có cờ từng đoạn. Nếu lấy cờ QA làm điều
kiện thì hybrid **không bao giờ chạy** trên đường sản phẩm.

Điều kiện dùng thay thế — tất định, không cần vòng QA nào:

> một đoạn bị kích hoạt khi `text` nguồn của nó chứa ít nhất một `term` đã duyệt thuộc
> glossary của ngôn ngữ nguồn, **hoặc** bản dịch của nó rỗng.

Hai điều kiện này bằng đúng tập 7 đoạn mà spike đo được. Điều kiện "rỗng" thêm vào vì đó là
lỗi hình thức mà `hy-mt` có thể sửa, không tốn gì khi không có đoạn rỗng.

### 3.2 Thứ tự và bất biến

1. `opus-mt` dịch cả lô như hiện nay (không đổi gì ở đường này).
2. Tính tập đoạn bị kích hoạt trên **chữ nguồn**, trước khi gọi bất kỳ engine nào.
3. Với từng đoạn bị kích hoạt: gọi engine dự phòng **một mình đoạn đó** qua đúng đường đã
   ship (bảo vệ thuật ngữ bằng token + `echo_guard` nếu engine có khai).
4. Thay **chỉ `text`** của đoạn đó. `i`/`start`/`end`/`words` phải giữ nguyên từng byte.
5. Thứ tự và số đoạn không đổi; không gộp, không tách, không sắp lại.

### 3.3 QA hai nguồn

- `engine_no_glossary` không còn là cảnh báo khi hybrid đã xử lý **mọi** đoạn có thuật ngữ:
  đổi thành thông tin "đã cưỡng chế bằng đường dự phòng", kèm số đoạn đã xử lý.
- `cps:`/`length:` vẫn báo nguyên, vì hybrid không sửa chúng — nếu ẩn đi là nói dối.
- Thêm dấu vết theo từng đoạn: engine nào đã sinh ra `text` cuối (metadata của bản dịch,
  không phải trường mới trên `Segment`). Cần cho báo cáo và cho việc soát sau này.

## 4. Cấu hình và gating

- Cặp engine là **dữ liệu** trong `registry.json`: engine nền (`opus-mt`) và engine dự phòng
  (engine có `term_placeholder: true`, hiện là `hy-mt-1.5-7b`). Không hard-code id trong
  pipeline.
- Engine dự phòng **không sẵn sàng** (chưa pull, `available: false`) ⇒ hybrid **không chạy**,
  giữ nguyên đầu ra của engine nền, gắn `engine_no_glossary` như hôm nay. Không được làm job
  hỏng vì thiếu model.
- Mặc định **tắt** cho tới khi có số đo trên đường sản phẩm; bật bằng dữ liệu, không bằng
  sửa code.

## 5. Xử lý lỗi

Nếu engine dự phòng lỗi trên một đoạn (`EchoProblem`, hết thời gian, trả về rỗng): **giữ
bản dịch của engine nền cho đoạn đó**, gắn cờ QA `hybrid_fallback` kèm mã lỗi, và tiếp tục.
Không đoạn nào được biến mất, không job nào hỏng vì một đoạn.

## 6. Ngân sách chi phí

- Chi phí biên đo được: **0,48 s/đoạn** khi model đã trong VRAM, **0,75 s** khi phải nạp.
- Nếu tỉ lệ đoạn có thuật ngữ vượt **20 %**, in cảnh báo cấp lượt kèm tỉ lệ đo được — vẫn
  chạy, vì chi phí tuyến tính và dự đoán được, nhưng người dùng phải thấy con số.
- Đổi model luân phiên trong VRAM (opus trên CPU, hy-mt trên GPU) **chưa đo**; phải đo trước
  khi coi con số 17,09 s là đại diện.

## 7. Test phải có (không model, không mạng)

1. Đoạn có thuật ngữ ⇒ gọi engine dự phòng đúng một lần, chỉ cho đoạn đó.
2. Đoạn không có thuật ngữ ⇒ **byte-identical** với đường hiện tại (không gọi dự phòng lần nào).
3. Engine dự phòng lỗi ⇒ giữ đầu ra engine nền, cờ `hybrid_fallback`, không ném.
4. Engine dự phòng không `available` ⇒ không chạy hybrid, cờ `engine_no_glossary` như cũ.
5. `i`/`start`/`end`/`words` không đổi sau khi thay `text`.
6. Đoạn rỗng nguồn ⇒ vẫn kích hoạt (nếu có) và không mất đoạn.

## 8. Nghiệm thu (khi triển khai)

Trên clip 115 đoạn, 5 thuật ngữ, cùng harness đã dùng cho spike:

- rendering glossary có mặt **7/7** đoạn (hiện 0/7 với opus một mình);
- echo **0**, `token_lost` **0**;
- thời gian cả clip **≤ 20 s**;
- 108 đoạn không có thuật ngữ **byte-identical** với opus;
- `cps:`/`length:` **không tăng** so với hôm nay;
- toàn bộ test cũ xanh, không đổi `default_mt`.

## 9. Không nằm trong phạm vi

Không sửa prompt, không đổi cỡ lô, không thêm engine mới, không đụng `PROMPT_VERSION`, không
đổi schema DB, không thay `default_mt` trong đợt này.
