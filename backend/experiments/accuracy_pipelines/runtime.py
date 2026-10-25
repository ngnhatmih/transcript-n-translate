from __future__ import annotations

import base64
import dataclasses
import json
import os
import pathlib
import subprocess
import tempfile
import time
from typing import Callable

import httpx

from app.adapters.registry_file import load_default_asr, load_default_mt, load_registry
from app.domain.alignment import AlignmentProblem
from app.config import HF_HOME
from app.domain.models import Segment, Term
from app.domain.mt import (DEFAULT_MAX_CHARS, DEFAULT_MAX_ITEMS, MtOpts,
                           batch_segments)
from app.pipeline.ingest import extract_audio
from app.registry import (default_asr_engine, default_mt_engine)

from .contracts import PipelineContext


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
_CHAT_TIMEOUT = 300.0


class ModelUnavailableError(RuntimeError):
    pass


def _prepare_model_caches() -> None:
    os.environ.setdefault("HF_HOME", str(HF_HOME))
    os.environ.setdefault("MODELSCOPE_CACHE", str(pathlib.Path(HF_HOME) / "modelscope"))


def _load_glossary(path: str | None) -> list[Term]:
    if not path:
        return []
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("glossary JSON must be a list of term objects")
    return [Term(
        id=item.get("id"), lang=str(item["lang"]), term=str(item["term"]),
        translation=str(item["translation"]), note=item.get("note"),
        approved=bool(item.get("approved", False)),
    ) for item in payload]


def load_runtime_context(args, *, audio_extractor: Callable = extract_audio) -> PipelineContext:
    media = pathlib.Path(args.media).expanduser().resolve()
    if not media.is_file():
        raise FileNotFoundError(f"media file does not exist: {media}")
    output_dir = pathlib.Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_owner = tempfile.TemporaryDirectory(prefix="phude-quality-")
    workdir = pathlib.Path(temp_owner.name)
    try:
        audio_path, duration = audio_extractor(media, workdir, stem="audio")
        specs = load_registry()
        asr_id = default_asr_engine(
            specs, declared=load_default_asr(), configured=getattr(args, "baseline_asr", None)
        )
        mt_id = default_mt_engine(
            specs, declared=load_default_mt(), configured=getattr(args, "baseline_mt", None)
        )
        models = {"baseline_asr": asr_id, "baseline_mt": mt_id or ""}
        return PipelineContext(
            media_path=media, audio_path=pathlib.Path(audio_path),
            source_lang=args.source, target_lang=args.target, workdir=workdir,
            output_dir=output_dir, glossary=_load_glossary(getattr(args, "glossary", None)),
            models=models, frame_interval_seconds=int(getattr(args, "frame_interval", 15)),
            ollama_base_url=getattr(args, "ollama_url", DEFAULT_OLLAMA_URL).rstrip("/"),
            audio_duration_seconds=float(duration), temp_owner=temp_owner,
        )
    except Exception:
        temp_owner.cleanup()
        raise


def transcribe(engine_id: str, audio_path: str | pathlib.Path, lang: str, *,
               engine_factory: Callable | None = None,
               initial_prompt: str | None = None) -> list[Segment]:
    """Run one registered ASR engine and release it on every exit path."""
    _prepare_model_caches()
    specs = load_registry()
    from app.registry import by_id

    spec = by_id(specs, engine_id)
    if spec.kind != "asr":
        raise ValueError(f"{engine_id!r} is not an ASR engine")
    if initial_prompt:
        spec = dataclasses.replace(spec, opts={**spec.opts, "initial_prompt": initial_prompt})
    if engine_factory is None:
        from app.adapters.asr.factory import engine_for
        engine_factory = lambda selected: engine_for(selected, download_root=str(HF_HOME))
    engine = engine_factory(spec)
    try:
        segments = engine.transcribe(str(audio_path), lang)
        if not segments:
            raise RuntimeError(f"{engine_id} returned no transcript segments")
        return segments
    finally:
        engine.release()


def _build_mt_engine(engine_id: str):
    from app.registry import by_id
    from app.adapters.mt.ollama_mt import OllamaMtEngine
    from app.adapters.mt.opus_mt import OpusMtEngine

    spec = by_id(load_registry(), engine_id)
    if spec.kind != "mt":
        raise ValueError(f"{engine_id!r} is not an MT engine")
    if spec.runtime == "ollama":
        return spec, OllamaMtEngine(
            spec.model_ref, engine_id=spec.id,
            supports_glossary=bool(spec.capabilities.get("glossary_prompt", False)),
        )
    return spec, OpusMtEngine(spec.model_ref)


def translate(engine_id: str, segments: list[Segment], glossary: list[Term],
              source_lang: str, target_lang: str, *, engine_factory: Callable | None = None
              ) -> list[Segment]:
    """Translate ordered batches through a shipped MT adapter, then unload it."""
    if engine_factory is None:
        _spec, engine = _build_mt_engine(engine_id)
    else:
        engine = engine_factory(engine_id)
    try:
        translated: list[Segment] = []
        opts = MtOpts(source_lang=source_lang, target_lang=target_lang)
        for batch in batch_segments(segments, max_chars=DEFAULT_MAX_CHARS,
                                    max_items=DEFAULT_MAX_ITEMS):
            try:
                out = engine.translate(batch, glossary, opts)
                if len(out) != len(batch) or [s.i for s in out] != [s.i for s in batch]:
                    raise RuntimeError(f"{engine_id} returned mismatched segment ids")
                if any(not s.text.strip() for s in out):
                    raise RuntimeError(f"{engine_id} returned an empty translation")
                translated.extend(out)
            except (ValueError, AlignmentProblem):
                # LLMs occasionally emit malformed batch JSON. Retry that batch
                # as singleton requests so one bad response does not discard all
                # subtitles; preserve order and still fail if any item is invalid.
                if len(batch) == 1:
                    raise
                for segment in batch:
                    out = engine.translate([segment], glossary, opts)
                    if len(out) != 1 or out[0].i != segment.i:
                        raise RuntimeError(f"{engine_id} returned mismatched segment ids")
                    if not out[0].text.strip():
                        raise RuntimeError(f"{engine_id} returned an empty translation")
                    translated.extend(out)
        return translated
    finally:
        engine.release()


