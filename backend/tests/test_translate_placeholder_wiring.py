"""Bảo vệ thuật ngữ bằng token, nối dây THẬT qua `TranslateHandler`.

Vì sao test này là test của đường ống chứ không của hàm thuần: chỗ dễ hỏng nhất
không phải `protect`/`restore` mà là ĐÚNG CHỖ che và ĐÚNG NGƯỜI được che. Ba bất
biến được ghim ở đây:

* engine KHÔNG khai `capabilities.term_placeholder` nhận **đúng chuỗi gốc** — nếu
  không, một lần bật cờ cho engine khác là đổi hành vi dịch của nó mà không có số
  đo nào bảo vệ (đo trên `opus-mt`: bản vá tên làm 3/7 câu tệ đi, cùng lý do);
* chỉ `text` được đổi: `i`/`start`/`end`/`words` ra y nguyên, vì `export` ghép phụ
  đề theo chúng;
* câu KHÔNG chứa thuật ngữ phải ra y hệt đường dịch hiện tại **kể cả khi engine
  đã bật cờ** — cơ chế này chỉ được chạm vào câu có thuật ngữ.

Engine là GIẢ (không GPU, không mạng); repos là `SqliteRepos` THẬT trên DB tạm để
test đi đúng đường ghi của sản phẩm.
"""
from __future__ import annotations

import dataclasses

import pytest

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.models import Segment, Term
from app.pipeline.translate import TranslateHandler
from experiments.accuracy_pipelines import name_patch

TITLE_TEXT = "这是小儿放纸鸢图"
TITLE = Term(id=None, lang="zh", term="小儿放纸鸢图",
             translation="Tranh thả diều của trẻ nhỏ (Tiểu Nhi Phóng Chỉ Diên Đồ)",
             approved=True)
KITE = Term(id=None, lang="zh", term="纸鸢", translation="con diều", approved=True)
NAME = Term(id=None, lang="zh", term="曹磊", translation="Tào Lôi", approved=True)


class _Job:
    """Job tối thiểu `translate()` cần: `cancel_requested`, `progress`, `id`."""

    def __init__(self):
        self.id = None
        self.progress = 0.0
        self.cancel_requested = False


class _FakePlaceholderEngine:
    """Engine GIẢ: "dịch" bằng cách bọc `[vi]`, và có công tắc bỏ token.

    `seen` giữ CHUỖI NHẬN ĐƯỢC của từng lần gọi: đó là thứ duy nhất chứng minh
    được "engine không khai cờ nhận đúng chữ gốc". Không dùng
    `monkeypatch`-engine.translate vì cách đó buộc test phải chép lại thân hàm.
    """

    def __init__(self, *, drop: tuple[str, ...] = (), echo: bool = False,
                 supports_glossary: bool = True):
        self._drop = drop
        self._echo = echo
        self._supports_glossary = supports_glossary
        self.seen: list[list[str]] = []
        self.model_ref = "fake/placeholder"
        self.last_stats = None

    @property
    def engine_id(self) -> str:
        return "fake-mt"

    def supports_glossary(self) -> bool:
        return self._supports_glossary

    def translate(self, batch, glossary, opts):
        self.seen.append([s.text for s in batch])
        out: list[Segment] = []
        for s in batch:
            text = s.text if self._echo else "[vi]" + s.text
            for token in self._drop:
                # Model bỏ token: giữ phần chữ còn lại, KHÔNG bịa lại tên.
                text = text.replace(token, "").replace("  ", " ")
            out.append(dataclasses.replace(s, text=text))
        return out

    def release(self) -> None:
        pass


@pytest.fixture
def repos(tmp_path):
    repo = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repo.init_schema()
    return repo


def _setup(repos, texts, terms=(), *, engine="fake-mt"):
    source_id = repos.add_source(kind="file", origin="x.mp4", media_path="/m/x.mp4")
    segments = [Segment(i=position, start=float(position), end=float(position) + 1,
                        text=text, words=[])
                for position, text in enumerate(texts, start=1)]
    transcript_id = repos.add_transcript(source_id=source_id, engine="fw", lang="zh",
                                         segments=segments)
    translation_id = repos.add_translation(
        transcript_id=transcript_id, transcript_version=1, engine=engine,
        target_lang="vi", segments=[], prompt_version="p1")
    for term in terms:
        repos.upsert_term(lang=term.lang, term=term.term,
                          translation=term.translation, note=None,
                          approved=term.approved)
    return translation_id, transcript_id


