from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._io import atomic_write_text
from .models import AgentKind

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

PUPPENCODE_CONFIG_NAME = ".pclaw.toml"
DEFAULT_INCLUDE_FILE_CANDIDATES = (
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "pyproject.toml",
    "package.json",
    "pnpm-workspace.yaml",
)


class PuppencodeProjectConfig(BaseModel):
    """Project-local defaults used by the puppencode terminal app."""

    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    project_name: str | None = None
    worker_id: str = "local"
    mode: Literal["fusion", "agent"] = "fusion"
    preferred_agent: AgentKind = "codex"
    model: str | None = None
    effort: str | None = None
    validation_command: str | None = None
    include_files: list[str] = Field(default_factory=list)
    memory_text: str | None = None

    @field_validator("include_files")
    @classmethod
    def _deduplicate_include_files(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    @property
    def resolved_project_id(self) -> str:
        return self.project_id or _slug(self.project_name or Path.cwd().name)

    @property
    def resolved_project_name(self) -> str:
        return self.project_name or self.resolved_project_id


def default_project_config_path(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()).resolve() / PUPPENCODE_CONFIG_NAME


def load_project_config(
    path: Path | None = None,
    *,
    cwd: Path | None = None,
) -> PuppencodeProjectConfig:
    config_path = (path or default_project_config_path(cwd)).expanduser().resolve()
    if not config_path.exists():
        return infer_project_config(cwd or config_path.parent)
    with config_path.open("rb") as handle:
        return PuppencodeProjectConfig.model_validate(tomllib.load(handle))


def save_project_config(config: PuppencodeProjectConfig, path: Path | None = None) -> Path:
    target = (path or default_project_config_path()).expanduser().resolve()
    atomic_write_text(target, tomli_w.dumps(_dump_config(config)))
    return target


def init_project_config(cwd: Path, *, force: bool = False) -> Path:
    path = default_project_config_path(cwd)
    if path.exists() and not force:
        return path
    save_project_config(infer_project_config(cwd), path)
    return path


def infer_project_config(cwd: Path) -> PuppencodeProjectConfig:
    root = cwd.expanduser().resolve()
    validation_command = _detect_validation_command(root)
    return PuppencodeProjectConfig(
        project_id=_slug(root.name),
        project_name=root.name,
        validation_command=validation_command,
        include_files=existing_default_include_files(root),
    )


def existing_default_include_files(cwd: Path) -> list[str]:
    root = cwd.expanduser().resolve()
    return [
        candidate for candidate in DEFAULT_INCLUDE_FILE_CANDIDATES if (root / candidate).exists()
    ]


def _detect_validation_command(cwd: Path) -> str | None:
    if (cwd / "package.json").exists():
        if (cwd / "pnpm-lock.yaml").exists():
            return "pnpm test"
        if (cwd / "yarn.lock").exists():
            return "yarn test"
        return "npm test"
    if (cwd / "pyproject.toml").exists() or (cwd / "pytest.ini").exists():
        return "pytest"
    if (cwd / "Makefile").exists():
        return "make test"
    return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return slug or "project"


def _dump_config(config: PuppencodeProjectConfig) -> dict[str, Any]:
    return config.model_dump(exclude_none=True)
