"""ASGI and WSGI middleware for automatic CockroachDB region context propagation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cockroachdb.core.region import RegionContext

if TYPE_CHECKING:
    from collections.abc import Callable


class CockroachDBASGIMiddleware:
    """ASGI middleware that extracts region from an HTTP header and sets RegionContext."""

    def __init__(
        self,
        app: Any,
        header_name: str = "x-cockroachdb-region",
    ) -> None:
        self._app = app
        self._header_name = header_name.lower().encode("latin-1")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        region = self._extract_region(scope)
        if region:
            with RegionContext.scoped(region):
                await self._app(scope, receive, send)
        else:
            await self._app(scope, receive, send)

    def _extract_region(self, scope: dict[str, Any]) -> str | None:
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        for name, value in headers:
            if name.lower() == self._header_name:
                return value.decode("latin-1")
        return None


class CockroachDBWSGIMiddleware:
    """WSGI middleware that extracts region from an HTTP header and sets RegionContext."""

    def __init__(
        self,
        app: Callable[..., Any],
        header_name: str = "X-CockroachDB-Region",
    ) -> None:
        self._app = app
        self._environ_key = "HTTP_" + header_name.upper().replace("-", "_")

    def __call__(self, environ: dict[str, Any], start_response: Any) -> Any:
        region = environ.get(self._environ_key)
        if region:
            with RegionContext.scoped(region):
                return self._app(environ, start_response)
        return self._app(environ, start_response)
