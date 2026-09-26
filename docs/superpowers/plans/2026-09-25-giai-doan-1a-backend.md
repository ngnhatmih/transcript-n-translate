# Giai đoạn 1a — Nền tảng backend + Workspace 1 · Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng backend của phu-de-lab chạy được đầu-cuối: nạp video (tệp hoặc link) → bóc băng ra transcript có timestamp cấp đoạn → sửa tay → xuất SRT, với hàng đợi theo giai đoạn và API mà frontend sẽ gọi.

**Architecture:** Hexagonal nhẹ. `domain/` là logic thuần, không import gì ngoài stdlib. `ports/` là Protocol. `adapters/` hiện thực cụ thể (faster-whisper, SenseVoice, SQLite). `pipeline/` ráp domain + ports thành use case. `worker.py` là hàng đợi một luồng, gom lô theo **cặp (loại job, engine)** để giảm số lần nạp/đổ model. Mọi job CPU/GPU chạy tuần tự.

**Tech Stack:** Python 3.10.5 · FastAPI + uvicorn · SQLite (stdlib `sqlite3`) · faster-whisper (CTranslate2) · FunASR + torch cu121 (SenseVoice) · ffmpeg/ffprobe + yt-dlp · pytest

**Spec:**
- `docs/superpowers/specs/2026-09-25-phu-de-lab-design.md` (kiến trúc, v3)
- `docs/superpowers/specs/2026-09-25-phu-de-lab-ui-design.md` (giao diện — chỉ dùng §8 ràng buộc kỹ thuật; phần UI do Kế hoạch 2 làm)

---

## Phạm vi kế hoạch này

**Có:** toàn bộ backend GĐ1a — phân tầng, schema, registry, hàng đợi theo giai đoạn, phục hồi sau crash, ingest, hai adapter ASR, xuất phụ đề, API + SSE + endpoint media có `Range`.

**Không có** (Kế hoạch 2, viết sau): frontend Next.js, hệ thống thiết kế, 3 vùng, trình phát, bàn phím, ảo hoá danh sách.

**Kết quả kiểm chứng được ở cuối kế hoạch này:** `pytest` xanh toàn bộ, và một lệnh `curl` nạp một tệp video thật → trả về transcript có timestamp → `curl` thứ hai tải về tệp `.srt`. Chưa có giao diện, nhưng toàn bộ đường ống đã thật.

---

## Global Constraints

Mọi task đều ngầm chứa các ràng buộc này. Giá trị sao chép nguyên văn từ spec.

- **Python:** 3.10.5 · venv tại `backend/.venv`
- **Cài torch TRƯỚC funasr:** `pip install torch --index-url https://download.pytorch.org/whl/cu121` rồi mới `pip install funasr modelscope`. Nếu không, FunASR kéo bản torch CPU và mất GPU **mà không báo lỗi**.
- **Model không nằm trong repo:** `OLLAMA_MODELS=D:\models\ollama` · `HF_HOME=D:\models\hf`
- **Cổng:** backend `8620` · frontend dev `3100`
- **DB:** `data/app.db` (SQLite)
- **Ranh giới tầng (kiểm bằng test, không bằng lời hứa):** `app/domain/**` **không được** import `fastapi`, `torch`, `httpx`, `faster_whisper`, `funasr`, `transformers`, `sqlite3`, `yt_dlp`, hay bất cứ module nào của `app.adapters` / `app.ports`. Relative import trong `domain/` chỉ được phép ở mức `.` (cùng package).
- **`faster-whisper` KHÔNG cần torch** — nó dùng CTranslate2. Chỉ SenseVoice cần torch.
- **GĐ1a chỉ tải model ASR** (`faster-whisper large-v3-turbo` ~1.6GB + `SenseVoice-Small` ~0.9GB). Ollama và mọi model LLM thuộc GĐ2 — nhưng **vẫn cài Ollama** ở Task 20 vì bước cài đặt cần được de-risk sớm.
- **Dấu hiệu tin cậy:** `suspect = no_speech_prob > 0.6 or avg_logprob < -1.0`
- **Ngưỡng CPS:** `20.0` ký tự/giây (không tính khoảng trắng)
- **Ngân sách lô dịch:** `1200` token đầu ra · `TOKENS_PER_SOURCE_CHAR = 1.0` (**phải đo lại ở GĐ1b**) · trần `30` segment/lô · `2` segment ngữ cảnh mỗi bên
- **Ngưỡng segmentation:** gộp đoạn `< 0.8s` · cắt đoạn `> 7.0s` hoặc `> 84` ký tự (2 dòng × 42)
- **Tên phase:** `f"{job_type}:{engine_id}"` — ví dụ `asr:fw-large-v3-turbo`. **Không** phải `asr`.
- **Trạng thái job:** `queued · running · done · failed · interrupted · cancelled`
- **Huỷ là hợp tác:** đặt `cancel_requested=1`, worker tự dừng ở ranh giới lô. Không kill tiến trình.
- **Múi giờ / thời gian:** mọi cột thời gian là ISO-8601 UTC chuỗi, sinh từ một `Clock` port để test được.
- **Ngôn ngữ nguồn GĐ1a:** `zh` (chính), `en`. Đích: `vi` (chưa dùng ở GĐ1a).
- **Commit:** conventional commits, mỗi task một commit cuối.

---

## Bản đồ file

```
phu-de-lab/
├── .gitignore                                  (đã có)
├── backend/
│   ├── requirements.txt                        T1
│   ├── pytest.ini                              T1
│   ├── run_api.py                              T15  (tiện ích chạy dev)
│   ├── registry.json                           T8
│   ├── app/
│   │   ├── __init__.py                         T1
│   │   ├── config.py                           T1
│   │   ├── domain/
│   │   │   ├── __init__.py                     T1
│   │   │   ├── models.py                       T2
│   │   │   ├── job_state.py                    T3
│   │   │   ├── staleness.py                    T3
│   │   │   ├── segmentation.py                 T4
│   │   │   ├── batching.py                     T5
│   │   │   ├── readability.py                  T6
│   │   │   ├── qa_rules.py                     T6
│   │   │   └── subtitle_format.py              T14
│   │   ├── ports/
│   │   │   ├── __init__.py                     T7
│   │   │   ├── clock.py                        T7
│   │   │   ├── repos.py                        T7
│   │   │   ├── asr.py                          T7
│   │   │   └── governor.py                     T7
│   │   ├── adapters/
│   │   │   ├── __init__.py                     T7
│   │   │   ├── clock_system.py                 T7
│   │   │   ├── registry_file.py                T8
│   │   │   ├── persist/
│   │   │   │   ├── __init__.py                 T7
│   │   │   │   ├── schema.py                   T7
│   │   │   │   └── sqlite_repos.py             T7
│   │   │   ├── governor/
│   │   │   │   ├── __init__.py                 T9
│   │   │   │   └── single_gpu.py               T9
│   │   │   └── asr/
│   │   │       ├── __init__.py                 T12
│   │   │       ├── sensevoice_tags.py          T13  (parser thuần, test không cần model)
│   │   │       ├── faster_whisper.py           T12
│   │   │       └── sensevoice.py               T13
│   │   ├── registry.py                         T8   (kiểu dữ liệu + tra cứu)
│   │   ├── pipeline/
│   │   │   ├── __init__.py                     T11
│   │   │   ├── ingest.py                       T11
│   │   │   ├── transcribe.py                   T12
│   │   │   ├── transcript_edit.py              T18
│   │   │   └── export.py                       T14
│   │   ├── worker.py                           T9
│   │   ├── runner.py                           T12
│   │   ├── api/
│   │   │   ├── __init__.py                     T15
│   │   │   ├── app.py                          T15
│   │   │   ├── deps.py                         T15
│   │   │   ├── routes_sources.py               T15
│   │   │   ├── routes_registry.py              T15
│   │   │   ├── routes_jobs.py                  T16
│   │   │   ├── sse.py                          T16
│   │   │   ├── routes_media.py                 T17
│   │   │   ├── routes_transcripts.py           T18
│   │   │   └── routes_export.py                T18
│   │   └── main.py                             T15
│   ├── scripts/
│   │   └── install.ps1                         T20
│   └── tests/
│       ├── conftest.py                         T1
│       ├── fakes.py                            T9
│       ├── test_layer_boundary.py              T1
│       ├── test_models_json.py                 T2
│       ├── test_job_state.py                   T3
│       ├── test_staleness.py                   T3
│       ├── test_segmentation.py                T4
│       ├── test_batching.py                    T5
│       ├── test_readability.py                 T6
│       ├── test_qa_rules.py                    T6
│       ├── test_repos.py                       T7
│       ├── test_registry.py                    T8
│       ├── test_worker_phases.py               T9
│       ├── test_worker_cancel.py               T10
│       ├── test_worker_recovery.py             T10
│       ├── test_ingest.py                      T11
│       ├── test_transcribe_pipeline.py         T12
│       ├── test_sensevoice_tags.py             T13
│       ├── test_export.py                      T14
│       ├── test_api_sources.py                 T15
│       ├── test_api_jobs_sse.py                T16
│       ├── test_api_media_range.py             T17
│       ├── test_api_transcripts.py             T18
│       └── test_e2e_fake.py                    T19
└── data/                                        (T1, .gitignore đã bỏ qua)
    ├── media/
    ├── logs/
    └── output/
```

**Ghi chú thiếu so với spec §3.1:** kế hoạch này thêm `domain/subtitle_format.py` và
`api/deps.py`. Lý do: sinh SRT/VTT/ASS là logic thuần nên phải nằm trong `domain/` để test được
mà không cần adapter; `deps.py` gom việc dựng phụ thuộc cho FastAPI. Spec §3.1 vẽ
`pipeline/export.py` — file đó vẫn có, chỉ ghi tệp; phần định dạng nằm ở domain.

---

## Task 1: Khung dự án + test ranh giới tầng

