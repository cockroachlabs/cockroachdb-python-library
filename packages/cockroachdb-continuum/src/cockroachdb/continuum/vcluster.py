"""Cockroach vCluster — workload routing & isolation (tagging + QoS).

v1 tags each transaction with an ``application_name`` and steers its
admission-control quality-of-service. Endpoint routing is a future increment;
today activating a vCluster makes the core template issue
``SET LOCAL application_name`` and ``SET LOCAL default_transaction_quality_of_service``
at transaction start.

Usage::

    with vcluster("analytics-batch", priority=Priority.LOW):
        template.execute(run_report)

    @virtual_cluster("checkout", priority=Priority.HIGH)
    def place_order() -> None:
        ...
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, TypeVar

from cockroachdb.core.vcluster import VClusterContext, VClusterSettings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

F = TypeVar("F", bound="Callable[..., object]")


class Priority(Enum):
    """Workload priority mapped to a CockroachDB quality-of-service tier."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"

    @property
    def qos(self) -> str:
        """The ``default_transaction_quality_of_service`` value for this priority."""
        return {
            Priority.LOW: "background",
            Priority.NORMAL: "regular",
            Priority.HIGH: "critical",
        }[self]


@contextmanager
def vcluster(name: str, priority: Priority = Priority.NORMAL) -> Iterator[VClusterSettings]:
    """Activate a vCluster for the duration of the block.

    Transactions executed through the core template while this is active are
    tagged with ``name`` (as ``application_name``) and run at ``priority``'s
    quality-of-service.
    """
    settings = VClusterSettings(application_name=name, quality_of_service=priority.qos)
    with VClusterContext.scoped(settings) as active:
        yield active


def virtual_cluster(name: str, priority: Priority = Priority.NORMAL) -> Callable[[F], F]:
    """Decorator form of :func:`vcluster` that wraps a callable's execution."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            with vcluster(name, priority):
                return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
