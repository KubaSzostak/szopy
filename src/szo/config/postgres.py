"""Ready-made PostgreSQL connection config for psycopg (v3) applications.

szo does not import psycopg: ``PostgresConfig`` only produces connection
parameters in the shapes ``psycopg.connect()`` accepts.
"""

from typing import Annotated, Literal, TypeAlias

from szo.config.annotations import Secret
from szo.config.base_config import BaseConfig

SslMode: TypeAlias = Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]


def _quote_conninfo_value(value: str) -> str:
    # libpq quoting: empty values and values containing spaces, quotes, or
    # backslashes go in single quotes; ``'`` and ``\`` are backslash-escaped.
    if value and not any(char in value for char in " '\\"):
        return value
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


class PostgresConfig(BaseConfig):
    """PostgreSQL connection settings."""

    host: Annotated[str, "PostgreSQL server host"] = "localhost"
    port: Annotated[int, "PostgreSQL server port"] = 5432
    dbname: Annotated[str, "PostgreSQL database name"] = "postgres"
    user: Annotated[str, "PostgreSQL database user"] = "postgres"
    password: Annotated[Secret[str], "PostgreSQL database password"]

    def connect_kwargs(
        self,
        connect_timeout: int | None = None,
        sslmode: SslMode | None = None,
        application_name: str | None = None,
    ) -> dict[str, str | int]:
        """Keyword arguments for ``psycopg.connect(**config.connect_kwargs())``.

        The optional parameters are included only when provided.
        """
        kwargs: dict[str, str | int] = {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
        }
        if connect_timeout is not None:
            kwargs["connect_timeout"] = connect_timeout
        if sslmode is not None:
            kwargs["sslmode"] = sslmode
        if application_name is not None:
            kwargs["application_name"] = application_name
        return kwargs

    def conninfo(
        self,
        connect_timeout: int | None = None,
        sslmode: SslMode | None = None,
        application_name: str | None = None,
    ) -> str:
        """libpq connection string: ``host=... port=... dbname=... user=... password=...``.

        The optional parameters are appended only when provided. The result
        contains the password in clear text — do not log it.
        """
        parts = {
            "host": self.host,
            "port": str(self.port),
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
        }
        if connect_timeout is not None:
            parts["connect_timeout"] = str(connect_timeout)
        if sslmode is not None:
            parts["sslmode"] = sslmode
        if application_name is not None:
            parts["application_name"] = application_name
        return " ".join(f"{key}={_quote_conninfo_value(value)}" for key, value in parts.items())
