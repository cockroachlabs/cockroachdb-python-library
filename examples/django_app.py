"""Runnable Django application demonstrating CockroachDB integration.

Showcases every feature of the ``cockroachdb-django`` package in a single
file that you can start with ``python examples/django_app.py runserver``
or exercise via the built-in demo mode (no browser needed).

Features demonstrated:
    - CockroachDBMiddleware — region header extraction, follower-read on safe methods
    - RegionalByRowMixin — per-row region column with crdb_locality marker
    - GlobalTableMixin — globally replicated table marker
    - TimestampMixin — auto-managed created_at / updated_at
    - atomic_with_retry — decorator for serialization-safe writes
    - execute_with_retry — explicit function-level retry
    - CockroachDBRouter — read/write routing by region and follower context
    - Django signals — retry lifecycle observers
    - configure_cockroachdb — database config helper

Prerequisites:
    pip install cockroachdb cockroachdb-core cockroachdb-django django

Usage:
    # Demo mode — exercises all endpoints via Django test client
    python examples/django_app.py

    # Start a real Django dev server
    python examples/django_app.py runserver 8000

    # With a region header
    curl -H "X-CockroachDB-Region: us-east1" http://localhost:8000/orders/
    curl http://localhost:8000/health/
"""

from __future__ import annotations

import json
import logging
import sys

# ---------------------------------------------------------------------------
# 1. Django settings — must happen before django.setup()
# ---------------------------------------------------------------------------
import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY="demo-insecure-key-do-not-use-in-production",
        ROOT_URLCONF=__name__,
        ALLOWED_HOSTS=["*"],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "file:demo?mode=memory&cache=shared",
                "OPTIONS": {"uri": True},
            },
            # The router sends reads to "follower" when FollowerReadContext
            # is active.  Both aliases share the same in-memory SQLite via
            # a shared-cache URI.  In production you'd point the follower
            # to a CockroachDB read-replica:
            #   "follower": configure_cockroachdb({...HOST: "follower.crdb.io"...})
            "follower": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "file:demo?mode=memory&cache=shared",
                "OPTIONS": {"uri": True},
            },
        },
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
        ],
        MIDDLEWARE=[
            "cockroachdb.django.CockroachDBMiddleware",
        ],
        DATABASE_ROUTERS=[
            "cockroachdb.django.CockroachDBRouter",
        ],
        COCKROACHDB={
            "REGION_HEADER": "X-CockroachDB-Region",
            "FOLLOWER_READ_SAFE_METHODS": ["GET", "HEAD"],
        },
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    )

django.setup()

# ---------------------------------------------------------------------------
# 2. Imports — safe after django.setup()
# ---------------------------------------------------------------------------

from django.db import models
from django.http import HttpRequest, JsonResponse
from django.urls import path

from cockroachdb.core.follower_read import FollowerReadContext
from cockroachdb.core.region import RegionContext
from cockroachdb.django.backend import CockroachDBRouter, configure_cockroachdb
from cockroachdb.django.mixins import GlobalTableMixin, RegionalByRowMixin, TimestampMixin
from cockroachdb.django.retry import atomic_with_retry, execute_with_retry
from cockroachdb.django.signals import (
    cockroachdb_retry_exhausted,
    post_cockroachdb_retry,
    pre_cockroachdb_retry,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 3. Models — using CockroachDB mixins
# ---------------------------------------------------------------------------


class Order(RegionalByRowMixin, TimestampMixin, models.Model):
    """An order pinned to a specific CockroachDB region.

    Uses ``RegionalByRowMixin`` so each row has a ``crdb_region`` column,
    and ``TimestampMixin`` for automatic ``created_at`` / ``updated_at``.
    """

    customer = models.CharField(max_length=200)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, default="pending")

    class Meta(RegionalByRowMixin.Meta):
        app_label = "demo"
        db_table = "orders"

    def __str__(self) -> str:
        return f"Order(id={self.pk}, customer={self.customer}, region={self.crdb_region})"

    def to_dict(self) -> dict:
        return {
            "id": self.pk,
            "customer": self.customer,
            "total": str(self.total),
            "status": self.status,
            "crdb_region": self.crdb_region,
            "created_at": str(self.created_at) if self.created_at else None,
            "updated_at": str(self.updated_at) if self.updated_at else None,
        }


