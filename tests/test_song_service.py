import pytest

from models.song import SongStatus
from services.song_service import SongCreate, SongNotFoundError, SongUpdate


@pytest.mark.asyncio
async def test_song_service_create_list_search_update_and_archive(song_service) -> None:
    created = await song_service.create_song(
        SongCreate(
            title="Cornerstone",
            artist_or_source="Hillsong",
            key="C",
            capo=3,
            time_signature="6/8",
            tempo_bpm=72,
            tags=["worship", "opening"],
            notes="Keep intro short.",
            arrangement_notes="Start with piano only.",
        )
    )

    songs = await song_service.list_songs()
    assert [song.title for song in songs] == ["Cornerstone"]

    search_results = await song_service.search_songs("worship")
    assert [song.id for song in search_results] == [created.id]

    updated = await song_service.update_song(
        created.id,
        SongUpdate(
            title="Cornerstone (Acoustic)",
            capo=None,
            time_signature="4/4",
            tempo_bpm=None,
            tags=["worship", "acoustic"],
            arrangement_notes="Strip back verse one.",
        ),
    )
    assert updated.title == "Cornerstone (Acoustic)"
    assert updated.capo is None
    assert updated.time_signature == "4/4"
    assert updated.tempo_bpm is None
    assert updated.tags == ["worship", "acoustic"]
    assert updated.arrangement_notes == "Strip back verse one."

    archived = await song_service.archive_song(created.id)
    assert archived.status is SongStatus.ARCHIVED
    assert await song_service.list_songs() == []
    assert len(await song_service.list_songs(include_archived=True)) == 1


@pytest.mark.asyncio
async def test_song_service_lists_unique_tags(song_service) -> None:
    await song_service.create_song(
        SongCreate(
            title="Build My Life",
            artist_or_source="Housefires",
            key="D",
            tags=["Worship", "Prayer"],
        )
    )
    await song_service.create_song(
        SongCreate(
            title="Gratitude",
            artist_or_source="Brandon Lake",
            key="G",
            tags=["worship", "Response"],
        )
    )

    assert await song_service.list_tags() == ["Prayer", "Response", "Worship"]


@pytest.mark.asyncio
async def test_song_service_raises_for_missing_song(song_service) -> None:
    with pytest.raises(SongNotFoundError):
        await song_service.get_song(999)
