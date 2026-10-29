"""Use case bóc băng. Ráp registry + engine + repos.

Bất biến: engine được GIỮ theo engine_id và chỉ tạo mới khi đổi engine. Nạp
lại model cho từng job là lãng phí 4-8 giây mỗi lần.
"""
from __future__ import annotations

import inspect
import pathlib
from typing import Callable, Iterable, Mapping

from app.domain import job_state as js
from app.domain.models import Job
from app.domain.paths import PathOutsideRoot, resolve_within
from app.domain.nguon_chu import chon_nguon, khoang_co_tieng
from app.ports.asr import ASREngine
from app.ports.ocr import OCREngine
from app.ports.repos import Repos
from app.registry import (MT_DEFAULT_SETTING, EngineSpec, by_id,
                          default_mt_engine)

AUTO_FORWARD_SETTING = "auto_forward"

#: Ngôn ngữ đích của bản dịch tự sinh. Chưa phải setting (không có khoá nào
#: trong bảng `settings` cho nó), nhưng phải là HẰNG SỐ DÙNG CHUNG giữa hàng
#: `translations` và payload của job — lệch một chữ ở đây là bản dịch được ghi
#: bằng ngôn ngữ khác với thứ handler đọc từ payload.
DEFAULT_TARGET_LANG = "vi"


def dinh_dang_giay(giay: float) -> str:
    """`mm:ss` cho câu tiến độ — đọc được trong một dòng log, không phải một số thực."""
    tong = max(0, int(giay))
    return f"{tong // 60}:{tong % 60:02d}"


def _boc_bang(engine: ASREngine, audio: str, lang: str,
              bao_tien_do: Callable[[float, float], None]):
    """Gọi `engine.transcribe`, kèm `on_progress` NẾU adapter đó nhận.

    Vì sao PHÉP DÒ chứ không phải một chữ ký cứng cho mọi adapter: tiến độ theo đoạn là thứ
    adapter TUỲ CHỌN cung cấp (chỉ engine có vòng lặp đoạn mới báo được), còn `SenseVoice` và
    mọi double trong test có chữ ký hai tham số. Truyền thẳng `on_progress=` cho chúng là
    `TypeError` — tức bản vá "thêm tiến độ" sẽ làm sập mọi engine không có nó.

    `inspect.signature`, KHÔNG `try/except TypeError`: một `TypeError` ném từ BÊN TRONG lần
    bóc băng sẽ bị nuốt rồi gọi lại lần thứ hai, che mất lỗi thật và bóc băng hai lượt.
    """
    if "on_progress" not in inspect.signature(engine.transcribe).parameters:
        return engine.transcribe(audio, lang)
    return engine.transcribe(audio, lang, on_progress=bao_tien_do)


