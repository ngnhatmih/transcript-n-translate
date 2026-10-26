"""Lồng tiếng: mỗi dòng phụ đề → một take TTS → ép về timeline → xuất file.

## Ba thứ ở đây, và vì sao chỉ ba

1. `ke_hoach_toc_do` — chọn MỘT tốc độ gần đều cho mọi dòng (thang bậc), thay vì mỗi dòng một
   tốc độ. Đo trên 14 dòng thật của clip 20:49: `take/chỗ` rải từ 1,00× tới 1,62×; mỗi dòng một
   tốc độ thì người nghe thấy giọng đổi nhịp liên tục, còn MỘT tốc độ chung thì phải lấy mức lớn
   nhất (1,62×) và mọi dòng đều bị đọc nhanh. Thang bậc là điểm giữa: chỉ 2–4 giá trị.
2. `trong_im_lang` — cắt im lặng đầu/cuối của take. MIỄN PHÍ: không đổi tốc độ, chỉ bỏ phần TTS
   tự đệm (10–15% của một dòng 1,5 s).
3. `rap` — đặt từng take vào canvas tại ĐÚNG `start` của nó. `start/end` là số của mình, không
   phải của model: đây là chỗ duy nhất quyết định "đúng timestamp".

## `ponytail:` trần của bản này

* Mỗi take cần MỘT lời gọi `ffmpeg` để đổi tốc độ (`atempo`) — 461 dòng ≈ 461 tiến trình. Đo rồi
  hẵng tối ưu; cách thay thế là một tiến trình ffmpeg với `filter_complex` cho cả clip.
* KHÔNG trộn với tiếng gốc (ducking): bản này xuất bản lồng SẠCH. Trộn là một `amix` khi có yêu
  cầu.
* KHÔNG gọi engine dịch lại khi take vượt trần — nó chỉ TRẢ VỀ danh sách dòng phải sửa.
"""
from __future__ import annotations

import pathlib
import subprocess

import numpy as np

TOC_DO_TRAN = 1.35
BAC_TOC_DO = 0.05
NGUONG_IM_LANG = 0.01


def ke_hoach_toc_do(takes: list[float], slots: list[float], avails: list[float], *,
                    tran: float = TOC_DO_TRAN, bac: float = BAC_TOC_DO
                    ) -> tuple[list[float], list[float], list[int]]:
    """Tốc độ cho từng dòng + danh sách dòng KHÔNG cứu được bằng tốc độ.

    `avails[i]` = từ `start` của dòng tới `start` của dòng kế (được mượn khoảng lặng giữa hai
    dòng). `need_i = take_i / min(slot_i, avail_i)` là tốc độ TỐI THIỂU để dòng đó không đè dòng
    sau. Thang bậc: chọn bậc nhỏ nhất ≥ `need_i`, nên tốc độ chỉ rơi vào các mốc cách nhau `bac`.

    Trả về `(toc_do, need, qua_tran)`; `qua_tran` là các chỉ số có `need > tran` — những dòng đó
    phải sửa chữ, và bị gán `tran` (không nén quá trần).
    """
    need: list[float] = []
    for take, slot, avail in zip(takes, slots, avails):
        # Cua so cho phep = TROI tu start nay toi start cua dong sau: take duoc TRAI vao khoang
        # lang, nen tran la `max(slot, avail)` — KHONG phai `min`. (Lan dau toi viet `min` va bai
        # test bat duoc: muon 0,5 s lang ma van bao phai nen 1.35x.)
        cho = max(slot, avail) if avail > 0 else slot
        need.append(take / cho if cho > 0 else 1.0)
    qua_tran = [i for i, n in enumerate(need) if n > tran + 1e-9]
    toc_do: list[float] = []
    for n in need:
        n = min(n, tran)
        # bậc nhỏ nhất >= n, đo từ 1.0 theo bước `bac` (1.0 là sàn: không BAO GIỜ đọc chậm đi)
        so_bac = max(0, int(np.ceil((n - 1.0) / bac - 1e-9)))
        toc_do.append(round(1.0 + so_bac * bac, 4))
    return toc_do, need, qua_tran


def trong_im_lang(mau: np.ndarray, *, nguong: float = NGUONG_IM_LANG) -> np.ndarray:
    """Bỏ im lặng đầu/cuối. Không cắt im lặng GIỮA (đó là chỗ phải giữ để câu không bị dồn)."""
    lon = np.flatnonzero(np.abs(mau) > nguong)
    if lon.size == 0:
        return mau
    return mau[lon[0]:lon[-1] + 1]


def rap(takes: list[tuple[float, np.ndarray]], tong_giay: float, *, sr: int) -> np.ndarray:
    """Đặt các take vào canvas tại `start`. Take chồng nhau thì CỘNG mẫu (không đè mất)."""
    dai = max(1, int(round(tong_giay * sr)))
    ra = np.zeros(dai, dtype=np.float32)
    for start, mau in takes:
        dau = max(0, int(round(start * sr)))
        if dau >= dai:
            continue
        cuoi = min(dai, dau + mau.size)
        ra[dau:cuoi] += mau[:cuoi - dau]
    dinh = float(np.max(np.abs(ra))) if ra.size else 0.0
    if dinh > 1.0:  # chồng tiếng có thể vượt 1.0 -> kẹp, không để vỡ tiếng khi ghi PCM
        ra = ra / dinh
    return ra


def doi_toc_do(wav_vao: pathlib.Path, wav_ra: pathlib.Path, toc_do: float) -> None:
    """`atempo` của ffmpeg — chất lượng tốt hơn nội suy numpy ở cùng mức đổi tốc độ."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_vao),
         "-filter:a", f"atempo={toc_do:.4f}", str(wav_ra)],
        check=True, capture_output=True,
    )


DINH_DANG = {
    "wav": [],
    "flac": ["-c:a", "flac"],
    "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
    "aac": ["-c:a", "aac", "-b:a", "192k", "-f", "adts"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
}


def xuat_dinh_dang(master: pathlib.Path, out_dir: pathlib.Path,
                   dinh_dangs=DINH_DANG) -> dict[str, pathlib.Path]:
    """Xuất bản master ra mọi định dạng. Trả `{định dạng: đường dẫn}` — chỉ file TẠO ĐƯỢC."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ra: dict[str, pathlib.Path] = {}
    for ten, tham_so in dinh_dangs.items():
        dich = out_dir / f"{master.stem}.{ten}"
        if ten == "wav":
            dich.write_bytes(master.read_bytes())
        else:
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(master), *tham_so, str(dich)],
                           check=True, capture_output=True)
        ra[ten] = dich
    return ra
