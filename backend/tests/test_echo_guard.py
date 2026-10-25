"""Vị từ `mt_qa.echoes_source` — cổng CHẶN echo của đường dịch.

Vì sao có tệp này (SỐ ĐO, clip 115 đoạn `20261019-name-patch-smoke/`): với
`hy-mt-1.5-7b`, ở lô 30 mặc định model trả NGUYÊN chữ Trung cho **59–89/115
đoạn**, lô 15 là **29/115**, lô 8 là **0–8/115**; `opus-mt` cùng clip là **0/115**.
Số mục vẫn khớp nên `check_alignment` cho qua, QA chỉ gắn `lang:<i>` từng dòng, và
hàng `translations` vẫn `done`. Vị từ ở đây là phép đo của cổng CHẶN
(`TranslateHandler._guard_echoes`), nên nó phải TẤT ĐỊNH, THUẦN, và hẹp vừa đủ để
không chặn một bản dịch đúng còn giữ thuật ngữ Hán.

Bốn bất biến được ghim:
* bản dịch tiếng Việt sạch -> `False`;
* bản CHÉP nguyên chữ Hán -> `True` (cả khi model viết lại trong chính tiếng
  Trung, ca khó hơn mà phép so nguyên văn bỏ sót);
* câu tiếng Việt còn một thuật ngữ Hán, tỉ lệ thấp -> `False` — ngưỡng `0,5` được
  ghim bằng đúng con số đã đo, không phải một con số tuỳ ý;
* rỗng/khoảng trắng -> `False`: dòng rỗng đã có issue `empty:` riêng, và "model
  không viết gì" không phải "model chép nguồn".

Vị từ có CỔNG NGÔN NGỮ: `zh -> vi`/`en` mới xét, `zh -> zh` thì chữ Hán là kết quả
ĐÚNG. Bài cuối tệp ghim chính cái cổng đó.
"""
from __future__ import annotations

import pytest

from app.domain.mt_qa import ECHO_GUARD_SHARE, echoes_source

#: Câu nguồn tiếng Trung dùng ở hầu hết bài — câu thật của clip, và là câu đã đo
#: được là bị chép ở lô 20 nhưng dịch được ở lô 4 (`test_translate_echo.py`).
ZH = "作为一个搞艺术的"


def _echoes(translation: str, source: str = ZH, *, source_lang: str = "zh",
            target_lang: str = "vi") -> bool:
    return echoes_source(source, translation, source_lang=source_lang,
                         target_lang=target_lang)


# ------------------------------------------------------- bốn ca của hợp đồng ---

def test_a_clean_vietnamese_translation_is_not_an_echo():
    assert _echoes("Là một người làm nghệ thuật") is False
    assert _echoes("Điều khiến tôi băn khoăn nhất chính là") is False


def test_a_pure_han_copy_is_an_echo_even_when_whitespace_moves():
    assert _echoes(ZH) is True, "chép nguyên văn chính là lỗi đang sửa"
    assert _echoes(f"  {ZH} ") is True, (
        "khoảng trắng đầu/cuối không làm một bản chép thành bản dịch"
    )


def test_a_chinese_rewrite_that_is_not_byte_identical_is_still_an_echo():
    """Ca KHÓ: model không chép y nguyên mà viết lại TRONG chính tiếng Trung.

    Đo trên artifact thật (lô 30, 22/89 đoạn echo): `而且看讲的都是路人` ->
    `而且讲讲的都是路人`, `我反正要来一场大的` -> `我反正要办一场盛大的活动`. Phép
    so nguyên văn bỏ sót cả hai; tỉ lệ chữ Hán của chúng là 1,00 nên LUẬT TỈ LỆ
    phải bắt, và đó là lý do vị từ có hai luật chứ không chỉ luật khớp nguyên văn.
    """
    assert _echoes("而且讲讲的都是路人", "而且看讲的都是路人") is True
    assert _echoes("我反正要办一场盛大的活动", "我反正要来一场大的") is True


def test_empty_output_is_not_an_echo():
    """Rỗng là lỗi KHÁC (`empty:`), không phải "model chép nguồn".

    Vì sao khác `is_echo`: QA cần DỊCH LẠI dòng rỗng nên `is_echo("…", "  ")` là
    `True`; còn cổng chặn lô mà báo "echo" cho một dòng rỗng là báo SAI nguyên
    nhân, và `empty:` đã nói đúng nguyên nhân đó rồi.
    """
    assert _echoes("") is False
    assert _echoes("   \n\t ") is False


