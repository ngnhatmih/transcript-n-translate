"""Kiểm `tach_nen` — hàm THUẦN, không cần GPU cho phần lớn bài.

Phần cần `demucs`/`torch` được đánh dấu `importorskip` để một image thiếu demucs không giết cả
suite (đúng lỗi đã xảy ra với `rapidocr` ở Task 3 — xem ledger).
"""
from __future__ import annotations

import pathlib
import subprocess

import numpy as np
import pytest


def _co_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


CAN_FFMPEG = _co_ffmpeg()


def _sr(n: int = 4410) -> int:
    return 44_100


def _nen(peak: float = 0.5, n: int = 4410) -> np.ndarray:
    """Nền giả `(2, N)`: sin nhỏ, nhân để có peak cho trước."""
    t = np.linspace(0, 0.1, n, dtype=np.float32)
    song = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    hai = np.stack([song, song * 0.8])
    return (hai * (peak / float(np.abs(hai).max()))).astype(np.float32)


def test_chuan_hoa_nen_ha_peak_ve_1():
    """Nền có peak > 1,0 (đo được trên dữ liệu thật: 1,2240) phải được chia về 1,0.

    Vì sao ghim: `htdemucs` xuất float KHÔNG chuẩn hoá, và `drums+bass+other` cộng lại vượt
    biên độ gốc. Không chuẩn hoá thì trộn `0,9/0,9` cho `+1,468 dB` và 87 mẫu kẹp.
    """
    from app.pipeline.tach_nen import chuan_hoa_nen

    goc = _nen(peak=1.224)
    ra, he_so = chuan_hoa_nen(goc)
    assert abs(float(np.abs(ra).max()) - 1.0) < 1e-5, float(np.abs(ra).max())
    assert abs(he_so - 1.224) < 1e-4, he_so
    # Dạng sóng phải GIỮ NGUYÊN tỉ lệ — chỉ đổi biên độ, không méo. So trên các mẫu
    # KHÁC 0: `_nen` là sin bắt đầu từ 0, nên mẫu đầu chia cho 0 ra `nan` (bài test
    # đầu của tôi mắc đúng lỗi đó — đo được `nan < 1e-06` ĐỎ).
    khac0 = goc[0] != 0
    ti_le = ra[0][khac0] / goc[0][khac0]
    assert float(np.std(ti_le)) < 1e-6, "chuẩn hoá phải là phép NHÂN MỘT HẰNG SỐ"


def test_chuan_hoa_nen_khong_dong_toi_nen_da_duoi_1():
    """Nền đã dưới 1,0 thì để nguyên — không hạ oan.

    Ghim để không ai "chuẩn hoá cho đều" rồi làm mọi video nhỏ đi: video có nền nhạc nhẹ phải
    giữ nguyên âm lượng, chỉ video có nền vượt biên độ mới bị hạ.
    """
    from app.pipeline.tach_nen import chuan_hoa_nen

    goc = _nen(peak=0.5)
    ra, he_so = chuan_hoa_nen(goc)
    assert he_so == 1.0
    assert np.array_equal(ra, goc)


def test_chuan_hoa_nen_voi_mang_toan_so_khong():
    """Mảng toàn 0 (đoạn im lặng) không được chia cho 0."""
    from app.pipeline.tach_nen import chuan_hoa_nen

    ra, he_so = chuan_hoa_nen(np.zeros((2, 100), dtype=np.float32))
    assert he_so == 1.0
    assert not np.any(np.isnan(ra))


