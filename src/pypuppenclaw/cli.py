from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bootstrap import PuppenclawInstaller
from .config import load_settings, save_settings
from .daemon import PuppenclawManager
from .errors import PuppenclawError
from .paths import default_config_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pypuppenclaw", description="Manage a local Puppenclaw daemon"
    )
    parser.add_argument(
        "--config", type=Path, default=default_config_path(), help="Wrapper TOML config path"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local dependencies and resolved paths")
    subparsers.add_parser("install", help="Build or resolve Puppenclaw")
    subparsers.add_parser(
        "config-init", help="Write a default config TOML file if it does not exist"
    )
    subparsers.add_parser("start", help="Start the managed Puppenclaw daemon")
    subparsers.add_parser("stop", help="Stop the managed Puppenclaw daemon")
    subparsers.add_parser("status", help="Show current managed daemon status")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    installer = PuppenclawInstaller(settings)
    manager = PuppenclawManager(settings, installer=installer)

    try:
        if args.command == "config-init":
            path = args.config.expanduser().resolve()
            if not path.exists():
                save_settings(settings, path)
            print(str(path))
            return 0
        if args.command == "doctor":
            manifest = installer.load_manifest()
            report = {
                "config_path": str(args.config.expanduser().resolve()),
                "source_kind": settings.source.kind,
                "checkout_path": str(settings.source.resolve_checkout_path())
                if settings.source.kind == "checkout"
                else None,
                "daemon_base_url": settings.daemon.base_url,
                "state_dir": str(settings.daemon.state_dir),
                "data_dir": str(settings.daemon.data_dir),
                "log_dir": str(settings.daemon.log_dir),
                "install_manifest": manifest.model_dump(by_alias=True) if manifest else None,
            }
            print(json.dumps(report, indent=2))
            return 0
        if args.command == "install":
            manifest = installer.install()
            print(manifest.model_dump_json(indent=2, by_alias=True))
            return 0
        if args.command == "start":
            status = manager.start()
            print(status.model_dump_json(indent=2, by_alias=True))
            return 0
        if args.command == "stop":
            status = manager.stop()
            print(status.model_dump_json(indent=2, by_alias=True))
            return 0
        if args.command == "status":
            status = manager.status()
            print(status.model_dump_json(indent=2, by_alias=True))
            return 0
    except PuppenclawError as error:
        parser.exit(status=1, message=f"{error}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
