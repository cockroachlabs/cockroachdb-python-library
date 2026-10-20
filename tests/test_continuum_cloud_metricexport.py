"""Tests for Continuum Cloud metric-export builders and the health probe."""

from __future__ import annotations

from cockroachdb.continuum.cloud import (
    SimulatedCloudClient,
    cloudwatch_export,
    datadog_export,
    health,
    prometheus_export,
)


def test_datadog_export() -> None:
    cfg = datadog_export("key-1", "US1")
    assert cfg.target == "datadog"
    assert cfg.settings == {"api_key": "key-1", "site": "US1"}


def test_cloudwatch_export() -> None:
    cfg = cloudwatch_export("arn:aws:iam::1:role/R", "crdb-logs", "us-east-1")
    assert cfg.target == "cloudwatch"
    assert cfg.settings == {
        "role_arn": "arn:aws:iam::1:role/R",
        "log_group_name": "crdb-logs",
        "target_region": "us-east-1",
    }
    # Empty target region is omitted.
    assert "target_region" not in cloudwatch_export("arn", "lg").settings


def test_prometheus_export() -> None:
    cfg = prometheus_export()
    assert cfg.target == "prometheus"
    assert cfg.settings == {}


def test_health_ok() -> None:
    assert health(SimulatedCloudClient()) is True


def test_health_false_on_error() -> None:
    class Broken:
        def list_clusters(self):
            raise RuntimeError("down")

    assert health(Broken()) is False
