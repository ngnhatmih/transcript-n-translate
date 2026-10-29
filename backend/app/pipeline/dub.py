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

from app.worker import JobCancelled

NGUONG_IM_LANG = 0.01


def ke_hoach_toc_do(takes: list[float], slots: list[float], avails: list[float]
                    ) -> tuple[list[float], list[float]]:
    """Tốc độ cho từng dòng, và `need` (tốc độ tối thiểu) để chẩn đoán.

    `avails[i]` = từ `start` của dòng tới `start` của dòng kế. `need_i = take_i /
    max(slot_i, avail_i)` là tốc độ TỐI THIỂU để dòng đó không đè dòng sau — tức
    ràng buộc CỨNG của sản phẩm.

    🔴 VÌ SAO BỎ TRẦN VÀ BỎ THANG BẬC (đổi hành vi, có chủ):
    Bản cũ kẹp `need` ở `TOC_DO_TRAN = 1.35` và trả thêm `qua_tran`. Đo được hệ quả: dòng
    vượt trần VẪN chồng sang dòng sau (vì 1,35 không đủ), và mã chỉ báo "phải sửa chữ".
    Người dùng chốt hai điều trái với cách đó: (a) không chồng lấn là điều kiện ĐÚNG/SAI;
    (b) "ko cần phải cắt mà chỉnh tốc độ là được". Nên nay nén tới ĐÚNG mức cần, không cắt
    chữ, không kẹp trần.

    Thang bậc (`BAC_TOC_DO`) cũng bỏ: nó tồn tại để giữ tốc độ "gần đều", nhưng bậc nhỏ hơn
    `need` sẽ GÂY chồng — tức phá ràng buộc cứng để giữ một mong muốn. Đổi lại, phần lớn dòng
    nay ở đúng 1,0× (khi take ngắn hơn chỗ), nên tốc độ thực tế đều hơn cả bản cũ.

    `need_i` có thể > 1 rất nhiều khi hai dòng quá sát nhau; đó là dữ liệu, không phải lỗi —
    xem `_ghi_ke_hoach` (đếm `nen_manh`).
    """
    need: list[float] = []
    for take, slot, avail in zip(takes, slots, avails):
        # Cua so cho phep = TROI tu start nay toi start cua dong sau: take duoc TRAI vao khoang
        # lang, nen lay `max(slot, avail)` — KHONG phai `min`.
        cho = max(slot, avail) if avail > 0 else slot
        need.append(take / cho if cho > 0 else 1.0)
    toc_do = [max(1.0, n) for n in need]
    return toc_do, need


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

# ───────────────────────── Handler của worker ─────────────────────────

