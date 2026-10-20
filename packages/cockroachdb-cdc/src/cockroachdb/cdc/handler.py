"""Handler registry for CockroachDB CDC changefeed webhooks."""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cockroachdb.cdc.metrics import CDCMetrics, NoopCDCMetrics
from cockroachdb.cdc.models import ChangefeedEvent, ChangefeedPayload

logger = logging.getLogger(__name__)

HandlerFn = Callable[[ChangefeedEvent[dict[str, Any]]], Any]


@dataclass
class _HandlerEntry:
    """Internal record for a registered handler."""

    fn: HandlerFn
    table: str
    operations: list[str]
    endpoint: str


class ChangefeedHandlerRegistry:
    """Discovers and dispatches CDC webhook events to registered handlers.

    Handlers are functions decorated with :func:`cockroachdb.changefeed_handler`
    or registered manually via :meth:`register`.  The registry maps webhook
    endpoint paths to their handler functions so that framework routers
    (FastAPI, Flask) can dispatch incoming payloads.

    Example::

        from cockroachdb import changefeed_handler
        from cockroachdb.cdc import ChangefeedHandlerRegistry

        @changefeed_handler(table="orders", operations=["insert"])
        def on_new_order(event):
            print(f"New order: {event.after}")

        registry = ChangefeedHandlerRegistry()
        registry.register(on_new_order)
    """

    def __init__(self, metrics: CDCMetrics | None = None) -> None:
        self._handlers: dict[str, _HandlerEntry] = {}
        self._metrics: CDCMetrics = metrics or NoopCDCMetrics()

    def register(self, fn: HandlerFn) -> HandlerFn:
        """Register a handler function.

        The function must have been decorated with
        :func:`cockroachdb.changefeed_handler` so that ``__crdb_changefeed__``
        metadata is present.

        Args:
            fn: A decorated handler function.

        Returns:
            The same function, unmodified.

        Raises:
            ValueError: If the function lacks changefeed metadata or
                the endpoint is already registered.
        """
        meta: dict[str, Any] | None = getattr(fn, "__crdb_changefeed__", None)
        if meta is None:
            raise ValueError(
                f"Function {fn.__qualname__} is not decorated with @changefeed_handler"
            )

        entry = _HandlerEntry(
            fn=fn,
            table=meta["table"],
            operations=meta["operations"],
            endpoint=meta["endpoint"],
        )

        if entry.endpoint in self._handlers:
            existing = self._handlers[entry.endpoint]
            raise ValueError(
                f"Endpoint {entry.endpoint!r} already registered to {existing.fn.__qualname__}"
            )

        self._handlers[entry.endpoint] = entry
        logger.info(
            "Registered CDC handler %s for table=%s ops=%s endpoint=%s",
            fn.__qualname__,
            entry.table,
            entry.operations,
            entry.endpoint,
        )
        return fn

    async def dispatch(
        self,
        endpoint: str,
        payload: str | bytes | dict[str, Any],
    ) -> list[Any]:
        """Route an incoming webhook payload to the registered handler.

        Parses the raw payload, filters events by the handler's configured
        operations, and invokes the handler for each matching event.

        Args:
            endpoint: The webhook endpoint path (e.g. ``/webhooks/orders``).
            payload: Raw JSON body from the webhook request.

        Returns:
            List of handler return values (one per matched event).

        Raises:
            KeyError: If no handler is registered for the endpoint.
            ValueError: If the payload cannot be parsed.
        """
        entry = self._handlers.get(endpoint)
        if entry is None:
            raise KeyError(f"No handler registered for endpoint {endpoint!r}")

        parsed = ChangefeedPayload.parse(payload)
        results: list[Any] = []

        for event in parsed.events:
            if event.operation.value not in entry.operations:
                logger.debug(
                    "Skipping %s event for handler %s (not in %s)",
                    event.operation.value,
                    entry.fn.__qualname__,
                    entry.operations,
                )
                continue

            start = time.monotonic()
            try:
                if inspect.iscoroutinefunction(entry.fn):
                    result = await entry.fn(event)
                else:
                    result = entry.fn(event)
                results.append(result)
                duration_ms = (time.monotonic() - start) * 1000
                self._metrics.record_event(entry.table, event.operation.value, duration_ms)
                self._metrics.record_dispatch(entry.table, True)
            except Exception as exc:
                duration_ms = (time.monotonic() - start) * 1000
                self._metrics.record_event(entry.table, event.operation.value, duration_ms)
                self._metrics.record_dispatch(entry.table, False)
                self._metrics.record_error(entry.table, exc)
                raise

        return results

    def get_handlers(self) -> dict[str, dict[str, Any]]:
        """List all registered handlers with their metadata.

        Returns:
            Dict mapping endpoint paths to handler information including
            function name, table, and operations.
        """
        return {
            endpoint: {
                "function": entry.fn.__qualname__,
                "table": entry.table,
                "operations": entry.operations,
                "endpoint": entry.endpoint,
            }
            for endpoint, entry in self._handlers.items()
        }
