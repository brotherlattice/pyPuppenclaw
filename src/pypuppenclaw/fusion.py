from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .errors import ConfigurationError
from .models import (
    AgentKind,
    ArtifactListDetails,
    ArtifactListQuery,
    ArtifactReadDetails,
    ArtifactReadQuery,
    CampaignActionRequest,
    CampaignEventsDetails,
    CampaignEventsQuery,
    CampaignRunRequest,
    CampaignStatusQuery,
    CampaignStatusSnapshot,
    ContextSyncRequest,
    ProjectCreateRequest,
    SendSessionRequest,
    SessionOutputDetails,
    StartSessionRequest,
)
from .project_config import PuppencodeProjectConfig, load_project_config
from .render import PuppencodeRenderer
from .service import PuppenclawService

TERMINAL_CAMPAIGN_STATES = {"completed", "failed", "cancelled", "waiting_approval"}


@dataclass(frozen=True)
class FusionRunOptions:
    """Runtime overrides for a puppencode campaign or agent turn."""

    cwd: Path
    config_path: Path | None = None
    prompt: str | None = None
    project_id: str | None = None
    worker_id: str | None = None
    agent: AgentKind | None = None
    model: str | None = None
    effort: str | None = None
    validation_command: str | None = None
    include_files: tuple[str, ...] | None = None
    wait: bool = True
    poll_interval: float = 2.0
    timeout: float | None = None


