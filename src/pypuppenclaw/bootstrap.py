from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ._io import atomic_write_text
from .config import WrapperSettings, ensure_checkout_path
from .errors import DependencyError, InstallationError
from .models import InstallManifest
from .paths import default_install_manifest_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PuppenclawInstaller:
    """Resolve or build the local Puppenclaw daemon and persist its install manifest."""

    def __init__(
        self,
        settings: WrapperSettings,
        *,
        manifest_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.manifest_path = (
            (manifest_path or default_install_manifest_path()).expanduser().resolve()
        )

    def install(self) -> InstallManifest:
        self.settings.ensure_directories()
        if self.settings.source.kind == "binary":
            manifest = self._resolve_binary_installation()
        else:
            manifest = self._install_from_checkout()
        self._write_manifest(manifest)
        return manifest

    def load_manifest(self) -> InstallManifest | None:
        if not self.manifest_path.exists():
            return None
        return InstallManifest.model_validate_json(self.manifest_path.read_text(encoding="utf-8"))

    def _resolve_binary_installation(self) -> InstallManifest:
        command = self.settings.source.daemon_command
        if command is None:
            resolved = shutil.which("puppenclaw-daemon")
            if resolved is None:
                raise DependencyError(
                    "Binary source mode requires source.daemonCommand or a "
                    "puppenclaw-daemon binary on PATH."
                )
            command = [resolved]
        return InstallManifest(
            sourceKind="binary",
            sourcePath=str(Path.cwd()),
            daemonCommand=command,
            packageName="@puppenclaw/openclaw-plugin",
            installedAt=_utc_now(),
        )

    def _install_from_checkout(self) -> InstallManifest:
        checkout = ensure_checkout_path(self.settings)
        package_json_path = checkout / "package.json"
        if not package_json_path.exists():
            raise InstallationError(f"Missing package.json in Puppenclaw checkout: {checkout}")

        self._require_command(self.settings.source.node_command)
        self._require_command(self.settings.source.npm_command)
        self._verify_node_version()

        package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
        daemon_entry = checkout / "dist" / "daemon" / "cli.js"
        if not daemon_entry.exists():
            self._run_command(
                [self.settings.source.npm_command, *self.settings.source.install_args],
                cwd=checkout,
            )
            self._run_command(
                [self.settings.source.npm_command, *self.settings.source.build_args],
                cwd=checkout,
            )

        if not daemon_entry.exists():
            raise InstallationError(
                f"Puppenclaw build did not produce daemon entry: {daemon_entry}"
            )

        return InstallManifest(
            sourceKind="checkout",
            sourcePath=str(checkout),
            daemonCommand=[self.settings.source.node_command, str(daemon_entry)],
            packageName=package_json.get("name"),
            version=package_json.get("version"),
            installedAt=_utc_now(),
        )

    def _require_command(self, executable: str) -> None:
        if shutil.which(executable) is None:
            raise DependencyError(f"Required executable not found on PATH: {executable}")

    def _verify_node_version(self) -> None:
        result = self._run_command(
            [self.settings.source.node_command, "--version"],
            check=True,
            capture_output=True,
            cwd=Path.cwd(),
        )
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", output)
        if match is None:  # pragma: no cover
            raise DependencyError(f"Unable to parse Node version: {output or result.stdout!r}")
        major, minor = int(match.group(1)), int(match.group(2))
        if (major, minor) < (22, 13):
            raise DependencyError(
                f"Puppenclaw requires Node >=22.13, found {output or result.stdout.strip()}."
            )

    def _run_command(
        self,
        args: list[str],
        *,
        cwd: Path,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                args,
                cwd=str(cwd),
                check=check,
                text=True,
                capture_output=capture_output,
            )
        except subprocess.CalledProcessError as error:
            stderr = error.stderr.strip() if error.stderr else ""
            raise InstallationError(
                f"Command failed in {cwd}: {' '.join(args)}{': ' + stderr if stderr else ''}"
            ) from error
        except OSError as error:
            raise InstallationError(f"Failed to run command {' '.join(args)}: {error}") from error

    def _write_manifest(self, manifest: InstallManifest) -> None:
        atomic_write_text(
            self.manifest_path,
            manifest.model_dump_json(indent=2, by_alias=True),
        )
