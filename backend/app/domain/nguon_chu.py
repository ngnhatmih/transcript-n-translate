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


def _giao(a_start: float, a_end: float, b_start: float, b_end: float,
          dung_sai: float = 0.0) -> float:
    """Độ dài phần GIAO của hai khoảng, sau khi nới mỗi khoảng `dung_sai` về hai phía."""
    dau = max(a_start - dung_sai, b_start - dung_sai)
    cuoi = min(a_end + dung_sai, b_end + dung_sai)
    return max(0.0, cuoi - dau)


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
        ung_vien = [
            (j, ocr) for j, ocr in enumerate(doan_ocr)
            if j not in da_dung
            and _giao(doan.start, doan.end, ocr.start, ocr.end, DUNG_SAI_OCR) > 0.0
        ]
        if not ung_vien:
            nghi = Segment(
                i=0,
                start=doan.start,
                end=doan.end,
                text=doan.text,
                words=doan.words,
                speaker=doan.speaker,
                suspect=True,
            )
            ra.append(nghi)
            so_nghi += 1
            continue

        # Giữ MỌI dòng OCR đè lên đoạn này — kể cả khi có hai dòng. Đó đúng là yêu cầu:
        # "một đoạn asr có 2 đoạn ocr thì ưu tiên dùng 2 đoạn ocr đó mà bỏ đoạn asr".
        for j, ocr in ung_vien:
            da_dung.add(j)
            ra.append(Segment(
                i=0,
                start=ocr.start,
                end=ocr.end,
                text=ocr.text,
                suspect=False,
            ))
        so_de += 1

    # Dòng OCR KHÔNG đè lên đoạn ASR nào: vẫn giữ. Chúng là phụ đề cứng có thật mà ASR
    # không nghe ra (nhạc nền lớn, hoặc ASR dừng sớm — đo được: ASR dừng ở 1186,4 s trong
    # khi OCR phủ tới 1243 s). Bỏ chúng là bỏ đúng phần ASR yếu nhất.
    for j, ocr in enumerate(doan_ocr):
        if j not in da_dung:
            ra.append(Segment(i=0, start=ocr.start, end=ocr.end, text=ocr.text,
                              suspect=False))

    ra.sort(key=lambda s: (s.start, s.end))
    for k, s in enumerate(ra):
        s.i = k
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
