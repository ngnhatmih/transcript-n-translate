# phu-de-lab · backend

## Thử nghiệm pipeline ưu tiên độ chính xác

Các biến thể ASR/dịch thuật và runner so sánh độc lập được mô tả tại
[`experiments/accuracy_pipelines/README.md`](experiments/accuracy_pipelines/README.md).
Chúng không đổi engine mặc định hay API production; kết quả không có reference
chỉ phục vụ review thủ công, không được coi là bằng chứng cải thiện độ chính xác.

## Cài đặt

```powershell
pwsh -File scripts/install.ps1
```

`install.ps1` cài torch cu121 **trước** funasr và **dừng lại** nếu
`torch.cuda.is_available()` trả False — chạy CPU mà không biết là kiểu hỏng tệ nhất.

Script cũng đặt `HF_HOME` và `MODELSCOPE_CACHE` ở **mức User** (mặc định
`D:\models\hf` và `D:\models\hf\modelscope`) để model không rơi vào ổ C:.
`HF_HOME` là **biến môi trường**, không phải hằng số trong `app/config.py`:
`huggingface_hub` đọc nó ngay lúc import. Shell đang mở chưa thấy biến mới —
mở shell mới, hoặc đặt lại trong phiên này:

```powershell
$env:HF_HOME = "D:\models\hf"
$env:MODELSCOPE_CACHE = "D:\models\hf\modelscope"
```

`jieba` (phụ thuộc của `funasr`) chỉ có bản sdist, không có wheel Windows, và pip
treo hàng chục phút ở bước tự dựng build-isolation cho nó. Vì vậy script cài
`setuptools` + `wheel`, rồi cài riêng `jieba` với `--no-build-isolation`, rồi mới
cài phần còn lại. Mọi dòng pip đều dùng `--no-cache-dir` — đọc cache là thứ làm
pip chậm một cách bệnh hoạn trên máy này.

## Chạy

