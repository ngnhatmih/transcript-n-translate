"""Kế hoạch CHIA ĐÔI (`scripts/echo_halving.py`) — hàm THUẦN, không model, không mạng.

Vì sao có tệp này
    Lượt đo `20261019-echo-halving` hỏi: khi lô 30 mục bị chép nguyên chữ nguồn,
    VỨT lô rồi dịch lại thành hai nửa có rẻ hơn 89 lời gọi singleton không. Câu
    trả lời chỉ có nghĩa nếu phép chia không làm MẤT hay NHÂN ĐÔI mục nào — nếu
    không thì "0 echo còn lại" của lượt chia có thể chỉ là "dịch thiếu 2 đoạn".
    Các bài dưới ghim đúng phần đó, trên một lô GIẢ, không cần Ollama 5 GB.

Ba tính chất được ghim, theo thứ tự quan trọng
    (a) phép chia giữ NGUYÊN thứ tự và nối lại đúng bằng đầu vào, cho MỌI kích
        thước 1..30 — kể cả mọi đường đi tới lá khi cả cây đều bị chép;
    (b) chỉ có ba lý do dừng (sạch / một mục / chạm trần), và "một mục" trả về
        chính mục đó chứ không trả `[]` — trả rỗng là biến "hết đường chia" thành
        "bỏ lô", đúng thứ cổng echo tồn tại để không xảy ra;
    (c) trần `MAX_DEPTH` mặc định sâu hơn số tầng mà lô 30 cần (5), nên van an
        toàn không bao giờ chạm trong lượt đo này.
"""
from __future__ import annotations

import importlib.util
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "echo_halving.py"


def _load():
    assert SCRIPT.exists(), "brief yêu cầu backend/scripts/echo_halving.py"
    spec = importlib.util.spec_from_file_location("echo_halving_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_clean_batch_costs_no_extra_call():
    """Lô KHÔNG bị chép không được sinh thêm lời gọi nào — đường của phần lớn lô."""
    plan = _load()
    for size in (1, 2, 15, 30):
        assert plan.next_step(list(range(size)), copied=False, depth=0) == (
            plan.CLEAN, [])


def test_an_empty_batch_is_treated_as_clean():
    """Lô rỗng không phải lý do để chia hay để gọi engine."""
    plan = _load()
    assert plan.next_step([], copied=True, depth=0) == (plan.CLEAN, [])


def test_a_copied_batch_of_thirty_splits_into_two_ordered_halves():
    """Ca THẬT của lượt đo: lô 30 bị chép -> đúng hai nửa 15, đúng thứ tự."""
    plan = _load()
    action, subs = plan.next_step(list(range(30)), copied=True, depth=0)
    assert action == plan.SPLIT
    assert [len(sub) for sub in subs] == [15, 15]
    assert [i for sub in subs for i in sub] == list(range(30))


def test_halves_are_contiguous_and_the_first_takes_the_odd_item():
    """Nửa ĐẦU nhận mục lẻ (15 -> 8/7), và hai nửa vẫn là hai KHOẢNG liên tiếp."""
    plan = _load()
    cases = [(30, [15, 15]), (15, [8, 7]), (8, [4, 4]), (7, [4, 3]),
             (3, [2, 1]), (2, [1, 1])]
    for size, want in cases:
        got = plan.halves(list(range(size)))
        assert [len(half) for half in got] == want, size
        assert [i for half in got for i in half] == list(range(size)), size


def test_the_depth_cap_falls_back_to_one_item_per_batch():
    """Chạm trần độ sâu: hạ xuống TỪNG mục (không mất mục, không đổi thứ tự)."""
    plan = _load()
    action, subs = plan.next_step(list(range(15)), copied=True, depth=2,
                                  max_depth=2)
    assert action == plan.DEPTH
    assert [len(sub) for sub in subs] == [1] * 15
    assert [i for sub in subs for i in sub] == list(range(15))


def test_a_single_copied_item_returns_itself_not_an_empty_plan():
    """Lô MỘT mục bị chép vẫn trả về chính nó: bên gọi phải dịch hoặc từ chối.

    `[]` ở đây sẽ có nghĩa "không còn gì để làm", tức bỏ đoạn — trong khi sự thật
    là mục đó VẪN CHƯA có bản dịch sạch. Ca này là chỗ hạ cấp cuối (`EchoProblem`
    nếu bản dịch một mục cũng chép nguồn).
    """
    plan = _load()
    for depth in (0, 5, 99):
        assert plan.next_step([7], copied=True, depth=depth) == (
            plan.SINGLETON, [[7]])


def test_the_default_depth_cap_is_deeper_than_thirty_needs():
    """30 -> 15 -> 8 -> 4 -> 2 -> 1 là 5 tầng; trần mặc định phải sâu hơn 5."""
    plan = _load()
    depth, size = 0, 30
    while size > 1:
        size = (size + 1) // 2
        depth += 1
    assert depth == 5
    assert plan.MAX_DEPTH > depth, (
        "van an toàn không được chạm trên clip này, nếu không phép đo sẽ hạ xuống "
        "singleton vì lý do kỹ thuật chứ không vì model")


def test_drilling_to_leaves_loses_and_duplicates_nothing():
    """Đường đi TỆ NHẤT: mọi tầng đều bị chép, cho mọi kích thước 1..30.

    Đây là bất biến mà cả lượt đo đứng trên: các lô lá phải phủ ĐÚNG dãy id đầu
    vào, mỗi id đúng một lần, theo thứ tự trái -> phải. Nếu phép chia làm mất một
    mục thì "0 echo còn lại" của lượt chia là một con số vô nghĩa.
    """
    plan = _load()
    for size in range(1, 31):
        items = list(range(100, 100 + size))
        found = plan.leaves(items)
        assert [i for sub in found for i in sub] == items, size
        assert all(len(sub) == 1 for sub in found), size
        assert len(found) == size, size
