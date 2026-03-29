"""create songs table"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260329_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "songs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("artist_or_source", sa.String(length=255), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("tempo_bpm", sa.Integer(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column(
            "notes",
            sa.String(length=1000),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "archived", name="song_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_songs")),
    )
    op.create_index(op.f("ix_songs_artist_or_source"), "songs", ["artist_or_source"], unique=False)
    op.create_index(op.f("ix_songs_status"), "songs", ["status"], unique=False)
    op.create_index(op.f("ix_songs_title"), "songs", ["title"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_songs_title"), table_name="songs")
    op.drop_index(op.f("ix_songs_status"), table_name="songs")
    op.drop_index(op.f("ix_songs_artist_or_source"), table_name="songs")
    op.drop_table("songs")
