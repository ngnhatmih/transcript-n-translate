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
        # ---- V1: cờ QA + số đo (lượt 3 của nhánh `fix-loi-dich-im-lang`) ----
        #
        # Vì sao bốn khoá này phải ở ĐÂY chứ không ở route chi tiết: đo được ở
        # lượt 2 là một bản "dịch" của `qwen2.5-3b` CHÉP NGUYÊN 43/44 đoạn chữ
        # Trung mà vẫn `status=done`, `transcript=translated`, và KHÔNG một
        # response HTTP nào mang `qa_issues` — tức là cờ QA có trong DB nhưng
        # không có đường ra tới màn hình, nên thất bại vẫn IM LẶNG ở tầng sản phẩm.
        # Cả ba route đọc hàng bản dịch đều đi qua hàm này, nên đặt ở đây là cách
        # duy nhất để chúng không trôi khỏi nhau (cùng lý do đã dẹp
        # `translated_from_version`).
        #
        # `getattr` có mặc định vì hàm này nhận MỌI hàng bản dịch: `Translation`
        # (đủ bốn trường) lẫn `TranslationSummary` cũ, và một hàng thiếu trường
        # phải ra `[]`/`None` chứ không được ném `AttributeError` giữa request.
        #
        # ⚠️ TRẦN có chủ: đây là PHƠI cờ, KHÔNG phải CỬA CHẶN. `status` giữ
        # nguyên ngữ nghĩa — một bản dịch có cờ `lang:...=source:` vẫn `done`
        # (quyết định sản phẩm, chưa làm ở lượt này). Và `qa_issues` ra tới HTTP
        # nghĩa là CÓ ĐƯỜNG, chưa phải là có người ĐỌC nó: hiển thị là việc
        # frontend, trên nhánh frontend.
        "qa_issues": _qa_issues_of(row),
        "tokens_in": getattr(row, "tokens_in", None),
        "tokens_out": getattr(row, "tokens_out", None),
        "duration_ms": getattr(row, "duration_ms", None),
    }


def _qa_issues_of(row) -> list[str]:
    """Cờ QA của một hàng, LUÔN là danh sách — vắng cột ⇒ `[]`, không bao giờ `None`.

    Một hình dạng thứ hai (`null`) cho cùng một khoá là thứ client phải nhớ, và
    thứ nó sẽ quên. `[]` và "không có cờ nào" nói cùng một điều, nên chỉ có một
    cách viết.
    """
    issues = getattr(row, "qa_issues", None)
    return list(issues) if issues else []

