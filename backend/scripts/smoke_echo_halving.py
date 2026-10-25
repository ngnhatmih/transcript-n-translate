"""Lượt đo CHIA ĐÔI lô bị chép nguồn: đối chứng / chia đôi / lô 15 thẳng.

Câu hỏi của lượt đo (một câu, và nó KHÔNG phải "cổng có chạy không")
    Trên clip 115 đoạn với `hy-mt-1.5-7b`, lô 30 mục bị chép nguyên chữ nguồn ở
    CẢ BA lô đủ 30 mục — `29/30`, `30/30`, `30/30` — và lô 25 mục cuối sạch
    (`artifact 20261019-echo-warmup/`). Id bị chép luôn là "mọi segment của lô trừ
    đoạn 9" (`2288`, số thuần nên `echoes_source` không tính), nên đây là một CHẾ
    ĐỘ CỦA LÔ chứ không phải một tỉ lệ theo đoạn. Cách chữa hiện tại
    (`_guard_echoes`) làm việc ở SAI ĐỘ PHÂN GIẢI: nó dịch lại TỪNG ĐOẠN
    (89 lời gọi singleton, 78,85–83,03 s) trong khi cái bị hỏng là cả lô.

    Giả thuyết: nếu chế độ chép nguồn bị kích hoạt bởi ĐỘ DÀI / THÀNH PHẦN của
    lô, thì VỨT lô bị chép và dịch lại nó thành HAI NỬA sẽ thoát chế độ đó với ít
    lời gọi hơn nhiều — 3 lời gọi cho một lô 30 (1 lô + 2 nửa 15) thay vì 30 lời
    gọi singleton. Nếu các nửa CŨNG bị chép thì phép chia đi tiếp
    15 -> 8/7 -> 4/3 -> ... và cây chia là BẰNG CHỨNG ÂM TÍNH: chế độ đó không
    phải chuyện độ dài.

Ba cấu hình, mỗi cấu hình MỘT tiến trình (model phải NGUỘI ở mỗi đầu lượt)
    control · lô 30, cổng echo dịch lại từng đoạn (đường ĐANG SHIP) — phải tái
        lập `89` lần dịch lại và pattern `29/30 -> 30/30 -> 30/30 -> 0/25`;
    halving · lô 30, nhưng khi một lô bị chép thì CHIA ĐÔI và dịch lại từng nửa
        (đệ quy), chỉ hạ xuống một mục khi lô đã là MỘT mục — xem
        `scripts/echo_halving.py` và `_HalvingHandler`;
    half-straight · lô 15 cho cả clip, cổng như cũ — để trả lời "nửa 15 có đơn
        giản là hành xử như một lô 15 bình thường không", tức phép chia có lợi
        thế nào so với việc hạ hẳn kích thước lô.

SỐ ĐO (cùng clip 115 đoạn, cùng 5 thuật ngữ, prompt v0, `echo_guard` BẬT, mỗi
cấu hình một tiến trình, `/api/ps` rỗng trước mỗi lượt; artifact ở
`data/experiments/accuracy-pipelines/20261019-echo-halving/`):

    cấu hình                    | dịch lại 1 mục | tổng lời gọi | lô hỏng | echo còn lại | chữ Hán | giây
    control · lô 30 (đang ship) | 89             | 93           | 0       | 0            | 0       | 78,91
    halving · lô 30, chia đôi   | 7              | 25           | 0       | 0            | 0       | 95,72
    half-straight · lô 15 thẳng | 29             | 37           | 0       | 0            | 0       | 59,09
    (lặp halving)               | 7              | 24           | 0       | 0            | 0       | 88,67

* **Đối chứng tái lập đúng** pattern đã ghim: `29/30 -> 30/30 -> 30/30 -> 0/25`,
  89 lần dịch lại, 89 lời gọi singleton (93 lời gọi cả lượt), 78,91 s. Nên bốn
  cột của bảng trên so được với nhau.
* **Chia đôi THOÁT được echo nhưng KHÔNG rẻ**: 0 echo còn lại, 0 `EchoProblem`,
  115/115 đoạn `done`, và **7/7** lời gọi một mục là HẠ CẤP ALIGNMENT (nửa 7 mục
  của lô 60–89 trả 6/7 mục HAI lần rồi mới hạ xuống từng mục), **không** phải cổng
  echo dịch lại đoạn nào. Nhưng 25 lời gọi vẫn trên mục tiêu "< ~20", và wall time
  **95,72 s** tệ hơn đối chứng vì lượt chia dịch **287 mục-lượt** (tổng số mục của
  mọi lời gọi, kể cả lô 30 bị vứt) so với 204 của đối chứng.
* **Chế độ chép nguồn không phải "lô 30 mục"**: các nửa CŨNG bị chép — ở 15 mục,
  5/14 lô bị chép (2/8 lô của lượt 15 thẳng + 3/6 nửa của lượt chia); ở 8 mục, 1/2;
  ở 4 mục, 0/2. Tức nó bám vào LỜI GỌI với xác suất tăng theo độ dài, không phải
  một ngưỡng mà phép chia cắt qua được — nên phép chia chỉ rẻ khi nửa ĐẦU TIÊN
  tình cờ sạch, và đó là tung đồng xu.
* Cây chia của lượt chính (lặp lại y hệt ở lượt lặp — xem `repeat-halving/`):

      lô 30 chép 29/30 -> 15 chép 14/15 -> 8 sạch, 7 sạch
                                        15 sạch
      lô 30 chép 30/30 -> 15 sạch, 15 sạch
      lô 30 chép 30/30 -> 15 chép 15/15 -> 8 chép 8/8 -> 4 sạch, 4 sạch
                                        7 lệch alignment 6/7 hai lần -> 7 mục một mình
                                        15 sạch
      lô 25 chép 0/25  -> sạch

  Tổng: 3 lô bị chép, 22 lời gọi theo nút (mỗi lô gốc tính cả lời gọi 30 mục đã
  bị vứt), sâu nhất 3 tầng, 0 nút `echo_problem`. `llm_calls` = 25 vì còn 1 lời
  gọi của lô 25 (không sinh cây) và 2 lần thử lại alignment (một ở lô 30 gốc của
  lô thứ hai, một ở nửa 7 mục); `tree_stats.calls` đếm theo NÚT nên nhỏ hơn đúng
  bằng hai lần thử lại đó.

Kết luận của lượt đo: **không nối phép chia vào sản phẩm**. Con số quyết định là
wall time — 95,72 s và 88,67 s so với 78,91 s của đường đang ship (và 59,09 s của
lô 15 thẳng): phép chia chỉ rẻ hơn về SỐ LỜI GỌI, còn thời gian thì tệ hơn, vì nó
dịch lại cả lô 30 vừa bị vứt. Ghi chú để lượt sau: mọi lời gọi **25 mục** đo được
tới nay đều sạch (0/25 ở cả ba lượt đối chứng và 0/25 ở hai lượt chia), nhưng lô
25 là ĐUÔI của clip trong MỌI lượt nên độ dài và nội dung còn lẫn nhau — muốn coi
đó là ngưỡng thì phải đo một phép chia 25/5, không phải phép chia đôi.

Vì sao mỗi cấu hình một tiến trình
    `guard.run_one` gọi `engine.release()` ở cuối (đổ model khỏi VRAM), nhưng
    `keep_alive` 30 phút của Ollama vẫn giữ model nếu lượt sau chạy quá nhanh;
    lượt đo sưởi đã ghim rằng trạng thái VRAM đầu lượt là một biến số của kết
    quả v0 (`model_loaded_before` trong artifact). Ba lượt trong BA tiến trình
    làm trạng thái đó giống nhau ở cả ba, và artifact ghi lại nó.

Vì sao KHÔNG sửa `pipeline/translate.py`
    Phép chia là GIẢ THUYẾT đang được đo, không phải một cải tiến đã có số. Toàn
    bộ cơ chế nằm ở `_HalvingHandler` — một lớp CON của `TranslateHandler` override
    `_guard_echoes` — nên đường ship không đổi từng byte, và nếu số đo không đạt
    thì xoá tệp này là xong (không có nhánh chết nào ở lại trong sản phẩm).

Không thuộc bộ pytest: cần Ollama + model thật (~5 GB VRAM). Phần THUẦN của phép
chia (`scripts/echo_halving.py`) thì có test riêng (`tests/test_echo_halving.py`).

Ví dụ (mỗi lệnh một tiến trình; `summary.json` được dựng lại sau MỖI lượt từ các
artifact đã có trong `--out-dir`):

    python -B scripts\\smoke_echo_halving.py --configs control \\
        --transcript ..\\data\\experiments\\accuracy-pipelines\\20261019-name-patch-smoke\\large-v3-beam5-prevfalse.json \\
        --glossary ..\\data\\experiments\\accuracy-pipelines\\20261019-term-placeholder-smoke\\glossary.json \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\20261019-echo-halving
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import echo_halving  # noqa: E402 - sau sys.path
import smoke_echo_guard as guard  # noqa: E402 - sau sys.path

from app.domain.alignment import AlignmentProblem, check_alignment  # noqa: E402
from app.domain.mt_qa import echoes_source  # noqa: E402
from app.pipeline.translate import EchoProblem, TranslateHandler  # noqa: E402

#: Ba cấu hình của lượt đo. `artifact` là tên tệp RIÊNG của từng cấu hình: hai
#: cấu hình cùng lô 30 (`control` và `halving`) sẽ ghi đè nhau nếu dùng tên mặc
#: định của `smoke_echo_guard` (`batch-30.json`), và khi đó phép so mất một vế.
CONFIGS: dict[str, dict] = {
    "control": {
        "batch_items": 30, "halving": False,
        "artifact": "control-batch-30.json",
        "note": "đối chứng: lô 30, cổng echo dịch lại TỪNG ĐOẠN (đường đang ship)",
    },
    "halving": {
        "batch_items": 30, "halving": True,
        "artifact": "halving-batch-30.json",
        "note": "lô 30, lô bị chép thì vứt và dịch lại thành HAI NỬA (đệ quy)",
    },
    "half-straight": {
        "batch_items": 15, "halving": False,
        "artifact": "half-straight-batch-15.json",
        "note": "so sánh: cả clip ở lô 15 thẳng, cổng như cũ",
    },
}


def _node(items: list, depth: int) -> dict:
    """Một nút của cây thử: lô nào, tầng nào, và các lời gọi của CHÍNH nút này."""

    return {"depth": depth, "items": len(items), "ids": [s.i for s in items],
            "echoed": 0, "echoed_ids": [], "action": None, "calls": [],
            "children": []}


def _echoed(items: list, out: list, opts) -> list:
    """Các segment của `out` vẫn CHÉP nguyên chữ nguồn — ĐÚNG phép đo của cổng.

    Dùng `mt_qa.echoes_source` với cùng hai ngôn ngữ mà cổng of the handler dùng
    (`opts.source_lang`/`opts.target_lang`): một phép đo thứ hai ở đây sẽ làm
    "echo còn lại" của lượt đo không so được với cổng.
    """
    by_id = {s.i: s for s in items}
    return [s for s in out
            if s.i in by_id
            and echoes_source(by_id[s.i].text, s.text,
                              source_lang=getattr(opts, "source_lang", "zh"),
                              target_lang=getattr(opts, "target_lang", "vi"))]


class _HalvingHandler(TranslateHandler):
    """`TranslateHandler` với bước (a4') ĐỔI: chia đôi thay vì dịch lại từng đoạn.

    Chỉ override `_guard_echoes`. Mọi thứ khác — batching, `check_alignment`,
    `EchoProblem`, `llm_calls`, bảo vệ thuật ngữ, checkpoint — là của sản phẩm và
    KHÔNG bị chạm, nên phép so "control vs halving" chỉ khác đúng một biến: cách
    phản ứng khi một lô bị chép nguồn.

    Cây thử được ghi lại theo từng LÔ GỐC (mỗi lần `_guard_echoes` được gọi trên
    một lô bị chép): nút gốc là lô 30 đã bị chép, con là hai nửa 15, v.v. Đây là
    bằng chứng mà cả lượt đo tồn tại để tạo ra — "nửa 15 có sạch không" chỉ trả
    lời được bằng cây, không bằng một con số tổng.

    `instances` cấp LỚP: driver chạy MỘT lượt mỗi tiến trình (xem docstring tệp),
    nên một danh sách là đủ để lấy cây sau lượt; nó KHÔNG phải registry thứ hai
    của sản phẩm (`_han dler` dựng handler một lần mỗi lượt).
    """

    instances: list["_HalvingHandler"] = []

    def __init__(self, *args, max_depth: int = echo_halving.MAX_DEPTH, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_depth = int(max_depth)
        self.trees: list[dict] = []
        _HalvingHandler.instances.append(self)

    # -- một lời gọi engine + alignment ------------------------------------

    def _call(self, engine, items, glossary, opts, node: dict, *, facts, job,
              report, progress):
        """MỘT lời gọi engine qua đúng chính sách alignment của handler.

        Giống bước (a) của `_translate_batch_impl`: thử hai lần khi lệch
        alignment/dị dạng, và MỖI lần chạm engine để lại một hàng `llm_calls`
        (kể cả lần hỏng) — nếu không thì `llm_calls` của lượt đo không bằng số
        lời gọi thật và cột "tổng lời gọi" là một con số trang trí.

        Trả `None` khi lô hỏng alignment HAI lần; bên gọi hạ xuống từng mục đúng
        như bước (b) của handler, chứ không ném — ném ở đây sẽ giết cả lượt đo vì
        một lô 4 mục lệch, trong khi câu hỏi của lượt đo là về ECHO.
        """
        node["calls"].append({"items": len(items), "ids": [s.i for s in items]})
        for attempt in (1, 2):
            try:
                out = engine.translate(items, glossary, opts)
            except (AlignmentProblem, ValueError) as exc:
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                report(progress, f"echo_halving: lô {len(items)} mục lệch "
                                 f"alignment (lần {attempt}): {exc}")
                continue
            except Exception as exc:      # noqa: BLE001 - hàng đếm PHẢI có mặt
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                raise
            try:
                check_alignment(items, out)
            except AlignmentProblem as exc:
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                report(progress, f"echo_halving: lô {len(items)} mục lệch "
                                 f"alignment (lần {attempt}): {exc.reason}")
                continue
            self._record_call(engine, facts, job, None,
                              getattr(engine, "last_stats", None))
            return out
        return None

    def _singletons(self, engine, items, glossary, opts, node: dict, *, facts,
                    job, report, progress) -> list:
        """Hạ cấp cuối: mỗi mục một lời gọi, đúng hình dạng bước (b) của handler.

        Dùng ở hai chỗ: lô lớn hỏng alignment hai lần, và chạm trần độ sâu. Mỗi
        mục vẫn phải qua cổng echo: một mục là bản chép thì cả lô bị từ chối
        (`EchoProblem`) — đây chính là "chỉ hạ xuống singleton khi không còn gì
        nhỏ hơn", và nếu ngay singleton cũng chép thì chế độ đó không còn là
        chuyện của lô nữa.
        """
        collected: list = []
        for item in items:
            child = _node([item], node["depth"] + 1)
            child["action"] = "singleton"
            node["children"].append(child)
            out = self._call(engine, [item], glossary, opts, child, facts=facts,
                             job=job, report=report, progress=progress)
            if out is None:
                child["action"] = "alignment_problem"
                raise EchoProblem([item.i], echoed=1, batch=len(items),
                                  reason=(f"segment {item.i}: hạ cấp một mục vẫn "
                                          f"hỏng alignment"))
            echoing = _echoed([item], out, opts)
            child["echoed"] = len(echoing)
            child["echoed_ids"] = [s.i for s in echoing]
            if echoing:
                child["action"] = "echo_problem"
                raise EchoProblem([item.i], echoed=1, batch=len(items),
                                  reason=(f"segment {item.i} vẫn là bản chép "
                                          f"nguồn khi dịch MỘT MÌNH — chế độ "
                                          f"không phải chuyện độ dài lô"))
            collected.extend(out)
        return collected

    def _solve(self, engine, items, node: dict, glossary, opts, *, facts, job,
               report, progress) -> list:
        """Dịch `items`, và nếu bị chép thì chia đôi (đệ quy) cho tới khi sạch.

        Đây là toàn bộ phép đo: một lời gọi cho lô, đọc kết quả, và chỉ đi tiếp
        nếu lô ĐÓ bị chép. Lô sạch dừng tại đây — đó là lý do phép chia có thể rẻ
        hơn 30 lời gọi singleton rất nhiều.
        """
        out = self._call(engine, items, glossary, opts, node, facts=facts, job=job,
                         report=report, progress=progress)
        if out is None:
            node["action"] = "singleton_fallback"
            return self._singletons(engine, items, glossary, opts, node,
                                    facts=facts, job=job, report=report,
                                    progress=progress)
        echoing = _echoed(items, out, opts)
        node["echoed"] = len(echoing)
        node["echoed_ids"] = [s.i for s in echoing]
        if not echoing:
            node["action"] = "clean"
            return out
        action, subs = echo_halving.next_step(
            [s.i for s in items], copied=True, depth=node["depth"],
            max_depth=self.max_depth)
        node["action"] = action
        if action == echo_halving.SINGLETON:
            # Lô MỘT mục vừa dịch vẫn chép: đây là chỗ hạ cấp cuối, và nó đã hỏng
            # — nên nút mang `echo_problem`, không phải `singleton` (một lời gọi
            # một mục THÀNH CÔNG cũng là `singleton`, và hai thứ đó không được
            # cùng một nhãn trong cây).
            node["action"] = "echo_problem"
            raise EchoProblem([items[0].i], echoed=1, batch=len(items),
                              reason=(f"segment {items[0].i} vẫn là bản chép "
                                      f"nguồn ở lô MỘT mục"))
        if action == echo_halving.DEPTH:
            return self._singletons(engine, items, glossary, opts, node,
                                    facts=facts, job=job, report=report,
                                    progress=progress)
        by_id = {s.i: s for s in items}
        collected: list = []
        for sub_ids in subs:
            sub = [by_id[i] for i in sub_ids]
            child = _node(sub, node["depth"] + 1)
            node["children"].append(child)
            collected.extend(self._solve(engine, sub, child, glossary, opts,
                                         facts=facts, job=job, report=report,
                                         progress=progress))
        return collected

    # -- bước (a4') của handler -------------------------------------------

    def _guard_echoes(self, engine, batch, out, glossary, opts, report, progress,
                      *, facts, job=None):
        """Cổng echo thay bằng phép chia đôi: vứt lô bị chép, dịch lại hai nửa.

        Lô KHÔNG bị chép đi đường cũ từng byte (`return out, []`, không một lời
        gọi thêm) — cùng luật với `_guard_echoes` của sản phẩm, nên phần lớn lô
        của clip không bị phép đo này làm chậm.

        Lô bị chép: lời gọi cả lô ĐÃ xảy ra rồi (handler ghi nó trước khi gọi
        bước này), nên nó là NÚT GỐC của cây; hai nửa mới là các lời gọi tiếp
        theo. Nhờ vậy tổng lời gọi trong artifact đếm được cả lời gọi đã bị vứt —
        nếu không thì "tổng lời gọi" của phép chia trông rẻ hơn sự thật đúng một
        lời gọi mỗi lô bị chép.

        Dòng log dùng tiền tố `echo_halving:` chứ KHÔNG phải `echo_guard:`, và đó
        là chủ ý: `smoke_echo_guard` cộng các dòng `echo_guard:<n>/<m>` thành
        `guard_retried`; phép chia không dịch lại đoạn nào một mình, nên để nó
        cộng vào cùng cột đó là nói dối về cơ chế (89 của đối chứng là 89 lời gọi
        singleton THẬT).
        """
        echoing = _echoed(batch, out, opts)
        if not echoing:
            return out, []
        report(progress, f"echo_halving:{len(echoing)}/{len(batch)} đoạn chép "
                         f"nguyên chữ nguồn: vứt lô, dịch lại thành hai nửa")
        root = _node(batch, 0)
        root["echoed"] = len(echoing)
        root["echoed_ids"] = [s.i for s in echoing]
        # Lời gọi CẢ LÔ đã xảy ra rồi (handler ghi nó TRƯỚC khi gọi bước này) và
        # nó đã bị VỨT. Ghi nó vào nút gốc để `_count_calls` = tổng lời gọi THẬT
        # của lô gốc: bỏ nó đi thì phép chia trông rẻ hơn sự thật đúng một lời
        # gọi mỗi lô bị chép, tức đúng cột mà lượt đo này dùng để kết luận.
        root["calls"].append({"items": len(batch), "ids": list(root["ids"]),
                              "bị_vứt": True})
        self.trees.append(root)
        action, subs = echo_halving.next_step(
            [s.i for s in batch], copied=True, depth=0, max_depth=self.max_depth)
        if action == echo_halving.SINGLETON:
            root["action"] = "echo_problem"
            raise EchoProblem([batch[0].i], echoed=1, batch=len(batch),
                              reason=(f"segment {batch[0].i} vẫn là bản chép "
                                      f"nguồn ở lô MỘT mục"))
        if action == echo_halving.DEPTH:
            root["action"] = action
            return self._singletons(engine, batch, glossary, opts, root,
                                    facts=facts, job=job, report=report,
                                    progress=progress), []
        root["action"] = "split"
        by_id = {s.i: s for s in batch}
        collected: list = []
        for sub_ids in subs:
            sub = [by_id[i] for i in sub_ids]
            child = _node(sub, 1)
            root["children"].append(child)
            collected.extend(self._solve(engine, sub, child, glossary, opts,
                                         facts=facts, job=job, report=report,
                                         progress=progress))
        if len(collected) != len(batch):
            # Bất biến của CẢ phép đo: phép chia không được làm mất hay nhân đôi
            # mục nào (test `test_drilling_to_leaves_loses_and_duplicates_nothing`
            # ghim phần THUẦN; đây là chốt ở chỗ chạy thật).
            raise RuntimeError(
                f"phép chia trả {len(collected)}/{len(batch)} mục — mất hoặc "
                f"nhân đôi mục, lượt đo không dùng được")
        report(progress, f"echo_halving: đã dịch lại {len(batch)} đoạn bằng "
                         f"{_count_calls(root)} lời gọi (cây chia ở artifact)")
        return collected, []


def _count_calls(node: dict) -> int:
    """Số lời gọi của cả cây dưới `node` (kể cả lời gọi của chính nó)."""
    return len(node["calls"]) + sum(_count_calls(child) for child in node["children"])


def _walk(node: dict):
    yield node
    for child in node["children"]:
        yield from _walk(child)


def _tree_stats(trees: list[dict]) -> dict:
    """Tóm tắt cây: bao nhiêu nút, bao nhiêu lần chia, sâu tới đâu, bao nhiêu lá."""
    nodes = [node for root in trees for node in _walk(root)]
    leaves = [node for node in nodes if not node["children"]]
    return {
        "copied_batches": len(trees),
        "nodes": len(nodes),
        "splits": sum(1 for node in nodes if node["action"] == "split"),
        "clean_nodes": sum(1 for node in nodes if node["action"] == "clean"),
        "leaf_singletons": sum(1 for node in leaves if node["items"] == 1),
        "echo_problem_nodes": sum(1 for node in nodes
                                  if node["action"] == "echo_problem"),
        "max_depth_reached": max((node["depth"] for node in nodes), default=0),
        "depth_histogram": {str(depth): sum(1 for node in nodes
                                            if node["depth"] == depth)
                            for depth in sorted({node["depth"]
                                                 for node in nodes})},
        "calls": sum(_count_calls(root) for root in trees),
    }


def _by_batch(trees: list[dict]) -> list[dict]:
    """Bảng theo LÔ GỐC, dựng từ cây — dạng so được với `echo_by_batch` của đối chứng.

    `smoke_echo_guard.echo_by_batch` mở một hàng cho MỖI lời gọi `size > 1`, nên
    trên một lượt chia nó sẽ coi nửa 15 là "một lô mới" — đúng phép đếm cho đường
    ship, sai câu hỏi ở đây. Bảng này gộp cả cây về lô gốc đã sinh ra nó.
    """
    rows = []
    for index, root in enumerate(trees, start=1):
        leaves = [node for node in _walk(root) if not node["children"]]
        rows.append({
            "batch": index,
            "items": root["items"],
            "ids": list(root["ids"]),
            "echoed_at_entry": root["echoed"],
            "batches_tried": len(list(_walk(root))),
            "calls": _count_calls(root),
            "leaf_singletons": sum(1 for node in leaves if node["items"] == 1),
            # "clean" = MỌI lá của cây ra bản dịch sạch: lá `clean` (lô sạch) hoặc
            # lá `singleton` (hạ cấp một mục đã sạch — nếu chính nó echo thì
            # `EchoProblem` đã nổ và artifact `done` này không tồn tại). "failed"
            # chỉ dành cho lá `echo_problem`/`alignment_problem`.
            "outcome": "clean" if all(
                node["action"] in ("clean", "singleton") for node in leaves)
                       else "failed",
            "attempts": [{"items": node["items"], "depth": node["depth"],
                          "echoed": node["echoed"], "action": node["action"]}
                         for node in _walk(root)],
        })
    return rows


def _label(node: dict) -> str:
    if node["action"] == "clean":
        return "sạch"
    if node["action"] == "split":
        return f"chép {node['echoed']}/{node['items']} -> chia đôi"
    if node["action"] == "singleton":
        return "dịch một mục"
    if node["action"] == "singleton_fallback":
        return "hỏng alignment hai lần -> hạ xuống dịch từng mục"
    if node["action"] == "echo_problem":
        return f"chép {node['echoed']}/{node['items']} -> EchoProblem (một mục vẫn chép)"
    if node["action"] == "alignment_problem":
        return "EchoProblem (hỏng alignment khi dịch một mục)"
    return f"chép {node['echoed']}/{node['items']} -> {node['action']}"


def _print_node(node: dict, indent: str) -> None:
    print(f"{indent}└ {node['items']} mục (tầng {node['depth']}): {_label(node)}",
          flush=True)
    for child in node["children"]:
        _print_node(child, indent + "   ")


def _print_tree(trees: list[dict]) -> None:
    print("\n  CÂY CHIA (mỗi lô gốc là một lần bị chép; con là các nửa đã thử):",
          flush=True)
    if not trees:
        print("  (không lô nào bị chép — không có cây)", flush=True)
        return
    for index, root in enumerate(trees, start=1):
        print(f"  lô gốc {index}: {root['items']} mục, chép "
              f"{root['echoed']}/{root['items']} -> {_label(root)}", flush=True)
        for child in root["children"]:
            _print_node(child, "  ")


# ---------------------------------------------------------------------------
# Chạy MỘT cấu hình + dựng `summary.json` từ các artifact đã có
# ---------------------------------------------------------------------------

def run_config(transcript: pathlib.Path, glossary: pathlib.Path,
               out_dir: pathlib.Path, config: str,
               max_depth: int = echo_halving.MAX_DEPTH,
               unload: bool = True) -> dict:
    plan = CONFIGS[config]
    handler_cls = _HalvingHandler if plan["halving"] else TranslateHandler
    kwargs = {"max_depth": max_depth} if plan["halving"] else {}
    result = guard.run_one(
        transcript, glossary, out_dir, plan["batch_items"],
        handler_cls=handler_cls, artifact_name=plan["artifact"],
        handler_kwargs=kwargs, unload=unload)
    result["config"] = config
    result["config_note"] = plan["note"]
    if plan["halving"]:
        handler = _HalvingHandler.instances[-1]
        result["attempt_tree"] = handler.trees
        result["tree_stats"] = _tree_stats(handler.trees)
        result["halving_by_batch"] = _by_batch(handler.trees)
        result["max_depth"] = max_depth
        # `echo_by_batch` của `run_one` mở một hàng cho mỗi lời gọi `size > 1`,
        # nên ở lượt chia nó KHÔNG phải bảng theo lô gốc; ghi rõ để người đọc
        # artifact không đọc nhầm nó thành bảng của đối chứng.
        result["echo_by_batch_note"] = (
            "lượt CHIA ĐÔI: bảng theo lô gốc là `halving_by_batch`/`attempt_tree`; "
            "`echo_by_batch` ở đây coi mỗi lời gọi size>1 là một lô nên không "
            "dùng để so với đối chứng")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / plan["artifact"]).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _load_rows(out_dir: pathlib.Path) -> list[dict]:
    """Đọc lại artifact của cả ba cấu hình (cấu hình đã chạy thì mới có hàng).

    Đọc từ TỆP chứ không từ biến trong bộ nhớ: mỗi cấu hình là một tiến trình
    riêng, nên `summary.json` chỉ đúng nếu nó được dựng từ thứ đã ghi ra đĩa.
    """
    rows = []
    for config, plan in CONFIGS.items():
        path = out_dir / plan["artifact"]
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append({
            "config": config,
            "batch_items": data["batch_items"],
            "singleton_calls": data["singleton_calls"],
            "llm_calls": data["llm_calls"],
            "batch_calls": data["batch_calls"],
            "guard_retried": data["guard_retried"],
            "echo_problem_batches": data["echo_problem_batches"],
            "accepted_segments": data["accepted_segments"],
            "echo_segments_guard": data["echo_segments_guard"],
            "echo_segments_qa": data["echo_segments_qa"],
            "han_chars": data["han_chars"],
            "qa_lang": data["qa_lang"],
            "seconds": data["seconds"],
            "translation_status": data["translation_status"],
            "error_type": (data["error"] or {}).get("type"),
            "tree_stats": data.get("tree_stats"),
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="smoke_echo_halving.py")
    parser.add_argument("--transcript", type=pathlib.Path, required=True)
    parser.add_argument("--glossary", type=pathlib.Path, required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--configs", nargs="+", choices=list(CONFIGS),
                        default=["control"], help="cấu hình cần chạy; đề nghị MỖI "
                        "cấu hình một lần gọi tiến trình (xem docstring)")
    parser.add_argument("--max-depth", type=int, default=echo_halving.MAX_DEPTH,
                        help="trần số tầng chia của cấu hình halving (mặc định "
                             "theo `echo_halving.MAX_DEPTH`)")
    args = parser.parse_args(argv)

    for config in args.configs:
        plan = CONFIGS[config]
        print(f"\n=== {config} · lô {plan['batch_items']} "
              f"· chia đôi={plan['halving']} ===", flush=True)
        print(f"    ({plan['note']})", flush=True)
        result = run_config(args.transcript, args.glossary, args.out_dir, config,
                            max_depth=args.max_depth)
        guard._print_batches(config, result["echo_by_batch"])
        if plan["halving"]:
            _print_tree(result["attempt_tree"])
            print(f"  tóm tắt cây: {result['tree_stats']}", flush=True)
        if result["error"]:
            print(f"  LỖI: {result['error']}", flush=True)

    rows = _load_rows(args.out_dir)
    summary = {"experiment": "echo-halving", "rows": rows,
               "max_depth": args.max_depth}
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print("\n| cấu hình | lô | dịch lại 1 mục | tổng lời gọi | lời gọi cả lô | "
          "lô hỏng | echo còn lại | chữ Hán | QA lang | giây |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        print(f"| {row['config']} | {row['batch_items']} | "
              f"{row['singleton_calls']} | {row['llm_calls']} | "
              f"{row['batch_calls']} | {row['echo_problem_batches']} | "
              f"{row['echo_segments_guard']} | {row['han_chars']} | "
              f"{row['qa_lang']} | {row['seconds']} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
