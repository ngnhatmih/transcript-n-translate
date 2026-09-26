"""Chạy THẬT một lần dịch và in ra SỐ. Không có số nghĩa là chưa xong.

Dùng:
    python -B scripts/smoke_mt.py <media> <source_lang> <engine_id> [target_lang]
    python -B scripts/smoke_mt.py --synthetic <engine_id> [--source zh] [--target vi]

Tuỳ chọn thêm cho chế độ media: ``--asr <id>`` (mặc định ``fw-small``).

``--asr`` có mặc định là ``fw-small`` chứ KHÔNG phải ``fw-tiny``: ``fw-tiny``
KHÔNG có trong ``registry.json`` (chỉ có ``fw-large-v3-turbo``/``fw-medium``/
``fw-small``), nên bản đầu tiên của script này chết ngay ở ``by_id`` với
``KeyError``. Một id không tồn tại phải báo ra DANH SÁCH id có thật, không chỉ nói
"không thấy".

Thoát khác 0 nếu không dịch được segment nào — "xanh với 0 segment" là báo cáo
sai, và đúng là thất bại mà Giai đoạn 1a đã trả giá: 19 task xanh trong khi đường
ASR chết vì chưa từng ai chạy nó.

MÃ THOÁT (mỗi mã là một loại hỏng KHÁC nhau, không gộp thành 1):

* ``0`` — dịch được, và số segment ra BẰNG số segment vào.
* ``1`` — chạy được nhưng đường ống SAI: 0 segment, lệch alignment, hoặc bản dịch
  rỗng. Đây là loại thất bại mà bản "0 đoạn vẫn OK" đã giấu.
* ``2`` — sai cách dùng, hoặc không thấy tệp.
* ``3`` — không dựng/nạp được engine (thiếu weight, Ollama tắt). Tách khỏi ``1``
  vì "engine không chạy được" phải báo thẳng, KHÔNG được thay bằng test giả.

HAI ĐƯỜNG THẬT, không tự viết lại:

* bóc băng đi qua ``scripts.smoke_asr.build_engine``, tức
  ``app.adapters.asr.factory.engine_for`` — cùng hàm dispatch mà
  ``app.main:_engine_factory`` gọi (R60, I-2). Tên hàm ở đây KHÁC tên brief đoán
  (``build_asr_engine`` trong ``app.adapters.asr.factory``): tầng ASR không có hàm
  đó, và ``engine_for`` đòi một ``EngineSpec`` + ``download_root`` chứ không nhận
  một chuỗi id.
* ``HF_HOME`` được ghim trước khi ``transformers``/``faster_whisper`` được import
  (R60): ``huggingface_hub`` đọc biến này NGAY LÚC IMPORT.

``--synthetic`` chạy đường DỊCH mà không cần âm thanh: nó dựng segment nguồn bằng
``dataclasses.replace`` trên một segment duy nhất (KHÔNG dựng tay ``Segment(...)``
— ``Segment`` có 13 trường và dựng tay làm rơi 7 trường không được kể tên).
"""
from __future__ import annotations

import argparse
import dataclasses
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.domain.models import Segment                       # noqa: E402
from app.domain.mt import MtOpts                            # noqa: E402

#: Engine ASR mặc định của smoke test. ``fw-small`` chứ không phải
#: ``fw-large-v3-turbo``: mục đích của smoke test là biết ĐƯỜNG ỐNG có thông hay
#: không trước khi trả giá 1,6 GB, và ``fw-small`` (500 MB) trả lời được câu đó.
DEFAULT_ASR_ID = "fw-small"

#: Câu nguồn cho chế độ ``--synthetic``. Tiếng Trung vì OPUS-MT của dự án là
#: ``Helsinki-NLP/opus-mt-zh-vi``: đưa tiếng Anh vào model zh->vi là đo nhầm thứ.
SYNTHETIC_SOURCE = [
    "你好，欢迎使用这个字幕翻译工具。",
    "今天我们讨论三个问题：速度、准确率和成本。",
    "第一，速度必须够快，否则用户会离开。",
    "第二，准确率决定了字幕能不能直接用。",
    "第三，成本要可控，所以我们先在本地跑模型。",
]

#: Ngân sách ký tự cho một lô. Khớp ``app.domain.mt.DEFAULT_MAX_CHARS``; đọc động
#: để script không trôi khỏi hằng số của sản phẩm.
def _default_max_chars() -> int:
    from app.domain.mt import DEFAULT_MAX_CHARS
    return DEFAULT_MAX_CHARS


def force_utf8_stdout(stream=None) -> bool:
    """Ép UTF-8 cho stdout (R17) — console Windows mặc định là cp1252.

    Cùng hợp đồng với ``scripts/smoke_asr.force_utf8_stdout``: ``errors="replace"``
    để một ký tự không hiển thị được không bao giờ làm chết lần chạy thật.
    """
    stream = sys.stdout if stream is None else stream
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return False
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        return False
    return True


