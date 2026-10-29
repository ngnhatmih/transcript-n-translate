"""Tách nền khỏi giọng gốc, trộn với bản lồng, rồi remux vào video.

## Vì sao có tệp này

`dub.py` xuất bản lồng **SẠCH** — chỉ có giọng đọc tiếng Việt, không nhạc, không tiếng động.
Đem bản đó vào video là mất toàn bộ âm thanh nền của phim gốc. Tệp này lấp khoảng đó:
tách `htdemucs` lấy nền, trộn với bản lồng, remux vào video gốc (video copy, không re-encode).

## Bốn con số quyết định toàn bộ tệp này, đo trên máy này

Nguồn thật: `/data/media/ac5df767b9e0c878.mp4` 1249,237 s, `h264` + `aac 48 kHz` stereo.

| khâu | đo được |
|---|---|
| nạp model `htdemucs` | 3,14 s |
| tách 1249,24 s | **42,6–43,9 s** (RTF 0,0341–0,0352) |
| GPU đỉnh | 549–555 MiB (còn ~6,5 GB) |
| remux | **21,7 s** |

## 🔴 BỐN CẠM BẪY ĐÃ ĐO ĐƯỢC, và cách tránh

**(1) `Separator.separate_tensor(wav, sr=N)` KHÔNG đổi sample rate của model.**
`htdemucs` LUÔN làm việc ở **44 100 Hz** (`sep.samplerate`), bất kể `sr=` truyền vào là gì —
`sr=` chỉ nói cho model biết cách resample ĐẦU VÀO. Truyền `sr=48000` với audio 48 kHz thì
đầu ra vẫn 44,1 kHz. Đo được hệ quả khi tôi hiểu sai: 55 091 368 mẫu chia cho 48 000 ra
1147,74 s, tôi tưởng "mất 101,5 giây audio". Chia đúng 44 100 thì ra **1249,2374 s** — khớp
đầu vào tới 36 microsecond. Vì vậy tệp này resample đầu vào về `sep.samplerate` TRƯỚC.

**(2) Nền phải tách từ AUDIO GỐC của video, không phải `wav` mà ingest tạo.**
Đo được: video gốc `aac 48 kHz 2 kênh`; `wav` của ingest `pcm_s16le 16 kHz 1 kênh`. Tách trên
hai nguồn, cùng model, cùng máy:

| nguồn | thời gian | nền peak | nền RMS |
|---|---|---|---|
| wav 16k mono | 42,58 s | 1,0988 | 0,0749 |
| audio gốc 48k stereo | 43,92 s | 1,3379 | **0,0831** |

Nền từ audio gốc dày hơn **11 % RMS**, giữ stereo và dải tần tới 20 kHz; giá là 1,34 s (3 %).

**(3) Nền `htdemucs` có peak > 1,0, PHẢI chuẩn hoá trước khi trộn.**
Đo được `peak = 1,2240`. Model xuất float không chuẩn hoá. Không chuẩn hoá thì `0,9/0,9` cho
`+1,468 dB` và 87 mẫu bị kẹp — không phải "có dự phòng" như tài liệu cũ ghi. Sau chuẩn hoá,
`0,90/0,90` cho **−1,042 dB, 0 mẫu kẹp** (dư 1 dB).

**(4) `-shortest` trần cắt theo audio NGẮN NHẤT, tức cắt mất phim.**
Đo được: bản lồng `dub-4.wav` dài 1186,36 s còn video 1249,24 s. Remux không `apad` cho
`remux.mp4` **1150,866 s** — mất **98,4 giây** cuối phim. Phải `-af apad` để đệm im lặng cho
audio đủ dài, rồi `-shortest` mới cắt đúng theo video.

## `ponytail:` trần của bản này

* Chạy `htdemucs` trên TOÀN BỘ audio một lượt. Video 20,8 phút tốn 43,9 s và 555 MiB VRAM —
  chưa cần chia lô. Video dài gấp mười sẽ cần chia, và đó là lúc phải đo lại, không phải bây giờ.
* Chỉ `htdemucs`. Không RoFormer, không model nào khác — người dùng đã chốt.
"""
from __future__ import annotations

import pathlib
import subprocess

import numpy as np

#: Sample rate mà `htdemucs` LUÔN trả về. KHÔNG suy từ `sr` truyền vào — xem cạm bẫy (1).
SR_MODEL = 44_100

