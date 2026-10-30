"""Đường dẫn python của TTS — BA nhánh, và nhánh thứ ba là lý do tệp này tồn tại.

VÌ SAO CẦN: `DubHandler.san_sang()` từ chối SỚM khi thiếu python/script, và đó là thiết kế
đúng — nhưng nó chỉ đúng nếu `TTS_PYTHON` trỏ tới một đường CÓ THẬT. Trong image Linux, đường
mặc định cũ (`/app/.venv-tts/bin/python`) không tồn tại vì `backend/.dockerignore` loại
`.venv-tts/` (venv Windows, 751 MB, không dòng nào chạy được trên Linux).

ĐO ĐƯỢC (job `dub` #21 trong container): `failed` ở 5% với
`RuntimeError: TTS không chạy được (/app/.venv-tts/Scripts/python.exe)` — người dùng chỉ biết
sau khi đã chờ.

Nay có ba đường, theo thứ tự thắng:
  1. `PHUDE_TTS_PYTHON` — đặt tường minh (image đặt `/opt/venv-tts/bin/python`).
  2. `.venv-tts` CẠNH mã nguồn — đường phát triển trên máy, chọn theo hệ điều hành.
  3. `/opt/venv-tts/bin/python` — venv dựng TRONG image, chỉ dùng khi (2) không có mặt.

⚠️ Vì sao phải KIỂM TỒN TẠI bằng `os.path.exists` chứ không đặt cứng đường (3): trên máy phát
triển KHÔNG có `/opt/venv-tts`, nên một hằng số vô điều kiện sẽ cướp đường `.venv-tts` của
Windows — và bài `test_dub_handler.py` đo được đường Windows thật đang thắng.

Tệp này chạy logic của `app.main` trong TIẾN TRÌNH CON, vì hằng số `TTS_PYTHON` được tính LÚC
IMPORT: muốn đo nhánh nào thì phải import lại trong một tiến trình mới với môi trường đã đặt.
Sửa `app.main.TTS_PYTHON` tại chỗ là đo một biến đã bị đọc, không đo được nhánh.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]

#: Đoạn mã chạy TRONG tiến trình con: chỉ in ra đường đã chọn, không dựng app.
_DO = (
    "import json, app.main as m; "
    "print(json.dumps({'tts_python': m.TTS_PYTHON}))"
)


#: Chạy tiến trình con với `BACKEND_DIR` do BÀI TEST quyết định, không phải đường thật.
#:
#: ⚠️ VÌ SAO PHẢI CÓ: đường (2) là `.venv-tts` CẠNH mã nguồn, và trên máy phát triển nó TỒN
#: TẠI THẬT. Nên `not os.path.exists(TTS_PYTHON)` luôn sai, nhánh dự phòng của image không bao
#: giờ chạy, và bài test không đo được nhánh đó — đo được: bản đầu của bài này đỏ với đường (2)
#: thay vì đường dự phòng. Đặt `BACKEND_DIR` vào một thư mục TẠM (không có `.venv-tts`) tái tạo
#: ĐÚNG trạng thái của image, nơi `.dockerignore` loại venv Windows.
_DO_VOI_BACKEND_DIR = (
    "import json, pathlib, app.main as m; "
    "print(json.dumps({'tts_python': m.TTS_PYTHON, 'backend': str(m.BACKEND_DIR)}))"
)


def _chay(
    env_them: dict[str, str],
    *,
    xoa: tuple[str, ...] = (),
    backend_dir: pathlib.Path | None = None,
) -> str:
    """Import `app.main` trong tiến trình MỚI và trả về `TTS_PYTHON` nó chọn.

    `env_them` được đặt TRƯỚC khi python khởi động — đó là điều kiện duy nhất để đo đúng,
    vì `main.py` đọc biến môi trường ở cấp MODULE.

    `backend_dir` khác `None` ⇒ chạy với `__file__` của `app/main.py` nằm trong thư mục đó, để
    đường (2) KHÔNG tồn tại. Dùng một bản SAO của `app/` trong `tmp_path` là quá nặng; thay vào
    đó bài test gọi `main` qua một shim đặt `BACKEND_DIR` — xem `_DO_VOI_BACKEND_DIR`.
    """
    env = {k: v for k, v in os.environ.items() if k not in xoa}
    env.update(env_them)
    env["PYTHONUTF8"] = "1"
    ma = _DO if backend_dir is None else _DO_VOI_BACKEND_DIR
    if backend_dir is not None:
        # `BACKEND_DIR` là `Path(__file__).resolve().parent.parent` của `app/main.py`, nên trỏ
        # nó vào một thư mục tạm cần một `app/main.py` THẬT ở đó. Rẻ nhất: một symlink/junction
        # tới thư mục `app` của repo đặt trong `tmp_path`.
        goi = backend_dir / "app"
        if not goi.exists():
            goi.parent.mkdir(parents=True, exist_ok=True)
            # Chép ĐỆ QUY cả cây `app/`: bản liệt kê tay ở lượt trước bỏ sót
            # `app/adapters/governor/` (một GÓI CON) nên tiến trình con chết với
            # `ModuleNotFoundError: No module named 'app.adapters.governor'`.
            shutil.copytree(
                BACKEND_DIR / "app",
                goi,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

    r = subprocess.run(
        [sys.executable, "-B", "-c", ma],
        cwd=str(BACKEND_DIR if backend_dir is None else backend_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert r.returncode == 0, (
        f"import app.main trong tiến trình con FAILED (exit {r.returncode})\n"
        f"STDOUT={r.stdout[-2000:]}\nSTDERR={r.stderr[-3000:]}"
    )
    return json.loads(r.stdout.strip().splitlines()[-1])["tts_python"]


def test_bien_moi_truong_thang_ca_hai_duong_mac_dinh():
    """(1) `PHUDE_TTS_PYTHON` là câu trả lời CAO NHẤT — không nhánh nào được ghi đè nó.

    Vì sao quan trọng: image Docker đặt biến này trỏ `/opt/venv-tts/bin/python`. Nếu một nhánh
    "thông minh" nào đó thấy `.venv-tts` cạnh mã nguồn và thắng, thì trong image (nơi không có
    `.venv-tts`) nó vẫn đúng, nhưng trên một máy vừa phát triển vừa chạy Docker nó SAI — và
    sai theo kiểu im lặng.
    """
    duong = _chay({"PHUDE_TTS_PYTHON": "/opt/venv-tts/bin/python"})
    assert duong == "/opt/venv-tts/bin/python", (
        f"biến môi trường phải thắng; đo được {duong!r}"
    )


def test_khong_dat_bien_thi_duong_canh_ma_nguon_thang_duong_trong_image():
    """(2) Không đặt biến ⇒ đường `.venv-tts` CẠNH mã nguồn, chọn theo HỆ ĐIỀU HÀNH.

    Đây là đường phát triển trên máy, và nó phải thắng đường `/opt/venv-tts` của image — nếu
    không, một máy có cả hai sẽ chạy TTS bằng interpreter khác với cái người dùng vừa cài.

    🔴 BỎ QUA TRONG IMAGE, và đây là lý do ĐO ĐƯỢC:

        $ python -m pytest tests/test_tts_python_duong_dan.py
        assert '.venv-tts' in '/opt/venv-tts/bin/python'
        AssertionError: đường mặc định phải là venv TTS cạnh mã nguồn

    Trong image KHÔNG có `.venv-tts` — đó là venv phát triển trên máy, không bao giờ
    nằm trong ảnh. Nên hàm rơi về `/opt/venv-tts/bin/python`, tức đúng nhánh mà bài
    NGAY DƯỚI kiểm (`test_duong_canh_ma_nguon_KHONG_co_thi_roi_ve_duong_trong_image`).
    Hai bài loại trừ nhau theo môi trường: bài này chỉ có nghĩa khi `.venv-tts` TỒN TẠI.

    Bỏ qua chứ không nới điều kiện: nới `assert` thành "hoặc `.venv-tts` hoặc `/opt`"
    thì bài này không còn chứng minh gì — nó sẽ xanh ở cả hai môi trường và không
    phát hiện được việc đảo thứ tự ưu tiên.
    """
    goc = pathlib.Path(__file__).resolve().parents[1]
    venv_canh_ma = goc / ".venv-tts"
    if not venv_canh_ma.is_dir():
        pytest.skip(f"không có {venv_canh_ma} — bài này chỉ kiểm trên máy phát triển")

    duong = _chay({}, xoa=("PHUDE_TTS_PYTHON",))
    ten = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    assert duong.replace("\\", "/").endswith(ten), (
        f"đường mặc định phải kết thúc bằng {ten!r} (theo hệ điều hành); đo được {duong!r}"
    )
    assert ".venv-tts" in duong, (
        f"đường mặc định phải là venv TTS cạnh mã nguồn; đo được {duong!r}"
    )


def test_duong_canh_ma_nguon_KHONG_co_thi_roi_ve_duong_trong_image(tmp_path):
    """(3) `.venv-tts` KHÔNG có mặt ⇒ rơi về đường dự phòng của IMAGE.

    Đây là nhánh container Linux đi qua, và là nhánh đã hỏng trước đây (`failed` ở 5%).

    ⚠️ ĐO ĐƯỢC, và đây là lý do đường dự phòng đọc được từ `PHUDE_TTS_PYTHON_TRONG_IMAGE`:
    bản đầu của nhánh này dùng hằng số cứng `/opt/venv-tts/bin/python`, mà trên Windows KHÔNG
    có `/opt` ⇒ nhánh không bao giờ chạy ⇒ **mutation SỐNG**: bỏ hẳn ba dòng dự phòng đi mà tệp
    này vẫn `EXIT=0`. Phép ghim khi đó là giả.

    Nay bài này DỰNG một python giả trong `tmp_path`, đặt biến trỏ vào nó, và đặt
    `PHUDE_TTS_PYTHON` **rỗng** để đường (1) không thắng — đúng trạng thái "đường (2) không có
    mặt" mà image Linux gặp. Đo được cả HAI vế: rơi về đúng đường dự phòng, và KHÔNG rơi về khi
    tệp đó không tồn tại.
    """
    # Python giả: một TỆP có thật, vì `os.path.exists` là thứ duy nhất được hỏi.
    gia = tmp_path / "venv-tts-image" / ("python.exe" if os.name == "nt" else "bin/python")
    gia.parent.mkdir(parents=True, exist_ok=True)
    gia.write_text("", encoding="utf-8")

    # (a) đường dự phòng CÓ mặt + đường (2) KHÔNG có ⇒ phải rơi về đường dự phòng.
    duong = _chay(
        {"PHUDE_TTS_PYTHON": "", "PHUDE_TTS_PYTHON_TRONG_IMAGE": str(gia)},
        backend_dir=tmp_path / "image",
    )
    assert pathlib.Path(duong) == gia, (
        f"phải rơi về đường dự phòng của image ({gia}); đo được {duong!r}"
    )

    # (b) VÀ nó chỉ được rơi về khi tệp TỒN TẠI: trỏ vào một đường không có thì phải giữ
    #     đường (2) — nếu không, một image thiếu venv sẽ im lặng trỏ vào hư không thay vì để
    #     `san_sang()` từ chối sớm với câu nêu đúng đường đã thử.
    khong_co = tmp_path / "khong-ton-tai" / "python"
    duong2 = _chay(
        {"PHUDE_TTS_PYTHON": "", "PHUDE_TTS_PYTHON_TRONG_IMAGE": str(khong_co)},
        backend_dir=tmp_path / "image",
    )
    assert pathlib.Path(duong2) != khong_co, (
        f"KHÔNG được trỏ vào đường dự phòng không tồn tại; đo được {duong2!r}"
    )
    assert ".venv-tts" in duong2, (
        f"khi đường dự phòng vắng mặt phải giữ đường (2); đo được {duong2!r}"
    )




# ----------- `tron_nen` mac dinh: ba muc, va muc thu ba la phep DO -----------

#: Doan ma chay TRONG tien trinh con - doc `_tron_nen_mac_dinh()` voi moi truong da dat.
#: Phai la tien trinh MOI vi bai test can moi truong SACH: `os.environ` cua pytest da co san
#: bien cua may, va sua tai cho thi khong do duoc nhanh "khong dat gi".
_DO_TRON_NEN = (
    "import json, app.main as m; "
    "print(json.dumps({'tron_nen': m._tron_nen_mac_dinh()}))"
)


def _chay_tron_nen(env_them: dict[str, str], *, xoa: tuple[str, ...] = ()) -> bool:
    """Import `app.main` trong tien trinh MOI, tra `_tron_nen_mac_dinh()`."""
    env = {k: v for k, v in os.environ.items() if k not in xoa}
    env.update(env_them)
    env["PYTHONUTF8"] = "1"
    r = subprocess.run(
        [sys.executable, "-B", "-c", _DO_TRON_NEN],
        cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, (
        f"import app.main trong tien trinh con FAILED (exit {r.returncode})\n"
        f"STDOUT={r.stdout[-2000:]}\nSTDERR={r.stderr[-3000:]}")
    return bool(json.loads(r.stdout.strip().splitlines()[-1])["tron_nen"])


def test_tron_nen_bien_moi_truong_ep_bat_va_ep_tat():
    """`PHUDE_DUB_TRON_NEN=1` phai BAT ke ca khi may khong co `demucs`.

    Vi sao ghim chieu BAT: muc 3 la phep do `demucs`, va tren may KHONG co demucs phep do tra
    `False`. Neu bien moi truong khong thang duoc phep do thi no la khai bao chet - nguoi dung
    dat `PHUDE_DUB_TRON_NEN=1` trong image co GPU nhung cai demucs theo cach phep do khong thay
    se khong bao gio bat duoc, ma cung khong co cau loi nao.
    """
    for gia_tri in ("1", "true", "yes", "on", "TRUE", " On "):
        assert _chay_tron_nen({"PHUDE_DUB_TRON_NEN": gia_tri}) is True, gia_tri
    for gia_tri in ("0", "false", "no", "off", "FALSE"):
        assert _chay_tron_nen({"PHUDE_DUB_TRON_NEN": gia_tri}) is False, gia_tri


def test_tron_nen_khong_dat_thi_roi_ve_phep_do_demucs():
    """Vang bien thi theo phep do, va tren may KHONG co demucs thi phai la `False`.

    Day la bai ghim su that cua MOI TRUONG: `backend/.venv` khong cai `demucs`, nen mac dinh
    phai TAT. Neu no thanh `True` thi moi job `dub` tren may nay chay toi 90 % roi `failed` -
    dung loai loi im lang ma co nay sinh ra de tranh.
    """
    import importlib.util

    co_demucs = importlib.util.find_spec("demucs.api") is not None
    assert _chay_tron_nen({}, xoa=("PHUDE_DUB_TRON_NEN",)) is co_demucs, (
        f"mac dinh phai bang phep do; may nay co demucs = {co_demucs}")


def test_tron_nen_gia_tri_rac_thi_roi_ve_phep_do():
    """Gia tri go sai KHONG duoc coi la bat - roi ve phep do, khong doan.

    Vi sao khong nem: day la mot tuy chon, va giet ca tien trinh vi mot chuoi go sai con te hon
    la dung mac dinh. Nhung "go sai" tuyet doi khong duoc hieu thanh "bat": bat nham tren image
    CPU la moi job `dub` chet o 90 %.
    """
    import importlib.util

    co_demucs = importlib.util.find_spec("demucs.api") is not None
    for gia_tri in ("rac", "2", "-1", "bat", "truee"):
        assert _chay_tron_nen({"PHUDE_DUB_TRON_NEN": gia_tri}) is co_demucs, gia_tri


# ----------- `_chon_tron_nen`: ham THUAN, test duoc ca hai chieu -----------

def test_chon_tron_nen_ep_tat_thang_phep_do_CO_demucs():
    """`PHUDE_DUB_TRON_NEN=0` phai TAT ke ca khi may CO `demucs`.

    🔴 Vi sao bai nay phai la ham THUAN: ban dau `_tron_nen_mac_dinh()` tu do `demucs` ben
    trong, nen bai test phai chay tren may THAT. Do duoc he qua: dot bien bo nhanh ep TAT
    (`if ep in ("0","false","no","off")` -> `if False:`) van XANH, vi tren may khong co demucs
    thi phep do CUNG tra `False` - hai duong cho CUNG ket qua. Nhanh ep TAT la nhanh duy nhat
    duoc dung de tranh loi im lang tren image CPU, nen no phai phan biet duoc.
    """
def test_chon_tron_nen_ep_tat_thang_phep_do_CO_demucs():
    """`PHUDE_DUB_TRON_NEN=0` phai TAT ke ca khi may CO `demucs`.

    🔴 Vi sao bai nay phai la ham THUAN: ban dau `_tron_nen_mac_dinh()` tu do
    `demucs` ben trong, nen bai test phai chay tren may THAT. Do duoc he qua: dot bien
    bo nhanh ep TAT (`if ep in ("0","false","no","off")` -> `if False:`) van XANH, vi
    tren may khong co demucs thi phep do CUNG tra `False` - hai duong cho CUNG ket qua.
    Nhanh ep TAT la nhanh duy nhat duoc dung de tranh loi im lang tren image CPU, nen
    no phai phan biet duoc.

    ⚠️ HOP DONG: `ep` la gia tri DA chuan hoa (lower + strip) - `_tron_nen_mac_dinh`
    lam viec do truoc khi goi. Bai test truyen chuoi thuong, dung hop dong. Ban dau
    bai nay truyen `"FALSE"`/`" off "` tho va DO - dung ly do: ham thuan khong chuan
    hoa lai, va khong duoc chuan hoa lai (hai noi cung chuan hoa la mot cho de lech).
    """
    from app.main import _chon_tron_nen

    for ep in ("0", "false", "no", "off"):
        assert _chon_tron_nen(ep, True) is False, (ep, "co demucs van phai TAT")
        assert _chon_tron_nen(ep, False) is False, (ep, "khong co demucs thi cang phai TAT")


def test_chon_tron_nen_ep_bat_thang_phep_do_KHONG_co_demucs():
    """`PHUDE_DUB_TRON_NEN=1` phai BAT ke ca khi phep do bao khong.

    Ghi chu: bat tren image KHONG co demucs thi job se `failed` o 90 % - do la lua chon
    cua nguoi dat bien, va no phai duoc THI HANH, khong bi phep do am tham ghi de. Im
    lang bo qua mot bien moi truong dat tuong minh con te hon la de job chet roi bao
    dung ly do.
    """
    from app.main import _chon_tron_nen

    for ep in ("1", "true", "yes", "on"):
        assert _chon_tron_nen(ep, False) is True, (ep, "phai BAT du phep do bao khong")
        assert _chon_tron_nen(ep, True) is True, ep
