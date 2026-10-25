# Dịch máy cục bộ: HY-MT và hiện tượng chép nguyên văn

## 1. Vấn đề

Engine `hy-mt` (Hunyuan-MT 1.5 7B, lượng tử hoá Q4_K_M) dịch Trung → Việt chạy cục bộ,
model chiếm thêm **5232 MiB** so với nền rảnh 1781 MiB ở mức ổn định (tối đa 5477 MiB ở
đỉnh): đỉnh đo được 7258 MiB trên card 8192 MiB (**chừa 934 MiB**), `ollama ps` xác nhận
model chạy **100% GPU**. Trên clip thử 115 đoạn, khi dịch theo lô 30 đoạn, **59–89 đoạn
(389–629 chữ Hán)** được trả về nguyên chữ Trung trong khi hệ thống vẫn ghi trạng thái
`done`. Đây là lỗi im lặng: mọi cổng kiểm tra hiện có (JSON hợp lệ, đúng số mục, id khớp,
không rỗng) đều cho qua, và chỉ có cờ `lang:` ở mức từng đoạn là ghi nhận được — nhưng cờ
không chặn.

## 2. Giải pháp đã giữ: echo guard

Sau mỗi lô, đoạn nào còn chữ Hán ở đầu ra thì được **dịch lại riêng**. Nếu vẫn còn,
hệ thống ném `EchoProblem`, **cả lô hỏng và không ghi `done`** thay vì lưu một bản dịch
là bản chép. Vị từ phát hiện có hai luật: khớp nguyên văn với nguồn, hoặc tỉ lệ chữ Hán
≥ 0,5 trên ký tự không phải khoảng trắng. Cổng chỉ chạy khi nguồn có chữ Hán và đích
không dùng chữ Hán, nên không phạt câu có một chữ Hán dẫn (0,08) hay câu đã thay thuật
ngữ bằng tiếng Việt (0,33). Nó cũng được bật theo capability của từng engine: engine
không khai thì đi đúng đường cũ, từng byte.

Kết quả: **0 echo ở lô 30 và lô 15**. Cái giá là thời gian:

| cấu hình | thời gian | so với `opus-mt` (9,75 s) |
|---|---|---|
| lô 30 + guard | 78,91 – 118,57 s (sáu lượt) | 8,1 – 12,2× |
| lô 15 + guard | 57,72 – 95,42 s (ba lượt) | 5,9 – 9,8× |

Thời gian phụ thuộc **số lời gọi một mục**, cộng nhiễu giữa các lượt: cả sáu lượt lô 30
đều có đúng 89 lời gọi một mục (89 + 0, 89 + 0, 59 + 30, 59 + 30 và hai lượt 89 + 0), vậy
mà thời gian chạy từ 79 đến 119 s. Hai lượt chậm nhất chạy khi máy còn làm việc khác, nên
biên trên phản ánh cả tải hệ thống — đại lượng ổn định giữa các lượt là **số lời gọi**, 
không phải số giây. Lô 15 có ba lượt (57,72 · 92,17 · 95,42 s) nên **không nhanh hơn lô
30**: hai khoảng chồng lấn gần hết, và lượt 57,72 s là ngoại lệ. Khác biệt thật giữa hai cỡ
nằm ở số lời gọi: lô 15 có ít lời gọi dịch lại hơn (29 so với 59–89) nhưng nhiều lời gọi
cấp lô hơn (8 so với 4). Vì vậy `default_mt` vẫn là `opus-mt`; nếu dùng `hy-mt` thì chọn cỡ
lô theo số lời gọi muốn chấp nhận, không phải theo niềm tin rằng lô nhỏ nhanh hơn.

## 3. Ba giả thuyết bị bác bỏ

1. **Model quên chỉ dẫn ở đầu prompt dài.** Đặt câu cấm chép ở cuối prompt, ngay trước
   dữ liệu: số lời gọi 93 → 93, số lần dịch lại 89 → 89. Không đổi gì.
2. **Model chưa được "sưởi", lô đầu bị ảnh hưởng.** Sưởi trong tiến trình, nạp sẵn model
   từ ngoài tiến trình, và dùng lô đầu nhỏ đều không chữa được: có lượt ra 0 lần dịch
   lại rồi lượt sau lại 29; có lượt lô 4 mục sạch nhưng lô 30 mục ngay sau chép 29/30 và
   tổng thời gian lên 114,16 s.
