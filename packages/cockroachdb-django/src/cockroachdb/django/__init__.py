"""CockroachDB Python Library — Django adapter.

Provides Django middleware for region context, ORM model mixins for
multi-region tables, retry utilities for serialization conflicts,
a database router for follower reads, and signals for retry events.

Quick start::

    # settings.py
    MIDDLEWARE = [
        "cockroachdb.django.CockroachDBMiddleware",
        ...
    ]

    COCKROACHDB = {
        "REGION_HEADER": "X-CockroachDB-Region",
        "FOLLOWER_READ_SAFE_METHODS": ["GET", "HEAD"],
    }

Imports are lazy because Django's ``models.Model`` metaclass requires
``settings.INSTALLED_APPS`` at class-definition time.  Eagerly importing
``mixins`` would force Django to be configured before any consumer can
even ``import cockroachdb.django``.
"""

from __future__ import annotations

__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy module-level imports to avoid triggering Django's app registry."""
    _lazy = {
        "CockroachDBMiddleware": "cockroachdb.django.middleware",
        "CockroachDBRouter": "cockroachdb.django.backend",
        "configure_cockroachdb": "cockroachdb.django.backend",
        "RegionalByRowMixin": "cockroachdb.django.mixins",
        "GlobalTableMixin": "cockroachdb.django.mixins",
        "TimestampMixin": "cockroachdb.django.mixins",
        "atomic_with_retry": "cockroachdb.django.retry",
        "execute_with_retry": "cockroachdb.django.retry",
        "pre_cockroachdb_retry": "cockroachdb.django.signals",
        "post_cockroachdb_retry": "cockroachdb.django.signals",
        "cockroachdb_retry_exhausted": "cockroachdb.django.signals",
    }
    if name in _lazy:
        import importlib

        module = importlib.import_module(_lazy[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CockroachDBMiddleware",
    "CockroachDBRouter",
    "GlobalTableMixin",
    "RegionalByRowMixin",
    "TimestampMixin",
    "atomic_with_retry",
    "cockroachdb_retry_exhausted",
    "configure_cockroachdb",
    "execute_with_retry",
    "post_cockroachdb_retry",
    "pre_cockroachdb_retry",
]
