from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from song_vault.bot.runtime import CHART_SERVICE_KEY, SETTINGS_KEY, SONG_SERVICE_KEY
from song_vault.config.settings import Settings
from song_vault.handlers.charts import chart_command, upload_chart_start
from song_vault.handlers.common import ensure_admin
from song_vault.handlers.repertoire import (
    EDIT_FIELD,
    EDIT_FIELD_KEY,
    EDIT_SONG_ID_KEY,
    EDIT_VALUE,
    RESULT_MESSAGE_CHAR_LIMIT,
    edit_song_field,
    edit_song_start,
    edit_song_value,
    list_songs_command,
    search_songs_command,
)
from song_vault.models.song import Song, SongStatus
from song_vault.services.chart_service import SongChartNotFoundError
from song_vault.services.song_service import SongNotFoundError


def build_context(
    *,
    args: list[str] | None = None,
    admin_ids: tuple[int, ...] = (1,),
    chart_service: object | None = None,
    song_service: object | None = None,
) -> SimpleNamespace:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        ADMIN_TELEGRAM_USER_IDS=admin_ids,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )
    return SimpleNamespace(
        args=args or [],
        user_data={},
        application=SimpleNamespace(
            bot_data={
                SETTINGS_KEY: settings,
                CHART_SERVICE_KEY: chart_service,
                SONG_SERVICE_KEY: song_service,
            }
        ),
    )


def build_update(*, user_id: int = 1) -> tuple[SimpleNamespace, AsyncMock]:
    reply = AsyncMock()
    message = SimpleNamespace(reply_text=reply, text=None)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
    )
    return update, reply


def build_song(
    *,
    song_id: int = 5,
    title: str = "Amazing Grace",
    artist_or_source: str = "Traditional",
    key: str = "G",
    tempo_bpm: int | None = 72,
    tags: list[str] | None = None,
    notes: str | None = "Slow intro.",
) -> Song:
    song = Song(
        title=title,
        artist_or_source=artist_or_source,
        key=key,
        tempo_bpm=tempo_bpm,
        tags=tags or ["hymn", "classic"],
        notes=notes,
        status=SongStatus.ACTIVE,
    )
    song.id = song_id
    now = datetime.now(UTC)
    song.created_at = now
    song.updated_at = now
    return song


@pytest.mark.asyncio
async def test_ensure_admin_rejects_non_admin() -> None:
    update, reply = build_update(user_id=999)
    context = build_context(admin_ids=(1,))

    allowed = await ensure_admin(update, context)

    assert allowed is False
    reply.assert_awaited_once_with("Admin access is required for this command.")


@pytest.mark.asyncio
async def test_search_command_requires_query() -> None:
    update, reply = build_update()
    context = build_context(args=[])

    await search_songs_command(update, context)

    reply.assert_awaited_once_with("Usage: /search <text>")


@pytest.mark.asyncio
async def test_list_songs_command_reports_empty_repertoire() -> None:
    update, reply = build_update()
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[]))
    context = build_context(song_service=song_service)

    await list_songs_command(update, context)

    reply.assert_awaited_once_with("No active songs yet.")


@pytest.mark.asyncio
async def test_list_songs_command_sends_detailed_song_cards_when_result_fits() -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[song]))
    context = build_context(song_service=song_service)

    await list_songs_command(update, context)

    reply.assert_awaited_once()
    message = reply.await_args.args[0]
    assert "Source: Traditional" in message
    assert "Notes: Slow intro." in message
    assert not message.startswith("Active songs (")


@pytest.mark.asyncio
async def test_search_command_sends_detailed_song_cards_when_result_fits() -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(search_songs=AsyncMock(return_value=[song]))
    context = build_context(args=["grace"], song_service=song_service)

    await search_songs_command(update, context)

    reply.assert_awaited_once()
    message = reply.await_args.args[0]
    assert "Source: Traditional" in message
    assert "Notes: Slow intro." in message
    assert not message.startswith('Matches for "grace" (')


