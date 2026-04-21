from __future__ import annotations

from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "pyPuppenclaw"
APP_AUTHOR = "Puppenclaw"


def platform_dirs() -> PlatformDirs:
    return PlatformDirs(APP_NAME, appauthor=APP_AUTHOR, ensure_exists=True)


def default_config_path() -> Path:
    return Path(platform_dirs().user_config_dir) / "config.toml"


def default_state_dir() -> Path:
    return Path(platform_dirs().user_state_dir)


def default_data_dir() -> Path:
    return default_state_dir() / "daemon-data"


def default_log_dir() -> Path:
    return default_state_dir() / "logs"


def default_generated_config_path() -> Path:
    return default_state_dir() / "puppenclaw.config.json"


def default_runtime_path() -> Path:
    return default_state_dir() / "runtime.json"


def default_install_manifest_path() -> Path:
    return default_state_dir() / "install-manifest.json"


def default_pid_path() -> Path:
    return default_state_dir() / "puppenclaw.pid"
