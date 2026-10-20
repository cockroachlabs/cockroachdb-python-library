"""Tests for cockroachdb.core.region.RegionContext."""

from __future__ import annotations

import pytest

from cockroachdb.core.region import RegionContext
from cockroachdb.exceptions import RegionValidationError


class TestRegionContextCurrent:
    """Tests for RegionContext.current() and .set()."""

    def test_default_is_none(self) -> None:
        # Reset to ensure clean state
        RegionContext.set(None)  # type: ignore[arg-type]
        try:
            assert RegionContext.current() is None
        finally:
            pass

    def test_set_and_current(self) -> None:
        RegionContext.set("us-east1")
        try:
            assert RegionContext.current() == "us-east1"
        finally:
            # Clean up by resetting
            RegionContext.set(None)  # type: ignore[arg-type]

    def test_set_returns_token(self) -> None:
        token = RegionContext.set("eu-west1")
        assert token is not None
        RegionContext.set(None)  # type: ignore[arg-type]


class TestRegionContextScoped:
    """Tests for RegionContext.scoped() context manager."""

    def test_scoped_sets_region(self) -> None:
        with RegionContext.scoped("us-east1") as region:
            assert region == "us-east1"
            assert RegionContext.current() == "us-east1"

    def test_scoped_restores_previous(self) -> None:
        RegionContext.set(None)  # type: ignore[arg-type]
        with RegionContext.scoped("us-east1"):
            assert RegionContext.current() == "us-east1"
        assert RegionContext.current() is None

    def test_nested_scoped(self) -> None:
        with RegionContext.scoped("us-east1"):
            assert RegionContext.current() == "us-east1"
            with RegionContext.scoped("eu-west1"):
                assert RegionContext.current() == "eu-west1"
            assert RegionContext.current() == "us-east1"


class TestRegionContextValidate:
    """Tests for RegionContext.validate()."""

    def test_valid_region_names(self) -> None:
        # Should not raise
        RegionContext.validate("us-east1")
        RegionContext.validate("eu-west1")
        RegionContext.validate("ap-southeast-2")
        RegionContext.validate("us")

    def test_invalid_region_uppercase(self) -> None:
        with pytest.raises(RegionValidationError):
            RegionContext.validate("US-EAST1")

    def test_invalid_region_starts_with_number(self) -> None:
        with pytest.raises(RegionValidationError):
            RegionContext.validate("1-us-east")

    def test_invalid_region_special_chars(self) -> None:
        with pytest.raises(RegionValidationError):
            RegionContext.validate("us_east.1")

    def test_invalid_region_single_char(self) -> None:
        with pytest.raises(RegionValidationError):
            RegionContext.validate("u")

    def test_valid_region_with_allowlist(self) -> None:
        RegionContext.validate("us-east1", allowed=["us-east1", "eu-west1"])

    def test_invalid_region_not_in_allowlist(self) -> None:
        with pytest.raises(RegionValidationError):
            RegionContext.validate("ap-south1", allowed=["us-east1", "eu-west1"])

    def test_empty_allowlist_allows_any_valid_format(self) -> None:
        # Empty list is falsy, so no allowlist check
        RegionContext.validate("us-east1", allowed=[])