**Files:**
- Create: `backend/requirements.txt`, `backend/pytest.ini`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/domain/__init__.py`, `backend/tests/conftest.py`, `backend/tests/test_layer_boundary.py`
- Create dirs: `data/media`, `data/logs`, `data/output`

**Interfaces:**
- Consumes: không
- Produces: `app.config` với các hằng số đường dẫn; test `test_layer_boundary.py` là **cái lưới an toàn** cho mọi task sau — nó quét `app/domain/**` và đỏ ngay khi ai đó import sai.

- [ ] **Step 1: Viết test ranh giới tầng (test này PHẢI chạy được trước khi có domain)**

```python
# backend/tests/test_layer_boundary.py
"""Bảo vệ quy tắc: domain/ là logic thuần, không biết gì về hạ tầng.

Test này là lý do tồn tại của cả phân tầng. Nếu nó đỏ, ĐỪNG sửa test —
hãy sửa chỗ import sai.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
DOMAIN = BACKEND / "app" / "domain"

FORBIDDEN_ABSOLUTE = {
    "fastapi", "starlette", "uvicorn",
    "torch", "faster_whisper", "funasr", "modelscope", "transformers",
    "ctranslate2", "onnxruntime",
    "httpx", "requests",
    "sqlite3", "yt_dlp",
    "app.adapters", "app.ports", "app.api", "app.pipeline", "app.worker",
}


def _imports_of(path: pathlib.Path) -> list[tuple[str, int]]:
    """Trả về (tên module, mức tương đối). Mức 0 = import tuyệt đối."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            out.append((node.module or "", node.level or 0))
    return out


def _domain_files() -> list[pathlib.Path]:
    if not DOMAIN.exists():
        return []
    return sorted(p for p in DOMAIN.rglob("*.py") if p.name != "__init__.py")


def test_domain_directory_exists():
    assert DOMAIN.is_dir(), f"thiếu thư mục {DOMAIN}"


def test_domain_has_no_forbidden_absolute_imports():
    offenders: list[str] = []
    for py in _domain_files():
        for name, level in _imports_of(py):
            if level != 0:
                continue
            top = name.split(".")[0]
            full = name
            if top in FORBIDDEN_ABSOLUTE or full in FORBIDDEN_ABSOLUTE:
                offenders.append(f"{py.name}: import {name}")
    assert not offenders, (
        "domain/ phải là logic thuần, không được import hạ tầng:\n  "
        + "\n  ".join(offenders)
    )


def test_domain_has_no_cross_layer_relative_imports():
    """`from .models import X` OK. `from ..adapters import Y` KHÔNG."""
    offenders: list[str] = []
    for py in _domain_files():
        for name, level in _imports_of(py):
            if level >= 2:
                offenders.append(f"{py.name}: {'..' * (level - 1)}{name}")
    assert not offenders, (
        "domain/ không được import ngược lên tầng trên:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_itself_can_fail(tmp_path):
    """Kiểm tra cái lưới: nếu domain/ có file import torch thì test phải bắt được."""
    rogue = DOMAIN / "_rogue_probe.py"
    rogue.write_text("import torch\n", encoding="utf-8")
    try:
        with pytest.raises(AssertionError):
            test_domain_has_no_forbidden_absolute_imports()
    finally:
        rogue.unlink()
```

- [ ] **Step 2: Tạo cây thư mục và các tệp tối thiểu**

```bash
mkdir -p backend/app/domain backend/tests data/media data/logs data/output
touch backend/app/__init__.py backend/app/domain/__init__.py
```

`backend/pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = .
addopts = -q
```

`backend/requirements.txt`:

```
# --- API ---
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.20

# --- ASR ---
# faster-whisper dùng CTranslate2, KHÔNG cần torch
faster-whisper==1.1.1

# --- SenseVoice (torch PHẢI cài riêng trước, xem scripts/install.ps1) ---
funasr==1.2.6
modelscope==1.22.0

# --- Tiện ích ---
httpx==0.28.1
yt-dlp==2025.1.15
soundfile==0.12.1
numpy==1.26.4

# --- Test ---
pytest==8.3.4
```

`backend/app/config.py`:

```python
"""Cấu hình đường dẫn và hằng số vận hành.

Chỉ đọc biến môi trường, không import gì từ app. Được phép import ở mọi tầng.
"""
from __future__ import annotations

import os
import pathlib

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


def _env_path(name: str, default: pathlib.Path) -> pathlib.Path:
    raw = os.environ.get(name)
    return pathlib.Path(raw).expanduser() if raw else default


DATA_DIR = _env_path("PHUDE_DATA", PROJECT_DIR / "data")
MEDIA_DIR = DATA_DIR / "media"
LOG_DIR = DATA_DIR / "logs"
OUTPUT_DIR = DATA_DIR / "output"
DB_PATH = _env_path("PHUDE_DB", DATA_DIR / "app.db")

REGISTRY_PATH = _env_path("PHUDE_REGISTRY", BACKEND_DIR / "registry.json")

HF_HOME = os.environ.get("HF_HOME", r"D:\models\hf")
OLLAMA_MODELS = os.environ.get("OLLAMA_MODELS", r"D:\models\ollama")

API_HOST = os.environ.get("PHUDE_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("PHUDE_PORT", "8620"))

# Ngưỡng nghiệp vụ — sao chép từ spec, KHÔNG tự đoán lại
SUSPECT_NO_SPEECH_PROB = 0.6
SUSPECT_AVG_LOGPROB = -1.0


def ensure_dirs() -> None:
    for d in (DATA_DIR, MEDIA_DIR, LOG_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

`backend/tests/conftest.py`:

```python
from __future__ import annotations

import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
```

- [ ] **Step 3: Chạy test — phải XANH**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_layer_boundary.py -v`

Expected: `4 passed` — trong đó `test_the_guard_itself_can_fail` chứng minh cái lưới thật sự bắt được vi phạm, không phải test rỗng.

- [ ] **Step 4: Commit**

```bash
git add backend data .gitignore
git commit -m "chore(backend): khung du an + test ranh gioi tang domain"
```

---

## Task 2: Domain models + (de)serialize JSON

**Files:**
- Create: `backend/app/domain/models.py`, `backend/tests/test_models_json.py`

**Interfaces:**
- Consumes: không (domain thuần)
- Produces:
  - `Word(w: str, s: float, e: float)`
  - `Segment(i, start, end, text, words, emotion, events, speaker, avg_logprob, no_speech_prob, suspect, t, qa)`
  - `Segment.to_json() -> dict` · `Segment.from_json(d: dict) -> Segment`
  - `segments_to_json(list[Segment]) -> str` · `segments_from_json(str) -> list[Segment]`
  - `Transcript`, `Translation`, `Job`, `Term`, `Source` dataclass

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_models_json.py
from __future__ import annotations

import json

from app.domain.models import Segment, Word, segments_from_json, segments_to_json


def test_segment_roundtrip_keeps_optional_fields_absent():
    seg = Segment(i=0, start=1.02, end=4.38, text="大家好")
    d = seg.to_json()
    assert d["i"] == 0 and d["start"] == 1.02 and d["end"] == 4.38
    assert d["text"] == "大家好"
    assert d["suspect"] is False
    assert "words" not in d, "engine không sinh words thì không được bịa khoá ra"
    assert "t" not in d, "chưa dịch thì không có khoá t"
    assert Segment.from_json(d) == seg


def test_segment_roundtrip_full():
    seg = Segment(
        i=3, start=12.85, end=15.6, text="这个模型它其实……",
        words=[Word(w="这个", s=12.85, e=13.4), Word(w="模型", s=13.4, e=14.1)],
        emotion="happy", events=["bgm"], speaker=None,
        avg_logprob=-1.42, no_speech_prob=0.71, suspect=True,
        t="Mô hình này thực ra thì……", qa=["too_long"],
    )
    d = seg.to_json()
    assert d["suspect"] is True
    assert d["events"] == ["bgm"]
    assert d["words"][0] == {"w": "这个", "s": 12.85, "e": 13.4}
    assert d["t"] == "Mô hình này thực ra thì……"
    assert Segment.from_json(d) == seg


def test_segments_json_is_valid_utf8_and_stable():
    segs = [Segment(i=0, start=0.0, end=1.0, text="你好")]
    raw = segments_to_json(segs)
    assert "你好" in raw, "ensure_ascii=False — đừng escape tiếng Trung"
    assert json.loads(raw)[0]["text"] == "你好"
    assert segments_from_json(raw) == segs


def test_from_json_tolerates_unknown_keys():
    d = {"i": 0, "start": 0.0, "end": 1.0, "text": "x", "la_ky_la": 1}
    assert Segment.from_json(d).text == "x"
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models_json.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.models'`

- [ ] **Step 3: Viết implementation tối thiểu**

```python
# backend/app/domain/models.py
"""Mô hình dữ liệu thuần. KHÔNG import gì ngoài stdlib.

Bất biến quan trọng: khoá tuỳ chọn chỉ xuất hiện khi engine thật sự sinh ra nó.
Không được bịa `words: []` cho engine không có word timestamp — nếu bịa, tầng
giao diện sẽ tưởng có dữ liệu từng từ và vẽ sai.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

SUSPECT_NO_SPEECH_PROB = 0.6
SUSPECT_AVG_LOGPROB = -1.0


@dataclass
class Word:
    w: str
    s: float
    e: float

    def to_json(self) -> dict:
        return {"w": self.w, "s": self.s, "e": self.e}

    @classmethod
    def from_json(cls, d: dict) -> "Word":
        return cls(w=d["w"], s=float(d["s"]), e=float(d["e"]))


@dataclass
class Segment:
    i: int
    start: float
    end: float
    text: str
    words: list[Word] | None = None
    emotion: str | None = None
    events: list[str] = field(default_factory=list)
    speaker: str | None = None
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    suspect: bool = False
    t: str | None = None
    qa: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def mark_suspect(self) -> None:
        """Đặt cờ nghi ngờ theo đúng ngưỡng trong spec."""
        if self.no_speech_prob is not None and self.no_speech_prob > SUSPECT_NO_SPEECH_PROB:
            self.suspect = True
        if self.avg_logprob is not None and self.avg_logprob < SUSPECT_AVG_LOGPROB:
            self.suspect = True

    def to_json(self) -> dict:
        d: dict = {
            "i": self.i,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
        }
        if self.words is not None:
            d["words"] = [w.to_json() for w in self.words]
        if self.emotion is not None:
            d["emotion"] = self.emotion
        if self.events:
            d["events"] = list(self.events)
        if self.speaker is not None:
            d["speaker"] = self.speaker
        if self.avg_logprob is not None:
            d["avg_logprob"] = round(self.avg_logprob, 4)
        if self.no_speech_prob is not None:
            d["no_speech_prob"] = round(self.no_speech_prob, 4)
        d["suspect"] = self.suspect
        if self.t is not None:
            d["t"] = self.t
        if self.qa:
            d["qa"] = list(self.qa)
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Segment":
        words = d.get("words")
        return cls(
            i=int(d["i"]),
            start=float(d["start"]),
            end=float(d["end"]),
            text=d.get("text", ""),
            words=[Word.from_json(w) for w in words] if words is not None else None,
            emotion=d.get("emotion"),
            events=list(d.get("events") or []),
            speaker=d.get("speaker"),
            avg_logprob=d.get("avg_logprob"),
            no_speech_prob=d.get("no_speech_prob"),
            suspect=bool(d.get("suspect", False)),
            t=d.get("t"),
            qa=list(d.get("qa") or []),
        )


def segments_to_json(segments: list[Segment]) -> str:
    return json.dumps([s.to_json() for s in segments], ensure_ascii=False)


def segments_from_json(raw: str) -> list[Segment]:
    return [Segment.from_json(d) for d in json.loads(raw)]


@dataclass
class Source:
    id: int | None
    kind: str          # 'file' | 'url'
    origin: str
    media_path: str
    lang: str | None = None
    audio_path: str | None = None
    duration: float | None = None
    created_at: str = ""


@dataclass
class Transcript:
    id: int | None
    source_id: int
    engine: str
    lang: str
    segments: list[Segment]
    version: int = 1
    status: str = "draft"        # draft | reviewed | translated
    created_at: str = ""


@dataclass
class Translation:
    id: int | None
    transcript_id: int
    transcript_version: int
    engine: str
    segments: list[Segment]
    prompt_version: str
    target_lang: str = "vi"
    glossary_version: int | None = None
    qa_issues: list[str] = field(default_factory=list)
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int | None = None
    created_at: str = ""


@dataclass
class Job:
    id: int | None
    workspace: int
    type: str                 # ingest | asr | translate | export
    engine: str | None
    phase: str
    state: str = "queued"
    payload: dict = field(default_factory=dict)
    cancel_requested: bool = False
    attempts: int = 0
    progress: float = 0.0
    log_tail: str = ""
    log_path: str | None = None
    error: str | None = None
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None


@dataclass
class Term:
    id: int | None
    lang: str
    term: str
    translation: str
    note: str | None = None
    approved: bool = False
    created_at: str = ""


@dataclass
class CallStats:
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int | None = None
```

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models_json.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS. Nếu `test_layer_boundary.py` đỏ, nghĩa là `models.py` vừa import sai — sửa `models.py`, không sửa test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/models.py backend/tests/test_models_json.py
git commit -m "feat(domain): mo hinh Segment/Job/Term + serialize JSON"
```

---

## Task 3: State machine của job + quy tắc stale theo version

**Files:**
- Create: `backend/app/domain/job_state.py`, `backend/app/domain/staleness.py`, `backend/tests/test_job_state.py`, `backend/tests/test_staleness.py`

**Interfaces:**
- Consumes: không
- Produces:
  - hằng số `QUEUED, RUNNING, DONE, FAILED, INTERRUPTED, CANCELLED`
  - `phase_of(job_type: str, engine: str | None) -> str`
  - `can_transition(src: str, dst: str) -> bool` · `assert_transition(src, dst) -> None` (raise `InvalidTransition`)
  - `TERMINAL_STATES: frozenset[str]`
  - `is_stale(transcript_version: int, translated_from_version: int) -> bool`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_job_state.py
from __future__ import annotations

import pytest

from app.domain.job_state import (
    CANCELLED, DONE, FAILED, INTERRUPTED, QUEUED, RUNNING,
    InvalidTransition, assert_transition, can_transition, phase_of,
)


def test_phase_includes_engine_not_just_job_type():
    """Đây là điểm dễ sai nhất của cả hàng đợi: gom theo `asr` là VÔ DỤNG
    vì người dùng đổi được model từng job."""
    assert phase_of("asr", "fw-large-v3-turbo") == "asr:fw-large-v3-turbo"
    assert phase_of("asr", "sensevoice-small") == "asr:sensevoice-small"
    assert phase_of("asr", "fw-large-v3-turbo") != phase_of("asr", "sensevoice-small")
    assert phase_of("ingest", None) == "ingest:-"


@pytest.mark.parametrize("src,dst", [
    (QUEUED, RUNNING), (QUEUED, CANCELLED),
    (RUNNING, DONE), (RUNNING, FAILED), (RUNNING, INTERRUPTED), (RUNNING, CANCELLED),
    (FAILED, QUEUED), (INTERRUPTED, QUEUED),
])
def test_allowed_transitions(src, dst):
    assert can_transition(src, dst) is True
    assert_transition(src, dst)


@pytest.mark.parametrize("src,dst", [
    (DONE, RUNNING), (DONE, QUEUED), (CANCELLED, RUNNING),
    (QUEUED, DONE), (QUEUED, FAILED), (RUNNING, QUEUED),
])
def test_forbidden_transitions(src, dst):
    assert can_transition(src, dst) is False
    with pytest.raises(InvalidTransition):
        assert_transition(src, dst)


def test_unknown_state_is_rejected():
    with pytest.raises(InvalidTransition):
        assert_transition("khong_ton_tai", RUNNING)
```

```python
# backend/tests/test_staleness.py
from __future__ import annotations

from app.domain.staleness import is_stale


def test_translation_from_current_version_is_fresh():
    assert is_stale(transcript_version=5, translated_from_version=5) is False


def test_translation_from_old_version_is_stale():
    assert is_stale(transcript_version=5, translated_from_version=3) is True


def test_first_translation_is_never_stale():
    assert is_stale(transcript_version=1, translated_from_version=1) is False


def test_same_second_edits_still_detected():
    """Đây chính là lý do dùng version thay vì timestamp: hai lần sửa trong
    cùng một giây vẫn phân biệt được."""
    assert is_stale(transcript_version=8, translated_from_version=7) is True
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_job_state.py tests/test_staleness.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Viết implementation**

```python
# backend/app/domain/job_state.py
"""State machine của job. Thuần, không phụ thuộc gì.

Vì sao cần: nếu không định nghĩa transition hợp lệ thì `done -> running` sẽ
xảy ra trong thực tế (double-click, SSE gửi lại) và bảng jobs sẽ mâu thuẫn.
"""
from __future__ import annotations

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
INTERRUPTED = "interrupted"
CANCELLED = "cancelled"

ALL_STATES = frozenset({QUEUED, RUNNING, DONE, FAILED, INTERRUPTED, CANCELLED})
TERMINAL_STATES = frozenset({DONE, CANCELLED})
RETRYABLE_STATES = frozenset({FAILED, INTERRUPTED})

_TRANSITIONS: dict[str, frozenset[str]] = {
    QUEUED: frozenset({RUNNING, CANCELLED}),
    RUNNING: frozenset({DONE, FAILED, INTERRUPTED, CANCELLED}),
    FAILED: frozenset({QUEUED}),
    INTERRUPTED: frozenset({QUEUED}),
    DONE: frozenset(),
    CANCELLED: frozenset(),
}


class InvalidTransition(ValueError):
    pass


def can_transition(src: str, dst: str) -> bool:
    if src not in ALL_STATES or dst not in ALL_STATES:
        return False
    return dst in _TRANSITIONS[src]


def assert_transition(src: str, dst: str) -> None:
    if src not in ALL_STATES:
        raise InvalidTransition(f"trạng thái nguồn không tồn tại: {src!r}")
    if dst not in ALL_STATES:
        raise InvalidTransition(f"trạng thái đích không tồn tại: {dst!r}")
    if not can_transition(src, dst):
        raise InvalidTransition(f"không được chuyển {src!r} -> {dst!r}")


def phase_of(job_type: str, engine: str | None) -> str:
    """Khoá giai đoạn = CẶP (loại job, engine).

    Đây là quyết định trung tâm của hàng đợi. Gom theo `asr`/`mt` là vô dụng
    vì người dùng đổi được model cho từng job: file A dùng turbo, file B dùng
    SenseVoice thì vẫn phải nạp/đổ model như thường.
    """
    return f"{job_type}:{engine if engine else '-'}"
```

```python
# backend/app/domain/staleness.py
"""Quy tắc 'bản dịch đã lỗi thời'. Dùng version, KHÔNG dùng timestamp.

Timestamp trùng nhau được (hai lần sửa trong cùng một giây) và không trả lời
được câu 'bản dịch này dịch từ bản transcript nào'.
"""
from __future__ import annotations


def is_stale(transcript_version: int, translated_from_version: int) -> bool:
    return translated_from_version < transcript_version
```

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_job_state.py tests/test_staleness.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/job_state.py backend/app/domain/staleness.py backend/tests/test_job_state.py backend/tests/test_staleness.py
git commit -m "feat(domain): state machine job + quy tac stale theo version"
```

---

## Task 4: Chuẩn hoá segment — gộp đoạn ngắn, cắt đoạn dài

**Files:**
- Create: `backend/app/domain/segmentation.py`, `backend/tests/test_segmentation.py`

**Interfaces:**
- Consumes: `app.domain.models.Segment`
- Produces: `normalize(segments, *, min_dur, max_dur, max_chars) -> list[Segment]` · hằng số `MIN_DUR=0.8`, `MAX_DUR=7.0`, `MAX_CHARS=84`, `HALLUCINATION_MARKERS`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_segmentation.py
from __future__ import annotations

from app.domain.models import Segment, Word
from app.domain.segmentation import MAX_CHARS, MIN_DUR, normalize


def _s(i, start, end, text, **kw):
    return Segment(i=i, start=start, end=end, text=text, **kw)


def test_renumbers_and_drops_empty():
    got = normalize([_s(5, 0.0, 3.0, "  "), _s(9, 3.0, 6.0, "你好")])
    assert [s.i for s in got] == [0]
    assert got[0].text == "你好"


def test_merges_short_segment_into_previous():
    got = normalize([
        _s(0, 0.0, 2.0, "第一句"),
        _s(1, 2.0, 2.3, "短"),          # 0.3s < MIN_DUR
        _s(2, 2.3, 5.0, "第三句"),
    ])
    assert len(got) == 2
    assert got[0].text == "第一句短"
    assert got[0].end == 2.3
    assert [s.i for s in got] == [0, 1]


def test_first_segment_too_short_merges_forward():
    got = normalize([_s(0, 0.0, 0.4, "嗯"), _s(1, 0.4, 3.0, "正文")])
    assert len(got) == 1
    assert got[0].text == "嗯正文"
    assert got[0].start == 0.0


def test_splits_long_by_duration_using_word_boundaries():
    words = [Word(w=f"词{k}", s=float(k), e=float(k + 1)) for k in range(10)]
    got = normalize([_s(0, 0.0, 10.0, "".join(w.w for w in words), words=words)])
    assert len(got) == 2, "10s > MAX_DUR phải bị cắt"
    assert got[0].end == got[1].start, "mốc nối phải liền nhau, không hở"
    assert all(s.duration <= 7.0 + 1e-6 for s in got)


def test_splits_long_by_chars_when_no_words():
    text = "一" * (MAX_CHARS + 40)
    got = normalize([_s(0, 0.0, 5.0, text)])
    assert len(got) == 2
    assert all(len(s.text) <= MAX_CHARS for s in got)
    assert got[0].start == 0.0 and got[-1].end == 5.0
    assert "".join(s.text for s in got) == text, "không được mất chữ khi cắt"


def test_removes_hallucination_markers():
    got = normalize([_s(0, 0.0, 3.0, "感谢观看"), _s(1, 3.0, 6.0, "真的一句")])
    assert [s.text for s in got] == ["真的一句"]


def test_keeps_confidence_and_suspect_flags_when_merging():
    got = normalize([
        _s(0, 0.0, 2.0, "甲", no_speech_prob=0.9, avg_logprob=-2.0, suspect=True),
        _s(1, 2.0, 2.2, "乙"),
    ])
    assert len(got) == 1
    assert got[0].suspect is True
    assert got[0].no_speech_prob == 0.9
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_segmentation.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Viết implementation**

```python
# backend/app/domain/segmentation.py
"""Hậu xử lý segment sau khi ASR trả về. Thuần.

Ba việc: bỏ rác, gộp đoạn quá ngắn, cắt đoạn quá dài.
Bất biến: không bao giờ mất chữ, và mốc thời gian luôn liền nhau (không hở).
"""
from __future__ import annotations

import math

from .models import Segment, Word

MIN_DUR = 0.8
MAX_DUR = 7.0
MAX_CHARS = 42 * 2          # 2 dòng × 42 ký tự

HALLUCINATION_MARKERS = (
    "[Music]", "[music]", "[Âm nhạc]", "[Applause]", "[Laughter]",
    "♪", "♪♪",
    "感谢观看", "感谢大家观看", "请不吝点赞", "订阅频道", "字幕由", "字幕组",
    "Thanks for watching", "Thank you for watching",
    "ご視聴ありがとうございました",
)


def _strip_markers(text: str) -> str:
    out = text
    for marker in HALLUCINATION_MARKERS:
        out = out.replace(marker, "")
    return " ".join(out.split()).strip()


def _seg_with(seg: Segment, **changes) -> Segment:
    """Sao chép segment với vài trường đổi. Dùng thay cho dataclasses.replace
    để giữ nguyên các trường tuỳ chọn không đụng tới."""
    data = seg.to_json()
    data.update(changes)
    return Segment.from_json(data)


def _merge(a: Segment, b: Segment) -> Segment:
    """Gộp b liền sau a. Giữ tín hiệu tin cậy XẤU NHẤT của cả hai."""
    words: list[Word] | None = None
    if a.words is not None and b.words is not None:
        words = list(a.words) + list(b.words)
    probs = [p for p in (a.no_speech_prob, b.no_speech_prob) if p is not None]
    logprobs = [p for p in (a.avg_logprob, b.avg_logprob) if p is not None]
    return _seg_with(
        a,
        text=(a.text + b.text).strip(),
        end=b.end,
        words=words,
        events=list(dict.fromkeys(a.events + b.events)),
        avg_logprob=min(logprobs) if logprobs else None,
        no_speech_prob=max(probs) if probs else None,
        suspect=a.suspect or b.suspect,
    )


def _split_once(seg: Segment, max_dur: float, max_chars: float) -> tuple[Segment, Segment]:
    """Cắt đôi một segment tại ranh giới từ gần giữa nhất."""
    if seg.words and len(seg.words) >= 2:
        mid = len(seg.words) // 2
        left_words, right_words = seg.words[:mid], seg.words[mid:]
        cut = left_words[-1].e
        left_text = seg.text[: max(1, len(seg.text) // 2)] if not left_words else "".join(w.w for w in left_words)
        right_text = seg.text[len(left_text):]
        return (
            _seg_with(seg, text=left_text.strip(), end=cut, words=left_words),
            _seg_with(seg, text=right_text.strip(), start=cut, words=right_words),
        )

    # Không có word timestamp: cắt theo ký tự, chia thời gian theo tỉ lệ ký tự.
    half = len(seg.text) // 2
    # lùi về khoảng trắng gần nhất nếu có (tiếng Anh)
    space = seg.text.rfind(" ", 0, half + 10)
    if space > 0:
        half = space
    left_text, right_text = seg.text[:half], seg.text[half:]
    ratio = len(left_text) / max(1, len(seg.text))
    cut = seg.start + seg.duration * ratio
    return (
        _seg_with(seg, text=left_text.strip(), end=cut, words=None),
        _seg_with(seg, text=right_text.strip(), start=cut, words=None),
    )


def _split(seg: Segment, max_dur: float, max_chars: float) -> list[Segment]:
    if seg.duration <= max_dur and len(seg.text) <= max_chars:
        return [seg]
    if len(seg.text) < 2:
        return [seg]
    left, right = _split_once(seg, max_dur, max_chars)
    if not left.text or not right.text:
        return [seg]
    return _split(left, max_dur, max_chars) + _split(right, max_dur, max_chars)


def normalize(
    segments: list[Segment],
    *,
    min_dur: float = MIN_DUR,
    max_dur: float = MAX_DUR,
    max_chars: int = MAX_CHARS,
) -> list[Segment]:
    cleaned: list[Segment] = []
    for seg in segments:
        text = _strip_markers(seg.text)
        if not text:
            continue
        if text != seg.text:
            seg = _seg_with(seg, text=text)
        cleaned.append(seg)

    merged: list[Segment] = []
    for seg in cleaned:
        if merged and seg.duration < min_dur:
            merged[-1] = _merge(merged[-1], seg)
        elif not merged and seg.duration < min_dur:
            merged.append(seg)          # sẽ gộp xuôi ở vòng sau
        else:
            if merged and merged[-1].duration < min_dur:
                merged[-1] = _merge(merged[-1], seg)
            else:
                merged.append(seg)
    # gộp xuôi cho đoạn đầu quá ngắn
    if len(merged) >= 2 and merged[0].duration < min_dur:
        merged[1] = _merge(merged[0], merged[1])
        merged.pop(0)

    split: list[Segment] = []
    for seg in merged:
        split.extend(_split(seg, max_dur, max_chars))

    return [_seg_with(s, i=idx) for idx, s in enumerate(split)]
```

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_segmentation.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS. Nếu `test_splits_long_by_chars_when_no_words` đỏ vì mất chữ, kiểm tra `_split_once` — nó phải chia `seg.text` thành hai phần **liền nhau, không chồng, không hở**.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/segmentation.py backend/tests/test_segmentation.py
git commit -m "feat(domain): chuan hoa segment - gop doan ngan, cat doan dai"
```

---

## Task 5: Chia lô dịch theo ngân sách token

**Files:**
- Create: `backend/app/domain/batching.py`, `backend/tests/test_batching.py`

**Interfaces:**
- Consumes: `app.domain.models.Segment`
- Produces:
  - `Batch(segments: tuple[Segment,...], before: tuple[Segment,...], after: tuple[Segment,...])`
  - `estimate_output_tokens(source_text, ratio=TOKENS_PER_SOURCE_CHAR) -> int`
  - `make_batches(segments, *, budget, max_segments, context, ratio) -> list[Batch]`
  - hằng số `OUTPUT_TOKEN_BUDGET=1200`, `MAX_SEGMENTS_PER_BATCH=30`, `CONTEXT_SEGMENTS=2`, `TOKENS_PER_SOURCE_CHAR=1.0`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_batching.py
from __future__ import annotations

from app.domain.batching import (
    CONTEXT_SEGMENTS, MAX_SEGMENTS_PER_BATCH, OUTPUT_TOKEN_BUDGET,
    estimate_output_tokens, make_batches,
)
from app.domain.models import Segment


def _segs(n, chars=10):
    return [Segment(i=i, start=float(i), end=float(i + 1), text="一" * chars) for i in range(n)]


def test_estimate_is_linear_in_source_chars():
    assert estimate_output_tokens("") == 1
    assert estimate_output_tokens("一" * 100, ratio=1.0) == 100
    assert estimate_output_tokens("一" * 100, ratio=0.5) == 50


def test_splits_by_token_budget_not_by_count():
    """Đây là lỗi mà kế hoạch này sửa so với bản spec đầu: chia theo SỐ segment
    là sai đơn vị — 25 segment ngắn và 25 segment dài chênh nhau 8 lần."""
    short = [Segment(i=i, start=float(i), end=float(i + 1), text="一" * 10) for i in range(300)]
    batches = make_batches(short, budget=100, max_segments=1000, context=0)
    assert all(sum(estimate_output_tokens(s.text) for s in b.segments) <= 100 for b in batches)
    assert sum(len(b.segments) for b in batches) == 300

    long = [Segment(i=i, start=float(i), end=float(i + 1), text="一" * 60) for i in range(300)]
    long_batches = make_batches(long, budget=100, max_segments=1000, context=0)
    assert len(long_batches) > len(batches), "segment dài phải cho nhiều lô hơn"


def test_single_oversized_segment_gets_its_own_batch():
    segs = [Segment(i=0, start=0.0, end=1.0, text="一" * 5000)]
    batches = make_batches(segs, budget=100, context=0)
    assert len(batches) == 1
    assert len(batches[0].segments) == 1


def test_hard_cap_on_segment_count():
    segs = _segs(100, chars=1)
    batches = make_batches(segs, budget=10**9, max_segments=MAX_SEGMENTS_PER_BATCH, context=0)
    assert all(len(b.segments) <= MAX_SEGMENTS_PER_BATCH for b in batches)
    assert len(batches) == 4


def test_context_is_taken_from_neighbours_and_excluded_from_payload():
    segs = _segs(10)
    batches = make_batches(segs, budget=30, max_segments=3, context=CONTEXT_SEGMENTS)
    first = batches[0]
    assert first.before == (), "lô đầu không có ngữ cảnh trước"
    assert [s.i for s in first.after] == [3, 4]
    mid = batches[1]
    assert [s.i for s in mid.before] == [1, 2]
    assert all(s.i not in {x.i for x in mid.segments} for s in mid.before)


def test_no_segment_is_lost_or_duplicated():
    segs = _segs(37, chars=7)
    batches = make_batches(segs, budget=25, max_segments=4, context=2)
    flat = [s.i for b in batches for s in b.segments]
    assert flat == list(range(37))


def test_empty_input_gives_no_batches():
    assert make_batches([], budget=100, context=2) == []
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_batching.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Viết implementation**

```python
# backend/app/domain/batching.py
"""Chia lô để dịch. Thuần.

Chia theo NGÂN SÁCH TOKEN, không theo số segment. Số segment chỉ là trần phụ
để chặn rủi ro hỏng JSON khi lô có quá nhiều mục.

TOKENS_PER_SOURCE_CHAR = 1.0 là GIÁ TRỊ TẠM. Giai đoạn 1b phải đo thật tỉ lệ
ký tự nguồn -> token đích rồi hiệu chỉnh; xem spec §10 bảng benchmark.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Segment

OUTPUT_TOKEN_BUDGET = 1200
MAX_SEGMENTS_PER_BATCH = 30
CONTEXT_SEGMENTS = 2
TOKENS_PER_SOURCE_CHAR = 1.0


@dataclass(frozen=True)
class Batch:
    segments: tuple[Segment, ...]
    before: tuple[Segment, ...] = ()
    after: tuple[Segment, ...] = ()

    @property
    def indices(self) -> tuple[int, ...]:
        return tuple(s.i for s in self.segments)


def estimate_output_tokens(
    source_text: str, ratio: float = TOKENS_PER_SOURCE_CHAR
) -> int:
    return max(1, math.ceil(len(source_text) * ratio))


def make_batches(
    segments: list[Segment],
    *,
    budget: int = OUTPUT_TOKEN_BUDGET,
    max_segments: int = MAX_SEGMENTS_PER_BATCH,
    context: int = CONTEXT_SEGMENTS,
    ratio: float = TOKENS_PER_SOURCE_CHAR,
) -> list[Batch]:
    if not segments:
        return []

    groups: list[list[Segment]] = []
    current: list[Segment] = []
    used = 0
    for seg in segments:
        cost = estimate_output_tokens(seg.text, ratio)
        too_big = current and (used + cost > budget or len(current) >= max_segments)
        if too_big:
            groups.append(current)
            current, used = [], 0
        current.append(seg)
        used += cost
    if current:
        groups.append(current)

    batches: list[Batch] = []
    cursor = 0
    for group in groups:
        before = tuple(segments[max(0, cursor - context):cursor])
        after = tuple(segments[cursor + len(group): cursor + len(group) + context])
        batches.append(Batch(segments=tuple(group), before=before, after=after))
        cursor += len(group)
    return batches
```

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_batching.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/batching.py backend/tests/test_batching.py
git commit -m "feat(domain): chia lo dich theo ngan sach token"
```

---

## Task 6: CPS (tốc độ đọc) + QA tầng 1

**Files:**
- Create: `backend/app/domain/readability.py`, `backend/app/domain/qa_rules.py`, `backend/tests/test_readability.py`, `backend/tests/test_qa_rules.py`

**Interfaces:**
- Consumes: `app.domain.models.Segment`
- Produces:
  - `reading_cps(text, start, end) -> float` · `is_too_fast(text, start, end, threshold=CPS_WARN) -> bool` · `CPS_WARN = 20.0`
  - `check(source_text, translated_text, glossary_terms=(), *, length_ratio_max=5.0) -> list[str]` — trả về mã lỗi dạng chuỗi

  **SỬA SAU KHI SHIP (R18, R22).** Bản đầu ghi `length_ratio_max=3.0` — **sai**: 3.0 gắn cờ `too_long` cho
  **mọi** bản dịch Trung→Việt đúng (đo được: ca sạch 3,86; ca glossary 4,33). Code đã ship dùng **5.0**.
  Và `glossary_terms` **phải là các bản dịch ĐÍCH**, không phải thuật ngữ nguồn — xem R22.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_readability.py
from __future__ import annotations

from app.domain.readability import CPS_WARN, is_too_fast, reading_cps


def test_cps_counts_chars_without_spaces():
    # 20 ký tự không tính khoảng trắng, trong 2 giây -> 10 CPS
    assert reading_cps("a b c d e f g h i j k l m n o p q r s t", 0.0, 2.0) == 10.0


def test_zero_or_negative_duration_is_infinite_not_a_crash():
    assert reading_cps("abc", 5.0, 5.0) == float("inf")
    assert is_too_fast("abc", 5.0, 5.0) is True


def test_vietnamese_line_over_threshold_is_flagged():
    text = "Hôm nay chúng ta sẽ cùng bàn về trí tuệ nhân tạo"
    assert reading_cps(text, 0.0, 2.0) > CPS_WARN
    assert is_too_fast(text, 0.0, 2.0) is True
    assert is_too_fast(text, 0.0, 6.0) is False
```

```python
# backend/tests/test_qa_rules.py
from __future__ import annotations

from app.domain.qa_rules import check


def test_clean_translation_has_no_issues():
    assert check("人工智能很有趣", "Trí tuệ nhân tạo rất thú vị") == []


def test_empty_translation_is_flagged():
    assert "empty" in check("人工智能", "   ")


def test_missing_number_is_flagged_with_the_number():
    issues = check("增长到 2025 年", "Tăng trưởng trong năm nay")
    assert any(i.startswith("missing_number:2025") for i in issues), issues


def test_present_number_is_not_flagged():
    assert not [i for i in check("增长到 2025 年", "Tăng đến năm 2025") if i.startswith("missing_number")]


def test_missing_glossary_term_is_flagged():
    issues = check("大模型很重要", "Mô hình rất quan trọng", glossary_terms=["大模型"])
    assert "missing_term:大模型" in issues


def test_glossary_term_present_is_clean():
    assert check("大模型很重要", "Mô hình lớn rất quan trọng", glossary_terms=["Mô hình lớn"]) == []


def test_overlong_translation_is_flagged():
    issues = check("好", "tốt " * 40)
    assert "too_long" in issues


def test_short_translation_is_not_flagged_for_length():
    assert "too_long" not in check("这是一个很长的句子用来测试", "Ngắn")
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_readability.py tests/test_qa_rules.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Viết implementation**

```python
# backend/app/domain/readability.py
"""Tốc độ đọc (CPS). Thuần.

Vì sao cần riêng một module: tiếng Việt dài gấp 2-3 lần tiếng Trung. Một dòng
phụ đề dịch đúng nghĩa vẫn có thể KHÔNG ĐỌC KỊP. Đây là lỗi phụ đề phổ biến
nhất và nó chỉ lộ ra khi đặt bản gốc cạnh bản dịch.
"""
from __future__ import annotations

CPS_WARN = 20.0


def reading_cps(text: str, start: float, end: float) -> float:
    """Ký tự không tính khoảng trắng trên mỗi giây."""
    duration = end - start
    if duration <= 0:
        return float("inf")
    chars = len("".join(text.split()))
    return chars / duration


def is_too_fast(text: str, start: float, end: float, threshold: float = CPS_WARN) -> bool:
    return reading_cps(text, start, end) > threshold
```

```python
# backend/app/domain/qa_rules.py
"""QA tầng 1 — thuần code, miễn phí, chạy trên MỌI segment.

Tầng 2 (gọi LLM soát lại) chỉ chạy trên segment đã bị tầng này cảnh báo, để
không đốt token. Xem spec §8.8.

Tên riêng không có NER ở đây — dùng chính thuật ngữ glossary làm đại diện. Đó
là thứ duy nhất người dùng đã nói rõ là quan trọng.

    HỢP ĐỒNG NGÔN NGỮ (làm rõ sau khi ship, R22): `glossary_terms` phải chứa các
    bản dịch ĐÍCH, không phải thuật ngữ nguồn. Hàm so chúng với `translated_text`,
    nên truyền thuật ngữ nguồn (ví dụ "大模型") sẽ báo `missing_term` cho MỌI dòng
    đúng, và đẩy mọi dòng có thuật ngữ lên QA tầng 2 — ồn và tốn, không sai phụ đề.
là thứ duy nhất người dùng đã nói rõ là quan trọng.
"""
from __future__ import annotations

import re

LENGTH_RATIO_MAX = 5.0   # SỬA SAU KHI SHIP (R18): spec §8.8 ghi 3.0 và 3.0 SAI cho Trung→Việt
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_GARBAGE_RE = re.compile(r"^[\W_]+$", re.UNICODE)


def _numbers(text: str) -> set[str]:
    return {m.group(0) for m in _NUMBER_RE.finditer(text)}


def check(
    source_text: str,
    translated_text: str,
    glossary_terms: tuple[str, ...] | list[str] = (),
    *,
    length_ratio_max: float = LENGTH_RATIO_MAX,
) -> list[str]:
    issues: list[str] = []
    translated = translated_text.strip()

    if not translated or _GARBAGE_RE.match(translated):
        return ["empty"]

    for number in sorted(_numbers(source_text)):
        if number not in translated:
            issues.append(f"missing_number:{number}")

    for term in glossary_terms:
        if term and term not in translated:
            issues.append(f"missing_term:{term}")

    source_len = max(1, len(source_text.strip()))
    if len(translated) > source_len * length_ratio_max:
        issues.append("too_long")

    return issues
```

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_readability.py tests/test_qa_rules.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/readability.py backend/app/domain/qa_rules.py backend/tests/test_readability.py backend/tests/test_qa_rules.py
git commit -m "feat(domain): CPS toc do doc + QA tang 1 thuan code"
```

---

## Task 7: Ports + SQLite schema + repository

**Files:**
- Create: `backend/app/ports/__init__.py`, `backend/app/ports/clock.py`, `backend/app/ports/repos.py`, `backend/app/ports/asr.py`, `backend/app/ports/governor.py`
- Create: `backend/app/adapters/__init__.py`, `backend/app/adapters/clock_system.py`, `backend/app/adapters/persist/__init__.py`, `backend/app/adapters/persist/schema.py`, `backend/app/adapters/persist/sqlite_repos.py`
- Create: `backend/tests/test_repos.py`

**Interfaces:**
- Consumes: `app.domain.models`, `app.domain.job_state`
- Produces:
  - `Clock` Protocol: `now_iso() -> str`
  - `SystemClock`
  - `ASREngine` Protocol: `engine_id: str` · `transcribe(audio_path: str, lang: str) -> list[Segment]` · `release() -> None`
  - `ResourceGovernor` Protocol: `before_phase(phase: str) -> None` · `after_phase(phase: str) -> None` · `can_run_parallel(a_vram_mb: int, b_vram_mb: int) -> bool`
  - `SqliteRepos(db_path)` với các phương thức ở Step 3
  - `SCHEMA_SQL` (chuỗi DDL)

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_repos.py
from __future__ import annotations

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.domain.models import Job, Segment


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def test_source_and_transcript_roundtrip(repos):
    sid = repos.add_source(kind="file", origin="a.mp4", media_path="m/a.mp4",
                           lang="zh", audio_path="m/a.wav", duration=12.5)
    segs = [Segment(i=0, start=0.0, end=2.0, text="你好")]
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh", segments=segs)

    t = repos.get_transcript(tid)
    assert t.version == 1 and t.status == "draft"
    assert t.segments[0].text == "你好"
    assert repos.get_source(sid).duration == 12.5


def test_update_segments_bumps_version(repos):
    sid = repos.add_source(kind="file", origin="a", media_path="m", lang="zh")
    tid = repos.add_transcript(source_id=sid, engine="e", lang="zh",
                               segments=[Segment(i=0, start=0.0, end=1.0, text="a")])
    assert repos.update_transcript_segments(tid, [Segment(i=0, start=0.0, end=1.0, text="b")]) == 2
    assert repos.update_transcript_segments(tid, [Segment(i=0, start=0.0, end=1.0, text="c")]) == 3
    assert repos.get_transcript(tid).version == 3


def test_queue_picks_oldest_of_a_given_phase(repos):
    for engine in ("fw-large-v3-turbo", "sensevoice-small", "fw-large-v3-turbo"):
        repos.add_job(Job(id=None, workspace=1, type="asr", engine=engine,
                          phase=js.phase_of("asr", engine), payload={"source_id": 1}))
    first = repos.next_queued_for_phase("asr:fw-large-v3-turbo")
    assert first.engine == "fw-large-v3-turbo"
    oldest = repos.oldest_queued()
    assert oldest.id == 1, "job cũ nhất phải là cái đầu tiên được thêm"


def test_queue_ignores_cancelled_and_done(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e",
                            phase="asr:e", payload={}))
    repos.set_job_state(jid, js.RUNNING)
    repos.set_job_state(jid, js.DONE)
    assert repos.oldest_queued() is None
    assert repos.next_queued_for_phase("asr:e") is None


def test_mark_running_as_interrupted_at_startup(repos):
    a = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    b = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.set_job_state(a, js.RUNNING)
    repos.set_job_state(b, js.QUEUED)
    assert repos.mark_running_as_interrupted() == 1
    assert repos.get_job(a).state == js.INTERRUPTED
    assert repos.get_job(b).state == js.QUEUED
    assert repos.get_job(a).finished_at is not None


def test_illegal_transition_raises(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.set_job_state(jid, js.RUNNING)
    repos.set_job_state(jid, js.DONE)
    with pytest.raises(js.InvalidTransition):
        repos.set_job_state(jid, js.RUNNING)


def test_cancel_request_and_progress_and_log_tail(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.request_cancel(jid)
    assert repos.get_job(jid).cancel_requested is True
    repos.set_job_progress(jid, 0.42)
    assert repos.get_job(jid).progress == pytest.approx(0.42)
    for n in range(150):
        repos.append_job_log(jid, f"line {n}")
    tail = repos.get_job(jid).log_tail.splitlines()
    assert len(tail) == 100, "log_tail phải giữ đúng 100 dòng cuối"
    assert tail[-1] == "line 149"


def test_retry_after_failure_resets_to_queued_and_bumps_attempts(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.set_job_state(jid, js.RUNNING)
    repos.set_job_state(jid, js.FAILED, error="boom")
    repos.retry_job(jid)
    j = repos.get_job(jid)
    assert j.state == js.QUEUED and j.attempts == 1 and j.error is None


def test_llm_calls_are_recorded(repos):
    jid = repos.add_job(Job(id=None, workspace=1, type="asr", engine="e", phase="asr:e", payload={}))
    repos.add_llm_call(job_id=jid, engine="e", model_ref="m", prompt_version=None,
                       tokens_in=None, tokens_out=None, duration_ms=123, ok=True, error=None)
    rows = repos.list_llm_calls(jid)
    assert len(rows) == 1 and rows[0]["duration_ms"] == 123


def test_glossary_upsert_and_list(repos):
    repos.upsert_term(lang="zh", term="大模型", translation="mô hình lớn", note=None, approved=False)
    repos.upsert_term(lang="zh", term="大模型", translation="mô hình lớn", note="sửa", approved=True)
    terms = repos.list_terms(lang="zh")
    assert len(terms) == 1
    assert terms[0].approved is True
    assert repos.glossary_version() == 2, "mỗi lần ghi glossary phải tăng version"


def test_settings_roundtrip(repos):
    assert repos.get_setting("auto_forward", default="1") == "1"
    repos.set_setting("auto_forward", "0")
    assert repos.get_setting("auto_forward") == "0"
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_repos.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.adapters'`

- [ ] **Step 3: Viết ports**

```python
# backend/app/ports/clock.py
from __future__ import annotations

from typing import Protocol


class Clock(Protocol):
    def now_iso(self) -> str:
        """ISO-8601 UTC, ví dụ '2026-09-25T14:02:11Z'."""
        ...
```

```python
# backend/app/ports/asr.py
from __future__ import annotations

from typing import Protocol

from app.domain.models import Segment


class ASREngine(Protocol):
    engine_id: str

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        ...

    def release(self) -> None:
        """Giải phóng VRAM. Phải an toàn khi gọi nhiều lần."""
        ...
```

```python
# backend/app/ports/governor.py
from __future__ import annotations

from typing import Protocol


class ResourceGovernor(Protocol):
    def before_phase(self, phase: str) -> None:
        """Giải phóng VRAM mà giai đoạn mới cần, trước khi nạp model của nó."""
        ...

    def after_phase(self, phase: str) -> None:
        """Gọi khi rời một giai đoạn (hàng đợi hết việc của giai đoạn đó)."""
        ...

    def can_run_parallel(self, a_vram_mb: int, b_vram_mb: int) -> bool:
        """Chỉ dùng ở GĐ3. GĐ1a luôn trả False."""
        ...
```

```python
# backend/app/ports/repos.py
"""Giao diện lưu trữ. Chỉ là Protocol — không hiện thực gì ở đây."""
from __future__ import annotations

from typing import Protocol

from app.domain.models import (CallStats, Job, Segment, Source, Term, Transcript)


class Repos(Protocol):
    # sources
    def add_source(self, *, kind: str, origin: str, media_path: str,
                   lang: str | None = None, audio_path: str | None = None,
                   duration: float | None = None) -> int: ...
    def get_source(self, source_id: int) -> Source: ...
    def set_source_audio(self, source_id: int, audio_path: str, duration: float) -> None: ...

    # transcripts
    def add_transcript(self, *, source_id: int, engine: str, lang: str,
                       segments: list[Segment]) -> int: ...
    def get_transcript(self, transcript_id: int) -> Transcript: ...
    def list_transcripts(self) -> list[Transcript]: ...
    def update_transcript_segments(self, transcript_id: int,
                                   segments: list[Segment]) -> int: ...
    def set_transcript_status(self, transcript_id: int, status: str) -> None: ...

    # jobs
    def add_job(self, job: Job) -> int: ...
    def get_job(self, job_id: int) -> Job: ...
    def list_jobs(self, *, states: tuple[str, ...] | None = None) -> list[Job]: ...
    def oldest_queued(self) -> Job | None: ...
    def next_queued_for_phase(self, phase: str) -> Job | None: ...
    def set_job_state(self, job_id: int, state: str, *,
                      error: str | None = None) -> None: ...
    def set_job_progress(self, job_id: int, progress: float) -> None: ...
    def append_job_log(self, job_id: int, line: str) -> None: ...
    def request_cancel(self, job_id: int) -> None: ...
    def mark_running_as_interrupted(self) -> int: ...
    def retry_job(self, job_id: int) -> None: ...

    # glossary / settings / calls
    def upsert_term(self, *, lang: str, term: str, translation: str,
                    note: str | None, approved: bool) -> int: ...
    def list_terms(self, *, lang: str | None = None) -> list[Term]: ...
    def glossary_version(self) -> int: ...
    def get_setting(self, key: str, default: str | None = None) -> str | None: ...
    def set_setting(self, key: str, value: str) -> None: ...
    def add_llm_call(self, *, job_id: int | None, engine: str, model_ref: str | None,
                     prompt_version: str | None, tokens_in: int | None,
                     tokens_out: int | None, duration_ms: int | None,
                     ok: bool, error: str | None) -> int: ...
    def list_llm_calls(self, job_id: int | None = None) -> list[dict]: ...
```

- [ ] **Step 4: Viết schema + adapter SQLite**

```python
# backend/app/adapters/persist/schema.py
SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('file','url')),
  origin TEXT NOT NULL,
  media_path TEXT NOT NULL,
  audio_path TEXT,
  duration REAL,
  lang TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES sources(id),
  engine TEXT NOT NULL,
  lang TEXT NOT NULL,
  segments TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS translations (
  id INTEGER PRIMARY KEY,
  transcript_id INTEGER NOT NULL REFERENCES transcripts(id),
  transcript_version INTEGER NOT NULL,
  engine TEXT NOT NULL,
  target_lang TEXT NOT NULL DEFAULT 'vi',
  segments TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  glossary_version INTEGER,
  qa_issues TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  duration_ms INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY,
  workspace INTEGER NOT NULL CHECK(workspace IN (1,2)),
  type TEXT NOT NULL,
  engine TEXT,
  phase TEXT NOT NULL,
  state TEXT NOT NULL,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  progress REAL NOT NULL DEFAULT 0,
  log_tail TEXT NOT NULL DEFAULT '',
  log_path TEXT,
  error TEXT,
  payload TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_state_phase ON jobs(state, phase, id);

CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY,
  job_id INTEGER,
  engine TEXT NOT NULL,
  model_ref TEXT,
  prompt_version TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  duration_ms INTEGER,
  ok INTEGER NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS glossary (
  id INTEGER PRIMARY KEY,
  lang TEXT NOT NULL,
  term TEXT NOT NULL,
  translation TEXT NOT NULL,
  note TEXT,
  approved INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(lang, term)
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""
```

```python
# backend/app/adapters/persist/sqlite_repos.py
from __future__ import annotations

import json
import pathlib
import sqlite3
from typing import Iterable

from app.domain import job_state as js
from app.domain.models import (
    Job, Segment, Source, Term, Transcript,
    segments_from_json, segments_to_json,
)
from app.ports.clock import Clock

from .schema import SCHEMA_SQL, SCHEMA_VERSION

LOG_TAIL_LINES = 100


class NotFound(LookupError):
    pass


class SqliteRepos:
    """Hiện thực Repos trên SQLite.

    Một kết nối cho mỗi luồng gọi. GĐ1a chỉ có một worker + các request FastAPI
    đọc, nên khoá ghi ở mức kết nối là đủ.
    """

    def __init__(self, db_path: str | pathlib.Path, *, clock: Clock) -> None:
        self.db_path = str(db_path)
        self._clock = clock

    # ---------- hạ tầng ----------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self) -> None:
        pathlib.Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES('version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    # ---------- sources ----------
    def add_source(self, *, kind: str, origin: str, media_path: str,
                   lang: str | None = None, audio_path: str | None = None,
                   duration: float | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO sources(kind, origin, media_path, audio_path, duration, lang, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (kind, origin, media_path, audio_path, duration, lang, self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def get_source(self, source_id: int) -> Source:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise NotFound(f"source {source_id} không tồn tại")
        return Source(id=row["id"], kind=row["kind"], origin=row["origin"],
                      media_path=row["media_path"], lang=row["lang"],
                      audio_path=row["audio_path"], duration=row["duration"],
                      created_at=row["created_at"])

    def set_source_audio(self, source_id: int, audio_path: str, duration: float) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sources SET audio_path=?, duration=? WHERE id=?",
                         (audio_path, duration, source_id))

    # ---------- transcripts ----------
    def add_transcript(self, *, source_id: int, engine: str, lang: str,
                       segments: list[Segment]) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO transcripts(source_id, engine, lang, segments, version, status, created_at)"
                " VALUES(?,?,?,?,1,'draft',?)",
                (source_id, engine, lang, segments_to_json(segments), self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def _row_to_transcript(self, row: sqlite3.Row) -> Transcript:
        return Transcript(
            id=row["id"], source_id=row["source_id"], engine=row["engine"],
            lang=row["lang"], segments=segments_from_json(row["segments"]),
            version=row["version"], status=row["status"], created_at=row["created_at"],
        )

    def get_transcript(self, transcript_id: int) -> Transcript:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM transcripts WHERE id=?", (transcript_id,)).fetchone()
        if row is None:
            raise NotFound(f"transcript {transcript_id} không tồn tại")
        return self._row_to_transcript(row)

    def list_transcripts(self) -> list[Transcript]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM transcripts ORDER BY id DESC").fetchall()
        return [self._row_to_transcript(r) for r in rows]

    def update_transcript_segments(self, transcript_id: int,
                                  segments: list[Segment]) -> int:
        """Ghi segments và TĂNG version. Trả về version mới.

        Version tăng là cơ chế duy nhất khiến bản dịch cũ thành 'lỗi thời'.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT version FROM transcripts WHERE id=?",
                               (transcript_id,)).fetchone()
            if row is None:
                raise NotFound(f"transcript {transcript_id} không tồn tại")
            new_version = int(row["version"]) + 1
            conn.execute("UPDATE transcripts SET segments=?, version=? WHERE id=?",
                         (segments_to_json(segments), new_version, transcript_id))
            return new_version

    def set_transcript_status(self, transcript_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE transcripts SET status=? WHERE id=?", (status, transcript_id))

    # ---------- jobs ----------
    def add_job(self, job: Job) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO jobs(workspace, type, engine, phase, state, cancel_requested,"
                " attempts, progress, log_tail, log_path, error, payload, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job.workspace, job.type, job.engine, job.phase, job.state,
                 int(job.cancel_requested), job.attempts, job.progress, job.log_tail,
                 job.log_path, job.error, json.dumps(job.payload or {}, ensure_ascii=False),
                 job.created_at or self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"], workspace=row["workspace"], type=row["type"], engine=row["engine"],
            phase=row["phase"], state=row["state"],
            cancel_requested=bool(row["cancel_requested"]), attempts=row["attempts"],
            progress=row["progress"], log_tail=row["log_tail"], log_path=row["log_path"],
            error=row["error"], payload=json.loads(row["payload"] or "{}"),
            created_at=row["created_at"], started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    def get_job(self, job_id: int) -> Job:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise NotFound(f"job {job_id} không tồn tại")
        return self._row_to_job(row)

    def list_jobs(self, *, states: tuple[str, ...] | None = None) -> list[Job]:
        sql = "SELECT * FROM jobs"
        params: tuple = ()
        if states:
            sql += f" WHERE state IN ({','.join('?' * len(states))})"
            params = tuple(states)
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_job(r) for r in rows]

    def oldest_queued(self) -> Job | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE state=? ORDER BY id LIMIT 1", (js.QUEUED,)
            ).fetchone()
        return self._row_to_job(row) if row else None

    def next_queued_for_phase(self, phase: str) -> Job | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE state=? AND phase=? ORDER BY id LIMIT 1",
                (js.QUEUED, phase),
            ).fetchone()
        return self._row_to_job(row) if row else None

    def set_job_state(self, job_id: int, state: str, *, error: str | None = None) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise NotFound(f"job {job_id} không tồn tại")
            js.assert_transition(row["state"], state)
            now = self._clock.now_iso()
            if state == js.RUNNING:
                conn.execute(
                    "UPDATE jobs SET state=?, started_at=COALESCE(started_at, ?), error=NULL WHERE id=?",
                    (state, now, job_id))
            elif state in (js.DONE, js.FAILED, js.INTERRUPTED, js.CANCELLED):
                conn.execute(
                    "UPDATE jobs SET state=?, finished_at=?, error=COALESCE(?, error) WHERE id=?",
                    (state, now, error, job_id))
            else:
                conn.execute("UPDATE jobs SET state=?, finished_at=NULL, error=? WHERE id=?",
                             (state, error, job_id))

    def set_job_progress(self, job_id: int, progress: float) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET progress=? WHERE id=?",
                         (max(0.0, min(1.0, float(progress))), job_id))

    def append_job_log(self, job_id: int, line: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT log_tail FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise NotFound(f"job {job_id} không tồn tại")
            lines = (row["log_tail"] + "\n" + line).splitlines()[-LOG_TAIL_LINES:]
            conn.execute("UPDATE jobs SET log_tail=? WHERE id=?",
                         ("\n".join(lines), job_id))

    def request_cancel(self, job_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (job_id,))

    def mark_running_as_interrupted(self) -> int:
        """Gọi lúc khởi động. Không có nó thì worker chết giữa job sẽ để job
        treo vĩnh viễn ở `running` và giao diện hiện 'đang chạy' mãi mãi."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE jobs SET state=?, finished_at=? WHERE state=?",
                (js.INTERRUPTED, self._clock.now_iso(), js.RUNNING),
            )
            return int(cur.rowcount)

    def retry_job(self, job_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT state, attempts FROM jobs WHERE id=?",
                               (job_id,)).fetchone()
            if row is None:
                raise NotFound(f"job {job_id} không tồn tại")
            js.assert_transition(row["state"], js.QUEUED)
            conn.execute(
                "UPDATE jobs SET state=?, attempts=attempts+1, finished_at=NULL,"
                " error=NULL, progress=0 WHERE id=?",
                (js.QUEUED, job_id),
            )

    # ---------- glossary / settings / calls ----------
    def upsert_term(self, *, lang: str, term: str, translation: str,
                    note: str | None, approved: bool) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO glossary(lang, term, translation, note, approved, created_at)"
                " VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(lang, term) DO UPDATE SET translation=excluded.translation,"
                " note=excluded.note, approved=excluded.approved",
                (lang, term, translation, note, int(approved), self._clock.now_iso()),
            )
            conn.execute(
                "INSERT INTO settings(key, value) VALUES('glossary_version', '1')"
                " ON CONFLICT(key) DO UPDATE SET value=CAST(CAST(value AS INTEGER)+1 AS TEXT)"
            )
            return int(cur.lastrowid or 0)

    def list_terms(self, *, lang: str | None = None) -> list[Term]:
        sql = "SELECT * FROM glossary"
        params: tuple = ()
        if lang:
            sql += " WHERE lang=?"
            params = (lang,)
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Term(id=r["id"], lang=r["lang"], term=r["term"],
                     translation=r["translation"], note=r["note"],
                     approved=bool(r["approved"]), created_at=r["created_at"])
                for r in rows]

    def glossary_version(self) -> int:
        return int(self.get_setting("glossary_version", "0") or "0")

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def add_llm_call(self, *, job_id: int | None, engine: str, model_ref: str | None,
                     prompt_version: str | None, tokens_in: int | None,
                     tokens_out: int | None, duration_ms: int | None,
                     ok: bool, error: str | None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO llm_calls(job_id, engine, model_ref, prompt_version,"
                " tokens_in, tokens_out, duration_ms, ok, error, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (job_id, engine, model_ref, prompt_version, tokens_in, tokens_out,
                 duration_ms, int(ok), error, self._clock.now_iso()),
            )
            return int(cur.lastrowid)

    def list_llm_calls(self, job_id: int | None = None) -> list[dict]:
        sql = "SELECT * FROM llm_calls"
        params: tuple = ()
        if job_id is not None:
            sql += " WHERE job_id=?"
            params = (job_id,)
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
```

```python
# backend/app/adapters/clock_system.py
from __future__ import annotations

import datetime as _dt


class SystemClock:
    def now_iso(self) -> str:
        return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FrozenClock:
    """Cho test: thời gian đứng yên, có thể đẩy tay."""

    def __init__(self, start: str = "2026-09-25T00:00:00Z") -> None:
        self._now = start
        self._tick = 0

    def now_iso(self) -> str:
        return self._now

    def advance(self, seconds: int) -> None:
        self._tick += seconds
        base = _dt.datetime.strptime(self._now, "%Y-%m-%dT%H:%M:%SZ")
        self._now = (base + _dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
```

- [ ] **Step 5: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_repos.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS. `test_layer_boundary.py` **phải vẫn xanh** — `sqlite3` chỉ được xuất hiện trong `adapters/`, không bao giờ trong `domain/`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ports backend/app/adapters backend/tests/test_repos.py
git commit -m "feat(persist): ports + sqlite schema + repository"
```

---

## Task 8: Registry engine

**Files:**
- Create: `backend/registry.json`, `backend/app/registry.py`, `backend/app/adapters/registry_file.py`, `backend/tests/test_registry.py`

**Interfaces:**
- Consumes: `app.config.REGISTRY_PATH`
- Produces:
  - `EngineSpec(id, label, kind, runtime, model_ref, vram_mb, langs, capabilities, opts)` — dataclass **frozen**
  - `load_registry(path) -> list[EngineSpec]`
  - `by_id(specs, engine_id) -> EngineSpec` (raise `KeyError`)
  - `of_kind(specs, kind) -> list[EngineSpec]`
  - `estimate_vram_mb(specs, engine_ids: Iterable[str]) -> int`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_registry.py
from __future__ import annotations

import json

import pytest

from app.adapters.registry_file import load_registry
from app.registry import by_id, estimate_vram_mb, of_kind


@pytest.fixture()
def specs(tmp_path):
    data = {
        "asr": [
            {"id": "fw-large-v3-turbo", "label": "Faster-Whisper large-v3-turbo",
             "runtime": "inprocess", "model_ref": "large-v3-turbo", "vram_mb": 1600,
             "langs": ["zh", "en"],
             "capabilities": {"timestamps": True, "word_timestamps": True,
                              "confidence": True, "emotion": False},
             "opts": {"batch_size": 8}},
            {"id": "sensevoice-small", "label": "SenseVoice-Small",
             "runtime": "inprocess", "model_ref": "iic/SenseVoiceSmall", "vram_mb": 1000,
             "langs": ["zh", "yue", "en", "ja", "ko"],
             "capabilities": {"timestamps": True, "word_timestamps": False,
                              "confidence": False, "emotion": True},
             "opts": {}},
        ],
        "mt": [
            {"id": "qwen2.5-7b", "label": "Qwen2.5-7B", "runtime": "ollama",
             "model_ref": "qwen2.5:7b-instruct-q4_K_M", "vram_mb": 5200,
             "langs": ["zh", "en"],
             "capabilities": {"glossary_prompt": True, "chimera": False},
             "opts": {}},
        ],
    }
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_registry(p)


def test_loads_all_kinds(specs):
    assert len(specs) == 3
    assert {s.kind for s in specs} == {"asr", "mt"}


def test_of_kind_filters(specs):
    assert [s.id for s in of_kind(specs, "asr")] == ["fw-large-v3-turbo", "sensevoice-small"]


def test_by_id_returns_spec_and_raises_on_unknown(specs):
    assert by_id(specs, "sensevoice-small").vram_mb == 1000
    with pytest.raises(KeyError):
        by_id(specs, "khong-co")


def test_capabilities_and_opts_survive_json_roundtrip(specs):
    fw = by_id(specs, "fw-large-v3-turbo")
    assert fw.capabilities["word_timestamps"] is True
    assert fw.opts["batch_size"] == 8


def test_spec_is_frozen_so_a_job_cannot_mutate_shared_config(specs):
    fw = by_id(specs, "fw-large-v3-turbo")
    with pytest.raises(Exception):
        fw.vram_mb = 1  # type: ignore[misc]


def test_estimate_vram_sums_only_requested(specs):
    assert estimate_vram_mb(specs, ["fw-large-v3-turbo"]) == 1600
    assert estimate_vram_mb(specs, ["fw-large-v3-turbo", "qwen2.5-7b"]) == 6800


def test_shipped_registry_file_is_valid():
    specs = load_registry()          # dùng đường dẫn mặc định từ config
    ids = {s.id for s in specs}
    assert "fw-large-v3-turbo" in ids
    assert "sensevoice-small" in ids
    assert all(s.phase_key.startswith(("asr:", "translate:")) for s in specs)
    # SỬA SAU KHI SHIP (R28): bản đầu khẳng định ("asr:", "mt:") — không thể đỏ với giá trị
    # dựng từ `kind`. Và phải thêm test liên module: phase_key == phase_of(job_type, id)
    # với cặp (asr, asr) và (mt, translate) trên registry đã ship.
    # Moonshine KHÔNG được có mặt: nó không sinh timestamp (spec §6)
    assert not any("moonshine" in s.id.lower() for s in specs)
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_registry.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.registry'`

- [ ] **Step 3: Viết `registry.json`**

```json
{
  "_ghi_chu": "Thêm model mới = sửa file này. KHÔNG hard-code ở pipeline hay giao diện. Frontend đọc qua GET /api/registry.",
  "asr": [
    {
      "id": "fw-large-v3-turbo",
      "label": "Faster-Whisper large-v3-turbo",
      "runtime": "inprocess",
      "model_ref": "large-v3-turbo",
      "vram_mb": 1600,
      "langs": ["zh", "en"],
      "capabilities": { "timestamps": true, "word_timestamps": true, "confidence": true, "emotion": false, "batch_infer": true },
      "opts": { "batch_size": 8, "compute_type": "int8_float16" }
    },
    {
      "id": "fw-medium",
      "label": "Faster-Whisper medium",
      "runtime": "inprocess",
      "model_ref": "medium",
      "vram_mb": 1500,
      "langs": ["zh", "en"],
      "capabilities": { "timestamps": true, "word_timestamps": true, "confidence": true, "emotion": false, "batch_infer": true },
      "opts": { "batch_size": 8, "compute_type": "int8_float16" }
    },
    {
      "id": "fw-small",
      "label": "Faster-Whisper small",
      "runtime": "inprocess",
      "model_ref": "small",
      "vram_mb": 500,
      "langs": ["zh", "en"],
      "capabilities": { "timestamps": true, "word_timestamps": true, "confidence": true, "emotion": false, "batch_infer": true },
      "opts": { "batch_size": 8, "compute_type": "int8_float16" }
    },
    {
      "id": "sensevoice-small",
      "label": "SenseVoice-Small",
      "runtime": "inprocess",
      "model_ref": "iic/SenseVoiceSmall",
      "vram_mb": 1000,
      "langs": ["zh", "yue", "en", "ja", "ko"],
      "capabilities": { "timestamps": true, "word_timestamps": false, "confidence": false, "emotion": true, "batch_infer": false },
      "opts": { "use_itn": true }
    }
  ],
  "mt": [
    {
      "id": "opus-mt",
      "label": "OPUS-MT (Marian)",
      "runtime": "inprocess",
      "model_ref": "Helsinki-NLP/opus-mt-zh-vi",
      "vram_mb": 0,
      "langs": ["zh", "en"],
      "capabilities": { "glossary_prompt": false, "glossary_patch": false, "chimera": false, "batch_json": false },
      "opts": {}
    },
    {
      "id": "qwen2.5-3b",
      "label": "Qwen2.5-3B (Ollama)",
      "runtime": "ollama",
      "model_ref": "qwen2.5:3b-instruct-q4_K_M",
      "vram_mb": 2500,
      "langs": ["zh", "en"],
      "capabilities": { "glossary_prompt": true, "glossary_patch": false, "chimera": false, "batch_json": true },
      "opts": {}
    },
    {
      "id": "qwen2.5-7b",
      "label": "Qwen2.5-7B (Ollama)",
      "runtime": "ollama",
      "model_ref": "qwen2.5:7b-instruct-q4_K_M",
      "vram_mb": 5200,
      "langs": ["zh", "en"],
      "capabilities": { "glossary_prompt": true, "glossary_patch": false, "chimera": false, "batch_json": true },
      "opts": {}
    },
    {
      "id": "hy-mt-1.5-7b",
      "label": "HY-MT1.5-7B (Hunyuan-MT)",
      "runtime": "ollama",
      "model_ref": "hy-mt1.5-7b:q4_K_M",
      "vram_mb": 5200,
      "langs": ["zh", "en"],
      "capabilities": { "glossary_prompt": false, "glossary_patch": true, "chimera": true, "batch_json": true },
      "opts": {}
    }
  ]
}
```

- [ ] **Step 4: Viết loader + kiểu dữ liệu**

```python
# backend/app/registry.py
"""Kiểu dữ liệu của registry và các phép tra cứu. Thuần, không đọc tệp.

Việc đọc tệp nằm ở adapters/registry_file.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class EngineSpec:
    id: str
    label: str
    kind: str            # 'asr' | 'mt'
    runtime: str         # 'inprocess' | 'ollama'
    model_ref: str
    vram_mb: int
    langs: tuple[str, ...]
    capabilities: dict = field(default_factory=dict)
    opts: dict = field(default_factory=dict)

    @property
    def phase_key(self) -> str:
        """Khoá giai đoạn của hàng đợi. Phải khớp `job_state.phase_of`.

        SỬA SAU KHI SHIP (R28). Bản đầu trả `f"{self.kind}:{self.id}"` ⇒ `mt:qwen2.5-7b`,
        nhưng loại job dịch là `translate` nên khoá mà `jobs.phase` lưu là
        `translate:qwen2.5-7b` — LỆCH cả 4 engine MT (ASR thì khớp, nên trông như đúng).
        Uỷ quyền cho `phase_of` để hai bên không thể trôi khỏi nhau lần nữa.
        Cần ở đầu module: `from app.domain.job_state import phase_of` (job_state không
        import gì ⇒ không có vòng; guard chỉ ràng buộc `app/domain/**`) và
        `_JOB_TYPE_OF_KIND = {"asr": "asr", "mt": "translate"}`.
        """
        return phase_of(_JOB_TYPE_OF_KIND[self.kind], self.id)


def of_kind(specs: Iterable[EngineSpec], kind: str) -> list[EngineSpec]:
    return [s for s in specs if s.kind == kind]


def by_id(specs: Iterable[EngineSpec], engine_id: str) -> EngineSpec:
    for spec in specs:
        if spec.id == engine_id:
            return spec
    raise KeyError(f"engine {engine_id!r} không có trong registry")


def estimate_vram_mb(specs: Iterable[EngineSpec], engine_ids: Iterable[str]) -> int:
    specs = list(specs)
    return sum(by_id(specs, eid).vram_mb for eid in engine_ids)
```

```python
# backend/app/adapters/registry_file.py
from __future__ import annotations

import json
import pathlib

from app.config import REGISTRY_PATH
from app.registry import EngineSpec

_KINDS = ("asr", "mt")


def load_registry(path: str | pathlib.Path | None = None) -> list[EngineSpec]:
    p = pathlib.Path(path) if path is not None else REGISTRY_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    specs: list[EngineSpec] = []
    for kind in _KINDS:
        for entry in raw.get(kind, []):
            specs.append(EngineSpec(
                id=entry["id"],
                label=entry.get("label", entry["id"]),
                kind=kind,
                runtime=entry["runtime"],
                model_ref=entry["model_ref"],
                vram_mb=int(entry.get("vram_mb", 0)),
                langs=tuple(entry.get("langs", ())),
                capabilities=dict(entry.get("capabilities", {})),
                opts=dict(entry.get("opts", {})),
            ))
    return specs
```

- [ ] **Step 5: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_registry.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/registry.json backend/app/registry.py backend/app/adapters/registry_file.py backend/tests/test_registry.py
git commit -m "feat(registry): khai bao engine + loader"
```

---

## Task 9: Hàng đợi theo giai đoạn — trái tim của hệ thống

**Files:**
- Create: `backend/app/adapters/governor/__init__.py`, `backend/app/adapters/governor/single_gpu.py`, `backend/app/worker.py`, `backend/tests/fakes.py`, `backend/tests/test_worker_phases.py`

**Interfaces:**
- Consumes: `Repos`, `ResourceGovernor`, `app.domain.job_state`
- Produces:
  - `JobHandler` Protocol: `handles() -> str` (loại job) · `run(job: Job, report: Callable[[float, str], None]) -> None`
  - `PhaseQueueWorker(repos, governor, handlers, *, poll_interval=0.05, sleeper=time.sleep)`
  - `worker.recover() -> int` · `worker.tick() -> bool` · `worker.run_forever(stop_event)`
  - `worker.current_phase: str | None` (đọc được, cho `/api/status` và test)
  - `worker.phase_switches: int` (đếm số lần đổi giai đoạn — dùng cho test và cho benchmark)
  - `SingleGpuGovernor(repos)`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/fakes.py
"""Đối tượng giả cho test. KHÔNG nạp model nào, KHÔNG chạm GPU."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable

from app.domain.models import Job, Segment


class FakeClock:
    def __init__(self, start: str = "2026-09-25T00:00:00Z") -> None:
        self._counter = itertools.count()
        self._start = start

    def now_iso(self) -> str:
        n = next(self._counter)
        return f"2026-09-25T00:00:{n:02d}Z"


class FakeGovernor:
    """Ghi lại mọi lần nạp/đổ model để test đếm được số lần swap."""

    def __init__(self) -> None:
        self.before: list[str] = []
        self.after: list[str] = []

    def before_phase(self, phase: str) -> None:
        self.before.append(phase)

    def after_phase(self, phase: str) -> None:
        self.after.append(phase)

    def can_run_parallel(self, a_vram_mb: int, b_vram_mb: int) -> bool:
        return False


@dataclass
class RecordingHandler:
    """Handler giả: ghi lại thứ tự job đã chạy, có thể cấu hình để hỏng."""

    job_type: str
    fail_on: set[int] = field(default_factory=set)
    ran: list[int] = field(default_factory=list)
    cancel_after: int | None = None
    _repos: object | None = None
    _job_id_to_cancel: int | None = None

    def handles(self) -> str:
        return self.job_type

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        assert job.id is not None
        self.ran.append(job.id)
        report(0.5, f"chạy job {job.id}")
        if job.id in self.fail_on:
            raise RuntimeError(f"job {job.id} hỏng theo kịch bản test")
        if self.cancel_after is not None and len(self.ran) >= self.cancel_after:
            if self._repos is not None and self._job_id_to_cancel is not None:
                self._repos.request_cancel(self._job_id_to_cancel)
        report(1.0, "xong")


def a_job(job_id_ignored: int | None, *, job_type: str, engine: str,
          workspace: int = 1) -> Job:
    from app.domain.job_state import phase_of
    return Job(id=None, workspace=workspace, type=job_type, engine=engine,
               phase=phase_of(job_type, engine), payload={})
```

```python
# backend/tests/test_worker_phases.py
from __future__ import annotations

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.governor.single_gpu import SingleGpuGovernor
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.worker import PhaseQueueWorker
from tests.fakes import FakeGovernor, RecordingHandler, a_job


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def _worker(repos, governor, *handlers):
    return PhaseQueueWorker(repos, governor, {h.handles(): h for h in handlers})


def test_two_files_two_engines_cause_exactly_two_phase_switches(repos):
    """Đây là toàn bộ lý do tồn tại của hàng đợi theo giai đoạn.

    Thứ tự thêm: asr:fw ... , asr:fw ... , asr:sv ... , asr:sv ...
    Nếu chạy FIFO thuần thì mỗi job là một lần nạp/đổ model (4 lần).
    Gom theo giai đoạn thì chỉ 2 lần.
    """
    gov = FakeGovernor()
    fw = RecordingHandler(job_type="asr")
    worker = _worker(repos, gov, fw)

    for engine in ("fw-large-v3-turbo", "fw-large-v3-turbo",
                   "sensevoice-small", "sensevoice-small"):
        repos.add_job(a_job(None, job_type="asr", engine=engine))

    while worker.tick():
        pass

    assert len(fw.ran) == 4
    assert worker.phase_switches == 2, (
        f"phải là 2 lần đổi giai đoạn, thực tế {worker.phase_switches}"
    )
    assert gov.before == ["asr:fw-large-v3-turbo", "asr:sensevoice-small"]
    assert gov.after == ["asr:fw-large-v3-turbo", "asr:sensevoice-small"]


def test_interleaved_engines_still_group(repos):
    gov = FakeGovernor()
    fw = RecordingHandler(job_type="asr")
    worker = _worker(repos, gov, fw)
    for engine in ("fw-large-v3-turbo", "sensevoice-small", "fw-large-v3-turbo"):
        repos.add_job(a_job(None, job_type="asr", engine=engine))

    while worker.tick():
        pass

    # job đầu là fw -> chạy fw; còn lại sensevoice + fw. Giai đoạn kế của job cũ
    # nhất còn chờ là sensevoice -> chạy nó; rồi tới fw.
    assert worker.phase_switches == 3
    assert fw.ran == [1, 2, 3]


def test_current_phase_is_none_when_queue_drains(repos):
    gov = FakeGovernor()
    worker = _worker(repos, gov, RecordingHandler(job_type="asr"))
    repos.add_job(a_job(None, job_type="asr", engine="e"))
    assert worker.tick() is True
    assert worker.current_phase == "asr:e"
    assert worker.tick() is False
    assert worker.current_phase is None, "hết việc thì phải nhả giai đoạn để lần sau chọn lại"


def test_failing_job_does_not_stop_the_queue(repos):
    gov = FakeGovernor()
    handler = RecordingHandler(job_type="asr", fail_on={2})
    worker = _worker(repos, gov, handler)
    for _ in range(3):
        repos.add_job(a_job(None, job_type="asr", engine="e"))

    while worker.tick():
        pass

    assert handler.ran == [1, 2, 3]
    assert repos.get_job(2).state == js.FAILED
    assert "hỏng theo kịch bản test" in (repos.get_job(2).error or "")
    assert repos.get_job(1).state == js.DONE
    assert repos.get_job(3).state == js.DONE


def test_job_of_another_type_is_deferred_not_starved(repos):
    """Job loại khác phải được chạy sau khi giai đoạn hiện tại hết việc,
    không được bỏ quên."""
    gov = FakeGovernor()
    asr = RecordingHandler(job_type="asr")
    mt = RecordingHandler(job_type="translate")
    worker = _worker(repos, gov, asr, mt)
    repos.add_job(a_job(None, job_type="translate", engine="qwen2.5-7b", workspace=2))
    repos.add_job(a_job(None, job_type="asr", engine="fw-large-v3-turbo"))

    while worker.tick():
        pass

    assert mt.ran == [1]
    assert asr.ran == [2]


def test_progress_and_log_are_written(repos):
    gov = FakeGovernor()
    worker = _worker(repos, gov, RecordingHandler(job_type="asr"))
    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    worker.tick()
    job = repos.get_job(jid)
    assert job.progress == 1.0
    assert "chạy job" in job.log_tail and "xong" in job.log_tail


def test_unknown_job_type_does_not_crash_the_worker(repos):
    gov = FakeGovernor()
    worker = _worker(repos, gov, RecordingHandler(job_type="asr"))
    jid = repos.add_job(a_job(None, job_type="export", engine=None))
    while worker.tick():
        pass
    job = repos.get_job(jid)
    assert job.state == js.FAILED
    assert "không có handler" in (job.error or "")


def test_single_gpu_governor_never_allows_parallel_in_phase_1a(tmp_path):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    gov = SingleGpuGovernor(repos)
    assert gov.can_run_parallel(1600, 5200) is False
    assert gov.can_run_parallel(100, 100) is False
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_worker_phases.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.worker'`

- [ ] **Step 3: Viết governor + worker**

```python
# backend/app/adapters/governor/single_gpu.py
from __future__ import annotations

from app.ports.repos import Repos


class SingleGpuGovernor:
    """Điều phối VRAM cho một GPU.

    GĐ1a chỉ có ASR chạy in-process và hàng đợi vốn đã tuần tự, nên việc thật
    sự cần làm là: khi rời một giai đoạn thì đảm bảo model của giai đoạn đó
    được giải phóng. Việc đổ model Ollama (keep_alive: 0) là của GĐ2.
    """

    def __init__(self, repos: Repos) -> None:
        self._repos = repos
        self._loaded: dict[str, object] = {}

    def register(self, phase: str, releaser) -> None:
        self._loaded[phase] = releaser

    def before_phase(self, phase: str) -> None:
        for other, releaser in list(self._loaded.items()):
            if other != phase:
                releaser()
                self._loaded.pop(other, None)

    def after_phase(self, phase: str) -> None:
        releaser = self._loaded.pop(phase, None)
        if releaser is not None:
            releaser()

    def can_run_parallel(self, a_vram_mb: int, b_vram_mb: int) -> bool:
        # Chế độ song song là GĐ3 và mặc định tắt. Trả False là hành vi thật,
        # không phải chỗ trống chờ điền.
        return False
```

```python
# backend/app/worker.py
"""Hàng đợi một luồng, gom lô theo GIAI ĐOẠN.

Giai đoạn = cặp (loại job, engine). Chạy hết job của giai đoạn hiện tại rồi mới
đổi giai đoạn, nên số lần nạp/đổ model là O(số giai đoạn) thay vì O(số job).
Nạp qwen2.5-7B Q4 mất 5-15s, nên với video ngắn đây là 20-40% tổng thời gian.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Protocol

from app.domain import job_state as js
from app.domain.models import Job
from app.ports.governor import ResourceGovernor
from app.ports.repos import Repos


class JobHandler(Protocol):
    def handles(self) -> str:
        """Loại job mà handler này nhận: 'ingest' | 'asr' | 'translate' | 'export'."""
        ...

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        ...


class PhaseQueueWorker:
    def __init__(
        self,
        repos: Repos,
        governor: ResourceGovernor,
        handlers: dict[str, JobHandler],
        *,
        poll_interval: float = 0.05,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repos = repos
        self.governor = governor
        self.handlers = handlers
        self.poll_interval = poll_interval
        self._sleep = sleeper
        self.current_phase: str | None = None
        self.phase_switches = 0
        self._stop = threading.Event()

    # ---------- vòng đời ----------
    def recover(self) -> int:
        """Gọi MỘT LẦN lúc khởi động, trước run_forever."""
        return self.repos.mark_running_as_interrupted()

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            if not self.tick():
                self._sleep(self.poll_interval)

    # ---------- một nhịp ----------
    def tick(self) -> bool:
        """Chạy đúng một job. Trả về True nếu có job được chạy."""
        if self.current_phase is None:
            nxt = self.repos.oldest_queued()
            if nxt is None:
                return False
            self._enter_phase(nxt.phase)

        job = self.repos.next_queued_for_phase(self.current_phase)
        if job is None:
            self._leave_phase()
            return False

        self._run_one(job)
        return True

    def _enter_phase(self, phase: str) -> None:
        self.current_phase = phase
        self.phase_switches += 1
        self.governor.before_phase(phase)

    def _leave_phase(self) -> None:
        if self.current_phase is not None:
            self.governor.after_phase(self.current_phase)
        self.current_phase = None

    # ---------- chạy job ----------
    def _run_one(self, job: Job) -> None:
        assert job.id is not None
        handler = self.handlers.get(job.type)

        self.repos.set_job_state(job.id, js.RUNNING)

        if handler is None:
            self.repos.append_job_log(job.id, f"không có handler cho loại {job.type!r}")
            self.repos.set_job_state(
                job.id, js.FAILED, error=f"không có handler cho loại job {job.type!r}"
            )
            return

        def report(progress: float, line: str) -> None:
            self.repos.set_job_progress(job.id, progress)
            self.repos.append_job_log(job.id, line)

        try:
            handler.run(job, report)
        except Exception as exc:  # noqa: BLE001 - phải bắt hết để hàng đợi sống
            self.repos.append_job_log(job.id, f"LỖI: {exc}")
            self.repos.set_job_state(job.id, js.FAILED, error=f"{type(exc).__name__}: {exc}")
            return

        # Kiểm tra yêu cầu huỷ ở RANH GIỚI job. Không có đường nào kill tiến trình.
        fresh = self.repos.get_job(job.id)
        if fresh.cancel_requested:
            self.repos.append_job_log(job.id, "đã huỷ theo yêu cầu")
            self.repos.set_job_state(job.id, js.CANCELLED)
            return

        self.repos.set_job_progress(job.id, 1.0)
        self.repos.set_job_state(job.id, js.DONE)
```

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_worker_phases.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS. Nếu `test_two_files_two_engines_cause_exactly_two_phase_switches` đỏ với 3 hoặc 4 lần đổi, nghĩa là `_leave_phase` bị gọi quá sớm — `tick()` chỉ được nhả giai đoạn khi **không còn job nào** của giai đoạn đó.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/governor backend/app/worker.py backend/tests/fakes.py backend/tests/test_worker_phases.py
git commit -m "feat(worker): hang doi gom lo theo giai đoạn (cap loai-job, engine)"
```

---

## Task 10: Phục hồi sau crash + huỷ hợp tác giữa job dài

**Files:**
- Modify: `backend/app/worker.py` (thêm kiểm tra huỷ giữa các bước, dùng `checkpoint()`)
- Create: `backend/tests/test_worker_recovery.py`, `backend/tests/test_worker_cancel.py`

**Interfaces:**
- Consumes: `PhaseQueueWorker`, `Repos`
- Produces:
  - `JobCancelled` exception trong `app.worker`
  - `PhaseQueueWorker.checkpoint(job_id: int) -> None` — handler gọi giữa các bước; raise `JobCancelled` nếu có yêu cầu huỷ. Worker bắt lấy và chuyển job sang `cancelled`.
  - `RecordingHandler` trong `tests/fakes.py` được mở rộng để gọi `checkpoint`.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_worker_recovery.py
from __future__ import annotations

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.worker import PhaseQueueWorker
from tests.fakes import FakeGovernor, RecordingHandler, a_job


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def _worker(repos, *handlers):
    return PhaseQueueWorker(repos, FakeGovernor(), {h.handles(): h for h in handlers})


def test_recover_marks_orphan_running_jobs_as_interrupted(repos):
    """Mô phỏng: worker bị kill giữa lúc đang chạy job. Không có bước này thì
    job treo vĩnh viễn ở `running` và giao diện hiện 'đang chạy' mãi mãi."""
    a = repos.add_job(a_job(None, job_type="asr", engine="e"))
    b = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.set_job_state(a, js.RUNNING)      # worker chết ở đây
    worker = _worker(repos, RecordingHandler(job_type="asr"))

    assert worker.recover() == 1

    assert repos.get_job(a).state == js.INTERRUPTED
    assert repos.get_job(a).finished_at is not None
    assert repos.get_job(b).state == js.QUEUED


def test_recover_is_idempotent(repos):
    a = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.set_job_state(a, js.RUNNING)
    worker = _worker(repos, RecordingHandler(job_type="asr"))
    assert worker.recover() == 1
    assert worker.recover() == 0


def test_retried_job_runs_again_after_recovery(repos):
    a = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.set_job_state(a, js.RUNNING)
    handler = RecordingHandler(job_type="asr")
    worker = _worker(repos, handler)

    worker.recover()
    repos.retry_job(a)
    while worker.tick():
        pass

    assert handler.ran == [a]
    assert repos.get_job(a).state == js.DONE
    assert repos.get_job(a).attempts == 1
```

```python
# backend/tests/test_worker_cancel.py
from __future__ import annotations

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.worker import JobCancelled, PhaseQueueWorker
from tests.fakes import FakeGovernor, a_job


class CheckpointingHandler:
    """Handler gọi checkpoint giữa các bước, giống handler thật sẽ làm."""

    def __init__(self, worker_ref: list) -> None:
        self._worker_ref = worker_ref
        self.steps_done = 0

    def handles(self) -> str:
        return "asr"

    def run(self, job, report) -> None:
        worker = self._worker_ref[0]
        for step in range(5):
            worker.checkpoint(job.id)
            self.steps_done += 1
            report(step / 5, f"bước {step}")


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def test_cancel_between_steps_stops_early_and_marks_cancelled(repos):
    ref: list = []
    handler = CheckpointingHandler(ref)
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": handler})
    ref.append(worker)

    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.request_cancel(jid)          # huỷ TRƯỚC khi chạy

    while worker.tick():
        pass

    assert handler.steps_done == 0, "checkpoint đầu tiên phải chặn ngay, không chạy bước nào"
    assert repos.get_job(jid).state == js.CANCELLED


def test_cancel_midway_only_runs_started_steps(repos):
    ref: list = []
    handler = CheckpointingHandler(ref)
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": handler})
    ref.append(worker)

    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    # huỷ sau bước đầu: dùng clock? đơn giản hơn — huỷ ngay sau checkpoint 1
    original_checkpoint = worker.checkpoint
    calls = {"n": 0}

    def counting_checkpoint(job_id: int) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            repos.request_cancel(job_id)
        original_checkpoint(job_id)

    worker.checkpoint = counting_checkpoint  # type: ignore[assignment]

    while worker.tick():
        pass

    assert handler.steps_done == 1
    assert repos.get_job(jid).state == js.CANCELLED


def test_cancelled_job_does_not_run_again(repos):
    ref: list = []
    handler = CheckpointingHandler(ref)
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": handler})
    ref.append(worker)

    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.request_cancel(jid)
    while worker.tick():
        pass

    assert worker.tick() is False
    assert repos.get_job(jid).state == js.CANCELLED


def test_cancel_requested_flag_stays_but_state_is_terminal(repos):
    ref: list = []
    worker = PhaseQueueWorker(repos, FakeGovernor(), {"asr": CheckpointingHandler(ref)})
    ref.append(worker)
    jid = repos.add_job(a_job(None, job_type="asr", engine="e"))
    repos.request_cancel(jid)
    while worker.tick():
        pass
    job = repos.get_job(jid)
    assert job.state == js.CANCELLED
    assert job.cancel_requested is True
    assert job.finished_at is not None
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_worker_recovery.py tests/test_worker_cancel.py -v`

Expected: `test_worker_recovery.py` PASS (đã có `recover()` từ Task 9), `test_worker_cancel.py` FAIL — `ImportError: cannot import name 'JobCancelled'`.

- [ ] **Step 3: Thêm `checkpoint` và `JobCancelled` vào worker**

Chèn vào `backend/app/worker.py`, ngay trên `class PhaseQueueWorker`:

```python
class JobCancelled(Exception):
    """Handler ném ra từ checkpoint() khi có yêu cầu huỷ."""
```

Thêm phương thức vào `PhaseQueueWorker` (đặt cạnh `_run_one`):

```python
    def checkpoint(self, job_id: int) -> None:
        """Handler gọi giữa các bước. Đây là cách duy nhất để huỷ một job dài.

        Không kill tiến trình: nếu kill, DB có thể nằm ở trạng thái nửa vời và
        model đang nạp dở sẽ không được giải phóng.
        """
        if self.repos.get_job(job_id).cancel_requested:
            raise JobCancelled(f"job {job_id} đã được yêu cầu huỷ")
```

Và sửa khối `try/except` trong `_run_one` để bắt `JobCancelled` **trước** `Exception`:

```python
        try:
            handler.run(job, report)
        except JobCancelled:
            self.repos.append_job_log(job.id, "đã huỷ theo yêu cầu ở checkpoint")
            self.repos.set_job_state(job.id, js.CANCELLED)
            return
        except Exception as exc:  # noqa: BLE001
            self.repos.append_job_log(job.id, f"LỖI: {exc}")
            self.repos.set_job_state(job.id, js.FAILED, error=f"{type(exc).__name__}: {exc}")
            return
```

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_worker_recovery.py tests/test_worker_cancel.py tests/test_worker_phases.py -v`

Expected: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/worker.py backend/tests/test_worker_recovery.py backend/tests/test_worker_cancel.py
git commit -m "feat(worker): phuc hoi sau crash + huy hop tac qua checkpoint"
```

---

## Task 11: Ingest — ffprobe, ffmpeg, yt-dlp

**Files:**
- Create: `backend/app/pipeline/__init__.py`, `backend/app/pipeline/ingest.py`, `backend/tests/test_ingest.py`

**Interfaces:**
- Consumes: `app.config`
- Produces:
  - `sha256_file(path) -> str`
  - `probe_duration(path) -> float`
  - `extract_audio(media_path, out_dir, *, stem) -> tuple[Path, float]` — trả `(wav_path, duration)`
  - `download_url(url, out_dir, *, on_progress=None) -> Path`
  - `AUDIO_SAMPLE_RATE = 16000`

> **ĐÍNH CHÍNH (R48 = DOC-01, R53 = DOC-03).** Khối Interfaces bản đầu còn một dòng
> `IngestHandler(repos, clock)` với `handles() -> "ingest"`. Dòng đó **sai ở hai tầng** và đã bị bỏ:
> (a) `IngestHandler` **không thuộc Task 11** — nó được thêm ở **Task 15** (mục
> *"## Task 15: FastAPI app + route sources & registry"*, đoạn `Thêm \`IngestHandler\` vào
> \`backend/app/pipeline/ingest.py\``), nên đây là
> một phép chiếu tới task sau bị viết như đặc tả của task hiện tại; và (b) chữ ký nêu ra cũng sai:
> chữ ký **đã ship** là
> `IngestHandler(repos, *, audio_dir=None, media_root=None, specs=None, declared_default_asr=None)`
> (`IngestHandler.__init__` trong `backend/app/pipeline/ingest.py`) — **không** có tham số `clock`, và ba tham số từ khoá cuối
> chỉ `app/main.py` truyền (I-3, I-6). DOC-03 ("R53 = thông tin", ledger ghi *không làm gì*) tự đóng
> kèm DOC-01: cùng một dòng, cùng một edit.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_ingest.py
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from app.pipeline import ingest


def _have(binary: str) -> bool:
    return shutil.which(binary) is not None


pytestmark = pytest.mark.skipif(
    not (_have("ffmpeg") and _have("ffprobe")),
    reason="cần ffmpeg/ffprobe trên PATH",
)


@pytest.fixture()
def tone_wav(tmp_path):
    """Sinh một tệp wav 3 giây bằng ffmpeg — không cần tài nguyên ngoài."""
    out = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(out)],
        check=True,
    )
    return out


def test_sha256_is_stable_and_distinguishes_files(tone_wav, tmp_path):
    other = tmp_path / "other.wav"
    shutil.copy(tone_wav, other)
    assert ingest.sha256_file(tone_wav) == ingest.sha256_file(other)
    assert len(ingest.sha256_file(tone_wav)) == 64


def test_probe_duration_reads_real_duration(tone_wav):
    assert 2.8 < ingest.probe_duration(tone_wav) < 3.2


def test_extract_audio_produces_mono_16k_wav(tone_wav, tmp_path):
    wav, duration = ingest.extract_audio(tone_wav, tmp_path, stem="abc")
    assert wav.exists()
    assert wav.name == "abc.wav"
    assert 2.8 < duration < 3.2

    # Đọc theo TÊN trường, không theo thứ tự: ffprobe 8.1.1 luôn xuất
    # sample_rate TRƯỚC channels (`16000,1`) bất kể thứ tự liệt kê trong
    # -show_entries, nên khẳng định vị trí `startswith("1,")` là sai.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=channels,sample_rate", "-of", "json", str(wav)],
        capture_output=True, text=True, check=True,
    ).stdout
    stream = json.loads(probe)["streams"][0]
    assert stream["channels"] == 1, f"phải là mono, nhận được {stream['channels']!r}"
    assert ingest.AUDIO_SAMPLE_RATE == 16000
    assert int(stream["sample_rate"]) == 16000, (
        f"phải là 16kHz, nhận được {stream['sample_rate']!r}"
    )


def test_extract_audio_is_idempotent(tone_wav, tmp_path):
    first, _ = ingest.extract_audio(tone_wav, tmp_path, stem="abc")
    stamp = first.stat().st_mtime_ns
    again, _ = ingest.extract_audio(tone_wav, tmp_path, stem="abc")
    assert again == first
    assert again.stat().st_mtime_ns == stamp, "chạy lại không được extract lại"


def test_probe_duration_on_garbage_raises_a_clear_error(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"khong phai video")
    with pytest.raises(ingest.IngestError):
        ingest.probe_duration(bad)


def test_download_url_rejects_non_http_scheme(tmp_path):
    with pytest.raises(ingest.IngestError):
        ingest.download_url("file:///etc/passwd", tmp_path)


def test_download_url_uses_injected_runner(tmp_path):
    """Không gọi mạng trong test: bơm runner giả để kiểm tra hợp đồng."""
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str], on_progress) -> str:
        calls.append(cmd)
        produced = tmp_path / "video.mp4"
        produced.write_bytes(b"x")
        if on_progress:
            on_progress({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
            on_progress({"status": "finished", "filename": str(produced)})
        return str(produced)

    seen: list[float] = []
    path = ingest.download_url("https://example.com/v", tmp_path,
                               on_progress=seen.append, runner=fake_runner)
    assert path == tmp_path / "video.mp4"
    assert seen == [0.5, 1.0]
    assert "yt-dlp" in calls[0][0] or "yt_dlp" in calls[0][0]
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ingest.py -v`

> **ĐÍNH CHÍNH (R49 = DOC-02).** Hai assertion bản đầu — `assert probe.startswith("1,")` và
> `assert ",16000" in probe` trên `-of csv=p=0` — **không thể xanh** trên máy này: ffprobe **8.1.1**
> xuất cột theo thứ tự ĐĂNG KÝ TRƯỜNG của chính binary (`16000,1`), không theo thứ tự yêu cầu trong
> `-show_entries` (đảo thứ tự yêu cầu **không** đổi thứ tự CSV; yêu cầu `channels,codec_name` cũng
> trả `pcm_s16le,1`). Bản sửa **đã ship** trong `backend/tests/test_ingest.py:63-76` dùng `-of json`
> rồi đọc trường có tên, và khối test phía trên đã được đồng bộ với nó. Đây là **đồng bộ văn bản**,
> không phải một bản sửa test mới.

Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipeline'`

- [ ] **Step 3: Viết implementation**

```python
# backend/app/pipeline/ingest.py
"""Nạp liệu: tệp tải lên hoặc link online -> wav 16k mono.

Toàn bộ phần chạm ffmpeg/yt-dlp nằm ở đây. `runner` được bơm vào để test không
cần mạng và không cần tệp thật.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
from typing import Callable, Protocol


class IngestError(RuntimeError):
    pass


AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
_CHUNK = 1024 * 1024


class ProgressCallback(Protocol):
    def __call__(self, fraction: float) -> None: ...


def sha256_file(path: str | pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise IngestError(f"không tìm thấy chương trình: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise IngestError(
            f"{cmd[0]} thất bại (mã {exc.returncode}): {(exc.stderr or '').strip()[:400]}"
        ) from exc


def probe_duration(path: str | pathlib.Path) -> float:
    result = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(path),
    ])
    try:
        payload = json.loads(result.stdout)
        return float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IngestError(f"không đọc được thời lượng của {path}") from exc


def extract_audio(
    media_path: str | pathlib.Path,
    out_dir: str | pathlib.Path,
    *,
    stem: str | None = None,
) -> tuple[pathlib.Path, float]:
    """ffmpeg -> wav 16k mono. Idempotent: đã có thì không làm lại."""
    media_path = pathlib.Path(media_path)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or media_path.stem
    target = out_dir / f"{stem}.wav"

    if target.exists() and target.stat().st_size > 0:
        return target, probe_duration(target)

    duration = probe_duration(media_path)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(media_path),
        "-vn",
        "-ac", str(AUDIO_CHANNELS),
        "-ar", str(AUDIO_SAMPLE_RATE),
        "-c:a", "pcm_s16le",
        str(target),
    ])
    if not target.exists() or target.stat().st_size == 0:
        raise IngestError(f"ffmpeg không tạo được {target}")
    return target, duration


def download_url(
    url: str,
    out_dir: str | pathlib.Path,
    *,
    on_progress: Callable[[float], None] | None = None,
    runner: Callable[[list[str], Callable[[dict], None] | None], str] | None = None,
) -> pathlib.Path:
    if not (url.startswith("http://") or url.startswith("https://")):
        raise IngestError(f"chỉ nhận http/https, không nhận {url.split(':', 1)[0]!r}")

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def _hook(payload: dict) -> None:
        if on_progress is None:
            return
        total = payload.get("total_bytes") or payload.get("total_bytes_estimate")
        done = payload.get("downloaded_bytes")
        if total and done:
            on_progress(min(1.0, done / total))
        elif payload.get("status") == "finished":
            on_progress(1.0)

    if runner is not None:
        return pathlib.Path(runner(_ytdlp_cmd(url, out_dir), _hook if on_progress else None))

    import yt_dlp  # import trễ: chỉ cần khi thật sự tải

    def _download(cmd: list[str], hook) -> str:
        opts = {
            "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "noprogress": True,
            "noplaylist": True,
            "format": "bv*+ba/b",
            "merge_output_format": "mp4",
            "progress_hooks": [hook] if hook else [],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return str(ydl.prepare_filename(info))

    return pathlib.Path(_download(_ytdlp_cmd(url, out_dir), _hook if on_progress else None))


def _ytdlp_cmd(url: str, out_dir: pathlib.Path) -> list[str]:
    return ["yt-dlp", "--no-playlist", "-o", str(out_dir / "%(id)s.%(ext)s"), url]


def find_local_media(directory: str | pathlib.Path, stem: str) -> pathlib.Path | None:
    directory = pathlib.Path(directory)
    for candidate in directory.glob(f"{stem}.*"):
        if candidate.suffix.lower() not in {".wav", ".part", ".ytdl"}:
            return candidate
    return None


def free_space_gb(path: str | pathlib.Path) -> float:
    usage = shutil.disk_usage(str(path))
    return usage.free / (1024 ** 3)
```

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ingest.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS (hoặc skip nếu thiếu ffmpeg — nhưng máy đích đã có ffmpeg nên phải chạy thật).

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/__init__.py backend/app/pipeline/ingest.py backend/tests/test_ingest.py
git commit -m "feat(ingest): ffprobe/ffmpeg/yt-dlp -> wav 16k mono"
```

---

## Task 12: Adapter Faster-Whisper + handler ASR

**Files:**
- Create: `backend/app/adapters/asr/__init__.py`, `backend/app/adapters/asr/faster_whisper.py`, `backend/app/pipeline/transcribe.py`, `backend/tests/test_transcribe_pipeline.py`

**Interfaces:**
- Consumes: `EngineSpec`, `ASREngine` protocol, `Repos`, `normalize`
- Produces:
  - `FasterWhisperEngine(spec, *, device="cuda", download_root=None, model_factory=None)`
  - `to_segments(raw_segments: list[dict]) -> list[Segment]` — hàm thuần, test không cần model
  - `EngineFactory` protocol: `__call__(spec: EngineSpec) -> ASREngine`
  - `TranscribeHandler(repos, registry, engine_factory, workdir)` với `handles() -> "asr"`
  - `TranscribeHandler.run` tạo transcript, đặt `source.audio_path`, và nếu `settings.auto_forward` bật thì thêm một job `translate` ở workspace 2

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_transcribe_pipeline.py
from __future__ import annotations

import pytest

from app.adapters.asr.faster_whisper import to_segments
from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.domain.models import Job, Segment, Source
from app.pipeline.transcribe import TranscribeHandler


def test_to_segments_maps_confidence_and_marks_suspect():
    raw = [
        {"start": 0.0, "end": 2.0, "text": " 你好 ", "avg_logprob": -0.3,
         "no_speech_prob": 0.02, "words": [{"word": "你好", "start": 0.0, "end": 2.0}]},
        {"start": 2.0, "end": 4.0, "text": "感谢观看", "avg_logprob": -2.5,
         "no_speech_prob": 0.8, "words": []},
    ]
    segs = to_segments(raw)
    assert segs[0].text == "你好"
    assert segs[0].avg_logprob == -0.3
    assert segs[0].no_speech_prob == 0.02
    assert segs[0].suspect is False
    assert segs[0].words[0].w == "你好"
    assert segs[1].suspect is True, "no_speech_prob 0.8 phải bị đánh dấu nghi ngờ"
    assert segs[1].words is None, "không có word timestamp thì phải là None, không phải []"


def test_to_segments_marks_suspect_on_low_logprob():
    segs = to_segments([{"start": 0.0, "end": 1.0, "text": "x",
                         "avg_logprob": -1.5, "no_speech_prob": 0.01}])
    assert segs[0].suspect is True


class FakeEngine:
    def __init__(self, spec) -> None:
        self.engine_id = spec.id
        self.calls: list[tuple[str, str]] = []
        self.released = 0

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        self.calls.append((audio_path, lang))
        return [Segment(i=0, start=0.0, end=2.0, text="你好"),
                Segment(i=1, start=2.0, end=4.0, text="世界")]

    def release(self) -> None:
        self.released += 1


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


@pytest.fixture()
def specs():
    from app.registry import EngineSpec
    return [EngineSpec(id="fw-large-v3-turbo", label="FW", kind="asr",
                       runtime="inprocess", model_ref="large-v3-turbo", vram_mb=1600,
                       langs=("zh", "en"), capabilities={}, opts={})]


def test_handler_produces_transcript_and_forwards_to_workspace_2(repos, specs, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    sid = repos.add_source(kind="file", origin="a.mp4", media_path=str(tmp_path / "a.mp4"),
                           lang="zh", audio_path=str(wav), duration=4.0)
    created: list[FakeEngine] = []

    def factory(spec):
        engine = FakeEngine(spec)
        created.append(engine)
        return engine

    handler = TranscribeHandler(repos, specs, factory, workdir=tmp_path)
    job = Job(id=1, workspace=1, type="asr", engine="fw-large-v3-turbo",
              phase=js.phase_of("asr", "fw-large-v3-turbo"),
              payload={"source_id": sid}, created_at="2026-09-25T00:00:00Z")
    logs: list[tuple[float, str]] = []
    handler.run(job, lambda p, line: logs.append((p, line)))

    transcripts = repos.list_transcripts()
    assert len(transcripts) == 1
    t = transcripts[0]
    assert [s.text for s in t.segments] == ["你好", "世界"]
    assert t.engine == "fw-large-v3-turbo" and t.lang == "zh" and t.version == 1

    queue = repos.list_jobs()
    forwarded = [j for j in queue if j.type == "translate"]
    assert len(forwarded) == 1, "auto_forward mặc định BẬT nên phải có job dịch ở WS2"
    assert forwarded[0].workspace == 2
    assert forwarded[0].payload["transcript_id"] == t.id
    assert logs and logs[-1][0] == 1.0


def test_auto_forward_can_be_turned_off(repos, specs, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    repos.set_setting("auto_forward", "0")
    sid = repos.add_source(kind="file", origin="a", media_path="m", lang="zh",
                           audio_path=str(wav), duration=4.0)
    handler = TranscribeHandler(repos, specs, lambda spec: FakeEngine(spec), workdir=tmp_path)
    job = Job(id=1, workspace=1, type="asr", engine="fw-large-v3-turbo",
              phase="asr:fw-large-v3-turbo", payload={"source_id": sid},
              created_at="2026-09-25T00:00:00Z")
    handler.run(job, lambda p, line: None)
    assert [j for j in repos.list_jobs() if j.type == "translate"] == []
    assert repos.list_transcripts()[0].status == "draft"


def test_missing_audio_raises_actionable_error(repos, specs, tmp_path):
    sid = repos.add_source(kind="file", origin="a", media_path="m", lang="zh")
    handler = TranscribeHandler(repos, specs, lambda spec: FakeEngine(spec), workdir=tmp_path)
    job = Job(id=1, workspace=1, type="asr", engine="fw-large-v3-turbo",
              phase="asr:fw-large-v3-turbo", payload={"source_id": sid},
              created_at="2026-09-25T00:00:00Z")
    with pytest.raises(Exception) as exc:
        handler.run(job, lambda p, line: None)
    assert "audio" in str(exc.value).lower()


def test_engine_is_reused_across_jobs_of_the_same_phase(repos, specs, tmp_path):
    """Nạp model 4 lần cho 4 job là lãng phí 4-8 giây mỗi lần. Handler phải
    giữ engine theo id và chỉ tạo mới khi đổi engine."""
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    created: list[FakeEngine] = []

    def factory(spec):
        engine = FakeEngine(spec)
        created.append(engine)
        return engine

    handler = TranscribeHandler(repos, specs, factory, workdir=tmp_path)
    for n in range(3):
        sid = repos.add_source(kind="file", origin=f"a{n}", media_path="m", lang="zh",
                               audio_path=str(wav), duration=4.0)
        job = Job(id=n + 1, workspace=1, type="asr", engine="fw-large-v3-turbo",
                  phase="asr:fw-large-v3-turbo", payload={"source_id": sid},
                  created_at="2026-09-25T00:00:00Z")
        handler.run(job, lambda p, line: None)

    assert len(created) == 1, f"chỉ được nạp model 1 lần, thực tế {len(created)}"


def test_handler_releases_engine_when_switching_engine(repos, specs, tmp_path):
    from app.registry import EngineSpec
    both = specs + [EngineSpec(id="sensevoice-small", label="SV", kind="asr",
                               runtime="inprocess", model_ref="iic/SenseVoiceSmall",
                               vram_mb=1000, langs=("zh",), capabilities={}, opts={})]
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    created: list[FakeEngine] = []

    def factory(spec):
        engine = FakeEngine(spec)
        created.append(engine)
        return engine

    handler = TranscribeHandler(repos, both, factory, workdir=tmp_path)
    for n, engine_id in enumerate(["fw-large-v3-turbo", "fw-large-v3-turbo", "sensevoice-small"]):
        sid = repos.add_source(kind="file", origin=f"a{n}", media_path="m", lang="zh",
                               audio_path=str(wav), duration=4.0)
        job = Job(id=n + 1, workspace=1, type="asr", engine=engine_id,
                  phase=js.phase_of("asr", engine_id), payload={"source_id": sid},
                  created_at="2026-09-25T00:00:00Z")
        handler.run(job, lambda p, line: None)

    assert len(created) == 2
    assert created[0].released == 1, "đổi engine phải giải phóng engine cũ"
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_transcribe_pipeline.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.adapters.asr'`

- [ ] **Step 3: Viết adapter faster-whisper**

```python
# backend/app/adapters/asr/faster_whisper.py
"""Adapter faster-whisper (CTranslate2). KHÔNG cần torch.

`model_factory` được bơm vào để test kiểm tra hợp đồng mà không nạp model.
"""
from __future__ import annotations

from typing import Callable

from app.domain.models import Segment, Word
from app.domain.segmentation import normalize
from app.registry import EngineSpec


def to_segments(raw_segments: list[dict]) -> list[Segment]:
    """Hàm THUẦN: dict thô của faster-whisper -> list[Segment].

    Tách riêng để test được mà không cần GPU. Đây là chỗ dễ sai nhất của
    adapter: word timestamp rỗng phải thành None, không phải [].
    """
    out: list[Segment] = []
    for idx, raw in enumerate(raw_segments):
        words_raw = raw.get("words") or []
        words = [Word(w=w["word"], s=float(w["start"]), e=float(w["end"]))
                 for w in words_raw
                 if w.get("start") is not None and w.get("end") is not None]
        seg = Segment(
            i=idx,
            start=float(raw["start"]),
            end=float(raw["end"]),
            text=(raw.get("text") or "").strip(),
            words=words or None,
            avg_logprob=raw.get("avg_logprob"),
            no_speech_prob=raw.get("no_speech_prob"),
        )
        seg.mark_suspect()
        out.append(seg)
    return out


class FasterWhisperEngine:
    def __init__(
        self,
        spec: EngineSpec,
        *,
        device: str = "cuda",
        download_root: str | None = None,
        model_factory: Callable[..., object] | None = None,
    ) -> None:
        self.engine_id = spec.id
        self.spec = spec
        self.device = device
        self.download_root = download_root
        self._model_factory = model_factory
        self._model = None
        self._batched = None

    def _load(self):
        if self._model is None:
            factory = self._model_factory
            if factory is None:
                from faster_whisper import WhisperModel
                factory = WhisperModel
            self._model = factory(
                self.spec.model_ref,
                device=self.device,
                compute_type=self.spec.opts.get("compute_type", "int8_float16"),
                download_root=self.download_root,
            )
        return self._model

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        model = self._load()
        batch_size = int(self.spec.opts.get("batch_size", 0) or 0)
        if batch_size > 1:
            from faster_whisper import BatchedInferencePipeline
            if self._batched is None:
                self._batched = BatchedInferencePipeline(model=model)
            iterator, _info = self._batched.transcribe(
                audio_path, language=lang, batch_size=batch_size,
                vad_filter=True, word_timestamps=True,
                condition_on_previous_text=False,
                initial_prompt=self.spec.opts.get("initial_prompt"),
            )
        else:
            iterator, _info = model.transcribe(
                audio_path, language=lang,
                vad_filter=True, word_timestamps=True,
                condition_on_previous_text=False,
                initial_prompt=self.spec.opts.get("initial_prompt"),
            )

        raw = [{
            "start": s.start, "end": s.end, "text": s.text,
            "avg_logprob": getattr(s, "avg_logprob", None),
            "no_speech_prob": getattr(s, "no_speech_prob", None),
            "words": [{"word": w.word, "start": w.start, "end": w.end}
                      for w in (getattr(s, "words", None) or [])],
        } for s in iterator]
        return normalize(to_segments(raw))

    def release(self) -> None:
        self._batched = None
        self._model = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
```

- [ ] **Step 4: Viết handler ASR**

```python
# backend/app/pipeline/transcribe.py
"""Use case bóc băng. Ráp registry + engine + repos.

Bất biến: engine được GIỮ theo engine_id và chỉ tạo mới khi đổi engine. Nạp
lại model cho từng job là lãng phí 4-8 giây mỗi lần.
"""
from __future__ import annotations

import pathlib
from typing import Callable, Iterable

from app.domain import job_state as js
from app.domain.models import Job
from app.ports.asr import ASREngine
from app.ports.repos import Repos
from app.registry import EngineSpec, by_id

AUTO_FORWARD_SETTING = "auto_forward"


class EngineFactory:
    def __call__(self, spec: EngineSpec) -> ASREngine:  # pragma: no cover - Protocol
        raise NotImplementedError


class TranscribeHandler:
    def __init__(
        self,
        repos: Repos,
        specs: Iterable[EngineSpec],
        engine_factory: Callable[[EngineSpec], ASREngine],
        *,
        workdir: str | pathlib.Path,
    ) -> None:
        self._repos = repos
        self._specs = list(specs)
        self._factory = engine_factory
        self._workdir = pathlib.Path(workdir)
        self._engine: ASREngine | None = None
        self._engine_id: str | None = None

    def handles(self) -> str:
        return "asr"

    def _engine_for(self, engine_id: str) -> ASREngine:
        if self._engine is not None and self._engine_id == engine_id:
            return self._engine
        if self._engine is not None:
            self._engine.release()
            self._engine = None
        spec = by_id(self._specs, engine_id)
        self._engine = self._factory(spec)
        self._engine_id = engine_id
        return self._engine

    def release(self) -> None:
        if self._engine is not None:
            self._engine.release()
            self._engine = None
            self._engine_id = None

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        source_id = job.payload["source_id"]
        source = self._repos.get_source(source_id)
        if not source.audio_path:
            raise FileNotFoundError(
                f"source {source_id} chưa có audio; job ingest phải chạy trước"
            )
        audio = pathlib.Path(source.audio_path)
        if not audio.exists():
            raise FileNotFoundError(f"tệp audio không tồn tại: {audio}")

        lang = source.lang or "zh"
        report(0.05, f"nạp engine {job.engine}")
        engine = self._engine_for(job.engine or "")

        report(0.15, f"bóc băng {audio.name} (lang={lang})")
        segments = engine.transcribe(str(audio), lang)

        report(0.9, f"đã có {len(segments)} đoạn")
        transcript_id = self._repos.add_transcript(
            source_id=source_id, engine=job.engine or "", lang=lang, segments=segments,
        )
        report(0.95, f"lưu transcript #{transcript_id}")

        if (self._repos.get_setting(AUTO_FORWARD_SETTING, "1") or "1") == "1":
            self._forward_to_translation(source_id, transcript_id, lang)
            report(0.98, "đã tạo job dịch ở workspace 2")
        else:
            report(0.98, "giữ lại để sửa (auto_forward tắt)")
        report(1.0, "xong")

    def _forward_to_translation(self, source_id: int, transcript_id: int, lang: str) -> None:
        engine_id = self._default_mt_engine()
        self._repos.add_job(Job(
            id=None, workspace=2, type="translate", engine=engine_id,
            phase=js.phase_of("translate", engine_id),
            payload={"transcript_id": transcript_id, "source_id": source_id, "lang": lang},
        ))

    def _default_mt_engine(self) -> str | None:
        configured = self._repos.get_setting("default_mt_engine")
        if configured:
            return configured
        mt_specs = [s for s in self._specs if s.kind == "mt"]
        return mt_specs[0].id if mt_specs else None
```

- [ ] **Step 5: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_transcribe_pipeline.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS. `test_layer_boundary.py` phải vẫn xanh: `transcribe.py` nằm ở `pipeline/`, được phép import `app.ports`; `faster_whisper.py` nằm ở `adapters/`, được phép import `faster_whisper`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/adapters/asr backend/app/pipeline/transcribe.py backend/tests/test_transcribe_pipeline.py
git commit -m "feat(asr): adapter faster-whisper + handler transcribe voi auto_forward"
```

---

## Task 13: Adapter SenseVoice + parser tag

**Files:**
- Create: `backend/app/adapters/asr/sensevoice_tags.py`, `backend/app/adapters/asr/sensevoice.py`, `backend/tests/test_sensevoice_tags.py`

**Interfaces:**
- Consumes: `EngineSpec`, `normalize`
- Produces:
  - `parse_rich_tags(raw: str) -> ParsedUtterance(text, lang, emotion, events, itn)`
  - `EMOTION_TAGS: frozenset[str]`, `EVENT_TAGS: frozenset[str]`
  - `SenseVoiceEngine(spec, *, device="cuda", model_factory=None)`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_sensevoice_tags.py
from __future__ import annotations

from app.adapters.asr.sensevoice_tags import parse_rich_tags


def test_parses_language_emotion_and_event_tags():
    raw = "<|zh|><|HAPPY|><|BGM|><|Speech|><|withitn|>大家好，欢迎来到本期节目"
    p = parse_rich_tags(raw)
    assert p.text == "大家好，欢迎来到本期节目"
    assert p.lang == "zh"
    assert p.emotion == "happy"
    assert p.events == ["bgm"]
    assert p.itn is True


def test_handles_multiple_events():
    p = parse_rich_tags("<|zh|><|NEUTRAL|><|Laughter|><|Applause|><|Speech|>哈哈")
    assert p.events == ["laughter", "applause"]
    assert p.emotion == "neutral"


def test_no_tags_is_passed_through():
    p = parse_rich_tags("纯文本")
    assert p.text == "纯文本"
    assert p.lang is None and p.emotion is None and p.events == []


def test_event_tags_are_not_leaked_into_subtitle_text():
    """Đây là lỗi dễ gặp nhất: nhét <|BGM|> vào phụ đề và người xem thấy nó."""
    raw = "<|zh|><|SAD|><|BGM|><|Speech|>这句话很难过"
    p = parse_rich_tags(raw)
    assert "<|" not in p.text and "|>" not in p.text
    assert p.text == "这句话很难过"


def test_unknown_tag_does_not_crash_and_is_dropped():
    p = parse_rich_tags("<|zh|><|SOMETHING_NEW|><|Speech|>文本")
    assert p.text == "文本"
    assert p.emotion is None


def test_whitespace_is_normalised():
    p = parse_rich_tags("<|zh|><|Speech|>  你好   世界  ")
    assert p.text == "你好 世界"
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sensevoice_tags.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Viết parser**

```python
# backend/app/adapters/asr/sensevoice_tags.py
"""Parser cho đầu ra 'rich text' của SenseVoice.

SenseVoice trả về chuỗi có tag, ví dụ:
    <|zh|><|HAPPY|><|BGM|><|Speech|><|withitn|>大家好

Parser này là hàm THUẦN nên test được mà không cần nạp model. Nó cũng là chỗ
chặn lỗi khó chịu nhất: để lọt <|BGM|> vào phụ đề.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TAG_RE = re.compile(r"<\|([^|]+)\|>")

EMOTION_TAGS = frozenset({
    "happy", "sad", "angry", "neutral", "fearful", "disgusted", "surprised",
    "unknown",
})
EVENT_TAGS = frozenset({
    "bgm", "speech", "applause", "laughter", "cry", "cough", "sneeze",
    "breath", "noise",
})
LANG_TAGS = frozenset({"zh", "en", "yue", "ja", "ko", "nospeech"})


@dataclass
class ParsedUtterance:
    text: str
    lang: str | None = None
    emotion: str | None = None
    events: list[str] = field(default_factory=list)
    itn: bool = False


def parse_rich_tags(raw: str) -> ParsedUtterance:
    out = ParsedUtterance(text="")
    for match in _TAG_RE.finditer(raw):
        token = match.group(1).strip().lower()
        if token in LANG_TAGS:
            out.lang = token
        elif token in EMOTION_TAGS:
            out.emotion = token
        elif token in EVENT_TAGS:
            if token != "speech" and token not in out.events:
                out.events.append(token)
        elif token == "withitn":
            out.itn = True
        # tag lạ: bỏ qua, không làm hỏng gì

    out.text = " ".join(_TAG_RE.sub("", raw).split())
    return out
```

- [ ] **Step 4: Viết adapter SenseVoice**

```python
# backend/app/adapters/asr/sensevoice.py
"""Adapter SenseVoice qua FunASR.

Khác faster-whisper ở ba điểm:
  * không có word timestamp -> chỉ timestamp cấp đoạn
  * không có avg_logprob -> dấu hiệu nghi ngờ lấy từ tag sự kiện (bgm, laughter)
  * cần torch + FunASR (faster-whisper thì không)
"""
from __future__ import annotations

from typing import Callable

from app.domain.models import Segment
from app.domain.segmentation import normalize
from app.registry import EngineSpec

from .sensevoice_tags import parse_rich_tags

SUSPICIOUS_EVENTS = frozenset({"bgm", "laughter", "cry", "applause"})


class SenseVoiceEngine:
    def __init__(
        self,
        spec: EngineSpec,
        *,
        device: str = "cuda",
        model_factory: Callable[..., object] | None = None,
    ) -> None:
        self.engine_id = spec.id
        self.spec = spec
        self.device = device
        self._model_factory = model_factory
        self._model = None

    def _load(self):
        if self._model is None:
            factory = self._model_factory
            if factory is None:
                from funasr import AutoModel
                factory = AutoModel
            self._model = factory(
                model=self.spec.model_ref,
                vad_model="fsmn-vad",
                punc_model="ct-punc",
                device=self.device,
                disable_update=True,
            )
        return self._model

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        model = self._load()
        raw = model.generate(
            input=audio_path,
            language=lang,
            use_itn=bool(self.spec.opts.get("use_itn", True)),
            batch_size_s=60,
            merge_vad=True,
        )
        segments: list[Segment] = []
        for idx, item in enumerate(_flatten(raw)):
            parsed = parse_rich_tags(item.get("text", ""))
            if not parsed.text:
                continue
            start = float(item.get("start", item.get("timestamp", [0])[0] if item.get("timestamp") else 0)) / 1000.0
            end = float(item.get("end", item.get("timestamp", [0, 0])[-1] if item.get("timestamp") else 0)) / 1000.0
            seg = Segment(
                i=idx, start=start, end=max(end, start + 0.01), text=parsed.text,
                emotion=parsed.emotion, events=list(parsed.events),
            )
            if SUSPICIOUS_EVENTS.intersection(parsed.events):
                seg.suspect = True
            segments.append(seg)
        if not segments:
            raise RuntimeError("SenseVoice không trả về đoạn nào")
        return normalize(segments)

    def release(self) -> None:
        self._model = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


def _flatten(raw) -> list[dict]:
    """FunASR trả về list[dict] hoặc list[list[dict]] tuỳ cấu hình VAD."""
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, list):
            out.extend(i for i in item if isinstance(i, dict))
        elif isinstance(item, dict):
            out.append(item)
    return out
```

- [ ] **Step 5: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_sensevoice_tags.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/adapters/asr/sensevoice_tags.py backend/app/adapters/asr/sensevoice.py backend/tests/test_sensevoice_tags.py
git commit -m "feat(asr): adapter SenseVoice + parser tag cam xuc/su kien"
```

---

## Task 14: Định dạng phụ đề + handler export

**Files:**
- Create: `backend/app/domain/subtitle_format.py`, `backend/app/pipeline/export.py`, `backend/tests/test_export.py`

**Interfaces:**
- Consumes: `Segment`
- Produces:
  - `format_timestamp(seconds: float, *, sep: str = ",") -> str` — `HH:MM:SS,mmm`
  - `to_srt(segments, *, translations=None, bilingual=False) -> str`
  - `to_vtt(segments, *, translations=None, bilingual=False) -> str`
  - `to_ass(segments, *, translations=None, bilingual=False, title="phu-de-lab") -> str`
  - `ExportHandler(repos, out_dir)` với `handles() -> "export"`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_export.py
from __future__ import annotations

import pytest

from app.domain.models import Segment
from app.domain.subtitle_format import (
    format_timestamp, to_ass, to_srt, to_vtt,
)


def test_timestamp_formatting_hours_and_millis():
    assert format_timestamp(0.0) == "00:00:00,000"
    assert format_timestamp(1.5) == "00:00:01,500"
    assert format_timestamp(3661.25) == "01:01:01,250"
    assert format_timestamp(1.5, sep=".") == "00:00:01.500"


def test_negative_timestamp_clamps_to_zero():
    assert format_timestamp(-3.0) == "00:00:00,000"


def test_srt_structure_and_indexing_from_one():
    segs = [Segment(i=0, start=1.0, end=2.5, text="甲"),
            Segment(i=1, start=2.5, end=4.0, text="乙")]
    out = to_srt(segs)
    lines = out.strip().splitlines()
    assert lines[0] == "1"
    assert lines[1] == "00:00:01,000 --> 00:00:02,500"
    assert lines[2] == "甲"
    assert lines[3] == ""
    assert lines[4] == "2"
    assert out.endswith("\n")


def test_srt_bilingual_puts_source_above_translation():
    segs = [Segment(i=0, start=0.0, end=2.0, text="大家好")]
    out = to_srt(segs, translations=["Chào mọi người"], bilingual=True)
    body = out.strip().splitlines()[2:]
    assert body[0] == "大家好"
    assert body[1] == "Chào mọi người"


def test_srt_monolingual_uses_translation_only():
    segs = [Segment(i=0, start=0.0, end=2.0, text="大家好")]
    out = to_srt(segs, translations=["Chào mọi người"], bilingual=False)
    assert "大家好" not in out
    assert "Chào mọi người" in out


def test_srt_translation_mismatch_length_raises():
    segs = [Segment(i=0, start=0.0, end=2.0, text="a"),
            Segment(i=1, start=2.0, end=4.0, text="b")]
    with pytest.raises(ValueError):
        to_srt(segs, translations=["chỉ một dòng"])


def test_vtt_has_header_and_dot_separator():
    out = to_vtt([Segment(i=0, start=0.0, end=1.0, text="x")])
    assert out.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.000" in out


def test_ass_has_script_info_and_dialogue_lines():
    segs = [Segment(i=0, start=0.0, end=1.0, text="x")]
    out = to_ass(segs)
    assert "[Script Info]" in out and "[V4+ Styles]" in out and "[Events]" in out
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,x" in out


def test_ass_escapes_braces_that_would_be_read_as_override_codes():
    segs = [Segment(i=0, start=0.0, end=1.0, text="a{b}c")]
    assert "a\\{b\\}c" in to_ass(segs)


def test_empty_segment_list_gives_valid_empty_documents():
    assert to_srt([]) == ""
    assert to_vtt([]).startswith("WEBVTT")
    assert "[Events]" in to_ass([])
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_export.py -v`

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Viết formatter (domain — thuần)**

```python
# backend/app/domain/subtitle_format.py
"""Sinh SRT / VTT / ASS. Thuần, không phụ thuộc gì.

Đặt ở domain vì đây là logic nghiệp vụ và phải test được mà không cần model,
không cần đĩa, không cần mạng.
"""
from __future__ import annotations

from .models import Segment


def format_timestamp(seconds: float, *, sep: str = ",") -> str:
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def _ass_timestamp(seconds: float) -> str:
    total_cs = int(round(max(0.0, seconds) * 100))
    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, centis = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _assert_lengths(segments: list[Segment], translations: list[str] | None) -> None:
    if translations is not None and len(translations) != len(segments):
        raise ValueError(
            f"số bản dịch ({len(translations)}) khác số đoạn ({len(segments)})"
        )


def _lines(seg: Segment, translated: str | None, bilingual: bool) -> list[str]:
    if translated is None:
        return [seg.text]
    return [seg.text, translated] if bilingual else [translated]


def to_srt(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False) -> str:
    _assert_lengths(segments, translations)
    if not segments:
        return ""
    blocks: list[str] = []
    for n, seg in enumerate(segments, start=1):
        translated = translations[n - 1] if translations is not None else None
        body = "\n".join(_lines(seg, translated, bilingual))
        blocks.append(
            f"{n}\n"
            f"{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n"
            f"{body}"
        )
    return "\n\n".join(blocks) + "\n"


def to_vtt(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False) -> str:
    _assert_lengths(segments, translations)
    out = ["WEBVTT", ""]
    for seg in segments:
        translated = None
        if translations is not None:
            translated = translations[seg.i] if seg.i < len(translations) else None
        out.append(
            f"{format_timestamp(seg.start, sep='.')} --> {format_timestamp(seg.end, sep='.')}"
        )
        out.extend(_lines(seg, translated, bilingual))
        out.append("")
    return "\n".join(out) + "\n"


_ASS_HEADER = """[Script Info]
Title: {title}
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Archivo,54,&H00DCE4E8,&H0000B0FF,&H00201F1E,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,60,60,48,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def to_ass(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False, title: str = "phu-de-lab") -> str:
    _assert_lengths(segments, translations)
    lines = [_ASS_HEADER.format(title=title)]
    for seg in segments:
        translated = translations[seg.i] if translations is not None and seg.i < len(translations) else None
        parts = _lines(seg, translated, bilingual)
        text = _ass_escape("\\N".join(parts))
        lines.append(
            f"Dialogue: 0,{_ass_timestamp(seg.start)},{_ass_timestamp(seg.end)},"
            f"Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Viết handler export**

```python
# backend/app/pipeline/export.py
"""Use case xuất phụ đề ra tệp."""
from __future__ import annotations

import json
import pathlib
from typing import Callable

from app.domain.models import Job
from app.domain.subtitle_format import to_ass, to_srt, to_vtt
from app.ports.repos import Repos

FORMATS = {"srt": to_srt, "vtt": to_vtt, "ass": to_ass}


class ExportHandler:
    def __init__(self, repos: Repos, *, out_dir: str | pathlib.Path) -> None:
        self._repos = repos
        self._out_dir = pathlib.Path(out_dir)

    def handles(self) -> str:
        return "export"

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        payload = job.payload
        transcript_id = int(payload["transcript_id"])
        fmt = str(payload.get("format", "srt")).lower()
        bilingual = bool(payload.get("bilingual", False))
        if fmt not in FORMATS:
            raise ValueError(f"định dạng không hỗ trợ: {fmt!r} (có: {sorted(FORMATS)})")

        transcript = self._repos.get_transcript(transcript_id)
        report(0.3, f"dựng {fmt.upper()} cho transcript #{transcript_id}")

        translations = payload.get("translations")
        if translations is not None and len(translations) != len(transcript.segments):
            raise ValueError("số bản dịch không khớp số đoạn")

        content = FORMATS[fmt](transcript.segments, translations=translations,
                               bilingual=bilingual)

        self._out_dir.mkdir(parents=True, exist_ok=True)
        stem = payload.get("stem") or f"transcript-{transcript_id}"
        suffix = ".vi" if translations is not None else ""
        target = self._out_dir / f"{stem}{suffix}.{fmt}"
        target.write_text(content, encoding="utf-8")

        index = target.with_suffix(target.suffix + ".json")
        index.write_text(json.dumps({
            "transcript_id": transcript_id,
            "transcript_version": transcript.version,
            "engine": transcript.engine,
            "format": fmt,
            "bilingual": bilingual,
            "segments": len(transcript.segments),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        report(1.0, f"đã ghi {target}")
```

- [ ] **Step 5: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_export.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/subtitle_format.py backend/app/pipeline/export.py backend/tests/test_export.py
git commit -m "feat(export): SRT/VTT/ASS don ngu + song ngu"
```

---

## Task 15: FastAPI app + route sources & registry

**Files:**
- Create: `backend/app/api/__init__.py`, `backend/app/api/app.py`, `backend/app/api/deps.py`, `backend/app/api/routes_sources.py`, `backend/app/api/routes_registry.py`, `backend/app/main.py`, `backend/run_api.py`, `backend/tests/test_api_sources.py`

**Interfaces:**
- Consumes: `SqliteRepos`, `load_registry`, `ingest`, `config`
- Produces:
  - `create_app(*, repos, specs, media_dir, out_dir, worker=None) -> FastAPI`
  - `app.dependency_overrides` dùng được trong test
  - Endpoints: `POST /api/sources/upload` · `POST /api/sources/url` · `GET /api/sources` · `GET /api/sources/{id}` · `GET /api/registry` · `GET /api/status`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_api_sources.py
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.registry import EngineSpec


@pytest.fixture()
def client(tmp_path):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    specs = [
        EngineSpec(id="fw-large-v3-turbo", label="FW turbo", kind="asr",
                   runtime="inprocess", model_ref="large-v3-turbo", vram_mb=1600,
                   langs=("zh", "en"),
                   capabilities={"timestamps": True, "word_timestamps": True}, opts={}),
        EngineSpec(id="qwen2.5-7b", label="Qwen 7B", kind="mt", runtime="ollama",
                   model_ref="qwen2.5:7b", vram_mb=5200, langs=("zh", "en"),
                   capabilities={"glossary_prompt": True}, opts={}),
    ]
    app = create_app(repos=repos, specs=specs, media_dir=tmp_path / "media",
                     out_dir=tmp_path / "out")
    with TestClient(app) as c:
        c.repos = repos          # type: ignore[attr-defined]
        c.tmp = tmp_path         # type: ignore[attr-defined]
        yield c


def test_registry_endpoint_lists_both_kinds(client):
    body = client.get("/api/registry").json()
    assert [e["id"] for e in body["asr"]] == ["fw-large-v3-turbo"]
    assert [e["id"] for e in body["mt"]] == ["qwen2.5-7b"]
    assert body["mt"][0]["vram_mb"] == 5200


def test_status_endpoint_reports_phase_and_queue(client):
    body = client.get("/api/status").json()
    assert body["queue_depth"] == 0
    assert body["current_phase"] is None
    assert body["ollama"] in {"unknown", "up", "down"}


def test_upload_creates_source_and_ingest_job(client):
    payload = b"khong-phai-video-that-nhung-du-de-luu"
    resp = client.post(
        "/api/sources/upload",
        files={"file": ("bai-giang.mp4", io.BytesIO(payload), "video/mp4")},
        data={"lang": "zh"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"]["origin"] == "bai-giang.mp4"
    assert body["source"]["kind"] == "file"
    assert body["job"]["type"] == "ingest"
    assert body["job"]["workspace"] == 1

    stored = client.tmp / "media" / body["source"]["media_path"].split("/")[-1]
    assert stored.exists() and stored.read_bytes() == payload


def test_upload_rejects_unknown_lang(client):
    resp = client.post("/api/sources/upload",
                       files={"file": ("a.mp4", io.BytesIO(b"x"), "video/mp4")},
                       data={"lang": "klingon"})
    assert resp.status_code == 422


def test_upload_rejects_empty_file(client):
    resp = client.post("/api/sources/upload",
                       files={"file": ("a.mp4", io.BytesIO(b""), "video/mp4")},
                       data={"lang": "zh"})
    assert resp.status_code == 422


def test_url_endpoint_creates_url_source(client, monkeypatch):
    def fake_download(url, out_dir, on_progress=None, runner=None):
        import pathlib
        p = pathlib.Path(out_dir) / "vid.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return p

    monkeypatch.setattr("app.api.routes_sources.ingest.download_url", fake_download)
    resp = client.post("/api/sources/url", json={"url": "https://example.com/v", "lang": "zh"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"]["kind"] == "url"
    assert body["source"]["origin"] == "https://example.com/v"


def test_url_endpoint_rejects_non_http(client):
    resp = client.post("/api/sources/url", json={"url": "ftp://x/y", "lang": "zh"})
    assert resp.status_code == 422


def test_list_sources_returns_newest_first(client):
    for n in range(3):
        client.post("/api/sources/upload",
                    files={"file": (f"v{n}.mp4", io.BytesIO(b"x"), "video/mp4")},
                    data={"lang": "zh"})
    body = client.get("/api/sources").json()
    assert [s["origin"] for s in body] == ["v2.mp4", "v1.mp4", "v0.mp4"]


def test_cors_allows_frontend_dev_origin(client):
    resp = client.options("/api/registry", headers={
        "Origin": "http://localhost:3100",
        "Access-Control-Request-Method": "GET",
    })
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3100"
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_sources.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.api'`

- [ ] **Step 3: Viết deps + app factory**

```python
# backend/app/api/deps.py
from __future__ import annotations

from typing import Any

from fastapi import Request


def get_repos(request: Request):
    return request.app.state.repos


def get_specs(request: Request):
    return request.app.state.specs


def get_worker(request: Request):
    return getattr(request.app.state, "worker", None)


def get_dirs(request: Request) -> dict[str, Any]:
    return request.app.state.dirs
```

```python
# backend/app/api/app.py
from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.registry import EngineSpec

FRONTEND_DEV_ORIGINS = ["http://localhost:3100", "http://127.0.0.1:3100"]


def create_app(*, repos, specs: list[EngineSpec], media_dir, out_dir,
               worker=None, log_dir=None) -> FastAPI:
    app = FastAPI(title="phu-de-lab", version="0.1.0")
    app.state.repos = repos
    app.state.specs = specs
    app.state.worker = worker
    app.state.dirs = {
        "media": pathlib.Path(media_dir),
        "out": pathlib.Path(out_dir),
        "log": pathlib.Path(log_dir) if log_dir else pathlib.Path(out_dir).parent / "logs",
    }
    app.state.dirs["media"].mkdir(parents=True, exist_ok=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api import routes_registry, routes_sources

    app.include_router(routes_registry.router)
    app.include_router(routes_sources.router)
    return app
```

- [ ] **Step 4: Viết routes registry + sources**

```python
# backend/app/api/routes_registry.py
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.api.deps import get_repos, get_specs, get_worker

router = APIRouter(prefix="/api", tags=["registry"])


@router.get("/registry")
def get_registry(specs=Depends(get_specs)):
    out = {"asr": [], "mt": []}
    for spec in specs:
        payload = asdict(spec)
        payload["langs"] = list(spec.langs)
        out.setdefault(spec.kind, []).append(payload)
    return out


@router.get("/status")
def get_status(repos=Depends(get_repos), worker=Depends(get_worker)):
    queued = repos.list_jobs(states=("queued",))
    running = repos.list_jobs(states=("running",))
    return {
        "queue_depth": len(queued),
        "running": [j.id for j in running],
        "current_phase": getattr(worker, "current_phase", None),
        "phase_switches": getattr(worker, "phase_switches", 0),
        "ollama": "unknown",
    }
```

```python
# backend/app/api/routes_sources.py
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, field_validator

from app.api.deps import get_dirs, get_repos
from app.domain import job_state as js
from app.domain.models import Job
from app.pipeline import ingest

router = APIRouter(prefix="/api/sources", tags=["sources"])

ALLOWED_LANGS = {"zh", "en"}
_CHUNK = 1024 * 1024


class UrlIn(BaseModel):
    url: str
    lang: str = "zh"

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("chỉ nhận http/https")
        return v

    @field_validator("lang")
    @classmethod
    def _known_lang(cls, v: str) -> str:
        if v not in ALLOWED_LANGS:
            raise ValueError(f"ngôn ngữ không hỗ trợ: {v!r}")
        return v


def _source_json(source) -> dict:
    return {
        "id": source.id, "kind": source.kind, "origin": source.origin,
        "media_path": source.media_path, "audio_path": source.audio_path,
        "duration": source.duration, "lang": source.lang,
        "created_at": source.created_at,
    }


def _job_json(job: Job) -> dict:
    return {"id": job.id, "workspace": job.workspace, "type": job.type,
            "engine": job.engine, "phase": job.phase, "state": job.state}


def _enqueue_ingest(repos, source_id: int, lang: str) -> Job:
    job = Job(id=None, workspace=1, type="ingest", engine=None,
              phase=js.phase_of("ingest", None),
              payload={"source_id": source_id, "lang": lang})
    job.id = repos.add_job(job)
    return job


@router.post("/upload", status_code=201)
async def upload(file: UploadFile = File(...), lang: str = Form("zh"),
                 repos=Depends(get_repos), dirs=Depends(get_dirs)):
    if lang not in ALLOWED_LANGS:
        raise HTTPException(422, f"ngôn ngữ không hỗ trợ: {lang!r}")

    media_dir: pathlib.Path = dirs["media"]
    target = media_dir / pathlib.Path(file.filename or "upload.bin").name
    size = 0
    with open(target, "wb") as fh:
        while chunk := await file.read(_CHUNK):
            size += len(chunk)
            fh.write(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(422, "tệp rỗng")

    digest = ingest.sha256_file(target)
    stem = digest[:16]
    final = media_dir / f"{stem}{target.suffix}"
    target.replace(final)

    source_id = repos.add_source(kind="file", origin=file.filename or final.name,
                                 media_path=str(final), lang=lang)
    job = _enqueue_ingest(repos, source_id, lang)
    return {"source": _source_json(repos.get_source(source_id)), "job": _job_json(job)}


@router.post("/url", status_code=201)
def add_url(payload: UrlIn, repos=Depends(get_repos), dirs=Depends(get_dirs)):
    media_dir: pathlib.Path = dirs["media"]
    try:
        path = ingest.download_url(payload.url, media_dir)
    except ingest.IngestError as exc:
        raise HTTPException(422, str(exc)) from exc

    source_id = repos.add_source(kind="url", origin=payload.url,
                                 media_path=str(path), lang=payload.lang)
    job = _enqueue_ingest(repos, source_id, payload.lang)
    return {"source": _source_json(repos.get_source(source_id)), "job": _job_json(job)}


@router.get("")
def list_sources(repos=Depends(get_repos)):
    return [_source_json(s) for s in repos.list_sources()]


@router.get("/{source_id}")
def get_source(source_id: int, repos=Depends(get_repos)):
    try:
        return _source_json(repos.get_source(source_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
```

Route trên gọi `repos.list_sources()`. **Thêm phương thức đó vào ports và adapter ngay bây giờ** — nếu không, route sẽ không import được:

`backend/app/ports/repos.py`, trong Protocol `Repos`:

```python
    def list_sources(self) -> list[Source]: ...
```

`backend/app/adapters/persist/sqlite_repos.py`:

```python
    def list_sources(self) -> list[Source]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM sources ORDER BY id DESC").fetchall()
        return [self.get_source(r["id"]) for r in rows]
```

- [ ] **Step 5: Viết điểm khởi động**

```python
# backend/app/main.py
from __future__ import annotations

import threading

from app.adapters.clock_system import SystemClock
from app.adapters.governor.single_gpu import SingleGpuGovernor
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.adapters.registry_file import load_registry
from app.api.app import create_app
from app.config import (API_HOST, API_PORT, DB_PATH, LOG_DIR, MEDIA_DIR,
                        OUTPUT_DIR, ensure_dirs)
from app.pipeline.export import ExportHandler
from app.pipeline.ingest import IngestHandler
from app.pipeline.transcribe import TranscribeHandler
from app.worker import PhaseQueueWorker


def build_components():
    ensure_dirs()
    repos = SqliteRepos(DB_PATH, clock=SystemClock())
    repos.init_schema()
    specs = load_registry()
    governor = SingleGpuGovernor(repos)
    handlers = {
        "ingest": IngestHandler(repos),
        "asr": TranscribeHandler(repos, specs, engine_factory=_engine_factory, workdir=MEDIA_DIR),
        "export": ExportHandler(repos, out_dir=OUTPUT_DIR),
    }
    worker = PhaseQueueWorker(repos, governor, handlers)
    return repos, specs, worker


def _engine_factory(spec):
    from app.adapters.asr.faster_whisper import FasterWhisperEngine
    from app.adapters.asr.sensevoice import SenseVoiceEngine

    if spec.id.startswith("fw-"):
        return FasterWhisperEngine(spec)
    if spec.id == "sensevoice-small":
        return SenseVoiceEngine(spec)
    raise KeyError(f"không có adapter cho engine {spec.id!r}")


def main() -> None:
    import uvicorn

    repos, specs, worker = build_components()
    worker.recover()
    app = create_app(repos=repos, specs=specs, media_dir=MEDIA_DIR,
                     out_dir=OUTPUT_DIR, worker=worker, log_dir=LOG_DIR)
    thread = threading.Thread(target=worker.run_forever, name="phase-queue", daemon=True)
    thread.start()
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


if __name__ == "__main__":
    main()
```

```python
# backend/run_api.py
"""Chạy API cho phát triển: python run_api.py"""
from app.main import main

if __name__ == "__main__":
    main()
```

Thêm `IngestHandler` vào `backend/app/pipeline/ingest.py`:

> **Ghi chú (R53 = DOC-03).** Chữ ký trong khối dưới đây là bản **đầu** của plan; code **đã ship**
> rộng hơn: `IngestHandler(repos, *, audio_dir=None, media_root=None, specs=None, declared_default_asr=None)`
> (`IngestHandler.__init__` trong `backend/app/pipeline/ingest.py`) — ba tham số cuối do I-3/I-6 thêm và
> chỉ `app/main.py` (khối `handlers` trong `build_components()`) truyền. `main.py` vì vậy cũng không còn
> là `IngestHandler(repos)` như khối `build_components()` ở dưới.

```python
class IngestHandler:
    """Job 'ingest': extract audio từ media đã có, đặt duration và lang."""

    def __init__(self, repos: Repos, *, audio_dir=None) -> None:
        self._repos = repos
        self._audio_dir = audio_dir

    def handles(self) -> str:
        return "ingest"

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        source_id = int(job.payload["source_id"])
        source = self._repos.get_source(source_id)
        media = pathlib.Path(source.media_path)
        if not media.exists():
            raise IngestError(f"tệp media không tồn tại: {media}")

        out_dir = pathlib.Path(self._audio_dir) if self._audio_dir else media.parent
        report(0.2, f"extract audio từ {media.name}")
        wav, duration = extract_audio(media, out_dir, stem=media.stem)
        self._repos.set_source_audio(source_id, str(wav), duration)
        report(0.7, f"audio {wav.name} · {duration:.1f}s")

        engine_id = self._repos.get_setting("default_asr_engine") or "fw-large-v3-turbo"
        self._repos.add_job(Job(
            id=None, workspace=1, type="asr", engine=engine_id,
            phase=job_state.phase_of("asr", engine_id),
            payload={"source_id": source_id, "lang": source.lang or "zh"},
        ))
        report(1.0, "đã tạo job bóc băng")
```

Thêm vào đầu `backend/app/pipeline/ingest.py`:

```python
from app.domain import job_state
from app.domain.models import Job
from app.ports.repos import Repos
```

- [ ] **Step 6: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_sources.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api backend/app/pipeline/ingest.py backend/app/main.py backend/run_api.py backend/app/ports/repos.py backend/app/adapters/persist/sqlite_repos.py backend/tests/test_api_sources.py
git commit -m "feat(api): app factory + routes sources/registry/status + IngestHandler"
```

---

## Task 16: Route jobs + SSE stream

**Files:**
- Create: `backend/app/api/routes_jobs.py`, `backend/app/api/sse.py`, `backend/tests/test_api_jobs_sse.py`
- Modify: `backend/app/api/app.py` (include router)

**Interfaces:**
- Consumes: `Repos`, `PhaseQueueWorker`
- Produces:
  - `POST /api/jobs` · `GET /api/jobs` · `GET /api/jobs/{id}` · `POST /api/jobs/{id}/cancel` · `POST /api/jobs/{id}/retry`
  - `GET /api/jobs/stream` — **một** SSE stream toàn cục; mỗi sự kiện là JSON của một job đã đổi trạng thái. Client tự lọc theo `job_id`.
  - `JobEventBroker` — hàng đợi trong bộ nhớ, worker/handler đẩy sự kiện vào

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_api_jobs_sse.py
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.api.sse import JobEventBroker, stream_events
from app.domain import job_state as js
from app.domain.models import Job
from app.registry import EngineSpec

_ASR_SPEC = EngineSpec(id="fw-large-v3-turbo", label="FW", kind="asr",
                       runtime="inprocess", model_ref="large-v3-turbo",
                       vram_mb=1600, langs=("zh", "en"), capabilities={}, opts={})


@pytest.fixture()
def env(tmp_path):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    broker = JobEventBroker()
    app = create_app(repos=repos, specs=[_ASR_SPEC], media_dir=tmp_path / "m",
                     out_dir=tmp_path / "o", broker=broker)
    with TestClient(app) as c:
        c.repos = repos
        c.broker = broker
        yield c


def test_create_job_validates_type(env):
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "khong-co", "engine": None})
    assert resp.status_code == 422
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                      "engine": "fw-large-v3-turbo",
                                      "payload": {"source_id": 1}})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["phase"] == "asr:fw-large-v3-turbo"
    assert body["state"] == js.QUEUED


def test_create_job_rejects_unknown_engine(env):
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                      "engine": "khong-co", "payload": {}})
    assert resp.status_code == 422


def test_list_and_get_job(env):
    env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                "engine": "fw-large-v3-turbo", "payload": {}})
    listed = env.get("/api/jobs").json()
    assert len(listed) == 1
    jid = listed[0]["id"]
    assert env.get(f"/api/jobs/{jid}").json()["id"] == jid
    assert env.get("/api/jobs/9999").status_code == 404


def test_cancel_sets_flag_not_kill(env):
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                       "engine": "fw-large-v3-turbo", "payload": {}})
    jid = resp.json()["id"]
    assert env.post(f"/api/jobs/{jid}/cancel").json()["cancel_requested"] is True
    assert env.repos.get_job(jid).state == js.CANCELLED, (
        "huỷ job đang queued là xong ngay (spec §5.4: 'job chưa chạy, huỷ là xong')"
    )


def test_retry_only_from_retryable_states(env):
    resp = env.post("/api/jobs", json={"workspace": 1, "type": "asr",
                                       "engine": "fw-large-v3-turbo", "payload": {}})
    jid = resp.json()["id"]
    assert env.post(f"/api/jobs/{jid}/retry").status_code == 409
    env.repos.set_job_state(jid, js.RUNNING)
    env.repos.set_job_state(jid, js.FAILED, error="x")
    assert env.post(f"/api/jobs/{jid}/retry").status_code == 200
    assert env.repos.get_job(jid).state == js.QUEUED


def test_sse_stream_emits_published_events(env):
    """Kiểm generator TRỰC TIẾP — KHÔNG qua `TestClient.stream()`.

    `TestClient` chạy app trong một portal rồi CHỜ app kết thúc, nên một
    `StreamingResponse` bọc generator vô hạn (`while True` + heartbeat 15s) làm
    `with env.stream(...)` **không bao giờ trả về**: test TREO chứ không đỏ.
    Gọi thẳng generator vẫn kiểm đúng tính chất cần kiểm — sự kiện publish ra
    thì có mặt trên luồng, đúng định dạng SSE — mà không cần app kết thúc.
    """
    gen = stream_events(env.broker, heartbeat=0.05)
    try:
        assert next(gen) == ": connected\n\n"
        env.broker.publish({"id": 7, "state": "done", "progress": 1.0})
        line = next(gen)
        assert line.startswith("data: ")
        assert json.loads(line[len("data: "):])["id"] == 7
    finally:
        gen.close()
    assert any(getattr(r, "path", None) == "/api/jobs/stream" for r in env.app.routes), (
        "route SSE phải được đăng ký trên app"
    )


def test_broker_drops_oldest_when_subscriber_is_slow():
    """Một subscriber chậm không được làm phình bộ nhớ server."""
    broker = JobEventBroker(max_queue=3)
    q = broker.subscribe()
    for n in range(10):
        broker.publish({"id": n})
    assert q.qsize() == 3
    got = [q.get_nowait()["id"] for _ in range(3)]
    assert got == [7, 8, 9], "phải giữ sự kiện MỚI NHẤT, bỏ cái cũ"
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_jobs_sse.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.sse'`

- [ ] **Step 3: Viết broker + route**

```python
# backend/app/api/sse.py
"""Một SSE stream toàn cục cho mọi job.

Vì sao toàn cục chứ không phải mỗi job một stream: giao diện hiển thị cả hàng
đợi, nên nó cần biết mọi job đổi trạng thái. Mỗi job một kết nối sẽ mở hàng
chục kết nối và mỗi cái lại phải polling.
"""
from __future__ import annotations

import json
import queue
import threading
from typing import Any, Iterator


class JobEventBroker:
    def __init__(self, *, max_queue: int = 500) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []
        self._max_queue = max_queue

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=self._max_queue)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            if q.full():
                try:
                    q.get_nowait()          # bỏ sự kiện CŨ NHẤT, giữ cái mới
                except queue.Empty:
                    pass
            try:
                q.put_nowait(event)
            except queue.Full:
                pass


def format_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def stream_events(broker: JobEventBroker, *, heartbeat: float = 15.0) -> Iterator[str]:
    q = broker.subscribe()
    try:
        yield ": connected\n\n"
        while True:
            try:
                event = q.get(timeout=heartbeat)
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            yield format_sse(event)
    finally:
        broker.unsubscribe(q)
```

```python
# backend/app/api/routes_jobs.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_repos, get_specs
from app.api.sse import JobEventBroker, stream_events
from app.domain import job_state as js
from app.domain.models import Job
from app.registry import by_id

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

JOB_TYPES = {"ingest", "asr", "translate", "export"}
ENGINE_REQUIRED = {"asr", "translate"}


class JobIn(BaseModel):
    workspace: int = Field(ge=1, le=2)
    type: str
    engine: str | None = None
    payload: dict = Field(default_factory=dict)


def _job_json(job: Job) -> dict:
    return {
        "id": job.id, "workspace": job.workspace, "type": job.type,
        "engine": job.engine, "phase": job.phase, "state": job.state,
        "cancel_requested": job.cancel_requested, "attempts": job.attempts,
        "progress": job.progress, "log_tail": job.log_tail, "error": job.error,
        "payload": job.payload, "created_at": job.created_at,
        "started_at": job.started_at, "finished_at": job.finished_at,
    }


@router.post("", status_code=201)
def create_job(payload: JobIn, repos=Depends(get_repos), specs=Depends(get_specs)):
    if payload.type not in JOB_TYPES:
        raise HTTPException(422, f"loại job không hợp lệ: {payload.type!r}")
    if payload.type in ENGINE_REQUIRED:
        if not payload.engine:
            raise HTTPException(422, f"job loại {payload.type} phải có engine")
        try:
            by_id(specs, payload.engine)
        except KeyError as exc:
            raise HTTPException(422, str(exc)) from exc

    job = Job(id=None, workspace=payload.workspace, type=payload.type,
              engine=payload.engine,
              phase=js.phase_of(payload.type, payload.engine),
              payload=payload.payload)
    job.id = repos.add_job(job)
    return _job_json(repos.get_job(job.id))


# PHẢI khai báo TRƯỚC "/{job_id}", nếu không FastAPI khớp "stream" vào job_id -> 422
@router.get("/stream")
def stream(request: Request):
    broker: JobEventBroker = request.app.state.broker
    return StreamingResponse(
        stream_events(broker),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("")
def list_jobs(repos=Depends(get_repos)):
    return [_job_json(j) for j in repos.list_jobs()]


@router.get("/{job_id}")
def get_job(job_id: int, repos=Depends(get_repos)):
    try:
        return _job_json(repos.get_job(job_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, repos=Depends(get_repos)):
    try:
        repos.request_cancel(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    job = repos.get_job(job_id)
    if job.state == js.QUEUED:
        repos.set_job_state(job_id, js.CANCELLED)
    return _job_json(repos.get_job(job_id))


@router.post("/{job_id}/retry")
def retry_job(job_id: int, repos=Depends(get_repos)):
    try:
        job = repos.get_job(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    if job.state not in js.RETRYABLE_STATES:
        raise HTTPException(409, f"chỉ chạy lại được job ở trạng thái {sorted(js.RETRYABLE_STATES)}")
    repos.retry_job(job_id)
    return _job_json(repos.get_job(job_id))
```

Sửa `create_app` trong `backend/app/api/app.py` — thay bằng bản đầy đủ này:

```python
# backend/app/api/app.py
from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.sse import JobEventBroker
from app.registry import EngineSpec

FRONTEND_DEV_ORIGINS = ["http://localhost:3100", "http://127.0.0.1:3100"]


def create_app(*, repos, specs: list[EngineSpec], media_dir, out_dir,
               worker=None, log_dir=None, broker=None) -> FastAPI:
    app = FastAPI(title="phu-de-lab", version="0.1.0")
    app.state.repos = repos
    app.state.specs = specs
    app.state.worker = worker
    app.state.broker = broker or JobEventBroker()
    app.state.dirs = {
        "media": pathlib.Path(media_dir),
        "out": pathlib.Path(out_dir),
        "log": pathlib.Path(log_dir) if log_dir else pathlib.Path(out_dir).parent / "logs",
    }
    app.state.dirs["media"].mkdir(parents=True, exist_ok=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_DEV_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api import routes_jobs, routes_registry, routes_sources

    app.include_router(routes_registry.router)
    app.include_router(routes_sources.router)
    app.include_router(routes_jobs.router)
    return app
```

> **Thứ tự trong file là quan trọng, không phải ở đây.** Router được thêm DẦN theo từng task, và mỗi task chỉ được import những router **đã tồn tại** tại thời điểm đó — import một module chưa có là `ModuleNotFoundError`, không phải "chuẩn bị trước":
> - **T15:** `routes_registry`, `routes_sources` (2 dòng).
> - **T16 (task này):** thêm `routes_jobs` — **một** dòng.
> - **T17:** thêm `routes_media` — **một** dòng.
> - **T18:** thêm `routes_transcripts` **và** `routes_export` — **hai** dòng.
>
> Khối code ngay trên là bản **của T16** (đúng ba router). Bản đầy đủ sáu router chỉ đúng **sau T18**.

> **Bẫy thứ tự route:** `GET /api/jobs/stream` phải được khai báo **TRƯỚC** `GET /api/jobs/{job_id}`, nếu không FastAPI sẽ khớp `stream` vào `job_id` và trả 422. Đặt `stream` ngay sau `POST ""`.

- [ ] **Step 4: Viết heartbeat cho worker đẩy sự kiện**

Thêm vào `backend/app/worker.py` — một tham số tuỳ chọn để phát sự kiện:

```python
    def __init__(
        self,
        repos: Repos,
        governor: ResourceGovernor,
        handlers: dict[str, JobHandler],
        *,
        poll_interval: float = 0.05,
        sleeper: Callable[[float], None] = time.sleep,
        publish: Callable[[dict], None] | None = None,
    ) -> None:
        ...
        self._publish = publish or (lambda event: None)

    def _emit(self, job_id: int) -> None:
        job = self.repos.get_job(job_id)
        self._publish({
            "id": job.id, "state": job.state, "progress": job.progress,
            "phase": job.phase, "error": job.error,
        })
```

Gọi `self._emit(job.id)` sau **mỗi** lần `set_job_state`, `set_job_progress`, và trong `report()`.

- [ ] **Step 5: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_jobs_sse.py tests/test_worker_phases.py -v`

Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes_jobs.py backend/app/api/sse.py backend/app/api/app.py backend/app/worker.py backend/tests/test_api_jobs_sse.py
git commit -m "feat(api): route jobs + SSE stream toan cuc + broker"
```

---

## Task 17: Endpoint media có HTTP Range

**Files:**
- Create: `backend/app/api/routes_media.py`, `backend/tests/test_api_media_range.py`
- Modify: `backend/app/api/app.py` (include router)

**Interfaces:**
- Consumes: `Repos`, `media_dir`
- Produces: `GET /api/media/{source_id}` trả `200` (toàn tệp) hoặc `206` (`Range`), kèm `Accept-Ranges: bytes`, `Content-Range`, `Content-Length`

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_api_media_range.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app

PAYLOAD = bytes(range(256)) * 4          # 1024 byte xác định


@pytest.fixture()
def client(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    video = media / "clip.mp4"
    video.write_bytes(PAYLOAD)

    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    sid = repos.add_source(kind="file", origin="clip.mp4", media_path=str(video), lang="zh")

    app = create_app(repos=repos, specs=[], media_dir=media, out_dir=tmp_path / "o")
    with TestClient(app) as c:
        c.source_id = sid       # type: ignore[attr-defined]
        yield c


def test_full_download_advertises_range_support(client):
    resp = client.get(f"/api/media/{client.source_id}")
    assert resp.status_code == 200
    assert resp.headers["accept-ranges"] == "bytes"
    assert len(resp.content) == 1024
    assert resp.headers["content-type"].startswith("video/mp4")


def test_range_request_returns_206_with_exact_slice(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=0-99"})
    assert resp.status_code == 206
    assert resp.content == PAYLOAD[:100]
    assert resp.headers["content-range"] == "bytes 0-99/1024"
    assert resp.headers["content-length"] == "100"


def test_open_ended_range(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=1000-"})
    assert resp.status_code == 206
    assert resp.content == PAYLOAD[1000:]
    assert resp.headers["content-range"] == "bytes 1000-1023/1024"


def test_suffix_range_returns_last_bytes(client):
    """Trình phát của trình duyệt dùng dạng này để đọc moov atom ở cuối mp4."""
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=-64"})
    assert resp.status_code == 206
    assert resp.content == PAYLOAD[-64:]
    assert resp.headers["content-range"] == "bytes 960-1023/1024"


def test_unsatisfiable_range_returns_416_with_total(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=5000-6000"})
    assert resp.status_code == 416
    assert resp.headers["content-range"] == "bytes */1024"