class FusionRunner:
    """High-level terminal workflow around Puppenclaw's orchestration API."""

    def __init__(
        self,
        *,
        service: PuppenclawService | None = None,
        renderer: PuppencodeRenderer | None = None,
    ) -> None:
        self.service = service or PuppenclawService()
        self.renderer = renderer or PuppencodeRenderer()

    def ensure_ready(self) -> None:
        self.renderer.info("checking Puppenclaw installation")
        self.service.install()
        self.renderer.info("starting or reusing the local Puppenclaw daemon")
        self.service.start()

    def load_config(self, options: FusionRunOptions) -> PuppencodeProjectConfig:
        return load_project_config(options.config_path, cwd=options.cwd)

    def prepare_project(self, options: FusionRunOptions) -> str:
        config = self.load_config(options)
        project_id = options.project_id or config.resolved_project_id
        project_name = config.resolved_project_name
        agent = options.agent or config.preferred_agent
        model = options.model or config.model
        effort = options.effort or config.effort
        include_files = list(options.include_files or tuple(config.include_files))

        self.renderer.info(f"registering project {project_id!r}")
        self.service.client.orchestrator.create_project(
            ProjectCreateRequest(
                id=project_id,
                name=project_name,
                rootDir=str(options.cwd.expanduser().resolve()),
                defaultAgent=agent,
                fusionPreferredAgent=agent,
                effort=effort,
                model=model,
            )
        )
        if include_files or config.memory_text:
            self.renderer.info("syncing project context")
            self.service.client.orchestrator.sync_context(
                ContextSyncRequest(
                    projectId=project_id,
                    includeFiles=include_files,
                    memoryText=config.memory_text,
                )
            )
        return project_id

    def run_fusion(self, prompt: str, options: FusionRunOptions) -> CampaignStatusSnapshot:
        if not prompt.strip():
            raise ConfigurationError("A non-empty prompt is required.")
        self.ensure_ready()
        config = self.load_config(options)
        project_id = self.prepare_project(options)
        worker_id = options.worker_id or config.worker_id
        agent = options.agent or config.preferred_agent
        validation_command = options.validation_command or config.validation_command

        self.renderer.info(f"starting puppenfusion campaign on worker {worker_id!r}")
        result = self.service.client.orchestrator.run_campaign(
            CampaignRunRequest(
                projectId=project_id,
                workerId=worker_id,
                name=_campaign_name(prompt),
                template="puppenfusion",
                task=prompt,
                fusionPreferredAgent=agent,
                evaluationCommand=validation_command,
            )
        )
        snapshot = result.details
        self.renderer.campaign(snapshot)
        if not options.wait or snapshot.campaign.state in TERMINAL_CAMPAIGN_STATES:
            return snapshot
        return self.wait_for_campaign(
            snapshot.campaign.id,
            poll_interval=options.poll_interval,
            timeout=options.timeout,
        )

    def run_agent(self, prompt: str, options: FusionRunOptions) -> SessionOutputDetails:
        if not prompt.strip():
            raise ConfigurationError("A non-empty prompt is required.")
        self.ensure_ready()
        config = self.load_config(options)
        agent = options.agent or config.preferred_agent
        include_files = list(options.include_files or tuple(config.include_files))
        session_name = f"puppencode-{agent}-{_timestamp_slug()}"
        self.renderer.info(f"starting {agent} session {session_name!r}")
        result = self.service.client.sessions.start(
            StartSessionRequest(
                agent=agent,
                name=session_name,
                directory=str(options.cwd.expanduser().resolve()),
                task=prompt,
                effort=options.effort or config.effort,
                model=options.model or config.model,
                contextFiles=include_files,
            )
        )
        if result.details.output:
            self.renderer.text(result.details.output)
        return result.details

    def send_agent(self, session_name: str, message: str) -> SessionOutputDetails:
        self.ensure_ready()
        result = self.service.client.sessions.send(
            SendSessionRequest(name=session_name, message=message)
        )
        if result.details.output:
            self.renderer.text(result.details.output)
        return result.details

    def wait_for_campaign(
        self,
        campaign_id: str,
        *,
        poll_interval: float = 2.0,
        timeout: float | None = None,
    ) -> CampaignStatusSnapshot:
        deadline = None if timeout is None else time.monotonic() + timeout
        last_state: str | None = None
        while True:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"Timed out waiting for campaign {campaign_id}.")
            result = self.service.client.orchestrator.status(
                CampaignStatusQuery(campaignId=campaign_id)
            )
            snapshot = result.details
            if not isinstance(snapshot, CampaignStatusSnapshot):
                raise ConfigurationError(f"Unexpected campaign status response for {campaign_id}.")
            if snapshot.campaign.state != last_state:
                self.renderer.info(f"campaign {campaign_id} is {snapshot.campaign.state}")
                self.renderer.campaign(snapshot)
                last_state = snapshot.campaign.state
            if snapshot.campaign.state in TERMINAL_CAMPAIGN_STATES:
                return snapshot
            time.sleep(poll_interval)

    def campaign_status(self, campaign_id: str) -> CampaignStatusSnapshot:
        self.ensure_ready()
        result = self.service.client.orchestrator.status(
            CampaignStatusQuery(campaignId=campaign_id)
        )
        snapshot = result.details
        if not isinstance(snapshot, CampaignStatusSnapshot):
            raise ConfigurationError(f"Unexpected campaign status response for {campaign_id}.")
        self.renderer.campaign(snapshot)
        return snapshot

    def artifacts(
        self,
        *,
        campaign_id: str | None = None,
        project_id: str | None = None,
    ) -> ArtifactListDetails:
        self.ensure_ready()
        result = self.service.client.orchestrator.artifacts(
            ArtifactListQuery(campaignId=campaign_id, projectId=project_id)
        )
        self.renderer.artifacts(result.details.artifacts)
        return result.details

    def read_artifact(self, artifact_id: str, *, limit_chars: int = 120_000) -> ArtifactReadDetails:
        self.ensure_ready()
        result = self.service.client.orchestrator.read_artifact(
            ArtifactReadQuery(artifactId=artifact_id, limitChars=limit_chars)
        )
        self.renderer.text(result.details.text)
        if result.details.truncated:
            self.renderer.warning(f"artifact truncated at {result.details.limit_chars} characters")
        return result.details

    def events(
        self,
        campaign_id: str,
        *,
        after: str | None = None,
        limit: int = 100,
    ) -> CampaignEventsDetails:
        self.ensure_ready()
        result = self.service.client.orchestrator.events(
            CampaignEventsQuery(campaignId=campaign_id, after=after, limit=limit)
        )
        self.renderer.events(result.details)
        return result.details

    def approve(self, campaign_id: str) -> CampaignStatusSnapshot:
        self.ensure_ready()
        result = self.service.client.orchestrator.approve(
            CampaignActionRequest(campaignId=campaign_id)
        )
        self.renderer.campaign(result.details)
        return result.details

    def cancel(self, campaign_id: str):
        self.ensure_ready()
        result = self.service.client.orchestrator.cancel(
            CampaignActionRequest(campaignId=campaign_id)
        )
        self.renderer.json(result.details)
        return result.details


def _campaign_name(prompt: str) -> str:
    stem = " ".join(prompt.strip().split())[:48].strip()
    return f"puppencode {_timestamp_slug()} {stem}".strip()


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
