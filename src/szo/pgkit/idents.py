import re
from dataclasses import dataclass
from typing import LiteralString, cast
from psycopg import sql

_IDENT_RE = re.compile(r"[a-z_][a-z0-9_]*")  # PostgreSQL unquoted-identifier safe subset
_QUOTED_IDENT_RE = re.compile(r"\"(?:[^\"\x00]|\"\")+\"")

# PostgreSQL 18's RESERVED_KEYWORD and TYPE_FUNC_NAME_KEYWORD categories are
# excluded from ColId, which is required for the schema in schema.relation.
# Source: src/include/parser/kwlist.h in PostgreSQL's REL_18_STABLE branch.
_PG_INVALID_SCHEMA_KEYWORDS: frozenset[str] = frozenset(
    """
    all analyse analyze and any array as asc asymmetric authorization binary both
    case cast check collate collation column concurrently constraint create cross
    current_catalog current_date current_role current_schema current_time
    current_timestamp current_user default deferrable desc distinct do else end
    except false fetch for foreign freeze from full grant group having ilike in
    initially inner intersect into is isnull join lateral leading left like limit
    localtime localtimestamp natural not notnull null offset on only or order outer
    overlaps placing primary references returning right select session_user similar
    some symmetric system_user table tablesample then to trailing true union unique
    user using variadic verbose when where window with
    """.split()
)


def quote_ident(name: str) -> LiteralString:
    if not name or "\x00" in name:
        raise ValueError(f"not a valid PostgreSQL identifier: `{name}`")
    truncated = name.encode("utf-8")[:63].decode("utf-8", errors="ignore")
    escaped = truncated.replace("\"", "\"\"")
    return cast(LiteralString, f"\"{escaped}\"")


def normalize_ident(name: str) -> LiteralString:
    """Normalize a quoted or unquoted PostgreSQL identifier.

    Quoted identifiers retain their spelling. Unquoted identifiers mirror the
    server: they are case-folded to lowercase (TableName -> tablename) and
    truncated to 63 bytes. Raises ValueError for invalid identifier syntax.
    """
    if name.startswith('"') and name.endswith('"'):
        if _QUOTED_IDENT_RE.fullmatch(name):
            return cast(LiteralString, name)
        raise ValueError(f"not a valid quoted PostgreSQL identifier: `{name}`")
    
    if not name.isascii():
        return quote_ident(name)
    normalized = name.lower()
    if not _IDENT_RE.fullmatch(normalized):
        return quote_ident(name)
    return cast(LiteralString, normalized[:63])  # only ASCII passes, so chars == bytes


def normalize_schema(name: str) -> LiteralString:
    """Normalize a PostgreSQL schema name that is safe to use unquoted.

    Raises ValueError when the normalized name is a keyword PostgreSQL does
    not accept as the first component of an unquoted qualified relation name.
    """
    normalized = normalize_ident(name)
    if normalized.startswith('"'):
        return normalized
    if normalized in _PG_INVALID_SCHEMA_KEYWORDS:
        return quote_ident(name)  # all -> "all"
    return normalized


@dataclass(frozen=True)
class Fqrn:
    """Fully qualified relation name: schema.relation, e.g. `library.authors`.

    Intended for named relations: tables, views, materialized views and
    partitioned tables. Anonymous row sources (subqueries, VALUES lists)
    have no schema and cannot be an Fqrn.

    The constructor takes the two parts; Fqrn.ensure() accepts either a
    dotted string or an existing Fqrn:

        Fqrn("library", "authors")
        Fqrn.ensure("library.authors")
        Fqrn.ensure(existing_fqrn)  # returns existing_fqrn itself
    """

    schema: str
    relation: str

    def __post_init__(self) -> None:
        # frozen dataclass: normalization must bypass the frozen __setattr__
        object.__setattr__(self, "schema", normalize_schema(self.schema))
        object.__setattr__(self, "relation", normalize_ident(self.relation))

    @classmethod
    def ensure(cls, fqrn: "str | Fqrn") -> "Fqrn":
        """Return `fqrn` itself if already an Fqrn; parse a `schema.relation` string otherwise."""
        if isinstance(fqrn, Fqrn):
            return fqrn
        parts = fqrn.split(".")
        if len(parts) != 2:
            raise ValueError(f"expected PostgreSQL `schema.relation`, got: `{fqrn}`")
        return cls(*parts)

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> LiteralString:
        """The validated `schema.relation` SQL identifier tokens."""
        return cast(LiteralString, f"{self.schema}.{self.relation}")

    @property
    def ident(self) -> sql.Identifier:
        """psycopg Identifier for sql.SQL composition; always rendered quoted."""
        return sql.Identifier(self.schema, self.relation)
