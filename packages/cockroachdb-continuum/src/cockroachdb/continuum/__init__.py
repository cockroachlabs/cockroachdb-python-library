"""CockroachDB Continuum — vCluster, Plenum, Aegis, and the agent/MCP surface.

Idiomatic Python back-port of the Cockroach Continuum features:

- **vCluster** (:mod:`cockroachdb.continuum.vcluster`) — workload tagging + QoS via
  ``vcluster``/``virtual_cluster`` and ``Priority``.
- **Plenum** (:mod:`cockroachdb.continuum.plenum`) — customer-safe storage
  insights via ``storage_summary``.
- **Aegis** (:mod:`cockroachdb.continuum.aegis`) — autonomous-ops findings and an
  event exhaust.
- **Agent/MCP** (:mod:`cockroachdb.continuum.agent`) — expose least-privilege
  tools to agents.
"""

from __future__ import annotations

from cockroachdb.continuum.aegis import (
    AegisClient,
    AegisConfig,
    AegisExhaust,
    AppEvent,
    Finding,
    HttpAegisClient,
    McpAegisClient,
    McpToolNames,
    Recommendation,
    SimulatedAegisClient,
    make_aegis,
)
from cockroachdb.continuum.agent import (
    CrdbAgent,
    CrdbOpsTools,
    ToolDescriptor,
    ToolRegistry,
    ToolSpec,
    agent_tool,
)
from cockroachdb.continuum.cloud import (
    CloudClient,
    CloudConfig,
    Cluster,
    HttpCloudClient,
    MetricExportConfig,
    SimulatedCloudClient,
    VirtualCluster,
    VirtualClusterManager,
    cloudwatch_export,
    datadog_export,
    health,
    make_cloud,
    prometheus_export,
    routing_conn_string,
)
from cockroachdb.continuum.mcp import (
    CallResult,
    HttpMcpClient,
    McpClient,
    McpConfig,
    SimulatedMcpClient,
    Tool,
    make_mcp,
)
from cockroachdb.continuum.plenum import TableStorage, storage_summary
from cockroachdb.continuum.vcluster import Priority, vcluster, virtual_cluster

__version__ = "0.1.0"

__all__ = [
    # Aegis
    "AegisClient",
    "AegisConfig",
    "AegisExhaust",
    "AppEvent",
    # MCP
    "CallResult",
    # Cloud control-plane
    "CloudClient",
    "CloudConfig",
    "Cluster",
    # Agent / MCP
    "CrdbAgent",
    "CrdbOpsTools",
    "Finding",
    "HttpAegisClient",
    "HttpCloudClient",
    "HttpMcpClient",
    "McpAegisClient",
    "McpClient",
    "McpConfig",
    "McpToolNames",
    "MetricExportConfig",
    # vCluster
    "Priority",
    "Recommendation",
    "SimulatedAegisClient",
    "SimulatedCloudClient",
    "SimulatedMcpClient",
    # Plenum
    "TableStorage",
    "Tool",
    "ToolDescriptor",
    "ToolRegistry",
    "ToolSpec",
    "VirtualCluster",
    "VirtualClusterManager",
    "__version__",
    "agent_tool",
    "cloudwatch_export",
    "datadog_export",
    "health",
    "make_aegis",
    "make_cloud",
    "make_mcp",
    "prometheus_export",
    "routing_conn_string",
    "storage_summary",
    "vcluster",
    "virtual_cluster",
]
