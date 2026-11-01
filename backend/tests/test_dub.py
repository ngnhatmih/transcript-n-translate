"""Hai hàm của đường lồng tiếng — phần THUẦN, không TTS, không ffmpeg.

🔴 HÀNH VI ĐÃ ĐỔI (spec 2026-10-29, người dùng chốt):
  · RÀNG BUỘC CỨNG: giọng câu trước KHÔNG được còn nói khi câu sau bắt đầu.
  · Tốc độ đều là MONG MUỐN, không bắt buộc.
  · KHÔNG cắt chữ để đổi lấy tốc độ — chỉ chỉnh tốc độ.

Ba bài đầu vì thế khẳng định điều KHÁC bản cũ: bản cũ kẹp `need` ở trần 1,35 và trả
`qua_tran` (dòng vượt trần VẪN chồng, chỉ được đánh dấu). Bản mới nén tới ĐÚNG mức cần.
"""
from __future__ import annotations

import numpy as np

from app.domain.models import Segment
from app.pipeline.dub import (
    LOP_HAI_NGUON,
    LOP_MOT_NGUON,
    ke_hoach_toc_do,
    mot_dong_moi_cap,
    rap,
    trong_im_lang,
)


def test_nen_toi_dung_muc_can_khong_kep_o_tran():
    """Dòng cần 1,40× thì phải được 1,40×, KHÔNG phải kẹp 1,35 rồi chồng sang dòng sau.

    Số lấy từ lượt đo trên 14 dòng thật của clip 20:49: `take/chỗ` rải tới 1,62×.
    Bài này là ghim của RÀNG BUỘC CỨNG, nên nó phải ĐỎ nếu ai đó đặt lại trần.
    """
    takes, slots, avails = [1.02, 1.18, 1.40], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]
    toc_do, need = ke_hoach_toc_do(takes, slots, avails)
    assert [round(n, 2) for n in need] == [1.02, 1.18, 1.4]
    assert toc_do == [1.02, 1.18, 1.40], toc_do


def test_khong_bao_gio_doc_cham_di():
    """Take ngắn hơn chỗ ⇒ tốc độ 1,00, KHÔNG kéo chậm để lấp chỗ trống."""
    toc_do, need = ke_hoach_toc_do([0.4, 0.9], [1.0, 1.0], [1.0, 1.0])
    assert toc_do == [1.0, 1.0], toc_do
    assert need == [0.4, 0.9]


def test_muon_duoc_khoang_lang_thi_can_it_toc_do_hon():
    """Cùng take 1,5 s: chỗ 1,0 s nhưng dòng sau bắt đầu ở 1,5 s ⇒ chỉ cần 1,0×."""
    khong_muon, _ = ke_hoach_toc_do([1.5], [1.0], [1.0])
    co_muon, _ = ke_hoach_toc_do([1.5], [1.0], [1.5])
    assert khong_muon == [1.5]      # 1.5/1.0 = 1.5 — nén đúng mức, KHÔNG kẹp ở trần
    assert co_muon == [1.0]         # mượn 0,5 s lặng là đủ


def test_khong_cap_lien_ke_nao_chong_lan():
    """RÀNG BUỘC CỨNG, kiểm trên một bộ dòng dày đặc.

    Đây là bài quan trọng nhất của tệp. Nó kiểm ĐÚNG điều người dùng gọi là "không hợp lệ":
    giọng câu trước còn đang nói khi câu sau đã bắt đầu.
    """
    takes = [1.5, 2.0, 0.8, 3.0, 1.2]
    starts = [0.0, 1.0, 1.5, 2.0, 6.0]
    slots = [0.5, 0.5, 0.5, 4.0, 1.0]
    avails = [starts[k + 1] - starts[k] for k in range(len(starts) - 1)] + [1.0]
    toc_do, _ = ke_hoach_toc_do(takes, slots, avails)
    for k in range(len(starts) - 1):
        ket_thuc = starts[k] + takes[k] / toc_do[k]
        assert ket_thuc <= starts[k + 1] + 1e-9, (
            f"dòng {k} kết thúc ở {ket_thuc:.4f}s, vượt mốc bắt đầu dòng {k + 1} "
            f"({starts[k + 1]}s) — CHỒNG LẤN, không hợp lệ"
        )


