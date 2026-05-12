"""add dashboard tables

Creates the ``dashboard`` and ``dashboard_component`` tables that back the
"pin chart to dashboard" feature. Each ``dashboard_component`` carries
enough context (connector + schema + raw SQL + chart_params) to re-execute
the stored SQL on dashboard load and re-render the chart without going
back through the agent.

Both tables are scoped to a (tenant, workspace) pair — ``workspace_id`` is
required so a dashboard always belongs to exactly one workspace.

Revision ID: d1e2f3a4b5c6
Revises: k8l9m0n1p2q3
Create Date: 2026-05-06 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "k8l9m0n1p2q3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create dashboard + dashboard_component tables."""

    op.create_table(
        "dashboard",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspace.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dashboard_tenant_workspace",
        "dashboard",
        ["tenant_id", "workspace_id"],
    )
    op.create_index(
        "ix_dashboard_workspace_created_by",
        "dashboard",
        ["workspace_id", "created_by"],
    )
    op.create_index(
        "ix_dashboard_workspace_updated_at",
        "dashboard",
        ["workspace_id", "updated_at"],
    )

    op.create_table(
        "dashboard_component",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),

        # SQL re-execution context. The chart was originally rendered against
        # this connector + schema; we re-run the same SQL on dashboard load
        # to refresh the data.
        sa.Column("connector_name", sa.String(length=255), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=True),
        sa.Column("sql", sa.Text(), nullable=False),

        # The user's natural-language question — kept for display / debugging.
        sa.Column("original_query", sa.Text(), nullable=True),

        # How the live data should be rendered.
        sa.Column("chart_type", sa.String(length=64), nullable=False),
        # Persisted output of /visualization/predict — x_axis, chart_title,
        # chart_description, chart_insight.
        sa.Column(
            "chart_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["dashboard_id"], ["dashboard.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspace.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dashboard_component_dashboard",
        "dashboard_component",
        ["dashboard_id"],
    )
    op.create_index(
        "ix_dashboard_component_workspace",
        "dashboard_component",
        ["workspace_id"],
    )


def downgrade() -> None:
    """Drop dashboard tables in reverse dependency order.

    Uses ``DROP INDEX IF EXISTS`` so this downgrade is robust against any
    intermediate revision of this migration that used different index
    names (e.g. an earlier version had ``ix_dashboard_component_tenant``
    and ``ix_dashboard_tenant_created_by`` / ``ix_dashboard_tenant_updated_at``
    before workspace_id became the primary scope).
    """
    # dashboard_component indexes — current and historical names
    op.execute("DROP INDEX IF EXISTS ix_dashboard_component_workspace")
    op.execute("DROP INDEX IF EXISTS ix_dashboard_component_tenant")
    op.execute("DROP INDEX IF EXISTS ix_dashboard_component_dashboard")
    op.execute("DROP TABLE IF EXISTS dashboard_component")

    # dashboard indexes — current and historical names
    op.execute("DROP INDEX IF EXISTS ix_dashboard_workspace_updated_at")
    op.execute("DROP INDEX IF EXISTS ix_dashboard_workspace_created_by")
    op.execute("DROP INDEX IF EXISTS ix_dashboard_tenant_workspace")
    op.execute("DROP INDEX IF EXISTS ix_dashboard_tenant_updated_at")
    op.execute("DROP INDEX IF EXISTS ix_dashboard_tenant_created_by")
    op.execute("DROP TABLE IF EXISTS dashboard")
