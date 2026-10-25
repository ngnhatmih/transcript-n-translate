# OCR caption reference v2 — error analysis (2026-10-16)

> **Superseded as canonical identity.** The current canonical file is
> `ocr-caption-reference-v4.json` (dataset `ocr-caption-reference-v2`, version 4,
> SHA-256 `fa35ddb2718bf897a97b3711ce8c3cc04ce113ad259d418928200c839a7909ad`).
> It differs from this v2 canonical freeze (SHA-256
> `9f5b4f3aa749bfaac1074b12d2eed1d1f68237df49f68781d723f3bdc8721a07`) only by
> the v3 version bump and the v4 frozen chronological 42/42 dev/test split; caption
> text and scoring protocol are unchanged.

## Frozen reference

`ocr-caption-reference-v2.json` is generated from the saved caption observations by `backend/scripts/freeze_ocr_reference.py`. It includes 84 scoreable observations and preserves the source OCR string and an evidence label on every included row. Nine fixed channel-watermark observations and twelve rows below the scorer's minimum length are retained separately in `excluded_observations` with exclusion reasons. The minimum is **4 characters after NFKC normalization and removal of Unicode punctuation and whitespace**; this same predeclared rule is applied to every OCR observation, independent of ASR output.

Four reference strings are completed from frame evidence, with source OCR preserved: row 26 (`一定可以把成本` → `一定可以把成本压在2,000以内`) uses successive subtitle states at 44.2s and 44.8s; row 57 (`交给给我们您放心` → `交给我们您放心`) removes a duplicated OCR `给` seen at 116.55s; row 64 (`还会吐泡泡泡` → `还会吐泡泡`) removes a duplicated OCR `泡` seen at 133.5s; row 82 (`所以为什么是榕树女孩啊` → `所以为什么是榕树女神啊`) corrects 孩 to 神 from the frame at 220.27s. These are frame-based subtitle readings, not ASR-derived edits.

Rows 27 (45.79–47.17s, `你直接卖字儿多少钱`) and 69 (181.43–183.01s, `还是卷起来了`) remain `verification_status: unverified`; ASR agreement is not reference evidence. In the currently scored raw large-v3 transcript, row 27 omits `儿`, while row 69 contains `还是`. SenseVoice and the user-reported ElevenLabs Scribe outputs contain both candidates, but this is automated-model corroboration, not listening evidence. The user reports an opening `[音效声]` overlapping the 181.4s utterance; that is a plausible interference note, not independently verified here. Three-second review clips centered on both points (±1.5s) are available locally as `data/experiments/accuracy-pipelines/20261015-ocr-reference-v2/review_45.8s.wav` and `review_181.4s.wav`.

Reference SHA-256: `9f5b4f3aa749bfaac1074b12d2eed1d1f68237df49f68781d723f3bdc8721a07`.

## Low-density OCR frame audit

Across the 84 included captions, OCR density is normalized characters per caption duration. The 10th-percentile cutoff uses the nearest-rank rule (`ceil(0.10 × 84)`), flagging values **≤ 2.941176 characters/second**. The nine flagged rows, listed by density, were inspected at `start + 0.05s`, midpoint, and `end − 0.05s` (27 frames total):

| Row | OCR chars / duration | chars/s |
| ---: | ---: | ---: |
| 43 | 8 / 4.76s | 1.681 |
| 68 | 6 / 2.88s | 2.083 |
| 3 | 5 / 2.36s | 2.119 |
| 5 | 10 / 4.08s | 2.451 |
| 78 | 6 / 2.38s | 2.521 |
| 38 | 5 / 1.98s | 2.525 |
| 47 | 6 / 2.26s | 2.655 |
| 56 | 6 / 2.20s | 2.727 |
| 48 | 6 / 2.04s | 2.941 |

For all nine, the midpoint frame visibly matched the original OCR. Start/end samples showed neighboring caption states at transitions; no truncation was found, so their reference strings were left unchanged. Each row records the three sample times and this result in its `frame_audit`/`evidence_detail` fields. This supports only the statement that **the nine lowest-density rows were not visibly cut in the reviewed frames**; it does not prove that the other 75 rows are complete or OCR-error-free. As a sensitivity check, row 26's original OCR (`一定可以把成本`) has density **4.217 chars/s**, above the same P10 cutoff (**2.941 chars/s**), so the density heuristic would not have flagged the actual truncation. This demonstrates a limitation, not a reason to discard the audit.

A separate scan of all 84 `source_ocr` strings flagged each consecutive repeated-character run of length ≥2 (NFKC, punctuation/whitespace removed). All 11 candidate rows (13, 14, 24, 25, 40, 49, 51, 57, 64, 65, 79) were checked at a caption frame. Numeric repetitions (`2,000`, `187,712`, `100`) and lexical reduplications (`画画`, `处处`, `指指点点`, `角角落落`) matched the visible subtitle. Rows 57 and 64 had OCR-only extra repeated characters and were corrected as described above. The individual checks and frame times are recorded in the JSON. Row 82 was independently frame-checked because of the 孩/神 discrepancy.

## Reproduced scores

Scoring protocol is unchanged: OpenCC t2s + NFKC, remove punctuation/whitespace, compare each caption against the best substring from ASR segments intersecting its midpoint ±2s, with substring length tolerance ±3 characters.

| Variant | References | Timed mean per-caption CER | Timed del/sub/ins | Global mean per-caption CER |
| --- | ---: | ---: | ---: | ---: |
| Whisper large-v3, raw audio | 84 | 0.0453 | 1 / 25 / 0 | 0.0453 |
| Whisper large-v3, Demucs vocals | 84 | 0.2441 | 97 / 63 / 0 | 0.1862 |