def resolve_hf_home() -> str:
    """Ghim ``HF_HOME`` TRƯỚC khi thư viện model được import (R60).

    Trả về đường dẫn thật sẽ dùng để in ra, vì ``app.config.HF_HOME`` chỉ là hằng
    số Python — không phải thứ ``huggingface_hub`` nhìn thấy.
    """
    from app.config import HF_HOME

    import os
    os.environ.setdefault("HF_HOME", HF_HOME)
    os.environ.setdefault("MODELSCOPE_CACHE",
                          str(pathlib.Path(os.environ["HF_HOME"]) / "modelscope"))
    return os.environ["HF_HOME"]


def _spec_or_report(kind: str, engine_id: str):
    """``by_id`` nhưng khi không thấy thì LIỆT KÊ id có thật của ``kind``.

    ``KeyError: "engine 'fw-tiny' không có trong registry"`` là một ngõ cụt: người
    chạy không biết id nào tồn tại. Lần chạy thật đầu tiên của script này đã chết
    đúng như vậy, nên đây là sửa theo SỐ ĐO chứ không phải phòng xa.
    """
    from app.adapters.registry_file import load_registry
    from app.registry import by_id

    specs = load_registry()
    try:
        return by_id(specs, engine_id)
    except KeyError:
        available = [s.id for s in specs if s.kind == kind]
        raise SystemExit(
            f"engine {kind} {engine_id!r} không có trong registry.json.\n"
            f"  id {kind} có thật: {', '.join(available) or '(không có)'}"
        ) from None


