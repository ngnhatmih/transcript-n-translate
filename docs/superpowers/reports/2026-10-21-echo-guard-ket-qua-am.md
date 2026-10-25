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

Dưới prompt đang ship, **cả mười lượt lô 30 đều bị chép ít nhất một lô**, nên không lượt nào
dưới 77,86 s. Lượt lô 30 sạch duy nhất đo được (48,03 s, 4 lời gọi) dùng prompt thử `v2` và
thừa hưởng model **đã nạp sẵn từ ngoài tiến trình**, nên nó là cận dưới lạc quan. Lô 15 rẻ
nhất là 57,72 s, thấp hơn 77,86 s, nhưng bốn lượt lô 15 chia thành hai cặp (57,72 · 59,09 s
đầu phiên, 92,17 · 95,42 s cuối phiên), nên chênh lệch không quy được cho cỡ lô; một lượt lô
15 vẫn gọi 37 lời gọi, so với 4 của lượt lô 30 sạch. Số lời gọi là đại lượng so sánh được:
lượt sạch 4 lời gọi, lượt ba lô bị chép 93–96 — nhưng mười lượt cùng 93–96 lời gọi vẫn chênh
**77,86 – 118,57 s**, nên số giây thừa hưởng cả tải máy. Vì vậy `default_mt` vẫn là `opus-mt`;
nếu dùng `hy-mt` thì chọn cỡ lô theo số lời gọi muốn chấp nhận, không phải theo niềm tin rằng
lô nhỏ nhanh hơn.

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
   bị bỏ. Lượt 78,85 s ở bảng trên là lượt guard riêng, không phải lượt chia đôi.

## 4. Phát hiện chính

**Chép là chuyện của cả lời gọi, và nó chép cả lô.** Mỗi lời gọi mang nhiều hơn một mục là
một hàng trong `echo_by_batch` của driver. Dưới đây là **toàn bộ** 93 hàng của 18 lượt đi
qua cổng — không chọn mẫu; hai lượt tắt cổng và ba lượt không có bảng được nói ở dưới —
tách theo prompt vì hai prompt trả lời hai câu hỏi khác nhau:

| cỡ lời gọi | bị chép (prompt đang ship) | n | bị chép (prompt thử `v2`) | n |
|---|---|---|---|---|
| 30 | 23 | 31 | 3 | 21 |
| 25 — luôn là đuôi clip | 0 | 8 | 0 | 5 |
| 21 — đuôi clip | 0 | 1 | 0 | 1 |
| 15 | 6 | 21 | — | — |
| 10 — đuôi clip | 0 | 3 | — | — |
| 4 — lô đầu của lượt D | 0 | 1 | 0 | 1 |

Ở prompt đang ship: **23/31 lời gọi 30 mục bị chép** (74%), 6/21 ở 15 mục (29%), và **0/13**
ở mọi cỡ còn lại — tám lời gọi 30 mục sạch duy nhất nằm gọn trong ba lượt (85,49 · 95,25 ·
114,16 s). Cỡ 25 sạch **không** phải vì 25 nhỏ mà vì nó luôn là đuôi clip (30+30+30+25);
một lô 25 mục nằm giữa clip chưa từng được đo (§6). Prompt `v2` (biến thể của lượt sưởi,
không ship) chỉ chép 3/21 lời gọi 30 mục, nên gộp hai prompt vào một ô sẽ làm nhẹ đi hiện
tượng ở prompt đang ship.

**Chép cả lô, không phải một tỉ lệ.** Không có hàng nào ở mức "chép một nửa": mọi lời gọi bị
chép trả về **29/30 hoặc 30/30** (và 14/15 hoặc 15/15 ở lô 15). Đoạn không bị chép luôn là
cùng một đoạn — đoạn 9, nguồn `2288`, chỉ có số nên không có chữ Hán. Vì vậy "29" không phải
con số đặc biệt: nó là 30 trừ đúng đoạn không có chữ Hán.

