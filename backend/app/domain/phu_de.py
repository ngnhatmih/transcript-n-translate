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
#:
#: ĐO ĐƯỢC trên 7864 hộp thô của video 1249,237 s, sau khi lọc đúng dải phụ đề
#: (`tim_dai_phu_de` -> `y ∈ [0,87; 0,996]`): 403 text lặp lại, spread `max(x0)-min(x0)`:
#:
#:     <=  0 px:  96 text (23,7 %)      <=  8 px: 394 text (97,3 %)
#:     <=  1 px: 244 text (60,2 %)      <= 12 px: 398 text (98,3 %)  <- hết cụm phụ đề
#:     <=  2 px: 340 text (84,0 %)        31 px: 1 text  ('12')
#:     <=  4 px: 383 text (94,6 %)        60 px: 1 text  ('驴肉')
#:                                       755 px: 1 text  ('元')
#:
#: KHOẢNG TRỐNG **12 -> 31 px RỖNG HOÀN TOÀN**. Mọi ngưỡng trong `[12, 31)` cho CÙNG kết
#: quả: bỏ đúng 7 text, giữ 398. Nên 24 nằm giữa một cao nguyên 19 px rộng, không phải một
#: con số may mắn — ghim bằng `test_dung_sai_x_nam_trong_khoang_trong_do_duoc`.
#:
#: 7 text bị bỏ đều là mẩu menu giá / chữ rời, không phải phụ đề: '12', '驴肉', '15',
#: '20元', '16', '烤', '元'. Hạ ngưỡng xuống 4 hoặc 8 sẽ bỏ OAN 15–22 dòng phụ đề thật.
DUNG_SAI_X = 24.0


