# Accuracy-first pipeline experiments

These experiments are isolated from API routes, registry defaults, and the production pipeline. They run selected variants sequentially and release model resources between stages for an 8 GB VRAM card.

From `backend/`, run for example:

```powershell
.\.venv\Scripts\python.exe -B scripts/compare_pipelines.py path\to\clip.mp4 --source zh --target vi --pipelines baseline,sensevoice_opus,whisper_hymt,dual_asr_hymt
```

Available ids: `baseline`, `sensevoice_opus`, `whisper_hymt`, `whisper_hymt_qwen3b_edit`, `whisper_qwen7b`, `dual_asr_hymt`, `dual_asr_glossary_whisper_hymt`, `visual_context`, `whisper_vl_prompt`, `caption_ocr`, `qwen3_asr_hymt`, `qwen3_vl_asr_hymt`, and `whisper_large_v3_hymt`. The full Whisper variant uses `Systran/faster-whisper-large-v3` with `int8_float16`, beam size 5, and no prior-segment conditioning; it is separate from the app's `fw-large-v3-turbo` default. The Qwen3-ASR variants use the 0.6B model plus the 0.6B forced aligner; ASR and alignment are loaded sequentially. Set `QWEN3_ASR_RUNTIME_PATH`, `QWEN3_ASR_MODEL_PATH`, and `QWEN3_ASR_ALIGNER_PATH` to the isolated package directory and local model directories. They do not download models at runtime. The visual variant also requires `qwen3-vl:2b`; install it explicitly with `ollama pull qwen3-vl:2b`. The runner rejects audio-only media for visual pipelines.

`dual_asr_glossary_whisper_hymt` runs full Whisper large-v3 and SenseVoice on the extracted audio, asks Qwen2.5 3B for a topic/glossary using only their differing segments (up to 40), validates every proposed term against that evidence, then reruns Whisper with both `initial_prompt` and `hotwords`. A final guarded ASR selection may choose only the second Whisper or the aligned SenseVoice text; the HY-MT translation and editor continue using the user-supplied glossary. The report includes `CER pass 1` and `CER pass 2` when a source reference is supplied. The pipeline itself still uses ffmpeg audio extraction only; Demucs is not enabled in the runner. A separate A/B below tests a Demucs vocal stem before deciding whether it belongs in this pipeline. Models are loaded sequentially for the 8 GB VRAM target.

#### Dual-ASR glossary pilot (2026-10-14)

On `data/media/8f4b5304daf42569.mp4`, the first attempt injected a literal placeholder topic (`一句话`) despite returning no glossary terms. Its timed OCR-CER rose from 0.1446 (pass 1) to 0.3193 (pass 2); this is retained as a rejected experiment. After filtering placeholders, requiring two different spellings in the same ASR evidence window, and rejecting ambiguous one-to-many timestamp matches, the final run found no grounded term pair and skipped pass 2. On the same 93 OCR captions (OpenCC t2s, NFKC, punctuation/space removed, best substring CER within ±3 characters and ±2 seconds around each OCR midpoint): large-v3 baseline 0.1446, pass 1 0.1446, pass 2 skipped 0.1446, guarded output 0.1435. The 0.0011 absolute change is too small to claim an accuracy gain. This is a timestamp-favored OCR diagnostic, not gold-transcript corpus CER.

That run took 111.1 seconds across recorded pipeline stages (audio extraction excluded); the second Whisper pass and disagreement LLM review were skipped because no confidently aligned spelling pair remained. Translation post-edit was rejected by its guard (`segment ids/order changed`), so the original HY-MT text was preserved. In an earlier attempt the guard also caught a dropped negation. The per-run JSON retains stage timing, ASR variants, candidate evidence, glossary, and fallback reason for audit.

#### Demucs vocal-separation A/B (2026-10-14)

Demucs 4.0.1 `htdemucs` separated the existing 278.5-second WAV on the RTX 3070 8 GB; Whisper large-v3 was then rerun with the same beam-5/int8_float16 settings on `vocals.wav`. Scoring uses exactly the same 93 OCR captions, OpenCC t2s, and timed window/substrings as the glossary pilot. Raw audio scored timed mean CER 0.1446 (97 del / 27 sub / 0 ins); the vocal stem scored 0.3210 (180 del / 68 sub / 0 ins). Global mean CER rose from 0.1296 to 0.2571. Demucs substantially worsened this clip, so it should not be a default step here. Since best-substring matching can discard errors at phrase edges, the insertion count is specific to this retrieval diagnostic, not a full-transcript insertion rate.

