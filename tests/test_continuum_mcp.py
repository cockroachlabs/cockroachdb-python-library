"""Tests for the Continuum MCP client — fakes only, no live server."""

from __future__ import annotations

import json

import pytest

from cockroachdb.continuum.mcp import (
    HttpMcpClient,
    McpConfig,
    SimulatedMcpClient,
    make_mcp,
)


def test_make_mcp_selects_simulated_when_no_endpoint() -> None:
    assert isinstance(make_mcp(McpConfig()), SimulatedMcpClient)
    assert isinstance(make_mcp(McpConfig(endpoint="https://x/mcp")), HttpMcpClient)


def test_simulated_list_and_call() -> None:
    c = SimulatedMcpClient()
    assert len(c.list_tools()) > 0
    assert c.call_tool("ping").text() == "pong"
    echoed = c.call_tool("echo", {"k": "v"}).text()
    assert json.loads(echoed) == {"k": "v"}
    assert c.calls() == [("ping", {}), ("echo", {"k": "v"})]


class _FakeTransport:
    """Scripts JSON-RPC replies by method and records requests."""

    def __init__(self, *, sse: bool = False) -> None:
        self.sse = sse
        self.requests: list[dict] = []
        self.headers: list[dict] = []

    def __call__(self, method, url, headers, body):
        req = json.loads(body)
        self.requests.append(req)
        self.headers.append(dict(headers))
        if "id" not in req:  # notification
            return 202, {}, ""
        result: dict | None = None
        if req["method"] == "initialize":
            return (
                200,
                {"Content-Type": "application/json", "Mcp-Session-Id": "sess-123"},
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req["id"],
                        "result": {"protocolVersion": "2025-06-18"},
                    }
                ),
            )
        if req["method"] == "tools/list":
            result = {"tools": [{"name": "list_findings", "description": "d"}]}
        elif req["method"] == "tools/call":
            result = {"content": [{"type": "text", "text": "ok"}]}
        env = json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result})
        if self.sse:
            return 200, {"Content-Type": "text/event-stream"}, f"event: message\ndata: {env}\n\n"
        return 200, {"Content-Type": "application/json"}, env


def test_http_initialize_list_call_json() -> None:
    t = _FakeTransport()
    c = HttpMcpClient(McpConfig(endpoint="https://x/mcp", token="tok"), t)

    tools = c.list_tools()
    assert [tool.name for tool in tools] == ["list_findings"]
    assert c.call_tool("list_findings", {"cluster": "c1"}).text() == "ok"

    methods = [r["method"] for r in t.requests]
    assert methods == ["initialize", "notifications/initialized", "tools/list", "tools/call"]
    for h in t.headers:
        assert h["Authorization"] == "Bearer tok"
        assert "text/event-stream" in h["Accept"]
    # tools/list (index 2) echoes the server-assigned session id.
    assert t.headers[2]["Mcp-Session-Id"] == "sess-123"
    assert t.headers[2]["MCP-Protocol-Version"] == "2025-06-18"


def test_http_sse_response_parsed() -> None:
    t = _FakeTransport(sse=True)
    c = HttpMcpClient(McpConfig(endpoint="https://x/mcp"), t)
    assert c.call_tool("list_findings").text() == "ok"


def test_http_server_error_surfaced() -> None:
    def transport(method, url, headers, body):
        req = json.loads(body)
        if "id" not in req:
            return 202, {}, ""
        if req["method"] == "initialize":
            return (
                200,
                {"Content-Type": "application/json"},
                json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": {}}),
            )
        return (
            200,
            {"Content-Type": "application/json"},
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "error": {"code": -32601, "message": "method not found"},
                }
            ),
        )

    c = HttpMcpClient(McpConfig(endpoint="https://x/mcp"), transport)
    with pytest.raises(RuntimeError, match="method not found"):
        c.list_tools()
