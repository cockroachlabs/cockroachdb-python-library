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
