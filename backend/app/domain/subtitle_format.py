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
Style: Default,{font},{co},{mau_chu},{mau_chu},&H00000000,{mau_hop},{dam},{nghieng},0,0,100,100,0,0,{kieu_vien},{vien},{bong},{can_le},{le},{le},{duoi},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

#: Màu chữ mặc định: TRẮNG đục (`&HAABBGGRR`, alpha 00 = đục hoàn toàn).
#:
#: 🔴 VÌ SAO ĐỔI (yêu cầu trực tiếp của chủ dự án): bản cũ dùng `&H00DCE4E8` — xám
#: ngả xanh, và nó CHÌM vào nền video. Trên video có phụ đề Trung cứng màu trắng
#: viền đen, chữ xám của ta không tách được khỏi lớp chữ có sẵn. Trắng + hộp đen
#: là cấu hình DUY NHẤT đọc được trên mọi nền, và đó là thứ được yêu cầu.
_ASS_MAU_CHU = "&H00FFFFFF"

#: Nền hộp: ĐEN, hơi trong (`&HAABBGGRR`, alpha AA = 170/255 ≈ 67 % đục) để vẫn
#: thấy hình phía sau nhưng đủ tương phản với chữ trắng.
_ASS_MAU_HOP = "&HA0000000"

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
#:
#: `kieu_vien`/`dam`/`nghieng`/`bong`/`can_le` vào đây để `.ass` không còn trường nào
#: viết cứng trong template: hộp đen + chữ trắng là lựa chọn của người dùng, không phải
#: hằng số của định dạng.
_ASS_KHUNG_MAC_DINH = {"rx": 1920, "ry": 1080, "co": 54, "vien": 2, "le": 60,
                       "duoi": 48, "wrap": 2,
                       # `BorderStyle: 3` = hộp đục phía sau chữ (kiểu "opaque box"),
                       # thay cho `1` = chỉ viền quanh nét chữ.
                       "kieu_vien": 3, "dam": 0, "nghieng": 0, "bong": 0, "can_le": 2,
                       # Font phai co o CA HAI noi: image burn (`fc-match`) va trinh duyet.
                       # DO DUOC truoc khi sua: container khong co Archivo nen chữ burn
                       # ra DejaVu Sans, lech han so voi ban xem truoc.
                       "font": "Archivo",
                       "mau_chu": _ASS_MAU_CHU, "mau_hop": _ASS_MAU_HOP}

#: Dịch khối chữ XUỐNG bao nhiêu, tính theo tỉ lệ chiều cao khung.
#:
#: 🔴 VÌ SAO CẦN (yêu cầu trực tiếp, có lý do đo được): video nguồn đã có PHỤ ĐỀ TRUNG
#: CỨNG burn trong pixel ở khoảng 1/8 dưới khung. Chữ Việt đặt đúng đáy (Alignment 2,
#: `MarginV` 48) nằm CHỒNG LÊN lớp chữ đó, và hai lớp chữ khác màu/mực chồng nhau thì
#: không đọc được cái nào. Đẩy khối chữ ta xuống dưới lớp chữ gốc làm nó CHE LẤP lớp cũ
#: — hộp đen đục che hẳn, chữ trắng của ta nằm trên. `MarginV` = 0 đặt sát đáy khung.
#:
#: 0.06 là mức đã đo: với khung 1080×1920, `duoi` = 48 → đáy chữ cách mép dưới 48 px
#: (hệ 1920×1080 quy đổi). Hạ thêm 6 % chiều cao (115 px trên 1920) đủ để hộp đen phủ
#: lên dòng phụ đề cứng mà không bị cắt mép dưới.
_ASS_OFFSET_DOC_MAC_DINH = 0.06



def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


#: Khoá `style` được phép ghi đè. Danh sách TRẮNG, không phải danh sách đen: `style` đi
#: từ HTTP xuống đây, nên khoá lạ phải bị BỎ chứ không được chèn vào `tham_so`. Chèn bừa
#: thì một khoá như `rx` sẽ đổi hệ toạ độ và làm chữ tràn khung — đúng thứ
#: `_ASS_KHUNG_MAC_DINH` sinh ra để chặn.
#: Font duoc phep chon — CHI nhung font co o CA image burn (fontconfig) VA trinh duyet.
#: Them mot ten vao day ma khong cai font vao image la burn ra font khac ban xem truoc.
FONT_CHO_PHEP = ("Archivo", "IBM Plex Mono")

