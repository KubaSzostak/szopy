"""Command-line side of config loading.

All parsed values stay raw strings or None. 

Supported:
- ``--name value``
- ``--name=value``
- ``--name`` (parsed as ``{"--name": None}``)

Not supported:
- accumulation:         ``--tag a --tag b``
- nargs:                --point 1 2 3, optional values (nargs='?'), "the rest" (nargs='*')
- short flags:          ``-v -x 5 -y5 -z=5`` (it would require a special handling for negative numbers -n -3)
- combined short flags: ``-vf``
- abbreviations:        --verb matches --verbose
- other CLI parsing features

Keep it consistent with the environment variable parsing: no interpolation, no multiline values, no type conversion.
"""

import sys


def _is_arg_flag(token: str) -> bool:
    return token.startswith("--")


def parse_args(argv: list[str] | None = None) -> dict[str, str | None]:
    """Parse command-line tokens into a config mapping: name -> value."""
    argv = sys.argv[1:] if argv is None else argv
    values: dict[str, str | None] = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if not _is_arg_flag(arg):
            raise ValueError(f"unexpected argument {arg!r}")
        flag, has_value, inline_value = arg.partition("=")
        if has_value:
            # `--name=value`
            values[flag] = inline_value
        elif i + 1 < len(argv) and not _is_arg_flag(argv[i + 1]):
            # `--name value`
            i += 1
            values[flag] = argv[i]
        else:
            # Bare `--name` (no value)
            values[flag] = None
        i += 1
    return values
