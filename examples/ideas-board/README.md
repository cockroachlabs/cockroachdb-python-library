# Concurrent Ideas Board (Python)

The Python twin of the Spring/.NET/Java/Go fundamentals demos. It proves the
library's hero feature: **automatic retry on serialization conflicts
(SQLSTATE 40001)** via the `@crdb_retry` decorator.

## What it shows

One idea row, many concurrent upvotes. Each upvote is a read-modify-write
(`SELECT votes` → `votes + 1` → `UPDATE`) under **SERIALIZABLE** isolation, so
colliding upvotes force CockroachDB to raise `40001`.

- `upvote_without_retry()` — no decorator. Conflicts propagate, votes are **lost**.
- `upvote()` — wrapped in `@crdb_retry(...)`. The decorator re-runs the whole
  function in a fresh transaction on `40001`, so **every vote lands**.

```
PLAIN   @crdb_retry OFF : 2/25 votes landed (23 lost to 40001)
RETRY   @crdb_retry ON  : 25/25 votes landed (0 failures)
```

## Files

| File | Role |
|------|------|
| `idea.py` | `Idea` dataclass (id, text, votes) |
| `repository.py` | psycopg read-modify-write helpers taking a cursor |
| `service.py` | `upvote_without_retry` (plain) and `upvote` (`@crdb_retry`) |
| `main.py` | seed one idea, fire N concurrent upvotes per path, print both |
| `test_unit.py` | fast unit test, no Docker (mocked psycopg) |
| `test_concurrency.py` | integration test, real CockroachDB via testcontainers |
| `crdb_container.py` | helper that boots an insecure CockroachDB container |

## Prerequisites

- Python 3.12+
- Docker (only for `main.py`'s throwaway cluster and the integration test)

## Install

The library ships on an anonymous PEP 503 feed, not public PyPI:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` pins the **published** `cockroachdb==0.1.2` (plus
`cockroachdb-testing==0.1.1`) and carries the `--extra-index-url` line for the
feed. A single-package install looks like:

```bash
pip install 'cockroachdb==0.1.2' \
  --extra-index-url https://cockroachlabs.github.io/cockroachdb-python-library/simple/
```

## Run

```bash
# Uses $CRDB_DSN if set, otherwise spins up a throwaway container (needs Docker).
python main.py

# Point at your own cluster instead:
CRDB_DSN=postgresql://root@localhost:26257/defaultdb python main.py
```

## Test

```bash
pytest                       # unit always runs; integration needs Docker
pytest test_unit.py          # fast path only, no container
```

The unit test runs with **no container**. The integration test boots a real
CockroachDB container and asserts the retry path lands exactly 60 votes while
the plain path does not.

> Container note: the published `cockroachdb-testing` fixture and the
> `testcontainers` cockroachdb module boot CockroachDB in *secure* mode, which
> needs a client certificate this example does not ship (and psycopg3 cannot
> parse the module's `cockroachdb+psycopg2://` URL). So `crdb_container.py` runs
> the same image in `--insecure` mode and yields a plain `postgresql://` DSN —
> the exact connection style the library's own examples use.

> Source note: this example lives inside the `cockroachdb-python-library`
> checkout, so its tests were validated against the **local source** via
> `pip install -e packages/cockroachdb packages/cockroachdb-core`.
> Customers use the pinned published install above.
