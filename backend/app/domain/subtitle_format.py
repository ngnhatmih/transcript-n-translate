"""Sinh SRT / VTT / ASS / JSON. Thuần, không phụ thuộc gì.

Đặt ở domain vì đây là logic nghiệp vụ và phải test được mà không cần model,
không cần đĩa, không cần mạng.

Bất biến: `translations` là danh sách SONG SONG với `segments` —
`_assert_lengths` bảo đảm `len(translations) == len(segments)`. Vì vậy CẢ BỐN
định dạng tra bản dịch theo VỊ TRÍ (`enumerate`), không theo `seg.i`.

Tra theo `seg.i` là sai một cách âm thầm: `normalize()` đánh số lại liên tục
nên `seg.i == vị trí` trong thực tế, và hai cách chỉ trùng nhau NHỜ MAY. Khi
`i` có khoảng trống (`i=[0,1,3]` sau khi xoá một đoạn ở giữa mà không đánh số
lại), `translations[3]` vượt biên và bản dịch biến mất — cùng một transcript
cho ra phụ đề khác nhau tuỳ định dạng.

`to_json` là định dạng DUY NHẤT mang mốc thời gian của BẢN GỐC ra ngoài cùng bản
dịch dưới dạng MÁY đọc được: ba định dạng phụ đề kia chỉ có một dòng chữ, nên
muốn ghép lại bản gốc với bản dịch thì phải parse phụ đề. Xem docstring của nó để
biết chính xác các khoá và đơn vị thời gian.
"""
from __future__ import annotations

import json
import re

from .models import Segment


def format_timestamp(seconds: float, *, sep: str = ",") -> str:
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def _ass_timestamp(seconds: float) -> str:
    total_cs = int(round(max(0.0, seconds) * 100))
    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, centis = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _assert_lengths(segments: list[Segment], translations: list[str] | None) -> None:
    if translations is not None and len(translations) != len(segments):
        raise ValueError(
            f"số bản dịch ({len(translations)}) khác số đoạn ({len(segments)})"
        )


def _lines(seg: Segment, translated: str | None, bilingual: bool) -> list[str]:
    if translated is None:
        return [seg.text]
    return [seg.text, translated] if bilingual else [translated]


def to_srt(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False) -> str:
    _assert_lengths(segments, translations)
    if not segments:
        return ""
    blocks: list[str] = []
    for n, seg in enumerate(segments, start=1):
        translated = translations[n - 1] if translations is not None else None
        body = "\n".join(_lines(seg, translated, bilingual))
        blocks.append(
            f"{n}\n"
            f"{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n"
            f"{body}"
        )
    return "\n\n".join(blocks) + "\n"


def to_vtt(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False) -> str:
    _assert_lengths(segments, translations)
    out = ["WEBVTT", ""]
    for position, seg in enumerate(segments):
        translated = translations[position] if translations is not None else None
        out.append(
            f"{format_timestamp(seg.start, sep='.')} --> {format_timestamp(seg.end, sep='.')}"
        )
        out.extend(_lines(seg, translated, bilingual))
        out.append("")
    return "\n".join(out) + "\n"


