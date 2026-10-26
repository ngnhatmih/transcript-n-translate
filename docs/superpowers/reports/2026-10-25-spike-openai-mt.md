# Spike: dịch qua một endpoint OpenAI-compatible (không phải đường ship)

**Câu hỏi.** Một endpoint `/v1/chat/completions` — cổng kiểu `whalegate` (biến phiên
`chat.deepseek.com` thành API) hoặc API chính thức — có giữ được **hợp đồng đầu ra** của
đường dịch (đúng số mục, đúng `id`, không rỗng) không, và giá phải trả là gì?

**Cách đo.** Adapter `app/adapters/mt/openai_chat_mt.py` (mã sản phẩm, chưa khai trong
`registry.json`) cắm vào **`TranslateHandler` của sản phẩm** — cùng batching, cùng retry
alignment, cùng QA — với `engine_capabilities={}`, tức engine **không** khai `echo_guard`/
`term_placeholder`/`name_patch`. Driver: `scripts/spike_openai_mt.py`. Không sửa
`registry.json`, không đổi `default_mt`.

**Chạy trên cái gì.** Chưa có gateway: `whalegate` **không được cài** (`~/.whalegate` không
tồn tại, cổng 8790 không mở) và **không có API key** nào trong môi trường. Nên phép đo
chạy trên endpoint OpenAI-compatible **có sẵn** — Ollama `http://127.0.0.1:11434/v1`, model
`hy-mt1.5-7b:q4_K_M`, cùng clip 115 đoạn, cùng 5 thuật ngữ. Đây là **cùng giao thức** mà
gateway nói, nên kết quả nói về giao thức, **không** nói về DeepSeek.

| hợp đồng | lô | lời gọi | lỗi | nhận được | giây | chữ Hán còn | echo | thuật ngữ |
|---|---|---|---|---|---|---|---|---|
| `json` | 30 | 32 | 14 (`other`) | **0/115** `failed` | 49,11 | – | – | – |
| `json` | 30 (bản đầu, engine trong script) | 33 | 5 (`other`) | 30/115 `failed` | 55,04 | 175 | 29 | 0/2 |
| `lines` | 30 | 67 | 5 (`alignment`) | **115/115** `done` | 99,34 | 0 | 0 | 6/7 |
| `lines` | 15 | 25 | 3 (`alignment`) | **115/115** `done` | **59,09** | 0 | 0 | **7/7** |

Artifact: `data/experiments/accuracy-pipelines/20261025-spike-openai-mt/` (mỗi lời gọi một
hàng trong `calls[]`, có `kind` = `alignment` / `http` / `other`).

## 1. Hợp đồng JSON là của **Ollama**, không phải của model

Đường native (`/api/chat` + `format: "json"`) chưa từng hỏng JSON trong suốt các lượt đo
echo. Qua `/v1` (không có `format: "json"`) thì model 7B viết **sai cú pháp** ngay: mất dấu
phẩy giữa hai mục, `{" translations"` thừa dấu cách, `"text", "..."` thay vì `"text": "..."`,
và có lần `Unterminated string`. Hỏng ở lô 30 **và** ở lô 1 (3/30 lời gọi). Hai lượt `json`
đều kết thúc `failed` với 0–30/115 đoạn.

Ràng buộc decode theo grammar của Ollama là thứ giữ hợp đồng. Cổng web không có nó, và
README của `whalegate` ghi rõ `temperature`/`top_p`/`max_tokens`/`stop`/`response_format`
**không có tương đương** — nên cổng nằm đúng chỗ của lượt `json` ở trên.

## 2. Đổi hợp đồng sang `lines`: hỏng theo kiểu KHÁC, và kiểu đó thì cứu được

Hợp đồng `lines` (mỗi dòng `<i>` TAB `<bản dịch>`) không có ngoặc, không có dấu phẩy, nên
những lỗi trên không tồn tại. Cái còn lại là **lệch số dòng**: model trả 29/30 hoặc 2/30.
`parse_lines_response` ném `AlignmentProblem`, handler thử lại rồi hạ cấp từng mục — và
clip đi hết: **115/115 `done`**, 0 chữ Hán, **0 echo**, thuật ngữ 6/7 (lô 30) và 7/7 (lô 15).

Đây là điểm quan trọng nhất của spike, và nó là một **phẩm chất**, không phải một sự tiện:

* hợp đồng JSON ở lô 30 hỏng **im lặng** — model **chép nguyên văn** cả lô (29/115 đoạn,
  175 chữ Hán) trong khi trạng thái vẫn có thể là `done`; phải có `echo_guard` mới bắt được;
* hợp đồng `lines` hỏng **ồn** — thiếu dòng là `AlignmentProblem`, handler thấy ngay.

Vì vậy "không đo được" ồn hơn "đo sai": cùng một model, cùng lô, hai hợp đồng cho hai kiểu
thất bại, và chỉ một kiểu tự báo.

## 3. Giá