@pytest.mark.asyncio
async def test_list_songs_command_falls_back_to_compact_summary_when_output_is_long() -> None:
    update, reply = build_update()
    song = build_song(notes="x" * (RESULT_MESSAGE_CHAR_LIMIT + 100))
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[song]))
    context = build_context(song_service=song_service)

    await list_songs_command(update, context)

    reply.assert_awaited_once()
    message = reply.await_args.args[0]
    assert message.startswith("Active songs (1):")
    assert "#5 Amazing Grace | Traditional | Key: G" in message
    assert "Notes:" not in message
    assert len(message) <= RESULT_MESSAGE_CHAR_LIMIT


@pytest.mark.asyncio
async def test_search_command_falls_back_to_compact_summary_when_output_is_long() -> None:
    update, reply = build_update()
    song = build_song(notes="x" * (RESULT_MESSAGE_CHAR_LIMIT + 100))
    song_service = SimpleNamespace(search_songs=AsyncMock(return_value=[song]))
    context = build_context(args=["grace"], song_service=song_service)

    await search_songs_command(update, context)

    reply.assert_awaited_once()
    message = reply.await_args.args[0]
    assert message.startswith('Matches for "grace" (1):')
    assert "#5 Amazing Grace | Traditional | Key: G" in message
    assert "Notes:" not in message
    assert len(message) <= RESULT_MESSAGE_CHAR_LIMIT


@pytest.mark.asyncio
async def test_search_command_splits_compact_summary_across_multiple_messages() -> None:
    update, reply = build_update()
    songs = [
        build_song(
            song_id=index,
            title=f"Song {index}",
            artist_or_source=f"Source {index}",
            key="C",
            notes="ok",
        )
        for index in range(1, 221)
    ]
    song_service = SimpleNamespace(search_songs=AsyncMock(return_value=songs))
    context = build_context(args=["setlist"], song_service=song_service)

    await search_songs_command(update, context)

    assert reply.await_count > 1
    messages = [call.args[0] for call in reply.await_args_list]
    assert messages[0].startswith('Matches for "setlist" (220):')
    assert messages[1].startswith(f'Matches for "setlist" (220) (cont. 2/{len(messages)}):')
    assert "#1 Song 1 | Source 1 | Key: C" in messages[0]
    assert all(len(message) <= RESULT_MESSAGE_CHAR_LIMIT for message in messages)


@pytest.mark.asyncio
async def test_chart_command_requires_song_id() -> None:
    update, reply = build_update()
    context = build_context(args=[])

    await chart_command(update, context)

    reply.assert_awaited_once_with("Usage: /chart <song_id>")


@pytest.mark.asyncio
async def test_chart_command_reports_missing_chart() -> None:
    update, reply = build_update()
    chart_service = SimpleNamespace(
        get_active_chart_file=AsyncMock(side_effect=SongChartNotFoundError())
    )
    context = build_context(args=["7"], chart_service=chart_service)

    await chart_command(update, context)

    reply.assert_awaited_once_with("No chart uploaded yet for song #7.")


@pytest.mark.asyncio
async def test_upload_chart_start_requires_admin() -> None:
    update, reply = build_update(user_id=2)
    chart_service = SimpleNamespace(assert_song_exists=AsyncMock())
    context = build_context(args=["5"], admin_ids=(1,), chart_service=chart_service)

    state = await upload_chart_start(update, context)

    assert state == -1
    reply.assert_awaited_once_with("Admin access is required for this command.")
    chart_service.assert_song_exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_chart_start_requires_song_id_arg() -> None:
    update, reply = build_update()
    chart_service = SimpleNamespace(assert_song_exists=AsyncMock())
    context = build_context(args=[], chart_service=chart_service)

    state = await upload_chart_start(update, context)

    assert state == -1
    reply.assert_awaited_once_with("Usage: /uploadchart <song_id>")


