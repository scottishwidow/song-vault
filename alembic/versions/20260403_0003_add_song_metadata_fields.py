"""add richer song metadata fields"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260403_0003"
down_revision: str | None = "20260401_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("songs", sa.Column("capo", sa.Integer(), nullable=True))
    op.add_column("songs", sa.Column("time_signature", sa.String(length=16), nullable=True))
    op.add_column("songs", sa.Column("arrangement_notes", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("songs", "arrangement_notes")
    op.drop_column("songs", "time_signature")
    op.drop_column("songs", "capo")