def _run(repos, engine, translation_id, transcript_id, *,
         term_placeholder=True, engine_id="fake-mt"):
    """Chạy handler trên DB thật; trả (segments đã ghi, các chuỗi engine nhận)."""
    capabilities = ({engine_id: {"term_placeholder": term_placeholder}}
                    if term_placeholder is not None else None)
    handler = TranslateHandler(repos, {engine_id: engine},
                               engine_capabilities=capabilities)
    handler.translate(translation_id=translation_id, transcript_id=transcript_id,
                      engine_id=engine_id, source_lang="zh", target_lang="vi",
                      job=_Job(), report=lambda _progress, _line: None)
    return repos.get_translation(translation_id).segments, engine.seen


def test_the_engine_receives_tokens_and_the_output_carries_the_rendering(repos):
    """Bản dịch của thuật ngữ đến từ GLOSSARY, không từ lựa chọn của model.

    Model GIẢ "dịch" bằng cách bọc `[vi]` quanh chữ nhận được: nếu handler không
    thay token thì đầu ra vẫn còn `ZXQ1` thô, còn nếu nó để model tự dịch (không
    che) thì đầu ra là chữ Hán — cả hai đều làm bài này đỏ.
    """
    translation_id, transcript_id = _setup(repos, [TITLE_TEXT], [KITE, TITLE])
    out, seen = _run(repos, _FakePlaceholderEngine(), translation_id, transcript_id)

    assert seen == [["这是ZXQ1"]], "engine phải nhận BẢN ĐÃ CHE, không phải chữ gốc"
    assert out[0].text == "[vi]这是" + TITLE.translation
    assert "ZXQ" not in out[0].text, "token thô không được lọt vào phụ đề"


def test_an_echoing_engine_round_trips_the_text(repos):
    echo = Term(id=None, lang="zh", term="曹磊", translation="曹磊", approved=True)
    translation_id, transcript_id = _setup(repos, ["这是曹磊的鱼灯"], [echo])
    out, seen = _run(repos, _FakePlaceholderEngine(echo=True), translation_id,
                     transcript_id)

    assert seen == [["这是ZXQ1的鱼灯"]]
    assert out[0].text == "这是曹磊的鱼灯", (
        "engine chép nguyên văn bản đã che ⇒ sau khi khôi phục phải đúng chuỗi đầu vào"
    )


def test_a_dropped_token_keeps_the_model_text_and_flags_the_segment(repos):
    """Model bỏ token: KHÔNG ném, KHÔNG bịa lại tên, chỉ đánh cờ `token_lost`."""
    translation_id, transcript_id = _setup(repos, [TITLE_TEXT], [KITE, TITLE])
    out, _seen = _run(repos, _FakePlaceholderEngine(drop=("ZXQ1",)), translation_id,
                      transcript_id)

    assert out[0].text == "[vi]这是", "giữ ĐÚNG chữ model viết, không chèn tên vào"
    assert "token_lost" in out[0].qa
    assert repos.get_translation(translation_id).status == "done"


def test_an_engine_without_the_capability_gets_the_original_text(repos):
    """Engine không khai cờ: adapter nhận ĐÚNG chuỗi gốc, đầu ra y hệt hôm nay."""
    translation_id, transcript_id = _setup(repos, [TITLE_TEXT], [KITE, TITLE])
    engine = _FakePlaceholderEngine()
    out_off, seen_off = _run(repos, engine, translation_id, transcript_id,
                             term_placeholder=False)

    assert seen_off == [[TITLE_TEXT]], (
        "engine không khai `term_placeholder` phải nhận nguyên văn chữ nguồn"
    )
    assert out_off[0].text == "[vi]" + TITLE_TEXT

    # Đối chứng: đường KHÔNG có `engine_capabilities` (đường của bản trước tính
    # năng) phải ra y hệt — "tắt cờ" và "không biết cờ" là cùng một hành vi.
    second_id = repos.add_translation(
        transcript_id=transcript_id, transcript_version=1, engine="fake-mt",
        target_lang="vi", segments=[], prompt_version="p1")
    out_none, seen_none = _run(repos, _FakePlaceholderEngine(), second_id,
                               transcript_id, term_placeholder=None)
    assert seen_none == seen_off
    assert [s.to_json() for s in out_none] == [s.to_json() for s in out_off]


