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

from app.pipeline.dub import ke_hoach_toc_do, rap, trong_im_lang


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
    """Chỉ tốc độ được đổi; hàm KHÔNG trả về danh sách dòng phải sửa chữ.

    Ghim lời người dùng: "ko cần phải cắt mà chỉnh tốc độ là được". Bản cũ trả `qua_tran`
    để giao diện kêu người dùng sửa chữ — bỏ hẳn khái niệm đó.
    """
    ra = ke_hoach_toc_do([9.0], [1.0], [1.0])
    assert isinstance(ra, tuple) and len(ra) == 2, (
        f"phải trả đúng (toc_do, need), đo được {len(ra)} phần tử"
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
