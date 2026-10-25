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

| cấu hình | lượt | thời gian | lời gọi | so với `opus-mt` (9,75 s) |
|---|---|---|---|---|
| lô 30, prompt đang ship | 10 | 77,86 – 118,57 s | 93 – 96 | 8,0 – 12,2× |
| lô 30, prompt thử `v2` | 6 | 48,03 – 103,91 s | 4 – 67 | 4,9 – 10,7× |
| lô 15, prompt đang ship | 4 | 57,72 – 95,42 s | 37 | 5,9 – 9,8× |
| lô 8, prompt đang ship | 1 | 61,00 s | 32 | 6,3× |
| lô 30 chia đôi, prompt đang ship | 2 | 88,67 · 95,72 s | 24 · 25 | 9,1 – 9,8× |

Hai mốc `opus-mt` trong báo cáo là **hai lượt đo khác nhau, không so chéo**: 9,75 s ở bảng này
(`sweep-opus/b30-r2.json`, lô 30, 4 lời gọi) và 11,86 s ở §6 (`hybrid-spike/opus-whole-clip`,
cùng lượt với 5,23 s của `hy-mt`).

Dưới prompt đang ship, **cả mười lượt lô 30 chạy thẳng đều bị chép ít nhất một lô** — hai lượt
chia đôi là hàng riêng, không nằm trong mười lượt này, và chúng cũng bị chép cả 3/3 lô gốc
(`tree_stats.copied_batches = 3`). Nên không lượt lô 30 nào dưới 77,86 s. Lượt lô 30 sạch duy
nhất đo được (48,03 s, 4 lời gọi) dùng prompt thử `v2` và thừa hưởng model **đã nạp sẵn từ
ngoài tiến trình**, nên nó là cận dưới lạc quan.

**Thời gian dao động lớn, nguyên nhân chưa xác định.** Bốn lượt lô 15 có cấu trúc lời gọi
giống hệt nhau — 8 lời gọi cấp lô + 29 lời gọi một mục = 37 — vậy mà đo 57,72 · 59,09 · 92,17
· 95,42 s; mười lượt lô 30 cũng đều 93–96 lời gọi mà chênh 77,86 – 118,57 s. Không có đại
lượng nào trong artifact giải thích được khoảng 35 s đó, nên **không gán nó cho số lần dịch
lại**. Số lời gọi là con số ĐẾM được để so sánh cấu hình; số giây thì không. Vì vậy `default_mt`
vẫn là `opus-mt`; nếu dùng `hy-mt` thì chọn cỡ lô theo số lời gọi muốn chấp nhận, không phải
theo niềm tin rằng lô nhỏ nhanh hơn.

## 3. Ba giả thuyết bị bác bỏ

1. **Model quên chỉ dẫn ở đầu prompt dài.** Đặt câu cấm chép ở cuối prompt, ngay trước
   dữ liệu: số lời gọi 93 → 93, số lần dịch lại 89 → 89. Không đổi gì.
2. **Model chưa được "sưởi", lô đầu bị ảnh hưởng.** Sưởi trong tiến trình, nạp sẵn model
   từ ngoài tiến trình, và dùng lô đầu nhỏ đều không chữa được: có lượt ra 0 lần dịch
   lại rồi lượt sau lại 29; có lượt lô 4 mục sạch nhưng lô 30 mục ngay sau chép 29/30 và
   tổng thời gian lên 114,16 s.
3. **Chia đôi lô bị chép sẽ thoát chế độ chép.** Đầu ra cuối **sạch**: 115/115 `done`, 0
   chữ Hán, `echo_segments_guard = 0` — cùng phép đo với đối chứng, đo trên **bản dịch đã
   nhận**, không phải trên cổng. (Cột `echoed` của lượt này không dùng được: cổng bị tắt, xem
   §4.) Nhưng nó chậm hơn: 25 lời gọi và 95,72 s (88,67 s ở lượt lặp), so với 93 lời gọi và
   78,91 s ở đối chứng của **chính lượt chia đôi**, vì tổng số mục-lượt phải dịch là khoảng
   250 thay vì 204 (115 đoạn + 89 lần dịch lại), và mỗi lô bị chép vẫn tốn một lời gọi đầy
   đủ trước khi bị bỏ. Lượt 78,85 s ở bảng trên là lượt guard riêng, không phải lượt chia đôi.

