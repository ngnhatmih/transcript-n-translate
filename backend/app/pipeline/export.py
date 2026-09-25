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
from app.domain.subtitle_format import to_ass, to_srt, to_vtt
from app.ports.repos import Repos

FORMATS = {"srt": to_srt, "vtt": to_vtt, "ass": to_ass}


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
        stem = payload.get("stem") or f"transcript-{transcript_id}"
        suffix = ".vi" if translations is not None else ""
        target = self._out_dir / f"{stem}{suffix}.{fmt}"
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
