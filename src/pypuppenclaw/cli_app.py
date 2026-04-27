from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast, get_args

from .config import load_settings
from .errors import PuppenclawError
from .fusion import FusionRunner, FusionRunOptions
from .interactive import InteractiveState, PuppencodeShell
from .models import AgentKind, LogsQuery, ReassessmentReportQuery, ReassessmentStartRequest
from .project_config import init_project_config, load_project_config
from .render import PuppencodeRenderer
from .service import PuppenclawService

_AGENT_CHOICES = cast(tuple[AgentKind, ...], get_args(AgentKind))
_COMMANDS = {
    "chat",
    "interactive",
    "fusion",
    "run",
    "init",
    "doctor",
    "install",
    "start",
    "stop",
    "status",
    "site",
    "sessions",
    "campaigns",
    "artifacts",
    "read",
    "events",
    "approve",
    "cancel",
    "logs",
    "reassess",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="puppencode",
        description="Fusion-first terminal coding CLI for Puppenclaw.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            [
                "examples:",
                '  puppencode "implement the failing test fix"',
                "  puppencode chat",
                '  puppencode fusion --validation-command "pytest" "refactor the client"',
                "  puppencode status camp-...",
                "  puppencode read artifact-...",
            ]
        ),
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Project working directory")
    parser.add_argument("--config", type=Path, default=None, help="Project .pclaw.toml path")
    parser.add_argument(
        "--wrapper-config",
        type=Path,
        default=None,
        help="pyPuppenclaw config path",
    )
    parser.add_argument("--plain", action="store_true", help="Disable rich terminal rendering")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON where possible",
    )

    sub = parser.add_subparsers(dest="command")

    chat = sub.add_parser("chat", help="Start the interactive coding shell")
    _add_workflow_overrides(chat)
    interactive = sub.add_parser("interactive", help="Alias for chat")
    _add_workflow_overrides(interactive)

    fusion = sub.add_parser("fusion", help="Run a puppenfusion coding campaign")
    _add_workflow_overrides(fusion)
    fusion.add_argument("--no-wait", action="store_true", help="Return after campaign creation")
    fusion.add_argument("prompt", nargs="+")

    run = sub.add_parser("run", help="Run a direct single-agent coding session")
    _add_workflow_overrides(run)
    run.add_argument("prompt", nargs="+")

    init = sub.add_parser("init", help="Create .pclaw.toml for this project")
    init.add_argument("--force", action="store_true", help="Overwrite an existing .pclaw.toml")

    sub.add_parser("doctor", help="Print local puppencode and wrapper configuration")
    sub.add_parser("install", help="Install or build Puppenclaw")
    sub.add_parser("start", help="Start the managed Puppenclaw daemon")
    sub.add_parser("stop", help="Stop the managed Puppenclaw daemon")

    status = sub.add_parser("status", help="Show orchestrator or campaign status")
    status.add_argument("campaign_id", nargs="?")

    sub.add_parser("site", help="Show site status")
    sub.add_parser("sessions", help="List sessions")
    sub.add_parser("campaigns", help="List campaigns")

    artifacts = sub.add_parser("artifacts", help="List artifacts")
    artifacts.add_argument("--campaign-id")
    artifacts.add_argument("--project-id")

    read = sub.add_parser("read", help="Read artifact text")
    read.add_argument("artifact_id")
    read.add_argument("--limit-chars", type=int, default=120_000)

    events = sub.add_parser("events", help="Show campaign fusion events")
    events.add_argument("campaign_id")
    events.add_argument("--after")
    events.add_argument("--limit", type=int, default=100)

    approve = sub.add_parser("approve", help="Approve a waiting campaign")
    approve.add_argument("campaign_id")
    cancel = sub.add_parser("cancel", help="Cancel a campaign")
    cancel.add_argument("campaign_id")

    logs = sub.add_parser("logs", help="Show daemon logs for a session, campaign, or run")
    logs.add_argument("--session-name")
    logs.add_argument("--campaign-id")
    logs.add_argument("--run-id")
    logs.add_argument("--limit-chars", type=int, default=12_000)

    reassess = sub.add_parser("reassess", help="Start or inspect conservative model reassessment")
    reassess_sub = reassess.add_subparsers(dest="reassess_command", required=True)
    reassess_start = reassess_sub.add_parser("start", help="Start reassessment")
    reassess_start.add_argument("--project-id", required=True)
    reassess_start.add_argument("--worker-id", default="local")
    reassess_start.add_argument("--target-model", required=True)
    reassess_start.add_argument("--target-agent", choices=_AGENT_CHOICES)
    reassess_start.add_argument("--validation-command")
    reassess_start.add_argument("--base-ref")
    reassess_start.add_argument("--limit", type=int, default=20)
    reassess_sub.add_parser("status", help="List reassessments")
    reassess_report = reassess_sub.add_parser("report", help="Show reassessment report")
    reassess_report.add_argument("reassessment_id")

    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = _normalize_argv(list(sys.argv[1:] if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    if args.command is None:
        args = parser.parse_args([*raw_argv, "chat"])
    renderer = PuppencodeRenderer(plain=args.plain, json_output=args.json)
    service = _service(args)
    runner = FusionRunner(service=service, renderer=renderer)

    try:
        return _dispatch(args, runner, renderer)
    except PuppenclawError as error:
        renderer.error(str(error))
        return 2
    except TimeoutError as error:
        renderer.error(str(error))
        return 1


def _dispatch(
    args: argparse.Namespace,
    runner: FusionRunner,
    renderer: PuppencodeRenderer,
) -> int:
    command = args.command
    cwd = args.cwd.expanduser().resolve()
    if command == "init":
        path = init_project_config(cwd, force=args.force)
        renderer.text(str(path))
        return 0
    if command == "doctor":
        renderer.json(
            {
                "cwd": str(cwd),
                "project_config": load_project_config(args.config, cwd=cwd),
                "wrapper_base_url": runner.service.settings.daemon.base_url,
                "source_kind": runner.service.settings.source.kind,
            }
        )
        return 0
    if command == "install":
        renderer.json(runner.service.install())
        return 0
    if command == "start":
        renderer.json(runner.service.start())
        return 0
    if command == "stop":
        renderer.json(runner.service.stop())
        return 0
    if command in {"chat", "interactive"}:
        state = InteractiveState.from_project_config(cwd=cwd, config_path=args.config)
        _apply_state_overrides(state, args)
        return PuppencodeShell(state=state, runner=runner, renderer=renderer).run()
    if command == "fusion":
        prompt = " ".join(args.prompt)
        runner.run_fusion(prompt, _options(args, prompt=prompt, wait=not args.no_wait))
        return 0
    if command == "run":
        prompt = " ".join(args.prompt)
        runner.run_agent(prompt, _options(args, prompt=prompt))
        return 0
    if command == "status":
        runner.ensure_ready()
        if args.campaign_id:
            runner.campaign_status(args.campaign_id)
        else:
            renderer.orchestrator_summary(runner.service.client.orchestrator.status().details)
        return 0
    if command == "site":
        runner.ensure_ready()
        renderer.site_status(runner.service.client.site.status(verbose=True).details)
        return 0
    if command == "sessions":
        runner.ensure_ready()
        renderer.sessions(runner.service.client.sessions.list().details.sessions)
        return 0
    if command == "campaigns":
        runner.ensure_ready()
        summary = runner.service.client.orchestrator.status().details
        renderer.campaigns(summary.campaigns)
        return 0
    if command == "artifacts":
        runner.artifacts(campaign_id=args.campaign_id, project_id=args.project_id)
        return 0
    if command == "read":
        runner.read_artifact(args.artifact_id, limit_chars=args.limit_chars)
        return 0
    if command == "events":
        runner.events(args.campaign_id, after=args.after, limit=args.limit)
        return 0
    if command == "approve":
        runner.approve(args.campaign_id)
        return 0
    if command == "cancel":
        runner.cancel(args.campaign_id)
        return 0
    if command == "logs":
        runner.ensure_ready()
        result = runner.service.client.site.logs(
            LogsQuery(
                sessionName=args.session_name,
                campaignId=args.campaign_id,
                runId=args.run_id,
                limitChars=args.limit_chars,
            )
        )
        renderer.text(result.details.text)
        return 0
    if command == "reassess":
        return _dispatch_reassess(args, runner, renderer)
    raise AssertionError(f"unhandled command: {command!r}")


def _dispatch_reassess(
    args: argparse.Namespace,
    runner: FusionRunner,
    renderer: PuppencodeRenderer,
) -> int:
    runner.ensure_ready()
    if args.reassess_command == "start":
        result = runner.service.client.orchestrator.start_reassessment(
            ReassessmentStartRequest(
                projectId=args.project_id,
                workerId=args.worker_id,
                targetModel=args.target_model,
                targetAgent=args.target_agent,
                validationCommand=args.validation_command,
                baseRef=args.base_ref,
                limit=args.limit,
            )
        )
        renderer.json(result.details)
        return 0
    if args.reassess_command == "status":
        renderer.json(runner.service.client.orchestrator.reassessment_status().details)
        return 0
    if args.reassess_command == "report":
        result = runner.service.client.orchestrator.reassessment_report(
            ReassessmentReportQuery(reassessmentId=args.reassessment_id)
        )
        renderer.text(result.details.report)
        return 0
    raise AssertionError(f"unhandled reassess command: {args.reassess_command!r}")


def _add_workflow_overrides(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agent", choices=_AGENT_CHOICES)
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--validation-command")
    parser.add_argument("--project-id")
    parser.add_argument("--worker-id")
    parser.add_argument("--include-file", action="append", dest="include_files")


def _options(
    args: argparse.Namespace,
    *,
    prompt: str | None = None,
    wait: bool = True,
) -> FusionRunOptions:
    return FusionRunOptions(
        cwd=args.cwd.expanduser().resolve(),
        config_path=args.config,
        prompt=prompt,
        project_id=getattr(args, "project_id", None),
        worker_id=getattr(args, "worker_id", None),
        agent=getattr(args, "agent", None),
        model=getattr(args, "model", None),
        effort=getattr(args, "effort", None),
        validation_command=getattr(args, "validation_command", None),
        include_files=tuple(getattr(args, "include_files", None) or ()) or None,
        wait=wait,
    )


def _apply_state_overrides(state: InteractiveState, args: argparse.Namespace) -> None:
    if args.agent is not None:
        state.agent = args.agent
    if args.model is not None:
        state.model = args.model
    if args.effort is not None:
        state.effort = args.effort
    if args.validation_command is not None:
        state.validation_command = args.validation_command


def _service(args: argparse.Namespace) -> PuppenclawService:
    settings = load_settings(args.wrapper_config) if args.wrapper_config is not None else None
    return PuppenclawService(settings=settings)


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return ["chat"]
    position = _first_command_position(argv)
    if position is None:
        return argv
    if argv[position] in _COMMANDS:
        return argv
    return [*argv[:position], "fusion", *argv[position:]]


def _first_command_position(argv: list[str]) -> int | None:
    value_options = {"--cwd", "--config", "--wrapper-config"}
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in value_options:
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in value_options):
            index += 1
            continue
        if token in {"--plain", "--json"}:
            index += 1
            continue
        if token.startswith("-"):
            return None
        return index
    return None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
