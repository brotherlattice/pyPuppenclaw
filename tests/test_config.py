from __future__ import annotations

import json
from pathlib import Path

from pypuppenclaw.config import (
    WrapperSettings,
    ensure_checkout_path,
    load_settings,
    save_settings,
    write_generated_puppenclaw_config,
)


def test_save_and_load_settings_roundtrip(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    settings = WrapperSettings()
    settings.daemon.state_dir = tmp_path / "state"
    settings.daemon.data_dir = tmp_path / "data"
    settings.daemon.log_dir = tmp_path / "logs"
    settings.daemon.generated_config_path = tmp_path / "state" / "generated.json"

    saved_path = save_settings(settings, config_path)
    loaded = load_settings(saved_path)

    assert saved_path == config_path.resolve()
    assert loaded.daemon.state_dir == settings.daemon.state_dir.resolve()
    assert loaded.agents.default_agent == settings.agents.default_agent


def test_write_generated_puppenclaw_config_contains_expected_keys(tmp_path: Path) -> None:
    settings = WrapperSettings()
    settings.daemon.state_dir = tmp_path / "state"
    settings.daemon.data_dir = tmp_path / "data"
    settings.daemon.log_dir = tmp_path / "logs"
    settings.daemon.generated_config_path = tmp_path / "state" / "generated.json"
    settings.orchestration.default_project_root = tmp_path / "workspace"

    written = write_generated_puppenclaw_config(settings)
    payload = json.loads(written.read_text(encoding="utf-8"))

    assert payload["backend"] == "local"
    assert payload["defaultAgent"] in {"claude", "codex"}
    assert payload["orchestration"]["defaultProjectRoot"] == str((tmp_path / "workspace").resolve())


def test_ensure_checkout_path_prefers_existing_env_var(tmp_path: Path, monkeypatch) -> None:
    checkout = tmp_path / "puppenclaw"
    checkout.mkdir()
    monkeypatch.setenv("PUPPENCLAW_SOURCE_DIR", str(checkout))

    resolved = ensure_checkout_path(WrapperSettings())

    assert resolved == checkout.resolve()
