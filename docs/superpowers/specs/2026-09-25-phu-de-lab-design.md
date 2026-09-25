# phu-de-lab — Thiết kế

**Ngày:** 2026-09-25
**Trạng thái:** Chờ người dùng duyệt

Một web app chia thành hai bàn thao tác cho một dây chuyền hai bước:
**Workspace 1** bóc băng audio/video ra văn bản kèm timestamp, **Workspace 2** dịch văn bản đó sang tiếng Việt. Mỗi workspace đổi được model độc lập.

---

## 1. Mục tiêu & phạm vi

### Mục tiêu

1. Nạp liệu bằng **file tải lên** hoặc **link video online**.
2. **Workspace 1**: audio → văn bản có timestamp cấp đoạn (word-level là bonus).
3. **Workspace 2**: văn bản → bản dịch tiếng Việt, xuất được phụ đề.
4. **Đổi model tự do** ở cả hai workspace, không mất kết quả cũ.
5. Chạy **hoàn toàn local** trên một máy RTX 3070 8GB.

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
| Không cần | cmake / MSVC (quyết định ở §3) |

**Ràng buộc cứng:** 8GB VRAM phải chia cho hai workspace. Đây là ràng buộc định hình toàn bộ kiến trúc.

**Hệ quả về dung lượng:** model đặt ở `D:\models\` để không ăn vào 52GB còn lại của `C:`.

---

## 3. Kiến trúc

### Quyết định: Python monolith + Ollama lo phần LLM

```
┌─ frontend/ (Next.js) ────────────────────────────────┐
│  React 19 · Tailwind v4 · shadcn/ui                  │
│  rewrite /api/* → http://127.0.0.1:8620              │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP + SSE
┌───────────────────────▼──────────────────────────────┐
│  backend/ (FastAPI + SQLite)                         │
│                                                      │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  api/      │  │  pipeline/   │  │  engines/    │  │
│  │  routes    │─▶│  ingest      │─▶│  ASR adapter │  │
│  │  SSE       │  │  asr         │  │  MT adapter  │  │
│  │            │  │  translate   │  │  registry    │  │
│  └────────────┘  │  qa / export │  │  vram mgr    │  │
│                  └──────┬───────┘  └──────┬───────┘  │
│                         │                 │          │
│                  ┌──────▼───────┐  ┌──────▼───────┐  │
│                  │ worker queue │  │   SQLite     │  │
│                  │ (1 luồng mặc │  │   + files    │  │
│                  │  định)       │  │              │  │
│                  └──────────────┘  └──────────────┘  │
└──────────┬──────────────────────┬────────────────────┘
           │ in-process           │ HTTP
    ┌──────▼───────┐       ┌──────▼──────────┐
    │ faster-whisper│      │ Ollama (nền)    │
    │ SenseVoice    │      │ Qwen2.5 · HY-MT │
    │ OPUS-MT       │      │ keep_alive      │
    └───────────────┘      └─────────────────┘
```

**Lý do chọn:** Ollama có `keep_alive` — tự đổ model sau khi rảnh, và nhận lệnh đổ ngay (`keep_alive: 0`). Đây chính là cơ chế giải bài toán tranh chấp 8GB VRAM mà không phải tự viết. Đường cài trên Windows chắc chắn chạy (installer, không build C++).

**Phương án đã loại:**

- *Tất cả in-process (`llama-cpp-python`)* — không có wheel Windows sẵn, phải tự build với CUDA, cần MSVC + cmake mà máy chưa có.
- *Microservices* — phức tạp gấp ~3, thừa cho một máy một người dùng, và khó debug VRAM hơn chứ không dễ hơn.

### Nguyên tắc bất di bất dịch

> **Toàn bộ xử lý model nằm trong `backend/`.** Frontend không bao giờ đụng tới model, chỉ gọi API và render.

---

## 4. Cấu trúc thư mục

```
C:\Users\Admin\Desktop\ngn\deepseek\phu-de-lab\
├── backend/
│   ├── .venv/                     # venv riêng
│   ├── app/
│   │   ├── main.py                # FastAPI app + CORS cho Next.js dev
│   │   ├── api/                   # routes, SSE
│   │   ├── engines/
│   │   │   ├── registry.py        # đọc/ghi registry.json
│   │   │   ├── vram.py            # ước tính + điều phối VRAM
│   │   │   ├── asr/               # faster_whisper.py, sensevoice.py
│   │   │   └── mt/                # opus_mt.py, ollama_mt.py
│   │   ├── pipeline/
│   │   │   ├── ingest.py          # yt-dlp + ffmpeg
│   │   │   ├── asr.py             # chạy ASR + hậu xử lý segment
│   │   │   ├── translate.py       # chia lô, JSON self-healing
│   │   │   ├── qa.py              # QA tầng 1 (code) + tầng 2 (LLM)
│   │   │   └── export.py          # SRT / VTT / ASS
│   │   ├── worker.py              # hàng đợi job
│   │   ├── db.py                  # schema + migrations
│   │   └── config.py
│   ├── registry.json              # khai báo engine (sửa để thêm model)
│   ├── requirements.txt
│   └── tests/
├── frontend/                      # Next.js 16 App Router
│   ├── app/
│   ├── components/
│   └── lib/
├── data/
│   ├── media/                     # file gốc + wav đã extract
│   ├── output/                    # SRT/VTT/ASS xuất ra
│   └── app.db                     # SQLite
└── docs/superpowers/
    ├── specs/                     # file này
    └── plans/
```

**Biến môi trường:**

```
OLLAMA_MODELS = D:\models\ollama
HF_HOME       = D:\models\hf
PHUDE_DB      = ./data/app.db
PHUDE_PORT    = 8620
```

Cổng **8620** cho backend (tránh 8619 của `truyen-dich`) và **3100** cho Next.js dev (tránh 3000).

---

## 5. Mô hình dữ liệu

SQLite, một file `data/app.db`.

```sql
CREATE TABLE sources (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL CHECK(kind IN ('file','url')),
  origin      TEXT NOT NULL,            -- tên file gốc hoặc URL
  media_path  TEXT NOT NULL,            -- video/audio đã tải về
  audio_path  TEXT,                     -- wav 16k mono đã extract
  duration    REAL,
  lang        TEXT,                     -- 'zh' | 'en'
  created_at  TEXT NOT NULL
);

CREATE TABLE transcripts (
  id          INTEGER PRIMARY KEY,
  source_id   INTEGER NOT NULL REFERENCES sources(id),
  engine      TEXT NOT NULL,            -- id trong registry.json
  lang        TEXT NOT NULL,
  segments    TEXT NOT NULL,            -- JSON array (xem bên dưới)
  status      TEXT NOT NULL DEFAULT 'draft',   -- draft|reviewed|translated
  edited_at   TEXT,                     -- lần sửa tay cuối → dùng để đánh stale
  created_at  TEXT NOT NULL
);

CREATE TABLE translations (
  id               INTEGER PRIMARY KEY,
  transcript_id    INTEGER NOT NULL REFERENCES transcripts(id),
  engine           TEXT NOT NULL,
  target_lang      TEXT NOT NULL DEFAULT 'vi',
  segments         TEXT NOT NULL,       -- JSON array
  glossary_version INTEGER,
  qa_issues        TEXT,                -- JSON array
  stale            INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT NOT NULL
);

CREATE TABLE jobs (
  id          INTEGER PRIMARY KEY,
  workspace   INTEGER NOT NULL CHECK(workspace IN (1,2)),
  type        TEXT NOT NULL,            -- ingest|asr|translate|export
  engine      TEXT,
  state       TEXT NOT NULL,            -- queued|running|done|failed|cancelled
  progress    REAL NOT NULL DEFAULT 0,
  log         TEXT NOT NULL DEFAULT '',
  error       TEXT,
  payload     TEXT,                     -- JSON tham số
  created_at  TEXT NOT NULL,
  started_at  TEXT,
  finished_at TEXT
);

CREATE TABLE glossary (
  id          INTEGER PRIMARY KEY,
  lang        TEXT NOT NULL,            -- ngôn ngữ nguồn
  term        TEXT NOT NULL,
  translation TEXT NOT NULL,
  note        TEXT,
  approved    INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  UNIQUE(lang, term)
);

CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

### Hình dạng một segment

```json
{
  "i": 0,
  "start": 1.02,
  "end": 4.38,
  "text": "大家好",
  "words": [{"w": "大家", "s": 1.02, "e": 2.10}],
  "emotion": "happy",
  "events": ["bgm"],
  "speaker": null
}
```

`words`, `emotion`, `events`, `speaker` đều **tuỳ chọn** — chỉ engine nào sinh được mới có. Sau khi dịch, mỗi phần tử có thêm `"t"` là bản dịch.

### Vì sao `translations` là N dòng trên 1 transcript

Đây là quyết định trung tâm: **đổi model dịch = thêm một dòng, không ghi đè**. Nhờ vậy so sánh kết quả giữa các model là việc của UI, không phải của kiến trúc.

---

## 6. Engine registry & ma trận model

`registry.json` là nguồn sự thật duy nhất. **Thêm model mới = sửa JSON, không đụng pipeline, không đụng UI** — frontend đọc registry qua `GET /api/registry` để render dropdown.

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
        "emotion": false, "glossary_prompt": true
      }
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

SenseVoice có thêm khả năng Faster-Whisper không có: **nhận cảm xúc + sự kiện âm thanh** (cười, vỗ tay, nhạc nền). Lưu vào metadata của segment.

> **Moonshine bị loại khỏi workspace 1.** Nó chỉ hỗ trợ tiếng Anh và **không sinh timestamp** — không thoả yêu cầu cứng về timestamp cấp đoạn. Nó là model cho voice command on-device, không phải cho phụ đề.

### Workspace 2 — Dịch

| id | Runtime | VRAM | Đặc điểm |
|---|---|---|---|
| `opus-mt` | in-process (Marian) | CPU | tức thì, dịch từng câu rời, **không glossary** |
| `qwen2.5-3b` | Ollama | ~2500MB | nhanh, có glossary/văn phong |
| `qwen2.5-7b` | Ollama | ~5200MB | chủ lực: ngữ cảnh dài, glossary, giữ format |
| `hy-mt-1.5-7b` | Ollama | ~5200MB | chuyên dịch, sát nghĩa; prompt ngắn, kém tuân lệnh |

> **Chimera là một CHẾ ĐỘ của `hy-mt-1.5-7b`, không phải engine riêng.** Bật bằng checkbox trong UI; nó sinh 6 ứng viên rồi gọi thêm một lượt để pha thành bản tinh. Chạy tuần tự nên **VRAM không tăng**, chỉ chậm ~7×. Thể hiện bằng `capabilities.chimera: true` trong registry.

### Adapter interface

```python
class ASREngine:
    def transcribe(self, audio_path: str, lang: str, opts: dict) -> list[Segment]: ...

class MTEngine:
    def translate(self, segments: list[Segment], glossary: list[Term],
                  opts: dict) -> tuple[list[Segment], list[Issue]]: ...
```

Mọi engine hiện thực đúng interface này. Pipeline không biết gì về engine cụ thể.

---

## 7. Điều phối VRAM

Một GPU 8GB, hai workspace. Cơ chế:

1. **Một hàng đợi toàn cục.** Mọi job của cả hai workspace vào một worker duy nhất. Mặc định **không bao giờ có hai job GPU chạy đồng thời**.
2. **ASR in-process**: nạp model → chạy → giải phóng + `torch.cuda.empty_cache()`. Cache lại **một** model gần nhất để khỏi nạp lại liên tục.
3. **MT qua Ollama**: `keep_alive` 5 phút. Khi job ASR cần VRAM mà Ollama đang giữ model, backend gọi generate với `keep_alive: 0` để **ra lệnh đổ ngay**, rồi mới nạp model ASR.
4. **Chế độ song song — tuỳ chọn, MẶC ĐỊNH TẮT.** Cho phép 1 job ASR + 1 job MT chạy cùng lúc, nhưng **chỉ khi** tổng VRAM ước tính < 7000MB. Vượt ngưỡng → tự hạ về tuần tự và ghi rõ lý do vào `jobs.log`.
5. **Ước tính VRAM tĩnh** lấy từ `registry.json` (`vram_mb`). Mục tiêu chỉ là chặn OOM, không cần đo chính xác.

### Ngân sách VRAM tham chiếu

| Tổ hợp | VRAM | Kết luận |
|---|---|---|
| ASR một mình | ~1.6GB | thoải mái |
| MT một mình (Qwen2.5-7B) | ~5.2GB | thoải mái |
| ASR + MT song song | ~6.8GB | vừa khít — cộng ~0.8GB desktop Windows = 7.6/8GB, **rủi ro** |

→ Vì vậy mặc định tuần tự. Chạy tuần tự thì tổng thời gian vẫn chấp nhận được vì ASR và MT vốn đã tuần tự theo tự nhiên của dây chuyền.

---

## 8. Pipeline

### 8.1 Ingest

| Bước | Việc |
|---|---|
| File | Upload → `data/media/<sha256>.<ext>` |
| URL | `yt-dlp` tải về, ghi tiến độ % vào job log |
| Chuẩn hoá | `ffprobe` lấy thời lượng → `ffmpeg -vn -ac 1 -ar 16000 -c:a pcm_s16le` → `<sha256>.wav` |

### 8.2 ASR

**Faster-Whisper**

1. VAD Silero cắt khoảng lặng (`vad_filter=True`) — chống ảo giác lặp câu ở đoạn im lặng/nhạc.
2. `language` **ghim cứng** (`zh` hoặc `en`) — không để model tự nhận nhầm.
3. `condition_on_previous_text=False` — giảm hiện tượng lặp.
4. `initial_prompt` = các thuật ngữ glossary tiếng nguồn — giúp viết đúng tên riêng.
5. `word_timestamps=True`.

**SenseVoice**

1. FunASR pipeline: VAD → SenseVoice-Small → dấu câu (`ct-punc`) → căn chỉnh timestamp.
2. `use_itn=True` (số ra chữ số).
3. Tag cảm xúc/sự kiện lưu vào metadata của segment, **không nhét vào text phụ đề** trừ khi người dùng bật tuỳ chọn.

**Hậu xử lý chung (mọi engine)**

- Gộp đoạn < 0.8s vào đoạn kề.
- Cắt đoạn quá dài (> 7s hoặc > 2 dòng × 42 ký tự) tại ranh giới từ gần nhất.
- Bỏ marker ảo giác, chuẩn hoá khoảng trắng, đánh số lại `i` từ 0.

### 8.3 Bàn giao

`transcripts.status`: `draft` → `reviewed` → `translated`

- **`auto_forward` mặc định BẬT.** ASR xong → tự tạo job translate ở workspace 2.
- Nút **"Giữ lại để sửa"** tắt `auto_forward` cho riêng job đó; transcript dừng ở `draft` chờ người dùng bấm "Duyệt → chuyển WS2".
- **Sửa transcript sau khi đã dịch** → `transcripts.edited_at` đổi → mọi bản dịch có `created_at < edited_at` bị gắn `stale = 1`, UI hiện nhãn "lỗi thời" kèm nút "dịch lại".

> Cơ chế `stale` này lấy nguyên từ pattern `charbook_version` đã chạy tốt ở `truyen-dich`.

### 8.4 Dịch

**① Phân lô, không dịch từng câu rời**

- Lô **15–25 segment**, kèm **2 segment trước và 2 segment sau làm ngữ cảnh** (chỉ để hiểu, không dịch).
- Yêu cầu model trả **JSON array** đúng số phần tử, mỗi phần tử `{"i": <idx>, "t": "<bản dịch>"}`.
- **Tự chữa:** nếu số phần tử lệch hoặc JSON hỏng → **chia đôi lô và thử lại**, tối đa 2 lần. Vẫn hỏng → fallback dịch từng segment.

**② Chiến lược prompt theo từng engine — đây là chỗ dễ sai nhất**

| Engine | Glossary | Prompt |
|---|---|---|
| Qwen2.5 | **nhét vào system prompt** (model nghe lời) | system: vai trò + quy tắc xưng hô + glossary; user: lô JSON |
| HY-MT1.5 | **KHÔNG nhét prompt** — hậu kiểm + vá tìm-thay-thế | đúng format chính thức, cực ngắn |
| OPUS-MT | không hỗ trợ (UI hiện cảnh báo) | không prompt, dịch từng segment |

> **Đây là quyết định quan trọng:** HY-MT1.5 kém tuân lệnh; nhồi glossary vào prompt dễ làm hỏng cả bản dịch. Nên với nó, glossary xử lý ở **hậu kiểm** thay vì ở prompt.

**③ Chế độ Chimera (chỉ HY-MT1.5)**

Sinh 6 ứng viên cho mỗi lô → gọi lượt thứ 7 để chọn/pha thành một bản tinh. Chạy **tuần tự** nên VRAM không tăng, chỉ chậm ~7×. Là tuỳ chọn bật trong UI.

### 8.5 QA — hai tầng, tốn token tối thiểu

**Tầng 1 — thuần code, miễn phí, chạy trên mọi segment:**

- Số / ngày tháng trong bản dịch có khớp bản gốc không.
- Tên riêng có xuất hiện không.
- Thuật ngữ glossary đã duyệt có bị mất không.
- Độ dài bất thường (bản dịch dài gấp > 3× bản gốc = nghi bịa).
- Bản dịch rỗng hoặc chỉ có ký tự lạ.

**Tầng 2 — chỉ gọi LLM cho những segment đã bị tầng 1 cảnh báo.** Không bao giờ soát cả file.

Kết quả lưu vào `translations.qa_issues` và hiện trong UI.

### 8.6 Export

- Định dạng: **SRT · VTT · ASS**
- **Đơn ngữ** (chỉ tiếng Việt) hoặc **song ngữ** (dòng trên tiếng gốc, dòng dưới tiếng Việt)
- Nếu transcript có N bản dịch → chọn bản nào để xuất
- ASS tận dụng word timestamp cho karaoke nếu engine có
- Tên file: `<tên gốc>.<engine>.srt`, ghi vào `data/output/`

---

## 9. Giao diện

Next.js 16 App Router · React 19 · Tailwind v4 · shadcn/ui. `next.config.ts` rewrite `/api/*` → `http://127.0.0.1:8620` (đổi bằng biến `PHUDE_API`), đúng pattern của `truyen-dich`.

```
┌──────────────────────────────────────────────────────────────────┐
│ phu-de-lab      [Ollama ●]  [GPU 3.2/8GB]  [hàng đợi: 2]         │
├───────────────────────────────┬──────────────────────────────────┤
│ WORKSPACE 1 · Tách âm         │ WORKSPACE 2 · Dịch               │
│ ┌───────────────────────────┐ │ ┌──────────────────────────────┐ │
│ │ kéo file vào  │  dán URL  │ │ │ transcript: [chọn ▼]         │ │
│ └───────────────────────────┘ │ └──────────────────────────────┘ │
│ Model: [Faster-Whisper ▼]     │ Model: [HY-MT1.5-7B ▼]           │
│ ☐ Giữ lại để sửa              │ ☐ Chế độ Chimera (chậm ~7×)      │
│ [ Bắt đầu ]                   │ [ Dịch ]                         │
│ ┌─ transcript (sửa trực tiếp)┐│ ┌─ N bản dịch ──────────────────┐│
│ │ 00:01 → 00:04  大家好     ││ │ ● Qwen2.5-7B  ○ HY-MT1.5      ││
│ │ 00:04 → 00:07  ...        ││ │ ○ OPUS-MT                     ││
│ └───────────────────────────┘│ │ 00:01 → 00:04 Xin chào mọi người││
│ [ Duyệt → chuyển WS2 ]        │ └──────────────────────────────┘│
│ [ Xuất SRT ]                  │ [ Xuất SRT song ngữ ]            │
├───────────────────────────────┴──────────────────────────────────┤
│ Thanh job: log trực tiếp · progress · nút huỷ                     │
└──────────────────────────────────────────────────────────────────┘
```

**Chi tiết:**

- Header hiện **trạng thái Ollama + VRAM thật + số job đang chờ** — để luôn biết vì sao một job phải chờ.
- Danh sách model trong dropdown đọc từ `GET /api/registry`, **không hard-code**.
- Log streaming bằng **SSE** (`GET /api/jobs/stream`) — đơn giản hơn WebSocket và đủ dùng.
- Sửa transcript: click vào dòng để sửa text; gộp/tách dòng; chỉnh mốc thời gian bằng tay.
- N bản dịch hiển thị dạng tab, chuyển qua lại để đối chiếu, đánh dấu bản nào để xuất.
- Tab **Thuật ngữ**: duyệt/sửa glossary, hiện số bản dịch bị ảnh hưởng khi glossary đổi.

---

## 10. API

| Method | Endpoint | Việc |
|---|---|---|
| `POST` | `/api/sources/upload` | nhận file (multipart) |
| `POST` | `/api/sources/url` | nhận URL |
| `POST` | `/api/jobs` | tạo job |
| `GET` | `/api/jobs/{id}` | trạng thái một job |
| `GET` | `/api/jobs/stream` | **một** SSE stream toàn cục cho mọi job; client tự lọc theo `job_id` |
| `POST` | `/api/jobs/{id}/cancel` | huỷ job |
| `GET` | `/api/registry` | danh sách engine cho dropdown |
| `GET` | `/api/status` | Ollama, VRAM, độ sâu hàng đợi |
| `GET` | `/api/transcripts` | danh sách transcript |
| `GET` | `/api/transcripts/{id}` | chi tiết + segments |
| `PATCH` | `/api/transcripts/{id}` | sửa segments → đánh `stale` các bản dịch cũ |
| `POST` | `/api/transcripts/{id}/approve` | duyệt → chuyển WS2 |
| `GET` | `/api/translations?transcript_id=` | N bản dịch của một transcript |
| `PATCH` | `/api/translations/{id}` | sửa tay một bản dịch |
| `GET` | `/api/glossary` · `POST` · `PATCH` | quản lý glossary |
| `GET` | `/api/export/{translation_id}` | `?format=srt\|vtt\|ass&bilingual=0\|1` |

---

## 11. Cài đặt & môi trường

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

> **Thứ tự bắt buộc:** cài `torch` với `--index-url https://download.pytorch.org/whl/cu121` **trước**, rồi mới `funasr`. Nếu không, FunASR sẽ kéo bản torch CPU và mất GPU mà không báo lỗi.

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

Mỗi bước phải pass mới sang bước sau — nếu bước 2 hay 4 vỡ thì biết ngay, không phải mò trong một đống lỗi.

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

## 12. Kiểm thử

| Loại | Nội dung | Cần model? |
|---|---|---|
| Unit thuần | chia lô · parse JSON + tự chữa khi lệch số phần tử · QA tầng 1 · cắt/gộp segment · sinh SRT/VTT/ASS | Không |
| E2E fake | 1 fake ASR + 1 fake MT → chạy cả pipeline | Không |
| Smoke thật | file 30s → chạy từng engine, kiểm có timestamp và không crash | Có |
| Tranh chấp VRAM | bật 2 job cùng lúc, xác nhận không OOM và log ghi đúng lý do hạ cấp | Có |

Pattern E2E fake lấy từ `tests/test_fake_e2e.py` của `truyen-dich`.

---

## 13. Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| GGUF Hunyuan-MT/HY-MT1.5 hiện chỉ có bản **cộng đồng**, chất lượng chưa kiểm chứng | Cao | Test chất lượng trước khi tin; `qwen2.5-7b` là fallback chắc chắn |
| FunASR + torch trên Windows hay vướng | Trung | Cài torch trước với index-url; nếu vẫn vỡ → dùng **SenseVoice GGUF** qua llama.cpp runtime (FunASR có sẵn bản này) |
| RTX 3070 8GB OOM khi bật song song | Trung | Mặc định tuần tự · ngưỡng 7000MB · tự hạ cấp và ghi log |
| SenseVoice không có word timestamp | Thấp | Chấp nhận — yêu cầu là cấp đoạn |
| HY-MT1.5 hỏng bản dịch khi nhồi glossary vào prompt | Trung | Đã xử lý ở §8.4: glossary đi đường hậu kiểm, không đi đường prompt |
| `yt-dlp` hỏng khi site đổi cấu trúc | Thấp | Chỉ cần `pip install -U yt-dlp` |

---

## 14. Không làm (YAGNI)

1. **Ghi âm trực tiếp từ mic** — người dùng đã chọn file + link.
2. **Crawler hàng loạt / watch-folder** — không có trong yêu cầu.
3. **So sánh A/B tự động giữa các model** — nhưng vì `translations` cho N bản trên 1 transcript nên thêm sau chỉ là việc của UI, không phải đổi kiến trúc.
4. **Tách giọng khỏi nhạc nền (Demucs/UVR5)** — hữu ích cho video nhiều nhạc, nhưng để sau.
5. **Moonshine** — loại khỏi workspace 1 vì không có timestamp (§6).
6. **Xác thực người dùng / multi-tenant** — chạy local một người dùng.

---

## 15. Lộ trình triển khai

Hệ thống gồm 6 tiểu hệ thống; gói tất cả vào một kế hoạch là quá lớn. Chia thành **3 giai đoạn**, mỗi giai đoạn có kế hoạch triển khai riêng.

> **File này là spec kiến trúc tổng thể.** Nó bao trùm cả ba giai đoạn; mỗi giai đoạn sẽ có spec chi tiết (nếu cần) và kế hoạch triển khai riêng. **Kế hoạch đầu tiên chỉ phủ Giai đoạn 1.**

### Giai đoạn 1 — Nền tảng + Workspace 1 *(kế hoạch đầu tiên)*

- Khung backend FastAPI + SQLite + schema + config
- `registry.json` + registry loader + `GET /api/registry`
- Worker hàng đợi một luồng + SSE stream
- Ingest: upload file + yt-dlp + ffmpeg
- ASR: adapter faster-whisper + adapter SenseVoice

  > Một adapter faster-whisper phủ cả ba biến thể `fw-small` / `fw-medium` / `fw-large-v3-turbo` (chúng chỉ khác `model_ref`). Giai đoạn 1 **chỉ tải về** `large-v3-turbo`; `small` và `medium` đã chọn được trong UI ngay nhưng sẽ tải model ở lần chạy đầu.

- Hậu xử lý segment + xuất SRT
- Frontend: khung Next.js + pane workspace 1 (nạp liệu, chọn model, xem/sửa transcript)
- Test: unit + E2E fake + smoke thật

**Kết quả bàn giao:** nạp một video, chọn engine, ra transcript có timestamp, sửa được, xuất SRT tiếng gốc.

### Giai đoạn 2 — Workspace 2

- MT engines: `opus-mt`, `qwen2.5-3b`, `qwen2.5-7b`, `hy-mt-1.5-7b`
- Chia lô + prompt theo engine + JSON self-healing
- Glossary + QA hai tầng + đánh dấu `stale`
- Frontend: pane workspace 2, N bản dịch dạng tab, tab Thuật ngữ
- Export SRT/VTT/ASS đơn ngữ + song ngữ

**Kết quả bàn giao:** bấm một nút từ video ra phụ đề tiếng Việt, đổi model dịch và đối chiếu được.

### Giai đoạn 3 — Chất lượng & vận hành

- Chế độ song song + VRAM guard + test tranh chấp
- Chế độ Chimera
- Thống kê VRAM / thời gian / số cảnh báo QA theo từng engine
- Dùng số liệu thật ở trên để chỉnh: kích thước lô, ngưỡng QA độ dài, quy tắc xưng hô trong prompt

---

## 16. Tiêu chí thành công

1. Nạp một video tiếng Trung bằng link → ra transcript có timestamp cấp đoạn, sửa tay được.
2. Chuyển transcript sang workspace 2, chọn model dịch → ra phụ đề tiếng Việt, xuất được SRT song ngữ.
3. Đổi engine ASR và chạy lại trên cùng một source → có hai transcript để so sánh, không mất bản cũ.
4. Đổi engine dịch và chạy lại trên cùng một transcript → có hai bản dịch để đối chiếu.
5. Không OOM trên 8GB VRAM. Ở chế độ tuần tự không bao giờ OOM; ở chế độ song song, VRAM guard phải **hạ cấp về tuần tự và ghi log lý do**, tuyệt đối không để tiến trình chết.
6. Toàn bộ chạy offline, không gọi API ngoài.
