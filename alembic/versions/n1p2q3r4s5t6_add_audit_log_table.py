"""Add audit_log — append-only compliance event store (NEU-1804, slice C3a).

The audit_log table is the foundation for every compliance reporting
need (SOC 2 CC6.6, HIPAA § 164.312(b), GDPR Art 30/32). Every meaningful
mutation in the gateway will write a single row here so we can answer
"who did what to which resource at what time" — required by every
framework's audit / access-review controls.

The table is **append-only**: a Postgres BEFORE UPDATE/DELETE trigger
raises SQLSTATE 'AU001' so the immutability invariant holds at the
database level (auditors won't accept "we promise we don't update it").

The matching SQLAlchemy event hook in ``tables.py`` installs the same
trigger when ``Base.metadata.create_all`` runs, so tests and production
end up with identical DDL.

See ``user-stories/user-lifecycle.md`` § "Audit log requirements" for
the product-level specification and event-type catalog.

Revision ID: n1p2q3r4s5t6
Revises: m0n1p2q3r4s5
Create Date: 2026-04-29 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID


revision: str = "n1p2q3r4s5t6"
down_revision: Union[str, Sequence[str], None] = "m0n1p2q3r4s5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # NO ACTION (default): a tenant cannot be hard-deleted while audit
        # history references it. Retention runner clears audit_log first.
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            sa.ForeignKey("tenant.id"),
            nullable=False,
        ),
        # Nullable for system-initiated events; SET NULL on user hard-delete
        # so audit entries survive the user.
        sa.Column(
            "actor_user_id",
            UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column(
            "event_metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ip_address", INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # PII tags — read by the C6 anonymization runner.
    op.execute(
        "COMMENT ON COLUMN audit_log.ip_address IS 'pii:ipaddress'"
    )
    op.execute(
        "COMMENT ON COLUMN audit_log.user_agent IS 'pii:freetext'"
    )

    # Read-path indexes.
    op.execute(
        "CREATE INDEX ix_audit_log_tenant_occurred_at "
        "ON audit_log (tenant_id, occurred_at DESC)"
    )
    op.create_index(
        "ix_audit_log_event_type",
        "audit_log",
        ["event_type"],
    )
    op.execute(
        "CREATE INDEX ix_audit_log_actor_occurred_at "
        "ON audit_log (actor_user_id, occurred_at DESC) "
        "WHERE actor_user_id IS NOT NULL"
    )

    # Immutability: BEFORE UPDATE/DELETE trigger raises SQLSTATE 'AU001'.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_block_mutation() RETURNS trigger AS $func$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; UPDATE/DELETE blocked'
                USING ERRCODE = 'AU001';
        END;
        $func$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_immutability "
        "BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutability ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_mutation()")
    op.drop_index("ix_audit_log_actor_occurred_at", table_name="audit_log")
    op.drop_index("ix_audit_log_event_type", table_name="audit_log")
    op.drop_index("ix_audit_log_tenant_occurred_at", table_name="audit_log")
    op.drop_table("audit_log")
