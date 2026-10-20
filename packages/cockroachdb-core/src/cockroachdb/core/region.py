"""Region context management using contextvars for multi-region CockroachDB deployments."""

from __future__ import annotations

import contextvars
import re
from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from cockroachdb.exceptions import RegionValidationError

if TYPE_CHECKING:
    from collections.abc import Iterator

_region_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "cockroachdb_region", default=None
)

_REGION_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


class RegionContext:
    """Thread-safe region context backed by contextvars.

    Provides classmethod-based access to the current region, suitable
    for use across async frameworks and threaded servers.
    """

    @classmethod
    def current(cls) -> str | None:
        return _region_var.get()

    @classmethod
    def set(cls, region: str) -> contextvars.Token[str | None]:
        return _region_var.set(region)

    @classmethod
    @contextmanager
    def scoped(cls, region: str) -> Iterator[str]:
        """Context manager that sets the region for the duration of a block."""
        token = _region_var.set(region)
        try:
            yield region
        finally:
            _region_var.reset(token)

    @classmethod
    def validate(cls, region: str, allowed: list[str] | None = None) -> None:
        """Validate a region name against format rules and an optional allowlist.

        Raises RegionValidationError if invalid.
        """
        if not _REGION_PATTERN.match(region):
            raise RegionValidationError(
                region,
                "Must start with lowercase letter, contain only lowercase "
                "alphanumerics and hyphens, and be 2-63 characters",
            )
        if allowed and region not in allowed:
            raise RegionValidationError(
                region,
                f"Not in allowed regions: {', '.join(allowed)}",
            )


@runtime_checkable
class RegionResolver(Protocol):
    """Protocol for resolving the current region from external context."""

    def resolve(self) -> str | None: ...


class StaticRegionResolver:
    """Returns a fixed region value."""

    def __init__(self, region: str) -> None:
        self._region = region

    def resolve(self) -> str | None:
        return self._region


class HeaderRegionResolver:
    """Resolves region from an HTTP header in a request-like mapping."""

    def __init__(self, headers: dict[str, str], header_name: str = "X-CockroachDB-Region") -> None:
        self._headers = headers
        self._header_name = header_name

    def resolve(self) -> str | None:
        return self._headers.get(self._header_name)
