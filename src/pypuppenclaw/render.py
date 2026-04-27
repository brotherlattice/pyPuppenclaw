from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from typing import Any, TextIO

from pydantic import BaseModel

from .models import (
    ArtifactRecord,
    CampaignEventsDetails,
    CampaignSpecRecord,
    CampaignStatusSnapshot,
    OrchestratorStatusSummary,
    SessionInfo,
    SiteStatus,
)

try:  # pragma: no cover - fallback is covered in unit tests without rich.
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:  # pragma: no cover
    Console = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Table = None  # type: ignore[assignment]


class PuppencodeRenderer:
    """Human-oriented renderer for the puppencode terminal workflow."""

    def __init__(
        self,
        *,
        plain: bool = False,
        json_output: bool = False,
        file: TextIO | None = None,
    ) -> None:
        self.plain = plain
        self.json_output = json_output
        self.file = file or sys.stdout
        self.console = (
            None
            if plain or Console is None
            else Console(file=self.file, highlight=False, soft_wrap=True)
        )

    def info(self, message: str) -> None:
        if self.json_output:
            return
        if self.console is not None:
            self._print(f"[cyan]puppencode[/] {message}")
            return
        self._print(f"[puppencode] {message}")

    def warning(self, message: str) -> None:
        if self.json_output:
            return
        if self.console is not None:
            self._print(f"[yellow]warning[/] {message}")
            return
        self._print(f"warning: {message}")

    def error(self, message: str) -> None:
        if self.console is not None and Console is not None:
            Console(file=sys.stderr, highlight=False, soft_wrap=True).print(
                f"[red]error[/] {message}"
            )
            return
        print(f"error: {message}", file=sys.stderr)

    def text(self, value: str) -> None:
        if self.json_output:
            print(json.dumps({"text": value}, indent=2), file=self.file)
            return
        self._print(value)

    def json(self, value: Any) -> None:
        print(json.dumps(_jsonable(value), indent=2), file=self.file)

    def site_status(self, status: SiteStatus) -> None:
        if self.json_output:
            self.json(status)
            return
        rows = [
            ("site", status.site_id),
            ("backend", status.backend),
            ("health", status.plugin_health),
            ("default agent", status.default_agent),
            ("workers", str(len(status.workers))),
        ]
        self._kv_panel("Site Status", rows)

    def sessions(self, sessions: Iterable[SessionInfo]) -> None:
        rows = [
            (session.name, session.agent, session.state, session.directory) for session in sessions
        ]
        self._table("Sessions", ("name", "agent", "state", "directory"), rows)

    def campaigns(self, campaigns: Iterable[CampaignSpecRecord]) -> None:
        rows = [
            (
                campaign.id,
                campaign.name,
                campaign.template,
                campaign.state,
                campaign.last_progress_at,
            )
            for campaign in campaigns
        ]
        self._table("Campaigns", ("id", "name", "template", "state", "updated"), rows)

    def campaign(self, snapshot: CampaignStatusSnapshot) -> None:
        if self.json_output:
            self.json(snapshot)
            return
        progress = snapshot.progress
        rows = [
            ("campaign", snapshot.campaign.id),
            ("name", snapshot.campaign.name),
            ("state", snapshot.campaign.state),
            ("template", snapshot.campaign.template),
            ("progress", f"{progress.completed_steps}/{progress.total_steps} steps"),
            ("current", progress.current_step_title or "<none>"),
        ]
        self._kv_panel("Campaign", rows)

    def orchestrator_summary(self, summary: OrchestratorStatusSummary) -> None:
        if self.json_output:
            self.json(summary)
            return
        self._kv_panel(
            "Orchestrator",
            [
                ("projects", str(len(summary.projects))),
                ("workers", str(len(summary.workers))),
                ("campaigns", str(len(summary.campaigns))),
            ],
        )

    def artifacts(self, artifacts: Iterable[ArtifactRecord]) -> None:
        rows = [
            (
                artifact.id,
                artifact.kind,
                artifact.title,
                str(artifact.size_bytes),
            )
            for artifact in artifacts
        ]
        self._table("Artifacts", ("id", "kind", "title", "bytes"), rows)

    def events(self, details: CampaignEventsDetails) -> None:
        if self.json_output:
            self.json(details)
            return
        rows = [
            (
                event.created_at,
                event.phase,
                event.candidate or "",
                event.message,
            )
            for event in details.events
        ]
        self._table("Campaign Events", ("time", "phase", "agent", "message"), rows)

    def _kv_panel(self, title: str, rows: list[tuple[str, str]]) -> None:
        if self.console is None or Panel is None:
            self._print(title)
            for key, value in rows:
                self._print(f"{key}: {value}")
            return
        body = "\n".join(f"[bold]{key}[/]: {value}" for key, value in rows)
        self.console.print(Panel(body, title=title))

    def _table(
        self,
        title: str,
        headers: tuple[str, ...],
        rows: Iterable[tuple[str, ...]],
    ) -> None:
        if self.console is None or Table is None:
            self._print(title)
            self._print("\t".join(headers))
            for row in rows:
                self._print("\t".join(row))
            return
        table = Table(title=title)
        for header in headers:
            table.add_column(header)
        count = 0
        for row in rows:
            count += 1
            table.add_row(*row)
        if count == 0:
            self.console.print(f"{title}: none")
            return
        self.console.print(table)

    def _print(self, value: str) -> None:
        if self.console is not None:
            self.console.print(value)
            return
        print(value, file=self.file)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
