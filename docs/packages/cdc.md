# cockroachdb-cdc

Change Data Capture (CDC) webhook handler for CockroachDB changefeeds.

```bash
pip install cockroachdb-cdc
```

**Depends on:** `cockroachdb-core`

## Changefeed Handler

Decorator-based routing for CDC webhook events.

```python
from cockroachdb.cdc import changefeed_handler


@changefeed_handler("users")
def on_user_change(event) -> None:
    print(f"User changed: {event.key} -> {event.value}")
```

## CDC Models

Typed models for changefeed payloads:

```python
from cockroachdb.cdc import ChangefeedEvent

# event.key     -- primary key of changed row
# event.value   -- new row data (dict)
# event.updated -- timestamp of change
# event.table   -- source table name
```

## CDC Router

Route incoming webhook payloads to registered handlers.

```python
from cockroachdb.cdc import CDCRouter

router = CDCRouter()


@router.on("users")
def handle_users(event): ...


@router.on("orders")
def handle_orders(event): ...


# In your webhook endpoint:
router.dispatch(payload)
```

## CDC Manager

High-level manager for registering handlers and processing events.

```python
from cockroachdb.cdc import CDCManager

manager = CDCManager()
manager.register("users", on_user_change)
manager.register("orders", on_order_change)

# Process a batch of events
manager.process(events)
```

## FastAPI Integration

```python
from fastapi import FastAPI, Request
from cockroachdb.cdc import CDCRouter

app = FastAPI()
router = CDCRouter()


@router.on("users")
def handle_users(event):
    print(f"User: {event.key}")


@app.post("/cdc-webhook")
async def cdc_webhook(request: Request):
    payload = await request.json()
    router.dispatch(payload)
    return {"status": "ok"}
```

## API Summary

| Symbol | Type | Description |
|--------|------|-------------|
| `changefeed_handler` | decorator | Register a table handler |
| `ChangefeedEvent` | model | Typed CDC event payload |
| `CDCRouter` | class | Route events to handlers |
| `CDCManager` | class | Manage handler lifecycle |
