# Accuracy-First Backend Pipeline Experiments

Date: 2026-10-13

## Goal

Add an isolated, reproducible benchmark suite on `codex/accuracy-first-pipelines`
for comparing the current subtitle pipeline with several accuracy-focused ASR
and translation variants. Preserve the current application behavior; the
benchmark identifies candidates for a later production integration.

The user has an 8 GB VRAM GPU and currently has these Ollama models available:

- `hy-mt1.5-7b:q4_K_M`
- `qwen2.5:7b-instruct-q4_K_M`
- `qwen2.5:3b-instruct-q4_K_M`

The repo already implements Faster-Whisper, SenseVoice, OPUS-MT, Ollama MT, and
segment QA. The SenseVoice ModelScope cache is present at
`D:\models\hf\modelscope\models\iic--SenseVoiceSmall`. The optional visual
variant uses Ollama `qwen3-vl:2b` (Q4_K_M, about 1.9 GB); it is not currently
installed.

## Scope and non-goals

- Add runnable, separately selectable pipeline variants and one comparison
  command for the same input media.
- Reuse the existing ASR/MT adapters and segmentation/QA rules where possible.
- Support both automatic comparison against optional references and saved
  side-by-side outputs for manual review.
- Run all model stages sequentially and release models between stages. No
  pipeline may assume more than 8 GB VRAM or keep an ASR model resident while
  loading an Ollama model.
- Do not change application routes, default engines, persisted translation
  schema, or production behavior in this experiment branch.
- Do not claim an accuracy improvement until a reference set or human review
  supports it. This task creates the means to compare; it does not train models.

## Pipeline variants

Each variant has its own Python module with the same `run(context)` contract.
The comparison runner selects variants by stable id and invokes them on the
same media and language pair.

1. `baseline`: current configured ASR and MT engines, matching the existing
   app path as closely as possible.
2. `sensevoice_opus`: SenseVoice-Small + OPUS-MT, isolating the alternate ASR
   against the existing translation baseline.
3. `whisper_hymt`: Faster-Whisper large-v3-turbo + HY-MT1.5 7B, isolating the
   translation-model change.
4. `whisper_hymt_qwen3b_edit`: Whisper + HY-MT1.5, followed by Qwen2.5 3B
   contextual post-edit using adjacent segments and approved glossary terms.
5. `whisper_qwen7b`: Whisper + Qwen2.5 7B contextual translation, compared
   with the specialized translation model.
6. `dual_asr_hymt`: Whisper and SenseVoice run sequentially; Qwen2.5 3B
   reconciles hypotheses while preserving Whisper segment ids/timestamps; the
   result is translated by HY-MT1.5 and context-edited by Qwen2.5 3B.
7. `visual_context`: sample video frames; Qwen3-VL 2B extracts only visible
   entities, setting, and scene context; dual-ASR reconciliation receives that
   context before HY-MT translation and Qwen2.5 3B post-edit. Audio-only input
   is rejected for this variant with a clear explanation.

LLM correction must retain the raw hypotheses in the result artifact and
validate output ids/counts before accepting edits. It may correct words but must
not invent speech or alter timestamps. Translation post-edit must preserve
segment ids and return non-empty Vietnamese for every source segment. Failed
validation is recorded as a failed stage; it must not silently substitute a
partial result.

## Post-processing rules

Post-processing is explicit, deterministic where possible, and records both the
input and output of every change:

- Normalize whitespace and punctuation without changing lexical content before
  scoring. Keep original text in artifacts so normalization never destroys
  evidence.
- ASR correction uses the independent hypotheses, nearby transcript context,
  glossary, and confidence/suspect signals. It may resolve a homophone only
  when the acoustic hypotheses and context support the choice. If evidence is
  weak, preserve the best raw hypothesis and mark the segment for review.
- Visual context may disambiguate visible names, objects, or setting; it cannot
  add speech or override audio evidence. Store extracted visual facts separately
  from corrected transcript text.
- Translation editing must preserve meaning, negation, numbers, names, speaker
  attribution, and glossary terms. It may improve Vietnamese fluency and
  cross-segment coherence, but cannot add explanations absent from the source.
- Every transformation must preserve segment ids and timestamps. Validate exact
  id/order coverage, non-empty text, and glossary constraints after each stage;
  invalid output fails that stage and leaves the raw result intact.
- Apply existing subtitle readability/QA rules after translation. QA findings
  are reported and do not trigger an unbounded rewrite loop.

## Tests and error-improvement loop

