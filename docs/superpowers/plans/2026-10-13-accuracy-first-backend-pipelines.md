# Accuracy-First Backend Pipelines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate, reproducible benchmark branch with seven accuracy-oriented ASR/translation pipelines, post-processing rules, reference metrics, and a runner that compares their saved outputs.

**Architecture:** Keep production handlers and API unchanged. Put pipeline contracts, shared model lifecycle, metrics, and post-processing in `backend/experiments/accuracy_pipelines/`; each selectable variant gets one module, while a CLI runs them sequentially against the same extracted audio and writes JSON plus Markdown artifacts.

**Tech Stack:** Existing Python backend, registry/adapters, `httpx`, ffmpeg/ffprobe, pytest, Ollama local API; no new Python runtime dependency.

**Spec:** `docs/superpowers/specs/2026-10-13-accuracy-first-backend-pipelines-design.md`

## Global Constraints

- Do not change application routes, default engines, persisted translation schema, or production behavior.
- Keep all model stages sequential and release models between stages; target the available 8 GB VRAM.
- Preserve raw ASR and MT results alongside every corrected or edited result.
- Preserve exact segment ids, order, timestamps, and non-empty outputs; invalid model output fails its stage.
- Optional references produce CER and character n-gram chrF; absent references produce manual comparison artifacts and no fabricated scores.
- Unit tests must not require CUDA, Ollama, network access, or downloaded model weights.
- Only add tests because the user explicitly requested a test suite and retesting.

---

### Task 1: Shared pipeline result and evaluation metrics

**Files:**
- Create: `backend/experiments/__init__.py`
- Create: `backend/experiments/accuracy_pipelines/__init__.py`
- Create: `backend/experiments/accuracy_pipelines/contracts.py`
- Create: `backend/experiments/accuracy_pipelines/metrics.py`
- Create: `backend/tests/experiments/test_metrics.py`

**Interfaces:**
- `PipelineContext`: media/audio paths, source/target language, approved glossary, temp/output paths, model ids, frame interval.
- `PipelineResult`: `pipeline_id`, `stages`, `source_segments`, optional `corrected_segments`, `raw_translation`, optional `final_translation`, and `metadata`.
- `char_error_rate(reference: str, hypothesis: str) -> float` uses normalized Unicode text and Levenshtein distance.
- `chrf(reference: str, hypothesis: str, *, max_order: int = 6, beta: float = 2.0) -> float` returns a 0–100 character n-gram F-score.

- [x] **Step 1: Add metric tests first.** Cover identical strings (0 CER, 100 chrF), empty reference, empty hypothesis, one substitution, Unicode Vietnamese, and punctuation/whitespace normalization.
- [x] **Step 2: Run the metric tests first and confirm the missing-module failure.**
- [x] **Step 3: Implement the dataclasses and stdlib-only normalized CER/chrF functions.** Keep metric inputs as plain strings so segment concatenation is owned by the comparison layer.
- [x] **Step 4: Rerun that test file and confirm all hand-calculated expectations pass.**
- [x] **Step 5: Commit only the shared contracts and metric files.** Completed in the approved design/spec commits; implementation remains on the requested feature branch.

### Task 2: Safe transcript and translation post-processing

**Files:**
- Create: `backend/experiments/accuracy_pipelines/postprocess.py`
- Create: `backend/tests/experiments/test_postprocess.py`
- Reuse: `backend/app/domain/models.py`, `backend/app/domain/mt_qa.py`, `backend/app/domain/glossary_match.py`

**Interfaces:**
- `validate_asr_correction(original: list[Segment], corrected: list[Segment]) -> list[Segment]` accepts only exact id/order/timestamp coverage and non-empty text; if model output is invalid it raises `PipelineOutputError` and the caller retains the original list.
- `validate_translation_edit(source: list[Segment], raw: list[Segment], edited: list[Segment], glossary: list[Term]) -> list[Segment]` enforces exact alignment, non-empty text, timestamps, and approved glossary terms.
- `normalize_for_scoring(text: str) -> str` performs Unicode NFKC, canonical punctuation handling, and whitespace normalization without changing saved source text.

- [x] **Step 1: Write tests for missing, duplicate, reordered ids; altered timestamps; empty text; glossary mismatch; and supported corrections.**
- [x] **Step 2: Run the postprocess tests red-first and verify the missing behavior, then rerun after implementation.**
- [x] **Step 3: Implement validation as pure functions.** Do not accept model output that changes timing, adds/removes segments, or violates approved glossary entries.
- [x] **Step 4: Add normalization and model-output tests; confirm they pass.**
- [x] **Step 5: Preserve pre-existing dirty files; feature work remains uncommitted on the requested branch to avoid capturing unrelated edits.**

### Task 3: Shared model lifecycle and media preparation

**Files:**
- Create: `backend/experiments/accuracy_pipelines/runtime.py`
- Create: `backend/tests/experiments/test_runtime.py`
- Reuse: `backend/app/adapters/asr/factory.py`, `backend/app/adapters/mt/ollama_mt.py`, `backend/app/adapters/mt/opus_mt.py`, `backend/app/adapters/registry_file.py`, `backend/app/pipeline/ingest.py`

