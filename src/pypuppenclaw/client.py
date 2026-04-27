from __future__ import annotations

from typing import Any, TypeVar, overload
from urllib.parse import quote

import httpx
from pydantic import TypeAdapter

from .errors import RequestError
from .models import (
    ArtifactListDetails,
    ArtifactListQuery,
    ArtifactReadDetails,
    ArtifactReadQuery,
    CampaignActionRequest,
    CampaignCancelDetails,
    CampaignEventsDetails,
    CampaignEventsQuery,
    CampaignRunRequest,
    CampaignStatusQuery,
    CampaignStatusSnapshot,
    ContextSyncDetails,
    ContextSyncRequest,
    ForkSessionRequest,
    HealthStatus,
    LogsQuery,
    LogsResult,
    OkResult,
    OperationResult,
    OrchestratorStatusSummary,
    ProjectCreateDetails,
    ProjectCreateRequest,
    ReassessmentRecord,
    ReassessmentReportDetails,
    ReassessmentReportQuery,
    ReassessmentStartRequest,
    ReassessmentStatusDetails,
    ReassessmentStatusQuery,
    ResumeSessionRequest,
    SendSessionRequest,
    SessionCostDetails,
    SessionOutputDetails,
    SessionsListDetails,
    SessionStatusDetails,
    SiteStatus,
    SiteStatusQuery,
    StartSessionRequest,
    ToolTextBlock,
    WorkerManifest,
    WorkerRegisterDetails,
)

TModel = TypeVar("TModel")


