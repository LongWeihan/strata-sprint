"""Own one upstream server; recover confirmed exits, never replay API requests."""
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from .profile import clean_environment, write_config


def native_state(parent_pid, executable):
    """True = owned native process exists, False = absent, None = unobservable."""
    parent = Path(f"/proc/{parent_pid}/task/{parent_pid}/children")
    try:
        children = parent.read_text().split()
        for child in children:
            try:
                cmd = Path(f"/proc/{child}/cmdline").read_bytes().split(b"\0")
                state = Path(f"/proc/{child}/stat").read_text().rsplit(")", 1)[1].split()[0]
            except FileNotFoundError:
                continue
            if cmd and os.fsdecode(cmd[0]) == executable and state != "Z":
                return True
        return False
    except (OSError, ValueError, IndexError):
        return None


def health(port, host="127.0.0.1"):
    address = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    if ":" in address:
        address = f"[{address}]"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{address}:{port}/health", timeout=3) as response:
            return json.load(response).get("loaded")
    except (OSError, ValueError):
        return None


def should_restart(loaded, native, missing_streak, age, saw_native, startup_grace):
    # A slow/unknown/busy live engine is preserved. Missing /proc is not absence.
    missing = loaded is False and native is False
    streak = missing_streak + 1 if missing else 0
    return streak, streak >= 3 and (saw_native or age >= startup_grace)


def stop_owned(process):
    if getattr(process, "_sprint_cleaned", False):
        return
    process._sprint_cleaned = True
    # Clean the original group even when its wrapper has already exited: a
    # surviving CUDA child must not collide with the replacement engine.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait(); return
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            process.wait(); return
        time.sleep(.1)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def check_port(port, host):
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family) as sock:
        sock.bind((host, port))


def run(config_path, config, root, python, state_dir, once=False, interval=5, startup_grace=300):
    state_dir = Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stop = threading.Event()
    old = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        old[sig] = signal.signal(sig, lambda *_: stop.set())
    process = None
    try:
        with (state_dir / "server.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("A Sprint supervisor already owns this state directory") from None
            restarts = 0
            while not stop.is_set():
                check_port(int(config.get("port", 8080)), config.get("host", "127.0.0.1"))
                env = clean_environment(os.environ)
                env["OMP_NUM_THREADS"] = "4"
                process = subprocess.Popen(
                    [str(python), "-u", "-m", "serve.server", "--engine", "strata",
                     "--config", str(config_path), "--host", config.get("host", "127.0.0.1"),
                     "--port", str(config.get("port", 8080))],
                    cwd=root, env=env, start_new_session=True,
                )
                began = time.monotonic(); missing = 0; seen = False; healthy_since = None
                reason = "server_exited"
                while process.poll() is None and not stop.is_set():
                    loaded = health(int(config.get("port", 8080)), config.get("host", "127.0.0.1"))
                    native = native_state(process.pid, config["exe"])
                    seen = seen or native is True
                    age = time.monotonic() - began
                    missing, restart = should_restart(loaded, native, missing, age, seen, startup_grace)
                    if loaded is True:
                        healthy_since = healthy_since or time.monotonic()
                        if time.monotonic() - healthy_since >= 60:
                            restarts = 0
                    else:
                        healthy_since = None
                    write_config(state_dir / "status.json", {
                        "updated_at": time.time(), "loaded": loaded, "native_present": native,
                        "server_pid": process.pid, "restart_count_since_stable": restarts,
                        "state": "ready" if loaded is True else "loading_or_unavailable",
                        "profile": config["sprint"]["profile"],
                    })
                    if restart:
                        reason = "confirmed_native_exit"; stop_owned(process); break
                    stop.wait(interval)
                if stop.is_set():
                    stop_owned(process); break
                code = process.poll()
                stop_owned(process)
                if once or (code == 0 and reason != "confirmed_native_exit"):
                    return code or 0
                restarts += 1
                delay = min(60, 2 ** min(restarts, 6))
                write_config(state_dir / "status.json", {"updated_at": time.time(), "state": "backoff",
                    "reason": reason, "exit_code": code, "retry_seconds": delay,
                    "restart_count_since_stable": restarts})
                print(f"Sprint: {reason}; retrying in {delay}s. No request is replayed.", flush=True)
                stop.wait(delay)
    finally:
        if process is not None:
            stop_owned(process)
        for sig, handler in old.items():
            signal.signal(sig, handler)
    return 0
