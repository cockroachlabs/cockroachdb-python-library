"""Tests for cockroachdb.core.follower_read.FollowerReadContext."""

from __future__ import annotations

from cockroachdb.core.follower_read import FollowerReadContext


class TestFollowerReadContextIsActive:
    """Tests for FollowerReadContext.is_active()."""

    def test_inactive_by_default(self) -> None:
        # Outside any scoped block, should be inactive
        assert FollowerReadContext.is_active() is False

    def test_active_inside_scoped(self) -> None:
        with FollowerReadContext.scoped():
            assert FollowerReadContext.is_active() is True

    def test_inactive_after_scoped(self) -> None:
        with FollowerReadContext.scoped():
            pass
        assert FollowerReadContext.is_active() is False


class TestFollowerReadContextStaleness:
    """Tests for FollowerReadContext.current_staleness()."""

    def test_default_staleness(self) -> None:
        with FollowerReadContext.scoped() as staleness:
            assert staleness == "follower_read_timestamp()"
            assert FollowerReadContext.current_staleness() == "follower_read_timestamp()"

    def test_custom_staleness(self) -> None:
        with FollowerReadContext.scoped("-10s") as staleness:
            assert staleness == "-10s"
            assert FollowerReadContext.current_staleness() == "-10s"

    def test_no_staleness_outside_scope(self) -> None:
        assert FollowerReadContext.current_staleness() is None


class TestFollowerReadContextNesting:
    """Tests for nested FollowerReadContext scopes."""

    def test_nested_scopes_restore(self) -> None:
        with FollowerReadContext.scoped("-5s"):
            assert FollowerReadContext.current_staleness() == "-5s"
            with FollowerReadContext.scoped("-10s"):
                assert FollowerReadContext.current_staleness() == "-10s"
            assert FollowerReadContext.current_staleness() == "-5s"

    def test_scoped_yields_staleness_string(self) -> None:
        with FollowerReadContext.scoped("-1s") as s:
            assert isinstance(s, str)
            assert s == "-1s"

    def test_multiple_sequential_scopes(self) -> None:
        with FollowerReadContext.scoped("-5s"):
            assert FollowerReadContext.is_active() is True
        assert FollowerReadContext.is_active() is False

        with FollowerReadContext.scoped("-10s"):
            assert FollowerReadContext.is_active() is True
        assert FollowerReadContext.is_active() is False