_ASS_STYLE_CHO_PHEP = ("co", "vien", "le", "duoi", "kieu_vien", "dam", "nghieng",
                       "bong", "can_le", "mau_chu", "mau_hop")


def _mau_ass(mau: str, *, do_duc: float | None = None) -> str:
    """Đổi màu sang `&HAABBGGRR` của ASS.

    Nhận HAI dạng, vì hai đầu gửi hai dạng khác nhau: `#RRGGBB`/`#RRGGBBAA` (CSS, giao
    diện dùng) và `&HAABBGGRR` (ASS, đã đúng thì giữ nguyên).

    🔴 `Alpha` của ASS NGƯỢC với CSS: `00` = ĐỤC hoàn toàn, `FF` = trong suốt. Đây là chỗ
    dễ sai nhất khi map màu, nên phép đảo nằm ở đúng một dòng và ghim bằng test.
    """
    s = str(mau).strip()
    if s.startswith("&H") or s.startswith("&h"):
        return s.upper().replace("&H", "&H", 1)
    if not s.startswith("#") or len(s) not in (7, 9):
        raise ValueError(f"màu phải là '#RRGGBB', '#RRGGBBAA' hoặc '&HAABBGGRR', đo được {mau!r}")
    try:
        r, g, b = int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16)
        a_css = int(s[7:9], 16) if len(s) == 9 else 255
    except ValueError as exc:
        raise ValueError(f"màu không phải hex hợp lệ: {mau!r}") from exc
    if do_duc is not None:
        a_css = round(min(max(float(do_duc), 0.0), 1.0) * 255)
    a_ass = 255 - a_css
    return f"&H{a_ass:02X}{b:02X}{g:02X}{r:02X}"


def _style_ass(style: dict) -> dict:
    """Chuẩn hoá `style` từ ngoài thành các khoá của `_ASS_KHUNG_MAC_DINH`.

    Kẹp mọi số vào khoảng hợp lệ thay vì ném lỗi: một cỡ chữ 5 px hay 900 px vẫn phải ra
    một tệp ĐỌC ĐƯỢC, không phải một job hỏng. Riêng màu sai định dạng thì ném —
    im lặng đổi sang màu khác là giấu lỗi của người gọi.
    """
    ra: dict = {}
    #: Chi nhan font CO THAT o ca image burn lan trinh duyet. Font la khai niem cua MOI
    #: TRUONG, khong phai cua mot khoa JSON, nen nhan bua mot ten la burn ra font khac.
    if "font" in style and str(style["font"]) in FONT_CHO_PHEP:
        ra["font"] = str(style["font"])
    if "mau_chu" in style:
        ra["mau_chu"] = _mau_ass(style["mau_chu"])
    if "mau_hop" in style:
        ra["mau_hop"] = _mau_ass(style["mau_hop"], do_duc=style.get("do_duc_hop"))
    for khoa, thap, cao_ in (("co", 8, 400), ("vien", 0, 20), ("le", 0, 500),
                             ("duoi", 0, 500)):
        if khoa in style:
            ra[khoa] = min(max(int(style[khoa]), thap), cao_)
    if "kieu_vien" in style:
        ra["kieu_vien"] = 3 if int(style["kieu_vien"]) == 3 else 1
    for khoa in ("dam", "nghieng", "bong"):
        if khoa in style:
            ra[khoa] = -1 if style[khoa] else 0
    if "can_le" in style:
        ra["can_le"] = min(max(int(style["can_le"]), 1), 9)
    return ra


#: File font trong IMAGE BURN — phải khớp `_style_ass`/`FONT_CHO_PHEP`.
_FONT_CHO_DUONG = {
    "Archivo": "/usr/share/fonts/truetype/archivo/Archivo.ttf",
    "IBM Plex Mono": "/usr/share/fonts/truetype/archivo/IBMPlexMono-Regular.ttf",
}


