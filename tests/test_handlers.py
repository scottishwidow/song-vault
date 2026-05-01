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
    UPLOAD_CHART_KEY,
    UPLOAD_MEDIA,
    build_upload_chart_handler,
    cancel_upload_chart,
    chart_command,
    upload_chart_chart_key,
    upload_chart_media,
    upload_chart_start,
)
from handlers.common import ensure_admin
from handlers.repertoire import (
    ADD_KEY,
    ADD_SOURCE,
    EDIT_FIELD,
    EDIT_FIELD_KEY,
    EDIT_SONG_ID_KEY,
    EDIT_VALUE,
    RESULT_MESSAGE_CHAR_LIMIT,
    add_song_artist,
    add_song_notes,
    add_song_source,
    build_add_song_handler,
    build_edit_song_handler,
    cancel_command,
    edit_song_cancel_from_callback,
    edit_song_field,
    edit_song_start,
    edit_song_value,
    list_songs_command,
    search_songs_command,
)
from handlers.ui import BUTTON_CANCEL, BUTTON_SKIP, MENU_START
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


def build_callback_update(
    *,
    data: str,
    user_id: int = 1,
) -> tuple[SimpleNamespace, SimpleNamespace, AsyncMock]:
    reply = AsyncMock()
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=SimpleNamespace(reply_text=reply),
        effective_chat=SimpleNamespace(type="private"),
        callback_query=query,
    )
    return update, query, reply


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


def assert_link_previews_disabled(call: object) -> None:
    assert call.kwargs["link_preview_options"].is_disabled is True


@pytest.mark.asyncio
async def test_ensure_admin_rejects_non_admin() -> None:
    update, reply = build_update(user_id=999)
    context = build_context(admin_ids=(1,))

    allowed = await ensure_admin(update, context)

    assert allowed is False
    reply.assert_awaited_once_with("Ця дія доступна лише адміністраторам.")


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

    for state, state_handlers in handler.states.items():
        for state_handler in state_handlers:
            if state == EDIT_FIELD:
                assert not bool(state_handler.check_update(message_update))
                assert not bool(state_handler.check_update(edited_update))
                continue
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
    cancel_update = build_telegram_update(edited=False, text=BUTTON_CANCEL)

    for state_handlers in handler.states.values():
        for state_handler in state_handlers:
            assert not bool(state_handler.check_update(cancel_update))

    assert any(bool(fallback.check_update(cancel_update)) for fallback in handler.fallbacks)


@pytest.mark.asyncio
async def test_search_command_requires_query() -> None:
    update, reply = build_update()
    context = build_context(args=[])

    await search_songs_command(update, context)

    reply.assert_awaited_once_with("Використання: /search <запит>")


@pytest.mark.asyncio
async def test_list_songs_command_reports_empty_repertoire() -> None:
    update, reply = build_update()
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[]))
    context = build_context(song_service=song_service)

    await list_songs_command(update, context)

    reply.assert_awaited_once_with("У репертуарі ще немає активних пісень.")


@pytest.mark.asyncio
async def test_search_command_reports_empty_results_with_specific_copy() -> None:
    update, reply = build_update()
    song_service = SimpleNamespace(search_songs=AsyncMock(return_value=[]))
    context = build_context(args=["missing"], song_service=song_service)

    await search_songs_command(update, context)

    reply.assert_awaited_once_with("За цим запитом пісень не знайдено.")


@pytest.mark.asyncio
async def test_list_songs_command_sends_detailed_song_cards_when_result_fits() -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[song]))
    context = build_context(song_service=song_service)

    await list_songs_command(update, context)

    reply.assert_awaited_once()
    message = reply.await_args.args[0]
    assert "Виконавець: Traditional" in message
    assert "Джерело (оригінал): -" in message
    assert "Нотатки: Slow intro." in message
    assert "Каподастр: 1" in message
    assert "Розмір: 3/4" in message
    assert "Нотатки аранжування:" not in message
    assert not message.startswith("Активні пісні (")


