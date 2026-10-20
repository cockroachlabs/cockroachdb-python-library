"""Multi-region and follower read example.

Demonstrates CockroachDB's multi-region primitives:
    - ``RegionContext.scoped()`` context manager for setting the active region
    - ``FollowerReadContext.scoped()`` for bounded-staleness reads
    - ``@crdb_region`` decorator to pin functions to a region
    - ``@follower_read`` decorator for replica reads
    - Region validation with ``RegionContext.validate()``

Prerequisites:
    pip install cockroachdb cockroachdb-core

Usage:
    python examples/regions_and_follower_reads.py
"""

from __future__ import annotations

from cockroachdb import RegionValidationError, crdb_region, follower_read
from cockroachdb.core import FollowerReadContext, RegionContext

# ---------------------------------------------------------------------------
# 1. RegionContext.scoped() — set region for a block of code
# ---------------------------------------------------------------------------


def demonstrate_region_context() -> None:
    """Use RegionContext.scoped() to pin operations to a region.

    The context manager sets a contextvar that downstream code (the
    template layer, SQLAlchemy event listeners, etc.) reads to inject
    ``SET crdb_region`` into SQL connections.
    """
    print("--- RegionContext.scoped() ---")

    # No region set initially
    print(f"  Current region (before): {RegionContext.current()}")

    with RegionContext.scoped("us-east1") as region:
        print(f"  Inside scope: region = {region}")
        print(f"  RegionContext.current() = {RegionContext.current()}")

        # Nested scopes override the outer region
        with RegionContext.scoped("eu-west1") as inner:
            print(f"  Nested scope: region = {inner}")

        # After nested scope exits, outer region is restored
        print(f"  Back to outer scope: {RegionContext.current()}")

    # After all scopes exit, region is cleared
    print(f"  Current region (after): {RegionContext.current()}")
    print()


# ---------------------------------------------------------------------------
# 2. FollowerReadContext.scoped() — bounded-staleness reads
# ---------------------------------------------------------------------------


def demonstrate_follower_read_context() -> None:
    """Use FollowerReadContext.scoped() for low-latency stale reads.

    CockroachDB's follower reads allow any replica to serve reads that
    are slightly stale, dramatically reducing read latency in
    multi-region deployments.
    """
    print("--- FollowerReadContext.scoped() ---")

    print(f"  Follower read active (before): {FollowerReadContext.is_active()}")

    # Default: follower_read_timestamp() — CockroachDB picks the optimal staleness
    with FollowerReadContext.scoped() as staleness:
        print(f"  Active: {FollowerReadContext.is_active()}")
        print(f"  Staleness expression: {staleness}")
        print(f"  current_staleness(): {FollowerReadContext.current_staleness()}")

    # Custom staleness: 5-second bounded staleness
    with FollowerReadContext.scoped("-5s") as staleness:
        print(f"  Custom staleness: {staleness}")

    # Fixed point-in-time read
    with FollowerReadContext.scoped("'2024-01-15 10:00:00'") as staleness:
        print(f"  Point-in-time: {staleness}")

    print(f"  Follower read active (after): {FollowerReadContext.is_active()}")
    print()


# ---------------------------------------------------------------------------
# 3. @crdb_region decorator — pin a function to a specific region
# ---------------------------------------------------------------------------


@crdb_region("us-east1")
def get_east_coast_orders() -> str:
    """This function always executes in the us-east1 region.

    The decorator attaches ``__crdb_region__`` metadata that the
    framework layer reads to set the region context before execution.
    """
    return f"Fetching orders from region: us-east1 (metadata: {get_east_coast_orders.__crdb_region__})"


@crdb_region("eu-west1")
def get_european_orders() -> str:
    """Pinned to the eu-west1 region."""
    return (
        f"Fetching orders from region: eu-west1 (metadata: {get_european_orders.__crdb_region__})"
    )


def demonstrate_region_decorator() -> None:
    """Show the @crdb_region decorator metadata."""
    print("--- @crdb_region decorator ---")
    print(f"  {get_east_coast_orders()}")
    print(f"  {get_european_orders()}")
    print()


# ---------------------------------------------------------------------------
# 4. @follower_read decorator — mark functions as stale-read-safe
# ---------------------------------------------------------------------------


@follower_read()
def get_product_catalog() -> str:
    """Product catalog reads can tolerate slight staleness.

    The decorator attaches ``__crdb_follower_read__`` metadata with the
    staleness expression. The framework layer uses this to prepend
    ``AS OF SYSTEM TIME follower_read_timestamp()`` to queries.
    """
    return f"Catalog query (staleness: {get_product_catalog.__crdb_follower_read__})"


@follower_read(staleness="-10s")
def get_analytics_dashboard() -> str:
    """Analytics dashboards can tolerate 10 seconds of staleness."""
    return f"Analytics query (staleness: {get_analytics_dashboard.__crdb_follower_read__})"


def demonstrate_follower_read_decorator() -> None:
    """Show the @follower_read decorator metadata."""
    print("--- @follower_read decorator ---")
    print(f"  {get_product_catalog()}")
    print(f"  {get_analytics_dashboard()}")
    print()


# ---------------------------------------------------------------------------
# 5. Region validation
# ---------------------------------------------------------------------------


def demonstrate_region_validation() -> None:
    """Validate region names against format rules and an allowlist.

    CockroachDB region names must match ``^[a-z][a-z0-9-]{1,62}$``.
    You can also restrict to an explicit set of allowed regions.
    """
    print("--- Region validation ---")

    allowed_regions = ["us-east1", "us-west2", "eu-west1"]

    # Valid region
    try:
        RegionContext.validate("us-east1", allowed=allowed_regions)
        print("  'us-east1' is valid")
    except RegionValidationError:
        print("  'us-east1' is invalid")

    # Invalid format (uppercase)
    try:
        RegionContext.validate("US-EAST1")
        print("  'US-EAST1' is valid")
    except RegionValidationError as e:
        print(f"  'US-EAST1' rejected: {e}")

    # Valid format but not in allowlist
    try:
        RegionContext.validate("ap-southeast1", allowed=allowed_regions)
        print("  'ap-southeast1' is valid")
    except RegionValidationError as e:
        print(f"  'ap-southeast1' rejected: {e}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== CockroachDB Multi-Region & Follower Read Examples ===\n")

    demonstrate_region_context()
    demonstrate_follower_read_context()
    demonstrate_region_decorator()
    demonstrate_follower_read_decorator()
    demonstrate_region_validation()

    print("Done.")
