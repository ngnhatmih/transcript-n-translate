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
"Kiểm thử" trên, chạy từ trong `backend\`). Thứ có nghĩa là **1364 / 15**, không
phải số giây — thời gian trôi giữa các lần chạy (đã thấy 24,00–30,94 s) còn con
số bài thì không:

```
1364 passed, 15 deselected, 1 warning
```

Hai con số đó là SỐ BÀI ĐƯỢC CHỌN, và chúng khớp với số mà `--collect-only` báo
(`1364/1379`, 15 bài `live` bị bỏ;
`tests/test_backend_readme.py::test_readme_baseline_matches_the_tests_actually_
collected` đối chiếu mỗi lần chạy).


Máy này **CÓ** `ffmpeg 8.1.1` + `ffprobe` trên PATH (đã đo), nên `1364/15` ở trên
là số THẬT của nó. Máy **không có** `ffmpeg`/`ffprobe` cho một kết quả KHÁC: cả
`tests/test_ingest.py` bị `skipif` ở cấp module — **9** bài cùng skip một lượt —
nên dòng tổng kết của máy đó là **`1355 passed, 9 skipped, 15 deselected`** (=
`1364 − 9`; con số này TỪNG ghi `978`, tức một baseline rất cũ, và nó lệch phép
trừ của chính khối nền ngay trên nó). Đó là
con số của máy thiếu ffmpeg, **không phải** con số máy này từng in ra; đừng chép
nó vào khối nền ở trên, và đừng "sửa" số nền xuống chỉ vì thiếu ffmpeg.

⚠️ Con số `856` ở đây TỪNG không khớp phép trừ của chính nó: `865 − 9 = 856`, tức
nó là số của lượt TRƯỚC `V1` (+3 bài) còn sót lại. Phép trừ của khối nền hiện tại
là `1364 − 9` = `1355`.


(Con số này từng bị ghi là `798`: bài `test_a_failed_translation_leaves_the_
transcript_reviewed` được thêm ở `a428334` — **cùng commit đã sửa tệp này** — mà
số nền không được bump. Nó tồn tại để phát hiện TRÔI, nên một số sai làm mọi lần
chạy báo dương tính giả.


Lần bump này, `1353/15` → `1364/15` (**+11 bài**), do **BỐN TẦNG LỌC PHỤ ĐỀ** trong
`app/domain/phu_de.py`: `tests/test_phu_de.py` là tệp mới với 11 bài ghim hàm THUẦN
`tim_dai_phu_de`, `loc_on_dinh`, `loc_hinh_dang`, `loc_theo_asr`, `gop_thanh_dong` — tầng lọc
cho đường OCR-first, chưa nối vào pipeline (việc nối là task sau). Bài thứ 11 ghim đúng lỗi
Critical mà reviewer Task 2 tìm ra: cụm phụ đề TRẢI trên nhiều dải phải thắng cụm logo DỒN
vào một dải khi số hộp bằng nhau. Lần bump TRƯỚC,
`1351/15` → `1353/15` (**+2 bài**), do **BỎ TRẦN TỐC ĐỘ 1,35** trong
`ke_hoach_toc_do`: `tests/test_dub.py` viết lại thành 7 bài (bản cũ 5 bài), thêm bài ghim
RÀNG BUỘC CỨNG "không cặp liền kề nào chồng lấn" và bài ghim "không cắt chữ". Lần bump
TRƯỚC NỮA, `1346/15` → `1351/15` (**+5 bài**), do **TTS CHẠY ĐƯỢC TRONG IMAGE LINUX** — trước
đó mọi job `dub` trong container `failed` ở 5% vì `TTS_PYTHON` trỏ một đường Windows không tồn
tại (`/app/.venv-tts/Scripts/python.exe`; `backend/.dockerignore` loại `.venv-tts/`, và venv đó
là venv Windows). Nay `backend/Dockerfile` dựng `/opt/venv-tts` bằng pip Linux
(`vieneu==3.8.3` + `soundfile`), `ENV PHUDE_TTS_PYTHON` chỉ vào nó, và `app/main.py` có thêm
đường dự phòng `/opt/venv-tts/bin/python` đọc được từ `PHUDE_TTS_PYTHON_TRONG_IMAGE`.

Ba bài của `tests/test_tts_python_duong_dan.py` ghim BA nhánh của đường dẫn đó (biến môi trường
thắng; đường `.venv-tts` cạnh mã nguồn thắng đường trong image; và khi đường cạnh mã nguồn KHÔNG
có mặt thì rơi về đường trong image — nhánh container đi qua, và là nhánh đã hỏng). Hai bài của
`tests/test_dub_handler.py` ghim câu lỗi của TTS: nó phải là **dòng chẩn đoán**, không phải khối
rác WSL. Đo được trước khi sửa: `error` của job #21 dài **472 ký tự**, 400 ký tự sau là
`UtilGetPpid:1359: Failed to parse: /proc/1/stat, content: 1 (python) S 0 1 1 0 -1 4194560 …` —
và bản cũ lấy `stderr[-800:]`, tức lấy ĐUÔI, nên giữ đúng khối rác và có thể cắt mất câu chẩn
đoán ở ĐẦU.

⚠️ **Một phép ghim GIẢ đã bị bắt trong lúc làm, và nó đáng ghi lại.** Bản đầu của bài "rơi về
đường trong image" dùng hằng số cứng `/opt/venv-tts/bin/python` — mà trên Windows KHÔNG có
`/opt`, nên nhánh đó không bao giờ chạy: **mutation SỐNG** (bỏ hẳn ba dòng dự phòng trong
`main.py` mà tệp test vẫn `EXIT=0`). Sửa bằng cách cho đường dự phòng đọc được từ
`PHUDE_TTS_PYTHON_TRONG_IMAGE`, để bài test dựng một python giả trong `tmp_path` và đo ĐÚNG
nhánh. Sau đó hai mutation đều CHẾT: bỏ nhánh dự phòng ⇒ đỏ với đường `.venv-tts`; bỏ
`os.path.exists` ⇒ đỏ với đường không tồn tại.

Bảy bài của lần bump TRƯỚC (`1343/15` → `1346/15`) vẫn còn nguyên, và lý do của chúng:
`POST /api/dubs` xếp một job `dub` cho một bản dịch, `DubHandler` chạy TTS
(VieNeu-TTS v3 Turbo, 48 kHz, venv riêng `backend/.venv-tts`), ép tốc độ từng dòng
để `take ≤ slot` rồi ghi **một** file master ra `data/output/dubs/dub-<translation_id>.<fmt>`;
`GET /api/dubs/{translation_id}/download?format=` trả file theo whitelist
`wav|mp3|aac|m4a|flac`. Bảy bài mới: năm định dạng đều ghi được, dòng đặt ĐÚNG `start`
của nó, tiến độ báo `1.0` khi xong, từ chối một bản dịch không có dòng nào, và ba bài
của hai lỗi đo được ngay dưới đây. Phần THUẦN (`ke_hoach_toc_do`, `rap`,
`xuat_dinh_dang`) đã có 5 bài từ commit trước (`tests/test_dub.py`), nay là 7 bài sau khi
bỏ trần tốc độ.

⚠️ **`handles()` là một phần của hợp đồng handler, không phải trang trí.** Bản đầu
của `DubHandler` thiếu nó, và hậu quả KHÔNG nằm ở đường lồng tiếng: `routes_jobs.
_registered_job_types` gọi `handler.handles()` trên **mọi** handler để biết loại job
nào có đường chạy thật, nên `POST /api/jobs` nổ `AttributeError: 'DubHandler' object
has no attribute 'handles'` — đo được **8 bài `test_api_export_by_translation.py`
ĐỎ** dù đường xuất file không có gì sai. Đó là lý do bài ghim tập handler ở
`test_api_sources.py` nay đòi `{"ingest","asr","translate","export","dub"}`: tập đó
là thứ `_registered_job_types` đọc, nên nó phải phản ánh số handler THẬT.

Hai lỗi nữa của bản đầu, **cả hai chỉ lộ ra khi chạy trên máy thật** — xem mục
"Lồng tiếng (TTS)" bên dưới:

* `chay_tts_batch` tự dựng `TemporaryDirectory` rồi trả ĐƯỜNG DẪN tới các wav trong đó;
  thư mục bị xoá ngay khi hàm trả về nên `run()` đọc một tệp đã biến mất ⇒ mọi job chết
  ở 40% với `LibsndfileError: … System error`. Nay thư mục tạm do **handler** sở hữu và
  `tts_runner` nhận `out_dir` làm tham số. Bốn bài cũ vẫn xanh vì runner giả tự dựng thư
  mục riêng bên ngoài — fixture vô tình thoả hợp đồng mà sản phẩm vi phạm.
* Đường mặc định của TTS là `…/.venv-tts/Scripts/python.exe`, một đường **Windows**;
  trong image Linux nó không tồn tại nên job được nhận rồi `failed` ở 5%. Nay
  `TTS_PYTHON` chọn theo `os.name`, và `POST /api/dubs` **từ chối sớm bằng 409** qua
  `DubHandler.san_sang()` (đo được trong container: `queue_depth` **0 → 0**, không để
  lại hàng `jobs` nào). Kèm theo `.venv-tts` (751 MB) bị `COPY . .` mang vào image;
  thêm vào `backend/.dockerignore` ⇒ image **10,8 GB → 9,64 GB**.

Lần bump trước, `1300/15` → `1336/15` (**+36 bài**), gồm hai cụm:

**(a) Mười bài của `tests/test_asr_progress.py` — job `asr` phải NHÍCH và lần đầu tải model phải
NÓI RA.** Sự cố đo được trên stack thật: một job `asr` với `fw-large-v3` đứng ở `15%` suốt **sáu
phút** rồi bị một lượt dựng lại container cắt ngang. Hai nguyên nhân, cả hai là lỗi HIỂN THỊ:
`progress` chỉ có ba nấc (`0` → `0,15` → `1,0`), và lần đầu dùng một engine là một lượt **TẢI
MODEL** (`fw-large-v3` = 2,9 GB, đo được: `stat /models/models--Systran--faster-whisper-large-v3`
= 10:14:53) trong khi job chỉ nói "nạp engine". Nay adapter báo tiến độ theo đoạn đã bóc
(`on_progress(giây_đã_tới, tổng_giây)`, throttle 2 s vì mỗi lần báo là một lượt ghi DB + một sự
kiện SSE), handler quy ra `0,15 … 0,89`, và job nói trước khi phải tải model. Ba lần mutation đã
chạy: bỏ `bao(float(s.end))`, bỏ nhánh `model_cached`, hoặc bỏ phép dò `inspect.signature` ⇒ mỗi
lần đúng một bài ĐỎ. `model_cached()` trả **ba** giá trị (`True`/`False`/`None`), không phải hai:
bản đầu của bản vá trả `False` cho MỌI job vì `spec.model_ref` là **bí danh** (`large-v3-turbo`)
còn repo thật là `mobiuslabsgmbh/...` — một câu "chưa có model" SAI còn tệ hơn im lặng.

**(b) Mười ba bài của cụm engine `http`** (`test_mt_engine_contract.py` +9,
`test_openai_base_url_env.py` +4). Nguyên nhân gốc: adapter `runtime: "http"` khai ba thuộc tính
của cổng `MtEngine` là **METHOD** thay vì `@property` — đo được trên stack thật, job translate
bằng `deepseek-web` chết ngay lô đầu với `sqlite3.InterfaceError: Error binding parameter 2 —
probably unsupported type`, vì `TranslateHandler._record_call` đọc
`getattr(engine, "model_ref")` và nhận **bound method**. `tests/test_mt_engine_contract.py` (+9
ca, gồm tham số hoá theo từng adapter) ghim HÌNH DẠNG: `engine_id`/`model_ref`/`prompt_version`
là `@property`, `supports_glossary` là method, **và** một ca đi đúng đường đã chết
(`getattr` → bind vào `llm_calls` của sqlite). Mutation đã chạy: bỏ `@property` ở `model_ref` ⇒
hai ca ĐỎ. Kèm theo: hàng `deepseek-web` được KHAI trong `registry.json` sau khi đo trên endpoint
thật, và ba bài ghim registry (`test_registry`, `test_mt_wiring`, `test_worker_phases`) được cập
nhật theo (9 → 10 engine; harness của `test_mt_wiring` vá thêm `OpenAiChatMt` +
`openai_models_available` để test không chạm mạng và không đọc môi trường của máy chạy).

Bốn bài còn lại là **`PHUDE_OPENAI_BASE_URL`** (`tests/test_openai_base_url_env.py`): cùng một hàng
`registry.json` phải chạy được ở HAI chỗ với HAI địa chỉ — chạy thẳng trên máy thì gateway ở
`127.0.0.1:8790`, còn trong container thì `127.0.0.1` là CHÍNH container. Đo được: hàng
`deepseek-web` trong `docker compose up` trả `available: false` cho tới khi compose truyền
`PHUDE_OPENAI_BASE_URL=http://host.docker.internal:8790/v1` (cùng khuôn **M-10** của `OLLAMA_HOST`,
và cùng MỘT hàm với phép dò `available` để hai chỗ không thể đọc hai địa chỉ khác nhau). Sau khi
sửa: `available: true` trong container, và một job THẬT trên clip **461 đoạn** của người dùng chạy
**`done` sau 72,5 s**, echo **1/461** đoạn.