def tim_dai_phu_de(hops: list[Hop], chieu_cao: int) -> tuple[float, float]:
    """Dải `y` của phụ đề, theo TỈ LỆ `0..1` của chiều cao khung.

    Dùng tỉ lệ chứ không dùng pixel để cùng một video ở 720p/1080p/4K cho cùng kết quả —
    ghim bằng `test_tim_dai_phu_de_tra_ti_le_khong_phai_pixel`.

    Chia khung thành 100 dải, đếm số DÒNG KHÁC NHAU có ĐỈNH nằm trong mỗi dải, rồi
    lấy cụm dải liên tiếp có MẬT ĐỘ cao nhất mà bề dày <= `DAY_DAI_TOI_DA`.

    🔴 MẬT ĐỘ, KHÔNG PHẢI TỔNG (bản trước cộng dồn — SAI, đo được trên video thật).
    Tổng các dải ĐƠN ĐIỆU TĂNG theo bề rộng cửa sổ, nên "tổng lớn nhất" luôn chọn cửa sổ
    RỘNG NHẤT: `DAY_DAI_TOI_DA` không còn là ràng buộc mà thành MỤC TIÊU. Đo được trên
    7864 hộp thô của video 1249,237 s: cửa sổ 15 dải từ dải 0 có tổng 1121 và THẮNG, trong
    khi cụm phụ đề thật ở dải 86-87 chỉ có 698. Kết quả trả về `y0=0,0000 y1=0,9986` —
    bề dày **719/720 pixel = 100 % khung**, tức không tìm ra dải nào cả.
    Chấm theo `tổng / bề rộng` thì cụm thật thắng: dải 87 một mình có mật độ **509**, và
    trả `y0=0,8700 y1=0,9958` — bề dày 90,6 pixel = 13 % khung, khớp `[627, 682]/720` đã
    ghi ở `DAY_DAI_TOI_DA`.
    Số đo từng dải (text khác nhau): 87 -> 509, 86 -> 189, 3 -> 254, 0 -> 138; phần còn
    lại dưới 80. Một dải phụ đề dày 2 dải thắng một cửa sổ 15 dải rải rác — đó là điều
    "mật độ" nói và "tổng" không nói được.

    🔴 ĐẾM DÒNG KHÁC NHAU, KHÔNG ĐẾM HỘP (bản đầu đếm hộp — SAI, đo được).
    Logo/wartermark là HẰNG SỐ theo thời gian: nó xuất hiện ở MỌI khung với cùng một
    chuỗi, nên đếm hộp thì nó luôn thắng phụ đề (phụ đề chỉ có ở ~40-60 % số khung).
    Đo được, 6 ca:
        logo 20/20 khung, phụ đề 10/20  -> đếm hộp: px(28,8) SAI | đếm dòng: px(626,4) ĐÚNG
        logo 20/20 khung, phụ đề  1/20  -> đếm hộp: px(28,8) SAI | đếm dòng: px(626,4) ĐÚNG
        watermark 30 hộp vs phụ đề 20  -> đếm hộp: px( 0,0) SAI | đếm dòng: px(626,4) ĐÚNG
        logo 10/10, phụ đề 10/10       -> ĐÚNG cả hai
        không logo                      -> ĐÚNG cả hai
        hoà 20/20 cả hai                -> ĐÚNG cả hai (khoá "cao hơn" quyết)
    Vì sao đúng: một logo lặp y nguyên ở 20 khung là MỘT dòng; 10 câu phụ đề khác nhau
    là MƯỜI dòng. Đếm dòng đo ĐÚNG lượng thông tin, đếm hộp đo số lần lặp.

    🔴 LUẬT PHÁ HOÀ — mật độ là khoá, `x` là khoá phụ, và ràng buộc bắt buộc:

    (1) MẬT ĐỘ CAO NHẤT (`tổng / bề rộng`). Không dùng tổng trần — xem vì sao ở trên.

    (2) CAO HƠN, khi (1) hoà. Lý do đo được, không phải khẩu vị: phụ đề nhúng đáy khung
    (y ∈ [627, 682] của 720); watermark/logo ở đỉnh (y ≤ 70). Không video nào đặt phụ đề
    trên cao hơn logo. Hoà mật độ là ca THẬT: `test_tim_dai_phu_de_tra_ti_le_khong_phai_pixel`
    đặt 20 dòng phụ đề ở dải 87 và 20 dòng watermark ở dải 1 — hai cụm mật độ 20,00 như nhau.

    🔴 RÀNG BUỘC: cửa sổ phải BẮT ĐẦU ở một dải CÓ HỘP. Không có nó, cửa sổ rộng 15 dải
    bắt đầu ở một dải rỗng sẽ có mật độ thấp hơn (cùng tổng, chia nhiều dải hơn) — nên
    ràng buộc này vẫn cần cho trường hợp bề rộng lớn hơn làm loãng mật độ. Nó KHÔNG chặn
    được ca 100 % khung: dải 0 của video thật CÓ 138 text, nên cửa sổ từ dải 0 hợp lệ và
    mật độ của nó (1121/15 = 74,7) vẫn thua 509 của dải 87.
    """
    if not hops or chieu_cao <= 0:
        return (0.0, 0.0)
    SO_DAI = 100
    # Mỗi dải giữ TẬP `text` khác nhau, không phải số hộp — xem vì sao ở docstring.
    theo_dai: dict[int, set[str]] = {}
    for h in hops:
        i = int((h.y0 / chieu_cao) * SO_DAI)
        theo_dai.setdefault(max(0, min(SO_DAI - 1, i)), set()).add(h.text)
    dem = [len(theo_dai.get(i, ())) for i in range(SO_DAI)]

    toi_da_dai = max(1, int(DAY_DAI_TOI_DA * SO_DAI))
    # Khoá (1) là MẬT ĐỘ, không phải tổng — xem docstring. Khoá (2) `dau > tot_nhat_dau`
    # phá hoà theo hướng CAO HƠN, và chỉ chạy khi mật độ BẰNG NHAU thật (`==` trên float
    # ở đây an toàn vì cả hai vế đều là `tong / dai` của số nguyên — cùng phép chia, cùng
    # kết quả, không có tích luỹ sai số).
    tot_nhat, tot_nhat_dau, tot_nhat_dai = -1.0, 0, 0
    for dau in range(SO_DAI):
        if dem[dau] == 0:
            continue          # cửa sổ phải bắt đầu ở dải CÓ hộp
        for dai in range(1, toi_da_dai + 1):
            if dau + dai > SO_DAI:
                break
            tong = sum(dem[dau:dau + dai])
            mat_do = tong / dai
            tot_hon = (
                mat_do > tot_nhat
                or (mat_do == tot_nhat and dau > tot_nhat_dau)
            )
            if tot_hon:
                tot_nhat, tot_nhat_dau, tot_nhat_dai = mat_do, dau, dai
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
