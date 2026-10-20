"""Echo = "model không dịch mà chép nguyên chữ nguồn": nhận diện + dịch lại.

Vì sao có tệp này (SỐ ĐO, clip 115 đoạn `20261019-name-patch-smoke/`): ở lô 30,
`hy-mt-1.5-7b` trả nguyên chữ Trung cho 59–89/115 đoạn. Số mục VẪN KHỚP nên
`check_alignment` cho qua, `qa_translation` chỉ gắn cờ `lang:<i>` từng dòng, hàng
`translations` vẫn `done` — một lượt "4 lời gọi / 32,8 s" là lượt KHÔNG dịch. Đó
là lý do cơ chế ở đây là DỊCH LẠI, không phải chỉ báo.

Ba bất biến được ghim:
* engine KHÔNG khai `capabilities.echo_retry` nhận đúng MỘT lời gọi cho cả lô,
  kể cả khi đầu ra là bản chép — bật cơ chế cho engine khác là đổi hành vi dịch
  của nó mà không có số đo nào bảo vệ;
* chỉ đoạn bị echo mới được gọi lại, và nó được gọi MỘT MÌNH (lô 1);
* lần dịch lại hỏng KHÔNG được làm mất lô: vẫn đủ segment, chữ của model được
  giữ, và đoạn đó mang cờ `echo` trên `Segment.qa`.

Engine là GIẢ (không GPU, không mạng); repos là `SqliteRepos` THẬT trên DB tạm để
test đi đúng đường ghi của sản phẩm.
"""
from __future__ import annotations

import dataclasses

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.alignment import AlignmentProblem
from app.domain.models import Segment
from app.domain.mt_qa import (ECHO_HAN_RATIO, ECHO_FLAG, echo_run_issue, is_echo)
from app.pipeline.translate import TranslateHandler

#: Câu nguồn tiếng Trung, và bản dịch GIẢ toàn chữ Latinh (`vi<i>`) — để phép
#: đếm chữ Hán của `is_echo` không bị nhiễu bởi chính đầu ra của engine giả.
SRC = ["作为一个搞艺术的", "最困扰的事就是", "这是小儿放纸鸢图"]


class _Job:
    def __init__(self):
        self.id = None
        self.progress = 0.0
        self.cancel_requested = False


class _EchoEngine:
    """Engine GIẢ: chép nguyên chữ nguồn cho `echo_ids` khi lô có >1 mục.

    `sizes` là dấu vết DUY NHẤT trả lời được "đoạn nào bị gọi lại, gọi một mình
    hay gọi trong lô": mỗi phần tử là số mục của MỘT lời gọi, theo đúng thứ tự.
    """

    def __init__(self, *, echo_ids=(), echo_always=(), fail_single=(),
                 supports_glossary: bool = True):
        self._echo_ids = set(echo_ids)
        self._echo_always = set(echo_always)
        self._fail_single = set(fail_single)
        self._supports_glossary = supports_glossary
        self.sizes: list[int] = []
        self.seen: list[list[str]] = []
        self.last_stats = None
        self.model_ref = "fake/echo"

    @property
    def engine_id(self) -> str:
        return "fake-echo"

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
            out.append(dataclasses.replace(s, text=s.text if echo else f"vi{s.i}"))
        return out

    def release(self) -> None:
        pass


@pytest.fixture
def repos(tmp_path):
    repo = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repo.init_schema()
    return repo


def _setup(repos, texts, *, engine="fake-echo"):
    source_id = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    segments = [Segment(i=position, start=float(position), end=float(position) + 1,
                        text=text, words=[])
                for position, text in enumerate(texts, start=1)]
    transcript_id = repos.add_transcript(source_id=source_id, engine="fw", lang="zh",
                                         segments=segments)
    translation_id = repos.add_translation(
        transcript_id=transcript_id, transcript_version=1, engine=engine,
        target_lang="vi", segments=[], prompt_version="p1")
    return translation_id, transcript_id


def _run(repos, engine, translation_id, transcript_id, *, echo_retry=True,
         engine_id="fake-echo", extra=None):
    caps = {"echo_retry": echo_retry}
    caps.update(extra or {})
    capabilities = {engine_id: caps} if echo_retry is not None else None
    handler = TranslateHandler(repos, {engine_id: engine},
                               engine_capabilities=capabilities)
    handler.translate(translation_id=translation_id, transcript_id=transcript_id,
                      engine_id=engine_id, source_lang="zh", target_lang="vi",
                      job=_Job(), report=lambda _progress, _line: None)
    stored = repos.get_translation(translation_id)
    return stored, engine


