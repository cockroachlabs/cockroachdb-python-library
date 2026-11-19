"""Integration test for REGIONAL BY ROW — gated on a real multi-region cluster.

REGIONAL BY ROW needs a database with multiple regions (e.g. us-east1 + us-west1
added via ALTER DATABASE ... ADD REGION), which a single Testcontainers node does
not have. This test therefore SKIPS unless ``CRDB_MULTIREGION=true``; when enabled
it reads an external cluster from ``CRDB_URL`` (expected to already have both
regions added). It never fails by default — it is skipped. Mirrors the Java
``RegionalIdeaIT``.
"""

from __future__ import annotations

import os

import psycopg
import pytest

import regional_service as rs

pytestmark = pytest.mark.skipif(
    os.environ.get("CRDB_MULTIREGION") != "true",
    reason="REGIONAL BY ROW needs a multi-region cluster; "
    "set CRDB_MULTIREGION=true and CRDB_URL",
)


# tag::region-it[]
def test_writes_home_rows_in_the_pinned_region() -> None:
    url = os.environ["CRDB_URL"]
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS regional_idea")
        for ddl in rs.REGIONAL_BY_ROW_DDL.split(";"):
            if ddl.strip():
                cur.execute(ddl)

    east = rs.add_in_us_east(url, "Home me in the east")
    west = rs.add_in_us_west(url, "Home me in the west")

    assert rs.region_of(url, east) == "us-east1"
    assert rs.region_of(url, west) == "us-west1"
# end::region-it[]
