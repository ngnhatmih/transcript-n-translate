"""Chọn nguồn chữ cho pipeline lồng tiếng: OCR là CHÍNH, ASR là dự phòng.

## Vì sao là domain policy, không phải một bước trong pipeline

"Chọn nguồn nào" là một QUYẾT ĐỊNH về chất lượng, không phải một phép biến đổi dữ liệu. Tách
ra đây thì test được mà không cần model, và nó là chỗ duy nhất phải sửa khi đổi chính sách.

## Vì sao OCR là chính

ĐO ĐƯỢC trên video 1249,237 s, đoạn 120–420 s, OCR làm gốc (76 cửa sổ 4 s, 163 dòng):
  · ASR trên audio GỐC:   chính xác ký tự 66,27 %, bỏ sót 0 cửa sổ
  · ASR trên vocals tách: 60,48 % (roformer-1296), 56,29 % (htdemucs)
OCR đọc chữ ĐÃ BIÊN TẬP (người làm phụ đề gõ), nên nó đúng chính tả và đúng từ; ASR nghe và
hay sai tên riêng. Ngoài ra ASR DỪNG ở 1186,4 s — thiếu 62,8 s cuối video, còn OCR phủ tới
1243 s.

## Vì sao vẫn cần ASR

Video không có phụ đề cứng thì OCR trả danh sách rỗng một cách HỢP LỆ. Đó không phải lỗi, và
rơi về ASR là hành vi đúng. Ngoài ra ASR cấp mốc thời gian chính xác hơn (word-level ~0,1 s
so với OCR 2 fps ±0,5 s).
"""
from __future__ import annotations
from difflib import SequenceMatcher

from app.domain.models import Segment

#: Hai đoạn ASR cách nhau ít hơn ngưỡng này là MỘT khoảng có tiếng (nhiễu cắt dòng).
#: Đo được: bản ASR gốc 451 đoạn trên 1249 s có nhiều cặp sát nhau cỡ 0,1–0,3 s.
NGUONG_GOP = 0.5

#: DUNG SAI khi so mốc OCR với mốc ASR, tính bằng giây.
#:
#: 🔴 ĐO ĐƯỢC, và đây là con số quyết định toàn bộ phép hợp nhất: MỌI dòng OCR đều dài
#: đúng `0,50 s` — vì `gop_thanh_dong` (`domain/phu_de.py:276-291`) đặt
#: `end = t_hộp_cuối + 1/fps` với `fps = 2`. Nguyên văn 77 dòng của transcript #13:
#:
#:     i=0   0.00 -> 0.50   i=1   1.50 -> 2.00   i=4  29.50 -> 30.00
#:
#: Nghĩa là OCR chỉ biết "dòng này hiện ở KHUNG nào", sai số tới ±0,5 s ở MỖI đầu. Còn ASR
#: có mốc ~0,1 s. So khít hai bên là so hai thứ đo bằng hai đơn vị khác nhau: một dòng OCR
#: `0.50-1.00` và một đoạn ASR `0.55-1.80` nói về CÙNG một câu, nhưng `overlap` khít sẽ
#: trượt nếu mép lệch quá 0,5 s.
#:
#: Chọn 0,5 = đúng một nhịp khung, không phải số tuỳ ý: đó là độ phân giải THẬT của OCR.
#: Nới hơn nữa thì một dòng OCR bắt đầu "đè" lên câu nói trước nó (hai phụ đề liền nhau cách
#: 0,6 s là chuyện bình thường trong video này — xem `i=4/i=5` của transcript #13: hai dòng
#: cách nhau 0,0 s, còn `i=2/i=3` cách 0,5 s).
DUNG_SAI_OCR = 0.5

#: Giao THO toi thieu de coi mot dong OCR la UNG voi mot doan ASR (tuc cung mot cau).
#:
#: DO DUOC tren transcript #38, hai dong trong cung mot `ung_vien`:
#:
#:     OCR [48.50-49.47]  giaoTho=0.970  <- CUNG CAU, phai la lop 2
#:     OCR [50.00-51.09]  giaoTho=0.050  <- chi cham mep, phai la lop 1
#:
#: `0.30` nam giua hai gia tri do va cach moi ben rat xa, nen khong phai chon so la.
#: Nho hon `DUNG_SAI_OCR` (0.5) vi day la phep so NOI DUNG, khong phai phep no sai so.
NGUONG_UNG = 0.30