3. **Chia đôi lô bị chép sẽ thoát chế độ chép.** Thoát được (0 echo) nhưng chậm hơn:
   25 lời gọi và 95,72 s (88,67 s ở lượt lặp), so với 93 lời gọi và 78,91 s ở đối chứng
   của **chính lượt chia đôi**, vì tổng số mục-lượt phải dịch là khoảng 250 thay vì 204
   (115 đoạn + 89 lần dịch lại), và mỗi lô bị chép vẫn tốn một lời gọi đầy đủ trước khi
   bị bỏ. Con số 78,85 s ở mục 2 là của lượt đo guard riêng, không phải lượt này.

## 4. Phát hiện chính

Chép nguyên văn là thuộc tính của từng lời gọi: 19/23 lời gọi cỡ 30 bị chép, so với 8/29
ở 15 mục, 0/1 ở 10 mục (đuôi clip của lượt lô 15), 1/2 ở 8 mục, 0/2 ở 4 mục và 0/7 ở lời
gọi một mục. Các hàng cỡ nhỏ có n rất nhỏ, và nhiều lời gọi trong số đó chỉ phát sinh sau
khi lô cha bị chép, nên bảng cho thấy xu hướng, không cho phép xếp thứ tự giữa các cỡ.
Echo ở cỡ 15 không phải hiện tượng của lô đầu: lô thứ năm giữa lượt cũng chép 15/15, và cả
hai lượt lặp lại giống hệt nhau từng dòng.
Khi một lời gọi bị chép thì bị chép gần như toàn bộ: mọi lô bị chép ở cỡ 30 đều có số đoạn
bị chép là **29/30 hoặc 30/30**; riêng lượt đối chứng là 89 trong 115 đoạn của clip. Con
số "29/30" ban đầu thực chất là 30 trừ đoạn chỉ có số.

`19/23` gộp **bảy lượt** (sáu lượt chạy thẳng lô 30 và lượt chia đôi), nên số lô bị chép
và số lời gọi bị chép là hai phép đếm khác nhau, không phải mâu thuẫn. Cách phát biểu
không phụ thuộc cách đếm, và nên dùng khi bảo vệ: **cả sáu lượt chạy thẳng lô 30 đều bị
chép ở ít nhất hai lô đầy** (số lô bị chép mỗi lượt: 3, 2, 3, 2, 3, 3).

| cỡ lời gọi | bị chép | n |
|---|---|---|
| 30 | 19 | 23 |
| 25 | 0 | 6 — lời gọi đuôi của lượt chia đôi không có `attempts` |
| 15 | 8 | 29 |
| 10 | 0 | 1 |
| 8 | 1 | 2 |
| 4 | 0 | 2 |
| 1 | 0 | 7 |

Bỏ lượt `vram-sample` khỏi bảng thì cỡ 30 là **17/19** và kết luận không đổi — kết quả
không phụ thuộc lượt đo có bản ghi mơ hồ. Cỡ 30 có 23 chứ không phải 24 là đúng số học
của các lượt đó: một lượt có 94 lời gọi = 5 lời gọi cấp lô (bốn cỡ 30 gồm ba lô gốc và
một lần gửi lại cả lô sau lệch alignment, cộng một lô cuối 25 mục) + 29 và 30 lời gọi dịch
lại do echo + 30 lời gọi dịch lại do lệch alignment. Các bản ghi `echoed = 0` kèm 30 lời
gọi một mục là **pha alignment**, không phải trường bị ghi sai: đó là lời gọi cỡ 30 thật
và sạch. Cỡ 25 có 6 chứ không phải 7 vì lượt chia đôi có lời gọi đuôi 25 mục nhưng không
lưu danh sách lần gọi.

Bảng chỉ dùng mười artifact có bản ghi từng lời gọi và **chỉ đếm lời gọi cấp lô** (lô gốc,
lần gửi lại, và lần chia); các lời gọi một mục do echo chỉ được tính khi bản ghi có danh
sách (lượt chia đôi: 7). Vì vậy tổng `n = 70` **không phải** tổng số lời gọi của mười
artifact, vốn là 696. Kết luận thực dụng: cỡ 30 không dùng được nếu thiếu guard; nếu dùng
`hy-mt` thì lô 15 và lô 30 cho thời gian tương đương, khác nhau ở chỗ lô 15 có ít đoạn bị
chép hơn mỗi lần (29 so với 59–89).

## 5. Bài học phương pháp

