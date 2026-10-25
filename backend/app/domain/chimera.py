"""Luật của chế độ CHIMERA — spec kiến trúc §8.7.5, và spec UI §4.5.

CHIMERA = N ỨNG VIÊN + MỘT LƯỢT PHA. Tệp này là phần THUẦN của chế độ đó: nó
không gọi engine, không đọc DB, không biết HTTP — nhờ vậy mọi luật ở đây ghim được
bằng test không cần model nào.

⚠️ BA CHỖ SPEC KHÔNG NÓI, VÀ BA QUYẾT ĐỊNH Ở ĐÂY (khai ra, không giấu):

* **Sáu ứng viên KHÁC NHAU ở đâu.** `2026-09-25-phu-de-lab-design.md:584` chỉ nói
  *"Sinh 6 ứng viên mỗi lô → gọi lượt thứ 7 để pha"*; nó KHÔNG nói sáu bản đó khác
  nhau ở chỗ nào. Đọc theo nghĩa hẹp nhất — sáu lời gọi cùng một model ở
  `temperature=0.1` cố định của `ollama_mt.py` — thì sáu bản gần như giống hệt
  nhau, và một lượt "pha" trên sáu bản giống nhau là một lượt gọi vô nghĩa: tính
  năng sẽ chạy được, tốn gấp bảy, và không đổi lấy được gì. QUYẾT ĐỊNH: một ứng
  viên là một cặp `(engine, temperature)`, và DANH SÁCH ứng viên là DỮ LIỆU khai
  trong `registry.json` (`chimera.candidates`) — không hard-code ở đây, đúng luật
  "thêm model mới = sửa registry.json" của tệp đó.
* **Luật hợp nhất.** Cùng dòng đó chỉ nói *"gọi lượt thứ 7 để pha"*. QUYẾT ĐỊNH:
  một MỎ NEO tất định (`anchor_index`) + MỘT lời gọi model THẬT để pha
  (`adapters/mt/chimera_merge.py`). Mỏ neo được trao cho lượt pha làm bản tham
  chiếu, và nếu lượt pha hỏng thì bản hợp nhất LÙI VỀ MỎ NEO kèm cờ `fallback` —
  "lấy cái đầu tiên" không bao giờ là một đường im lặng.
* **Số ứng viên CHẠY ĐƯỢC.** `2026-09-25-phu-de-lab-ui-design.md:242` vẽ nhãn
  `HỢP NHẤT TỪ 6 ỨNG VIÊN`. Sáu ứng viên KHAI BÁO không phải sáu ứng viên CHẠY
  ĐƯỢC: trên máy này chỉ một model Ollama đã được pull. QUYẾT ĐỊNH: `run_count` là
  số THẬT SỰ chạy, giao diện hiện con số thật, và ứng viên không chạy được vẫn
  được HIỆN kèm lý do (`reason`) — đúng luật "hiện đúng số chạy được và nói rõ cái
  thiếu", thay vì hứa sáu rồi lặng lẽ chạy bốn.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from app.domain.models import Segment, Term
from app.domain.mt_qa import QaLimits, cps_row, qa_translation

#: Nhiệt độ ĐỌC ĐƯỢC của một ứng viên không khai `temperature`. Khớp
#: `_TEMPERATURE` của `adapters/mt/ollama_mt.py` — chỗ ÁP DỤNG vẫn là adapter;
#: hằng ở đây chỉ để mô tả được một ứng viên thiếu trường đó.
DEFAULT_TEMPERATURE = 0.1

#: Ngưỡng CPS + tỉ lệ độ dài dùng để chấm ứng viên. CÙNG `QaLimits` mà
#: `TranslateHandler` dùng cho QA cuối — hai ngưỡng khác nhau cho cùng một bản
#: dịch là hai câu trả lời cho cùng một câu hỏi.
DEFAULT_LIMITS = QaLimits()


@dataclass(frozen=True)
class CandidateSpec:
    """Một ứng viên ĐÃ KHAI trong `registry.json` — dữ liệu, không phải hành vi."""

    id: str
    engine: str
    label: str
    temperature: float | None = None
    #: Cảnh báo CHẤT LƯỢNG đi kèm ứng viên này, nếu có. Là DỮ LIỆU (đọc từ
    #: registry), không phải câu chữ dựng trong mã: nó là một phép đo đã ghi lại,
    #: và nó phải sửa được mà không phải sửa mã.
    quality_note: str | None = None
    #: `True` = engine của ứng viên này phục vụ được job NGAY BÂY GIỜ.
    available: bool = False
    #: Lý do KHÔNG chạy được, bằng chữ. `None` khi `available` là `True`.
    reason: str | None = None


@dataclass(frozen=True)
class ChimeraPlan:
    """Kế hoạch Chimera: N ứng viên + ĐÚNG MỘT engine pha."""

    candidates: tuple[CandidateSpec, ...]
    merge_engine: str

    @property
    def declared(self) -> int:
        return len(self.candidates)

    @property
    def runnable(self) -> tuple[CandidateSpec, ...]:
        return tuple(c for c in self.candidates if c.available)

    @property
    def run_count(self) -> int:
        return len(self.runnable)

    @property
    def calls_per_batch(self) -> int:
        """Số lượt CHẠM ENGINE cho một lô: N ứng viên + ĐÚNG MỘT lượt pha.

        Con số này là HỆ SỐ CHI PHÍ mà §8.7.5 ("chậm ~7×") và spec UI §4.5
        ("7 lượt gọi model cho mỗi lô") nói tới. Nó được TÍNH chứ không được chép:
        máy chạy được bốn ứng viên thì hệ số là năm, không phải bảy.
        """
        return self.run_count + 1


def plan_from_raw(raw: object, *, mt_ids: set[str]) -> ChimeraPlan:
    """Dựng `ChimeraPlan` từ khối `chimera` của `registry.json`.

    Mọi lỗi ở đây là lỗi CẤU HÌNH và phải nổ NGAY lúc dựng tiến trình, kèm đúng id
    sai và chỗ cần sửa — cùng bài học I-3 của `default_mt_engine`: một id gõ sai
    chỉ lộ ra thành job chết ở tận worker sau khi hàng `translations` đã được ghi.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"khối `chimera` của registry phải là object, nhận {type(raw).__name__}")

    merge_engine = raw.get("merge_engine")
    if not isinstance(merge_engine, str) or merge_engine not in mt_ids:
        raise ValueError(
            f"`chimera.merge_engine` {merge_engine!r} không có trong registry; "
            f"các engine mt đang có: {sorted(mt_ids)}. Sửa khoá `merge_engine` "
            f"trong registry.json cho khớp."
        )

    entries = raw.get("candidates")
    if not isinstance(entries, list) or not entries:
        raise ValueError("`chimera.candidates` phải là mảng KHÔNG rỗng")

    out: list[CandidateSpec] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"mục `chimera.candidates` phải là object, nhận {entry!r}")
        cid = entry.get("id")
        engine = entry.get("engine")
        if not isinstance(cid, str) or not cid:
            raise ValueError(f"ứng viên thiếu `id`: {entry!r}")
        if cid in seen:
            raise ValueError(f"`id` ứng viên trùng: {cid!r}")
        if not isinstance(engine, str) or engine not in mt_ids:
            raise ValueError(
                f"ứng viên {cid!r} trỏ tới engine {engine!r} không có trong registry; "
                f"các engine mt đang có: {sorted(mt_ids)}."
            )
        temperature = entry.get("temperature")
        if temperature is not None and not isinstance(temperature, (int, float)):
            raise ValueError(
                f"`temperature` của ứng viên {cid!r} phải là số, nhận {temperature!r}")
        note = entry.get("quality_note")
        seen.add(cid)
        out.append(CandidateSpec(
            id=cid,
            engine=engine,
            label=str(entry.get("label") or cid),
            temperature=None if temperature is None else float(temperature),
            quality_note=str(note) if isinstance(note, str) and note else None,
        ))
    return ChimeraPlan(candidates=tuple(out), merge_engine=merge_engine)


