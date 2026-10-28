# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Versions are per
package; this entry covers the `cockroachdb`, `cockroachdb-core`, and
`cockroachdb-sqlalchemy` packages.

## [Unreleased]

Follower reads can now target a specific staleness, and a `@follower_read` /
SQLAlchemy session helper that raised `AttributeError` at runtime has been fixed.

### Added
- `hours_ago`, `minutes_ago` and `seconds_ago` keyword-only parameters on the
  `follower_read()` decorator, `FollowerReadContext.scoped()`, and the SQLAlchemy
  session `follower_read()` helper. They add up and compose to
  `AS OF SYSTEM TIME '-Ns'`; with nothing set the read still uses
  `follower_read_timestamp()`.
- `cockroachdb.staleness.build_staleness()` — the single source of truth for
  composing + validating a staleness expression. Exported from `cockroachdb`.

### Fixed
- **SQLAlchemy `session.follower_read()` raised `AttributeError` at runtime.** It
  called `FollowerReadContext.set(...)` / `reset(...)` (methods that do not exist)
  and passed a `bool` into a `str | None` contextvar. It now uses the real
  `FollowerReadContext.scoped()` contextmanager.
- A negative `hours_ago`/`minutes_ago`/`seconds_ago` now raises `ValueError` at
  call time instead of producing an invalid clause.

### Known limitation
- `MetricsCollector.record_follower_read()` is still not wired to any execution
  path (no call sites library-wide). Recording follower-read metrics requires
  instrumenting the SQLAlchemy event / psycopg execution layer — tracked
  separately.
