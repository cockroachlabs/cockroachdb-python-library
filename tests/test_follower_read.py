"""Tests for cockroachdb.core.follower_read.FollowerReadContext."""

from __future__ import annotations

import pytest

from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.decorators import follower_read
from cockroachdb.staleness import build_staleness


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


class TestBuildStaleness:
    """Tests for the shared build_staleness helper (CONTRACT v2)."""

    def test_default_returns_follower_read_timestamp(self) -> None:
        # Nothing set -> current default.
        assert build_staleness() == "follower_read_timestamp()"

    def test_custom_staleness_passthrough(self) -> None:
        assert build_staleness("-5s") == "-5s"

    def test_additive_seconds(self) -> None:
        assert build_staleness(seconds_ago=30) == "'-30s'"

    def test_additive_composition_adds_up(self) -> None:
        # 1h + 2m + 3s = 3723s
        assert build_staleness(hours_ago=1, minutes_ago=2, seconds_ago=3) == "'-3723s'"

    def test_additive_wins_over_staleness(self) -> None:
        # Any positive part takes precedence over the staleness fallback.
        assert build_staleness("follower_read_timestamp()", minutes_ago=5) == "'-300s'"

    def test_zero_parts_fall_back_to_staleness(self) -> None:
        assert build_staleness("-5s", hours_ago=0, minutes_ago=0, seconds_ago=0) == "-5s"

    @pytest.mark.parametrize(
        ("kwargs", "bad"),
        [
            ({"hours_ago": -1}, "hours_ago"),
            ({"minutes_ago": -1}, "minutes_ago"),
            ({"seconds_ago": -1}, "seconds_ago"),
        ],
    )
    def test_negative_part_raises(self, kwargs: dict[str, int], bad: str) -> None:
        with pytest.raises(ValueError, match=bad):
            build_staleness(**kwargs)


class TestScopedAdditive:
    """Additive staleness on FollowerReadContext.scoped (CONTRACT v2)."""

    def test_additive_composition(self) -> None:
        with FollowerReadContext.scoped(minutes_ago=2, seconds_ago=30) as s:
            assert s == "'-150s'"
            assert FollowerReadContext.current_staleness() == "'-150s'"

    def test_default_unchanged(self) -> None:
        with FollowerReadContext.scoped() as s:
            assert s == "follower_read_timestamp()"

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="seconds_ago"):
            with FollowerReadContext.scoped(seconds_ago=-1):
                pass
        # Fail fast: context must not have been activated.
        assert FollowerReadContext.is_active() is False


class TestFollowerReadDecoratorAdditive:
    """Additive staleness on the @follower_read decorator (CONTRACT v2)."""

    def test_default(self) -> None:
        @follower_read()
        def query() -> None:
            pass

        assert query.__crdb_follower_read__ == "follower_read_timestamp()"

    def test_additive_composition(self) -> None:
        @follower_read(hours_ago=1, seconds_ago=5)
        def query() -> None:
            pass

        assert query.__crdb_follower_read__ == "'-3605s'"

    def test_negative_raises_at_decoration(self) -> None:
        with pytest.raises(ValueError, match="minutes_ago"):

            @follower_read(minutes_ago=-5)
            def query() -> None:
                pass
