"""Nạp liệu: tệp tải lên hoặc link online -> wav 16k mono.

Toàn bộ phần chạm ffmpeg/yt-dlp nằm ở đây. `runner` được bơm vào để test không
cần mạng và không cần tệp thật.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from typing import Callable, Iterable

from app.domain import job_state as _job_state
from app.domain.models import Job
from app.domain.paths import PathOutsideRoot, resolve_within
from app.ports.repos import Repos
from app.registry import (ASR_DEFAULT_SETTING, FALLBACK_ASR_ENGINE_ID, EngineSpec,
                          default_asr_engine)


class IngestError(RuntimeError):
    pass


AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
_CHUNK = 1024 * 1024


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


#: Giữ tên cũ cho ai còn import; giá trị thật nằm ở `app.registry` (I-3).
DEFAULT_ASR_ENGINE = FALLBACK_ASR_ENGINE_ID
DEFAULT_LANG = "zh"


class IngestHandler:
    """Job 'ingest': bóc âm thanh từ media đã có, đặt duration, rồi xếp job asr.

    Đây là mắt đầu tiên của cả pipeline. Nó KHÔNG tải media: việc tải (tệp lên
    hay link) xảy ra ở route, trước khi job tồn tại, để request HTTP không phải
    giữ một tệp 2 GB trong lúc bóc âm thanh.

    Hai tham số chỉ có `app/main.py` truyền (composition root) — chúng biến hai
    luật của tầng này từ "hy vọng người gọi nhớ" thành thứ chạy được:

    * `media_root` (I-6): gốc media. Mọi `media_path` đọc từ DB phải được
      `resolve_within` gốc này TRƯỚC khi đưa cho ffprobe/ffmpeg, đúng luật mà
      route media đã áp cho chính cột đó khi ĐỌC.
    * `specs` + `declared_default_asr` (I-3): registry đã nạp và engine ASR mặc
      định do registry khai báo. Có chúng thì một engine mặc định không tồn tại
      bị từ chối NGAY, thay vì xếp một job asr chắc chắn `KeyError` ở worker.

    `specs=None` nghĩa là "không có registry để đối chiếu" (test dựng handler
    trần); production luôn truyền cả ba.
    """

    def __init__(self, repos: Repos, *, audio_dir=None, media_root=None,
                 specs: Iterable[EngineSpec] | None = None,
                 declared_default_asr: str | None = None) -> None:
        self._repos = repos
        self._audio_dir = audio_dir
        self._media_root = media_root
        self._specs = list(specs) if specs is not None else None
        self._declared_default_asr = declared_default_asr

    def handles(self) -> str:
        return "ingest"

    def _resolve_asr_engine(self, source_id: int) -> str:
        """Engine ASR mặc định, đã kiểm nếu biết registry (I-3)."""
        configured = self._repos.get_setting(ASR_DEFAULT_SETTING)
        if self._specs is None:
            return configured or self._declared_default_asr or DEFAULT_ASR_ENGINE
        try:
            return default_asr_engine(self._specs, declared=self._declared_default_asr,
                                      configured=configured)
        except KeyError as exc:
            raise IngestError(f"source {source_id}: {exc}") from exc

    def _contained_media(self, source_id: int, media: pathlib.Path) -> pathlib.Path:
        """Chứng minh `media_path` vẫn nằm trong gốc media trước khi mở nó (I-6)."""
        if self._media_root is None:
            return media
        try:
            return resolve_within(self._media_root, media)
        except PathOutsideRoot as exc:
            raise IngestError(
                f"source {source_id}: media_path nằm ngoài gốc media "
                f"({self._media_root}): {exc}"
            ) from exc

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        source_id = int(job.payload["source_id"])
        source = self._repos.get_source(source_id)
        media = self._contained_media(source_id, pathlib.Path(source.media_path))
        if not media.exists():
            # Nêu cả đường dẫn LẪN source id: người vận hành cần biết tệp nào
            # mất và hàng `sources` nào đang trỏ tới nó. Ném lỗi ở đây cũng là
            # cách duy nhất để job dừng TRƯỚC khi tạo job asr — nếu không, job
            # asr sẽ nổ ở `TranscribeHandler` với thông báo mơ hồ hơn nhiều.
            raise IngestError(
                f"source {source_id}: tệp media không tồn tại: {media}. "
                "Kiểm tra `media_path` trong bảng sources, hoặc nạp lại nguồn."
            )

        # I-3: chọn engine mặc định TRƯỚC khi bóc âm thanh. Id không có trong
        # registry nghĩa là job asr chắc chắn chết, nên đừng làm việc nặng rồi
        # mới phát hiện — và tuyệt đối đừng xếp job đó vào hàng đợi.
        engine_id = self._resolve_asr_engine(source_id)

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

        engine_id = self._resolve_asr_engine(source_id)
        self._repos.add_job(Job(
            id=None, workspace=1, type="asr", engine=engine_id,
            phase=_job_state.phase_of("asr", engine_id),
            payload={"source_id": source_id, "lang": lang},
        ))
        report(1.0, "đã tạo job bóc băng")
