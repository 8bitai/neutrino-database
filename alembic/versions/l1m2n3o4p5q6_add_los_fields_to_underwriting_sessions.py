"""add los fields to underwriting_sessions

Revision ID: l1m2n3o4p5q6
Revises: 0e2ffac974b4
Create Date: 2026-04-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l1m2n3o4p5q6'
down_revision: Union[str, Sequence[str], None] = '0e2ffac974b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column})
    return result.fetchone() is not None


def upgrade() -> None:
    """Add LOS pipeline display columns to underwriting_sessions."""
    if not _column_exists("underwriting_sessions", "los_application_id"):
        op.add_column("underwriting_sessions", sa.Column("los_application_id", sa.Text(), nullable=True))
        op.create_unique_constraint("uq_underwriting_sessions_los_application_id", "underwriting_sessions", ["los_application_id"])

    if not _column_exists("underwriting_sessions", "channel"):
        op.add_column("underwriting_sessions", sa.Column("channel", sa.Text(), nullable=True))

    if not _column_exists("underwriting_sessions", "officer_name"):
        op.add_column("underwriting_sessions", sa.Column("officer_name", sa.Text(), nullable=True))

    if not _column_exists("underwriting_sessions", "phone"):
        op.add_column("underwriting_sessions", sa.Column("phone", sa.Text(), nullable=True))

    if not _column_exists("underwriting_sessions", "dob"):
        op.add_column("underwriting_sessions", sa.Column("dob", sa.Text(), nullable=True))

    if not _column_exists("underwriting_sessions", "employment_type"):
        op.add_column("underwriting_sessions", sa.Column("employment_type", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove LOS pipeline display columns from underwriting_sessions."""
    op.drop_constraint("uq_underwriting_sessions_los_application_id", "underwriting_sessions", type_="unique")
    op.drop_column("underwriting_sessions", "los_application_id")
    op.drop_column("underwriting_sessions", "channel")
    op.drop_column("underwriting_sessions", "officer_name")
    op.drop_column("underwriting_sessions", "phone")
    op.drop_column("underwriting_sessions", "dob")
    op.drop_column("underwriting_sessions", "employment_type")
