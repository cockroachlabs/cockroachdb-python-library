"""SQLAlchemy integration example.

Demonstrates the CockroachDB SQLAlchemy adapter:
    - ``create_cockroachdb_engine()`` with optimized defaults
    - ``CockroachDBSession`` with ``execute_with_retry``
    - ``RegionalByRowMixin`` for multi-region tables
    - ``GlobalTableMixin`` for globally replicated tables
    - ``follower_read()`` for low-latency stale reads
    - ``in_region()`` for region-pinned operations

Prerequisites:
    pip install cockroachdb-sqlalchemy sqlalchemy psycopg2-binary

    CockroachDB running at localhost:26257 with database ``defaultdb``.

Usage:
    python examples/sqlalchemy_integration.py
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, Numeric, String, Text, text
from sqlalchemy.orm import DeclarativeBase

from cockroachdb.sqla import (
    CockroachDBSession,
    GlobalTableMixin,
    RegionalByRowMixin,
    create_cockroachdb_engine,
)

# Connection URL — CockroachDB uses the cockroachdb:// or postgresql:// scheme
DATABASE_URL = "cockroachdb://root@localhost:26257/defaultdb"


# ---------------------------------------------------------------------------
# 1. Define ORM models with CockroachDB mixins
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class Order(RegionalByRowMixin, Base):
    """Orders table — REGIONAL BY ROW.

    Each row lives in a specific region based on its ``crdb_region`` column.
    This minimizes read latency for region-local queries.

    The ``RegionalByRowMixin`` automatically adds:
        - A ``crdb_region`` column (String, NOT NULL)
        - ``__table_args__`` with ``cockroachdb_locality: REGIONAL BY ROW``
    """

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    customer_name = Column(String(200), nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    status = Column(String(50), default="pending")


class Product(GlobalTableMixin, Base):
    """Products table — GLOBAL.

    Global tables are replicated to every region. Reads are fast from
    anywhere but writes pay cross-region latency. Ideal for reference
    data that changes infrequently.

    The ``GlobalTableMixin`` sets:
        - ``__table_args__`` with ``cockroachdb_locality: GLOBAL``
    """

    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    price = Column(Numeric(10, 2), nullable=False)


# ---------------------------------------------------------------------------
# 2. Engine and session setup
# ---------------------------------------------------------------------------


def create_session() -> CockroachDBSession:
    """Create a CockroachDB-optimized engine and session.

    ``create_cockroachdb_engine()`` applies sensible defaults:
        - pool_size=10
        - pool_pre_ping=True (detects stale connections)
        - pool_recycle=1800 (30-minute connection recycling)

    It also registers SQLAlchemy event listeners that automatically
    handle follower reads and region context propagation.
    """
    engine = create_cockroachdb_engine(
        DATABASE_URL,
        # Override defaults if needed:
        # pool_size=20,
        # pool_recycle=3600,
        echo=False,  # Set True to see generated SQL
    )

    return CockroachDBSession(engine)


# ---------------------------------------------------------------------------
# 3. execute_with_retry — retry-safe transactions
# ---------------------------------------------------------------------------


def demonstrate_retry(crdb: CockroachDBSession) -> None:
    """Execute a transaction with automatic retry on serialization conflicts.

    ``execute_with_retry`` creates a fresh Session for each attempt.
    The callback receives the Session, performs work, and the session
    is committed on success or rolled back on failure.
    """
    print("--- execute_with_retry ---")

    result = crdb.execute_with_retry(
        lambda session: session.execute(text("SELECT 1 AS health")).scalar()
    )
    print(f"  Health check result: {result}")

    # Insert with retry safety
    def insert_order(session):
        order = Order(
            id=1,
            customer_name="Alice",
            total=99.99,
            crdb_region="us-east1",
        )
        session.merge(order)
        return order.id

    order_id = crdb.execute_with_retry(insert_order)
    print(f"  Inserted/merged order ID: {order_id}")
    print()


# ---------------------------------------------------------------------------
# 4. follower_read — low-latency stale reads
# ---------------------------------------------------------------------------


def demonstrate_follower_read(crdb: CockroachDBSession) -> None:
    """Execute a read query using follower reads.

    ``crdb.follower_read()`` sets the FollowerReadContext so the event
    listener injects ``SET TRANSACTION AS OF SYSTEM TIME
    follower_read_timestamp()`` — any replica can serve the read.
    """
    print("--- follower_read ---")

    result = crdb.follower_read(
        lambda session: session.execute(text("SELECT count(*) FROM orders")).scalar()
    )
    print(f"  Order count (follower read): {result}")
    print()


# ---------------------------------------------------------------------------
# 5. in_region — region-pinned operations
# ---------------------------------------------------------------------------


def demonstrate_in_region(crdb: CockroachDBSession) -> None:
    """Execute operations pinned to a specific CockroachDB region.

    ``crdb.in_region('us-east1')`` returns a ``RegionalSession`` that
    sets the region contextvar before executing. This causes the event
    listener to inject ``SET crdb_region = 'us-east1'``.
    """
    print("--- in_region ---")

    east = crdb.in_region("us-east1")
    result = east.execute(
        lambda session: session.execute(
            text("SELECT count(*) FROM orders WHERE crdb_region = 'us-east1'")
        ).scalar()
    )
    print(f"  East coast orders: {result}")

    west = crdb.in_region("us-west2")
    result = west.execute(
        lambda session: session.execute(
            text("SELECT count(*) FROM orders WHERE crdb_region = 'us-west2'")
        ).scalar()
    )
    print(f"  West coast orders: {result}")
    print()


# ---------------------------------------------------------------------------
# 6. Model metadata inspection
# ---------------------------------------------------------------------------


def demonstrate_model_metadata() -> None:
    """Inspect the CockroachDB locality metadata set by the mixins."""
    print("--- Model metadata ---")

    order_args = Order.__table_args__
    print(f"  Order.__table_args__ = {order_args}")
    print(f"  Order locality: {order_args.get('info', {}).get('cockroachdb_locality')}")

    product_args = Product.__table_args__
    print(f"  Product.__table_args__ = {product_args}")
    print(f"  Product locality: {product_args.get('info', {}).get('cockroachdb_locality')}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== CockroachDB SQLAlchemy Integration Examples ===\n")

    # Model metadata works without a database
    demonstrate_model_metadata()

    # The remaining examples require a running CockroachDB instance.
    # Uncomment the block below when connected to a real cluster.

    # crdb = create_session()
    # demonstrate_retry(crdb)
    # demonstrate_follower_read(crdb)
    # demonstrate_in_region(crdb)

    print("Done.")
