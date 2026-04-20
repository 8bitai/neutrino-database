"""add_excel_datasets_table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    excel_dataset_status = sa.Enum("ready", "failed", "deleted", name="excel_dataset_status")
    excel_dataset_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "excel_datasets",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("schema_name", sa.String(200), nullable=False, unique=True),
        sa.Column("minio_path", sa.String(1000), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("ready", "failed", "deleted", name="excel_dataset_status", create_type=False),
            nullable=False,
        ),
        sa.Column("table_metadata", postgresql.JSONB, nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("error_details", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_excel_datasets_workspace", "excel_datasets", ["workspace_id"])
    op.create_index("ix_excel_datasets_tenant", "excel_datasets", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_excel_datasets_tenant", table_name="excel_datasets")
    op.drop_index("ix_excel_datasets_workspace", table_name="excel_datasets")
    op.drop_table("excel_datasets")

    sa.Enum(name="excel_dataset_status").drop(op.get_bind(), checkfirst=True)