@pytest.mark.asyncio
async def test_upload_chart_start_reports_missing_song() -> None:
    update, reply = build_update()
    chart_service = SimpleNamespace(
        assert_song_exists=AsyncMock(side_effect=SongNotFoundError("Song 10 was not found."))
    )
    context = build_context(args=["10"], chart_service=chart_service)

    state = await upload_chart_start(update, context)

    assert state == -1
    reply.assert_awaited_once_with("Song 10 was not found.")


@pytest.mark.asyncio
async def test_edit_song_start_shows_editable_field_previews() -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(args=["5"], song_service=song_service)

    state = await edit_song_start(update, context)

    assert state == EDIT_FIELD
    message = reply.await_args.args[0]
    assert "Current editable fields:" in message
    assert "title: Amazing Grace" in message
    assert "artist: Traditional" in message
    assert "tempo: 72" in message
    assert "tags: hymn, classic" in message
    assert "notes: Slow intro." in message


@pytest.mark.asyncio
async def test_edit_song_field_shows_prompt_with_current_value() -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = song.id
    update.effective_message.text = "tempo"

    state = await edit_song_field(update, context)

    assert state == EDIT_VALUE
    message = reply.await_args.args[0]
    assert "New tempo BPM? Use a number or 'clear'." in message
    assert "Current tempo: 72" in message


@pytest.mark.asyncio
async def test_edit_song_field_rejects_unknown_field() -> None:
    update, reply = build_update()
    context = build_context()
    update.effective_message.text = "unsupported"

    state = await edit_song_field(update, context)

    assert state == EDIT_FIELD
    reply.assert_awaited_once_with(
        "Invalid field. Choose one of: title, artist, key, tempo, tags, notes."
    )


@pytest.mark.asyncio
async def test_edit_song_value_retries_on_invalid_tempo() -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(
        get_song=AsyncMock(return_value=song),
        update_song=AsyncMock(),
    )
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = song.id
    context.user_data[EDIT_FIELD_KEY] = "tempo"
    update.effective_message.text = "fast"

    state = await edit_song_value(update, context)

    assert state == EDIT_VALUE
    message = reply.await_args.args[0]
    assert "Tempo must be a number or 'clear'." in message
    assert "Current tempo: 72" in message
    song_service.update_song.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_song_value_retries_on_blank_required_text() -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(
        get_song=AsyncMock(return_value=song),
        update_song=AsyncMock(),
    )
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = song.id
    context.user_data[EDIT_FIELD_KEY] = "title"
    update.effective_message.text = "   "

    state = await edit_song_value(update, context)

    assert state == EDIT_VALUE
    message = reply.await_args.args[0]
    assert "Title cannot be empty. Send a non-empty value." in message
    assert "Current title: Amazing Grace" in message
    song_service.update_song.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "expected_error"),
    [
        ("tags", "Tags must be comma-separated values or 'clear'."),
        ("notes", "Notes must be text or 'clear'."),
    ],
)
async def test_edit_song_value_retries_on_blank_optional_field_input(
    field_name: str,
    expected_error: str,
) -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(
        get_song=AsyncMock(return_value=song),
        update_song=AsyncMock(),
    )
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = song.id
    context.user_data[EDIT_FIELD_KEY] = field_name
    update.effective_message.text = "   "

    state = await edit_song_value(update, context)

    assert state == EDIT_VALUE
    message = reply.await_args.args[0]
    assert expected_error in message
    song_service.update_song.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_song_value_updates_song_and_clears_state() -> None:
    update, reply = build_update()
    updated_song = build_song(title="Amazing Grace (Acoustic)")
    song_service = SimpleNamespace(
        update_song=AsyncMock(return_value=updated_song),
    )
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = updated_song.id
    context.user_data[EDIT_FIELD_KEY] = "title"
    update.effective_message.text = "Amazing Grace (Acoustic)"

    state = await edit_song_value(update, context)

    assert state == -1
    assert EDIT_SONG_ID_KEY not in context.user_data
    assert EDIT_FIELD_KEY not in context.user_data
    update_payload = song_service.update_song.await_args.args[1]
    assert update_payload.values() == {"title": "Amazing Grace (Acoustic)"}
    assert "Updated song:" in reply.await_args.args[0]