## 4. Phát hiện chính

**Chép là chuyện của cả lô, không phải của từng mục.** Mỗi lời gọi mang nhiều hơn một mục là
một hàng trong `echo_by_batch` của driver. Dưới đây là **toàn bộ** 93 hàng của 18 lượt đi
qua cổng — không chọn mẫu; hai lượt tắt cổng và ba lượt không có bảng được nói ở dưới — và
các hàng được gộp theo **lô gốc của clip** (cùng danh sách `ids`), vì một lô có thể bị gọi
lại: 86 lô (61 prompt đang ship + 25 prompt thử). Tách theo prompt vì hai prompt trả lời hai
câu hỏi khác nhau:

| cỡ lô gốc | bị chép (prompt đang ship) | n | bị chép (prompt thử `v2`) | n |
|---|---|---|---|---|
| 30 | 23 | 27 | 3 | 18 |
| 25 — luôn là đuôi clip | 0 | 8 | 0 | 5 |
| 21 — đuôi clip | 0 | 1 | 0 | 1 |
| 15 | 6 | 21 | — | — |
| 10 — đuôi clip | 0 | 3 | — | — |
| 4 — lô đầu của lượt D | 0 | 1 | 0 | 1 |

Ở prompt đang ship: **23/27 lô 30 mục bị chép** (85%), 6/21 ở 15 mục (29%), và **0/13** ở mọi
cỡ còn lại — bốn lô 30 mục sạch duy nhất nằm trong ba lượt (85,49 · 95,25 · 114,16 s: một lô
mỗi lượt, riêng lượt 114,16 s có hai). Prompt `v2` (biến thể của lượt sưởi, không ship) chỉ
chép 3/18 lô 30 mục, nên gộp hai prompt vào một ô sẽ làm nhẹ đi hiện tượng ở prompt đang ship.

**Chép cả lô, không phải một tỉ lệ.** Không có lô nào ở mức "chép một nửa": cả 26 lô bị chép ở
cỡ 30 (23 + 3) trả về **29/30 hoặc 30/30**, và 6 lô bị chép ở cỡ 15 trả về **14/15 hoặc
15/15**. Đoạn không bị chép luôn là cùng một đoạn — đoạn 9, nguồn `2288`, chỉ có số nên không
có chữ Hán. Vì vậy "29" không phải con số đặc biệt: nó là 30 trừ đúng đoạn không có chữ Hán.

**Cỡ lô và vị trí bị lẫn nhau trên một clip — nhưng không hoàn toàn.** Ba lượt lô 15 (59,09 ·
92,17 · 95,42 s) chép **đúng hai cửa sổ giống hệt nhau** ở cả ba lượt: `0–14` (14/15) và
`60–74` (15/15), không phải cửa sổ nào khác — nên ở cỡ 15 thì nội dung/vị trí quyết định chứ
không phải cỡ. Nhưng phép thử tự nhiên lại nói ngược lại ở cỡ 30: lô `30–59` có nội dung
đúng bằng hai cửa sổ `30–44` và `45–59` (sạch ở cả ba lượt lô 15), vậy mà **6 trong 9 lượt lô
30** vẫn chép cả lô đó. Cùng nội dung, sạch ở 15 mục, bị chép ở 30 mục ⇒ **cỡ lô cũng là biến
số thật**, và trên một clip thì hai biến này không tách được. Vì vậy 6/21 ở bảng trên đọc là
"sáu cửa sổ 15 mục ở đúng hai vị trí đó", không phải "cỡ 15 an toàn hơn".

