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
from app.domain.phu_de import xep_hang_trong_lop
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


def test_ban_long_giu_dong_TREN_cua_layer_1_khi_OCR_va_ASR_cung_cau():
    """🔴 HOP DONG (nguoi dung chot 2026-11-02): "toi chi bao dung phu de cua cai
    tren cua layer 1 chu co bao bo cai gi dau".

    Nghia la: TIMELINE giu CA HAI dong de nguoi doc soat, con PHU DE / BAN LONG chi
    lay dong cua LOP 1. Khong duoc bo dong nao khoi du lieu — chi chon dong nao duoc
    dung.

    Ca that tren #41 (nguoi dung gui anh):

        i=7 [7.02-9.66]S "要经常证明自己的作品是有价值的长"   <- ASR (lan duoi)
        i=8 [7.50-8.00]  "经常要证明"                        <- OCR (lan tren)

    Phai lay i=8. Ban truoc bo i=8 vi no co `chua_trong`, nen ban long doc cau ASR dai
    — dung ca nguoi dung bao "van bi dung cai duoi".
    """
    d = [
        _d(7, 7.02, 9.66, "ASR dai", LOP_HAI_NGUON, True),
        _d(8, 7.50, 8.00, "OCR ngan", LOP_MOT_NGUON, False, chua_trong=7),
    ]
    ra = mot_dong_moi_cap(d)
    assert [s.text for s in ra] == ["OCR ngan"], (
        "phai lay dong TREN cua layer 1 (OCR), do duoc: " + repr([s.text for s in ra]))


def test_ban_long_GIU_CA_HAI_khi_hai_cau_khong_chong_nhau():
    d = [
        _d(0, 0.0, 1.0, "cau mot", LOP_HAI_NGUON, False),
        _d(1, 2.0, 3.0, "cau hai", LOP_HAI_NGUON, False),
    ]
    assert [s.text for s in mot_dong_moi_cap(d)] == ["cau mot", "cau hai"]


def test_ban_long_gop_du_lieu_cu_chong_nhau_thanh_MOT_dong():
    """Ban ghi tao truoc khi backend co truong `layer`.

    Hai dong chong nhau van la "cung mot cau" theo phep do THOI GIAN, nen chi duoc doc
    MOT lan. Ban truoc giu ca hai vi doi `layer` — nhung luc do chung se duoc doc hai
    lan chong len nhau, dung thu ma rang buoc "dong N khong duoc con noi khi N+1 bat
    dau" cam.
    """
    d = [
        _d(0, 0.0, 1.0, "cu mot"),
        _d(1, 0.5, 1.5, "cu hai"),
    ]
    ra = mot_dong_moi_cap(d)
    assert len(ra) == 1, [s.text for s in ra]




# ---------------------------------------------------------------------------
# PHỤ ĐỀ BURN: một câu một lúc — đoạn sau ĐỢI đoạn trước hiện xong
#
# 🔴 Chủ dự án: "khi burn phụ đề có mấy cái bị đè nhau … tôi muốn nó đợi cái được burn
# trước hết xong mới đến lượt cái sau", giới hạn phạm vi: "vẫn đang xét trong layer 1 /
# làn 1 thôi".
#
# Đo được trên bản dịch #63: 163 đoạn, 61 cặp chồng, tổng 64,26 s — ví dụ
# `7,02-8,00` (lớp 1) nằm dưới `7,02-9,66` (lớp 2). Sau `mot_dong_moi_cap`: 110 đoạn,
# 0 cặp chồng. `xep_hang_trong_lop` là BẢO HIỂM cho dữ liệu mà hai dòng CÙNG lớp vẫn chồng.
# ---------------------------------------------------------------------------

def test_xep_hang_doi_DAU_doan_sau_len_END_doan_truoc():
    d = [
        _d(1, 1.00, 3.00, "trước", LOP_MOT_NGUON, False),
        _d(2, 2.00, 4.00, "sau", LOP_MOT_NGUON, False),
    ]
    ra = xep_hang_trong_lop(d)
    sau = [s for s in ra if s.i == 2][0]
    assert sau.start == 3.00, f"đoạn sau phải đợi đoạn trước xong (3,00), đo được {sau.start}"
    assert sau.end == 4.00, "KHÔNG được cắt chữ — `end` giữ nguyên"


def test_xep_hang_KHONG_dung_vao_lop_khac():
    """Hai LỚP là hai làn hiển thị; chồng nhau ở đó là bình thường, không được dời."""
    d = [
        _d(1, 1.00, 3.00, "lớp 1", LOP_MOT_NGUON, False),
        _d(2, 1.00, 3.00, "lớp 2", LOP_HAI_NGUON, False),
    ]
    ra = xep_hang_trong_lop(d)
    assert [(s.i, s.start, s.end) for s in ra] == [(1, 1.0, 3.0), (2, 1.0, 3.0)]


