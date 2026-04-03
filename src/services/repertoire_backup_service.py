from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.song import Song, SongStatus
from models.song_chart import SongChart, SongChartStatus
from storage.chart_storage import ChartStorage, StoredChartObject

MANIFEST_FILENAME = "manifest.json"
BACKUP_MANIFEST_VERSION = 1


class BackupValidationError(Exception):
    """Raised when backup data is malformed."""


@dataclass(slots=True, frozen=True)
class BackupArchive:
    filename: str
    content: bytes
    song_count: int
    chart_count: int


@dataclass(slots=True, frozen=True)
class BackupImportSummary:
    song_count: int
    chart_count: int


@dataclass(slots=True, frozen=True)
class _BackupSong:
    id: int
    title: str
    artist_or_source: str
    key: str
    capo: int | None
    time_signature: str | None
    tempo_bpm: int | None
    tags: list[str]
    notes: str | None
    arrangement_notes: str | None
    status: SongStatus
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class _BackupChart:
    id: int
    song_id: int
    original_filename: str
    content_type: str
    source_url: str | None
    chart_key: str | None
    status: SongChartStatus
    created_at: datetime
    updated_at: datetime
    archive_path: str


@dataclass(slots=True, frozen=True)
class _ParsedBackup:
    songs: list[_BackupSong]
    charts: list[_BackupChart]
    chart_content: dict[str, bytes]


