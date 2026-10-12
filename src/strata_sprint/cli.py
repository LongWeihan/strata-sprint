import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .profile import preflight, tune, write_config


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "bench":
        from .benchmark import main as bench
        return bench(argv[1:])
    parser = argparse.ArgumentParser(description="Strata Sprint · PRO 6000 serving with measured defaults")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure", help="Derive a separate Sprint config from a working Strata config")
    configure.add_argument("--base", type=Path, required=True)
    configure.add_argument("--output", type=Path, required=True)
    configure.add_argument("--ram-gib", type=int, default=160, help="Actual container/host limit, at least 160")
    configure.add_argument("--port", type=int, default=8080)
    for name in ("doctor", "serve"):
        cmd = commands.add_parser(name, help="Validate runtime" if name == "doctor" else "Run and supervise the pinned upstream server")
        cmd.add_argument("--config", type=Path, required=True)
        cmd.add_argument("--engine", type=Path, required=True, help="Pinned Strata checkout")
        cmd.add_argument("--python", type=Path, help="Upstream Python with its dependencies; defaults to ENGINE/.venv/bin/python")
        if name == "serve":
            cmd.add_argument("--state-dir", type=Path, default=Path("runtime/sprint"))
            cmd.add_argument("--once", action="store_true", help="Do not restart a failed upstream server")
    args = parser.parse_args(argv)
    try:
        if args.command == "configure":
            if args.base.resolve() == args.output.resolve():
                raise ValueError("Use a separate output file; keep your baseline config for comparison")
            if not 1 <= args.port <= 65535:
                raise ValueError("Port must be between 1 and 65535")
            config = json.loads(args.base.read_text())
            config = tune(config, args.base.parent, args.ram_gib)
            config["port"] = args.port
            write_config(args.output, config)
            print(f"Wrote {args.output}; model weights and sampling settings are preserved.")
            return 0
        config = json.loads(args.config.read_text())
        root = args.engine.resolve()
        python = (args.python or root / ".venv/bin/python").resolve()
        report = preflight(config, root, python)
        if args.command == "doctor":
            print(json.dumps(report, indent=2)); return 0
        if sys.platform != "linux":
            raise ValueError("The supervised GPU runtime is validated on Linux")
        from .supervisor import run
        return run(args.config.resolve(), config, root, python, args.state_dir, args.once)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Sprint: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
