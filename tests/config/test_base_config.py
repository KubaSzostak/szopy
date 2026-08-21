import sys
import typing

from typing import Annotated, Literal

import pytest

from szo import BaseConfig, Secret
from szo.config.args import parse_args
from szo import convert
from szo.config.annotations import get_setting_annotation
from szo.config.dotenv import parse_dotenv


class DbConfig(BaseConfig):
    host: str = "localhost"
    port: Annotated[int, "server port"] = 5432
    password: Secret[str]


class ApiConfig(BaseConfig):
    client_id: str
    tags: list[str] = ["a", "b"]


class AppConfig(BaseConfig):
    """Test app config."""

    verbose: bool = False
    db: DbConfig
    api: ApiConfig


FULL_ARGV = ["--db-password", "pw", "--api-client-id", "cid"]

# Constructing with real sources would read pytest's argv, the shell
# environment, and any ./.env — tests inject explicit sources instead.
NO_SOURCES: dict = {"args": {}, "environ": {}, "dotenv": {}}


def load_app(argv):
    """AppConfig from CLI tokens and the real environment, .env disabled."""
    return AppConfig(env_prefix="SZOTEST", args=parse_args(argv), dotenv={})


def make_db(password=None):
    """A loaded config is treated as immutable — provide values via sources."""
    if password is None:
        return DbConfig(**NO_SOURCES)
    return DbConfig(args={"--password": password}, environ={}, dotenv={})


# --- Setting collection -------------------------------------------------------


class TestSettingCollection:
    def test_order_and_metadata(self):
        settings = DbConfig(**NO_SOURCES)._settings
        assert list(settings) == ["host", "port", "password"]
        assert settings["host"].annotation.setting_type is str
        assert settings["port"].annotation.setting_type is int
        assert settings["port"].annotation.description == "server port"
        assert settings["password"].annotation.is_secret is True

    def test_defaults_are_plain_class_attributes(self):
        assert DbConfig.port == 5432
        assert not hasattr(DbConfig, "password")

    def test_nested_configs_registered(self):
        app = AppConfig(**NO_SOURCES)
        assert list(app._nested_configs) == ["db", "api"]
        assert isinstance(app._nested_configs["db"], DbConfig)
        assert "db" not in app._settings

    def test_get_settings_returns_all_including_nested(self):
        app = AppConfig(args={"--db-password": "pw", "--api-client-id": "cid"}, environ={}, dotenv={})
        arg_names = [setting.binding.arg_name for setting in app.get_settings()]
        assert arg_names == ["--verbose", "--db-host", "--db-port", "--db-password", "--api-client-id", "--api-tags"]

        db_password = next(setting for setting in app.get_settings() if setting.binding.arg_name == "--db-password")
        assert db_password.value == "pw"
        assert db_password.source == "cli"
        assert db_password.error is None

        password = next(setting for setting in DbConfig(**NO_SOURCES).get_settings() if setting.name == "password")
        assert password.value == ""
        assert password.source is None
        assert password.error == "required config value not provided"

    def test_inheritance_extends_parent(self):
        class ExtendedDb(DbConfig):
            timeout: int = 30

        assert list(ExtendedDb(**NO_SOURCES)._settings) == ["host", "port", "password", "timeout"]
        assert list(DbConfig(**NO_SOURCES)._settings) == ["host", "port", "password"]

    def test_subclass_override_keeps_position(self):
        class LocalDb(DbConfig):
            port: int = 5433

        assert list(LocalDb(**NO_SOURCES)._settings) == ["host", "port", "password"]
        assert LocalDb(**NO_SOURCES).port == 5433
        assert DbConfig(**NO_SOURCES).port == 5432

    def test_private_and_classvar_skipped(self):
        class C(BaseConfig):
            x: int = 1
            _internal: str = "y"
            kind: typing.ClassVar[str] = "c"

        assert list(C(**NO_SOURCES)._settings) == ["x"]

    def test_unsupported_type_raises_at_construction(self):
        class BadDict(BaseConfig):
            data: dict

        with pytest.raises(TypeError, match="unsupported"):
            BadDict(**NO_SOURCES)

        class BadUnion(BaseConfig):
            value: int | str

        with pytest.raises(TypeError, match="unsupported"):
            BadUnion(**NO_SOURCES)

    def test_nested_with_foreign_default_raises(self):
        class Bad(BaseConfig):
            db: DbConfig = "not-a-config"  # pyright: ignore[reportAssignmentType]

        with pytest.raises(TypeError, match="DbConfig instance or None"):
            Bad(**NO_SOURCES)


# --- Annotation parsing ------------------------------------------------------


