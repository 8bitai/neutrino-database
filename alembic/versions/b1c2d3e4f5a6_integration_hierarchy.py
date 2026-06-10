"""Add unified integration hierarchy (WF-VS1).

Three tables backing the workflow pillar's connector hierarchy — and,
in later slices, ES + DA once they migrate onto this model:

  * ``integration`` — the universal credential record. ONE row per
    credential; the Vault secret lives behind ``vault_secret_id``.
    owner_kind ∈ {tenant, user}; CHECK ties it to the nullability of
    owner_user_id / workspace_id. ``capabilities`` (text[]) is the
    cross-pillar axis (ingest / query / act).
  * ``integration_workspace_enablement`` — per-workspace opt-in for a
    tenant integration, with capability scope-down.
  * ``integration_member_grant`` — per-member ACL (deny-wins), same
    shape as workspace_da_access_grant.

Six enums:

  * integration_owner_kind          tenant | user
  * integration_identity_kind       user | app | service_account
  * integration_auth_kind           oauth2 | api_key | basic | custom
  * integration_status              active | disabled | revoked | expired
  * integration_enablement_status   active | disabled
  * integration_grant_effect        allow | deny

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-05-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


owner_kind_enum = ENUM(
    "tenant", "user", name="integration_owner_kind", create_type=False
)
identity_kind_enum = ENUM(
    "user", "app", "service_account",
    name="integration_identity_kind", create_type=False,
)
auth_kind_enum = ENUM(
    "oauth2", "api_key", "basic", "custom",
    name="integration_auth_kind", create_type=False,
)
status_enum = ENUM(
    "active", "disabled", "revoked", "expired",
    name="integration_status", create_type=False,
)
enablement_status_enum = ENUM(
    "active", "disabled",
    name="integration_enablement_status", create_type=False,
)
grant_effect_enum = ENUM(
    "allow", "deny", name="integration_grant_effect", create_type=False
)


def upgrade() -> None:
    owner_kind_enum.create(op.get_bind(), checkfirst=False)
    identity_kind_enum.create(op.get_bind(), checkfirst=False)
    auth_kind_enum.create(op.get_bind(), checkfirst=False)
    status_enum.create(op.get_bind(), checkfirst=False)
    enablement_status_enum.create(op.get_bind(), checkfirst=False)
    grant_effect_enum.create(op.get_bind(), checkfirst=False)

    # -- integration --------------------------------------------------------
    op.create_table(
        "integration",
        sa.Column(
            "id", UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id", UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("owner_kind", owner_kind_enum, nullable=False),
        sa.Column(
            "owner_user_id", UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "workspace_id", UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("vault_secret_id", sa.String(512), nullable=False),
        sa.Column("identity_kind", identity_kind_enum, nullable=False),
        sa.Column("identity_label", sa.String(255), nullable=True),
        sa.Column("auth_kind", auth_kind_enum, nullable=False),
        sa.Column("oauth_scopes_granted", ARRAY(sa.Text), nullable=True),
        sa.Column("instance_url", sa.String(512), nullable=True),
        sa.Column("external_account_id", sa.String(255), nullable=True),
        sa.Column("external_account_name", sa.String(255), nullable=True),
        sa.Column("capabilities", ARRAY(sa.Text), nullable=False),
        sa.Column(
            "status", status_enum, nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("last_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "metadata", JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_by", UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "(owner_kind = 'tenant' AND owner_user_id IS NULL AND workspace_id IS NULL) "
            "OR (owner_kind = 'user' AND owner_user_id IS NOT NULL AND workspace_id IS NOT NULL)",
            name="ck_integration_owner_kind_invariant",
        ),
        sa.UniqueConstraint(
            "tenant_id", "provider", "external_account_id",
            name="ux_integration_tenant_provider_account",
        ),
    )
    op.create_index(
        "ix_integration_tenant_provider", "integration",
        ["tenant_id", "provider"],
    )
    op.create_index(
        "ix_integration_owner_user", "integration", ["owner_user_id"],
    )

    # -- integration_workspace_enablement -----------------------------------
    op.create_table(
        "integration_workspace_enablement",
        sa.Column(
            "id", UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "integration_id", UUID(as_uuid=False),
            sa.ForeignKey("integration.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "workspace_id", UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("capabilities_enabled", ARRAY(sa.Text), nullable=False),
        sa.Column("display_name_override", sa.String(255), nullable=True),
        sa.Column(
            "status", enablement_status_enum, nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "enabled_by", UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=False,
        ),
        sa.Column(
            "enabled_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "integration_id", "workspace_id",
            name="ux_integration_enablement_integration_workspace",
        ),
    )
    op.create_index(
        "ix_integration_enablement_workspace",
        "integration_workspace_enablement", ["workspace_id"],
    )

    # -- integration_member_grant -------------------------------------------
    op.create_table(
        "integration_member_grant",
        sa.Column(
            "id", UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id", UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "integration_id", UUID(as_uuid=False),
            sa.ForeignKey("integration.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column("effect", grant_effect_enum, nullable=False),
        sa.Column(
            "created_by", UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "workspace_id", "user_id", "integration_id", "capability",
            name="ux_integration_member_grant_member_integration_cap",
        ),
    )
    op.create_index(
        "ix_integration_member_grant_workspace_user",
        "integration_member_grant", ["workspace_id", "user_id"],
    )
    op.create_index(
        "ix_integration_member_grant_integration",
        "integration_member_grant", ["integration_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integration_member_grant_integration",
        table_name="integration_member_grant",
    )
    op.drop_index(
        "ix_integration_member_grant_workspace_user",
        table_name="integration_member_grant",
    )
    op.drop_table("integration_member_grant")

    op.drop_index(
        "ix_integration_enablement_workspace",
        table_name="integration_workspace_enablement",
    )
    op.drop_table("integration_workspace_enablement")

    op.drop_index("ix_integration_owner_user", table_name="integration")
    op.drop_index("ix_integration_tenant_provider", table_name="integration")
    op.drop_table("integration")

    sa.Enum(name="integration_grant_effect").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="integration_enablement_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="integration_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="integration_auth_kind").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="integration_identity_kind").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="integration_owner_kind").drop(op.get_bind(), checkfirst=False)
