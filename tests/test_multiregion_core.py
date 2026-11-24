"""Unit tests for cockroachdb.core.multiregion — the shared compare logic.

Pure logic only; no database. Covers every branch of ``evaluate`` (both
directions, contradictions), the ``check_outcome`` mode rules (the teeth-check
for contradiction-fails-in-warn), identifier quoting/parsing, and ``load_state``
against a routed fake query.
"""

from __future__ import annotations

from cockroachdb.core import multiregion as mr
from cockroachdb.core.multiregion import (
    Kind,
    MultiregionReport,
    MultiregionState,
    MultiregionTable,
    TableInfo,
    check_outcome,
    evaluate,
    kind_for,
    parse_identifier,
    quote_identifier,
    regional_by_row_column,
)


def _state(*, primary="us-east1", regions=("us-east1", "us-west1"), tables=None, keywords=()):
    return MultiregionState(
        database="defaultdb",
        current_schema="public",
        primary_region=primary,
        cluster_regions=list(regions),
        tables=tables or {},
        keywords=set(keywords),
    )


def _global(entity="app.Product", table="products"):
    return MultiregionTable(entity=entity, table=table, kind=Kind.GLOBAL)


def _rbr(entity="app.Order", table="orders", region_column=None):
    return MultiregionTable(
        entity=entity, table=table, kind=Kind.REGIONAL_BY_ROW, region_column=region_column
    )


def _plain(entity="app.Thing", table="things"):
    return MultiregionTable(entity=entity, table=table, kind=Kind.NONE)


# --- identifiers -----------------------------------------------------------


def test_quote_plain_identifier_unquoted():
    assert quote_identifier("orders", set()) == "orders"


def test_quote_keyword_is_quoted():
    assert quote_identifier("select", {"select"}) == '"select"'


def test_quote_mixed_case_is_quoted():
    assert quote_identifier("Orders", set()) == '"Orders"'


def test_quote_doubles_embedded_quote():
    assert quote_identifier('a"b', set()) == '"a""b"'


def test_parse_qualified_quoted_name():
    assert parse_identifier('app."Orders"') == ["app", "Orders"]


def test_parse_unquoted_folds_lower():
    assert parse_identifier("App.ORDERS") == ["app", "orders"]


def test_regional_by_row_column_implicit():
    assert regional_by_row_column("REGIONAL BY ROW") == "crdb_region"


def test_regional_by_row_column_explicit():
    assert regional_by_row_column('REGIONAL BY ROW AS "region"') == "region"


def test_regional_by_row_column_not_rbr():
    assert regional_by_row_column("GLOBAL") is None


def test_kind_for_mapping():
    assert kind_for("GLOBAL") is Kind.GLOBAL
    assert kind_for("REGIONAL BY ROW") is Kind.REGIONAL_BY_ROW
    assert kind_for(None) is Kind.NONE


# --- check_outcome (teeth target) ------------------------------------------


def test_outcome_empty_is_ok():
    assert check_outcome("warn", MultiregionReport()) == "ok"


def test_outcome_plain_problem_warns_in_warn():
    r = MultiregionReport()
    r.problem("x")
    assert check_outcome("warn", r) == "warn"


def test_outcome_contradiction_fails_even_in_warn():
    r = MultiregionReport()
    r.contradiction("the schema and model disagree")
    # This is the teeth: a contradiction must FAIL in warn mode, not merely warn.
    assert check_outcome("warn", r) == "fail"


def test_outcome_any_problem_fails_in_validate():
    r = MultiregionReport()
    r.problem("x")
    assert check_outcome("validate", r) == "fail"


# --- evaluate: database not multi-region -----------------------------------


def test_not_multiregion_with_regions_suggests_primary_and_add():
    state = _state(primary=None, regions=("us-east1", "us-west1", "us-central1"))
    report = evaluate(state, [_global()])
    assert not report.is_empty()
    assert any("is not multi-region" in p for p in report.problems)
    assert 'ALTER DATABASE defaultdb SET PRIMARY REGION "us-east1";' in report.statements
    assert 'ALTER DATABASE defaultdb ADD REGION "us-west1";' in report.statements
    assert 'ALTER DATABASE defaultdb ADD REGION "us-central1";' in report.statements


def test_not_multiregion_no_cluster_regions_has_no_statements():
    state = _state(primary=None, regions=())
    report = evaluate(state, [_global()])
    assert any("no regions" in p for p in report.problems)
    # Only the DATABASE-level advice; the per-table advice still adds a SET LOCALITY.
    assert not any("ALTER DATABASE" in s for s in report.statements)


# --- evaluate: GLOBAL ------------------------------------------------------


def test_global_table_missing():
    report = evaluate(_state(tables={}), [_global()])
    assert any("does not exist" in p for p in report.problems)


def test_global_table_already_global_is_clean():
    tables = {("public", "products"): TableInfo("GLOBAL")}
    report = evaluate(_state(tables=tables), [_global()])
    assert report.is_empty()


def test_global_table_is_rbr_is_contradiction():
    tables = {("public", "products"): TableInfo("REGIONAL BY ROW")}
    report = evaluate(_state(tables=tables), [_global()])
    assert report.has_contradictions()
    assert "ALTER TABLE public.products SET LOCALITY GLOBAL;" in report.statements


def test_global_table_other_locality_is_problem_not_contradiction():
    tables = {("public", "products"): TableInfo("REGIONAL BY TABLE IN PRIMARY REGION")}
    report = evaluate(_state(tables=tables), [_global()])
    assert not report.has_contradictions()
    assert not report.is_empty()
    assert "ALTER TABLE public.products SET LOCALITY GLOBAL;" in report.statements


