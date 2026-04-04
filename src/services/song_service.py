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
    artist: str
    key: str
    source_url: str | None = None
    capo: int | None = None
    time_signature: str | None = None
    tempo_bpm: int | None = None
    tags: list[str] = field(default_factory=list)
    notes: str | None = None
    arrangement_notes: str | None = None


@dataclass(slots=True)
class SongUpdate:
    title: str | _MissingType = MISSING
    artist: str | _MissingType = MISSING
    source_url: str | None | _MissingType = MISSING
    key: str | _MissingType = MISSING
    capo: int | None | _MissingType = MISSING
    time_signature: str | None | _MissingType = MISSING
    tempo_bpm: int | None | _MissingType = MISSING
    tags: list[str] | _MissingType = MISSING
    notes: str | None | _MissingType = MISSING
    arrangement_notes: str | None | _MissingType = MISSING
    status: SongStatus | _MissingType = MISSING

    def values(self) -> dict[str, object]:
        changes: dict[str, object] = {}
        for field_name in (
            "title",
            "artist",
            "source_url",
            "key",
            "capo",
            "time_signature",
            "tempo_bpm",
            "tags",
            "notes",
            "arrangement_notes",
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


def _clean_capo(capo: int | None) -> int | None:
    if capo is None:
        return None
    if capo <= 0:
        raise ValueError("Capo must be a positive integer.")
    return capo


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
                | func.lower(Song.artist).contains(term)
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
            artist=_clean_required(payload.artist, "artist"),
            source_url=_clean_optional(payload.source_url),
            key=_clean_required(payload.key, "key"),
            capo=_clean_capo(payload.capo),
            time_signature=_clean_optional(payload.time_signature),
            tempo_bpm=payload.tempo_bpm,
            tags=parse_tag_input(",".join(payload.tags)),
            notes=_clean_optional(payload.notes),
            arrangement_notes=_clean_optional(payload.arrangement_notes),
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
                if field_name in {"title", "artist", "key"}:
                    value = _clean_required(cast(str, raw_value), field_name)
                elif field_name in {"source_url", "notes", "time_signature", "arrangement_notes"}:
                    value = _clean_optional(cast(str | None, raw_value))
                elif field_name == "capo":
                    value = _clean_capo(cast(int | None, raw_value))
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