@pytest.mark.asyncio
async def test_list_songs_command_suppresses_previews_for_visible_source_urls() -> None:
    update, reply = build_update()
    song = build_song(source_url="https://example.org/amazing-grace")
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[song]))
    context = build_context(song_service=song_service)

    await list_songs_command(update, context)

    reply.assert_awaited_once()
    assert "Джерело (оригінал): https://example.org/amazing-grace" in reply.await_args.args[0]
    assert_link_previews_disabled(reply.await_args)


@pytest.mark.asyncio
async def test_search_command_sends_detailed_song_cards_when_result_fits() -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(search_songs=AsyncMock(return_value=[song]))
    context = build_context(args=["grace"], song_service=song_service)

    await search_songs_command(update, context)

    reply.assert_awaited_once()
    message = reply.await_args.args[0]
    assert "Виконавець: Traditional" in message
    assert "Джерело (оригінал): -" in message
    assert "Нотатки: Slow intro." in message
    assert "Каподастр: 1" in message
    assert "Розмір: 3/4" in message
    assert not message.startswith('Результати для "grace" (')


@pytest.mark.asyncio
async def test_search_command_suppresses_previews_for_visible_source_urls() -> None:
    update, reply = build_update()
    song = build_song(source_url="https://example.org/amazing-grace")
    song_service = SimpleNamespace(search_songs=AsyncMock(return_value=[song]))
    context = build_context(args=["grace"], song_service=song_service)

    await search_songs_command(update, context)

    reply.assert_awaited_once()
    assert "Джерело (оригінал): https://example.org/amazing-grace" in reply.await_args.args[0]
    assert_link_previews_disabled(reply.await_args)


@pytest.mark.asyncio
async def test_list_songs_command_falls_back_to_compact_summary_when_output_is_long() -> None:
    update, reply = build_update()
    song = build_song(notes="x" * (RESULT_MESSAGE_CHAR_LIMIT + 100))
    song_service = SimpleNamespace(list_songs=AsyncMock(return_value=[song]))
    context = build_context(song_service=song_service)

    await list_songs_command(update, context)

    reply.assert_awaited_once()
    message = reply.await_args.args[0]
    assert message.startswith("Активні пісні (1):")
    assert "#5 Amazing Grace | Traditional | Тональність: G" in message
    assert "Нотатки:" not in message
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
    assert message.startswith('Результати для "grace" (1):')
    assert "#5 Amazing Grace | Traditional | Тональність: G" in message
    assert "Нотатки:" not in message
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
    assert messages[0].startswith('Результати для "setlist" (220):')
    assert messages[1].startswith(
        f'Результати для "setlist" (220) (продовження 2/{len(messages)}):'
    )
    assert "#1 Song 1 | Source 1 | Тональність: C" in messages[0]
    assert all(len(message) <= RESULT_MESSAGE_CHAR_LIMIT for message in messages)


@pytest.mark.asyncio
async def test_chart_command_requires_song_id() -> None:
    update, reply = build_update()
    context = build_context(args=[])

    await chart_command(update, context)

    reply.assert_awaited_once_with("Використання: /chart <id_пісні>")


@pytest.mark.asyncio
async def test_chart_command_reports_missing_chart() -> None:
    update, reply = build_update()
    chart_service = SimpleNamespace(
        get_active_chart_file=AsyncMock(side_effect=SongChartNotFoundError())
    )
    context = build_context(args=["7"], chart_service=chart_service)

    await chart_command(update, context)

    reply.assert_awaited_once_with("Для пісні #7 ще не завантажено гармонію.")


