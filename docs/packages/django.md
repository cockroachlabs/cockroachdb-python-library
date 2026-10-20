# cockroachdb-django

Django integration with region-aware middleware, model mixins, retry utilities, and database router for CockroachDB.

```bash
pip install cockroachdb-django
```

**Depends on:** `cockroachdb-core`, `django`

## Installation

```bash
pip install cockroachdb-django
```

Or with the monorepo:

```bash
pip install cockroachdb[django]
```

## Settings Configuration

Add the CockroachDB configuration to your Django `settings.py`:

```python
from cockroachdb.django import configure_cockroachdb

DATABASES = {
    "default": configure_cockroachdb(
        {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "defaultdb",
            "HOST": "localhost",
            "PORT": "26257",
            "USER": "root",
        }
    ),
    "follower": configure_cockroachdb(
        {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "defaultdb",
            "HOST": "follower.localhost",
            "PORT": "26257",
            "USER": "root",
        }
    ),
}

COCKROACHDB = {
    "REGION_HEADER": "X-CockroachDB-Region",
    "FOLLOWER_READ_SAFE_METHODS": ["GET", "HEAD"],
}
```

`configure_cockroachdb()` applies CockroachDB-optimal defaults:

- `CONN_MAX_AGE = 600` — persistent connections
- `OPTIONS.sslmode = "verify-full"` — secure by default
- `ATOMIC_REQUESTS = False` — avoids implicit transactions

## Middleware

`CockroachDBMiddleware` extracts the region from a request header and activates `RegionContext` and optionally `FollowerReadContext` for the request lifecycle.

```python
MIDDLEWARE = [
    "cockroachdb.django.CockroachDBMiddleware",
    "django.middleware.common.CommonMiddleware",
    # ...
]
```

Configuration options in `settings.COCKROACHDB`:

| Key | Default | Description |
|-----|---------|-------------|
| `REGION_HEADER` | `"X-CockroachDB-Region"` | HTTP header for region extraction |
| `FOLLOWER_READ_SAFE_METHODS` | `["GET", "HEAD"]` | Methods that activate follower reads |

## Model Mixins

### RegionalByRowMixin

Adds a `crdb_region` CharField for CockroachDB REGIONAL BY ROW tables:

```python
from django.db import models
from cockroachdb.django import RegionalByRowMixin


class Order(RegionalByRowMixin, models.Model):
    customer = models.CharField(max_length=200)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta(RegionalByRowMixin.Meta):
        db_table = "orders"
```

### GlobalTableMixin

Marks a table as GLOBAL for low-latency reads from any region:

```python
from cockroachdb.django import GlobalTableMixin


class Product(GlobalTableMixin, models.Model):
    name = models.CharField(max_length=200)

    class Meta(GlobalTableMixin.Meta):
        db_table = "products"
```

### TimestampMixin

Adds `created_at` and `updated_at` DateTimeFields:

```python
from cockroachdb.django import TimestampMixin


class Event(TimestampMixin, models.Model):
    name = models.CharField(max_length=200)
```

## Retry Utilities

### execute_with_retry

Wraps a callable with automatic retry on serialization errors (SQLSTATE 40001):

```python
from cockroachdb.django import execute_with_retry


def transfer():
    sender = Account.objects.select_for_update().get(pk=1)
    sender.balance -= 100
    sender.save()


execute_with_retry(transfer, max_retries=5)
```

### atomic_with_retry

Decorator that wraps a function in `transaction.atomic()` with retry:

```python
from cockroachdb.django import atomic_with_retry


@atomic_with_retry(max_retries=3)
def create_order(name, total):
    return Order.objects.create(customer=name, total=total)
```

Can also be used as a context manager (note: the context manager form wraps a single atomic block but cannot re-execute the body on retry — use the decorator form for full retry support):

```python
with atomic_with_retry():
    Order.objects.create(customer="Alice", total=99.99)
```

## Database Router

`CockroachDBRouter` routes reads and writes based on active context:

```python
DATABASE_ROUTERS = ["cockroachdb.django.CockroachDBRouter"]
```

| Context | Reads | Writes |
|---------|-------|--------|
| None | `default` | `default` |
| `FollowerReadContext` active | `follower` | `default` |
| `RegionContext("us-east1")` | `us-east1` | `us-east1` |
| Both active | `follower` | `us-east1` |

## Signals

Django signals are emitted during retry lifecycle events:

```python
from cockroachdb.django.signals import (
    pre_cockroachdb_retry,
    post_cockroachdb_retry,
    cockroachdb_retry_exhausted,
)


def on_retry(sender, attempt, error, **kwargs):
    print(f"Retry attempt {attempt}: {error}")


pre_cockroachdb_retry.connect(on_retry)
```

| Signal | Kwargs | When |
|--------|--------|------|
| `pre_cockroachdb_retry` | `attempt`, `error` | Before each retry |
| `post_cockroachdb_retry` | `attempts` | After successful retry |
| `cockroachdb_retry_exhausted` | `error` | All retries exhausted |

## API Summary

| Symbol | Type | Description |
|--------|------|-------------|
| `CockroachDBMiddleware` | middleware | Region + follower read context |
| `CockroachDBRouter` | router | Context-aware database routing |
| `RegionalByRowMixin` | mixin | Adds `crdb_region` column |
| `GlobalTableMixin` | mixin | Marks table as `GLOBAL` |
| `TimestampMixin` | mixin | Adds `created_at` / `updated_at` |
| `execute_with_retry` | function | Retry wrapper for callables |
| `atomic_with_retry` | class | Retry + `transaction.atomic()` |
| `configure_cockroachdb` | function | Apply CRDB defaults to DATABASES |
| `pre_cockroachdb_retry` | signal | Before retry attempt |
| `post_cockroachdb_retry` | signal | After successful retry |
| `cockroachdb_retry_exhausted` | signal | Retries exhausted |
