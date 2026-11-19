"""Fast unit test for multi-region — no Docker, no database.

Covers the decorator metadata (``@regional_by_row``, ``@crdb_region``), the
``RegionContext`` scope, and region-name validation. The REGIONAL BY ROW writes
need a multi-region cluster and are gated in ``test_regional_it.py``.
"""

from __future__ import annotations

import pytest

import regional_service as rs
from cockroachdb.core import RegionContext
from cockroachdb.exceptions import RegionValidationError


# tag::regional-unit-test[]
def test_regional_by_row_marks_entity() -> None:
    assert rs.RegionalIdea.__crdb_regional_by_row__ is True
    assert rs.RegionalIdea.__crdb_default_region__ == "us-east1"


def test_crdb_region_decorator_pins_region() -> None:
    assert rs.add_in_us_east.__crdb_region__ == "us-east1"
    assert rs.add_in_us_west.__crdb_region__ == "us-west1"


def test_region_context_scopes_and_resets() -> None:
    assert RegionContext.current() is None
    with RegionContext.scoped("us-west1"):
        assert RegionContext.current() == "us-west1"
    assert RegionContext.current() is None


def test_region_validation_rejects_bad_names() -> None:
    RegionContext.validate("us-east1")  # valid — no raise
    with pytest.raises(RegionValidationError):
        RegionContext.validate("US_EAST!")
# end::regional-unit-test[]
