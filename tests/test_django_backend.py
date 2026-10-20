"""Tests for cockroachdb.django.backend — database router and configuration."""

from __future__ import annotations

from unittest.mock import MagicMock

from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.core.region import RegionContext
from cockroachdb.django.backend import CockroachDBRouter, configure_cockroachdb


class TestCockroachDBRouter:
    """Tests for CockroachDBRouter."""

    def test_db_for_read_defaults_to_default(self) -> None:
        """Without any context, reads go to 'default'."""
        router = CockroachDBRouter()
        result = router.db_for_read(MagicMock)
        assert result == "default"

    def test_db_for_write_defaults_to_default(self) -> None:
        """Without any context, writes go to 'default'."""
        router = CockroachDBRouter()
        result = router.db_for_write(MagicMock)
        assert result == "default"

    def test_db_for_read_uses_follower_when_active(self) -> None:
        """Reads route to 'follower' when FollowerReadContext is active."""
        router = CockroachDBRouter()
        with FollowerReadContext.scoped():
            result = router.db_for_read(MagicMock)
        assert result == "follower"

    def test_db_for_write_ignores_follower_context(self) -> None:
        """Writes always ignore FollowerReadContext."""
        router = CockroachDBRouter()
        with FollowerReadContext.scoped():
            result = router.db_for_write(MagicMock)
        assert result == "default"

    def test_db_for_read_uses_region_when_active(self) -> None:
        """Reads route to the region database when RegionContext is active."""
        router = CockroachDBRouter()
        with RegionContext.scoped("us-east1"):
            result = router.db_for_read(MagicMock)
        assert result == "us-east1"

    def test_db_for_write_uses_region_when_active(self) -> None:
        """Writes route to the region database when RegionContext is active."""
        router = CockroachDBRouter()
        with RegionContext.scoped("eu-west1"):
            result = router.db_for_write(MagicMock)
        assert result == "eu-west1"

    def test_db_for_read_follower_takes_precedence_over_region(self) -> None:
        """FollowerReadContext takes precedence over RegionContext for reads."""
        router = CockroachDBRouter()
        with RegionContext.scoped("us-east1"), FollowerReadContext.scoped():
            result = router.db_for_read(MagicMock)
        assert result == "follower"

    def test_custom_follower_db_alias(self) -> None:
        """Custom follower_db alias is used when specified."""
        router = CockroachDBRouter(follower_db="read-replica")
        with FollowerReadContext.scoped():
            result = router.db_for_read(MagicMock)
        assert result == "read-replica"

    def test_custom_default_db_alias(self) -> None:
        """Custom default_db alias is used when specified."""
        router = CockroachDBRouter(default_db="primary")
        result = router.db_for_read(MagicMock)
        assert result == "primary"

    def test_allow_relation_returns_true(self) -> None:
        """allow_relation always returns True."""
        router = CockroachDBRouter()
        assert router.allow_relation(MagicMock(), MagicMock()) is True

    def test_allow_migrate_returns_true(self) -> None:
        """allow_migrate always returns True."""
        router = CockroachDBRouter()
        assert router.allow_migrate("default", "myapp") is True


class TestConfigureCockroachDB:
    """Tests for configure_cockroachdb."""

    def test_sets_conn_max_age(self) -> None:
        """CONN_MAX_AGE is set to the default."""
        result = configure_cockroachdb({"ENGINE": "django.db.backends.postgresql"})
        assert result["CONN_MAX_AGE"] == 600

    def test_preserves_user_conn_max_age(self) -> None:
        """User-specified CONN_MAX_AGE is not overwritten."""
        result = configure_cockroachdb(
            {
                "ENGINE": "django.db.backends.postgresql",
                "CONN_MAX_AGE": 300,
            }
        )
        assert result["CONN_MAX_AGE"] == 300

    def test_sets_default_options(self) -> None:
        """Default OPTIONS include sslmode."""
        result = configure_cockroachdb({"ENGINE": "django.db.backends.postgresql"})
        assert "sslmode" in result["OPTIONS"]
        assert result["OPTIONS"]["sslmode"] == "verify-full"

    def test_merges_user_options(self) -> None:
        """User OPTIONS are merged with defaults (user takes precedence)."""
        result = configure_cockroachdb(
            {
                "ENGINE": "django.db.backends.postgresql",
                "OPTIONS": {"sslmode": "require", "connect_timeout": 10},
            }
        )
        assert result["OPTIONS"]["sslmode"] == "require"
        assert result["OPTIONS"]["connect_timeout"] == 10
        # Default 'options' key should still be present
        assert "options" in result["OPTIONS"]

    def test_preserves_all_user_settings(self) -> None:
        """User settings like ENGINE, NAME, HOST are preserved."""
        user = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "mydb",
            "HOST": "myhost",
            "PORT": "26257",
        }
        result = configure_cockroachdb(user)
        assert result["ENGINE"] == "django.db.backends.postgresql"
        assert result["NAME"] == "mydb"
        assert result["HOST"] == "myhost"
        assert result["PORT"] == "26257"

    def test_does_not_mutate_input(self) -> None:
        """The input dict is not mutated."""
        original = {"ENGINE": "django.db.backends.postgresql"}
        original_copy = dict(original)
        configure_cockroachdb(original)
        assert original == original_copy

    def test_sets_atomic_requests_false(self) -> None:
        """ATOMIC_REQUESTS defaults to False for CockroachDB."""
        result = configure_cockroachdb({"ENGINE": "django.db.backends.postgresql"})
        assert result["ATOMIC_REQUESTS"] is False