def test_khong_co_hang_nao_bi_cat_chu():
    """Chỉ tốc độ được đổi; KHÔNG dòng nào bị cắt chữ, dù phải nén tới 9×.

    Ghim lời người dùng: "ko cần phải cắt mà chỉnh tốc độ là được".

    🔴 VÌ SAO BÀI NÀY ĐI QUA `DubHandler` CHỨ KHÔNG CHỈ GỌI `ke_hoach_toc_do`:
    bản đầu của bài này chỉ khẳng định `ke_hoach_toc_do` trả đúng 2 phần tử — gần như
    rỗng, vì hàm đó KHÔNG nhận và KHÔNG trả `text`, nên một bản vá cắt chữ trong `run()`
    vẫn làm nó XANH. Đo được (review Task 1): một implementation cắt sạch mọi phụ đề
    trong `run()` vẫn qua bài cũ. Nay bài này chặn ĐÚNG chỗ chữ đi vào TTS.
    """
    import pathlib
    import tempfile

    import soundfile as sf

    from app.adapters.clock_system import SystemClock
    from app.adapters.persist.sqlite_repos import SqliteRepos
    from app.domain.models import Job, Segment
    from app.pipeline.dub import DubHandler

    # Take DÀI GẤP 9 LẦN chỗ: need = 9.0, nên đây đúng là dòng mà bản cũ sẽ kẹp ở trần.
    CHU = "câu này rất dài và không được phép bị cắt bớt chữ nào cả"

    with tempfile.TemporaryDirectory() as tam:
        tam_p = pathlib.Path(tam)
        r = SqliteRepos(tam_p / "t.db", clock=SystemClock())
        r.init_schema()
        sid = r.add_source(kind="file", origin="a", media_path="m", lang="zh")
        tid = r.add_transcript(source_id=sid, engine="fw", lang="zh",
                               segments=[Segment(i=0, start=0.0, end=1.0, text="你好")])
        tid_ban = r.add_translation(
            transcript_id=tid, transcript_version=1, engine="deepseek-web",
            target_lang="vi", prompt_version="p1",
            segments=[Segment(i=0, start=0.0, end=1.0, text=CHU)])

        da_nhan: list[str] = []

        def tts_gia(items, voice, out_dir):
            out_dir = pathlib.Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            ra = {}
            for it in items:
                da_nhan.append(it["text"])
                p = out_dir / f"{it['i']:05d}.wav"
                # 9,0 s cho một chỗ 1,0 s ⇒ buộc phải nén 9×, không được cắt chữ.
                sf.write(str(p), np.full(9 * 48_000, 0.5, dtype=np.float32), 48_000)
                ra[it["i"]] = {"i": it["i"], "seconds": 9.0, "path": str(p)}
            return ra

        out = tam_p / "dubs"
        h = DubHandler(r, out, tts_gia)
        job = r.get_job(r.add_job(Job(
            id=None, workspace=2, type="dub", engine="vieneu-v3-turbo",
            phase="dub:vieneu-v3-turbo", payload={"translation_id": tid_ban})))
        h.run(job, lambda p, line: None)

        assert da_nhan == [CHU], (
            f"chữ gửi TTS phải NGUYÊN VẸN; đo được {da_nhan!r}"
        )

        import json as _json
        kh = _json.loads((out / f"dub-{tid_ban}.plan.json").read_text(encoding="utf-8"))
        assert kh["dong"][0]["text"] == CHU, (
            f"kế hoạch ghi cũng phải giữ nguyên chữ; đo được {kh['dong'][0]['text']!r}"
        )
        assert kh["dong"][0]["speed"] == 9.0, (
            f"phải nén ĐÚNG 9× (take 9,0 / chỗ 1,0), đo được {kh['dong'][0]['speed']}"
        )


