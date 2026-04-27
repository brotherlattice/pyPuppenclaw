from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast, get_args

from .errors import PuppenclawError
from .fusion import FusionRunner, FusionRunOptions
from .models import AgentKind, OrchestratorStatusSummary
from .project_config import PuppencodeProjectConfig, load_project_config
from .render import PuppencodeRenderer

_AGENT_CHOICES = cast(tuple[AgentKind, ...], get_args(AgentKind))
_MODE_CHOICES = ("fusion", "agent")
_BOOLEAN_CHOICES = ("on", "off")
_EFFORT_CHOICES = ("low", "medium", "high", "xhigh", "clear")
_MODEL_HINTS = (
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
    "sonnet",
    "opus",
    "clear",
)


@dataclass
class InteractiveState:
    cwd: Path
    config_path: Path | None = None
    mode: Literal["fusion", "agent"] = "fusion"
    agent: AgentKind = "codex"
    model: str | None = None
    effort: str | None = None
    validation_command: str | None = None
    wait: bool = True
    show_events: bool = False

    @classmethod
    def from_project_config(
        cls,
        *,
        cwd: Path,
        config_path: Path | None = None,
        config: PuppencodeProjectConfig | None = None,
    ) -> InteractiveState:
        resolved = config or load_project_config(config_path, cwd=cwd)
        return cls(
            cwd=cwd,
            config_path=config_path,
            mode=resolved.mode,
            agent=resolved.preferred_agent,
            model=resolved.model,
            effort=resolved.effort,
            validation_command=resolved.validation_command,
        )

    def options(self, prompt: str | None = None) -> FusionRunOptions:
        return FusionRunOptions(
            cwd=self.cwd,
            config_path=self.config_path,
            prompt=prompt,
            agent=self.agent,
            model=self.model,
            effort=self.effort,
            validation_command=self.validation_command,
            wait=self.wait,
        )

    def prompt(self) -> str:
        model = self.model or "default"
        return f"puppencode[{self.mode}:{self.agent}:{model}]> "