```powershell
.\.venv\Scripts\python.exe run_api.py      # http://127.0.0.1:8620
```

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest                        # toàn bộ, không cần model
.\.venv\Scripts\python.exe -m pytest -m live                # CHẠM model thật (OPUS-MT + Ollama)
.\.venv\Scripts\python.exe scripts\smoke_asr.py clip.mp4 zh # model thật, cần GPU
```

Đừng thêm cờ quiet vào lệnh pytest: `pytest.ini` đã có `addopts = -q`, thêm nữa
là thành chế độ im lặng gấp đôi và **mất dòng "N passed"** — khi đó không ai biết
bao nhiêu test đã chạy.

`pytest.ini` cũng đã có `-m "not live"`, nên lần chạy mặc định **bỏ qua** các bài
chạm model thật trong `tests/test_mt_live.py` và
`tests/test_asr_first_chunk_live.py` (clip thật ~234 s ở `_realpipe`). Đó là chủ ý:
máy chưa tải weight không được đỏ vì lý do không liên quan tới code. Muốn chạy
chúng thì `-m live`, và mỗi lần chạy như vậy là một lần **ĐO** — đừng thay bằng
test giả.

`scripts/smoke_asr.py` **không** thuộc bộ pytest: nó tải model ~1,6 GB và cần
GPU. Nó tự ép UTF-8 cho stdout (console Windows mặc định cp1252, còn script in
tiếng Trung/Việt) và tự đặt cache model trước khi nạp `faster_whisper`.

Con số nền của lần chạy mặc định, đo sau khi xoá `__pycache__` (lệnh ở mục
"Kiểm thử" trên, chạy từ trong `backend\`). Thứ có nghĩa là **1289 / 15**, không
phải số giây — thời gian trôi giữa các lần chạy (đã thấy 24,00–30,94 s) còn con
số bài thì không:

```
1289 passed, 15 deselected, 1 warning
```

Hai con số đó là SỐ BÀI ĐƯỢC CHỌN, và chúng khớp với số mà `--collect-only` báo
(`1289/1304`, 15 bài `live` bị bỏ;
`tests/test_backend_readme.py::test_readme_baseline_matches_the_tests_actually_
collected` đối chiếu mỗi lần chạy).

Máy này **CÓ** `ffmpeg 8.1.1` + `ffprobe` trên PATH (đã đo), nên `1289/15` ở trên
là số THẬT của nó. Máy **không có** `ffmpeg`/`ffprobe` cho một kết quả KHÁC: cả
`tests/test_ingest.py` bị `skipif` ở cấp module — **9** bài cùng skip một lượt —
nên dòng tổng kết của máy đó là **`1280 passed, 9 skipped, 15 deselected`** (=
`1289 − 9`; con số này TỪNG ghi `978`, tức một baseline rất cũ, và nó lệch phép
trừ của chính khối nền ngay trên nó). Đó là
con số của máy thiếu ffmpeg, **không phải** con số máy này từng in ra; đừng chép
nó vào khối nền ở trên, và đừng "sửa" số nền xuống chỉ vì thiếu ffmpeg.

⚠️ Con số `856` ở đây TỪNG không khớp phép trừ của chính nó: `865 − 9 = 856`, tức
nó là số của lượt TRƯỚC `V1` (+3 bài) còn sót lại. Phép trừ của khối nền hiện tại
là `1289 − 9` = `1280`.

(Con số này từng bị ghi là `798`: bài `test_a_failed_translation_leaves_the_
transcript_reviewed` được thêm ở `a428334` — **cùng commit đã sửa tệp này** — mà
số nền không được bump. Nó tồn tại để phát hiện TRÔI, nên một số sai làm mọi lần
chạy báo dương tính giả.

Lần bump này, `1288/15` → `1289/15` (**+1 bài**), do đóng nợ **`N-9`** (route export ghi
tệp trên một `GET`): mặc định `GET /api/export/{translation_id}` chỉ TRẢ nội dung,
`?save=1` mới ghi. Bài mới `test_export_without_save_does_not_touch_the_disk` đo cả hai
vế; bốn bài cũ (đo đường GHI, so tên/byte trên đĩa) nay xin `save=1`. Mutation đã chạy:
bỏ `if save:` ⇒ bài mới ĐỎ.

Lần bump trước, `1286/15` → `1288/15` (**+2 bài**), do đóng nợ **`retry_job` không xoá
`cancel_requested`** (ERRATA #46 mục 9): tầng repo (`test_repos.py`) và tầng HTTP
(`test_api_jobs_sse.py`) mỗi nơi một bài. Mutation đã chạy: bỏ `cancel_requested=0`
⇒ cả hai bài đỏ. Kèm theo, `DEFAULT_MAX_CHARS` nay đã được ÉP bằng lượt đo
`20261025-batch-chars` (mục "Giới hạn" bên dưới) — nợ đó cũng đóng.

Lần bump trước, `1269/15` → `1286/15` (**+17 bài**), do **VRAM hiện thật** ở
`GET /api/status`: `tests/test_status_vram.py` ghim parser (`nvidia-smi` dòng đầu,
số nguyên không âm, chuỗi lạ ⇒ `None`), ba ca lỗi tiến trình (không có binary,
timeout, returncode khác 0 ⇒ `None`, không 500) và hợp đồng HTTP (`vram` là số
hoặc `null`, `vram_unit` LUÔN có). Trước đó route trả `vram: null` CỐ ĐỊNH nên
giao diện luôn in "chưa đo được".

Lần bump trước, `1206/15` → `1269/15` (**+63 bài**), do **hợp đồng đầu ra `lines`**,
adapter OpenAI-compatible, và **nối dây runtime `http`**. `tests/test_mt_lines_contract.py` (**+24**) ghim parser dòng:
đủ số dòng, đúng tập `id`, id trùng, mục có id mà không có bản dịch, và — quan trọng
nhất — một dòng KHÔNG mang id nằm GIỮA khối bản dịch là LỖI chứ không phải lời dẫn bị bỏ
qua (model xuống dòng giữa câu thì bỏ dòng sau là mất nửa câu mà số dòng vẫn "đủ").
`tests/test_mt_openai_chat.py` (**+17**) ghim thân yêu cầu của adapter: `temperature`,
`max_tokens`, `response_format` **không** được gửi trừ khi có yêu cầu rõ ràng (một cổng
web không có tương đương cho chúng), khoá API chỉ đi trong header, và lỗi HTTP phải ném
`HTTPStatusError` chứ không phải `JSONDecodeError`. Số đo của hai hợp đồng nằm trong
`docs/superpowers/reports/2026-10-25-spike-openai-mt.md`. `tests/test_mt_openai_wiring.py`
 (**+22**) ghim phần NỐI DÂY: `available` của engine `http` là câu trả lời thật (endpoint
trả lời, khai đúng `model_ref`, khoá API có trong biến môi trường), hai hàng cùng endpoint
chỉ dò MỘT lần, hàng thiếu `base_url` là "chưa sẵn sàng" chứ không làm sập tiến trình,
còn lúc DỰNG engine thì thiếu `base_url`/khoá là lỗi ồn và `runtime` lạ không được đoán
thành `opus-mt`.

Lần bump gần nhất, `1202/15` → `1206/15` (**+4 bài**), do sửa lỗi **`--batches`
bị `--configs` nuốt**: `main()` của `scripts/smoke_echo_guard.py` tự gán cứng lô
30 cho mọi lượt có `--configs`, nên `--batches 15 --configs A` vẫn gọi engine bằng
lô 30 và ghi `batch_items: 30` — cờ trông như đã chạy mà không chạy, không bài nào
đỏ. `tests/test_echo_guard_batches.py` (**+4**) ghim: `--batches 15` ⇒
`batch_items == 15`; `--batches 15 30` ⇒ hai artifact, mỗi lô một tệp; lượt
`--configs` độc hại cũ nay cũng ra 15; và hai lô trên cùng một cấu hình không ghi
đè nhau (`config-A-batch-15.json` / `config-A-batch-30.json`). Test dùng engine +
handler GIẢ và `_loaded_models` giả, nên không cần model, không cần mạng, không
chạm `nvidia-smi`. Lượt sửa này **không đổi đường ship**: mặc định lô vẫn là 30,
prompt/`PROMPT_VERSION`/registry không chạm.

Trước đó, `1200/15` → `1202/15` (**+2 bài**), do lượt đo **VRAM**:
`tests/test_vram_sample.py` (**+2**) ghim (a) hàm THUẦN `summarize_vram` của
`scripts/smoke_echo_guard.py` — nền phẳng rồi bàn ổn định, một gai đơn lẻ (peak
bắt nó, steady thì không; gai trong NỀN không được đọc thành "đã nạp"), và mảng
rỗng trả `None` chứ không phải `0` — và (b) cờ `--sample-vram` TẮT thì artifact
KHÔNG có khoá `vram` và không chạm `nvidia-smi`. Lượt đo đó **không ship gì**:
cờ mặc định tắt, đường dịch không đổi — xem mục VRAM bên dưới.

Trước đó, `1192/15` → `1200/15` (**+8 bài**), do lượt đo **chia đôi lô bị
chép**: `tests/test_echo_halving.py` (**+8**) ghim phép chia THUẦN
`scripts/echo_halving.py` — lô sạch không chia, lô 30 -> 15/15, nửa đầu nhận mục
lẻ (15 -> 8/7), trần độ sâu hạ xuống từng mục, lô MỘT mục trả về chính nó (không
trả rỗng), trần mặc định sâu hơn 5 tầng mà lô 30 cần, và đường đi TỆ NHẤT từ 1..30
mục không làm mất hay nhân đôi mục nào. Lượt đo đó **không ship gì** — xem mục
echo bên dưới.

Trước đó, `1194/15` → `1192/15` (**−2 bài**), do **xoá seam "sưởi trước
lô đầu"** khỏi `app/pipeline/translate.py`: **−4** bài ghim seam đó bị gỡ cùng nó,
**ba** bài ghim `scripts/smoke_echo_guard.py::echo_by_batch` (kế toán theo lô: echo
của lô nào nằm ở lô đó, một lời gọi một mục đứng TRƯỚC lô đầu không bị tính vào lô
1, và nhãn `phase` tách được lô 4 mục của cấu hình D khỏi một lô 4 mục bình
thường) được GIỮ LẠI — chúng kiểm phép KẾ TOÁN, không kiểm seam, và bảng theo lô
là bằng chứng của cả lượt đo — cộng **+2** bài mới ghim `mt_qa.is_echo` (một con
số giữ nguyên như `2288` -> `2288` KHÔNG phải echo; nguồn Hán chép nguyên văn vẫn
là echo). Seam bị xoá vì nó là ĐƯỜNG CHẾT: cờ capability của nó **chưa từng** được
khai trong `registry.json`, nên không cấu hình nào vào được đường đó — cùng một
lỗi với một khai báo không ai đọc, và repo này đã xoá `capabilities.batch_infer`
đúng theo luật đó. Đường ship không đổi từng byte.

Số đo đứng sau việc **để nó ngoài sản phẩm** vẫn là bảng A–E ngay dưới, và ba giả
thuyết nó bác là: sưởi **không** sửa được v0 (**0/2** lượt — B trùng A đến từng
lô), **lô đầu nhỏ không thay được sưởi** (D: lô 4 mục sạch rồi lô 30 mục ngay sau
đó vẫn chép `29/30`), và **dời chỉ dẫn xuống cuối prompt đổi 0/89 lần dịch lại**
(V1, xem đoạn quét prompt bên dưới). Artifact của lượt đo:
`data/experiments/accuracy-pipelines/20261019-echo-warmup/`.

Lượt đo đó (cùng clip 115 đoạn, cùng 5 thuật ngữ, lô 30, `echo_guard` BẬT, mỗi cấu
hình MỘT TIẾN TRÌNH, `/api/ps` rỗng trước mỗi lượt vì driver `release()` sau lượt
trước; artifact ở `data/experiments/accuracy-pipelines/20261019-echo-warmup/`):

    cấu hình                                              | dịch lại | EchoProblem | echo còn lại | chữ Hán | giây
    A · v0, không sưởi (đối chứng)                        | 89       | 0           | 0            | 0       | 77,86
    B · v0 + một lời gọi sưởi                             | 89       | 0           | 0            | 0       | 79,19
    C · v2 + sưởi                                         | 0 / 29   | 0 / 0       | 0 / 0        | 0 / 0   | 56,90 / 71,48
    D · v0, lô đầu ép còn 4 mục (không sưởi)              | 29       | 0           | 0            | 0       | 114,16
    E · v2, lô đầu ép còn 4 mục (không sưởi)              | 0        | 0           | 0            | 0       | 103,91

Bảng echo THEO LÔ (`echo_by_batch` trong chính artifact) là thứ lượt trước thiếu, và
nó lật đúng chỗ kết luận cũ dễ bị đọc sai. **A** (đối chứng) không dồn echo vào lô
1: cả BA lô đủ 30 mục đều bị chép — `29/30`, `30/30`, `30/30` — và lô 25 mục CUỐI
sạch (`0/25`); **B** ra y hệt A từng lô, tức một lời gọi sưởi KHÔNG đổi gì với v0.
Id bị chép luôn là "mọi segment của lô trừ đoạn 9" (`2288`, số thuần nên
`echoes_source` không tính) ⇒ echo là COPY CẢ LÔ, và con số `29` của lượt trước
không phải một tỉ lệ đặc biệt mà là "30 trừ đoạn không có chữ Hán". **D** tách được
hai giả thuyết: lô 4 mục SẠCH, rồi lô 30 mục NGAY SAU ĐÓ chép `29/30` — rủi ro bám
vào **lô ĐẦU TIÊN ĐỦ 30 MỤC**, không phải "lời gọi đầu"; và hai lô 30 mục sau trả
thiếu mục (22/30, 24/30, 25/30) nên hạ cấp từng segment (60 lời gọi singleton), wall
time **114,16 s** — "lô đầu nhỏ" là một cách chữa ĐẮT và không sửa được gì.

Với **v2**, mọi lô TRỪ lô đầu đều sạch (7/7 lượt của cả hai vòng đo), và lô đầu
chép `29/30` phụ thuộc trạng thái model: model NGUỘI (chưa nạp) ⇒ 3/3 lượt đều
chép; còn khi model đã nạp trước lô đầu — bằng lời gọi sưởi (C) hoặc bằng một lần
nạp SẴN từ ngoài tiến trình (`/api/generate`, không phải một lượt dịch) — thì kết
quả là **0 rồi 29** ở cả hai nhánh. Tức "sưởi" không chữa được: nó đổi một đồng xu
lấy một lời gọi, và wall time KHÔNG về dưới 40 s được: **48,03 s** là lượt sạch
NHANH NHẤT đo được (4 lô, 115 đoạn, engine tự báo 48,0 s — gần như toàn bộ wall
time là sinh token thật), nên con số `~33 s` mà tiêu chí "< 10 lần dịch lại, không
`EchoProblem`, ≤ ~40 s" nhắm tới chính là wall time của một lượt KHÔNG dịch (lượt
chép nguồn ở lô 30 cũ: 32,89 s). Kết luận: không cấu hình nào đạt cả ba tiêu chí;
C và E đạt hai tiêu chí đầu (0 dịch lại, 0 `EchoProblem`) nhưng wall time 56,90 s
và 103,91 s, và C KHÔNG tái lập được (lượt lặp: 29 lần dịch lại) — nên đòn bẩy còn
lại vẫn là kiến trúc hybrid, không phải prompt và không phải sưởi.

Lượt đo **chia đôi lô bị chép** (cùng clip, cùng 5 thuật ngữ, prompt v0,
`echo_guard` BẬT, mỗi cấu hình một tiến trình, `/api/ps` rỗng trước mỗi lượt;
artifact ở `data/experiments/accuracy-pipelines/20261019-echo-halving/`) hỏi thẳng
một câu: khi lô 30 bị chép, VỨT nó và dịch lại thành HAI NỬA có rẻ hơn 89 lời gọi
singleton không. `pipeline/translate.py` KHÔNG bị sửa: driver
`scripts/smoke_echo_halving.py` override `_guard_echoes` để chia đôi, còn
`scripts/echo_halving.py` là phép chia THUẦN (có test, xem mục "Kiểm thử"):

    cấu hình                    | dịch lại 1 mục | tổng lời gọi | lô hỏng | echo còn lại | chữ Hán | giây
    control · lô 30 (đang ship) | 89             | 93           | 0       | 0            | 0       | 78,91
    halving · lô 30, chia đôi   | 7              | 25           | 0       | 0            | 0       | 95,72
    half-straight · lô 15 thẳng | 29             | 37           | 0       | 0            | 0       | 59,09
    (lặp halving)               | 7              | 24           | 0       | 0            | 0       | 88,67

**Đối chứng tái lập đúng** pattern đã ghim (`29/30 -> 30/30 -> 30/30 -> 0/25`, 89
lần dịch lại), nên bốn cột trên so được với nhau. **Chia đôi THOÁT được echo**
(0 echo còn lại, 0 `EchoProblem`, 115/115 `done`), và **7/7** lời gọi một mục của
nó là hạ cấp ALIGNMENT — nửa 7 mục của lô 60–89 trả 6/7 mục HAI lần rồi mới hạ
xuống từng mục — **không** phải cổng echo dịch lại đoạn nào. Nhưng nó **không
rẻ**: 25 lời gọi vẫn trên mục tiêu "< ~20", và wall time 95,72 s tệ hơn đối chứng
vì lượt chia dịch **250 mục-lượt** (tổng số mục của mọi lời gọi, kể cả lô 30 bị
vứt: cây gọi 22 lời / 225 mục, cộng lô cuối 25) so với 204 của đối chứng. Cây chia
giải thích tại sao (`repeat-halving/` lặp lại y hệt): các NỬA cũng bị chép — ở 15
mục **4/14** lô (2/8 lô của lượt 15 thẳng + 2/6 nửa của lượt chia), ở 8 mục 1/2, ở
4 mục 0/2 — nên chế độ này bám vào LỜI GỌI, không phải một ngưỡng mà phép chia cắt
ngang được; phép chia chỉ rẻ khi nửa đầu tình cờ sạch. Vì vậy **không nối phép chia vào sản
phẩm**: con số quyết định là 95,72 s / 88,67 s so với 78,91 s của đường đang ship
(và 59,09 s của lô 15 thẳng — phép chia chỉ rẻ hơn về SỐ LỜI GỌI). Ghi chú cho
lượt sau: mọi lời gọi **25 mục** đo được tới nay đều sạch (**0/13** hàng
`echo_by_batch`), nhưng lô 25 là ĐUÔI của clip trong mọi lượt nên độ dài
và nội dung còn lẫn nhau — muốn coi đó là ngưỡng thì phải đo một phép chia 25/5.

Smoke của lượt đo đó (cùng clip 115 đoạn, cùng 5 thuật ngữ, cùng engine, lô 30,
`echo_guard` BẬT, mỗi style MỘT lượt qua `TranslateHandler`, artifact ở
`data/experiments/accuracy-pipelines/20261019-prompt-echo-sweep/`): **V0** -> 89
lần dịch lại / 0 lô hỏng / 83,03 s (tái lập đúng số đã ghim, nên bốn cột so được
với nhau); **V1** -> **89** / 0 / 76,01 s (dời chỉ dẫn xuống cuối KHÔNG đổi gì:
giả thuyết "model bỏ chỉ dẫn ở đầu prompt dài" SAI với engine này); **V2** ->
**29** / 0 / 68,16 s (một cặp ví dụ cắt 60 lần dịch lại, và 29 lần còn lại nằm
HẾT ở lô ĐẦU — lần chạy lặp lại, artifact ở `repeat-v2/` trong cùng thư mục, vẫn
đúng **29** nên không phải may); **V3** -> 0 lần
dịch lại nhưng **1 `EchoProblem`** (model trả 22/30 rồi 25/30 mục, hạ cấp xuống
dịch từng segment, một segment vẫn echo) / 32,92 s / **0** segment được nhận.
Không lượt nào bị QA báo `lang:`; cờ `is_echo` duy nhất còn lại (đoạn 9, `2288`
-> `2288`) có ở CẢ artifact `20261019-echo-guard/` cũ, tức phép đo của QA bắt oan
một con số giữ nguyên, không phải lỗi mới — và đó chính là ca đã sửa sau lượt này:
`mt_qa.is_echo` nay trả `False` khi NGUỒN không có chữ Hán nào, vì một con số/mã
giữ nguyên là bản dịch ĐÚNG chứ không phải bản chép của một bản dịch (không cấu
hình nào của lượt đo cũ chạy lại, nên bốn artifact trên vẫn giữ cờ cũ đó). Tức
KHÔNG biến thể nào đạt mức "< 10
lần dịch lại, không `EchoProblem`, ≤ ~40 s": V2 là biến thể duy nhất cải thiện
được con số, nhưng 29 ≥ 10 và 29 lời gọi singleton vẫn giữ wall time ở 60–68 s —
nên KHÔNG nhận biến thể nào ở lượt này, và đòn bẩy tiếp theo là kiến trúc hybrid
(opus-mt trước, hy-mt chỉ trên các đoạn bị gắn cờ), không phải prompt.

Lần bump trước, `1165/15` → `1187/15` (**+22 bài**), do **hatch biến thể prompt**
của lượt đo echo (`tests/test_mt_prompt_styles.py`, **+22**): bốn biến thể V0–V3
(mặc định; chỉ dẫn dời xuống cuối; một cặp ví dụ Hán -> Việt; dòng dữ liệu đánh số
`[i]`) chọn bằng `prompts.EXPERIMENT_PROMPT_STYLE_ENV` và CHỈ cho `hy-mt-1.5-7b`,
để đo xem có biến thể nào làm lô 30 thôi chép nguồn không — cái giá của `echo_guard`
là **89** lời gọi singleton và **78,85 s** ở lô 30, và mục tiêu là kéo số đó xuống
dưới ~10 lần dịch lại để wall time về ~33 s. Hai mươi hai bài đó ghim ba thứ: (a)
prompt mặc định **từng byte** — cả `system_prompt` lẫn `user_prompt`, cộng sha256
của cặp, vì hai hàm này DÙNG CHUNG với `qwen2.5-3b`/`qwen2.5-7b` và số của chúng
đã ghim; (b) một engine không chọn biến thể (`qwen*`, `opus-mt`, hoặc người gọi
không truyền `engine_id`) nhận ĐÚNG chuỗi mặc định **dù biến môi trường có đặt gì**
— hatch đọc biến đó SAU khi đã loại engine, nên đây là tính chất của code chứ không
phải lời hứa; (c) mỗi biến thể có đúng tính chất định nghĩa nó (V1 DỜI câu cấm chứ
không nhân bản nó, V2 đúng MỘT cặp input/output giữ số `12000` và KHÔNG lấy chữ từ
clip, V3 đánh số mọi dòng dữ liệu nhưng giữ NGUYÊN VĂN dòng `Định dạng:`). KHÔNG
biến thể nào được ship và `PROMPT_VERSION` KHÔNG đổi, nên nhãn của lượt đo nằm ở
trường `prompt_style` trong artifact chứ không ở `translations.prompt_version`.

Lần bump trước, `1141/15` → `1165/15` (**+21 bài**), do **echo guard**: với
`hy-mt-1.5-7b`, trên clip 115 đoạn `20261019-name-patch-smoke`, số đoạn bị TRẢ
NGUYÊN chữ Trung là **0–8/115** ở lô 8, **29/115** ở lô 15, **59–89/115** ở lô 30
(chữ Hán trong đầu ra: 0–54 / 181 / 389–629; `opus-mt` cùng clip: 0/115 và 0 chữ
Hán). Số mục vẫn khớp nên `check_alignment` cho qua và hàng `translations` vẫn
`done` — nên đường dịch có thêm `mt_qa.echoes_source` (vị từ THUẦN, ngưỡng
`ECHO_GUARD_SHARE = 0,5` chữ Hán / ký tự không phải khoảng trắng, cộng luật khớp
nguyên văn cho ca thuật ngữ đã token hoá), `TranslateHandler._guard_echoes` (dịch
lại MỘT MÌNH từng đoạn bị chép), và lỗi CÓ TÊN `pipeline.translate.EchoProblem`
(cả lô `failed`, không ghi `done`). Cơ chế bật bằng `capabilities.echo_guard` và
chỉ `hy-mt-1.5-7b` khai, nên `opus-mt` đi đúng đường cũ từng byte. Toàn bộ
**+21 bài** nằm ở hai tệp mới: `tests/test_echo_guard.py` (**+12**: bản dịch Việt
sạch, chép nguyên văn, model viết lại trong tiếng Trung, rỗng, câu lai có thuật
ngữ Hán ở 0,33/0,47 KHÔNG bị chặn, một chữ Hán trích dẫn, ngưỡng 0,5, ca đã token
hoá 2/6 phải bắt bằng luật nguyên văn, cổng ngôn ngữ `zh -> zh`/`en -> vi`) và
`tests/test_translate_echo_guard.py` (**+9**: engine không khai cờ nhận nguyên
đầu ra Hán với ĐÚNG một lời gọi, thiếu `engine_capabilities` y hệt cờ tắt, đoạn
echo được gọi lại một mình rồi lô thành công kèm số đo trong log, lô sạch không
gọi cổng, lô vẫn echo ném `EchoProblem` kèm id/số đoạn và hàng `failed` không có
segment nào, lỗi liệt kê ĐỦ id, cờ của `registry.json` THẬT chỉ bật cho
`hy-mt-1.5-7b` và cờ đó chạy, dịch lại hỏng alignment cũng chặn, chỉ `text` đổi).

Smoke THẬT sau khi bật cổng (cùng clip, engine thật, `scripts/smoke_echo_guard.py`,
artifact ở `data/experiments/accuracy-pipelines/20261019-echo-guard/`): lô 30 -> 4
lời gọi cả lô + **89** lời gọi dịch lại, **0** lô hỏng, **0** đoạn echo, **0** chữ
Hán, **78,85 s**; lô 15 -> 8 + **29**, 0 lô hỏng, 0 echo, 0 chữ Hán, **57,72 s**;
lô 8 -> 17 + (7 cổng + 8 hạ cấp), 0 lô hỏng, 0 echo, **2** chữ Hán (một câu sót
`不到路费2000` -> `不到2000`, tỉ lệ 0,33 dưới ngưỡng nên cổng cố ý không chặn), **61,00 s**.
Tức cổng biến "59–89/115 đoạn chép nguồn" thành "0 đoạn", và làm điều đó ở CẢ BA
kích thước lô — cái giá là 89 lời gọi singleton ở lô 30, và đó là lý do cờ bật bằng
dữ liệu của từng engine.

⚠️ Số nền trước lượt này đọc là `1141`, nhưng lần chạy thật TRƯỚC thay đổi đã CHỌN
`1144` bài: ba bài thêm trong cây làm việc chưa được bump (đúng kiểu TRÔI mà con
số này tồn tại để bắt). `1144 + 21 = 1165` là con số đã đo.

Lần bump trước, `1128/15` → `1141/15` (**+13 bài**), do **echo là lỗi IM LẶNG**: trên
clip 115 đoạn `20261019-name-patch-smoke`, `hy-mt-1.5-7b` trả nguyên
chữ Trung cho **59–89/115 đoạn** ở lô 30 — số mục vẫn khớp nên `check_alignment`
cho qua, QA chỉ gắn `lang:<i>` từng dòng, và hàng `translations` vẫn `done`, tức
một lượt "4 lời gọi / 32,8 s" là lượt KHÔNG dịch (`opus-mt`: 0/115 trên cùng
clip). Vì vậy đường dịch có thêm `mt_qa.is_echo` + `mt_qa.echo_run_issue` và
`TranslateHandler._retry_echoed`: đoạn bị chép nguồn được dịch lại MỘT MÌNH (lô
1), đoạn vẫn echo giữ chữ của model kèm cờ `echo` trên `Segment.qa`, và cả lượt
thêm issue `echo:<n>/<tổng>` khi vượt 5%. Cơ chế bật bằng
`capabilities.echo_retry` (`registry.json`), nên engine chưa đo đi đường cũ. Toàn
bộ **+13 bài** nằm ở `tests/test_translate_echo.py` mới (chép nguyên văn, viết
lại trong tiếng Trung vẫn là echo, câu lai có tên Hán KHÔNG phải echo, ngưỡng
0,5 và 5%, chỉ đoạn echo bị gọi lại và gọi một mình, dịch lại hỏng không làm mất
lô, mỗi lần dịch lại đúng một hàng `llm_calls`, cảnh báo cấp lượt không phụ thuộc
cờ).

Trước đó, `1115/15` → `1128/15` (**+13 bài**), do tính năng **XOÁ** —
hai route `DELETE /api/sources/{id}` và `DELETE /api/translations/{id}`
(`routes_sources.delete_source` + `routes_translations.delete_translation`), phần
cascade viết tay trong `adapters/persist/sqlite_repos.py` (`schema.py` KHÔNG có
`ON DELETE CASCADE`), và luật 409 dùng chung ở `app/api/delete_guard.py`. Chia
ra: `tests/test_api_delete_sources.py` mới **+9 bài** (cascade ba bảng, tệp media
bị xoá, tệp thiếu không phải lỗi, tệp NGOÀI `media_dir` không bị chạm, 404 nêu
id, 409 cho job `queued`/`running` kèm id job, job `done` không chặn và hàng
`jobs` sống sót, job của nguồn KHÁC không chặn);
`tests/test_api_delete_translations.py` mới **+4 bài** (chỉ một hàng bị xoá,
transcript/nguồn nguyên vẹn, 404, 409 khi có job `translate`, job `done` không
chặn).

Trước đó, `1075/15` → `1115/15` (**+40 bài**), do **bảo vệ thuật ngữ
bằng token** (`app/domain/term_placeholder.py` + seam trong
`pipeline/translate.py`), **cổng capability của bản vá tên riêng**, và **hai cờ QA
từng nói SAI** khi cơ chế token bật. Policy tên riêng là Hán-Việt
(`曹磊 → Tào Lôi`), còn `hy-mt1.5-7b:q4_K_M` tự ra pinyin (`Cao Lei`) — nên bản
dịch của thuật ngữ phải đến từ hàng glossary. Chia ra:
`tests/test_term_placeholder.py` mới **+22 bài** (thuật ngữ dài thắng, một lượt
`re.sub` không thay hai lần, `ZXQ1`/`ZXQ10`, model hoa/thường/tách số, token ở đầu
câu, token bỏ/lặp/lạ, va chạm tiền tố, term dính số, `plan_terms`);
`tests/test_translate_placeholder_wiring.py` mới **+11 bài** (engine không khai cờ
nhận ĐÚNG chuỗi gốc, chỉ `text` đổi, câu không chứa thuật ngữ byte-identical, câu
nguồn đã có token, QA không còn báo sai, cổng `name_patch` của
`opus-mt`/`hy-mt-1.5-7b` trên `registry.json` thật); `test_mt_qa.py` **+3** (cờ
`glossary_enforced`, rendering dài không bị tính là model lan man, chỉ quy đổi
rendering của thuật ngữ CÓ trong câu nguồn); `test_metrics.py` **+3** và
`test_ocr_scoring.py` **+1** (paired bootstrap CI tất định theo seed; bảng theo cặp
phải khớp bảng điểm — dùng để chấm **test split** 42 caption, xem
`data/experiments/accuracy-pipelines/20261019-decode-dev-sweep/paired-ci-test-summary-v4.json`).

Trước đó, `819/13` → `821/13`, là do đợt dọn nợ thêm
`tests/test_schema_llm_calls_index.py` (2 bài chọn được, cả 2 chạy thật). Vì
`ffmpeg` có mặt, không bài nào skip ở đây — nên nếu con số này "nhảy" mà không có
bài nào được thêm hay gỡ, đó đúng là TRÔI cần điều tra.

Bump của nhánh `fix-loi-dich-im-lang`: `835/13` → `865/13` (+30 bài), do ba bản
vá `A1`/`A2`/`A3` + bản vá prompt của báo cáo
`.superpowers/sdd/2026-09-26-frontend-workspace-2/real-pipeline-fix-report.md`:
`test_api_sources.py` +7 (tên tệp Unicode: 6 ca hợp lệ, 1 ca cắt đường dẫn, 2 ca
route — và `ảnh.mp4` được CHUYỂN khỏi bảng từ chối ASCII, `-2`), `test_mt_prompts.py`
+15, `test_mt_qa.py` +6, `test_translate_handler.py` +2.

Bump của lượt 3 cùng nhánh: `865/13` → `868/13` (+3 bài), do **V1** — phơi cờ QA
và số đo ra HTTP (`qa_issues` + `tokens_in`/`tokens_out`/`duration_ms`) trong
`.superpowers/sdd/2026-09-26-frontend-workspace-2/real-pipeline-expose-report.md`:
`test_api_translations.py` +3 (route phơi cờ cho ca echo + đối chứng âm `opus-mt`;
vắng cờ ⇒ `[]` chứ không `null`; danh sách cùng hình dạng với chi tiết). Hai lượt
bump này là **cùng một nhánh**, nên `865/13` ở trên không phải số của `gd3-frontend`.

Bump của nhánh `chimera`: `868/13` → `920/13` (**+52 bài**), do tính năng **CHIMERA**
(§8.7.5 của spec kiến trúc + §4.5 của spec UI) — `.superpowers/sdd/
2026-09-26-frontend-workspace-2/chimera-report.md`. Chia ra: `tests/test_chimera.py`
mới **+50 bài** (dữ liệu registry, luật mỏ neo, hệ số chi phí, runner N+1 lượt,
đường LÙI có ghi chép, ba route Chimera); `tests/test_schema_migration.py` **+1**
(cột `translations.chimera` trên DB v1); `tests/test_schema_llm_calls_index.py`
**+1** (bất biến "index không phải một bước migration" nay ghim bằng
`_MIGRATIONS` thay vì bằng con số `SCHEMA_VERSION` — con số đó bump vì một CỘT, nên
ghim nó ở đó sẽ nói sai lý do).

Bump này cũng đổi `SCHEMA_VERSION` `2` → `3`: cột `translations.chimera` là một
CỘT, nên nó cần một bước migration thật, khác hẳn index của `llm_calls` (một ĐỐI
TƯỢNG, `CREATE INDEX IF NOT EXISTS` tự chạy trên DB cũ).

Số này chỉ để phát hiện TRÔI: một thay đổi làm nó **giảm** là một bài đã bị gỡ
hoặc bị bỏ quên, không phải "suite nhanh hơn".

### Smoke test DỊCH — in ra SỐ, và thoát khác 0 khi không có gì để dịch

```powershell
# 1) tải weight OPUS-MT trước, để lần chạy thật đầu tiên không phải chờ mạng
$env:HF_HOME = "D:\models\hf"
.\.venv\Scripts\python.exe -B scripts\download_mt_models.py

