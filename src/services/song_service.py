from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, cast

from sqlalchemy import String, func, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.song import Song, SongStatus


class SongNotFoundError(Exception):
    """Raised when a song lookup fails."""


class _MissingType:
    pass


MISSING: Final = _MissingType()


@dataclass(slots=True)
class SongCreate:
    title: str
    artist_or_source: str
    key: str
    tempo_bpm: int | None = None
    tags: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(slots=True)
class SongUpdate:
    title: str | _MissingType = MISSING
    artist_or_source: str | _MissingType = MISSING
    key: str | _MissingType = MISSING
    tempo_bpm: int | None | _MissingType = MISSING
    tags: list[str] | _MissingType = MISSING
    notes: str | None | _MissingType = MISSING
    status: SongStatus | _MissingType = MISSING

    def values(self) -> dict[str, object]:
        changes: dict[str, object] = {}
        for field_name in (
            "title",
            "artist_or_source",
            "key",
            "tempo_bpm",
            "tags",
            "notes",
            "status",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, _MissingType):
                changes[field_name] = value
        return changes


def parse_tag_input(raw_value: str) -> list[str]:
    items = [part.strip() for part in raw_value.split(",")]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(item)
    return deduped


def _clean_required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required.")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class SongService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_songs(self, *, include_archived: bool = False) -> list[Song]:
        async with self._session_factory() as session:
            statement = select(Song).order_by(Song.title.asc())
            if not include_archived:
                statement = statement.where(Song.status == SongStatus.ACTIVE)
            result = await session.scalars(statement)
            return list(result)

    async def search_songs(self, query: str, *, include_archived: bool = False) -> list[Song]:
        term = query.strip().lower()
        if not term:
            return []

        async with self._session_factory() as session:
            statement = select(Song).where(
                func.lower(Song.title).contains(term)
                | func.lower(Song.artist_or_source).contains(term)
                | func.lower(sql_cast(Song.tags, String)).contains(term)
            )
            if not include_archived:
                statement = statement.where(Song.status == SongStatus.ACTIVE)
            statement = statement.order_by(Song.title.asc())
            result = await session.scalars(statement)
            return list(result)

    async def get_song(self, song_id: int) -> Song:
        async with self._session_factory() as session:
            song = await session.get(Song, song_id)
            if song is None:
                raise SongNotFoundError(f"Song {song_id} was not found.")
            return song

    async def create_song(self, payload: SongCreate) -> Song:
        song = Song(
            title=_clean_required(payload.title, "title"),
            artist_or_source=_clean_required(payload.artist_or_source, "artist_or_source"),
            key=_clean_required(payload.key, "key"),
            tempo_bpm=payload.tempo_bpm,
            tags=parse_tag_input(",".join(payload.tags)),
            notes=_clean_optional(payload.notes),
            status=SongStatus.ACTIVE,
        )

        async with self._session_factory() as session:
            session.add(song)
            await session.commit()
            await session.refresh(song)
            return song

    async def update_song(self, song_id: int, payload: SongUpdate) -> Song:
        updates = payload.values()
        if not updates:
            raise ValueError("At least one field must be updated.")

        async with self._session_factory() as session:
            song = await session.get(Song, song_id)
            if song is None:
                raise SongNotFoundError(f"Song {song_id} was not found.")

            for field_name, raw_value in updates.items():
                value = raw_value
                if field_name in {"title", "artist_or_source", "key"}:
                    value = _clean_required(cast(str, raw_value), field_name)
                elif field_name == "notes":
                    value = _clean_optional(cast(str | None, raw_value))
                elif field_name == "tags":
                    value = parse_tag_input(",".join(cast(list[str], raw_value)))
                setattr(song, field_name, value)

            await session.commit()
            await session.refresh(song)
            return song

    async def archive_song(self, song_id: int) -> Song:
        return await self.update_song(song_id, SongUpdate(status=SongStatus.ARCHIVED))

    async def list_tags(self) -> list[str]:
        songs = await self.list_songs()
        tags_by_key: dict[str, str] = {}
        for song in songs:
            for tag in song.tags:
                tags_by_key.setdefault(tag.lower(), tag)
        return sorted(tags_by_key.values(), key=str.lower)
