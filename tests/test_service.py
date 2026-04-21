from __future__ import annotations

from pypuppenclaw.service import PuppenclawService


class StubManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def install(self):
        self.calls.append("install")
        return {"ok": True}

    def start(self):
        self.calls.append("start")
        return {"ok": True}

    def stop(self):
        self.calls.append("stop")
        return {"ok": True}

    def status(self):
        self.calls.append("status")
        return {"running": False}


class StubClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_service_running_context_starts_and_stops(temp_settings) -> None:
    manager = StubManager()
    client = StubClient()
    service = PuppenclawService(
        settings=temp_settings,
        manager=manager,
        client=client,
    )

    with service.running() as yielded:
        assert yielded is client

    assert manager.calls == ["install", "start", "stop"]


def test_service_close_closes_client(temp_settings) -> None:
    manager = StubManager()
    client = StubClient()
    service = PuppenclawService(
        settings=temp_settings,
        manager=manager,
        client=client,
    )

    service.close()

    assert client.closed is True
