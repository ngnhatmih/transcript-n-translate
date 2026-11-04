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

import math

from dataclasses import dataclass

from app.domain.models import Segment, Word, GOC_TOI_DA


def goc_hop(diem: list) -> float:
    """Goc NGHIENG cua hop, do — am la nghieng sang phai (chieu kim dong ho).

    `diem` la bon diem `[[x,y], ...]` theo thu tu goc tren-trai, tren-phai, duoi-phai,
    duoi-trai (thu tu RapidOCR tra ve). Lay canh TREN (`p0 -> p1`) lam chieu chu.

    Vi sao can: `x0/y0/x1/y1` la HINH CHU NHAT BAO, no xoa mat goc nghieng. Do duoc tren
    nguon 6: phu de cung luon `0.0`, con poster chup xien trong canh thi `-9.5` den
    `-16.9`. Khong co goc thi khong phan biet duoc hai thu do.

    Tra `0.0` khi khong du bon diem — coi nhu nam ngang, KHONG loai hop. The la an toan:
    hinh dang lai la mot phep do co the sai, con bo nham phu de thi mat chu that.
    """
    if not diem or len(diem) < 4:
        return 0.0
    p0, p1 = diem[0], diem[1]
    dx = float(p1[0]) - float(p0[0])
    dy = float(p1[1]) - float(p0[1])
    if dx == 0.0 and dy == 0.0:
        return 0.0
    return math.degrees(math.atan2(dy, dx))


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

    #: Goc NGHIENG cua hop, do. Xem `loc_hinh_dang` — day la phep do HINH HOC duy nhat
    #: trong ca file, va no la thu phan biet phu de cung voi chu tren poster/bien hieu.
    #:
    #: DO DUOC tren nguon 6, khung 193.0-194.0 s:
    #:
    #:     goc =   0.0   'biibili'              watermark, nam ngang
    #:     goc =   0.0   '想想工作室'            watermark, nam ngang
    #:     goc =   0.0   '中仑山区民族器乐学'     bien hieu, nam ngang
    #:     goc =  -9.5   '9福州烟台山'           POSTER, nghieng
    #:     goc = -16.9   '2026-10-2027·1'      POSTER, nghieng
    #:     goc = -14.6   '开2026见'             POSTER, nghieng
    #:
    #: Khoang trong 0.0 -> -5.9 do rong, khong ca nao o giua, nen nguong 3 do tach sach.
    goc: float = 0.0


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
        # 🔴 HOP NGHIENG: KHONG `continue` — KHONG XOA.
        #
        # Nguoi dung chot: "neu bi nghieng thi ko doc" NHUNG "van co luu nha dung xoa
        # may cai nghieng chi la ko cho vao layer nao thoi".
        #
        # Ban dau toi dat `continue` o day — SAI, no xoa han hop khoi du lieu. Do duoc
        # hau qua (job asr #152): transcript #46 con 152 doan thay vi 158, va 6 khoi
        # poster bien mat khoi ban ghi, khong khoi phuc duoc.
        #
        # Gio hop nghieng di het pipeline (gop dong, chon nguon) roi `nguon_chu`
        # gan `layer = ""` — van luu, khong vao lan nao. Do goc: xem `nguon_chu`.
        #
        # Cac luat NOI DUNG ben duoi VAN ap cho hop nghieng: mot logo nghieng ngan hon
        # 3 ky tu van bi bo vi no khong phai chu de doc.
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


