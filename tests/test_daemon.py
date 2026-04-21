from __future__ import annotations

import sys
from pathlib import Path

from pypuppenclaw.daemon import PuppenclawManager
from pypuppenclaw.models import DaemonRuntimeInfo, InstallManifest


class StubInstaller:
    def __init__(self, manifest: InstallManifest) -> None:
        self.manifest = manifest

    def install(self) -> InstallManifest:
        return self.manifest

    def load_manifest(self) -> InstallManifest:
        return self.manifest


def test_manager_start_status_stop(temp_settings, tmp_path: Path) -> None:
    script = tmp_path / "fake_daemon.py"
    fixture_script = Path(__file__).parent / "fixtures" / "fake_puppenclaw_daemon.py"
    script.write_text(fixture_script.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = InstallManifest(
        sourceKind="binary",
        sourcePath=str(tmp_path),
        daemonCommand=[sys.executable, str(script)],
        packageName="fake",
        version="0.0.0",
        installedAt="2026-01-01T00:00:00Z",
    )
    manager = PuppenclawManager(
        temp_settings,
        installer=StubInstaller(manifest),
        pid_path=tmp_path / "daemon.pid",
        runtime_path=tmp_path / "runtime.json",
    )

    started = manager.start()
    assert started.running is True
    assert started.healthy is True
    assert started.runtime is not None

    status = manager.status()
    assert status.running is True
    assert status.healthy is True

    stopped = manager.stop()
    assert stopped.running is False
    assert manager.status().running is False


def test_manager_cleans_stale_runtime(temp_settings, tmp_path: Path) -> None:
    runtime_path = tmp_path / "runtime.json"
    runtime = DaemonRuntimeInfo(
        pid=999999,
        baseUrl=temp_settings.daemon.base_url,
        dataDir=str(temp_settings.daemon.data_dir),
        logPath=str(tmp_path / "daemon.log"),
        configPath=str(tmp_path / "generated.json"),
        command=["fake"],
        startedAt="2026-01-01T00:00:00Z",
    )
    runtime_path.write_text(runtime.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    manager = PuppenclawManager(
        temp_settings,
        installer=StubInstaller(
            InstallManifest(
                sourceKind="binary",
                sourcePath=str(tmp_path),
                daemonCommand=["fake"],
                packageName="fake",
                version="0.0.0",
                installedAt="2026-01-01T00:00:00Z",
            )
        ),
        pid_path=tmp_path / "daemon.pid",
        runtime_path=runtime_path,
    )

    status = manager.status()

    assert status.running is False
    assert runtime_path.exists() is False
