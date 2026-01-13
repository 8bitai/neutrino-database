"""Add Google IDP Provider

Revision ID: c4abbcc55cb8
Revises: b5e8f2a3c1d4
Create Date: 2026-01-13 11:35:49.410720

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c4abbcc55cb8'
down_revision: Union[str, Sequence[str], None] = 'b5e8f2a3c1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add GOOGLE_IDENTITY to idp_provider enum
    op.execute("ALTER TYPE idp_provider ADD VALUE IF NOT EXISTS 'GOOGLE_IDENTITY'")


def downgrade() -> None:
    """Downgrade schema."""
    # Note: PostgreSQL does not support removing enum values directly.
    # To properly downgrade, you would need to:
    # 1. Create a new enum type without GOOGLE_IDENTITY
    # 2. Update all columns using idp_provider to the new type
    # 3. Drop the old enum and rename the new one
    # This is complex and risky, so we leave it as a no-op.
    # If downgrade is critical, ensure no data uses GOOGLE_IDENTITY before downgrading.
    pass
