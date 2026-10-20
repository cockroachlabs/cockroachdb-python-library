"""Agent / MCP surface — make the database actionable to agents.

A minimal, dependency-light MCP-style facade over ``@agent_tool``-decorated
callables. Build a :class:`CrdbAgent` from one or more provider objects, then use
:meth:`CrdbAgent.list_tools` (MCP ``tools/list`` shape) and
:meth:`CrdbAgent.invoke` (MCP ``tools/call`` shape).

Least-privilege by default: only decorated callables are exposed, and
``destructive`` tools are hidden and rejected unless the agent is constructed
with ``allow_destructive=True``. A network transport (stdio/HTTP) is out of
scope for this increment; the JSON-shaped dicts returned here are what a
transport would relay.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

from cockroachdb.continuum.plenum import storage_summary

if TYPE_CHECKING:
    from collections.abc import Mapping

    import psycopg

F = TypeVar("F", bound=Callable[..., Any])

_MARKER = "__agent_tool__"

_JSON_TYPES: dict[type, str] = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
}


@dataclass(frozen=True)
class ToolSpec:
    """Metadata attached to a callable by :func:`agent_tool`."""

    name: str
    description: str
    destructive: bool


@dataclass(frozen=True)
class ToolDescriptor:
    """A registered tool: its metadata, JSON input schema, and bound callable."""

    name: str
    description: str
    destructive: bool
    input_schema: dict[str, Any]
    func: Callable[..., Any] = field(compare=False)


def agent_tool(name: str, description: str = "", destructive: bool = False) -> Callable[[F], F]:
    """Mark a callable as an agent tool.

    The callable remains directly callable; :class:`ToolRegistry` discovers the
    attached :class:`ToolSpec`. ``destructive`` tools are hidden by default.
    """

    def decorator(func: F) -> F:
        setattr(
            func, _MARKER, ToolSpec(name=name, description=description, destructive=destructive)
        )
        return func

    return decorator


def _json_schema_for(hint: Any) -> dict[str, str]:
    return {"type": _JSON_TYPES.get(hint, "string")}


def _describe(name: str, func: Callable[..., Any]) -> str:
    sig = inspect.signature(func)
    params = ", ".join(p for p in sig.parameters if p != "self")
    return f"Invokes {name}({params})"


def _build_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Generate a simple JSON Schema object from a callable's signature."""
    sig = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}
    properties: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        properties[pname] = _json_schema_for(hints.get(pname))
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


class ToolRegistry:
    """Collects ``@agent_tool`` callables from provider objects and functions."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDescriptor] = {}

    def register(self, provider: object) -> ToolRegistry:
        """Register every ``@agent_tool`` method exposed by ``provider``."""
        for _member_name, member in inspect.getmembers(provider):
            if not callable(member):
                continue
            spec = getattr(member, _MARKER, None)
            if isinstance(spec, ToolSpec):
                self._add(member, spec)
        return self

    def register_callable(self, func: Callable[..., Any]) -> ToolRegistry:
        """Register a single decorated callable."""
        spec = getattr(func, _MARKER, None)
        if not isinstance(spec, ToolSpec):
            raise ValueError("callable is not decorated with @agent_tool")
        self._add(func, spec)
        return self

    def _add(self, func: Callable[..., Any], spec: ToolSpec) -> None:
        self._tools[spec.name] = ToolDescriptor(
            name=spec.name,
            description=spec.description or _describe(spec.name, func),
            destructive=spec.destructive,
            input_schema=_build_schema(func),
            func=func,
        )

    def all(self) -> list[ToolDescriptor]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolDescriptor | None:
        return self._tools.get(name)


class CrdbAgent:
    """MCP-style facade exposing registered tools under a least-privilege policy."""

    def __init__(self, registry: ToolRegistry, *, allow_destructive: bool = False) -> None:
        self._registry = registry
        self._allow_destructive = allow_destructive

    @classmethod
    def from_providers(cls, *providers: object, allow_destructive: bool = False) -> CrdbAgent:
        """Build an agent exposing the ``@agent_tool`` methods of ``providers``."""
        registry = ToolRegistry()
        for provider in providers:
            registry.register(provider)
        return cls(registry, allow_destructive=allow_destructive)

    def _is_visible(self, tool: ToolDescriptor) -> bool:
        return not tool.destructive or self._allow_destructive

    def tools(self) -> list[ToolDescriptor]:
        """The tools currently visible under the least-privilege policy."""
        return [t for t in self._registry.all() if self._is_visible(t)]

    def list_tools(self) -> dict[str, Any]:
        """MCP ``tools/list`` response as a JSON-shaped dict."""
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema,
                }
                for t in self.tools()
            ]
        }

    def invoke(self, name: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """MCP ``tools/call`` for ``name`` with ``args``.

        Unknown or non-permitted (hidden destructive) tools raise
        :class:`ValueError`. Tool exceptions are returned as an error result
        rather than propagated, matching the MCP ``tools/call`` shape.
        """
        tool = self._registry.get(name)
        if tool is None or not self._is_visible(tool):
            raise ValueError(f"Unknown or not permitted tool: {name}")
        supplied = dict(args or {})
        valid = set(inspect.signature(tool.func).parameters)
        kwargs = {k: v for k, v in supplied.items() if k in valid}
        try:
            result = tool.func(**kwargs)
            return self._result(result, is_error=False)
        except Exception as exc:
            return self._result(str(exc), is_error=True)

    @staticmethod
    def _result(payload: Any, *, is_error: bool) -> dict[str, Any]:
        text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": is_error}


class CrdbOpsTools:
    """Built-in read-only ops tools: health and a Plenum storage summary.

    ``storage_summary`` requires a ``connection_factory`` returning a psycopg
    connection (used as a context manager).
    """

    def __init__(self, connection_factory: Callable[[], psycopg.Connection] | None = None) -> None:
        self._connection_factory = connection_factory

    @agent_tool("health", "Liveness/health signal for the library surface.")
    def health(self) -> dict[str, Any]:
        return {"status": "ok", "database_configured": self._connection_factory is not None}

    @agent_tool("storage_summary", "Cockroach Plenum storage summary for the current database.")
    def storage_summary(self) -> list[dict[str, Any]]:
        if self._connection_factory is None:
            raise RuntimeError("storage_summary requires a connection_factory")
        with self._connection_factory() as conn:
            return [
                {"schema": t.schema, "table": t.table, "rows": t.rows, "bytes": t.bytes}
                for t in storage_summary(conn)
            ]