#### OCR-reference audit (2026-10-15)

Reviewing the timed deletions found that 9 OCR observations near 243–269s were the persistent top-right `想想工作室 / bilibili` watermark, not spoken captions. They account for 93 deletions on the original 93-row diagnostic. Frame checks completed row 26 at 44.2–44.8s, removed an OCR-duplicated `给` in row 57 at 116.55s, removed an OCR-duplicated `泡` in row 64 at 133.5s, and corrected 孩→神 in row 82 at 220.27s. Row 27 (`儿`) is a timed deletion in the current raw large-v3 transcript; row 69 (`还是`) matches in that transcript. SenseVoice and user-reported ElevenLabs Scribe outputs support both spellings, but all are automated ASR; both rows remain unverified, not heard.

After excluding the 9 watermark observations and applying all four frame-supported OCR corrections, the reference has 84 usable captions (656 normalized characters). Re-scoring `20261014-whisper-large-v3/large_v3.json` gives raw-audio large-v3 timed mean per-caption CER 0.0453 (1 del / 25 sub / 0 ins; pooled CER 0.0396); Demucs vocals scores timed mean per-caption CER 0.2441 (97 del / 63 sub / 0 ins; pooled CER 0.2439). The corresponding global mean per-caption CER values are 0.0453 and 0.1862 (Demucs pooled CER 0.1860). Mean per-caption CER and pooled CER are distinct metrics and are labeled separately in the report. The unfiltered 93-caption score 0.1446 is not comparable with these v2 scores. Demucs remains substantially worse on timed caption retrieval after reference cleanup. Its row-26 CER is 1.0 both before (7/7) and after (15/15) completing the caption; its unchanged per-row CER explains why adding eight reference characters alone did not change the unrounded mean.

The frozen, provenance-labeled v2 reference is `backend/experiments/accuracy_pipelines/references/ocr-caption-reference-v2.json`; regenerate it with `python -B scripts/freeze_ocr_reference.py`. Its per-substitution category review, SHA-256, score artifacts, and one-clip limitation are documented in `backend/experiments/accuracy_pipelines/references/ocr-caption-reference-v2.md`. The 25 substitutions are OCR-mismatch candidates, not independently confirmed acoustic errors. Four OCR rows are corrected using frame evidence; model-supported rows 27 and 69 remain unverified. The freeze script records the nearest-rank P10 density scan and repeated-character frame audit. The density scan checks only its nine flagged rows; row 26's original OCR would not pass that threshold, so this is not a completeness guarantee.

Reproduce the score for any saved segment JSON (the result reports del/sub/ins, mean CER, and pooled CER separately):

```powershell
..venv\Scripts\python.exe -B scripts/score_caption_ocr.py ..\data\experiments\accuracy-pipelines\20261014-caption-ocr-observations\caption_ocr.json ..\data\experiments\accuracy-pipelines\20261014-demucs-ocr93\whisper_large_v3_vocals.json
```

Artifacts are in `data/experiments/accuracy-pipelines/20261014-demucs-ocr93/` (scores, separated stems, and the vocal-stem transcript). The scorer requires evaluation-only `opencc-python-reimplemented==0.1.7`; Demucs was installed into the local backend venv for this experiment and is not a production dependency.

```powershell
.\.venv\Scripts\python.exe -B scripts/compare_pipelines.py ..\data\media\8f4b5304daf42569.mp4 --source zh --target vi --pipelines whisper_large_v3_hymt,dual_asr_glossary_whisper_hymt --reference path\to\reference.json
```

To compare the full multilingual model against the existing turbo baseline on a clip:

```powershell
.\.venv\Scripts\python.exe -B scripts/compare_pipelines.py path\to\clip.mp4 --source zh --target vi --pipelines baseline,whisper_large_v3_hymt
```

Optional arguments include `--reference refs.json`, `--glossary glossary.json`, `--output-dir PATH`, `--frame-interval 15`, `--baseline-asr ENGINE_ID`, and `--baseline-mt ENGINE_ID`. A reference has both fields; either may be a string or ordered list of segment strings:

```json
{"source": ["source segment one", "source segment two"], "translation": ["translated segment one", "translated segment two"]}
```

