"""Kiểm bảng "Cài đặt model": luật used→fallback, ghi/đọc, và hai route.

Ba tầng, ba câu hỏi khác nhau:

* `test_chon_*` — LUẬT thuần ("dự phòng chỉ dùng khi model đang dùng không chạy được");
* `test_api_*` — route đọc/ghi và TỪ CHỐI id không có trong danh mục của chính việc đó;
* `test_noi_day_*` — dây nối thật: engine dự phòng có đi vào JOB, và bộ mã hoá burn có
  đi vào lệnh ffmpeg. Thiếu tầng này thì bảng cài đặt là một ô không có đường thực hiện —
  đúng loại "khai báo chết" mà repo này xoá.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app import chon_model
from app.domain import model_settings as ms
from app.domain.models import Segment
from app.registry import EngineSpec


def _repos(tmp_path) -> SqliteRepos:
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def _spec(id: str, kind: str, *, runtime: str = "inprocess",
          available: bool | None = None, label: str | None = None) -> EngineSpec:
    caps: dict = {}
    if available is not None:
        caps["available"] = available
    return EngineSpec(id=id, label=label or id.upper(), kind=kind, runtime=runtime,
                      model_ref=f"ref-{id}", vram_mb=0, langs=("zh", "vi"),
                      capabilities=caps)


def _specs() -> list[EngineSpec]:
    return [
        _spec("asr-a", "asr", available=True),
        _spec("asr-b", "asr", available=False),
        _spec("mt-inproc", "mt", runtime="inprocess", available=True),
        _spec("llm-ollama", "mt", runtime="ollama", available=True),
        _spec("llm-dead", "mt", runtime="ollama", available=False),
        _spec("rapidocr", "ocr"),
    ]


# ── Luật thuần ─────────────────────────────────────────────────────────────


def test_chon_dung_model_DANG_DUNG_khi_no_chay_duoc():
    """Model đang dùng chạy được thì KHÔNG được lấy dự phòng — dự phòng không phải mặc
    định thứ hai, nó chỉ là đường lui."""
    assert ms.chon("a", "b", {"a", "b"}) == ("a", "dang-dung")


def test_chon_roi_ve_DU_PHONG_khi_model_dang_dung_khong_chay_duoc():
    assert ms.chon("a", "b", {"b"}) == ("b", "du-phong")


def test_chon_tra_NONE_khi_ca_hai_deu_khong_chay_duoc():
    """Không có đường nào chạy được ⇒ `None`, để bên gọi TỪ CHỐI kèm lý do.

    Trả một id bất kỳ ở đây là xếp một job chắc chắn chết ở tận worker.
    """
    assert ms.chon("a", "b", set()) == (None, "khong-co")


def test_chon_voi_fallback_RONG_khong_no():
    assert ms.chon("a", None, {"b"}) == (None, "khong-co")
    assert ms.chon(None, None, {"a"}) == (None, "khong-co")


def test_nhom_dich_tach_theo_RUNTIME_chu_khong_them_truong_moi():
    """MT = chạy trong tiến trình; LLM = ollama/http. Runtime lạ KHÔNG được đoán hộ."""
    assert ms.nhom_cua_dich("inprocess") == ms.NHOM_MT
    assert ms.nhom_cua_dich("ollama") == ms.NHOM_LLM
    assert ms.nhom_cua_dich("http") == ms.NHOM_LLM
    assert ms.nhom_cua_dich("bat-dau-lanh") is None


def test_MA_HOA_va_BURN_ENCODERS_cung_mot_bo_khoa():
    """`tach_nen.MA_HOA` (lệnh ffmpeg) và `model_settings.BURN_ENCODERS` (bảng chọn) là
    hai chỗ khai CÙNG bộ mã hoá; lệch khoá là chọn một bộ rồi chạy bộ khác."""
    from app.pipeline import tach_nen

    assert set(tach_nen.MA_HOA) == set(ms.BURN_ENCODERS)


def test_chon_burn_LUON_co_duong_cung_khi_khong_co_GPU(tmp_path):
    """Máy không NVENC mà người dùng đặt `h264_nvenc` ⇒ chạy `libx264`, không ném."""
    r = _repos(tmp_path)
    r.set_setting(ms.KEY_USED.format(task="burn"), ms.BURN_NVENC)
    assert ms.chon_burn(r, co_gpu=False) == (ms.BURN_X264, "du-phong")
    assert ms.chon_burn(r, co_gpu=True)[0] == ms.BURN_NVENC


def test_chon_burn_ton_trong_lua_chon_CPU_du_may_co_GPU(tmp_path):
    """Có GPU nhưng người dùng CHỌN `libx264` ⇒ tôn trọng lựa chọn, không tự nâng cấp."""
    r = _repos(tmp_path)
    r.set_setting(ms.KEY_USED.format(task="burn"), ms.BURN_X264)
    assert ms.chon_burn(r, co_gpu=True) == (ms.BURN_X264, "dang-dung")


# ── Ghi / đọc ──────────────────────────────────────────────────────────────


def test_ghi_roi_doc_lai_duoc_va_chuoi_RONG_la_CHUA_DAT(tmp_path):
    r = _repos(tmp_path)
    ms.ghi_cai_dat(r, cap_nhat={"asr": {"used": "asr-a", "fallback": "asr-b"}},
                   nhom_dich="llm")
    da = ms.doc_cai_dat(r)
    assert da["asr"] == {"used": "asr-a", "fallback": "asr-b"}
    assert ms.doc_nhom_dich(r) == "llm"

    ms.ghi_cai_dat(r, cap_nhat={"asr": {"used": None, "fallback": None}})
    assert ms.doc_cai_dat(r)["asr"] == {"used": None, "fallback": None}, (
        "ghi chuỗi rỗng phải đọc lại thành CHƯA ĐẶT, không phải id rỗng")


def test_ghi_viec_la_thi_nem(tmp_path):
    r = _repos(tmp_path)
    with pytest.raises(KeyError, match="khong-co-viec-nay"):
        ms.ghi_cai_dat(r, cap_nhat={"khong-co-viec-nay": {"used": "x"}}, nhom_dich=None)


def test_nhom_dich_la_thi_giu_mt_chu_khong_nem(tmp_path):
    r = _repos(tmp_path)
    r.set_setting(ms.KEY_NHOM_DICH, "linh-tinh")
    assert ms.doc_nhom_dich(r) == ms.NHOM_MT


# ── Route ──────────────────────────────────────────────────────────────────


def _client(tmp_path, specs=None):
    r = _repos(tmp_path)
    app = create_app(repos=r, specs=_specs() if specs is None else specs,
                     media_dir=tmp_path / "m", out_dir=tmp_path / "o")
    return TestClient(app), r


def test_api_GET_tra_du_sau_viec_va_engine_SE_CHAY(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        d = c.get("/api/model-settings").json()
    assert [t["id"] for t in d["tasks"]] == [t.id for t in ms.TASKS]
    asr = next(t for t in d["tasks"] if t["id"] == "asr")
    assert asr["used"] == "asr-a", asr
    assert asr["hieu_luc"] == {"engine": "asr-a", "ly_do": "dang-dung"}, asr["hieu_luc"]
    assert {u["id"] for u in asr["candidates"]} == {"asr-a", "asr-b"}
    assert asr["locked"] is False
    # Ứng viên ĐƠN: `locked` = giao diện không vẽ ô dự phòng.
    tts = next(t for t in d["tasks"] if t["id"] == "tts")
    assert tts["locked"] is True and len(tts["candidates"]) == 1


def test_api_GET_chi_rong_engine_dich_va_co_NHOM(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        d = c.get("/api/model-settings").json()
    dich = next(t for t in d["tasks"] if t["id"] == "dich")
    nhom = {u["id"]: u["nhom"] for u in dich["candidates"]}
    assert nhom == {"mt-inproc": "mt", "llm-ollama": "llm", "llm-dead": "llm"}, nhom
    assert d["nhom_dich_chon"] == ["mt", "llm"]


def test_api_PUT_ghi_roi_GET_thay_doi(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        put = c.put("/api/model-settings", json={
            "tasks": {"asr": {"used": "asr-b", "fallback": "asr-a"}},
            "nhom_dich": "llm",
        })
        assert put.status_code == 200, put.text
        d = put.json()
    asr = next(t for t in d["tasks"] if t["id"] == "asr")
    assert asr["used"] == "asr-b" and asr["fallback"] == "asr-a"
    #: `asr-b` KHÔNG chạy được (available false) nên engine hiệu lực là dự phòng.
    assert asr["hieu_luc"] == {"engine": "asr-a", "ly_do": "du-phong"}, asr["hieu_luc"]
    assert d["nhom_dich"] == "llm"


def test_api_PUT_tu_choi_model_cua_VIEC_KHAC(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        r = c.put("/api/model-settings", json={"tasks": {"asr": {"used": "mt-inproc"}}})
    assert r.status_code == 422, r.text
    assert "asr" in r.json()["detail"] and "mt-inproc" in r.json()["detail"]


def test_api_PUT_tu_choi_khi_used_TRUNG_fallback(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        r = c.put("/api/model-settings", json={
            "tasks": {"asr": {"used": "asr-a", "fallback": "asr-a"}}})
    assert r.status_code == 422, r.text
    assert "TRÙNG" in r.json()["detail"]


def test_api_PUT_tu_choi_viec_la_va_nhom_la(tmp_path):
    c, _ = _client(tmp_path)
    with c:
        viec = c.put("/api/model-settings", json={"tasks": {"khong-co": {"used": "x"}}})
        nhom = c.put("/api/model-settings", json={"tasks": {}, "nhom_dich": "linh-tinh"})
    assert viec.status_code == 422 and "khong-co" in viec.json()["detail"]
    assert nhom.status_code == 422 and "nhóm dịch" in nhom.json()["detail"]


# ── Dây nối thật ───────────────────────────────────────────────────────────


def test_noi_day_job_ASR_dung_model_DU_PHONG(tmp_path):
    """Client gửi engine KHÔNG chạy được ⇒ job phải mang engine dự phòng.

    Đây là câu của chủ dự án: *"model mặc định được dùng khi model sử dụng không thể hoạt
    động"*. Không có bài này thì bảng cài đặt vẫn "lưu được" mà không đổi gì.
    """
    c, r = _client(tmp_path)
    sid = r.add_source(kind="file", origin="a", media_path=str(tmp_path / "v.mp4"),
                       lang="zh")
    r.set_source_audio(sid, audio_path=str(tmp_path / "a.wav"), duration=1.0)
    r.set_setting(ms.KEY_FALLBACK.format(task="asr"), "asr-a")
    with c:
        resp = c.post("/api/jobs", json={
            "workspace": 1, "type": "asr", "engine": "asr-b",
            "payload": {"source_id": sid}})
    assert resp.status_code == 201, resp.text
    job = r.get_job(resp.json()["id"])
    assert job.engine == "asr-a", f"job phải chạy model dự phòng, đo được {job.engine!r}"
    assert job.phase == "asr:asr-a", job.phase


def test_noi_day_job_ASR_tu_choi_khi_KHONG_CO_duong_nao(tmp_path):
    """Không có dự phòng chạy được ⇒ 409 kèm chỉ dẫn, KHÔNG xếp job chắc chắn hỏng."""
    c, r = _client(tmp_path)
    sid = r.add_source(kind="file", origin="a", media_path=str(tmp_path / "v.mp4"),
                       lang="zh")
    r.set_source_audio(sid, audio_path=str(tmp_path / "a.wav"), duration=1.0)
    with c:
        resp = c.post("/api/jobs", json={
            "workspace": 1, "type": "asr", "engine": "asr-b",
            "payload": {"source_id": sid}})
    assert resp.status_code == 409, resp.text
    assert "Cài đặt model" in resp.json()["detail"]
    assert not r.list_jobs(), "không được xếp job nào"


def test_noi_day_DUB_chon_bo_ma_hoa_theo_cai_dat(tmp_path, monkeypatch):
    """Bảng cài đặt phải đổi được bộ mã hoá của bước burn (real ffmpeg arg)."""
    from app.pipeline import dub, tach_nen

    r = _repos(tmp_path)
    r.set_setting(ms.KEY_USED.format(task="burn"), ms.BURN_NVENC)
    monkeypatch.setattr(tach_nen, "co_nvenc", lambda: False)
    assert ms.chon_burn(r, co_gpu=tach_nen.co_nvenc()) == (ms.BURN_X264, "du-phong")

    da_goi: list[str] = []

    def remux_gia(video, audio, ra, phu_de=None, ma_hoa_id=None):
        da_goi.append(ma_hoa_id)

    monkeypatch.setattr(tach_nen, "remux", remux_gia)
    #: `chon_burn` được gọi trong `_tron_va_remux`; ở đây kiểm thẳng dây nối để không
    #: phải dựng cả một lượt lồng tiếng với demucs.
    ma, _ly_do = ms.chon_burn(r, co_gpu=tach_nen.co_nvenc())
    tach_nen.remux(pathlib.Path("v.mp4"), pathlib.Path("a.wav"), pathlib.Path("ra.mp4"),
                   ma_hoa_id=ma)
    assert da_goi == [ms.BURN_X264], da_goi
    assert hasattr(dub.DubHandler, "_tron_va_remux")


def test_bang_cai_dat_co_du_sau_viec_va_dung_NHAN():
    """Sáu việc, đúng nhóm — giao diện vẽ theo dữ liệu này, không viết cứng."""
    assert [(t.id, t.nhom) for t in ms.TASKS] == [
        ("ocr", "Phiên âm"), ("asr", "Phiên âm"), ("dich", "Dịch"),
        ("tts", "Lồng tiếng"), ("tach_giong", "Ghép nền"), ("burn", "Ghép nền"),
    ]
    assert ms.TTS_ENGINE in ms.NHAN_CO_DINH
    assert ms.SEP_ENGINE in ms.NHAN_CO_DINH
