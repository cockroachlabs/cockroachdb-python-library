"""Shared helper for building ``AS OF SYSTEM TIME`` staleness expressions.

Lives in the base ``cockroachdb`` package (not ``cockroachdb-core``) because
both the ``@follower_read`` decorator here and ``FollowerReadContext.scoped``
in core must reuse it, and core depends on base — not the other way around.
"""

from __future__ import annotations


def build_staleness(
    staleness: str = "follower_read_timestamp()",
    *,
    hours_ago: int = 0,
    minutes_ago: int = 0,
    seconds_ago: int = 0,
) -> str:
    """Build an ``AS OF SYSTEM TIME`` expression.

    Additive staleness: ``hours_ago``/``minutes_ago``/``seconds_ago`` add up
    and, when their total is positive, compose to ``'-Ns'`` which takes
    precedence over *staleness*. When no parts are set, *staleness* is returned
    unchanged (default ``follower_read_timestamp()``).

    This is the single source of truth for the fail-fast rule: a negative part
    raises immediately rather than silently falling back to a current read.

    Args:
        staleness: Fallback AS OF SYSTEM TIME expression used when no
            additive parts are set.
        hours_ago: Whole hours of staleness to add. Must be >= 0.
        minutes_ago: Whole minutes of staleness to add. Must be >= 0.
        seconds_ago: Whole seconds of staleness to add. Must be >= 0.

    Returns:
        Either ``'-Ns'`` (composed from the additive parts) or *staleness*.

    Raises:
        ValueError: if any additive part is negative.
    """
    for name, value in (
        ("hours_ago", hours_ago),
        ("minutes_ago", minutes_ago),
        ("seconds_ago", seconds_ago),
    ):
        if value < 0:
            raise ValueError(f"{name} must be >= 0, got {value}")

    total_seconds = hours_ago * 3600 + minutes_ago * 60 + seconds_ago
    if total_seconds > 0:
        return f"'-{total_seconds}s'"
    return staleness
