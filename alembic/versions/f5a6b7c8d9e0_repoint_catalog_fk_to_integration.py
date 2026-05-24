"""Repoint da_catalog_schema FK to integration (DA-U2).

DA warehouse connections now live on the unified `integration` table, so the
catalog's parent FK must point there. Greenfield cutover: there's no live DA
data to back-fill (confirmed dev = 0 rows, no staging/prod DA data), so this is
a pure constraint repoint — drop the FK to da_connection, add it to integration.

The column keeps its legacy name `da_connection_id`; the connection ids are
preserved across the model, so post-cutover catalog rows reference integration
ids under the old column name (rename deferred — TD-DA-CATALOG-COLNAME). Lands
back-to-back with the connector-service repoint (DA-U3) that makes the create /
sync flow write integration rows; until then the catalog write path is idle.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-05-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK = "da_catalog_schema_da_connection_id_fkey"


def upgrade() -> None:
    op.drop_constraint(_FK, "da_catalog_schema", type_="foreignkey")
    op.create_foreign_key(
        _FK,
        "da_catalog_schema",
        "integration",
        ["da_connection_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(_FK, "da_catalog_schema", type_="foreignkey")
    op.create_foreign_key(
        _FK,
        "da_catalog_schema",
        "da_connection",
        ["da_connection_id"],
        ["id"],
        ondelete="CASCADE",
    )