_ASS_HEADER = """[Script Info]
Title: {title}
ScriptType: v4.00+
WrapStyle: {wrap}
ScaledBorderAndShadow: yes
PlayResX: {rx}
PlayResY: {ry}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Archivo,{co},&H00DCE4E8,&H0000B0FF,&H00201F1E,&H80000000,0,0,0,0,100,100,0,0,1,{vien},1,2,{le},{le},{duoi},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

#: Hệ toạ độ MẶC ĐỊNH của `.ass` — giữ nguyên từng byte so với bản trước khi có `khung`.
#:
#: 🔴 VÌ SAO PHẢI THAM SỐ HOÁ (đo được, không phải phòng xa): `PlayRes` là hệ toạ độ mà
#: libass dùng để ĐẶT chữ và tính lề, rồi nó CO GIÃN cả hệ đó theo khung hình thật. Video
#: trong repo là **dọc 1080×1920**, còn hằng cũ khai **ngang 1920×1080** — hai hệ lệch
#: nhau 3,56× theo một trục và 0,56× theo trục kia. Đo được trên `dub-1.mp4` (1080×1920,
#: 278,5 s): chữ Việt burn đúng nhưng **TRÀN RA NGOÀI khung** — dòng dài nhất trong bản
#: dịch #1 là **693 ký tự** (`Bố! Bố! …`), và với `MarginL/R` 60 px tính theo hệ 1920
#: thì lề thật chỉ còn ~34 px trên khung 1080. Cắt chữ ở hai đầu mép là đúng thứ bị cấm.
#:
#: `WrapStyle: 2` (hằng cũ) nghĩa là "không tự xuống dòng, chỉ xuống ở `\N`" — nên một
#: dòng 693 ký tự KHÔNG được bẻ. `WrapStyle: 0` để libass tự bẻ theo lề.
_ASS_KHUNG_MAC_DINH = {"rx": 1920, "ry": 1080, "co": 54, "vien": 2, "le": 60,
                       "duoi": 48, "wrap": 2}


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def to_ass(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False, title: str = "phu-de-lab",
           khung: tuple[int, int] | None = None) -> str:
    """Sinh `.ass`. `khung=(rong, cao)` là kích thước VIDEO THẬT mà chữ sẽ nằm lên.

    `khung=None` giữ nguyên hệ `1920×1080` từng byte — đường xuất tệp rời không biết
    video nào, và đổi mặc định là đổi kết quả của mọi lượt xuất cũ mà không ai yêu cầu.

    Có `khung` thì hệ toạ độ, cỡ chữ, viền và lề đều được suy theo khung đó:
      · `PlayResX/Y` = khung thật, nên libass KHÔNG co giãn chữ;
      · cỡ chữ và lề tính theo TỈ LỆ so với hệ 1920×1080 gốc (cùng một tỉ lệ cho cả hai
        trục, lấy trục NGẮN hơn làm chuẩn — chữ phải vừa cả hai chiều);
      · `WrapStyle: 0` để libass TỰ BẺ dòng theo lề, thay vì để một dòng 693 ký tự tràn
        ra ngoài mép (đo được, xem `_ASS_KHUNG_MAC_DINH`).
    """
    _assert_lengths(segments, translations)
    tham_so = dict(_ASS_KHUNG_MAC_DINH)
    if khung is not None:
        rong, cao = int(khung[0]), int(khung[1])
        if rong > 0 and cao > 0:
            # Tỉ lệ theo trục NGẮN: khung dọc 1080×1920 có trục ngắn 1080, nên chữ nhỏ
            # lại đúng bằng 1080/1920 so với hệ gốc — vừa bề ngang, không tràn.
            ti_le = min(rong / 1920, cao / 1080)
            tham_so.update(
                rx=rong, ry=cao, wrap=0,
                co=max(12, round(_ASS_KHUNG_MAC_DINH["co"] * ti_le)),
                vien=max(1, round(_ASS_KHUNG_MAC_DINH["vien"] * ti_le)),
                le=max(8, round(_ASS_KHUNG_MAC_DINH["le"] * ti_le)),
                duoi=max(8, round(_ASS_KHUNG_MAC_DINH["duoi"] * ti_le)),
            )
    lines = [_ASS_HEADER.format(title=title, **tham_so)]
    for position, seg in enumerate(segments):
        translated = translations[position] if translations is not None else None
        parts = _lines(seg, translated, bilingual)
        text = _ass_escape("\\N".join(parts))
        lines.append(
            f"Dialogue: 0,{_ass_timestamp(seg.start)},{_ass_timestamp(seg.end)},"
            f"Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


#: Tiền tố issue có kèm `id` của đoạn: `cps:12=…`, `length:3=…`, `empty:5`,
#: `lang:8=…`, `missing_term:9=…`. Cờ `engine_no_glossary` KHÔNG có id (nó nói về
#: engine, không về một dòng) nên nó ở lại `meta.qa_issues` và không xuống đoạn nào.
_QA_WITH_ID = re.compile(r"^[a-z_]+:(\d+)")


def _qa_by_segment(issues: list[str]) -> dict[int, list[str]]:
    """Chia `qa_issues` (danh sách phẳng) về theo `id` của đoạn.

    Vì sao đọc `id` từ CHUỖI thay vì tính lại QA ở đây: `translations.qa_issues`
    là thứ đã được ghi và đã hiện cho người dùng (màn Đối chiếu đọc CPS từ route
    khác, nhưng cùng nguồn). Tính lại QA trong đường export là nguồn thứ hai, và
    hai nguồn thì trôi khỏi nhau. Cái giá là phải parse chuỗi — nhưng tiền tố và
    dấu `:` là HỢP ĐỒNG grep được đã tuyên bố ở `mt_qa.py` (và `engine_no_glossary`
    không có `id` chính là ca chứng minh phép parse phải chấp nhận "không khớp").
    """
    by_id: dict[int, list[str]] = {}
    for issue in issues:
        match = _QA_WITH_ID.match(issue)
        if match is not None:
            by_id.setdefault(int(match.group(1)), []).append(issue)
    return by_id


def to_json(segments: list[Segment], *, translations: list[str] | None = None,
            meta: dict | None = None) -> str:
    """JSON hai thứ tiếng: MỖI đoạn có mốc thời gian của BẢN GỐC + nguồn + dịch.

    Hình dạng đã CHỌN (khai ra đây, và ghim bằng test — không phải một chi tiết
    ngẫu nhiên): một MẢNG PHẲNG `segments[]` cộng một khối `meta`, KHÔNG phải khối
    song ngữ lồng nhau. Lý do: người tiêu thụ (script, CAT tool, spreadsheet) đi
    theo `i`/thời gian, và một mảng phẳng thì `jq '.segments[]'` là đủ.

    Khoá của mỗi mục:

    * `i` — id đoạn, ĐÚNG giá trị của bản gốc;
    * `start`/`end` — GIÂY, **KHÔNG làm tròn thêm** ở đây: đây là chính giá trị
      của đoạn NGUỒN (transcript), không phải của bản dịch;
    * `start_timecode`/`end_timecode` — `HH:MM:SS.mmm` (giống VTT), và đây là chỗ
      DUY NHẤT có làm tròn: `format_timestamp` làm tròn tới mili giây;
    * `text` — câu NGUỒN; `translation` — bản dịch, `null` khi bản xuất không kèm
      bản dịch (đường cũ không truyền `translations`);
    * `suspect` — cờ nghi ngờ của đoạn NGUỒN (ASR); `qa` — các issue CỦA RIÊNG
      đoạn này (lọc từ `meta.qa_issues` theo `id`, cộng `seg.qa` nếu có).

    `meta` do bên gọi dựng (`pipeline/export.py::export_meta`) và được đặt NGUYÊN
    vào `meta` của tệp: hàm này không biết gì về bảng `translations`, nên nó
    không thể bịa ra `translation_id`/`engine`/`prompt_version`.

    `bilingual` KHÔNG phải tham số: định dạng này LUÔN có cả nguồn lẫn bản dịch —
    đó chính là lý do nó tồn tại. Một cờ "có/không nguồn" ở đây sẽ tạo ra hai
    hình dạng JSON cho cùng một định dạng, tức là hai hợp đồng.

    `ensure_ascii=False`: tiếng Việt và chữ Hán ra UTF-8 THẬT, không thành
    `\\u1eeb`. Tệp được ghi qua `_write_utf8` với `newline="\\n"` như mọi định
    dạng khác, nên byte trên đĩa và byte trong HTTP body khớp nhau.
    """
    _assert_lengths(segments, translations)
    header = dict(meta or {})
    qa_by_id = _qa_by_segment(list(header.get("qa_issues") or []))
    out: list[dict] = []
    for position, seg in enumerate(segments):
        qa: list[str] = []
        for item in [*qa_by_id.get(seg.i, []), *seg.qa]:
            if item not in qa:          # `seg.qa` có thể chứa lại chính issue đó
                qa.append(item)
        out.append({
            "i": seg.i,
            "start": seg.start,
            "end": seg.end,
            "start_timecode": format_timestamp(seg.start, sep="."),
            "end_timecode": format_timestamp(seg.end, sep="."),
            "text": seg.text,
            "translation": None if translations is None else translations[position],
            "suspect": bool(seg.suspect),
            "qa": qa,
        })
    return json.dumps({"meta": header, "segments": out},
                      ensure_ascii=False, indent=2) + "\n"