@pytest.mark.asyncio
async def test_upload_chart_start_requires_admin() -> None:
    update, reply = build_update(user_id=2)
    chart_service = SimpleNamespace(assert_song_exists=AsyncMock())
    context = build_context(args=["5"], admin_ids=(1,), chart_service=chart_service)

    state = await upload_chart_start(update, context)

    assert state == -1
    reply.assert_awaited_once_with("Ця дія доступна лише адміністраторам.")
    chart_service.assert_song_exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_chart_start_requires_song_id_arg() -> None:
    update, reply = build_update()
    chart_service = SimpleNamespace(assert_song_exists=AsyncMock())
    context = build_context(args=[], chart_service=chart_service)

    state = await upload_chart_start(update, context)

    assert state == -1
    reply.assert_awaited_once_with("Використання: /uploadchart <id_пісні>")


@pytest.mark.asyncio
async def test_upload_chart_start_reports_missing_song() -> None:
    update, reply = build_update()
    chart_service = SimpleNamespace(
        assert_song_exists=AsyncMock(side_effect=SongNotFoundError("Пісню 10 не знайдено."))
    )
    context = build_context(args=["10"], chart_service=chart_service)

    state = await upload_chart_start(update, context)

    assert state == -1
    reply.assert_awaited_once_with("Пісню 10 не знайдено.")


@pytest.mark.asyncio
async def test_upload_chart_media_moves_directly_to_chart_key_step() -> None:
    update, reply = build_update()
    telegram_file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(b"img")))
    update.effective_message.photo = [
        SimpleNamespace(get_file=AsyncMock(return_value=telegram_file))
    ]
    context = build_context()
    context.user_data["upload_chart_state"] = {"song_id": 5}

    state = await upload_chart_media(update, context)

    assert state == UPLOAD_CHART_KEY
    assert reply.await_args.args[0] == (
        "Тональність гармонії необов'язкова. Надішліть текст або «Пропустити»."
    )
    keyboard = reply.await_args.kwargs["reply_markup"]
    assert keyboard.keyboard[0][0].text == BUTTON_SKIP
    assert keyboard.keyboard[0][1].text == BUTTON_CANCEL


@pytest.mark.asyncio
async def test_upload_chart_media_rejects_non_image_with_harmony_copy() -> None:
    update, reply = build_update()
    update.effective_message.photo = []
    update.effective_message.document = SimpleNamespace(
        mime_type="application/pdf",
        file_name="chart.pdf",
    )
    context = build_context()
    context.user_data["upload_chart_state"] = {"song_id": 5}

    state = await upload_chart_media(update, context)

    assert state == UPLOAD_MEDIA
    reply.assert_awaited_once_with(
        "Надішліть фото або зображення-документ гармонії (наприклад, image/png)."
    )


def test_upload_chart_handler_skips_source_url_step() -> None:
    handler = build_upload_chart_handler()
    callbacks = {
        state_handler.callback.__name__
        for handlers in handler.states.values()
        for state_handler in handlers
    }
    assert "upload_chart_source_url" not in callbacks