# ---------------------------------------------------------------- hàm thuần ---

def test_is_echo_catches_an_exact_copy_and_an_empty_line():
    assert is_echo("作为一个搞艺术的", "作为一个搞艺术的") is True
    assert is_echo("作为一个搞艺术的", "  作为一个搞艺术的 ") is True, (
        "khoảng trắng đầu/cuối không làm một bản chép thành bản dịch"
    )
    assert is_echo("作为一个搞艺术的", "   ") is True, (
        "dòng rỗng không phải bản dịch: nó phải bị DỊCH LẠI, không chỉ bị báo `empty:`"
    )


def test_is_echo_does_not_call_a_preserved_number_an_echo():
    """`2288` -> `2288`: con số được GIỮ NGUYÊN, không phải bản chép của bản dịch.

    Đoạn 9 của clip 115 đoạn có nguồn KHÔNG một chữ Hán nào, nên không có gì để
    "chưa dịch": giữ nguyên con số là bản dịch ĐÚNG. QA cũ vẫn gắn cờ `echo` cho
    nó chỉ vì hai chuỗi giống nhau — cờ đó có trong cả `20261019-echo-guard/` và
    `20261019-prompt-echo-sweep/`.
    """
    assert is_echo("2288", "2288") is False
    assert is_echo("2288", "  2288  ") is False, (
        "khoảng trắng không được biến một con số giữ nguyên thành echo"
    )
    assert is_echo("V2.3", "V2.3") is False, (
        "mã/token Latinh cũng là đầu ra hợp lệ khi nguồn không có chữ Hán"
    )


def test_is_echo_still_catches_a_han_source_copied_verbatim():
    """Luật "nguồn không có chữ Hán" KHÔNG được nới lỏng ca thật của echo.

    Cùng ca đã đo `qwen2.5-3b` ở prompt `p1`: nguồn Hán, đích y hệt từng ký tự
    (43/44 đoạn) — vẫn phải là echo để nó còn được DỊCH LẠI.
    """
    assert is_echo("小儿放纸鸢图", "小儿放纸鸢图") is True
    assert is_echo("  你来了  ", "你来了") is True


def test_is_echo_catches_a_chinese_rewrite_that_is_not_byte_identical():
    """Ca KHÓ: model không chép y nguyên mà viết lại TRONG chính tiếng Trung.

    Đo trên artifact thật (lô 30, 22/89 đoạn echo): `而且看讲的都是路人` ->
    `而且讲讲的都是路人`, `我反正要来一场大的` -> `我反正要办一场盛大的活动`.
    Phép so nguyên văn bỏ sót cả hai; tỉ lệ chữ Hán của chúng là 1,00.
    """
    assert is_echo("而且看讲的都是路人", "而且讲讲的都是路人") is True
    assert is_echo("我反正要来一场大的", "我反正要办一场盛大的活动") is True


def test_is_echo_leaves_a_vietnamese_translation_alone():
    assert is_echo("作为一个搞艺术的", "Là một người làm nghệ thuật") is False
    assert is_echo("福州烟台山的市场负责人",
                   "福州Yên Đài Sơn的市场负责人") is False, (
        "câu lai còn tên riêng Hán là bản dịch HỎNG MỘT PHẦN, không phải bản chép: "
        "tỉ lệ Hán của nó (0,42) nằm dưới ngưỡng, và trên đường ống nó còn được "
        "phép so nguyên văn trên bản ĐÃ token hoá bắt trước"
    )


def test_the_threshold_is_the_documented_one():
    """Ngưỡng là DỮ LIỆU đã đo (khoảng trống 0,29–1,00), không phải số tuỳ ý."""
    assert ECHO_HAN_RATIO == 0.5


