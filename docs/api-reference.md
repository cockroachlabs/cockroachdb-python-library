# API Reference

Quick reference to the main classes and functions across all packages.

## cockroachdb (Base)

| Symbol | Kind | Import |
|--------|------|--------|
| `crdb_retry` | decorator | `from cockroachdb import crdb_retry` |
| `crdb_region` | decorator | `from cockroachdb import crdb_region` |
| `regional_by_row` | decorator | `from cockroachdb import regional_by_row` |
| `global_table` | decorator | `from cockroachdb import global_table` |
| `follower_read` | decorator | `from cockroachdb import follower_read` |
| `CockroachDBConfig` | class | `from cockroachdb import CockroachDBConfig` |
| `SerializationError` | exception | `from cockroachdb import SerializationError` |
| `RetryExhaustedError` | exception | `from cockroachdb import RetryExhaustedError` |
| `CircuitOpenError` | exception | `from cockroachdb import CircuitOpenError` |

See [Base package](packages/base.md) for details.

## cockroachdb-core

| Symbol | Kind | Import |
|--------|------|--------|
| `RetryEngine` | class | `from cockroachdb.core import RetryEngine` |
| `CockroachDBTemplate` | class | `from cockroachdb.core import CockroachDBTemplate` |
| `CircuitBreaker` | class | `from cockroachdb.core import CircuitBreaker` |
| `RegionContext` | context manager | `from cockroachdb.core import RegionContext` |
| `FollowerReadContext` | context manager | `from cockroachdb.core import FollowerReadContext` |
| `CockroachDBMiddleware` | class | `from cockroachdb.core import CockroachDBMiddleware` |

See [Core package](packages/core.md) for details.

## cockroachdb-sqlalchemy

| Symbol | Kind | Import |
|--------|------|--------|
| `create_cockroachdb_engine` | function | `from cockroachdb.sqlalchemy import create_cockroachdb_engine` |
| `CockroachDBSession` | class | `from cockroachdb.sqlalchemy import CockroachDBSession` |
| `RegionalMixin` | mixin | `from cockroachdb.sqlalchemy import RegionalMixin` |
| `GlobalMixin` | mixin | `from cockroachdb.sqlalchemy import GlobalMixin` |

See [SQLAlchemy package](packages/sqlalchemy.md) for details.

## cockroachdb-cdc

| Symbol | Kind | Import |
|--------|------|--------|
| `changefeed_handler` | decorator | `from cockroachdb.cdc import changefeed_handler` |
| `ChangefeedEvent` | model | `from cockroachdb.cdc import ChangefeedEvent` |
| `CDCRouter` | class | `from cockroachdb.cdc import CDCRouter` |
| `CDCManager` | class | `from cockroachdb.cdc import CDCManager` |

See [CDC package](packages/cdc.md) for details.

## cockroachdb-ai

| Symbol | Kind | Import |
|--------|------|--------|
| `VectorSearchTemplate` | class | `from cockroachdb.ai import VectorSearchTemplate` |
| `CockroachDBVectorStore` | class | `from cockroachdb.ai import CockroachDBVectorStore` |
| `RagPipeline` | class | `from cockroachdb.ai import RagPipeline` |
| `Embeddings` | protocol | `from cockroachdb.ai import Embeddings` |

See [AI package](packages/ai.md) for details.

## cockroachdb-testing

| Symbol | Kind | Import |
|--------|------|--------|
| `CockroachDBFixture` | class | `from cockroachdb.testing import CockroachDBFixture` |
| `RetrySimulator` | class | `from cockroachdb.testing import RetrySimulator` |
| `ConcurrencyRunner` | class | `from cockroachdb.testing import ConcurrencyRunner` |
| `factories` | module | `from cockroachdb.testing import factories` |

See [Testing package](packages/testing.md) for details.