Each run writes per-pipeline JSON (raw ASR, alternate/corrected ASR, raw MT, final MT, models and stage timings), `comparison.json`, and `comparison.md` under `data/experiments/accuracy-pipelines/`. Without a reference, CER/chrF remain unavailable; the report is for side-by-side manual review, not an accuracy claim.

Qwen3-ASR uses an isolated target directory to avoid upgrading the backend's pinned Transformers version. The tested runtime is `qwen-asr==0.0.6`, `transformers==4.57.6`, `tokenizers==0.22.2`, and `accelerate==1.12.0`; PyTorch CUDA is reused from the backend environment. The two local model directories are expected at `D:\models\hf\qwen3-asr\ASR-0.6B` and `D:\models\hf\qwen3-asr\ForcedAligner-0.6B` on this workstation.

`qwen3_vl_asr_hymt` crops the lower quarter of sampled frames before sending them to Qwen3-VL, so burned-in subtitle text cannot be copied as ASR context. It passes only extracted entities to Qwen3-ASR's native `context` input. Treat its output as an experiment: compare with `qwen3_asr_hymt` under the same audio and reference.

## Error analysis and retest loop

1. Compare the same media, languages, glossary, and reference across variants. Review raw and edited stages separately for ASR homophones/omissions, translation meaning/terminology, alignment, and invented content.
2. Reproduce a real failure as a small deterministic fixture with fake model clients. Record the input, expected output, and failing stage; never replace or discard the original raw output.
3. Add the narrowest rule or prompt correction that addresses the repeatable failure. ASR edits must select only evidence-supported hypotheses; translation edits must preserve ids, timestamps, numbers, negation, and approved terminology.
4. Run `python -m pytest tests/experiments -q`, then the full backend suite. Rerun affected media variants with the same reference and manually review changed segments.
5. Record metric and manual-review outcomes in the run notes. If no reference or real media is available, say so; synthetic examples validate contracts, not model accuracy.

Unit tests need no GPU, model weights, Ollama server, or network. The SenseVoice variant uses the existing adapter and local cache when available; missing dependencies/cache fail visibly.

## Gate for a decode candidate (dev split only)

The reference carries `metadata.evaluation_split`: a chronological half split, first 42 scoreable captions = dev (up to 96.09 s), last 42 = test (from 96.09 s). A decode candidate — prompt text, hotword list, beam width, temperature, batching, ROVER — may be carried to test **only when all three hold**:

1. **No content loss.** Full-clip segment count drops at most 5% versus its family baseline, measured on the whole clip rather than the dev window.
2. **The transcript actually changes.** Text inside the scored region must differ from the baseline. A byte-identical candidate is a no-op, not a pass: hotword `金线` left the transcript byte-identical and only split one segment (115 -> 116).
3. **The change is evidenced as a correction.** The changed characters must be shown to fix target terms by frame/OCR evidence or an independent timestamped second opinion — not merely be different.

Why each rule exists, all measured on the 278.5 s clip:

- `initial_prompt` and `hotwords` can silently delete 15-25% of the transcript. Prompt alone gave 87-97 segments (baseline 115), hotwords alone 98, both 82, while dev mean per-caption CER rose from 0.0526 to about 0.40 and `rep5` fell to zero. That is content loss, and a segment-count gate catches it while a CER-only gate understates the damage.
- `delta CER = 0` does **not** mean "nothing changed inside dev". Hotword `拉踩` changed `困扰` -> `苦恼` at 1.16-2.44 s and `乘` -> `成` at 9.66-11.02 s, both inside the dev span, and all 42 per-caption CERs stayed identical because those characters sit where the reference row is `...` or already counted as an error. Label that candidate **inconclusive**, not "pass".
- Damage depends on content, not prompt length: a single hotword (`汕头`) removed 17 segments in an earlier probe while `金线` and `拉踩` removed none. Every new hotword needs its own full-clip gate run.

Two measurement traps this gate depends on:

- **`rep5` (share of 5-grams that repeat) must be computed inside the scored region.** Clip-wide, turbo measures 0.189 against 0.002 for large-v3, but the entire difference is the 243.31-278.5 s tail (ending song plus watermark overlay): before 243.31 s both produce exactly 843 characters. The reference itself carries 0.0215 repeated 5-grams. A clip-wide `rep5` is a tail artifact here, not an over-generation measure.
- **Timed CER is sensitive to segment boundaries, so a batch-size comparison measures segmentation as much as decoding.** `batch_size=2` scored dev 0.0824 against 0.0854 for 4/8, yet the two transcripts differ by only 6 characters and only 12 of 102 segment boundaries agree. Do not cite a batch size as better on this metric.

