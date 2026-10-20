"""Minimal Model Context Protocol (MCP) client over the Streamable HTTP transport.

Implements just enough of the 2025-06-18 spec to discover and call tools on a
remote MCP server (for example the Cockroach Continuum Cloud MCP server): the
initialize handshake, ``tools/list``, and ``tools/call``. MCP is a public,
versioned protocol, so unlike the not-yet-public Aegis REST API this speaks the
real wire format.

The HTTP client uses only the standard library and accepts an injectable
transport for tests; a ``None`` endpoint selects an in-memory
:class:`SimulatedMcpClient`.
"""

from __future__ import annotations

import contextlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from itertools import count
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping

PROTOCOL_VERSION = "2025-06-18"

# A transport maps (method, url, headers, body) -> (status, response_headers, text).
McpTransport = (
    "Callable[[str, str, Mapping[str, str], str | None], tuple[int, Mapping[str, str], str]]"
)


@dataclass(frozen=True)
class Tool:
    """A tool advertised by an MCP server."""

    name: str
    title: str = ""
    description: str = ""
    input_schema: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CallResult:
    """The result of a ``tools/call``."""

    content: tuple[dict[str, Any], ...] = ()
    structured_content: Mapping[str, Any] | None = None
    is_error: bool = False

    def text(self) -> str:
        """Concatenated text of all text content blocks."""
        return "".join(c.get("text", "") for c in self.content if c.get("type") == "text")


@dataclass(frozen=True)
class McpConfig:
    """Configuration for constructing an MCP client.

    A ``None`` ``endpoint`` selects the in-memory simulated client.
    """

    enabled: bool = True
    endpoint: str | None = None
    token: str | None = None
    client_name: str = "cockroachdb-python"
    client_version: str = "0.1"


@runtime_checkable
class McpClient(Protocol):
    """Protocol for an MCP client."""

    def list_tools(self) -> list[Tool]: ...

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> CallResult: ...


def _urllib_transport(
    method: str, url: str, headers: Mapping[str, str], body: str | None
) -> tuple[int, Mapping[str, str], str]:
    """Default transport backed by :mod:`urllib.request` (no extra dependency)."""
    data = body.encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read().decode("utf-8", "replace")


def _extract_sse(body: str) -> str:
    """Concatenate the ``data:`` payloads of an SSE body into one message."""
    return "".join(line[5:].strip() for line in body.splitlines() if line.startswith("data:"))


class HttpMcpClient:
    """HTTP-backed MCP client speaking the Streamable HTTP transport.

    Lazily performs the initialize handshake before the first tools call.
    """

    def __init__(self, config: McpConfig, transport: McpTransport | None = None) -> None:
        self._endpoint = config.endpoint
        self._token = config.token
        self._name = config.client_name
        self._version = config.client_version
        self._transport = transport or _urllib_transport
        self._ids = count(1)
        self._session_id: str | None = None
        self._init = False

    def list_tools(self) -> list[Tool]:
        self._ensure_init()
        result = self._call("tools/list", {})
        return [
            Tool(
                name=t["name"],
                title=t.get("title", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in result.get("tools", [])
        ]

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> CallResult:
        self._ensure_init()
        result = self._call("tools/call", {"name": name, "arguments": dict(arguments or {})})
        return CallResult(
            content=tuple(result.get("content", [])),
            structured_content=result.get("structuredContent"),
            is_error=bool(result.get("isError", False)),
        )

    def _ensure_init(self) -> None:
        if self._init:
            return
        self._call(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": self._name, "version": self._version},
            },
        )
        with contextlib.suppress(Exception):  # a rejected notification must not block us
            self._notify("notifications/initialized")
        self._init = True

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        if self._session_id:
            h["Mcp-Session-Id"] = self._session_id
        if self._init:
            h["MCP-Protocol-Version"] = PROTOCOL_VERSION
        return h

    def _post(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        status, resp_headers, text = self._transport(
            "POST", self._endpoint or "", self._headers(), json.dumps(payload)
        )
        for key, value in resp_headers.items():
            if key.lower() == "mcp-session-id" and value:
                self._session_id = value
        if status == 202:
            return None
        if not 200 <= status < 300:
            raise RuntimeError(f"mcp: HTTP {status}: {text[:200]}")
        ctype = next((v for k, v in resp_headers.items() if k.lower() == "content-type"), "")
        if ctype.startswith("text/event-stream"):
            text = _extract_sse(text)
        return json.loads(text) if text else {}

    def _call(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params}
        resp = self._post(payload)
        if resp is None:
            raise RuntimeError(f"mcp: {method}: unexpected empty response")
        if resp.get("error"):
            err = resp["error"]
            raise RuntimeError(
                f"mcp: {method}: server error {err.get('code')}: {err.get('message')}"
            )
        return resp.get("result") or {}

    def _notify(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method})


class SimulatedMcpClient:
    """In-memory MCP client for development and tests.

    Advertises a small canned tool set and echoes tool calls, so code that drives
    an MCP server runs offline. Records every call for assertions via :meth:`calls`.
    """

    def __init__(self) -> None:
        self._tools = [
            Tool("ping", "Ping", "Health check; returns pong."),
            Tool("echo", "Echo", "Echoes its arguments as JSON text."),
        ]
        self._calls: list[tuple[str, dict[str, Any]]] = []

    def list_tools(self) -> list[Tool]:
        return list(self._tools)

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> CallResult:
        args = dict(arguments or {})
        self._calls.append((name, args))
        if name == "ping":
            return CallResult(content=({"type": "text", "text": "pong"},))
        return CallResult(content=({"type": "text", "text": json.dumps(args)},))

    def calls(self) -> list[tuple[str, dict[str, Any]]]:
        """Recorded (name, arguments) tool calls, in order."""
        return list(self._calls)


def make_mcp(config: McpConfig, transport: McpTransport | None = None) -> McpClient:
    """Return an MCP client for ``config``.

    Selects :class:`SimulatedMcpClient` when ``endpoint`` is ``None``, otherwise an
    :class:`HttpMcpClient`.
    """
    if config.endpoint is None:
        return SimulatedMcpClient()
    return HttpMcpClient(config, transport)