class RepertoireBackupService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ChartStorage,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage

    async def export_backup(self) -> BackupArchive:
        async with self._session_factory() as session:
            songs = list(await session.scalars(select(Song).order_by(Song.id.asc())))
            charts = list(await session.scalars(select(SongChart).order_by(SongChart.id.asc())))

        chart_paths = {
            chart.id: _build_chart_archive_path(chart.id, chart.original_filename)
            for chart in charts
        }
        manifest = {
            "version": BACKUP_MANIFEST_VERSION,
            "songs": [self._serialize_song(song) for song in songs],
            "charts": [
                {
                    **self._serialize_chart(chart),
                    "archive_path": chart_paths[chart.id],
                }
                for chart in charts
            ],
        }

        buffer = BytesIO()
        with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(
                MANIFEST_FILENAME,
                json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
            )
            for chart in charts:
                stored = await self._storage.get_chart(
                    bucket=chart.storage_bucket,
                    object_key=chart.storage_key,
                )
                archive.writestr(chart_paths[chart.id], stored.content)

        file_name = f"song-vault-backup-{datetime.now(UTC):%Y%m%d-%H%M%S}.zip"
        return BackupArchive(
            filename=file_name,
            content=buffer.getvalue(),
            song_count=len(songs),
            chart_count=len(charts),
        )

    async def import_backup(self, archive_bytes: bytes) -> BackupImportSummary:
        parsed = _parse_backup_archive(archive_bytes)

        uploaded_objects: list[StoredChartObject] = []
        uploaded_by_chart_id: dict[int, StoredChartObject] = {}
        restore_prefix = f"imports/{uuid4().hex}"
        try:
            for chart in parsed.charts:
                stored = await self._storage.put_chart(
                    object_key=_build_restore_object_key(
                        restore_prefix=restore_prefix,
                        song_id=chart.song_id,
                        original_filename=chart.original_filename,
                    ),
                    content=parsed.chart_content[chart.archive_path],
                    content_type=chart.content_type,
                )
                uploaded_by_chart_id[chart.id] = stored
                uploaded_objects.append(stored)

            old_objects = await self._replace_repertoire(parsed, uploaded_by_chart_id)
        except Exception:
            await _delete_objects(self._storage, uploaded_objects)
            raise

        await _delete_object_refs(self._storage, old_objects)
        return BackupImportSummary(song_count=len(parsed.songs), chart_count=len(parsed.charts))

    async def _replace_repertoire(
        self,
        parsed: _ParsedBackup,
        uploaded_by_chart_id: dict[int, StoredChartObject],
    ) -> list[tuple[str, str]]:
        old_object_refs: list[tuple[str, str]] = []
        async with self._session_factory() as session:
            async with session.begin():
                existing_charts = list(await session.scalars(select(SongChart)))
                old_object_refs = [
                    (chart.storage_bucket, chart.storage_key) for chart in existing_charts
                ]

                await session.execute(delete(SongChart))
                await session.execute(delete(Song))

                for song in parsed.songs:
                    session.add(
                        Song(
                            id=song.id,
                            title=song.title,
                            artist_or_source=song.artist_or_source,
                            key=song.key,
                            capo=song.capo,
                            time_signature=song.time_signature,
                            tempo_bpm=song.tempo_bpm,
                            tags=song.tags,
                            notes=song.notes,
                            arrangement_notes=song.arrangement_notes,
                            status=song.status,
                            created_at=song.created_at,
                            updated_at=song.updated_at,
                        )
                    )

                for chart in parsed.charts:
                    stored = uploaded_by_chart_id[chart.id]
                    session.add(
                        SongChart(
                            id=chart.id,
                            song_id=chart.song_id,
                            storage_bucket=stored.bucket,
                            storage_key=stored.key,
                            original_filename=chart.original_filename,
                            content_type=chart.content_type,
                            file_size_bytes=stored.size_bytes,
                            source_url=chart.source_url,
                            chart_key=chart.chart_key,
                            status=chart.status,
                            created_at=chart.created_at,
                            updated_at=chart.updated_at,
                        )
                    )

                await _reset_sequences(
                    session,
                    song_max_id=max((song.id for song in parsed.songs), default=0),
                    chart_max_id=max((chart.id for chart in parsed.charts), default=0),
                )
        return old_object_refs

    @staticmethod
    def _serialize_song(song: Song) -> dict[str, object]:
        return {
            "id": song.id,
            "title": song.title,
            "artist_or_source": song.artist_or_source,
            "key": song.key,
            "capo": song.capo,
            "time_signature": song.time_signature,
            "tempo_bpm": song.tempo_bpm,
            "tags": song.tags,
            "notes": song.notes,
            "arrangement_notes": song.arrangement_notes,
            "status": song.status.value,
            "created_at": song.created_at.isoformat(),
            "updated_at": song.updated_at.isoformat(),
        }

    @staticmethod
    def _serialize_chart(chart: SongChart) -> dict[str, object]:
        return {
            "id": chart.id,
            "song_id": chart.song_id,
            "original_filename": chart.original_filename,
            "content_type": chart.content_type,
            "source_url": chart.source_url,
            "chart_key": chart.chart_key,
            "status": chart.status.value,
            "created_at": chart.created_at.isoformat(),
            "updated_at": chart.updated_at.isoformat(),
        }


def _build_chart_archive_path(chart_id: int, original_filename: str) -> str:
    safe_name = Path(original_filename).name or f"chart-{chart_id}"
    return f"charts/{chart_id}-{safe_name}"


def _build_restore_object_key(*, restore_prefix: str, song_id: int, original_filename: str) -> str:
    suffix = Path(original_filename).suffix[:10]
    return f"{restore_prefix}/songs/{song_id}/{uuid4().hex}{suffix}"


def _parse_backup_archive(archive_bytes: bytes) -> _ParsedBackup:
    if not archive_bytes:
        raise BackupValidationError("Backup file is empty.")

    try:
        with ZipFile(BytesIO(archive_bytes), mode="r") as archive:
            manifest = _parse_manifest(archive)
            content_by_path: dict[str, bytes] = {}
            for chart in manifest.charts:
                try:
                    content_by_path[chart.archive_path] = archive.read(chart.archive_path)
                except KeyError as error:
                    raise BackupValidationError(
                        f"Missing chart file '{chart.archive_path}' in backup archive."
                    ) from error
            return _ParsedBackup(
                songs=manifest.songs,
                charts=manifest.charts,
                chart_content=content_by_path,
            )
    except BadZipFile as error:
        raise BackupValidationError("Backup file must be a valid .zip archive.") from error


