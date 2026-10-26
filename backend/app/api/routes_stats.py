"""`GET /api/stats/tokens` — thống kê token/thời lượng theo engine, đọc từ `llm_calls`.

Vì sao có route này: mọi con số ĐÃ được ghi từ trước (`TranslateHandler._record_call` ghi một
hàng `llm_calls` cho ĐÚNG một lần chạm engine), nhưng chỉ cộng vào hàng `translations` của MỘT
bản dịch. Muốn trả lời "engine nào tốn bao nhiêu token" thì phải mở DB bằng tay — đo được ngay
trên app thật: 18 lời gọi `deepseek-web` có đủ token mà không có chỗ nào trong API/UI đọc ra.

Hai luật của phép trả lời, cả hai đều là "không bịa":

* **`None` ≠ `0`.** Engine in-process (`opus-mt`) không có token, và `duration_ms` của engine
  `http` chỉ có từ khi adapter tự đo. Tổng nào chưa đo được thì là `null`; đổi thành `0` là nói
  dối rằng "đã đo và bằng không".
* **`ok_calls` tách khỏi `calls`.** Một lời gọi hỏng vẫn tốn token (endpoint đã xử lý rồi mới
  trả sai số dòng) — gộp chúng vào một con số thì số token không giải thích được.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_repos

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _cong(gia_tri: list[int | None]) -> int | None:
    """Tổng của một cột, `None` khi KHÔNG có giá trị nào — không bao giờ `0` thay cho `None`."""
    co = [v for v in gia_tri if v is not None]
    return sum(co) if co else None


@router.get("/tokens")
def token_stats(repos=Depends(get_repos)):
    """Token/thời lượng đã dùng, gộp theo `(engine, model_ref)`, cộng thêm tổng toàn bộ.

    Đơn vị: `tokens_in`/`tokens_out` là token của endpoint (do chính nó trả trong `usage`);
    `duration_ms` là mili giây ĐO ĐƯỢC (Ollama trả `total_duration`, adapter `http` tự bấm
    giờ). Không có quy đổi ra tiền: giá phụ thuộc bảng giá của từng dịch vụ, và bịa một tỉ giá
    ở đây là bịa một con số không ai kiểm được.
    """
    hang = repos.token_stats()
    return {
        "engines": hang,
        "total": {
            "calls": sum(int(r["calls"] or 0) for r in hang),
            "ok_calls": _cong([r["ok_calls"] for r in hang]),
            "tokens_in": _cong([r["tokens_in"] for r in hang]),
            "tokens_out": _cong([r["tokens_out"] for r in hang]),
            "duration_ms": _cong([r["duration_ms"] for r in hang]),
        },
    }
