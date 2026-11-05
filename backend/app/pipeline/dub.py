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


#: Hai LOP hien thi — MOT dinh nghia duy nhat, o domain.
#: Ban truoc khai lai o day ("trung ten voi nguon_chu.LOP_*") va do la cho sinh loi:
#: hai noi cung dinh nghia mot khai niem thi khong co gi bao chung lech nhau.
#: Van xuat ra duoi ten cu vi tests/test_dub.py va cac cho khac import chung.
from app.domain.nguon_chu import LOP_1, LOP_2
LOP_MOT_NGUON = LOP_1
LOP_HAI_NGUON = LOP_2
def mot_dong_moi_cap(segments: list) -> list:
    """LOC theo LOP: moi cap (OCR, ASR) cung noi mot cau chi giu MOT dong de long.

    ## Vi sao phai loc

    `nguon_chu.hop_nhat_theo_doan` giu CA HAI dong khi OCR va ASR cung doc/nghe ra mot
    cau (nguoi dung chot 2026-11-02: "chia 2 layer 2 dong"). Do la dung cho TIMELINE —
    nguoi doc thay duoc may nghe gi va doc gi.

    Nhung BAN LONG thi khong duoc doc hai lan. Rang buoc da chot tu dau: dong N khong
    duoc con noi khi N+1 bat dau, va moi cau chi noi MOT lan. Hai dong cung mot cau ma
    deu vao TTS thi ban long noi cau do hai lan chong len nhau.

    ## Giu dong nao

    * Cap co MOT dong LOP 1        -> giu dong do (bang chung chat nhat, va do la dong
      DUY NHAT co chu dung: dong con lai la ban sao).
    * Cap co HAI dong LOP 2        -> giu dong `suspect=False`, tuc dong OCR — OCR doc
      CHU DA BIEN TAP, con ASR nghe va hay sai ten rieng. Do duoc tren #36:

            ASR "你见过人类做海豹吗"   <- nghe sai (hai cau)
            OCR "你见过人类做海报吗"   <- doc dung (poster)

    * Dong khong co `layer` (du lieu cu) -> giu nguyen, khong doan bua.

    Phan biet "cung mot cau" bang CHONG THOI GIAN, khong bang chu: hai dong cung cap luon
    chong len nhau it nhat mot phan, va do la dau hieu duy nhat khong phu thuoc vao viec
    ASR nghe dung hay sai.
    """
    # Moi CAU chi giu MOT dong de long/xuat phu de. Uu tien dong OCR (lop tren).
    #
    # Nguoi dung: "toi chi bao dung phu de cua cai tren cua layer 1 chu co bao bo cai gi
    # dau". Nghia la: TIMELINE giu ca hai dong de soat, con PHU DE / BAN LONG chi lay dong
    # cua lop 1. Khong duoc bo dong nao khoi du lieu — chi chon dong nao duoc dung.
    #
    # "Cung mot cau" do bang CHONG THOI GIAN: hai dong cua cung mot cau luon chong len nhau.
    #
    # Trong mot cap:
    #   · co OCR (suspect=False) -> lay OCR. OCR doc CHU DA BIEN TAP; ASR nghe va hay sai
    #     ten rieng. Do duoc tren #36:
    #
    #         ASR "你见过人类做海豹吗"   <- nghe sai (hai cau)
    #         OCR "你见过人类做海报吗"   <- doc dung (poster)
    #
    #   · chi co ASR             -> lay ASR. Do la nguon DUY NHAT o doan do.
    #
    # Dong co `chua_trong >= 0` (logo / dong ghi cong nam gon trong mot cau) VAN duoc giu
    # trong du lieu; no chi khong duoc chon lam dai dien khi da co dong khac cung cap.
    ra = []
    da_dung: set[int] = set()
    for s in segments:
        if s.i in da_dung:
            continue
        cap = [x for x in segments if min(x.end, s.end) - max(x.start, s.start) > 0.0]
        for x in cap:
            da_dung.add(x.i)

        # Uu tien OCR; neu khong co thi ASR.
        ocr = [x for x in cap if not getattr(x, "suspect", False)]
        giu = ocr[0] if ocr else cap[0]
        ra.append(giu)

    return ra


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

