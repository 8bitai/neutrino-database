"""Add Dashboards schema — 3 tables + 4 enum types + chat extensions (NEU-1811 DA-P3.1).

The Dashboards authoring layer. Builds on the DA pillar's chat surface
(DA-P2a) with workspace-scoped authored dashboards composed of widgets
that pull from the curated DA catalog. See
``product-feature-roadmap/data-analytics/data-analytics.md`` D3 / D5 /
D6 / D7 / D11 / D12 and this session's DA-P3 design lock.

Tables created:

  * ``dashboard`` — workspace-scoped authored surface. Draft +
    Published lifecycle; visibility flag controls audience.
  * ``dashboard_widget`` — the widgets that compose a dashboard.
    12-col grid layout (x/y/w/h), inline SQL data binding, viz_spec +
    grounding_metadata JSONB. Back-pointer to the build-chat message
    that proposed it.
  * ``dashboard_link_token`` — anonymous shareable URL tokens for
    external / link-only access. Expire-able, revocable, audited.

Chat table extensions:

  * ``chat.kind`` — ad_hoc | dashboard_build (D6). Splits day-to-day
    Q&A from build conversations. Existing chats default to ad_hoc.
  * ``chat.dashboard_id`` — nullable FK to dashboard (1:1 back-
    pointer to the build chat).

Enum types created:

  * ``dashboard_status``        (draft, published)
  * ``dashboard_visibility``    (workspace_members, restricted, link_only)
  * ``dashboard_widget_type``   (kpi_tile, line_chart, bar_chart,
                                 stacked_bar, pie_chart, donut_chart,
                                 table, text)
  * ``chat_kind``               (ad_hoc, dashboard_build)

FK cascade behaviour (deliberate):

  * dashboard → workspace               CASCADE  (delete workspace = delete its dashboards)
  * dashboard → chat (build_chat_id)    SET NULL (compliance purge of chat keeps the dashboard)
  * dashboard → user (owner / created_by)  SET NULL (GDPR erasure keeps the dashboard)
  * dashboard_widget → dashboard        CASCADE  (delete dashboard = delete its widgets)
  * dashboard_widget → message          SET NULL (message purge keeps the widget)
  * dashboard_link_token → dashboard    CASCADE  (delete dashboard = revoke tokens)
  * chat → dashboard (dashboard_id)     CASCADE  (delete dashboard = delete its build chat)

Note the reciprocal SET NULL / CASCADE pattern between dashboard and
chat is intentional — deleting a dashboard hard-cascades its build
chat (the chat exists for the dashboard), but deleting a chat
independently (compliance purge) keeps the dashboard alive with
``build_chat_id=NULL``.

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
Create Date: 2026-05-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "z3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DASHBOARD_STATUS_VALUES = ("draft", "published")
_DASHBOARD_VISIBILITY_VALUES = (
    "workspace_members",
    "restricted",
    "link_only",
)
_DASHBOARD_WIDGET_TYPE_VALUES = (
    "kpi_tile",
    "line_chart",
    "bar_chart",
    "stacked_bar",
    "pie_chart",
    "donut_chart",
    "table",
    "text",
)
_CHAT_KIND_VALUES = ("ad_hoc", "dashboard_build")


def upgrade() -> None:
    bind = op.get_bind()

    # ----- enum types -----
    postgresql.ENUM(
        *_DASHBOARD_STATUS_VALUES, name="dashboard_status"
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        *_DASHBOARD_VISIBILITY_VALUES, name="dashboard_visibility"
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        *_DASHBOARD_WIDGET_TYPE_VALUES, name="dashboard_widget_type"
    ).create(bind, checkfirst=True)
    postgresql.ENUM(*_CHAT_KIND_VALUES, name="chat_kind").create(
        bind, checkfirst=True
    )

    # ----- dashboard table -----
    op.create_table(
        "dashboard",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="dashboard_status", create_type=False),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "visibility",
            postgresql.ENUM(name="dashboard_visibility", create_type=False),
            nullable=False,
            server_default=sa.text("'workspace_members'"),
        ),
        sa.Column(
            "build_chat_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("chat.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "workspace_id", "slug", name="ux_dashboard_workspace_slug"
        ),
    )
    op.create_index(
        "ix_dashboard_workspace_status",
        "dashboard",
        ["workspace_id", "status"],
    )
    op.create_index("ix_dashboard_tenant", "dashboard", ["tenant_id"])

    # ----- dashboard_widget table -----
    op.create_table(
        "dashboard_widget",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "dashboard_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("dashboard.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "position_x", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "position_y", sa.Integer, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "position_w", sa.Integer, nullable=False, server_default=sa.text("4")
        ),
        sa.Column(
            "position_h", sa.Integer, nullable=False, server_default=sa.text("2")
        ),
        sa.Column(
            "widget_type",
            postgresql.ENUM(name="dashboard_widget_type", create_type=False),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("data_binding", postgresql.JSONB, nullable=False),
        sa.Column("viz_spec", postgresql.JSONB, nullable=False),
        sa.Column("grounding_metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_by_message_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("message.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_dashboard_widget_dashboard",
        "dashboard_widget",
        ["dashboard_id"],
    )

    # ----- dashboard_link_token table -----
    op.create_table(
        "dashboard_link_token",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "dashboard_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("dashboard.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(128), nullable=False),
        sa.Column(
            "expires_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "revoked_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "accessed_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_dashboard_link_token_token",
        "dashboard_link_token",
        ["token"],
        unique=True,
    )
    op.create_index(
        "ix_dashboard_link_token_dashboard",
        "dashboard_link_token",
        ["dashboard_id"],
    )

    # ----- chat extensions -----
    op.add_column(
        "chat",
        sa.Column(
            "kind",
            postgresql.ENUM(name="chat_kind", create_type=False),
            nullable=False,
            server_default=sa.text("'ad_hoc'"),
        ),
    )
    op.add_column(
        "chat",
        sa.Column(
            "dashboard_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey(
                "dashboard.id",
                ondelete="CASCADE",
                name="fk_chat_dashboard_id_dashboard",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Drop in reverse order — chat extensions, then link_token,
    # widgets, dashboards, then enum types.
    op.drop_constraint(
        "fk_chat_dashboard_id_dashboard", "chat", type_="foreignkey"
    )
    op.drop_column("chat", "dashboard_id")
    op.drop_column("chat", "kind")

    op.drop_index(
        "ix_dashboard_link_token_dashboard",
        table_name="dashboard_link_token",
    )
    op.drop_index(
        "ux_dashboard_link_token_token", table_name="dashboard_link_token"
    )
    op.drop_table("dashboard_link_token")

    op.drop_index(
        "ix_dashboard_widget_dashboard", table_name="dashboard_widget"
    )
    op.drop_table("dashboard_widget")

    op.drop_index("ix_dashboard_tenant", table_name="dashboard")
    op.drop_index("ix_dashboard_workspace_status", table_name="dashboard")
    op.drop_table("dashboard")

    bind = op.get_bind()
    postgresql.ENUM(name="chat_kind").drop(bind, checkfirst=True)
    postgresql.ENUM(name="dashboard_widget_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="dashboard_visibility").drop(bind, checkfirst=True)
    postgresql.ENUM(name="dashboard_status").drop(bind, checkfirst=True)
