"""Opt-in multi-region schema check for SQLAlchemy models.

Enumerates a declarative base's mapped classes, reads their locality from the
``cockroachdb_locality`` key the :class:`RegionalByRowMixin` / :class:`GlobalTableMixin`
stamp onto ``Table.info``, and compares them against the live multi-region
configuration of the database (see :mod:`cockroachdb.core.multiregion`).

There is no auto-startup for SQLAlchemy. Call :func:`verify_multiregion_schema`
directly, or pass ``multiregion_base=`` to :func:`create_cockroachdb_engine`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cockroachdb.core.multiregion import (
    MultiregionCheckError,
    MultiregionTable,
    evaluate_schema,
    kind_for,
    normalize_mode,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _tables_from_base(base: type) -> list[MultiregionTable]:
    """Every mapped class under ``base`` as a :class:`MultiregionTable`.

    Keys off the ORM mixins (``Table.info["cockroachdb_locality"]``), not the
    marker decorators in ``cockroachdb.decorators`` — those only stamp
    ``__crdb_*__`` attributes and are not wired to tables. Unannotated classes
    are included too, so the check can also flag a table that is multi-region
    while its model is not.
    """
    tables: list[MultiregionTable] = []
    for mapper in base.registry.mappers:
        cls = mapper.class_
        table = mapper.local_table
        if table is None:
            continue
        locality = table.info.get("cockroachdb_locality") if table.info else None
        kind = kind_for(locality)
        region_column = "crdb_region" if "crdb_region" in table.columns else None
        tables.append(
            MultiregionTable(
                entity=f"{cls.__module__}.{cls.__qualname__}",
                table=table.name,
                kind=kind,
                schema=table.schema,
                region_column=region_column,
            )
        )
    return tables


def verify_multiregion_schema(engine: Engine, base: type, mode: str = "warn") -> None:
    """Compare ``base``'s mapped models against the live multi-region schema.

    Read-only. In ``warn`` mode it logs problems; a contradiction (the model and
    the schema disagree about where rows live) raises in every mode but ``none``.
    In ``validate`` mode any problem raises.

    Args:
        engine: a configured CockroachDB engine.
        base: the declarative base whose mapped classes to check.
        mode: ``"none"`` | ``"warn"`` | ``"validate"`` (default ``"warn"``).

    Raises:
        MultiregionCheckError: on a contradiction, or any problem in validate mode.
        ValueError: if ``mode`` is not a known mode.
    """
    mode = normalize_mode(mode)
    if mode == "none":
        return
    tables = _tables_from_base(base)
    if not tables:
        return

    with engine.connect() as conn:

        def query(sql: str, params: object = ()) -> list:
            result = conn.exec_driver_sql(sql, params) if params else conn.exec_driver_sql(sql)
            return list(result)

        try:
            outcome, report = evaluate_schema(query, tables, mode)
        except Exception as exc:  # pragma: no cover - exercised via integration
            if mode == "validate":
                raise MultiregionCheckError(
                    f"CockroachDB multiregion check could not read the database: {exc}"
                ) from exc
            logger.warning("CockroachDB multiregion check could not read the database: %s", exc)
            return

    if report is None or outcome in ("skip", "ok"):
        logger.debug("CockroachDB multiregion check: %s", outcome)
        return
    message = report.format(mode)
    if outcome == "fail":
        raise MultiregionCheckError(message)
    logger.warning(message)
