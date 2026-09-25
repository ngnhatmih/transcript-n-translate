# phu-de-lab — Thiết kế

**Ngày:** 2026-09-25 · **Bản:** v3 (thêm ràng buộc từ thiết kế UI/UX)
**Trạng thái:** Chờ người dùng duyệt lần cuối

Một web app chia thành hai bàn thao tác cho một dây chuyền hai bước:
**Workspace 1** bóc băng audio/video ra văn bản kèm timestamp, **Workspace 2** dịch văn bản đó sang tiếng Việt. Mỗi workspace đổi được model độc lập.

> **File thiết kế giao diện tách riêng:** `2026-09-25-phu-de-lab-ui-design.md`.
> File này ghi *hệ thống làm gì*; file kia ghi *người dùng nhìn thấy gì*.

---

## 0. Lịch sử thay đổi

### v2 → v3 — ràng buộc từ thiết kế UI/UX

Soi lại 10 tính năng qua lăng kính giao diện (`frontend-design`, `frontend-developer`) tìm ra
10 phát hiện, trong đó 4 mức Cao. Bốn cái Cao làm **đổi cả bố cục lẫn backend**, nên chúng được
áp vào file này chứ không nằm yên trong file UI.

| Mã | Phát hiện | Mức | Xử lý |
|---|---|---|---|
| U1 | Bố cục hai pane không chịu được nhiều source, trong khi §7.2 lại giả định nhiều job | Cao | §9.1 ba vùng, thêm vùng KÊNH |
| U5 | Không có trình phát media → tín hiệu `suspect` báo lỗi mà không sửa được | Cao | §9.2 transport + §11 endpoint media có `Range` |
| U3 | Tiếng Việt dài gấp 2–3× tiếng Trung, hai pane tách rời nên không thấy lỗi | Cao | §9.1 chế độ Đối chiếu + CPS, §3.1 `readability.py` |
| U10 | Không có bàn phím cho một công cụ dùng hàng giờ | Cao | §9.3 bảng phím tắt là yêu cầu |
| U2 | Job bị đẩy ra sau mà không thấy hàng đợi | Trung | §9.1 vùng HÀNG ĐỢI + lý do chờ |
| U4 | Chỉnh timestamp bằng chuột | Trung | §9.3 nudge + đặt mốc tại đầu đọc |
| U6 | Ảo hoá + sửa trực tiếp làm mất focus | Trung | §9.2 ghim dòng đang sửa |
| U7 | N bản dịch dạng tab sẽ nổ | Trung | §9.2 segmented + ghim bản B |
| U8 | Trạng thái rỗng/lỗi chưa được thiết kế | Trung | §9.2 Ollama mất kết nối là trạng thái hạng nhất |
| U9 | Tiến độ không đồng nhất giữa các công đoạn | Thấp | File UI/UX §5.4, hai thanh tiến độ |

Thêm một ràng buộc mới do phải chạy offline: **font self-host, không CDN** (§9.4).

### v1 → v2 — đánh giá kiến trúc / hiệu năng / AI-ML

v1 được đánh giá lại qua ba lăng kính (`architecture-patterns`, `application-performance-performance-optimization`, `ai-ml`). 18 phát hiện, trong đó 9 mức Cao. Bản v2 sửa hết.

| Mã | Phát hiện | Mức | Xử lý |
|---|---|---|---|
| A1 | `pipeline/` gọi thẳng engine + DB → domain không test được nếu không có model | Cao | §3.1 phân tầng hexagonal nhẹ |
| A2 | `stale` so sánh timestamp — mâu thuẫn với chính pattern `charbook_version` được viện dẫn | Cao | §5.3 chuyển sang `version` |
| A3 | Không có state machine cho job | Trung | §5.4 |
| A4 | Không có phục hồi sau crash → job treo vĩnh viễn ở `running` | Cao | §5.4 trạng thái `interrupted` |
| A5 | JSON blob chưa nói rõ là đánh đổi có ý thức | Trung | §5.6 |
| A6 | `workspace` chưa nói rõ chỉ là nhãn | Thấp | §5.6 |
| P1 | Mâu thuẫn "cache model" vs `keep_alive: 0` → swap model mỗi job | Cao | §7.2 hàng đợi theo giai đoạn |
| P2 | Chia lô dịch theo **số segment** là sai đơn vị | Cao | §8.7.1 ngân sách token |
| P3 | Không có baseline, không một con số nào | Cao | §10 eval + benchmark |
| P4 | Bỏ sót batched inference của faster-whisper | Trung | §8.2 |
| P5 | `jobs.log` TEXT không giới hạn → phình DB | Trung | §5.5 log ra file |
| P6 | Transcript dài render hết vào DOM sẽ giật | Trung | §9 ảo hoá danh sách |
| P7 | Không có ETA | Thấp | §9 |
| M1 | **Không đánh giá chất lượng** → "đổi model" thành cảm tính | Rất cao | §10 subsystem `eval/` |
| M2 | Không lưu vết lượt gọi model; prompt không có chỗ ở, không version | Cao | §5.5 `llm_calls`, §8.7.3 prompts |
| M3 | Bỏ phí `avg_logprob`/`no_speech_prob` để phát hiện đoạn bịa | Cao | §8.4 |
| M4 | Glossary chỉ nhập tay, bỏ lỡ pattern đã có ở `truyen-dich` | Trung | §14 — YAGNI, cân nhắc lại |
| M5 | Prompt injection | Thấp | §14 — không áp dụng |

**Ba skill thành thật về phạm vi áp dụng:** ~60% của `application-performance-performance-optimization` (CDN, edge, PWA, k6, APM, SLO) và gần như toàn bộ phần RAG/vector-DB/agent của `ai-ml` **không áp dụng** cho một app local một người dùng. Chúng được bỏ qua có ý thức, không phải bỏ sót.

---

## 1. Mục tiêu & phạm vi

### Mục tiêu

1. Nạp liệu bằng **file tải lên** hoặc **link video online**.
2. **Workspace 1**: audio → văn bản có timestamp cấp đoạn (word-level là bonus).
3. **Workspace 2**: văn bản → bản dịch tiếng Việt, xuất được phụ đề.
4. **Đổi model tự do** ở cả hai workspace, không mất kết quả cũ.
5. Chạy **hoàn toàn local** trên một máy RTX 3070 8GB.
6. **Đo được chất lượng model**, không chỉ "chạy được".

### Ngôn ngữ

Nguồn: **tiếng Trung (chính)** và **tiếng Anh**. Đích: **tiếng Việt**.

### Không thuộc phạm vi (xem §14)

Ghi âm trực tiếp từ mic · crawler hàng loạt · watch-folder · so sánh A/B tự động · tách giọng khỏi nhạc nền.

---

## 2. Ràng buộc môi trường