def test_malformed_range_header_is_ignored_not_fatal(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "banana"})
    assert resp.status_code == 200


def test_unknown_source_is_404(client):
    assert client.get("/api/media/9999").status_code == 404


def test_missing_file_on_disk_is_410(client, tmp_path):
    import os
    src = client.repos.get_source(client.source_id) if hasattr(client, "repos") else None
    # đường dẫn nằm trong DB; xoá tệp rồi thử lại
    path = None
    for candidate in (tmp_path / "media").iterdir():
        path = candidate
    assert path is not None
    path.unlink()
    resp = client.get(f"/api/media/{client.source_id}")
    assert resp.status_code == 410
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_media_range.py -v`

Expected: FAIL — 404 vì chưa có route (hoặc `ModuleNotFoundError`)

- [ ] **Step 3: Viết route media**

```python
# backend/app/api/routes_media.py
"""Serve media cho trình phát.

BẮT BUỘC hỗ trợ HTTP Range. Không có Range thì trình duyệt không seek được, và
tín hiệu 'đoạn nghi ngờ' trở nên vô dụng: người dùng biết dòng nào sai mà không
nghe được để sửa.
"""
from __future__ import annotations

import mimetypes
import pathlib
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

from app.api.deps import get_dirs, get_repos

router = APIRouter(prefix="/api/media", tags=["media"])

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_CHUNK = 1024 * 256