class _BaseAPI:
    def __init__(self, client: PuppenclawClient) -> None:
        self._client = client

    def _tool_request(
        self,
        method: str,
        path: str,
        *,
        model: type[TModel],
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> OperationResult[TModel]:
        payload = self._client._request(method, path, json_body=json_body, params=params)
        details = TypeAdapter(model).validate_python(payload["details"])
        content = TypeAdapter(list[ToolTextBlock]).validate_python(payload.get("content", []))
        return OperationResult(content=content, details=details)


class SessionsAPI(_BaseAPI):
    """Session management endpoints exposed by the Puppenclaw daemon."""

    def list(self) -> OperationResult[SessionsListDetails]:
        return self._tool_request("GET", "/sessions", model=SessionsListDetails)

    def get(self, name: str) -> OperationResult[SessionStatusDetails]:
        return self._tool_request(
            "GET", f"/session/{quote(name, safe='')}", model=SessionStatusDetails
        )

    def start(self, request: StartSessionRequest) -> OperationResult[SessionOutputDetails]:
        return self._tool_request(
            "POST",
            "/session/start",
            model=SessionOutputDetails,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )

    def send(self, request: SendSessionRequest) -> OperationResult[SessionOutputDetails]:
        return self._tool_request(
            "POST",
            f"/session/{quote(request.name, safe='')}/send",
            model=SessionOutputDetails,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )

    def resume(self, request: ResumeSessionRequest) -> OperationResult[SessionOutputDetails]:
        return self._tool_request(
            "POST",
            f"/session/{quote(request.name, safe='')}/resume",
            model=SessionOutputDetails,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )

    def stop(self, name: str) -> OperationResult[SessionStatusDetails]:
        return self._tool_request(
            "DELETE",
            f"/session/{quote(name, safe='')}",
            model=SessionStatusDetails,
        )

    def fork(self, request: ForkSessionRequest) -> OperationResult[SessionOutputDetails]:
        return self._tool_request(
            "POST",
            f"/session/{quote(request.source, safe='')}/fork",
            model=SessionOutputDetails,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )

    def cost(self, name: str) -> OperationResult[SessionCostDetails]:
        return self._tool_request(
            "GET",
            f"/session/{quote(name, safe='')}/cost",
            model=SessionCostDetails,
        )

    def gc(self) -> OkResult:
        payload = self._client._request("POST", "/gc")
        return OkResult.model_validate(payload)


class OrchestratorAPI(_BaseAPI):
    """Project, campaign, and artifact orchestration endpoints."""

    def create_project(
        self, request: ProjectCreateRequest
    ) -> OperationResult[ProjectCreateDetails]:
        return self._tool_request(
            "POST",
            "/orchestrator/project",
            model=ProjectCreateDetails,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )

    def register_worker(self, worker: WorkerManifest) -> OperationResult[WorkerRegisterDetails]:
        return self._tool_request(
            "POST",
            "/orchestrator/worker",
            model=WorkerRegisterDetails,
            json_body=worker.model_dump(by_alias=True, exclude_none=True),
        )

    def sync_context(self, request: ContextSyncRequest) -> OperationResult[ContextSyncDetails]:
        return self._tool_request(
            "POST",
            "/orchestrator/context-sync",
            model=ContextSyncDetails,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )

    def run_campaign(self, request: CampaignRunRequest) -> OperationResult[CampaignStatusSnapshot]:
        return self._tool_request(
            "POST",
            "/orchestrator/campaign",
            model=CampaignStatusSnapshot,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )

    @overload
    def status(self, query: None = None) -> OperationResult[OrchestratorStatusSummary]: ...

    @overload
    def status(
        self, query: CampaignStatusQuery
    ) -> OperationResult[CampaignStatusSnapshot | OrchestratorStatusSummary]: ...

    def status(
        self, query: CampaignStatusQuery | None = None
    ) -> OperationResult[CampaignStatusSnapshot | OrchestratorStatusSummary]:
        resolved = query or CampaignStatusQuery()
        params = _normalize_query(resolved.model_dump(by_alias=True, exclude_none=True))
        if resolved.campaign_id is not None:
            return self._tool_request(
                "GET",
                "/orchestrator/status",
                model=CampaignStatusSnapshot,
                params=params,
            )
        return self._tool_request(
            "GET",
            "/orchestrator/status",
            model=OrchestratorStatusSummary,
            params=params,
        )

    def artifacts(
        self, query: ArtifactListQuery | None = None
    ) -> OperationResult[ArtifactListDetails]:
        resolved = query or ArtifactListQuery()
        return self._tool_request(
            "GET",
            "/orchestrator/artifacts",
            model=ArtifactListDetails,
            params=_normalize_query(resolved.model_dump(by_alias=True, exclude_none=True)),
        )

    def read_artifact(self, query: ArtifactReadQuery) -> OperationResult[ArtifactReadDetails]:
        return self._tool_request(
            "GET",
            f"/orchestrator/artifacts/{quote(query.artifact_id, safe='')}/content",
            model=ArtifactReadDetails,
            params=_normalize_query(
                query.model_dump(by_alias=True, exclude_none=True, exclude={"artifact_id"})
            ),
        )

    def events(self, query: CampaignEventsQuery) -> OperationResult[CampaignEventsDetails]:
        return self._tool_request(
            "GET",
            "/orchestrator/events",
            model=CampaignEventsDetails,
            params=_normalize_query(query.model_dump(by_alias=True, exclude_none=True)),
        )

    def approve(self, request: CampaignActionRequest) -> OperationResult[CampaignStatusSnapshot]:
        return self._tool_request(
            "POST",
            "/orchestrator/approve",
            model=CampaignStatusSnapshot,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )

    def start_reassessment(
        self, request: ReassessmentStartRequest
    ) -> OperationResult[ReassessmentRecord]:
        return self._tool_request(
            "POST",
            "/orchestrator/reassessment",
            model=ReassessmentRecord,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )

    @overload
    def reassessment_status(
        self, query: None = None
    ) -> OperationResult[ReassessmentStatusDetails]: ...

    @overload
    def reassessment_status(
        self, query: ReassessmentStatusQuery
    ) -> OperationResult[ReassessmentRecord | ReassessmentStatusDetails]: ...

    def reassessment_status(
        self, query: ReassessmentStatusQuery | None = None
    ) -> OperationResult[ReassessmentRecord | ReassessmentStatusDetails]:
        resolved = query or ReassessmentStatusQuery()
        model: type[ReassessmentRecord] | type[ReassessmentStatusDetails] = (
            ReassessmentRecord
            if resolved.reassessment_id is not None
            else ReassessmentStatusDetails
        )
        return self._tool_request(
            "GET",
            "/orchestrator/reassessment/status",
            model=model,
            params=_normalize_query(resolved.model_dump(by_alias=True, exclude_none=True)),
        )

    def reassessment_report(
        self, query: ReassessmentReportQuery
    ) -> OperationResult[ReassessmentReportDetails]:
        return self._tool_request(
            "GET",
            "/orchestrator/reassessment/report",
            model=ReassessmentReportDetails,
            params=_normalize_query(query.model_dump(by_alias=True, exclude_none=True)),
        )

    def cancel(self, request: CampaignActionRequest) -> OperationResult[CampaignCancelDetails]:
        return self._tool_request(
            "POST",
            "/orchestrator/cancel",
            model=CampaignCancelDetails,
            json_body=request.model_dump(by_alias=True, exclude_none=True),
        )


class SiteAPI(_BaseAPI):
    """Site-level status, log, and shutdown endpoints."""

    def status(
        self, verbose: bool = False, format: str | None = None
    ) -> OperationResult[SiteStatus]:
        query = SiteStatusQuery(verbose=verbose, format=format)
        return self._tool_request(
            "GET",
            "/site/status",
            model=SiteStatus,
            params=_normalize_query(query.model_dump(by_alias=True, exclude_none=True)),
        )

    def logs(self, query: LogsQuery) -> OperationResult[LogsResult]:
        return self._tool_request(
            "GET",
            "/site/logs",
            model=LogsResult,
            params=_normalize_query(query.model_dump(by_alias=True, exclude_none=True)),
        )

    def shutdown(self) -> OkResult:
        payload = self._client._request("POST", "/shutdown")
        return OkResult.model_validate(payload)


class PuppenclawClient:
    """Typed synchronous HTTP client for the local Puppenclaw daemon."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            trust_env=False,
        )
        self.sessions = SessionsAPI(self)
        self.orchestrator = OrchestratorAPI(self)
        self.site = SiteAPI(self)

    def __enter__(self) -> PuppenclawClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def health(self) -> HealthStatus:
        payload = self._request("GET", "/health")
        return HealthStatus.model_validate(payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, json=json_body, params=params)
        except httpx.HTTPError as error:
            raise RequestError(f"Failed to reach Puppenclaw at {self.base_url}: {error}") from error
        try:
            payload = response.json()
        except ValueError as error:
            raise RequestError(f"Invalid JSON response from Puppenclaw: {response.text}") from error
        if not response.is_success:
            message = payload.get("error") if isinstance(payload, dict) else None
            raise RequestError(
                message or f"Puppenclaw request failed with HTTP {response.status_code}"
            )
        if not isinstance(payload, dict):
            raise RequestError(f"Unexpected non-object response from Puppenclaw: {payload!r}")
        return payload


def _normalize_query(data: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, bool):
            normalized[key] = str(value).lower()
        else:
            normalized[key] = value
    return normalized