The two CER columns are means over 84 per-caption CER values; they are not pooled CER. For the current v2 scores, pooled CER is timed/global **26/656 = 0.0396** for raw audio and timed **160/656 = 0.2439** (global **122/656 = 0.1860**) for Demucs. The current scored raw hypothesis is `data/experiments/accuracy-pipelines/20261014-whisper-large-v3/large_v3.json`; the Demucs hypothesis is `data/experiments/accuracy-pipelines/20261014-demucs-ocr93/whisper_large_v3_vocals.json`.

These are timestamp-favored OCR retrieval diagnostics, not corpus CER against a human transcript. Four reference strings were completed using frame evidence; the remaining original-OCR rows are not independently confirmed spoken words.

Demucs produced 97 timed deletions, but this does **not** by itself establish that it erased 97 spoken characters or whole speech segments. The metric counts reference characters not recovered by the best local substring within ±2 seconds. On the concatenated full transcript, the same stem has only 5 deletions (and 117 substitutions), so most of the timed deletion excess is local-retrieval failure: possible timestamp/segmentation displacement, omitted local speech, or both. Relative to the old reference, timed deletions rose from 89 to 97, exactly the eight newly frame-verified characters in row 26 that the Demucs local window failed to retrieve. For row 26, Demucs has CER 7/7 = 1.0 under the old string and 15/15 = 1.0 under the completed string; hence its per-caption CER and the unrounded mean remain unchanged from that eight-character extension alone. Later frame corrections in rows 57 and 82 change the overall mean slightly. The aggregate scores cannot distinguish signal suppression from timing displacement. Demucs remains substantially worse on this clip's timed caption retrieval score.

## Deletion candidates and score reconciliation

Under the currently scored raw large-v3 transcript, row 27 contributes one timed deletion (`儿`); row 69 (`还是`) matches and contributes no deletion. The current timed score is 26 errors / 656 reference characters (pooled 0.0396; mean per-caption CER 0.0453). No counterfactual reference edits are applied.

Caption-level comparison found a plausible source for the two-deletion discrepancy: `large_v3.json` (`condition_on_previous_text: false`) has a deletion only at row 27, while the saved beam-5 `condition_on_previous_text: true` variant has deletions at rows 27, 65, and 79. Rows 65 and 79 could explain the count difference if that variant was used for the earlier report; the archived artifacts do not prove that it was. This is an ASR artifact/configuration difference, not completion of row 26 or the OCR edits. The historical 0.0514 / 3-del / 27-sub result still does not reproduce exactly: re-scoring the saved `prev=True` variant against the current reference gives timed mean CER 0.0478 with 3 del / 26 sub. The original hypothesis used for 0.0514 is not archived, so retain that score as unreconciled and do not compare it as if it were the same run.

## The 25 timed substitution operations

The categories below classify the *kind of mismatch against OCR*, not confirmed acoustic errors. One caption can contribute multiple character substitutions. Counts add to the current scorer's 25 substitutions.

| Candidate class | Count | Caption rows / examples |
| --- | ---: | --- |
| Proper names and artwork title | 7 | 12 `小儿放纸鸢图` / `小二放指缘图` (3); 53 `烟台山` / `燕台山` (1); 77 `曹磊` / `草垒` (2); 90 `烟台山` / `阴台山` (1) |
| Domain-specific terms and phrases | 5 | 20 `螺钿` / `螺垫` plus `人` / `个` (2); 21 `金线` / `经线` (1); 41 `拉踩` / `拉采` (1); 50 `看展` / `看讲` (1) |
| Symbols, quantities, and spoken-vs-written form | 5 | 6 `（+宽）x系数` / `加宽乘系数` (2); 13 `一平尺2,000` / `一瓶是2000` (2); 24 `不算路费2,000` / `不到路费2000` (1) |
| General lexical, particle, or context ambiguity | 8 | 11 `啊` / `这` (1); 25 `做` / `多` (1); 57 `交给` / `的教过` (2); 60 `串` / `场` (1); 64 `吐` / `捅` (1); 75 `嘛` / `吗` (1); 88 `哎` / `喂` (1) |

Interpretation: proper-name/title mismatches are the largest single *specific* class (7/25), while broad lexical/context ambiguity accounts for 8/25. The data does not support claiming that homophones alone dominate; several items may be OCR wording, subtitle-vs-speech differences, local timing/alignment, or ambiguous reference text. Simplified/traditional variants contribute zero after OpenCC t2s normalization.

Frame review showed that both earlier candidates involved OCR errors, but with different scoring effects: row 57 had an extra `给`, so its substitution count fell from 3 to 2 and one residual substitution remains in the current table; row 82 misread `神` as `孩`, and correcting it removed that row's substitution entirely. Row 82 therefore no longer appears in the substitution table.

## Audit changelog (2026-10-16)

Corrected the substitution heading and class proportions to 25 total (7/25 proper-name/title; 8/25 general lexical/context); corrected the row-69 description to match the currently scored transcript; documented the saved-variant caption-level deletion difference; clarified that row 57 retains one fewer substitution while row 82's substitution is removed; and recorded the corrected Demucs explanation (row 26 CER remains 1.0 before/after completion). These report-only edits do not change the frozen JSON or its SHA-256.

## Demucs follow-up availability

The repository's local media inventory contains only `data/media/8f4b5304daf42569.mp4` and its extracted WAV. There is no second unwatermarked clip available here, so a cross-clip Demucs conclusion cannot be measured yet. On this one clip, Demucs remains decisively worse even after removing watermark rows. To test generality, add a second clip with a human-checked transcript/reference and run both raw and Demucs audio using the same ASR settings and scoring protocol.
