# pyPuppenclaw

`pyPuppenclaw` is a Python wrapper around the Puppenclaw daemon. It does not reimplement Puppenclaw in Python. It bootstraps a local Puppenclaw checkout, writes daemon config, manages the background process, and exposes a typed Python client for sessions, orchestration, site status, and logs.

## What it does

- builds Puppenclaw from a sibling checkout by default
- writes an isolated Puppenclaw daemon config and state directory
- starts and stops the daemon as a managed background process
- exposes a synchronous `httpx` client with typed request and response models
- provides a small CLI for `doctor`, `install`, `config-init`, `start`, `stop`, and `status`

## Current bootstrap mode

The default v1 bootstrap mode is a local sibling checkout at `../puppenclaw`. You can override that with:

- `PUPPENCLAW_SOURCE_DIR`
- the generated `config.toml`

Registry-based installation is planned, but the current implementation intentionally starts from the working local repo.

## Quick start

```bash
python -m pip install -e .[dev]
pypuppenclaw config-init
pypuppenclaw doctor
pypuppenclaw install
pypuppenclaw start
```

Python usage:

```python
from pypuppenclaw import PuppenclawService

service = PuppenclawService()
service.install()

with service.running() as client:
    site = client.site.status(verbose=True)
    print(site.details.site_id)
```

## Requirements

- Python 3.10+
- Node 22.13+
- `npm`
- a working Puppenclaw checkout
- valid ACP adapter/auth setup if you want real Codex or Claude execution

## Development

```bash
python -m pip install -e .[dev]
pytest
ruff check .
```

## Documentation

`pyPuppenclaw` now has the same Read the Docs deployment path shape as `pyflowreg`: a repository-level `.readthedocs.yaml`, a Sphinx configuration in `docs/conf.py`, and a package `docs` extra in `pyproject.toml`.

Local docs build:

```bash
python -m pip install -e .[docs]
sphinx-build -b html docs docs/_build/html
```

GitHub Actions validates the docs build, while hosted publication is intended to come from Read the Docs after the repository is connected there.