**Kiểm tra đường cơ sở trước khi đặt mục tiêu.** Mục tiêu ban đầu là "kéo thời gian về
khoảng 33 s", lấy từ một lượt chạy 32,89 s — nhưng đó chính là lượt **chép nguồn, không
dịch gì**. Lượt sạch nhanh nhất đo được là 48,03 s. Mục tiêu bất khả ngay từ đầu.

**Số dẫn xuất phải tính lại từ nguồn, và nguồn phải đúng đơn vị đếm.** Ba con số xuất
hiện trong quá trình viết đều sai cùng một kiểu: một con số mục-lượt (287) không tái lập
được từ artifact; một mẫu số (46) trộn lô gốc với lần thử lại; và một tỉ lệ (5/14) đếm
từ lượt không ghi dữ liệu theo lô. Cả ba đều trông hợp lý. Bài học: chọn đơn vị đếm
trước, rồi mới cộng.

**Một khai báo không có người đọc thì xoá.** Seam "sưởi" và capability `echo_warmup` được
đo, bị từ chối, rồi bị xoá khỏi mã — số đo ở lại tài liệu và artifact. Đây là lần thứ hai
áp dụng cùng nguyên tắc (trước đó là `capabilities.batch_infer`).

## 6. Hướng phát triển

**Hybrid.** `opus-mt` dịch cả lô (9,75 s); chỉ những đoạn bị QA gắn cờ (`lang:`, lệch
glossary) mới chuyển sang `hy-mt` dịch riêng từng câu. Chi phí khi đó tỉ lệ với số đoạn
bị gắn cờ thay vì cả clip, và `hy-mt` chỉ nhận lời gọi ngắn nên tránh hẳn chế độ chép
theo lô. Chưa đo.

**Một ứng viên rẻ chưa bị loại:** chia lô 25/5. Mọi lời gọi 25 mục đo được đều sạch,
nhưng cả hai đều là đuôi clip nên chưa kết luận được; cần một lượt đo với lô 25 mục nằm
giữa clip.

Mọi đòn bẩy rẻ khác đã bị loại bằng số; hybrid là thay đổi kiến trúc nên để sau.

## Phụ lục: nguồn số liệu

| số liệu | nguồn |
|---|---|
| VRAM (đỉnh 7258, ổn định 7013, chừa 934 MiB, 87 mẫu) | `20261019-vram-sample/batch-30.json`, khối `vram`; đỉnh rơi vào pha hạ cấp alignment nên là đỉnh đường xấu nhất; nền rảnh 1781 MiB không phải GPU trống |
| echo 59–89/115, 389–629 chữ Hán; lô 8/15/30 | `20261019-echo-guard/`, `20261019-term-placeholder-clip/sweep/` |
| chi phí lô 30 (78,91 – 118,57 s, sáu lượt) và lô 15 (57,72 – 95,42 s, ba lượt) | `echo-halving/control-batch-30.json`, `vram-sample/batch-30.json`, `echo-batch30-repeat/{run1,run2}`, `echo-batch15-real/{run1,run2}`, `echo-guard/batch-15.json`. Hai thư mục `echo-batch15-repeat/*` có `batch_items = 30` vì driver khi đó **bỏ qua** tham số cỡ lô; lỗi đã được vá kèm bốn test ghim (`test_echo_guard_batches.py`), nên chúng được tính vào lô 30 và `echo-batch15-real/*` mới là lô 15 thật |
| ba giả thuyết (V0–V3, A–E, cây chia) | `20261019-prompt-echo-sweep/`, `20261019-echo-warmup/`, `20261019-echo-halving/` |
| 250 mục-lượt so với 204 | `20261019-echo-halving/halving-batch-30.json`, `attempt_tree[].calls[].items` (225) + lô cuối 25 |
| bảng cỡ lời gọi | tám artifact có `echo_by_batch`: `vram-sample/batch-30`, `echo-halving/{control-batch-30, half-straight-batch-15, halving-batch-30}`, và bốn lượt lặp `echo-batch30-repeat/{run1,run2}` + `echo-batch15-repeat/{run1,run2}`. Ba chỗ dữ liệu không sạch, đã ghi rõ khi đọc bảng: ba lượt (`vram-sample`, `echo-batch30-repeat/run2`, `echo-batch15-repeat/*`) có một bản ghi của **lần gửi lại cả lô** (trường `echoed` ghi 0 và cả 30 mục bị gọi lại một mình = 30 lời gọi cỡ 1 của pha alignment); `halving-batch-30` có lời gọi đuôi 25 mục nhưng **không lưu danh sách lần gọi**; `half-straight-batch-15` có đuôi 10 mục, là hàng `10` trong bảng |