# 2) chạy THẬT cả hai engine trên cùng một tệp
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py clip.wav zh opus-mt vi
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py clip.wav zh qwen2.5-3b vi

# 3) chỉ đo đường DỊCH (không cần âm thanh), và chỉ ra engine bóc băng khác
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py --synthetic opus-mt
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py clip.wav zh qwen2.5-3b vi --asr fw-large-v3-turbo
```

`smoke_mt.py` **không** thuộc bộ pytest: nó nạp weight thật và gọi Ollama thật.
Nó in **số** cho mỗi lần chạy (segment vào/ra, thời gian, `tokens_in`/
`tokens_out`) và mã thoát phản ánh kết quả thật:

| mã | nghĩa |
|----|-------|
| `0` | dịch được, số segment ra **bằng** số vào |
| `1` | chạy được nhưng đường ống SAI: **0 segment**, lệch alignment, hoặc bản dịch rỗng |
| `2` | sai cách dùng, hoặc không thấy tệp |
| `3` | không dựng/nạp được engine (thiếu weight, Ollama tắt, id sai) |

**`0` segment KHÔNG phải thành công.** Một lần chạy "xanh" trên không có gì đúng
là kiểu thất bại mà Giai đoạn 1a đã trả giá (19 task xanh trong khi đường ASR chết
vì chưa từng ai chạy nó), nên nó thoát khác 0 kèm lý do.

`--asr <id>` chọn engine bóc băng (mặc định `fw-small`). Id **không có** trong
`registry.json` bị từ chối kèm danh sách id có thật — `fw-tiny` là ví dụ: nó từng
nằm trong tài liệu nhưng **không tồn tại** trong registry.

`tokens_in`/`tokens_out` chỉ có ở engine chạy qua Ollama (`qwen2.5-3b`,
`qwen2.5-7b`, `hy-mt-1.5-7b`); OPUS-MT chạy trong tiến trình và không có token
count, nên nó in `None` chứ **không** in `0` — "chưa đo được" khác "nhanh bằng không".

`download_mt_models.py` in ra đường dẫn cache THẬT và dung lượng THẬT. Nó đặt
`HF_HOME` **trước** khi import `transformers`, vì `huggingface_hub` đọc biến đó
ngay lúc import: đặt sau thì model rơi vào cache mặc định trên ổ C: dù dòng log
in ra đường dẫn đúng.

## Giai đoạn 2 — Workspace 2 (dịch)

Workspace 2 là đường **dịch**: `draft -> reviewed -> translated` (spec §8.6), rồi
xuất phụ đề. Đây là trạng thái **đã đo** của nó, kèm những gì **chưa** biết.

### Cài

`transformers` cho OPUS-MT đã nằm trong `requirements.txt` (`transformers==4.46.3`),
nên `scripts/install.ps1` là đủ cho engine dịch in-process. Engine chạy qua Ollama
cần thêm **một tiến trình ngoài venv**:

```powershell
ollama pull qwen2.5:3b-instruct-q4_K_M   # đúng `model_ref` trong registry.json
```

`GET /api/registry` trả `available` cho từng engine, và `available` nghĩa là
**"phục vụ được job NGAY BÂY GIỜ"**: với engine `runtime == "ollama"` điều đó cần
CẢ tiến trình trả lời được **VÀ** `model_ref` có trong `/api/tags`. "Ollama đang
chạy" là điều kiện cần nhưng **không đủ** — chọn một engine mà API khai sẵn sàng
rồi job chết ở tận worker là lớp lỗi đã bị bịt (từ chối 409 ngay lúc tạo bản dịch).

### Chạy

```powershell
# chỉ đo đường DỊCH, không cần âm thanh
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py --synthetic opus-mt

