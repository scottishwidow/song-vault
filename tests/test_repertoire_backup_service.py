from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from db.base import Base
from db.session import build_session_factory, create_engine
from models.song import Song, SongStatus
from models.song_chart import SongChart, SongChartStatus
from services.repertoire_backup_service import (
    BACKUP_MANIFEST_VERSION,
    BackupValidationError,
    RepertoireBackupService,
)
from storage.chart_storage import ChartStorageError, StoredChartBinary, StoredChartObject


class FakeChartStorage:
    def __init__(self, bucket: str = "song-vault-charts") -> None:
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []

    async def ensure_ready(self) -> None:
        return None

    async def put_chart(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
    ) -> StoredChartObject:
        self.objects[object_key] = (content, content_type)
        return StoredChartObject(
            bucket=self.bucket,
            key=object_key,
            size_bytes=len(content),
            content_type=content_type,
        )

    async def get_chart(self, *, bucket: str, object_key: str) -> StoredChartBinary:
        if bucket != self.bucket or object_key not in self.objects:
            raise ChartStorageError("Object not found.")
        content, content_type = self.objects[object_key]
        return StoredChartBinary(content=content, content_type=content_type)

    async def delete_chart(self, *, bucket: str, object_key: str) -> None:
        if bucket != self.bucket:
            return None
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)


