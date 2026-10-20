"""Tests for cockroachdb.core.classifier.PsycopgExceptionClassifier."""

from __future__ import annotations

from conftest import (
    FakeDeadlockError,
    FakeNonRetryableError,
    FakeRetryableError,
    FakeRetryableErrorPgcode,
    FakeWrappedRetryableError,
)

from cockroachdb.core.classifier import PsycopgExceptionClassifier


class TestPsycopgExceptionClassifierIsRetryable:
    """Tests for PsycopgExceptionClassifier.is_retryable()."""

    def setup_method(self) -> None:
        self.classifier = PsycopgExceptionClassifier()

    def test_retryable_with_sqlstate_40001(self) -> None:
        assert self.classifier.is_retryable(FakeRetryableError()) is True

    def test_retryable_with_pgcode_40001(self) -> None:
        assert self.classifier.is_retryable(FakeRetryableErrorPgcode()) is True

    def test_retryable_with_deadlock(self) -> None:
        assert self.classifier.is_retryable(FakeDeadlockError()) is True

    def test_not_retryable_generic_error(self) -> None:
        assert self.classifier.is_retryable(FakeNonRetryableError()) is False

    def test_not_retryable_plain_exception(self) -> None:
        assert self.classifier.is_retryable(ValueError("nope")) is False

    def test_retryable_via_cause_chain(self) -> None:
        assert self.classifier.is_retryable(FakeWrappedRetryableError()) is True


class TestPsycopgExceptionClassifierIsSerializationError:
    """Tests for PsycopgExceptionClassifier.is_serialization_error()."""

    def setup_method(self) -> None:
        self.classifier = PsycopgExceptionClassifier()

    def test_serialization_error_40001(self) -> None:
        assert self.classifier.is_serialization_error(FakeRetryableError()) is True

    def test_deadlock_is_not_serialization(self) -> None:
        # 40P01 is retryable but not a serialization error
        assert self.classifier.is_serialization_error(FakeDeadlockError()) is False

    def test_generic_is_not_serialization(self) -> None:
        assert self.classifier.is_serialization_error(ValueError("nope")) is False


class TestPsycopgExceptionClassifierProtocol:
    """Tests that PsycopgExceptionClassifier matches the ExceptionClassifier protocol."""

    def test_has_is_retryable(self) -> None:
        classifier = PsycopgExceptionClassifier()
        assert callable(getattr(classifier, "is_retryable", None))

    def test_has_is_serialization_error(self) -> None:
        classifier = PsycopgExceptionClassifier()
        assert callable(getattr(classifier, "is_serialization_error", None))

    def test_implements_protocol(self) -> None:
        from cockroachdb.types import ExceptionClassifier

        classifier = PsycopgExceptionClassifier()
        assert isinstance(classifier, ExceptionClassifier)