**Vì vậy không có cỡ lô nào an toàn.** Cỡ 30 hỏng 85% lô, cỡ 15 hỏng 29%, và cỡ 1 cũng không
miễn nhiễm: một lượt (`v3`, 32,92 s) chết vì `EchoProblem` khi đoạn 7 **vẫn** là bản chép sau
khi đã dịch riêng. Cổng không phụ thuộc cỡ lô vì thế.

**Ba lượt không có bảng theo lô.** `20261019-echo-guard/` chạy trước khi driver ghi
`echo_by_batch`, nên chúng chỉ đóng góp vào bảng chi phí. Riêng `batch-15.json` đo **57,72 s**
có `batch_items = 15` — đúng là lô 15, 8 lời gọi cấp lô + 29 lần dịch lại = 37 lời gọi — nhưng
nó **không** nằm trong bảng trên, vì artifact của nó không có bảng theo lô.

**Hai lượt chia đôi cũng không nằm trong bảng.** Driver của chúng tắt cổng cho lô bị chép
(chia thay vì dịch lại), nên cả 35 hàng đều ghi `echoed = 0` dù **cả ba** lô gốc thật sự bị
chép (`tree_stats.copied_batches = 3`). Đếm chúng vào bảng sẽ báo "sạch" cho những lời gọi
không sạch — đây là chỗ một bảng trộn hai dụng cụ đo sẽ sai mà không ai thấy.

Kết luận thực dụng: cỡ 30 không dùng được nếu thiếu guard; nếu dùng `hy-mt` thì hai cỡ
chồng lấn về thời gian (57,72–95,42 so với 77,86–118,57 s), khác nhau ở chỗ lô 15 có ít đoạn
bị chép hơn mỗi lần (29 so với 59–89).

## 5. Bài học phương pháp

**Kiểm tra đường cơ sở trước khi đặt mục tiêu.** Mục tiêu ban đầu là "kéo thời gian về
khoảng 33 s", lấy từ hai lượt chạy **32,84 và 32,89 s** — nhưng cả hai đều **chép nguồn**:
4 lời gọi, trạng thái `done`, **89/115 đoạn vẫn là chữ Trung** (67 đoạn trùng khít nguồn),
629 chữ Hán. 32,89 s là thời gian của một lượt không dịch. Lượt sạch nhanh nhất đo được là
48,03 s (prompt thử, model nạp sẵn), còn dưới prompt đang ship thì lượt lô 30 rẻ nhất là
77,86 s. Mục tiêu bất khả ngay từ đầu.

**Số dẫn xuất phải tính lại từ nguồn, và nguồn phải đúng đơn vị đếm.** Ba con số xuất
hiện trong quá trình viết đều sai, và cả ba đều trông hợp lý: một con số mục-lượt (287)
không tái lập được từ cây chia (đúng là **250** = 225 + lô cuối 25); một mẫu số (46) trộn
lô gốc với lần thử lại; và một tỉ lệ (5/14) cộng sai một ô của cây chia (2/6 nửa bị chép
ghi thành 3/6, đúng là **4/14**). Bài học: chọn đơn vị đếm trước, rồi mới cộng — và cộng
lại từ artifact, không từ trí nhớ.

**Một khai báo không có người đọc thì xoá.** Seam "sưởi" và capability `echo_warmup` được
đo, bị từ chối, rồi bị xoá khỏi mã — số đo ở lại tài liệu và artifact. Đây là lần thứ hai
áp dụng cùng nguyên tắc (trước đó là `capabilities.batch_infer`).

## 6. Hướng phát triển

