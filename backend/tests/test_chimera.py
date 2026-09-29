"""Chế độ CHIMERA — spec kiến trúc §8.7.5, spec UI §4.5.

Ba vế của dòng 423 trong spec UI, và mỗi vế có bài ghim riêng ở đây:

* **6 ứng viên** — `test_shipped_registry_declares_six_chimera_candidates` ghim
  ĐÚNG danh sách đã ship, và
  `test_calls_per_batch_is_the_spec_seven_when_all_six_run` ghim hệ số `~7×` của
  §8.7.5 khi máy chạy được cả sáu.
* **MỘT bản hợp nhất, có LUẬT** — `test_anchor_*` ghim thứ tự so sánh, và
  `test_merge_falls_back_to_the_anchor_and_says_so` ghim vế dễ nói dối nhất: lượt
  pha hỏng thì bản hợp nhất là bản của MỘT ứng viên có tên, và điều đó được GHI RA.
* **Cảnh báo chi phí ĐO ĐƯỢC** — `test_estimate_*` và hai bài route
  `/api/chimera/cost`.

Vì sao phần lớn bài ở đây chạy KHÔNG cần model: luật của chế độ này (chọn mỏ neo,
nhân hệ số chi phí, đếm đoạn nhại lại) là logic thuần, và nó phải ghim được trên
mọi máy. Phần chạm engine thật nằm ở `test_mt_live.py` (đánh dấu `live`).
"""
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.adapters.registry_file import load_registry
from app.api.app import create_app
from app.domain.chimera import (DEFAULT_TEMPERATURE, Baseline, CandidateSpec,
                                ChimeraPlan, anchor_index, candidate_json,
                                candidate_metrics, cost_json, echo_count,
                                estimate_cost, mark_availability, plan_from_raw)
from app.domain.models import CallStats, Segment
from app.domain.mt import MtOpts
from app.pipeline.chimera import ChimeraRunner
from app.pipeline.translate import TranslateHandler
from app.registry import EngineSpec, of_kind
from tests.fakes_mt import FakeMtEngine


# ---------------------------------------------------------------------------
# Dựng cảnh
# ---------------------------------------------------------------------------

def seg(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i), end=float(i) + 1, text=text)


def _sources(n: int = 4) -> list[Segment]:
    """Đoạn nguồn TIẾNG TRUNG — đúng dữ liệu thật của sản phẩm.

    Cố ý không dùng chữ Latinh: phép kiểm ngôn ngữ đầu ra của `mt_qa` chỉ bắt được
    ca "bản dịch còn nguyên chữ Hán", nên một cảnh bằng chữ Latinh sẽ làm
    `test_the_echoing_candidate_loses_the_anchor...` xanh vì LÝ DO SAI.
    """
    return [seg(i, f"第{i}句中文") for i in range(1, n + 1)]


def _plan(candidates, merge_engine="bo-pha") -> ChimeraPlan:
    return ChimeraPlan(candidates=tuple(candidates), merge_engine=merge_engine)


def _cand(cid, engine, *, available=True, reason=None, temperature=None):
    return CandidateSpec(id=cid, engine=engine, label=cid.upper(),
                         temperature=temperature, available=available, reason=reason)


def _spec(engine_id, *, available=True) -> EngineSpec:
    return EngineSpec(id=engine_id, label=engine_id, kind="mt", runtime="inprocess",
                      model_ref=engine_id, vram_mb=0, langs=("zh",),
                      capabilities={"available": available,
                                    "prompt_version": "qwen-json-p2",
                                    "chimera_prompt_version": "chimera-merge-p1"})


@pytest.fixture
def repos(tmp_path):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return r


# ---------------------------------------------------------------------------
# (1) SÁU ỨNG VIÊN — dữ liệu của registry
# ---------------------------------------------------------------------------

def test_shipped_registry_declares_six_chimera_candidates():
    """SÁU ứng viên của §8.7.5 là DỮ LIỆU đã ship, và bài này ghim đúng nó.

    Con số SÁU nằm ở đây chứ không nằm trong mã: nếu một ngày registry khai bảy
    ứng viên thì bài này đỏ và người sửa phải ĐỌC LẠI §8.7.5 — đó là điều nó tồn
    tại để làm, chứ không phải để cấm thay đổi.
    """
    raw = json.loads((pathlib.Path(__file__).resolve().parents[1]
                      / "registry.json").read_text(encoding="utf-8"))
    block = raw["chimera"]
    assert len(block["candidates"]) == 6, (
        "spec kiến trúc §8.7.5 nói SÁU ứng viên; registry khai "
        f"{len(block['candidates'])}"
    )
    mt_ids = {s.id for s in of_kind(load_registry(), "mt")}
    for entry in block["candidates"]:
        assert entry["engine"] in mt_ids, (
            f"ứng viên {entry['id']!r} trỏ tới engine {entry['engine']!r} không có "
            f"trong mảng `mt`: {sorted(mt_ids)}"
        )
    assert block["merge_engine"] in mt_ids


def test_the_engines_missing_a_prompt_version_are_the_ones_already_declared():
    """`llm_calls.prompt_version` phải CÓ NGHĨA, và chỗ còn thiếu phải là chỗ ĐÃ KHAI.

    `PROMPT_VERSION` hôm nay phủ ba trong bốn engine dịch. Engine còn thiếu là
    `hy-mt-1.5-7b` — model CHƯA được pull ở máy này, nên nhánh đó chưa từng chạy và
    một chuỗi `prompt_version` cho nó sẽ là một lời khai không có phép đo nào đứng
    sau. Bài này biến khoảng trống đó thành DỮ LIỆU: thêm một engine mới vào
    `chimera.candidates` mà quên `prompt_version` thì nó đỏ, và người sửa phải chọn
    — khai một version thật, hay khai thêm vào danh sách "đã biết là thiếu".
    """
    from app.adapters.mt.prompts import MERGE_PROMPT_VERSION, PROMPT_VERSION

    raw = json.loads((pathlib.Path(__file__).resolve().parents[1]
                      / "registry.json").read_text(encoding="utf-8"))
    used = {entry["engine"] for entry in raw["chimera"]["candidates"]}
    missing = sorted(used - set(PROMPT_VERSION))
    assert missing == ["hy-mt-1.5-7b"], (
        "danh sách engine CHƯA có `prompt_version` đã đổi. Hôm nay đúng một engine "
        "— HY-MT1.5, model chưa được pull trên máy này. Thiếu: "
        f"{missing}"
    )
    assert MERGE_PROMPT_VERSION not in set(PROMPT_VERSION.values()), (
        "prompt của LƯỢT PHA phải KHÁC prompt dịch: dùng chung một chuỗi thì không "
        "phân biệt được một lượt pha với một lượt dịch thường"
    )


