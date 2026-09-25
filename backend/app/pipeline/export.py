"""Use case xuất phụ đề ra tệp.

Ghi hai tệp cạnh nhau: tệp phụ đề và một tệp chỉ mục `.json` cùng tên. Chỉ mục
là thứ duy nhất nối tệp trên đĩa với hàng trong cơ sở dữ liệu, nên nó mang
`transcript_version` — không có nó thì không biết tệp đã cũ hay chưa khi
transcript được sửa.
"""
from __future__ import annotations

import json
import pathlib
from typing import Callable

from app.domain.models import Job
from app.domain.paths import safe_basename
from app.domain.subtitle_format import to_ass, to_srt, to_vtt
from app.ports.repos import Repos

FORMATS = {"srt": to_srt, "vtt": to_vtt, "ass": to_ass}

#: Đuôi `Content-Type` cho từng định dạng. Ở đây chứ không ở route: danh sách
#: này đi cùng `FORMATS`, và `application/x-subrip` KHÔNG phải `text/plain` —
#: một chỗ khai sai thì trình phát tải về rồi không nhận ra phụ đề.
MEDIA_TYPES = {"srt": "application/x-subrip", "vtt": "text/vtt",
               "ass": "text/x-ssa"}


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
        transcript_id = int(payload["transcript_id"])
        fmt = str(payload.get("format", "srt")).lower()
        bilingual = bool(payload.get("bilingual", False))
        if fmt not in FORMATS:
            raise ValueError(f"định dạng không hỗ trợ: {fmt!r} (có: {sorted(FORMATS)})")

        transcript = self._repos.get_transcript(transcript_id)
        report(0.3, f"dựng {fmt.upper()} cho transcript #{transcript_id}")

        translations = payload.get("translations")
        if translations is not None and len(translations) != len(transcript.segments):
            raise ValueError("số bản dịch không khớp số đoạn")

        content = FORMATS[fmt](transcript.segments, translations=translations,
                               bilingual=bilingual)

        self._out_dir.mkdir(parents=True, exist_ok=True)
        # `stem` cũng là dữ liệu BÊN NGOÀI (payload job), nên `../` trong đó ghi
        # được ra ngoài `out_dir` (R76). Cùng một phép cắt với route upload.
        raw_stem = payload.get("stem")
        stem = safe_basename(str(raw_stem) if raw_stem else None,
                             fallback=f"transcript-{transcript_id}")
        target = self._out_dir / artifact_name(stem, fmt, translated=translations is not None)
        _write_utf8(target, content)

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
