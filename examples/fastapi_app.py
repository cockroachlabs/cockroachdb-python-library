"""Complete FastAPI application example.

Demonstrates a production-style FastAPI app combining multiple
CockroachDB library features:
    - ASGI middleware for automatic region context propagation
    - Retry-decorated endpoints for write operations
    - Follower reads for low-latency GET endpoints
    - CDC webhook router mounted as a sub-router
    - Health check endpoint

Prerequisites:
    pip install cockroachdb cockroachdb-core cockroachdb-cdc[fastapi] \
                cockroachdb-sqlalchemy fastapi uvicorn

Usage:
    uvicorn examples.fastapi_app:app --host 0.0.0.0 --port 8000

    # Send a request with a region header:
    curl -H "X-CockroachDB-Region: us-east1" http://localhost:8000/orders

    # Health check:
    curl http://localhost:8000/health
"""

from __future__ import annotations

import logging
from typing import Any

from cockroachdb import CockroachDBRetryExhausted, changefeed_handler, crdb_retry
from cockroachdb.cdc import ChangefeedHandlerRegistry, create_fastapi_router
from cockroachdb.core import FollowerReadContext, RegionContext
from cockroachdb.core.middleware import CockroachDBASGIMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = "postgresql://root@localhost:26257/defaultdb"


# ---------------------------------------------------------------------------
# CDC Handlers
# ---------------------------------------------------------------------------


@changefeed_handler(table="orders", operations=["insert"])
def on_new_order(event) -> None:
    """Process new order events from CockroachDB CDC."""
    logger.info("New order received: %s", event.after)


@changefeed_handler(table="orders", operations=["update"])
def on_order_status_change(event) -> None:
    """Process order status changes."""
    logger.info(
        "Order %s status changed: %s -> %s",
        event.after.get("id") if event.after else "?",
        event.before.get("status") if event.before else "?",
        event.after.get("status") if event.after else "?",
    )


# Register CDC handlers
cdc_registry = ChangefeedHandlerRegistry()
cdc_registry.register(on_new_order)
cdc_registry.register(on_order_status_change)


# ---------------------------------------------------------------------------
# Retry-safe database operations
# ---------------------------------------------------------------------------


@crdb_retry(
    max_retries=3, on_retry=lambda attempt, err: logger.warning("Retry %d: %s", attempt, err)
)
def create_order(order_data: dict[str, Any]) -> dict[str, Any]:
    """Create an order with automatic retry on serialization conflicts.

    In a real app, this would use psycopg or SQLAlchemy to execute
    the INSERT. The ``@crdb_retry`` decorator re-executes the entire
    function if CockroachDB reports a serialization conflict.
    """
    # Placeholder — replace with actual database logic
    logger.info("Creating order: %s", order_data)
    return {"id": 1, **order_data, "status": "created"}


@crdb_retry(max_retries=5, base_delay=0.2)
def update_order_status(order_id: int, status: str) -> dict[str, Any]:
    """Update order status with aggressive retry settings."""
    logger.info("Updating order %d to status %s", order_id, status)
    return {"id": order_id, "status": status}


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
except ImportError:
    raise ImportError("FastAPI is required. Install with: pip install fastapi uvicorn")