def test_plan_from_raw_rejects_an_engine_outside_the_registry():
    with pytest.raises(ValueError, match="không có trong registry"):
        plan_from_raw({"merge_engine": "a", "candidates": [
            {"id": "c1", "engine": "khong-co"}]}, mt_ids={"a"})


def test_plan_from_raw_rejects_a_duplicate_candidate_id():
    with pytest.raises(ValueError, match="trùng"):
        plan_from_raw({"merge_engine": "a", "candidates": [
            {"id": "c1", "engine": "a"}, {"id": "c1", "engine": "a"}]}, mt_ids={"a"})


def test_plan_from_raw_rejects_a_temperature_that_is_not_a_number():
    with pytest.raises(ValueError, match="temperature"):
        plan_from_raw({"merge_engine": "a", "candidates": [
            {"id": "c1", "engine": "a", "temperature": "nóng"}]}, mt_ids={"a"})


def test_plan_from_raw_rejects_a_merge_engine_outside_the_registry():
    with pytest.raises(ValueError, match="merge_engine"):
        plan_from_raw({"merge_engine": "z", "candidates": [
            {"id": "c1", "engine": "a"}]}, mt_ids={"a"})


def test_a_candidate_without_a_temperature_keeps_it_unset():
    """`temperature` vắng là `None`, KHÔNG phải `0,1` được đóng dấu vào dữ liệu.

    Hai thứ khác nhau: `None` nghĩa là "adapter tự quyết" (`_TEMPERATURE`), còn một
    con số ở đây nghĩa là "ứng viên này ĐÃ KHAI". Đóng dấu mặc định vào dữ liệu là
    biến một cấu hình thành hai bản sao của cùng một hằng số, và bản sao sẽ trôi.
    """
    plan = plan_from_raw({"merge_engine": "a", "candidates": [
        {"id": "c1", "engine": "a"}]}, mt_ids={"a"})
    assert plan.candidates[0].temperature is None
    assert DEFAULT_TEMPERATURE == 0.1, (
        "hằng đọc-được này phải khớp `_TEMPERATURE` của `ollama_mt.py`"
    )


# ---------------------------------------------------------------------------
# Chỉ số chạy được — "hiện đúng số chạy được và nói rõ cái thiếu"
# ---------------------------------------------------------------------------

def test_mark_availability_reuses_the_engine_flag_and_names_the_reason():
    plan = _plan([_cand("c1", "a"), _cand("c2", "b"), _cand("c3", "c")])
    marked = mark_availability(plan, {"a", "c"})
    flags = {c.id: (c.available, c.reason) for c in marked.candidates}
    assert flags["c1"][0] is True and flags["c1"][1] is None
    assert flags["c2"][0] is False and "chưa sẵn sàng" in flags["c2"][1]
    assert flags["c3"][0] is True
    assert marked.run_count == 2
    assert marked.declared == 3


def test_calls_per_batch_is_the_spec_seven_when_all_six_run():
    """SÁU ứng viên + MỘT lượt pha = **bảy** lượt chạm engine — con số của §8.7.5.

    Đây là hệ số `~7×` mà §9.2 và §4.5 nói tới. Nó được TÍNH từ số ứng viên chạy
    được, nên trên một máy thiếu model nó nhỏ hơn — và đó là điều đúng: cảnh báo
    chi phí phải nói về lượt chạy SẮP tới, không phải về một máy đủ model.
    """
    plan = _plan([_cand(f"c{i}", f"e{i}") for i in range(6)], merge_engine="e0")
    assert plan.calls_per_batch == 7


def test_calls_per_batch_drops_with_the_number_of_runnable_candidates():
    plan = mark_availability(
        _plan([_cand("c1", "a"), _cand("c2", "b"), _cand("c3", "c")],
              merge_engine="a"), {"a"})
    assert plan.declared == 3
    assert plan.run_count == 1
    assert plan.calls_per_batch == 2


# ---------------------------------------------------------------------------
# ĐOẠN NHẠI LẠI NGUỒN — phép đo của thất bại đã biết của engine nhỏ
# ---------------------------------------------------------------------------

def test_echo_count_counts_exact_copies_of_the_source():
    src = [seg(1, "第一句"), seg(2, "第二句"), seg(3, "第三句")]
    out = [seg(1, "第一句"), seg(2, "Câu hai"), seg(3, "第三句")]
    assert echo_count(src, out) == 2


def test_echo_count_ignores_surrounding_whitespace_but_not_a_real_translation():
    src = [seg(1, "第一句"), seg(2, "第二句")]
    out = [seg(1, "  第一句 "), seg(2, "Câu thứ hai")]
    assert echo_count(src, out) == 1


def test_echo_count_ignores_an_empty_source_segment():
    """Đoạn nguồn RỖNG không được tính là "nhại lại".

    Một đoạn nguồn rỗng mà bản dịch cũng rỗng là chuyện của dữ liệu nguồn, không
    phải của engine. Đếm nó là thổi phồng cảnh báo chất lượng bằng một dòng không
    có chữ nào để nhại.
    """
    assert echo_count([seg(1, "   ")], [seg(1, "")]) == 0


# ---------------------------------------------------------------------------
# LUẬT HỢP NHẤT — mỏ neo
# ---------------------------------------------------------------------------

def test_anchor_is_the_candidate_with_the_fewest_qa_flags():
    metrics = [{"qa": 3, "cps_over": 0, "echo": 0},
               {"qa": 1, "cps_over": 9, "echo": 4},
               {"qa": 5, "cps_over": 0, "echo": 0}]
    assert anchor_index(metrics) == 1


