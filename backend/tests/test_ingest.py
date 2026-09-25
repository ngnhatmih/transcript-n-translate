from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from app.pipeline import ingest


def _have(binary: str) -> bool:
    return shutil.which(binary) is not None


pytestmark = pytest.mark.skipif(
    not (_have("ffmpeg") and _have("ffprobe")),
    reason="cần ffmpeg/ffprobe trên PATH",
)


@pytest.fixture()
def tone_wav(tmp_path):
    """Sinh một tệp wav 3 giây bằng ffmpeg — không cần tài nguyên ngoài."""
    out = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(out)],
        check=True,
    )
    return out


def test_sha256_is_stable_and_distinguishes_files(tone_wav, tmp_path):
    other = tmp_path / "other.wav"
    shutil.copy(tone_wav, other)
    assert ingest.sha256_file(tone_wav) == ingest.sha256_file(other)
    assert len(ingest.sha256_file(tone_wav)) == 64

    # R46: bản sao y hệt không chứng minh được tính "phân biệt" trong tên test.
    # Phải có một tệp KHÁC NỘI DUNG và hash của nó phải khác.
    different = tmp_path / "different.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=880:duration=3", str(different)],
        check=True,
    )
    assert ingest.sha256_file(different) != ingest.sha256_file(tone_wav)


def test_probe_duration_reads_real_duration(tone_wav):
    assert 2.8 < ingest.probe_duration(tone_wav) < 3.2


def test_extract_audio_produces_mono_16k_wav(tone_wav, tmp_path):
    wav, duration = ingest.extract_audio(tone_wav, tmp_path, stem="abc")
    assert wav.exists()
    assert wav.name == "abc.wav"
    assert 2.8 < duration < 3.2

    # Đọc theo TÊN trường, không theo thứ tự: ffprobe 8.1.1 luôn xuất
    # sample_rate TRƯỚC channels (`16000,1`) bất kể thứ tự liệt kê trong
    # -show_entries, nên khẳng định vị trí `startswith("1,")` là sai.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=channels,sample_rate", "-of", "json", str(wav)],
        capture_output=True, text=True, check=True,
    ).stdout
    stream = json.loads(probe)["streams"][0]
    assert stream["channels"] == 1, f"phải là mono, nhận được {stream['channels']!r}"
    assert ingest.AUDIO_SAMPLE_RATE == 16000
    assert int(stream["sample_rate"]) == 16000, (
        f"phải là 16kHz, nhận được {stream['sample_rate']!r}"
    )


def test_extract_audio_is_idempotent(tone_wav, tmp_path):
    first, _ = ingest.extract_audio(tone_wav, tmp_path, stem="abc")
    stamp = first.stat().st_mtime_ns
    again, _ = ingest.extract_audio(tone_wav, tmp_path, stem="abc")
    assert again == first
    assert again.stat().st_mtime_ns == stamp, "chạy lại không được extract lại"


def test_probe_duration_on_garbage_raises_a_clear_error(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"khong phai video")
    with pytest.raises(ingest.IngestError):
        ingest.probe_duration(bad)


def test_download_url_rejects_non_http_scheme(tmp_path):
    with pytest.raises(ingest.IngestError):
        ingest.download_url("file:///etc/passwd", tmp_path)


def test_download_url_uses_injected_runner(tmp_path):
    """Không gọi mạng trong test: bơm runner giả để kiểm tra hợp đồng."""
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str], on_progress) -> str:
        calls.append(cmd)
        produced = tmp_path / "video.mp4"
        produced.write_bytes(b"x")
        if on_progress:
            on_progress({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
            on_progress({"status": "finished", "filename": str(produced)})
        return str(produced)

    seen: list[float] = []
    path = ingest.download_url("https://example.com/v", tmp_path,
                               on_progress=seen.append, runner=fake_runner)
    assert path == tmp_path / "video.mp4"
    assert seen == [0.5, 1.0]
    assert "yt-dlp" in calls[0][0] or "yt_dlp" in calls[0][0]


def test_run_keeps_child_stderr_when_a_byte_cannot_be_decoded():
    """_run() must keep the child's diagnostic even if stderr holds a bad byte.

    ffmpeg/ffprobe emit UTF-8, but `text=True` without `encoding=` decodes with
    the *locale* codec (cp1252 on this machine). The Vietnamese sequences this
    project meets daily encode as E1 BB xx, and cp1252 leaves exactly five bytes
    undefined: 0x81, 0x8D, 0x8F, 0x90, 0x9D. So a filename holding e.g. "o" with
    dot below or "e" with circumflex and grave kills the subprocess reader
    thread: `exc.stderr` comes back as None and `(exc.stderr or '')` collapses
    the reason to nothing -- the job still fails, but the "why" is lost.

    This test is environment-independent by construction. The child writes the
    single byte 0x8D, which is BOTH undefined in cp1252 AND an invalid
    standalone byte in UTF-8, so the decode fails under either locale. With
    `encoding="utf-8", errors="replace"` it is absorbed and replaced either way.
    An explicit `encoding=` would also work if the locale were UTF-8, but here
    the locale is the bug, so the test cannot lean on it.

    Note the assertion that matters is the stderr CONTENT, not the exception
    type: without the fix _run still raises IngestError, just an empty one.
    """
    # bytes([0x8d]) rather than a "\x8d" string literal: a literal would be
    # rewritten into a real U+008D character while this source is read, and the
    # child would then reject it as a non-ASCII byte literal.
    child = (
        "import sys; "
        "sys.stderr.buffer.write(b'stderr-before' + bytes([0x8d]) + b'stderr-after'); "
        "sys.exit(1)"
    )
    with pytest.raises(ingest.IngestError) as excinfo:
        ingest._run([sys.executable, "-c", child])

    message = str(excinfo.value)
    # ascii() in the messages: the failure path must stay printable on a cp1252
    # console, and `message` itself can hold non-ASCII text.
    assert "stderr-before" in message, f"child stderr was lost: {ascii(message)}"
    assert "stderr-after" in message, f"child stderr was lost: {ascii(message)}"
    # Proves the bad byte was REPLACED rather than dropped or swallowed whole:
    # errors="replace" maps an undecodable byte to U+FFFD.
    assert "stderr-before\ufffdstderr-after" in message, (
        f"the undecodable byte was not replaced in place: {ascii(message)}"
    )
