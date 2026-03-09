"""add_trace_spans_table

Revision ID: a1b2c3d4e5f6
Revises: 2620a0e773a3
Create Date: 2026-03-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "2620a0e773a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    span_type = sa.Enum("llm", "tool", "agent", name="span_type")
    span_type.create(op.get_bind(), checkfirst=True)

    span_status = sa.Enum("ok", "error", name="span_status")
    span_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "trace_spans",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(26),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_span_id",
            sa.String(26),
            sa.ForeignKey("trace_spans.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("sequence", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "span_type",
            postgresql.ENUM("llm", "tool", "agent", name="span_type", create_type=False),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("ok", "error", name="span_status", create_type=False),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("attributes", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_trace_spans_run_id", "trace_spans", ["run_id"])
    op.create_index("ix_trace_spans_run_type", "trace_spans", ["run_id", "span_type"])
    op.create_index("ix_trace_spans_run_sequence", "trace_spans", ["run_id", "sequence"])
    op.create_index("ix_trace_spans_parent", "trace_spans", ["parent_span_id"])


def downgrade() -> None:
    op.drop_index("ix_trace_spans_parent", table_name="trace_spans")
    op.drop_index("ix_trace_spans_run_type", table_name="trace_spans")
    op.drop_index("ix_trace_spans_run_id", table_name="trace_spans")
    op.drop_table("trace_spans")

    sa.Enum(name="span_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="span_type").drop(op.get_bind(), checkfirst=True)
