from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Chat, Message, Update, User

from bot.runtime import BACKUP_SERVICE_KEY, CHART_SERVICE_KEY, SETTINGS_KEY, SONG_SERVICE_KEY
from config.settings import Settings
from handlers.backup import (
    IMPORT_BACKUP_UPLOAD,
    build_import_backup_handler,
    cancel_import_backup,
    export_backup_command,
    import_backup_file,
    import_backup_start,
)
from handlers.charts import (
    build_upload_chart_handler,
    cancel_upload_chart,
    chart_command,
    upload_chart_start,
)
from handlers.common import ensure_admin
from handlers.repertoire import (
    EDIT_FIELD,
    EDIT_FIELD_KEY,
    EDIT_SONG_ID_KEY,
    EDIT_VALUE,
    RESULT_MESSAGE_CHAR_LIMIT,
    build_add_song_handler,
    build_edit_song_handler,
    cancel_command,
    edit_song_field,
    edit_song_start,
    edit_song_value,
    list_songs_command,
    search_songs_command,
)
from handlers.ui import MENU_START
from models.song import Song, SongStatus
from services.chart_service import SongChartNotFoundError
from services.repertoire_backup_service import BackupArchive
from services.song_service import SongNotFoundError


def build_context(
    *,
    args: list[str] | None = None,
    admin_ids: tuple[int, ...] = (1,),
    chart_service: object | None = None,
    song_service: object | None = None,
    backup_service: object | None = None,
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
                BACKUP_SERVICE_KEY: backup_service,
            }
        ),
    )


def build_update(*, user_id: int = 1) -> tuple[SimpleNamespace, AsyncMock]:
    reply = AsyncMock()
    reply_document = AsyncMock()
    message = SimpleNamespace(
        reply_text=reply,
        reply_document=reply_document,
        text=None,
        document=None,
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
        effective_chat=SimpleNamespace(type="private"),
    )
    return update, reply


def build_song(
    *,
    song_id: int = 5,
    title: str = "Amazing Grace",
    artist: str = "Traditional",
    source_url: str | None = None,
    key: str = "G",
    capo: int | None = 1,
    time_signature: str | None = "3/4",
    tempo_bpm: int | None = 72,
    tags: list[str] | None = None,
    notes: str | None = "Slow intro.",
    arrangement_notes: str | None = "Lift dynamics in verse two.",
) -> Song:
    song = Song(
        title=title,
        artist=artist,
        source_url=source_url,
        key=key,
        capo=capo,
        time_signature=time_signature,
        tempo_bpm=tempo_bpm,
        tags=tags or ["hymn", "classic"],
        notes=notes,
        arrangement_notes=arrangement_notes,
        status=SongStatus.ACTIVE,
    )
    song.id = song_id
    now = datetime.now(UTC)
    song.created_at = now
    song.updated_at = now
    return song


def build_telegram_update(*, edited: bool, text: str = "value") -> Update:
    user = User(id=1, first_name="Test", is_bot=False)
    chat = Chat(id=1, type="private")
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        text=text,
    )
    if edited:
        return Update(update_id=2, edited_message=message)
    return Update(update_id=1, message=message)


@pytest.mark.asyncio
async def test_ensure_admin_rejects_non_admin() -> None:
    update, reply = build_update(user_id=999)
    context = build_context(admin_ids=(1,))

    allowed = await ensure_admin(update, context)

    assert allowed is False
    reply.assert_awaited_once_with("Admin access is required for this action.")


def test_add_song_conversation_filters_ignore_edited_messages() -> None:
    handler = build_add_song_handler()
    message_update = build_telegram_update(edited=False)
    edited_update = build_telegram_update(edited=True)

    for state_handlers in handler.states.values():
        for state_handler in state_handlers:
            assert bool(state_handler.check_update(message_update))
            assert not bool(state_handler.check_update(edited_update))


def test_edit_song_conversation_filters_ignore_edited_messages() -> None:
    handler = build_edit_song_handler()
    message_update = build_telegram_update(edited=False)
    edited_update = build_telegram_update(edited=True)

    for state_handlers in handler.states.values():
        for state_handler in state_handlers:
            assert bool(state_handler.check_update(message_update))
            assert not bool(state_handler.check_update(edited_update))