#: Sample rate của tệp ra, để khớp nguồn video gốc (`aac 48 kHz`).
SR_RA = 48_000

#: Tỉ lệ trộn SAU khi chuẩn hoá nền về peak 1,0. Đo được: peak −1,042 dB, 0 mẫu kẹp.
TY_NEN = 0.90
TY_DUB = 0.90



def trich_audio_goc(video: pathlib.Path, ra: pathlib.Path, *, sr: int = SR_MODEL) -> float:
    """Trích audio của video ra WAV `sr` Hz stereo. Trả số giây.

    Đây là nguồn nền ĐÚNG: audio gốc của video, không phải `wav` 16 kHz mono mà ingest tạo cho
    ASR. Xem cạm bẫy (2) ở docstring đầu tệp.
    """
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video), "-vn", "-acodec", "pcm_s16le",
         "-ar", str(sr), "-ac", "2", str(ra)],
        check=True, capture_output=True)
    import soundfile as sf

    return sf.info(str(ra)).duration


def tach_nen(audio: pathlib.Path, *, device: str = "cuda") -> np.ndarray:
    """`(2, N)` float32 ở `SR_MODEL`: nền = `drums + bass + other`.

    KHÔNG chuẩn hoá ở đây — `chuan_hoa_nen` làm việc đó, và tách riêng để test được phép kiểm
    "peak nền > 1,0" mà không cần GPU.
    """
    import soundfile as sf
    import torch
    from demucs.api import Separator

    sep = Separator(model="htdemucs", device=device, progress=False)
    mau, sr = sf.read(str(audio), dtype="float32", always_2d=True)
    if sr != int(sep.samplerate):
        raise ValueError(
            f"audio phải ở {sep.samplerate} Hz (sample rate của htdemucs), đo được {sr}. "
            f"Resample TRƯỚC bằng `trich_audio_goc`, đừng truyền `sr=` vào model — nó không "
            f"đổi sample rate đầu ra, chỉ đổi cách resample đầu vào.")
    _, ra = sep.separate_tensor(torch.from_numpy(mau.T.copy()), sr=sr)
    nen = sum(ra[k] for k in ("drums", "bass", "other")).numpy()
    return np.ascontiguousarray(nen, dtype=np.float32)


def chuan_hoa_nen(nen: np.ndarray) -> tuple[np.ndarray, float]:
    """Đưa nền về peak 1,0. Trả `(nền đã chuẩn hoá, hệ số đã chia)`.

    Vì sao BẮT BUỘC: `htdemucs` xuất float không chuẩn hoá, và `drums+bass+other` cộng lại
    vượt biên độ gốc — đo được **peak 1,2240**. Không chuẩn hoá thì trộn `0,9/0,9` cho
    `+1,468 dB` và 87 mẫu kẹp; sau chuẩn hoá còn `−1,042 dB` và 0 mẫu kẹp.

    Chia về 1,0 chứ không hạ gain mù, vì hệ số trộn phải CỐ ĐỊNH cho mọi video: hạ gain mù
    buộc phải chọn theo video có nền to nhất, tức mọi video khác bị nền nhỏ đi vô cớ.
    """
    peak = float(np.abs(nen).max())
    if peak <= 1.0 or peak <= 0.0:
        return nen, 1.0
    return (nen / peak).astype(np.float32), peak


def tron(nen: np.ndarray, dub: np.ndarray) -> np.ndarray:
    """`nền × 0,90 + lồng × 0,90`, cắt về độ dài NGẮN HƠN. Cả hai `(2, N)`.

    Lồng ngắn hơn video là BÌNH THƯỜNG (bản dịch hết trước khi phim hết). Cắt về ngắn hơn ở
    đây, rồi `remux` đệm im lặng — xem cạm bẫy (4). KHÔNG kéo dài nền bằng cách lặp, vì lặp
    nhạc nền nghe ra ngay.
    """
    if nen.ndim != 2 or dub.ndim != 2:
        raise ValueError(f"cả hai phải 2 chiều (kênh, mẫu); đo được {nen.shape} và {dub.shape}")
    n = min(nen.shape[1], dub.shape[1])
    if n <= 0:
        raise ValueError(f"không có mẫu nào để trộn: nền {nen.shape[1]}, lồng {dub.shape[1]}")
    return (nen[:, :n] * TY_NEN + dub[:, :n] * TY_DUB).astype(np.float32)