# đo cả đường bóc băng, và chỉ ra engine bóc băng khác
.\.venv\Scripts\python.exe -B scripts\smoke_mt.py clip.wav zh qwen2.5-3b vi --asr fw-large-v3-turbo
```

`tests/test_mt_live.py` là các bài **chạm model thật**, mặc định bị `pytest.ini`
bỏ qua (`-m "not live"`). Chạy chúng bằng:

```powershell
.\.venv\Scripts\python.exe -m pytest -m live
```

Mỗi lần chạy như vậy là một lần **ĐO**, không phải một lần "chắc là đúng".

### Số đo đã có

Đo trên một wav tiếng Trung thật (21,5 s), qua `smoke_mt.py`:

| engine | segment vào/ra | thời gian | `tokens_in`/`tokens_out` |
|---|---|---|---|
| `opus-mt` | 4 / 4 | 6,7 s | `None` / `None` (in-process, không có token count) |
| `qwen2.5-3b` | 4 / 4 | 2,9 s | 219 / 149 |

Bóc băng `fw-small`: **1,0 s / RTF 0,049** là con số của **`smoke_asr.py`** (đo
riêng, model đã nạp sẵn trong tiến trình), **KHÔNG** phải của `smoke_mt.py`. Giai
đoạn bóc băng **bên trong** `smoke_mt.py` — hai lần chạy thật của Task 16, cùng wav
21,48 s — đo được **3,7 s**, vì tiến trình mới còn phải nạp model. Sau **mọi** lần
`release()`, `ollama ps` **rỗng** — model dịch thật sự rời VRAM, không chỉ được
đánh dấu là đã rời.

#### VRAM hiện trên header (`GET /api/status`) — đo thật, kèm đơn vị

Trước lượt này route trả `"vram": None` **CỐ ĐỊNH** (GĐ1a chưa có đường đọc), nên
giao diện luôn in `VRAM: chưa đo được`. Nay `app/adapters/gpu.py` đọc
`nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits`, và
`app/main.py::build_app` đặt callable đó vào `app.state.vram_reader` (route
**không** import adapter — `tests/test_api_sources.py` cấm).

Số đo trên máy này (RTX 3070 8 GB, 2026-10-25), 20 lần gọi liên tiếp:

| tổng 20 lần | mỗi lần | giá trị khi không model nào trong VRAM |
|---|---|---|
| 811,3 ms | **~40,6 ms** | 1467–1468 MiB |

⇒ đo **mỗi request** được: route này đã probe Ollama mỗi request (trần 0,3 s) và
frontend **không poll** nó, nên 40 ms là cùng bậc; **không cache** (cache là thêm
trạng thái để test và để lệch số).

Hợp đồng: `vram` là số hoặc `null` (không đọc được ⇒ `null`, KHÔNG phải `0` —
`0` nói "card trống"), và `vram_unit` **luôn có** (`"MiB"`), kể cả khi `vram` là
`null`. Giao diện in `1467 MiB`; nó **không** tự gắn đơn vị. Đơn vị nằm ở
`app/domain/vram.py::VRAM_UNIT` vì cả `app/api` (nơi trả JSON) lẫn
`app/adapters` (nơi cầm số) đều đọc, mà `app/api` không được import adapter.

#### VRAM của lượt dịch (`--sample-vram`) — có artifact, trích dẫn được

Lượt trước báo *peak 6830 MiB / headroom 1362 / steady ~6433 / model 100% GPU*
nhưng **không tệp nào trên đĩa** chứa những số đó. Lượt `20261019-vram-sample`
(cùng clip 115 đoạn, 5 thuật ngữ, prompt v0, lô 30, `echo_guard` BẬT, RTX 3070
8 GB) ghi từng mẫu `nvidia-smi --query-gpu=memory.used` (~1 Hz) vào khối `vram`
của `data/experiments/accuracy-pipelines/20261019-vram-sample/batch-30.json`:

```powershell
.\.venv\Scripts\python.exe -B scripts\smoke_echo_guard.py --batches 30 --sample-vram `
    --transcript ..\data\experiments\accuracy-pipelines\20261019-name-patch-smoke\large-v3-beam5-prevfalse.json `
    --glossary ..\data\experiments\accuracy-pipelines\20261019-term-placeholder-smoke\glossary.json `
    --out-dir ..\data\experiments\accuracy-pipelines\20261019-vram-sample
```

