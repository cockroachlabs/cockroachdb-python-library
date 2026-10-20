"""Tests for cockroachdb.cdc.models — CDC payload parsing and configuration."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from cockroachdb.cdc.models import (
    ChangefeedConfig,
    ChangefeedEvent,
    ChangefeedPayload,
    _infer_operation,
    _parse_timestamp,
)
from cockroachdb.types import CDCOperation


class TestChangefeedPayloadParse:
    """Tests for ChangefeedPayload.parse()."""

    def test_parse_insert_event_from_json_string(self):
        """Parses a JSON string with a single insert event."""
        body = json.dumps(
            {
                "payload": [
                    {
                        "after": {"id": 1, "name": "alice"},
                        "before": None,
                        "key": [1],
                        "topic": "users",
                        "updated": "1716300000.0000000000",
                    }
                ],
                "length": 1,
                "resolved": None,
            }
        )

        result = ChangefeedPayload.parse(body)

        assert len(result.events) == 1
        event = result.events[0]
        assert event.operation == CDCOperation.INSERT
        assert event.table == "users"
        assert event.after == {"id": 1, "name": "alice"}
        assert event.before is None

    def test_parse_from_bytes(self):
        """Parses a bytes payload."""
        body = json.dumps(
            {
                "payload": [
                    {
                        "after": {"id": 2, "val": "x"},
                        "before": None,
                        "key": [2],
                        "topic": "items",
                        "updated": "1716300000.0000000000",
                    }
                ],
                "length": 1,
                "resolved": None,
            }
        ).encode()

        result = ChangefeedPayload.parse(body)
        assert len(result.events) == 1
        assert result.events[0].operation == CDCOperation.INSERT

    def test_parse_from_dict(self):
        """Parses a pre-parsed dict payload."""
        body = {
            "payload": [
                {
                    "after": None,
                    "before": {"id": 1, "name": "old"},
                    "key": [1],
                    "topic": "users",
                    "updated": "1716300000.0000000000",
                }
            ],
            "length": 1,
            "resolved": None,
        }

        result = ChangefeedPayload.parse(body)
        assert result.events[0].operation == CDCOperation.DELETE

    def test_parse_update_event(self):
        """Update is inferred when both before and after are present."""
        body = {
            "payload": [
                {
                    "after": {"id": 1, "name": "bob"},
                    "before": {"id": 1, "name": "alice"},
                    "key": [1],
                    "topic": "users",
                    "updated": "1716300000.0000000000",
                }
            ],
            "length": 1,
            "resolved": None,
        }

        result = ChangefeedPayload.parse(body)
        assert result.events[0].operation == CDCOperation.UPDATE

    def test_parse_invalid_json_raises_value_error(self):
        """Malformed JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            ChangefeedPayload.parse("{not json")

    def test_parse_non_dict_raises_value_error(self):
        """Non-dict parsed JSON raises ValueError."""
        with pytest.raises(ValueError, match="Expected dict"):
            ChangefeedPayload.parse(json.dumps([1, 2, 3]))

    def test_resolved_timestamp_propagated(self):
        """Resolved timestamp from the envelope is attached to events."""
        body = {
            "payload": [
                {
                    "after": {"id": 1},
                    "before": None,
                    "key": [1],
                    "topic": "t",
                    "updated": "1716300000.0000000000",
                }
            ],
            "resolved": "1716300001.0000000000",
        }

        result = ChangefeedPayload.parse(body)
        assert result.resolved == "1716300001.0000000000"
        assert result.events[0].resolved == "1716300001.0000000000"


class TestChangefeedEvent:
    """Tests for ChangefeedEvent dataclass."""

    def test_create_insert_event(self):
        event = ChangefeedEvent(
            operation=CDCOperation.INSERT,
            table="orders",
            timestamp=datetime.fromtimestamp(0),
            after={"id": 1, "total": 100},
        )
        assert event.operation == CDCOperation.INSERT
        assert event.before is None
        assert event.after["total"] == 100

    def test_create_delete_event(self):
        event = ChangefeedEvent(
            operation=CDCOperation.DELETE,
            table="orders",
            timestamp=datetime.fromtimestamp(0),
            before={"id": 1},
        )
        assert event.operation == CDCOperation.DELETE
        assert event.after is None

    def test_frozen_dataclass(self):
        event = ChangefeedEvent(
            operation=CDCOperation.INSERT,
            table="t",
            timestamp=datetime.fromtimestamp(0),
        )
        with pytest.raises(AttributeError):
            event.table = "other"  # type: ignore[misc]


class TestChangefeedConfig:
    """Tests for ChangefeedConfig defaults and SQL generation."""

    def test_default_values(self):
        cfg = ChangefeedConfig()
        assert cfg.format == "json"
        assert cfg.envelope == "wrapped"
        assert cfg.updated is True
        assert cfg.diff is True

    def test_to_options_sql_includes_format_and_envelope(self):
        cfg = ChangefeedConfig()
        sql = cfg.to_options_sql()
        assert "format = 'json'" in sql
        assert "envelope = 'wrapped'" in sql

    def test_to_options_sql_includes_updated_and_diff(self):
        cfg = ChangefeedConfig(updated=True, diff=True)
        sql = cfg.to_options_sql()
        assert "updated" in sql
        assert "diff" in sql

    def test_to_options_sql_omits_disabled_flags(self):
        cfg = ChangefeedConfig(updated=False, diff=False)
        sql = cfg.to_options_sql()
        # "updated" and "diff" as standalone keywords should not appear
        parts = [p.strip() for p in sql.split(",")]
        assert "updated" not in parts
        assert "diff" not in parts

    def test_to_options_sql_includes_cursor(self):
        cfg = ChangefeedConfig(cursor="1716300000.0000000000")
        sql = cfg.to_options_sql()
        assert "cursor = '1716300000.0000000000'" in sql


class TestInferOperation:
    """Tests for _infer_operation helper."""

    def test_insert(self):
        assert _infer_operation(None, {"id": 1}) == CDCOperation.INSERT

    def test_delete(self):
        assert _infer_operation({"id": 1}, None) == CDCOperation.DELETE

    def test_update(self):
        assert _infer_operation({"id": 1}, {"id": 1, "v": 2}) == CDCOperation.UPDATE


class TestParseTimestamp:
    """Tests for _parse_timestamp helper."""

    def test_parses_valid_timestamp(self):
        dt = _parse_timestamp("1716300000.0000000000")
        assert isinstance(dt, datetime)
        assert dt.year >= 2024

    def test_empty_string_returns_epoch(self):
        dt = _parse_timestamp("")
        assert dt == datetime.fromtimestamp(0)

    def test_invalid_string_returns_epoch(self):
        dt = _parse_timestamp("not-a-number")
        assert dt == datetime.fromtimestamp(0)
