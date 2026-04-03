from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from models.song import Song, SongStatus
from services.song_service import SongService


class FakeSession:
    def __init__(self, store: list[Song]) -> None:
        self._store = store

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb

    def add(self, song: Song) -> None:
        next_id = max((item.id for item in self._store), default=0) + 1
        song.id = next_id
        now = datetime.now(UTC)
        song.created_at = now
        song.updated_at = now
        self._store.append(song)

    async def commit(self) -> None:
        return None

    async def refresh(self, song: Song) -> None:
        song.updated_at = datetime.now(UTC)

    async def get(self, model: type[Song], song_id: int) -> Song | None:
        del model
        for song in self._store:
            if song.id == song_id:
                return song
        return None

    async def scalars(self, statement: Any) -> list[Song]:
        sql = str(statement)
        params = statement.compile().params
        songs = list(self._store)

        status = params.get("status_1")
        if isinstance(status, SongStatus):
            songs = [song for song in songs if song.status is status]

        term = params.get("lower_1")
        if isinstance(term, str):
            lowered = term.lower()
            songs = [
                song
                for song in songs
                if lowered in song.title.lower()
                or lowered in song.artist_or_source.lower()
                or any(lowered in tag.lower() for tag in song.tags)
            ]

        if "ORDER BY songs.title ASC" in sql:
            songs.sort(key=lambda song: song.title.lower())

        return songs


class FakeSessionFactory:
    def __init__(self) -> None:
        self._store: list[Song] = []

    def __call__(self) -> FakeSession:
        return FakeSession(self._store)


@pytest.fixture
def song_service() -> SongService:
    return SongService(FakeSessionFactory())  # type: ignore[arg-type]