| nền idle | đỉnh | ổn định | headroom | mẫu | giây |
|---|---|---|---|---|---|
| 1781 MiB (5 mẫu) | 7258 | 7013 | 934 | 87 (81 sau khi nạp) | 85,49 |

`ollama ps` **trong** lượt (sau lời gọi đầu, lúc 9,41 s):

```
hy-mt1.5-7b:q4_K_M    5f79e49d4ed2    5.3 GB    100% GPU    4096    llamacpp
```

`/api/ps` cùng lúc cho `size_vram == size == 5.279.842.303` byte, tức model
**không** bị chia sang CPU — con số, không phải nhãn.

* **"Đã nạp"** = mẫu đầu tiên cao hơn TRUNG VỊ nền idle ít nhất **512 MiB** VÀ
  mẫu KẾ TIẾP cũng trên ngưỡng (2 mẫu liên tiếp). Một gai đơn lẻ không phải một
  lần nạp model 4,9 GB: trong lượt này mẫu `1933` MiB bị bỏ qua, `6318` MiB mới
  là mẫu đầu của lần nạp.
* **peak** = max phần đã nạp. `7258` rơi vào pha **hạ cấp alignment của lô 2**
  (30 lời gọi một mục), nên nó là đỉnh của ĐƯỜNG XẤU NHẤT, không phải của lúc
  dịch bình thường. **steady** = MODE phần đã nạp: `7013` giữ từ khoảng giây 50
  tới cuối lượt, còn `7258` chỉ là một mẫu.
