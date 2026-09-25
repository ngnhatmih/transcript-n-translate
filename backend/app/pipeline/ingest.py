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

from app.domain import job_state as _job_state
from app.domain.models import Job
from app.ports.repos import Repos


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
        return subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=True,
        )
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


DEFAULT_ASR_ENGINE = "fw-large-v3-turbo"
DEFAULT_LANG = "zh"


class IngestHandler:
    """Job 'ingest': bóc âm thanh từ media đã có, đặt duration, rồi xếp job asr.

    Đây là mắt đầu tiên của cả pipeline. Nó KHÔNG tải media: việc tải (tệp lên
    hay link) xảy ra ở route, trước khi job tồn tại, để request HTTP không phải
    giữ một tệp 2 GB trong lúc bóc âm thanh.
    """

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
            # Nêu cả đường dẫn LẪN source id: người vận hành cần biết tệp nào
            # mất và hàng `sources` nào đang trỏ tới nó. Ném lỗi ở đây cũng là
            # cách duy nhất để job dừng TRƯỚC khi tạo job asr — nếu không, job
            # asr sẽ nổ ở `TranscribeHandler` với thông báo mơ hồ hơn nhiều.
            raise IngestError(
                f"source {source_id}: tệp media không tồn tại: {media}. "
                "Kiểm tra `media_path` trong bảng sources, hoặc nạp lại nguồn."
            )

        out_dir = pathlib.Path(self._audio_dir) if self._audio_dir else media.parent
        report(0.2, f"extract audio từ {media.name}")
        wav, duration = extract_audio(media, out_dir, stem=media.stem)
        self._repos.set_source_audio(source_id, str(wav), duration)
        report(0.7, f"audio {wav.name} · {duration:.1f}s")

        # Ngôn ngữ đã khai báo thì dùng; nguồn không khai báo (Task 19 nạp thẳng
        # vào DB, hoặc hàng cũ trước khi có cột `lang`) mới rơi về mặc định.
        # Dòng log phải NÓI RÕ đây là dự phòng — nếu không, 'zh' giả định sẽ trá
        # hình thành 'zh' do người dùng chọn và không ai phát hiện ra.
        if source.lang:
            lang = source.lang
            report(0.8, f"ngôn ngữ khai báo: {lang}")
        else:
            lang = DEFAULT_LANG
            report(0.8, f"nguồn chưa khai báo ngôn ngữ — dùng mặc định {lang}")

        engine_id = self._repos.get_setting("default_asr_engine") or DEFAULT_ASR_ENGINE
        self._repos.add_job(Job(
            id=None, workspace=1, type="asr", engine=engine_id,
            phase=_job_state.phase_of("asr", engine_id),
            payload={"source_id": source_id, "lang": lang},
        ))
        report(1.0, "đã tạo job bóc băng")
