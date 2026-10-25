"""Hợp đồng của `scripts/mine_ocr_glossary.py` (vòng 3: gate core).

Script này đào bảng vá nguồn từ reference OCR v4, và thứ nó sinh ra sẽ được dùng
để SỬA CHỮ NGUỒN trước khi dịch. Vì vậy mỗi quy tắc ở đây có hai phía: phía "phải
bắt được" (một tên riêng bị nghe nhầm thì mất hẳn nếu bỏ sót) và phía "tuyệt đối
không được bắt" (một phép đổi số liệu hay một lần đổi hệ chữ mà lọt vào bảng thì
translator được dạy sửa số/sửa hệ chữ, sai theo kiểu không ai truy được).

Ba vòng siết, mỗi vòng có bài riêng ở dưới:

* t2s (OpenCC) trước khi canh — dòng 87 của reference là phồn thể, không t2s thì
  `个`/`個` và `区`/`區` thành "cặp nghe nhầm".
* cửa sổ neo — `阴台山`/`烟台山` chỉ lệch một âm tiết trên ba, nhưng so ở cửa sổ
  MỘT âm tiết thì `yin` ≠ `yan` và cặp tốt nhất của cả reference bị mất.
* gate core — cửa sổ neo cứu MỌI khác biệt một chữ trong ngữ cảnh, kể cả `是`/`就`
  (`shi`/`jiu`); nên core phải gần đồng âm (> 0,5) và cửa sổ chỉ được có MỘT
  `replace`. Cặp bị loại vẫn phải đọc được: nó nằm trong `dropped`.
* patchability — cặp một chữ không bao giờ được duyệt, vì thay một chữ phổ thông
  là thay nó ở mọi chỗ trong transcript.

Không bài nào cần `pypinyin`/`opencc` thật, không bài nào chạm mạng/GPU: hàm đào
nhận `pinyin_fn` và `t2s_fn` như tham số, các bài dưới bơm bản GIẢ. Hai bài CLI
thì chặn gói bằng `sys.modules` (đặt `None`) để kiểm đúng thông báo cài đặt mà
không cần gỡ gói khỏi venv.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import sys

import scripts.mine_ocr_glossary as mine

#: Bảng âm tiết giả: mỗi chữ Hán một âm tiết, chữ không có trong bảng trả về
#: chính nó — đúng hành vi `errors="default"` của `lazy_pinyin`, nên hình dạng dữ
#: liệu mà bộ lọc nhìn thấy giống bản thật.
SYLLABLES = {
    "燕": "yan",
    "煙": "yan",
    "烟": "yan",
    "台": "tai",
    "臺": "tai",
    "山": "shan",
    "阴": "yin",
    "草": "cao",
    "曹": "cao",
    "垒": "lei",
    "磊": "lei",
    "指": "zhi",
    "纸": "zhi",
    "缘": "yuan",
    "鸢": "yuan",
    "拉": "la",
    "彩": "cai",
    "踩": "cai",
    "扇": "shan",
    "汕": "shan",
    "头": "tou",
    "螺": "luo",
    "垫": "dian",
    "钿": "dian",
    "夜": "ye",
    "业": "ye",
    "钩": "gou",
    "勾": "gou",
    "香": "xiang",
    "想": "xiang",
    "个": "ge",
    "個": "ge",
    "区": "qu",
    "區": "qu",
    # Gate core: các cặp mà tỉ lệ pinyin quyết định số phận candidate.
    "长": "zhang",
    "展": "zhan",
    "看": "kan",
    "的": "de",
    "都": "dou",
    "了": "le",
    "人": "ren",
    "是": "shi",
    "就": "jiu",
    "诶": "ei",
    "哎": "ai",
    "那": "na",
    "弄": "nong",
    "我": "wo",
    "画": "hua",
    "有": "you",
    "来": "lai",
    "本": "ben",
    "搓": "cuo",
    "找": "zhao",
}

#: t2s giả: chỉ đúng hai cặp chữ mà dòng 87 của reference cần, để bài t2s không
#: phải cài OpenCC thật mà vẫn đo được đúng hành vi "chuẩn hoá TRƯỚC khi canh".
FAKE_T2S = {"個": "个", "區": "区"}


def fake_pinyin(text: str) -> list[str]:
    return [SYLLABLES.get(char, char) for char in text]


def fake_t2s(text: str) -> str:
    return "".join(FAKE_T2S.get(char, char) for char in text)


def _document(rows, excluded=()):
    return {
        "dataset_id": "fake-reference",
        "version": 4,
        "metadata": {"caption_observations": list(rows)},
        "excluded_observations": list(excluded),
    }


def _mine(document, t2s_fn=None):
    """Chỉ lấy candidates; cặp bị gate core loại xem bằng `_mine_both`."""
    return _mine_all(document, t2s_fn)[0]


def _mine_all(document, t2s_fn=None):
    """`(candidates, dropped, rejected)` — cả ba danh sách của sổ ghi vết."""
    return mine.mine_candidates(mine.collect_rows(document, t2s_fn), fake_pinyin, t2s_fn)


def _mine_both(document, t2s_fn=None):
    candidates, dropped, _ = _mine_all(document, t2s_fn)
    return candidates, dropped


def _replace_opcodes(document, t2s_fn=None):
    """Canh LẠI từ đầu để lấy mẫu số — KHÔNG dùng vòng lặp của `mine_candidates`.

    Đây là chỗ bài kiểm không được tự xác nhận chính nó: nếu mẫu số lấy từ code
    đang bị kiểm thì một opcode bị bỏ sót ở cả hai phía sẽ vẫn cho bài kiểm xanh.
    """
    opcodes = []
    for row in mine.collect_rows(document, t2s_fn):
        matcher = difflib.SequenceMatcher(
            None, row["asr_norm"], row["ocr_norm"], autojunk=False
        )
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "replace":
                continue
            opcodes.append((row["i"], row["asr_norm"][i1:i2], row["ocr_norm"][j1:j2]))
    return opcodes


def _row(i, asr, ocr, split="dev", **extra):
    return {"i": i, "asr": asr, "ocr": ocr, "evaluation_split": split, **extra}


def test_homophone_mishear_is_high_when_the_correct_form_is_corroborated():
    """`草垒 -> 曹磊`: dạng đúng xuất hiện ở dòng THỨ HAI ⇒ high + approved.

    Hình dạng chuẩn của một cặp tốt: ASR nghe nhầm một tên riêng, OCR ghi đúng,
    dạng đúng còn xuất hiện độc lập ở dòng khác. Dòng thứ hai cố ý có `asr == ocr`
    để nó KHÔNG sinh ra cặp nào — nó chỉ làm chứng.

    Cặp này dài 2 chữ nên KHÔNG có cửa sổ neo (`anchor: false`, `narrow_*` null):
    neo chỉ dựng khi một vế chưa đủ 2 âm tiết, và bịa thêm ngữ cảnh cho một cặp đã
    đủ nghĩa là tự làm nhiễu bảng.
    """
    document = _document(
        [
            _row(77, "也可以看到草垒的鱼灯", "也可以看到曹磊的鱼灯", split="test"),
            _row(80, "曹磊说这个鱼灯", "曹磊说这个鱼灯", split="test"),
        ]
    )

    entries = _mine(document)

    assert len(entries) == 1
    entry = entries[0]
    assert (entry["wrong"], entry["correct"]) == ("草垒", "曹磊")
    assert entry["confidence"] == "high"
    assert entry["approved"] is True
    assert entry["patchable"] is True
    assert entry["anchor"] is False
    assert entry["narrow_wrong"] is None and entry["narrow_correct"] is None
    assert entry["occurrences"] == 1
    assert entry["correct_form_rows"] == 2
    # `曹磊` xuất hiện ở ocr dòng 77, cả asr lẫn ocr dòng 80.
    assert entry["corpus_frequency"] == {"correct": 3, "wrong": 1}
    assert entry["rare_form"] is True
    assert entry["reason"] == "correct form corroborated by 2 rows"
    assert entry["rows"] == [{"i": 77, "split": "test", "verification_status": None}]


def test_single_unverified_row_is_low_but_still_patchable():
    """Một dòng, không `frame_checked_*`, không ai làm chứng ⇒ low, approved false.

    `patchable` vẫn là `true` — hai khái niệm khác nhau, và bài này ghim đúng chỗ
    chúng tách nhau: cặp này VÁ ĐƯỢC (2 chữ) nhưng chưa ĐÁNG TIN, nên không được
    duyệt. Gộp hai thứ đó lại là mở đường cho một lỗi OCR đi thẳng vào bản dịch.

    Dòng giả ở đây là dòng 12 của reference thật, nguyên hình dạng: ASR `指缘`,
    OCR `纸鸢` nằm giữa hai dấu 《》 (dấu ngoặc là `insert`, không sinh cặp).
    """
    entries = _mine(_document([_row(12, "这是小儿放指缘图", "这是《小儿放纸鸢图》")]))

    assert len(entries) == 1
    entry = entries[0]
    assert (entry["wrong"], entry["correct"]) == ("指缘", "纸鸢")
    assert entry["confidence"] == "low"
    assert entry["approved"] is False
    assert entry["patchable"] is True
    assert entry["anchor"] is False
    assert entry["reason"] == "single unverified row; not corroborated"


def test_a_frame_checked_row_is_high_without_any_corroboration():
    """`verification_status = frame_checked_no_edit` ⇒ high một mình.

    Nguồn tin thứ nhất trong ba nguồn của quy tắc tin cậy: dòng đã được người soi
    frame xác nhận là đúng, nên nó không cần dòng thứ hai làm chứng.
    """
    entries = _mine(
        _document(
            [
                _row(
                    77,
                    "也可以看到草垒的鱼灯",
                    "也可以看到曹磊的鱼灯",
                    verification_status="frame_checked_no_edit",
                )
            ]
        )
    )

    assert len(entries) == 1
    entry = entries[0]
    assert (entry["wrong"], entry["correct"]) == ("草垒", "曹磊")
    assert entry["confidence"] == "high"
    assert entry["approved"] is True
    assert entry["reason"] == "frame-checked row in reference"
    assert entry["rows"][0]["verification_status"] == "frame_checked_no_edit"


def test_single_character_pair_can_be_high_but_is_never_approved():
    """Cặp MỘT chữ: `high` được, `approved` thì không (luật patchability).

    `燕 -> 烟` có bằng chứng mạnh (dạng đúng ở 2 dòng ⇒ `high`), nhưng vá một chữ
    phổ thông là thay nó ở MỌI chỗ trong transcript chứ không riêng chỗ nghe nhầm.
    Vì vậy `approved: false`, `patchable: false`, và `reason` phải nói rõ
    `single_character_not_patchable` — để người đọc không tưởng nó bị loại vì yếu
    bằng chứng.

    Dòng giả cố ý NGẮN (mỗi vế một chữ) để cửa sổ neo không mở được: đây là hình
    dạng mà luật một-chữ là lớp bảo vệ cuối cùng.
    """
    entries = _mine(_document([_row(1, "燕", "烟"), _row(2, "烟", "烟", split="test")]))

    assert len(entries) == 1
    entry = entries[0]
    assert (entry["wrong"], entry["correct"]) == ("燕", "烟")
    assert entry["confidence"] == "high"
    assert entry["patchable"] is False
    assert entry["approved"] is False
    assert "single_character_not_patchable" in entry["reason"]
    assert entry["correct_form_rows"] == 2


def test_anchor_window_rescues_the_near_homophone_place_name():
    """`阴台山 -> 烟台山`: cửa sổ neo cứu cặp tốt nhất của cả reference.

    `阴` (yīn) và `烟` (yān) khác nguyên âm, nên ở cửa sổ MỘT âm tiết cặp này bị
    quy tắc "1:1 âm tiết phải bằng nhau" loại. Ở cửa sổ 3 âm tiết, `yin tai shan`
    và `yan tai shan` khớp 2/3 = 0,67 > 0,5 nên qua — và vì `烟台山` còn xuất hiện
    ở dòng 53, cặp này thành `high` + `approved`. Đây chính là cặp mà bản vòng 1
    bỏ sót.
    """
    document = _document(
        [
            _row(90, "来阴台山吧", "来烟台山吧", split="test"),
            _row(53, "福州烟台山的市场负责人", "福州烟台山的市场负责人", split="test"),
        ]
    )

    entries = _mine(document)

    assert len(entries) == 1
    entry = entries[0]
    assert (entry["wrong"], entry["correct"]) == ("阴台山", "烟台山")
    assert entry["anchor"] is True
    assert (entry["narrow_wrong"], entry["narrow_correct"]) == ("阴", "烟")
    assert entry["confidence"] == "high"
    assert entry["approved"] is True
    assert entry["correct_form_rows"] == 2
    assert entry["reason"].endswith("context window around 阴 -> 烟")
    # 3 lần trong corpus: ocr dòng 90, asr dòng 53, ocr dòng 53.
    assert entry["corpus_frequency"]["correct"] == 3
    assert entry["corpus_frequency"]["wrong"] == 1


def test_anchor_extends_left_when_the_mishearing_is_the_tail_of_a_word():
    """`拉彩 -> 拉踩`: chữ bên trái là hình vị NỘI DUNG ⇒ neo mở sang TRÁI.

    `彩` một âm tiết; mở sang trái một chữ được `拉彩`/`拉踩` (2 âm tiết, khớp
    1,0). Mở sang phải thì được `彩的` — dính trợ từ `的`, đúng loại cửa sổ mà
    `STOP_CHARS` tồn tại để tránh. Cặp này low (một dòng), nhưng `patchable` và
    `narrow_*` phải đúng: nếu neo làm mất cặp hẹp thì không ai truy được vì sao nó
    ra `拉踩` chứ không phải `踩`.
    """
    entries = _mine(_document([_row(41, "经常通过拉彩的方式", "经常通过拉踩的方式")]))

    assert len(entries) == 1
    entry = entries[0]
    assert (entry["wrong"], entry["correct"]) == ("拉彩", "拉踩")
    assert entry["anchor"] is True
    assert (entry["narrow_wrong"], entry["narrow_correct"]) == ("彩", "踩")
    assert entry["confidence"] == "low"
    assert entry["approved"] is False
    assert entry["patchable"] is True


def test_t2s_removes_script_variant_pairs_and_no_t2s_brings_them_back():
    """t2s phải chạy TRƯỚC `SequenceMatcher`, không phải sau.

    Dòng 87 của reference thật là phồn thể (`在整個街區藏了很多個‘福’`) trong khi
    ASR là giản thể. Canh trên chữ phồn thì mọi `replace` ở dòng đó là "nghe nhầm"
    giả, và bảng dạy translator đổi hệ chữ — đúng thứ `scoring_normalization` của
    reference (OpenCC t2s) tồn tại để tránh. Bài kiểm cả hai chiều: BẬT thì không
    còn cặp nào, TẮT thì `個` và `區` quay lại.
    """
    document = _document(
        [
            _row(87, "藏了很多个福", "藏了很多個福", split="test"),
            _row(88, "整个街区", "整個街區", split="test"),
        ]
    )

    assert _mine(document, fake_t2s) == []

    without_t2s = _mine(document)
    corrects = [entry["correct"] for entry in without_t2s]
    assert any("個" in correct for correct in corrects), corrects
    assert any("區" in correct for correct in corrects), corrects


def test_pair_rejection_names_the_script_variant_rule():
    """Luật t2s phải có ĐÚNG MỘT chỗ cài đặt, và chỗ đó trả về tên quy tắc.

    Khi `collect_rows` đã t2s hai vế thì nhánh này không bắn; nó vẫn phải đúng khi
    được gọi trên chuỗi thô — nếu ai đó đổi thứ tự chuẩn hoá, đây là chỗ duy nhất
    còn nhớ rằng `个`/`個` không phải nghe nhầm.
    """
    assert mine.pair_rejection("个", "個", fake_pinyin) is None
    assert mine.pair_rejection("个", "個", fake_pinyin, fake_t2s) == "script_variant"
    assert mine.pair_rejection("区", "區", fake_pinyin, fake_t2s) == "script_variant"


def test_digit_quantity_row_produces_no_pair():
    """`一瓶是2000` / `一平尺2,000` KHÔNG được sinh cặp.

    Đây là số liệu bị chuẩn hoá khác nhau, không phải nghe nhầm. Bằng chứng đo
    được: cặp CHUỖI ĐẦY ĐỦ bị quy tắc độ dài loại trước (6 vs 9 ký tự); cặp mà
    bộ canh thật sự dựng lên từ dòng giả này (`瓶是 -> 平尺`) bị quy tắc đồng âm
    loại vì khớp ĐÚNG 0,5 còn ngưỡng là `> 0,5` — đó là lý do ngưỡng phải chặt
    hơn đúng một chút. Quy tắc chữ số được ghim riêng ngay dưới, trên một cặp vừa
    đủ ngắn để đi qua quy tắc độ dài.
    """
    entries = _mine(_document([_row(13, "一瓶是2000", "一平尺2,000")]))

    assert entries == []
    assert mine.pair_rejection("一瓶是2000", "一平尺2,000", fake_pinyin) == "length"
    assert mine.pair_rejection("瓶是", "平尺", fake_pinyin) == "not_homophone"
    assert mine.pair_rejection("2000", "2,000", fake_pinyin) == "digits_or_symbols"


def test_symbol_row_produces_no_pair():
    """`加宽乘系数` / `（+宽）x系数` KHÔNG được sinh cặp.

    Cặp chuỗi đầy đủ bị độ dài loại (5 vs 7); cặp mà bộ canh dựng lên từ dòng giả
    `i` = 6 (`成细 -> (+宽)x系`, đúng hình dạng của dòng 6 trong reference thật:
    ASR `成细数`, OCR `（+宽）x系数`) bị quy tắc ký hiệu loại. Đó là lý do tồn tại
    của quy tắc đó: dấu ngoặc và dấu cộng là dấu câu của reference, không phải chữ
    bị nghe nhầm.
    """
    entries = _mine(_document([_row(6, "成细数", "（+宽）x系数")]))

    assert entries == []
    assert mine.pair_rejection("加宽乘系数", "（+宽）x系数", fake_pinyin) == "length"
    assert mine.pair_rejection("成细", "(+宽)x系", fake_pinyin) == "digits_or_symbols"
    assert mine.pair_rejection("乘", ")x", fake_pinyin) == "digits_or_symbols"


def test_placeholder_empty_and_watermark_rows_are_skipped():
    """Ba loại dòng không dùng được phải bị bỏ TRƯỚC khi canh.

    Watermark là thứ nguy hiểm nhất trong ba loại: nó là chữ trên màn hình
    (`想想工作室 bilibili`), và nếu lọt qua thì ASR đọc lời thoại sẽ bị ghép với
    tên kênh. Dòng watermark ở đây cố ý chứa một cặp đồng âm thật (`香 -> 想`)
    để nếu bộ lọc watermark hỏng thì bài này đỏ vì CÓ cặp, chứ không phải xanh
    một cách tình cờ.
    """
    document = _document(
        [
            _row(0, "作为一个搞艺术", "作为一个搞艺术的"),
            _row(1, "最苦恼的事就是", "..."),
            _row(2, "诶我说", "…"),
            _row(3, "某句", ""),
            _row(4, "某句", "   "),
            _row(93, "香香工作室", "想想工作室 bilibili"),
            _row(96, "某句", "想法工作室"),
            _row(97, "某句", "BILIBILI"),
        ]
    )

    rows = mine.collect_rows(document, fake_t2s)

    assert [row["i"] for row in rows] == [0]
    assert _mine(document, fake_t2s) == []


def test_pair_is_keyed_by_i_not_by_array_position():
    """Dòng thú vị nằm ở VỊ TRÍ 2 nhưng mang `i = 57`.

    Reference thật lệch như vậy (vị trí 26 giữ `i` = 29, vị trí 57 giữ `i` = 62)
    vì ba dòng `i` = 1, 2, 7 bị loại khỏi nửa chấm điểm. Bám theo vị trí mảng là
    ghi sai danh tính dòng, và nhãn `split` đi kèm cũng sẽ trỏ sang nửa khác —
    đúng thứ mà nhãn này tồn tại để chặn (không ai được chấm ASR bằng một bảng
    đào từ nửa test).
    """
    document = _document(
        [
            _row(4, "这值几个钱", "这值几个钱", split="dev"),
            _row(6, "能值多少钱", "能值多少钱", split="dev"),
            # Vị trí mảng = 2, `i` = 57: đúng hình dạng của reference thật.
            _row(57, "来草垒钓鱼吧", "来曹磊钓鱼吧", split="test"),
        ]
    )

    entries = _mine(document)

    assert len(entries) == 1
    assert entries[0]["wrong"] == "草垒"
    assert entries[0]["rows"][0]["i"] == 57
    assert entries[0]["rows"][0]["split"] == "test"


def test_reference_text_comes_from_ocr_and_never_from_source_ocr():
    """`ocr` là bản có hiệu lực; `source_ocr` là bản đã bị sửa.

    Dòng 82 của reference thật là ca rõ nhất: `source_ocr` ghi `榕树女孩`, `ocr`
    ghi `榕树女神` (sửa từ frame). Bản giả dưới đây dựng đúng hình dạng đó với một
    cặp đồng âm: nếu code đọc `source_ocr` thì nó so ASR với chính nó và KHÔNG ra
    cặp nào — nên bài này kiểm cả hai chiều, có và không.
    """
    document = _document([_row(82, "找草垒", "找曹磊", source_ocr="找草垒")])

    entries = _mine(document)
    assert [(entry["wrong"], entry["correct"]) for entry in entries] == [
        ("草垒", "曹磊")
    ]

    # Chiều ngược lại: nếu reference trỏ về `source_ocr` (tức là bản SAI) thì
    # không có cặp nào — bằng chứng rằng cặp ở trên đến từ `ocr`.
    regression = {"i": 82, "asr": "找草垒", "ocr": "找草垒", "source_ocr": "找草垒"}
    assert _mine(_document([regression])) == []


def test_min_confidence_high_drops_the_unapproved_pairs():
    """`--min-confidence high` chỉ còn cặp đã duyệt — nó không đổi `approved`.

    Cờ này là bộ lọc ĐẦU RA, không phải một lần chấm điểm thứ hai: cặp low vẫn
    `approved: false` và biến mất, chứ không bị nâng lên cho vừa cờ.
    """
    entries = [
        {"wrong": "阴台山", "correct": "烟台山", "confidence": "high", "approved": True},
        {"wrong": "草垒", "correct": "曹磊", "confidence": "low", "approved": False},
    ]

    assert [entry["correct"] for entry in mine.filter_by_confidence(entries, "low")] == [
        "烟台山",
        "曹磊",
    ]
    kept = mine.filter_by_confidence(entries, "high")
    assert [entry["correct"] for entry in kept] == ["烟台山"]
    assert kept[0]["approved"] is True


def test_output_header_carries_provenance_the_policy_and_the_t2s_state():
    """Header phải tự nói nó đã chuẩn hoá bằng gì.

    Cùng một reference, `--no-t2s` cho ra danh sách KHÁC (có `个 -> 個`), nên một
    tệp đầu ra không ghi rõ t2s bật hay tắt là một tệp không tái lập được. Chuỗi
    `translation_policy` cũng là hợp đồng với bước sau: tên riêng đọc Hán-Việt,
    tiêu đề tác phẩm đọc nghĩa + Hán-Việt (kèm ghi chú rằng bước kiểm chuỗi khớp
    phần trong ngoặc), thuật ngữ thông dụng và tiếng lóng đọc nghĩa, và mọi
    `Term.translation` vẫn để trống chờ người điền.
    """
    document = _document([_row(90, "来阴台山吧", "来烟台山吧", split="test")])

    with_t2s = mine.build_output(document, b'{"version": 4}', [], [], [], True)
    without_t2s = mine.build_output(document, b'{"version": 4}', [], [], [], False)

    assert with_t2s["reference"]["sha256"] == hashlib.sha256(b'{"version": 4}').hexdigest()
    assert with_t2s["generated_by"] == "scripts/mine_ocr_glossary.py"
    assert with_t2s["normalization"].endswith("OpenCC t2s")
    assert "t2s" not in without_t2s["normalization"]
    policy = with_t2s["translation_policy"]
    assert "Sino-Vietnamese reading (string check matches the parenthetical)" in policy
    assert "common terms and slang -> meaning" in policy
    assert policy.endswith(
        'every Term.translation stays "<VI: dien sau>" until a human fills it'
    )


def test_cli_exits_with_an_actionable_message_when_pypinyin_is_missing(
    monkeypatch, tmp_path, capsys
):
    """Thiếu `pypinyin` thì phải thoát KHÁC 0 kèm lệnh cài, không được traceback.

    Người chạy gặp `ModuleNotFoundError` giữa lúc đào không biết đó là phụ thuộc
    đánh giá hay app hỏng. Ở đây `pypinyin` bị chặn bằng `sys.modules` (đặt
    `None`), nên bài không cần gỡ gói khỏi venv và vẫn chạy được trên máy đã cài.
    """
    monkeypatch.setitem(sys.modules, "pypinyin", None)
    reference = tmp_path / "reference.json"
    reference.write_text(
        json.dumps(_document([_row(62, "这是燕台山", "这是烟台山")])),
        encoding="utf-8",
    )
    output = tmp_path / "out" / "candidates.json"

    code = mine.main(["--reference", str(reference), "--output", str(output)])

    captured = capsys.readouterr()
    assert code == 2
    assert "pip install pypinyin" in captured.err
    assert output.exists() is False, "thiếu gói thì không được ghi tệp dở dang"


def test_cli_exits_with_an_actionable_message_when_opencc_is_missing(
    monkeypatch, tmp_path, capsys
):
    """Thiếu `opencc` cũng phải thoát KHÁC 0, kèm đường lùi rõ ràng.

    t2s là chuẩn hoá mặc định từ vòng 2, nên máy thiếu `opencc` sẽ không chạy được
    script nếu không có chỉ dẫn. Thông báo phải nêu cả lệnh cài LẪN `--no-t2s`
    (đường lùi có ý thức, không phải im lặng bỏ qua bước chuẩn hoá). `mine._OPENCC`
    được đặt lại `None` để bài không phụ thuộc việc converter đã được nạp bởi bài
    khác trong cùng tiến trình.
    """
    monkeypatch.setitem(sys.modules, "opencc", None)
    monkeypatch.setattr(mine, "_OPENCC", None)
    reference = tmp_path / "reference.json"
    reference.write_text(
        json.dumps(_document([_row(90, "来阴台山吧", "来烟台山吧")])),
        encoding="utf-8",
    )
    output = tmp_path / "candidates.json"

    code = mine.main(
        ["--reference", str(reference), "--output", str(output)], pinyin_fn=fake_pinyin
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "opencc-python-reimplemented" in captured.err
    assert "--no-t2s" in captured.err
    assert output.exists() is False


def test_core_gate_keeps_the_near_homophone_cores():
    """Core 0,667 (`阴/烟`) và 0,889 (`长/展`) PHẢI qua; ngưỡng là `> 0,5`.

    Đây là hai cặp mà gate core không được phép giết, và cả hai đều là lỗi nghe
    nhầm thật của một thuật ngữ: `烟台山` là địa danh, `看展` là "đi xem triển
    lãm" — ASR nghe `长` (zhǎng) thành `展` (zhǎn) chỉ lệch đúng một phụ âm cuối.
    Tỉ lệ được ghim thành SỐ, không phải "khác rỗng": đổi ngưỡng hay đổi cách nối
    âm tiết là bài này đỏ ngay.
    """
    place = _mine(
        _document(
            [
                _row(90, "来阴台山吧", "来烟台山吧", split="test"),
                _row(53, "福州烟台山的市场负责人", "福州烟台山的市场负责人"),
            ]
        )
    )
    assert [(entry["wrong"], entry["correct"]) for entry in place] == [
        ("阴台山", "烟台山")
    ]
    assert place[0]["core_pinyin_ratio"] == 0.667
    assert place[0]["narrow_core"] == {"wrong": "阴", "correct": "烟"}
    assert place[0]["approved"] is True

    term = _mine(_document([_row(50, "而且看长的都是路人", "而且看展的都是路人")]))
    assert [(entry["wrong"], entry["correct"]) for entry in term] == [
        ("长的都", "展的都")
    ]
    assert term[0]["core_pinyin_ratio"] == 0.889
    assert term[0]["narrow_core"] == {"wrong": "长", "correct": "展"}


def test_core_gate_drops_a_window_that_swallows_two_replaces():
    """`了→人` + `垫→钿` trong cùng cửa sổ ⇒ `multiple_cores`, không phải một bản vá.

    Dòng 20 của reference thật: `找了螺垫搓字` / `找人螺钿搓字`. Cặp ĐÚNG là
    `螺钿 <- 螺垫` (mở trái từ `垫`, cửa sổ chỉ có một `replace`). Cặp SAI là
    `人螺钿 <- 了螺垫`: cửa sổ mở phải từ `了` nuốt luôn `垫→钿`, tức hai chỗ lệch
    — chỉ một trong hai có thể là nghe nhầm, nên cả cửa sổ không phải một bản vá.
    Bài kiểm cả hai chiều trên CÙNG một dòng: cặp đúng nằm trong `candidates`, cặp
    sai nằm trong `dropped` kèm `core_count: 2`.
    """
    candidates, dropped = _mine_both(
        _document([_row(20, "找了螺垫搓字", "找人螺钿搓字")])
    )

    assert [(entry["wrong"], entry["correct"]) for entry in candidates] == [
        ("螺垫", "螺钿")
    ]
    assert len(dropped) == 1
    entry = dropped[0]
    assert (entry["wrong"], entry["correct"]) == ("了螺垫", "人螺钿")
    assert entry["reason"] == "multiple_cores"
    assert entry["core_count"] == 2
    assert entry["narrow_core"] == {"wrong": "了", "correct": "人"}
    assert entry["core_pinyin_ratio"] == 0.4
    assert entry["rows"][0]["i"] == 20


def test_core_gate_drops_a_core_that_is_not_a_homophone():
    """`是/就` (0,333) và `诶/哎` (đúng 0,500) ⇒ `core_not_homophone`.

    Hai ca này là lý do gate core tồn tại. `是`/`就` không liên quan gì tới nghe
    nhầm (`本来是有的` vs `本来就有的` là khác biệt ngữ pháp), nhưng cửa sổ ba âm
    tiết vẫn khớp 0,67 nên cửa sổ một mình không chặn được. `诶`/`哎` (`ei`/`ai`)
    khớp ĐÚNG 0,5 và bị chặn bởi ngưỡng `> 0,5` — cùng một quyết định với
    `瓶值/平尺`, nên bài này ghim luôn rằng ngưỡng không được nới thành `>=`.
    """
    candidates, dropped = _mine_both(
        _document(
            [
                _row(39, "临摹了个本来是有的东西", "临摹了个本来就有的东西"),
                _row(2, "诶我说", "哎我说", split=None),
            ]
        )
    )

    assert candidates == []
    by_pair = {(entry["wrong"], entry["correct"]): entry for entry in dropped}
    assert set(by_pair) == {("是有的", "就有的"), ("诶我说", "哎我说")}
    assert by_pair[("是有的", "就有的")]["reason"] == "core_not_homophone"
    assert by_pair[("是有的", "就有的")]["core_pinyin_ratio"] == 0.333
    assert by_pair[("诶我说", "哎我说")]["reason"] == "core_not_homophone"
    assert by_pair[("诶我说", "哎我说")]["core_pinyin_ratio"] == 0.5
    assert by_pair[("诶我说", "哎我说")]["rows"][0]["split"] is None


def test_dropped_pairs_are_written_beside_candidates_and_never_inside_them():
    """`dropped` là danh sách RIÊNG trong tệp, không lẫn vào `candidates`.

    Dòng 3 của reference thật (`那我画上了赔了` / `弄我画上了！`) là ca đáng chú ý:
    dòng đó `frame_checked_no_edit`, tức bằng chứng mạnh, NHƯNG `那`/`弄`
    (`na`/`nong`) khớp 0,333 — đây là sửa-theo-hình chứ không phải nghe nhầm, nên
    nó nằm ngoài phạm vi của một glossary ĐỒNG ÂM. Bằng chứng mạnh không được phép
    vượt gate core. Bài cũng kiểm `build_output` giữ hai danh sách tách nhau: trộn
    chúng lại là mời người sau vá nhầm.
    """
    document = _document(
        [
            _row(90, "来阴台山吧", "来烟台山吧", split="test"),
            _row(53, "福州烟台山的市场负责人", "福州烟台山的市场负责人"),
            _row(3, "那我画上了赔了", "弄我画上了！", verification_status="frame_checked_no_edit"),
        ]
    )

    candidates, dropped, rejected = _mine_all(document)

    assert [entry["correct"] for entry in candidates] == ["烟台山"]
    assert [entry["correct"] for entry in dropped] == ["弄我画"]
    assert dropped[0]["reason"] == "core_not_homophone"
    assert dropped[0]["rows"][0]["verification_status"] == "frame_checked_no_edit"
    # Dòng 3 còn một opcode nữa (`赔了 -> ！`) và nó phải nằm trong sổ `rejected`,
    # không được biến mất. NFKC đã đổi `！` toàn khổ thành `!` — ghim đúng chữ mà
    # chuỗi đã chuẩn hoá mang.
    assert [(entry["wrong"], entry["correct"]) for entry in rejected] == [("赔了", "!")]

    output = mine.build_output(document, b"{}", candidates, dropped, rejected, True)
    assert output["candidates"] == candidates
    assert output["dropped"] == dropped
    assert output["rejected"] == rejected
    assert all(entry["correct"] != "弄我画" for entry in output["candidates"])


def test_every_replace_opcode_is_accounted_for_exactly_once():
    """BẤT BIẾN: mỗi opcode `replace` xuất hiện ĐÚNG MỘT LẦN trong hợp ba danh sách.

    Mẫu số được canh LẠI từ đầu (`_replace_opcodes`), không lấy từ
    `mine_candidates`: nếu lấy chung thì một opcode bị bỏ sót ở cả hai phía vẫn
    cho bài kiểm xanh — đúng kiểu test tự xác nhận chính nó.

    Đơn vị giải trình của một entry là `(i, narrow_core)`: đó là thứ định danh một
    opcode (một dòng có thể có nhiều opcode, và hai opcode có thể cùng một dòng).
    Dòng thứ hai của cùng một cặp đã được entry đầu phát rồi thì phải nằm trong
    `rejected` với `merged_duplicate`.
    """
    document = _document(
        [
            _row(77, "也可以看到草垒的鱼灯", "也可以看到曹磊的鱼灯", split="test"),
            _row(80, "草垒说这个鱼灯", "曹磊说这个鱼灯", split="test"),
            _row(20, "找了螺垫搓字", "找人螺钿搓字"),
            _row(2, "诶我说", "哎我说", split=None),
            _row(13, "一瓶是2000", "一平尺2,000"),
            _row(3, "那我画上了赔了", "弄我画上了！"),
        ]
    )

    candidates, dropped, rejected = _mine_all(document)
    expected = _replace_opcodes(document)

    accounted = []
    for entry in candidates + dropped:
        # Entry đã phát chỉ giải trình cho dòng ĐẦU (dòng nhỏ nhất); các dòng còn
        # lại của cùng cặp nằm trong `rejected` dưới dạng `merged_duplicate`.
        accounted.append(
            (entry["rows"][0]["i"], entry["narrow_core"]["wrong"],
             entry["narrow_core"]["correct"])
        )
    for entry in rejected:
        accounted.append(
            (entry["i"], entry["narrow_core"]["wrong"], entry["narrow_core"]["correct"])
        )

    assert len(candidates) + len(dropped) + len(rejected) == len(expected)
    assert sorted(accounted) == sorted(expected)
    # Không có opcode nào được giải trình hai lần.
    assert len(set(accounted)) == len(accounted)


def test_rejected_ledger_names_the_rule_that_dropped_the_pair():
    """`rejected` phải mang đúng TÊN quy tắc, không phải một cờ "không đạt".

    Hai ca đại diện cho hai lớp bị loại khác hẳn nhau: `瓶值 -> 平尺` là số liệu bị
    chuẩn hoá lại (`not_homophone`, vì `ping zhi` vs `ping chi` khớp đúng 0,5) và
    `成细 -> (+宽)x系` là dấu câu của reference (`digits_or_symbols`). Không có
    danh sách này thì cả hai chỉ là "không thấy trong bảng" — không phân biệt được
    với "chưa bao giờ được xét".
    """
    document = _document(
        [
            _row(13, "一瓶是2000", "一平尺2,000"),
            _row(6, "成细数", "（+宽）x系数", split="test"),
        ]
    )

    candidates, dropped, rejected = _mine_all(document)

    assert candidates == [] and dropped == []
    # `rejected` xếp theo `i` để đọc như một sổ, không theo thứ tự bị loại.
    # (Dòng 13 thật trong reference là `一瓶值2000`; bản giả ở đây viết `一瓶是2000`
    # nên cặp hẹp là `瓶是 -> 平尺` — cùng hình dạng, cùng lý do bị loại.)
    assert [
        (entry["i"], entry["wrong"], entry["correct"], entry["reason"], entry["split"])
        for entry in rejected
    ] == [
        (6, "成细", "(+宽)x系", "digits_or_symbols", "test"),
        (13, "瓶是", "平尺", "not_homophone", "dev"),
    ]
    assert all(entry["merged_into"] is None for entry in rejected)
    assert all(isinstance(entry["ratio"], float) for entry in rejected)


def test_a_repeated_pair_is_recorded_as_merged_duplicate():
    """Cùng một cặp ở dòng thứ hai: entry đã phát rồi, không đẻ thêm entry thứ hai.

    Không ghi vết ca này là mất một opcode: `candidates` chỉ có MỘT entry cho cặp
    `草垒 -> 曹磊` (dù `occurrences` = 2, vì đó là bằng chứng tin cậy), nên opcode
    ở dòng 80 phải hiện ra ở `rejected` với `merged_duplicate` và trỏ về dòng đã
    phát. `occurrences` vẫn phải là 2 — sổ ghi vết không được làm mất bằng chứng.
    """
    document = _document(
        [
            _row(77, "也可以看到草垒的鱼灯", "也可以看到曹磊的鱼灯", split="test"),
            _row(80, "草垒说这个鱼灯", "曹磊说这个鱼灯", split="test"),
        ]
    )

    candidates, dropped, rejected = _mine_all(document)

    assert len(candidates) == 1
    assert candidates[0]["occurrences"] == 2
    assert [row["i"] for row in candidates[0]["rows"]] == [77, 80]
    assert dropped == []
    assert len(rejected) == 1
    entry = rejected[0]
    assert entry["reason"] == "merged_duplicate"
    assert entry["i"] == 80
    assert (entry["wrong"], entry["correct"]) == ("草垒", "曹磊")
    assert entry["merged_into"] == {"i": 77, "where": "candidates"}


def test_dropped_pairs_are_not_listed_again_in_rejected():
    """Entry đã nằm trong `dropped` thì KHÔNG được lặp lại trong `rejected`.

    Hai danh sách đó trả lời hai câu khác nhau ("bị gate core loại" và "bị quy tắc
    lọc loại"), và tổng của ba danh sách phải bằng số opcode — lặp lại một entry là
    đếm hai lần cho một opcode.
    """
    document = _document([_row(2, "诶我说", "哎我说", split=None)])

    candidates, dropped, rejected = _mine_all(document)

    assert candidates == []
    assert [(entry["wrong"], entry["correct"]) for entry in dropped] == [("诶我说", "哎我说")]
    assert rejected == []
