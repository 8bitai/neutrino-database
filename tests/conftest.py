"""
Shared pytest configuration for neutrino-database.

This is the schema-owning repo — its tests verify the canonical
schema (the ``tables.py`` Core definitions and the ``orm.py`` ORM
wrappers) end-to-end against real Postgres. Sister conftest in
neutrino-gateway has the same shape; both must stay aligned.

Required environment variables
------------------------------
TEST_DATABASE_URL
    Async-driver Postgres URL for a database used ONLY by tests.
    Example:
        postgresql+asyncpg://postgres:root@localhost:5432/neutrino_database_test_db

    Hard safety guard: the conftest refuses to start if
    ``TEST_DATABASE_URL`` is missing or equals ``DATABASE_URL`` (the
    dev DB the runtime config points at — see ``.env``).

How isolation works
-------------------
* Session-scoped ``test_engine`` fixture: one async engine bound to
  the test DB. ``Base.metadata.create_all`` runs once per session so
  the schema is brought up to the canonical ``tables.py`` definitions.
  (Alembic itself is exercised by the parity-debt tests in DB Task 0a
  follow-up — task #29 — not here.)
* Test functions clean up the rows they create via try/finally; the
  full-rollback fixture pattern from gateway is overkill for the
  schema-shape tests this repo currently hosts.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Pre-import environment guard. Runs before any neutrino_database imports.
# ---------------------------------------------------------------------------

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not _TEST_DATABASE_URL:
    sys.stderr.write(
        "\n[conftest] ERROR: TEST_DATABASE_URL is not set.\n"
        "  Required to run tests. Example:\n"
        "    export TEST_DATABASE_URL='postgresql+asyncpg://postgres:root@localhost:5432/neutrino_database_test_db'\n"
        "  Then create the test DB once with:\n"
        "    PGPASSWORD=<pwd> make setup-test-db\n\n"
    )
    raise RuntimeError("TEST_DATABASE_URL is required")

if _TEST_DATABASE_URL == os.environ.get("DATABASE_URL"):
    sys.stderr.write(
        "\n[conftest] ERROR: TEST_DATABASE_URL must not equal DATABASE_URL.\n"
        "  Tests must run against a separate database to avoid clobbering dev/prod data.\n\n"
    )
    raise RuntimeError("TEST_DATABASE_URL must differ from DATABASE_URL")

# Mirror what the gateway does: stamp DATABASE_URL with the test URL so
# any neutrino_database settings/env-loads inside tests pick up the test
# database, not the dev one.
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL

# ---------------------------------------------------------------------------
# Imports (after env is configured).
# ---------------------------------------------------------------------------

import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from neutrino_database.models.base import Base  # noqa: E402

# Force-register every Table on `Base.metadata` by importing the module
# that defines them. Without this, only the tables that happen to be
# referenced via ORM classes get created.
from neutrino_database.models import tables  # noqa: E402, F401
from neutrino_database.models.credentials import api_keys  # noqa: E402, F401


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Async engine bound to the test database. Brings up the schema once."""
    engine = create_async_engine(
        _TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()
