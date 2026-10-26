"""Tiến độ của job `asr` phải NHÍCH, và lần đầu tải model phải NÓI RA.

Sự cố ĐO ĐƯỢC trên stack thật (2026-10-26): job `asr` với `fw-large-v3` đứng ở **15%** suốt
**6 phút**, rồi bị một lượt dựng lại container cắt ngang. Hai nguyên nhân, cả hai đều là lỗi
hiển thị chứ không phải lỗi bóc băng:

1. `progress` của handler chỉ có ba nấc — `0` → `0.15` (nạp xong engine) → `1.0`. Với clip 20:49
   trên `fw-large-v3`, "đang bóc băng" là hàng phút của một thanh không nhích.
2. Lần ĐẦU dùng một engine là một lượt **TẢI MODEL** (`fw-large-v3` = 2,9 GB), không phải một
   lượt bóc băng — và job chỉ nói "nạp engine", nên không ai phân biệt được "đang tải 2,9 GB"
   với "treo". Đo được: `stat /models/models--Systran--faster-whisper-large-v3` = 10:14:53,
   tức thư mục đó đang được ghi trong đúng 6 phút đứng im kia.
"""
from __future__ import annotations

import sys
import types

import pytest

import app.adapters.asr.faster_whisper as fw_module
from app.adapters.asr.faster_whisper import FasterWhisperEngine
from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain import job_state as js
from app.domain.models import Job, Segment
from app.pipeline.transcribe import TranscribeHandler
from app.registry import EngineSpec


def _spec(model_ref: str = "large-v3", **opts) -> EngineSpec:
    return EngineSpec(id="fw-large-v3", label="FW large v3", kind="asr",
                      runtime="inprocess", model_ref=model_ref, vram_mb=3200,
                      langs=("zh", "en"), capabilities={}, opts=dict(opts))


class _Doan:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = -0.2
        self.no_speech_prob = 0.01
        self.words = None


class _Model:
    """`WhisperModel` giả: trả (iterator, info) ĐÚNG hình dạng faster-whisper."""

    def __init__(self, doan: list[_Doan], duration: float) -> None:
        self._doan = doan
        self._info = types.SimpleNamespace(duration=duration)

    def transcribe(self, audio_path, **kwargs):
        return iter(self._doan), self._info


# ---------------------------------------------------------------------------
# Adapter: callback tiến độ
# ---------------------------------------------------------------------------

def test_adapter_bao_tien_do_theo_doan_va_khong_vuot_tong_thoi_luong(monkeypatch):
    """Mỗi lần báo là `(giây đã tới, tổng giây)`; giá trị không vượt tổng."""
    monkeypatch.setattr(fw_module, "_PROGRESS_EVERY_S", 0.0)  # tắt throttle cho phép đo
    engine = FasterWhisperEngine(
        _spec(),
        model_factory=lambda *a, **k: _Model(
            [_Doan(0.0, 2.0, "你好"), _Doan(2.0, 5.0, "世界"), _Doan(5.0, 9.0, "再见")],
            duration=9.0),
    )
    goi: list[tuple[float, float]] = []
    segs = engine.transcribe("a.wav", "zh", on_progress=lambda a, b: goi.append((a, b)))

    assert len(segs) == 3
    assert goi == [(2.0, 9.0), (5.0, 9.0), (9.0, 9.0)], goi


def test_adapter_bao_tien_do_bi_throttle(monkeypatch):
    """446 đoạn trong một clip không được sinh 446 lượt ghi DB + sự kiện SSE."""
    monkeypatch.setattr(fw_module, "_PROGRESS_EVERY_S", 2.0)
    engine = FasterWhisperEngine(
        _spec(),
        model_factory=lambda *a, **k: _Model([_Doan(0.0, 1.0, "a")] * 5, duration=5.0),
    )
    goi: list[tuple[float, float]] = []
    engine.transcribe("a.wav", "zh", on_progress=lambda a, b: goi.append((a, b)))
    assert len(goi) == 1, (
        f"năm đoạn trong cùng một phần nghìn giây phải gộp còn MỘT lần báo, đo được {goi}"
    )


def test_khong_co_callback_thi_khong_no():
    """`on_progress` là TUỲ CHỌN: mọi caller cũ (và mọi double trong test) không truyền nó."""
    engine = FasterWhisperEngine(_spec(), model_factory=lambda *a, **k: _Model(
        [_Doan(0.0, 1.0, "a")], duration=1.0))
    assert len(engine.transcribe("a.wav", "zh")) == 1


# ---------------------------------------------------------------------------
# Adapter: model đã có trên đĩa chưa
# ---------------------------------------------------------------------------

def _gia_hub(monkeypatch, *, tra=None, nem=None):
    """Giả `huggingface_hub` + `huggingface_hub.errors` cùng lúc (adapter import cả hai)."""
    goi: list[dict] = []
    that = types.ModuleType("huggingface_hub")

    def snapshot_download(repo, **kwargs):
        goi.append({"repo": repo, **kwargs})
        if nem is not None:
            raise nem
        return tra or "/cache"

    that.snapshot_download = snapshot_download
    loi = types.ModuleType("huggingface_hub.errors")

    class LocalEntryNotFoundError(OSError):
        pass

    loi.LocalEntryNotFoundError = LocalEntryNotFoundError
    that.errors = loi
    monkeypatch.setitem(sys.modules, "huggingface_hub", that)
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors", loi)
    return goi, LocalEntryNotFoundError


