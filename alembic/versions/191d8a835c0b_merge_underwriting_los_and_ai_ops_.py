"""merge underwriting los and ai_ops correlation branches

Revision ID: 191d8a835c0b
Revises: k8l9m0n1p2q3, l1m2n3o4p5q6
Create Date: 2026-04-24 16:09:18.224446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '191d8a835c0b'
down_revision: Union[str, Sequence[str], None] = ('k8l9m0n1p2q3', 'l1m2n3o4p5q6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