Lần bump trước, `1298/15` → `1300/15` (**+2 bài**), do **worker chết vì một lỗi ở đường GHI SỔ**:
một lượt dọn DB tay xoá hàng `jobs` trong lúc worker đang chạy nó ⇒ đường **báo lỗi** của
`_run_one` gọi `append_job_log` và nhận `NotFound` ⇒ exception thoát khỏi `tick()` và thoát khỏi
`run_forever`, tức **luồng worker chết**; hàng đợi đứng im vĩnh viễn (`/api/status` vẫn
`queue_depth: 1`, giao diện vẫn "chờ gom lô · 0%", không lỗi nào hiện ra). Nay `run_forever` bọc
`tick()`: in vết lỗi ra stderr (đọc bằng `docker compose logs`) rồi tiếp nhịp sau — **worker SỐNG
là bất biến**, còn `tick()` gọi trực tiếp vẫn NÉM (khuôn `while worker.tick(): pass` của test
không đổi). `tests/test_worker_survives.py` (+2) ghim: job một làm hỏng `append_job_log` thì job
hai vẫn chạy `done` và stderr có `Traceback` kèm nguyên nhân; và đối chứng "vòng lặp vẫn dừng
được theo `stop_event`". Mutation đã chạy: đổi `except Exception` thành một exception hẹp hơn ⇒
bài đầu ĐỎ với đúng `NotFound: job 1 không tồn tại`.

