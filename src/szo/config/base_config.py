import os
import sys
import typing

from pathlib import Path
from collections.abc import Mapping
from typing import Any, Callable, ClassVar, Collection, TextIO

from szo.config.args import parse_args
from szo.config.setting import Setting, SettingBinding, SettingBuilder
from szo.config.annotations import SettingAnnotation, get_setting_annotation, get_setting_fallback
from szo.config.dotenv import parse_dotenv
from szo.console import blocks


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
        _setting_names: set[str] | None = None
    ):
        """Load every declared setting from args > environ > dotenv > class default.

        - ``env_prefix``: prefix for env variable names, no trailing underscore: ``"DB"`` -> ``DB_HOST``.
        - ``arg_prefix``: prefix for argument names, including the dashes: ``"--db"`` -> ``--db-host``.
        - ``prog``: program name shown in ``--help``; defaults to the ``sys.argv[0]`` basename.
        - ``args``: pre-parsed command-line values; ``None`` parses ``sys.argv``.
        - ``environ``: environment variables; ``None`` uses ``os.environ``.
        - ``dotenv``: already-parsed mapping or a ``.env`` file path (a missing
          file is ignored); ``None`` reads no dotenv file.
        """
        if env_prefix and not env_prefix.isidentifier():
            raise ValueError(f"env_prefix {env_prefix!r} is not a valid identifier")
        if arg_prefix and not (arg_prefix.startswith("--") and arg_prefix.lstrip("-").replace("-", "_").isidentifier()):
            raise ValueError(f"arg_prefix {arg_prefix!r} must start with '--' followed by a valid name")
        self._env_prefix = env_prefix
        self._arg_prefix = arg_prefix
        self._prog = prog if prog is not None else os.path.basename(sys.argv[0])
        self._settings: dict[str, Setting] = {}
        self._nested_configs: dict[str, BaseConfig] = {}
        self._errors: list[blocks.Block] = []

        args = self._load_args(args)
        environ = dict(os.environ) if environ is None else environ
        dotenv = self._load_dotenv(dotenv)
        # `or set()` would discard a shared-but-still-empty set: empty sets are falsy.
        setting_names = set() if _setting_names is None else _setting_names
        
        type_hints = typing.get_type_hints(type(self), include_extras=True)
        for name, type_hint in type_hints.items():
            if name.startswith("_"):
                continue
            if type_hint is ClassVar or typing.get_origin(type_hint) is ClassVar:
                continue
            if isinstance(type_hint, type) and issubclass(type_hint, BaseConfig):
                self._init_nested_config(name, type_hint, args, environ, dotenv, setting_names)
            else:
                self._init_setting(name, type_hint, args, environ, dotenv, setting_names)

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
