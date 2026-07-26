"""Class-time setting annotations: parsing, the Secret marker, synthesized defaults."""

import types
import typing

from typing import Literal, NamedTuple

from szo import convert


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
        )

    if origin is typing.Union or origin is types.UnionType:
        union_args = typing.get_args(type_hint)
        inner_types = [arg for arg in union_args if arg is not type(None)]
        if len(union_args) != 2 or len(inner_types) != 1:
            raise TypeError(f"unsupported config setting type {type_hint!r}")
        return get_setting_annotation(inner_types[0])._replace(is_optional=True)

    if not convert.supports(type_hint):
        raise TypeError(f"unsupported config setting type {type_hint!r}")

    return SettingAnnotation(type_hint, "", False, False)