#: LOP 1 — BAN CHINH. Bat lop nay thi chi hien cac doan cua lop 1.
#:
#: Layer la mot LOP HIEN THI kieu Photoshop, KHONG phai phep dem so nguon.
#: Ten cu `mot_nguon`/`hai_nguon` la di san: chuoi trong DB van giu nguyen de
#: khong phai migrate, nhung nghia cua no la LOP, khong phai "may nguon doc ra".
#:
#: Doan vao lop 1 khi no la ban CHAT NHAT cho cau do:
#:   · OCR doc duoc phu de ma ASR khong nghe ra  -> doan OCR thuan;
#:   · ASR nghe duoc loi noi ma OCR khong doc ra -> doan ASR thuan, `suspect=True`.
#:
#: Nguoi dung dat ten: "Layer 1 la chat nhat va duoc uu tien lay: ocr + asr doan ko co ocr".
LOP_1 = "mot_nguon"

#: Ten cu, giu lai cho cho nao con doc. Dung `LOP_1` trong ma moi.
LOP_MOT_NGUON = LOP_1

#: LOP 2 — BAN PHU. Bat lop nay thi chi hien cac doan cua lop 2.
#:
#: Doan vao lop 2 khi OCR va ASR cung doc/nghe ra mot cau — chu da duoc kiem cheo,
#: nhung khong mang them thong tin ma lop 1 chua co, nen lop 2 xep SAU.
#:
#: Nguoi dung dat ten: "layer 2 la co ocr nhung co ca asr".
LOP_2 = "hai_nguon"

#: Ten cu, giu lai cho cho nao con doc. Dung `LOP_2` trong ma moi.
LOP_HAI_NGUON = LOP_2



def _bao(trong_start: float, trong_end: float, ngoai_start: float, ngoai_end: float,
         dung_sai: float = 0.3) -> bool:
    """`(trong_start, trong_end)` co nam GON BEN TRONG `(ngoai_start, ngoai_end)` khong?

    ## Hai dieu kien, ca hai deu DO DUOC

    **1. Khong lot dau nao** — bat dau khong som hon, ket thuc khong muon hon.

    **2. Lot CA HAI DAU** it nhat `dung_sai`. Day la dieu kien phan biet quan trong, va ban dau
    toi thieu no nen ba bai test cu DO. Do 5 cap that:

        ca                              lotDau  lotCuoi  ket qua dung
        #32 "ΛNI"     trong ASR 219-221  0.83    0.61    GIU CA HAI
        #32 "作者：熊伟" trong ASR 235-237  0.81    0.39    GIU CA HAI
        fixture  OCR 10.0-10.5 trong 10.0-12.0   0.00    1.50    OCR THANG
        fixture  OCR 20.0-20.5 trong 20.0-23.0   0.00    2.50    OCR THANG
        #32 cap 7 OCR 229.0-230.0 trong 229-231  0.01    0.74    OCR THANG

    Nhom can giu lot dau 0,81-0,83; nhom OCR thang lot dau 0,00-0,01. Khong co ca nao o giua,
    nen `dung_sai = 0.5` (cung nguong voi `DUNG_SAI_OCR`) tach sach ma khong phai chon so la.

    Vi sao phai co dieu kien 2: `OCR 10.0-10.5` nam trong `ASR 10.0-12.0` theo dinh nghia hinh
    hoc, nhung do KHONG phai mot vat the khac tren man hinh — do la OCR doc nua dau cua CUNG
    mot cau ma ASR nghe tron. Chinh sach cu (OCR thang) dung cho ca do. Chi khi vat the do lot
    han vao trong — logo, dong ghi cong — thi moi la hai thu khac nhau va phai giu ca hai.
    """
    if (trong_end - trong_start) >= (ngoai_end - ngoai_start):
        return False
    lot_dau = trong_start - ngoai_start
    lot_cuoi = ngoai_end - trong_end
    return lot_dau >= dung_sai and lot_cuoi >= dung_sai


def _giao(a_start: float, a_end: float, b_start: float, b_end: float,
          dung_sai: float = 0.0) -> float:
    """Độ dài phần GIAO của hai khoảng, sau khi nới mỗi khoảng `dung_sai` về hai phía."""
    dau = max(a_start - dung_sai, b_start - dung_sai)
    cuoi = min(a_end + dung_sai, b_end + dung_sai)
    return max(0.0, cuoi - dau)


