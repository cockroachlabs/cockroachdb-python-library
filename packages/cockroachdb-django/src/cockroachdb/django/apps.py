"""Django AppConfig for the CockroachDB adapter.

Add ``"cockroachdb.django"`` to ``INSTALLED_APPS`` to register the multi-region
schema system check (:func:`cockroachdb.django.checks.check_multiregion_schema`).
"""

from __future__ import annotations

from django.apps import AppConfig


class CockroachDBConfig(AppConfig):  # type: ignore[misc]
    name = "cockroachdb.django"
    label = "cockroachdb"
    verbose_name = "CockroachDB"

    def ready(self) -> None:
        from cockroachdb.django.checks import check_multiregion_schema
        from django.core.checks import register

        register(check_multiregion_schema)