def test_anchor_breaks_ties_in_the_declared_order_qa_then_cps_then_echo():
    """BỐN vế, và thứ tự của chúng là hợp đồng — không phải chi tiết cài đặt.

    `min` của Python tình cờ giữ phần tử đầu khi bằng nhau; dựa vào chi tiết đó là
    để luật nằm ngoài tầm ghim. Bài này đi qua từng vế: (a) QA thắng CPS, (b) CPS
    thắng echo, (c) echo thắng thứ tự, (d) hoà cả ba thì lấy ứng viên ĐỨNG TRƯỚC.
    """
    qa_wins = [{"qa": 0, "cps_over": 9, "echo": 9},
               {"qa": 1, "cps_over": 0, "echo": 0}]
    assert anchor_index(qa_wins) == 0, "QA là vế ĐẦU"

    cps_wins = [{"qa": 0, "cps_over": 2, "echo": 0},
                {"qa": 0, "cps_over": 1, "echo": 7}]
    assert anchor_index(cps_wins) == 1, "CPS là vế THỨ HAI"

    echo_wins = [{"qa": 0, "cps_over": 0, "echo": 4},
                 {"qa": 0, "cps_over": 0, "echo": 1}]
    assert anchor_index(echo_wins) == 1, "echo là vế THỨ BA"

    all_tied = [{"qa": 0, "cps_over": 0, "echo": 0},
                {"qa": 0, "cps_over": 0, "echo": 0}]
    assert anchor_index(all_tied) == 0, "hoà cả ba thì lấy ứng viên ĐỨNG TRƯỚC"


def test_anchor_index_refuses_an_empty_field():
    with pytest.raises(ValueError, match="mỏ neo"):
        anchor_index([])


def test_metrics_flag_an_echoing_candidate_worse_than_a_translating_one():
    """Hai ứng viên THẬT: một bản nhại nguồn, một bản dịch — ứng viên dịch thắng.

    Đây là vế khiến "cảnh báo chất lượng" không chỉ là câu chữ: `qwen2.5-3b` ở
    prompt `p1` CHÉP nguyên chữ Hán 43/44 đoạn, và một chế độ gọi nó sáu lần rồi
    "pha" sáu bản chữ Hán là một chế độ vô dụng. `candidate_metrics` đo được điều
    đó, và `anchor_index` không bao giờ chọn bản nhại khi có bản dịch.
    """
    src = _sources(4)
    echo = list(src)
    good = [seg(s.i, f"Câu {s.i} đã dịch") for s in src]
    m_echo = candidate_metrics(src, echo, glossary=[], supports_glossary=True)
    m_good = candidate_metrics(src, good, glossary=[], supports_glossary=True)
    assert m_echo["echo"] == 4 and m_good["echo"] == 0
    assert m_echo["qa"] > m_good["qa"], (
        "chữ Hán CÒN NGUYÊN trong bản dịch phải bị `qa_translation` gắn cờ `lang:` "
        f"— echo {m_echo['qa']} cờ, bản dịch {m_good['qa']} cờ"
    )
    assert anchor_index([m_echo, m_good]) == 1


# ---------------------------------------------------------------------------
# CẢNH BÁO CHI PHÍ — đo được, và nói ra khi chưa đo được
# ---------------------------------------------------------------------------

def _baseline(**kw) -> Baseline:
    base = dict(translation_id=7, engine="fake-mt", segments=4,
                duration_ms=8000, tokens_in=400, tokens_out=800)
    base.update(kw)
    return Baseline(**base)


def test_estimate_scales_with_the_segment_count_and_the_call_count():
    est = estimate_cost(_baseline(), segments=8, calls=5)
    assert est == {"calls_per_batch": 5, "duration_ms": 80000,
                   "tokens_in": 4000, "tokens_out": 8000}


def test_estimate_is_none_when_there_is_no_measured_baseline():
    """`None` KHÁC `0`: "chưa đo được" và "nhanh bằng không" là hai chuyện."""
    assert estimate_cost(None, segments=8, calls=5) is None
    assert estimate_cost(_baseline(duration_ms=None), segments=8, calls=5) is None


def test_cost_json_says_why_the_estimate_is_missing():
    plan = mark_availability(_plan([_cand("c1", "a"), _cand("c2", "b")]), {"a"})
    body = cost_json(plan, segments=10, baseline=None)
    assert body["estimate"] is None
    assert "chưa đo được" in body["estimate_basis"]
    assert body["declared"] == 2 and body["runnable"] == 1
    assert body["calls_per_batch"] == 2 and body["multiplier"] == 2


def test_cost_json_names_every_declared_candidate_including_the_ones_that_cannot_run():
    """Ứng viên KHÔNG chạy được vẫn phải có mặt, kèm lý do.

    Đây là vế "nói rõ cái thiếu": giấu nó đi thì giao diện hứa sáu ứng viên và chỉ
    chạy được bốn, mà không câu nào nói vì sao.
    """
    plan = _plan([_cand("c1", "a"),
                  _cand("c2", "b", available=False, reason="model chưa pull")])
    body = cost_json(plan, segments=4, baseline=_baseline())
    assert [c["id"] for c in body["candidates"]] == ["c1", "c2"]
    assert body["candidates"][1]["available"] is False
    assert body["candidates"][1]["reason"] == "model chưa pull"
    assert body["estimate_basis"].startswith("đo từ bản dịch #7")


def test_candidate_json_carries_the_declared_quality_warning():
    spec = CandidateSpec(id="c2", engine="qwen2.5-3b", label="Q",
                         quality_note="đã đo: nhại lại nguồn")
    assert candidate_json(spec)["quality_note"] == "đã đo: nhại lại nguồn"


# ---------------------------------------------------------------------------
# RUNNER — N ứng viên, MỘT lượt pha, và đường LÙI có ghi chép
# ---------------------------------------------------------------------------

class _Engine:
    """Engine tối thiểu mà runner cần: một cái tên và cờ glossary.

    `supports_glossary` KHÔNG phải chi tiết trang trí: `candidate_metrics` truyền
    nó xuống `qa_translation`, và QA dùng nó để quyết định có gắn
    `engine_no_glossary` hay không — một engine giả thiếu phương thức này làm runner
    nổ ở giữa đường, đúng như bản đầu của tệp này đã làm.
    """

    def __init__(self, name: str, *, glossary: bool = True) -> None:
        self.name = name
        self._glossary = glossary

    def supports_glossary(self) -> bool:
        return self._glossary


def _runner_plan():
    return _plan([_cand("c1", "a"), _cand("c2", "b", temperature=0.7),
                  _cand("c3", "c", available=False, reason="model chưa pull")],
                 merge_engine="m")


