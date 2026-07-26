# szo

Building blocks for Python applications (3.10+):

- **`szo.config`** — typed application configuration loaded from command-line
  arguments, environment variables, and `.env` files. No argparse, no pydantic.
- **`szo.console`** — terminal output helpers (card-shaped blocks used by the
  config reports).
- **`szo.convert`** — string-to-value conversion shared by the above.

## Installation

```console
pip install szo
```

## szo.config

Declare settings as annotated class attributes, construct, and use plain
attribute access:

```python
from typing import Annotated
from szo import BaseConfig, Secret


class DbConfig(BaseConfig):
    host: Annotated[str, "PostgreSQL server host"] = "localhost"
    port: Annotated[int, "PostgreSQL server port"] = 5432
    password: Annotated[Secret[str], "database password"]


class AppConfig(BaseConfig):
    """My application."""

    verbose: bool = False
    db: DbConfig


config = AppConfig(dotenv=".env")
config.validate_or_exit()  # --help exits 0; config errors exit 2

print(config.db.host, config.db.port)
```

```console
$ python app.py --db-host db.example.com
$ DB_PASSWORD=s3cret python app.py
$ python app.py --help
```

### Sources and precedence

Every setting resolves from the first source that provides it:

1. command-line arguments — `--db-host db.example.com` or `--db-host=db.example.com`
2. environment variables — `DB_HOST=db.example.com`
3. a dotenv file — only when requested: `AppConfig(dotenv=".env")`
   (by default no dotenv file is read)
4. the declared class default


## Development

Install locally in editable mode:

```console
pip install -e .
```

Run the tests:

```console
python -m pytest -q tests/
```

## Build

```console
python -m pip install --upgrade build twine
python -m build
twine check dist/*
```

Artifacts land in `dist/`.

## Publishing a new release

Releases are published to PyPI automatically by
[`.github/workflows/publish.yml`](.github/workflows/publish.yml),
triggered by pushing a version tag. Authentication uses PyPI Trusted
Publishing (OIDC) — no tokens or passwords are stored anywhere.

1. Bump the version in `src/szo/__init__.py`:

```python
__version__ = "0.0.3"
```

2. Commit and push to `main`:

```console
git commit -am "Release 0.0.3"
git push
```

3. Tag and push the tag — this is what triggers the release:

```console
git tag v0.0.3
git push --tags
```

4. Watch the run at
   [Actions](https://github.com/KubaSzostak/szopy/actions).

5. Verify:

```console
pip install --upgrade szo
python -c "import szo; print(szo.__version__)"
```

or

```console
cd /tmp
uv venv verify
source verify/bin/activate
uv pip install szo
python -c "import szo; print(szo.__version__)"
deactivate
rm -rf /tmp/verify
```

### Notes

- Pushing to `main` does not publish. Only tags do.
- The tag (`v0.0.3`) and `__version__` (`0.0.3`) must match — the workflow
  verifies this and runs the tests (Python 3.10/3.12/3.14) before building;
  a mismatch or a test failure aborts the release.
