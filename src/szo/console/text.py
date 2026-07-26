"""Plain-text rendering of values and type hints (reports, help output)."""

import typing

from typing import Literal

SECRET_MASK = "**********"


def get_value_text(value: object) -> str:
    """Source-form text of a value: what a consumer could type to provide it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def get_type_text(target_type: object) -> str:
    # str, int, float, bool, list[str], list[int], list[float]
    if typing.get_origin(target_type) is list:
        return f"list[{typing.get_args(target_type)[0].__name__}]"
    if typing.get_origin(target_type) is Literal:
        # Choices are str-only; the choices themselves come from get_choices_text.
        return "str"
    return target_type.__name__  # type: ignore[attr-defined]


def get_choices_text(literal_type: object) -> str:
    """Comma-joined Literal choices; empty string for non-Literal types."""
    if typing.get_origin(literal_type) is not Literal:
        return ""
    return ", ".join(typing.get_args(literal_type))
