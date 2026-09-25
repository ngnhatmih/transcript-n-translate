"""Mô hình dữ liệu thuần. KHÔNG import gì ngoài stdlib.

Bất biến quan trọng: khoá tuỳ chọn chỉ xuất hiện khi engine thật sự sinh ra nó.
Không được bịa `words: []` cho engine không có word timestamp — nếu bịa, tầng
giao diện sẽ tưởng có dữ liệu từng từ và vẽ sai.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

SUSPECT_NO_SPEECH_PROB = 0.6
SUSPECT_AVG_LOGPROB = -1.0


@dataclass
class Word:
    w: str
    s: float
    e: float

    def to_json(self) -> dict:
        return {"w": self.w, "s": self.s, "e": self.e}

    @classmethod
    def from_json(cls, d: dict) -> "Word":
        return cls(w=d["w"], s=float(d["s"]), e=float(d["e"]))


@dataclass
class Segment:
    i: int
    start: float
    end: float
    text: str
    words: list[Word] | None = None
    emotion: str | None = None
    events: list[str] = field(default_factory=list)
    speaker: str | None = None
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    suspect: bool = False
    t: str | None = None
    qa: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def mark_suspect(self) -> None:
        """Đặt cờ nghi ngờ theo đúng ngưỡng trong spec."""
        if self.no_speech_prob is not None and self.no_speech_prob > SUSPECT_NO_SPEECH_PROB:
            self.suspect = True
        if self.avg_logprob is not None and self.avg_logprob < SUSPECT_AVG_LOGPROB:
            self.suspect = True

    def to_json(self) -> dict:
        d: dict = {
            "i": self.i,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
        }
        if self.words is not None:
            d["words"] = [w.to_json() for w in self.words]
        if self.emotion is not None:
            d["emotion"] = self.emotion
        if self.events:
            d["events"] = list(self.events)
        if self.speaker is not None:
            d["speaker"] = self.speaker
        if self.avg_logprob is not None:
            d["avg_logprob"] = round(self.avg_logprob, 4)
        if self.no_speech_prob is not None:
            d["no_speech_prob"] = round(self.no_speech_prob, 4)
        d["suspect"] = self.suspect
        if self.t is not None:
            d["t"] = self.t
        if self.qa:
            d["qa"] = list(self.qa)
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Segment":
        words = d.get("words")
        return cls(
            i=int(d["i"]),
            start=float(d["start"]),
            end=float(d["end"]),
            text=d.get("text", ""),
            words=[Word.from_json(w) for w in words] if words is not None else None,
            emotion=d.get("emotion"),
            events=list(d.get("events") or []),
            speaker=d.get("speaker"),
            avg_logprob=d.get("avg_logprob"),
            no_speech_prob=d.get("no_speech_prob"),
            suspect=bool(d.get("suspect", False)),
            t=d.get("t"),
            qa=list(d.get("qa") or []),
        )


def segments_to_json(segments: list[Segment]) -> str:
    return json.dumps([s.to_json() for s in segments], ensure_ascii=False)


def segments_from_json(raw: str) -> list[Segment]:
    return [Segment.from_json(d) for d in json.loads(raw)]


@dataclass
class Source:
    id: int | None
    kind: str          # 'file' | 'url'
    origin: str
    media_path: str
    lang: str | None = None
    audio_path: str | None = None
    duration: float | None = None
    created_at: str = ""


@dataclass
class Transcript:
    id: int | None
    source_id: int
    engine: str
    lang: str
    segments: list[Segment]
    version: int = 1
    status: str = "draft"        # draft | reviewed | translated
    created_at: str = ""


@dataclass
class Translation:
    id: int | None
    transcript_id: int
    transcript_version: int
    engine: str
    segments: list[Segment]
    prompt_version: str
    target_lang: str = "vi"
    glossary_version: int | None = None
    qa_issues: list[str] = field(default_factory=list)
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int | None = None
    created_at: str = ""


@dataclass
class TranslationSummary:
    """Một hàng `translations` ĐÃ BỎ `segments`.

    Route transcript chỉ cần biết bản dịch nào thuộc transcript nào và nó dịch
    từ version mấy để tính `stale`. Kéo theo `segments` là giải mã JSON của cả
    một bản dịch đầy đủ cho mỗi hàng trong danh sách — đúng thứ
    `list_transcripts()` cố tình tránh ở route danh sách.

    Không phải `Translation` rút gọn: `Translation.segments` là trường BẮT BUỘC,
    nên nhét `[]` vào đó là bịa ra một bản dịch rỗng.
    """
    id: int | None
    transcript_id: int
    transcript_version: int
    engine: str
    target_lang: str
    prompt_version: str
    created_at: str = ""


@dataclass
class Job:
    id: int | None
    workspace: int
    type: str                 # ingest | asr | translate | export
    engine: str | None
    phase: str
    state: str = "queued"
    payload: dict = field(default_factory=dict)
    cancel_requested: bool = False
    attempts: int = 0
    progress: float = 0.0
    log_tail: str = ""
    log_path: str | None = None
    error: str | None = None
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None

    def to_event(self) -> dict:
        """Hình dạng sự kiện SSE của job này.

        MỘT nguồn cho cả `worker._emit` lẫn ảnh chụp đầu stream của
        `/api/jobs/stream`: `stream_events` khử trùng theo NỘI DUNG, nên hai bên
        lệch khoá là sự kiện vừa bị gửi trùng vừa bị bỏ sót — hỏng âm thầm.

        `log_tail` nằm trong sự kiện vì design §9.2 yêu cầu log streaming qua
        SSE: client chỉ nghe stream vẫn phải thấy dòng log vừa sinh. Trường này
        đã bị chặn ở `LOG_TAIL_LINES` nên sự kiện vẫn nhỏ.
        """
        return {
            "id": self.id,
            "state": self.state,
            "progress": self.progress,
            "phase": self.phase,
            "error": self.error,
            "log_tail": self.log_tail,
        }


@dataclass
class Term:
    id: int | None
    lang: str
    term: str
    translation: str
    note: str | None = None
    approved: bool = False
    created_at: str = ""


@dataclass
class CallStats:
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int | None = None
