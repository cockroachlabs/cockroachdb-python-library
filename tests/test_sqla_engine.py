"""Tests for cockroachdb.sqla.engine — CockroachDB engine factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestCreateCockroachDBEngine:
    """Tests for create_cockroachdb_engine()."""

    @patch("cockroachdb.sqla.engine.setup_cockroachdb_events")
    @patch("cockroachdb.sqla.engine.create_engine")
    def test_creates_engine_with_defaults(self, mock_create_engine, mock_setup_events):
        """Engine is created with CockroachDB defaults: pool_size, pool_pre_ping, pool_recycle."""
        from cockroachdb.sqla.engine import create_cockroachdb_engine

        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        result = create_cockroachdb_engine("cockroachdb://user:pass@host:26257/db")

        mock_create_engine.assert_called_once()
        call_kwargs = mock_create_engine.call_args
        assert call_kwargs[1]["pool_size"] == 10
        assert call_kwargs[1]["pool_pre_ping"] is True
        assert call_kwargs[1]["pool_recycle"] == 1800
        assert result is mock_engine

    @patch("cockroachdb.sqla.engine.setup_cockroachdb_events")
    @patch("cockroachdb.sqla.engine.create_engine")
    def test_user_kwargs_override_defaults(self, mock_create_engine, mock_setup_events):
        """User-supplied kwargs override the CockroachDB defaults."""
        from cockroachdb.sqla.engine import create_cockroachdb_engine

        mock_create_engine.return_value = MagicMock()

        create_cockroachdb_engine(
            "cockroachdb://user:pass@host:26257/db",
            pool_size=20,
            pool_pre_ping=False,
        )

        call_kwargs = mock_create_engine.call_args[1]
        assert call_kwargs["pool_size"] == 20
        assert call_kwargs["pool_pre_ping"] is False
        # pool_recycle should still be default
        assert call_kwargs["pool_recycle"] == 1800

    @patch("cockroachdb.sqla.engine.setup_cockroachdb_events")
    @patch("cockroachdb.sqla.engine.create_engine")
    def test_registers_event_listeners(self, mock_create_engine, mock_setup_events):
        """setup_cockroachdb_events is called with the engine and config."""
        from cockroachdb.sqla.engine import create_cockroachdb_engine

        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        create_cockroachdb_engine("cockroachdb://user:pass@host:26257/db")

        mock_setup_events.assert_called_once()
        args = mock_setup_events.call_args[0]
        assert args[0] is mock_engine

    @patch("cockroachdb.sqla.engine.setup_cockroachdb_events")
    @patch("cockroachdb.sqla.engine.create_engine")
    def test_custom_config_forwarded(self, mock_create_engine, mock_setup_events):
        """A custom CockroachDBConfig is forwarded to setup_cockroachdb_events."""
        from cockroachdb.config import CockroachDBConfig
        from cockroachdb.sqla.engine import create_cockroachdb_engine

        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        custom_config = CockroachDBConfig()

        create_cockroachdb_engine(
            "cockroachdb://user:pass@host:26257/db",
            config=custom_config,
        )

        args = mock_setup_events.call_args[0]
        assert args[1] is custom_config

    @patch("cockroachdb.sqla.engine.setup_cockroachdb_events")
    @patch("cockroachdb.sqla.engine.create_engine")
    def test_url_passed_to_create_engine(self, mock_create_engine, mock_setup_events):
        """The connection URL is passed as the first positional arg to create_engine."""
        from cockroachdb.sqla.engine import create_cockroachdb_engine

        mock_create_engine.return_value = MagicMock()
        url = "cockroachdb://root@localhost:26257/defaultdb"

        create_cockroachdb_engine(url)

        assert mock_create_engine.call_args[0][0] == url