**Hybrid — spike MỘT clip, n = 7 đoạn.** `opus-mt` dịch cả clip (11,86 s); đoạn nào **chứa
thuật ngữ đã duyệt** thì chuyển sang `hy-mt` dịch riêng từng câu. Trên clip đó: 7/115 đoạn
(6,1%), 7 lời gọi một mục của `hy-mt` mất 5,23 s — tổng **17,09 s**, tức 1,4× `opus-mt` một
mình và rẻ hơn **2,8×** so với lượt `hy-mt` cả lô nhanh nhất (48,03 s), **3,4–6,9×** so với các
lượt còn lại (57,72–118,57 s). Cả 7 câu ra đúng thuật ngữ (0/7 → **7/7**), nhưng **n = 7 là
tín hiệu, không phải kết quả**: 7 đoạn đó được chọn CHÍNH VÌ chứa thuật ngữ, nên mức 0/7 của
`opus-mt` gần như có sẵn từ cách chọn, và chưa nói được gì cho clip khác. Điều kiện kích hoạt
phải là **sự có mặt của thuật ngữ**, không phải một cờ QA: `missing_term` chỉ nổi lên khi phép
dò thuật ngữ được bật, còn `cps:`/`length:` là lỗi hình dạng nên không được dùng làm điều kiện.
Hybrid **vẫn phải giữ echo guard** cho các lời gọi `hy-mt` một mục: §4 cho thấy cỡ 1 không
miễn nhiễm (lượt `v3`).

**`fw-large-v3` không phải mặc định, dù CER tốt hơn.** Trọng số trên đĩa **3,13 GB** so với
**1,51 GB** của turbo; cùng phép đo (một tiến trình, gồm nạp model) nó chạy **38,35 s** so với
**12,32 s**, và tuỳ cấu hình decode là 29,88–44,32 s. Máy 8 GB chỉ chừa 934 MiB cho MT, nên
`default_asr` vẫn là `fw-large-v3-turbo`; đổi mặc định là một lượt đo mới, để sau. (Số "~18 s"
từng được nhắc ở đây **không có artifact nào** chống lưng — đã thay bằng số đo.)

