"""Nối dây **echo guard**: lô dịch bị TỪ CHỐI khi đầu ra vẫn chép nguyên nguồn.

Vì sao có tệp này (SỐ ĐO, clip 115 đoạn `20261019-name-patch-smoke/`, cùng prompt,
cùng 5 thuật ngữ): `hy-mt-1.5-7b` trả nguyên chữ Trung cho **0–8/115** đoạn ở lô 8,
**29/115** ở lô 15, **59–89/115** ở lô 30; `opus-mt` cùng clip là **0/115**. Số mục
VẪN KHỚP nên `check_alignment` cho qua, QA chỉ gắn `lang:<i>` từng dòng, và hàng
`translations` vẫn `done` — tức bản dịch "thành công" mà không dịch. Cổng ở đây là
câu trả lời: đoạn bị chép được dịch lại MỘT MÌNH, và nếu vẫn chép thì cả lô ném
`EchoProblem` thay vì ghi `done`.

Năm bất biến được ghim:
* engine KHÔNG khai `capabilities.echo_guard` nhận đúng MỘT lời gọi và giữ nguyên
  đầu ra Hán của nó — cổng là OPT-IN, nên đường `opus-mt` đã ship không đổi từng
  byte và không tốn một phép kiểm nào;
* engine CÓ khai: chỉ đoạn echo được gọi lại, và gọi MỘT MÌNH (lô 1);
* dịch lại được -> lô thành công, và số đoạn đã sửa hiện ra ở log `echo_guard:<n>/<m>`;
* dịch lại vẫn echo -> `EchoProblem` mang ĐỦ id + số đoạn, hàng dịch `failed`, và
  KHÔNG có segment nào của lô được ghi (không có `done` giả);
* chỉ `text` đổi: `i`/`start`/`end`/`words` lấy từ lô, không lấy từ phản hồi của
  lần dịch lại.

Engine là GIẢ (không GPU, không mạng); repos là `SqliteRepos` THẬT trên DB tạm để
test đi đúng đường ghi của sản phẩm.
"""
from __future__ import annotations

import dataclasses

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment, Word
from app.domain.mt_qa import ECHO_FLAG
from app.pipeline.translate import EchoProblem, TranslateHandler

#: Câu nguồn tiếng Trung và đầu ra GIẢ toàn chữ Latinh (`vi<i>`) — để phép đếm chữ
#: Hán của cổng không bị nhiễu bởi chính đầu ra của engine giả.
SRC = ["作为一个搞艺术的", "最困扰的事就是", "这是小儿放纸鸢图"]


class _Job:
    def __init__(self):
        self.id = None
        self.progress = 0.0
        self.cancel_requested = False


class _FakeEngine:
    """Engine GIẢ: chép nguyên chữ nguồn cho `echo_ids` khi lô có >1 mục.

    `echo_always` echo cả khi được gọi MỘT MÌNH — đó là ca "dịch lại vẫn echo" mà
    cổng phải từ chối cả lô. `sizes` là dấu vết duy nhất trả lời được "đoạn nào bị
    gọi lại, gọi một mình hay gọi trong lô": mỗi phần tử là số mục của MỘT lời gọi.
    """

    def __init__(self, *, echo_ids=(), echo_always=(), fail_single=(),
                 mangle_retry: bool = False, supports_glossary: bool = True):
        self._echo_ids = set(echo_ids)
        self._echo_always = set(echo_always)
        self._fail_single = set(fail_single)
        self._mangle_retry = mangle_retry
        self._supports_glossary = supports_glossary
        self.sizes: list[int] = []
        self.seen: list[list[str]] = []
        self.last_stats = None
        self.model_ref = "fake/echo-guard"

    @property
    def engine_id(self) -> str:
        return "fake-echo-guard"

    def supports_glossary(self) -> bool:
        return self._supports_glossary

    def translate(self, batch, glossary, opts):
        self.sizes.append(len(batch))
        self.seen.append([s.text for s in batch])
        single = len(batch) == 1
        if single and batch[0].i in self._fail_single:
            raise AlignmentProblem(expected_ids=[batch[0].i], got_ids=[], reason="giả")
        out: list[Segment] = []
        for s in batch:
            echo = (s.i in self._echo_always
                    or (not single and s.i in self._echo_ids))
            text = s.text if echo else f"vi{s.i}"
            if single and self._mangle_retry and not echo:
                # Phản hồi CỐ Ý sai mốc thời gian/words: cổng phải giữ mốc của lô,
                # không được tin mốc do model gửi lại.
                out.append(dataclasses.replace(s, text=text, start=99.0, end=99.0,
                                               words=[Word(w="mangled", s=99.0,
                                                           e=99.0)]))
                continue
            out.append(dataclasses.replace(s, text=text))
        return out

    def release(self) -> None:
        pass


