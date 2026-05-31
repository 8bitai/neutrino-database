"""[NEU-1816] UC-ES-DB-1.A — relax integration schema for ES uploads.

The canonical `integration` table was built for SaaS connectors (Jira,
Slack, GitHub, DA Postgres) where every row has a remote credential and
a vault secret. To collapse the legacy `datasources` table onto
`integration`, we need to accept rows that represent local-only sources
(member uploads a PDF / CSV) where there is no remote auth, no remote
identity, and no secret to vault.

Three contract points:

  1. ``IntegrationAuthKindEnum`` exposes ``NONE = "none"`` for sources
     that don't authenticate against a remote system (manual upload).
  2. ``IntegrationIdentityKindEnum`` exposes ``NONE = "none"`` for the
     same reason — there is no identity the destination SaaS sees.
  3. ``integration.vault_secret_id`` is NULLABLE so the no-secret case
     can be stored without a placeholder.

This test fails today (enum values absent, column NOT NULL) and passes
after the enums.py update + tables.py edit + alembic migration land.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from neutrino_database.models.enums import (
    IntegrationAuthKindEnum,
    IntegrationIdentityKindEnum,
)


def test_auth_kind_enum_exposes_none():
    values = {member.value for member in IntegrationAuthKindEnum}
    assert "none" in values, (
        "IntegrationAuthKindEnum must expose a 'none' value so ES upload "
        "sources (PDF / CSV / Drive-upload / manual) can sit on the "
        "integration table. Add `NONE = \"none\"` to the enum class in "
        "neutrino_database/models/enums.py."
    )


def test_identity_kind_enum_exposes_none():
    values = {member.value for member in IntegrationIdentityKindEnum}
    assert "none" in values, (
        "IntegrationIdentityKindEnum must expose a 'none' value for "
        "sources that have no remote identity (member upload, local file). "
        "Add `NONE = \"none\"` to the enum class in "
        "neutrino_database/models/enums.py."
    )


@pytest.mark.asyncio
async def test_integration_vault_secret_id_is_nullable(test_engine):
    async with test_engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {
                c["name"]: c
                for c in sa.inspect(sync_conn).get_columns("integration")
            }
        )
    assert "vault_secret_id" in cols, "integration table missing vault_secret_id"
    assert cols["vault_secret_id"]["nullable"] is True, (
        "integration.vault_secret_id must be NULLABLE so ES upload sources "
        "(no remote auth, no secret to vault) can be stored as integration "
        "rows. Update the Column(...) in tables.py and add an alembic "
        "migration that ALTERs the column to DROP NOT NULL."
    )