def _totals(tokens_in=1, tokens_out=2, duration_ms=3):
    return {"calls": 1, "tokens_in": tokens_in, "tokens_out": tokens_out,
            "duration_ms": duration_ms}


def _run_factory(log, *, merge_text="[gộp]", merge_drops=False):
    def run(engine, batch, glossary, opts, facts, job, report, progress):
        entry = {"engine": engine.name, "facts": facts,
                 "temperature": opts.temperature,
                 "is_merge": bool(opts.merge_candidates)}
        log.append(entry)
        if opts.merge_candidates:
            entry["candidate_ids"] = [cid for cid, _ in opts.merge_candidates]
            entry["anchor"] = opts.merge_anchor
            if merge_drops:
                return None, [s.i for s in batch], _totals(11, 22, 33)
            return [seg(s.i, merge_text) for s in batch], [], _totals(5, 6, 7)
        return ([seg(s.i, f"{engine.name}:{opts.temperature}") for s in batch], [],
                _totals())
    return run


def _engines():
    return {"a": _Engine("a"), "b": _Engine("b"), "c": _Engine("c"),
            "m": _Engine("m")}


def _opts():
    return MtOpts(source_lang="zh", target_lang="vi")


def test_runner_runs_every_available_candidate_and_one_merge_call():
    log = []
    runner = ChimeraRunner(_runner_plan(), merge_engine=_Engine("m"))
    result = runner.run_batch(run=_run_factory(log), engines=_engines(),
                              batch=_sources(3), glossary=[], opts=_opts(),
                              job=None, report=lambda *_: None, progress=0.0)
    assert [e["engine"] for e in log] == ["a", "b", "m"], (
        "hai ứng viên chạy được + ĐÚNG MỘT lượt pha, theo thứ tự ĐÃ KHAI"
    )
    assert [e["temperature"] for e in log] == [None, 0.7, None], (
        "c1 không khai nhiệt độ (`None` = adapter tự quyết), c2 khai 0,7; lượt pha "
        "để `None` vì nhiệt độ của nó là cấu hình của ADAPTER PHA "
        "(`MERGE_TEMPERATURE`), không phải của một ứng viên"
    )
    from app.adapters.mt.chimera_merge import MERGE_TEMPERATURE
    assert MERGE_TEMPERATURE == 0.1, "lượt pha là GỘP bản đã có, không phải sáng tác"
    assert result.segments is not None
    assert [s.text for s in result.segments] == ["[gộp]"] * 3
    record = result.record
    assert record["ran_count"] == 2 and record["declared"] == 3
    assert record["calls_per_batch"] == 3, "2 ứng viên chạy được + 1 lượt pha"
    assert record["merge"]["calls"] == 1
    assert record["candidates"][2]["skipped"] == "model chưa pull"


def test_runner_records_the_anchor_as_a_one_based_declared_index():
    """`hyp` của §4.5 là chỉ số 1-BASED trong danh sách ĐÃ KHAI.

    Không phải trong danh sách chạy được: đọc theo danh sách chạy được thì cùng một
    ứng viên mang hai số khác nhau giữa hai máy, và "hyp 3" không còn trỏ tới một
    hàng xác định trong kế hoạch.
    """
    log = []
    runner = ChimeraRunner(_runner_plan(), merge_engine=_Engine("m"))
    result = runner.run_batch(run=_run_factory(log), engines=_engines(),
                              batch=_sources(2), glossary=[], opts=_opts(),
                              job=None, report=lambda *_: None, progress=0.0)
    hyp = {int(i): v for i, v in result.record["merge"]["anchor_by_segment"].items()}
    assert hyp == {1: 1, 2: 1}
    assert result.record["anchors"] == {"c1": 2}
    assert log[-1]["candidate_ids"] == ["c1", "c2"]
    assert log[-1]["anchor"] == "c1"


def test_runner_counts_how_many_DISTINCT_outputs_the_candidates_produced():
    """N ứng viên cho ra MỘT chuỗi ⇒ lượt pha không có gì để pha.

    ĐO ĐƯỢC trên máy này: bốn ứng viên `qwen2.5-3b`/`qwen2.5-7b` ở ba mức nhiệt độ
    trả về CHUỖI Y HỆT bản gốc cho cả sáu đoạn, nên `distinct_by_segment` bằng `1` ở
    mọi đoạn. Con số này là thứ biến "chế độ đắt gấp N" từ một lời khai thành một
    phép đo — không có nó thì giao diện không có cách nào nói ra rằng ứng viên trùng
    nhau.
    """
    log = []

    def same_run(engine, batch, glossary, opts, facts, job, report, progress):
        log.append(engine.name)
        if opts.merge_candidates:
            return [seg(s.i, "[gộp]") for s in batch], [], _totals()
        return [seg(s.i, "giống nhau") for s in batch], [], _totals()

    plan = _plan([_cand("c1", "a"), _cand("c2", "b")], merge_engine="m")
    runner = ChimeraRunner(plan, merge_engine=_Engine("m"))
    result = runner.run_batch(run=same_run, engines=_engines(),
                              batch=_sources(3), glossary=[], opts=_opts(),
                              job=None, report=lambda *_: None, progress=0.0)
    assert result.record["distinct_by_segment"] == {"1": 1, "2": 1, "3": 1}, (
        "hai ứng viên trả về CÙNG một chuỗi ⇒ đúng MỘT bản khác nhau"
    )

    def khac_run(engine, batch, glossary, opts, facts, job, report, progress):
        if opts.merge_candidates:
            return [seg(s.i, "[gộp]") for s in batch], [], _totals()
        return [seg(s.i, f"{engine.name}:{s.i}") for s in batch], [], _totals()

    runner2 = ChimeraRunner(_plan([_cand("c1", "a"), _cand("c2", "b")],
                                  merge_engine="m"), merge_engine=_Engine("m"))
    result2 = runner2.run_batch(run=khac_run, engines=_engines(), batch=_sources(2),
                                glossary=[], opts=_opts(), job=None,
                                report=lambda *_: None, progress=0.0)
    assert result2.record["distinct_by_segment"] == {"1": 2, "2": 2}, (
        "hai ứng viên khác nhau ⇒ HAI bản khác nhau"
    )


