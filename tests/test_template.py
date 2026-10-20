"""Tests for cockroachdb.core.template (CockroachDBTemplate and AsyncCockroachDBTemplate)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cockroachdb.config import CockroachDBConfig
from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.core.metrics import InMemoryMetricsCollector
from cockroachdb.core.region import RegionContext
from cockroachdb.core.template import (
    CockroachDBTemplate,
    RegionalTemplate,
)


class TestCockroachDBTemplateInit:
    """Tests for CockroachDBTemplate initialization."""

    @patch("cockroachdb.core.template.psycopg")
    def test_creates_with_defaults(self, mock_psycopg: MagicMock) -> None:
        template = CockroachDBTemplate(conninfo="postgresql://localhost:26257/db")
        assert template._conninfo == "postgresql://localhost:26257/db"
        assert template._config is not None

    @patch("cockroachdb.core.template.psycopg")
    def test_creates_with_custom_config(self, mock_psycopg: MagicMock) -> None:
        config = CockroachDBConfig()
        metrics = InMemoryMetricsCollector()
        template = CockroachDBTemplate(
            conninfo="postgresql://localhost:26257/db",
            config=config,
            metrics=metrics,
        )
        assert template._metrics is metrics

    @patch("cockroachdb.core.template.psycopg")
    def test_retry_engine_uses_config(self, mock_psycopg: MagicMock) -> None:
        from cockroachdb.config import RetryConfig

        config = CockroachDBConfig(retry=RetryConfig(max_retries=7))
        template = CockroachDBTemplate(conninfo="dsn", config=config)
        assert template._retry_engine.policy.max_retries == 7


class TestCockroachDBTemplateExecute:
    """Tests for CockroachDBTemplate.execute() with mocked psycopg."""

    @patch("cockroachdb.core.template.psycopg")
    def test_execute_calls_fn_with_connection(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_psycopg.connect.return_value.__exit__ = MagicMock(return_value=False)

        template = CockroachDBTemplate(conninfo="postgresql://localhost/db")

        def fn(conn: object) -> str:
            return "result"

        result = template.execute(fn)
        assert result == "result"

    @patch("cockroachdb.core.template.psycopg")
    def test_execute_commits_transaction(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_psycopg.connect.return_value.__exit__ = MagicMock(return_value=False)

        template = CockroachDBTemplate(conninfo="dsn")
        template.execute(lambda conn: None)
        mock_conn.commit.assert_called_once()

    @patch("cockroachdb.core.template.psycopg")
    def test_execute_records_metrics(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_psycopg.connect.return_value.__exit__ = MagicMock(return_value=False)

        metrics = InMemoryMetricsCollector()
        template = CockroachDBTemplate(conninfo="dsn", metrics=metrics)
        template.execute(lambda conn: "ok")
        assert metrics.total_transactions == 1


class TestCockroachDBTemplateRegional:
    """Tests for CockroachDBTemplate.in_region()."""

    @patch("cockroachdb.core.template.psycopg")
    def test_in_region_returns_regional_template(self, mock_psycopg: MagicMock) -> None:
        template = CockroachDBTemplate(conninfo="dsn")
        regional = template.in_region("us-east1")
        assert isinstance(regional, RegionalTemplate)

    @patch("cockroachdb.core.template.psycopg")
    def test_regional_execute_sets_region(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_psycopg.connect.return_value.__exit__ = MagicMock(return_value=False)

        captured_region: str | None = None

        def fn(conn: object) -> str:
            nonlocal captured_region
            captured_region = RegionContext.current()
            return "ok"

        template = CockroachDBTemplate(conninfo="dsn")
        regional = template.in_region("us-east1")
        regional.execute(fn)
        assert captured_region == "us-east1"


class TestCockroachDBTemplateFollowerRead:
    """Tests for CockroachDBTemplate.follower_read() context manager."""

    @patch("cockroachdb.core.template.psycopg")
    def test_follower_read_activates_context(self, mock_psycopg: MagicMock) -> None:
        template = CockroachDBTemplate(conninfo="dsn")
        with template.follower_read():
            assert FollowerReadContext.is_active() is True
        assert FollowerReadContext.is_active() is False

    @patch("cockroachdb.core.template.psycopg")
    def test_follower_read_custom_staleness(self, mock_psycopg: MagicMock) -> None:
        template = CockroachDBTemplate(conninfo="dsn")
        with template.follower_read(staleness="-10s"):
            assert FollowerReadContext.current_staleness() == "-10s"

    @patch("cockroachdb.core.template.psycopg")
    def test_follower_read_yields_template(self, mock_psycopg: MagicMock) -> None:
        template = CockroachDBTemplate(conninfo="dsn")
        with template.follower_read() as t:
            assert t is template
