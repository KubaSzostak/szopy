from szo.config import BaseConfig, PostgresConfig
from szo.config.postgres import _quote_conninfo_value


def make_pg(password: str = "pw", **args: str) -> PostgresConfig:
    return PostgresConfig(args={"--password": password, **args}, environ={}, dotenv={})


class TestPostgresConfig:
    def test_defaults(self):
        pg = make_pg()
        assert pg.host == "localhost"
        assert pg.port == 5432
        assert pg.dbname == "postgres"
        assert pg.user == "postgres"
        assert pg.password == "pw"

    def test_password_is_secret_and_required(self):
        pg = make_pg()
        assert pg._settings["password"].annotation.is_secret is True
        missing = PostgresConfig(args={}, environ={}, dotenv={})
        assert missing.is_valid() is False

    def test_nested_binding_names(self):
        class AppConfig(BaseConfig):
            db: PostgresConfig

        app = AppConfig(args={"--db-password": "pw"}, environ={}, dotenv={})
        arg_names = [setting.binding.arg_name for setting in app.get_settings()]
        assert arg_names == ["--db-host", "--db-port", "--db-dbname", "--db-user", "--db-password"]
        assert app.db.password == "pw"


class TestConnectKwargs:
    def test_all_core_settings(self):
        pg = make_pg(**{"--host": "db.example.com", "--port": "5433", "--dbname": "app", "--user": "svc"})
        assert pg.connect_kwargs() == {
            "host": "db.example.com",
            "port": 5433,
            "dbname": "app",
            "user": "svc",
            "password": "pw",
        }

    def test_optional_parameters_included(self):
        kwargs = make_pg().connect_kwargs(connect_timeout=10, sslmode="require", application_name="myapp")
        assert kwargs["connect_timeout"] == 10
        assert kwargs["sslmode"] == "require"
        assert kwargs["application_name"] == "myapp"

    def test_optional_parameters_omitted_by_default(self):
        kwargs = make_pg().connect_kwargs()
        assert "connect_timeout" not in kwargs
        assert "sslmode" not in kwargs
        assert "application_name" not in kwargs


class TestConninfo:
    def test_core_string(self):
        assert make_pg().conninfo() == "host=localhost port=5432 dbname=postgres user=postgres password=pw"

    def test_optional_parameters_appended(self):
        conninfo = make_pg().conninfo(connect_timeout=10, sslmode="require", application_name="myapp")
        assert conninfo.endswith("password=pw connect_timeout=10 sslmode=require application_name=myapp")

    def test_optional_parameters_omitted_by_default(self):
        conninfo = make_pg().conninfo()
        assert "connect_timeout" not in conninfo
        assert "sslmode" not in conninfo
        assert "application_name" not in conninfo

    def test_password_with_space_is_quoted(self):
        assert make_pg(password="s3 cret").conninfo().endswith("password='s3 cret'")


class TestQuoteConninfoValue:
    def test_plain_value_unquoted(self):
        assert _quote_conninfo_value("abc") == "abc"

    def test_empty_value_quoted(self):
        assert _quote_conninfo_value("") == "''"

    def test_space_quoted(self):
        assert _quote_conninfo_value("a b") == "'a b'"

    def test_single_quote_escaped(self):
        assert _quote_conninfo_value("it's") == "'it\\'s'"

    def test_backslash_escaped(self):
        assert _quote_conninfo_value("a\\b") == "'a\\\\b'"