def test_runner_records_the_segments_where_the_merge_changed_nothing():
    """Lượt pha trả về CHUỖI Y HỆT mỏ neo ⇒ ghi vào `merge.identical_segments`.

    ⚠️ VÌ SAO BÀI NÀY TỒN TẠI (mutant `M8` **SỐNG SÓT** ở lượt mutation đầu): thay khối
    ghi `identical_segments` bằng `pass` KHÔNG làm bài nào đỏ. Hậu quả không phải hình
    thức: `is-chon` vẫn sáng trên mỏ neo, nhưng KHÔNG còn gì nói rằng lượt gọi thứ `N+1`
    vừa tiêu tốn một lượt engine mà không đổi một chữ nào — tức là chế độ đắt gấp `N`
    không còn cách nào tự biện minh. ĐO ĐƯỢC trên máy này: **cả sáu đoạn** rơi vào trường
    hợp đó.

    Bài ghim CẢ HAI CHIỀU: lượt pha không đổi ⇒ có mặt; lượt pha CÓ đổi ⇒ vắng mặt.
    Một chiều thôi thì một hằng số `[1, 2, 3, ...]` cũng làm bài xanh.
    """
    log = []
    plan = _plan([_cand("c1", "a")], merge_engine="m")

    # (a) Lượt pha trả về ĐÚNG chuỗi của mỏ neo ⇒ đoạn nào cũng "không đổi gì".
    khong_doi = ChimeraRunner(plan, merge_engine=_Engine("m"))
    kq = khong_doi.run_batch(run=_run_factory(log, merge_text="a:None"),
                             engines=_engines(), batch=_sources(3), glossary=[],
                             opts=_opts(), job=None, report=lambda *_: None,
                             progress=0.0)
    assert kq.record["merge"]["identical_segments"] == [1, 2, 3], (
        "lượt pha trả về y hệt mỏ neo ở cả ba đoạn ⇒ cả ba phải được ghi"
    )

    # (b) Lượt pha trả về chuỗi KHÁC ⇒ KHÔNG đoạn nào được ghi.
    co_doi = ChimeraRunner(plan, merge_engine=_Engine("m"))
    kq2 = co_doi.run_batch(run=_run_factory(log, merge_text="[gộp]"),
                           engines=_engines(), batch=_sources(3), glossary=[],
                           opts=_opts(), job=None, report=lambda *_: None,
                           progress=0.0)
    assert kq2.record["merge"]["identical_segments"] == [], (
        "lượt pha CÓ đổi chữ ⇒ ghi vào đây là nói sai rằng nó không làm gì"
    )


def test_merge_falls_back_to_the_anchor_and_says_so():
    """Lượt pha hỏng ⇒ bản hợp nhất là bản của MỎ NEO, và điều đó được GHI RA.

    Đây là vế dễ nói dối nhất của cả chế độ: một "bản hợp nhất" thật ra là bản của
    ứng viên số một mà không ai nói, thì giao diện đang trình bày một bản gộp không
    tồn tại. Ba thứ phải có mặt: chữ của mỏ neo, danh sách đoạn đã lùi, và lý do.
    """
    log = []
    runner = ChimeraRunner(_runner_plan(), merge_engine=_Engine("m"))
    result = runner.run_batch(run=_run_factory(log, merge_drops=True),
                              engines=_engines(), batch=_sources(2), glossary=[],
                              opts=_opts(), job=None, report=lambda *_: None,
                              progress=0.0)
    assert [s.text for s in result.segments] == ["a:None"] * 2, (
        "phải là chữ của ứng viên MỎ NEO (c1 / engine a)"
    )
    merge = result.record["merge"]
    assert merge["fallback_segments"] == [1, 2]
    assert "lượt pha thất bại" in merge["fallback_reason"]
    assert merge["calls"] >= 1, "lượt pha ĐÃ chạm engine thì vẫn phải được ĐẾM"


def test_a_missing_merge_engine_is_a_recorded_fallback_not_a_crash():
    runner = ChimeraRunner(_runner_plan(), merge_engine=None)
    result = runner.run_batch(run=_run_factory([]), engines=_engines(),
                              batch=_sources(1), glossary=[], opts=_opts(),
                              job=None, report=lambda *_: None, progress=0.0)
    assert result.segments is not None
    assert "không dựng được engine pha" in result.record["merge"]["fallback_reason"]


def test_runner_returns_no_segments_when_every_candidate_fails():
    runner = ChimeraRunner(_plan([_cand("c1", "a")]), merge_engine=_Engine("m"))

    def run(engine, batch, glossary, opts, facts, job, report, progress):
        return None, [s.i for s in batch], _totals(None, None, None)

    result = runner.run_batch(run=run, engines=_engines(), batch=_sources(2),
                              glossary=[], opts=_opts(), job=None,
                              report=lambda *_: None, progress=0.0)
    assert result.segments is None and result.missing == [1, 2]


def test_session_keeps_the_estimate_recorded_before_the_run():
    """Ước lượng đã HIỆN cho người dùng phải còn nguyên trong bản ghi cuối.

    Giữ nó là cách duy nhất để "đối chiếu trước/sau" so ĐÚNG con số đã hiện, chứ
    không phải một con số tính lại theo công thức mới.
    """
    created = {"enabled": True, "estimate": {"duration_ms": 1234}, "baseline": None,
               "estimate_basis": "đo từ bản dịch #7"}
    runner = ChimeraRunner(_runner_plan(), merge_engine=_Engine("m"), created=created)
    record = runner.session()
    assert record["estimate"] == {"duration_ms": 1234}
    assert record["estimate_basis"] == "đo từ bản dịch #7"
    assert record["enabled"] is True


# ---------------------------------------------------------------------------
# HANDLER — chế độ Chimera đi qua chính sách alignment + ghi `llm_calls`
# ---------------------------------------------------------------------------

class _Job:
    def __init__(self, job_id=1):
        self.id = job_id
        self.state = "running"
        self.progress = 0.0
        self.cancel_requested = False


class _Echo(FakeMtEngine):
    """Ứng viên NHẠI LẠI nguồn — đúng thất bại đã đo được của `qwen2.5-3b` p1."""

    def translate(self, batch, glossary, opts):
        self.attempts.append([s.i for s in batch])
        self.calls.append([s.i for s in batch])
        self.last_stats = CallStats(tokens_in=1, tokens_out=1, duration_ms=1)
        return list(batch)


