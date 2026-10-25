"""Use case xuất phụ đề ra tệp.

Ghi hai tệp cạnh nhau: tệp phụ đề và một tệp chỉ mục `.json` cùng tên. Chỉ mục
là thứ duy nhất nối tệp trên đĩa với hàng trong cơ sở dữ liệu, nên nó mang
`transcript_version` — không có nó thì không biết tệp đã cũ hay chưa khi
transcript được sửa.

`render()` là CỬA VÀO DUY NHẤT cho mọi định dạng, dùng chung bởi đường job (ở
đây) và đường spec (`api/routes_translations.export_translation`): hai chỗ tự gọi
`FORMATS[...]` là hai chỗ để `json` (định dạng DUY NHẤT cần thêm `meta`) trôi
khỏi nhau. `FORMATS` vẫn là danh sách định dạng hợp lệ (dùng cho 422 và
`MEDIA_TYPES`).
"""
from __future__ import annotations

import json
import pathlib
from typing import Callable

from app.domain.models import Job
from app.domain.paths import safe_basename
from app.domain.subtitle_format import to_ass, to_json, to_srt, to_vtt
from app.ports.repos import Repos

FORMATS = {"srt": to_srt, "vtt": to_vtt, "ass": to_ass, "json": to_json}

#: Đuôi `Content-Type` cho từng định dạng. Ở đây chứ không ở route: danh sách
#: này đi cùng `FORMATS`, và `application/x-subrip` KHÔNG phải `text/plain` —
#: một chỗ khai sai thì trình phát tải về rồi không nhận ra phụ đề.
MEDIA_TYPES = {"srt": "application/x-subrip", "vtt": "text/vtt",
               "ass": "text/x-ssa", "json": "application/json"}

#: Định dạng cần khối `meta` (chỉ `json`). Một TẬP chứ không một phép so chuỗi
#: rải rác: thêm một định dạng có meta là sửa đúng một dòng.
META_FORMATS = frozenset({"json"})


def render(fmt: str, segments, *, translations: list[str] | None = None,
           bilingual: bool = False, meta: dict | None = None) -> str:
    """Sinh nội dung của MỘT định dạng — cửa vào duy nhất của cả hai đường export.

    Ba định dạng phụ đề nhận `bilingual`; `json` bỏ qua nó (định dạng đó LUÔN có
    nguồn lẫn bản dịch — xem `subtitle_format.to_json`) và nhận `meta` thay vào.
    `meta=None` cho `json` là `{}` chứ không phải lỗi: đường cũ (job) không có
    hàng `translations` để đọc `translation_id`, và "không biết" phải ra `null`/
    vắng mặt chứ không được bịa.
    """
    if fmt in META_FORMATS:
        return FORMATS[fmt](segments, translations=translations, meta=meta or {})
    return FORMATS[fmt](segments, translations=translations, bilingual=bilingual)


def export_meta(*, transcript, translation=None, stale: bool | None = None) -> dict:
    """Khối `meta` của định dạng `json` — MỘT nguồn cho cả hai đường export.

    `translation=None` là đường job (`POST /api/export`): payload của nó chỉ có
    `transcript_id` + danh sách chữ đã dịch, KHÔNG có hàng `translations`, nên
    `translation_id`/`engine`/`target_lang`/`prompt_version`
    /`translated_from_transcript_version` là `null` và `stale` là `null` ("chưa đo
    được", không phải `false` — cùng quy ước với `tokens_in`/`duration_ms`). Đường
    spec (theo một hàng bản dịch) luôn đủ khoá: đó là đường mà ba nút xuất của giao
    diện dùng.

    HAI khoá version, và chúng KHÁC NHAU có chủ:

    * `transcript_version` — version của hàng `transcripts` mà nội dung NGUỒN trong
      tệp được đọc ra (cùng nghĩa ở cả hai đường);
    * `translated_from_transcript_version` — version mà hàng `translations` khai nó
      đã dịch TỪ (`translations.transcript_version`, dấu vết duy nhất của bản dịch);
      `stale` chính là "hai số này khác nhau".

    Chỉ có MỘT khoá version là chỗ để hai câu hỏi khác nhau ("nguồn này là bản nào"
    và "bản dịch này làm từ bản nào") đội lốt nhau — đúng lúc `stale` bật, tức đúng
    lúc người đọc cần phân biệt chúng nhất.
    """
    return {
        "transcript_id": transcript.id,
        "translation_id": None if translation is None else translation.id,
        "engine": None if translation is None else translation.engine,
        "target_lang": None if translation is None else translation.target_lang,
        "prompt_version": None if translation is None else translation.prompt_version,
        "transcript_version": transcript.version,
        "translated_from_transcript_version":
            None if translation is None else translation.transcript_version,
        "stale": stale,
        # Danh sách issue ĐẦY ĐỦ (kể cả `engine_no_glossary`, vốn không thuộc đoạn
        # nào). Từng đoạn có bản lọc riêng ở khoá `qa`; để lại bản đầy đủ ở meta là
        # cách duy nhất không nuốt mất issue không có `id`.
        "qa_issues": [] if translation is None else list(translation.qa_issues),
    }


