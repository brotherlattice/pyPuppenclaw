from __future__ import annotations

import json
from pathlib import Path

from pypuppenclaw.cli import main


class _StatusStub:
    def model_dump_json(self, **_kwargs) -> str:
        return json.dumps({"running": False})


def test_cli_config_init_and_status(temp_settings, tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("pypuppenclaw.cli.load_settings", lambda _path: temp_settings)

    assert main(["--config", str(config_path), "config-init"]) == 0
    assert config_path.exists()
    capsys.readouterr()

    class StubManager:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def status(self):
            return _StatusStub()

    monkeypatch.setattr("pypuppenclaw.cli.PuppenclawManager", StubManager)
    assert main(["--config", str(config_path), "status"]) == 0
    assert json.loads(capsys.readouterr().out)["running"] is False