class _Tot(FakeMtEngine):
    """Ứng viên DỊCH ĐƯỢC: trả tiếng Việt sạch, không còn chữ Hán."""

    def translate(self, batch, glossary, opts):
        self.attempts.append([s.i for s in batch])
        self.calls.append([s.i for s in batch])
        self.last_stats = CallStats(tokens_in=2, tokens_out=3, duration_ms=4)
        return [Segment(i=s.i, start=s.start, end=s.end, text=f"câu {s.i} đã dịch")
                for s in batch]


class _Same(FakeMtEngine):
    """Ứng viên trả về CÙNG một chuỗi — dựng cảnh "ứng viên trùng nhau"."""

    def translate(self, batch, glossary, opts):
        self.attempts.append([s.i for s in batch])
        self.calls.append([s.i for s in batch])
        self.last_stats = CallStats(tokens_in=1, tokens_out=1, duration_ms=1)
        return [Segment(i=s.i, start=s.start, end=s.end, text="[giống hệt]")
                for s in batch]


class _Merge(FakeMtEngine):
    def __init__(self, text="[gộp cả lô]", **kw):
        super().__init__(**kw)
        self.text = text

    @property
    def engine_id(self) -> str:
        return "bo-pha"

    @property
    def prompt_version(self) -> str:
        return "chimera-merge-p1"

    def translate(self, batch, glossary, opts):
        self.attempts.append([s.i for s in batch])
        self.calls.append([s.i for s in batch])
        self.last_stats = CallStats(tokens_in=7, tokens_out=8, duration_ms=9)
        return [Segment(i=s.i, start=s.start, end=s.end, text=self.text)
                for s in batch]


class _DropAllMerge(_Merge):
    """Lượt pha trả RỖNG (0 mục).

    ⚠️ Cố ý KHÔNG ném `AlignmentProblem` từ `translate`: hợp đồng của adapter là
    `AlignmentProblem` đến từ phép KIỂM alignment (`check_alignment`), còn một
    ngoại lệ ném RA TỪ `translate` được tầng gọi coi là lỗi vận chuyển — nó ghi
    `llm_calls` rồi NỔI LÊN, không retry và không hạ cấp. Ném ở đây sẽ kiểm một
    đường khác với đường mà adapter thật đi (adapter thật trả về một danh sách
    thiếu mục rồi để `parse_batch_response` ném).
    """

    def translate(self, batch, glossary, opts):
        self.attempts.append([s.i for s in batch])
        self.calls.append([s.i for s in batch])
        self.last_stats = CallStats(tokens_in=9, tokens_out=9, duration_ms=9)
        return []


@pytest.fixture
def seeded(repos):
    sid = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    segs = _sources(4)
    tid = repos.add_transcript(source_id=sid, engine="fw", lang="zh", segments=segs)
    return repos, tid, segs


def _handler(repos, *, merge):
    engines = {"nhao": _Echo(), "tot": _Tot(), "thuong": FakeMtEngine(),
               "bo-pha": merge}
    plan = _plan([_cand("c1", "nhao"), _cand("c2", "tot")], merge_engine="bo-pha")
    return TranslateHandler(repos, engines, chimera=plan, chimera_merge=merge)


def _run(handler, repos, tid, *, chimera, engine_id="bo-pha"):
    tr = repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=engine_id, target_lang="vi",
        segments=[], prompt_version="chimera-merge-p1", chimera=chimera)
    job = _Job()
    handler.translate(translation_id=tr, transcript_id=tid, engine_id=engine_id,
                      source_lang="zh", target_lang="vi", job=job,
                      report=lambda *_: None)
    return repos.get_translation(tr), job


def test_a_translation_without_the_flag_takes_the_old_path(seeded):
    repos, tid, _segs = seeded
    handler = _handler(repos, merge=_Merge())
    row, _job = _run(handler, repos, tid, chimera=None, engine_id="thuong")
    assert row.chimera is None
    assert all(s.text.startswith("[vi]第") for s in row.segments), (
        "không bật Chimera thì KHÔNG được chạy ứng viên nào"
    )


def test_the_merge_output_is_what_gets_stored(seeded):
    repos, tid, _segs = seeded
    handler = _handler(repos, merge=_Merge())
    row, _job = _run(handler, repos, tid,
                     chimera={"enabled": True, "estimate": {"duration_ms": 5000}})
    assert [s.text for s in row.segments] == ["[gộp cả lô]"] * 4
    trace = row.chimera
    assert trace["enabled"] is True
    assert trace["estimate"] == {"duration_ms": 5000}, (
        "ước lượng ĐÃ GHI LÚC TẠO HÀNG phải còn nguyên trong bản ghi cuối"
    )
    assert [c["id"] for c in trace["candidates"]] == ["c1", "c2"]
    assert trace["ran_count"] == 2
    assert trace["merge"]["calls"] == 1


def test_each_candidate_gets_its_own_row_in_llm_calls(seeded):
    """MỖI ứng viên một hàng `llm_calls`, không phải một hàng tổng.

    Đây là vế "token THẬT của từng ứng viên": `translations.tokens_*` là TỔNG, và
    một cảnh báo chi phí chỉ có tổng thì không nói được ứng viên nào đắt.
    """
    repos, tid, _segs = seeded
    handler = _handler(repos, merge=_Merge())
    row, job = _run(handler, repos, tid, chimera={"enabled": True})
    rows = repos.list_llm_calls(job.id)
    assert [r["engine"] for r in rows] == ["nhao", "tot", "bo-pha"], (
        "MỘT hàng cho MỖI lần chạm engine, theo thứ tự đã chạy"
    )
    assert rows[2]["prompt_version"] == "chimera-merge-p1"
    assert row.duration_ms == sum(r["duration_ms"] for r in rows)
    assert row.tokens_in == sum(r["tokens_in"] for r in rows)


def test_the_echoing_candidate_loses_the_anchor_to_the_translating_one(seeded):
    repos, tid, _segs = seeded
    handler = _handler(repos, merge=_Merge())
    row, _job = _run(handler, repos, tid, chimera={"enabled": True})
    trace = row.chimera
    assert trace["candidates"][0]["echo"] == 4
    assert trace["candidates"][1]["echo"] == 0
    assert trace["anchors"] == {"c2": 4}, (
        "ứng viên nhại lại nguồn phải THUA ứng viên dịch ở cả bốn đoạn"
    )
    assert set(trace["merge"]["anchor_by_segment"].values()) == {2}
    assert trace["ran_count"] == 2


