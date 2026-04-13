"""Add governance defaults to LLM provider model_config.

Revision ID: j7k8l9m0n1p2
Revises: a7b8c9d0e1f2
Create Date: 2026-04-13 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "j7k8l9m0n1p2"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE providers
        SET model_config = jsonb_set(
            COALESCE(model_config, '{}'::jsonb),
            '{governance}',
            COALESCE(model_config->'governance', '{
                "enabled": false,
                "strategy": "regex",
                "apply_to_embeddings": false,
                "store_lookup_values_in_traces": true
            }'::jsonb),
            true
        )
        WHERE provider_category = 'llm'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE providers
        SET model_config = COALESCE(model_config, '{}'::jsonb) - 'governance'
        WHERE provider_category = 'llm'
        """
    )