class Product(GlobalTableMixin, TimestampMixin, models.Model):
    """A product replicated across all CockroachDB regions.

    Uses ``GlobalTableMixin`` so the table is marked for global
    replication — low-latency reads from any region, higher write latency.
    """

    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta(GlobalTableMixin.Meta):
        app_label = "demo"
        db_table = "products"

    def __str__(self) -> str:
        return f"Product(id={self.pk}, name={self.name})"

    def to_dict(self) -> dict:
        return {
            "id": self.pk,
            "name": self.name,
            "price": str(self.price),
            "crdb_locality": self.crdb_locality,
            "created_at": str(self.created_at) if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# 4. Signal handlers — observe retry lifecycle
# ---------------------------------------------------------------------------


def on_retry(sender, attempt, error, **kwargs):
    logger.warning("[signal] pre_retry: %s attempt %d — %s", sender.__name__, attempt, error)


def on_retry_success(sender, attempts, **kwargs):
    logger.info("[signal] post_retry: %s succeeded after %d attempts", sender.__name__, attempts)


def on_retry_exhausted(sender, error, **kwargs):
    logger.error("[signal] retry_exhausted: %s gave up — %s", sender.__name__, error)


pre_cockroachdb_retry.connect(on_retry)
post_cockroachdb_retry.connect(on_retry_success)
cockroachdb_retry_exhausted.connect(on_retry_exhausted)


# ---------------------------------------------------------------------------
# 5. Views
# ---------------------------------------------------------------------------


def health(request: HttpRequest) -> JsonResponse:
    """Health check showing active context state."""
    router = CockroachDBRouter()
    return JsonResponse(
        {
            "status": "healthy",
            "current_region": RegionContext.current(),
            "follower_read_active": FollowerReadContext.is_active(),
            "read_db": router.db_for_read(Order),
            "write_db": router.db_for_write(Order),
        }
    )


def region_info(request: HttpRequest) -> JsonResponse:
    """Show the region extracted by the middleware."""
    region = RegionContext.current()
    return JsonResponse(
        {
            "region": region,
            "message": f"Serving from region: {region}" if region else "No region set",
            "follower_read": FollowerReadContext.is_active(),
        }
    )


def list_orders(request: HttpRequest) -> JsonResponse:
    """List orders — middleware activates follower read on GET."""
    orders = list(
        Order.objects.all().values(
            "id",
            "customer",
            "total",
            "status",
            "crdb_region",
        )
    )
    return JsonResponse(
        {
            "region": RegionContext.current(),
            "follower_read": FollowerReadContext.is_active(),
            "count": len(orders),
            "orders": orders,
        }
    )


def list_products(request: HttpRequest) -> JsonResponse:
    """List globally replicated products."""
    products = list(Product.objects.all().values("id", "name", "price"))
    return JsonResponse(
        {
            "crdb_locality": Product.crdb_locality,
            "count": len(products),
            "products": products,
        }
    )


@atomic_with_retry(max_retries=3, base_delay=0.05)
def _create_order(customer: str, total: float, region: str) -> Order:
    """Create an order inside a retryable atomic block.

    If CockroachDB raises a serialization conflict (SQLSTATE 40001),
    ``atomic_with_retry`` rolls back and re-executes this function.
    """
    return Order.objects.create(
        customer=customer,
        total=total,
        crdb_region=region,
    )


def create_order(request: HttpRequest) -> JsonResponse:
    """POST endpoint — creates an order with retry-safe writes."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    body = json.loads(request.body) if request.body else {}
    customer = body.get("customer", "Anonymous")
    total = body.get("total", 0.0)
    region = RegionContext.current() or body.get("region", "us-east1")

    order = _create_order(customer, total, region)
    return JsonResponse({"created": order.to_dict()}, status=201)


def transfer(request: HttpRequest) -> JsonResponse:
    """POST endpoint — demonstrates execute_with_retry for explicit retry."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    body = json.loads(request.body) if request.body else {}
    from_id = body.get("from_id")
    to_id = body.get("to_id")
    amount = body.get("amount", 10)

    def do_transfer():
        src = Order.objects.get(pk=from_id)
        dst = Order.objects.get(pk=to_id)
        src.total = float(src.total) - amount
        dst.total = float(dst.total) + amount
        src.save()
        dst.save()
        return {"from": src.to_dict(), "to": dst.to_dict()}

    result = execute_with_retry(do_transfer, max_retries=3)
    return JsonResponse({"transfer": result})


def configure_db_demo(request: HttpRequest) -> JsonResponse:
    """Show what configure_cockroachdb() does to a settings dict."""
    raw = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "defaultdb",
        "HOST": "localhost",
        "PORT": "26257",
        "USER": "root",
    }
    configured = configure_cockroachdb(raw)
    return JsonResponse({"raw": raw, "configured": configured})


# ---------------------------------------------------------------------------
# 6. URL patterns
# ---------------------------------------------------------------------------

urlpatterns = [
    path("health/", health),
    path("region/", region_info),
    path("orders/", list_orders),
    path("orders/create/", create_order),
    path("products/", list_products),
    path("transfer/", transfer),
    path("configure-db/", configure_db_demo),
]


