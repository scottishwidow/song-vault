"""create song charts table"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260401_0002"
down_revision: str | None = "20260329_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "song_charts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("song_id", sa.Integer(), nullable=False),
        sa.Column("storage_bucket", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("chart_key", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "archived", name="song_chart_status"),
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
        sa.ForeignKeyConstraint(
            ["song_id"],
            ["songs.id"],
            name=op.f("fk_song_charts_song_id_songs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_song_charts")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_song_charts_storage_key")),
    )
    op.create_index(op.f("ix_song_charts_song_id"), "song_charts", ["song_id"], unique=False)
    op.create_index(op.f("ix_song_charts_status"), "song_charts", ["status"], unique=False)
    op.create_index(
        "uq_song_charts_active_song",
        "song_charts",
        ["song_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_song_charts_active_song", table_name="song_charts")
    op.drop_index(op.f("ix_song_charts_status"), table_name="song_charts")
    op.drop_index(op.f("ix_song_charts_song_id"), table_name="song_charts")
    op.drop_table("song_charts")
