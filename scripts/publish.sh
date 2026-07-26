#!/usr/bin/env bash
# Publish a new version: test, bump __version__, commit, tag, push.
# The PyPI upload itself is done by .github/workflows/publish.yml,
# triggered by the pushed tag.
#
# Usage:
#   ./scripts/publish.sh          # patch bump: 0.0.2 -> 0.0.3
#   ./scripts/publish.sh 0.1.0    # explicit version
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

VERSION_FILE="src/szo/__init__.py"

PYTHON="python3"
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
fi

branch="$(git symbolic-ref --short HEAD)"
if [ "$branch" != "main" ]; then
    echo "ERROR: on branch '$branch' — publish from 'main'." >&2
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: working tree is not clean — commit or stash first." >&2
    exit 1
fi

current="$(PYTHONPATH=src "$PYTHON" -c 'import szo; print(szo.__version__)')"

if [ $# -ge 1 ]; then
    new="$1"
    if ! [[ "$new" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "ERROR: version '$new' is not in X.Y.Z form." >&2
        exit 1
    fi
else
    IFS=. read -r major minor patch <<<"$current"
    new="$major.$minor.$((patch + 1))"
fi

echo "Publishing $current -> $new"

"$PYTHON" -m pytest -q

sed -i "s/^__version__ = \"$current\"/__version__ = \"$new\"/" "$VERSION_FILE"
bumped="$(PYTHONPATH=src "$PYTHON" -c 'import szo; print(szo.__version__)')"
if [ "$bumped" != "$new" ]; then
    echo "ERROR: failed to bump version in $VERSION_FILE (still $bumped)." >&2
    git checkout -- "$VERSION_FILE"
    exit 1
fi

git commit -m "Release $new" -- "$VERSION_FILE"
git tag "v$new"
git push origin main "v$new"

echo
echo "Pushed tag v$new — the workflow publishes it to PyPI:"
echo "https://github.com/KubaSzostak/szopy/actions"
