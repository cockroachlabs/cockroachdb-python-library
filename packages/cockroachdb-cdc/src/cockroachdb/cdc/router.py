"""Framework-specific routers for CockroachDB CDC webhook endpoints."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cockroachdb.cdc.handler import ChangefeedHandlerRegistry

logger = logging.getLogger(__name__)


def create_fastapi_router(
    registry: ChangefeedHandlerRegistry,
    *,
    prefix: str = "",
    tags: list[str] | None = None,
) -> Any:
    """Create a FastAPI ``APIRouter`` with webhook endpoints for all registered handlers.

    Each registered handler's endpoint becomes a POST route that accepts the
    CockroachDB webhook JSON body, dispatches it through the registry, and
    returns a 200 on success.

    Args:
        registry: The handler registry containing discovered handlers.
        prefix: Optional URL prefix for all routes.
        tags: Optional OpenAPI tags for the generated routes.

    Returns:
        A ``fastapi.APIRouter`` instance.

    Raises:
        ImportError: If FastAPI is not installed.
    """
    try:
        from fastapi import APIRouter, Request
        from fastapi.responses import JSONResponse
    except ImportError as exc:
        raise ImportError(
            "FastAPI is required for create_fastapi_router. "
            "Install it with: pip install cockroachdb-cdc[fastapi]"
        ) from exc

    router = APIRouter(prefix=prefix, tags=tags or ["cdc"])

    for endpoint, info in registry.get_handlers().items():

        def _make_handler(ep: str, info: Any) -> Any:
            async def webhook_handler(request: Request) -> JSONResponse:
                try:
                    body = await request.body()
                    results = await registry.dispatch(ep, body)
                    return JSONResponse(
                        content={"status": "ok", "processed": len(results)},
                        status_code=200,
                    )
                except KeyError as exc:
                    logger.error("CDC dispatch error: %s", exc)
                    return JSONResponse(
                        content={"status": "error", "detail": str(exc)},
                        status_code=404,
                    )
                except ValueError as exc:
                    logger.error("CDC payload error: %s", exc)
                    return JSONResponse(
                        content={"status": "error", "detail": str(exc)},
                        status_code=400,
                    )
                except Exception:
                    logger.exception("Unhandled error in CDC handler for %s", ep)
                    return JSONResponse(
                        content={"status": "error", "detail": "Internal server error"},
                        status_code=500,
                    )

            webhook_handler.__name__ = f"cdc_{info['table']}"
            webhook_handler.__qualname__ = f"cdc_{info['table']}"
            return webhook_handler

        handler = _make_handler(endpoint, info)
        router.add_api_route(
            endpoint,
            handler,
            methods=["POST"],
            summary=f"CDC webhook for {info['table']}",
        )

    return router


def create_flask_blueprint(
    registry: ChangefeedHandlerRegistry,
    *,
    name: str = "cdc",
    url_prefix: str = "",
) -> Any:
    """Create a Flask ``Blueprint`` with webhook endpoints for all registered handlers.

    Each registered handler's endpoint becomes a POST route that accepts the
    CockroachDB webhook JSON body, dispatches it through the registry, and
    returns a 200 on success.

    Args:
        registry: The handler registry containing discovered handlers.
        name: Blueprint name.
        url_prefix: URL prefix for the blueprint.

    Returns:
        A ``flask.Blueprint`` instance.

    Raises:
        ImportError: If Flask is not installed.
    """
    try:
        from flask import Blueprint, Response, request
    except ImportError as exc:
        raise ImportError(
            "Flask is required for create_flask_blueprint. "
            "Install it with: pip install cockroachdb-cdc[flask]"
        ) from exc

    bp = Blueprint(name, __name__, url_prefix=url_prefix)

    for endpoint, info in registry.get_handlers().items():

        def _make_handler(ep: str, info: Any) -> Any:
            def webhook_handler() -> Response:
                try:
                    body = request.get_data()
                    loop = _get_or_create_event_loop()
                    results = loop.run_until_complete(registry.dispatch(ep, body))
                    return Response(
                        response=json.dumps({"status": "ok", "processed": len(results)}),
                        status=200,
                        mimetype="application/json",
                    )
                except KeyError as exc:
                    logger.error("CDC dispatch error: %s", exc)
                    return Response(
                        response=json.dumps({"status": "error", "detail": str(exc)}),
                        status=404,
                        mimetype="application/json",
                    )
                except ValueError as exc:
                    logger.error("CDC payload error: %s", exc)
                    return Response(
                        response=json.dumps({"status": "error", "detail": str(exc)}),
                        status=400,
                        mimetype="application/json",
                    )
                except Exception:
                    logger.exception("Unhandled error in CDC handler for %s", ep)
                    return Response(
                        response=json.dumps(
                            {"status": "error", "detail": "Internal server error"}
                        ),
                        status=500,
                        mimetype="application/json",
                    )

            webhook_handler.__name__ = f"cdc_{info['table']}"
            webhook_handler.__qualname__ = f"cdc_{info['table']}"
            return webhook_handler

        handler = _make_handler(endpoint, info)
        bp.add_url_rule(endpoint, view_func=handler, methods=["POST"])

    return bp


def _get_or_create_event_loop() -> Any:
    """Get the running event loop or create a new one for sync Flask contexts."""
    import asyncio

    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
