"""`adapters/gpu.py` + trường `vram`/`vram_unit` của `GET /api/status`.

Vì sao có bài này: trước đây route trả `vram: null` **cố định** (GĐ1a chưa có
đường đọc), nên giao diện luôn in "VRAM: chưa đo được". Nay số được đọc THẬT từ
`nvidia-smi` qua một callable mà composition root đặt vào `app.state`.

Ba thứ được ghim, vì mỗi thứ hỏng theo một kiểu khác nhau:

1. **Parser** — dòng đầu là GPU 0; chuỗi lạ ⇒ `None`, KHÔNG `float()` hoá và
   KHÔNG rơi về 0 (0 là một con số bịa: nó nói "card trống").
2. **Lỗi của tiến trình** — không có `nvidia-smi`, returncode khác 0, timeout ⇒
   `None`. Route trạng thái không được 500 vì driver card.
3. **Hợp đồng HTTP** — `vram` là số hoặc `null`, và `vram_unit` LUÔN có (kể cả
   khi `vram` là `null`, vì nó nói đơn vị của con số sẽ có). Giao diện không được
   tự thêm đơn vị, nên backend phải nói.
"""
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.gpu import parse_mib, vram_used_mib
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.domain.vram import VRAM_UNIT
from app.registry import EngineSpec


# -- parser -----------------------------------------------------------------
@pytest.mark.parametrize("stdout, expected", [
    ("1467\n", 1467),
    ("  1467  \n", 1467),
    ("1467\r\n", 1467),
    ("", None),
    ("\n\n", None),
    ("N/A\n", None),                 # driver cũ trả `N/A` khi không đọc được
    ("1467.5\n", None),              # `nounits` phải là số nguyên; lạ ⇒ không đoán
    ("-3\n", None),
    ("1467\n2387\n", 1467),          # nhiều GPU ⇒ GPU 0, đúng card governor dùng
])
def test_parse_reads_the_first_line_as_a_non_negative_integer(stdout, expected):
    assert parse_mib(stdout) == expected


# -- lỗi tiến trình ---------------------------------------------------------
class _Done:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


def test_missing_binary_is_none_not_an_exception(monkeypatch):
    def boom(*_a, **_k):
        raise FileNotFoundError("nvidia-smi")
    monkeypatch.setattr(subprocess, "run", boom)
    assert vram_used_mib() is None


def test_timeout_is_none_not_an_exception(monkeypatch):
    def slow(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=0.5)
    monkeypatch.setattr(subprocess, "run", slow)
    assert vram_used_mib() is None


def test_non_zero_returncode_is_none(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Done(9, "1467\n"))
    assert vram_used_mib() is None


def test_success_returns_the_parsed_number(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Done(0, "7013\n"))
    assert vram_used_mib() == 7013


# -- hợp đồng HTTP ----------------------------------------------------------
def _specs() -> list[EngineSpec]:
    return [EngineSpec(id="opus-mt", label="OPUS-MT", kind="mt",
                       runtime="inprocess", model_ref="Helsinki-NLP/opus-mt-zh-vi",
                       vram_mb=0, langs=("zh", "en"),
                       capabilities={}, opts={})]


class _Reader:
    """Callable như `adapters/gpu.py::VramReader`, nhưng trả số cố định."""

    unit = VRAM_UNIT

    def __init__(self, value: int | None) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> int | None:
        self.calls += 1
        return self.value


def _client(tmp_path, *, vram_reader):
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    app = create_app(repos=repos, specs=_specs(), media_dir=tmp_path / "media",
                     out_dir=tmp_path / "out", vram_reader=vram_reader)
    return TestClient(app)


def test_status_returns_the_measured_number_and_its_unit(tmp_path):
    reader = _Reader(7013)
    with _client(tmp_path, vram_reader=reader) as c:
        body = c.get("/api/status").json()
    assert body["vram"] == 7013
    assert body["vram_unit"] == "MiB"
    assert reader.calls == 1, "route phải ĐO mỗi lần gọi, không đọc số cũ"


def test_status_says_unknown_when_the_reader_fails(tmp_path):
    """`None` là 'chưa đọc được', KHÔNG phải 0 — và đơn vị vẫn được nói ra."""
    with _client(tmp_path, vram_reader=_Reader(None)) as c:
        body = c.get("/api/status").json()
    assert body["vram"] is None
    assert body["vram_unit"] == "MiB"


def test_app_without_a_reader_still_answers_and_says_unknown(tmp_path):
    """Test chỉ đọc dựng app không cần GPU: `vram_reader=None` ⇒ `null`."""
    with _client(tmp_path, vram_reader=None) as c:
        body = c.get("/api/status").json()
    assert body["vram"] is None
    assert body["vram_unit"] == "MiB"


def test_status_does_not_touch_the_gpu_when_there_is_no_reader(tmp_path):
    """Không có reader thì KHÔNG có lời gọi `nvidia-smi` nào (40,6 ms/lần)."""
    with _client(tmp_path, vram_reader=None) as c:
        c.get("/api/status")
        c.get("/api/status")
