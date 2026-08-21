"""Class-time setting annotations: parsing, the Secret marker, item selectors, synthesized defaults."""

import types
import typing

from enum import Enum
from typing import Literal, NamedTuple, TypeAlias

from szo import convert


class ItemSelector(Enum):
    """Sentinel values selecting items positionally instead of by value.

    A setting opts in by declaring selector types in its annotation union:
    ``region_ids: list[str] | AllItems | LastItem = ItemSelector.ALL``.
    Sources spell them with the ``@`` sigil (``--region-ids @last``,
    ``REGION_IDS=@all``) so a selector can never be confused with plain data;
    the application interprets what "first", "last", or "all" mean.
    """

    FIRST = "first"
    LAST = "last"
    ALL = "all"

    def __repr__(self) -> str:
        return f"{type(self).__name__}.{self.name}"


FirstItem: TypeAlias = Literal[ItemSelector.FIRST]
LastItem: TypeAlias = Literal[ItemSelector.LAST]
AllItems: TypeAlias = Literal[ItemSelector.ALL]


def get_selectors_text(selectors: frozenset[ItemSelector]) -> str:
    """Comma-joined source spellings in declaration order: ``@first, @last``."""
    return ", ".join(f"@{member.value}" for member in ItemSelector if member in selectors)


class _SecretMarker:
    """Annotation metadata marking a setting whose value is masked in output."""


_T = typing.TypeVar("_T")

Secret = typing.Annotated[_T, _SecretMarker]
"""Type marker for secret settings: ``password: Secret[str]``.

The attribute stays a plain value; only library-controlled output
(``repr()``, ``--help``, ``print_config()``, the reports) masks it. Secret settings additionally accept the
``NAME_FILE`` env indirection (the value is read from the referenced file).
"""


class SettingAnnotation(NamedTuple):
    setting_type: object  # conversion target, wrappers stripped: Secret[str] -> str, int | None -> int (+ is_optional), list[int] -> list[int]
    description: str
    is_secret: bool
    is_optional: bool  # the annotation was T | None (is nullable)
    selectors: frozenset[ItemSelector] = frozenset()  # selector types declared in the union: list[str] | AllItems


def get_setting_metadata(setting_metadata: tuple) -> tuple[bool, str]:
    """Extract ``is_secret, description`` from ``Annotated[...]`` extras."""
    is_secret = False
    description = ""
    for metadata in setting_metadata:
        if metadata is _SecretMarker:
            is_secret = True
        elif isinstance(metadata, str) and not description:
            description = metadata
    return is_secret, description


def get_setting_fallback(setting_type: object, is_optional: bool) -> object:
    """Synthesized default for a setting with no declared default."""
    if is_optional:
        return None
    if setting_type is str:
        return ""
    if setting_type is bool:
        return False
    if setting_type is int:
        return 0
    if setting_type is float:
        return 0.0
    if typing.get_origin(setting_type) is list:
        return []
    if typing.get_origin(setting_type) is Literal:
        return typing.get_args(setting_type)[0]
    raise TypeError(f"unsupported config setting type {setting_type!r}")


def _get_literal_selectors(type_hint: object) -> frozenset[ItemSelector] | None:
    """The members of an all-selector Literal; None when it is anything else."""
    if typing.get_origin(type_hint) is not Literal:
        return None
    literal_args = typing.get_args(type_hint)
    if all(isinstance(arg, ItemSelector) for arg in literal_args):
        return frozenset(literal_args)
    return None


def get_setting_annotation(type_hint: object) -> SettingAnnotation:
    origin = typing.get_origin(type_hint)

    if origin is typing.Annotated:
        annotated_args = typing.get_args(type_hint)
        is_secret, description = get_setting_metadata(annotated_args[1:])
        inner = get_setting_annotation(annotated_args[0])
        return SettingAnnotation(
            inner.setting_type,
            description or inner.description,
            is_secret or inner.is_secret,
            inner.is_optional,
            inner.selectors,
        )

    if origin is typing.Union or origin is types.UnionType:
        union_args = typing.get_args(type_hint)
        is_optional = False
        selectors: frozenset[ItemSelector] = frozenset()
        base_types = []
        for union_arg in union_args:
            arg_selectors = _get_literal_selectors(union_arg)
            if union_arg is type(None):
                is_optional = True
            elif arg_selectors is not None:
                selectors |= arg_selectors
            else:
                base_types.append(union_arg)
        if len(base_types) != 1:
            raise TypeError(f"unsupported config setting type {type_hint!r}")
        inner = get_setting_annotation(base_types[0])
        if selectors and typing.get_origin(inner.setting_type) is Literal:
            # str choices and selectors in one setting would blur which literal is which.
            raise TypeError(f"unsupported config setting type {type_hint!r} (choices cannot be combined with selectors)")
        return inner._replace(
            is_optional=inner.is_optional or is_optional,
            selectors=inner.selectors | selectors,
        )

    if not convert.supports(type_hint):
        raise TypeError(f"unsupported config setting type {type_hint!r}")

    return SettingAnnotation(type_hint, "", False, False)