@dataclass(slots=True, frozen=True)
class _Manifest:
    songs: list[_BackupSong]
    charts: list[_BackupChart]


def _parse_manifest(archive: ZipFile) -> _Manifest:
    try:
        raw_manifest = archive.read(MANIFEST_FILENAME)
    except KeyError as error:
        raise BackupValidationError("Backup archive is missing manifest.json.") from error

    try:
        payload = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupValidationError("Backup manifest.json is invalid JSON.") from error

    if not isinstance(payload, dict):
        raise BackupValidationError("Backup manifest.json must contain an object at the root.")

    version = payload.get("version")
    if version != BACKUP_MANIFEST_VERSION:
        raise BackupValidationError(
            f"Unsupported backup manifest version: {version!r}. Expected {BACKUP_MANIFEST_VERSION}."
        )

    raw_songs = payload.get("songs")
    raw_charts = payload.get("charts")
    if not isinstance(raw_songs, list) or not isinstance(raw_charts, list):
        raise BackupValidationError("Backup manifest must contain 'songs' and 'charts' arrays.")

    songs = [_parse_song_row(item) for item in raw_songs]
    charts = [_parse_chart_row(item) for item in raw_charts]

    song_ids = [song.id for song in songs]
    if len(set(song_ids)) != len(song_ids):
        raise BackupValidationError("Backup contains duplicate song IDs.")

    chart_ids = [chart.id for chart in charts]
    if len(set(chart_ids)) != len(chart_ids):
        raise BackupValidationError("Backup contains duplicate chart IDs.")

    known_song_ids = set(song_ids)
    for chart in charts:
        if chart.song_id not in known_song_ids:
            raise BackupValidationError(
                f"Chart #{chart.id} references unknown song ID {chart.song_id}."
            )
        _validate_archive_path(chart.archive_path)

    return _Manifest(songs=songs, charts=charts)


def _parse_song_row(raw_item: object) -> _BackupSong:
    item = _expect_dict(raw_item, "song entry")
    return _BackupSong(
        id=_expect_int(item, "id", "song"),
        title=_expect_non_empty_str(item, "title", "song"),
        artist_or_source=_expect_non_empty_str(item, "artist_or_source", "song"),
        key=_expect_non_empty_str(item, "key", "song"),
        capo=_expect_optional_int(item, "capo", "song"),
        time_signature=_expect_optional_str(item, "time_signature", "song"),
        tempo_bpm=_expect_optional_int(item, "tempo_bpm", "song"),
        tags=_expect_str_list(item, "tags", "song"),
        notes=_expect_optional_str(item, "notes", "song"),
        arrangement_notes=_expect_optional_str(item, "arrangement_notes", "song"),
        status=_expect_song_status(item, "status"),
        created_at=_expect_datetime(item, "created_at", "song"),
        updated_at=_expect_datetime(item, "updated_at", "song"),
    )


def _parse_chart_row(raw_item: object) -> _BackupChart:
    item = _expect_dict(raw_item, "chart entry")
    content_type = _expect_non_empty_str(item, "content_type", "chart")
    if not content_type.startswith("image/"):
        raise BackupValidationError("Chart content_type must start with 'image/'.")

    return _BackupChart(
        id=_expect_int(item, "id", "chart"),
        song_id=_expect_int(item, "song_id", "chart"),
        original_filename=_expect_non_empty_str(item, "original_filename", "chart"),
        content_type=content_type,
        source_url=_expect_optional_str(item, "source_url", "chart"),
        chart_key=_expect_optional_str(item, "chart_key", "chart"),
        status=_expect_chart_status(item, "status"),
        created_at=_expect_datetime(item, "created_at", "chart"),
        updated_at=_expect_datetime(item, "updated_at", "chart"),
        archive_path=_expect_non_empty_str(item, "archive_path", "chart"),
    )


