"""Job `dub`: handler + hai route (xếp job, tải file).

TTS được TIÊM vào handler (`tts_runner`), nên bài này chạy mà không cần cài VieNeu — đúng lý do
tham số đó tồn tại (venv TTS riêng, xem `scripts/tts_batch.py`).
"""
from __future__ import annotations

import pathlib
import types

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app
from app.domain import job_state as js
from app.domain.models import Job, Segment
from app.pipeline.dub import DubHandler


@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    sid = r.add_source(kind="file", origin="a", media_path="m", lang="zh")
    tid = r.add_transcript(source_id=sid, engine="fw", lang="zh",
                           segments=[Segment(i=0, start=0.0, end=2.0, text="你好")])
    ban = r.add_translation(transcript_id=tid, transcript_version=1, engine="deepseek-web",
                            target_lang="vi", prompt_version="p1",
                            segments=[Segment(i=0, start=0.0, end=2.0, text="Xin chào"),
                                      Segment(i=1, start=3.0, end=5.0, text="Tạm biệt")])
    return r, ban


def _tts_gia_1_giay(items, voice, out_dir):
    """Ghi một wav 1,0 s cho MỖI dòng vào `out_dir` — take ngắn hơn chỗ, nên tốc độ là 1,00.

    ⚠️ `out_dir` là THAM SỐ, không phải thư mục tự dựng: handler sở hữu thư mục tạm, nên đường
    dẫn trả về còn sống khi nó đọc. Bản đầu của fixture này tự dựng thư mục riêng — và chính vì
    thế nó KHÔNG bắt được lỗi thật, xem `test_handler_doc_duoc_take_vi_thu_muc_con_song`.
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ra = {}
    for it in items:
        p = out_dir / f"{it['i']:05d}.wav"
        sf.write(str(p), np.full(48_000, 0.5, dtype=np.float32), 48_000)
        ra[it["i"]] = {"i": it["i"], "seconds": 1.0, "path": str(p)}
    return ra


def test_handler_dat_take_dung_offset_va_xuat_du_nam_dinh_dang(repos, tmp_path):
    r, tid = repos
    out = tmp_path / "dubs"
    h = DubHandler(r, out, _tts_gia_1_giay)
    job_id = r.add_job(Job(id=None, workspace=2, type="dub", engine="vieneu-v3-turbo",
                           phase="dub:vieneu-v3-turbo", payload={"translation_id": tid}))
    job = r.get_job(job_id)

    dong: list[tuple[float, str]] = []
    h.run(job, lambda p, line: dong.append((p, line)))

    for dd in ("wav", "flac", "mp3", "aac", "m4a"):
        tep = out / f"dub-{tid}.{dd}"
        assert tep.is_file() and tep.stat().st_size > 0, f"thiếu {dd}"
    du_lieu, sr = sf.read(str(out / f"dub-{tid}.wav"))
    assert sr == 48_000
    assert abs(len(du_lieu) / sr - 5.0) < 0.05, "canvas phải dài bằng end của dòng cuối (5,0 s)"
    # take 1,0 s đặt ở 0,0 và 3,0 -> mẫu ở 0,0 và 3,0 phải có tiếng, giữa hai take thì im
    assert abs(du_lieu[0]) > 0.0
    assert abs(du_lieu[int(1.5 * sr)]) < 1e-6, "khoảng giữa (1,5 s) phải im"
    assert dong and dong[-1][0] == 1.0, "progress phải kết ở 1.0"


def test_handler_doc_duoc_take_vi_thu_muc_con_song(repos, tmp_path):
    """HỢP ĐỒNG: đường dẫn runner trả về phải còn sống khi `run()` đọc nó.

    Đây là bài ghim của một LỖI ĐÃ ĐO ĐƯỢC trên máy thật, không phải một giả thuyết. Bản đầu
    để `chay_tts_batch` tự dựng `TemporaryDirectory`, ghi wav vào đó, trả ĐƯỜNG DẪN về, rồi
    thư mục bị xoá ngay khi hàm trả về. `run()` đọc những đường dẫn ấy sau đó ⇒ mọi job `dub`
    chết ở 40%:

        LibsndfileError: Error opening
        'C:\\\\Users\\\\Admin\\\\AppData\\\\Local\\\\Temp\\\\tts-5cs2do_f\\\\wav\\\\00000.wav': System error

    Đo cô lập đúng khuôn đó: `trong with: ton tai = True` / `sau with: ton tai = False`.

    ⚠️ VÌ SAO bộ test cũ KHÔNG bắt được: runner giả tự dựng một thư mục bên ngoài
    (`_tts_gia_1_giay.thu_muc`) nên đường dẫn của nó luôn sống — fixture vô tình thoả hợp đồng
    mà sản phẩm vi phạm. Bài này ghim hợp đồng bằng cách ĐỌC tệp trong lúc `run()` còn chạy, và
    đòi thư mục do runner ghi nằm DƯỚI thư mục tạm do handler cấp (đúng kiến trúc mới).
    """
    r, tid = repos
    da_thay: list[tuple[str, bool, bool]] = []

    def runner_ghi_roi_kiem(items, voice, out_dir):
        """Ghi wav vào `out_dir` handler cấp, RỒI khẳng định tệp sống ngay tại đó."""
        out = pathlib.Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        ra = {}
        for it in items:
            p = out / f"{it['i']:05d}.wav"
            sf.write(str(p), np.full(48_000, 0.5, dtype=np.float32), 48_000)
            da_thay.append((str(p), p.is_file(), "tts-" in out.name or "dub-" in out.name))
            ra[it["i"]] = {"i": it["i"], "seconds": 1.0, "path": str(p)}
        return ra

    out = tmp_path / "dubs"
    h = DubHandler(r, out, runner_ghi_roi_kiem)
    job_id = r.add_job(Job(id=None, workspace=2, type="dub", engine="vieneu-v3-turbo",
                           phase="dub:vieneu-v3-turbo", payload={"translation_id": tid}))
    h.run(r.get_job(job_id), lambda p, line: None)

    assert len(da_thay) == 2, f"runner phải nhận đủ hai dòng, đo được {len(da_thay)}"
    for duong, con_song, trong_thu_muc_tam in da_thay:
        assert con_song, f"tệp take phải tồn tại khi runner trả về: {duong}"
        assert trong_thu_muc_tam, (
            f"runner phải ghi vào thư mục TẠM do handler cấp (một thư mục `tts-`/`dub-`), "
            f"đo được {duong}"
        )
    assert (out / f"dub-{tid}.wav").is_file(), "bản master vẫn phải ra đúng chỗ"


def test_handler_tu_choi_ban_dich_rong(repos, tmp_path):
    r, tid = repos
    r.update_translation_segments(tid, [])
    h = DubHandler(r, tmp_path / "dubs", _tts_gia_1_giay)
    job_id = r.add_job(Job(id=None, workspace=2, type="dub", engine="x", phase="dub:x",
                           payload={"translation_id": tid}))
    with pytest.raises(RuntimeError, match="không có dòng"):
        h.run(r.get_job(job_id), lambda p, line: None)


def test_route_xep_job_va_tu_choi_ban_dich_khong_ton_tai(repos, tmp_path):
    r, tid = repos
    app = create_app(repos=r, specs=[], media_dir=tmp_path / "m", out_dir=tmp_path / "o")
    from app.api.deps import get_worker
    app.dependency_overrides[get_worker] = lambda: object()
    with TestClient(app) as c:
        r_ok = c.post("/api/dubs", json={"translation_id": tid})
        assert r_ok.status_code == 201, r_ok.text
        assert r_ok.json()["job"]["type"] == "dub"
        assert r_ok.json()["job"]["id"] >= 1
        that = c.post("/api/dubs", json={"translation_id": 999})
        assert that.status_code == 404
        assert "999" in that.json()["detail"], "câu lỗi phải nêu đúng id"


def test_route_tai_tra_404_kem_huong_dan_khi_chua_long_tieng(repos, tmp_path):
    r, tid = repos
    app = create_app(repos=r, specs=[], media_dir=tmp_path / "m", out_dir=tmp_path / "o")
    with TestClient(app) as c:
        thieu = c.get(f"/api/dubs/{tid}/download?format=mp3")
        assert thieu.status_code == 404
        assert "chưa có bản lồng tiếng" in thieu.json()["detail"]
        sai = c.get(f"/api/dubs/{tid}/download?format=ogg")
        assert sai.status_code == 404 and "ogg" in sai.json()["detail"]


def test_san_sang_noi_dung_thu_dang_thieu_khi_may_chua_co_tts(repos, tmp_path):
    """`san_sang()` là câu trả lời của HANDLER về môi trường, và nó phải nêu ĐÚNG thứ thiếu.

    Đo được (image Linux `docker compose up`): đường mặc định là `…/Scripts/python.exe` — một
    đường Windows — nên job `dub` được nhận, chạy tới 5% rồi `failed`, và người dùng chỉ biết
    sau khi đã chờ. Bài này ghim hai vế của phép dò: thiếu python ⇒ `False` + câu nêu đường dẫn
    đã thử; đủ cả python lẫn script ⇒ `True`.

    ⚠️ Vế "không khai đường dẫn ⇒ `True`" cũng được ghim: một handler tự dựng với runner GIẢ
    không có ý kiến gì về môi trường, nên đoán hộ nó là bịa — và nếu đoán sai thì mọi bài route
    ở trên sẽ đỏ vì một lý do không liên quan tới chúng.
    """
    r, _tid = repos
    khong_khai = DubHandler(r, tmp_path / "o", _tts_gia_1_giay)
    assert khong_khai.san_sang() == (True, ""), (
        "handler không khai đường dẫn thì KHÔNG được phán về môi trường"
    )

    thieu = DubHandler(r, tmp_path / "o", _tts_gia_1_giay,
                       python=str(tmp_path / "khong-co" / "python.exe"),
                       script=str(tmp_path / "khong-co" / "tts_batch.py"))
    duoc, vi_sao = thieu.san_sang()
    assert duoc is False
    assert "khong-co" in vi_sao, f"câu lỗi phải nêu ĐÚNG đường đã thử, đo được {vi_sao!r}"
    assert "vieneu" in vi_sao and "PHUDE_TTS_PYTHON" in vi_sao, (
        f"câu lỗi phải nêu việc phải làm (cài vieneu / đặt biến), đo được {vi_sao!r}"
    )

    py = tmp_path / "py"
    py.write_text("")
    sc = tmp_path / "tts_batch.py"
    sc.write_text("")
    du = DubHandler(r, tmp_path / "o", _tts_gia_1_giay, python=str(py), script=str(sc))
    assert du.san_sang() == (True, "")


def test_route_tu_choi_409_TRUOC_KHI_ghi_job_khi_may_chua_co_tts(repos, tmp_path):
    """Route phải từ chối SỚM, và KHÔNG được để lại một hàng `jobs` chết trong hàng đợi.

    Đây là khác biệt giữa "báo lỗi" và "báo lỗi ĐÚNG CHỖ": một job `failed` trong hàng đợi là
    một hàng người dùng phải dọn, còn một `409` là một câu trả lời không để lại rác.
    """
    r, tid = repos
    app = create_app(repos=r, specs=[], media_dir=tmp_path / "m", out_dir=tmp_path / "o")
    from app.api.deps import get_worker
    handler = DubHandler(r, tmp_path / "o", _tts_gia_1_giay,
                         python=str(tmp_path / "khong-co" / "python.exe"),
                         script=str(tmp_path / "khong-co" / "tts_batch.py"))
    app.dependency_overrides[get_worker] = lambda: types.SimpleNamespace(handlers={"dub": handler})
    truoc = len(r.list_jobs())
    with TestClient(app) as c:
        resp = c.post("/api/dubs", json={"translation_id": tid})
        assert resp.status_code == 409, resp.text
        assert "chưa có TTS" in resp.json()["detail"]
    assert len(r.list_jobs()) == truoc, "409 phải KHÔNG để lại hàng `jobs` nào"

def test_plan_ghi_du_sau_so_cua_tung_dong(repos, tmp_path):
    """`dub-<tid>.plan.json` là thứ DUY NHẤT mang `take`/`chỗ`/tốc độ về cho giao diện.

    Bốn số đó chỉ tồn tại trong lượt chạy. Không ghi ra thì bảng dòng ở màn Lồng tiếng chỉ có
    hai lựa chọn: bịa, hoặc bắt người dùng chạy lại TTS (5–7 phút) để xem một lượt đã xong.
    """
    import json

    r, tid = repos
    out = tmp_path / "dubs"
    h = DubHandler(r, out, _tts_gia_1_giay)
    job_id = r.add_job(Job(id=None, workspace=2, type="dub", engine="vieneu-v3-turbo",
                           phase="dub:vieneu-v3-turbo", payload={"translation_id": tid}))
    h.run(r.get_job(job_id), lambda p, line: None)

    tep = out / f"dub-{tid}.plan.json"
    assert tep.is_file(), "lượt chạy phải để lại kế hoạch cạnh master"
    kh = json.loads(tep.read_text(encoding="utf-8"))
    assert kh["translation_id"] == tid
    assert kh["so_dong"] == 2, f"bản dịch fixture có hai dòng, đo được {kh['so_dong']}"
    assert kh["tong_giay"] == 5.0
    assert "tran" not in kh, "khoá `tran` phải BIẾN MẤT cùng trần 1,35"
    # take 1,0 s: dòng #0 (chỗ 2,0 s) vừa, dòng #1 (chỗ 2,0 s) vừa ⇒ 0 nén, 0 nén mạnh.
    assert kh["dem"] == {"vua": 2, "nen": 0, "nen_manh": 0}, kh["dem"]
    mot = kh["dong"][0]
    assert set(mot) == {"i", "start", "end", "text", "take", "slot", "avail", "speed", "need",
                        "trang_thai"}, f"hàng phải có đúng chín khoá, đo được {sorted(mot)}"
    assert mot["text"] == "Xin chào", "câu của dòng phải là của BẢN DỊCH, không phải bản gốc"
    assert mot["take"] == 1.0 and mot["slot"] == 2.0 and mot["speed"] == 1.0


def test_plan_la_null_khi_chua_long_lan_nao(repos, tmp_path):
    """Chưa lồng ⇒ `null`, KHÔNG phải 404 và KHÔNG phải một kế hoạch rỗng bịa ra.

    "Chưa có số đo" và "không có bản dịch" là hai câu khác nhau; giao diện phải phân biệt được.
    """
    r, tid = repos
    app = create_app(repos=r, specs=[], media_dir=tmp_path / "m", out_dir=tmp_path / "o")
    with TestClient(app) as c:
        resp = c.get(f"/api/dubs/{tid}/plan")
        assert resp.status_code == 200, resp.text
        assert resp.json() is None, f"chưa lồng thì phải là null, đo được {resp.json()!r}"


def test_take_cat_dung_doan_cua_dong(repos, tmp_path):
    """Nghe thử một dòng: trả wav dài ĐÚNG `take / tốc độ`, không phải `end - start`.

    ⚠️ Vì sao không dùng `end - start`: khi take NGẮN hơn chỗ (chuyện thường), `end - start` dài
    hơn tiếng thật và người dùng nghe thấy một khoảng lặng không có trong bản lồng.
    """
    r, tid = repos
    out = tmp_path / "dubs"
    h = DubHandler(r, out, _tts_gia_1_giay)
    job_id = r.add_job(Job(id=None, workspace=2, type="dub", engine="vieneu-v3-turbo",
                           phase="dub:vieneu-v3-turbo", payload={"translation_id": tid}))
    h.run(r.get_job(job_id), lambda p, line: None)

    app = create_app(repos=r, specs=[], media_dir=tmp_path / "m", out_dir=out.parent)
    with TestClient(app) as c:
        resp = c.get(f"/api/dubs/{tid}/take", params={"i": 0})
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("audio/wav")
        # ⚠️ HEADER NÀY LÀ ĐIỀU KIỆN ĐỂ NGHE ĐƯỢC, không phải chi tiết phụ. ĐO ĐƯỢC trên app
        # thật: `FileResponse(..., filename=...)` khiến Starlette trả
        # `Content-Disposition: attachment`, và Chrome coi URL là một lượt TẢI XUỐNG nên thẻ
        # `<audio>` treo ở `readyState: 0` / `networkState: 2` mà KHÔNG gửi request nào
        # (Resource Timing rỗng) và `play()` trả Promise không bao giờ resolve. `fetch` cùng URL
        # vẫn trả đủ 245804 byte, nên chỉ header này phân biệt được hai hành vi.
        assert resp.headers["content-disposition"].startswith("inline"), (
            "route NGHE phải là `inline`; `attachment` khiến trình duyệt tải tệp thay vì phát, "
            f"đo được {resp.headers['content-disposition']!r}")
        tam = tmp_path / "take.wav"
        tam.write_bytes(resp.content)
        mau, sr = sf.read(str(tam))
        assert sr == 48_000
        # take 1,0 s ở tốc độ 1,00 ⇒ 1,0 s. Chỗ của dòng là 2,0 s — con số SAI sẽ là 2,0.
        assert abs(len(mau) / sr - 1.0) < 0.02, f"take phải dài 1,0 s, đo được {len(mau) / sr:.3f}"

        khong = c.get(f"/api/dubs/{tid}/take", params={"i": 99})
        assert khong.status_code == 404
        assert "không có dòng 99" in khong.json()["detail"]

def test_cau_loi_TTS_bo_rac_WSL_va_giu_cau_chan_doan():
    """`_dong_loi_dau_tien`: câu lỗi trên panel phải là CHẨN ĐOÁN, không phải rác của WSL.

    ⚠️ ĐO ĐƯỢC (job `dub` #21 trong container): `error` dài **472 ký tự**; 400 ký tự sau là
    `UtilGetPpid:1359: Failed to parse: /proc/1/stat, content: 1 (python) S 0 1 1 0 -1 4194560 …`
    — cảnh báo của WSL, không phải lỗi TTS. Bản trước lấy `stderr[-800:]` (ĐUÔI), nên giữ đúng
    khối rác và có thể cắt mất câu chẩn đoán ở ĐẦU. Trên panel phải khối rác đó chiếm 8 dòng,
    đẩy job vừa thành công ra khỏi tầm mắt người đọc.

    Bốn vế, và vế (1) là vế đã hỏng thật:
      (1) rác đứng TRƯỚC ⇒ vẫn phải trả câu chẩn đoán đứng SAU;
      (2) `stderr` rỗng ⇒ dùng `stdout` (một số chương trình in lỗi ra đó);
      (3) cả hai rỗng ⇒ nói RA là rỗng, không trả chuỗi trắng;
      (4) dòng dài ⇒ cắt, vì một dòng 5 000 ký tự cũng không đọc được trên panel.
    """
    from app.pipeline.dub import _dong_loi_dau_tien

    # (1) ĐÚNG hình dạng đo được của job #21: rác WSL trước, chẩn đoán sau.
    rac = (
        "WSL (36 - ) ERROR: UtilGetPpid:1359: Failed to parse: /proc/1/stat, "
        "content: 1 (python) S 0 1 1 0 -1 4194560 17042 6671 23 16 73 89 0 2\n"
        "RuntimeError: TTS không chạy được (/app/.venv-tts/Scripts/python.exe): "
        "ModuleNotFoundError: No module named 'vieneu'\n"
    )
    duoc = _dong_loi_dau_tien(rac, None)
    assert duoc.startswith("RuntimeError: TTS không chạy được"), (
        f"phải trả câu CHẨN ĐOÁN, không phải rác WSL; đo được {duoc!r}"
    )
    assert "UtilGetPpid" not in duoc, f"rác WSL không được lọt vào câu lỗi; đo được {duoc!r}"
    assert "/proc/1/stat" not in duoc, f"rác `/proc/1/stat` không được lọt vào; đo được {duoc!r}"

    # (2) `stderr` rỗng ⇒ `stdout`.
    assert _dong_loi_dau_tien("", "loi tren stdout\n") == "loi tren stdout"

    # (3) Cả hai rỗng ⇒ NÓI RA, không trả chuỗi trắng.
    assert _dong_loi_dau_tien(None, None) == "(không có đầu ra)"
    assert _dong_loi_dau_tien("\n\n  \n", "") == "(không có đầu ra)", (
        "toàn dòng trắng cũng là 'không có đầu ra', không phải một câu lỗi rỗng"
    )

    # (4) Cắt độ dài.
    dai = "x" * 5000
    assert len(_dong_loi_dau_tien(dai, None)) == 300, (
        "dòng lỗi phải bị cắt ở 300 ký tự; đo được "
        f"{len(_dong_loi_dau_tien(dai, None))}"
    )


def test_chay_tts_batch_dung_cau_chan_doan_khi_khong_co_ket_qua(tmp_path):
    """`chay_tts_batch` khi tiến trình TTS chết: câu `RuntimeError` là DÒNG CHẨN ĐOÁN.

    Bài này chạy ĐÚNG hàm thật với một `tts_python` giả là **script Python** in rác WSL ra
    stderr rồi thoát — nên phép đo đi qua `subprocess` thật, không phải một mock. Đó là điều
    kiện để tin rằng panel sẽ không còn dãy số rác.
    """
    import sys as _sys

    from app.pipeline.dub import chay_tts_batch

    gia = tmp_path / "tts_gia.py"
    gia.write_text(
        "import sys\n"
        "print('WSL (36 - ) ERROR: UtilGetPpid:1359: Failed to parse: /proc/1/stat', file=sys.stderr)\n"
        "print(\"RuntimeError: TTS không chạy được: No module named 'vieneu'\", file=sys.stderr)\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    chay = chay_tts_batch(_sys.executable, gia)
    try:
        chay([{"i": 0, "text": "xin chào"}], None, tmp_path / "ra")
    except RuntimeError as exc:
        cau = str(exc)
    else:  # pragma: no cover - chỉ chạy nếu tiến trình giả lại "thành công"
        raise AssertionError("tiến trình TTS chết mà không có RuntimeError")

    assert "TTS không chạy được" in cau, f"câu lỗi phải nêu việc TTS không chạy; đo được {cau!r}"
    assert "No module named 'vieneu'" in cau, (
        f"câu lỗi phải giữ CHẨN ĐOÁN của tiến trình con; đo được {cau!r}"
    )
    assert "UtilGetPpid" not in cau, f"rác WSL không được lọt vào; đo được {cau!r}"
    assert "/proc/1/stat" not in cau, f"rác `/proc/1/stat` không được lọt vào; đo được {cau!r}"


def test_route_chuyen_tron_nen_vao_payload_va_mac_dinh_la_null(repos, tmp_path):
    """`tron_nen` phải đi từ request vào payload của job, và VẮNG thì là `None`.

    🔴 Vì sao ghim cả hai chiều: `None` nghĩa là "theo mặc định của MÔI TRƯỜNG" (image có GPU
    thì bật), khác hẳn `false` nghĩa là "chỉ bản lồng sạch". Nếu route lặng lẽ đổi vắng thành
    `False` thì một image có GPU sẽ KHÔNG BAO GIỜ trộn nền dù người dùng không yêu cầu tắt —
    và không ai thấy gì bất thường, chỉ là video ra mất nhạc.
    """
    r, tid = repos
    app = create_app(repos=r, specs=[], media_dir=tmp_path / "m", out_dir=tmp_path / "o")
    from app.api.deps import get_worker
    app.dependency_overrides[get_worker] = lambda: object()
    with TestClient(app) as c:
        for gui, mong in (
            ({}, None),
            ({"tron_nen": True}, True),
            ({"tron_nen": False}, False),
        ):
            body = {"translation_id": tid, **gui}
            resp = c.post("/api/dubs", json=body)
            assert resp.status_code == 201, resp.text
            job = r.get_job(resp.json()["job"]["id"])
            assert job.payload.get("tron_nen") == mong, (gui, job.payload)
