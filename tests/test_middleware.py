"""Tests for cockroachdb.core.middleware (ASGI and WSGI)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cockroachdb.core.middleware import (
    CockroachDBASGIMiddleware,
    CockroachDBWSGIMiddleware,
)
from cockroachdb.core.region import RegionContext


class TestCockroachDBASGIMiddleware:
    """Tests for the ASGI middleware."""

    @pytest.mark.asyncio
    async def test_sets_region_from_header(self) -> None:
        captured_region: str | None = None

        async def app(scope: dict, receive: object, send: object) -> None:
            nonlocal captured_region
            captured_region = RegionContext.current()

        middleware = CockroachDBASGIMiddleware(app)
        scope = {
            "type": "http",
            "headers": [
                (b"x-cockroachdb-region", b"us-east1"),
            ],
        }
        await middleware(scope, None, None)
        assert captured_region == "us-east1"

    @pytest.mark.asyncio
    async def test_no_region_header_passes_through(self) -> None:
        captured_region: str | None = "should_be_none"

        async def app(scope: dict, receive: object, send: object) -> None:
            nonlocal captured_region
            captured_region = RegionContext.current()

        middleware = CockroachDBASGIMiddleware(app)
        scope = {
            "type": "http",
            "headers": [],
        }
        await middleware(scope, None, None)
        assert captured_region is None

    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self) -> None:
        app = AsyncMock()
        middleware = CockroachDBASGIMiddleware(app)
        scope = {"type": "lifespan"}
        await middleware(scope, None, None)
        app.assert_awaited_once_with(scope, None, None)

    @pytest.mark.asyncio
    async def test_custom_header_name(self) -> None:
        captured_region: str | None = None

        async def app(scope: dict, receive: object, send: object) -> None:
            nonlocal captured_region
            captured_region = RegionContext.current()

        middleware = CockroachDBASGIMiddleware(app, header_name="x-region")
        scope = {
            "type": "http",
            "headers": [
                (b"x-region", b"eu-west1"),
            ],
        }
        await middleware(scope, None, None)
        assert captured_region == "eu-west1"

    @pytest.mark.asyncio
    async def test_region_cleaned_after_request(self) -> None:
        async def app(scope: dict, receive: object, send: object) -> None:
            pass

        middleware = CockroachDBASGIMiddleware(app)
        scope = {
            "type": "http",
            "headers": [(b"x-cockroachdb-region", b"us-east1")],
        }
        await middleware(scope, None, None)
        # After the middleware finishes, region should be restored
        assert RegionContext.current() is None


class TestCockroachDBWSGIMiddleware:
    """Tests for the WSGI middleware."""

    def test_sets_region_from_environ(self) -> None:
        captured_region: str | None = None

        def app(environ: dict, start_response: object) -> list:
            nonlocal captured_region
            captured_region = RegionContext.current()
            return [b"ok"]

        middleware = CockroachDBWSGIMiddleware(app)
        environ = {"HTTP_X_COCKROACHDB_REGION": "us-east1"}
        middleware(environ, None)
        assert captured_region == "us-east1"

    def test_no_region_passes_through(self) -> None:
        captured_region: str | None = "should_be_none"

        def app(environ: dict, start_response: object) -> list:
            nonlocal captured_region
            captured_region = RegionContext.current()
            return [b"ok"]

        middleware = CockroachDBWSGIMiddleware(app)
        environ = {}
        middleware(environ, None)
        assert captured_region is None

    def test_custom_header_name(self) -> None:
        captured_region: str | None = None

        def app(environ: dict, start_response: object) -> list:
            nonlocal captured_region
            captured_region = RegionContext.current()
            return [b"ok"]

        middleware = CockroachDBWSGIMiddleware(app, header_name="X-Region")
        environ = {"HTTP_X_REGION": "ap-south1"}
        middleware(environ, None)
        assert captured_region == "ap-south1"

    def test_returns_app_response(self) -> None:
        def app(environ: dict, start_response: object) -> list:
            return [b"hello"]

        middleware = CockroachDBWSGIMiddleware(app)
        result = middleware({}, None)
        assert result == [b"hello"]
