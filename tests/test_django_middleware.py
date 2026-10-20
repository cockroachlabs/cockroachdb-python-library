"""Tests for cockroachdb.django.middleware — Django CockroachDB middleware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.core.region import RegionContext
from cockroachdb.django.middleware import CockroachDBMiddleware


class FakeRequest:
    """Minimal Django HttpRequest stand-in for testing."""

    def __init__(
        self,
        method: str = "GET",
        meta: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.method = method
        self.META = meta or {}
        self.headers = headers or {}


class TestCockroachDBMiddleware:
    """Tests for CockroachDBMiddleware."""

    def _make_middleware(
        self,
        cockroachdb_settings: dict | None = None,
    ) -> tuple[CockroachDBMiddleware, MagicMock]:
        """Create middleware with a mock get_response."""
        mock_response = MagicMock()
        mock_get_response = MagicMock(return_value=mock_response)
        middleware = CockroachDBMiddleware(mock_get_response)

        if cockroachdb_settings is not None:
            patcher = patch(
                "cockroachdb.django.middleware.settings",
                COCKROACHDB=cockroachdb_settings,
            )
            patcher.start()
            # Store patcher so tests can stop it
            middleware._test_patcher = patcher  # type: ignore[attr-defined]

        return middleware, mock_get_response

    def _stop_patcher(self, middleware: CockroachDBMiddleware) -> None:
        patcher = getattr(middleware, "_test_patcher", None)
        if patcher:
            patcher.stop()

    @patch("cockroachdb.django.middleware.settings")
    def test_region_extracted_from_meta(self, mock_settings: MagicMock) -> None:
        """Region is extracted from request.META using the default header."""
        mock_settings.COCKROACHDB = {}
        captured_region: str | None = None

        def get_response(request: FakeRequest) -> MagicMock:
            nonlocal captured_region
            captured_region = RegionContext.current()
            return MagicMock()

        middleware = CockroachDBMiddleware(get_response)
        request = FakeRequest(
            method="POST",
            meta={"HTTP_X_COCKROACHDB_REGION": "us-east1"},
        )

        middleware(request)
        assert captured_region == "us-east1"

    @patch("cockroachdb.django.middleware.settings")
    def test_follower_read_activated_on_get(self, mock_settings: MagicMock) -> None:
        """FollowerReadContext is activated for GET requests."""
        mock_settings.COCKROACHDB = {}
        follower_active = False

        def get_response(request: FakeRequest) -> MagicMock:
            nonlocal follower_active
            follower_active = FollowerReadContext.is_active()
            return MagicMock()

        middleware = CockroachDBMiddleware(get_response)
        request = FakeRequest(method="GET")

        middleware(request)
        assert follower_active is True

    @patch("cockroachdb.django.middleware.settings")
    def test_follower_read_activated_on_head(self, mock_settings: MagicMock) -> None:
        """FollowerReadContext is activated for HEAD requests."""
        mock_settings.COCKROACHDB = {}
        follower_active = False

        def get_response(request: FakeRequest) -> MagicMock:
            nonlocal follower_active
            follower_active = FollowerReadContext.is_active()
            return MagicMock()

        middleware = CockroachDBMiddleware(get_response)
        request = FakeRequest(method="HEAD")

        middleware(request)
        assert follower_active is True

    @patch("cockroachdb.django.middleware.settings")
    def test_no_follower_read_on_post(self, mock_settings: MagicMock) -> None:
        """FollowerReadContext is NOT activated for POST requests."""
        mock_settings.COCKROACHDB = {}
        follower_active = False

        def get_response(request: FakeRequest) -> MagicMock:
            nonlocal follower_active
            follower_active = FollowerReadContext.is_active()
            return MagicMock()

        middleware = CockroachDBMiddleware(get_response)
        request = FakeRequest(method="POST")

        middleware(request)
        assert follower_active is False

    @patch("cockroachdb.django.middleware.settings")
    def test_custom_header_name(self, mock_settings: MagicMock) -> None:
        """Custom header name from settings is respected."""
        mock_settings.COCKROACHDB = {"REGION_HEADER": "X-My-Region"}
        captured_region: str | None = None

        def get_response(request: FakeRequest) -> MagicMock:
            nonlocal captured_region
            captured_region = RegionContext.current()
            return MagicMock()

        middleware = CockroachDBMiddleware(get_response)
        request = FakeRequest(
            method="POST",
            meta={"HTTP_X_MY_REGION": "eu-west1"},
        )

        middleware(request)
        assert captured_region == "eu-west1"

    @patch("cockroachdb.django.middleware.settings")
    def test_missing_header_no_region_set(self, mock_settings: MagicMock) -> None:
        """When the region header is absent, RegionContext remains None."""
        mock_settings.COCKROACHDB = {}
        captured_region: str | None = "sentinel"

        def get_response(request: FakeRequest) -> MagicMock:
            nonlocal captured_region
            captured_region = RegionContext.current()
            return MagicMock()

        middleware = CockroachDBMiddleware(get_response)
        request = FakeRequest(method="POST", meta={})

        middleware(request)
        assert captured_region is None

    @patch("cockroachdb.django.middleware.settings")
    def test_region_and_follower_read_together(self, mock_settings: MagicMock) -> None:
        """Both RegionContext and FollowerReadContext are active on GET with region."""
        mock_settings.COCKROACHDB = {}
        captured_region: str | None = None
        follower_active = False

        def get_response(request: FakeRequest) -> MagicMock:
            nonlocal captured_region, follower_active
            captured_region = RegionContext.current()
            follower_active = FollowerReadContext.is_active()
            return MagicMock()

        middleware = CockroachDBMiddleware(get_response)
        request = FakeRequest(
            method="GET",
            meta={"HTTP_X_COCKROACHDB_REGION": "us-west2"},
        )

        middleware(request)
        assert captured_region == "us-west2"
        assert follower_active is True

    @patch("cockroachdb.django.middleware.settings")
    def test_context_cleaned_up_after_request(self, mock_settings: MagicMock) -> None:
        """Contexts are cleaned up after the request completes."""
        mock_settings.COCKROACHDB = {}

        middleware = CockroachDBMiddleware(lambda r: MagicMock())
        request = FakeRequest(
            method="GET",
            meta={"HTTP_X_COCKROACHDB_REGION": "us-east1"},
        )

        middleware(request)

        assert RegionContext.current() is None
        assert FollowerReadContext.is_active() is False

    @patch("cockroachdb.django.middleware.settings")
    def test_custom_follower_read_safe_methods(self, mock_settings: MagicMock) -> None:
        """Custom FOLLOWER_READ_SAFE_METHODS disables follower read for GET."""
        mock_settings.COCKROACHDB = {"FOLLOWER_READ_SAFE_METHODS": []}
        follower_active = False

        def get_response(request: FakeRequest) -> MagicMock:
            nonlocal follower_active
            follower_active = FollowerReadContext.is_active()
            return MagicMock()

        middleware = CockroachDBMiddleware(get_response)
        request = FakeRequest(method="GET")

        middleware(request)
        assert follower_active is False
