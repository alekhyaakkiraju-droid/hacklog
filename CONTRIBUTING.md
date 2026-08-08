# Contributing to Hacklog

Welcome! This guide will get you from a fresh clone to a working development environment with passing tests in under 30 minutes.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Development Environment Setup](#development-environment-setup)
3. [Running Tests](#running-tests)
4. [Code Style](#code-style)
5. [Architecture Overview](#architecture-overview)
6. [PR Process](#pr-process)

---

## Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.12 | 3.13 also supported and tested in CI |
| Git | any recent | — |
| Docker | 24+ | Optional — only needed for container-based testing |

Check your Python version:

```bash
python --version   # must be 3.12.x or 3.13.x
```

---

## Development Environment Setup

### 1. Clone the repository

```bash
git clone https://github.com/dandb/hacklog.git
cd hacklog
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows
```

### 3. Install the package with test and dev dependencies

```bash
pip install -e '.[test,dev]'
```

This installs:
- **Runtime dependencies** — `sqlalchemy`, `aiosmtplib`, `pydantic-settings`, `structlog`, `pyyaml`, `prometheus-client`, `alembic`
- **Test dependencies** — `pytest`, `pytest-asyncio`, `pytest-cov`, `hypothesis`, `coverage`, `bandit`
- **Dev dependencies** — `ruff`, `black`, `isort`, `mypy`, `types-PyYAML`

### 4. Verify the installation

```bash
pytest tests/ -q
```

All tests should pass. You are ready to develop.

### 5. Run the server locally

Hacklog reads **SMTP secrets and tuning from `HACKLOG_*` environment variables** via `ConfigManager` (`hacklog/config.py`). Legacy bind/port and parser patterns still come from `conf/server.conf`.

```bash
cp .env.example .env          # fill in HACKLOG_SMTP_* and HACKLOG_ALERT_RECIPIENT
make dev-start                # or: ./scripts/run.sh
make dev-status               # check pid file
make dev-stop                 # SIGTERM graceful shutdown (no kill -9)
```

Logs are written to `var/log/hacklog-dev.log`. The pid file defaults to `.hacklog-dev.pid` in the repo root.

**Docker alternative:** `docker compose up -d` (see README) — same `HACKLOG_*` variables, container-managed lifecycle.

**Production:** use `deploy/hacklog.service` (systemd) — see README *Quick Start — Bare Metal*.

#### Legacy `hacklog/run.sh` and `hacklog/stop.sh` (removed)

Older clones included crude helpers under `hacklog/run.sh` and `hacklog/stop.sh` that invoked `python server.py` directly and stopped the process with `ps | grep | kill -9`. Those scripts are **removed** in favor of:

| Use case | Replacement |
|----------|-------------|
| Local development | `make dev-start` / `make dev-stop` (`scripts/run.sh`, `scripts/stop.sh`) |
| Container deployment | `docker compose up` / `docker compose down` |
| Bare-metal production | `systemctl start hacklog` / `systemctl stop hacklog` (`deploy/hacklog.service`) |

The modern dev scripts use correct `#!/bin/sh` shebangs, load `HACKLOG_*` via ConfigManager, and stop with **SIGTERM** (graceful shutdown) using a pid file — not `kill -9`.

---

## Running Tests

### Full test suite

```bash
pytest tests/
```

### With coverage report

```bash
pytest tests/ --cov=hacklog --cov-report=term-missing
```

### Single test file

```bash
pytest tests/test_scoring_engine.py -v
```

### Single test by name

```bash
pytest tests/test_retention.py::test_run_purge_full_pipeline -v
```

### Async tests

The test suite uses `pytest-asyncio` with `asyncio_mode = "auto"` (configured in `pyproject.toml`), so async tests run automatically without any extra flags.

### Security scan

```bash
bandit -r hacklog/
```

---

## Code Style

Hacklog enforces style with three tools, all configured in `pyproject.toml`:

| Tool | Purpose | Command |
|------|---------|---------|
| `black` | Opinionated code formatter | `black hacklog/ tests/` |
| `isort` | Import ordering | `isort hacklog/ tests/` |
| `ruff` | Fast linting (E, F, I, N, W rules) | `ruff check hacklog/ tests/` |

Run all three at once before committing:

```bash
black hacklog/ tests/
isort hacklog/ tests/
ruff check hacklog/ tests/
```

### Type checking

```bash
mypy hacklog/
```

### CI enforcement

The GitHub Actions CI pipeline runs ruff, black, isort, mypy, bandit, and pytest against Python 3.12 and 3.13 on every push and pull request. A PR cannot be merged unless all checks pass.

---

## Architecture Overview

Hacklog is structured in six layers. Understanding this helps you locate the right file for a given change.

```
┌─────────────────────────────────────────────────────┐
│  1. Syslog Ingestion  (hacklog/syslog_server.py)     │
│     UDP listener → validates source CIDR →           │
│     rate-limits per source IP                        │
├─────────────────────────────────────────────────────┤
│  2. Parsing           (hacklog/parse.py)             │
│     Extracts username, IP, server, success/fail      │
│     from sshd log lines → EventLog entity            │
├─────────────────────────────────────────────────────┤
│  3. Scoring Engine    (hacklog/scoring.py)           │
│     Weighted surprisal across 6 dimensions →         │
│     compares event to user's profile baseline        │
├─────────────────────────────────────────────────────┤
│  4. Alerting          (hacklog/alerting.py)          │
│     Async SMTP delivery with circuit breaker,        │
│     retry, and dead-letter queue                     │
├─────────────────────────────────────────────────────┤
│  5. Persistence       (hacklog/repositories.py)      │
│     SQLAlchemy ORM → SQLite; repository pattern;     │
│     Alembic migrations; append-only audit trail      │
├─────────────────────────────────────────────────────┤
│  6. Config & Observability                           │
│     pydantic-settings env vars; structlog JSON;      │
│     Prometheus metrics; data retention / purge       │
└─────────────────────────────────────────────────────┘
```

### Key files

| File | What to change here |
|------|-------------------|
| `hacklog/entities.py` | SQLAlchemy models, `Weight`/`Threshold` constants |
| `hacklog/repositories.py` | Data access — add query or persistence methods |
| `hacklog/services.py` | Profile update logic |
| `hacklog/scoring.py` | Risk scoring algorithm |
| `hacklog/alerting.py` | Alert delivery, circuit breaker behaviour |
| `hacklog/retention.py` | Data retention / purge logic |
| `hacklog/config.py` | New configuration fields |
| `hacklog/logging_config.py` | Structured logging processors |
| `migrations/versions/` | Alembic schema migrations |
| `tests/` | Tests — one file per module, same name prefix |

### Dependency injection

Services are wired together via constructor injection. `ScoringEngine` accepts `UpdateService`, `AlertService`, and an optional `AuditRepository`. This makes all components independently testable with mocks — you will rarely need an actual database in unit tests.

### Database migrations

When you add or modify a SQLAlchemy model in `entities.py`, create a migration:

```bash
alembic revision -m "describe_your_change"
# edit the generated file in migrations/versions/
alembic upgrade head
```

The existing migrations in `migrations/versions/` are numbered `001`, `002`, `003` — follow the same convention.

---

## PR Process

1. **Fork** the repository and create a feature branch from `master`:

   ```bash
   git checkout -b feature/my-change
   ```

2. **Write tests first** (or alongside the change). Every new behaviour must have a test. Every bug fix must have a regression test.

3. **Run the full check suite locally** before pushing:

   ```bash
   black hacklog/ tests/
   isort hacklog/ tests/
   ruff check hacklog/ tests/
   mypy hacklog/
   pytest tests/ --cov=hacklog
   bandit -r hacklog/
   ```

4. **Open a pull request** against `master`. Fill in the PR description with:
   - What changed and why
   - How to test it manually (if applicable)
   - Any migration steps required

5. **CI must be green** — all checks on Python 3.12 and 3.13 must pass before review.

6. **One approving review** from a maintainer is required before merge.

7. **Squash or rebase** to keep a clean linear history.

### Commit message style

```
[WO-NNN] Short imperative summary (≤72 chars)

Optional longer explanation of why the change was made,
not what was changed (the diff shows that).
```

### What not to include in a PR

- Credentials, secrets, or `.env` files
- Compiled binaries or generated files
- Changes to `CLAUDE.md` or `.claude/` directories
- Unrelated refactoring mixed with a feature or bug fix