Lần bump trước, `1291/15` → `1298/15` (**+7 bài**), do **`PHUDE_ASR_DEVICE`** — biến chọn
thiết bị ASR, thêm vì image Docker không có driver GPU nên job `asr` chết; kéo theo
`compute_type` (`int8_float16` vô nghĩa trên CPU). `tests/test_asr_device.py` (+7) ghim
cặp (thiết bị, kiểu số) và các ca: mặc định `cuda`, env `cpu` ⇒ hạ `int8`, `float32`
giữ nguyên, tham số thắng env, env rỗng ⇒ `cuda`.

Lần bump trước, **gộp nhánh `gd2-mt`** (13 commit dọn nợ P2: `M-3`, `M-4`, `M-10`..`M-14`, `P1-1`): `1289/15` → `1291/15` (**+2 bài** ròng) — thêm `tests/test_ollama_probe.py`, `tests/test_schema_llm_calls_index.py`, `tests/test_transcribe_pipeline.py` và các ca mới ở `test_api_sources.py`/`test_api_jobs_sse.py`, đồng thời `M-3` gỡ đường GHI của route export (kèm bài ghim "không ghi tệp") và `M-13` gỡ `app.state.mt_engines` cùng bài ghim nó. Bản gộp chọn cách của `gd2-mt` cho `N-9`/`M-3` (**không** `?save=1`): một tham số không người gọi trong production là khai báo chết.

