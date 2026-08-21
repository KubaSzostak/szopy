"""Generic text rendering of values and type hints (reports, help output).

Call qualified — ``text.format_duration(...)``, ``text.get_type_text(...)``.
"""

import typing

from datetime import timedelta
from typing import Literal

SECRET_MASK = "**********"


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


def format_duration(duration: float | timedelta) -> str:
    """Duration text scaled to magnitude: 78 s, 12m 34s, 1h 12m 34s, 1d 3h 12m."""
    seconds = duration.total_seconds() if isinstance(duration, timedelta) else float(duration)
    if seconds < 0:
        raise ValueError(f"duration must not be negative, got {duration!r}")
    seconds = round(seconds)
    if seconds < 100:
        return f"{seconds} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m {seconds}s"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h {minutes}m"


def format_value(value: object) -> str:
    """Display text of a value: durations scaled, bools lowercase, lists comma-joined."""
    if isinstance(value, timedelta):
        return format_duration(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(format_value(item) for item in value)
    return str(value)
