"""Chạy MỘT LÔ ở chế độ CHIMERA: N ứng viên rồi MỘT lượt pha.

Vì sao là một lớp có TRẠNG THÁI chứ không phải một hàm thuần: kết quả của chế độ
này là một BẢN GHI TÍCH LUỸ theo lô (`candidates[].segments`, số token, số cờ QA),
và bản ghi đó phải còn nguyên khi lô thứ ba hỏng. Một hàm thuần trả về từng lô rời
sẽ để chỗ cộng dồn nằm ở handler — tức là ở đúng tệp đang phải giữ bốn bất biến
khác của `translations.segments`.

Vì sao nó KHÔNG tự gọi engine: `TranslateHandler._translate_batch` là chỗ DUY NHẤT
cài chính sách alignment ba bước (spec §4.2) và là chỗ duy nhất ghi `llm_calls`.
Runner nhận nó qua tham số `run=`, nên mọi lượt của Chimera — N ứng viên VÀ lượt
pha — đi qua ĐÚNG chính sách đó và được ĐẾM y như một lượt dịch thường. Một đường
gọi riêng cho Chimera là đường thứ hai để hai thứ đó trôi.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.chimera import (DEFAULT_LIMITS, ChimeraPlan, anchor_index,
                                candidate_metrics)
from app.domain.models import Segment
from app.domain.mt import MtOpts
from app.domain.mt_qa import QaLimits

#: Khoá của bản ghi Chimera, khai ra để `session()` và bài ghim đọc cùng một tên.
@dataclass
class ChimeraBatch:
    """Kết quả của MỘT lô: phần để ghi vào `translations.segments`, và bản ghi đầy đủ."""

    #: `None` = lô này KHÔNG có bản hợp nhất nào (mọi ứng viên đều hỏng).
    segments: list[Segment] | None
    missing: list[int]
    record: dict


def _prompt_version(engine) -> str:
    """`prompt_version` của engine, `"unknown"` khi nó không khai.

    Đọc từ CHÍNH engine chứ không từ một bảng trong `pipeline/`: `app/pipeline`
    không được biết `app/adapters` (`prompts.PROMPT_VERSION`), còn engine thì đã
    phơi sẵn giá trị đó — `OllamaMtEngine.prompt_version` và
    `OllamaMergeEngine.prompt_version`. Đây là cùng một giá trị, đọc ở đúng tầng.
    """
    return str(getattr(engine, "prompt_version", "unknown"))


def _blank_totals() -> dict:
    return {"calls": 0, "tokens_in": None, "tokens_out": None, "duration_ms": None}


def _add(totals: dict, add: dict) -> None:
    totals["calls"] += int(add.get("calls") or 0)
    for key in ("tokens_in", "tokens_out", "duration_ms"):
        value = add.get(key)
        if value is None:
            continue
        totals[key] = int(value) + (totals[key] or 0)


class ChimeraRunner:
    """Trạng thái tích luỹ của MỘT bản dịch chạy ở chế độ Chimera."""

    def __init__(self, plan: ChimeraPlan, *, merge_engine=None,
                 limits: QaLimits = DEFAULT_LIMITS,
                 created: dict | None = None) -> None:
        self.plan = plan
        self._merge_engine = merge_engine
        self._limits = limits
        #: Dict ĐÃ GHI LÚC TẠO HÀNG (`translations.chimera`), mang theo ƯỚC LƯỢNG
        #: CHI PHÍ đã hiện cho người dùng TRƯỚC khi họ bấm. Giữ nguyên nó trong bản
        #: ghi cuối là cách duy nhất để "đối chiếu trước/sau" so ĐÚNG con số đã
        #: hiện, chứ không phải một con số tính lại theo công thức mới.
        self._created = dict(created or {})
        self._entries = [self._blank(c) for c in plan.candidates]
        self._merge = {
            "engine": plan.merge_engine,
            **_blank_totals(),
            "fallback_segments": [],
            "fallback_reason": None,
            "anchor_by_segment": {},
            #: Đoạn mà lượt pha trả về CHUỖI Y HỆT mỏ neo. Đây là phép đo khiến
            #: cảnh báo chi phí trung thực: một lượt pha chép nguyên mỏ neo thì
            #: KHÔNG đổi lấy được gì, và người dùng phải thấy điều đó thay vì tin
            #: rằng lượt gọi thứ `N+1` nào cũng đang cải thiện bản dịch (ĐO ĐƯỢC
            #: trên máy này: `qwen2.5-3b` làm đúng như vậy cho cả sáu đoạn).
            "identical_segments": [],
        }
        self._anchor_counts: dict[str, int] = {}
        #: `{Segment.i: số CHUỖI KHÁC NHAU giữa các ứng viên ĐÃ CHẠY}`.
        #:
        #: Đây là phép đo trả lời thẳng câu hỏi mà §4.5 đặt ra ("một chế độ tốn gấp
        #: bảy lần phải biện minh cho chi phí của nó"): N ứng viên mà cho ra MỘT
        #: chuỗi thì lượt pha không có gì để pha. ĐO ĐƯỢC trên máy này: bốn ứng viên
        #: `qwen2.5-3b`/`qwen2.5-7b` ở ba mức nhiệt độ trả về CHUỖI Y HỆT bản gốc cho
        #: cả sáu đoạn — tức `1` — trong khi `opus-mt` cho một chuỗi khác ⇒ `2`.
        #: Không có con số này thì "chế độ đắt gấp N" là một lời khai không kiểm được.
        self._distinct: dict[int, int] = {}

    # ---------------------------------------------------------------- hình dạng
    @staticmethod
    def _blank(spec) -> dict:
        """Một hàng ứng viên RỖNG. Mọi khoá đều có mặt ngay từ đầu.

        Khoá chỉ xuất hiện SAU khi chạy là một hình dạng hai trạng thái cho cùng
        một đối tượng, và client phải nhớ cả hai. `available`/`reason` đến từ kế
        hoạch nên có ngay; `qa`/`cps_over`/`echo`/`segments` bắt đầu từ 0/[].
        """
        return {
            "id": spec.id,
            "engine": spec.engine,
            "label": spec.label,
            "temperature": spec.temperature,
            "quality_note": spec.quality_note,
            "available": spec.available,
            "reason": spec.reason,
            "ran": False,
            "skipped": None,
            "qa": 0,
            "cps_over": 0,
            "echo": 0,
            "segments": [],
            **_blank_totals(),
        }

    def session(self) -> dict:
        """Bản ghi ĐẦY ĐỦ tính tới lô vừa xong — thứ được ghi xuống DB."""
        base = {k: v for k, v in self._created.items() if k != "enabled"}
        return {
            **base,
            "enabled": True,
            "declared": self.plan.declared,
            "run_count": self.plan.run_count,
            "ran_count": sum(1 for e in self._entries if e["ran"]),
            "calls_per_batch": self.plan.calls_per_batch,
            "merge_engine": self.plan.merge_engine,
            #: `{id_ứng_viên: số đoạn nó làm mỏ neo}` — để §4.5 trả lời được
            #: "ứng viên nào thắng nhiều nhất", chứ không chỉ "lô này ai thắng".
            "anchors": dict(self._anchor_counts),
            "distinct_by_segment": {str(k): v for k, v in sorted(self._distinct.items())},
            "candidates": [dict(e) for e in self._entries],
            "merge": {**self._merge,
                      "fallback_segments": list(self._merge["fallback_segments"]),
                      "identical_segments": list(self._merge["identical_segments"]),
                      "anchor_by_segment": dict(self._merge["anchor_by_segment"])},
        }

    # ------------------------------------------------------------------ chạy lô
    def run_batch(self, *, run, engines: dict, batch: list[Segment], glossary,
                  opts: MtOpts, job, report, progress: float) -> ChimeraBatch:
        """Chạy N ứng viên trên `batch`, chọn mỏ neo, rồi gọi ĐÚNG MỘT lượt pha.

        `run` là `TranslateHandler._run_engine_batch` — xem docstring đầu tệp.
        """
        ran_ids: list[str] = []
        ran_segments: list[list[Segment]] = []
        metrics: list[dict] = []

        for entry, spec in zip(self._entries, self.plan.candidates):
            if not spec.available:
                entry["skipped"] = spec.reason
                continue
            engine = engines.get(spec.engine)
            if engine is None:
                entry["skipped"] = f"engine {spec.engine!r} chưa được dựng"
                continue
            # Nhiệt độ là cấu hình của TỪNG ứng viên, và nó phải đi vào CHÍNH lượt
            # gọi: ở một nhiệt độ cố định thì N ứng viên là N bản giống nhau.
            c_opts = MtOpts(source_lang=opts.source_lang, target_lang=opts.target_lang,
                            temperature=spec.temperature)
            out, missing, totals = run(engine, batch, glossary, c_opts,
                                       (spec.engine, _prompt_version(engine)),
                                       job, report, progress)
            _add(entry, totals)
            if out is None:
                # Ứng viên hỏng được GHI RA chứ không bị bỏ im: một lượt Chimera
                # tốn N+1 lời gọi, nên "ứng viên nào chết" là dữ liệu người dùng
                # phải thấy, không phải chi tiết nội bộ.
                entry["skipped"] = f"lô thất bại: thiếu segment {missing}"
                continue
            entry["ran"] = True
            entry["segments"].extend({"i": s.i, "text": s.text} for s in out)
            m = candidate_metrics(batch, out, glossary=glossary,
                                  supports_glossary=engine.supports_glossary(),
                                  limits=self._limits, target_lang=opts.target_lang)
            for key, value in m.items():
                entry[key] = entry[key] + value
            ran_ids.append(spec.id)
            ran_segments.append(out)
            metrics.append(m)

        if not metrics:
            return ChimeraBatch(segments=None, missing=[s.i for s in batch],
                                record=self.session())

        # Đo ĐỘ ĐA DẠNG trước khi chọn mỏ neo: đếm số chuỗi KHÁC NHAU mà các ứng
        # viên đã chạy trả về cho từng đoạn.
        for s in batch:
            seen: set[str] = set()
            for segs in ran_segments:
                for x in segs:
                    if x.i == s.i:
                        seen.add(x.text)
            self._distinct[s.i] = len(seen)

        anchor_at = anchor_index(metrics)
        anchor_id = ran_ids[anchor_at]
        anchor_out = ran_segments[anchor_at]
        # `hyp` của §4.5 là chỉ số 1-BASED của mỏ neo trong danh sách ĐÃ KHAI —
        # không phải trong danh sách chạy được. Đọc theo danh sách chạy được thì
        # cùng một ứng viên mang hai số khác nhau giữa hai máy, và "hyp 3" không còn
        # trỏ tới một hàng nào xác định trong kế hoạch.
        declared_index = next(i for i, c in enumerate(self.plan.candidates)
                              if c.id == anchor_id) + 1
        self._anchor_counts[anchor_id] = self._anchor_counts.get(anchor_id, 0) + len(batch)
        for s in batch:
            self._merge["anchor_by_segment"][str(s.i)] = declared_index

        merged = None
        reason = None
        if self._merge_engine is None:
            reason = (f"không dựng được engine pha {self.plan.merge_engine!r} "
                      f"(engine chưa sẵn sàng, hoặc không phải engine Ollama)")
        else:
            candidates = tuple(zip(ran_ids, (tuple(segs) for segs in ran_segments)))
            m_opts = MtOpts(source_lang=opts.source_lang, target_lang=opts.target_lang,
                            merge_candidates=candidates, merge_anchor=anchor_id)
            out, missing, totals = run(self._merge_engine, batch, glossary, m_opts,
                                       (self.plan.merge_engine,
                                        _prompt_version(self._merge_engine)),
                                       job, report, progress)
            _add(self._merge, totals)
            if out is None:
                reason = f"lượt pha thất bại: thiếu segment {missing}"
            else:
                merged = out
                # Chỉ tính khi lượt pha THẬT SỰ chạy: nhánh LÙI VỀ mỏ neo cũng cho
                # chữ y hệt, và tính nó ở đó sẽ trộn "không cải thiện" với "đã hỏng"
                # — hai chuyện khác nhau, và `fallback_segments` đã nói vế thứ hai.
                anchor_text = {s.i: s.text for s in anchor_out}
                self._merge["identical_segments"].extend(
                    s.i for s in out if anchor_text.get(s.i) == s.text)

        if merged is None:
            # LÙI VỀ MỎ NEO, và NÓI RA. Đây là vế khiến "bản hợp nhất" không bao giờ
            # là một lời nói dối: khi lượt pha hỏng, thứ được ghi là bản của MỘT ứng
            # viên đã biết tên, kèm danh sách đoạn đã lùi và lý do.
            merged = anchor_out
            self._merge["fallback_segments"].extend(s.i for s in batch)
            if self._merge["fallback_reason"] is None:
                self._merge["fallback_reason"] = reason

        return ChimeraBatch(segments=merged, missing=[], record=self.session())
