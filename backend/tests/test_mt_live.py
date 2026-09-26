"""Test CHẠM model thật. Mặc định BỊ BỎ QUA để máy khác không đỏ oan.

Chạy: ``python -B -m pytest -m live``

Vì sao tách khỏi suite mặc định: mấy bài này nạp ~300 MB weight OPUS-MT và gọi
Ollama thật. Máy chưa cài không được đỏ vì lý do không liên quan tới code — đó là
lý do marker ``live`` tồn tại, và lý do ``pytest.ini`` đặt ``-m "not live"``.

Vì sao VẪN phải có: Giai đoạn 1a có 19 task xanh trong khi đường ASR chết ở hai
chỗ không test nào chạm, vì CHƯA TỪNG AI CHẠY nó. Một bài chỉ chạy khi được gọi
tên vẫn hơn một bài không tồn tại — nhưng nó chỉ có giá trị nếu có người gọi tên
nó, nên lần chạy thật và số đo nằm ở ``.superpowers/.../task-16-report.md``.

KHÔNG dựng tay ``Segment(...)`` trong file này: ``Segment`` có 13 trường và dựng
tay làm rơi 7 trường không được kể tên (đã xảy ra hai lần trong giai đoạn 2).
Dùng một segment làm khuôn + ``dataclasses.replace``.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import pathlib

import pytest

from app.domain.models import CallStats, Segment
from app.domain.mt import MtOpts

pytestmark = pytest.mark.live

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _segment(i: int, text: str) -> Segment:
    """Segment nguồn dựng bằng ``replace`` trên một khuôn duy nhất."""
    template = Segment(i=0, start=0.0, end=1.0, text="", words=None,
                       avg_logprob=-0.2, no_speech_prob=0.01)
    return dataclasses.replace(template, i=i, text=text)


# ---------------------------------------------------------------------------
# OPUS-MT — model trong tiến trình, CPU
# ---------------------------------------------------------------------------

def test_opus_mt_translates_real_text_zh_to_vi():
    from app.adapters.mt.opus_mt import OpusMtEngine

    eng = OpusMtEngine()
    batch = [_segment(0, "你好"), _segment(1, "谢谢")]
    out = eng.translate(batch, [], MtOpts(source_lang="zh", target_lang="vi"))

    assert len(out) == len(batch), "hợp đồng MtEngine cấm trả list ngắn hơn"
    assert all(o.text.strip() for o in out), "model thật phải trả chữ, không rỗng"
    assert [o.i for o in out] == [0, 1], "id và thứ tự phải giữ nguyên"
    # `replace` phải giữ 12 trường còn lại; `qa`/`events` là hai trường dễ rơi nhất
    # khi ai đó dựng tay `Segment(...)`.
    assert out[0].avg_logprob == -0.2 and out[0].events == []


def test_opus_mt_does_not_claim_glossary_support():
    """Spec §8.7.2: OPUS-MT không có glossary. Cờ phải nói thật để QA gắn nhãn."""
    from app.adapters.mt.opus_mt import OpusMtEngine

    assert OpusMtEngine().supports_glossary() is False


def test_release_then_reload_works():
    """``release()`` idempotent, và sau khi nhả thì nạp lại vẫn dịch được."""
    from app.adapters.mt.opus_mt import OpusMtEngine

    eng = OpusMtEngine()
    eng.release()          # chưa nạp gì: phải là no-op
    eng.release()          # lần thứ hai cũng vậy
    out = eng.translate([_segment(0, "再见")], [],
                        MtOpts(source_lang="zh", target_lang="vi"))
    assert len(out) == 1 and out[0].text.strip()


# ---------------------------------------------------------------------------
# Qwen2.5-3B qua Ollama — model ở tiến trình RIÊNG, có token count
# ---------------------------------------------------------------------------

def test_qwen_ollama_translates_and_reports_token_counts():
    """Qwen là engine CHỦ LỰC: nó phải trả đủ segment VÀ có token count thật."""
    from app.adapters.mt.ollama_mt import OllamaMtEngine

    eng = OllamaMtEngine(engine_id="qwen2.5-3b")
    batch = [_segment(0, "你好，欢迎使用这个字幕翻译工具。"),
             _segment(1, "今天我们讨论三个问题。")]
    try:
        out = eng.translate(batch, [], MtOpts(source_lang="zh", target_lang="vi"))
    finally:
        stats = eng.last_stats
        eng.release()

    assert len(out) == len(batch), "hợp đồng MtEngine cấm trả list ngắn hơn"
    assert all(o.text.strip() for o in out), "Qwen phải trả chữ, không rỗng"
    assert isinstance(stats, CallStats), (
        "Ollama trả prompt_eval_count/eval_count; thiếu CallStats nghĩa là "
        "adapter đã bỏ số đo"
    )
    assert stats.tokens_in and stats.tokens_out, (
        f"token count phải là số THẬT, nhận {stats!r}"
    )


def test_qwen_release_is_a_noop_before_any_call():
    """Contract: gọi ``release()`` lúc chưa nạp KHÔNG được gửi HTTP.

    Governor gọi nó ở mọi lần thoát và mọi lần đổi phase, kể cả phase chưa từng
    dịch câu nào; một vòng HTTP hỏng ở đó là chi phí thuần.
    """
    from app.adapters.mt.ollama_mt import OllamaMtEngine

    calls: list[str] = []

    class _RecordingClient:
        def post(self, url, **kwargs):
            calls.append(url)
            raise AssertionError("không được gửi HTTP khi chưa nạp gì")

    eng = OllamaMtEngine(engine_id="qwen2.5-3b", client=_RecordingClient())
    eng.release()
    eng.release()
    assert calls == []


# ---------------------------------------------------------------------------
# smoke_mt.py — 0 segment PHẢI thoát khác 0 ("xanh với 0 segment" là báo cáo sai)
# ---------------------------------------------------------------------------

def _load_smoke_mt():
    """Nạp ``scripts/smoke_mt.py`` theo ĐƯỜNG DẪN.

    ``scripts/`` không phải package không có ``__init__.py``... thực tế nó CÓ, nên
    ``import scripts.smoke_mt`` cũng được — nhưng nạp theo đường dẫn giữ bài này
    độc lập với việc ``sys.path`` có ``backend/`` hay không.
    """
    script = BACKEND / "scripts" / "smoke_mt.py"
    assert script.exists(), "brief Task 16 yêu cầu backend/scripts/smoke_mt.py"
    spec = importlib.util.spec_from_file_location("smoke_mt_under_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _StubAsr:
    """Engine ASR giả trả ĐÚNG danh sách segment được dặn — không nạp weight."""

    def __init__(self, segments):
        self.segments = list(segments)
        self.released = False

    def transcribe(self, audio_path, lang):
        return list(self.segments)

    def release(self):
        self.released = True


class _StubMt:
    """Engine dịch giả đếm số lần được gọi — để chứng minh nó KHÔNG được gọi."""

    def __init__(self):
        self.calls = 0
        self.engine_id = "stub-mt"
        self.last_stats = CallStats(tokens_in=1, tokens_out=1, duration_ms=1)

    def translate(self, batch, glossary, opts):
        self.calls += 1
        return [dataclasses.replace(s, text="x") for s in batch]

    def supports_glossary(self):
        return False

    def release(self):
        pass


def _drive_media(monkeypatch, tmp_path, asr_segments):
    """Lái ``run_media`` tới hết đường bóc băng mà không chạm model thật."""
    from app.registry import EngineSpec

    smoke = _load_smoke_mt()
    audio = tmp_path / "synth-zh.wav"
    audio.write_bytes(b"RIFF")

    asr = _StubAsr(asr_segments)
    mt = _StubMt()
    spec = EngineSpec(id="fw-tiny", label="FW tiny", kind="asr",
                      runtime="inprocess", model_ref="tiny", vram_mb=200,
                      langs=("zh", "en"), capabilities={}, opts={})
    monkeypatch.setattr(smoke, "build_asr_engine", lambda engine_id: (spec, asr))
    monkeypatch.setattr(smoke, "build_mt_engine", lambda engine_id: (spec, mt))
    monkeypatch.setattr(smoke, "resolve_hf_home", lambda: str(tmp_path))
    return smoke, asr, mt, audio


def test_smoke_mt_exits_nonzero_with_zero_segments(monkeypatch, tmp_path, capsys):
    """Đúng ca mà task này tồn tại để chặn: 0 segment KHÔNG được là thành công."""
    smoke, asr, mt, audio = _drive_media(monkeypatch, tmp_path, asr_segments=[])

    code = smoke.run_media(str(audio), "zh", "opus-mt", "vi")
    out = capsys.readouterr().out

    assert code != 0, (
        "0 segment phải làm smoke test THẤT BẠI (mã thoát khác 0); 'chạy xong với "
        "0 segment' là báo cáo sai, đúng thứ Giai đoạn 1a đã trả giá"
    )
    assert "OK" not in out, f"0 segment thì KHÔNG được có dòng OK:\n{out}"
    assert mt.calls == 0, "không có gì để dịch thì không được gọi engine dịch"
    assert asr.released, "engine ASR vẫn phải được giải phóng trên nhánh hỏng"


def _fake_mt_spec(model_ref: str = "stub-model"):
    """``EngineSpec`` tối thiểu cho engine dịch giả.

    PHẢI là spec thật chứ không phải ``None``: ``run_media`` đọc
    ``mt_spec.model_ref`` để IN RA model đã dùng, nên trả ``None`` làm nó nổ
    ``AttributeError`` — và vì ``run_media`` bắt mọi exception quanh lời gọi
    ``translate``, cái nổ đó biến thành mã 3 (engine không dựng được) thay vì
    thất bại alignment mà bài muốn kiểm. Test xanh vì lý do sai.
    """
    from app.registry import EngineSpec
    return EngineSpec(id="stub-mt", label="Stub MT", kind="mt",
                      runtime="inprocess", model_ref=model_ref, vram_mb=0,
                      langs=("zh",), capabilities={}, opts={})


def test_smoke_mt_reports_zero_alignments_as_failure(monkeypatch, tmp_path, capsys):
    """Bản dịch RỖNG cũng là hỏng: 'có segment' không đồng nghĩa 'có bản dịch'."""
    smoke, _asr, _mt, audio = _drive_media(
        monkeypatch, tmp_path, asr_segments=[_segment(0, "你好"), _segment(1, "谢谢")])

    class _EmptyMt(_StubMt):
        def translate(self, batch, glossary, opts):
            self.calls += 1
            return [dataclasses.replace(s, text="  ") for s in batch]

    empty = _EmptyMt()
    monkeypatch.setattr(smoke, "build_mt_engine",
                        lambda engine_id: (_fake_mt_spec(), empty))

    code = smoke.run_media(str(audio), "zh", "opus-mt", "vi")
    out = capsys.readouterr().out

    assert code != 0, f"bản dịch rỗng phải là thất bại:\n{out}"
    assert "OK" not in out, f"bản dịch rỗng thì KHÔNG được có dòng OK:\n{out}"


def test_smoke_mt_succeeds_and_prints_numbers_with_real_segments(
        monkeypatch, tmp_path, capsys):
    """Chiều ngược lại: có segment và bản dịch thật thì thoát 0 kèm SỐ."""
    smoke, _asr, _mt, audio = _drive_media(
        monkeypatch, tmp_path,
        asr_segments=[_segment(0, "你好"), _segment(1, "谢谢"), _segment(2, "再见")])
    monkeypatch.setattr(smoke, "build_mt_engine",
                        lambda engine_id: (_fake_mt_spec(), _StubMt()))

    code = smoke.run_media(str(audio), "zh", "opus-mt", "vi")
    out = capsys.readouterr().out

    assert code == 0, f"có segment thì phải thoát 0:\n{out}"
    assert "OK" in out, f"phải có dòng OK:\n{out}"
    assert "3/3 segment" in out, f"phải in số segment THẬT:\n{out}"
    assert "tokens_in=" in out, f"phải in token count:\n{out}"


def test_smoke_mt_usage_error_is_not_a_success():
    smoke = _load_smoke_mt()
    assert smoke.main([]) == 2
    assert smoke.main(["--help"]) == 0


def test_smoke_mt_unknown_engine_id_exits_three_and_names_the_real_ones(capsys):
    """id sai phải thoát 3 và LIỆT KÊ id có thật, không phải một ngõ cụt.

    Đo được trên lần chạy thật: ``fw-tiny`` (id brief đưa) KHÔNG có trong
    ``registry.json``, và bản đầu tiên chết ở ``by_id`` với ``KeyError``. Sau đó
    bản thứ hai in đúng thông báo nhưng ``SystemExit`` lọt ra ngoài nên tiến trình
    thoát 1 chứ không phải 3 — mã thoát là thứ duy nhất máy đọc được.
    """
    smoke = _load_smoke_mt()
    code = smoke.run_synthetic("fw-tiny", "zh", "vi")
    out = capsys.readouterr().out

    assert code == 3, f"engine không dựng được là mã 3, không phải {code}:\n{out}"
    assert "opus-mt" in out and "qwen2.5-3b" in out, (
        f"phải liệt kê id DỊCH có thật để người chạy biết dùng gì:\n{out}"
    )


def test_smoke_mt_unknown_asr_id_exits_three(monkeypatch, tmp_path, capsys):
    smoke = _load_smoke_mt()
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    monkeypatch.setattr(smoke, "resolve_hf_home", lambda: str(tmp_path))

    def _boom(_engine_id):
        raise SystemExit("engine asr 'fw-tiny' không có trong registry.json.")

    monkeypatch.setattr(smoke, "build_asr_engine", _boom)
    code = smoke.run_media(str(audio), "zh", "opus-mt", "vi")
    out = capsys.readouterr().out

    assert code == 3, f"id ASR sai phải là mã 3, nhận {code}:\n{out}"


def test_smoke_mt_main_understands_the_asr_flag():
    """``--asr <id>`` phải được lấy ra khỏi tham số VỊ TRÍ, không lẫn vào chúng.

    Không có phép tách này thì ``media zh opus-mt --asr fw-small`` khiến ``--asr``
    thành ``target_lang`` và script dịch sang một "ngôn ngữ" tên là ``--asr``.
    """
    seen: dict = {}
    smoke = _load_smoke_mt()

    def _spy(media, source_lang, engine_id, target_lang, asr_id="fw-small"):
        seen.update(media=media, source=source_lang, engine=engine_id,
                    target=target_lang, asr=asr_id)
        return 0

    smoke.run_media = _spy
    code = smoke.main(["clip.wav", "zh", "opus-mt", "--asr", "fw-large-v3-turbo"])

    assert code == 0
    assert seen == {"media": "clip.wav", "source": "zh", "engine": "opus-mt",
                    "target": "vi", "asr": "fw-large-v3-turbo"}, seen


def test_smoke_mt_synthetic_path_builds_segments_without_hand_building():
    """``--synthetic`` phải dựng segment bằng ``replace`` trên một khuôn."""
    smoke = _load_smoke_mt()
    batch = smoke.synthetic_segments(smoke._default_max_chars())

    assert batch, "nguồn tổng hợp phải có ít nhất một segment"
    assert [s.i for s in batch] == list(range(len(batch))), "id phải liên tục từ 0"
    assert all(s.text.strip() for s in batch)
    # Khuôn mang `avg_logprob`/`no_speech_prob`; `replace` phải giữ chúng.
    assert all(s.avg_logprob == -0.2 for s in batch)
    assert all(s.words is None and s.events == [] for s in batch)
