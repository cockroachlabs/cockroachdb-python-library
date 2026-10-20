"""Django database router and configuration helpers for CockroachDB.

Provides :class:`CockroachDBRouter` for routing reads and writes based on
:class:`RegionContext` and :class:`FollowerReadContext`, and
:func:`configure_cockroachdb` for applying CockroachDB-optimal settings
to a Django ``DATABASES`` entry.

Example::

    # settings.py
    DATABASE_ROUTERS = ["cockroachdb.django.CockroachDBRouter"]

    DATABASES = {
        "default": configure_cockroachdb({
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "defaultdb",
            "HOST": "localhost",
            "PORT": "26257",
            "USER": "root",
        }),
        "follower": configure_cockroachdb({
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "defaultdb",
            "HOST": "follower.localhost",
            "PORT": "26257",
            "USER": "root",
        }),
    }
"""

from __future__ import annotations

from typing import Any

from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.core.region import RegionContext

# Default database aliases used by the router
_DEFAULT_DB = "default"
_FOLLOWER_DB = "follower"

# CockroachDB-optimal connection settings
_COCKROACHDB_DEFAULTS: dict[str, Any] = {
    "CONN_MAX_AGE": 600,
    "OPTIONS": {
        "sslmode": "verify-full",
        "options": "--cluster=<your-cluster>",
    },
    "ATOMIC_REQUESTS": False,
}


class CockroachDBRouter:
    """Django database router for CockroachDB multi-region deployments.

    Routes reads to a follower-read replica when :class:`FollowerReadContext`
    is active, and routes writes to the region-appropriate database when
    :class:`RegionContext` is active.

    The router uses the following database alias conventions:

    - ``"default"`` — primary read/write database
    - ``"follower"`` — follower-read replica (reads only)
    - ``"<region>"`` — region-specific database (e.g., ``"us-east1"``)

    If no context is active, all operations fall back to ``"default"``.

    Configure in settings::

        DATABASE_ROUTERS = ["cockroachdb.django.CockroachDBRouter"]
    """

    def __init__(
        self,
        follower_db: str = _FOLLOWER_DB,
        default_db: str = _DEFAULT_DB,
    ) -> None:
        self._follower_db = follower_db
        self._default_db = default_db

    def db_for_read(
        self,
        model: type,
        **hints: Any,
    ) -> str:
        """Route read operations based on active context.

        Returns the follower database alias when :class:`FollowerReadContext`
        is active, otherwise falls back to the region database or default.
        """
        if FollowerReadContext.is_active():
            return self._follower_db

        region = RegionContext.current()
        if region:
            return region

        return self._default_db

    def db_for_write(
        self,
        model: type,
        **hints: Any,
    ) -> str:
        """Route write operations based on active region context.

        Returns the region-specific database alias when :class:`RegionContext`
        is active, otherwise falls back to default.
        """
        region = RegionContext.current()
        if region:
            return region

        return self._default_db

    def allow_relation(
        self,
        obj1: Any,
        obj2: Any,
        **hints: Any,
    ) -> bool | None:
        """Allow all relations — CockroachDB handles distributed consistency."""
        return True

    def allow_migrate(
        self,
        db: str,
        app_label: str,
        model_name: str | None = None,
        **hints: Any,
    ) -> bool | None:
        """Allow migrations on all databases."""
        return True


def configure_cockroachdb(settings_dict: dict[str, Any]) -> dict[str, Any]:
    """Apply CockroachDB-optimal defaults to a Django ``DATABASES`` entry.

    Merges sensible defaults for CockroachDB deployments (connection
    pooling, SSL, atomic requests) with the provided settings.
    User-provided values take precedence over defaults.

    Args:
        settings_dict: A Django ``DATABASES`` entry dict.

    Returns:
        The settings dict with CockroachDB defaults applied.

    Example::

        DATABASES = {
            "default": configure_cockroachdb({
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "defaultdb",
                "HOST": "localhost",
                "PORT": "26257",
                "USER": "root",
            }),
        }
    """
    result = dict(settings_dict)

    # Apply top-level defaults (user values take precedence)
    for key, value in _COCKROACHDB_DEFAULTS.items():
        if key == "OPTIONS":
            # Merge OPTIONS dicts rather than overwriting
            existing_options = result.get("OPTIONS", {})
            merged_options = {**value, **existing_options}
            result["OPTIONS"] = merged_options
        else:
            result.setdefault(key, value)

    return result
