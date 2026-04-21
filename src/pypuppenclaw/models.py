from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

AgentKind = Literal["claude", "codex"]
PermissionMode = Literal["approve-reads", "approve-all", "deny-all"]
PlanningProfile = Literal["off", "quick", "deep"]
ResponseFormat = Literal["text", "json"]
CampaignTemplate = Literal[
    "custom",
    "literature_review",
    "baseline_from_scratch",
    "ablation_campaign",
    "self_improvement_loop",
    "puppenfusion",
]
SessionState = Literal["idle", "running", "waiting_input", "completed", "failed", "stopped"]
CampaignState = Literal["draft", "running", "waiting_approval", "completed", "failed", "cancelled"]
RunState = Literal[
    "pending",
    "queued",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
]
OrchestrationStepKind = Literal[
    "judge",
    "research",
    "plan",
    "code",
    "experiment",
    "eval",
    "artifact_sync",
    "review",
    "publish",
    "handoff",
]
OrchestrationExecutor = Literal["acp", "command"]
LogScope = Literal["session", "campaign", "run"]
ExposureMode = Literal["read-only", "execute"]


class Model(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ToolTextBlock(Model):
    type: Literal["text"] = "text"
    text: str


TDetails = TypeVar("TDetails", bound=Model)


@dataclass(frozen=True)
class OperationResult(Generic[TDetails]):
    content: list[ToolTextBlock]
    details: TDetails

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.content)


class HealthStatus(Model):
    ok: bool
    sessions: int = 0


class TokenUsage(Model):
    used: int | None = None
    size: int | None = None
    input: int | None = None
    output: int | None = None
    cached: int | None = None


class SessionTranscriptEntry(Model):
    role: Literal["system", "user", "assistant", "status"]
    text: str
    created_at: str = Field(alias="createdAt")


class ContextFileEntry(Model):
    path: str
    resolved_path: str = Field(alias="resolvedPath")
    bytes: int
    truncated: bool


class AcpxSessionHandle(Model):
    runtime_session_name: str = Field(alias="runtimeSessionName")
    cwd: str
    agent: AgentKind
    mode: Literal["persistent"]


class ConversationScope(Model):
    channel: str
    account_id: str = Field(alias="accountId")
    conversation_id: str = Field(alias="conversationId")
    parent_conversation_id: str | None = Field(default=None, alias="parentConversationId")
    thread_id: str | int | None = Field(default=None, alias="threadId")


class SessionSourceInfo(Model):
    kind: Literal["tool", "command", "daemon"]
    channel: str | None = None
    requester_sender_id: str | None = Field(default=None, alias="requesterSenderId")
    binding_id: str | None = Field(default=None, alias="bindingId")


class SessionInfo(Model):
    name: str
    agent: AgentKind
    directory: str
    state: SessionState
    created_at: str = Field(alias="createdAt")
    last_activity: str = Field(alias="lastActivity")
    permission_mode: PermissionMode = Field(alias="permissionMode")
    effort: str | None = None
    planning_profile: PlanningProfile | None = Field(default=None, alias="planningProfile")
    model: str | None = None
    token_usage: TokenUsage | None = Field(default=None, alias="tokenUsage")
    pending_question: str | None = Field(default=None, alias="pendingQuestion")
    last_error: str | None = Field(default=None, alias="lastError")
    warnings: list[str] = Field(default_factory=list)
    transcript: list[SessionTranscriptEntry] = Field(default_factory=list)
    handle: AcpxSessionHandle | None = None
    last_stop_reason: str | None = Field(default=None, alias="lastStopReason")
    source: SessionSourceInfo | None = None
    origin: ConversationScope | None = None


class RuntimeSessionStatus(Model):
    exists: bool | None = None


class SessionsListDetails(Model):
    sessions: list[SessionInfo] = Field(default_factory=list)


