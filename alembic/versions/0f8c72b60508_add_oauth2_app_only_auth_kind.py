"""UC-ES-DB-1.D.1e — split oauth2 into delegated vs app-only.

The existing ``oauth2`` value on ``integration_auth_kind`` is ambiguous:
it doesn't distinguish the standard authorization-code grant
(delegated — the user signs in, the app acts AS that user) from the
client-credentials grant (app-only — the app authenticates as itself,
e.g. SharePoint Sites.Selected). The two have very different security
shapes; the SOC2 evidence chain ("how did this credential
authenticate?") MUST disambiguate them.

After this migration:
  * ``oauth2``           — delegated authorization-code grant (the
                            standard "OAuth popup → sign in" flow).
  * ``oauth2_app_only``  — client-credentials grant (the app
                            authenticates as itself; needs admin pre-grant
                            on the destination, e.g. Sites.Selected).

Pre-production note: no rows currently use ``oauth2`` (SharePoint hasn't
successfully connected via the unified framework yet), so no data
backfill is needed. The existing SharePoint provider spec is updated in
the next commit to use ``oauth2_app_only`` for its current behaviour and
to additionally declare ``oauth2`` for the delegated path landing in
D.1.f / D.1.g.

Revision ID: 0f8c72b60508
Revises: e3f4a5b6c7d8
"""

from __future__ import annotations

from alembic import op


revision: str = "0f8c72b60508"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres requires ADD VALUE outside any transaction the surrounding
    # block opens. Same pattern as the ``none`` addition in
    # ``e2f3a4b5c6d7_relax_integration_for_es_uploads``.
    op.execute(
        "ALTER TYPE integration_auth_kind ADD VALUE IF NOT EXISTS 'oauth2_app_only'"
    )
    op.execute("COMMIT")


def downgrade() -> None:
    # Postgres does not support DROP VALUE on an enum; downgrade is a
    # no-op (pre-prod, see migration docstring — no rows to clean).
    pass
