"""integration owner_kind workspace tier (workspace-owned connections)

Revision ID: c1d2e3f4a5b6
Revises: a6b7c8d9e0f1
Create Date: 2026-05-25

S1 of the workspace-owned-connections work. Adds the 'workspace' owner tier
to the integration_owner_kind enum and extends the owner_kind invariant
CHECK so a workspace-owned row is (owner_user_id NULL, workspace_id NOT NULL)
— the workspace_id column doubles as the owning workspace for this tier.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INVARIANT = "ck_integration_owner_kind_invariant"


def upgrade() -> None:
    # ADD VALUE must be committed before the recreated CHECK can reference
    # 'workspace' (Postgres won't let a new enum value be used in the same
    # transaction that added it), so do it in an autocommit block.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE integration_owner_kind ADD VALUE IF NOT EXISTS 'workspace'"
        )
    op.execute(f"ALTER TABLE integration DROP CONSTRAINT {_INVARIANT}")
    op.execute(
        f"ALTER TABLE integration ADD CONSTRAINT {_INVARIANT} CHECK ("
        "(owner_kind = 'tenant' AND owner_user_id IS NULL AND workspace_id IS NULL) "
        "OR (owner_kind = 'user' AND owner_user_id IS NOT NULL "
        "AND workspace_id IS NOT NULL) "
        "OR (owner_kind = 'workspace' AND owner_user_id IS NULL "
        "AND workspace_id IS NOT NULL)"
        ")"
    )


def downgrade() -> None:
    # Postgres can't drop an enum value, so leave 'workspace' on the type
    # and just restore the two-tier invariant. Any owner_kind='workspace'
    # rows must be removed first or this fails by design (they'd violate
    # the restored CHECK).
    op.execute(f"ALTER TABLE integration DROP CONSTRAINT {_INVARIANT}")
    op.execute(
        f"ALTER TABLE integration ADD CONSTRAINT {_INVARIANT} CHECK ("
        "(owner_kind = 'tenant' AND owner_user_id IS NULL AND workspace_id IS NULL) "
        "OR (owner_kind = 'user' AND owner_user_id IS NOT NULL "
        "AND workspace_id IS NOT NULL)"
        ")"
    )