class PuppencodeShell:
    """Interactive slash-command shell for puppencode."""

    def __init__(
        self,
        *,
        state: InteractiveState,
        runner: FusionRunner | None = None,
        renderer: PuppencodeRenderer | None = None,
    ) -> None:
        self.state = state
        self.renderer = renderer or PuppencodeRenderer()
        self.runner = runner or FusionRunner(renderer=self.renderer)

    def run(self) -> int:
        print(_interactive_banner(), file=sys.stderr)
        while True:
            try:
                user_text = _read_interactive_input(self.state.prompt())
            except EOFError:
                print("", file=sys.stderr)
                return 0
            except KeyboardInterrupt:
                print("^C", file=sys.stderr)
                continue
            if not user_text.strip():
                continue
            try:
                if self.handle_line(user_text):
                    return 0
            except KeyboardInterrupt:
                print("^C", file=sys.stderr)
            except (PuppenclawError, TimeoutError) as error:
                self.renderer.error(str(error))

    def handle_line(self, user_text: str) -> bool:
        stripped = _resolve_input_line(user_text.strip())
        if stripped.startswith("/"):
            command, _, rest = stripped[1:].partition(" ")
            resolved = _resolve_slash_command(command.lower())
            if resolved is None:
                return False
            return self._handle_slash_command(resolved, rest.strip())
        if self.state.mode == "agent":
            self.runner.run_agent(stripped, self.state.options(stripped))
        else:
            self.runner.run_fusion(stripped, self.state.options(stripped))
        return False

    def _handle_slash_command(self, command: str, rest: str) -> bool:
        if command in {"exit", "quit"}:
            return True
        if command == "help":
            _print_interactive_help()
            return False
        if command == "clear":
            print("\033c", end="")
            return False
        if command == "mode":
            self._set_mode(rest)
            return False
        if command == "agent":
            self._set_agent(rest)
            return False
        if command == "model":
            self._set_nullable("model", rest)
            return False
        if command in {"effort", "reasoning"}:
            self._set_nullable("effort", rest)
            return False
        if command == "validation":
            self._set_validation(rest)
            return False
        if command == "wait":
            self._set_boolean("wait", rest, command_name="wait")
            return False
        if command == "events":
            self._set_boolean("show_events", rest, command_name="events")
            return False
        if command == "status":
            self._status(rest)
            return False
        if command == "site":
            self.runner.ensure_ready()
            self.renderer.site_status(self.runner.service.client.site.status(verbose=True).details)
            return False
        if command == "sessions":
            self.runner.ensure_ready()
            self.renderer.sessions(self.runner.service.client.sessions.list().details.sessions)
            return False
        if command in {"campaigns", "projects", "workers"}:
            self.runner.ensure_ready()
            summary = self.runner.service.client.orchestrator.status().details
            if isinstance(summary, OrchestratorStatusSummary):
                if command == "campaigns":
                    self.renderer.campaigns(summary.campaigns)
                else:
                    self.renderer.orchestrator_summary(summary)
            return False
        if command == "artifacts":
            self.runner.artifacts(campaign_id=rest or None)
            return False
        if command in {"read", "cat", "artifact"}:
            if not rest:
                print("usage: /read ARTIFACT_ID", file=sys.stderr)
                return False
            self.runner.read_artifact(rest)
            return False
        if command == "campaign-events":
            if not rest:
                print("usage: /campaign-events CAMPAIGN_ID", file=sys.stderr)
                return False
            self.runner.events(rest)
            return False
        if command == "approve":
            if not rest:
                print("usage: /approve CAMPAIGN_ID", file=sys.stderr)
                return False
            self.runner.approve(rest)
            return False
        if command == "cancel":
            if not rest:
                print("usage: /cancel CAMPAIGN_ID", file=sys.stderr)
                return False
            self.runner.cancel(rest)
            return False
        if command in {"run", "fusion"}:
            if not rest:
                print(f"usage: /{command} PROMPT", file=sys.stderr)
                return False
            self.runner.run_fusion(rest, self.state.options(rest))
            return False
        if command == "agent-run":
            if not rest:
                print("usage: /agent-run PROMPT", file=sys.stderr)
                return False
            self.runner.run_agent(rest, self.state.options(rest))
            return False
        if command == "send":
            session_name, _, message = rest.partition(" ")
            if not session_name or not message:
                print("usage: /send SESSION_NAME MESSAGE", file=sys.stderr)
                return False
            self.runner.send_agent(session_name, message)
            return False
        print(f"unknown command: /{command}; type /help", file=sys.stderr)
        return False

    def _set_mode(self, value: str) -> None:
        if value not in _MODE_CHOICES:
            print(f"usage: /mode {'|'.join(_MODE_CHOICES)}", file=sys.stderr)
            return
        self.state.mode = cast(Literal["fusion", "agent"], value)
        print(f"mode={self.state.mode}", file=sys.stderr)

    def _set_agent(self, value: str) -> None:
        if value not in _AGENT_CHOICES:
            print(f"usage: /agent {'|'.join(_AGENT_CHOICES)}", file=sys.stderr)
            return
        self.state.agent = cast(AgentKind, value)
        print(f"agent={self.state.agent}", file=sys.stderr)

    def _set_nullable(self, field: Literal["model", "effort"], value: str) -> None:
        if not value:
            print(f"{field}={getattr(self.state, field) or '<default>'}", file=sys.stderr)
            return
        setattr(self.state, field, None if value == "clear" else value)
        print(f"{field}={getattr(self.state, field) or '<default>'}", file=sys.stderr)

    def _set_validation(self, value: str) -> None:
        if not value:
            print(
                f"validation={self.state.validation_command or '<none>'}",
                file=sys.stderr,
            )
            return
        self.state.validation_command = None if value == "clear" else value
        print(f"validation={self.state.validation_command or '<none>'}", file=sys.stderr)

    def _set_boolean(
        self,
        field: Literal["wait", "show_events"],
        value: str,
        *,
        command_name: str,
    ) -> None:
        if value not in _BOOLEAN_CHOICES:
            print(f"usage: /{command_name} on|off", file=sys.stderr)
            return
        setattr(self.state, field, value == "on")
        print(f"{command_name}={value}", file=sys.stderr)

    def _status(self, rest: str) -> None:
        if rest:
            self.runner.campaign_status(rest)
            return
        self.runner.ensure_ready()
        summary = self.runner.service.client.orchestrator.status().details
        if isinstance(summary, OrchestratorStatusSummary):
            self.renderer.orchestrator_summary(summary)