# ------------------------------------- ngưỡng 0,5: ca KHÔNG được bắt oan ---

def test_a_han_term_inside_vietnamese_text_at_low_share_is_not_an_echo():
    """Câu lai còn tên riêng Hán: bản dịch HỎNG MỘT PHẦN, không phải bản chép.

    Hai câu lấy từ artifact thật của clip (nhóm KHÔNG phải echo), và cả hai đều có
    thuật ngữ glossary được viết bằng tiếng Việt ở giữa câu Trung:

    * `找个螺钿搓字` -> `找个khảm xà cừ搓字`: 4 chữ Hán / 12 ký tự không phải
      khoảng trắng = **0,33** — đây là câu lai cao nhất đo được trong nhóm này;
    * `福州烟台山的市场负责人` -> `福州Yên Đài Sơn的市场负责人`: 8/17 = **0,47**.

    Cả hai dưới 0,5 nên KHÔNG bị chặn; chặn chúng sẽ là dịch lại (và có thể làm
    hỏng cả lô) vì một cái tên riêng, đúng thứ mà ngưỡng `ECHO_GUARD_SHARE` tồn
    tại để tránh.
    """
    assert _echoes("找个khảm xà cừ搓字", "找个螺钿搓字") is False, "4/12 = 0,33"
    assert _echoes("福州Yên Đài Sơn的市场负责人", "福州烟台山的市场负责人") is False, (
        "8/17 = 0,47 — vẫn dưới ngưỡng"
    )


def test_a_single_quoted_han_character_never_fails_a_segment():
    """Một chữ Hán trong ngoặc là TRÍCH DẪN, không phải bản chép."""
    assert _echoes("Anh ấy nói chữ 人") is False, "1/13 = 0,08"
    assert _echoes("Người ta viết là 人 rồi mới đến 大") is False


def test_the_threshold_is_the_documented_one():
    """Ngưỡng là DỮ LIỆU đã đo (khoảng trống 0,33–1,00), không phải số tuỳ ý."""
    assert ECHO_GUARD_SHARE == 0.5


# ------------------------- luật khớp nguyên văn: cứu ca đã token hoá thuật ngữ ---

def test_an_exact_copy_of_a_tokenised_source_is_an_echo():
    """Thuật ngữ đã thành `ZXQ{n}` làm tỉ lệ Hán TỤT, nên luật tỉ lệ một mình hụt.

    Số đo trên chính clip: 7/115 đoạn có thuật ngữ glossary; hai trong số đó, khi
    bị chép nguyên ở dạng ĐÃ token hoá (đúng chuỗi engine nhận), chỉ còn 2/6 =
    0,33 — dưới ngưỡng 0,5. Luật khớp nguyên văn bắt chúng, và nó an toàn vì với
    nguồn có chữ Hán thì một chuỗi y hệt nguồn KHÔNG THỂ là bản dịch tiếng Việt.
    """
    assert _echoes("这是ZXQ1", "这是ZXQ1") is True
    assert 2 / 6 < ECHO_GUARD_SHARE, "luật tỉ lệ một mình sẽ bỏ sót đúng ca này"


# ------------------------------------------------------- cổng NGÔN NGỮ ---

def test_a_source_without_han_is_never_an_echo():
    """Không có chữ Hán ở nguồn thì "chép nguồn" không phân biệt được với dịch đúng.

    GIỚI HẠN đã biết và ghi ra: `iPhone` -> `iPhone` là bản dịch ĐÚNG ở chiều
    `zh -> vi`, nên luật khớp nguyên văn KHÔNG được chạy khi nguồn không có chữ
    Hán. Muốn bắt echo Latinh -> Latinh (`en -> vi`) thì cần phép đo khác.
    """
    assert _echoes("iPhone", "iPhone") is False
    assert _echoes("你好", "Hello") is False


@pytest.mark.parametrize("source_lang,target_lang", [
    ("en", "vi"),   # nguồn không viết bằng chữ Hán
    ("zh", "zh"),   # đích viết bằng chữ Hán: chữ Hán là kết quả ĐÚNG
    ("zh", "ja"),   # không phải đích chữ Latinh
])
def test_the_guard_only_speaks_for_han_source_to_latin_script_target(
        source_lang, target_lang):
    """Cổng ngôn ngữ: `zh -> zh` mà bị chặn thì là chặn đúng bản dịch."""
    assert _echoes(ZH, source_lang=source_lang, target_lang=target_lang) is False