**`name_patch` chỉ dùng được trên đường hybrid.** Capability này chỉ `hy-mt` khai, còn
`default_mt` là `opus-mt`, nên nó **chưa từng chạy trên đường sẽ ship**. Ép chạy trên
`opus-mt` (7 câu thử): **3/7 câu dịch xấu đi** — nhưng ví dụ `福州燕台山` cho thấy lỗi nằm ở
**engine dịch** (nguồn đã được sửa đúng thành `烟台山` mà bản dịch vẫn ra "thị trường chứng
khoán, tiểu bang Virginia"), không phải ở phép sửa tên, nên con số này **không nói được gì về
`hy-mt`**. Về thuật ngữ: đọc tay 7 câu thì không câu nào có thuật ngữ đã duyệt, nhưng trường
`hit_after` rỗng ở **cả hai** engine nên nó không phải bằng chứng (rỗng có thể là chưa tính).
Lý do chưa bật là **chưa thử trên đường sẽ chạy**, không phải "đã đo và kém".

**Ứng viên "chia lô 25/5" — ĐÃ ĐO và ĐÃ BỊ LOẠI.** Cả 13 lời gọi 25 mục đo trước đây đều
sạch, nhưng tất cả đều là **đuôi clip** (id 90–114), nên con số đó không nói 25 mục là an
toàn. Lượt đo `20261025-batch-25` (`scripts/measure_batch_25.py`, cùng clip 115 đoạn,
`hy-mt`, `batch_items=25`, **không** `echo_guard`) chia lô 25 mục để đưa lô 25 vào GIỮA clip:

| lô | id | cỡ | vị trí | bị chép |
|---|---|---|---|---|
| 1 | 0–24 | 25 | giữa | **24/25** |
| 2 | 25–49 | 25 | giữa | **25/25** |
| 3 | 50–74 | 25 | giữa | 0/25 |
| 4 | 75–99 | 25 | giữa | 0/25 |
| 5 | 100–114 | 15 | đuôi | 0/15 |

⇒ "25 mục thì sạch" **SAI**. Những lời gọi 25 mục sạch trước đây sạch vì **vị trí/nội
dung** (đuôi clip), không phải vì cỡ — nên chia lô 25/5 **không phải** một đòn bẩy, và
danh sách ứng viên rẻ đóng lại.

Chưa thấy đòn bẩy rẻ nào cho kết quả tốt hơn **trong các lượt đã đo**; hybrid là thay đổi kiến
trúc nên để sau.

## Phụ lục: nguồn số liệu

| số liệu | nguồn |
|---|---|
| VRAM (đỉnh 7258, ổn định 7013, chừa 934 MiB, 87 mẫu) | `20261019-vram-sample/batch-30.json`, khối `vram`; đỉnh rơi vào pha hạ cấp alignment nên là đỉnh đường xấu nhất; nền rảnh 1781 MiB không phải GPU trống |
| echo 59–89/115, 389–629 chữ Hán; lô 8/15/30 | `20261019-echo-guard/`, `20261019-term-placeholder-clip/sweep/b30-r{1,2,3}.json` (r1 59/389 chữ Hán, r2 và r3 89/629, đều `done`) |
| mục tiêu "~33 s" là lượt không dịch | `20261019-term-placeholder-clip/sweep/b30-r2.json` (32,84 s) và `b30-r3.json` (32,89 s): 4 lời gọi, `done`, 89/115 đoạn `vi` còn chữ Trung (67 đoạn trùng khít `zh`), 629 chữ Hán |
| chi phí 23 lượt (bảng ở mục 2) | `echo-guard/{batch-8,batch-15,batch-30}`; `echo-warmup/{config-A,config-B,config-C,config-D,config-E,repeat-C/config-C}` + `echo-warmup/control-v2-{warm-model,warm-model-2,no-warmup}/v2-batch-30`; `echo-halving/{control-batch-30,half-straight-batch-15,halving-batch-30}` + `echo-halving/repeat-halving/halving-batch-30`; `vram-sample/batch-30`; `echo-batch30-repeat/{run1,run2}/config-A`; `echo-batch15-repeat/{run1,run2}/config-A`; `echo-batch15-real/{run1,run2}/config-A`. Đúng 23 tệp, mỗi tệp một tiến trình. Sáu lượt chạy prompt thử `v2` (`echo-warmup/{config-C,config-E,repeat-C/config-C}` và ba lượt `control-v2-*`), còn lại là prompt đang ship. Hai thư mục `echo-batch15-repeat/*` có `batch_items = 30` vì driver khi đó **bỏ qua** tham số cỡ lô; lỗi đã được vá kèm bốn test ghim (`test_echo_guard_batches.py`), nên chúng tính vào lô 30 và `echo-batch15-real/*` mới là lô 15 thật |
| ba giả thuyết (V0–V3, A–E, cây chia) | `20261019-prompt-echo-sweep/` (lượt `v3` 32,92 s: `translation_status = failed`, `accepted_segments = 0`, `error.type = EchoProblem`), `20261019-echo-warmup/`, `20261019-echo-halving/` |
| 250 mục-lượt so với 204 | `20261019-echo-halving/halving-batch-30.json`, tổng `attempt_tree[].calls[].items` = 225 (22 lời gọi) + lô cuối 25 = 250; đối chứng 115 + 89 lần dịch lại = 204 |
| bảng cỡ lô gốc (93 hàng → 86 lô, 18 lượt) | prompt đang ship — 65 hàng → 61 lô, 12 lượt: `echo-warmup/{config-A,config-B,config-D}`, `echo-halving/{control-batch-30,half-straight-batch-15}`, `vram-sample/batch-30`, `echo-batch30-repeat/{run1,run2}/config-A`, `echo-batch15-repeat/{run1,run2}/config-A`, `echo-batch15-real/{run1,run2}/config-A`. Prompt thử `v2` — 28 hàng → 25 lô, 6 lượt: `echo-warmup/{config-C,config-E,repeat-C/config-C}` + `echo-warmup/control-v2-{warm-model,warm-model-2,no-warmup}/v2-batch-30`. Một hàng = một lời gọi `size > 1` (đúng định nghĩa `echo_by_batch`); các hàng **cùng `ids`** là lần gửi lại của cùng một lô (4 hàng ở prompt ship: `config-D` 2, `vram-sample` 1, `batch30-repeat/run2` 1; 3 hàng ở `v2`: `config-E` 2, `repeat-C` 1) nên được gộp — nếu đếm hàng thay vì lô thì mẫu số thành 31/21 và chính là lỗi "trộn lô gốc với lần gửi lại" mà §5 nêu. **Không** dùng hai lượt chia đôi (dụng cụ tắt cổng, `echoed` luôn 0 dù `tree_stats.copied_batches = 3`) và **không** dùng ba lượt `echo-guard/*` (không có bảng theo lô) |
| 25 mục: 0/13 (đuôi) và **2/4 lô giữa clip bị chép** | cùng bảng trên cho 13 lô đuôi; lượt `20261025-batch-25/batch-25.json` (5 lô 25/15 mục, `hy-mt`, không guard): 24/25 và 25/25 bị chép ở lô 1–2, 0/25 ở lô 3–4 |
| vị trí vs cỡ lô | ba lượt lô 15 (`echo-halving/half-straight-batch-15.json`, `echo-batch15-real/{run1,run2}/config-A.json`) cùng chép `ids 0–14` và `ids 60–74`, mọi cửa sổ khác 0 — đọc `echo_by_batch[].ids`/`echoed` của từng lượt. Lô giữa `30–59` (= hai cửa sổ `30–44` + `45–59`, sạch ở cỡ 15) bị chép ở **6/9** lượt lô 30 (`config-A`, `config-B`, `control-batch-30`, `echo-batch30-repeat/run1`, `echo-batch15-repeat/{run1,run2}`); sạch ở `vram-sample`, `echo-batch30-repeat/run2`, và ở `config-D` (lô giữa của lượt này lệch 4 mục vì lô đầu 4 mục) |
| `fw-large-v3` so với turbo | trọng số trên đĩa: `D:\models\hf\models--Systran--faster-whisper-large-v3` 3,13 GB, `models--mobiuslabsgmbh--faster-whisper-large-v3-turbo` 1,51 GB. Thời gian cùng phép đo (một tiến trình, gồm nạp model): 38,35 s so với 12,32 s — `backend/experiments/accuracy_pipelines/README.md`; tuỳ cấu hình decode: 29,88–44,32 s — `20261019-decode-dev-sweep/large-v3-*.json` (`inference_seconds`, không gồm nạp model nên không so trực tiếp với 12,32 s). CER 0,0490 so với 0,0696 trên cùng tham chiếu 84 caption — `references/ocr-caption-reference-v2.md` |
| hybrid 7/115 đoạn (6,1%), 17,09 s, 0/7 → 7/7 thuật ngữ | `20261019-hybrid-spike/hybrid-spike.json`: `definitions.wide` (7 id), `phases.opus_whole_clip` 11,86 s, `phases.hymt_flagged_only` 5,23 s / 7 lời gọi (`cost.hymt_seconds_per_flagged_segment` 0,747), `segments_detail[].vi_hy` cho cả 7 câu. **n = 7 đoạn của một clip** |
| hai mốc `opus-mt`: 9,75 s và 11,86 s | 9,75 s = `20261019-term-placeholder-clip/sweep-opus/b30-r2.json` (lô 30, 4 lời gọi); 11,86 s = `20261019-hybrid-spike/opus-whole-clip/whole-clip.json` (cả clip, 4 lời gọi; lượt lặp `run2` là 12,16 s). Hai lượt khác nhau, không so chéo |
| `name_patch` trên `opus-mt`: 3/7 câu xấu đi | `20261019-name-patch-translation-eval/eval.json`, 7 câu có `vi_before`/`vi_after` cho **cả hai** engine. "3/7" là đọc tay trên 7 cặp của `opus-mt`; `hy-mt` chưa có phép đo tương ứng, và `hit_after` rỗng ở cả hai engine nên **không** dùng trường đó làm bằng chứng |
