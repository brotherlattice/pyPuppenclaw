from __future__ import annotations

import sys
import types
from pathlib import Path

from pypuppenclaw.interactive import (
    InteractiveState,
    PuppencodeShell,
    _completion_matches,
    _interactive_banner,
    _prompt_toolkit_input,
    _resolve_input_line,
    _suggestion_suffix,
)


def test_interactive_slash_completion_candidates() -> None:
    assert ("/exit", -3) in _completion_matches("/ex")
    assert ("/help", -1) in _completion_matches("/")
    assert _completion_matches("hello") == []
    assert ("fusion", -1) in _completion_matches("/mode f")
    assert ("codex", -1) in _completion_matches("/agent c")
    assert ("high", -1) in _completion_matches("/effort h")


def test_interactive_unique_prefix_ghost_suffix_and_enter_resolution() -> None:
    assert _suggestion_suffix("/ex") == "it"
    assert _resolve_input_line("/ex") == "/exit"
    assert _resolve_input_line("/mode f") == "/mode fusion"
    assert _resolve_input_line("/e") == "/e"


def test_interactive_shell_executes_unique_exit_prefix() -> None:
    shell = PuppencodeShell(state=InteractiveState(cwd=Path.cwd()))
    assert shell.handle_line("/ex") is True


def test_interactive_banner_mentions_ghost_completion(monkeypatch) -> None:
    monkeypatch.setattr("pypuppenclaw.interactive._completion_backend", lambda: "prompt_toolkit")
    assert "ghost text" in _interactive_banner()
    monkeypatch.setattr("pypuppenclaw.interactive._completion_backend", lambda: "none")
    assert "Completion unavailable" in _interactive_banner()


def test_prompt_toolkit_backend_wires_autosuggest_and_enter_keybinding(monkeypatch) -> None:
    calls: dict[str, object] = {}
    package = types.ModuleType("prompt_toolkit")
    package.__path__ = []  # type: ignore[attr-defined]

    def fake_prompt(message: str, **kwargs: object) -> str:
        calls["message"] = message
        calls["kwargs"] = kwargs
        return "/exit"

    package.prompt = fake_prompt  # type: ignore[attr-defined]

    completion = types.ModuleType("prompt_toolkit.completion")

    class Completer:
        pass

    class Completion:
        def __init__(self, text: str, *, start_position: int) -> None:
            self.text = text
            self.start_position = start_position

    completion.Completer = Completer  # type: ignore[attr-defined]
    completion.Completion = Completion  # type: ignore[attr-defined]

    auto_suggest = types.ModuleType("prompt_toolkit.auto_suggest")

    class AutoSuggest:
        pass

    class Suggestion:
        def __init__(self, text: str) -> None:
            self.text = text

    auto_suggest.AutoSuggest = AutoSuggest  # type: ignore[attr-defined]
    auto_suggest.Suggestion = Suggestion  # type: ignore[attr-defined]

    key_binding = types.ModuleType("prompt_toolkit.key_binding")

    class KeyBindings:
        def __init__(self) -> None:
            self.bindings: list[str] = []

        def add(self, key: str):
            self.bindings.append(key)

            def decorator(func):
                return func

            return decorator

    key_binding.KeyBindings = KeyBindings  # type: ignore[attr-defined]

    shortcuts = types.ModuleType("prompt_toolkit.shortcuts")

    class CompleteStyle:
        MULTI_COLUMN = "multi-column"

    shortcuts.CompleteStyle = CompleteStyle  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "prompt_toolkit", package)
    monkeypatch.setitem(sys.modules, "prompt_toolkit.completion", completion)
    monkeypatch.setitem(sys.modules, "prompt_toolkit.auto_suggest", auto_suggest)
    monkeypatch.setitem(sys.modules, "prompt_toolkit.key_binding", key_binding)
    monkeypatch.setitem(sys.modules, "prompt_toolkit.shortcuts", shortcuts)

    read = _prompt_toolkit_input()
    assert read is not None
    assert read("puppencode> ") == "/exit"
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["complete_style"] == "multi-column"
    assert kwargs["complete_while_typing"] is True
    assert "auto_suggest" in kwargs
    assert "key_bindings" in kwargs
