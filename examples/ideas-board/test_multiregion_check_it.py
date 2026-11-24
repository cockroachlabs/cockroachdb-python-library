"""Integration test for the 0.2.0 multi-region schema check — gated like the
REGIONAL BY ROW writes in ``test_regional_it.py``.

``verify_multiregion_schema`` reads the *live* multi-region configuration, so it
only means anything against a real multi-region cluster. This test therefore
SKIPS unless ``CRDB_MULTIREGION=true``; when enabled it reads an external
cluster from ``CRDB_URL`` (expected to already have the regions added). It never
fails by default — it is skipped.
"""

from __future__ import annotations

import os

import multiregion_check_service as mc
import psycopg
import pytest
import regional_service as rs

from cockroachdb.sqla import verify_multiregion_schema

pytestmark = pytest.mark.skipif(
    os.environ.get("CRDB_MULTIREGION") != "true",
    reason="multi-region check needs a multi-region cluster; set CRDB_MULTIREGION=true and CRDB_URL",
)


def _sqlalchemy_url(pg_url: str) -> str:
    """Rewrite a ``postgres://`` DSN to the CockroachDB SQLAlchemy dialect URL."""
    return "cockroachdb+psycopg://" + pg_url.split("://", 1)[1]


# tag::mr-check-report[]
def test_matching_schema_passes() -> None:
    url = os.environ["CRDB_URL"]
    # Make the live table match the model: regional_idea as REGIONAL BY ROW.
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS regional_idea")
        for ddl in rs.REGIONAL_BY_ROW_DDL.split(";"):
            if ddl.strip():
                cur.execute(ddl)

    engine = mc.start_engine(_sqlalchemy_url(url))  # warn opt-in runs here; match => no raise

    # A matching schema passes even the strict mode (any problem would raise).
    verify_multiregion_schema(engine, mc.Base, mode="validate")


# end::mr-check-report[]
