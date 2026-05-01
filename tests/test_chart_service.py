from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from models.song import Song, SongStatus
from models.song_chart import SongChart, SongChartStatus
from services.chart_service import ChartService, ChartUpload, SongChartNotFoundError
from services.song_service import SongNotFoundError
from storage.chart_storage import ChartStorageError, StoredChartBinary, StoredChartObject


class FakeChartStorage:
    def __init__(self, bucket: str = "song-vault-charts") -> None:
        self.bucket = bucket
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []
        self.get_requests: list[tuple[str, str]] = []

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
        self.get_requests.append((bucket, object_key))
        if bucket != self.bucket or object_key not in self.objects:
            raise ChartStorageError("Object not found.")
        content, content_type = self.objects[object_key]
        return StoredChartBinary(content=content, content_type=content_type)

    async def delete_chart(self, *, bucket: str, object_key: str) -> None:
        if bucket != self.bucket:
            return None
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)


class FakeSession:
    def __init__(self, songs: dict[int, Song], charts: list[SongChart]) -> None:
        self._songs = songs
        self._charts = charts
        self._next_chart_id = max((item.id for item in charts), default=0) + 1

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb

    async def get(self, model: type[Any], object_id: int) -> Song | None:
        if model is Song:
            return self._songs.get(object_id)
        return None

    async def scalar(self, statement: Any) -> SongChart | None:
        params = statement.compile().params
        song_id = params.get("song_id_1")
        status = params.get("status_1")
        for chart in self._charts:
            if isinstance(song_id, int) and chart.song_id != song_id:
                continue
            if isinstance(status, SongChartStatus) and chart.status is not status:
                continue
            return chart
        return None

    def add(self, chart: SongChart) -> None:
        chart.id = self._next_chart_id
        self._next_chart_id += 1
        now = datetime.now(UTC)
        chart.created_at = now
        chart.updated_at = now
        self._charts.append(chart)

    async def commit(self) -> None:
        return None

    async def refresh(self, chart: SongChart) -> None:
        chart.updated_at = datetime.now(UTC)


class FakeSessionFactory:
    def __init__(self) -> None:
        self.songs: dict[int, Song] = {}
        self.charts: list[SongChart] = []

    def __call__(self) -> FakeSession:
        return FakeSession(self.songs, self.charts)

    def add_song(self, song_id: int, *, title: str) -> Song:
        song = Song(
            title=title,
            artist="source",
            key="C",
            tempo_bpm=None,
            tags=[],
            notes=None,
            status=SongStatus.ACTIVE,
        )
        song.id = song_id
        now = datetime.now(UTC)
        song.created_at = now
        song.updated_at = now
        self.songs[song_id] = song
        return song


@pytest.fixture
def chart_fixture() -> tuple[ChartService, FakeSessionFactory, FakeChartStorage]:
    session_factory = FakeSessionFactory()
    storage = FakeChartStorage()
    chart_service = ChartService(session_factory, storage)  # type: ignore[arg-type]
    return chart_service, session_factory, storage


@pytest.mark.asyncio
async def test_chart_service_uploads_and_fetches_active_chart(
    chart_fixture: tuple[ChartService, FakeSessionFactory, FakeChartStorage],
) -> None:
    chart_service, session_factory, _ = chart_fixture
    song = session_factory.add_song(1, title="Gratitude")

    created = await chart_service.upload_chart(
        song.id,
        ChartUpload(
            original_filename="gratitude.png",
            content_type="image/png",
            content=b"chart-bytes",
            source_url="https://example.org/charts/gratitude",
            chart_key="G",
        ),
    )

    assert created.status is SongChartStatus.ACTIVE
    assert created.file_size_bytes == len(b"chart-bytes")

    chart_file = await chart_service.get_active_chart_file(song.id)
    assert chart_file.song_title == "Gratitude"
    assert chart_file.original_filename == "gratitude.png"
    assert chart_file.content == b"chart-bytes"
    assert chart_file.source_url == "https://example.org/charts/gratitude"
    assert chart_file.chart_key == "G"


@pytest.mark.asyncio
async def test_chart_service_archives_previous_chart_on_replacement(
    chart_fixture: tuple[ChartService, FakeSessionFactory, FakeChartStorage],
) -> None:
    chart_service, session_factory, _ = chart_fixture
    song = session_factory.add_song(2, title="House of the Lord")

    first = await chart_service.upload_chart(
        song.id,
        ChartUpload(
            original_filename="house-v1.jpg",
            content_type="image/jpeg",
            content=b"v1",
        ),
    )
    second = await chart_service.upload_chart(
        song.id,
        ChartUpload(
            original_filename="house-v2.jpg",
            content_type="image/jpeg",
            content=b"v2",
        ),
    )

    assert [chart.status for chart in session_factory.charts] == [
        SongChartStatus.ARCHIVED,
        SongChartStatus.ACTIVE,
    ]
    assert session_factory.charts[0].id == first.id
    assert session_factory.charts[1].id == second.id


@pytest.mark.asyncio
async def test_chart_service_cleans_up_storage_on_missing_song(
    chart_fixture: tuple[ChartService, FakeSessionFactory, FakeChartStorage],
) -> None:
    chart_service, _, storage = chart_fixture

    with pytest.raises(SongNotFoundError):
        await chart_service.upload_chart(
            999,
            ChartUpload(
                original_filename="missing.jpg",
                content_type="image/jpeg",
                content=b"payload",
            ),
        )

    assert len(storage.deleted) == 1
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_chart_service_raises_when_song_has_no_chart(
    chart_fixture: tuple[ChartService, FakeSessionFactory, FakeChartStorage],
) -> None:
    chart_service, session_factory, _ = chart_fixture
    song = session_factory.add_song(3, title="Same God")

    with pytest.raises(SongChartNotFoundError):
        await chart_service.get_active_chart_file(song.id)


@pytest.mark.asyncio
async def test_chart_service_reports_active_chart_availability_without_downloading_bytes(
    chart_fixture: tuple[ChartService, FakeSessionFactory, FakeChartStorage],
) -> None:
    chart_service, session_factory, storage = chart_fixture
    song = session_factory.add_song(4, title="Firm Foundation")

    assert await chart_service.has_active_chart(song.id) is False

    await chart_service.upload_chart(
        song.id,
        ChartUpload(
            original_filename="firm-foundation.png",
            content_type="image/png",
            content=b"chart-bytes",
        ),
    )

    assert await chart_service.has_active_chart(song.id) is True
    assert storage.get_requests == []