* idle `1781` MiB **không phải GPU trống**: đó là nền của máy này (desktop +
  trình duyệt) với `ollama ps` rỗng trước khi nạp (`unloaded_before_idle: false`,
  `model_loaded_before: []`). Headroom `934` MiB là headroom thật của cấu hình
  đang chạy.
* Cờ **mặc định TẮT**: không có lời gọi `nvidia-smi` nào và artifact **không** có
  khoá `vram` — `tests/test_vram_sample.py` ghim cả hai vế (khối vắng mặt + hàm
  THUẦN `summarize_vram`).

### Thêm một engine dịch qua API (`runtime: "http"`)

Một engine dịch không nhất thiết phải nằm trên máy này. `runtime: "http"` nói giao thức
**OpenAI-compatible** (`POST {base_url}/chat/completions`); mọi thứ còn lại — batching,
alignment, QA, retry — vẫn là `TranslateHandler` của sản phẩm. Đây là DỮ LIỆU: thêm một
hàng vào `mt` là xong, không sửa mã. `available` của hàng đó là câu trả lời THẬT (endpoint
trả lời, khai đúng `model_ref` ở `/models`, và khoá API có trong biến môi trường), dò một
lần lúc dựng, giống hệt cách engine Ollama bị dò.

```json
{
  "id": "api-dich",
  "label": "API dịch (cần mạng)",
  "runtime": "http",
  "model_ref": "deepseek-chat",
  "vram_mb": 0,
  "langs": ["zh", "en"],
  "capabilities": { "glossary_prompt": true, "glossary_patch": false, "chimera": false },
  "opts": {
    "base_url": "https://api.deepseek.com/v1",
    "contract": "json",
    "json_mode": "object",
    "max_tokens": 4096,
    "api_key_env": "DEEPSEEK_API_KEY"
  }
}
```

