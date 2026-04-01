from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from song_vault.models.song import Song
from song_vault.models.song_chart import SongChart, SongChartStatus
from song_vault.services.song_service import SongNotFoundError
from song_vault.storage.chart_storage import ChartStorage


class SongChartNotFoundError(Exception):
    """Raised when a song has no active chart."""


@dataclass(slots=True, frozen=True)
class ChartUpload:
    original_filename: str
    content_type: str
    content: bytes
    source_url: str | None = None
    chart_key: str | None = None


@dataclass(slots=True, frozen=True)
class ChartFile:
    song_id: int
    song_title: str
    original_filename: str
    content_type: str
    source_url: str | None
    chart_key: str | None
    content: bytes


class ChartService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ChartStorage,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage

    async def ensure_storage_ready(self) -> None:
        await self._storage.ensure_ready()

    async def assert_song_exists(self, song_id: int) -> Song:
        async with self._session_factory() as session:
            song = await session.get(Song, song_id)
            if song is None:
                raise SongNotFoundError(f"Song {song_id} was not found.")
            return song

    async def upload_chart(self, song_id: int, payload: ChartUpload) -> SongChart:
        original_filename = _clean_filename(payload.original_filename)
        content_type = _clean_content_type(payload.content_type)
        source_url = _clean_source_url(payload.source_url)
        chart_key = _clean_optional(payload.chart_key)
        object_key = _build_object_key(song_id, original_filename)

        stored_object = await self._storage.put_chart(
            object_key=object_key,
            content=payload.content,
            content_type=content_type,
        )

        try:
            async with self._session_factory() as session:
                song = await session.get(Song, song_id)
                if song is None:
                    raise SongNotFoundError(f"Song {song_id} was not found.")

                statement = select(SongChart).where(
                    SongChart.song_id == song_id,
                    SongChart.status == SongChartStatus.ACTIVE,
                )
                existing_chart = await session.scalar(statement)
                if existing_chart is not None:
                    existing_chart.status = SongChartStatus.ARCHIVED

                new_chart = SongChart(
                    song_id=song_id,
                    storage_bucket=stored_object.bucket,
                    storage_key=stored_object.key,
                    original_filename=original_filename,
                    content_type=content_type,
                    file_size_bytes=stored_object.size_bytes,
                    source_url=source_url,
                    chart_key=chart_key,
                    status=SongChartStatus.ACTIVE,
                )
                session.add(new_chart)
                await session.commit()
                await session.refresh(new_chart)
                return new_chart
        except Exception:
            await self._storage.delete_chart(
                bucket=stored_object.bucket,
                object_key=stored_object.key,
            )
            raise

    async def get_active_chart_file(self, song_id: int) -> ChartFile:
        async with self._session_factory() as session:
            song = await session.get(Song, song_id)
            if song is None:
                raise SongNotFoundError(f"Song {song_id} was not found.")

            statement = select(SongChart).where(
                SongChart.song_id == song_id,
                SongChart.status == SongChartStatus.ACTIVE,
            )
            chart = await session.scalar(statement)
            if chart is None:
                raise SongChartNotFoundError(f"Song {song_id} has no active chart.")

        stored_binary = await self._storage.get_chart(
            bucket=chart.storage_bucket,
            object_key=chart.storage_key,
        )

        return ChartFile(
            song_id=song.id,
            song_title=song.title,
            original_filename=chart.original_filename,
            content_type=chart.content_type or stored_binary.content_type,
            source_url=chart.source_url,
            chart_key=chart.chart_key,
            content=stored_binary.content,
        )


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_filename(original_filename: str) -> str:
    cleaned = original_filename.strip()
    if not cleaned:
        raise ValueError("A filename is required for chart uploads.")
    return cleaned[:255]


def _clean_content_type(content_type: str) -> str:
    cleaned = content_type.strip().lower()
    if not cleaned.startswith("image/"):
        raise ValueError("Chart uploads must be images.")
    return cleaned


def _clean_source_url(source_url: str | None) -> str | None:
    cleaned = _clean_optional(source_url)
    if cleaned is None:
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Source URL must be an http:// or https:// URL.")
    return cleaned


def _build_object_key(song_id: int, original_filename: str) -> str:
    suffix = Path(original_filename).suffix[:10]
    return f"songs/{song_id}/{uuid4().hex}{suffix}"