Build a test suite around the shared contracts and post-processing rules using
fake ASR/MT/VLM clients; unit tests must not require CUDA, Ollama, network access,
or downloaded model weights. Cover malformed JSON, missing/duplicate/reordered
segment ids, empty output, forbidden timing changes, glossary violations,
unsupported ASR edits, visual facts inventing speech, cancellation/failure
cleanup, and model release between stages. Metric tests use tiny fixed
references with hand-computable CER/chrF values.

Run an explicit quality-improvement cycle on real media when available:

1. Run the selected variants on identical inputs and save raw stage outputs,
   metrics, model ids, prompts, and environment/runtime details.
2. Inspect failures and regressions by stage: ASR homophones/omissions,
   translation meaning/terminology, alignment, hallucination, and output format.
3. Convert each reproducible failure into a regression fixture and a narrow
   post-processing rule or prompt change. Do not add a rule based only on one
   anecdote if it could alter unrelated segments.
4. Rerun the full deterministic test suite and the affected real-media variants;
   compare metrics and manually review changed segments. Keep the previous raw
   output so regressions remain attributable.
5. Record the outcome and known limitations in the comparison report. Do not
   claim improvement when scores are unavailable or the reviewed sample regresses.

## Data flow and files

Add a focused package under `backend/experiments/accuracy_pipelines/`:

- One module per pipeline variant, each exposing `run(context)`.
- A small shared module for registry/model construction, Ollama calls, model
  release, frame sampling, schema validation, and metrics. Avoid copying the
  same adapter setup into every variant.
- `backend/scripts/compare_pipelines.py` parses media, language pair, selected
  pipeline ids, optional references, and output directory; runs each selected
  pipeline sequentially; writes JSON per pipeline plus a Markdown comparison.
- Artifacts default to `data/experiments/accuracy-pipelines/`, which is
  generated output and is not committed.

The runner reports per-stage duration, selected model ids, alignment/QA
failures, Ollama token counts where available, and peak CUDA memory where the
active runtime exposes it. It must retain raw ASR, corrected ASR, raw MT, and
post-edited MT so quality changes can be attributed to a stage.

## Evaluation

The optional reference JSON contains a source transcript and target
translation, each either as a string or as an ordered list of segment strings.
Compare concatenated source text with character error rate (CER), and target
translations with character n-gram chrF. The report also includes segment
alignment coverage and empty-output counts. Without references, emit the same
segment pairs in JSON/Markdown and clearly label quality metrics unavailable.

Automatic scores are diagnostic, not a production acceptance claim. When a
reference set is available, all variants must use the same media, source/target
language, glossary, and reference. Manual review remains available for names,
homophones, omitted meaning, and hallucinated context.

## 8 GB VRAM and model handling

- Never run multiple GPU models concurrently.
- Release Faster-Whisper and SenseVoice before loading Ollama models.
- Set Ollama `keep_alive` to zero after each model stage and verify the model is
  absent from the next stage's active memory before loading another large model.
- Keep LLM context and image sampling bounded. The visual pipeline samples
  frames at a configurable interval rather than sending every frame.
- The runner checks required model tags before starting a variant and reports
  the exact `ollama pull` command if one is missing. It does not download a
  model implicitly while a benchmark is running.
- Default visual model is `qwen3-vl:2b`; its official Ollama listing reports
  Q4_K_M at about 1.9 GB. The visual stage runs alone, so this does not add to
  the 7B translation model's VRAM use.

## Error handling and reproducibility

Each pipeline failure is captured with its failed stage and traceback summary;
the runner can continue with other selected pipelines and marks the comparison
incomplete. It never turns an empty transcript, missing translation, or
alignment mismatch into a successful run. Each result records timestamp,
input path metadata, language pair, pipeline id/version, model tags, prompt
versions, reference path/hash when supplied, and runtime measurements.

## Acceptance criteria

- All seven variants are independently selectable and produce the same result
  schema.
- A single invocation can run multiple variants sequentially on one media
  input and writes per-variant outputs plus a comparison report.
- Optional references produce CER and chrF; absent references produce manual
  comparison outputs without fabricated scores.
- Output shape, ids, timestamps, and non-empty translations are validated.
- Unit tests cover the post-processing and failure contracts without requiring
  model downloads; reproducible real-media errors can be promoted to regression
  fixtures and rerun after a rule change.
- The visual model is optional and missing-model errors explain how to enable
  that variant.
- The application API, existing registry defaults, and production pipeline
  remain unchanged.
