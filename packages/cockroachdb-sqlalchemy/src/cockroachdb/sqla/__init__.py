"""CockroachDB Python Library — SQLAlchemy 2.0 adapter.

Provides a CockroachDB-optimized engine factory, session wrapper with
built-in retry logic, and ORM mixins for multi-region and vector tables.

Quick start::

    from cockroachdb.sqla import create_cockroachdb_engine, CockroachDBSession

    engine = create_cockroachdb_engine("cockroachdb://root@localhost:26257/mydb")
    crdb = CockroachDBSession(engine)

    result = crdb.execute_with_retry(
        lambda session: session.execute(text("SELECT 1")).scalar()
    )
"""

from __future__ import annotations

from cockroachdb.sqla.ddl_compiler import CockroachDDLCompiler
from cockroachdb.sqla.dialect import CockroachDBDialect
from cockroachdb.sqla.engine import create_cockroachdb_engine
from cockroachdb.sqla.events import FollowerReadContext, RegionContext
from cockroachdb.sqla.mixins import GlobalTableMixin, RegionalByRowMixin, VectorColumnMixin
from cockroachdb.sqla.session import CockroachDBSession, RegionalSession

__all__ = [
    "CockroachDBDialect",
    "CockroachDBSession",
    "CockroachDDLCompiler",
    "FollowerReadContext",
    "GlobalTableMixin",
    "RegionContext",
    "RegionalByRowMixin",
    "RegionalSession",
    "VectorColumnMixin",
    "create_cockroachdb_engine",
]
