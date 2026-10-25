"""Test cho định dạng phụ đề (domain) và handler export (pipeline).

Hai nhóm lý do file này tồn tại:

  * R65 — ba bộ sinh trong brief không nhất quán cách tra bản dịch: `to_srt`
    tra theo VỊ TRÍ (`translations[n - 1]`), còn `to_vtt`/`to_ass` tra theo
    `seg.i`. Hai cách chỉ trùng nhau nhờ `normalize()` đánh số lại liên tục.
    `translations` là danh sách SONG SONG — `_assert_lengths` bảo đảm
    `len(translations) == len(segments)` — nên phải tra theo vị trí. Khi `i`
    không liên tục (ví dụ `i=[0,1,3]`) bản brief làm VTT/ASS mất một bản dịch
    trong khi SRT vẫn còn, và cùng một transcript cho ra phụ đề khác nhau tuỳ
    định dạng.

  * R66 — `app/pipeline/export.py` không được bài test nào import trong brief
    (chuỗi `pipeline.export` xuất hiện 0 lần), nên một lỗi cú pháp trong đó sẽ
    vô hình tới Task 15. Đây là task thứ ba liên tiếp có dạng này.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import NotFound, SqliteRepos
from app.domain.models import Job, Segment, Transcript
from app.domain.subtitle_format import (
    format_timestamp, to_ass, to_json, to_srt, to_vtt,
)
from app.pipeline.export import FORMATS, MEDIA_TYPES, ExportHandler, export_meta, render


# ---------------------------------------------------------------------------
# `to_json` — định dạng DUY NHẤT mang mốc thời gian của BẢN GỐC ra ngoài cùng bản
# dịch. Hình dạng đã chọn: mảng phẳng `segments[]` + khối `meta`. Các bài ở đây
# ghim HÌNH DẠNG đó (khoá nào, đơn vị nào, giây có làm tròn không) và ghim rằng
# thời gian đến từ BẢN GỐC, không phải từ bản dịch.
# ---------------------------------------------------------------------------

_JSON_SOURCE = [Segment(i=0, start=0.0, end=2.1, text="你好"),
                Segment(i=1, start=2.1, end=4.25, text="再见", suspect=True)]
_JSON_VI = ["Xin chào", "Tạm biệt"]


def test_json_has_meta_and_a_flat_segments_array():
    out = json.loads(to_json(_JSON_SOURCE, translations=_JSON_VI,
                             meta={"transcript_id": 1, "translation_id": 2}))
    assert set(out) == {"meta", "segments"}
    assert out["meta"] == {"transcript_id": 1, "translation_id": 2}
    assert [s["i"] for s in out["segments"]] == [0, 1]
    assert set(out["segments"][0]) == {
        "i", "start", "end", "start_timecode", "end_timecode",
        "text", "translation", "suspect", "qa",
    }


def test_json_times_come_from_the_source_segment_not_the_translation():
    """`start`/`end` là GIÂY của đoạn NGUỒN, KHÔNG làm tròn thêm.

    Phép đo phải phân biệt được nguồn với bản dịch, nên bản dịch ở đây mang mốc
    thời gian KHÁC hẳn (0/99) — lấy nhầm bên nào là đỏ ngay.
    """
    source = [Segment(i=7, start=1.5, end=2.75, text="甲")]
    translated = [Segment(i=7, start=0.0, end=99.0, text="Bản dịch")]
    out = json.loads(to_json(source, translations=[t.text for t in translated]))
    item = out["segments"][0]
    assert (item["start"], item["end"]) == (1.5, 2.75)
    assert item["start_timecode"] == "00:00:01.500"
    assert item["end_timecode"] == "00:00:02.750"
    assert item["text"] == "甲" and item["translation"] == "Bản dịch"


def test_json_keeps_vietnamese_and_han_as_utf8_not_escaped():
    """`ensure_ascii=False`: byte trong tệp là UTF-8 THẬT.

    `\\u1eeb` là cùng một JSON hợp lệ về ngữ nghĩa, nhưng nó biến một tệp người
    đọc được thành một tệp chỉ máy đọc được — và đó là thứ người dùng mở ra để
    kiểm bản dịch. Ghim trên CHUỖI thô, không chỉ trên `json.loads` (nếu không thì
    hai cách mã hoá là tương đương về ngữ nghĩa và bài này vô nghĩa).
    """
    raw = to_json(_JSON_SOURCE, translations=_JSON_VI)
    assert "Xin chào" in raw and "Tạm biệt" in raw
    assert "你好" in raw
    assert "\\u" not in raw, "không được escape sang \\uXXXX"


def test_json_marks_a_missing_translation_as_null():
    out = json.loads(to_json(_JSON_SOURCE))
    assert [s["translation"] for s in out["segments"]] == [None, None]


def test_json_carries_the_source_suspect_flag():
    out = json.loads(to_json(_JSON_SOURCE, translations=_JSON_VI))
    assert [s["suspect"] for s in out["segments"]] == [False, True]


def test_json_splits_qa_issues_by_segment_and_keeps_idless_ones_in_meta():
    """Issue CÓ `id` xuống đúng đoạn; issue KHÔNG có `id` ở lại `meta`.

    `engine_no_glossary` nói về ENGINE, không về một dòng — nhét nó vào một đoạn
    là bịa ra một vấn đề của dòng đó; nuốt nó đi là mất một cờ mà người dùng cần.
    """
    issues = ["engine_no_glossary", "cps:1=30.0>21.0", "lang:1=source:han5/latin0"]
    out = json.loads(to_json(_JSON_SOURCE, translations=_JSON_VI,
                             meta={"qa_issues": issues}))
    assert out["meta"]["qa_issues"] == issues
    assert out["segments"][0]["qa"] == []
    assert out["segments"][1]["qa"] == ["cps:1=30.0>21.0", "lang:1=source:han5/latin0"]


def test_json_rejects_a_translation_count_mismatch():
    with pytest.raises(ValueError):
        to_json(_JSON_SOURCE, translations=["chỉ một"])


def test_json_is_wired_into_the_one_format_registry():
    """`json` là định dạng THẬT của đường export: có media type, và `render` đi
    qua `to_json` (không qua một đường thứ hai)."""
    assert "json" in FORMATS and "json" in MEDIA_TYPES
    assert MEDIA_TYPES["json"] == "application/json"
    body = json.loads(render("json", _JSON_SOURCE, translations=_JSON_VI,
                             meta={"transcript_id": 9}))
    assert body["meta"]["transcript_id"] == 9
    assert len(body["segments"]) == 2


def test_meta_engine_is_null_when_there_is_no_translation_row():
    """Đường job không có hàng `translations` ⇒ `engine` là `null`, KHÔNG phải
    engine ASR của transcript: hai nghĩa khác nhau không được dùng chung một khoá."""
    transcript = Transcript(id=3, source_id=1, engine="fw-large-v3-turbo", lang="zh",
                            segments=[], version=2)
    meta = export_meta(transcript=transcript)
    assert meta["translation_id"] is None and meta["engine"] is None
    assert meta["stale"] is None, "chưa đo được KHÁC false"
    assert meta["transcript_version"] == 2


def test_timestamp_formatting_hours_and_millis():
    assert format_timestamp(0.0) == "00:00:00,000"
    assert format_timestamp(1.5) == "00:00:01,500"
    assert format_timestamp(3661.25) == "01:01:01,250"
    assert format_timestamp(1.5, sep=".") == "00:00:01.500"


def test_negative_timestamp_clamps_to_zero():
    assert format_timestamp(-3.0) == "00:00:00,000"


def test_srt_structure_and_indexing_from_one():
    segs = [Segment(i=0, start=1.0, end=2.5, text="甲"),
            Segment(i=1, start=2.5, end=4.0, text="乙")]
    out = to_srt(segs)
    lines = out.strip().splitlines()
    assert lines[0] == "1"
    assert lines[1] == "00:00:01,000 --> 00:00:02,500"
    assert lines[2] == "甲"
    assert lines[3] == ""
    assert lines[4] == "2"
    assert out.endswith("\n")


def test_srt_bilingual_puts_source_above_translation():
    segs = [Segment(i=0, start=0.0, end=2.0, text="大家好")]
    out = to_srt(segs, translations=["Chào mọi người"], bilingual=True)
    body = out.strip().splitlines()[2:]
    assert body[0] == "大家好"
    assert body[1] == "Chào mọi người"


def test_srt_monolingual_uses_translation_only():
    """Một đoạn -> ĐÚNG một dòng văn bản, không dư dòng nào.

    Không chỉ kiểm `"大家好" not in out`: nếu `_lines` trả về thêm một dòng rỗng
    thì khẳng định đó vẫn xanh, còn tệp SRT thật thì hỏng. Vì vậy ở đây so
    thẳng danh sách dòng với dạng đúng.
    """
    segs = [Segment(i=0, start=0.0, end=2.0, text="大家好")]
    out = to_srt(segs, translations=["Chào mọi người"], bilingual=False)
    assert "大家好" not in out
    assert out == (
        "1\n"
        "00:00:00,000 --> 00:00:02,000\n"
        "Chào mọi người\n"
    )
    assert out.splitlines()[2:] == ["Chào mọi người"]


def test_srt_translation_mismatch_length_raises():
    segs = [Segment(i=0, start=0.0, end=2.0, text="a"),
            Segment(i=1, start=2.0, end=4.0, text="b")]
    with pytest.raises(ValueError):
        to_srt(segs, translations=["chỉ một dòng"])


def test_vtt_has_header_and_dot_separator():
    out = to_vtt([Segment(i=0, start=0.0, end=1.0, text="x")])
    assert out.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.000" in out


def test_ass_has_script_info_and_dialogue_lines():
    segs = [Segment(i=0, start=0.0, end=1.0, text="x")]
    out = to_ass(segs)
    assert "[Script Info]" in out and "[V4+ Styles]" in out and "[Events]" in out
    assert "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,x" in out


def test_ass_escapes_braces_that_would_be_read_as_override_codes():
    segs = [Segment(i=0, start=0.0, end=1.0, text="a{b}c")]
    assert "a\\{b\\}c" in to_ass(segs)


def test_empty_segment_list_gives_valid_empty_documents():
    assert to_srt([]) == ""
    assert to_vtt([]).startswith("WEBVTT")
    assert "[Events]" in to_ass([])


# --------------------------------------------------------------------------
# R65: bản dịch là danh sách SONG SONG -> tra theo VỊ TRÍ, không theo `seg.i`
# --------------------------------------------------------------------------

def _non_contiguous() -> list[Segment]:
    """Ba đoạn có `i` KHÔNG liên tục — đúng thứ mà mọi fixture trong brief thiếu.

    `i=[0,1,3]` là trạng thái có thật: `update_transcript_segments` cho phép
    ghi lại segments đã sửa, và bất cứ bước nào xoá một đoạn ở giữa mà không
    đánh số lại sẽ để lại khoảng trống như thế này.
    """
    return [Segment(i=0, start=0.0, end=1.0, text="一"),
            Segment(i=1, start=1.0, end=2.0, text="二"),
            Segment(i=3, start=3.0, end=4.0, text="三")]


NON_CONTIGUOUS_TRANSLATIONS = ["một", "hai", "ba"]


def _srt_bodies(out: str) -> list[str]:
    """Các dòng VĂN BẢN của SRT, bóc theo VỊ TRÍ — không theo GIÁ TRỊ.

    Mỗi khối SRT là ba phần: `chỉ số`, `thời gian`, rồi các dòng văn bản, ngăn
    nhau bằng dòng rỗng. Bỏ hai dòng đầu của mỗi khối là đủ.

    EX-03 (F3/Task 14): bản cũ lọc `ln not in ("", "1", "2", "3")` — theo GIÁ
    TRỊ — nên nó nuốt luôn dòng VĂN BẢN có nội dung đúng bằng `"1"`/`"2"`/`"3"`.
    Với một fixture văn-bản-số, phép so bản dịch (R65) trở nên yếu đi mà không
    ai thấy: cùng một giá trị bị lọc ở cả hai vế thì một bản dịch rơi mất vẫn
    "bằng nhau".
    """
    bodies: list[str] = []
    for block in out.strip().split("\n\n"):
        bodies.extend(block.splitlines()[2:])
    return bodies


def _vtt_bodies(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln and ln != "WEBVTT" and "-->" not in ln]


def _ass_bodies(out: str) -> list[str]:
    """Trường Text (trường thứ 10) của mỗi dòng Dialogue.

    Không dùng `split(",,", 1)`: chuỗi `Default,,0,0,0,,` có HAI lần `,,` nên
    cách đó cắt ngay sau `Default` và trả về cả phần toạ độ. Trường Text là
    phần sau lần `,,` CUỐI CÙNG.
    """
    return [ln[ln.rindex(",,") + 2:] for ln in out.splitlines()
            if ln.startswith("Dialogue:")]


def test_all_three_formats_index_translations_by_position_not_by_seg_i():
    """Cùng một transcript + cùng một danh sách bản dịch -> cùng nội dung.

    Với bản brief (`translations[seg.i]`), đoạn `i=3` tra `translations[3]`;
    `3 < 3` sai nên nó rơi về `None` và VTT/ASS mất bản dịch "ba" trong khi SRT
    vẫn in. Test này khoá lại việc cả ba định dạng dùng CHUNG một cách tra.
    """
    segs = _non_contiguous()
    assert _srt_bodies(to_srt(segs, translations=NON_CONTIGUOUS_TRANSLATIONS)) == \
        NON_CONTIGUOUS_TRANSLATIONS
    assert _vtt_bodies(to_vtt(segs, translations=NON_CONTIGUOUS_TRANSLATIONS)) == \
        NON_CONTIGUOUS_TRANSLATIONS
    assert _ass_bodies(to_ass(segs, translations=NON_CONTIGUOUS_TRANSLATIONS)) == \
        NON_CONTIGUOUS_TRANSLATIONS


def test_bilingual_non_contiguous_keeps_every_pair_together():
    """Bản song ngữ: mỗi đoạn phải là (nguồn, dịch) của CÙNG một đoạn.

    ASS khác SRT/VTT ở đây: `_ass_escape` chạy SAU khi `_lines` đã nối hai dòng
    bằng `"\\N"`, nên dấu `\\` của dấu phân cách bị nhân đôi thành `"\\\\N"`.
    Đó là hành vi của bản brief (dòng 209-214) — test này ghi lại đúng như vậy
    thay vì sửa test cho khớp; xem báo cáo Task 14.
    """
    segs = _non_contiguous()
    assert _srt_bodies(
        to_srt(segs, translations=NON_CONTIGUOUS_TRANSLATIONS, bilingual=True)
    ) == ["一", "một", "二", "hai", "三", "ba"]
    assert _vtt_bodies(
        to_vtt(segs, translations=NON_CONTIGUOUS_TRANSLATIONS, bilingual=True)
    ) == ["一", "một", "二", "hai", "三", "ba"]
    # TODO(ASS-escape): separator phải là một \N
    assert _ass_bodies(
        to_ass(segs, translations=NON_CONTIGUOUS_TRANSLATIONS, bilingual=True)
    ) == ["一\\\\Nmột", "二\\\\Nhai", "三\\\\Nba"]


def test_srt_body_extraction_keeps_text_lines_that_look_like_indices():
    """EX-03 · bóc theo VỊ TRÍ: dòng văn bản đúng bằng "1"/"2" vẫn phải còn.

    Đây là chứng minh của lỗi: với `_srt_bodies` lọc theo giá trị, cả ba bản
    dịch số bị nuốt nên phép so R65 ở trên trở thành so hai danh sách rỗng.
    """
    segs = _non_contiguous()
    numeric = ["1", "2", "3"]

    assert _srt_bodies(to_srt(segs, translations=numeric)) == numeric
    # Song ngữ: dòng nguồn (chữ Hán) và dòng dịch (số) xen kẽ, đủ sáu dòng —
    # lọc theo giá trị chỉ còn ba dòng chữ Hán.
    assert _srt_bodies(
        to_srt(segs, translations=numeric, bilingual=True)
    ) == ["一", "1", "二", "2", "三", "3"]


# --------------------------------------------------------------------------
# R66: handler export — đường ghi tệp chưa từng được test chạm tới
# --------------------------------------------------------------------------

@pytest.fixture()
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


@pytest.fixture()
def transcript_id(repos):
    """Transcript THẬT trong sqlite, không phải đồ giả.

    `transcripts.source_id` có khoá ngoại thật, nên phải tạo source trước —
    đúng cách các test khác đang làm.
    """
    source_id = repos.add_source(kind="file", origin="a.mp4",
                                 media_path="m.mp4", lang="zh")
    return repos.add_transcript(
        source_id=source_id,
        engine="fw-large-v3-turbo",
        lang="zh",
        segments=_non_contiguous(),
    )


def _handler(repos, tmp_path):
    return ExportHandler(repos, out_dir=tmp_path / "out")


def _job(**payload) -> Job:
    return Job(id=None, workspace=3, type="export", engine=None, phase="export:-",
               payload=payload)


def test_handler_handles_export():
    assert ExportHandler(None, out_dir=".").handles() == "export"


def test_unsupported_format_names_the_supported_ones(repos, tmp_path, transcript_id):
    """Lỗi phải NÓI ĐƯỢC định dạng nào dùng được, không chỉ kêu 'sai'."""
    with pytest.raises(ValueError) as excinfo:
        _handler(repos, tmp_path).run(
            _job(transcript_id=transcript_id, format="docx"), lambda *_: None
        )
    message = str(excinfo.value)
    assert "docx" in message, message
    for supported in ("ass", "srt", "vtt"):
        assert supported in message, message


def test_translation_count_mismatch_raises(repos, tmp_path, transcript_id):
    with pytest.raises(ValueError, match="không khớp"):
        _handler(repos, tmp_path).run(
            _job(transcript_id=transcript_id, format="srt", translations=["chỉ một"]),
            lambda *_: None,
        )


def test_missing_transcript_surfaces_as_notfound(repos, tmp_path):
    """`get_transcript` ném `NotFound`; handler không được bọc nó thành
    `AttributeError` khó hiểu."""
    with pytest.raises(NotFound):
        _handler(repos, tmp_path).run(
            _job(transcript_id=999, format="srt"), lambda *_: None
        )


@pytest.mark.parametrize("fmt", ["srt", "vtt", "ass"])
def test_successful_run_matches_the_formatter_and_writes_utf8(
    repos, tmp_path, transcript_id, fmt
):
    """Bản SONG NGỮ: nội dung tệp phải khớp `bilingual=True`.

    Cố ý dùng `bilingual=True` chứ không phải mặc định: nếu chỉ chạy chế độ một
    ngôn ngữ thì một handler bỏ qua cờ `bilingual` trong payload vẫn cho ra tệp
    y hệt và test sẽ không nhìn thấy gì.
    """
    seen: list[float] = []
    _handler(repos, tmp_path).run(
        _job(transcript_id=transcript_id, format=fmt, stem="my-clip",
             translations=NON_CONTIGUOUS_TRANSLATIONS, bilingual=True),
        lambda fraction, _msg: seen.append(fraction),
    )
    target = tmp_path / "out" / f"my-clip.vi.{fmt}"
    assert target.is_file(), sorted(p.name for p in (tmp_path / "out").iterdir())

    raw = target.read_bytes()
    expected = {"srt": to_srt, "vtt": to_vtt, "ass": to_ass}[fmt](
        _non_contiguous(), translations=NON_CONTIGUOUS_TRANSLATIONS, bilingual=True
    )
    # UTF-8 thật, không phải mã hoá mặc định của hệ điều hành.
    raw.decode("utf-8")
    assert raw.startswith(b"\xef\xbb\xbf") is False
    assert raw == expected.encode("utf-8")
    # Chế độ song ngữ thật sự có cả nguồn lẫn bản dịch, đúng thứ tự từng cặp.
    bodies = {"srt": _srt_bodies, "vtt": _vtt_bodies, "ass": _ass_bodies}[fmt](expected)
    if fmt == "ass":
        # TODO(ASS-escape): separator phải là một \N
        assert bodies == ["一\\\\Nmột", "二\\\\Nhai", "三\\\\Nba"]
    else:
        assert bodies == ["一", "một", "二", "hai", "三", "ba"]
    assert seen[0] == pytest.approx(0.3) and seen[-1] == 1.0


def test_sidecar_index_is_written_next_to_the_subtitle(repos, tmp_path, transcript_id):
    handler = _handler(repos, tmp_path)
    handler.run(_job(transcript_id=transcript_id, format="srt", stem="my-clip"),
                lambda *_: None)
    index = tmp_path / "out" / "my-clip.srt.json"
    assert index.is_file()
    data = json.loads(index.read_text(encoding="utf-8"))
    assert data["transcript_id"] == transcript_id
    assert data["format"] == "srt"
    assert data["bilingual"] is False
    assert data["segments"] == 3
    assert data["engine"] == "fw-large-v3-turbo"


def test_sidecar_carries_the_stored_transcript_version(repos, tmp_path, transcript_id):
    """Không phải `1` mặc định: ta sửa transcript để version thành 2 rồi mới
    export, nên sidecar phải khớp hàng đã lưu."""
    new_version = repos.update_transcript_segments(transcript_id, _non_contiguous())
    assert new_version == 2, "fixture: bản sửa đầu tiên phải đẩy version lên 2"
    stored = repos.get_transcript(transcript_id)
    assert stored.version == 2

    _handler(repos, tmp_path).run(
        _job(transcript_id=transcript_id, format="vtt", stem="my-clip"), lambda *_: None
    )
    data = json.loads(
        (tmp_path / "out" / "my-clip.vtt.json").read_text(encoding="utf-8")
    )
    assert data["transcript_version"] == stored.version == 2


def test_vi_suffix_only_when_translations_are_supplied(repos, tmp_path, transcript_id):
    handler = _handler(repos, tmp_path)
    handler.run(_job(transcript_id=transcript_id, format="srt", stem="with-tr",
                     translations=NON_CONTIGUOUS_TRANSLATIONS), lambda *_: None)
    handler.run(_job(transcript_id=transcript_id, format="srt", stem="without-tr"),
                lambda *_: None)
    names = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert "with-tr.vi.srt" in names
    assert "without-tr.srt" in names
    assert "without-tr.vi.srt" not in names


def test_default_stem_is_transcript_id(repos, tmp_path, transcript_id):
    _handler(repos, tmp_path).run(
        _job(transcript_id=transcript_id, format="srt"), lambda *_: None
    )
    assert (tmp_path / "out" / f"transcript-{transcript_id}.srt").is_file()


def test_export_stem_cannot_escape_the_output_directory(repos, tmp_path, transcript_id):
    """R76: `stem` do payload job gửi tới phải được cắt thành TÊN TRẦN.

    `out_dir` ở đây là `tmp_path/out`, nên `out_dir / f"../thoat-ra-ngoai.{fmt}"`
    ghi thẳng ra `tmp_path` — ngoài thư mục xuất, và tệp `.json` đi theo. Không
    cắt thì hai khẳng định dưới đỏ.
    """
    _handler(repos, tmp_path).run(
        _job(transcript_id=transcript_id, format="srt", stem="../thoat-ra-ngoai"),
        lambda *_: None,
    )

    assert (tmp_path / "out" / "thoat-ra-ngoai.srt").is_file(), (
        sorted(p.name for p in (tmp_path / "out").iterdir())
    )
    assert (tmp_path / "out" / "thoat-ra-ngoai.srt.json").is_file()
    assert not (tmp_path / "thoat-ra-ngoai.srt").exists(), "thoát ra ngoài thư mục xuất"
    assert not (tmp_path / "thoat-ra-ngoai.srt.json").exists()


def test_export_rejects_a_stem_that_is_only_dotdot(repos, tmp_path, transcript_id):
    """`..` không phải tên tệp: phải hỏng ồn ào, không ghi ra thư mục cha."""
    with pytest.raises(ValueError, match="tên tệp"):
        _handler(repos, tmp_path).run(
            _job(transcript_id=transcript_id, format="srt", stem=".."),
            lambda *_: None,
        )


def test_missing_transcript_id_is_an_actionable_error(repos, tmp_path):
    """EX-04 (F4/Task 14): job thiếu `transcript_id` ⇒ `ValueError` NÊU TÊN KHOÁ.

    Bản cũ đi thẳng vào `int(payload["transcript_id"])` nên ném
    `KeyError: 'transcript_id'` trần từ tận worker — không nói được job thiếu
    gì, và không phải lớp lỗi hành động được (cùng họ F2 của Task 12).
    """
    with pytest.raises(ValueError, match="thiếu transcript_id"):
        _handler(repos, tmp_path).run(_job(format="srt"), lambda *_: None)


def test_missing_transcript_id_is_reported_before_the_format_is_checked(repos, tmp_path):
    """Payload vừa THIẾU id vừa SAI định dạng: lỗi phải nêu đúng thứ đang thiếu.

    Thứ tự validate không được để ca này nổi lên thành "định dạng không hỗ trợ"
    (hay thành `KeyError`): sửa định dạng xong job vẫn chết vì thiếu id, nên
    thông báo phải chỉ thẳng vào `transcript_id` ngay từ lần chạy đầu.
    """
    with pytest.raises(ValueError, match="thiếu transcript_id"):
        _handler(repos, tmp_path).run(_job(format="docx"), lambda *_: None)


def test_empty_stem_falls_back_instead_of_raising(repos, tmp_path, transcript_id):
    """DOC-09 (N6): `stem=""` là falsy nên handler đổi thành `None` TRƯỚC khi
    gọi `safe_basename`, tức lùi về `transcript-<id>`; đưa thẳng `""` vào
    `safe_basename` thì ném `InvalidBasename`.

    Cùng một giá trị `""` đi hai đường khác nhau là CỐ Ý (giữ ngữ nghĩa
    `payload.get("stem") or ...` cũ): route upload từ chối `""` của client bằng
    422 (`test_upload_answers_422_for_an_empty_filename`), còn export ở đây lùi
    về tên mặc định. "Sửa" một trong hai cho giống nhau mà không đọc hợp đồng ở
    `safe_basename` sẽ làm đỏ một trong hai test.
    """
    _handler(repos, tmp_path).run(
        _job(transcript_id=transcript_id, format="srt", stem=""), lambda *_: None
    )
    assert (tmp_path / "out" / f"transcript-{transcript_id}.srt").is_file(), (
        sorted(p.name for p in (tmp_path / "out").iterdir())
    )
