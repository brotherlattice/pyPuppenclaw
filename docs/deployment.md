# Deployment

`pyPuppenclaw` now has a real docs deployment path.

## Hosted deployment

Hosted documentation is intended to be built by Read the Docs using:

- `.readthedocs.yaml`
- `docs/conf.py`
- the package `docs` extra from `pyproject.toml`

Once the repository is connected in Read the Docs, RTD will install the package with `.[docs]` and build the site from `docs/`.

## Local build

```bash
python -m pip install -e .[docs]
sphinx-build -b html docs docs/_build/html
```

## GitHub Actions

GitHub Actions validates the docs build through a dedicated workflow, but it does not publish the docs site. Publishing is delegated to Read the Docs.
