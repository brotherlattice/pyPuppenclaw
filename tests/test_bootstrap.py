from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pypuppenclaw.bootstrap import PuppenclawInstaller
from pypuppenclaw.config import SourceSettings, WrapperSettings


def test_checkout_install_builds_when_daemon_entry_is_missing(tmp_path: Path, monkeypatch) -> None:
    checkout = tmp_path / "puppenclaw"
    dist_daemon = checkout / "dist" / "daemon"
    checkout.mkdir()
    (checkout / "package.json").write_text(
        json.dumps({"name": "@puppenclaw/openclaw-plugin", "version": "0.1.0"}),
        encoding="utf-8",
    )
    settings = WrapperSettings(source=SourceSettings(kind="checkout", checkoutPath=checkout))
    installer = PuppenclawInstaller(settings, manifest_path=tmp_path / "manifest.json")

    monkeypatch.setattr(installer, "_require_command", lambda _name: None)
    monkeypatch.setattr(installer, "_verify_node_version", lambda: None)

    def fake_run(args: list[str], *, cwd: Path, check: bool = True, capture_output: bool = False):
        if args[-2:] == ["run", "build"]:
            dist_daemon.mkdir(parents=True, exist_ok=True)
            (dist_daemon / "cli.js").write_text("console.log('ok')\n", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(installer, "_run_command", fake_run)

    manifest = installer.install()

    assert manifest.source_kind == "checkout"
    assert manifest.package_name == "@puppenclaw/openclaw-plugin"
    assert manifest.daemon_command[0] == settings.source.node_command
    assert Path(manifest.daemon_command[1]).name == "cli.js"


def test_binary_install_uses_explicit_daemon_command(tmp_path: Path) -> None:
    settings = WrapperSettings(
        source=SourceSettings(kind="binary", daemonCommand=["puppenclaw-daemon"]),
    )
    installer = PuppenclawInstaller(settings, manifest_path=tmp_path / "manifest.json")

    manifest = installer.install()

    assert manifest.source_kind == "binary"
    assert manifest.daemon_command == ["puppenclaw-daemon"]