`opts`: `base_url` BẮT BUỘC (gồm `/v1`); `contract` (`json` | `lines`, mặc định `json`);
`api_key_env` là TÊN biến môi trường, **không** phải khoá — một khoá nằm trong
`registry.json` là khoá đã chia sẻ với mọi người đọc repo.

**Chọn `contract` theo endpoint, không theo sở thích.** `json` chỉ đúng khi endpoint BẢO
ĐẢM JSON (API chính thức có `response_format`; Ollama native có `format: "json"` — grammar
của nó là thứ giữ hợp đồng, không phải model). Endpoint không có grammar — ví dụ một cổng
biến phiên web thành API — phải dùng `lines`: đo được trên cùng clip, cùng `hy-mt`, `json`
chết ở 0–30/115 đoạn vì lỗi cú pháp, còn `lines` đi hết **115/115 trong 59,09 s / 25 lời
gọi**, 0 chữ Hán, thuật ngữ 7/7 (`docs/superpowers/reports/2026-10-25-spike-openai-mt.md`).
Lô 15 là điểm làm việc của hợp đồng `lines`: lô 30 làm 3/4 lô hỏng alignment rồi phải hạ
cấp, đắt hơn — nên đặt `capabilities.max_items_per_call: 15`.

**Ví dụ trên KHÔNG có trong `registry.json` đã ship**, và đó là chủ ý: engine chưa đo trên
endpoint thật thì chưa khai. Ba điều phải nói trước khi bật nó:

1. **`default_mt` phải tiếp tục là `opus-mt`.** Đổi engine mặc định là đổi tiền đề offline
   của cả pipeline, và mọi số trong tài liệu này đo trên đường local.
2. **Văn bản phụ đề rời khỏi máy.** Đây là thay đổi về quyền riêng tư, không phải một tối
   ưu — với engine `runtime: "http"` thì nội dung clip của người dùng đi tới bên thứ ba.
3. **Số đo của nó không tái lập được.** Không đặt được sampling, hành vi của dịch vụ đổi
   ngoài tầm kiểm soát. Một con số của engine `http` phải được dán nhãn như vậy, không được
   trộn vào bảng so sánh local.

### Giới hạn — đọc trước khi tin bất cứ con số nào ở trên

1. **`DEFAULT_MAX_CHARS = 1200` NAY ĐÃ ĐƯỢC ÉP — và nó có tác dụng thật.**
   Lượt đo `20261025-batch-chars` (`scripts/measure_batch_chars.py`, transcript TỔNG
   HỢP, `qwen2.5-3b`, `engine_capabilities={}` tức **không** `echo_guard`) chạy bốn
   cấu hình, mỗi cấu hình **một lượt**:

   | cấu hình | lô theo lý thuyết | giây | alignment | echo | kết quả |
   |---|---|---|---|---|---|
   | 24 đoạn × 150 ký tự, `batch_chars=1200` | 8 mục / 1200 ký tự × 3 | 29,34 | 1 | **16/24** | `done` (1 lời gọi phải thử lại) |
   | 24 × 150, `batch_chars=3000` | 20 mục / 3000 + 4 / 600 | 29,65 | 0 | **24/24** | `done` |
   | 24 × 150, `batch_chars=8000` | **1 lô 24 mục / 3600 ký tự** | 91,61 | 9 | 0 | **`failed`** (0/24 đoạn) |
   | 60 × 25 (cỡ phụ đề thật), `batch_chars=1200` | **30 mục / 750 ký tự** × 2 | 17,30 | 0 | 33/60 | `done` |

   Ba kết luận, mỗi kết luận một dòng đo:

   * **Trần SỐ MỤC không phải thứ làm vỡ hợp đồng.** 30 mục / **750** ký tự chạy sạch
     (0 alignment); 24 mục / **3600** ký tự mới vỡ. Cùng trần 30 mục, khác số ký tự ⇒
     **ký tự** là biến quyết định, không phải số mục.
   * **Ngưỡng vỡ đo được nằm giữa 3000 và 3600 ký tự** cho MỘT lời gọi (`qwen2.5-3b`,
     transcript tổng hợp): 3000 ký tự còn qua, 3600 ký tự thì `AlignmentProblem` rồi
     `ValueError`, hạ cấp xuống từng mục vẫn **hỏng cả lượt** (9 lỗi, 91,6 s).
   * ⇒ Giữ **1200** là **bảo thủ ~2,5×** so với ngưỡng vỡ đo được, và nó còn có tác
     dụng PHỤ đo được: lô 8 mục echo **16/24**, lô 20 mục echo **24/24** — lô nhỏ hơn
     thì chép ít hơn (cùng hiện tượng đã ghi ở mục echo).

   ⚠️ **Trần của phép đo:** n = 1 mỗi cấu hình, MỘT engine (`qwen2.5-3b`), chữ tổng
   hợp (câu hợp lệ nhưng không phải ASR thật). Đừng trích "ngưỡng 3000–3600" như một
   hằng số của mọi engine — nó là ngưỡng **đo được của cấu hình này**. Điều đã đủ để
   nói: **1200 không phải con số tuỳ tiện**, và **tăng nó lên là tăng echo**.