class SessionStatusDetails(Model):
    session: SessionInfo
    runtime: RuntimeSessionStatus = Field(default_factory=RuntimeSessionStatus)


class SessionOutputDetails(Model):
    session: SessionInfo
    output: str | None = None


class SessionCostDetails(Model):
    name: str
    token_usage: TokenUsage | None = Field(default=None, alias="tokenUsage")
    pricing: dict[str, Any] | None = None
    note: str


class ProjectRecord(Model):
    id: str
    name: str
    root_dir: str = Field(alias="rootDir")
    description: str | None = None
    default_agent: AgentKind | None = Field(default=None, alias="defaultAgent")
    fusion_preferred_agent: AgentKind | None = Field(default=None, alias="fusionPreferredAgent")
    planning_profile: PlanningProfile | None = Field(default=None, alias="planningProfile")
    permission_mode: PermissionMode | None = Field(default=None, alias="permissionMode")
    effort: str | None = None
    model: str | None = None
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    last_context_sync_at: str | None = Field(default=None, alias="lastContextSyncAt")


class WorkerManifest(Model):
    id: str
    label: str
    format: ResponseFormat | None = None
    labels: list[str] = Field(default_factory=list)
    project_roots: list[str] = Field(default_factory=list, alias="projectRoots")
    supported_steps: list[OrchestrationStepKind] = Field(
        default_factory=list, alias="supportedSteps"
    )
    executors: list[OrchestrationExecutor] = Field(default_factory=list)
    default_agent: AgentKind | None = Field(default=None, alias="defaultAgent")
    max_concurrent_runs: int = Field(default=1, alias="maxConcurrentRuns")
    admin_only_raw_sessions: bool = Field(default=True, alias="adminOnlyRawSessions")
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class ProjectContextBundle(Model):
    project_id: str = Field(alias="projectId")
    project_name: str = Field(alias="projectName")
    root_dir: str = Field(alias="rootDir")
    created_at: str = Field(alias="createdAt")
    include_files: list[ContextFileEntry] = Field(default_factory=list, alias="includeFiles")
    notes: str | None = None
    memory_text: str | None = Field(default=None, alias="memoryText")
    prompt_text: str = Field(alias="promptText")


class ArtifactFileRecord(Model):
    relative_path: str = Field(alias="relativePath")
    size_bytes: int = Field(alias="sizeBytes")
    sha256: str


class ArtifactRecord(Model):
    id: str
    project_id: str = Field(alias="projectId")
    campaign_id: str | None = Field(default=None, alias="campaignId")
    run_id: str | None = Field(default=None, alias="runId")
    step_id: str | None = Field(default=None, alias="stepId")
    site_id: str = Field(alias="siteId")
    kind: str
    title: str
    summary: str | None = None
    relative_path: str = Field(alias="relativePath")
    created_at: str = Field(alias="createdAt")
    size_bytes: int = Field(alias="sizeBytes")
    sha256: str
    files: list[ArtifactFileRecord] | None = None


class ProjectCreateDetails(Model):
    project: ProjectRecord


class WorkerRegisterDetails(Model):
    worker: WorkerManifest


class ContextSyncDetails(Model):
    project: ProjectRecord
    artifact: ArtifactRecord
    bundle: ProjectContextBundle


class CampaignStepRecord(Model):
    id: str
    title: str
    kind: OrchestrationStepKind
    executor: OrchestrationExecutor
    instruction: str | None = None
    command: str | None = None
    context_files: list[str] = Field(default_factory=list, alias="contextFiles")
    approval_required: bool = Field(alias="approvalRequired")
    agent: AgentKind | None = None
    phase_group: str | None = Field(default=None, alias="phaseGroup")
    session_scope: Literal["campaign", "step"] | None = Field(default=None, alias="sessionScope")
    working_directory: str | None = Field(default=None, alias="workingDirectory")
    env: dict[str, str] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, alias="timeoutMs")
    retry_limit: int = Field(alias="retryLimit")


