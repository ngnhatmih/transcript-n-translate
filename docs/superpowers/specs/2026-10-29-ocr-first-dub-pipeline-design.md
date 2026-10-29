# Pipeline lồng tiếng lấy OCR làm gốc

Ngày: 2026-10-29
Nhánh: `thu-nghiem-tach-giong`
Trạng thái: chờ người dùng duyệt

## 1. Mục tiêu

Thay nguồn chữ của pipeline lồng tiếng: **OCR phụ đề cứng là nguồn chính**, ASR là phụ trợ khi
có. Giữ nguyên khâu dịch (đã có), thay khâu sinh tiếng và khâu ghép video.

Ba yêu cầu cứng, theo thứ tự ưu tiên do người dùng chốt:

1. **Không bao giờ chồng lấn.** Giọng lồng tiếng của câu trước không được còn đang nói khi câu
   sau bắt đầu. Đây là điều kiện ĐÚNG/SAI, không phải thẩm mỹ.
2. **Điểm bắt đầu trùng mốc gốc.** Mỗi dòng vào đúng `start` của nó.
3. **Tốc độ gần đều.** Là MONG MUỐN, không phải ràng buộc. Bỏ được thì tốt, không bỏ được thì
   nén cục bộ. **Không cắt chữ để đổi lấy tốc độ.**

Ngoài ra: pipeline phải chạy được **khi không có ASR** (người dùng chọn A).

## 2. Hiện trạng đo được (số thật trên máy này)

Video thử: `/data/media/ac5df767b9e0c878.mp4`, 1249,237 s, 1280x720, tiếng Trung, có phụ đề
cứng.

| Hạng mục | Số đo | Ghi chú |
|---|---|---|
| OCR toàn video, 2 fps | 696 dòng / 4741 ký tự / 372,8 s | `rapidocr-onnxruntime 1.4.4` |
| OCR sau lọc 3 tầng | 627 dòng / 4434 ký tự | bỏ 69 dòng (10 %) |
| Độ phủ phụ đề | 60,52 % (756,0 / 1249,2 s) | 87 khoảng lặng > 1 s |
| Dải `y` phụ đề | `[627, 682]` trên 720 = `0,87H..0,95H` | đo trên 6 khung |
| Dải `y` watermark/logo | `[0, 70]` | không chồng dải phụ đề |
| ASR `large-v3` bản gốc | 451 đoạn / 3912 ký tự, dừng ở **1186,4 s** | thiếu 62,8 s cuối |
| ASR word-level | `words[].s/.e` chính xác ~0,1 s | có sẵn trong transcript |
| Mốc OCR ở 2 fps | ±0,5 s | giới hạn bởi tần số lấy mẫu |
| `htdemucs` toàn video | 39 s | RTF 0,0249 |
| BS-RoFormer-1296 toàn video | ~9,3 phút | RTF 0,448 — **đã loại, chỉ dùng demucs** |

## 3. Phần A — Phát hiện phụ đề

### 3.1 Port mới

`ocr` là một **port**, cùng khuôn với `ports/asr.py` (Protocol + `engine_id` + một hàm + `release`).
Nó không phải một bước chèn trong `pipeline/`, vì có nhiều engine như ASR có nhiều engine.

```
backend/app/ports/ocr.py          # Protocol OCREngine
backend/app/adapters/ocr_rapidocr.py
backend/app/domain/models.py      # thêm dataclass riêng cho kết quả OCR
registry.json                     # thêm nhóm "ocr" với một entry
```

Chữ ký đề xuất, bám sát `ASREngine`:

```python
class OCREngine(Protocol):
    engine_id: str

    def doc_phu_de(self, video_path: str, *, fps: float = 2.0) -> list[Segment]:
        ...

    def release(self) -> None:
        """Giải phóng VRAM/RAM. Phải an toàn khi gọi nhiều lần."""
        ...
```

Trả `list[Segment]` để dùng lại được toàn bộ hạ tầng hiện có (`Segment` đã có `i/start/end/text`,
và `words` để trống). Đây là quyết định có chủ ý: OCR và ASR khác nhau ở **cách lấy**, không khác
ở **hình dạng dữ liệu**, nên mọi thứ sau đó không phải phân nhánh.

