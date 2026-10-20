"""Chặn XOÁ khi còn job đang xếp hàng/đang chạy trên hàng đó.

Vì sao phải có một chỗ dùng chung cho hai route `DELETE`: `jobs` **không có khoá
ngoại** trỏ tới `sources`/`translations` (`adapters/persist/schema.py` khai
`REFERENCES` cho `transcripts.source_id` và `translations.transcript_id`, còn
`jobs.payload` chỉ là TEXT). Đường nối DUY NHẤT từ một job tới hàng nó đang chạm
là `payload` JSON, và nó là hợp đồng đã có:

* job `ingest`/`asr` mang `payload.source_id` (`routes_sources._enqueue_ingest`,
  `pipeline/ingest.TranscribeHandler`), và chính handler đọc khoá đó.
* job `translate` mang `payload.translation_id`
  (`routes_translations.create_translation`, `pipeline/translate.TranslateHandler`).

Để hai route tự viết lại phép dò này là hai chỗ để trôi khỏi payload thật — và
trôi ở đây KHÔNG có triệu chứng: một predicate sai chỉ âm thầm cho phép xoá hàng
dưới chân một handler đang chạy.

Vì sao TỪ CHỐI (409) thay vì xoá kèm huỷ job: handler đang chạy giữ `job` trong
bộ nhớ và ghi checkpoint vào hàng `translations`/`transcripts` sau mỗi lô. Xoá
hàng dưới chân nó thì checkpoint kế tiếp hoặc `NotFound` (job thành `failed` vì
một lý do không liên quan tới dữ liệu), hoặc — tệ hơn — `INSERT`/`UPDATE` rơi
vào một id đã được cấp lại cho hàng khác. Huỷ job trước là việc của người dùng
(route `POST /api/jobs/{id}/cancel`), và câu 409 nói đúng job nào cần huỷ.
"""
from __future__ import annotations

from app.domain import job_state as js

#: Trạng thái job được coi là ĐANG LÀM VIỆC. `UNSETTLED_TRANSLATION_STATUSES`
#: (`app.domain.models`) không dùng lại được ở đây: nó là trạng thái của BẢN
#: DỊCH, và hai khái niệm chỉ tình cờ trùng tên (một bản dịch `queued` là hàng
#: chờ, một job `queued` là việc chờ) — gộp chúng là buộc hai thứ khác nhau phải
#: đổi cùng nhau.
ACTIVE_JOB_STATES: tuple[str, ...] = (js.QUEUED, js.RUNNING)


def active_job_ids(repos, *, key: str, value: int) -> list[int]:
    """Id của MỌI job `queued`/`running` có `payload[key] == value`, tăng dần.

    Danh sách RỖNG là câu trả lời bình thường ("không ai đang chạm hàng này"), nên
    người gọi phân nhánh bằng `if ids:`, không phải `is None`.

    So sánh qua `int(raw)`, không `==` trần: `payload` đi qua JSON
    (`json.dumps`/`json.loads`) nên giá trị đọc lên thường là `int`, nhưng một
    job do tay người hay một fixture ghi vào có thể mang `"12"`; `==` trần sẽ nói
    "không có job nào" cho đúng hàng đang có job, tức cho phép xoá. `int()` cũng
    TỪ CHỐI `None`/dict/chuỗi rác bằng `TypeError`/`ValueError` — nuốt hai lỗi đó
    thành `False` là hành vi đúng ("payload không nói về hàng này").

    `payload` không phải `dict` cũng bị bỏ qua vì cùng lý do, và vì
    `Job.payload` là `dict` ở mọi đường ghi của sản phẩm: một giá trị lạ ở đây là
    dữ liệu cũ, không phải một job đang chạy.
    """
    found: list[int] = []
    for job in repos.list_jobs(states=ACTIVE_JOB_STATES):
        payload = getattr(job, "payload", None)
        if not isinstance(payload, dict):
            continue
        try:
            same = int(payload.get(key)) == value
        except (TypeError, ValueError):
            continue
        if same and job.id is not None:
            found.append(int(job.id))
    return sorted(found)


def mot_loi_409(*, doi_tuong: str, ids: list[int], cach_sua: str) -> str:
    """Câu 409 NGUYÊN VĂN: nêu ĐÚNG id job, không phải một câu chung.

    Client hiện nguyên văn `ApiError.message` (xem `endpoints.ts` + `NutXoa`), nên
    câu này là thứ người dùng đọc để sửa — "có job đang chạy" mà không nói job
    NÀO thì không sửa được gì.
    """
    danh_sach = ", ".join(f"#{i}" for i in ids)
    return (f"không xoá được {doi_tuong}: job {danh_sach} đang xếp hàng hoặc đang "
            f"chạy trên nó — {cach_sua}")