def noi_manh_cung_dong(hops: list[Hop]) -> list[Hop]:
    """NỐI các mảnh của CÙNG một lần hiện phụ đề, bị dòng khác chen vào giữa.

    ## Lỗi thật (chủ dự án báo: *"các đoạn dùng ocr bị khá là ngắn mặc dù phụ đề trên vid
    ## đoạn phụ đề đấy chưa kết thúc"*)

    `gop_thanh_dong` chỉ nối các hộp **cùng chữ LIỀN NHAU** trong danh sách đã sắp. Khi
    video hiện HAI dòng phụ đề cùng lúc (chữ Hán ở một dải, một dòng khác ở dải khác) thì
    hai dòng ĐAN XEN nhau trong danh sách, chuỗi bị đứt, và mỗi lần đổi chữ sinh một
    `Segment` mới dài đúng `1/fps`.

    ĐO ĐƯỢC trên transcript #13 (nguồn 2, `vung_doc=[0,0.1,1,1]`, 77 dòng):

        so cap CUNG CHU LIEN NHAU trong danh sach:  0
        so cap cung chu bi dong khac chen giua:     15, khoang cach DEU = 0,0 s

        '福州烟台山商业漫步街区' x6  moc=[(189.5,190.5),(190.5,191.0),(191.0,191.5),
                                          (191.5,192.0),(192.0,192.5),(192.5,193.0)]
        '你在十一黄金周'        x3  moc=[(190.0,190.5),(190.5,191.0),(191.0,191.5)]

    Dòng đầu hiện **3,5 giây** thật (189,5 → 193,0) nhưng bị chẻ thành 6 dòng `0,5 s`. Mảnh
    đầu dài `1,0 s` vì trong cửa sổ đó có hai hộp.

    ## Luật nối — và vì sao phải có CẢ HAI điều kiện

    Hai hộp được coi là cùng một lần hiện khi CẢ BA:

    1. **cùng `text`**;
    2. **cùng DẢI `y`** — tâm dọc của hai hộp lệch nhau dưới `DAY_DAI_TOI_DA / 2` chiều
       cao khung. Hai dòng phụ đề thật hiện đồng thời nằm ở hai dải khác nhau;
    3. **cách nhau dưới `_NHIP_KHUNG * 2`** — đo được: cả 15/15 cặp cần nối ở #13 đều cách
       đúng `0,0 s`, nhưng phải nới vì hộp khác chữ chen vào giữa làm mất một nhịp.

    ⚠️ ĐIỀU KIỆN `y` KHÔNG PHẢI PHÒNG XA — dữ liệu thật bắt buộc phải có. Đo trên
    transcript #13, vùng 191–195 s:

        191.00 -> 191.50  '福州烟台山商业漫步街区'
        191.00 -> 191.50  '你在十一黄金周'
        191.50 -> 192.00  '来到福州烟台山'
        193.00 -> 193.50  '福州烟台山'      <- CÙNG chữ, KHÁC dải y
        194.00 -> 194.50  '福州烟台山'
        194.50 -> 195.00  '福州烟台山'

    `福州烟台山` xuất hiện ba lần ở ba khung liền nhau nhưng là BA DÒNG THẬT khác nhau (mỗi
    khung có 3 dòng phụ đề đồng thời, và dòng này đổi vị trí giữa các khung). Không có `y`
    thì chúng bị nối thành một dòng dài 2,0 s — sai.

    ⚠️ KHÔNG nối theo chữ đơn thuần: đo trên transcript #12 (cùng nguồn, không lọc vùng),
    **8 cặp cùng chữ nhưng cách nhau 26–134 s** — watermark `想想工作室…` hiện lại ở những
    đoạn khác nhau, không phải cùng một lần hiện. Điều kiện 3 chặn chúng.

    ## Trả gì

    Danh sách hộp ĐÃ GỘP: mỗi lần hiện còn ĐÚNG MỘT hộp, mang `t` của hộp ĐẦU (để
    `gop_thanh_dong` tính `start` đúng chỗ phụ đề bắt đầu hiện) và `diem` CAO NHẤT trong
    các mảnh (mảnh đọc được rõ nhất đại diện cho cả lần hiện). `x`/`y` lấy của mảnh đầu.

    Giữ nguyên thứ tự `t` tăng dần của danh sách vào.
    """
    if not hops:
        return []
    #: Nửa bề dày dải phụ đề, tính bằng TỈ LỆ chiều cao khung — nhưng `Hop` ở đây dùng
    #: PIXEL, và hàm này không biết chiều cao khung. Nên so theo tỉ lệ giữa `y` với chính
    #: bề dày hộp: hai hộp cùng một dòng thì tâm dọc gần như trùng, khác dòng thì lệch ít
    #: nhất một bề dày. Dùng `DAY_DAI_TOI_DA` làm hệ số nhân bề dày hộp trung bình.
    ra: list[Hop] = []
    # `t_cuoi[k]` = `t` của hộp CUỐI CÙNG đã gộp vào chuỗi `k`. Phải nhớ riêng: `ra[k].t`
    # là `t` của hộp ĐẦU (dùng để tính `start`), và so ngưỡng nối với hộp ĐẦU là SAI.
    t_cuoi: list[float] = []
    # 🔴 `goc` PHAI DUOC CHEP O CA HAI NHANH DUOI DAY.
    #
    # Ham nay chay TRUOC `gop_thanh_dong` trong `doc_phu_de`, va no tao `Hop` MOI. Ban dau
    # toi chi sua `gop_thanh_dong` — do duoc ket qua (job asr #154, transcript #47): van
    # `0/158` doan mang truong `goc`, 6 khoi poster van o lop 1. Vi goc da bi xoa TU DAY.
    #
    # Nhanh 1 (khong noi vao chuoi nao): chep `goc` cua chinh hop do.
    # Nhanh 2 (noi vao chuoi co san): giu `goc` cua hop DAU chuoi.
    for h in hops:
        noi_vao: int | None = None
        for k in range(len(ra) - 1, -1, -1):
            ung = ra[k]
            if ung.text != h.text:
                continue
            # Cùng dải y? So TÂM dọc, với dung sai bằng bề dày hộp (một dòng phụ đề có
            # thể cao thấp hơn nhau vài pixel giữa các khung do khử răng cưa).
            tam_ung = (ung.y0 + ung.y1) / 2
            tam_h = (h.y0 + h.y1) / 2
            be_day = max(1.0, (ung.y1 - ung.y0 + h.y1 - h.y0) / 2)
            if abs(tam_h - tam_ung) > be_day:
                continue
            if h.t - t_cuoi[k] <= _NHIP_KHUNG * 2:
                noi_vao = k
            # 🔴 `break` PHAI NẰM TRONG `if`: bản trước để nó ngoài, nên vòng lặp chỉ xét
            # ĐÚNG phần tử cuối của `ra` rồi thoát. Đo được hậu quả: 5 hộp `A,B,A,B,A`
            # vào, chỉ 2 hộp ra — `A@190.5` và `A@191.5` BIẾN MẤT khỏi kết quả, tức mất
            # dòng phụ đề, chứ không phải nối sai. Đó là lý do phải có bài test đếm số hộp.
            break
        if noi_vao is None:
            ra.append(Hop(text=h.text, x0=h.x0, y0=h.y0, x1=h.x1, y1=h.y1,
                          t=h.t, diem=h.diem, goc=h.goc))
            t_cuoi.append(h.t)
        else:
            ung = ra[noi_vao]
            ra[noi_vao] = Hop(text=ung.text, x0=ung.x0, y0=ung.y0, x1=ung.x1, y1=ung.y1,
                              t=ung.t, diem=max(ung.diem, h.diem), goc=ung.goc)
            t_cuoi[noi_vao] = h.t
    return ra


