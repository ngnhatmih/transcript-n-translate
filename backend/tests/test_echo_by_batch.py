"""Bảng echo THEO TỪNG LÔ (`scripts/smoke_echo_guard.py::echo_by_batch`).

Vì sao có tệp này
    Lượt quét prompt trước (`20261019-prompt-echo-sweep`) chỉ có MỘT con số tổng
    cho cả lượt, nên câu "29 lần echo còn lại nằm HẾT ở lô ĐẦU" là suy ra từ
    `guard_lines` trong log chứ không phải từ một bảng — và một kết luận về THỨ TỰ
    mà không có bảng theo lô thì không đỡ được phản biện nào. `echo_by_batch` là
    hàm THUẦN: nó ghép hình dạng lời gọi (size/ids/vị trí dòng log) với các dòng
    `echo_guard:<n>/<m>` của cổng thành bảng theo lô, nên đưa vào một chuỗi lời
    gọi + log GIẢ có pattern echo đã biết thì nó phải ra đúng con số của từng lô.

Vì sao KHÔNG còn bài nào cho seam SƯỞI
    Tệp này từng ghim cả seam "sưởi trước lô đầu" (bốn bài đi qua handler với một
    cờ capability mà `registry.json` chưa từng khai). Seam đó đã bị XOÁ: một đường
    không cấu hình nào vào được là cùng một lỗi với một khai báo không ai đọc, và
    phép đo đứng sau nó (bảng A–E trong `backend/README.md`, artifact
    `20261019-echo-warmup/`) nói nó không đáng bật. Ba bài dưới đây Ở LẠI vì
    chúng KHÔNG kiểm seam: chúng kiểm phép KẾ TOÁN theo lô, và bảng đó là bằng
    chứng của cả lượt đo — kể cả sau khi seam biến mất.
"""
from __future__ import annotations

import importlib.util
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "smoke_echo_guard.py"