@pytest.fixture
def repos(tmp_path):
    repo = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repo.init_schema()
    return repo


def _setup(repos, texts, *, engine="fake-echo-guard"):
    source_id = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    segments = [Segment(i=position, start=float(position), end=float(position) + 1,
                        text=text, words=[Word(w="w", s=0.0, e=1.0)])
                for position, text in enumerate(texts, start=1)]
    transcript_id = repos.add_transcript(source_id=source_id, engine="fw", lang="zh",
                                         segments=segments)
    translation_id = repos.add_translation(
        transcript_id=transcript_id, transcript_version=1, engine=engine,
        target_lang="vi", segments=[], prompt_version="p1")
    return translation_id, transcript_id


def _handler(repos, engine, capabilities):
    return TranslateHandler(repos, {"fake-echo-guard": engine},
                            engine_capabilities=capabilities)


def _translate(handler, repos, translation_id, transcript_id, lines=None):
    """Chạy handler; trả `(translation đã ghi, lỗi nếu có)` — KHÔNG nuốt lỗi khác.

    `EchoProblem` là kết quả MONG ĐỢI của bài "vẫn echo", nên nó được trả về để
    bài ghim nội dung của nó; mọi ngoại lệ khác vẫn nổi lên và làm bài đỏ.
    """
    lines = lines if lines is not None else []
    error = None
    try:
        handler.translate(translation_id=translation_id,
                          transcript_id=transcript_id, engine_id="fake-echo-guard",
                          source_lang="zh", target_lang="vi", job=_Job(),
                          report=lambda progress, line: lines.append((progress, line)))
    except EchoProblem as exc:
        error = exc
    return repos.get_translation(translation_id), error


# ------------------------------------------------ opt-in: engine không khai cờ ---

def test_an_engine_without_the_flag_keeps_the_han_output_it_returned(repos):
    """KHÔNG khai `echo_guard` ⇒ hành vi y như trước: một lời gọi, nhận bản chép.

    Đây là bất biến của toàn bộ thay đổi: `opus-mt` — đo được 0/115 đoạn echo ở cả
    ba lô 8/15/30 — không được chậm đi, không được đỏ lên, và không được chạy
    `echoes_source` chỉ vì một engine khác cần cổng này.
    """
    translation_id, transcript_id = _setup(repos, SRC)
    engine = _FakeEngine(echo_always={1, 2, 3})
    lines: list[tuple[float, str]] = []
    stored, error = _translate(_handler(repos, engine,
                                        {"fake-echo-guard": {"echo_retry": False}}),
                               repos, translation_id, transcript_id, lines)

    assert error is None
    assert engine.sizes == [3], "không khai cờ thì không có lời gọi thêm nào"
    assert [s.text for s in stored.segments] == SRC, (
        "bản chép của model được giữ nguyên"
    )
    assert stored.status == "done"
    assert not [line for _p, line in lines if line.startswith("echo_guard:")], (
        "cổng không được chạy (kể cả phần log) cho engine không khai cờ"
    )


def test_no_capabilities_at_all_is_the_same_as_the_flag_off(repos):
    """Đối chứng: thiếu hẳn `engine_capabilities` phải ra Y HỆT khai cờ tắt."""
    translation_id, transcript_id = _setup(repos, SRC)
    stored_off, _ = _translate(
        _handler(repos, _FakeEngine(echo_always={2}),
                 {"fake-echo-guard": {"echo_retry": False}}),
        repos, translation_id, transcript_id)

    second_id = repos.add_translation(
        transcript_id=transcript_id, transcript_version=1, engine="fake-echo-guard",
        target_lang="vi", segments=[], prompt_version="p1")
    engine_none = _FakeEngine(echo_always={2})
    stored_none, error = _translate(_handler(repos, engine_none, None),
                                    repos, second_id, transcript_id)

    assert error is None
    assert [s.to_json() for s in stored_none.segments] == \
           [s.to_json() for s in stored_off.segments]