#: Một nhịp khung ở `fps = 2` — ngưỡng nối mảnh trong `noi_manh_cung_dong`.
#:
#: ⚠️ ĐÂY LÀ HẰNG SỐ CỦA `fps = 2`, không phải hằng số của thuật toán. `doc_phu_de` nhận
#: `fps` làm tham số, nên nếu ai đó gọi với `fps = 1` thì ngưỡng này thành hai nhịp khung và
#: có thể nối nhầm hai lần hiện khác nhau. `noi_manh_cung_dong` không nhận `fps` vì nó chạy
#: trên `Hop` đã có `t` tuyệt đối; truyền `fps` vào đây sẽ là tham số thứ hai cùng nói một
#: điều. Nếu đổi `fps` mặc định thì phải đổi cả hằng số này — ghim bằng
#: `test_nguong_noi_manh_khop_fps_mac_dinh`.
_NHIP_KHUNG = 0.5


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
        # 🔴 `goc=truoc.goc` — KHONG duoc bo. `Hop` co goc nhung `Segment` tao moi o day,
        # nen thieu dong nay thi goc bi vut DUNG tai day va `nguon_chu` khong con gi de
        # loc. Do duoc: job asr 150 chay tren ma da co `goc_hop` nhung transcript #45 van
        # co 0/158 doan mang truong `goc`, va 6 khoi poster van nam trong lop 1.
        ra.append(Segment(i=len(ra), start=dau, end=truoc.t + buoc, text=truoc.text,
                          goc=truoc.goc))
        dau, truoc = h.t, h
    ra.append(Segment(i=len(ra), start=dau, end=truoc.t + buoc, text=truoc.text,
                      goc=truoc.goc))
    return ra


