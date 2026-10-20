"""Tests for cockroachdb.cdc.manager — changefeed lifecycle management."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cockroachdb.cdc.manager import ChangefeedManager, _strip_scheme
from cockroachdb.cdc.models import ChangefeedConfig


class TestChangefeedManagerCreate:
    """Tests for ChangefeedManager.create()."""

    def test_builds_correct_sql(self):
        """CREATE CHANGEFEED SQL includes table, webhook URL, and default options."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (12345,)
        mock_conn.execute.return_value = mock_cursor

        mgr = ChangefeedManager(mock_conn)
        job_id = mgr.create("orders", "https://example.com/webhooks/orders")

        assert job_id == 12345
        sql = mock_conn.execute.call_args[0][0]
        assert "CREATE CHANGEFEED FOR orders" in sql
        assert "webhook-https://" in sql
        assert "example.com/webhooks/orders" in sql

    def test_applies_custom_config(self):
        """Custom ChangefeedConfig options appear in the SQL."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (99,)
        mock_conn.execute.return_value = mock_cursor

        cfg = ChangefeedConfig(format="avro", diff=False, updated=False)
        mgr = ChangefeedManager(mock_conn)
        mgr.create("items", "https://example.com/items", config=cfg)

        sql = mock_conn.execute.call_args[0][0]
        assert "format = 'avro'" in sql

    def test_applies_extra_options(self):
        """Extra raw WITH options are appended to the SQL."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.execute.return_value = mock_cursor

        mgr = ChangefeedManager(mock_conn)
        mgr.create("t", "https://x.com/hook", options={"key_in_value": "true"})

        sql = mock_conn.execute.call_args[0][0]
        assert "key_in_value = 'true'" in sql

    def test_raises_runtime_error_on_failure(self):
        """RuntimeError is raised when execute fails."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("connection lost")

        mgr = ChangefeedManager(mock_conn)
        with pytest.raises(RuntimeError, match="Failed to create changefeed"):
            mgr.create("t", "https://x.com/hook")

    def test_raises_runtime_error_when_no_job_id(self):
        """RuntimeError is raised when fetchone returns None."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.execute.return_value = mock_cursor

        mgr = ChangefeedManager(mock_conn)
        with pytest.raises(RuntimeError, match="returned no job ID"):
            mgr.create("t", "https://x.com/hook")


class TestChangefeedManagerCancel:
    """Tests for ChangefeedManager.cancel()."""

    def test_executes_cancel_job(self):
        mock_conn = MagicMock()
        mgr = ChangefeedManager(mock_conn)
        mgr.cancel(12345)

        sql = mock_conn.execute.call_args[0][0]
        assert sql == "CANCEL JOB 12345"

    def test_raises_runtime_error_on_failure(self):
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("fail")

        mgr = ChangefeedManager(mock_conn)
        with pytest.raises(RuntimeError, match="Failed to cancel"):
            mgr.cancel(99)

    def test_cancel_different_job_ids(self):
        mock_conn = MagicMock()
        mgr = ChangefeedManager(mock_conn)

        mgr.cancel(111)
        assert "111" in mock_conn.execute.call_args[0][0]

        mgr.cancel(222)
        assert "222" in mock_conn.execute.call_args[0][0]


class TestChangefeedManagerPause:
    """Tests for ChangefeedManager.pause()."""

    def test_executes_pause_job(self):
        mock_conn = MagicMock()
        mgr = ChangefeedManager(mock_conn)
        mgr.pause(555)

        sql = mock_conn.execute.call_args[0][0]
        assert sql == "PAUSE JOB 555"

    def test_raises_runtime_error_on_failure(self):
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("fail")

        mgr = ChangefeedManager(mock_conn)
        with pytest.raises(RuntimeError, match="Failed to pause"):
            mgr.pause(555)

    def test_pause_returns_none(self):
        mock_conn = MagicMock()
        mgr = ChangefeedManager(mock_conn)
        result = mgr.pause(555)
        assert result is None


class TestChangefeedManagerResume:
    """Tests for ChangefeedManager.resume()."""

    def test_executes_resume_job(self):
        mock_conn = MagicMock()
        mgr = ChangefeedManager(mock_conn)
        mgr.resume(777)

        sql = mock_conn.execute.call_args[0][0]
        assert sql == "RESUME JOB 777"

    def test_raises_runtime_error_on_failure(self):
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("fail")

        mgr = ChangefeedManager(mock_conn)
        with pytest.raises(RuntimeError, match="Failed to resume"):
            mgr.resume(777)

    def test_resume_returns_none(self):
        mock_conn = MagicMock()
        mgr = ChangefeedManager(mock_conn)
        result = mgr.resume(777)
        assert result is None


class TestStripScheme:
    """Tests for _strip_scheme helper."""

    def test_strips_https(self):
        assert _strip_scheme("https://example.com/path") == "example.com/path"

    def test_strips_http(self):
        assert _strip_scheme("http://example.com/path") == "example.com/path"

    def test_no_scheme_unchanged(self):
        assert _strip_scheme("example.com/path") == "example.com/path"
