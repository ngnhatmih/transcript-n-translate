"""Smoke THẬT của **echo guard**: dịch cả clip bằng `hy-mt-1.5-7b` qua đường đã ship.

Đây KHÔNG phải một driver thứ hai: mỗi lượt đi qua `TranslateHandler` của sản phẩm
(cùng `_guard_echoes`, cùng `mt_qa.echoes_source`, cùng repo trong bộ nhớ của
`smoke_term_placeholder`), với engine Ollama THẬT và glossary THẬT. Tệp này chỉ
làm ba việc mà handler không làm: bắt `EchoProblem` để báo cáo thay vì chết, đếm
hình dạng lời gọi, và gom số đo thành artifact.

Vì sao phải có một smoke như vậy
    Cổng này là thứ chặn một lỗi ÂM THẦM: ở lô 30, `hy-mt-1.5-7b` trả nguyên chữ
    Trung cho 59–89/115 đoạn, số mục vẫn khớp nên `check_alignment` cho qua, và
    hàng `translations` vẫn `done`. Một test giả không chứng minh được rằng model
    THẬT dịch sạch khi được gọi lại một mình — đó là con số duy nhất phép đo này
    trả lời, và nó phải chạy trên clip thật.

Vì sao `--batches` chứ không sửa `DEFAULT_MAX_ITEMS`/`max_items_per_call`
    Trần số mục của một lời gọi engine là THAM SỐ của handler
    (`TranslateHandler(batch_items=...)`). Sửa mặc định của sản phẩm để đo rồi sửa
    lại là đổi mặc định hai lần cho một phép đo, và lần quên sửa lại thì mặc định
    đã đổi mà không có số nào bảo vệ. Điểm của phép đo này là: cổng, KHÔNG phải
    kích thước lô, mới là thứ quyết định, nên cùng một clip phải chạy được ở cả
    30/15/8.

Vì sao đếm cả `echo_guard:<n>/<m>` trong log
    Đó là con số DUY NHẤT do chính cổng in ra (tiền tố ổn định, grep được trong
    `jobs` log khi chạy thật), nên smoke đối chiếu nó với hình dạng lời gọi thay vì
    tin một bộ đếm riêng của kịch bản.

Số đo (clip 115 đoạn, 5 thuật ngữ, cùng prompt; artifact ở
`data/experiments/accuracy-pipelines/20261019-echo-guard/`):

    lô | lô hỏng (EchoProblem) | đoạn dịch lại | lời gọi cả lô | lời gọi 1 mục | echo còn lại | chữ Hán | giây
    30 | 0                     | 89            | 4             | 89            | 0            | 0       | 78,85
    15 | 0                     | 29            | 8             | 29            | 0            | 0       | 57,72
     8 | 0                     | 7             | 17            | 15            | 0            | 2       | 61,00

Ba kết luận mà bảng đó trả lời:

* **Cổng, không phải kích thước lô, là thứ quyết định.** Ở cùng một clip, số lô
  hỏng là 0 ở CẢ BA lô: mọi đoạn bị chép đều dịch lại được khi gọi một mình —
  đúng số đo "lô 1 cho 0/115 đoạn echo" đã dùng để chọn hình dạng lời gọi.
* **Không có bản dịch nào `done` mà còn chép nguồn.** `echo` theo cổng là 0/115 ở
  cả ba lô (trước bản này: 59–89/115 ở lô 30, tức 389–629 chữ Hán). Ở lô 8 còn
  **2** chữ Hán — `不到路费2000` -> `不到2000`, tỉ lệ Hán 2/6 = 0,33 DƯỚI ngưỡng
  0,5 nên cổng cố ý không chặn (đó là ca "sót chữ Hán", QA báo `lang:27`), không
  phải ca "chép cả câu".
* **Giá của cổng ĐẾM ĐƯỢC.** Lô 30 tốn 78,85 s thay vì 32,89 s vì 89 lời gọi
  singleton; lô 15 chỉ tốn 29 lời gọi (57,72 s). Con số này là lý do cổng bật bằng
  DỮ LIỆU của từng engine chứ không bật cho mọi engine.

Lưu ý: "lời gọi 1 mục" ở lô 8 là 15 = **7** lần cổng dịch lại + **8** lần hạ cấp
alignment của lô (đo được 2 lần lệch `engine trả 7/6 mục, cần 8` trong lượt này),
không phải 15 lần cổng.

Không thuộc bộ pytest: cần Ollama + model thật (~5 GB VRAM), không có bài test giả
nào thay được nó.

Quét BIẾN THỂ PROMPT (`--styles`, lượt đo `20261019-prompt-echo-sweep`)
    Cùng driver, cùng clip, cùng lô 30, cùng cổng; thứ đổi là MỘT chuỗi prompt,
    chọn bằng hatch `prompts.EXPERIMENT_PROMPT_STYLE_ENV` mà tệp này đặt cho từng
    lượt chạy (`v0` = mặc định, `v1`/`v2`/`v3` = biến thể). Không thêm driver thứ
    hai vì câu hỏi của lượt này là "cổng còn phải dịch lại bao nhiêu đoạn", và
    con số đó chỉ có nghĩa khi đi qua ĐÚNG `TranslateHandler` như lượt trước —
    một script gọi thẳng `engine.chat` sẽ không có `echo_guard`, tức không có
    `guard_retried` để so.

    Tên tệp artifact mang style khi style KHÁC mặc định (`v3-batch-30.json`), còn
    lượt mặc định giữ nguyên `batch-30.json` — nếu không thì lần chạy lại một lô
    của lượt cũ sẽ ghi đè artifact của lượt cũ bằng một prompt khác.

    Số đo (lô 30, cùng clip/glossary, artifact ở
    `20261019-prompt-echo-sweep/`):

        style | đoạn phải dịch lại | lô hỏng | echo còn lại | chữ Hán | QA lang | giây
        v0    | 89                | 0       | 0            | 0       | 0       | 83,03
        v1    | 89                | 0       | 0            | 0       | 0       | 76,01
        v2    | 29                | 0       | 0            | 0       | 0       | 68,16
        v3    | 0                 | 1       | 0            | 0       | 0       | 32,92

    Cột `QA lang` = 0 ở cả bốn lượt: không bản dịch nào bị QA báo `lang:` sau khi
    cổng dọn xong. (Còn ĐÚNG MỘT cờ `is_echo` — đoạn 9, nguồn `2288`, đích
    `2288` — ở cả bốn lượt VÀ ở artifact `20261019-echo-guard/` cũ: đó là số thuần
    giữ nguyên, tức phép đo của QA bắt oan, không phải lỗi mới của lượt này.)

    V3 là lượt DUY NHẤT không đi hết đường: nó chết vì lệch alignment (22/30 rồi
    25/30 mục) chứ không phải vì echo, nên "0 đoạn dịch lại" của nó không so được
    với ba lượt kia.

ĐẾM ECHO THEO TỪNG LÔ + SƯỞI (`--configs`, lượt đo `20261019-echo-warmup`)
    Lượt trước chỉ có MỘT con số cho cả lượt, nên kết luận "echo nằm ở lô ĐẦU" là
    suy ra từ `guard_lines` in trong log, không phải từ một bảng. Lượt này đo
    thẳng thứ đó: `echo_by_batch()` (hàm THUẦN, có test riêng) ghép hình dạng lời
    gọi (mỗi lời gọi ghi `size`, `ids`, VỊ TRÍ dòng log lúc gọi) với các dòng
    `echo_guard:<n>/<m>` của cổng, nên mỗi lô ra một hàng `(mục, echo, dịch lại,
    chữ Hán)`. Nhờ vậy "echo rải đều" và "echo chỉ ở lô 1" là hai bảng KHÁC NHAU,
    không còn là hai cách đọc cùng một con số tổng.

    Mỗi cấu hình MỘT tiến trình (`--configs A`), vì "lời gọi đầu của phiên" chỉ có
    nghĩa khi tiến trình còn mới:

        A | v0, không sưởi          — đối chứng
        B | v0 + sưởi              — giả thuyết "lời gọi đầu đặc biệt"
        C | v2 + sưởi              — prompt tốt nhất lượt trước + sưởi
        D | v0, lô đầu ÉP CÒN 4 mục — cùng giả thuyết, không cần lời gọi thừa
        E | v2, lô đầu ÉP CÒN 4 mục — thêm SAU khi A–D cho thấy hai điều rời nhau

    B và C đã bị XOÁ khỏi `CONFIGS` cùng seam sưởi của sản phẩm (xem đoạn dưới):
    một cấu hình "bật sưởi" nay không còn gì để bật. Số đo của chúng vẫn là bằng
    chứng trong bảng trên và trong `backend/README.md`, nhưng KHÔNG tái lập được.

    SỐ ĐO (cùng clip 115 đoạn, cùng 5 thuật ngữ, lô 30, `echo_guard` BẬT; artifact
    ở `data/experiments/accuracy-pipelines/20261019-echo-warmup/`):

        cấu hình | dịch lại | EchoProblem | echo còn lại | chữ Hán | QA lang | giây
        A        | 89       | 0           | 0            | 0       | 0       | 77,86
        B        | 89       | 0           | 0            | 0       | 0       | 79,19
        C        | 0 / 29   | 0 / 0       | 0 / 0        | 0 / 0   | 0 / 0   | 56,90 / 71,48
        D        | 29       | 0           | 0            | 0       | 0       | 114,16
        E        | 0        | 0           | 0            | 0       | 0       | 103,91

    Ba điều mà chỉ bảng THEO LÔ mới nói được:

    * **v0 chép nguồn ở MỌI lô đủ 30 mục** — A và B ra y nhau (29/30, 30/30, 30/30,
      0/25), nên "lô đầu" KHÔNG phải biến số của v0; lô duy nhất sạch trong cả bốn
      lượt v0 là lô 25 mục CUỐI. (Đây là chỗ kết luận "29 lần còn lại nằm hết ở lô
      đầu" của lượt trước bị sai: nó đúng với v2, không đúng với v0.)
    * **Echo là COPY CẢ LÔ, không phải một tỉ lệ** — id bị chép luôn là "mọi segment
      của lô trừ đoạn 9" (`2288`, không có chữ Hán nên `echoes_source` không tính).
      Vì vậy "29" KHÔNG phải một con số đặc biệt: nó là 30 trừ đúng đoạn không có
      chữ Hán.
    * **Rủi ro của v2 bám vào lô ĐẦU TIÊN ĐỦ 30 MỤC, không phải "lời gọi đầu"** — D
      cho lô 4 mục sạch rồi lô 30 mục ngay sau đó chép 29/30. Sưởi (C) và nạp model
      sẵn từ ngoài đều cho 0 rồi 29 ở hai lượt lặp: hết rủi ro là chuyện TUNG ĐỒNG
      XU, không phải một cái công tắc.

    Sưởi ĐÃ BỊ XOÁ khỏi sản phẩm, không phải bị quên. Nó từng đi qua đúng seam của
    handler (gọi engine MỘT lần với một câu ngoài clip, vứt đầu ra), bật bằng một
    khoá chép thêm vào `engine_capabilities` để `registry.json` không bị sửa — và
    bảng A–E ở trên là lý do nó bị xoá: sưởi không sửa được v0 (0/2 lượt), chỉ đôi
    khi sạch v2, và lô đầu nhỏ (D/E) không thay được nó. Đường ship không đổi từng
    byte khi xoá vì `registry.json` CHƯA TỪNG khai cờ đó. Muốn đọc lại phép đo:
    `backend/README.md` (mục echo) + artifact `20261019-echo-warmup/`.

    D không có tham số nào trong handler: nó dùng ĐÚNG đường RETRY của sản phẩm
    (`translate` bắt đầu lại từ segment đầu tiên còn thiếu). Giai đoạn 1 chỉ lộ 4
    segment đầu của transcript, nên handler dịch đúng MỘT lô 4 mục và checkpoint;
    giai đoạn 2 lộ cả 115, handler thấy 4 segment đã có và chia 111 đoạn còn lại
    thành 30/30/30/21. Không thêm knob nào vào sản phẩm cho một phép đo.

    `release()` sau MỖI lượt (và `/api/ps` ghi lại trạng thái TRƯỚC lượt) là bắt
    buộc, không phải dọn dẹp: `keep_alive` 30 phút giữ model trong VRAM, nên lượt
    sau sẽ thừa hưởng model ĐÃ NẠP của lượt trước và "sưởi" sẽ không còn gì để
    sưởi. Artifact ghi `model_loaded_before` để lần đọc lại biết điều đó đã được
    kiểm hay chưa.

Ví dụ:
    python -B scripts\\smoke_echo_guard.py --batches 30 15 8 \\
        --transcript ..\\data\\experiments\\accuracy-pipelines\\20261019-name-patch-smoke\\large-v3-beam5-prevfalse.json \\
        --glossary ..\\data\\experiments\\accuracy-pipelines\\20261019-term-placeholder-smoke\\glossary.json \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\20261019-echo-guard

    python -B scripts\\smoke_echo_guard.py --batches 30 --styles v0 v1 v2 v3 \\
        --transcript ..\\data\\experiments\\accuracy-pipelines\\20261019-name-patch-smoke\\large-v3-beam5-prevfalse.json \\
        --glossary ..\\data\\experiments\\accuracy-pipelines\\20261019-term-placeholder-smoke\\glossary.json \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\20261019-prompt-echo-sweep

    python -B scripts\\smoke_echo_guard.py --configs A \\
        --transcript ..\\data\\experiments\\accuracy-pipelines\\20261019-name-patch-smoke\\large-v3-beam5-prevfalse.json \\
        --glossary ..\\data\\experiments\\accuracy-pipelines\\20261019-term-placeholder-smoke\\glossary.json \\
        --out-dir ..\\data\\experiments\\accuracy-pipelines\\20261019-echo-warmup
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
import types

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import httpx  # noqa: E402 - sau sys.path

import smoke_term_placeholder as smoke  # noqa: E402 - sau sys.path

from app.adapters.mt.ollama_mt import DEFAULT_BASE_URL  # noqa: E402
from app.adapters.mt.prompts import (EXPERIMENT_PROMPT_STYLE_ENV,  # noqa: E402
                                     PROMPT_STYLES, STYLE_DEFAULT)
from app.domain.mt_qa import echoes_source, is_echo  # noqa: E402
from app.pipeline.translate import EchoProblem, TranslateHandler  # noqa: E402

#: Chữ Hán (CJK Unified + Ext A), cùng khối mà `mt_qa` đếm — dùng để báo cáo con
#: số "chữ Hán còn sót" giống hệt `sweep_mt_batch.py` để hai artifact so được.
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
#: Dòng cổng in ra: `echo_guard:<n>/<m>` — nguồn số của "đoạn dịch lại" ở đây.
_GUARD_LINE = re.compile(r"^echo_guard:(\d+)/(\d+)")


# ---------------------------------------------------------------------------
# Ba cấu hình CÒN LẠI của lượt đo "sưởi" — mỗi cấu hình một tiến trình
# ---------------------------------------------------------------------------

#: Lượt đo đó từng có A–E (xem docstring), nhưng **B và C đã bị xoá** cùng seam
#: sưởi của sản phẩm: seam được ĐO rồi bị TỪ CHỐI (bảng A–E ở docstring và
#: `backend/README.md`), nên một cấu hình "bật sưởi" nay không còn gì để bật —
#: giữ lại là một knob không sinh lời gọi nào, đúng thứ repo này xoá. Số đo của B
#: và C vẫn là bằng chứng, ở artifact `20261019-echo-warmup/`, nhưng chúng KHÔNG
#: tái lập được nữa vì cái seam sinh ra chúng không còn tồn tại.
#:
#: `first_batch_items` = giai đoạn 1 chỉ lộ chừng ấy segment đầu của transcript,
#: rồi giai đoạn 2 đi tiếp bằng chính đường retry của handler.
CONFIGS: dict[str, dict] = {
    "A": {"style": STYLE_DEFAULT, "first_batch_items": None,
          "note": "đối chứng: v0, không sưởi"},
    "D": {"style": STYLE_DEFAULT, "first_batch_items": 4,
          "note": "v0, lô ĐẦU ép còn 4 mục rồi phần còn lại 30 (không sưởi)"},
    # E KHÔNG nằm trong bốn cấu hình của đề bài: nó được thêm sau khi A–D cho thấy
    # hai điều rời nhau — (1) v2 làm MỌI lô trừ lô ĐẦU sạch (7/7 lượt), và (2) lô
    # đầu chép nguồn là chuyện của lô ĐẦU TIÊN ĐỦ 30 MỤC, không phải của "lời gọi
    # đầu" (xem D: lô 4 mục sạch, lô 30 mục ngay sau đó chép 29/30). E ghép đúng
    # hai điều đó: prompt v2 + lô đầu 4 mục.
    "E": {"style": "v2", "first_batch_items": 4,
          "note": "v2 + lô ĐẦU ép còn 4 mục (ghép hai kết quả của A–D)"},
}


class _CallRecorder:
    """Bọc engine THẬT, ghi SỐ MỤC, ID và VỊ TRÍ LOG của từng lời gọi.

    Hình dạng lời gọi là bằng chứng duy nhất cho ba câu hỏi: cổng có gọi lại ĐÚNG
    đoạn bị echo không, mỗi lần gọi lại có đúng MỘT mục không, và lời gọi đó thuộc
    LÔ NÀO. Bọc ở đây chứ không sửa adapter: adapter là code đã ship, phép đo
    không được đổi nó.

    `at` = số dòng log đã in TRƯỚC khi lời gọi này bắt đầu. Đó là thứ duy nhất
    ghép được một dòng `echo_guard:<n>/<m>` với đúng lô đã sinh ra nó mà không
    phải đoán theo thứ tự: cổng in dòng đó SAU khi lời gọi cả lô trả về, và TRƯỚC
    mọi lời gọi dịch lại của chính lô đó, nên "lời gọi cả lô gần nhất trước dòng
    log" là phép ghép đúng tuyệt đối (xem `echo_by_batch`).
    """

    def __init__(self, inner, log: list[str]) -> None:
        self._inner = inner
        self._log = log
        self.calls: list[dict] = []
        #: 1 hoặc 2 — lượt D chạy `translate()` HAI lần (4 mục rồi phần còn lại);
        #: không có nhãn này thì bảng theo lô không phân biệt được "lô nhỏ đầu"
        #: với "một lô 4 mục bình thường".
        self.phase = 1

    @property
    def sizes(self) -> list[int]:
        return [call["size"] for call in self.calls]

    @property
    def ids(self) -> list[list[int]]:
        return [call["ids"] for call in self.calls]

    @property
    def engine_id(self) -> str:
        return self._inner.engine_id

    @property
    def model_ref(self) -> str:
        return self._inner.model_ref

    @property
    def last_stats(self):
        return getattr(self._inner, "last_stats", None)

    def supports_glossary(self) -> bool:
        return self._inner.supports_glossary()

    def translate(self, batch, glossary, opts):
        # Ghi TRƯỚC khi gọi: một lời gọi NÉM vẫn là một lần chạm engine (cùng
        # nguyên tắc với `llm_calls`, spec §4.2), nên nó phải có mặt trong hình
        # dạng lời gọi chứ không được biến mất khỏi phép đếm.
        self.calls.append({"phase": self.phase, "size": len(batch),
                           "ids": [s.i for s in batch], "at": len(self._log),
                           "duration_ms": None, "error": None})
        try:
            out = self._inner.translate(batch, glossary, opts)
        except Exception as exc:
            self.calls[-1]["error"] = type(exc).__name__
            raise
        stats = getattr(self._inner, "last_stats", None)
        self.calls[-1]["duration_ms"] = getattr(stats, "duration_ms", None)
        return out

    def release(self) -> None:
        self._inner.release()


def echo_by_batch(calls: list[dict], log: list[str]) -> list[dict]:
    """Bảng echo THEO TỪNG LÔ, dựng từ hình dạng lời gọi + dòng log của cổng.

    Hàm THUẦN (không engine, không DB, không thời gian), nên nó pin được mà không
    cần model: `tests/test_echo_by_batch.py` đưa vào một chuỗi lời gọi + log giả có
    pattern echo đã biết và đòi đúng con số ở từng lô.

    Hai nguồn, hai câu hỏi khác nhau:

    * **Hình dạng lời gọi** (`calls`) cho biết lô nào có bao nhiêu MỤC và mỗi lô
      tốn bao nhiêu lời gọi DỊCH LẠI. Một lời gọi `size > 1` mở một lô mới; mọi
      lời gọi `size == 1` sau đó (cổng gọi lại, hoặc hạ cấp alignment) thuộc lô
      đó. Lời gọi `size == 1` đứng TRƯỚC lô đầu không thuộc lô nào — seam sưởi
      từng sinh ra đúng một lời gọi như vậy (nay đã bị xoá), và luật ở đây vẫn
      đúng cho nó: một lời gọi thử bị tính vào "dịch lại" của lô 1 sẽ làm con số
      của lượt đo trông xấu hơn sự thật.
    * **Dòng `echo_guard:<n>/<m>`** là con số do CHÍNH cổng in ra: `n` đoạn bị
      chép ở lời gọi cả lô, `m` số mục của lô. Dòng này được ghép với lô có lời
      gọi cả lô GẦN NHẤT TRƯỚC nó (xem `_CallRecorder.at`), không theo thứ tự
      xuất hiện — nhờ vậy một lô KHÔNG echo (không có dòng nào) vẫn giữ đúng
      hàng của nó.

    Lô hỏng alignment xuất hiện thành HAI hàng cùng `ids` (handler gọi lại cả lô
    trước khi hạ cấp): hàng đầu mang `echoed = 0` vì dòng `echo_guard` ghép vào
    hàng sau. Đó là sự thật của lượt chạy, không phải lỗi của phép đếm — và lượt
    đo này không gặp ca đó (xem `batch_calls` trong artifact).
    """
    batches: list[dict] = []
    for call in calls:
        if call["size"] > 1:
            batches.append({
                "batch": len(batches) + 1,
                "phase": call.get("phase", 1),
                "items": call["size"],
                "ids": list(call["ids"]),
                "echoed": 0,
                "singleton_calls": 0,
                "retried_ids": [],
                "guard_items": None,
                "engine_ms": 0,
            })
            row = batches[-1]
        elif not batches:
            continue                      # lượt sưởi, không thuộc lô nào
        else:
            row = batches[-1]
            row["singleton_calls"] += 1
            row["retried_ids"].extend(call["ids"])
        if call.get("duration_ms"):
            row["engine_ms"] += int(call["duration_ms"])

    full_calls = [call for call in calls if call["size"] > 1]
    for position, line in enumerate(log):
        match = _GUARD_LINE.match(line)
        if match is None:
            continue
        owner = None
        for index, call in enumerate(full_calls):
            if call["at"] <= position:
                owner = index
        if owner is None:                 # dòng log không thuộc lô nào: bỏ qua
            continue
        batches[owner]["echoed"] = int(match.group(1))
        batches[owner]["guard_items"] = int(match.group(2))
    return batches


def _echo_ids(source: dict[int, str], accepted) -> tuple[list[int], list[int]]:
    """`(echo theo cổng, echo theo QA)` của đầu ra ĐÃ nhận — hai phép đo, hai câu hỏi.

    `echoes_source` là phép đo của cổng (ngưỡng + luật nguyên văn, có cổng ngôn
    ngữ); `is_echo` là phép đo của QA/dịch lại. Chúng PHẢI cùng nói "0" ở đây, và
    in cả hai ra là cách duy nhất để thấy chúng lệch nhau nếu có.
    """
    guard = [s.i for s in accepted
             if echoes_source(source.get(s.i, ""), s.text, source_lang="zh",
                              target_lang="vi")]
    qa = [s.i for s in accepted if is_echo(source.get(s.i, ""), s.text)]
    return guard, qa


def _loaded_models() -> list[str]:
    """Model đang nằm trong VRAM theo `/api/ps` — trạng thái TRƯỚC một lượt đo.

    Không phải trang trí: `keep_alive` 30 phút giữ model sau khi lượt trước xong,
    nên nếu trường này KHÁC rỗng ở đầu một lượt có sưởi thì "sưởi" trong lượt đó
    không kiểm được gì cả (model đã nóng sẵn). Ghi lại để người đọc artifact thấy
    điều đó đã được kiểm thay vì tin vào lời hứa.
    """
    try:
        data = httpx.get(f"{DEFAULT_BASE_URL}/api/ps", timeout=10).json()
    except Exception as exc:              # noqa: BLE001 - chỉ là số đo phụ
        return [f"(không đọc được /api/ps: {type(exc).__name__})"]
    return [str(item.get("name") or item.get("model"))
            for item in data.get("models") or []]


class _PhaseRepos(smoke._InMemoryRepos):
    """Repo trong bộ nhớ + một công tắc `limit` trên TRANSCRIPT.

    `limit` = chỉ lộ ra chừng ấy segment ĐẦU của transcript. Đó là toàn bộ cơ chế
    của lượt D: giai đoạn 1 (limit 4) làm handler dịch đúng MỘT lô 4 mục rồi
    checkpoint vào CÙNG hàng `translations`; giai đoạn 2 (limit `None`) cho handler
    thấy cả clip, nó đọc `done` từ hàng đó và đi tiếp bằng chính đường retry của
    sản phẩm. Không sửa `batch_segments`, không thêm knob nào vào handler.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.limit: int | None = None

    def get_transcript(self, transcript_id):
        stored = super().get_transcript(transcript_id)
        if self.limit is None:
            return stored
        # Chỉ `segments` được handler đọc từ transcript (`translate`), nên một
        # namespace nhỏ là đủ — dựng `_Stored` thứ hai sẽ là bản sao thứ hai của
        # cùng một hàng.
        return types.SimpleNamespace(segments=stored.segments[:self.limit])


