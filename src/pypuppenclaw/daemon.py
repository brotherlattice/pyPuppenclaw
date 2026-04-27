from __future__ import annotations

import errno
import os
import signal
import subprocess
import time
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

import httpx

from ._io import atomic_write_text
from .bootstrap import PuppenclawInstaller
from .config import WrapperSettings, write_generated_puppenclaw_config
from .errors import DaemonProcessError, DaemonTimeoutError
from .models import DaemonRuntimeInfo, HealthStatus, InstallManifest, ManagedDaemonStatus
from .paths import default_pid_path, default_runtime_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PuppenclawManager:
    """Manage a local Puppenclaw daemon process and its runtime metadata."""

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
        self._log_handle: TextIO | None = None

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
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None
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
        atomic_write_text(self.pid_path, f"{runtime.pid}\n")
        try:
            self.wait_until_ready()
        except Exception:
            self._cleanup_failed_startup()
            raise
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
            if self._process is not None:
                returncode = self._process.poll()
                if returncode is not None:
                    raise self._build_startup_failure(returncode)
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
            with httpx.Client(
                timeout=self.settings.daemon.request_timeout,
                trust_env=False,
            ) as client:
                response = client.get(f"{self.settings.daemon.base_url}/health")
                response.raise_for_status()
                return HealthStatus.model_validate(response.json())
        except httpx.HTTPError as error:
            raise DaemonProcessError(f"Puppenclaw daemon health check failed: {error}") from error

    def _request_shutdown(self) -> None:
        with suppress(Exception):
            with httpx.Client(
                timeout=self.settings.daemon.request_timeout,
                trust_env=False,
            ) as client:
                client.post(f"{self.settings.daemon.base_url}/shutdown")

    def _write_runtime(self, runtime: DaemonRuntimeInfo) -> None:
        atomic_write_text(
            self.runtime_path,
            runtime.model_dump_json(indent=2, by_alias=True),
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

    def _cleanup_failed_startup(self) -> None:
        if self._process is not None and self._process.poll() is None:
            with suppress(OSError):
                self._process.terminate()
            if not self._wait_for_owned_process(
                self._process.pid,
                min(self.settings.daemon.stop_timeout, 2.0),
            ):
                with suppress(OSError):
                    self._process.kill()
                self._wait_for_owned_process(self._process.pid, 1.0)
        self._cleanup_runtime_files()

    def _build_startup_failure(self, returncode: int) -> DaemonProcessError:
        runtime = self._load_runtime()
        log_path = (
            Path(runtime.log_path)
            if runtime is not None
            else self.settings.daemon.log_dir / "puppenclaw-daemon.log"
        )
        log_tail = _read_log_tail(log_path)
        message = "Puppenclaw daemon exited before becoming healthy " f"(exit code {returncode})."
        if log_path.exists():
            message += f" Log: {log_path}."
        if log_tail:
            message += f" Last log lines:\n{log_tail}"
        return DaemonProcessError(message)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as error:
        if _is_missing_pid_error(error):
            return False
        return True
    return True


def _is_missing_pid_error(error: OSError) -> bool:
    return error.errno in {errno.ESRCH, errno.EINVAL} or getattr(error, "winerror", None) == 87


def _read_log_tail(path: Path, *, max_lines: int = 20) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])