def _do_rong_chu(chu: str, font: str, co: int) -> int:
    """Bề rộng chữ, tính bằng PIXEL của hệ `PlayRes`, theo ĐÚNG file font sẽ burn.

    `0` = KHÔNG ĐO ĐƯỢC (máy chạy test không có `/usr/share/fonts/...`, hoặc thiếu
    Pillow). Bên gọi phải coi `0` là "bỏ hộp vector", KHÔNG phải "hộp rộng 0" — nếu không
    sẽ vẽ ra hộp cụt.

    Vì sao phải đo: `.ass` không có khái niệm "hộp rộng bằng chữ" khi hộp do mình vẽ
    vector. Đo được thì `ngang = 0` mới có nghĩa "bám chữ", thay vì "tắt".
    """
    duong = _FONT_CHO_DUONG.get(font)
    if duong is None:
        return 0
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(duong, max(8, int(co)))
        hop = f.getbbox(chu or " ")
        return int(hop[2] - hop[0])
    except Exception:  # noqa: BLE001 — thiếu font/Pillow thì bỏ đo, KHÔNG làm hỏng đường xuất
        return 0


def to_ass(segments: list[Segment], *, translations: list[str] | None = None,
           bilingual: bool = False, title: str = "phu-de-lab",
           khung: tuple[int, int] | None = None,
           offset_doc: float | None = None,
           style: dict | None = None) -> str:
    """Sinh `.ass`. `khung=(rong, cao)` là kích thước VIDEO THẬT mà chữ sẽ nằm lên.

    `khung=None` giữ nguyên hệ `1920×1080` từng byte — đường xuất tệp rời không biết
    video nào, và đổi mặc định là đổi kết quả của mọi lượt xuất cũ mà không ai yêu cầu.

    Có `khung` thì hệ toạ độ, cỡ chữ, viền và lề đều được suy theo khung đó:
      · `PlayResX/Y` = khung thật, nên libass KHÔNG co giãn chữ;
      · cỡ chữ và lề tính theo TỈ LỆ so với hệ 1920×1080 gốc (cùng một tỉ lệ cho cả hai
        trục, lấy trục NGẮN hơn làm chuẩn — chữ phải vừa cả hai chiều);
      · `WrapStyle: 0` để libass TỰ BẺ dòng theo lề, thay vì để một dòng 693 ký tự tràn
        ra ngoài mép (đo được, xem `_ASS_KHUNG_MAC_DINH`).

    `offset_doc` = tỉ lệ chiều cao khung để DỊCH KHỐI CHỮ XUỐNG (0.06 = 6 %). `None`
    nghĩa là dùng `_ASS_OFFSET_DOC_MAC_DINH` khi có `khung`, và 0 khi `khung=None`
    (đường xuất tệp rời không có video để đè lên, nên không có gì để né).

    🔴 VÌ SAO OFFSET ĐI QUA `\pos` CHỨ KHÔNG QUA `MarginV` (đo được, không phải
    sở thích): `Alignment: 2` neo chữ ở ĐÁY và `MarginV` là khoảng cách từ mép dưới
    LÊN, nên muốn hạ khối chữ xuống phải GIẢM `MarginV`. Nhưng với khung 1080×1920
    thì `duoi` chỉ có 27 px, còn 6 % chiều cao là 115 px — `max(0, 27-115) = 0`, tức
    là offset ăn sạch lề và chữ dính sát mép dưới (đo được: `MarginV=0` ở cả khung
    dọc lẫn ngang). `MarginV` âm thì libass CẮT chữ — đúng thứ bị cấm.
    Nên `MarginV` giữ nguyên giá trị đã suy theo tỉ lệ, và độ hạ đi qua thẻ ghi đè
    `\an2\pos(x,y)` của TỪNG dòng: `y` là đáy khối chữ tính tuyệt đối trong hệ
    `PlayRes`, kẹp trong `[0, ry]` để không bao giờ đẩy chữ ra ngoài khung.
    """
    _assert_lengths(segments, translations)
    tham_so = dict(_ASS_KHUNG_MAC_DINH)
    # 🔴 STYLE ÁP **TRƯỚC** KHỐI `khung`, và khối đó NHÂN TỈ LỆ TỪ `tham_so`.
    #
    # Thứ tự này là thứ tự duy nhất đúng: người dùng chọn cỡ chữ trong hệ 1920×1080, còn
    # video có thể dọc 1080×1920. Nếu style áp SAU khối `khung` thì cỡ chữ do người dùng
    # chọn ĐÈ MẤT phần đã suy theo tỉ lệ, và chữ tràn ra ngoài mép trên khung dọc — đúng
    # lỗi mà `_ASS_KHUNG_MAC_DINH` sinh ra để chặn.
    if style:
        tham_so.update(_style_ass(style))
    #: `None` = không ghi đè vị trí (giữ nguyên hành vi cũ từng byte).
    pos_y: int | None = None
    if khung is not None:
        rong, cao = int(khung[0]), int(khung[1])
        if rong > 0 and cao > 0:
            # Tỉ lệ theo trục NGẮN: khung dọc 1080×1920 có trục ngắn 1080, nên chữ nhỏ
            # lại đúng bằng 1080/1920 so với hệ gốc — vừa bề ngang, không tràn.
            ti_le = min(rong / 1920, cao / 1080)
            co = max(12, round(tham_so["co"] * ti_le))
            le = max(8, round(tham_so["le"] * ti_le))
            duoi = max(8, round(tham_so["duoi"] * ti_le))
            # Đáy khối chữ trong hệ `PlayRes`, tính TỈ LỆ THEO CHIỀU CAO KHUNG — không
            # trừ vào `duoi`.
            #
            # 🔴 VÌ SAO KHÔNG TRỪ VÀO `duoi` (đo được, đây là lần sửa thứ hai):
            # `duoi` suy theo tỉ lệ chỉ còn **27 px** trên khung 1080×1920, còn offset
            # 6 % chiều cao là **115 px**. `27 − 115` âm ngay, nên `day` bị kẹp xuống
            # sàn và `pos_y` BÃO HOÀ: đo được `pos_y=1905` ở cả offset 0,02 / 0,06 /
            # 0,20 / 0,50 — tham số không điều khiển được gì. Một tham số bão hoà là
            # tham số chết, và nó che mất sự thật rằng mục tiêu là "che lớp chữ cứng",
            # không phải "bớt lề dưới".
            #
            # Nên `pos_y` = `cao × (1 − tỉ lệ đáy)`, với `tỉ lệ đáy` = khoảng cách từ
            # đáy khung tới ĐÁY khối chữ. Mặc định 4 % chiều cao (77 px trên 1920) đủ
            # để hộp đen phủ lên dòng phụ đề cứng mà vẫn chừa `le_san` cho đuôi chữ.
            #
            # 🔴 VÌ SAO CẦN `le_san`: `\an2` neo ở ĐÁY HỘP CHỮ, không phải đường
            # baseline. Đặt `pos_y = cao` (chạm mép) thì chân chữ nằm ngoài khung và bị
            # cắt — đo được `pos_y=1920` với `cao=1920` khi chưa có sàn, tức không còn
            # một pixel lề. `le_san` = nửa cỡ chữ là mức tối thiểu để không mất nét.
            ti_le_doc = _ASS_OFFSET_DOC_MAC_DINH if offset_doc is None else float(offset_doc)
            le_san = max(4, co // 2)
            # `ti_le_doc` là PHẦN HẠ XUỐNG tính từ đáy khung; kẹp để không bao giờ ra
            # ngoài khung dù người gọi truyền số vô lý (âm, > 1).
            ti_le_doc = min(max(0.0, ti_le_doc), 1.0)
            pos_y = int(round(cao * (1.0 - ti_le_doc)))
            pos_y = min(cao - le_san, max(le_san, pos_y))
            tham_so.update(
                rx=rong, ry=cao, wrap=0,
                co=co,
                vien=max(1, round(tham_so["vien"] * ti_le)),
                le=le, duoi=duoi,
            )
    lines = [_ASS_HEADER.format(title=title, **tham_so)]
    #: Hộp vẽ bằng VECTOR (`\p1`) — cho hộp RỘNG/CAO **độc lập với cỡ chữ**.
    #:
    #: Vì sao phải vẽ chứ không dùng `Style`: `Outline` là đệm ĐỀU bốn phía, nên muốn hộp
    #: to hơn thì chữ cũng bị đẩy ra theo. `\p1` cho toạ độ tuyệt đối.
    #:
    #: ĐO ĐƯỢC (burn thật bằng `ffmpeg -vf ass=` lên nền xám, đo pixel):
    #:
    #:     khai  200 -> đo  200        khai  600 -> đo  540
    #:     khai  300 -> đo  300        khai  800 -> đo  540
    #:     khai  500 -> đo  500        khai 1000 -> đo  540
    #:
    #:   · tỉ lệ **1:1 tuyệt đối** tới `500 px`, chiều cao đúng ở mọi mức đã thử
    #:     (`80/100/120/200`) — và KHÔNG phụ thuộc `Fontsize`: hộp khai `600×120` ra
    #:     **y hệt nhau** với chữ `fs54` và `fs200`.
    #:   · **TRẦN CỨNG `PlayResX / 2`** (đo được `540` trên hệ 1080), KHÔNG phải do lề
    #:     (thử `MarginL/R = 0` vẫn 540). Khai hơn thì libass CẮT, không báo lỗi — nên
    #:     phải kẹp ở đây thay vì để người dùng nhận một hộp cụt mà không biết.
    rong_hop = int(style.get("rong_hop") or 0) if style else 0
    cao_hop = int(style.get("cao_hop") or 0) if style else 0
    #: 🔴 `ngang = 0` KHÔNG còn là "tắt hộp" — nó là **hộp rộng theo CHỮ, cao theo số đặt**.
    #:
    #: ĐO ĐƯỢC (chủ dự án: *"tôi kéo cỡ cao rồi nhưng chưa có tác dụng, tại cỡ ngang bằng 0
    #: thì nó ko đổi đcc"*): bản trước đòi CẢ HAI > 0, nên `ngang = 0` làm `ve_hop` sai và
    #: mọi thay đổi ở ô "cao" không có gì để áp vào.
    ve_hop = ((rong_hop > 0 or cao_hop > 0)
              and int(tham_so.get("kieu_vien", 0)) == 3)
    if ve_hop:
        # TRẦN = BỀ NGANG KHUNG; SÀN = 40 px, áp TỪNG TRỤC (dưới sàn thì trục đó về 0).
        rong_hop = min(rong_hop, int(tham_so["rx"]))
        cao_hop = min(cao_hop, int(tham_so["ry"]))
        if 0 < rong_hop < 40:
            rong_hop = 0
        if 0 < cao_hop < 40:
            cao_hop = 0
        #: `ngang = 0` ⇒ đo bề rộng chữ của DÒNG DÀI NHẤT rồi dùng chung cho mọi dòng, để
        #: các dòng có hộp ĐỀU NHAU. Không đo được ⇒ 0 ⇒ bỏ hộp vector (giữ hộp tự động).
        if rong_hop == 0:
            do_rong = 0
            for pos_, sg_ in enumerate(segments):
                tr_ = translations[pos_] if translations is not None else None
                do_rong = max(do_rong, _do_rong_chu(
                    "".join(_lines(sg_, tr_, bilingual)),
                    str(tham_so.get("font", "Archivo")), int(tham_so["co"])))
            rong_hop = do_rong + 2 * int(tham_so.get("vien", 0)) if do_rong else 0
        ve_hop = rong_hop >= 40 and cao_hop >= 40
    for position, seg in enumerate(segments):
        translated = translations[position] if translations is not None else None
        parts = _lines(seg, translated, bilingual)
        text = _ass_escape("\\N".join(parts))
        # `\an2` = neo ĐÁY-GIỮA, cùng neo với `Alignment: 2` của style, nên `\pos`
        # chỉ DỜI khối chữ chứ không đổi cách nó lớn lên khi xuống dòng.
        #
        # Chưa truyền `khung` (`pos_y is None`) mà CÓ hộp thì vẫn phải neo: hộp vector cần
        # một mốc tuyệt đối, và chữ phải nằm trong hộp — nên lấy đáy theo `MarginV`.
        y = pos_y if pos_y is not None else int(tham_so["ry"]) - int(tham_so["duoi"])
        co_pos = pos_y is not None or ve_hop
        # 🔴 KHI ĐÃ VẼ HỘP VECTOR THÌ SỰ KIỆN CHỮ PHẢI TẮT HỘP CỦA CHÍNH NÓ.
        #
        # `Style` để `BorderStyle: 3`, nên libass tự vẽ một hộp đục quanh chữ theo
        # `Outline`. ĐO ĐƯỢC hậu quả khi quên: hộp khai `400×120` mà đo ra **432×241** với
        # `fs54` và **517×241** với `fs200` — tức vùng đen là HỢP của hộp vector và hộp
        # tự động, và nó lại phụ thuộc cỡ chữ. `\bord0\shad0` tắt hộp đó, chỉ còn vector.
        tat_hop = "\\bord0\\shad0" if ve_hop else ""
        dau = f"{{\\an2\\pos({tham_so['rx'] // 2},{y}){tat_hop}}}" if co_pos else ""
        if ve_hop:
            # 🔴 CHIA HỘP THÀNH NHIỀU MẢNH: MỘT hình vẽ bị libass THU NHỎ khi rộng quá
            # `PlayResX / 2` (đo được 600→540, 800→540, 2400→540; đổi `\an`, thêm
            # `\fscx` đều không cứu). NHIỀU mảnh ≤ `rx/2` đặt sát nhau thì vượt được.
            #
            # 🔴 VÀ TOẠ ĐỘ PHẢI DƯƠNG — đo được trên ảnh burn thật:
            #
            #     \an2 pos(270), m -270..270   -> x 0..269    (MẤT nửa trái)
            #     \an5 pos(270), m -270..270   -> x 0..269    (mỏ neo không cứu)
            #     \an2 pos(270), m 0..540      -> x 0..539    ĐÚNG
            #     \an2 pos(810), m -270..270   -> x 270..809  (lệch hẳn về giữa)
            #
            # Nên mỗi mảnh vẽ trong hệ `0..w`, và `\an2` canh GIỮA hộp-bao mảnh vào `pos.x`.
            bgr, alpha = tham_so["mau_hop"][4:], tham_so["mau_hop"][2:4]
            toi_da = max(1, int(tham_so["rx"]) // 2)
            so_manh = max(1, -(-rong_hop // toi_da))
            nen = rong_hop // so_manh
            du = rong_hop - nen * so_manh
            trai = (int(tham_so["rx"]) - rong_hop) / 2
            for m in range(so_manh):
                rong_m = nen + (1 if m < du else 0)
                cx = trai + rong_m / 2
                lines.append(
                    f"Dialogue: 0,{_ass_timestamp(seg.start)},{_ass_timestamp(seg.end)},"
                    f"Default,,0,0,0,,{{\\an2\\pos({int(round(cx))},{y})\\p1"
                    f"\\1c&H{bgr}&\\1a&H{alpha}&\\bord0\\shad0}}"
                    f"m 0 0 l {rong_m} 0 {rong_m} {-cao_hop} 0 {-cao_hop}{{\\p0}}"
                )
                trai += rong_m
        lines.append(
            f"Dialogue: 0,{_ass_timestamp(seg.start)},{_ass_timestamp(seg.end)},"
            f"Default,,0,0,0,,{dau}{text}"
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
      đoạn này (lọc từ `meta.qa_issues` theo `id`, cộng `seg.qa` nếu có);
    * `layer` — `"mot_nguon"` / `"hai_nguon"`, tức LỚP của đoạn. Trường này
      ĐỘC LẬP với `suspect`: `layer` nói mấy nguồn cùng đọc ra câu, `suspect`
      nói nguồn nào đọc ra nó. Đo được trên #41: 62/75 đoạn `mot_nguon` là do
      ASR sinh ra, nên hai trường không suy ra được nhau.

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
            # `layer` KHONG phai ban sao cua `suspect` — hai truc doc lap:
            #
            #     layer   = "may NGUON doc ra cau nay"   (mot_nguon / hai_nguon)
            #     suspect = "NGUON NAO doc ra no"        (False=OCR, True=ASR)
            #
            # Do duoc tren #41: 62/75 doan `mot_nguon` la do ASR sinh ra. Nen nhin
            # `layer` khong suy ra duoc `suspect`, va nguoc lai. Tep xuat truoc day chi
            # co `suspect`, nen nguoi doc khong biet doan nao la layer 1 — phai mo lai
            # du lieu goc moi kiem duoc.
            "layer": seg.layer,
            "qa": qa,
        })
    return json.dumps({"meta": header, "segments": out},
                      ensure_ascii=False, indent=2) + "\n"