class TestAnnotations:
    def test_secret_alias(self):
        parsed = get_setting_annotation(Secret[str])
        assert parsed.setting_type is str
        assert parsed.is_secret is True

    def test_description_string(self):
        parsed = get_setting_annotation(Annotated[int, "server port"])
        assert parsed.setting_type is int
        assert parsed.description == "server port"

    def test_secret_with_description(self):
        parsed = get_setting_annotation(Annotated[Secret[str], "database password"])
        assert parsed.setting_type is str
        assert parsed.is_secret is True
        assert parsed.description == "database password"

    def test_optional_unwraps_to_inner_type(self):
        parsed = get_setting_annotation(int | None)
        assert parsed.setting_type is int
        assert parsed.is_optional is True

    def test_optional_inside_annotated(self):
        parsed = get_setting_annotation(Annotated[int | None, "seconds"])
        assert parsed.setting_type is int
        assert parsed.description == "seconds"
        assert parsed.is_optional is True

    def test_non_optional_union_rejected(self):
        with pytest.raises(TypeError, match="unsupported"):
            get_setting_annotation(int | str)


# --- Programmatic constructor ----------------------------------------------


class TestConstructor:
    def test_defaults_and_attribute_assignment(self):
        db = make_db("pw")
        assert db.host == "localhost"
        assert db.port == 5432
        assert db.password == "pw"

    def test_required_setting_left_unset(self):
        db = DbConfig(**NO_SOURCES)
        # The synthesized default keeps the setting usable; the report records it.
        assert db.password == ""
        assert [setting.name for setting in db.get_settings() if setting.error] == ["password"]
        assert db.host == "localhost"

    def test_list_default_not_shared_between_instances(self):
        a = ApiConfig(**NO_SOURCES)
        b = ApiConfig(**NO_SOURCES)
        a.tags.append("z")
        assert b.tags == ["a", "b"]

    def test_repr_masks_secrets(self):
        db = DbConfig(args={"--password": "pw"}, environ={}, dotenv={})
        assert "pw" not in repr(db)
        assert "**********" in repr(db)
        assert "localhost" in repr(db)


# --- Constructor **defaults ---------------------------------------------------


class TestConstructorDefaults:
    def test_kwarg_replaces_class_default(self):
        db = DbConfig(host="db.internal", password="pw", **NO_SOURCES)
        assert db.host == "db.internal"
        assert db._settings["host"].source == "default"

    def test_kwarg_makes_required_optional(self):
        db = DbConfig(password="pw", **NO_SOURCES)
        assert db.password == "pw"
        assert db.is_valid() is True
        assert db._settings["password"].binding.is_required is False
        assert db._settings["password"].source == "default"

    def test_class_default_kept_when_no_kwarg(self):
        db = DbConfig(password="pw", **NO_SOURCES)
        assert db.host == "localhost"

    def test_sources_still_override_kwarg_default(self):
        db = DbConfig(host="kwarg", password="pw", args={"--host": "cli"}, environ={}, dotenv={})
        assert db.host == "cli"
        db = DbConfig(host="kwarg", password="pw", args={}, environ={"HOST": "env"}, dotenv={})
        assert db.host == "env"
        db = DbConfig(host="kwarg", password="pw", args={}, environ={}, dotenv={"HOST": "dot"})
        assert db.host == "dot"

    def test_help_shows_kwarg_default(self, capsys):
        DbConfig(host="db.internal", **NO_SOURCES).print_help()
        out = capsys.readouterr().out
        assert "str | optional (default: db.internal)" in out

    def test_help_masks_secret_kwarg_default(self, capsys):
        DbConfig(password="sekret", **NO_SOURCES).print_help()
        out = capsys.readouterr().out
        assert "str | secret | optional" in out
        assert "**********" in out
        assert "sekret" not in out

    def test_list_kwarg_default(self):
        api = ApiConfig(client_id="cid", tags=["x", "y"], **NO_SOURCES)
        assert api.tags == ["x", "y"]

    def test_unknown_name_raises(self):
        with pytest.raises(TypeError, match="hostt"):
            DbConfig(hostt="x", **NO_SOURCES)

    def test_nested_config_name_raises(self):
        with pytest.raises(TypeError, match="pass its defaults to the DbConfig constructor"):
            AppConfig(db={"host": "x"}, **NO_SOURCES)

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError, match="'5433' is not a valid int"):
            DbConfig(port="5433", **NO_SOURCES)
        with pytest.raises(TypeError, match="True is not a valid int"):
            DbConfig(port=True, **NO_SOURCES)
        with pytest.raises(TypeError, match="None is not a valid str"):
            DbConfig(host=None, **NO_SOURCES)

    def test_list_item_type_checked(self):
        with pytest.raises(TypeError, match=r"item 1 of list"):
            ApiConfig(client_id="cid", tags=[1], **NO_SOURCES)

    def test_int_accepted_for_float(self):
        class Numeric(BaseConfig):
            ratio: float = 0.5

        assert Numeric(ratio=2, **NO_SOURCES).ratio == 2

    def test_literal_kwarg_checked_against_choices(self):
        assert RegionConfig(region_type="nuts", **NO_SOURCES).region_type == "nuts"
        with pytest.raises(TypeError, match="not one of: admin, postcode"):
            RegionConfig(region_type="bogus", **NO_SOURCES)

    def test_optional_accepts_none(self):
        config = OptionalConfig(row_count=None, **NO_SOURCES)
        assert config.row_count is None
        assert config._settings["row_count"].source == "default"

    def test_reserved_setting_name_raises(self):
        class BadName(BaseConfig):
            prog: str = "x"

        with pytest.raises(TypeError, match="constructor parameter"):
            BadName(**NO_SOURCES)

    def test_prebuilt_nested_with_kwarg_defaults(self):
        class WithMine(BaseConfig):
            db: DbConfig = DbConfig(host="db.internal", password="pw", **NO_SOURCES)

        config = WithMine(**NO_SOURCES)
        assert config.db.host == "db.internal"
        assert config.is_valid() is True