def test_xep_hang_KHONG_de_doan_thanh_ZERO_giay():
    """Dời `start` lên sát `end` thì phải kéo `end`, không được để đoạn vô hình."""
    d = [
        _d(1, 1.00, 5.00, "dài", LOP_MOT_NGUON, False),
        _d(2, 1.00, 1.20, "ngắn", LOP_MOT_NGUON, False),
    ]
    ra = xep_hang_trong_lop(d)
    sau = [s for s in ra if s.i == 2][0]
    assert sau.start == 5.00, sau.start
    assert sau.end > sau.start, (
        f"đoạn không được dài 0 giây: {sau.start}..{sau.end}"
    )
    assert abs((sau.end - sau.start) - 0.20) < 1e-9, "giữ ĐÚNG độ dài cũ (0,20 s)"


def test_xep_hang_khong_sua_tai_cho_va_giu_nguyen_thu_tu_khac():
    d = [
        _d(2, 2.00, 4.00, "sau", LOP_MOT_NGUON, False),
        _d(1, 1.00, 3.00, "trước", LOP_MOT_NGUON, False),
    ]
    ra = xep_hang_trong_lop(d)
    assert [s.i for s in ra] == [1, 2], "trả theo thứ tự thời gian"
    assert d[0].start == 2.00 and d[1].start == 1.00, "KHÔNG được sửa danh sách gốc"


def test_xep_hang_danh_sach_rong():
    assert xep_hang_trong_lop([]) == []


def test_ASS_burn_khong_con_HAI_dong_cung_lop_chong_nhau():
    """Chuỗi đầy đủ của đường burn: lọc theo lớp → xếp hàng → dựng `.ass`.

    Ghim bằng chính `export.render("ass", …)`: đọc ngược thời gian từ sự kiện `Dialogue`
    rồi khẳng định không còn hai dòng CÙNG LỚP nào chồng nhau.
    """
    import re

    from app.pipeline.export import render

    #: ⚠️ Đi THẲNG qua `xep_hang_trong_lop`, KHÔNG qua `mot_dong_moi_cap`: hàm lọc kia GỘP
    #: mọi đoạn chồng thời gian vào cùng một "cặp", nên nó đã dẹp chồng từ trước và phép
    #: xếp hàng không còn gì để làm. Ở đây ta kiểm chính phép xếp hàng.
    doan = xep_hang_trong_lop([
        _d(1, 0.00, 2.00, "câu một", LOP_MOT_NGUON, False),
        _d(2, 1.50, 3.00, "câu hai", LOP_MOT_NGUON, False),
    ])
    ass = render("ass", doan, translations=[s.text for s in doan],
                 khung=(1080, 1920), style={"co": 54, "cao_hop": 180, "kieu_vien": 3})

    def giay(s: str) -> float:
        h, m, r = s.split(":")
        return int(h) * 3600 + int(m) * 60 + float(r)

    khung_thoi = []
    for line in ass.splitlines():
        if not line.startswith("Dialogue:") or "\\p1" in line:
            continue
        phan = line.split(",", 9)
        khung_thoi.append((giay(phan[1]), giay(phan[2]), phan[9]))

    khung_thoi.sort()
    for (a0, a1, atext), (b0, b1, btext) in zip(khung_thoi, khung_thoi[1:]):
        assert b0 >= a1 - 1e-6, (
            f"còn chồng: {a0:.2f}-{a1:.2f} {atext[:24]!r} || {b0:.2f}-{b1:.2f} {btext[:24]!r}"
        )
    assert len(khung_thoi) == 2, [t for _, _, t in khung_thoi]
    assert "câu hai" in " ".join(t for _, _, t in khung_thoi)


def test_ASS_burn_giu_NGUYEN_ban_OCR_khi_mot_cau_co_hai_ban():
    """Vế đối chứng: lọc theo lớp phải giữ bản OCR (lớp 1), không phải bản ASR."""
    from app.pipeline.export import render

    d = [
        _d(1, 0.00, 2.00, "OCR đọc đúng", LOP_MOT_NGUON, False),
        _d(2, 0.00, 2.00, "ASR nghe sai", LOP_HAI_NGUON, True),
    ]
    doan = xep_hang_trong_lop(
        [s for s in d if s.i in {x.i for x in mot_dong_moi_cap(list(d))}])
    ass = render("ass", doan, translations=[s.text for s in doan],
                 khung=(1080, 1920), style={"co": 54, "cao_hop": 180, "kieu_vien": 3})
    assert "OCR đọc đúng" in ass
    assert "ASR nghe sai" not in ass, "bản ASR KHÔNG được burn cùng câu"