app = FastAPI(
    title="CockroachDB Example API",
    description="A production-style API demonstrating CockroachDB Python Library features",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# 1. ASGI Middleware — automatic region extraction from headers
# ---------------------------------------------------------------------------

# The middleware reads the X-CockroachDB-Region header and sets
# RegionContext for the entire request lifecycle. Downstream handlers
# and database operations automatically inherit the region.
app.add_middleware(
    CockroachDBASGIMiddleware,
    header_name="x-cockroachdb-region",
)


# ---------------------------------------------------------------------------
# 2. Mount CDC webhook router
# ---------------------------------------------------------------------------

cdc_router = create_fastapi_router(cdc_registry, prefix="/cdc", tags=["cdc"])
app.include_router(cdc_router)


# ---------------------------------------------------------------------------
# 3. Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint.

    Returns the current region (if set by middleware), follower read
    status, and registered CDC handler count.
    """
    return {
        "status": "healthy",
        "current_region": RegionContext.current(),
        "follower_read_active": FollowerReadContext.is_active(),
        "cdc_handlers": len(cdc_registry.get_handlers()),
    }


# ---------------------------------------------------------------------------
# 4. Read endpoints — use follower reads for low latency
# ---------------------------------------------------------------------------


@app.get("/orders", tags=["orders"])
async def list_orders(request: Request):
    """List orders using follower reads.

    Follower reads allow any CockroachDB replica to serve the query,
    reducing read latency in multi-region deployments. The trade-off
    is slightly stale data (typically < 5 seconds).

    The X-CockroachDB-Region header (if present) is automatically
    picked up by the ASGI middleware.
    """
    region = RegionContext.current()

    with FollowerReadContext.scoped():
        # In a real app, query the database here.
        # The FollowerReadContext signals the template/session layer
        # to inject AS OF SYSTEM TIME follower_read_timestamp().
        return {
            "region": region,
            "follower_read": True,
            "orders": [
                {"id": 1, "customer": "Alice", "total": 99.99, "status": "shipped"},
                {"id": 2, "customer": "Bob", "total": 149.50, "status": "pending"},
            ],
        }


@app.get("/orders/{order_id}", tags=["orders"])
async def get_order(order_id: int):
    """Get a single order by ID using follower reads."""
    region = RegionContext.current()

    with FollowerReadContext.scoped():
        return {
            "id": order_id,
            "region": region,
            "follower_read": True,
            "customer": "Alice",
            "total": 99.99,
            "status": "shipped",
        }


# ---------------------------------------------------------------------------
# 5. Write endpoints — use retry decorator
# ---------------------------------------------------------------------------


@app.post("/orders", tags=["orders"], status_code=201)
async def create_order_endpoint(request: Request):
    """Create a new order with automatic retry.

    Write operations use ``@crdb_retry`` to handle serialization
    conflicts transparently. The region context (from the middleware)
    ensures the write goes to the correct region.
    """
    body = await request.json()
    region = RegionContext.current()

    try:
        order = create_order(body)
        return {
            "region": region,
            "order": order,
        }
    except CockroachDBRetryExhausted:
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable — retries exhausted",
        )


@app.put("/orders/{order_id}/status", tags=["orders"])
async def update_status_endpoint(order_id: int, request: Request):
    """Update order status with retry safety."""
    body = await request.json()
    status = body.get("status", "unknown")

    try:
        result = update_order_status(order_id, status)
        return {"region": RegionContext.current(), "order": result}
    except CockroachDBRetryExhausted:
        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable — retries exhausted",
        )


# ---------------------------------------------------------------------------
# 6. Region-aware endpoint
# ---------------------------------------------------------------------------


@app.get("/region", tags=["system"])
async def get_current_region():
    """Show the active region context.

    The region is automatically set by the ASGI middleware from the
    ``X-CockroachDB-Region`` header. If no header is present, the
    region is None.
    """
    region = RegionContext.current()
    return {
        "region": region,
        "message": f"Serving from region: {region}" if region else "No region set",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== CockroachDB FastAPI Application ===\n")
    print("Start the server with:")
    print("  uvicorn examples.fastapi_app:app --host 0.0.0.0 --port 8000\n")
    print("Endpoints:")
    print("  GET  /health                — Health check")
    print("  GET  /orders                — List orders (follower read)")
    print("  GET  /orders/{id}           — Get order (follower read)")
    print("  POST /orders                — Create order (retry-safe)")
    print("  PUT  /orders/{id}/status    — Update status (retry-safe)")
    print("  GET  /region                — Show current region context")
    print("  POST /cdc/webhooks/orders   — CDC webhook endpoint")
    print()
    print("Send a region header:")
    print('  curl -H "X-CockroachDB-Region: us-east1" http://localhost:8000/orders')