class DubHandler:
    """Job `dub`: TTS một bản dịch → ép timeline → xuất file theo định dạng yêu cầu.

    `tts_runner(dong, voice, out_dir) -> {i: {"path":..., "seconds":...}}` là một THAM SỐ,
    không phải import: TTS nằm ở venv riêng (xem `scripts/tts_batch.py`) và test phải chạy
    được mà không cần cài VieNeu.

    ⚠️ `out_dir` do HANDLER cấp, không do runner tự tạo — và đây là một lỗi ĐÃ ĐO ĐƯỢC, không
    phải kiểu cách. Bản đầu để runner tự dựng `TemporaryDirectory` bên trong nó rồi trả về
    đường dẫn tới các wav trong đó. Thư mục ấy bị xoá NGAY khi runner trả về, nên `run()` đọc
    `lay[s.i]["path"]` sau đó là đọc một tệp đã biến mất. Đo được trên máy Windows thật:
    `LibsndfileError: Error opening '…\\Temp\\tts-5cs2do_f\\wav\\00000.wav': System error`; và
    đo cô lập đúng khuôn `with TemporaryDirectory(...)` cho `trong with: ton tai = True`,
    `sau with: ton tai = False`. Trên Linux lỗi sẽ là `No such file`.
    Hợp đồng nay là: **đường dẫn runner trả về phải còn sống khi `run()` đọc nó**, và cách duy
    nhất để bảo đảm điều đó là thư mục do chính `run()` sở hữu.
    """

    def __init__(self, repos, out_dir: pathlib.Path, tts_runner, *,
                 dinh_dangs=None,
                 python: str = "", script: str = "") -> None:
        self._repos = repos
        self._out_dir = pathlib.Path(out_dir)
        self._tts = tts_runner
        self._dinh_dangs = dinh_dangs or DINH_DANG
        # Đường của tiến trình TTS — CHỈ để `san_sang()` trả lời được "máy này có TTS chưa".
        # Vắng (`""`) thì `san_sang()` trả `True`: một handler tự dựng trong test (với runner
        # giả) là một handler KHÔNG có ý kiến gì về môi trường, và đoán hộ nó là bịa.
        self._python = python
        self._script = script

    def san_sang(self) -> tuple[bool, str]:
        """Đường TTS có chạy được trong TIẾN TRÌNH NÀY không — và nếu không thì vì sao.

        Trả `(True, "")` khi dùng được. Trả `(False, câu_tiếng_Việt)` khi không, và câu đó
        phải nêu ĐÚNG thứ đang thiếu, vì nó là câu người dùng đọc được ở `409` của route.

        Vì sao cần phép dò này chứ không để handler nổ lúc chạy: TTS sống ở một venv RIÊNG
        (`.venv-tts`, `vieneu` không cài được vào venv của app — xem README), nên "máy này có
        TTS" là một sự thật của MÔI TRƯỜNG, không phải của mã. Đo được: trong image Linux
        `docker compose up`, đường dẫn mặc định là `…/Scripts/python.exe` — một đường WINDOWS —
        nên job `dub` được nhận, chạy tới 5%, rồi `failed`; người dùng chỉ biết sau khi chờ.
        Từ chối NGAY LÚC XẾP JOB là cùng khuôn với `409 "engine chưa sẵn sàng"` của đường dịch.

        ⚠️ Phép dò KHÔNG chạy thử TTS (một lượt nạp model 63 s trong một route HTTP là không
        được): nó chỉ hỏi tệp thực thi có tồn tại, và `tts_batch.py` có đi kèm không.

        ⚠️ KHÔNG khai đường dẫn ⇒ `(True, "")`. Một handler tự dựng trong test (runner GIẢ) là
        một handler KHÔNG có ý kiến gì về môi trường; phán hộ nó là bịa, và phán SAI thì mọi bài
        route ở `tests/test_dub_handler.py` đỏ vì một lý do không liên quan tới chúng. Đo được
        đúng ca này: bản đầu dùng `pathlib.Path("").is_file()` — luôn `False` — nên handler
        không khai gì cũng bị coi là "máy chưa có TTS".
        """
        if not self._python:
            return True, ""
        python = pathlib.Path(self._python)
        if not python.is_file():
            return False, (
                f"máy này chưa có TTS: không thấy {python} — "
                f"tạo venv riêng rồi cài `pip install vieneu` vào đó "
                f"(xem backend/README.md mục Lồng tiếng), hoặc đặt PHUDE_TTS_PYTHON "
                f"trỏ tới python của venv đó"
            )
        script = pathlib.Path(self._script)
        if not script.is_file():
            return False, f"máy này chưa có TTS: không thấy script {script}"
        return True, ""

    def handles(self) -> str:
        """Loại job mà handler này nhận.

        ⚠️ KHÔNG phải trang trí: `routes_jobs._registered_job_types` hỏi `handles()` trên MỌI
        handler để biết loại job nào có đường chạy THẬT trong tiến trình này. Thiếu nó thì
        `POST /api/jobs` nổ `AttributeError: 'DubHandler' object has no attribute 'handles'`
        — đo được: 8 bài `test_api_export_by_translation.py` ĐỎ vì chúng đi qua chính route đó,
        không phải vì route xuất file có lỗi.
        """
        return "dub"

    def run(self, job, report) -> None:
        import soundfile as sf

        payload = job.payload or {}
        tid = int(payload["translation_id"])
        voice = payload.get("voice") or None
        gioi_han = payload.get("so_dong") or None

        ban = self._repos.get_translation(tid)
        dong = [s for s in ban.segments if (s.text or "").strip()]
        if gioi_han:
            dong = dong[: int(gioi_han)]
        if not dong:
            raise RuntimeError(f"bản dịch {tid} không có dòng nào để lồng tiếng")
        report(0.05, f"lồng tiếng bản dịch #{tid}: {len(dong)} dòng"
                     + (f" (giới hạn {gioi_han} dòng)" if gioi_han else ""))

        # THƯ MỤC TẠM DO HANDLER SỞ HỮU, không phải do runner: runner trả về ĐƯỜNG DẪN, và
        # đường dẫn chỉ dùng được khi thư mục còn sống. Bản đầu để runner tự dựng
        # `TemporaryDirectory` — nó xoá thư mục ngay khi trả về, nên mọi lần đọc take sau đó
        # đều trỏ vào hư không (đo được: `LibsndfileError: … System error`).
        import tempfile

        with tempfile.TemporaryDirectory(prefix="dub-") as tam:
            tam = pathlib.Path(tam)
            lay = self._tts([{"i": s.i, "text": s.text} for s in dong], voice, tam)
            if not lay:
                raise RuntimeError("TTS không trả về take nào")
            report(0.40, f"TTS xong {len(lay)}/{len(dong)} take")

            dung = [s for s in dong if s.i in lay]
            takes = [lay[s.i]["seconds"] for s in dung]
            slots = [max(0.01, s.end - s.start) for s in dung]
            avails = [(dung[k + 1].start if k + 1 < len(dung) else dung[k].end) - dung[k].start
                      for k in range(len(dung))]
            toc_do, need = ke_hoach_toc_do(takes, slots, avails)

            sr = 48_000
            dat: list[tuple[float, np.ndarray]] = []
            for k, s in enumerate(dung):
                if self._bi_huy(job):
                    raise JobCancelled(f"job {job.id} đã được yêu cầu huỷ")
                mau, sr = sf.read(lay[s.i]["path"], dtype="float32", always_2d=False)
                if mau.ndim > 1:
                    mau = mau.mean(axis=1)
                mau = trong_im_lang(mau)
                if abs(toc_do[k] - 1.0) > 1e-6:
                    sped = tam / f"{s.i:05d}-x.wav"
                    doi_toc_do(pathlib.Path(lay[s.i]["path"]), sped, toc_do[k])
                    mau, sr = sf.read(str(sped), dtype="float32", always_2d=False)
                    if mau.ndim > 1:
                        mau = mau.mean(axis=1)
                dat.append((s.start, mau.astype(np.float32)))
                report(0.40 + 0.50 * (k + 1) / len(dung),
                       f"đặt dòng {k + 1}/{len(dung)} · {toc_do[k]:.2f}×")

        master = rap(dat, max(s.end for s in dung), sr=sr)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        master_path = self._out_dir / f"dub-{tid}.wav"
        sf.write(str(master_path), master, sr, subtype="PCM_16")

        # KẾ HOẠCH TỐC ĐỘ, ghi cạnh master: bảng dòng của màn Lồng tiếng cần `take`, `chỗ`,
        # tốc độ và trạng thái của TỪNG dòng — bốn số chỉ tồn tại trong lượt chạy này. Không ghi
        # ra thì giao diện chỉ có thể bịa, hoặc phải chạy lại TTS (5–7 phút) để xem lại một lượt
        # đã xong. Tệp là DẪN XUẤT của lượt chạy, không phải nguồn sự thật thứ hai: xoá nó đi
        # thì route trả `null` và giao diện nói "chưa có số đo", KHÔNG bịa số.
        self._ghi_ke_hoach(tid, dung, takes, slots, avails, toc_do, need)

        report(0.92, f"xuất {len(self._dinh_dangs)} định dạng")
        xuat_dinh_dang(master_path, self._out_dir, self._dinh_dangs)
        manh = [k for k, s in enumerate(toc_do) if s > 1.5]
        if manh:
            report(1.0, f"xong · {len(manh)} dòng phải nén trên 1,5× (đã nén đủ để không "
                        f"chồng, không cắt chữ): " + ", ".join(str(dung[k].i) for k in manh))
        else:
            report(1.0, "xong")

    def _ghi_ke_hoach(self, tid: int, dung, takes, slots, avails, toc_do, need) -> None:
        """Ghi `dub-<tid>.plan.json`: số đo của TỪNG dòng cho bảng ở màn Lồng tiếng.

        `trang_thai` là HAI câu khác nhau, không phải ba:
          * `vua`      — take ≤ chỗ, không phải nén;
          * `nen`      — take > chỗ, đã nén ĐỦ để không chồng sang dòng sau.

        🔴 Bản cũ có trạng thái thứ ba `phai-sua` ("nén tới trần vẫn tràn ⇒ phải sửa chữ").
        Trạng thái đó biến mất cùng trần: nay không còn dòng nào "không cứu được bằng tốc độ",
        vì tốc độ không bị kẹp. `nen_manh` là con số CHẨN ĐOÁN (> 1,5×, mức khó nghe), không
        phải trạng thái chặn.

        Ghi bằng `ensure_ascii=False` để tệp đọc được bằng mắt khi cần chẩn đoán.
        """
        import json as _json

        dong = []
        for k, s in enumerate(dung):
            dong.append({
                "i": s.i,
                "start": round(float(s.start), 3),
                "end": round(float(s.end), 3),
                "text": s.text,
                "take": round(float(takes[k]), 3),
                "slot": round(float(slots[k]), 3),
                "avail": round(float(avails[k]), 3),
                "speed": round(float(toc_do[k]), 3),
                "need": round(float(need[k]), 3),
                "trang_thai": "nen" if need[k] > 1.0 + 1e-9 else "vua",
            })
        so_vua = sum(1 for d in dong if d["trang_thai"] == "vua")
        so_nen = sum(1 for d in dong if d["trang_thai"] == "nen")
        so_manh = sum(1 for d in dong if d["speed"] > 1.5)
        trung_vi = float(np.median([d["speed"] for d in dong])) if dong else 0.0
        ke_hoach = {
            "translation_id": tid,
            "tong_giay": round(float(max(s.end for s in dung)), 3),
            "so_dong": len(dong),
            "dem": {"vua": so_vua, "nen": so_nen, "nen_manh": so_manh},
            "trung_vi_toc_do": round(trung_vi, 3),
            "dong": dong,
        }
        (self._out_dir / f"dub-{tid}.plan.json").write_text(
            _json.dumps(ke_hoach, ensure_ascii=False, indent=1), encoding="utf-8")

    def _bi_huy(self, job) -> bool:
        try:
            return bool(self._repos.get_job(job.id).cancel_requested)
        except LookupError:
            return False


