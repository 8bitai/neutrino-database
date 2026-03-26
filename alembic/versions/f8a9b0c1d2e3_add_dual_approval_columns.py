"""Add dual-approval columns (app_decision, email_decision) to ai_ops_approvals.

Revision ID: f8a9b0c1d2e3
Revises: e6f7a8b9c0d1, c3d4e5f6a7b8
Create Date: 2026-03-23
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str]] = ("e6f7a8b9c0d1", "c3d4e5f6a7b8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_ops_approvals", sa.Column("app_decision", sa.String(50), nullable=True))
    op.add_column("ai_ops_approvals", sa.Column("app_decided_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("ai_ops_approvals", sa.Column("email_decision", sa.String(50), nullable=True))
    op.add_column("ai_ops_approvals", sa.Column("email_decided_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_ops_approvals", "email_decided_at")
    op.drop_column("ai_ops_approvals", "email_decision")
    op.drop_column("ai_ops_approvals", "app_decided_at")
    op.drop_column("ai_ops_approvals", "app_decision")