def test_upload_chart_conversation_filters_ignore_edited_messages() -> None:
    handler = build_upload_chart_handler()
    message_update = build_telegram_update(edited=False)
    edited_update = build_telegram_update(edited=True)

    for state_handlers in handler.states.values():
        for state_handler in state_handlers:
            assert bool(state_handler.check_update(message_update))
            assert not bool(state_handler.check_update(edited_update))


def test_import_backup_conversation_filters_ignore_edited_messages() -> None:
    handler = build_import_backup_handler()
    message_update = build_telegram_update(edited=False)
    edited_update = build_telegram_update(edited=True)

    for state_handlers in handler.states.values():
        for state_handler in state_handlers:
            assert bool(state_handler.check_update(message_update))
            assert not bool(state_handler.check_update(edited_update))


@pytest.mark.parametrize(
    "handler_factory",
    [
        build_add_song_handler,
        build_edit_song_handler,
        build_upload_chart_handler,
        build_import_backup_handler,
    ],
)
def test_conversation_state_handlers_do_not_consume_cancel_button(handler_factory: object) -> None:
    handler = handler_factory()
    cancel_update = build_telegram_update(edited=False, text="Cancel")

    for state_handlers in handler.states.values():
        for state_handler in state_handlers:
            assert not bool(state_handler.check_update(cancel_update))

    assert any(bool(fallback.check_update(cancel_update)) for fallback in handler.fallbacks)


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
    assert "Artist: Traditional" in message
    assert "Source: -" in message
    assert "Notes: Slow intro." in message
    assert "Capo: 1" in message
    assert "Time signature: 3/4" in message
    assert "Arrangement notes: Lift dynamics in verse two." in message
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
    assert "Artist: Traditional" in message
    assert "Source: -" in message
    assert "Notes: Slow intro." in message
    assert "Capo: 1" in message
    assert "Time signature: 3/4" in message
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
            artist=f"Source {index}",
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
    reply.assert_awaited_once_with("Admin access is required for this action.")
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
    assert "source: -" in message
    assert "capo: 1" in message
    assert "time_signature: 3/4" in message
    assert "tempo: 72" in message
    assert "tags: hymn, classic" in message
    assert "notes: Slow intro." in message
    assert "arrangement_notes: Lift dynamics in verse two." in message
    assert "Tap Cancel to stop." in message
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == "Cancel"


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
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == "Cancel"


@pytest.mark.asyncio
async def test_edit_song_field_accepts_source_field() -> None:
    update, reply = build_update()
    song = build_song(source_url="https://example.org/source")
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = song.id
    update.effective_message.text = "source"

    state = await edit_song_field(update, context)

    assert state == EDIT_VALUE
    message = reply.await_args.args[0]
    assert "New source URL? Use text or 'clear'." in message
    assert "Current source URL: https://example.org/source" in message
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == "Cancel"


@pytest.mark.asyncio
async def test_edit_song_field_rejects_unknown_field() -> None:
    update, reply = build_update()
    context = build_context()
    update.effective_message.text = "unsupported"

    state = await edit_song_field(update, context)

    assert state == EDIT_FIELD
    assert reply.await_args.args[0] == (
        "Invalid field. Choose one of: title, artist, source, key, capo, "
        "time_signature, tempo, tags, notes, arrangement_notes."
    )
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == "Cancel"


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
        ("source", "Source URL must be text or 'clear'."),
        ("time_signature", "Time signature must be text or 'clear'."),
        ("tags", "Tags must be comma-separated values or 'clear'."),
        ("notes", "Notes must be text or 'clear'."),
        ("arrangement_notes", "Arrangement notes must be text or 'clear'."),
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


