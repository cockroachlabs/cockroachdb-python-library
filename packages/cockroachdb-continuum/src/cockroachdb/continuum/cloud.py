"""Cockroach Continuum Cloud control-plane client.

An optional, separate surface from the core retry path: manage Continuum
control-plane resources (clusters, virtual clusters, metric export)
programmatically.

Like :mod:`cockroachdb.continuum.aegis`, a :class:`SimulatedCloudClient` is used
whenever no API key is configured, so code runs without a Continuum organization;
set an API key to target the real API (default base URL
``https://cockroachlabs.cloud/api/v1``). Authentication uses a service-account
secret key sent as a Bearer token. The HTTP client uses the standard library
(no extra dependency) and accepts an injectable transport for tests.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

DEFAULT_BASE_URL = "https://cockroachlabs.cloud/api/v1"

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

# A transport maps (method, url, headers, body) -> (status_code, response_text).
Transport = Callable[[str, str, Mapping[str, str], "str | None"], "tuple[int, str]"]


@dataclass(frozen=True)
class Cluster:
    """A CockroachDB Cloud cluster (control-plane view)."""

    id: str
    name: str = ""
    plan: str = ""
    state: str = ""
    cloud_provider: str = ""
    regions: tuple[str, ...] = ()


@dataclass(frozen=True)
class VirtualCluster:
    """A Cockroach virtual cluster. ``routing_id`` is used when connecting."""

    name: str
    id: str = ""
    routing_id: str = ""
    state: str = ""


@dataclass(frozen=True)
class MetricExportConfig:
    """Metric-export configuration. ``target`` is one of ``datadog`` /
    ``cloudwatch`` / ``prometheus``; ``settings`` carries the target-specific
    fields."""

    target: str
    settings: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CloudConfig:
    """Configuration for the Cloud client."""

    enabled: bool = False
    base_url: str = ""
    api_key: str = ""


@runtime_checkable
class CloudClient(Protocol):
    """The Cloud control-plane surface."""

    def list_clusters(self) -> list[Cluster]: ...

    def get_cluster(self, cluster_id: str) -> Cluster: ...

    def configure_metric_export(self, cluster_id: str, config: MetricExportConfig) -> None: ...


def make_cloud(config: CloudConfig, transport: Transport | None = None) -> CloudClient:
    """Return a Cloud client: simulated when disabled or no API key, else HTTP."""
    if not config.enabled or not config.api_key:
        return SimulatedCloudClient()
    return HttpCloudClient(config, transport=transport)


class SimulatedCloudClient:
    """In-memory Cloud backend for development and tests."""

    def __init__(self) -> None:
        self._clusters = [
            Cluster(
                id="00000000-0000-0000-0000-000000000001",
                name="dev-cluster",
                plan="STANDARD",
                state="CREATED",
                cloud_provider="GCP",
                regions=("us-east1",),
            )
        ]
        self._exports: dict[str, MetricExportConfig] = {}

    def list_clusters(self) -> list[Cluster]:
        return list(self._clusters)

    def get_cluster(self, cluster_id: str) -> Cluster:
        for c in self._clusters:
            if c.id == cluster_id:
                return c
        raise KeyError(f"cloud: cluster not found: {cluster_id}")

    def configure_metric_export(self, cluster_id: str, config: MetricExportConfig) -> None:
        if config is None or not config.target:
            raise ValueError("cloud: metric export target is required")
        self._exports[cluster_id] = config

    def metric_exports(self) -> dict[str, MetricExportConfig]:
        """Return the metric-export configs recorded so far, keyed by cluster ID."""
        return dict(self._exports)


def _urllib_transport(
    method: str, url: str, headers: Mapping[str, str], body: str | None
) -> tuple[int, str]:
    data = body.encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


class HttpCloudClient:
    """HTTP-backed Cloud client using a service-account Bearer token."""

    def __init__(self, config: CloudConfig, transport: Transport | None = None) -> None:
        self._base = (config.base_url or DEFAULT_BASE_URL).rstrip("/")
        self._key = config.api_key
        self._transport: Transport = transport or _urllib_transport

    def _do(self, method: str, path: str, body: Any | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body)
        status, text = self._transport(method, self._base + path, headers, payload)
        if status < 200 or status >= 300:
            raise RuntimeError(f"cloud: {method} {path}: status {status}: {text[:200]}")
        return json.loads(text) if text else {}

    def list_clusters(self) -> list[Cluster]:
        data = self._do("GET", "/clusters")
        return [_to_cluster(c) for c in data.get("clusters", [])]

    def get_cluster(self, cluster_id: str) -> Cluster:
        return _to_cluster(self._do("GET", f"/clusters/{cluster_id}"))

    def configure_metric_export(self, cluster_id: str, config: MetricExportConfig) -> None:
        if config is None or not config.target:
            raise ValueError("cloud: metric export target is required")
        self._do(
            "POST",
            f"/clusters/{cluster_id}/metricexport/{config.target}",
            dict(config.settings),
        )


def _to_cluster(m: Mapping[str, Any]) -> Cluster:
    regions = m.get("regions") or []
    return Cluster(
        id=str(m.get("id", "")),
        name=str(m.get("name", "")),
        plan=str(m.get("plan", "")),
        state=str(m.get("state", "")),
        cloud_provider=str(m.get("cloud_provider", "")),
        regions=tuple(str(r) for r in regions),
    )


def _validate_ident(name: str) -> None:
    if not name or not _IDENT.match(name):
        raise ValueError(
            f"cloud: invalid virtual-cluster name {name!r} "
            "(allowed: letters, digits, underscore; must not start with a digit)"
        )


class VirtualClusterManager:
    """Manages virtual-cluster lifecycle over a DB-API connection (e.g. psycopg).

    Issues ``CREATE / SHOW / DROP VIRTUAL CLUSTER``, which require a
    Continuum-enabled cluster. Names are validated against a strict identifier
    pattern before interpolation into DDL.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def create(self, name: str) -> None:
        _validate_ident(name)
        self._exec(f"CREATE VIRTUAL CLUSTER {name}")

    def drop(self, name: str) -> None:
        _validate_ident(name)
        self._exec(f"DROP VIRTUAL CLUSTER {name}")

    def _exec(self, sql: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(sql)
        self._conn.commit()

    def list(self) -> list[VirtualCluster]:
        with self._conn.cursor() as cur:
            cur.execute("SHOW VIRTUAL CLUSTERS")
            rows: Sequence[Sequence[Any]] = cur.fetchall()
        return [VirtualCluster(name=str(r[1]), id=str(r[0]), routing_id=str(r[1])) for r in rows]


def routing_conn_string(base: str, vcluster_name: str) -> str:
    """Append the ``-ccluster`` option so connections route to a virtual cluster."""
    _validate_ident(vcluster_name)
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}options=-ccluster%3D{vcluster_name}"