# ---------------------------------------------------------------------------
# KÉO `end` CỦA DÒNG OCR THEO MỐC LỜI NÓI ASR
# ---------------------------------------------------------------------------

#: Tỉ lệ ký tự OCR tối thiểu phải khớp với từ ASR để coi là "cùng một câu".
#:
#: ĐO ĐƯỢC trên nguồn 2: 538 ký tự OCR, 359 ký tự có mặt trong ASR cùng cửa sổ = **66,7 %**.
#: Nhưng phân bố KHÔNG đều — các cặp đúng khớp 6/8 tới 8/9, còn cặp sai (OCR `胖2026见` trong
#: khi ASR nghe `这样一个雷霆大海豹`) khớp gần 0. Đặt 0,5 nằm giữa hai cụm đó.
KHOP_TOI_THIEU = 0.5


def _chu(s: str) -> set[str]:
    """Tập ký tự của `s`, bỏ khoảng trắng và dấu câu — để so OCR với ASR.

    OCR và ASR khác nhau ở dấu câu và khoảng trắng (`作为一个搞艺术的` vs
    `作为一个搞艺术`), nên so nguyên chuỗi sẽ trượt. So tập KÝ TỰ chịu được cả thiếu chữ
    lẫn thừa dấu.
    """
    return {c for c in s if not c.isspace() and c.isalnum()}


def _tu_trong_khoang(tu: list[Word], dau: float, cuoi: float,
                     dung_sai: float = 0.0) -> list[Word]:
    """Các từ có TÂM nằm trong `[dau - dung_sai, cuoi + dung_sai]`."""
    ra: list[Word] = []
    for w in tu:
        tam = (w.s + w.e) / 2
        if dau - dung_sai <= tam <= cuoi + dung_sai:
            ra.append(w)
    return ra


