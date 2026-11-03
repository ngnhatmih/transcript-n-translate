"""Quy tắc 'bản dịch đã lỗi thời'. Dùng version, KHÔNG dùng timestamp.

Timestamp trùng nhau được (hai lần sửa trong cùng một giây) và không trả lời
được câu 'bản dịch này dịch từ bản transcript nào'.
"""
from __future__ import annotations

from app.domain.pricing import Price, cost_usd


def is_stale(transcript_version: int, translated_from_version: int) -> bool:
    return translated_from_version < transcript_version


#: Tien to cua co QA noi ve NOI DUNG ban dich — tuc la ban dich SAI, khong phai
#: ban dich CHAM. Day la ranh gioi duy nhat quyet dinh `status` co bi doi hay khong.
#:
#: DO DUOC tren 52 ban dich dang co trong DB (workspace 2):
#:
#:     cps:      4715 co    <- TOC DO DOC vuot nguong. So do de hien thi.
#:     length:    714 co    <- TI LE DO DAI. So do de hien thi.
#:     lang:       53 co    <- DONG DICH VAN LA CHU GOC. Ban dich sai.
#:     echo:        2 co    <- CHEP NGUYEN VAN. Ban dich sai.
#:
#: Neu coi CA BON la loi thi 51/52 ban dich thanh khong dung duoc — vi `cps` keu o
#: 4715 cho, va mot dong 26 ky tu trong cua so 1 giay la chuyen binh thuong cua phu
#: de. Lay so do lam dieu kien chan la bien toan bo du lieu thanh loi.
#:
#: Do duoc sau khi tach: 3/52 ban dich co loi noi dung that (id=22, 17, 12);
#: 48/52 chi co so do; 1/52 sach hoan toan.
CO_LOI_NOI_DUNG = ("lang:", "echo:")


def co_loi_noi_dung(qa_issues: list[str] | None) -> bool:
    """Ban dich nay co loi NOI DUNG khong (khac voi co so do vuot nguong).

    Tach hai thu ma truoc day nam chung mot danh sach. `cps:` va `length:` la SO DO —
    chung noi 'dong nay doc nhanh hon nguong', khong noi 'dong nay sai'. `lang:` va
    `echo:` moi noi ban dich SAI: dong do van la chu Han goc, hoac chep nguyen van.

    Dung chung mot danh sach `qa_issues` cho ca hai viec la thu da lam co QA khong
    bao gio chan duoc gi — xem chu thich cua `CO_LOI_NOI_DUNG`.
    """
    if not qa_issues:
        return False
    return any(str(q).startswith(CO_LOI_NOI_DUNG) for q in qa_issues)


def translation_summary_json(row, current_version: int | None = None, *,
                             stale: bool | None = None,
                             prices: dict[str, Price] | None = None) -> dict:
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
    # 🔴 `status` GIU NGUYEN — no la co SAN SANG, khong phai co CHAT LUONG.
    #
    # Da thu doi `status` sang `needs_review` khi co loi noi dung: bai
    # `test_e2e_fake.py::test_full_pipeline_from_upload_to_srt` DO, va no dung.
    # Cau khang dinh trong bai ghi ro hop dong:
    #
    #     "endpoint nay phai phan biet duoc `queued` voi `done`: day la thu giao dien
    #     Workspace 2 dung de biet ban dich da san sang chua"
    #
    # Tron hai nghia vao mot khoa la lam hong thu ma giao dien dang dua vao. Nen co
    # chat luong di ra khoa RIENG `needs_review`, va `status` khong biet gi ve no.
    needs_review = co_loi_noi_dung(_qa_issues_of(row))
    return {
        "id": row.id,
        "transcript_id": row.transcript_id,
        "engine": row.engine,
        "target_lang": row.target_lang,
        "prompt_version": row.prompt_version,
        "transcript_version": row.transcript_version,
        # 🔴 `status` PHAI phan anh loi NOI DUNG, khong phai so do.
        #
        # Truoc day dong nay la `"status": row.status` va co QA chi duoc PHOI ra HTTP —
        # nghia la mot ban dich con nguyen chu Han van bao `done`. Do duoc: id=22 va
        # id=17 co `lang:...=source:...` (dong dich VAN la chu goc) ma `status=done`.
        #
        # Khong doi sang `failed`: ban dich da chay xong, co `segments` day du, nguoi
        # dung van doc duoc. `needs_review` noi dung dieu do — xong nhung phai xem lai.
        "status": row.status,
        # 🔴 CO CHAT LUONG, tach khoi `status`.
        #
        # `True` khi `qa_issues` co `lang:` hoac `echo:` — tuc la dong dich VAN LA CHU
        # GOC, hoac chep nguyen van. Do duoc: 3/52 ban dich trong DB (id=22, 17, 12).
        #
        # `cps:` va `length:` KHONG lam co nay bat: chung la so do toc do doc / ti le do
        # dai, va mot dong 26 ky tu trong cua so 1 giay la chuyen binh thuong cua phu de.
        # Neu gop chung thi 48/52 ban dich bi gan co sai.
        "needs_review": needs_review,
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
        # CHI PHÍ ƯỚC LƯỢNG của bản dịch này (USD) = token ĐÃ ĐO × giá ĐÃ KHAI của engine.
        # `None` khi không tính được (engine in-process không có giá/không báo token) — xem
        # `app/domain/pricing.py`; ở đó có ghi vì sao `None` không được thay bằng `0`.
        "cost_usd": cost_usd(getattr(row, "engine", None),
                             getattr(row, "tokens_in", None),
                             getattr(row, "tokens_out", None), prices),
    }


def _qa_issues_of(row) -> list[str]:
    """Cờ QA của một hàng, LUÔN là danh sách — vắng cột ⇒ `[]`, không bao giờ `None`.

    Một hình dạng thứ hai (`null`) cho cùng một khoá là thứ client phải nhớ, và
    thứ nó sẽ quên. `[]` và "không có cờ nào" nói cùng một điều, nên chỉ có một
    cách viết.
    """
    issues = getattr(row, "qa_issues", None)
    return list(issues) if issues else []

