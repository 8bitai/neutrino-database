"""Add bedrock to llm_providers service_type valid values.

service_type is stored as VARCHAR(50) with no prior check constraint.
This migration adds a check constraint that enumerates all valid
service types (openai, anthropic, gemini, azure_openai, landingai,
bedrock) so that invalid values are rejected at the DB layer.

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
Create Date: 2026-06-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "z3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALID_SERVICE_TYPES = (
    "openai",
    "anthropic",
    "gemini",
    "azure_openai",
    "landingai",
    "bedrock",
)

_CONSTRAINT_NAME = "ck_llm_providers_service_type"


def upgrade() -> None:
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "llm_providers",
        sa.column("service_type").in_(_VALID_SERVICE_TYPES),
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "llm_providers", type_="check")