def mark_availability(plan: ChimeraPlan, available_engines: set[str]) -> ChimeraPlan:
    """Ghi cờ chạy được cho TỪNG ứng viên theo cờ của ENGINE nó.

    Nguồn sự thật là `spec.capabilities["available"]` mà `main._mark_availability`
    đã tính một lần cho mọi engine dịch — KHÔNG dò lại Ollama ở đây. Hai phép dò
    riêng cho cùng một câu hỏi ("engine này chạy được ngay bây giờ không") là hai
    câu trả lời có thể lệch nhau, và câu trả lời lệch ở đây nghĩa là giao diện hứa
    một ứng viên rồi job chết ở worker.
    """
    marked = tuple(
        replace(
            c,
            available=c.engine in available_engines,
            reason=None if c.engine in available_engines else (
                f"engine {c.engine!r} chưa sẵn sàng: model chưa được pull, "
                f"hoặc runtime không phục vụ được"),
        )
        for c in plan.candidates
    )
    return ChimeraPlan(candidates=marked, merge_engine=plan.merge_engine)


def candidate_json(spec: CandidateSpec) -> dict:
    """Hình dạng JSON của MỘT ứng viên ở phần KẾ HOẠCH (trước khi chạy)."""
    return {
        "id": spec.id,
        "engine": spec.engine,
        "label": spec.label,
        "temperature": spec.temperature,
        "quality_note": spec.quality_note,
        "available": spec.available,
        "reason": spec.reason,
    }


