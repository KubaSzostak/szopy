from typing import Annotated, Literal

import pytest

from szo.config import BaseConfig, ItemSelector, FirstItem, LastItem, AllItems, Secret
from szo.config.annotations import get_setting_annotation, get_selectors_text

# Constructing with real sources would read pytest's argv, the shell
# environment, and any ./.env — tests inject explicit sources instead.
NO_SOURCES: dict = {"args": {}, "environ": {}, "dotenv": {}}


class JobConfig(BaseConfig):
    region_ids: list[str] | AllItems | FirstItem | LastItem = ItemSelector.ALL
    region_id: Annotated[str | LastItem, "region to process"] = "r0"


class PlainConfig(BaseConfig):
    name: str = ""


# --- Annotation parsing ------------------------------------------------------


class TestSelectorAnnotations:
    def test_union_collects_selectors(self):
        parsed = get_setting_annotation(list[str] | AllItems | FirstItem)
        assert parsed.setting_type == list[str]
        assert parsed.selectors == {ItemSelector.ALL, ItemSelector.FIRST}
        assert parsed.is_optional is False

    def test_optional_combines_with_selectors(self):
        parsed = get_setting_annotation(str | AllItems | None)
        assert parsed.setting_type is str
        assert parsed.selectors == {ItemSelector.ALL}
        assert parsed.is_optional is True

    def test_annotated_wrapper_propagates_selectors(self):
        parsed = get_setting_annotation(Annotated[str | LastItem, "region to process"])
        assert parsed.setting_type is str
        assert parsed.description == "region to process"
        assert parsed.selectors == {ItemSelector.LAST}

    def test_secret_with_selector(self):
        parsed = get_setting_annotation(Secret[str] | LastItem)
        assert parsed.is_secret is True
        assert parsed.selectors == {ItemSelector.LAST}

    def test_selectors_without_base_type_rejected(self):
        with pytest.raises(TypeError, match="unsupported"):
            get_setting_annotation(AllItems | LastItem)
        with pytest.raises(TypeError, match="unsupported"):
            get_setting_annotation(AllItems)

    def test_choices_with_selectors_rejected(self):
        with pytest.raises(TypeError, match="choices cannot be combined with selectors"):
            get_setting_annotation(Literal["a", "b"] | AllItems)

    def test_mixed_selector_literal_rejected(self):
        with pytest.raises(TypeError, match="unsupported"):
            get_setting_annotation(Literal[ItemSelector.ALL, "x"])

    def test_two_base_types_still_rejected(self):
        with pytest.raises(TypeError, match="unsupported"):
            get_setting_annotation(int | str | AllItems)

    def test_selectors_text_in_declaration_order(self):
        assert get_selectors_text(frozenset({ItemSelector.ALL, ItemSelector.FIRST})) == "@first, @all"


# --- Loading from sources ----------------------------------------------------


class TestSelectorLoading:
    def test_from_cli(self):
        config = JobConfig(args={"--region-ids": "@last"}, environ={}, dotenv={})
        assert config.region_ids is ItemSelector.LAST
        assert config._settings["region_ids"].source == "cli"

    def test_from_env(self):
        config = JobConfig(args={}, environ={"REGION_IDS": "@first"}, dotenv={})
        assert config.region_ids is ItemSelector.FIRST

    def test_from_dotenv(self):
        config = JobConfig(args={}, environ={}, dotenv={"REGION_IDS": "@all"})
        assert config.region_ids is ItemSelector.ALL

    def test_default_selector(self):
        config = JobConfig(**NO_SOURCES)
        assert config.region_ids is ItemSelector.ALL
        assert config._settings["region_ids"].source == "default"
        assert config.is_valid() is True

    def test_plain_value_still_converts(self):
        config = JobConfig(args={"--region-ids": "r1,r2"}, environ={}, dotenv={})
        assert config.region_ids == ["r1", "r2"]

    def test_word_without_sigil_is_data(self):
        config = JobConfig(args={"--region-ids": "all"}, environ={}, dotenv={})
        assert config.region_ids == ["all"]

    def test_sigil_on_non_selector_setting_is_data(self):
        config = PlainConfig(args={"--name": "@all"}, environ={}, dotenv={})
        assert config.name == "@all"

    def test_undeclared_selector_reports_error(self):
        config = JobConfig(args={"--region-id": "@first"}, environ={}, dotenv={})
        setting = config._settings["region_id"]
        assert setting.error == "'@first' is not a valid selector (use @last)"
        assert config.region_id == "r0"  # fallback kept, like other value errors
        assert config.is_valid() is False

    def test_unknown_selector_reports_error(self):
        config = JobConfig(args={"--region-ids": "@bogus"}, environ={}, dotenv={})
        setting = config._settings["region_ids"]
        assert setting.error == "'@bogus' is not a valid selector (use @first, @last, @all)"

    def test_selector_must_be_whole_value(self):
        config = JobConfig(args={"--region-ids": "@all,r2"}, environ={}, dotenv={})
        assert config._settings["region_ids"].error is not None

    def test_sources_override_selector_default(self):
        config = JobConfig(args={"--region-ids": "r1"}, environ={}, dotenv={})
        assert config.region_ids == ["r1"]

    def test_optional_selector_setting(self):
        class Opt(BaseConfig):
            row_filter: str | AllItems | None = None

        assert Opt(**NO_SOURCES).row_filter is None
        assert Opt(args={"--row-filter": "@all"}, environ={}, dotenv={}).row_filter is ItemSelector.ALL
        assert Opt(args={"--row-filter": "x=1"}, environ={}, dotenv={}).row_filter == "x=1"


# --- Constructor **defaults --------------------------------------------------


class TestSelectorDefaultsKwarg:
    def test_kwarg_selector_default(self):
        config = JobConfig(region_id=ItemSelector.LAST, **NO_SOURCES)
        assert config.region_id is ItemSelector.LAST
        assert config._settings["region_id"].source == "default"

    def test_required_selector_setting_defaulted_by_kwarg(self):
        class Sweep(BaseConfig):
            ids: list[str] | AllItems

        config = Sweep(ids=ItemSelector.ALL, **NO_SOURCES)
        assert config.ids is ItemSelector.ALL
        assert config.is_valid() is True

    def test_kwarg_undeclared_selector_raises(self):
        with pytest.raises(TypeError, match="not one of the declared selectors: @last"):
            JobConfig(region_id=ItemSelector.FIRST, **NO_SOURCES)

    def test_kwarg_selector_on_plain_setting_raises(self):
        with pytest.raises(TypeError, match="no selectors declared"):
            PlainConfig(name=ItemSelector.ALL, **NO_SOURCES)


# --- Help, config report, repr -----------------------------------------------


class TestSelectorOutput:
    def test_help_lists_selectors(self, capsys):
        JobConfig(prog="job", **NO_SOURCES).print_help()
        out = capsys.readouterr().out
        assert "list[str] | selectors: @first, @last, @all | optional (default: @all)" in out
        assert "str | selectors: @last | optional (default: r0)" in out

    def test_print_config_shows_selector_value(self, capsys):
        JobConfig(**NO_SOURCES).print_config()
        out = capsys.readouterr().out
        assert "@all" in out
        assert "source: default (@all)" in out

    def test_repr_shows_selector(self):
        assert "region_ids=ItemSelector.ALL" in repr(JobConfig(**NO_SOURCES))