#: Dòng stderr bị COI LÀ RÁC: cảnh báo của WSL khi nó không đọc được `/proc/1/stat` của tiến
#: trình con. Chúng xuất hiện TRƯỚC thông điệp thật và chiếm hàng trăm ký tự.
#:
#: ⚠️ ĐO ĐƯỢC (job `dub` #21 trong container): `error` dài **472 ký tự**, và 400 ký tự sau là
#: `UtilGetPpid:1359: Failed to parse: /proc/1/stat, content: 1 (python) S 0 1 1 0 -1 4194560
#: 17042 6671 …` — rác WSL, không phải lỗi TTS. Bản trước lấy `stderr[-800:]`, tức lấy ĐUÔI:
#: nó giữ đúng khối rác và có thể CẮT MẤT câu chẩn đoán ở đầu. Trên panel phải, khối rác đó
#: chiếm 8 dòng và đẩy job thành công ra khỏi tầm mắt.
_RAC_STDERR = ("/proc/1/stat", "UtilGetPpid", "WSL (")


def _dong_loi_dau_tien(stderr: str | None, stdout: str | None, *,
                       toi_da: int = 300) -> str:
    """Chọn DÒNG ĐẦU TIÊN CÓ Ý NGHĨA của stderr, thay vì cả khối (hay đuôi khối).

    Ba bậc, theo thứ tự:
      1. Dòng đầu của `stderr` KHÔNG khớp `_RAC_STDERR` — đó là câu chẩn đoán thật.
      2. Không có dòng nào như vậy ⇒ dòng đầu của `stdout` (một số chương trình in lỗi ra đó).
      3. Cả hai rỗng ⇒ nói RA là rỗng, không trả chuỗi trắng để người đọc tưởng có lỗi mà
         không thấy lý do.

    `toi_da` cắt câu trả về: một dòng lỗi dài 5 000 ký tự cũng là thứ không đọc được trên panel.
    Cắt ở ĐÂY (một chỗ) chứ không ở component — component không biết chuỗi nào là rác.
    """
    for nguon in (stderr, stdout):
        if not nguon:
            continue
        for dong in nguon.splitlines():
            dong = dong.strip()
            if not dong:
                continue
            if any(rac in dong for rac in _RAC_STDERR):
                continue
            return dong[:toi_da]
    return "(không có đầu ra)"


