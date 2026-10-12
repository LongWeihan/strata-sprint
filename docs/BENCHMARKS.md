# Measurements you can inspect

Measured on 2026-10-12: RTX PRO 6000 Blackwell Server Edition, 97,887 MiB reported VRAM, 20 vCPUs, 160 GiB RAM, Linux. The GPU host happened to be a Molab notebook; every number below comes from direct loopback HTTP to the engine. No desktop gateway or notebook execution round trip is included in the timing. Sprint itself does not use that platform.

Both arms use Strata 0.1.43 at `7695859aa13afb248bdb4d36f9b2e95707db079d`, the same SC117 IQ3_S files, native pack, Q2_0 MTP, FP16 KV and 131072-token capacity. The baseline already has GPU-resident experts; Sprint changes buffer borrowing and enables upstream's host-memory conversation cache.

## What is compared

The baseline's full engine arguments are in [`baseline.example.json`](../profiles/baseline.example.json), with machine paths replaced by portable paths. Original arguments include `--expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5 --resident-budget-gib 8 --pool-workers 3 --pcie-frac 0`. It has no conversation parking enabled.

The selected full profile changes only:

```text
--prefill 8192
--no-prefill-borrow
--conversation-cache-mib 16384
--conversation-cache-slots 4
--conversation-cache-min-tokens 2048
--conversation-cache-min-free-mib 16384
--memory-limit-mib 163840
```

No extra kernel tuning environment variables are enabled. This is a comparison with that recorded baseline, not a blanket comparison with the best possible tuning of Strata. Strata with these same arguments is the same computation; the optimized mechanism is upstream's work.

## Protocol and repetitions

- **Short sweep:** 54 recorded cases across baseline/repeat and candidate configurations. Code, reasoning and prose are separated because longer speculative windows helped some tasks and hurt others.
- **Long-input sweep:** 70 recorded cases. Two repetitions at approximately 4K, 32K and 123K tokens per variant, plus warm follow-ups. The isolated dedicated-buffer arm has conversation parking disabled.
- **Fusion/sampling sweep:** 45 recorded cases. Kernel fusions, coupled sampling and Gumbel sampling were evaluated separately. Instrumented profiler throughput is not used as normal throughput.
- **Comprehensive validation:** four configurations × 70 records = 280. Nine short tasks × three trials, three decode tasks × three trials, three context tiers × three trials, one warm follow-up and twelve short-task/long-conversation return pairs. The third short-task trial uses sampling; the other short trials are greedy.

Together these four sweeps contain **449 records**. Warm-up requests and separate numerical-control experiments are additional requests, not added to this headline count.

The full validation executes in a fixed order. Repeated context sizes can inherit a parking cost from a previous larger conversation. In that sequence, 4K TTFT rose from 1.526 to 2.865 seconds. This result is kept in the headline table. First parking costs roughly 0.3–3 seconds depending on history size; later incremental saves and restores are smaller. Cache capacity and eviction mean not every return will hit.

**TTFT** starts immediately before the HTTP request and ends on the first nonempty answer or reasoning delta. This includes prompt processing and state-copy overhead. **Decode token/s** is the server's reported `predicted_per_second`, not total request throughput. GPU memory/power samples are collected about once per second; peaks between samples may be missed. This is a modest same-host experiment, not a randomized multi-machine statistical study; small decode differences are treated as noise.

## Results and unsuccessful candidates

The [summary](../benchmarks/pro6000-2026-10-12/summary.json) is generated from the raw record sets. The [interactive page](https://longweihan.github.io/strata-sprint/) shows the full-profile comparison and the separate buffer-only comparison. `scripts/check_evidence.py` recomputes central claims in CI.

Rejected candidates remain in the data:

| Candidate | Reason it was not shipped |
| :--- | :--- |
| QFUSE | Changed logits; mean KL around 0.00164 in the diagnostic comparison |
| Expert regrouping / sorted MMQ | Some logits and one validation output changed |
| 16K prefill chunks | Faster long prefill, but changed long-input logits |
| Longer fixed MTP windows | Task-dependent gains and prose regressions |
| Extra PLE RAM / PDL | No consistent useful gain over baseline variation |
| CPU affinity, QDEDUP, LFUSE | No demonstrated material gain worth enabling |
| Coupled / Gumbel sampling | No consistent speed improvement |

Three math samples hit a 512-token output limit in both baseline and selected profiles. The comparison therefore checks identical truncated outputs, not successful mathematics. A separate 1536-token supplement finished all three, gave the correct answer and preserved each original 512-token prefix. See [precision limits](PRECISION.md).

## Reproduce the 70-record sequence

Use an otherwise idle GPU. Keep the same source, model files, sampling and fixtures. Run the two configurations sequentially; a fresh server per arm avoids importing an earlier arm's conversation cache.

1. Start the **baseline** through the pinned upstream server. Use your private baseline JSON and its Python environment:

```bash
# Working directory: the engine checkout
python -m serve.server --engine strata --config /absolute/path/baseline.json \
  --host 127.0.0.1 --port 8080
```

2. In another terminal, from Sprint's root:

```bash
strata-sprint bench --label baseline --url http://127.0.0.1:8080 \
  --output results/local/baseline.json --fixtures results/local/fixtures
```

3. Stop the baseline gracefully. Start Sprint with its corresponding derived config, then:

```bash
strata-sprint bench --label sprint --url http://127.0.0.1:8080 \
  --output results/local/sprint.json --fixtures results/local/fixtures
python scripts/compare_runs.py results/local/baseline.json results/local/sprint.json
```

Use `--model` if the server requires a different alias. Use `SPRINT_BENCH_API_KEY` if authenticated. The tool refuses to overwrite a result file and treats an incomplete stream as an unknown outcome; it does not replay it. The context fixtures are shared across arms. `--suite decode`, `context` and `resume` select smaller experiments; compare only identical suite settings. The `context` suite is not the historical two-repeat buffer-only sweep, so label a new experiment accordingly.

The current portable benchmark adapts the same prompts, seeds and 70-record sequence from the recorded experiment. Packaging and supervision were extracted later. Raw numerical vectors stay on the measurement machine; hashes, maximum differences and KL summaries are published here. Scratch path prefixes and process IDs were sanitized; [provenance.json](../benchmarks/pro6000-2026-10-12/provenance.json) records those transformations and file hashes.