# --- Optional settings ---------------------------------------------------------


class OptionalConfig(BaseConfig):
    row_count: int | None = None


class TestOptionalSettings:
    def test_default_is_none(self):
        assert OptionalConfig(**NO_SOURCES).row_count is None

    def test_source_provides_value(self):
        config = OptionalConfig(args={"--row-count": "100"}, environ={}, dotenv={})
        assert config.row_count == 100

    def test_no_source_keeps_none(self):
        assert OptionalConfig(**NO_SOURCES).row_count is None

    def test_empty_env_value_keeps_none(self, monkeypatch):
        monkeypatch.setenv("ROW_COUNT", "")
        config = OptionalConfig(args={}, dotenv={})
        assert config.row_count is None


# --- Nested section defaults ------------------------------------------------


class TestNestedDefaults:
    def test_bare_and_none_sections_auto_initialized(self):
        app = AppConfig(**NO_SOURCES)
        assert isinstance(app.db, DbConfig)
        assert isinstance(app.api, ApiConfig)
        assert app.db.port == 5432

    def test_auto_initialized_sections_are_fresh_per_instance(self):
        a, b = AppConfig(**NO_SOURCES), AppConfig(**NO_SOURCES)
        assert a.db is not b.db
        assert a.api is not b.api

    def test_assigned_section_used_exactly(self):
        mine = DbConfig(**NO_SOURCES)
        mine.host = "custom"
        app = AppConfig(**NO_SOURCES)
        app.db = mine
        assert app.db is mine

    def test_prebuilt_default_used_exactly(self):
        mine = make_db("pw")

        class WithMine(BaseConfig):
            db: DbConfig = mine

        w1, w2 = WithMine(**NO_SOURCES), WithMine(**NO_SOURCES)
        assert w1.db is mine
        assert w2.db is mine
        assert w1.db.password == "pw"  # loaded from the prebuilt's own sources


# --- Section env_prefix ------------------------------------------------------


class TestSectionEnvPrefix:
    def test_prebuilt_section_loads_from_own_sources(self):
        # The consumer may load each part of the configuration from its own
        # sources (a different .env file, for example) — the parent's prefix
        # and sources do not apply.
        class WithAudit(BaseConfig):
            audit: DbConfig = DbConfig(
                env_prefix="AUDIT", args={}, environ={"AUDIT_PASSWORD": "apw"}, dotenv={}
            )

        config = WithAudit(env_prefix="SZOTEST", **NO_SOURCES)
        assert config.audit.password == "apw"

    def test_prebuilt_section_uses_own_names(self, capsys):
        class WithAudit(BaseConfig):
            audit: DbConfig = DbConfig(
                env_prefix="AUDIT", arg_prefix="--audit", **NO_SOURCES
            )

        config = WithAudit(env_prefix="SZOTEST", **NO_SOURCES)
        assert not config.is_valid()
        config.print_errors()
        err = capsys.readouterr().err
        assert "--audit-password" in err
        assert "env: AUDIT_PASSWORD" in err

    def test_standalone_section_uses_unprefixed_names(self, monkeypatch):
        monkeypatch.setenv("PASSWORD", "standalone-pw")
        db = DbConfig(args={}, dotenv={})
        assert db.password == "standalone-pw"


