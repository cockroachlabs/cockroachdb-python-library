"""Tests for cockroachdb.django.checks — the multi-region system check."""

from __future__ import annotations

import types

from cockroachdb.core.multiregion import Kind, MultiregionReport
from cockroachdb.django.checks import (
    _messages_for,
    _tables_from_models,
    check_multiregion_schema,
)


def _fake_model(label, db_table, locality, fields):
    meta = types.SimpleNamespace(
        label=label,
        db_table=db_table,
        get_fields=lambda: [types.SimpleNamespace(name=f) for f in fields],
    )
    model = types.SimpleNamespace(_meta=meta)
    if locality is not None:
        model.crdb_locality = locality
    return model


class TestEnumeration:
    def test_reads_locality_and_region_column(self):
        models = [
            _fake_model("app.Order", "orders", "REGIONAL BY ROW", ["id", "crdb_region"]),
            _fake_model("app.Product", "products", "GLOBAL", ["id"]),
            _fake_model("app.Plain", "plain", None, ["id"]),
        ]
        by_table = {t.table: t for t in _tables_from_models(models)}
        assert by_table["orders"].kind is Kind.REGIONAL_BY_ROW
        assert by_table["orders"].region_column == "crdb_region"
        assert by_table["orders"].entity == "app.Order"
        assert by_table["products"].kind is Kind.GLOBAL
        assert by_table["plain"].kind is Kind.NONE


class TestMessageMapping:
    def test_contradiction_is_error(self):
        from django.core.checks import Error

        report = MultiregionReport()
        report.contradiction("the schema and model disagree")
        messages = _messages_for("fail", report, "warn")
        assert len(messages) == 1
        assert isinstance(messages[0], Error)
        assert messages[0].id == "cockroachdb.E001"

    def test_plain_problem_is_warning(self):
        from django.core.checks import Warning as CheckWarning

        report = MultiregionReport()
        report.problem("add the mixin")
        messages = _messages_for("warn", report, "warn")
        assert len(messages) == 1
        assert isinstance(messages[0], CheckWarning)
        assert messages[0].id == "cockroachdb.W001"

    def test_ok_outcome_has_no_messages(self):
        assert _messages_for("ok", MultiregionReport(), "warn") == []

    def test_skip_outcome_has_no_messages(self):
        assert _messages_for("skip", None, "warn") == []


class TestRegisteredCheck:
    def test_none_mode_returns_no_messages(self):
        from django.test import override_settings

        with override_settings(COCKROACHDB_MULTIREGION_MODE="none"):
            assert check_multiregion_schema() == []

    def test_non_cockroachdb_database_is_skipped(self):
        # The test database is sqlite (see conftest_django), so SELECT version()
        # fails and the check skips quietly rather than raising.
        assert check_multiregion_schema() == []
