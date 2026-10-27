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
    """
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


