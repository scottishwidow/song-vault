from sqlalchemy.dialects import postgresql

from song_vault.models.song import Song, SongStatus
from song_vault.models.song_chart import SongChart, SongChartStatus


def test_song_status_uses_enum_values_for_postgres_bind() -> None:
    enum_type = Song.__table__.c.status.type
    processor = enum_type.bind_processor(postgresql.dialect())

    assert processor is not None
    assert processor(SongStatus.ACTIVE) == "active"


def test_song_chart_status_uses_enum_values_for_postgres_bind() -> None:
    enum_type = SongChart.__table__.c.status.type
    processor = enum_type.bind_processor(postgresql.dialect())

    assert processor is not None
    assert processor(SongChartStatus.ACTIVE) == "active"
