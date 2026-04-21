from __future__ import annotations

import os
import signal
import subprocess
import time
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .bootstrap import PuppenclawInstaller
from .config import WrapperSettings, write_generated_puppenclaw_config
from .errors import DaemonProcessError, DaemonTimeoutError
from .models import DaemonRuntimeInfo, HealthStatus, InstallManifest, ManagedDaemonStatus
from .paths import default_pid_path, default_runtime_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PuppenclawManager:
    def __init__(
        self,
        settings: WrapperSettings,
        *,
        installer: PuppenclawInstaller | None = None,
        pid_path: Path | None = None,
        runtime_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.installer = installer or PuppenclawInstaller(settings)
        self.pid_path = (pid_path or default_pid_path()).expanduser().resolve()
        self.runtime_path = (runtime_path or default_runtime_path()).expanduser().resolve()
        self._process: subprocess.Popen[str] | None = None
        self._log_handle = None

    def install(self) -> InstallManifest:
        return self.installer.install()

    def write_config(self) -> Path:
        self.settings.ensure_directories()
        return write_generated_puppenclaw_config(self.settings)

    def start(self) -> ManagedDaemonStatus:
        current = self.status()
        if current.running and current.runtime is not None:
            return current

        manifest = self.install()
        config_path = self.write_config()
        self.settings.ensure_directories()

        log_path = self.settings.daemon.log_dir / "puppenclaw-daemon.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = log_path.open("a", encoding="utf-8")

        command = [
            *manifest.daemon_command,
            "start",
            "--host",
            self.settings.daemon.host,
            "--port",
            str(self.settings.daemon.port),
            "--data-dir",
            str(self.settings.daemon.data_dir),
            "--config",
            str(config_path),
        ]
        cwd = Path(manifest.source_path).resolve()
        if not cwd.is_dir():
            cwd = cwd.parent
        popen_kwargs = {
            "cwd": str(cwd),
            "stdout": self._log_handle,
            "stderr": subprocess.STDOUT,
            "text": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True

        try:
            self._process = subprocess.Popen(command, **popen_kwargs)
        except OSError as error:
            raise DaemonProcessError(f"Failed to start Puppenclaw daemon: {error}") from error

        runtime = DaemonRuntimeInfo(
            pid=self._process.pid,
            baseUrl=self.settings.daemon.base_url,
            dataDir=str(self.settings.daemon.data_dir),
            logPath=str(log_path),
            configPath=str(config_path),
            command=command,
            startedAt=_utc_now(),
        )
        self._write_runtime(runtime)
        self.pid_path.write_text(str(runtime.pid), encoding="utf-8")
        self.wait_until_ready()
        return ManagedDaemonStatus(
            running=True,
            healthy=True,
            runtime=runtime,
            installManifest=manifest,
        )

    def stop(self) -> ManagedDaemonStatus:
        current = self.status()
        if current.runtime is None:
            self._cleanup_runtime_files()
            return ManagedDaemonStatus(
                running=False,
                healthy=False,
                installManifest=current.install_manifest,
            )

        self._request_shutdown()
        if self._wait_for_owned_process(current.runtime.pid, self.settings.daemon.stop_timeout):
            self._cleanup_runtime_files()
            return ManagedDaemonStatus(
                running=False,
                healthy=False,
                installManifest=current.install_manifest,
            )

        deadline = time.monotonic() + self.settings.daemon.stop_timeout
        while time.monotonic() < deadline:
            if not _pid_exists(current.runtime.pid):
                self._cleanup_runtime_files()
                return ManagedDaemonStatus(
                    running=False,
                    healthy=False,
                    installManifest=current.install_manifest,
                )
            time.sleep(0.2)

        if _pid_exists(current.runtime.pid):
            with suppress(OSError):
                os.kill(current.runtime.pid, signal.SIGTERM)
            if self._wait_for_owned_process(current.runtime.pid, self.settings.daemon.stop_timeout):
                self._cleanup_runtime_files()
                return ManagedDaemonStatus(
                    running=False,
                    healthy=False,
                    installManifest=current.install_manifest,
                )

            deadline = time.monotonic() + self.settings.daemon.stop_timeout
            while time.monotonic() < deadline:
                if not _pid_exists(current.runtime.pid):
                    self._cleanup_runtime_files()
                    return ManagedDaemonStatus(
                        running=False,
                        healthy=False,
                        installManifest=current.install_manifest,
                    )
                time.sleep(0.2)

        if _pid_exists(current.runtime.pid):
            raise DaemonTimeoutError(
                f"Timed out stopping Puppenclaw daemon PID {current.runtime.pid}."
            )

        self._cleanup_runtime_files()
        return ManagedDaemonStatus(
            running=False,
            healthy=False,
            installManifest=current.install_manifest,
        )

    def status(self) -> ManagedDaemonStatus:
        manifest = self.installer.load_manifest()
        runtime = self._load_runtime()
        if runtime is None:
            return ManagedDaemonStatus(running=False, healthy=False, installManifest=manifest)

        if not _pid_exists(runtime.pid):
            self._cleanup_runtime_files()
            return ManagedDaemonStatus(running=False, healthy=False, installManifest=manifest)

        healthy = False
        with suppress(Exception):
            healthy = self.healthcheck().ok
        return ManagedDaemonStatus(
            running=True,
            healthy=healthy,
            runtime=runtime,
            installManifest=manifest,
        )

    def wait_until_ready(self) -> HealthStatus:
        deadline = time.monotonic() + self.settings.daemon.startup_timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                status = self.healthcheck()
                if status.ok:
                    return status
            except Exception as error:  # pragma: no cover - covered by timeout branch
                last_error = error
            time.sleep(0.25)
        raise DaemonTimeoutError(
            "Puppenclaw daemon did not become healthy within "
            f"{self.settings.daemon.startup_timeout:.1f}s."
            + (f" Last error: {last_error}" if last_error else "")
        )

    def healthcheck(self) -> HealthStatus:
        try:
            with httpx.Client(timeout=self.settings.daemon.request_timeout) as client:
                response = client.get(f"{self.settings.daemon.base_url}/health")
                response.raise_for_status()
                return HealthStatus.model_validate(response.json())
        except httpx.HTTPError as error:
            raise DaemonProcessError(f"Puppenclaw daemon health check failed: {error}") from error

    def _request_shutdown(self) -> None:
        with suppress(Exception):
            with httpx.Client(timeout=self.settings.daemon.request_timeout) as client:
                client.post(f"{self.settings.daemon.base_url}/shutdown")

    def _write_runtime(self, runtime: DaemonRuntimeInfo) -> None:
        self.runtime_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_path.write_text(
            runtime.model_dump_json(indent=2, by_alias=True),
            encoding="utf-8",
        )

    def _load_runtime(self) -> DaemonRuntimeInfo | None:
        if not self.runtime_path.exists():
            return None
        return DaemonRuntimeInfo.model_validate_json(self.runtime_path.read_text(encoding="utf-8"))

    def _cleanup_runtime_files(self) -> None:
        for path in (self.pid_path, self.runtime_path):
            with suppress(FileNotFoundError):
                path.unlink()
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None
        self._process = None

    def _wait_for_owned_process(self, pid: int, timeout: float) -> bool:
        if self._process is None or self._process.pid != pid:
            return False
        try:
            self._process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
