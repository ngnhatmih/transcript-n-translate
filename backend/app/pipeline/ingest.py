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
