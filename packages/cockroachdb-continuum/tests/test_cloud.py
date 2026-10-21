"""Unit tests for cockroachdb.continuum.cloud (no DB or network required)."""

from __future__ import annotations

import json

import pytest

from cockroachdb.continuum.cloud import (
    CloudConfig,
    HttpCloudClient,
    MetricExportConfig,
    SimulatedCloudClient,
    VirtualClusterManager,
    make_cloud,
    routing_conn_string,
)


def test_make_cloud_selects_simulated_without_key():
    assert isinstance(make_cloud(CloudConfig()), SimulatedCloudClient)
    assert isinstance(make_cloud(CloudConfig(enabled=True)), SimulatedCloudClient)


def test_make_cloud_selects_http_with_key():
    assert isinstance(make_cloud(CloudConfig(enabled=True, api_key="sk")), HttpCloudClient)


def test_simulated_clusters_and_metric_export():
    c = SimulatedCloudClient()
    clusters = c.list_clusters()
    assert len(clusters) == 1
    assert c.get_cluster(clusters[0].id).name == "dev-cluster"
    with pytest.raises(KeyError):
        c.get_cluster("missing")
    c.configure_metric_export(clusters[0].id, MetricExportConfig("datadog", {"site": "us5"}))
    assert c.metric_exports()[clusters[0].id].target == "datadog"
    with pytest.raises(ValueError):
        c.configure_metric_export("x", MetricExportConfig(""))


class _RecordingTransport:
    def __init__(self, responses):
        self.responses = responses  # dict: (method, path_suffix) -> (status, text)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        for (m, suffix), resp in self.responses.items():
            if method == m and url.endswith(suffix):
                return resp
        return 404, "not found"


def test_http_list_parses_and_sends_bearer():
    body = json.dumps(
        {
            "clusters": [
                {
                    "id": "c1",
                    "name": "prod",
                    "plan": "STANDARD",
                    "state": "CREATED",
                    "cloud_provider": "AWS",
                    "regions": ["us-east-1"],
                }
            ]
        }
    )
    t = _RecordingTransport({("GET", "/clusters"): (200, body)})
    c = HttpCloudClient(CloudConfig(enabled=True, api_key="sk-123"), transport=t)
    clusters = c.list_clusters()
    assert len(clusters) == 1
    assert clusters[0].cloud_provider == "AWS"
    assert clusters[0].regions == ("us-east-1",)
    assert t.calls[0][2]["Authorization"] == "Bearer sk-123"


def test_http_metric_export_posts_to_target_path():
    t = _RecordingTransport({("POST", "/clusters/c1/metricexport/datadog"): (200, "")})
    c = HttpCloudClient(CloudConfig(enabled=True, api_key="sk"), transport=t)
    c.configure_metric_export("c1", MetricExportConfig("datadog", {"site": "us5"}))
    method, url, _headers, sent = t.calls[0]
    assert method == "POST"
    assert url.endswith("/clusters/c1/metricexport/datadog")
    assert json.loads(sent) == {"site": "us5"}


def test_http_non_2xx_raises():
    t = _RecordingTransport({("GET", "/clusters"): (401, "unauthorized")})
    c = HttpCloudClient(CloudConfig(enabled=True, api_key="bad"), transport=t)
    with pytest.raises(RuntimeError):
        c.list_clusters()


class _FakeCursor:
    def __init__(self, parent):
        self.parent = parent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, *args):
        self.parent.executed.append(sql)

    def fetchall(self):
        return self.parent.rows


class _FakeConn:
    def __init__(self, rows=None):
        self.executed = []
        self.rows = rows or []
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1


def test_vcluster_manager_create_drop_list():
    conn = _FakeConn(rows=[(3, "analytics"), (4, "reporting")])
    m = VirtualClusterManager(conn)
    m.create("analytics")
    m.drop("reporting")
    assert conn.executed == ["CREATE VIRTUAL CLUSTER analytics", "DROP VIRTUAL CLUSTER reporting"]
    assert conn.commits == 2
    vcs = m.list()
    assert [v.name for v in vcs] == ["analytics", "reporting"]


def test_vcluster_manager_rejects_bad_names():
    m = VirtualClusterManager(_FakeConn())
    for bad in ["", "1abc", "drop table users;", "has space", "a--b"]:
        with pytest.raises(ValueError):
            m.create(bad)


def test_routing_conn_string():
    out = routing_conn_string(
        "postgresql://root@host:26257/defaultdb?sslmode=verify-full", "analytics"
    )
    assert "options=-ccluster%3Danalytics" in out
    assert "sslmode=verify-full" in out
    with pytest.raises(ValueError):
        routing_conn_string("postgresql://h/db", "bad name")
