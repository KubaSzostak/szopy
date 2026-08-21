import os
import sys
import typing

from pathlib import Path
from collections.abc import Mapping
from typing import Any, Callable, ClassVar, Collection, Literal, TextIO

from szo.config.args import parse_args
from szo.config.setting import Setting, SettingBinding, SettingBuilder
from szo.config.annotations import ItemSelector, SettingAnnotation, get_selectors_text, get_setting_annotation, get_setting_fallback
from szo.config.dotenv import parse_dotenv
from szo.console import blocks
from szo.text import get_choices_text, get_type_text

# Keep in sync with the BaseConfig.__init__ parameters: a setting with one of
# these names could never receive its ``**defaults`` value (the named parameter
# would swallow it silently), so such setting names are rejected outright.
_RESERVED_SETTING_NAMES = frozenset({"env_prefix", "arg_prefix", "prog", "args", "environ", "dotenv"})


def _get_default_error(
    value: object,
    setting_type: object,
    is_optional: bool,
    selectors: frozenset[ItemSelector] = frozenset()
) -> str | None:
    """None when the typed value fits the setting type; the error text otherwise."""
    if isinstance(value, ItemSelector):
        if value in selectors:
            return None
        if selectors:
            return f"{value!r} is not one of the declared selectors: {get_selectors_text(selectors)}"
        return f"{value!r} is not a valid {get_type_text(setting_type)} (no selectors declared)"
    if value is None:
        return None if is_optional else f"None is not a valid {get_type_text(setting_type)}"
    if typing.get_origin(setting_type) is Literal:
        if value in typing.get_args(setting_type):
            return None
        return f"{value!r} is not one of: {get_choices_text(setting_type)}"
    if typing.get_origin(setting_type) is list:
        if not isinstance(value, list):
            return f"{value!r} is not a valid {get_type_text(setting_type)}"
        item_type = typing.get_args(setting_type)[0]
        for index, item in enumerate(value, start=1):
            if _get_default_error(item, item_type, is_optional=False):
                return f"{item!r} is not a valid {item_type.__name__} (item {index} of list)"
        return None
    if setting_type is bool:
        is_valid = isinstance(value, bool)
    elif setting_type is int:
        # bool is an int subclass; a True default for an int setting is a mistake.
        is_valid = isinstance(value, int) and not isinstance(value, bool)
    elif setting_type is float:
        is_valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        is_valid = isinstance(value, str)
    return None if is_valid else f"{value!r} is not a valid {get_type_text(setting_type)}"


