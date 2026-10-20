"""Django middleware for automatic CockroachDB region context propagation.

Extracts the region from an HTTP request header and sets
:class:`RegionContext` for the duration of the request.  Optionally
activates :class:`FollowerReadContext` for safe HTTP methods (GET, HEAD
by default).

Configuration is read from ``django.conf.settings.COCKROACHDB``::

    # settings.py
    COCKROACHDB = {
        "REGION_HEADER": "X-CockroachDB-Region",
        "FOLLOWER_READ_SAFE_METHODS": ["GET", "HEAD"],
    }
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.core.region import RegionContext
from django.conf import settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest, HttpResponse

_DEFAULT_CONFIG: dict[str, Any] = {
    "REGION_HEADER": "X-CockroachDB-Region",
    "FOLLOWER_READ_SAFE_METHODS": ["GET", "HEAD"],
}


def _get_config() -> dict[str, Any]:
    """Merge user settings with defaults."""
    user_config: dict[str, Any] = getattr(settings, "COCKROACHDB", {})
    return {**_DEFAULT_CONFIG, **user_config}


class CockroachDBMiddleware:
    """Django middleware for CockroachDB region and follower-read context.

    Uses the new-style Django middleware pattern (``__init__`` /
    ``__call__``).  The middleware:

    1. Reads the region from the configured request header and sets
       :class:`RegionContext` for the request lifecycle.
    2. Optionally activates :class:`FollowerReadContext` for HTTP
       methods listed in ``FOLLOWER_READ_SAFE_METHODS``.

    Example::

        MIDDLEWARE = [
            "cockroachdb.django.CockroachDBMiddleware",
            ...
        ]
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        config = _get_config()
        header_name: str = config["REGION_HEADER"]
        safe_methods: list[str] = config["FOLLOWER_READ_SAFE_METHODS"]

        # Django normalises headers via META: HTTP_X_COCKROACHDB_REGION
        meta_key = "HTTP_" + header_name.upper().replace("-", "_")
        region: str | None = request.META.get(meta_key)

        # Also check request.headers (Django 3.2+) as a fallback
        if region is None:
            region = request.headers.get(header_name)

        use_follower_read = request.method in safe_methods

        if region and use_follower_read:
            with RegionContext.scoped(region), FollowerReadContext.scoped():
                return self.get_response(request)
        elif region:
            with RegionContext.scoped(region):
                return self.get_response(request)
        elif use_follower_read:
            with FollowerReadContext.scoped():
                return self.get_response(request)
        else:
            return self.get_response(request)