Lần bump trước, `1288/15` → `1289/15` (**+1 bài**), do đóng nợ **`N-9`** (route export ghi
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

📌 **Lịch sử bump của nhánh `gd2-mt` (đợt dọn nợ P2), ghi nguyên văn.** Bốn chữ số dưới đây là số của **nhánh đó**, KHÔNG phải của cây gộp — chúng được giữ lại để không mất dấu `M-3`, `M-4`, `M-10`..`M-14` và lý do từng bài bị gỡ/đổi tên; số nền của cây gộp là khối ở TRÊN.

Sáu lần bump gần nhất, theo ĐÚNG thứ tự thời gian của commit. `819/13` → `821/13`:
đợt dọn nợ thêm `tests/test_schema_llm_calls_index.py` (2 bài chọn được, cả 2
chạy thật). `821/13` → `829/13`: đợt dọn nợ P2 (Giai đoạn 2) thêm **8** bài chọn
được — `M-11` 3 bài (`safe_basename` trần độ dài + route upload thật), `M-14` 1
bài (hai route nói cùng một câu cho lỗi engine lạ), `M-4` 1 bài (auto-forward
ghim `glossary_version`), `M-12` 3 bài (`audio_path` phải chứng minh containment
+ `is_file()`). `829/13` → `828/13`: cùng đợt P2, `M-13` **gỡ** một bài —
`test_app_exposes_the_same_mt_engines_object`, bài duy nhất ghim thuộc tính
`app.state.mt_engines` mà KHÔNG mã sản xuất nào đọc; bất biến thật của nó
("handler và composition root dùng CÙNG một dict engine") vẫn được ghim bằng
`tests/test_mt_wiring.py::test_translate_handler_is_registered_with_the_same_
engines_dict`. `828/13` → `829/13`: `M-10` thêm 1 bài ghim rằng **ba** đường
Ollama (`/api/status`, phép dò availability, `base_url` của engine) cùng đi qua
`app.config.resolve_ollama_base_url`, tức cùng tôn trọng `OLLAMA_HOST`.
`829/13` → `827/13`: cùng đợt P2, `M-3` **gỡ HAI** bài vì tiền đề của chúng là
lần GHI trên đĩa của route spec (`routes_translations._materialise` gọi
`domain.paths.resolve_within`), thứ `M-3` xoá hẳn:
`test_the_spec_route_proves_containment_before_writing` và
`test_the_spec_route_still_serves_the_body_when_containment_fails`. Hai vế của
chúng KHÔNG mất — xem khối thay thế ở cuối
`tests/test_api_export_by_translation.py`;
`test_the_spec_route_materialises_the_same_artifact_name` được ĐỔI TÊN thành
`test_the_spec_route_writes_no_artifact_to_disk` (không đổi số lượng).
`827/13` → `828/13` (bước CUỐI của đợt P2): `P1-1` thêm 1 bài vào
`tests/test_schema_llm_calls_index.py` — một ca dựng DB **v2** (schema của
`4a747e6`: đã có `translations.status` và `version='2'`, chỉ thiếu
`idx_llm_calls_job`) để ghim rằng gate `executescript(SCHEMA_SQL)` sau
`version < SCHEMA_VERSION` là HỒI QUY: nó giữ ca v1 xanh trong khi mọi DB v2
đang tồn tại vĩnh viễn không nhận index.

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
(và 59,09 s của lô 15 thẳng — phép chia chỉ rẻ hơn về SỐ LỜI GỌI). Đã đo (`20261025-batch-25`, `scripts/measure_batch_25.py`): câu "25 mục thì sạch"
**SAI** — hai lô 25 mục GIỮA clip bị chép **24/25** (id 0–24) và **25/25** (id 25–49),
hai lô sau sạch (50–74, 75–99), đuôi 15 mục sạch. Các lời gọi 25 mục sạch trước đây sạch
vì là **đuôi clip**, không phải vì cỡ ⇒ ứng viên chia lô 25/5 bị LOẠI.

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

**Hàng `deepseek-web` NAY CÓ trong `registry.json` đã ship** — vì nó đã được đo trên endpoint
thật (`whalegate serve` ở `http://127.0.0.1:8790/v1`, model `deepseek-web`): hợp đồng `lines` lô
30 ⇒ **115/115 `done`, 4 lời gọi, 13,21 s, 0 lỗi alignment, 0 chữ Hán, 0 echo, thuật ngữ 7/7**;
`lines` lô 15 ⇒ 115/115, 8 lời gọi, 33,64 s; và `json` + `response_format` lô 15 ⇒ 115/115, 8
lời gọi, 19,41 s (`data/experiments/accuracy-pipelines/20261026-spike-deepseek-web/`; đính chính
"`response_format` không tồn tại" trong báo cáo spike). Chọn `lines` vì hỏng thì ỒN, và lô 30 đo
được **không một lần thử lại**. Ví dụ `api-dich` ở trên thì **KHÔNG** có trong registry: chưa ai
đo nó — luật "engine chưa đo thì chưa khai" vẫn nguyên.

Ba điều phải nói trước khi bật nó:

1. **`default_mt` phải tiếp tục là `opus-mt`.** Đổi engine mặc định là đổi tiền đề offline
   của cả pipeline, và mọi số trong tài liệu này đo trên đường local.
2. **Văn bản phụ đề rời khỏi máy.** Đây là thay đổi về quyền riêng tư, không phải một tối
   ưu — với engine `runtime: "http"` thì nội dung clip của người dùng đi tới bên thứ ba (ở đây
   là phiên web của một tài khoản, kèm ToS của dịch vụ đó).
3. **Số đo của nó không tái lập được.** Không đặt được sampling, hành vi của dịch vụ đổi
   ngoài tầm kiểm soát. Một con số của engine `http` phải được dán nhãn như vậy, không được
   trộn vào bảng so sánh local. README của whalegate nói rõ hơn: `temperature`/`top_p`/
   `max_tokens`/`stop`/`response_format` **have no web equivalent** — nên một hợp đồng đầu ra
   dựa vào `response_format` là hợp đồng dựa vào may mắn (`lines` không dựa vào gì ngoài SỐ
   DÒNG, và hỏng thì ỒN).

`reasoning_effort` phải là **`none`** cho đường dịch: hàng `deepseek-web` khai khoá đó trong
`opts`, và đây là DỮ LIỆU ĐO ĐƯỢC chứ không phải khẩu vị — cùng một lô 5 mục, `none` cho 1,77 s /
121 token vào / **107** token ra, còn mặc định (`auto`, tức BẬT DeepThink) cho 12,55 s / 143 /
**3 203**: **30 lần token ra, 7 lần chậm**, và bản dịch KHÔNG hơn (`auto` bịa `ba ngày` đúng chỗ
`none` giữ `ba ngàn`). Dịch phụ đề không cần suy luận dài — và `cached_tokens` trong `usage` cho
thấy mỗi lượt là một lượt mới.

**Chi phí:** hàng đó khai thêm `price_in_usd_per_mtok: 0.15` / `price_out_usd_per_mtok: 0.6` (bảng
giá DeepSeek-flash mà gateway đang dùng). Nhờ vậy `GET /api/translations/{id}` trả `cost_usd` =
token ĐÃ ĐO × giá ĐÃ KHAI, và màn **Đối chiếu** nối `~$0,006` vào nhãn của bản dịch đó
(`app/domain/pricing.py`). Engine chạy trên máy không khai giá ⇒ `cost_usd: null`, **không phải
`$0,00`**: "không tính được" và "miễn phí" là hai câu khác nhau, và cột `0` ở đó nói cả hai.

`available` của hàng đó là câu trả lời THẬT: không chạy `whalegate` thì nó là `false` và giao
diện không cho chọn (không có gì khác phải sửa). Muốn đổi endpoint/khoá, hoặc không muốn hàng
này trong registry, thì trỏ `PHUDE_REGISTRY` vào một bản `registry.json` của riêng bạn.

### So sánh CHẤT LƯỢNG giữa các engine — `scripts/compare_mt_engines.py`

```powershell
.\.venv\Scripts\python.exe -B scripts\compare_mt_engines.py --so-doan 5 --out-dir ..\data\experiments\accuracy-pipelines\20261026-mt-quality
```

Nó đi qua **`TranslateHandler` của sản phẩm** (prompt p2, `echo_retry`/`echo_guard`/
`term_placeholder`, trần `max_items_per_call`), trên một repo TRONG BỘ NHỚ nên không chạm DB.
Gọi thẳng `engine.translate(...)` thì rơi về prompt mặc định **p1** — bản đã đo là chép nguyên
chữ nguồn 43/44 đoạn trên `qwen2.5-3b` — nên phép đo sẽ nói về prompt, không về engine.

**Nó KHÔNG cho BLEU/MQM**: cần bản tham chiếu của người (non-goal của repo). Nó in bản dịch để
người đọc chấm, kèm tín hiệu máy đo được (echo, chữ Hán còn, rỗng, issue QA). Và một đoạn ngắn
chỉ nói về đoạn đó — nguồn là chữ ASR thật nên có câu rác sẵn.

Lượt đo 2026-10-26, **5 đoạn đầu** của clip 20:49 (`20261026-mt-quality`, batch theo từng engine):

| engine | giây | lời gọi | echo | chữ Hán | issue QA | nhận xét đọc được |
|---|---|---|---|---|---|---|
| `deepseek-web` | **2,73** | 1 | 0 | 0 | 4 | đọc như tiếng Việt, giữ được số ("ba ngàn"), 烤冷面 → "mì nướng lạnh" |
| `hy-mt-1.5-7b` | 9,11 | 5 | 0 | 0 | 8 | trôi chảy nhất, nhưng **bịa đơn vị**: "3.000 ngày" cho 三千 |
| `opus-mt` (mặc định) | 6,71 | 1 | 0 | 0 | 3 | **rơi mất nội dung**: mất "Đông Bắc", 烤冷面 → "món thịt nướng", câu 4 rác |
| `qwen2.5-3b` | 3,74 | 1 | 0 | **1** | 4 | còn chữ Hán, bỏ sót ("ăn 11 bữa ở 吉林 khi ở 吉林") |
| `qwen2.5-7b` | 6,71 | 1 | **5/5** | **5** | 5 | chép nguyên chữ nguồn cả 5 đoạn (handler chỉ *cảnh báo*, hàng này không khai `echo_guard`) |

⚠️ Đây là **kiểm tra nhanh**, không phải phán quyết chất lượng: 5 đoạn, một clip, không có bản
tham chiếu, và hai trong năm câu nguồn đã rác sẵn từ ASR. Điều đọc được chắc chắn: `qwen2.5-7b`
ở prompt p2 vẫn chép nguồn; `opus-mt` (engine MẶC ĐỊNH) rơi nội dung; và `hy-mt` có kiểu hỏng
riêng là **bịa thêm thông tin** — nguy hiểm hơn rơi chữ, vì bản dịch vẫn đọc trôi.

### Lồng tiếng (TTS) — job `dub`, hai route, và CLI

Ba đường vào, MỘT đường chạy: `DubHandler` (`app/pipeline/dub.py`). `POST /api/dubs` xếp một
job `dub`, worker chạy nó, `GET /api/dubs/{translation_id}/download?format=` trả file;
`scripts/make_dub.py` là CLI trên cùng dữ liệu (dùng khi không muốn bật API).

```powershell
# venv RIÊNG cho TTS: vieneu kéo huggingface_hub 2.x + starlette 1.x, xung đột với transformers 4.46
.\.venv\Scripts\python.exe -m venv .venv-tts
.\.venv-tts\Scripts\python.exe -m pip install vieneu

# qua API (khuyến nghị — cùng đường với giao diện)
curl -X POST http://127.0.0.1:8620/api/dubs -H 'Content-Type: application/json' -d '{"translation_id":1,"so_dong":8,"voice":"Minh Quân"}'

# hoặc CLI
.\.venv\Scripts\python.exe -B scripts\make_dub.py --so-dong 8 --voice "Minh Quân"
```

Đo được: nạp model **62,6 s** (lần đầu, kèm tải), `infer` **1,2 s** cho một câu, ra **48 kHz**;
8 dòng → master **33,78 s** (dòng 7 đặt ở 32,46 s đúng `start`) và **5 file**
wav 3167 kB · flac 462 · mp3 793 · aac 314 · m4a 310.

Tốc độ KHÔNG phải mỗi dòng một số: `ke_hoach_toc_do` gom về thang bậc 0,05 (tối đa 1,35),
vì đo trên 14 dòng thật `take/chỗ` rải 1,00–1,62× — mỗi dòng một tốc độ thì giọng đổi nhịp liên
tục, còn một tốc độ chung thì phải lấy mức lớn nhất. 8 dòng trên dùng 5 mốc: 1,00/1,10/1,15/
1,20/1,25. Dòng nào `need > 1,35` thì handler GHI RA là "phải sửa chữ" và không tự nén quá trần.

#### Đo end-to-end qua HTTP (bản dịch #1, 4 dòng, máy Windows)

`POST /api/dubs {"translation_id":1,"so_dong":4}` → job **`done` sau 6,1 s** (model đã cache từ
lượt trước; lần đầu phải cộng 62,6 s nạp). Năm file ra `data/output/dubs/`, `ffprobe` đọc lại:

| file | dài | mẫu | kênh | codec | byte |
|---|---|---|---|---|---|
| `dub-1.wav` | 5,800 s | 48000 Hz | 1 | pcm_s16le | 556 844 |
| `dub-1.flac` | 5,800 s | 48000 Hz | 1 | flac | 174 712 |
| `dub-1.mp3` | 5,800 s | 48000 Hz | 1 | mp3 | 140 589 |
| `dub-1.m4a` | 5,800 s | 48000 Hz | 1 | aac | 107 277 |
| `dub-1.aac` | 5,242 s | 48000 Hz | 1 | aac | 107 289 |

Canvas 5,800 s = `end` của dòng CUỐI (bốn dòng: 0,00–1,08 / 1,08–2,52 / 2,52–3,44 / 3,44–5,80).
Đo biên tiếng trên wav (năng lượng cửa sổ 20 ms, ngưỡng 0,02, gộp khoảng lặng < 150 ms) ra
**3 khối**: `0,080 → 2,140` · `2,520 → 3,040` · `3,440 → 5,300`. Hai khối sau khớp `start` của
dòng 2 và dòng 3 **tới mili giây** (2,520 / 3,440); khối đầu là dòng 0+1 dính nhau vì chúng liền
mạch, và nó **trễ 80 ms** — phần đệm còn lại sau `trong_im_lang`, không phải sai `start`.

⚠️ `.aac` ngắn hơn 0,558 s: đó là **ADTS** (`-f adts`), mỗi frame tự mô tả nên `ffprobe` báo
theo frame đã đọc; `m4a` cùng codec aac giữ đủ 5,800 s. Đừng đọc chênh lệch đó thành mất tiếng.

#### Hai lỗi ĐO ĐƯỢC của bản đầu, và vì sao test cũ không bắt

1. **Đường dẫn tệp take chết trước khi handler đọc.** `chay_tts_batch` tự dựng
   `TemporaryDirectory`, ghi wav vào đó, trả ĐƯỜNG DẪN về, rồi thư mục bị xoá ngay khi hàm trả
   về ⇒ mọi job `dub` chết ở 40% với
   `LibsndfileError: Error opening '…\Temp\tts-5cs2do_f\wav\00000.wav': System error`
   (Linux: `No such file`). Đo cô lập đúng khuôn `with TemporaryDirectory(...)`:
   `trong with: ton tai = True` / `sau with: ton tai = False`. Nay thư mục tạm do **handler**
   sở hữu và `tts_runner` nhận `out_dir` làm tham số; ghim bằng
   `test_handler_doc_duoc_take_vi_thu_muc_con_song`. **Vì sao 4 bài cũ vẫn xanh:** runner giả
   tự dựng thư mục riêng bên ngoài, nên đường dẫn của nó luôn sống — fixture vô tình thoả hợp
   đồng mà sản phẩm vi phạm.
2. **Đường mặc định của TTS là đường Windows, trong image Linux.**
   `…/.venv-tts/Scripts/python.exe` không tồn tại trên Linux, nên job được nhận rồi `failed` ở
   5% sau khi người dùng đã chờ. Nay `TTS_PYTHON` chọn theo `os.name`, và `POST /api/dubs`
   **từ chối sớm bằng 409** qua `DubHandler.san_sang()` thay vì để job chết — đo được trong
   container: `{"detail":"máy này chưa có TTS: không thấy /app/.venv-tts/bin/python — …"}` với
   `queue_depth` **0 → 0**. Kèm theo: `.venv-tts` (751 MB, 24 116 tệp, `pyvenv.cfg` ghi
   `home = C:\Users\…`) bị `COPY . .` mang vào image; thêm nó vào `backend/.dockerignore` ⇒
   image **10,8 GB → 9,64 GB**. ⚠️ `.dockerignore` ở GỐC repo KHÔNG có tác dụng: build context
   của `api` là `./backend`.

`ponytail:` chưa có — trộn với tiếng gốc (ducking, người dùng đã loại), gọi lại engine dịch để
rút chữ, TTS trong container (cần image riêng có `vieneu`, không phải chép venv Windows), và GPU
cho TTS (đang chạy CPU).
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

### Thiết bị ASR: `PHUDE_ASR_DEVICE` (mặc định `cuda`)

Adapter `faster-whisper` chọn thiết bị theo thứ tự: tham số `device=` → biến môi trường
**`PHUDE_ASR_DEVICE`** → `"cuda"`. Biến này tồn tại vì một chỗ hỏng ĐO ĐƯỢC: image Docker
không có driver GPU, nên job `asr` đầu tiên chết với *"CUDA driver version is insufficient"*.

Đổi thiết bị **kéo theo** `compute_type`: `int8_float16` chỉ có nghĩa trên GPU, CTranslate2
từ chối nó trên CPU, nên `device_and_compute_type()` tự hạ về `int8`. Hai vế là một cặp,
không phải hai biến rời — cặp đó được ghim ở `tests/test_asr_device.py` (7 bài).

### Lượt chạy THẬT đầu-cuối trên cây đã gộp (2026-10-25)

Bài `test_e2e_translate.py` ở trên thay engine bằng đồ giả. Lượt dưới đây **không
thay gì**: wav thật (278 s, `data/media/8f4b5304daf42569.wav`) → `POST
/api/sources/upload` → `ingest` → `asr` (`fw-large-v3-turbo`, model thật) →
`translate` (`opus-mt`, in-process) → `GET /api/export/{id}?format=srt`, trên
backend thật ở cổng **8622** với DB **scratch ngoài repo**:

```
jobs: [[1, "ingest", "done"], [2, "asr", "done"], [3, "translate", "done"]]
transcript   id=1 status=translated segments=105
translation  id=1 engine=opus-mt status=done
export       200 bytes=10624 files_written=0
srt head     1 / 00:00:00,000 --> 00:00:01,080 / Như một tác phẩm nghệ thuật.
status       {"vram": 1143, "vram_unit": "MiB", "ollama": "up", ...}
```

Ba thứ lượt này chứng minh **trên sản phẩm**, không phải trên test: chuỗi ba job
chạy hết và ghi đúng trạng thái; `GET /api/export/{id}` trả SRT và **không ghi tệp
nào** (`files_written=0` — nợ `N-9` đóng đúng trên đường thật); `/api/status` trả
**VRAM thật kèm đơn vị**. Nó **không** chứng minh chất lượng bản dịch (chưa ai
chấm) và chỉ đo trên **một** clip.

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