def xep_hang_trong_lop(doan: list[Segment]) -> list[Segment]:
    """XẾP HÀNG hiển thị trong TỪNG LỚP: đoạn sau ĐỢI đoạn trước hiện xong.

    🔴 VÌ SAO (chủ dự án: *"khi burn phụ đề có mấy cái bị đè nhau … tôi muốn nó đợi cái được
    burn trước hết xong mới đến lượt cái sau"*, kèm giới hạn phạm vi: *"vẫn đang xét trong
    layer 1 / làn 1 thôi"*).

    Hai đoạn cùng một làn mà chồng thời gian thì trên video có hai dòng chữ đè nhau, người
    xem không đọc được dòng nào. Cách rẻ nhất và đúng ý: dời `start` của đoạn sau lên ĐÚNG
    `end` của đoạn trước.

    Ba điều phải đúng:

    * **Chỉ so trong CÙNG một lớp.** Lớp 1 và lớp 2 là hai làn HIỂN THỊ; chồng nhau ở đó là
      bình thường (timeline giữ cả hai để người đọc soát). Gộp hai lớp vào một hàng sẽ đẩy
      lùi cả dòng của lớp kia — sai hẳn dữ liệu.
    * **Không để `start >= end`.** Dời tới mức đoạn không còn thời gian hiện là biến nó thành
      vô hình, mà nguyên tắc đã chốt là *"không cắt chữ"* — thà giữ `end` cũ (nên nó dài ra)
      còn hơn nuốt mất một dòng. Vì vậy mốc để dời luôn là `end` của đoạn trước, và nếu ra
      `start >= end` thì giữ nguyên độ dài CŨ.
    * **Đoạn không có `layer`** (dữ liệu cũ) là một lớp riêng (`""`), không gộp bừa vào lớp 1.

    Trả DANH SÁCH MỚI, không sửa tại chỗ: các bước trước (`keo_dai_theo_asr`, `gop_thanh_dong`)
    vẫn phải thấy mốc CHƯA dời, và `Segment` là dữ liệu gốc của bản dịch.
    """
    if not doan:
        return []

    #: Mốc `end` XA NHẤT đã dùng cho từng lớp — dùng `max` chứ không phải "end của đoạn vừa
    #: xét": một đoạn dài có thể vượt qua nhiều đoạn ngắn phía sau.
    moc: dict[str, float] = {}
    ra: list[Segment] = []
    for s in sorted(doan, key=lambda x: (x.start, x.i)):
        lop = s.layer or ""
        truoc = moc.get(lop)
        start, end = s.start, s.end
        if truoc is not None and start < truoc:
            start = truoc
        if end <= start:
            end = start + max(end - s.start, 0.04)
        moc[lop] = end if truoc is None else max(truoc, end)
        ra.append(Segment(
            i=s.i, start=start, end=end, text=s.text, words=s.words,
            emotion=s.emotion, events=list(s.events), speaker=s.speaker,
            avg_logprob=s.avg_logprob, no_speech_prob=s.no_speech_prob,
            suspect=s.suspect, t=s.t, qa=list(s.qa), layer=s.layer,
        ))
    return ra


