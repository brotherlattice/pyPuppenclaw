from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator

from .errors import ConfigurationError
from .models import AgentKind, PermissionMode
from .paths import (
    default_config_path,
    default_data_dir,
    default_generated_config_path,
    default_log_dir,
    default_state_dir,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

import tomli_w
from pydantic import BaseModel, ConfigDict


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LocalWorkerSettings(ConfigModel):
    id: str = "local"
    label: str = "Local Worker"
    labels: list[str] = Field(default_factory=lambda: ["local"])
    project_roots: list[str] = Field(default_factory=list, alias="projectRoots")


class MediatedRemoteControlSettings(ConfigModel):
    enabled: bool = True


class PurePipeRemoteControlSettings(ConfigModel):
    enabled: bool = False
    allow_from: list[str] = Field(default_factory=list, alias="allowFrom")
    allowed_agents: list[AgentKind] = Field(default_factory=list, alias="allowedAgents")


class RemoteControlSettings(ConfigModel):
    mediated: MediatedRemoteControlSettings = Field(default_factory=MediatedRemoteControlSettings)
    pure_pipe: PurePipeRemoteControlSettings = Field(
        default_factory=PurePipeRemoteControlSettings,
        alias="purePipe",
    )
    require_conversation_binding: bool = Field(default=True, alias="requireConversationBinding")


class SourceSettings(ConfigModel):
    kind: Literal["checkout", "binary"] = "checkout"
    checkout_path: Path | None = Field(default=None, alias="checkoutPath")
    daemon_command: list[str] | None = Field(default=None, alias="daemonCommand")
    node_command: str = Field(default="node", alias="nodeCommand")
    npm_command: str = Field(default="npm", alias="npmCommand")
    install_args: list[str] = Field(default_factory=lambda: ["install"], alias="installArgs")
    build_args: list[str] = Field(default_factory=lambda: ["run", "build"], alias="buildArgs")

    @field_validator("checkout_path", mode="before")
    @classmethod
    def _coerce_checkout_path(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        return Path(value)

    def resolve_checkout_path(self) -> Path | None:
        if self.checkout_path is not None:
            return self.checkout_path.expanduser().resolve()

        env_path = os.environ.get("PUPPENCLAW_SOURCE_DIR")
        if env_path:
            candidate = Path(env_path).expanduser().resolve()
            if candidate.exists():
                return candidate

        local_candidates = [
            Path.cwd() / "puppenclaw",
            Path.cwd().parent / "puppenclaw",
            Path(__file__).resolve().parents[3] / "puppenclaw",
        ]
        for candidate in local_candidates:
            if candidate.exists():
                return candidate.resolve()
        return None


class DaemonSettings(ConfigModel):
    host: str = "127.0.0.1"
    port: int = 18795
    startup_timeout: float = Field(default=30.0, alias="startupTimeout")
    stop_timeout: float = Field(default=10.0, alias="stopTimeout")
    request_timeout: float = Field(default=60.0, alias="requestTimeout")
    state_dir: Path = Field(default_factory=default_state_dir, alias="stateDir")
    data_dir: Path = Field(default_factory=default_data_dir, alias="dataDir")
    log_dir: Path = Field(default_factory=default_log_dir, alias="logDir")
    generated_config_path: Path = Field(
        default_factory=default_generated_config_path, alias="generatedConfigPath"
    )

    @field_validator("state_dir", "data_dir", "log_dir", "generated_config_path", mode="before")
    @classmethod
    def _coerce_path(cls, value: Any) -> Any:
        return Path(value) if value not in (None, "") else value

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class AgentSettings(ConfigModel):
    default_agent: AgentKind = Field(default="claude", alias="defaultAgent")
    acpx_command: str | None = Field(default=None, alias="acpxCommand")
    codex_command: str = Field(default="npx @zed-industries/codex-acp", alias="codexCommand")
    claude_command: str = Field(
        default="npx -y @zed-industries/claude-agent-acp",
        alias="claudeCommand",
    )
    permission_mode: PermissionMode = Field(default="approve-reads", alias="permissionMode")
    max_sessions: int = Field(default=5, alias="maxSessions")
    session_ttl_minutes: int = Field(default=60, alias="sessionTtlMinutes")
    stream_output: bool = Field(default=True, alias="streamOutput")
    mcp_servers: dict[str, Any] = Field(default_factory=dict, alias="mcpServers")


class OrchestrationSettings(ConfigModel):
    enabled: bool = True
    max_campaigns: int = Field(default=32, alias="maxCampaigns")
    artifact_retention_hours: int = Field(default=336, alias="artifactRetentionHours")
    allow_local_command_execution: bool = Field(default=True, alias="allowLocalCommandExecution")
    default_project_root: Path | None = Field(default=None, alias="defaultProjectRoot")
    gpt_researcher_command: str | None = Field(default=None, alias="gptResearcherCommand")
    fusion_arbiter_command: str | None = Field(default=None, alias="fusionArbiterCommand")
    local_worker: LocalWorkerSettings = Field(
        default_factory=LocalWorkerSettings,
        alias="localWorker",
    )

    @field_validator("default_project_root", mode="before")
    @classmethod
    def _coerce_project_root(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        return Path(value)


class WrapperSettings(ConfigModel):
    source: SourceSettings = Field(default_factory=SourceSettings)
    daemon: DaemonSettings = Field(default_factory=DaemonSettings)
    agents: AgentSettings = Field(default_factory=AgentSettings)
    orchestration: OrchestrationSettings = Field(default_factory=OrchestrationSettings)
    remote_control: RemoteControlSettings = Field(
        default_factory=RemoteControlSettings,
        alias="remoteControl",
    )

    def to_puppenclaw_config(self) -> dict[str, Any]:
        agent_commands = {
            "codex": self.agents.codex_command,
            "claude": self.agents.claude_command,
        }
        payload: dict[str, Any] = {
            "backend": "local",
            "daemonUrl": self.daemon.base_url,
            "defaultAgent": self.agents.default_agent,
            "maxSessions": self.agents.max_sessions,
            "permissionMode": self.agents.permission_mode,
            "sessionTtlMinutes": self.agents.session_ttl_minutes,
            "streamOutput": self.agents.stream_output,
            "agentCommands": agent_commands,
            "mcpServers": self.agents.mcp_servers,
            "remoteControl": self.remote_control.model_dump(by_alias=True, exclude_none=True),
            "orchestration": self._orchestration_payload(),
        }
        if self.agents.acpx_command:
            payload["acpxCommand"] = self.agents.acpx_command
        return payload

    def _orchestration_payload(self) -> dict[str, Any]:
        payload = self.orchestration.model_dump(by_alias=True, exclude_none=True)
        if self.orchestration.default_project_root is not None:
            payload["defaultProjectRoot"] = str(
                self.orchestration.default_project_root.expanduser().resolve()
            )
        payload["localWorker"] = self._local_worker_payload()
        return payload

    def _local_worker_payload(self) -> dict[str, Any]:
        payload = self.orchestration.local_worker.model_dump(by_alias=True, exclude_none=True)
        payload["projectRoots"] = [
            str(Path(root).expanduser().resolve())
            for root in self.orchestration.local_worker.project_roots
        ]
        return payload

    def ensure_directories(self) -> None:
        for path in (self.daemon.state_dir, self.daemon.data_dir, self.daemon.log_dir):
            path.mkdir(parents=True, exist_ok=True)


def load_settings(path: Path | None = None) -> WrapperSettings:
    config_path = (path or default_config_path()).expanduser().resolve()
    if not config_path.exists():
        settings = WrapperSettings()
        settings.ensure_directories()
        return settings

    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    settings = WrapperSettings.model_validate(data)
    settings.ensure_directories()
    return settings


def save_settings(settings: WrapperSettings, path: Path | None = None) -> Path:
    config_path = (path or default_config_path()).expanduser().resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    settings.ensure_directories()
    config_path.write_text(
        tomli_w.dumps(settings.model_dump(mode="json", by_alias=True, exclude_none=True)),
        encoding="utf-8",
    )
    return config_path


def write_generated_puppenclaw_config(settings: WrapperSettings, path: Path | None = None) -> Path:
    target = (path or settings.daemon.generated_config_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(settings.to_puppenclaw_config(), indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def ensure_checkout_path(settings: WrapperSettings) -> Path:
    checkout = settings.source.resolve_checkout_path()
    if checkout is None:
        raise ConfigurationError(
            "Could not resolve a Puppenclaw checkout. Set PUPPENCLAW_SOURCE_DIR "
            "or source.checkoutPath."
        )
    return checkout