Determinism, measured: two runs per batch size produced byte-identical transcripts, and an independent adapter run reproduced `b8` exactly (dev mean per-caption CER 0.085375). The paired bootstrap CIs here resample captions only; they do not include variance between runs.

## Workstation retest (2026-10-13)

The local 278.5-second clip `data/media/8f4b5304daf42569.mp4` produced 105 Whisper segments. No reference file was available, so these are contract/completeness results, not comparative accuracy claims.

- Baseline (`fw-large-v3-turbo` + OPUS-MT): completed with 105/105 source and translation segments.
- HY-MT batch runs exposed malformed JSON and incomplete batch alignment (25/30 items). The experiment runtime now retries malformed/alignment-failing translation batches one segment at a time and still validates every id and non-empty result. The rerun completed with 105/105 translations (about 89 seconds total).
- The first Qwen2.5 7B experiment incorrectly used the *post-editor* on raw Chinese source text; its mixed-language output was not a valid translation. After switching it to the existing translation adapter, the rerun still echoed Chinese on 98/105 segments. The QA gate now marks this as failed quality even though segment alignment is complete. Do not use that output as Vietnamese subtitles.
- HY-MT completed 105/105 segments after singleton retry, but its earlier raw output also contained untranslated Chinese. A full QA-scored rerun is required before treating it as usable.
- HY-MT + Qwen2.5 3B post-edit returned mismatched ids even on singleton retry; the pipeline rejects it. No partial output is presented as successful.
- The initial SenseVoice attempt could not be measured because `funasr` was missing. After installing/fixing the adapter, a follow-up Whisper-vs-SenseVoice comparison was run on the same clip; see `data/experiments/accuracy-pipelines/20261013-sensevoice-vs-whisper-rerun/` below.
- Qwen3-VL 2B and Qwen3-ASR 0.6B were later installed locally and tested; see the Qwen3 retest below.

The raw outputs and comparison reports are ignored local artifacts under `data/experiments/accuracy-pipelines/`; failures and retries are retained there for auditability. The current experiment has not delivered a usable accuracy improvement on this clip; the quality gate is useful precisely because it exposed that rather than certifying 105/105 structure as quality.

### Whisper vs SenseVoice retest

Both variants used OPUS-MT for Chinese-to-Vietnamese translation on the same 278.5-second clip, isolating the ASR choice. SenseVoice completed successfully. Whisper produced 105 aligned segments in 142.6 seconds (ASR 17.3s, translation 125.3s); SenseVoice produced 61 aligned segments in 22.7 seconds (ASR 8.4s, translation 14.3s). SenseVoice ASR was about 2.1x faster; end-to-end time was about 6.3x lower, largely because its longer segments reduced translation calls. That is a throughput result, not evidence of better recognition or translation.

No human reference transcript/translation was supplied, so CER/chrF could not be calculated. Both outputs contain clear recognition/translation errors in the manually inspected sample; the SenseVoice output also has garbled Chinese near the tail, while Whisper switches to unrelated French there. Structural alignment was 100% for both, which does not mean semantic quality passed. The generated comparison marks a combined 64 QA issues (61 Whisper, 3 SenseVoice), mostly subtitle length/readability checks. See `comparison.md` and the per-pipeline JSON files in the run directory for raw ASR, translations, and timings. Treat SenseVoice as working and faster on this clip, but not yet proven more accurate or production-ready.

### Qwen3-ASR and visual-context retest

Qwen3-ASR 0.6B plus Qwen3-ForcedAligner 0.6B ran on the same RTX 3070 8GB clip. To stay within VRAM, ASR and aligner load sequentially. With `max_new_tokens=4096`, ASR took about 213 seconds and translation about 54 seconds; the no-context pipeline completed in 268 seconds. The Qwen3-VL 2B variant took 50 seconds for context extraction, 208 seconds for ASR/alignment, and 55 seconds for translation (317 seconds total). Both had 100% structural alignment and zero empty segments, but QA flagged 50 and 51 subtitle-readability issues respectively. These structural checks are not accuracy scores.