class CampaignSpecRecord(Model):
    id: str
    project_id: str = Field(alias="projectId")
    worker_id: str = Field(alias="workerId")
    name: str
    template: CampaignTemplate
    task: str | None = None
    evaluation_command: str | None = Field(default=None, alias="evaluationCommand")
    experiment_commands: list[str] = Field(default_factory=list, alias="experimentCommands")
    experiment_parallelism: int = Field(alias="experimentParallelism")
    iterations: int
    steps: list[CampaignStepRecord] = Field(default_factory=list)
    acp_session_name: str | None = Field(default=None, alias="acpSessionName")
    current_step_index: int = Field(alias="currentStepIndex")
    current_run_id: str | None = Field(default=None, alias="currentRunId")
    waiting_approval_step_id: str | None = Field(default=None, alias="waitingApprovalStepId")
    last_error: str | None = Field(default=None, alias="lastError")
    last_progress_at: str = Field(alias="lastProgressAt")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    state: CampaignState


class RunRecord(Model):
    id: str
    campaign_id: str = Field(alias="campaignId")
    project_id: str = Field(alias="projectId")
    worker_id: str = Field(alias="workerId")
    step_id: str = Field(alias="stepId")
    step_title: str = Field(alias="stepTitle")
    step_index: int = Field(alias="stepIndex")
    kind: OrchestrationStepKind
    executor: OrchestrationExecutor
    state: RunState
    started_at: str = Field(alias="startedAt")
    updated_at: str = Field(alias="updatedAt")
    last_progress_at: str = Field(alias="lastProgressAt")
    finished_at: str | None = Field(default=None, alias="finishedAt")
    summary: str | None = None
    output_text: str | None = Field(default=None, alias="outputText")
    exit_code: int | None = Field(default=None, alias="exitCode")
    command: str | None = None
    session_name: str | None = Field(default=None, alias="sessionName")
    attempts: int
    failure_code: str | None = Field(default=None, alias="failureCode")
    failure_category: str | None = Field(default=None, alias="failureCategory")


class CampaignProgressSnapshot(Model):
    total_steps: int = Field(alias="totalSteps")
    completed_steps: int = Field(alias="completedSteps")
    failed_steps: int = Field(alias="failedSteps")
    current_step_index: int = Field(alias="currentStepIndex")
    experiment_parallelism: int = Field(alias="experimentParallelism")
    current_step_id: str | None = Field(default=None, alias="currentStepId")
    current_step_title: str | None = Field(default=None, alias="currentStepTitle")
    current_run_id: str | None = Field(default=None, alias="currentRunId")
    last_progress_at: str = Field(alias="lastProgressAt")


class CampaignStatusSnapshot(Model):
    campaign: CampaignSpecRecord
    project: ProjectRecord | None = None
    worker: WorkerManifest | None = None
    runs: list[RunRecord] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    progress: CampaignProgressSnapshot


class CampaignCancelDetails(Model):
    campaign: CampaignSpecRecord


class OrchestratorStatusSummary(Model):
    projects: list[ProjectRecord] = Field(default_factory=list)
    workers: list[WorkerManifest] = Field(default_factory=list)
    campaigns: list[CampaignSpecRecord] = Field(default_factory=list)


class ArtifactListDetails(Model):
    artifacts: list[ArtifactRecord] = Field(default_factory=list)


class SiteAgentAvailability(Model):
    agent: AgentKind
    command: str
    configured: bool


class SiteSessionSnapshot(Model):
    name: str
    agent: AgentKind
    directory: str
    state: SessionState
    last_activity: str = Field(alias="lastActivity")
    source_kind: str | None = Field(default=None, alias="sourceKind")


class SiteCampaignSnapshot(Model):
    id: str
    name: str
    project_id: str = Field(alias="projectId")
    worker_id: str = Field(alias="workerId")
    template: CampaignTemplate
    state: CampaignState
    current_step_index: int = Field(alias="currentStepIndex")
    experiment_parallelism: int = Field(alias="experimentParallelism")
    last_progress_at: str = Field(alias="lastProgressAt")
    last_error: str | None = Field(default=None, alias="lastError")