def run_one(transcript: pathlib.Path, glossary: pathlib.Path,
            out_dir: pathlib.Path, batch_items: int,
            style: str = STYLE_DEFAULT, *, config: str | None = None,
            first_batch_items: int | None = None,
            unload: bool = True) -> dict:
    terms = smoke._load_terms(glossary)
    segments = smoke._load_segments(transcript, None)
    spec, engine = smoke._engine_and_capabilities(smoke.ENGINE_ID)
    log: list[str] = []
    recorder = _CallRecorder(engine, log)
    prompt_version = smoke._prompt_version(spec)
    #: Capability nguyên bản của `registry.json`: seam sưởi từng được bật Ở ĐÂY
    #: (không phải trong registry) để đo mà không đổi đường ship; nó đã bị xoá, nên
    #: giờ chỉ còn đúng những gì registry khai.
    capabilities = dict(spec.capabilities)
    repos = _PhaseRepos(segments, terms, engine=spec.id,
                        prompt_version=prompt_version)

    def _handler(items: int) -> TranslateHandler:
        return TranslateHandler(
            repos, {spec.id: recorder},
            engine_capabilities={spec.id: capabilities},
            # Số cụ thể THẮNG `capabilities.max_items_per_call` — đúng đường mà
            # `sweep_mt_batch.py` dùng để quét lô, và không đổi mặc định sản phẩm.
            batch_items=items,
        )

    def _report(_progress: float, line: str) -> None:
        log.append(line)
        print(line, flush=True)

    job = smoke._Job()
    error: dict | None = None
    model_loaded_before = _loaded_models()
    started = time.perf_counter()
    # HATCH: đặt biến môi trường ĐÚNG một lần cho cả lượt (mọi lần dịch lại
    # singleton bên trong `echo_guard` cũng đọc nó), rồi TRẢ LẠI giá trị cũ ở
    # `finally`. Chỉ engine của `smoke.ENGINE_ID` đọc biến này (xem
    # `prompts.experiment_prompt_style`), nên `--styles v3` không đổi prompt của
    # bất kỳ engine nào khác trong cùng tiến trình.
    previous_style = os.environ.get(EXPERIMENT_PROMPT_STYLE_ENV)
    os.environ[EXPERIMENT_PROMPT_STYLE_ENV] = style
    try:
        if first_batch_items:
            # Giai đoạn 1: chỉ 4 segment đầu, nên ĐÚNG MỘT lô 4 mục.
            repos.limit = first_batch_items
            recorder.phase = 1
            _handler(first_batch_items).translate(
                translation_id=1, transcript_id=1, engine_id=spec.id,
                source_lang="zh", target_lang="vi", job=job, report=_report)
            # Giai đoạn 2: cả clip; handler đọc `done` (4 segment đã checkpoint)
            # và chia 111 đoạn còn lại thành 30/30/30/21.
            repos.limit = None
            recorder.phase = 2
            _handler(batch_items).translate(
                translation_id=1, transcript_id=1, engine_id=spec.id,
                source_lang="zh", target_lang="vi", job=job, report=_report)
        else:
            _handler(batch_items).translate(
                translation_id=1, transcript_id=1, engine_id=spec.id,
                source_lang="zh", target_lang="vi", job=job, report=_report)
    except EchoProblem as exc:
        error = {"type": "EchoProblem", "ids": exc.ids, "echoed": exc.echoed,
                 "batch": exc.batch, "message": str(exc)}
    except Exception as exc:      # noqa: BLE001 - smoke phải BÁO, không được chết
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if previous_style is None:
            os.environ.pop(EXPERIMENT_PROMPT_STYLE_ENV, None)
        else:
            os.environ[EXPERIMENT_PROMPT_STYLE_ENV] = previous_style
        # Đo xong thì ĐỔ model khỏi VRAM: lượt SAU phải bắt đầu từ đúng trạng thái
        # mà lượt này bắt đầu, nếu không "sưởi" của lượt sau là vô nghĩa (model
        # đã nóng sẵn vì `keep_alive` 30 phút).
        if unload:
            try:
                recorder.release()
            except Exception as exc:      # noqa: BLE001 - đổ hỏng không làm hỏng số đo
                print(f"(không đổ được model: {type(exc).__name__}: {exc})",
                      flush=True)
    seconds = round(time.perf_counter() - started, 2)

    accepted = repos._translation.segments
    source = {s.i: s.text for s in segments}
    guard_echo, qa_echo = _echo_ids(source, accepted)
    guard_counts = [int(m.group(1)) for line in log
                    if (m := _GUARD_LINE.match(line))]
    batches = echo_by_batch(recorder.calls, log)
    # Chữ Hán theo TỪNG LÔ: cùng phép đếm với cột tổng, nhưng chia theo id của lô
    # — "echo dồn ở lô 1" phải nhìn thấy được ở cả chữ Hán, không chỉ ở số đoạn.
    han_by_id = {s.i: len(HAN.findall(s.text)) for s in accepted}
    for row in batches:
        row["han_chars"] = sum(han_by_id.get(i, 0) for i in row["ids"])
        row["accepted"] = sum(1 for i in row["ids"] if i in han_by_id)
    result = {
        "experiment": "echo-guard-smoke",
        "engine": spec.id,
        "model_ref": spec.model_ref,
        "prompt_version": prompt_version,
        #: Style prompt của lượt này — nhãn DUY NHẤT phân biệt bốn artifact.
        #: `PROMPT_VERSION` cố ý KHÔNG đổi cho biến thể (chưa ship gì), nên thiếu
        #: trường này thì cả bốn tệp cùng ghi `hymt-json-p2` và không ai biết cái
        #: nào là prompt nào.
        "prompt_style": style,
        #: Nhãn cấu hình của lượt đo sưởi (A/D/E — B và C đã bị xoá cùng seam).
        #: `None` = lượt quét lô/style cũ.
        "config": config,
        "first_batch_items": first_batch_items,
        #: Trạng thái VRAM TRƯỚC lượt: phải rỗng ở MỖI lượt có sưởi thì "sưởi" và
        #: "không sưởi" mới là hai điều kiện khác nhau đúng một biến.
        "model_loaded_before": model_loaded_before,
        "capabilities": dict(capabilities),
        "transcript": str(transcript),
        "glossary": [[t.term, t.translation] for t in terms],
        "segments": len(segments),
        #: Trần số mục của MỘT lời gọi engine (tham số `batch_items`), chép vào
        #: artifact để lần chạy sau không phải suy từ code lúc đó.
        "batch_items": batch_items,
        "seconds": seconds,
        "batch_calls": sum(1 for size in recorder.sizes if size > 1),
        "singleton_calls": sum(1 for size in recorder.sizes if size == 1),
        "llm_calls": len(repos.llm_calls),
        #: Số đoạn mà CỔNG đã gọi lại, đọc từ chính dòng log của cổng — không phải
        #: một bộ đếm thứ hai trong kịch bản.
        "guard_retried": sum(guard_counts),
        "guard_lines": [line for line in log if line.startswith("echo_guard:")],
        #: BẢNG theo lô — thứ lượt trước thiếu (xem docstring `echo_by_batch`).
        "echo_by_batch": batches,
        "echo_problem_batches": 1 if (error or {}).get("type") == "EchoProblem" else 0,
        "accepted_segments": len(accepted),
        "translation_status": repos.status,
        "qa_issues": repos.qa_issues,
        #: Số cờ QA `lang:` — mức "dòng vẫn là chữ nguồn" mà QA tự báo, độc lập
        #: với cổng. Đếm trên issue CẤP LƯỢT (`qa_translation` ghi ở đó), không
        #: trên `Segment.qa`.
        "qa_lang": sum(1 for issue in repos.qa_issues
                       if str(issue).startswith("lang:")),
        "han_chars": sum(len(HAN.findall(s.text)) for s in accepted),
        "echo_segments_guard": len(guard_echo),
        "echo_segments_qa": len(qa_echo),
        "echo_ids_guard": guard_echo,
        "error": error,
        "sentences": [{"i": s.i, "zh": source.get(s.i, ""), "vi": s.text,
                       "qa": list(s.qa)} for s in accepted],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / _artifact_name(config, style, batch_items)).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _artifact_name(config: str | None, style: str, batch_items: int) -> str:
    """Tên tệp artifact: cấu hình THẮNG mọi nhãn khác khi có.

    Lượt đo sưởi có năm cấu hình A–E trên cùng một lô 30, nên tên theo lô
    (`batch-30.json`) là năm lượt ghi vào MỘT tệp. Và lượt mặc định của các lượt
    CŨ vẫn phải giữ nguyên `batch-30.json` để lần chạy lại không đổi tên artifact
    của lượt trước.
    """
    if config is not None:
        return f"config-{config}.json"
    return (f"batch-{batch_items}.json" if style == STYLE_DEFAULT
            else f"{style}-batch-{batch_items}.json")


