from __future__ import annotations

from typing import Protocol

from app.domain.models import Segment


class ASREngine(Protocol):
    engine_id: str

    def transcribe(self, audio_path: str, lang: str) -> list[Segment]:
        ...

    def release(self) -> None:
        """Giải phóng VRAM. Phải an toàn khi gọi nhiều lần."""
        ...
