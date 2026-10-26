"""`GET /api/stats/tokens` — token/thời lượng theo engine, đọc từ `llm_calls`.

Vì sao có bài này: mọi con số đã được GHI từ trước (`TranslateHandler._record_call` ghi một hàng
`llm_calls` cho đúng một lần chạm engine), nhưng trước route này thì câu hỏi "engine nào tốn bao
nhiêu token" chỉ trả lời được bằng cách mở DB bằng tay — đo được trên app thật: 18 lời gọi
`deepseek-web` có đủ token mà không chỗ nào trong API/UI đọc ra.

Hai luật được ghim ở đây:

* **`None` ≠ `0`**: `opus-mt` chạy trong tiến trình nên không có token; đổi "không đo được" thành
  `0` là nói dối rằng engine đó đã báo một con số.
* **`ok_calls` tách khỏi `calls`**: một lời gọi hỏng vẫn tốn token, nên gộp chúng vào một con số
  làm số token không giải thích được.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.api.routes_stats import token_stats
from app.registry import EngineSpec

_SPEC = EngineSpec(id="opus-mt", label="OPUS", kind="mt", runtime="inprocess",
                   model_ref="m", vram_mb=0, langs=("zh", "vi"),
                   capabilities={}, opts={})


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def _goi(repos, engine, *, model_ref="m", tin=None, tout=None, ms=None, ok=True):
    repos.add_llm_call(job_id=None, engine=engine, model_ref=model_ref,
                       prompt_version="p1", tokens_in=tin, tokens_out=tout,
                       duration_ms=ms, ok=ok, error=None if ok else "hỏng")


def test_db_rong_tra_none_chu_khong_phai_khong(repos):
    """Chưa có lời gọi nào ⇒ `calls: 0` nhưng các tổng là `null`, không phải `0`."""
    kq = token_stats(repos=repos)
    assert kq["engines"] == []
    assert kq["total"]["calls"] == 0
    assert kq["total"]["tokens_in"] is None
    assert kq["total"]["tokens_out"] is None
    assert kq["total"]["duration_ms"] is None


def test_gop_theo_engine_va_tach_so_lan_hong(repos):
    """Hai engine, một cái không báo token (như `opus-mt`), một cái có."""
    _goi(repos, "deepseek-web", model_ref="deepseek-web",
         tin=100, tout=40, ms=1500, ok=True)
    _goi(repos, "deepseek-web", model_ref="deepseek-web",
         tin=200, tout=60, ms=2500, ok=False)
    _goi(repos, "opus-mt", model_ref="Helsinki-NLP/opus-mt-zh-vi", ok=True)

    kq = token_stats(repos=repos)
    theo_id = {r["engine"]: r for r in kq["engines"]}

    ds = theo_id["deepseek-web"]
    assert ds["calls"] == 2 and ds["ok_calls"] == 1, ds
    assert (ds["tokens_in"], ds["tokens_out"]) == (300, 100), ds
    assert ds["duration_ms"] == 4000, ds

    opus = theo_id["opus-mt"]
    assert opus["calls"] == 1 and opus["ok_calls"] == 1, opus
    assert opus["tokens_in"] is None and opus["tokens_out"] is None, (
        "engine in-process không báo token ⇒ `null`, KHÔNG phải 0"
    )

    assert kq["total"]["calls"] == 3
    assert kq["total"]["ok_calls"] == 2
    assert (kq["total"]["tokens_in"], kq["total"]["tokens_out"]) == (300, 100)
    assert kq["total"]["duration_ms"] == 4000


def test_route_co_mat_va_tra_200(repos, tmp_path):
    """Route phải được ĐĂNG KÝ trong app thật — một hàm đúng mà không có route là vô hình."""
    app = create_app(repos=repos, specs=[_SPEC], media_dir=tmp_path / "m",
                     out_dir=tmp_path / "o")
    with TestClient(app) as c:
        r = c.get("/api/stats/tokens")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engines"] == [] and body["total"]["calls"] == 0
