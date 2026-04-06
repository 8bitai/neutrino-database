"""add_local_auth_columns_and_invited_user_status

Revision ID: e6144cac2db4
Revises: 9d3c7b2a1f44
Create Date: 2026-04-06 15:55:23.363299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e6144cac2db4'
down_revision: Union[str, Sequence[str], None] = '9d3c7b2a1f44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add local-auth columns, unique constraint, and case-insensitive index to user table."""
    op.add_column('user', sa.Column('username', sa.String(100), nullable=True))
    op.add_column('user', sa.Column('password_hash', sa.Text(), nullable=True))
    op.add_column('user', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('user', sa.Column('password_changed_at', sa.TIMESTAMP(timezone=True), nullable=True))

    op.create_unique_constraint('ux_user_tenant_username', 'user', ['tenant_id', 'username'])
    op.create_index(
        'ix_user_tenant_username_lower', 'user',
        ['tenant_id', sa.literal_column('lower(username)')],
        unique=True,
        postgresql_where=sa.text('username IS NOT NULL'),
    )


def downgrade() -> None:
    """Remove local-auth columns, unique constraint, and case-insensitive index from user table."""
    op.drop_index('ix_user_tenant_username_lower', table_name='user', postgresql_where=sa.text('username IS NOT NULL'))
    op.drop_constraint('ux_user_tenant_username', 'user', type_='unique')
    op.drop_column('user', 'password_changed_at')
    op.drop_column('user', 'must_change_password')
    op.drop_column('user', 'password_hash')
    op.drop_column('user', 'username')