def _client(client=None):
    return client if client is not None else httpx.Client()


def require_ollama_models(model_tags: list[str] | tuple[str, ...], *,
                          base_url: str = DEFAULT_OLLAMA_URL, client=None) -> None:
    owns_client = client is None
    client = _client(client)
    try:
        response = client.get(f"{base_url.rstrip('/')}/api/tags", timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            client.close()
    entries = payload.get("models") if isinstance(payload, dict) else None
    available = set()
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                for key in ("name", "model"):
                    name = entry.get(key)
                    if isinstance(name, str):
                        available.add(name)
    missing = [tag for tag in model_tags if tag not in available]
    if missing:
        commands = "\n".join(f"  ollama pull {tag}" for tag in missing)
        raise ModelUnavailableError(f"missing Ollama model tag(s): {', '.join(missing)}\n{commands}")


def ollama_json(model: str, system: str, prompt: str, *,
                images: list[pathlib.Path] = (), base_url: str = DEFAULT_OLLAMA_URL,
                client=None, think: bool | None = None,
                unload_after: bool = True,
                num_predict: int | None = None) -> tuple[dict, dict]:
    """Call local Ollama for JSON and always request model unload afterwards."""
    owns_client = client is None
    client = _client(client)
    message = {"role": "user", "content": prompt}
    if images:
        message["images"] = [base64.b64encode(path.read_bytes()).decode("ascii")
                             for path in images]
    messages = []
    if system.strip():
        messages.append({"role": "system", "content": system})
    messages.append(message)
    body = {
        "model": model, "stream": False, "format": "json", "keep_alive": "5m",
        "options": {"temperature": 0.1, "num_ctx": 4096},
        "messages": messages,
    }
    if num_predict is not None:
        body["options"]["num_predict"] = num_predict
    if think is not None:
        body["think"] = think
    try:
        response = client.post(f"{base_url.rstrip('/')}/api/chat", json=body,
                               timeout=_CHAT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        message_data = data.get("message") if isinstance(data, dict) else None
        content = message_data.get("content") if isinstance(message_data, dict) else None
        if not isinstance(content, str):
            raise ValueError("Ollama returned no JSON content")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ollama content is not valid JSON: {exc}") from exc
        if not isinstance(result, dict):
            raise ValueError("Ollama JSON response must be an object")
        duration = data.get("total_duration")
        stats = {
            "tokens_in": data.get("prompt_eval_count"),
            "tokens_out": data.get("eval_count"),
            "duration_ms": int(duration) // 1_000_000 if duration else None,
        }
        return result, stats
    finally:
        if unload_after:
            _unload_ollama_model(model, base_url=base_url, client=client)
        if owns_client:
            client.close()


def _unload_ollama_model(model: str, *, base_url: str, client) -> None:
    try:
        client.post(f"{base_url.rstrip('/')}/api/chat",
                    json={"model": model, "messages": [], "keep_alive": 0},
                    timeout=30.0)
    except Exception:
        pass


def unload_ollama_model(model: str, *, base_url: str = DEFAULT_OLLAMA_URL,
                        client=None) -> None:
    owns_client = client is None
    client = _client(client)
    try:
        _unload_ollama_model(model, base_url=base_url, client=client)
    finally:
        if owns_client:
            client.close()


def extract_context_frames(media_path: pathlib.Path, out_dir: pathlib.Path,
                           interval_seconds: int, *, runner=None,
                           crop_subtitles: bool = False) -> list[pathlib.Path]:
    if interval_seconds < 1:
        raise ValueError("frame interval must be at least 1 second")
    media_path = pathlib.Path(media_path)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run = runner or subprocess.run
    probe = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_type", "-of", "json", str(media_path),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    streams = json.loads(probe.stdout).get("streams", [])
    if not streams:
        raise ValueError("visual context pipeline requires video; input is audio-only")
    pattern = out_dir / "frame_%04d.jpg"
    video_filter = f"fps=1/{interval_seconds},scale=640:-2"
    if crop_subtitles:
        # Keep visual entities while excluding the common burned-in caption band,
        # which would leak reference transcript text into ASR context.
        video_filter += ",crop=iw:ih*3/4:0:0"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(media_path),
        "-vf", video_filter, "-frames:v", "24",
        "-q:v", "4", str(pattern),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    frames = sorted(out_dir.glob("frame_*.jpg"))
    if not frames:
        raise RuntimeError(f"ffmpeg did not extract frames from {media_path}")
    return frames


def extract_frame_at(media_path: pathlib.Path, timestamp: float,
                     output_path: pathlib.Path, *, runner=None) -> pathlib.Path:
    """Extract one resized frame at a media timestamp for local visual inspection."""
    if timestamp < 0:
        raise ValueError("frame timestamp must be non-negative")
    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run = runner or subprocess.run
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{timestamp:.3f}", "-i", str(media_path),
        "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", str(output_path),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return output_path
