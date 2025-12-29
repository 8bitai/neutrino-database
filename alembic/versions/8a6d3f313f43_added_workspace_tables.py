"""added workspace tables

Revision ID: 8a6d3f313f43
Revises: a3235d7ece3f
Create Date: 2025-12-23 19:13:09.361896

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a6d3f313f43'
down_revision: Union[str, Sequence[str], None] = 'a3235d7ece3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Create workspace table WITHOUT created_by FK
    op.create_table('workspace',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('ACTIVE', 'DELETED', name='workspace_status'), server_default='ACTIVE', nullable=False),
        sa.Column('created_by', sa.UUID(as_uuid=False), nullable=True),  # Column exists but no FK yet
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='ux_workspace_tenant_name')
    )
    op.create_index('ix_workspace_tenant', 'workspace', ['tenant_id'], unique=False)
    op.create_index('ix_workspace_tenant_status', 'workspace', ['tenant_id', 'status'], unique=False)

    # Step 2: Add default_workspace_id to user table
    op.add_column('user', sa.Column('default_workspace_id', sa.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key('fk_user_default_workspace_id', 'user', 'workspace', ['default_workspace_id'], ['id'], ondelete='SET NULL')

    # Step 3: Now add the created_by FK to workspace
    op.create_foreign_key('fk_workspace_created_by', 'workspace', 'user', ['created_by'], ['id'], ondelete='SET NULL')

    # Step 4: Create workspace_access_request
    op.create_table('workspace_access_request',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('workspace_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='workspace_access_status'), server_default='PENDING', nullable=False),
        sa.Column('requested_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reviewed_by', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('reviewed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['reviewed_by'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workspace_access_request_user_status', 'workspace_access_request', ['user_id', 'status'], unique=False)
    op.create_index('ix_workspace_access_request_workspace_status', 'workspace_access_request', ['workspace_id', 'status'], unique=False)

    # Step 5: Create workspace_invitation
    op.create_table('workspace_invitation',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('workspace_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('inviter', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('is_workspace_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['inviter'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workspace_invitation_email', 'workspace_invitation', ['email'], unique=False)
    op.create_index('ix_workspace_invitation_expires_at', 'workspace_invitation', ['expires_at'], unique=False)
    op.create_index('ix_workspace_invitation_workspace_email', 'workspace_invitation', ['workspace_id', 'email'], unique=False)

    # Step 6: Create workspace_member
    op.create_table('workspace_member',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('workspace_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('is_workspace_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'user_id', name='ux_workspace_member_workspace_user')
    )
    op.create_index('ix_workspace_member_user', 'workspace_member', ['user_id'], unique=False)
    op.create_index('ix_workspace_member_workspace', 'workspace_member', ['workspace_id'], unique=False)
    op.create_index('ix_workspace_member_workspace_admin', 'workspace_member', ['workspace_id', 'is_workspace_admin'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop tables in reverse order
    op.drop_index('ix_workspace_member_workspace_admin', table_name='workspace_member')
    op.drop_index('ix_workspace_member_workspace', table_name='workspace_member')
    op.drop_index('ix_workspace_member_user', table_name='workspace_member')
    op.drop_table('workspace_member')

    op.drop_index('ix_workspace_invitation_workspace_email', table_name='workspace_invitation')
    op.drop_index('ix_workspace_invitation_expires_at', table_name='workspace_invitation')
    op.drop_index('ix_workspace_invitation_email', table_name='workspace_invitation')
    op.drop_table('workspace_invitation')

    op.drop_index('ix_workspace_access_request_workspace_status', table_name='workspace_access_request')
    op.drop_index('ix_workspace_access_request_user_status', table_name='workspace_access_request')
    op.drop_table('workspace_access_request')

    # Drop FKs before dropping tables
    op.drop_constraint('fk_workspace_created_by', 'workspace', type_='foreignkey')
    op.drop_constraint('fk_user_default_workspace_id', 'user', type_='foreignkey')
    op.drop_column('user', 'default_workspace_id')

    op.drop_index('ix_workspace_tenant_status', table_name='workspace')
    op.drop_index('ix_workspace_tenant', table_name='workspace')
    op.drop_table('workspace')