"""Multi-region schema check (cockroachdb-sqlalchemy 0.2.0) for the ideas board.

The rest of this example talks to CockroachDB through plain psycopg. The 0.2.0
multi-region *check* is a SQLAlchemy-layer feature: you declare each table's
locality with an ORM mixin (``RegionalByRowMixin`` / ``GlobalTableMixin``), and
the library compares your models against the live database so a model that says
"REGIONAL BY ROW" can't silently drift from a table that isn't.

This module mirrors the ``regional_idea`` table (created by
``regional_service.REGIONAL_BY_ROW_DDL``) as a SQLAlchemy model and runs the
check at engine creation. It never calls ``create_all`` — the check is
read-only; the model is just metadata the check reads.
"""

from __future__ import annotations

# tag::mr-check-entity[]
from sqlalchemy import Column, String
from sqlalchemy.orm import DeclarativeBase

from cockroachdb.sqla import RegionalByRowMixin


class Base(DeclarativeBase):
    pass


class RegionalIdeaModel(RegionalByRowMixin, Base):
    """ORM view of the ``regional_idea`` table, declared REGIONAL BY ROW.

    ``RegionalByRowMixin`` adds the ``crdb_region`` column and stamps the
    locality the check reads — it is the SQLAlchemy counterpart of the Java
    ``@RegionalByRow`` and .NET ``[RegionalByRow]`` the other demos use.
    """

    __tablename__ = "regional_idea"

    id = Column(String, primary_key=True)
    text = Column(String, nullable=False)


# end::mr-check-entity[]


# tag::mr-check-usage[]
from cockroachdb.sqla import create_cockroachdb_engine


def start_engine(url: str):
    """Create the engine and verify the multi-region schema at startup.

    ``multiregion_mode="warn"`` logs a mismatch (e.g. the model says REGIONAL BY
    ROW but the table isn't) instead of failing boot; a direct contradiction
    still raises even in ``warn``. Use ``"validate"`` to fail on any problem, or
    ``"none"`` to skip. ``url`` is a SQLAlchemy URL, e.g.
    ``cockroachdb+psycopg://root@localhost:26257/defaultdb?sslmode=disable``.
    """
    return create_cockroachdb_engine(url, multiregion_base=Base, multiregion_mode="warn")


# end::mr-check-usage[]
