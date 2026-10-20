"""Django ORM model mixins for CockroachDB multi-region tables.

Provides reusable mixins that add CockroachDB-specific columns and
``Meta`` options to Django models, mirroring the SQLAlchemy mixins in
``cockroachdb.sqla.mixins``.

Example::

    from django.db import models
    from cockroachdb.django import RegionalByRowMixin, GlobalTableMixin

    class Order(RegionalByRowMixin, models.Model):
        total = models.DecimalField(max_digits=10, decimal_places=2)

        class Meta(RegionalByRowMixin.Meta):
            db_table = "orders"

    class Product(GlobalTableMixin, models.Model):
        name = models.CharField(max_length=200)

        class Meta(GlobalTableMixin.Meta):
            db_table = "products"
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class RegionalByRowMixin(models.Model):
    """Mixin for CockroachDB REGIONAL BY ROW tables.

    Adds a ``crdb_region`` column and sets ``Meta`` to include the
    CockroachDB locality configuration.  Models inheriting this mixin
    will have their rows distributed across regions based on the value
    of ``crdb_region``.

    Subclasses should inherit from both this mixin and ``models.Model``
    and extend ``Meta`` from ``RegionalByRowMixin.Meta``.
    """

    crdb_region = models.CharField(
        max_length=63,
        db_index=True,
        help_text="CockroachDB region for row-level locality.",
    )

    crdb_locality = "REGIONAL BY ROW"

    class Meta:
        abstract = True


class GlobalTableMixin(models.Model):
    """Mixin for CockroachDB GLOBAL tables.

    Marks the table as globally replicated.  Global tables are readable
    from any region with low latency but incur higher write latency
    because writes must propagate to all regions.
    """

    crdb_locality = "GLOBAL"

    class Meta:
        abstract = True


class TimestampMixin(models.Model):
    """Mixin that adds ``created_at`` and ``updated_at`` timestamp fields.

    Common pattern in CockroachDB applications for tracking record
    lifecycle.  Uses ``auto_now_add`` and ``auto_now`` respectively.
    """

    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        help_text="Timestamp when the record was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when the record was last updated.",
    )

    class Meta:
        abstract = True
