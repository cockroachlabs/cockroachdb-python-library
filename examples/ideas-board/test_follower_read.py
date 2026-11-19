"""Fast unit test for follower reads — no Docker, no database.

Covers the genuinely unit-testable logic: staleness composition via
``build_staleness``, the ``@follower_read`` decorator's stamped expression, the
fail-fast on a negative part, and the ``FollowerReadContext`` scope. The real
follower-snapshot read needs a cluster (see ``test_follower_read_it.py``).
"""

from __future__ import annotations

import follower_read_service as frs
import pytest

from cockroachdb import build_staleness, follower_read
from cockroachdb.core import FollowerReadContext


# tag::follower-read-unit-test[]
def test_build_staleness_defaults_and_additive() -> None:
    assert build_staleness() == "follower_read_timestamp()"
    assert build_staleness(seconds_ago=5) == "'-5s'"
    assert build_staleness(minutes_ago=1, seconds_ago=30) == "'-90s'"


def test_follower_read_decorator_stamps_resolved_staleness() -> None:
    assert frs.top_ideas.__crdb_follower_read__ == "follower_read_timestamp()"

    @follower_read(seconds_ago=10)
    def reader() -> None: ...

    assert reader.__crdb_follower_read__ == "'-10s'"


def test_negative_staleness_fails_fast() -> None:
    with pytest.raises(ValueError):
        build_staleness(seconds_ago=-1)


def test_scoped_context_activates_and_resets() -> None:
    assert FollowerReadContext.current_staleness() is None
    with FollowerReadContext.scoped(seconds_ago=5) as staleness:
        assert staleness == "'-5s'"
        assert FollowerReadContext.is_active()
    assert FollowerReadContext.current_staleness() is None


# end::follower-read-unit-test[]
