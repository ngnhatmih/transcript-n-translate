"""Ba hàm của đường lồng tiếng — phần THUẦN, không TTS, không ffmpeg.

Số liệu dùng ở đây lấy từ lượt đo trên 14 dòng thật của clip 20:49 (`take/chỗ` từ 1,00× tới
1,62×): chỗ nào làm được bằng phép tính thì không cần cài VieNeu để kiểm.
"""
from __future__ import annotations

import numpy as np

from app.pipeline.dub import ke_hoach_toc_do, rap, trong_im_lang


def test_thang_bac_gom_toc_do_ve_vai_moc_va_ton_trong_tran():
    # take/chỗ = 1.02, 1.18, 1.40 (dòng cuối vượt trần 1.35)
    takes, slots, avails = [1.02, 1.18, 1.40], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]
    toc_do, need, qua_tran = ke_hoach_toc_do(takes, slots, avails, tran=1.35, bac=0.05)
    assert [round(n, 2) for n in need] == [1.02, 1.18, 1.4]
    assert toc_do == [1.05, 1.20, 1.35], toc_do   # bậc nhỏ nhất ≥ need, kẹp ở trần
    assert qua_tran == [2], qua_tran
    assert len(set(toc_do)) <= 3, "thang bậc phải gom về VÀI mốc, không mỗi dòng một số"


def test_khong_bao_gio_doc_cham_di():
    """Take ngắn hơn chỗ ⇒ tốc độ 1,00, KHÔNG kéo chậm để lấp chỗ trống."""
    toc_do, need, _ = ke_hoach_toc_do([0.4, 0.9], [1.0, 1.0], [1.0, 1.0])
    assert toc_do == [1.0, 1.0], toc_do
    assert need == [0.4, 0.9]


def test_muon_duoc_khoang_lang_thi_can_it_toc_do_hon():
    """Cùng take 1,5 s: chỗ 1,0 s nhưng dòng sau bắt đầu ở 1,5 s ⇒ chỉ cần 1,0×."""
    khong_muon, _, qua_khong = ke_hoach_toc_do([1.5], [1.0], [1.0])
    co_muon, _, qua_co = ke_hoach_toc_do([1.5], [1.0], [1.5])
    assert khong_muon == [1.35] and qua_khong == [0]      # 1.5 > tran -> phải sửa
    assert co_muon == [1.00] and qua_co == []          # mượn 0.5 s lặng là đủ


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