@pytest.mark.asyncio
async def test_export_backup_command_requires_admin() -> None:
    update, reply = build_update(user_id=2)
    backup_service = SimpleNamespace(export_backup=AsyncMock())
    context = build_context(admin_ids=(1,), backup_service=backup_service)

    await export_backup_command(update, context)

    reply.assert_awaited_once_with("Admin access is required for this action.")
    backup_service.export_backup.assert_not_awaited()


@pytest.mark.asyncio
async def test_export_backup_command_sends_archive_document() -> None:
    update, _ = build_update()
    backup_service = SimpleNamespace(
        export_backup=AsyncMock(
            return_value=BackupArchive(
                filename="backup.zip",
                content=b"zip-data",
                song_count=2,
                chart_count=1,
            )
        )
    )
    context = build_context(backup_service=backup_service)

    await export_backup_command(update, context)

    update.effective_message.reply_document.assert_awaited_once()
    args = update.effective_message.reply_document.await_args.kwargs
    sent_file = args["document"]
    assert sent_file.filename == "backup.zip"
    assert sent_file.input_file_content == b"zip-data"
    assert "Songs: 2" in args["caption"]
    assert "Charts: 1" in args["caption"]


@pytest.mark.asyncio
async def test_import_backup_start_prompts_for_zip_file() -> None:
    update, reply = build_update()
    context = build_context()

    state = await import_backup_start(update, context)

    assert state == IMPORT_BACKUP_UPLOAD
    assert reply.await_args.args[0] == "Send a .zip backup file to import, or tap Cancel."
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == "Cancel"


@pytest.mark.asyncio
async def test_import_backup_file_rejects_non_zip_document() -> None:
    update, reply = build_update()
    update.effective_message.document = SimpleNamespace(
        file_name="backup.txt",
        mime_type="text/plain",
    )
    context = build_context()

    state = await import_backup_file(update, context)

    assert state == IMPORT_BACKUP_UPLOAD
    reply.assert_awaited_once_with("Backup import expects a .zip document file.")


@pytest.mark.asyncio
async def test_import_backup_file_runs_restore_and_reports_success() -> None:
    update, reply = build_update()
    telegram_file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(b"zip")))
    update.effective_message.document = SimpleNamespace(
        file_name="backup.zip",
        mime_type="application/zip",
        get_file=AsyncMock(return_value=telegram_file),
    )
    backup_service = SimpleNamespace(
        import_backup=AsyncMock(return_value=SimpleNamespace(song_count=3, chart_count=2))
    )
    context = build_context(backup_service=backup_service)

    state = await import_backup_file(update, context)

    assert state == -1
    backup_service.import_backup.assert_awaited_once_with(b"zip")
    message = reply.await_args.args[0]
    assert "Songs restored: 3" in message
    assert "Charts restored: 2" in message


@pytest.mark.asyncio
async def test_cancel_command_returns_home_menu() -> None:
    update, reply = build_update()
    context = build_context()
    context.user_data["pending_song"] = {"title": "Amazing Grace"}
    context.user_data["edit_song_id"] = 5
    context.user_data["edit_field"] = "title"

    state = await cancel_command(update, context)

    assert state == -1
    assert context.user_data == {}
    assert reply.await_args.args[0] == (
        "Cancelled.\nSong Vault is ready.\nUse the menu buttons below."
    )
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == MENU_START


@pytest.mark.asyncio
async def test_cancel_upload_chart_returns_home_menu() -> None:
    update, reply = build_update()
    context = build_context()
    context.user_data["upload_chart_state"] = {"song_id": 5}

    state = await cancel_upload_chart(update, context)

    assert state == -1
    assert context.user_data == {}
    assert reply.await_args.args[0] == (
        "Cancelled.\nSong Vault is ready.\nUse the menu buttons below."
    )
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == MENU_START


@pytest.mark.asyncio
async def test_cancel_import_backup_returns_home_menu() -> None:
    update, reply = build_update()
    context = build_context()
    context.user_data["import_backup_state"] = {}

    state = await cancel_import_backup(update, context)

    assert state == -1
    assert context.user_data == {}
    assert reply.await_args.args[0] == (
        "Cancelled.\nSong Vault is ready.\nUse the menu buttons below."
    )
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == MENU_START
