"""Unit tests for Cockroach Aegis clients, events, and the exhaust."""

from __future__ import annotations

import pytest

from cockroachdb.continuum import (
    AegisConfig,
    AegisExhaust,
    AppEvent,
    Finding,
    HttpAegisClient,
    Recommendation,
    SimulatedAegisClient,
    make_aegis,
)


def test_make_aegis_returns_simulated_without_endpoint() -> None:
    client = make_aegis(AegisConfig())
    assert isinstance(client, SimulatedAegisClient)


def test_make_aegis_returns_http_stub_with_endpoint() -> None:
    client = make_aegis(AegisConfig(endpoint="https://aegis.example", token="t"))
    assert isinstance(client, HttpAegisClient)


def test_simulated_findings_and_recommendations() -> None:
    client = SimulatedAegisClient()
    findings = client.findings()
    recommendations = client.recommendations()
    assert findings and all(isinstance(f, Finding) for f in findings)
    assert recommendations and all(isinstance(r, Recommendation) for r in recommendations)


def test_simulated_records_emitted_events() -> None:
    client = SimulatedAegisClient()
    assert client.emitted_events() == []
    client.emit(AppEvent.now("custom", "unit-test", {"key": "value"}))
    events = client.emitted_events()
    assert len(events) == 1
    assert events[0].kind == "custom"
    assert events[0].source == "unit-test"
    assert events[0].attrs["key"] == "value"
    assert events[0].epoch_millis > 0


def test_app_event_default_attrs_empty() -> None:
    event = AppEvent(kind="k", source="s")
    assert event.attrs == {}
    assert event.epoch_millis == 0


def test_http_stub_raises_not_implemented() -> None:
    client = make_aegis(AegisConfig(endpoint="https://aegis.example"))
    with pytest.raises(NotImplementedError, match="not yet public"):
        client.findings()
    with pytest.raises(NotImplementedError, match="not yet public"):
        client.recommendations()
    with pytest.raises(NotImplementedError, match="not yet public"):
        client.emit(AppEvent.now("k", "s"))


def test_aegis_exhaust_forwards_signals() -> None:
    client = SimulatedAegisClient()
    exhaust = AegisExhaust(client, source="svc")
    exhaust.record_retry("place_order", attempt=1, sqlstate="40001")
    exhaust.record_retry_exhausted("place_order", attempts=3, sqlstate="40001")
    exhaust.record_circuit_open("place_order", consecutive_failures=5)

    events = client.emitted_events()
    assert [e.kind for e in events] == ["retry", "retry_exhausted", "circuit_open"]
    assert all(e.source == "svc" for e in events)
    assert events[0].attrs["operation"] == "place_order"
    assert events[0].attrs["attempt"] == 1
    assert events[1].attrs["attempts"] == 3
    assert events[2].attrs["consecutive_failures"] == 5