# Typed builders for the three metric-export sinks. Each returns a
# :class:`MetricExportConfig` ready for :meth:`CloudClient.configure_metric_export`,
# so callers don't have to remember the Cloud API's field names. The raw ``settings``
# mapping remains available for sinks or fields not covered here (e.g. Azure Monitor).


def datadog_export(api_key: str, site: str) -> MetricExportConfig:
    """Build a Datadog metric-export config. ``site`` is the Datadog site (e.g. ``US1``)."""
    return MetricExportConfig(target="datadog", settings={"api_key": api_key, "site": site})


def cloudwatch_export(
    role_arn: str, log_group_name: str, target_region: str | None = None
) -> MetricExportConfig:
    """Build an Amazon CloudWatch metric-export config.

    ``role_arn`` is the CockroachCloudMetricsExportRole ARN; ``target_region`` may be
    omitted to use the cluster's region.
    """
    settings: dict[str, Any] = {"role_arn": role_arn, "log_group_name": log_group_name}
    if target_region:
        settings["target_region"] = target_region
    return MetricExportConfig(target="cloudwatch", settings=settings)


def prometheus_export() -> MetricExportConfig:
    """Build a Prometheus metric-export config (enabled without extra settings)."""
    return MetricExportConfig(target="prometheus", settings={})


def health(client: CloudClient) -> bool:
    """Report whether the Cloud control plane is reachable.

    Issues a lightweight ``list_clusters`` and returns ``True`` on success,
    ``False`` if it raises. Use it for readiness probes.
    """
    try:
        client.list_clusters()
    except Exception:
        return False
    return True
