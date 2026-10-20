"""Tests for the Aegis-over-MCP adapter — fake MCP client, no live server."""

from __future__ import annotations

import json
from typing import Any

import pytest

from cockroachdb.continuum.aegis import AppEvent, McpAegisClient, McpToolNames
from cockroachdb.continuum.mcp import CallResult


class _FakeMcp:
    """Scripts CallResults by tool name and records calls."""

    def __init__(self, results: dict[str, CallResult]) -> None:
        self._results = results
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self):
        return []

    def call_tool(self, name: str, arguments: Any = None) -> CallResult:
        self.calls.append((name, dict(arguments or {})))
        return self._results.get(name, CallResult())


def _text(s: str) -> CallResult:
    return CallResult(content=({"type": "text", "text": s},))


def test_findings_and_recommendations_parsed() -> None:
    fake = _FakeMcp(
        {
            "list_findings": _text(
                json.dumps([{"id": "f1", "severity": "warning", "title": "hot", "detail": "d"}])
            ),
            "list_recs": _text(
                json.dumps([{"id": "r1", "title": "split", "rationale": "why", "action": "ALTER"}])
            ),
        }
    )
    c = McpAegisClient(fake, McpToolNames(findings="list_findings", recommendations="list_recs"))

    findings = c.findings()
    assert len(findings) == 1
    assert findings[0].id == "f1"
    assert findings[0].severity == "warning"

    recs = c.recommendations()
    assert recs[0].action == "ALTER"
    assert recs[0].rationale == "why"


def test_emit_sends_args() -> None:
    fake = _FakeMcp({})
    c = McpAegisClient(fake, McpToolNames(emit="emit_event"))
    c.emit(AppEvent("retry", "svc", {"attempt": 2}, 99))
    assert fake.calls[0][0] == "emit_event"
    assert fake.calls[0][1]["kind"] == "retry"
    assert fake.calls[0][1]["epochMillis"] == 99


def test_unconfigured_tool_raises() -> None:
    c = McpAegisClient(_FakeMcp({}), McpToolNames())
    with pytest.raises(ValueError, match="not configured"):
        c.findings()
    with pytest.raises(ValueError, match="not configured"):
        c.recommendations()
    with pytest.raises(ValueError, match="not configured"):
        c.emit(AppEvent("x", "y"))


def test_tool_error_surfaced() -> None:
    fake = _FakeMcp(
        {"list_findings": CallResult(content=({"type": "text", "text": "boom"},), is_error=True)}
    )
    c = McpAegisClient(fake, McpToolNames(findings="list_findings"))
    with pytest.raises(RuntimeError, match="reported error"):
        c.findings()
