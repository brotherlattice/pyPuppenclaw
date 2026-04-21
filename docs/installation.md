# Installation

Install the package and the docs toolchain separately depending on what you want to do locally.

## Package development

```bash
python -m pip install -e .[dev]
pypuppenclaw config-init
pypuppenclaw doctor
```

Set `PUPPENCLAW_SOURCE_DIR` if the local Puppenclaw checkout is not at `../puppenclaw`.

## Documentation development

```bash
python -m pip install -e .[docs]
sphinx-build -b html docs docs/_build/html
```

That local Sphinx command matches the hosted Read the Docs build path.