def test_a_run_where_every_candidate_is_identical_is_recorded_as_such(seeded):
    """Mọi ứng viên trả về CHUỖI Y HỆT nhau ⇒ bản ghi phải NÓI RA, không im.

    Dựng cảnh này bằng hai engine cùng trả một chuỗi — đúng hình dạng đo được trên
    máy: bốn ứng viên `qwen` ở ba nhiệt độ trả về cùng một bản chữ Hán.
    """
    repos, tid, _segs = seeded
    merge = _Merge()
    engines = {"giong": _Same(), "tot": _Same(), "bo-pha": merge}
    plan = _plan([_cand("c1", "giong"), _cand("c2", "tot")], merge_engine="bo-pha")
    handler = TranslateHandler(repos, engines, chimera=plan, chimera_merge=merge)
    row, _job = _run(handler, repos, tid, chimera={"enabled": True})
    assert row.chimera["distinct_by_segment"] == {"1": 1, "2": 1, "3": 1, "4": 1}, (
        "hai ứng viên giống hệt nhau ⇒ MỘT bản khác nhau, và con số đó phải ra tới DB"
    )


def test_the_trace_counts_the_segments_each_candidate_produced(seeded):
    repos, tid, _segs = seeded
    handler = _handler(repos, merge=_Merge())
    row, _job = _run(handler, repos, tid, chimera={"enabled": True})
    assert [len(c["segments"]) for c in row.chimera["candidates"]] == [4, 4]


def test_a_chimera_run_whose_merge_dies_stores_the_anchor_text(seeded):
    repos, tid, segs = seeded
    handler = _handler(repos, merge=_DropAllMerge())
    row, _job = _run(handler, repos, tid, chimera={"enabled": True})
    assert [s.text for s in row.segments] == [f"câu {s.i} đã dịch" for s in segs], (
        "lượt pha hỏng ⇒ chữ được giữ là chữ của MỎ NEO (c2 / engine tot)"
    )
    merge = row.chimera["merge"]
    assert merge["fallback_segments"] == [1, 2, 3, 4]
    assert merge["fallback_reason"]
    assert merge["calls"] >= 1, "lượt pha ĐÃ chạm engine thì vẫn phải được ĐẾM"


# ---------------------------------------------------------------------------
# ROUTE — cảnh báo chi phí TRƯỚC khi bấm, và dấu vết SAU khi chạy
# ---------------------------------------------------------------------------

PLAN = _plan([_cand("c1", "nhao"), _cand("c2", "tot"),
              _cand("c3", "thieu", available=False, reason="model chưa pull")],
             merge_engine="bo-pha")

SPECS = [_spec("nhao"), _spec("tot"), _spec("bo-pha"), _spec("thieu", available=False)]


@pytest.fixture
def app_client(tmp_path, repos):
    app = create_app(repos=repos, specs=SPECS, media_dir=tmp_path / "m",
                     out_dir=tmp_path / "o", chimera_plan=PLAN)
    return TestClient(app), repos


def _seed_transcript(repos, n=4):
    sid = repos.add_source(kind="file", origin="x", media_path="/m/x")
    return repos.add_transcript(source_id=sid, engine="fw", lang="zh",
                                segments=_sources(n))


def _seed_done_translation(repos, tid, *, engine="tot", duration_ms=8000,
                           tokens_in=400, tokens_out=800, chimera=None):
    return repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=engine, target_lang="vi",
        segments=[seg(s.i, f"đã dịch {s.i}") for s in _sources(4)],
        prompt_version="qwen-json-p2", duration_ms=duration_ms,
        tokens_in=tokens_in, tokens_out=tokens_out, chimera=chimera, status="done")


def test_cost_route_reports_the_multiplier_and_the_measured_baseline(app_client):
    c, repos = app_client
    tid = _seed_transcript(repos)
    _seed_done_translation(repos, tid)

    body = c.get(f"/api/chimera/cost?transcript_id={tid}").json()
    assert body["declared"] == 3 and body["runnable"] == 2
    assert body["calls_per_batch"] == 3, "2 ứng viên chạy được + 1 lượt pha"
    assert body["merge_engine"] == "bo-pha"
    assert body["baseline"]["translation_id"] is not None
    assert body["estimate"]["duration_ms"] == 8000 * 3, (
        "cùng bốn đoạn, ba lượt ⇒ gấp ba thời gian của lượt đo được"
    )
    assert "đo từ bản dịch" in body["estimate_basis"]
    assert [item["available"] for item in body["candidates"]] == [True, True, False]


def test_cost_route_says_the_estimate_is_unmeasured_without_a_done_translation(app_client):
    c, repos = app_client
    tid = _seed_transcript(repos)
    body = c.get(f"/api/chimera/cost?transcript_id={tid}").json()
    assert body["estimate"] is None
    assert "chưa đo được" in body["estimate_basis"]


def test_a_finished_chimera_run_is_not_used_as_the_baseline(app_client):
    """Cơ sở đo phải là một lượt dịch THƯỜNG, không phải một lượt Chimera.

    Một lượt Chimera tốn `N+1` lời gọi; lấy nó làm mốc rồi nhân thêm `N+1` lần nữa
    là nhân đôi hệ số và thổi phồng cảnh báo lên gấp `N+1`.
    """
    c, repos = app_client
    tid = _seed_transcript(repos)
    _seed_done_translation(repos, tid, duration_ms=100)
    _seed_done_translation(repos, tid, duration_ms=99999, chimera={"enabled": True})

    body = c.get(f"/api/chimera/cost?transcript_id={tid}").json()
    assert body["baseline"]["duration_ms"] == 100, (
        "hàng Chimera mới nhất bị LOẠI khỏi cơ sở đo"
    )


def test_cost_route_refuses_a_transcript_that_does_not_exist(app_client):
    c, _repos = app_client
    assert c.get("/api/chimera/cost?transcript_id=999").status_code == 404


def test_cost_route_reports_503_when_the_registry_has_no_chimera_block(tmp_path, repos):
    app = create_app(repos=repos, specs=SPECS, media_dir=tmp_path / "m",
                     out_dir=tmp_path / "o", chimera_plan=None)
    c = TestClient(app)
    tid = _seed_transcript(repos, 2)
    r = c.get(f"/api/chimera/cost?transcript_id={tid}")
    assert r.status_code == 503 and "chimera" in r.json()["detail"]