# ---------------------------------------------------------------------------
# 7. Demo runner — exercises all features without a browser
# ---------------------------------------------------------------------------


def run_demo() -> None:
    """Exercise every feature using Django's test client."""
    from django.core.management import call_command
    from django.test import Client

    print("=" * 60)
    print("  CockroachDB Django Demo")
    print("=" * 60)

    # Create tables using SchemaEditor (no migrations needed for a demo)
    print("\n--- Creating tables ---")
    call_command("migrate", verbosity=0)  # base Django tables
    from django.db import connection

    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(Order)
        schema_editor.create_model(Product)
    print("Tables created: orders, products")

    # Seed data
    print("\n--- Seeding data ---")
    Order.objects.create(customer="Alice", total=99.99, crdb_region="us-east1")
    Order.objects.create(customer="Bob", total=149.50, crdb_region="eu-west1")
    Order.objects.create(customer="Charlie", total=250.00, crdb_region="us-east1")
    Product.objects.create(name="Widget", price=19.99)
    Product.objects.create(name="Gadget", price=49.99)
    print(f"  Orders: {Order.objects.count()}")
    print(f"  Products: {Product.objects.count()}")

    client = Client()

    # Health check
    print("\n--- GET /health/ ---")
    resp = client.get("/health/")
    _print_response(resp)

    # Region info (no header)
    print("\n--- GET /region/ (no header) ---")
    resp = client.get("/region/")
    _print_response(resp)

    # Region info (with header)
    print("\n--- GET /region/ (X-CockroachDB-Region: us-east1) ---")
    resp = client.get("/region/", HTTP_X_COCKROACHDB_REGION="us-east1")
    _print_response(resp)

    # List orders (follower read activated on GET)
    print("\n--- GET /orders/ (follower read active) ---")
    resp = client.get("/orders/")
    _print_response(resp)

    # List orders with region header
    print("\n--- GET /orders/ (region: eu-west1) ---")
    resp = client.get("/orders/", HTTP_X_COCKROACHDB_REGION="eu-west1")
    _print_response(resp)

    # List products (global table)
    print("\n--- GET /products/ ---")
    resp = client.get("/products/")
    _print_response(resp)

    # Create order (retry-safe write)
    print("\n--- POST /orders/create/ (atomic_with_retry) ---")
    resp = client.post(
        "/orders/create/",
        data=json.dumps({"customer": "Diana", "total": 75.00, "region": "ap-southeast1"}),
        content_type="application/json",
    )
    _print_response(resp)

    # Transfer (execute_with_retry)
    print("\n--- POST /transfer/ (execute_with_retry) ---")
    orders = list(Order.objects.all()[:2])
    if len(orders) >= 2:
        resp = client.post(
            "/transfer/",
            data=json.dumps(
                {
                    "from_id": orders[0].pk,
                    "to_id": orders[1].pk,
                    "amount": 10,
                }
            ),
            content_type="application/json",
        )
        _print_response(resp)

    # configure_cockroachdb helper
    print("\n--- GET /configure-db/ ---")
    resp = client.get("/configure-db/")
    _print_response(resp)

    # Model introspection
    print("\n--- Model metadata ---")
    print(f"  Order.crdb_locality     = {Order.crdb_locality}")
    print(f"  Product.crdb_locality   = {Product.crdb_locality}")
    print(
        f"  Order fields            = {[f.name for f in Order._meta.get_fields() if hasattr(f, 'column')]}"
    )
    print(
        f"  Product fields          = {[f.name for f in Product._meta.get_fields() if hasattr(f, 'column')]}"
    )

    print("\n" + "=" * 60)
    print("  Demo complete. All features exercised successfully.")
    print("=" * 60)
    print("\nTo start a dev server:")
    print("  python examples/django_app.py runserver 8000")
    print("\nThen try:")
    print("  curl http://localhost:8000/health/")
    print('  curl -H "X-CockroachDB-Region: us-east1" http://localhost:8000/orders/')
    print('  curl -X POST -H "Content-Type: application/json" \\')
    print('       -d \'{"customer":"Eve","total":42.00}\' http://localhost:8000/orders/create/')


def _print_response(resp) -> None:
    """Pretty-print a Django test client response."""
    data = json.loads(resp.content)
    print(f"  Status: {resp.status_code}")
    print(f"  Body:   {json.dumps(data, indent=2, default=str)}")


# ---------------------------------------------------------------------------
# 8. Main — demo mode or management commands (e.g., runserver)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from django.core.management import execute_from_command_line

        execute_from_command_line(sys.argv)
    else:
        run_demo()