# --- evaluate: REGIONAL BY ROW ---------------------------------------------


def test_rbr_table_already_rbr_is_clean():
    tables = {("public", "orders"): TableInfo("REGIONAL BY ROW")}
    report = evaluate(_state(tables=tables), [_rbr()])
    assert report.is_empty()


def test_rbr_table_is_global_is_contradiction():
    tables = {("public", "orders"): TableInfo("GLOBAL", {"crdb_region": "crdb_internal_region"})}
    report = evaluate(_state(tables=tables), [_rbr()])
    assert report.has_contradictions()
    assert any("SET LOCALITY REGIONAL BY ROW" in s for s in report.statements)


def test_rbr_custom_column_wrong_type_is_problem():
    # Table is not yet RBR on the wanted column, and the column exists as STRING.
    tables = {
        ("public", "orders"): TableInfo(
            "REGIONAL BY TABLE IN PRIMARY REGION", {"region": "STRING"}
        )
    }
    report = evaluate(_state(tables=tables), [_rbr(region_column="region")])
    assert any("needs a crdb_internal_region column" in p for p in report.problems)


def test_rbr_custom_column_missing_is_problem():
    tables = {("public", "orders"): TableInfo("REGIONAL BY ROW", {})}
    report = evaluate(_state(tables=tables), [_rbr(region_column="region")])
    assert any("does not exist" in p for p in report.problems)


def test_rbr_table_wrong_locality_is_problem():
    tables = {("public", "orders"): TableInfo("REGIONAL BY TABLE IN PRIMARY REGION")}
    report = evaluate(_state(tables=tables), [_rbr()])
    assert not report.has_contradictions()
    assert not report.is_empty()


# --- evaluate: entity unannotated, table multi-region ----------------------


def test_unannotated_entity_on_global_table():
    tables = {("public", "things"): TableInfo("GLOBAL")}
    report = evaluate(_state(tables=tables), [_plain()])
    assert any("has no @GlobalTable" in p for p in report.problems)


def test_unannotated_entity_on_rbr_table():
    tables = {("public", "things"): TableInfo("REGIONAL BY ROW")}
    report = evaluate(_state(tables=tables), [_plain()])
    assert any("has no @RegionalByRow" in p for p in report.problems)


def test_unannotated_on_non_multiregion_is_clean():
    report = evaluate(_state(primary=None, regions=()), [_plain()])
    assert report.is_empty()


# --- evaluate: conflicting declarations ------------------------------------


def test_single_entity_both_kinds_is_contradiction():
    both = MultiregionTable(entity="app.X", table="x", kind=Kind.BOTH)
    report = evaluate(_state(tables={("public", "x"): TableInfo("GLOBAL")}), [both])
    assert report.has_contradictions()
    assert any("keep one" in p for p in report.problems)


def test_two_entities_same_table_conflict_is_contradiction():
    g = _global(entity="app.A", table="shared")
    r = _rbr(entity="app.B", table="shared")
    report = evaluate(_state(tables={("public", "shared"): TableInfo("GLOBAL")}), [g, r])
    assert report.has_contradictions()
    assert any("conflicting declarations" in p for p in report.problems)


# --- keyword quoting in output SQL -----------------------------------------


def test_keyword_table_name_is_quoted_in_sql():
    tables = {("public", "select"): TableInfo("REGIONAL BY ROW")}
    report = evaluate(
        _state(tables=tables, keywords=("select",)),
        [_global(entity="app.Select", table="select")],
    )
    assert 'ALTER TABLE public."select" SET LOCALITY GLOBAL;' in report.statements


# --- load_state against a routed fake query --------------------------------


def test_load_state_reads_show_and_information_schema():
    def query(sql: str, params=()):
        if "information_schema.columns" in sql:
            assert params == ("public", "orders")
            return [("crdb_region", "crdb_internal_region")]
        if "current_database(), current_schema()" in sql:
            return [("defaultdb", "public")]
        if "SHOW DATABASES" in sql:
            return [("us-east1",)]
        if "SHOW REGIONS FROM CLUSTER" in sql:
            return [("us-east1",), ("us-west1",)]
        if "pg_get_keywords" in sql:
            return [("select",), ("table",)]
        if "SHOW TABLES" in sql:
            return [("public", "orders", "REGIONAL BY ROW"), ("public", "ignored", "GLOBAL")]
        raise AssertionError(f"unexpected SQL: {sql}")

    state = mr.load_state(query, [_rbr(table="orders")])
    assert state.database == "defaultdb"
    assert state.primary_region == "us-east1"
    assert state.cluster_regions == ["us-east1", "us-west1"]
    assert state.keywords == {"select", "table"}
    assert ("public", "orders") in state.tables
    assert state.tables[("public", "orders")].column_types == {
        "crdb_region": "crdb_internal_region"
    }
    # A table that isn't one of ours is not loaded.
    assert ("public", "ignored") not in state.tables


def test_evaluate_schema_skips_when_mode_none():
    outcome, report = mr.evaluate_schema(lambda sql, params=(): [], [_global()], "none")
    assert outcome == "skip"
    assert report is None


def test_evaluate_schema_skips_when_not_cockroachdb():
    def query(sql: str, params=()):
        return [("PostgreSQL 16.0",)] if "version()" in sql else []

    outcome, _ = mr.evaluate_schema(query, [_global()], "warn")
    assert outcome == "skip"