@pytest.mark.asyncio
async def test_upload_chart_chart_key_sends_success_and_next_actions() -> None:
    update, reply = build_update()
    update.effective_message.text = "G"
    chart_service = SimpleNamespace(upload_chart=AsyncMock(return_value=SimpleNamespace(id=12)))
    context = build_context(chart_service=chart_service)
    context.user_data["upload_chart_state"] = {
        "song_id": 5,
        "content": b"img",
        "content_type": "image/png",
        "filename": "song-5-chart.png",
        "return_mode": "upload",
        "return_page": 3,
    }

    state = await upload_chart_chart_key(update, context)

    assert state == -1
    assert "upload_chart_state" not in context.user_data
    assert reply.await_count == 2
    assert reply.await_args_list[0].args[0] == "Гармонію #12 для пісні #5 завантажено."
    assert reply.await_args_list[0].kwargs["reply_markup"].keyboard[0][0].text == MENU_START
    callbacks = [
        button.callback_data
        for row in reply.await_args_list[1].kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["song:detail:5:3", "browser:page:u:3", "nav:home"]


@pytest.mark.asyncio
async def test_edit_song_start_shows_editable_field_previews() -> None:
    update, reply = build_update()
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(args=["5"], song_service=song_service)

    state = await edit_song_start(update, context)

    assert state == EDIT_FIELD
    message = reply.await_args.args[0]
    assert "Поточні поля для редагування:" in message
    assert "назва: Amazing Grace" in message
    assert "виконавець: Traditional" in message
    assert "джерело: -" in message
    assert "каподастр: 1" in message
    assert "розмір: 3/4" in message
    assert "темп: 72" in message
    assert "теги: hymn, classic" in message
    assert "нотатки: Slow intro." in message
    assert "нотатки аранжування:" not in message
    assert "Натисніть «Скасувати», щоб зупинити." in message
    keyboard = reply.await_args.kwargs["reply_markup"]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert labels == [
        "назва",
        "виконавець",
        "джерело",
        "тональність",
        "каподастр",
        "розмір",
        "темп",
        "теги",
        "нотатки",
        BUTTON_CANCEL,
    ]
    assert "edit:field:5:title" in callback_data
    assert "edit:field:5:source" in callback_data
    assert "edit:field:5:tempo" in callback_data
    assert callback_data[-1] == "edit:cancel"


@pytest.mark.asyncio
async def test_edit_song_start_suppresses_previews_for_visible_source_url() -> None:
    update, reply = build_update()
    song = build_song(source_url="https://example.org/source")
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(args=["5"], song_service=song_service)

    state = await edit_song_start(update, context)

    assert state == EDIT_FIELD
    assert "Джерело (оригінал): https://example.org/source" in reply.await_args.args[0]
    assert_link_previews_disabled(reply.await_args)


@pytest.mark.asyncio
async def test_add_song_artist_prompts_for_source_with_original_link_text() -> None:
    update, reply = build_update()
    context = build_context()
    context.user_data["pending_song"] = {"title": "Amazing Grace"}
    update.effective_message.text = "Traditional"

    state = await add_song_artist(update, context)

    assert state == ADD_SOURCE
    assert reply.await_args.args[0] == "Надішліть джерело пісні або «Пропустити»."


@pytest.mark.asyncio
async def test_add_song_source_prompts_for_original_key() -> None:
    update, reply = build_update()
    context = build_context()
    context.user_data["pending_song"] = {"title": "Amazing Grace", "artist": "Traditional"}
    update.effective_message.text = "Пропустити"

    state = await add_song_source(update, context)

    assert state == ADD_KEY
    assert reply.await_args.args[0] == "Надішліть оригінальну тональність."


@pytest.mark.asyncio
async def test_add_song_notes_creates_song_without_arrangement_notes_step() -> None:
    update, reply = build_update()
    update.effective_message.text = "Пропустити"
    created_song = build_song()
    song_service = SimpleNamespace(create_song=AsyncMock(return_value=created_song))
    context = build_context(song_service=song_service)
    context.user_data["pending_song"] = {
        "title": "Amazing Grace",
        "artist": "Traditional",
        "source_url": None,
        "key": "G",
        "capo": 1,
        "time_signature": "3/4",
        "tempo_bpm": 72,
        "tags": ["hymn", "classic"],
    }

    state = await add_song_notes(update, context)

    assert state == -1
    payload = song_service.create_song.await_args.args[0]
    assert payload.arrangement_notes is None
    assert "Пісню створено:" in reply.await_args.args[0]


@pytest.mark.asyncio
async def test_add_song_notes_suppresses_previews_for_visible_source_url() -> None:
    update, reply = build_update()
    update.effective_message.text = "Пропустити"
    created_song = build_song(source_url="https://example.org/source")
    song_service = SimpleNamespace(create_song=AsyncMock(return_value=created_song))
    context = build_context(song_service=song_service)
    context.user_data["pending_song"] = {
        "title": "Amazing Grace",
        "artist": "Traditional",
        "source_url": "https://example.org/source",
        "key": "G",
        "capo": 1,
        "time_signature": "3/4",
        "tempo_bpm": 72,
        "tags": ["hymn", "classic"],
    }

    state = await add_song_notes(update, context)

    assert state == -1
    assert "Джерело (оригінал): https://example.org/source" in reply.await_args.args[0]
    assert_link_previews_disabled(reply.await_args)


@pytest.mark.asyncio
async def test_edit_song_field_shows_prompt_with_current_value() -> None:
    update, query, reply = build_callback_update(data="edit:field:5:tempo")
    song = build_song()
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = song.id

    state = await edit_song_field(update, context)

    assert state == EDIT_VALUE
    query.answer.assert_awaited_once()
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert context.user_data[EDIT_FIELD_KEY] == "tempo"
    message = reply.await_args.args[0]
    assert "Новий темп (BPM)? Надішліть число або «очистити»." in message
    assert "Поточне значення поля «темп»: 72" in message
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == BUTTON_CANCEL


@pytest.mark.asyncio
async def test_edit_song_field_accepts_source_field() -> None:
    update, query, reply = build_callback_update(data="edit:field:5:source")
    song = build_song(source_url="https://example.org/source")
    song_service = SimpleNamespace(get_song=AsyncMock(return_value=song))
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = song.id

    state = await edit_song_field(update, context)

    assert state == EDIT_VALUE
    query.answer.assert_awaited_once()
    assert context.user_data[EDIT_FIELD_KEY] == "source"
    message = reply.await_args.args[0]
    assert "Нове джерело? Надішліть текст або «очистити»." in message
    assert "Поточне значення поля «джерело»: https://example.org/source" in message
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == BUTTON_CANCEL


@pytest.mark.asyncio
async def test_edit_song_field_handles_invalid_callback_data() -> None:
    update, query, _ = build_callback_update(data="edit:field:5:unsupported")
    song_service = SimpleNamespace(get_song=AsyncMock())
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = 5

    state = await edit_song_field(update, context)

    assert state == -1
    assert EDIT_SONG_ID_KEY not in context.user_data
    assert EDIT_FIELD_KEY not in context.user_data
    query.answer.assert_awaited_once()
    query.edit_message_text.assert_awaited_once_with("Не вдалося розпізнати поле для редагування.")
    song_service.get_song.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_song_cancel_from_callback_returns_home_menu() -> None:
    update, query, reply = build_callback_update(data="edit:cancel")
    context = build_context()
    context.user_data[EDIT_SONG_ID_KEY] = 5
    context.user_data[EDIT_FIELD_KEY] = "title"

    state = await edit_song_cancel_from_callback(update, context)

    assert state == -1
    assert context.user_data == {}
    query.answer.assert_awaited_once()
    query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert reply.await_args.args[0] == (
        "Скасовано.\nБот готовий.\nКористуйтеся кнопками меню нижче."
    )
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == MENU_START


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
    assert "Темп має бути числом або «очистити»." in message
    assert "Поточне значення поля «темп»: 72" in message
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
    assert "Поле «назва» не може бути порожнім. Надішліть непорожнє значення." in message
    assert "Поточне значення поля «назва»: Amazing Grace" in message
    song_service.update_song.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "expected_error"),
    [
        ("source", "Джерело має бути текстом або «очистити»."),
        ("time_signature", "Розмір має бути текстом або «очистити»."),
        ("tags", "Теги мають бути значеннями через кому або «очистити»."),
        ("notes", "Нотатки мають бути текстом або «очистити»."),
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
    context.user_data["song_browser_state"] = {
        "mode": "browse",
        "title": "Активні пісні",
        "items": [{"id": 5, "title": "Amazing Grace", "artist": "Traditional"}],
        "current_page": 2,
    }
    update.effective_message.text = "Amazing Grace (Acoustic)"

    state = await edit_song_value(update, context)

    assert state == -1
    assert EDIT_SONG_ID_KEY not in context.user_data
    assert EDIT_FIELD_KEY not in context.user_data
    update_payload = song_service.update_song.await_args.args[1]
    assert update_payload.values() == {"title": "Amazing Grace (Acoustic)"}
    assert reply.await_count == 2
    assert "Пісню оновлено:" in reply.await_args_list[0].args[0]
    assert reply.await_args_list[0].kwargs["reply_markup"].keyboard[0][0].text == MENU_START
    callbacks = [
        button.callback_data
        for row in reply.await_args_list[1].kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["song:detail:5:2", "browser:page:b:2", "nav:home"]


@pytest.mark.asyncio
async def test_edit_song_value_suppresses_previews_for_visible_source_url() -> None:
    update, reply = build_update()
    updated_song = build_song(source_url="https://example.org/source")
    song_service = SimpleNamespace(
        update_song=AsyncMock(return_value=updated_song),
    )
    context = build_context(song_service=song_service)
    context.user_data[EDIT_SONG_ID_KEY] = updated_song.id
    context.user_data[EDIT_FIELD_KEY] = "title"
    update.effective_message.text = "Amazing Grace"

    state = await edit_song_value(update, context)

    assert state == -1
    success_call = reply.await_args_list[0]
    assert "Джерело (оригінал): https://example.org/source" in success_call.args[0]
    assert_link_previews_disabled(success_call)


@pytest.mark.asyncio
async def test_export_backup_command_requires_admin() -> None:
    update, reply = build_update(user_id=2)
    backup_service = SimpleNamespace(export_backup=AsyncMock())
    context = build_context(admin_ids=(1,), backup_service=backup_service)

    await export_backup_command(update, context)

    reply.assert_awaited_once_with("Ця дія доступна лише адміністраторам.")
    backup_service.export_backup.assert_not_awaited()


@pytest.mark.asyncio
async def test_export_backup_command_sends_archive_document() -> None:
    update, reply = build_update()
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
    assert "Пісень: 2" in args["caption"]
    assert "Файлів гармонії: 1" in args["caption"]
    assert reply.await_count == 2
    assert reply.await_args_list[0].args[0] == "Резервну копію експортовано."
    assert reply.await_args_list[0].kwargs["reply_markup"].keyboard[0][0].text == MENU_START
    callbacks = [
        button.callback_data
        for row in reply.await_args_list[1].kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["backup:menu", "nav:home"]


@pytest.mark.asyncio
async def test_import_backup_start_prompts_for_zip_file() -> None:
    update, reply = build_update()
    context = build_context()

    state = await import_backup_start(update, context)

    assert state == IMPORT_BACKUP_UPLOAD
    assert reply.await_args.args[0] == (
        "Надішліть .zip файл резервної копії або натисніть «Скасувати»."
    )
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == BUTTON_CANCEL


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
    reply.assert_awaited_once_with("Потрібен .zip файл резервної копії, надісланий документом.")


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
    assert reply.await_count == 2
    message = reply.await_args_list[0].args[0]
    assert "Відновлено пісень: 3" in message
    assert "Відновлено файлів гармонії: 2" in message
    assert reply.await_args_list[0].kwargs["reply_markup"].keyboard[0][0].text == MENU_START
    callbacks = [
        button.callback_data
        for row in reply.await_args_list[1].kwargs["reply_markup"].inline_keyboard
        for button in row
    ]
    assert callbacks == ["backup:menu", "nav:home"]


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
        "Скасовано.\nБот готовий.\nКористуйтеся кнопками меню нижче."
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
        "Скасовано.\nБот готовий.\nКористуйтеся кнопками меню нижче."
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
        "Скасовано.\nБот готовий.\nКористуйтеся кнопками меню нижче."
    )
    assert reply.await_args.kwargs["reply_markup"].keyboard[0][0].text == MENU_START