@pytest_asyncio.fixture
async def backup_fixture(
    tmp_path: Path,
) -> tuple[
    RepertoireBackupService,
    async_sessionmaker[AsyncSession],
    FakeChartStorage,
    AsyncEngine,
]:
    db_file = tmp_path / "backup-test.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(engine)
    storage = FakeChartStorage()
    service = RepertoireBackupService(session_factory=session_factory, storage=storage)
    try:
        yield service, session_factory, storage, engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_export_backup_contains_manifest_and_chart_files(
    backup_fixture: tuple[
        RepertoireBackupService,
        async_sessionmaker[AsyncSession],
        FakeChartStorage,
        AsyncEngine,
    ],
) -> None:
    service, session_factory, storage, _ = backup_fixture
    now = datetime.now(UTC)
    storage.objects["songs/1/chart.png"] = (b"chart-1", "image/png")

    async with session_factory() as session:
        async with session.begin():
            session.add(
                Song(
                    id=1,
                    title="Cornerstone",
                    artist_or_source="Hillsong",
                    key="C",
                    capo=2,
                    time_signature="4/4",
                    tempo_bpm=72,
                    tags=["worship"],
                    notes="Lead with guitar.",
                    arrangement_notes="Build from verse two.",
                    status=SongStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                SongChart(
                    id=11,
                    song_id=1,
                    storage_bucket=storage.bucket,
                    storage_key="songs/1/chart.png",
                    original_filename="chart.png",
                    content_type="image/png",
                    file_size_bytes=7,
                    source_url="https://example.com/chart",
                    chart_key="C",
                    status=SongChartStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )

    archive = await service.export_backup()

    with ZipFile(BytesIO(archive.content), mode="r") as zip_file:
        manifest = json.loads(zip_file.read("manifest.json").decode("utf-8"))
        assert manifest["version"] == BACKUP_MANIFEST_VERSION
        assert len(manifest["songs"]) == 1
        assert manifest["songs"][0]["capo"] == 2
        assert manifest["songs"][0]["time_signature"] == "4/4"
        assert manifest["songs"][0]["arrangement_notes"] == "Build from verse two."

        assert len(manifest["charts"]) == 1
        chart_path = manifest["charts"][0]["archive_path"]
        assert zip_file.read(chart_path) == b"chart-1"


@pytest.mark.asyncio
async def test_import_backup_replaces_existing_data_and_deletes_old_storage(
    backup_fixture: tuple[
        RepertoireBackupService,
        async_sessionmaker[AsyncSession],
        FakeChartStorage,
        AsyncEngine,
    ],
) -> None:
    service, session_factory, storage, _ = backup_fixture
    now = datetime.now(UTC)

    storage.objects["songs/old/chart-old.png"] = (b"old-chart", "image/png")
    async with session_factory() as session:
        async with session.begin():
            session.add(
                Song(
                    id=1,
                    title="Old Song",
                    artist_or_source="Source",
                    key="D",
                    status=SongStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                SongChart(
                    id=1,
                    song_id=1,
                    storage_bucket=storage.bucket,
                    storage_key="songs/old/chart-old.png",
                    original_filename="chart-old.png",
                    content_type="image/png",
                    file_size_bytes=9,
                    source_url=None,
                    chart_key=None,
                    status=SongChartStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )

    backup_bytes = _build_backup_zip(
        songs=[
            {
                "id": 20,
                "title": "New Song",
                "artist_or_source": "New Source",
                "key": "E",
                "capo": 1,
                "time_signature": "6/8",
                "tempo_bpm": 68,
                "tags": ["set-opener"],
                "notes": "Acoustic intro.",
                "arrangement_notes": "Pad starts in chorus.",
                "status": "active",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        ],
        charts=[
            {
                "id": 30,
                "song_id": 20,
                "original_filename": "new-song.png",
                "content_type": "image/png",
                "source_url": "https://example.com/new-song",
                "chart_key": "E",
                "status": "active",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "archive_path": "charts/30-new-song.png",
            }
        ],
        chart_files={"charts/30-new-song.png": b"new-chart"},
    )

    summary = await service.import_backup(backup_bytes)

    assert summary.song_count == 1
    assert summary.chart_count == 1
    assert "songs/old/chart-old.png" in storage.deleted

    async with session_factory() as session:
        songs = list(await session.scalars(select(Song).order_by(Song.id)))
        charts = list(await session.scalars(select(SongChart).order_by(SongChart.id)))

    assert [song.id for song in songs] == [20]
    assert songs[0].title == "New Song"
    assert songs[0].arrangement_notes == "Pad starts in chorus."
    assert [chart.id for chart in charts] == [30]
    assert charts[0].song_id == 20
    assert charts[0].storage_key in storage.objects
    assert storage.objects[charts[0].storage_key][0] == b"new-chart"


@pytest.mark.asyncio
async def test_import_backup_rejects_missing_chart_file(
    backup_fixture: tuple[
        RepertoireBackupService,
        async_sessionmaker[AsyncSession],
        FakeChartStorage,
        AsyncEngine,
    ],
) -> None:
    service, session_factory, _, _ = backup_fixture
    now = datetime.now(UTC)
    invalid_backup = _build_backup_zip(
        songs=[
            {
                "id": 5,
                "title": "Anchor",
                "artist_or_source": "Maverick City",
                "key": "G",
                "capo": None,
                "time_signature": None,
                "tempo_bpm": None,
                "tags": [],
                "notes": None,
                "arrangement_notes": None,
                "status": "active",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        ],
        charts=[
            {
                "id": 9,
                "song_id": 5,
                "original_filename": "anchor.png",
                "content_type": "image/png",
                "source_url": None,
                "chart_key": None,
                "status": "active",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "archive_path": "charts/9-anchor.png",
            }
        ],
        chart_files={},
    )

    with pytest.raises(BackupValidationError):
        await service.import_backup(invalid_backup)

    async with session_factory() as session:
        assert list(await session.scalars(select(Song))) == []
        assert list(await session.scalars(select(SongChart))) == []


def _build_backup_zip(
    *,
    songs: list[dict[str, object]],
    charts: list[dict[str, object]],
    chart_files: dict[str, bytes],
) -> bytes:
    payload = {
        "version": BACKUP_MANIFEST_VERSION,
        "songs": songs,
        "charts": charts,
    }
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(payload).encode("utf-8"))
        for path, content in chart_files.items():
            archive.writestr(path, content)
    return buffer.getvalue()
