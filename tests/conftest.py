from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pypuppenclaw.config import DaemonSettings, SourceSettings, WrapperSettings


@pytest.fixture()
def temp_settings(tmp_path: Path, free_tcp_port_factory: Callable[[], int]) -> WrapperSettings:
    return WrapperSettings(
        source=SourceSettings(kind="binary", daemonCommand=[sys.executable]),
        daemon=DaemonSettings(
            host="127.0.0.1",
            port=free_tcp_port_factory(),
            stateDir=tmp_path / "state",
            dataDir=tmp_path / "data",
            logDir=tmp_path / "logs",
            generatedConfigPath=tmp_path / "state" / "puppenclaw.config.json",
            startupTimeout=5.0,
            stopTimeout=5.0,
            requestTimeout=2.0,
        ),
    )