def test_echo_run_issue_only_above_five_percent():
    src = [Segment(i=i, start=0.0, end=0.0, text="作为一个搞艺术的") for i in range(20)]
    one = [Segment(i=i, start=0.0, end=0.0,
                   text=("作为一个搞艺术的" if i == 0 else "Là một người làm nghệ thuật"))
           for i in range(20)]
    two = [dataclasses.replace(s, text=("作为一个搞艺术的" if s.i in (0, 1)
                                        else "Là một người làm nghệ thuật"))
           for s in one]

    assert echo_run_issue(src, one) is None, "1/20 = 5% chưa VƯỢT ngưỡng 5%"
    assert echo_run_issue(src, two) == "echo:2/20"
    assert echo_run_issue([], []) is None, "không có mẫu số thì không có tỉ lệ"


# ------------------------------------------------------------- nối dây thật ---

def test_an_echoed_segment_is_retried_alone_and_replaced(repos):
    translation_id, transcript_id = _setup(repos, SRC)
    stored, engine = _run(repos, _EchoEngine(echo_ids={2}), translation_id,
                          transcript_id)

    assert engine.sizes == [3, 1], (
        "lô 3 mục trước, rồi ĐÚNG MỘT lời gọi riêng cho đoạn bị echo"
    )
    assert [s.text for s in stored.segments] == ["vi1", "vi2", "vi3"]
    assert ECHO_FLAG not in stored.segments[1].qa, "dịch lại được thì không gắn cờ"
    assert stored.status == "done"


def test_only_the_echoed_ids_are_retried(repos):
    translation_id, transcript_id = _setup(repos, SRC)
    _stored, engine = _run(repos, _EchoEngine(echo_ids={1, 3}), translation_id,
                           transcript_id)

    assert engine.sizes == [3, 1, 1], "hai đoạn echo ⇒ hai lời gọi riêng, không gộp"
    assert engine.seen[1] == [SRC[0]] and engine.seen[2] == [SRC[2]]


def test_an_engine_without_the_capability_gets_one_call_for_the_whole_batch(repos):
    """Engine không khai `echo_retry`: KHÔNG có lời gọi thêm nào.

    Nhưng nó vẫn bị BÁO: `echo:<n>/<tổng>` là cảnh báo về ĐẦU RA, không phải một
    phần của cơ chế dịch lại — một engine không được bật cơ chế mà lại chép nguồn
    77% số đoạn còn nguy hiểm hơn, nên tín hiệu này không được phụ thuộc vào cờ.
    """
    translation_id, transcript_id = _setup(repos, SRC)
    stored, engine = _run(repos, _EchoEngine(echo_ids={2}), translation_id,
                          transcript_id, echo_retry=False)

    assert engine.sizes == [3], "không khai cờ thì không có lời gọi thêm nào"
    assert stored.segments[1].text == SRC[1], "bản chép của model được giữ nguyên"
    assert ECHO_FLAG not in stored.segments[1].qa
    assert "echo:1/3" in stored.qa_issues, (
        "cảnh báo đi theo ĐẦU RA: cờ tắt thì vẫn phải biết là lượt dịch này có "
        "đoạn không được dịch"
    )

    # Đối chứng: "không truyền capabilities" phải ra y hệt "tắt cờ".
    second_id = repos.add_translation(
        transcript_id=transcript_id, transcript_version=1, engine="fake-echo",
        target_lang="vi", segments=[], prompt_version="p1")
    stored_none, engine_none = _run(repos, _EchoEngine(echo_ids={2}), second_id,
                                    transcript_id, echo_retry=None)
    assert engine_none.sizes == engine.sizes
    assert [s.text for s in stored_none.segments] == [s.text for s in stored.segments]


def test_a_segment_that_still_echoes_keeps_the_model_text_and_is_flagged(repos):
    translation_id, transcript_id = _setup(repos, SRC)
    stored, engine = _run(repos, _EchoEngine(echo_always={2}), translation_id,
                          transcript_id)

    assert engine.sizes == [3, 1], "vẫn thử lại đúng một lần, không lặp vô hạn"
    assert stored.segments[1].text == SRC[1], "giữ chữ model viết, không bịa lại"
    assert ECHO_FLAG in stored.segments[1].qa
    assert stored.status == "done", "một đoạn hỏng không được làm hỏng cả lượt"


def test_a_failed_retry_does_not_lose_the_batch(repos):
    translation_id, transcript_id = _setup(repos, SRC)
    stored, engine = _run(repos, _EchoEngine(echo_ids={2}, fail_single={2}),
                          translation_id, transcript_id)

    assert engine.sizes == [3, 1]
    assert len(stored.segments) == 3, "lô đã hợp lệ về số mục: không được vứt đi"
    assert stored.segments[1].text == SRC[1]
    assert ECHO_FLAG in stored.segments[1].qa
    assert stored.status == "done"