# --- Conversion --------------------------------------------------------------


class TestConvert:
    @pytest.mark.parametrize("raw", ["1", "true", "True", "YES", "on"])
    def test_bool_true(self, raw):
        assert convert.to_type(raw, bool) is True

    @pytest.mark.parametrize("raw", ["0", "false", "False", "No", "OFF"])
    def test_bool_false(self, raw):
        assert convert.to_type(raw, bool) is False

    def test_bool_invalid(self):
        with pytest.raises(ValueError, match="not a valid bool"):
            convert.to_type("maybe", bool)

    def test_numbers(self):
        assert convert.to_type("42", int) == 42
        assert convert.to_type("2.5", float) == 2.5

    def test_int_invalid_message(self):
        with pytest.raises(ValueError) as exc:
            convert.to_type("abc", int)
        assert str(exc.value) == "'abc' is not a valid int"

    def test_lists(self):
        assert convert.to_type("1, 2,3", list[int]) == [1, 2, 3]
        assert convert.to_type("0.5,1.5", list[float]) == [0.5, 1.5]
        assert convert.to_type("a,,b", list[str]) == ["a", "", "b"]

    def test_list_item_error_message(self):
        with pytest.raises(ValueError) as exc:
            convert.to_type("1,x,3", list[int])
        assert str(exc.value) == "'x' is not a valid int (item 2 of list)"


# --- Literal settings ----------------------------------------------------------


RegionType = Literal["admin", "postcode", "cresta", "nuts"]


class RegionConfig(BaseConfig):
    region_type: RegionType = "admin"


class TestLiteralSettings:
    def test_to_type_member_passes_through(self):
        assert convert.to_type("cresta", RegionType) == "cresta"

    def test_to_type_non_member_message(self):
        with pytest.raises(ValueError) as exc:
            convert.to_type("bogus", RegionType)
        assert str(exc.value) == "'bogus' is not one of: admin, postcode, cresta, nuts"

    def test_value_from_env(self):
        config = RegionConfig(args={}, environ={"REGION_TYPE": "nuts"}, dotenv={})
        assert config.region_type == "nuts"
        assert config._settings["region_type"].source == "env"

    def test_default_used_when_absent(self):
        config = RegionConfig(**NO_SOURCES)
        assert config.region_type == "admin"
        assert config._settings["region_type"].source == "default"

    def test_non_member_records_setting_error(self):
        config = RegionConfig(args={"--region-type": "bogus"}, environ={}, dotenv={})
        setting = config._settings["region_type"]
        assert setting.error == "'bogus' is not one of: admin, postcode, cresta, nuts"
        assert config.region_type == "admin"

    def test_required_literal_reports_missing(self):
        class RequiredRegion(BaseConfig):
            region_type: RegionType

        setting = RequiredRegion(**NO_SOURCES)._settings["region_type"]
        assert setting.error == "required config value not provided"
        assert setting.value == "admin"  # synthesized fallback: first choice

    def test_help_metadata_line(self, capsys):
        RegionConfig(**NO_SOURCES).print_help()
        out = capsys.readouterr().out
        assert "str | choices: admin, postcode, cresta, nuts | optional (default: admin)" in out

    def test_non_str_literal_raises(self):
        class BadLiteral(BaseConfig):
            level: Literal[1, 2, 3]

        with pytest.raises(TypeError, match="unsupported"):
            BadLiteral(**NO_SOURCES)


# --- .env parsing -----------------------------------------------------------


class TestDotenv:
    def test_parsing_rules(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# comment\n"
            "\n"
            "export SZO_A=1\n"
            'SZO_B="quoted value"\n'
            "SZO_C=a=b=c\n"
            "SZO_D='single'\n"
            "malformed line\n"
            "SZO_E = spaced \n"
        )
        assert parse_dotenv(str(env_file)) == {
            "SZO_A": "1",
            "SZO_B": "quoted value",
            "SZO_C": "a=b=c",
            "SZO_D": "single",
            "SZO_E": "spaced",
        }

    def test_inline_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "SZO_A=value # comment\n"
            "SZO_B=pass#word\n"
            'SZO_C="a # b" # comment\n'
        )
        assert parse_dotenv(str(env_file)) == {
            "SZO_A": "value",
            "SZO_B": "pass#word",
            "SZO_C": "a # b",
        }

    def test_missing_file_returns_empty(self, tmp_path):
        assert parse_dotenv(str(tmp_path / "nope.env")) == {}


# --- Constructor overlay: sources and precedence -----------------------------


