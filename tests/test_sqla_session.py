"""Tests for cockroachdb.sqla.session — retry, follower read, region scoping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cockroachdb.config import CockroachDBConfig
from cockroachdb.exceptions import CockroachDBRetryExhausted
from cockroachdb.sqla.session import (
    CockroachDBSession,
    RegionalSession,
    _calc_delay,
    _is_serialization_error,
)


class TestIsSerializationError:
    """Tests for the _is_serialization_error helper."""

    def test_true_when_pgcode_40001(self):
        exc = Exception("conflict")
        exc.pgcode = "40001"
        assert _is_serialization_error(exc) is True

    def test_true_when_orig_has_pgcode(self):
        orig = Exception("inner")
        orig.pgcode = "40001"
        exc = Exception("outer")
        exc.orig = orig
        assert _is_serialization_error(exc) is True

    def test_false_for_other_pgcodes(self):
        exc = Exception("other")
        exc.pgcode = "23505"
        assert _is_serialization_error(exc) is False

    def test_false_when_no_pgcode(self):
        exc = Exception("generic")
        assert _is_serialization_error(exc) is False


class TestCalcDelay:
    """Tests for the _calc_delay backoff helper."""

    def test_first_attempt_near_base(self):
        delay = _calc_delay(0, base=0.1, cap=5.0, mult=2.0, jitter=0.0)
        assert delay == pytest.approx(0.1, abs=0.01)

    def test_capped_at_max(self):
        delay = _calc_delay(100, base=0.1, cap=5.0, mult=2.0, jitter=0.0)
        assert delay == pytest.approx(5.0, abs=0.01)

    def test_jitter_adds_randomness(self):
        delays = {_calc_delay(0, base=1.0, cap=10.0, mult=2.0, jitter=0.5) for _ in range(50)}
        # With jitter, we expect some variance
        assert len(delays) > 1


class TestCockroachDBSessionExecuteWithRetry:
    """Tests for execute_with_retry."""

    def _make_session(self, max_retries=3):
        engine = MagicMock()
        config = CockroachDBConfig()
        config.retry.max_retries = max_retries
        config.retry.base_delay = 0.001  # fast for tests
        config.retry.max_delay = 0.01
        return CockroachDBSession(engine, config)

    def test_succeeds_on_first_attempt(self):
        crdb = self._make_session()
        mock_session = MagicMock()
        crdb._session_factory = MagicMock(return_value=mock_session)

        result = crdb.execute_with_retry(lambda s: "ok")
        assert result == "ok"
        mock_session.commit.assert_called_once()

    @patch("cockroachdb.sqla.session.time.sleep")
    def test_retries_on_serialization_error(self, mock_sleep):
        crdb = self._make_session(max_retries=2)

        call_count = 0

        def fn(session):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                exc = Exception("conflict")
                exc.pgcode = "40001"
                raise exc
            return "success"

        mock_session = MagicMock()
        crdb._session_factory = MagicMock(return_value=mock_session)

        result = crdb.execute_with_retry(fn)
        assert result == "success"
        assert call_count == 3

    @patch("cockroachdb.sqla.session.time.sleep")
    def test_raises_retry_exhausted(self, mock_sleep):
        crdb = self._make_session(max_retries=1)

        def fn(session):
            exc = Exception("conflict")
            exc.pgcode = "40001"
            raise exc

        mock_session = MagicMock()
        crdb._session_factory = MagicMock(return_value=mock_session)

        with pytest.raises(CockroachDBRetryExhausted):
            crdb.execute_with_retry(fn)

    def test_raises_non_serialization_errors_immediately(self):
        crdb = self._make_session()

        def fn(session):
            raise ValueError("bad data")

        mock_session = MagicMock()
        crdb._session_factory = MagicMock(return_value=mock_session)

        with pytest.raises(ValueError, match="bad data"):
            crdb.execute_with_retry(fn)


class TestFollowerRead:
    """Tests for CockroachDBSession.follower_read."""

    @patch("cockroachdb.sqla.session.FollowerReadContext")
    def test_sets_and_resets_context(self, mock_frc):
        engine = MagicMock()
        crdb = CockroachDBSession(engine)
        mock_session = MagicMock()
        crdb._session_factory = MagicMock(return_value=mock_session)
        mock_token = MagicMock()
        mock_frc.set.return_value = mock_token

        crdb.follower_read(lambda s: "result")

        mock_frc.set.assert_called_once_with(True)
        mock_frc.reset.assert_called_once_with(mock_token)

    @patch("cockroachdb.sqla.session.FollowerReadContext")
    def test_returns_fn_result(self, mock_frc):
        engine = MagicMock()
        crdb = CockroachDBSession(engine)
        mock_session = MagicMock()
        crdb._session_factory = MagicMock(return_value=mock_session)
        mock_frc.set.return_value = MagicMock()

        result = crdb.follower_read(lambda s: 42)
        assert result == 42

    @patch("cockroachdb.sqla.session.FollowerReadContext")
    def test_closes_session_on_exception(self, mock_frc):
        engine = MagicMock()
        crdb = CockroachDBSession(engine)
        mock_session = MagicMock()
        crdb._session_factory = MagicMock(return_value=mock_session)
        mock_frc.set.return_value = MagicMock()

        with pytest.raises(RuntimeError):
            crdb.follower_read(lambda s: (_ for _ in ()).throw(RuntimeError("boom")))

        mock_session.close.assert_called_once()


class TestInRegion:
    """Tests for CockroachDBSession.in_region and RegionalSession."""

    def test_returns_regional_session(self):
        engine = MagicMock()
        crdb = CockroachDBSession(engine)
        regional = crdb.in_region("us-east1")
        assert isinstance(regional, RegionalSession)

    @patch("cockroachdb.sqla.session.RegionContext")
    def test_regional_session_sets_and_resets_context(self, mock_rc):
        engine = MagicMock()
        crdb = CockroachDBSession(engine)
        mock_session = MagicMock()
        crdb._session_factory = MagicMock(return_value=mock_session)
        mock_token = MagicMock()
        mock_rc.set.return_value = mock_token

        regional = crdb.in_region("us-east1")
        result = regional.execute(lambda s: "ok")

        mock_rc.set.assert_called_with("us-east1")
        mock_rc.reset.assert_called_with(mock_token)
        assert result == "ok"

    def test_regional_session_repr(self):
        engine = MagicMock()
        crdb = CockroachDBSession(engine)
        regional = crdb.in_region("eu-west1")
        assert "eu-west1" in repr(regional)
