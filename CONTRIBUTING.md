# Contributing

Start with a reproducible workload and one clear change. For a new hardware profile, include the GPU, visible VRAM, CPU/RAM, OS, driver, CUDA/compiler, upstream commit, model revision, quantization, context size, sampler, prompt fixtures and exact argument diff.

Compare on the same hardware with a fresh engine per arm. Publish repeated timing records, regressions and memory costs. A cache-hit improvement should be labelled as a cache-hit improvement, and first-token latency should stay separate from decode throughput.

Changes to kernels, prefill grouping or precision need numerical controls and capability checks. Compare cache copy against an uninterrupted continuation; a cold recomputation is a different floating-point path. Do not change baseline settings to manufacture an advantage.

Run `python -m unittest discover -s tests -v` and `python scripts/check_evidence.py`. Linux CI exercises process-group recovery. Native upstream changes belong in a separately reviewed engine revision; retain attribution and its licenses. This first release intentionally keeps the upstream checkout clean.

Use synthetic fixtures. Never commit credentials, private conversation text, model weights, runtime state or raw request logs.