# --------------------------------------------- engine CÓ khai cờ: dịch lại được ---

def test_an_echoed_segment_is_retried_alone_and_the_batch_succeeds(repos):
    translation_id, transcript_id = _setup(repos, SRC)
    engine = _FakeEngine(echo_ids={2})
    lines: list[tuple[float, str]] = []
    stored, error = _translate(
        _handler(repos, engine, {"fake-echo-guard": {"echo_guard": True}}),
        repos, translation_id, transcript_id, lines)

    assert error is None
    assert engine.sizes == [3, 1], (
        "lô 3 mục trước, rồi ĐÚNG MỘT lời gọi riêng cho đoạn bị echo — 2 lời gọi"
    )
    assert [s.text for s in stored.segments] == ["vi1", "vi2", "vi3"]
    assert ECHO_FLAG not in stored.segments[1].qa, "dịch lại được thì không gắn cờ"
    assert stored.status == "done"
    assert len(repos.list_llm_calls(None)) == 2, (
        "1 lời gọi cả lô + 1 lời gọi dịch lại = 2 hàng `llm_calls`"
    )
    # Số đo phải hiện ra ở LOG, không chỉ nằm trong đầu người viết code.
    assert any(line.startswith("echo_guard:1/3") for _p, line in lines), (
        f"số đoạn bị chép không có trong log: {[l for _p, l in lines]}"
    )
    assert any(line.startswith("echo_guard: đã sửa 1/3") for _p, line in lines)


def test_a_clean_batch_never_calls_the_guard(repos):
    translation_id, transcript_id = _setup(repos, SRC)
    engine = _FakeEngine()
    lines: list[tuple[float, str]] = []
    stored, error = _translate(
        _handler(repos, engine, {"fake-echo-guard": {"echo_guard": True}}),
        repos, translation_id, transcript_id, lines)

    assert error is None
    assert engine.sizes == [3]
    assert [s.text for s in stored.segments] == ["vi1", "vi2", "vi3"]
    assert not [line for _p, line in lines if line.startswith("echo_guard:")], (
        "lô sạch không được nhiễu log bằng một dòng echo_guard"
    )


# ------------------------------------------- engine CÓ khai cờ: vẫn echo -> ném ---

def test_a_batch_that_still_echoes_raises_echo_problem(repos):
    translation_id, transcript_id = _setup(repos, SRC)
    engine = _FakeEngine(echo_always={2})
    lines: list[tuple[float, str]] = []
    stored, error = _translate(
        _handler(repos, engine, {"fake-echo-guard": {"echo_guard": True}}),
        repos, translation_id, transcript_id, lines)

    assert isinstance(error, EchoProblem), "phải là lỗi CÓ TÊN, không phải RuntimeError"
    assert error.ids == [2] and error.echoed == 1 and error.batch == 3
    assert "2" in str(error) and "1/3" in str(error), (
        "thông báo lỗi phải mang cả id lẫn số đoạn để `jobs.error` đọc được"
    )
    # "KHÔNG ghi `done`" là toàn bộ lý do cổng tồn tại: không segment nào của lô
    # được checkpoint, và hàng dịch phải là `failed`.
    assert stored.status == "failed"
    assert stored.segments == [], "lô hỏng không được ghi một nửa"
    assert any(line.startswith("echo_guard:1/3") for _p, line in lines)
    assert any(line.startswith("echo_guard:1/3 đoạn VẪN") for _p, line in lines)


