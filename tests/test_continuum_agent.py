"""Unit tests for the agent/MCP surface: registry, schema, invocation, gating."""

from __future__ import annotations

import json

import pytest

from cockroachdb.continuum import (
    CrdbAgent,
    CrdbOpsTools,
    ToolRegistry,
    agent_tool,
)


class _Tools:
    @agent_tool("echo", "Echoes the message a number of times.")
    def echo(self, message: str, times: int = 1) -> str:
        return message * times

    @agent_tool("wipe", "Deletes everything.", destructive=True)
    def wipe(self) -> str:
        return "gone"


def test_ops_tools_listed_and_health_invocable() -> None:
    agent = CrdbAgent.from_providers(CrdbOpsTools())
    names = {t["name"] for t in agent.list_tools()["tools"]}
    assert {"health", "storage_summary"} <= names

    result = agent.invoke("health")
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["status"] == "ok"
    assert payload["database_configured"] is False


def test_schema_generated_from_signature() -> None:
    registry = ToolRegistry().register(_Tools())
    echo = registry.get("echo")
    assert echo is not None
    schema = echo.input_schema
    assert schema["type"] == "object"
    assert schema["properties"]["message"] == {"type": "string"}
    assert schema["properties"]["times"] == {"type": "integer"}
    assert schema["required"] == ["message"]


def test_invoke_binds_arguments() -> None:
    agent = CrdbAgent.from_providers(_Tools())
    result = agent.invoke("echo", {"message": "ab", "times": 3})
    assert result["isError"] is False
    # String results are relayed as raw text (structured results are JSON-encoded).
    assert result["content"][0]["text"] == "ababab"


def test_destructive_hidden_and_rejected_by_default() -> None:
    agent = CrdbAgent.from_providers(_Tools())
    names = {t["name"] for t in agent.list_tools()["tools"]}
    assert "wipe" not in names
    with pytest.raises(ValueError, match="not permitted"):
        agent.invoke("wipe")


def test_destructive_allowed_when_opted_in() -> None:
    agent = CrdbAgent.from_providers(_Tools(), allow_destructive=True)
    names = {t["name"] for t in agent.list_tools()["tools"]}
    assert "wipe" in names
    result = agent.invoke("wipe")
    assert result["isError"] is False
    assert result["content"][0]["text"] == "gone"


def test_invoke_unknown_tool_raises() -> None:
    agent = CrdbAgent(ToolRegistry())
    with pytest.raises(ValueError, match="Unknown or not permitted"):
        agent.invoke("does-not-exist")


def test_tool_exception_returned_as_error_result() -> None:
    # storage_summary without a connection factory raises inside the tool.
    agent = CrdbAgent.from_providers(CrdbOpsTools())
    result = agent.invoke("storage_summary")
    assert result["isError"] is True
    assert "connection_factory" in result["content"][0]["text"]


def test_register_callable_requires_decoration() -> None:
    def undecorated() -> None:
        return None

    with pytest.raises(ValueError, match="not decorated"):
        ToolRegistry().register_callable(undecorated)