2. **Chất lượng dịch CHƯA được đánh giá.** Chưa có điểm BLEU/MQM, chưa có người
   đọc duyệt. Không có tuyên bố nào về chất lượng ở đây. Đổi lại, **lỗi thấy được
   trên đầu ra thật** thì được ghi, vì đó là số thật về sản phẩm chứ không phải
   phỏng đoán:
   * `opus-mt` **cắt cụt câu** (bản dịch chỉ phủ phần đầu của câu nguồn) và dịch
     成本 thành `"10%"`.
   * `qwen2.5-3b` **để sót chữ Hán** trong bản dịch: `dịch字`, `việc字幕`.
   * 🔴 **`opus-mt` là engine cho đường ASR; `qwen2.5-3b` CHỈ dịch được chữ SẠCH.** Với chữ ASR
     thật (vỡ câu · lẫn Phồn thể · sai từ) `qwen2.5-3b` **CHÉP NGUYÊN VĂN bản gốc**: **43/44 đoạn**
     trên một clip tiếng Trung thật (`fw-tiny` → 44 đoạn → `POST /api/translations`), vẫn ghi
     `status=done` + `transcript=translated`. Prompt `qwen-json-p2` làm **chữ sạch** dịch thật
     (**8/8** qua API) mà **không** cứu được chữ ASR (43/44); `temperature=0.1` cho kết quả **tất
     định theo nội dung prompt**, và giả thuyết *prompt-cache* / *model vừa nạp lại* đã bị **bác bỏ
     bằng phép đo** — nên đây là hành vi của model + nội dung chữ nguồn, **KHÔNG** phải lỗi API.
     Cùng clip đó `opus-mt` cho **44/44 đoạn tiếng Việt, 0/118 ký tự Hán**. Cờ QA (`lang:`) nay ra
     tới HTTP (`qa_issues` + `tokens_in`/`tokens_out`/`duration_ms` trên `GET /api/translations/{id}`
     và trên danh sách), nhưng `status` **không** đổi ngữ nghĩa — chặn theo cờ vẫn là quyết định mở.
     Số đo đầy đủ: `.superpowers/sdd/2026-09-26-frontend-workspace-2/real-pipeline-fix-report.md`
     (§3) và `real-pipeline-expose-report.md`.
3. **Chưa làm:** HY-MT1.5 (`hy-mt-1.5-7b` có trong registry nhưng chưa lần nào
   chạy), **chế độ Chimera**, và **toàn bộ frontend**. Backend là thứ đang chạy
   được; giao diện thì chưa có.
   * **"Thuật ngữ cấm" của spec §8 (QA tất định): CHƯA LÀM, và đây là chỗ ghi
     nhận chính thức.** Spec Giai đoạn 2 §8 hứa QA gắn cờ *thuật ngữ cấm*, nhưng
     không có mô hình dữ liệu nào cho nó: `glossary` chỉ có `approved`, không có
     cột `forbidden`, và spec nền cũng không định nghĩa khái niệm đó. Bảng phủ
     spec của plan gán §8 cho T5/T13, nên nửa "thuật ngữ cấm" từng là một lỗ
     hổng **không được ghi ở đâu cả**. Quyết định: **không** hiện thực trong
     Giai đoạn 2 (nó cần một quyết định về mô hình dữ liệu trước), và ghi nó vào
     đây + vào sổ nợ của ledger. Nửa còn lại của §8 (CPS, tỉ lệ độ dài, cờ
     engine-không-glossary, cờ `stale`) **đã** có.
   * **`llm_calls` (spec §4.2) thì NAY ĐÃ CÓ** — mỗi lần chạm engine ghi một
     hàng, và `translations.tokens_in/tokens_out/duration_ms` là TỔNG của các
     hàng đó. Trước vòng sửa cuối, bảng này chỉ có test chạm tới, và số của bản
     dịch chỉ là số của lô CUỐI.
4. **`HF_HOME` và lần chạy thật tiếp theo.** Mặc định là `D:\models\hf`. Trong
   phiên đo gần nhất, **ghi sang D: bị từ chối** (`WinError 5`:
   `mkdir FAILED PermissionError ... 'D:\models'`), nên trọng số OPUS-MT đã bị
   **xoá cùng thư mục scratch**. Lần chạy thật tiếp theo **phải tải lại ≈800 MB**:

   ```powershell
   .\.venv\Scripts\python.exe -B scripts\download_mt_models.py
   ```

### Nghiệm thu đầu-cuối

`tests/test_e2e_translate.py` chạy trọn chuỗi trên **bộ ráp thật của production**
(`main.build_components()` + `main.build_app()`), chỉ thay adapter model bằng engine
giả, và không phải bài `live`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_e2e_translate.py
```

Nó đi qua cả ba mốc `draft -> reviewed -> translated`, khẳng định `approve` ghi
`reviewed` (không phải `translated`), và khẳng định `translated` chỉ xuất hiện sau
khi bản dịch xong — kèm một bài đối chứng cho chính mốc đó, và một bài cho vế ngược
lại: bản dịch **HỎNG** thì transcript phải còn `reviewed`. Bài cũng ghim đối số chạy
vào adapter thật: `model_ref` truyền cho engine mặc định được so với chính
`registry.json` (không hard-code chuỗi).

**Giới hạn: engine Ollama KHÔNG nằm trên đường của bài này.** Fixture coi như chưa
pull model nào (`ollama_available → set()`), nên `qwen2.5-3b/7b` và `hy-mt-1.5-7b`
không được dựng và không được chạy; bài chỉ phủ đường **in-process** `opus-mt`.
Đường Ollama do `tests/test_mt_live.py` phủ khi chạy `-m live` (cần model thật) và
bởi `scripts/smoke_mt.py`.

## Chưa kiểm chứng

* **Hình dạng thật của `timestamp` từ SenseVoice/FunASR.** Ba hình dạng
  (`start`+`end` số · cặp phẳng `[b, k]` · danh sách cặp `[[b, k], ...]`) đã được
  ghim bằng test với `model_factory` giả, nhưng **chưa lần nào chạy model thật**:
  `funasr` không có trong venv và không được tải model ở đây. Nếu hình dạng thật
  khác cả ba, `SenseVoiceEngine` sẽ **nổ** kèm danh sách khoá hiện có — đó là tín
  hiệu mong muốn, không phải lỗi cần vá im lặng.
* **Nhánh tải `yt-dlp` thật** (khi `runner is None`): đã được chạy qua một
  `yt_dlp` giả, chưa lần nào tải thật.
* **RTF + thời gian nạp model**: hai số này chỉ có sau khi chạy
  `smoke_asr.py` với GPU; chúng là đầu vào cho bảng benchmark ở GĐ1b.

## Ghi chú kiến trúc

`app/domain/` là logic thuần — `tests/test_layer_boundary.py` **sẽ đỏ** nếu ai đó
import `torch`, `sqlite3`, `fastapi` hay `httpx` vào đó. Đó là chủ ý, đừng sửa test.

`app/worker.py` gom lô theo **cặp (loại job, engine)**, không phải theo
`asr`/`mt`. Lý do: người dùng đổi được model cho từng job, nên gom theo loại job
là vô dụng.

Audio **im lặng** làm job `asr` thành `FAILED`, **không** sinh transcript rỗng
(xem `tests/test_silent_audio.py`). Một transcript rỗng trông y hệt một lần bóc
băng thành công, nên nó giấu mất lỗi thật.
