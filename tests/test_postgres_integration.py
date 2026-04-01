from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from song_vault.db.session import build_session_factory, create_engine
from song_vault.models.song import SongStatus
from song_vault.services.song_service import SongCreate, SongService

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def postgres_database_url() -> str:
    database_url = os.getenv(TEST_DATABASE_URL_ENV)
    if not database_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not set; skipping Postgres integration tests.")
    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.fail(
            f"{TEST_DATABASE_URL_ENV} must use a SQLAlchemy async Postgres URL "
            "(postgresql+asyncpg://...)."
        )
    return database_url


@pytest.fixture(scope="session")
def migrated_postgres_url(postgres_database_url: str) -> str:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", postgres_database_url)

    try:
        command.downgrade(config, "base")
    except CommandError:
        # Fresh databases may not have an alembic version row yet.
        pass

    command.upgrade(config, "head")
    return postgres_database_url


@pytest_asyncio.fixture
async def postgres_engine(migrated_postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(migrated_postgres_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(sa.text("TRUNCATE TABLE songs RESTART IDENTITY CASCADE"))
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def postgres_session_factory(
    postgres_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield build_session_factory(postgres_engine)


@pytest.mark.asyncio
async def test_migrations_create_expected_schema(postgres_engine: AsyncEngine) -> None:
    async with postgres_engine.connect() as connection:
        song_columns_result = await connection.execute(
            sa.text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'songs'
                ORDER BY ordinal_position
                """
            )
        )
        song_columns = [row[0] for row in song_columns_result.all()]

        chart_columns_result = await connection.execute(
            sa.text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'song_charts'
                ORDER BY ordinal_position
                """
            )
        )
        chart_columns = [row[0] for row in chart_columns_result.all()]

        enum_result = await connection.execute(
            sa.text(
                """
                SELECT e.enumlabel
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = 'song_status'
                ORDER BY e.enumsortorder
                """
            )
        )
        enum_labels = [row[0] for row in enum_result.all()]

        chart_enum_result = await connection.execute(
            sa.text(
                """
                SELECT e.enumlabel
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = 'song_chart_status'
                ORDER BY e.enumsortorder
                """
            )
        )
        chart_enum_labels = [row[0] for row in chart_enum_result.all()]

        index_result = await connection.execute(
            sa.text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'song_charts'
                  AND indexname = 'uq_song_charts_active_song'
                """
            )
        )
        active_chart_index = index_result.scalar_one()

    assert song_columns == [
        "id",
        "title",
        "artist_or_source",
        "key",
        "tempo_bpm",
        "tags",
        "notes",
        "status",
        "created_at",
        "updated_at",
    ]
    assert chart_columns == [
        "id",
        "song_id",
        "storage_bucket",
        "storage_key",
        "original_filename",
        "content_type",
        "file_size_bytes",
        "source_url",
        "chart_key",
        "status",
        "created_at",
        "updated_at",
    ]
    assert enum_labels == ["active", "archived"]
    assert chart_enum_labels == ["active", "archived"]
    assert "status = 'active'" in active_chart_index


@pytest.mark.asyncio
async def test_song_service_persists_in_postgres(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    song_service = SongService(postgres_session_factory)

    created = await song_service.create_song(
        SongCreate(
            title="King of Kings",
            artist_or_source="Hillsong Worship",
            key="A",
            tempo_bpm=68,
            tags=["worship", "resurrection"],
            notes="Use a softer intro.",
        )
    )

    second = await song_service.create_song(
        SongCreate(
            title="No Longer Slaves",
            artist_or_source="Bethel Music",
            key="G",
            tags=["response"],
        )
    )

    search_results = await song_service.search_songs("resurrection")
    assert [song.id for song in search_results] == [created.id]

    archived = await song_service.archive_song(second.id)
    assert archived.status is SongStatus.ARCHIVED

    active_titles = [song.title for song in await song_service.list_songs()]
    assert active_titles == ["King of Kings"]

    all_titles = [song.title for song in await song_service.list_songs(include_archived=True)]
    assert all_titles == ["King of Kings", "No Longer Slaves"]


@pytest.mark.asyncio
async def test_song_chart_active_constraint_is_enforced(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    song_service = SongService(postgres_session_factory)
    song = await song_service.create_song(
        SongCreate(
            title="Holy Forever",
            artist_or_source="Bethel Music",
            key="E",
        )
    )

    async with postgres_session_factory() as session:
        await session.execute(
            sa.text(
                """
                INSERT INTO song_charts (
                    song_id,
                    storage_bucket,
                    storage_key,
                    original_filename,
                    content_type,
                    file_size_bytes,
                    source_url,
                    chart_key,
                    status
                )
                VALUES (
                    :song_id,
                    'song-vault-charts',
                    'songs/holy-forever-v1.jpg',
                    'holy-forever-v1.jpg',
                    'image/jpeg',
                    12,
                    NULL,
                    NULL,
                    'active'
                )
                """
            ),
            {"song_id": song.id},
        )
        await session.commit()

    with pytest.raises(IntegrityError):
        async with postgres_session_factory() as session:
            await session.execute(
                sa.text(
                    """
                    INSERT INTO song_charts (
                        song_id,
                        storage_bucket,
                        storage_key,
                        original_filename,
                        content_type,
                        file_size_bytes,
                        source_url,
                        chart_key,
                        status
                    )
                    VALUES (
                        :song_id,
                        'song-vault-charts',
                        'songs/holy-forever-v2.jpg',
                        'holy-forever-v2.jpg',
                        'image/jpeg',
                        12,
                        NULL,
                        NULL,
                        'active'
                    )
                    """
                ),
                {"song_id": song.id},
            )
            await session.commit()
