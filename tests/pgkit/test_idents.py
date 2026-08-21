import pytest

from szo.pgkit.idents import Fqrn, normalize_ident, normalize_schema


def test_normalize_ident_rejects_kelvin_sign() -> None:
    # K lowercases to a plain `k`: it must be rejected, never folded.
    with pytest.raises(ValueError, match="unquoted"):
        normalize_ident("K")


def test_normalize_ident_folds_and_truncates_like_the_server() -> None:
    assert normalize_ident("TableName") == "tablename"
    assert normalize_ident("a" * 70) == "a" * 63


@pytest.mark.parametrize(
    "name",
    [
        "\"all\"",
        "\"odd\"\"schema\"",
        "missing \"quote",
        "\"missing quote",
        "quote\"",
        "has space",
        "table.name",
        "1digit",
        "",
    ],
)
def test_normalize_ident_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(ValueError, match="unquoted"):
        normalize_ident(name)


def test_normalize_unquoted_schema_normalizes_unreserved_name() -> None:
    assert normalize_schema("Public") == "public"


def test_normalize_unquoted_schema_accepts_pg18_column_name_keyword() -> None:
    assert normalize_schema("Between") == "between"


@pytest.mark.parametrize("schema", ["select", "JOIN", "Authorization", "All"])
def test_normalize_unquoted_schema_rejects_pg18_schema_keyword(schema: str) -> None:
    with pytest.raises(ValueError, match="schema"):
        normalize_schema(schema)


def test_fqrn_rejects_pg18_schema_keyword() -> None:
    with pytest.raises(ValueError, match="schema"):
        Fqrn("select", "records")


def test_fqrn_accepts_reserved_relation_after_safe_schema() -> None:
    assert Fqrn("public", "SELECT").full_name == "public.select"


def test_fqrn_rejects_quoted_identifiers() -> None:
    with pytest.raises(ValueError, match="unquoted"):
        Fqrn("\"all\"", "\"table_name\"")


def test_fqrn_rejects_kelvin_sign_relation() -> None:
    with pytest.raises(ValueError, match="unquoted"):
        Fqrn("public", "K")


def test_fqrn_ensure_parses_dotted_string() -> None:
    assert Fqrn.ensure("Library.Authors") == Fqrn("library", "authors")


def test_fqrn_ensure_returns_same_instance() -> None:
    fqrn = Fqrn("library", "authors")
    assert Fqrn.ensure(fqrn) is fqrn


def test_fqrn_ensure_rejects_string_without_schema() -> None:
    with pytest.raises(ValueError, match="schema.relation"):
        Fqrn.ensure("authors")