def _load_smoke_asr():
    """Nạp ``scripts/smoke_asr.py`` theo ĐƯỜNG DẪN.

    ``scripts/`` KHÔNG phải package (không có ``__init__.py``) nên
    ``import scripts.smoke_asr`` sẽ nổ ``ModuleNotFoundError``; và thêm
    ``__init__.py`` chỉ để một script import được script kia là đổi cấu trúc repo
    cho một tiện lợi nhỏ. Nạp theo đường dẫn cũng khớp cách
    ``tests/test_smoke_script.py`` đang làm.
    """
    import importlib.util

    path = pathlib.Path(__file__).resolve().parent / "smoke_asr.py"
    spec = importlib.util.spec_from_file_location("smoke_asr_for_smoke_mt", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_asr_engine(engine_id: str):
    """Dựng engine ASR qua ĐÚNG hàm dispatch của production (R60, I-2).

    ``scripts/smoke_asr.build_engine`` là chỗ gọi thứ hai của
    ``app.adapters.asr.factory.engine_for`` và nó đã được ghim với
    ``app.main:_engine_factory`` bằng ``tests/test_smoke_script.py``. Gọi lại nó
    thay vì tự dựng adapter giữ nguyên tính chất đó cho smoke test này.

    LƯU Ý TÊN: brief đoán ``from app.adapters.asr.factory import build_asr_engine``
    và ``asr.transcribe(media, lang=...)``. Tầng ASR KHÔNG có hàm ``build_asr_engine``
    — hàm thật là ``engine_for(spec, *, download_root=...)``, chỉ nhận
    ``EngineSpec`` chứ không nhận id. Đọc code trước khi gọi, như hiệu chỉnh C dặn.
    """
    spec = _spec_or_report("asr", engine_id)
    return spec, _load_smoke_asr().build_engine(spec)


def build_mt_engine(engine_id: str):
    """Dựng engine DỊCH theo ``id`` của ``registry.json``, KHÔNG đoán theo tiền tố.

    Model và các cờ capability đọc từ registry: ``glossary_prompt`` của
    ``qwen2.5-3b`` là ``true`` còn của ``opus-mt`` là ``false``, và cờ đó vào
    thẳng prompt lẫn nhãn QA — tự đoán là nói dối về một engine khác.
    """
    spec = _spec_or_report("mt", engine_id)
    if spec.runtime == "ollama":
        from app.adapters.mt.ollama_mt import OllamaMtEngine
        return spec, OllamaMtEngine(
            spec.model_ref,
            engine_id=spec.id,
            supports_glossary=bool(spec.capabilities.get("glossary_prompt", False)),
        )
    from app.adapters.mt.opus_mt import OpusMtEngine
    return spec, OpusMtEngine(spec.model_ref)


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Cắt văn bản dài thành khúc <= ``max_chars``, ưu tiên cắt ở dấu câu.

    Cần vì ``--synthetic`` gửi câu dài thẳng vào OPUS-MT: Marian có giới hạn 512
    token và một câu vượt giới hạn bị CẮT ÂM THẦM ở tầng tokenizer, nên "dịch
    được" có thể chỉ là "dịch được nửa đầu".
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    rest = text
    cutters = "。！？；，、,;!?"
    while len(rest) > max_chars:
        window = rest[:max_chars]
        cut = max(window.rfind(c) for c in cutters)
        if cut <= 0:
            cut = max_chars - 1
        parts.append(rest[:cut + 1])
        rest = rest[cut + 1:]
    if rest.strip():
        parts.append(rest)
    return [p for p in parts if p.strip()]


def synthetic_segments(max_chars: int) -> list[Segment]:
    """Segment nguồn cho ``--synthetic``, dựng bằng ``dataclasses.replace``.

    Một ``Segment`` gốc duy nhất làm khuôn cho mọi dòng: ``replace`` bảo đảm 12
    trường còn lại (``words``/``emotion``/``events``/``speaker``/``avg_logprob``/
    ``no_speech_prob``/``suspect``/``t``/``qa``/...) được giữ nguyên bởi NGÔN NGỮ,
    không phải bởi việc đọc kỹ danh sách tham số.
    """
    template = Segment(i=0, start=0.0, end=0.0, text="", words=None,
                       avg_logprob=-0.2, no_speech_prob=0.01)
    out: list[Segment] = []
    for text in SYNTHETIC_SOURCE:
        for piece in chunk_text(text, max_chars):
            out.append(dataclasses.replace(template, i=len(out), text=piece))
    return out


def _report_alignment(batch: list[Segment], out: list[Segment]) -> bool:
    """In tỉ lệ hỏng alignment. Trả ``True`` nếu KHỚP đủ."""
    empty = sum(1 for s in out if not s.text.strip())
    if len(out) != len(batch):
        print(f"THẤT BẠI: alignment sai — vào {len(batch)}, ra {len(out)}")
        return False
    if empty:
        print(f"THẤT BẠI: {empty}/{len(out)} segment ra RỖNG — không phải bản dịch")
        return False
    return True


def _print_pairs(batch: list[Segment], out: list[Segment], limit: int = 5) -> None:
    for s, t in list(zip(batch, out))[:limit]:
        print(f"      {s.i:>4}  {s.text[:40]!r} -> {t.text[:40]!r}")


def _stats_of(engine) -> tuple[object, object]:
    stats = getattr(engine, "last_stats", None)
    return (getattr(stats, "tokens_in", None),
            getattr(stats, "tokens_out", None))


def run_synthetic(engine_id: str, source_lang: str, target_lang: str) -> int:
    """Đường DỊCH không cần âm thanh. Đo được engine trước khi tải weight/model ASR."""
    max_chars = _default_max_chars()
    batch = synthetic_segments(max_chars)
    print(f"[1/3] nguồn tổng hợp: {len(batch)} segment "
          f"(ngân sách lô {max_chars} ký tự, {sum(len(s.text) for s in batch)} ký tự)")
    try:
        _spec, engine = build_mt_engine(engine_id)
    except SystemExit as exc:
        # `_spec_or_report` ném `SystemExit` để in danh sách id có thật. KHÔNG bắt
        # nó thì tiến trình thoát bằng mã của `SystemExit` (1) chứ không phải mã
        # ta định nghĩa (3) — và mã thoát là thứ duy nhất máy đọc được. Đo được
        # trên lần chạy thật: `--synthetic fw-tiny` in đúng thông báo nhưng thoát 1.
        print(exc)
        return 3
    except Exception as exc:                                    # noqa: BLE001
        print(f"KHÔNG DỰNG ĐƯỢC ENGINE {engine_id!r}: {type(exc).__name__}: {exc}")
        return 3

    opts = MtOpts(source_lang=source_lang, target_lang=target_lang)
    try:
        t0 = time.perf_counter()
        out = engine.translate(batch, [], opts)
        elapsed = time.perf_counter() - t0
    except Exception as exc:                                    # noqa: BLE001
        print(f"ENGINE {engine_id!r} NỔ: {type(exc).__name__}: {exc}")
        return 3
    finally:
        release = getattr(engine, "release", None)
        if release is not None:
            release()

    tokens_in, tokens_out = _stats_of(engine)
    print(f"[2/3] dịch {len(batch)} segment bằng {engine_id} trong {elapsed:.1f}s "
          f"(engine_id thật={engine.engine_id})")
    print(f"      tokens_in={tokens_in} tokens_out={tokens_out}")
    if not _report_alignment(batch, out):
        return 1
    _print_pairs(batch, out)
    print(f"[3/3] OK — {len(out)}/{len(batch)} segment, {elapsed:.1f}s, "
          f"engine={engine.engine_id}, glossary={engine.supports_glossary()}")
    return 0


def run_media(media: str, source_lang: str, engine_id: str,
              target_lang: str, asr_id: str = DEFAULT_ASR_ID) -> int:
    """Đường ĐẦY ĐỦ: bóc băng thật rồi dịch thật."""
    audio = pathlib.Path(media)
    if not audio.exists():
        print(f"không thấy tệp: {audio}")
        return 2

    cache_root = resolve_hf_home()
    print(f"      HF_HOME={cache_root!r}")

    print(f"[1/3] bóc băng {audio.name} (lang={source_lang}, asr={asr_id}) ...")
    try:
        asr_spec, asr = build_asr_engine(asr_id)
    except SystemExit as exc:
        print(exc)
        return 3
    except Exception as exc:                                    # noqa: BLE001
        print(f"KHÔNG DỰNG ĐƯỢC ENGINE ASR {asr_id!r}: "
              f"{type(exc).__name__}: {exc}")
        return 3
    t0 = time.perf_counter()
    try:
        segments = asr.transcribe(str(audio), source_lang)
    except Exception as exc:                                    # noqa: BLE001
        print(f"BÓC BĂNG NỔ: {type(exc).__name__}: {exc}")
        return 3
    finally:
        asr.release()
    asr_elapsed = time.perf_counter() - t0
    print(f"      {len(segments)} segment trong {asr_elapsed:.1f}s "
          f"(asr={asr_spec.id})")
    if not segments:
        print("THẤT BẠI: không có segment nào để dịch — đường ASR không sinh "
              "transcript nào. KHÔNG tính là smoke test đạt (R62/R68).")
        return 1

    sample = segments[:20]
    try:
        mt_spec, engine = build_mt_engine(engine_id)
    except SystemExit as exc:
        print(exc)
        return 3
    except Exception as exc:                                    # noqa: BLE001
        print(f"KHÔNG DỰNG ĐƯỢC ENGINE {engine_id!r}: {type(exc).__name__}: {exc}")
        return 3

    print(f"[2/3] dịch {len(sample)} segment bằng {engine_id} "
          f"(model_ref={mt_spec.model_ref!r}) ...")
    t0 = time.perf_counter()
    try:
        out = engine.translate(sample, [], MtOpts(source_lang=source_lang,
                                                  target_lang=target_lang))
    except Exception as exc:                                    # noqa: BLE001
        print(f"ENGINE {engine_id!r} NỔ: {type(exc).__name__}: {exc}")
        return 3
    finally:
        release = getattr(engine, "release", None)
        if release is not None:
            release()
    elapsed = time.perf_counter() - t0
    tokens_in, tokens_out = _stats_of(engine)

    print(f"      tokens_in={tokens_in} tokens_out={tokens_out}")
    if not _report_alignment(sample, out):
        return 1
    _print_pairs(sample, out)
    print(f"[3/3] OK — {len(out)}/{len(sample)} segment, {elapsed:.1f}s, "
          f"engine={engine.engine_id}, glossary={engine.supports_glossary()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdout()
    raw = list(sys.argv[1:] if argv is None else argv)

    if raw and raw[0] == "--synthetic":
        # Chế độ không cần âm thanh có cú pháp riêng: `--synthetic <engine_id>`
        # kèm `--source`/`--target` tuỳ chọn. Không dùng chung bộ tham số vị trí
        # với chế độ media, vì ở đó vị trí 2 là NGÔN NGỮ NGUỒN còn ở đây là
        # engine — cùng một ô mang hai nghĩa là đúng kiểu nhầm làm script đo
        # nhầm engine mà vẫn in ra "OK".
        parser = argparse.ArgumentParser(
            prog="smoke_mt.py --synthetic",
            description="Chạy thật đường DỊCH mà không cần âm thanh.",
        )
        parser.add_argument("engine_id", help="id trong registry.json, vd opus-mt")
        parser.add_argument("--source", default="zh", dest="source_lang")
        parser.add_argument("--target", default="vi", dest="target_lang")
        args = parser.parse_args(raw[1:])
        return run_synthetic(args.engine_id, args.source_lang, args.target_lang)

    if not raw or raw[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if raw else 2
    # `--asr <id>` lấy ra khỏi danh sách vị trí trước khi đếm, để
    # `smoke_mt.py clip.wav zh opus-mt --asr fw-small` và
    # `smoke_mt.py clip.wav zh opus-mt vi --asr fw-small` đều đúng.
    asr_id = DEFAULT_ASR_ID
    positional: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i] == "--asr":
            if i + 1 >= len(raw):
                print("--asr cần một id engine")
                return 2
            asr_id = raw[i + 1]
            i += 2
            continue
        positional.append(raw[i])
        i += 1

    if len(positional) < 3:
        print(__doc__)
        return 2
    media, source_lang, engine_id = positional[0], positional[1], positional[2]
    target_lang = positional[3] if len(positional) > 3 else "vi"
    return run_media(media, source_lang, engine_id, target_lang, asr_id)


if __name__ == "__main__":
    raise SystemExit(main())
