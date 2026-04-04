"""split song artist and source url"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260404_0004"
down_revision: str | None = "20260403_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("songs", sa.Column("artist", sa.String(length=255), nullable=True))
    op.add_column("songs", sa.Column("source_url", sa.String(length=1024), nullable=True))
    op.execute("UPDATE songs SET artist = artist_or_source")
    op.alter_column(
        "songs",
        "artist",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.create_index(op.f("ix_songs_artist"), "songs", ["artist"], unique=False)
    op.drop_index(op.f("ix_songs_artist_or_source"), table_name="songs")
    op.drop_column("songs", "artist_or_source")


def downgrade() -> None:
    op.add_column("songs", sa.Column("artist_or_source", sa.String(length=255), nullable=True))
    op.execute("UPDATE songs SET artist_or_source = artist")
    op.alter_column(
        "songs",
        "artist_or_source",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.create_index(op.f("ix_songs_artist_or_source"), "songs", ["artist_or_source"], unique=False)
    op.drop_index(op.f("ix_songs_artist"), table_name="songs")
    op.drop_column("songs", "source_url")
    op.drop_column("songs", "artist")
