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
"Kiểm thử" trên, chạy từ trong `backend\`). Thứ có nghĩa là **1032 / 15**, không
phải số giây — thời gian trôi giữa các lần chạy (đã thấy 24,00–30,94 s) còn con
số bài thì không:

```
1032 passed, 15 deselected, 1 warning
```

Hai con số đó là SỐ BÀI ĐƯỢC CHỌN, và chúng khớp với số mà `--collect-only` báo
(`tests/test_backend_readme.py::test_readme_baseline_matches_the_tests_actually_
collected` đối chiếu mỗi lần chạy).

Máy này **CÓ** `ffmpeg 8.1.1` + `ffprobe` trên PATH (đã đo), nên `1032/15` ở trên
là số THẬT của nó. Máy **không có** `ffmpeg`/`ffprobe` cho một kết quả KHÁC: cả
`tests/test_ingest.py` bị `skipif` ở cấp module — **9** bài cùng skip một lượt —
nên dòng tổng kết của máy đó là **`978 passed, 9 skipped, 15 deselected`**. Đó là
con số của máy thiếu ffmpeg, **không phải** con số máy này từng in ra; đừng chép
nó vào khối nền ở trên, và đừng "sửa" số nền xuống chỉ vì thiếu ffmpeg.

⚠️ Con số `856` ở đây TỪNG không khớp phép trừ của chính nó: `865 − 9 = 856`, tức
nó là số của lượt TRƯỚC `V1` (+3 bài) còn sót lại. Nay nó bằng đúng `920 − 9`.

(Con số này từng bị ghi là `798`: bài `test_a_failed_translation_leaves_the_
transcript_reviewed` được thêm ở `a428334` — **cùng commit đã sửa tệp này** — mà
số nền không được bump. Nó tồn tại để phát hiện TRÔI, nên một số sai làm mọi lần
chạy báo dương tính giả.

Lần bump gần nhất, `819/13` → `821/13`, là do đợt dọn nợ thêm
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

### Giới hạn — đọc trước khi tin bất cứ con số nào ở trên

1. **`DEFAULT_MAX_CHARS = 1200` CHƯA TỪNG BỊ ÉP.** Lô lớn nhất đo được chỉ **94 ký
   tự**, và alignment **chưa lần nào vỡ** trên 18 segment. Giữ 1200 nghĩa là
   *"không có cơ sở đo để đổi"*, **KHÔNG** phải *"đã xác nhận 1200 là đúng"*.
   **Ngưỡng hỏng thật vẫn chưa biết.** Muốn biết thì phải đo lại: nạp một
   transcript dài (hàng nghìn ký tự) rồi cho `TranslateHandler` chạy với
   `batch_chars` giảm dần cho tới khi alignment vỡ. `smoke_mt.py` **không** có cờ
   cho việc này (nó chạy đúng ngân sách mặc định) — phép đo đó phải viết mới.
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