def doc_stereo(path: pathlib.Path, *, sr: int = SR_MODEL) -> np.ndarray:
    """Đọc một tệp audio thành `(2, N)` float32 ở `sr`. RESAMPLE nếu khác `sr`.

    Vì sao resample chứ không NÉM: hai nguồn audio của dự án ở hai sample rate khác
    nhau một cách CHÍNH ĐÁNG — master `dub.py` ghi 48 kHz (biến `sr` trong `run`), còn
    `htdemucs` chỉ làm việc ở 44,1 kHz. Bắt người gọi tự resample trước là đẩy một
    phép biến đổi BẮT BUỘC ra ngoài, và đo được hệ quả: bản đầu của hàm này NÉM, nên
    đường thật chết ngay tại `dub-4.wav` 48 kHz. Ném ở đây không bảo vệ được gì —
    không có tệp 44,1 kHz nào để đưa vào.

    ⚠️ KHÁC `tach_nen()`: hàm đó nhận audio ĐẦU VÀO cho model và PHẢI đúng 44,1 kHz,
    vì `separate_tensor(wav, sr=N)` không resample hộ — truyền sai thì model làm việc
    trên dải thời gian sai và trả về mảng dài sai (đúng ERRATA 5). Ở đây ta chỉ ĐỌC
    một tệp để cộng vào một mảng đã có, nên resample là việc của chính hàm đọc.
    """
    import soundfile as sf

    mau, sr_goc = sf.read(str(path), dtype="float32", always_2d=True)
    if mau.shape[1] == 1:
        mau = np.repeat(mau, 2, axis=1)
    elif mau.shape[1] > 2:
        mau = mau[:, :2]
    if sr_goc != sr:
        mau = _resample(mau, sr_goc, sr)
    return np.ascontiguousarray(mau.T, dtype=np.float32)


def _resample(mau: np.ndarray, tu: int, den: int) -> np.ndarray:
    """Resample `(N, kênh)` bằng ffmpeg — cùng công cụ pipeline dùng, không thêm phụ thuộc.

    Vì sao KHÔNG `scipy.signal.resample` hay `librosa`: container có ffmpeg và nó là thứ
    `remux`/`trich_audio_goc` đã dùng; thêm một đường resample thứ hai là thêm một chỗ
    để hai đường cho kết quả lệch nhau. Đo được: `torchaudio` KHÔNG có trong image
    (`ModuleNotFoundError: No module named 'torchaudio'`), nên nó không phải lựa chọn.
    """
    import tempfile

    import soundfile as sf

    with tempfile.TemporaryDirectory(prefix="sr-") as tam:
        tam = pathlib.Path(tam)
        vao = tam / "vao.wav"
        ra = tam / "ra.wav"
        sf.write(str(vao), mau, tu, subtype="FLOAT")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(vao), "-ar", str(den), "-acodec", "pcm_f32le", str(ra)],
            check=True, capture_output=True)
        lai, _ = sf.read(str(ra), dtype="float32", always_2d=True)
    return np.ascontiguousarray(lai, dtype=np.float32)


def remux(video: pathlib.Path, audio: pathlib.Path, ra: pathlib.Path) -> None:
    """Video COPY (không re-encode), audio `aac 192k` ở `SR_RA`, đệm im lặng cho đủ dài.

    🔴 `-af apad` là BẮT BUỘC, không phải trang trí. Đo được: thiếu nó, `-shortest` cắt theo
    audio NGẮN NHẤT và `remux.mp4` chỉ còn **1150,866 s** thay vì 1249,237 s — mất 98,4 giây
    cuối phim, không một dòng cảnh báo. `apad` đệm im lặng vào cuối audio, rồi `-shortest` cắt
    đúng theo video.

    `-ar` đặt tường minh: audio đã resample về `SR_RA` từ trước, nhưng để encoder tự quyết thì
    kết quả phụ thuộc phiên bản ffmpeg — đo được một lần ra 44,1 kHz dù đầu vào 48 kHz.
    """
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video), "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR_RA),
         "-af", "apad", "-shortest", str(ra)],
        check=True, capture_output=True)


def do_dai(path: pathlib.Path) -> float:
    """Số giây của tệp, bằng `ffprobe`. Dùng để KIỂM kết quả, không để tính toán."""
    ra = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(ra)