Đo trực tiếp trên máy đích ngày 2026-09-25:

| Thành phần | Giá trị |
|---|---|
| GPU | NVIDIA RTX 3070 — **8GB VRAM**, driver 566.36, CUDA 12.7 |
| CPU | AMD Ryzen 7 7800X3D, 16 luồng |
| Ổ đĩa | `C:` 52GB trống · `D:` 61.6GB trống |
| Đã có | Python 3.10.5, pip, Node v24, pnpm 11, ffmpeg + ffprobe, git, docker, winget |
| Còn thiếu | Ollama, yt-dlp, toàn bộ thư viện ML (chưa có torch) |
| Không cần | cmake / MSVC (quyết định ở §3.2) |

**Ràng buộc cứng:** 8GB VRAM phải chia cho hai workspace. Đây là ràng buộc định hình toàn bộ kiến trúc.

**Model đặt ở `D:\models\`** để không ăn vào 52GB còn lại của `C:`.

---

## 3. Kiến trúc

### 3.1 Phân tầng — hexagonal nhẹ

```
backend/app/
├── domain/                  # ⛔ KHÔNG import gì ngoài stdlib
│   ├── models.py            # Segment, Transcript, Translation, Job, Term
│   ├── segmentation.py      # gộp/cắt đoạn, đánh số lại
│   ├── batching.py          # chia lô theo ngân sách token
│   ├── staleness.py         # quy tắc version → stale
│   ├── qa_rules.py          # QA tầng 1, thuần code
│   ├── readability.py       # CPS (tốc độ đọc) + ngưỡng cảnh báo
│   └── job_state.py         # state machine
├── ports/                   # giao diện, KHÔNG hiện thực
│   ├── asr.py · mt.py · repos.py · governor.py · clock.py
├── adapters/                # hiện thực cụ thể
│   ├── asr/faster_whisper.py · asr/sensevoice.py
│   ├── mt/opus_mt.py · mt/ollama_mt.py
│   ├── persist/sqlite_repos.py
│   └── governor/vram.py
├── pipeline/                # use case: ráp domain + ports
│   ├── ingest.py · transcribe.py · translate.py · qa.py · export.py
├── api/                     # FastAPI routes + SSE
├── worker.py                # hàng đợi theo giai đoạn
└── main.py
```

**Dependency rule:** `adapters → ports ← domain`. `pipeline` biết cả ba. `api` chỉ biết `pipeline` + `ports`.

**Kiểm chứng bằng test, không bằng lời hứa:** một test khẳng định `domain/` không import bất cứ gì từ `adapters/`, `ports/`, `fastapi`, `torch`, `httpx`. Vi phạm → test đỏ.

**Vì sao:** đây là thứ làm cho §12 "E2E với fake engine" trở thành hiển nhiên thay vì phải chế, và làm cho logic chia lô / đánh stale / QA test được mà không cần nạp model nào.

### 3.2 Quyết định runtime: Python monolith + Ollama lo phần LLM

```
┌─ frontend/ (Next.js) ────────────────────────────────┐
│  React 19 · Tailwind v4 · Radix/shadcn cho HÀNH VI │
│  rewrite /api/* → http://127.0.0.1:8620              │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP + SSE
┌───────────────────────▼──────────────────────────────┐
│  backend/ (FastAPI + SQLite)                         │
│  domain ← ports ← adapters · pipeline · api · worker  │
└──────────┬──────────────────────┬────────────────────┘
           │ in-process           │ HTTP
    ┌──────▼───────┐       ┌──────▼──────────┐
    │ faster-whisper│      │ Ollama (nền)    │
    │ SenseVoice    │      │ Qwen2.5 · HY-MT │
    │ OPUS-MT       │      │ keep_alive      │
    └───────────────┘      └─────────────────┘
```

**Lý do chọn:** Ollama có `keep_alive` — tự đổ model sau khi rảnh, và nhận lệnh đổ ngay. Đây là cơ chế giải bài toán tranh chấp 8GB VRAM mà không phải tự viết. Đường cài trên Windows chắc chắn chạy (installer, không build C++).

**Phương án đã loại:**

- *Tất cả in-process (`llama-cpp-python`)* — không có wheel Windows sẵn, phải tự build với CUDA, cần MSVC + cmake mà máy chưa có.
- *Microservices* — phức tạp gấp ~3, thừa cho một máy một người dùng, và khó debug VRAM hơn chứ không dễ hơn.

### 3.3 Nguyên tắc bất di bất dịch

> **Toàn bộ xử lý model nằm trong `backend/`.** Frontend không bao giờ đụng tới model, chỉ gọi API và render.

---

## 4. Cấu trúc thư mục

```
C:\Users\Admin\Desktop\ngn\deepseek\phu-de-lab\
├── backend/
│   ├── .venv/                     # venv riêng
│   ├── app/                       # (chi tiết ở §3.1)
│   ├── eval/                      # (chi tiết ở §10)
│   ├── prompts/                   # prompt dịch, có version trong tên file
│   │   ├── mt_qwen_v1.md · mt_hymt_v1.md · mt_qa_v1.md
│   ├── registry.json              # khai báo engine (sửa để thêm model)
│   ├── requirements.txt
│   └── tests/
├── frontend/                      # Next.js 16 App Router
├── data/
│   ├── media/                     # file gốc + wav đã extract
│   ├── logs/job-<id>.log          # log job, tách khỏi DB
│   ├── output/                    # SRT/VTT/ASS xuất ra
│   └── app.db                     # SQLite
└── docs/superpowers/{specs,plans}/
```

**Biến môi trường:**

```
OLLAMA_MODELS = D:\models\ollama
HF_HOME       = D:\models\hf
PHUDE_DB      = ./data/app.db
PHUDE_PORT    = 8620
```

Cổng **8620** cho backend (tránh 8619 của `truyen-dich`), **3100** cho Next.js dev (tránh 3000).

---

## 5. Mô hình dữ liệu

SQLite, một file `data/app.db`.

```sql
CREATE TABLE sources (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL CHECK(kind IN ('file','url')),
  origin      TEXT NOT NULL,            -- tên file gốc hoặc URL
  media_path  TEXT NOT NULL,
  audio_path  TEXT,                     -- wav 16k mono
  duration    REAL,
  lang        TEXT,                     -- 'zh' | 'en'
  created_at  TEXT NOT NULL
);

CREATE TABLE transcripts (
  id          INTEGER PRIMARY KEY,
  source_id   INTEGER NOT NULL REFERENCES sources(id),
  engine      TEXT NOT NULL,            -- id trong registry.json
  lang        TEXT NOT NULL,
  segments    TEXT NOT NULL,            -- JSON array (§5.2)
  version     INTEGER NOT NULL DEFAULT 1,   -- tăng mỗi lần ghi segments
  status      TEXT NOT NULL DEFAULT 'draft',  -- draft|reviewed|translated
  created_at  TEXT NOT NULL
);

CREATE TABLE translations (
  id                 INTEGER PRIMARY KEY,
  transcript_id      INTEGER NOT NULL REFERENCES transcripts(id),
  transcript_version INTEGER NOT NULL,   -- bản transcript đã dịch
  engine             TEXT NOT NULL,
  target_lang        TEXT NOT NULL DEFAULT 'vi',
  segments           TEXT NOT NULL,
  prompt_version     TEXT NOT NULL,
  glossary_version   INTEGER,
  qa_issues          TEXT,               -- JSON array
  tokens_in          INTEGER,
  tokens_out         INTEGER,
  duration_ms        INTEGER,
  created_at         TEXT NOT NULL
);

CREATE TABLE jobs (
  id               INTEGER PRIMARY KEY,
  workspace        INTEGER NOT NULL CHECK(workspace IN (1,2)),
  type             TEXT NOT NULL,        -- ingest|asr|translate|export
  engine           TEXT,
  phase            TEXT,                 -- khoá giai đoạn, §7.2
  state            TEXT NOT NULL,        -- §5.4
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  attempts         INTEGER NOT NULL DEFAULT 0,
  progress         REAL NOT NULL DEFAULT 0,
  log_tail         TEXT NOT NULL DEFAULT '',  -- 100 dòng cuối cho UI
  log_path         TEXT,                 -- data/logs/job-<id>.log
  error            TEXT,
  payload          TEXT,                 -- JSON tham số
  created_at       TEXT NOT NULL,
  started_at       TEXT,
  finished_at      TEXT
);

CREATE TABLE llm_calls (
  id             INTEGER PRIMARY KEY,
  job_id         INTEGER,
  engine         TEXT NOT NULL,
  model_ref      TEXT,
  prompt_version TEXT,
  tokens_in      INTEGER,
  tokens_out     INTEGER,
  duration_ms    INTEGER,
  ok             INTEGER NOT NULL,
  error          TEXT,
  created_at     TEXT NOT NULL
);

CREATE TABLE glossary (
  id          INTEGER PRIMARY KEY,
  lang        TEXT NOT NULL,
  term        TEXT NOT NULL,
  translation TEXT NOT NULL,
  note        TEXT,
  approved    INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  UNIQUE(lang, term)
);

CREATE TABLE settings ( key TEXT PRIMARY KEY, value TEXT NOT NULL );
```

### 5.2 Hình dạng một segment

```json
{
  "i": 0,
  "start": 1.02,
  "end": 4.38,
  "text": "大家好",
  "words": [{"w": "大家", "s": 1.02, "e": 2.10}],
  "emotion": "happy",
  "events": ["bgm"],
  "speaker": null,
  "avg_logprob": -0.42,
  "no_speech_prob": 0.03,
  "suspect": false
}
```

`words`, `emotion`, `events`, `speaker`, `avg_logprob`, `no_speech_prob` đều **tuỳ chọn** — engine nào sinh được mới có. Sau khi dịch, mỗi phần tử có thêm `"t"` là bản dịch và `"qa"` là danh sách cảnh báo.

### 5.3 `stale` dùng version, không dùng timestamp

```
stale = (translations.transcript_version < transcripts.version)
```

`stale` là **giá trị tính**, không lưu cột. Bỏ hẳn `stale` và `edited_at` của v1.

UI hiện được *"dịch từ bản v3 · hiện tại v5"* — thông tin mà cách so sánh timestamp không bao giờ đưa ra được. Đây đúng là pattern `charbook_version` của `truyen-dich`, lần này dùng cho thật.

### 5.4 State machine của job

```
queued ──► running ──► done
   │          │
   │          ├──► failed ──► queued   (chạy lại, attempts + 1)
   │          └──► interrupted          (phát hiện lúc khởi động)
   └──► cancelled                        (huỷ khi còn trong hàng đợi)

running + cancel_requested = 1 ──► cancelled  (worker tự dừng ở checkpoint)
```

Hai đường vào `cancelled`:
1. **Từ `queued`** — job chưa chạy, huỷ là xong ngay.
2. **Từ `running`** — đặt `cancel_requested = 1`; worker kiểm tra cờ ở ranh giới mỗi lô rồi tự dừng. Không có đường nào kill tiến trình.

- **Huỷ là hợp tác, không phải kill.** Worker kiểm tra `cancel_requested` ở ranh giới mỗi lô.
- **Lúc khởi động**, mọi job đang `running` bị chuyển thành `interrupted` — không bao giờ còn job treo vĩnh viễn.

### 5.5 Log tách khỏi DB

`jobs.log` (TEXT, không giới hạn) của v1 → **file** `data/logs/job-<id>.log`. Bảng `jobs` chỉ giữ `log_tail` 100 dòng cuối cho UI.

Lý do: video 2 giờ + progress yt-dlp + log từng lô có thể phình hàng chục MB trong **một dòng** SQLite, mà UI lại đọc bảng đó liên tục qua SSE.

### 5.6 Hai đánh đổi ghi rõ là có ý thức

- **`segments` là JSON blob.** Không truy vấn được "mọi segment chứa X". Chấp nhận: quy mô nhỏ, không có nhu cầu đó.
- **`workspace` chỉ là nhãn** phân loại job cho UI. **Không** có bảng `workspaces`, **không** có hai backend.

### 5.7 Vì sao `translations` là N dòng trên 1 transcript

**Đổi model dịch = thêm một dòng, không ghi đè.** Nhờ vậy việc so sánh kết quả giữa các model là việc của UI, không phải của kiến trúc.

---

## 6. Engine registry & ma trận model

`registry.json` là nguồn sự thật duy nhất. **Thêm model mới = sửa JSON, không đụng pipeline, không đụng UI** — frontend đọc qua `GET /api/registry`.

```json
{
  "asr": [
    {
      "id": "fw-large-v3-turbo",
      "label": "Faster-Whisper large-v3-turbo",
      "runtime": "inprocess",
      "model_ref": "large-v3-turbo",
      "vram_mb": 1600,
      "langs": ["zh", "en"],
      "capabilities": {
        "timestamps": true, "word_timestamps": true,
        "confidence": true, "emotion": false, "batch_infer": true
      },
      "opts": { "batch_size": 8 }
    }
  ],
  "mt": [
    {
      "id": "hy-mt-1.5-7b",
      "label": "HY-MT1.5-7B (Hunyuan-MT)",
      "runtime": "ollama",
      "model_ref": "hy-mt1.5-7b:q4_K_M",
      "vram_mb": 5200,
      "langs": ["zh", "en"],
      "capabilities": {
        "glossary_prompt": false, "glossary_patch": true,
        "chimera": true, "batch_json": true
      }
    }
  ]
}
```

### Workspace 1 — ASR

| id | Ngôn ngữ | Timestamp | VRAM |
|---|---|---|---|
| `fw-small` | zh/en | đoạn + từ | ~500MB |
| `fw-medium` | zh/en | đoạn + từ | ~1500MB |
| `fw-large-v3-turbo` | zh/en | đoạn + từ | ~1600MB (int8) |
| `sensevoice-small` | zh/yue/en/ja/ko | đoạn (qua VAD + căn chỉnh) | ~1000MB |

SenseVoice có thêm khả năng Faster-Whisper không có: **nhận cảm xúc + sự kiện âm thanh** (cười, vỗ tay, nhạc nền), lưu vào metadata của segment.

> **Moonshine bị loại khỏi workspace 1.** Chỉ hỗ trợ tiếng Anh và **không sinh timestamp** — không thoả yêu cầu cứng về timestamp cấp đoạn. Đây là model cho voice command on-device, không phải cho phụ đề.

### Workspace 2 — Dịch

| id | Runtime | VRAM | Đặc điểm |
|---|---|---|---|
| `opus-mt` | in-process (Marian) | CPU | tức thì, dịch từng câu rời, **không glossary** |
| `qwen2.5-3b` | Ollama | ~2500MB | nhanh, có glossary/văn phong |
| `qwen2.5-7b` | Ollama | ~5200MB | chủ lực: ngữ cảnh dài, glossary, giữ format |
| `hy-mt-1.5-7b` | Ollama | ~5200MB | chuyên dịch, sát nghĩa; prompt ngắn, kém tuân lệnh |

> **Chimera là một CHẾ ĐỘ của `hy-mt-1.5-7b`, không phải engine riêng.** Bật bằng checkbox; sinh 6 ứng viên rồi gọi thêm một lượt để pha. Chạy tuần tự nên **VRAM không tăng**, chỉ chậm ~7×.

### Adapter interface

```python
class ASREngine(Protocol):
    def transcribe(self, audio_path: str, lang: str, opts: dict) -> list[Segment]: ...

class MTEngine(Protocol):
    def translate(self, segments: list[Segment], glossary: list[Term],
                  opts: dict) -> tuple[list[Segment], list[Issue], CallStats]: ...
```

`CallStats` (tokens, ms) chảy vào bảng `llm_calls`. Pipeline không biết gì về engine cụ thể.

---

## 7. Điều phối VRAM & hàng đợi

### 7.1 Vấn đề

v1 mắc lỗi tự mâu thuẫn: §7.2 nói "cache lại model gần nhất", §7.3 nói "ra lệnh đổ ngay". Với `auto_forward` BẬT, dây chuyền tự nhiên là ASR → MT → ASR → MT… **mỗi vòng là một lần đổ + một lần nạp.** Nạp qwen2.5-7B Q4 từ đĩa mất 5–15s, faster-whisper turbo 3–8s → với video ngắn, nạp model chiếm **20–40% tổng thời gian**.

### 7.2 Hàng đợi theo giai đoạn

Worker giữ `current_phase`. Vòng lặp:

1. Còn job `queued` thuộc `current_phase` → chạy cái cũ nhất.
2. Hết → chọn giai đoạn của job `queued` cũ nhất, đặt làm `current_phase`, **swap model một lần**.
3. Hàng đợi rỗng → idle, giữ model nóng theo `keep_alive`.

**"Giai đoạn" là cặp (loại job, engine), không phải `asr`/`mt`:**

```
asr:fw-large-v3-turbo        translate:qwen2.5-7b
asr:sensevoice-small         translate:hy-mt-1.5-7b
ingest:-      export:-       translate:opus-mt
```

> **ĐÍNH CHÍNH (R28).** Bản đầu của mục này ghi nhãn minh hoạ là `mt:ollama:qwen2.5-7b` — **sai hai
> đường**. (a) Loại job dịch viết là **`translate`**, không phải `mt`: `Job.type ∈ {ingest, asr,
> translate, export}` và khoá do `phase_of(job_type, engine)` sinh ra, nên khoá thật của MT là
> `translate:<engine-id>`. (b) Nhãn có thêm `runtime` (`ollama`/`inprocess`) là **thừa** — id engine
> đã phân biệt runtime rồi, nên khoá chỉ có hai phần.
> Lỗi này đã lan vào code: `EngineSpec.phase_key` trả `f"{kind}:{id}"` ⇒ `mt:<id>`, **lệch cả 4 engine
> MT** so với khoá mà `jobs.phase` thực sự lưu. Nguy hiểm ở chỗ 4 engine ASR **khớp đúng**, nên hợp
> đồng trông như đang được thoả nếu chỉ thử với ASR. Đã sửa ở T8 (uỷ quyền cho `phase_of`).

Vì người dùng đổi được model **từng job**, nếu file A dùng turbo và file B dùng SenseVoice thì gom theo `asr` vẫn phải swap. Gom theo cặp (loại, model) thì số lần swap = **số cặp khác nhau đang chờ**, không phải số job.

**Kết quả:** 1 file → không chậm thêm chút nào. N file → 2 lần swap thay vì 2N.

**UI bắt buộc giải thích** (không thì người dùng tưởng app treo):
- Header: `Giai đoạn hiện tại: ASR · Faster-Whisper turbo`
- Mỗi job đang chờ: `chờ gom lô cùng giai đoạn`

### 7.3 Chính sách model

| Runtime | Nạp | Đổ |
|---|---|---|
| ASR (in-process) | khi vào giai đoạn asr | khi rời giai đoạn asr |
| MT (Ollama) | khi Ollama nhận request đầu | `keep_alive` 5 phút, hoặc `keep_alive: 0` khi worker cần GPU cho ASR |

### 7.4 Chế độ song song

Tuỳ chọn, **MẶC ĐỊNH TẮT**. Cho phép 1 job ASR + 1 job MT cùng lúc, **chỉ khi** tổng VRAM ước tính < 7000MB. Vượt ngưỡng → tự hạ về tuần tự và ghi rõ lý do vào log job.

### 7.5 Ngân sách VRAM tham chiếu

| Tổ hợp | VRAM | Kết luận |
|---|---|---|
| ASR một mình | ~1.6GB | thoải mái |
| MT một mình (Qwen2.5-7B) | ~5.2GB | thoải mái |
| ASR + MT song song | ~6.8GB | vừa khít — cộng ~0.8GB desktop = 7.6/8GB, **rủi ro** |

Ước tính VRAM lấy tĩnh từ `registry.json` (`vram_mb`). Mục tiêu chỉ là chặn OOM.

---

## 8. Pipeline

### 8.1 Ingest

| Bước | Việc |
|---|---|
| File | Upload → `data/media/<sha256>.<ext>` |
| URL | `yt-dlp` tải về, ghi tiến độ % vào log job |
| Chuẩn hoá | `ffprobe` lấy thời lượng → `ffmpeg -vn -ac 1 -ar 16000 -c:a pcm_s16le` → `<sha256>.wav` |

### 8.2 ASR — Faster-Whisper

1. VAD Silero cắt khoảng lặng (`vad_filter=True`) — chống ảo giác lặp câu.
2. `language` **ghim cứng** (`zh` hoặc `en`).
3. `condition_on_previous_text=False` — giảm lặp.
4. `initial_prompt` = thuật ngữ glossary tiếng nguồn.
5. `word_timestamps=True`.
6. **`BatchedInferencePipeline`**, `batch_size` từ registry (mặc định 8), tự giảm nếu OOM.

### 8.3 ASR — SenseVoice

1. FunASR pipeline: VAD → SenseVoice-Small → dấu câu (`ct-punc`) → căn chỉnh timestamp.
2. `use_itn=True` (số ra chữ số).
3. Tag cảm xúc/sự kiện vào metadata segment, **không nhét vào text phụ đề** trừ khi bật tuỳ chọn.

### 8.4 Tín hiệu tin cậy

- Lưu `avg_logprob` + `no_speech_prob` vào segment.
- `suspect = no_speech_prob > 0.6 or avg_logprob < -1.0`.
- UI **đánh dấu bằng vân chéo ở lề** (KHÔNG tô đỏ — lý do ở §9.2) + nút "nhảy tới đoạn nghi ngờ kế tiếp".
- SenseVoice: dùng tag sự kiện thay thế (có `bgm` → cảnh báo đoạn đó dễ sai).
- Ngưỡng nằm trong `domain/qa_rules.py`, chỉnh được.

### 8.5 Hậu xử lý chung (mọi engine)

- Gộp đoạn < 0.8s vào đoạn kề.
- Cắt đoạn quá dài (> 7s hoặc > 2 dòng × 42 ký tự) tại ranh giới từ gần nhất.
- Bỏ marker ảo giác, chuẩn hoá khoảng trắng, đánh số lại `i` từ 0.

### 8.6 Bàn giao

`transcripts.status`: `draft` → `reviewed` → `translated`

- **`auto_forward` mặc định BẬT.** ASR xong → tự tạo job translate ở workspace 2.
- Nút **"Giữ lại để sửa"** tắt `auto_forward` cho riêng job đó.
- **Sửa transcript sau khi đã dịch** → `transcripts.version` tăng → mọi bản dịch có `transcript_version` cũ tự thành `stale` (§5.3), UI hiện nhãn + nút "dịch lại".

### 8.7 Dịch

**8.7.1 Chia lô theo ngân sách token — không theo số segment**

v1 chia "15–25 segment". Đó là **sai đơn vị**: 25 segment × 60 ký tự ≈ 500 token, còn 25 segment × 300 ký tự ≈ 4000 token → chậm gấp 8 và dễ hỏng JSON.

```
ngân sách lô = 1200 token đầu ra   (hằng số, hiệu chỉnh bằng đo thật ở GĐ1b)
ước lượng    = số ký tự nguồn × hệ_số   (hệ_số ban đầu 1.0 — PHẢI ĐO, không đoán)
trần phụ     = 30 segment/lô (chặn rủi ro hỏng JSON khi nhiều mục)
```

Kèm **2 segment trước và 2 sau làm ngữ cảnh** (không dịch, chỉ để hiểu).

**8.7.2 Chiến lược prompt theo engine — chỗ dễ sai nhất**

| Engine | Glossary | Prompt |
|---|---|---|
| Qwen2.5 | **nhét vào system prompt** | system: vai trò + quy tắc xưng hô + glossary; user: lô JSON |
| HY-MT1.5 | **KHÔNG nhét prompt** — hậu kiểm + vá tìm-thay-thế | đúng format chính thức, cực ngắn |
| OPUS-MT | không hỗ trợ, UI cảnh báo | không prompt, dịch từng segment |

HY-MT1.5 kém tuân lệnh; nhồi glossary vào prompt dễ làm hỏng cả bản dịch. Với nó, glossary đi đường **hậu kiểm**.

**8.7.3 Prompt có version**

Prompt lưu ở `backend/prompts/*.md`, version trong tên file (`mt_qwen_v1.md`). Mỗi bản dịch ghi `prompt_version` → đổi prompt thì biết ngay bản dịch nào sinh từ prompt nào. Prompt là **tài sản quan trọng nhất** của dự án; nó phải có chỗ ở và có version.

**8.7.4 Tự chữa JSON**

Yêu cầu model trả `[{"i": idx, "t": "..."}]`. Nếu số phần tử lệch hoặc JSON hỏng → **chia đôi lô và thử lại**, tối đa 2 lần. Vẫn hỏng → fallback dịch từng segment.

**8.7.5 Chimera (chỉ HY-MT1.5)**

Sinh 6 ứng viên mỗi lô → gọi lượt thứ 7 để pha. Tuần tự nên VRAM không tăng, chỉ chậm ~7×. Tuỳ chọn bật trong UI.

### 8.8 QA — hai tầng

**Tầng 1 — thuần code (`domain/qa_rules.py`), miễn phí:**

- Số / ngày tháng khớp bản gốc không.
- Tên riêng có xuất hiện không.
- Thuật ngữ glossary đã duyệt có bị mất không.
- Độ dài bất thường (dài > 3× gốc = nghi bịa).
- Bản dịch rỗng hoặc chỉ có ký tự lạ.
- **CPS (tốc độ đọc) vượt ngưỡng** — `domain/readability.py`. Tiếng Việt dài gấp 2–3× tiếng
  Trung nên đây là lỗi phụ đề phổ biến nhất, và nó chỉ lộ ra khi đặt hai thứ cạnh nhau (§9.1).

**Tầng 2 — chỉ gọi LLM cho segment đã bị tầng 1 cảnh báo.** Không bao giờ soát cả file.

Lưu vào `translations.qa_issues` và vào `segment.qa`.

### 8.9 Export

SRT · VTT · ASS — đơn ngữ hoặc **song ngữ**. Chọn bản dịch nào để xuất. ASS tận dụng word timestamp cho karaoke. Ghi vào `data/output/`.

---

## 9. Giao diện

> **Thiết kế giao diện đầy đủ nằm ở file riêng:** `2026-09-25-phu-de-lab-ui-design.md`
> (hướng thẩm mỹ, hệ thống thiết kế, 8 màn hình, bàn phím). Mục này chỉ ghi những gì
> **ràng buộc kiến trúc backend**.

Next.js 16 App Router · React 19 · Tailwind v4. `next.config.ts` rewrite `/api/*` → `http://127.0.0.1:8620`, đúng pattern của `truyen-dich`.

### 9.1 Bố cục: BA vùng, không phải hai pane

v2 vẽ hai pane chia đôi. Bố cục đó không chịu được hai thứ mà chính spec này yêu cầu: nhiều
source cùng lúc (§7.2 gom lô chỉ có nghĩa khi có nhiều job) và việc nghe lại để soát (§8.4).

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ PHÒNG THU BIÊN TẬP    [● Ollama]  [▮▮▮▯▯ 3.2/8GB]  [GĐ: ASR·turbo]       [⚙]  │
├──────────────┬────────────────────────────────────────┬───────────────────────┤
│ KÊNH         │  BÀN LÀM VIỆC                          │  HÀNG ĐỢI             │
│ 214px        │  ┌─rail─┬─────────────────────────────┐│  286px                │
│ ● video-01   │  │ 0:01 │ …                           ││  ▸ ASR·turbo   ▓▓▓░░  │
│ ○ video-02   │  │ 0:12╱│ [nghi ngờ]                  ││  ⏸ MT·qwen2.5-7b      │
│ [+ NẠP LIỆU ]│  └──────┴─────────────────────────────┘│    chờ gom lô         │
│              │  [ BIÊN TẬP │ ĐỐI CHIẾU │ THUẬT NGỮ ]   │                       │
├──────────────┴────────────────────────────────────────┴───────────────────────┤
│ ▶ 0:15/12:04  [━━━━━━━━━░░░░░░]  ETA 4m           [SRT] [VTT] [ASS]           │
└───────────────────────────────────────────────────────────────────────────────┘
```

Ba chế độ của vùng BÀN LÀM VIỆC: **Biên tập** · **Đối chiếu** (hai cột + CPS) · **Thuật ngữ**.
Hai màn hình **đo lường** (§10) thay toàn bộ vùng giữa vì chúng không gắn với kênh nào.

### 9.2 Yêu cầu bắt buộc

- **Header** hiện trạng thái Ollama + VRAM + **giai đoạn hiện tại** + số job chờ.
- **Job đang chờ hiện lý do** (`chờ gom lô cùng giai đoạn`) — nếu không, người dùng tưởng app treo.
- Dropdown model đọc từ `GET /api/registry`, **không hard-code**.
- **Danh sách ảo hoá** cho transcript và bản dịch — 2000 dòng vẫn mượt. **Dòng đang sửa được
  ghim** để không bị unmount khi cuộn.
- **ETA** trên thanh job, dựa trên `duration` × RTF đo được.
- **Đoạn nghi ngờ đánh bằng vân chéo ở lề, KHÔNG tô đỏ** — lý do ở file UI/UX §2.5 (giữ amber là
  tài nguyên duy nhất có nghĩa; an toàn cho người mù màu).
- **Trình phát media** ở thanh transport: click dòng → seek tới đoạn đó. Không có nó thì tín hiệu
  `suspect` báo chỗ sai mà người dùng không nghe được để sửa.
- **N bản dịch là segmented control, không phải tab nổi** — 4 engine × nhiều phiên bản prompt sẽ
  làm tab nổ tung. Cần so hai bản thì **ghim bản B** hiện cột thứ ba.
- **Chimera hiện cả 6 ứng viên và bản hợp nhất**, kèm **cảnh báo chi phí** (`~7×`). Một chế độ
  tốn gấp 7 lần phải biện minh cho chi phí của nó, nếu không sẽ không ai dùng.
- **Tab Thuật ngữ hiện số bản dịch bị ảnh hưởng** khi glossary đổi, và hàng đợi tự sinh job
  *"Dịch lại · do glossary đổi"*.
- **Ollama mất kết nối là trạng thái HẠNG NHẤT** (dải vằn chéo ở đỉnh cửa sổ + khối hướng dẫn),
  **không phải toast** — app không dùng được nếu thiếu, mà đây là lỗi phổ biến nhất của app local.
- Log streaming bằng **SSE** (`GET /api/jobs/stream`, một stream toàn cục, client lọc theo `job_id`).

### 9.3 Bàn phím là yêu cầu, không phải điểm cộng

Người dùng ngồi với app này hàng giờ. Bảng phím tắt đầy đủ ở file UI/UX §5.1; tối thiểu phải có:
`Space` phát/dừng · `J`/`K` chuyển dòng · `Enter` sửa dòng · `Esc` thoát · `Shift+←/→` nudge mốc
±0,1s · `[`/`]` đặt start/end tại đầu đọc · `S` tách dòng · `M` gộp dòng · `N` nhảy tới đoạn
nghi ngờ kế tiếp · `Ctrl+1/2/3` đổi chế độ.

### 9.4 Ràng buộc offline áp lên frontend

App chạy hoàn toàn offline (§17.8) nên:

- **Font phải self-host woff2** ở `frontend/public/fonts/`, **không được nạp từ Google Fonts CDN**.
- Không có telemetry, không analytics, không gọi mạng ngoài khi chạy.

---

## 10. Subsystem đánh giá chất lượng (`backend/eval/`)

**Đây là phần mà v1 thiếu hoàn toàn, và là gap nặng nhất.** v1 chỉ kiểm "có timestamp, không crash". Nhưng câu hỏi trung tâm của dự án là **"model nào tốt hơn"** — không đo được thì toàn bộ tính năng "đổi model" trở thành cảm tính.

```
backend/eval/
├── samples/          # 5 clip 1–2 phút + transcript chuẩn
├── run_asr_eval.py   # WER/CER cho từng engine
├── run_mt_eval.py    # đếm cảnh báo QA + xuất 20 câu để chấm tay
└── report.md         # bảng kết quả, commit → lịch sử chất lượng
```

### Bộ mẫu — 5 clip

| # | Clip | Kiểm tra điều gì |
|---|---|---|
| 1 | Trung, có nhạc nền | khả năng chống ảo giác |
| 2 | Trung nói nhanh, nhiều tên riêng | độ chính xác + glossary |
| 3 | Trung, phụ đề cứng | trường hợp khó nhất |
| 4 | Anh, có accent | nhánh tiếng Anh |
| 5 | Trung, có hát | trường hợp dễ sinh rác nhất |

### Đo gì

| Đối tượng | Cách đo |
|---|---|
| ASR | **WER/CER** so với transcript chuẩn (cần bạn soát transcript mẫu) |
| MT | **Không** dùng BLEU/COMET — không có bản tham chiếu đủ tin. Dùng **số cảnh báo QA** + **chấm tay 20 câu thang 1–5** |

### Bảng benchmark (bắt buộc ở GĐ1b)

| Số cần đo | Vì sao |
|---|---|
| RTF (real-time factor) từng engine ASR | để tính ETA, để so sánh engine |
| tokens/s từng engine MT | để chọn kích thước lô |
| thời gian nạp model | để đánh giá hiệu quả hàng đợi theo giai đoạn |
| hệ số ước lượng token (ký tự nguồn → token đích) | để chia lô đúng (§8.7.1) |
| WER/CER từng engine ASR | chất lượng bóc băng |
| điểm chấm tay từng engine MT | chất lượng dịch |

Ghi số thật vào `eval/report.md` và commit. **Không có con số thì không biết mình đang nhanh hay chậm, và không phát hiện được hồi quy.**

---

## 11. API

| Method | Endpoint | Việc |
|---|---|---|
| `POST` | `/api/sources/upload` | nhận file (multipart) |
| `POST` | `/api/sources/url` | nhận URL |
| `POST` | `/api/jobs` | tạo job |
| `GET` | `/api/jobs/{id}` | trạng thái một job |
| `GET` | `/api/jobs/stream` | **một** SSE stream toàn cục; client lọc theo `job_id` |
| `POST` | `/api/jobs/{id}/cancel` | đặt `cancel_requested`, worker dừng ở checkpoint |
| `GET` | `/api/registry` | danh sách engine cho dropdown |
| `GET` | `/api/status` | Ollama, VRAM, giai đoạn hiện tại, độ sâu hàng đợi |
| `GET` | `/api/transcripts` · `GET /{id}` | danh sách / chi tiết |
| `PATCH` | `/api/transcripts/{id}` | sửa segments → `version` tăng → bản dịch cũ thành `stale` |
| `POST` | `/api/transcripts/{id}/approve` | duyệt → chuyển WS2 |
| `GET` | `/api/translations?transcript_id=` | N bản dịch + cờ `stale` tính sẵn |
| `PATCH` | `/api/translations/{id}` | sửa tay một bản dịch |
| `GET` | `/api/glossary` · `POST` · `PATCH` | quản lý glossary |
| `GET` | `/api/media/{source_id}` | **serve media, BẮT BUỘC hỗ trợ HTTP `Range`** — không có `Range` thì trình phát không seek được |
| `GET` | `/api/export/{translation_id}` | `?format=srt\|vtt\|ass&bilingual=0\|1` |

---

## 12. Cài đặt & môi trường

### A. Công cụ hệ thống

| Cài | Lệnh | Vì sao |
|---|---|---|
| Ollama (Windows) | `winget install Ollama.Ollama` | chạy Qwen2.5 + HY-MT1.5, tự quản VRAM |
| yt-dlp | `winget install yt-dlp` | tải video từ link |
| ffmpeg, git, node | ✅ đã có | không cần làm gì |
| cmake / MSVC | **KHÔNG cần** | vì không build `llama-cpp-python` |

### B. Python — venv riêng tại `backend/.venv`

Python 3.10.5 có sẵn.

| Gói | Dùng cho | Dung lượng |
|---|---|---|
| `fastapi` `uvicorn[standard]` `python-multipart` | API + upload | nhỏ |
| `faster-whisper` | ASR — kéo theo CTranslate2, **không cần torch** | ~50MB |
| `torch` (cu121) + `funasr` + `modelscope` | SenseVoice | **~2.5GB** |
| `transformers` `sentencepiece` `sacremoses` | OPUS-MT (Marian) | ~500MB |
| `httpx` `yt-dlp` `soundfile` `numpy` | gọi Ollama · tải video · xử lý audio | nhỏ |
| `jiwer` | tính WER/CER cho eval | nhỏ |

> **Thứ tự bắt buộc:** cài `torch` với `--index-url https://download.pytorch.org/whl/cu121` **trước**, rồi mới `funasr`. Nếu không, FunASR kéo bản torch CPU và mất GPU mà không báo lỗi.

### C. Model — đặt hết ở `D:\models\`

| Nguồn | Model | Tải về |
|---|---|---|
| `ollama pull` | `qwen2.5:7b-instruct-q4_K_M` | 4.7GB |
| `ollama pull` | `qwen2.5:3b-instruct-q4_K_M` | 2.0GB |
| `ollama create` từ GGUF trên HF | Hunyuan-MT-7B / HY-MT1.5-7B Q4_K_M | 4.7GB |
| HF cache | faster-whisper large-v3-turbo / medium / small | 3.6GB |
| HF cache | SenseVoice-Small | 0.9GB |
| HF cache | OPUS-MT zh-vi + en-vi | 0.6GB |
| | **Tổng ~16.5GB** (D: còn 61.6GB → thừa) | |

### D. Thứ tự cài kèm verify

Mỗi bước phải pass mới sang bước sau.

| # | Cài | Verify |
|---|---|---|
| 1 | Ollama | `ollama run qwen2.5:3b "hi"` chạy bằng GPU |
| 2 | venv + torch cu121 | `torch.cuda.is_available()` → `True` |
| 3 | faster-whisper | transcribe file mẫu ra timestamp |
| 4 | funasr + SenseVoice | transcribe file tiếng Trung mẫu |
| 5 | transformers + OPUS-MT | dịch một câu zh→vi |
| 6 | yt-dlp | tải thử một link ngắn |
| 7 | pull/import model Ollama | dịch một câu qua API |

---

## 13. Kiểm thử

| Loại | Nội dung | Cần model? |
|---|---|---|
| Ranh giới tầng | `domain/` không import `adapters`/`ports`/`fastapi`/`torch`/`httpx` | Không |
| Unit thuần | chia lô theo token · parse JSON + tự chữa · QA tầng 1 · cắt/gộp segment · state machine · quy tắc stale theo version · sinh SRT/VTT/ASS | Không |
| E2E fake | 1 fake ASR + 1 fake MT → chạy cả pipeline | Không |
| Hàng đợi | gom lô theo giai đoạn: 2 file đổi model → đúng số lần swap | Không (fake) |
| Phục hồi | kill worker giữa job → restart → job thành `interrupted`, DB không hỏng | Không |
| Smoke thật | file 30s → chạy từng engine, kiểm có timestamp, không crash | Có |
| Tranh chấp VRAM | 2 job cùng lúc → không OOM, log ghi đúng lý do hạ cấp | Có |
| Eval chất lượng | §10 | Có |

Pattern E2E fake lấy từ `tests/test_fake_e2e.py` của `truyen-dich`.

---

## 14. Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| GGUF Hunyuan-MT/HY-MT1.5 hiện chỉ có bản **cộng đồng** | Cao | **Eval ở §10 sẽ trả lời bằng số**; `qwen2.5-7b` là fallback chắc chắn |
| FunASR + torch trên Windows hay vướng | Trung | Cài torch trước với index-url; nếu vẫn vỡ → dùng **SenseVoice GGUF** qua llama.cpp runtime |
| RTX 3070 8GB OOM khi bật song song | Trung | Mặc định tuần tự · ngưỡng 7000MB · tự hạ cấp và ghi log |
| SenseVoice không có word timestamp | Thấp | Chấp nhận — yêu cầu là cấp đoạn |
| HY-MT1.5 hỏng bản dịch khi nhồi glossary vào prompt | Trung | Đã xử lý ở §8.7.2: glossary đi đường hậu kiểm |
| Hệ số ước lượng token sai → lô quá lớn/nhỏ | Trung | Đo thật ở GĐ1b rồi hiệu chỉnh (§8.7.1) |
| Hàng đợi theo giai đoạn làm job chờ lâu, người dùng tưởng treo | Trung | UI hiện giai đoạn hiện tại + lý do chờ (§7.2) |
| `yt-dlp` hỏng khi site đổi cấu trúc | Thấp | `pip install -U yt-dlp` |

---

## 15. Không làm (YAGNI)

1. **Ghi âm trực tiếp từ mic** — đã chọn file + link.
2. **Crawler hàng loạt / watch-folder.**
3. **So sánh A/B tự động giữa các model** — nhưng vì `translations` cho N bản trên 1 transcript nên thêm sau chỉ là việc của UI.
4. **Tách giọng khỏi nhạc nền (Demucs/UVR5)** — hữu ích cho video nhiều nhạc, để sau.
5. **Moonshine** — loại khỏi workspace 1 vì không có timestamp (§6).
6. **Xác thực người dùng / multi-tenant.**
7. **Glossary tự đề xuất (LLM quét transcript gợi ý thuật ngữ)** — `truyen-dich` đã có pattern này. Ở đây **chưa làm** vì phụ đề video ít thuật ngữ lặp hơn webnovel. *Cân nhắc lại ở Giai đoạn 2/3 nếu thấy phải gõ tay quá nhiều.*
8. **Prompt injection / phòng chống nội dung độc hại** — không áp dụng: input là video do chính người dùng chọn, chạy local, không có tenant khác.
9. **CDN, edge, PWA, load testing, APM, SLO** — không áp dụng cho app local một người dùng.

---

## 16. Lộ trình triển khai

Hệ thống gồm 6 tiểu hệ thống; gói tất cả vào một kế hoạch là quá lớn.

> **File này là spec kiến trúc tổng thể.** Nó bao trùm cả bốn giai đoạn; mỗi giai đoạn có kế hoạch triển khai riêng. **Kế hoạch đầu tiên chỉ phủ Giai đoạn 1a.**

### Giai đoạn 1a — Nền tảng + Workspace 1 *(kế hoạch đầu tiên)*

- Khung backend theo phân tầng §3.1 + test ranh giới tầng
- SQLite schema §5 + migrations + state machine job (§5.4)
- `registry.json` + registry loader + `GET /api/registry`
- Worker hàng đợi **theo giai đoạn** (§7.2) + SSE stream + log ra file
- Ingest: upload file + yt-dlp + ffmpeg
- ASR: adapter faster-whisper (phủ `small`/`medium`/`turbo` — một adapter, ba `model_ref`) + adapter SenseVoice + batched inference
- Hậu xử lý segment + tín hiệu tin cậy (§8.4) + xuất SRT
- **Endpoint media có HTTP `Range`** (§11) — điều kiện để có trình phát
- Frontend Next.js: khung **ba vùng** (§9.1) — KÊNH / BÀN LÀM VIỆC / HÀNG ĐỢI + thanh transport
- **Hệ thống thiết kế**: token màu, font self-host woff2 (§9.4), grain, dải vân nghi ngờ
- **Trình phát + bàn phím** (§9.3) — nudge mốc, `[`/`]`, tách/gộp dòng, `N` nhảy đoạn nghi ngờ
- **Danh sách ảo hoá + ghim dòng đang sửa** (§9.2)
- Trạng thái rỗng và **trạng thái Ollama mất kết nối** (§9.2)
- Test: unit + ranh giới tầng + E2E fake + hàng đợi + phục hồi + smoke thật

**Bàn giao:** nạp một video (file hoặc link), chọn engine, ra transcript có timestamp, sửa được, xuất SRT tiếng gốc.

> Một adapter faster-whisper phủ cả ba biến thể (chúng chỉ khác `model_ref`). GĐ1a **chỉ tải về** `large-v3-turbo`; `small` và `medium` đã chọn được trong UI ngay nhưng tải model ở lần chạy đầu.

### Giai đoạn 1b — Đo lường

- Subsystem `eval/` (§10): 5 clip mẫu, `run_asr_eval.py`, `report.md`
- Bảng benchmark: RTF, thời gian nạp model, hệ số ước lượng token
- Hiệu chỉnh ngân sách lô (§8.7.1) bằng số thật
- Ảo hoá danh sách + ETA trên UI
- `llm_calls` ghi đầy đủ

**Bàn giao:** WER của từng engine ASR, thời gian thật của từng công đoạn, và ngân sách lô đã được hiệu chỉnh.

*Lý do tách khỏi 1a:* eval cần 1a chạy đã mới đo được.

### Giai đoạn 2 — Workspace 2

- MT engines: `opus-mt`, `qwen2.5-3b`, `qwen2.5-7b`, `hy-mt-1.5-7b`
- Chia lô theo token + prompt có version + JSON self-healing
- Glossary + QA hai tầng + `transcript_version`/`stale`
- `run_mt_eval.py`: đếm cảnh báo QA + chấm tay 20 câu
- Frontend: pane workspace 2, N bản dịch dạng tab, tab Thuật ngữ
- Export SRT/VTT/ASS đơn ngữ + song ngữ

**Bàn giao:** bấm một nút từ video ra phụ đề tiếng Việt; có **số** để nói model nào dịch tốt hơn.

### Giai đoạn 3 — Chất lượng & vận hành

- Chế độ song song + VRAM guard + test tranh chấp
- Chế độ Chimera
- Thống kê VRAM / thời gian / cảnh báo QA theo engine
- Dùng số liệu thật để chỉnh: ngân sách lô, ngưỡng `suspect`, quy tắc xưng hô trong prompt

---

## 17. Tiêu chí thành công

1. Nạp một video tiếng Trung bằng link → transcript có timestamp cấp đoạn, sửa tay được.
2. Chuyển transcript sang workspace 2 → phụ đề tiếng Việt, xuất được SRT song ngữ.
3. Đổi engine ASR và chạy lại cùng source → hai transcript để so sánh, không mất bản cũ.
4. Đổi engine dịch và chạy lại cùng transcript → hai bản dịch để đối chiếu.
5. **Có bảng WER cho ASR và điểm chấm tay cho MT** — trả lời được "model nào tốt hơn" bằng số, không bằng cảm giác.
6. Không OOM trên 8GB VRAM. Tuần tự không bao giờ OOM; song song thì VRAM guard **hạ cấp và ghi log**, tuyệt đối không để tiến trình chết.
7. Kill worker giữa job → restart → job thành `interrupted`, không treo, DB không hỏng.
8. Toàn bộ chạy offline, không gọi API ngoài.
