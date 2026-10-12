"""Only the measured memory/scheduling knobs; model arithmetic is upstream's."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile

COMMIT = "7695859aa13afb248bdb4d36f9b2e95707db079d"
UPSTREAM_VERSION = "0.1.43"
MODEL = "Qwen3.8-Flash-Next-GSQ-RCO-abliterated-IQ3_S-00001-of-00002.gguf"
PROFILE = "pro6000-fp16-v1"
OPTIONS = {
    "--prefill": "8192",
    "--conversation-cache-mib": "16384",
    "--conversation-cache-slots": "4",
    "--conversation-cache-min-tokens": "2048",
    "--conversation-cache-min-free-mib": "16384",
    "--memory-limit-mib": "163840",
}
# Application access settings are not kernel tuning switches.
ACCESS_ENV = {"STRATA_API_KEY", "STRATA_ALLOWED_HOSTS"}
PATH_OPTIONS = {"--native", "--pack", "--ple-gguf", "--expert-profile", "--mtp"}
FIXED_OPTIONS = {"--kv": "fp16", "--spec": "4", "--max-context": "131072",
                 "--spec-min-p": "0.5", "--expert-cache": "auto",
                 "--resident-budget-gib": "8", "--pool-workers": "3", "--pcie-frac": "0"}


def option(args, key):
    indices = [i for i, v in enumerate(args) if v == key]
    if len(indices) != 1 or indices[0] + 1 >= len(args):
        raise ValueError(f"Expected exactly one {key} with a value")
    value = args[indices[0] + 1]
    if value.startswith("--"):
        raise ValueError(f"Missing value after {key}")
    return value


def validate_base(config):
    if not isinstance(config, dict):
        raise ValueError("Strata config must be a JSON object")
    env = config.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise ValueError("Config env must map string names to string values")
    args = config.get("args")
    if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
        raise ValueError("Config args must be a list of strings")
    if Path(option(args, "--native")).name != MODEL:
        raise ValueError("This release validates the SC117 IQ3_S target only; see docs/INSTALL.md")
    for key, expected in FIXED_OPTIONS.items():
        if option(args, key) != expected:
            raise ValueError(f"The measured profile requires {key} {expected}; no automatic precision changes")
    for key in PATH_OPTIONS:
        option(args, key)
    allowed = PATH_OPTIONS | set(FIXED_OPTIONS) | set(OPTIONS) | {"--no-prefill-borrow"}
    for arg in args:
        if arg.startswith("--") and arg not in allowed:
            raise ValueError(f"Unvalidated engine option: {arg}; use the recorded baseline example")
    for key in ("exe", "cwd", "tokenizer"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError(f"Missing {key} in the Strata configuration")
    if config.get("parallel", 1) != 1 or config.get("replicas", 1) != 1:
        raise ValueError("The measured profile uses one engine and one active sequence")


def clean_environment(env):
    return {k: v for k, v in env.items() if not k.startswith("STRATA_") or k in ACCESS_ENV}


def tune(config, base_dir, ram_gib=160):
    validate_base(config)
    if isinstance(ram_gib, bool) or not isinstance(ram_gib, int) or ram_gib < 160:
        raise ValueError("The validated profile requires at least 160 GiB of host RAM")
    out = copy.deepcopy(config)
    base_dir = Path(base_dir).resolve()
    def absolute(value, relative_to):
        p = Path(value).expanduser()
        return str((p if p.is_absolute() else relative_to / p).resolve())
    cwd = Path(absolute(out["cwd"], base_dir))
    out["cwd"] = str(cwd)
    out["exe"] = absolute(out["exe"], cwd)
    out["tokenizer"] = absolute(out["tokenizer"], cwd)
    if out.get("log"):
        out["log"] = absolute(out["log"], cwd)
    args = out["args"]
    for key in PATH_OPTIONS:
        index = args.index(key) + 1
        args[index] = absolute(args[index], cwd)
    # Remove every old occurrence, so a later duplicate cannot override the profile.
    cleaned = []
    i = 0
    while i < len(args):
        if args[i] in OPTIONS:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                raise ValueError(f"Missing value after {args[i]}")
            i += 2
        elif args[i] == "--no-prefill-borrow":
            i += 1
        else:
            cleaned.append(args[i]); i += 1
    for key, value in OPTIONS.items():
        cleaned += [key, str(ram_gib * 1024) if key == "--memory-limit-mib" else value]
    out["args"] = cleaned + ["--no-prefill-borrow"]
    out["env"] = clean_environment(out.get("env", {}))
    out["env"]["OMP_NUM_THREADS"] = "4"
    out.update(idle_unload_s=0, parallel=1)
    out.setdefault("host", "127.0.0.1")
    out.setdefault("port", 8080)
    out["sprint"] = {"profile": PROFILE, "upstream_commit": COMMIT, "ram_gib": ram_gib}
    return out


def validate_profile(config):
    validate_base(config)
    ram = config.get("sprint", {}).get("ram_gib")
    if not isinstance(ram, int) or isinstance(ram, bool) or ram < 160:
        raise ValueError("Missing validated Sprint memory limit; run configure")
    for key, value in OPTIONS.items():
        want = str(ram * 1024) if key == "--memory-limit-mib" else value
        if option(config["args"], key) != want:
            raise ValueError(f"Profile drift: {key}")
    if config["args"].count("--no-prefill-borrow") != 1:
        raise ValueError("Profile drift: dedicated prefill buffers are required")
    if clean_environment(config.get("env", {})) != config.get("env", {}):
        raise ValueError("Unvalidated STRATA_* kernel switch in config")
    if config.get("env", {}).get("OMP_NUM_THREADS") != "4":
        raise ValueError("Profile drift: OMP_NUM_THREADS must be 4")
    if config.get("idle_unload_s") != 0:
        raise ValueError("Sprint supervision requires idle_unload_s = 0")


def write_config(path, config):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".sprint-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(config, stream, indent=2); stream.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def source_check(root):
    def git(*args):
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20)
        if r.returncode:
            raise ValueError("Cannot verify the Strata checkout; initialize the pinned engine submodule")
        return r.stdout.strip()
    if git("rev-parse", "HEAD") != COMMIT:
        raise ValueError(f"The measured engine commit is {COMMIT}; this checkout differs")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Tracked Strata sources were changed; this release requires the pinned clean source")


def validate_access(config, environ):
    # Upstream reads the server's process environment, not cfg.env (which is
    # forwarded only to the native child), when authenticating HTTP requests.
    if "STRATA_API_KEY" in environ and not environ["STRATA_API_KEY"].strip():
        raise ValueError("STRATA_API_KEY is present but empty")
    value = environ.get("STRATA_API_KEY") or config.get("api_key")
    if isinstance(value, (list, tuple)):
        keys = [str(v).strip() for v in value]
        if not keys or any(not k for k in keys):
            raise ValueError("An API key list must contain nonempty keys")
    else:
        keys = [v.strip() for v in str(value or "").split(",") if v.strip()]
    if config.get("host", "127.0.0.1") not in {"localhost", "127.0.0.1", "::1"} and not keys:
        raise ValueError("Set an upstream API key before binding outside loopback")


def preflight(config, root, python):
    validate_profile(config)
    source_check(root)
    if Path(config["cwd"]).resolve() != Path(root).resolve():
        raise ValueError("Config cwd must be the verified Strata checkout")
    for value in [config["exe"], python, *[option(config["args"], k) for k in PATH_OPTIONS]]:
        if not Path(value).exists():
            raise ValueError(f"Required engine/model asset is missing: {value}")
    for name in ["vocab.json", "merges.txt", "token_type.json"]:
        if not (Path(config["tokenizer"]) / name).is_file():
            raise ValueError(f"Tokenizer asset missing: {name}")
    validate_access(config, os.environ)
    r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True, timeout=10)
    lines = r.stdout.strip().splitlines()
    if r.returncode or len(lines) != 1:
        raise ValueError("The validated profile requires one visible NVIDIA GPU")
    name, memory = lines[0].rsplit(",", 1)
    if "PRO 6000" not in name or "Blackwell" not in name or float(memory) < 90000:
        raise ValueError("The validated GPU is RTX PRO 6000 Blackwell 96 GB")
    limits = []
    for path in [Path("/sys/fs/cgroup/memory.max"), Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")]:
        try:
            value = int(path.read_text().strip())
            if 0 < value < 2**60:
                limits.append(value)
        except (OSError, ValueError):
            pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                limits.append(int(line.split()[1]) * 1024)
    except OSError:
        pass
    # Physical MemTotal excludes reserved kernel pages. Allow 2% accounting slack.
    if limits and min(limits) < config["sprint"]["ram_gib"] * 2**30 * .98:
        raise ValueError("Configured RAM cap exceeds visible host/container memory")
    return {"profile": PROFILE, "upstream_commit": COMMIT, "gpu": name.strip(),
            "gpu_memory_mib": int(float(memory)), "configured_ram_gib": config["sprint"]["ram_gib"]}