class TestOverlay:
    def test_from_cli(self):
        config = load_app([*FULL_ARGV, "--db-port", "5433", "--verbose"])
        assert config.db.port == 5433
        assert config.db.password == "pw"
        assert config.verbose is True
        assert config.api.tags == ["a", "b"]

    def test_precedence_cli_env_dotenv_default(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("SZOTEST_DB_PORT=1111\n")
        monkeypatch.setenv("SZOTEST_DB_PORT", "2222")

        def load_with_dotenv(argv):
            return AppConfig(
                env_prefix="SZOTEST", args=parse_args(argv), dotenv=parse_dotenv(str(env_file))
            )

        assert load_with_dotenv([*FULL_ARGV, "--db-port", "3333"]).db.port == 3333
        assert load_with_dotenv(FULL_ARGV).db.port == 2222
        monkeypatch.delenv("SZOTEST_DB_PORT")
        assert load_with_dotenv(FULL_ARGV).db.port == 1111
        assert load_app(FULL_ARGV).db.port == 5432

    def test_empty_env_value_reports_missing(self):
        config = AppConfig(
            args=parse_args(FULL_ARGV), environ={"DB_PORT": ""}, dotenv={"DB_PORT": "1111"}
        )
        assert config.db.port == 5432  # default kept, dotenv NOT consulted
        assert [setting.name for setting in config.db.get_settings() if setting.error] == ["port"]

    def test_empty_value_for_required_reports_missing(self, monkeypatch, capsys):
        monkeypatch.setenv("SZOTEST_DB_PASSWORD", "")
        config = load_app(["--api-client-id", "cid"])
        assert not config.is_valid()
        config.print_errors()
        assert "--db-password" in capsys.readouterr().err

    def test_flag_collision_marks_later_definition(self, capsys):
        class Sub(BaseConfig):
            host: str = "x"

        class Root(BaseConfig):
            db: Sub
            db_host: str = "y"

        # db.host is declared first and wins; db_host is the intruder.
        config = Root(**NO_SOURCES)
        assert config.is_valid() is False
        duplicates = [setting.name for setting in config.get_settings() if setting.error == "duplicate argument"]
        assert duplicates == ["db_host"]
        config.print_errors()
        assert "duplicate argument" in capsys.readouterr().err

    def test_flag_collision_reported_across_levels(self):
        class Leaf(BaseConfig):
            host: str = "x"

        class Mid(BaseConfig):
            b: Leaf

        class Root(BaseConfig):
            a: Mid
            a_b_host: str = "y"

        config = Root(**NO_SOURCES)
        assert config.is_valid() is False
        duplicates = [setting.name for setting in config.get_settings() if setting.error]
        assert duplicates == ["a_b_host"]

    def test_env_collision_with_prebuilt_section(self):
        class Sub(BaseConfig):
            host: str = "x"

        class Root(BaseConfig):
            db: Sub = Sub(env_prefix="APP", arg_prefix="--db", **NO_SOURCES)
            app_host: str = "y"

        # The flags differ (--db-host vs --app-host) but both read env APP_HOST.
        config = Root(**NO_SOURCES)
        assert config.is_valid() is False
        duplicates = [setting.name for setting in config.get_settings() if setting.error == "duplicate env name"]
        assert duplicates == ["app_host"]


# --- Constructor overlay: injected source dicts ------------------------------


class TestSourceInjection:
    def test_args_dict_used_directly(self):
        config = AppConfig(
            env_prefix="SZOTEST",
            args={"--db-password": "pw", "--api-client-id": "cid", "--db-port": "9"},
            environ={},
            dotenv={},
        )
        assert config.db.port == 9
        assert config.is_valid() is True

    def test_envs_dict_replaces_os_environ(self, monkeypatch):
        monkeypatch.setenv("SZOTEST_DB_PORT", "1111")
        config = AppConfig(
            env_prefix="SZOTEST",
            args=parse_args(FULL_ARGV),
            environ={"SZOTEST_DB_PORT": "2222"},
            dotenv={},
        )
        assert config.db.port == 2222

    def test_dotenvs_dict_is_lowest_source(self):
        config = AppConfig(
            env_prefix="SZOTEST",
            args=parse_args(FULL_ARGV),
            environ={},
            dotenv={"SZOTEST_DB_PORT": "3333"},
        )
        assert config.db.port == 3333


# --- parse_args: the argv config provider ------------------------------------


class TestParseConfigArgs:
    def test_all_forms(self):
        assert parse_args(["--a", "1", "--b=2", "--c", "--no-d"]) == {
            "--a": "1",
            "--b": "2",
            "--c": None,
            "--no-d": None,
        }

    def test_bare_flag_before_another_flag(self):
        assert parse_args(["--a", "--b", "x"]) == {"--a": None, "--b": "x"}

    def test_positional_rejected(self):
        with pytest.raises(ValueError, match="unexpected argument"):
            parse_args(["stray"])


# --- Constructor overlay: argv handling ---------------------------------------


class TestArgvParsing:
    def test_inline_value(self):
        config = load_app([*FULL_ARGV, "--db-port=7"])
        assert config.db.port == 7

    def test_empty_inline_value_reports_missing(self):
        config = load_app([*FULL_ARGV, "--db-host="])
        assert config.db.host == "localhost"
        assert [setting.name for setting in config.db.get_settings() if setting.error] == ["host"]

    def test_bare_flag_on_non_bool_reports_missing(self, capsys):
        config = load_app([*FULL_ARGV, "--db-port"])
        assert config.db.port == 5432
        config.print_errors()
        err = capsys.readouterr().err
        assert "provided empty config value" in err
        assert "--db-port" in err

    def test_help_flag_is_not_unknown(self):
        config = load_app([*FULL_ARGV, "--help"])
        assert config.is_valid() is True


# --- Constructor overlay: file-indirected values ------------------------------


class TestConfigLevelErrors:
    def test_stray_positional_recorded_not_raised(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prog", "bogus", "--host", "x"])
        db = DbConfig(environ={}, dotenv={})
        assert db.is_valid() is False
        db.print_errors()
        err = capsys.readouterr().err
        assert "DbConfig" in err
        assert "invalid command line arguments" in err
        assert "unexpected argument 'bogus'" in err

    def test_help_survives_argv_parse_error(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "bogus", "--help"])
        db = DbConfig(environ={}, dotenv={})
        assert db.is_help_requested() is True

    def test_dotenv_path_is_parsed(self, tmp_path):
        dotenv_file = tmp_path / "custom.env"
        dotenv_file.write_text("HOST=from-dotenv\n", encoding="utf-8")
        db = DbConfig(args={"--password": "pw"}, environ={}, dotenv=str(dotenv_file))
        assert db.host == "from-dotenv"

    def test_dotenv_none_reads_nothing(self):
        db = DbConfig(args={"--password": "pw"}, environ={}, dotenv=None)
        assert db.host == "localhost"

    def test_unreadable_dotenv_recorded(self, tmp_path, capsys):
        dotenv_file = tmp_path / "binary.env"
        dotenv_file.write_bytes(b"\xff\xfe\x00broken")
        db = DbConfig(args={"--password": "pw"}, environ={}, dotenv=str(dotenv_file))
        assert db.is_valid() is False
        db.print_errors()
        err = capsys.readouterr().err
        assert "cannot read dotenv file" in err

    def test_errors_shown_in_print_config(self, tmp_path, capsys):
        dotenv_file = tmp_path / "binary.env"
        dotenv_file.write_bytes(b"\xff\xfe\x00broken")
        db = DbConfig(args={"--password": "pw"}, environ={}, dotenv=str(dotenv_file))
        db.print_config()
        assert "cannot read dotenv file" in capsys.readouterr().out


class TestFileValues:
    def test_env_file_suffix_reads_content(self, tmp_path, monkeypatch):
        secret_file = tmp_path / "db_password"
        secret_file.write_text("filepw\n")
        monkeypatch.setenv("SZOTEST_DB_PASSWORD_FILE", str(secret_file))
        config = load_app(["--api-client-id", "cid"])
        assert config.db.password == "filepw"

    def test_direct_env_wins_over_file(self, tmp_path, monkeypatch):
        secret_file = tmp_path / "db_password"
        secret_file.write_text("filepw")
        monkeypatch.setenv("SZOTEST_DB_PASSWORD_FILE", str(secret_file))
        monkeypatch.setenv("SZOTEST_DB_PASSWORD", "direct")
        config = load_app(["--api-client-id", "cid"])
        assert config.db.password == "direct"

    def test_cli_value_is_never_indirected(self, tmp_path):
        value_file = tmp_path / "value.txt"
        value_file.write_text("content")
        config = load_app([*FULL_ARGV, "--db-host", str(value_file)])
        assert config.db.host == str(value_file)

    def test_dotenv_file_suffix(self, tmp_path):
        secret_file = tmp_path / "db_password"
        secret_file.write_text("dotenv-filepw")
        env_file = tmp_path / ".env"
        env_file.write_text(f"SZOTEST_DB_PASSWORD_FILE={secret_file}\n")
        config = AppConfig(
            env_prefix="SZOTEST",
            args={"--api-client-id": "cid"},
            environ={},
            dotenv=parse_dotenv(str(env_file)),
        )
        assert config.db.password == "dotenv-filepw"

    def test_missing_value_file_reported_invalid(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("SZOTEST_DB_PASSWORD_FILE", str(tmp_path / "nope"))
        config = load_app(["--api-client-id", "cid"])
        assert not config.is_valid()
        config.print_errors()
        assert "does not exist" in capsys.readouterr().err
        password = next(setting for setting in config.db.get_settings() if setting.name == "password")
        assert password.source == "env"  # the broken file reference came from env

    def test_empty_value_file_reported_invalid(self, tmp_path, monkeypatch, capsys):
        secret_file = tmp_path / "db_password"
        secret_file.write_text("   \n")
        monkeypatch.setenv("SZOTEST_DB_PASSWORD_FILE", str(secret_file))
        config = load_app(["--api-client-id", "cid"])
        assert not config.is_valid()
        config.print_errors()
        assert "is empty" in capsys.readouterr().err
        password = next(setting for setting in config.db.get_settings() if setting.name == "password")
        assert password.source == "env"  # the broken file reference came from env

    def test_file_ignored_for_non_secret_settings(self, tmp_path, monkeypatch):
        port_file = tmp_path / "port"
        port_file.write_text("9999")
        monkeypatch.setenv("SZOTEST_DB_PORT_FILE", str(port_file))
        config = load_app(FULL_ARGV)
        assert config.db.port == 5432  # NAME_FILE applies to Secret settings only

    def test_file_content_is_converted(self, tmp_path):
        class Tokens(BaseConfig):
            pin: Secret[int] = 0

        pin_file = tmp_path / "pin"
        pin_file.write_text("9999")
        config = Tokens(args={}, environ={"PIN_FILE": str(pin_file)}, dotenv={})
        assert config.pin == 9999


# --- print_help(), print_config() and is_valid() ------------------------------


class TestPrintHelp:
    def test_prints_generated_help(self, capsys):
        AppConfig(env_prefix="SZOTEST", prog="demo", **NO_SOURCES).print_help()
        out = capsys.readouterr().out
        assert "usage: demo" in out
        assert "Test app config." in out
        assert "\ndb\n" in out
        assert "\napi\n" in out
        assert "server port" in out
        assert "int | optional (default: 5432)" in out
        assert "str | secret | required" in out
        assert "env: SZOTEST_DB_PASSWORD | SZOTEST_DB_PASSWORD_FILE" in out
        assert "list[str] | optional (default: a,b)" in out

    def test_nested_docstring_in_section_header(self, capsys):
        class Documented(BaseConfig):
            """Section description."""

            value: int = 1

        class App(BaseConfig):
            section: Documented

        App(**NO_SOURCES).print_help()
        assert "\nsection\n  Section description.\n" in capsys.readouterr().out

    def test_exact_layout(self, capsys):
        class Small(BaseConfig):
            """Small test config."""

            name: Annotated[str, "the name"] = "x y"
            token: Secret[str]

        Small(prog="small", **NO_SOURCES).print_help()
        expected = (
            "usage: small [--help] [options]\n"
            "\n"
            "Small test config.\n"
            "\n"
            f"  {'--help':<25}  show this help message and exit\n"
            f"  {'--name':<25}  the name\n"
            f"  {'':<25}  str | optional (default: 'x y')\n"
            f"  {'':<25}  env: NAME\n"
            f"  {'--token':<25}  str | secret | required\n"
            f"  {'':<25}  env: TOKEN | TOKEN_FILE\n"
        )
        assert capsys.readouterr().out == expected

    def test_no_generated_no_flags(self, capsys):
        AppConfig(prog="demo", **NO_SOURCES).print_help()
        out = capsys.readouterr().out
        assert "--verbose" in out
        assert "--no-verbose" not in out


class TestPrintConfig:
    def test_prints_all_settings_with_values(self, capsys):
        app = AppConfig(env_prefix="SZOTEST", **NO_SOURCES)
        app.print_config()
        out = capsys.readouterr().out
        assert "Config:" in out
        assert "--db-host" in out
        assert "localhost" in out
        assert "source: default" in out
        assert "--api-tags" in out
        assert "a,b" in out
        assert "--verbose" in out
        assert "false" in out
        # Missing required settings report inline instead of a value.
        assert "ERROR: required config value not provided" in out

    def test_masks_secrets(self, capsys):
        app = AppConfig(
            env_prefix="SZOTEST", args={"--db-password": "sekret-pw"}, environ={}, dotenv={}
        )
        app.print_config()
        out = capsys.readouterr().out
        assert "sekret-pw" not in out
        assert "**********" in out

    def test_standalone_section_uses_own_names(self, capsys):
        make_db("pw").print_config()
        out = capsys.readouterr().out
        assert "host " in out
        assert "db_host" not in out


class TestIsValid:
    def test_fresh_config_with_required_settings_is_invalid(self):
        assert AppConfig(**NO_SOURCES).is_valid() is False
        assert DbConfig(**NO_SOURCES).is_valid() is False

    def test_valid_after_filling_required_settings(self):
        assert make_db("pw").is_valid() is True

    def test_valid_after_full_overlay(self):
        assert load_app(FULL_ARGV).is_valid() is True

    def test_checks_nested_leaves(self):
        app = AppConfig(args={"--db-password": "pw"}, environ={}, dotenv={})
        assert app.is_valid() is False  # api.client_id still not provided
        app = AppConfig(args={"--db-password": "pw", "--api-client-id": "cid"}, environ={}, dotenv={})
        assert app.is_valid() is True

    def test_invalid_source_value_makes_invalid(self):
        config = load_app([*FULL_ARGV, "--db-port", "abc"])
        assert config.db.port == 5432
        assert config.is_valid() is False


class TestHelpAndValidateOrExit:
    def test_help_requested(self):
        config = DbConfig(args={"--help": None}, environ={}, dotenv={})
        assert config.is_help_requested() is True

    def test_help_not_requested(self):
        assert DbConfig(**NO_SOURCES).is_help_requested() is False

    def test_help_wins_over_errors_and_exits_0(self, capsys):
        # password is missing, but --help takes priority: help on stdout, exit 0.
        config = DbConfig(args={"--help": None}, environ={}, dotenv={})
        with pytest.raises(SystemExit) as exc:
            config.validate_or_exit()
        assert exc.value.code == 0
        assert "--password" in capsys.readouterr().out

    def test_errors_exit_2(self, capsys):
        config = DbConfig(**NO_SOURCES)  # password missing
        with pytest.raises(SystemExit) as exc:
            config.validate_or_exit()
        assert exc.value.code == 2
        assert "required config value not provided" in capsys.readouterr().err

    def test_returns_when_all_is_fine(self):
        make_db("pw").validate_or_exit()


# --- Bool flag forms ----------------------------------------------------------


class TestBoolFlags:
    @pytest.mark.parametrize(
        "extra,expected",
        [
            (["--verbose"], True),
            (["--verbose=true"], True),
            (["--verbose=false"], False),
            (["--verbose", "false"], False),
            ([], False),
        ],
    )
    def test_cli_forms(self, extra, expected):
        config = load_app([*FULL_ARGV, *extra])
        assert config.verbose is expected

    def test_flag_does_not_consume_next_option(self):
        config = load_app([*FULL_ARGV, "--verbose", "--db-port", "9"])
        assert config.verbose is True
        assert config.db.port == 9

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("SZOTEST_VERBOSE", "yes")
        assert load_app(FULL_ARGV).verbose is True

    def test_invalid_value_reported(self, capsys):
        config = load_app([*FULL_ARGV, "--verbose=maybe"])
        assert not config.is_valid()
        config.print_errors()
        assert "'maybe' is not a valid bool" in capsys.readouterr().err

    def test_help_metadata_marks_flag(self, capsys):
        AppConfig(prog="demo", **NO_SOURCES).print_help()
        assert "bool | flag | optional (default: false)" in capsys.readouterr().out

    def test_setting_named_no_something_is_reachable(self):
        class Flags(BaseConfig):
            no_cache: bool = False

        config = Flags(args=parse_args(["--no-cache"]), environ={}, dotenv={})
        assert config.no_cache is True


# --- Error report -------------------------------------------------------------


class TestErrorReport:
    def test_exact_output(self, capsys):
        config = load_app(["--db-port", "abc"])
        assert not config.is_valid()
        config.print_errors()
        # Sections mirror the config tree; the root section (verbose) has no
        # errors and prints nothing.
        expected = (
            "Errors:\n"
            "\n"
            "db\n"
            f"  {'--db-port':<25}  'abc' is not a valid int\n"
            f"  {'':<25}  int | optional (default: 5432)\n"
            f"  {'':<25}  env: SZOTEST_DB_PORT\n"
            f"  {'--db-password':<25}  required config value not provided\n"
            f"  {'':<25}  str | secret | required\n"
            f"  {'':<25}  env: SZOTEST_DB_PASSWORD | SZOTEST_DB_PASSWORD_FILE\n"
            "\n"
            "api\n"
            f"  {'--api-client-id':<25}  required config value not provided\n"
            f"  {'':<25}  str | required\n"
            f"  {'':<25}  env: SZOTEST_API_CLIENT_ID\n"
        )
        assert capsys.readouterr().err == expected
