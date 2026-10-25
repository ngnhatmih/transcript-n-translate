# Spike: dịch qua một endpoint OpenAI-compatible (không phải đường ship)

**Câu hỏi.** Cổng kiểu `whalegate` (biến phiên `chat.deepseek.com` thành
`/v1/chat/completions`) hoặc một API chính thức có dùng được làm **engine dịch** của
`phu-de-lab` không — cụ thể: nó có giữ được **hợp đồng JSON** (đúng số mục, đúng `id`,
không rỗng) mà đường dịch đang dựa vào, và giá phải trả là gì?

**Cách đo.** `backend/scripts/spike_openai_mt.py` dựng một engine tối thiểu nói giao thức
OpenAI và cắm vào **`TranslateHandler` của sản phẩm** (cùng batching, cùng
`parse_batch_response`, cùng retry alignment, cùng QA), với `engine_capabilities={}` — tức
engine **không** khai `echo_guard`/`term_placeholder`/`name_patch`. Không sửa
`registry.json`, không đổi `default_mt`, không thêm capability nào.

**Đã chạy trên cái gì.** Chưa có gateway: `whalegate` **không được cài** (`~/.whalegate`
không tồn tại, cổng 8790 không mở) và **không có API key** nào trong môi trường. Nên phép
đo chạy trên endpoint OpenAI-compatible **có sẵn** — Ollama `http://127.0.0.1:11434/v1`,
model `hy-mt1.5-7b:q4_K_M`, cùng clip 115 đoạn, cùng 5 thuật ngữ, cùng lô 30. Đây là
**cùng giao thức** mà gateway nói, nên kết quả nói về giao thức, không nói về DeepSeek.

| lượt | `json_mode` | lời gọi | lỗi hợp đồng | nhận được | thời gian | trạng thái |
|---|---|---|---|---|---|---|
| `ollama-v1-hy-mt-b30` | không gửi `response_format` | 33 | **5** | 30/115 | 55,04 s | `failed` |
| `ollama-v1-hy-mt-b30-jsonmode` | `response_format: json_object` | 2 | 0 | 30/115 | 10,67 s | `failed` (HTTP 500) |

Artifact: `data/experiments/accuracy-pipelines/20261025-spike-openai-mt/{ollama-v1-hy-mt-b30,
ollama-v1-hy-mt-b30-jsonmode}.json` (mỗi lời gọi một hàng trong `calls[]`, kèm
`response_head` của lần hỏng).

## Phát hiện: hợp đồng JSON là của **Ollama**, không phải của model

Đường native (`/api/chat` + `format: "json"`) chưa từng hỏng JSON trong suốt các lượt đo
echo, và tài liệu vẫn ngầm hiểu đó là "model làm đúng". Qua `/v1/chat/completions` thì
model trả JSON **hỏng cú pháp** ngay:

- lô 30, lần 1: `Expecting ',' delimiter: line 1 column 1001` — mất dấu phẩy giữa hai mục;
- lô 30, lần 2: `{" translations": ...` (thừa dấu cách) và một mục dùng `"text", "Bản dịch"`
  thay vì `"text": "Bản dịch"`;
- **cỡ 1**: vẫn hỏng — 3 trong 30 lời gọi một mục trả JSON sai cấu trúc
  (`{"translations": [{"i": 30, "text": "..."}}]`, thừa một dấu ngoặc).

Tức ràng buộc decode theo grammar của Ollama mới là thứ giữ hợp đồng; bỏ nó đi thì model
7B viết sai cú pháp ở **cả lô 30 lẫn lô 1**. Một gateway web không có grammar, không nhận
`response_format` (README của `whalegate` ghi rõ: các tham số sampling **không có tương
đương** trên web), nên nó ở đúng vị trí của lượt `json_mode: none` — hỏng hợp đồng.

Lượt có `response_format` sống được lời gọi đầu (30/115 đoạn, 0 lỗi hợp đồng) rồi chết ở
lời gọi thứ hai: HTTP 500 `prediction aborted, token repeat limit reached`. Đây là chế độ
hỏng **đã biết** của `hy-mt` ở lô 30 (native cũng có nhánh "model lặp token, Ollama ngắt"),
không phải bằng chứng `response_format` bị từ chối — nhưng nó cho thấy kể cả khi hợp đồng
JSON được giữ, endpoint này vẫn chết giữa clip.

## Phát hiện phụ: harness đo đúng hiện tượng cũ

Không bật `echo_guard`, lượt lô 30 chép nguyên văn **29/115 đoạn** (175 chữ Hán) — khớp
hiện tượng đã đo trên đường native (29/30 ở lô đầu). Nên script này không phải một dụng cụ
mới cần tin: nó tái tạo đúng lỗi mà cả báo cáo echo đang nói tới.

## Kết luận

**Không dùng được như một engine thay thế trực tiếp.** Ba yêu cầu tối thiểu nếu muốn đi
tiếp, và cả ba đều là việc mới chứ không phải đổi `base_url`:

1. **Bỏ hợp đồng JSON** ở đầu ra: dùng giao thức dễ tha hơn (mỗi đoạn một dòng, tiền tố
   `id`, hoặc parser khoan dung như DSML của `whalegate`) — nếu không, lô 30 sẽ hỏng.
2. **Vẫn phải giữ `echo_guard`**: cỡ 1 cũng có thể chép (đo được ở lượt `v3`), và một
   gateway không có grammar cũng không có guard.
3. Chấp nhận **không tái lập được** (không sampling, hành vi web đổi) và **rủi ro ToS**.

Đường đúng vẫn là: cloud thì **API chính thức** (có `response_format` thật, có SLA) — cùng
script này đo được bằng một dòng `--base-url ... --api-key-env ...`; còn offline thì
**hybrid** đã có spec. Spike này **không** đo gì về DeepSeek web, và không được trích dẫn
như thể đã đo.
