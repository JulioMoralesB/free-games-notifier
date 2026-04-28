"""Add game_type column to games table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-27

Adds a ``game_type`` column (TEXT, NOT NULL, DEFAULT 'game') so the system
can distinguish standalone games from DLC promotions. Existing rows are
backfilled to 'game'.

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE free_games.games
        ADD COLUMN IF NOT EXISTS game_type TEXT NOT NULL DEFAULT 'game'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE free_games.games
        DROP COLUMN IF EXISTS game_type
    """)
