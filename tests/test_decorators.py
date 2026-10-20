"""Tests for cockroachdb.decorators."""

from __future__ import annotations

import pytest
from conftest import FakeNonRetryableError, FakeRetryableError

from cockroachdb.decorators import (
    changefeed_handler,
    crdb_region,
    crdb_retry,
    follower_read,
    global_table,
    regional_by_row,
    semantic_search,
    vector_search,
)
from cockroachdb.exceptions import CockroachDBRetryExhausted
from cockroachdb.types import IsolationLevel


class TestCrdbRetrySync:
    """Tests for @crdb_retry on synchronous functions."""

    def test_succeeds_without_retry(self) -> None:
        @crdb_retry(max_retries=3, base_delay=0.0)
        def work() -> str:
            return "ok"

        assert work() == "ok"

    def test_retries_on_40001_then_succeeds(self) -> None:
        call_count = 0

        @crdb_retry(max_retries=3, base_delay=0.0)
        def work() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise FakeRetryableError()
            return "ok"

        assert work() == "ok"
        assert call_count == 3

    def test_raises_non_retryable_immediately(self) -> None:
        @crdb_retry(max_retries=3, base_delay=0.0)
        def work() -> str:
            raise FakeNonRetryableError("fail")

        with pytest.raises(FakeNonRetryableError):
            work()

    def test_exhaustion_raises_retry_exhausted(self) -> None:
        @crdb_retry(max_retries=2, base_delay=0.0)
        def work() -> str:
            raise FakeRetryableError()

        with pytest.raises(CockroachDBRetryExhausted) as exc_info:
            work()
        assert exc_info.value.max_retries == 2

    def test_on_retry_callback_invoked(self) -> None:
        attempts: list[int] = []

        def on_retry(attempt: int, error: Exception) -> None:
            attempts.append(attempt)

        call_count = 0

        @crdb_retry(max_retries=3, base_delay=0.0, on_retry=on_retry)
        def work() -> str:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise FakeRetryableError()
            return "done"

        work()
        assert attempts == [1, 2]

    def test_sets_crdb_retry_attribute(self) -> None:
        @crdb_retry()
        def work() -> None:
            pass

        assert getattr(work, "__crdb_retry__", False) is True

    def test_sets_isolation_attribute(self) -> None:
        @crdb_retry(isolation=IsolationLevel.READ_COMMITTED)
        def work() -> None:
            pass

        assert work.__crdb_isolation__ == IsolationLevel.READ_COMMITTED


class TestCrdbRetryAsync:
    """Tests for @crdb_retry on async functions."""

    @pytest.mark.asyncio
    async def test_async_succeeds(self) -> None:
        @crdb_retry(max_retries=3, base_delay=0.0)
        async def work() -> str:
            return "async_ok"

        result = await work()
        assert result == "async_ok"

    @pytest.mark.asyncio
    async def test_async_retries_on_40001(self) -> None:
        call_count = 0

        @crdb_retry(max_retries=3, base_delay=0.0)
        async def work() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise FakeRetryableError()
            return "ok"

        assert await work() == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_exhaustion(self) -> None:
        @crdb_retry(max_retries=1, base_delay=0.0)
        async def work() -> str:
            raise FakeRetryableError()

        with pytest.raises(CockroachDBRetryExhausted):
            await work()

    @pytest.mark.asyncio
    async def test_async_non_retryable_raises_immediately(self) -> None:
        @crdb_retry(max_retries=3, base_delay=0.0)
        async def work() -> str:
            raise FakeNonRetryableError("fail")

        with pytest.raises(FakeNonRetryableError):
            await work()


class TestFollowerRead:
    """Tests for @follower_read decorator."""

    def test_sets_default_staleness(self) -> None:
        @follower_read()
        def query() -> None:
            pass

        assert query.__crdb_follower_read__ == "follower_read_timestamp()"

    def test_sets_custom_staleness(self) -> None:
        @follower_read(staleness="-5s")
        def query() -> None:
            pass

        assert query.__crdb_follower_read__ == "-5s"

    def test_function_still_callable(self) -> None:
        @follower_read()
        def query() -> str:
            return "data"

        assert query() == "data"


