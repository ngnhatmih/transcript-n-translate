"""Handler dịch: một job cho MỘT bản dịch, batch hoá bên trong, checkpoint mỗi lô.

Vì sao một job chứ không nhiều job nhỏ: `translations` là một hàng, một version;
`Job.progress` biểu diễn được % của cả bản dịch; và API không bị rò chi tiết cài
đặt (spec §3).

Bất biến: `translations.segments` chỉ chứa bản dịch khớp ĐÚNG id đầu vào, theo
đúng thứ tự. Phần chưa dịch là THIẾU DÒNG, không bao giờ là dòng rỗng.

Bốn quyết định đã chốt bằng review trong phase này, và lý do chúng không hiển
nhiên:

* **Ai cộng dồn danh sách.** `update_translation_segments` GHI ĐÈ bằng đúng danh
  sách được đưa — adapter không tự nối. Handler giữ `done` trong bộ nhớ, cộng dồn
  rồi truyền CẢ danh sách, nên `len(done)` chính là tiến độ (spec §3). Truyền mỗi
  lô vừa xong thì checkpoint sau xoá checkpoint trước và tiến độ biến mất trong im
  lặng; đó là lý do `test_checkpoint_replaces_with_a_shorter_list` tồn tại.
* **Hạ cấp chỉ ghi khi THÀNH CÔNG.** Phần hạ cấp đã dịch được KHÔNG được trả về
  khi còn segment hỏng: trả về một danh sách thiếu dòng ở giữa sẽ khiến lần retry
  sau coi id đó là "đã xong" và bỏ qua vĩnh viễn. Hỏng thì `done` không đổi, và
  `segments` giữ đúng những lô đã checkpoint nguyên vẹn.
* **`engine_id` tra theo khoá registry.** `self._engines` được Task 12 dựng theo
  `spec.id` của registry, KHÔNG theo `engine.engine_id`; hai giá trị này khác nhau
  với HY-MT (`hy-mt1.5-7b-q4_K_M` vs `hy-mt-1.5-7b`), nên tra theo thuộc tính của
  engine sẽ `KeyError` trên chính engine vừa nhận. `KeyError` phải nổ TRƯỚC khi
  ghi bất cứ thứ gì.
* **`report` nhận HAI tham số** (`worker.py:24`:
  `run(self, job, report: Callable[[float, str], None])`). Gọi một tham số là
  `TypeError` ngay dòng log đầu, và vì nó nằm trong `try` của `_run_one`, job chỉ
  lặng lẽ thành `failed`.
* **Cờ huỷ đọc LẠI TỪ REPO mỗi lô.** `job.cancel_requested` là ẢNH CHỤP worker
  đọc trước khi handler chạy, còn yêu cầu huỷ thật chỉ ghi DB; tin ảnh chụp thì
  chức năng huỷ không bao giờ chạy trong đường nối dây thật, mà test chỉ lật
  thuộc tính của một job giả vẫn xanh (F1 của review Task 11).
* **Lỗi không lường trước phải để lại `failed`.** Cả vòng lặp được bọc; nếu chỉ
  nhánh alignment ghi `failed` thì một `RuntimeError` trần (Ollama sập, OOM) để
  hàng dịch treo ở `queued` trong khi job đã `FAILED`. `LookupError` đi thẳng ra:
  hàng biến mất thì không có gì để đánh dấu (F2 của review Task 11).
* **MỌI lời gọi engine đều được ĐẾM, và số của cả bản dịch là TỔNG.** Spec §4.2
  đòi mỗi bước ghi được vào `llm_calls`; trước bản này `add_llm_call` không có
  người gọi nào trong `app/`. `_translate_batch` ghi MỘT hàng cho MỖI lần chạm
  engine — cả lần retry hỏng, cả từng segment ở bước hạ cấp — nên bản dịch 3 lô
  có 3 hàng trở lên. `tokens_in`/`tokens_out`/`duration_ms` của hàng `translations`
  là TỔNG của chính các hàng đó, không phải `engine.last_stats`: adapter GHI ĐÈ
  `last_stats` mỗi lần gọi (`ollama_mt.py`), nên đọc nó sau vòng lặp chỉ còn số
  của lô CUỐI và một bản dịch 3 lô báo thiếu 2/3 chi phí. Tổng suy từ `llm_calls`
  nên hai mặt của cùng một bản dịch không thể lệch nhau, và một lần chạy lại
  (retry từ segment còn thiếu) cộng dồn trên các hàng đã ghi của CHÍNH job đó.
  `_Totals` dùng `None` (không phải `0`) khi chưa có hàng nào: "chưa gọi engine
  lần nào" khác "gọi rồi mà engine không báo token" — OPUS-MT chạy trong tiến
  trình và không có token count.
* **Echo là lỗi IM LẶNG, nên nó phải được DỊCH LẠI chứ không chỉ bị gắn cờ.**
  Đo trên clip 115 đoạn (`20261019-term-placeholder-clip`): ở lô 30 mặc định,
  `hy-mt-1.5-7b` trả về nguyên chữ Trung cho **59–89/115 đoạn** — số mục vẫn
  khớp nên `check_alignment` cho qua, `qa_issues` chỉ thêm cờ `lang:<i>` theo
  từng dòng, và hàng `translations` vẫn `done`. Cùng lô đó, một lượt "chỉ có 4
  lời gọi / 32,8 s" chính là lượt KHÔNG dịch — nên mọi số đo tốc độ cũ của engine
  này trước bản này đều là số của một lượt chưa làm việc. Vì vậy mỗi đoạn bị echo
  được gọi lại MỘT MÌNH (`_retry_echoed`, lô 1, ngữ cảnh ngắn), vẫn qua đúng
  chính sách alignment; đoạn vẫn echo sau lần đó giữ chữ của model, mang cờ
  `echo` trên `Segment.qa`, và cả lượt thêm issue `echo:<n>/<tổng>` khi vượt 5%
  (`mt_qa.echo_run_issue`). Cơ chế bật bằng DỮ LIỆU
  (`capabilities.echo_retry`) nên engine chưa đo — `opus-mt`, đo được 0 echo
  trên cùng clip — đi đúng đường cũ từng byte.
* **Với engine khai `echo_guard`, echo là lỗi CHẶN LÔ, không phải một cái cờ.**
  Số đo (cùng clip 115 đoạn, cùng prompt, `hy-mt-1.5-7b`): lô 8 -> 0–8/115 đoạn
  echo, 0–54 chữ Hán; lô 15 -> 29/115, 181 chữ Hán; lô 30 -> **59–89/115**,
  389–629 chữ Hán. `opus-mt` cùng clip: 0/115, 0 chữ Hán. Vì thế lỗi này KHÔNG
  được "sửa" bằng cách hạ kích thước lô (nó có mặt ở cả ba lô) và cũng không được
  "sửa" bằng một cờ QA: số mục vẫn khớp nên `check_alignment` cho qua, và một
  hàng `translations` `done` chứa nguyên chữ Trung là lỗi ÂM THẦM đúng nghĩa
  đen. Nên đoạn bị chép được dịch lại MỘT MÌNH (`_guard_echoes`, lô 1), và nếu
  vẫn chép thì cả lô `raise EchoProblem` kèm id + số đoạn: hàng dịch thành
  `failed`, không có `done` nào được ghi. Cũng là DỮ LIỆU của registry
  (`capabilities.echo_guard`), nên `opus-mt` — không khai — đi đúng đường cũ từng
  byte và không tốn một phép kiểm nào (`mt_qa.echoes_source`).
* **Bảo vệ thuật ngữ bằng token nằm TRONG `_translate_batch`, không ở vòng lặp
  lô.** Vòng lặp chỉ thấy MỘT lời gọi engine, còn `_translate_batch` là nơi duy
  nhất đi qua cả ba đường chạm engine: lần thử cả lô, lần retry, và bước hạ cấp
  từng segment. Che thuật ngữ ở vòng lặp thì bước hạ cấp — đúng bước chạy khi
  model hỏng alignment — nhận chữ CHƯA token hoá và trả về bản dịch không có
  bảo vệ nào; và đường Chimera (`_run_engine_batch`) cũng đi qua đây nên nó được
  che luôn mà không phải sửa `pipeline/chimera.py`. Bảo vệ là DỮ LIỆU của
  registry: chỉ engine khai `capabilities.term_placeholder` mới bật, nên mọi
  engine khác đi đúng đường cũ từng byte (xem `_placeholder_terms`).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from app.domain.alignment import AlignmentProblem, check_alignment
from app.domain.glossary_match import approved
from app.domain.models import Segment, Term
from app.domain.mt import (DEFAULT_MAX_CHARS, DEFAULT_MAX_ITEMS, MtOpts,
                           batch_segments)
from app.domain.mt_qa import (ECHO_FLAG, QaLimits, echo_run_issue, echoes_source,
                              is_echo, qa_translation)
from app.domain.term_placeholder import (TOKEN_COLLISION, count_tokens,
                                         has_token_like, plan_terms, protect,
                                         restore)
from app.pipeline.chimera import ChimeraRunner


@dataclass(frozen=True)
class _Totals:
    """Tổng token/thời gian của MỌI lời gọi engine đã ghi cho một job dịch.

    `None` khi chưa có hàng `llm_calls` nào, hoặc khi mọi hàng đều để trống
    trường đó (OPUS-MT không trả token). Không bao giờ là `0`: một con số 0 nói
    "đã đo được và bằng không", còn sự thật là "chưa đo được".
    """

    tokens_in: int | None
    tokens_out: int | None
    duration_ms: int | None


def _sum_rows(rows: list[dict], column: str) -> int | None:
    values = [r[column] for r in rows if r.get(column) is not None]
    return sum(values) if values else None


def _totals_of(rows: list[dict]) -> dict:
    """Số đo của MỘT NHÓM hàng `llm_calls` (thường là các hàng của đúng một lời gọi).

    Chế độ Chimera cần tách số đo theo TỪNG ứng viên, mà `llm_calls` là một dãy
    phẳng theo job. Cách tách ở đây là ĐẾM SỐ HÀNG trước và sau một lời gọi rồi
    cắt — không thêm cột, không thêm bảng, và không suy đoán: một lời gọi ghi ít
    nhất một hàng (kể cả hàng hỏng), nên phép cắt luôn cắt đúng chỗ.
    """
    return {
        "calls": len(rows),
        "tokens_in": _sum_rows(rows, "tokens_in"),
        "tokens_out": _sum_rows(rows, "tokens_out"),
        "duration_ms": _sum_rows(rows, "duration_ms"),
    }


class EchoProblem(Exception):
    """Một lô mà sau khi dịch lại riêng vẫn còn đoạn CHÉP NGUYÊN chữ nguồn.

    Đây là lỗi của LÔ, cùng họ với `AlignmentProblem`: bên gọi không được ghi gì
    từ lô này. Khác `AlignmentProblem` ở chỗ nó không phải lỗi CẤU TRÚC (số mục
    vẫn khớp, id vẫn đúng) mà là lỗi NỘI DUNG — đúng kiểu hỏng mà `check_alignment`
    không nhìn thấy, nên trước bản này nó đi thẳng vào một hàng `done`.

    `ids` là các segment vẫn là bản chép SAU lần dịch lại (đã sắp xếp), `echoed` là
    số của chính danh sách đó, `batch` là số mục của lô. Ba trường rời nhau chứ
    không chỉ một chuỗi: `jobs.error` ghi `EchoProblem: <str>`, còn người đọc
    `llm_calls`/log cần con số và id để biết phải xem đoạn nào.

    Nơi khai: `pipeline/translate.py` chứ không phải `domain/mt_qa.py` — `mt_qa`
    là logic THUẦN (chỉ ĐO), còn "một lô có bị từ chối hay không" là chính sách
    của đường dịch, cùng tầng với `AlignmentProblem` của `domain/alignment.py`
    nhưng do handler quyết định.
    """

    def __init__(self, ids: list[int], *, echoed: int, batch: int,
                 reason: str) -> None:
        super().__init__(reason)
        self.ids = list(ids)
        self.echoed = int(echoed)
        self.batch = int(batch)
        self.reason = reason


class TranslateHandler:
    def __init__(self, repos, engines: dict[str, object], *,
                 batch_chars: int = DEFAULT_MAX_CHARS,
                 batch_items: int | None = None,
                 limits: QaLimits = QaLimits(),
                 chimera=None, chimera_merge=None,
                 engine_capabilities: dict[str, dict] | None = None) -> None:
        self._repos = repos
        self._engines = engines
        self._batch_chars = batch_chars
        #: `capabilities` của từng `EngineSpec` DỊCH, do composition root chép từ
        #: registry và trao vào (`{spec.id: spec.capabilities}`). Handler KHÔNG
        #: được import `app.adapters` (có test canh tầng API) và cũng không tự đọc
        #: `registry.json`: registry là DỮ LIỆU do composition root nạp một lần,
        #: đúng khuôn với `prompt_version`/`chimera_prompt_version` mà `main.py`
        #: cũng đặt vào chính dict đó. Thiếu tham số này thì MỌI engine đi đường
        #: cũ — không có nhánh chết nào được bật bằng cách thiếu cấu hình.
        self._capabilities = dict(engine_capabilities or {})
        #: Trần SỐ MỤC của một lời gọi engine (ngân sách thứ hai, xem
        #: `mt.DEFAULT_MAX_ITEMS` cho số đo và lý do). Nó là chính sách của HANDLER
        #: chứ không phải của `batch_segments`: hàm đó vẫn là một hàm thuần chỉ biết
        #: hai con số, còn "một lời gọi engine chịu được bao nhiêu mục" là chuyện
        #: của đường dịch.
        #:
        #: `None` = "theo TỪNG ENGINE": engine khai `capabilities.max_items_per_call`
        #: thì dùng số đó, còn lại dùng `mt.DEFAULT_MAX_ITEMS`. Vì sao cần: đo trên
        #: clip 115 đoạn, CÙNG prompt, `hy-mt-1.5-7b` echo 90/115 đoạn khi lô 30 và
        #: **0/115 khi lô 1** (55,3 s, 116 lời gọi) — với engine đó, "một lời gọi
        #: chịu được bao nhiêu mục" không phải 30 mà là 1, và đó là dữ liệu của
        #: engine chứ không phải chính sách chung. Truyền một số cụ thể (test, phép
        #: đo) vẫn THẮNG capability, để còn đo được các lô khác.
        self._batch_items = batch_items
        self._limits = limits
        #: Kế hoạch Chimera (§8.7.5). `None` = registry không khai báo chế độ này,
        #: và khi đó MỌI hàng `translations` đi đường cũ — không có nhánh chết nào
        #: được kích hoạt bằng cách thiếu cấu hình.
        self._chimera = chimera
        #: Adapter của LƯỢT PHA (`adapters/mt/chimera_merge.OllamaMergeEngine`).
        #: `None` = lượt pha không chạy được, và runner LÙI VỀ MỎ NEO kèm lý do.
        self._chimera_merge = chimera_merge

    def handles(self) -> str:
        return "translate"

    def run(self, job, report: Callable[[float, str], None]) -> None:
        # `getattr` chứ không `job.payload`: payload vắng là lỗi CỦA JOB, và nó
        # phải ra `KeyError` (khoá nào thiếu thì Python tự nói) chứ không phải
        # `AttributeError` trần — worker bắt mọi `Exception` nên cả hai đều thành
        # job `failed`, nhưng thông báo phải chỉ đúng thứ đang thiếu (Task 12 ghim
        # đúng chữ ký này ở `test_mt_wiring`).
        p = getattr(job, "payload", None) or {}
        self.translate(
            translation_id=int(p["translation_id"]),
            transcript_id=int(p["transcript_id"]),
            engine_id=str(p["engine_id"]),
            source_lang=str(p.get("source_lang") or "zh"),
            target_lang=str(p.get("target_lang") or "vi"),
            job=job,
            report=report,
        )

    def translate(self, *, translation_id: int, transcript_id: int, engine_id: str,
                  source_lang: str, target_lang: str, job,
                  report: Callable[[float, str], None]) -> None:
        # Id engine sai hỏng TRƯỚC khi đọc/ghi gì: hàng dịch phải còn nguyên
        # `queued` để lần retry sau không thấy một bản dịch nửa vời. Đây cũng là
        # lý do `running` được ghi SAU dòng này, không phải trước.
        engine = self._engines[engine_id]
        # Đọc MỘT lần, dùng cho cả `done` lẫn các trường dấu vết của `llm_calls`
        # (`engine`/`prompt_version`): chúng là dữ liệu ĐÃ GHI LÚC TẠO (route lấy
        # từ `spec.capabilities` của registry), không phải thứ suy lại từ engine.
        stored = self._repos.get_translation(translation_id)
        # Chế độ Chimera là DỮ LIỆU ĐÃ GHI trên hàng (`POST /api/translations` ghi
        # nó lúc tạo, kèm ƯỚC LƯỢNG CHI PHÍ đã hiện cho người dùng). Đọc từ hàng
        # chứ không từ `job.payload`: payload là ảnh chụp lúc xếp hàng, còn hàng là
        # thứ API trả cho giao diện — hai nguồn cho cùng một câu trả lời là hai
        # câu trả lời có thể lệch.
        cfg = getattr(stored, "chimera", None) or {}
        runner = None
        if cfg.get("enabled") and self._chimera is not None:
            runner = ChimeraRunner(self._chimera, merge_engine=self._chimera_merge,
                                   limits=self._limits, created=cfg)
        # `running` (spec §6): thiếu nó thì hàng dịch nằm nguyên ở `queued` suốt
        # thời gian chạy, và `GET /api/translations` (Task 13) không phân biệt
        # được "vừa xếp, chưa ai chạm" với "đang chạy" — trong khi vocabulary đã
        # khai `running` từ Task 1.
        self._repos.set_translation_status(translation_id, "running")
        opts = MtOpts(source_lang=source_lang, target_lang=target_lang)
        glossary = approved(self._repos.list_terms(lang=source_lang))
        # Version ĐỌC NGAY ĐÂY, cùng chỗ dựng `glossary`: đây là glossary THẬT SỰ
        # đi vào prompt (spec §8.1 — `translations.glossary_version` là dấu vết
        # duy nhất cho biết bản dịch dùng glossary nào). KHÔNG đọc từ
        # `job.payload`: payload là ảnh chụp lúc enqueue, nên một lần sửa glossary
        # khác xen vào trước khi job chạy sẽ khiến dấu vết ghi version CŨ — đúng
        # loại dối mà Task 18 tồn tại để dẹp (F1 của review Task 14).
        glossary_version = self._repos.glossary_version()

        source = self._repos.get_transcript(transcript_id).segments
        done = self._ordered_prefix(source, stored.segments)
        done_ids = {s.i for s in done}
        total = len(source)

        report(0.0, f"dịch {len(done)}/{total} segment đã có (engine {engine_id})")

        # Thuật ngữ được ÉP bằng token cho engine này — tính MỘT lần cho cả bản
        # dịch, vì hai chỗ dùng cùng một câu trả lời: vòng lặp (đưa vào
        # `_translate_batch`) và QA cuối (`glossary_enforced`). Tính lại mỗi lô là
        # hai nguồn cho cùng một câu hỏi.
        placeholder_terms = self._placeholder_terms(engine_id, glossary, source_lang)
        # Dịch lại các đoạn bị chép nguyên chữ nguồn — cũng là DỮ LIỆU của
        # registry, cùng khuôn với `_placeholder_terms` ở trên và cùng lý do: chỉ
        # engine ĐÃ ĐO là cần cơ chế này mới bật (`hy-mt-1.5-7b`: 59–89/115 đoạn
        # echo ở lô 30; `opus-mt`: 0 đoạn trên cùng clip).
        echo_retry = self._echo_retry(engine_id)
        # Cổng CHẶN echo cho engine khai `capabilities.echo_guard` — hẹp hơn
        # `echo_retry` ở trên và ĐÈ nó: `echo_retry` dịch lại rồi vẫn nhận bản chép
        # (chỉ gắn cờ), còn cổng này từ chối cả lô (xem `_guard_echoes`). Hai cờ
        # cùng có trên `hy-mt-1.5-7b`, và cổng thắng vì đó là thứ đang được sửa —
        # một hàng `done` chứa nguyên chữ Trung là chính lỗi mà cổng tồn tại để
        # không xảy ra nữa.
        echo_guard = self._echo_guard(engine_id)
        # Trần số mục cho RIÊNG engine này: `capabilities.max_items_per_call` nếu
        # registry khai (xem `_batch_items_for`), ngược lại mặc định của handler.
        batch_items = self._batch_items_for(engine_id)

        # Retry bắt đầu từ segment ĐẦU TIÊN chưa có bản dịch, không dịch lại từ
        # đầu: `done` đọc từ hàng đã ghi ở lần chạy trước (spec §3, "Retry").
        remaining = [s for s in source if s.i not in done_ids]
        # Bọc CẢ vòng lặp: mọi lỗi không lường trước (engine sập, OOM, mạng) phải
        # để hàng dịch ở `failed` TRƯỚC khi nổi lên. Chỉ nhánh alignment ghi
        # `failed` là chưa đủ: một `RuntimeError` trần để hàng treo ở `queued`
        # trong khi job đã `FAILED`, và API/UI hiện một bản dịch "đang chờ" không
        # bao giờ chạy. `LookupError` (`NotFound` kế thừa nó) là ngoại lệ: hàng đã
        # biến mất thì không có gì để đánh dấu, và lần ghi thêm sẽ ném `NotFound`
        # thứ hai che mất lỗi gốc.
        try:
            # Sưởi (gọi thử MỘT lần trước lô đầu) TỪNG có ở đây và ĐÃ BỊ XOÁ cùng
            # cờ capability mà `registry.json` chưa từng khai — một đường không
            # cấu hình nào vào được là cùng một lỗi với một khai báo không ai đọc.
            # Nó đã được ĐO và bị từ chối, không phải bị bỏ quên: bảng A–E và ba
            # giả thuyết bị bác nằm trong `backend/README.md` (mục echo), artifact
            # `data/experiments/accuracy-pipelines/20261019-echo-warmup/`. Tóm tắt:
            # sưởi KHÔNG sửa được v0 (0/2 lượt), lô đầu nhỏ không thay được sưởi,
            # và dời chỉ dẫn xuống cuối prompt đổi 0/89 lần dịch lại. Đừng dựng
            # lại nếu chưa có số mới.
            for batch in batch_segments(remaining, max_chars=self._batch_chars,
                                        max_items=batch_items):
                # Hủy chỉ được kiểm GIỮA các lô: kill giữa lô để lại DB nửa vời và
                # model không được giải phóng (worker.checkpoint).
                if self._cancel_requested(job):
                    self._repos.set_translation_status(translation_id, "cancelled")
                    job.progress = len(done) / total if total else 1.0
                    report(job.progress, f"đã huỷ: giữ {len(done)}/{total} segment")
                    return

                if runner is None:
                    translated, missing = self._translate_batch(
                        engine, batch, glossary, opts, report, job.progress,
                        facts=(stored.engine, stored.prompt_version), job=job,
                        placeholder_terms=placeholder_terms, echo_retry=echo_retry,
                        echo_guard=echo_guard)
                else:
                    kq = runner.run_batch(
                        run=self._run_engine_batch, engines=self._engines,
                        batch=batch, glossary=glossary, opts=opts, job=job,
                        report=report, progress=job.progress)
                    translated, missing = kq.segments, kq.missing
                    # Ghi NGAY sau mỗi lô. Một lượt Chimera dài gấp `N+1` lần lượt
                    # thường, nên "chỉ ghi khi cả bản dịch xong" là mất trắng số đo
                    # của cả lượt chạy khi lô cuối hỏng — mà số đo đó chính là thứ
                    # §4.5 tồn tại để phơi ra.
                    self._repos.set_translation_chimera(translation_id, runner.session())
                if translated is None:
                    # Giữ nguyên phần đã dịch (không xoá công đã làm) và nói rõ id nào
                    # chưa có bản dịch — đây là thông báo hành động được của bước (c).
                    self._repos.set_translation_status(translation_id, "failed")
                    raise RuntimeError(
                        f"dịch thất bại: segment {missing} chưa có bản dịch "
                        f"(đã giữ {len(done)}/{total} segment đã dịch xong)")

                # Checkpoint: ghi CẢ danh sách đã cộng dồn, nên `len(done)` là tiến độ.
                done.extend(translated)
                self._repos.update_translation_segments(translation_id, done)
                job.progress = len(done) / total if total else 1.0
                report(job.progress, f"đã dịch {len(done)}/{total}")
        except LookupError:
            raise
        except Exception:
            self._repos.set_translation_status(translation_id, "failed")
            raise

        # Chuẩn hoá thứ tự trước khi chốt `done`: một hàng CŨ đã ghi lệch thứ tự
        # (hoặc bị chèn giữa) sẽ khiến `done` mang thứ tự của hàng cũ chứ không
        # phải của nguồn, mà lần ghi này là lần ghi CUỐI CÙNG của bản dịch. `done`
        # theo thứ tự nguồn cũng là thứ `qa_translation` giả định (nó ghép `out`
        # theo id, nhưng người đọc log/DB phải thấy cùng một thứ tự với phụ đề).
        done = self._ordered_prefix(source, done)
        self._repos.update_translation_segments(translation_id, done)

        if runner is not None:
            # Bản ghi CUỐI: cùng `runner` nên nó chỉ hơn bản ghi giữa đường ở chỗ
            # đã có đủ mọi lô. Không dựng lại từ DB — dựng lại là nguồn thứ hai.
            self._repos.set_translation_chimera(translation_id, runner.session())

        issues = qa_translation(source, done, glossary=glossary,
                                supports_glossary=engine.supports_glossary(),
                                limits=self._limits,
                                target_lang=target_lang,
                                # Thuật ngữ đã được ÉP bằng token thì
                                # `engine_no_glossary` là thông tin sai: engine
                                # không nhận glossary qua prompt, nhưng rendering
                                # vẫn được bảo đảm bằng khôi phục hậu xử lý.
                                glossary_enforced=bool(placeholder_terms))
        # Issue CẤP LƯỢT cho echo, sau `qa_translation` và KHÔNG nằm trong nó:
        # hàm đó cũng là nguồn số của chế độ Chimera (`candidate_metrics`), nơi
        # `echo` đã là một mét riêng — thêm ở đó là đếm hai lần cùng một hiện
        # tượng. Một dòng `echo:89/115` là thứ tự nói ra tỉ lệ, thay vì bắt người
        # đọc ĐẾM 89 cờ `lang:` rải rác.
        run_echo = echo_run_issue(source, done)
        if run_echo is not None:
            issues.append(run_echo)
            report(1.0, f"cảnh báo: {run_echo} đoạn vẫn là bản chép nguồn")
        # TỔNG của mọi lời gọi engine đã ghi cho job này, không phải
        # `engine.last_stats` (chỉ còn số của lô cuối — xem docstring đầu tệp).
        totals = self._totals_for(getattr(job, "id", None))
        self._repos.set_translation_status(
            translation_id, "done", qa_issues=issues,
            tokens_in=totals.tokens_in,
            tokens_out=totals.tokens_out,
            duration_ms=totals.duration_ms,
            glossary_version=glossary_version,
        )
        # §8.6 `draft -> reviewed -> translated`: `approve` ghi `reviewed` (Task 15,
        # vì `translated` ngay lúc duyệt một transcript CHƯA có bản dịch nào là sai
        # ngay khi ghi), nên giá trị cuối chuỗi phải do chỗ DUY NHẤT biết chắc bản
        # dịch đã xong sinh ra — đây là chỗ đó. Chỉ nằm trên đường thành công: cả
        # nhánh `failed` lẫn nhánh `cancelled` ở trên đều KHÔNG đi qua đây, vì một
        # transcript `translated` với bản dịch hỏng cũng là một lời nói dối.
        self._repos.set_transcript_status(transcript_id, "translated")
        job.progress = 1.0
        report(1.0, f"xong: {len(done)} segment, {len(issues)} issue QA")

    def _run_engine_batch(self, engine, batch, glossary, opts, facts, job,
                          report, progress) -> tuple[list[Segment] | None,
                                                     list[int], dict]:
        """MỘT lời gọi engine qua chính sách alignment, kèm SỐ ĐO CỦA RIÊNG NÓ.

        Đây là chỗ chế độ Chimera lấy được "ứng viên này tốn bao nhiêu token": số
        đo được cắt từ `llm_calls` theo mốc đếm trước/sau, nên nó đến từ CÙNG nguồn
        với tổng của cả bản dịch (`_totals_for`) và hai con số không thể lệch nhau.
        """
        job_id = getattr(job, "id", None)
        before = len(self._repos.list_llm_calls(job_id))
        # Khoá capability là `facts[0]` — id registry của CHÍNH engine vừa được
        # chạy. Với Chimera đó là `spec.engine`/`plan.merge_engine`, không phải
        # `engine.engine_id`: `OpusMtEngine` mang `model_ref` chứ không mang id
        # registry, nên tra theo thuộc tính của engine sẽ trượt đúng ứng viên
        # in-process (cùng lý do `self._engines` đánh khoá theo `spec.id`).
        out, missing = self._translate_batch(engine, batch, glossary, opts, report,
                                             progress, facts=facts, job=job,
                                             placeholder_terms=self._placeholder_terms(
                                                 facts[0], glossary, opts.source_lang),
                                             echo_retry=self._echo_retry(facts[0]),
                                             # `echo_guard` KHÔNG đi qua đường
                                             # Chimera, và đây là quyết định chứ
                                             # không phải thiếu sót: một ứng viên
                                             # ném `EchoProblem` sẽ giết cả lô
                                             # `N+1` lời gọi của chế độ đó (runner
                                             # không có nhánh bắt lỗi từng ứng
                                             # viên), trong khi Chimera ĐÃ có phép
                                             # đo echo riêng cho từng ứng viên
                                             # (`candidate_metrics`). Cổng này chỉ
                                             # canh đường dịch thường — đường ghi
                                             # thẳng `done`.
                                             echo_guard=False)
        rows = self._repos.list_llm_calls(job_id)[before:]
        return out, missing, _totals_of(rows)

    def _cancel_requested(self, job) -> bool:
        """Cờ huỷ của job, ĐỌC LẠI TỪ REPO mỗi lô.

        `job.cancel_requested` là ẢNH CHỤP: `worker._run_one` bốc job bằng
        `oldest_queued()` TRƯỚC khi handler chạy, còn yêu cầu huỷ thật
        (`routes_jobs` → `repos.request_cancel`) CHỈ ghi `jobs.cancel_requested=1`,
        và worker chỉ đọc lại cờ sau khi `run()` trả về. Tin ảnh chụp thì người
        dùng bấm huỷ mà cả bản dịch vẫn chạy hết, ghi `done` kèm QA, rồi job mới
        thành `cancelled` ở ranh giới — hai mặt của cùng một bản dịch nói hai
        chuyện khác nhau.

        Một lần đọc theo khoá chính mỗi lô là không đáng kể cạnh một lời gọi
        engine, và handler phải đúng bất kể ai gọi nó. Cờ trên `job` vẫn được giữ
        làm đường tắt cho test đơn vị (job giả không có hàng trong DB), nhưng thứ
        được TIN là lần đọc lại này. Job không còn hàng (`LookupError`, `NotFound`
        kế thừa nó) coi như không huỷ: hàng biến mất thì đã có lỗi khác nói lên.
        """
        if job.cancel_requested:
            return True
        job_id = getattr(job, "id", None)
        if job_id is None:
            return False
        try:
            return bool(self._repos.get_job(job_id).cancel_requested)
        except LookupError:
            return False

    def _ordered_prefix(self, source: list[Segment],
                        stored: list[Segment]) -> list[Segment]:
        """Phần đã dịch, xếp theo thứ tự NGUỒN và chỉ giữ id có thật ở nguồn.

        Thứ tự không phải chuyện hình thức: `export` ghép bản dịch theo VỊ TRÍ
        (`subtitle_format` lặp `transcript.segments`), nên một hàng lưu sai thứ tự
        vẫn đủ số lượng mà phụ đề đã lệch. Id lạ bị bỏ NGAY ở đây thay vì để nó đi
        vào `check_alignment` của mọi lô sau.
        """
        by_id: dict[int, Segment] = {}
        for s in stored:
            by_id.setdefault(s.i, s)
        return [by_id[s.i] for s in source if s.i in by_id]

    def _placeholder_terms(self, engine_id: str, glossary: list[Term],
                           source_lang: str) -> list[Term]:
        """Thuật ngữ sẽ được THAY bằng token cho `engine_id`; `[]` = không bảo vệ.

        Điều kiện duy nhất là CAPABILITY của registry
        (`spec.capabilities["term_placeholder"]`), không phải một hằng số: chỉ
        engine ĐÃ ĐO là giữ token nguyên vẹn mới được bật. Đo trên adapter thật:
        `hy-mt1.5-7b:q4_K_M` giữ `ZXQ{n}` 6/6 trong một lô 7 câu, còn chính nó thì
        KHÔNG theo policy Hán-Việt (trả `Cao Lei`, `núi Yantai` thay vì `Tào Lôi`,
        `Yên Đài Sơn`) — nên đây là engine cần cơ chế này nhất. Engine chưa đo thì
        để `false` (mặc định): bật một cơ chế chưa đo trên engine khác là đổi hành
        vi dịch của nó mà không có số nào bảo vệ.

        Glossary RỖNG ⇒ `[]` ngay: không có thuật ngữ thì không có gì để bảo vệ, và
        đường đi phải trùng khít bản không có tính năng (kể cả khi engine khai
        capability). `plan_terms` lọc thêm lần nữa theo ngôn ngữ + trạng thái duyệt
        — xem docstring của nó.
        """
        if not glossary:
            return []
        capabilities = self._capabilities.get(engine_id) or {}
        if not capabilities.get("term_placeholder"):
            return []
        return plan_terms(glossary, source_lang=source_lang)

    def _batch_items_for(self, engine_id: str) -> int:
        """Trần số mục của MỘT lời gọi engine cho `engine_id`.

        Ba nguồn, theo thứ tự THẮNG:

        1. `batch_items` truyền vào constructor (test, phép đo) — một con số cụ
           thể luôn thắng, nếu không thì không đo lại được kích thước lô nào;
        2. `capabilities.max_items_per_call` của registry — DỮ LIỆU của engine;
        3. `mt.DEFAULT_MAX_ITEMS` (30) — chính sách chung.

        Vì sao (2) tồn tại, bằng SỐ ĐO (clip 115 đoạn, cùng prompt p2, cùng
        `temperature`): `hy-mt-1.5-7b` echo **90/115 đoạn ở lô 30** và **0/115 ở
        lô 1**. Nghĩa là với engine này, "một lời gọi chịu được bao nhiêu mục" có
        câu trả lời RIÊNG, và câu trả lời đó là 1 — nhưng nó KHÔNG phải chính sách
        chung cho mọi engine (`opus-mt`: 0 echo ở cả ba lô, mà lô 1 thì chậm gấp
        1,15 lần). Một con số chung không nói được cả hai điều đó.
        """
        if self._batch_items is not None:
            return int(self._batch_items)
        capabilities = self._capabilities.get(engine_id) or {}
        declared = capabilities.get("max_items_per_call")
        return int(declared) if declared else DEFAULT_MAX_ITEMS

    def _echo_retry(self, engine_id: str) -> bool:
        """`engine_id` có được DỊCH LẠI các đoạn bị chép nguyên chữ nguồn không.

        Cùng khuôn với `_placeholder_terms` ở trên và cùng lý do: capability của
        registry là NGUỒN SỰ THẬT (`spec.capabilities["echo_retry"]`), vì bật cơ
        chế này là thêm lời gọi engine (chậm hơn) cho từng đoạn bị echo. Engine
        không khai — `opus-mt`, `qwen2.5-*`, và cả engine in-process — đi đúng
        đường cũ từng byte.

        ⚠️ `echo_retry` KHÔNG thay `max_items_per_call`; hai thứ trả lời hai câu
        khác nhau và số đo nói rõ: lô 1 + cờ dịch lại = 55,3 s / 116 lời gọi / 0
        echo; lô 30 + cờ dịch lại = 75,0 s / 94 lời gọi / 0 echo (89 lần dịch lại
        đắt hơn 115 lời gọi đều đặn). Nên cấu hình đúng là "gọi một mục" TRƯỚC,
        và cờ dịch lại là LƯỚI AN TOÀN cho đoạn hiếm hoi vẫn bị chép.

        Số đo đứng sau cờ này (clip 115 đoạn, `20261019-term-placeholder-clip`):
        `hy-mt-1.5-7b` echo 59–89/115 đoạn ở lô 30 và 8–29/115 ở lô 8–15, nên đây
        là engine cần cơ chế; `opus-mt` echo 0/115 ở cả ba lô cùng clip.
        """
        capabilities = self._capabilities.get(engine_id) or {}
        return bool(capabilities.get("echo_retry"))

    def _echo_guard(self, engine_id: str) -> bool:
        """`engine_id` có bị TỪ CHỐI cả lô khi đầu ra vẫn chép nguyên chữ nguồn không.

        Cùng khuôn với `_echo_retry`/`_placeholder_terms`: capability của registry
        là NGUỒN SỰ THẬT (`spec.capabilities["echo_guard"]`), không phải một hằng
        số trong code. Khác `echo_retry` ở HẬU QUẢ, không ở phép đo: `echo_retry`
        dịch lại rồi vẫn nhận bản chép (gắn cờ), còn cổng này từ chối lô để hàng
        dịch thành `failed` thay vì `done` chứa chữ nguồn.

        Vì sao cần một cờ RIÊNG chứ không nâng cấp `echo_retry`: bật cổng là đổi
        ngữ nghĩa của đường ống (một lô có thể làm hỏng cả bản dịch), và ngữ nghĩa
        đó chỉ được phép bật cho engine ĐÃ ĐO. `opus-mt` — 0/115 đoạn echo ở cả ba
        lô 8/15/30 trên cùng clip — không khai cờ, nên nó đi đúng đường cũ từng
        byte và KHÔNG chạy `echoes_source` lấy một lần.

        Số đo đứng sau cờ (clip 115 đoạn `20261019-name-patch-smoke/
        large-v3-beam5-prevfalse.json`, 5 thuật ngữ): `hy-mt-1.5-7b` echo
        0–8/115 ở lô 8, 29/115 ở lô 15, **59–89/115 ở lô 30** — nên "hỏng ở lô 30"
        không phải chuyện của một kích thước lô, và cổng phải độc lập với nó.
        """
        capabilities = self._capabilities.get(engine_id) or {}
        return bool(capabilities.get("echo_guard"))

    def _protect_batch(self, batch: list[Segment], terms: list[Term],
                       report, progress: float) -> tuple[
                           list[Segment], dict[int, tuple[dict[str, str], dict[str, int]]],
                           dict[int, list[str]]]:
        """Token hoá từng segment; trả `(lô đã che, {id: (map, số lần)}, cờ nguồn)`.

        Từng segment một, không token hoá cả lô trong một lần gọi: token phải được
        khôi phục đúng segment, và một thuật ngữ bị MẤT ở segment này không được
        làm cờ `token_lost` của segment khác. Đánh khoá theo `i` chứ theo vị trí
        vì `check_alignment` bảo đảm id, còn vị trí thì không.

        Số lần mỗi token có trong bản ĐÃ CHE được đếm NGAY ĐÂY, trước khi engine
        chạm vào: cùng một thuật ngữ xuất hiện hai lần trong câu thì token của nó
        cũng phải có mặt hai lần, và `restore` cần con số đó để không gắn
        `token_duplicated` cho một câu lặp tên bình thường.

        `qa=list(s.qa)` là BẮT BUỘC, không phải phòng xa: `dataclasses.replace`
        GIỮ NGUYÊN object list của trường `qa`, nên bản sao đã che và segment
        NGUỒN dùng chung một list — thêm cờ vào bản dịch sẽ ghi ngược vào chính
        segment của hàng `transcript` đang giữ trong bộ nhớ. Segment bị va chạm
        cũng phải sao chép `qa` dù `text` không đổi, vì nó ĐƯỢC gắn cờ.

        Va chạm với chữ có sẵn trong NGUỒN (`ZXQ1` đã nằm trong câu, do ASR nghe
        ra hoặc do kịch bản) ⇒ BỎ bảo vệ cho RIÊNG câu đó và gắn
        `token_collision_in_source`; câu vẫn được dịch bình thường. Không được che
        lên chữ có sẵn: `restore` không phân biệt được token của ta với chữ của bản
        gốc nên sẽ thay cả hai. Vẫn ném `ValueError` cho những va chạm khác (tiền
        tố có trong câu mà không kèm số) — chúng cũng rơi vào cùng đường này.
        """
        protected: list[Segment] = []
        plans: dict[int, tuple[dict[str, str], dict[str, int]]] = {}
        source_flags: dict[int, list[str]] = {}
        for s in batch:
            try:
                if has_token_like(s.text):
                    raise ValueError(
                        f"chữ nguồn đã có sẵn chuỗi giống token ({s.text!r})")
                text, mapping = protect(s.text, terms)
            except ValueError as exc:
                report(progress, f"segment {s.i} không che thuật ngữ: {exc}")
                protected.append(replace(s, qa=list(s.qa)))
                source_flags[s.i] = [TOKEN_COLLISION]
                continue
            if not mapping:
                protected.append(s)
                continue
            protected.append(replace(s, text=text, qa=list(s.qa)))
            plans[s.i] = (mapping, count_tokens(text, mapping))
        return protected, plans, source_flags

    def _restore_batch(self, out: list[Segment],
                       plans: dict[int, tuple[dict[str, str], dict[str, int]]],
                       source_flags: dict[int, list[str]]) -> dict[str, list[int]]:
        """Khôi phục token trong `out` tại chỗ; trả `{cờ QA: [id segment]}`.

        Chỉ `text` đổi (và `qa` thêm cờ): `i`/`start`/`end`/`words` đến từ segment
        của adapter và không bị chạm.

        Bốn cờ, theo `term_placeholder`: ba cờ của `restore` cộng
        `token_collision_in_source` do `_protect_batch` quyết định. Gộp chúng là
        mất đúng thứ người sửa cần biết:

        * `token_lost` — model BỎ token (thường là bỏ cả cái tên). Giữ chữ của
          model, không bịa lại; ném thì mất cả câu vì một cái tên.
        * `token_duplicated` — model viết token NHIỀU lần hơn nguồn.
        * `token_unknown` — model bịa/đổi số token; chữ đó được để NGUYÊN VĂN trong
          phụ đề, không đoán ra tên từ một con số không ánh xạ được.
        * `token_collision_in_source` — câu nguồn đã có chuỗi giống token nên câu
          đó KHÔNG được che.

        CẢ BỐN chỉ là CẢNH BÁO: không chặn xuất bản, không thử lại bằng kiểu token
        khác (lý do: xem docstring đầu `term_placeholder`).

        Cờ đi vào `Segment.qa`, kênh đã có sẵn (`models.Segment.qa` ->
        `translations.segments` -> `subtitle_format` gộp vào `qa` của từng dòng
        phụ đề).
        """
        flagged: dict[str, list[int]] = {}
        for s in out:
            flags: list[str] = []
            plan = plans.get(s.i)
            if plan is not None:
                mapping, expected = plan
                text, issues = restore(s.text, mapping, expected=expected)
                s.text = text
                flags.extend(issue.split(":", 1)[0] for issue in issues)
            flags.extend(source_flags.get(s.i, ()))
            for flag in flags:
                if flag not in s.qa:
                    s.qa.append(flag)
                ids = flagged.setdefault(flag, [])
                if s.i not in ids:
                    ids.append(s.i)
        return flagged

    def _translate_batch(self, engine, batch: list[Segment], glossary, opts,
                         report, progress: float, *, facts, job=None,
                         placeholder_terms: list[Term] | None = None,
                         echo_retry: bool = False,
                         echo_guard: bool = False) -> tuple[
                             list[Segment] | None, list[int]]:
        """Che thuật ngữ quanh `_translate_batch_impl`, rồi khôi phục.

        `placeholder_terms` rỗng/`None` ⇒ gọi thẳng `_translate_batch_impl` với
        ĐÚNG object `batch` nhận được, nên engine không khai capability đi đường
        cũ từng byte (cùng danh sách, cùng thứ tự, cùng đối tượng — `test_
        translate_placeholder_wiring` ghim đúng chuỗi mà adapter nhận).

        Lô không có thuật ngữ nào xuất hiện cũng đi thẳng đường cũ: che một lô
        không có gì để che chỉ tạo ra bản sao segment vô nghĩa, và câu không chứa
        thuật ngữ phải ra y hệt đường dịch hiện tại (kể cả khi engine đã bật
        `term_placeholder`).

        `echo_retry` đi xuống NGUYÊN `_translate_batch_impl` chứ không nằm ở đây:
        chỗ đó mới là nơi có đồng thời `batch` (chữ đã đưa cho engine) và `out`
        (chữ engine trả), tức nơi DUY NHẤT so được "nó có chép nguyên không".
        So ở đây thì phép so rơi vào bản ĐÃ khôi phục token — và lúc đó một câu
        vừa echo vừa được thay thuật ngữ sẽ không còn khớp nguyên văn nữa.

        Ghi chú về Chimera: lượt pha đi qua CÙNG `_translate_batch` này, nên nó
        cũng nhận token và khôi phục y như ứng viên — token không bao giờ chảy vào
        bản ghi cuối của chế độ đó. Cùng lý do, lượt pha cũng dịch lại đoạn echo
        nếu engine của nó khai `echo_retry`.

        `echo_guard` cũng đi xuống NGUYÊN `_translate_batch_impl`, cùng lý do như
        `echo_retry`: chỉ ở đó mới có đồng thời chữ ĐÃ ĐƯA cho engine (kể cả bản đã
        token hoá) và chữ engine TRẢ, tức chỗ duy nhất phán được "nó có chép
        nguyên không". So trên bản đã khôi phục là muộn: thuật ngữ đã thành tiếng
        Việt nên một câu vừa echo vừa có thuật ngữ không còn khớp nguyên văn nữa.
        """
        if not placeholder_terms:
            return self._translate_batch_impl(engine, batch, glossary, opts, report,
                                              progress, facts=facts, job=job,
                                              echo_retry=echo_retry,
                                              echo_guard=echo_guard)
        protected, plans, source_flags = self._protect_batch(
            batch, placeholder_terms, report, progress)
        if not plans and not source_flags:
            return self._translate_batch_impl(engine, batch, glossary, opts, report,
                                              progress, facts=facts, job=job,
                                              echo_retry=echo_retry,
                                              echo_guard=echo_guard)
        out, missing = self._translate_batch_impl(engine, protected, glossary, opts,
                                                  report, progress, facts=facts,
                                                  job=job, echo_retry=echo_retry,
                                                  echo_guard=echo_guard)
        # Lô hỏng hẳn (`None`) thì không có chữ nào để khôi phục: bên gọi không
        # được ghi gì từ lô này, kể cả một segment đã khôi phục một nửa.
        if out is None:
            return None, missing
        flagged = self._restore_batch(out, plans, source_flags)
        for flag in sorted(flagged):
            report(progress, f"segment {flagged[flag]} mang cờ {flag}: giữ bản dịch "
                             f"của model")
        return out, missing

    def _translate_batch_impl(self, engine, batch: list[Segment], glossary, opts,
                              report, progress: float, *, facts, job=None,
                              echo_retry: bool = False,
                              echo_guard: bool = False) -> tuple[
                                  list[Segment] | None, list[int]]:
        """Chính sách alignment ba bước (spec §4.2).

        Trả `(kết quả, [])` khi thành công, `(None, id_thiếu)` khi thất bại hẳn.
        `None` nghĩa là bên gọi KHÔNG được ghi gì từ lô này.

        `progress` là tiến độ ĐÃ ghi được, chỉ để dòng log không bịa ra một con số
        mới: `report` phải ghi cả tiến độ lẫn thông báo, và tiến độ không được
        giảm giữa hai dòng (một con số 0.0 cho một dòng chẩn đoán sẽ làm thanh
        tiến độ của giao diện nhảy lùi, mà không ai đọc log lại tưởng là 0%).

        `facts` là `(engine, prompt_version)` ĐÃ GHI trên hàng `translations`; mỗi
        lần chạm engine để lại MỘT hàng `llm_calls` (spec §4.2), kể cả lần hỏng —
        đó chính là dữ liệu để đo "engine nào hay hỏng alignment" (spec §10).

        `echo_retry` là BƯỚC (a4), chạy sau khi lô đã qua alignment và trước khi
        trả về: đoạn nào engine trả CHÍNH chữ nguồn thì được dịch lại một mình.
        Vì sao phải sau alignment: echo KHÔNG làm lệch số mục, nên nó đi qua cả ba
        bước (a)(b)(c) mà không bước nào động tới — đúng kiểu hỏng im lặng mà
        `check_alignment` không nhìn thấy và `qa_translation` chỉ báo được từng
        dòng.

        `echo_guard` là bước (a4') cùng chỗ, chạy TRƯỚC `echo_retry` và thay hẳn nó
        khi được khai (xem `_guard_echoes`): dịch lại từng đoạn bị chép, và nếu
        vẫn chép thì ném `EchoProblem` — không nhận lô. Cả bước (b) cũng phải mang
        cổng này: (b) là đường chạy khi lô lớn hỏng alignment, và một đoạn echo
        sinh ra ở đó vẫn là một hàng `done` chứa chữ nguồn nếu không ai chặn.
        """
        # (a) Retry trong cùng lô, tối đa MỘT lần. `attempts` của engine được đếm
        # cả lần hỏng nên con số ở đây đo được: mutant `for attempt in (1,)` mất
        # đúng một lần thử.
        for attempt in (1, 2):
            try:
                out = engine.translate(batch, glossary, opts)
            except (AlignmentProblem, ValueError) as exc:
                # HAI lớp hỏng mà HỢP ĐỒNG LỖI CỦA ADAPTER đã tuyên bố, và cả hai
                # đều là hỏng CỦA LÔ NÀY chứ không phải của đường ống:
                #
                # * `AlignmentProblem` — adapter tự ném khi nó parse phản hồi và
                #   thấy số mục không khớp (`adapters/mt/prompts.parse_batch_response`);
                # * `ValueError` — phản hồi DỊ DẠNG: không phải JSON, thiếu khoá
                #   `translations`, hoặc một mục sai khoá/kiểu (`test_mt_prompts.py`
                #   ghim sáu hình dạng như vậy). ĐO ĐƯỢC trên bản ghi thật: lần chạy
                #   thật với `qwen2.5-7b` chết ở 270/464 vì model trả
                #   `{"i:": 277, "text": "…"}` — khoá `i:` thay vì `i`.
                #
                # Cả hai phải đi CÙNG đường với `check_alignment` ngay dưới: ghi hàng
                # đếm, báo log, thử lại cả lô, rồi hạ cấp từng segment. Trước bản này
                # chúng rơi vào `except Exception` bên dưới (đều là lớp con của
                # `Exception`) và bị coi là lỗi VẬN CHUYỂN rồi NỔI LÊN — chính sách ba
                # bước không bao giờ chạy. Bản ghi thật `data/app.db` job #4
                # (`qwen2.5-7b`, 464 đoạn): log chỉ có MỘT dòng `LỖI: engine trả 101
                # mục, cần 135`, không có dòng `lệch alignment (lần 1)` và không có
                # dòng `hạ cấp`, `llm_calls` có ĐÚNG MỘT hàng mỗi lần chạy ⇒ 0/464
                # đoạn, job `failed` ở 0%.
                #
                # `str(exc)` chứ không `exc.reason`: `ValueError` không có `.reason`.
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                report(progress, f"lệch alignment (lần {attempt}): {exc}")
                continue
            except Exception as exc:      # noqa: BLE001 - hàng đếm PHẢI có mặt
                # Lỗi vận chuyển/HTTP (Ollama sập) không phải `AlignmentProblem`
                # nên nó không được thử lại, nhưng nó vẫn là một lần CHẠM ENGINE
                # đã tiêu thời gian — nuốt nó khỏi `llm_calls` là bỏ mất đúng
                # nhóm hỏng mà §4.2 tồn tại để đếm. Ghi rồi mới nổi lên.
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                raise
            try:
                check_alignment(batch, out)
            except AlignmentProblem as exc:
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                report(progress, f"lệch alignment (lần {attempt}): {exc.reason}")
                continue
            self._record_call(engine, facts, job, None,
                              getattr(engine, "last_stats", None))
            if echo_guard:
                # BƯỚC (a4'): cổng CHẶN của engine đã ĐO là hay chép nguồn. Đứng
                # TRƯỚC `echo_retry` vì hai cờ trả lời hai câu khác nhau và cổng
                # là câu đang được sửa: `echo_retry` nhận bản chép kèm cờ, cổng
                # thì không nhận.
                return self._guard_echoes(engine, batch, out, glossary, opts,
                                          report, progress, facts=facts, job=job)
            if echo_retry:
                # BƯỚC (a4): lô đã qua alignment, nhưng có đoạn model chỉ CHÉP
                # lại chữ nguồn. Dịch lại ĐÚNG đoạn đó, mỗi đoạn một lời gọi.
                return self._retry_echoed(engine, batch, out, glossary, opts,
                                          report, progress, facts=facts, job=job)
            return out, []

        # (b) Hạ cấp: lô lớn là lúc LLM hay hỏng nhất, nên dịch từng segment.
        # Lô một phần tử là đủ để engine không còn gì để lệch.
        report(progress, f"hạ cấp xuống dịch từng segment ({len(batch)} segment)")
        out: list[Segment] = []
        failed: int | None = None
        for s in batch:
            try:
                one = engine.translate([s], glossary, opts)
                check_alignment([s], one)
            except (AlignmentProblem, ValueError) as exc:
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                # Bước (b) là chỗ CUỐI: một phản hồi dị dạng cho MỘT đoạn cũng là
                # "đoạn này chưa có bản dịch", không phải lỗi vận chuyển — nó phải
                # được đếm và báo ra như mọi đoạn hỏng khác, thay vì ném lên và bỏ
                # luôn phần còn lại của lô.
                report(progress, f"segment {s.i} thất bại: {exc}")
                if failed is None:
                    failed = s.i
                # KHÔNG retry lại từng segment và KHÔNG `break`: bước (b) chỉ được
                # thử mỗi segment MỘT lần (retry một lần là chuyện của bước (a)),
                # và phần còn lại vẫn được thử để chẩn đoán đủ. Không có gì được
                # GHI cho tới khi cả lô xong, nên không việc gì bị mất; lần chạy
                # lại vẫn thấy đúng id hỏng là còn thiếu.
                continue
            except Exception as exc:      # noqa: BLE001 - cùng lý do như bước (a)
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                raise
            self._record_call(engine, facts, job, None,
                              getattr(engine, "last_stats", None))
            if echo_guard and echoes_source(s.text, one[0].text,
                                            source_lang=opts.source_lang,
                                            target_lang=opts.target_lang):
                # Bước (b) là chỗ CUỐI của chính sách alignment, và nó không có
                # bước nào để hạ cấp thêm: một đoạn bị chép ở đây mà vẫn được
                # `out.append` thì sẽ thành một hàng `done` chứa chữ nguồn — đúng
                # lỗi mà cổng tồn tại để chặn. Ném ngay, kèm đúng id đó.
                report(progress, f"echo_guard: segment {s.i} vẫn chép nguyên chữ "
                                 f"nguồn ở bước hạ cấp")
                raise EchoProblem([s.i], echoed=1, batch=len(batch),
                                  reason=f"đoạn {s.i} vẫn là bản chép nguồn sau "
                                         f"khi dịch riêng")
            out.append(one[0])
        if failed is None:
            return out, []

        # (c) Id hỏng ĐẦU TIÊN, cộng mọi segment chưa có bản dịch ở trong lô. Vì
        # bước (b) đã thử HẾT lô, danh sách này là "id nào chưa có bản dịch" theo
        # đúng nghĩa đen của nó, và lần chạy lại sẽ bắt đầu từ `failed` (xem
        # `remaining` ở `translate`: id SAU nó cũng còn thiếu nên không bị bỏ qua).
        got = {y.i for y in out}
        return None, [x.i for x in batch if x.i not in got]

    def _guard_echoes(self, engine, batch: list[Segment], out: list[Segment],
                      glossary, opts, report, progress: float, *, facts,
                      job=None) -> tuple[list[Segment] | None, list[int]]:
        """Cổng CHẶN echo (bước a4') cho engine khai `capabilities.echo_guard`.

        Vì sao cổng này tồn tại, bằng SỐ ĐO (clip 115 đoạn `20261019-name-patch-
        smoke/large-v3-beam5-prevfalse.json`, `hy-mt-1.5-7b`, 5 thuật ngữ):

            lô | trung vị | đoạn echo | chữ Hán
             8 | 63,54 s  | 0–8/115   | 0–54
            15 | 44,11 s  | 29/115    | 181
            30 | 32,89 s  | 59–89/115 | 389–629

        Số mục VẪN KHỚP trong mọi ca, nên `check_alignment` cho qua và trước bản
        này cả lượt ghi `done`. Vì thế cơ chế KHÔNG phải "hạ kích thước lô" (echo có
        ở cả lô 8) và KHÔNG phải "gắn thêm cờ" (cờ không chặn): dịch lại từng đoạn
        một mình, và đoạn vẫn chép thì cả lô bị từ chối bằng `EchoProblem`.

        Vì sao lô 1 cho lần dịch lại: cùng lý do `_retry_echoed` ghi — lô là thứ
        làm model chép nguồn; đo trên cùng clip, lô 1 cho 0/115 đoạn echo, nên một
        lời gọi chỉ có MỘT câu là đủ để model dịch thật.

        Ba nhánh, theo đúng thứ tự:

        * dịch lại được, hết echo -> dùng bản dịch mới, không gắn cờ;
        * dịch lại vẫn echo -> vào `still`, và CUỐI VÒNG `raise EchoProblem` kèm
          danh sách id: đây là điểm khác `_retry_echoed` (nhánh đó giữ chữ model
          kèm cờ `echo`), và là toàn bộ lý do cổng này được thêm;
        * lần dịch lại hỏng alignment/dị dạng -> cũng vào `still`: không lấy được
          bản dịch sạch thì đoạn đó vẫn là bản chép, tức đúng lớp lỗi đang chặn.

        Không `continue` sau khi gom `still` là có chủ ý: các đoạn CÒN LẠI của lô
        vẫn được thử, nên thông báo lỗi liệt kê ĐỦ id hỏng thay vì id đầu tiên.

        Mỗi lần chạm engine — kể cả lần hỏng — để lại MỘT hàng `llm_calls` (§4.2),
        nên chi phí của cổng ĐẾM ĐƯỢC: một lô 30 mục bị echo 20 đoạn sinh thêm 20
        hàng, và đó là con số phải nhìn trước khi bật cờ cho engine khác.

        Số đo của lần chạy hiện ra ở HAI kênh, không chỉ một câu văn: mỗi lô in
        `echo_guard:<n>/<số mục>` (tiền tố ổn định để grep trong `jobs` log), và
        `EchoProblem` mang `.ids`/`.echoed` để `jobs.error` có cả tên lỗi lẫn số.
        """
        source_lang = getattr(opts, "source_lang", "zh")
        target_lang = getattr(opts, "target_lang", "vi")
        by_id = {s.i: s for s in batch}
        echoing = [segment for segment in out
                   if segment.i in by_id
                   and echoes_source(by_id[segment.i].text, segment.text,
                                     source_lang=source_lang,
                                     target_lang=target_lang)]
        if not echoing:
            return out, []
        report(progress, f"echo_guard:{len(echoing)}/{len(batch)} đoạn chép nguyên "
                         f"chữ nguồn: dịch lại riêng từng đoạn")
        still: dict[int, Segment] = {}
        for segment in echoing:
            source = by_id[segment.i]
            try:
                one = engine.translate([source], glossary, opts)
                check_alignment([source], one)
            except (AlignmentProblem, ValueError) as exc:
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                report(progress, f"echo_guard: dịch lại segment {segment.i} thất "
                                 f"bại: {exc}")
                still[segment.i] = segment
                continue
            except Exception as exc:      # noqa: BLE001 - hàng đếm PHẢI có mặt
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                raise
            self._record_call(engine, facts, job, None,
                              getattr(engine, "last_stats", None))
            if echoes_source(source.text, one[0].text, source_lang=source_lang,
                             target_lang=target_lang):
                still[segment.i] = one[0]
                continue
            # CHỈ `text` đổi: `i`/`start`/`end`/`words` (và `qa`) lấy từ segment
            # của LÔ — bản mà `check_alignment` vừa xác nhận — chứ không lấy từ
            # segment engine trả về lần dịch lại. Cùng bất biến của
            # `_retry_echoed`/`_restore_batch`, và là thứ `subtitle_format` dùng để
            # ghép phụ đề theo VỊ TRÍ; mốc thời gian do model gửi lại không có
            # quyền đổi một dòng phụ đề đã có mốc đúng.
            index = next(position for position, item in enumerate(out)
                         if item.i == segment.i)
            out[index] = replace(source, text=one[0].text, qa=list(source.qa))

        if still:
            ids = sorted(still)
            report(progress, f"echo_guard:{len(ids)}/{len(batch)} đoạn VẪN là bản "
                             f"chép nguồn sau khi dịch lại: {ids}")
            raise EchoProblem(ids, echoed=len(ids), batch=len(batch),
                              reason=(f"{len(ids)}/{len(batch)} đoạn vẫn là bản "
                                      f"chép nguyên chữ nguồn sau khi dịch lại "
                                      f"riêng: {ids}"))
        report(progress, f"echo_guard: đã sửa {len(echoing)}/{len(batch)} đoạn"
                         f" (dịch lại riêng), không còn đoạn chép nguồn")
        return out, []

    def _retry_echoed(self, engine, batch: list[Segment], out: list[Segment],
                      glossary, opts, report, progress: float, *, facts,
                      job=None) -> tuple[list[Segment] | None, list[int]]:
        """Dịch lại RIÊNG từng đoạn bị chép nguyên chữ nguồn (bước a4).

        Vì sao lô 1: lô là thứ làm model chép nguồn — đo được trên clip 115 đoạn,
        cùng một câu `作为一个搞艺术的` ra tiếng Việt ở lô 4 và bị chép ở lô 20; một
        lời gọi chỉ có MỘT câu thì không còn "cả mảng JSON để chép lại". Đây cũng
        đúng là hình dạng bước (b) đã dùng khi lô hỏng alignment.

        Ba nhánh, theo đúng thứ tự đã cân nhắc:

        * dịch lại ĐƯỢC (không còn echo) -> dùng bản dịch mới, không gắn cờ;
        * dịch lại vẫn echo -> giữ chữ của model và gắn `echo` lên `Segment.qa`.
          KHÔNG ném, KHÔNG bỏ segment: một dòng đọc được (dù sai ngôn ngữ) vẫn hơn
          một dòng mất, và cờ này đi thẳng tới phụ đề qua `Segment.qa`;
        * lần dịch lại hỏng alignment -> cũng gắn cờ và giữ bản cũ. Hỏng ở đây
          KHÔNG được biến thành `(None, missing)` như bước (b): lô đã có bản dịch
          hợp lệ về số mục, và trả `None` sẽ khiến cả lô bị vứt vì một lần dịch
          lại phụ.

        Mỗi lần chạm engine — kể cả lần hỏng — vẫn để lại MỘT hàng `llm_calls`
        (§4.2), nên chi phí của cơ chế này ĐẾM ĐƯỢC: một lượt có 89 đoạn echo sẽ
        có 89 hàng thêm, và đó là con số phải nhìn trước khi bật cờ này cho engine
        khác.

        Trả `(out, [])` luôn: danh sách id thiếu là chuyện của bước (b)(c).
        """
        by_id = {s.i: s for s in batch}
        retried = 0
        still = 0
        for index, segment in enumerate(out):
            source = by_id.get(segment.i)
            if source is None or not is_echo(source.text, segment.text):
                continue
            retried += 1
            report(progress, f"segment {segment.i} là bản chép nguyên chữ nguồn: "
                             f"dịch lại riêng")
            try:
                one = engine.translate([source], glossary, opts)
                check_alignment([source], one)
            except (AlignmentProblem, ValueError) as exc:
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                report(progress, f"dịch lại segment {segment.i} thất bại: {exc}")
                self._flag_echo(segment)
                still += 1
                continue
            except Exception as exc:    # noqa: BLE001 - hàng đếm PHẢI có mặt
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                raise
            self._record_call(engine, facts, job, None,
                              getattr(engine, "last_stats", None))
            if is_echo(source.text, one[0].text):
                self._flag_echo(one[0])
                still += 1
            out[index] = one[0]
        if retried:
            report(progress, f"dịch lại {retried} đoạn bị echo, còn {still} đoạn "
                             f"vẫn là bản chép nguồn (cờ {ECHO_FLAG})")
        return out, []

    def _flag_echo(self, segment: Segment) -> None:
        """Gắn `ECHO_FLAG` lên `Segment.qa` của ĐÚNG segment đó, không nhân đôi cờ.

        Gán một LIST MỚI chứ không `append`: `dataclasses.replace` — đường mà cả
        hai adapter dịch dùng — GIỮ NGUYÊN object list của trường `qa`, nên
        `append` ở đây sẽ ghi ngược vào chính segment của hàng `transcript` đang
        giữ trong bộ nhớ (cùng lớp lỗi mà `_protect_batch` đã ghi lại). Đoạn echo
        có thể là BẤT KỲ đoạn nào, không chỉ đoạn đã được `_protect_batch` sao
        chép, nên ở đây không được dựa vào việc "chắc nó đã được copy".

        Cùng khuôn với `_restore_batch`: `qa` là kênh đã có sẵn
        (`models.Segment.qa` -> `translations.segments` -> `subtitle_format`), nên
        cờ đi tới phụ đề mà không cần cột mới.
        """
        if ECHO_FLAG not in segment.qa:
            segment.qa = [*segment.qa, ECHO_FLAG]

    def _record_call(self, engine, facts, job, error, stats) -> None:
        """Ghi MỘT hàng `llm_calls` cho ĐÚNG một lần chạm engine.

        `ok=False` cộng `error` khi lần gọi đó hỏng (lệch alignment hoặc lỗi
        vận chuyển); `tokens_in`/`tokens_out`/`duration_ms` lấy từ `last_stats`
        của CHÍNH lần gọi đó — giá trị ở đây là dữ liệu CỦA MỘT HÀNG, còn tổng
        của cả bản dịch được cộng lại từ các hàng này ở cuối `translate`.

        `model_ref` lấy từ engine (`getattr`): nó là tên model THẬT SỰ được gọi,
        thứ mà registry biết nhưng handler không giữ. Engine không khai thì ghi
        `None` — cột đó cho phép NULL, và bịa ra `spec.id` sẽ trộn "model đã gọi"
        với "khoá registry".
        """
        engine_id, prompt_version = facts
        self._repos.add_llm_call(
            job_id=getattr(job, "id", None),
            engine=engine_id,
            model_ref=getattr(engine, "model_ref", None),
            prompt_version=prompt_version,
            tokens_in=getattr(stats, "tokens_in", None),
            tokens_out=getattr(stats, "tokens_out", None),
            duration_ms=getattr(stats, "duration_ms", None),
            ok=error is None,
            error=None if error is None else str(error),
        )

    def _totals_for(self, job_id: int | None) -> _Totals:
        """Cộng mọi hàng `llm_calls` của job thành số của CẢ bản dịch.

        Nguồn là DB chứ không phải một biến đếm trong bộ nhớ: cùng một nguồn với
        thứ `llm_calls` phơi ra cho người vận hành, nên `translations` và
        `llm_calls` không thể nói hai con số khác nhau. `job_id=None` (job giả
        của test đơn vị) vẫn cộng được: `list_llm_calls(None)` trả MỌI hàng, và
        job giả không có hàng nào khác trong DB của nó.
        """
        rows = self._repos.list_llm_calls(job_id)
        return _Totals(tokens_in=_sum_rows(rows, "tokens_in"),
                       tokens_out=_sum_rows(rows, "tokens_out"),
                       duration_ms=_sum_rows(rows, "duration_ms"))
