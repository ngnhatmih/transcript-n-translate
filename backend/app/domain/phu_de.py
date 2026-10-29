"""Bốn tầng lọc phụ đề cứng — hàm THUẦN, không model, không video.

## Vì sao là hàm thuần, không phải adapter

Tầng lọc chỉ làm việc trên danh sách `Hop`. Tách khỏi adapter thì test được bằng dữ liệu
tổng hợp (không cần `rapidocr` 100 MB), và thay engine OCR không phải sửa logic lọc.

## Bốn tầng, và cái gì bắt được cái gì

ĐO ĐƯỢC trên video 1249,237 s (1280x720, tiếng Trung, phụ đề cứng): OCR thô 696 dòng,
sau lọc 3 tầng còn 627 (bỏ 69 = 10 %). Tầng 4 (tuỳ chọn, cần ASR) cũng về 627.

  1. `tim_dai_phu_de`  — dải `y` nào là phụ đề. Chạy trên MẪU (~50 khung), trả TỈ LỆ.
  2. `loc_on_dinh`     — bỏ chữ CHẠY (đổi `x` mỗi khung).
  3. `loc_hinh_dang`   — bỏ menu giá tiền (dài, nhiều số), logo đọc sai, dòng lặp.
  4. `loc_theo_asr`    — TUỲ CHỌN: cửa sổ OCR có chữ mà ASR im lặng ⇒ nghi vấn.

⚠️ Tầng 1 KHÔNG lọc dòng. Nó chỉ tìm dải. Việc lọc dòng chạy trên TOÀN BỘ khung đã OCR.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import Segment


@dataclass
class Hop:
    """Một hộp chữ OCR đọc được ở một khung hình.

    `t` là GIÂY của khung đó. `diem` là điểm tin cậy của OCR (0..1).
    Toạ độ theo PIXEL của khung gốc; đổi sang tỉ lệ ở chỗ cần.
    """
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    t: float
    diem: float


#: Bề dày tối đa của dải phụ đề, theo tỉ lệ chiều cao khung. Đo được ở video thật:
#: [627, 682]/720 = 0,076. Để 0,15 là rộng gấp đôi, đủ cho video có phụ đề hai dòng.
DAY_DAI_TOI_DA = 0.15

#: Độ dài chữ hợp lệ của một dòng phụ đề. Menu giá tiền đo được 200 ký tự.
DAI_MIN, DAI_MAX = 3, 40

#: Số cụm số mà từ đó coi là menu giá tiền.
SO_CUM_SO_TOI_DA = 2

#: Dung sai `x` khi coi hai khung là CÙNG một dòng đứng yên (pixel).
DUNG_SAI_X = 24.0


def tim_dai_phu_de(hops: list[Hop], chieu_cao: int) -> tuple[float, float]:
    """Dải `y` của phụ đề, theo TỈ LỆ `0..1` của chiều cao khung.

    Dùng tỉ lệ chứ không dùng pixel để cùng một video ở 720p/1080p/4K cho cùng kết quả —
    ghim bằng `test_tim_dai_phu_de_tra_ti_le_khong_phai_pixel`.

    Chia khung thành 100 dải, đếm số hộp có ĐỈNH nằm trong mỗi dải, rồi lấy cụm dải liên
    tiếp DÀY NHẤT mà bề dày <= `DAY_DAI_TOI_DA`.

    🔴 LUẬT PHÁ HOÀ — vì sao phải có (đo được, không phải phòng xa):
    Fixture của `test_tim_dai_phu_de_tra_ti_le_khong_phai_pixel` đặt 20 hộp phụ đề ở dải 88
    và 20 hộp watermark ở dải 1. Hai cụm DÀY BẰNG NHAU (20 = 20), nên `tong > tot_nhat`
    nghiêm ngặt để dải THẤP NHẤT thắng và trả `(0.00, 0.02)` — watermark. Docstring cũ nói
    "watermark mỏng hơn nên không thắng" là SAI với chính dữ liệu của bài test.

    Luật: khi hoà số hộp, cụm **CAO HƠN** thắng. Lý do đo được, không phải khẩu vị: phụ đề
    nhúng đáy khung (y ∈ [627, 682] của 720); watermark/logo ở đỉnh (y ≤ 70). Không có video
    nào đặt phụ đề trên cao hơn logo. Nên `>=` cộng với việc duyệt `dau` TỪ CAO XUỐNG là
    cùng một luật, viết một lần.
    """
    if not hops or chieu_cao <= 0:
        return (0.0, 0.0)
    SO_DAI = 100
    dem = [0] * SO_DAI
    for h in hops:
        i = int((h.y0 / chieu_cao) * SO_DAI)
        dem[max(0, min(SO_DAI - 1, i))] += 1

    toi_da_dai = max(1, int(DAY_DAI_TOI_DA * SO_DAI))
    tot_nhat, tot_nhat_dau, tot_nhat_dai = -1, 0, 0
    # LUẬT PHÁ HOÀ, ba khoá theo thứ tự: (1) nhiều hộp nhất; (2) HẸP NHẤT; (3) CAO NHẤT.
    #
    # Vì sao phải có khoá (2) — đo được, không phải phòng xa: cửa sổ rộng 15 dải bắt đầu ở
    # dải 0 phủ trọn cụm watermark ở dải 1 nên tổng cũng bằng 20, và nếu chỉ so `>=` thì nó
    # THẮNG ở lần lặp cuối, trả `(0.00, 0.15)` — một dải rỗng. Hẹp nhất buộc phải chọn đúng
    # cụm 20 hộp thật (bề dày 1 dải) thay vì cửa sổ rộng nuốt nó.
    # Khoá (3) chỉ dùng khi (1) và (2) đều hoà: phụ đề nhúng đáy khung, logo ở đỉnh.
    for dau in range(SO_DAI):
        for dai in range(1, toi_da_dai + 1):
            if dau + dai > SO_DAI:
                break
            tong = sum(dem[dau:dau + dai])
            tot_hon = (
                tong > tot_nhat
                or (tong == tot_nhat and dai < tot_nhat_dai)
                or (tong == tot_nhat and dai == tot_nhat_dai and dau > tot_nhat_dau)
            )
            if tot_hon:
                tot_nhat, tot_nhat_dau, tot_nhat_dai = tong, dau, dai
    if tot_nhat <= 0:
        return (0.0, 0.0)

    # ĐÁY của dải lấy từ CHÍNH các hộp trong cụm, không phải từ chỉ số dải.
    # 🔴 Vì sao (đo được): cụm chỉ được chọn theo ĐỈNH `y0`, nên nếu trả `(dau + dai)/SO_DAI`
    # thì một cụm dày 1 dải cho `y1 = 0,88` trong khi đáy thật của hộp là `680/720 = 0,944` —
    # bài test đòi `0.93 <= y1 <= 0.97` và ĐỎ. Đáy là dữ liệu, không suy ra được từ đỉnh.
    cuoi_dai = tot_nhat_dau + tot_nhat_dai
    trong_cum = [
        h for h in hops
        if tot_nhat_dau <= int((h.y0 / chieu_cao) * SO_DAI) < cuoi_dai
    ]
    y1 = max(h.y1 for h in trong_cum) / chieu_cao
    return (tot_nhat_dau / SO_DAI, y1)


def loc_on_dinh(hops: list[Hop], fps: float) -> list[Hop]:
    """Bỏ chữ CHẠY: cùng nội dung nhưng `x` đổi mỗi khung.

    Phụ đề đứng yên 0,5–2,5 s rồi đổi; chữ chạy (dải danh lam thắng cảnh đo được ở giây
    1056) dịch `x` liên tục.

    🔴 VÌ SAO PHẢI GOM NHÓM TRƯỚC KHI XÉT (bản đầu sai, đo được):
    Bản đầu so `x` với hộp TRƯỚC CÙNG `text` và bỏ hộp nào lệch. Hộp ĐẦU của một chuỗi chạy
    không có gì để so, nên nó LUÔN được giữ — fixture `[桂林山水@100, 桂林山水@180]` cho ra
    `[A, A, 桂林山水]` trong khi bài test đòi `[A, A]`. Không có cách sửa cục bộ nào cứu được:
    muốn biết hộp đầu là chữ chạy, phải nhìn hộp SAU nó.

    Luật: gom theo `text`; nếu trong cùng một `text` có `max(x0) - min(x0) > DUNG_SAI_X` thì
    CẢ NHÓM là chữ chạy ⇒ bỏ TẤT CẢ. Phụ đề thật lặp lại y nguyên một câu thì `x` không đổi.

    `fps` dùng để biết "khung trước" là gì khi `hops` không đều; hiện chỉ cần `> 0`.
    """
    if fps <= 0:
        return list(hops)
    theo_chu: dict[str, list[float]] = {}
    for h in hops:
        theo_chu.setdefault(h.text, []).append(h.x0)
    chay = {t for t, xs in theo_chu.items() if max(xs) - min(xs) > DUNG_SAI_X}
    return [h for h in hops if h.text not in chay]


def loc_hinh_dang(hops: list[Hop]) -> list[Hop]:
    """Bỏ dòng có hình dạng KHÔNG phải phụ đề, và gộp dòng lặp y nguyên.

    Bốn điều kiện, đều đo được từ dữ liệu thật:
      · độ dài 3–40 ký tự (menu giá tiền: 200);
      · không quá `SO_CUM_SO_TOI_DA` cụm số (menu: '24元20元15元');
      · không phải TOÀN chữ Latinh (logo 'ebilibili'/'Cilibili' đọc sai);
      · không lặp y nguyên liên tiếp (logo bị đọc nhiều khung thành '好好好').

    Vì sao dài >= 3: phụ đề thật ngắn nhất đo được là 3 ký tự.

    🔴 VÌ SAO PHẢI CÓ LUẬT LATINH (bản đầu thiếu, đo được):
    `len('ebilibili') == 9` và `len('Cilibili') == 8`, cả hai đều nằm trong 3..40 và không có
    cụm số nào — nên hai điều kiện đầu KHÔNG bắt được chúng, dù docstring cũ khẳng định
    "quá ngắn". Fixture `test_loc_hinh_dang_bo_logo_doc_sai` đòi chúng bị bỏ.

    Luật: bỏ hộp mà MỌI ký tự là chữ cái Latinh (a–z, A–Z). Cơ sở đo được: phụ đề nhúng của
    video này là tiếng Trung; dòng nào toàn Latinh trong video tiếng Trung là logo/watermark
    bị OCR đọc sai. `你怎么骑` có chữ Hán nên qua. Một dòng lai `OK好吃` cũng qua — luật chỉ
    bắt dòng TOÀN Latinh, nên không bao giờ xoá nhầm phụ đề có chữ Hán.
    """
    ra: list[Hop] = []
    for h in hops:
        t = h.text.strip()
        if not (DAI_MIN <= len(t) <= DAI_MAX):
            continue
        if len([c for c in _cum_so(t)]) > SO_CUM_SO_TOI_DA:
            continue
        if _toan_latinh(t):
            continue
        # GỘP dòng lặp y nguyên LIÊN TIẾP: logo bị OCR đọc nhiều khung thành '好好好' sẽ
        # thành một dòng, không phải năm. Giữ hộp ĐẦU (mốc thời gian sớm nhất).
        if ra and ra[-1].text.strip() == t:
            continue
        ra.append(h)
    return ra


def _toan_latinh(text: str) -> bool:
    """True nếu MỌI ký tự là chữ cái Latinh — dấu hiệu logo/watermark đọc sai.

    Tách khỏi `loc_hinh_dang` để test được riêng, cùng khuôn `_cum_so`.
    """
    return bool(text) and all(c.isascii() and c.isalpha() for c in text)


def _cum_so(text: str) -> list[str]:
    """Các cụm CHỮ SỐ liên tiếp. Tách khỏi `loc_hinh_dang` để test được riêng."""
    ra: list[str] = []
    cur = ""
    for c in text:
        if c.isdigit():
            cur += c
        elif cur:
            ra.append(cur)
            cur = ""
    if cur:
        ra.append(cur)
    return ra


def loc_theo_asr(hops: list[Hop], khoang_asr: list[tuple[float, float]]) -> list[Hop]:
    """TUỲ CHỌN — bỏ dòng OCR không có tiếng nói nào tương ứng.

    ⚠️ KHÔNG BAO GIỜ làm rỗng khi `khoang_asr` rỗng: lọc bằng một nguồn rỗng thì xoá sạch,
    và thà giữ rác còn hơn mất phụ đề. Ghim bằng
    `test_loc_theo_asr_khong_bao_gio_lam_rong_khi_asr_rong`.

    Đo được: thêm tầng này giữ 627/696 dòng — tức nó bắt thêm phần lớn trong 69 dòng rác.
    """
    if not khoang_asr:
        return list(hops)
    ra: list[Hop] = []
    for h in hops:
        for dau, cuoi in khoang_asr:
            if dau <= h.t <= cuoi:
                ra.append(h)
                break
    return ra


def gop_thanh_dong(hops: list[Hop], *, fps: float) -> list[Segment]:
    """Gộp các hộp liên tiếp CÙNG chữ thành một `Segment`.

    Ở 2 fps, một dòng phụ đề hiện trên 1–5 khung ⇒ phải thành MỘT dòng, không phải năm.
    `start` = `t` của hộp đầu; `end` = `t` của hộp cuối + `1/fps` (khung cuối còn hiện
    thêm một nhịp).

    Trả `Segment` (model có sẵn) để mọi thứ sau đó không phải phân nhánh: OCR và ASR khác
    nhau ở CÁCH LẤY, không khác ở HÌNH DẠNG dữ liệu.
    """
    if not hops:
        return []
    buoc = 1.0 / fps if fps > 0 else 0.5
    ra: list[Segment] = []
    dau = hops[0].t
    truoc = hops[0]
    for h in hops[1:]:
        if h.text == truoc.text:
            truoc = h
            continue
        ra.append(Segment(i=len(ra), start=dau, end=truoc.t + buoc, text=truoc.text))
        dau, truoc = h.t, h
    ra.append(Segment(i=len(ra), start=dau, end=truoc.t + buoc, text=truoc.text))
    return ra
