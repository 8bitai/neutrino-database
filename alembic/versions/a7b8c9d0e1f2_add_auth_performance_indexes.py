"""add auth performance indexes

Revision ID: a7b8c9d0e1f2
Revises: 0e2ffac974b4
Create Date: 2026-04-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = '0e2ffac974b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Login and forgot-password query on lower(email) across all tenants.
    # Without this, every login/reset does a sequential scan on "user".
    op.create_index(
        'ix_user_email_lower_active',
        'user',
        [sa.literal_column('lower(email)')],
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    # Login query also matches on lower(username); the existing
    # ix_user_tenant_username_lower is tenant-scoped and can't serve
    # the cross-tenant lookup used by local-auth login.
    op.create_index(
        'ix_user_username_lower_active',
        'user',
        [sa.literal_column('lower(username)')],
        postgresql_where=sa.text('deleted_at IS NULL AND username IS NOT NULL'),
    )

    # Workspace invitation lookups always filter for pending
    # (accepted_at IS NULL, deleted_at IS NULL). A partial index
    # avoids scanning historical/deleted rows.
    op.create_index(
        'ix_workspace_invitation_email_pending',
        'workspace_invitation',
        ['email'],
        postgresql_where=sa.text('accepted_at IS NULL AND deleted_at IS NULL'),
    )

    # Same pattern for tenant-level user invitations.
    op.create_index(
        'ix_user_invitation_tenant_email_pending',
        'user_invitation',
        ['tenant_id', 'email'],
        postgresql_where=sa.text('accepted_at IS NULL AND deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'ix_user_invitation_tenant_email_pending',
        table_name='user_invitation',
        postgresql_where=sa.text('accepted_at IS NULL AND deleted_at IS NULL'),
    )
    op.drop_index(
        'ix_workspace_invitation_email_pending',
        table_name='workspace_invitation',
        postgresql_where=sa.text('accepted_at IS NULL AND deleted_at IS NULL'),
    )
    op.drop_index(
        'ix_user_username_lower_active',
        table_name='user',
        postgresql_where=sa.text('deleted_at IS NULL AND username IS NOT NULL'),
    )
    op.drop_index(
        'ix_user_email_lower_active',
        table_name='user',
        postgresql_where=sa.text('deleted_at IS NULL'),
    )
