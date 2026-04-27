from __future__ import annotations

from pathlib import Path

from pypuppenclaw import cli_app
from pypuppenclaw.fusion import FusionRunOptions


def test_puppencode_init_creates_project_config(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("pypuppenclaw.cli_app._service", lambda _args: object())

    assert cli_app.main(["--cwd", str(tmp_path), "init"]) == 0

    assert (tmp_path / ".pclaw.toml").exists()
    assert str(tmp_path / ".pclaw.toml") in capsys.readouterr().out


def test_puppencode_bare_prompt_dispatches_fusion(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple[str, FusionRunOptions]] = []

    class FakeRunner:
        def __init__(self, **_kwargs) -> None:
            pass

        def run_fusion(self, prompt: str, options: FusionRunOptions) -> None:
            calls.append((prompt, options))

    monkeypatch.setattr("pypuppenclaw.cli_app._service", lambda _args: object())
    monkeypatch.setattr("pypuppenclaw.cli_app.FusionRunner", FakeRunner)

    assert cli_app.main(["--cwd", str(tmp_path), "implement", "the", "fix"]) == 0

    assert calls[0][0] == "implement the fix"


def test_puppencode_fusion_passes_overrides(tmp_path: Path, monkeypatch) -> None:
    calls: list[tuple[str, FusionRunOptions]] = []

    class FakeRunner:
        def __init__(self, **_kwargs) -> None:
            pass

        def run_fusion(self, prompt: str, options: FusionRunOptions) -> None:
            calls.append((prompt, options))

    monkeypatch.setattr("pypuppenclaw.cli_app._service", lambda _args: object())
    monkeypatch.setattr("pypuppenclaw.cli_app.FusionRunner", FakeRunner)

    rc = cli_app.main(
        [
            "--cwd",
            str(tmp_path),
            "fusion",
            "--agent",
            "claude",
            "--model",
            "sonnet",
            "--validation-command",
            "pytest",
            "--no-wait",
            "make",
            "it",
        ]
    )

    assert rc == 0
    prompt, options = calls[0]
    assert prompt == "make it"
    assert options.agent == "claude"
    assert options.model == "sonnet"
    assert options.validation_command == "pytest"
    assert options.wait is False
