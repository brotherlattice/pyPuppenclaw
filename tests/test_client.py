from __future__ import annotations

import json

import httpx
import pytest

from pypuppenclaw.client import PuppenclawClient
from pypuppenclaw.errors import RequestError
from pypuppenclaw.models import (
    ArtifactListQuery,
    CampaignStatusQuery,
    LogsQuery,
    SendSessionRequest,
    SiteStatus,
)


def _transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "sessions": 2})
        if request.url.path == "/sessions":
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Tracked sessions"}],
                    "details": {"sessions": []},
                },
            )
        if request.url.path == "/session/demo":
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Status"}],
                    "details": {
                        "session": {
                            "name": "demo",
                            "agent": "codex",
                            "directory": "/tmp/demo",
                            "state": "idle",
                            "createdAt": "2026-01-01T00:00:00Z",
                            "lastActivity": "2026-01-01T00:00:00Z",
                            "permissionMode": "approve-reads",
                            "warnings": [],
                            "transcript": [],
                        },
                        "runtime": {"exists": True},
                    },
                },
            )
        if request.url.path == "/session/demo/send":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["message"] == "hello"
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Sent"}],
                    "details": {
                        "session": {
                            "name": "demo",
                            "agent": "codex",
                            "directory": "/tmp/demo",
                            "state": "running",
                            "createdAt": "2026-01-01T00:00:00Z",
                            "lastActivity": "2026-01-01T00:00:00Z",
                            "permissionMode": "approve-reads",
                            "warnings": [],
                            "transcript": [],
                        },
                        "output": "Handled: hello",
                    },
                },
            )
        if request.url.path == "/orchestrator/status":
            if request.url.params.get("campaignId") == "camp-1":
                return httpx.Response(
                    200,
                    json={
                        "content": [{"type": "text", "text": "Campaign"}],
                        "details": {
                            "campaign": {
                                "id": "camp-1",
                                "projectId": "proj",
                                "workerId": "local",
                                "name": "Demo",
                                "template": "custom",
                                "experimentCommands": [],
                                "experimentParallelism": 1,
                                "iterations": 1,
                                "steps": [],
                                "currentStepIndex": 0,
                                "lastProgressAt": "2026-01-01T00:00:00Z",
                                "createdAt": "2026-01-01T00:00:00Z",
                                "updatedAt": "2026-01-01T00:00:00Z",
                                "state": "completed",
                            },
                            "project": None,
                            "worker": None,
                            "runs": [],
                            "artifacts": [],
                            "progress": {
                                "totalSteps": 0,
                                "completedSteps": 0,
                                "failedSteps": 0,
                                "currentStepIndex": 0,
                                "experimentParallelism": 1,
                                "lastProgressAt": "2026-01-01T00:00:00Z",
                            },
                        },
                    },
                )
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Summary"}],
                    "details": {"projects": [], "workers": [], "campaigns": []},
                },
            )
        if request.url.path == "/orchestrator/artifacts":
            assert request.url.params.get("projectId") == "proj"
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Artifacts"}],
                    "details": {"artifacts": []},
                },
            )
        if request.url.path == "/site/status":
            assert request.url.params.get("verbose") == "true"
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Site"}],
                    "details": {
                        "siteId": "local",
                        "label": "Local Worker",
                        "backend": "local",
                        "pluginHealth": "ok",
                        "openclawRuntime": {"available": True},
                        "defaultAgent": "codex",
                        "availableAgents": [],
                        "orchestration": {"enabled": True},
                        "sessions": {"maxSessions": 5, "total": 0, "active": 0},
                        "campaigns": {"maxCampaigns": 32, "total": 0, "active": 0},
                        "workers": [],
                        "exposures": {"total": 0, "currentExposure": None},
                    },
                },
            )
        if request.url.path == "/site/logs":
            assert request.url.params.get("follow") == "false"
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Logs"}],
                    "details": {
                        "scope": "session",
                        "targetId": "demo",
                        "limitChars": 500,
                        "followRequested": False,
                        "followSupported": False,
                        "text": "hi",
                        "entries": [],
                    },
                },
            )
        return httpx.Response(404, json={"error": f"Unhandled path {request.url.path}"})

    return httpx.MockTransport(handler)


def test_client_parses_health_and_tool_results() -> None:
    raw_client = httpx.Client(base_url="http://puppenclaw.test", transport=_transport())

    with PuppenclawClient("http://puppenclaw.test", client=raw_client) as client:
        assert client.health().ok is True
        assert client.sessions.list().details.sessions == []
        assert client.sessions.get("demo").details.session.name == "demo"
        assert (
            client.sessions.send(SendSessionRequest(name="demo", message="hello")).details.output
            == "Handled: hello"
        )

        summary = client.orchestrator.status()
        assert summary.details.projects == []

        campaign = client.orchestrator.status(CampaignStatusQuery(campaignId="camp-1"))
        assert campaign.details.campaign.id == "camp-1"

        artifacts = client.orchestrator.artifacts(ArtifactListQuery(projectId="proj"))
        assert artifacts.details.artifacts == []

        site = client.site.status(verbose=True)
        assert isinstance(site.details, SiteStatus)
        assert site.details.site_id == "local"

        logs = client.site.logs(LogsQuery(sessionName="demo", limitChars=500))
        assert logs.details.target_id == "demo"

    assert raw_client.is_closed is True


def test_client_raises_request_error_on_http_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = PuppenclawClient(
        "http://puppenclaw.test",
        client=httpx.Client(
            base_url="http://puppenclaw.test", transport=httpx.MockTransport(handler)
        ),
    )

    with pytest.raises(RequestError, match="boom"):
        client.sessions.list()