def _read_interactive_input(message: str) -> str:
    if not sys.stdin.isatty():
        return input(message)
    prompt_toolkit_input = _prompt_toolkit_input()
    if prompt_toolkit_input is not None:
        return prompt_toolkit_input(message)
    readline_input = _readline_input()
    if readline_input is not None:
        return readline_input(message)
    return input(message)


def _interactive_banner() -> str:
    base = "puppencode interactive. Type /help for commands; /exit to quit."
    backend = _completion_backend()
    if backend == "prompt_toolkit":
        return base + " Unique /command prefixes show ghost text and execute on Enter."
    if backend == "readline":
        return base + " Press Tab to complete /commands."
    return base + " Completion unavailable; install prompt-toolkit."


def _completion_backend() -> str:
    if _prompt_toolkit_input() is not None:
        return "prompt_toolkit"
    if _readline_input() is not None:
        return "readline"
    return "none"


def _prompt_toolkit_input():
    try:
        from prompt_toolkit import prompt
        from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.shortcuts import CompleteStyle
    except ImportError:
        return None

    class SlashCompleter(Completer):
        def get_completions(self, document: object, _complete_event: object):
            text = getattr(document, "text_before_cursor", "")
            for value, start_position in _completion_matches(text):
                yield Completion(value, start_position=start_position)

    class SlashAutoSuggest(AutoSuggest):
        def get_suggestion(self, _buffer: object, document: object) -> object | None:
            text = getattr(document, "text_before_cursor", "")
            suffix = _suggestion_suffix(text)
            return Suggestion(suffix) if suffix else None

    key_bindings = KeyBindings()

    @key_bindings.add("enter")
    def _accept_unique_completion(event: object) -> None:
        buffer = event.app.current_buffer  # type: ignore[attr-defined]
        resolved = _resolve_input_line(buffer.text)
        buffer.text = resolved
        buffer.cursor_position = len(resolved)
        buffer.validate_and_handle()

    def _read(message: str) -> str:
        return prompt(
            message,
            completer=SlashCompleter(),
            auto_suggest=SlashAutoSuggest(),
            key_bindings=key_bindings,
            complete_style=CompleteStyle.MULTI_COLUMN,
            complete_while_typing=True,
        )

    return _read


def _readline_input():
    try:
        import readline
    except ImportError:
        return None

    def _complete(_text: str, state: int) -> str | None:
        line = readline.get_line_buffer()
        end = readline.get_endidx()
        candidates = [value for value, _ in _completion_matches(line[:end])]
        return candidates[state] if state < len(candidates) else None

    def _read(message: str) -> str:
        old_completer = readline.get_completer()
        old_delims = readline.get_completer_delims()
        try:
            readline.set_completer(_complete)
            readline.set_completer_delims(" \t\n")
            readline.parse_and_bind("tab: complete")
            return input(message)
        finally:
            readline.set_completer(old_completer)
            readline.set_completer_delims(old_delims)

    return _read


