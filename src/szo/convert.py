"""String-to-value conversion: str, bool, int, float, str-only Literal, list of scalars.

Callers pass non-empty strings; empty-value handling is the caller's job.
Call qualified — ``convert.to_int(...)``, ``convert.supports(...)`` — the
module name is part of each function's name.
"""

import typing

from typing import Literal

from szo.console.text import get_choices_text

_TRUE_STRINGS = {"1", "true", "yes", "on"}
_FALSE_STRINGS = {"0", "false", "no", "off"}

_SCALAR_TYPES = (str, int, float, bool)
_LIST_ITEM_TYPES = (str, int, float)


def supports(target_type: object) -> bool:
    """True when ``to_type`` can handle the type."""
    if target_type in _SCALAR_TYPES:
        return True
    if typing.get_origin(target_type) is Literal:
        # str-only choices: values to convert arrive as strings.
        return all(isinstance(choice, str) for choice in typing.get_args(target_type))
    if typing.get_origin(target_type) is not list:
        return False
    args = typing.get_args(target_type)
    return len(args) == 1 and args[0] in _LIST_ITEM_TYPES


def to_bool(value: str) -> bool:
    value_lower = value.strip().lower()
    if value_lower in _TRUE_STRINGS:
        return True
    if value_lower in _FALSE_STRINGS:
        return False
    raise ValueError(f"{value!r} is not a valid bool (use true/false)")


def to_int(value: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        raise ValueError(f"{value!r} is not a valid int") from None


def to_float(value: str) -> float:
    try:
        return float(value.strip())
    except ValueError:
        raise ValueError(f"{value!r} is not a valid float") from None


def to_type(value: str, target_type: object) -> object:
    if target_type is str:
        return value
    if target_type is bool:
        return to_bool(value)
    if target_type is int:
        return to_int(value)
    if target_type is float:
        return to_float(value)
    if typing.get_origin(target_type) is Literal:
        if value in typing.get_args(target_type):
            return value
        raise ValueError(f"{value!r} is not one of: {get_choices_text(target_type)}")

    if typing.get_origin(target_type) is not list:
        raise TypeError(f"unsupported conversion target {target_type!r}")

    item_type = typing.get_args(target_type)[0]
    if item_type not in _LIST_ITEM_TYPES:
        raise TypeError(f"unsupported list item type {item_type!r}")

    items = []
    for index, item in enumerate(value.split(","), start=1):
        item = item.strip()
        try:
            items.append(to_type(item, item_type))
        except ValueError:
            raise ValueError(f"{item!r} is not a valid {item_type.__name__} (item {index} of list)") from None
    return items