class TestCrdbRegion:
    """Tests for @crdb_region decorator."""

    def test_sets_region_attribute(self) -> None:
        @crdb_region("us-east1")
        def work() -> None:
            pass

        assert work.__crdb_region__ == "us-east1"

    def test_function_still_callable(self) -> None:
        @crdb_region("eu-west1")
        def work() -> str:
            return "regional"

        assert work() == "regional"

    def test_different_regions(self) -> None:
        @crdb_region("ap-southeast1")
        def work() -> None:
            pass

        assert work.__crdb_region__ == "ap-southeast1"


class TestRegionalByRow:
    """Tests for @regional_by_row class decorator."""

    def test_sets_attribute(self) -> None:
        @regional_by_row()
        class MyTable:
            pass

        assert MyTable.__crdb_regional_by_row__ is True

    def test_sets_default_region(self) -> None:
        @regional_by_row(default_region="us-east1")
        class MyTable:
            pass

        assert MyTable.__crdb_default_region__ == "us-east1"

    def test_no_default_region(self) -> None:
        @regional_by_row()
        class MyTable:
            pass

        assert MyTable.__crdb_default_region__ is None


class TestGlobalTable:
    """Tests for @global_table class decorator."""

    def test_sets_attribute(self) -> None:
        @global_table
        class RefData:
            pass

        assert RefData.__crdb_global_table__ is True

    def test_class_still_instantiable(self) -> None:
        @global_table
        class RefData:
            value: int = 42

        obj = RefData()
        assert obj.value == 42

    def test_returns_same_class(self) -> None:
        class Original:
            pass

        decorated = global_table(Original)
        assert decorated is Original


class TestChangefeedHandler:
    """Tests for @changefeed_handler decorator."""

    def test_sets_changefeed_dict(self) -> None:
        @changefeed_handler(table="orders")
        def handler(event: object) -> None:
            pass

        info = handler.__crdb_changefeed__
        assert info["table"] == "orders"
        assert info["operations"] == ["insert", "update", "delete"]
        assert info["endpoint"] == "/webhooks/orders"

    def test_custom_operations_and_endpoint(self) -> None:
        @changefeed_handler(table="users", operations=["insert"], endpoint="/hooks/users")
        def handler(event: object) -> None:
            pass

        info = handler.__crdb_changefeed__
        assert info["operations"] == ["insert"]
        assert info["endpoint"] == "/hooks/users"

    def test_function_still_callable(self) -> None:
        @changefeed_handler(table="t")
        def handler() -> str:
            return "handled"

        assert handler() == "handled"


class TestVectorSearch:
    """Tests for @vector_search decorator."""

    def test_sets_vector_search_dict(self) -> None:
        @vector_search(table="docs", vector_column="embedding")
        def search(query_vec: list[float]) -> None:
            pass

        info = search.__crdb_vector_search__
        assert info["table"] == "docs"
        assert info["vector_column"] == "embedding"
        assert info["metric"] == "cosine"
        assert info["limit"] == 10

    def test_custom_metric_and_limit(self) -> None:
        @vector_search(table="t", vector_column="v", metric="l2", limit=5)
        def search(query_vec: list[float]) -> None:
            pass

        info = search.__crdb_vector_search__
        assert info["metric"] == "l2"
        assert info["limit"] == 5

    def test_function_still_callable(self) -> None:
        @vector_search(table="t", vector_column="v")
        def search() -> str:
            return "results"

        assert search() == "results"


class TestSemanticSearch:
    """Tests for @semantic_search decorator."""

    def test_sets_semantic_search_dict(self) -> None:
        @semantic_search(table="docs", vector_column="embedding", text_column="content")
        def search(query: str) -> None:
            pass

        info = search.__crdb_semantic_search__
        assert info["table"] == "docs"
        assert info["vector_column"] == "embedding"
        assert info["text_column"] == "content"
        assert info["metric"] == "cosine"
        assert info["limit"] == 10

    def test_custom_params(self) -> None:
        @semantic_search(table="t", vector_column="v", text_column="txt", metric="l2", limit=20)
        def search(query: str) -> None:
            pass

        info = search.__crdb_semantic_search__
        assert info["metric"] == "l2"
        assert info["limit"] == 20

    def test_function_still_callable(self) -> None:
        @semantic_search(table="t", vector_column="v", text_column="txt")
        def search() -> str:
            return "found"

        assert search() == "found"