def test_timings_ids_and_words_are_untouched(repos):
    """Chỉ `text` được đổi. `export` ghép phụ đề theo `i`/`start`/`end`."""
    special = Segment(i=2, start=12.5, end=15.25, text="曹磊", words=[],
                      speaker="A", suspect=True)
    translation_id, transcript_id = _setup(repos, [TITLE_TEXT, "曹磊"], [KITE, TITLE,
                                                                       NAME])
    source = repos.get_transcript(transcript_id).segments
    out, _seen = _run(repos, _FakePlaceholderEngine(), translation_id, transcript_id)

    assert [s.i for s in out] == [s.i for s in source]
    assert [s.start for s in out] == [s.start for s in source]
    assert [s.end for s in out] == [s.end for s in source]
    assert [s.words for s in out] == [s.words for s in source]
    assert [s.text for s in out] == ["[vi]这是" + TITLE.translation, "[vi]Tào Lôi"]
    assert special.start, "segment đặc biệt trong fixture chỉ để đọc rõ ý đồ"


def test_an_empty_glossary_changes_nothing(repos):
    translation_id, transcript_id = _setup(repos, [TITLE_TEXT], [])
    out, seen = _run(repos, _FakePlaceholderEngine(), translation_id, transcript_id)
    assert seen == [[TITLE_TEXT]]
    assert out[0].text == "[vi]" + TITLE_TEXT


def test_a_sentence_without_terms_is_byte_identical_with_the_capability_on(repos):
    """Câu không chứa thuật ngữ phải đi đường CŨ, kể cả khi cờ đang bật.

    Che theo TỪNG segment (không theo cả lô) nên đây là điều kiện tách được: câu 1
    có thuật ngữ, câu 2 thì không, và câu 2 phải đến engine y nguyên từng byte.
    """
    translation_id, transcript_id = _setup(repos, ["曹磊", "你们要的大嘛"], [NAME])
    out, seen = _run(repos, _FakePlaceholderEngine(), translation_id, transcript_id)

    assert seen == [["ZXQ1", "你们要的大嘛"]], (
        "câu không có thuật ngữ phải đến engine đúng chuỗi gốc"
    )
    assert out[1].text == "[vi]你们要的大嘛"
    assert out[1].qa == []


def test_a_source_sentence_that_already_has_a_token_is_not_protected(repos):
    """Nguồn có sẵn `ZXQ1` (ASR nghe ra, hoặc kịch bản): KHÔNG che, GẮN CỜ.

    Che lên chữ có sẵn thì `restore` không phân biệt được token của ta với chữ của
    bản gốc và sẽ thay cả hai — nên câu đó đi thẳng đường dịch, và người đọc được
    báo bằng `token_collision_in_source` thay vì nhận một bản dịch đã bị sửa lén.
    """
    translation_id, transcript_id = _setup(repos, ["ZXQ1 và 曹磊"], [NAME])
    out, seen = _run(repos, _FakePlaceholderEngine(), translation_id, transcript_id)

    assert seen == [["ZXQ1 và 曹磊"]], "câu va chạm phải đến engine nguyên văn"
    assert out[0].text == "[vi]ZXQ1 và 曹磊"
    assert "token_collision_in_source" in out[0].qa
    assert "token_lost" not in out[0].qa, "không có token nào của ta để mà mất"


# ---------------------------------------------------------------------------
# Cổng capability của bản vá tên riêng (`name_patch`)
# ---------------------------------------------------------------------------
_SPECS = [
    dataclasses.make_dataclass("Spec", [("kind", str), ("id", str),
                                        ("capabilities", dict)])(
        kind="mt", id="hy-mt-1.5-7b", capabilities={"name_patch": True}),
    dataclasses.make_dataclass("Spec", [("kind", str), ("id", str),
                                        ("capabilities", dict)])(
        kind="mt", id="opus-mt", capabilities={"glossary_patch": False}),
]

_SYLLABLES = {"我": "wo", "去": "qu", "了": "le", "燕": "yan", "烟": "yan",
              "台": "tai", "山": "shan"}


def _fake_pinyin(text: str) -> list[str]:
    return [_SYLLABLES.get(char, char) for char in text]


def _no_t2s(text: str) -> str:
    return text


def _patch(engine_id):
    return name_patch.patch_transcript(
        [{"i": 0, "start": 10.0, "end": 12.0, "text": "我去了燕台山"}],
        [{"i": 7, "start": 10.1, "end": 11.9, "ocr": "我去了烟台山"}],
        pinyin_fn=_fake_pinyin, t2s_fn=_no_t2s, engine_id=engine_id, specs=_SPECS)