### 3.2 Bốn tầng lọc

Chạy tuần tự. Tầng 1–3 **không cần ASR**; tầng 4 tuỳ chọn.

**Tầng 1 — hộp bao theo tỉ lệ.** Lấy mẫu 50 khung rải đều, OCR, dựng histogram `y` (đỉnh hộp).
Dải nào có mật độ cao và biên độ < 15 % chiều cao khung là dải phụ đề. Dùng tỉ lệ `y/H`, không
dùng pixel, để tự thích ứng 720p/1080p/4K. Không cần người dùng nhập gì.

🔴 Tầng 1 chỉ **tìm dải `y`** trên 50 khung mẫu. Nó KHÔNG lọc dòng. Việc lọc dòng chạy trên
**toàn bộ** khung đã OCR (2 fps toàn video). Hai bước dùng hai tập dữ liệu khác nhau, và số đo
"696 → 627 dòng" ở mục 2 là kết quả của tầng 2–3 trên toàn bộ 696 dòng, không phải trên 50 khung
mẫu.

**Tầng 2 — ổn định theo thời gian.** Phụ đề đứng yên 0,5–2,5 s rồi đổi. Chữ chạy (ví dụ dải danh
lam thắng cảnh đo được ở giây 1056) di chuyển mỗi khung. Loại dòng nếu cùng nội dung xuất hiện ở
`x` khác nhau giữa hai khung liên tiếp.

**Tầng 3 — hình dạng nội dung.** Ba điều kiện, đều đo được từ dữ liệu:
- độ dài 3–40 ký tự (menu giá tiền đo được 200 ký tự)
- không có ≥ 3 cụm số (giá tiền: `24元20元15元`)
- không lặp lại y nguyên liên tiếp

**Tầng 4 (tuỳ chọn) — đối chiếu ASR.** Cửa sổ nào OCR có chữ mà ASR hoàn toàn im lặng thì đánh
dấu nghi vấn. Chỉ bật khi có ASR. Đo được: lọc 3 tầng giữ 696 dòng, thêm tầng 4 còn 627.

### 3.3 Hệ quả của việc chọn A

Vì pipeline phải chạy được khi không có ASR, **tầng 4 mặc định TẮT**. Hệ quả: những dòng như menu
giá tiền nằm đúng dải phụ đề sẽ lọt qua. Đây là đánh đổi đã biết, không phải lỗi. Người dùng bật
tầng 4 bằng một cờ khi muốn sạch hơn và chấp nhận chạy ASR.

## 4. Phần B — Timestamp

### 4.1 Nguyên tắc

**Chữ lấy từ OCR, mốc lấy từ nguồn chính xác nhất đang có.**

| Nguồn | Chữ | Mốc |
|---|---|---|
| OCR 2 fps | chính xác (chữ đã biên tập) | ±0,5 s |
| OCR 4 fps quanh điểm chuyển dòng | chính xác | ±0,25 s |
| ASR word-level (nếu có) | kém hơn | ±0,1 s |

### 4.2 Tăng mốc OCR lên 4 fps — cục bộ, không toàn video

Chạy 2 fps toàn video (đo được 372,8 s). Ở chỗ **chữ vừa đổi**, đọc lại 4 khung quanh mốc đó ở
4 fps. Chi phí thêm ước 15 %, và cho ±0,25 s — đủ cho lồng tiếng, không cần ASR.

Vì sao không 10 fps toàn video: 12 490 khung, ước 31 phút, để đổi ±0,5 s thành ±0,1 s. Không
tương xứng.

### 4.3 Ghép khi có ASR

Căn chỉnh chuỗi giữa danh sách OCR và danh sách ASR trên cùng cửa sổ thời gian; mốc lấy từ ASR.
Chỗ ASR không có (sau 1186,4 s) dùng mốc OCR. Phần này **tuỳ chọn**, cùng cờ với tầng 4.

## 5. Phần C — Ràng buộc thời gian (phần phải sửa)

### 5.1 Mã hiện có, và chỗ nó trái yêu cầu

`backend/app/pipeline/dub.py` đã có `ke_hoach_toc_do(takes, slots, avails)` với
`avails[i] = start[i+1] - start[i]`, và `need_i = take_i / max(slot_i, avail_i)` — chính là tốc
độ tối thiểu để **không đè dòng sau**. Ràng buộc cứng "không chồng lấn" đã có sẵn.

