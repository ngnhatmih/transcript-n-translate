"""Hợp đồng của `experiments/accuracy_pipelines/name_patch.py` và CLI của nó.

Đây là bộ vá **lúc chạy thật**: với một video MỚI, caption OCR đốt trong hình và
transcript ASR được so trong cùng một cửa sổ thời gian, rồi chỗ nghe gần đồng âm
của tên riêng được sửa trong chữ NGUỒN trước khi dịch. Vì vậy mỗi bài ở đây có
hai phía, đúng như bộ test của miner:

* phía "phải bắt được": một tên riêng bị nghe nhầm mà bỏ sót thì âm Hán-Việt của
  chữ SAI đi thẳng vào bản dịch, và không ai truy được nó từ đâu ra;
* phía "tuyệt đối không được bắt": một bản vá đổi số liệu, đổi hệ chữ, hay đổi
  một chữ phổ thông là phá dữ liệu, không phải sửa lỗi.

Không bài nào cần `pypinyin`/`opencc` thật, không bài nào chạm mạng/GPU: hàm chính
nhận `pinyin_fn` và `t2s_fn` như tham số và các bài dưới bơm bản GIẢ. Hai bài CLI
chặn gói bằng `sys.modules` (đặt `None`) để kiểm đúng thông báo cài đặt mà không
cần gỡ gói khỏi venv.

Bất biến quan trọng nhất nằm ở bài `test_a_pair_that_no_miner_ever_saw_is_patched`:
bộ canh này KHÔNG đọc `ocr-glossary-candidates.json` / `ocr-glossary-manual-
approvals.json` của miner. Chúng là đầu ra của MỘT clip và là test harness của
riêng bộ đào; đường chạy thật chỉ có (ASR, OCR) của video đang xử lý.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

import scripts.patch_names_from_ocr as cli
from experiments.accuracy_pipelines import name_patch

#: Bảng âm tiết giả: chữ không có trong bảng trả về chính nó — đúng hành vi
#: `errors="default"` của `lazy_pinyin`, nên hình dạng dữ liệu mà bộ canh nhìn thấy
#: giống bản thật. Chỉ những chữ QUYẾT ĐỊNH số phận một candidate mới cần có mặt:
#: chữ ngữ cảnh xuất hiện ở cả hai vế nên tự triệt tiêu.
SYLLABLES = {
    "燕": "yan",
    "烟": "yan",
    "雁": "yan",
    "找": "zhao",
    "赵": "zhao",
    "雷": "lei",
    # Cặp `教过`/`交给`: core (nối chuỗi) = 0,714 nhưng cửa sổ (danh sách âm tiết)
    # = 0,5 — đúng chỗ hai phép đo cố ý khác nhau.
    "教": "jiao",
    "交": "jiao",
    "过": "guo",
    "给": "gei",
    # Tiêu đề `小儿放纸鸢图`: cặp `二`/`儿` và `指缘`/`纸鸢` phải qua được cả hai
    # phép so để chứng minh dấu câu `《》` NGOÀI core không chặn bản vá.
    "二": "er",
    "儿": "er",
    "指": "zhi",
    "纸": "zhi",
    "缘": "yuan",
    "鸢": "yuan",
}


def fake_pinyin(text: str) -> list[str]:
    return [SYLLABLES.get(char, char) for char in text]


def no_t2s(text: str) -> str:
    """t2s giả = đồng nhất: các bài dưới dùng chữ giản thể sẵn, và bơm bản giả để
    không bài nào phải nạp `opencc`."""
    return text


def run(segments, rows, **kwargs):
    return name_patch.patch_transcript(
        segments, rows, pinyin_fn=fake_pinyin, t2s_fn=no_t2s, **kwargs
    )


def asr_row(i: int, start: float, end: float, text: str) -> dict:
    return {"i": i, "start": start, "end": end, "text": text}


def ocr_row(i: int, start: float, end: float, text: str) -> dict:
    return {"i": i, "start": start, "end": end, "ocr": text}


# ---------------------------------------------------------------------------
# 1. Ca của video MỚI: cùng cửa sổ thì vá, mốc thời gian không được xê dịch
# ---------------------------------------------------------------------------


def test_a_new_video_pair_is_patched_and_timings_are_untouched():
    """`燕台山` -> `烟台山` khi caption OCR nằm trong cùng cửa sổ.

    Đây là hình dạng việc thật: ASR nghe nhầm một âm tiết của địa danh, caption
    đốt trong hình ghi đúng, và hai bên nói cùng lúc. Cặp hẹp là MỘT chữ, nên nếu
    không có cửa sổ neo (`燕台山`/`烟台山`) thì bản vá trượt
    `single_character_not_patchable` và tên riêng đi vào bản dịch với âm sai.
    """
    segments = [asr_row(0, 10.0, 12.0, "我去了燕台山")]
    rows = [ocr_row(7, 10.1, 11.9, "我去了烟台山")]

    result = run(segments, rows)

    assert result.segments[0]["text"] == "我去了烟台山"
    assert (result.segments[0]["start"], result.segments[0]["end"]) == (10.0, 12.0)
    assert result.stats == {
        "segments": 1,
        "ocr_rows": 1,
        "overlaps": 1,
        "applied": 1,
        "rejected": 0,
    }
    assert len(result.changes) == 1
    change = result.changes[0]
    assert {
        "i", "before", "after", "narrow_wrong", "narrow_correct",
        "window_wrong", "window_correct", "core_pinyin_ratio",
        "window_pinyin_ratio", "ocr_row_i", "ocr_text", "overlap_s",
    } <= set(change)
    assert change["i"] == 0
    assert change["before"] == "我去了燕台山"
    assert change["after"] == "我去了烟台山"
    assert change["narrow_wrong"] == "燕"
    assert change["narrow_correct"] == "烟"
    # Cửa sổ neo phải mở đủ hai ký tự bên phải để thành một CỤM, không phải một chữ.
    assert change["window_wrong"] == "燕台山"
    assert change["window_correct"] == "烟台山"
    assert change["core_pinyin_ratio"] == 1.0
    assert change["window_pinyin_ratio"] == 1.0
    assert change["ocr_row_i"] == 7
    assert change["ocr_text"] == "我去了烟台山"
    assert change["overlap_s"] == 1.8


# ---------------------------------------------------------------------------
# 2. Cửa sổ thời gian là cổng THẬT, không phải trang trí
# ---------------------------------------------------------------------------


def test_a_row_outside_the_window_is_never_considered():
    """Cùng cặp chữ, nhưng dòng OCR cách 30 giây thì KHÔNG được vá.

    Caption của cả clip đều cùng nội dung chủ đề, nên nếu bỏ cửa sổ thời gian thì
    một dòng ở phút thứ ba có thể "sửa" một câu ở phút đầu — bản vá đúng chữ nhưng
    sai chỗ. `overlaps` phải bằng 0: dòng đó chưa từng được xét, và log phải nói
    được điều đó (khác với "đã xét rồi loại").
    """
    segments = [asr_row(0, 10.0, 12.0, "我去了燕台山")]
    rows = [ocr_row(7, 40.0, 41.0, "我去了烟台山")]

    result = run(segments, rows)

    assert result.changes == []
    assert result.rejected == []
    assert result.stats == {
        "segments": 1,
        "ocr_rows": 1,
        "overlaps": 0,
        "applied": 0,
        "rejected": 0,
    }
    assert result.segments[0]["text"] == "我去了燕台山"


# ---------------------------------------------------------------------------
# 3. Số liệu bị chuẩn hoá lại không phải nghe nhầm tên riêng
# ---------------------------------------------------------------------------


def test_a_number_reshaped_by_ocr_is_not_a_name_patch():
    """`一瓶是2000` / `一平尺2,000` phải bị loại với lý do `digits_or_symbols`.

    Đo trên đúng dòng `i` = 13 của reference: `SequenceMatcher` cắt thành
    `replace` `瓶值 -> 平尺` **cộng một `insert` dấu phẩy**, nên chữ số nằm NGOÀI
    cặp hẹp. Cặp hẹp vì thế trông sạch (`ping shi`/`ping chi`, 0,857) và lý do
    loại sẽ là một luật âm thanh — đúng cái không trả lời được câu "vì sao chỗ này
    không vá": nó KHÔNG phải chuyện nghe nhầm, nó là số liệu. Bài này ghim rằng
    CHỮ SỐ được kiểm trên vùng ±2 ký tự (đúng vùng cửa sổ neo nhìn tới) và được
    kiểm TRƯỚC các luật âm thanh.
    """
    segments = [asr_row(0, 0.0, 2.0, "一瓶是2000")]
    rows = [ocr_row(13, 0.1, 1.9, "一平尺2,000")]

    result = run(segments, rows)

    assert result.changes == []
    assert result.segments[0]["text"] == "一瓶是2000"
    assert [entry["reason"] for entry in result.rejected] == ["digits_or_symbols"]
    entry = result.rejected[0]
    assert entry["i"] == 0
    assert entry["ocr_row_i"] == 13
    assert entry["narrow_wrong"] == "瓶是"
    assert entry["narrow_correct"] == "平尺"
    assert result.stats["applied"] == 0
    assert result.stats["rejected"] == 1


# ---------------------------------------------------------------------------
# 3b. Tiêu đề sách: dấu câu NGOÀI core không được chặn, chữ số trong ±2 thì vẫn
#     chặn — cùng một luật, HAI phạm vi (vòng sửa 2)
# ---------------------------------------------------------------------------


def test_a_book_title_with_brackets_outside_the_core_is_patched():
    """`这是小二放指缘图` -> `这是小儿放纸鸢图`: `《》` nằm NGOÀI core, không chặn.

    Tiêu đề Hán luôn có `《》`, nên nếu luật dấu câu soi cả vùng ±2 thì MỌI tiêu đề
    tác phẩm đều thành false negative — đúng loại tên mà bộ vá sinh ra để sửa.
    Đo trên dòng `i` = 12 của reference: `指缘`/`纸鸢` có core = cửa sổ = 1,0 và
    từng bị chặn chỉ vì `《` nằm trong ±2. Ở decode smoke, câu này còn một lỗi
    cạnh đó (`小二` -> `小儿`) nên CẢ HAI bản vá phải được áp, và không được sinh
    ra dòng `rejected` nào cho câu này.
    """
    segments = [asr_row(14, 19.5, 20.92, "这是小二放指缘图")]
    rows = [ocr_row(12, 19.4, 20.9, "这是《小儿放纸鸢图》")]

    result = run(segments, rows)

    assert result.segments[0]["text"] == "这是小儿放纸鸢图"
    assert {
        (change["narrow_wrong"], change["narrow_correct"])
        for change in result.changes
    } == {("二", "儿"), ("指缘", "纸鸢")}
    assert result.rejected == [], "dấu câu ngoài core không được sinh ra dòng loại"
    assert result.stats["applied"] == 2


def test_the_guard_splits_digits_from_punctuation():
    """Cùng một luật, HAI phạm vi: chữ số ở ±2 thì chặn, dấu câu ở ±2 thì không.

    Đây là bất biến dễ trôi nhất khi sửa guard: nới dấu câu ra ngoài core mà nới
    luôn chữ số theo là quay lại chuyện "chuẩn hoá" số liệu (`一瓶是2000` bị vá
    thành `一平尺2000`); siết chữ số vào trong core là bỏ lọt đúng ca chữ số nằm ở
    `insert` (dòng `i` = 13: `replace` `瓶是 -> 平尺` + `insert` dấu phẩy). Một
    bài, hai đoạn: đoạn 0 là số (phải loại `digits_or_symbols`), đoạn 1 là tiêu đề
    có `《》` (phải vá).
    """
    segments = [
        asr_row(0, 0.0, 1.0, "一瓶是2000"),
        asr_row(1, 2.0, 4.0, "这是小二放指缘图"),
    ]
    rows = [
        ocr_row(13, 0.1, 0.9, "一平尺2,000"),
        ocr_row(12, 2.1, 3.9, "这是《小儿放纸鸢图》"),
    ]

    result = run(segments, rows)

    assert result.segments[0]["text"] == "一瓶是2000"
    assert result.segments[1]["text"] == "这是小儿放纸鸢图"
    digits = [entry for entry in result.rejected if entry["i"] == 0]
    assert [entry["reason"] for entry in digits] == ["digits_or_symbols"]
    assert digits[0]["narrow_wrong"] == "瓶是"
    assert digits[0]["narrow_correct"] == "平尺"
    assert [entry for entry in result.rejected if entry["i"] == 1] == []
    assert result.stats["applied"] == 2


# ---------------------------------------------------------------------------
# 4. Cặp một chữ không có ngữ cảnh thì không bao giờ được áp
# ---------------------------------------------------------------------------


def test_a_one_character_diff_without_context_is_never_applied():
    """`燕` vs `烟`: mỗi vế một chữ, không mở được cửa sổ neo.

    Không có ngữ cảnh thì không có bằng chứng đây là TÊN bị nghe nhầm thay vì một
    khác biệt từ vựng; bản vá phải nằm trong `rejected` kèm tên luật, không phải
    biến mất khỏi mọi danh sách.
    """
    segments = [asr_row(0, 0.0, 1.0, "燕")]
    rows = [ocr_row(1, 0.0, 1.0, "烟")]

    result = run(segments, rows)

    assert result.changes == []
    assert result.segments[0]["text"] == "燕"
    assert result.rejected[0]["reason"] == "single_character_not_patchable"
    assert result.rejected[0]["narrow_wrong"] == "燕"
    assert result.rejected[0]["narrow_correct"] == "烟"


# ---------------------------------------------------------------------------
# 5. Hai dòng OCR chồng nhau: KHÔNG chọn heuristic, không áp gì
# ---------------------------------------------------------------------------


def test_two_overlapping_rows_proposing_different_fixes_apply_nothing():
    """Cùng một khoảng, hai dòng OCR đề xuất `烟` và `雁`: cả hai đều gần đồng âm.

    Caption hai dòng và hai trạng thái caption liền nhau là chuyện có thật, nên
    tình huống này sẽ xảy ra. Chọn một theo heuristic là đặt cược 50/50 rồi ghi
    vào transcript như thể chắc chắn; ở đây KHÔNG áp gì và ghi `ambiguous` kèm cả
    hai đề xuất để người đọc quyết định.
    """
    segments = [asr_row(0, 10.0, 12.0, "我去了燕台山")]
    rows = [
        ocr_row(1, 10.1, 11.9, "我去了烟台山"),
        ocr_row(2, 10.1, 11.9, "我去了雁台山"),
    ]

    result = run(segments, rows)

    assert result.changes == []
    assert result.segments[0]["text"] == "我去了燕台山"
    assert result.stats["applied"] == 0
    ambiguous = [entry for entry in result.rejected if entry["reason"] == "ambiguous"]
    assert len(ambiguous) == 2, "mỗi đề xuất phải có một dòng giải trình riêng"
    proposals = ambiguous[0]["proposals"]
    assert {proposal["narrow_correct"] for proposal in proposals} == {"烟", "雁"}
    assert {proposal["ocr_row_i"] for proposal in proposals} == {1, 2}
    assert ambiguous[1]["proposals"] == proposals
    assert {entry["ocr_row_i"] for entry in ambiguous} == {1, 2}


# ---------------------------------------------------------------------------
# 6. Bản vá chỉ được đổi `text`
# ---------------------------------------------------------------------------


def test_only_text_changes_never_timings_or_ids():
    """Sau khi vá, mọi `i`/`start`/`end` và mọi khoá khác phải y nguyên.

    Cắt phụ đề, ghép bản dịch và mọi bước sau đều bám theo mốc thời gian; một bản
    vá làm lệch `end` nửa giây là hỏng cả dây chuyền chứ không chỉ một câu. Đầu
    vào cũng không được bị sửa tại chỗ: người gọi còn cần bản gốc để đối chiếu.
    """
    segments = [
        {"i": 0, "start": 10.0, "end": 12.0, "text": "我去了燕台山", "avg_logprob": -0.2},
        {"i": 1, "start": 12.0, "end": 14.0, "text": "然后回家", "avg_logprob": -0.3},
    ]
    rows = [ocr_row(7, 10.1, 11.9, "我去了烟台山")]

    result = run(segments, rows)

    assert [(item["i"], item["start"], item["end"]) for item in result.segments] == [
        (0, 10.0, 12.0),
        (1, 12.0, 14.0),
    ]
    assert result.segments[0]["text"] == "我去了烟台山"
    assert result.segments[0]["avg_logprob"] == -0.2
    assert result.segments[1] == segments[1], "đoạn không bị vá phải y nguyên từng byte"
    without_text = lambda segment: {k: v for k, v in segment.items() if k != "text"}
    assert without_text(result.segments[0]) == without_text(segments[0])
    assert segments[0]["text"] == "我去了燕台山", "đầu vào không được sửa tại chỗ"
    assert result.segments is not segments


# ---------------------------------------------------------------------------
# 7. Không đọc artefact của miner: cặp CHƯA AI ĐÀO vẫn phải vá được
# ---------------------------------------------------------------------------


def test_a_pair_that_no_miner_ever_saw_is_patched():
    """`找雷` -> `赵雷` không có trong bảng đào, và vẫn phải được vá.

    Nếu bộ canh đọc `ocr-glossary-candidates.json` (đầu ra của một clip) thì video
    mới chỉ được vá những cặp đã gặp ở clip cũ — tức bước chạy thật chỉ còn là tra
    bảng, và mọi tên riêng chưa ai đào đi thẳng vào bản dịch với âm Hán-Việt của
    chữ sai. Bài này khoá cả hành vi lẫn mã nguồn: module không được nhắc tới tên
    artefact nào của miner.
    """
    segments = [asr_row(0, 0.0, 3.0, "这首歌是找雷唱的")]
    rows = [ocr_row(5, 0.1, 2.9, "这首歌是赵雷唱的")]

    result = run(segments, rows)

    assert result.segments[0]["text"] == "这首歌是赵雷唱的"
    assert result.changes[0]["narrow_wrong"] == "找"
    assert result.changes[0]["narrow_correct"] == "赵"

    # Khoá cả MÃ NGUỒN, không chỉ hành vi: docstring được phép nhắc tên artefact
    # (để giải thích vì sao không đọc nó), nhưng không literal nào khác được mang
    # tên artefact/đường dẫn tệp — nghĩa là bộ canh không có chỗ nào để mở chúng.
    tree = ast.parse(pathlib.Path(name_patch.__file__).read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    assert not [text for text in literals if "ocr-glossary" in text], (
        "module chạy thật không được đọc artefact đào của miner"
    )
    assert not [text for text in literals if text.endswith(".json")]


# ---------------------------------------------------------------------------
# 8. Tất định
# ---------------------------------------------------------------------------


def test_the_same_input_twice_produces_the_same_json():
    """Hai lần chạy cùng đầu vào phải ra cùng JSON.

    Log bản vá là thứ người khác dùng để đối chiếu giữa hai biến thể decode; nếu
    thứ tự `changes`/`rejected` phụ thuộc thứ tự duyệt của `set`/`dict` thì hai lần
    chạy giống hệt nhau lại ra hai tệp khác nhau, và mọi diff đều thành nhiễu.
    """
    segments = [
        asr_row(0, 10.0, 12.0, "我去了燕台山"),
        asr_row(1, 0.0, 2.0, "一瓶是2000"),
    ]
    rows = [
        ocr_row(1, 10.1, 11.9, "我去了烟台山"),
        ocr_row(13, 0.1, 1.9, "一平尺2,000"),
    ]

    first = json.dumps(run(segments, rows).to_dict(), ensure_ascii=False)
    second = json.dumps(run(segments, rows).to_dict(), ensure_ascii=False)

    assert first == second
    parsed = json.loads(first)
    assert parsed["stats"]["applied"] == 1
    assert parsed["stats"]["rejected"] == 1


# ---------------------------------------------------------------------------
# 9. Hai phép so pinyin là hai phép đo KHÁC NHAU, cố ý
# ---------------------------------------------------------------------------


def test_the_window_granularity_rejects_a_pair_the_core_would_pass():
    """`教过`/`交给`: core (nối chuỗi) = 0,714 qua, cửa sổ (danh sách âm tiết) = 0,5 trượt.

    Đây là lý do hai phép so tồn tại riêng: nối chuỗi thưởng cho chữ cái trùng nhau
    GIỮA hai âm tiết nên nó nới tay với các cặp chỉ gần âm, còn so danh sách chỉ
    tính âm tiết khớp TRỌN VẸN. Một khác biệt động từ (`giáo quá`/`giáo giao`)
    không phải tên bị nghe nhầm, và nếu cửa sổ cũng bị bỏ thì nó sẽ được vá.
    """
    segments = [asr_row(0, 0.0, 2.0, "教过我们")]
    rows = [ocr_row(57, 0.1, 1.9, "交给我们")]

    result = run(segments, rows)

    assert result.changes == []
    assert result.segments[0]["text"] == "教过我们"
    entry = result.rejected[0]
    assert entry["reason"] == "window_not_homophone"
    assert entry["core_pinyin_ratio"] == 0.714
    assert entry["window_pinyin_ratio"] == 0.5


# ---------------------------------------------------------------------------
# 10. Watermark / dòng rỗng bị lọc TRƯỚC khi canh
# ---------------------------------------------------------------------------


def test_watermark_and_placeholder_rows_are_never_matched():
    """Watermark kênh nằm cùng cửa sổ với lời nói gần như suốt clip.

    9 trong 21 dòng `excluded_observations` của reference có `ocr` là watermark
    (`想想工作室`, ...). Ghép chúng với ASR thì bản vá biến lời nói thành chữ trên
    màn hình, nên chúng bị bỏ trước khi canh; `ocr_rows` vẫn đếm chúng (đã đọc),
    `overlaps` thì không (chưa từng được xét).
    """
    segments = [asr_row(0, 10.0, 12.0, "我去了燕台山")]
    rows = [
        ocr_row(0, 10.0, 12.0, "想想工作室"),
        ocr_row(1, 10.0, 12.0, "..."),
        ocr_row(7, 10.1, 11.9, "我去了烟台山"),
    ]

    result = run(segments, rows)

    assert result.segments[0]["text"] == "我去了烟台山"
    assert result.stats["ocr_rows"] == 3
    assert result.stats["overlaps"] == 1
    assert result.stats["applied"] == 1
    assert [change["ocr_row_i"] for change in result.changes] == [7]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def write_json(path: pathlib.Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_cli_preserves_the_document_shape_and_other_keys(tmp_path):
    """Tệp ra phải cùng hình dạng tệp vào: đúng khoá `source_segments`, mọi khoá khác nguyên.

    Pipeline đọc transcript theo đúng khoá (`segments` vs `source_segments`) và
    dùng lại `model`/`configuration`/`inference_seconds` để báo cáo. Ghi ra một
    hình dạng khác là bước sau đọc sai trường, dù bản vá chữ đúng.
    """
    transcript = {
        "experiment": "smoke",
        "configuration": {"beam_size": 5},
        "source_segments": [{"start": 10.0, "end": 12.0, "text": "我去了燕台山"}],
    }
    transcript_path = tmp_path / "transcript.json"
    ocr_path = tmp_path / "ocr.json"
    out_path = tmp_path / "out.json"
    write_json(transcript_path, transcript)
    write_json(ocr_path, {"metadata": {"caption_observations": [
        {"i": 7, "start": 10.1, "end": 11.9, "ocr": "我去了烟台山"},
    ]}})

    code = cli.main(
        ["--transcript", str(transcript_path), "--ocr", str(ocr_path), "--out", str(out_path)],
        pinyin_fn=fake_pinyin,
        t2s_fn=no_t2s,
    )

    assert code == 0
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert list(written) == ["experiment", "configuration", "source_segments"]
    assert written["experiment"] == "smoke"
    assert written["configuration"] == {"beam_size": 5}
    assert written["source_segments"][0]["text"] == "我去了烟台山"
    assert "segments" not in written

    log_path = pathlib.Path(str(out_path) + ".patch-log.json")
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert set(log) == {"changes", "rejected", "stats"}
    assert log["stats"]["applied"] == 1
    assert log["changes"][0]["ocr_row_i"] == 7


def test_cli_exits_with_an_actionable_message_when_pypinyin_is_missing(
    tmp_path, monkeypatch, capsys
):
    """Thiếu `pypinyin` là lỗi CÀI ĐẶT: exit 2 kèm lệnh cài, không traceback.

    `pypinyin` là phụ thuộc ĐÁNH GIÁ, không thuộc app; người chạy máy khác rất dễ
    không có nó. Thông báo phải nói được cài gì, và phải nói nó KHÔNG thuộc
    requirements — nếu không sẽ có người thêm nó vào app.
    """
    transcript_path = tmp_path / "transcript.json"
    ocr_path = tmp_path / "ocr.json"
    write_json(transcript_path, {"segments": [asr_row(0, 0.0, 1.0, "我去了燕台山")]})
    write_json(ocr_path, {"metadata": {"caption_observations": [ocr_row(7, 0.0, 1.0, "我去了烟台山")]}})
    monkeypatch.setitem(sys.modules, "pypinyin", None)

    code = cli.main(
        ["--transcript", str(transcript_path), "--ocr", str(ocr_path),
         "--out", str(tmp_path / "out.json")],
        t2s_fn=no_t2s,
    )

    assert code == 2
    error = capsys.readouterr().err
    assert "pypinyin" in error
    assert "pip install pypinyin" in error
    assert "requirements" in error
    assert not (tmp_path / "out.json").exists()


def test_cli_exits_with_an_actionable_message_when_opencc_is_missing(
    tmp_path, monkeypatch, capsys
):
    """Thiếu `opencc` cũng là exit 2, và tên gói PyPI phải đúng.

    Import là `opencc` nhưng tên gói trên PyPI là `opencc-python-reimplemented`;
    ghi sai tên thì thông báo "hãy cài đi" lại là thứ không cài được.
    """
    transcript_path = tmp_path / "transcript.json"
    ocr_path = tmp_path / "ocr.json"
    write_json(transcript_path, {"segments": [asr_row(0, 0.0, 1.0, "我去了燕台山")]})
    write_json(ocr_path, {"metadata": {"caption_observations": [ocr_row(7, 0.0, 1.0, "我去了烟台山")]}})
    monkeypatch.setitem(sys.modules, "opencc", None)

    code = cli.main(
        ["--transcript", str(transcript_path), "--ocr", str(ocr_path),
         "--out", str(tmp_path / "out.json")],
        pinyin_fn=fake_pinyin,
    )

    assert code == 2
    error = capsys.readouterr().err
    assert "opencc" in error
    assert "opencc-python-reimplemented" in error
    assert not (tmp_path / "out.json").exists()


def test_cli_report_prints_each_changed_sentence(tmp_path, capsys):
    """`--report` in đúng dạng `i  start-end  TRƯỚC → SAU`.

    Báo cáo này là thứ người chạy đọc để quyết định có tin bản vá hay không; nó
    phải cho thấy cả câu trước và sau, chứ không chỉ "đã vá 6 chỗ".
    """
    transcript_path = tmp_path / "transcript.json"
    ocr_path = tmp_path / "ocr.json"
    out_path = tmp_path / "out.json"
    write_json(transcript_path, {"segments": [asr_row(4, 10.0, 12.0, "我去了燕台山")]})
    write_json(ocr_path, {"metadata": {"caption_observations": [
        {"i": 7, "start": 10.1, "end": 11.9, "ocr": "我去了烟台山"},
    ]}})

    code = cli.main(
        ["--transcript", str(transcript_path), "--ocr", str(ocr_path),
         "--out", str(out_path), "--report"],
        pinyin_fn=fake_pinyin,
        t2s_fn=no_t2s,
    )

    assert code == 0
    printed = capsys.readouterr().out
    assert re.search(
        r"^4  10\.00-12\.00  我去了燕台山 → 我去了烟台山$", printed, re.MULTILINE
    ), printed
