# CockroachDB Python Library — guide for coding agents

You are editing a Python app that depends on the `cockroachdb` libraries. This library
already solves the hard CockroachDB-specific problems. Use its helpers; do not re-implement
them. Exact APIs and options live in the [README](../../README.md).

## Already handled — do NOT rebuild

- **Serialization retry (SQLSTATE `40001`)** is automatic. Wrap writes with `@crdb_retry`
  (sync or async), or run them through `CockroachDBTemplate.transaction(...)` /
  `CockroachDBSession`. Never hand-roll a retry loop or `while`/`except` on `40001`.
- **Multi-region topology check** runs at startup and validates `@global_table` /
  `@regional_by_row` usage — don't reinvent it. If it blocks startup incorrectly, set the
  region-check mode to `none` rather than deleting annotations.
- **Metrics, Continuum, and CDC plumbing** are provided. Don't write Prometheus wiring or a
  changefeed webhook server by hand.

## Which helper for each job

| Job | Use |
|-----|-----|
| Auto-retry a write | `@crdb_retry(max_retries=...)` or `CockroachDBTemplate.transaction()` / `CockroachDBSession` |
| Stale read off nearest replica | `@follower_read(seconds_ago=...)` or `with FollowerReadContext.scoped(...)` |
| Pin work to a region | `@crdb_region("us-east1")`; scope with `RegionContext` |
| Regional-by-row / global tables | `@regional_by_row(default_region=...)`, `@global_table` |
| CDC webhook | `@changefeed_handler(table=..., operations=[...])` + `create_changefeed_router()` |
| Vector search / RAG | `@vector_search(...)`, `VectorSearchTemplate`, `RagPipeline`, `CockroachDBVectorStore` (`cockroachdb.ai`) |
| Cloud / MCP / Aegis | `make_cloud`, `make_mcp`, `McpAegisClient` (`cockroachdb.continuum`) |

Homing a row to a region = writing the **`crdb_region` COLUMN** on the row (the decorators and
`RegionContext` do this). There is **no `SET crdb_region` session variable** — never emit it.

## Config that matters

Everything is `CockroachDBConfig` (Pydantic), overridable via `CRDB_`-prefixed env vars:
`CRDB_RETRY__MAX_RETRIES`, `CRDB_REGION__DEFAULT_REGION`,
`CRDB_REGION__REGION_HEADER` (default `X-CockroachDB-Region`, read by `CockroachDBMiddleware`),
`CRDB_FOLLOWER_READ__ENABLED`. See the README Configuration table.

## Anti-patterns (don't do these)

- Hand-rolled `40001` retry loops — the library owns this.
- Raw `SET crdb_region ...` — not a real session var; set the `crdb_region` column instead.
- Writing changefeed webhook plumbing by hand — use `@changefeed_handler` / the CDC router.
- Running transactions at **READ COMMITTED** so `40001` never surfaces and retry silently
  no-ops — CockroachDB retry correctness assumes SERIALIZABLE.
- AI vector: `ensure_table()` runs DDL and needs **autocommit**; and do not open a result
  reader/cursor and then `commit()` the same transaction — read fully (or use a separate
  connection) first.

## Testing

Use `cockroachdb-testing`: `CockroachDBFixture` (Testcontainers-backed real CockroachDB) and
`RetrySimulator` (injects `40001` failures to prove retry works). Don't mock the driver.

## Learn CockroachDB fundamentals

The library handles the Python side; these CockroachDB docs explain the database underneath. The
links below go to the Markdown version of each page, which is easier for an agent to read; drop the
`.md` for the HTML page. Every docs page has one, and <https://docs.cockroachlabs.com/llms.txt>
indexes the whole documentation site.

**Start here**

