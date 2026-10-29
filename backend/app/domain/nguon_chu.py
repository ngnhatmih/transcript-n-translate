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


def chon_nguon(doan_ocr: list[Segment], doan_asr: list[Segment] | None
               ) -> tuple[list[Segment], str]:
    """Chọn nguồn chữ. Trả `(đoạn dùng được, lý do tiếng Việt)`.

    Ưu tiên OCR. Rơi về ASR khi OCR rỗng (video không có phụ đề cứng). Ném `RuntimeError`
    khi cả hai đều rỗng — im lặng trả `[]` sẽ khiến job "thành công" với bản lồng rỗng.
    """
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
