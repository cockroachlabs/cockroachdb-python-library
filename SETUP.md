# Setup & Development Guide

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Runtime |
| [uv](https://docs.astral.sh/uv/) | 0.2+ | Package manager and workspace tool |
| Docker | 24+ | Running CockroachDB for integration tests |
| Git | 2.30+ | Version control |

## Clone and Setup

```bash
git clone https://github.com/cockroachdb/cockroachdb-python-library.git
cd cockroachdb-python-library
```

## Development Environment

This project uses [uv workspaces](https://docs.astral.sh/uv/concepts/workspaces/) to manage the monorepo. All six packages are declared in the root `pyproject.toml`.

### Install all packages in development mode

```bash
# Create venv and install all workspace packages + dev dependencies
uv sync --all-packages

# Verify installation
uv run python -c "import cockroachdb; print(cockroachdb.__version__)"
```

### Install a single package

```bash
# Install only the base package
uv sync --package cockroachdb

# Install base + core
uv sync --package cockroachdb --package cockroachdb-core
```

### Activate the virtualenv (optional)

```bash
source .venv/bin/activate
```

## Project Structure

```
cockroachdb-python-library/
├── pyproject.toml                    # Workspace root (uv, ruff, mypy, pytest config)
├── packages/
│   ├── cockroachdb/                  # Base: decorators, types, config, exceptions
│   ├── cockroachdb-core/             # Engine: retry, circuit breaker, regions, middleware
│   ├── cockroachdb-sqlalchemy/       # SQLAlchemy 2.0 adapter
│   ├── cockroachdb-cdc/              # CDC changefeed webhook handlers
│   ├── cockroachdb-ai/               # Vector search, RAG, embeddings
│   └── cockroachdb-testing/          # Testcontainers fixtures, simulators
├── tests/
│   ├── unit/                         # Unit tests (no CockroachDB required)
│   └── integration/                  # Integration tests (requires Docker)
├── examples/                         # Usage examples
└── docs/                             # Architecture diagrams
```

## Running Tests

### Unit tests (no Docker required)

```bash
# All unit tests
uv run pytest tests/unit/ -v

# Single package tests
uv run pytest tests/unit/test_decorators.py -v

# With coverage
uv run pytest tests/unit/ --cov=cockroachdb --cov-report=term-missing
```

### Integration tests (requires Docker)

Integration tests spin up a CockroachDB container via Testcontainers.

```bash
# Start Docker daemon first, then:
uv run pytest tests/integration/ -v

# Run a specific integration test
uv run pytest tests/integration/test_retry_integration.py -v
```

### Run all tests

```bash
uv run pytest -v
```

## Linting and Type Checking

### Ruff (linter + formatter)

```bash
# Check for lint errors
uv run ruff check .

# Auto-fix lint errors
uv run ruff check . --fix

# Format code
uv run ruff format .

# Check formatting without modifying
uv run ruff format . --check
```

### Mypy (type checking)

```bash
# Type check all packages
uv run mypy packages/

# Type check a single package
uv run mypy packages/cockroachdb/

# Strict mode is enabled by default in pyproject.toml
```

### Run all checks

```bash
uv run ruff check . && uv run ruff format . --check && uv run mypy packages/ && uv run pytest -v
```

## Building Packages

Each package builds independently using [Hatch](https://hatch.pypa.io/).

```bash
# Build a single package
cd packages/cockroachdb
uv build

# Build all packages from root
for pkg in packages/*/; do
    echo "Building $(basename $pkg)..."
    (cd "$pkg" && uv build)
done

# Built artifacts land in packages/<name>/dist/
ls packages/cockroachdb/dist/
# cockroachdb-0.1.0.tar.gz
# cockroachdb-0.1.0-py3-none-any.whl
```

## Publishing to PyPI

### Test PyPI (recommended first)

```bash
cd packages/cockroachdb

# Upload to Test PyPI
uv publish --index-url https://test.pypi.org/legacy/

# Verify install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ cockroachdb
```

### Production PyPI

```bash
# Ensure you have a PyPI token configured
# Option 1: environment variable
export UV_PUBLISH_TOKEN=pypi-xxxxx

# Option 2: pass directly
uv publish --token pypi-xxxxx

# Publish all packages (in dependency order)
for pkg in cockroachdb cockroachdb-core cockroachdb-sqlalchemy cockroachdb-cdc cockroachdb-ai cockroachdb-testing; do
    echo "Publishing $pkg..."
    (cd "packages/$pkg" && uv publish)
done
```

Publish in this order to satisfy dependencies:
1. `cockroachdb` (base, no deps on other packages)
2. `cockroachdb-core` (depends on cockroachdb)
3. `cockroachdb-sqlalchemy`, `cockroachdb-cdc`, `cockroachdb-ai` (depend on core)
4. `cockroachdb-testing` (depends on core)

## Running a Minimal Demo

### FastAPI example

Create `examples/fastapi_demo.py`:

```python
"""Minimal FastAPI app with CockroachDB retry handling."""

from fastapi import FastAPI
from cockroachdb import crdb_retry
from cockroachdb.config import CockroachDBConfig

app = FastAPI()
config = CockroachDBConfig()


@app.get("/")
async def health():
    return {"status": "ok", "retry_config": config.retry.model_dump()}


@app.post("/transfer")
@crdb_retry(max_retries=config.retry.max_retries)
async def transfer():
    # Replace with real DB logic
    return {"status": "transferred"}
```

Run it:

```bash
uv add fastapi uvicorn
uv run uvicorn examples.fastapi_demo:app --reload --port 8000
```

### Standalone retry demo

```bash
uv run python -c "
from cockroachdb import crdb_retry
from cockroachdb.config import CockroachDBConfig

config = CockroachDBConfig()
print(f'Retry config: {config.retry.model_dump()}')
print(f'Circuit breaker: {config.circuit_breaker.model_dump()}')
print(f'Region config: {config.region.model_dump()}')
"
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'cockroachdb'`

You are not running inside the uv virtualenv. Either:
- Prefix commands with `uv run`
- Activate the venv: `source .venv/bin/activate`
- Re-sync: `uv sync --all-packages`

### `ImportError: cannot import name 'CockroachDBTemplate'`

`CockroachDBTemplate` lives in `cockroachdb-core`, not the base `cockroachdb` package:

```bash
uv sync --package cockroachdb-core
```

```python
from cockroachdb.core import CockroachDBTemplate  # correct
```

### Integration tests fail with "Docker not available"

Ensure Docker Desktop (or Docker Engine) is running:

```bash
docker info
docker run --rm cockroachdb/cockroach:latest version
```

### Mypy reports errors in third-party packages

Add stubs or ignore rules in `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = "psycopg2.*"
ignore_missing_imports = true
```

### Ruff and mypy disagree on import order

Ruff's isort configuration takes precedence. The root `pyproject.toml` defines `known-first-party = ["cockroachdb"]`. If adding new third-party deps, ruff will auto-sort them.

### `cockroachdb-testing` Testcontainers timeout

Increase the Docker pull timeout or pre-pull the image:

```bash
docker pull cockroachdb/cockroach:latest
```

### uv can't resolve workspace packages

Ensure all six packages are listed in the root `pyproject.toml` under `[tool.uv.workspace]`:

```toml
[tool.uv.workspace]
members = [
    "packages/cockroachdb",
    "packages/cockroachdb-core",
    "packages/cockroachdb-sqlalchemy",
    "packages/cockroachdb-cdc",
    "packages/cockroachdb-ai",
    "packages/cockroachdb-testing",
]
```

Then re-sync:

```bash
uv sync --all-packages
```
