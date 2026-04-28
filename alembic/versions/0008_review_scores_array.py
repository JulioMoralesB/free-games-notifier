"""Rename review_score to review_scores and migrate to JSON array format.

Each game previously stored a single review-score string in ``review_score``.
The field is renamed to ``review_scores`` and its value is now a JSON array
so multiple sources (Steam user reviews, Metacritic, OpenCritic) can be
stored together.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-27

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new array column (stored as JSON text).
    op.execute("""
        ALTER TABLE free_games.games
        ADD COLUMN IF NOT EXISTS review_scores TEXT
    """)

    # Migrate existing single-string scores into a JSON array.
    # json_build_array handles quoting/escaping correctly for any string value.
    op.execute("""
        UPDATE free_games.games
        SET review_scores = CASE
            WHEN review_score IS NOT NULL AND review_score <> ''
                THEN json_build_array(review_score)::text
            ELSE '[]'
        END
        WHERE review_scores IS NULL
    """)

    # Remove the old column.
    op.execute("""
        ALTER TABLE free_games.games
        DROP COLUMN IF EXISTS review_score
    """)


def downgrade() -> None:
    # Re-add the single-value column.
    op.execute("""
        ALTER TABLE free_games.games
        ADD COLUMN IF NOT EXISTS review_score TEXT
    """)

    # Restore by extracting the first element of the JSON array (if any).
    op.execute("""
        UPDATE free_games.games
        SET review_score = CASE
            WHEN review_scores IS NOT NULL AND review_scores <> '[]'
                THEN review_scores::json->>0
            ELSE NULL
        END
    """)

    op.execute("""
        ALTER TABLE free_games.games
        DROP COLUMN IF EXISTS review_scores
    """)