def test_trong_im_lang_bo_dau_cuoi_giu_giua():
    sr = 100
    im = np.zeros(10, dtype=np.float32)
    tieng = np.full(5, 0.5, dtype=np.float32)
    mau = np.concatenate([im, tieng, np.zeros(3, dtype=np.float32), tieng, im])
    ra = trong_im_lang(mau, nguong=0.01)
    assert ra.size == 5 + 3 + 5, ra.size
    assert ra[0] == 0.5 and ra[-1] == 0.5


def test_rap_dat_dung_offset_va_cong_don_khi_chong():
    sr = 1000
    take = np.full(100, 0.25, dtype=np.float32)      # 0,1 s
    ra = rap([(0.0, take), (0.5, take)], 1.0, sr=sr)
    assert ra.shape == (1000,)
    assert ra[0] == 0.25 and ra[99] == 0.25
    assert ra[100:500].max() == 0.0, "khoảng giữa hai take phải im"
    assert ra[500] == 0.25
    # chồng tiếng thì CỘNG, không đè mất
    chong = rap([(0.0, take), (0.05, take)], 1.0, sr=sr)
    assert chong[75] == 0.5

def _d(i, start, end, text, layer="", suspect=False, chua_trong=-1):
    return Segment(i=i, start=start, end=end, text=text, layer=layer,
                   suspect=suspect, chua_trong=chua_trong)


def test_ban_long_chi_doc_MOT_lan_moi_cau_khi_OCR_va_ASR_cung_cau():
    """Ca that tren #36: ASR nghe sai "海豹", OCR doc dung "海报".

    Timeline giu CA HAI de nguoi doc thay may nghe sai. Ban long ma doc ca hai thi cung
    mot cau duoc noi hai lan chong len nhau — vi pham rang buoc "dong N khong duoc con
    noi khi N+1 bat dau".
    """
    d = [
        _d(96, 195.50, 196.53, "ASR nghe sai", LOP_HAI_NGUON, True),
        _d(97, 195.50, 196.17, "OCR doc dung", LOP_HAI_NGUON, False),
    ]
    ra = mot_dong_moi_cap(d)
    assert len(ra) == 1, [s.text for s in ra]
    assert ra[0].text == "OCR doc dung", "phai giu ban OCR: " + repr(ra[0].text)


def test_ban_long_giu_ban_OCR_khi_hai_dong_trung_khit():
    d = [
        _d(98, 197.00, 198.11, "cung mot cau", LOP_HAI_NGUON, True),
        _d(99, 197.00, 198.11, "cung mot cau", LOP_HAI_NGUON, False),
    ]
    ra = mot_dong_moi_cap(d)
    assert len(ra) == 1, [s.text for s in ra]
    assert ra[0].suspect is False, "phai giu ban OCR (suspect=False)"


def test_ban_long_BO_logo_long_trong_loi_thoai():
    """Ca i=109/i=110: ca hai deu mot_nguon, nen loc theo layer KHONG bat duoc.

    Do duoc: neu chi loc theo `layer` thi ham tra ve CA HAI. Phai dung `chua_trong` —
    no da danh dau san doan nao nam gon trong doan nao.
    """
    d = [
        _d(109, 219.17, 221.11, "loi noi that", LOP_MOT_NGUON, True),
        _d(110, 220.00, 220.50, "LOGO", LOP_MOT_NGUON, False, chua_trong=109),
    ]
    ra = mot_dong_moi_cap(d)
    assert [s.text for s in ra] == ["loi noi that"], [s.text for s in ra]


def test_ban_long_GIU_CA_HAI_khi_hai_cau_khong_chong_nhau():
    d = [
        _d(0, 0.0, 1.0, "cau mot", LOP_HAI_NGUON, False),
        _d(1, 2.0, 3.0, "cau hai", LOP_HAI_NGUON, False),
    ]
    assert [s.text for s in mot_dong_moi_cap(d)] == ["cau mot", "cau hai"]


def test_ban_long_KHONG_dung_toi_du_lieu_cu_khong_co_lop():
    """Ban ghi tao truoc khi backend co truong `layer` — khong duoc doan bua."""
    d = [
        _d(0, 0.0, 1.0, "cu mot"),
        _d(1, 0.5, 1.5, "cu hai"),
    ]
    assert len(mot_dong_moi_cap(d)) == 2

