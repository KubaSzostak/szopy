"""Minimal ``.env`` file parsing (no interpolation, no multiline values)."""

import os

from pathlib import Path


def parse_dotenv(path: str | Path) -> dict[str, str]:
    """Parse a ``.env`` file into a name → value dict.

    Rules: blank lines, ``#`` comments, and lines without ``=`` are skipped;
    a leading ``export `` is stripped; values split on the first ``=``. A
    value starting with a quote ends at the matching close quote (quotes
    removed, anything after them dropped); in an unquoted value a ``#``
    preceded by whitespace starts an inline comment. No interpolation, no
    multiline values. A missing file yields an empty dict.
    """
    if not os.path.isfile(path):
        return {}
    entries: dict[str, str] = {}
    with open(path, encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if value[:1] in ("'", '"'):
                closing = value.find(value[0], 1)
                if closing != -1:
                    value = value[1:closing]
            else:
                for index, char in enumerate(value):
                    if char == "#" and (index == 0 or value[index - 1] in " \t"):
                        value = value[:index].rstrip()
                        break
            entries[key] = value
    return entries
