# Examples

Runnable examples demonstrating key library features. All examples assume a CockroachDB cluster at `localhost:26257`.

## Basic Retry

Automatic retry on serialization failures:

```python
import psycopg
from cockroachdb import crdb_retry


@crdb_retry(max_retries=5, base_delay=0.1)
def transfer(conn, from_id: int, to_id: int, amount: float) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, from_id))
        cur.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, to_id))
    conn.commit()


with psycopg.connect("postgresql://root@localhost:26257/defaultdb") as conn:
    transfer(conn, from_id=1, to_id=2, amount=50.0)
```

## Transaction Template

Programmatic API without decorators:

```python
from cockroachdb.core import CockroachDBTemplate

template = CockroachDBTemplate("postgresql://root@localhost:26257/defaultdb")


def insert_event(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO events (name) VALUES ('signup')")


template.execute(insert_event)
```

## SQLAlchemy Session

```python
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase
from cockroachdb.sqlalchemy import create_cockroachdb_engine, CockroachDBSession

engine = create_cockroachdb_engine("cockroachdb://root@localhost:26257/defaultdb")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))


Base.metadata.create_all(engine)

with CockroachDBSession(engine) as session:
    session.add(User(name="Alice"))
    session.commit()
```

## Follower Reads

```python
from cockroachdb import follower_read


@follower_read
def get_catalog(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM products")
        return cur.fetchall()
```

## Multi-Region

```python
from cockroachdb import crdb_region, regional_by_row, global_table


@crdb_region("us-east1")
def create_us_user(conn, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (name, region) VALUES (%s, 'us-east1')", (name,))
    conn.commit()
```

## CDC Webhook

```python
from fastapi import FastAPI, Request
from cockroachdb.cdc import CDCRouter

app = FastAPI()
router = CDCRouter()


@router.on("users")
def handle_users(event):
    print(f"User changed: {event.key}")


@app.post("/cdc")
async def cdc_webhook(request: Request):
    router.dispatch(await request.json())
    return {"status": "ok"}
```

## Vector Search

```python
from cockroachdb.ai import VectorSearchTemplate

vst = VectorSearchTemplate(
    dsn="postgresql://root@localhost:26257/defaultdb",
    table="documents",
    vector_column="embedding",
)

results = vst.search(query_vector=[0.1, 0.2, 0.3], top_k=5)
```

## RAG Pipeline

```python
from cockroachdb.ai import CockroachDBVectorStore, RagPipeline

store = CockroachDBVectorStore(
    dsn="postgresql://root@localhost:26257/defaultdb",
    table="docs",
    vector_column="embedding",
    dimensions=1536,
)

rag = RagPipeline(vector_store=store, embedding_fn=my_embed_fn)
rag.index("doc-1", "CockroachDB is a distributed SQL database.")
answer = rag.query("What is CockroachDB?")
```

## FastAPI Middleware

```python
from fastapi import FastAPI
from cockroachdb.core import CockroachDBMiddleware

app = FastAPI()
app.add_middleware(CockroachDBMiddleware)


@app.get("/")
async def root():
    return {"region": "determined from X-CockroachDB-Region header"}
```

## Testing with Testcontainers

```python
import pytest
from cockroachdb.testing import CockroachDBFixture


@pytest.fixture
def crdb():
    with CockroachDBFixture() as fixture:
        fixture.execute("CREATE TABLE users (id INT PRIMARY KEY, name STRING)")
        yield fixture


def test_insert(crdb):
    crdb.execute("INSERT INTO users VALUES (1, 'Bob')")
    assert len(crdb.fetch_all("SELECT * FROM users")) == 1
```
