from __future__ import annotations

import os

import pytest

from pypuppenclaw import PuppenclawService

pytestmark = pytest.mark.live


@pytest.mark.skipif(os.environ.get("PYPUPPENCLAW_LIVE") != "1", reason="live smoke disabled")
def test_real_checkout_smoke() -> None:
    service = PuppenclawService()
    service.install()
    try:
        service.start()
        assert service.client.health().ok is True
    finally:
        service.stop()
