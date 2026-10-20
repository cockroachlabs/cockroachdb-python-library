"""Unit tests for Cockroach vCluster tagging and QoS context."""

from __future__ import annotations

from cockroachdb.continuum import Priority, vcluster, virtual_cluster
from cockroachdb.core.vcluster import VClusterContext


def test_priority_qos_mapping() -> None:
    assert Priority.LOW.qos == "background"
    assert Priority.NORMAL.qos == "regular"
    assert Priority.HIGH.qos == "critical"


def test_vcluster_sets_and_restores_context() -> None:
    assert VClusterContext.current() is None
    with vcluster("analytics-batch", Priority.LOW) as settings:
        assert settings.application_name == "analytics-batch"
        assert settings.quality_of_service == "background"
        active = VClusterContext.current()
        assert active is not None
        assert active.application_name == "analytics-batch"
        assert active.quality_of_service == "background"
    assert VClusterContext.current() is None


def test_vcluster_defaults_to_normal_priority() -> None:
    with vcluster("web") as settings:
        assert settings.quality_of_service == "regular"


def test_vcluster_nesting_restores_outer() -> None:
    with vcluster("outer", Priority.HIGH):
        with vcluster("inner", Priority.LOW):
            active = VClusterContext.current()
            assert active is not None
            assert active.application_name == "inner"
        outer = VClusterContext.current()
        assert outer is not None
        assert outer.application_name == "outer"
        assert outer.quality_of_service == "critical"


def test_virtual_cluster_decorator() -> None:
    captured: dict[str, str | None] = {}

    @virtual_cluster("checkout", Priority.HIGH)
    def place_order() -> str:
        active = VClusterContext.current()
        captured["qos"] = active.quality_of_service if active else None
        captured["app"] = active.application_name if active else None
        return "done"

    assert place_order() == "done"
    assert captured["qos"] == "critical"
    assert captured["app"] == "checkout"
    assert VClusterContext.current() is None
