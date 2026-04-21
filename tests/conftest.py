from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pypuppenclaw.config import DaemonSettings, SourceSettings, WrapperSettings


@pytest.fixture()
def temp_settings(tmp_path: Path) -> WrapperSettings:
    return WrapperSettings(
        source=SourceSettings(kind="binary", daemonCommand=[sys.executable]),
        daemon=DaemonSettings(
            host="127.0.0.1",
            port=18895,
            stateDir=tmp_path / "state",
            dataDir=tmp_path / "data",
            logDir=tmp_path / "logs",
            generatedConfigPath=tmp_path / "state" / "puppenclaw.config.json",
            startupTimeout=5.0,
            stopTimeout=5.0,
            requestTimeout=2.0,
        ),
    )
