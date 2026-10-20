"""Cockroach Aegis — autonomous-ops findings & recommendations in your app.

Aegis surfaces cluster findings/recommendations to the application and lets the
app emit operational signals (``AppEvent``) back. This module ships a
protocol (:class:`AegisClient`), value types, an in-memory
:class:`SimulatedAegisClient` for development and tests, an
:class:`HttpAegisClient` stub for the not-yet-public API, and
:class:`AegisExhaust`, which forwards retry/circuit signals as events.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cockroachdb.continuum.mcp import McpClient


@dataclass(frozen=True)
class Finding:
    """An observation about the cluster surfaced to the application."""

    id: str
    severity: str
    title: str
    detail: str


@dataclass(frozen=True)
class Recommendation:
    """A suggested action to improve cluster health or workload behavior."""

    id: str
    title: str
    rationale: str
    action: str


@dataclass(frozen=True)
class AppEvent:
    """An application-level operational signal emitted to Aegis."""

    kind: str
    source: str
    attrs: Mapping[str, Any] = field(default_factory=dict)
    epoch_millis: int = 0

    @classmethod
    def now(cls, kind: str, source: str, attrs: Mapping[str, Any] | None = None) -> AppEvent:
        """Build an event stamped with the current wall-clock time in millis."""
        return cls(
            kind=kind,
            source=source,
            attrs=dict(attrs or {}),
            epoch_millis=int(time.time() * 1000),
        )


@dataclass(frozen=True)
class AegisConfig:
    """Configuration for constructing an :class:`AegisClient`.

    A ``None`` ``endpoint`` selects the in-memory simulated client.
    """

    enabled: bool = True
    endpoint: str | None = None
    token: str | None = None


@runtime_checkable
class AegisClient(Protocol):
    """Protocol for an Aegis backend."""

    def findings(self) -> list[Finding]: ...

    def recommendations(self) -> list[Recommendation]: ...

    def emit(self, event: AppEvent) -> None: ...


class SimulatedAegisClient:
    """In-memory Aegis backend for development and tests.

    Returns a small canned set of findings/recommendations and records every
    emitted event so tests can assert on the exhaust via :meth:`emitted_events`.
    """

    def __init__(self) -> None:
        self._emitted: list[AppEvent] = []
        self._findings: list[Finding] = [
            Finding(
                "f-hotspot-001",
                "warning",
                "Range hotspot detected",
                "A range is receiving disproportionate traffic relative to its peers.",
            ),
            Finding(
                "f-retry-002",
                "info",
                "Elevated serialization retries",
                "Serialization retries are above baseline for the last hour.",
            ),
        ]
        self._recommendations: list[Recommendation] = [
            Recommendation(
                "r-split-001",
                "Relieve the hot range",
                "Traffic is concentrated on a single range.",
                "Introduce a hash-sharded index or split the range.",
            ),
            Recommendation(
                "r-qos-002",
                "Tag background workloads",
                "Batch jobs are competing with OLTP for resources.",
                "Run batch work inside vcluster(..., priority=Priority.LOW).",
            ),
        ]

    def findings(self) -> list[Finding]:
        return list(self._findings)

    def recommendations(self) -> list[Recommendation]:
        return list(self._recommendations)

    def emit(self, event: AppEvent) -> None:
        self._emitted.append(event)

    def emitted_events(self) -> list[AppEvent]:
        """All events emitted so far, in order."""
        return list(self._emitted)


class HttpAegisClient:
    """Stub for the HTTP Aegis backend. The Aegis API is not yet public."""

    _MESSAGE = "Aegis API not yet public"

    def __init__(self, config: AegisConfig) -> None:
        self._config = config

    def findings(self) -> list[Finding]:
        raise NotImplementedError(self._MESSAGE)

    def recommendations(self) -> list[Recommendation]:
        raise NotImplementedError(self._MESSAGE)

    def emit(self, event: AppEvent) -> None:
        raise NotImplementedError(self._MESSAGE)


class AegisExhaust:
    """Forwards application operational signals to an :class:`AegisClient`.

    Feeds retry attempts, retry exhaustion, and circuit-breaker trips into Aegis
    as :class:`AppEvent`s. Attach it to your retry/circuit instrumentation.
    """

    def __init__(self, client: AegisClient, source: str = "cockroachdb-python") -> None:
        self._client = client
        self._source = source

    def record_retry(self, operation: str, attempt: int, sqlstate: str | None = None) -> None:
        """Record a single retry attempt for ``operation``."""
        self._client.emit(
            AppEvent.now(
                "retry",
                self._source,
                {"operation": operation, "attempt": attempt, "sqlstate": sqlstate or ""},
            )
        )

    def record_retry_exhausted(
        self, operation: str, attempts: int, sqlstate: str | None = None
    ) -> None:
        """Record that ``operation`` exhausted its retry budget."""
        self._client.emit(
            AppEvent.now(
                "retry_exhausted",
                self._source,
                {"operation": operation, "attempts": attempts, "sqlstate": sqlstate or ""},
            )
        )

    def record_circuit_open(self, operation: str, consecutive_failures: int) -> None:
        """Record that the circuit breaker opened for ``operation``."""
        self._client.emit(
            AppEvent.now(
                "circuit_open",
                self._source,
                {"operation": operation, "consecutive_failures": consecutive_failures},
            )
        )


def make_aegis(config: AegisConfig) -> AegisClient:
    """Return an Aegis client for ``config``.

    Selects :class:`SimulatedAegisClient` when ``endpoint`` is ``None``,
    otherwise the :class:`HttpAegisClient` stub.
    """
    if config.endpoint is None:
        return SimulatedAegisClient()
    return HttpAegisClient(config)


@dataclass(frozen=True)
class McpToolNames:
    """Maps Aegis operations to the tool names an MCP server advertises.

    The Cockroach Continuum MCP tool contract is not pinned here: names differ by
    server and may change. Discover them with :meth:`McpClient.list_tools` and set
    the ones you need. An unset name raises rather than guessing.
    """

    findings: str = ""
    recommendations: str = ""
    emit: str = ""


class McpAegisClient:
    """Adapts an :class:`~cockroachdb.continuum.mcp.McpClient` to :class:`AegisClient`.

    Aegis is reachable read-only over the Cockroach Continuum Cloud MCP server.
    This adapter calls the configured tools and parses their text content as JSON
    into :class:`Finding`/:class:`Recommendation`.
    """

    def __init__(self, client: McpClient, tools: McpToolNames) -> None:
        self._mcp = client
        self._tools = tools

    def findings(self) -> list[Finding]:
        rows = self._read_list(self._tools.findings, "findings")
        return [
            Finding(
                r.get("id", ""), r.get("severity", ""), r.get("title", ""), r.get("detail", "")
            )
            for r in rows
        ]

    def recommendations(self) -> list[Recommendation]:
        rows = self._read_list(self._tools.recommendations, "recommendations")
        return [
            Recommendation(
                r.get("id", ""),
                r.get("title", ""),
                r.get("rationale", r.get("detail", "")),
                r.get("action", r.get("suggestedAction", "")),
            )
            for r in rows
        ]

    def emit(self, event: AppEvent) -> None:
        if not self._tools.emit:
            msg = "aegis: MCP tool name not configured: emit"
            raise ValueError(msg)
        res = self._mcp.call_tool(
            self._tools.emit,
            {
                "kind": event.kind,
                "source": event.source,
                "attrs": dict(event.attrs),
                "epochMillis": event.epoch_millis,
            },
        )
        if res.is_error:
            msg = f"aegis: emit tool reported error: {res.text()}"
            raise RuntimeError(msg)

    def _read_list(self, tool: str, what: str) -> list[dict[str, Any]]:
        if not tool:
            msg = f"aegis: MCP tool name not configured: {what}"
            raise ValueError(msg)
        res = self._mcp.call_tool(tool)
        if res.is_error:
            msg = f"aegis: {what} tool reported error: {res.text()}"
            raise RuntimeError(msg)
        text = res.text()
        if not text:
            return []
        data = json.loads(text)
        if not isinstance(data, list):
            msg = f"aegis: {what}: expected a JSON array"
            raise ValueError(msg)
        return data
