"""Tests for cockroachdb.sqla.events — SQLAlchemy event listeners."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cockroachdb.config import CockroachDBConfig


class TestSetupCockroachDBEvents:
    """Tests for setup_cockroachdb_events registration."""

    @patch("cockroachdb.sqla.events.event")
    def test_registers_listeners(self, mock_event):
        """setup_cockroachdb_events registers connect and before_cursor_execute listeners."""
        from cockroachdb.sqla.events import setup_cockroachdb_events

        mock_engine = MagicMock()
        setup_cockroachdb_events(mock_engine)

        # Should have called event.listens_for at least for "connect" and "before_cursor_execute"
        listener_calls = mock_event.listens_for.call_args_list
        events_registered = [c[0][1] for c in listener_calls]
        assert "connect" in events_registered
        assert "before_cursor_execute" in events_registered

    @patch("cockroachdb.sqla.events.event")
    def test_accepts_custom_config(self, mock_event):
        """No error when a custom CockroachDBConfig is provided."""
        from cockroachdb.sqla.events import setup_cockroachdb_events

        mock_engine = MagicMock()
        config = CockroachDBConfig()
        # Should not raise
        setup_cockroachdb_events(mock_engine, config)

    @patch("cockroachdb.sqla.events.event")
    def test_default_config_used_when_none(self, mock_event):
        """When config is None, defaults are used without error."""
        from cockroachdb.sqla.events import setup_cockroachdb_events

        mock_engine = MagicMock()
        setup_cockroachdb_events(mock_engine, None)
        # No exception means defaults were applied


class TestBeforeCursorExecute:
    """Tests for the _before_cursor_execute listener behavior.

    We test the listener logic by calling the inner function directly.
    Since setup_cockroachdb_events registers closures, we capture them.
    """

    def _capture_listener(self, config=None):
        """Set up events and capture the before_cursor_execute listener."""
        from cockroachdb.sqla.events import setup_cockroachdb_events

        mock_engine = MagicMock()
        listeners = {}

        def fake_listens_for(engine, event_name):
            def decorator(fn):
                listeners[event_name] = fn
                return fn

            return decorator

        with patch("cockroachdb.sqla.events.event") as mock_event:
            mock_event.listens_for = fake_listens_for
            setup_cockroachdb_events(mock_engine, config)

        return listeners

    @patch("cockroachdb.sqla.events.RegionContext")
    @patch("cockroachdb.sqla.events.FollowerReadContext")
    def test_injects_region_set_when_active(self, mock_frc, mock_rc):
        """When RegionContext is active, SET crdb_region is executed on the cursor."""
        mock_rc.current.return_value = "us-east1"
        mock_frc.is_active.return_value = False

        listeners = self._capture_listener()
        cursor = MagicMock()

        listeners["before_cursor_execute"](MagicMock(), cursor, "SELECT 1", None, None, False)

        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        assert "SET crdb_region" in sql
        assert "us-east1" in sql

    @patch("cockroachdb.sqla.events.RegionContext")
    @patch("cockroachdb.sqla.events.FollowerReadContext")
    def test_injects_follower_read_when_active(self, mock_frc, mock_rc):
        """When FollowerReadContext is active and enabled, AS OF SYSTEM TIME is injected."""
        mock_rc.current.return_value = None
        mock_frc.is_active.return_value = True
        mock_frc.current_staleness.return_value = "follower_read_timestamp()"

        config = CockroachDBConfig()
        config.follower_read.enabled = True

        listeners = self._capture_listener(config)
        cursor = MagicMock()

        listeners["before_cursor_execute"](MagicMock(), cursor, "SELECT 1", None, None, False)

        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        assert "AS OF SYSTEM TIME" in sql

    @patch("cockroachdb.sqla.events.RegionContext")
    @patch("cockroachdb.sqla.events.FollowerReadContext")
    def test_does_nothing_when_no_context_active(self, mock_frc, mock_rc):
        """When neither context is active, cursor.execute is never called."""
        mock_rc.current.return_value = None
        mock_frc.is_active.return_value = False

        listeners = self._capture_listener()
        cursor = MagicMock()

        listeners["before_cursor_execute"](MagicMock(), cursor, "SELECT 1", None, None, False)

        cursor.execute.assert_not_called()

    @patch("cockroachdb.sqla.events.RegionContext")
    @patch("cockroachdb.sqla.events.FollowerReadContext")
    def test_both_contexts_active(self, mock_frc, mock_rc):
        """When both region and follower read are active, both SETs are executed."""
        mock_rc.current.return_value = "eu-west1"
        mock_frc.is_active.return_value = True
        mock_frc.current_staleness.return_value = "follower_read_timestamp()"

        config = CockroachDBConfig()
        config.follower_read.enabled = True

        listeners = self._capture_listener(config)
        cursor = MagicMock()

        listeners["before_cursor_execute"](MagicMock(), cursor, "SELECT 1", None, None, False)

        assert cursor.execute.call_count == 2
        calls = [c[0][0] for c in cursor.execute.call_args_list]
        assert any("crdb_region" in c for c in calls)
        assert any("AS OF SYSTEM TIME" in c for c in calls)

    @patch("cockroachdb.sqla.events.RegionContext")
    @patch("cockroachdb.sqla.events.FollowerReadContext")
    def test_follower_read_disabled_in_config(self, mock_frc, mock_rc):
        """When follower_read.enabled is False, no follower-read SET is injected."""
        mock_rc.current.return_value = None
        mock_frc.is_active.return_value = True
        mock_frc.current_staleness.return_value = "follower_read_timestamp()"

        config = CockroachDBConfig()
        config.follower_read.enabled = False

        listeners = self._capture_listener(config)
        cursor = MagicMock()

        listeners["before_cursor_execute"](MagicMock(), cursor, "SELECT 1", None, None, False)

        cursor.execute.assert_not_called()