def test_the_name_patch_only_runs_for_engines_that_declare_it():
    """`opus-mt` không khai `name_patch` ⇒ KHÔNG vá, chữ ra y nguyên đầu vào.

    ĐO ĐƯỢC lý do: áp bản vá rồi dịch bằng `opus-mt` làm 3 trong 7 câu TỆ ĐI, nên
    "engine lạ thì mặc định KHÔNG vá" là luật, không phải tuỳ chọn.
    """
    skipped = _patch("opus-mt")
    assert [s["text"] for s in skipped.segments] == ["我去了燕台山"]
    assert skipped.changes == []
    assert skipped.stats["applied"] == 0
    assert skipped.stats["name_patch"] is False
    assert "opus-mt" in skipped.stats["skipped_reason"]

    unknown = _patch("không-có-engine-này")
    assert [s["text"] for s in unknown.segments] == ["我去了燕台山"], (
        "id lạ cũng phải mặc định KHÔNG vá"
    )


def test_the_shipped_registry_allows_the_patch_for_hymt_only():
    """Nguồn sự thật là `registry.json` THẬT, không phải bảng trong test."""
    assert name_patch.name_patch_allowed("hy-mt-1.5-7b") is True
    assert name_patch.name_patch_allowed("opus-mt") is False
    assert name_patch.name_patch_allowed("qwen2.5-7b") is False

    patched = _patch("hy-mt-1.5-7b")
    assert [s["text"] for s in patched.segments] == ["我去了烟台山"]
    assert patched.stats["applied"] == 1


# ---------------------------------------------------------------------------
# QA không được nói SAI khi thuật ngữ đã được ÉP bằng token
# ---------------------------------------------------------------------------


def test_enforced_terms_do_not_claim_the_engine_has_no_glossary(repos):
    """`engine_no_glossary` và `length:` từng bắn SAI khi cơ chế token bật.

    Đo trên smoke thật: engine `hy-mt-1.5-7b` khai `glossary_prompt: false`, nên
    QA gắn `engine_no_glossary` — trong khi mọi thuật ngữ ĐÃ được ép bằng token;
    và rendering tiêu đề dài (46 ký tự cho 6 chữ nguồn) làm `length:14=7.75` dù
    bản dịch không lan man. Cả hai cờ đều là thông tin sai cho người đọc.

    Engine dưới đây trả CÙNG một câu cho cả hai lần chạy, nên biến duy nhất giữa
    hai lần là cờ `term_placeholder` — đúng thứ bài này cô lập.
    """
    class _RendersTitle:
        model_ref = "fake/renders-title"
        last_stats = None

        def __init__(self):
            self.seen: list[list[str]] = []

        @property
        def engine_id(self) -> str:
            return "fake-mt"

        def supports_glossary(self) -> bool:
            return False

        def translate(self, batch, glossary, opts):
            self.seen.append([s.text for s in batch])
            return [dataclasses.replace(s, text="Đây là " + TITLE.translation)
                    for s in batch]

        def release(self) -> None:
            pass

    translation_id, transcript_id = _setup(repos, [TITLE_TEXT], [KITE, TITLE])
    _run(repos, _RendersTitle(), translation_id, transcript_id)
    issues = repos.get_translation(translation_id).qa_issues
    assert "engine_no_glossary" not in issues, issues
    assert not [i for i in issues if i.startswith("length:")], issues

    # Đối chứng: TẮT cờ thì cả hai lại bắn — nếu không, bài này không phân biệt
    # được gì và sẽ xanh kể cả khi ai đó gỡ mất đường nối `glossary_enforced`.
    second_id = repos.add_translation(
        transcript_id=transcript_id, transcript_version=1, engine="fake-mt",
        target_lang="vi", segments=[], prompt_version="p1")
    _run(repos, _RendersTitle(), second_id, transcript_id, term_placeholder=False)
    control = repos.get_translation(second_id).qa_issues
    assert "engine_no_glossary" in control, control
    # `length:` KHÔNG xuất hiện ở cả hai lần, và đó là chủ ý: việc quy rendering
    # glossary về độ dài chữ nguồn không phụ thuộc cơ chế nào đã đặt rendering vào
    # câu — chuỗi policy dài không phải model lan man, dù nó đến từ token hay từ
    # model tự viết. Xem `test_mt_qa.py::test_a_long_glossary_rendering_*`.
    assert not [i for i in control if i.startswith("length:")], control
