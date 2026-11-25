"""Django system check that compares models against the live multi-region schema.

Django's system-check framework is the idiomatic analog of the Spring starter's
startup check. Add ``"cockroachdb.django"`` to ``INSTALLED_APPS`` and the
:class:`~cockroachdb.django.apps.CockroachDBConfig` registers
:func:`check_multiregion_schema`, which runs at startup and on ``manage.py check``.

It reads each model's locality from the :class:`RegionalByRowMixin` /
:class:`GlobalTableMixin` (their ``crdb_locality`` class attribute) and compares
it with the database (see :mod:`cockroachdb.core.multiregion`).

Mode comes from the ``COCKROACHDB_MULTIREGION_MODE`` setting
(``"none"`` | ``"warn"`` | ``"validate"``, default ``"warn"``):

* ``validate`` — any problem is an ``Error`` (fails ``manage.py check`` and startup).
* ``warn`` — problems are ``Warning``\\ s, but a contradiction is an ``Error`` even here.
* ``none`` — skipped.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cockroachdb.core.multiregion import (
    MultiregionTable,
    evaluate_schema,
    kind_for,
    normalize_mode,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.core.checks import CheckMessage

logger = logging.getLogger(__name__)

SETTING = "COCKROACHDB_MULTIREGION_MODE"


def _tables_from_models(models: Iterable[Any]) -> list[MultiregionTable]:
    """Every concrete model as a :class:`MultiregionTable`.

    Keys off the ORM mixins' ``crdb_locality`` attribute. Unannotated models are
    included too, so the check can flag a table that is multi-region while its
    model is not.
    """
    tables: list[MultiregionTable] = []
    for model in models:
        meta = model._meta
        locality = getattr(model, "crdb_locality", None)
        field_names = {f.name for f in meta.get_fields()}
        region_column = "crdb_region" if "crdb_region" in field_names else None
        tables.append(
            MultiregionTable(
                entity=meta.label,
                table=meta.db_table,
                kind=kind_for(locality),
                region_column=region_column,
            )
        )
    return tables


def _messages_for(outcome: str, report: Any, mode: str) -> list[CheckMessage]:
    from django.core.checks import Error
    from django.core.checks import Warning as CheckWarning

    if report is None or outcome in ("skip", "ok"):
        return []
    message = report.format(mode, setting=SETTING)
    if outcome == "fail":
        return [Error(message, id="cockroachdb.E001")]
    return [CheckWarning(message, id="cockroachdb.W001")]


def check_multiregion_schema(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """Registered Django check. See the module docstring for behaviour."""
    from django.conf import settings
    from django.core.checks import Error
    from django.db import connections

    mode = normalize_mode(getattr(settings, SETTING, "warn"))
    if mode == "none":
        return []

    from django.apps import apps

    tables = _tables_from_models(apps.get_models())
    if not tables:
        return []

    conn = connections["default"]
    try:
        with conn.cursor() as cursor:

            def query(sql: str, params: object = ()) -> list[Any]:
                cursor.execute(sql, params or None)
                return list(cursor.fetchall())

            outcome, report = evaluate_schema(query, tables, mode)
    except Exception as exc:  # pragma: no cover - exercised via integration
        if mode == "validate":
            return [
                Error(
                    f"CockroachDB multiregion check could not read the database: {exc}",
                    id="cockroachdb.E002",
                )
            ]
        logger.warning("CockroachDB multiregion check could not read the database: %s", exc)
        return []

    return _messages_for(outcome, report, mode)
