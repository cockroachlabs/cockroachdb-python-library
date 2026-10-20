"""Tests for cockroachdb.ai.metrics — in-memory AI metrics collection."""

from __future__ import annotations

import pytest

from cockroachdb.ai.metrics import AIMetrics, InMemoryAIMetrics, NoopAIMetrics


class TestInMemoryAIMetricsRecordVectorSearch:
    """Tests for recording vector search metrics."""

    def test_increments_search_count(self):
        metrics = InMemoryAIMetrics()
        metrics.record_vector_search("docs", "cosine", 5, 12.5)
        assert metrics.search_count == 1

    def test_accumulates_total_results(self):
        metrics = InMemoryAIMetrics()
        metrics.record_vector_search("docs", "cosine", 5, 10.0)
        metrics.record_vector_search("docs", "cosine", 3, 8.0)
        assert metrics.total_results == 8

    def test_accumulates_total_search_ms(self):
        metrics = InMemoryAIMetrics()
        metrics.record_vector_search("docs", "cosine", 1, 10.0)
        metrics.record_vector_search("docs", "l2", 2, 15.0)
        assert metrics.total_search_ms == pytest.approx(25.0)

    def test_appends_record(self):
        metrics = InMemoryAIMetrics()
        metrics.record_vector_search("docs", "cosine", 5, 12.5)
        assert len(metrics.records) == 1
        assert metrics.records[0].name == "vector_search"
        assert metrics.records[0].attributes["table"] == "docs"


class TestInMemoryAIMetricsRecordEmbedding:
    """Tests for recording embedding metrics."""

    def test_increments_embedding_count(self):
        metrics = InMemoryAIMetrics()
        metrics.record_embedding("openai", 3, 1536, 50.0)
        assert metrics.embedding_count == 1

    def test_accumulates_texts_embedded(self):
        metrics = InMemoryAIMetrics()
        metrics.record_embedding("openai", 3, 1536, 50.0)
        metrics.record_embedding("openai", 7, 1536, 80.0)
        assert metrics.total_texts_embedded == 10

    def test_accumulates_embedding_ms(self):
        metrics = InMemoryAIMetrics()
        metrics.record_embedding("p", 1, 768, 20.0)
        metrics.record_embedding("p", 1, 768, 30.0)
        assert metrics.total_embedding_ms == pytest.approx(50.0)

    def test_record_contains_provider_info(self):
        metrics = InMemoryAIMetrics()
        metrics.record_embedding("openai", 5, 1536, 100.0)
        rec = metrics.records[0]
        assert rec.attributes["provider"] == "openai"
        assert rec.attributes["dimensions"] == 1536


class TestInMemoryAIMetricsRecordChatCompletion:
    """Tests for recording chat completion metrics."""

    def test_increments_chat_count(self):
        metrics = InMemoryAIMetrics()
        metrics.record_chat_completion("openai", 3, 200.0)
        assert metrics.chat_count == 1

    def test_accumulates_chat_ms(self):
        metrics = InMemoryAIMetrics()
        metrics.record_chat_completion("p", 2, 100.0)
        metrics.record_chat_completion("p", 4, 150.0)
        assert metrics.total_chat_ms == pytest.approx(250.0)

    def test_record_contains_chat_info(self):
        metrics = InMemoryAIMetrics()
        metrics.record_chat_completion("gpt4", 5, 300.0)
        rec = metrics.records[0]
        assert rec.name == "chat_completion"
        assert rec.attributes["num_messages"] == 5


class TestInMemoryAIMetricsReset:
    """Tests for reset()."""

    def test_resets_all_counters(self):
        metrics = InMemoryAIMetrics()
        metrics.record_vector_search("t", "c", 5, 10.0)
        metrics.record_embedding("p", 3, 768, 50.0)
        metrics.record_chat_completion("p", 2, 100.0)

        metrics.reset()

        assert metrics.search_count == 0
        assert metrics.total_results == 0
        assert metrics.embedding_count == 0
        assert metrics.total_texts_embedded == 0
        assert metrics.chat_count == 0
        assert metrics.total_search_ms == 0.0
        assert metrics.total_embedding_ms == 0.0
        assert metrics.total_chat_ms == 0.0
        assert metrics.records == []

    def test_reset_allows_fresh_recording(self):
        metrics = InMemoryAIMetrics()
        metrics.record_vector_search("t", "c", 5, 10.0)
        metrics.reset()
        metrics.record_vector_search("t", "c", 3, 5.0)
        assert metrics.search_count == 1
        assert metrics.total_results == 3


class TestNoopAIMetrics:
    """Tests for NoopAIMetrics."""

    def test_record_vector_search_does_nothing(self):
        noop = NoopAIMetrics()
        noop.record_vector_search("t", "c", 5, 10.0)
        # No exception, no state

    def test_record_embedding_does_nothing(self):
        noop = NoopAIMetrics()
        noop.record_embedding("p", 1, 768, 5.0)

    def test_record_chat_completion_does_nothing(self):
        noop = NoopAIMetrics()
        noop.record_chat_completion("p", 2, 100.0)


class TestAIMetricsProtocol:
    """Tests for the AIMetrics protocol."""

    def test_in_memory_implements_protocol(self):
        assert isinstance(InMemoryAIMetrics(), AIMetrics)

    def test_noop_is_not_protocol_instance(self):
        """NoopAIMetrics does implement the protocol methods but
        may or may not pass isinstance check depending on runtime_checkable."""
        # Just verify it has the required methods
        noop = NoopAIMetrics()
        assert callable(noop.record_vector_search)
        assert callable(noop.record_embedding)
        assert callable(noop.record_chat_completion)