def test_the_error_names_every_id_that_still_echoes(repos):
    """Không `break` ở id hỏng đầu tiên: thông báo phải liệt kê ĐỦ id."""
    translation_id, transcript_id = _setup(repos, SRC)
    engine = _FakeEngine(echo_always={1, 3})
    stored, error = _translate(
        _handler(repos, engine, {"fake-echo-guard": {"echo_guard": True}}),
        repos, translation_id, transcript_id)

    assert isinstance(error, EchoProblem)
    assert error.ids == [1, 3], "hai đoạn vẫn echo ⇒ id của CẢ HAI"
    assert error.echoed == 2 and error.batch == 3
    assert engine.sizes == [3, 1, 1], "mỗi đoạn echo một lời gọi riêng, không gộp"
    assert len(repos.list_llm_calls(None)) == 3
    assert stored.status == "failed" and stored.segments == []


def test_the_shipped_registry_turns_the_guard_on_for_hymt_only(repos):
    """`registry.json` THẬT: chỉ `hy-mt-1.5-7b` khai cờ — và cờ đó CHẠY.

    Hai vế trong một bài vì chúng là một lời hứa: (1) ba engine còn lại không khai
    `echo_guard`, nên đường `opus-mt`/`qwen2.5-*` đã ship không đổi từng byte;
    (2) cờ của `hy-mt-1.5-7b` được `TranslateHandler` đọc đúng — một khoá khai
    trong JSON mà không ai đọc là một lời khai suông. Đây cũng là bài chống TRÔI
    cho `registry.json`: gỡ cờ khỏi entry đó là phép đỏ, không phải im lặng.
    """
    from app.adapters.registry_file import load_registry

    specs = {spec.id: spec for spec in load_registry()}
    assert specs["hy-mt-1.5-7b"].capabilities.get("echo_guard") is True
    for engine_id in ("opus-mt", "qwen2.5-3b", "qwen2.5-7b"):
        assert "echo_guard" not in specs[engine_id].capabilities, engine_id

    translation_id, transcript_id = _setup(repos, SRC)
    engine = _FakeEngine(echo_always={1, 2, 3})
    handler = TranslateHandler(
        repos, {"fake-echo-guard": engine}, batch_items=3,
        engine_capabilities={"fake-echo-guard":
                             dict(specs["hy-mt-1.5-7b"].capabilities)})
    _stored, error = _translate(handler, repos, translation_id, transcript_id)
    assert isinstance(error, EchoProblem), (
        "capabilities của `hy-mt-1.5-7b` trong registry phải bật cổng thật"
    )
    assert engine.sizes == [3, 1, 1, 1], "lô 3 rồi mỗi đoạn echo một lời gọi riêng"


def test_a_failed_singleton_retry_also_blocks_the_batch(repos):
    """Không lấy được bản dịch sạch (alignment hỏng) = đoạn đó vẫn là bản chép."""
    translation_id, transcript_id = _setup(repos, SRC)
    engine = _FakeEngine(echo_ids={2}, fail_single={2})
    stored, error = _translate(
        _handler(repos, engine, {"fake-echo-guard": {"echo_guard": True}}),
        repos, translation_id, transcript_id)

    assert isinstance(error, EchoProblem)
    assert error.ids == [2]
    assert engine.sizes == [3, 1]
    assert stored.status == "failed" and stored.segments == []


# ------------------------------------------------- chỉ `text` được đổi ---

def test_only_text_changes_on_the_segments_the_guard_repaired(repos):
    """`i`/`start`/`end`/`words` lấy từ LÔ, không lấy từ phản hồi dịch lại.

    Phản hồi của lần dịch lại mang mốc 99,0 và `words` rác; nếu cổng thay cả
    segment bằng phản hồi đó thì phụ đề sẽ lệch mốc — `export` ghép theo VỊ TRÍ và
    `subtitle_format` ghi mốc của segment. Test này là chốt của bất biến đó.
    """
    translation_id, transcript_id = _setup(repos, SRC)
    engine = _FakeEngine(echo_ids={2}, mangle_retry=True)
    stored, error = _translate(
        _handler(repos, engine, {"fake-echo-guard": {"echo_guard": True}}),
        repos, translation_id, transcript_id)

    assert error is None
    repaired = stored.segments[1]
    assert repaired.text == "vi2"
    assert (repaired.i, repaired.start, repaired.end) == (2, 2.0, 3.0), (
        "mốc thời gian của segment đã qua alignment phải được giữ nguyên"
    )
    assert repaired.words == [Word(w="w", s=0.0, e=1.0)], (
        "`words` của lô, không phải của phản hồi"
    )
