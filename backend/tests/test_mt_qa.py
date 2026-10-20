"""QA tất định trên bản dịch. Không tốn model, nên phải chạy ở mọi lần dịch.

Mỗi issue có tiền tố ổn định để grep được trong `translations.qa_issues`.
"""
from app.domain.models import Segment, Term
from app.domain.mt_qa import QaLimits, qa_translation
from app.domain.qa_rules import LENGTH_RATIO_MAX


def seg(i: int, text: str, *, dur: float = 1.0) -> Segment:
    return Segment(i=i, start=0.0, end=dur, text=text)


def term(t: str, tr: str) -> Term:
    return Term(id=None, lang="zh", term=t, translation=tr, approved=True)


LIMITS = QaLimits(max_cps=10.0, min_len_ratio=0.5, max_len_ratio=2.0)


def test_clean_translation_reports_nothing():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con rồng")]
    assert qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS) == []


def test_cps_over_limit_is_reported_with_the_id():
    src, out = [seg(1, "a")], [seg(1, "x" * 30, dur=1.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert any(i.startswith("cps:1=") for i in issues), issues


def test_zero_duration_does_not_divide_by_zero():
    """F2: cửa sổ NGUỒN là cửa sổ `subtitle_format` thật sự ghi ra, nên nguồn
    1.0s + bản dịch 0.0s vẫn là một dòng đọc được — không phải vấn đề. Chỉ khi
    CẢ HAI vế không dương mới không đo được CPS, và lúc đó báo `nowindow`."""
    # nguồn 1.0s, bản dịch 0.0s -> đo trên nguồn -> dòng "b" trong 1.0s là ổn
    src, out = [seg(1, "a")], [seg(1, "b", dur=0.0)]
    assert qa_translation(src, out, glossary=[], supports_glossary=True,
                          limits=LIMITS) == []
    # cả hai vế 0.0s -> không có cửa sổ dương nào -> báo, và KHÔNG chia 0
    src0, out0 = [seg(1, "a", dur=0.0)], [seg(1, "b", dur=0.0)]
    issues = qa_translation(src0, out0, glossary=[], supports_glossary=True,
                            limits=LIMITS)
    assert issues == ["cps:1=nowindow/1c"]


def test_too_short_and_too_long_translations_are_reported():
    src = [seg(1, "x" * 10)]
    short = [seg(1, "y")]
    long_ = [seg(1, "z" * 40)]
    assert any(i.startswith("length:1=") for i in
               qa_translation(src, short, glossary=[], supports_glossary=True, limits=LIMITS))
    assert any(i.startswith("length:1=") for i in
               qa_translation(src, long_, glossary=[], supports_glossary=True, limits=LIMITS))


def test_missing_required_term_is_reported():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con rong")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=True, limits=LIMITS)
    assert any(i.startswith("missing_term:1=") for i in issues), issues


def test_present_required_term_is_not_reported():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con rồng lớn")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=True, limits=LIMITS)
    assert not any(i.startswith("missing_term:") for i in issues)


def test_engine_without_glossary_support_gets_a_flag_not_a_missing_term():
    src = [seg(1, "con rồng")]
    out = [seg(1, "con dragon")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=False, limits=LIMITS)
    assert "engine_no_glossary" in issues
    assert not any(i.startswith("missing_term:") for i in issues), \
        "engine không hỗ trợ glossary thì không được buộc tội thiếu thuật ngữ"


def test_empty_translated_text_is_reported():
    src, out = [seg(1, "con rồng")], [seg(1, "   ")]
    assert any(i.startswith("empty:1") for i in
               qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS))


# --- Fix round 1 -----------------------------------------------------------
# F1: ngưỡng độ dài ship ra phải là số repo đã ĐO, không phải 4.0 đã đo là sai.


def test_default_max_len_ratio_is_the_measured_qa_rules_value():
    """F1: `qa_rules` đo cùng phép đo và ship 5.0 (fixture 6 -> 26 = 4.33, nên
    4.0 cờ nhầm bản dịch đúng). Ghim ngưỡng từ CẢ HAI phía: 4.99 phải qua,
    5.01 phải bị bắt."""
    assert QaLimits().max_len_ratio == LENGTH_RATIO_MAX == 5.0

    src = [seg(1, "x" * 100, dur=1000.0)]
    under = [seg(1, "y" * 499, dur=1000.0)]     # 4.99 -> qua
    over = [seg(1, "y" * 501, dur=1000.0)]      # 5.01 -> bắt
    assert qa_translation(src, under, glossary=[], supports_glossary=True,
                          limits=QaLimits()) == []
    assert qa_translation(src, over, glossary=[], supports_glossary=True,
                          limits=QaLimits()) == ["length:1=5.01"]


# F2: CPS đo trên cửa sổ được HIỂN THỊ — cửa sổ nguồn.


def test_cps_uses_the_source_window_not_the_translation_window():
    """F2: `subtitle_format` ghi mốc thời gian NGUỒN và tra bản dịch theo vị trí,
    nên cửa sổ người xem thấy là cửa sổ nguồn. Nguồn 1.0s / bản dịch 3.0s: đo
    trên cửa sổ bản dịch thì 20 ký tự = 6.7 cps (im lặng), đo trên cửa sổ nguồn
    mới là 20.0 cps > 10.0 -> phải báo."""
    src = [seg(1, "x" * 20, dur=1.0)]
    out = [Segment(i=1, start=0.0, end=3.0, text="y" * 20)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert issues == ["cps:1=20.0>10.0"]


def test_cps_falls_back_to_the_translation_window_when_the_source_has_none():
    """F2: cửa sổ nguồn không dương là dữ liệu nguồn hỏng — vẫn còn cửa sổ bản
    dịch để đo thật, nên KHÔNG được báo `nowindow`."""
    src = [seg(1, "x" * 30, dur=0.0)]
    out = [Segment(i=1, start=0.0, end=1.0, text="y" * 30)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert issues == ["cps:1=30.0>10.0"]


# F3 + các survivor M6/M1b/M14/M16/M7/M8.


def test_only_approved_terms_are_required():
    """F3/M6: chỉ glossary ĐÃ DUYỆT mới là ràng buộc (design §8). Mục CHƯA DUYỆT
    là bản nháp của người dùng, thiếu nó không phải lỗi; mục đã duyệt thì phải
    báo."""
    src, out = [seg(1, "con rồng")], [seg(1, "con rong")]
    draft = Term(id=None, lang="zh", term="rồng", translation="rồng", approved=False)
    ok = Term(id=None, lang="zh", term="rồng", translation="rồng", approved=True)
    assert qa_translation(src, out, glossary=[draft], supports_glossary=True,
                          limits=LIMITS) == []
    assert qa_translation(src, out, glossary=[ok], supports_glossary=True,
                          limits=LIMITS) == ["missing_term:1=rồng->rồng"]


def test_no_glossary_flag_when_there_is_no_glossary_to_miss():
    """F3/M1b: cờ `engine_no_glossary` thay cho việc buộc tội thiếu thuật ngữ.
    Glossary rỗng thì engine không bỏ lỡ gì cả, nên không có cờ."""
    src, out = [seg(1, "con rồng")], [seg(1, "con rồng")]
    assert qa_translation(src, out, glossary=[], supports_glossary=False,
                          limits=LIMITS) == []


def test_empty_translation_reports_exactly_one_issue():
    """F3/M14: "một vấn đề, báo đúng một lần" — dòng ra rỗng chỉ được báo
    `empty:`, không kèm `length:1=0.00` và `missing_term:` cho cùng một lỗi."""
    src, out = [seg(1, "con rồng")], [seg(1, "   ")]
    issues = qa_translation(src, out, glossary=[term("rồng", "rồng")],
                            supports_glossary=True, limits=LIMITS)
    assert issues == ["empty:1"]


def test_empty_source_text_does_not_divide_by_zero():
    """F3/M16: segment nguồn rỗng là dữ liệu nguồn hỏng. Mẫu số kẹp xuống 1 để
    tỉ lệ không thành vô hạn và không ZeroDivisionError."""
    src, out = [seg(1, "")], [seg(1, "con rồng")]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True, limits=LIMITS)
    assert issues == ["length:1=8.00"]


# --------------------------------------------------------------------------
# A2: QA phải nhìn thấy NGÔN NGỮ ĐẦU RA.
#
# ĐO ĐƯỢC ở lượt trước: `qwen2.5-3b` qua `POST /api/translations` trả về CHÍNH
# chữ Trung gốc (9/9 job, 116–118 ký tự Hán) mà `qa_issues` là `[]` — QA chỉ đo
# CPS / tỉ lệ độ dài / thuật ngữ, không có phép kiểm nào cho "đầu ra có đúng
# ngôn ngữ đích không". Nên một bản "dịch" còn nguyên chữ Hán được ghi `done`.
#
# Hai mức, hai tiền tố con, cùng nằm dưới `lang:`:
#   `lang:<i>=source:han<n>/latin<m>` — dòng VẪN là chữ gốc (Hán >= chữ Latinh).
#   `lang:<i>=residue:han<n>`         — dòng đã là tiếng Việt nhưng còn sót Hán.
# Cả hai đều KHÔNG phá `opus-mt`: đầu ra của nó có 0 ký tự Hán (đo ở §1.5 lượt
# trước), nên ca XANH bên dưới đi kèm ca ĐỎ như luật của lượt này đòi.
# --------------------------------------------------------------------------

def test_an_echoed_chinese_line_is_flagged_as_still_the_source():
    """A2 RED TRƯỚC: echo chữ Trung -> `vi` không có cờ nào. Sau bản vá: có
    `lang:1=source:...`, và đó là thứ duy nhất được báo (CPS/tỉ lệ đều sạch).

    `你好` = 2 ký tự Hán, 0 chữ Latinh, nên chuỗi issue ghim luôn ĐỊNH DẠNG con
    số: `source:han2/latin0`. Cùng khuôn với `cps:1=30.0>10.0` của F2.
    """
    src = [seg(1, "你好", dur=1.0)]
    out = [seg(1, "你好", dur=1.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True,
                            target_lang="vi", limits=QaLimits())
    assert issues == ["lang:1=source:han2/latin0"], issues


def test_a_full_echo_batch_is_flagged_on_every_line():
    """Ca THẬT đã đo: 8/8 dòng trả về nguyên chữ Trung (118 ký tự Hán). Không
    dòng nào được coi là đạt."""
    src = [seg(1, "今天我们来聊一聊中文语音识别。", dur=3.0),
           seg(2, "这个项目的成本其实只有百分之十。", dur=3.0)]
    out = [seg(1, "今天我们来聊一聊中文语音识别。", dur=3.0),
           seg(2, "这个项目的成本其实只有百分之十。", dur=3.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True,
                            target_lang="vi", limits=QaLimits())
    flagged = [i for i in issues if i.startswith("lang:")]
    assert len(flagged) == 2, issues
    assert all("source:" in i for i in flagged), issues


def test_residual_chinese_in_a_vietnamese_line_is_flagged_as_residue():
    """Ca THẬT của `qwen2.5-3b` khi nó chịu dịch: còn sót một cụm Hán
    (`chiều明天下午`) — dòng đã là tiếng Việt (Hán chỉ 4/44 ký tự) nên không phải
    `source:`, nhưng KHÔNG được im lặng: đây đúng lớp `dịch字` mà
    `backend/README.md` đã ghi.

    Chuỗi này chép nguyên văn từ đầu ra ĐO ĐƯỢC ở `_realpipe2/echo_matrix.json`
    (ứng viên S1, mục 4), không phải một ví dụ tự nghĩ ra.
    """
    src = [seg(1, "天气预报说明天下午会有大雨。", dur=3.0)]
    out = [seg(1, "Báo cáo thời tiết cho biết trời sẽ mưa to vào chiều明天下午.", dur=3.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True,
                            target_lang="vi", limits=QaLimits())
    assert issues == ["lang:1=residue:han4"], issues


def test_the_language_check_does_not_touch_a_clean_vietnamese_translation():
    """Ca XANH: đầu ra THẬT của `opus-mt` trên cùng 8 câu (đo ở lượt trước,
    0/118 ký tự Hán) phải đi qua QA mà KHÔNG có cờ `lang:` nào."""
    src = [seg(1, "今天我们来聊一聊中文语音识别。", dur=3.0),
           seg(2, "这家餐厅的红烧肉特别好吃，你一定要试试。", dur=4.0),
           seg(3, "会议推迟到下周三上午九点半。", dur=3.0)]
    out = [seg(1, "Hôm nay chúng ta sẽ nói chuyện về tiếng Trung.", dur=3.0),
           seg(2, "Thịt nướng đỏ ở nhà hàng này ngon lắm đấy. Thử đi.", dur=4.0),
           seg(3, "Cuộc họp sẽ trì hoãn vào 3 giờ 30 sáng tuần tới.", dur=3.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True,
                            target_lang="vi")
    assert not [i for i in issues if i.startswith("lang:")], issues


def test_the_language_check_is_target_aware():
    """Dịch sang tiếng Trung thì chữ Hán là ĐÚNG, không phải lỗi: phép kiểm phải
    theo `target_lang`, không phải một luật cứng "cấm chữ Hán".

    Bám vào ĐÚNG thứ phép kiểm này sinh ra (`lang:`), không bám vào cả danh sách
    issue: `length:`/`cps:` là chuyện của hai phép đo khác, và một dòng ngắn hơn
    bản gốc là chuyện bình thường khi đi qua ngôn ngữ đích khác.
    """
    src = [seg(1, "con rồng", dur=3.0)]
    out = [seg(1, "龙", dur=3.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True,
                            target_lang="zh", limits=QaLimits())
    assert not [i for i in issues if i.startswith("lang:")], issues



def test_the_language_check_is_on_by_default():
    """Mặc định của `target_lang` là ngôn ngữ đích của sản phẩm (`vi`), nên
    người gọi cũ — và mọi đường nối quên truyền — vẫn được kiểm. Đây là điều
    kiện để bản vá này không trở thành một phép kiểm chết."""
    src = [seg(1, "今天我们来聊一聊中文语音识别。", dur=3.0)]
    out = [seg(1, "今天我们来聊一聊中文语音识别。", dur=3.0)]
    issues = qa_translation(src, out, glossary=[], supports_glossary=True,
                            limits=QaLimits())
    assert any(i.startswith("lang:1=source:") for i in issues), issues



# ---------------------------------------------------------------------------
# Bảo vệ thuật ngữ bằng token: hai cờ QA từng nói SAI khi cơ chế này bật
# ---------------------------------------------------------------------------


def test_an_enforced_glossary_silences_the_no_glossary_flag():
    """`engine_no_glossary` là thông tin SAI khi thuật ngữ đã được ép bằng token.

    `hy-mt-1.5-7b` khai `glossary_prompt: false`, nên engine KHÔNG nhận glossary
    qua prompt — nhưng pipeline che thuật ngữ bằng token rồi khôi phục bằng đúng
    chuỗi glossary. Giữ cờ này là báo cho người dùng một ràng buộc "không tồn
    tại", và smoke thật của tính năng đã cho ra đúng cờ sai đó.
    """
    terms = [term("曹磊", "Tào Lôi")]
    src, out = [seg(1, "曹磊")], [seg(1, "Tào Lôi")]
    assert "engine_no_glossary" in qa_translation(
        src, out, glossary=terms, supports_glossary=False)
    assert "engine_no_glossary" not in qa_translation(
        src, out, glossary=terms, supports_glossary=False, glossary_enforced=True)


def test_a_long_glossary_rendering_is_not_counted_as_model_verbosity():
    """Rendering dài theo policy không phải model lan man.

    Đo trên smoke thật: `小儿放纸鸢图` (6 chữ) render thành 46 ký tự có ngoặc, tỉ
    lệ 7,75 trên ngưỡng 5,0 — bản dịch đúng vẫn bị gắn `length:`. Sau khi quy
    rendering về độ dài chữ nguồn, tỉ lệ còn ~2,2 và cờ biến mất.
    """
    title = "Tranh thả diều của trẻ nhỏ (Tiểu Nhi Phóng Chỉ Diên Đồ)"
    src = [seg(1, "小儿放纸鸢图", dur=5.0)]
    out = [seg(1, f"Đây là {title}", dur=5.0)]
    # Chốt rằng phép so THÔ thật sự vượt ngưỡng — nếu không, bài này xanh vì lý do
    # khác và không chứng minh được gì.
    assert len(out[0].text) / len(src[0].text) > QaLimits().max_len_ratio
    issues = qa_translation(src, out, glossary=[term("小儿放纸鸢图", title)],
                            supports_glossary=True)
    assert not [i for i in issues if i.startswith("length:")], issues


def test_a_rendering_of_a_term_absent_from_the_source_is_not_forgiven():
    """Chỉ quy đổi rendering của thuật ngữ CÓ trong câu nguồn.

    Một rendering tình cờ nằm trong câu khác không phải chỗ glossary được áp; quy
    nó về chữ nguồn là bịa ra một phép so không có thật và sẽ dung túng đúng loại
    lan man mà luật `length:` sinh ra để bắt.
    """
    src = [seg(1, "con rồng", dur=1.0)]
    out = [seg(1, "con rồng Tào Lôi " + "x" * 25, dur=1.0)]
    issues = qa_translation(src, out, glossary=[term("曹磊", "Tào Lôi")],
                            supports_glossary=True)
    assert any(i.startswith("length:") for i in issues), issues