def _chuan_hoa(chu: str) -> str:
    """Chu thuan de so sanh: bo khoang trang, ha chu, doi dau nhay kieu Trung sang ASCII.

    DO DUOC vi sao phai doi dau nhay: OCR doc `“福` con ASR nghe `福` — cung mot tu, khac
    ky tu nhay, va phep so sanh tho se truot.
    """
    return "".join(chu.split()).lower().replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")


def _da_co_chu(chu: str, da_dung: list[str]) -> bool:
    """Chu cua `chu` da nam trong MOT trong cac dong `da_dung` chua?

    So theo KY TU, khong theo tu: OCR va ASR nghe khac nhau nen so tu se luon truot.
    (`最苦恼的事就是` / `最苦闹的事就是` — hai tu khac, bon tu giong.)

    Dung `in` hai chieu: OCR tach dong ngan hon ASR (`经常要证明` nam trong
    `要经常证明自己的作品是有价值的长`), va ASR cung co the ngan hon OCR. Ca hai chieu deu
    la cung mot cau, nen ca hai deu phai bi coi la ban sao.
    """
    a = _chuan_hoa(chu)
    if not a:
        return False
    for d in da_dung:
        b = _chuan_hoa(d)
        if not b:
            continue
        if a in b or b in a:
            return True
        # DO DUOC: `in` mot minh bo sot cap SAI MOT CHU — OCR doc `集` con ASR nghe
        # `街` trong cung mot cau (`在整个集区藏了很多个福` / `在整个街区藏了很多个“福`),
        # ti le ky tu chung 0,87. Nguong 0,85 bat duoc ca do ma khong cham cap KHAC cau:
        #
        #     cung cau:  0,90   0,91   0,87
        #     khac cau:  0,00   0,00   0,00   0,32
        #
        # Khoang trong 0,32 -> 0,87 rong, nen 0,85 la nguong an toan.
        if SequenceMatcher(None, a, b).ratio() >= 0.85:
            return True
    return False


