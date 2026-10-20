"""Django configuration for test discovery.

This module configures Django settings before any Django-dependent test
modules are imported.  It is imported by conftest.py if needed, or
tests can use the ``django_settings`` fixture.
"""

from __future__ import annotations

import django
from django.conf import settings


def configure_django_settings() -> None:
    """Configure minimal Django settings for testing."""
    if settings.configured:
        return

    settings.configure(
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            },
        },
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
        ],
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        COCKROACHDB={},
    )
    django.setup()


# Auto-configure when this module is imported
configure_django_settings()