Hai chỗ trái yêu cầu mới:

**(a) Trần 1,35 cắt `need`.** Dòng 55–58: `need > 1.35` ⇒ gán `1.35` và đưa vào `qua_tran`. Dòng
đó **vẫn chồng lấn** vì 1,35 không đủ, và mã chỉ báo "phải sửa chữ". Người dùng đã nói **không
cắt chữ, chỉnh tốc độ là được** ⇒ phải bỏ trần.

**(b) `rap()` cộng mẫu khi chồng.** Dòng 74 ghi rõ "Take chồng nhau thì CỘNG mẫu". Đó là hành vi
chống mất tiếng, giữ nguyên — nhưng **đầu vào phải không có chồng**, và chỗ bảo đảm là (a).

### 5.2 Thuật toán mới

```
need_i = take_i / max(slot_i, avail_i)        # giữ nguyên
toc_do_i = max(1.0, need_i)                   # BỎ trần, BỎ thang bậc
```

Bỏ cả `tran` lẫn `bac`. Lý do bỏ thang bậc: thang bậc tồn tại để giữ tốc độ "gần đều" — nhưng
khi ràng buộc cứng là không chồng lấn, bậc nhỏ hơn `need` sẽ gây chồng. Và người dùng đã hạ ràng
buộc đều xuống mức mong muốn, nên ưu tiên đúng mức cần.

Kết quả: **phần lớn dòng ở 1,0×** (`need ≤ 1` khi take ngắn hơn khoảng cách), chỉ dòng bị dồn mới
nhanh hơn, và nhanh **đúng mức cần**. Đây thực ra gần "tốc độ bằng nhau" hơn cả cách thang bậc cũ,
vì cách cũ nén cả những dòng không cần.

### 5.2b Trường hợp `avail <= 0` — spec này KHÔNG cứu được bằng tốc độ

Khi `start_{i+1} <= start_i` (hai dòng cùng mốc, hoặc dòng sau bắt đầu trước dòng trước trong
transcript gốc), `max(slot_i, avail_i) = slot_i`, và nén dòng `i` **không** tạo ra chỗ cho nó —
vì dòng sau đã bắt đầu từ trước. Đây không phải vấn đề tốc độ mà là **dữ liệu đầu vào tự mâu
thuẫn**.

Cách xử lý, theo thứ tự:

1. **Phát hiện và báo**, không tự sửa: đếm số cặp có `avail <= 0` trên 438 dòng thật. Nếu bằng 0
   thì trường hợp này không tồn tại trên dữ liệu hiện có, và test chỉ cần khẳng định nó bằng 0.
2. Nếu khác 0: dòng sau bị **đẩy muộn** tới `start_i + take_i/toc_do_i`, và ghi log. Đây là chỗ
   duy nhất được phép phá ràng buộc số 2 (điểm bắt đầu trùng), vì giữ nó sẽ vi phạm ràng buộc số
   1 (không chồng lấn) — mà (1) ưu tiên cao hơn (2).
3. Không bao giờ để `rap()` cộng hai giọng vào nhau ở trường hợp này.

Con số ở bước 1 là một trong ba con số phải đo trước khi lập plan — xem mục 7.

### 5.3 Điều kiện kiểm

Test phải khẳng định, trên toàn bộ 438 dòng thật:

1. **Không cặp dòng liền kề nào chồng:** `start_i + take_i/toc_do_i <= start_{i+1}` với mọi `i`.
   Đây là test chính, và là điều kiện người dùng gọi là "hợp lệ".
2. `toc_do_i >= 1.0` (không bao giờ đọc chậm đi).
3. Số dòng có `toc_do > 1.05` — báo cáo con số, không đặt ngưỡng cứng.
4. `toc_do` lớn nhất — báo cáo để biết có dòng nào bị nén tới mức không nghe được.

### 5.4 Ghi log

Ghi rõ dòng nào có `toc_do > 1.35` (mức mà pipeline cũ coi là không chấp nhận được). Không sửa
gì, chỉ để người dùng biết chỗ nào nên rút gọn bản dịch về sau.