def hop_nhat_theo_doan(doan_ocr: list[Segment], doan_asr: list[Segment]
                       ) -> tuple[list[Segment], int, int]:
    """Hợp nhất OCR và ASR THEO TỪNG ĐOẠN. Trả `(đoạn, số đè, số nghi ngờ)`.

    ## Luật, đúng như chủ dự án đặt ra

    ASR nghe trước để biết ĐOẠN NÀO CÓ LỜI; OCR đọc chữ đã biên tập. Với mỗi đoạn ASR:

    * **Có ≥1 dòng OCR đè lên** ⇒ DÙNG OCR, bỏ chữ ASR. Nếu một đoạn ASR chứa HAI dòng OCR
      thì giữ CẢ HAI dòng OCR và bỏ đoạn ASR — chữ đã biên tập luôn đúng hơn chữ nghe được.
    * **Không có dòng OCR nào đè lên** ⇒ giữ đoạn ASR nhưng đánh `suspect = True`. Khi OCR
      ĐANG BẬT, một đoạn có tiếng nói mà không đọc được phụ đề cứng là dấu hiệu đáng ngờ
      (OCR sót khung, phụ đề nằm ngoài `vung_doc`, hoặc ASR nghe nhầm chỗ không có tiếng).

    Vì sao vẫn GIỮ đoạn ASR nghi ngờ thay vì xoá: xoá là mất lời nói thật khỏi bản lồng, và
    người dùng không có cách nào biết đã mất gì. `suspect` hiện thành việc "nghi ngờ phiên
    âm" trong cột việc (`viecCuaDong`) để người dùng TỰ xem — đó là lý do cờ này tồn tại.

    ## Thứ tự đầu ra

    Sắp theo `start` của đoạn được giữ, KHÔNG theo thứ tự hai danh sách đầu vào: dòng OCR
    đứng đúng chỗ lời nói của nó, và một đoạn ASR nghi ngờ chen giữa hai dòng OCR vẫn nằm
    đúng chỗ. `i` đánh lại từ 0 theo thứ tự đó — `Segment.i` là SỐ THỨ TỰ, không phải danh
    tính, và để lỗ hổng ở đây sẽ làm `PATCH /segments/{i}` trỏ sai dòng.

    ## Vì sao không "gộp" chữ của hai nguồn trong một đoạn

    Không có cách nào trộn chữ của hai nguồn mà không bịa ra câu chưa ai nói: OCR đọc
    `最苦恼的事就是`, ASR nghe `最苦闹的事就是` — cái đúng là OCR, nhưng nếu OCR chỉ đọc được
    NỬA dòng (khung cuối bị cắt) thì nửa còn lại của ASR là manh mối, không phải chữ dùng
    được. Chọn MỘT nguồn cho mỗi đoạn là quyết định đọc được và giải thích được.
    """
    if not doan_asr:
        # Không có ASR ⇒ không có gì để đối chiếu. Trả nguyên OCR (nếu có) và để
        # `chon_nguon` quyết định; ở đây không đánh `suspect` vì KHÔNG có bằng chứng nào
        # nói dòng đó sai — OCR đọc được chữ là bằng chứng nó tồn tại.
        return list(doan_ocr), 0, 0

    # Mỗi dòng OCR chỉ được dùng MỘT lần: nếu hai đoạn ASR cùng đè lên một dòng OCR thì
    # dòng đó thuộc về đoạn ASR có giao LỚN NHẤT, không phải cả hai (chép đôi là lỗi thật
    # — bản lồng sẽ nói cùng một câu hai lần).
    da_dung: set[int] = set()
    ra: list[Segment] = []
    so_de = 0
    so_nghi = 0

    for doan in doan_asr:
        # 🔴 DO DUOC: loc bang GIAO DA NOI (`DUNG_SAI_OCR = 0.5`) la mot loi THAT.
        # No khien mot dong OCR cach doan ASR gan NUA GIAAY van bi coi la "ung vien",
        # chiem mat no, roi doan ASR that moi khong con gi de khop:
        #
        #     ASR [218.50-219.60]  <- doan truoc
        #     OCR [220.00-220.50]  giaoTho=0.000 nhung giaoNoi=0.10 -> bi chiem
        #     ASR [219.17-221.11]  <- doan that, gio `ung_vien` RONG
        #
        # Ket qua do duoc: `ΛNI` mat `chua_trong` dung va bi gan `hai_nguon` (sai — no chi
        # co MOT nguon doc ra). Voi `giaoTho` thi dong do khong duoc chon, va `ΛNI`
        # thuoc ve dung doan ASR cua no.
        #
        # `DUNG_SAI_OCR` van dung cho `_giao` khi CAN do rong tay: do la sai so lam tron
        # cua OCR, khong phai loi moi de gop hai vat the khac nhau.
        ung_vien = [
            (j, ocr) for j, ocr in enumerate(doan_ocr)
            if j not in da_dung
            and _giao(doan.start, doan.end, ocr.start, ocr.end, 0.0) > 0.0
        ]
        if not ung_vien:
            # KHONG khop dong OCR nao. Nhung truoc khi giu, phai kiem: chu cua doan
            # ASR nay da nam trong mot dong OCR DA DUNG chua?
            #
            # 🔴 DO DUOC tren transcript #30 (nguon 6, 131 doan): **19/130 cap chong thoi
            # gian**, va gan nhu toan bo la CUNG MOT CAU hien hai lan — mot ban
            # `suspect=True` (ASR) va mot ban `suspect=False` (OCR):
            #
            #     i=1 [1.14-2.42] S "最苦恼的事就是"
            #     i=2 [1.50-2.42]   "最苦恼的事就是"     <- cung chu, chong len nhau
            #
            #     i=31 [50.00-51.09]   "比如这个搞雕塑的"
            #     i=32 [50.05-51.39] S "比如这个搞雕塑的"  <- nguoc chieu, van trung
            #
            # Nguyen nhan: `ung_vien` doi hoi GIAO THOI GIAN > 0. Khi OCR va ASR lech nhau
            # vai phan tram giay thi giao van duong, nhung khi lech han (vi du OCR 1.50-2.42
            # con ASR 1.14-2.42 — giao van duong) thi khong. Va ca khi giao = 0 thi doan ASR
            # van duoc giu nguyen, ke ca khi chu cua no TRUNG KHIT mot dong OCR da dung.
            #
            # Hau qua: ban long doc cung mot cau HAI LAN, va phu de hien hai dong chong nhau.
            #
            # Cach sua: so CHU, khong chi so THOI GIAN. Mot dong OCR da dung ma chua toan bo
            # chu cua doan ASR (hoac nguoc lai) thi doan ASR la BAN SAO — bo no.
            # 🔴 DO DUOC: ban dau toi chi kiem trong `da_dung` va no LUON RONG o nhanh
            # nay — vi `da_dung` chi duoc nap khi ASR KHOP mot dong OCR, ma day chinh la
            # nhanh "KHONG khop". Nen phep kiem chua bao gio chay, va hai bai test moi do
            # dung: `assert 2 == 1` voi hai ban cua cung mot cau.
            #
            # Phai kiem voi TOAN BO dong OCR, khong phai chi dong da dung: mot dong OCR
            # chua duoc dung vi ASR lech thoi gian van la BAN SAO cua doan ASR nay.
            if _da_co_chu(doan.text, [o.text for o in doan_ocr]):
                continue

            nghi = Segment(
                i=0,
                start=doan.start,
                end=doan.end,
                text=doan.text,
                words=doan.words,
                speaker=doan.speaker,
                suspect=True,
                # LOP 1: chi ASR nghe ra, OCR khong doc ra. Bang chung chat nhat
                # vi khong co nguon thu hai phu nhan.
                layer=LOP_MOT_NGUON,
            )
            ra.append(nghi)
            so_nghi += 1
            continue

        # Giữ MỌI dòng OCR đè lên đoạn này — kể cả khi có hai dòng. Đó đúng là yêu cầu:
        # "một đoạn asr có 2 đoạn ocr thì ưu tiên dùng 2 đoạn ocr đó mà bỏ đoạn asr".
        # 🔴 DA THU VA DA BO — ghi lai de khong ai lam lai lan nua.
        #
        # Y dinh: chi coi OCR la ban sua cua ASR khi CHU tuong ung, de giu duoc ca
        # nhung ca nhu #31 cap 6 (OCR "ΛNI" chong len ASR "所以为什么是榕树女神" — hai
        # thu khac han, ca hai deu that).
        #
        # DO DUOC no KHONG LAM DUOC, vi hai nhom khong tach ra duoc:
        #
        #                          giaoTho  tiLeASR  lenOCR  lenASR  cungCau
        #   fixture cu (OCR thang)   0.50     0.250     5      13     False
        #   #31 cap 6  (ASR giu)     0.50     0.258     3      10     False
        #   fixture cu (OCR thang)   0.50     0.167    10      15     False
        #   #31 cap 8  (ASR giu)     0.50     0.294     5      11     False
        #
        # Thoi gian chenh 0,008; do dai chenh 2 ky tu; `cungCau` deu False. Khong mot
        # dac trung nao tach duoc. Va quan trong hon: ap quy tac do lam DO ba bai test
        # cua chinh sach cu (`test_co_ocr_thi_dung_ocr`, `..._de_len_thi_dung_chu_ocr`,
        # `..._chua_hai_dong_ocr_thi_giu_ca_hai`) — tuc no DOI HOP DONG chu khong sua loi.
        #
        # Hop dong dang dung: OCR doc CHU DA BIEN TAP nen khi no de len mot doan ASR thi
        # OCR thang, ke ca khi ASR nghe ra chu khac. Giu nguyen.
        # --- BAO NHAU: giu CA HAI, chi danh dau ---
        #
        # DO DUOC: `_giao(219.17, 221.11, 220.00, 220.50, 0.5) = 1.5`, nhung giao THO chi
        # 0.50 — dung bang do dai doan OCR. Nghia la doan OCR nam GON trong doan ASR.
        # Ca that tren transcript #32:
        #
        #     ASR [219.17-221.11] "所以为什么是榕树女神"
        #     OCR [220.00-220.50] "ΛNI"       <- logo, khong phai loi thoai
        #
        # Voi ca nay, xoa mot ben la MAT du lieu: bo OCR thi mat dong chu that tren hinh,
        # bo ASR thi mat loi noi that. Nen giu ca hai va ghi `chua_trong` de giao dien biet
        # doan nao nam trong doan nao.
        # Xet bao theo TUNG dong OCR, khong theo "chi co mot dong khop".
        #
        # 🔴 DO DUOC: ban dau toi viet `len(ung_vien) == 1 and _bao(...)`, va no SAI tren
        # du lieu that. Transcript #33 co vung 219-221 chua HAI dong OCR cung giao voi mot
        # doan ASR:
        #
        #     ASR [219.17-221.11]
        #     OCR [220.00-220.50] giaoNoi=1.50  bao=True    <- logo, can giu ca hai
        #     OCR [221.00-221.50] giaoNoi=1.11  bao=False   <- dong thu hai
        #
        # `len(ung_vien)` la 2 nen `long_nhau` thanh False, va `ΛNI` bi gan `hai_nguon`
        # (do duoc: `Counter({("hai_nguon", True): 2})`) trong khi no chi co MOT nguon
        # doc ra.
        #
        # Dieu kien dung: dong OCR DANG XET bao doan ASR. Khong lien quan co bao nhieu
        # dong khac cung giao.
        # Hop dong cu van giu: mot doan ASR chua HAI dong OCR NGANG NHAU la ASR gop hai
        # cau phu de thanh mot, va khi do lay hai dong OCR, bo ASR.
        #
        # 🔴 DO DUOC dieu kien phan biet. Hai ca trong cung mot doan ASR:
        #
        #   #33  ASR [219.17-221.11]:  OCR [220.00-220.50] giaoTho=0.50  <- troi
        #                              OCR [221.00-221.50] giaoTho=0.11  <- chi cham mep
        #        => MOT dong troi han => do la logo, giu CA HAI.
        #
        #   fixture ASR [20.00-23.00]: OCR [20.00-20.50]    giaoTho=0.50  <- ngang
        #                              OCR [21.00-21.50]    giaoTho=0.50  <- ngang
        #        => hai dong NGANG NHAU => ASR gop hai cau, bo ASR.
        #
        # Nen: chi coi la bao khi dong bao la dong CO GIAO LON NHAT, va no troi han so
        # voi dong lon thu hai (>= 2 lan). Neu hai dong ngang nhau thi khong dong nao
        # "so huu" doan ASR nay, va hop dong cu ap dung.
        # Dung GIAO THO (khong noi `DUNG_SAI_OCR`): do duoc viec noi 0.5 lam ca hai
        # dong phinh gan bang nhau nen mat tuong phan —
        #
        #   #33 LambdaNI   giaoNoi=[1.50, 1.11] -> 1.50 >= 2*1.11 SAI  (mat ca)
        #   #33 LambdaNI   giaoTho=[0.50, 0.11] -> 0.50 >= 2*0.11 DUNG (giu ca hai)
        #   fixture 2 cau  giaoTho=[0.50, 0.50] -> 0.50 >= 2*0.50 SAI  (bo ASR)
        giao = [_giao(doan.start, doan.end, ocr.start, ocr.end, 0.0)
                for _, ocr in ung_vien]
        i_troi = giao.index(max(giao))
        giao_lon_nhi = sorted(giao)[-2] if len(giao) > 1 else 0.0
        troi_han = max(giao) >= 2 * giao_lon_nhi if giao_lon_nhi > 0 else True
        co_dong_bao = troi_han and _bao(
            ung_vien[i_troi][1].start, ung_vien[i_troi][1].end, doan.start, doan.end
        )
        if co_dong_bao:
            ra.append(Segment(
                i=0,
                start=doan.start,
                end=doan.end,
                text=doan.text,
                words=doan.words,
                speaker=doan.speaker,
                suspect=True,
                layer=LOP_MOT_NGUON,
            ))
            so_nghi += 1

        # 🔴 DOI HANH VI — nguoi dung chot: "NHO LA DANG CHIA 2 LAYER 2 DONG NHA".
        #
        # Ban truoc BO doan ASR khi OCR va ASR cung noi mot cau. Do duoc tren #36:
        # **51/56 doan `hai_nguon` khong con dong ASR nao song song** — chung mang
        # nhan "2 nguon" nhung thuc chat chi con chu OCR. Nhan sai su that.
        #
        # Nay giu CA HAI dong, moi dong mot lop:
        #   · dong OCR  -> `LOP_HAI_NGUON` (co nguon thu hai doi chieu)
        #   · dong ASR  -> `LOP_HAI_NGUON`, `suspect=True` (nghe duoc, da kiem cheo)
        #
        # Tru hai ca da xu ly o tren:
        #   · `co_dong_bao`  -> vat the khac (logo, ghi cong): ASR da duoc giu rieng
        #   · nhieu dong OCR -> ASR gop nhieu cau: khong co mot dong ASR tuong ung
        giu_asr = (not co_dong_bao) and len(ung_vien) == 1
        if giu_asr:
            ra.append(Segment(
                i=0,
                start=doan.start,
                end=doan.end,
                text=doan.text,
                words=doan.words,
                speaker=doan.speaker,
                suspect=True,
                layer=LOP_HAI_NGUON,
            ))

        # 🔴 DO DUOC — loi THAT, khong phai gia thiet.
        #
        # Ban truoc gan `hai_nguon` cho MOI dong trong `ung_vien`. Nhung `ung_vien`
        # duoc loc bang giao DA NOI, nen mot dong OCR chi CHAM MEP cung lot vao. Do
        # duoc bang phep do chen trong `hop_nhat_theo_doan` (transcript #38):
        #
        #     ASR [48.27-50.05] "有时又会显得很荒诞"
        #       uv j=7 [48.50-49.47] giaoTho=0.970  "有时又会显得很荒诞"  <- CUNG CAU
        #       uv j=8 [50.00-51.09] giaoTho=0.050  "比如这个搞雕塑的"    <- CHI CHAM MEP
        #
        # Ca hai deu bi gan `hai_nguon`, nen 33/56 dong OCR mang nhan "2 nguon" trong khi
        # chung chi co MOT nguon doc ra. Nhan noi sai su that, va mau tren giao dien vi
        # the cung sai theo.
        #
        # Dong OCR chi CHAM MEP van duoc GIU (no la phu de that), va van la LOP 1 — OCR
        # la ban mac dinh, khong phan biet chạm mep hay khong.
        #
        # `NGUONG_UNG` van dung cho `ung_vien` va `_da_co_chu` (nhan dien CUNG CAU), chi
        # khong con dung de gan LOP nua.
        for j, ocr in ung_vien:
            da_dung.add(j)

            # 🔴 DONG OCR LUON THUOC LOP 1.
            #
            # Nguoi dung chot: "lop 1 = mac dinh ocr + asr nhung cho ocr ko co.
            # lop 2 = asr doan ocr co".
            #
            # Do duoc tren #43 TRUOC khi sua: 27 dong OCR bi gan `hai_nguon`, vi ban cu
            # gan lop 2 moi khi `ung_that` (OCR va ASR cung cau). Nhung OCR la BAN MAC
            # DINH — no khong bao gio thuoc lop 2. Chi dong ASR moi vao lop 2, va chi khi
            # tai cho do DA CO OCR.
            #
            # Hau qua cua ban cu: hai dong cung lop 2 chong nhau (i=0 [0.00-1.04] OCR va
            # i=1 [0.00-1.14] ASR), nen mot lop phai trai hai lan tren timeline. Do la loi
            # nguoi dung chi ra: "the tai sao lop 2 van hien dong dau".
            lop = LOP_MOT_NGUON

            ra.append(Segment(
                i=0,
                start=ocr.start,
                end=ocr.end,
                text=ocr.text,
                suspect=False,
                layer=lop,
            ))
        so_de += 1

    # Dòng OCR KHÔNG đè lên đoạn ASR nào: vẫn giữ. Chúng là phụ đề cứng có thật mà ASR
    # không nghe ra (nhạc nền lớn, hoặc ASR dừng sớm — đo được: ASR dừng ở 1186,4 s trong
    # khi OCR phủ tới 1243 s). Bỏ chúng là bỏ đúng phần ASR yếu nhất.
    for j, ocr in enumerate(doan_ocr):
        if j not in da_dung:
            # LOP 1: chi OCR doc ra, ASR khong nghe ra. Cung la bang chung chat
            # nhat — khong co nguon thu hai phu nhan.
            ra.append(Segment(i=0, start=ocr.start, end=ocr.end, text=ocr.text,
                              suspect=False, layer=LOP_MOT_NGUON))

    ra.sort(key=lambda s: (s.start, s.end))
    for k, s in enumerate(ra):
        s.i = k

    # GAN `chua_trong` SAU CUNG: no tro toi `i` cua doan BAO, ma `i` chi dung sau khi
    # sap xep va danh lai. Gan trong luc dung se tro sai dong.
    for s in ra:
        for khac in ra:
            if khac is s:
                continue
            if _bao(s.start, s.end, khac.start, khac.end):
                s.chua_trong = khac.i
                break
    return ra, so_de, so_nghi


