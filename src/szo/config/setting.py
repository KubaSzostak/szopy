"""The runtime setting model: one setting's value resolved from the sources and frozen."""

import shlex

from pathlib import Path
from typing import Literal, NamedTuple

from szo import convert
from szo.config.annotations import SettingAnnotation
from szo.console.text import SECRET_MASK, get_value_text, get_choices_text, get_type_text

SettingSource = Literal["cli", "env", "dotenv", "default"]


class SettingBinding(NamedTuple):
    arg_name: str  # --db-host
    env_name: str  # DB_HOST
    is_required: bool  # no default declared on the class
    fallback_value: object  # declared class default, or a synthesized one


class Setting(NamedTuple):
    name: str  # local attribute name: "host"
    value: object  # frozen at construction
    source: SettingSource | None  # None = no value provided and no default declared
    error: str | None
    binding: SettingBinding
    annotation: SettingAnnotation

    @property
    def value_text(self) -> str:
        return SECRET_MASK if self.annotation.is_secret else get_value_text(self.value)

    @property
    def value_repr(self) -> str:
        return SECRET_MASK if self.annotation.is_secret else repr(self.value)
    
    @property
    def spec_text(self) -> str:
        binding = self.binding
        annotations = [get_type_text(self.annotation.setting_type)]
        if self.annotation.setting_type is bool:
            # Promote the bare --name form; a value is accepted but not needed.
            annotations.append("flag")
        choices_text = get_choices_text(self.annotation.setting_type)
        if choices_text:
            annotations.append(f"choices: {choices_text}")
        if self.annotation.is_secret:
            annotations.append("secret")
        if binding.is_required:
            annotations.append("required")
        else:
            default_text = SECRET_MASK if self.annotation.is_secret else get_value_text(binding.fallback_value)
            annotations.append(f"default: {shlex.quote(default_text)}")
        return " | ".join(annotations)

    @property
    def env_text(self) -> str:
        env_line = f"env: {self.binding.env_name}"
        if self.annotation.is_secret:
            env_line += f" | {self.binding.env_name}_FILE"
        return env_line
    
    @property
    def source_text(self) -> str:
        src = self.source
        if not src:
            return "source: none"
        
        if src == "cli":
            binding_src = self.binding.arg_name
        elif src == "env":
            binding_src = self.binding.env_name
        elif src == "dotenv":
            binding_src = self.binding.env_name
        elif src == "default":
            binding_src = SECRET_MASK if self.annotation.is_secret else get_value_text(self.value)
        else:
            raise ValueError(f"unexpected setting source {src!r}")
        return f"source: {src} ({shlex.quote(binding_src)})"


class SettingBuilder:
    """Mutable working state for loading one setting; ``build()`` freezes the ``Setting``."""

    def __init__(self, name: str, binding: SettingBinding, annotation: SettingAnnotation):
        self.name = name
        self.binding = binding
        self.annotation = annotation
        self.value: object = binding.fallback_value
        self.source: SettingSource | None = None
        self.error: str | None = None

    def load(
        self,
        args: dict[str, str | None],
        environ: dict[str, str],
        dotenv: dict[str, str],
    ) -> None:
        _ = self._set_arg_value(args) \
            or self._set_env_value(environ, "env") \
            or self._set_env_value(dotenv, "dotenv")
        if self.source is None:
            if not self.binding.is_required:
                self.source = "default"
            elif self.error is None:
                self.error = "required config value not provided"

    def validate_names(self, setting_names: set[str]) -> None:
        # Arg names start with "--" and env names never do, so one set holds both.
        if self.binding.arg_name in setting_names:
            self.error = "duplicate argument"
        elif self.binding.env_name in setting_names:
            self.error = "duplicate env name"
        setting_names.add(self.binding.arg_name)
        setting_names.add(self.binding.env_name)

    def build(self) -> Setting:
        # Copy so instances never share one mutable list default.
        value = self.value
        value = list(value) if isinstance(value, list) else value
        return Setting(
            name=self.name,
            value=value,
            source=self.source,
            error=self.error,
            binding=self.binding,
            annotation=self.annotation,
        )

    def _set_arg_value(self, args: dict[str, str | None]) -> bool:
        # Consider: arg_value = args.get("--foo", None)
        # It can be None for two reasons:
        # 1. the flag was not provided,
        # 2. it was provided as a bare --foo.
        if self.binding.arg_name not in args:
            return False

        arg_value = args.get(self.binding.arg_name, None)
        if self.annotation.setting_type is bool and arg_value is None:
            # A bare --flag arrives as None
            self.value = True
            self.source = "cli"
            return True

        return self._set_config_value(arg_value, "cli")

    def _set_env_value(self, env: dict[str, str], env_source: SettingSource) -> bool:
        if self.binding.env_name in env:
            return self._set_config_value(env.get(self.binding.env_name), env_source)

        if not self.annotation.is_secret:
            # NAME_FILE indirection (docker/k8s mounted secrets) is for Secret settings only.
            return False

        config_file = env.get(self.binding.env_name + "_FILE", None)
        if not config_file:
            return False

        # The source names who provided the file reference, so errors below
        # point at the right place even though the value stays the fallback.
        self.source = env_source
        config_path = Path(config_file)
        if not config_path.is_file():
            self.error = "provided config file does not exist"
            return True

        try:
            with open(config_path, encoding="utf-8") as file:
                file_content = file.read().strip()
        except OSError as exc:
            self.error = f"cannot read value from config file: {exc}"
            return True

        if not file_content:
            self.error = "provided config file is empty"
            return True

        return self._set_config_value(file_content, env_source)

    def _set_config_value(self, config_value: str | None, config_source: SettingSource) -> bool:
        """Always returns True: the setting was consumed (even if the value was invalid)."""
        self.source = config_source
        if not config_value:
            # The value was provided, but with an empty value (FOO=, --foo=, bare --foo).
            self.error = "provided empty config value"
            return True

        try:
            self.value = convert.to_type(config_value, self.annotation.setting_type)
        except ValueError as exc:
            self.error = str(exc)
        return True
