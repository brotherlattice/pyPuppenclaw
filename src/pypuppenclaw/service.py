from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from .bootstrap import PuppenclawInstaller
from .client import PuppenclawClient
from .config import WrapperSettings, load_settings
from .daemon import PuppenclawManager
from .models import InstallManifest, ManagedDaemonStatus


class PuppenclawService:
    """High-level wrapper that composes installation, daemon lifecycle, and client access."""

    def __init__(
        self,
        settings: WrapperSettings | None = None,
        *,
        client: PuppenclawClient | None = None,
        installer: PuppenclawInstaller | None = None,
        manager: PuppenclawManager | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.installer = installer or PuppenclawInstaller(self.settings)
        self.manager = manager or PuppenclawManager(self.settings, installer=self.installer)
        self.client = client or PuppenclawClient(
            self.settings.daemon.base_url,
            timeout=self.settings.daemon.request_timeout,
        )

    def install(self) -> InstallManifest:
        return self.manager.install()

    def start(self) -> ManagedDaemonStatus:
        return self.manager.start()

    def stop(self) -> ManagedDaemonStatus:
        return self.manager.stop()

    def status(self) -> ManagedDaemonStatus:
        return self.manager.status()

    def close(self) -> None:
        self.client.close()

    @contextmanager
    def running(self, *, ensure_install: bool = True) -> Iterator[PuppenclawClient]:
        if ensure_install:
            self.install()
        self.start()
        try:
            yield self.client
        finally:
            self.stop()
