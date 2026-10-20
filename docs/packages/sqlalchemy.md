# cockroachdb-sqlalchemy

SQLAlchemy integration with retry-aware engine and session.

```bash
pip install cockroachdb-sqlalchemy
```

**Depends on:** `cockroachdb-core`, `sqlalchemy`

## Engine

Create a SQLAlchemy engine pre-configured for CockroachDB.

```python
from cockroachdb.sqlalchemy import create_cockroachdb_engine

engine = create_cockroachdb_engine("cockroachdb://root@localhost:26257/defaultdb")
```

The engine registers event listeners that handle serialization retries transparently.

## CockroachDBSession

A session class with built-in serialization retry.

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


with CockroachDBSession(engine) as session:
    session.add(User(name="Alice"))
    session.commit()
```

## Event Listeners

The package registers SQLAlchemy event listeners for:

- **`before_cursor_execute`** -- sets session-level variables (e.g., follower reads, region)
- **`handle_error`** -- catches serialization failures and triggers retry

## Mixins

Reusable model mixins for common CockroachDB patterns:

```python
from cockroachdb.sqlalchemy import RegionalMixin, GlobalMixin


class UserProfile(Base, RegionalMixin):
    __tablename__ = "user_profiles"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))


class CountryList(Base, GlobalMixin):
    __tablename__ = "countries"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
```

## API Summary

| Symbol | Type | Description |
|--------|------|-------------|
| `create_cockroachdb_engine` | function | Create retry-aware SQLAlchemy engine |
| `CockroachDBSession` | class | Session with serialization retry |
| `RegionalMixin` | mixin | Adds `crdb_region` column |
| `GlobalMixin` | mixin | Marks table as `GLOBAL` |
