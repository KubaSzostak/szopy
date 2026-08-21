import pytest

from szo.pgkit.idents import Fqrn, normalize_ident, normalize_schema, quote_ident


def test_normalize_ident_quotes_kelvin_sign() -> None:
    assert normalize_ident("\u212a") == "\"\u212a\""


def test_quote_ident_escapes_embedded_quotes() -> None:
    assert quote_ident("table\"name") == "\"table\"\"name\""


def test_quote_ident_truncates_without_splitting_utf8_character() -> None:
    assert quote_ident("a" * 62 + "\u0105") == "\"" + "a" * 62 + "\""


def test_normalize_unquoted_schema_normalizes_unreserved_name() -> None:
    assert normalize_schema("Public") == "public"


def test_normalize_unquoted_schema_accepts_pg18_column_name_keyword() -> None:
    assert normalize_schema("Between") == "between"


@pytest.mark.parametrize("schema", ["select", "JOIN", "Authorization"])
def test_normalize_unquoted_schema_rejects_pg18_schema_keyword(schema: str) -> None:
    with pytest.raises(ValueError, match="schema"):
        normalize_schema(schema)


def test_fqrn_rejects_pg18_schema_keyword() -> None:
    with pytest.raises(ValueError, match="schema"):
        Fqrn("select", "records")


def test_fqrn_accepts_reserved_relation_after_safe_schema() -> None:
    assert Fqrn("public", "SELECT").full_name == "public.select"


def test_fqrn_accepts_quoted_identifiers() -> None:
    fqrn = Fqrn("\"all\"", "\"table_name\"")

    assert str(fqrn) == "\"all\".\"table_name\""
    assert fqrn.ident.as_string() == "\"all\".\"table_name\""


def test_fqrn_preserves_and_decodes_escaped_quotes() -> None:
    fqrn = Fqrn("\"odd\"\"schema\"", "\"table.name\"")

    assert fqrn.full_name == "\"odd\"\"schema\".\"table.name\""
    assert fqrn.ident.as_string() == "\"odd\"\"schema\".\"table.name\""


def test_normalize_ident_rejects_malformed_quoted_identifier() -> None:
    with pytest.raises(ValueError, match="quoted PostgreSQL identifier"):
        normalize_ident("\"missing quote")


def test_fqrn_quotes_kelvin_sign_relation() -> None:
    assert Fqrn("public", "\u212a").full_name == "public.\"\u212a\""


def test_fqrn_ensure_parses_dotted_string() -> None:
    assert Fqrn.ensure("Library.Authors") == Fqrn("library", "authors")


def test_fqrn_ensure_returns_same_instance() -> None:
    fqrn = Fqrn("library", "authors")
    assert Fqrn.ensure(fqrn) is fqrn


def test_fqrn_ensure_rejects_string_without_schema() -> None:
    with pytest.raises(ValueError, match="schema.relation"):
        Fqrn.ensure("authors")