def parse_range(header: str, size: int) -> tuple[int, int] | None | str:
    """Trả (start, end) đóng, hoặc None nếu bỏ qua header, hoặc 'unsatisfiable'."""
    match = _RANGE_RE.match(header.strip())
    if not match:
        return None
    raw_start, raw_end = match.group(1), match.group(2)

    if raw_start == "" and raw_end == "":
        return None
    if raw_start == "":
        length = int(raw_end)
        if length <= 0:
            return "unsatisfiable"
        start = max(0, size - length)
        return start, size - 1
    start = int(raw_start)
    end = int(raw_end) if raw_end else size - 1
    if start >= size or start > end:
        return "unsatisfiable"
    return start, min(end, size - 1)


def _iter_file(path: pathlib.Path, start: int, end: int):
    remaining = end - start + 1
    with open(path, "rb") as fh:
        fh.seek(start)
        while remaining > 0:
            chunk = fh.read(min(_CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/{source_id}")
def get_media(source_id: int, request: Request,
              repos=Depends(get_repos), dirs=Depends(get_dirs)):
    try:
        source = repos.get_source(source_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    path = pathlib.Path(source.media_path)
    if not path.exists():
        raise HTTPException(410, f"tệp media đã bị xoá: {path.name}")

    size = path.stat().st_size
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(path, media_type=media_type,
                            headers={"Accept-Ranges": "bytes"})

    parsed = parse_range(range_header, size)
    if parsed is None:
        return FileResponse(path, media_type=media_type,
                            headers={"Accept-Ranges": "bytes"})
    if parsed == "unsatisfiable":
        return Response(status_code=416, headers={
            "Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes",
        })

    start, end = parsed
    return Response(
        content=b"".join(_iter_file(path, start, end)),
        status_code=206,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
        },
    )
```

Sửa `create_app`: `from app.api import routes_jobs, routes_media, routes_registry, routes_sources` và `app.include_router(routes_media.router)`.

- [ ] **Step 4: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_media_range.py -v`

Expected: tất cả PASS, đặc biệt `test_suffix_range_returns_last_bytes`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes_media.py backend/app/api/app.py backend/tests/test_api_media_range.py
git commit -m "feat(api): endpoint media ho tro HTTP Range cho trinh phat"
```

---

## Task 18: Route transcripts (sửa → tăng version → đánh stale) + export

**Files:**
- Create: `backend/app/api/routes_transcripts.py`, `backend/app/api/routes_export.py`, `backend/tests/test_api_transcripts.py`
- Modify: `backend/app/api/app.py` (include routers)

**Interfaces:**
- Consumes: `Repos`, `is_stale`, `reading_cps`
- Produces:
  - `GET /api/transcripts` · `GET /api/transcripts/{id}` · `PATCH /api/transcripts/{id}` · `POST /api/transcripts/{id}/approve`
  - `GET /api/transcripts/{id}/readability` — danh sách đoạn vượt ngưỡng CPS
  - `POST /api/export` → tạo job export; `GET /api/export/{job_id}/download`

> **Quyết định tường minh (R75 = DOC-04).** Hình dạng export của GĐ1a **cố ý** khác spec §11:
> plan (và code đã ship ở `backend/app/api/routes_export.py:59,83`) dùng
> **`POST /api/export`** + **`GET /api/export/{job_id}/download`**, còn spec §11 ghi
> `GET /api/export/{translation_id}?format=&bilingual=`. Lý do: GĐ1a **chưa có `translation_id`**
> để tham chiếu — chưa có handler `translate`, bảng `translations` chưa có người ghi — nên hình dạng
> của spec không dùng được. Đây là **điều chỉnh có ý thức**, không phải lệch im lặng; khi bảng
> `translations` có người ghi (GĐ2) thì chuyển sang hình dạng spec, hoặc giữ nguyên và ghi rõ lý do.
> Ba nhóm endpoint spec §11 chưa ship — `GET /api/translations?transcript_id=`,
> `PATCH /api/translations/{id}`, `GET`/`POST`/`PATCH /api/glossary` — là **đúng phạm vi**
> (workspace 2 ⇒ GĐ2), đã ghi trong bảng "Đã biết, NGOÀI phạm vi GĐ1a" ở cuối plan này để review
> toàn nhánh **không** đếm nhầm chúng thành thiếu sót.

- [ ] **Step 1: Viết test thất bại**

```python
# backend/tests/test_api_transcripts.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.domain.models import Segment


@pytest.fixture()
def client(tmp_path):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    sid = repos.add_source(kind="file", origin="a.mp4", media_path="m", lang="zh")
    segments = [
        Segment(i=0, start=0.0, end=3.0, text="大家好"),
        Segment(i=1, start=3.0, end=5.0, text="今天我们要聊的是人工智能"),
        Segment(i=2, start=5.0, end=8.0, text="这个模型它其实……",
                no_speech_prob=0.8, suspect=True),
    ]
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo",
                               lang="zh", segments=segments)
    app = create_app(repos=repos, specs=[], media_dir=tmp_path / "m",
                     out_dir=tmp_path / "o")
    with TestClient(app) as c:
        c.repos = repos
        c.tid = tid
        c.tmp = tmp_path
        yield c


def test_get_transcript_returns_segments_and_version(client):
    body = client.get(f"/api/transcripts/{client.tid}").json()
    assert body["version"] == 1
    assert [s["text"] for s in body["segments"]] == ["大家好", "今天我们要聊的是人工智能", "这个模型它其实……"]
    assert body["segments"][2]["suspect"] is True


def test_patch_segments_bumps_version(client):
    body = client.get(f"/api/transcripts/{client.tid}").json()
    segments = body["segments"]
    segments[0]["text"] = "Chào mọi người"
    resp = client.patch(f"/api/transcripts/{client.tid}", json={"segments": segments})
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    assert client.get(f"/api/transcripts/{client.tid}").json()["segments"][0]["text"] == "Chào mọi người"


def test_patch_rejects_malformed_segment(client):
    resp = client.patch(f"/api/transcripts/{client.tid}",
                        json={"segments": [{"start": 0.0}]})
    assert resp.status_code == 422


def test_readability_endpoint_flags_long_line(client):
    """Số đo THẬT của fixture, tính bằng `reading_cps` (không đoán):

        đoạn 0 · 大家好 · 3 ký tự / 3,0 s = **1,00 CPS**
        đoạn 1 · 今天我们要聊的是人工智能 · 12 ký tự / 2,0 s = **6,00 CPS**
        đoạn 2 · 这个模型它其实…… · 9 ký tự / 3,0 s = **3,00 CPS**

    `CPS_WARN = 20,0` nên ở ngưỡng mặc định **không đoạn nào** bị gắn cờ và phép
    kiểm vô nghĩa. Hạ ngưỡng xuống **5,0** — nằm giữa 3,00 và 6,00 — thì đúng đoạn
    1 bị gắn cờ. (Bản trước của plan khẳng định ngưỡng mặc định, kèm thông báo
    "19 ký tự trong 2 giây" — con số đó = 9,5 CPS, **cũng không đạt** 20,0, tức
    plan sai ở cả phép kiểm lẫn thông báo.)
    """
    body = client.get(f"/api/transcripts/{client.tid}/readability",
                      params={"threshold": 5.0}).json()
    assert body["threshold"] == 5.0
    flagged = [item["i"] for item in body["too_fast"]]
    assert 1 in flagged, "đoạn 1 = 6,00 CPS phải vượt ngưỡng 5,0"
    assert 0 not in flagged, "đoạn 0 = 1,00 CPS không được vượt ngưỡng 5,0"


def test_approve_moves_status_to_reviewed(client):
    resp = client.post(f"/api/transcripts/{client.tid}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "reviewed"


def test_stale_flag_is_computed_not_stored(client):
    """Bản dịch dịch từ v1, transcript lên v3 -> phải báo lỗi thời."""
    client.repos.add_llm_call(job_id=None, engine="qwen2.5-7b", model_ref="m",
                              prompt_version="v1", tokens_in=1, tokens_out=1,
                              duration_ms=1, ok=True, error=None)
    with client.repos._connect() as conn:  # noqa: SLF001 - test dựng dữ liệu
        conn.execute(
            "INSERT INTO translations(transcript_id, transcript_version, engine,"
            " target_lang, segments, prompt_version, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (client.tid, 1, "qwen2.5-7b", "vi", "[]", "v1", "2026-09-25T00:00:00Z"),
        )
    body = client.get(f"/api/transcripts/{client.tid}").json()
    assert body["translations"][0]["stale"] is False, "v1 == v1 nên chưa lỗi thời"

    segments = body["segments"]
    segments[0]["text"] = "sửa"
    client.patch(f"/api/transcripts/{client.tid}", json={"segments": segments})

    body = client.get(f"/api/transcripts/{client.tid}").json()
    assert body["version"] == 2
    assert body["translations"][0]["stale"] is True
    assert body["translations"][0]["translated_from_version"] == 1


def test_export_creates_job_and_download_serves_file(client):
    resp = client.post("/api/export", json={"transcript_id": client.tid,
                                            "format": "srt", "bilingual": False})
    assert resp.status_code == 201
    job = resp.json()
    assert job["type"] == "export"

    # chạy handler trực tiếp vì test này không chạy worker
    from app.pipeline.export import ExportHandler
    from app.domain.models import Job
    handler = ExportHandler(client.repos, out_dir=client.tmp / "o")
    handler.run(Job(id=job["id"], workspace=1, type="export", engine=None,
                    phase="export:-", payload=job["payload"]), lambda p, line: None)
    client.repos.set_job_state(job["id"], "running")
    client.repos.set_job_state(job["id"], "done")

    dl = client.get(f"/api/export/{job['id']}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/x-subrip"), (
        "SRT dùng MIME application/x-subrip (media_types['srt']), KHÔNG phải text/plain"
    )
    assert "1\n00:00:00,000 --> 00:00:03,000\n大家好" in dl.text


def test_export_rejects_unknown_format(client):
    resp = client.post("/api/export", json={"transcript_id": client.tid, "format": "docx"})
    assert resp.status_code == 422


def test_export_before_job_done_is_409(client):
    resp = client.post("/api/export", json={"transcript_id": client.tid, "format": "srt"})
    job_id = resp.json()["id"]
    assert client.get(f"/api/export/{job_id}/download").status_code == 409
```

- [ ] **Step 2: Chạy test — phải ĐỎ**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_transcripts.py -v`

Expected: FAIL — 404 vì chưa có route

- [ ] **Step 3: Viết route transcripts**

```python
# backend/app/api/routes_transcripts.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_repos
from app.domain.models import Segment
from app.domain.readability import CPS_WARN, reading_cps
from app.domain.staleness import is_stale

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])

VALID_STATUS = {"draft", "reviewed", "translated"}


class PatchIn(BaseModel):
    segments: list[dict] = Field(min_length=1)
    status: str | None = None


def _translation_json(row: dict, current_version: int) -> dict:
    return {
        "id": row["id"],
        "engine": row["engine"],
        "target_lang": row["target_lang"],
        "prompt_version": row["prompt_version"],
        "translated_from_version": row["transcript_version"],
        "stale": is_stale(current_version, row["transcript_version"]),
        "created_at": row["created_at"],
    }


def _transcript_json(repos, transcript, include_segments: bool = True) -> dict:
    with repos._connect() as conn:  # noqa: SLF001 - đọc danh sách bản dịch kèm theo
        rows = [dict(r) for r in conn.execute(
            "SELECT id, engine, target_lang, prompt_version, transcript_version, created_at"
            " FROM translations WHERE transcript_id=? ORDER BY id DESC",
            (transcript.id,),
        ).fetchall()]
    out = {
        "id": transcript.id,
        "source_id": transcript.source_id,
        "engine": transcript.engine,
        "lang": transcript.lang,
        "version": transcript.version,
        "status": transcript.status,
        "created_at": transcript.created_at,
        "translations": [_translation_json(r, transcript.version) for r in rows],
    }
    if include_segments:
        out["segments"] = [s.to_json() for s in transcript.segments]
    return out


@router.get("")
def list_transcripts(repos=Depends(get_repos)):
    return [_transcript_json(repos, t, include_segments=False)
            for t in repos.list_transcripts()]


@router.get("/{transcript_id}")
def get_transcript(transcript_id: int, repos=Depends(get_repos)):
    try:
        return _transcript_json(repos, repos.get_transcript(transcript_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.patch("/{transcript_id}")
def patch_transcript(transcript_id: int, payload: PatchIn, repos=Depends(get_repos)):
    try:
        repos.get_transcript(transcript_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    try:
        segments = [Segment.from_json(d) for d in payload.segments]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, f"segment không hợp lệ: {exc}") from exc

    repos.update_transcript_segments(transcript_id, segments)

    if payload.status:
        if payload.status not in VALID_STATUS:
            raise HTTPException(422, f"trạng thái không hợp lệ: {payload.status!r}")
        repos.set_transcript_status(transcript_id, payload.status)

    return _transcript_json(repos, repos.get_transcript(transcript_id))


@router.get("/{transcript_id}/readability")
def readability(transcript_id: int, threshold: float = CPS_WARN,
                repos=Depends(get_repos)):
    try:
        transcript = repos.get_transcript(transcript_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    too_fast = []
    for seg in transcript.segments:
        cps = reading_cps(seg.text, seg.start, seg.end)
        if cps > threshold:
            too_fast.append({"i": seg.i, "cps": round(cps, 1),
                             "start": seg.start, "end": seg.end})
    return {"threshold": threshold, "too_fast": too_fast}


@router.post("/{transcript_id}/approve")
def approve(transcript_id: int, repos=Depends(get_repos)):
    try:
        repos.get_transcript(transcript_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    repos.set_transcript_status(transcript_id, "reviewed")
    return _transcript_json(repos, repos.get_transcript(transcript_id),
                            include_segments=False)
```

- [ ] **Step 4: Viết route export**

```python
# backend/app/api/routes_export.py
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.api.deps import get_dirs, get_repos
from app.domain import job_state as js
from app.domain.models import Job
from app.pipeline.export import FORMATS

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportIn(BaseModel):
    transcript_id: int
    format: str = "srt"
    bilingual: bool = False
    stem: str | None = None


def _artifact_path(out_dir: pathlib.Path, stem: str, fmt: str, bilingual: bool) -> pathlib.Path:
    del bilingual  # tên tệp không phụ thuộc chế độ; nội dung mới phụ thuộc
    return out_dir / f"{stem}.{fmt}"


@router.post("", status_code=201)
def create_export(payload: ExportIn, repos=Depends(get_repos)):
    fmt = payload.format.lower()
    if fmt not in FORMATS:
        raise HTTPException(422, f"định dạng không hỗ trợ: {payload.format!r}")
    try:
        repos.get_transcript(payload.transcript_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    stem = payload.stem or f"transcript-{payload.transcript_id}"
    job = Job(id=None, workspace=1, type="export", engine=None,
              phase=js.phase_of("export", None),
              payload={"transcript_id": payload.transcript_id, "format": fmt,
                       "bilingual": payload.bilingual, "stem": stem})
    job.id = repos.add_job(job)
    stored = repos.get_job(job.id)
    return {"id": stored.id, "type": stored.type, "phase": stored.phase,
            "state": stored.state, "payload": stored.payload}


@router.get("/{job_id}/download", response_class=PlainTextResponse)
def download(job_id: int, repos=Depends(get_repos), dirs=Depends(get_dirs)):
    try:
        job = repos.get_job(job_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    if job.type != "export":
        raise HTTPException(422, "job này không phải job xuất tệp")
    if job.state != js.DONE:
        raise HTTPException(409, f"job chưa xong (đang ở {job.state})")

    fmt = job.payload["format"]
    stem = job.payload["stem"]
    path = _artifact_path(pathlib.Path(dirs["out"]), stem, fmt, job.payload.get("bilingual", False))
    if not path.exists():
        raise HTTPException(410, f"tệp xuất không còn: {path.name}")

    media_types = {"srt": "application/x-subrip", "vtt": "text/vtt",
                   "ass": "text/x-ssa"}
    return PlainTextResponse(path.read_text(encoding="utf-8"),
                             media_type=media_types.get(fmt, "text/plain"))
```

- [ ] **Step 5: Chạy test — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api_transcripts.py tests/test_layer_boundary.py -v`

Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes_transcripts.py backend/app/api/routes_export.py backend/app/api/app.py backend/tests/test_api_transcripts.py
git commit -m "feat(api): transcripts (version/stale/CPS) + export"
```

---

## Task 19: E2E với engine giả — không tốn một MB VRAM

**Files:**
- Create: `backend/tests/test_e2e_fake.py`

**Interfaces:**
- Consumes: toàn bộ thành phần đã dựng
- Produces: chứng minh đường ống thật chạy đầu-cuối mà không nạp model nào

- [ ] **Step 1: Viết test**

```python
# backend/tests/test_e2e_fake.py
"""Chạy CẢ đường ống mà không nạp model nào.

Đây là lợi ích cụ thể của việc phân tầng: `domain` thuần nên thay engine thật
bằng engine giả là chuyện bình thường, không phải hack.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.governor.single_gpu import SingleGpuGovernor
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.domain.models import Job, Segment
from app.pipeline.export import ExportHandler
from app.pipeline.ingest import IngestHandler
from app.pipeline.transcribe import TranscribeHandler
from app.registry import EngineSpec
from app.worker import PhaseQueueWorker


class FakeASREngine:
    """Trả về transcript cố định, gồm cả một đoạn nghi ngờ."""

    def __init__(self, spec: EngineSpec) -> None:
        self.engine_id = spec.id
        self.release_count = 0

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        return [
            Segment(i=0, start=0.0, end=3.0, text="大家好"),
            Segment(i=1, start=3.0, end=5.0, text="今天我们要聊的是人工智能"),
            Segment(i=2, start=5.0, end=8.0, text="这个模型它其实……",
                    no_speech_prob=0.85, avg_logprob=-1.9, suspect=True),
        ]

    def release(self) -> None:
        self.release_count += 1


@pytest.fixture()
def wired(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    (media / "clip.wav").write_bytes(b"RIFF" + b"\x00" * 100)
    (media / "clip.mp4").write_bytes(b"\x00" * 64)

    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()

    specs = [
        EngineSpec(id="fw-large-v3-turbo", label="FW", kind="asr", runtime="inprocess",
                   model_ref="large-v3-turbo", vram_mb=1600, langs=("zh", "en"),
                   capabilities={}, opts={}),
    ]
    governor = SingleGpuGovernor(repos)

    created: list[FakeASREngine] = []

    def factory(spec):
        engine = FakeASREngine(spec)
        created.append(engine)
        return engine

    handlers = {
        "asr": TranscribeHandler(repos, specs, factory, workdir=media),
        "export": ExportHandler(repos, out_dir=tmp_path / "out"),
    }
    # ingest thật cần ffmpeg; ở test này ta đã có wav nên dùng handler giả tối thiểu
    class StubIngest:
        def handles(self) -> str:
            return "ingest"

        def run(self, job, report) -> None:
            sid = job.payload["source_id"]
            source = repos.get_source(sid)
            # R37: tệp wav phải TỒN TẠI. Bản trước suy tên qua `.replace(".mp4", ".wav")`
            # nhưng KHÔNG ai tạo tệp đó, nên `TranscribeHandler` ném FileNotFoundError
            # và job ASR thành FAILED. Dùng `open` (builtin) để khỏi thêm import.
            audio = source.media_path.replace(".mp4", ".wav")
            with open(audio, "wb") as fh:
                fh.write(b"stub-wav")
            repos.set_source_audio(sid, audio, 8.0)
            # R7: và phải TẠO JOB ASR — không có nó thì không có gì chạy bóc băng.
            repos.add_job(Job(id=None, workspace=1, type="asr",
                              engine="fw-large-v3-turbo",
                              phase="asr:fw-large-v3-turbo",
                              payload={"source_id": sid}))
            report(1.0, "ingest giả")

    handlers["ingest"] = StubIngest()

    worker = PhaseQueueWorker(repos, governor, handlers)
    app = create_app(repos=repos, specs=specs, media_dir=media,
                     out_dir=tmp_path / "out", worker=worker)
    with TestClient(app) as c:
        c.repos = repos
        c.worker = worker
        c.created = created
        c.tmp = tmp_path
        yield c


def test_full_pipeline_from_upload_to_srt(wired):
    """upload -> ingest -> asr -> (auto_forward tạo job dịch) -> export -> tải về."""
    resp = wired.post("/api/sources/upload",
                      files={"file": ("clip.mp4", b"x" * 64, "video/mp4")},
                      data={"lang": "zh"})
    assert resp.status_code == 201

    wired.worker.recover()
    while wired.worker.tick():
        pass

    transcripts = wired.get("/api/transcripts").json()
    assert len(transcripts) == 1
    tid = transcripts[0]["id"]

    detail = wired.get(f"/api/transcripts/{tid}").json()
    assert detail["version"] == 1
    assert [s["text"] for s in detail["segments"]][0] == "大家好"
    assert detail["segments"][2]["suspect"] is True

    running = wired.get("/api/status").json()
    assert running["queue_depth"] == 0, "hàng đợi phải cạn; job dịch không có handler nên sẽ failed"

    read = wired.get(f"/api/transcripts/{tid}/readability",
                     params={"threshold": 5.0}).json()
    assert 1 in [item["i"] for item in read["too_fast"]], (
        "đoạn 1 = 6,00 CPS > ngưỡng 5,0 (CPS_WARN 20,0 sẽ không gắn cờ đoạn nào)"
    )

    exp = wired.post("/api/export", json={"transcript_id": tid, "format": "srt"})
    assert exp.status_code == 201
    job_id = exp.json()["id"]
    while wired.worker.tick():
        pass

    dl = wired.get(f"/api/export/{job_id}/download")
    assert dl.status_code == 200
    text = dl.text
    assert "1\n00:00:00,000 --> 00:00:03,000\n大家好" in text
    assert text.count("-->") == 3


def test_fake_asr_model_loaded_exactly_once_for_the_phase(wired):
    for n in range(3):
        wired.post("/api/sources/upload",
                   files={"file": (f"c{n}.mp4", b"x" * 64, "video/mp4")},
                   data={"lang": "zh"})
    wired.worker.recover()
    while wired.worker.tick():
        pass

    assert len(wired.created) == 1, (
        f"3 job cùng engine phải nạp model 1 lần, thực tế {len(wired.created)}"
    )
    assert wired.worker.phase_switches == 2, "ingest:- rồi asr:fw-large-v3-turbo"


def test_layer_boundary_still_holds_after_everything(wired):
    """Nhắc lại: nếu test này đỏ thì ai đó đã import hạ tầng vào domain."""
    from tests.test_layer_boundary import test_domain_has_no_forbidden_absolute_imports
    test_domain_has_no_forbidden_absolute_imports()
```

- [ ] **Step 2: Chạy test — kỳ vọng ĐỎ ở lần đầu**

Run: `.venv\Scripts\python.exe -m pytest tests/test_e2e_fake.py -v`

Expected: có thể FAIL ở `queue_depth` vì job `translate` không có handler sẽ thành `failed` — nếu vậy, sửa test cho khớp hành vi thật (job failed nhưng hàng đợi cạn), **không** thêm handler giả cho translate.

- [ ] **Step 3: Chỉnh test cho khớp hành vi thật**

Nếu job translate thành `failed`, thêm khẳng định rõ ràng thay vì bỏ qua:

```python
    jobs = wired.get("/api/jobs").json()
    translate_jobs = [j for j in jobs if j["type"] == "translate"]
    assert len(translate_jobs) == 1
    assert translate_jobs[0]["state"] == "failed", (
        "GĐ1a chưa có handler dịch; job phải failed rõ ràng chứ không treo"
    )
    assert "không có handler" in (translate_jobs[0]["error"] or "")
```

- [ ] **Step 4: Chạy lại — phải XANH**

Run: `.venv\Scripts\python.exe -m pytest tests/test_e2e_fake.py -v`

Expected: tất cả PASS.

- [ ] **Step 5: Chạy TOÀN BỘ bộ test**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: tất cả PASS, không test nào bị skip ngoài `test_ingest.py` (chỉ skip nếu máy không có ffmpeg).

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_e2e_fake.py
git commit -m "test(e2e): duong ong day du voi engine gia, khong ton VRAM"
```

---

## Task 20: Cài đặt + smoke test với model thật

**Files:**
- Create: `backend/scripts/install.ps1`, `backend/scripts/smoke_asr.py`
- Create: `backend/README.md`

**Interfaces:**
- Consumes: mọi thứ ở trên
- Produces: môi trường cài được bằng một lệnh, và một smoke test chạy model thật

- [ ] **Step 1: Viết script cài đặt**

```powershell
# backend/scripts/install.ps1
# Cài môi trường backend. Chạy: pwsh -File backend/scripts/install.ps1
#
# THỨ TỰ QUAN TRỌNG: torch PHẢI cài trước funasr. Nếu không, FunASR kéo bản
# torch CPU và bạn mất GPU mà không có cảnh báo nào.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Split-Path -Parent $here
Set-Location $backend

Write-Host "== 1/6 · venv ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { py -3.10 -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip

Write-Host "== 2/6 · torch cu121 (TRƯỚC funasr) ==" -ForegroundColor Cyan
& $py -m pip install torch==2.5.1 torchaudio==2.5.1 `
    --index-url https://download.pytorch.org/whl/cu121

Write-Host "== 3/6 · kiểm tra CUDA ==" -ForegroundColor Cyan
& $py -c @"
import torch, sys
ok = torch.cuda.is_available()
print('torch', torch.__version__, '| cuda available:', ok)
if not ok:
    sys.exit('THẤT BẠI: torch không thấy GPU. Dừng ở đây thay vì chạy CPU.')
print('device:', torch.cuda.get_device_name(0))
"@

Write-Host "== 4/6 · phần còn lại ==" -ForegroundColor Cyan
& $py -m pip install -r requirements.txt

Write-Host "== 5/6 · Ollama (chưa cần model, nhưng cài sớm để de-risk) ==" -ForegroundColor Cyan
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "ollama đã có sẵn"
} else {
    Write-Host "chưa có ollama — cài bằng: winget install Ollama.Ollama" -ForegroundColor Yellow
}

Write-Host "== 6/6 · yt-dlp ==" -ForegroundColor Cyan
if (-not (Get-Command yt-dlp -ErrorAction SilentlyContinue)) {
    & $py -m pip install --upgrade yt-dlp
}

Write-Host ""
Write-Host "XONG. Biến môi trường nên đặt:" -ForegroundColor Green
Write-Host '  $env:HF_HOME = "D:\models\hf"'
Write-Host '  $env:PHUDE_PORT = "8620"'
```

- [ ] **Step 2: Viết smoke test model thật**

```python
# backend/scripts/smoke_asr.py
"""Smoke test với model THẬT. Chạy sau khi cài xong:

    .venv\\Scripts\\python.exe scripts\\smoke_asr.py <duong-dan-audio> [zh|en]

Không thuộc bộ pytest vì nó tải model vài GB và cần GPU.
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.adapters.asr.faster_whisper import FasterWhisperEngine  # noqa: E402
from app.adapters.registry_file import load_registry  # noqa: E402
from app.registry import by_id  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    audio = pathlib.Path(sys.argv[1])
    lang = sys.argv[2] if len(sys.argv) > 2 else "zh"
    if not audio.exists():
        print(f"không thấy tệp: {audio}")
        return 2

    spec = by_id(load_registry(), "fw-large-v3-turbo")
    print(f"[1/3] nạp {spec.model_ref} ...")
    t0 = time.perf_counter()
    engine = FasterWhisperEngine(spec)
    engine._load()  # noqa: SLF001 - smoke test đo thời gian nạp
    print(f"      nạp xong sau {time.perf_counter() - t0:.1f}s  <-- ghi số này vào eval/report.md")

    print(f"[2/3] bóc băng {audio.name} (lang={lang}) ...")
    t1 = time.perf_counter()
    segments = engine.transcribe(str(audio), lang)
    elapsed = time.perf_counter() - t1

    duration = segments[-1].end if segments else 0.0
    rtf = elapsed / duration if duration else float("nan")
    print(f"[3/3] {len(segments)} đoạn trong {elapsed:.1f}s "
          f"| RTF = {rtf:.3f}  <-- ghi số này vào eval/report.md")

    for seg in segments[:5]:
        flag = " ⚠NGHI NGỜ" if seg.suspect else ""
        words = "có word-ts" if seg.words else "không word-ts"
        print(f"  {seg.start:7.2f} → {seg.end:7.2f}  {seg.text}{flag}  [{words}]")
    if len(segments) > 5:
        print(f"  ... và {len(segments) - 5} đoạn nữa")

    engine.release()
    print("OK — có timestamp cấp đoạn, engine chạy được.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Viết README backend**

> **ĐÍNH CHÍNH (R40/DOC-07).** Ba dòng in trong script ghi `eval/report.md` vì `scripts/smoke_asr.py`
> chạy với cwd `backend\`; đường dẫn **đúng theo spec §10** là **`backend/eval/report.md`**
> (subsystem `backend/eval/`, `report.md` là bảng kết quả). Đây là **smoke THỦ CÔNG của Task 20**,
> **không** phải test tự động — GĐ1a chưa nạp model thật lần nào. Thư mục `backend/eval/` **chưa tồn tại**
> và **cố ý không được tạo** ở vòng dọn này (tạo thư mục rỗng chỉ để "cho khớp" là giả); việc sinh báo cáo
> thật thuộc GĐ1b. Xem bảng "Đã biết, NGOÀI phạm vi GĐ1a" ở cuối plan.

```markdown
# phu-de-lab · backend

## Cài đặt

```powershell
pwsh -File scripts/install.ps1
$env:HF_HOME = "D:\models\hf"
```

`install.ps1` cài torch cu121 **trước** funasr và **dừng lại** nếu
`torch.cuda.is_available()` trả False — chạy CPU mà không biết là kiểu hỏng tệ nhất.

## Chạy

```powershell
.\.venv\Scripts\python.exe run_api.py      # http://127.0.0.1:8620
```

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q                    # toàn bộ, không cần model
.\.venv\Scripts\python.exe scripts\smoke_asr.py clip.mp4 zh # model thật, cần GPU
```

## Ghi chú kiến trúc

`app/domain/` là logic thuần — `tests/test_layer_boundary.py` **sẽ đỏ** nếu ai đó
import `torch`, `sqlite3`, `fastapi` hay `httpx` vào đó. Đó là chủ ý, đừng sửa test.

`app/worker.py` gom lô theo **cặp (loại job, engine)**, không phải theo
`asr`/`mt`. Lý do: người dùng đổi được model cho từng job, nên gom theo loại job
là vô dụng.
```

- [ ] **Step 4: Chạy cài đặt thật**

Run: `pwsh -File backend/scripts/install.ps1`

Expected: bước 3 in ra `cuda available: True` và tên GPU `NVIDIA GeForce RTX 3070`. **Nếu in `False`, DỪNG và sửa trước khi đi tiếp** — đừng chạy tiếp rồi debug chất lượng model sau.

- [ ] **Step 5: Chạy smoke test với một tệp thật**

Lấy một đoạn tiếng Trung 1–2 phút (tự cắt bằng ffmpeg nếu có sẵn video dài):

Run: `.\.venv\Scripts\python.exe scripts\smoke_asr.py data\media\<ten>.wav zh`

Expected: in ra ít nhất 1 đoạn có `start`/`end`, và **RTF < 0.2** cho large-v3-turbo int8 trên 3070. Ghi số RTF và thời gian nạp lại — hai số này là đầu vào cho bảng benchmark ở GĐ1b.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts backend/README.md
git commit -m "chore(backend): script cai dat + smoke test model that + README"
```

---

## Nghiệm thu cuối Giai đoạn 1a

- [ ] `.venv\Scripts\python.exe -m pytest -q` → tất cả PASS
- [ ] `python run_api.py` → API sống ở `http://127.0.0.1:8620`
- [ ] `curl http://127.0.0.1:8620/api/registry` → có cả `asr` và `mt`
- [ ] Nạp một video thật qua `POST /api/sources/upload` → job `ingest` chạy → job `asr` chạy → `GET /api/transcripts` có transcript với timestamp
- [ ] `GET /api/transcripts/{id}/readability` trả về ít nhất một đoạn vượt ngưỡng nếu audio có câu dài
- [ ] `POST /api/export` rồi `GET /api/export/{job_id}/download` → tải được `.srt` mở đúng trong trình phát
- [ ] `GET /api/media/{source_id}` với `Range: bytes=0-99` trả `206` và đúng 100 byte
- [ ] Kill tiến trình giữa lúc `running`, khởi động lại → job thành `interrupted`, không treo
- [ ] Nạp 3 tệp cùng engine → `phase_switches` cho thấy model chỉ nạp **một** lần

---

## Tự soát kế hoạch

**Phủ spec:** đối chiếu từng mục của `2026-09-25-phu-de-lab-design.md`:

| Spec | Task |
|---|---|
| §3.1 phân tầng | T1 (test ranh giới), T7 (ports/adapters) |
| §4 cấu trúc thư mục | T1, T7 |
| §5 schema, version, state machine, log_tail, llm_calls | T2, T3, T7 |
| §5.3 stale theo version | T3, T18 |
| §5.4 phục hồi + huỷ hợp tác | T10 |
| §6 registry | T8 |
| §7.2 hàng đợi theo giai đoạn | T9 |
| §8.1 ingest | T11 |
| §8.2/§8.3 ASR + batched inference | T12, T13 |
| §8.4 tín hiệu tin cậy | T2 (`mark_suspect`), T12, T13 |
| §8.5 hậu xử lý segment | T4 |
| §8.8 QA tầng 1 + CPS | T6 |
| §9.2 ghim dòng, ảo hoá, N bản dịch, Ollama mất kết nối | **Kế hoạch 2** (frontend) |
| §9.3 bàn phím | **Kế hoạch 2** |
| §9.4 font self-host | **Kế hoạch 2** |
| §10 eval + benchmark | GĐ1b; T20 thu thập hai số đầu (RTF, thời gian nạp) |
| §11 API | T15–T18 |
| §11 endpoint media `Range` | T17 |
| §12 cài đặt | T20 |
| §13 kiểm thử | Toàn bộ; T19 E2E fake |
| §16 GĐ1a | Toàn bộ kế hoạch |

**Khoảng trống đã biết, nằm ngoài phạm vi:** mọi thứ ở cột "Kế hoạch 2", và toàn bộ GĐ1b/2/3 —
danh sách cụ thể, từng dòng một, ở bảng **"Đã biết, NGOÀI phạm vi GĐ1a"** cuối plan này.

**Quét placeholder:** không có "TBD"/"TODO". Hai chỗ cố tình để ngỏ và **có ghi rõ lý do**:
`TOKENS_PER_SOURCE_CHAR = 1.0` (phải đo ở GĐ1b) và `governor.can_run_parallel` trả `False`
(hành vi thật của GĐ1a, không phải chỗ trống).

**Nhất quán kiểu:** `Segment` dùng `t` cho bản dịch (khớp JSON §5.2) và `translation` chỉ là
tên cũ trong ghi chú — **không** xuất hiện trong code.

> **ĐÍNH CHÍNH (R28).** Bản đầu của đoạn này ghi: *"`phase_of` ở `domain/job_state.py` và
> `EngineSpec.phase_key` ở `registry.py` phải cho cùng chuỗi … cả hai đều dùng tiền tố `asr:`/`mt:`"*
> — **SAI**, và chính câu đó đã che mất một lỗi thật. `phase_key` bản đầu trả `f"{kind}:{id}"` với
> `kind ∈ {"asr","mt"}`, còn khoá hàng đợi thật do `phase_of(job_type, engine)` sinh ra với
> `job_type ∈ {ingest, asr, translate, export}` — **loại job dịch là `translate`, không phải `mt`**.
> ⇒ Lệch cả 4 engine MT; 4 engine ASR khớp nên hợp đồng trông như đang đúng nếu chỉ thử với ASR.
> Đúng ra phải viết: **`phase_key` phải UỶ QUYỀN cho `phase_of`**, chứ không phải "cùng dùng một tiền tố".
> Đã sửa ở T8 và trong mục §7.2 của spec. **Bài học:** "hai bên dùng cùng quy ước" là khẳng định
> phải **kiểm bằng test liên module**, không phải bằng cách đọc hai đoạn code cạnh nhau.

**Hai task đã sửa so với spec, có ghi chú tại chỗ:** thêm `domain/subtitle_format.py` (T14) và
`api/deps.py` (T15); thêm `Repos.list_sources()` (T15 Step 5) thay vì để route chọc vào
`_connect()`.

---

## Đã biết, NGOÀI phạm vi GĐ1a

> Mục đích: một review toàn nhánh đọc bảng này và **không đếm nhầm các mục HOÃN CÓ KẾ HOẠCH thành
> THIẾU SÓT**. Mọi dòng đã được đối chiếu với code ở HEAD `65c03b5`; lệnh grep/read dùng để
> chứng minh nằm trong `.superpowers/sdd/2026-09-25-giai-doan-1a-backend/cleanup-C-report.md`.
> Không dòng nào ở đây là việc bị bỏ quên, và không dòng nào có test — lý do "không test" ghi ngay
> trong cột Vì sao.

| # | Mục đã biết là NGOÀI phạm vi GĐ1a | Vì sao (một dòng) |
|---|---|---|
| 1 | **Toàn bộ frontend** (spec §9.2–§9.4: ghim dòng, bàn phím, font self-host) | Thuộc "Kế hoạch 2"; cây repo chỉ có `.superpowers/`, `backend/`, `docs/` — không có mã frontend nào. |
| 2 | **Workspace 2 / dịch máy (MT)** — không có handler `translate` | `backend/app/pipeline/` chỉ có `ingest.py`/`export.py`/`transcribe.py`; `app/main.py` (`build_components()`, khối `handlers`) cố ý đặt `auto_forward="0"` vì GĐ1a chưa có handler `translate`, nên job dịch (nếu ai bật) chỉ bị worker đánh `FAILED`. |
| 3 | **`GET /api/translations?transcript_id=` và `PATCH /api/translations/{id}`** (spec §11) | Không có route tương ứng trong `backend/app/api/` (grep `translations` chỉ thấy payload của `routes_transcripts.py`); workspace 2 ⇒ GĐ2. |
| 4 | **`GET`/`POST`/`PATCH /api/glossary`** (spec §11) | Grep `glossary` trong `backend/app/api/` → 0 hit (port `upsert_term` có sẵn nhưng chưa có route); glossary là workspace 2 ⇒ GĐ2. |
| 5 | **GĐ1b: subsystem `eval/` + benchmark** (spec §10, `backend/eval/report.md`) | `backend/eval/` chưa tồn tại và **cố ý không được tạo**; Task 20 chỉ thu hai số đầu (RTF, thời gian nạp) bằng smoke **thủ công**, không phải test tự động. |
| 6 | **Task ASS riêng (EX-02)** | `to_ass` join bằng `"\N"` rồi `_ass_escape` nhân đôi backslash ⇒ tệp ASS song ngữ in một `\` thừa: lỗi người-dùng-thấy-được, nhưng `task-14-brief.md:209` **buộc** giữ ở GĐ1a; sửa cùng adjudication brace-escaping ở task ASS riêng. |
| 7 | **`.vi` hardcode (EX-08)** | `backend/app/pipeline/export.py:35` (`artifact_name`) gắn `.vi` theo cờ `translated`, không theo ngôn ngữ đích — đúng khi Việt là đích duy nhất; khi có đích thứ hai thì đổi thành `payload.get("lang", "vi")`. Không test: hành vi hiện tại là hợp đồng đúng của GĐ1a. |
| 8 | **Bảng `translations` chưa có người ghi (DC-04)** | Schema (`schema.py`, `CREATE TABLE IF NOT EXISTS translations`) và đường ĐỌC qua port (`list_translations`, `ports/repos.py`) có, nhưng **không writer production** nào gọi `add_translation` (grep toàn `backend/` chỉ thấy định nghĩa `add_translation` trong `sqlite_repos.py` + test); GĐ1a chỉ đọc nếu có, GĐ2 mới ghi — viết test sẽ phải tự chế writer, tức test chính cái không tồn tại. |
| 9 | **`initial_prompt` lấy từ glossary (DOC-06/R40)** | `faster_whisper.py:89,96` đọc `spec.opts["initial_prompt"]` mà `registry.json` **không có khoá đó** (grep), nên "mồi thuật ngữ" của spec §8.2.4 không có đường vào; glossary là workspace 2 ⇒ GĐ2, và GĐ1a không có nguồn dữ liệu để test. |
| 10 | **API-05 (N7): `origin` thô + `fallback` một-đường** | Route upload (`routes_sources.py`, `repos.add_source(kind="file", origin=file.filename or final.name)`) lưu `origin` **nguyên vẹn kể cả thành phần đường dẫn** (`a/b/c.mp4`), còn `fallback` của `safe_basename` chỉ tới được khi `filename is None`; re-review kết luận **no action required** — quan sát, không phải defect, không nơi nào dùng `origin` làm đường dẫn (grep `origin` trong `backend/app`: chỉ gán/lưu/đọc để hiển thị). Không test: lý do là "quyết định giữ nguyên", không phải "thiếu test". |
| 11 | **`digest[:16]` thay vì `<sha256>` đầy đủ (API-06/R40, đối chiếu spec §8.1)** | Điều chỉnh **có ý thức**: tên tệp ngắn, 16 hex (64 bit) đủ chống trùng ở quy mô GĐ1a; đổi sang 64 hex là đổi hợp đồng `media_path` (R37/StubIngest, Task 19) nên phải làm cùng lúc. Quyết định được ghim bằng chú thích + khẳng định độ dài 16 trong `test_upload_still_accepts_a_normal_filename` — **không phải** lệch im lặng. |