class SiteWorkerSnapshot(Model):
    id: str
    label: str
    labels: list[str] = Field(default_factory=list)
    project_roots: list[str] = Field(default_factory=list, alias="projectRoots")
    supported_steps: list[OrchestrationStepKind] = Field(
        default_factory=list, alias="supportedSteps"
    )
    executors: list[OrchestrationExecutor] = Field(default_factory=list)
    default_agent: AgentKind | None = Field(default=None, alias="defaultAgent")
    max_concurrent_runs: int = Field(alias="maxConcurrentRuns")
    active_campaigns: int = Field(alias="activeCampaigns")


class ExposureRecord(Model):
    binding_id: str = Field(alias="bindingId")
    conversation: ConversationScope
    allow_pure_pipe: bool = Field(alias="allowPurePipe")
    allowed_agents: list[AgentKind] = Field(default_factory=list, alias="allowedAgents")
    mode: ExposureMode
    allowed_verbs: list[str] = Field(default_factory=list, alias="allowedVerbs")
    allowed_project_roots: list[str] = Field(default_factory=list, alias="allowedProjectRoots")
    updated_at: str = Field(alias="updatedAt")


class SiteStatus(Model):
    site_id: str = Field(alias="siteId")
    label: str
    backend: str
    plugin_health: str = Field(alias="pluginHealth")
    openclaw_runtime: dict[str, Any] = Field(alias="openclawRuntime")
    default_agent: AgentKind = Field(alias="defaultAgent")
    available_agents: list[SiteAgentAvailability] = Field(
        default_factory=list, alias="availableAgents"
    )
    orchestration: dict[str, Any]
    sessions: dict[str, Any]
    campaigns: dict[str, Any]
    workers: list[SiteWorkerSnapshot] = Field(default_factory=list)
    exposures: dict[str, Any]


class LogEntry(Model):
    id: str
    title: str
    state: str | None = None
    updated_at: str = Field(alias="updatedAt")
    text: str


class LogsResult(Model):
    scope: LogScope
    target_id: str = Field(alias="targetId")
    limit_chars: int = Field(alias="limitChars")
    follow_requested: bool = Field(alias="followRequested")
    follow_supported: bool = Field(alias="followSupported")
    text: str
    entries: list[LogEntry] = Field(default_factory=list)


class OkResult(Model):
    ok: bool


class InstallManifest(Model):
    source_kind: str = Field(alias="sourceKind")
    source_path: str = Field(alias="sourcePath")
    daemon_command: list[str] = Field(alias="daemonCommand")
    package_name: str | None = Field(default=None, alias="packageName")
    version: str | None = None
    installed_at: str = Field(alias="installedAt")


class DaemonRuntimeInfo(Model):
    pid: int
    base_url: str = Field(alias="baseUrl")
    data_dir: str = Field(alias="dataDir")
    log_path: str = Field(alias="logPath")
    config_path: str = Field(alias="configPath")
    command: list[str]
    started_at: str = Field(alias="startedAt")


class ManagedDaemonStatus(Model):
    running: bool
    healthy: bool
    runtime: DaemonRuntimeInfo | None = None
    install_manifest: InstallManifest | None = Field(default=None, alias="installManifest")


class StartSessionRequest(Model):
    agent: AgentKind
    name: str
    directory: str
    task: str
    format: ResponseFormat | None = None
    permission_mode: PermissionMode | None = Field(default=None, alias="permissionMode")
    effort: str | None = None
    planning_profile: PlanningProfile | None = Field(default=None, alias="planningProfile")
    model: str | None = None
    context_files: list[str] = Field(default_factory=list, alias="contextFiles")