**Vì vậy không có cỡ lô nào an toàn.** Cỡ 30 hỏng 74% lời gọi, cỡ 15 hỏng 29%, và cỡ 1 cũng
không miễn nhiễm: một lượt (`v3`, 32,92 s) chết vì `EchoProblem` khi đoạn 7 **vẫn** là bản
chép sau khi đã dịch riêng. Cổng không phụ thuộc cỡ lô vì thế.

**Ba lượt không có bảng theo lô.** `20261019-echo-guard/` chạy trước khi driver ghi
`echo_by_batch`, nên chúng chỉ đóng góp vào bảng chi phí. Riêng `batch-15.json` đo **57,72 s**
có `batch_items = 15` — đúng là lô 15, 8 lời gọi cấp lô + 29 lần dịch lại = 37 lời gọi — nhưng
nó **không** nằm trong bảng trên, vì bảng đó chỉ đếm hàng có thật trong artifact.

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

**Hybrid.** `opus-mt` dịch cả clip (11,86 s); đoạn nào **chứa thuật ngữ đã duyệt** thì chuyển
sang `hy-mt` dịch riêng từng câu. Trên clip: 7/115 đoạn (6,1%), 7 lời gọi một mục của `hy-mt`
mất 5,23 s — tổng **17,09 s**, tức 1,4× `opus-mt` một mình và rẻ hơn **2,8×** so với lượt
`hy-mt` cả lô nhanh nhất (48,03 s), **3,4–6,9×** so với các lượt còn lại (57,72–118,57 s).
Cả 7 câu ra đúng thuật ngữ (0/7 → **7/7**). Điều kiện kích hoạt phải là **sự có mặt của thuật
ngữ**, không phải một cờ QA: `missing_term` chỉ nổi lên khi phép dò thuật ngữ được bật, còn
`cps:`/`length:` là lỗi hình dạng nên không được dùng làm điều kiện.

**`fw-large-v3` không phải mặc định, dù CER trên dev thấp hơn.** Cùng clip, nó cần **3,2 GB
VRAM** so với 1,6 GB của turbo và **~18 s** so với ~12 s. Máy 8 GB chỉ chừa 934 MiB cho MT,
nên `default_asr` vẫn là `fw-large-v3-turbo`; đổi mặc định là một lượt đo mới, để sau.

