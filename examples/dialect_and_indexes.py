"""Demonstrate CockroachDB dialect with inline indexes.

This example shows how to:
1. Connect using the ``cockroachdb://`` dialect URL
2. Define tables with indexes that are created inline for ~25x speedup
3. Use computed columns (STORED only)
4. Reflect columns and indexes from an existing table

Prerequisites:
    pip install cockroachdb-sqlalchemy
    # Start a CockroachDB node:
    docker compose -f docker/docker-compose.1node.yml up -d

Usage:
    python examples/dialect_and_indexes.py
"""

from sqlalchemy import (
    Column,
    Computed,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
)

# 1. Connect using cockroachdb:// dialect URL
engine = create_engine(
    "cockroachdb://root@localhost:26257/defaultdb",
    echo=True,  # Show generated SQL
)

metadata = MetaData()

# 2. Define a table with indexes — they'll be inlined in CREATE TABLE
orders = Table(
    "demo_orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer", String(100)),
    Column("region", String(50)),
    Column("total", Integer),
    Column("qty", Integer),
    # Computed column: CockroachDB requires STORED
    Column("total_with_tax", Integer, Computed("total * qty", persisted=True)),
    # These indexes are emitted INSIDE the CREATE TABLE statement
    Index("idx_customer", "customer"),
    Index("idx_region_total", "region", "total"),
    # With STORING clause for covering indexes
    Index("idx_customer_store", "customer", cockroachdb_storing=["region"]),
)

# 3. Create table — look at the SQL output:
# CREATE TABLE demo_orders (
#   id INTEGER NOT NULL,
#   customer VARCHAR(100),
#   ...
#   total_with_tax INTEGER AS (total * qty) STORED,
#   INDEX idx_customer (customer),
#   INDEX idx_region_total (region, total),
#   INDEX idx_customer_store (customer) STORING (region)
# )
print("\n=== Creating table with inline indexes ===")
metadata.create_all(engine)

# 4. Reflect and verify
print("\n=== Reflecting table ===")
inspector = inspect(engine)
columns = inspector.get_columns("demo_orders")
print(f"Columns: {[c['name'] for c in columns]}")

indexes = inspector.get_indexes("demo_orders")
print(f"Indexes: {[i['name'] for i in indexes]}")

# 5. Clean up
print("\n=== Cleaning up ===")
metadata.drop_all(engine)
engine.dispose()
print("Done!")
