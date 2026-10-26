"""Giá khai trong registry + chi phí ƯỚC LƯỢNG của một bản dịch.

Ba luật, mỗi luật một lý do ĐO ĐƯỢC:

* giá là DỮ LIỆU (`opts` của hàng registry), không phải hằng số trong mã hay trong giao diện;
* `None` ≠ `0`: engine in-process (opus-mt) không có giá VÀ không báo token — một cột `$0,00`
  ở đó là hai câu nói dối ("đã đo và bằng không" + "miễn phí");
* đây là ƯỚC LƯỢNG: token ĐÃ ĐO × giá ĐÃ KHAI, không phải hoá đơn.
"""
from __future__ import annotations

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.domain.pricing import Price, cost_usd, price_of, prices_from_specs
from app.domain.staleness import translation_summary_json
from app.registry import EngineSpec


def _spec(engine_id: str, **opts) -> EngineSpec:
    return EngineSpec(id=engine_id, label=engine_id, kind="mt", runtime="inprocess",
                      model_ref="m", vram_mb=0, langs=("zh", "vi"),
                      capabilities={}, opts=dict(opts))


class _Hang:
    """Hàng `translations` tối thiểu mà builder đọc."""

    def __init__(self, engine: str, tokens_in=None, tokens_out=None):
        self.id = 1
        self.transcript_id = 1
        self.engine = engine
        self.target_lang = "vi"
        self.prompt_version = "p1"
        self.transcript_version = 1
        self.status = "done"
        self.created_at = "2026-10-26T00:00:00Z"
        self.qa_issues = []
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.duration_ms = None


def test_gia_doc_tu_opts_va_phai_du_ca_hai_ve():
    assert price_of(_spec("x", price_in_usd_per_mtok=0.15,
                          price_out_usd_per_mtok=0.6)) == Price(0.15, 0.6)
    assert price_of(_spec("x")) is None, "không khai giá ⇒ không có giá"
    assert price_of(_spec("x", price_in_usd_per_mtok=0.15)) is None, (
        "nửa bảng giá là nửa phép nhân ⇒ một con số SAI, không phải một con số thiếu"
    )


def test_prices_from_specs_bo_qua_engine_khong_co_gia():
    bang = prices_from_specs([_spec("opus-mt"), _spec("deepseek-web",
                                                      price_in_usd_per_mtok=0.15,
                                                      price_out_usd_per_mtok=0.6)])
    assert set(bang) == {"deepseek-web"}, bang


def test_cost_usd_bang_khong_khi_thieu_mot_ve_so_lieu():
    gia = {"e": Price(0.15, 0.6)}
    assert cost_usd("e", 1_000_000, 1_000_000, gia) == 0.75
    assert cost_usd("e", 1000, 2000, gia) == (1000 * 0.15 + 2000 * 0.6) / 1e6
    # Ba đường "không tính được" đều là None, không phải 0.0:
    assert cost_usd("e", None, 2000, gia) is None, "thiếu token vào"
    assert cost_usd("e", 1000, None, gia) is None, "thiếu token ra"
    assert cost_usd("opus-mt", 1000, 2000, gia) is None, "engine không khai giá"
    assert cost_usd("e", 1000, 2000, None) is None, "không có bảng giá"
    assert cost_usd("e", 1000, 2000, {}) is None


def test_builder_gan_cost_usd_va_de_none_khi_khong_tinh_duoc():
    gia = {"deepseek-web": Price(0.15, 0.6)}
    co = translation_summary_json(_Hang("deepseek-web", 24_195, 17_212),
                                  current_version=1, prices=gia)
    assert abs(co["cost_usd"] - (24_195 * 0.15 + 17_212 * 0.6) / 1e6) < 1e-12, co["cost_usd"]
    khong = translation_summary_json(_Hang("opus-mt"), current_version=1, prices=gia)
    assert khong["cost_usd"] is None, (
        "engine in-process không báo token ⇒ `cost_usd` phải là null, KHÔNG phải 0"
    )


def test_route_tra_khoa_cost_usd_co_mat(tmp_path):
    """Route phải ĐI QUA builder có bảng giá: thiếu khoá là giao diện không có gì để vẽ."""
    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    specs = [_spec("deepseek-web", price_in_usd_per_mtok=0.15,
                   price_out_usd_per_mtok=0.6)]
    app = create_app(repos=repos, specs=specs, media_dir=tmp_path / "m",
                     out_dir=tmp_path / "o")
    sid = repos.add_source(kind="file", origin="a", media_path="m", lang="zh")
    repos.add_transcript(source_id=sid, engine="fw", lang="zh",
                         segments=[])
    tid = repos.add_translation(transcript_id=1, transcript_version=1,
                                engine="deepseek-web", target_lang="vi",
                                segments=[], prompt_version="p1")
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        r = c.get(f"/api/translations/{tid}")
    assert r.status_code == 200, r.text
    assert "cost_usd" in r.json(), (
        "route phải trả `cost_usd` (kể cả khi null) — thiếu khoá là hình dạng thứ hai cho cùng "
        "một câu hỏi, và client sẽ phải nhớ"
    )