def echo_count(source: list[Segment], out: list[Segment]) -> int:
    """Số đoạn DỊCH GIỐNG HỆT bản nguồn (sau khi cắt khoảng trắng).

    Đây là phép đo trực tiếp của thất bại đã đo được trên máy này: `qwen2.5-3b` ở
    prompt `p1` chép nguyên chữ Hán 43/44 đoạn. `qa_translation` BẮT được ca đó qua
    cờ `lang:`, nhưng cờ đó là một phép suy đoán theo bộ ký tự; phép so NGUYÊN VĂN
    ở đây là bằng chứng, và nó là thứ khiến "cảnh báo chất lượng" đi kèm cảnh báo
    chi phí trở thành một SỐ ĐO chứ không phải một câu chữ.
    """
    by_id = {t.i: t for t in out}
    hits = 0
    for s in source:
        t = by_id.get(s.i)
        if t is None:
            continue
        raw = s.text.strip()
        if raw and raw == t.text.strip():
            hits += 1
    return hits


def candidate_metrics(source: list[Segment], out: list[Segment], *,
                      glossary: list[Term], supports_glossary: bool,
                      limits: QaLimits = DEFAULT_LIMITS,
                      target_lang: str = "vi") -> dict:
    """Ba con số dùng để xếp hạng một ứng viên — TẤT CẢ tính từ dữ liệu thật.

    Không có điểm số do model tự chấm: ba phép đo này đều tất định và chạy lại
    được. `qa` dùng ĐÚNG `qa_translation` của tầng QA (spec §8.8 tầng 1), nên một
    ứng viên có ít cờ QA hơn cũng là ứng viên mà tầng QA cuối sẽ ít phàn nàn hơn.
    """
    issues = qa_translation(source, out, glossary=glossary,
                            supports_glossary=supports_glossary, limits=limits,
                            target_lang=target_lang)
    by_id = {t.i: t for t in out}
    over = 0
    for s in source:
        t = by_id.get(s.i)
        if t is not None and cps_row(s, t, limits=limits).over:
            over += 1
    return {"qa": len(issues), "cps_over": over, "echo": echo_count(source, out)}


#: Thứ tự so sánh, KHAI RA thành dữ liệu để nó đọc được từ ngoài và để bài ghim
#: biết chính xác nó đang ghim cái gì.
ANCHOR_ORDER = ("qa", "cps_over", "echo")


def anchor_index(metrics: list[dict]) -> int:
    """Chỉ số (0-based) của ứng viên MỎ NEO trong `metrics`.

    LUẬT, theo đúng thứ tự này:

    1. ít cờ QA nhất (§8.8 tầng 1 — số/ngày, tên riêng, thuật ngữ, độ dài, rỗng,
       và cờ ngôn ngữ đầu ra);
    2. ít đoạn VƯỢT NGƯỠNG ĐỌC nhất (§4.3 — lỗi phụ đề phổ biến nhất của Việt ngữ);
    3. ít đoạn NHẠI LẠI NGUỒN nhất (`echo_count` — thất bại đã đo được của engine
       nhỏ trên máy này);
    4. vẫn hoà thì lấy ứng viên ĐỨNG TRƯỚC trong danh sách ĐÃ KHAI.

    Vế 4 là chỗ dễ trôi nhất, nên nó được nói ra: một luật "hoà thì lấy cái đầu"
    mà không nói là đúng thứ luật này tồn tại để chặn. `i` nằm TRONG khoá so sánh
    nên thứ tự là TẤT ĐỊNH — `min` của Python giữ phần tử đầu khi bằng nhau, nhưng
    dựa vào chi tiết cài đặt đó là để luật nằm ngoài tầm ghim.
    """
    if not metrics:
        raise ValueError("không có ứng viên nào để chọn mỏ neo")

    def key(i: int) -> tuple:
        m = metrics[i]
        return tuple(int(m.get(name, 0)) for name in ANCHOR_ORDER) + (i,)

    return min(range(len(metrics)), key=key)