def chay_tts_batch(tts_python: str, tts_script: pathlib.Path):
    """`tts_runner` thật: MỘT tiến trình cho cả lượt, JSON vào/ra qua TỆP (encoding console).

    `out_dir` do BÊN GỌI cấp (xem `DubHandler.run`) và KHÔNG bị hàm này xoá: đường dẫn trả về
    phải còn sống khi handler đọc nó. Chỉ hai tệp JSON (`viec`/`kq`) nằm trong thư mục tạm, và
    chúng bị xoá ngay — hợp đồng là các WAV, không phải các tệp điều khiển.
    """
    import json as _json
    import tempfile as _tempfile

    def chay(items: list[dict], voice: str | None, out_dir) -> dict[int, dict]:
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        with _tempfile.TemporaryDirectory(prefix="tts-json-") as tam:
            tam = pathlib.Path(tam)
            viec, kq = tam / "viec.json", tam / "kq.json"
            viec.write_text(_json.dumps({"items": items, "voice": voice,
                                         "out_dir": str(out_dir), "result": str(kq)},
                                        ensure_ascii=False), encoding="utf-8")
            r = subprocess.run([tts_python, "-B", str(tts_script), str(viec)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if not kq.exists():
                raise RuntimeError(
                    f"TTS không chạy được ({tts_python}): "
                    f"{_dong_loi_dau_tien(r.stderr, r.stdout)}")
            data = _json.loads(kq.read_text(encoding="utf-8"))
        if data.get("loi"):
            raise RuntimeError("TTS lỗi: " + "; ".join(
                f"dòng {x['i']}: {x['error']}" for x in data["loi"][:3]))
        return {x["i"]: x for x in data["ok"]}
    return chay