Three burned-in Chinese caption phrases were independently checked against their frames and compared at 14.7s, 36.0s, and 216.5s. For each anchor, local CER is the minimum character error rate among substrings found in a ±3 second transcript window (a deliberately local retrieval score, not corpus CER; it is optimistic and only n=3): Whisper turbo 0.159, Qwen3 without visual context 0.198, Qwen3 with Qwen3-VL context 0.198, and SenseVoice 0.619 with the old interpolated timestamps. After fixing SenseVoice to use its per-character timestamp output, its mean local anchor CER was 0.111. Qwen3-VL identified only `想想工作室` and `bilibili` from subtitle-masked frames; the ASR hypotheses at these anchors were identical with and without that context. No result supports an overall CER claim or translation-quality ranking without complete human references.

Qwen3 returned the Chinese speech through approximately 236.6s, while the remaining Whisper output is French song lyrics. That is consistent with a language switch outside the forced-Chinese test, not evidence that 4096 tokens fixed the entire 278.5s clip. Raw outputs and per-stage timings are in `data/experiments/accuracy-pipelines/20261014-qwen3-asr-context-4096/`; the earlier 2048-token run is retained in `20261014-qwen3-asr-context/`.

An OpenCC `t2s`-normalized diagnostic (`opencc-python-reimplemented==0.1.7`, evaluation environment only) compared the same 84 readable Chinese OCR captions across all ASR variants. Global/timed phrase CER was 0.0696/0.0696 for Whisper turbo, 0.0490/0.0490 for full Whisper large-v3 beam 5, 0.0806/0.0857 for SenseVoice after the timestamp fix, 0.2190/0.2378 for Qwen3, and 0.2246/0.2434 for Qwen3+VL. The earlier SenseVoice timed value 0.8469 was a timestamp-handling bug: VAD and `merge_vad=True` were already enabled, but the adapter collapsed FunASR's character timestamps into one span and then split it proportionally by text length. The adapter now groups by sentence punctuation and carries character timestamps through `normalize()` without exposing them as word timestamps. Native `sentence_timestamp=True` was also tried, but FunASR 1.2.6 throws a punctuation/timestamp length mismatch on this clip even with `ct-punc`.

All these OCR figures are optimistic retrieval diagnostics, not standard corpus CER: the 84 references are partially verified OCR strings, each score finds a best substring within ±3 characters, and their timestamps come from Whisper midpoint frames (so Whisper is timing-favored). A human gold transcript remains necessary for a production decision. Full per-run rows are in `data/experiments/accuracy-pipelines/20261014-whisper-large-v3/opencc_timed_global_comparison.json`.

### Full Whisper large-v3 retest

To try a non-LLM route, the same 278.5-second clip was decoded with full `Systran/faster-whisper-large-v3` on the RTX 3070 8GB using `int8_float16`. In a same-process ASR-only comparison that includes model loading and transcription but excludes audio extraction, turbo took 12.32s, full large-v3 beam 5 took 38.35s, and the corrected SenseVoice adapter took 8.56s. Large-v3 achieved OpenCC-normalized global/timed CER 0.0490/0.0490 versus 0.0696/0.0696 for turbo; its three manually checked caption anchors all had local CER 0.000.

Decoding checks found beam size 10 gave the same CER as beam 5 but took longer; `condition_on_previous_text=True` gave slightly worse CER. The experiment therefore keeps beam 5 and no prior-segment conditioning. The comparison runner exposes it as `whisper_large_v3_hymt`; the application's default remains unchanged until a complete human-reviewed Chinese transcript and Vietnamese translation confirm the gain. Raw hypotheses and scores are in `data/experiments/accuracy-pipelines/20261014-whisper-large-v3/`.

### SenseVoice as a second opinion

Re-bucketing SenseVoice's character-timestamped text onto Whisper large-v3 segment boundaries produced timed CER 0.1063, worse than SenseVoice's own corrected sentence grouping (0.0857). On the 84 OCR windows at a permissive CER ≤0.2, Whisper matched 78 captions, SenseVoice matched 75; both matched 73, Whisper alone 5, and SenseVoice alone 2. Comparing hypotheses in matching time windows flagged 14 of 100 comparable Whisper segments at CER >0.35. That supports using SenseVoice disagreement as a review cue, not automatically replacing Whisper text or fusing both outputs. This diagnostic is also Whisper-time-biased. See `sensevoice_whisper_combination.json` in the run directory.