@dataclass(frozen=True)
class Baseline:
    """Chi phí THẬT của MỘT lượt dịch một-engine trên CHÍNH kênh này.

    Đây là cơ sở của cảnh báo chi phí, và nó là số ĐO ĐƯỢC: một hàng `translations`
    đã `done` của cùng transcript, với `duration_ms`/`tokens_*` mà chính
    `TranslateHandler` đã cộng từ `llm_calls`. Không có hàng nào như vậy thì
    `duration_ms is None` và cảnh báo NÓI RA là chưa đo được — nó không bịa một
    con số từ số đoạn.
    """

    translation_id: int | None
    engine: str
    segments: int
    duration_ms: int | None
    tokens_in: int | None
    tokens_out: int | None

    def to_json(self) -> dict:
        return {
            "translation_id": self.translation_id,
            "engine": self.engine,
            "segments": self.segments,
            "duration_ms": self.duration_ms,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


def _scale(value: int | None, factor: float) -> int | None:
    return None if value is None else int(round(value * factor))


def estimate_cost(baseline: Baseline | None, *, segments: int, calls: int) -> dict | None:
    """Ước lượng chi phí của cả lượt Chimera, SUY TỈ LỆ từ `baseline`.

    Trả `None` khi CHƯA ĐO ĐƯỢC (chưa có bản dịch nào chạy xong trên kênh này, hoặc
    hàng đó không có `duration_ms`). `None` KHÁC `0`: "chưa đo được" và "nhanh bằng
    không" là hai chuyện, và cảnh báo chi phí phải nói được cái thứ nhất.
    """
    if baseline is None or baseline.duration_ms is None:
        return None
    if baseline.segments <= 0 or segments <= 0 or calls <= 0:
        return None
    factor = segments * calls / baseline.segments
    return {
        "calls_per_batch": calls,
        "duration_ms": _scale(baseline.duration_ms, factor),
        "tokens_in": _scale(baseline.tokens_in, factor),
        "tokens_out": _scale(baseline.tokens_out, factor),
    }


def cost_json(plan: ChimeraPlan, *, segments: int, baseline: Baseline | None) -> dict:
    """Cảnh báo chi phí HIỆN TRƯỚC khi người dùng bấm (§4.5, §9.2).

    `estimate is None` là một câu trả lời HỢP LỆ và nó đi kèm `estimate_basis` nói
    vì sao chưa đo được. Bịa một con số ở đây là làm hỏng đúng thứ dòng 423 của
    spec UI đòi: một cảnh báo chi phí không đo được thì không cảnh báo được gì.
    """
    calls = plan.calls_per_batch
    estimate = estimate_cost(baseline, segments=segments, calls=calls)
    if estimate is None:
        basis = ("chưa đo được: chưa có bản dịch nào của kênh này chạy xong kèm "
                 "thời gian THẬT, nên chưa có gì để suy tỉ lệ")
        # Vì sao cần một câu RIÊNG cho "làm gì bây giờ": đo được trên máy này —
        # engine chạy trong tiến trình (OPUS-MT) không trả token/thời gian, nên một
        # kênh chỉ từng dịch bằng OPUS-MT sẽ mãi mãi thấy "chưa đo được". Một cảnh
        # báo chi phí không nói được cách thoát khỏi tình trạng đó là một cảnh báo
        # người dùng sẽ học cách bỏ qua.
        hint = ("engine chạy trong tiến trình (OPUS-MT) không trả token/thời gian. "
                "Chạy xong MỘT bản dịch bằng một engine Ollama rồi đọc lại cảnh báo "
                "này để có số đo thật.")
    else:
        basis = (f"đo từ bản dịch #{baseline.translation_id} ({baseline.engine}): "
                 f"{baseline.duration_ms} ms / {baseline.segments} đoạn")
        hint = None
    return {
        "segments": segments,
        "declared": plan.declared,
        "runnable": plan.run_count,
        "calls_per_batch": calls,
        "multiplier": calls,
        "merge_engine": plan.merge_engine,
        "candidates": [candidate_json(c) for c in plan.candidates],
        "baseline": None if baseline is None else baseline.to_json(),
        "estimate": estimate,
        "estimate_basis": basis,
        "estimate_hint": hint,
    }
