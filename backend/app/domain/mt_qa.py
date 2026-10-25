"""QA tất định sau dịch: CPS, tỉ lệ độ dài, thuật ngữ bắt buộc, NGÔN NGỮ đầu ra.

Không tốn model nên chạy ở MỌI lần dịch. Đây là lớp bắt lỗi rẻ nhất; ngưỡng cụ
thể cho tiếng Việt còn để ngỏ (spec §12) và đo trên dữ liệu thật.

Issue dùng tiền tố ổn định để grep được trong `translations.qa_issues`:
`cps:` · `length:` · `missing_term:` · `empty:` · `lang:` · `echo:` · cờ trần
`engine_no_glossary`. (`echo:<n>/<tổng>` là issue CẤP LƯỢT do
`echo_run_issue` sinh; nó không đi qua `qa_translation` vì chế độ Chimera đã có
số đo `echo` riêng cho từng ứng viên và cộng thêm ở đây là đếm hai lần.)

Danh sách `glossary` truyền vào đã được lọc theo ngôn ngữ; `terms_in` KHÔNG lọc
`approved()` (Task 4 cố ý để bên gọi quyết định), nên ở đây lọc bằng `approved()`:
mục chưa duyệt là bản nháp của người dùng, không phải ràng buộc — buộc tội thiếu
một thuật ngữ chưa duyệt là báo lỗi cho một luật chưa hề được đặt ra.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .glossary_match import approved, terms_in
from .models import Segment, Term

#: Ngôn ngữ đích viết bằng chữ LATINH. Một dòng trả về còn nguyên chữ Hán thì
#: không phải bản dịch cho các ngôn ngữ này. `target_lang` khác (vd `zh`) KHÔNG
#: đi qua phép kiểm: ở đó chữ Hán là kết quả đúng.
_LATIN_SCRIPT_TARGETS = frozenset({"vi", "en"})

#: Ngôn ngữ đích mặc định của sản phẩm (`POST /api/translations` cũng mặc định
#: `vi`). Mặc định ở ĐÂY, không phải `None`: quên truyền thì phép kiểm vẫn chạy,
#: thay vì âm thầm tắt.
_DEFAULT_TARGET_LANG = "vi"

#: Chữ Hán (CJK Unified Ideographs + Ext A + tương thích). KHÔNG gồm dấu câu CJK
#: (`。`, `、`): chúng xuất hiện trong cả văn bản tiếng Việt trích dẫn, nên đếm
#: chúng là thổi phồng con số của phép đo.
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")




@dataclass(frozen=True)
class QaLimits:
    max_cps: float = 21.0          # ký tự mỗi giây; trên ngưỡng là khó đọc
    min_len_ratio: float = 0.25    # bản dịch ngắn hơn thế này là cụt
    # ĐÚNG bằng `qa_rules.LENGTH_RATIO_MAX` (5.0), và cùng phép đo — giữ hai con
    # số này lệch nhau là tự mâu thuẫn. Số đo ghi ở `qa_rules.py:13-19`: fixture
    # 6 -> 26 ký tự = 4.33, nên 4.0 vẫn cờ nhầm một bản dịch đúng; 5.0 qua cả
    # hai fixture mà vẫn bắt được ca bịa/lặp (~159 lần).
    max_len_ratio: float = 5.0     # dài hơn thế này là lan man / lặp


def _window(src: Segment, out: Segment) -> float:
    """Thời lượng dùng để tính CPS, tính bằng giây: cửa sổ của segment NGUỒN.

    Cửa sổ NGUỒN là khoảng thời gian người xem thật sự thấy dòng dịch:
    `subtitle_format.to_srt/to_vtt/to_ass` ghi mốc `seg.start --> seg.end` của
    `segments` NGUỒN và chỉ tra bản dịch theo VỊ TRÍ (`subtitle_format.py:56-64`
    và `:71-78`; `pipeline/export.py:80` bắt `len(translations) ==
    len(transcript.segments)`). Đo CPS trên cửa sổ của chính bản dịch là đo một
    khoảng không ai thấy — cùng một dòng có thể bị tốc độ sai chỉ vì engine trả
    mốc thời gian khác.

    Cửa sổ bản dịch chỉ là DỰ PHÒNG khi cửa sổ nguồn không dương (dữ liệu nguồn
    hỏng): vẫn còn hơn là không đo được gì.

    Trả `0.0` chỉ khi CẢ HAI cửa sổ đều không dương — lúc đó CPS thật sự không
    đo được và bên gọi báo `nowindow` thay vì bịa ra một con số.
    """
    src_window = src.end - src.start
    if src_window > 0:
        return src_window
    return out.end - out.start


@dataclass(frozen=True)
class CpsRow:
    """CPS của MỘT đoạn dịch, dạng SỐ — không phải một chuỗi hiển thị.

    Vì sao tách khỏi `qa_translation`: chuỗi `cps:` trong `translations.qa_issues`
    VÀ con số mà `GET /api/translations/{id}` trả cho màn Đối chiếu phải là CÙNG một
    đại lượng. Hai chỗ tính CPS là hai chỗ trôi khỏi nhau — đúng lớp lỗi mà spec
    frontend §2 dựng ra để chặn. Cả hai đi qua `cps_row` dưới đây.

    `cps is None` nghĩa là KHÔNG ĐO ĐƯỢC (cả cửa sổ nguồn lẫn cửa sổ bản dịch đều
    không dương). Khác hẳn `0.0` (một tốc độ thật bằng không), và khác `inf`: đó là
    DỮ LIỆU HỎNG, không phải "hơi nhanh". `chars` vẫn có để nói được đã đếm bao
    nhiêu ký tự — theo đúng cách nhánh `nowindow` của `qa_translation` đã làm.
    """

    i: int
    #: `len(text.strip())` — CÙNG định nghĩa với con số trong chuỗi `cps:`.
    chars: int
    #: Cửa sổ NGUỒN (dự phòng: cửa sổ bản dịch), giây.
    window: float
    #: `None` = không đo được.
    cps: float | None
    max_cps: float
    over: bool


def cps_row(src: Segment, out: Segment, *,
            limits: QaLimits = QaLimits()) -> CpsRow:
    """CHỖ DUY NHẤT tính CPS.

    `out` là đoạn DỊCH (bên được đo), `src` là đoạn nguồn cùng `i` (bên cho cửa sổ
    thời gian). Gọi `cps_row(t, t)` khi không có đoạn nguồn tương ứng: cửa sổ nguồn
    bằng 0 nên `_window` tự rơi về cửa sổ bản dịch — đúng quy tắc dự phòng đã có,
    không phải một quy tắc mới.

    `over` so trên giá trị CHƯA làm tròn. Đó là lý do nó phải đi kèm con số ra
    ngoài: một client tự so `cps` (đã làm tròn để hiển thị) với `max_cps` sẽ nói
    SAI ở đúng biên (21,04 CPS hiển thị là 21,0).
    """
    text = out.text.strip()
    window = _window(src, out)
    if window <= 0:
        return CpsRow(i=out.i, chars=len(text), window=window, cps=None,
                      max_cps=limits.max_cps, over=False)
    cps = len(text) / window
    return CpsRow(i=out.i, chars=len(text), window=window, cps=cps,
                  max_cps=limits.max_cps, over=cps > limits.max_cps)


def cps_issue(row: CpsRow) -> str | None:
    """Chuỗi `cps:` cho `qa_issues`, sinh TỪ CÙNG dữ liệu với con số của route.

    Trả `None` khi đoạn đó không có gì để báo (đo được và không vượt ngưỡng).
    Định dạng giữ nguyên y như trước khi tách hàm — nó là hợp đồng grep được.

    Nhánh `nowindow` ghi SỐ KÝ TỰ chứ không ghi một thời lượng: `0.0s` cho một cửa
    sổ âm là con số bịa. Báo như thế này thay vì để phép chia giết cả job dịch.

    ⚠️ CƠ CHẾ (ERRATA #15 mục 2 — bản đầu của khối này kể SAI): `json.dumps({"cps":
    inf})` **KHÔNG** ném, nó trả `{"cps": Infinity}` (đã đo). `ValueError: Out of range
    float values are not JSON compliant` đến từ `JSONResponse.render` của Starlette,
    nơi gọi `json.dumps(..., allow_nan=False)`. Nên `inf` không phải thứ `json.dumps`
    từ chối — nó là thứ **tầng HTTP** từ chối.

    ⚠️ `CpsRow.chars` ở trên đếm `len(text.strip())` — **CÓ** khoảng trắng. Route
    `readability` phát một khoá đếm ký tự **KHÁC** (`chars_no_space`, bỏ khoảng
    trắng), nên cùng một dòng có thể ra hai con số. Hai tên khác nhau là cố ý.
    """
    if row.cps is None:
        return f"cps:{row.i}=nowindow/{row.chars}c"
    if row.over:
        return f"cps:{row.i}={row.cps:.1f}>{row.max_cps}"
    return None


def _language_issues(src: Segment, out: Segment,
                     target_lang: str | None) -> list[str]:
    """Cờ `lang:` khi dòng dịch VẪN là chữ của bản gốc.

    Vì sao cần (A2, đo được): `qwen2.5-3b` qua `POST /api/translations` trả về
    CHÍNH chữ Trung gốc (9/9 job, 116–118 ký tự Hán) mà QA cũ — CPS, tỉ lệ độ
    dài, thuật ngữ — không có phép kiểm nào cho "đầu ra có đúng ngôn ngữ đích
    không", nên `qa_issues` là `[]`, job `done`, transcript `translated`. Đó là
    thất bại ÂM THẦM ở tầng ngữ nghĩa, đúng lớp mà `AlignmentProblem` chặn ở
    tầng cấu trúc.

    Hai mức, hai tiền tố con, cùng nằm dưới `lang:`:

    * `lang:<i>=source:han<n>/latin<m>` — Hán >= chữ Latinh, tức dòng đó VẪN là
      bản gốc. Đây là ca echo, và là ca mà một sản phẩm Trung -> Việt không được
      phép coi là đạt.
    * `lang:<i>=residue:han<n>` — dòng đã là tiếng Việt nhưng còn SÓT chữ Hán
      (`Hội nghị đã được推迟到下周三上午九点半举行`). Nhẹ hơn, vẫn phải báo:
      đây đúng lớp `dịch字` mà `backend/README.md` đã ghi.

    Phép kiểm chỉ chạy khi `target_lang` là ngôn ngữ viết bằng chữ Latinh
    (`_LATIN_SCRIPT_TARGETS`): dịch sang tiếng Trung thì chữ Hán là ĐÚNG.

    ⚠️ GIỚI HẠN đã biết, ghi ra chứ không giấu: phép đo là "còn chữ Hán", nên nó
    bắt được chiều zh -> vi/en (chiều DUY NHẤT mà registry đã ship phục vụ:
    `langs` của mọi engine là `zh`/`en`). Một bản echo Latinh -> Latinh (en -> vi)
    KHÔNG bị phép kiểm này bắt; muốn bắt thì cần phép đo khác (vd. so trùng từ),
    và đó là việc của lượt sau, không phải của một heuristic đội lốt.
    """
    if target_lang not in _LATIN_SCRIPT_TARGETS:
        return []
    text = out.text.strip()
    if not text:
        # Dòng rỗng đã có `empty:` báo rồi — "một vấn đề, báo đúng một lần".
        return []
    han = len(_CJK.findall(text))
    if not han:
        return []
    latin = sum(1 for ch in text if ch.isalpha() and not _CJK.match(ch))
    if han >= latin:
        return [f"lang:{out.i}=source:han{han}/latin{latin}"]
    return [f"lang:{out.i}=residue:han{han}"]


#: Tỉ lệ chữ Hán trong một DÒNG mà từ đó coi dòng đó là "vẫn là bản nguồn".
#:
#: Chọn 0,5 theo SỐ ĐO chứ không theo cảm tính — phân bố tỉ lệ đó trên bản ghi
#: thật của clip 115 đoạn (`20261019-term-placeholder-clip`, mọi lượt chạy
#: `hy-mt`, đọc từ artifact):
#:
#: * nhóm KHÔNG phải echo (bản dịch tiếng Việt có sót chữ Hán): 0,035 – 0,29 —
#:   đều là câu mà thuật ngữ đã được THAY bằng rendering tiếng Việt vào giữa câu
#:   Trung (`找个螺钿搓字` -> `找个khảm xà cừ搓字`, tỉ lệ 0,286);
#: * nhóm echo THẬT: 1,00 ở 18/18 dòng đo được — kể cả khi model sửa vài chữ
#:   trong chính câu Trung (`我反正要来一场大的` -> `我反正要办一场盛大的活动`).
#:
#: Khoảng trống 0,29 – 1,00 là lý do chọn 0,5: nó rơi ĐÚNG vào chỗ không có mẫu
#: nào, nên ngưỡng không phải một con số tuỳ ý chen giữa hai cụm.
#:
#: ⚠️ Nhóm 0,035 – 0,29 ở trên là echo + rendering glossary, và nó KHÔNG lọt lưới:
#: phép so trong đường ống chạy trên bản ĐÃ token hoá (`term_placeholder`), nên
#: câu đó khớp NGUYÊN VĂN với bản đã che (`这是ZXQ1` -> `这是ZXQ1`) và bị bắt bởi
#: luật so nguyên văn, không cần luật tỉ lệ.
ECHO_HAN_RATIO = 0.5

#: Tỉ lệ ĐOẠN bị echo trên cả lượt dịch mà từ đó gắn issue cấp lượt.
#:
#: 5% theo đề xuất của review, và nó tương đương "1 đoạn trên clip 20 đoạn": dưới
#: mức đó là lỗi lẻ của một câu, trên mức đó là model đang KHÔNG dịch. Con số này
#: chỉ điều khiển CẢNH BÁO, không chặn gì (`done` vẫn là `done`).
ECHO_ALERT_RATIO = 0.05

#: Cờ gắn lên `Segment.qa` của đoạn VẪN là bản chép nguồn sau khi đã dịch lại.
#: Nằm cùng kênh với bốn cờ `token_*`, nên nó đi tới phụ đề mà không cần cột mới.
ECHO_FLAG = "echo"


def is_echo(source_text: str, out_text: str) -> bool:
    """`out_text` có phải BẢN CHÉP của `source_text` (không phải bản dịch) không.

    Bốn luật, mỗi luật có một ca thật đứng sau:

    * **Rỗng** -> coi là echo. Dòng rỗng không phải bản dịch, và `qa_translation`
      đã báo `empty:` riêng; ở đây nó phải bị DỊCH LẠI, không chỉ bị báo.
    * **Nguồn KHÔNG có chữ Hán** -> KHÔNG phải echo. Khi nguồn không có chữ Hán
      thì không có gì "chưa dịch": một con số, một mã, hay một token Latinh được
      giữ nguyên là đầu ra HỢP LỆ, không phải bản chép hỏng của một bản dịch. Ca
      thật: đoạn 9 của clip 115 đoạn, nguồn `2288` -> đích `2288` — QA gắn cờ
      `echo` cho nó chỉ vì hai chuỗi giống nhau, và cờ đó nằm trong cả hai artifact
      `data/experiments/accuracy-pipelines/20261019-echo-guard/` và
      `20261019-prompt-echo-sweep/`. Luật này đứng TRƯỚC luật nguyên văn và luật
      tỉ lệ, nên hai luật dưới chỉ nói về nguồn CÓ chữ Hán — nơi "chép nguồn" mới
      thật sự là lỗi.
    * **Khớp NGUYÊN VĂN** (sau khi cắt khoảng trắng) -> echo. Đây là phép so mà
      `chimera.echo_count` đã dùng để xếp hạng ứng viên, và là ca đã đo được:
      `qwen2.5-3b` ở prompt `p1` chép nguyên chữ Hán 43/44 đoạn.
    * **Tỉ lệ chữ Hán > `ECHO_HAN_RATIO`** -> echo. Luật này bắt ca KHÓ HƠN mà
      phép so nguyên văn bỏ sót: model không chép y nguyên mà VIẾT LẠI trong
      chính ngôn ngữ nguồn (`而且看讲的都是路人` -> `而且讲讲的都是路人`,
      `我反正要来一场大的` -> `我反正要办一场盛大的活动`). Đo trên clip 115 đoạn:
      22/89 đoạn echo ở lô 30 thuộc dạng này, và chúng đều có tỉ lệ Hán 1,00.

    Vì sao KHÔNG dùng "khác rỗng là đạt": một dòng tiếng Việt có sót tên riêng
    Hán (`Hội nghị đã được推迟到下周三`) là bản dịch HỎNG MỘT PHẦN, không phải
    bản chép; dịch lại nó là việc đúng, nhưng nó không cùng lớp với "model không
    dịch gì cả" — và luật tỉ lệ ở trên phân biệt được hai lớp đó bằng số đo.
    """
    source = source_text.strip()
    out = out_text.strip()
    if not out:
        return True
    if not _CJK.search(source):
        # Nguồn không có chữ Hán: giữ nguyên `2288`, một mã, hay một token Latinh
        # là bản dịch ĐÚNG, không phải "chép nguồn" (ca `2288` -> `2288` đã bị QA
        # bắt oan trong `20261019-echo-guard/` và `20261019-prompt-echo-sweep/`).
        return False
    if source and out == source:
        return True
    han = len(_CJK.findall(out))
    return han / len(out) > ECHO_HAN_RATIO


#: Ngôn ngữ NGUỒN viết bằng chữ Hán. Chỉ `zh`: đó là chiều duy nhất registry đã
#: ship phục vụ (`langs` của mọi engine là `zh`/`en`) và là chiều ĐÃ ĐO của lỗi
#: này. Không suy rộng ra `ja`/`yue` — chúng chưa có trong `langs`, nên một phép
#: kiểm cho chúng là một phép kiểm chưa lần nào chạy trên dữ liệu thật.
_HAN_SCRIPT_SOURCES = frozenset({"zh"})

#: Tỉ lệ chữ Hán / ký tự KHÔNG phải khoảng trắng mà từ đó coi đầu ra là BẢN CHÉP
#: của nguồn. Đây là ngưỡng của `echoes_source` (cổng CHẶN), khác `ECHO_HAN_RATIO`
#: ở trên (ngưỡng của QA/dịch lại, chỉ báo).
#:
#: Vì sao có ngưỡng chứ không phải "có một chữ Hán là echo": phép kiểm phải KHÔNG
#: bắt oan một bản dịch tiếng Việt còn giữ một thuật ngữ Hán trong ngoặc. Đo trên
#: artifact thật (clip 115 đoạn, `20261019-term-placeholder-clip`), nhóm KHÔNG phải
#: echo có tỉ lệ Hán 0,035 – 0,29 khi chia cho CẢ chuỗi (cách `is_echo` đếm); chia
#: cho ký tự không phải khoảng trắng — cách đếm ở đây, vì khoảng trắng tiếng Việt
#: không phải "nội dung" — câu lai cao nhất trong nhóm đó là
#: `找个khảm xà cừ搓字` = 4/12 = 0,33. Nhóm echo THẬT là 1,00 (18/18 dòng đo được,
#: kể cả khi model sửa vài chữ trong chính câu Trung). Khoảng trống 0,33 – 1,00
#: rỗng, nên 0,5 nằm ĐÚNG giữa chỗ không có mẫu nào và chịu được cả hai phía: 6/12
#: = 0,50 mới bị chặn, còn câu "Anh ấy nói chữ 人" (1/13 = 0,08) thì không.
#:
#: ⚠️ Ngưỡng này MỘT MÌNH không đủ, và số đo chỉ ra chỗ thủng: 7/115 đoạn của clip
#: có thuật ngữ glossary, và tính trung thực trên bản ĐÃ token hoá (`ZXQ{n}` thay
#: thuật ngữ, đúng thứ engine nhận) thì 2/7 đoạn tụt xuống 0,33 khi bị chép nguyên
#: (`这是小儿放纸鸢图` -> `这是ZXQ1` = 2/6, `来烟台山吧` -> `来ZXQ1吧` = 2/6). Vì vậy
#: `echoes_source` còn một luật thứ hai: khớp NGUYÊN VĂN với nguồn là echo, bất kể
#: tỉ lệ — với nguồn tiếng Trung thì một chuỗi y hệt nguồn không thể là bản dịch.
ECHO_GUARD_SHARE = 0.5


def echoes_source(source_text: str, translation: str, *, source_lang: str,
                  target_lang: str) -> bool:
    """`translation` có phải BẢN CHÉP của `source_text`, theo nghĩa CHẶN được không.

    Đây là vị từ của **echo guard** (`TranslateHandler._guard_echoes`): cổng chặn
    lô dịch, không phải QA. Khác `is_echo` ở ba điểm, mỗi điểm có lý do:

    * **Có cổng ngôn ngữ.** Chỉ bật khi NGUỒN viết bằng chữ Hán và ĐÍCH viết bằng
      chữ Latinh (`_HAN_SCRIPT_SOURCES` + `_LATIN_SCRIPT_TARGETS`). `is_echo` là
      phép đo của QA nên nó chạy cho mọi cặp ngôn ngữ; chặn một lô vì "đầu ra có
      chữ Hán" khi đích là `zh` sẽ là chặn đúng bản dịch. Nguồn không có chữ Hán
      thì cũng không xét: một câu tiếng Anh bị chép nguyên văn không phải lỗi mà
      cổng này tồn tại để bắt (xem "GIỚI HẠN" bên dưới).
    * **Rỗng KHÔNG phải echo.** Dòng rỗng đã có issue `empty:` riêng và không phải
      "model chép nguồn"; `is_echo` trả `True` cho nó vì QA cần DỊCH LẠI dòng
      rỗng. Ở đây `False` để một lô hỏng vì lý do khác không bị báo sai nguyên
      nhân.
    * **Hai luật, không phải ba.** (a) khớp NGUYÊN VĂN với nguồn (sau khi cắt
      khoảng trắng) và (b) tỉ lệ chữ Hán >= `ECHO_GUARD_SHARE` (0,5) trên ký tự
      không phải khoảng trắng. Luật (a) bắt đúng ca của lỗi này — "trả nguyên chữ
      Trung" — kể cả khi thuật ngữ glossary đã thay chữ Hán bằng `ZXQ{n}` và làm
      tỉ lệ tụt dưới 0,5 (2/7 đoạn có thuật ngữ, số đo ở `ECHO_GUARD_SHARE`). Luật
      (b) bắt ca KHÓ hơn mà khớp nguyên văn bỏ sót: model viết lại trong chính
      tiếng Trung (`而且看讲的都是路人` -> `而且讲讲的都是路人`), 22/89 đoạn echo ở
      lô 30, tỉ lệ Hán 1,00.

    ⚠️ GIỚI HẠN đã biết, ghi ra chứ không giấu: luật (a) chỉ chạy khi NGUỒN có
    chữ Hán, nên một câu nguồn thuần Latinh bị chép nguyên văn KHÔNG bị chặn —
    cố ý, vì `iPhone` -> `iPhone` là bản dịch ĐÚNG và chặn nó là biến một bản dịch
    đúng thành lỗi. Muốn bắt echo Latinh -> Latinh (`en` -> `vi`) thì cần phép đo
    khác (so trùng từ), và đó là việc của lượt sau.

    Hàm THUẦN và TẤT ĐỊNH: không model, không I/O, không phụ thuộc batch.
    """
    if source_lang not in _HAN_SCRIPT_SOURCES:
        return False
    if target_lang not in _LATIN_SCRIPT_TARGETS:
        return False
    source = (source_text or "").strip()
    text = (translation or "").strip()
    if not source or not text:
        return False
    if not _CJK.search(source):
        # Nguồn không có chữ Hán: "chép nguồn" ở đây không phân biệt được với một
        # bản dịch đúng trùng chuỗi (xem GIỚI HẠN ở trên).
        return False
    if text == source:
        return True
    han = len(_CJK.findall(text))
    if not han:
        return False
    visible = sum(1 for ch in text if not ch.isspace())
    return han / max(visible, 1) >= ECHO_GUARD_SHARE


def echo_run_issue(src: list[Segment], out: list[Segment]) -> str | None:
    """Issue CẤP LƯỢT DỊCH khi tỉ lệ đoạn echo vượt `ECHO_ALERT_RATIO`.

    Vì sao cần một issue riêng chứ không chỉ dựa vào `lang:<i>`: cờ `lang:` là
    từng đoạn, nên một lượt dịch hỏng 89/115 đoạn vẫn chỉ là một dãy cờ dài mà
    người đọc phải ĐẾM mới biết mức độ. Một dòng `echo:89/115` tự nói ra tỉ lệ, và
    nó là thứ để grep/bật cảnh báo mà không phải hiểu ngữ nghĩa từng cờ.

    `src` rỗng -> `None` (không có mẫu số thì không có tỉ lệ).
    """
    by_id = {t.i: t for t in out}
    total = 0
    echoed = 0
    for s in src:
        t = by_id.get(s.i)
        if t is None:
            continue
        total += 1
        if is_echo(s.text, t.text):
            echoed += 1
    if not total or echoed / total <= ECHO_ALERT_RATIO:
        return None
    return f"{ECHO_FLAG}:{echoed}/{total}"


def _length_basis(out_text: str, src_text: str, terms: list[Term]) -> str:
    """Chữ của OUTPUT sau khi quy mỗi rendering glossary về ĐỘ DÀI CHỮ NGUỒN.

    Vì sao phải quy đổi: luật `length:` tồn tại để bắt model LAN MAN/LẶP, nhưng
    rendering của glossary có thể dài hơn chữ nguồn rất nhiều theo policy sản
    phẩm — đo trên smoke thật, tiêu đề `小儿放纸鸢图` render thành "Tranh thả diều
    của trẻ nhỏ (Tiểu Nhi Phóng Chỉ Diên Đồ)" và câu 6 ký tự thành 46 ký tự, tỉ lệ
    **7,75** trong khi bản dịch không hề lan man: phần dài thêm là CHUỖI CỦA
    GLOSSARY, không phải lời của model. Không quy đổi thì mọi thuật ngữ có
    rendering dài đều bị gắn cờ sai, và người dùng học cách bỏ qua `length:`.

    Chỉ thay rendering của thuật ngữ CÓ trong câu nguồn (`terms_in`): một rendering
    tình cờ xuất hiện trong câu khác không phải chỗ glossary được áp, quy nó về
    chữ nguồn là bịa ra một phép so không có thật.
    """
    basis = out_text
    for term in terms_in(src_text, terms):
        rendering = term.translation.strip()
        if not rendering:
            continue
        # Không phân biệt hoa/thường: tiếng Việt viết hoa đầu câu là chuyện thường,
        # và `re.escape` để rendering có ngoặc/dấu chấm không thành cú pháp regex.
        basis = re.sub(re.escape(rendering), term.term, basis, flags=re.IGNORECASE)
    return basis


def qa_translation(src: list[Segment], out: list[Segment], *, glossary: list[Term],
                   supports_glossary: bool, limits: QaLimits = QaLimits(),
                   target_lang: str = _DEFAULT_TARGET_LANG,
                   glossary_enforced: bool = False) -> list[str]:
    """Sinh danh sách issue. Rỗng nghĩa là không thấy vấn đề tất định nào.

    Giả định `check_alignment` đã chạy trước: `src` và `out` khớp id theo thứ tự.
    Segment có trong `src` mà thiếu ở `out` bị BỎ QUA chứ không báo: lúc đó là
    `check_alignment`/`TranslateHandler` phải nói, không phải QA.

    `target_lang` MẶC ĐỊNH là `vi` — ngôn ngữ đích của sản phẩm — nên mọi đường
    nối quên truyền vẫn được kiểm; đây là điều kiện để phép kiểm ngôn ngữ không
    trở thành một phép kiểm chết.

    `glossary_enforced` = thuật ngữ đã được ÉP bằng token rồi khôi phục
    (`pipeline/translate.py` + `domain/term_placeholder.py`), không qua prompt.
    Khi đó `engine_no_glossary` là thông tin SAI: engine không nhận glossary qua
    prompt, nhưng rendering vẫn được bảo đảm bằng hậu xử lý. Cờ này cũng KHÔNG
    kéo theo `missing_term:`: một token bị model bỏ đã có cờ riêng `token_lost`
    trên segment, báo thêm `missing_term:` là hai cờ cho một sự việc.
    """
    issues: list[str] = []
    if not supports_glossary and glossary and not glossary_enforced:
        # Thông tin, KHÔNG phải lỗi: engine này không có đường nào nhận glossary.
        # Cờ này thay cho mọi `missing_term:` — engine không nhận được ràng buộc
        # thì không thể bị buộc tội vi phạm nó. Một vấn đề, báo đúng một lần.
        issues.append("engine_no_glossary")

    required = approved(glossary)
    by_id = {s.i: s for s in out}
    for s in src:
        t = by_id.get(s.i)
        if t is None:
            continue
        text = t.text.strip()
        if not text:
            issues.append(f"empty:{s.i}")
            continue

        # CPS: hình dạng chuỗi do `cps_issue` quyết, con số do `cps_row` tính —
        # CÙNG một chỗ với con số mà `GET /api/translations/{id}` trả ra.
        issue = cps_issue(cps_row(s, t, limits=limits))
        if issue is not None:
            issues.append(issue)

        # Mẫu số kẹp xuống 1: segment nguồn rỗng làm mọi bản dịch thành "quá dài"
        # với tỉ lệ vô hạn — đó là lỗi của dữ liệu nguồn, không phải của bản dịch.
        # Tử số quy rendering glossary về độ dài chữ nguồn (`_length_basis`): cái
        # dài thêm của một chuỗi policy không phải là model lan man.
        base = max(len(s.text.strip()), 1)
        ratio = len(_length_basis(text, s.text, required)) / base
        if ratio < limits.min_len_ratio or ratio > limits.max_len_ratio:
            issues.append(f"length:{s.i}={ratio:.2f}")

        # Thuật ngữ bắt buộc phải XUẤT HIỆN trong bản dịch. So không phân biệt
        # hoa thường vì tiếng Việt viết hoa đầu câu là chuyện bình thường.
        if supports_glossary:
            lowered = text.casefold()
            for term in terms_in(s.text, required):
                if term.translation.strip().casefold() not in lowered:
                    issues.append(f"missing_term:{s.i}={term.term}->{term.translation}")

        # Ngôn ngữ đầu ra báo SAU CÙNG: nó là phép kiểm nặng nhất về nghĩa, và
        # một dòng vừa quá nhanh vừa còn nguyên chữ Hán thì cả hai đều đúng.
        issues.extend(_language_issues(s, t, target_lang))
    return issues