- [Developer Basics](https://docs.cockroachlabs.com/docs/stable/developer-basics.md): what's different about building on CockroachDB.
- [PostgreSQL Compatibility](https://docs.cockroachlabs.com/docs/stable/postgresql-compatibility.md): CockroachDB speaks the PostgreSQL wire protocol (use a PostgreSQL driver — `psycopg`, `asyncpg`, or SQLAlchemy), with some differences.
- [Connection Pooling](https://docs.cockroachlabs.com/docs/stable/connection-pooling.md): sizing a client-side pool.
- [Common Errors and Solutions](https://docs.cockroachlabs.com/docs/stable/common-errors.md)

**Transactions and contention**

- [Transactions](https://docs.cockroachlabs.com/docs/stable/transactions.md): SERIALIZABLE by default, and why clients see retry errors.
- [Transaction Retry Error Reference](https://docs.cockroachlabs.com/docs/stable/transaction-retry-error-reference.md): what each `40001` (`RETRY_SERIALIZABLE`, `RETRY_WRITE_TOO_OLD`, ...) means and how to make it rarer. The library retries them; this tells you why they happen.
- [Reduce transaction contention](https://docs.cockroachlabs.com/docs/stable/performance-best-practices-overview.md#reduce-transaction-contention): the checklist. Keep transactions small, limit the rows they touch, use `SELECT ... FOR UPDATE` for read-then-write, `UPSERT` whole rows, use historical reads where staleness is fine.
- [Understand Hotspots](https://docs.cockroachlabs.com/docs/stable/understand-hotspots.md): ranges that take far more traffic than others, and how to spread it.
- [Performance Tuning Recipes](https://docs.cockroachlabs.com/docs/stable/performance-recipes.md): symptoms and fixes, contention included.
- [Monitor and Analyze Transaction Contention](https://docs.cockroachlabs.com/docs/stable/monitor-and-analyze-transaction-contention.md)
- [`SELECT FOR UPDATE`](https://docs.cockroachlabs.com/docs/stable/select-for-update.md)
- [Read Committed Transactions](https://docs.cockroachlabs.com/docs/stable/read-committed.md): an alternative isolation level, with trade-offs. Don't switch to it just to avoid retries — at READ COMMITTED `40001` never surfaces and the library's retry silently no-ops.

**Schema design**

- [Database Schemas](https://docs.cockroachlabs.com/docs/stable/schema-design-overview.md): how to design and change schemas, including why to change them with a migration tool rather than through the ORM.
- [Unique ID best practices](https://docs.cockroachlabs.com/docs/stable/performance-best-practices-overview.md#unique-id-best-practices): prefer `UUID` keys (`gen_random_uuid()`) over sequences or auto-increment, which create hotspots.
- [`UUID`](https://docs.cockroachlabs.com/docs/stable/uuid.md) and [Hash-sharded Indexes](https://docs.cockroachlabs.com/docs/stable/hash-sharded-indexes.md), for when an index must be on a sequential column.
- [Online Schema Changes](https://docs.cockroachlabs.com/docs/stable/online-schema-changes.md): schema changes run in the background; what that means for migrations.

**Multi-region**

- [Multi-Region Capabilities Overview](https://docs.cockroachlabs.com/docs/stable/multiregion-overview.md)
- [Table Localities](https://docs.cockroachlabs.com/docs/stable/table-localities.md): `REGIONAL BY TABLE`, `REGIONAL BY ROW` and `GLOBAL`, which `@regional_by_row` and `@global_table` map to.
- [How to Choose a Multi-Region Configuration](https://docs.cockroachlabs.com/docs/stable/choosing-a-multi-region-configuration.md)
- [Follower Reads](https://docs.cockroachlabs.com/docs/stable/follower-reads.md) and [`AS OF SYSTEM TIME`](https://docs.cockroachlabs.com/docs/stable/as-of-system-time.md), behind `@follower_read`.

**Change data capture**

- [`CREATE CHANGEFEED`](https://docs.cockroachlabs.com/docs/stable/create-changefeed.md) and [Changefeed Sinks](https://docs.cockroachlabs.com/docs/stable/changefeed-sinks.md) (the webhook sink is what `@changefeed_handler` receives).

**Vector search**

- [`VECTOR`](https://docs.cockroachlabs.com/docs/stable/vector.md) and [Vector Indexes](https://docs.cockroachlabs.com/docs/stable/vector-indexes.md)