## 6. Phần D — Tách nền và remux

**Tách nền: `htdemucs` — và CHỈ `htdemucs`.** Người dùng chốt: chỉ dùng demucs, không dùng model
tách nào khác. Đo được 39 s cho toàn video 20,8 phút (RTF 0,0249).

Đây là quyết định dứt khoát, không phải mặc định có thể đổi: ba model BS/Mel-RoFormer đã thử
nghiệm (1296, 1297, 1143) đều chạy được trên 8 GB VRAM nhưng **không** được đưa vào pipeline —
chậm hơn 14–18 lần mà lợi ích SDR không chuyển thành chất lượng, và mục đích ở đây chỉ là lấy nền.

**Remux: đã có, đã đo.** `h264` copy + `aac` 192k. Lần đo trước: video 1249,233 s, audio
1249,210 s, peak −0,42 dB. Chỉ thay nguồn audio từ bản dub sạch sang bản trộn nền + dub.

**Trộn:** `nền × 0,9 + dub × 0,9` với `amix normalize=0`. Đo được ba tỉ lệ; `0,9/0,9` cho
peak −0,18 dB (có dự phòng) và RMS −18,87 dB. Tỉ lệ `0,95/0,85` **bị loại** vì peak chạm
0,000000 dB (kẹp cứng).

**Một lỗi đã biết của khâu dub hiện tại:** `dub-4.wav` có peak `0,000000 dB` — bản lồng tiếng
chạm trần ngay từ khâu xuất. Đây là lỗi của `dub.py`, không phải của phép trộn. Spec này **không
sửa** nó (ngoài phạm vi), nhưng ghi lại để không ai đổ lỗi cho khâu remux.

## 7. Phần E — Bốn con số phải đo trước khi lập plan chi tiết

Spec này cố ý **không** chốt bốn con số, vì chưa đo thì chốt là đoán.

1. **`T_tts(1,0)/T_nói` trên 438 dòng thật.** Quyết định bao nhiêu % dòng phải nén. Nếu phần lớn
   dòng phải nén > 1,3× thì "tốc độ gần đều" không còn nghĩa, và phải quay lại bàn về khâu dịch.
2. **A1 thuần (tầng 1–3, không ASR) giữ bao nhiêu dòng.** Đã đo A2 = 627; chưa đo A1.
3. **Mốc OCR 4 fps có đạt ±0,25 s không**, và tốn thêm bao nhiêu phút trên toàn video.
4. **Số cặp dòng có `avail <= 0`** trên 438 dòng thật (mục 5.2b). Nếu bằng 0 thì nhánh xử lý đó
   là phòng xa; nếu khác 0 thì phải biết bao nhiêu dòng sẽ bị đẩy mốc.

## 8. Ngoài phạm vi

- Không sửa khâu dịch (đã có, người dùng nói không cần lo).
- Không sửa lỗi peak `0,000000 dB` của `dub.py`.
- Không dùng model tách nào ngoài `htdemucs` — kể cả BS-RoFormer/Mel-RoFormer đã thử nghiệm.
- Không xử lý video **không có** phụ đề cứng — trường hợp đó vẫn phải dùng ASR, và spec này không
  thiết kế đường đó.
- Không commit gì vào `gd4-tts`; mọi thay đổi ở nhánh `thu-nghiem-tach-giong`.

## 9. Rủi ro đã biết

| Rủi ro | Cách xử lý |
|---|---|
| OCR bắt menu giá tiền nằm đúng dải phụ đề | bật tầng 4 (cần ASR); hoặc chấp nhận, người dùng sửa tay |
| `numpy` trong venv app đã lên 2.2.6 khi cài `rapidocr` | **phải chạy backend test suite trước khi commit** — chưa đo |
| Dòng bị nén mạnh (> 1,5×) nghe không được | ghi log, không tự sửa; người dùng rút gọn bản dịch |
| `rapidocr` không có CUDA (`onnxruntime` CPU) | đã đo 372,8 s cho 20,8 phút — chấp nhận được |
| Model RoFormer tải về chiếm ~2,3 GB trong `/tmp` | không dùng trong pipeline; xoá được bất cứ lúc nào, không nằm trong repo |