def keo_dai_theo_asr(doan: list[Segment], tu_asr: list[Word],
                     dung_sai: float = 0.5) -> list[Segment]:
    """Kéo `end` của mỗi dòng OCR tới hết LỜI NÓI của câu đó.

    ## Vì sao cần (lỗi thật, chủ dự án báo)

    *"các đoạn dùng ocr bị khá là ngắn mặc dù phụ đề trên vid đoạn phụ đề đấy chưa kết
    thúc. Được thì dùng timestamp của asr cx đc"*

    OCR chỉ biết "dòng này hiện ở KHUNG nào". `gop_thanh_dong` đặt
    `end = t_hộp_cuối + 1/fps`, nên **mọi** dòng OCR dài đúng `0,50 s` ở `fps = 2` — đo
    được: 76/77 dòng của transcript #13 dài `0,50`, một dòng `1,00`. Một phụ đề hiện 1,3 s
    vẫn thành dòng `0,50 s` nếu OCR chỉ đọc được một khung.

    ASR có mốc **word-level** và phủ đúng chỗ đó. Đo được trên nguồn 2:

        OCR 193.00..193.50  '你会在山上看到'
        ASR  你[192.53-193.13] 会[193.13-193.25] 在[193.25-193.35]
             山[193.35-193.51] 上[193.51-193.63] 看到[193.63-193.81]

    Chữ OCR khớp các từ ASR trải tới `193,81` — dài **1,28 s**, không phải `0,50 s`.

    ## Luật

    Với mỗi đoạn OCR:

    1. Lấy các từ ASR có tâm nằm trong `[start - dung_sai, end + dung_sai]`.
    2. Tính tỉ lệ ký tự OCR có mặt trong các từ đó. Dưới `KHOP_TOI_THIEU` ⇒ **KHÔNG kéo**:
       ASR đang nói chuyện khác, và kéo theo nó là gán mốc của câu khác.
    3. Khớp đủ ⇒ kéo `end` tới `e` của từ ASR **cuối cùng LIÊN TỤC khớp**. Dừng ở từ đầu
       tiên không đóng góp ký tự mới nào: đo được ASR hay NGHE THÊM chữ không có trong OCR
       (`会显得不太聪明` vs `价值会显得不太聪明比如` — ASR thừa `比如` ở cuối), và lấy từ
       cuối của cả cửa sổ sẽ kéo `end` sang câu sau.

    ## Không bao giờ vượt dòng kế tiếp

    Ràng buộc CỨNG của dự án: hai dòng không được chồng nhau. Nên `end` bị chặn trên bởi
    `start` của dòng OCR kế tiếp (khi có). Không có dòng kế thì không chặn.

    `end` không bao giờ bị RÚT NGẮN: nếu ASR kết thúc sớm hơn `end` hiện tại (OCR đọc được
    khung cuối muộn hơn lời nói), giữ `end` cũ.
    """
    if not doan:
        return []
    ra: list[Segment] = []

    #: `end` LON NHAT da dung, TINH RIENG CHO TUNG LAYER.
    #:
    #: 🔴 PHAI LA DICT, va phai cap nhat bang `end` SAU KHI NOI. DO DUOC tren
    #: transcript #53 (chay lai toan bo 156 doan):
    #:
    #:     i=64  layer 1  [101.55-102.50]
    #:     i=65  layer 2  [101.55-103.17]   <- chen giua
    #:     i=66  layer 1  [102.07-103.17]   <- start lui ve 102,07, CHONG 0,43
    #:
    #: Hai loi lam nen ca nay:
    #:
    #: 1. Mot bien duy nhat bi RESET khi doi layer. `i=65` la layer 2 nen moc cua
    #:    layer 1 bi xoa, va `i=66` khong con gi de chan. Moc cua layer 1 phai song sot
    #:    qua cac dong layer 2 chen giua — nen phai la dict, khong phai mot so.
    #: 2. Cap nhat bang `s.end` GOC thay vi `end` SAU KHI NOI. Dong truoc vua bi keo
    #:    dai thi moc phai la `end` MOI, neu khong `start` cua dong sau lui vao trong no.
    #:
    #: Cung loi o `i=67`/`i=69` (0,40) va `i=93`/`i=95` (0,33).
    moc_theo_layer: dict[str, float] = {}
    for k, s in enumerate(doan):
        tu = _tu_trong_khoang(tu_asr, s.start, s.end, dung_sai)
        if not tu:
            ra.append(s)
            truoc = moc_theo_layer.get(s.layer)
            moc_theo_layer[s.layer] = s.end if truoc is None else max(truoc, s.end)
            continue
        ocr_chu = _chu(s.text)
        if not ocr_chu:
            ra.append(s)
            truoc = moc_theo_layer.get(s.layer)
            moc_theo_layer[s.layer] = s.end if truoc is None else max(truoc, s.end)
            continue
        asr_chu: set[str] = set()
        for w in tu:
            asr_chu |= _chu(w.w)
        if len(ocr_chu & asr_chu) / len(ocr_chu) < KHOP_TOI_THIEU:
            ra.append(s)
            truoc = moc_theo_layer.get(s.layer)
            moc_theo_layer[s.layer] = s.end if truoc is None else max(truoc, s.end)
            continue

        # KEO CA `start` LUI, khong chi `end` toi.
        #
        # Day la phan con THIEU, va no dung la thu chu du an thay: vach chay da cham
        # roi nhung current van chua toi cai phu de.
        #
        # DO DUOC tren translation #52 (158 doan): `start` cua CA 62/62 dong OCR la boi
        # so cua 0,5 s, vi OCR chay 2 fps va chi biet dong nay hien o KHUNG nao. ASR can
        # theo mau am thanh nen co moc that. So 18 cap cung cau:
        #
        #     OCR bat dau SAU ASR : 17 / 18 cap
        #     OCR bat dau TRUOC   :  0 / 18 cap
        #     lech trung binh     : +0,28 s
        #     lech lon nhat       : +0,95 s
        #
        # Vi du nguoi dung chup anh: vach o 1:15.00, khoi `Cho n...` chua to vang.
        #     ASR i=48  bat dau 75,31
        #     OCR i=49  bat dau 75,50   <- tre 0,19 s
        #
        # Do lai sau khi sua (cung du lieu): ho giam 112,25 s -> 99,77 s, va so cap CHONG
        # NHAU sau khi noi la 0.
        #
        # Rang buoc: `start` khong duoc lui qua `end` cua dong TRUOC (hai dong khong duoc
        # chong nhau — rang buoc CUNG cua du an), va khong lui qua tu ASR dau tien.
        start_moi = s.start
        for tu_dau in sorted(tu, key=lambda x: x.s):
            if not (_chu(tu_dau.w) & ocr_chu):
                continue
            start_moi = min(start_moi, tu_dau.s)
            break
        # Chi chan khi dong TRUOC ket thuc truoc dong nay — hai dong SONG SONG (cung
        # `start`, khac dai `y`) khong tranh nhau cho, y het ly do o phan chan `end`.
        #
        # 🔴 KHONG dat ten bien vong lap la `k`: no GHI DE chi so doan `k` cua vong
        # ngoai, va dong chan `end` o duoi (`doan[k + 1]`) doc phai gia tri rac. Do
        # duoc ngay khi vua viet: `for w in ...` roi `if k + 1 < len(doan)` — `k` luc do
        # la mot `Word`, khong phai so.
        # 🔴 CHAN THEO DONG TRUOC DA XU LY, KHONG theo `doan[k - 1]`.
        #
        # Ban dau toi chan bang `doan[k - 1].end` va DO DUOC mot cap chong con lai
        # (transcript #51):
        #
        #     i=49  [76.79-77.95]  '经常通过拉踩的方式'
        #     i=51  [77.73-78.97]  '来体现作品的价值'   CHONG 0,22 s
        #
        # `i=50` chen giua hai dong nay trong danh sach, nen `doan[k - 1]` la `i=50` chu
        # khong phai `i=49` — chan sai doi tuong. Phai chan bang dong TRUOC DA XU LY,
        # tuc phan tu cuoi cua `ra`.
        #
        # Chi chan khi dong truoc ket thuc truoc dong nay — hai dong SONG SONG (cung
        # `start`, khac dai `y`) khong tranh nhau cho, y het ly do o phan chan `end`.
        # 🔴 CHAN BANG `end` LON NHAT cua cac dong DA XU LY, khong phai `ra[-1]`.
        #
        # Ban dung `ra[-1]` va DO DUOC (bai test do voi 'do duoc 77.6'):
        #
        #     i=0  [76.79-77.95]  '经常通过拉踩的方式'
        #     i=1  [76.79-77.20]  'dong song song khac dai y'   <- ket thuc SOM hon i=0
        #     i=2  [78.00-78.97]  '来体现作品的价值'
        #
        # `ra[-1]` la `i=1` (ket thuc 77,20), nen chan thanh 77,20 va `start` lui ve 77,60 —
        # CHONG len `i=0` (ket thuc 77,95). Dong song song trong danh sach KHONG co nghia
        # la dong co `end` nho nhat; phai chan bang moc MUON NHAT da dung.
        #
        # Chi chan khi moc do ket thuc truoc dong nay — hai dong SONG SONG (cung `start`,
        # khac dai `y`) khong tranh nhau cho, y het ly do o phan chan `end`.
        moc = moc_theo_layer.get(s.layer)
        if moc is not None and moc <= s.start:
            start_moi = max(start_moi, moc)
        start_moi = min(start_moi, s.start)

        # Đi từng từ theo thời gian, dừng ở từ đầu tiên KHÔNG đóng góp ký tự mới nào mà
        # OCR cần. `da_co` tích luỹ để `比如` ở cuối (ký tự đã có) không kéo dài thêm.
        da_co: set[str] = set()
        end_moi = s.end
        for w in sorted(tu, key=lambda x: x.s):
            moi = _chu(w.w) & ocr_chu
            if not moi - da_co:
                # 🔴 BỎ QUA, KHÔNG DỪNG. ĐO ĐƯỢC (bài test đỏ vì lỗi này): OCR
                # `会显得不太聪明`, ASR `价值会显得不太聪明比如`. Bản đầu `break` ngay ở
                # `价值` — từ ĐẦU TIÊN — vì nó không đóng góp ký tự nào OCR cần, nên
                # KHÔNG kéo được gì và `end` đứng ở 49,0 thay vì 49,47.
                #
                # Từ thừa ở GIỮA cũng không được kéo `end` (nó không đóng góp gì), nhưng
                # cũng không được dừng vòng lặp: từ sau nó có thể đóng góp. Chỉ dừng khi đã
                # phủ hết ký tự OCR cần — điều kiện `da_co >= ocr_chu` ở dưới.
                continue
            da_co |= moi
            end_moi = max(end_moi, w.e)
            if da_co >= ocr_chu:
                break

        # Chặn trên: chỉ chặn khi dòng kế tiếp là DÒNG NỐI TIẾP (bắt đầu SAU dòng này).
        #
        # 🔴 ĐO ĐƯỢC: bản đầu chặn vô điều kiện bằng `min(end, doan[k+1].start)` và nó
        # CẮT SAI 14 cặp. Vùng 191-195 s của #13 có BA dòng phụ đề hiện ĐỒNG THỜI (cùng
        # `start`, khác dải `y`); dòng kế tiếp trong danh sách bắt đầu ĐÚNG LÚC dòng này
        # bắt đầu, nên `min` kéo `end` về bằng `start` — dòng dài 0 giây. Đó là hai
        # dòng SONG SONG, không phải nối tiếp, và chúng không tranh nhau chỗ nói.
        # 🔴 CHAN BANG DONG SAU **CUNG LAYER**, khong phai `doan[k + 1]`.
        #
        # Ban dung `doan[k + 1]` va DO DUOC 9 cap chong tren transcript #53 khi chay lai
        # toan bo 156 doan:
        #
        #     i=0   [0.00-1.14]      >< i=2   [1.04-2.42]      chong 0,10
        #     i=55  [94.23-96.03]    >< i=57  [96.00-96.93]    chong 0,03
        #     i=64  [101.55-102.75]  >< i=66  [102.07-103.17]  chong 0,68
        #
        # Voi `i=55`, `doan[k + 1]` la `i=56` (layer 2) bat dau 94,23 — KHONG lon hon
        # 94,23 nen khong chan gi. Nhung `i=57` (layer 1) bat dau 96,00 moi la dong noi
        # tiep that. Phai tim `start` NHO NHAT cua moi dong SAU, CUNG LAYER.
        #
        # Giu nguyen y do cu: chi chan khi dong do bat dau SAU dong nay — hai dong SONG
        # SONG (cung `start`, khac dai `y`) khong tranh nhau cho noi.
        sau_cung_layer = [
            x.start for x in doan[k + 1:] if x.layer == s.layer and x.start > s.start
        ]
        if sau_cung_layer:
            end_moi = min(end_moi, min(sau_cung_layer))
        # 🔴 CHEP `goc` — cho dut THU NAM cua cung mot loi.
        #
        # DO DUOC: `doc_phu_de` tra ve 6 khoi deu co goc (`你会在山上看到` goc=-12.40),
        # nhung transcript #49 chi con 4 khoi mang goc. Hai khoi mat goc la hai khoi bi
        # ham nay KEO DAI (`end` 193.50 -> 193.81 va 194.50 -> 194.75) — vi ham nay tao
        # `Segment` MOI ma ban dau khong chep `goc`.
        #
        # Chep ca `layer` va `chua_trong` cho day du: day la tao lai CUNG mot doan, chi
        # khac `end`, nen moi truong khac phai giu nguyen.
        end_that = max(s.end, end_moi)
        ra.append(Segment(i=s.i, start=start_moi, end=end_that, text=s.text,
                          suspect=s.suspect, layer=s.layer, goc=s.goc,
                          chua_trong=s.chua_trong))
        truoc = moc_theo_layer.get(s.layer)
        moc_theo_layer[s.layer] = end_that if truoc is None else max(truoc, end_that)
    return ra