#: Đuôi tệp mà route tải được, KHÔNG phải đuôi `xuat_dinh_dang` sinh ra.
#:
#: 🔴 Vì sao là HAI tập khác nhau (đo được): `DINH_DANG` là dict tham số `ffmpeg` để
#: chuyển MỘT master audio sang định dạng khác. `mp4` không thuộc loại đó — nó cần
#: VIDEO GỐC (`-c:v copy`) và chỉ tồn tại khi job chạy với `tron_nen`. Nhét `mp4` vào
#: `DINH_DANG` sẽ khiến `xuat_dinh_dang` gọi `ffmpeg -i master.wav -c:v copy dub-4.mp4`
#: và chết vì đầu vào không có stream video. Nhưng route vẫn phải TẢI được nó, nên
#: tập đuôi tải được là hợp của hai nguồn.
DUOI_TAI_DUOC = tuple(DINH_DANG) + ("mp4",)


def xuat_dinh_dang(master: pathlib.Path, out_dir: pathlib.Path,
                   dinh_dangs=DINH_DANG) -> dict[str, pathlib.Path]:
    """Xuất bản master ra mọi định dạng. Trả `{định dạng: đường dẫn}` — chỉ file TẠO ĐƯỢC."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ra: dict[str, pathlib.Path] = {}
    for ten, tham_so in dinh_dangs.items():
        dich = out_dir / f"{master.stem}.{ten}"
        if ten == "wav":
            #: 🔴 ĐỪNG CHÉP LÊN CHÍNH NÓ. `dich` ở đây CHÍNH LÀ `master` (master là
            #: `dub-{tid}.wav`), nên `write_bytes(read_bytes())` là một vòng đọc-ghi 24 MB
            #: vô nghĩa — và nó ĐỔI `mtime` của master. Hậu quả ĐO ĐƯỢC: cache bản trộn
            #: (`dub-{tid}.tron.wav`, khoá theo mtime master) KHÔNG BAO GIỜ trúng, nên mỗi
            #: lần đổi kiểu chữ vẫn chạy lại htdemucs (91 s thay vì phần burn+remux).
            if dich.resolve() != master.resolve():
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
                 python: str = "", script: str = "",
                 tron_nen: bool = False) -> None:
        self._repos = repos
        self._out_dir = pathlib.Path(out_dir)
        self._tts = tts_runner
        self._dinh_dangs = dinh_dangs or DINH_DANG
        #: `True` thi TRỘN NỀN trước khi xuất: tách `htdemucs` lấy nhạc/tiếng động của
        #: video gốc, cộng với bản lồng, rồi remux vào video. `False` (mặc định) giữ
        #: nguyên hành vi cũ — xuất bản lồng SẠCH, không đụng tới video. Đây là cờ
        #: MÔI TRƯỜNG: `demucs` chỉ có trong image có GPU, và một image thiếu nó vẫn
        #: phải lồng tiếng được.
        self._tron_nen = tron_nen
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
        # Cờ THEO JOB, không phải theo handler: `self._tron_nen` chỉ là mặc định của MÔI
        # TRƯỜNG (image có GPU hay không). Payload `null`/vắng = theo mặc định đó; `true` =
        # bắt buộc trộn dù mặc định tắt; `false` = chỉ bản lồng sạch.
        tron_nen = payload.get("tron_nen")
        if tron_nen is None:
            tron_nen = self._tron_nen
        #: Kiểu chữ phụ đề BURN vào video. Đi qua payload để giao diện và đường job dùng
        #: CÙNG một kiểu với bản xem trước trên web — hai nơi tự đặt kiểu riêng là hai
        #: nơi trôi khỏi nhau. `None` = mặc định của định dạng (từng byte như cũ).
        kieu_chu = payload.get("style") or None

        ban = self._repos.get_translation(tid)

        #: 🔴 `chi_tron` = GHÉP NỀN TỪ BẢN LỒNG ĐÃ CÓ, không chạy lại TTS.
        #
        # ĐO ĐƯỢC (chủ dự án: *"tại sao ấn ghép nền thì nó chạy lại cả lồng tiếng"*): trước
        # nhánh này, `run()` LUÔN gọi `self._tts(...)` ở dưới rồi mới tới `if tron_nen`. Nên
        # bấm "Ghép nền" (job `dub` + `tron_nen = true`) là chạy lại toàn bộ TTS — 5–7 phút
        # cho một việc mà đầu vào `dub-<tid>.wav` đã nằm sẵn trên đĩa.
        #
        # Ghép nền chỉ cần đúng hai thứ: master đã có, và chữ của bản dịch (để burn phụ đề).
        # Không có master thì NÉM, không lặng lẽ chạy lại TTS: người dùng bấm "ghép nền" chứ
        # không bấm "lồng lại", và biến một thao tác 1 phút thành 7 phút mà không nói gì là
        # đúng loại im lặng repo này xoá.
        master_path = self._out_dir / f"dub-{tid}.wav"
        if bool(payload.get("chi_tron")):
            if not master_path.is_file():
                raise RuntimeError(
                    f"chưa có bản lồng của bản dịch #{tid} ({master_path.name}) — "
                    "chạy Lồng tiếng trước rồi mới ghép nền")
            report(0.05, f"ghép nền từ bản lồng đã có: {master_path.name} "
                         f"({master_path.stat().st_size} byte) — không chạy lại TTS")
            self._tron_va_remux(tid, ban.transcript_id, master_path, report,
                                chu_dich=[s.text for s in (ban.segments or [])],
                                kieu_chu=kieu_chu)
            xuat_dinh_dang(master_path, self._out_dir, self._dinh_dangs)
            report(1.0, "xong · ghép nền (dùng lại bản lồng đã có)")
            return

        # LOC THEO LOP truoc khi long: timeline giu 2 dong de nguoi doc soat, nhung
        # ban long chi duoc noi MOT lan moi cau (xem `mot_dong_moi_cap`).
        dong = mot_dong_moi_cap([s for s in ban.segments if (s.text or "").strip()])
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

        if tron_nen:
            # `chu_dich` = chữ của BẢN DỊCH, truyền XUỐNG thay vì để `_tron_va_remux`
            # tự đọc lại: `run()` đã có `ban` trong tay (`ban.segments`), đọc lại là
            # một truy vấn thừa và một cơ hội để hai chỗ lệch nhau — cùng lý do
            # `transcript_id` được truyền vào chứ không tra lại.
            #
            # 🔴 ĐO ĐƯỢC, đây là lỗi đã có thật: bản đầu tôi viết `_tron_va_remux`
            # dùng thẳng biến `ban` của `run()`, nhưng nó KHÔNG nằm trong tầm với
            # (`NameError: name 'ban' is not defined`). Job vẫn xong nhờ `try/except`
            # quanh bước burn, nhưng `dub-1.mp4` ra 88,9 MB mà KHÔNG có chữ nào —
            # đúng kiểu hỏng im lặng mà một `except` rộng che mất.
            self._tron_va_remux(tid, ban.transcript_id, master_path, report,
                                chu_dich=[s.text for s in (ban.segments or [])],
                                kieu_chu=kieu_chu)

        report(0.92, f"xuất {len(self._dinh_dangs)} định dạng")
        xuat_dinh_dang(master_path, self._out_dir, self._dinh_dangs)
        manh = [k for k, s in enumerate(toc_do) if s > 1.5]
        if manh:
            report(1.0, f"xong · {len(manh)} dòng phải nén trên 1,5× (đã nén đủ để không "
                        f"chồng, không cắt chữ): " + ", ".join(str(dung[k].i) for k in manh))
        else:
            report(1.0, "xong")

    def _tron_va_remux(self, tid: int, transcript_id: int,
                       master: pathlib.Path, report,
                       chu_dich: list[str] | None = None,
                       kieu_chu: dict | None = None) -> None:
        """Trộn nền của VIDEO GỐC với bản lồng, rồi remux vào video.

        Chuỗi lấy video: `translation` -> `transcript` -> `source`. `transcript_id` được
        TRUYỀN VÀO chứ không tra lại từ `tid`: người gọi đã có `ban.transcript_id` trong
        tay, tra lại là một truy vấn thừa và một cơ hội để hai chỗ lệch nhau.

        Nguồn nền là `source.media_path` — VIDEO GỐC, không phải `audio_path` (wav 16 kHz
        mono của ASR). Đo được: nền tách từ audio gốc dày hơn 11 % RMS và giữ stereo;
        xem docstring `tach_nen.py` cạm bẫy (2).

        Không có video gốc (nguồn là audio thuần) thì BỎ QUA kèm một dòng log, không ném:
        lồng tiếng cho một tệp audio là nhu cầu hợp lệ, và bản lồng sạch đã nằm trên đĩa.
        """
        from app.pipeline import tach_nen

        transcript = self._repos.get_transcript(transcript_id)
        source = self._repos.get_source(transcript.source_id)
        video = pathlib.Path(source.media_path)
        if not video.is_file():
            report(0.90, f"bỏ qua trộn nền: không thấy video gốc ({video.name})")
            return

        import tempfile

        #: 🔴 CACHE BẢN TRỘN — tách nền (htdemucs) là phần ĐẮT NHẤT của bước ghép, và nó
        #: KHÔNG phụ thuộc kiểu chữ phụ đề.
        #:
        #: ĐO ĐƯỢC (chủ dự án: *"nhưng tại sao xuất phải chạy lại lồng tiếng và ghép nền?"*):
        #: đổi cỡ chữ rồi bấm Xuất thì job ghép chạy lại TỪ ĐẦU — 96 giây cho một việc mà
        #: đầu vào không đổi. Trong đó TTS đã được bỏ từ trước (`chi_tron`), còn lại phần
        #: đắt là tách nền + trộn.
        #:
        #: Khoá cache là `(master, video)`: bản trộn chỉ đúng khi master lồng tiếng và video
        #: gốc chưa đổi, nên so `mtime` của cả hai. Đổi kiểu chữ KHÔNG làm hai mốc đó đổi,
        #: nên lần ghép sau dùng lại `tron.wav` và chỉ còn burn phụ đề + remux.
        self._out_dir.mkdir(parents=True, exist_ok=True)
        cache_tron = self._out_dir / f"dub-{tid}.tron.wav"
        con_dung = (
            cache_tron.is_file()
            and cache_tron.stat().st_mtime >= master.stat().st_mtime
            and cache_tron.stat().st_mtime >= video.stat().st_mtime
        )

        with tempfile.TemporaryDirectory(prefix="nen-") as tam:
            tam = pathlib.Path(tam)
            import soundfile as sf

            if con_dung:
                report(0.90, f"dùng lại bản trộn đã có ({cache_tron.name}) — "
                             "chỉ burn lại phụ đề + remux")
                tron_path = cache_tron
            else:
                report(0.90, "tách nền khỏi tiếng gốc (htdemucs)")
                goc = tam / "goc.wav"
                tach_nen.trich_audio_goc(video, goc)
                nen = tach_nen.tach_nen(goc)
                nen, he_so = tach_nen.chuan_hoa_nen(nen)
                if he_so > 1.0:
                    report(0.93, f"nền vượt biên độ (peak {he_so:.3f}) — đã chuẩn hoá")

                dub = tach_nen.doc_stereo(master, sr=tach_nen.SR_MODEL)
                tron = tach_nen.tron(nen, dub)
                #: Ghi thẳng vào thư mục ra (không phải thư mục tạm) để lần sau dùng lại.
                sf.write(str(cache_tron), tron.T, tach_nen.SR_MODEL)
                tron_path = cache_tron

            report(0.95, "remux vào video gốc")
            ra = self._out_dir / f"dub-{tid}.mp4"

            # 🔴 BURN CỨNG phụ đề của BẢN DỊCH vào hình — yêu cầu sản phẩm: "video cuối
            # phải có phụ đề + lồng tiếng + nền đã tách". Trước bước này, `remux` chỉ
            # `-c:v copy` và `dub-<tid>.mp4` KHÔNG có chữ nào; phụ đề chỉ tồn tại dưới
            # dạng `.srt`/`.ass` RỜI, nên "video cuối có phụ đề" là một lời hứa không có
            # đường thực hiện.
            #
            # Sinh `.ass` bằng ĐÚNG `export.render()` mà ba nút xuất của giao diện dùng
            # — không tự ghép chuỗi ASS ở đây. Hai đường sinh phụ đề là hai chỗ để style,
            # thời điểm và cách thoát chữ trôi khỏi nhau; `render` đã là "cửa vào duy
            # nhất" theo docblock của nó.
            #
            # Chọn `.ass` chứ không `.srt`: `ass` giữ được style/karaoke mà `export.py`
            # đã sinh, còn `.srt` chỉ có chữ trần. Đây là bản BURN vào pixel, nên style
            # là thứ người xem thấy.
            #
            # ⚠️ `chu_dich` là chữ của BẢN DỊCH (tiếng Việt) — đúng thứ cần hiện.
            # Truyền vào từ `run()`, KHÔNG đọc lại ở đây: bản đầu tôi dùng thẳng biến
            # `ban` và đo được `NameError: name 'ban' is not defined` — nó không nằm
            # trong tầm với của hàm này.
            #
            # Nếu bản dịch `stale` thì chữ vẫn là chữ đã dịch; nói thẳng điều đó ở log
            # thay vì im lặng, vì người dùng có thể đang xem một bản dịch cũ.
            phu_de = tam / f"dub-{tid}.ass"
            try:
                from app.domain.phu_de import xep_hang_trong_lop
                from app.pipeline import export as _export

                # 🔴 PHỤ ĐỀ BURN PHẢI MỘT CÂU MỘT LÚC — hai việc, cả hai đều cần.
                #
                # 1. LỌC THEO LỚP, y hệt đường XUẤT TỆP (`ExportHandler.run`): timeline giữ
                #    CẢ HAI dòng của một câu (để người đọc soát), nhưng chữ burn vào video
                #    mà có cả hai thì hai câu khác nhau nằm chồng ở cùng mốc. Đo được trên
                #    bản dịch #63: 163 đoạn, **61 cặp chồng**, tổng 64,26 s chồng — ví dụ
                #    `7,02-8,00 "Thường xuyên phải chứng minh"` (lớp 1) nằm dưới
                #    `7,02-9,66 "Thường xuyên phải chứng minh tác phẩm…"` (lớp 2).
                #    Sau `mot_dong_moi_cap`: 110 đoạn, **0 cặp chồng**.
                #
                # 2. XẾP HÀNG trong từng lớp (`xep_hang_trong_lop`): đoạn sau ĐỢI đoạn trước
                #    hiện xong. Với dữ liệu hiện tại bước này không đổi gì (0 cặp chồng sau
                #    khi lọc), nhưng nó là BẢO HIỂM cho dữ liệu khác có hai dòng lớp 1 chồng
                #    nhau — lúc đó chữ sẽ đè lên nhau trên video.
                #
                # Chữ đi kèm phải lọc theo CÙNG chỉ số, nếu không câu hiện ra lệch hàng.
                giu = {s.i for s in mot_dong_moi_cap(list(transcript.segments))}
                chi_so = [k for k, s in enumerate(transcript.segments) if s.i in giu]
                doan_burn = [transcript.segments[k] for k in chi_so]
                chu_burn = (
                    [chu_dich[k] for k in chi_so]
                    if chu_dich is not None and len(chu_dich) == len(transcript.segments)
                    else list(chu_dich or [])
                )
                doan_burn = xep_hang_trong_lop(doan_burn)

                # Kích thước khung THẬT của video gốc — `.ass` phải khai đúng hệ này,
                # nếu không libass co giãn và chữ tràn ra ngoài mép. Đo được trên
                # `dub-1.mp4` (1080×1920) với `.ass` hệ 1920×1080: chữ Việt hiện đúng
                # nhưng bị cắt hai đầu. Xem `tach_nen.kich_thuoc`.
                khung = tach_nen.kich_thuoc(video)
                if khung is None:
                    report(0.94, "không đọc được kích thước video — phụ đề dùng hệ "
                                 "1920×1080, có thể lệch trên khung dọc")
                phu_de.write_text(
                    # `khung` khai đúng hệ toạ độ; `offset_doc` (mặc định 6 % chiều cao)
                    # đẩy khối chữ XUỐNG để HỘP ĐEN che lấp lớp phụ đề TRUNG CỨNG của
                    # video gốc ở đáy khung — xem `subtitle_format._ASS_OFFSET_DOC_MAC_DINH`.
                    _export.render("ass", doan_burn,
                                   translations=chu_burn, khung=khung,
                                   style=kieu_chu),
                    encoding="utf-8",
                )
            except Exception as exc:  # noqa: BLE001 — xem lý do ngay dưới
                # KHÔNG nuốt im lặng, nhưng cũng KHÔNG làm hỏng cả job: bản lồng sạch
                # và master vẫn là thành quả có thật. Nói ra và đi tiếp là hành vi đúng
                # — người dùng nhận được video có tiếng, và biết vì sao thiếu chữ.
                phu_de = None
                report(0.94, f"không burn được phụ đề ({type(exc).__name__}: {exc}) — "
                             f"video vẫn có tiếng lồng, thiếu chữ")

            tach_nen.remux(video, tron_path, ra, phu_de=phu_de)
            report(0.96, f"video lồng tiếng: {ra.name} ({ra.stat().st_size // 1024} kB)"
                         + ("" if phu_de is not None else " · KHÔNG có phụ đề"))

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