def test_tron_cat_ve_do_dai_ngan_hon():
    """Lồng ngắn hơn nền (bình thường: bản dịch hết trước phim) thì cắt về lồng.

    Ghim BA thứ, và cả ba đều là SỐ ĐO ĐƯỢC viết thẳng — không đọc lại hằng số của
    module:
      · tỉ lệ 0,90/0,90 (đo được: peak −1,042 dB, 0 mẫu kẹp sau chuẩn hoá)
      · phép cắt về độ dài NGẮN HƠN (`remux` dựa vào đó để biết phải `apad` bao nhiêu)
      · công thức cộng

    🔴 Vì sao KHÔNG đọc `TY_NEN`/`TY_DUB` từ module (đo được): bản đầu của bài này làm
    vậy, rồi đột biến `TY_NEN = 0.90` -> `0.50` vẫn XANH — nó kiểm "công thức khớp với
    chính nó", không kiểm giá trị. Đó là pin giả, và đột biến đã chứng minh.
    """
    from app.pipeline.tach_nen import tron

    nen = _nen(peak=1.0, n=1000)
    dub = _nen(peak=0.5, n=600)
    ra = tron(nen, dub)
    assert ra.shape == (2, 600), ra.shape
    for c in range(2):
        for k in (0, 299, 599):
            mong = nen[c, k] * 0.90 + dub[c, k] * 0.90
            assert abs(float(ra[c, k]) - float(mong)) < 1e-6, (c, k, ra[c, k], mong)


def test_tron_voi_mang_rong_thi_nem():
    """Không có mẫu nào thì phải NÉM, không trả mảng rỗng — mảng rỗng đi tiếp sẽ thành
    một video không tiếng mà job vẫn báo `done`."""
    from app.pipeline.tach_nen import tron

    with pytest.raises(ValueError, match="không có mẫu nào"):
        tron(np.zeros((2, 0), dtype=np.float32), np.zeros((2, 0), dtype=np.float32))


def test_tron_voi_mang_mot_chieu_thi_nem():
    """Mảng 1 chiều là lỗi lập trình — ném ngay, đừng để `[:, :n]` ném IndexError mơ hồ."""
    from app.pipeline.tach_nen import tron

    with pytest.raises(ValueError, match="2 chiều"):
        tron(np.zeros(100, dtype=np.float32), np.zeros((2, 100), dtype=np.float32))


def test_doc_stereo_nhan_doi_kenh_mono(tmp_path):
    """Tệp mono phải thành `(2, N)` — nếu không, phép trộn broadcast sai và ra hình dạng lạ."""
    import soundfile as sf

    from app.pipeline.tach_nen import doc_stereo

    p = tmp_path / "m.wav"
    sf.write(str(p), np.zeros(1000, dtype=np.float32), 44_100)
    ra = doc_stereo(p)
    assert ra.shape == (2, 1000), ra.shape
    assert np.array_equal(ra[0], ra[1])


def test_doc_stereo_resample_khi_sai_sample_rate(tmp_path):
    """48 kHz phải được RESAMPLE về 44,1 kHz, không ném và không đọc sai.

    🔴 Bản đầu của bài này ghim `pytest.raises(ValueError)`. ĐÓ LÀ SAI, và đường
    thật đã chứng minh: `dub.py` ghi master ở **48 kHz**, `htdemucs` chỉ làm việc ở
    **44,1 kHz**, nên NÉM ở đây làm cả nhánh trộn nền chết ngay tại `dub-4.wav`.
    Không có tệp 44,1 kHz nào để đưa vào — resample là việc BẮT BUỘC của hàm đọc.

    ⚠️ `tach_nen()` thì VẪN phải ném khi sai sample rate: ở đó mảng là ĐẦU VÀO cho
    model, và `separate_tensor(wav, sr=N)` không resample hộ (ERRATA 5). Hai hàm
    nhau ở đúng điểm này, và đó là lý do cả hai bài cùng tồn tại.
    """
    import soundfile as sf

    from app.pipeline.tach_nen import SR_MODEL, doc_stereo

    p = tmp_path / "m.wav"
    # 0,1 s ở 48 kHz -> 0,1 s ở 44,1 kHz, tức 4410 mau (dung bang 0,1*44100).
    sf.write(str(p), np.zeros((4800, 2), dtype=np.float32), 48_000)
    ra = doc_stereo(p)
    assert ra.shape[0] == 2, ra.shape
    assert abs(ra.shape[1] - 4410) <= 2, (
        f"phai resample ve {SR_MODEL} Hz: 0,1 s = 4410 mau, do duoc {ra.shape[1]}")