def test_create_with_chimera_refuses_when_no_candidate_can_run(app_client):
    c, repos = app_client
    tid = _seed_transcript(repos, 2)
    c.app.state.chimera_plan = _plan(
        [_cand("c1", "a", available=False, reason="chưa pull")], merge_engine="a")
    r = c.post("/api/translations", json={"transcript_id": tid, "engine": "tot",
                                          "chimera": True})
    assert r.status_code == 409
    assert "KHÔNG ứng viên nào chạy được" in r.json()["detail"]
    assert repos.list_translations_for_transcript(tid) == [], (
        "từ chối TRƯỚC khi ghi: một hàng `queued` nằm lại là một lời hứa suông"
    )


def test_create_with_chimera_refuses_when_the_merge_engine_is_not_available(app_client):
    c, repos = app_client
    tid = _seed_transcript(repos, 2)
    c.app.state.chimera_plan = _plan([_cand("c1", "nhao")], merge_engine="thieu")
    r = c.post("/api/translations", json={"transcript_id": tid, "engine": "tot",
                                          "chimera": True})
    assert r.status_code == 409
    assert "engine pha" in r.json()["detail"]


def test_create_with_chimera_records_the_engine_that_wrote_the_text(app_client):
    """`engine` của hàng là engine PHA — người THẬT SỰ viết ra chữ được giữ.

    Ghi id người dùng chọn ở đây là để hàng bản dịch tự nhận công của một engine
    không viết chữ nào.
    """
    c, repos = app_client
    tid = _seed_transcript(repos)
    _seed_done_translation(repos, tid)

    r = c.post("/api/translations", json={"transcript_id": tid, "engine": "nhao",
                                          "chimera": True})
    assert r.status_code == 201
    assert r.json()["translation"]["engine"] == "bo-pha"
    assert r.json()["translation"]["prompt_version"] == "chimera-merge-p1"

    tr_id = r.json()["translation"]["id"]
    trace = c.get(f"/api/translations/{tr_id}").json()["chimera"]
    assert trace["enabled"] is True
    assert trace["declared"] == 3 and trace["run_count"] == 2
    assert trace["estimate"]["duration_ms"] == 8000 * 3, (
        "ước lượng ghi lúc TẠO HÀNG phải là con số đã hiện trước khi bấm"
    )


def test_a_plain_translation_carries_a_null_chimera_trace(app_client):
    c, repos = app_client
    tid = _seed_transcript(repos, 2)
    tr = _seed_done_translation(repos, tid)
    body = c.get(f"/api/translations/{tr}").json()
    assert body["chimera"] is None, (
        "`None` (không chạy Chimera) KHÁC `{}` (chạy mà chưa có dữ liệu)"
    )


# ---------------------------------------------------------------------------
# COMPOSITION ROOT — kế hoạch đọc từ registry THẬT
# ---------------------------------------------------------------------------

def test_chimera_plan_for_reads_the_shipped_registry_and_the_engine_flags():
    from app import main

    specs = load_registry()
    for spec in of_kind(specs, "mt"):
        spec.capabilities["available"] = True
    plan = main.chimera_plan_for(specs)
    assert plan.declared == 6 and plan.run_count == 6
    assert plan.calls_per_batch == 7, "§8.7.5: sáu ứng viên + một lượt pha"

    only_three_b = load_registry()
    for spec in of_kind(only_three_b, "mt"):
        spec.capabilities["available"] = spec.id == "qwen2.5-3b"
    plan2 = main.chimera_plan_for(only_three_b)
    assert plan2.declared == 6, "vẫn HIỆN đủ sáu ứng viên ĐÃ KHAI"
    assert plan2.run_count == 3, "ba ứng viên của qwen2.5-3b chạy được"
    assert plan2.calls_per_batch == 4
    missing = sorted({c.engine for c in plan2.candidates if not c.available})
    assert missing == ["hy-mt-1.5-7b", "opus-mt", "qwen2.5-7b"]


def test_chimera_plan_for_is_empty_when_no_candidate_engine_is_in_specs():
    """Một registry TỐI là cấu hình hợp lệ — nó không được làm nổ lúc dựng."""
    from app import main

    plan = main.chimera_plan_for([])
    assert plan.declared == 0 and plan.merge_engine == ""
    assert plan.calls_per_batch == 1, "0 ứng viên + 1 lượt pha, không âm"


def test_chimera_plan_for_is_deterministic_across_two_calls():
    """`build_components()` và `build_app()` gọi nó RIÊNG — hai kết quả phải bằng nhau.

    Nếu không, `TranslateHandler` và route `/api/chimera/cost` nói về hai kế hoạch
    khác nhau, và cảnh báo chi phí sẽ mô tả một lượt chạy khác với lượt chạy thật.
    """
    from app import main

    specs = load_registry()
    for spec in of_kind(specs, "mt"):
        spec.capabilities["available"] = spec.id == "qwen2.5-3b"
    assert main.chimera_plan_for(specs) == main.chimera_plan_for(specs)


def test_the_merge_adapter_needs_an_engine_that_can_chat():
    """Lượt pha cần một engine biết `chat`; OPUS-MT không có nó.

    Điều kiện là DUCK TYPING chứ không `isinstance`: `tests/test_mt_wiring.py` thay
    `main.OllamaMtEngine` bằng một hàm factory, và `isinstance` với một thuộc tính
    đã bị vá sẽ ném `TypeError` — đúng lỗi mà bản đầu của `chimera_merge_for` mắc.
    """
    from app import main
    from app.adapters.mt.chimera_merge import OllamaMergeEngine
    from app.adapters.mt.opus_mt import OpusMtEngine

    plan = _plan([_cand("c1", "tot")], merge_engine="tot")
    assert main.chimera_merge_for(plan, {"tot": OpusMtEngine("x")}) is None, (
        "OPUS-MT không có `chat`, nên nó không làm được lượt pha"
    )
    assert main.chimera_merge_for(plan, {"tot": object()}) is None
    assert main.chimera_merge_for(plan, {}) is None

    class _Chatty:
        def chat(self, system, user, *, temperature=None):
            return "{}"

    wrapped = main.chimera_merge_for(plan, {"tot": _Chatty()})
    assert isinstance(wrapped, OllamaMergeEngine)
    assert isinstance(wrapped.prompt_version, str)