class BaseConfig:
    """Base class for config models. Subclass, annotate settings, construct."""

    def __init__(
        self,
        env_prefix: str = "",
        arg_prefix: str = "",
        prog: str | None = None,
        *,
        args: Mapping[str, str | None] | None = None,
        environ: Mapping[str, str] | None = None,
        dotenv: Mapping[str, str] | Path | str | None = None,
        _setting_names: set[str] | None = None,
        **defaults: Any
    ):
        """Load every declared setting from args > environ > dotenv > default.

        - ``env_prefix``: prefix for env variable names, no trailing underscore: ``"DB"`` -> ``DB_HOST``.
        - ``arg_prefix``: prefix for argument names, including the dashes: ``"--db"`` -> ``--db-host``.
        - ``prog``: program name shown in ``--help``; defaults to the ``sys.argv[0]`` basename.
        - ``args``: pre-parsed command-line values; ``None`` parses ``sys.argv``.
        - ``environ``: environment variables; ``None`` uses ``os.environ``.
        - ``dotenv``: already-parsed mapping or a ``.env`` file path (a missing
          file is ignored); ``None`` reads no dotenv file.
        - ``**defaults``: replacement defaults for this class's own settings, as
          typed values: ``PostgresConfig(host="db.internal")``. A setting
          defaulted here is no longer required; args/environ/dotenv still
          override it. Unknown or nested-section names and invalid values
          raise ``TypeError``.
        """
        if env_prefix and not env_prefix.isidentifier():
            raise ValueError(f"env_prefix {env_prefix!r} is not a valid identifier")
        if arg_prefix and not (arg_prefix.startswith("--") and arg_prefix.lstrip("-").replace("-", "_").isidentifier()):
            raise ValueError(f"arg_prefix {arg_prefix!r} must start with '--' followed by a valid name")
        self._env_prefix = env_prefix
        self._arg_prefix = arg_prefix
        self._prog = prog if prog is not None else os.path.basename(sys.argv[0])
        self._defaults = defaults
        self._settings: dict[str, Setting] = {}
        self._nested_configs: dict[str, BaseConfig] = {}
        self._errors: list[blocks.Block] = []

        args = self._load_args(args)
        environ = dict(os.environ) if environ is None else environ
        dotenv = self._load_dotenv(dotenv)
        # `or set()` would discard a shared-but-still-empty set: empty sets are falsy.
        setting_names = set() if _setting_names is None else _setting_names

        handled_names: set[str] = set()
        type_hints = typing.get_type_hints(type(self), include_extras=True)
        for name, type_hint in type_hints.items():
            if name.startswith("_"):
                continue
            if type_hint is ClassVar or typing.get_origin(type_hint) is ClassVar:
                continue
            if name in _RESERVED_SETTING_NAMES:
                raise TypeError(
                    f"{type(self).__name__}.{name}: setting name collides with a BaseConfig constructor parameter"
                )
            handled_names.add(name)
            if isinstance(type_hint, type) and issubclass(type_hint, BaseConfig):
                self._init_nested_config(name, type_hint, args, environ, dotenv, setting_names)
            else:
                self._init_setting(name, type_hint, args, environ, dotenv, setting_names)

        unknown_defaults = [key for key in defaults if key not in handled_names]
        if unknown_defaults:
            names = ", ".join(repr(key) for key in unknown_defaults)
            raise TypeError(f"{type(self).__name__}() got unexpected setting defaults: {names}")

    def __repr__(self) -> str:
        parts = []
        for setting in self._settings.values():
            parts.append(f"{setting.name}={setting.value_repr}")
            
        for nested_name, nested_config in self._nested_configs.items():
            parts.append(f"{nested_name}={nested_config!r}")
        return f"{type(self).__name__}({', '.join(parts)})"

    def _init_nested_config(
        self, 
        name: str, 
        nested_config_cls: type["BaseConfig"],
        args: Mapping[str, str | None],
        environ: Mapping[str, str],
        dotenv: Mapping[str, str],
        setting_names: set[str]
    ) -> None:
        if name in self._defaults:
            raise TypeError(
                f"{type(self).__name__}.{name} is a nested config; "
                f"pass its defaults to the {nested_config_cls.__name__} constructor instead"
            )
        default = getattr(type(self), name, None)
        if isinstance(default, nested_config_cls):
            # Allow the consumer to provide a pre-constructed nested config instance.
            # Record its names so later settings are checked against them too.
            self._nested_configs[name] = default
            for setting in default.get_settings():
                setting_names.add(setting.binding.arg_name)
                setting_names.add(setting.binding.env_name)
            return
        if default is not None:
            raise TypeError(
                f"{type(self).__name__}.{name}: nested config default must be "
                f"a {nested_config_cls.__name__} instance or None"
            )
        nested_config = nested_config_cls(
            env_prefix=self._get_env_name(name), 
            arg_prefix=self._get_arg_name(name), 
            args=args, 
            environ=environ, 
            dotenv=dotenv,
            _setting_names=setting_names)
        setattr(self, name, nested_config)
        self._nested_configs[name] = nested_config

    def _init_setting(
        self,
        name: str,
        type_hint: Any,
        args: Mapping[str, str | None],
        environ: Mapping[str, str],
        dotenv: Mapping[str, str],
        setting_names: set[str]
    ) -> None:
        annotation = self._get_setting_annotation(name, type_hint)
        binding = self._get_setting_binding(name, annotation)

        builder = SettingBuilder(name, binding, annotation)
        builder.load(args, environ, dotenv)
        builder.validate_names(setting_names)
        setting = builder.build()

        setattr(self, name, setting.value)
        self._settings[name] = setting

    def _append_error(self, message: str, error: Exception) -> None:
        error_block = blocks.Block(type(self).__name__, [message])
        error_block.append_error(error)
        self._errors.append(error_block)

    def _load_args(self, args: Mapping[str, str | None] | None) -> Mapping[str, str | None]:
        if args is not None:
            self._help_requested = "--help" in args
            return args
        # Help must win even when argv parsing fails, so detect it on raw argv.
        self._help_requested = "--help" in sys.argv[1:]
        try:
            return parse_args()
        except ValueError as exc:
            self._append_error("invalid command line arguments", exc)
            return {}

    def _load_dotenv(self, dotenv: Mapping[str, str] | Path | str | None) -> Mapping[str, str]:
        if isinstance(dotenv, Mapping):
            return dotenv
        if dotenv is None:
            return {}
        try:
            return parse_dotenv(dotenv)
        except (OSError, UnicodeDecodeError) as exc:
            self._append_error("cannot read dotenv file", exc)
            return {}

    def _get_env_name(self, name: str) -> str:
        # AppConfig -> DbConfig -> host: str -> DB_HOST
        name = name.upper().replace("-", "_")
        return f"{self._env_prefix}_{name}" if self._env_prefix else name

    def _get_arg_name(self, name: str) -> str:
        # AppConfig -> DbConfig -> host: str -> --db-host
        name = name.replace("_", "-")
        return f"{self._arg_prefix}-{name}" if self._arg_prefix else f"--{name}"

    def _get_setting_annotation(self, name: str, type_hint: Any) -> SettingAnnotation:
        try:
            return get_setting_annotation(type_hint)
        except TypeError as exc:
            raise TypeError(f"{type(self).__name__}.{name}: {exc}") from None

    def _get_setting_binding(self, name: str, annotation: SettingAnnotation) -> SettingBinding:
        if name in self._defaults:
            # A **defaults value replaces the class default, so the setting is
            # no longer required and --help shows the replacement value.
            fallback = self._defaults[name]
            error = _get_default_error(fallback, annotation.setting_type, annotation.is_optional, annotation.selectors)
            if error:
                raise TypeError(f"{type(self).__name__}.{name}: default {error}")
            has_default_value = True
        else:
            has_default_value = hasattr(type(self), name)
            fallback = getattr(type(self), name) if has_default_value else get_setting_fallback(annotation.setting_type, annotation.is_optional)
        return SettingBinding(
            arg_name=self._get_arg_name(name),
            env_name=self._get_env_name(name),
            is_required=not has_default_value,
            fallback_value=fallback,
        )

    def get_settings(self) -> list[Setting]:
        """All settings as loaded, flattened across nested sections."""
        settings = list(self._settings.values())
        for nested_config in self._nested_configs.values():
            settings.extend(nested_config.get_settings())
        return settings

    def is_valid(self) -> bool:
        if self._errors:
            return False
        for setting in self._settings.values():
            if setting.error is not None:
                return False
        for nested_config in self._nested_configs.values():
            if not nested_config.is_valid():
                return False
        return True

    def is_help_requested(self) -> bool:
        """True when ``--help`` was among the command-line args."""
        return self._help_requested

    def validate_or_exit(self) -> None:
        """Print help (exit 0) or the error report (exit 2); otherwise returns silently."""
        if self.is_help_requested():
            self.print_help()
            sys.exit(0)
        if not self.is_valid():
            self.print_errors()
            sys.exit(2)

    def print_errors(self) -> None:
        """Print the aggregated setting-error report (without exiting)."""
        if self.is_valid():
            print("No config errors found.", file=sys.stderr)
            return
        print("Errors:", file=sys.stderr)
        self._print_error_blocks()

    def _print_error_blocks(self) -> None:
        for error_block in self._errors:
            blocks.print_block(error_block, sys.stderr)
        err_settings = [err for err in self._settings.values() if err.error]
        self._print_setting_blocks(err_settings, lambda setting: setting.error, sys.stderr)
        for nested_config in self._nested_configs.values():
            nested_config._print_error_blocks()
        
    def print_config(self) -> None:
        """Print every setting's loaded value and its source, one card per setting."""
        print("Config:")
        self._print_config()

    def print_help(self) -> None:
        print(f"usage: {self._prog} [--help] [options]", end="\n\n")
        if type(self).__doc__:
            print(type(self).__doc__, end="\n\n")
        print(f"  {'--help':<25}  show this help message and exit")
        self._print_help_options()

    def _print_help_options(self) -> None:
        self._print_setting_blocks(self._settings.values(), lambda setting: setting.annotation.description)
        for nested_config in self._nested_configs.values():
            nested_config._print_help_options()

    def _print_block_header(self, file: TextIO | None = None) -> None:
        if not self._arg_prefix:
            return
        doc = (type(self).__doc__ or "").strip()
        description = doc.splitlines()[0] if doc else ""
        blocks.print_header(self._arg_prefix.lstrip("-"), file)
        if description:
            print(f"  {description}", file=file)
            print(file=file)

    def _print_setting_blocks(
        self,
        settings: Collection[Setting],
        first_line_selector: Callable[[Setting], str | None],
        file: TextIO | None = None
    ) -> None:
        if not settings:
            return
        self._print_block_header(file)
        for setting in settings:
            self._print_setting_block(setting, first_line_selector, file)

    def _print_setting_block(
        self,
        setting: Setting,
        first_line_selector: Callable[[Setting], str | None],
        file: TextIO | None = None
    ) -> None:
        block = blocks.Block(setting.binding.arg_name)
        first_line = first_line_selector(setting)
        block.append_line(first_line)
        block.append_line(setting.spec_text)
        block.append_line(setting.env_text)
        blocks.print_block(block, file)

    def _print_config_block(self, setting: Setting) -> None:
        if setting.error:
            first_line_selector = lambda setting: f"ERROR: {setting.error}"
            self._print_setting_block(setting, first_line_selector)
            return
        block = blocks.Block(setting.binding.arg_name)
        block.append_line(setting.value_text)
        block.append_line(setting.source_text)
        blocks.print_block(block)
    
    def _print_config(self) -> None:
        self._print_block_header()
        for error_block in self._errors:
            blocks.print_block(error_block)
        for setting in self._settings.values():
            self._print_config_block(setting)
        for nested_config in self._nested_configs.values():
            nested_config._print_config()
