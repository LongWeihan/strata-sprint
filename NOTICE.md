# Attribution and provenance

**Upstream engine:** Strata 0.1.43, by Niko1221 and the Strata contributors, MIT license. Repository: https://github.com/Niko1221/Strata. Pinned commit: `7695859aa13afb248bdb4d36f9b2e95707db079d`. The `engine/` submodule retains its source history and notices. `STRATA-LICENSE` is an unchanged copy of its license at that revision.

**Sprint additions:** PRO 6000 profile selection, standalone configuration/supervision tools, portable benchmark tooling, evidence exports, documentation and presentation. Copyright 2026 LongWeihan and the Strata Sprint contributors, MIT license. No custom CUDA-kernel speedup is claimed by this release. The dedicated buffers and exact-state cache are upstream Strata features.

**Models:** Qwen3.8-Flash-Next and its derivatives belong to the Qwen team and respective publishers. The measured IQ3_S files are published by SC117. No model weights are included in this repository. Consult each publisher's model card and license before obtaining weights.

**Other components:** Strata uses llama.cpp / ggml and other components under their respective notices; see upstream's `third_party/` and documentation. Keeping a source submodule does not replace those notices with Sprint's license.

**Measurements:** Raw timing/precision records were collected on 2026-10-12 using an authorized remote GPU. The standalone packaging followed those measurements; provider/client integration tests are intentionally excluded. The public exports remove process IDs and replace scratch path prefixes while keeping measurements, output hashes and failures intact. The raw-vector files and model weights remain on the original GPU host, not in Git history.
