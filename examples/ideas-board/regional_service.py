"""Multi-region: REGIONAL BY ROW writes that home each idea in a chosen region.

``@regional_by_row`` marks the entity; ``@crdb_region`` pins a function to a region;
``RegionContext.scoped(region)`` carries the region across a call; the write sets
the hidden ``crdb_region`` column from that context.

NOTE: like follower reads, the psycopg path is cooperative — only the SQLAlchemy
layer auto-issues ``SET crdb_region``, so this service writes ``crdb_region``
explicitly. That is exactly what the Java demo does too (it sets ``crdb_region``
from its call context rather than relying on the gateway region).

REGIONAL BY ROW requires a multi-region database (multiple ADD REGIONs), which a
single node does not have, so the integration test is gated and skips by default.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

# tag::regional-entity[]
from cockroachdb import crdb_region, regional_by_row
from cockroachdb.core import RegionContext


@regional_by_row(default_region="us-east1")
@dataclass
class RegionalIdea:
    """An idea pinned to a region via the hidden ``crdb_region`` column."""

    id: str
    text: str
    region: str


# end::regional-entity[]


# tag::region-config[]
# Enablement DDL. On a multi-region database (ALTER DATABASE ... ADD REGION ...)
# this makes the table REGIONAL BY ROW, adding the hidden crdb_region column.
REGIONAL_BY_ROW_DDL = (
    "CREATE TABLE IF NOT EXISTS regional_idea "
    "(id UUID PRIMARY KEY DEFAULT gen_random_uuid(), text STRING NOT NULL);"
    "ALTER TABLE regional_idea SET LOCALITY REGIONAL BY ROW"
)
# end::region-config[]


# tag::inregion-usage[]
def add_in_region(dsn: str, region: str, text: str) -> str:
    """Store an idea homed in ``region`` by writing ``crdb_region`` from the context."""
    RegionContext.validate(region)
    with RegionContext.scoped(region):
        bound = RegionContext.current()
        with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO regional_idea (text, crdb_region) VALUES (%s, %s) RETURNING id",
                (text, bound),
            )
            return str(cur.fetchone()[0])


@crdb_region("us-east1")
def add_in_us_east(dsn: str, text: str) -> str:
    """Store an idea homed in us-east1 (region read back from ``@crdb_region``)."""
    return add_in_region(dsn, add_in_us_east.__crdb_region__, text)


@crdb_region("us-west1")
def add_in_us_west(dsn: str, text: str) -> str:
    """Store an idea homed in us-west1."""
    return add_in_region(dsn, add_in_us_west.__crdb_region__, text)


def region_of(dsn: str, idea_id: str) -> str | None:
    """The ``crdb_region`` a row actually landed in, if present."""
    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT crdb_region::STRING FROM regional_idea WHERE id = %s", (idea_id,))
        row = cur.fetchone()
        return row[0] if row else None


# end::inregion-usage[]