def _row(result: dict) -> dict:
    """Một hàng của bảng tổng kết — đúng những cột được hỏi trong đề bài."""
    return {
        "config": result["config"],
        "prompt_style": result["prompt_style"],
        "batch_items": result["batch_items"],
        "first_batch_items": result["first_batch_items"],
        "echo_problem_batches": result["echo_problem_batches"],
        "guard_retried": result["guard_retried"],
        "batch_calls": result["batch_calls"],
        "singleton_calls": result["singleton_calls"],
        "llm_calls": result["llm_calls"],
        "accepted_segments": result["accepted_segments"],
        "echo_segments_guard": result["echo_segments_guard"],
        "echo_segments_qa": result["echo_segments_qa"],
        "han_chars": result["han_chars"],
        "qa_lang": result["qa_lang"],
        "seconds": result["seconds"],
        "translation_status": result["translation_status"],
        "error_type": (result["error"] or {}).get("type"),
    }


def _print_batches(config: str | None, batches: list[dict]) -> None:
    """Bảng theo lô của MỘT lượt — in ngay để đọc được khi lượt còn đang chạy.

    Hai cột phải đứng CẠNH nhau: `echo` là số đoạn bị chép (đọc từ dòng
    `echo_guard:<n>/<m>` của cổng) còn `gọi 1 mục` là số lời gọi MỘT mục của cả lô
    (cổng + hạ cấp alignment). Chúng bằng nhau ở lô bị echo; lô nào có `echo = 0`
    mà `gọi 1 mục > 0` là lô hỏng ALIGNMENT (xem D: hai lô 30 mục trả thiếu mục,
    30 lời gọi hạ cấp mỗi lô) — gộp hai cột làm một là nói dối về nguồn của 60 lời
    gọi đó.
    """
    label = config or "-"
    print(f"\n  echo theo lô (cấu hình {label}):")
    print("  lô | pha | mục | echo | gọi 1 mục | nhận | chữ Hán | ms engine")
    print("  ---|---|---|---|---|---|---|---")
    for row in batches:
        print(f"  {row['batch']} | {row['phase']} | {row['items']} | "
              f"{row['echoed']} | {row['singleton_calls']} | {row['accepted']} | "
              f"{row['han_chars']} | {row['engine_ms']}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="smoke_echo_guard.py")
    parser.add_argument("--transcript", type=pathlib.Path, required=True)
    parser.add_argument("--glossary", type=pathlib.Path, required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    parser.add_argument("--batches", type=int, nargs="+", default=[30],
                        help="các trần số mục cần đo (mặc định 30 = mặc định cũ)")
    parser.add_argument("--styles", nargs="+", default=[STYLE_DEFAULT],
                        choices=list(PROMPT_STYLES),
                        help="các biến thể prompt cần đo (mặc định v0 = prompt "
                             "đang ship)")
    parser.add_argument("--configs", nargs="+", choices=list(CONFIGS),
                        help="các cấu hình của lượt đo SƯỞI còn tái lập được "
                             "(A/D, và E thêm sau; B/C đã bị xoá cùng seam sưởi); "
                             "có mặt thì THẮNG --styles/--batches. Mỗi cấu hình "
                             "nên là một lần gọi tiến trình riêng (xem docstring)")
    parser.add_argument("--no-unload", action="store_true",
                        help="KHÔNG đổ model sau mỗi lượt (mặc định là đổ, để lượt "
                             "sau bắt đầu từ cùng trạng thái VRAM)")
    args = parser.parse_args(argv)

    rows: list[dict] = []
    #: Bảng theo lô của TỪNG lượt, đánh khoá theo nhãn cấu hình (hoặc
    #: `style-lô`) — chép vào `summary.json` để không phải mở bốn tệp mới thấy
    #: được câu trả lời "echo nằm ở lô NÀO".
    tables: dict[str, list[dict]] = {}
    plans: list[dict] = []
    if args.configs:
        for config in args.configs:
            plan = dict(CONFIGS[config])
            plan.update({"config": config, "batch_items": 30})
            plans.append(plan)
    else:
        for style in args.styles:
            for batch_items in args.batches:
                plans.append({"config": None, "style": style,
                              "batch_items": batch_items,
                              "first_batch_items": None, "note": ""})

    for plan in plans:
        label = plan["config"] or f"{plan['style']}·lô {plan['batch_items']}"
        print(f"\n=== {label} · {plan['style']} · lô {plan['batch_items']} "
              f"· lô đầu={plan['first_batch_items']} ===", flush=True)
        if plan["note"]:
            print(f"    ({plan['note']})", flush=True)
        result = run_one(args.transcript, args.glossary, args.out_dir,
                         plan["batch_items"], plan["style"],
                         config=plan["config"],
                         first_batch_items=plan["first_batch_items"],
                         unload=not args.no_unload)
        rows.append(_row(result))
        tables[plan["config"] or f"{plan['style']}-{plan['batch_items']}"] = (
            result["echo_by_batch"])
        _print_batches(plan["config"], result["echo_by_batch"])

    summary = {"experiment": "echo-guard-smoke", "rows": rows,
               "echo_by_batch": tables}
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n| cấu hình | style | lô | lô hỏng | đoạn dịch lại | "
          "lời gọi cả lô | lời gọi 1 mục | echo còn lại | chữ Hán | QA lang | giây |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        print(f"| {row['config'] or '-'} | {row['prompt_style']} | "
              f"{row['batch_items']} | "
              f"{row['echo_problem_batches']} | {row['guard_retried']} | "
              f"{row['batch_calls']} | {row['singleton_calls']} | "
              f"{row['echo_segments_guard']} | {row['han_chars']} | "
              f"{row['qa_lang']} | {row['seconds']} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
