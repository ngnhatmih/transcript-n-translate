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
"""
from __future__ import annotations

from typing import Callable

from app.domain.alignment import AlignmentProblem, check_alignment
from app.domain.glossary_match import approved
from app.domain.models import Segment
from app.domain.mt import MtOpts, batch_segments
from app.domain.mt_qa import QaLimits, qa_translation

DEFAULT_BATCH_CHARS = 1200


class TranslateHandler:
    def __init__(self, repos, engines: dict[str, object], *,
                 batch_chars: int = DEFAULT_BATCH_CHARS,
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
        # `queued` để lần retry sau không thấy một bản dịch nửa vời.
        engine = self._engines[engine_id]
        opts = MtOpts(source_lang=source_lang, target_lang=target_lang)
        glossary = approved(self._repos.list_terms(lang=source_lang))

        source = self._repos.get_transcript(transcript_id).segments
        done = self._ordered_prefix(
            source, self._repos.get_translation(translation_id).segments)
        done_ids = {s.i for s in done}
        total = len(source)

        report(0.0, f"dịch {len(done)}/{total} segment đã có (engine {engine_id})")

        # Retry bắt đầu từ segment ĐẦU TIÊN chưa có bản dịch, không dịch lại từ
        # đầu: `done` đọc từ hàng đã ghi ở lần chạy trước (spec §3, "Retry").
        remaining = [s for s in source if s.i not in done_ids]
        for batch in batch_segments(remaining, max_chars=self._batch_chars):
            # Hủy chỉ được kiểm GIỮA các lô: kill giữa lô để lại DB nửa vời và
            # model không được giải phóng (worker.checkpoint).
            if job.cancel_requested:
                self._repos.set_translation_status(translation_id, "cancelled")
                job.progress = len(done) / total if total else 1.0
                report(job.progress, f"đã huỷ: giữ {len(done)}/{total} segment")
                return

            translated, missing = self._translate_batch(
                engine, batch, glossary, opts, report, job.progress)
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
        stats = getattr(engine, "last_stats", None)
        self._repos.set_translation_status(
            translation_id, "done", qa_issues=issues,
            tokens_in=getattr(stats, "tokens_in", None),
            tokens_out=getattr(stats, "tokens_out", None),
            duration_ms=getattr(stats, "duration_ms", None),
        )
        job.progress = 1.0
        report(1.0, f"xong: {len(done)} segment, {len(issues)} issue QA")

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
                         report, progress: float) -> tuple[list[Segment] | None,
                                                            list[int]]:
        """Chính sách alignment ba bước (spec §4.2).

        Trả `(kết quả, [])` khi thành công, `(None, id_thiếu)` khi thất bại hẳn.
        `None` nghĩa là bên gọi KHÔNG được ghi gì từ lô này.

        `progress` là tiến độ ĐÃ ghi được, chỉ để dòng log không bịa ra một con số
        mới: `report` phải ghi cả tiến độ lẫn thông báo, và tiến độ không được
        giảm giữa hai dòng (một con số 0.0 cho một dòng chẩn đoán sẽ làm thanh
        tiến độ của giao diện nhảy lùi, mà không ai đọc log lại tưởng là 0%).
        """
        # (a) Retry trong cùng lô, tối đa MỘT lần. `attempts` của engine được đếm
        # cả lần hỏng nên con số ở đây đo được: mutant `for attempt in (1,)` mất
        # đúng một lần thử.
        for attempt in (1, 2):
            try:
                out = engine.translate(batch, glossary, opts)
                check_alignment(batch, out)
                return out, []
            except AlignmentProblem as exc:
                report(progress, f"lệch alignment (lần {attempt}): {exc.reason}")

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
                report(progress, f"segment {s.i} thất bại: {exc.reason}")
                if failed is None:
                    failed = s.i
                # KHÔNG retry lại từng segment và KHÔNG `break`: bước (b) chỉ được
                # thử mỗi segment MỘT lần (retry một lần là chuyện của bước (a)),
                # và phần còn lại vẫn được thử để chẩn đoán đủ. Không có gì được
                # GHI cho tới khi cả lô xong, nên không việc gì bị mất; lần chạy
                # lại vẫn thấy đúng id hỏng là còn thiếu.
                continue
            out.append(one[0])
        if failed is None:
            return out, []

        # (c) Id hỏng ĐẦU TIÊN, cộng mọi segment chưa có bản dịch ở trong lô. Vì
        # bước (b) đã thử HẾT lô, danh sách này là "id nào chưa có bản dịch" theo
        # đúng nghĩa đen của nó, và lần chạy lại sẽ bắt đầu từ `failed` (xem
        # `remaining` ở `translate`: id SAU nó cũng còn thiếu nên không bị bỏ qua).
        got = {y.i for y in out}
        return None, [x.i for x in batch if x.i not in got]
