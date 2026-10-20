"""vCluster session-tagging context for CockroachDB workload isolation.

Mirrors :class:`~cockroachdb.core.follower_read.FollowerReadContext`: the
low-level contextvar and settings live in the engine layer so the template can
apply them at transaction start, while the customer-facing API (``Priority``,
``vcluster``, ``virtual_cluster``) lives in ``cockroachdb.continuum``.

When a vCluster is active, the template issues ``SET LOCAL application_name``
and ``SET LOCAL default_transaction_quality_of_service`` before running the
transaction body, tagging the workload and steering its quality-of-service.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True)
class VClusterSettings:
    """Session settings a vCluster applies to a transaction.

    ``application_name`` tags the workload for observability; ``quality_of_service``
    is one of CockroachDB's admission-control tiers (``background``/``regular``/
    ``critical``).
    """

    application_name: str
    quality_of_service: str


_vcluster_var: contextvars.ContextVar[VClusterSettings | None] = contextvars.ContextVar(
    "cockroachdb_vcluster", default=None
)


class VClusterContext:
    """Thread-safe vCluster context backed by contextvars.

    Correct across threads, asyncio tasks, and framework request scopes. The
    template reads :meth:`current` at transaction start and, when non-``None``,
    applies the session settings for the duration of that transaction.
    """

    @classmethod
    def current(cls) -> VClusterSettings | None:
        return _vcluster_var.get()

    @classmethod
    def set(cls, settings: VClusterSettings) -> contextvars.Token[VClusterSettings | None]:
        return _vcluster_var.set(settings)

    @classmethod
    @contextmanager
    def scoped(cls, settings: VClusterSettings) -> Iterator[VClusterSettings]:
        """Activate ``settings`` for the duration of the block."""
        token = _vcluster_var.set(settings)
        try:
            yield settings
        finally:
            _vcluster_var.reset(token)
