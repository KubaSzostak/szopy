# szo

Reusable building blocks.

## Installation

```console
pip install szo
```

## Development

Install locally in editable mode:

```console
pip install -e .
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
- The tag (`v0.0.3`) and `__version__` (`0.0.3`) must match. Nothing
  enforces this yet — a mismatch will publish the wrong version number.