def artifact_name(stem: str, fmt: str, *, translated: bool) -> str:
    """Tên tệp phụ đề trên đĩa. MỘT nguồn cho cả handler lẫn route tải về.

    `translated` (payload có bản dịch) thêm `.vi` vào TRƯỚC đuôi định dạng. Hai
    chỗ tự ghép tên là hai chỗ trôi khỏi nhau: handler ghi `<stem>.vi.srt` còn
    route đi tìm `<stem>.srt` thì người dùng nhận 410 cho một tệp nằm ngay đó.
    """
    return f"{stem}{'.vi' if translated else ''}.{fmt}"


def _write_utf8(path: pathlib.Path, text: str) -> None:
    """Ghi UTF-8 với kết thúc dòng CỐ ĐỊNH `\\n`.

    `Path.write_text()` mở ở chế độ văn bản nên trên Windows nó dịch mọi `\\n`
    thành `\\r\\n`. Hệ quả: cùng một nội dung cho ra byte khác nhau tuỳ hệ điều
    hành, tệp ghi trên Windows không còn khớp với chuỗi mà `to_srt`/`to_vtt`/
    `to_ass` sinh ra, và các trình phát cũ chỉ chấp nhận `\\n` sẽ thấy ký tự
    xuống dòng thừa ở cuối mỗi dòng. Mở thẳng với `newline="\\n"` để tắt dịch.
    """
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


class ExportHandler:
    def __init__(self, repos: Repos, *, out_dir: str | pathlib.Path) -> None:
        self._repos = repos
        self._out_dir = pathlib.Path(out_dir)

    def handles(self) -> str:
        return "export"

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        payload = job.payload
        # EX-04 (F4/Task 14): kiểm `transcript_id` TRƯỚC `fmt`. Đi thẳng vào
        # `int(payload["transcript_id"])` thì một job dị dạng nổi lên ở tận
        # worker thành `KeyError: 'transcript_id'` trần — không phải lớp lỗi
        # hành động được và không nói job thiếu gì. Kiểm trước cũng để một
        # payload vừa thiếu id vừa sai định dạng báo ĐÚNG thứ đang thiếu, thay
        # vì để phép validate định dạng che mất.
        raw_transcript_id = payload.get("transcript_id")
        if not raw_transcript_id:
            raise ValueError("job export thiếu transcript_id")
        transcript_id = int(raw_transcript_id)
        fmt = str(payload.get("format", "srt")).lower()
        bilingual = bool(payload.get("bilingual", False))
        if fmt not in FORMATS:
            raise ValueError(f"định dạng không hỗ trợ: {fmt!r} (có: {sorted(FORMATS)})")

        transcript = self._repos.get_transcript(transcript_id)
        report(0.3, f"dựng {fmt.upper()} cho transcript #{transcript_id}")

        translations = payload.get("translations")
        if translations is not None and len(translations) != len(transcript.segments):
            raise ValueError("số bản dịch không khớp số đoạn")

        content = render(fmt, transcript.segments, translations=translations,
                         bilingual=bilingual,
                         meta=export_meta(transcript=transcript))

        self._out_dir.mkdir(parents=True, exist_ok=True)
        # `stem` cũng là dữ liệu BÊN NGOÀI (payload job), nên `../` trong đó ghi
        # được ra ngoài `out_dir` (R76). Cùng một phép cắt với route upload.
        raw_stem = payload.get("stem")
        stem = safe_basename(str(raw_stem) if raw_stem else None,
                             fallback=f"transcript-{transcript_id}")
        target = self._out_dir / artifact_name(stem, fmt, translated=translations is not None)
        _write_utf8(target, content)

        # Chỉ mục `.json` đi kèm CHỈ khi tệp chính không phải chính nó. Với
        # `format=json`, `<tên>.vi.json.json` là bản sao thứ hai của cùng một tệp
        # dưới một cái tên gây nhầm — và tệp `json` ĐÃ mang đủ khối `meta` mà chỉ
        # mục kia tồn tại để giữ (`transcript_id`, `transcript_version`, `engine`).
        if fmt != "json":
            index = target.with_suffix(target.suffix + ".json")
            _write_utf8(index, json.dumps({
                "transcript_id": transcript_id,
                "transcript_version": transcript.version,
                "engine": transcript.engine,
                "format": fmt,
                "bilingual": bilingual,
                "segments": len(transcript.segments),
            }, ensure_ascii=False, indent=2))

        report(1.0, f"đã ghi {target}")