def _expect_dict(raw_item: object, entry_name: str) -> dict[str, Any]:
    if not isinstance(raw_item, dict):
        raise BackupValidationError(f"Each {entry_name} must be an object.")
    return raw_item


def _expect_int(item: dict[str, Any], key: str, entry_name: str) -> int:
    value = item.get(key)
    if not isinstance(value, int):
        raise BackupValidationError(f"{entry_name}.{key} must be an integer.")
    return value


def _expect_optional_int(item: dict[str, Any], key: str, entry_name: str) -> int | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise BackupValidationError(f"{entry_name}.{key} must be an integer or null.")
    return value


def _expect_non_empty_str(item: dict[str, Any], key: str, entry_name: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BackupValidationError(f"{entry_name}.{key} must be a non-empty string.")
    return value


def _expect_optional_str(item: dict[str, Any], key: str, entry_name: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BackupValidationError(f"{entry_name}.{key} must be a string or null.")
    cleaned = value.strip()
    return cleaned or None


def _expect_str_list(item: dict[str, Any], key: str, entry_name: str) -> list[str]:
    value = item.get(key)
    if not isinstance(value, list) or not all(isinstance(part, str) for part in value):
        raise BackupValidationError(f"{entry_name}.{key} must be a list of strings.")
    return [part for part in value]


def _expect_song_status(item: dict[str, Any], key: str) -> SongStatus:
    raw_status = item.get(key)
    if not isinstance(raw_status, str):
        raise BackupValidationError("song.status must be a string.")
    try:
        return SongStatus(raw_status)
    except ValueError as error:
        raise BackupValidationError(f"Unsupported song.status value: {raw_status!r}.") from error


def _expect_chart_status(item: dict[str, Any], key: str) -> SongChartStatus:
    raw_status = item.get(key)
    if not isinstance(raw_status, str):
        raise BackupValidationError("chart.status must be a string.")
    try:
        return SongChartStatus(raw_status)
    except ValueError as error:
        raise BackupValidationError(f"Unsupported chart.status value: {raw_status!r}.") from error


def _expect_datetime(item: dict[str, Any], key: str, entry_name: str) -> datetime:
    raw_value = item.get(key)
    if not isinstance(raw_value, str):
        raise BackupValidationError(f"{entry_name}.{key} must be an ISO-8601 datetime string.")
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError as error:
        raise BackupValidationError(
            f"{entry_name}.{key} must be a valid ISO-8601 datetime string."
        ) from error


def _validate_archive_path(path_value: str) -> None:
    path = PurePosixPath(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise BackupValidationError(f"Invalid chart archive_path: {path_value!r}.")
    if not path_value.startswith("charts/"):
        raise BackupValidationError("chart.archive_path must be inside the charts/ directory.")


async def _reset_sequences(session: AsyncSession, *, song_max_id: int, chart_max_id: int) -> None:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if song_max_id > 0:
        await session.execute(
            text("SELECT setval(pg_get_serial_sequence('songs', 'id'), :value, true)"),
            {"value": song_max_id},
        )
    else:
        await session.execute(
            text("SELECT setval(pg_get_serial_sequence('songs', 'id'), 1, false)")
        )

    if chart_max_id > 0:
        await session.execute(
            text("SELECT setval(pg_get_serial_sequence('song_charts', 'id'), :value, true)"),
            {"value": chart_max_id},
        )
    else:
        await session.execute(
            text("SELECT setval(pg_get_serial_sequence('song_charts', 'id'), 1, false)")
        )


async def _delete_objects(storage: ChartStorage, objects: list[StoredChartObject]) -> None:
    for obj in objects:
        await storage.delete_chart(bucket=obj.bucket, object_key=obj.key)


async def _delete_object_refs(storage: ChartStorage, refs: list[tuple[str, str]]) -> None:
    for bucket, key in refs:
        await storage.delete_chart(bucket=bucket, object_key=key)