def test_doc_stereo_cat_bot_khi_nhieu_hon_hai_kenh(tmp_path):
    """5.1 cắt còn 2 kênh đầu, không ném — video thật có thể là 5.1."""
    import soundfile as sf

    from app.pipeline.tach_nen import doc_stereo

    p = tmp_path / "m.wav"
    sf.write(str(p), np.zeros((1000, 6), dtype=np.float32), 44_100)
    ra = doc_stereo(p)
    assert ra.shape == (2, 1000), ra.shape


@pytest.mark.skipif(not CAN_FFMPEG, reason="cần ffmpeg")
def test_trich_audio_goc_ra_dung_sr_va_stereo(tmp_path):
    """Trích từ video phải ra đúng `SR_MODEL` và 2 kênh, kèm số giây ĐO ĐƯỢC."""
    import soundfile as sf

    from app.pipeline.tach_nen import SR_MODEL, trich_audio_goc

    video = tmp_path / "v.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1:r=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video)],
        check=True, capture_output=True)

    ra = tmp_path / "a.wav"
    giay = trich_audio_goc(video, ra)
    info = sf.info(str(ra))
    assert info.samplerate == SR_MODEL, info.samplerate
    assert info.channels == 2, info.channels
    assert 0.9 <= giay <= 1.1, giay


@pytest.mark.skipif(not CAN_FFMPEG, reason="cần ffmpeg")
def test_remux_giu_nguyen_do_dai_video_khi_audio_ngan_hon(tmp_path):
    """🔴 Bài quan trọng nhất tệp này: audio NGẮN hơn video KHÔNG được cắt mất phim.

    Đo được trên dữ liệu thật: thiếu `-af apad`, `-shortest` cắt theo audio ngắn nhất và
    `remux.mp4` chỉ còn 1150,866 s thay vì 1249,237 s — mất 98,4 giây cuối phim, không một
    dòng cảnh báo.
    """
    from app.pipeline.tach_nen import do_dai, remux

    video = tmp_path / "v.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=64x64:d=3:r=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video)],
        check=True, capture_output=True)

    # Audio CHỈ 1 giây cho video 3 giây — đúng hình dạng lỗi thật (dub ngắn hơn phim).
    ngan = tmp_path / "ngan.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=880:duration=1",
         "-ar", "48000", "-ac", "2", str(ngan)],
        check=True, capture_output=True)

    ra = tmp_path / "ra.mp4"
    remux(video, ngan, ra)
    dai_video = do_dai(video)
    dai_ra = do_dai(ra)
    assert abs(dai_ra - dai_video) < 0.15, (
        f"mất phim: video {dai_video:.3f} s nhưng ra {dai_ra:.3f} s — thiếu `-af apad`?")


def test_tach_nen_bat_buoc_demucs_va_sr_dung():
    """Bài cần `demucs` + GPU: chỉ chạy khi có. Sai sample rate phải NÉM kèm số đo.

    Không dùng `pytest.importorskip` cho cả tệp vì phần lớn bài ở đây là hàm thuần.
    """
    pytest.importorskip("demucs.api", reason="image không có demucs — bỏ qua, không giết suite")
    pytest.importorskip("torch")
    import soundfile as sf

    from app.pipeline.tach_nen import tach_nen

    p = pathlib.Path("/tmp/_sai_sr.wav")
    sf.write(str(p), np.zeros((1000, 2), dtype=np.float32), 48_000)
    with pytest.raises(ValueError, match="44100"):
        tach_nen(p)


