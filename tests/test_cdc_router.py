"""Tests for cockroachdb.cdc.router — FastAPI and Flask router factories."""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from cockroachdb.cdc.handler import ChangefeedHandlerRegistry


def _make_handler(table="orders", operations=None, endpoint="/webhooks/orders"):
    """Create a fake handler function with __crdb_changefeed__ metadata."""
    operations = operations or ["insert"]

    def handler(event):
        return {"handled": event.table}

    handler.__crdb_changefeed__ = {
        "table": table,
        "operations": operations,
        "endpoint": endpoint,
    }
    return handler


def _make_fastapi_modules():
    """Create mock fastapi modules that behave like real imports."""
    mock_router_instance = MagicMock()
    mock_api_router = MagicMock(return_value=mock_router_instance)
    mock_request = MagicMock()
    mock_json_response = MagicMock()

    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.APIRouter = mock_api_router
    fastapi_mod.Request = mock_request

    responses_mod = types.ModuleType("fastapi.responses")
    responses_mod.JSONResponse = mock_json_response
    fastapi_mod.responses = responses_mod

    return fastapi_mod, responses_mod, mock_router_instance


def _make_flask_modules():
    """Create mock flask module that behaves like real imports."""
    mock_bp_instance = MagicMock()
    mock_blueprint = MagicMock(return_value=mock_bp_instance)
    mock_request = MagicMock()
    mock_response = MagicMock()

    flask_mod = types.ModuleType("flask")
    flask_mod.Blueprint = mock_blueprint
    flask_mod.request = mock_request
    flask_mod.Response = mock_response

    return flask_mod, mock_bp_instance


class TestCreateFastapiRouter:
    """Tests for create_fastapi_router()."""

    def test_returns_api_router_instance(self):
        """create_fastapi_router returns a FastAPI APIRouter."""
        fastapi_mod, responses_mod, mock_router = _make_fastapi_modules()

        with patch.dict(
            sys.modules,
            {
                "fastapi": fastapi_mod,
                "fastapi.responses": responses_mod,
            },
        ):
            # Re-import to pick up the mocked modules
            import cockroachdb.cdc.router as router_mod

            importlib.reload(router_mod)

            registry = ChangefeedHandlerRegistry()
            registry.register(_make_handler())
            result = router_mod.create_fastapi_router(registry)

        assert result is mock_router

    def test_registers_post_route_for_each_handler(self):
        """Each handler endpoint gets a POST route added."""
        fastapi_mod, responses_mod, mock_router = _make_fastapi_modules()

        with patch.dict(
            sys.modules,
            {
                "fastapi": fastapi_mod,
                "fastapi.responses": responses_mod,
            },
        ):
            import cockroachdb.cdc.router as router_mod

            importlib.reload(router_mod)

            registry = ChangefeedHandlerRegistry()
            registry.register(_make_handler(table="t1", endpoint="/e1"))
            registry.register(_make_handler(table="t2", endpoint="/e2"))
            router_mod.create_fastapi_router(registry)

        route_calls = mock_router.add_api_route.call_args_list
        endpoints_registered = [c[0][0] for c in route_calls]
        assert "/e1" in endpoints_registered
        assert "/e2" in endpoints_registered

    def test_raises_import_error_without_fastapi(self):
        """ImportError is raised when FastAPI is not installed."""
        # Temporarily remove fastapi from sys.modules if present
        saved = sys.modules.pop("fastapi", None)
        saved_resp = sys.modules.pop("fastapi.responses", None)
        try:
            sys.modules["fastapi"] = None  # type: ignore[assignment]
            import cockroachdb.cdc.router as router_mod

            importlib.reload(router_mod)

            registry = ChangefeedHandlerRegistry()
            registry.register(_make_handler())

            with pytest.raises(ImportError, match="FastAPI"):
                router_mod.create_fastapi_router(registry)
        finally:
            sys.modules.pop("fastapi", None)
            if saved is not None:
                sys.modules["fastapi"] = saved
            if saved_resp is not None:
                sys.modules["fastapi.responses"] = saved_resp


class TestCreateFlaskBlueprint:
    """Tests for create_flask_blueprint()."""

    def test_returns_blueprint_instance(self):
        """create_flask_blueprint returns a Flask Blueprint."""
        flask_mod, mock_bp = _make_flask_modules()

        with patch.dict(sys.modules, {"flask": flask_mod}):
            import cockroachdb.cdc.router as router_mod

            importlib.reload(router_mod)

            registry = ChangefeedHandlerRegistry()
            registry.register(_make_handler())
            result = router_mod.create_flask_blueprint(registry)

        assert result is mock_bp

    def test_registers_routes_for_each_handler(self):
        """Each handler endpoint gets a route added to the blueprint."""
        flask_mod, mock_bp = _make_flask_modules()

        with patch.dict(sys.modules, {"flask": flask_mod}):
            import cockroachdb.cdc.router as router_mod

            importlib.reload(router_mod)

            registry = ChangefeedHandlerRegistry()
            registry.register(_make_handler(table="t1", endpoint="/e1"))
            registry.register(_make_handler(table="t2", endpoint="/e2"))
            router_mod.create_flask_blueprint(registry)

        route_calls = mock_bp.add_url_rule.call_args_list
        endpoints_registered = [c[0][0] for c in route_calls]
        assert "/e1" in endpoints_registered
        assert "/e2" in endpoints_registered

    def test_raises_import_error_without_flask(self):
        """ImportError is raised when Flask is not installed."""
        saved = sys.modules.pop("flask", None)
        try:
            sys.modules["flask"] = None  # type: ignore[assignment]
            import cockroachdb.cdc.router as router_mod

            importlib.reload(router_mod)

            registry = ChangefeedHandlerRegistry()
            registry.register(_make_handler())

            with pytest.raises(ImportError, match="Flask"):
                router_mod.create_flask_blueprint(registry)
        finally:
            sys.modules.pop("flask", None)
            if saved is not None:
                sys.modules["flask"] = saved