def _completion_matches(text_before_cursor: str) -> list[tuple[str, int]]:
    if not text_before_cursor.startswith("/"):
        return []
    tree = _completion_tree()
    if " " not in text_before_cursor:
        return [
            (command, -len(text_before_cursor))
            for command in tree
            if command.startswith(text_before_cursor)
        ]
    command, _, rest = text_before_cursor.partition(" ")
    values = tree.get(command)
    if not isinstance(values, tuple):
        return []
    token = rest.rsplit(" ", 1)[-1]
    return [(value, -len(token)) for value in values if value.startswith(token)]


def _suggestion_suffix(text_before_cursor: str) -> str:
    matches = _completion_matches(text_before_cursor)
    if len(matches) != 1:
        return ""
    value, start_position = matches[0]
    typed = text_before_cursor[len(text_before_cursor) + start_position :]
    if not value.startswith(typed):
        return ""
    return value[len(typed) :]


def _resolve_input_line(line: str) -> str:
    if not line.startswith("/"):
        return line
    if " " not in line:
        matches = _completion_matches(line)
        if len(matches) == 1:
            return matches[0][0]
        return line
    command, separator, rest = line.partition(" ")
    values = _completion_tree().get(command)
    if not isinstance(values, tuple):
        return line
    token = rest.rsplit(" ", 1)[-1]
    matches = [value for value in values if value.startswith(token)]
    if len(matches) != 1:
        return line
    prefix = rest[: len(rest) - len(token)]
    return f"{command}{separator}{prefix}{matches[0]}"


def _resolve_slash_command(command: str) -> str | None:
    if command in _slash_commands():
        return command
    matches = [known for known in _slash_commands() if known.startswith(command)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        print(
            f"ambiguous command: /{command}; matches: "
            + ", ".join(f"/{match}" for match in matches),
            file=sys.stderr,
        )
        return None
    print(f"unknown command: /{command}; type /help", file=sys.stderr)
    return None


def _completion_tree() -> dict[str, tuple[str, ...] | None]:
    return {
        "/help": None,
        "/exit": None,
        "/quit": None,
        "/clear": None,
        "/mode": _MODE_CHOICES,
        "/agent": _AGENT_CHOICES,
        "/model": _MODEL_HINTS,
        "/effort": _EFFORT_CHOICES,
        "/reasoning": _EFFORT_CHOICES,
        "/validation": ("clear",),
        "/wait": _BOOLEAN_CHOICES,
        "/events": _BOOLEAN_CHOICES,
        "/status": None,
        "/site": None,
        "/sessions": None,
        "/campaigns": None,
        "/projects": None,
        "/workers": None,
        "/artifacts": None,
        "/read": None,
        "/cat": None,
        "/artifact": None,
        "/campaign-events": None,
        "/approve": None,
        "/cancel": None,
        "/fusion": None,
        "/run": None,
        "/agent-run": None,
        "/send": None,
    }


def _slash_commands() -> tuple[str, ...]:
    return tuple(command[1:] for command in _completion_tree())


def _print_interactive_help() -> None:
    print(
        "\n".join(
            [
                "Commands:",
                "  /help",
                "  /exit | /quit",
                "  /mode fusion|agent",
                "  /agent codex|claude",
                "  /model NAME | /model clear",
                "  /effort LEVEL | /effort clear",
                "  /validation COMMAND | /validation clear",
                "  /wait on|off",
                "  /status [CAMPAIGN_ID]",
                "  /site",
                "  /sessions",
                "  /campaigns",
                "  /artifacts [CAMPAIGN_ID]",
                "  /read ARTIFACT_ID",
                "  /campaign-events CAMPAIGN_ID",
                "  /approve CAMPAIGN_ID",
                "  /cancel CAMPAIGN_ID",
                "  /fusion PROMPT | /run PROMPT",
                "  /agent-run PROMPT",
                "  /send SESSION_NAME MESSAGE",
                "Plain text starts puppenfusion in fusion mode or an agent session in agent mode.",
            ]
        ),
        file=sys.stderr,
    )
