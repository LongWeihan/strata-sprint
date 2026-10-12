# Precision, without changing the reference

The target's IQ3_S weights, native tensor representation and FP16 KV are unchanged. This preserves the **existing quantized model**, not an unquantized Qwen reference. MTP remains the existing Q2_0 auxiliary representation with four draft tokens; the same upstream verifier checks drafts. Sampling and thinking configuration are copied from the input config.

## Three different questions

1. **Does the selected buffer profile change the measured first-step computation?** The 49 non-interleaved first-logit comparisons were byte-identical. All 70 selected-profile output-text hashes matched the corresponding baseline hashes.
2. **Is restoring a parked state equivalent to continuing the same state?** A separate run compared uninterrupted A→A with fresh A→unrelated B→restored A under identical settings. The initial answer, follow-up answer and captured first-logit vector were byte-identical; measured KL and maximum absolute difference were zero.
3. **Is a cached continuation identical to recomputing a whole prefix from scratch?** Not necessarily. In the 12 interleaved comparisons, baseline recomputed and Sprint reused state. Those first-logit vectors differed numerically (maximum KL about 0.000666), while top-1 choices and the final text matched. Their different histories prevent treating them as a byte-copy test.

The public data therefore reports **49/61** first-logit vectors byte-identical across the entire baseline/selected run and **61/61** top-1 choices identical, rather than claiming all scores are unchanged. The uninterrupted-session control is a separate, smaller experiment.

## What the tests do not establish

- First-step vectors and finite outputs do not cover every generated token, prompt, sampler seed or hardware stack.
- Matching the baseline is not the same as answering correctly. The original math checks hit a 512-token limit; these remain failures in the data. The larger-budget supplement is separately labelled.
- No claim is made about recovery of full-precision model quality, benchmark leaderboard scores or other quantizations.
- GPU/driver/compiler changes and future upstream releases require renewed validation.

## Audit the vectors on the measurement host

The pinned upstream diagnostic flag `STRATA_DUMP_FIRST_LOGITS` writes raw little-endian float32 score vectors. Run diagnostics on an isolated copy of the upstream config, outside Sprint's production profile (which rejects unvalidated `STRATA_*` kernel/diagnostic settings). Keep original vectors on the measurement host; they can become large.

```bash
python scripts/compare_logits.py reference.f32 candidate.f32
```

The comparison checks shape, finite masks, byte equality, top-1 equality, maximum absolute error and KL in float64. Files containing NaN or inconsistent finite masks are reported as invalid comparisons. The exported original records are [here](../benchmarks/pro6000-2026-10-12/validation-logits-summary.json); the separate cache control is [here](../benchmarks/pro6000-2026-10-12/cache-parity.json).