`lines` lô 15: **59,09 s / 25 lời gọi**, so với đường native lô 15 có guard (57,72–95,42 s,
37 lời gọi) và lô 30 có guard (77,86–118,57 s, 93–96 lời gọi) — tức ngang lượt native tốt
nhất, ít lời gọi hơn, và **không cần guard** vì không có bản chép nào.

Lô 30 rẻ hơn về số lời gọi lý thuyết nhưng đắt hơn trên thực tế (99,34 s / 67) vì 3 lô hỏng
alignment rồi hạ cấp: **cỡ lô 15 là điểm làm việc** của hợp đồng này trên clip này.

## 4. Harness đo đúng hiện tượng cũ

Lượt `json` không guard chép **29/115 đoạn** — khớp hiện tượng đã đo trên đường native
(29/30 ở lô đầu). Nên dụng cụ này không phải một dụng cụ mới cần tin: nó tái tạo đúng lỗi
mà cả báo cáo echo đang nói tới.

## Kết luận

* **Adapter OpenAI-compatible là khả thi** và đã có trong mã (`openai_chat_mt.py`,
  `parse_lines_response`, 41 bài ghim). Nó **chưa** được khai trong `registry.json`: chưa có
  số đo trên endpoint thật (gateway hay API chính thức), và một engine chưa đo thì chưa khai.
* **Hợp đồng `lines` là đường đi cho endpoint không có grammar.** Không cần bỏ JSON cho
  đường Ollama (đường đó đang tốt) — mỗi engine khai hợp đồng của nó.
* **`echo_guard` vẫn phải giữ** cho engine dùng hợp đồng `json`; với `lines` thì trên clip
  này không cần, nhưng đó là kết luận của **một clip**, không phải một bảo đảm.
* Gateway `whalegate` vẫn **không** phải đường cho sản phẩm: ToS, không tái lập được, và
  `response_format` không tồn tại. Nếu cần chất lượng cloud thì API chính thức, cùng script
  này, một dòng `--base-url/--api-key-env`.
* Spike này **không** đo gì về DeepSeek web, và không được trích dẫn như thể đã đo.

---

## Phụ lục 2026-10-26 — ĐO TRÊN ENDPOINT THẬT (`whalegate`, model `deepseek-web`)

Endpoint thật giờ đã có trên máy này: `whalegate serve` ở `http://127.0.0.1:8790/v1` (model
`deepseek-web`, tài khoản đã đăng nhập). Chạy lại CHÍNH script này — cùng clip 115 đoạn, cùng 5
thuật ngữ, cùng `TranslateHandler` của sản phẩm:

| hợp đồng | lô | giây | lời gọi | lỗi alignment | nhận được | chữ Hán | echo | thuật ngữ |
|---|---|---|---|---|---|---|---|---|
| `lines` | 30 | **13,21** | **4** | 0 | **115/115** `done` | 0 | 0 | 7/7 |
| `lines` | 15 | 33,64 | 8 | 0 | 115/115 `done` | 0 | 0 | 7/7 |
| `json` + `response_format: {"type":"json_object"}` | 15 | 19,41 | 8 | 0 | 115/115 `done` | 0 | 0 | 7/7 |

Artifact: `data/experiments/accuracy-pipelines/20261026-spike-deepseek-web/`.

### 🔴 ĐÍNH CHÍNH mục 1: `response_format` CÓ tồn tại ở cổng này

Mục 1 ở trên viết `response_format` "không có tương đương" ở cổng web (theo README của
`whalegate` lúc viết). **Đo lại thì sai**: gửi `response_format: {"type": "json_object"}` ⇒
**HTTP 200** và body là JSON hợp lệ; cả một lượt `json` 115 đoạn / 8 lời gọi **không một lỗi cú
pháp nào**. Nhưng kết luận "chọn hợp đồng theo endpoint" **không đổi**: thứ bảo đảm JSON ở đây
không phải một grammar bị ghim như `format: "json"` của Ollama, mà là hành vi của một model lớn
hơn; **một lượt xanh không phải một bảo đảm**, và kiểu hỏng của `json` vẫn là kiểu IM (chép
nguyên chữ nguồn với số mục vẫn khớp).

### Hệ quả — hợp đồng được chọn cho hàng registry, và cái giá

`deepseek-web` được khai với `opts.contract: "lines"`: hỏng thì ỒN (`AlignmentProblem`), và lô
30 đo được **4 lời gọi cho 115 đoạn**, tức **không một lần thử lại**. `json` nhanh hơn ở lô 15
(19,41 s so với 33,64 s) nhưng chậm hơn `lines` ở lô 30 (13,21 s) ⇒ trên endpoint này **cỡ lô là
biến quyết định, không phải hợp đồng**.

⚠️ Khi nối hàng đó vào SẢN PHẨM (không phải qua script này) thì một lỗi hình dạng của adapter lộ
ra mà spike không thấy được — xem ERRATA #52: cả 63 bài test của adapter vẫn XANH trong khi mọi
job `translate` chết ở lô đầu. Bài học nằm ở đó, không ở đây.
