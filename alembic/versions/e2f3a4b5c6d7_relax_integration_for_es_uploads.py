"""[NEU-1816] UC-ES-DB-1.A — relax integration schema for ES uploads.

The canonical ``integration`` table was built for SaaS connectors where
every row has remote auth + a vaulted secret. To collapse the legacy
``datasources`` table onto ``integration`` (next slices), the schema
must accept rows that represent local-only sources (member uploads a
PDF / CSV) where there is no remote auth, no remote identity, and no
secret to vault.

Changes:

  * ``integration_auth_kind`` enum — add ``'none'`` value
  * ``integration_identity_kind`` enum — add ``'none'`` value
  * ``integration.vault_secret_id`` — DROP NOT NULL

``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction in PG <12
and even on modern PG must commit before the new value is usable. Each
``op.execute`` runs in its own implicit transaction here because we
pass the raw SQL to alembic; alembic auto-commits between statements
when ``transactional_ddl`` is set to False per-step. We use
``op.execute("COMMIT")`` to force a commit after each ADD VALUE so the
later ``ALTER COLUMN`` (still in the same migration) can rely on the
enum being usable. ``IF NOT EXISTS`` makes the ADD VALUE idempotent so
re-running the migration is safe.

Revision ID: e2f3a4b5c6d7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-31
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str]] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum additions. Must each commit before the value is usable in
    # subsequent statements within the same migration script.
    op.execute("ALTER TYPE integration_auth_kind ADD VALUE IF NOT EXISTS 'none'")
    op.execute("COMMIT")
    op.execute("ALTER TYPE integration_identity_kind ADD VALUE IF NOT EXISTS 'none'")
    op.execute("COMMIT")

    # Drop NOT NULL on vault_secret_id so 'none'-auth rows can omit it.
    op.execute('ALTER TABLE "integration" ALTER COLUMN vault_secret_id DROP NOT NULL')


def downgrade() -> None:
    raise NotImplementedError(
        "UC-ES-DB-1.A — relaxing the integration schema is one-way. "
        "Removing an enum value requires rebuilding the type, and "
        "re-imposing NOT NULL on vault_secret_id would require purging "
        "every row that uses auth_kind='none' first. If you genuinely "
        "need to revert, do it by hand with a fresh data-aware migration."
    )
