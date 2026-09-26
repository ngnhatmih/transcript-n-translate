"""Quy tắc 'bản dịch đã lỗi thời'. Dùng version, KHÔNG dùng timestamp.

Timestamp trùng nhau được (hai lần sửa trong cùng một giây) và không trả lời
được câu 'bản dịch này dịch từ bản transcript nào'.
"""
from __future__ import annotations


def is_stale(transcript_version: int, translated_from_version: int) -> bool:
    return translated_from_version < transcript_version


def translation_summary_json(row, current_version: int | None = None, *,
                             stale: bool | None = None) -> dict:
    """Hình dạng JSON DUY NHẤT của một hàng bản dịch tóm tắt (Task 13/15).

    MỘT builder cho mọi endpoint, không phải mỗi route tự ghép khoá: trước bản
    này `routes_translations._summary` phát `transcript_version` + `status` còn
    `routes_transcripts._translation_json` phát `translated_from_version` và
    KHÔNG có `status`. Cùng một hàng đọc ở hai endpoint cho hai hình dạng khác
    nhau, và endpoint chi tiết transcript — đúng cái Workspace 2 mở cho mỗi video
    — không phân biệt được một bản dịch `queued` với một bản dịch `done`.

    Khoá `transcript_version` (không phải `translated_from_version`) là khoá mà
    route danh sách bản dịch đã ship (Task 13); nó cũng là tên CỘT trong DB, nên
    nó không cần một lớp dịch tên.

    Hai lối vào, CÙNG một kết quả:

    * `current_version` — version hiện tại của transcript; `stale` được TÍNH ở
      đây (`is_stale`). Đây là lối của route transcript, nơi version vừa đọc.
    * `stale=` — cờ đã tính sẵn. Đây là lối của route bản dịch, nơi transcript
      đã được đọc ngay trước đó cho việc khác; truyền thẳng giá trị đã tính thay
      vì đọc lại hàng lần thứ hai trong cùng request.

    Truyền CẢ HAI là lỗi lập trình (`ValueError`): một hàm hai nguồn sự thật cho
    cùng một khoá là đúng thứ nó tồn tại để dẹp.
    """
    if (current_version is None) == (stale is None):
        raise ValueError(
            "truyền ĐÚNG MỘT trong hai: `current_version` hoặc `stale=` "
            f"(nhận current_version={current_version!r}, stale={stale!r})")
    if stale is None:
        stale = is_stale(current_version, row.transcript_version)
    return {
        "id": row.id,
        "transcript_id": row.transcript_id,
        "engine": row.engine,
        "target_lang": row.target_lang,
        "prompt_version": row.prompt_version,
        "transcript_version": row.transcript_version,
        "status": row.status,
        "stale": stale,
        "created_at": row.created_at,
    }