def test_tron_nen_end_to_end_that_qua_handler(tmp_path):
    """🔴 NỢ 1: đường `tron_nen=True` chạy TRỌN, có video ra, không cần sửa tay.

    Đây là bài duy nhất chạm `DubHandler._tron_va_remux`. Trước nó, đường trộn nền chỉ được
    chứng minh BẰNG TAY trong container (job #36), không bằng test — nên ai đổi
    `tach_nen.py` hay `_tron_va_remux` sẽ không thấy gì đỏ cho tới khi chạy thật.

    Chạy được trên HOST vì `demucs==4.1.0` đã được khai vào `requirements-docker.txt` và cài
    vào `backend\\.venv`; trước đó bài này buộc phải `skip` và `_tron_nen_mac_dinh()` trên host
    trả `False` một cách giả tạo.

    Video 2 s, một dòng dịch 0–1 s. Kiểm BỐN thứ, và mỗi thứ là một cách hỏng khác nhau:
      · có tệp `dub-<tid>.mp4` (nhánh trộn nền thật sự chạy, không bị bỏ qua);
      · độ dài video ra BẰNG video gốc (thiếu `-af apad` thì mất phần đuôi — ERRATA 4);
      · audio trong tệp ra là `aac` 48 kHz 2 kênh (resample đúng, không để encoder tự quyết);
      · audio KHÔNG kẹp mẫu nào (nền `htdemucs` peak > 1,0 nên thiếu chuẩn hoá là kẹp).
    """
    pytest.importorskip("demucs.api", reason="cần demucs để tách nền")
    pytest.importorskip("torch")
    import json
    import subprocess

    import soundfile as sf
    from fastapi.testclient import TestClient

    from app.adapters.clock_system import SystemClock
    from app.adapters.persist.sqlite_repos import SqliteRepos
    from app.domain.models import Job, Segment
    from app.pipeline.dub import DubHandler

    if not CAN_FFMPEG:
        pytest.skip("cần ffmpeg")

    # Video 2 s CÓ tiếng (sine 440 Hz) và CÓ hình — nền phải tách được từ chính nó.
    video = tmp_path / "goc.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=2:r=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video)],
        check=True, capture_output=True)

    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    sid = r.add_source(kind="file", origin="a", media_path=str(video), lang="zh")
    tid = r.add_transcript(source_id=sid, engine="fw", lang="zh",
                           segments=[Segment(i=0, start=0.0, end=1.0, text="你好")])
    ban_id = r.add_translation(transcript_id=tid, transcript_version=1, engine="x",
                               target_lang="vi", prompt_version="p1",
                               segments=[Segment(i=0, start=0.0, end=1.0, text="Xin chào")])

    def tts_gia(items, voice, out_dir):
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ra = {}
        for it in items:
            p = out_dir / f"{it['i']:05d}.wav"
            sf.write(str(p), np.full(48_000, 0.3, dtype=np.float32), 48_000)
            ra[it["i"]] = {"i": it["i"], "seconds": 1.0, "path": str(p)}
        return ra

    out = tmp_path / "dubs"
    h = DubHandler(r, out, tts_gia, tron_nen=True)
    job_id = r.add_job(Job(id=None, workspace=2, type="dub", engine="vieneu-v3-turbo",
                           phase="dub:vieneu-v3-turbo",
                           payload={"translation_id": ban_id, "tron_nen": True}))
    h.run(r.get_job(job_id), lambda p, line: None)

    mp4 = out / f"dub-{ban_id}.mp4"
    assert mp4.is_file() and mp4.stat().st_size > 0, (
        f"thiếu {mp4.name} — nhánh trộn nền không chạy; có: {[p.name for p in out.iterdir()]}")

    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
         str(mp4)], capture_output=True, text=True, check=True).stdout)
    dai_video = float(info["format"]["duration"])
    dai_goc = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(video)], capture_output=True, text=True, check=True).stdout.strip())
    assert abs(dai_video - dai_goc) < 0.15, (
        f"mất phim: gốc {dai_goc:.3f} s nhưng ra {dai_video:.3f} s — thiếu `-af apad`?")

    audio = [s for s in info["streams"] if s["codec_type"] == "audio"][0]
    assert audio["codec_name"] == "aac", audio["codec_name"]
    assert int(audio["sample_rate"]) == 48_000, audio["sample_rate"]
    assert int(audio["channels"]) == 2, audio["channels"]

    # Giải mã audio trong tệp ra và đếm mẫu kẹp.
    giai = tmp_path / "kiem.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp4),
                    "-vn", "-acodec", "pcm_f32le", "-ar", "48000", "-ac", "2", str(giai)],
                   check=True, capture_output=True)
    mau, _ = sf.read(str(giai), dtype="float32", always_2d=True)
    assert float(np.abs(mau).max()) < 1.0, (
        f"audio kẹp trần: peak {float(np.abs(mau).max()):.6f} — nền chưa chuẩn hoá?")