class TranscribeHandler:
    def __init__(
        self,
        repos: Repos,
        specs: Iterable[EngineSpec],
        engine_factory: Callable[[EngineSpec], ASREngine],
        *,
        workdir: str | pathlib.Path,
        declared_default_mt: str | None = None,
        prompt_versions: Mapping[str, str] | None = None,
        ocr_engine: OCREngine | None = None,
    ) -> None:
        self._repos = repos
        self._specs = list(specs)
        self._factory = engine_factory
        self._workdir = pathlib.Path(workdir)
        #: Khoá `default_mt` của registry (R58/WQ-02), do `main.py` nạp. Vắng nó
        #: thì `_default_mt_engine` mới rơi về phần tử đầu của danh sách `mt`.
        self._declared_default_mt = declared_default_mt
        #: `{engine_id: prompt_version}` — DỮ LIỆU của `adapters/mt/prompts.py`,
        #: do composition root bơm vào. `add_translation` BẮT BUỘC có
        #: `prompt_version`, mà `pipeline/` không được biết adapter (chỉ
        #: `main.py` được phép), nên nó đi qua đây y như `declared_default_mt`.
        #: Vắng mặt thì ghi `"unknown"`: bịa ra một phiên bản prompt còn tệ hơn.
        self._prompt_versions = dict(prompt_versions or {})
        self._engine: ASREngine | None = None
        self._engine_id: str | None = None
        #: OCR la TUY CHON: `None` nghia la "khong co OCR", va duong ASR thuan van
        #: nguyen ven. Moi bai test `transcribe` cu dung handler khong truyen tham so
        #: nay, nen chung ghim dung hanh vi cu — do la ly do no la tham so keyword co
        #: mac dinh.
        self._ocr = ocr_engine

    def handles(self) -> str:
        return "asr"

    def _engine_for(self, engine_id: str) -> ASREngine:
        if self._engine is not None and self._engine_id == engine_id:
            return self._engine
        if self._engine is not None:
            self._engine.release()
            self._engine = None
        spec = by_id(self._specs, engine_id)
        self._engine = self._factory(spec)
        self._engine_id = engine_id
        return self._engine

    def release(self) -> None:
        if self._engine is not None:
            self._engine.release()
            self._engine = None
            self._engine_id = None

    def chon_doan(self, media_path: str, lang: str, *,
                  dung_ocr_lam_goc: bool = True,
                  asr_engine_id: str | None = None) -> tuple[list[Segment], str]:
        """Chọn nguồn chữ cho MỘT media. Trả `(đoạn, lý do tiếng Việt)`.

        Thứ tự: OCR (nếu có engine VÀ `dung_ocr_lam_goc`) -> ASR -> lỗi.

        🔴 VÌ SAO KHÔNG PHẢI "CHỈ OCR": video không có phụ đề cứng thì OCR trả `[]` một cách
        HỢP LỆ, và rơi về ASR là hành vi đúng. ĐO ĐƯỢC lý do vẫn ưu tiên OCR khi có: trên
        đoạn 120-420 s của video thật, ASR chỉ đúng 66,27 % ký tự (bản gốc) và 60,48 %
        (trên vocals tách); OCR đọc chữ đã biên tập nên đúng chính tả, lại phủ tới 1243 s
        trong khi ASR dừng ở 1186,4 s.

        ASR LUÔN chạy trước khi gọi OCR, vì tầng lọc 4 cần `khoang_asr`. Đó là chi phí đã
        biết: muốn dùng tầng 4 thì phải trả tiền ASR.
        """
        engine_id = asr_engine_id or self._engine_id
        doan_asr: list[Segment] = []
        if self._ocr is not None and engine_id:
            # Chạy ASR TRƯỚC để có `khoang_asr` cho tầng lọc 4. `_engine_for` giữ engine
            # theo id nên nạp model một lần, không phải mỗi lượt.
            doan_asr = self._engine_for(engine_id).transcribe(media_path, lang)
        if self._ocr is not None and dung_ocr_lam_goc:
            khoang = khoang_co_tieng(doan_asr)
            doan_ocr = self._ocr.doc_phu_de(media_path, khoang_asr=khoang or None)
            if doan_ocr:
                return chon_nguon(doan_ocr, doan_asr)
        if not doan_asr and engine_id:
            doan_asr = self._engine_for(engine_id).transcribe(media_path, lang)
        return chon_nguon([], doan_asr)

    def run(self, job: Job, report: Callable[[float, str], None]) -> None:
        source_id = job.payload["source_id"]
        source = self._repos.get_source(source_id)
        if not source.audio_path:
            raise FileNotFoundError(
                f"source {source_id} chưa có audio; job ingest phải chạy trước"
            )
        audio = pathlib.Path(source.audio_path)
        # M-12: `audio_path` là dữ liệu ĐỌC TỪ DB, nên phải CHỨNG MINH nó nằm
        # trong gốc media trước khi mở — cùng luật với `routes_media.py` (đường
        # ĐỌC) và `pipeline/ingest.py` (đường GHI). `self._workdir` CHÍNH LÀ gốc
        # media: `main.py:192` dựng handler này bằng `workdir=MEDIA_DIR`, nên
        # không phải plumb thêm gì.
        #
        # KHÔNG có nhánh `if self._workdir is None`: `workdir` là tham số
        # keyword-only BẮT BUỘC nên luôn có. Nhánh đó tồn tại ở `ingest.py:196`
        # vì `media_root` ở đó là tham số tuỳ chọn — chép nguyên nó sang đây là
        # bịa ra một trạng thái không tồn tại.
        try:
            audio = resolve_within(self._workdir, audio)
        except PathOutsideRoot as exc:
            raise FileNotFoundError(
                f"tệp audio nằm ngoài gốc media ({self._workdir}): {exc}") from exc
        # `is_file()` chứ không `exists()`: một THƯ MỤC cũng `exists()`, nên nó
        # lọt qua phép kiểm cũ rồi nổ ở tận trong engine với thông báo mơ hồ.
        if not audio.is_file():
            raise FileNotFoundError(f"tệp audio không tồn tại: {audio}")

        lang = source.lang or "zh"
        # Nguồn chữ do `chon_doan` quyết: OCR (nếu có engine) -> ASR -> lỗi. Đường ASR
        # THUẦN vẫn nguyên khi `self._ocr is None`, nên mọi hành vi cũ giữ nguyên.
        #
        # Báo "nạp engine" / "tải model" CHỈ có nghĩa với ASR: adapter ASR nạp model 2,9 GB
        # ở lần dùng đầu và thanh tiến độ đứng im suốt lúc đó (đo được: 6 phút ở 15%). OCR
        # không có bước ấy — nó đọc khung và báo tiến độ ở `report(0.30, ...)`.
        if self._ocr is None:
            engine = self._engine_for(job.engine or "")
            hoi_cache = getattr(engine, "model_cached", None)
            # CHỈ cảnh báo khi adapter trả ĐÚNG `False` ("chắc chắn không có"). `None` = không
            # biết, và một câu "chưa có model" sai còn tệ hơn không nói gì — bản đầu của bản
            # vá này báo sai cho MỌI job vì `spec.model_ref` là bí danh (`large-v3-turbo`)
            # còn repo thật là `mobiuslabsgmbh/...`.
            if callable(hoi_cache) and hoi_cache() is False:
                report(0.05, f"chưa có model của {job.engine} trên đĩa — lần đầu phải tải "
                             f"về, có thể mất vài phút (không phải treo)")
            else:
                report(0.05, f"nạp engine {job.engine}")

            # `report` đi TIẾP vào trong vòng lặp của adapter để progress nhích theo số đoạn
            # đã bóc, thay vì đứng ở 0,15 cho tới khi xong. Trần 0,89: ba bước sau (lưu
            # transcript, tạo job dịch, xong) vẫn có chỗ riêng của chúng.
            def bao_tien_do(da_toi: float, tong_giay: float) -> None:
                if tong_giay <= 0:
                    return
                ti_le = min(1.0, max(0.0, da_toi / tong_giay))
                report(0.15 + 0.74 * ti_le,
                       f"bóc băng {audio.name}: {dinh_dang_giay(da_toi)} / "
                       f"{dinh_dang_giay(tong_giay)} ({round(100 * ti_le)}%)")

            report(0.15, f"bóc băng {audio.name} (lang={lang})")
            segments = _boc_bang(engine, str(audio), lang, bao_tien_do)
            ly_do = f"dùng ASR: {len(segments)} đoạn lời nói"
        else:
            report(0.05, f"chọn nguồn chữ cho {audio.name} (lang={lang})")
            segments, ly_do = self.chon_doan(str(audio), lang,
                                            asr_engine_id=job.engine or None)
            # Tiến độ ĐÃ báo trong `chon_doan`/ASR; không gắn `on_progress` cho OCR vì đọc
            # khung không phát tiến độ theo đoạn, thanh sẽ đứng ở 15 % suốt 6 phút.
            report(0.30, ly_do)

        #: `engine` ghi ĐÚNG nguồn đã dùng, không phải engine của job: nếu chữ đến từ OCR mà
        #: ghi `fw-large-v3` thì lịch sử nói dối, và không cách nào phát hiện bằng cách đọc
        #: transcript. Đây là lý do `chon_doan` trả kèm `ly_do` chứ không chỉ danh sách.
        # `ly_do` được `chon_doan` đặt cho MỌI nhánh (OCR, ASR, và cả nhánh ASR
        # thuần khi không có OCR). Tiền tố là hợp đồng đã ghim ở `test_nguon_chu.py`,
        # nên đọc nó ở đây không phải đoán chuỗi tự do.
        engine_ghi = ("rapidocr" if ly_do.startswith("dùng OCR")
                      else (job.engine or ""))

        # R68, và cố ý đặt ở ĐÂY chứ không trong từng adapter: guard này phải
        # đúng cho MỌI engine. `SenseVoiceEngine` đã có guard riêng của nó
        # (adapters/asr/sensevoice.py), nhưng engine MẶC ĐỊNH của GĐ1a —
        # `fw-large-v3-turbo` — là `FasterWhisperEngine`, và nó không có guard
        # nào: audio im lặng (VAD bỏ hết) trả `[]` mà không ném, nên job thành
        # `done` kèm một transcript 0 đoạn. Một transcript rỗng trông y hệt một
        # lần bóc băng thành công mà không có tiếng nói, nên nó giấu mất lỗi
        # giải mã/thiếu model. Thà hỏng ồn ào còn hơn (xem R62).
        if not segments:
            raise RuntimeError(
                f"{job.engine}: không có đoạn nào — audio im lặng hay giải mã hỏng. "
                f"KHÔNG lưu transcript rỗng (R68)."
            )

        report(0.9, f"đã có {len(segments)} đoạn")
        transcript_id = self._repos.add_transcript(
            source_id=source_id, engine=engine_ghi, lang=lang, segments=segments,
        )
        report(0.95, f"lưu transcript #{transcript_id}")

        if (self._repos.get_setting(AUTO_FORWARD_SETTING, "1") or "1") == "1":
            self._forward_to_translation(transcript_id, lang)
            report(0.98, "đã tạo job dịch ở workspace 2")
        else:
            report(0.98, "giữ lại để sửa (auto_forward tắt)")
        report(1.0, "xong")

    def _forward_to_translation(self, transcript_id: int, lang: str) -> None:
        """Tạo HÀNG `translations` trước, rồi mới xếp job `translate`.

        Thứ tự này là bắt buộc, không phải phong cách: `TranslateHandler` ghi
        checkpoint và trạng thái lên hàng đó, và nó tra `translation_id` từ
        payload. Không có hàng thì job tự sinh sẽ `NotFound`/`KeyError` ở tận
        worker — đúng lớp lỗi mà Giai đoạn 1a đã trả giá (handler được dựng mà
        thiếu thứ nó cần).

        Payload là ĐÚNG năm khoá `TranslateHandler.run` đọc
        (`pipeline/translate.py:71-77`): `translation_id`, `transcript_id`,
        `engine_id`, `source_lang`, `target_lang`. `source_id` đã bị bỏ: handler
        dịch không đọc nó, còn nguồn thì tra được qua transcript.

        `transcript_version` là version của transcript VỪA tạo (đọc lại từ
        repo), không phải "version hiện tại" tại thời điểm job chạy — job có thể
        chạy sau khi người dùng sửa transcript, và khi đó bản dịch này phải được
        coi là lệch thời (`is_stale`).

        `glossary_version` đi qua ĐÚNG nguồn mà đường API dùng
        (`routes_translations.create_translation` gọi `repos.glossary_version()`).
        Thiếu nó thì `add_translation` nhận `None` và cột thành NULL, tức cùng
        một trạng thái (hàng `queued`, 0 segment, job chưa chạy) có hai nghĩa
        khác nhau tuỳ đường tạo hàng — M-4 của review cuối.
        """
        engine_id = self._default_mt_engine()
        transcript = self._repos.get_transcript(transcript_id)
        translation_id = self._repos.add_translation(
            transcript_id=transcript_id,
            transcript_version=transcript.version,
            engine=engine_id or "",
            target_lang=DEFAULT_TARGET_LANG,
            segments=[],
            prompt_version=self._prompt_versions.get(engine_id or "", "unknown"),
            glossary_version=self._repos.glossary_version(),
            status="queued",
        )
        self._repos.add_job(Job(
            id=None, workspace=2, type="translate", engine=engine_id,
            phase=js.phase_of("translate", engine_id),
            payload={
                "translation_id": translation_id,
                "transcript_id": transcript_id,
                "engine_id": engine_id,
                "source_lang": lang,
                "target_lang": DEFAULT_TARGET_LANG,
            },
        ))

    def _default_mt_engine(self) -> str | None:
        """Engine dịch mặc định — DỮ LIỆU, không phải thứ tự dòng trong registry.

        R58/WQ-02: bản cũ lấy thẳng `mt_specs[0].id`, tức thứ tự mảng `mt` của
        `registry.json` quyết định engine mặc định của cả pipeline (hiện ra đúng
        `opus-mt` chỉ do may). Nay khoá `default_mt` do `main.py` nạp được ưu
        tiên; chỉ khi registry không khai báo gì thì mới rơi về phần tử đầu.
        """
        return default_mt_engine(
            self._specs,
            declared=self._declared_default_mt,
            configured=self._repos.get_setting(MT_DEFAULT_SETTING),
        )