def _load_driver():
    assert SCRIPT.exists(), "brief yêu cầu driver backend/scripts/smoke_echo_guard.py"
    spec = importlib.util.spec_from_file_location(
        "smoke_echo_guard_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Trace:
    """Dựng `(calls, log)` GIẢ đúng thứ tự mà handler thật sinh ra.

    Mọi `at` được lấy từ `len(log)` tại thời điểm gọi, đúng như `_CallRecorder`
    làm ở lượt chạy thật — nhờ vậy bài không kiểm một con số do bài tự bịa.
    """

    def __init__(self) -> None:
        self.log: list[str] = []
        self.calls: list[dict] = []
        self.phase = 1

    def batch(self, ids: list[int]) -> None:
        self.calls.append({"phase": self.phase, "size": len(ids), "ids": list(ids),
                           "at": len(self.log), "duration_ms": 100})

    def single(self, i: int) -> None:
        self.calls.append({"phase": self.phase, "size": 1, "ids": [i],
                           "at": len(self.log), "duration_ms": 10})

    def guard(self, echoed: int, items: int) -> None:
        self.log.append(f"echo_guard:{echoed}/{items} đoạn chép nguyên chữ nguồn: "
                        f"dịch lại riêng từng đoạn")

    def guard_fixed(self, echoed: int, items: int) -> None:
        self.log.append(f"echo_guard: đã sửa {echoed}/{items} đoạn (dịch lại riêng), "
                        f"không còn đoạn chép nguồn")

    def checkpoint(self, done: int, total: int) -> None:
        self.log.append(f"đã dịch {done}/{total}")


def test_the_batch_accounting_puts_echoes_in_the_batch_that_produced_them():
    """Bảng phải phân biệt "echo DỒN ở lô 1" với "echo RẢI đều" — đó là cả câu hỏi.

    Pattern giả: lô 1 có 2 echo, lô 2 có 30 echo (cả lô), lô 3 và 4 KHÔNG có dòng
    `echo_guard` nào. Một phép đếm theo thứ tự xuất hiện sẽ ghép dòng của lô 2 vào
    lô... không có gì để ghép, và đó chính là lỗi mà `at` tồn tại để chặn.
    """
    driver = _load_driver()
    trace = _Trace()
    trace.log.append("dịch 0/115 segment đã có (engine hy-mt-1.5-7b)")

    trace.batch(list(range(0, 30)))
    trace.guard(2, 30)
    trace.guard_fixed(2, 30)
    trace.single(3)
    trace.single(7)
    trace.checkpoint(30, 115)

    trace.batch(list(range(30, 60)))
    trace.guard(30, 30)
    trace.guard_fixed(30, 30)
    for i in range(30, 60):
        trace.single(i)
    trace.checkpoint(60, 115)

    trace.batch(list(range(60, 90)))
    trace.checkpoint(90, 115)

    trace.batch(list(range(90, 115)))
    trace.checkpoint(115, 115)

    rows = driver.echo_by_batch(trace.calls, trace.log)

    assert [(row["items"], row["echoed"], row["singleton_calls"]) for row in rows] == [
        (30, 2, 2), (30, 30, 30), (30, 0, 0), (25, 0, 0),
    ]
    assert [row["batch"] for row in rows] == [1, 2, 3, 4]
    assert rows[0]["retried_ids"] == [3, 7], (
        "id dịch lại của lô 1 phải nằm ĐÚNG lô 1, không trôi sang lô khác"
    )
    assert rows[0]["guard_items"] == 30 and rows[1]["guard_items"] == 30
    assert rows[2]["guard_items"] is None, (
        "lô không echo thì không có dòng `echo_guard:<n>/<m>` nào để ghép"
    )


def test_a_singleton_call_before_the_first_batch_belongs_to_no_batch():
    """Lời gọi MỘT mục đứng TRƯỚC lô đầu KHÔNG được tính là "dịch lại" của lô 1.

    Ca thật duy nhất từng sinh ra nó là lượt sưởi trước lô đầu, với `i` là id ÂM
    của một segment giả (`-1`, không bao giờ trùng id thật). Seam đó đã bị xoá,
    nhưng luật của hàm THUẦN vẫn phải giữ: một lời gọi thử bị tính vào "dịch lại"
    của lô 1 sẽ làm con số của lượt đo trông xấu hơn sự thật.
    """
    driver = _load_driver()
    trace = _Trace()
    trace.log.append("dịch 0/115 segment đã có (engine hy-mt-1.5-7b)")
    trace.single(-1)                              # lời gọi thử, id âm
    trace.batch(list(range(0, 30)))
    trace.checkpoint(30, 115)

    rows = driver.echo_by_batch(trace.calls, trace.log)

    assert [(row["batch"], row["items"], row["singleton_calls"]) for row in rows] == [
        (1, 30, 0),
    ]
    assert rows[0]["retried_ids"] == []


def test_the_batch_table_keeps_phases_apart():
    """Lượt D chạy `translate()` HAI lần: lô 4 mục (pha 1) rồi 30/30/30/21 (pha 2).

    Không có nhãn pha thì "lô nhỏ 4 mục" và "một lô 4 mục bình thường" không phân
    biệt được — mà đó đúng là biến số duy nhất của cấu hình D.
    """
    driver = _load_driver()
    trace = _Trace()
    trace.batch([0, 1, 2, 3])
    trace.guard(1, 4)
    trace.single(2)
    trace.checkpoint(4, 115)
    trace.phase = 2
    trace.batch(list(range(4, 34)))
    trace.checkpoint(34, 115)
    trace.batch(list(range(34, 64)))
    trace.checkpoint(64, 115)

    rows = driver.echo_by_batch(trace.calls, trace.log)

    assert [(row["phase"], row["items"], row["echoed"]) for row in rows] == [
        (1, 4, 1), (2, 30, 0), (2, 30, 0),
    ]