def test_every_retry_leaves_exactly_one_llm_call_row(repos):
    """Chi phí của cơ chế ĐẾM ĐƯỢC — đây là con số phải nhìn trước khi bật cờ."""
    translation_id, transcript_id = _setup(repos, SRC)
    stored, engine = _run(repos, _EchoEngine(echo_ids={1, 2, 3}), translation_id,
                          transcript_id)

    assert engine.sizes == [3, 1, 1, 1]
    calls = repos.list_llm_calls(None)
    assert len(calls) == 4, "1 lô + 3 lần dịch lại = 4 hàng `llm_calls`"
    assert all(row["ok"] for row in calls)


def test_a_clean_batch_never_retries(repos):
    translation_id, transcript_id = _setup(repos, SRC)
    stored, engine = _run(repos, _EchoEngine(), translation_id, transcript_id)

    assert engine.sizes == [3]
    assert [s.text for s in stored.segments] == ["vi1", "vi2", "vi3"]
    assert not [q for q in stored.qa_issues if q.startswith("echo:")]


def test_the_run_level_issue_is_raised_when_the_engine_echoes_most_of_the_clip(repos):
    texts = [f"作为一个搞艺术的{i}" for i in range(6)]
    translation_id, transcript_id = _setup(repos, texts)
    stored, _engine = _run(repos, _EchoEngine(echo_always=set(range(1, 7))),
                           translation_id, transcript_id)

    assert "echo:6/6" in stored.qa_issues, (
        "một lượt dịch KHÔNG dịch gì vẫn `done` — nên tín hiệu phải nằm ở "
        "`qa_issues`, và nó phải nói ra tỉ lệ chứ không chỉ từng dòng"
    )
    assert stored.status == "done", (
        "cảnh báo, không chặn: `degraded` là thay đổi từ vựng status (DB/API/UI) "
        "và chưa được làm trong lượt này"
    )


# ------------------------------------- trần số mục RIÊNG của từng engine ---

def test_max_items_per_call_one_makes_the_engine_translate_each_segment_alone(repos):
    """`capabilities.max_items_per_call: 1` ⇒ mỗi đoạn một lời gọi, không lô.

    Số đo đứng sau khoá này: cùng prompt p2, `hy-mt-1.5-7b` echo 90/115 đoạn ở lô
    30 và 0/115 ở lô 1. Test ghim ĐÚNG hình dạng lời gọi, vì đó là thứ quyết định
    echo — không phải một cờ trang trí.
    """
    translation_id, transcript_id = _setup(repos, SRC)
    stored, engine = _run(repos, _EchoEngine(), translation_id, transcript_id,
                          extra={"max_items_per_call": 1})

    assert engine.sizes == [1, 1, 1], "ba đoạn ⇒ ba lời gọi một mục"
    assert [s.text for s in stored.segments] == ["vi1", "vi2", "vi3"]


def test_without_the_capability_the_handler_still_batches(repos):
    """Engine không khai khoá ⇒ lô theo chính sách chung (một lời gọi cho cả lô).

    Đây là bất biến của toàn bộ thay đổi: `opus-mt` — đo được 0 echo ở cả ba lô —
    KHÔNG được chậm đi vì một cơ chế của engine khác.
    """
    translation_id, transcript_id = _setup(repos, SRC)
    _stored, engine = _run(repos, _EchoEngine(), translation_id, transcript_id)

    assert engine.sizes == [3]


def test_an_explicit_batch_items_wins_over_the_engine_capability(repos):
    """Số cụ thể truyền vào handler THẮNG capability — để phép đo còn đo được."""
    translation_id, transcript_id = _setup(repos, SRC)
    engine = _EchoEngine()
    handler = TranslateHandler(repos, {"fake-echo": engine}, batch_items=2,
                               engine_capabilities={"fake-echo": {
                                   "echo_retry": False, "max_items_per_call": 1}})
    handler.translate(translation_id=translation_id, transcript_id=transcript_id,
                      engine_id="fake-echo", source_lang="zh", target_lang="vi",
                      job=_Job(), report=lambda _progress, _line: None)

    assert engine.sizes == [2, 1], "lô 2 rồi lô 1 — đúng `batch_items=2`"
