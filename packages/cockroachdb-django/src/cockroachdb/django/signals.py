"""Django signals for CockroachDB retry events.

These signals allow application code to observe retry lifecycle events
without coupling to the retry implementation.  Useful for logging,
metrics collection, and alerting.

Example::

    from cockroachdb.django.signals import pre_cockroachdb_retry

    def on_retry(sender, attempt, error, **kwargs):
        print(f"Retrying {sender.__name__}, attempt {attempt}: {error}")

    pre_cockroachdb_retry.connect(on_retry)
"""

from __future__ import annotations

from django.dispatch import Signal

# Sent before a retry attempt.
# sender: the callable being retried
# attempt: int — the retry attempt number (1-based)
# error: Exception — the error that triggered the retry
pre_cockroachdb_retry = Signal()

# Sent after a successful retry (i.e., the operation eventually succeeded).
# sender: the callable that was retried
# attempts: int — total number of attempts (including the successful one)
post_cockroachdb_retry = Signal()

# Sent when all retry attempts are exhausted.
# sender: the callable that was retried
# error: Exception — the last error before giving up
cockroachdb_retry_exhausted = Signal()
