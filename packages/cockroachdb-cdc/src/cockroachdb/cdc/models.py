"""Data models for CockroachDB CDC changefeed events and configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

from cockroachdb.types import CDCOperation

T = TypeVar("T")


@dataclass(frozen=True)
class ChangefeedEvent(Generic[T]):
    """A single parsed changefeed event.

    CockroachDB emits JSON payloads on each row-level change. This dataclass
    normalises the raw payload into a typed event with before/after snapshots.

    Attributes:
        operation: The CDC operation type (insert, update, delete).
        table: Fully-qualified table name emitting the change.
        timestamp: Wall-clock time of the event as reported by CockroachDB.
        before: Row state before the change (None for inserts).
        after: Row state after the change (None for deletes).
        key: Primary-key columns identifying the affected row.
        resolved: Resolved timestamp string for ordering guarantees.
    """

    operation: CDCOperation
    table: str
    timestamp: datetime
    before: T | None = None
    after: T | None = None
    key: dict[str, Any] = field(default_factory=dict)
    resolved: str | None = None


@dataclass(frozen=True)
class ChangefeedPayload:
    """Parser for raw CockroachDB webhook JSON payloads.

    CockroachDB sends webhook payloads in the following JSON envelope::

        {
            "payload": [
                {
                    "after": {"id": 1, "name": "alice"},
                    "before": null,
                    "key": [1],
                    "topic": "users",
                    "updated": "1234567890.0000000000"
                }
            ],
            "length": 1,
            "resolved": null
        }

    This class provides a ``parse`` classmethod to convert the raw JSON into
    a list of :class:`ChangefeedEvent` instances.
    """

    raw: dict[str, Any]
    events: list[ChangefeedEvent[dict[str, Any]]]
    resolved: str | None

    @classmethod
    def parse(cls, body: str | bytes | dict[str, Any]) -> ChangefeedPayload:
        """Parse a raw webhook body into a ChangefeedPayload.

        Args:
            body: JSON string, bytes, or pre-parsed dict from the webhook request.

        Returns:
            A ChangefeedPayload with parsed events.

        Raises:
            ValueError: If the payload cannot be parsed.
        """
        if isinstance(body, (str, bytes)):
            try:
                raw = json.loads(body)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in changefeed payload: {exc}") from exc
        else:
            raw = body

        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict payload, got {type(raw).__name__}")

        resolved = raw.get("resolved")
        payload_items = raw.get("payload", [])
        events: list[ChangefeedEvent[dict[str, Any]]] = []

        for item in payload_items:
            after = item.get("after")
            before = item.get("before")
            topic = item.get("topic", "unknown")
            updated = item.get("updated", "")

            operation = _infer_operation(before, after)
            timestamp = _parse_timestamp(updated)

            key_raw = item.get("key", [])
            key = _normalise_key(key_raw, after or before)

            events.append(
                ChangefeedEvent(
                    operation=operation,
                    table=topic,
                    timestamp=timestamp,
                    before=before,
                    after=after,
                    key=key,
                    resolved=resolved,
                )
            )

        return cls(raw=raw, events=events, resolved=resolved)


@dataclass(frozen=True)
class ChangefeedConfig:
    """Configuration for creating a CockroachDB changefeed.

    Attributes:
        format: Payload format (``json`` or ``avro``).
        envelope: Envelope type controlling before/after inclusion.
        cursor: Resume from a specific timestamp.
        updated: Include an ``updated`` timestamp in each message.
        diff: Include a ``before`` value showing the pre-update state.
        schema_change_policy: How to handle DDL changes.
        min_checkpoint_frequency: Minimum interval between resolved timestamps.
        webhook_sink_config: Additional sink-level configuration dict.
    """

    format: str = "json"
    envelope: str = "wrapped"
    cursor: str | None = None
    updated: bool = True
    diff: bool = True
    schema_change_policy: str = "backfill"
    min_checkpoint_frequency: str = "30s"
    webhook_sink_config: dict[str, Any] = field(default_factory=dict)

    def to_options_sql(self) -> str:
        """Build the WITH clause options for CREATE CHANGEFEED.

        Returns:
            SQL fragment like ``format = 'json', envelope = 'wrapped', ...``
        """
        parts: list[str] = [
            f"format = '{self.format}'",
            f"envelope = '{self.envelope}'",
            f"schema_change_policy = '{self.schema_change_policy}'",
            f"min_checkpoint_frequency = '{self.min_checkpoint_frequency}'",
        ]
        if self.updated:
            parts.append("updated")
        if self.diff:
            parts.append("diff")
        if self.cursor:
            parts.append(f"cursor = '{self.cursor}'")
        if self.webhook_sink_config:
            config_json = json.dumps(self.webhook_sink_config)
            parts.append(f"webhook_sink_config = '{config_json}'")
        return ", ".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _infer_operation(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> CDCOperation:
    """Determine the CDC operation from before/after presence."""
    if before is None and after is not None:
        return CDCOperation.INSERT
    if before is not None and after is None:
        return CDCOperation.DELETE
    return CDCOperation.UPDATE


def _parse_timestamp(updated: str) -> datetime:
    """Parse a CockroachDB ``updated`` field into a datetime.

    CockroachDB sends nanosecond-precision UNIX timestamps as strings
    like ``"1716300000.0000000000"``.
    """
    if not updated:
        return datetime.fromtimestamp(0)
    try:
        seconds = float(updated.split(".")[0])
        return datetime.fromtimestamp(seconds)
    except (ValueError, OSError):
        return datetime.fromtimestamp(0)


def _normalise_key(
    key_raw: list[Any],
    row: dict[str, Any] | None,
) -> dict[str, Any]:
    """Convert positional key list into a named dict.

    CockroachDB emits keys as a positional list. When the row payload is
    available we zip the first N column names with the key values.
    """
    if not key_raw:
        return {}
    if row and isinstance(row, dict):
        columns = list(row.keys())
        return dict(zip(columns[: len(key_raw)], key_raw, strict=False))
    return {f"key_{i}": v for i, v in enumerate(key_raw)}
