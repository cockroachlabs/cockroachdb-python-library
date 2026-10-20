"""CDC changefeed webhook example.

Demonstrates CockroachDB's Change Data Capture (CDC) webhook integration:
    - ``@changefeed_handler`` decorator to define event handlers
    - ``ChangefeedHandlerRegistry`` for handler discovery and dispatch
    - ``create_fastapi_router()`` to generate a FastAPI router
    - FastAPI application setup with CDC endpoints

CockroachDB CDC sends JSON payloads to webhook URLs when rows change.
This library provides a structured way to register handlers and route
those payloads to the right function.

Prerequisites:
    pip install cockroachdb cockroachdb-cdc fastapi uvicorn

Usage:
    # Start the server:
    uvicorn examples.cdc_webhook:app --host 0.0.0.0 --port 8000

    # Then create a changefeed in CockroachDB:
    # CREATE CHANGEFEED FOR TABLE orders
    #     INTO 'webhook-https://your-host:8000/webhooks/orders?insecure_tls_skip_verify=true'
    #     WITH updated, resolved;

Example webhook JSON payload from CockroachDB::

    {
        "payload": [
            {
                "after": {"id": 1, "customer": "Alice", "total": 99.99, "status": "pending"},
                "key": [1],
                "topic": "orders",
                "updated": "1234567890.0000000000"
            }
        ],
        "length": 1
    }
"""

from __future__ import annotations

import logging

from cockroachdb import changefeed_handler
from cockroachdb.cdc import (
    ChangefeedHandlerRegistry,
    create_fastapi_router,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Define handlers with @changefeed_handler
# ---------------------------------------------------------------------------


@changefeed_handler(table="orders", operations=["insert"])
def on_new_order(event) -> None:
    """Handle new order insertions.

    Called when a row is inserted into the ``orders`` table.
    The ``event`` is a ``ChangefeedEvent`` with:
        - event.operation — CDCOperation.INSERT
        - event.table — "orders"
        - event.after — dict with the new row data
        - event.before — None (it's an insert)
        - event.key — primary key columns
        - event.timestamp — wall-clock time
    """
    logger.info(
        "New order: id=%s, customer=%s, total=%s",
        event.after.get("id"),
        event.after.get("customer"),
        event.after.get("total"),
    )


@changefeed_handler(table="orders", operations=["update"])
def on_order_updated(event) -> None:
    """Handle order updates.

    Both ``event.before`` and ``event.after`` are populated for updates,
    letting you compute what changed.
    """
    logger.info(
        "Order updated: id=%s, old_status=%s, new_status=%s",
        event.after.get("id"),
        event.before.get("status") if event.before else "unknown",
        event.after.get("status"),
    )


@changefeed_handler(table="orders", operations=["delete"])
def on_order_deleted(event) -> None:
    """Handle order deletions.

    For deletes, ``event.after`` is None and ``event.before`` contains
    the row that was deleted.
    """
    logger.info(
        "Order deleted: id=%s",
        event.before.get("id") if event.before else "unknown",
    )


@changefeed_handler(
    table="inventory",
    operations=["insert", "update"],
    endpoint="/webhooks/inventory-changes",  # Custom endpoint path
)
def on_inventory_change(event) -> None:
    """Handle inventory changes with a custom endpoint path.

    By default, the endpoint is ``/webhooks/{table}``. You can override
    it with the ``endpoint`` parameter for more control.
    """
    logger.info(
        "Inventory change: product=%s, operation=%s",
        event.after.get("product_id") if event.after else "unknown",
        event.operation,
    )


# ---------------------------------------------------------------------------
# 2. Register handlers in the registry
# ---------------------------------------------------------------------------

registry = ChangefeedHandlerRegistry()

# Register each handler — the registry reads the __crdb_changefeed__
# metadata attached by the decorator
registry.register(on_new_order)
registry.register(on_order_updated)
registry.register(on_order_deleted)
registry.register(on_inventory_change)


# ---------------------------------------------------------------------------
# 3. Create FastAPI router and application
# ---------------------------------------------------------------------------

# create_fastapi_router() generates POST endpoints for each registered
# handler. It parses the incoming JSON webhook payload, constructs
# ChangefeedEvent instances, and dispatches them to the right handler.
cdc_router = create_fastapi_router(
    registry,
    prefix="",  # URL prefix (e.g., "/api/v1")
    tags=["cdc"],  # OpenAPI tags
)

# Build the FastAPI app
try:
    from fastapi import FastAPI

    app = FastAPI(
        title="CockroachDB CDC Webhook Server",
        description="Receives changefeed webhooks from CockroachDB",
        version="1.0.0",
    )

    # Mount the CDC router
    app.include_router(cdc_router)

    @app.get("/health")
    def health_check():
        """Health check endpoint for load balancer probes."""
        return {"status": "healthy", "handlers": len(registry.get_handlers())}

except ImportError:
    app = None
    print("FastAPI not installed — run: pip install fastapi uvicorn")


# ---------------------------------------------------------------------------
# 4. Standalone testing
# ---------------------------------------------------------------------------


def demonstrate_handler_metadata() -> None:
    """Inspect handler metadata without running the server."""
    print("--- Registered CDC handlers ---")

    for endpoint, info in registry.get_handlers().items():
        print(f"  Endpoint: {endpoint}")
        print(f"    Table: {info['table']}")
        print(f"    Operations: {info['operations']}")
        print(f"    Handler: {info['fn'].__name__}")
        print()


if __name__ == "__main__":
    print("=== CockroachDB CDC Webhook Examples ===\n")

    demonstrate_handler_metadata()

    if app is not None:
        print("To start the webhook server, run:")
        print("  uvicorn examples.cdc_webhook:app --host 0.0.0.0 --port 8000")
        print()
        print("Then create a changefeed in CockroachDB SQL shell:")
        print("  CREATE CHANGEFEED FOR TABLE orders")
        print(
            "    INTO 'webhook-https://localhost:8000/webhooks/orders"
            "?insecure_tls_skip_verify=true'"
        )
        print("    WITH updated, resolved;")
    else:
        print("Install FastAPI to run the webhook server:")
        print("  pip install cockroachdb-cdc[fastapi] uvicorn")

    print("\nDone.")
