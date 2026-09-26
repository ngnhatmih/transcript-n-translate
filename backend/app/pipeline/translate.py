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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.domain.alignment import AlignmentProblem, check_alignment
from app.domain.glossary_match import approved
from app.domain.models import Segment
from app.domain.mt import DEFAULT_MAX_CHARS, MtOpts, batch_segments
from app.domain.mt_qa import QaLimits, qa_translation


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


class TranslateHandler:
    def __init__(self, repos, engines: dict[str, object], *,
                 batch_chars: int = DEFAULT_MAX_CHARS,
                 limits: QaLimits = QaLimits()) -> None:
        self._repos = repos
        self._engines = engines
        self._batch_chars = batch_chars
        self._limits = limits

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
            for batch in batch_segments(remaining, max_chars=self._batch_chars):
                # Hủy chỉ được kiểm GIỮA các lô: kill giữa lô để lại DB nửa vời và
                # model không được giải phóng (worker.checkpoint).
                if self._cancel_requested(job):
                    self._repos.set_translation_status(translation_id, "cancelled")
                    job.progress = len(done) / total if total else 1.0
                    report(job.progress, f"đã huỷ: giữ {len(done)}/{total} segment")
                    return

                translated, missing = self._translate_batch(
                    engine, batch, glossary, opts, report, job.progress,
                    facts=(stored.engine, stored.prompt_version), job=job)
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

        issues = qa_translation(source, done, glossary=glossary,
                                supports_glossary=engine.supports_glossary(),
                                limits=self._limits)
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

    def _translate_batch(self, engine, batch: list[Segment], glossary, opts,
                         report, progress: float, *, facts, job=None) -> tuple[
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
        """
        # (a) Retry trong cùng lô, tối đa MỘT lần. `attempts` của engine được đếm
        # cả lần hỏng nên con số ở đây đo được: mutant `for attempt in (1,)` mất
        # đúng một lần thử.
        for attempt in (1, 2):
            try:
                out = engine.translate(batch, glossary, opts)
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
            except AlignmentProblem as exc:
                self._record_call(engine, facts, job, exc,
                                  getattr(engine, "last_stats", None))
                report(progress, f"segment {s.i} thất bại: {exc.reason}")
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
            out.append(one[0])
        if failed is None:
            return out, []

        # (c) Id hỏng ĐẦU TIÊN, cộng mọi segment chưa có bản dịch ở trong lô. Vì
        # bước (b) đã thử HẾT lô, danh sách này là "id nào chưa có bản dịch" theo
        # đúng nghĩa đen của nó, và lần chạy lại sẽ bắt đầu từ `failed` (xem
        # `remaining` ở `translate`: id SAU nó cũng còn thiếu nên không bị bỏ qua).
        got = {y.i for y in out}
        return None, [x.i for x in batch if x.i not in got]

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