class SendSessionRequest(Model):
    name: str
    message: str
    format: ResponseFormat | None = None
    stream: bool | None = None
    ultrathink: bool | None = None
    context_files: list[str] = Field(default_factory=list, alias="contextFiles")


class ResumeSessionRequest(Model):
    name: str
    format: ResponseFormat | None = None


class ForkSessionRequest(Model):
    source: str
    target: str
    format: ResponseFormat | None = None
    model: str | None = None
    effort: str | None = None


class ProjectCreateRequest(Model):
    id: str | None = None
    name: str
    root_dir: str = Field(alias="rootDir")
    description: str | None = None
    default_agent: AgentKind | None = Field(default=None, alias="defaultAgent")
    fusion_preferred_agent: AgentKind | None = Field(default=None, alias="fusionPreferredAgent")
    planning_profile: PlanningProfile | None = Field(default=None, alias="planningProfile")
    permission_mode: PermissionMode | None = Field(default=None, alias="permissionMode")
    effort: str | None = None
    model: str | None = None
    format: ResponseFormat | None = None


class ContextSyncRequest(Model):
    project_id: str = Field(alias="projectId")
    include_files: list[str] = Field(default_factory=list, alias="includeFiles")
    memory_text: str | None = Field(default=None, alias="memoryText")
    notes: str | None = None
    format: ResponseFormat | None = None


class CampaignStepRequest(Model):
    id: str | None = None
    title: str
    kind: OrchestrationStepKind
    executor: OrchestrationExecutor
    instruction: str | None = None
    command: str | None = None
    context_files: list[str] = Field(default_factory=list, alias="contextFiles")
    approval_required: bool = Field(default=False, alias="approvalRequired")
    agent: AgentKind | None = None
    phase_group: str | None = Field(default=None, alias="phaseGroup")
    session_scope: Literal["campaign", "step"] | None = Field(default=None, alias="sessionScope")
    working_directory: str | None = Field(default=None, alias="workingDirectory")
    env: dict[str, str] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, alias="timeoutMs")
    retry_limit: int = Field(default=0, alias="retryLimit")


class CampaignRunRequest(Model):
    project_id: str = Field(alias="projectId")
    worker_id: str = Field(alias="workerId")
    name: str
    format: ResponseFormat | None = None
    template: CampaignTemplate = "custom"
    task: str | None = None
    fusion_preferred_agent: AgentKind | None = Field(default=None, alias="fusionPreferredAgent")
    use_external_arbiter: bool | None = Field(default=None, alias="useExternalArbiter")
    fusion_base_ref: str | None = Field(default=None, alias="fusionBaseRef")
    evaluation_command: str | None = Field(default=None, alias="evaluationCommand")
    experiment_commands: list[str] = Field(default_factory=list, alias="experimentCommands")
    experiment_parallelism: int = Field(default=1, alias="experimentParallelism")
    iterations: int = 1
    steps: list[CampaignStepRequest] = Field(default_factory=list)


class CampaignStatusQuery(Model):
    campaign_id: str | None = Field(default=None, alias="campaignId")
    project_id: str | None = Field(default=None, alias="projectId")
    format: ResponseFormat | None = None


class ArtifactListQuery(Model):
    campaign_id: str | None = Field(default=None, alias="campaignId")
    project_id: str | None = Field(default=None, alias="projectId")
    format: ResponseFormat | None = None


class CampaignActionRequest(Model):
    campaign_id: str = Field(alias="campaignId")
    format: ResponseFormat | None = None


class SiteStatusQuery(Model):
    verbose: bool = False
    format: ResponseFormat | None = None


class LogsQuery(Model):
    session_name: str | None = Field(default=None, alias="sessionName")
    campaign_id: str | None = Field(default=None, alias="campaignId")
    run_id: str | None = Field(default=None, alias="runId")
    limit_chars: int = Field(default=8000, alias="limitChars")
    follow: bool = False
    format: ResponseFormat | None = None
