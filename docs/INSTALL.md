# Install on the GPU host

The validated target is Linux, one RTX PRO 6000 Blackwell 96 GB, and **160 GiB or more of host RAM**. The original run had 20 vCPUs. Other cards, smaller RAM allocations, alternate quantizations and simultaneous native sequences need their own validation.

This repository contains source and measurements. It does not contain model weights or a prebuilt CUDA binary. Keep the original Strata and model licenses with your installation.

## Reuse an existing installation

1. Clone this project with `--recurse-submodules` and install it with `python3 -m pip install -e '.[bench]'`. Use an existing Python environment if its dependencies are compatible.
2. Locate your working Strata config and its Python environment. The source must be at `7695859aa13afb248bdb4d36f9b2e95707db079d` with clean tracked files. The runtime checks this before starting.
3. Compare the native arguments with [`profiles/baseline.example.json`](../profiles/baseline.example.json). This first release accepts the exact tested target and engine controls. It rejects unvalidated model/precision/parallel settings instead of silently changing them.
4. Run `strata-sprint configure --base BASE.json --output SPRINT.json --ram-gib 160`. The base file is preserved. Relative asset paths are resolved using its `cwd`; the new file can live elsewhere.
5. Run `strata-sprint doctor`, then `strata-sprint serve`, with the engine source and its Python as shown in the README. Stop another server on the same port first. Model loading is reported by upstream's normal output and the supervisor status file.

The generated config retains sampling settings, reasoning settings and access keys. It removes unvalidated `STRATA_*` kernel switches from the config and launch environment. `STRATA_API_KEY` and `STRATA_ALLOWED_HOSTS` remain available for access control. Review the generated config locally; it may contain your private key.

## Build from source

Install a working NVIDIA driver and CUDA Toolkit with Blackwell `sm_120` support, a C++ compiler, Git, CMake and Ninja. The recorded build used CUDA 13 and architecture 120. These commands are for a normal Linux CUDA installation; use your installation's paths if the toolkit is elsewhere.

```bash
git clone --recurse-submodules https://github.com/LongWeihan/strata-sprint.git
cd strata-sprint
python3 -m pip install -e '.[bench]'
python3 -m pip install -r engine/requirements.txt

cmake -S engine -B engine/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=ON \
  -DSTRATA_BUILD_TESTS=OFF -DCMAKE_CUDA_ARCHITECTURES=120
cmake --build engine/build --target strata -j 4
```

Upstream CMake obtains its pinned llama.cpp / ggml dependency. The Python requirements belong to the pinned engine; do not replace their versions to match an unrelated environment. For platform-specific build questions, see [upstream installation](../engine/docs/INSTALL.md).

## Prepare the tested model

Obtain the two IQ3_S shards from [SC117's model repository](https://huggingface.co/SC117/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-GGUF/tree/eec4e10a2c29b440a2ae85591fa11569ce752963). File sizes, revision and SHA256 digests are in [`model-manifest.json`](../model-manifest.json). Download and verify them **on the GPU host**. Keep the shard filenames unchanged and next to one another. The two files total about 83.86 GB; packs, the MTP source and build products need additional space. Reserve at least 130 GB of free storage.

The commands below assume the shards are in `runtime/assets/models/` and run from the project root:

```bash
mkdir -p runtime/assets
python scripts/verify_model.py runtime/assets/models

# Native packing preserves the target's quantized tensors.
export STRATA_GGUF_PY="$PWD/engine/build/_deps/strata_llamacpp-src/gguf-py"
python engine/tools/iq_pack.py \
  --gguf runtime/assets/models/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-IQ3_S-00001-of-00002.gguf \
  --out runtime/assets/pack

# Upstream fetches its MTP source and constructs the same Q2_0 draft representation.
python engine/tools/mtp_fetch.py fetch --out runtime/assets/mtp
python engine/tools/mtp_pack.py --src runtime/assets/mtp --experts q2_0 \
  --out runtime/assets/mtp/mtp-q2_0.gguf
python engine/tools/mtp_rt.py --gguf runtime/assets/mtp/mtp-q2_0.gguf \
  --out runtime/assets/mtp/rt
cp engine/data/draft_vocab.bin runtime/assets/mtp/rt/draft_vocab.bin

strata-sprint configure --base profiles/baseline.example.json \
  --output runtime/sprint.json --ram-gib 160 --port 8080
strata-sprint doctor --config runtime/sprint.json --engine engine \
  --python "$(command -v python)"
strata-sprint serve --config runtime/sprint.json --engine engine \
  --python "$(command -v python)"
```

Use the same `STRATA_GGUF_PY` environment for any pack command that needs that reader; alternatively install the pinned checkout's `gguf-py` in the selected Python environment. Do not use `--compat-bf16` for this profile: it permits conversions beyond the recorded target path. A packing failure should be diagnosed, not bypassed by changing precision.

The generated example points its second-shard PLE table, tokenizer, native pack and MTP directory at these locations. If your paths differ, edit a private copy of the example before configuring. The original model and MTP source have their own licenses; this project's MIT license covers neither weights nor third-party components.

## Host RAM and exposed interfaces

`--ram-gib` is the actual RAM ceiling available to the engine, **not** how much memory you want the cache to consume. It must be at least 160 for this validated profile. The upstream cache also observes visible cgroup limits and available memory, but a container can hide its outer limit. Set the real allocation explicitly.

The default host is `127.0.0.1`. To expose upstream APIs on a private network, set the config's `host` and an `api_key` (or `STRATA_API_KEY`); use your normal authenticated TLS ingress for wider access. Sprint performs no request forwarding and stores no chat history of its own.
