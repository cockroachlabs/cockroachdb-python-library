"""Tests for cockroachdb.django.mixins — Django model mixins."""

from __future__ import annotations

from cockroachdb.django.mixins import GlobalTableMixin, RegionalByRowMixin, TimestampMixin


class TestRegionalByRowMixin:
    """Tests for RegionalByRowMixin."""

    def test_has_crdb_region_field(self) -> None:
        """RegionalByRowMixin defines a crdb_region CharField."""
        # Check the field exists on the class
        fields = {f.name: f for f in RegionalByRowMixin._meta.get_fields()}
        assert "crdb_region" in fields

    def test_crdb_region_is_char_field(self) -> None:
        """crdb_region is a CharField."""
        from django.db import models

        fields = {f.name: f for f in RegionalByRowMixin._meta.get_fields()}
        assert isinstance(fields["crdb_region"], models.CharField)

    def test_crdb_region_max_length(self) -> None:
        """crdb_region has max_length=63."""
        fields = {f.name: f for f in RegionalByRowMixin._meta.get_fields()}
        assert fields["crdb_region"].max_length == 63

    def test_crdb_region_has_db_index(self) -> None:
        """crdb_region has db_index=True."""
        fields = {f.name: f for f in RegionalByRowMixin._meta.get_fields()}
        assert fields["crdb_region"].db_index is True

    def test_meta_is_abstract(self) -> None:
        """RegionalByRowMixin.Meta.abstract is True."""
        assert RegionalByRowMixin._meta.abstract is True

    def test_has_crdb_locality(self) -> None:
        """RegionalByRowMixin has crdb_locality class attribute."""
        assert RegionalByRowMixin.crdb_locality == "REGIONAL BY ROW"


class TestGlobalTableMixin:
    """Tests for GlobalTableMixin."""

    def test_meta_is_abstract(self) -> None:
        """GlobalTableMixin.Meta.abstract is True."""
        assert GlobalTableMixin._meta.abstract is True

    def test_has_crdb_locality(self) -> None:
        """GlobalTableMixin has crdb_locality class attribute."""
        assert GlobalTableMixin.crdb_locality == "GLOBAL"

    def test_no_extra_fields(self) -> None:
        """GlobalTableMixin does not add any model fields."""
        # Abstract models with no fields should have empty local fields
        local_fields = [f for f in GlobalTableMixin._meta.get_fields() if hasattr(f, "column")]
        assert len(local_fields) == 0


class TestTimestampMixin:
    """Tests for TimestampMixin."""

    def test_has_created_at_field(self) -> None:
        """TimestampMixin defines a created_at field."""
        fields = {f.name: f for f in TimestampMixin._meta.get_fields()}
        assert "created_at" in fields

    def test_has_updated_at_field(self) -> None:
        """TimestampMixin defines an updated_at field."""
        fields = {f.name: f for f in TimestampMixin._meta.get_fields()}
        assert "updated_at" in fields

    def test_created_at_is_datetime_field(self) -> None:
        """created_at is a DateTimeField."""
        from django.db import models

        fields = {f.name: f for f in TimestampMixin._meta.get_fields()}
        assert isinstance(fields["created_at"], models.DateTimeField)

    def test_updated_at_is_datetime_field(self) -> None:
        """updated_at is a DateTimeField."""
        from django.db import models

        fields = {f.name: f for f in TimestampMixin._meta.get_fields()}
        assert isinstance(fields["updated_at"], models.DateTimeField)

    def test_created_at_not_editable(self) -> None:
        """created_at is not editable."""
        fields = {f.name: f for f in TimestampMixin._meta.get_fields()}
        assert fields["created_at"].editable is False

    def test_updated_at_auto_now(self) -> None:
        """updated_at has auto_now=True."""
        fields = {f.name: f for f in TimestampMixin._meta.get_fields()}
        assert fields["updated_at"].auto_now is True

    def test_meta_is_abstract(self) -> None:
        """TimestampMixin.Meta.abstract is True."""
        assert TimestampMixin._meta.abstract is True
