"""SQLAlchemy ORM mixins for CockroachDB multi-region and vector tables.

These mixins add CockroachDB-specific columns and ``__table_args__`` to
declarative models, mirroring the Java ``@RegionalByRow`` /
``@GlobalTable`` annotations and .NET ``[RegionalByRow]`` /
``[GlobalTable]`` attributes.

Example::

    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass

    class Order(RegionalByRowMixin, Base):
        __tablename__ = "orders"
        id = Column(Integer, primary_key=True)
        total = Column(Numeric)

    class Product(GlobalTableMixin, Base):
        __tablename__ = "products"
        id = Column(Integer, primary_key=True)
        name = Column(String)
"""

from __future__ import annotations

from sqlalchemy import Column, String
from sqlalchemy.orm import declared_attr


class RegionalByRowMixin:
    """Mixin for CockroachDB REGIONAL BY ROW tables.

    Adds a ``crdb_region`` column and sets ``__table_args__`` to include
    the CockroachDB locality configuration. Models inheriting this mixin
    will have their rows distributed across regions based on the
    ``crdb_region`` column value.

    The ``crdb_region`` column is **not** automatically set — application
    code or a default value in CockroachDB should assign it.
    """

    crdb_region: str = Column(  # type: ignore[assignment]
        String,
        nullable=False,
        server_default="",
        comment="CockroachDB region for REGIONAL BY ROW locality",
    )

    @declared_attr  # type: ignore[arg-type]
    def __table_args__(cls) -> dict:  # noqa: N805
        return {
            "info": {"cockroachdb_locality": "REGIONAL BY ROW"},
        }


class GlobalTableMixin:
    """Mixin for CockroachDB GLOBAL tables.

    Sets ``__table_args__`` to mark the table as globally replicated.
    Global tables are readable from any region with low latency but
    incur higher write latency because writes must propagate to all
    regions.
    """

    @declared_attr  # type: ignore[arg-type]
    def __table_args__(cls) -> dict:  # noqa: N805
        return {
            "info": {"cockroachdb_locality": "GLOBAL"},
        }


class VectorColumnMixin:
    """Mixin that adds a vector embedding column for pgvector operations.

    Adds a ``vector_embedding`` column stored as a string representation
    of a float array. CockroachDB uses the pgvector extension for
    similarity search — the column type in the database should be
    ``VECTOR(dimensions)``.

    The default dimension is 1536 (OpenAI ``text-embedding-3-small``).
    Override ``_vector_dimensions`` on the subclass to change it.

    Note:
        This mixin stores the column as ``String`` for maximum ORM
        compatibility. Use ``text()`` or raw SQL for actual vector
        similarity queries until CockroachDB's pgvector type is
        natively supported by SQLAlchemy dialects.
    """

    _vector_dimensions: int = 1536

    vector_embedding: str | None = Column(  # type: ignore[assignment]
        String,
        nullable=True,
        comment="pgvector embedding column",
    )