**Interfaces:**
- `load_runtime_context(args) -> PipelineContext` loads the registry, validates input paths and tags, prepares HF/ModelScope caches, and extracts one canonical 16 kHz mono WAV in a temporary directory.
- `transcribe(engine_id: str, audio_path: str, lang: str) -> list[Segment]` builds via the existing ASR factory and always calls `release()` in `finally`.
- `translate(engine_id: str, segments: list[Segment], glossary: list[Term], source_lang: str, target_lang: str) -> list[Segment]` builds via shipped adapter patterns and releases the model in `finally`.
- `ollama_json(model: str, system: str, prompt: str, *, images: list[Path] = ()) -> tuple[dict, dict]` requests JSON from `/api/chat`, returns parsed content and usage stats, and unloads the Ollama model in `finally`.
- `extract_context_frames(media_path: Path, out_dir: Path, interval_seconds: int) -> list[Path]` rejects audio-only input and samples a bounded number of frames with ffmpeg.

- [x] **Step 1: Add fake engine/client tests for release paths, tag checks, single audio extraction, and audio-only frame rejection.**
- [x] **Step 2: Run runtime tests red-first and verify green after implementation.**
- [x] **Step 3: Implement lazy model construction and injected test clients; reuse existing extractors/adapters.**
- [x] **Step 4: Implement Ollama JSON parsing, image transport, usage collection, unload, and explicit missing-tag commands.**
- [x] **Step 5: Verify runtime tests; do not commit overlapping pre-existing dirty files.**

### Task 4: Implement the seven selectable pipeline modules

**Files:**
- Create: `backend/experiments/accuracy_pipelines/baseline.py`
- Create: `backend/experiments/accuracy_pipelines/sensevoice_opus.py`
- Create: `backend/experiments/accuracy_pipelines/whisper_hymt.py`
- Create: `backend/experiments/accuracy_pipelines/whisper_hymt_qwen3b_edit.py`
- Create: `backend/experiments/accuracy_pipelines/whisper_qwen7b.py`
- Create: `backend/experiments/accuracy_pipelines/dual_asr_hymt.py`
- Create: `backend/experiments/accuracy_pipelines/visual_context.py`
- Modify: `backend/experiments/accuracy_pipelines/__init__.py`
- Create: `backend/tests/experiments/test_pipeline_contracts.py`

**Interfaces:** Every module exposes `PIPELINE_ID: str`, `MODEL_TAGS: tuple[str, ...]`, and `run(context: PipelineContext) -> PipelineResult`. Registry `PIPELINES: dict[str, Callable]` maps ids to those run functions.

- [x] **Step 1: Write fake-runtime contract tests for all seven ids and stage ordering.**
- [x] **Step 2: Run contract tests red-first and verify green after implementation.**
- [x] **Step 3: Implement the baseline, SenseVoice/OPUS, and Whisper/HY-MT variants.**
- [x] **Step 4: Implement bounded contextual editing, glossary rules, JSON validation, and raw-output retention.**
- [x] **Step 5: Implement dual-ASR reconciliation constrained to supported hypotheses and fixed Whisper timing.**
- [x] **Step 6: Implement optional visual facts separate from transcript speech.**
- [x] **Step 7: Run contract suite; leave code uncommitted to protect pre-existing dirty workspace changes.**

### Task 5: Reference input, comparison CLI, and reports

**Files:**
- Create: `backend/experiments/accuracy_pipelines/reporting.py`
- Create: `backend/scripts/compare_pipelines.py`
- Create: `backend/tests/experiments/test_reporting.py`
- Create: `backend/tests/experiments/test_compare_pipelines.py`

**Interfaces:**
- Reference JSON accepts `{"source": "...", "translation": "..."}` or lists of strings for either field.
- CLI: `python -B scripts/compare_pipelines.py MEDIA --source zh --target vi --pipelines baseline,dual_asr_hymt --reference refs.json --glossary glossary.json --output-dir PATH --frame-interval 15`.
- Default outputs are per-pipeline JSON plus one Markdown table under `data/experiments/accuracy-pipelines/<run-id>/`.

- [x] **Step 1: Test CLI parsing, unknown ids, reference schema, partial failures, and no-reference labels.**
- [x] **Step 2: Run report/CLI tests red-first and verify green.**
- [x] **Step 3: Implement report rows with optional CER/chrF, alignment, empty outputs, models, and runtime.**
- [x] **Step 4: Run variants sequentially, save artifacts, continue after failures, and mark incomplete comparisons.**
- [x] **Step 5: Verify comparison tests; leave branch changes uncommitted to protect pre-existing edits.**

### Task 6: Regression loop documentation and full retest

**Files:**
- Modify: `backend/README.md`
- Create: `backend/experiments/accuracy_pipelines/README.md`
- Modify: regression fixtures under `backend/tests/experiments/` as failures are discovered.

- [x] **Step 1: Document usage, seven ids, references, model tags, and optional VLM installation.**
- [x] **Step 2: Run the focused experiment suite.**
- [x] **Step 3: Run the full backend suite and correct its README test-count baseline.**
- [x] **Step 4: Run real-media baseline, HY-MT, and Qwen7B; document unavailable SenseVoice/VLM and missing reference.**
- [x] **Step 5: Promote malformed batch/alignment and incomplete edit responses into regression tests and narrow fallbacks; rerun affected media and suites.**
- [x] **Step 6: Review diff. Avoid committing files that overlap pre-existing dirty user changes.**
