# Contributing

## Development Setup

```bash
# Clone the repository
git clone https://github.com/cockroachdb/cockroachdb-python-library.git
cd cockroachdb-python-library

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all packages in dev mode
uv sync --all-packages --all-extras
```

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run only unit tests
uv run pytest tests/unit/ -v

# Run only integration tests (requires Docker for Testcontainers)
uv run pytest tests/integration/ -v

# Run with coverage
uv run pytest tests/ --cov=packages --cov-report=term-missing
```

## Linting and Formatting

```bash
# Check formatting
uv run ruff format --check .

# Fix formatting
uv run ruff format .

# Lint
uv run ruff check .

# Lint with auto-fix
uv run ruff check --fix .

# Type checking
uv run mypy packages/cockroachdb/src packages/cockroachdb-core/src packages/cockroachdb-testing/src
```

## Code Style

- **Formatter:** Ruff (line length 99)
- **Linter:** Ruff with pycodestyle, pyflakes, isort, pep8-naming, pyupgrade, bugbear, simplify rules
- **Type checking:** mypy in strict mode
- **Python:** 3.11+ only, use modern syntax (`match`, `|` unions, f-strings)

## Project Structure

```
packages/
  cockroachdb/          # Base: decorators, types, config, exceptions
  cockroachdb-core/     # Engine: retry, circuit breaker, template, middleware
  cockroachdb-sqlalchemy/ # SQLAlchemy integration
  cockroachdb-cdc/      # CDC webhook handler
  cockroachdb-ai/       # Vector search, RAG
  cockroachdb-testing/  # Test fixtures, simulators
tests/
  unit/                 # Fast tests, no external deps
  integration/          # Needs Docker (Testcontainers)
docs/                   # MkDocs documentation
```

## Pull Request Guidelines

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure `ruff format --check .` and `ruff check .` pass
4. Ensure `mypy` passes on the packages you modified
5. Ensure all tests pass
6. Keep commits focused -- one logical change per commit
7. Write clear commit messages describing the "why"

## Adding a New Package

1. Create `packages/<name>/` with `pyproject.toml` and `src/cockroachdb/<submodule>/`
2. Add the package to `tool.uv.workspace.members` in the root `pyproject.toml`
3. Add documentation under `docs/packages/<name>.md`
4. Update `mkdocs.yml` navigation
5. Add the package to the CI mypy step if applicable

## Building Documentation

```bash
pip install mkdocs-material
mkdocs serve     # Local preview at http://localhost:8000
mkdocs build     # Build static site to site/
```
