from __future__ import annotations


class PuppenclawError(RuntimeError):
    """Base exception for wrapper failures."""


class ConfigurationError(PuppenclawError):
    """Raised for invalid wrapper configuration."""


class DependencyError(PuppenclawError):
    """Raised when required local tools are missing."""


class InstallationError(PuppenclawError):
    """Raised when Puppenclaw bootstrap/build fails."""


class DaemonProcessError(PuppenclawError):
    """Raised for local daemon process failures."""


class DaemonTimeoutError(PuppenclawError):
    """Raised when the daemon does not reach the expected state in time."""


class RequestError(PuppenclawError):
    """Raised for HTTP-level daemon request failures."""