def test_model_cached_true_va_giai_bi_danh_thanh_repo_that(monkeypatch):
    """`spec.model_ref` là BÍ DANH: tra cache bằng bí danh là tra sai thư mục.

    Đo được ngay ở lượt đầu của bản vá: `large-v3-turbo` (bí danh) tra ra `models--large-v3-turbo`
    không tồn tại, nên MỌI job bị báo "chưa có model" dù model 1,6 GB nằm sẵn trên đĩa.
    """
    goi, _loi = _gia_hub(monkeypatch)
    from faster_whisper.utils import _MODELS
    assert FasterWhisperEngine(_spec(model_ref="large-v3-turbo")).model_cached() is True
    assert goi[0]["repo"] == _MODELS["large-v3-turbo"] != "large-v3-turbo", goi[0]


def test_model_cached_false_khi_cache_thieu(monkeypatch):
    """`LocalEntryNotFoundError` là câu "CHẮC CHẮN không có" — chỉ nó mới được thành `False`."""
    _goi, Loi = _gia_hub(monkeypatch, nem=None)
    that = sys.modules["huggingface_hub"]
    that.snapshot_download = lambda *a, **k: (_ for _ in ()).throw(Loi("thiếu"))
    assert FasterWhisperEngine(_spec()).model_cached() is False


def test_model_cached_none_khi_loi_la_hoac_thieu_thu_vien(monkeypatch):
    """KHÔNG BIẾT phải là `None`, không phải `False`: một câu "chưa có model" SAI tệ hơn im."""
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    assert FasterWhisperEngine(_spec()).model_cached() is None

    _gia_hub(monkeypatch, nem=RuntimeError("lỗi lạ"))
    assert FasterWhisperEngine(_spec()).model_cached() is None


# ---------------------------------------------------------------------------
# Handler: ba đường tiến độ + câu "đang tải lần đầu"
# ---------------------------------------------------------------------------

class _EngineCoTienDo:
    """Engine giả NHẬN `on_progress` — chữ ký giống adapter thật sau bản vá."""

    def __init__(self, spec, *, cached: bool = True) -> None:
        self.engine_id = spec.id
        self._cached = cached
        self.nhan = False

    def model_cached(self) -> bool:
        return self._cached

    def transcribe(self, audio_path: str, lang: str, *, on_progress=None):
        self.nhan = True
        if on_progress is not None:
            on_progress(30.0, 120.0)
            on_progress(120.0, 120.0)
        return [Segment(i=0, start=0.0, end=120.0, text="你好")]

    def release(self) -> None:
        pass


class _EngineKhongTienDo:
    """Engine giả KHÔNG nhận `on_progress` — mọi adapter cũ + mọi double hiện có."""

    def __init__(self, spec) -> None:
        self.engine_id = spec.id

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        return [Segment(i=0, start=0.0, end=4.0, text="世界")]

    def release(self) -> None:
        pass


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


def _chay(repos, tmp_path, engine, *, engine_id="fw-large-v3"):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    sid = repos.add_source(kind="file", origin="a", media_path=str(tmp_path / "a.mp4"),
                           lang="zh", audio_path=str(wav), duration=120.0)
    specs = [_spec(), EngineSpec(id="mt-x", label="MT", kind="mt", runtime="inprocess",
                                 model_ref="x", vram_mb=0, langs=("zh", "vi"),
                                 capabilities={}, opts={})]
    handler = TranscribeHandler(repos, specs, lambda spec: engine, workdir=tmp_path)
    repos.set_setting("auto_forward", "0")
    job = Job(id=1, workspace=1, type="asr", engine=engine_id,
              phase=js.phase_of("asr", engine_id), payload={"source_id": sid},
              created_at="2026-10-26T00:00:00Z")
    logs: list[tuple[float, str]] = []
    handler.run(job, lambda p, line: logs.append((p, line)))
    return logs


def test_handler_map_tien_do_doan_ra_khoang_015_089(repos, tmp_path):
    logs = _chay(repos, tmp_path, _EngineCoTienDo(_spec()))
    tiendo = [(p, s) for p, s in logs if "bóc băng a.wav:" in s]
    assert tiendo, f"phải có dòng tiến độ theo đoạn, đo được {logs}"
    # 30/120 = 25% ⇒ 0,15 + 0,74*0,25 = 0,335 ; 120/120 ⇒ 0,89 (trần)
    assert [round(p, 3) for p, _ in tiendo] == [0.335, 0.89], tiendo
    assert "0:30 / 2:00 (25%)" in tiendo[0][1], tiendo[0][1]
    assert tiendo[-1][0] < 0.9, "phải chừa chỗ cho ba bước sau (lưu/forward/xong)"


def test_handler_van_chay_voi_engine_khong_nhan_on_progress(repos, tmp_path):
    """Bản vá tiến độ KHÔNG được làm sập engine không có `on_progress`."""
    logs = _chay(repos, tmp_path, _EngineKhongTienDo(_spec()))
    assert logs[-1][0] == 1.0
    assert repos.list_transcripts()[0].segments[0].text == "世界"


def test_handler_noi_ra_khi_model_chua_co_tren_dia(repos, tmp_path):
    """Lần đầu dùng engine là một lượt TẢI MODEL — phải nói trước, không để thanh đứng im."""
    logs = _chay(repos, tmp_path, _EngineCoTienDo(_spec(), cached=False))
    dau = logs[0][1]
    assert "chưa có model" in dau and "không phải treo" in dau, dau


def test_handler_noi_nap_engine_khi_model_da_co(repos, tmp_path):
    logs = _chay(repos, tmp_path, _EngineCoTienDo(_spec(), cached=True))
    assert logs[0][1] == "nạp engine fw-large-v3", logs[0][1]