def chon_nguon(doan_ocr: list[Segment], doan_asr: list[Segment] | None
               ) -> tuple[list[Segment], str]:
    """Chọn nguồn chữ. Trả `(đoạn dùng được, lý do tiếng Việt)`.

    ## Ba tình huống, và vì sao chúng KHÁC NHAU

    * **Có OCR VÀ có ASR** ⇒ HỢP NHẤT theo từng đoạn (`hop_nhat_theo_doan`). Đây là thay
      đổi hành vi: bản trước để OCR thắng TUYỆT ĐỐI, nên một đoạn ASR nghe được mà OCR
      không đọc ra (phụ đề ngoài `vung_doc`, khung bị mờ) bị xoá IM LẶNG — người dùng mất
      lời nói mà không biết. Nay đoạn đó được giữ kèm `suspect = True` để hiện thành việc
      "nghi ngờ phiên âm" cho người dùng tự xem.
    * **Chỉ OCR** (không có ASR — engine ASR không có, hoặc `doan_asr` rỗng) ⇒ dùng OCR
      nguyên bản. KHÔNG đánh `suspect`: không có bằng chứng nào nói dòng đó sai.
    * **Chỉ ASR** (OCR rỗng — video không có phụ đề cứng) ⇒ dùng ASR nguyên bản, KHÔNG đánh
      `suspect`. Đây là điểm dễ sai: "OCR bật mà đọc ra rỗng" KHÁC "không có OCR". Khi OCR
      trả rỗng cho cả video thì đó là video không có phụ đề cứng — mọi đoạn ASR đều bình
      thường, đánh dấu nghi ngờ tất cả sẽ biến một video sạch thành 451 việc giả.
    * **Không cả hai** ⇒ `RuntimeError`. Im lặng trả `[]` khiến job "thành công" với bản
      lồng rỗng.
    """
    if doan_ocr and doan_asr:
        doan, so_de, so_nghi = hop_nhat_theo_doan(doan_ocr, doan_asr)
        ly_do = (f"hợp nhất OCR + ASR: {so_de} đoạn lấy chữ OCR, "
                 f"{so_nghi} đoạn chỉ có ASR (đánh dấu nghi ngờ), "
                 f"tổng {len(doan)} đoạn")
        return doan, ly_do
    if doan_ocr:
        return list(doan_ocr), f"dùng OCR: {len(doan_ocr)} dòng phụ đề đọc được từ hình"
    if doan_asr:
        return list(doan_asr), (f"dùng ASR: không đọc được phụ đề cứng nào, "
                                f"dùng {len(doan_asr)} đoạn lời nói")
    raise RuntimeError(
        "không có chữ để lồng tiếng: OCR không đọc được phụ đề cứng nào và ASR cũng không "
        "có đoạn lời nói nào — kiểm lại video (có phụ đề cứng? có tiếng nói?)"
    )


def khoang_co_tieng(doan_asr: list[Segment]) -> list[tuple[float, float]]:
    """Các khoảng CÓ tiếng nói, từ danh sách đoạn ASR. Dùng cho tầng lọc 4.

    Gộp hai đoạn cách nhau dưới `NGUONG_GOP` — ASR hay cắt một câu thành hai đoạn sát nhau,
    và nếu không gộp thì tầng 4 sẽ coi phần đệm giữa chúng là "không có tiếng" rồi xoá nhầm
    phụ đề nằm đúng đó.

    Trả `[]` khi không có đoạn nào; `loc_theo_asr` đã ghim là KHÔNG xoá gì khi nhận `[]`.
    """
    if not doan_asr:
        return []
    da_sap = sorted((float(s.start), float(s.end)) for s in doan_asr)
    ra: list[tuple[float, float]] = [da_sap[0]]
    for dau, cuoi in da_sap[1:]:
        if dau - ra[-1][1] < NGUONG_GOP:
            ra[-1] = (ra[-1][0], max(ra[-1][1], cuoi))
        else:
            ra.append((dau, cuoi))
    return ra
