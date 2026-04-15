"""Add vault_path columns for OpenBao secret storage.

Revision ID: k1l2m3n4o5p6
Revises: j7k8l9m0n1p2
Create Date: 2026-04-15 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, Sequence[str], None] = "j7k8l9m0n1p2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("vault_path", sa.Text(), nullable=True))
    op.alter_column("providers", "encrypted_value", existing_type=sa.Text(), nullable=True)
    op.execute("ALTER TABLE providers ALTER COLUMN encryption_method SET DEFAULT 'openbao'")

    op.add_column("credentials", sa.Column("vault_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("credentials", "vault_path")

    op.execute("ALTER TABLE providers ALTER COLUMN encryption_method SET DEFAULT 'AES-256-GCM'")
    op.alter_column("providers", "encrypted_value", existing_type=sa.Text(), nullable=False)
    op.drop_column("providers", "vault_path")