**`name_patch` chỉ chạy được qua đường hybrid.** Sửa tên riêng từ OCR trước khi dịch chỉ có
tác dụng khi engine nhận capability đó — hiện chỉ `hy-mt` khai, còn `default_mt` là `opus-mt`.
Ép chạy trên `opus-mt` với 7 câu thử: **0 câu** ra thuật ngữ trong glossary và phần lớn câu
**xấu đi** (`福州燕台山` được sửa đúng thành `烟台山` nhưng bản dịch ra "thị trường chứng
khoán, tiểu bang Virginia"). Vì vậy nó chưa bật.

**Một ứng viên rẻ chưa bị loại:** chia lô 25/5. Cả **13** lời gọi 25 mục đo được đều sạch,
nhưng tất cả đều là đuôi clip nên chưa kết luận được; cần một lượt đo với lô 25 mục nằm giữa
clip.

Mọi đòn bẩy rẻ khác đã bị loại bằng số; hybrid là thay đổi kiến trúc nên để sau.

## Phụ lục: nguồn số liệu

| số liệu | nguồn |
|---|---|
| VRAM (đỉnh 7258, ổn định 7013, chừa 934 MiB, 87 mẫu) | `20261019-vram-sample/batch-30.json`, khối `vram`; đỉnh rơi vào pha hạ cấp alignment nên là đỉnh đường xấu nhất; nền rảnh 1781 MiB không phải GPU trống |
| echo 59–89/115, 389–629 chữ Hán; lô 8/15/30 | `20261019-echo-guard/`, `20261019-term-placeholder-clip/sweep/b30-r{1,2,3}.json` (r1 59/389 chữ Hán, r2 và r3 89/629, đều `done`) |
| mục tiêu "~33 s" là lượt không dịch | `20261019-term-placeholder-clip/sweep/b30-r2.json` (32,84 s) và `b30-r3.json` (32,89 s): 4 lời gọi, `done`, 89/115 đoạn `vi` còn chữ Trung (67 đoạn trùng khít `zh`), 629 chữ Hán |
| chi phí 23 lượt (bảng ở mục 2) | `echo-guard/{batch-8,batch-15,batch-30}`; `echo-warmup/{config-A,config-B,config-C,config-D,config-E,repeat-C/config-C}` + `echo-warmup/control-v2-{warm-model,warm-model-2,no-warmup}/v2-batch-30`; `echo-halving/{control-batch-30,half-straight-batch-15,halving-batch-30}` + `echo-halving/repeat-halving/halving-batch-30`; `vram-sample/batch-30`; `echo-batch30-repeat/{run1,run2}/config-A`; `echo-batch15-repeat/{run1,run2}/config-A`; `echo-batch15-real/{run1,run2}/config-A`. Đúng 23 tệp, mỗi tệp một tiến trình. Sáu lượt chạy prompt thử `v2` (`echo-warmup/{config-C,config-E,repeat-C/config-C}` và ba lượt `control-v2-*`), còn lại là prompt đang ship. Hai thư mục `echo-batch15-repeat/*` có `batch_items = 30` vì driver khi đó **bỏ qua** tham số cỡ lô; lỗi đã được vá kèm bốn test ghim (`test_echo_guard_batches.py`), nên chúng tính vào lô 30 và `echo-batch15-real/*` mới là lô 15 thật |
| ba giả thuyết (V0–V3, A–E, cây chia) | `20261019-prompt-echo-sweep/` (lượt `v3` 32,92 s: `translation_status = failed`, `accepted_segments = 0`, `error.type = EchoProblem`), `20261019-echo-warmup/`, `20261019-echo-halving/` |
| 250 mục-lượt so với 204 | `20261019-echo-halving/halving-batch-30.json`, tổng `attempt_tree[].calls[].items` = 225 (22 lời gọi) + lô cuối 25 = 250; đối chứng 115 + 89 lần dịch lại = 204 |
| bảng cỡ lời gọi (93 hàng, 18 lượt) | prompt đang ship — 65 hàng, 12 lượt: `echo-warmup/{config-A,config-B,config-D}`, `echo-halving/{control-batch-30,half-straight-batch-15}`, `vram-sample/batch-30`, `echo-batch30-repeat/{run1,run2}/config-A`, `echo-batch15-repeat/{run1,run2}/config-A`, `echo-batch15-real/{run1,run2}/config-A`. Prompt thử `v2` — 28 hàng, 6 lượt: `echo-warmup/{config-C,config-E,repeat-C/config-C}` + `echo-warmup/control-v2-{warm-model,warm-model-2,no-warmup}/v2-batch-30`. Mỗi hàng là một lời gọi `size > 1`, đúng như `echo_by_batch` định nghĩa. **Không** dùng hai lượt chia đôi (dụng cụ tắt cổng, `echoed` luôn 0 dù `tree_stats.copied_batches = 3`) và **không** dùng ba lượt `echo-guard/*` (không có bảng theo lô) |
| 25 mục sạch 0/13, 15 mục 6/21 | cùng bảng trên; 13 lời gọi 25 mục đều là lô cuối của clip (id 90–114), nên chưa nói được gì về một lô 25 mục nằm giữa clip |
| hybrid 7/115 đoạn (6,1%), 17,09 s, 0/7 → 7/7 thuật ngữ | `20261019-hybrid-spike/hybrid-spike.json`: `definitions.wide` (7 id), `phases.opus_whole_clip` 11,86 s, `phases.hymt_flagged_only` 5,23 s / 7 lời gọi, `segments_detail[].vi_hy` cho cả 7 câu |
