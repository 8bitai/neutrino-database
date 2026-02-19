"""Add retrieval_strategy to orchestrator_config

Revision ID: b5e8f2a3c1d4
Revises: 02de7a8c7705
Create Date: 2026-01-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'b5e8f2a3c1d4'
down_revision: Union[str, Sequence[str], None] = '02de7a8c7705'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the retrieval_strategy enum type
    retrieval_strategy_enum = sa.Enum(
        'SEMANTIC', 'KEYWORD', 'HYBRID', 'AGENTIC',
        name='retrieval_strategy',
        create_type=False
    )
    
    # Create enum type in database
    op.execute("CREATE TYPE retrieval_strategy AS ENUM ('SEMANTIC', 'KEYWORD', 'HYBRID', 'AGENTIC')")
    
    # Add retrieval_strategy column with default HYBRID
    op.add_column(
        'orchestrator_config',
        sa.Column(
            'retrieval_strategy',
            retrieval_strategy_enum,
            nullable=False,
            server_default='HYBRID'
        )
    )
    
    # Add retrieval_config JSONB column for top_k and semantic_weight
    op.add_column(
        'orchestrator_config',
        sa.Column(
            'retrieval_config',
            JSONB,
            nullable=False,
            server_default='{"top_k": 3, "semantic_weight": 0.3}'
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('orchestrator_config', 'retrieval_config')
    op.drop_column('orchestrator_config', 'retrieval_strategy')
    op.execute("DROP TYPE IF EXISTS retrieval_strategy")

